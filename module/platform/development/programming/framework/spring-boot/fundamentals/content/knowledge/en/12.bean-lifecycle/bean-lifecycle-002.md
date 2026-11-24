# Constructor Initialization, Dependency Injection, and Lifecycle Callbacks

When Spring creates a bean, the work does not stop at calling a constructor. The container must find and create required dependencies, assign them to the bean, run initialization callbacks, apply post-processors, and finally manage bean destruction when the context closes.

Understanding this sequence helps you know whether to place logic in a constructor or `@PostConstruct`, why dependencies are already usable in certain callbacks but should not be accessed at other times, and why singleton beans are typically created right when a Spring Boot application starts up.

This lesson belongs to the **Bean Lifecycle** chapter of **Spring Boot Fundamentals**. We will trace a bean's journey from constructor, dependency injection, and initialization callbacks to destruction callbacks, while also distinguishing the lifecycles of singleton, prototype, and `@Bean`-created beans.

## 1. What Phases Does a Bean Go Through?

For a regular bean managed by Spring, the general flow can be pictured as:

```text
Bean definition is registered
          │
          ▼
Container chooses how to create the bean
(constructor or factory method)
          │
          ▼
Resolve dependencies needed for creation
          │
          ▼
Instantiate: create the object
          │
          ▼
Populate properties / field / setter injection
          │
          ▼
Aware callbacks
          │
          ▼
BeanPostProcessor: before initialization
          │
          ▼
Initialization callbacks
  @PostConstruct
  InitializingBean.afterPropertiesSet()
  custom init method
          │
          ▼
BeanPostProcessor: after initialization
          │
          ▼
Bean is ready to use
          │
          ▼
Context closes / bean destroyed by scope
          │
          ▼
Destruction callbacks
  @PreDestroy
  DisposableBean.destroy()
  custom destroy method
```

This is a learning diagram for a container-managed bean. Some steps may vary depending on creation method, scope, lazy initialization, and configured infrastructure. For example, dependencies used in a constructor are resolved **before the current bean's constructor runs**; field and setter injection happen after the object has been instantiated.

Phases to distinguish:

- **Instantiation:** creating the Java object.
- **Dependency injection / property population:** supplying dependencies and configuration values.
- **Initialization:** running callbacks so the bean finishes preparing itself.
- **Post-processing:** allowing Spring and integration frameworks to process or wrap the bean, such as creating proxies.
- **Destruction:** invoking cleanup callbacks when the container manages the end of the bean's lifecycle.

Not every object created with `new` goes through this workflow. An object only receives the full Spring lifecycle when it is registered and managed as a bean inside the container.

## 2. Bean Definition and Bean Instance

Before creating an object, Spring needs to know the **bean definition**. A bean definition describes how to create and manage a bean, such as:

- Bean class or factory method.
- Bean name and aliases.
- Constructor arguments or property values.
- Scope such as singleton or prototype.
- Required dependencies.
- Init method and destroy method.
- Relevant configuration conditions.

Example:

```java
@Configuration(proxyBeanMethods = false)
public class ClockConfiguration {

    @Bean
    public Clock applicationClock() {
        return Clock.systemUTC();
    }
}
```

The `applicationClock()` method provides a bean definition. When the container creates the bean from this definition, it calls the factory method and manages the returned object.

Distinction:

```text
Bean definition
  "Create a bean of type Clock using applicationClock()"
                 │
                 ▼
Bean instance
  A concrete Clock object returned by the factory method
```

A bean definition is not an object; it is metadata for the container to create and manage the object.

## 3. Instantiation: When Is the Constructor Called?

Instantiation is the step of creating a Java object. For a bean declared by a class, Spring selects the appropriate constructor, resolves the required parameters, and calls the constructor to create the instance.

Example:

```java
package com.example.demo.service;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    private final String greetingPrefix;

    public GreetingService() {
        this.greetingPrefix = "Hello";
    }

    public String greet(String name) {
        return greetingPrefix + ", " + name + "!";
    }
}
```

When Spring creates the `GreetingService` bean, it calls the constructor. Afterward, the bean is processed through the subsequent lifecycle phases.

### 3.1. Constructor with dependencies

Typically, a bean needs another dependency:

```java
package com.example.demo.service;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    private final MessageFormatter formatter;

    public GreetingService(MessageFormatter formatter) {
        this.formatter = formatter;
    }

    public String greet(String name) {
        return formatter.format(name);
    }
}
```

```java
package com.example.demo.service;

import org.springframework.stereotype.Component;

@Component
public class MessageFormatter {

    public String format(String name) {
        return "Hello, " + name + "!";
    }
}
```

Before invoking the `GreetingService(MessageFormatter)` constructor, Spring must find a matching bean of type `MessageFormatter`. If that bean does not yet have an instance and needs to be created, the container creates the dependency first according to the dependency graph.

```text
Create GreetingService
       │
       ▼
Needs MessageFormatter
       │
       ▼
Create MessageFormatter
       │
       ▼
Complete MessageFormatter
       │
       ▼
Call constructor GreetingService(formatter)
       │
       ▼
Complete GreetingService
```

Thanks to this, when the `GreetingService` constructor runs, the `formatter` parameter has already been supplied. You do not need to call `new MessageFormatter()` inside the service.

### 3.2. When a class has only one constructor

For a Spring bean class with only **one constructor**, Spring can use that constructor to inject dependencies without needing `@Autowired`.

```java
@Service
public class OrderService {

    private final PaymentGateway paymentGateway;

    public OrderService(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }
}
```

This approach is common because:

- Dependencies are made explicit right in the constructor.
- Fields can be declared `final`.
- The object does not have to exist in a state missing required dependencies.
- It is easy to write unit tests by passing fake/mock dependencies directly.
- No field injection or setter injection is needed.

If there are multiple constructors, you need to explicitly indicate the right constructor with `@Autowired` or corresponding configuration. Do not leave multiple constructors and expect Spring to guess the constructor you want.

### 3.3. Dependencies must be available before the current bean's constructor runs

Example:

```java
@Service
public class ReportService {

    private final Clock clock;

    public ReportService(Clock clock) {
        this.clock = clock;
        System.out.println("ReportService constructor");
    }
}
```

If a `Clock` bean does not yet exist, Spring must find or create an appropriate bean first. If none is found, the container cannot invoke the constructor with a valid argument, and `ReportService` creation fails.

This error is typically wrapped in `UnsatisfiedDependencyException` or `BeanCreationException`. You should read deeper into the cause to know whether a bean is missing, multiple matching beans exist, or the dependency itself failed to be created.

## 4. Constructor Injection, Setter Injection, and Field Injection

Spring supports multiple ways to provide dependencies. They differ in when the object is created and how well they express a valid object state.

### 4.1. Constructor injection

```java
@Service
public class InvoiceService {

    private final TaxCalculator taxCalculator;

    public InvoiceService(TaxCalculator taxCalculator) {
        this.taxCalculator = taxCalculator;
    }
}
```

The dependency is resolved before the constructor runs and passed into the constructor. The bean cannot be successfully created if a required dependency is not supplied.

This is usually the preferred choice for required dependencies.

### 4.2. Setter injection

```java
@Component
public class ReportExporter {

    private StorageClient storageClient;

    @Autowired
    public void setStorageClient(StorageClient storageClient) {
        this.storageClient = storageClient;
    }

    public void export(byte[] content) {
        storageClient.store(content);
    }
}
```

Setter injection requires the object to be instantiated first, after which Spring calls the setter to assign the dependency. It is better suited for optional or mutable dependencies, though you must avoid letting the bean be used before the setter has been called.

### 4.3. Field injection

```java
@Component
public class NotificationService {

    @Autowired
    private EmailSender emailSender;
}
```

Spring creates the object and then injects into the field via reflection during the property population step. This is concise, but dependencies are hidden from the constructor, fields are hard to keep immutable, and unit tests often have to use reflection or spin up a Spring context.

For new applications, constructor injection is generally clearer.

### 4.4. Timing comparison

| Injection style | When is the object created? | When is the dependency provided? | Notes |
|---|---|---|---|
| Constructor | After constructor parameters are resolved | Directly in the constructor | Good for required dependencies |
| Setter | Before the setter is called | After instantiation | Useful for optional dependencies |
| Field | Before the field is injected | After instantiation, via reflection | Dependencies are harder to see from the class API |

Spring also supports method injection and some other mechanisms. Whichever approach is used, dependencies must be resolved by the container according to bean definitions and autowiring rules.

## 5. Field/Property Population Happens After Instantiation

With setter or field injection, the basic sequence is:

```text
Call constructor
      │
      ▼
Object is created
      │
      ▼
Spring processes dependency injection
      │
      ├── inject fields
      ├── call setters
      └── apply property values
      │
      ▼
Continue callbacks and initialization
```

Example:

```java
@Component
public class AuditService {

    private Clock clock;

    @Autowired
    public void setClock(Clock clock) {
        this.clock = clock;
    }

    @PostConstruct
    public void initialize() {
        System.out.println("Clock injected: " + clock);
    }
}
```

When `@PostConstruct` is invoked in the standard initialization flow, setter injection has already been performed. Therefore, the callback can use `clock`.

However, do not use the constructor to access a field injected via `@Autowired` after instantiation: at the time the constructor runs, that field has not yet been assigned by Spring.

```java
@Component
public class IncorrectService {

    @Autowired
    private Clock clock;

    public IncorrectService() {
        // clock has not yet been field-injected at this point.
        // clock.instant(); // NullPointerException
    }
}
```

This is another reason to use constructor injection: required dependencies are present as soon as the object is created.

## 6. Aware Callbacks: Beans Receive Information from the Container

After the object is instantiated and dependencies/properties are supplied, Spring can invoke `Aware`-group callbacks so the bean receives information about its managing environment.

Examples:

- `BeanNameAware`: receives the bean name in the container.
- `BeanClassLoaderAware`: receives the class loader used to load the bean.
- `BeanFactoryAware`: receives the BeanFactory managing the bean.
- `ApplicationContextAware`: receives the ApplicationContext if the context infrastructure supports this callback.

Example:

```java
@Component
public class ContainerInfo implements BeanNameAware, BeanFactoryAware {

    private String beanName;
    private BeanFactory beanFactory;

    @Override
    public void setBeanName(String name) {
        this.beanName = name;
    }

    @Override
    public void setBeanFactory(BeanFactory beanFactory) {
        this.beanFactory = beanFactory;
    }

    @PostConstruct
    public void showInfo() {
        System.out.println("Bean name: " + beanName);
        System.out.println("BeanFactory: " + beanFactory.getClass().getName());
    }
}
```

The example requires imports:

```java
import org.springframework.beans.factory.BeanFactory;
import org.springframework.beans.factory.BeanFactoryAware;
import org.springframework.beans.factory.BeanNameAware;
```

`Aware` callbacks are part of the lifecycle. They are useful for infrastructure components or framework integration, but business services generally should not implement `ApplicationContextAware` to look up dependencies themselves. Prefer constructor injection for business dependencies.

Some callbacks such as `ApplicationContextAware` are handled by a Spring context BeanPostProcessor; therefore, do not assume every `Aware` interface is called within the same method or internal implementation.

## 7. BeanPostProcessor: Spring Intervenes Before and After Initialization

`BeanPostProcessor` is an important Spring extension point. It allows processing a bean instance before and after initialization callbacks.

Simplified interface:

```java
public interface BeanPostProcessor {

    Object postProcessBeforeInitialization(
            Object bean,
            String beanName
    );

    Object postProcessAfterInitialization(
            Object bean,
            String beanName
    );
}
```

Both methods can return the original bean or a wrapper/proxy object. Spring and integration libraries use this mechanism for many capabilities.

Examples of roles:

- Processing lifecycle annotations such as `@PostConstruct`.
- Creating proxies for AOP.
- Supporting certain injection annotations.
- Integrating specialized bean processing mechanisms.

You do not need to write a `BeanPostProcessor` yourself for regular services. But understanding it explains why the object your code receives after startup may be a proxy instead of the original instance.

### 7.1. Proxies can be created after initialization

For example, a service with `@Transactional` or `@Async` can be wrapped by Spring in a proxy through the appropriate post-processing infrastructure.

```text
Target object is instantiated
          │
          ▼
Dependency injection
          │
          ▼
Initialization callbacks
          │
          ▼
BeanPostProcessor after initialization
          │
          ▼
Proxy is returned to container/client
          │
          ▼
Calls pass through the proxy to apply advice
```

This is a conceptual model; proxies can be created at different points depending on the specific mechanism. The key takeaway is that the bean injected into a consumer may be a Spring-managed proxy, not necessarily the raw target object.

## 8. Initialization Callbacks: The Bean Completes Preparation

After dependencies are injected and before-initialization post-processing steps execute, Spring invokes initialization callbacks.

There are three common ways:

1. `@PostConstruct`.
2. `InitializingBean.afterPropertiesSet()`.
3. Custom init method declared via `@Bean(initMethod = "...")` or XML.

In the standard flow, the order is:

```text
Bean instance has been created
          │
          ▼
Dependencies have been supplied
          │
          ▼
Aware callbacks
          │
          ▼
BeanPostProcessor.beforeInitialization
          │
          ▼
@PostConstruct
          │
          ▼
InitializingBean.afterPropertiesSet()
          │
          ▼
Custom init method
          │
          ▼
BeanPostProcessor.afterInitialization
          │
          ▼
Bean ready
```

`@PostConstruct` is invoked through Spring's corresponding post-processing infrastructure, so it sits in the phase prior to the `InitializingBean` initialization callback.

### 8.1. `@PostConstruct`

Example:

```java
package com.example.demo.service;

import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Service;

@Service
public class CacheService {

    @PostConstruct
    public void initialize() {
        System.out.println("CacheService initialized");
    }
}
```

`@PostConstruct` marks a method that should run after dependency injection completes and before the bean is considered finished initializing.

Common characteristics:

- The method takes no parameters.
- Return type is `void`.
- It is not a constructor.
- It is not a place to inject dependencies.
- It can use dependencies that have already been injected.
- With Spring Boot 3, the annotation package is `jakarta.annotation.PostConstruct`.

`@PostConstruct` is suitable for lightweight preparation operations, such as checking internal state, populating small local cache data, or normalizing data structures after configuration has been injected.

Avoid performing long-running, hard-to-control, or external-system-dependent work in this callback if it makes startup fragile. For tasks that should run when the application is ready, consider `ApplicationRunner`, `CommandLineRunner`, or an appropriate application event.

### 8.2. `InitializingBean.afterPropertiesSet()`

Spring provides the interface:

```java
import org.springframework.beans.factory.InitializingBean;

public class SearchIndexService implements InitializingBean {

    @Override
    public void afterPropertiesSet() {
        System.out.println("SearchIndexService received all properties");
    }
}
```

Spring calls `afterPropertiesSet()` after dependency/property injection completes. It serves a similar purpose to `@PostConstruct`, but requires the class to implement a Spring interface.

This approach is useful in certain libraries or classes intentionally designed to integrate closely with Spring. For new business classes, `@PostConstruct` usually creates less framework coupling.

### 8.3. Custom init method with `@Bean`

You can declare a dedicated initialization method:

```java
public class LegacyClient {

    public void connect() {
        System.out.println("LegacyClient prepared");
    }
}
```

```java
@Configuration(proxyBeanMethods = false)
public class ClientConfiguration {

    @Bean(initMethod = "connect")
    public LegacyClient legacyClient() {
        return new LegacyClient();
    }
}
```

After Spring creates the bean and injects related dependencies, it calls the `connect()` method as a custom initialization callback.

A custom init method is useful when the class comes from an external library and you cannot add `@PostConstruct` or implement `InitializingBean` in that class.

The method specified as the init method must exist and have an appropriate signature; otherwise, bean creation may fail.

### 8.4. Should all three callbacks be used in one class?

Technically, a bean can participate in multiple callback types. Callback ordering matters when they coexist:

| Callback | Position in the initialization chain |
|---|---|
| `@PostConstruct` | Before `afterPropertiesSet()` |
| `InitializingBean.afterPropertiesSet()` | After `@PostConstruct` |
| Custom init method | After `afterPropertiesSet()` |

Do not split a single initialization operation into three places just to use every callback. Choose one appropriate mechanism so readers clearly see where the bean finishes preparing.

If you need to observe the order in an example, you can log in each callback:

```java
@Component
public class LifecycleProbe implements InitializingBean {

    @PostConstruct
    public void postConstruct() {
        System.out.println("1 - @PostConstruct");
    }

    @Override
    public void afterPropertiesSet() {
        System.out.println("2 - afterPropertiesSet");
    }

    public void customInit() {
        System.out.println("3 - custom init method");
    }
}
```

Declare `customInit` via `@Bean(initMethod = "customInit")` if the bean is created from a factory method. The illustrative output order is `1`, `2`, `3`.

## 9. A Constructor Is Not an Initialization Callback

Constructors and `@PostConstruct` differ in timing and purpose.

| Constructor | `@PostConstruct` |
|---|---|
| Creates the Java object | Finalizes preparation steps after injection |
| Constructor parameters can receive dependencies | Can use dependencies that were already injected |
| Runs before field/setter injection | Runs after injection |
| Used to establish initial required state | Used to perform initialization depending on the assembled bean |
| Not a callback defined by Spring | A lifecycle annotation processed by Spring |

Example:

```java
@Service
public class PricingService {

    private final TaxCalculator taxCalculator;
    private Map<String, BigDecimal> rates;

    public PricingService(TaxCalculator taxCalculator) {
        this.taxCalculator = taxCalculator;
        // Constructor dependency is already available here.
    }

    @PostConstruct
    public void loadRates() {
        // Can use taxCalculator and injected configuration.
        this.rates = Map.of(
                "STANDARD", new BigDecimal("0.10"),
                "REDUCED", new BigDecimal("0.05")
        );
    }
}
```

A constructor is suited for ensuring the object has its required dependencies. `@PostConstruct` is suited for steps that need to run after the container has assembled the object.

However, do not treat `@PostConstruct` as a full replacement for constructors. Core state that an object needs in order to exist validly should still be represented through the constructor whenever possible.

## 10. Beans Created with `@Bean` Also Have a Lifecycle

Not only classes annotated with `@Component` have a lifecycle. Objects returned from `@Bean` are also managed by the container.

Example:

```java
public class ReportClient {

    private final String endpoint;

    public ReportClient(String endpoint) {
        this.endpoint = endpoint;
    }

    public void initialize() {
        System.out.println("Connecting to " + endpoint);
    }

    public void close() {
        System.out.println("Closing client");
    }
}
```

```java
@Configuration(proxyBeanMethods = false)
public class ReportClientConfiguration {

    @Bean(initMethod = "initialize", destroyMethod = "close")
    public ReportClient reportClient() {
        return new ReportClient("https://reports.example.test");
    }
}
```

Spring manages the instance returned by the factory method and invokes the declared callbacks according to the lifecycle. A bean does not need `@Component` to be managed by the container.

If the factory method has parameters:

```java
@Bean
public ReportClient reportClient(AppProperties properties) {
    return new ReportClient(properties.reportEndpoint());
}
```

Spring resolves `AppProperties` before calling the `reportClient(...)` method. This is factory-method dependency injection, following the same dependency resolution principles as constructor injection.

## 11. Destruction Callbacks: When Is a Bean Destroyed?

When an ApplicationContext closes gracefully, Spring can invoke destruction callbacks for beans whose lifecycle the container manages.

Three common mechanisms:

1. `@PreDestroy`.
2. `DisposableBean.destroy()`.
3. Custom destroy method, such as `@Bean(destroyMethod = "close")`.

Typical sequence:

```text
ApplicationContext begins closing
          │
          ▼
Singleton bean needs destruction
          │
          ▼
@PreDestroy
          │
          ▼
DisposableBean.destroy()
          │
          ▼
Custom destroy method
          │
          ▼
Destruction callback completes
```

### 11.1. `@PreDestroy`

```java
package com.example.demo.service;

import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Service;

@Service
public class CacheService {

    @PreDestroy
    public void cleanup() {
        System.out.println("CacheService is cleaning up");
    }
}
```

Spring calls this callback during managed bean destruction when the context closes gracefully.

Appropriate tasks can include:

- Closing internal resources.
- Stopping an executor created and owned by the bean.
- Flushing buffered data as needed.
- Releasing handles or clients directly managed by the bean.

Do not rely on `@PreDestroy` as a mechanism guaranteed to run under every kind of process termination. If the machine powers off abruptly, the process is force-killed, or the JVM crashes, the callback may never get a chance to run.

### 11.2. `DisposableBean.destroy()`

```java
import org.springframework.beans.factory.DisposableBean;

public class LegacyResource implements DisposableBean {

    @Override
    public void destroy() {
        System.out.println("LegacyResource closed");
    }
}
```

This is Spring's callback interface. It suits certain framework-integrated classes, but creates a direct dependency on the Spring API.

### 11.3. Custom destroy method

Example:

```java
public class ExternalClient {

    public void close() {
        System.out.println("ExternalClient closed");
    }
}
```

```java
@Configuration(proxyBeanMethods = false)
public class ExternalClientConfiguration {

    @Bean(destroyMethod = "close")
    public ExternalClient externalClient() {
        return new ExternalClient();
    }
}
```

When the context closes and the bean is destroyed according to its lifecycle, Spring calls `close()`.

With `@Bean`, Spring can infer certain common destroy methods such as `close` or `shutdown` in appropriate cases. Explicit declaration lets readers see the intent clearly and avoids relying on inference when a class has multiple cleanup methods.

## 12. Order of Destruction Callbacks

If a bean uses all three approaches:

```java
@Component
public class ResourceManager implements DisposableBean {

    @PreDestroy
    public void preDestroy() {
        System.out.println("1 - @PreDestroy");
    }

    @Override
    public void destroy() {
        System.out.println("2 - DisposableBean.destroy");
    }

    public void closeResource() {
        System.out.println("3 - custom destroy method");
    }
}
```

If the custom method is configured appropriately, the typical order is:

```text
@PreDestroy
    ↓
DisposableBean.destroy()
    ↓
custom destroy method
```

Do not repeat the same resource-closing action across all three callbacks. If `@PreDestroy` has already closed a client, the custom destroy method should not close a resource that is no longer in a valid state again.

## 13. How Does an ApplicationContext Close?

With a closeable context, you can use `try-with-resources`:

```java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class ContextLifecycleExample {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            GreetingService service =
                    context.getBean(GreetingService.class);

            System.out.println(service.greet("Lan"));
        }

        // Context has been closed after exiting the try block.
    }
}
```

`AnnotationConfigApplicationContext` is a closeable context. Upon exiting `try`, `close()` is called and destruction callbacks of managed singletons can run.

In a Spring Boot web application, you do not close the context immediately after `SpringApplication.run(...)`, because the web server and application beans need to keep running.

Spring Boot typically registers a shutdown hook to close the ApplicationContext when the JVM terminates normally. In service/container environments, the operational runtime needs to give the process enough shutdown time for cleanup callbacks to complete.

### 13.1. Closing the context differs from manually destroying a bean

Do not retrieve a bean from the context and arbitrarily call `destroy()` or `close()` on it while the container is still managing that bean. Doing so can leave the bean still injected elsewhere even though its internal resources have already been closed.

Let the container manage destruction, or design a separate business API if you need to terminate a session/operation without terminating the singleton bean.

## 14. How Does Scope Affect the Lifecycle?

### 14.1. Singleton

`singleton` is the default scope. Within an IoC container, each singleton bean definition typically corresponds to one shared instance.

With a standard ApplicationContext, non-lazy singletons are typically created during context refresh. When the context closes gracefully, Spring invokes destruction callbacks for the singletons it manages.

```java
@Component
public class ApplicationCache {

    public ApplicationCache() {
        System.out.println("ApplicationCache constructor");
    }

    @PreDestroy
    public void close() {
        System.out.println("ApplicationCache destroyed");
    }
}
```

This is the type of bean commonly seen in Spring Boot applications.

Note: Spring's singleton is a singleton **per bean definition within one container**, not unique across the entire JVM. Two independent ApplicationContexts can have two instances with the same bean name.

### 14.2. Prototype

`@Scope("prototype")` instructs the container to create a new instance each time the bean is requested via the corresponding lookup mechanism:

```java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class TemporaryReport {
}
```

Spring performs creation and initialization callbacks for prototypes, then hands the object off to the client. **Spring does not automatically manage full destruction callbacks for prototypes** after handing out the object, because the container does not track the usage lifecycle of individual prototype instances.

If a prototype holds resources that need closing, the client receiving the object must take responsibility for cleanup or use an appropriate factory/lifecycle mechanism.

This is an important difference compared to singletons.

### 14.3. Request and session scopes

Web applications can use request or session scopes if the corresponding context and web infrastructure have been configured.

- `request`: an instance tied to a single HTTP request.
- `session`: an instance tied to an HTTP session.
- Other web scopes depending on the environment.

These beans have lifecycles dependent on requests/sessions, unlike singletons which live for the duration of the context.

If injecting a request-scoped bean into a singleton, Spring typically needs a proxy or an appropriate provider mechanism to access the right instance for the current request.

### 14.4. Comparison table of scope and destruction

| Scope | Instance rule | Initialization | Destruction |
|---|---|---|---|
| singleton | One instance per bean definition in the container | When the container creates the bean, typically eager during context refresh if not lazy | Container calls callbacks when the context closes gracefully |
| prototype | New instance each time requested from the container | Each instance is initialized per the corresponding lifecycle | Container does not automatically call destruction callbacks after handing out the instance |
| request | Instance per HTTP request | When request scope needs the bean | Follows the request and web context lifecycle |
| session | Instance per HTTP session | When session scope needs the bean | Follows the session and web context lifecycle |

Web scopes require an appropriate web environment; do not apply them in a plain BeanFactory without web scope infrastructure.

## 15. Lazy Initialization and When Constructors Run

Singleton beans are normally created early during ApplicationContext refresh if not marked lazy. With `@Lazy`, creation can be deferred until the bean is requested.

Example:

```java
@Component
@Lazy
public class ExpensiveSearchIndex {

    public ExpensiveSearchIndex() {
        System.out.println("Search index initialized");
    }
}
```

If no eager bean requires `ExpensiveSearchIndex` during startup and no code requests it, the constructor may not have run when context refresh finishes. The first time the bean is injected/looked up in a way that triggers creation, the container creates the instance.

However, `@Lazy` does not guarantee the constructor always runs late:

- Another eager singleton with a direct dependency on the lazy bean can require it during startup.
- A `getBean()` call in a startup callback can trigger bean creation.
- Lazy initialization can be configured at the application level, affecting many beans.

Therefore, **when a constructor runs depends on scope, the lazy flag, and the dependency graph**.

## 16. Circular Dependencies and Constructor Injection

A circular dependency occurs when two beans depend on each other:

```text
ServiceA needs ServiceB
      ▲       │
      │       ▼
      └──── ServiceB needs ServiceA
```

Example of a constructor cycle:

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

To create `ServiceA`, Spring needs `ServiceB`. To create `ServiceB`, Spring in turn needs `ServiceA`, while `ServiceA`'s constructor has not yet completed. The container cannot create both objects through this constructor chain and typically reports `BeanCurrentlyInCreationException` or a circular reference error wrapped in `UnsatisfiedDependencyException`.

Constructor injection makes the dependency graph explicit, so dependency cycles are usually detected early.

### 16.1. Should you switch to field/setter injection to bypass circular dependencies?

Some forms of circular dependencies via setters/fields can be resolved through early singleton reference mechanisms in certain Spring configurations. However, modern Spring Boot disallows circular references by default in many application configurations, and switching to setter injection solely to evade a dependency cycle usually hides a design issue.

A better approach is to analyze responsibilities:

- Extract shared logic into a third service.
- Convert one direction of dependency into an appropriate event or callback.
- Pass required data instead of having two services call each other.
- If a dependency is genuinely only needed at a later point, you can use `ObjectProvider<T>` or an intentional lazy mechanism, while understanding its lifecycle and semantics.

Do not use `@Lazy` as a default fix for every circular dependency. Design a clearly directed dependency graph.

## 17. Callbacks and Events After Beans Have Been Initialized

Not every operation after context startup belongs to an individual bean's lifecycle callback.

### 17.1. `SmartInitializingSingleton`

This interface provides the `afterSingletonsInstantiated()` callback after regular eager singletons have finished being created.

```java
@Component
public class StartupSummary implements SmartInitializingSingleton {

    @Override
    public void afterSingletonsInstantiated() {
        System.out.println("Eager singletons have been initialized");
    }
}
```

It suits infrastructure beans that need to observe state after eager singletons are created. This is not a callback replacing `@PostConstruct` for each bean.

### 17.2. `ApplicationRunner` and `CommandLineRunner`

Spring Boot provides two interfaces to run logic after the ApplicationContext has refreshed and before the application signals full readiness.

```java
@Component
public class StartupTasks implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Application has completed context refresh");
    }
}
```

`CommandLineRunner` has the method `run(String... args)`; `ApplicationRunner` receives `ApplicationArguments`.

Runners are suitable for application-level work after the context has initialized, such as controlled seed data loading or checking startup conditions. They are not initialization callbacks for individual beans.

### 17.3. Application events

ApplicationContext publishes events during its lifecycle, such as `ContextRefreshedEvent` when the context has refreshed and `ContextClosedEvent` when the context closes.

You can listen for them:

```java
@Component
public class ContextEventLogger {

    @EventListener
    public void onClosed(ContextClosedEvent event) {
        System.out.println("ApplicationContext is closing");
    }
}
```

Context events are container-level signals. Do not replace a bean's `@PreDestroy` with a context event listener if the goal is cleaning up a resource owned by that bean. Use the callback suited to the lifecycle scope.

## 18. Lifecycle Callbacks in Spring Boot 3

With Spring Boot 3, the ecosystem moved to the Jakarta namespace. Thus, common lifecycle annotations are imported from:

```java
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
```

Do not mistakenly use the old `javax.annotation.PostConstruct` or `javax.annotation.PreDestroy` packages in a Boot 3 application if current dependencies do not provide them.

Complete example:

```java
package com.example.demo.service;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Service;

@Service
public class ConnectionManager {

    private boolean initialized;

    public ConnectionManager() {
        System.out.println("1 - Constructor");
    }

    @PostConstruct
    public void initialize() {
        initialized = true;
        System.out.println("2 - PostConstruct");
    }

    public void execute() {
        if (!initialized) {
            throw new IllegalStateException("Bean is not ready");
        }
        System.out.println("Executing work");
    }

    @PreDestroy
    public void cleanup() {
        System.out.println("3 - PreDestroy");
        initialized = false;
    }
}
```

To compile, the project needs the Jakarta annotation API on the compile classpath. Spring Boot starters and dependencies may provide this API depending on configuration; if the compiler reports it cannot find package `jakarta.annotation`, verify whether the dependency is resolved.

## 19. Common Errors in Constructors, Injection, and Callbacks

| Symptom | Commonly related phase | Causes to check |
|---|---|---|
| `NoSuchBeanDefinitionException` | Dependency resolution | No bean matching type/name/qualifier |
| `NoUniqueBeanDefinitionException` | Dependency resolution | Multiple matching beans without a single one selected |
| `UnsatisfiedDependencyException` | Bean creation/injection | Constructor, field, setter, or factory method dependency could not be resolved |
| `BeanCurrentlyInCreationException` | Instantiation/dependency graph | Circular dependency or accessing a bean currently under creation |
| `BeanCreationException` | Various bean creation phases | Constructor, factory method, injection, or init callback failed |
| `NullPointerException` in constructor when using `@Autowired` field | Instantiation | Field injection has not happened yet |
| `NoSuchMethodException` or init method error | Initialization | Custom init method name does not exist or signature is incompatible |
| Exception in `@PostConstruct` | Initialization | Callback logic failed; bean did not complete creation |
| Resources not closed on shutdown | Destruction | Context did not close gracefully, callback not registered, or bean scope does not have container-managed destruction |
| Prototype does not call `@PreDestroy` automatically | Destruction | Container does not track prototype lifecycle after handing out the instance |

### 19.1. Reading the `Caused by` chain

A dependency error can be wrapped in multiple layers:

```text
BeanCreationException:
  Error creating bean with name 'checkoutService'

Caused by: UnsatisfiedDependencyException:
  Error creating bean with name 'checkoutService'

Caused by: NoUniqueBeanDefinitionException:
  No qualifying bean of type 'PaymentGateway'
  available: expected single matching bean but found 2
```

The first line tells you which bean failed. The deepest cause tells you Spring could not pick a single `PaymentGateway`. Troubleshooting must focus on candidates/qualifiers/primary rather than editing the `@PostConstruct` callback.

### 19.2. Constructor throws an exception

If a constructor throws an exception:

```java
@Component
public class FileIndex {

    public FileIndex() {
        throw new IllegalStateException("Cannot create index");
    }
}
```

the bean is not created successfully; beans that depend on it can also fail. If initialization logic needs injected dependencies, you cannot put it in the constructor while expecting field/setter injection to have already completed.

Consider `@PostConstruct`, an init method, or an application-level runner/event depending on the goal, and handle errors intentionally.

### 19.3. Exception in `@PostConstruct`

If an initialization callback fails, Spring considers the bean's initialization incomplete. Context refresh may stop and the application may fail to start up.

Therefore, this callback should have a clear scope, handle errors reasonably, and avoid performing unnecessarily long tasks. For tasks that can be retried or depend on external services, design a separate operational workflow rather than forcing every startup to complete that task immediately.

## 20. Complete Example Tracing Lifecycle Order

We create an illustrative bean with constructor, setter injection, initialization callbacks, and destruction. The example uses setter injection to make injection timing easy to observe; in real business code, constructor injection is generally preferred for required dependencies.

```java
package com.example.demo.lifecycle;

import org.springframework.stereotype.Component;

@Component
public class LifecycleDependency {

    public LifecycleDependency() {
        System.out.println("A - Dependency constructor");
    }

    public void use() {
        System.out.println("Dependency is ready");
    }
}
```

```java
package com.example.demo.lifecycle;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

@Component
public class LifecycleProbe implements InitializingBean {

    private LifecycleDependency dependency;

    public LifecycleProbe() {
        System.out.println("B - Probe constructor");
    }

    @Autowired
    public void setDependency(LifecycleDependency dependency) {
        this.dependency = dependency;
        System.out.println("C - Setter injection");
    }

    @PostConstruct
    public void postConstruct() {
        System.out.println("D - @PostConstruct");
        dependency.use();
    }

    @Override
    public void afterPropertiesSet() {
        System.out.println("E - afterPropertiesSet");
    }

    public void customInit() {
        System.out.println("F - Custom init");
    }

    @PreDestroy
    public void preDestroy() {
        System.out.println("G - @PreDestroy");
    }

    public void customDestroy() {
        System.out.println("H - Custom destroy");
    }
}
```

Register custom init/destroy methods if you want to trace those two callbacks using an appropriate bean definition, or switch the class to `@Bean` configuration with `initMethod`/`destroyMethod`. If the class is already component-scanned, choose a single bean registration path to avoid registering the same class from two sources.

A clean way to separate them is using a factory method:

```java
@Configuration(proxyBeanMethods = false)
public class LifecycleConfiguration {

    @Bean(initMethod = "customInit", destroyMethod = "customDestroy")
    public LifecycleProbe lifecycleProbe() {
        return new LifecycleProbe();
    }
}
```

In this case, remove `@Component` on `LifecycleProbe` to avoid registering that class via component scan simultaneously with `@Bean`. The bean still receives setter injection and the corresponding callbacks.

Conceptual log output when the context is refreshed and then closed:

```text
A - Dependency constructor
B - Probe constructor
C - Setter injection
D - @PostConstruct
Dependency is ready
E - afterPropertiesSet
F - Custom init

... application uses the bean ...

G - @PreDestroy
H - Custom destroy
```

Log order between different beans depends on the dependency graph and initialization order. The example above only describes the lifecycle relationship inside one bean and its dependency; do not rely on alphabetical order of class names to guess creation order across every bean in the application.

## 21. Lifecycle Design Principles in Spring Boot Projects

When building services, apply the following principles:

- **Constructor:** establish required state and receive required dependencies through parameters.
- **Constructor injection:** use for most dependencies of services/controllers/repositories.
- **Setter/field injection:** use only when there is a clear reason; setters are better suited for optional dependencies or mutable configuration.
- **`@PostConstruct`:** use for short preparation steps that need to run after dependencies have been injected.
- **`InitializingBean`/custom init method:** use when integrating with Spring interfaces or external classes, while avoiding multiple mechanisms doing the same job.
- **`@PreDestroy`/destroy method:** close resources owned by the bean when the container ends the lifecycle.
- **Prototype:** manage resource release yourself after receiving the instance.
- **`ApplicationRunner`/`CommandLineRunner`:** use for application-level work after context refresh, not in place of per-bean callbacks.
- **Circular dependency:** review the dependency graph design before using lazy/provider or changing injection style.

A bean has an easy-to-understand lifecycle when each phase has a clear responsibility: the constructor receives required dependencies, the container assembles the object, initialization completes preparation, the bean serves the application, and destruction releases resources.

## 22. Practice Exercises

### Exercise 1 — Observe constructor injection

Create `MessageFormatter` and `GreetingService`. Register them as beans, use constructor injection, and log inside constructors. Observe the dependency being created before the bean that needs it.

### Exercise 2 — Compare setter injection

Switch a dependency to setter injection. Log in the constructor, setter, and `@PostConstruct`. Record the order to see that the object is instantiated before the setter is called.

### Exercise 3 — Observe initialization callback order

Create a bean implementing `InitializingBean`, add `@PostConstruct`, and declare a custom init method. Log in each callback. Observe the callback order on the same bean.

### Exercise 4 — Observe destruction

Add `@PreDestroy` and a custom destroy method. Run the application with a closeable context, call `close()`, or use `try-with-resources`. Observe the bean destruction logs.

### Exercise 5 — Compare singleton and prototype

Create two beans of the same class, one singleton and one prototype. Request each bean twice, comparing identity and constructor logs. Add `@PreDestroy` and observe the difference when the context closes; clean up prototype instances appropriately yourself.

### Exercise 6 — Try a circular dependency

Create `ServiceA` requiring `ServiceB` via constructor and vice versa. Observe the error when the context initializes. Then split responsibilities or move shared logic to a third service to eliminate the dependency cycle.

### Exercise 7 — Distinguish init callbacks from application startup tasks

Create `@PostConstruct` in one bean and `ApplicationRunner` in another bean. Log to observe the bean's callback occurring during initialization, while the runner executes after the context has refreshed.

### Exercise 8 — Trace errors in callbacks

Intentionally throw an exception in `@PostConstruct`, observe context startup failing, and read the `Caused by` chain. Restore the code, then try throwing an exception in the runner to compare the error's location and meaning.

After these exercises, you should be able to distinguish **constructors creating objects**, **dependency injection assembling objects**, **initialization callbacks finalizing beans**, and **destruction callbacks cleaning up beans**. This is the foundation for reading Spring Boot logs, designing services with clear dependencies, and managing resources properly within the IoC container lifecycle.
