# @ConfigurationProperties, Constructor Binding, and Nested Data Types

## 1. Why Do We Need Typed Configuration Binding?

Spring Boot applications typically receive configuration from `application.yml`, `application.properties`, environment variables, system properties, command-line arguments, or external configuration sources. If values are read individually with `@Value` or by calling `Environment.getProperty()` directly, configuration can easily become scattered and difficult to validate.

**`@ConfigurationProperties`** groups properties sharing the same prefix into a typed Java object. It supports data type conversion, nested structures, lists, maps, and validation integration. With constructor binding, the configuration object can be immutable after creation, clearly representing the input data required by the application.

In the **SPRING_BOOT_NATIVE_IMAGE** module, binding also needs to be viewed within the Spring AOT workflow. Spring AOT analyzes the ApplicationContext and configuration beans, then generates initialization code. Using explicitly declared, typed configuration properties registered in the context makes the application structure easier to analyze, test, and package natively.

## 2. Creating Configuration Properties with a Prefix

For example, an order-processing application needs the following configuration:

```yaml
orders:
  service-name: order-api
  enabled: true
  timeout: 3s
  max-items: 100
```

It can be mapped into a class:

```java
@ConfigurationProperties(prefix = "orders")
public class OrdersProperties {

    private String serviceName;
    private boolean enabled;
    private Duration timeout;
    private int maxItems;

    // getters and setters
}
```

Spring Boot relaxed binding maps property names such as `service-name` to the Java property `serviceName`. Types like `boolean`, `int`, and `Duration` are converted from configuration strings via Spring Boot's conversion service.

Avoid using a single giant properties class containing configuration for multiple subsystems. Splitting by prefix and responsibility keeps configuration clear, easy to validate, and easy to manage across environments.

## 3. Registering Configuration Properties in the ApplicationContext

There are two common ways for Spring to discover classes annotated with `@ConfigurationProperties`.

### Using Configuration Properties Scan

```java
@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
```

Scanning starts by default from the application class's package and its subpackages. If the properties class resides outside that scope, specify the packages or classes to scan using the appropriate API.

### Using @EnableConfigurationProperties

```java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(OrdersProperties.class)
class OrdersConfiguration {
}
```

This approach explicitly registers specific properties classes, making it suitable when you want to control the list of types added to the context.

Simply placing `@ConfigurationProperties` on a class does not guarantee the bean will be automatically registered in every application structure. A corresponding scan or enable mechanism must be configured.

## 4. Constructor Binding and Immutable Configuration

Constructor binding lets Spring create an object by passing configuration values into the constructor. In Spring Boot 3, a class with a single constructor is typically used for constructor binding without needing `@ConstructorBinding`. With multiple constructors, you may need to mark the chosen constructor with the `@ConstructorBinding` annotation from the `org.springframework.boot.context.properties.bind` package according to the corresponding version.

Java record example:

```java
@ConfigurationProperties(prefix = "orders")
public record OrdersProperties(
        String serviceName,
        boolean enabled,
        Duration timeout,
        int maxItems) {
}
```

A record has a canonical constructor and automatically generated accessors. When using a record, there is no need to write manual getters/setters. The object is created with the configuration values and its components cannot be modified after initialization.

Advantages of constructor binding:

- The configuration object has immutable state.
- Required values are clearly expressed right in the constructor signature.
- Unit tests are easy to write by constructing the object directly.
- Half-initialized configuration states caused by uncalled setters are avoided.

With regular Java classes, you can use a constructor with `final` fields. Do not arbitrarily mix constructor binding with setter binding; choose a clear binding model appropriate to your Spring Boot version.

## 5. Nested Data Types

Real-world configuration often has groups of related properties. For example:

```yaml
orders:
  service-name: order-api
  enabled: true
  client:
    base-url: https://inventory.internal
    connect-timeout: 2s
    read-timeout: 5s
  retry:
    max-attempts: 3
    backoff: 500ms
```

The Java model can use nested records:

```java
@ConfigurationProperties(prefix = "orders")
public record OrdersProperties(
        String serviceName,
        boolean enabled,
        Client client,
        Retry retry) {

    public record Client(
            URI baseUrl,
            Duration connectTimeout,
            Duration readTimeout) {
    }

    public record Retry(
            int maxAttempts,
            Duration backoff) {
    }
}
```

The Spring Boot binder maps `orders.client.base-url` to the `client.baseUrl` component, and similarly for `retry`. Grouping properties helps separate connection configuration from retry configuration.

With nested types, you need to define the behavior when an entire group is missing. If a child object is required, validation or a default value must be explicitly designed; do not assume every nested object automatically receives default values when corresponding properties are absent.

## 6. Default Values for Nested Objects

Spring Boot supports `@DefaultValue` in constructor binding to provide default values when the corresponding property is not configured. For example:

```java
@ConfigurationProperties(prefix = "orders")
public record OrdersProperties(
        String serviceName,
        @DefaultValue("true") boolean enabled,
        @DefaultValue Client client) {

    public record Client(
            @DefaultValue("2s") Duration connectTimeout,
            @DefaultValue("5s") Duration readTimeout) {
    }
}
```

`@DefaultValue` without a value on a nested object parameter can instruct the binder to create the child object even when none of its child properties are present. This is useful when you want `client` to be non-null with default timeouts.

If a nested object must be fully provided, you can omit the default and use validation to reject missing configuration. Choose a consistent policy: safe defaults for development environments, or mandatory declaration in production environments.

## 7. Lists and Maps in Configuration

Configuration properties support collections. YAML example:

```yaml
orders:
  allowed-regions:
    - north
    - central
    - south
  limits:
    basic: 100
    premium: 1000
```

Record:

```java
@ConfigurationProperties(prefix = "orders")
public record OrdersProperties(
        List<String> allowedRegions,
        Map<String, Integer> limits) {
}
```

The binder converts lists and maps from property source structures into Java types. You can use collections nested inside nested records to model routing, tenants, features, or per-group limits.

Note that ordering and how collections merge across property sources follow specific rules. When profile-specific config or environment variables override a list, do not assume values are always appended; verify the binding behavior of your Spring Boot version and test the actual configuration.

## 8. Configuration Validation

Invalid configuration should be caught early during ApplicationContext creation rather than causing errors on the first request. You can use Jakarta Bean Validation:

```java
@ConfigurationProperties(prefix = "orders")
@Validated
public record OrdersProperties(
        @NotBlank String serviceName,
        @Min(1) int maxItems,
        @Valid Client client) {

    public record Client(
            @NotNull URI baseUrl,
            @NotNull Duration connectTimeout) {
    }
}
```

An appropriate validation dependency is required, typically `spring-boot-starter-validation`, along with importing annotations from `jakarta.validation.constraints`. `@Valid` tells validation to cascade into nested objects; without it, constraints on nested objects may not be checked as expected.

Some useful rules:

- `@NotBlank` for required strings that must not be empty.
- `@Min`/`@Max` for integers within bounds.
- `@NotNull` for required objects, URIs, or Durations.
- `@Valid` to validate nested structures.
- Custom constraints when business rules cannot be expressed with built-in annotations.

If validation fails, Spring Boot typically throws an error while binding or initializing the configuration bean. This is a good place to fail fast before receiving traffic.

## 9. Type Conversion and Value Formatting

Spring Boot supports conversion for many common types such as `Duration`, `DataSize`, enums, URIs, and numeric types. For example:

```yaml
orders:
  timeout: 2500ms
  payload-limit: 10MB
  endpoint: https://orders.internal/api
  mode: STRICT
```

Record:

```java
@ConfigurationProperties(prefix = "orders")
public record OrdersProperties(
        Duration timeout,
        DataSize payloadLimit,
        URI endpoint,
        Mode mode) {

    enum Mode {
        STRICT, RELAXED
    }
}
```

Use appropriate domain types instead of keeping every value as a `String` and parsing them scattered throughout services. When special formatting is needed, you can register a converter according to the supported Spring Boot configuration properties binding mechanism.

Be sure to check units explicitly: `2500ms` and `2s` represent durations, whereas `10MB` is a data size. Avoid unitless numbers when the default unit is not obvious.

## 10. Distinguishing Binding from @Value

| Criterion | `@ConfigurationProperties` | `@Value` |
|---|---|---|
| Scope | Groups properties by prefix | Single value or expression |
| Nested objects | Supported directly | Must combine multiple fields manually |
| Validation | Integrated Bean Validation | Usually requires separate handling |
| IDE metadata | Can generate configuration metadata | More limited |
| Constructor binding | Supports immutable objects | Can inject into constructor but does not group properties |
| SpEL | Does not use SpEL for standard property binding | Supports SpEL |
| Best suited for | Structured configuration | A few isolated values |

For example, `@Value("${server.port}")` makes sense for a single simple value in a bean. When there are multiple related properties such as timeout, endpoint, retry, credentials reference, and limits, `@ConfigurationProperties` is easier to manage.

Do not replace every `@Value` in the application with configuration properties if that group only has a single value and does not need a separate abstraction.

## 11. Binding and Spring AOT

Spring AOT analyzes the ApplicationContext during the build phase. Configuration properties are registered as beans in the context with explicit type metadata, so Spring can prepare the corresponding initialization code. Constructor binding also makes the input dependencies needed to instantiate the object explicit.

For AOT to recognize properties:

- Register the class via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`.
- Keep constructor signatures and nested types concrete.
- Avoid creating configuration beans via custom reflection without metadata.
- Ensure properties/profiles used to evaluate bean structure are supplied accurately to the AOT step.
- Use validation to detect invalid configuration early.

Spring Boot provides AOT support for many common configuration properties scenarios. Avoid manually adding reflection hints for every properties class if the framework already handles it. If a library or custom binder uses reflection outside the Spring-supported path, inspect native diagnostics and add the necessary RuntimeHints/metadata.

## 12. Metadata for IDEs and Discoverable Configuration

The Spring Boot configuration processor can generate JSON metadata so IDEs can suggest property names, types, and descriptions. With Maven or Gradle, add the appropriate annotation processor:

Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
```

Gradle:

```groovy
annotationProcessor(
    "org.springframework.boot:spring-boot-configuration-processor"
)
```

Metadata is typically generated into `META-INF/spring-configuration-metadata.json` in the build output. This is metadata for tooling/documentation support, not a replacement for GraalVM RuntimeHints or reachability metadata.

You can add descriptions and default values to metadata if you need to document properties for operators. Never write secrets or sensitive values into metadata.

## 13. Testing Configuration Properties

You can test binding directly or by starting an ApplicationContext. Example with Spring Boot test:

```java
@SpringBootTest(properties = {
        "orders.service-name=order-api",
        "orders.enabled=true",
        "orders.client.connect-timeout=2s"
})
class OrdersPropertiesTest {

    @Autowired
    OrdersProperties properties;

    @Test
    void bindsNestedValues() {
        assertThat(properties.serviceName()).isEqualTo("order-api");
        assertThat(properties.client().connectTimeout())
                .isEqualTo(Duration.ofSeconds(2));
    }
}
```

The example assumes `OrdersProperties` is already registered in the context, and the nested client is created according to the provided configuration. For records with required nested objects, the test must declare sufficient properties or corresponding defaults.

You should write tests for:

- Default values when properties are missing.
- Nested objects and nested collections.
- Conversion of `Duration`, `DataSize`, enums, and URIs.
- Validation when values are missing or invalid.
- Overrides via profile, environment, or command line.
- AOT configuration selected for each structural variant.

## 14. Native Image: Testing Binding on the Executable

A test passing on the JVM does not by itself prove that binding works correctly in native mode. After configuring AOT and building the native image, you must run the executable with the same test configuration suite.

Workflow:

1. Run JVM integration tests with the recorded profiles and properties.
2. Run Spring AOT via the appropriate Maven/Gradle plugin.
3. Build the Native Image.
4. Run the binary with the corresponding classpath configuration files and external config.
5. Verify nested values, defaults, conversion, and validation.
6. Run in a container with environment variables or a mounted config file.
7. Compare JVM and native results.

If configuration properties only supply runtime values such as URLs or timeouts, you can run the same binary with different values as long as the bean structure does not change. If a property is used with `@ConditionalOnProperty` to enable or disable a configuration class, that value can affect AOT structure and must be fixed appropriately at build time.

## 15. Common Errors and Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Properties bean is not injected | Class not scanned or enabled | Add `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties` |
| Nested object is null | No property/default and nested binding was not initialized | Use `@DefaultValue` appropriately or require configuration |
| Constructor binding does not work | Multiple constructors or misplaced annotation | Configure constructor binding according to the Spring Boot version |
| Property does not bind | Wrong prefix, name, or property source | Check relaxed binding and the effective Environment |
| Wrong Duration/DataSize | Missing or incorrect unit | Use explicit units such as `2500ms`, `10MB` |
| Validation does not run on nested object | Missing `@Valid` or validation dependency | Add the annotation and validation starter |
| Passes on JVM, fails in native binder/custom converter | Dynamic reflection/type path outside default support | Check native diagnostics and add hints if truly needed |
| Native uses unexpected configuration | Different structural properties/profiles during AOT | Record and pass the exact properties into the AOT phase |

When debugging, check in order: whether the class is registered, whether the prefix/property source is correct, whether the constructor/nested types are valid, whether validation runs, and only then examine AOT/native metadata issues.

## 16. Lab Exercise: Building Nested Order Configuration

**Context:** the order API service needs an inventory endpoint, timeouts, a retry policy, and a list of allowed regions.

**Step 1 — Create YAML.** Declare `orders.client`, `orders.retry`, `orders.allowed-regions`, and the required values.

**Step 2 — Create record properties.** Use `@ConfigurationProperties(prefix = "orders")`, nested records for client/retry, and `List<String>` for regions.

**Step 3 — Register properties.** Use `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`.

**Step 4 — Add validation.** Verify that the URL is non-null, timeouts are positive, max attempts is at least 1, and service name is not blank.

**Step 5 — Write tests.** Test binding, defaults, nested values, collections, conversion, and validation failure.

**Step 6 — Run Spring AOT and native build.** Observe AOT, build the executable, and verify the properties bean is created properly.

**Step 7 — Run in a container.** Supply external config via environment/mount; change the endpoint and timeout without rebuilding when they are purely runtime values.

Completion criteria: properties are bound with the right types, nested objects work, validation fails fast, runtime configuration can be changed as designed, and the native executable behaves identically to the JVM.

## 17. Conclusion

`@ConfigurationProperties` provides a typed, prefixed way to organize Spring Boot configuration with support for nested objects, collections, conversion, and validation. Constructor binding, especially with Java records, helps create immutable configuration and makes required initialization values explicit.

In Spring Boot Native Image, register configuration properties explicitly in the ApplicationContext, distinguish runtime values from properties that determine bean structure, verify validation, and run the same test suite against the native executable. Typed and tested configuration makes applications easy to operate across multiple environments without relying on dynamic binding operations that are hard to analyze.
