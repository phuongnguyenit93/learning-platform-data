# Definition Registration, Instantiation, Dependency Injection, and Initialization

In a Spring Boot application, a developer can write an `OrderService` class, annotate it with `@Service`, declare a constructor accepting `OrderRepository`, and use that service inside a controller without writing chains of `new` statements themselves. This happens thanks to the **Spring IoC container**: the Spring Framework component responsible for managing registered objects, resolving dependency relationships, and coordinating part of their lifecycle.

However, four distinct tasks are very easily conflated into one:

1. **Definition registration:** telling the container *there is a bean to manage* and what the rules for creating it are.
2. **Instantiation:** actually creating an instance of the class or invoking a factory method to obtain an object.
3. **Dependency injection:** supplying the collaborators that the bean needs.
4. **Initialization:** running callbacks or setup logic after the bean already has its required dependencies.

These phases are related yet not identical. **Having a `BeanDefinition` does not mean the bean has been created; having run the constructor does not mean the bean has finished initialization; Spring Boot starting successfully does not mean all beans have been created in every configuration.**

This lesson describes the stages from when Spring Boot starts until a bean is ready to serve the application, illustrated using Java 21 and Spring Boot 3.x.

## 1. Foundational Concepts

### 1.1. IoC and Dependency Injection

**Inversion of Control (IoC)** is the idea of transferring part of the orchestration over creating and connecting objects to an external component. In a Spring application, that component is typically the **Spring container**.

**Dependency Injection (DI)** is a way an object receives the components it needs from outside, such as via its constructor. DI is a key mechanism the Spring container uses to implement IoC.

Plain Java example:

~~~java
public final class OrderService {
    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }
}
~~~

`OrderService` needs an `OrderRepository`, yet does not decide the implementation or instantiate the repository itself. Another place passes the matching object when constructing `OrderService`.

In plain Java, the assembly point could be:

~~~java
OrderRepository repository = new InMemoryOrderRepository();
OrderService service = new OrderService(repository);
~~~

The types in this snippet are illustrative. With Spring, the container can handle this creation and wiring based on registered **bean definitions**.

### 1.2. Bean and BeanDefinition

A **Bean** is an object managed by the Spring IoC container. An ordinary Java object instantiated with `new` outside the container does not automatically become a Spring bean.

A **BeanDefinition** is metadata telling the container how to create, configure, and manage a bean. Depending on how it is registered, a definition can describe:

- The class to instantiate or a factory method that will supply the object.
- The bean name, scope, and lazy/eager status.
- Constructor arguments, configuration values, and dependency metadata.
- Initialization or destruction methods, if declared.
- Conditions and other metadata used by configuration processors.

Let us distinguish:

| Concept | Nature | Example |
| --- | --- | --- |
| Class | Java type defined by the developer | `GreetingService.class` |
| BeanDefinition | Description of how the container manages/creates the bean | Definition for bean named `greetingService` |
| Bean instance | Actual object created and managed | `GreetingService` instance injected into a controller |
| ApplicationContext | Container supplying beans and other application services | Return value from `SpringApplication.run(...)` |

A container can know a bean's name and type **before the corresponding instance exists**. This is especially evident with beans declared lazy or scoped as `prototype`.

### 1.3. BeanFactory and ApplicationContext

`BeanFactory` is the foundational interface for retrieving and managing beans. `ApplicationContext` extends that capability with application services such as events, resources, message resolution, and configuration management integrations.

In a typical Spring Boot application, `SpringApplication.run(...)` creates and refreshes an `ApplicationContext` suited to the application type:

~~~java
@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Spring Boot makes preparing the environment, selecting the context type, loading configuration, and running the application convenient. **The `BeanDefinition`, Dependency Injection, and bean lifecycle mechanisms belong to Spring Framework**, while Boot builds the startup experience and auto-configuration around them.

## 2. Viewing the Full Cycle Before Diving Into Details

A typical processing flow for an ordinary singleton bean during startup can be visualized as follows:

~~~mermaid
flowchart TD
    A["SpringApplication.run(...)"] --> B["Prepare ApplicationContext"]
    B --> C["Read config, scan components, register BeanDefinitions"]
    C --> D["Process/adjust metadata and register BeanPostProcessors"]
    D --> E["BeanFactory selects beans to create"]
    E --> F["Resolve constructor dependencies and create instance"]
    F --> G["Inject additional property/field/method dependencies if any"]
    G --> H["Pre-initialization callbacks, e.g. @PostConstruct"]
    H --> I["InitializingBean / custom init method"]
    I --> J["Post-initialization callbacks; may create proxy"]
    J --> K["Bean ready for other components to use"]
    K --> L["Context completes refresh; Boot invokes appropriate runners"]
~~~

This is a **conceptual diagram**, not a promise that every bean or every extension passes through the exact same list of callbacks. Some beans are created early to assist configuration processing; some are created only when requested; some are initialized by factories or framework-specific infrastructure along separate paths.

For an ordinary non-lazy singleton bean, keep the essential order in mind:

~~~text
Definition is registered
          ↓
Container decides to create bean
          ↓
Create instance and resolve dependencies
          ↓
Complete necessary injection
          ↓
Invoke initialization callbacks
          ↓
Bean can be used according to context configuration
~~~

**Registration** and **instantiation** are different. **Instantiation/injection** and **initialization** are also different. This is key to understanding common Spring errors.

## 3. Phase 1: Registering BeanDefinitions

### 3.1. Registration via Component Scan

The most visible approach in Spring Boot uses component annotations:

~~~java
package com.example.demo;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

`@Service` is a specialization of `@Component`. When the package containing the class falls within the application's **component scan** scope, Spring can detect the class and register its bean definition.

Common annotations:

| Annotation | Expressed Intent |
| --- | --- |
| `@Component` | General container-managed component |
| `@Service` | Component belonging to the service or business processing layer |
| `@Repository` | Component belonging to the data access layer; can also participate in exception translation when applicable |
| `@Controller` | Spring MVC web controller |
| `@RestController` | Controller geared toward returning HTTP response bodies |
| `@Configuration` | Class declaring configuration and bean factory methods |

Spring Boot typically uses `@SpringBootApplication`, which includes default component scanning starting from the application class's package and its subpackages.

Example:

~~~text
com.example.demo
├── DemoApplication.java       ← @SpringBootApplication
├── GreetingService.java       ← @Service, normally scanned
└── web/
    └── GreetingController.java ← @RestController, normally scanned

com.example.other
└── ExternalService.java       ← outside default scan scope
~~~

If `ExternalService` is not imported through another configuration mechanism, merely marking it with `@Service` will not ensure the container discovers it. This is a common cause of missing-bean errors.

Worth noting: **component scan creates bean definitions first; it does not necessarily instantiate every corresponding object immediately while scanning classes**.

### 3.2. Registration via `@Bean` in Configuration Classes

Not every class can or should be annotated with `@Component`. For instance, a third-party library may not belong to source code you own.

You can declare a factory method:

~~~java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class GreetingConfiguration {

    @Bean
    public MessageFormatter messageFormatter() {
        return new EnglishMessageFormatter();
    }
}
~~~

With:

~~~java
package com.example.demo;

public interface MessageFormatter {
    String format(String name);
}
~~~

And implementation:

~~~java
package com.example.demo;

public final class EnglishMessageFormatter implements MessageFormatter {
    @Override
    public String format(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

In the configuration above:

- `@Configuration` marks a Spring configuration class.
- `@Bean` tells Spring to manage the object returned by the factory method.
- The default bean name is normally taken from the method name, here `messageFormatter`.
- `EnglishMessageFormatter` does not need `@Component` because the bean is created via the factory method.

When processing the configuration class, Spring registers the **definition** for the `messageFormatter` bean. When the bean needs to be created, the container invokes `messageFormatter()` to obtain the actual instance.

This explains why "Spring sees `@Bean`" cannot be equated with "Spring already ran the `@Bean` method during scanning."

### 3.3. Injection Directly in Factory Method Parameters

A factory method can receive dependencies already managed by the container:

~~~java
@Configuration
public class ClientConfiguration {

    @Bean
    public ReportClient reportClient(HttpClient httpClient) {
        return new ReportClient(httpClient);
    }
}
~~~

In this illustrative snippet, `HttpClient` and `ReportClient` are assumed types that must be defined/registered separately. Spring resolves a matching bean for the `httpClient` parameter when creating `ReportClient`.

The benefit is that the configuration class still expresses the **dependency graph** clearly; we are not forced to call `applicationContext.getBean(...)` manually inside the configuration method.

### 3.4. Spring Boot Auto-Configuration Also Registers Definitions

Beyond components you write, Spring Boot includes **auto-configuration**. Based on the classpath, existing beans, configuration properties, and corresponding conditions, it can provide common infrastructure beans.

For example, when an application has a web starter and matching configuration, components serving Spring MVC and an embedded server can be set up automatically.

Conditional annotations in this mechanism commonly include:

~~~java
@ConditionalOnClass(...)
@ConditionalOnMissingBean(...)
@ConditionalOnProperty(...)
~~~

These are **example conditional annotations**, not complete standalone compilable code.

`@ConditionalOnMissingBean` commonly lets auto-configuration step back when the user has already provided a matching bean. However, exact behavior depends on conditions, configuration processing order, and the bean type in question.

**Auto-configuration does not mean Spring Boot always creates every possible bean.** It selects appropriate definitions based on the application's actual conditions.

### 3.5. Programmatic Registration

Beyond annotations, Spring Framework supports registering definitions via APIs such as `BeanDefinitionRegistry` or bean registration methods available on appropriate contexts.

This approach is typically meant for frameworks, starters, or dynamic configuration. In an introductory context, `@Component` and `@Bean` are the most readable and maintainable registration paths.

## 4. Phase 2: The Container Decides When Beans Need to Be Created

Once definitions exist, the container must determine **which beans need to be created immediately** and which only need creation when requested.

### 4.1. Singletons Are Usually Created During Startup

The default scope of a Spring bean is **singleton within a single Spring container**. For a non-lazy singleton, `ApplicationContext` typically instantiates that bean when refreshing the context.

Example:

~~~java
@Service
public class GreetingService {
    public GreetingService() {
        System.out.println("GreetingService constructor");
    }
}
~~~

If the class lies within the scan scope and no condition blocks bean registration/creation, the constructor is normally called when the application starts.

However, this rule applies to **non-lazy singletons in a standard startup flow**. Do not treat it as "seeing a bean definition means the constructor has already run."

### 4.2. Lazy Beans Can Be Created Only When Requested

~~~java
@Lazy
@Service
public class HeavyReportService {
    public HeavyReportService() {
        System.out.println("HeavyReportService created");
    }
}
~~~

`@Lazy` can defer bean instantiation until the bean is requested. However, there is an easy trap: if another non-lazy singleton requires `HeavyReportService` as a mandatory dependency, resolving that dependency can still cause the bean to be created during startup.

If you want an injection point to use a lazy reference mechanism, Spring also supports `@Lazy` on injection points in suitable situations. When designing, distinguish **lazy bean definition** from **lazy dependency resolution**.

Spring Boot also has a configuration property:

~~~properties
spring.main.lazy-initialization=true
~~~

This property changes the default initialization strategy for many beans. It can shorten startup time in some scenarios while causing configuration/initialization errors to surface later when the bean is first used.

### 4.3. Prototype Scope Creates Instances on Demand

~~~java
@Component
@Scope("prototype")
public class TaskContext {
    public TaskContext() {
        System.out.println("New TaskContext");
    }
}
~~~

With `prototype` scope, the container creates a new instance whenever a request for that bean arrives. Unlike singletons, prototypes are not pre-created in bulk simply because a definition exists.

If a prototype is injected directly into **a singleton** via constructor, that dependency is normally resolved once when the singleton is created. Calling methods on the singleton **does not automatically receive a new prototype**. When a fresh instance is needed on each use, design it using `ObjectProvider<T>` or an equivalent suitable mechanism.

Spring also has lifecycle management limits for prototypes: the container creates, configures, and initializes prototypes, yet does not manage full destruction steps for every prototype instance the way it does for singletons.

### 4.4. Singleton Does Not Mean "One Object Across the Entire JVM"

If two different application contexts exist, each context can hold its own singleton for the same bean definition. Moreover, external Java code can still instantiate other instances with `new`.

The meaning of a Spring singleton is **one instance per bean definition within the container's scope**, not a global constraint of the Java language.

## 5. Phase 3: Creating Objects and Resolving Constructors

For beans registered via a class, Spring selects the appropriate creation method, typically a constructor. For beans from `@Bean`, the container calls the factory method and uses the returned object.

### 5.1. Constructor Injection

Example:

~~~java
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
~~~

To create `GreetingService`, Spring needs a bean compatible with type `MessageFormatter`.

Conceptual breakdown:

~~~text
Request to create GreetingService
             │
             ▼
Inspect constructor requiring MessageFormatter
             │
             ▼
Find matching BeanDefinition/bean
             │
             ▼
Create or retrieve MessageFormatter instance
             │
             ▼
Invoke new GreetingService(formatter)
             │
             ▼
GreetingService instance created
~~~

"Spring creates a bean" usually includes **walking its dependencies before invoking the constructor**. Thus logs from a dependency's constructor can appear before logs from the consuming bean's constructor.

If a class has **only one constructor**, Spring can use that constructor for injection without requiring `@Autowired`. This style is widely favored because mandatory dependencies are clearly visible.

### 5.2. What Does the Container Use to Find a Matching Bean?

Spring performs dependency resolution based on information such as bean type, qualifiers, primary candidates, bean names where applicable, and rules specific to each injection point type.

If there is only one `MessageFormatter` bean, the constructor above usually resolves smoothly.

If there are **two implementing beans**:

~~~java
@Component
class EnglishFormatter implements MessageFormatter {
    public String format(String name) {
        return "Hello, " + name;
    }
}

@Component
class FormalFormatter implements MessageFormatter {
    public String format(String name) {
        return "Greetings, " + name;
    }
}
~~~

then a constructor requesting a single `MessageFormatter` can become ambiguous. This example is **an alternative scenario**, not an addition alongside the `@Bean messageFormatter` example above; adding all implementations simultaneously creates even more candidates.

You can specify one bean explicitly:

~~~java
public GreetingService(
        @Qualifier("englishFormatter") MessageFormatter formatter) {
    this.formatter = formatter;
}
~~~

Or mark one implementation as the preferred choice using `@Primary` according to actual design. When multiple mandatory dependencies share the same type, do not arbitrarily pick one bean just to silence startup errors.

### 5.3. Constructors May Never Be Called Due to Missing Dependencies

Example:

~~~java
@Service
public class OrderService {
    public OrderService(OrderRepository repository) {
        // ...
    }
}
~~~

If there is no bean matching `OrderRepository`, Spring cannot supply the mandatory parameter and typically reports a bean creation error such as `UnsatisfiedDependencyException` with cause `NoSuchBeanDefinitionException`.

This occurs **while resolving dependencies to create the bean**, before the service is ready for use. Switching to a no-arg constructor to hide the dependency usually fails to address the actual design requirement.

### 5.4. Creating Objects via `@Bean`

With a factory method:

~~~java
@Bean
MessageFormatter messageFormatter() {
    return new EnglishMessageFormatter();
}
~~~

Spring does not need to invoke `EnglishMessageFormatter`'s constructor itself via component scan. It calls the registered factory method and manages the returned object.

If a class is both scanned as `@Component` and instantiated separately by a `@Bean` method, you may accidentally register two beans with similar roles. Be clear about **which path** you want the container to use to create the bean.

## 6. Phase 4: Dependency Injection and Property Configuration

In constructor injection, dependencies are supplied **immediately when creating the object**. With field injection or setter/method injection, Spring also has a step that assigns dependencies **after the constructor has run**.

### 6.1. Constructor Injection

~~~java
@Service
public class EmailService {
    private final MailClient mailClient;

    public EmailService(MailClient mailClient) {
        this.mailClient = mailClient;
    }
}
~~~

`MailClient` here is an illustrative interface/class requiring a matching bean in the context.

Advantages:

- Mandatory dependencies appear clearly in the constructor.
- `final` can be used to keep references stable.
- Easy to instantiate objects in plain Java unit tests.
- Prevents a situation where an object is validly constructed yet lacks mandatory dependencies.

This is generally the preferred choice for mandatory collaborators of services, controllers, and similar components.

### 6.2. Setter Injection

~~~java
@Component
public class ReportPrinter {
    private AuditLogger auditLogger;

    @Autowired
    public void setAuditLogger(AuditLogger auditLogger) {
        this.auditLogger = auditLogger;
    }
}
~~~

In this illustrative snippet, Spring can instantiate `ReportPrinter` first and then call the setter to inject `AuditLogger`.

This style can be used for optional or deliberately replaceable dependencies, though code must handle cases where the dependency has not been provided according to design contracts.

### 6.3. Field Injection

~~~java
@Component
public class ReportPrinter {
    @Autowired
    private AuditLogger auditLogger;
}
~~~

Field injection is supported by Spring, yet creates "hidden" dependencies in the class: to instantiate with plain Java, you cannot pass the dependency via constructor. The field is also not yet populated during the constructor.

If a constructor invokes a method needing an injected field, that field may still be `null`. Therefore, activities requiring dependencies after field injection should happen during an appropriate initialization phase, not inside the constructor.

### 6.4. Injection Differs from Invoking Business Methods

When a controller has:

~~~java
public GreetingController(GreetingService greetingService) {
    this.greetingService = greetingService;
}
~~~

the container supplying `GreetingService` is **injection**. When a client sends an HTTP request causing the controller to call `greetingService.greet(...)`, that is **business execution after the objects have been wired**.

Do not confuse a one-time injection when creating a singleton with per-request service calls during HTTP requests.

## 7. Phase 5: Initialization Callbacks

After the instance is created and required dependencies have been assigned, Spring can execute declared initialization callbacks. This phase is appropriate for a bean to **validate supplied configuration, set up necessary internal state, or prepare resources belonging to the bean's own lifecycle**.

### 7.1. `@PostConstruct`

In Spring Boot 3.x, the annotation uses the Jakarta package:

~~~java
import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    private final MessageFormatter formatter;

    public GreetingService(MessageFormatter formatter) {
        this.formatter = formatter;
    }

    @PostConstruct
    public void initialize() {
        System.out.println("GreetingService dependencies are ready");
    }

    public String greet(String name) {
        return formatter.format(name);
    }
}
~~~

`@PostConstruct` runs after Spring has performed standard injection for the bean, during initialization. This annotation is processed by the appropriate bean post-processing mechanism in Spring.

Distinguish the timings:

~~~text
constructor                       : creates instance
constructor injection             : dependencies available right as constructor runs
field/setter injection (if any)   : performed after instance creation
@PostConstruct                    : initialization callback after injection
~~~

Do not use `@PostConstruct` to assume **every bean in the entire application context** has completed startup. It belongs only to the initialization lifecycle of the **current bean** and the dependencies already resolved to create it.

### 7.2. `InitializingBean.afterPropertiesSet()`

Spring Framework provides the interface:

~~~java
import org.springframework.beans.factory.InitializingBean;

public class ConfiguredClient implements InitializingBean {
    @Override
    public void afterPropertiesSet() {
        System.out.println("ConfiguredClient initialized");
    }
}
~~~

If a Spring-managed bean implements `InitializingBean`, the container invokes `afterPropertiesSet()` during initialization.

This mechanism ties directly to Spring APIs. `@PostConstruct` generally makes application code callbacks easier to read, while `InitializingBean` still appears in framework code or intentional integrations.

### 7.3. Custom Init Method on `@Bean`

You can specify an initialization method name:

~~~java
public class ConnectionHolder {
    public void warmUp() {
        System.out.println("ConnectionHolder warm-up");
    }

    public void shutDown() {
        System.out.println("ConnectionHolder shutdown");
    }
}
~~~

Registration:

~~~java
@Configuration
class ConnectionConfiguration {

    @Bean(initMethod = "warmUp", destroyMethod = "shutDown")
    ConnectionHolder connectionHolder() {
        return new ConnectionHolder();
    }
}
~~~

In this example, Spring manages the `connectionHolder` bean, invokes `warmUp` during initialization, and invokes `shutDown` during the appropriate singleton destruction phase when the context closes gracefully. Exact destruction behavior still depends on bean scope and lifecycle.

You still have to write the actual resource opening/closing logic inside those methods. Annotations do not automatically turn an arbitrary object into a database connection.

### 7.4. Order of Common Callbacks

For an ordinary bean carrying all callbacks and processed through standard mechanisms, the high-level order is typically:

1. Instance is created; dependencies are resolved and injected.
2. Container-awareness callbacks such as `BeanNameAware` or `BeanFactoryAware` run if the bean implements them.
3. `BeanPostProcessor.postProcessBeforeInitialization(...)` is called; `@PostConstruct` processing normally occurs at this stage.
4. `InitializingBean.afterPropertiesSet()` is called if present.
5. Declared custom init method is called if present.
6. `BeanPostProcessor.postProcessAfterInitialization(...)` is called; certain mechanisms may wrap the bean in a proxy.
7. The bean continues to be used according to the context lifecycle.

Note that multiple `BeanPostProcessor` implementations and framework logic exist. This outline explains the **common flow**, not every special bean creation path.

A bean can use more than one callback style, though splitting initialization for the same purpose across multiple mechanisms should be avoided as it becomes harder to predict and maintain.

## 8. Complete Spring Boot Example: Observing Each Phase

Let us build a small application with a greeting endpoint. The app uses:

- `MessageFormatter` as the greeting formatting contract.
- `EnglishMessageFormatter` as the implementation.
- `GreetingConfiguration` registering the implementation via `@Bean`.
- `GreetingService` discovered by component scan and receiving the formatter via constructor.
- `GreetingController` receiving the service via constructor.
- `CommandLineRunner` exercising the service after context startup.

The example uses Java 21, Maven, and Spring Boot `3.3.5` as an illustrative baseline.

### 8.1. File Structure

~~~text
ioc-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/example/ioc/
                ├── IocDemoApplication.java
                ├── MessageFormatter.java
                ├── EnglishMessageFormatter.java
                ├── GreetingConfiguration.java
                ├── GreetingService.java
                └── GreetingController.java
~~~

### 8.2. File `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>ioc-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

### 8.3. File `MessageFormatter.java`

~~~java
package com.example.ioc;

public interface MessageFormatter {
    String format(String name);
}
~~~

An interface expressing the greeting formatting capability needed by the service, without forcing the service to know the concrete implementation class.

### 8.4. File `EnglishMessageFormatter.java`

~~~java
package com.example.ioc;

public final class EnglishMessageFormatter implements MessageFormatter {
    @Override
    public String format(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

This class intentionally **lacks** `@Component`; it will be created by a factory method in the configuration file.

### 8.5. File `GreetingConfiguration.java`

~~~java
package com.example.ioc;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class GreetingConfiguration {

    @Bean
    public MessageFormatter messageFormatter() {
        System.out.println("[factory] Creating MessageFormatter");
        return new EnglishMessageFormatter();
    }
}
~~~

When the configuration is processed, Spring has a bean definition named `messageFormatter`. When that bean needs to be created, the container invokes the factory method.

### 8.6. File `GreetingService.java`

~~~java
package com.example.ioc;

import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    private final MessageFormatter formatter;

    public GreetingService(MessageFormatter formatter) {
        this.formatter = formatter;
        System.out.println("[constructor] GreetingService created");
    }

    @PostConstruct
    public void initialize() {
        System.out.println("[init] GreetingService initialized");
    }

    public String greet(String name) {
        return formatter.format(name);
    }
}
~~~

`@Service` gives component scan a basis for registering the `GreetingService` definition. The mandatory constructor requires a `MessageFormatter`. `@PostConstruct` outputs a milestone during the service's initialization phase.

### 8.7. File `GreetingController.java`

~~~java
package com.example.ioc;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {
    private final GreetingService greetingService;

    public GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/api/greeting")
    public GreetingResponse greet(
            @RequestParam(defaultValue = "Friend") String name) {
        return new GreetingResponse(greetingService.greet(name));
    }

    public record GreetingResponse(String message) {
    }
}
~~~

Spring registers the controller as a bean and injects `GreetingService` into its constructor. When an HTTP request arrives, the controller calls the service previously created and wired by the container.

### 8.8. File `IocDemoApplication.java`

~~~java
package com.example.ioc;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class IocDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(IocDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner afterStartup(GreetingService greetingService) {
        return args -> System.out.println(
                "[runner] " + greetingService.greet("Alice"));
    }
}
~~~

`CommandLineRunner` is a callback invoked by Spring Boot after the application context has been refreshed per the startup sequence. It **differs** from `@PostConstruct`: the runner is application-level logic after context startup; `@PostConstruct` belongs to the initialization lifecycle of a single bean.

The `afterStartup(...)` method is also a `@Bean` factory method. Spring resolves the `GreetingService` parameter when creating the runner bean.

### 8.9. Running and Reading the Output

In the directory containing `pom.xml`, with JDK 21 and a compatible Maven setup:

~~~bash
mvn spring-boot:run
~~~

Among the startup log lines, you can observe the milestones printed by the example:

~~~text
[factory] Creating MessageFormatter
[constructor] GreetingService created
[init] GreetingService initialized
[runner] Hello, Alice!
~~~

These are **lines to observe by dependency relationship**, not necessarily adjacent in stdout; Spring Boot also logs many framework messages. Under normal startup conditions and this example, the formatter factory must supply an object before the service constructor can receive its dependency, service initialization happens after the service is constructed, and the runner is called only in the post-refresh stage.

Open another terminal and send an HTTP request:

~~~bash
curl -i "http://localhost:8080/api/greeting?name=Bob"
~~~

Expected body:

~~~json
{"message":"Hello, Bob!"}
~~~

The application must be running on port `8080`, or adjust the URL to match the configured port. The response demonstrates that the controller can use the container-injected service and registered formatter.

### 8.10. Tracing the Bean Path in the Example

~~~mermaid
flowchart TD
    A["Component scan and @Configuration processing"] --> B["BeanDefinition: messageFormatter"]
    A --> C["BeanDefinition: greetingService"]
    A --> D["BeanDefinition: greetingController"]
    A --> E["BeanDefinition: afterStartup"]
    B --> F["Invoke @Bean factory method"]
    F --> G["EnglishMessageFormatter instance"]
    G --> H["Inject into GreetingService constructor"]
    C --> H
    H --> I["GreetingService instance"]
    I --> J["@PostConstruct"]
    J --> K["Inject into GreetingController"]
    D --> K
    I --> L["Inject into CommandLineRunner factory method"]
    E --> L
    L --> M["Runner invokes greet after context refresh"]
~~~

The diagram does not fix creation order for unrelated beans. It shows **ordering constraints imposed by dependencies**. For instance, the service cannot be instantiated per the example's constructor if the formatter has not yet been provided.

## 9. What Does `BeanPostProcessor` Handle in the Cycle?

Spring has an important extension point called `BeanPostProcessor`. It can intervene on beans **before and after initialization**.

The main interface declares two key methods:

~~~java
Object postProcessBeforeInitialization(Object bean, String beanName);

Object postProcessAfterInitialization(Object bean, String beanName);
~~~

These are abbreviated signatures for illustration, omitting annotations and other details of the actual interface/API.

Processors can:

- Handle lifecycle annotations such as `@PostConstruct`.
- Apply custom logic to matching beans.
- In certain Spring integrations, participate in creating proxies or wrapping behavior around beans.

With AOP or `@Transactional`, the object received elsewhere may be a **proxy** rather than the original implementation instance itself. This lets Spring add behaviors such as transaction management, yet also requires understanding constructors, method interception, and runtime types properly.

Do not assume every bean is proxied; only beans matching corresponding configurations/conditions pass through the necessary proxy mechanisms.

### 9.1. `BeanFactoryPostProcessor` Differs from `BeanPostProcessor`

The two similar names operate at two different layers.

| Mechanism | Primary Target | Conceptual Timing |
| --- | --- | --- |
| `BeanFactoryPostProcessor` | Bean factory metadata/configuration, especially bean definitions | Before creating ordinary application singletons |
| `BeanDefinitionRegistryPostProcessor` | Can add/modify `BeanDefinition` registrations | While the registry is being prepared |
| `BeanPostProcessor` | Bean instances being created/initialized | Around each instance's initialization phase |

For example, a `BeanFactoryPostProcessor` can adjust properties of a bean definition; it is not a regular callback for "using a finished bean."

In an introductory application, you usually **do not need to write** these processors yourself. Understanding them explains why Spring does more than just find annotations and call `new`.

## 10. Initialization and Application Startup Are Two Different Points in Time

In an application with many beans, separate two levels:

- **Bean initialization:** a specific bean has been created, injected, and had its initialization callbacks invoked.
- **Application startup:** the application context has been refreshed and Spring Boot proceeds with application-level callbacks such as `ApplicationRunner` or `CommandLineRunner`.

Example:

~~~java
@Component
class StartupTask implements ApplicationRunner {
    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Application startup task");
    }
}
~~~

`ApplicationRunner` and `ApplicationArguments` belong to Spring Boot; they are not lifecycle callbacks for an individual service bean like `@PostConstruct`.

If a task must run **only after the application context is ready per Boot's lifecycle**, a runner may fit better than forcing that work into `@PostConstruct` on an arbitrary service.

However, runners still execute during startup and exceptions from them can fail startup. Slow tasks, periodic jobs, or work needing retries or transactional guarantees usually require dedicated designs rather than being dropped indiscriminately into startup callbacks.

### 10.1. Do Not Confuse `ApplicationReadyEvent` with `@PostConstruct`

Spring Boot also publishes application lifecycle events such as `ApplicationReadyEvent` near the end of successful startup, after relevant runners finish. A listener for this event suits certain application-wide notification or coordination needs.

Availability of servers, beans, and resources depends on actual configuration. Do not assume external resources such as databases, message brokers, or external HTTP services are healthy solely because the ready event was published.

## 11. Managing Initialization Order Between Beans

If bean A needs bean B via constructor, Spring must supply B before it can finish A:

~~~java
@Service
class OrderService {
    OrderService(OrderRepository repository) {
        // repository must exist before OrderService finishes creation
    }
}
~~~

However, if two beans **have no dependency on each other**, never write logic relying on the incidental order they appear in logs.

If you genuinely need to declare an initialization relationship that cannot be expressed via constructors, Spring provides the `@DependsOn` annotation:

~~~java
@Component
@DependsOn("schemaInitializer")
class ReportScheduler {
    // ...
}
~~~

The snippet only illustrates the relationship; a bean named `schemaInitializer` must be registered. `@DependsOn` controls certain bean creation ordering relationships, **does not automatically inject** an object into a constructor, and does not guarantee external systems have completed all work.

In most application code, explicit dependencies declared via constructors are clearer. If two beans require an initialization sequence without collaborating directly, check whether that belongs to an application-level orchestrator or lifecycle component.

## 12. When Are Beans Destroyed?

This lesson focused on registration → instantiation → injection → initialization, yet the bean lifecycle also includes a **destruction** phase.

For eligible singletons, when the Spring context closes normally, the container can invoke:

- Methods annotated with `@PreDestroy` (Jakarta).
- `DisposableBean.destroy()` if the bean implements this interface.
- A custom destroy method if declared.
- Appropriate inferred destroy-method mechanisms for beans created via `@Bean`.

Example:

~~~java
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;

@Component
public class ManagedWorker {

    @PostConstruct
    public void start() {
        System.out.println("Worker initialized");
    }

    @PreDestroy
    public void stop() {
        System.out.println("Worker stopping");
    }
}
~~~

These callbacks apply to **Spring-managed** objects and the context lifecycle. Never assume `@PreDestroy` always runs if the JVM is forcibly terminated, crashes, or is killed without a chance for normal shutdown.

For prototypes, the container does not normally track destruction of every instance after allocation. For resources needing cleanup, the caller or a corresponding scope mechanism must have an explicit strategy.

## 13. Common Errors Tied to Each Phase

Looking at which stage is failing helps narrow down the issue faster.

| Symptom | Related Phase | What to Check |
| --- | --- | --- |
| `OrderRepository` bean not found | Registration / dependency resolution | Package scan, annotations, `@Bean`, configuration conditions |
| Two beans of the same type; Spring cannot choose | Dependency resolution | `@Qualifier`, `@Primary`, or design of multiple implementations |
| Constructor throws exception | Instantiation | Actual root cause in constructor and input dependencies |
| `@Autowired` field is null inside constructor | Instantiation before field injection | Move mandatory dependencies to the constructor |
| `@PostConstruct` method throws exception | Initialization | Setup logic, configuration, required resources |
| Bean does not appear at startup but initializes when calling endpoint | Possible lazy/scope involvement | `@Lazy`, `spring.main.lazy-initialization`, scope, dependency path |
| Runtime uses a proxy bean, unexpected type, or call path | Post-processing / AOP | AOP config, transactions, proxies, and how methods are called |

### 13.1. No Matching Bean

Example:

~~~text
No qualifying bean of type '...OrderRepository' available
~~~

Possible causes:

1. The implementation has not been annotated or registered via `@Bean`.
2. Its package lies outside the component scan scope.
3. Relevant auto-configuration was not activated due to missing dependencies/conditions.
4. The bean was disabled by a profile or condition.
5. The type requested by the constructor is incompatible with existing beans.

Do not solve this by arbitrarily adding `@ComponentScan` across the entire project. First understand which module/package truly owns the bean.

### 13.2. Multiple Beans Sharing a Contract

If a `PaymentGateway` is required yet both `CardGateway` and `MockGateway` implementations are registered, the container needs a valid way to choose. In a real application, a mock implementation should not be present by default in production just for testing purposes.

You can use profiles, conditions, qualifiers, or bean configuration to explicitly express which implementation is used under which circumstances.

### 13.3. Circular Dependency

Example:

~~~text
ServiceA ──constructor──► ServiceB
ServiceB ──constructor──► ServiceA
~~~

To create A, B is needed; to create B, A is needed. This is a **circular dependency**. With mandatory constructor injection on both sides, the container cannot complete the object creation chain normally.

Spring Boot 3.x discourages circular dependencies of this kind by default and typically fails when unable to resolve them. The right fix is reviewing responsibilities:

- Is there logic that properly belongs in a third service?
- Are the two services taking on too many responsibilities?
- Has a higher-level orchestration flow been mistakenly placed inside a lower-level service?

Using lazy references or setters to work around the error can hide design issues. Use them only when you thoroughly understand the dependencies and lifecycles.

### 13.4. Constructor Runs, Yet `@PostConstruct` Does Not

Possibilities worth examining:

- The object was created with `new` outside the container, so Spring does not process its lifecycle.
- The bean was not registered with Spring or did not pass through the appropriate annotation processing mechanism.
- The running code is using a different instance from the one you are observing.
- Bean creation failed before reaching initialization.

Do not jump to blaming the annotation. Identify **who created the object** and whether Spring is managing that instance.

### 13.5. Initialization Failure Prevents the Application from Starting

For example, a `@PostConstruct` method tries connecting to a database and throws an exception. If this bean must be created during startup, an initialization failure can fail the entire context refresh.

The outer message is typically a `BeanCreationException`. Read the deepest **cause** in the stack trace to learn which logic actually failed, rather than just looking at the bean name and tweaking annotations.

Sometimes an external connection needs a retry strategy, health checks, or initialization at a different stage. That should be designed around business and system characteristics instead of putting all I/O in `@PostConstruct` by default.

## 14. Observing the Bean Lifecycle with Appropriate Tools

### 14.1. Logging Constructors and Callbacks

In a learning environment, adding logs in constructors and `@PostConstruct` helps distinguish creation from initialization:

~~~java
@Service
class InventoryService {
    InventoryService() {
        System.out.println("[constructor] InventoryService");
    }

    @PostConstruct
    void initialize() {
        System.out.println("[init] InventoryService");
    }
}
~~~

The logs illustrate order within this bean's scope. Do not extrapolate the initialization order of all other beans across the application from a few log lines, as many definitions are processed by different mechanisms.

In real applications, use a properly configured logger rather than printing sensitive data to stdout.

### 14.2. Identifying Which Beans Are Registered

`ApplicationContext` lets you query registered bean definition names:

~~~java
@Bean
CommandLineRunner showBeanName(ApplicationContext context) {
    return args -> {
        for (String name : context.getBeanDefinitionNames()) {
            if (name.toLowerCase().contains("greeting")) {
                System.out.println("Bean definition: " + name);
            }
        }
    };
}
~~~

The snippet above uses `ApplicationContext` and `CommandLineRunner`, with necessary imports inside a Spring Boot configuration class. It helps inspect registered bean names.

**A `BeanDefinition` list is not proof that every instance has already been created**. `getBeanDefinitionNames()` reports registrations; calling `getBean(...)` can trigger creation of lazy beans.

### 14.3. Debugging Auto-Configuration

Spring Boot can print an auto-configuration condition evaluation report when debug mode is enabled:

~~~bash
java -jar app.jar --debug
~~~

This information is useful when you want to see why an auto-configuration applied or did not apply. The filename `app.jar` is just an example; replace it with your actual artifact.

Condition reports alone cannot explain every DI error. Combine them with exception stack traces, package scans, bean lists, and the dependency graph to find the exact cause.

## 15. Practice Exercises: Predicting When Beans Are Created

### Exercise A. Is a `BeanDefinition` an Instance?

Given:

~~~java
@Lazy
@Component
class ExportService {
    ExportService() {
        System.out.println("ExportService constructor");
    }
}
~~~

Question: if the application scans `ExportService`, is the constructor log line guaranteed to appear immediately at startup?

**Hint:** No. Spring can register the definition while deferring instance creation due to laziness. If an eager bean directly requires `ExportService`, dependency resolution may cause it to be created earlier than you expect.

### Exercise B. Reading Callback Order

Given:

~~~java
@Component
class SampleService {
    SampleService() {
        System.out.println("A: constructor");
    }

    @PostConstruct
    void init() {
        System.out.println("B: @PostConstruct");
    }
}
~~~

Question: during creation of a container-managed instance under normal mechanics, which log appears first?

**Hint:** `A` appears when the constructor runs; `B` is an initialization callback and therefore appears after the instance is created and required injection completes.

### Exercise C. Constructor and Field Injection

Given:

~~~java
@Component
class AuditService {
    @Autowired
    private AuditClient client;

    AuditService() {
        System.out.println(client);
    }
}
~~~

Question: why can the constructor print `null`?

**Hint:** Field injection occurs **after the constructor runs**. `AuditClient` is an assumed type requiring a matching bean; the way to avoid uninitialized dependencies is requiring `AuditClient` via the constructor.

### Exercise D. Distinguishing Component Scan and `@Bean`

Given:

~~~java
@Configuration
class ToolsConfiguration {
    @Bean
    Formatter formatter() {
        return new JsonFormatter();
    }
}
~~~

In this example, `Formatter` and `JsonFormatter` are illustrative types.

Question: does `JsonFormatter` necessarily need `@Component`?

**Hint:** No. The container obtains the bean definition through the `@Bean` factory method. The implementation class does not have to be directly component-scanned to produce a bean via this approach.

### Exercise E. Multiple Implementations

Given:

~~~java
interface Notifier {
    void notify(String text);
}

@Component
class MailNotifier implements Notifier {
    public void notify(String text) {
        System.out.println("MAIL " + text);
    }
}

@Component
class SmsNotifier implements Notifier {
    public void notify(String text) {
        System.out.println("SMS " + text);
    }
}
~~~

And:

~~~java
@Service
class AlertService {
    AlertService(Notifier notifier) {
        // ...
    }
}
~~~

Question: does Spring have enough information to reliably select a single `Notifier` bean? What are the ways to fix this?

**Hint:** When two valid candidates exist without an appropriate precedence rule, injection can fail. You can use `@Qualifier`, `@Primary`, or register only the implementation actually needed.

### Exercise F. Tracing the Dependency Graph

Given:

~~~text
OrderController → OrderService → OrderRepository → DataSource
~~~

Explain:

1. Which kinds of bean definitions must exist so the container can instantiate all objects?
2. If `OrderRepository` is missing, what happens to creating `OrderService`?
3. Should `OrderController` call `new OrderRepository(...)` itself?
4. If the `DataSource` constructor or datasource-creating factory fails, why can the error appear during startup of a higher-level service?

**Hint:** Spring must resolve dependencies to build beans along the graph; errors in a lower bean propagate up to beans that require it. DI separates dependency-creation decisions from usage logic.

## 16. Principles to Keep When Writing Spring Boot Applications

When designing classes and beans, ask yourself:

- **Has the bean been registered?** Check annotations, `@Bean` config, package scanning, and conditions.
- **When is the bean created?** Check scopes, laziness, and dependencies from eager singletons.
- **Who provides collaborators?** Prefer constructor injection for mandatory dependencies.
- **Which implementation is the bean receiving?** When multiple candidates exist, use explicit selection rules.
- **Where does initialization belong?** Callbacks should handle bean-level setup, not arbitrarily perform full application startup orchestration.
- **Are you relying on accidental ordering?** Use explicit dependencies or proper lifecycle mechanisms rather than relying on log order.
- **Who manages the lifecycle?** Objects created with `new` outside the container do not automatically receive Spring's callbacks and bean mechanisms.

Understanding the distinction among **`BeanDefinition`**, **bean instance**, **dependency resolution**, and **initialization callbacks** helps diagnose most common startup errors: missing beans, multiple beans of the same type, circular dependencies, throwing constructors, or failed resource initialization.

Spring Boot helps start the context and supplies many default infrastructure definitions; Spring Framework performs most of the bean management work. In the typical flow, the container **registers how to create beans**, **decides when to create them**, **resolves dependencies to construct objects**, **injects necessary components**, and **executes initialization callbacks** before beans are used as designed. Grasping each step forms the foundation for learning bean scopes, auto-configuration, AOP, transactions, and the lifecycle of Spring Boot applications.
