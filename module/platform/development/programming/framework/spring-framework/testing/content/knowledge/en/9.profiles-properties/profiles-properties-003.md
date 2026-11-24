# @TestPropertySource with Files or Inline Properties

In the Spring TestContext Framework, the **@TestPropertySource** annotation lets you declare property sources that apply only to a test ApplicationContext. You can load configuration from one or more files, declare key-value pairs inline on the test class, or combine both approaches. These values are added to the Spring Environment before beans are created, allowing tests to control configuration without modifying the application's main configuration files.

For example, a service uses the `checkout.enabled` property to enable or disable the checkout feature. In production, the value might come from `application.properties` or an environment variable. A test can provide its own value:

~~~java
@SpringJUnitConfig(AppConfig.class)
@TestPropertySource(properties = "checkout.enabled=false")
class CheckoutServiceTest {

    @Autowired
    private CheckoutService checkoutService;

    @Test
    void rejectsCheckoutWhenFeatureIsDisabled() {
        // Verify behavior when checkout.enabled=false.
    }
}
~~~

`@TestPropertySource` is useful when you need to test a bean with deterministic configuration, reuse a configuration set in a fixture file, or override a few values per test class. Because it belongs to the Spring TestContext Framework, it works with plain Spring Framework tests, Spring MVC tests, and Spring Boot tests.

## 1. The Role of Properties in the Spring Environment

The Spring Environment provides a unified model for reading properties and determining active profiles. Beans can access properties via `Environment`, use `@Value`, or receive structured data via `@ConfigurationProperties`.

~~~java
@Component
class CheckoutService {

    private final boolean enabled;

    CheckoutService(@Value("${checkout.enabled:true}") boolean enabled) {
        this.enabled = enabled;
    }

    boolean isEnabled() {
        return enabled;
    }
}
~~~

The value of `checkout.enabled` can come from various `PropertySource` instances, for example:

- Properties in application configuration files.
- Java system properties.
- Operating system environment variables.
- A `PropertySource` registered by Spring configuration.
- Test-specific properties.

Spring resolves values according to the precedence order of the `PropertySource`s in `Environment`. When a test needs to control a specific value, `@TestPropertySource` adds a test-specific property source to the context's `Environment`.

The important point is that this annotation does not modify `application.properties`, does not alter the machine's environment variables, and does not overwrite global OS configuration. It supplies values solely to the context created to run the test.

## 2. Declaring Properties Inline with properties

Properties can be declared directly on the annotation through the `properties` attribute:

~~~java
@SpringJUnitConfig(AppConfig.class)
@TestPropertySource(properties = {
    "checkout.enabled=false",
    "checkout.timeout=5s",
    "checkout.currency=VND"
})
class CheckoutConfigurationTest {

    @Autowired
    private Environment environment;

    @Test
    void exposesInlineTestProperties() {
        assertEquals(
            "false",
            environment.getProperty("checkout.enabled")
        );
        assertEquals(
            "5s",
            environment.getProperty("checkout.timeout")
        );
        assertEquals(
            "VND",
            environment.getProperty("checkout.currency")
        );
    }
}
~~~

Each element in the `properties` array is a string representing a property. You can use `key=value` or `key:value` syntax. Whitespace around the separator is handled according to Java Properties parsing rules.

~~~java
@TestPropertySource(properties = {
    "feature.search.enabled = true",
    "feature.search.page-size: 25"
})
~~~

The `properties` attribute is suited for:

- Small values used only within a single test class.
- Overriding a few default properties.
- Configuring test variants without creating additional files.
- Making test conditions explicit right at the declaration site.

Avoid placing a very long list of properties inline in the annotation if it makes the test class hard to read. When many related configurations exist or multiple tests share them, moving them into a properties file can help organize things better.

### 2.1. Reading properties with Environment

`Environment` lets you access properties by name and convert data types:

~~~java
@Autowired
private Environment environment;

@Test
void readsConfiguredValues() {
    assertEquals("VND", environment.getProperty("checkout.currency"));
    assertFalse(environment.getProperty(
        "checkout.enabled",
        Boolean.class,
        true
    ));
}
~~~

When a default value is needed, you can use the overload accepting a default value. If a property is required, use a lookup method that makes the test fail clearly when configuration is missing, rather than silently receiving an inappropriate default value.

### 2.2. Using @Value

Beans can receive properties via `@Value`:

~~~java
@Component
class SearchSettings {

    private final int pageSize;

    SearchSettings(@Value("${feature.search.page-size}") int pageSize) {
        this.pageSize = pageSize;
    }

    int pageSize() {
        return pageSize;
    }
}
~~~

The test declares the value:

~~~java
@SpringJUnitConfig(AppConfig.class)
@TestPropertySource(properties = "feature.search.page-size=25")
class SearchSettingsTest {

    @Autowired
    private SearchSettings settings;

    @Test
    void injectsPageSizeFromTestPropertySource() {
        assertEquals(25, settings.pageSize());
    }
}
~~~

The property must be present in `Environment` before beans are instantiated and placeholders are resolved. Therefore, `@TestPropertySource` is declared on the test class, not as an operation that mutates values after the context has already created beans.

### 2.3. Using @ConfigurationProperties

For structured configuration groups, `@ConfigurationProperties` is often easier to manage than many scattered `@Value` annotations:

~~~java
@ConfigurationProperties(prefix = "checkout")
public class CheckoutProperties {

    private boolean enabled;
    private Duration timeout = Duration.ofSeconds(10);

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
~~~

A test can provide:

~~~java
@SpringJUnitConfig(CheckoutTestConfig.class)
@TestPropertySource(properties = {
    "checkout.enabled=true",
    "checkout.timeout=3s"
})
class CheckoutPropertiesTest {

    @Autowired
    private CheckoutProperties properties;

    @Test
    void bindsInlineProperties() {
        assertTrue(properties.isEnabled());
        assertEquals(Duration.ofSeconds(3), properties.getTimeout());
    }
}
~~~

In this example, `CheckoutTestConfig` needs to register `CheckoutProperties` via `@EnableConfigurationProperties` or the application's appropriate registration mechanism. With Spring Boot, you can use `@EnableConfigurationProperties`, `@ConfigurationPropertiesScan`, or existing application configuration. `@TestPropertySource` only supplies values; it does not automatically register configuration beans.

## 3. Loading Properties from Files

When a configuration has many values, is reused across multiple tests, or should be treated as a separate fixture, declare files in `locations`:

~~~java
@SpringJUnitConfig(AppConfig.class)
@TestPropertySource(locations = "classpath:/test-config/checkout.properties")
class CheckoutServiceIntegrationTest {

    @Autowired
    private CheckoutService checkoutService;

    @Test
    void usesCheckoutTestConfiguration() {
        // ...
    }
}
~~~

Create the file in `src/test/resources`:

~~~properties
checkout.enabled=true
checkout.timeout=3s
checkout.currency=VND
payment.gateway.url=https://gateway.example.test
~~~

Because `src/test/resources` is on the test classpath, Spring can locate the file using `ClassPathResource`. The `classpath:` prefix makes the resource source explicit and avoids depending on the working directory.

### 3.1. Location formats

The `locations` attribute accepts one or more resource locations. Common formats include:

| Location Format | Meaning | Example |
|---|---|---|
| `classpath:` | Look up resource on the classpath | `classpath:/test-config/app.properties` |
| `file:` | Read file from the filesystem | `file:./config/test.properties` |
| URL with scheme | Read resource from a supported URL | `https://example.test/config.properties` |
| Path without prefix | Treated as a classpath resource by default | `test-config/app.properties` |

In automated tests, fixture files on the classpath are usually the most stable. Relative file paths depend on the working directory, while external URLs make tests depend on the network and external systems. Only use those sources when that is specifically what the test needs to verify.

Multiple files can be declared:

~~~java
@TestPropertySource(locations = {
    "classpath:/test-config/common.properties",
    "classpath:/test-config/checkout.properties"
})
~~~

Spring loads the declared resources and adds the properties to `Environment`. When the same key appears in multiple sources, the order and precedence of the `PropertySource`s determine the final value; declare clearly which source is intended to override.

### 3.2. Default path when locations is omitted

If `@TestPropertySource` declares neither `locations` nor `properties`, Spring can look for a default properties file based on the fully qualified name of the test class. For example, the test class `com.example.CheckoutServiceTest` corresponds to the resource:

~~~text
classpath:com/example/CheckoutServiceTest.properties
~~~

If the default file does not exist, Spring reports an error when preparing the test context. This mechanism can be useful when each test class has its own configuration file following a naming convention. In projects with many fixtures, declaring `locations` explicitly is usually easier to read and locate.

### 3.3. Reading XML properties

Spring Test's `DefaultPropertySourceFactory` supports properties resources in Java's `.properties` format and XML properties format. XML properties must conform to the format supported by `java.util.Properties.loadFromXML`, not an arbitrary XML file.

Example:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE properties SYSTEM "http://java.sun.com/dtd/properties.dtd">
<properties>
    <entry key="checkout.enabled">true</entry>
    <entry key="checkout.timeout">3s</entry>
</properties>
~~~

The file can be referenced via `locations` just like a `.properties` file. If an application uses another format such as YAML, you must configure an appropriate `PropertySourceFactory` or use Spring Boot's configuration mechanism. Do not rename a YAML file to `.properties` and expect Spring to understand YAML syntax automatically.

### 3.4. File encoding

The `encoding` attribute lets you specify the charset when reading source files:

~~~java
@TestPropertySource(
    locations = "classpath:/test-config/messages.properties",
    encoding = "UTF-8"
)
~~~

If a file contains Vietnamese characters or non-ASCII content, keep the encoding consistent between saving the file and loading it. Do not rely on the operating system's default charset, as developer machines and CI may differ.

## 4. Combining Files and Inline Properties

You can use both `locations` and `properties` on the same annotation:

~~~java
@SpringJUnitConfig(AppConfig.class)
@TestPropertySource(
    locations = "classpath:/test-config/checkout.properties",
    properties = {
        "checkout.enabled=false",
        "checkout.timeout=1s"
    }
)
class CheckoutOverrideTest {
    // ...
}
~~~

This is an appropriate approach when a file holds a baseline configuration set while the test class changes only a few values to create a specific scenario.

When the same key appears in both the file and inline properties, inline properties have higher precedence than properties loaded from `locations`. In the example above, if the file declares `checkout.enabled=true`, the inline value `false` will be used for this test context.

This rule enables layered configuration:

1. Properties files store shared baseline values.
2. Inline properties describe differences specific to a test class.
3. Test methods verify bean behavior under those conditions.

Do not declare the same key multiple times unless overriding is intentional. When overriding, keep the property name and inline value close to the test being verified so readers understand the reason.

## 5. Precedence Order of Test Property Sources

Spring `Environment` can contain multiple `PropertySource`s. Sources added for tests have high precedence so tests can override application configuration. With `@TestPropertySource`, the key rules are:

- Inline properties in `properties` have higher precedence than properties loaded from `locations`.
- Test property sources can override normal configuration sources such as application-level `@PropertySource`, system properties, and environment variables.
- Properties registered with `@DynamicPropertySource` have higher precedence than `@TestPropertySource`.
- Other framework or Spring Boot configuration mechanisms may have their own rules; examine all property sources when the final value is not as expected.

For example, configuration file:

~~~properties
feature.mode=standard
feature.timeout=10s
~~~

Test class:

~~~java
@TestPropertySource(
    locations = "classpath:/test-config/feature.properties",
    properties = "feature.mode=isolated"
)
~~~

In the test context, `feature.mode` receives the value `isolated`; `feature.timeout` still receives `10s` from the file.

If a value is overridden unexpectedly, you can inspect the sources by accessing the `PropertySources` of `ConfigurableEnvironment`:

~~~java
@Autowired
private Environment environment;

@Test
void inspectsPropertySources() {
    ConfigurableEnvironment configurable =
        (ConfigurableEnvironment) environment;

    configurable.getPropertySources().forEach(source ->
        System.out.println(source.getName())
    );
}
~~~

This example is for investigating property source ordering. Do not leave debug logs or assertions depending on internal `PropertySource` names if those names are not part of the application's stable contract.

## 6. Configuration Inheritance Across Test Classes

When a test class extends a base class, Spring TestContext can inherit `locations` and inline `properties` declared on the parent class.

~~~java
@SpringJUnitConfig(AppConfig.class)
@TestPropertySource(
    locations = "classpath:/test-config/integration.properties"
)
abstract class BaseIntegrationTest {
}

@TestPropertySource(properties = "payment.mode=stub")
class PaymentServiceTest extends BaseIntegrationTest {
    // ...
}
~~~

By default, Spring inherits `locations` and `properties` from enclosing or parent classes according to the corresponding test class model. Values on the child class are combined with inherited values. The two attributes controlling this behavior are:

- `inheritLocations`: defaults to `true`; determines whether to inherit the resource `locations` list.
- `inheritProperties`: defaults to `true`; determines whether to inherit inline `properties`.

Inheritance can be disabled individually:

~~~java
@TestPropertySource(
    locations = "classpath:/test-config/payment-isolated.properties",
    inheritLocations = false,
    inheritProperties = false
)
class IsolatedPaymentTest extends BaseIntegrationTest {
    // Only use the configuration declared directly on this class.
}
~~~

When inheritance is disabled, the child test class uses only the configuration set it declares under that policy. Use this option when a group of tests genuinely needs a different environment; do not disable inheritance merely to avoid understanding property source ordering.

### 6.1. Combining multiple configuration layers

You can create a base class for shared configuration, then add specific properties on child classes:

~~~java
@TestPropertySource(
    locations = "classpath:/test-config/application-test.properties"
)
abstract class BaseServiceTest {
}

@TestPropertySource(properties = {
    "notification.enabled=false",
    "notification.sender=test@example.test"
})
class NotificationServiceTest extends BaseServiceTest {
}
~~~

This reduces duplication when multiple tests use the same baseline configuration. However, the base class should hold genuinely shared configuration. If each test class has a long, distinct list of overrides, putting configuration in a base class can make value origins harder to trace.

## 7. Combining @TestPropertySource with @ActiveProfiles

`@TestPropertySource` and `@ActiveProfiles` address two different needs:

- `@ActiveProfiles` selects which Spring profiles to activate, such as `test` or `integration`.
- `@TestPropertySource` provides additional or overriding property values for the test context.

Example:

~~~java
@SpringJUnitConfig(AppConfig.class)
@ActiveProfiles("test")
@TestPropertySource(properties = {
    "payment.gateway.url=https://gateway.example.test",
    "payment.retry.enabled=false"
})
class PaymentServiceTest {
    // ...
}
~~~

The `test` profile can cause Spring to select beans annotated with `@Profile("test")` or load corresponding profile configurations. Inline properties supply values specific to the test scenario. If the goal is to select beans by profile, declare `@ActiveProfiles` so intent is clear; do not use an arbitrary property in place of the profile mechanism.

When configuration files span multiple profiles, be clear about which profiles are active and which property sources are loaded. A property existing in a file does not mean the profile containing its corresponding beans is active.

## 8. Using @TestPropertySource in Spring Boot Tests

`@TestPropertySource` is not limited to `@SpringJUnitConfig`. It can be used with `@SpringBootTest` or Spring Boot test slices:

~~~java
@SpringBootTest
@TestPropertySource(
    locations = "classpath:/test-config/order-service.properties"
)
class OrderServiceApplicationTest {

    @Autowired
    private OrderService orderService;

    @Test
    void startsWithTestConfiguration() {
        // ...
    }
}
~~~

Spring Boot also provides the `properties` attribute on `@SpringBootTest` to declare values inline:

~~~java
@SpringBootTest(properties = {
    "order.processing.enabled=false",
    "order.processing.batch-size=10"
})
class OrderProcessingTest {
}
~~~

The two approaches have similar goals but are not identical in declaration location and organization:

| Approach | When to Use |
|---|---|
| `@TestPropertySource(properties = ...)` | Want to use Spring TestContext's mechanism and optionally combine with resource files |
| `@TestPropertySource(locations = ...)` | Want to load a property set from a dedicated fixture |
| `@SpringBootTest(properties = ...)` | Test uses Spring Boot and wants quick inline values on the bootstrap annotation |
| `@DynamicPropertySource` | Values are provided dynamically during test execution, such as URLs/ports of containers or launched services |

Choose one clear declaration place for each configuration group. When combining multiple mechanisms, remember their precedence order so tests do not receive unexpected values.

## 9. When Should @DynamicPropertySource Be Used?

`@TestPropertySource` fits static values known before the context initializes. If a value is only available after a test resource starts—such as the random port of a database container—`@DynamicPropertySource` is a better fit.

~~~java
@SpringBootTest
class DatabaseIntegrationTest {

    @Container
    static PostgreSQLContainer<?> database =
        new PostgreSQLContainer<>("postgres:16");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", database::getJdbcUrl);
        registry.add("spring.datasource.username", database::getUsername);
        registry.add("spring.datasource.password", database::getPassword);
    }
}
~~~

This example requires Testcontainers and container lifecycle configuration suited to the project. `DynamicPropertyRegistry` accepts a `Supplier` to obtain the value at the time Spring needs the property. This is a better choice than trying to write a random port into a properties file before the container runs.

You can combine `@DynamicPropertySource` with `@TestPropertySource`: the file provides static configuration, while the dynamic source supplies connection values generated at test runtime. When the same key appears in both sources, the dynamic property source has higher precedence.

## 10. Customizing PropertySourceFactory

By default, `@TestPropertySource` uses Spring's factory to load properties files. When another format or custom `PropertySource` creation logic is needed, you can supply a custom `PropertySourceFactory` via the `factory` attribute.

Example declaration structure:

~~~java
@TestPropertySource(
    locations = "classpath:/test-config/application-test.yml",
    factory = YamlPropertySourceFactory.class
)
class YamlBackedTest {
}
~~~

`YamlPropertySourceFactory` here is a class supplied by the application or a library; Spring Test does not automatically treat every YAML file as a property source just because the extension is `.yml`. The factory needs to read the `Resource`, parse the content, and return an appropriate `PropertySource`.

When implementing a custom factory, handle clearly:

- Missing or unreadable resources.
- Malformed syntax in content.
- File encoding.
- Nested YAML structures and key mapping rules.
- `PropertySource` naming and handling of multiple resources.

The `factory` attribute is available in Spring Framework versions that support this API; verify the project's framework version before using it. If a test only needs a few properties, inline properties are usually simpler than creating a factory.

## 11. Property Sources and the Spring TestContext Cache

The Spring TestContext Framework can cache `ApplicationContext` instances across tests with equivalent configurations. Property source configuration is part of the metadata used to determine whether a context can be reused.

This has several consequences:

- Multiple test classes using the same `locations` and `properties` configuration can reuse a context.
- Each test class declaring a different set of inline `properties` may require its own context.
- Changing the order or content of property sources can make context configurations differ.
- Using too many property source variations increases the number of contexts to initialize and total suite runtime.

For example, if ten test classes all need `checkout.enabled=true` and `checkout.timeout=3s`, they can use a shared fixture file or unified base configuration. Create separate variations only when a test genuinely requires different conditions.

Do not force every test into the same context just to increase cache hits if doing so causes mutable state to be shared unsafely across tests. Test independence and reliability remain more important than optimizing context startup time.

## 12. Common Pitfalls

### 12.1. Wrong resource path

An unfound location causes test property source loading to fail during context preparation. Place files in `src/test/resources`, check exact filename casing, and use the `classpath:` prefix explicitly.

### 12.2. Mistyped property name

`Environment` does not guess similar keys. `checkout.enable` and `checkout.enabled` are two different properties. Use a constant or consistent naming convention when the same key is used in multiple places.

### 12.3. Thinking inline properties write back to files

`@TestPropertySource` only adds a `PropertySource` to the test context. It does not edit `application.properties` or fixture files. If file content needs to change, that is a separate operation and should not happen as a test side effect.

### 12.4. Misunderstanding precedence order

If a file has `checkout.enabled=true` but an inline property declares `false`, the inline value takes precedence. When results are not as expected, inspect all relevant `PropertySource`s, including dynamic property sources and application configuration.

### 12.5. Using @TestPropertySource instead of profiles

Profiles determine which configuration groups or beans are activated. Use `@ActiveProfiles` to describe a test's profiles; use `@TestPropertySource` to supply property values.

### 12.6. Reading properties too early

If a class reads `System.getProperty` directly in a static initializer or constructor invoked before Spring prepares the context, it will not see values from the test `PropertySource`. Let configuration flow through the Spring `Environment`, `@Value`, or `@ConfigurationProperties` if the component belongs to the Spring container.

### 12.7. Using overly large configuration files

A test file containing many unrelated values makes tests hard to understand and prone to being affected by unrelated changes. Split fixtures by functional area or declare only the needed values inline.

### 12.8. Using YAML files without a factory

The default property source factory does not parse YAML the way Spring Boot configuration does. If using YAML, choose a factory that supports that format or an appropriate configuration mechanism; otherwise, use `.properties` files.

### 12.9. Mutating properties after the context is created

`@TestPropertySource` is applied when preparing the context. If a property is changed after beans have already been created, fields injected with `@Value` or `@ConfigurationProperties` do not automatically update. For values that must vary over time within the same test, design a controllable abstraction or create a new context as needed.

## 13. Configuration-Based Test Organization Pattern

A test that uses a file as a baseline and inline properties to override can be written as follows:

~~~java
@SpringJUnitConfig(AppConfig.class)
@TestPropertySource(
    locations = "classpath:/test-config/checkout.properties",
    properties = {
        "checkout.enabled=false",
        "checkout.timeout=1s"
    }
)
class CheckoutDisabledTest {

    @Autowired
    private CheckoutService checkoutService;

    @Test
    void rejectsCheckoutWhenDisabled() {
        assertThrows(
            CheckoutDisabledException.class,
            () -> checkoutService.checkout(validCommand())
        );
    }
}
~~~

The `checkout.properties` file can hold the baseline values:

~~~properties
checkout.enabled=true
checkout.timeout=10s
checkout.currency=VND
checkout.max-items=20
~~~

In this test context, `checkout.enabled` and `checkout.timeout` are overridden by inline values; `currency` and `max-items` still come from the file. This creates a readable configuration that highlights only the differences for the scenario.

When designing property-driven tests, determine:

- Which values are shared baseline configuration?
- Which values are conditions specific to the test?
- Should a fixture file or inline properties be declared?
- Are any higher-precedence property sources overriding them?
- Does the test need a specific profile or only a few properties?
- Are the values static or must they be obtained dynamically from test resources?
- Can the configuration be shared to reuse the context or does it need an isolated context?

## Conclusion

`@TestPropertySource` helps Spring TestContext load dedicated test configuration from files or inline key-value property pairs. Files suit shared baseline configuration sets; inline properties suit short values that should be explicit right in the test class. You can combine both approaches, inherit or disable inheritance of configurations, and coordinate with `@ActiveProfiles` and `@DynamicPropertySource` when needed. Understanding precedence order and `ApplicationContext` creation timing ensures tests receive the right configuration, remain stable, and stay easy to maintain.
