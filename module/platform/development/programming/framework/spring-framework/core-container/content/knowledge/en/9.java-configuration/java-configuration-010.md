# Separating Object Creation from Business Bootstrap Work in Spring Java Configuration

## 1. Goal and Core Idea

In the Spring Core Container, `@Configuration` and `@Bean` let you tell the IoC container **how objects should be constructed** and **which beans they depend on**. However, an object existing in the container does not mean the application has finished all **business bootstrap work**—such as loading seed data, validating service launch preconditions, building reference catalogs, registering with an external system, or triggering an operational workflow.

A common design mistake is putting those business operations directly inside the body of `@Bean`:

```java
// Counter-example: not a standalone program.
@Bean
CustomerService customerService(CustomerRepository repository) {
    CustomerService service = new CustomerService(repository);
    service.importSeedCustomers(); // Business operation happens during bean creation.
    return service;
}
```

The factory method now performs both **wiring** and **executing a use case with side effects**. Consequences can include startup depending on I/O, transactions running too early, test contexts mutating data, difficult retries, poor ordering control, and repeated execution whenever another bean/context is created.

You should separate three responsibilities:

1. **Object construction / bean wiring:** creating objects, wiring dependencies, and configuring immutable values. This belongs to constructors and `@Bean` factory methods.
2. **Bean-local initialization:** validating configuration, preparing internal structures, and opening resources owned by the bean itself when genuinely necessary. This belongs to `@PostConstruct`, `@Bean(initMethod=...)`, or corresponding lifecycle callbacks.
3. **Application/business bootstrap:** coordinating business actions once required collaborators are ready, with explicit idempotency, transaction, error, and observability policies. This usually belongs to a **startup coordinator** or an explicit business entry point, which can be triggered via `SmartInitializingSingleton`, `ContextRefreshedEvent`, `SmartLifecycle`, or the appropriate runtime mechanism.

**Principle:** `@Bean` declares **how to build a bean**; a business service declares **behavior**; a bootstrap coordinator decides **when to run initialization behavior**. Never turn constructors or factory methods into places that execute business workflows.

This lesson belongs to **Java Configuration — Spring Framework Core Container**. Spring Boot's `ApplicationRunner`, `CommandLineRunner`, and `ApplicationReadyEvent` are mentioned only for boundary comparison and are not used in the plain Spring Framework example.

## 2. Three Distinct Phases to Separate

### 2.1. Phase A — object creation and dependency wiring

```java
@Configuration(proxyBeanMethods = false)
class AppConfig {

    @Bean
    OrderRepository orderRepository() {
        return new InMemoryOrderRepository();
    }

    @Bean
    OrderService orderService(OrderRepository repository) {
        return new OrderService(repository);
    }
}
```

This is an **illustration requiring definitions** of `OrderRepository`, `InMemoryOrderRepository`, and `OrderService`. `@Bean`'s role is solely building objects and expressing dependencies:

- `orderRepository()` supplies the repository implementation object.
- `orderService(OrderRepository repository)` asks Spring to resolve the repository and pass it into the service.
- Spring decides bean creation timing based on scope, lazy/eager semantics, and the dependency graph.
- There is no need to invoke business logic like `service.placeOrder(...)` inside the factory method.

When writing `@Configuration(proxyBeanMethods=false)`, passing dependencies via **factory method parameters** also prevents direct calls from one `@Bean` method to another from creating objects outside bean identity. That is a wiring rule, independent of whether bootstrapping should run.

### 2.2. Phase B — bean-local initialization

Some beans can only operate after validating properties or preparing **their own** internal state:

```java
final class RulesIndex {
    private boolean ready;

    void initialize() {
        // Build index from configuration already present in the object.
        ready = true;
    }

    boolean isReady() {
        return ready;
    }
}
```

You can declare:

```java
@Bean(initMethod = "initialize")
RulesIndex rulesIndex() {
    return new RulesIndex();
}
```

Spring will invoke `initialize()` per lifecycle when creating and initializing the **managed bean**. This is local preparation, not running a workflow that generates invoices, sends emails, or mutates business data.

`@PostConstruct` and `InitializingBean.afterPropertiesSet()` address the same category of tasks. However, **init callbacks typically execute during singleton creation, under the singleton creation lock**. Spring recommends keeping them concise and focused on validating state/preparing local structures; avoid heavy work, arbitrary calls to other beans, or complex I/O, which risk slowing startup or causing initialization deadlocks.

### 2.3. Phase C — business/application bootstrap

Suppose an application must ensure sample customer data exists before accepting work. That is a **use case**: it needs a repository, a service, deduplication policies, and possibly transactions or external systems.

Avoid writing:

```java
@Bean
CustomerService customerService(CustomerRepository repository) {
    CustomerService service = new CustomerService(repository);
    service.register("seed-001"); // Mixes bean provisioning with a use case.
    return service;
}
```

Instead, use a dedicated coordinator:

```java
// Illustration: a Spring-managed startup bean.
final class SeedCustomers implements SmartInitializingSingleton {
    private final CustomerService customers;

    SeedCustomers(CustomerService customers) {
        this.customers = customers;
    }

    @Override
    public void afterSingletonsInstantiated() {
        customers.register("seed-001");
    }
}
```

`SmartInitializingSingleton` lives in `org.springframework.beans.factory`. Spring invokes `afterSingletonsInstantiated()` after **completing pre-instantiation of regular, non-lazy singletons** in the bean factory. It fits post-singleton-initialization work; do not mistake it for meaning all lazy/prototype beans are initialized or that the entire distributed system is ready.

A complete runnable example is in section 6.

## 3. Why Mixing Business Logic into @Bean Is Problematic

### Factory method turned into a business command

An ideal factory method is primarily responsible for:

```java
@Bean
InvoiceService invoiceService(InvoiceRepository repository,
                              InvoicePolicy policy) {
    return new InvoiceService(repository, policy);
}
```

This snippet does wiring only. If replaced with:

```java
@Bean
InvoiceService invoiceService(InvoiceRepository repository,
                              InvoicePolicy policy) {
    InvoiceService service = new InvoiceService(repository, policy);
    service.generateMonthlyInvoices(); // Business side effect.
    return service;
}
```

the caller never has to invoke `generateMonthlyInvoices()`, yet the work already ran while the context was constructing beans. Common harms:

- **Unpredictable startup:** slow DB/network calls can stall or crash context initialization.
- **Easy duplicate runs:** integration tests, context refreshes, multiple instances/replicas, or a scope recreating beans can run the business logic multiple times.
- **Unintended side effects:** running a test that starts the context may send real emails or modify live data.
- **Unclear transactions:** calling a method inside a factory/constructor does not guarantee it passes through the desired `@Transactional` proxy.
- **Hard to operate:** there is no clean seam for idempotency, retries, metrics, logging, readiness, or rollback.
- **Hard to test:** merely wanting to test wiring forces mocking external services and data.

`InvoiceRepository`, `InvoicePolicy`, and `InvoiceService` in the two snippets above are hypothetical types; this is an **illustrative counter-example**, not a standalone compilable project.

### Constructors are not business entry points either

```java
final class InvoiceService {
    InvoiceService(InvoiceRepository repository) {
        this.repository = repository;
        generateMonthlyInvoices(); // Hard-to-control design.
    }
}
```

Having a constructor execute a business workflow suffers the same problems: causing side effects before the object finishes construction, hard to test, potentially depending on unready beans, and unclear retry/transaction boundaries.

Constructors should record/validate dependencies and establish internal invariants, avoiding external side effects unless opening an internal resource is an intentionally designed part of the object construction contract.

### Do not "fix" it by calling another @Bean method manually

```java
@Configuration(proxyBeanMethods = false)
class BadConfig {
    @Bean
    InvoiceRepository repository() {
        return new JdbcInvoiceRepository();
    }

    @Bean
    InvoiceService invoiceService() {
        InvoiceService service = new InvoiceService(repository());
        service.generateMonthlyInvoices();
        return service;
    }
}
```

There are **two** distinct risks here:

1. `repository()` is called directly in lite mode, potentially creating a repository **outside** the container-managed bean.
2. `generateMonthlyInvoices()` executes during bean creation.

Fix: inject `InvoiceRepository` via a **`@Bean` parameter**, and move the use-case execution to a startup coordinator or an explicitly invoked business command.

## 4. Which Mechanism Fits Which Kind of Work?

| Task | Usually Appropriate Place | Why |
| --- | --- | --- |
| Construct objects, wire dependencies | Constructor, `@Bean` method | Clear factory/wiring responsibility |
| Validate local configuration parameters | Constructor or bean init callback | Catch misconfiguration early |
| Prepare small maps/caches from data already on the bean | `@PostConstruct`/`@Bean(initMethod)` | Bean-local initialization |
| Release bean-owned resources | `@PreDestroy`/`@Bean(destroyMethod)`/`close()` | Bean lifecycle cleanup |
| Work needing all regular non-lazy singletons constructed | `SmartInitializingSingleton` | Callback after singleton pre-instantiation phase |
| Work that must happen once context has refreshed | `ApplicationListener<ContextRefreshedEvent>` or `@EventListener` | Context lifecycle event |
| Component needing phased start/stop and shutdown support | `SmartLifecycle` | Managed lifecycle with start/stop |
| Task run only when triggered by user/job | Service method called from proper entry point | Do not force business tasks to run at startup |
| Boot app needing ordered startup commands integrated with Boot lifecycle | `ApplicationRunner`/`CommandLineRunner` | **Spring Boot**, outside core API |
| Boot needing to know the whole app is ready to serve | `ApplicationReadyEvent` or readiness probes | **Spring Boot**, not a replacement for core callbacks |

This table does not imply **every application must have a bootstrap job**. Many applications only register beans and wait for requests or messages; in such cases, **running no business logic at startup** is the cleanest design.

## 5. Container Lifecycle: Key Milestones

A plain Spring `ApplicationContext` typically passes through these conceptual stages:

```text
Register / read bean definitions
        |
        v
Process bean factory / post-processors
        |
        v
Instantiate regular non-lazy singletons
  + call factory / constructor
  + dependency injection
  + @PostConstruct / initMethod
  + BeanPostProcessor
        |
        v
SmartInitializingSingleton.afterSingletonsInstantiated()
        |
        v
Complete refresh, manage lifecycle
        |
        v
ContextRefreshedEvent
        |
        v
Application executes requested tasks
        |
        v
Context closes: appropriate stop/destroy callbacks
```

This is a **conceptual diagram**, not the full internal sequence of every `ApplicationContext` or framework extension. The refresh event can be emitted again when a context is refreshed anew, and parent-child hierarchies can produce multiple events from different contexts.

### Does @PostConstruct mean "after full application startup"?

**No.** `@PostConstruct` runs within the initialization lifecycle of **one specific bean**. It does not guarantee all other beans have been created; some may be lazy, prototype, or depend on other configs/conditions.

Example:

```java
// Illustrative snippet; requires Jakarta Annotations on the classpath.
@PostConstruct
void init() {
    validateLocalSettings();
}
```

Tasks involving heavy external calls, long execution, transactions, or system-wide coordination rarely belong here. Spring also warns that init callbacks running under the singleton creation lock can risk deadlocks if performing heavy work or out-of-band bean lookups.

### Does SmartInitializingSingleton mean "the application is ready to serve"?

**Not completely.** It signals that the BeanFactory has finished **pre-instantiating regular non-lazy singletons**, yet some refresh/lifecycle completion steps may occur afterward. If work genuinely depends on context refresh completion, choose `ContextRefreshedEvent`; if it depends on web server readiness in Spring Boot, consider Boot's corresponding mechanisms.

### ContextRefreshedEvent can repeat

`ContextRefreshedEvent` is published when an `ApplicationContext` is initialized or refreshed. It is not a contract saying "run business logic strictly once in the company's lifetime". In parent-child context hierarchies, a listener may observe events from different contexts; when refreshed again, the event can fire again.

**Assuming one callback == business-level exactly-once is wrong.** If a task creates data or affects external systems, proper idempotency/coordination is required.

## 6. Runnable Example: Pure Factory, Local Init, and Separate Business Bootstrap

The example uses plain **Java 17 + Spring Framework 6.2** with `AnnotationConfigApplicationContext`. There is no Spring Boot, database, or external network.

We build:

- `CustomerRepository`: stores customer IDs in memory; allows inserting if absent.
- `Rules`: a bean with a small initialization callback to mark readiness, and a destroy callback when the context closes.
- `CustomerService`: holds customer registration business logic and runs nothing on its own when constructed.
- `SeedCustomers`: a coordinator implementing `SmartInitializingSingleton`, performing a seed step after regular singletons are initialized.
- `AppConfig`: `@Bean` methods **only create/wire beans**, never calling `customers.register(...)` inside factory methods.

### 6.1. Directory layout

```text
spring-init-separation/
├── pom.xml
└── src/main/java/demo/InitSeparationDemo.java
```

### 6.2. File pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>spring-init-separation</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.18</version>
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

### 6.3. File src/main/java/demo/InitSeparationDemo.java

```java
package demo;

import java.util.HashSet;
import java.util.Set;

import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class InitSeparationDemo {

    interface CustomerRepository {
        boolean saveIfAbsent(String id);
        boolean contains(String id);
    }

    static final class MemoryCustomerRepository implements CustomerRepository {
        private final Set<String> ids = new HashSet<>();

        @Override
        public boolean saveIfAbsent(String id) {
            return ids.add(id);
        }

        @Override
        public boolean contains(String id) {
            return ids.contains(id);
        }
    }

    static final class Rules {
        private boolean ready;

        void initialize() {
            ready = true;
            System.out.println("rules.initialize");
        }

        boolean isReady() {
            return ready;
        }

        void close() {
            System.out.println("rules.close");
        }
    }

    static final class CustomerService {
        private final CustomerRepository repository;
        private final Rules rules;

        CustomerService(CustomerRepository repository, Rules rules) {
            this.repository = repository;
            this.rules = rules;
        }

        String register(String id) {
            if (!rules.isReady()) {
                throw new IllegalStateException("Rules not initialized");
            }
            return repository.saveIfAbsent(id)
                    ? "created:" + id
                    : "existing:" + id;
        }

        boolean exists(String id) {
            return repository.contains(id);
        }
    }

    static final class SeedCustomers implements SmartInitializingSingleton {
        private final CustomerService customers;

        SeedCustomers(CustomerService customers) {
            this.customers = customers;
        }

        @Override
        public void afterSingletonsInstantiated() {
            // Business bootstrap work has its own entry point.
            System.out.println("bootstrap=" +
                    customers.register("seed-001"));
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class AppConfig {

        @Bean
        CustomerRepository customerRepository() {
            return new MemoryCustomerRepository();
        }

        @Bean(initMethod = "initialize", destroyMethod = "close")
        Rules rules() {
            return new Rules();
        }

        @Bean
        CustomerService customerService(
                CustomerRepository repository, Rules rules) {
            return new CustomerService(repository, rules);
        }

        @Bean
        SeedCustomers seedCustomers(CustomerService customers) {
            return new SeedCustomers(customers);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            CustomerService customers =
                    context.getBean(CustomerService.class);

            System.out.println("main.seedFound=" +
                    customers.exists("seed-001"));
            System.out.println("main.new=" +
                    customers.register("c-100"));
            System.out.println("main.repeat=" +
                    customers.register("seed-001"));
        }
    }
}
```

### 6.4. How to run

In the directory containing `pom.xml`, with JDK 17+ and Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.InitSeparationDemo
```

Lines **printed by the program** (excluding log messages Maven/Spring may emit depending on environment):

```text
rules.initialize
bootstrap=created:seed-001
main.seedFound=true
main.new=created:c-100
main.repeat=existing:seed-001
rules.close
```

### 6.5. Interpreting the output and each component's responsibility

1. Spring loads `AppConfig` and four `@Bean` definitions. The factory methods only return instances or pass dependencies. No method calls `CustomerService.register` to perform business bootstrapping.
2. When the container creates the managed `Rules` bean, it calls `Rules.initialize()` because of `@Bean(initMethod = "initialize")`. `rules.initialize` appears during the bean-local initialization phase. The whole application does not need to finish refreshing to set this flag.
3. After completing initialization of regular non-lazy singletons, Spring invokes `SeedCustomers.afterSingletonsInstantiated()`. The coordinator calls the `CustomerService.register("seed-001")` use case and prints `bootstrap=created:seed-001`.
4. Once `AnnotationConfigApplicationContext(AppConfig.class)` returns, `main` retrieves `CustomerService`. Seeding has already run, so `main.seedFound=true`.
5. Registering new ID `c-100` returns `created:c-100`; repeating the seed ID returns `existing:seed-001` because the repository uses `Set.add(...)` to deduplicate **in memory within the same context**.
6. Upon exiting `try-with-resources`, Spring closes the context and invokes `Rules.close()` on the `Rules` singleton, outputting `rules.close`.

**Note on idempotency:** `Set.add` in the example is a single-threaded in-memory demo. It does not replace database uniqueness/transactions, distributed locks, or idempotency keys in multi-process/multi-replica environments. In production, seeding needs deduplication at the data/system level, not merely a static variable or instance boolean.

### 6.6. Benefits of separating as in the example

- `AppConfig` is easy to read: only "create repository", "create rules", "create service", "create bootstrap coordinator".
- `Rules.initialize()` describes local readiness of a bean and invokes no use case.
- `CustomerService.register` holds business logic and can be unit-tested independently with fake repository/rules.
- `SeedCustomers` provides a clear entry point for **triggering** a startup task; the trigger policy can be changed without modifying constructors or factories.
- Runtime consumers do not need to know which startup callback created the seed data.
- To omit seeding completely in an environment, simply **do not register** `SeedCustomers` in that environment's configuration (e.g., splitting `@Configuration` or using `@Profile`), rather than putting `if` checks inside the service constructor.

## 7. @PostConstruct, @Bean(initMethod), and InitializingBean: Using the Right Scope

Spring supports several ways to declare **bean initialization** callbacks:

### 7.1. @PostConstruct

```java
import jakarta.annotation.PostConstruct;

final class TokenFormat {
    private String prefix;

    @PostConstruct
    void validate() {
        if (prefix == null || prefix.isBlank()) {
            throw new IllegalStateException("Missing token prefix");
        }
    }
}
```

This is an **illustrative snippet**; `prefix` must be configured/supplied on the object in real code. `@PostConstruct` from `jakarta.annotation` requires Jakarta Annotations on the classpath and the corresponding Spring post-processor. In Spring Framework 6.x, use the Jakarta namespace rather than legacy `javax.annotation.PostConstruct`.

Appropriate for: checking/asserting invariants or preparing internal state. Inappropriate for: large data scans, multi-system API calls, or long-running business loops inside an init callback.

### 7.2. @Bean(initMethod = "...")

```java
@Bean(initMethod = "initialize")
TokenParser tokenParser() {
    return new TokenParser();
}
```

This is an illustrative snippet requiring `TokenParser.initialize()` to actually exist. Well suited when configuring library objects you do not want to modify to add `@PostConstruct`. The init method is called by Spring after bean creation/population per lifecycle, so there is no need to call `tokenParser.initialize()` directly inside the factory method.

With `@Bean`, you can set `destroyMethod` for resource cleanup; if the object exposes an eligible `close` or `shutdown` method, Spring also infers a destroy method. Understand clearly whether the bean genuinely **owns** that resource before letting the container close it automatically.

### 7.3. InitializingBean.afterPropertiesSet()

```java
final class LocalIndex implements org.springframework.beans.factory.InitializingBean {
    @Override
    public void afterPropertiesSet() {
        // Only validate and prepare the bean's own state.
    }
}
```

This couples directly to a Spring API. It remains a **bean-local lifecycle callback**, and does not automatically become an application-level startup hook.

### 7.4. Do not call init callbacks manually and also declare them to Spring

If you write:

```java
@Bean(initMethod = "initialize")
Rules rules() {
    Rules rules = new Rules();
    rules.initialize();
    return rules;
}
```

then `initialize()` can run **twice**: once from the factory body itself and once from BeanFactory's lifecycle callback. If init is not idempotent, this can fail or open resources twice.

Choose **one mechanism to own initialization**, rather than calling it manually and asking Spring to call it again. If the constructor already guarantees a valid object and no init callback is needed, do not add a callback just to "have lifecycle annotations".

### 7.5. Can @PostConstruct call a @Transactional method?

Do not assume an init callback is a valid entry point for transaction AOP. The bean may not yet have passed through the required proxies/post-processors, and self-invocation to a method on the same instance typically bypasses the proxy in proxy-based AOP.

When bootstrapping needs a transaction, have a **managed coordinator** call **another service** through its proper proxy after application infrastructure is ready, with `@Transactional` properly enabled and configured. Also define clearly when transactions open, roll back, and retry; never treat the presence of the annotation as proof that a transaction is active.

## 8. SmartInitializingSingleton: After Singleton Creation, Before Assuming System Readiness

`SmartInitializingSingleton` is a Spring Core interface with the method:

```java
void afterSingletonsInstantiated();
```

It is invoked at the end of `BeanFactory`'s singleton pre-instantiation phase. Advantages over `@PostConstruct`:

- The coordinator bean already has its dependencies injected.
- Regular, non-lazy singletons have completed initialization, reducing the risk of touching another bean mid-initialization.
- The callback is triggered by the BeanFactory mechanism without putting business calls inside `@Bean` factory methods.
- Fits post-initialization setup needing multiple singletons without requiring the context refresh event to complete.

Important limitations:

- No guarantee that every **lazy singleton**, prototype, or external resource is ready.
- Runs synchronously on the normal initialization/refresh path; heavy work can delay startup.
- Provides no built-in retry, timeout, transaction, or distributed coordination.
- Multiple callbacks should not rely on accidental ordering if there are business order dependencies between them; coordinate explicitly.
- The callback is not an exactly-once event across replicas.
- If the coordinator bean itself is marked `@Lazy` and not instantiated during pre-instantiation, do not assume the callback ran.

### When ordering across multiple tasks is required

Suppose the application must **validate the schema**, then **load reference data**, and only then **enable a traffic-serving adapter**. Do not create three `SmartInitializingSingleton` beans and assume Spring will run them in a specific business order based on `@Bean` method order.

Instead, have a single **coordinator** own the sequence of steps:

```java
// Illustrative snippet; each action is an application interface/bean.
final class StartupCoordinator implements SmartInitializingSingleton {
    private final ValidateSchema validateSchema;
    private final SeedReferenceData seedReferenceData;

    StartupCoordinator(ValidateSchema validateSchema,
                       SeedReferenceData seedReferenceData) {
        this.validateSchema = validateSchema;
        this.seedReferenceData = seedReferenceData;
    }

    @Override
    public void afterSingletonsInstantiated() {
        validateSchema.run();
        seedReferenceData.run();
    }
}
```

This is not a standalone file. `ValidateSchema` and `SeedReferenceData` must be defined in the application; the coordinator makes the sequence explicit and provides a single place to manage idempotency/logging/failure policy.

## 9. ContextRefreshedEvent: When a Refreshed Context Is Needed

Spring publishes `ContextRefreshedEvent` once an `ApplicationContext` has been initialized or refreshed. You can listen via:

```java
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;

@Component
final class StartupListener {
    private final ReferenceDataService referenceData;

    StartupListener(ReferenceDataService referenceData) {
        this.referenceData = referenceData;
    }

    @EventListener(ContextRefreshedEvent.class)
    void onRefresh() {
        referenceData.ensureSeeded();
    }
}
```

This is an **illustrative snippet** requiring importing `@Component`, defining `ReferenceDataService`, and ensuring the scanner finds the listener. The method is invoked by Spring when the matching event is dispatched; do not treat event listeners as the sole mechanism for every startup task.

Points for caution:

- A context can **refresh multiple times** if the context type/operational flow supports it, so the listener can run again.
- With **parent-child contexts**, a listener can observe events from different contexts depending on hierarchy; filter `event.getApplicationContext()` when needed.
- The event multicaster normally dispatches synchronously by default, yet can be configured asynchronously; do not treat event handling as a readiness barrier if dispatching was changed.
- If the callback fails, the effect on startup depends on dispatch mode, exception handling, and context lifecycle; test failure paths directly.
- `ContextRefreshedEvent` describes the **Spring context**, and does not automatically guarantee external databases, brokers, and remote services are ready.

### @EventListener and ApplicationListener

Both styles express the same event-listening intent; you do not need to write both:

```java
// Interface-based illustration:
final class Listener implements
        org.springframework.context.ApplicationListener<ContextRefreshedEvent> {

    @Override
    public void onApplicationEvent(ContextRefreshedEvent event) {
        // Handle one emission of the context refresh event.
    }
}
```

This class must also be registered as a bean/listener in the context. Use `@EventListener` for method-based listeners; use the interface when fitting an infrastructure contract. Either way, idempotency policy belongs to the business logic.

## 10. SmartLifecycle: When Bootstrap Is a Component with Start/Stop

A background component such as a polling consumer, listener adapter, or scheduler has a **start — run — stop** lifecycle. Building the object and initializing the bean are only part of it; background execution should be controlled via lifecycle.

Spring's `SmartLifecycle` supports:

- `start()`: begin operation.
- `stop()` or `stop(Runnable callback)`: stop synchronously or asynchronously as appropriate.
- `isRunning()`: report state.
- `getPhase()`: define phase ordering among lifecycle components.
- `isAutoStartup()`: decide whether to start automatically on context refresh.

Conceptual diagram:

```text
@Bean factory: new MessageConsumer(...)
            |
            v
Bean is managed by Spring
            |
            v
Lifecycle processor calls start()
            |
            v
Consumer listens for messages by phase
            |
            v
Context stop/close -> stop(callback)
            |
            v
Destroy callbacks and resources cleaned up
```

Do not spawn long-lived threads or run infinite loops inside constructors, `@Bean` factories, or `@PostConstruct`. Doing so can block context initialization, make runtime shutdown ordering hard to control, or leak resources.

A `SmartLifecycle` implementation must handle concurrency, shutdown timeouts, and completion callbacks per contract; use it only when you genuinely have **a component with an active operational lifecycle**, not for a simple one-off data seed.

## 11. Distinguishing Spring Framework Core and Spring Boot

In a **plain Spring Framework** application, you typically choose:

- `SmartInitializingSingleton` when needing action after singleton pre-instantiation.
- `ContextRefreshedEvent` when needing a post-refresh hook.
- `SmartLifecycle` when a component starts/stops in phases.
- Application entry points calling services directly when work does not belong to startup.

In **Spring Boot**, in addition to Spring Framework's options, there are:

- `ApplicationRunner` and `CommandLineRunner`: hooks executed once the Boot application has started per Boot's runner lifecycle; can use `@Order`/`Ordered` per Boot policy.
- `ApplicationReadyEvent`: signal that Boot has finished startup and is ready to serve requests, emitted after runners in the standard lifecycle.
- Readiness/liveness probes and other Boot operational features.

Keep the boundary clear: **`ApplicationReadyEvent` is not part of the Spring Core Container**, and even though it signals readiness at the Boot application level, it does not promise external systems or a distributed cluster are ready. Do not copy `CommandLineRunner` into an example declaring only `spring-context` and expect it to compile.

### When should you NOT bootstrap automatically?

If a task can run on a schedule, be triggered by an admin, wait for approval, or require distributed quotas/locks, do not force it to run every time an application instance starts. Let the appropriate entry point call a service with its own state/signals. Separating factories from business logic lets you change the **trigger** without rewriting object wiring.

## 12. Idempotency and Transactions in Business Bootstrapping

A business bootstrap task can run more than once:

- Application restarts after failure.
- Multiple replicas start concurrently.
- Integration tests create multiple Spring contexts.
- A context refreshes or a listener receives multiple events.
- Retries from orchestration/deployment tooling.
- Manual seed commands run alongside bootstrapping.

Hence **once per JVM** is usually insufficient. For important data, enforce verifiable invariants in the data store.

### Create if absent, not unconditionally

Instead of:

```java
// Counter-example:
void seedRoles() {
    roleRepository.insert("ADMIN"); // Re-running can fail/duplicate.
}
```

design an idempotent operation:

```java
// Application-level illustrative snippet:
void ensureDefaultRole() {
    roleRepository.insertIfAbsent("ADMIN");
}
```

`insertIfAbsent` is a hypothetical application API. In a real database, use unique constraints/UPSERT or proper transactions to prevent race conditions across multiple instances. A separate "query then insert" sequence is not concurrency-safe without data constraints.

### Transactions must sit at the right boundary

When a transaction is required, the coordinator can call another Spring-managed service:

```java
// Illustrative snippet: transaction method belongs to a properly proxied bean.
final class SeedCoordinator {
    private final RoleBootstrapService roleService;

    SeedCoordinator(RoleBootstrapService roleService) {
        this.roleService = roleService;
    }

    void execute() {
        roleService.ensureDefaultRoles();
    }
}
```

`RoleBootstrapService` can define a transaction boundary with `@Transactional` once transaction infrastructure is enabled. Do not assume calling a `@Transactional` method from the constructor or `@PostConstruct` of **that same bean** goes through a transaction proxy. Likewise, do not call another transactional method on the same class expecting proxy-based advice to apply automatically.

### Failure policy for bootstrap

Define clearly:

| Task Type | What to do on failure? |
| --- | --- |
| Required for safe operation | Fail startup or withhold readiness; report root cause clearly |
| Reloadable reference data | Controlled retry without duplicates, with metrics |
| Auxiliary such as cache warm-up | Allow degraded mode if business accepts it; log and monitor |
| Manually triggered business command | Return result/error to caller; do not hide inside lifecycle hook |
| Unavailable external resource | Use timeouts, circuit breakers/retries, or readiness constraints per requirements |

Never catch `Exception` and silently skip a mandatory seed step so the container still reports healthy. Conversely, an optional cache warm-up might not justify failing startup for the entire app—yet that must be an **explicit business decision**, not an accidental side effect of `@Bean`.

## 13. Observability, Testability, and Side-Effect Budget

Separating responsibilities allows testing across three layers.

### Testing construction separately

Test `CustomerService` with a fake repository:

```java
// Illustrative snippet in a unit test; requires fake repository and valid Rules.
CustomerService service = new CustomerService(fakeRepository, preparedRules);
String result = service.register("customer-1");
```

No Spring context is needed just to test business methods; that is a benefit of explicit constructor injection.

### Testing bean initialization separately

A small Spring test verifies `Rules.initialize()` runs when the bean is created via BeanFactory and `isReady()` is `true`. Never call `new AppConfig().rules()` yourself and assume you tested Spring-managed init callbacks.

### Testing bootstrap separately

Construct `SeedCustomers` with a fake `CustomerService` or use an integration `ApplicationContext` and verify seed data was created before the context constructor returns. In the full example, you can add this assertion inside `main`:

```java
CustomerService customers =
        context.getBean(CustomerService.class);

if (!customers.exists("seed-001")) {
    throw new AssertionError("Startup seed was not created");
}
```

This addition prints no extra stdout when valid. It tests the actual effect of the coordinator, not merely that a callback was declared in source.

### Integration tests verifying contexts do not trigger unintended business work

If a test only needs repository/service beans to test wiring, ideally use a test configuration that **does not register the bootstrap coordinator**, or swap external gateways with fakes. When factories are pure construction, opening an `ApplicationContext` does not execute unrelated use cases unless startup components are intentionally registered.

### Observability for startup jobs

In real systems, record:

- Step name and start/end timestamps.
- Success/failure and root cause.
- Counts of records created/updated/skipped.
- Idempotency/retry/lock status.
- Total duration and timeouts.
- Relevant schema/data migration version.
- Readiness or degraded mode if applicable.

Never log secrets/tokens or sensitive payload data just to see that bootstrap ran. Metrics/logs also do not replace correctness of unique constraints and transactions.

## 14. Key Anti-Patterns

### Anti-pattern A: sending emails right inside a factory

```java
@Bean
EmailService emailService(EmailGateway gateway) {
    EmailService service = new EmailService(gateway);
    service.sendWelcomeEmails(); // Side effect repeats whenever context builds.
    return service;
}
```

**Fix:** the factory only creates `EmailService`; a properly triggered job/command invokes `sendWelcomeEmails()` with its own idempotency and observability. If sending emails should be user-triggered, never run it at startup at all.

### Anti-pattern B: loading large datasets in @PostConstruct

```java
@PostConstruct
void init() {
    externalApi.downloadEverythingAndWriteDatabase();
}
```

**Fix:** bean-local init only validates/precomputes small local state. Move heavy tasks to a post-singleton-creation coordinator or an asynchronous job with its own policy; if readiness gating is needed, design it explicitly.

### Anti-pattern C: spawning threads in a constructor

```java
public PollingConsumer() {
    new Thread(this::pollForever).start();
}
```

**Fix:** the constructor only stores config/dependencies; use `SmartLifecycle` or an appropriate scheduler/managed executor to start/stop, handling shutdown and exceptions per contract.

### Anti-pattern D: using @DependsOn to orchestrate all business work

```java
@Bean
@DependsOn("seedData")
ReportService reportService() {
    return new ReportService();
}
```

`@DependsOn` expresses **bean initialization/destruction ordering constraints**, not turning `seedData` into a business orchestration engine with retries, transactions, and idempotency. If business steps A -> B -> C are needed, express them explicitly in a coordinator and test them.

### Anti-pattern E: running tasks in a @Configuration constructor

```java
@Configuration
class StartupConfig {
    StartupConfig(ReportingService reporting) {
        reporting.generateMonthlyReport();
    }
}
```

**Fix:** config classes handle wiring, not workflows; avoid forcing the container to run external tasks while the config class itself is still initializing. Especially dangerous if the constructor needs beans supplied by this very configuration class's factory definitions, risking circular dependencies.

### Anti-pattern F: treating @Bean(initMethod) as "application ready"

```java
@Bean(initMethod = "startAllJobs")
JobCoordinator jobCoordinator() {
    return new JobCoordinator();
}
```

An init callback is **bean lifecycle**, not a guarantee that all application-level dependencies/external services are ready. If `startAllJobs` needs many beans, DB, transactions, or business data, reconsider the trigger and lifecycle orchestration.

## 15. Symptom-Based Troubleshooting

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Every test context startup sends emails or mutates data | Business logic lives in constructor, `@Bean`, or init callback | Separate use case from wiring; register startup coordinator intentionally |
| Context hangs/fails to start when DB is slow | Factory/init callback performs external I/O too early | Move task to proper lifecycle; add timeouts/retries/readiness |
| `@PostConstruct` calls another bean before it is ready | Init callback runs during bean creation, not after all singletons | Prepare internal state in init; move orchestration to later callback |
| Deadlock or refresh hangs | Init callback holds singleton creation lock and does out-of-band lookups/calls | Minimize init work; use `SmartInitializingSingleton`/refresh events appropriately |
| `@Transactional` method runs without a transaction | Self-invocation or called during init before proxies are ready | Call through proper service/proxy at a later boundary |
| Duplicate seed data after scale-out | Relying solely on an in-JVM/context boolean flag | Use unique constraints/UPSERT and multi-instance idempotency |
| Resource opened twice | Called init in factory AND declared `initMethod`; or direct `@Bean` call in lite config | Pick one callback; inject managed bean via parameter |
| Task runs multiple times after refresh | Listener receives multiple `ContextRefreshedEvent`s | Filter target context and design idempotency |
| Startup callback didn't run on lazy bean | Lazy bean callback skipped during non-lazy singleton pre-instantiation | Register coordinator as non-lazy if startup hook is genuinely needed |
| Assuming SmartInitializingSingleton means all external services are ready | Callback only signals a BeanFactory phase | Use explicit health/readiness/dependency checks |
| Unit tests forced to spin up a database | Constructor/factory executes business logic itself | Constructor injection, fake dependencies, separate bootstrap |
| Thread/pool leak on shutdown | Resources or threads opened without lifecycle management | `destroyMethod`, `SmartLifecycle`, managed executors |
| No logs explaining bootstrap failure | Exception caught and swallowed in init | Handle exceptions/metrics/logging per operational policy |

### Step-by-step debugging process

1. Locate whether the side-effecting code sits in a **constructor**, **`@Bean`**, **init callback**, or **startup coordinator**.
2. Check if the `@Configuration` class uses lite mode; if calling a `@Bean` method directly, the object may live outside BeanFactory.
3. Verify required dependencies are injected via constructor/factory parameters.
4. Identify whether the callback runs before/after singleton pre-instantiation, context refresh, or Boot readiness.
5. Determine how many times each startup/context refresh/replica can trigger the task.
6. Check whether the task is idempotent and has the right transaction boundary.
7. Read the root cause exception and check resource/connection/shutdown policies.
8. Write integration tests reproducing both an initial startup and a repeated startup.

## 16. Practice Exercises and Answers

### Exercise 1 — Classifying work

Inside a `@Bean DataClient dataClient()`, there are steps: (a) build a builder with a URL; (b) validate URL is non-blank; (c) insert 1,000 invoices into the DB; (d) pass a dependency to another service. Which belong to wiring/local setup?

**Answer:** (a), (b), and (d) can belong to construction/configuration when performing no business I/O. (c) is a workflow with side effects needing its own entry point and policy; it should not run inside a factory.

### Exercise 2 — Does @PostConstruct run after all beans?

A `@PostConstruct` on `CustomerService` invokes every handler in the system. Is it guaranteed that all singleton/lazy beans are already initialized?

**Answer:** No. Init callbacks belong to the current bean's lifecycle, not a barrier after the whole container; they can also run under the singleton creation lock. Coordinate post-initialization through the proper mechanism and avoid heavy work here.

### Exercise 3 — Does SmartInitializingSingleton replace @Bean?

If `SeedCustomers` implements `SmartInitializingSingleton`, must it still be registered as a bean?

**Answer:** Yes. Spring can only invoke callbacks on beans managed by BeanFactory. In the complete example, `@Bean SeedCustomers seedCustomers(CustomerService customers)` registers the coordinator.

### Exercise 4 — Predicting stdout

In `InitSeparationDemo` from section 6, why does `rules.initialize` run before `bootstrap=created:seed-001`?

**Answer:** `Rules` is a dependency of `CustomerService`; Spring completes the managed `Rules` init callback during singleton creation. After non-lazy singletons are pre-instantiated, it calls `SeedCustomers.afterSingletonsInstantiated()`, at which point the use case runs.

### Exercise 5 — Running multiple instances

Two replicas both seed the `ADMIN` role via "insert if not exists" without a unique constraint. Is it safe?

**Answer:** No. Both replicas can read "not exists" simultaneously and both insert. Unique constraints/UPSERT/transactions or appropriate distributed coordination are needed per requirements.

### Exercise 6 — Does @DependsOn replace a coordinator?

You need to load catalog A, then build index B, then start listener C. Is placing `@DependsOn` on the three beans enough to express retry/idempotency/readiness?

**Answer:** No. `@DependsOn` specifies bean lifecycle ordering dependencies, not business orchestration policies. Use an appropriate coordinator/startup lifecycle and test both ordering and failure scenarios.

### Exercise 7 — When to use SmartLifecycle?

A message consumer must start in the right phase and stop before the pool is released. Should you put a `while(true)` loop in `@PostConstruct` or use `SmartLifecycle`?

**Answer:** `SmartLifecycle` or an appropriate managed listener/scheduler abstraction expresses start/stop and phases; never start an infinite loop inside an init callback.

### Exercise 8 — Can ContextRefreshedEvent run twice?

A data-seeding listener relies on `ContextRefreshedEvent`; the app has parent-child contexts. Should you assume the listener sees only one event and skip idempotency?

**Answer:** No. Events can fire per context and on refresh; the listener should filter by context if required, while the seeding use case itself must be safe under repeated execution.

### Exercise 9 — Where do transactions belong?

A bean calls its own `@Transactional` method from its constructor. Why should that pattern be avoided?

**Answer:** Constructors run before the object/proxy is complete; self-invocation in proxy-based Spring AOP normally bypasses the proxy. Use a managed service/proxy as the transaction boundary and invoke it from a coordinator in the appropriate phase.

### Exercise 10 — Redesigning @Bean

Refactor the following snippet:

```java
@Bean
InventoryService inventoryService(InventoryRepository repository) {
    InventoryService service = new InventoryService(repository);
    service.importCatalog();
    return service;
}
```

**Guided answer:**

```java
@Bean
InventoryService inventoryService(InventoryRepository repository) {
    return new InventoryService(repository);
}

@Bean
CatalogBootstrap catalogBootstrap(InventoryService inventoryService) {
    return new CatalogBootstrap(inventoryService);
}
```

`CatalogBootstrap` is an application coordinator class: it can implement `SmartInitializingSingleton` or receive triggers from an appropriate entry point depending on business timing. This is a structural example requiring definitions of `InventoryRepository`, `InventoryService`, and `CatalogBootstrap`. The key point is that the factory **does not call `importCatalog()`**.

## 17. Project Adoption Checklist

- [ ] Every `@Bean` factory method primarily **creates/wires instances**, never executing business workflows.
- [ ] Service constructors do not send emails, migrate data, or call external APIs unnecessarily.
- [ ] Bean-local validation/preparation sits in constructors or small lifecycle callbacks with clear contracts.
- [ ] Multi-bean tasks or heavy I/O are not forced into `@PostConstruct`.
- [ ] For startup hooks, pick `SmartInitializingSingleton`, `ContextRefreshedEvent`, `SmartLifecycle`, or Boot runners according to actual needs.
- [ ] If no automatic startup task is needed, **do not register** an unnecessary business-running callback.
- [ ] Ordering across business steps is coordinated **explicitly**, not left to accidental bean definition order.
- [ ] Startup tasks have idempotency, transaction, retry/timeout, and failure/readiness policies matching business requirements.
- [ ] Multiple replicas or context refreshes are accounted for in case tasks run repeatedly.
- [ ] `@Bean` dependencies use method parameters rather than direct bean-method calls in lite mode.
- [ ] Unit tests can invoke business services without spinning up a Spring context when infrastructure is not involved.
- [ ] Integration tests verify lifecycle/seeding/identity and catch unintended side effects.
- [ ] Resources or background tasks have matching cleanup/stop callbacks.
- [ ] Logging/metrics give sufficient observability without leaking sensitive data.

## Final Takeaways

**Bean creation, bean initialization, and business bootstrapping are three separate responsibilities.** Spring provides multiple lifecycle extension points because these phases are not equivalent:

- `@Bean` and constructors: **construct objects + wire dependencies**.
- `@PostConstruct` or `@Bean(initMethod)`: **validate/prepare bean-local state**.
- `SmartInitializingSingleton` or `ContextRefreshedEvent`: **post-initialization coordination when the application genuinely needs it**.
- `SmartLifecycle`: **start/stop of lifecycle-managed components**.
- Use-case/service methods: **actual business logic**, invoked from deliberate triggers.

Do not try to "do everything" inside `@Configuration`. Good Java configuration tells readers **which beans exist and how they wire together**, while a good bootstrap coordinator tells readers **which business tasks run, when, and under what failure and retry policies**.

## Official References

- [Spring Framework 6.2 — Customizing the Nature of a Bean](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html): lifecycle callbacks, singleton creation lock caveats, `SmartInitializingSingleton`/context refresh events, and `SmartLifecycle`.
- [Spring Framework 6.2 — Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/bean-annotation.html): factory method parameters and `initMethod`/`destroyMethod`.
- [Spring Framework 6.2 — SmartInitializingSingleton Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/beans/factory/SmartInitializingSingleton.html): semantics of the callback after singleton pre-instantiation.
- [Spring Framework 6.2 — ContextRefreshedEvent Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/context/event/ContextRefreshedEvent.html): event when ApplicationContext is initialized/refreshed.
- [Spring Framework 6.2 — SmartLifecycle Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/context/SmartLifecycle.html): start/stop, auto-startup, and lifecycle phases.
- [Spring Framework 6.2 — Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java.html): factory configuration boundaries.
