# Distinguishing Context Smoke Tests from Business Behavior Tests

When you first create a Spring Boot project, you usually see a test class named `ApplicationTests` with an empty method:

```java
@SpringBootTest
class ApplicationTests {

    @Test
    void contextLoads() {
    }
}
```

This method calls no services, sends no HTTP requests, and compares no values. Yet it has real value: if it passes, Spring Boot succeeded in initializing the required `ApplicationContext` in that test environment.

Problems arise when people mistake **a successfully starting context for a properly tested application**. A service computing the wrong total, an API returning the wrong status code, a repository saving incorrect fields, or a bypassed authorization rule can all exist while `contextLoads()` stays green.

This lesson belongs to the **Platform Testing** chapter of **Spring Boot Fundamentals**. Its focus is distinguishing:

- **Context smoke tests:** quick verification of Spring context bootstrapping and wiring under test configuration.
- **Business behavior tests:** providing inputs, executing behavior, and asserting outputs, side effects, or exceptions really meet requirements.
- **Integration and HTTP contract tests:** verifying components collaborate properly across boundaries like controllers, persistence, and external systems.

After this lesson, you should know what each test type proves, what it **does not prove**, and why a trustworthy Spring Boot test suite requires multiple testing layers rather than a lone `contextLoads()`.

## 1. What is a smoke test?

In software testing, a "smoke test" is a quick check verifying that a system or subsystem is stable enough for deeper testing. In Spring Boot, a **context smoke test** checks whether `ApplicationContext` creation completes without error.

Example:

```java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class ShopApplicationTests {

    @Test
    void contextLoads() {
    }
}
```

Running this test class triggers Spring Test to use the Spring Boot bootstrap to build a context for the application. If configuration fails while loading the context, the test is marked failed.

### 1.1. Why can the test method be empty?

Because **Spring context preparation occurs before JUnit invokes the method**.

Flow:

```text
JUnit discovers test class
           │
           ▼
Spring TestContext Framework
           │
           ▼
Spring Boot test bootstrap
           │
           ▼
Read test config, profiles, properties
           │
           ▼
Process configuration/auto-configuration
           │
           ▼
Instantiate and inject required beans
           │
           ▼
Refresh ApplicationContext
           │
      ┌────┴─────┐
      │          │
      ▼          ▼
   Success    Failure
      │          │
      ▼          ▼
Invoke         Report test
contextLoads() failed
      │
      ▼
Test passes
```

An empty method does not mean "testing nothing." It indirectly checks that the Spring TestContext bootstrap process completed cleanly under test conditions.

### 1.2. Examples of errors a context smoke test can catch

Suppose the application needs these beans:

```java
@Service
public class CheckoutService {

    private final InventoryClient inventoryClient;

    public CheckoutService(InventoryClient inventoryClient) {
        this.inventoryClient = inventoryClient;
    }
}
```

but the test context has no matching `InventoryClient` bean—creating `CheckoutService` fails.

Other scenarios:

- Two beans share a type and injection lacks a clear candidate rule.
- A constructor dependency cannot be resolved.
- A `@Configuration` fails while creating a bean.
- A mandatory `@ConfigurationProperties` fails binding or validation.
- An auto-configuration needs an infrastructure component that is absent.
- Certain external service connection errors appear at bean creation time if the app connects eagerly then.
- Classpath or component scan issues produce invalid configuration.
- A bean initialization callback throws an exception.

Still, a smoke test catches only issues **actually triggered during test context initialization**.

## 2. Why isn't contextLoads enough to claim the app is right?

Consider a pricing service:

```java
@Service
public class PriceService {

    public BigDecimal total(
            BigDecimal unitPrice,
            int quantity
    ) {
        return unitPrice.add(
                BigDecimal.valueOf(quantity)
        );
    }
}
```

The required business rule is:

```text
total = unitPrice × quantity
```

Yet the code used addition.

Spring creates `PriceService` without trouble. No missing dependencies, no annotation errors, and no startup exceptions.

Therefore:

```java
@SpringBootTest
class ShopApplicationTests {

    @Test
    void contextLoads() {
    }
}
```

passes completely.

To catch the bug, you need a **behavior test**:

```java
@Test
void calculatesTotalFromUnitPriceAndQuantity() {
    PriceService service = new PriceService();

    BigDecimal total = service.total(
            new BigDecimal("12.50"),
            2
    );

    assertThat(total)
            .isEqualByComparingTo("25.00");
}
```

This test fails if the service adds instead of multiplying.

### 2.1. Comparison table

| Question | Context smoke test | Behavior test |
|---|---|---|
| Can the Spring context initialize? | Primary goal | Not necessarily |
| Do bean dependencies resolve? | Catches wiring defects | Only when the test uses real wiring |
| Is the pricing formula right? | No | Yes, with appropriate assertions |
| Does validation reject negative quantity? | No | Yes |
| Does the API return HTTP 201 per contract? | No | Yes in web tests |
| Does the repository query the right rows? | Insufficient | Yes in repository/integration tests |
| Does security block unauthorized users? | No | Yes in security/HTTP tests |
| Do real external integrations work? | Uncertain | Yes if integration tests actually connect |
| Is the app production-ready? | No | A few behavior tests alone aren't enough either |

**Key point:** a test suite can include both smoke tests and behavior tests. Keep `contextLoads()`, but never let it replace business testing.

## 3. What does a single test prove?

Before writing test code, state the test goal in one concrete sentence.

Examples:

**Goal A:**

> Under the `test` profile, the application builds its Spring `ApplicationContext` with no bean wiring errors.

This is a context smoke test goal.

**Goal B:**

> When a user buys 2 items priced at 12.50, the total must be 25.00.

This is a business rule behavior test.

**Goal C:**

> When a client sends a valid POST `/purchases`, the API returns HTTP 201 with a JSON receipt.

This is an HTTP contract test.

**Goal D:**

> When saving a `Purchase` record to the test database and reading it back, values are preserved.

This is a persistence integration test.

A good test has clear **inputs**, **action**, and **expected outcome**, aside from smoke tests whose primary goal is completing bootstrap without throwing.

## 4. Testing layers in a Spring Boot application

You can organize a test suite into pragmatic groups:

| Test type | Spring context? | External dependencies? | Goal |
|---|---|---|---|
| Plain Java unit test | Not needed | Usually mocks/fakes | Verify algorithms, rules, error handling |
| Context smoke test | Yes | Depends on configuration | Verify bootstrap and bean wiring |
| Spring test slice | Limited context | Usually replaced / test setup | Verify a single layer such as MVC/JPA |
| Full-context integration test | Yes | Real or test doubles | Verify multi-bean collaboration |
| End-to-end / API integration test | Often real server | May include test dependencies | Verify HTTP/persistence across boundaries |
| Multi-service system/E2E test | Multiple processes/systems | Usually present | Verify user journeys across systems |

These are not rigid universal labels required by every project. More important than labels are the test's real scope, which dependencies are real, and which behavior assertions verify.

### 4.1. Two tests can both use @SpringBootTest with different purposes

Both classes use `@SpringBootTest`:

```java
@SpringBootTest
class ContextSmokeTest {

    @Test
    void contextLoads() {
    }
}
```

```java
@SpringBootTest
class CheckoutIntegrationTest {

    @Autowired
    CheckoutService checkoutService;

    @Test
    void rejectsInvalidQuantity() {
        assertThatThrownBy(
                () -> checkoutService.checkout("SKU-1", 0)
        ).isInstanceOf(IllegalArgumentException.class);
    }
}
```

The first checks only the context. The second executes a behavior and asserts the outcome, even though it also boots a full Spring context.

Thus, **annotations alone do not define a test's value**. A test's value comes from what is executed and asserted.

## 5. What does @SpringBootTest do?

`@SpringBootTest` is Spring Boot Test's integration annotation for bootstrapping a Spring application context for tests.

Typically:

```java
import org.springframework.boot.test.context.SpringBootTest;
```

Example:

```java
@SpringBootTest
class ApplicationContextTest {

    @Test
    void contextLoads() {
    }
}
```

Spring Boot searches for the appropriate application configuration—usually a class carrying `@SpringBootConfiguration` or `@SpringBootApplication` in a matching package hierarchy—and prepares the context for the test environment.

### 5.1. Test contexts are not identical to production processes

Differences can stem from:

- Different profiles.
- Different system properties or environment variables.
- Test-specific properties.
- Test doubles or mock beans.
- Embedded databases or test containers instead of production databases.
- `@SpringBootTest` web environment settings.
- Test classpath containing dependencies absent in production.
- Security or test configurations.
- External integrations replaced or disabled.

Therefore, when `contextLoads()` is green, the accurate conclusion is:

> The context initialized cleanly **under this test's configuration**.

Not:

> Every production deployment is guaranteed to start and work properly.

### 5.2. Keeping test classes in the right package

Suppose the main class is:

```java
package com.example.shop;

@SpringBootApplication
public class ShopApplication {
}
```

The test class belongs in the same package or a subpackage:

```java
package com.example.shop;

@SpringBootTest
class ShopApplicationTests {
}
```

This usually lets Spring Boot find the application configuration and run component scanning properly.

If a test resides in an unrelated package, declare:

```java
@SpringBootTest(classes = ShopApplication.class)
```

Do not drop an extra `@SpringBootApplication` into a test package just to make a test run if it inadvertently alters scan scope and makes the test differ from production.

## 6. @SpringBootTest and webEnvironment choices

`@SpringBootTest` provides `webEnvironment`, with common modes:

| Value | Meaning |
|---|---|
| `MOCK` | Creates a web context / mock web environment when a web stack is present, without starting a real embedded server |
| `RANDOM_PORT` | Starts the web server on a randomly chosen port |
| `DEFINED_PORT` | Starts the web server on the configured port |
| `NONE` | Creates a non-web application context |

### 6.1. Default MOCK does not mean a live server is running

Example:

```java
@SpringBootTest
class ShopApplicationTests {
}
```

By default, `webEnvironment = MOCK`. With an eligible web stack, Spring builds a mock web application context without opening a real embedded server on a network port.

Hence, `contextLoads()` in this mode does not prove HTTP requests over TCP will be handled properly.

### 6.2. NONE for tests not needing web

```java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class BatchApplicationSmokeTest {

    @Test
    void contextLoads() {
    }
}
```

Fits batch/CLI applications or integration tests not needing a web server.

However, if production is a Servlet web app, choosing `NONE` changes the context type and may skip web-only auto-configurations. Do not treat a `NONE` smoke test as proof that full web infrastructure will start properly.

### 6.3. RANDOM_PORT to test real HTTP communication

```java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class ShopHttpIntegrationTest {
}
```

This starts a web server on a port chosen at runtime. Tests can send HTTP requests over the local network interface.

Still, **adding `RANDOM_PORT` with an empty test method** does not test HTTP behavior. You must actually send requests and assert responses.

### 6.4. Do not overuse DEFINED_PORT

`DEFINED_PORT` can collide with another process or cause conflicts during parallel test runs.

`RANDOM_PORT` is usually preferable for automated HTTP integration tests, because each test context receives an available port.

## 7. How should a context smoke test be written?

A short, clear smoke test:

```java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class ShopApplicationSmokeTest {

    @Test
    void contextLoads() {
        // Succeeds when ApplicationContext is initialized.
    }
}
```

No need to write:

```java
assertThat(true).isTrue();
```

That assertion checks nothing meaningful.

### 7.1. Should you assert the context is non-null?

You can inject the context:

```java
@SpringBootTest
class ShopApplicationSmokeTest {

    @Autowired
    ApplicationContext context;

    @Test
    void contextLoads() {
        assertThat(context).isNotNull();
    }
}
```

That gives the test an explicit assertion, though most of the value still comes from loading the context itself. If the context fails to build, the test fails before any assertion executes.

Do not turn a smoke test into hundreds of lines of `getBean(...)` calls when the goal is strictly bootstrap health.

### 7.2. Do not tie smoke tests to incidental business outputs

If a smoke test calls a business API, queries a database, and checks business rules, it is no longer just a smoke test. There is nothing wrong with integration tests, but name and organize them clearly so readers know why a test failed.

## 8. Example with a bug where the context still loads

Suppose the service is:

```java
package com.example.shop.pricing;

import java.math.BigDecimal;
import org.springframework.stereotype.Service;

@Service
public class PricingService {

    public BigDecimal calculateTotal(
            BigDecimal unitPrice,
            int quantity
    ) {
        // BUG: should multiply, not add.
        return unitPrice.add(
                BigDecimal.valueOf(quantity)
        );
    }
}
```

All dependencies are valid, so `contextLoads()` passes.

Yet the behavior test:

```java
package com.example.shop.pricing;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class PricingServiceTest {

    private final PricingService pricingService =
            new PricingService();

    @Test
    void calculatesTotal() {
        BigDecimal actual = pricingService.calculateTotal(
                new BigDecimal("12.50"),
                2
        );

        assertThat(actual)
                .isEqualByComparingTo("25.00");
    }
}
```

fails against the implementation above.

Fix the service:

```java
public BigDecimal calculateTotal(
        BigDecimal unitPrice,
        int quantity
) {
    return unitPrice.multiply(
            BigDecimal.valueOf(quantity)
    );
}
```

Now the behavior test verifies the exact rule, not merely that the class was registered in the context.

### 8.1. Why doesn't this test need Spring?

`PricingService` is a plain Java object needing no dependency injection, transactions, or web infrastructure to test its calculation.

Instantiating it with `new` in a unit test is therefore faster and clearer than booting an entire `ApplicationContext`.

**Not every class annotated with `@Service` must be tested with `@SpringBootTest`.**

## 9. Unit tests: inputs, outputs, and side effects

A unit test aims to verify the behavior of a small unit of code under controlled conditions. Most cases require no Spring container.

A readable structure:

1. **Arrange:** prepare data and dependencies.
2. **Act:** invoke the method under test.
3. **Assert:** verify output and side effects.

Example:

```java
@Test
void rejectsNonPositiveQuantity() {
    PricingService pricingService = new PricingService();

    assertThatThrownBy(
            () -> pricingService.calculateTotal(
                    new BigDecimal("12.50"),
                    0
            )
    )
    .isInstanceOf(IllegalArgumentException.class);
}
```

This test only holds if the implementation actually validates input:

```java
public BigDecimal calculateTotal(
        BigDecimal unitPrice,
        int quantity
) {
    if (quantity <= 0) {
        throw new IllegalArgumentException(
                "quantity must be positive"
        );
    }

    if (unitPrice.signum() < 0) {
        throw new IllegalArgumentException(
                "unitPrice must not be negative"
        );
    }

    return unitPrice.multiply(
            BigDecimal.valueOf(quantity)
    );
}
```

Crucially, tests must verify **the required business rule**. Never write a test asserting buggy behavior simply because the current code behaves that way.

### 9.1. Cases worth testing

For `calculateTotal`, consider at minimum:

| Input | Expected |
|---|---|
| `unitPrice = 12.50`, `quantity = 2` | `25.00` |
| `unitPrice = 0`, `quantity = 3` | `0` |
| `quantity = 0` | Validation exception |
| Negative `quantity` | Validation exception |
| Negative `unitPrice` | Validation exception |
| Large `unitPrice`, large `quantity` | Exact result without overflow thanks to `BigDecimal` |
| Decimals like `0.10` | No precision loss thanks to proper `BigDecimal` usage |

A context smoke test exercises none of the rows in this table.

## 10. JUnit 5 and AssertJ in Spring Boot tests

Spring Boot typically provides JUnit Jupiter and AssertJ via `spring-boot-starter-test` in test scope.

Gradle:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

Test libraries are managed by the project's matching BOM/version.

### 10.1. JUnit marks test methods

```java
import org.junit.jupiter.api.Test;

@Test
void shouldCalculateTotal() {
    // ...
}
```

### 10.2. AssertJ asserts behavior

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
```

Example:

```java
assertThat(result).isEqualTo(expected);

assertThatThrownBy(() -> service.execute(invalidInput))
        .isInstanceOf(IllegalArgumentException.class);
```

Or using JUnit assertions:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
```

Both styles are widely used. Follow your project's consistent convention.

### 10.3. Give tests behavior-descriptive names

A name like:

```java
void test1()
```

does not say what is being tested.

Better:

```java
void calculatesTotalForMultipleItems()
void rejectsZeroQuantity()
void doesNotPersistWhenPriceLookupFails()
```

Specific names help readers understand contracts and make CI failure reports meaningful.

## 11. Behavior tests with dependencies: using Mockito

Most services do more than pure arithmetic. They call repositories, HTTP clients, or other services.

Suppose a purchasing flow involves:

```text
CheckoutService
    │
    ├── ProductCatalog: fetch unit price
    │
    └── PurchaseRepository: persist order
```

When unit testing `CheckoutService`, you can replace dependencies with Mockito mocks to focus on service logic.

### 11.1. Declaring contracts

```java
package com.example.shop.checkout;

import java.math.BigDecimal;

public interface ProductCatalog {

    BigDecimal unitPrice(String sku);
}
```

```java
package com.example.shop.checkout;

import java.math.BigDecimal;

public interface PurchaseRepository {

    void save(
            String sku,
            int quantity,
            BigDecimal total
    );
}
```

Record response:

```java
package com.example.shop.checkout;

import java.math.BigDecimal;

public record CheckoutReceipt(
        String sku,
        int quantity,
        BigDecimal total
) {
}
```

On projects using Java 17 or newer, `record` is a concise choice for value objects. On older Java versions, use a regular class.

### 11.2. Service enforcing rules

```java
package com.example.shop.checkout;

import java.math.BigDecimal;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private final ProductCatalog catalog;
    private final PurchaseRepository repository;

    public CheckoutService(
            ProductCatalog catalog,
            PurchaseRepository repository
    ) {
        this.catalog = catalog;
        this.repository = repository;
    }

    public CheckoutReceipt checkout(
            String sku,
            int quantity
    ) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException(
                    "sku must not be blank"
            );
        }

        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive"
            );
        }

        BigDecimal price = catalog.unitPrice(sku);

        if (price == null || price.signum() < 0) {
            throw new IllegalStateException(
                    "invalid product price"
            );
        }

        BigDecimal total = price.multiply(
                BigDecimal.valueOf(quantity)
        );

        repository.save(sku, quantity, total);

        return new CheckoutReceipt(
                sku,
                quantity,
                total
        );
    }
}
```

Rules to verify:

- SKU is not blank.
- Quantity is greater than 0.
- Price is retrieved from the catalog.
- Null or negative prices are rejected.
- Total = price × quantity.
- Repository is written only when data is valid.
- Receipt reflects the processed data.

Merely instantiating this bean is only the starting point; the rules above require behavior tests.

## 12. Unit testing CheckoutService with MockitoExtension

Unit tests require no Spring context:

```java
package com.example.shop.checkout;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.verify;

@ExtendWith(MockitoExtension.class)
class CheckoutServiceTest {

    @Mock
    ProductCatalog catalog;

    @Mock
    PurchaseRepository repository;

    @InjectMocks
    CheckoutService service;

    @Test
    void calculatesTotalAndPersistsPurchase() {
        given(catalog.unitPrice("SKU-1"))
                .willReturn(new BigDecimal("12.50"));

        CheckoutReceipt receipt =
                service.checkout("SKU-1", 2);

        assertThat(receipt.sku())
                .isEqualTo("SKU-1");

        assertThat(receipt.quantity())
                .isEqualTo(2);

        assertThat(receipt.total())
                .isEqualByComparingTo("25.00");

        verify(repository).save(
                "SKU-1",
                2,
                new BigDecimal("25.00")
        );
    }
}
```

Here:

- Mockito creates both mocks.
- `@InjectMocks` creates and injects `CheckoutService`.
- `given(...).willReturn(...)` stubs the catalog.
- Assertions check the receipt.
- `verify(...)` verifies the repository save side effect.

**No `@SpringBootTest`**. Unit tests stay fast because they skip loading an entire context.

### 12.1. Testing validation and absence of side effects

```java
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.verifyNoInteractions;

@Test
void rejectsZeroQuantityBeforeCallingDependencies() {
    assertThatThrownBy(
            () -> service.checkout("SKU-1", 0)
    )
    .isInstanceOf(IllegalArgumentException.class)
    .hasMessageContaining("quantity");

    verifyNoInteractions(catalog, repository);
}
```

This is a high-value behavior test: it confirms both the exception and that dependencies are untouched on invalid input.

### 12.2. Testing dependency failures

```java
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.verifyNoInteractions;

@Test
void doesNotPersistWhenCatalogFails() {
    given(catalog.unitPrice("SKU-1"))
            .willThrow(new IllegalStateException(
                    "catalog unavailable"
            ));

    assertThatThrownBy(
            () -> service.checkout("SKU-1", 2)
    )
    .isInstanceOf(IllegalStateException.class)
    .hasMessageContaining("catalog unavailable");

    verifyNoInteractions(repository);
}
```

The test proves the service does not save a purchase if price lookup fails. `contextLoads()` can never catch a side-effect rule like this.

### 12.3. Do not verify every internal detail

Mocking is valuable, yet overusing `verify` on every call couples tests tightly to implementation details.

Prioritize:

1. Return values.
2. Important state changes and side effects.
3. Exception/error contracts.
4. Collaborator interactions genuinely part of the business contract.

Do not verify every getter or internal helper just because you can.

## 13. When should a behavior test use a Spring context?

Not every behavior is best tested in plain Java.

Some behaviors are supplied by the Spring container:

- `@Transactional` and transaction propagation.
- Method security with Spring Security.
- Spring-based validation and binding.
- Serialization and HTTP conversion.
- Conditional configuration.
- Spring Data repositories.
- Caching, async, and advice via proxies.
- Configuration properties binding.
- Event dispatch and infrastructure.

When behavior depends on this infrastructure, a unit test calling `new Service(...)` is not enough.

Example:

```java
@Transactional
public void transfer(...) {
    // ...
}
```

Calling `new TransferService(...)` creates no Spring transactional proxy. Plain Java tests can still verify business arithmetic, yet cannot prove a real transaction opens, rolls back properly, or propagates as configured.

### 13.1. Distinguishing business logic from framework behavior

| What to verify | Typically suitable test |
|---|---|
| Total calculation formula | Unit test without Spring |
| Not saving on invalid input | Unit test with mocks/fakes |
| `@Transactional` rollback on error | Integration test with Spring/database |
| `@ConfigurationProperties` binding and validation | Spring context/configuration test |
| Controller returning JSON and status | MVC slice or HTTP test |
| Security filter blocking requests | Security/MVC integration test |
| Database unique constraint | Repository/database integration test |

The point is not "always pick the lightest test," but **pick the execution level sufficient to prove the required behavior**.

## 14. Full-context behavior tests with @SpringBootTest

You can load the context and invoke the service via dependency injection:

```java
@SpringBootTest
class CheckoutServiceIntegrationTest {

    @Autowired
    CheckoutService checkoutService;

    @Test
    void rejectsBlankSku() {
        assertThatThrownBy(
                () -> checkoutService.checkout("", 1)
        )
        .isInstanceOf(IllegalArgumentException.class);
    }
}
```

This test asserts behavior on a Spring-managed bean. It will only start if every required dependency in the context is provided.

### 14.1. Replacing dependencies with mocks inside a Spring context

In Spring Boot releases supporting Spring Framework 6.2+ (such as Boot 3.4+), `@MockitoBean` can be used:

```java
package com.example.shop.checkout;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.BDDMockito.given;

@SpringBootTest
class CheckoutServiceSpringTest {

    @Autowired
    CheckoutService checkoutService;

    @MockitoBean
    ProductCatalog catalog;

    @MockitoBean
    PurchaseRepository repository;

    @Test
    void calculatesTotalThroughSpringManagedService() {
        given(catalog.unitPrice("SKU-1"))
                .willReturn(new BigDecimal("12.50"));

        CheckoutReceipt receipt =
                checkoutService.checkout("SKU-1", 2);

        assertThat(receipt.total())
                .isEqualByComparingTo("25.00");
    }
}
```

Here Spring builds the context and injects the registered mocks into `CheckoutService`. The test checks behavior while exercising Spring wiring.

**Note:** this test does not prove real implementations of `ProductCatalog` or `PurchaseRepository` work, because they were replaced with mocks.

### 14.2. @MockBean and @MockitoBean across versions

Older Spring Boot projects may use:

```java
import org.springframework.boot.test.mock.mockito.MockBean;
```

As of Spring Boot 3.4, Boot's `@MockBean` was deprecated in favor of Spring Framework's `@MockitoBean`. APIs and packages vary by release line.

Never copy `@MockitoBean` into a project on older framework/test libraries without checking versions. Likewise, on modern projects follow the bean override mechanism supported by your actual version.

### 14.3. When is a full context too heavy?

If a test only computes `12.50 × 2`, a full context wastes bootstrap time, pulls extra dependencies, and introduces failure points unrelated to the test.

Write most behavior tests in plain Java where possible, and add integration tests where Spring wiring or infrastructure is genuinely needed.

## 15. Test slices: testing one layer without loading the whole app

Spring Boot offers test annotations designed to load only the relevant slice of the context.

Examples:

- `@WebMvcTest`: focuses on the Spring MVC layer.
- `@DataJpaTest`: focuses on JPA and persistence.
- `@JsonTest`: focuses on JSON serialization/deserialization.
- `@RestClientTest`: supports HTTP client testing use cases.

A test slice does not mean "no Spring." It uses a narrower context suited to testing one class of behavior.

### 15.1. Why use test slices?

Suppose you only want to test:

> `POST /purchases` returns HTTP 201 and the right JSON.

You do not need to start a database, scheduler, message consumer, or all application integrations just to check controller mapping and serialization.

`@WebMvcTest` tests MVC behavior with service dependencies mocked.

## 16. @WebMvcTest: testing HTTP contracts at the controller layer

Suppose the controller is:

```java
package com.example.shop.checkout;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/purchases")
public class CheckoutController {

    private final CheckoutService service;

    public CheckoutController(CheckoutService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<CheckoutReceipt> checkout(
            @RequestBody CheckoutRequest request
    ) {
        CheckoutReceipt receipt = service.checkout(
                request.sku(),
                request.quantity()
        );

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(receipt);
    }

    public record CheckoutRequest(
            String sku,
            int quantity
    ) {
    }
}
```

What needs testing:

- Route `POST /purchases`.
- JSON request body deserializes properly.
- Controller invokes the service with matching arguments.
- Response has HTTP 201.
- JSON response includes the receipt.

### 16.1. Testing with MockMvc

```java
package com.example.shop.checkout;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(CheckoutController.class)
class CheckoutControllerTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    CheckoutService service;

    @Test
    void returnsCreatedReceipt() throws Exception {
        given(service.checkout("SKU-1", 2))
                .willReturn(new CheckoutReceipt(
                        "SKU-1",
                        2,
                        new BigDecimal("25.00")
                ));

        mvc.perform(
                post("/purchases")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(
                                """
                                {"sku":"SKU-1","quantity":2}
                                """
                        )
        )
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.sku").value("SKU-1"))
        .andExpect(jsonPath("$.quantity").value(2))
        .andExpect(jsonPath("$.total").value(25.0));
    }
}
```

The example uses Java text blocks (Java 15+, standard in Boot 3+ projects). On older Spring Boot versions, `@MockBean` may be used as appropriate.

### 16.2. What does this test verify?

It verifies MVC mapping, request decoding, controller handling, and the controller's JSON response.

It **does not** verify:

- The total calculation inside `CheckoutService`, because the service is mocked.
- Repository persistence.
- Real HTTP stack over TCP.
- Database connectivity.
- External integration behavior.

This is a **controller behavior test** with a clear, narrow boundary.

### 16.3. Watch out for Spring Security

If the application uses Spring Security, `@WebMvcTest` can apply security filters. Unauthenticated requests or missing CSRF tokens may yield 401/403 instead of 201.

Do not strip security from tests merely to force status 201. Configure test authentication/authorization matching the real HTTP contract, or narrow test scope explicitly if verifying MVC mapping independently of security.

## 17. An HTTP test does not equal full business testing

You can write:

```java
mvc.perform(get("/health"))
        .andExpect(status().isOk());
```

That tells you the endpoint returns 200 in the test setup, yet verifies none of your checkout or pricing business rules.

Conversely, a pricing unit test may pass while the controller mapping is broken.

So there are at least three layers of questions:

1. **Logic:** are amounts, rules, and validations right?
2. **Web contract:** are routes, status codes, JSON, headers, and authorization right?
3. **Integration:** do real HTTP requests traverse the service, repository, and external dependencies properly?

One single test rarely needs to prove all three; the **test suite** should cover them proportional to risk.

## 18. @DataJpaTest: testing persistence behavior

Suppose we persist an order with JPA.

Entity:

```java
package com.example.shop.persistence;

import java.math.BigDecimal;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchases")
public class PurchaseEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String sku;

    private int quantity;

    private BigDecimal total;

    protected PurchaseEntity() {
    }

    public PurchaseEntity(
            String sku,
            int quantity,
            BigDecimal total
    ) {
        this.sku = sku;
        this.quantity = quantity;
        this.total = total;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public int getQuantity() {
        return quantity;
    }

    public BigDecimal getTotal() {
        return total;
    }
}
```

Spring Data repository:

```java
package com.example.shop.persistence;

import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseJpaRepository
        extends JpaRepository<PurchaseEntity, Long> {
}
```

### 18.1. Testing persistence with a test slice

```java
package com.example.shop.persistence;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
class PurchaseJpaRepositoryTest {

    @Autowired
    PurchaseJpaRepository repository;

    @Test
    void savesAndReadsPurchase() {
        PurchaseEntity saved = repository.saveAndFlush(
                new PurchaseEntity(
                        "SKU-1",
                        2,
                        new BigDecimal("25.00")
                )
        );

        PurchaseEntity loaded = repository.findById(
                saved.getId()
        ).orElseThrow();

        assertThat(loaded.getSku())
                .isEqualTo("SKU-1");

        assertThat(loaded.getQuantity())
                .isEqualTo(2);

        assertThat(loaded.getTotal())
                .isEqualByComparingTo("25.00");
    }
}
```

This test executes actions and assertions on persisted data. It proves far more than just that the entity and repository beans were created.

### 18.2. Prerequisites for the example

To run this test in a real project, you need:

- Spring Data JPA starter and test dependencies.
- A suitable test database, such as H2 or a Testcontainers database.
- Properly discovered JPA entities.
- Corresponding schema generation or migration.
- Matching Spring Boot/Jakarta imports.

`@DataJpaTest` typically configures the JPA slice and per-test transaction rollback, though database replacement details depend on setup. Do not assume the production database is verified just because an H2 test passed.

### 18.3. @DataJpaTest does not prove production SQL compatibility

An H2 test may stay green while queries or migrations fail on production PostgreSQL or MySQL.

If the app relies on dialect-specific SQL, JSONB, custom indexes/constraints, or transaction isolation behavior, write integration tests against a database engine compatible with production.

## 19. Testing a real database with Testcontainers

Testcontainers runs services like PostgreSQL, Redis, or message brokers inside containers for integration testing.

The goal is testing closer to real runtime dependencies.

Conceptual flow with PostgreSQL:

```text
JUnit integration test
          │
          ▼
Spring Boot test context
          │
          ▼
DataSource configuration
          │
          ▼
Testcontainers PostgreSQL container
          │
          ▼
Real SQL/schema/transactions
```

In a modern test setup, you can pair Testcontainers with Spring Boot's `@ServiceConnection` or `@DynamicPropertySource` to pass JDBC URL, username, and password into Spring's `Environment`.

### 19.1. What extra aspects get tested?

- Database driver and runtime connectivity.
- SQL dialect behavior.
- Constraints, schemas, and migrations.
- Transaction semantics within test scope.
- Repository queries.
- Type mapping against real database column types.

### 19.2. What remains untested?

A local PostgreSQL container does not test:

- Production network policies.
- Production database credentials.
- Production quotas and load.
- Real multi-region or failover behavior.
- Full production data volumes.

Testcontainers makes integration tests far more trustworthy for compatible dependencies, without turning them into an exact replica of production.

### 19.3. Keep tests isolated

When using a test database:

- Never connect to production by mistake.
- Never use production credentials.
- Seed test data explicitly.
- Clean up data between tests via transaction rollback, cleanup hooks, or isolated schemas/containers.
- Never let test execution order change outcomes.

A test that passes alone yet fails in the full suite is a clear signal to hunt for shared state.

## 20. End-to-end HTTP tests with RANDOM_PORT

To test real HTTP, run the test server on a random port with an HTTP client.

Example:

```java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class ShopHttpTest {

    @Autowired
    TestRestTemplate rest;

    @Test
    void healthEndpointResponds() {
        ResponseEntity<String> response =
                rest.getForEntity("/actuator/health", String.class);

        assertThat(response.getStatusCode().is2xxSuccessful())
                .isTrue();
    }
}
```

This example checks an HTTP endpoint assuming `spring-boot-starter-actuator` is present and `health` is exposed in tests.

**Note:** `TestRestTemplate` is a utility available in specific Spring Boot test versions; in newer versions or when using another client, use an HTTP test client supported by your version, such as `RestTestClient` or equivalent clients. The core idea remains sending requests through a real server and asserting the response.

### 20.1. This test is still an HTTP-level smoke check

An HTTP test calling only `/actuator/health` checks basic routing, server, and health integration. It does not test business workflows.

To test checkout end-to-end, send `POST /purchases` and read back data or assert side effects per contract.

### 20.2. Watch out for transactions in random-port tests

With `RANDOM_PORT`, the test client and HTTP request handler typically run on different threads. Putting `@Transactional` on the test method **does not automatically wrap** the server request's transaction.

Therefore, do not assume database writes made by an HTTP endpoint will roll back with the test transaction. Use isolated test data, explicit cleanup, or separate test databases.

This is a major difference between rolling-back repository tests and real-server HTTP integration tests.

## 21. What kind of mock does a mock-based test rely on?

Distinguish these tools clearly:

| Tool | Purpose |
|---|---|
| Mockito `@Mock` | Creates a plain Java mock, typically for unit tests |
| Mockito `@InjectMocks` | Constructs/injects the object under unit test |
| Spring `@MockitoBean` | Replaces or adds a mock bean inside a Spring test context where supported |
| Boot's legacy `@MockBean` | Bean-mocking mechanism in older versions |
| Fake implementation | Test implementation with lightweight logic, e.g., in-memory repository |
| Real dependency | Live database/HTTP service or compatible test container |

### 21.1. @Mock does not replace beans in ApplicationContext

If you write:

```java
@Mock
ProductCatalog catalog;
```

inside a `@SpringBootTest`, Mockito creates a mock on the test class, yet Spring's application context does not automatically use it as a bean dependency.

With Spring TestContext, use the appropriate bean override mechanism, such as `@MockitoBean` on supported versions.

### 21.2. Misconfigured mocks can create false greens

Suppose a test asserts only:

```java
assertThat(checkoutService).isNotNull();
```

while `ProductCatalog` and `PurchaseRepository` are mocks; the test proves only that Spring injected mocks into the service. It proves nothing about business behavior or real integrations.

Write assertions protecting the intended rules or contracts.

### 21.3. When should you use a fake?

An in-memory fake fits well when verifying state transitions without needing a real database.

Example:

```java
public class InMemoryPurchaseRepository
        implements PurchaseRepository {

    private final List<PurchaseRecord> records =
            new ArrayList<>();

    @Override
    public void save(
            String sku,
            int quantity,
            BigDecimal total
    ) {
        records.add(
                new PurchaseRecord(sku, quantity, total)
        );
    }

    public List<PurchaseRecord> records() {
        return List.copyOf(records);
    }
}
```

This assumes `PurchaseRecord` is a test-defined record with those three fields.

Fakes can make state assertions easier to read than many `verify(...)` calls, though they still do not prove the real SQL implementation works.

## 22. Test data: prefer clear, repeatable inputs

A good behavior test supplies its own inputs and expected outputs.

Good example:

```java
BigDecimal price = new BigDecimal("12.50");
int quantity = 2;
BigDecimal expectedTotal = new BigDecimal("25.00");
```

Flaky example:

```java
BigDecimal price = catalog.getLatestPriceFromProduction();
```

If tests depend on live production data that changes over time, they fail due to environmental changes rather than code regressions.

### 22.1. Avoid depending on the system clock unnecessarily

A rule such as "coupons expire after 7 days" needs testing across boundary dates.

Instead of calling:

```java
LocalDate.now()
```

everywhere, inject `Clock`:

```java
public class CouponService {

    private final Clock clock;

    public CouponService(Clock clock) {
        this.clock = clock;
    }

    public boolean isExpired(LocalDate expiresOn) {
        return LocalDate.now(clock).isAfter(expiresOn);
    }
}
```

Unit test:

```java
Clock fixed = Clock.fixed(
        Instant.parse("2026-01-15T00:00:00Z"),
        ZoneOffset.UTC
);
```

Fixing time keeps tests deterministic.

### 22.2. Do not make test data depend on execution order

Avoid:

```text
Test A: create user 42
Test B: assume user 42 already exists from Test A
```

When running Test B alone or in parallel, it will fail.

Each test should set up its own data or use fixtures with well-defined lifecycles.

## 23. @ActiveProfiles and properties in tests

A context smoke test can depend heavily on the active profile.

Example:

```java
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class ShopApplicationSmokeTest {

    @Test
    void contextLoads() {
    }
}
```

Spring Boot loads `application-test.yml` alongside applicable config sources.

### 23.1. Using test-specific properties

```java
@SpringBootTest(properties = {
        "app.notifications.enabled=false",
        "app.catalog.timeout=1s"
})
class ShopApplicationSmokeTest {
}
```

This controls specific test values cleanly.

However, if you disable every major integration, the context smoke test may skip the very configuration paths that need checking before production.

### 23.2. Should every test use H2?

Not necessarily. H2 suits tests needing a fast embedded database, yet cannot replace all dialect and migration checks for the production database.

Choose test databases by goal:

- Unit tests: no database needed.
- Repository slices: H2 or compatible engine depending on requirements.
- SQL/dialect/transaction integration: database engine matching production.
- E2E: controlled environment closer to real deployment.

### 23.3. Never use production credentials in tests

A test suite running in CI should never have write permissions to a production database.

Use separate test credentials and environments, with guardrails preventing any property from pointing to live systems by mistake.

## 24. How can a smoke test produce a "false green"?

A context loading cleanly does not guarantee every behavior was exercised. Smoke tests can miss defects for several reasons.

### 24.1. Lazily initialized beans

If an application uses lazy initialization:

```yaml
spring:
  main:
    lazy-initialization: true
```

some beans are not instantiated when context refresh completes. A broken constructor or init callback on an unused bean will not surface in `contextLoads()`.

Accurately put, a context smoke test catches failures on beans actually created during the current bootstrap—not every bean defined in the application.

### 24.2. Conditionally excluded beans

Example:

```java
@ConditionalOnProperty(
        prefix = "app.payment",
        name = "enabled",
        havingValue = "true"
)
@Bean
PaymentGateway paymentGateway() {
    // ...
}
```

If the test profile sets `app.payment.enabled=false`, this configuration never activates.

A green context smoke test cannot verify conditional production configuration when that condition is turned off.

### 24.3. Mocks mask failures in real integrations

If a test replaces a `DataSource` or HTTP client with a mock, the context can succeed even when the real integration configuration is broken.

Mocking itself is not wrong when isolating behavior; the mistake is **over-interpreting** what that test proved.

### 24.4. Tests do not call methods needing proxies

A `@Transactional` method may suffer from self-invocation, bypassing advice while the context still starts cleanly.

To test transaction behavior, write an integration test invoking the method across its Spring proxy boundary and verifying DB state/rollback.

### 24.5. Test runtime differs from production

Differences may include:

- JDK version.
- Classpath and test dependencies.
- OS environment.
- Active profiles.
- External config.
- Startup mode.
- Database engine.
- Network policies.
- Security credentials.

Smoke tests catch defects in the test environment; they do not replace deployment validation.

## 25. A smoke test can fail while business code is valid

The reverse matters too.

Suppose `PricingService` unit tests are all green, yet `contextLoads()` fails due to a missing `EmailClient` bean.

That tells us:

- Pricing calculations are correct for the tested cases.
- Yet the application cannot bootstrap under the current test configuration.

Both signals are valuable.

### 25.1. Distinguishing startup errors from behavior errors

| Failure | Best caught by |
|---|---|
| Missing `ProductCatalog` bean | Context smoke / integration |
| Two `PaymentGateway` candidates without qualifier | Context smoke / integration |
| Wrong discount formula | Unit behavior |
| API returning wrong HTTP status | MVC / HTTP behavior |
| Missing DB constraint enforcement | DB integration |
| `@Transactional` failing to roll back | Spring / DB integration |
| Runtime classpath missing dependency in packaged artifact | Artifact / deployment smoke |
| Wrong production secret | Deployment / environment validation |

Never delete smoke tests just because unit tests are green; never skip unit tests just because smoke tests are green.

## 26. Context caching and test suite speed

Spring TestContext Framework caches `ApplicationContext` instances across test classes when configurations match.

This prevents tests sharing identical context configurations from rebooting Spring every time.

However, differences create separate context cache keys:

- Active profiles.
- Test properties.
- Mock bean overrides.
- Configuration classes.
- Web environments.
- Initializers and customizers.
- Dynamic properties and test setups.

### 26.1. Why can many @SpringBootTest classes become slow?

If every test class uses a different combination of mocks and properties, Spring builds many distinct contexts.

Example:

```text
Test A -> context profile=test, mock Catalog
Test B -> context profile=test, mock Payment
Test C -> context profile=integration, real database
```

Three different context configurations cannot share a cache entry.

### 26.2. @DirtiesContext is not always good

`@DirtiesContext` marks the context as mutated so Spring evicts it from cache.

It is genuinely needed when a test alters application context state in a way that cannot be safely reset. However, overusing `@DirtiesContext` slows down the suite and masks isolation problems.

Prefer:

- Avoiding mutations to global application state.
- Resetting database/test data properly.
- Restoring any modified global config/loggers.
- Using test doubles with clean lifecycles.

### 26.3. Balancing speed and confidence

A sensible layout:

- Many fast unit tests for business rules.
- Targeted slices for controllers and repositories.
- Selective integration tests for framework behavior.
- A few purposeful context smoke tests.
- A handful of E2E tests for critical workflows.

You do not need a full context bootstrap for every branch of every business rule.

## 27. Testing exceptions and errors is also behavior

Business behavior is not just the happy path.

For instance, checkout must reject invalid quantities:

```java
@Test
void rejectsNegativeQuantity() {
    assertThatThrownBy(
            () -> service.checkout("SKU-1", -1)
    )
    .isInstanceOf(IllegalArgumentException.class);
}
```

And there is a second requirement:

> When checkout is rejected, the repository must not persist any record.

```java
verifyNoInteractions(repository);
```

These two assertions protect two different parts of the business contract.

### 27.1. Testing HTTP error mapping

If a service throws `IllegalArgumentException`, a controller does not automatically convert it into HTTP 400 under every configuration.

You might define a handler:

```java
@RestControllerAdvice
public class CheckoutExceptionHandler {

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<Map<String, String>> badRequest(
            IllegalArgumentException ex
    ) {
        return ResponseEntity.badRequest().body(
                Map.of(
                        "code", "INVALID_PURCHASE",
                        "message", "Invalid purchase request"
                )
        );
    }
}
```

Then write an MVC test verifying:

```java
.andExpect(status().isBadRequest())
.andExpect(jsonPath("$.code").value("INVALID_PURCHASE"));
```

This is HTTP contract behavior that `contextLoads()` never verifies on its own.

### 27.2. Testing timeouts and retries

When an application retries after remote service timeouts:

- Verify retry counts follow policy.
- Do not retry non-retryable errors.
- Avoid unintended duplicate side effects.
- Preserve the right exception/cause once retries exhaust.
- Do not wait out long real timeouts in unit tests; use fakes, mocks, `Clock`, or test-specific configs.

These cases require behavior tests with assertions, not startup smoke tests.

## 28. Testing real transactions

Suppose:

```java
@Service
public class TransferService {

    @Transactional
    public void transfer(...) {
        debit(...);
        credit(...);
    }
}
```

Business requirement:

> If the credit step fails, the preceding debit must roll back.

To verify this, you need a test executing across the Spring-managed transactional boundary against a compatible database:

1. Prepare initial balances for two accounts.
2. Invoke `transfer` from outside the proxy.
3. Inject an intentional failure after the debit step.
4. Assert balances remain unchanged after rollback.
5. Assert the expected exception per contract.

### 28.1. Why aren't unit tests enough?

Plain Java unit tests verify the method calls debit then credit. They cannot prove the transaction manager opened a transaction or rolled back the database.

### 28.2. Why isn't contextLoads enough?

Spring can build `TransferService` and the transaction manager cleanly while the method is never called. Self-invocation or wrong propagation settings can still break runtime behavior.

### 28.3. Do not let the test's own transaction mask a bug

In some integration tests, the test's own default rollback can revert changes, misleading you into thinking the service's `@Transactional` rolled back properly.

Design tests so measurements reflect the **service under test's transaction**, not just test cleanup. Separate transaction boundaries or use Spring TestContext transaction utilities deliberately when needed.

## 29. Testing security is also business and contract behavior

An API can build its context cleanly while accidentally allowing ordinary users to access an admin endpoint.

Example:

```text
GET /admin/reports
```

Expected behavior:

- Unauthenticated user: rejected per security policy.
- Authenticated user lacking authority: rejected.
- Authorized user: succeeds.

These cases must be tested under a setup applying appropriate security filters and method security.

### 29.1. Context smoke tests do not check the authorization matrix

Simply creating a `SecurityFilterChain` bean does not prove every request path is protected properly.

### 29.2. Do not disable filters and conclude security works

In tests aimed at verifying security, disabling all filters renders the test meaningless.

Conversely, when testing only controller serialization, a slice test may use a dedicated security test setup. State test scope clearly and avoid over-broad conclusions.

## 30. Testing configuration properties

Suppose the app has:

```yaml
app:
  checkout:
    max-quantity: 20
    timeout: 3s
```

Record:

```java
@ConfigurationProperties(prefix = "app.checkout")
public record CheckoutProperties(
        int maxQuantity,
        Duration timeout
) {
}
```

There are at least two separate concerns:

1. Does Spring bind config into the object properly?
2. Does business code enforce `maxQuantity` and `timeout` properly?

### 30.1. Context smoke tests can catch binding failures

If Spring instantiates and binds `CheckoutProperties` with validation enabled, a smoke test catches invalid property values.

Yet if the bean is not registered or created in the test context, the test never checks that configuration.

### 30.2. Binding tests vs. behavior tests

Binding test:

```java
assertThat(properties.maxQuantity()).isEqualTo(20);
assertThat(properties.timeout()).isEqualTo(Duration.ofSeconds(3));
```

Business behavior test:

```java
assertThatThrownBy(
        () -> checkoutService.checkout("SKU-1", 21)
).isInstanceOf(IllegalArgumentException.class);
```

One test checks the bound config values; the other checks the rule enforcing that limit to reject excessive quantities.

These are two separate contracts.

## 31. Signs a test suite relies too heavily on contextLoads

Warning signs:

- The project has complex services yet only one `contextLoads()` test.
- CI stays green despite breaking changes in pricing or validation logic.
- No assertions on expected outputs.
- No tests for failure paths.
- No HTTP tests despite public APIs being core features.
- No repository tests despite SQL/transaction risks.
- Coverage measures only loaded classes, not behavior.
- Production bugs occur in scenarios easily reproduced by unit tests.

If you see these signs, do not delete the smoke test—supplement it with behavior tests prioritized by business risk.

### 31.1. Coverage alone does not prove quality

A test method calling lots of code can raise coverage without meaningful assertions.

Example:

```java
@Test
void checkoutSomething() {
    service.checkout("SKU-1", 2);
}
```

This catches unexpected exceptions, yet fails to verify totals, persistence, or side effects.

Better:

```java
CheckoutReceipt receipt =
        service.checkout("SKU-1", 2);

assertThat(receipt.total())
        .isEqualByComparingTo("25.00");

verify(repository).save(
        "SKU-1",
        2,
        new BigDecimal("25.00")
);
```

Prioritize assertion strength and key cases over raw coverage percentages alone.

## 32. Organizing tests by package and goal

An example layout:

```text
src/
├── main/
│   └── java/com/example/shop/
│       ├── ShopApplication.java
│       ├── checkout/
│       ├── pricing/
│       ├── persistence/
│       └── web/
└── test/
    └── java/com/example/shop/
        ├── ShopApplicationSmokeTest.java
        ├── pricing/
        │   └── PricingServiceTest.java
        ├── checkout/
        │   └── CheckoutServiceTest.java
        ├── web/
        │   └── CheckoutControllerTest.java
        └── persistence/
            └── PurchaseJpaRepositoryTest.java
```

Test names communicate scope:

- `ShopApplicationSmokeTest`: verifies bootstrap.
- `PricingServiceTest`: unit tests for pricing rules.
- `CheckoutServiceTest`: unit tests for checkout flow.
- `CheckoutControllerTest`: MVC contract tests.
- `PurchaseJpaRepositoryTest`: persistence integration tests.

You can split integration tests into separate source sets or tasks in large projects with heavy dependencies, without overcomplicating small projects solely for extra folders.

### 32.1. Should integration tests use the *IT suffix?

Some projects use the `IT` suffix for integration tests; others use `IntegrationTest` or separate packages.

Follow your repository's build and test conventions. What matters is that CI distinguishes fast checks from tests needing heavier integration environments.

## 33. Workflow for choosing tests for a new requirement

Suppose you receive a requirement:

> "Add a feature applying a 10% discount for orders over 1,000,000 VND."

You can proceed as follows.

### Step 1 — Define the business contract

For example:

- Total 1,000,000: no discount if the rule is strictly "over."
- Total 1,000,001: 10% discount.
- Negative total: rejected as invalid.
- Rounding: per currency policy.
- Discount is never applied twice.

### Step 2 — Write unit tests

Test each boundary and rule on a pure Java service.

### Step 3 — Check wiring if adding new beans or configs

A context smoke test catches a missing `DiscountPolicy` bean or injection conflict.

### Step 4 — Verify API contract if exposing a new endpoint

Use `@WebMvcTest` or an HTTP test to check JSON input, status code, response schema, and validation.

### Step 5 — Verify persistence if storing new fields

Use a repository integration test to confirm discount amounts and totals persist and load cleanly.

### Step 6 — Verify key collaboration

An integration test can verify service, transaction, and repository working together.

### Step 7 — Assess remaining risks

Security, concurrency, idempotency, external services, performance, and deployment are not automatically covered by the tests above.

Each test layer adds evidence rather than serving as a blanket guarantee.

## 34. Test pyramid: why favor many unit tests?

A common structure puts many fast tests at the bottom and fewer heavy tests at the top:

```text
              /\
             /  \
            / E2E\
           /______\
          /        \
         /Integration\
        /____________\
       /              \
      /   Unit tests   \
     /__________________\
```

Interpretation:

- **Unit:** fast, isolated, easy to cover many cases and boundaries.
- **Integration / slice:** verifies component collaboration or framework behavior.
- **E2E:** verifies end-to-end flows from outside through multiple layers; slower and more environment-dependent.

### 34.1. Where do context smoke tests fit?

A context smoke test is not a separate pyramid tier. It is typically treated as an integration smoke test: bootstrapping the framework/context and flagging wiring or configuration errors early.

It is valuable in CI without replacing the other layers.

### 34.2. There is no mandatory ratio

There is no universal rule forcing "70% unit, 20% integration, 10% E2E" on every app.

A computation library may rely primarily on unit tests. A SQL- and protocol-heavy app may need more integration tests. Allocate effort based on risk and maintenance cost.

## 35. Which tests should run at each CI stage?

A pipeline might be structured as:

| Stage | Common checks | Goal |
|---|---|---|
| Developer local | Unit tests, selected slices | Fast feedback |
| Pull request | Unit + slices + context smoke | Catch regressions and wiring breaks |
| Integration stage | DB/container/API integration | Verify real interactions |
| Deployment smoke | App startup/health/basic route check | Verify packaged artifact and deploy environment |
| Periodic E2E | Critical user journeys | Verify cross-system flows |

This is an example organization, not a mandatory pipeline template.

### 35.1. Deployment smoke vs. context smoke

**Context smoke in tests:**

```java
@SpringBootTest
void contextLoads() {
}
```

**Deployment smoke:**

```text
Deploy artifact
    │
    ▼
Process starts
    │
    ▼
Health/readiness endpoint OK
    │
    ▼
Execute a basic HTTP operation
```

Deployment smoke verifies the packaged artifact in a more realistic runtime environment; context smoke verifies the Spring context under test classpath/properties.

Both are useful, yet support different conclusions.

### 35.2. A health endpoint is not a business E2E test

`GET /actuator/health` returning `UP` does not prove ordering, payment, or authorization works properly.

A deployment smoke test may run a safe synthetic operation suited to the system, while avoiding real transactions with live side effects in production without careful safety design.

## 36. How to read errors when a test fails

When `contextLoads()` fails, the stack trace can be long. Look for the root cause:

```text
Failed to load ApplicationContext
...
Caused by: UnsatisfiedDependencyException
...
Caused by: NoSuchBeanDefinitionException
```

Or:

```text
BeanCreationException
ConfigurationPropertiesBindException
...
```

### 36.1. Investigating context failures

1. Read the exception cause chain, not just `Failed to load ApplicationContext`.
2. Check active profiles and properties.
3. Confirm the `@SpringBootApplication` class was discovered.
4. Check component scanning and bean definitions.
5. Check qualifiers/primaries if multiple beans share a type.
6. Check whether an external dependency is called at startup.
7. Check test mocks and bean override configurations.
8. Check test runtime dependencies and versions.

### 36.2. Investigating behavior failures

If a test reports:

```text
Expected: 25.00
Actual: 14.50
```

inspect the formula, inputs, and rounding rules. There is no reason to investigate component scanning.

If a test reports:

```text
Expected: HTTP 201
Actual: HTTP 403
```

inspect authentication, authorization, and CSRF policies in the test setup before editing business services.

If a repository test fails on a unique constraint, inspect schema, data, and transaction behavior. Classifying failures by scope leads straight to the right fix.

## 37. Common misconceptions

### 37.1. "contextLoads() passing means the API works"

No. The test sends no HTTP requests and asserts no responses. It only proves the test context loaded.

### 37.2. "Using @SpringBootTest guarantees a deep integration test"

No. `@SpringBootTest` selects bootstrapping/context; depth still depends on the test method, real vs. mocked dependencies, assertions, and web environment.

### 37.3. "An empty test method is useless"

No. Building the context is a valuable bootstrap check, especially after changing dependencies or configurations.

### 37.4. "Every service must be tested with @SpringBootTest"

No. Pure Java business logic should be tested rapidly with unit tests whenever possible.

### 37.5. "Mocking all dependencies is still a real integration test"

No. Mocks isolate behavior and wiring, yet prove nothing about real dependency implementations.

### 37.6. "@WebMvcTest tests the database"

No. The MVC slice usually omits full persistence infrastructure; databases require separate tests.

### 37.7. "Passing H2 @DataJpaTest guarantees production PostgreSQL works"

No. SQL dialects, migrations, and transaction differences often require testing against a production-compatible engine.

### 37.8. "HTTP 200 from /health proves business workflows work"

No. Health reports configured indicators, not every business rule.

### 37.9. "Calling a service method without assertions is enough"

It catches unexpected exceptions, yet fails to verify outputs or side effects. Always add concrete assertions.

### 37.10. "Unit tests with Mockito have no value"

No. Mock-based unit tests are highly effective for business rules and critical interactions. Complement them with integration tests at risky boundaries rather than abandoning unit tests.

### 37.11. "@Transactional on tests always tests service rollback"

Not necessarily. The test's transaction can mask service behavior unless transaction boundaries are set up carefully.

### 37.12. "A passing CI context smoke test guarantees production startup"

No. Production may differ in profiles, secrets, infrastructure, classpath/runtime, and deployment settings.

## 38. Pre-test thinking checklist

This is not a lesson-content QA checklist; it is a set of questions **guiding test strategy choices** for a real Spring Boot requirement:

- Am I testing bootstrap, business behavior, HTTP contracts, or integration?
- What are the exact inputs and expected outputs?
- Are there side effects that must be asserted?
- What important errors or edge cases exist?
- Does the behavior depend on Spring proxies, transactions, or serialization?
- Can I write a plain Java unit test?
- Do I need to mock an external dependency?
- If mocking, which integration behavior am I leaving untested?
- If using `@SpringBootTest`, do I genuinely need a full context?
- If using `@WebMvcTest`, are security filters scoped properly?
- If using a test database, does the SQL engine match the risks I need to test?
- Is test data independent, deterministic, and safe?
- Which kind of regression will a test failure catch?
- How many important configuration variants/profiles exist?
- Are any tests passing solely because they lack assertions?

A reliable test suite comes from answering these questions clearly, not from piling on Spring annotations.

## 39. Practice exercises

### Exercise 1 — Simple context smoke test

Create a Spring Boot application with `@SpringBootApplication` and one `@Service`. Write `@SpringBootTest` with an empty `contextLoads()`. Run it, then intentionally introduce a constructor dependency with no bean to observe the bootstrap error.

### Exercise 2 — Business bug missed by context startup

Create `PricingService` with the buggy calculation `unitPrice + quantity`. Confirm the context smoke test still passes, then write a unit test expecting `unitPrice × quantity` to catch the bug.

### Exercise 3 — Validation behavior

Add a rule rejecting quantities less than or equal to 0. Write tests for quantity = -1, 0, and 1. Assert the exception type and appropriate message.

### Exercise 4 — Mockito unit test

Create `CheckoutService` with `ProductCatalog` and `PurchaseRepository`. Mock catalog price 12.50, check out 2 items, assert total 25.00, and verify repository save.

### Exercise 5 — Never write to repository on invalid input

Use Mockito `verifyNoInteractions` to verify checking out quantity 0 calls neither catalog nor repository.

### Exercise 6 — Full-context Spring behavior test

Use `@SpringBootTest` to inject `CheckoutService`; swap integrations using `@MockitoBean` or the version-appropriate API. Test a business rule and explain which real dependencies remain untested.

### Exercise 7 — MVC slice

Create `CheckoutController` accepting JSON and returning a receipt. Write a `@WebMvcTest` with `MockMvc`, verifying status 201 and JSON fields.

### Exercise 8 — HTTP error contract

Create a `@RestControllerAdvice` mapping invalid quantities to HTTP 400. Write a `MockMvc` test asserting response status and error JSON.

### Exercise 9 — Repository test

Create `PurchaseEntity`, `JpaRepository`, and `@DataJpaTest`. Save a purchase and read it back. Explain the difference between a JPA behavior test and a context smoke test.

### Exercise 10 — Testcontainers

Use Testcontainers with your application's database engine. Compare repository tests against H2, especially around SQL dialect-specific features or database constraints.

### Exercise 11 — RANDOM_PORT HTTP test

Start the server with `@SpringBootTest(webEnvironment = RANDOM_PORT)`. Send a request from an HTTP client and assert the response. Explain how this differs from `MockMvc`.

### Exercise 12 — Profiles

Create `test` and `prod` profiles with a conditional bean. Run the smoke test under `test` and explain which production configuration remains untested.

### Exercise 13 — Lazy initialization

Enable lazy initialization and add a bean whose constructor throws when instantiated. Observe how `contextLoads` can avoid triggering the constructor; then write a test invoking the bean to check real behavior.

### Exercise 14 — Transaction rollback

Create a `@Transactional` service performing two writes. Cause a failure on the second step; write an integration test proving rollback at the service boundary without letting the test's own transaction cleanup hide the result.

### Exercise 15 — Testing authorization

Create an endpoint restricted to the admin role. Write tests for anonymous users, regular users, and admins. Do not disable security filters in tests meant to verify security.

### Exercise 16 — Testing with a fixed Clock

Write coupon expiration logic using `Clock`. Write deterministic tests before, on, and after the expiration date.

### Exercise 17 — Classifying test failures

Introduce three bugs: a missing bean, a wrong calculation, and an unexpected HTTP 403. Identify which test catches each error and how to investigate appropriately.

### Exercise 18 — Designing a test suite

For an app with pricing, checkout, a PostgreSQL repository, and a REST API, design a minimal suite: unit tests, MVC slice, repository integration, context smoke, and one critical end-to-end flow. Explain the goal of each test.

### Exercise 19 — Measuring context cache impact

Create multiple `@SpringBootTest` classes sharing profiles/properties, then change one configuration. Observe bootstrap times and context caching effects. Avoid overusing `@DirtiesContext`.

### Exercise 20 — Deployment smoke vs. context smoke

Describe how to verify a deployed artifact using readiness/health plus a safe synthetic API operation. Compare the evidence from that check against `contextLoads()` running on the test classpath.

## 40. Official references

- [Spring Boot Reference — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `@SpringBootTest`, web environments, mock web testing, and integration tests.
- [Spring Boot Reference — Test Auto-configuration Annotations](https://docs.spring.io/spring-boot/reference/test-auto-configuration.html): test slices such as `@WebMvcTest` and `@DataJpaTest` by version.
- [Spring Framework Reference — TestContext Framework](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework.html): Spring TestContext, context caching, and lifecycle.
- [Spring Framework Reference — Bean Overrides in Tests](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/bean-overriding.html): `@MockitoBean` and test bean overrides in supported versions.
- [Spring Framework Reference — MockMvc](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html): testing the controller layer without starting a real HTTP server.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): `@Test`, assertions, and test execution mechanisms.
- [Mockito Documentation](https://site.mockito.org/): mocks, stubbing, and interaction verification.
- [Testcontainers Documentation](https://java.testcontainers.org/): integration tests with dependencies running in containers.
- [Spring Boot Reference — Testcontainers Support](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): integrating Testcontainers into Spring Boot tests.

**Core takeaway:** `contextLoads()` is a **smoke test for the Spring ApplicationContext**, catching configuration or dependency wiring errors during bootstrap. It does not invoke business methods, assert outputs, or prove HTTP/database/security behavior is right. To protect business logic, write tests with concrete inputs and assertions; to protect integrations, write tests exercising the exact framework boundaries and dependencies required. Keep smoke tests as a helpful baseline signal, while building real confidence in your application through a multi-layered suite of behavior tests with clear scopes and expectations.
