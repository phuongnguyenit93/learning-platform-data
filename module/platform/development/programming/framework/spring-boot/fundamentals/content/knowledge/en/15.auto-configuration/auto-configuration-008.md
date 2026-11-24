# Auto-configuration ordering and how it differs from bean creation order

Spring Boot can automatically load many configuration classes from starters and libraries. When an application adds web, database, security, or integration libraries, multiple auto-configurations participate in building the application context. Sometimes one configuration needs to be processed before another so that conditions like `@ConditionalOnBean` or `@ConditionalOnMissingBean` see the right bean definitions.

Spring Boot provides mechanisms such as `@AutoConfiguration(before = ...)`, `@AutoConfiguration(after = ...)`, and `@AutoConfigureOrder` to arrange the **processing order of auto-configuration classes**. This must be distinguished from **bean instance creation order**. An auto-configuration being processed first does not guarantee that constructors of all beans in that configuration run before all beans in another configuration.

Bean creation order is governed primarily by dependency relationships, scope, lazy initialization, and lifecycle directives such as `@DependsOn`. Meanwhile, `@Order` usually controls the order of beans in collections or certain processing mechanisms that support ordering; it is not a general tool for controlling when singletons are instantiated.

## 1. What is auto-configuration in the startup process?

A Spring Boot application typically has a main class:

~~~java
@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

`@SpringBootApplication` includes `@EnableAutoConfiguration`. On startup, Spring Boot locates auto-configurations published by libraries, evaluates conditions, and imports matching configurations into the application context.

In Spring Boot 3.x, auto-configuration libraries usually publish classes through the file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Example file in a JAR:

~~~text
com.example.cache.CacheAutoConfiguration
com.example.metrics.MetricsAutoConfiguration
com.example.audit.AuditAutoConfiguration
~~~

These classes are brought into configuration processing. They can declare default beans, integration configurations, and conditions so they activate only when the classpath, properties, or beans match.

High-level process:

~~~text
SpringApplication.run(...)
        |
        v
Read Environment and prepare BeanFactory
        |
        v
Parse application configurations
        |
        v
Discover auto-configuration candidates
        |
        v
Filter candidates by exclusions and conditions
        |
        v
Sort auto-configuration processing order
        |
        v
Register bean definitions
        |
        v
Instantiate singletons by dependencies/lifecycle
        |
        v
Context refresh complete
~~~

These are conceptual stages; internally Spring has many steps for processing configuration classes, bean definitions, and post-processors. What to remember is that **auto-configuration is the process of selecting and registering configurations/bean definitions**, whereas creating instances is the subsequent bean management phase.

## 2. Why does auto-configuration need ordering?

Suppose one library provides default database configuration, while another library provides a bean using `DataSource` if available:

~~~text
DataSourceAutoConfiguration
        |
        | registers DataSource bean definition
        v
DatabaseMetricsAutoConfiguration
        |
        | @ConditionalOnBean(DataSource.class)
        v
DatabaseMetrics bean definition
~~~

If the metrics configuration were processed before the DataSource configuration registered its bean definition, the `@ConditionalOnBean(DataSource.class)` condition might not see the bean it needs yet. The metrics configuration could be skipped even though the application will eventually have a DataSource.

Therefore, auto-configuration ordering can be used to ensure **configurations providing foundational beans are processed before configurations that depend on those beans**.

This is especially important for conditions such as:

- `@ConditionalOnBean`: activates only when a matching bean is already in the registry at the time the condition is evaluated.
- `@ConditionalOnMissingBean`: provides a default bean only if no matching bean exists yet.
- Conditions/selectors that depend on configurations processed earlier.

Auto-configuration order helps conditions see bean definitions at the right time. It is not a mechanism for requiring objects to be created or methods to run in business order.

## 3. @AutoConfiguration(before = ...) and after = ...

In Spring Boot 3.x, auto-configuration classes typically use `@AutoConfiguration`:

~~~java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;

@AutoConfiguration(after = DataSourceAutoConfiguration.class)
public class DatabaseMetricsAutoConfiguration {
    // Configuration that needs to be processed after DataSourceAutoConfiguration.
}
~~~

The `after` attribute indicates this configuration should be processed after the specified class. Similarly, `before` indicates this configuration should be processed before the specified class.

For example:

~~~java
@AutoConfiguration(before = MetricsAutoConfiguration.class)
public class EarlyMetricsDefaultsAutoConfiguration {
}
~~~

The two attributes carry relative semantics:

| Attribute | Meaning |
|---|---|
| `before` | Places the current auto-configuration before the specified classes |
| `beforeName` | Same as `before`, referencing class names as strings |
| `after` | Places the current auto-configuration after the specified classes |
| `afterName` | Same as `after`, referencing class names as strings |

Use class literals when the dependency is directly present and poses no class-loading issues. Use string class names when you want to avoid compile-time dependencies on an optional class or a library that may not be present.

### 3.1. Example of a configuration depending on DataSource

Suppose a metrics library needs to provide a bean when the application has a `DataSource`:

~~~java
package com.example.metrics.autoconfigure;

import javax.sql.DataSource;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(after = DataSourceAutoConfiguration.class)
public class DatabaseMetricsAutoConfiguration {

    @Bean
    @ConditionalOnBean(DataSource.class)
    DatabaseMetrics databaseMetrics(DataSource dataSource) {
        return new DatabaseMetrics(dataSource);
    }
}
~~~

`DataSource` belongs to the Java SE/JDBC package `javax.sql` and still uses this namespace on modern JDKs; do not change it to `jakarta.sql`.

Meaning:

1. `DataSourceAutoConfiguration` is processed first.
2. The DataSource bean definition gets the opportunity to be registered.
3. The `@ConditionalOnBean(DataSource.class)` condition is evaluated in the metrics configuration.
4. If a matching bean exists, the `databaseMetrics` method is registered.
5. When the metrics bean is created, Spring injects DataSource via the method parameter.

The example assumes the `DatabaseMetrics` class and required dependencies are provided. `after` ordering does not create a DataSource itself; if the datasource configuration is excluded or its conditions are not met, metrics still has no bean to use.

### 3.2. before and after only create relative relationships

If A declares `before = B`, that only says A should be processed before B. It does not determine A's absolute position relative to every other auto-configuration.

~~~text
A  --->  B
     (A before B)

C is not constrained relative to A/B:
    C may sit elsewhere depending on the remaining ordering relationships.
~~~

When multiple configurations declare before/after relationships, Spring Boot constructs a valid order from the declared constraints. Avoid creating excessive cross-relationships or ordering cycles; good design usually only needs to describe meaningful direct dependencies.

## 4. When is @AutoConfigureOrder used?

`@AutoConfigureOrder` supplies a general numeric order value for an auto-configuration:

~~~java
import org.springframework.boot.autoconfigure.AutoConfigureOrder;
import org.springframework.core.Ordered;

@AutoConfigureOrder(Ordered.HIGHEST_PRECEDENCE)
@AutoConfiguration
public class CoreDefaultsAutoConfiguration {
}
~~~

Lower order values have higher priority (standing earlier) than higher values according to Spring's ordering convention. `Ordered.HIGHEST_PRECEDENCE` indicates very high priority; `Ordered.LOWEST_PRECEDENCE` indicates lowest priority.

`@AutoConfigureOrder` is useful when a general ordering hint is needed among auto-configurations with no specific class relationship. However, if the goal is "configuration X must run after configuration Y", `after`/`before` relationships are usually easier to read and express intent more precisely.

In Spring Boot 3.x code, `@AutoConfiguration(before = ..., after = ...)` is usually the direct way to declare specific ordering relationships. `@AutoConfigureOrder` remains an ordering tool, though you should not use it as an arbitrary number to force bean instantiation order.

### Do not confuse with @Order

`@AutoConfigureOrder` and `@Order` look similar in name, yet differ in semantic scope:

| Annotation | What it orders | Target |
|---|---|---|
| `@AutoConfigureOrder` | Auto-configuration classes | Processing order of auto-configurations |
| `@Order` | Beans/objects in mechanisms supporting ordering | Priority order when injecting collections or processing lists |

Putting `@Order(1)` on a service does not mean that service will be created before every service annotated with `@Order(2)`.

## 5. Auto-configuration ordering affects bean definition registration

An auto-configuration class typically contains `@Bean` methods:

~~~java
@AutoConfiguration
public class SearchAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    SearchClient searchClient() {
        return new SearchClient();
    }
}
~~~

When the configuration class is processed, Spring reads the configuration methods and registers bean definitions into the BeanFactory. At this stage, the container knows what beans by name/type can be created, yet bean instances have not necessarily been instantiated.

This allows a subsequent configuration to use conditions like `@ConditionalOnBean` or `@ConditionalOnMissingBean` to inspect already-registered bean definitions.

For example:

~~~java
@AutoConfiguration
public class SearchMetricsAutoConfiguration {

    @Bean
    @ConditionalOnBean(SearchClient.class)
    SearchMetrics searchMetrics(SearchClient client) {
        return new SearchMetrics(client);
    }
}
~~~

If `SearchAutoConfiguration` is ordered before `SearchMetricsAutoConfiguration`, the condition can see the `SearchClient` definition. Yet **registering the SearchClient definition does not mean the SearchClient constructor has already run at that moment**.

This is a foundational distinction:

- **Bean definition registration:** the container records how to create the bean, its name, scope, conditions, and metadata.
- **Bean instance creation:** the container executes constructors/factory methods, injects dependencies, and runs callbacks.

Auto-configuration order primarily coordinates the first step.

## 6. How is bean creation order determined?

Once bean definitions are registered, Spring creates instances based on demand and lifecycle.

Key factors:

1. **Dependency graph:** if bean B needs bean A via constructor or property injection, A must be resolved before B finishes initializing.
2. **Scope:** singleton, prototype, request, and other scopes have different creation timings.
3. **Lazy initialization:** lazy beans may not be created until requested.
4. **@DependsOn:** declares initialization dependencies by bean name when there is no direct dependency injection.
5. **Callbacks/lifecycle contracts:** Spring invokes initialization and destruction callbacks according to the bean's lifecycle.

Typical dependency example:

~~~java
@Configuration(proxyBeanMethods = false)
class OrderConfiguration {

    @Bean
    OrderRepository orderRepository() {
        return new OrderRepository();
    }

    @Bean
    OrderService orderService(OrderRepository repository) {
        return new OrderService(repository);
    }
}
~~~

When Spring creates `OrderService`, it needs `OrderRepository` to pass to the factory method. Therefore, the repository is resolved and initialized before the service. There is no need to use `@DependsOn` or ordering annotations for relationships already expressed via dependency injection.

~~~text
Request to create OrderService
          |
          v
 Needs OrderRepository
          |
          v
 Create OrderRepository
          |
          v
 Pass repository into factory method
          |
          v
 Create OrderService
~~~

This relationship expresses a real dependency, so Spring can manage the order properly and detect many circular dependency cases.

## 7. @DependsOn is used when explicit initialization order is needed

Sometimes a bean depends on an **initialization side effect** of another bean without needing to inject that instance. For example, one bean initializes a data directory or registers a shared resource before another bean starts:

~~~java
@Configuration(proxyBeanMethods = false)
class StartupConfiguration {

    @Bean
    DataDirectoryInitializer dataDirectoryInitializer() {
        return new DataDirectoryInitializer();
    }

    @Bean
    @DependsOn("dataDirectoryInitializer")
    FileCatalog fileCatalog() {
        return new FileCatalog();
    }
}
~~~

`@DependsOn("dataDirectoryInitializer")` requires the `dataDirectoryInitializer` bean to be initialized before the `fileCatalog` bean. When these singletons are destroyed during container shutdown, the depended-on bean is destroyed in reverse order so the dependent bean is destroyed before the bean it relies on.

`@DependsOn` can be placed on a component class or a `@Bean` method. It accepts bean names, so ensure the specified names are accurate.

### When should @DependsOn not be used?

If bean B already injects bean A:

~~~java
@Bean
FileCatalog fileCatalog(DataDirectoryInitializer initializer) {
    return new FileCatalog(initializer);
}
~~~

then dependency injection already expresses the dependency relationship. Adding `@DependsOn` is usually redundant.

Do not use `@DependsOn` to sort all services into an arbitrary order or to hide an unclearly designed dependency. If B genuinely needs A, inject A. If only an initialization side effect is needed, consider whether that side effect should be modeled as an explicit dependency or lifecycle contract.

## 8. @Order does not control singleton creation order

`@Order` is typically used when Spring needs to sort a set of objects. For example, multiple handlers implementing an interface:

~~~java
public interface RequestHandler {
    void handle(Request request);
}
~~~

~~~java
@Component
@Order(10)
class AuthenticationHandler implements RequestHandler {
    public void handle(Request request) {
        // Authenticate.
    }
}
~~~

~~~java
@Component
@Order(20)
class AuthorizationHandler implements RequestHandler {
    public void handle(Request request) {
        // Authorize.
    }
}
~~~

A bean consuming the collection:

~~~java
@Component
class RequestPipeline {
    private final List<RequestHandler> handlers;

    RequestPipeline(List<RequestHandler> handlers) {
        this.handlers = handlers;
    }

    void process(Request request) {
        handlers.forEach(handler -> handler.handle(request));
    }
}
~~~

Spring sorts the elements in the collection according to their order. `AuthenticationHandler` with order 10 comes before `AuthorizationHandler` with order 20 in the list. However, that **does not prove AuthenticationHandler's constructor ran before AuthorizationHandler's constructor**.

`@Order` can affect:

- Element order in injected arrays/lists.
- Bean order in `ObjectProvider.orderedStream()`.
- Spring extension points documented to support `Ordered` or `@Order`.
- Specific processing chains such as interceptors, resolvers, or post-processors when that API supports ordering.

It is not a general rule for singleton instantiation. If bean A must be created before bean B, express a dependency or use `@DependsOn` where appropriate.

## 9. @AutoConfiguration, @Order, and @DependsOn: quick comparison

| Mechanism | What does it order? | Controls when bean instances are created? |
|---|---|---|
| `@AutoConfiguration(before/after)` | Processing order of auto-configuration classes | No |
| `@AutoConfigureOrder` | Processing priority of auto-configuration classes | No |
| `@Order` / `Ordered` | Order in collections or extension points supporting ordering | Not a general mechanism |
| Constructor/bean method dependency | Dependency relationship between beans | Yes: dependency is resolved before the bean needing it |
| `@DependsOn` | Initialization order by bean name | Yes: specified bean must initialize before the dependent bean |
| `@Lazy` | When a bean is requested/initialized | Affects timing, not priority order |

An easy-to-remember example:

~~~text
AutoConfiguration A before B
    -> registers configurations/bean definitions in order A then B

Bean X needs Bean Y via constructor
    -> creates/resolves Y before completing X

Bean M @Order(1), Bean N @Order(2)
    -> M comes before N in ordered collections
    -> does not imply M was instantiated before N
~~~

## 10. Why shouldn't auto-configuration order be used to fix initialization order bugs?

Suppose a bean needs the database connection to be open:

~~~java
@Bean
DatabaseReportService databaseReportService() {
    return new DatabaseReportService();
}
~~~

If `DatabaseReportService`'s constructor accesses another bean via global lookup, relies on a side effect, or opens connections itself, simply adding:

~~~java
@AutoConfiguration(after = DataSourceAutoConfiguration.class)
~~~

is not a good way to express the dependency. It only orders the configuration class, without guaranteeing that instances or side effects of all related beans have finished as intended.

Inject the dependency instead:

~~~java
@Bean
DatabaseReportService databaseReportService(DataSource dataSource) {
    return new DatabaseReportService(dataSource);
}
~~~

If schema or baseline data needs to be initialized before the service uses it, express a dependency on an initializer or use Spring Boot's database initialization mechanism. Do not rely on import order as a substitute for lifecycle.

## 11. Auto-configuration order is not a global application order

Auto-configuration ordering applies to configurations brought into the auto-configuration pipeline. It is not a mechanism to sort every `@Configuration` class in the project, nor is it a global order across all beans registered via component scan, `@Import`, or user configuration.

Some limitations:

- `before`/`after` relationships constrain only the involved auto-configuration classes.
- A configuration may be skipped by `exclude` or unmatched conditions.
- One auto-configuration can register multiple beans, yet each bean has its own dependency graph.
- Lazy beans may not be created during startup.
- Prototypes are created when requested from the container, not on a singleton initialization schedule.
- A bean may be instantiated early if a condition directly references a bean instance; that is a different issue from auto-configuration order.

Therefore, if you want to control when a bean is created, start from scope and the dependency graph, not by tweaking an auto-configuration order value.

## 12. Example of a library providing ordered auto-configuration

Suppose a library provides cache defaults and the cache configuration needs to run after the foundational cache manager configuration:

~~~java
package com.example.cache.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.cache.CacheAutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(after = CacheAutoConfiguration.class)
public class CustomCacheDefaultsAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(CacheKeyGenerator.class)
    CacheKeyGenerator cacheKeyGenerator() {
        return new DefaultCacheKeyGenerator();
    }
}
~~~

The library registers the class in:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

~~~text
com.example.cache.autoconfigure.CustomCacheDefaultsAutoConfiguration
~~~

`after = CacheAutoConfiguration.class` indicates this default configuration should be processed after Boot's cache configuration. `@ConditionalOnMissingBean` lets the application provide its own `CacheKeyGenerator`; if a matching bean already exists, the default bean is not registered.

In a real library, verify the cache APIs and auto-configurations of the Boot version in use; the example above illustrates expressing ordering and back-off, not that every application has to import cache auto-configuration manually.

### 12.1. Why should library auto-configurations use @AutoConfiguration?

`@AutoConfiguration` is designed for Boot's automatic configuration classes and sets `proxyBeanMethods = false`. Libraries typically publish them via `AutoConfiguration.imports` so Boot can discover, order, and apply conditions to them.

Do not place library auto-configuration classes in the application's broad component scan like regular components. Doing so can cause them to be processed outside the auto-configuration discovery/ordering pipeline the library expects.

## 13. Diagnosing when a condition does not see a bean

A common situation:

~~~java
@AutoConfiguration
class PartnerMetricsAutoConfiguration {

    @Bean
    @ConditionalOnBean(PartnerClient.class)
    PartnerMetrics partnerMetrics(PartnerClient client) {
        return new PartnerMetrics(client);
    }
}
~~~

The `PartnerClient` bean exists in another configuration, yet `PartnerMetrics` is not registered. You can investigate:

1. Was the configuration providing `PartnerClient` loaded?
2. Was that auto-configuration excluded or did its conditions fail?
3. Was the `PartnerClient` bean definition registered before the metrics condition was evaluated?
4. Do the two auto-configurations have the right ordering relationship?
5. Does `PartnerClient` have the exact type or qualifier the condition is looking for?
6. Is there confusion between a bean definition and a bean instance?

If both classes are auto-configurations, declaring `after`/`before` can solve the processing order issue. If the bean is supplied by the application via component scan, inspect the timing of component scan/configuration processing and whether the condition is placed in the right spot. Do not add ordering annotations blindly before identifying the bean definition source.

### Condition Evaluation Report

You can enable:

~~~properties
debug=true
~~~

or run with `--debug` to view Spring Boot's condition report. The report typically shows which auto-configurations matched, did not match, or were excluded, along with reasons related to classpath, properties, or beans.

The condition report confirms whether a configuration was selected. It is not a log of every bean's constructor order and does not replace lifecycle inspection when investigating instance creation order.

### Tracing bean creation

You can raise container log levels in development:

~~~properties
logging.level.org.springframework.beans.factory.support=DEBUG
~~~

Specific log levels and messages vary by Spring version. Use logs to see which beans are created and which dependencies are resolved; do not enable overly verbose logging in production without evaluating log volume and internal details exposed.

## 14. Commonly confused concepts

| Conception | Accurate understanding |
|---|---|
| "Auto-configuration A runs before B so all beans of A are created before beans of B." | A is processed/registered before B; instance creation has its own lifecycle and dependencies. |
| "@Order(1) makes a singleton get created first." | `@Order` mainly sorts collections/extension points supporting ordering. |
| "@DependsOn and @AutoConfigureAfter are the same." | `@DependsOn` controls bean initialization order; `after` controls auto-configuration processing order. |
| "Changing @Import order guarantees constructors run in that order." | Import order does not replace the dependency graph or lifecycle contracts. |
| "@ConditionalOnBean always sees every bean in the application." | Conditions evaluate only against registry/metadata at the moment they are processed; ordering can matter. |
| "@AutoConfigureOrder controls the order of all @Configuration classes." | It is for auto-configuration ordering, not the order of all application configurations. |
| "A bean definition being registered means the instance already exists." | A definition describes how to create a bean; the instance may only be created later or when requested. |

## 15. How to choose the right mechanism

When faced with a requirement "A must run before B", first identify which stage "run" refers to:

| Actual requirement | Mechanism to consider |
|---|---|
| Auto-configuration A needs to be processed before B so conditions see bean definitions | `@AutoConfiguration(before/after)` or `@AutoConfigureOrder` |
| Bean B needs bean A in order to function | Constructor injection or `@Bean` parameter |
| Bean B needs A's initialization side effect before being created | `@DependsOn` if the dependency cannot be expressed by injection |
| Need processing order for a list of handlers/plugins | `@Order`, `Ordered`, and collection injection |
| Need a bean created only when used | `@Lazy` or on-demand lookup |
| Need work to run after all singletons have been instantiated | `SmartInitializingSingleton` or appropriate lifecycle/event |
| Need to run a task when the Boot application is ready | `ApplicationRunner`, `CommandLineRunner`, or `ApplicationReadyEvent` |

For example, if a startup task needs to use multiple already-created singletons, `SmartInitializingSingleton` can be suitable:

~~~java
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.stereotype.Component;

@Component
class StartupVerifier implements SmartInitializingSingleton {

    @Override
    public void afterSingletonsInstantiated() {
        // Verify singletons that have been created.
    }
}
~~~

If work needs to wait until the Boot application is ready to serve requests, `ApplicationReadyEvent` or a runner may be more appropriate. These lifecycle hooks address application-level milestones; do not substitute them with `@AutoConfigureAfter`.

## 16. Design principles

1. Use `@AutoConfiguration(before/after)` to describe relationships between auto-configurations, especially when conditions depend on another configuration's bean definitions.
2. Use `@AutoConfigureOrder` for general ordering hints when there is no specific class to reference; avoid abusing numeric values.
3. Use constructor injection or `@Bean` method parameters to express real dependencies and let Spring create beans according to the dependency graph.
4. Use `@DependsOn` when name-based initialization order is needed for a side-effect relationship that cannot be expressed via injection.
5. Use `@Order` for lists/extension points supporting ordering; do not use it to govern singleton startup.
6. Distinguish bean definitions from bean instances: conditions usually operate on registered configuration/metadata; constructors and initialization callbacks run when instances are created.
7. Inspect the condition report and bean creation logs when issues arise; do not change order before knowing which configuration is being evaluated and which bean is not yet registered.

Auto-configuration ordering answers **which automatic configuration is processed first to register bean definitions and evaluate conditions**. Bean creation order answers **which instance must be created first so another instance's dependencies and lifecycle are satisfied**. Using the right mechanism for each question helps Spring Boot configure modules conditionally while keeping bean lifecycles clear and predictable.
