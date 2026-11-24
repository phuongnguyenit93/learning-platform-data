# Initialization Order Driven by the Dependency Graph in Spring Core Container

## 1. Lesson Objectives

In Spring Framework, whether one bean is initialized before or after another **is primarily determined by dependency relationships**, not the order you place `@Bean` methods, class order in `@Import`, `<bean>` position in XML, or the bean's `@Order` value. A bean needing a dependency to complete its constructor or factory method must wait for that dependency to be resolved.

Example:

```java
@Configuration(proxyBeanMethods = false)
class CatalogConfig {
    @Bean
    CatalogRepository catalogRepository() {
        return new InMemoryCatalogRepository();
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
```

This is an **illustration**, requiring appropriate Java types. Looking at the factory method signatures, Spring knows:

```text
catalogController -> catalogService -> catalogRepository
```

The arrow means **the bean on the left needs the bean on the right**. Therefore when `catalogController` must be created, Spring ensures `catalogRepository` and `catalogService` are created/resolved sufficiently to pass into constructors/factory methods before completing the controller.

However, if there is also an `metricsExporter` unrelated to these three beans, you **cannot conclude** it is guaranteed to be created before or after `catalogRepository` merely because the `metricsExporter()` method is written on the first line of the class.

After this lesson, you will be able to:

1. Draw and read a **directed dependency graph** from constructors, setter/property injection, factory method parameters, and `depends-on` metadata.
2. Distinguish a **partial order** from a fixed total order.
3. Understand that Spring creates regular non-lazy singletons during `ApplicationContext.refresh()` while still resolving their dependencies first.
4. Know that Spring can create a lazy bean early because it is a dependency of an eager bean.
5. Use `@Bean` method parameters and constructor injection to make dependency relationships explicit.
6. Use `@DependsOn`/XML `depends-on` for **initialization constraints not expressible via direct references**, and understand the consequence on destruction order.
7. Distinguish `@Order`, `Ordered`, and `@Priority` used for sorting/selection from bean startup order.
8. Distinguish `@Import`/`@ImportResource`, XML file order, and actual bean dependency order.
9. Recognize circular dependencies and choose an appropriate refactoring.
10. Understand that extension points like `SmartInitializingSingleton`, `SmartLifecycle`, and `ContextRefreshedEvent` are not synonymous with constructor dependency ordering.
11. Run a **Java 17 + Spring Framework 6.2** example with contract-accurate ordering assertions that do not depend on accidental ordering of independent beans.
12. Write tests and debug initialization/circular dependency errors in real applications.

**Core idea:** Spring guarantees **A already has the required dependency B when A is created**; Spring does not guarantee **every independent bean follows a startup order you can use as a business workflow**.

## 2. What Is a Dependency Graph?

Model each bean definition/bean instance to be created as a **vertex**. A dependency from bean A to bean B is drawn as:

```text
A --> B
```

This means "to initialize A, the container needs B", not "A is guaranteed to call B at runtime".

Given the beans:

- `Controller` needs `Service`.
- `Service` needs `Repository` and `Clock`.
- `Repository` does not need `Service`.
- `MetricsExporter` is independent of the other three beans.

Graph:

```text
                   Controller
                       |
                       v
                    Service
                    /     \
                   v       v
             Repository   Clock

             MetricsExporter
              (independent)
```

Spring knows the **constraints**:

- `Repository` must be created/resolved before `Service` is completed.
- `Clock` must be created/resolved before `Service` is completed.
- `Service` must be created/resolved before `Controller` is completed.
- By transitivity, `Repository` and `Clock` must be ready before `Controller`.

However, between **Repository and Clock** there is no direct edge; both can be created in any valid order. **MetricsExporter** also has no connecting edge, so do not assume its position in a total order.

### 2.1. Partial Order, Not a Fixed Schedule

In graph theory, a set of conditions like "B before A" above forms a **partial order** when acyclic. There are multiple valid **topological orders**:

```text
Repository, Clock, Service, Controller, MetricsExporter
Clock, Repository, MetricsExporter, Service, Controller
MetricsExporter, Clock, Repository, Service, Controller
```

These three sequences are merely **possible orders satisfying the same constraints**, not a promise that Spring will pick one specific sequence among the three. The priority here is satisfying dependencies and lifecycles properly; exact timing between independent nodes is an implementation detail not to rely on.

### 2.2. Instance Creation Order Differs from Definition Registration Order

A `BeanDefinition` is metadata about a bean: class, factory method, scope, lazy, constructor args, properties, depends-on, and other options. Definitions can be registered before any instance is created.

```text
register definitions:
    Controller
    MetricsExporter
    Service
    Repository
    Clock

instantiate as needed:
    Repository / Clock -> Service -> Controller
    MetricsExporter (independent)
```

If you inspect the list of bean definition names, you may see the registration order. **Do not use that order as a business initialization order**.

## 3. How Spring Decides Bean Creation Timing

A standard `ApplicationContext` performs several steps during `refresh()`:

```text
Find/read Java config, XML, component metadata
                    |
                    v
Register BeanDefinitions
                    |
                    v
Process BeanFactoryPostProcessor / BeanPostProcessor
                    |
                    v
Pre-instantiate regular non-lazy singletons
                    |
                    +--> get bean A
                    |      |
                    |      +--> A needs bean B
                    |                |
                    |                +--> B needs bean C
                    |                |       |
                    |                |       v
                    |                |     create C
                    |                v
                    |              create B
                    v
                  create A
                    |
                    v
Finish pre-instantiation / refresh
```

This is a **conceptual model**. Spring has specialized infrastructure for proxies, bean post-processors, `FactoryBean`, circular reference handling, scoped beans, and Spring 6.2 background bootstrap; do not interpret the diagram as a line-by-line algorithm for every implementation.

### 3.1. Spring Does Not Simply Follow Method Declaration Order

```java
@Configuration(proxyBeanMethods = false)
class Config {
    @Bean
    Controller controller(Service service) {
        return new Controller(service);
    }

    @Bean
    Service service(Repository repository) {
        return new Service(repository);
    }

    @Bean
    Repository repository() {
        return new Repository();
    }
}
```

If `controller` is requested, the container still must resolve `Service` and `Repository` before it can invoke the constructor/factory method with the required arguments, even though the `controller` factory method is written first in source.

### 3.2. Spring Does Not Need a Bean to Already Be Created to Know Its Dependencies

Spring inspects types/metadata of constructors, factory methods, `@Autowired`, and XML references. It can resolve dependencies **at bean creation time**, based on the registry holding the definitions.

A Java bean implementation can be declared in another config, yet the BeanFactory can still find it as long as all definitions belong to the same context.

### 3.3. A Bean Marked Lazy Can Appear in Startup Order

```java
@Bean
@Lazy
Repository lazyRepository() {
    return new Repository();
}

@Bean
Service eagerService(Repository lazyRepository) {
    return new Service(lazyRepository);
}
```

In this illustrative example, if `eagerService` is a non-lazy singleton, Spring must resolve `Repository` right during startup. `@Lazy` on the repository definition only prevents standalone proactive pre-instantiation, not creation as a required dependency of an eager bean.

## 4. Types of Dependency Edges Spring Recognizes

Spring can form dependency relationships through several mechanisms.

### 4.1. Constructor Injection

```java
final class OrderService {
    private final OrderRepository repository;

    OrderService(OrderRepository repository) {
        this.repository = repository;
    }
}
```

If Spring creates `OrderService` and the constructor requires `OrderRepository`, the repository must exist before the constructor call completes.

### 4.2. @Bean Factory Method Parameters

```java
@Bean
OrderService orderService(OrderRepository repository) {
    return new OrderService(repository);
}
```

The BeanFactory must resolve `OrderRepository` before invoking `orderService(repository)`. This is a very suitable way to express dependencies when a `@Configuration` class creates beans across different modules.

### 4.3. Setter/Property Injection

```java
final class TaskProcessor {
    private TaskRepository repository;

    public void setRepository(TaskRepository repository) {
        this.repository = repository;
    }
}
```

XML:

```xml
<bean id="taskProcessor" class="example.TaskProcessor">
    <property name="repository" ref="taskRepository"/>
</bean>
```

The BeanFactory needs the repository when populating properties before the corresponding initialization steps. With setter injection, **the raw `TaskProcessor` object may already have gone through its constructor before the repository is injected**. Therefore "dependency before consumer" should normally be understood as **the dependency must be resolved before the consumer finishes initialization**, not that every consumer constructor must strictly run after every dependency constructor, especially with setter/field injection or circular-reference mechanisms.

### 4.4. @Autowired Field

```java
@Component
class BillingFacade {
    @Autowired
    BillingService billingService;
}
```

Field injection also causes the container to resolve `BillingService` during `BillingFacade`'s population phase. However, the facade's constructor can run **before** the field is injected. That is one reason constructor injection generally makes the dependency graph more transparent and guarantees invariants earlier.

### 4.5. @DependsOn / depends-on Metadata

```java
@Bean
@DependsOn("schemaValidator")
DataAccessService dataAccessService() {
    return new DataAccessService();
}
```

Here `dataAccessService` does not receive a `schemaValidator` reference via parameter, yet metadata states `schemaValidator` must be initialized before creating the service bean. That is an **explicit ordering edge**.

### 4.6. Dynamic Lookup Is a Deferred Dependency Edge

```java
final class Exporter {
    private final ObjectProvider<RemoteGateway> gateway;

    Exporter(ObjectProvider<RemoteGateway> gateway) {
        this.gateway = gateway;
    }

    void sendLater() {
        gateway.getObject().send();
    }
}
```

This is an illustration requiring appropriate `ObjectProvider`/`RemoteGateway`. The `Exporter` constructor can be called without instantiating the gateway target immediately. The dependency is resolved **when the method invokes the provider**, so it is not a "gateway target must be created before Exporter constructor" edge.

## 5. Distinguishing Dependency Graph and Import Graph

`@Import` is a mechanism for **combining bean definitions/configuration classes**, not a constraint that every bean in config A is created before every bean in config B.

```java
@Configuration(proxyBeanMethods = false)
@Import({RepositoryConfig.class, ServiceConfig.class})
class RootConfig {
}
```

This brings both configuration classes into the pipeline, producing bean definition metadata in the same container. However, the order:

```java
@Import({RepositoryConfig.class, ServiceConfig.class})
```

should not be used to claim "all repositories will finish before all services". If a service bean needs a repository, declare a constructor/factory method dependency. If two beans are independent, there is no business ordering contract.

### Proper Example: Compose at Root, Inject by Type

```java
@Configuration(proxyBeanMethods = false)
class RepositoryConfig {
    @Bean
    PurchaseRepository purchaseRepository() {
        return new InMemoryPurchaseRepository();
    }
}

@Configuration(proxyBeanMethods = false)
class ServiceConfig {
    @Bean
    PurchaseService purchaseService(PurchaseRepository repository) {
        return new PurchaseService(repository);
    }
}

@Configuration(proxyBeanMethods = false)
@Import({RepositoryConfig.class, ServiceConfig.class})
class RootConfig {
}
```

This is an illustrative example requiring matching Java classes/imports. `ServiceConfig` does **not** need to constructor-inject `RepositoryConfig` and call `repositoryConfig.purchaseRepository()`; the BeanFactory automatically resolves `PurchaseRepository` declared within the same context.

### XML Imports Also Only Merge Metadata

```xml
<import resource="modules/services.xml"/>
<import resource="modules/repositories.xml"/>
```

If `services.xml` contains `<constructor-arg ref="purchaseRepository"/>`, Spring still knows the service needs the repository. File listing order does not turn into business execution order, and Spring does not create two separate BeanFactories merely because two XMLs are used.

## 6. `@DependsOn` Adds an Edge to the Graph Without Supplying an Object Reference

With a constructor dependency, an edge A→B means A **needs an instance of B**. With `@DependsOn("schemaValidator")` on `reportService`, that edge only means the BeanFactory must **initialize `schemaValidator` before `reportService`** even though `reportService` does not accept the validator in its constructor:

```java
@Bean
@DependsOn("schemaValidator")
ReportService reportService() {
    return new ReportService();
}
```

In the graph, both kinds of edges enforce a prerequisite → dependent constraint during bean creation, yet only **DI via constructor/`@Bean` parameter** supplies the collaborator object. Do not use `@DependsOn` to repeat a dependency already clearly expressed by a parameter; use it when a separate initialization side effect is needed.

The XML equivalent is `depends-on="schemaValidator"`; the name in `@DependsOn` and XML is the **bean name**, not the Java class name. If the dependent is eager and the prerequisite is `@Lazy`, this edge can still cause the prerequisite to be created during refresh. If two beans form a cycle A→B→A, reordering `@Bean` methods or adding `@Order` cannot fix the graph.

Here the role of `@DependsOn` is **an additional edge when deriving a partial order**. The dedicated lesson on `@DependsOn` explained metadata, multiple prerequisites, XML/component scanning, and debugging bean names; this lesson applies them to the full dependency graph.

## 7. Destruction Order: Opposite Direction of Initialization Dependencies

An easily overlooked detail: `depends-on` does not only affect initialization; for **singleton beans**, it can also govern **reverse destruction order**.

Suppose A depends on B:

```text
Startup:
      B is initialized
      A is initialized

Shutdown:
      A is destroyed
      B is destroyed
```

Because A may need B for cleanup, the container must destroy A before destroying B. Spring documentation confirms `depends-on` for singleton beans specifies that the dependent bean is destroyed before its dependency.

### XML Example

```xml
<bean id="eventStore" class="example.EventStore"
      destroy-method="close"/>

<bean id="eventDispatcher" class="example.EventDispatcher"
      depends-on="eventStore"
      destroy-method="stop"/>
```

If both beans are managed singletons and the context closes normally, the ordering relationship keeps `eventStore` available while `eventDispatcher` shuts down.

### Limitations

- Destruction semantics depend on scope and lifecycle. Prototype beans do not have full destruction callbacks managed by the BeanFactory like singletons.
- If a destroy callback itself performs long I/O, hangs, or throws, resource management, timeouts, and observability are still needed.
- Do not rely on destruction order between two completely independent beans.
- With custom scopes, proxies, parent-child contexts, and external resources, check the specific lifecycle contract.

**Specifically:** `@DependsOn` is helpful when you truly need ordering for both startup and cleanup of infrastructure beans; however, explain the reason clearly in code review.

## 8. @Order Does NOT Control Singleton Startup Order

This is the most common misconception in this topic.

`org.springframework.core.annotation.Order` serves as an **ordering hint for multiple sorted objects/beans**, such as injecting a `List<Handler>`, `Ordered` components, bean post-processors, or contract-based extension-point ordering. **Spring's Javadoc states explicitly that `@Order` values do not determine the startup order of singleton beans**; that is a separate concern governed by the dependency graph and `@DependsOn`.

Example:

```java
@Bean
@Order(20)
Notifier backupNotifier() {
    return new BasicNotifier("backup");
}

@Bean
@Order(10)
Notifier priorityNotifier() {
    return new BasicNotifier("priority");
}

@Bean
NotifierRegistry notifierRegistry(List<Notifier> notifiers) {
    return new NotifierRegistry(notifiers);
}
```

If both notifier beans are resolved into `List<Notifier>`, Spring uses `@Order` on the `@Bean` methods to sort the **injected collection**, so `priority` comes before `backup`. However, from that you **must not infer** that `priorityNotifier`'s constructor ran before `backupNotifier`'s constructor.

### @Order on a @Configuration Class

The `@Order` annotation on configuration classes may influence **the order in which Spring evaluates configuration classes** in the corresponding pipeline, yet does not automatically govern the initialization order of every `@Bean` inside them. For bean ordering, rely on dependency relations.

### @Primary Does Not Determine Creation Order

`@Primary` helps choose a bean when an injection point has multiple candidates of the same type. It does not mean the primary bean will always be constructed before other beans.

### @Priority and Ordered Must Also Be Read in Context

`@Priority` and `Ordered` can influence candidate selection/sorting in extension points designed to support them. Do not treat priority values as a creation schedule for all singleton beans.

### Comparison Examples

| Need | Better mechanism |
| --- | --- |
| Service must have repository when running constructor | Constructor injection / `@Bean` parameter |
| Client needs schema initializer finished beforehand without holding a ref | `@DependsOn`/`depends-on` when appropriate |
| Pipeline receives `List<Handler>` in priority order | `@Order`/`Ordered` or ordering contract |
| Pick one default implementation among multiple candidates | `@Primary`/`@Qualifier` |
| Defer an expensive bean until first use | Intentional `@Lazy`/`ObjectProvider` |
| Coordinate phased start/stop of listeners | `SmartLifecycle`/lifecycle coordinator |
| Choose which configuration classes are loaded | `@Import`/`ImportSelector` or XML imports |

## 9. Initialization Order and *Method Execution* Order Differ

Suppose `PaymentService` depends on `PaymentRepository`. What Spring guarantees is that the dependency is resolved as required for bean creation, **not** that all subsequent business method calls follow a fixed order.

```java
PaymentService service = context.getBean(PaymentService.class);
service.pay(orderA);
service.pay(orderB);
```

The order of the two `pay` calls is orchestrated by **client code**, not inferred from the bean creation graph. If threads, events, reactive streams, or executors are involved, runtime concurrency must be designed separately.

### Constructor Finishing Does Not Mean the Bean Is Fully Initialized

A bean may still go through:

- Dependency population/property injection.
- Aware callbacks.
- BeanPostProcessor hooks.
- `@PostConstruct`.
- `InitializingBean.afterPropertiesSet()`.
- Custom init methods.
- AOP proxy wrapping/exposure.

With constructor injection, dependencies are resolved before the consumer constructor runs. With setter/field injection, the consumer's raw constructor can run before injection and init callbacks happen afterward. Therefore "initialization order" should clarify whether you mean **constructor start**, **constructor completion**, **property population**, or **bean fully initialized**.

## 10. Complete Example: Java 17 + Spring Framework 6.2

The runnable example focuses on **actual ordering constraints**, without forcing an order among independent beans.

Four mechanisms are demonstrated:

1. `Repository` is a direct dependency of `OrderService`.
2. `AuditInitializer` is not passed into the service constructor, yet `@DependsOn("auditInitializer")` forces it to initialize before the service.
3. `OrderController` depends on the service, so the service initializes before the controller.
4. Lazy `OptionalReport` has no eager consumer so it is not created at refresh.
5. Two `AlertChannel` beans are sorted by `@Order` **when injected into `List<AlertChannel>`**, without using that ordering to assert constructor startup sequence.

All output is computed from **guaranteed relationships**, avoiding printing a startup log dependent on creation order of unrelated beans.

### 10.1. Project Tree

```text
bean-dependency-order/
├── pom.xml
└── src/main/java/
    └── demo/
        └── BeanOrderDemo.java
```

### 10.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>bean-dependency-order</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 10.3. Complete Java Code

Create `src/main/java/demo/BeanOrderDemo.java`:

```java
package demo;

import java.util.ArrayList;
import java.util.List;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.DependsOn;
import org.springframework.context.annotation.Lazy;
import org.springframework.core.annotation.Order;

public class BeanOrderDemo {

    public static final class Trace {
        private final List<String> events = new ArrayList<>();

        public void mark(String event) {
            events.add(event);
        }

        public boolean contains(String event) {
            return events.contains(event);
        }

        public boolean before(String first, String second) {
            int a = events.indexOf(first);
            int b = events.indexOf(second);
            return a >= 0 && b >= 0 && a < b;
        }
    }

    public interface Repository {
        String find(String sku);
    }

    public static final class MemoryRepository implements Repository {
        public MemoryRepository(Trace trace) {
            trace.mark("repository.ready");
        }

        @Override
        public String find(String sku) {
            return "item:" + sku;
        }
    }

    public static final class AuditInitializer {
        public AuditInitializer(Trace trace) {
            trace.mark("audit.ready");
        }
    }

    public static final class OrderService {
        private final Repository repository;

        public OrderService(Repository repository, Trace trace) {
            this.repository = repository;
            trace.mark("service.ready");
        }

        public Repository repository() {
            return repository;
        }

        public String order(String sku) {
            return repository.find(sku);
        }
    }

    public static final class OrderController {
        private final OrderService service;

        public OrderController(OrderService service, Trace trace) {
            this.service = service;
            trace.mark("controller.ready");
        }

        public String show(String sku) {
            return "view:" + service.order(sku);
        }
    }

    public static final class OptionalReport {
        public OptionalReport(Trace trace) {
            trace.mark("optional.ready");
        }
    }

    public interface AlertChannel {
        String label();
    }

    public static final class BasicAlertChannel implements AlertChannel {
        private final String value;

        public BasicAlertChannel(String value) {
            this.value = value;
        }

        @Override
        public String label() {
            return value;
        }
    }

    public static final class AlertCatalog {
        private final List<AlertChannel> channels;

        public AlertCatalog(List<AlertChannel> channels) {
            this.channels = List.copyOf(channels);
        }

        public String labels() {
            return String.join(",",
                    channels.stream().map(AlertChannel::label).toList());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {

        @Bean
        public Trace trace() {
            return new Trace();
        }

        @Bean
        public Repository repository(Trace trace) {
            return new MemoryRepository(trace);
        }

        @Bean
        public AuditInitializer auditInitializer(Trace trace) {
            return new AuditInitializer(trace);
        }

        @Bean
        @DependsOn("auditInitializer")
        public OrderService orderService(
                Repository repository, Trace trace) {
            return new OrderService(repository, trace);
        }

        @Bean
        public OrderController orderController(
                OrderService service, Trace trace) {
            return new OrderController(service, trace);
        }

        @Bean
        @Lazy
        public OptionalReport optionalReport(Trace trace) {
            return new OptionalReport(trace);
        }

        @Bean
        @Order(20)
        public AlertChannel backupAlertChannel() {
            return new BasicAlertChannel("backup");
        }

        @Bean
        @Order(10)
        public AlertChannel priorityAlertChannel() {
            return new BasicAlertChannel("priority");
        }

        @Bean
        public AlertCatalog alertCatalog(List<AlertChannel> channels) {
            return new AlertCatalog(channels);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            Trace trace = context.getBean(Trace.class);
            OrderService service = context.getBean(OrderService.class);
            OrderController controller =
                    context.getBean(OrderController.class);
            AlertCatalog alerts = context.getBean(AlertCatalog.class);

            System.out.println("repository.before.service=" +
                    trace.before("repository.ready", "service.ready"));
            System.out.println("audit.before.service=" +
                    trace.before("audit.ready", "service.ready"));
            System.out.println("service.before.controller=" +
                    trace.before("service.ready", "controller.ready"));
            System.out.println("managed.repository.same=" +
                    (service.repository() == context.getBean(Repository.class)));
            System.out.println("controller=" +
                    controller.show("BK-7"));
            System.out.println("alerts=" + alerts.labels());
            System.out.println("optional.before.lookup=" +
                    trace.contains("optional.ready"));

            OptionalReport first =
                    context.getBean(OptionalReport.class);
            OptionalReport second =
                    context.getBean(OptionalReport.class);

            System.out.println("optional.after.lookup=" +
                    trace.contains("optional.ready"));
            System.out.println("optional.sameSingleton=" + (first == second));
        }
    }
}
```

### 10.4. Run Command

Requires Java 17+, Maven, and dependencies cached locally or access to the Maven repository to download on first run:

```bash
mvn -q clean compile exec:java -Dexec.mainClass=demo.BeanOrderDemo
```

### 10.5. Expected Output

These are the lines **printed by the program**, excluding Maven/Spring logs configured by the environment:

```text
repository.before.service=true
audit.before.service=true
service.before.controller=true
managed.repository.same=true
controller=view:item:BK-7
alerts=priority,backup
optional.before.lookup=false
optional.after.lookup=true
optional.sameSingleton=true
```

### 10.6. Output Explanation

**`repository.before.service=true`:** `orderService(Repository repository, Trace trace)` only runs once Spring has resolved the repository singleton. `MemoryRepository`'s constructor marks `repository.ready` before the factory method creating `OrderService` marks `service.ready`.

**`audit.before.service=true`:** `@DependsOn("auditInitializer")` adds an ordering edge, even though the service constructor does not take `AuditInitializer`. Spring must create `auditInitializer` before `orderService`.

**`service.before.controller=true`:** `Controller` requires `OrderService` in its factory method parameter. Spring finishes creating the service before the factory method creating the controller marks `controller.ready`.

**`managed.repository.same=true`:** The service receives the managed `Repository` singleton via BeanFactory resolution, without calling `new MemoryRepository(...)` directly in business code.

**`controller=view:item:BK-7`:** The controller uses the injected service and repository to produce the string. **Runtime method usage** order is determined by the `controller.show(...)` call in `main`, not by order annotations.

**`alerts=priority,backup`:** `@Order(10)` on `priorityAlertChannel` and `@Order(20)` on `backupAlertChannel` sort the `List<AlertChannel>` injected into `AlertCatalog`. It does not prove the priority channel constructor ran before the backup channel constructor.

**`optional.before.lookup=false`:** `OptionalReport` is a lazy singleton, and no eager bean requires it; its constructor has not recorded the event when app refresh finishes.

**`optional.after.lookup=true`:** After `context.getBean(OptionalReport.class)`, the lazy bean is created and marks `Trace`.

**`optional.sameSingleton=true`:** Lazy does not change scope; two lookups in the same context return the same singleton bean.

### 10.7. Why Does This Example Not Depend on Unguaranteed Order?

We do not print all of `Trace.events` as a single fixed sequence. Since `repository` and `auditInitializer` are two independent prerequisites of `service`, there is no need to assert which is created before the other. `trace.before(a,b)` only checks the edges that actually exist. This is **the right kind of property to test for what Spring promises**.

The program also does not rely on `@Bean` method order in `AppConfig`, does not require component scanning, does not use a static global mutable list, has no background threads, and does not call `optionalReport` before measuring laziness.

### 10.8. Why Is @Configuration(proxyBeanMethods=false) Still Correct Here?

All dependencies in the demo are requested through **`@Bean` method parameters**. No factory method directly calls another `@Bean` method to create a collaborator. Therefore CGLIB interception of a full configuration is unnecessary to preserve singleton identity.

If you changed it to call `repository(trace())` as a direct Java method inside `orderService()` while `proxyBeanMethods=false`, you could create separate Java objects outside the BeanFactory and break managed dependency identity. That is not the right way to express the dependency graph.

## 11. Extended Project Exercise: Demonstrating @Order Differs from @DependsOn

You can try two separate changes to see that they control different aspects.

### Try A — Swap @Order on AlertChannels

Change to:

```java
@Bean
@Order(5)
AlertChannel backupAlertChannel() {
    return new BasicAlertChannel("backup");
}

@Bean
@Order(50)
AlertChannel priorityAlertChannel() {
    return new BasicAlertChannel("priority");
}
```

When injecting `List<AlertChannel>`, the list is sorted as `backup,priority`. However, you **must not** infer that Spring reversed the construction order of those two singletons. Only test collection semantics.

### Try B — Remove @DependsOn from orderService

Remove:

```java
@DependsOn("auditInitializer")
```

The service still has the repository dependency because the factory method takes `Repository`. However, the **constraint of audit before service is no longer declared**. Since `auditInitializer` and `orderService` are eager singletons independent apart from shared dependencies, startup might still coincidentally mark audit before service in one build. **Do not use a single run like that to conclude a guarantee still exists.**

The right takeaway is: once the annotation is removed, **there is no longer a contract** forcing `auditInitializer` to finish before `orderService`. If the application genuinely needs that, keep the explicit dependency or refactor so the service constructor accepts the required collaborator.

## 12. XML constructor-arg, property, and depends-on

XML also builds the shared dependency graph in the BeanFactory.

### Constructor Dependency

```xml
<bean id="repository"
      class="example.InMemoryRepository"/>

<bean id="service"
      class="example.OrderService">
    <constructor-arg ref="repository"/>
</bean>

<bean id="controller"
      class="example.OrderController">
    <constructor-arg ref="service"/>
</bean>
```

From the refs, the graph is:

```text
controller -> service -> repository
```

Even if the three `<bean>` elements are written in the order controller, service, repository, Spring still resolves refs to call the right constructors. Example classes must have compatible constructors.

### Property Dependency

```xml
<bean id="service" class="example.MutableService">
    <property name="repository" ref="repository"/>
</bean>
```

Spring creates the raw `MutableService` object and then injects `repository` via setter/property before regular init callbacks. You should not assume the service constructor necessarily starts only **after** the repository constructor in every setter-injection scenario.

### Explicit depends-on

```xml
<bean id="eventStore" class="example.EventStore"/>

<bean id="dispatcher"
      class="example.Dispatcher"
      depends-on="eventStore"/>
```

Even though `Dispatcher` has no constructor/property reference to `EventStore`, `depends-on` forces the store to be initialized before the dispatcher. If singleton beans are destroyed per dependencies, the dependent dispatcher is destroyed before the event store.

### One XML File or Multiple XML Files Does Not Alter the Graph

`<import resource="repositories.xml"/>` and `<import resource="services.xml"/>` merely import bean definitions from multiple resources into **the same container**. The DI graph is still expressed through `ref` and explicit `depends-on` metadata. Do not rely on import position as a creation order for all beans across files.

## 13. Dependency Created First, Yet BeanFactory Still Has a Lifecycle

When saying "bean B must be initialized before A", there can be several milestones:

- B's constructor is called.
- B's properties are populated.
- B has run `@PostConstruct`.
- B has run `InitializingBean.afterPropertiesSet()` or custom init.
- B has passed through `BeanPostProcessor` and may be wrapped in a proxy.
- A's constructor/factory method receives the appropriate object.
- A completes initialization.

### 13.1. Constructor Injection and Fully Initialized Beans

For a non-circular constructor reference `A(B)`, Spring normally resolves B through the BeanFactory before it can invoke A's constructor. B is created and passes through its regular lifecycle to supply an appropriate reference to A.

### 13.2. Circular Setter/Field Injection Is a Special Case

Spring can support certain circular references via early singleton references when configured to allow them. In those cases, A may see a reference to bean B **currently in creation**, not yet fully initialized. Therefore you cannot state unconditionally that every dependency graph with a cycle always has a topological initialization order.

### 13.3. BeanPostProcessor May Return a Proxy

A may receive a proxy for B rather than the raw B object. Proxying does not itself break dependency contracts; however, lazy-resolution proxies or scoped proxies can defer **target** creation. Distinguish "already has a proxy reference" from "target has been constructed".

### 13.4. @PostConstruct Is Not a Milestone Where Every Bean in the Context Is Done

A bean's `@PostConstruct` is called during **that bean's** lifecycle. It does not guarantee every unrelated bean has initialized. If a callback needs to see all regular non-lazy singleton beans, consider `SmartInitializingSingleton` or an appropriate hook instead of using `@PostConstruct` arbitrarily.

## 14. Circular Dependencies and Non-Existence of a Topological Order

If the graph has a cycle:

```text
A -> B -> C -> A
```

no order satisfies "B before A", "C before B", and "A before C" simultaneously. This is why constructor injection cycles typically lead to creation failures such as `BeanCurrentlyInCreationException` in the exception chain.

### 14.1. Unsolvable Example with Constructors

```java
final class PaymentService {
    PaymentService(OrderService orders) {
    }
}

final class OrderService {
    OrderService(PaymentService payments) {
    }
}
```

Both constructors require the other to already exist in order to construct themselves, leaving no starting point.

### 14.2. Swapping @Bean Method Positions Does Not Fix the Cycle

```java
@Bean
PaymentService paymentService(OrderService orders) {
    return new PaymentService(orders);
}

@Bean
OrderService orderService(PaymentService payments) {
    return new OrderService(payments);
}
```

Swapping the two methods does not change the A↔B graph.

### 14.3. Cyclic @DependsOn Makes Things Worse

```java
@Bean
@DependsOn("b")
A a() {
    return new A();
}

@Bean
@DependsOn("a")
B b() {
    return new B();
}
```

If A must be created after B and B must be created after A, the ordering metadata contradicts itself. You cannot fix this by adding `@Order` because `@Order` is not startup ordering.

### 14.4. How to Refactor

Before:

```text
OrderService <----> PaymentService
```

After:

```text
           CheckoutCoordinator
              /          \
             v            v
       OrderService    PaymentService
```

Or extract `PaymentPolicy`/`SharedRules` so both services depend on a common abstraction instead of depending on each other in reverse. The goal is a dependency graph that **never returns to a vertex currently in creation**.

### 14.5. Do @Lazy and ObjectProvider Break Cycles?

An `@Lazy` injection point can supply a lazy-resolution proxy for one edge and allow a constructor to finish in some cases. `ObjectProvider<T>` can defer lookup to another method. Yet the bidirectional logical relationship may still exist and errors return if dereferenced too early. They are **no substitute** for dependency inversion.

## 15. Scope Affects When Edges Are Executed

### Non-Lazy Singleton

Non-lazy singleton beans are normally created by Spring's `ApplicationContext` during refresh. When creating an eager singleton, its dependencies are resolved. This is the clearest context for startup ordering.

### Lazy Singleton

```java
@Bean
@Lazy
ExpensiveRules expensiveRules() {
    return new ExpensiveRules();
}
```

This bean may not appear during pre-instantiation. However, if an eager consumer requires it as a constructor parameter, it is still created. If it is only invoked via a provider/proxy for the first time after refresh, dependency creation happens later.

### Prototype

```java
@Bean
@Scope("prototype")
Worker worker() {
    return new Worker();
}
```

Prototype beans are not bulk pre-instantiated like singletons, yet one can be created **during startup** if an eager singleton constructor needs a `Worker` to inject. The singleton keeps the injected `Worker`; it does not automatically receive a new instance for each business invocation.

### Request/Session Scopes

A scoped proxy can be injected into a singleton while the target request/session bean does not yet exist in the corresponding scope. The dependency edge between the singleton and **the proxy** differs from initializing the target during a later request. Do not assume request-scoped targets must finish during `ApplicationContext` refresh.

### @DependsOn with Lazy and Scope

`@DependsOn("x")` can cause a lazy singleton `x` to be created early when an eager dependent singleton is created. Destruction/shutdown behavior is governed by singleton lifecycle; do not generalize it directly to prototypes or all custom scopes.

## 16. SmartInitializingSingleton and the "After Eager Beans" Moment

`org.springframework.beans.factory.SmartInitializingSingleton` provides the callback:

```java
@Override
public void afterSingletonsInstantiated() {
    // Short logic after pre-instantiation of regular non-lazy singletons.
}
```

If an eager singleton implements this interface, the callback runs after the BeanFactory completes pre-instantiation of regular non-lazy singletons. Thus it can be suitable when a post-initialization step is needed after regular singletons, rather than assuming an order among beans that have no dependencies.

### Not All Beans Exist Yet

- Unrequested lazy singletons may not have been created yet.
- Prototype beans are created only on demand.
- Certain scoped targets require an active request/session.
- External services may not be ready yet.
- A lazy bean's callback created after bootstrap is not normally invoked late as a "post-check for every new singleton".

### SmartInitializingSingleton Differs from SmartLifecycle

`SmartInitializingSingleton` suits a callback at the end of pre-instantiation. `SmartLifecycle` supports start/stop and phase ordering for lifecycle-aware components. If the application has consumers, listeners, schedulers, or long-running processes, use the appropriate lifecycle abstraction instead of forcing bean constructors to run on a schedule.

### ContextRefreshedEvent and Boot Readiness

`ContextRefreshedEvent` is published per the Spring Context refresh lifecycle after the appropriate steps; Spring Boot's `ApplicationReadyEvent` sits at a higher stage of Boot startup. Do not equate either with "every external dependency is healthy".

## 17. @Order in Collection Injection: Understanding Its Exact Scope

Suppose a bean needs all `Handler` implementations:

```java
@Bean
Pipeline pipeline(List<Handler> handlers) {
    return new Pipeline(handlers);
}
```

Spring can sort `List<Handler>` based on:

- `@Order` on component classes.
- `@Order` on `@Bean` methods.
- `Ordered` on the corresponding objects.
- Other priority/ordering contracts depending on the injection mechanism.

If we have:

```java
@Bean
@Order(50)
Handler standardHandler() {
    return new StandardHandler();
}

@Bean
@Order(5)
Handler urgentHandler() {
    return new UrgentHandler();
}
```

`Pipeline` normally receives handlers ordered `urgent` before `standard`. Yet that statement only describes **element positions inside the List**. Spring may have constructed the standard bean first because another dependency demanded it early. Do not test `@Order` using constructor log order.

### When Stage Execution Ordering Is Needed

With `List<Handler>` already sorted properly by Spring, **Pipeline itself iterates over the List** to execute stages. That is intentional business execution order. `@Order` does not automatically invoke bean methods in any order.

## 18. Another Trap: Direct Calls Between @Bean Methods

```java
@Configuration(proxyBeanMethods = false)
class UnsafeConfig {
    @Bean
    Repository repository() {
        return new Repository();
    }

    @Bean
    Service service() {
        return new Service(repository());
    }
}
```

With `proxyBeanMethods=false`, calling `repository()` inside `service()` is an ordinary **Java method call**, which can construct a second `Repository` object outside the managed `repository` bean. In doing so you have **bypassed** the graph reference Spring needs to know about.

The right way:

```java
@Configuration(proxyBeanMethods = false)
class SafeConfig {
    @Bean
    Repository repository() {
        return new Repository();
    }

    @Bean
    Service service(Repository repository) {
        return new Service(repository);
    }
}
```

Spring resolves and passes the managed `Repository` bean, enabling proper ordering/dependency tracking/lifecycle handling.

### What About Full @Configuration?

With `@Configuration(proxyBeanMethods=true)` on a managed enhanced config, inter-bean method calls can be CGLIB-intercepted to retrieve the Spring-managed bean. Still, coupling factory methods via direct calls is harder to refactor than method parameter injection. In lite mode or when invoked on a manually instantiated `new Config()`, CGLIB semantics do not apply as you might expect.

## 19. Background Initialization in Spring Framework 6.2

Spring Framework 6.2 adds a background bootstrap option for `@Bean` methods in supported cases, such as `@Bean(bootstrap = Bean.Bootstrap.BACKGROUND)`.

This mechanism allows certain beans to be initialized in the background during startup instead of running all bean creation sequentially on the refresh thread. This is an **additional reason to avoid inferring a total order** from source line order or logs.

Conceptual limits to remember:

- Non-lazy dependency injection points needing the real instance **must wait** until the dependency is ready for use.
- With background initialization, some beans can begin construction concurrently when no mandatory dependency edge exists.
- BeanFactory/context orchestration must still uphold the corresponding startup contract.
- Do not assume every regular bean constructor runs on the main thread.
- Dependencies/proxies require proper thread safety and lifecycles.
- When background beans are accessed from another bean's `@PostConstruct` or custom infrastructure, check bootstrap mode semantics.

Illustrative syntax example:

```java
@Bean(bootstrap = Bean.Bootstrap.BACKGROUND)
RemoteMetadataClient remoteMetadataClient() {
    return new RemoteMetadataClient();
}
```

In Spring Framework, not every background configuration automatically has a suitable executor or produces identical behavior across all environments; consult the documentation/setup for your exact version before using it in production. The main runnable example **does not enable background initialization**, to keep the graph illustration simple.

**What does not change:** Increasing concurrency does not erase dependency edges; a consumer cannot be treated as complete while a required collaborator is not yet ready.

## 20. Infrastructure Configuration and Early Initialization

Certain beans do not follow a simple application initialization schedule because they participate in **setting up the BeanFactory itself**:

- `BeanDefinitionRegistryPostProcessor`.
- `BeanFactoryPostProcessor`.
- `BeanPostProcessor`.
- Beans involved in resource loading, proxies, and property resolution.
- `FactoryBean` with product/factory semantics.

These components can be processed **before pre-instantiation of regular application singletons**. Therefore do not use them to "fetch every business bean early" via `getBean()`.

### BeanFactoryPostProcessor Is Not the Place to Initialize the Business Graph

A post-processor should manipulate bean metadata per its contract. Calling `getBean("billingService")` at this stage can create `billingService` before BeanPostProcessors/AOP features are fully registered, causing "not eligible for processing" warnings or unpredictable behavior.

### Static @Bean for Infrastructure Post-Processors

In scenarios recommended by Spring docs, declaring `static @Bean` when defining a `BeanFactoryPostProcessor` can avoid forcing the `@Configuration` instance to initialize prematurely. This is an infrastructure lifecycle technique, not a way to impose arbitrary ordering on two business beans.

### FactoryBean

With `FactoryBean<T>`, there is a factory object and a product bean. The BeanFactory may need to inspect the factory to determine product type; some factories/products have distinct eager initialization semantics. Hence "definition registration order" and "product construction order" should even less be treated as equivalent.

## 21. Common Issues and How to Diagnose Them

| Symptom | Why does it happen? | How to handle |
| --- | --- | --- |
| B constructor runs before A even though `@Bean a()` is written first | A depends on B | This is expected DI behavior |
| Startup order changes after refactoring | Some beans are independent with no ordering constraint | Do not depend on accidental order; add dependency if truly needed |
| `@Order(1)` does not make bean initialize first | `@Order` does not control singleton startup | Use dependencies/`@DependsOn` according to true semantics |
| XML service declared before repo yet still runs | `ref` points to repo; Spring resolves dependencies | Expected; do not use XML line order to control timing |
| `@Import` order A, B differs from bean startup | Import merges config metadata, not a startup schedule | Use `@Bean` method parameters |
| `@Lazy` bean still created during refresh | An eager bean requires it | Inspect the dependency graph |
| Prototype bean appears at startup | Eager singleton injects prototype | Not bulk prototype pre-instantiation |
| `@DependsOn` does not pass object into constructor | It only sets an ordering constraint | Use constructor param/ref for instance dependency |
| `BeanCurrentlyInCreationException` cycle | Constructor/metadata graph has a cycle | Refactor dependency direction |
| Bean constructor runs before setter dependency | Raw instance created before property population | Do not confuse constructor-start with fully initialized |
| Handler order is right yet constructor logs are reversed | Collection sorting differs from startup order | Test the list/selection, not constructor order |
| Resource shuts down earlier than consumer | Missing/mis-modeled lifecycle dependency | Add explicit dependency and proper destroy callbacks |
| `SmartInitializingSingleton` callback runs while lazy bean is uncreated | Hook is only after regular non-lazy pre-instantiation | Do not assume all lazy/prototype beans exist |
| Slow startup due to heavy dependency chain | Eager bean pulls in many collaborators | Profile constructors/init; consider lazy/provider if appropriate |
| Creation timing differs in prod | Different profiles/conditions/scopes/post-processors/background bootstrap | Test with the exact root context and runtime config |
| AOP not applied to a bean created too early | Bean initialized before BeanPostProcessor registration | Avoid early `getBean` in infrastructure |
| `@Bean` returns duplicate objects | Direct method call under `proxyBeanMethods=false` | Use factory method parameter injection |
| `@DependsOn` introduces a new cycle | A depends on B and B depends on A | Remove the wrong ordering edge |
| Multiple beans of same type cause ambiguity | Multiple definitions after import/scan | Proper Qualifier/Primary |
| Context refresh succeeds yet external service fails | Instance initialized does not prove remote readiness | Health checks/timeouts/retries and readiness policies |

### Investigation Workflow

1. Identify the **bean name** reporting the error and the phase (definition parsing, creation, injection, initialization, or shutdown).
2. Find constructors and `@Bean` factory method signatures.
3. Draw all dependency edges: constructors, properties, `@Autowired`, refs, `@DependsOn`.
4. Identify scope/lazy settings; find eager beans pulling targets into startup.
5. Separate beans **with dependency paths** from **independent beans**.
6. If there is a cycle, refactor the graph instead of changing declaration order.
7. If only list sorting is needed, use `@Order`/`Ordered` at the injection point.
8. Distinguish constructor, init callback, `SmartInitializingSingleton`, and lifecycle startup.
9. For Framework 6.2 background init/AOP/FactoryBean, inspect exception mechanisms and thread semantics.
10. Write integration tests around **constraints that must hold**; do not assert full log order.

## 22. Testing Order with Contract-Accurate Assertions

In the Section 10 example, instead of checking that `Trace.events` is strictly `[repository, audit, service, controller]`, we check the ordering inequalities:

```java
if (!trace.before("repository.ready", "service.ready")) {
    throw new AssertionError("Repository must precede service");
}
if (!trace.before("audit.ready", "service.ready")) {
    throw new AssertionError("Audit must precede service");
}
if (!trace.before("service.ready", "controller.ready")) {
    throw new AssertionError("Service must precede controller");
}
```

These are **supplemental lines inside `main` after the context is created**, using `Trace` from the example project. They verify required edges without imposing an order between `repository` and `audit`.

### If a Test Needs to Verify a Bean Definition Exists

You can check:

```java
boolean exists =
        context.getBeanFactory().containsBeanDefinition("orderService");
```

This is a metadata check. It does not prove `orderService` has been created if the bean is lazy or registered via another mechanism.

### Checking Whether a Singleton Was Created Without Triggering Creation

```java
boolean created =
        context.getBeanFactory().containsSingleton("optionalReport");
```

For lazy `optionalReport` not yet requested, the result is normally false. **Do not call `getBean("optionalReport")` before checking** if the goal is measuring pre-first-use state.

### Testing Lifecycle Destruction

If service and repository hold resources, add destroy callbacks that record markers and close the ApplicationContext; assert that the consumer is destroyed before the dependency when the dependency was properly registered. Do not use direct `new` outside the container when testing lifetime semantics.

### Why Not Assert Exact Global Order?

The BeanFactory may change registration order, add infrastructure beans, change background initialization, refactor configs, or create independent beans in a different order. A test enforcing the entire sequence of constructor logs is usually **flaky** and does not verify actual business requirements.

## 23. Exercises with Answers

### Exercise 1 — Drawing the Graph

A takes B and C in its constructor; B takes D; C is independent of D. Draw the dependency graph and state the constraints.

**Answer:**

```text
      A
     / \
    v   v
    B   C
    |
    v
    D
```

D must be created/resolved before B, and B and C before A's constructor is called with the corresponding references. There is no direct constraint on the relative order of C and D.

### Exercise 2 — Two Valid Orders

For the graph in Exercise 1, list two valid linearizations.

**Answer:** `D,B,C,A` and `C,D,B,A` both satisfy the constraints. These are mathematically possible orders, not a promise that Spring will choose them.

### Exercise 3 — Swapping @Bean Order

Factory method `@Bean Controller controller(Service s)` sits before `@Bean Service service(Repository r)` in Java. Does that cause Spring to create Controller before Service?

**Answer:** No, Spring must resolve the `Service` parameter before invoking the factory method creating the controller.

### Exercise 4 — XML ref

`<bean id="service">` sits before `<bean id="repo">` in XML, yet service has constructor-arg `ref="repo"`. Must you reorder them in the file to run?

**Answer:** No. The BeanFactory can resolve `repo` from registered definitions, independent of which tag appears earlier/later in the file.

### Exercise 5 — @Order

Two `Handler` beans have `@Order(1)` and `@Order(20)`. Is the bean with order 1 guaranteed to construct first?

**Answer:** No. `@Order` affects sorting in supported places such as `List<Handler>` injection, and does not guarantee singleton startup order.

### Exercise 6 — @DependsOn

Bean `ReportService` does not accept a `SchemaValidator` reference, yet must initialize after the validator finishes. Write the annotation.

**Answer:**

```java
@Bean
@DependsOn("schemaValidator")
ReportService reportService() {
    return new ReportService();
}
```

The name `schemaValidator` must match the actual bean name.

### Exercise 7 — Destruction

If singleton A has `depends-on="b"` and both have destroy callbacks, which is normally destroyed first?

**Answer:** A (the dependent) is destroyed before B (the dependency), so B remains available while A cleans up.

### Exercise 8 — Lazy Dependency

Eager singleton A's constructor requires lazy singleton B. When Spring refreshes, can B be created?

**Answer:** Yes, normally it must be; A cannot complete its constructor without a B instance.

### Exercise 9 — @DependsOn and Lazy

Eager A has `@DependsOn("b")`, and B is lazy. Can B be initialized before A?

**Answer:** Yes. Explicit ordering is a cause of dependency-driven creation, even though B is lazy.

### Exercise 10 — Setter Injection

`new Consumer()` constructor runs before BeanFactory calls `setRepository(...)`. Does this violate "dependency before consumer"?

**Answer:** No. With setter injection, the raw consumer object may already be constructed; Spring resolves the dependency to **populate the property before the bean completes normal initialization**. Be clear which milestone is being compared.

### Exercise 11 — Multiple @Import

`@Import({ServiceConfig.class, RepoConfig.class})`, and service factory accepts `Repository`. Must you swap them so `RepoConfig` comes first?

**Answer:** No, because the DI dependency graph determines that `Repo` must be resolved before `Service` when service creation requires `repo`.

### Exercise 12 — Prototype

Eager singleton A's constructor takes prototype B. Can B be created during startup? Does A receive a new B on every method call?

**Answer:** B is created to be injected into A when A is built. A normally keeps the received instance rather than changing on each call; use a provider if a per-operation prototype is needed.

### Exercise 13 — Cycle

A's constructor needs B, B's constructor needs C, and C's constructor needs A. Does changing declaration order help?

**Answer:** No. A directed cycle has no valid topological order; you must adjust the architecture/refactor dependency direction.

### Exercise 14 — SmartInitializingSingleton

Does the `afterSingletonsInstantiated` callback mean every lazy bean has already been created?

**Answer:** No. It is tied to the end of regular non-lazy singleton pre-instantiation; unrequested lazy beans can still remain uncreated.

### Exercise 15 — Runtime Method Calls

Spring creates A before B due to a dependency edge. Does that mean when requests arrive, B always runs its business method after A?

**Answer:** No. Runtime method execution is determined by callers, threads, events, and orchestration, not bean initialization ordering.

### Exercise 16 — Predicting Example Output

Why are `repository.before.service` and `audit.before.service` both true, yet there is no assertion for `repository.before.audit`?

**Answer:** `repo` is a constructor dependency of `service`, and `audit` is a `@DependsOn` dependency of `service`. Between `repo` and `audit`, there is no edge enforcing relative order.

### Exercise 17 — Changing @Order

If you swap `@Order(10)`/`@Order(20)` on the `AlertChannel` beans, what changes most clearly?

**Answer:** The order of elements in `List<AlertChannel>` received by `AlertCatalog`. Do not infer that constructor startup order changed.

### Exercise 18 — One-Direction Design

An application has `RepositoryService` and `BillingService` needing each other in their constructors. Propose a refactoring.

**Guided answer:** Identify who genuinely owns the business orchestration; move coordination into a third bean or extract a shared abstraction/policy. Keep the repository layer from depending backward on the application service, making the dependency graph unidirectional.

### Exercise 19 — Testing Partial Rather Than Total Order

Suppose startup logs happen to print `audit, repo, service, controller`. After a framework upgrade they print `repo, audit, service, controller`. Should this be considered a regression?

**Answer:** No, if the contract is only audit before service, repo before service, and service before controller. Both sequences are valid.

### Exercise 20 — @Bean bootstrap BACKGROUND

If B is created on a background thread in Spring Framework 6.2 and A's constructor needs the real B, can A enter the fully initialized state before B is ready?

**Answer:** Not for a required non-lazy dependency instance under contract; the container must wait/resolve B appropriately. However, independent beans may proceed concurrently, making it even more important not to assert a global constructor order.

## 24. Spring Configuration Review Checklist

- [ ] Mapped real dependency edges from constructors, setters, fields, and factory method params.
- [ ] Distinguished bean definition registration order from instance creation order.
- [ ] Understood Spring guarantees constraints, not necessarily a global total order.
- [ ] Did not make business logic depend on the initialization order of two independent singletons.
- [ ] `@Bean` methods use parameters to receive collaborators instead of direct calls in lite mode.
- [ ] `@Import`/XML imports only merge definitions, without changing the dependency graph.
- [ ] `@DependsOn` has a clear reason and accurate bean names.
- [ ] Did not add `@DependsOn` merely to duplicate constructor dependencies.
- [ ] Understood `@DependsOn` also affects singleton destruction order.
- [ ] Did not use `@Order` as startup control; only for sorting/selection per contract.
- [ ] Dependency graph has no constructor cycles.
- [ ] Eager/lazy settings match dependency chains and startup goals.
- [ ] A lazy bean required by an eager consumer can still be created early.
- [ ] Setter/field injection is understood as population lifecycle, not confused with constructor order.
- [ ] Scoped/lazy proxies and `ObjectProvider` are treated as deferred target resolution when actually used.
- [ ] Startup hooks/`SmartInitializingSingleton` are not confused with runtime readiness.
- [ ] `SmartLifecycle` is used when phased start/stop is needed.
- [ ] BeanFactory post-processors do not arbitrarily invoke business beans early.
- [ ] If 6.2 background bootstrap is enabled, evaluated concurrency and dependency waiting.
- [ ] Tests assert each required edge rather than ordering between independent nodes.
- [ ] Tests cover startup, lazy first-use, destroy callbacks, and profile configurations when critical.
- [ ] Did not use `getBean` to check whether a lazy bean was created if aiming not to trigger creation.
- [ ] Did not put heavy business side effects in constructors just to force ordering.
- [ ] Startup health/readiness is designed separately from BeanFactory creation.

## Conclusion

**Bean initialization order in Spring comes from the dependency graph**, meaning the container resolves the collaborators a bean needs to complete construction and initialization. `@DependsOn` can add ordering edges for dependencies not expressed via constructor/property references. The result is a **partial order**: dependency constraints are guaranteed, whereas ordering between independent beans **should not be treated as a contract**.

Specifically:

- `@Bean` declaration order, `@Import` order, and XML source order **do not replace dependency edges**.
- `@Order` controls ordering semantics such as injected collections, **not** singleton startup order.
- `@Lazy` and scopes affect *when* a target is needed; eager dependencies can still cause lazy beans to be created.
- A constructor cycle A→B→A cannot be fixed by reordering declarations.
- Singleton cleanup generally follows the reverse of dependencies to preserve; explicit `depends-on` can affect destruction order.

Use constructor/factory method parameter injection to describe real dependencies, `@DependsOn` when implicit initialization ordering is genuinely required, and a lifecycle coordinator when the requirement is a **startup/shutdown workflow** rather than mere object creation. When testing, verify **required constraints** rather than an accidental sequence of constructor logs.

## Official Documentation

- [Spring Framework — Using depends-on](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-dependson.html): initialization order, XML `depends-on`, singleton destruction order.
- [Spring Framework — Lazy-initialized Beans](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-lazy-init.html): pre-instantiation, lazy dependencies required by eager singletons.
- [Spring Framework — Dependency Injection](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-collaborators.html): constructor/property dependency resolution.
- [Spring Framework — Using @Autowired](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired.html): `@Order`/`Ordered` on injected collections vs singleton startup order.
- [Spring Framework — Composing Java-based Configurations](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/composing-configuration-classes.html): `@Import`, `@Bean` wiring, `@DependsOn`, and Spring 6.2 background initialization.
- [Spring Framework 6.2 — @Order API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/core/annotation/Order.html): ordering priority vs singleton startup.
- [Spring Framework 6.2 — @DependsOn API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/annotation/DependsOn.html): bean names and initialization/destruction order.
- [Spring Framework 6.2 — SmartInitializingSingleton API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/beans/factory/SmartInitializingSingleton.html): callback after regular singleton pre-instantiation.
