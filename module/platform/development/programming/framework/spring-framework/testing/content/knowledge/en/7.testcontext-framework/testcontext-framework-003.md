# TestContextBootstrapper, ContextLoader, and SmartContextLoader

The Spring TestContext Framework needs to perform two tasks before an integration test can use Spring: determine how to build the test environment, and then load the ApplicationContext according to the merged configuration. The three components TestContextBootstrapper, ContextLoader, and SmartContextLoader participate in those two tasks at different layers.

- **TestContextBootstrapper** prepares the TestContext scaffolding: choosing how to initialize TestContext, the default ContextLoader, and the list of TestExecutionListeners.
- **ContextLoader** is the contract for loading an ApplicationContext from test configuration.
- **SmartContextLoader** extends the loader contract to understand Spring Test's merged configuration, including configuration classes, active profiles, initializers, and other attributes.

Understanding each component's role helps you trace how Spring creates a context, know which annotations govern behavior, and choose the right extension point when customization is needed.

## Position of the Three Components in the TestContext Framework

The TestContext Framework is not simply a direct call to `new AnnotationConfigApplicationContext(...)`. It has an initialization pipeline that combines metadata from the test class, context configuration, listeners, and the cache.

Overall flow:

~~~mermaid
flowchart TD
    A["JUnit calls SpringExtension"] --> B["TestContextManager"]
    B --> C["BootstrapUtils locates TestContextBootstrapper"]
    C --> D["Bootstrapper builds TestContext and listeners"]
    D --> E["TestContext needs ApplicationContext"]
    E --> F["CacheAwareContextLoaderDelegate"]
    F --> G["ContextLoader / SmartContextLoader"]
    G --> H["ApplicationContext"]
    H --> I["Test uses Spring beans and environment"]
~~~

The components have distinct responsibilities:

| Component | Responsibility | Question It Answers |
|---|---|---|
| `TestContextManager` | Coordinates Spring Test callbacks during the test lifecycle | When should the test instance be prepared, listeners invoked, and test completion signaled? |
| `TestContextBootstrapper` | Creates TestContext and supplies foundational framework configuration | Which bootstrap strategy does this test class use? |
| `TestContext` | Holds the test context and provides ApplicationContext when needed | Which class/method does the current test belong to, and what is its context? |
| `ContextLoader` | Loads ApplicationContext according to the chosen configuration | How should the context be created? |
| `SmartContextLoader` | Loader that understands Spring's merged test configuration | How are configuration classes, profiles, initializers, and properties handled? |
| `CacheAwareContextLoaderDelegate` | Coordinates retrieving a context from the cache or asking the loader to create a new one | Is a matching context already in the cache? |
| `TestExecutionListener` | Participates in stages of the test lifecycle | What action should run before or after a test stage? |

The bootstrapper and loader do not replace each other. The bootstrapper sets up how the TestContext Framework operates; the loader is responsible for creating the ApplicationContext. Listeners participate in the lifecycle, while the context cache is coordinated through the delegate.

## TestContextBootstrapper: Setting Up the Testing Scaffolding

`TestContextBootstrapper` is the SPI (Service Provider Interface) used to bootstrap the Spring TestContext Framework for a test class. It supplies the components that `TestContextManager` needs to manage the test.

A bootstrapper typically determines or provides:

- How to create the `TestContext` object bound to the test class.
- The list of `TestExecutionListener` instances to be registered.
- The default ContextLoader if the test does not specify a custom loader.
- How to merge metadata from test configuration annotations.
- The merged configuration info to pass to the loader.

Spring locates the bootstrapper via `BootstrapUtils`. The `@BootstrapWith` annotation allows specifying a bootstrapper for a test class or a composed annotation. If no custom choice is present, the framework uses the default bootstrapper appropriate for the test type.

### Default Bootstrapper and Specialized Bootstrappers

Spring Framework provides `DefaultTestContextBootstrapper` for standard tests. For web tests, the framework has a specialized bootstrapper such as `WebTestContextBootstrapper` to work with web application contexts and related components.

For example, a test using standard Java configuration:

~~~java
@SpringJUnitConfig(BillingTestConfig.class)
class BillingServiceIntegrationTest {

    @Autowired
    BillingService billingService;

    @Test
    void calculatesInvoice() {
        // Verify behavior with beans in ApplicationContext.
    }
}
~~~

`@SpringJUnitConfig` is an annotation combining JUnit Jupiter extension via `SpringExtension` and context configuration declaration via `@ContextConfiguration`. SpringExtension uses TestContextManager; TestContextManager uses the bootstrapper to set up TestContext.

If the test belongs to a Spring Boot application, `@SpringBootTest` uses Spring Boot's own bootstrap mechanism, typically `SpringBootTestContextBootstrapper`. Boot adds application initialization via SpringApplication and auto-configuration. This is Spring Boot's extension built on top of the TestContext Framework.

### Customizing the Bootstrapper with @BootstrapWith

When a group of tests needs a custom bootstrap policy, you can specify a class implementing `TestContextBootstrapper` via `@BootstrapWith`:

~~~java
@BootstrapWith(ProjectTestContextBootstrapper.class)
@ContextConfiguration(classes = ProjectTestConfig.class)
class ProjectIntegrationTest {
    // ...
}
~~~

`ProjectTestContextBootstrapper` is a project-supplied bootstrapper, typically built by extending an existing bootstrapper and overriding the necessary extension points. It can change default listeners, the default ContextLoader, or how test configuration is constructed.

Do not create a custom bootstrapper just to add a bean or enable a profile. Standard configuration needs are already covered by annotations such as `@ContextConfiguration`, `@ActiveProfiles`, `@TestPropertySource`, `@DynamicPropertySource`, and `@ContextHierarchy`. A bootstrapper is suitable when you need to change bootstrap policy at the framework level or standardize how multiple test classes are set up.

## ContextLoader: The Contract for Loading ApplicationContext

`ContextLoader` describes the responsibility of loading a Spring `ApplicationContext` for a test. It receives configuration location details and creates a context so the test can use beans.

In the older API model, the loader worked with a list of resource locations. Legacy `ContextLoader` methods process locations per test class and load the context from those locations. This approach suits traditional XML configuration but does not fully express the kinds of metadata the modern TestContext Framework manages.

Example of a test using XML:

~~~java
@ContextConfiguration(locations = "/test-context.xml")
class LegacyXmlContextTest {
    // Spring loads ApplicationContext from XML resource.
}
~~~

If no loader is specified, the bootstrapper and Spring's defaults select an appropriate loader. Tests usually only need to declare resource locations or configuration classes; there is no need to invoke the loader manually.

### ContextLoader Is Not TestContextBootstrapper

The two components are often confused because both participate in the context preparation phase:

- The bootstrapper selects and provides the bootstrap structure for the TestContext Framework.
- The loader reads the selected configuration and creates the ApplicationContext.

For example, a bootstrapper may choose the appropriate default loader for a group of tests. That loader then creates the context from each test class's configuration classes or resource locations.

The loader is not responsible for coordinating `@BeforeEach`, `@AfterEach`, listener callbacks, or JUnit method execution order. Those belong to the lifecycle coordinated by JUnit, SpringExtension, TestContextManager, and TestExecutionListener.

### Specifying a Loader for a Test

`@ContextConfiguration` has a `loader` attribute to specify the ContextLoader or SmartContextLoader that the test wants to use:

~~~java
@ContextConfiguration(
    locations = "/billing-test-context.xml",
    loader = ProjectContextLoader.class
)
class BillingXmlIntegrationTest {
    // ...
}
~~~

`ProjectContextLoader` is a project-supplied implementation. If the loader needs to understand modern configuration such as annotated classes, active profiles, initializers, or property sources, it should implement the `SmartContextLoader` SPI. Legacy loaders only suit the simple location contract and may not support newer metadata fully.

Specifying a loader is a decision about the context loading mechanism. It does not replace declaring beans, profiles, or properties; those contents must still exist in the configuration received by the loader.

## SmartContextLoader: Loader That Understands Merged Configuration

`SmartContextLoader` is an extension of `ContextLoader` to support a richer configuration model. It works with `ContextConfigurationAttributes` when processing configuration metadata and `MergedContextConfiguration` when loading the final context.

The two main steps have distinct meanings:

1. **Processing configuration:** `processContextConfiguration(...)` lets the loader inspect `@ContextConfiguration` metadata, derive default configuration when needed, or adjust configuration details.
2. **Loading context:** `loadContext(MergedContextConfiguration)` receives the merged configuration and creates the ApplicationContext.

`MergedContextConfiguration` holds information synthesized by the TestContext Framework from the test class and its superclasses or related annotations. Depending on the test type, configuration can include:

- Resource locations and annotated classes.
- Context initializer classes.
- Active profiles.
- Property source descriptors and inline properties.
- Context customizers.
- Selected ContextLoader.
- Parent context if using a context hierarchy.
- Resource base path information for web contexts.

Because of this, the loader does not have to rediscover and re-parse every annotation across the entire inheritance tree. It receives a configuration object already prepared by the framework to load the context consistently.

### DelegatingSmartContextLoader

Spring Framework provides `DelegatingSmartContextLoader` as the default smart loader for many non-web tests. It can delegate to a loader appropriate for the configuration style:

- `AnnotationConfigContextLoader` when the test declares configuration via classes or component configuration.
- `GenericXmlContextLoader` when the test declares XML resources.

For web tests, there is a corresponding delegating loader, `WebDelegatingSmartContextLoader`, which works with web context loaders such as `AnnotationConfigWebContextLoader` and `GenericXmlWebContextLoader`.

Example of Java-based configuration:

~~~java
@Configuration
@ComponentScan(basePackageClasses = BillingService.class)
class BillingTestConfig {
    // Beans and configuration for testing.
}

@ContextConfiguration(classes = BillingTestConfig.class)
class BillingContextTest {
    @Autowired
    BillingService billingService;
}
~~~

The test only declares the configuration class. The smart loader receives that metadata and creates the context from the annotated configuration. When switching to XML, the test can declare `locations`; the corresponding delegated loader processes the XML resources.

Delegation lets tests use multiple configuration source types without manually choosing a loader implementation in every case.

## Relationship Between @ContextConfiguration and the Loader

`@ContextConfiguration` is where the test describes configuration sources. The loader is the component that executes loading of those configuration sources.

Some common declaration forms:

~~~java
// Java configuration
@ContextConfiguration(classes = BillingTestConfig.class)
class JavaConfigTest {
}

// XML configuration
@ContextConfiguration(locations = "/billing-context.xml")
class XmlConfigTest {
}

// Specify a custom loader
@ContextConfiguration(
    classes = BillingTestConfig.class,
    loader = ProjectSmartContextLoader.class
)
class CustomLoaderTest {
}
~~~

These attributes can be combined with other annotations:

- `@ActiveProfiles` activates profiles.
- `@TestPropertySource` declares properties for the test.
- `@DynamicPropertySource` registers properties determined at runtime.
- `@ContextHierarchy` describes parent/child relationships between contexts.
- `@WebAppConfiguration` marks that the test requires a web application context.

Spring aggregates the relevant information before asking the loader to load the context. When configuration is inherited from a superclass or composed annotations, the TestContext Framework's merge rules determine the final configuration. The loader operates on that merged configuration.

### Context Hierarchy

Some applications have a parent and child context structure, such as a root context containing services/repositories and a child web context containing controllers or web infrastructure. `@ContextHierarchy` describes this structure so the TestContext Framework loads the contexts in parent/child relation.

~~~java
@ContextHierarchy({
    @ContextConfiguration(classes = RootTestConfig.class),
    @ContextConfiguration(classes = WebTestConfig.class)
})
@WebAppConfiguration
class WebLayerIntegrationTest {
    // Testing inside a web application context with a parent context.
}
~~~

The loader must receive parent context details in the merged configuration to construct the child context with the proper relationship. Cache management and context relationships are coordinated by the TestContext Framework; you should not manually create a child context inside a test method and expect Spring to manage its lifecycle automatically.

## Bootstrapper, Loader, and Context Cache

Initializing an ApplicationContext can be expensive. Spring Test uses a context cache to reuse contexts across tests with equivalent configuration.

The bootstrapper prepares the configuration and loader for TestContext. When a test needs the ApplicationContext, TestContext checks the cache via `CacheAwareContextLoaderDelegate`. If a matching context already exists, the framework can reuse it; if not, the delegate calls the loader to create the context and stores it.

~~~mermaid
flowchart TD
    A["MergedContextConfiguration"] --> B["CacheAwareContextLoaderDelegate"]
    B --> C{"Is context in cache?"}
    C -->|Yes| D["Use cached ApplicationContext"]
    C -->|No| E["Invoke SmartContextLoader"]
    E --> F["Create ApplicationContext"]
    F --> G["Store context in cache"]
    G --> D
~~~

The cache key is formed from the merged context configuration and related factors. Therefore, changes in configuration such as configuration classes, profiles, properties, initializers, or context customizers can cause a test to use a different context cache entry.

`@DirtiesContext` marks the context as altered and no longer suitable for reuse within the declared scope. It affects the context cache; it does not replace cleaning database data or cleaning up side effects outside the context.

If tests continuously create many nearly identical configurations, the number of cached contexts can grow and slow down the suite. Use consistent configuration when possible, and mark a context dirty only when the test genuinely alters context state in an unrecoverable way.

## When Should Each Component Be Customized?

Choose the extension point according to the responsibility you need to change:

| Need | Component to Consider | Reason |
|---|---|---|
| Change how a group of tests is bootstrapped, default listeners, or shared configuration policy | `TestContextBootstrapper` | It sets up the TestContext scaffolding |
| Use a custom ApplicationContext loading mechanism | `ContextLoader` / `SmartContextLoader` | It creates the context from configuration |
| Declare extra beans, profiles, or properties for a test | Existing configuration annotations | These are configuration metadata, no custom SPI needed yet |
| Change behavior before/after test stages | `TestExecutionListener` | Listeners participate in the test lifecycle |
| Add JUnit Jupiter-specific behavior | JUnit Extension or appropriate `SpringExtension` integration | This is the test execution layer |
| Use Spring Boot auto-configuration | `@SpringBootTest` and Boot's bootstrap/loader mechanism | Boot already provides specialized integration |

A custom `SmartContextLoader` should only appear when the project has a specialized configuration source or context loading rule that built-in loaders do not support. A custom bootstrapper should only appear when you need to alter how the framework prepares TestContext for a group of tests.

Do not implement a custom loader just to swap out a few beans in a test. Use `@TestConfiguration`, `@Import`, `@ContextConfiguration`, profiles, or test property sources. Those mechanisms express intent more clearly and are easier to maintain.

## Process for Tracing How Spring Creates a Context

When a test loads the wrong configuration, misses a bean, or creates more ApplicationContexts than expected, you can trace the flow as follows:

1. Identify the test class and configuration annotations: `@ContextConfiguration`, `@BootstrapWith`, `@WebAppConfiguration`, `@SpringBootTest`, or composed annotations.
2. Identify the selected bootstrapper. If `@BootstrapWith` is present, check the specified class; otherwise, check the default bootstrapper or the specialized bootstrapper for the test type.
3. Check which TestExecutionListeners and default ContextLoader the bootstrapper provides.
4. Inspect the final merged configuration: classes, locations, profiles, properties, initializers, customizers, and parent context.
5. Identify the actual loader. If `DelegatingSmartContextLoader` is used, check whether it delegates to the annotation or XML loader.
6. Monitor the context cache to see whether the context is reused or newly created.
7. If the wrong context is created, inspect the loader and configuration sources; if the context is right but the test lifecycle is wrong, inspect listeners and TestContextManager.

This tracing method separates context configuration errors from test logic errors. For instance, a missing bean might be due to a component outside the scan path, an unactivated profile, or a custom loader ignoring annotated classes. Creating contexts too many times may stem from differing merged configurations or contexts marked dirty.

## Common Misconceptions

**Assuming the bootstrapper directly instantiates all beans.** The bootstrapper sets up TestContext and framework components. ContextLoader is what actually loads the ApplicationContext.

**Assuming ContextLoader manages JUnit's lifecycle.** The loader does not coordinate `@BeforeEach`, `@AfterEach`, or test callbacks. TestContextManager and TestExecutionListener handle lifecycle coordination.

**Assuming SmartContextLoader is another kind of bootstrapper.** SmartContextLoader is an SPI for loading contexts. It is selected or supplied by the bootstrapper to create the ApplicationContext.

**Assuming @ContextConfiguration always uses a single loader for every test type.** The default loader can differ across standard tests, web tests, or extensions like Spring Boot. The `loader` attribute also allows specifying a custom implementation.

**Assuming a custom loader is the standard way to add configuration.** Most cases only need configuration classes, profiles, property sources, initializers, or imports. Creating a new loader increases infrastructure maintenance burden.

**Assuming the context cache is managed by the loader itself.** Caching is coordinated through `CacheAwareContextLoaderDelegate`; the loader is responsible for loading a context when the framework needs to create a new one.

## How to Remember

TestContextBootstrapper answers the question "how will the framework be set up for this test?". ContextLoader answers "how to load the ApplicationContext?". SmartContextLoader answers that question using a rich test configuration merged by Spring.

In most normal tests, you only need to declare `@ContextConfiguration`, `@SpringJUnitConfig`, profiles, and properties. Spring picks the right default bootstrapper and smart loader. Extend the bootstrapper only when changing TestContext initialization policy at the framework level; extend SmartContextLoader only when needing a specialized ApplicationContext loading mechanism. Distinguishing these two extension points keeps test configuration clear, reduces custom infrastructure code, and makes it easy to trace causes when Spring builds an unexpected context.
