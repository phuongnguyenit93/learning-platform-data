# Constructor Binding, Java Records, and Refresh Limitations

This lesson belongs to the **Typed Configuration** chapter of the **SPRING_CLOUD_CORE** module. Spring Boot groups related properties into strongly typed objects using `@ConfigurationProperties`. With **constructor binding**, the Binder passes values into a constructor to create the object; fields can be `final` and setters are unnecessary. Java **records** are a natural fit for immutable configuration since components are declared directly in the record header.

Immutability makes configuration easy to read, easy to test, and safe against unintended mutation after startup. However, there is an important limitation in Spring Cloud: **constructor-bound configuration properties, including Java records, are not directly rebound by Spring Cloud Context on refresh**. If configuration must change while the application is running, choose a different design or establish a clear mechanism to recreate configuration snapshots.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish JavaBean/setter binding from constructor binding.
2. Declare immutable configuration using a Java class or Java record.
3. Register configuration with `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`.
4. Use `@DefaultValue` on constructor parameters, record components, and nested objects.
5. Combine type conversion, relaxed binding, and Bean Validation.
6. Understand compiler parameter-name requirements and differences across Spring Boot generations.
7. Explain why constructor-bound objects are not rebound by Spring Cloud Context.
8. Choose between restarts, mutable configuration properties, and refresh-scoped snapshots when configuration changes are needed.
9. Write tests verifying binding, defaults, validation, and refresh limitations.
10. Avoid confusing an Environment receiving new values with an immutable object being recreated.

## 2. Two Ways to Bind Configuration

`@ConfigurationProperties` maps a group of properties into a structured object. Spring Boot supports two common binding styles.

### 2.1. JavaBean Binding

JavaBean binding typically uses a no-arg constructor and setters:

~~~java
@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {
    private URI baseUrl;
    private Duration connectTimeout = Duration.ofSeconds(1);
    private int maxAttempts = 3;

    public URI getBaseUrl() { return baseUrl; }
    public void setBaseUrl(URI baseUrl) { this.baseUrl = baseUrl; }

    public Duration getConnectTimeout() { return connectTimeout; }
    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public int getMaxAttempts() { return maxAttempts; }
    public void setMaxAttempts(int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }
}
~~~

The Binder instantiates the bean and sets values via setters/property access. The object remains mutable after creation. This is convenient when rebinding is needed, though the object must be protected against arbitrary mutation in business logic.

### 2.2. Constructor Binding

Constructor binding passes bound values into the constructor:

~~~java
@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {
    private final URI baseUrl;
    private final Duration connectTimeout;
    private final int maxAttempts;

    public ClientProperties(
            URI baseUrl,
            Duration connectTimeout,
            int maxAttempts) {
        this.baseUrl = baseUrl;
        this.connectTimeout = connectTimeout;
        this.maxAttempts = maxAttempts;
    }

    public URI getBaseUrl() { return baseUrl; }
    public Duration getConnectTimeout() { return connectTimeout; }
    public int getMaxAttempts() { return maxAttempts; }
}
~~~

The object is constructed with its configuration values from the start. No setters are needed and fields can be `final`. Once created, the object cannot be updated via setter calls.

### 2.3. Comparison

| Criterion | JavaBean/Setter Binding | Constructor Binding |
| --- | --- | --- |
| Instantiation | Typically uses a no-arg constructor. | Invokes a parameterized constructor. |
| Value assignment | Setter/property access. | Passes values as constructor arguments. |
| Mutability | Typically mutable. | Can be immutable. |
| Defaults | Field initializers or initialization logic. | `@DefaultValue` or supplied values. |
| Validation | Can be validated after binding. | Validated after constructor binding completes. |
| Spring Cloud refresh | Can be rebound if supported bean type. | Constructor-bound properties are not rebound directly. |
| Best suited for | Configuration needing runtime updates. | Immutable configuration, application-lifecycle snapshots. |

No single binding style is best for every case. Choose based on configuration lifecycle: if values only change on deploy, immutable configuration is usually simpler; if runtime changes are required, design specifically for the update mechanism.

## 3. Constructor Binding in Spring Boot

### 3.1. When Does Spring Boot Choose a Constructor?

In modern Spring Boot versions:

- A class with a single parameterized constructor is typically inferred as constructor binding.
- Java records have a canonical constructor; if the record declares no other constructor, `@ConstructorBinding` is generally unnecessary.
- If a class has multiple constructors, mark the target constructor with `@ConstructorBinding`.
- Constructor binding applies only to configuration-properties types registered via `@EnableConfigurationProperties` or `@ConfigurationPropertiesScan`.
- Do not use constructor binding for beans created via standard Spring mechanisms such as `@Component`, `@Bean` methods, or `@Import`.

In Spring Boot 3.x, `@ConstructorBinding` is used when a constructor must be specified explicitly and lives in package:

~~~java
import org.springframework.boot.context.properties.bind.ConstructorBinding;
~~~

You do not need to add this annotation to every record. When reading Spring Boot 2.x docs or upgrading from older versions, verify the annotation's package and target rules for your specific version, as the constructor binding API evolved across generations.

### 3.2. Registering Configuration Properties

There are two common ways.

**Scanning configuration classes:**

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

**Explicit registration:**

~~~java
@SpringBootApplication
@EnableConfigurationProperties(ClientProperties.class)
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Pick the approach that fits your application structure. Never annotate a constructor-bound class with `@Component` just so Spring discovers it; registering through the configuration properties mechanism is part of the binding contract.

### 3.3. Constructor Parameter Names

The Binder needs parameter names to map properties. When using constructor binding, the project must preserve parameter names in bytecode via the `-parameters` compiler flag.

The Spring Boot Gradle plugin and Maven Spring Boot parent configure this properly in standard projects. If using a custom build, verify compiler options. When parameter names are missing, binding may fail to work as expected or error out on startup.

## 4. Java Records for Immutable Configuration

### 4.1. Basic Record

Java records fit well when a group of properties represents descriptive data that should be fully initialized and immutable after creation.

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        URI baseUrl,
        Duration connectTimeout,
        int maxAttempts
) {
}
~~~

With configuration:

~~~yaml
app:
  client:
    base-url: https://inventory.internal
    connect-timeout: 750ms
    max-attempts: 3
~~~

Spring Boot binds `base-url` to component `baseUrl`, `connect-timeout` to `Duration connectTimeout`, and `max-attempts` to `int maxAttempts`. The record automatically generates accessors matching component names, such as `baseUrl()` and `connectTimeout()`.

### 4.2. Nested Records

Configuration can be grouped:

~~~yaml
app:
  client:
    base-url: https://inventory.internal
    connect-timeout: 750ms
    security:
      enabled: true
      username: order-reader
      roles:
        - INVENTORY_READ
        - STOCK_CHECK
~~~

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        URI baseUrl,
        Duration connectTimeout,
        Security security
) {
    public record Security(
            boolean enabled,
            String username,
            List<String> roles
    ) {
    }
}
~~~

Nested members of a constructor-bound class are also bound via their constructors. The Java structure mirrors the YAML structure and scopes properties cleanly.

### 4.3. Do Not Add Setters to Records

Records are designed to model immutable data. Components live in `final` fields and expose only accessors. You cannot add regular setters to mutate components after creation.

If configuration must change continuously without recreating the object, a record is not the right choice for a rebound configuration-properties bean.

## 5. DefaultValue and Default Values

### 5.1. DefaultValue on Record Components

Spring Boot provides `@DefaultValue` for constructor binding:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        @DefaultValue("https://localhost:8443") URI baseUrl,
        @DefaultValue("750ms") Duration connectTimeout,
        @DefaultValue("3") int maxAttempts
) {
}
~~~

If a property is not supplied, the Binder uses the annotation's default value and converts it to the target type. Spring Boot's conversion service handles converting `750ms` to `Duration`.

`@DefaultValue` applies when a property is absent. If a property is present with an empty or malformed value, the outcome depends on the target type and conversion rules; do not assume an empty value is equivalent to an omitted property.

### 5.2. Instantiating Nested Objects When Properties Are Absent

If no properties exist under `security`, the `security` component can be `null`. To ensure a child object is always created, use an empty `@DefaultValue`:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        URI baseUrl,
        @DefaultValue Security security
) {
    public record Security(
            String username,
            @DefaultValue("USER") List<String> roles
    ) {
    }
}
~~~

An empty `@DefaultValue` on the `security` parameter instructs the Binder to instantiate the nested object even when no properties exist for that group. Unset inner components must still be handled according to the application's nullability/validation rules.

### 5.3. DefaultValue Does Not Replace Validation

Defaults supply values when missing; validation rejects invalid values. The two mechanisms serve different goals.

~~~java
@ConfigurationProperties(prefix = "app.client")
@Validated
public record ClientProperties(
        @NotNull URI baseUrl,
        @DefaultValue("750ms") Duration connectTimeout,
        @Min(1) @DefaultValue("3") int maxAttempts
) {
}
~~~

- If `baseUrl` is required yet missing, validation causes the application to fail fast.
- `connectTimeout` defaults to `750ms`.
- `maxAttempts` defaults to `3` and must be greater than or equal to `1`.

To use Jakarta Bean Validation on Spring Boot 3, include a compatible validation dependency, typically `spring-boot-starter-validation`. For nested objects, place `@Valid` on the nested component if cascading validation is needed.

### 5.4. Avoid Optional for Configuration Properties

Avoid using `Optional<T>` as a field or constructor parameter type in `@ConfigurationProperties` to represent optional properties. `Optional` is primarily designed for return types. For configuration, use an appropriate nullable type, a default value, or a child object with explicit state.

If a property is required, use `@NotNull`; if it has a default, use `@DefaultValue`.

## 6. Type Conversion and Relaxed Binding

### 6.1. Common Data Types

| Java Type | Example Property | Value After Binding |
| --- | --- | --- |
| `Duration` | `connect-timeout: 750ms` | 750-millisecond duration. |
| `DataSize` | `max-payload: 10MB` | 10 MB data size. |
| `URI` / `URL` | `base-url: https://api.internal` | Endpoint address. |
| `InetAddress` | `remote-address: 10.0.0.10` | IP/host address. |
| `boolean` | `enabled: true` | On/off flag. |
| `int` / `long` | `max-attempts: 3` | Integer. |
| `enum` | `strategy: ROUND_ROBIN` | Matching enum constant. |
| `List<T>` | `regions: [ap-southeast, ap-northeast]` | Element list. |
| `Map<K,V>` | `weights.region-a: 70` | Key/value map. |

For durations and data sizes, use explicit unit suffixes to prevent misunderstandings. If a different default unit is needed, use the relevant annotations or configure conversion as required.

### 6.2. Relaxed Binding

YAML property names typically use kebab-case:

~~~yaml
app:
  client:
    connect-timeout: 750ms
    max-attempts: 3
~~~

Java component names use camelCase:

~~~java
Duration connectTimeout;
int maxAttempts;
~~~

The Binder supports relaxed binding to map compatible name forms. When referencing properties via `@Value`, prefer canonical lowercase hyphenated names to avoid discrepancies across sources.

### 6.3. Enums and Invalid Values

~~~java
public enum RoutingStrategy {
    ROUND_ROBIN,
    RANDOM,
    WEIGHTED
}
~~~

~~~yaml
app:
  routing:
    strategy: WEIGHTED
~~~

If configuration specifies `WEIGHT` instead of a valid enum constant, the Binder throws a conversion/binding error. This is desirable for critical settings because the application fails fast instead of running with an unknown strategy.

## 7. Validation and Fail-Fast at Startup

### 7.1. Why Is Validation Needed?

Configuration is application input. If a value is wrong, errors might surface late when real requests are processed. Validating during binding catches misconfiguration at startup.

~~~java
@ConfigurationProperties(prefix = "app.routing")
@Validated
public record RoutingProperties(
        @NotNull RoutingStrategy strategy,
        @Min(1) @Max(100) int maxConcurrentRequests,
        @NotNull Duration requestTimeout
) {
}
~~~

~~~yaml
app:
  routing:
    strategy: ROUND_ROBIN
    max-concurrent-requests: 50
    request-timeout: 800ms
~~~

If `max-concurrent-requests` is 0 or exceeds 100, validation fails and the application fails to start.

### 7.2. Nested Validation

~~~java
@ConfigurationProperties(prefix = "app.client")
@Validated
public record ClientProperties(
        @NotNull URI baseUrl,
        @Valid Security security
) {
    public record Security(
            @NotBlank String username,
            @NotBlank String credential
    ) {
    }
}
~~~

`@Valid` enables validation inside the nested object. If `security` is optional, decide explicitly whether `null` is valid; if not, combine `@NotNull` with `@Valid`.

Never log credentials when validation fails. Error messages should state the property name and constraint type without printing secret values.

### 7.3. Validation vs. Conversion

- **Conversion:** transforms configuration strings into Java types, e.g., `750ms` into `Duration`.
- **Validation:** checks whether bound values satisfy rules, e.g., timeout must be positive.
- **Business validation:** checks relationships across values or conditions tied to system state.

Not every business rule belongs in validation annotations. Checks requiring database, registry, or remote service access belong in the appropriate stage of the application lifecycle.

## 8. Constructor Binding and Spring Cloud Refresh Limitations

### 8.1. Why Do Records Not Auto-Update?

~~~java
@ConfigurationProperties(prefix = "app.routing")
public record RoutingProperties(
        String strategy,
        int maxAttempts
) {
}
~~~

When the Binder constructs the object, it invokes the constructor with current values. Components are stored in `final` fields. If the Environment later receives new values, the existing record instance still holds the old values.

There are no setters to rebind individual fields. Spring Cloud Context cannot update constructor-bound configuration properties directly via standard rebinding.

### 8.2. How Does Spring Cloud Context Rebind Mutable Beans?

For mutable JavaBeans registered as `@ConfigurationProperties`, Spring Cloud Context can handle `EnvironmentChangeEvent` and rebind the bean after the Environment changes.

In essence, rebinding updates properties on the existing bean instance rather than creating a new object. This implies:

- Fields are mutated in place on the same instance.
- Concurrent readers may observe intermediate states while multiple fields are being updated.
- Collections may briefly become empty during rebinding before new elements are populated, depending on collection type and Binder behavior.
- Rebinding does not automatically update other singleton beans that already cached values from the configuration bean.

If configuration must stay consistent as an atomic snapshot, Spring Cloud recommends considering `@RefreshScope` on an appropriate bean instead of letting multiple threads read a mutable configuration object mid-update.

### 8.3. Constructor-Bound Configuration Properties Are Not Refreshed

Current Spring Cloud Context explicitly establishes that **constructor-bound objects, including Java records annotated with `@ConfigurationProperties`, cannot be refreshed/rebound directly**.

This does not mean records cannot be used in Spring Cloud applications. They remain well-suited for immutable configuration read at startup. The limitation appears only when expecting the constructor-bound bean itself to update after Environment changes.

### 8.4. Comparison Table

| Bean Type | On Environment Change and Refresh | Outcome |
| --- | --- | --- |
| Regular singleton with `@Value` | Not re-injected automatically. | Fields typically hold the old snapshot. |
| Mutable `@ConfigurationProperties` | Can be rebound via `EnvironmentChangeEvent`. | Fields are updated on the existing bean. |
| Constructor-bound class | Not rebound directly. | Existing object keeps old values. |
| Java record `@ConfigurationProperties` | Not rebound directly. | Record remains an immutable snapshot. |
| Suitable `@RefreshScope` bean | Target cache is invalidated; next call creates a new target. | New target receives current config if dependencies/sources are wired properly. |

## 9. Choosing a Strategy When Runtime Configuration Changes Are Needed

There are three main approaches. Choose based on consistency requirements, lifecycle, and blast radius of changes.

### 9.1. Strategy A: Instance Restart or Rollout

If configuration only changes on deployment, use immutable records and restart instances when applying new values.

Advantages:
- Simple, immutable objects.
- No torn or half-updated state during rebinding.
- Easy to test configuration at startup.
- Reproducible from the same artifact and config revision.

This is usually the most predictable choice for ports, listeners, foundational endpoints, or startup resource configuration.

### 9.2. Strategy B: Mutable @ConfigurationProperties

If values must update at runtime and do not require atomic multi-field replacement, use JavaBean configuration properties:

~~~java
@ConfigurationProperties(prefix = "app.routing")
public class RoutingProperties {
    private String strategy = "ROUND_ROBIN";
    private int maxAttempts = 3;

    public String getStrategy() { return strategy; }
    public void setStrategy(String strategy) { this.strategy = strategy; }

    public int getMaxAttempts() { return maxAttempts; }
    public void setMaxAttempts(int maxAttempts) { this.maxAttempts = maxAttempts; }
}
~~~

This bean can be rebound when Spring Cloud Context emits the appropriate events. Manage concurrency carefully if requests read multiple interrelated properties.

### 9.3. Strategy C: Refresh-Scoped Snapshot

If you want immutable configuration objects yet need the entire object recreated on refresh, design a **refresh-scoped bean factory/holder** that builds a fresh snapshot from the current Environment. Do not treat a constructor-bound record registered directly via `@ConfigurationProperties` as refreshable.

~~~mermaid
flowchart TD
    ENV["Updated Environment"] --> FACTORY["Refresh-scoped snapshot factory"]
    FACTORY --> TARGET["Immutable configuration snapshot"]
    CALLER["Service caller"] --> PROXY["Refresh-scoped proxy"]
    PROXY --> TARGET
    REFRESH["Refresh event"] --> INVALIDATE["Invalidate target cache"]
    INVALIDATE --> PROXY
    PROXY --> NEW["Next call creates a new snapshot"]
~~~

This fits well when multiple fields must change atomically, the bean must remain immutable after creation, and the application controls how objects are reconstructed.

## 10. Example Factory Creating Immutable Snapshots

The following example illustrates the idea: a refresh-scoped bean constructs a record from `Environment` whenever a target is initialized. This is an application-managed object; **do not register this record as a constructor-bound `@ConfigurationProperties` bean**.

Record:

~~~java
public record RoutingSnapshot(
        RoutingStrategy strategy,
        int maxAttempts,
        Duration requestTimeout
) {
}
~~~

Factory bean:

~~~java
@Component
@RefreshScope
public class RoutingSnapshotProvider {

    private final RoutingSnapshot snapshot;

    public RoutingSnapshotProvider(Environment environment) {
        Binder binder = Binder.get(environment);

        this.snapshot = binder.bind(
            "app.routing",
            Bindable.of(RoutingSnapshot.class)
        ).orElseThrow(() ->
            new IllegalStateException("Missing app.routing configuration")
        );
    }

    public RoutingSnapshot current() {
        return snapshot;
    }
}
~~~

Caller:

~~~java
@Service
public class RoutingService {

    private final RoutingSnapshotProvider snapshotProvider;

    public RoutingService(RoutingSnapshotProvider snapshotProvider) {
        this.snapshotProvider = snapshotProvider;
    }

    public RoutingDecision decide() {
        RoutingSnapshot config = snapshotProvider.current();
        return calculate(config);
    }
}
~~~

In this example:
- `RoutingSnapshotProvider` is a refresh-scoped bean/proxy.
- When refresh scope invalidates the target, the next `current()` call creates a new provider.
- The provider constructor uses `Binder` to read the current `Environment` and build a new record.
- `RoutingService` holds the proxy provider, not a direct reference to the old snapshot.
- Each request should fetch the snapshot once and reuse it throughout the operation to avoid observing multiple revisions in the same request.

Required imports include Spring `Environment`, `Binder`, `Bindable`, Spring Cloud `@RefreshScope`, and domain types. Exact `Binder` API details can vary across Spring Boot versions; verify how `Binder` is constructed in your project's version. Also add validation/data checks before using the snapshot and handle errors if the new target fails to initialize.

## 11. Testing Constructor Binding and Records

### 11.1. Standalone Binder Test

You can use `Binder` and `MapConfigurationPropertySource` to test binding without booting the full application:

~~~java
@Test
void bindsRecordFromConfigurationProperties() {
    MapConfigurationPropertySource source =
        new MapConfigurationPropertySource(Map.of(
            "app.client.base-url", "https://inventory.internal",
            "app.client.connect-timeout", "750ms",
            "app.client.max-attempts", "4"
        ));

    ClientProperties properties = new Binder(source)
        .bind("app.client", Bindable.of(ClientProperties.class))
        .orElseThrow();

    assertEquals(
        URI.create("https://inventory.internal"),
        properties.baseUrl()
    );
    assertEquals(Duration.ofMillis(750), properties.connectTimeout());
    assertEquals(4, properties.maxAttempts());
}
~~~

This test verifies that the Binder converts properties into the record. It does not test component scanning, ApplicationContext validation, refresh, or Config Server.

### 11.2. Testing Default Values

~~~java
@Test
void usesDefaultsWhenPropertiesAreMissing() {
    MapConfigurationPropertySource source =
        new MapConfigurationPropertySource(Map.of(
            "app.client.base-url", "https://inventory.internal"
        ));

    ClientProperties properties = new Binder(source)
        .bind("app.client", Bindable.of(ClientProperties.class))
        .orElseThrow();

    assertEquals(Duration.ofMillis(750), properties.connectTimeout());
    assertEquals(3, properties.maxAttempts());
}
~~~

Ensure the record under test declares matching `@DefaultValue` annotations. Without defaults on optional properties, values may be null or primitive defaults depending on type; tests should reflect the real contract.

### 11.3. Testing Validation via ApplicationContext

To verify `@Validated`, create a test context registering the configuration properties with the validation dependency present. Test both valid configs and constraint-violating configs. For required configurations, expect context startup to fail with an exception identifying the offending property/constraint.

### 11.4. Testing Refresh Limitations

Write dedicated integration tests for these scenarios:

1. Start the context with property A and create the constructor-bound record.
2. Update the configuration source to B.
3. Trigger Spring Cloud Context's refresh process.
4. Verify `Environment` holds value B.
5. Verify the existing constructor-bound record still holds A.
6. If a mutable configuration bean exists, verify it was rebound via the supported mechanism.
7. If a refresh-scoped snapshot provider exists, verify a new target reads B after cache invalidation.
8. Verify singletons do not directly cache an old snapshot when expected to use the new one.

Never write a test that only checks `Environment` and concludes every bean updated.

## 12. Common Issues

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Record not created as a bean. | Not registered via configuration properties scan/enable. | Use `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`. |
| Constructor binding cannot find parameters. | Compiler did not retain parameter names. | Enable `-parameters` and check Maven/Gradle plugins. |
| Binder picks unintended constructor. | Class has multiple constructors without marking constructor binding. | Place `@ConstructorBinding` from your version's package/target. |
| `@ConstructorBinding` errors when placed on a component. | Annotation misplaced or API version mismatch. | Check Boot version docs; single-canonical-constructor records usually omit it. |
| `@ConfigurationProperties` fails to bind nested properties. | Wrong prefix, property name, or nested structure. | Inspect YAML, record components, and Binder diagnostics. |
| Default values do not appear. | Missing `@DefaultValue` or property supplied with invalid value. | Check property sources and missing vs. blank semantics. |
| Validation does not run. | Missing validation starter, `@Validated`, or `@Valid` cascade. | Check dependencies and annotations on nested properties. |
| Record still holds old values after refresh. | Constructor-bound properties are not rebound by Spring Cloud. | Use restart, mutable bean, or refresh-scoped snapshot factory. |
| Mutable config shows intermediate state. | Rebind mutates object in place while another thread reads it. | Use immutable snapshots or an appropriate refresh scope. |
| Refresh-scoped provider still returns old config. | Factory injected an old singleton record or caller cached snapshot. | Read Environment/Binder when new target initializes and hold only proxy in callers. |
| App boots despite invalid configuration. | Missing validation or default hiding missing properties. | Add constraints and fail-fast tests. |

## 13. Guidelines for Choosing a Configuration Model

| Need | Recommended Option | Reason |
| --- | --- | --- |
| Config changes only on deploy | Constructor binding / Java record | Immutable, easy to test and reproduce. |
| Config needs per-property rebinding | Mutable `@ConfigurationProperties` | Supports bean updates via Spring Cloud Context. |
| Need a group of values updated as a snapshot | Refresh-scoped snapshot/provider | Recreates target and provides a consistent object. |
| Config creates infrastructure resources | Evaluate restart/rollout or custom refresh lifecycle | Requires closing/reopening resources safely. |
| Secret configuration | Secret manager and controlled typed binding | Limits exposure and supports rotation. |

Do not pick records solely for concise syntax. Identify who owns the configuration lifecycle, when it changes, which beans must receive updates, and how to verify all instances run the same revision.

## 14. Completion Checklist

- [ ] Can distinguish JavaBean binding from constructor binding.
- [ ] Can create a configuration class with a constructor and `final` fields.
- [ ] Can use Java records with `@ConfigurationProperties`.
- [ ] Can register records using `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`.
- [ ] Know when `@ConstructorBinding` is required and its package per Boot version.
- [ ] Ensure the compiler retains constructor parameter names.
- [ ] Can use `@DefaultValue` for scalars and nested objects.
- [ ] Can use type conversion for Duration, DataSize, URI, enums, and collections.
- [ ] Combine `@Validated`, constraints, and `@Valid`.
- [ ] Understand why constructor-bound/record configuration is not rebound by Spring Cloud Context.
- [ ] Distinguish Environment updates from recreating configuration objects.
- [ ] Choose restarts, mutable properties, or refresh-scoped snapshots based on requirements.
- [ ] Have tests for binding, defaults, validation, and refresh limitations.
- [ ] Have policies for secrets, revisions, and cross-instance configuration consistency.

**Official references to verify against your project's version:**

- [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): `@ConfigurationProperties`, constructor binding, Java records, `@DefaultValue`, validation, and parameter names.
- [Spring Cloud Commons – Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html): Environment changes, rebinding, refresh scope, and limitations of constructor-bound objects.
- [Spring Boot – Validation](https://docs.spring.io/spring-boot/reference/io/validation.html): Bean Validation integration and fail-fast configuration binding.

Constructor binding, annotation packages, and refresh behavior can differ across Spring Boot/Spring Cloud generations. Check the compatibility matrix and release-train documentation before applying examples in production.
