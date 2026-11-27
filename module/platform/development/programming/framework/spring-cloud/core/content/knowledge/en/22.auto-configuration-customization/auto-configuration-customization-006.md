# Configuration Definition Order vs. Bean Initialization Order

In Spring, having one configuration class processed first does not mean the beans it declares will be created first. Likewise, a bean appearing earlier in a Java file or annotated with `@Order(1)` is not automatically initialized before other singletons.

To customize auto-configuration and control the application lifecycle accurately, distinguish three concepts:

1. **Configuration class processing order:** Spring reads, parses, and processes configuration sources such as `@Configuration`, `@Import`, component scans, and auto-configurations.
2. **BeanDefinition registration order:** the container records bean metadata, including name, type, scope, factory method, conditions, and dependencies.
3. **Bean initialization order:** the container instantiates objects, injects dependencies, runs initialization callbacks, and transitions instances to a ready state.

These three phases are related, not identical. `@Order` on a configuration class can influence configuration processing order; auto-configuration ordering affects bean definition order; meanwhile, singleton instantiation primarily follows the dependency graph and `@DependsOn` relationships.

This lesson belongs to the **Auto-Configuration Customization** chapter of the **SPRING_CLOUD_CORE** module. It focuses on how Spring processes Java configuration, Spring Boot auto-configuration, container extension points, and how to test initialization order without relying on accidental declaration order.

## 1. Three Orders to Distinguish

A Spring Boot application starts through several stages. At a high level:

~~~mermaid
flowchart TD
    A["Create ApplicationContext and Environment"] --> B["Register initial configuration sources"]
    B --> C["ConfigurationClassPostProcessor parses configuration"]
    C --> D["Register BeanDefinitions"]
    D --> E["BeanFactoryPostProcessor modifies metadata"]
    E --> F["Register and apply BeanPostProcessors"]
    F --> G["Instantiate non-lazy singletons"]
    G --> H["Inject dependencies and run init callbacks"]
    H --> I["SmartInitializingSingleton / ContextRefreshedEvent"]
    I --> J["ApplicationContext ready"]
~~~

This diagram shows the general sequence. Certain infrastructure components are created early to drive these stages themselves; not every bean follows an identical linear path.

| Concept | Ordered target | Common mechanism | Outcome |
| --- | --- | --- | --- |
| Configuration processing | Configuration classes | `@Order`, `@Import`, auto-configuration ordering | Order in which configuration sources are parsed/applied |
| Bean definition registration | Bean metadata | Configuration processing, component scan, imports, conditions | Order BeanDefinitions appear in BeanFactory |
| Bean instance creation | Managed objects | Constructor/method dependencies, `@DependsOn`, lazy/eager | Initialization order driven by dependency graph |
| Collection injection order | Beans of the same type injected into List/array | `@Order`, `Ordered`, registration order | Order of injected elements |
| Post-initialization processing | BeanPostProcessors | `Ordered`, `PriorityOrdered`, registration order | Order of instance-processing callbacks |

A common mistake is using an annotation meant for one stage to control another. For example, adding `@Order(1)` to a configuration class does not force all beans in that class to initialize before beans in other configuration classes.

## 2. How Does Spring Process Configuration Classes?

Spring supports multiple bean definition sources: component scanning, XML, Java configuration, imports, and auto-configuration. With Java configuration, `@Configuration` marks a class as a source of bean definitions; `@Bean` methods describe factory methods that create instances.

Example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CatalogConfiguration {

    @Bean
    CatalogRepository catalogRepository() {
        return new JdbcCatalogRepository();
    }

    @Bean
    CatalogService catalogService(CatalogRepository repository) {
        return new CatalogService(repository);
    }
}
~~~

When the ApplicationContext processes this configuration, Spring parses the class and registers the corresponding BeanDefinitions. Registering metadata does not immediately instantiate `CatalogRepository` or `CatalogService`.

A key step is `ConfigurationClassPostProcessor`. This is a `BeanDefinitionRegistryPostProcessor` used by Spring to process annotation-based configurations, including `@Configuration`, `@Bean`, `@Import`, `@ComponentScan`, and related constructs. It runs during registry processing, before the container begins instantiating regular application beans.

### 2.1. Registering a BeanDefinition Is Not Creating an Object

A BeanDefinition holds metadata such as:
- Bean name and bean class or factory method.
- Scope, such as singleton, prototype, or a custom scope.
- Constructor arguments and property values.
- Declared dependencies.
- Lazy-init, primary, qualifiers, and related attributes.
- Conditions or bean origin metadata.

You can picture it as:

~~~text
Configuration class
      |
      | parse @Bean methods
      v
BeanDefinitionRegistry
      |
      +-- catalogRepository : BeanDefinition
      |
      +-- catalogService    : BeanDefinition
      |
      v
BeanFactory creates objects later
~~~

In the example, Spring might register `catalogService`'s definition before or after `catalogRepository`'s definition depending on configuration processing. When instantiating `catalogService`, Spring still has to resolve the `CatalogRepository` dependency before completing the service bean.

Thus, the order in which metadata appears and the order in which instances are created are two separate concerns.

### 2.2. Configuration Sources Can Come from Many Places

An ApplicationContext can receive configuration from:
- Classes specified directly when creating the context.
- `@Import` from another configuration class.
- `@ComponentScan` discovering components in packages.
- Auto-configurations loaded by Spring Boot.
- BeanDefinitions registered programmatically via APIs.
- XML or other integrated configuration sources.

Do not rely on accidental filesystem ordering, package scan order, or how an IDE lists classes. If a relationship is required, declare it using the mechanism that expresses that exact relationship.

## 3. Configuration Class Processing Order

Spring Framework allows using `@Order` on configuration classes to influence evaluation order within a set of configurations processed at startup.

Example:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;

@Configuration
@Order(10)
public class SharedInfrastructureConfiguration {
    // Shared infrastructure beans.
}

@Configuration
@Order(20)
public class ApplicationFeatureConfiguration {
    // Application feature beans.
}
~~~

The two classes in the example sit in separate Java files. `@Order` on a configuration class only orders configuration evaluation; it creates no dependency relationship between beans.

Lower values have higher priority in sorting. However, `@Order` here only affects the processing order of configuration classes within the applicable set. It does not control the initialization order of the beans declared inside them.

### 3.1. @Order on Configuration Classes Does Not Apply to @Bean Methods

Example:

~~~java
@Configuration
@Order(1)
public class FirstConfiguration {

    @Bean
    AlphaService alphaService() {
        return new AlphaService();
    }

    @Bean
    BetaService betaService() {
        return new BetaService();
    }
}

@Configuration
@Order(2)
public class SecondConfiguration {

    @Bean
    GammaService gammaService() {
        return new GammaService();
    }
}
~~~

`FirstConfiguration` is prioritized before `SecondConfiguration` within the ordered configuration set. But that establishes no contract that `AlphaService` and `BetaService` are always initialized before `GammaService`.

Object creation order is still governed by dependencies, `@DependsOn`, lazy/eager settings, and the container's singleton initialization process.

### 3.2. @Import Expresses Clear Configuration Relationships

You can split configuration into small classes and compose them with `@Import`:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;

@Configuration
@Import({
        PersistenceConfiguration.class,
        MessagingConfiguration.class,
        CatalogFeatureConfiguration.class
})
public class ApplicationConfiguration {
}
~~~

`@Import` makes it explicit which configuration sources are included in the context. Do not use the order inside the import array as a way to control bean initialization order. If `CatalogFeatureConfiguration` needs a persistence bean, express that dependency in a factory method or via `@DependsOn` when the dependency is strictly an indirect initialization dependency.

## 4. Auto-Configuration Ordering in Spring Boot

Spring Boot automatically brings matching configuration classes into the ApplicationContext based on the classpath, properties, existing beans, and other conditions. Auto-configuration is not a list of beans created sequentially by class name.

An auto-configuration can declare before/after relationships with other auto-configurations so conditions and bean definitions are evaluated in the desired order.

Common mechanisms:

| Annotation | Meaning |
| --- | --- |
| `@AutoConfigureBefore` | Requests that the current auto-configuration be applied before the specified class |
| `@AutoConfigureAfter` | Requests that the current auto-configuration be applied after the specified class |
| `@AutoConfigureOrder` | Orders auto-configurations that have no direct relationship with each other |
| `@AutoConfiguration(before=...)` | Declares "before" ordering directly on the auto-configuration annotation |
| `@AutoConfiguration(after=...)` | Declares "after" ordering directly on the auto-configuration annotation |

Example:

~~~java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(after = DataSourceAutoConfiguration.class)
@ConditionalOnClass(CatalogClient.class)
public class CatalogClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    CatalogClient catalogClient() {
        return new CatalogClient();
    }
}
~~~

This example illustrates an auto-configuration that needs to be processed after DataSource configuration. Setting `after` clarifies the application order of auto-configurations, especially when conditions depend on registered BeanDefinitions.

### 4.1. Auto-Configuration Ordering Only Controls Bean Definitions

Spring Boot makes this explicit: auto-configuration application order affects the order in which bean definitions are registered. The order in which bean instances are subsequently created is still determined by dependencies and `@DependsOn`.

For example, `CatalogClientAutoConfiguration` being applied after `DataSourceAutoConfiguration` does not mean every bean created by DataSource auto-configuration is initialized before every catalog bean.

If `CatalogClient` needs `DataSource`, declare the dependency:

~~~java
@Bean
CatalogClient catalogClient(DataSource dataSource) {
    return new CatalogClient(dataSource);
}
~~~

The container will create the required dependency before completing `CatalogClient`.

### 4.2. @AutoConfigureOrder Is for Independent Auto-Configurations

If two auto-configurations should not directly depend on each other's classes, use `@AutoConfigureOrder`:

~~~java
import org.springframework.boot.autoconfigure.AutoConfigureOrder;
import org.springframework.boot.autoconfigure.AutoConfiguration;

@AutoConfiguration
@AutoConfigureOrder(100)
class CommonMetricsAutoConfiguration {
}

@AutoConfiguration
@AutoConfigureOrder(200)
class OptionalMetricsAutoConfiguration {
}
~~~

This orders the application sequence within the set of auto-configurations. It is not a mechanism for controlling the lifecycle of the declared beans.

When there is a direct relationship such as “configuration B must be applied after configuration A,” prefer `after` or `@AutoConfigureAfter` to express the intent more clearly than arbitrary order numbers.

### 4.3. How Spring Boot Discovers Auto-Configuration

Auto-configurations are published via Spring Boot's imports mechanism. In modern layouts, libraries typically declare classes in:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Each line contains the fully qualified name of an auto-configuration class. These classes should not be discovered via regular component scanning; Spring Boot loads them via the auto-configuration mechanism.

This imports file mechanism is used in modern Spring Boot versions starting from 2.7. In older Spring Boot projects, auto-configurations were typically registered under the `EnableAutoConfiguration` key in `META-INF/spring.factories`. When upgrading libraries, use the registration mechanism appropriate for the range of Boot versions the library supports.

The `@AutoConfiguration` annotation also belongs to Spring Boot 2.7 and later. In older Boot versions, auto-configuration classes typically used `@Configuration` combined with the ordering/condition annotations available in that version and registered via `spring.factories`. Check the actual API of your target BOM before applying examples.

When writing a Spring Boot library:
- Place auto-configurations in a dedicated package.
- Register classes via the imports file.
- Use `@ConditionalOnClass`, `@ConditionalOnMissingBean`, and `@ConditionalOnProperty` as appropriate.
- Use `before`/`after` to order definitions with related auto-configurations.
- Do not enable broad component scanning from an auto-configuration to find arbitrary classes.
- Do not use auto-configuration ordering as a substitute for dependency injection.

## 5. Configuration Conditions and Evaluation Order

Condition annotations such as `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnBean`, and `@ConditionalOnMissingBean` determine whether a configuration or bean definition is registered.

Auto-configuration application order can affect the result of conditions that inspect existing beans. For example, an auto-configuration creating a default bean with `@ConditionalOnMissingBean` needs to be applied after configurations that have the chance to supply a custom bean.

Example:

~~~java
@AutoConfiguration
public class DefaultCatalogAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(CatalogClient.class)
    CatalogClient defaultCatalogClient() {
        return new DefaultCatalogClient();
    }
}
~~~

An application can provide its own bean:

~~~java
@Configuration(proxyBeanMethods = false)
public class CustomCatalogConfiguration {

    @Bean
    CatalogClient catalogClient() {
        return new CustomCatalogClient();
    }
}
~~~

Once the custom configuration is registered and the condition sees the corresponding BeanDefinition, the default bean can be skipped. If one auto-configuration depends on another auto-configuration, declare an ordering relationship rather than relying on class names or file ordering.

Note: conditions are evaluated during configuration processing/definition registration. They do not wait for bean instances to be constructed before deciding. This is why it is important to distinguish registered metadata from runtime objects.

## 6. Bean Initialization Order Is Determined by the Dependency Graph

When Spring creates a bean, the container must resolve its dependencies before completing the dependent bean. This is the primary mechanism guaranteeing initialization order.

Example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CatalogConfiguration {

    @Bean
    CatalogRepository catalogRepository() {
        return new JdbcCatalogRepository();
    }

    @Bean
    CatalogService catalogService(CatalogRepository repository) {
        return new CatalogService(repository);
    }

    @Bean
    CatalogController catalogController(CatalogService service) {
        return new CatalogController(service);
    }
}
~~~

Dependency graph:

~~~mermaid
flowchart LR
    A["CatalogRepository"] --> B["CatalogService"]
    B --> C["CatalogController"]
~~~

To create `CatalogController`, Spring needs `CatalogService`. To create `CatalogService`, Spring needs `CatalogRepository`. Therefore, the repository must be created and configured before the service; the service must be ready before the controller.

This order exists because the dependency relationships are declared via factory method parameters. Neither `@Order` nor `@DependsOn` is needed to restate those dependencies.

### 6.1. Constructor Injection Makes Dependencies Explicit

Component example:

~~~java
import org.springframework.stereotype.Repository;
import org.springframework.stereotype.Service;

@Repository
public class CatalogRepository {
}

@Service
public class CatalogService {

    private final CatalogRepository repository;

    public CatalogService(CatalogRepository repository) {
        this.repository = repository;
    }
}
~~~

When creating `CatalogService`, Spring must supply `CatalogRepository` first. Constructor injection makes mandatory dependencies visible right at object creation, making code easier to read and test.

For genuinely required dependencies, constructor injection is always better than relying on implicit initialization order or calling `getBean()` manually.

### 6.2. Without a Dependency, Do Not Assume Order

If two singletons are independent—having no direct dependency and no `@DependsOn`—the application must not rely on an accidental creation order between them.

A framework upgrade, a different component scan, or a new auto-configuration can change definition registration order. If business logic requires A to complete before B, express that relationship with a dependency or an appropriate lifecycle callback.

## 7. When Is @DependsOn Needed?

`@DependsOn` is used when there is an indirect initialization dependency that constructor or method injection cannot express.

For example, a bean needs to be created after a schema initializer has run, even though it does not need to hold a reference to the initializer:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.DependsOn;

@Configuration(proxyBeanMethods = false)
public class SearchConfiguration {

    @Bean
    SchemaInitializer schemaInitializer() {
        return new SchemaInitializer();
    }

    @Bean
    @DependsOn("schemaInitializer")
    SearchIndex searchIndex() {
        return new SearchIndex();
    }
}
~~~

Spring creates `schemaInitializer` before creating `searchIndex`. You do not need to inject `SchemaInitializer` into `SearchIndex`'s constructor if that bean does not use the object.

### 7.1. @DependsOn Also Affects Singleton Destruction Order

For singletons, a `depends-on` relationship also affects destruction order. The dependent bean is destroyed before the bean it depends on.

If `searchIndex` depends on `schemaInitializer`, when the context closes, Spring destroys `searchIndex` first and then `schemaInitializer`. This is helpful when a dependent bean must release resources before the underlying component shuts down.

### 7.2. Do Not Use @DependsOn Instead of Constructor Injection

If bean B actually needs bean A to operate, inject A:

~~~java
@Bean
CatalogService catalogService(CatalogRepository repository) {
    return new CatalogService(repository);
}
~~~

Do not write:

~~~java
@Bean
@DependsOn("catalogRepository")
CatalogService catalogService() {
    return new CatalogService();
}
~~~

when the service still needs the repository and has no explicit way to access it. `@DependsOn` only guarantees initialization order; it does not inject dependencies and does not replace the dependency graph.

### 7.3. Avoid Long @DependsOn Chains

A configuration with many beans linked by `@DependsOn` can become hard to maintain:

~~~java
@Bean
@DependsOn({"databaseReady", "messageBrokerReady", "cacheReady"})
OrderProcessor orderProcessor() {
    return new OrderProcessor();
}
~~~

If `OrderProcessor` needs those components, inject them directly via constructor. Use `@DependsOn` for side effects or indirect initialization ordering, not as a second dependency injection system.

## 8. @Order Does Not Control Singleton Startup Order

`@Order` is frequently misunderstood as an “initialize first” annotation. Spring Framework documentation draws a clear distinction:

- `@Order` can sort beans when injected into arrays or collections.
- `@Order` on configuration classes affects configuration class processing order.
- `@Order` does not control singleton initialization order.
- Singleton initialization order is based on dependency relationships and `@DependsOn`.

Collection ordering example:

~~~java
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

public interface StartupTask {
    void execute();
}

@Component
@Order(10)
class ValidateConfigurationTask implements StartupTask {
    @Override
    public void execute() {
        // Validate configuration.
    }
}

@Component
@Order(20)
class WarmupCacheTask implements StartupTask {
    @Override
    public void execute() {
        // Warm up cache.
    }
}
~~~

A coordinator bean receives the list:

~~~java
import java.util.List;
import org.springframework.stereotype.Component;

@Component
class StartupTaskRunner {

    private final List<StartupTask> tasks;

    StartupTaskRunner(List<StartupTask> tasks) {
        this.tasks = tasks;
    }

    void runTasks() {
        tasks.forEach(StartupTask::execute);
    }
}
~~~

The `tasks` list is sorted according to the beans' order values. However, that does not mean the `ValidateConfigurationTask` instance was initialized before every other bean in the ApplicationContext.

If tasks must run sequentially, invoke them in order inside a coordinator like the example above, or use an appropriate lifecycle hook. Do not rely on singleton creation order to execute business logic.

### 8.1. Lower Order Values Have Higher Priority

With `Ordered` and `@Order`, lower numeric values have higher priority. When unspecified, the default order is `Ordered.LOWEST_PRECEDENCE`.

Example:

~~~java
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

interface EventHandler {
}

@Order(0)
@Component
class FirstHandler implements EventHandler {
}

@Order(100)
@Component
class LaterHandler implements EventHandler {
}
~~~

When these beans are injected into an order-aware collection, `FirstHandler` precedes `LaterHandler`. Do not infer that they were instantiated in that order.

If beans do not declare `@Order` or `Ordered`, element order typically follows the registration order of their corresponding BeanDefinitions in the container. This is still collection injection order, not a contract about singleton instantiation timing.

### 8.2. @Primary Is Also Not Ordering

`@Primary` helps Spring pick one bean when multiple candidates of the same type exist at a single injection point. It does not control when beans are initialized and does not sort collections.

| Annotation | Responsibility |
| --- | --- |
| `@Order` | Sorts precedence at injection points that support ordering |
| `@Primary` | Picks a preferred candidate when a single bean is needed |
| `@Qualifier` | Narrows the candidate set by qualifier |
| `@DependsOn` | Forces the specified beans to initialize before the current bean |
| Constructor/method injection | Declares direct dependencies |

## 9. @Lazy and Singleton Creation Timing

By default, an ApplicationContext eagerly pre-instantiates non-lazy singletons during context refresh. This helps catch configuration, dependency, or environment connection errors early.

You can defer a bean with `@Lazy`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Lazy;

@Configuration(proxyBeanMethods = false)
public class ReportingConfiguration {

    @Bean
    @Lazy
    ExpensiveReportGenerator reportGenerator() {
        return new ExpensiveReportGenerator();
    }
}
~~~

This bean is created when first requested, rather than being pre-instantiated alongside other eager singletons.

### 9.1. A Lazy Bean That Is a Dependency of an Eager Singleton

If a lazy bean is a dependency of a non-lazy singleton, Spring still has to create the lazy bean to inject it into that singleton during startup.

~~~java
@Bean
@Lazy
ReportRepository reportRepository() {
    return new ReportRepository();
}

@Bean
ReportService reportService(ReportRepository repository) {
    return new ReportService(repository);
}
~~~

In this example, `reportService` is an eager singleton and requires `reportRepository`. Therefore the repository is created during context startup even though the method declares `@Lazy`.

### 9.2. @Lazy at an Injection Point

You can place `@Lazy` at an injection point to inject a proxy that defers fetching the real bean until it is used:

~~~java
@Service
public class AdminService {

    private final HeavyAnalyticsService analyticsService;

    public AdminService(@Lazy HeavyAnalyticsService analyticsService) {
        this.analyticsService = analyticsService;
    }
}
~~~

This is useful when a dependency is only used on certain code paths. However, a lazy proxy does not solve a circular dependency from a design standpoint and should not be used to hide an unhealthy dependency graph.

## 10. Bean Lifecycle and Callback Order

Once the container decides to create a bean, a singleton typically passes through these main steps:

1. Instance creation (constructor or factory method).
2. Dependency and property injection.
3. Invocation of applicable Aware callbacks.
4. Running `BeanPostProcessor` before initialization.
5. Invoking `@PostConstruct`.
6. Invoking `InitializingBean.afterPropertiesSet()` if the bean implements the interface.
7. Invoking any declared custom init method.
8. Running `BeanPostProcessor` after initialization.
9. Placing the completed bean in the container for use.

These callbacks belong to each individual bean's lifecycle. `@PostConstruct` on bean A does not mean every other singleton in the context has already been created.

### 10.1. @PostConstruct Is Not an After-All-Singletons Hook

Example:

~~~java
import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Component;

@Component
public class CacheInitializer {

    @PostConstruct
    void initialize() {
        // Initialize this bean's internal state.
    }
}
~~~

`@PostConstruct` is suitable for validating bean state or preparing internal data structures after dependencies have been injected. Do not use it assuming all other beans are finished initializing, or to arbitrarily look up other beans via the ApplicationContext.

### 10.2. SmartInitializingSingleton Runs After Regular Singletons

If you need a callback after regular eager singletons have been created, implement `SmartInitializingSingleton`:

~~~java
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.stereotype.Component;

@Component
public class StartupSummary implements SmartInitializingSingleton {

    @Override
    public void afterSingletonsInstantiated() {
        // Regular singletons have been pre-instantiated.
        // Initialization state can be aggregated here.
    }
}
~~~

This callback is appropriate for aggregating or checking state after the singleton pre-instantiation phase. It does not replace `@DependsOn` for a dependency that must exist before another bean is created.

### 10.3. ContextRefreshedEvent Marks Context Refresh Completion

You can listen for the event:

~~~java
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ApplicationReadyForContextListener {

    @EventListener
    public void onContextRefreshed(ContextRefreshedEvent event) {
        // The corresponding context has finished its refresh phase.
    }
}
~~~

An application can receive multiple `ContextRefreshedEvent` instances if there is a context hierarchy or special context refreshes. If you only care about when a Boot application is ready to receive traffic, consider `ApplicationReadyEvent` and readiness state instead of treating every `ContextRefreshedEvent` as a single startup event.

## 11. BeanFactoryPostProcessor and BeanPostProcessor Have Their Own Ordering

These two extension points often appear when customizing auto-configuration. They operate at different stages.

| Extension point | Target | Timing |
| --- | --- | --- |
| BeanDefinitionRegistryPostProcessor | Registry and BeanDefinitions | Before regular BeanFactoryPostProcessors |
| BeanFactoryPostProcessor | BeanDefinition/configuration metadata | After definitions are registered, before regular application beans are created |
| BeanPostProcessor | Bean instances | During creation and initialization of each bean |

### 11.1. BeanFactoryPostProcessor Modifies Metadata

Example of a post-processor that inspects or adjusts a BeanDefinition before the container creates application beans:

~~~java
import org.springframework.beans.BeansException;
import org.springframework.beans.factory.config.BeanFactoryPostProcessor;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.core.Ordered;

public class CatalogDefinitionPostProcessor
        implements BeanFactoryPostProcessor, Ordered {

    @Override
    public int getOrder() {
        return 100;
    }

    @Override
    public void postProcessBeanFactory(
            ConfigurableListableBeanFactory beanFactory)
            throws BeansException {

        if (beanFactory.containsBeanDefinition("catalogClient")) {
            // Read or adjust the BeanDefinition if genuinely needed.
        }
    }
}
~~~

Spring can sort post-processors implementing `PriorityOrdered` and `Ordered`. This is extension-point execution order, not business-bean initialization order.

Avoid calling `beanFactory.getBean(...)` to fetch application beans from inside a `BeanFactoryPostProcessor`. Doing so can instantiate beans prematurely, before all post-processors are registered and applied, bypassing part of standard processing.

### 11.2. Registering Post-Processors via @Bean Should Use static

If a `@Bean` method returns a `BeanFactoryPostProcessor`, declare the method as `static`:

~~~java
@Configuration(proxyBeanMethods = false)
public class CatalogPostProcessorConfiguration {

    @Bean
    static CatalogDefinitionPostProcessor catalogDefinitionPostProcessor() {
        return new CatalogDefinitionPostProcessor();
    }
}
~~~

Reason: the container must instantiate `BeanFactoryPostProcessor` beans very early to process metadata. If it has to instantiate the enclosing configuration class prematurely, some annotation injection or lifecycle processing on that configuration class may not have run yet.

The same consideration applies to `BeanPostProcessor` beans declared via `@Bean`; processors and their direct dependencies are initialized early. Avoid making them depend on regular application beans.

### 11.3. BeanPostProcessor Processes Instances

Example:

~~~java
import org.springframework.beans.BeansException;
import org.springframework.beans.factory.config.BeanPostProcessor;

public class CatalogTracingPostProcessor implements BeanPostProcessor {

    @Override
    public Object postProcessBeforeInitialization(
            Object bean,
            String beanName) throws BeansException {
        return bean;
    }

    @Override
    public Object postProcessAfterInitialization(
            Object bean,
            String beanName) throws BeansException {
        return bean;
    }
}
~~~

A `BeanPostProcessor` can wrap beans in proxies, add behavior, or process annotations. Ordering among multiple processors affects how they transform an instance, not whether the corresponding business bean initializes before or after other beans.

## 12. @Configuration Full Mode vs. Lite Mode

One detail related to bean definitions is how Spring handles calls between `@Bean` methods.

With default `@Configuration`, Spring uses an enhanced configuration class to ensure internal calls to `@Bean` methods are routed through the container. This preserves scope and singleton semantics.

~~~java
@Configuration
public class FullConfiguration {

    @Bean
    CatalogRepository catalogRepository() {
        return new CatalogRepository();
    }

    @Bean
    CatalogService catalogService() {
        return new CatalogService(catalogRepository());
    }
}
~~~

In full mode, the call `catalogRepository()` is intercepted to retrieve the bean from the container rather than instantiating a second singleton object.

If you use:

~~~java
@Configuration(proxyBeanMethods = false)
public class LiteConfiguration {

    @Bean
    CatalogRepository catalogRepository() {
        return new CatalogRepository();
    }

    @Bean
    CatalogService catalogService() {
        return new CatalogService(catalogRepository());
    }
}
~~~

`@Bean` methods run in lite mode. The direct Java call `catalogRepository()` is not intercepted; it may create a new object instead of fetching the container-managed singleton.

In lite mode, use method parameters:

~~~java
@Configuration(proxyBeanMethods = false)
public class RecommendedConfiguration {

    @Bean
    CatalogRepository catalogRepository() {
        return new CatalogRepository();
    }

    @Bean
    CatalogService catalogService(CatalogRepository repository) {
        return new CatalogService(repository);
    }
}
~~~

Factory method parameters express dependencies explicitly and work consistently in both full and lite configurations.

## 13. Circular Dependencies Are Not an Ordering Tool

If A requires B and B also requires A via constructor, Spring cannot create either bean first to complete the other's constructor. This is a circular dependency.

~~~mermaid
flowchart LR
    A["Bean A"] --> B["Bean B"]
    B --> A
~~~

Anti-pattern example:

~~~java
@Component
class OrderService {
    OrderService(PaymentService paymentService) {
    }
}

@Component
class PaymentService {
    PaymentService(OrderService orderService) {
    }
}
~~~

Constructor cycles typically cause bean creation to fail. Some forms of circular references via setters/fields can be resolved under certain singleton conditions, but they depend on proxy mechanisms and container configuration; do not rely on them as normal design.

Modern Spring Boot discourages circular references by default and may reject them. Break dependency cycles by:
- Extracting shared responsibility into a third service.
- Moving common logic into an independent abstraction.
- Using events to decouple when synchronous interaction is unnecessary.
- Using `ObjectProvider` or lazy lookup when there is a clear architectural reason.
- Inverting a dependency via an appropriate interface.

Do not use `@DependsOn` to mask a circular dependency. It adds ordering constraints without resolving the logical cycle.

## 14. Practical Example: Schema Must Be Ready Before Index

Suppose the application creates a search index that requires the database schema to be prepared first. This is an indirect initialization relationship because `SearchIndex` does not need to hold a reference to `SchemaInitializer`.

Configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.DependsOn;

@Configuration(proxyBeanMethods = false)
public class SearchInfrastructureConfiguration {

    @Bean
    SchemaInitializer schemaInitializer() {
        return new SchemaInitializer();
    }

    @Bean
    @DependsOn("schemaInitializer")
    SearchIndex searchIndex() {
        return new SearchIndex();
    }

    @Bean
    SearchService searchService(SearchIndex searchIndex) {
        return new SearchService(searchIndex);
    }
}
~~~

Dependencies/ordering:
- `schemaInitializer` must be initialized before `searchIndex` due to `@DependsOn`.
- `searchService` requires `searchIndex`, so dependency injection ensures the index exists before the service.
- No `@Order` is needed on the configuration class or bean methods.

If `SearchService` actually needs to call `SchemaInitializer`, inject that dependency instead of relying solely on `@DependsOn`.

### 14.1. Testing Initialization Order

A simple test can record when factory methods execute:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.DependsOn;

class BeanStartupOrderTests {

    static final List<String> events = new ArrayList<>();

    static class SchemaInitializer {
    }

    static class SearchIndex {
    }

    @Configuration(proxyBeanMethods = false)
    static class TestConfiguration {

        @Bean
        SchemaInitializer schemaInitializer() {
            events.add("schema");
            return new SchemaInitializer();
        }

        @Bean
        @DependsOn("schemaInitializer")
        SearchIndex searchIndex() {
            events.add("index");
            return new SearchIndex();
        }
    }

    @Test
    void initializesSchemaBeforeSearchIndex() {
        events.clear();

        try (var context =
                     new AnnotationConfigApplicationContext(TestConfiguration.class)) {

            assertThat(events.indexOf("schema"))
                    .isLessThan(events.indexOf("index"));
        }
    }
}
~~~

The test verifies the declared relationship. In parallel test suites, avoid using a shared static mutable list and instead use a per-context event recorder.

### 14.2. Testing That @Order Does Not Dictate Startup

You can write another test for two independent beans to verify collection injection order rather than constructor invocation order:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;

class OrderInjectionTests {

    interface EventHandler {
    }

    static class FirstHandler implements EventHandler {
    }

    static class SecondHandler implements EventHandler {
    }

    @Configuration(proxyBeanMethods = false)
    static class HandlerConfiguration {

        @Bean
        @Order(20)
        EventHandler secondHandler() {
            return new SecondHandler();
        }

        @Bean
        @Order(10)
        EventHandler firstHandler() {
            return new FirstHandler();
        }
    }

    @Test
    void ordersCollectionInjectionWithoutDefiningStartupOrder() {
        try (var context =
                     new AnnotationConfigApplicationContext(HandlerConfiguration.class)) {

            List<EventHandler> handlers = context.getBeanProvider(EventHandler.class)
                    .orderedStream()
                    .collect(Collectors.toList());

            assertThat(handlers)
                    .extracting(Object::getClass)
                    .containsExactly(FirstHandler.class, SecondHandler.class);
        }
    }
}
~~~

This test verifies element ordering in collection injection. It neither tests nor establishes the singleton initialization order of `FirstHandler` and `SecondHandler`.

## 15. How to Diagnose Ordering in Real Applications

When startup does not follow expectations, observe each phase rather than adding annotations at random.

### 15.1. Check Loaded Configurations

Verify:
- Was the configuration class imported or component-scanned?
- Is the auto-configuration listed in the imports file?
- Did classpath/property/bean conditions match?
- Was the BeanDefinition registered?
- Are there exclusions or overrides?

With Spring Boot, you can inspect the condition report when running in debug mode to see which auto-configurations matched or did not match. This helps isolate issues during the configuration-application phase.

### 15.2. Inspect the Dependency Graph

If a bean is registered but initializes unexpectedly:
- Check constructor/factory method parameters.
- Verify bean names in `@DependsOn`.
- Check scope and lazy-init settings.
- Look for dependency cycles.
- Check whether a `BeanFactoryPostProcessor` calls `getBean` too early.
- Check whether a `BeanPostProcessor` depends on business beans.

### 15.3. Intentional Lifecycle Logging

You can log inside constructors, factory methods, `@PostConstruct`, or lifecycle callbacks to observe actual timing. Use logs strictly as an observation tool; do not turn the log order of independent beans into an architectural contract.

A fast-initializing bean may appear before another bean in one run, yet the order can change when a new dependency or auto-configuration is added.

## 16. Common Misconceptions

| Claim | Reality |
| --- | --- |
| A configuration class with `@Order(1)` creates all its beans first | `@Order` only affects configuration class processing order |
| The `@Bean` method declared first in a file runs first | There is no initialization contract based on source line order |
| `@Order` on a bean controls singleton startup | `@Order` primarily sorts precedence at order-aware injection points |
| `@Primary` causes a bean to be created first | `@Primary` only picks a candidate at a single-bean injection point |
| `@DependsOn` replaces constructor injection | `@DependsOn` only forces initialization order; it does not pass dependencies |
| `AutoConfigureAfter` makes the earlier configuration's beans instantiate first | It orders auto-configuration application / bean definition registration |
| `@Lazy` always delays a bean until first use | If an eager singleton needs a lazy bean, that bean is still created at startup |
| `@PostConstruct` runs after all beans are created | It runs within each individual bean's lifecycle |
| `ContextRefreshedEvent` and `ApplicationReadyEvent` are the same | They are distinct lifecycle milestones |
| Circular dependencies can be solved with `@DependsOn` | `@DependsOn` cannot break a logical dependency cycle |

## 17. Principles for Customizing Auto-Configuration

When building or extending auto-configuration in Spring Cloud / Spring Boot:

- Use `@AutoConfigureBefore`/`@AutoConfigureAfter` when ordering definitions with other auto-configurations.
- Use `@AutoConfigureOrder` for independent auto-configurations needing relative order.
- Use `@ConditionalOnMissingBean` to let applications replace default beans.
- Use constructor or method injection to express direct dependencies.
- Use `@DependsOn` for indirect initialization dependencies.
- Use `@Lazy` to defer initialization when there is a clear reason.
- Use `@Order` for collection injection order or extension points that support ordering.
- Use `BeanFactoryPostProcessor` to modify metadata and `BeanPostProcessor` to process instances.
- Declare `static` factory methods when registering post-processors via `@Bean`.
- Avoid circular dependencies and premature `getBean` calls.
- Test auto-configuration conditions, dependency graphs, and lifecycles separately.

## 18. Checklist When Facing Ordering Issues

- [ ] Have you identified whether the issue is configuration processing order, BeanDefinition registration, or instance creation?
- [ ] Was the configuration class imported/scanned/loaded via the proper mechanism?
- [ ] Does the auto-configuration imports file list the class?
- [ ] Do `@ConditionalOn...` conditions match?
- [ ] Have `before`/`after` been used for required auto-configuration ordering?
- [ ] Are direct bean dependencies declared via constructors or factory method parameters?
- [ ] Is there a side-effect dependency requiring `@DependsOn`?
- [ ] Is a lazy bean being pulled into startup by an eager singleton?
- [ ] Is `@Order` being confused with startup ordering?
- [ ] Is a `BeanFactoryPostProcessor` or `BeanPostProcessor` created too early or depending on inappropriate beans?
- [ ] Is there a circular dependency?
- [ ] Do tests verify the exact type of ordering required?

## Takeaways

Spring processes configurations and registers BeanDefinitions before instantiating most application beans. `@Order` on configuration classes affects configuration processing order; auto-configuration ordering affects bean definition order. **Singleton initialization order is determined by the dependency graph and `@DependsOn`**, while `@Order` mainly sorts beans at order-aware injection points. Use dependency injection for direct relationships, `@DependsOn` for indirect initialization dependencies, `@Lazy` for intentional deferral, and stage-appropriate lifecycle callbacks so you never depend on accidental ordering.

## References

- Spring Framework – Using @Autowired and ordering at injection points: https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html
- Spring Framework – Composing Java-based Configurations: https://docs.spring.io/spring-framework/reference/core/beans/java/composing-configuration-classes.html
- Spring Framework – Using depends-on: https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-dependson.html
- Spring Framework – Lazy-initialized Beans: https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-lazy-init.html
- Spring Framework – Container Extension Points: https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html
- Spring Framework – Customizing the Nature of a Bean: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Spring Boot – Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
