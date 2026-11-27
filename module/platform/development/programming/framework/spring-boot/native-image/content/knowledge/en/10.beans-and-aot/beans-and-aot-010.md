# Keeping Initialization Code Safe and Independent of External Services During Build Analysis

Spring AOT analyzes the Spring application structure at **build time** to generate initialization code and runtime hints for GraalVM Native Image. Therefore, the build process must be repeatable, predictable, and independent of whether a database, Kafka, Redis, Config Server, or external API is currently running.

It is important to understand accurately **which parts of Spring actually run during AOT**. AOT refresh typically creates and processes bean definitions without instantiating every application bean. Even so, callbacks involved in building the context structure still execute; beans acting as AOT processors along with their dependencies can also be instantiated right during analysis. If those code paths call external services, the build can fail, slow down, become non-reproducible, or accidentally depend on environment credentials.

This lesson helps identify that boundary, design safe initialization code, defer integration activity to runtime, and verify the application with Spring AOT tasks.

## 1. What does AOT do at build time?

Spring AOT inspects an `ApplicationContext` during the build to prepare the application structure that Spring would normally discover at runtime. This process can:

- Analyze configuration classes, component scans, and `@Bean` declarations.
- Process `ImportSelector`, `ImportBeanDefinitionRegistrar`, and callbacks related to configuration registration.
- Invoke `BeanFactoryPostProcessor` and `BeanDefinitionRegistryPostProcessor` to finalize the set of bean definitions.
- Evaluate `@Profile` and `@Conditional` conditions based on the classpath and `Environment` of the build run.
- Analyze bean types, injection points, lifecycle callbacks, and metadata needed for code generation.
- Invoke AOT contributors to produce source code, bytecode, and runtime hints.

In Spring Framework, `refreshForAotProcessing` behaves differently from a regular `ApplicationContext.refresh()`: it prepares the bean factory and bean definitions without instantiating regular application beans. Specialized post-processors required for AOT are still processed to determine structure and bean types.

~~~mermaid
flowchart TD
    A["processAot starts"] --> B["Read configuration and Environment"]
    B --> C["Analyze @Configuration, imports, scan"]
    C --> D["Run conditions and BeanFactoryPostProcessors"]
    D --> E["Complete BeanDefinition set"]
    E --> F["AOT processors contribute code and hints"]
    F --> G["Generate sources, bytecode, RuntimeHints"]
    G --> H["Native Image compiler"]
    H --> I["Native executable"]
    J["Database, Kafka, external API"] -. "Should not be a build prerequisite" .-> D
~~~

**AOT is a structural analysis step, not a full business execution run.** This is the basis for deciding which code needs to be build-safe.

## 2. Distinguishing callbacks running during AOT from runtime bean lifecycle

Do not assume every constructor, `@PostConstruct`, or `@Bean` factory method is invoked when running `processAot`. Spring AOT normally does not instantiate all application bean instances. However, certain callbacks genuinely run at build time.

| Component | Can run during AOT? | Responsibility |
|---|---|---|
| `BeanDefinitionRegistryPostProcessor` | Yes | Register or adjust bean definitions |
| `BeanFactoryPostProcessor` | Yes | Adjust bean factory metadata |
| `ImportSelector` / `DeferredImportSelector` | Yes | Select imported configurations |
| `ImportBeanDefinitionRegistrar` | Yes | Register bean definitions from metadata |
| `Condition.matches()` | Yes | Decide configuration conditions |
| `BeanFactoryInitializationAotProcessor` | Yes; processor instance and its dependencies are instantiated | Contribute initialization code for the bean factory |
| `BeanRegistrationAotProcessor` | Yes; processor instance and its dependencies are instantiated | Contribute registration logic for individual beans |
| Constructor of a regular application bean | Not during standard AOT refresh | Create instance when the runtime container needs the bean |
| `@PostConstruct`, `InitializingBean`, `initMethod` of regular beans | Not during standard AOT refresh | Lifecycle callback when the bean is actually created at runtime |
| `ApplicationRunner`, `CommandLineRunner` | Not an AOT refresh callback | Run when the Spring Boot application starts at runtime |

Two cases to remember:

1. **Regular application beans:** Spring AOT typically describes how to create the bean and generates an instance supplier. Constructors and lifecycle callbacks execute when the native executable starts and the container creates the bean.
2. **Beans acting as AOT processors:** processors must be invoked right at build time. If a processor is declared as a bean, Spring must instantiate the processor and its dependencies to obtain the AOT contribution.

Therefore, you do not need to remove `@PostConstruct` from every bean just because you use Native Image. Determine which phase that code runs in and whether it depends on external services during that phase.

## 3. Code paths that can accidentally call external services

Some code looks like configuration yet actually performs I/O or business logic:

- `Condition.matches()` sends an HTTP request to Config Server to decide whether to enable a feature.
- `ImportSelector.selectImports()` queries a database to find a list of modules to import.
- `BeanFactoryPostProcessor` calls `dataSource.getConnection()` to inspect the schema.
- `ImportBeanDefinitionRegistrar` reads an external service registry to create bean definitions.
- An AOT processor calls a cloud API to fetch a list of buckets, queues, or secrets.
- A constructor or static initializer of an AOT processor creates a client and connects immediately.
- An `EnvironmentPostProcessor` or Config Data loading mechanism configured to reach a remote config source while AOT runs.

These paths make the build depend on external state. A single slow endpoint, DNS failure, expired credential, or blocked CI network can cause AOT processing to fail.

### Example of an unsafe configuration condition

~~~java
public class RemoteFeatureCondition implements Condition {

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        // Unsafe: build condition depends on an HTTP service.
        try {
            URI uri = URI.create("https://feature.example.internal/enabled");
            HttpURLConnection connection =
                (HttpURLConnection) uri.toURL().openConnection();
            connection.setConnectTimeout(2_000);
            connection.setReadTimeout(2_000);

            return connection.getResponseCode() == 200;
        }
        catch (IOException ex) {
            throw new IllegalStateException(
                "Cannot determine feature availability", ex);
        }
    }
}
~~~

`Condition.matches()` is invoked while Spring analyzes configuration. Thus the code above can cause `processAot` to access the network. It also makes build results vary with service state, causing the same commit to produce different bean sets.

## 4. Build conditions should rely on stable metadata

Configuration conditions should rely on data known and controllable at build time, such as:

- Properties explicitly provided in the AOT environment.
- Spring profiles selected for the artifact.
- Whether the classpath contains the required library or class.
- Whether another bean definition is already registered.
- Static metadata in source or resources belonging to build inputs.

Safer condition example:

~~~java
public class RemoteFeatureCondition implements Condition {

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        Environment environment = context.getEnvironment();

        // Read property only, do not call external services.
        return environment.getProperty(
            "features.remote.enabled",
            Boolean.class,
            false
        );
    }
}
~~~

Configuration declaration:

~~~java
@Configuration(proxyBeanMethods = false)
@Conditional(RemoteFeatureCondition.class)
class RemoteFeatureConfiguration {

    @Bean
    RemoteFeatureClient remoteFeatureClient(
            RemoteFeatureProperties properties) {
        return new RemoteFeatureClient(properties);
    }
}
~~~

This example assumes `RemoteFeatureProperties` is bound from configuration. `RemoteFeatureClient` must also be designed so object creation does not automatically open connections. The condition decides **whether to register the bean** using a build-time value; the client only performs I/O when requested at runtime.

Note: properties used in conditions affect the image's bean set. When using AOT, provide that value in the build environment. Changing the property at runtime does not automatically re-add a bean excluded from the AOT structure.

## 5. Do not perform I/O in BeanFactoryPostProcessor

`BeanFactoryPostProcessor` is invoked during bean factory preparation, including AOT refresh. Its role is to adjust metadata and bean definitions, not to start business workflows or health-check external systems.

Unsafe example:

~~~java
@Component
class SchemaCheckingPostProcessor
        implements BeanFactoryPostProcessor {

    private final DataSource dataSource;

    SchemaCheckingPostProcessor(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    @Override
    public void postProcessBeanFactory(
            ConfigurableListableBeanFactory beanFactory) {

        // Unsafe: may open a connection during AOT processing.
        try (Connection connection = dataSource.getConnection()) {
            // Read schema to decide bean registration.
        }
        catch (SQLException ex) {
            throw new IllegalStateException(ex);
        }
    }
}
~~~

This snippet also creates an unclear lifecycle dependency: the processor requires `DataSource` and opens a connection while the bean factory is being prepared. The build is no longer purely metadata analysis.

A post-processor registered as a bean is also instantiated early by Spring to run its callback. Therefore, the processor's own constructor and dependencies must be lightweight and safe; inject only essential infrastructure components such as `Environment`, `ResourceLoader`, or pre-prepared metadata.

A more appropriate design uses properties or supplied metadata:

~~~java
@Component
class FeatureBeanDefinitions
        implements BeanDefinitionRegistryPostProcessor {

    private final Environment environment;

    FeatureBeanDefinitions(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void postProcessBeanDefinitionRegistry(
            BeanDefinitionRegistry registry) {

        boolean enabled = environment.getProperty(
            "features.audit.enabled",
            Boolean.class,
            false
        );

        if (enabled && !registry.containsBeanDefinition("auditService")) {
            RootBeanDefinition definition =
                new RootBeanDefinition(AuditService.class);
            registry.registerBeanDefinition("auditService", definition);
        }
    }

    @Override
    public void postProcessBeanFactory(
            ConfigurableListableBeanFactory beanFactory) {
        // Do not connect to databases, brokers, or external APIs.
    }
}
~~~

The example above illustrates registering a bean definition based on `Environment`. For typical Spring applications, prefer `@Configuration`, `@Bean`, `@ConditionalOnProperty`, or `ImportBeanDefinitionRegistrar` when configuration-driven registration is needed; write a custom post-processor only when container-level intervention is genuinely required.

## 6. AOT processors must have small, safe dependencies

Spring supports extension points such as:

- `BeanFactoryInitializationAotProcessor`: contributes code to restore bean factory state.
- `BeanRegistrationAotProcessor`: contributes handling for individual bean definitions.

If a bean implements these interfaces, **the processor and all of its dependencies are instantiated during AOT**. This is easily overlooked when a business service is injected into a processor.

Configuration example to avoid:

~~~java
@Configuration
class NativeConfiguration {

    @Bean
    BeanFactoryInitializationAotProcessor featureProcessor(
            RemoteFeatureAdminClient remoteClient) {

        // Creating the processor can pull remoteClient into build time.
        return beanFactory -> {
            remoteClient.fetchFeatureCatalog();
            return null;
        };
    }
}
~~~

This example illustrates a dangerous dependency path, not a complete implementation. The factory method creating the processor is called to obtain the processor instance; the processor's dependencies must also be instantiated. If `RemoteFeatureAdminClient` connects in its constructor or in the method invoked when creating the contribution, the build becomes network-dependent.

If an AOT processor is needed, keep its dependencies at the infrastructure level: read bean definitions, metadata, classpath, or properties; generate code and runtime hints from that data. Do not inject business services that perform I/O.

When declaring a processor with `@Bean`, use a `static` factory method when appropriate so Spring does not have to instantiate the enclosing `@Configuration` class just to create the processor:

~~~java
@Configuration(proxyBeanMethods = false)
class NativeAotConfiguration {

    @Bean
    static FeatureHintsProcessor featureHintsProcessor() {
        return new FeatureHintsProcessor();
    }
}
~~~

`FeatureHintsProcessor` in this example is an application-implemented infrastructure class; it and its dependencies must still be safe when running inside AOT.

## 7. Separating client creation from service connection

A client object can be constructed without connecting yet. Keep constructors limited to assigning configuration and preparing local components; only open connections when an operation actually requires them.

Avoid:

~~~java
public class InventoryClient {

    private final InventoryApi api;

    public InventoryClient(URI endpoint) {
        this.api = createApi(endpoint);

        // Avoid: constructor makes a network call on its own.
        this.api.healthCheck();
    }
}
~~~

Better design:

~~~java
public class InventoryClient {

    private final InventoryApi api;

    public InventoryClient(URI endpoint) {
        // Create only the local client/configuration.
        this.api = createApi(endpoint);
    }

    public InventoryItem findItem(String itemId) {
        // Make the network call only when business logic actually needs it.
        return this.api.findItem(itemId);
    }
}
~~~

Register with Spring:

~~~java
@Configuration(proxyBeanMethods = false)
class InventoryConfiguration {

    @Bean
    InventoryClient inventoryClient(InventoryProperties properties) {
        return new InventoryClient(properties.endpoint());
    }
}
~~~

AOT can describe the bean and its instantiation path. When the native application runs and a bean needs `InventoryClient`, the constructor only builds the local client structure. Network calls happen when `findItem()` is invoked at runtime.

With HTTP, JDBC, or messaging libraries, check the specific APIs: some factories spawn threads, perform DNS lookups, create pools, or open connections immediately upon creation. Do not look only at a method name like `build()` or `create()` and assume it performs no I/O; verify the library's actual behavior.

## 8. Distinguishing constructors, @PostConstruct, and AOT callbacks

A regular bean may use constructor injection, `@PostConstruct`, `InitializingBean`, or `initMethod`. These lifecycle callbacks belong to **actual bean creation**. Since AOT refresh does not instantiate regular application beans, they are not where Spring runs general business logic during `processAot`.

However, avoid two faulty lines of reasoning:

- Do not conclude that no constructor code can run during the build. Constructors of AOT processors and their dependencies can run; static initializers can also run when classes are initialized along build paths.
- Do not conclude `@PostConstruct` can freely call external services without affecting the system. When the native executable starts, that callback still executes and can prevent the application from becoming ready if an external service is temporarily down.

Example of a runtime lifecycle callback:

~~~java
@Component
class StartupReporter {

    @PostConstruct
    void initialize() {
        // This callback runs when the bean is created at runtime.
        // Perform only local, fast, deterministic work.
    }
}
~~~

If business requirements involve checking external services, separate that into a runtime operation with explicit timeouts, retries, observability, and error policies. For services not strictly required at startup, connect on demand rather than blocking overall startup.

## 9. Avoiding static initializers with side effects

Static initializers can run when a class is initialized. If that class is used by a condition, registrar, or AOT processor during the build, the side effect occurs inside the build process.

Avoid:

~~~java
final class RemoteSchemaRegistry {

    static final Map<String, String> SCHEMAS = loadFromRemoteRegistry();

    private static Map<String, String> loadFromRemoteRegistry() {
        // Unsafe: static initialization may invoke the network.
        return RemoteRegistryClient.fetchSchemas();
    }
}
~~~

Replace with local data, or create a bean/service and perform access at runtime:

~~~java
final class LocalSchemaCatalog {

    static final Map<String, String> SCHEMAS = Map.of(
        "order-v1", "schemas/order-v1.json",
        "order-v2", "schemas/order-v2.json"
    );

    private LocalSchemaCatalog() {
    }
}
~~~

Static initializers are suited for constants and small, deterministic local structures. Do not use them to read secrets, open network connections, probe cloud metadata, or query databases.

## 10. Handling remote configuration and secrets

Some applications load configuration from Config Server, Vault, or secret management systems. Depending on bootstrap setup and integration versions, AOT processing may trigger part of that configuration-loading logic. If the build has to call a remote service to decide the bean set, results depend on the network and the build agent's permissions.

Classify data clearly:

| Data | Appropriate usage |
|---|---|
| Feature flags deciding whether a bean is registered | Provide explicit build-time values for AOT |
| URLs and timeouts of registered services | Read from runtime configuration when the application runs |
| Database passwords, API tokens, private keys | Supply via secret manager/runtime platform; never embed in generated sources or native images |
| List of schemas requiring code generation | Store in versioned sources/resources or controlled build inputs |
| Current service status (healthy/unhealthy) | Check at runtime/health monitoring; never use to decide bean structure at build time |

Never write credentials into:

- Command-line arguments recorded in logs.
- AOT generated source or resource files.
- Native Image build arguments or committed config files.
- Java constants, static fields, or metadata packaged inside the executable.
- Build caches/artifacts that may be widely shared.

If remote configuration is needed for a build, produce a **versioned, controlled build input** (such as a secret-free config file, feature manifest, or schema snapshot) and let AOT analyze that data. Fetching from the service and taking the snapshot should be a separate, authenticated, change-controlled step performed prior to AOT; `processAot` itself does not need to call the service.

## 11. Using profiles and @Conditional intentionally

Spring AOT evaluates bean conditions at build time. Conditions such as `@Profile`, `@ConditionalOnProperty`, and custom `Condition`s affect which beans are included in the AOT structure.

Example:

~~~java
@Configuration(proxyBeanMethods = false)
class PaymentConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "payment",
        name = "provider",
        havingValue = "remote"
    )
    PaymentGateway remoteGateway(PaymentProperties properties) {
        return new RemotePaymentGateway(properties.endpoint());
    }

    @Bean
    @ConditionalOnProperty(
        prefix = "payment",
        name = "provider",
        havingValue = "local",
        matchIfMissing = true
    )
    PaymentGateway localGateway() {
        return new LocalPaymentGateway();
    }
}
~~~

When AOT runs with `payment.provider=remote`, the bean set is generated according to that condition. If you run the executable with `payment.provider=local`, do not expect the local bean to appear on its own if it was excluded from the AOT structure.

Therefore:

1. Select profiles/properties affecting bean definitions at the build step.
2. Record AOT environment values alongside the artifact.
3. Use runtime properties for values that do not alter the bean set.
4. If multiple bean structures are needed, consider building separate artifacts per configuration or designing all implementations to be present while selecting data/strategies at runtime.

**Do not use external service status as a `@Conditional` condition.** Status can change immediately after the build, leaving the generated artifact out of sync with the operational environment.

## 12. Registering dynamic beans using metadata instead of querying services

If an application needs to create beans from a list of plugins or integration types, make that list a build-time analyzable metadata input.

Example of a registrar that relies only on properties and registers bean definitions:

~~~java
public class ConnectorRegistrar
        implements ImportBeanDefinitionRegistrar, EnvironmentAware {

    private Environment environment;

    @Override
    public void setEnvironment(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void registerBeanDefinitions(
            AnnotationMetadata importingClassMetadata,
            BeanDefinitionRegistry registry) {

        boolean enabled = environment.getProperty(
            "connectors.http.enabled",
            Boolean.class,
            false
        );
        if (!enabled) {
            return;
        }

        RootBeanDefinition definition =
            new RootBeanDefinition(HttpConnector.class);
        definition.setAutowireMode(
            AbstractBeanDefinition.AUTOWIRE_CONSTRUCTOR
        );
        registry.registerBeanDefinition("httpConnector", definition);
    }
}
~~~

In this example, the registrar only reads a build-time property to decide whether to register the bean. `HttpConnector` can receive `ConnectorProperties` via constructor injection, with endpoint and timeout bound from runtime configuration. The client's constructor should not call APIs on its own. The registrar does not query an external registry to decide how many connectors exist.

If the connector list changes per tenant or external registry at runtime, consider a dedicated business registry model: a single bean manages runtime metadata and creates clients on demand. Do not turn every runtime connector into a bean definition that must be discovered during AOT if that set is not fixed at build time.

## 13. Keeping builds runnable when external services are unavailable

A healthy pipeline should be able to run AOT without a live database, message broker, or business API. This does not mean the build needs no network to download dependencies; Maven/Gradle may need repositories and caches. The point is that **AOT must not need to call the application's business services to analyze the bean structure**.

Practical measures:

- Cache Maven/Gradle dependencies and pin versions to reduce network reliance across repeated builds.
- Use a dedicated AOT configuration containing explicit profiles/properties that decide beans.
- Mock or replace external integrations in tests; never let custom conditions or processors make live queries.
- Provide schemas, OpenAPI specs, or feature manifests as versioned files/artifacts.
- Do not require a database to be running just to initialize the `ApplicationContext` for AOT.
- Separate the step that generates config artifacts from external systems into its own job with clear outputs.
- Inspect build logs to spot unexpected HTTP requests, DNS lookups, or JDBC connections.

If database schema checks are needed, run them in a migration job, integration test, or runtime health check. Do not use `processAot` as a migration runner or an environment status check step.

## 14. Running AOT to detect build-time side effects

With Gradle, the Spring Boot AOT plugin provides the `processAot` task. When the GraalVM Native Image plugin is applied under standard Spring Boot setups, the AOT plugin may be applied automatically.

~~~bash
# Process application AOT
./gradlew processAot

# After AOT succeeds, compile the native executable
./gradlew nativeCompile
~~~

If you want to select profiles affecting bean structure for AOT:

~~~groovy
import org.springframework.boot.gradle.tasks.aot.ProcessAot

tasks.withType(ProcessAot).configureEach {
    args("--spring.profiles.active=local,native")
}
~~~

This configuration illustrates passing arguments to the `ProcessAot` task. Choose profiles that actually exist in the project.

With Maven, the Spring Boot Maven plugin provides the `process-aot` goal. When using the `native` profile supplied by the Spring Boot parent, the AOT execution is typically configured inside that profile:

~~~bash
# Invoke the Spring Boot Maven plugin's AOT goal directly
./mvnw spring-boot:process-aot

# Or run the native profile configured in the project
./mvnw -Pnative package
~~~

If the project requires specific Spring profiles, configure `profiles` for the `process-aot` execution in `pom.xml`:

~~~xml
<execution>
    <id>process-aot</id>
    <goals>
        <goal>process-aot</goal>
    </goals>
    <configuration>
        <profiles>local,native</profiles>
    </configuration>
</execution>
~~~

Examples should be adjusted for your current Spring Boot version and plugin configuration. Not every project has a preconfigured `native` Maven profile; check `pom.xml` and plugin management.

### Inspecting AOT output

Generated sources typically reside in:

| Build tool | Common location |
|---|---|
| Gradle | `build/generated/aotSources` or the plugin's corresponding generated AOT directory |
| Maven | `target/spring-aot/main/sources` |

Exact paths depend on plugin versions and project configuration. Inspect `processAot`/`process-aot` logs, look for `__BeanDefinitions` classes, initializer code, and runtime hints files.

**Do not edit generated files directly.** Fix the source configuration, condition, or AOT processor, then rerun the task.

## 15. Testing independence from external services

A useful test is running AOT in an environment without access to business services. You can use CI network policies, an isolated container environment, or mock services.

Suggested procedure:

1. Use a fixed commit and toolchain.
2. Warm up the dependency cache so dependency downloads are not confused with business connections.
3. Disable or block access to databases, Kafka, Redis, Config Server, and business APIs.
4. Run `processAot`.
5. If it fails, identify which callback or processor attempted a network call.
6. After AOT succeeds, run native compilation.
7. Launch the executable in an integration test environment with the required mock services or test containers.
8. Test flows that genuinely require runtime connections.

Expected outcome: **AOT and native compilation do not require live business services; integration tests/runtime verify connection behavior**.

Results can be recorded as:

| Item | Environment | Expected outcome |
|---|---|---|
| `processAot` | No access to business services | Succeeds |
| `nativeCompile` | Toolchain and dependencies ready | Succeeds |
| Start native app | Optional services absent | App still starts if architecture allows |
| Invoke database-backed feature | Test database available | Returns correct business result |
| Invoke external-API feature | Mock/test service available | Timeouts, errors, and retries follow policy |

Do not mechanically pass Maven/Gradle `--offline` if dependencies are not cached; the build tool's offline mode controls dependency downloads, not a firewall blocking connections opened by application code.

## 16. Symptoms and resolutions for service-dependency errors

| Symptom during AOT | Possible cause | Resolution |
|---|---|---|
| `Connection refused` to database in `processAot` | Processor, condition, or post-processor opens a connection | Check stack trace, remove I/O from build callbacks |
| HTTP timeout to Config Server | Bootstrap/AOT config is loading remote config | Supply local build-time configuration, separate secrets/runtime config |
| `BeanCreationException` for an AOT processor | Processor or dependency failed to initialize | Reduce dependencies, remove connection logic from constructors |
| `Condition` returns different results between CI and dev | Condition relies on external state or unfixed env | Rely on explicit properties/classpath and record AOT environment |
| Missing bean when running native | Condition/profile excluded the bean during build | Build with matching profiles/properties and inspect generated bean definitions |
| Static initializer fails on DNS | Class initialized along an AOT path | Move I/O out of static initializers |
| AOT succeeds, but runtime app fails to connect | Runtime service/credentials/network unavailable | Check runtime config, secrets, DNS, timeouts, and policies |
| Build succeeds, but startup is slow or fails | External work happening during runtime lifecycle | Measure startup separately, move connections to lazy/on-demand or background |

Do not fix errors by raising timeouts indefinitely or opening broad network access on build runners before identifying which code path is trying to connect. If a build callback is doing business work, that is usually a separation-of-responsibilities issue to fix in code.

## 17. Practice: removing an HTTP query from an AOT condition

Suppose an application has a `remote-catalog` feature. Initially, a custom condition sends an HTTP request to ask whether the catalog service is up. When running `processAot` in CI, the service is not started yet and the build fails.

### Step 1 — Identify the call path

Search across:

- `Condition.matches()`
- `ImportSelector.selectImports()`
- `ImportBeanDefinitionRegistrar`
- `BeanFactoryPostProcessor`
- `BeanFactoryInitializationAotProcessor`
- `BeanRegistrationAotProcessor`
- Constructors/static initializers of those classes

Locate where HTTP, JDBC, or secret reading occurs.

### Step 2 — Turn the structural decision into a property

Replace the network query with a `features.remote-catalog.enabled` property provided in the AOT environment. The condition reads only the property without checking service health.

### Step 3 — Separate the runtime client

Register `RemoteCatalogClient`, with its constructor only preparing the local HTTP client. Query methods execute HTTP only when business logic calls them.

### Step 4 — Run AOT with services blocked

~~~bash
./gradlew processAot
~~~

AOT should succeed even when the catalog service is unreachable. Afterward, integration tests can run against a mock server.

### Step 5 — Test the native executable

~~~bash
./gradlew nativeCompile
~~~

Run the native app and call the endpoint requiring the catalog. Verify requests are sent only when business logic requests them, timeouts are enforced, and service errors are handled according to policy.

### Comparison table

| Before fix | After fix |
|---|---|
| Condition calls HTTP to decide the bean | Condition reads a build-time property |
| AOT depends on the catalog service | AOT does not need the catalog service |
| Build output varies with service health | Build output is reproducible from source and config |
| Client connects upon creation | Client connects only when business logic calls it |
| CI must start auxiliary services before AOT | Only integration tests need mock/test services |

## 18. Checklist for safe initialization code

Before adding an integration to a Native Image application, answer:

1. **Which phase does this code run in?** AOT build, native compilation, runtime startup, or when business logic is invoked?
2. **Which callback invokes it?** Condition, registrar, post-processor, AOT processor, or lifecycle callback?
3. **Is there any I/O or side effect?** HTTP, JDBC, filesystem outside build inputs, DNS, cloud metadata, secret manager, broker?
4. **Is the result deterministic?** Do the same sources, toolchain, and build configuration yield the same bean definitions?
5. **Can it be replaced with metadata?** Properties, classpath, manifests, schema snapshots, or versioned files?
6. **Are AOT processor dependencies lightweight?** Does the processor pull in business services or auto-connecting clients?
7. **Does runtime have explicit error policies?** Timeouts, retries, circuit breakers, readiness, logging, and fallbacks?
8. **Has AOT been run with external services blocked?** If not, you cannot yet conclude the build is independent of external services.

A pragmatic rule: **build code decides structure from known data; runtime code interacts with the outside world**.

## 19. Key takeaways

Spring AOT normally does not instantiate all application beans during build analysis. However, configuration processing and bean registration do execute callbacks; AOT processors and their dependencies are also instantiated to produce contributions. Those are the places to inspect when a build accidentally depends on a database, broker, Config Server, or external API.

Keep `Condition`s, registrars, `BeanFactoryPostProcessor`s, and AOT processors **fast, deterministic, side-effect-free, and metadata-driven**. Creating a client should not mean connecting; defer I/O until the application actually needs it. For `@PostConstruct` and lifecycle callbacks on regular beans, remember they belong to runtime startup and can still affect a native app's readiness.

Designing this way lets AOT run in network-restricted CI, keeps builds reproducible, and ensures the native application depends on external services only at the exact moment business logic needs them.

### References

- Spring Framework — Ahead of Time Optimizations: https://docs.spring.io/spring-framework/reference/core/aot.html
- Spring Boot — Ahead-of-Time Processing: https://docs.spring.io/spring-boot/how-to/aot.html
- Spring Boot Gradle Plugin — Ahead-of-Time Processing: https://docs.spring.io/spring-boot/gradle-plugin/aot.html
- Spring Boot Maven Plugin — Ahead-of-Time Processing: https://docs.spring.io/spring-boot/maven-plugin/aot.html

APIs, tasks, and configurations may differ across Spring Boot/Spring Framework versions. When applying these practices, cross-check the documentation for your project's exact version.
