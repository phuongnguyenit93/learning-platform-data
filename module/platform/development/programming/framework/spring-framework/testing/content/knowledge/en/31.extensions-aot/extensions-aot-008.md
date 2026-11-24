# Dynamic Configuration Limitations in AOT or Native Image Mode

**Context:** Spring Framework Testing → Extensions and AOT.

Spring lets applications flexibly register beans, select configuration by profile, read properties, scan the classpath, and create proxies at runtime. This flexibility is very useful in a standard JVM environment, but it has limitations when an application is processed with **Ahead-of-Time (AOT)** or packaged as a **native image**.

AOT moves part of the work Spring normally does at startup into the build phase. Spring analyzes configuration, determines beans and dependency relationships, and then generates initialization code along with required runtime hints. Native image goes further by compiling the application into an executable with a predetermined set of classes, reflection, resources, and proxies.

Therefore, not every decision that can be changed arbitrarily at runtime on the JVM can be changed after AOT processing or native-image compilation is complete. It is important to distinguish:

- **Bean graph configuration:** decides which beans exist, how they are created, and which beans they depend on.
- **Runtime values:** configuration data that already-registered beans can read while the application runs.
- **Runtime accessibility:** classes, constructors, methods, resources, or proxies that the native image must retain for access.

An AOT application can still read environment configuration and handle data that changes at runtime. Limitations mainly arise when runtime data is used to alter the `ApplicationContext` structure or requires accessing components not prepared during the build.

## 1. What Do AOT and Native Image Change?

### 1.1. Standard JVM Spring Initialization

In a Spring application running on the JVM, the container typically performs many steps at startup:

1. Reading configuration and the environment.
2. Discovering configuration classes and components.
3. Evaluating profiles, conditions, and imports.
4. Registering bean definitions.
5. Processing bean factory post-processors.
6. Instantiating beans, injecting dependencies, and creating proxies.
7. Completing `ApplicationContext` setup.

Part of this work—such as classpath scanning, annotation analysis, constructor resolution, and metadata generation—can happen during startup.

### 1.2. AOT Moves Suitable Work to Build Time

Spring AOT analyzes the `ApplicationContext` during the build phase and generates code supporting initialization. The goal is to reduce work at startup and make the application structure easier for the native-image compiler to analyze.

~~~text
Build time
  |
  +--> Read application configuration
  |
  +--> Analyze components, @Bean, imports, and conditions
  |
  +--> Determine bean definitions and dependency graph
  |
  +--> Generate initialization code / runtime hints
  |
  v
Generated AOT artifacts
  |
  +--> JVM runs with AOT initializer
  |
  +--> Or native-image compiler builds executable
                         |
                         v
                    Runtime
~~~

AOT is not simply saving an already-created `ApplicationContext` and restoring it verbatim. Spring generates code and metadata to initialize the context inside the built application.

### 1.3. Native Image Limits What Can Be Discovered at Runtime

The native-image compiler analyzes reachable program paths to decide which components must be included in the executable. Operations relying on reflection, class loading, resource discovery, or dynamic proxies may need explicit hints.

If a class is only looked up by a name retrieved from external data after the executable is built, the compiler may not know that class needs to be retained. Similarly, a resource file not included in the image may not exist at runtime even if it existed on the build machine.

### 1.4. Distinguishing AOT Mode and Native Image

Two related but distinct concepts:

| Mode | What Happens |
|---|---|
| Standard JVM | Spring performs many configuration and initialization steps at startup on the JVM |
| JVM with AOT-generated code | The application still runs on the JVM but uses pre-generated initialization code |
| Native image | The native-image compiler builds an executable from the application and AOT artifacts |
| TestContext AOT | Spring analyzes the test `ApplicationContext` and generates an initializer for integration tests |

An application can be tested with AOT-generated code on the JVM before investing time in building a native image. This catches many AOT configuration issues earlier, though it does not replace running a native executable when verifying reflection, resources, proxies, and native runtime behavior.

## 2. Distinguishing Structural Configuration from Runtime Values

This is the most important principle when designing AOT applications.

### 2.1. Configuration Determining Which Beans Exist

The following mechanisms commonly affect the bean graph:

- `@Profile`.
- `@Conditional` and specialized conditions.
- `@ConditionalOnProperty` in Spring Boot.
- `@Import` and `ImportSelector`.
- Component scanning.
- Bean definitions registered via programmatic APIs.
- Configuration selected based on properties or environment.

In AOT, these decisions are evaluated when Spring analyzes the context at build time. The generated bean graph is based on the configuration seen at that moment.

Example:

~~~java
@Configuration
class PaymentConfiguration {

    @Bean
    @Profile("sandbox")
    PaymentGateway sandboxGateway() {
        return new SandboxPaymentGateway();
    }

    @Bean
    @Profile("production")
    PaymentGateway productionGateway() {
        return new HttpPaymentGateway();
    }
}
~~~

If AOT processing runs with the `sandbox` profile, the sandbox configuration may be included in the generated bean graph. Do not expect that merely activating the `production` profile after the native executable is built will cause the executable to add production beans that were excluded during AOT processing.

If you need two different bean graphs by profile, process the profile during the build phase and produce separate artifacts for each configuration, or design a bean that selects behavior via runtime values without altering the context structure.

### 2.2. Values Read by Already-Registered Beans Can Still Change at Runtime

Example:

~~~java
@Component
class CatalogEndpoint {

    private final Environment environment;

    CatalogEndpoint(Environment environment) {
        this.environment = environment;
    }

    URI baseUrl() {
        return URI.create(
                environment.getRequiredProperty("catalog.base-url")
        );
    }
}
~~~

The `CatalogEndpoint` bean is already registered in the context. When `baseUrl()` runs, it reads the property from the current `Environment`. The property value can be supplied from environment variables or runtime configuration sources, depending on how the application is deployed.

This differs from using a property to decide which bean gets registered:

~~~java
@Bean
@ConditionalOnProperty(
        name = "catalog.mode",
        havingValue = "sandbox"
)
CatalogGateway sandboxGateway() {
    return new SandboxCatalogGateway();
}
~~~

The condition determines the bean graph during AOT processing. Therefore, do not equate "AOT fixes every property" with "AOT fixes every runtime configuration." Determine whether a property controls bean registration or merely supplies a value to an already-existing bean.

### 2.3. Quick Identification Table

| Need | Impact | Approach |
|---|---|---|
| Selecting beans by `@Profile` | Changes bean graph | Select profile during AOT processing or build separate artifacts |
| Using `@ConditionalOnProperty` to register beans | Changes bean graph | Condition must be determined during build |
| Reading a service URL from environment in a registered bean | Runtime value | Use appropriate externalized configuration |
| Reading a feature flag inside a method | Runtime value if it does not alter the bean graph | Read via configuration service/environment |
| Loading arbitrary classes by runtime name | Dynamic class loading | Restrict class list and provide hints / ensure classes are in the image |
| Scanning plugins from a directory mounted after build | Dynamic discovery | Use a dedicated registry/plugin model or run plugins in an external service |
| Loading a schema file not on the image classpath | Dynamic resource | Package the resource or use supported filesystem/object storage |

## 3. Limitations of `@Profile` and Environment-Based Configuration

### 3.1. Profiles Are Evaluated When Creating Bean Definitions

In a standard JVM application, active profiles are read when Spring creates the context. Only beans with matching `@Profile` are registered.

In AOT, Spring needs to know which profiles are active when analyzing the context to generate initialization code. Those profiles become part of the build-time assumptions for the bean graph.

~~~java
@Configuration
class StorageConfiguration {

    @Bean
    @Profile("local")
    StorageClient localStorageClient() {
        return new LocalStorageClient();
    }

    @Bean
    @Profile("cloud")
    StorageClient cloudStorageClient() {
        return new CloudStorageClient();
    }
}
~~~

If the AOT build runs with the `local` profile, the executable should not be treated as an artifact that can arbitrarily switch to the `cloud` profile to obtain a completely different bean graph.

### 3.2. Multiple Environments May Need Multiple Build Configurations

If local, staging, and production genuinely require different bean graphs, you can:

- Build separate artifacts per profile used during AOT processing.
- Keep the bean graph identical and push differences into runtime properties.
- Use a unified adapter and configure endpoints or credentials at runtime.
- Move components that need flexible replacement behind a separate service or plugin boundary.

Choose the option based on deployment requirements. Building multiple native executables incurs higher build and release costs, but gives each artifact a clear structural configuration. A unified bean with runtime properties reduces artifact count, though behavior switching must be carefully controlled.

### 3.3. Profiles Are Not a Runtime Feature Flag Mechanism

Do not use `@Profile` to continuously toggle a feature on or off while a native executable is running. Profiles primarily select context configuration at initialization.

For feature flags that must change without rebuilding, use an already-registered bean and read values from a runtime source:

~~~java
interface FeatureFlags {
    boolean isEnabled(String name);
}

@Service
class OrderFeature {

    private final FeatureFlags featureFlags;

    OrderFeature(FeatureFlags featureFlags) {
        this.featureFlags = featureFlags;
    }

    boolean supportsNewFlow() {
        return featureFlags.isEnabled("new-order-flow");
    }
}
~~~

The `FeatureFlags` bean can read from properties, a configuration server, or a feature flag service. Designed this way, the bean graph does not need to change whenever a flag changes.

## 4. Limitations of `@Conditional` and Conditional Bean Registration

### 4.1. Conditions Affect the Bean Graph

Spring Boot frequently uses `@ConditionalOnProperty`, `@ConditionalOnClass`, `@ConditionalOnMissingBean`, and other conditions to select configuration.

~~~java
@Configuration
class ReportConfiguration {

    @Bean
    @ConditionalOnProperty(
            name = "reports.export.enabled",
            havingValue = "true"
    )
    ReportExporter reportExporter() {
        return new PdfReportExporter();
    }
}
~~~

During AOT, conditions are evaluated when the context is analyzed. If `reports.export.enabled` is `false` at build time, the bean may be absent from the generated context.

Changing that property to `true` after the executable has been built does not mean Spring can recreate every bean definition that was excluded from the AOT output.

### 4.2. `@ConditionalOnClass` and the Classpath Are Build-Time Inputs

A classpath-based condition is resolved at build time:

~~~java
@Configuration
@ConditionalOnClass(name = "com.example.pdf.PdfEngine")
class PdfEngineConfiguration {
    // Beans depending on PdfEngine.
}
~~~

If the library is not on the classpath during the build, the configuration may be excluded. Dropping a JAR into a runtime directory after the native image has been created does not make that class appear in the executable.

With native image, required classes must be present on the classpath during native compilation and retained via reachability/hints.

### 4.3. `@ConditionalOnMissingBean` and Configuration Ordering

Conditions based on existing bean definitions can depend on imported configurations and processing order. AOT analyzes the context with a set of configurations determined during the build.

Do not rely on runtime adding a bean outside the AOT output to alter condition outcomes. If you need to swap dependencies, select explicit build configuration or use a runtime abstraction with a fixed bean graph.

## 5. Limitations of Component Scanning and Classpath Discovery

### 5.1. Component Scanning Is Pre-Analyzed

In a standard JVM, component scanning searches packages and annotations on the classpath. AOT processes scan results during the build and generates bean registration code.

Therefore, do not expect a class copied onto the classpath after an AOT build to be automatically discovered by component scanning when the application runs. A native image generally does not include new classes added after compilation.

### 5.2. The Classpath Is Not an Arbitrary Runtime Plugin Directory

A plugin design might use `ServiceLoader`, reflection, or package scanning to find implementations. In a standard JVM, that can work if the plugin JAR is on the classpath.

With native image:

- Plugin classes must be present during native compilation.
- Service provider metadata must be recognized and packaged.
- Classes instantiated or invoked via reflection need appropriate runtime hints.
- Plugin resources must be included in the image or supplied from a supported runtime source.
- You cannot assume new JARs can be added to a native executable after build.

If the real requirement is loading new plugins without rebuilding, consider isolating plugins into a separate process/service or using a JVM runtime capable of managing classpaths appropriately. Native image is better suited to a set of classes known ahead of time.

### 5.3. `ServiceLoader` and Resource Metadata

Some libraries use `META-INF/services` to register implementations. The native-image toolchain can support many common discovery patterns, but do not assume every custom discovery mechanism works automatically.

When needed, declare resource hints or use the runtime hints API provided by Spring. Test the actual native executable to verify that service providers are found.

## 6. Programmatic Bean Registration

### 6.1. `BeanDefinitionRegistryPostProcessor` and Dynamic Registration

Some applications create bean definitions in code:

~~~java
class PluginRegistryPostProcessor
        implements BeanDefinitionRegistryPostProcessor {

    @Override
    public void postProcessBeanDefinitionRegistry(
            BeanDefinitionRegistry registry) {

        // Read the plugin list and register BeanDefinitions.
    }

    @Override
    public void postProcessBeanFactory(
            ConfigurableListableBeanFactory beanFactory) {
    }
}
~~~

In a standard JVM, a post-processor can read runtime data and conditionally register beans. But if the plugin list is only available after the native executable has been built, the AOT-generated bean graph cannot automatically infer those new beans.

AOT has extension points to contribute initialization code and runtime hints. If an application has custom bean registration logic, ensure that logic is handled during AOT analysis or has an appropriate AOT contribution. Do not assume any arbitrary `BeanDefinitionRegistryPostProcessor` can modify the bean graph after the native image is built.

### 6.2. `BeanFactoryPostProcessor` and Modifying Bean Definitions

`BeanFactoryPostProcessor` can modify bean definitions before beans are instantiated. When those modifications affect context structure, AOT needs to observe them during analysis.

A post-processor that relies on current time, network responses, or files appearing post-build to decide bean definitions can cause divergence between the AOT context and the runtime context. That is a sign the design should be revisited.

If you only need a runtime value, keep the bean definition stable and inject an abstraction that reads the value when needed. If you genuinely need to create beans from a plugin list, the list must be known at build time or require a specifically designed and tested AOT integration mechanism.

### 6.3. `ApplicationContextInitializer` and Context Customizers

`ApplicationContextInitializer`, `ContextCustomizer`, and TestContext extensions can alter `Environment` or context configuration. Some mechanisms can integrate into AOT processing, but do not assume all custom logic runs at the same point or with the same data in AOT and runtime.

When an initializer modifies bean definitions, property sources, or component registration based on dynamic data, clarify:

- Is it invoked during AOT processing, at runtime, or both?
- Are the input values the same at build time and runtime?
- Are the changes captured in the generated initializer?
- Are runtime hints registered for classes/resources the initializer needs?
- Could it cause duplicate registration or two different beans?

If stable behavior cannot be proven, simplify the initializer or separate structural decisions from reading runtime values.

## 7. Reflection and Dynamic Class Loading

### 7.1. Why Must Reflection Be Declared?

The native-image compiler analyzes the call graph and static access paths. A class referenced directly in code is generally easier to identify than a class loaded only by string name.

Example:

~~~java
Class<?> type = Class.forName(configuredClassName);
Object instance = type.getDeclaredConstructor().newInstance();
~~~

If `configuredClassName` only has a value when the application runs, the compiler may not know which class must be kept and which constructor must be accessible. When running the native executable, reflection may fail if metadata is missing.

### 7.2. Using `RuntimeHintsRegistrar`

Spring provides a runtime hints API to declare required accessibility:

~~~java
class PluginRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        hints.reflection().registerType(
                CsvReportPlugin.class,
                MemberCategory.INVOKE_DECLARED_CONSTRUCTORS,
                MemberCategory.INVOKE_PUBLIC_METHODS
        );
    }
}
~~~

Registering hints with configuration:

~~~java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(PluginRuntimeHints.class)
class PluginConfiguration {
}
~~~

The example above declares reflection access for a class known at build time. `RuntimeHintsRegistrar` does not make an arbitrary externally loaded class automatically become part of the native image. The class must still be present in build inputs and retained by the native-image compiler.

### 7.3. Registering Minimal Necessary Hints

Do not grant broad reflection access for every class if only a constructor or a specific set of methods is needed. Declare only the members the library actually uses.

Common hint categories:

- Reflection: constructors, methods, fields, and type metadata.
- Resource: files or resource patterns to be read.
- Proxy: interfaces requiring JDK dynamic proxies.
- Serialization: types needing serialization/deserialization via the corresponding mechanism.
- JNI: components requiring native interface access.

Avoiding overly broad hints reduces unnecessary metadata in the image and makes the application's runtime dependencies explicit.

### 7.4. Avoid Arbitrary Runtime Class Names When Unnecessary

If the set of implementations is finite, an explicit registry can be used:

~~~java
Map<String, Supplier<ReportPlugin>> plugins = Map.of(
        "csv", CsvReportPlugin::new,
        "pdf", PdfReportPlugin::new
);

ReportPlugin plugin = plugins.get(pluginName).get();
~~~

Class and constructor references appearing directly in code help the compiler identify reachability better than loading classes from arbitrary names. You still need to check libraries and reflection APIs used by the implementations.

## 8. Resource Hints and Configuration Files

### 8.1. Classpath Resources Are Not Always Automatically Included in Native Images

A native image packages only resources discovered by the build or explicitly declared. An application reading files via `ClassPathResource` may work on the JVM yet fail in a native executable if the resource was not included in the image.

Example:

~~~java
Resource schema = new ClassPathResource("schemas/order-v1.json");
~~~

If a required resource is not detected automatically, declare a hint:

~~~java
class SchemaRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        hints.resources().registerPattern("schemas/*.json");
    }
}
~~~

~~~java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(SchemaRuntimeHints.class)
class SchemaConfiguration {
}
~~~

The pattern should match the resource path on the classpath. If the application reads multiple file types, declare a reasonably scoped pattern and verify the files are actually present in the native image.

### 8.2. Distinguishing Classpath Resources and File System Resources

Classpath resources are packaged with the application and suit static data bundled with the artifact.

File system resources are files outside the executable, for example:

- `/etc/myapp/application-extra.yml`
- Certificate files mounted from a secret volume.
- Uploaded files or user data.
- Files updated at runtime.

A native image can still read file system files if the deployment environment provides the right permissions and paths. Runtime hints do not package external files into the image; they mainly inform the native executable about resources accessed through mechanisms requiring hints.

If configuration must change after build, use externalized configuration or mounted files at supported paths rather than expecting to swap classpath resources inside a native image.

### 8.3. Reading Files by Dynamic Name

Example:

~~~java
Path schemaPath = Path.of(
        environment.getRequiredProperty("schema.path")
);
String schema = Files.readString(schemaPath);
~~~

This is runtime filesystem access. The file needs to exist in the container or host at runtime and the process must have read permissions. It does not necessarily require a resource hint because it is not a classpath resource packaged inside the image.

However, if the path points to a resource inside the image or is accessed through a classloader, review the resource type and actual access mechanism.

## 9. Dynamic Proxies, AOP, and Proxy Hints

### 9.1. Spring Creates Proxies for Many Mechanisms

Spring may use proxies for:

- AOP advice.
- Transaction management.
- Method security.
- Scoped proxies.
- Lazy injection.
- Interface-based clients or decorators.
- Certain libraries creating proxies via reflection.

Proxies recognized by Spring AOT in supported patterns can be prepared automatically. However, proxies created dynamically by external libraries or from an unpredictable runtime list of interfaces may require hints.

### 9.2. JDK Dynamic Proxies

A JDK proxy is created from a set of interfaces:

~~~java
Object proxy = Proxy.newProxyInstance(
        classLoader,
        new Class<?>[] { PaymentGateway.class },
        invocationHandler
);
~~~

In a native image, the interfaces requiring proxies must be known. They can be declared via runtime hints:

~~~java
class PaymentProxyHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        hints.proxies().registerJdkProxy(
                PaymentGateway.class
        );
    }
}
~~~

~~~java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(PaymentProxyHints.class)
class PaymentProxyConfiguration {
}
~~~

Declare the exact interface combination used by the application. If a proxy implements multiple interfaces, pass all of them using the runtime hints API of your Spring version.

### 9.3. CGLIB and Class-Based Proxies

Class-based proxies are constructed differently from JDK dynamic proxies. Spring AOT can handle many Spring-managed proxy cases, but libraries that generate subclasses themselves or use arbitrary bytecode generation may not work as they do in JVM mode.

If a library must generate subclasses at runtime, check support in the native-image toolchain and framework. Do not assume adding a JDK proxy hint will solve a class-based proxy issue.

### 9.4. Avoid Creating Proxies from Arbitrary Runtime Interface Sets

If the interface list comes from plugin metadata or external configuration post-build, a native image cannot prepare every possible proxy combination by default.

Restrict the set of interfaces, declare the necessary combinations at build time, or replace dynamic proxies with an explicit registry/adapter when possible.

## 10. Serialization and Data Processed via Reflection

Some serialization/deserialization libraries rely on reflection, constructors, fields, or annotations. JSON codecs, XML bindings, object mappers, and persistence frameworks may require metadata depending on the case.

Spring and common integrations can contribute runtime hints automatically for many known types in the bean graph. However, types loaded from configuration or runtime data may need additional hints.

For example, if a library serializes a DTO via reflection, determine:

- Which types are serialized/deserialized?
- Which constructors are invoked?
- Which fields or methods are accessed?
- Are there generic types or polymorphic subtypes?
- Are classes selected from a runtime discriminator?
- Are hints registered at build time?

Do not add reflection hints for an entire package just to make an error disappear when only a few DTOs actually need special access.

## 11. Properties and Externalized Configuration

### 11.1. Properties Used for the Bean Graph

Properties can decide which configuration gets registered:

~~~java
@Configuration
class SearchConfiguration {

    @Bean
    @ConditionalOnProperty(
            name = "search.backend",
            havingValue = "remote"
    )
    SearchClient remoteSearchClient() {
        return new RemoteSearchClient();
    }
}
~~~

With AOT, the value of `search.backend` at context analysis time affects the generated bean graph. If a deployment wants to switch from `remote` to `local` post-build, you need a different design or separate artifacts built under the corresponding conditions.

### 11.2. Properties Only Supplying Values to Beans

~~~java
@ConfigurationProperties(prefix = "catalog")
record CatalogProperties(URI baseUrl, Duration timeout) {}

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(CatalogProperties.class)
class CatalogClientConfiguration {

    @Bean
    RestClient catalogRestClient(CatalogProperties properties) {
        return RestClient.builder()
                .baseUrl(properties.baseUrl().toString())
                .build();
    }
}
~~~

In this example, bean configuration is registered ahead of time. Property values are bound from the environment when the application starts. Externalized configuration can supply different URLs and timeouts per deployment without changing the bean list.

Verify how AOT processing and the runtime environment are set up in the project's build pipeline. Do not put production secrets into build artifacts; credentials should be provided from a secret store or appropriate runtime environment.

### 11.3. Property Sources Appearing After Build

If the application needs to read a configuration file mounted at runtime, ensure the file is loaded via an externalized configuration mechanism supported by the framework/Boot and is present in the deployment environment.

Do not confuse an external filesystem property file with a classpath resource. An external file can change after build; a classpath resource in a native image is normally already packaged into the executable.

## 12. AOT and the Spring TestContext Framework

### 12.1. `TestContext` Can Also Be AOT-Processed

The Spring TestContext Framework supports AOT processing for integration tests. Spring analyzes the test context configuration and generates initializers usable in AOT test execution or native test scenarios depending on the toolchain.

Elements that can affect the test context include:

- `@ContextConfiguration` and configuration classes.
- `@SpringBootTest` and Spring Boot test slices.
- Active profiles and test properties.
- `@Import` and nested test configurations.
- Bean overrides and test customizers.
- Context initializers, listeners, and dynamic property registration.

Tests relying on runtime discovery or state available only post-build must be reviewed carefully. TestContext AOT also requires an analyzable configuration when AOT processing runs.

### 12.2. Test Configuration Must Be Stable Between AOT Processing and Test Runtime

Suppose a test context uses:

~~~java
@SpringBootTest
@ActiveProfiles("integration")
@Import(IntegrationTestConfiguration.class)
class OrderIntegrationTest {
    // ...
}
~~~

Profiles and test configurations must be determinable when Spring creates the AOT test context. If test runtime tries to change profiles or the bean graph based on new data absent during AOT processing, the generated initializer may not represent the context the test expects.

Keep test configurations clear and stable. If multiple distinct contexts are needed, declare them as separate test configurations recognized by AOT processing.

### 12.3. `@DynamicPropertySource` and Runtime-Only Data

`@DynamicPropertySource` is commonly used to register properties from Testcontainers, mock servers, or resources with dynamic endpoints.

~~~java
@DynamicPropertySource
static void databaseProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
}
~~~

Values such as mapped ports may exist only after a container starts. When using test AOT, check your Spring Boot/Spring Test version and how the toolchain supports dynamic property sources during context generation.

Do not assume every supplier is evaluated at the right time—runtime or build time—without verifying it. For tests using Testcontainers, prefer the integration mechanism supported in your version, such as service connections where appropriate, or configure resources so AOT test processing can recognize them.

If a property affects the bean graph, its value must be consistent with the AOT-processed configuration. If it only supplies a runtime endpoint to an already-registered bean, verify that the supplier and resource lifecycle work properly in the target test mode.

### 12.4. Tests Using Dynamic Classpaths or Context Mutation

Some tests manually register beans, alter bean definitions, generate proxy classes, or scan plugins after the context has been initialized. These tests may be incompatible with TestContext AOT if the generated initializer cannot describe that behavior.

You do not necessarily have to remove them from the entire suite. You can keep them running in regular JVM test mode and separate out the AOT-compatible test group.

### 12.5. `@DisabledInAotMode`

Spring Test provides **`@DisabledInAotMode`** to mark tests or test classes that do not run in AOT mode:

~~~java
@DisabledInAotMode("Test requires runtime-generated plugin classes")
class DynamicPluginDiscoveryTests {
    // Run only in the appropriate mode.
}
~~~

This annotation is appropriate when a test verifies dynamic runtime behavior that AOT mode does not support or that is not the goal of that mode. It does not fix AOT configuration and does not make an incompatible application compatible.

Use it only with a specific reason. If a test is key evidence for production native behavior, find a way to support AOT or write an appropriate native test instead of disabling it.

`@DisabledInAotMode` is available in Spring Framework versions that support this annotation; check your project's Spring Test version before using it. On older frameworks, use conditional test mechanisms or corresponding task configurations.

## 13. Testing Applications Across Different Modes

An AOT testing workflow should distinguish three objectives.

### 13.1. Regular JVM Tests

Run the test suite in JVM mode to verify basic logic and configuration:

- Beans are registered properly.
- Profiles and properties take effect as expected.
- Reflection, resources, and proxies work on the JVM.
- Test fixtures and external dependencies are isolated.

This is the baseline, but it does not prove that AOT-generated code works.

### 13.2. Tests with AOT-Generated Code on the JVM

Run AOT processing and execute tests or the application using the generated initializer per the project's build configuration.

Objectives:

- Detect dynamic configuration not reflected in the generated context.
- Confirm conditions and profiles match build-time assumptions.
- Verify that the test AOT context can be created.
- Identify extension points lacking required AOT contributions.

If the build tool has separate tasks for application AOT and test AOT, use the task appropriate to your plugin and version. Do not confuse the application AOT task with the TestContext AOT task.

### 13.3. Native Executable Tests

When the application must be deployed as a native image, run the native build and test the executable in an environment close to deployment.

Focus on:

- Reflection and runtime hints.
- Class reachability.
- Packaged resources.
- JDK proxies and AOP.
- Serialization/codecs.
- TLS, filesystem, and environment.
- Startup, memory, and critical runtime behaviors.

AOT JVM tests can catch context configuration issues, but they do not replace native executable tests. The native-image compiler has reachability and runtime rules different from the JVM.

## 14. Redesigning Dynamic Configuration for AOT Compatibility

### 14.1. Keep the Bean Graph Stable, Move Differences to a Strategy

Instead of registering different beans based on a property that changes at runtime, you can register a facade bean and select a strategy from runtime values.

~~~java
interface StorageStrategy {
    StoredObject store(byte[] content);
}

@Component
class StorageService {

    private final StorageProperties properties;
    private final LocalStorage localStorage;
    private final CloudStorage cloudStorage;

    StorageService(
            StorageProperties properties,
            LocalStorage localStorage,
            CloudStorage cloudStorage) {
        this.properties = properties;
        this.localStorage = localStorage;
        this.cloudStorage = cloudStorage;
    }

    StoredObject store(byte[] content) {
        return switch (properties.mode()) {
            case "local" -> localStorage.store(content);
            case "cloud" -> cloudStorage.store(content);
            default -> throw new IllegalStateException(
                    "Unsupported storage mode");
        };
    }
}
~~~

Both implementations are registered in the bean graph. The `mode` value determines which strategy is called at runtime.

This works well when both implementations are present in the artifact and native image. If one implementation depends on a library or native feature that cannot be packaged together, separate artifacts or a different service boundary are needed.

### 14.2. Use an Explicit Registry Instead of Dynamic Classpath Scanning

If the set of plugins is known ahead of time, declare a registry:

~~~java
@Configuration(proxyBeanMethods = false)
class ExporterConfiguration {

    @Bean
    Map<String, Exporter> exporters(
            CsvExporter csv,
            PdfExporter pdf) {

        return Map.of(
                "csv", csv,
                "pdf", pdf
        );
    }
}
~~~

Runtime simply selects a key from the registry. Implementations and dependencies are already known at build time.

### 14.3. Isolate Plugins into a Service When Independent Extensibility Is Needed

If customers can install new plugins after the application is released, a native image may not be the right deployment model for dynamic plugin classes. You can isolate plugins into a separate process/service, expose a stable HTTP/gRPC contract, and have the host call it via a client.

Then plugins have an independent deployment lifecycle; the native-image host only needs to know the client contract. In return, the system must handle network failures, authentication, versioning, and observability.

### 14.4. Move Changing Configuration to `Environment` or a Configuration Service

If you only need to change URLs, timeouts, feature flags, or tenant policies, use runtime properties or a dedicated service. Do not recreate the `ApplicationContext` whenever a value changes unless truly necessary.

A bean can read properties at the point of use or receive a refreshable configuration abstraction. If using a dynamic refresh mechanism, verify that library and its AOT/native capabilities separately; not every dynamic refresh extension is supported automatically.

## 15. Indicators of Dynamic Configuration That May Cause Problems

| Indicator | Risk in AOT/Native | Mitigation |
|---|---|---|
| `@Profile` changes by environment post-build | Bean graph does not change with runtime profiles | Select profile at build time or use a runtime strategy |
| `@ConditionalOnProperty` depends on values available only post-deploy | Condition was already evaluated during AOT | Move differences into an already-registered bean |
| `Class.forName` takes class name from database | Class/constructor not recognized by compiler | Explicit registry and reflection hints |
| Scanning plugins from a runtime directory | Plugin classes absent from native image | Package plugins pre-build or isolate into a service |
| Classpath resource selected by dynamic name | Resource not packaged | Resource hints or external filesystem |
| Creating JDK proxies from arbitrary interface lists | Proxy combination lacks metadata | Declare proxy hints for known interface sets |
| `BeanDefinitionRegistryPostProcessor` reads runtime data | Generated bean graph misses beans | AOT contribution or redesign as a registry |
| Test mutates context after AOT initializer is generated | Test runtime differs from analyzed context | Explicit test config or exclude test from AOT mode |
| `@DynamicPropertySource` obtains dynamic port | Timing/lifecycle may differ in AOT tests | Use supported integration and verify in AOT tests |
| Adding JARs after native executable is built | Classes are not inside the image | Rebuild image or use a separate process/service |

## 16. Common Errors and How to Diagnose Them

### Bean Does Not Exist in the Native Executable

Check conditions, active profiles, and properties used during AOT processing. Verify whether the bean is registered in a regular JVM context yet excluded in the generated context.

If the bean must exist in every deployment, avoid using build-time conditions to exclude it from the bean graph.

### Changing `SPRING_PROFILES_ACTIVE` Does Not Change Beans

Profiles used to select bean definitions were already evaluated during AOT processing. Pick the right profile before building or design a stable bean graph with a runtime strategy.

### `ClassNotFoundException` or Reflection Failure

Verify whether the class is on the build classpath, whether reachability analysis retains it, and whether constructors/methods needing reflection have hints. Runtime hints cannot put a JAR absent from the native build into the executable.

### Resource Not Found

Distinguish classpath resources from file system resources. If the resource is on the classpath, add a resource hint if needed and verify the pattern is correct. If the file is external, check mounts, paths, and permissions in the container.

### Proxy Works on JVM but Fails in Native Image

Determine whether the proxy is a JDK dynamic proxy, class-based proxy, or proxy created by a library outside Spring. Check whether Spring AOT handles that pattern and declare proxy hints if needed. For arbitrary CGLIB/bytecode generation, verify support in the native-image toolchain.

### TestContext AOT Cannot Use Test Configuration

Verify that test configuration is imported explicitly, bean definitions are visible during AOT processing, and tests are not using unsupported dynamic registration. Do not assume a test passing in JVM mode will automatically work in TestContext AOT.

### Incorrect `@DynamicPropertySource` Value

Check when the container/mock server starts, when the supplier is evaluated, and the context lifecycle. Do not bake an old mapped port into the generated initializer and expect it to remain valid after the resource is recreated.

### Test Skipped in AOT Mode

If `@DisabledInAotMode` is used, read the reason and identify which behavior the test checks. The annotation only skips the test in AOT mode; it does not prove the native application is bug-free for that behavior.

## 17. Strategy for Testing Dynamic Configuration

You can divide tests by objective instead of forcing the exact same scenario into every mode.

| Test Group | Objective | Environment |
|---|---|---|
| Configuration/strategy unit tests | Verify strategy selection logic and runtime values | JVM |
| Regular context tests | Verify bean graph by profile/property | JVM Spring Test |
| AOT context tests | Verify generated initializers and analyzed configuration | JVM with AOT artifacts |
| Native integration tests | Verify reflection, resources, proxies, and codecs in executable | Native image |
| Deployment smoke tests | Verify real environment, secrets, filesystem, and network | Production-like environment |

For example, if an application supports both `local` and `cloud` profiles, test each bean graph in a regular JVM context. If you build only one native artifact for the `cloud` profile, AOT/native tests should confirm the `cloud` artifact has all required beans and runtime hints. Do not expect a `cloud` executable to automatically contain `local` beans if those beans were excluded during AOT processing.

## 18. Workflow for Migrating an Application to AOT/Native

### Step 1: Inventory Dynamic Configuration Points

Look for mechanisms:

- `@Profile` and `@Conditional`.
- `@ConditionalOnProperty`, `@ConditionalOnClass`.
- `ImportSelector` and `ImportBeanDefinitionRegistrar`.
- `BeanDefinitionRegistryPostProcessor`.
- `Class.forName`, reflection, and `ServiceLoader`.
- Classpath/resource scanning.
- Proxy creation and bytecode generation.
- `@DynamicPropertySource` in integration tests.
- Runtime property sources and external config.

Classify each mechanism as a build-time structural decision or a runtime value.

### Step 2: Define Build-Time Assumptions

Document profiles, properties, and dependencies affecting the bean graph. Ensure CI AOT builds use the exact inputs required by the deployment artifact.

Do not pass production credentials or secrets into the AOT build. Only values needed for bean structure should participate in build-time decisions.

### Step 3: Run AOT Processing and Inspect Errors

Use the AOT task appropriate for your build tool/plugin. Read errors to pinpoint which configuration cannot be analyzed, which extension needs an AOT contribution, or which type needs hints.

Do not solve every error by adding broad reflection hints. Some errors belong to bean registration, conditions, or runtime values rather than reflection.

### Step 4: Add Runtime Hints

Register reflection, resource, proxy, or serialization hints for components needing dynamic access that are known at build time. Keep hints in the configuration/module owning those types for maintainability.

### Step 5: Run AOT Tests on the JVM

Verify that the generated context has the same bean graph and expected behavior. Test the profiles/properties selected for the artifact.

### Step 6: Build and Run the Native Executable

Verify startup, critical requests, serialization, resource loading, proxies, filesystem, and networking in the native executable. Use an environment close to deployment to catch real differences.

### Step 7: Review Tests Excluded or Separated from AOT Mode

If tests use dynamic runtime behavior unsuitable for AOT, document the reason clearly and keep them running in the appropriate JVM mode. Ensure critical production behavior still has alternative test coverage at the appropriate level.

## 19. Practical Guidelines

1. Distinguish AOT-generated code on the JVM from native image; the two modes are related but not identical.
2. Determine whether a property alters the bean graph or merely supplies a value to an existing bean.
3. Treat `@Profile` and conditional bean registration as decisions that must be known during AOT processing.
4. Do not expect switching profiles at runtime to add beans excluded from the generated context.
5. Keep the classpath and required plugin set stable prior to native compilation.
6. Use an explicit registry when the set of implementations is finite.
7. Use `RuntimeHintsRegistrar` and `@ImportRuntimeHints` for reflection, resources, or proxies that must be declared.
8. Do not confuse runtime hints with a mechanism for adding new JARs or classes into a native executable.
9. Distinguish packaged classpath resources from runtime-mounted file system resources.
10. Verify that bean registration post-processors and context initializers have proper AOT integration.
11. Verify `@DynamicPropertySource` against your version and actual test resource lifecycle.
12. Use `@DisabledInAotMode` with a specific reason when a test is unsuitable for AOT mode.
13. Run JVM tests, AOT context tests, and native executable tests for their respective goals.
14. Keep secrets and sensitive configuration at runtime, not packaged in artifacts.
15. When application structure must change after deployment, consider a separate plugin/service boundary instead of relying on dynamic class loading inside a native image.

AOT and native image do not eliminate runtime configurability; they require application structure and required access capabilities to be known more clearly during the build phase. The bean graph, profiles, and conditions need to remain stable per built artifact. Environment values, endpoints, timeouts, and feature flags can still vary at runtime as long as they only control the behavior of already-registered beans. Distinguishing these two categories, declaring runtime hints in the right places, and testing AOT contexts separately from native executables will help your application retain needed flexibility while staying compatible with build-time analysis.

