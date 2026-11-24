# Constructors, Dependency Injection, and Aware Callbacks in the Spring Boot Bean Lifecycle

## 1. Position in the bean lifecycle

In Spring Boot, a **bean** is an object managed by the container according to a bean definition. The container does not just call a constructor: it chooses how to instantiate the object, resolves dependencies, injects fields/setters when needed, invokes infrastructure and initialization callbacks, and only then exposes the bean for other components to use.

Three concepts to distinguish:

- **Constructor** is the method that initializes a Java object. With constructor injection, Spring must supply the input dependencies in order to invoke the constructor.
- **Dependency injection (DI)** is the mechanism by which the container provides collaborators to a bean via constructors, setters, fields, or factory method parameters. It saves the bean from having to locate and create its own dependencies.
- **Aware callbacks** are special interfaces a bean can implement to receive container information or infrastructure, such as the bean name, `BeanFactory`, `ApplicationContext`, or `Environment`. These callbacks occur after the constructor has completed.

~~~mermaid
flowchart TD
  A["BeanDefinition has been registered"] --> B["Select constructor, resolve dependencies"]
  B --> C["Create instance via constructor / factory method"]
  C --> D["Inject fields, setters, and required properties"]
  D --> E["BeanNameAware, BeanFactoryAware..."]
  E --> F["Pre-init BeanPostProcessor, context Aware, @PostConstruct"]
  F --> G["InitializingBean.afterPropertiesSet, custom init-method"]
  G --> H["Post-init BeanPostProcessor, may create AOP proxy"]
  H --> I["Bean ready to be injected/used"]
  I --> J["When scope/context ends: appropriate destroy callback"]
~~~

This is the logical order for a **typical singleton bean** in a Spring `ApplicationContext`. With `@Bean` factory methods, other scopes, lazy beans, `FactoryBean`, custom bean post-processors, or proxies, some details may differ. The diagram also does **not** guarantee the initialization order across all beans in the entire application.

An important consequence: if you store `ApplicationContext` in a field via `ApplicationContextAware.setApplicationContext(...)`, that field **does not yet have** a value inside the same bean's constructor.

## 2. What is constructor injection and why is it recommended?

Consider a service that needs a repository:

~~~java
package com.example.orders;

import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public String describe(long id) {
        return repository.describe(id);
    }
}
~~~

This is a partial illustrative snippet: the project must have a matching `OrderRepository` interface or class to compile. When creating `OrderService`, the container selects the constructor, locates the `OrderRepository` bean, creates or retrieves that bean, and passes the reference into the constructor.

Constructor injection provides these benefits:
1. Required dependencies appear in the signature: a valid object cannot be created without supplying its collaborators.
2. Fields can be declared `final`, making references immutable and easier to reason about.
3. Unit tests can pass fakes/stubs directly into the constructor without spinning up a container just to set fields.
4. Missing beans or circular dependencies surface early, while Spring is creating the bean.
5. A constructor with too many parameters exposes a sign that the class has too many responsibilities.

Spring Boot recommends constructor injection for Spring-managed components.

### Single constructor vs. multiple constructors

With **a single constructor**, modern Spring uses that constructor automatically; you do not need to add `@Autowired`. With **multiple constructors**, you must follow Spring's constructor selection rules and typically mark the desired constructor with `@Autowired`.

~~~java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

@Service
class BillingService {
    private final BillingRepository repository;

    @Autowired
    BillingService(BillingRepository repository) {
        this.repository = repository;
    }

    BillingService() {
        this.repository = null;
    }
}
~~~

The snippet above only illustrates constructor selection and requires a `BillingRepository` definition; you **should not** use a design that allows creating a service without its required dependency. In new applications, keeping a single clear constructor is usually better.

### When multiple beans have the same type

Suppose `CardGateway` and `BankGateway` both implement `PaymentGateway`. If a service simply requests a `PaymentGateway` without a sufficiently clear selection rule, the container may throw `NoUniqueBeanDefinitionException`.

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
class CheckoutService {
    private final PaymentGateway gateway;

    CheckoutService(@Qualifier("cardGateway") PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

This snippet requires the `PaymentGateway` interface and a bean registered under the name `cardGateway`; it is not a standalone program. `@Qualifier` selects a candidate at the injection point, while `@Primary` can mark a default implementation. Both relate to **dependency selection**, not Aware callbacks, and neither allows two bean definitions with duplicate names.

### Handling potentially missing dependencies

If a collaborator is genuinely optional, you can use `Optional<T>` or `ObjectProvider<T>`; if you need a collection of strategies, you can inject `List<T>` or `Map<String,T>`. Example:

~~~java
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

@Service
class AuditFacade {
    private final ObjectProvider<AuditWriter> writer;

    AuditFacade(ObjectProvider<AuditWriter> writer) {
        this.writer = writer;
    }

    void record(String event) {
        AuditWriter available = writer.getIfAvailable();
        if (available != null) {
            available.write(event);
        }
    }
}
~~~

An `AuditWriter` must be provided if using this snippet. `ObjectProvider` defers obtaining the actual object until invocation time; if multiple candidates exist without an appropriate selection rule, lookup can still fail for non-uniqueness. Do not use a provider to hide critical dependencies.

### Setter and field injection

| Mechanism | Timing | Appropriate use | Limitations |
| --- | --- | --- | --- |
| Constructor injection | During instance creation | Required dependencies, `final` fields | Constructor cycles have no valid resolution order |
| Setter injection | After the object exists | Optional/reconfigurable dependencies | Object state may be incomplete before the setter runs |
| Field injection via `@Autowired` | After the constructor during population/post-processing | Seen in legacy code or tests | Hard to test in plain Java, obscures constructor requirements |
| `@Bean` factory method parameters | When the container invokes the factory method | Registering objects from external libraries | Must resolve factory parameters like any other dependency |

A setter with `@Autowired` by default **does not** mean optional: the container still requires a matching dependency unless configured as optional per the API contract.

### Constructor time is very early

In a bean constructor, stick to validating parameters, assigning fields, and establishing simple invariants. Avoid starting long business flows, calling remote APIs, looking up beans from the context yourself, or assuming fields injected later already have values. If you call an `@Transactional` or `@Async` method on the bean itself from its constructor, you cannot assume a proxy is ready to apply interception.

## 3. Aware callbacks: a bean receives Spring infrastructure info

The `Aware` interfaces tell a bean information that only the container can accurately provide. They are not a general-purpose mechanism for resolving all business dependencies.

| Interface | Callback | Information received | Common use case |
| --- | --- | --- | --- |
| `BeanNameAware` | `setBeanName(String name)` | Registered bean name | Diagnostics or infrastructure beans needing their identifier |
| `BeanClassLoaderAware` | `setBeanClassLoader(ClassLoader loader)` | ClassLoader used for bean classes | Class/resource loading mechanisms in libraries |
| `BeanFactoryAware` | `setBeanFactory(BeanFactory factory)` | BeanFactory managing the bean | Infrastructure extensions working with the factory |
| `ApplicationContextAware` | `setApplicationContext(ApplicationContext context)` | Context managing the bean | Framework integration, special lookups |
| `EnvironmentAware` | `setEnvironment(Environment env)` | Property sources and profiles | Infrastructure components needing configuration state |
| `ResourceLoaderAware` | `setResourceLoader(ResourceLoader loader)` | Resource loader | Libraries resolving classpath/URL resources |
| `ApplicationEventPublisherAware` | `setApplicationEventPublisher(ApplicationEventPublisher publisher)` | Event publisher | Infrastructure publishing events via the context |
| `MessageSourceAware` | `setMessageSource(MessageSource messages)` | Message/i18n service | Message lookup in extensions |
| `ServletContextAware` | `setServletContext(ServletContext context)` | Current servlet context | Servlet web applications/integrations |

`ServletContextAware` only applies if a servlet context exists; command-line or purely reactive applications do not necessarily have a servlet context. With Spring Boot 3.x, Servlet APIs use the `jakarta.servlet.*` package, unlike many older articles that use `javax.servlet.*`.

### BeanNameAware

~~~java
import org.springframework.beans.factory.BeanNameAware;
import org.springframework.stereotype.Component;

@Component("shipmentRouter")
class ShipmentRouter implements BeanNameAware {
    private String beanName;

    @Override
    public void setBeanName(String name) {
        this.beanName = name;
    }

    String getRegisteredName() {
        return beanName;
    }
}
~~~

After the container invokes the callback, the received name is `shipmentRouter`. Inside this class's constructor, `beanName` has not yet been assigned by `setBeanName`. Do not confuse bean name with simple class name: the name may be set by `@Component("...")`, `@Bean(name=...)`, or another naming strategy.

### BeanFactoryAware and ApplicationContextAware

~~~java
import org.springframework.beans.BeansException;
import org.springframework.beans.factory.BeanFactory;
import org.springframework.beans.factory.BeanFactoryAware;
import org.springframework.context.ApplicationContext;
import org.springframework.context.ApplicationContextAware;
import org.springframework.stereotype.Component;

@Component
class InfrastructureAdapter
        implements BeanFactoryAware, ApplicationContextAware {
    private BeanFactory beanFactory;
    private ApplicationContext applicationContext;

    @Override
    public void setBeanFactory(BeanFactory factory)
            throws BeansException {
        this.beanFactory = factory;
    }

    @Override
    public void setApplicationContext(ApplicationContext context)
            throws BeansException {
        this.applicationContext = context;
    }
}
~~~

Bean factory is the mechanism for managing and looking up beans. `ApplicationContext` provides a broader API—beyond bean lookup, it offers event publication, resource/message access, and application-level capabilities.

`BeanNameAware`, `BeanClassLoaderAware`, and `BeanFactoryAware` callbacks are typically invoked directly by the bean factory during initialization. Context-oriented Aware interfaces such as `ApplicationContextAware` are handled by Spring's `ApplicationContext` via a processor. They occur **before initialization callbacks**, but you should not infer that every custom Aware implementation shares one fixed order.

## 4. How does Aware differ from dependency injection?

You can obtain `Environment` in two different ways:

~~~java
// Option 1: Aware callback, called by Spring after the bean is created
class RuntimeAware implements EnvironmentAware {
    private Environment environment;

    @Override
    public void setEnvironment(Environment environment) {
        this.environment = environment;
    }
}
~~~

~~~java
// Option 2: constructor injection, available directly inside the constructor
@Component
class RuntimeConsumer {
    private final Environment environment;

    RuntimeConsumer(Environment environment) {
        this.environment = environment;
    }
}
~~~

Both snippets require appropriate imports from `org.springframework.context`, `org.springframework.core.env`, and `org.springframework.stereotype` if placed in separate files.

If a service only needs a configuration value such as timezone or retry limit, `@ConfigurationProperties` is usually clearer than holding the entire `Environment`. If a service only needs another bean, inject **that bean itself**.

| Criterion | Constructor injection | Aware callback |
| --- | --- | --- |
| When the object is received | Inside the constructor | After the constructor returns |
| Where dependencies are expressed | Constructor signature | Implemented callback interface |
| Primary purpose | Collaboration between beans | Connecting to container infrastructure |
| Plain Java unit tests | Pass fakes/stubs directly | Must simulate the callback if logic truly relies on it |
| Risk of overuse | Bloated constructors | Deep coupling to Spring, service-locator pattern |

**Rule of thumb:** Aware is meant for specific infrastructure needs. Having a business service implement `ApplicationContextAware` just to call `getBean(Repository.class)` usually makes code harder to understand than injecting `Repository` via the constructor.

## 5. Exact order: BeanPostProcessor and initialization callbacks

For a typical bean, after instantiation and dependency population:

1. The bean factory invokes basic Aware callbacks such as `setBeanName` and `setBeanFactory`.
2. `BeanPostProcessor.postProcessBeforeInitialization` methods run. In a standard context, `ApplicationContextAwareProcessor` handles applicable context callbacks, while the Jakarta annotations processor can invoke `@PostConstruct`.
3. If the bean implements `InitializingBean`, Spring calls `afterPropertiesSet()`.
4. If the bean definition specifies a custom `initMethod`, Spring calls that method.
5. Bean post-processors run the post-initialization phase via `postProcessAfterInitialization`; components such as AOP may return a proxy.

When a bean configures all **three differently named initialization hooks** (annotation, interface, and custom init method), the order documented by Spring Framework is:

~~~text
@PostConstruct
InitializingBean.afterPropertiesSet()
custom init-method
~~~

With Spring Boot 3.x / Spring Framework 6.x, the annotation import is:

~~~java
import jakarta.annotation.PostConstruct;
~~~

Do not copy `javax.annotation.PostConstruct` from old Java EE examples and expect it to compile as-is in Boot 3.x.

### Is @PostConstruct when the whole app is ready?

No. `@PostConstruct` belongs to the lifecycle of **a single bean**. It may be called during `ApplicationContext.refresh()` while many other beans have not yet finished initializing. This is the right time to validate configuration or prepare lightweight internal structures, not to run long batches or signal that the entire application is ready.

Spring Boot runners (`ApplicationRunner` / `CommandLineRunner`) run after refresh and before `ApplicationReadyEvent`. If the work depends on many beans being ready or requires a startup process, a runner or an appropriate lifecycle/event hook may be clearer than an Aware callback.

### Why shouldn't you call @Transactional methods in @PostConstruct?

An AOP proxy may be created during `BeanPostProcessor.postProcessAfterInitialization`. Calling a `@Transactional` method from a constructor, `@PostConstruct`, or via `this.method()` on the same bean does not guarantee passing through the proxy. This is a common reason logic that appears transactional fails to receive interception as expected.

## 6. Complete example for Java 17+ and Spring Boot 3.5.x

The project below uses the core Spring Boot starter, Maven, and Java 17+. It has **two component beans** and a `CommandLineRunner`. We observe the callback order **on the same bean** without running an HTTP server.

Structure:

~~~text
bean-lifecycle-demo/
├── pom.xml
└── src/main/java/com/example/lifecycle/
    ├── LifecycleDemoApplication.java
    ├── GreetingCatalog.java
    └── LifecycleReportService.java
~~~

**File `pom.xml`:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>bean-lifecycle-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**File `src/main/java/com/example/lifecycle/LifecycleDemoApplication.java`:**

~~~java
package com.example.lifecycle;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class LifecycleDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(LifecycleDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner showResult(LifecycleReportService service) {
        return args ->
                System.out.println("07.runner=" + service.message());
    }
}
~~~

**File `src/main/java/com/example/lifecycle/GreetingCatalog.java`:**

~~~java
package com.example.lifecycle;

import org.springframework.stereotype.Component;

@Component
public class GreetingCatalog {
    public String greeting() {
        return "Hello Spring";
    }
}
~~~

**File `src/main/java/com/example/lifecycle/LifecycleReportService.java`:**

~~~java
package com.example.lifecycle;

import jakarta.annotation.PostConstruct;
import org.springframework.beans.BeansException;
import org.springframework.beans.factory.BeanFactory;
import org.springframework.beans.factory.BeanFactoryAware;
import org.springframework.beans.factory.BeanNameAware;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.context.ApplicationContext;
import org.springframework.context.ApplicationContextAware;
import org.springframework.stereotype.Service;

@Service("lifecycleReportService")
public class LifecycleReportService
        implements BeanNameAware, BeanFactoryAware,
                   ApplicationContextAware, InitializingBean {

    private final GreetingCatalog catalog;
    private String beanName;
    private ApplicationContext applicationContext;

    public LifecycleReportService(GreetingCatalog catalog) {
        this.catalog = catalog;
        System.out.println("01.constructor=" + catalog.greeting());
    }

    @Override
    public void setBeanName(String name) {
        this.beanName = name;
        System.out.println("02.beanName=" + name);
    }

    @Override
    public void setBeanFactory(BeanFactory factory)
            throws BeansException {
        System.out.println("03.beanFactory="
                + factory.containsBean("greetingCatalog"));
    }

    @Override
    public void setApplicationContext(ApplicationContext context)
            throws BeansException {
        this.applicationContext = context;
        System.out.println("04.applicationContext="
                + context.containsBean("greetingCatalog"));
    }

    @PostConstruct
    void initialize() {
        if (beanName == null || applicationContext == null) {
            throw new IllegalStateException("Aware callbacks missing");
        }
        System.out.println("05.postConstruct");
    }

    @Override
    public void afterPropertiesSet() {
        System.out.println("06.afterPropertiesSet");
    }

    public String message() {
        return catalog.greeting();
    }
}
~~~

Run in the directory containing `pom.xml`:

~~~bash
mvn -q -DskipTests package
java -jar target/bean-lifecycle-demo-0.0.1-SNAPSHOT.jar
~~~

**Lines actively printed by the example program, in relative order:**

~~~text
01.constructor=Hello Spring
02.beanName=lifecycleReportService
03.beanFactory=true
04.applicationContext=true
05.postConstruct
06.afterPropertiesSet
07.runner=Hello Spring
~~~

Spring Boot may print additional startup logs depending on version and configuration; the block above is not the entire stdout.

Explanation:
1. Spring creates `GreetingCatalog` and passes the instance to the `LifecycleReportService(GreetingCatalog)` constructor. Because the service has one constructor, `@Autowired` is unnecessary.
2. `@Service("lifecycleReportService")` registers an explicit name, so `setBeanName` receives the string `lifecycleReportService`.
3. `setBeanFactory` receives the factory managing the bean; `containsBean("greetingCatalog")` is `true` because the catalog bean has already been registered to satisfy the constructor dependency.
4. `setApplicationContext` receives the context managing the bean; in a typical context, the catalog can also be looked up by name.
5. `@PostConstruct` checks the two callback fields before reporting successful initialization.
6. `afterPropertiesSet` runs after `@PostConstruct`.
7. `CommandLineRunner` is invoked after a successful refresh to use the fully initialized service.

**Regarding ordering:** lines `01`–`06` illustrate a single specific bean in the configuration above. If custom bean post-processors, special hooks, lazy flags, other scopes, or AOP are added, interactions become more complex. Do not rely on this example to impose a global order across all beans.

## 7. Refactoring the example to a typical production design

The demo's goal was to make Aware callbacks visible. A simple business service may only need constructor injection:

~~~java
package com.example.lifecycle;

import java.util.Objects;
import org.springframework.stereotype.Service;

@Service
public class WelcomeService {
    private final GreetingCatalog catalog;

    public WelcomeService(GreetingCatalog catalog) {
        this.catalog = Objects.requireNonNull(catalog);
    }

    public String welcome(String name) {
        return catalog.greeting() + ", " + name;
    }
}
~~~

There is no need to hold `ApplicationContext` just to call `getBean(GreetingCatalog.class)`; Spring already injected `GreetingCatalog` into the constructor. You can test it in plain Java with a snippet inside a method or test class:

~~~java
WelcomeService service = new WelcomeService(new GreetingCatalog());
System.out.println(service.welcome("Lan"));
~~~

Output:

~~~text
Hello Spring, Lan
~~~

This approach makes dependencies explicit and makes it easy to construct a fake catalog in tests. If you only need `Environment`, `ApplicationEventPublisher`, or `ResourceLoader`, you can also inject **that narrow interface** via the constructor instead of implementing a series of Aware callbacks.

## 8. Variations and exceptions to understand

### Beans from @Bean factory methods

Not every bean is created via component scanning. Example:

~~~java
@Configuration
class ClockConfiguration {
    @Bean
    java.time.Clock utcClock() {
        return java.time.Clock.systemUTC();
    }

    @Bean
    TimeService timeService(java.time.Clock clock) {
        return new TimeService(clock);
    }
}
~~~

The example is valid only if you add `@Configuration`/`@Bean` imports and the corresponding `TimeService` class. The container resolves the `clock` parameter before invoking the factory method. The returned object can still have appropriate lifecycle callbacks applied by the container.

### Singleton, prototype, and lazy beans

- **Singleton:** normally only one instance exists per bean definition per container. Non-lazy singletons are typically initialized during refresh; they may be created earlier if needed by another dependency.
- **Prototype:** each request to create an instance can re-run the constructor, injection, and init callbacks. The container does not automatically manage all destroy callbacks for a prototype after handing the object to the client.
- **Lazy:** defers instance creation until the bean is genuinely needed; a different log order from eager examples does not imply a bug.

### Failing constructors and uninvoked callbacks

If a constructor throws an exception, the container cannot proceed with normal bean initialization, so `setBeanName` or `@PostConstruct` on that bean will not be called. If a `@PostConstruct` callback throws an exception, the bean may not be exposed to consumers. You must read the stack trace to identify the **actual phase** that failed.

### Proxies and self-invocation

The bean seen by consumers may be an AOP-generated proxy, different from the original object that ran the constructor and init callbacks. When a bean calls `this.someTransactionalMethod()`, the internal call does not automatically pass through the proxy. This is the difference between Java object lifecycle and Spring advice semantics.

### Constructor dependency cycles

~~~text
ReportService -> AuditService -> ReportService
~~~

If both need each other right in their constructors, the container has no complete object to continue building. Spring typically reports an error related to `BeanCurrentlyInCreationException`, sometimes wrapped in `UnsatisfiedDependencyException`. To fix it properly, extract shared responsibilities, invert a dependency, or move orchestration to an independent layer. Do not expect `spring.main.allow-circular-references=true` to resolve constructor-to-constructor cycles.

## 9. Diagnosing common errors

| Symptom | Likely cause | How to resolve |
| --- | --- | --- |
| Constructor has no bean to inject | Bean unregistered, outside component scan, excluded by `@Profile`/conditional | Check package, configuration, and conditions; read nested cause |
| Multiple beans for the same interface | Ambiguous candidate | Use `@Qualifier`/`@Primary` by design or inject a collection if truly needed |
| `ApplicationContext` field is null in constructor | `ApplicationContextAware` callback has not run yet | Inject dependencies into constructor; use context after callback |
| Bean name is not what was expected | `@Bean(name=...)`/`@Component("...")` or naming strategy | Rely on `setBeanName` callback when the name is genuinely needed |
| `@PostConstruct` not called when using `new` | Object bypassed the Spring container | Let Spring manage the bean instead of instantiating it directly |
| I/O in Aware callback hangs startup | Accessing beans/external systems too early | Keep callbacks to lightweight infrastructure setup; use runners/lifecycle hooks otherwise |
| `@Transactional` has no effect during init | Target/proxy not used as expected | Call via collaborator/proxy after init, avoid self-invocation |
| `javax.annotation.PostConstruct` fails to compile | Using legacy namespace with Boot 3.x | Switch to `jakarta.annotation.PostConstruct` |
| Constructor dependency cycle | A needs B, B needs A to instantiate | Refactor dependency graph, split interfaces/orchestrator |
| Constructor log appears only some times | Bean scope or lazy | Check singleton/prototype and request timing |
| Context refresh fails before runner executes | Exception in constructor/injection/init | Inspect the first cause in logs and fix before looking at runners |

### Why shouldn't Aware be used instead of DI design?

Implementing `ApplicationContextAware` and calling `getBean(...)` throughout business code hides dependency relationships inside methods. Unit tests must mock the context and can easily miss missing-bean issues. For required collaborators, constructor injection makes requirements explicit. Aware still has a place in infrastructure extensions, when used for its intended purpose.

### Difference between initializing one bean and application readiness

`@PostConstruct` and `InitializingBean.afterPropertiesSet` reflect only the initialization of **that individual object**. `ApplicationReadyEvent` belongs to the startup lifecycle of the **entire Spring Boot application** after all runners complete successfully. An Aware callback likewise does not prove that databases, HTTP listeners, or external components are ready.

## 10. Knowledge self-check

**Question 1:** Does a `@Service` with a single constructor requiring `UserRepository` have to be annotated with `@Autowired`?  
**Answer:** No, modern Spring recognizes a single constructor and resolves its dependencies automatically.

**Question 2:** Does `setApplicationContext(...)` run before or after the constructor?  
**Answer:** After. The constructor cannot read fields that are only assigned in this callback.

**Question 3:** Why is `@Qualifier("cardGateway")` useful?  
**Answer:** It selects a candidate when multiple beans share the same type; it does not replace Aware mechanisms.

**Question 4:** Does a bean created directly with `new` automatically receive `BeanFactoryAware`?  
**Answer:** No; only objects going through the container's managed lifecycle receive callbacks that way.

**Question 5:** What is the order between `@PostConstruct` and `afterPropertiesSet()`?  
**Answer:** In standard configuration, `@PostConstruct` is called before `InitializingBean.afterPropertiesSet()`.

**Question 6:** When you need to read a property in a service, is implementing `EnvironmentAware` mandatory?  
**Answer:** No; you can inject `Environment` or use `@ConfigurationProperties` as needed.

**Question 7:** Does a constructor cycle A → B → A disappear if you enable the flag allowing circular references?  
**Answer:** No; constructor-to-constructor cycles cannot complete automatically.

**Question 8:** Why are Aware callbacks unsuitable for running a long job at application start?  
**Answer:** They run during bean creation, possibly before many other beans, making startup hard to control; use an appropriate lifecycle hook instead.

**Question 9:** Why does the example print `03.beanFactory=true`?  
**Answer:** The `greetingCatalog` bean has already been registered and resolved to create the service's dependency.

**Question 10:** Can a bean be returned as an AOP proxy instead of the original instance?  
**Answer:** Yes. Post-initialization BeanPostProcessors can wrap the target in a proxy.

## 11. Official documentation

- [Spring Boot — Spring Beans and Dependency Injection](https://docs.spring.io/spring-boot/reference/using/spring-beans-and-dependency-injection.html)
- [Spring Framework — Dependency Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html)
- [Spring Framework — Using @Autowired](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html)
- [Spring Framework — Customizing the Nature of a Bean](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring Framework — BeanPostProcessor Extension Points](https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html)
- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)

Examples use Spring Boot 3.5.x, Java 17+, and the Jakarta namespace. For other Spring Boot or Spring Framework versions, verify actual dependencies and version-matched APIs before applying.