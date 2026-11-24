# BeanFactory and ApplicationContext

In Spring Boot, we frequently write `@Service`, `@Repository`, `@RestController`, `@Bean`, or constructor injection without directly instantiating every object with `new`. Behind that workflow sits Spring's **IoC container**: the component that knows which objects must exist, how to create them, how to wire dependencies, and how to manage their lifecycles.

Two names encountered regularly when reading Spring documentation and source code are **`BeanFactory`** and **`ApplicationContext`**. These are two interfaces related by inheritance: `BeanFactory` defines the foundational contract of the container; `ApplicationContext` extends that capability for a full-fledged application. Spring Boot typically initializes and uses an **ApplicationContext** when running an application.

Understanding this relationship helps answer questions such as: why beans are created at startup, how `getBean()` works, why Spring can inject constructor dependencies, and why `ApplicationContext` can also be used to read configuration, load resources, or publish events.

## 1. From Manual `new` to the IoC Container

Suppose there are two Java classes:

```java
public class MessageFormatter {
    public String format(String name) {
        return "Hello, " + name + "!";
    }
}
```

```java
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

Without Spring, calling code might look like:

```java
MessageFormatter formatter = new MessageFormatter();
GreetingService service = new GreetingService(formatter);
System.out.println(service.greet("Alice"));
```

Output:

```text
Hello, Alice!
```

The code decides **when to create** `MessageFormatter`, **when to create** `GreetingService`, and **which dependency to pass to the constructor**.

When using an IoC container, you declare the *definitions* of the objects and the required relationships. The container takes responsibility for creating and supplying objects according to configuration:

```text
                    Bean definitions
            @Component / @Bean / configuration
                         │
                         ▼
                   IoC container
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
       MessageFormatter       GreetingService
              └──────────┬──────────┘
                         ▼
             Constructor injection
                         │
                         ▼
                Business code runs
```

That is **Inversion of Control**: business code does not need to orchestrate the entire object graph construction process itself. **Dependency Injection (DI)** is one way the IoC container supplies dependencies into constructors, fields, or setters; constructor injection is usually preferred because dependencies are declared explicitly and can be tested with plain Java.

A **Spring bean** is an object created or registered and managed by the container according to a bean definition or corresponding registration mechanism. Not every Java object in the JVM is a Spring bean.

## 2. What Is `BeanFactory`?

`BeanFactory` is the foundational interface of the Spring IoC container, located in the package:

```java
import org.springframework.beans.factory.BeanFactory;
```

Its primary role is providing access to beans managed by the container. Representative methods:

```java
Object getBean(String name);

<T> T getBean(String name, Class<T> requiredType);

<T> T getBean(Class<T> requiredType);

boolean containsBean(String name);

boolean isSingleton(String name);

boolean isPrototype(String name);

Class<?> getType(String name);
```

The list above shows common illustrative signatures; the interface also includes additional methods and overloads depending on the Spring version. General meaning:

- `getBean(...)` asks the container to return a bean by name or type.
- `containsBean(...)` checks whether a bean exists under a given name.
- `isSingleton(...)` and `isPrototype(...)` query the bean's scope.
- `getType(...)` looks up the bean's type when the container can determine it.

An important point is that **`BeanFactory` is an interface, not the name of a single running object in the application**. Spring provides implementations capable of storing bean definitions, constructing beans, resolving dependencies, and coordinating other processing steps.

### 2.1. Example Using `BeanFactory` Directly

We have a plain Java class:

```java
package com.example.ioc;

public class GreetingService {

    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
```

A program can instantiate a container implementation itself and register a bean definition:

```java
package com.example.ioc;

import org.springframework.beans.factory.BeanFactory;
import org.springframework.beans.factory.support.DefaultListableBeanFactory;
import org.springframework.beans.factory.support.RootBeanDefinition;

public class BeanFactoryExample {

    public static void main(String[] args) {
        DefaultListableBeanFactory registry =
                new DefaultListableBeanFactory();

        registry.registerBeanDefinition(
                "greetingService",
                new RootBeanDefinition(GreetingService.class)
        );

        BeanFactory factory = registry;

        GreetingService service =
                factory.getBean("greetingService", GreetingService.class);

        System.out.println(service.greet("Alice"));
    }
}
```

In this example:

1. `DefaultListableBeanFactory` is an implementation capable of registering and managing bean definitions.
2. `RootBeanDefinition` describes how to create the `GreetingService` bean.
3. `BeanFactory` is the interface type used to access the bean.
4. `getBean(...)` asks the container to supply the instance.

There is no `@SpringBootApplication`, web server, or Spring Boot auto-configuration in the example. It illustrates Spring Framework's fundamental IoC mechanism.

We do not call `new GreetingService()` where the bean is consumed; the container executes the creation process according to the bean definition. However, **programmatically configuring the bean** still has to happen, here via `registerBeanDefinition(...)`.

### 2.2. `BeanFactory` Does Not Automatically Scan the Entire Classpath

A misconception is that simply creating `new DefaultListableBeanFactory()` will automatically discover every class annotated with `@Service` or `@Component`.

In practice, the container needs **bean definitions**. When using a basic `BeanFactory` directly, you must register them yourself or explicitly configure the processors needed to load bean definitions from annotations, XML, or other sources.

`@Component` is metadata on a class. The presence of the annotation in bytecode **does not mean** the class has become a bean in an arbitrary container.

### 2.3. Bean Definitions and Bean Instances Differ

A **bean definition** describes how to create a bean: type, name, scope, dependencies, init method, etc. A **bean instance** is the concrete object created according to that definition.

```text
BeanDefinition
    name: greetingService
    class: GreetingService
    scope: singleton
              │
              ▼
       Create bean instance
              │
              ▼
       GreetingService@...
```

With a newly created manual `DefaultListableBeanFactory` where pre-instantiation steps have not been invoked, many singletons are only created when first requested via `getBean()`. This is often referred to as *lazy retrieval* in examples using `BeanFactory` directly.

However, **do not turn that into an absolute rule that every `BeanFactory` is always lazy**. When beans are created depends on the implementation, how the container is initialized, and which lifecycle management steps have been invoked.

## 3. What Is `ApplicationContext`?

`ApplicationContext` is an interface in Spring Framework:

```java
import org.springframework.context.ApplicationContext;
```

It **extends the bean management contracts** and adds capabilities for real-world applications: reading environment metadata, locating resources, providing localized messages, publishing application events, organizing contexts in parent/child hierarchies, and managing container initialization across corresponding implementations.

A simplified interface diagram:

```text
                        BeanFactory
                             ▲
                ┌────────────┴────────────┐
                │                         │
        HierarchicalBeanFactory    ListableBeanFactory
                ▲                         ▲
                └────────────┬────────────┘
                             │
                     ApplicationContext
                      /     |       \
             Environment  Events    Resources
               & i18n       &       loading
                         lifecycle*
```

The diagram represents a functional view rather than the exact inheritance hierarchy of every interface. Specifically, `ApplicationContext` extends `ListableBeanFactory`, `HierarchicalBeanFactory`, `MessageSource`, `ApplicationEventPublisher`, `ResourcePatternResolver`, and `EnvironmentCapable`. Configurable implementations, such as `ConfigurableApplicationContext`, provide additional contracts like `refresh()`, `close()`, and lifecycle support.

Because `ApplicationContext` is also a `BeanFactory` via interface inheritance, operations such as `getBean(...)` can still be called on `ApplicationContext`.

### 3.1. `ApplicationContext` Is Not a Second Container Outside `BeanFactory`

In many Spring implementations, an `ApplicationContext` uses an internal `BeanFactory` to perform bean creation, lookup, and management tasks.

This can be visualized as:

```text
Spring Boot Application
        │
        ▼
  ApplicationContext
   ├── BeanFactory contract / bean access
   ├── Underlying BeanFactory implementing bean mechanics
   ├── Environment / configuration
   ├── Resource loading
   ├── Events / MessageSource
   └── Startup and shutdown lifecycle
```

Therefore, you should not say "Spring Boot uses `ApplicationContext` so it does not use `BeanFactory`." **`ApplicationContext` is built on top of `BeanFactory` capabilities**. The two concepts describe related API layers, not two independent bean lists.

### 3.2. `ApplicationContext` Implementations

In Spring Framework code, you may encounter:

- `AnnotationConfigApplicationContext`: creates a context from configuration classes and component metadata, suited for standalone Java examples or non-web applications.
- `ClassPathXmlApplicationContext`: initialized from XML configuration on the classpath, often seen in documentation or legacy systems.
- Context types for web applications: integrating with servlet or reactive environments.
- Spring Boot implementations tailored to application type and bootstrap configuration.

You typically program against the **`ApplicationContext` interface** rather than coupling tightly to a concrete implementation.

## 4. `ApplicationContext` Example with Java Configuration

This time we will not manually register a bean definition as in `BeanFactoryExample`. Instead, we use `@Configuration` and `@Bean`.

### 4.1. Business Class

`src/main/java/com/example/ioc/GreetingService.java`:

```java
package com.example.ioc;

public class GreetingService {

    private final String prefix;

    public GreetingService(String prefix) {
        this.prefix = prefix;
    }

    public String greet(String name) {
        return prefix + ", " + name + "!";
    }
}
```

### 4.2. Configuration Class

`src/main/java/com/example/ioc/AppConfig.java`:

```java
package com.example.ioc;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class AppConfig {

    @Bean
    public GreetingService greetingService() {
        return new GreetingService("Hello");
    }
}
```

`@Configuration` marks the class as a configuration source. `@Bean` declares a bean named `greetingService` after the method name (unless another name is specified).

### 4.3. Initializing and Using the Context

`src/main/java/com/example/ioc/ApplicationContextExample.java`:

```java
package com.example.ioc;

import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class ApplicationContextExample {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            ApplicationContext applicationContext = context;

            GreetingService service =
                    applicationContext.getBean(GreetingService.class);

            System.out.println(service.greet("Alice"));
        }
    }
}
```

Output:

```text
Hello, Alice!
```

Here:

- `AnnotationConfigApplicationContext` reads `AppConfig` as configuration.
- `@Bean` is processed into a bean definition, then the bean is created and registered according to container rules.
- `ApplicationContext#getBean(...)` returns the needed bean.
- `try-with-resources` closes the context after use, triggering appropriate shutdown steps for context-managed beans.

This example uses **Spring Framework** and does not require Spring Boot, because `ApplicationContext` is a foundational Spring concept.

## 5. Comparing `BeanFactory` and `ApplicationContext`

| Criterion | `BeanFactory` | `ApplicationContext` |
|---|---|---|
| Primary role | Core interface for IoC/bean management | Application-level container interface |
| Relationship | Foundational interface | Extends bean lookup interfaces and adds capabilities |
| Retrieve bean by name/type | Yes | Yes |
| Container needs bean definitions | Yes | Yes |
| Automatic component scanning | Not guaranteed by the interface alone; requires infrastructure setup | Commonly configured conveniently via annotation-based implementations |
| Bean post-processors | Supported if registered | Standard implementations process and register supporting infrastructure during refresh |
| Singleton instantiation | For manually created BeanFactory, often created on demand unless pre-instantiated | Usually creates non-lazy singletons during refresh/startup |
| `Environment` access | Not part of the `BeanFactory` contract | Yes |
| Resource loading `ResourcePatternResolver` | Not part of the `BeanFactory` contract | Yes |
| Application events | Not part of the `BeanFactory` contract | Yes |
| Internationalization `MessageSource` | Not part of the `BeanFactory` contract | Yes |
| Context hierarchy | Not part of the base interface contract | Supports parent context awareness; implementation-dependent |
| Used directly in typical Spring Boot apps | Rarely needed | Common, created by Spring Boot at startup |

The "usually" notes describe implementations used in practice; do not infer that **every implementation of the interface** is forced to share the exact same bean creation schedule or annotation infrastructure.

### 5.1. Distinguishing Core Features from Application Services

`BeanFactory` provides operations for working with beans. `ApplicationContext` lets you use those operations inside an initialized application environment equipped with additional services.

For instance, the same bean retrieval API can appear on both:

```java
BeanFactory beanFactory = /* a configured BeanFactory */;
GreetingService one = beanFactory.getBean(GreetingService.class);
```

```java
ApplicationContext context = /* an initialized ApplicationContext */;
GreetingService two = context.getBean(GreetingService.class);
```

These two snippets illustrate the API and **do not assume** `one` and `two` are the same instance since they may belong to different containers. If the same `ApplicationContext` is viewed through both `BeanFactory` and `ApplicationContext` interfaces, the calls access the same bean registry of that context.

### 5.2. When Do You Need to Know About `BeanFactory`?

Business application developers rarely construct a `BeanFactory` manually. The concept is useful when:

- Reading IoC architecture or Spring source code.
- Understanding bean lookup, scopes, and bean definitions.
- Working with framework integrations that customize how beans are registered or initialized.
- Distinguishing container infrastructure from dependency injection in business code.

When building ordinary Spring Boot applications, you usually do not need to access `BeanFactory` directly; simply declare dependencies via constructors and let `ApplicationContext` supply the beans.

## 6. Bean Creation Timing: Understanding Lazy vs. Eager Properly

Suppose there is a singleton bean:

```java
public class StartupProbe {

    public StartupProbe() {
        System.out.println("StartupProbe created");
    }
}
```

### 6.1. Manual `BeanFactory`

```java
DefaultListableBeanFactory factory = new DefaultListableBeanFactory();

factory.registerBeanDefinition(
        "startupProbe",
        new RootBeanDefinition(StartupProbe.class)
);

System.out.println("Definition registered");

// First request for the bean:
factory.getBean("startupProbe");
```

In this basic setup, `StartupProbe` is typically created when `getBean` is first called. The container already knows the bean definition without needing to instantiate it at registration time.

This does not mean `BeanFactory` **cannot** pre-instantiate singletons. Advanced APIs and initialization routines can request creating them upfront.

### 6.2. `ApplicationContext` Initializes During `refresh()`

```java
@Configuration
public class ProbeConfig {

    @Bean
    public StartupProbe startupProbe() {
        return new StartupProbe();
    }
}
```

```java
try (AnnotationConfigApplicationContext context =
             new AnnotationConfigApplicationContext(ProbeConfig.class)) {

    System.out.println("Context is ready");
}
```

In a typical configuration, the `AnnotationConfigApplicationContext(ProbeConfig.class)` constructor registers the configuration and refreshes the context. Singletons **not marked lazy** are usually instantiated during refresh, before the program prints "Context is ready."

This is a practical benefit: many bean creation errors or missing dependencies surface **immediately at startup**, rather than waiting until a feature is invoked for the first time.

### 6.3. `@Lazy` Changes Creation Timing

```java
@Configuration
public class ProbeConfig {

    @Bean
    @Lazy
    public StartupProbe startupProbe() {
        return new StartupProbe();
    }
}
```

With this bean, the container can defer creating the instance until the bean is actually requested.

Note:

- `@Lazy` does not guarantee the bean is never created at startup; another eager singleton may require that bean as a dependency.
- `prototype`-scoped beans are inherently created when an instance is requested, unlike eager singletons.
- Spring Boot also provides application-level lazy initialization configuration options; do not conflate them with the definitions of `BeanFactory` or `ApplicationContext` themselves.

**Differences in eager/lazy behavior mainly stem from how the container is initialized and how beans are configured**, not because the two interfaces declare two strictly opposite absolute rules.

## 7. Additional Capabilities of `ApplicationContext`

The features below explain why Spring Boot typically works with `ApplicationContext` rather than a manually constructed `BeanFactory`.

### 7.1. `Environment`: Reading Configuration Properties and Profiles

`ApplicationContext` provides `getEnvironment()`:

```java
import org.springframework.context.ApplicationContext;
import org.springframework.core.env.Environment;

public class ConfigurationReader {

    public static void printPort(ApplicationContext context) {
        Environment environment = context.getEnvironment();

        String port = environment.getProperty(
                "server.port",
                "8080"
        );

        System.out.println("Configured server.port = " + port);
    }
}
```

In Spring Boot, `Environment` can obtain values from `application.yml`, profile-specific files, environment variables, system properties, command-line arguments, and other `PropertySources` according to precedence rules.

The value `8080` in the example is a fallback for **reading the property**, not a guarantee that the actual HTTP port is always 8080. When the web server uses a random port, specialized config, or is not a web app, the port used may differ.

For business code, it is usually better to inject configuration via `@ConfigurationProperties` or `@Value`, avoiding calling `context.getEnvironment()` everywhere.

### 7.2. `Resource`: Locating Resources on the Classpath and Elsewhere

`ApplicationContext` supports reading resources:

```java
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.context.ApplicationContext;
import org.springframework.core.io.Resource;

public class MessageReader {

    public static String read(ApplicationContext context)
            throws Exception {

        Resource resource =
                context.getResource("classpath:messages/welcome.txt");

        try (InputStream input = resource.getInputStream()) {
            return new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8
            );
        }
    }
}
```

The file may sit at:

```text
src/main/resources/messages/welcome.txt
```

and after packaging into a Spring Boot JAR, it typically resides at:

```text
BOOT-INF/classes/messages/welcome.txt
```

Code using `classpath:messages/welcome.txt` still works because it loads the resource through the classpath loader without requiring a physical file in the source tree.

`ApplicationContext` also supports locating multiple resources by pattern through the `ResourcePatternResolver` contract when needed. This is an application-level capability beyond basic bean lookup operations.

### 7.3. `ApplicationEventPublisher`: Publishing Internal Events

The context allows application components to publish events for listeners to receive and process.

Example of a Java event:

```java
package com.example.demo.events;

public record CustomerRegisteredEvent(String customerId) {
}
```

A service using `ApplicationEventPublisher`:

```java
package com.example.demo.service;

import com.example.demo.events.CustomerRegisteredEvent;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class RegistrationService {

    private final ApplicationEventPublisher events;

    public RegistrationService(ApplicationEventPublisher events) {
        this.events = events;
    }

    public void register(String customerId) {
        // Minimal example: business registration steps omitted.
        events.publishEvent(new CustomerRegisteredEvent(customerId));
    }
}
```

Listener:

```java
package com.example.demo.events;

import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class RegistrationListener {

    @EventListener
    public void onRegistered(CustomerRegisteredEvent event) {
        System.out.println(
                "Registered customer: " + event.customerId()
        );
    }
}
```

In a Spring Boot application with an appropriately initialized context, `@EventListener` is processed by Spring infrastructure and the listener receives the event when published. Events can be ordinary Java objects; extending `ApplicationEvent` is not mandatory in modern Spring.

**Note:** Spring's default event publishing mechanism typically invokes listeners **synchronously** under standard multicaster configuration. It does not automatically turn an event into a message queue, guarantee durability across restarts, or provide transaction boundaries simply by calling `publishEvent()`. If you want asynchronous or durable messaging, you must design and configure it separately.

A basic `BeanFactory` does not include `publishEvent(...)` in its interface contract.

### 7.4. `MessageSource`: Localized Messages

An application needing internationalization can use `MessageSource`, which `ApplicationContext` also extends.

Example:

```java
import java.util.Locale;
import org.springframework.context.ApplicationContext;

public class MessageExample {

    public static String greeting(ApplicationContext context) {
        return context.getMessage(
                "greeting.hello",
                null,
                "Hello",
                Locale.forLanguageTag("en-US")
        );
    }
}
```

If the application configures a `MessageSource` with the key `greeting.hello`, Spring retrieves the message matching the locale. If not found, the example uses the default message `Hello`. How message sources and files are configured depends on how the context is built; Spring Boot usually provides auto-configuration for message bundles by convention when appropriate message sources exist.

This capability is not part of `BeanFactory`'s basic bean lookup role.

### 7.5. Context Hierarchy

Some systems have a parent context and child contexts:

```text
Parent ApplicationContext
    ├── sharedService
    └── infrastructureBean
             │
             ▼
Child ApplicationContext
    ├── webController
    └── requestHandler
```

The child context can access beans from the parent context according to bean lookup rules and hierarchy relationships, while the parent context does not by default see beans that exist only in the child.

This mechanism is useful in certain web environments or multi-context integration architectures. A simple Spring Boot application usually does not need to construct hierarchies manually.

Avoid assuming "every `@SpringBootApplication` creates multiple contexts." Depending on bootstrap setup, typically only one main application context is needed.

## 8. Lifecycle: From Bean Definition to Context Destruction

A typical lifecycle of an `ApplicationContext` using annotation configuration can be pictured as follows:

```text
Select configuration sources
  (@SpringBootApplication, @Configuration, ...)
                     │
                     ▼
Register / parse bean definitions
                     │
                     ▼
Process BeanFactoryPostProcessors
  and related annotation infrastructure
                     │
                     ▼
Register BeanPostProcessors
                     │
                     ▼
Create non-lazy singletons and inject dependencies
                     │
                     ▼
Initialize beans, callbacks, related hooks
                     │
                     ▼
ApplicationContext is ready
                     │
                     ▼
Application uses beans
                     │
                     ▼
Close context
  -> destroy appropriately managed beans
```

This sequence is a learning model. The real lifecycle has more steps: registering `BeanDefinitionRegistryPostProcessor`, setting up the event multicaster, initializing `MessageSource`, lifecycle processors, publishing context events, server startup, and post-refresh callbacks depending on context type.

### 8.1. `BeanFactoryPostProcessor` and `BeanPostProcessor`

The two similar names act on different things:

| Component | Primarily Intervenes On | Conceptual Timing |
|---|---|---|
| `BeanFactoryPostProcessor` | Metadata/bean definitions before ordinary singletons are created | Container preparation phase |
| `BeanPostProcessor` | Bean instances before/after initialization steps | Bean creation phase |

For example, Spring uses post-processing infrastructure to support annotations, proxies, and many integration features. When manually creating only a `DefaultListableBeanFactory`, you **cannot assume** all post-processors have been discovered, registered, and executed automatically.

`ApplicationContext` implementations run a refresh process that executes many of these infrastructure steps so annotation configuration works as expected.

### 8.2. Bean Initialization and Destruction Hooks

Example using `@PostConstruct` and `@PreDestroy` with Jakarta Annotations in Spring Boot 3.x:

```java
package com.example.demo.service;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Service;

@Service
public class CacheService {

    @PostConstruct
    public void initialize() {
        System.out.println("CacheService initialized");
    }

    @PreDestroy
    public void shutdown() {
        System.out.println("CacheService shutting down");
    }
}
```

When the bean is created and appropriate lifecycle annotation infrastructure is registered, `@PostConstruct` is called during initialization. When the context closes gracefully, Spring can invoke destruction callbacks for managed singletons.

In Spring Boot 3.x, the standard package is `jakarta.annotation`; older Spring Boot code may use `javax.annotation`. Behavior depends on framework and dependency versions.

Additional notes:

- Graceful context shutdown is an important condition for destruction callbacks to have a chance to run.
- Spring does not automatically track and call destruction callbacks for every `prototype` instance after handing it to the client.
- A direct `BeanFactory` can be configured to support lifecycles, but requires proper infrastructure setup. Do not infer that using the `BeanFactory` interface means "there is never a lifecycle."

### 8.3. Eager Singletons Help Catch Errors Early

If a `PaymentService` bean requires `PaymentGateway` but no matching bean exists, an application context instantiating non-lazy singletons typically fails at startup:

```text
UnsatisfiedDependencyException:
No qualifying bean of type '...PaymentGateway' available
```

Consequently, an application can **compile successfully** yet fail to start. The issue is that the container cannot construct the object graph from bean definitions, unlike a Java compiler error where a class name cannot be found in source code.

## 9. How Does Spring Boot Use `ApplicationContext`?

A Spring Boot main class is typically written as:

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

`SpringApplication.run(...)` builds the runtime environment, selects the appropriate context type, loads configuration sources, executes Spring Boot's initialization sequence, and returns a `ConfigurableApplicationContext` on success.

You can store the returned context:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(DemoApplication.class, args);

        System.out.println("Beans: " +
                context.getBeanDefinitionCount());
    }
}
```

This snippet illustrates accessing the context after startup. `getBeanDefinitionCount()` comes from the bean-definition listing capability of the deployed context; the exact count depends on dependencies, auto-configuration, profiles, and application beans.

In a typical web application, **do not close the context immediately after `run(...)`** if you want the web server to keep serving requests. When graceful shutdown is needed, Spring Boot and deployment environments provide appropriate lifecycle/shutdown hooks.

### 9.1. Why Doesn't Spring Boot Require Calling `getBean()` Everywhere?

Because Spring Boot builds an `ApplicationContext` and processes bean definitions, you can declare constructor injection:

```java
package com.example.demo.service;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
```

```java
package com.example.demo.web;

import com.example.demo.service.GreetingService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    private final GreetingService greetingService;

    public GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/greet")
    public String greet(
            @RequestParam(defaultValue = "Spring") String name
    ) {
        return greetingService.greet(name);
    }
}
```

`@SpringBootApplication` typically enables component scanning from the main class's package and its subpackages. If the two classes above lie within scanned packages, Spring registers their bean definitions and creates `GreetingController` with `GreetingService` injected.

Thus you **do not need to write**:

```java
GreetingService service = context.getBean(GreetingService.class);
```

inside the controller. The container has already provided the dependency through the constructor.

### 9.2. The `ApplicationContext` Interface and Concrete Context Types

Spring Boot can create a context suited to the application type:

- Non-web application: a context based on annotation configuration.
- Servlet application: a context suited for Servlet infrastructure and web servers.
- Reactive application: a context suited for the reactive stack.

The exact concrete class depends on Spring Boot version and configuration. Business code usually does not need to depend on the implementation class. Injecting interfaces such as `ApplicationContext`, `Environment`, `ApplicationEventPublisher`, or better yet directly injecting business dependencies, avoids unnecessary coupling.

### 9.3. Auto-Configuration Registers Additional Beans in the Context

`@SpringBootApplication` combines:

- Root application configuration.
- Component scanning.
- Spring Boot auto-configuration.

Auto-configuration can register extra bean definitions when conditions are met: the corresponding library is on the classpath, a property is enabled, or a user-defined bean does not yet exist.

Therefore, the beans inside `ApplicationContext` can include both **your beans** and **infrastructure beans auto-configured by Spring Boot**. All of them belong to the context's management system.

`ApplicationContext` **does not automatically imply auto-configuration**. A Spring Framework `AnnotationConfigApplicationContext` can run without Spring Boot. Auto-configuration comes from Spring Boot's mechanism activated and processed on that container.

## 10. Three Ways of Working with Beans and Which to Choose

### 10.1. Common Approach: Constructor Injection

```java
@Service
public class InvoiceService {

    private final TaxCalculator taxCalculator;

    public InvoiceService(TaxCalculator taxCalculator) {
        this.taxCalculator = taxCalculator;
    }
}
```

Spring creates the bean and injects the matching `TaxCalculator`. This is generally the preferred direction for business code: dependencies are explicit, easy to test in plain Java, and avoid direct dependence on container APIs.

### 10.2. `@Bean` for Objects Created via Factory Methods

```java
@Configuration(proxyBeanMethods = false)
public class TimeConfiguration {

    @Bean
    public java.time.Clock applicationClock() {
        return java.time.Clock.systemUTC();
    }
}
```

Use when an object needs one-time configuration or comes from a library that cannot be annotated directly with `@Component`.

### 10.3. Calling `getBean()` Directly When There Is a Specific Reason

```java
ApplicationContext context = /* initialized context */;
Clock clock = context.getBean(Clock.class);
```

`getBean()` has value in integration code, diagnostic tools, plugins, or places where dynamic bean lookup is genuinely required. However, if a `@Service` repeatedly calls `ApplicationContext#getBean()` to fetch dependencies it knows upfront, the dependency contract becomes obscured.

When multiple implementations must be chosen dynamically, consider suitable mechanisms such as injecting `Map<String, Strategy>`, `ObjectProvider<T>`, or qualifiers rather than defaulting to "looking up" beans through a global context.

### 10.4. Why Avoid Turning `ApplicationContext` into a Global Service Locator?

An example to reconsider:

```java
public class OrderService {

    public void createOrder() {
        PaymentGateway gateway =
                GlobalContext.getBean(PaymentGateway.class);
        gateway.charge();
    }
}
```

In this snippet, `OrderService`'s dependency does not appear on its constructor; tests or readers must know about `GlobalContext`. A clearer direction:

```java
@Service
public class OrderService {

    private final PaymentGateway paymentGateway;

    public OrderService(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }

    public void createOrder() {
        paymentGateway.charge();
    }
}
```

With constructor injection, Spring still supplies the bean, while business code depends far less on container APIs.

## 11. Bean Scopes: What Does the Container Manage?

In Spring, beans can be declared with a scope. Two foundational scopes are:

- **`singleton`**: by default, one bean instance per bean definition within a single Spring IoC container. This is not *a single JVM-wide singleton* when multiple contexts exist.
- **`prototype`**: creates a new instance for each corresponding bean request to the container.

Example:

```java
@Configuration
public class ScopeConfig {

    @Bean
    public CounterService singletonCounter() {
        return new CounterService();
    }

    @Bean
    @Scope("prototype")
    public CounterService prototypeCounter() {
        return new CounterService();
    }
}
```

With a context configured by `ScopeConfig`:

```java
CounterService one = context.getBean("singletonCounter", CounterService.class);
CounterService two = context.getBean("singletonCounter", CounterService.class);

System.out.println(one == two); // true within the same context
```

```java
CounterService first = context.getBean("prototypeCounter", CounterService.class);
CounterService second = context.getBean("prototypeCounter", CounterService.class);

System.out.println(first == second); // false, two requests
```

The example assumes `CounterService` is a class with a valid no-argument constructor. Import `@Configuration`, `@Bean`, and `@Scope` from their respective Spring packages.

### 11.1. Injecting a Prototype into a Singleton

A common point of confusion: if a singleton receives a prototype directly via constructor, the container resolves the dependency when creating the singleton, so the singleton normally holds **the exact prototype instance it received**; it does not automatically create a new instance every time the singleton calls a method.

When you genuinely need a new prototype instance per usage, consider injecting `ObjectProvider<CounterService>` or an equivalent factory to request the bean as needed.

### 11.2. Web Scopes

Spring Web also includes scopes tied to HTTP requests, sessions, or the application depending on environment and configuration. A basic manually created `BeanFactory` does not automatically have request/session scopes because these scopes require web context infrastructure.

In a Spring Boot web application, the appropriate context integrates with servlet or reactive environment capabilities. That explains why the same IoC container concept can have different available scopes and bean infrastructure.

## 12. Common Container-Related Errors

| Symptom | Causes to Consider | Resolution Approach |
|---|---|---|
| `NoSuchBeanDefinitionException` | No bean matching the requested name/type | Check component scan, `@Bean`, `@Import`, profiles, conditional config |
| `NoUniqueBeanDefinitionException` | Multiple matching beans found when one was expected | Choose `@Qualifier`, `@Primary`, or inject a suitable collection |
| `UnsatisfiedDependencyException` | Container could not resolve dependencies while creating a bean | Inspect `Caused by`: missing bean, multiple beans, or bean creation failure |
| `BeanCreationException` | Bean failed during creation or initialization | Check constructor, factory method, init callbacks, and deepest root cause |
| `BeanCurrentlyInCreationException` | Possibly related to a circular dependency while the container creates beans | Trace dependency chain and redesign relationships to avoid cycles |
| `NoSuchBeanDefinitionException` when using `BeanFactory` manually | Bean definition not yet registered | Register classes/definitions or scanning infrastructure properly |
| `@Autowired` not working in an object created with `new` | Object is not managed by Spring | Let the container create the bean or pass dependencies manually |
| Context starts up, yet controller does not appear | Wrong component scan range or bean not registered | Check main class location, packages, and annotations |
| Bean missing under another profile | Bean has profile or configuration conditions | Check active profiles and registration conditions |

### 12.1. Reading Container Errors Properly

Example log:

```text
Parameter 0 of constructor in com.example.demo.OrderService
required a bean of type 'com.example.demo.PaymentGateway'
that could not be found.
```

This error means Spring **has no matching `PaymentGateway` bean** to construct `OrderService`. It does not mean the Java compiler failed to locate the `PaymentGateway` class. If the type were unknown, Java would have failed at compilation time.

Check:

1. Is `PaymentGateway` an interface or a class?
2. Is there an implementation annotated with `@Component`/`@Service` or a `@Bean` method providing it?
3. Is the configuration/implementation class inside the scanned range or imported?
4. Is `@Profile` or `@Conditional` preventing the bean from registering?
5. Are there multiple contexts with the bean sitting in another context?

Adding `@Autowired` to a field cannot substitute for a missing bean registration step.

### 12.2. Does the Error Appear at Startup or on First Call?

For non-lazy singletons, a standard `ApplicationContext` builds them during refresh, so dependency errors can surface during startup.

For beans marked `@Lazy` or `prototype`, certain errors only occur **when the bean is actually requested**. This explains why an application can print "Started ..." yet a feature still fails when touching a bean that had not yet been instantiated.

## 13. Distinguishing `BeanFactory` and `FactoryBean`

These two names look similar, yet refer to two different things:

- **`BeanFactory`** is the interface representing the container that supplies beans.
- **`FactoryBean<T>`** is an interface that a **specialized bean** can implement so Spring knows how to create another object.

For instance, in Spring, factory beans can be used when object creation is complex and needs tight integration with the bean lifecycle.

With a bean named `sampleFactory` that is a `FactoryBean`, a regular name lookup may return the **product** created by the factory; the `&` prefix on the bean name can be used to request the **factory object itself**:

```java
Object product = context.getBean("sampleFactory");
Object factoryObject = context.getBean("&sampleFactory");
```

This is an advanced Spring container feature. You do not need to implement `FactoryBean` when you merely want an ordinary `@Bean` method. Distinguishing the names prevents confusing `BeanFactory` and `FactoryBean` as two spellings of the same interface.

## 14. Practice in Spring Boot Fundamentals

The exercises below help directly observe differences without complex systems.

### Exercise 1: Using Standalone `BeanFactory`

Create `GreetingService` without Spring annotations and with a no-arg constructor. Create `DefaultListableBeanFactory`, register a `RootBeanDefinition`, and retrieve the bean via the `BeanFactory` interface.

Observe that you **explicitly choose** how to register bean definitions; the container does not scan the whole project.

### Exercise 2: Switching to `ApplicationContext`

Create `@Configuration` with `@Bean GreetingService`, instantiate `AnnotationConfigApplicationContext`, and retrieve the bean. Use `try-with-resources` to close the context.

Explain why you do not need to call `registerBeanDefinition(...)` manually for each `@Bean`: the context's annotation configuration infrastructure handles the metadata.

### Exercise 3: Observing Eager and Lazy

Create a bean that prints a line in its constructor, initialize `AnnotationConfigApplicationContext`, and observe when the line prints. Then add `@Lazy` to the bean and compare.

Be sure the bean is not immediately required by another eager singleton at startup; if such a dependency exists, `@Lazy` may not produce the timing difference you expect.

### Exercise 4: Observing Constructor Injection

Create two classes `MessageFormatter` and `GreetingService`, having `GreetingService` require `MessageFormatter` via constructor. Register them as beans via `@Component`/`@Service` or `@Bean`, then let Spring Boot create a controller needing `GreetingService`.

Then try creating a business object with `new` outside the container and compare the responsibility of supplying dependencies manually.

### Exercise 5: Reading `Environment` and Resources

Put a property in `application.yml` and a file `messages/welcome.txt` under `src/main/resources`. Inject `ApplicationContext` into a `CommandLineRunner` or use `Environment`/`Resource` directly, then read the property and resource at startup.

Explain why these are extended services of `ApplicationContext`, beyond the need to instantiate a `GreetingService`.

### Exercise 6: Publishing Internal Events

Create a `CustomerRegisteredEvent`, a listener with `@EventListener`, and call `publishEvent(...)` from a Spring-managed service. Observe the listener running within the initialized context.

Try distinguishing publishing an in-process event in a running application from sending a message to a durable queue: internal events do not inherently provide persistence or replay guarantees.

## 15. Takeaways When Reading Spring Boot Source Code

To avoid confusing the two interfaces, view them by layer of responsibility:

```text
Business code
    │
    ├── Constructor injection
    ├── @Service / @Repository / @Controller
    └── @Bean / @Configuration
                │
                ▼
        ApplicationContext
    ├── Bean access interface
    ├── Configuration and lifecycle processing
    ├── Environment / resources
    ├── Events / MessageSource
    └── Additional Spring Boot infrastructure
                │
                ▼
        BeanFactory implementation
    ├── Bean definitions
    ├── Bean creation and lookup
    ├── Dependency resolution
    └── Scopes and core bean lifecycle
```

**`BeanFactory`** is the foundation for the container to supply beans. **`ApplicationContext`** is the application-level container interface that inherits those capabilities and extends them with services a Spring application commonly needs. Spring Boot uses an appropriate `ApplicationContext` on startup, while bean creation and management operations still build on `BeanFactory` mechanics.

When writing business code, favor **constructor injection** and clear bean definitions. When reading documentation or diagnosing startup errors, remember that `ApplicationContext` is responsible for coordinating many configuration and lifecycle stages; bean lookup itself is only one part of the IoC container's overall operation.
