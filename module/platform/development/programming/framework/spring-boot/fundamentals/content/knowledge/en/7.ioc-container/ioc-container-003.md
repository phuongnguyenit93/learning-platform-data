# How Is a Bean Managed by the Container?

In Java, you can create an object yourself with `new` and then invoke its methods. In Spring Boot, a more common approach is declaring the required components and letting the **Spring IoC container** create, assemble, configure, and manage their lifecycles. An object managed by the container in this way is called a **Spring bean**.

The statement "a bean is an object managed by Spring" is only meaningful when you understand **what Spring is managing**: registering bean definitions, deciding when to create objects, choosing which dependencies to pass in, controlling instance lifespan, applying additional processing such as proxies, and invoking lifecycle callbacks. These responsibilities have direct consequences on how you write services, controllers, and configurations in a Spring Boot application.

## 1. A Bean Is Still a Java Object

Consider a plain Java class:

```java
public class GreetingService {
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

You can certainly instantiate it yourself:

```java
GreetingService service = new GreetingService();
System.out.println(service.greet("Alice"));
```

This is an **ordinary Java object**. To use it, the calling code must know how to instantiate it and decide who holds a reference to it. The statement `new GreetingService()` by itself does not register the object with Spring.

If you register the class as a bean:

```java
import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

and the class lies within the component scanning scope, Spring can discover this definition, create an instance, and supply that instance to other beans that require `GreetingService`.

**The distinction does not lie in the class's syntax.** The very same `GreetingService` class can have one instance you created manually with `new` and one instance managed by Spring. An object created with `new` **does not automatically become a bean** merely because the class has the `@Service` annotation.

| Question | Object Created Manually with `new` | Spring Bean |
|---|---|---|
| Who decides instantiation? | Java code calling the constructor. | The Spring container based on bean definition and scope; inside a factory method `new` may still be used. |
| Who supplies dependencies? | The calling code supplies them itself. | The container resolves and injects dependencies as configured. |
| Who decides to retain/reuse the instance? | The programmer. | The container and the bean's scope. |
| Who invokes Spring lifecycle callbacks? | Not automatic; the programmer handles it if desired. | The container applies lifecycle mechanisms to managed instances. |
| Can Spring AOP/proxies be applied automatically? | Not automatically via `new` alone. | Yes, when the bean meets conditions and proxy configuration applies. |

Spring does not "change the nature" of a Java object. A bean still has fields, methods, constructors, and obeys Java rules. The difference is that **the container holds control over coordinating how the object is used**.

## 2. IoC Is Inverting Control Over Object Wiring

**IoC** (*Inversion of Control*) describes shifting where decisions are made about how an object is created and connected to other objects.

If wiring objects manually:

```java
public class OrderService {
    private final EmailNotifier notifier;

    public OrderService() {
        this.notifier = new EmailNotifier();
    }

    public void placeOrder() {
        // Execute order creation logic...
        notifier.send("Order has been created");
    }
}
```

`OrderService` directly decides both the `EmailNotifier` implementation and how to create it. This makes the class difficult to replace the notifier with during tests or when switching to another notification channel.

Using dependency injection:

```java
public interface Notifier {
    void send(String message);
}

public class OrderService {
    private final Notifier notifier;

    public OrderService(Notifier notifier) {
        this.notifier = notifier;
    }

    public void placeOrder() {
        // Execute order creation logic...
        notifier.send("Order has been created");
    }
}
```

`OrderService` simply states that it **needs a `Notifier`**, while the outside decides which implementation to provide. This is **Dependency Injection (DI)**, a common technique for implementing IoC.

The Spring IoC container plays that "outside" role: it looks at bean definitions, selects matching dependencies, and invokes constructors or factory methods to wire them together. Spring also manages lifecycles, scopes, metadata, and other extensions, so **the IoC container encompasses more than automatically passing constructor arguments**.

A visualization of the orchestration direction:

```text
Without a container:

main() ── new EmailNotifier() ──> new OrderService(notifier)
   │                                     │
   └────────────── holds reference ──────┘

With the Spring container:

Configuration/component scan ──> Bean definitions
                                        │
                                        ▼
                                 Spring container
                                  /           \
                       Notifier bean       OrderService bean
                                  \           /
                                inject dependency
```

## 3. What Is the Container: BeanFactory and ApplicationContext

Spring Framework defines two foundational concepts:

- **`BeanFactory`**: the core interface for accessing and managing beans.
- **`ApplicationContext`**: extends `BeanFactory` with application-level capabilities such as event publication, resource handling, environment integration, and other utilities.

In Spring Boot, developers typically work with **`ApplicationContext`**. When calling `SpringApplication.run(...)`, Boot creates or selects the appropriate application context type, prepares the environment, loads bean definitions, refreshes the context, and initializes required components.

Example entry point:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Managed objects do not merely sit in a simple "list of Java objects." The container also holds **metadata to know which objects to create, who depends on whom, what scope applies, and which processing steps must be executed**.

This can be summarized briefly:

```text
ApplicationContext
├── Bean definitions (describing how to create and manage beans)
├── Dependency resolution (selecting and injecting dependencies)
├── Scope/lifecycle (creation, retention, termination)
├── BeanPostProcessor and extension points
├── Environment, resources, events...
└── Instances/proxies created according to scope
```

Not every bean definition necessarily corresponds to a currently existing instance. A default singleton bean may be created when the context starts; a `@Lazy` bean may be deferred; a prototype bean is newly created each time the container is asked for it; web-scoped beans have their own lifecycles.

## 4. Before There Is a Bean, There Must Be a Bean Definition

The container needs to know **what is allowed to be created**. This registration information is generally called a **bean definition**: name, type or object creation information, scope, initialization conditions, autowiring metadata, and lifecycle attributes.

Common registration sources in Spring Boot:

1. **Component scanning**: finding classes annotated with `@Component` or corresponding stereotypes.
2. **`@Bean` methods**: declaring an object created via a factory method.
3. **Import and configuration**: loading additional configuration/bean definitions via Spring mechanisms.
4. **Spring Boot auto-configuration**: registering beans based on present libraries, beans, and properties when conditions match.
5. **Programmatic registration**: infrastructure can register definitions or singletons via container APIs, seen more often in frameworks/libraries than basic applications.

### Component Scanning

A simple service:

```java
package com.example.demo.service;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

`@Service` is a specialized `@Component` annotation. It clarifies the **business role** for readers while serving as a candidate for component scanning.

Familiar stereotypes:

| Annotation | Primary Message | Can It Become a Bean When Scanned? |
|---|---|---|
| `@Component` | General Spring-managed component. | Yes. |
| `@Service` | Component containing application/business logic. | Yes. |
| `@Repository` | Data access layer component. | Yes; also integrates exception translation when configured appropriately. |
| `@Controller` | Web MVC controller. | Yes. |
| `@RestController` | Web controller returning response bodies in REST/controller style. | Yes; combines the semantics of `@Controller` and `@ResponseBody`. |
| `@Configuration` | Class declaring configuration, typically containing `@Bean` methods. | Yes, when loaded via appropriate scanning/importing. |

**An annotation alone does not guarantee the bean is registered.** Spring must actually scan or import the configuration containing that class. A service placed outside the default scan package may not be found.

`@SpringBootApplication` includes component scanning according to Boot conventions. By default, scanning starts from the package of the main/configuration class and its subpackages. For example:

```text
com.example.demo/
├── DemoApplication.java       # @SpringBootApplication
├── controller/
│   └── GreetingController.java
└── service/
    └── GreetingService.java
```

The two classes in `controller` and `service` sit inside subpackages of `com.example.demo` and are therefore normally scanned. A class in `com.other.service` does not automatically fall within that scope.

### Bean Definitions Can Be Blocked by Conditions

Spring Boot auto-configuration frequently uses conditions such as:

- Presence or absence of a specific class on the classpath.
- Presence or absence of a bean of a matching type/name.
- A configuration property having a required value.
- Matching application type or runtime environment.

For instance, Boot may automatically declare a default component **only if the application has not already provided a replacement bean**. Therefore, the claim "having a starter means bean X exists" always needs to be evaluated against actual conditions.

## 5. Two Common Ways to Declare Beans

### Approach A — Annotating Application Classes with Stereotypes

```java
package com.example.demo.service;

import org.springframework.stereotype.Service;

@Service
public class PriceService {
    public long calculate(long unitPrice, int quantity) {
        return unitPrice * quantity;
    }
}
```

When component scan discovers this class, Spring registers a bean definition and uses an appropriate constructor to create the instance. This is usually the natural choice for your application's services, controllers, and repositories.

### Approach B — Using `@Bean` Factory Methods

Sometimes you do not own the class's source code, or you need explicit control over instantiation. For example, registering `java.time.Clock`:

```java
package com.example.demo.config;

import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TimeConfiguration {

    @Bean
    public Clock appClock() {
        return Clock.systemUTC();
    }
}
```

`Clock` belongs to the JDK and has no `@Component`. The `appClock()` method tells the container how to create the object. As a result, **`Clock` is managed as a bean** when this configuration is loaded.

In both approaches, the final runtime object may be a regular Java object or an infrastructure-created **proxy**; what they share is that the container manages allocation/access according to the bean definition.

| Case | Usually Chosen |
|---|---|
| Class written by you acting as service/controller/repository | `@Service`, `@Controller`, `@Repository`... |
| Class from a library/JDK where annotations cannot be edited | `@Bean` inside a configuration class. |
| Need custom constructor, choosing implementation by config | `@Bean` with parameters or suitable factory logic. |
| Need to bring an object already created by a library into the container | Register the bean via appropriate configuration/infrastructure. |

## 6. A Complete Spring Boot Example: Container Assembling Beans

Suppose the project has root package `com.example.demo` and the web MVC starter matching the Boot version in use. The goal is creating an endpoint returning the current UTC time.

**File 1: `DemoApplication.java`**

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

**File 2: `config/TimeConfiguration.java`**

```java
package com.example.demo.config;

import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TimeConfiguration {
    @Bean
    public Clock appClock() {
        return Clock.systemUTC();
    }
}
```

**File 3: `service/TimeService.java`**

```java
package com.example.demo.service;

import java.time.Clock;
import java.time.Instant;
import org.springframework.stereotype.Service;

@Service
public class TimeService {
    private final Clock clock;

    public TimeService(Clock clock) {
        this.clock = clock;
    }

    public Instant now() {
        return Instant.now(clock);
    }
}
```

**File 4: `controller/TimeController.java`**

```java
package com.example.demo.controller;

import com.example.demo.service.TimeService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class TimeController {
    private final TimeService timeService;

    public TimeController(TimeService timeService) {
        this.timeService = timeService;
    }

    @GetMapping("/time")
    public String currentTime() {
        return timeService.now().toString();
    }
}
```

Spring handles the relationships conceptually as:

```text
Bean definition TimeConfiguration
           │ @Bean
           ▼
        Clock bean
           │ constructor dependency
           ▼
     TimeService bean
           │ constructor dependency
           ▼
    TimeController bean
           │ Spring MVC mapping
           ▼
       GET /time
```

The programmer does not need `new TimeController(new TimeService(Clock.systemUTC()))` inside `main()`. The container knows how to create and link them based on bean definitions. With a running Spring MVC application, the HTTP request `GET /time` is routed to the controller.

**Improved testability:** because `TimeService` accepts a `Clock` via constructor, plain Java tests can construct `Clock.fixed(...)` and assert deterministic time results without starting the entire Spring Boot context.

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock fixed = Clock.fixed(
        Instant.parse("2026-01-01T00:00:00Z"),
        ZoneOffset.UTC
);
TimeService service = new TimeService(fixed);
System.out.println(service.now()); // 2026-01-01T00:00:00Z
```

This illustrative snippet resides in a context that can access `TimeService`; when placed in a separate Java file, appropriate package imports are required. **An object is allowed to be used outside Spring in unit tests** even though at application runtime it is declared as a bean.

## 7. How Does Spring Find Dependencies?

When instantiating `TimeService`, Spring sees that the constructor requires a `Clock`. The container looks up a bean capable of satisfying that dependency. If a matching candidate is found, Spring passes the corresponding instance to the constructor.

This is **constructor injection**, usually preferred because dependencies are clearly visible, easy to test, and can be stored in `final` fields.

### Is `@Autowired` Needed on Constructors?

For a class with **only one constructor**, modern Spring can use that constructor to inject dependencies **without** `@Autowired`.

```java
@Service
public class AuditService {
    private final EventPublisher publisher;

    public AuditService(EventPublisher publisher) {
        this.publisher = publisher;
    }
}
```

This snippet assumes `EventPublisher` is a declared type and the container has a corresponding bean. If there are multiple constructors or a specific injection point must be designated, constructor selection rules must be examined carefully; `@Autowired` may be required.

Spring also supports setter and field injection, though field injection makes dependencies less explicit when instantiating objects in unit tests and makes immutability harder to establish. In new business code, constructor injection is usually easier to understand and maintain.

### What If Two Beans Implement the Same Interface?

Example:

```java
public interface MessageSender {
    void send(String text);
}
```

Two implementations:

```java
import org.springframework.stereotype.Component;

@Component("emailSender")
public class EmailSender implements MessageSender {
    @Override
    public void send(String text) {
        // Send email...
    }
}

@Component("smsSender")
public class SmsSender implements MessageSender {
    @Override
    public void send(String text) {
        // Send SMS...
    }
}
```

If a constructor simply asks for `MessageSender` without disambiguating information, Spring may report **multiple matching beans**. You can explicitly select one with `@Qualifier`:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class NotificationService {
    private final MessageSender sender;

    public NotificationService(
            @Qualifier("emailSender") MessageSender sender) {
        this.sender = sender;
    }
}
```

`@Primary` is another option: designating one bean as the default candidate when multiple matching beans exist. Selection rules may also involve parameter names, generics, qualifiers, or other metadata, so it is best to state intent explicitly when multiple implementations exist.

**Bean name** and **bean type** are two different attributes. In the example, the bean is named `emailSender` and its type is assignable to `EmailSender`/**`MessageSender`**. Do not confuse the Java class name with the bean name; Spring has default naming rules while still allowing name overrides through configuration.

## 8. Scopes Determine How Beans Live and Get Reused

**Scope** answers the question: does the container return the same instance or create/locate another instance when a bean is requested?

| Scope | Basic Behavior | Common Scenarios |
|---|---|---|
| **singleton** (default) | One container-managed instance per bean definition within a Spring container. | Stateless services, configuration/infrastructure services. |
| **prototype** | The container creates a new instance each time the bean is requested from the container. | Stateful objects that need to be created per specific request. |
| **request** | One instance bound to an HTTP request in a web-aware context. | Data living strictly for the request lifecycle. |
| **session** | One instance bound to an HTTP session when supported. | Per-user session state in web applications. |
| **application** | Bean bound to the `ServletContext` in compatible web applications. | Application state scoped to the servlet application. |
| **websocket** | Scoped to a WebSocket session in supporting infrastructure. | State for a single WebSocket connection. |

Web scopes require an appropriate web environment. You cannot assume a `request` bean works in a command-line program with no active request.

### Spring's Singleton Is Not a JVM-Wide Singleton

The **singleton concept in Spring** applies within the scope of **a single bean definition belonging to a single container**. It is not equivalent to the Java/GoF Singleton pattern guaranteeing only one object across the entire JVM process.

Suppose two independent `ApplicationContext` instances both register a singleton `PriceService` bean. Each context can hold its own separate instance. Similarly, two distinct bean definitions of the same Java class can produce two instances.

Inside a typical context:

```java
PriceService first = context.getBean(PriceService.class);
PriceService second = context.getBean(PriceService.class);

System.out.println(first == second); // true if the singleton bean is returned directly
```

The snippet above assumes the context has only **one** bean matching `PriceService`. If Spring returns a singleton proxy, two lookups still normally return the same proxy per scope; you should **not** conclude that two method invocations hit only a single underlying business object behind every kind of scoped proxy.

### Are Singleton Beans Automatically Thread-Safe?

**No.** The container manages instance count, but does not make mutable fields safe for concurrent access.

Example of a service with shared state unsuitable for multiple concurrent HTTP requests:

```java
@Service
public class CounterService {
    private int count;

    public int next() {
        return ++count; // Data race when multiple threads call concurrently
    }
}
```

With a singleton web service, multiple requests can call `next()` simultaneously. If you truly need a counter within a single JVM, you can use `AtomicInteger`:

```java
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Service;

@Service
public class CounterService {
    private final AtomicInteger count = new AtomicInteger();

    public int next() {
        return count.incrementAndGet();
    }
}
```

This only guarantees safe counting within the corresponding JVM instance; it does not create a shared counter across multiple Spring Boot instances on different machines. Distributed application state requires an appropriate store or coordination service.

**Common practice:** write singleton services to be stateless, keep business state in a database/cache or in method-local call variables, and apply synchronization appropriately when shared mutable state is necessary.

## 9. Prototype Scope: Creating New Instances Does Not Mean Changing Everywhere

Example of a prototype bean:

```java
import java.util.UUID;
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.Scope;
import org.springframework.stereotype.Component;

@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class ReportDraft {
    private final UUID id = UUID.randomUUID();

    public UUID id() {
        return id;
    }
}
```

Each time the container is asked to supply a prototype `ReportDraft`, it typically creates a new instance:

```java
ReportDraft a = context.getBean(ReportDraft.class);
ReportDraft b = context.getBean(ReportDraft.class);
// a != b
```

However, if you **inject a prototype directly into the constructor of a singleton**, the container obtains the prototype when creating the singleton. The singleton holds a reference to that single instance; **no new prototype is automatically created for each method call**.

To get a new instance on demand, you can use `ObjectProvider<T>`:

```java
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    private final ObjectProvider<ReportDraft> drafts;

    public ReportService(ObjectProvider<ReportDraft> drafts) {
        this.drafts = drafts;
    }

    public String newDraftId() {
        return drafts.getObject().id().toString();
    }
}
```

Each time `getObject()` is called, the provider asks the container for a bean according to its declared scope. This is an on-demand lookup technique that avoids passing `ApplicationContext` directly into the service.

**Lifecycle note:** Spring instantiates prototypes and runs initialization callbacks upon bean creation, but the container normally **does not invoke destruction callbacks for each prototype** after handing the instance to the caller. If a prototype owns resources that must be closed, calling code must manage releasing them by design.

## 10. Request and Session Beans: When Are Proxies Needed?

Beans tied to an HTTP request should not be held directly as a fixed instance for the entire lifetime of a singleton service. You can use a **scoped proxy** or provider so the container locates the right object for the current request.

Example with Spring MVC, a request-scoped bean:

```java
package com.example.demo.web;

import java.util.UUID;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.RequestScope;

@Component
@RequestScope
public class RequestTrace {
    private final String traceId = UUID.randomUUID().toString();

    public String traceId() {
        return traceId;
    }
}
```

`@RequestScope` is a dedicated annotation for request scope that uses a scoped proxy by default according to Spring's mechanism. A singleton service can receive a proxy of `RequestTrace`, while the actual object behind the proxy is resolved for the current request.

```text
Singleton service
       │ holds reference
       ▼
RequestTrace scoped proxy
       │ call during request A
       ├──> RequestTrace instance A
       │ call during request B
       └──> RequestTrace instance B
```

If a method requiring request scope is called when **no HTTP request is active** (for instance, from a background thread without request context), the container may throw a scope-not-active error. Request-scoped beans are not a mechanism for arbitrarily propagating state to new threads.

WebFlux and reactive models have execution contexts that differ from servlet thread-locals, so when using a reactive stack you must choose suitable context propagation mechanisms rather than applying servlet request-scope patterns to every application type.

## 11. A Bean's Lifecycle: From Definition to Destruction

For an ordinary singleton bean created at application context startup, we can visualize a simplified sequence:

```text
1. Register bean definition
         │
2. Decide bean needs creation (eager/lazy/scope)
         │
3. Instantiate object (constructor/factory method)
         │
4. Populate dependencies, inject required properties
         │
5. Invoke aware callbacks and pre-init BeanPostProcessors
         │
6. Initialization callbacks (@PostConstruct, afterPropertiesSet, initMethod...)
         │
7. Post-init BeanPostProcessors; may return a proxy
         │
8. Bean is ready for other components to use
         │
9. Context closes → destruction callbacks for beans with matching lifecycle
```

This is a **simplified model**. Extension points such as bean factory post-processing, bean post-processing, circular reference handling, and proxy creation mechanisms can make the actual observed sequence more complex. Do not use this diagram to predict exact log ordering across hundreds of beans.

### Lifecycle Callback Example

In Spring Boot 3+ using Jakarta annotations:

```java
package com.example.demo.service;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

@Component
public class ResourceMonitor {

    @PostConstruct
    public void start() {
        System.out.println("ResourceMonitor: initialized");
    }

    @PreDestroy
    public void stop() {
        System.out.println("ResourceMonitor: destroying");
    }
}
```

- `@PostConstruct` is invoked during the bean initialization phase, after the container has injected relevant dependencies.
- `@PreDestroy` is typically invoked when the container destroys singleton beans during normal context shutdown, if the corresponding lifecycle is supported.
- If the application is forcibly terminated by the operating system—such as an ungraceful kill or crash—**destruction callbacks cannot be guaranteed to run**.

You should not place entire background workloads or long-running processing inside `@PostConstruct`. At that time, the application context may not have finished all startup steps; some proxy/event/listener mechanisms may not yet be in the state you expect. For work that must run after application startup, look into `ApplicationRunner`, `CommandLineRunner`, and corresponding application events.

### What About `InitializingBean` and `DisposableBean`?

Spring also supports callbacks via the `InitializingBean`/`DisposableBean` interfaces and `initMethod`/`destroyMethod` in `@Bean` configuration. These are alternative options for initialization and resource cleanup; you do not need to combine all of them just to make a bean work.

Example of registering a Java object that has a resource-closing method:

```java
@Configuration
public class ClientConfiguration {

    @Bean(destroyMethod = "close")
    public MyClient myClient() {
        return new MyClient();
    }
}
```

The example above **assumes** you have a `MyClient` class and a matching `close()` method; it simply illustrates the meaning of `destroyMethod`. Most resource integrations already have standard starters/configurations, so use built-in mechanisms before building complex connection-managing beans yourself.

## 12. Being Container-Managed Does Not Mean Every Call Goes Through Spring

An important misconception: Spring managing a bean does not mean the container intercepts **every single line of Java code**.

Given a service:

```java
@Service
public class ProductService {
    public String formatName(String input) {
        return input.trim();
    }
}
```

Once an instance/proxy of `ProductService` exists, normal method calls execute using standard Java mechanics. Spring only adds behavior when a corresponding mechanism applies, such as an AOP proxy used for transactions, caching, async execution, or method security.

### Proxy and Target Object

A proxy can stand between the bean reference held by a caller and the target object:

```text
Caller → Spring-managed proxy → target object → method
            │
            ├─ before/after method per advice
            └─ transaction, caching, security... when configured
```

This lets Spring apply cross-cutting concerns without writing transaction-handling boilerplate in every controller.

However, **not every bean is proxied**, and not every call passes through a proxy. Depending on extension points and technology, Spring may choose a JDK dynamic proxy or a class-based proxy.

### Self-Invocation: Internal Method Calls Can Bypass Advice

Conceptual example:

```java
@Service
public class PaymentService {

    public void pay() {
        savePayment(); // internal call via this
    }

    @Transactional
    public void savePayment() {
        // save data...
    }
}
```

Assume `@Transactional` is configured to operate via **proxy-based transaction management**. When calling `pay()` on the bean proxy, the `this.savePayment()` call inside the target **may not go back through the proxy**, so the transaction advice on `savePayment()` may not execute as expected.

To achieve the desired behavior, you typically extract the transactional method into another bean and inject it into the caller, or place the transaction boundary on the method called externally through the proxy. Distinguish this detail from running with AspectJ weaving; you cannot claim every kind of Spring AOP behaves identically to proxy self-invocation.

### Do Not Manually `new` a Service That Needs Advice

If you manually call `new PaymentService()` inside a controller, that instance does not go through the Spring lifecycle, dependency injection, transaction proxy, security, or caching. This is a common reason annotations are "present on the class yet have no effect" at runtime.

## 13. `@Configuration` and `@Bean`: Java Call or Bean Reference?

In a standard `@Configuration` class, Spring can intercept calls between `@Bean` methods to return a container-managed bean according to its scope rather than merely executing the method body like plain Java.

Example:

```java
@Configuration
public class OrderConfiguration {

    @Bean
    public Notifier notifier() {
        return new EmailNotifier();
    }

    @Bean
    public OrderService orderService() {
        return new OrderService(notifier());
    }
}
```

With **full `@Configuration`** (the `@Bean` method interception mechanism when `proxyBeanMethods=true`, which is the default for `@Configuration`), Spring can ensure the `notifier()` call resolves to the container-managed `Notifier` bean in accordance with the definition's scope.

However, with `@Configuration(proxyBeanMethods = false)` or `@Bean` methods inside lite configuration mode, calling `notifier()` directly is an **ordinary Java method call** and can instantiate a new object outside the intended container flow.

A clearer approach that relies less on interception behavior is **injecting via factory method parameters**:

```java
@Configuration(proxyBeanMethods = false)
public class OrderConfiguration {

    @Bean
    public Notifier notifier() {
        return new EmailNotifier();
    }

    @Bean
    public OrderService orderService(Notifier notifier) {
        return new OrderService(notifier);
    }
}
```

Spring resolves the `Notifier` parameter before calling `orderService(...)`. Treat `@Bean` configuration as a way to **declare relationships between bean definitions**, not a place to manually recreate every object inside each method.

## 14. Lazy Initialization and When Beans Are Actually Created

Default singletons are normally initialized during context refresh, but this can be changed with `@Lazy`:

```java
import org.springframework.context.annotation.Lazy;
import org.springframework.stereotype.Service;

@Lazy
@Service
public class HeavyReportService {
    public HeavyReportService() {
        System.out.println("Constructing HeavyReportService");
    }
}
```

Meaning: the container can defer creating this bean until needed. However, if another singleton **eagerly** requires `HeavyReportService` in its constructor, that can still cause the bean to initialize early; to defer the dependency itself, a proxy/lazy injection or suitable provider may be needed.

Some systems enable lazy initialization more broadly via Boot configuration. This can reduce initial startup work while causing missing dependency/configuration errors to surface **later**, when the feature is first accessed. Therefore, eager and lazy are choices about lifecycle and error-detection timing, not a universal optimization rule.

## 15. Beans Can Vary by Profile or Configuration Conditions

Spring Boot allows beans to appear only when the environment matches, for example:

```java
public interface StorageClient {
    String where();
}
```

```java
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("local")
public class LocalStorageClient implements StorageClient {
    @Override
    public String where() {
        return "local";
    }
}
```

```java
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("prod")
public class ProductionStorageClient implements StorageClient {
    @Override
    public String where() {
        return "remote";
    }
}
```

When the `local` profile is active, Spring can register `LocalStorageClient`; with `prod`, the corresponding candidate is `ProductionStorageClient`. If no profile matches and a service requires `StorageClient`, initialization may fail due to a missing bean. If both profiles are active simultaneously, multiple candidates may appear, requiring a bean selection configuration.

Profiles are one of many bean registration conditions. Boot auto-configuration frequently uses richer conditional annotations such as `@ConditionalOnClass` or `@ConditionalOnMissingBean` to supply default beans only when appropriate.

**Do not check profiles by manually instantiating objects across multiple places** when dependency relationships can already be declared cleanly via beans and configuration.

## 16. Common Bean Errors and Their Meanings

| Common Symptom / Error | Possible Meaning | How to Check |
|---|---|---|
| `NoSuchBeanDefinitionException` | The container found no bean matching the dependency/lookup. | Check package scan, annotations, `@Bean` config, profiles, conditions, and dependencies. |
| `NoUniqueBeanDefinitionException` | Multiple matching beans exist and no single one could be selected. | Inspect candidates, `@Qualifier`, `@Primary`, and test/profile configs. |
| `BeanCreationException` | Creating or initializing a bean failed. | Read the deepest cause in the stack trace: constructor, config, resources, callbacks, dependencies. |
| `UnsatisfiedDependencyException` | A mandatory bean dependency was not satisfied. | Identify which parameter/field failed; check missing beans, wrong types, or multiple candidates. |
| `BeanCurrentlyInCreationException` | Possible circular dependency or issue during bean creation. | Check dependency graph and constructor design; avoid A → B → A cycles. |
| `ScopeNotActiveException` | Bean belongs to a scope not active in the current context. | Verify active request/session and usage of scoped proxies/providers. |
| `@Transactional`/`@Async` has no effect | Object is not container-managed or the call bypasses proxy/advice config. | Check how the bean is obtained, internal self-calls, AOP config, and proxy scope. |

Some errors are wrapped by Spring across multiple exception layers. The final line is helpful but insufficient; read the `Caused by` chain to locate the original cause.

### Constructor Circular Dependency

Example:

```java
@Service
public class ServiceA {
    public ServiceA(ServiceB b) { }
}

@Service
public class ServiceB {
    public ServiceB(ServiceA a) { }
}
```

To create `ServiceA`, the container needs `ServiceB`; to create `ServiceB`, it again needs `ServiceA`. With constructor injection, this circular relationship cannot be resolved as an ordinary linear initialization graph.

Instead of enabling circular-reference flags as a default fix, review the design: extract shared responsibilities, invert a dependency, or use events/callbacks when two components genuinely need to coordinate without holding bidirectional references.

## 17. Seeing Which Beans the Container Is Managing

During development/debugging, you can inspect `ApplicationContext`:

```java
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class BeanInspectorConfiguration {

    @Bean
    CommandLineRunner showTimeBeans(ApplicationContext context) {
        return args -> {
            for (String name : context.getBeanNamesForType(
                    com.example.demo.service.TimeService.class)) {
                System.out.println("TimeService bean: " + name);
            }
        };
    }
}
```

This example builds on `TimeService` from section 6 and assumes the config class is in a scanned package. On startup, the runner prints bean names of type `TimeService`. In real projects, use a logger and avoid dumping all beans if sensitive data or excessive output may appear.

You can verify singleton identity with a Spring Boot test:

```java
package com.example.demo;

import static org.junit.jupiter.api.Assertions.assertSame;

import com.example.demo.service.TimeService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

@SpringBootTest
class BeanIdentityTest {

    @Autowired
    ApplicationContext context;

    @Test
    void sameSingletonBeanIsReturned() {
        TimeService first = context.getBean(TimeService.class);
        TimeService second = context.getBean(TimeService.class);
        assertSame(first, second);
    }
}
```

The test assumes a single `TimeService` singleton bean and that the appropriate test starter has been added. **This is an exercise in observing scope**, not proof that every bean or every scope returns the same instance.

When an application meets requirements to enable Spring Boot Actuator, the `beans` endpoint can help inspect bean definitions and dependencies in a controlled environment. Configure appropriate exposure and secure management endpoints properly; never assume Actuator endpoints are all safe to expose publicly.

## 18. Common Misconceptions

**"Having `@Service` means Spring creates a new object on every method call."** False under default singleton scope. Repeated calls on the same bean can reuse the same instance across many requests.

**"A Spring singleton is a single instance across all machines."** False. Singleton scope is bound to one bean definition inside one container. Two Spring Boot processes do not share a Java heap.

**"Once dependencies are injected, I can freely `new` the service elsewhere without issue."** You can create a plain Java object, but that instance does not carry container-managed dependencies, lifecycle, or proxies. Choose the right mechanism for the goal.

**"`@Autowired` is the only way to inject."** A single constructor on a Spring-managed class can be used without writing the annotation. More important is clearly defining required dependencies.

**"Prototype means a new object for every HTTP request."** Not necessarily. Prototype means new **each time the container supplies the bean**, not automatically synchronized with requests. Request scope describes a lifecycle bound to HTTP requests.

**"Being a bean automatically makes it thread-safe."** No. Shared mutable state must be protected properly or avoided on singleton services.

**"One starter creates every bean for every case."** No. Starters bring dependencies onto the classpath; auto-configuration still depends on conditions and configuration.

**"`@PostConstruct` proves the entire application is ready."** No. It pertains to the initialization phase of **one bean**, not a guarantee that full startup has completed.

**"A method with `@Transactional` always runs in a transaction."** Not under every call path. With proxy-based interception, direct self-invocation can bypass the advice.

## 19. Hands-On Exercises on Beans and the IoC Container

### Exercise A: Comparing `new` with a Bean

Create `GreetingService` as in section 1, and try calling it via `new` inside a unit test. Then add `@Service` and inject it into a controller. Explain the responsibilities of the caller and the Spring container in each approach.

### Exercise B: Using Constructor Injection and a `Clock` Bean

Create `TimeConfiguration`, `TimeService`, and `TimeController` as in section 6. Hit `GET /time`. Then unit test `TimeService` with `Clock.fixed`. Observe why the same service class works both inside and outside Spring.

### Exercise C: Creating Two Implementations of the Same Interface

Register `emailSender` and `smsSender`, then inject `MessageSender` into a service. Observe the exception when a unique candidate cannot be chosen; use `@Qualifier` to specify the desired bean.

### Exercise D: Observing Singleton and Prototype

Create a prototype `ReportDraft`, call `context.getBean(ReportDraft.class)` twice, and compare identities. Try injecting it directly into a singleton and calling the method multiple times. Then use `ObjectProvider<ReportDraft>` to obtain a fresh instance on demand.

### Exercise E: Inspecting Lifecycle

Add `@PostConstruct` and `@PreDestroy` to a simple bean. Start and gracefully stop the application; observe the callbacks. Explain why you should not rely solely on destruction callbacks to guarantee completion of a critical business transaction.

### Exercise F: Observing Auto-Configuration

Add a Spring Boot starter matching your project's Boot version, run the application in debug mode, and locate the conditions evaluation report. Find one auto-configuration that applied and one that did not. Explain the classpath/bean/property conditions rather than judging solely by the starter's name.

## 20. Conclusion on Container Responsibilities

A **Spring bean** is an object recognized by the container via a bean definition and managed according to configuration. The container knows **how to create it**, **how to select and inject dependencies**, **when to reuse or create a new instance**, **which lifecycle callbacks apply**, and **which extension mechanisms wrap the bean**. From this, the application can cleanly separate business logic from manual object assembly.

When writing Spring Boot code, picture the path:

```text
@Component / @Service / @Repository / @Controller
@Bean / @Configuration / auto-configuration
                    │
                    ▼
             Bean definitions
                    │
                    ▼
              IoC container
       ┌────────────┼────────────┐
 Instantiation   DI Injection   Scope/lifecycle
       └────────────┼────────────┘
                    ▼
       Bean (instance or proxy)
                    │
                    ▼
       Controllers, services, repositories,
          application and callers
```

This mental model explains most missing-bean, multiple-bean, circular-dependency, wrong-scope, lifecycle, and non-working proxy annotation errors. Instead of adding annotations out of habit, you can pinpoint **whether the container registered the bean, which bean is being created, which dependency is selected, and what instance is actually returned**.
