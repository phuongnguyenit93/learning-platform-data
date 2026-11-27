# Auto-Configuration Scope of @DataElasticsearchTest

`@DataElasticsearchTest` is a Spring Boot test slice for Spring Data Elasticsearch. This annotation creates an `ApplicationContext` focused on Elasticsearch data access: configuring the appropriate client/template, converters, repositories, and entities annotated with `@Document`. It helps test repositories and mappings without starting the entire application.

The key is to understand **the scope of auto-configured beans**. `@DataElasticsearchTest` is not a stripped-down version of `@SpringBootTest` that merely omits the web server. It uses test slicing to restrict auto-configuration and component scanning. Regular `@Component` beans, services, controllers, and `@ConfigurationProperties` are not automatically brought into the context just because they reside in an application package. When a test needs a bean outside the slice, import or enable that specific configuration intentionally.

The annotation also does not automatically start an embedded Elasticsearch server. The test needs to connect to a reachable Elasticsearch instance, such as a container used for integration tests or a dedicated test service. Connection settings are read from the Spring Boot Environment just like other Elasticsearch configurations.

## 1. What Is a Test Slice?

A Spring Boot application typically has many types of beans:

- Web layer: controllers, filters, handlers, web configuration.
- Application layer: services orchestrating use cases.
- Persistence layer: Spring Data repositories, templates/operations, converters.
- Integration: HTTP clients, message producers, event handlers.
- Configuration: `@Configuration`, `@ConfigurationProperties`, and shared beans.

When testing a repository, most of those beans are unnecessary. Starting the entire context slows down tests, increases the number of dependencies to prepare, and allows errors in an unrelated component to fail repository tests.

A test slice creates a smaller context, enabling only the auto-configuration group and components needed for a specific area. `@DataElasticsearchTest` is the slice for Elasticsearch:

```java
import org.springframework.boot.test.autoconfigure.data.elasticsearch.DataElasticsearchTest;
import org.springframework.beans.factory.annotation.Autowired;

@DataElasticsearchTest
class ProductRepositoryTests {

    @Autowired
    ProductRepository products;

    // Tests for repository queries and Elasticsearch mapping.
}
```

In this example, Spring Boot finds Spring Data Elasticsearch repositories and `@Document` entities, then configures the Elasticsearch components required for data operations. The test does not need to initialize controllers, services, or a web server if the goal is solely to verify the repository.

### 1.1 Comparing with @SpringBootTest

| Criterion | `@DataElasticsearchTest` | `@SpringBootTest` |
|---|---|---|
| Scope | Slice focused on the Elasticsearch data layer | Can load nearly the entire application context |
| Elasticsearch repositories | Configured for testing | Configured if application auto-configuration and scanning are enabled |
| `@Document` entities | Scanned according to slice rules | Discovered according to application configuration |
| Regular services/controllers | Not scanned automatically | Usually scanned from application configuration |
| Web environment | Not the goal of the slice | Can be mocked or start a server |
| Startup time | Typically smaller | Typically larger |
| Suitable use cases | Repositories, mappings, queries, templates | Multi-layer integration or full-application testing |

Do not pick `@SpringBootTest` merely because a repository test needs to connect to real Elasticsearch. `@DataElasticsearchTest` can still use a real Elasticsearch server; the difference lies in the Spring context scope, not whether the database is real or fake.

### 1.2 A Test Slice Does Not Mock Repositories

`@DataElasticsearchTest` does not replace repositories with Mockito mocks by default. Its purpose is to configure Spring Data Elasticsearch so tests interact with Elasticsearch. If you only want to unit test a service and do not need to verify real mappings/queries, you can use Mockito in a test that does not load a Spring context.

Conversely, if you need to test query DSL, mappings, converters, analyzers, or real repository behavior, use the test slice with an appropriate Elasticsearch instance.

## 2. What @DataElasticsearchTest Auto-Configures

Conceptually, this slice enables configurations related to Spring Data Elasticsearch and limits component scanning to Elasticsearch data components.

Components typically present in the context:

- Spring Data Elasticsearch repositories discovered within the scan scope.
- Entities annotated with `@Document`.
- Elasticsearch client and connection settings provided by Spring Boot auto-configuration.
- Template/Operations and converters corresponding to the Spring Data Elasticsearch generation in use.
- Index operations and mapping metadata required for data operations.
- Related test/data auto-configurations imported by the slice.

Specific template/client class names change across Spring Data Elasticsearch generations. For example, older versions have `ElasticsearchRestTemplate`; newer versions have `ElasticsearchTemplate` based on the Elasticsearch Java API Client. When reading examples or inspecting beans, use the exact API of your project's dependencies.

Example injecting the template:

```java
@DataElasticsearchTest
class ProductTemplateTests {

    @Autowired
    ElasticsearchOperations operations;

    @Autowired
    ProductRepository products;
}
```

`ElasticsearchOperations` is an appropriate abstraction when a test needs to verify template behavior without coupling directly to an implementation class. If you need to test a template-specific API, you can inject the implementation provided by the version in use.

### 2.1 Scanned Repositories and Entities

The slice discovers Spring Data Elasticsearch repositories and `@Document`-annotated entities according to Spring Boot's scanning rules. Thus, repositories can be injected without manually declaring each bean:

```java
@Document(indexName = "products-test")
class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;
}

interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    Optional<ProductDocument> findBySku(String sku);
}
```

This is a condensed example to illustrate mapping and repository setup. In real applications, entities/repositories are usually public top-level types located within configured scan packages.

### 2.2 Does Not Scan All Components

`@DataElasticsearchTest` does not automatically bring regular `@Component` beans into the context. This includes many bean types such as:

- `@Service`.
- `@Controller` / `@RestController`.
- Custom components.
- Components containing business logic.
- Configuration classes outside the slice's auto-configuration.
- `@ConfigurationProperties` beans unless corresponding registration is enabled.

Example:

```java
@Service
class ProductPricingService {
    // Business logic.
}
```

Do not assume `ProductPricingService` will be injected just because its package lies beneath the package containing `@SpringBootApplication`. If a test needs a service, import the required service/configuration or switch to `@SpringBootTest` if the goal is multi-layer integration testing.

### 2.3 Does Not Start an Embedded Elasticsearch Automatically

Unlike some relational database slices that can automatically select an embedded database if the matching dependency is on the classpath, the Elasticsearch slice has no default embedded Elasticsearch server that starts automatically for each test. The test needs an active Elasticsearch endpoint and valid connection configuration.

Therefore, the context may initialize successfully while the first repository request fails because Elasticsearch is not running, the URI is wrong, credentials are wrong, or due to TLS or network issues. That is a connection infrastructure failure, not evidence of missing repository scanning.

## 3. Meta-Annotation Structure and Scope Implications

`@DataElasticsearchTest` is built from other Spring Boot test annotations. In Spring Boot 3.x lines, the annotation API exposes components such as:

- `@BootstrapWith`: selects the dedicated context bootstrapper for the Elasticsearch test slice.
- `@ExtendWith(SpringExtension.class)`: integrates Spring TestContext with JUnit Jupiter.
- `@OverrideAutoConfiguration(enabled = false)`: avoids enabling all auto-configurations like a full application.
- `@TypeExcludeFilters`: applies filters to restrict component scanning for the slice.
- `@AutoConfigureDataElasticsearch`: enables auto-configuration dedicated to Elasticsearch tests.
- `@ImportAutoConfiguration`: imports the selected auto-configurations for the slice.

Some Spring Boot 3.x releases also include auxiliary test configuration annotations such as `@AutoConfigureCache`. The list of meta-annotations and packages can change between major versions; do not blindly copy imports or internal annotations from a different release.

Practical implication: the slice is not just a pre-built set of beans. It also controls auto-configuration and which component types are allowed into the `ApplicationContext`.

### 3.1 Restricted Auto-Configuration

`@OverrideAutoConfiguration(enabled = false)` prevents enabling all standard auto-configurations in the manner of a full application context. The auto-configurations needed for the slice are imported selectively.

This explains why a bean that exists automatically when running the real application might be absent in `@DataElasticsearchTest`. If that bean does not belong to the Elasticsearch slice's auto-configuration, add explicit configuration or use a more suitable test type.

### 3.2 Type Exclude Filters

Type exclude filters are the mechanism that ensures component scanning respects slice boundaries. Spring Boot uses filters to exclude non-slice component types even when they live in a scanned package.

This is why a service or controller in the same package as a repository does not automatically appear in the context. A package being in scan scope does not mean every stereotype bean is included.

### 3.3 Do Not Disable Slice Filters Arbitrarily

If the context is missing a bean, do not immediately enable full component scanning or switch to `@SpringBootTest`. First identify which category the bean belongs to:

- Entity/repository: check package and annotations.
- Configuration properties: use `@EnableConfigurationProperties`.
- Test-specific bean: use `@TestConfiguration`.
- Component bean needed in the test: use `@Import` or an include filter.
- Additional auto-configuration: use `@ImportAutoConfiguration`.
- Multiple application layers needing to run together: consider `@SpringBootTest`.

Choosing the addition mechanism based on the bean type keeps the test context small and easy to understand.

## 4. Component Scan Scope and Primary Configuration

Spring Boot typically searches for the primary configuration from the test package upward until it finds a `@SpringBootApplication` or `@SpringBootConfiguration` class. This primary configuration provides the root metadata to build the context.

However, if the application class declares a custom `@ComponentScan`, default filters used for test slicing may be bypassed. In that case, the slice may unexpectedly scan additional services, controllers, or configurations that should have been excluded.

Example configuration prone to surprises:

```java
@SpringBootApplication
@ComponentScan("com.example")
public class Application {
}
```

A direct `@ComponentScan` can override the default scan configuration Spring Boot relies on to support slices. When a `@DataElasticsearchTest` sees too many beans, check component scanning on the primary configuration before adding exclude filters to individual tests.

### 4.1 Separating Custom Component Scans

If the application needs to scan a special package, consider separating that configuration from the primary `@SpringBootApplication`:

```java
@SpringBootApplication
public class Application {
}

@Configuration
@ComponentScan("com.example.integration")
class IntegrationComponentsConfiguration {
}
```

Only import `IntegrationComponentsConfiguration` in contexts that need it. This lets test slices keep default filters and avoid pulling out-of-scope components into every test.

### 4.2 Using a Dedicated @SpringBootConfiguration When Needed

If the application's primary configuration has a special scan structure and cannot be changed, you can provide an appropriate test `@SpringBootConfiguration` or specify the configuration source for the test. This gives control over the configuration source, though you must ensure the test configuration class does not accidentally turn the slice into a full application scan.

## 5. Adding Required Beans with @Import

If a test needs a specific component outside the slice, you can import that class:

```java
@DataElasticsearchTest
@Import(ProductProjectionMapper.class)
class ProductRepositoryTests {

    @Autowired
    ProductRepository products;

    @Autowired
    ProductProjectionMapper mapper;
}
```

`@Import` registers the specified class into the context. It is useful when the test needs a mapper, converter adapter, or small component whose dependencies are already in the slice.

Do not import an entire package or a configuration that pulls in unrelated services and clients. Each import should represent a dependency the test genuinely needs.

### 5.1 Importing Multiple Beans via Test Configuration

For multiple beans used only in tests, use a nested `@TestConfiguration`:

```java
@DataElasticsearchTest
class ProductRepositoryTests {

    @Autowired
    ProductRepository products;

    @TestConfiguration(proxyBeanMethods = false)
    static class TestBeans {

        @Bean
        ProductFixtureFactory productFixtureFactory() {
            return new ProductFixtureFactory();
        }
    }
}
```

`@TestConfiguration` supplements the primary configuration. A nested class does not replace the application configuration used by the test slice. `proxyBeanMethods = false` is suitable when bean methods do not call each other via Java method invocations.

If `TestConfiguration` is a top-level class, import it explicitly into the test:

```java
@DataElasticsearchTest
@Import(ProductElasticsearchTestConfiguration.class)
class ProductRepositoryTests {
}
```

### 5.2 Distinguishing @Configuration and @TestConfiguration

A nested class annotated solely with `@Configuration` may be treated as a replacement configuration source in certain test bootstrap paths. `@TestConfiguration` is designed to add test configuration while retaining the primary configuration discovered from the application.

When adding beans to a slice, a nested `@TestConfiguration` usually expresses intent more accurately. If using a top-level test configuration, import it explicitly to prevent component scanning from picking it up in unrelated contexts.

## 6. Selectively Registering @ConfigurationProperties

`@DataElasticsearchTest` does not automatically scan every `@ConfigurationProperties` bean. If a configuration relies on a properties type needed by the test, register it using `@EnableConfigurationProperties`:

```java
@ConfigurationProperties(prefix = "catalog.search")
public class CatalogSearchProperties {

    private int defaultPageSize = 20;

    public int getDefaultPageSize() {
        return defaultPageSize;
    }

    public void setDefaultPageSize(int defaultPageSize) {
        this.defaultPageSize = defaultPageSize;
    }
}
```

Test:

```java
@DataElasticsearchTest
@EnableConfigurationProperties(CatalogSearchProperties.class)
class ProductRepositoryTests {

    @Autowired
    CatalogSearchProperties properties;
}
```

If properties are only used by a service outside the slice, you can import the service and register the corresponding properties. There is no need to enable full application configuration properties scanning if the test only needs one class.

## 7. Controlling Test Properties

The annotation supports the `properties` attribute to add properties to the Spring Environment before the context runs:

```java
@DataElasticsearchTest(properties = {
    "spring.elasticsearch.uris=http://localhost:9200",
    "spring.elasticsearch.connection-timeout=2s",
    "spring.elasticsearch.socket-timeout=5s"
})
class ProductRepositoryTests {
}
```

Specific property names depend on the Spring Boot version and client generation. With common Elasticsearch configurations, `spring.elasticsearch.uris` specifies the endpoint; username/password, API key, TLS bundle, and timeouts can be configured with the version's corresponding properties.

Do not put production credentials in source code or test annotations committed to the repository. Use environment variables, a secret manager, or dedicated test configurations.

### 7.1 @TestPropertySource

`@TestPropertySource` can be used to read properties files or declare inline properties:

```java
@DataElasticsearchTest
@TestPropertySource(properties = {
    "spring.elasticsearch.uris=http://localhost:9200"
})
class ProductRepositoryTests {
}
```

Choose a consistent configuration mechanism to avoid duplication and confusion over precedence. If multiple sources declare the same key, check Spring Test/Boot property source precedence rather than guessing the final value.

### 7.2 @DynamicPropertySource

When the endpoint is only known at test runtime—for instance, a container receiving a dynamic port—use `@DynamicPropertySource`:

```java
@DataElasticsearchTest
class ProductRepositoryTests {

    @DynamicPropertySource
    static void elasticsearchProperties(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.elasticsearch.uris",
            () -> "http://localhost:9200"
        );
    }
}
```

The example uses a fixed URI to demonstrate the hook. With Testcontainers, the supplier can obtain the host/port from the running container. Dynamic properties are registered before the context requiring them is created.

### 7.3 Properties Do Not Create a Server

Declaring `spring.elasticsearch.uris` only tells the client where to connect. It does not pull a Docker image, start Elasticsearch, create indices, or guarantee endpoint readiness. Test server lifecycle must be managed separately via Testcontainers, test fixtures, or an integration test environment.

## 8. includeFilters and excludeFilters

When a test needs to include or exclude a specific component during scanning, `@DataElasticsearchTest` provides `includeFilters` and `excludeFilters`. These two attributes accept Spring component scan filters.

Common filter types:

- `FilterType.ASSIGNABLE_TYPE`: selects a specific class or subtype.
- `FilterType.ANNOTATION`: selects components with a specified annotation.
- `FilterType.REGEX`: selects by class name matching a regular expression.
- `FilterType.ASPECTJ`: selects by an AspectJ type pattern.
- `FilterType.CUSTOM`: uses a custom filter implementation.

### 8.1 Including a Specific Component

For example, needing a mapper in the test slice:

```java
@DataElasticsearchTest(
    includeFilters = @ComponentScan.Filter(
        type = FilterType.ASSIGNABLE_TYPE,
        classes = ProductProjectionMapper.class
    )
)
class ProductRepositoryTests {

    @Autowired
    ProductProjectionMapper mapper;
}
```

An include filter allows a component normally excluded by the slice to be included in scanning. This is useful when the class is managed as a component and you want to preserve scanning rather than importing individual beans manually.

### 8.2 Excluding a Component

If a component is brought into the context by default but is unsuitable for the test, you can exclude it:

```java
@DataElasticsearchTest(
    excludeFilters = @ComponentScan.Filter(
        type = FilterType.ASSIGNABLE_TYPE,
        classes = LegacySearchConfiguration.class
    )
)
class ProductRepositoryTests {
}
```

Only use an exclude filter when you know where that component is being picked up from. If a service is already excluded by the slice by default, adding an exclude filter for it solves nothing and makes the configuration harder to read.

### 8.3 When to Use includeFilters vs @Import

| Need | Appropriate mechanism |
|---|---|
| Add a specific bean without scanning | `@Import` |
| Add a group of classes by stereotype/type scan | `includeFilters` |
| Add multiple test-only beans | `@TestConfiguration` |
| Enable a configuration properties class | `@EnableConfigurationProperties` |
| Enable additional auto-configuration | `@ImportAutoConfiguration` |

Prefer the mechanism that expresses intent clearly and adds the fewest components. Include filters may pull in additional dependencies if the included component has constructor dependencies on multiple beans.

### 8.4 useDefaultFilters

The annotation has a `useDefaultFilters` attribute to control applying default filters when combined with the primary `@SpringBootApplication`. Default values and interactions with include/exclude filters are described in the Javadoc for your exact version.

This is an advanced option. Do not set `useDefaultFilters = false` just to "make the test run," because this change can prevent default slice components from being discovered as expected. If deep scan customization is needed, consult the Javadoc and inspect the actual beans in the context.

## 9. excludeAutoConfiguration

`excludeAutoConfiguration` lets you exclude one or more auto-configurations from the slice:

```java
@DataElasticsearchTest(
    excludeAutoConfiguration = {
        SomeOptionalAutoConfiguration.class
    }
)
class ProductRepositoryTests {
}
```

`SomeOptionalAutoConfiguration` is an illustrative placeholder; replace it with an actual auto-configuration class from your dependencies. This attribute is an alias for `@ImportAutoConfiguration`'s exclude list.

Only exclude auto-configuration when you know exactly which beans it configures and why you do not want them. Accidentally excluding core Elasticsearch configuration can prevent templates/clients/repositories from being created and cause tests to fail when injecting or executing queries.

### 9.1 Importing Additional Auto-Configuration

If a test needs another auto-configuration, add it via `@ImportAutoConfiguration`:

```java
@DataElasticsearchTest
@ImportAutoConfiguration(ExtraTestAutoConfiguration.class)
class ProductRepositoryTests {
}
```

`@ImportAutoConfiguration` is meant for auto-configuration classes designed to be imported via Spring Boot's mechanism. For a regular `@Configuration` or specific component, use `@Import`.

Do not confuse the two annotations:

- `@Import` registers the specified configuration/component.
- `@ImportAutoConfiguration` imports auto-configuration and follows Spring Boot's import/exclusion rules.

## 10. When to Use @AutoConfigureDataElasticsearch with @SpringBootTest

If you want to run a full application context while still needing Elasticsearch test/data auto-configuration, you can use `@AutoConfigureDataElasticsearch` with `@SpringBootTest`:

```java
@SpringBootTest
@AutoConfigureDataElasticsearch
class ProductApplicationIntegrationTests {

    @Autowired
    ProductService productService;

    @Autowired
    ProductRepository products;
}
```

The package name of `@AutoConfigureDataElasticsearch` depends on the Spring Boot version. This combination fits when a test needs services, event listeners, security configuration, or other application beans alongside repositories.

Do not stack multiple test slice annotations on the same test class hoping Spring will merge the slices. Spring Boot does not support arbitrarily combining multiple `@...Test` slices. Pick one primary slice and add appropriate `@AutoConfigure...` annotations, or use `@SpringBootTest` when the goal is a full context.

### 10.1 Choosing the Test Type Based on the Question

| Question | Testing approach |
|---|---|
| Does a query method return the right documents? | `@DataElasticsearchTest` |
| Does mapping/converter serialize fields properly? | `@DataElasticsearchTest` |
| Does a custom repository/Operations call the right query? | `@DataElasticsearchTest` |
| How does a service coordinate repositories and external clients? | Service unit test or `@SpringBootTest` depending on scope |
| How do controllers, security, and repositories integrate? | `@SpringBootTest` with an appropriate web test client |
| Only testing Java algorithms without Spring/Elasticsearch | Plain unit test |

## 11. Connecting to Elasticsearch in Tests

`@DataElasticsearchTest` configures Spring beans, while the Elasticsearch server must be provided separately. You can use:

1. A local Elasticsearch instance dedicated to integration tests.
2. Elasticsearch in Docker/Testcontainers.
3. A shared test service for CI.

Avoid running tests against a production cluster or production index. Tests may create, delete, and update documents; use a dedicated test cluster/index.

### 11.1 Static Endpoint Configuration

Example using a test profile:

```properties
spring.elasticsearch.uris=http://localhost:9200
```

Or configure directly on the test:

```java
@DataElasticsearchTest(properties = {
    "spring.elasticsearch.uris=http://localhost:9200"
})
class ProductRepositoryTests {
}
```

Ensure the server is actually running before the test context or repository sends requests. If the cluster requires authentication/TLS, provide the corresponding properties for your Spring Boot version.

### 11.2 Dynamic Endpoints with Testcontainers

Testcontainers can launch Elasticsearch for integration tests. The example below illustrates the structure; the image version, Testcontainers module, and security configuration must be compatible with your project's Elasticsearch/client:

```java
@DataElasticsearchTest
class ProductRepositoryTests {

    @Container
    static final ElasticsearchContainer elasticsearch =
        new ElasticsearchContainer(
            DockerImageName.parse(
                "docker.elastic.co/elasticsearch/elasticsearch:8.17.0"
            )
        );

    @DynamicPropertySource
    static void elasticsearchProperties(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.elasticsearch.uris",
            elasticsearch::getHttpHostAddress
        );
    }
}
```

Some Elasticsearch images require a password or TLS. In that case, the container must be configured accordingly and the test must register username/password or SSL settings into the Environment. Do not copy the example image version without checking the compatibility matrix.

If using the JUnit 5/Testcontainers extension, ensure the container lifecycle starts before Spring creates the client/context needing the endpoint. With context caching, the container should have a lifecycle compatible with how long the context stays cached; if the container stops too early, subsequent tests may reuse an old context pointing to an endpoint that no longer exists.

### 11.3 Do Not Confuse the Server Container with the Test Slice

Testcontainers handles the lifecycle of the Elasticsearch process. `@DataElasticsearchTest` handles the Spring test context. The two mechanisms complement each other:

```text
Testcontainers
    -> starts Elasticsearch and exposes host/port

DynamicPropertySource
    -> publishes URI to Spring Environment

@DataElasticsearchTest
    -> configures client/template/repositories in test context

Repository test
    -> sends real requests to the container
```

If the container is running but the URI is not registered properly, the client still connects to the wrong place. If the URI is right but the container is not ready, requests may fail due to a startup race.

## 12. Managing Indices and Data Between Tests

Elasticsearch does not have automatic transaction rollback per test like some relational test slices. When a repository writes a document, the data is written to Elasticsearch and persists after the test method finishes, unless the test actively deletes it or uses an isolated index.

### 12.1 Creating Index/Mapping for Tests

You can use `IndexOperations` to create the index and mapping before running tests:

```java
@BeforeEach
void ensureIndex() {
    IndexOperations indexOperations =
        operations.indexOps(ProductDocument.class);

    if (!indexOperations.exists()) {
        indexOperations.createWithMapping();
    }
}
```

Method names and mapping creation depend on the Spring Data Elasticsearch version. If an entity uses a fixed index name, ensure tests do not accidentally share the index with other environments.

### 12.2 Cleaning Up Data After Tests

Example deleting documents via the repository:

```java
@AfterEach
void cleanUp() {
    products.deleteAll();
}
```

If a test creates multiple document types or needs to check delete/index behavior, clean up within a dedicated index or use a dedicated index name per test class. Do not delete a shared alias/index if other tests might be running concurrently.

### 12.3 Using a Dedicated Index per Test Suite

One way to isolate data is to use an index with a test suffix:

```java
@Document(indexName = "products-repository-test")
class ProductDocument {
}
```

In parallel pipelines, a fixed index name can still be shared across workers. You can generate dynamic index names per test run or class, then configure `IndexCoordinates` for the repository/Operations accordingly. Changing index names dynamically must be designed consistently with mapping metadata and repositories; do not arbitrarily override properties if the `@Document` annotation still points to another index.

### 12.4 Context Caching Does Not Reset Data

Spring TestContext can cache the `ApplicationContext` between tests with equivalent configurations. Context caching reduces startup time, but it does not automatically delete documents/indices after each test. Data management must be an explicit responsibility of test fixtures or lifecycle hooks.

`@DirtiesContext` closes/removes the context from the cache according to the configured scope, but it is not a reliable Elasticsearch data cleanup mechanism. Data may remain on the server after the context closes.

## 13. Transactions and Cleanup

Do not assume `@DataElasticsearchTest` automatically wraps each test in a transaction and rolls back Elasticsearch when the test finishes. Elasticsearch does not provide multi-document ACID transactions equivalent to JPA; successful write operations do not undo themselves just because a test method finishes or an assertion fails.

Therefore:

- Create fixture data with easily identifiable IDs.
- Use dedicated indices if tests run in parallel.
- Delete data in `@AfterEach` or delete the index in an appropriate lifecycle hook.
- Do not share mutable data across tests if execution order may change.
- Verify cleanup even when tests fail, not just on the happy path.

Example:

```java
@DataElasticsearchTest
class ProductRepositoryTests {

    @Autowired
    ProductRepository products;

    @BeforeEach
    void setUp() {
        products.deleteAll();
    }

    @Test
    void findsProductBySku() {
        products.save(new ProductDocument("p-1", "KB-1001", "Keyboard"));

        assertThat(products.findBySku("KB-1001")).isPresent();
    }
}
```

This is a simple example; if multiple test classes share an index or run in parallel, clearing the whole repository in `@BeforeEach` can destroy another test's data. In that case, use isolated indices or separate ID namespaces.

## 14. JUnit 5 and JUnit 4

In JUnit Jupiter (JUnit 5), `@DataElasticsearchTest` already includes `SpringExtension`, so you do not need to add `@ExtendWith(SpringExtension.class)`:

```java
@DataElasticsearchTest
class ProductRepositoryTests {

    @Test
    void testRepository() {
    }
}
```

With JUnit 4, use the Spring Runner:

```java
@RunWith(SpringRunner.class)
@DataElasticsearchTest
public class ProductRepositoryTests {

    @Test
    public void testRepository() {
    }
}
```

If you forget the runner in JUnit 4, Spring test annotations may not be processed as expected. For new projects, JUnit 5 is typically the default choice in modern Spring Boot.

## 15. Package Differences Between Spring Boot 3 and 4

`@DataElasticsearchTest` has been available since Spring Boot 2.7. The import package changes between major versions:

| Spring Boot | Annotation package |
|---|---|
| Spring Boot 2.7 and 3.x | `org.springframework.boot.test.autoconfigure.data.elasticsearch.DataElasticsearchTest` |
| Spring Boot 4.x | `org.springframework.boot.data.elasticsearch.test.autoconfigure.DataElasticsearchTest` |

Example import in Boot 3.x:

```java
import org.springframework.boot.test.autoconfigure.data.elasticsearch.DataElasticsearchTest;
```

Example import in Boot 4.x:

```java
import org.springframework.boot.data.elasticsearch.test.autoconfigure.DataElasticsearchTest;
```

Boot 4 also reorganizes several test auto-configuration packages. When upgrading major versions, use IDE auto-import or version-specific Javadoc to update packages. Do not resolve import errors by adding multiple versions of Spring Boot test artifacts simultaneously.

## 16. Attributes of @DataElasticsearchTest

Commonly used annotation attributes include:

| Attribute | Purpose |
|---|---|
| `properties` | Adds `key=value` properties to the Environment before the test runs |
| `includeFilters` | Includes components otherwise filtered out of the slice |
| `excludeFilters` | Excludes components matching the filter from scanning |
| `useDefaultFilters` | Controls using default filters when combined with primary configuration |
| `excludeAutoConfiguration` | Excludes auto-configurations from the imported list |

Example combining several attributes:

```java
@DataElasticsearchTest(
    properties = "spring.elasticsearch.uris=http://localhost:9200",
    includeFilters = @ComponentScan.Filter(
        type = FilterType.ASSIGNABLE_TYPE,
        classes = ProductProjectionMapper.class
    ),
    excludeFilters = @ComponentScan.Filter(
        type = FilterType.ASSIGNABLE_TYPE,
        classes = LegacySearchConfiguration.class
    )
)
class ProductRepositoryTests {
}
```

Do not add every attribute upfront. Start with the default slice; only expand when a specific dependency is needed and the reason has been identified.

## 17. Diagnosing Missing Beans

When a test reports `NoSuchBeanDefinitionException`, classify the missing bean before changing annotations:

| Missing bean | Check/resolution |
|---|---|
| Repository | Check package scanning, repository enablement, and repository type |
| Entity/mapping | Check `@Document`, package, and mapping metadata |
| `ElasticsearchOperations` | Check dependencies, auto-configuration, and client setup |
| `@ConfigurationProperties` | Register with `@EnableConfigurationProperties` |
| Mapper/helper component | Use `@Import`, `@TestConfiguration`, or include filter |
| Service/controller | Determine if full context is really needed; selectively import or use `@SpringBootTest` |
| Custom auto-configuration | Use `@ImportAutoConfiguration` if that class is a suitable auto-configuration |

### 17.1 Distinguishing Context Errors and Connection Errors

Two errors are often confused:

- **Bean does not exist:** Spring could not create the repository/template/client bean due to scanning or auto-configuration.
- **Cannot connect to Elasticsearch:** beans exist, but the endpoint, credentials, TLS, network, or server lifecycle has an issue.

If `@Autowired ProductRepository` succeeds but querying throws a connection refused error, repository scanning is not the issue. Check the URI and Elasticsearch status.

### 17.2 Enabling Debug Condition Evaluation

When you need to understand which auto-configurations were enabled/disabled, you can enable debug logging for the test or inspect the Spring Boot condition evaluation report. The goal is to determine which conditions were not met, which classes were excluded, and which beans were created.

Do not change properties en masse or add random `@Import`s before inspecting the cause. One small change can accidentally enable an entire group of out-of-slice configurations.

## 18. Common Usage Mistakes

### 18.1 Expecting Services to Be Injected Automatically

`@DataElasticsearchTest` focuses only on the Elasticsearch data slice. Regular services are not scanned automatically. Import the service if the test genuinely needs it, or use a full application test for multi-layer use cases.

### 18.2 Thinking the Annotation Automatically Starts Elasticsearch

The annotation configures the Spring context; it does not start a server. You need a local service, Testcontainers, or a dedicated test environment.

### 18.3 Thinking Each Test Rolls Back Data

Elasticsearch writes do not automatically roll back with a test transaction. Actively clean up documents/indices or isolate data.

### 18.4 Using @SpringBootTest Just to Add One Bean

If only a mapper or properties class is missing, use `@Import`, `@TestConfiguration`, or `@EnableConfigurationProperties`. A full context makes the test broader than necessary.

### 18.5 Enabling Broad Component Scanning

Custom `@ComponentScan` on the application class can prevent slice filters from working as expected. Separate special scan configurations or control imports selectively.

### 18.6 Mixing Multiple Test Slice Annotations

Do not arbitrarily combine multiple `@...Test` slices. Choose the main slice and add appropriate `@AutoConfigure...` annotations, or use `@SpringBootTest`.

### 18.7 Importing Packages from the Wrong Version

Boot 3.x and Boot 4.x have different test annotation packages. Check imports according to the dependency version in use.

### 18.8 Sharing an Index Across Parallel Tests

Tests can delete or overwrite each other's documents. Use separate indices, ID namespaces, or run sequentially when tests cannot be isolated.

## 19. Process for Choosing Test Scope

You can follow these steps:

1. Determine whether the test verifies a repository, mapping, or multi-layer use case.
2. If only testing the Elasticsearch data layer, start with `@DataElasticsearchTest`.
3. Configure an Elasticsearch endpoint dedicated to tests.
4. Verify `@Document` entities and repositories are discovered.
5. If an auxiliary bean is missing, classify it as properties, component, test bean, or auto-configuration.
6. Add the right mechanism: `@EnableConfigurationProperties`, `@Import`, `@TestConfiguration`, include filter, or `@ImportAutoConfiguration`.
7. If multiple services/controllers/integration components are needed, consider `@SpringBootTest` and `@AutoConfigureDataElasticsearch`.
8. Create/clean up indices and documents so tests remain independent.
9. Verify the Elasticsearch container lifecycle is compatible with context caching.
10. Keep the test slice small so mapping/query errors are detected quickly and diagnosed easily.

```mermaid
flowchart TD
    A[Choose test scope] --> B{Only Elasticsearch data layer?}
    B -->|Yes| C[Use @DataElasticsearchTest]
    B -->|No| D{Need full application context?}
    D -->|Yes| E[Use @SpringBootTest + @AutoConfigureDataElasticsearch]
    D -->|No| F[Use a plain unit test or a smaller focused test]
    C --> G{A required bean is missing?}
    G -->|Properties| H[@EnableConfigurationProperties]
    G -->|Specific component| I[@Import or includeFilters]
    G -->|Test-only beans| J[@TestConfiguration]
    G -->|Extra auto-configuration| K[@ImportAutoConfiguration]
    G -->|No| L[Run repository test against test Elasticsearch]
    H --> L
    I --> L
    J --> L
    K --> L
```

## 20. Implementation Principles

- Use `@DataElasticsearchTest` for repository, mapping, converter, and template tests.
- Understand that this is a test slice with restricted auto-configuration and component scanning.
- Do not expect services/controllers or every `@Component` to appear in the context automatically.
- Register needed `@ConfigurationProperties` with `@EnableConfigurationProperties`.
- Use `@Import` or `@TestConfiguration` for beans needed only by tests.
- Use include/exclude filters only when component scanning control is truly required.
- Use `@ImportAutoConfiguration` for extra auto-configurations and `excludeAutoConfiguration` to exclude specific ones.
- Check custom `@ComponentScan` on the primary application configuration if the slice scans too broadly.
- Provide a separate Elasticsearch server; the annotation does not automatically start an embedded server.
- Use static properties or `@DynamicPropertySource` to configure the endpoint.
- Actively create/clean up data; do not assume tests roll back like JPA.
- Choose `@SpringBootTest` combined with `@AutoConfigureDataElasticsearch` when a full application context is needed.
- Verify package imports according to the Spring Boot major version.

## 21. Summary

`@DataElasticsearchTest` is a test slice focused on Spring Data Elasticsearch. It auto-configures the necessary data components, discovers repositories and `@Document` entities, and restricts auto-configuration/component scanning so the entire application is not loaded. Regular services, controllers, components, and `@ConfigurationProperties` are not automatically brought into the context; add them selectively using `@Import`, `@TestConfiguration`, `@EnableConfigurationProperties`, include filters, or `@ImportAutoConfiguration`.

The annotation does not automatically start an Elasticsearch server and does not create transactions that roll back data after each test. You need to provide a test endpoint, manage server/container lifecycle, configure properties, create/clean up indices, and isolate data between tests. When you need to test services/controllers together with repositories, use `@SpringBootTest` combined with `@AutoConfigureDataElasticsearch` or choose an appropriate integration test approach.

Understanding the exact auto-configuration scope helps tests load only the components they need, run faster, and clarify whether an error lies in repository scanning, auto-configuration, auxiliary beans, or the Elasticsearch connection. Start with the default slice and expand only the part of the context the test genuinely requires.

## References

- [Spring Boot Reference — Auto-configured Data Elasticsearch Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.3 API — DataElasticsearchTest](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/autoconfigure/data/elasticsearch/DataElasticsearchTest.html)
- [Spring Boot 4 API — DataElasticsearchTest](https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/data/elasticsearch/test/autoconfigure/DataElasticsearchTest.html)
- [Spring Boot Reference — Test Slices and Auto-configuration](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Data Elasticsearch Reference](https://docs.spring.io/spring-data/elasticsearch/reference/index.html)
- [Testcontainers — Elasticsearch Module](https://java.testcontainers.org/modules/elasticsearch/)
