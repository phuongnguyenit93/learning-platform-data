# `@Order` Does Not Replace Dependencies When Creating Beans

In Spring Boot, you can place `@Order(1)` on one bean and `@Order(2)` on another. That helps Spring sort them where an ordering mechanism is used, such as when injecting multiple beans into a `List` or invoking `CommandLineRunner`s. However, **`@Order` is not a tool for controlling the initialization order of all beans in the IoC container**.

If bean B genuinely needs bean A to be created and initialized first, the application must express that relationship using dependency injection or `@DependsOn` when only initialization order is needed due to a side effect. Placing `@Order` on A and B creates no dependency between them.

This is a crucial distinction when designing bean lifecycles:

- `@Order` answers: *When a mechanism needs to sort multiple elements, where does this element sit?*
- Dependency injection answers: *Which bean does this bean need in order to operate?*
- `@DependsOn` answers: *Which bean must be initialized before this bean even without directly injecting it?*

## 1. Spring Creates Beans According to Dependency Relationships

The Spring IoC container manages registering bean definitions, creating instances, supplying dependencies, calling initialization callbacks, and destroying beans when the context closes. A bean may be created early or late depending on scope, lazy initialization, and which other beans need it.

Example:

```java
@Component
public class DataSourceProvider {
    public DataSourceProvider() {
        System.out.println("Create DataSourceProvider");
    }
}

@Service
public class ReportService {
    private final DataSourceProvider dataSourceProvider;

    public ReportService(DataSourceProvider dataSourceProvider) {
        System.out.println("Create ReportService");
        this.dataSourceProvider = dataSourceProvider;
    }
}
```

`ReportService` needs `DataSourceProvider` to be created. When Spring creates `ReportService`, the container must resolve the constructor parameter first. Consequently, `DataSourceProvider` is created and initialized before Spring invokes `ReportService`'s constructor.

This relationship is formed by a real dependency in the constructor:

```text
DataSourceProvider
        |
        | needed beforehand
        v
ReportService
```

This is an edge in the container's **dependency graph**. Spring has the information to know which bean needs which bean, and from there determines an appropriate creation order.

### 1.1. Constructor injection expresses dependencies clearly

```java
@Service
public class OrderService {
    private final PaymentGateway paymentGateway;
    private final InventoryService inventoryService;

    public OrderService(
            PaymentGateway paymentGateway,
            InventoryService inventoryService) {
        this.paymentGateway = paymentGateway;
        this.inventoryService = inventoryService;
    }
}
```

`OrderService` can only be created after Spring resolves `PaymentGateway` and `InventoryService`. If a dependency has no matching bean, the container reports a bean creation error instead of silently initializing `OrderService` with a missing dependency.

Constructor injection offers several benefits:

- Expresses required dependencies directly in the constructor signature.
- Prevents the object from being created in a state missing dependencies.
- Makes writing unit tests easy by passing fakes or mocks.
- Tells Spring the relationships between beans to manage creation.

### 1.2. Setter and field injection also create dependencies

Spring also supports setter injection:

```java
@Service
public class ReportService {
    private DataSourceProvider dataSourceProvider;

    @Autowired
    public void setDataSourceProvider(
            DataSourceProvider dataSourceProvider) {
        this.dataSourceProvider = dataSourceProvider;
    }
}
```

And field injection:

```java
@Service
public class ReportService {
    @Autowired
    private DataSourceProvider dataSourceProvider;
}
```

In both cases, Spring still has to resolve the dependent bean when populating properties. The dependency is still known to the container. However, constructor injection is generally easier to read and control, especially for required dependencies.

**Note on timing:** with constructor injection, dependencies must be resolved before the constructor of the bean being created is called. With setter/field injection, the dependent object may be created after the main bean instance has been instantiated, yet before the main bean's initialization finishes. Do not assume all injection styles have the same constructor-level order.

## 2. What Does `@Order` Actually Do?

`@Order` belongs to the `org.springframework.core.annotation` package. The annotation declares a priority level so mechanisms supporting an order comparator can sort objects.

Example:

```java
@Component
@Order(1)
public class FirstHandler implements TaskHandler {
}

@Component
@Order(2)
public class SecondHandler implements TaskHandler {
}
```

Lower values have higher priority, so `FirstHandler` comes before `SecondHandler` when they are collected and sorted by order.

The `Ordered` interface also provides a programmatic way to declare order:

```java
@Component
public class UrgentHandler implements TaskHandler, Ordered {
    @Override
    public int getOrder() {
        return 1;
    }
}
```

### 2.1. Common places where order is used

| Usage site | Role of `@Order` / `Ordered` |
| --- | --- |
| Injecting `List<T>` with multiple matching beans | Sorts elements in the list |
| Injecting array `T[]` | Sorts array elements per autowiring mechanism |
| `ObjectProvider<T>.orderedStream()` | Provides a stream sorted by order |
| `CommandLineRunner` / `ApplicationRunner` | Sorts runner invocation order after context startup |
| Spring AOP aspects | Determines precedence among aspects when multiple apply |
| Certain Spring extension points | Sorts processors or strategies if the extension point contract uses order |

`@Order` does not mean every list, every bean, or every phase in Spring is automatically sorted. Its effect depends on the mechanism reading the order metadata.

### 2.2. `@Order` does not dictate singleton creation order

This is a critical rule to remember:

> `@Order` does not control the initialization order of singleton beans in the application context.

Example:

```java
@Component
@Order(1)
public class CacheInitializer {
    public CacheInitializer() {
        System.out.println("CacheInitializer constructor");
    }
}

@Component
@Order(2)
public class SearchInitializer {
    public SearchInitializer() {
        System.out.println("SearchInitializer constructor");
    }
}
```

Do not treat `@Order(1)` as a guarantee that `CacheInitializer`'s constructor always runs before `SearchInitializer`'s constructor. Singleton initialization order also depends on how beans are requested, dependency relationships, lazy initialization, and container workflows.

If `SearchInitializer` genuinely needs the cache to be ready, express an appropriate dependency or initialization relationship. Merely adding `@Order` does not inform Spring that `SearchInitializer` depends on `CacheInitializer`.

## 3. `@Order` in Collection Injection: Element Order, Not Bean Creation Order

A very fitting place to use `@Order` is when a service needs all implementations of the same interface and wants to iterate through them in sequence.

Declare an interface:

```java
public interface StartupTask {
    void execute();
}
```

Two implementations:

```java
@Component
@Order(10)
public class LoadConfigurationTask implements StartupTask {
    @Override
    public void execute() {
        System.out.println("Load configuration");
    }
}
```

```java
@Component
@Order(20)
public class PrintBannerTask implements StartupTask {
    @Override
    public void execute() {
        System.out.println("Print banner");
    }
}
```

A service receiving the list:

```java
@Service
public class StartupCoordinator {
    private final List<StartupTask> tasks;

    public StartupCoordinator(List<StartupTask> tasks) {
        this.tasks = tasks;
    }

    public void runAll() {
        tasks.forEach(StartupTask::execute);
    }
}
```

With standard collection autowiring, Spring sorts elements in `tasks` by order:

```text
tasks
  1. LoadConfigurationTask  (@Order(10))
  2. PrintBannerTask        (@Order(20))
```

When `runAll()` is called, the `execute()` methods run in the order of elements in the list. This is **execution order when the service iterates the collection**, not a guarantee that `LoadConfigurationTask`'s constructor ran before `PrintBannerTask`'s constructor.

Spring needs to create the beans to supply them to `StartupCoordinator`'s constructor. The creation order of instances may differ from the sorted order of elements in the list.

### 3.1. Illustrating the two kinds of order

```text
Bean creation time:

Container needs StartupTask beans
       |
       +--> Create instances (order not dictated by @Order)
       |
       v
Collect matching beans
       |
       v
Sort collection by @Order
       |
       v
Inject List<StartupTask> into StartupCoordinator
       |
       v
StartupCoordinator.runAll()
       |
       +--> LoadConfigurationTask.execute()
       |
       +--> PrintBannerTask.execute()
```

If the goal is simply running handlers in sequence, `@Order` and collection injection fit well. If the goal is guaranteeing one bean completes initialization before another bean, a separate dependency relationship is needed.

### 3.2. Lower order values come first

| Bean | Order | Position in list |
| --- | ---: | ---: |
| `LoadConfigurationTask` | 10 | 1 |
| `PrintBannerTask` | 20 | 2 |
| `CleanupTask` | 30 | 3 |

If no order is declared, the default value is typically equivalent to `Ordered.LOWEST_PRECEDENCE`. When two beans have the same order, do not rely on unguaranteed input ordering as a business rule.

### 3.3. `List`, array, `Set`, and `Map`

| Dependency reception type | How to understand it |
| --- | --- |
| `List<T>` | Suitable when needing multiple beans in order; autowired lists are sorted by order |
| `T[]` | Can receive multiple beans and is sorted by the array autowiring mechanism |
| `Set<T>` | Represents a set of elements; do not rely on iteration order |
| `Map<String, T>` | Useful for looking up beans by name; do not treat iteration order as an `@Order` contract |

If you need to retrieve beans in order lazily:

```java
@Service
public class TaskRunner {
    private final ObjectProvider<StartupTask> tasks;

    public TaskRunner(ObjectProvider<StartupTask> tasks) {
        this.tasks = tasks;
    }

    public void runAll() {
        tasks.orderedStream().forEach(StartupTask::execute);
    }
}
```

`orderedStream()` requests sorting the beans using the order comparator. Plain `stream()` should not be assumed to be sorted by `@Order`.

## 4. Expressing Dependencies via Constructor Injection

If bean B genuinely needs bean A to operate, inject A into B:

```java
@Component
public class DatabaseInitializer {

    public DatabaseInitializer() {
        System.out.println("Create DatabaseInitializer");
    }

    public void initialize() {
        System.out.println("Initialize database metadata");
    }
}
```

```java
@Service
public class CustomerRepository {
    private final DatabaseInitializer initializer;

    public CustomerRepository(DatabaseInitializer initializer) {
        this.initializer = initializer;
        System.out.println("Create CustomerRepository");
    }
}
```

In this illustrative example, `CustomerRepository` has a direct dependency on `DatabaseInitializer`. The container must resolve the dependency before finishing creation of `CustomerRepository`.

However, if `CustomerRepository` does not need to call methods on `DatabaseInitializer`, injecting it solely to force order can misrepresent design intent. In scenarios where only a prior side effect is needed, `@DependsOn` may be more appropriate.

### 4.1. Dependencies used in business logic

This is the case where constructor injection should be used:

```java
@Service
public class InvoiceService {
    private final TaxCalculator taxCalculator;

    public InvoiceService(TaxCalculator taxCalculator) {
        this.taxCalculator = taxCalculator;
    }

    public BigDecimal calculateTotal(BigDecimal amount) {
        return taxCalculator.calculate(amount);
    }
}
```

`InvoiceService` needs `TaxCalculator` to compute totals. The relationship is expressed directly in the class API, and Spring automatically ensures the right dependency is resolved before the main bean is ready.

There is no need to add `@Order` or `@DependsOn` to repeat a relationship already expressed by constructor injection.

## 5. `@DependsOn`: When Initialization Order Is Needed Without Direct Injection

Sometimes bean B does not need to hold a reference to bean A, yet B's initialization requires a **side effect** previously performed by A. For example, A registers plugins in a shared registry, while B reads that registry in an initialization callback.

`@DependsOn` belongs to `org.springframework.context.annotation.DependsOn`. The annotation tells Spring which beans must be initialized before the annotated bean.

Example:

```java
@Component("pluginCatalogInitializer")
public class PluginCatalogInitializer {

    @PostConstruct
    public void registerPlugins() {
        System.out.println("Register plugins in shared catalog");
    }
}
```

Bean using the registry after the catalog is prepared:

```java
@Component
@DependsOn("pluginCatalogInitializer")
public class PluginConsumer {

    @PostConstruct
    public void loadPlugins() {
        System.out.println("Read registered plugins");
    }
}
```

`PluginConsumer` does not need to inject `PluginCatalogInitializer`. Still, Spring must initialize the `pluginCatalogInitializer` bean before initializing `PluginConsumer`.

Expected initialization order output:

```text
Register plugins in shared catalog
Read registered plugins
```

The bean name in `@DependsOn` must match the actual bean name. If no explicit name is declared for the `PluginCatalogInitializer` component, the default name is typically `pluginCatalogInitializer`.

### 5.1. Using `@DependsOn` on a class

```java
@Component
@DependsOn({"configurationLoader", "pluginCatalogInitializer"})
public class PluginConsumer {
}
```

All listed beans must be initialized before `PluginConsumer`. Multiple bean names can be declared in an array.

### 5.2. Using `@DependsOn` on a `@Bean` method

```java
@Configuration(proxyBeanMethods = false)
public class PluginConfiguration {

    @Bean
    public PluginCatalogInitializer pluginCatalogInitializer() {
        return new PluginCatalogInitializer();
    }

    @Bean
    @DependsOn("pluginCatalogInitializer")
    public PluginConsumer pluginConsumer() {
        return new PluginConsumer();
    }
}
```

Here the bean is created via a factory method. `@DependsOn` on the `@Bean` method applies the initialization relationship to the bean registered by that method.

### 5.3. `@DependsOn` and singleton destruction order

For singleton beans, the `@DependsOn` relationship also affects destruction order: the dependent bean is destroyed before the bean it depends on.

If `pluginConsumer` depends on `pluginCatalogInitializer`'s side effect, when the application context closes, Spring can destroy the consumer first and only then destroy the initializer, per the declared dependency relationship.

This is helpful when a bean needs a resource or registry to still exist during cleanup. Exact destruction behavior still depends on bean scope and lifecycle callbacks.

## 6. Constructor Injection or `@DependsOn`: Choose by Underlying Nature

Both mechanisms help Spring create beans in a required relationship, yet they express different meanings.

| Scenario | Recommended approach | Reason |
| --- | --- | --- |
| `OrderService` needs `PaymentGateway` to process orders | Constructor injection | It is a real dependency actually used |
| `ReportService` needs `DataSource` to run queries | Constructor injection | The bean must have the dependency to operate |
| `PluginConsumer` needs plugins registered before reading | `@DependsOn` if no initializer reference is needed | The relationship is primarily initialization side-effect ordering |
| `CacheWarmupTask` and `BannerTask` only need sequential execution in a pipeline | `@Order` on collection | It is element processing order |
| Multiple `CommandLineRunner`s must run sequentially after startup | `@Order` / `Ordered` | Spring Boot sorts runner invocation order |
| One bean needs a default implementation among multiple candidates | `@Primary` or `@Qualifier` | It is bean selection, not dependency order |

Do not inject a bean solely to "force order" if that bean is not a genuine dependency. Conversely, do not use `@DependsOn` when a constructor can clearly express the object being used.

## 7. `@Order` and `@DependsOn` Can Coexist Without Replacing Each Other

A bean may need to participate in an ordered pipeline and simultaneously require another bean to initialize beforehand due to a side effect. These two requirements are independent.

Example:

```java
@Component("schemaInitializer")
public class SchemaInitializer {
    @PostConstruct
    public void initialize() {
        System.out.println("Prepare schema");
    }
}
```

```java
@Component
@DependsOn("schemaInitializer")
@Order(10)
public class ImportTask implements StartupTask {
    @Override
    public void execute() {
        System.out.println("Import data");
    }
}
```

```java
@Component
@Order(20)
public class ReportTask implements StartupTask {
    @Override
    public void execute() {
        System.out.println("Generate report");
    }
}
```

In this example:

- `@DependsOn("schemaInitializer")` guarantees the initializer initializes before `ImportTask`.
- `@Order(10)` and `@Order(20)` sort `ImportTask` and `ReportTask` when placed into an order-aware collection.
- `@Order` on `ImportTask` does not automatically cause `schemaInitializer` to initialize earlier.
- `@DependsOn` on `ImportTask` does not decide whether `ImportTask` comes before or after `ReportTask` in the collection.

If `ReportTask` also requires the schema to be ready, it needs its own dependency relationship or both tasks must depend on a shared service/initializer. Do not assume that because `ImportTask` has `@DependsOn`, `ReportTask` is covered as well.

## 8. `@Order` in `CommandLineRunner` Differs from Bean Creation Order

Spring Boot invokes `CommandLineRunner` and `ApplicationRunner` after the application context has started up. Runners can be sorted using `Ordered` or `@Order`.

Example:

```java
@Configuration(proxyBeanMethods = false)
public class StartupConfiguration {

    @Bean
    @Order(10)
    CommandLineRunner loadData() {
        return args -> System.out.println("Load data");
    }

    @Bean
    @Order(20)
    CommandLineRunner printStatus() {
        return args -> System.out.println("Print status");
    }
}
```

Spring Boot calls the `loadData` runner before the `printStatus` runner according to order. However, do not interpret this as a guarantee that the object representing the first runner is always **instantiated before** the second runner object.

### 8.1. When the second runner needs results from the first runner

If `printStatus` needs data produced by `loadData`, order can be used to determine runner invocation order within Spring Boot's runner mechanism:

```text
Context has refreshed
       |
       v
loadData.run()       @Order(10)
       |
       v
printStatus.run()    @Order(20)
```

However, if that data is an essential dependency of a bean during bean creation, `@Order` on a runner will not cause that bean to be created after the runner. Runners execute after the context refresh phase; regular eager singletons have already been initialized earlier.

If a bean needs a resource immediately inside its constructor or `@PostConstruct`, create an appropriate initialization dependency rather than relying on a runner executing first.

### 8.2. Separating data initialization from bean construction

Avoid putting heavy work or business ordering dependencies inside constructors:

```java
@Service
public class SearchService {
    public SearchService() {
        // Should not load the entire index or run long tasks here
    }
}
```

You can separate it into an explicit initialization service and coordinate after the context is ready:

```java
@Component
public class SearchIndexLoader implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        // Load or refresh the index after the context has started
    }
}
```

If multiple runners need invocation order, use `@Order`. If a bean needs a dependency during creation, inject that dependency. Both phases must be designed distinctly.

## 9. Bean Creation Order vs. Lifecycle Callback Order

A typical singleton bean goes through these primary steps:

```text
Register BeanDefinition
       |
       v
Resolve constructor dependencies
       |
       v
Instantiate object
       |
       v
Populate properties / inject dependencies
       |
       v
BeanPostProcessor before initialization
       |
       v
Initialization callbacks
(@PostConstruct, InitializingBean, initMethod...)
       |
       v
BeanPostProcessor after initialization
       |
       v
Bean ready for client
```

This is a simplified diagram. Actual order involves various internal steps and post-processors.

If `ServiceB` constructor-injects `ServiceA`, Spring must resolve `ServiceA` before completely creating `ServiceB`. Once `ServiceA` has finished initializing, Spring can supply it to proceed with creating `ServiceB`.

If `ServiceB` merely has `@Order(2)` and `ServiceA` has `@Order(1)`, that does not mean A's `@PostConstruct` callback always runs before B's. `@Order` does not add dependency edges to the lifecycle graph.

### 9.1. `@PostConstruct` is not a replacement for dependency injection

Example:

```java
@Component
public class FirstInitializer {
    @PostConstruct
    public void initialize() {
        System.out.println("Initialize first");
    }
}

@Component
public class SecondInitializer {
    @PostConstruct
    public void initialize() {
        System.out.println("Initialize second");
    }
}
```

There is no dependency relationship between these two beans. Placing `@Order` on the classes is not a general guarantee that the two `@PostConstruct` methods will run in order.

If this order is a genuine requirement, you can:

- Put the logic into a coordinator receiving a sorted `List<Initializer>` and invoke methods in order after the context is ready.
- Use `@DependsOn` if the second bean needs the first bean to complete initialization due to a side effect.
- Redesign so the dependency relationship is expressed via constructor injection.

### 9.2. `@DependsOn` also affects destruction timing

Suppose `ClientBean` depends on a resource prepared by `ResourceRegistry`:

```java
@Component("resourceRegistry")
public class ResourceRegistry {
    @PostConstruct
    public void start() {
        // Prepare registry
    }

    @PreDestroy
    public void stop() {
        // Clean up registry
    }
}

@Component
@DependsOn("resourceRegistry")
public class ClientBean {
    @PreDestroy
    public void close() {
        // Close client while registry still exists
    }
}
```

For singleton beans, Spring initializes `resourceRegistry` before `clientBean` and destroys `clientBean` before `resourceRegistry`. This ensures the client has the opportunity to close resources before the registry is cleaned up.

## 10. Lazy Initialization and Prototype Considerations

Bean creation order is also affected by scope and lazy initialization. `@Order` does not alter these rules.

### 10.1. `@Lazy`

```java
@Component
@Lazy
public class ExpensiveCatalog {
    public ExpensiveCatalog() {
        System.out.println("Create ExpensiveCatalog");
    }
}
```

A bean marked lazy can have its creation deferred until needed. If a non-lazy singleton directly injects `ExpensiveCatalog` via constructor, Spring still needs to create the dependency to finish that singleton.

`@Order(1)` on `ExpensiveCatalog` does not force it to initialize before other beans. If you want to defer lookup, you can use `ObjectProvider<ExpensiveCatalog>` and call `getObject()` when needed.

### 10.2. Prototype

```java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class JobContext {
}
```

Prototype beans are newly created when the container is asked to resolve a bean under this scope. If a prototype is directly injected into a singleton via constructor, resolution usually happens once when the singleton is created; the singleton holds that same prototype instance.

To get a new instance per execution:

```java
@Service
public class JobService {
    private final ObjectProvider<JobContext> contexts;

    public JobService(ObjectProvider<JobContext> contexts) {
        this.contexts = contexts;
    }

    public void process() {
        JobContext context = contexts.getObject();
        // Process work with a fresh context
    }
}
```

`@Order` on `JobContext` does not decide when prototypes are created. It can only affect how beans are sorted at order-aware injection points.

## 11. Circular Dependencies Are Not Resolved by `@Order`

Suppose:

```java
@Service
public class ServiceA {
    public ServiceA(ServiceB serviceB) {
    }
}
```

```java
@Service
public class ServiceB {
    public ServiceB(ServiceA serviceA) {
    }
}
```

Two beans depend on each other via constructors:

```text
ServiceA needs ServiceB
    ^             |
    |             v
ServiceB needs ServiceA
```

There is no valid creation order because A needs B before A can be created, while B also needs A before B can be created. Adding `@Order(1)` and `@Order(2)` does not break this dependency cycle.

Spring typically reports a circular dependency error during bean creation. Sustainable solutions involve reviewing class responsibilities:

- Extract shared logic into a third bean.
- Invert the dependency direction with an interface or event when appropriate.
- Use `ObjectProvider`/`@Lazy` for deferred lookup if that relationship is genuinely necessary.
- Avoid having two services call each other directly when business logic can be reorganized.

Do not use `@DependsOn` to create yet another dependency cycle; it cannot resolve an initialization cycle either.

## 12. Common Misconceptions

| Misconception | Correct understanding |
| --- | --- |
| "A bean with `@Order(1)` is always created before a bean with `@Order(2)`." | `@Order` does not control general singleton initialization order. |
| "`@Order` creates a dependency relationship." | It only supplies order metadata for mechanisms using comparators. |
| "Two beans with different orders have their `@PostConstruct` run in order." | No such general guarantee exists; dependencies or a coordinator are needed. |
| "`@DependsOn` and constructor injection are the same." | Constructor injection expresses a dependency to use; `@DependsOn` expresses initialization order by bean name. |
| "`@DependsOn` injects the bean into a field." | It provides no reference; to use an object, inject it. |
| "`@Order` selects the default implementation." | Use `@Primary` or `@Qualifier` to select a single bean. |
| "Runner order determines runner bean creation order." | It determines runner invocation order during the Spring Boot runner execution phase. |
| "Adding `@Order` can fix a circular dependency." | Dependency cycles require redesign or intentional deferred lookup. |
| "Singleton beans are always created in file or declaration order." | Never rely on declaration order; express needed relationships via the dependency graph. |

## 13. How to Diagnose When Beans Initialize in an Unexpected Order

When you see constructor or `@PostConstruct` logs running in an unexpected order, identify **which kind of order you actually need**.

### 13.1. If bean B needs object A

Check B's constructor signature:

```java
public ServiceB(ServiceA serviceA) {
    this.serviceA = serviceA;
}
```

If this dependency is missing yet B genuinely needs A, add the proper dependency. Do not just add `@Order`.

### 13.2. If B needs A's side effect without needing object A

Check `@DependsOn`:

```java
@Component
@DependsOn("initializerA")
public class ServiceB {
}
```

Make sure the bean name is right and the initializer actually finishes its work in a lifecycle callback before bean B is initialized.

### 13.3. If operations need to be sorted

Check whether the code accepts `List<T>` or `ObjectProvider<T>.orderedStream()` and actually iterates the collection in order. Merely putting `@Order` on a class without an ordering/coordinating mechanism is not enough.

### 13.4. If runner order is wrong

Check whether runners implement `Ordered` or carry `@Order`, and whether the application uses Spring Boot's standard runner invocation mechanism. Do not infer bean creation order from log order inside `run()`.

### 13.5. Add logging to observe

You can log in constructors, `@PostConstruct`, and execution methods:

```java
@Component
@Order(10)
public class ImportTask implements StartupTask {

    public ImportTask() {
        System.out.println("Construct ImportTask");
    }

    @PostConstruct
    public void initialize() {
        System.out.println("Initialize ImportTask");
    }

    @Override
    public void execute() {
        System.out.println("Execute ImportTask");
    }
}
```

Compare the three log types:

- `Construct ...`: when the object is instantiated.
- `Initialize ...`: the bean's lifecycle callback.
- `Execute ...`: when business/runner code is invoked.

If the goal is controlling `execute()` order across a collection, `@Order` may fit. If the goal is that `Initialize A` must finish before `Construct B`, express a dependency or use `@DependsOn` according to its true nature.

## 14. Practice Exercises

### Exercise 1 — Observe that `@Order` does not dictate constructor order

Create two components:

```java
@Component
@Order(1)
public class AlphaTask {
    public AlphaTask() {
        System.out.println("Create AlphaTask");
    }
}

@Component
@Order(2)
public class BetaTask {
    public BetaTask() {
        System.out.println("Create BetaTask");
    }
}
```

Start the application and record constructor order. Do not conclude that this order is an `@Order` contract.

### Exercise 2 — Observe collection order

Create a `Task` interface and have `AlphaTask` and `BetaTask` implement it. Inject `List<Task>` into a coordinator and print the list in order. Compare with the constructor logs from Exercise 1.

**Question:** Are the two orders the same thing? Why or why not?

### Exercise 3 — Create a real dependency

Modify `BetaTask` so its constructor accepts `AlphaTask`:

```java
public BetaTask(AlphaTask alphaTask) {
    this.alphaTask = alphaTask;
}
```

Restart. Explain why Spring must resolve `AlphaTask` before calling `BetaTask`'s constructor, even without `@Order`.

### Exercise 4 — Try `@DependsOn`

Create bean `RegistryInitializer` with `@PostConstruct` registering a value in a shared registry. Create bean `RegistryConsumer` reading that value in `@PostConstruct` and place:

```java
@DependsOn("registryInitializer")
```

Observe the logs. Then remove `@DependsOn` and explain why you should not rely on component scan order.

### Exercise 5 — Sort runners

Declare three `CommandLineRunner`s with orders 30, 10, and 20. Log inside `run()`. Identify the invocation order and explain why this is a case where `@Order` takes effect.

### Exercise 6 — Distinguish three requirements

Given these scenarios:

1. `InvoiceService` needs `TaxCalculator` to compute invoices.
2. `PluginConsumer` needs a registry initialized beforehand, without using the initializer object.
3. `ValidationTask`, `AuditTask`, and `NotificationTask` must run sequentially in a pipeline.

Choose among constructor injection, `@DependsOn`, and `@Order`. Explain why these tools cannot substitute for one another.

### Exercise 7 — Identify circular dependencies

Create two services constructor-injecting each other. Observe the startup error. Try adding `@Order` to both classes and determine why the error does not disappear. Propose how to split responsibilities or use a provider when deferred lookup is needed.

## 15. Key Takeaways

**`@Order` sorts elements where an order comparator is used; it does not create dependency relationships and does not dictate singleton bean initialization order.** When a bean needs another bean to be created or to operate, express that relationship with dependency injection. When a bean only needs another bean initialized first due to a side effect, consider `@DependsOn`. When iterating multiple beans in sequence, use `@Order` with collections or order-supporting extension points.

Separate three questions clearly when designing bean lifecycles: *Which objects does the bean need? Which beans must finish initializing beforehand? And in what order should operations across a set of beans execute?* Answering each question accurately makes Spring Boot applications predictable, less reliant on accidental registration order, and easier to maintain.
