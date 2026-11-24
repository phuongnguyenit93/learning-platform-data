# What Does ApplicationContext Provide Beyond BeanFactory in Spring Boot?

## 1. The Big Picture: From Bean Management to Application Context

When we first start learning Spring, we often hear that Spring is an **IoC container**: it creates objects, wires dependencies, and manages bean scopes and lifecycles. The foundation of that capability is `BeanFactory`. However, when a Spring Boot application starts with `SpringApplication.run(...)`, what the program receives is a `ConfigurableApplicationContext`, meaning an **`ApplicationContext` with lifecycle management capabilities**.

Why does Spring need a broader abstraction?

A program with many beans often also needs to:

- Read configuration according to the environment and active profiles.
- Load resources from the classpath, files, or path patterns.
- Look up localized messages by language.
- Publish events so components can coordinate with one another.
- Understand parent/child contexts if the application uses a container hierarchy.
- Trigger bean preparation steps, listeners, and startup/shutdown lifecycles.

`ApplicationContext` brings these services together on top of `BeanFactory`. Understanding the distinction accurately helps us place functionality in the right layer and understand why an application that creates beans manually does not automatically have behaviors like Spring Boot.

**Quick mental model:**

```text
SpringApplication.run(...)
           |
           v
  ConfigurableApplicationContext
           |
           +-- BeanFactory: define, create, look up, manage beans
           |
           +-- Environment: properties and profiles
           +-- MessageSource: localized messages
           +-- ResourcePatternResolver: resources and path patterns
           +-- ApplicationEventPublisher: event publishing
           +-- HierarchicalBeanFactory: parent/child contexts
           +-- Refresh / close / lifecycle: context operation
           |
           v
Application configured to begin execution
```

This is a diagram of **capabilities**, not an implication that `ApplicationContext` owns a separate object for every line. Some capabilities are inherited via interfaces, while others are implemented by internal components of the context.

## 2. Exact Interface Relationships

In Spring Framework 6.1 (the same generation as Spring Boot 3.3), the declaration of `ApplicationContext` is essentially:

```java
public interface ApplicationContext extends
        EnvironmentCapable,
        ListableBeanFactory,
        HierarchicalBeanFactory,
        MessageSource,
        ApplicationEventPublisher,
        ResourcePatternResolver {
    // Additional methods for identification, parent, and bean factory.
}
```

This snippet **abbreviates the method list** to study type relationships; it is not a file to copy into a project to redeclare the library interface.

Note: both `ListableBeanFactory` and `HierarchicalBeanFactory` belong to the `BeanFactory` branch. Therefore, an `ApplicationContext` is also a `BeanFactory` and can call `getBean(...)`, `containsBean(...)`, `getBeanProvider(...)`, or list beans via `getBeansOfType(...)`.

| Capability | Basic `BeanFactory` | `ApplicationContext` |
| --- | --- | --- |
| Look up beans by name/type | Yes, via `getBean` and related APIs | Yes, inherited |
| Manage bean scopes and lifecycle | Yes, at the bean factory/implementation level | Yes, backed by the internal bean factory |
| List bean definitions | Depends on interface/implementation, e.g., `ListableBeanFactory` | Yes, via `ListableBeanFactory` |
| Read `Environment`/active profiles | Not part of the `BeanFactory` interface contract | Yes, via `EnvironmentCapable` |
| Look up localized messages | Not part of the `BeanFactory` contract | Yes, via `MessageSource` |
| Publish application events | Not part of the `BeanFactory` contract | Yes, via `ApplicationEventPublisher` |
| Load resources from a location or pattern | Not part of the `BeanFactory` contract | Yes, via `ResourcePatternResolver` |
| Parent/child relationship | Not part of the basic contract; `HierarchicalBeanFactory` exists | Yes, via `HierarchicalBeanFactory` and `getParent()` |
| Automatic detection/registration of infrastructure beans | Can be done manually depending on implementation | Standard context implementations perform this during `refresh()` |
| Control context refresh, close, and lifecycle | Not in the basic interface | Via `ConfigurableApplicationContext` |

**Avoid misunderstanding:** `BeanFactory` does not mean a container that is "unaware of lifecycle." Implementations such as `DefaultListableBeanFactory` support scopes, `BeanPostProcessor` registration, singleton destruction, and many advanced features. The main difference lies in the integrated application services and the initialization workflow of standard `ApplicationContext` implementations.

## 3. BeanFactory Remains the Core of IoC

A `BeanFactory` knows how to return beans:

```java
Object bean = beanFactory.getBean("taskService");
```

It can manage singleton beans, prototype beans, dependencies, and lifecycle callbacks. Beans are often created on demand when using a plain `BeanFactory`, depending on the registration mechanism and initialization calls invoked.

`ApplicationContext` **does not replace** those operations with an independent bean system. It continues to use an internal bean factory. With `ConfigurableApplicationContext`, you can obtain the bean factory for special infrastructure needs:

```java
ConfigurableListableBeanFactory factory = context.getBeanFactory();
```

This snippet requires the `context` variable to have type `ConfigurableApplicationContext` and be in an appropriate state; this is an infrastructure API, not code that belongs in every service.

Most application code should prefer **constructor injection**:

```java
@Service
public class InvoiceService {
    private final PaymentGateway paymentGateway;

    public InvoiceService(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }
}
```

The snippet above illustrates a class with a dependency; `PaymentGateway` must be defined and registered as a bean in a real project. Constructor injection makes dependencies explicit and is easier to test than scattering `applicationContext.getBean(...)` across business logic.

## 4. Environment and Profiles: Knowing Which Configuration the Application Runs With

`ApplicationContext` extends `EnvironmentCapable`, so it provides `getEnvironment()` to read configuration properties and the list of profiles:

```java
Environment env = context.getEnvironment();

String name = env.getProperty("spring.application.name", "unknown");
boolean production = env.acceptsProfiles(Profiles.of("prod"));
String[] active = env.getActiveProfiles();
```

You need to import `org.springframework.core.env.Environment` and `org.springframework.core.env.Profiles`. The example uses a `context` variable already provided inside a method in the application.

This is useful when code must inspect configuration loaded from sources such as `application.properties`, YAML, environment variables, system properties, or command-line arguments. In Spring Boot, property source precedence is a separate topic; do not infer that every value comes from one specific file.

A plain `BeanFactory` **is not required** to have an `Environment` as part of its contract. You can create and attach a configuration mechanism to it yourself, but `ApplicationContext` standardizes the common access path.

**Distinguish reading from controlling:**

- `Environment#getProperty(...)` retrieves a value at the time of the call.
- `@Value` and `@ConfigurationProperties` help bind configuration into beans.
- `@Profile` and conditions decide which beans are registered while building the context.
- Changing an environment variable after the application has started **does not mean** all beans are automatically recreated or all `@ConfigurationProperties` update immediately.

A service that only needs a specific property should receive that value through appropriate configuration/injection, rather than always requiring the entire `ApplicationContext`.

## 5. MessageSource: Localized Messages

`ApplicationContext` extends `MessageSource`. It provides a mechanism to retrieve display strings based on a **message code** and a `Locale`. This is the foundation of internationalization (i18n).

Example in a Spring Boot project:

`src/main/resources/messages.properties`:

```properties
welcome=Hello, {0}!
```

`src/main/resources/messages_vi.properties`:

```properties
welcome=Xin chào, {0}!
```

`src/main/resources/messages_en.properties`:

```properties
welcome=Hello, {0}!
```

Java snippet:

```java
String message = context.getMessage(
        "welcome",
        new Object[] {"Lan"},
        Locale.forLanguageTag("vi"));

System.out.println(message);
```

Output:

```text
Xin chào, Lan!
```

Import `java.util.Locale`; assume `context` is an `ApplicationContext` in a running application. The `getMessage(...)` method does not need to query a database; it uses the configured message source bundle.

Spring Boot typically auto-configures a `MessageSource` from the appropriate resource bundles when a matching default file exists, such as `messages.properties`. In plain Spring Framework, you can declare a bean named `messageSource` (for example, `ResourceBundleMessageSource`). If no suitable message source is configured, do not expect `getMessage` to always resolve arbitrary codes.

Two commonly used signatures:

```java
// When a message source exists and the code is present:
String value = context.getMessage("welcome", args, locale);

// With fallback text if the code is not found:
String safe = context.getMessage(
        "missing.key", args, "No message available", locale);
```

`args` and `locale` here are existing variables. The variant with `defaultMessage` is useful when fallback content is permitted; the variant without a fallback may throw `NoSuchMessageException` if the code is not found.

**Note:** `MessageSource` is an i18n mechanism for messages, not a place to store business or operational settings like `server.port`. Use `Environment` and the configuration system when working with operational properties.

## 6. ResourceLoader and ResourcePatternResolver: Unified Resource Loading

`ApplicationContext` extends `ResourcePatternResolver`, and this interface extends `ResourceLoader`. Thus the context can resolve a **resource location** into a `Resource`:

```java
Resource resource = context.getResource("classpath:demo/notice.txt");

try (InputStream in = resource.getInputStream()) {
    String value = new String(in.readAllBytes(), StandardCharsets.UTF_8);
    System.out.println(value.trim());
}
```

Required imports: `org.springframework.core.io.Resource`, `java.io.InputStream`, and `java.nio.charset.StandardCharsets`; the calling method must handle or declare `IOException`.

With a Spring Boot executable JAR, `classpath:demo/notice.txt` can point to a resource inside `BOOT-INF/classes/demo/notice.txt`. Therefore, use `getInputStream()` instead of forcing a `Resource` into a `File` on the filesystem.

When you need to look up multiple resources by pattern:

```java
Resource[] files = context.getResources("classpath*:demo/*.txt");

System.out.println("resources=" + files.length);
```

`getResources(...)` is provided by `ResourcePatternResolver`; this method can throw `IOException`. The `classpath*:` prefix is used when you want to search across multiple classpath entries, whereas `classpath:` typically resolves a single specific resource. Do not assume the result count is fixed if dependencies also provide resources matching the pattern.

Selection table:

| Need | Example location | Notes |
| --- | --- | --- |
| Read a packaged file | `classpath:demo/notice.txt` | Stable when the classpath is complete |
| Read a file outside the JAR | `file:/opt/app/config/data.txt` | Must exist and have read permissions |
| Read a file relative to the working directory | `file:./config/data.txt` | Sensitive to the process cwd |
| Find multiple classpath files | `classpath*:demo/*.txt` | May return multiple `Resource` instances |
| Read a URL | `https://example.org/file.txt` | May involve network I/O; the URL must be controlled |

Although a `BeanFactory` can also manage beans of type `ResourceLoader` if you register them manually, it **does not directly expose `getResource/getResources` through the `BeanFactory` interface**. This is a difference in API contract.

**Common mistake:** the string `src/main/resources/demo/notice.txt` is a path to the source directory, not a classpath name at runtime. When running a JAR from another directory, use `classpath:demo/notice.txt`.

## 7. ApplicationEventPublisher: Components Notifying About Events

`ApplicationContext` is an `ApplicationEventPublisher`, so it can call:

```java
context.publishEvent(new OrderAccepted("ORDER-101"));
```

Assume the `OrderAccepted` class has already been defined. Since Spring Framework 4.2, the event payload can be **any object**; it is not mandatory to subclass `ApplicationEvent`. You can use a Java 17+ record:

```java
public record OrderAccepted(String orderId) { }
```

In a Spring-managed bean, a listener:

```java
@Component
class OrderListener {

    @EventListener
    public void onOrderAccepted(OrderAccepted event) {
        System.out.println("Accepted: " + event.orderId());
    }
}
```

The imports are `org.springframework.stereotype.Component` and `org.springframework.context.event.EventListener`, respectively. The listener is detected through Spring context annotation processing once the corresponding configuration is ready.

With the event `new OrderAccepted("ORDER-101")`, if the listener above is registered and the publisher operates synchronously, the line printed by the program is:

```text
Accepted: ORDER-101
```

**Key point:** Spring application events are an in-memory mechanism within the **same ApplicationContext/JVM** by default. They are not automatically Kafka, RabbitMQ, an HTTP webhook, or a durable persistent queue.

Behaviors to understand:

- `SimpleApplicationEventMulticaster` typically invokes listeners **synchronously on the publishing thread** by default. If a listener takes a long time, the caller may have to wait.
- Asynchronous execution can be configured via supported mechanisms, but you should not assume all listeners run in parallel by default.
- A listener throwing an exception can affect the publisher in synchronous mode, depending on how the multicaster handles errors.
- With database transactions, the time an event is published and the time the transaction commits are two different moments. If you need post-commit handling, look into `@TransactionalEventListener(phase = AFTER_COMMIT)` provided an appropriate transaction exists.
- Events such as `ContextRefreshedEvent` or `ContextClosedEvent` are **context lifecycle events**; they differ from business events like `OrderAccepted`.

A service whose only responsibility is publishing events should **inject `ApplicationEventPublisher`** instead of pulling in the entire context:

```java
@Service
class OrderService {

    private final ApplicationEventPublisher publisher;

    OrderService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    void accept(String orderId) {
        // Assume valid business processing has already occurred.
        publisher.publishEvent(new OrderAccepted(orderId));
    }
}
```

This is an illustrative snippet; you need to import `Service` and `ApplicationEventPublisher` and define `OrderAccepted`. Injecting a narrow interface keeps the code less coupled to infrastructure.

## 8. Parent/Child Contexts: Bean Visibility Scope

`ApplicationContext` extends `HierarchicalBeanFactory` and adds `getParent()`. When a system uses a **context hierarchy**, a child can see beans from the parent if no bean with the same name shadows them.

```text
Parent ApplicationContext
  |- bean: sharedService
  |- bean: appClock
  |
  +-- Child A
  |     |- bean: featureAController
  |     |- can look up sharedService from parent
  |
  +-- Child B
        |- bean: featureBController
        |- can look up sharedService from parent
```

The rules:

- **Lookup from child up to parent**: if a bean cannot be found in the child under the appropriate lookup mechanism, the parent can supply the bean.
- **A definition with the same name** in the child can shadow the bean name in the parent for lookups originating from the child.
- The parent **does not automatically see** beans defined solely in a child; two children do not automatically share each other's beans.
- `context.getParent()` may return `null` if there is no parent.
- `containsLocalBean(name)` checks the current context for a bean, whereas `containsBean(name)` can traverse the parent chain.
- Events published in a child can propagate up to the parent; do not assume events published in the parent are automatically sent down to every child.

Example checking the relationship:

```java
ApplicationContext parent = context.getParent();
System.out.println("hasParent=" + (parent != null));
System.out.println("localService=" +
        context.containsLocalBean("sharedService"));
```

This is code inserted into a method that already has a `context` variable. A typical Spring Boot application may use only **a single root context**; there is no requirement to build a hierarchy. Creating a hierarchy requires a clear purpose, such as isolating the web layer in a specific design or using advanced `SpringApplicationBuilder` setups.

## 9. ApplicationContext Does More Than Bundle APIs: It Standardizes Initialization

A very practical difference lies in the **`refresh()`** process.

`AbstractApplicationContext` (the common base of many contexts) actively discovers and registers infrastructure beans, invokes bean processors, prepares messages and events, and completes initialization of non-lazy singletons.

Important components:

- **`BeanFactoryPostProcessor`**: can modify or add metadata/bean definitions **before regular beans are created**. `BeanDefinitionRegistryPostProcessor` extends this role to registering bean definitions.
- **`BeanPostProcessor`**: intervenes in the initialization of each bean, enabling mechanisms such as certain types of proxies and annotation processing to operate.
- **`MessageSource`**: the context looks for a bean named `messageSource` or uses an appropriate mechanism to resolve messages, potentially delegating to the parent.
- **`ApplicationEventMulticaster`**: manages dispatching events to listeners.
- **`LifecycleProcessor`**: coordinates the lifecycle of `Lifecycle` / `SmartLifecycle` beans.
- **`ApplicationListener` and annotation-driven listeners**: discovered/registered through the corresponding infrastructure.
- **Pre-instantiation of non-lazy singletons**: singleton beans not marked as lazy are typically created before refresh completes.

When `DefaultListableBeanFactory` is used standalone, the low-level capabilities still exist, but the user must **manually configure post-processors and invoke the required phases**. In a standard context, `refresh()` performs that orchestration.

Abbreviated diagram, not a replacement for the full framework source code:

```text
ApplicationContext.refresh()
  |
  +-- Prepare context and BeanFactory
  +-- Process BeanFactoryPostProcessor / bean definitions
  +-- Register BeanPostProcessors
  +-- Initialize MessageSource
  +-- Initialize ApplicationEventMulticaster
  +-- Register ApplicationListeners
  +-- Complete instantiation of non-lazy singletons
  +-- Finish refresh, trigger LifecycleProcessor
  +-- Publish ContextRefreshedEvent
```

Different context implementations may add their own steps; a web context also prepares the web server via the appropriate hooks. This is an **application-building workflow**, not just a function to "refresh property values."

### Lazy Loading and a Common Misconception

A plain `BeanFactory` may create beans when `getBean(...)` is called. With standard contexts, `refresh()` typically initializes non-lazy singletons upfront. However:

- `@Lazy` can defer bean creation.
- Prototype beans are typically not pre-instantiated en masse.
- A lazy bean can still be created early if a non-lazy bean requires it as an actual dependency.
- Depending on configuration, some infrastructure beans must be created early to carry out startup tasks.

There is no rule that "every bean in ApplicationContext is eager" or "every bean in BeanFactory is lazy."

## 10. ConfigurableApplicationContext, Refresh, and Lifecycle

`ApplicationContext` is the interface that **provides capabilities for using** the context. To control the initialization/shutdown phases, Spring uses `ConfigurableApplicationContext` and its concrete implementations.

Example:

```java
ConfigurableApplicationContext context =
        SpringApplication.run(ContextFeaturesApplication.class, args);
```

`SpringApplication.run(...)` already prepares and refreshes the context before returning successfully. Therefore, you normally **do not call `context.refresh()` again after `run` returns**.

Related methods:

| Method / event | Meaning |
| --- | --- |
| `refresh()` | Executes the context build/initialization steps according to the implementation |
| `start()` / `stop()` | Sends lifecycle signals to lifecycle-capable beans; not equivalent to closing the context |
| `close()` | Closes the context and destroys managed singletons where appropriate |
| `isActive()` | Checks whether the context is still in an active state |
| `ContextRefreshedEvent` | Published after refresh completes |
| `ContextClosedEvent` | Published when the context closing process takes place |
| `ApplicationReadyEvent` | Spring Boot-specific event at the end of a successful startup, after appropriate runners |

**Can `refresh()` be called multiple times?** It depends on the implementation. For example, `GenericApplicationContext` (the base of `AnnotationConfigApplicationContext`) only supports refreshing once. Some contexts support repeated refreshes, but **you should not assume a Spring Boot application has a default mechanism to reload all beans at will**.

**Does changing config update automatically?** Editing `application.properties` on disk or changing environment variables does not mean `refresh()` will reload the data cleanly or that all beans will be safely recreated. Dynamic configuration refresh mechanisms in other products (if any) must be explicitly designed, have specific conditions, and are not identical to `ConfigurableApplicationContext.refresh()`.

**Closing the context does not mean the OS process stops immediately in every design.** There may still be threads not managed by the context; conversely, the JVM can exit when no non-daemon threads remain active. When running CLI/batch commands, control results, resource closing, and exit codes explicitly.

## 11. Complete Spring Boot 3.3 Example: Configuration, Messages, Resources, Events

The following example uses **Java 17 or higher**, Spring Boot 3.3, and the `spring-boot-starter` dependency. No web server is needed because the goal is to observe the capabilities of `ApplicationContext`.

### 11.1. File Structure

```text
context-features-demo/
  src/main/java/demo/context/ContextFeaturesApplication.java
  src/main/resources/application.properties
  src/main/resources/messages.properties
  src/main/resources/messages_vi.properties
  src/main/resources/demo/notice.txt
```

`src/main/resources/application.properties`:

```properties
spring.application.name=context-features-demo
spring.main.web-application-type=none
```

`src/main/resources/messages.properties`:

```properties
hello=Hello, {0}!
```

`src/main/resources/messages_vi.properties`:

```properties
hello=Xin chào, {0}!
```

`src/main/resources/demo/notice.txt`:

```text
Content from classpath
```

### 11.2. Java Code

Place the classes below in **a single file** named `ContextFeaturesApplication.java`; one class is `public`, and the remaining types are package-private, which is valid in Java 17+.

```java
package demo.context;

import java.io.InputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.event.EventListener;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class ContextFeaturesApplication {

    public static void main(String[] args) throws IOException {
        try (ConfigurableApplicationContext context =
                SpringApplication.run(ContextFeaturesApplication.class, args)) {

            String appName = context.getEnvironment().getProperty(
                    "spring.application.name", "unknown");
            System.out.println("app=" + appName);

            String viMessage = context.getMessage(
                    "hello", new Object[] {"Lan"},
                    Locale.forLanguageTag("vi"));
            System.out.println("message=" + viMessage);

            Resource resource = context.getResource(
                    "classpath:demo/notice.txt");
            try (InputStream in = resource.getInputStream()) {
                String content = new String(
                        in.readAllBytes(), StandardCharsets.UTF_8);
                System.out.println("resource=" + content.trim());
            }

            Resource[] matches = context.getResources(
                    "classpath*:demo/*.txt");
            System.out.println("resourcesFound=" + matches.length);

            context.publishEvent(new TicketIssued("T-101"));
        }
    }
}

record TicketIssued(String id) { }

@Component
class TicketListener {

    @EventListener
    public void whenIssued(TicketIssued event) {
        System.out.println("event=" + event.id());
    }
}
```

The Spring Boot Gradle plugin or Maven plugin/corresponding dependency configuration is required. If using Gradle, an example main dependency declaration is:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

Command to run when the project has the Gradle wrapper and Spring Boot plugin:

```bash
./gradlew bootRun
```

Lines printed by **the example code** in typical order, when only one `demo/*.txt` matches:

```text
app=context-features-demo
message=Xin chào, Lan!
resource=Content from classpath
resourcesFound=1
event=T-101
```

Spring Boot may print an additional banner and logs. The `resourcesFound` number in a large application depends on the entire classpath, so do not hardcode it when testing dependencies that may bring identically named resources.

**Why does the example work?**

1. `SpringApplication.run(...)` creates and refreshes the context, registering `TicketListener` via component scanning.
2. `Environment` returns `spring.application.name` from configuration.
3. `MessageSource` resolves `hello` with `Locale("vi")` from the Vietnamese bundle.
4. `ResourceLoader` reads `demo/notice.txt` from the classpath; `ResourcePatternResolver` finds the set of resources matching the pattern.
5. `ApplicationEventPublisher` publishes `TicketIssued`, and the registered listener receives the payload.
6. `try-with-resources` closes `ConfigurableApplicationContext` after the experiment, avoiding keeping the non-web demo alive unnecessarily.

If you delete `messages.properties` and leave only `messages_vi.properties`, do not assume Spring Boot will still auto-configure the message source as expected. Keep the base `messages.properties` file as the foundational bundle, then add locale-specific files.

### 11.3. Variant Using a Narrow Interface in a Service

The example above uses `ApplicationContext` directly to **demonstrate the full set of capabilities**. In business code, inject only the specific interface needed:

```java
@Service
public class GreetingService {

    private final MessageSource messageSource;

    public GreetingService(MessageSource messageSource) {
        this.messageSource = messageSource;
    }

    public String greet(String person, Locale locale) {
        return messageSource.getMessage(
                "hello", new Object[] {person}, locale);
    }
}
```

This snippet belongs in a separate `GreetingService.java` file in an appropriate package and requires importing `org.springframework.stereotype.Service`, `org.springframework.context.MessageSource`, and `java.util.Locale`. The bean name and bundle configuration must exist. This approach gives the service precise dependencies and makes it easy to mock in unit tests.

By the same principle: inject `ResourceLoader` if you only load files; `ApplicationEventPublisher` if you only publish events; `Environment` if you need to inspect properties; and inject business beans via constructor if you only need to invoke business logic.

## 12. Why Does ApplicationContext Matter When Launching Spring Boot?

Spring Boot is a layer providing configuration and automation around Spring Framework. When calling `SpringApplication.run(...)`, Boot is responsible for choosing the context, preparing the `Environment`, building property sources, running refresh, and executing subsequent phases.

Depending on `WebApplicationType`, the default context in Spring Boot 3.3 is typically:

| Type | Common context |
| --- | --- |
| `NONE` | `AnnotationConfigApplicationContext` |
| `SERVLET` | `AnnotationConfigServletWebServerApplicationContext` |
| `REACTIVE` | `AnnotationConfigReactiveWebServerApplicationContext` |

These classes are all implementations of the `ApplicationContext` hierarchy, so they all share the common capabilities covered in this lesson. Web contexts add capabilities related to the web server, request routing, and corresponding configuration. **Do not equate `ApplicationContext` with an HTTP server:** a `NONE` application still has `Environment`, `MessageSource`, resources, and events.

**Difference between launching plain Spring Framework and Spring Boot:** the `ApplicationContext` interface belongs to Spring Framework. Inferring the web application type, auto-configuring `MessageSource` from resource bundles, publishing Boot-specific events, and starter support are behaviors added by Spring Boot. Do not attribute every default Boot feature solely to the interface contract.

## 13. Comparing Context Refresh with Boot Events

Many events appear during startup. They help observe when services become ready.

An abbreviated sequence:

```text
Create SpringApplication
  -> prepare Environment and property sources
  -> create appropriate ApplicationContext
  -> load bean definitions and refresh ApplicationContext
  -> ContextRefreshedEvent
  -> ApplicationStartedEvent (Spring Boot)
  -> ApplicationRunner / CommandLineRunner
  -> ApplicationReadyEvent (Spring Boot)
```

The sequence above omits early events, callbacks, and specialized steps. Do not infer that `ContextRefreshedEvent` proves all runners have executed successfully. In Spring Boot, `ApplicationReadyEvent` is closer in meaning to startup completion.

Some listeners can be registered very early via `SpringApplication.addListeners(...)` or bootstrap mechanisms because before the context is created, regular bean listeners do not yet exist. This is also why you should not assume an `@EventListener` in a bean is active at **every** point during startup.

Useful practice:

- Use `ApplicationRunner` when you want to run logic after the context has been initialized.
- Use `ApplicationReadyEvent` when you need to react after the Boot startup process has finished.
- Use `ContextClosedEvent` or destruction callbacks to clean up resources when closing the context.
- Do not call `refresh()` repeatedly yourself to simulate a Spring Boot restart.

## 14. Distinguishing Bean Lifecycle from Context Lifecycle

The two lifecycles are related but distinct:

**Bean lifecycle** can include: creating the instance, injecting dependencies, running post-processors, the `@PostConstruct` callback, usage, and the `@PreDestroy` callback when managed/destroyed according to its scope.

**Context lifecycle** includes: creating the context, registering bean sources, refreshing, running, optionally receiving start/stop, and closing. When closing, the context typically destroys singletons it manages.

Important conditions:

- `prototype` beans typically do not have destruction callbacks automatically invoked by the container when the context closes; the consumer of the bean must manage cleanup.
- Do not assume all beans are created before `ApplicationReadyEvent`, because lazy loading configuration may leave some beans uninstantiated.
- `@PostConstruct` on a singleton does not mean the entire context is ready.
- If a bean needs to receive lifecycle events, it can use `ApplicationListener`/`@EventListener`, provided you understand registration timing and event ordering.

The purpose of `ApplicationContext` is to unify these rules into an operational unit with clear boundaries for the application.

## 15. Misconceptions and Diagnostic Pitfalls

| Symptom / false inference | What to check | Correct understanding or fix |
| --- | --- | --- |
| "`ApplicationContext` replaces `BeanFactory`" | Interface relationship | `ApplicationContext` inherits bean factory capabilities and adds application services |
| "Having a `BeanFactory` automatically handles `@EventListener` events" | Annotation-processing infrastructure registration | A plain container may require manual configuration of post-processors/listeners |
| "`getBean` finding a bean means the application is ready" | Refresh state, runners, health | Use appropriate readiness mechanisms, not just bean lookup |
| "All singletons are only created on `getBean`" | Non-lazy singletons during refresh | Standard contexts may create non-lazy singletons during refresh |
| "`refresh` means reloading YAML after the file changes" | Context type and config reload mechanism | Do not infer hot config reloading from `refresh()` |
| "`getResource` always returns a `java.io.File`" | Resource may live inside a JAR | Use `getInputStream()` to read |
| "`getResources` always returns one result" | Pattern and classpath | Check the resource count and handle zero or multiple results |
| "Without `messages_vi.properties`, translations still work" | MessageSource and fallback bundle | Declare the message bundle/locale properly |
| "Events run on a separate thread by default" | Event multicaster and executor | Default is usually synchronous; do not rely on an async assumption |
| "Spring events automatically propagate to another microservice" | JVM/context scope | Inter-service communication requires dedicated messaging/HTTP infrastructure |
| "Parent can retrieve every bean of a child" | Hierarchy lookup direction | Child looks up to parent; parent does not automatically look down to child |
| "Closing the context does not affect beans" | Lifecycle, destruction callbacks | Singletons managed by the context are cleaned up upon proper close |

A practical diagnostic workflow when Spring Boot has startup issues:

1. Confirm whether the context created/refreshed successfully; inspect the root exception in the startup logs.
2. If a bean is missing, check component scanning, `@Configuration`, `@Profile` conditions, and auto-configuration.
3. If a property is wrong, safely print or log the required value from `Environment` and check source precedence.
4. If a message is missing, check `messages.properties`, locale bundles, message codes, and `MessageSource`.
5. If a resource is missing, check the classpath/JAR, `classpath:` or `file:` prefix, and working directory.
6. If a listener is not invoked, verify it is a bean, annotations are processed, the event type matches, and publishing timing is valid.
7. If startup hangs, check non-lazy beans, post-processors, synchronous listeners, and I/O operations during refresh.
8. If a bean is not destroyed on exit, check its scope, who owns the bean, and whether the context is closed properly.

## 16. Hands-on Exercises

### Exercise A: Verify Inherited Capabilities

Based on the code in section 11, inspect these methods in your IDE:

- `getBeanDefinitionCount()` and `getBean(...)` from `ListableBeanFactory` / `BeanFactory`.
- `getEnvironment()` from `EnvironmentCapable`.
- `getMessage(...)` from `MessageSource`.
- `getResource(...)` and `getResources(...)` from `ResourceLoader` / `ResourcePatternResolver`.
- `publishEvent(...)` from `ApplicationEventPublisher`.
- `getParent()` from `ApplicationContext`.

For each method, note which **interface contract** you are using and what runtime dependencies are required. This clarifies why an `ApplicationContext` can do many things, yet business code should still inject smaller interfaces.

### Exercise B: Prove Events Can Be Synchronous by Default

Create a listener that prints the thread name using `Thread.currentThread().getName()` and a publisher that prints the thread name right before/after `publishEvent(...)`. Under the default configuration, observe that the event is handled on the calling thread. Try adding a controlled slow listener, then explain why the publisher may have to wait. Do not leave long sleeps in production applications.

### Exercise C: Check Resources After Packaging as a JAR

Package with Gradle `bootJar`, verify that `demo/notice.txt` exists under `BOOT-INF/classes`, and run with `java -jar` from a different directory. Compare:

```java
context.getResource("classpath:demo/notice.txt");
context.getResource("file:./demo/notice.txt");
```

The snippet above is illustrative code inside a method with `context`. The two locations have different lifecycles and lookup roots, so they will not always yield the same result.

### Exercise D: Distinguish Context Readiness from Bean Readiness

Register listeners for `ContextRefreshedEvent` and `ApplicationReadyEvent`; also create an `ApplicationRunner` with its own log line. Run and observe the order. Explain why a listener on `ContextRefreshedEvent` should not report that the entire system has finished all startup tasks.

## 17. Key Principles to Remember

1. **`BeanFactory` is the IoC core; `ApplicationContext` is the application context built on top of that core.**
2. The clearest additional capabilities are **`Environment`, `MessageSource`, resource/pattern loading, event publishing, and context hierarchy**.
3. For standard context implementations, **`refresh()` coordinates bean infrastructure, listeners, message source, singletons, and lifecycle**, giving the application a consistent operational state.
4. `ApplicationContext` does not automatically guarantee hot reloading of all configuration, asynchronous events, or an HTTP server; those features depend on the implementation and configuration.
5. In a Spring Boot application, let the framework build and refresh the context via `SpringApplication.run(...)`; in services, prefer **constructor injection** and narrow interfaces tailored to actual needs.

### Official Documentation

- [Spring Framework 6.1 — ApplicationContext API](https://docs.spring.io/spring-framework/docs/6.1.17/javadoc-api/org/springframework/context/ApplicationContext.html): list of inherited interfaces, methods, and capabilities.
- [Spring Framework — Additional Capabilities of ApplicationContext](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): i18n, resources, events, and hierarchy.
- [Spring Framework 6.1 — AbstractApplicationContext API](https://docs.spring.io/spring-framework/docs/6.1.17/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html): `refresh()` phases and internal infrastructure.
- [Spring Boot 3.3 — SpringApplication](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html): relationship between SpringApplication and context at startup.
