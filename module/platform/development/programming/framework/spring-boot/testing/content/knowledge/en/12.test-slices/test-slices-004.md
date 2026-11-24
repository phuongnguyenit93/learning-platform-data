# Test Slices: Adding Required Dependencies with Imports or Replacement Beans

## 1. Why Does a Test Slice Lack a Bean?

A `@SpringBootTest` test may start successfully, yet when switched to `@WebMvcTest(ProductController.class)` you see an error:

~~~text
UnsatisfiedDependencyException: Error creating bean 'productController'
No qualifying bean of type 'example.slices.ProductCatalog' available
~~~

This is usually an **intentional consequence** of the test slice, not proof that the production application is broken. Spring Boot places into the `ApplicationContext` only the part of the application needed for the layer under test. `@WebMvcTest` configures Spring MVC components and allowed web components, without scanning every regular `@Service`, `@Repository`, or `@Component`.

Suppose the controller takes three dependencies:

~~~text
ProductController            ← SUT: keep running for real
  ├─ ProductCatalog          ← @Service: outside web slice
  ├─ PriceFormatter          ← regular @Component: outside web slice
  └─ Clock                   ← @Bean in @Configuration: outside web slice
~~~

To keep the MVC test lean, we will **keep the controller real**, then deliberately choose:

- Import the real `PriceFormatter` because the test needs to verify price formatting.
- Supply `Clock.fixed(...)` via `@TestConfiguration + @Bean`, avoiding dependence on the current date.
- Replace `ProductCatalog` with `@MockitoBean` to stub/verify invocations, or with a fake `@Bean` to run simple rules.

This lesson explains how to choose, the corresponding annotations, common pitfalls, and runnable **Java 17+/Spring Boot 3.5.x/JUnit Jupiter** examples in a Gradle project configured for Spring Boot.

## 2. Design Principle: Add Only What Is Truly Needed

A **test slice** is a Spring Boot test context created by a specialized annotation such as `@WebMvcTest`, `@WebFluxTest`, `@DataJpaTest`, `@JdbcTest`, or `@JsonTest`. Unlike a full-context `@SpringBootTest`, each slice filters beans and loads only a relevant set of auto-configurations.

| Test slice | Primary scope | Commonly excluded dependencies |
| --- | --- | --- |
| `@WebMvcTest` | MVC controllers, advice, permitted filters/converters, `MockMvc` | Business `@Service`, repositories, many regular `@Component` beans |
| `@WebFluxTest` | Reactive controllers, web codecs, `WebTestClient` | Services/repositories outside the reactive web slice |
| `@JsonTest` | JSON serialization/deserialization | MVC controllers, business services, DB |
| `@DataJpaTest` | JPA mapping, entity manager, repositories, and transaction support | MVC controllers, most services |
| `@JdbcTest` | JDBC, datasource, and slice transaction support | HTTP/MVC, business services |
| `@DataMongoTest` | MongoDB components and repositories | Full MVC/business bean graph |

The exact set of beans depends on **classpath, Spring Boot version, profiles, conditions, and customizations**. Do not assume every repository or converter is present merely because it sits in the same Java module.

The first question when a dependency is missing is not "which class should I import to clear the exception?", but rather:

> **Is this dependency's behavior something the test must prove, or is it just an input/external system?**

| What you want to verify | Reasonable choice |
| --- | --- |
| Real mapper/formatter logic contributing to the HTTP response | `@Import(RealFormatter.class)` |
| Fixed time value or configuration flag | `@TestConfiguration + @Bean` |
| Controller calls the service with the right arguments and returns status/JSON | `@MockitoBean` for the service |
| Simple stateful behavior chain without needing a real DB | Fake implementation provided via `@Bean` |
| `@ConfigurationProperties` binds properly | `@EnableConfigurationProperties(Settings.class)` |
| Add a Spring Boot auto-configuration | `@ImportAutoConfiguration` |
| Transactions, SQL queries, entity mapping, real schema | JPA/JDBC slice with a real database |
| Controller + service + repository + advice interacting application-wide | `@SpringBootTest` with suitable test resources |

Mocking the controller itself and then asserting the value returned by the mock **is not a controller test**. Keep the SUT running for real, and substitute collaborators only at the boundary.

## 3. @Import: Bringing a Real Implementation into a Slice

The `org.springframework.context.annotation.Import` annotation lets you explicitly register a component or configuration class that the slice does not scan automatically.

~~~java
@WebMvcTest(ProductController.class)
@Import(PriceFormatter.class)
class ProductControllerTest {
    // Real PriceFormatter is present in the test context.
}
~~~

The snippet above is an **illustrative pattern, missing dependencies** if the controller also needs `Catalog` or `Clock`; see section 8 for the complete example.

Use `@Import` when an implementation:

1. Contains real logic that needs verification alongside the SUT, such as a formatter, mapper, or MVC converter.
2. Needs no network/DB, or has small, controlled dependencies.
3. Does not spawn large numbers of out-of-scope beans in the slice.
4. Has observable effects checked by assertions, rather than just silencing a context error.

Do not use `@Import(EntireApplication.class)` or a broad `@ComponentScan("...")` just to load a single formatter. Doing so can defeat **slice filters**, causing schedulers, migrations, datasources, or real clients to start.

Spring Boot notes: an explicit `@ComponentScan` on the primary `@SpringBootApplication` can cause default slice exclude filters not to apply as expected. Prefer `@Import`ing specific dependencies while keeping the root configuration minimal.

### Import the Real Collaborator or Mock It?

Suppose the controller needs `PriceFormatter.format(1250)` to return `"12.50 USD"`. If you stub the formatter to return that string, the test only proves the controller passes through the stubbed value; **it will not catch a production formatting bug**. Importing the real formatter allows JSON assertions to catch production formatting bugs. Conversely, if a service calls an external database, importing the entire real service can pull in a large graph without adding MVC evidence. In that case, mock the service port.

## 4. @TestConfiguration + @Bean: Test-Only Fakes or Fixtures

Spring Boot provides `org.springframework.boot.test.context.TestConfiguration`. A top-level test configuration in `src/test/java` is normally skipped by production component scanning and can be imported explicitly when needed.

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

@TestConfiguration(proxyBeanMethods = false)
class FixedClockTestConfiguration {
    @Bean
    Clock clock() {
        return Clock.fixed(
                Instant.parse("2026-01-02T00:00:00Z"),
                ZoneOffset.UTC);
    }
}
~~~

This is an **illustrative class with imports**; when used in a package, place it in `FixedClockTestConfiguration.java` under test sources. `Clock` executes real JDK logic with a deterministic value, so Mockito is unnecessary.

A fake can also be supplied via `@Bean`:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class FakeCatalogTestConfiguration {
    @Bean
    ProductCatalog productCatalog() {
        return sku -> "BOOK".equals(sku)
                ? Optional.of(new Product("BOOK", 1250L))
                : Optional.empty();
    }
}
~~~

This snippet needs the project's `ProductCatalog`, `Product`, and `import java.util.Optional;`; the full version is in section 8.

**Distinction from nested `@Configuration`:** a nested static `@TestConfiguration` is picked up by Boot to supplement test configuration, whereas a regular nested `@Configuration` can replace the primary configuration in some TestContext loading paths. For readability, use **top-level test configurations + `@Import`** as practiced in this lesson.

**Avoiding duplicate beans:** If the slice already has a `Clock` from elsewhere, adding an unqualified `@Bean Clock` can trigger `NoUniqueBeanDefinitionException`. Check where existing beans come from and use qualifiers or targeted bean overrides. Do not enable `spring.main.allow-bean-definition-overriding=true` just to mask an unclear setup.

## 5. @MockitoBean: Mocks Actually Injected by Spring into Beans

Spring Framework 6.2 supports `org.springframework.test.context.bean.override.mockito.MockitoBean`:

~~~java
@MockitoBean
ProductCatalog catalog;
~~~

`@MockitoBean` registers a **mock in the ApplicationContext** managed by Spring TestContext. Consequently, the controller instantiated by Spring receives that mock.

By contrast:

~~~java
@Mock
ProductCatalog catalog;
~~~

Plain Mockito `@Mock` only creates a mock object on the test field when Mockito is initialized; it **does not automatically replace a bean** in the Spring context. In Spring-free unit tests, `@Mock` with manual constructor injection works well. In a slice where a controller's dependency must be overridden, choose `@MockitoBean`.

### Replace-or-Create and enforceOverride

By default, `@MockitoBean` applies the **REPLACE_OR_CREATE** strategy:

- If a matching bean already exists in the context: replace that bean with the mock.
- If no matching bean exists: create a new mock bean for the test.

The second case is crucial in `@WebMvcTest`: the production `@Service ProductCatalogImpl` is filtered out, so the mock is normally **created additionally**, with no production service present to replace.

If you need to enforce that you are "replacing an existing production bean," you can use:

~~~java
@MockitoBean(enforceOverride = true)
PaymentGateway gateway;
~~~

However, in a web slice where no `PaymentGateway` bean exists yet, this attribute will cause context startup to **fail** instead of creating a new mock. Enable it only when the test contract requires the original bean to exist.

### Spring Versions

| Stack | Commonly used annotation |
| --- | --- |
| Spring Boot 3.3 and earlier | Spring Boot's `@MockBean` / `@SpyBean` |
| Spring Boot 3.4/3.5 + Spring Framework 6.2 | Spring TestContext's `@MockitoBean` / `@MockitoSpyBean` |
| Spring Boot 4.x | `@MockitoBean`, though check test packages/modules after migration |

Boot's `@MockBean` has been deprecated since 3.4; do not mix imports across versions. `@MockitoBean` follows candidate selection rules by type, bean name, and qualifier. If multiple beans share an interface, specify **which bean** to replace instead of relying on an ambiguous field name.

**AOP risk:** replacing a bean with a mock does not preserve transaction, caching, retry, or method-security advice on the real bean. If the goal is to test `@Transactional`, `@Cacheable`, or security advice, keep that bean real and mock lower-level collaborators.

### @MockitoSpyBean and @TestBean

- `@MockitoSpyBean` wraps an existing real bean in a spy, requiring a matching target bean to exist; real methods run by default. When stubbing a spy, `doReturn(...).when(spy)...` is usually safer than `when(spy.method())` because the latter invokes the real method during setup.
- Spring Framework's `@TestBean` creates a bean override from a **static factory method**, useful when you want a fake instance without Mockito. The factory takes no parameters and returns a compatible type.

~~~java
// Illustrates @TestBean inside a test class; not standalone:
@TestBean(methodName = "catalogForTest")
ProductCatalog catalog;

static ProductCatalog catalogForTest() {
    return sku -> Optional.empty();
}
~~~

`@TestBean` is imported from `org.springframework.test.context.bean.override.convention.TestBean`. When adding multiple fixtures to a web slice, `@TestConfiguration + @Import` is often clearer.

## 6. What Will the Practical Example Test?

The mini application has one endpoint:

~~~text
GET /api/products/BOOK/summary
          |
          v
   ProductController        ← runs for real in @WebMvcTest
       |      |       |
       v      v       v
    Catalog Formatter     Clock
     mock     real         fixed
      or
     fake
~~~

When the catalog provides `BOOK` priced at 1,250 cents, the API must return JSON containing:

~~~json
{
  "sku": "BOOK",
  "price": "12.50 USD",
  "asOf": "2026-01-02"
}
~~~

There are two test styles:

- **Test A:** `@MockitoBean ProductCatalog`, `@Import(PriceFormatter.class)`, and fixed `Clock`; verifies status, JSON, and `verify(catalog)`.
- **Test B:** supplies a fake `ProductCatalog` via `@TestConfiguration + @Bean`, still importing the formatter and `Clock`; uses no mocks for the catalog.

Neither uses PostgreSQL, a TCP HTTP server, or Docker. They test **MVC mapping, JSON, and the real formatter**; they do **not** test how the production catalog queries a database.

## 7. Complete Production Code (Java 17+)

All files in the example belong to package `example.slices`. In a Gradle Spring Boot project, place the following files in `src/main/java/example/slices/`.

### SliceDemoApplication.java

~~~java
package example.slices;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SliceDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SliceDemoApplication.class, args);
    }
}
~~~

This is the root configuration. `@WebMvcTest` is placed in the same package hierarchy so Spring Boot locates `@SpringBootApplication`.

### Product.java

~~~java
package example.slices;

public record Product(String sku, long priceCents) {
}
~~~

### ProductSummary.java

~~~java
package example.slices;

public record ProductSummary(String sku, String price, String asOf) {
}
~~~

Records are real data objects and need no Mockito mocks. Jackson in the Spring Boot web starter serializes them to JSON.

### ProductCatalog.java

~~~java
package example.slices;

import java.util.Optional;

public interface ProductCatalog {
    Optional<Product> findBySku(String sku);
}
~~~

This is the collaborator boundary; tests supply either a mock or a fake.

### InMemoryProductCatalog.java

~~~java
package example.slices;

import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class InMemoryProductCatalog implements ProductCatalog {
    @Override
    public Optional<Product> findBySku(String sku) {
        if ("BOOK".equals(sku)) {
            return Optional.of(new Product("BOOK", 1_250L));
        }
        return Optional.empty();
    }
}
~~~

In a normal production application, this `@Service` is component-scanned. However, `@WebMvcTest(ProductController.class)` **does not scan regular services**, so the test will not automatically pick up a bean of this class.

### PriceFormatter.java

~~~java
package example.slices;

import java.math.BigDecimal;
import org.springframework.stereotype.Component;

@Component
public class PriceFormatter {
    public String format(long cents) {
        return BigDecimal.valueOf(cents, 2).toPlainString()
                + " USD";
    }
}
~~~

For `1_250L`, `BigDecimal.valueOf(cents, 2)` represents `12.50` accurately, independent of locale or floating-point arithmetic. We will import the real formatter with `@Import`.

### ApplicationClockConfiguration.java

~~~java
package example.slices;

import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ApplicationClockConfiguration {
    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
~~~

When the app runs normally, the controller receives the real `Clock`. In the MVC slice, this regular production configuration is not included automatically; tests import a separate fixed `Clock`. Avoid placing `@Bean Clock` directly on root `SliceDemoApplication` so bean methods on the primary configuration do not participate in the slice.

### ProductController.java

~~~java
package example.slices;

import java.time.Clock;
import java.time.LocalDate;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProductController {
    private final ProductCatalog catalog;
    private final PriceFormatter formatter;
    private final Clock clock;

    public ProductController(
            ProductCatalog catalog,
            PriceFormatter formatter,
            Clock clock) {
        this.catalog = catalog;
        this.formatter = formatter;
        this.clock = clock;
    }

    @GetMapping("/api/products/{sku}/summary")
    public ResponseEntity<ProductSummary> summary(@PathVariable String sku) {
        return catalog.findBySku(sku)
                .map(product -> ResponseEntity.ok(
                        new ProductSummary(
                                product.sku(),
                                formatter.format(product.priceCents()),
                                LocalDate.now(clock).toString())))
                .orElseGet(() -> ResponseEntity.notFound().build());
    }
}
~~~

The controller keeps all real request handling: reading the path variable, calling the catalog, building the response record, and choosing 200 or 404. Taking `Clock` via the constructor makes date logic testable with a fixed value instead of relying on the CI machine's `LocalDate.now()`.

## 8. Complete Test Code: One Mock Slice, One Fake Slice

Place the following files in `src/test/java/example/slices/`, in the same package as the application.

### FixedClockTestConfiguration.java

~~~java
package example.slices;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

@TestConfiguration(proxyBeanMethods = false)
class FixedClockTestConfiguration {
    @Bean
    Clock clock() {
        return Clock.fixed(
                Instant.parse("2026-01-02T00:00:00Z"),
                ZoneOffset.UTC);
    }
}
~~~

A top-level test configuration is not automatically scanned by the production application; only tests that import it receive the fixed `Clock`.

### FakeCatalogTestConfiguration.java

~~~java
package example.slices;

import java.util.Optional;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

@TestConfiguration(proxyBeanMethods = false)
class FakeCatalogTestConfiguration {
    @Bean
    ProductCatalog productCatalog() {
        return sku -> "BOOK".equals(sku)
                ? Optional.of(new Product("BOOK", 1_250L))
                : Optional.empty();
    }
}
~~~

The fake implements the interface's real contract; it is not a Mockito mock and does not automatically verify invocations. Do not place it in production sources.

### ProductControllerMockitoSliceTest.java

~~~java
package example.slices;

import java.time.Clock;
import java.time.LocalDate;
import java.util.Optional;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ProductController.class)
@Import({
        PriceFormatter.class,
        FixedClockTestConfiguration.class
})
@DisplayName("MVC slice: import real formatter, mock catalog")
class ProductControllerMockitoSliceTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    PriceFormatter formatter;

    @Autowired
    Clock clock;

    @MockitoBean
    ProductCatalog catalog;

    @Test
    @DisplayName("GET summary returns 200 and formats real price")
    void returnsSummary() throws Exception {
        when(catalog.findBySku("BOOK"))
                .thenReturn(Optional.of(new Product("BOOK", 1_250L)));

        mvc.perform(get("/api/products/BOOK/summary"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.sku").value("BOOK"))
                .andExpect(jsonPath("$.price").value("12.50 USD"))
                .andExpect(jsonPath("$.asOf").value("2026-01-02"));

        verify(catalog).findBySku("BOOK");
    }

    @Test
    @DisplayName("Missing SKU returns 404")
    void returns404() throws Exception {
        when(catalog.findBySku("MISSING"))
                .thenReturn(Optional.empty());

        mvc.perform(get("/api/products/MISSING/summary"))
                .andExpect(status().isNotFound());

        verify(catalog).findBySku("MISSING");
    }

    @Test
    @DisplayName("Formatter and Clock are actually imported beans")
    void importedBeansHaveDeterministicBehavior() {
        assertNotNull(formatter);
        assertEquals("12.50 USD", formatter.format(1_250L));
        assertEquals("2026-01-02", LocalDate.now(clock).toString());
    }
}
~~~

These are **three independent test methods**. `@WebMvcTest` auto-configures `MockMvc` without **opening a TCP server**. `@MockitoBean` supplies the mock to the Spring context so the controller is not missing `ProductCatalog`. `@Import` registers the production formatter and test `Clock` so every collaborator is resolved without a database.

**Why not use `enforceOverride = true` here?** The real catalog service is filtered out by the slice, so the mock must be *created*. Using enforce override would require an existing bean, contrary to the test's goal.

### ProductControllerFakeSliceTest.java

~~~java
package example.slices;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ProductController.class)
@Import({
        PriceFormatter.class,
        FixedClockTestConfiguration.class,
        FakeCatalogTestConfiguration.class
})
@DisplayName("MVC slice: fake catalog supplied via @Bean")
class ProductControllerFakeSliceTest {

    @Autowired
    MockMvc mvc;

    @Test
    @DisplayName("Fake catalog provides BOOK for response")
    void returnsBook() throws Exception {
        mvc.perform(get("/api/products/BOOK/summary"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.sku").value("BOOK"))
                .andExpect(jsonPath("$.price").value("12.50 USD"))
                .andExpect(jsonPath("$.asOf").value("2026-01-02"));
    }

    @Test
    @DisplayName("Fake missing SKU returns 404")
    void missingSkuReturns404() throws Exception {
        mvc.perform(get("/api/products/MISSING/summary"))
                .andExpect(status().isNotFound());
    }
}
~~~

These are **two test methods** without Mockito. The catalog is a real bean returned from a test-only `@Bean`. The same controller and formatter are tested as in Test A, though the evidence **does not include verifying catalog call counts**. When interaction verification is needed, mocks are easier; when a fake with small state/logic is needed, a fake bean is often clearer.

### Two Test Classes Create Different Contexts

Test A uses `@MockitoBean ProductCatalog`; Test B uses `@Import(FakeCatalogTestConfiguration.class)`. Spring TestContext caches contexts by configuration, imports, customizers, test bean overrides, profiles, and properties. These two classes do not have to share the same cache entry. Avoid creating endless distinct configurations just because each test prefers different field names.

### Gradle Run Command

In a Spring Boot 3.5.x project that already has the plugin/dependency management and Java 17 toolchain, the dependencies section in `build.gradle` is:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

This is a **configuration snippet**, not a complete `build.gradle` file. In a plain Java project without the Spring Boot plugin, declare full versions/plugins according to your Gradle build.

Run both classes:

~~~bash
./gradlew test --tests example.slices.ProductControllerMockitoSliceTest --tests example.slices.ProductControllerFakeSliceTest
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests example.slices.ProductControllerMockitoSliceTest --tests example.slices.ProductControllerFakeSliceTest
~~~

**Expectation:** a total of **5 JUnit Jupiter methods PASS** (3 mock-slice, 2 fake-slice) in a properly set up project. There is no stdout printed by the tests themselves; Gradle/IDE displays the test report and `BUILD SUCCESSFUL`. No PostgreSQL, Docker, external network, or real HTTP server is required.

**Scope limit:** the tests only verify Controller + MVC + Formatter + substitute dependency. They do not prove that production `InMemoryProductCatalog` is scanned properly when running the full application, nor do they test databases or production security.

## 9. @EnableConfigurationProperties: When a Configuration Bean Is Missing

`@WebMvcTest` does not scan `@ConfigurationProperties` classes by default like regular components. If a controller depends on an object bound from properties, you can use:

~~~java
@WebMvcTest(CheckoutController.class)
@EnableConfigurationProperties(CheckoutSettings.class)
class CheckoutControllerTest {
    // Spring Boot binds CheckoutSettings from Environment.
}
~~~

This is an **illustrative pattern** with undeclared application types `CheckoutController` and `CheckoutSettings`, not a standalone test. `@EnableConfigurationProperties` is appropriate when you want to verify **real property binding** of a config type into the controller. When you only need a fixed test object without testing the binder, provide it via `@TestConfiguration + @Bean`.

Do not pull all production configuration properties into a web slice. Add only the exact class needed; avoid property binding that inadvertently triggers infrastructure.

## 10. @ImportAutoConfiguration: How Does It Differ from @Import?

Spring Boot applies auto-configuration through dedicated imports and conditions. When you need to add an auto-configuration to a slice, use `@ImportAutoConfiguration` rather than arbitrarily calling `@Import(SomeAutoConfiguration.class)`.

Illustrative example:

~~~java
@JdbcTest
@ImportAutoConfiguration(IntegrationAutoConfiguration.class)
class IntegrationJdbcTest {
    // Beans still depend on auto-configuration conditions.
}
~~~

This is an **annotation pattern** requiring appropriate Boot dependencies/imports and classes, not a runnable test. The reason: auto-configurations rely on `@ConditionalOnClass`, `@ConditionalOnMissingBean`, property checks, and Boot's specific import ordering.

| Want to add | Tool |
| --- | --- |
| Real business/formatter component | `@Import(RealClass.class)` |
| A few `@Bean` fixtures | `@TestConfiguration` then `@Import` |
| Mock inside Spring context | `@MockitoBean` |
| Fake override via static factory | `@TestBean` |
| Properties bean | `@EnableConfigurationProperties` |
| Auto-configuration via Boot's mechanism | `@ImportAutoConfiguration` |

Spring Boot **does not support combining multiple `@...Test` slice annotations on one class to stack slices together**. If a test needs multiple layers, choose one slice and add the exact `@AutoConfigure...` needed, or use `@SpringBootTest` when the goal exceeds a slice's scope.

## 11. @DataJpaTest and @JdbcTest: Same Principle, Different Evidence

In `@DataJpaTest`, what is retained is JPA entities, repositories, and transaction/data auto-configuration. Business services are not necessarily present. If you want to test `ProductRepository`, you should normally inject the **real repository** instead of importing an unrelated service.

With `@JdbcTest`, a small DAO/adapter can be imported because it is the very object under test:

~~~java
@JdbcTest
@Import(OrderJdbcAdapter.class)
class OrderJdbcAdapterTest {
    @Autowired OrderJdbcAdapter adapter;
    // Tests SQL against the configured test DataSource.
}
~~~

This snippet is **illustrative** and not standalone because it requires `OrderJdbcAdapter`, DB/schema/migrations, or application SQL fixtures. If the adapter needs a small clock or converter, import the real one or provide a test-only `@Bean`. However, if the goal is SQL correctness, **do not use a fake repository** and claim mapping/JPA transactions work.

Data slices may use an embedded DB depending on configuration, so know whether the test actually connects to H2 or PostgreSQL. When production dialect/schema is required, use PostgreSQL Testcontainers and configure the datasource properly; you may need `@AutoConfigureTestDatabase(replace = NONE)` and `@ServiceConnection`/`@DynamicPropertySource` depending on version.

Do not import both controllers and services orchestrating email, brokers, and HTTP clients into a JPA slice merely because a service constructor lacks dependencies. If you genuinely need a cross-layer workflow, an explicit integration test is more valuable.

## 12. Security, Advice, MVC Converters: Dependencies Carry Behavioral Meaning Too

**Spring Security:** when the security starter is on the classpath, `@WebMvcTest` can activate the filter chain. Unauthenticated requests may return 401/403. The right fix is adding `spring-security-test` and configuring `@WithMockUser`/`csrf()` per security requirements; **do not default to `@AutoConfigureMockMvc(addFilters = false)`** just to make every test PASS. Disable filters only when the test intentionally excludes security and that limitation is understood.

**`@ControllerAdvice`:** typically belongs to the web components scanned; if advice is registered through a configuration outside the slice, import the relevant advice/config and test the real status + error body.

**Jackson module/Converter:** a custom converter or module placed in a `@Configuration` class can often be excluded from the slice. Bring the exact configuration in via `@Import` when testing the JSON contract. Do not mock the serializer itself and treat that as real JSON testing.

**Validation:** for `@Valid` and real constraints to be evaluated, a validation provider must be on the classpath (e.g., `spring-boot-starter-validation` if the project uses Bean Validation). Mocking the entire validator erases evidence of the constraint annotations.

## 13. Troubleshooting Missing Beans Systematically

### Error 1: NoSuchBeanDefinitionException

From the exception, identify the **exact missing type/qualifier**. Determine whether it belongs in the slice's scope. Choose a real import if its logic matters, or supply a mock/fake if it is just a boundary. Do not widen component scanning across the whole application.

### Error 2: NoUniqueBeanDefinitionException

Usually caused by both importing a real bean and providing a fake bean of the same type, or importing a test `Clock` while the primary configuration already defines a `Clock`. Keep only one appropriate bean, or use `@Qualifier`/targeted overrides. Avoid turning on global overriding to hide an inconsistent bean graph.

### Error 3: @Mock Field Exists, Yet Controller Still Fails Injection

`@Mock` is not automatically in the Spring context. Use `@MockitoBean` or a test bean configuration. For a pure Java unit test, instantiate the controller via its constructor and pass mocks directly; skip the Spring context when it is unnecessary.

### Error 4: enforceOverride=true Prevents Context Startup

The slice may **not yet have a target bean** because the service was filtered out. `@MockitoBean`'s default `REPLACE_OR_CREATE` works when you just want to supply a missing collaborator. Only enforce when you want to assert that an existing bean is being replaced.

### Error 5: Importing Service Triggers Missing Repository/HTTP Client

That is a signal that the test's scope is drifting out of MVC. Mock the port or move to an integration test; do not expand imports endlessly just to clear exceptions.

### Error 6: MVC Test Returns 404/401/403 Even Though All Beans Exist

Look at mappings, controller scanning, profiles, security filters, CSRF, or stub arguments. Do not treat every non-200 status as an injection issue. Inspect the `MockMvc` response/exception and actual request conditions.

### Error 7: "Unable to find a @SpringBootConfiguration"

The test is not under the proper package hierarchy or the source root is unclear. Place the test in or below the application package, or specify the primary configuration explicitly as appropriate. Do not create a dummy `@SpringBootApplication` in tests and accidentally change scope.

### Error 8: Fake State Leaks Across Test Methods

Fake beans can be singletons in the context cache. If a fake holds mutable `Map`/`List` state, design explicit reset/cleanup in `@BeforeEach` or scope separate test contexts appropriately. Do not slap `@DirtiesContext` on every test just to avoid writing cleanup.

### Error 9: Mockito Override Drops AOP Advice

Spring Framework replaces the bean with the mock directly; transactions, caching, retries, and method security advice on the target bean are not preserved automatically. Do not mock the very bean carrying the behavior you want to prove.

### Error 10: Slice Tests Pass, Yet Production Wiring Fails

Slice tests prove the loaded portion with fakes/mocks, not the full app. Add `@SpringBootTest` smoke/integration tests to verify overall auto-configuration/wiring and contract tests for infrastructure.

## 14. Pre-Commit Checklist

- [ ] Identified the slice and the SUT under test, keeping the SUT running for real.
- [ ] Classified each missing dependency: real logic, fixed data, stateful fake, I/O boundary, or auto-configuration.
- [ ] Used `@Import` for small real components that need testing, without importing the entire graph.
- [ ] Used `@TestConfiguration + @Bean` for deliberate fixtures/fakes.
- [ ] Used `@MockitoBean` so the controller gets its mock **from the Spring context**, distinct from plain Mockito `@Mock`.
- [ ] Understood default `REPLACE_OR_CREATE` and enabled `enforceOverride=true` only when the original bean must exist.
- [ ] Kept test beans out of the production classpath and avoided broad scans that affect other slices.
- [ ] Used `@EnableConfigurationProperties` when real property binding needs testing.
- [ ] Used `@ImportAutoConfiguration` when deliberately adding a Boot auto-configuration class.
- [ ] Did not stack multiple `@...Test` slices or add `@SpringBootTest` to a slice just to work around a missing bean.
- [ ] MVC tests check status/body/JSON and real formatters when part of the contract.
- [ ] Security is tested with appropriate identity/roles/CSRF, not bypassed by blindly disabling filters.
- [ ] Stateful fakes are cleaned up; tests do not depend on execution order or context cache quirks.
- [ ] Repositories/SQL, AOP, transactions, HTTP TCP, and external systems have separate integration tests where needed.
- [ ] Code uses Java 17+, and imports/annotations match the Spring Boot version in use; e.g., Boot 3.5.x does not apply unchanged to 4.x.

**Remember:** test slices exclude out-of-scope dependencies **on purpose**. `@Import` brings in real implementations that need verification; `@TestConfiguration + @Bean` supplies deterministic fakes/fixtures; `@MockitoBean` injects mocks properly into the Spring context; `@EnableConfigurationProperties` adds bound properties beans; `@ImportAutoConfiguration` adds auto-configuration. If you have to pull the entire system in just to run one controller test, re-evaluate your goal and pick the right test level.

### Official References

- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): test slices, `@WebMvcTest`, `@Import`, and `@MockitoBean`.
- [Spring Boot 3.5 — Test Slice Auto-configuration](https://docs.spring.io/spring-boot/3.5/appendix/test-auto-configuration/slices.html): auto-configurations loaded for each slice type.
- [Spring Framework 6.2 — MockitoBean / MockitoSpyBean](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html): replace-or-create, enforceOverride, and spies.
- [Spring Framework — Bean Overriding in Tests](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/bean-overriding.html): how beans are replaced and effects on AOP.
- [Spring Framework — TestBean](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-testbean.html): test beans from static factory methods.
- [Spring Boot 4 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): comparing packages/modules when upgrading Spring Boot.
