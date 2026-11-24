# Registering the Same Functionality Using Component Scan and Java Configuration

Spring Boot provides several ways to put an object into the Spring IoC container. The two most common approaches are:

- **Component scan:** annotate a class with a stereotype such as `@Component`, `@Service`, `@Repository`, or `@Controller`; Spring finds the class within the scan scope and registers the bean.
- **Java configuration:** declare a `@Bean` method in a `@Configuration` class; Spring calls the factory method and registers the object it returns.

Both approaches can register the exact same functionality. For example, an application needs a `MessageFormatter` to format greetings. We can let Spring discover `DefaultMessageFormatter` via component scan, or explicitly declare that object using `@Bean`.

The key point is that **registering a bean and implementing functionality are two separate concerns**. Component scan and Java configuration are two ways to describe which objects belong to the container, which dependencies need to be supplied, and which lifecycle Spring manages. They do not change the business logic of the object as long as they produce the same implementation with the same dependencies and configuration.

This lesson practices both equivalent registration approaches, analyzes their differences, shows how to combine them in one application, explains how to avoid accidentally creating two beans for the same functionality, and demonstrates how to verify the results with Spring Boot tests.

## 1. Practice Goal and Model

Suppose the application needs a message formatting feature:

```text
WelcomeController
        |
        v
WelcomeService
        |
        v
MessageFormatter
        |
        v
DefaultMessageFormatter
```

`WelcomeService` only needs the `MessageFormatter` contract. It does not need to know whether the object was registered via component scan or `@Bean`.

We will implement two options:

**Option A — Component scan**

```java
@Component
public class DefaultMessageFormatter implements MessageFormatter {
    // ...
}
```

Spring finds the class and creates the bean.

**Option B — Java configuration**

```java
@Configuration(proxyBeanMethods = false)
public class MessageConfiguration {

    @Bean
    MessageFormatter messageFormatter() {
        return new DefaultMessageFormatter();
    }
}
```

Spring calls the factory method and registers the returned object.

The two options are **mutually exclusive alternatives for the same bean** in this example. If both are enabled unintentionally, the application may end up with two beans implementing `MessageFormatter`, leading to injection ambiguity or a bean name conflict.

## 2. What Is a Bean in Spring?

A bean is an object instantiated, configured, and lifecycle-managed by the Spring IoC container according to registered metadata.

For example:

```java
@Component
public class WelcomeService {
}
```

The class `WelcomeService` is a Java type. When component scan finds the class and Spring registers a bean definition, the container can create an instance and manage it.

An object created with `new` inside any method does not automatically become a Spring bean:

```java
WelcomeService service = new WelcomeService();
```

This object is created and owned by the current code. Spring does not automatically inject dependencies, apply bean post-processors, or invoke destroy callbacks on it.

### 2.1. Bean Definition vs. Bean Instance

We can distinguish:

| Concept | Meaning |
| --- | --- |
| Class | Java type, e.g. `DefaultMessageFormatter` |
| Bean definition | Metadata describing the bean to create, scope, dependencies, and related attributes |
| Bean instance | Actual object created in the container |
| Bean name | Name used to look up the bean in the container |
| Dependency | Bean or value supplied to another bean |

Both component scan and `@Bean` can create bean definitions. They differ in how metadata is declared and how Spring determines the object to create.

### 2.2. Why Are There Two Registration Approaches?

Component scan is convenient when the class belongs to your application code and can be annotated with a stereotype.

Java configuration is suitable when:

- The class comes from an external library and its source cannot be modified.
- You need to invoke a constructor/factory method with specific arguments.
- You want to select an implementation based on configuration.
- You need to assemble a bean from multiple dependencies.
- You want explicit control over bean name, scope, and init/destroy methods.
- You want to keep domain or library classes free of Spring annotations.

There is no single approach that is always better. Choose the one that expresses ownership and composition most clearly.

## 3. Setting Up the Spring Boot Project

The examples use a Spring Boot project with appropriate dependencies, a compatible Java version, and a configured build tool.

A simple package structure:

```text
com.example.welcome
├── WelcomeApplication.java
├── api
│   └── WelcomeController.java
├── application
│   └── WelcomeService.java
└── formatting
    ├── MessageFormatter.java
    └── DefaultMessageFormatter.java
```

Application class:

```java
package com.example.welcome;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WelcomeApplication {

    public static void main(String[] args) {
        SpringApplication.run(WelcomeApplication.class, args);
    }
}
```

`@SpringBootApplication` combines Spring Boot configuration, auto-configuration, and component scanning features. By default, component scan starts from the package of the application class and scans down into sub-packages.

Because `api`, `application`, and `formatting` are all sub-packages of `com.example.welcome`, stereotypes in these packages can be discovered.

## 4. Creating the Functionality Contract

Create the interface:

```java
package com.example.welcome.formatting;

public interface MessageFormatter {

    String format(String name);
}
```

The interface describes the behavior clients need: accept a name and return a formatted message.

Implementation:

```java
package com.example.welcome.formatting;

public class DefaultMessageFormatter implements MessageFormatter {

    @Override
    public String format(String name) {
        String normalizedName =
                name == null || name.isBlank()
                        ? "Guest"
                        : name.trim();

        return "Hello, " + normalizedName + "!";
    }
}
```

At this point, the class has no Spring annotations. It is a plain Java class that can be instantiated directly in unit tests or registered by Spring via Java configuration.

### 4.1. Logic Does Not Depend on Registration Mechanism

The `format()` method has no knowledge of:

- Whether component scan exists.
- What the bean name is.
- Whether the object was created via `@Component` or `@Bean`.
- Which profile the application is using.

This is a desirable property: formatting logic is independent of the wiring mechanism.

## 5. Option A: Registering via Component Scan

To let Spring discover the implementation, add a stereotype:

```java
package com.example.welcome.formatting;

import org.springframework.stereotype.Component;

@Component
public class DefaultMessageFormatter implements MessageFormatter {

    @Override
    public String format(String name) {
        String normalizedName =
                name == null || name.isBlank()
                        ? "Guest"
                        : name.trim();

        return "Hello, " + normalizedName + "!";
    }
}
```

When the application context starts:

1. Spring performs component scanning within the configured scope.
2. It detects `DefaultMessageFormatter` annotated with `@Component`.
3. It registers a bean definition.
4. It creates the bean according to its scope and lifecycle.
5. The bean can be injected into collaborators requiring `MessageFormatter`.

### 5.1. Default Bean Name

With a stereotype class:

```java
@Component
public class DefaultMessageFormatter {
}
```

The default bean name is typically the class name with a lowercase first letter:

```text
defaultMessageFormatter
```

You can specify an explicit name:

```java
@Component("welcomeMessageFormatter")
public class DefaultMessageFormatter {
}
```

Do not name beans out of habit unless there is a specific lookup or disambiguation need. When injecting by type with a single candidate, you usually do not need to know the bean name.

### 5.2. Common Stereotypes

| Annotation | Typical role |
| --- | --- |
| `@Component` | General Spring-managed component |
| `@Service` | Service/application layer component |
| `@Repository` | Persistence layer component; can participate in exception translation |
| `@Controller` | Spring MVC controller returning views |
| `@RestController` | Controller with default response body semantics |
| `@Configuration` | Class declaring bean definitions and Spring configuration |

`@Service`, `@Repository`, and `@Controller` are specialized stereotypes in the Spring ecosystem. They can all be discovered by component scanning.

### 5.3. Component Scan Does Not Scan the Entire Machine

Spring does not automatically inspect every class in every package of every dependency. The scan scope is determined by:

- The package containing the default scan configuration class.
- `@ComponentScan` and its specified base packages.
- Include/exclude filters.
- Conditions and class metadata.

If an implementation lives outside the root package, you may need explicit scan configuration or an import.

## 6. Injecting the Implementation via Interface

Create the service:

```java
package com.example.welcome.application;

import com.example.welcome.formatting.MessageFormatter;
import org.springframework.stereotype.Service;

@Service
public class WelcomeService {

    private final MessageFormatter formatter;

    public WelcomeService(MessageFormatter formatter) {
        this.formatter = formatter;
    }

    public String welcome(String name) {
        return formatter.format(name);
    }
}
```

`WelcomeService` uses constructor injection. Spring locates a bean matching type `MessageFormatter` and passes it to the constructor.

With Option A, the bean found is `DefaultMessageFormatter`.

### 6.1. Do Not Call the Constructor Manually

Do not do this:

```java
@Service
public class WelcomeService {

    private final MessageFormatter formatter =
            new DefaultMessageFormatter();
}
```

This code instantiates the implementation itself, bypassing Spring's management of that dependency. If the formatter needs another bean, proxy, configuration, or lifecycle callback, the manually created object will not be wired by the container.

### 6.2. Constructor Injection Makes Dependencies Explicit

```java
public WelcomeService(MessageFormatter formatter) {
    this.formatter = formatter;
}
```

The constructor states that the service cannot operate without a formatter. For required dependencies, this is usually a clearer choice than field injection.

## 7. Creating a REST Endpoint to Observe Functionality

```java
package com.example.welcome.api;

import com.example.welcome.application.WelcomeService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WelcomeController {

    private final WelcomeService welcomeService;

    public WelcomeController(WelcomeService welcomeService) {
        this.welcomeService = welcomeService;
    }

    @GetMapping("/welcome")
    public String welcome(
            @RequestParam(defaultValue = "Guest") String name) {
        return welcomeService.welcome(name);
    }
}
```

Run the application and call:

```http
GET /welcome?name=Lan
```

Response:

```text
Hello, Lan!
```

Call:

```http
GET /welcome
```

Response:

```text
Hello, Guest!
```

Call flow:

```text
HTTP request
    |
    v
WelcomeController
    |
    v
WelcomeService
    |
    v
MessageFormatter bean
    |
    v
DefaultMessageFormatter.format(...)
```

Neither the controller nor the service needs to know how the formatter was registered.

## 8. Option B: Registering the Same Functionality with Java Configuration

Now suppose `DefaultMessageFormatter` is a library class or a class you do not want to annotate with Spring annotations. We remove `@Component` and register the object via `@Bean`.

The implementation class remains unchanged:

```java
package com.example.welcome.formatting;

public class DefaultMessageFormatter implements MessageFormatter {

    @Override
    public String format(String name) {
        String normalizedName =
                name == null || name.isBlank()
                        ? "Guest"
                        : name.trim();

        return "Hello, " + normalizedName + "!";
    }
}
```

Create the configuration:

```java
package com.example.welcome.config;

import com.example.welcome.formatting.DefaultMessageFormatter;
import com.example.welcome.formatting.MessageFormatter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class MessageConfiguration {

    @Bean
    public MessageFormatter messageFormatter() {
        return new DefaultMessageFormatter();
    }
}
```

Spring detects `MessageConfiguration` via component scan because the class sits in a sub-package of the application class. When processing the configuration, Spring registers a bean from the `messageFormatter()` method.

### 8.1. `@Configuration` and `@Bean`

- `@Configuration` marks a class containing configuration declarations.
- `@Bean` marks a method that provides an object to the Spring container.
- The return value of the method becomes a Spring-managed bean.
- The default bean name is the method name, `messageFormatter` in this example.

The client still injects:

```java
public WelcomeService(MessageFormatter formatter) {
    this.formatter = formatter;
}
```

No changes to `WelcomeService` are needed.

### 8.2. Why Does `@Bean` Return the Interface?

The method declares:

```java
@Bean
public MessageFormatter messageFormatter() {
    return new DefaultMessageFormatter();
}
```

Spring knows the bean provides the `MessageFormatter` contract. When injecting by type, the container uses the actual object type and bean metadata to resolve the dependency.

Declaring the interface as the return type expresses the contract clients need. If configuration or the framework needs access to an implementation-specific method during bean creation, declaring the concrete type may be necessary; choose a return type appropriate to the wiring and API needs.

### 8.3. Bean Name from Method

In:

```java
@Bean
public MessageFormatter messageFormatter() {
    return new DefaultMessageFormatter();
}
```

The default bean name is:

```text
messageFormatter
```

You can specify one explicitly:

```java
@Bean("welcomeFormatter")
public MessageFormatter messageFormatter() {
    return new DefaultMessageFormatter();
}
```

The method name and bean name can differ. If there are multiple aliases:

```java
@Bean({"welcomeFormatter", "defaultFormatter"})
public MessageFormatter messageFormatter() {
    return new DefaultMessageFormatter();
}
```

Both names refer to the same bean definition; Spring does not create two separate instances just because there are two aliases.

## 9. How Do Both Approaches Produce the Same Result?

In this example:

| Aspect | Component scan | Java configuration |
| --- | --- | --- |
| Implementation class | `DefaultMessageFormatter` | `DefaultMessageFormatter` |
| Registration declaration | `@Component` | `@Bean` method |
| Where Spring finds it | Component scan | Registered configuration class |
| Bean type | `MessageFormatter` | `MessageFormatter` |
| `format("Lan")` behavior | `Hello, Lan!` | `Hello, Lan!` |
| Injecting client | `WelcomeService` | `WelcomeService` |
| Bean lifecycle | Spring-managed | Spring-managed |
| Object instantiation | Spring instantiates component | Factory method returns object |

Given equivalent objects, dependencies, and configuration, the functionality observed by clients is identical.

What mainly changes is **where and how the object is declared to belong to the container**.

### 9.1. Component Scan Favors Discovery

The class declares its own role as a Spring component:

```java
@Component
public class DefaultMessageFormatter {
}
```

Spring discovers and registers the class within the scan scope.

### 9.2. Java Configuration Favors Explicit Assembly

The configuration class states clearly:

```java
@Bean
MessageFormatter messageFormatter() {
    return new DefaultMessageFormatter();
}
```

Readers can immediately see where the object is created and which dependencies are passed into the factory method.

### 9.3. Clients Should Not Depend on the Registration Mechanism

If you need to switch from component scan to Java configuration, ideally you should not have to modify services or controllers. Only change where the bean is declared, preserving the contract and behavior.

This is a good test of whether the application layer is coupled too tightly to object creation mechanics.

## 10. Avoiding Unintentional Double Registration of the Same Implementation

A common mistake is keeping `@Component` on the class while also declaring a `@Bean` method that creates a new instance:

```java
@Component
public class DefaultMessageFormatter implements MessageFormatter {
}
```

```java
@Configuration(proxyBeanMethods = false)
public class MessageConfiguration {

    @Bean
    MessageFormatter anotherFormatter() {
        return new DefaultMessageFormatter();
    }
}
```

When both are loaded, the container can have:

```text
defaultMessageFormatter
anotherFormatter
```

Both implement `MessageFormatter`.

The constructor:

```java
public WelcomeService(MessageFormatter formatter) {
    this.formatter = formatter;
}
```

can hit `NoUniqueBeanDefinitionException` because two matching beans exist.

### 10.1. Different Bean Names Do Not Merge Them into One Bean

```text
defaultMessageFormatter -> instance A
anotherFormatter        -> instance B
```

Two different bean names usually mean two different bean definitions. Do not expect Spring to notice they share the same class and merge them.

### 10.2. Same Bean Name Can Cause Conflicts

If the component is named `messageFormatter` and the `@Bean` method is also named `messageFormatter`, the two registrations can collide. Bean definition overriding behavior depends on configuration and version; Spring Boot typically disables bean definition overriding by default in standard setups.

Do not rely on scan order or overriding mechanisms to decide the implementation. Register a single clear source for each bean name and each required contract.

### 10.3. How to Migrate from Component Scan to `@Bean`

When migrating:

1. Remove the stereotype annotation from the implementation if you do not want component scan to register it automatically.
2. Add the `@Bean` method in the configuration class.
3. Keep the contract and client injection unchanged.
4. Start the context to verify only the intended bean exists.
5. Test behavior through the client.

You do not need to touch `format()` logic just because the registration style changed.

### 10.4. When Do You Intentionally Need Two Implementations?

If two beans serve different roles, such as an English formatter and a Vietnamese formatter, having two beans is valid. In that case, the client must select explicitly via qualifier, primary, or a strategy router.

The issue is not "multiple beans are always wrong," but rather **multiple candidates without an explicit selection rule at the client**.

## 11. Registering External Library Classes with `@Bean`

A key reason to use Java configuration is that you cannot add `@Component` to external classes.

Suppose a dependency provides:

```java
package com.vendor.mail;

public class VendorMailClient {

    public VendorMailClient(String endpoint, int timeoutMillis) {
        // ...
    }

    public void send(String recipient, String content) {
        // ...
    }

    public void close() {
        // Release resources
    }
}
```

You do not own this class's source and cannot add `@Component`.

Create a configuration:

```java
@Configuration(proxyBeanMethods = false)
public class MailClientConfiguration {

    @Bean(destroyMethod = "close")
    public VendorMailClient vendorMailClient(
            MailProperties properties) {

        return new VendorMailClient(
                properties.endpoint(),
                properties.timeoutMillis()
        );
    }
}
```

Spring calls the factory method, passes the bound `MailProperties`, registers the client, and calls the destroy method when the bean is closed according to lifecycle.

### 11.1. When Is Component Scan Used for External Classes?

If a library already provides a configuration class or auto-configuration, you can import or enable it per the library's documentation.

Not every class in a dependency can or should be registered via component scanning. Many libraries only ship POJOs/client factories; Java configuration is the appropriate way to assemble them.

### 11.2. Keeping Library Classes Independent of Spring

Registering with `@Bean` keeps external classes free of Spring annotations. This is useful when:

- The library is shared across multiple frameworks.
- The class is a domain object or plain Java client.
- Source code cannot be modified.
- You want to isolate integration configuration in a dedicated package.

## 12. Dependency Injection Inside a `@Bean` Method

You do not need to manually fetch dependencies from `ApplicationContext`:

```java
@Bean
public WelcomeService welcomeService(ApplicationContext context) {
    MessageFormatter formatter =
            context.getBean(MessageFormatter.class);
    return new WelcomeService(formatter);
}
```

This couples code to a service locator and hides true dependencies.

Prefer method parameter injection:

```java
@Bean
public WelcomeService welcomeService(MessageFormatter formatter) {
    return new WelcomeService(formatter);
}
```

Spring resolves `MessageFormatter` and passes it into the method.

### 12.1. Complete Configuration Example

```java
@Configuration(proxyBeanMethods = false)
public class WelcomeConfiguration {

    @Bean
    public MessageFormatter messageFormatter() {
        return new DefaultMessageFormatter();
    }

    @Bean
    public WelcomeService welcomeService(
            MessageFormatter messageFormatter) {
        return new WelcomeService(messageFormatter);
    }
}
```

In a real application, if `WelcomeService` is already registered with `@Service`, there is no need to redeclare a `@Bean` for that service. The example above merely illustrates Spring injecting dependencies into a factory method.

### 12.2. Method Parameters Express the Dependency Graph

```java
@Bean
public OrderFacade orderFacade(
        OrderService orders,
        PaymentGateway payments,
        InventoryAvailability inventory) {

    return new OrderFacade(orders, payments, inventory);
}
```

Readers immediately see the three dependencies `OrderFacade` requires. Spring also has full information to order bean creation according to the dependency graph.

## 13. `@Configuration(proxyBeanMethods = false)` and Direct Calls Between Methods

A `@Configuration` class can use:

```java
@Configuration(proxyBeanMethods = false)
```

This is lite configuration mode for processing `@Bean` methods: Spring does not need to generate a CGLIB subclass to intercept direct method-to-method calls within the configuration class.

### 13.1. Do Not Call Another `@Bean` Method Directly to Obtain a Bean

With `proxyBeanMethods = false`, the code:

```java
@Configuration(proxyBeanMethods = false)
public class AppConfiguration {

    @Bean
    MessageFormatter formatter() {
        return new DefaultMessageFormatter();
    }

    @Bean
    WelcomeService welcomeService() {
        return new WelcomeService(formatter());
    }
}
```

The call `formatter()` in Java is a normal method call. It can create a new object instead of retrieving the container-managed `formatter` bean.

As a result, unintended extra instances may be created.

### 13.2. Use Method Parameter Injection

Write:

```java
@Configuration(proxyBeanMethods = false)
public class AppConfiguration {

    @Bean
    MessageFormatter formatter() {
        return new DefaultMessageFormatter();
    }

    @Bean
    WelcomeService welcomeService(MessageFormatter formatter) {
        return new WelcomeService(formatter);
    }
}
```

Spring resolves beans according to the dependency graph and passes the managed instance into the method.

### 13.3. Full Configuration

If you use:

```java
@Configuration
public class AppConfiguration {
}
```

`proxyBeanMethods` defaults to `true`. Spring can use a proxy to intercept calls between `@Bean` methods on the configuration object to preserve container bean reference semantics.

However, parameter injection is still usually clearer and makes configuration less dependent on proxying mechanics.

### 13.4. `@Component` with `@Bean` Methods

A class not annotated with `@Configuration` that declares `@Bean` methods is processed with lite configuration semantics. Do not assume direct method calls between them are intercepted like full `@Configuration`.

If a class is responsible for assembling beans, use `@Configuration` and explicit parameter injection.

## 14. Combining Component Scan and Java Configuration in the Same Application

An application typically uses both:

```text
Spring Boot application
       |
       +--> Component scan
       |       |
       |       +--> @Service
       |       +--> @Repository
       |       +--> @RestController
       |
       +--> @Configuration
               |
               +--> @Bean: third-party client
               +--> @Bean: clock / mapper / adapter
               +--> @Bean: conditional strategy
```

Example:

```java
@Service
public class WelcomeService {

    private final MessageFormatter formatter;

    public WelcomeService(MessageFormatter formatter) {
        this.formatter = formatter;
    }
}
```

Formatter registered via component scan:

```java
@Component
public class DefaultMessageFormatter implements MessageFormatter {
}
```

An external client registered via Java configuration:

```java
@Configuration(proxyBeanMethods = false)
public class PartnerConfiguration {

    @Bean(destroyMethod = "close")
    public PartnerClient partnerClient(
            PartnerProperties properties) {
        return new PartnerClient(properties.endpoint());
    }
}
```

There is no reason to force every bean to use the same mechanism. Choose based on where the class is defined and the level of control required.

## 15. Profile-Based Registration

Suppose the application needs two formatters:

- A simple formatter for local.
- A template-engine formatter in production.

### 15.1. Component Scan Combined with `@Profile`

```java
@Component
@Profile("local")
public class SimpleMessageFormatter implements MessageFormatter {

    @Override
    public String format(String name) {
        return "Hello, " + name + "!";
    }
}
```

```java
@Component
@Profile("production")
public class TemplateMessageFormatter implements MessageFormatter {

    @Override
    public String format(String name) {
        return "Welcome, " + name + "!";
    }
}
```

### 15.2. Java Configuration Combined with `@Profile`

```java
@Configuration(proxyBeanMethods = false)
public class MessageConfiguration {

    @Bean
    @Profile("local")
    MessageFormatter localFormatter() {
        return new SimpleMessageFormatter();
    }

    @Bean
    @Profile("production")
    MessageFormatter productionFormatter(
            TemplateEngine templateEngine) {
        return new TemplateMessageFormatter(templateEngine);
    }
}
```

In the second example, `TemplateEngine` is a hypothetical dependency that has already been registered.

### 15.3. Selecting a Profile at Runtime

```bash
java -jar app.jar --spring.profiles.active=local
```

Or:

```bash
java -jar app.jar --spring.profiles.active=production
```

Spring only registers bean definitions matching the active profile.

### 15.4. Avoiding Missing or Duplicate Implementations

If no profile creates `MessageFormatter`, a service with a required injection will fail at startup.

If multiple profiles are active simultaneously and both implementations get registered, the service may encounter ambiguity.

Verify profile combinations per environment and make sure the selected implementation is deterministic.

## 16. Property-Based Registration with `@ConditionalOnProperty`

If you want to select an implementation by property instead of profile, you can use conditional beans.

```java
@Configuration(proxyBeanMethods = false)
public class MessageConfiguration {

    @Bean
    @ConditionalOnProperty(
            name = "welcome.formatter",
            havingValue = "simple",
            matchIfMissing = true
    )
    MessageFormatter simpleFormatter() {
        return new DefaultMessageFormatter();
    }

    @Bean
    @ConditionalOnProperty(
            name = "welcome.formatter",
            havingValue = "template"
    )
    MessageFormatter templateFormatter(
            TemplateEngine templateEngine) {
        return new TemplateMessageFormatter(templateEngine);
    }
}
```

`application.properties`:

```properties
welcome.formatter=simple
```

Or:

```bash
java -jar app.jar --welcome.formatter=template
```

### 16.1. Meaning of `matchIfMissing`

```java
matchIfMissing = true
```

allows the condition to match when the property is not declared. In the example, the simple formatter becomes the default choice.

If neither condition matches, the application has no `MessageFormatter` and required dependencies can fail.

### 16.2. Avoid Registering Two Implementations Simultaneously by Mistake

Conditions should be designed so that only one option matches for any valid configuration. If a property has an unexpected value, fail clearly rather than silently picking the wrong bean.

### 16.3. `@ConditionalOnProperty` Belongs to Spring Boot

This annotation is typically imported from:

```java
org.springframework.boot.autoconfigure.condition.ConditionalOnProperty
```

It is useful in application configuration and auto-configuration. For a simple condition depending only on a profile, `@Profile` can be clearer.

## 17. Multiple Beans for the Same Interface: `@Qualifier` and `@Primary`

Having multiple implementations is a legitimate need. In that case, the client must specify which bean to use.

### 17.1. Using `@Qualifier`

Component:

```java
@Component("plainFormatter")
public class PlainFormatter implements MessageFormatter {
}
```

Java configuration:

```java
@Configuration(proxyBeanMethods = false)
public class FormatterConfiguration {

    @Bean("formalFormatter")
    MessageFormatter formalFormatter() {
        return new FormalFormatter();
    }
}
```

Client:

```java
@Service
public class FormalWelcomeService {

    private final MessageFormatter formatter;

    public FormalWelcomeService(
            @Qualifier("formalFormatter")
            MessageFormatter formatter) {
        this.formatter = formatter;
    }
}
```

### 17.2. Using `@Primary`

```java
@Bean
@Primary
MessageFormatter defaultFormatter() {
    return new DefaultMessageFormatter();
}
```

When type-based injection has multiple candidates, `@Primary` designates the default preferred bean in applicable cases.

### 17.3. When Runtime Selection Is Needed

`@Qualifier` and `@Primary` resolve choices at wiring time. If the provider is chosen per request or tenant, inject a registry/map or strategy router:

```java
@Service
public class FormatterRouter {

    private final Map<String, MessageFormatter> formatters;

    public FormatterRouter(
            Map<String, MessageFormatter> formatters) {
        this.formatters = formatters;
    }

    public MessageFormatter forLanguage(String language) {
        MessageFormatter formatter = formatters.get(language);
        if (formatter == null) {
            throw new IllegalArgumentException(
                    "Unsupported language"
            );
        }
        return formatter;
    }
}
```

In a real application, normalize keys and define fallbacks. Do not feed unvalidated input directly into arbitrary bean lookups.

## 18. Lifecycle of Beans Registered in Both Ways

An important point: both component scan and `@Bean` register beans whose lifecycle is managed by Spring.

With a component:

```java
@Component
public class FileIndex {

    @PostConstruct
    void initialize() {
        // ...
    }

    @PreDestroy
    void close() {
        // ...
    }
}
```

With Java configuration:

```java
@Bean(initMethod = "initialize", destroyMethod = "close")
public FileIndex fileIndex() {
    return new FileIndex();
}
```

In both cases, Spring manages the object if the bean is created by the container.

### 18.1. Declaring Destroy Methods for Third-Party Classes

A library class has a `close()` method but no Spring annotations:

```java
@Bean(destroyMethod = "close")
VendorClient vendorClient() {
    return new VendorClient();
}
```

This is a clear advantage of Java configuration: you can attach lifecycle metadata to a class without modifying its source.

### 18.2. Do Not Confuse Beans with Manually Created Objects

If inside a `@Bean` method you create:

```java
VendorClient client = new VendorClient();
return client;
```

the returned object is a bean and Spring manages it according to configuration.

However, if the method creates another object and stores it in a static field or exposes it externally without registering a bean, that object does not automatically get its own container lifecycle.

## 19. Scope and Proxies Do Not Depend on Registration Approach

You can declare scope with a stereotype:

```java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class RequestFormatter {
}
```

Or with `@Bean`:

```java
@Bean
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
RequestFormatter requestFormatter() {
    return new RequestFormatter();
}
```

Similarly, metadata such as `@Lazy`, `@Primary`, `@DependsOn`, qualifiers, and conditions can be applied in ways appropriate to each bean definition.

### 19.1. Prototypes Are Not Destroyed Like Singletons

Spring creates prototype beans on demand, but it does not manage the full destruction lifecycle of prototype instances after handing them off to clients.

If a prototype owns a socket, thread, or resource that must be closed, the caller or factory must have explicit release responsibility.

### 19.2. Scope Should Reflect Actual Lifecycle

Do not choose prototype just to "get a new object on every injection" if the bean holds shared resources or singleton dependencies. Examine how the bean's scope and its dependencies' scopes interact.

## 20. Component Scan: Controlling Search Scope

By default, `@SpringBootApplication` scans the package of the application class and its sub-packages.

For example:

```text
com.example
├── Application.java
├── orders
│   └── OrderService.java
└── payment
    └── PaymentGatewayImpl.java
```

If `Application.java` is in `com.example`, sub-packages can be scanned.

If the application class is in `com.example.orders`, the `com.example.payment` package is not a sub-package of it.

### 20.1. Using `scanBasePackages`

```java
@SpringBootApplication(
    scanBasePackages = {
        "com.example.orders",
        "com.example.payment"
    }
)
public class OrdersApplication {
}
```

### 20.2. Using `@ComponentScan`

```java
@Configuration
@ComponentScan(basePackages = {
        "com.example.orders",
        "com.example.payment"
})
public class ApplicationComponents {
}
```

In a Spring Boot application, avoid unnecessary duplicate scan configurations. Pick one clear place to define package roots.

### 20.3. Overly Broad Scanning

Avoid:

```java
@ComponentScan("com")
```

if that scope could scan packages of dependencies or modules that do not belong to your application. It can register unintended beans, cause conflicts, or slow down startup.

Organize root packages sensibly and scan only the modules owned by the application.

## 21. Registering Java Configuration from Another Package

Configuration classes must also be brought into the context.

If located outside component scan, you can import them:

```java
@SpringBootApplication
@Import(PartnerClientConfiguration.class)
public class Application {
}
```

Or adjust scan packages according to your architecture.

### 21.1. `@Import` Fits Explicit Module Wiring

A module can expose a configuration class:

```java
@Configuration(proxyBeanMethods = false)
public class BillingModuleConfiguration {

    @Bean
    BillingService billingService(PaymentGateway gateway) {
        return new BillingService(gateway);
    }
}
```

The application composition root imports the module:

```java
@Import(BillingModuleConfiguration.class)
```

This assembles modules without scanning entire package trees.

### 21.2. Do Not Import Configurations Arbitrarily

If two configurations create beans with the same name or the same contract without qualifiers, the application context can encounter conflicts. Inspect the composition root and module enablement conditions.

## 22. Comparing When to Use Component Scan vs. `@Bean`

| Scenario | Typically suitable approach | Reason |
| --- | --- | --- |
| Application-authored service with clear role | `@Service` + component scan | Simple, close to the class |
| Application-authored repository implementation | `@Repository` + component scan | Expresses persistence stereotype |
| Controller | `@Controller` / `@RestController` | Integrates with Spring MVC |
| External library class | `@Bean` | Source cannot be modified |
| Client requiring constructor args from config | `@Bean` | Explicit wiring |
| Selecting implementation by property | `@Bean` + condition or component + condition | Controlled selection |
| Creating object from a factory method | `@Bean` | Expresses construction process |
| Pure domain object, no container needed | Do not register as bean | Can be instantiated directly |
| Multiple objects for same contract by profile | Either approach combined with profiles | Clear implementation selection |
| Dependency with a `close()` lifecycle | `@Bean(destroyMethod=...)` or suitable bean lifecycle | Manages cleanup |

These are guidelines, not rigid rules. An application class can still be created via `@Bean` when explicit assembly is needed; a library class can also be imported via an existing auto-configuration.

## 23. Java Configuration Does Not Mean Managing Objects Outside Spring

A common misconception:

```java
@Configuration
public class AppConfiguration {

    @Bean
    MessageFormatter messageFormatter() {
        return new DefaultMessageFormatter();
    }
}
```

Because the method calls `new`, some assume Spring does not manage the object. That is incorrect.

Spring invokes the factory method and registers the returned object as a bean. The container can still:

- Inject the object into other beans.
- Apply bean post-processors.
- Manage scope.
- Apply proxies when appropriate.
- Invoke initialization/destruction callbacks.

An object created with `new` **inside a factory method** still becomes a bean when returned by a `@Bean` method.

What differs is who calls the constructor and where metadata is supplied: Spring processes the bean definition through the configuration method.

## 24. When Should a Class Not Be Registered as a Bean?

Not every class belongs in the container.

For example, a value object:

```java
public record Money(
        BigDecimal amount,
        Currency currency) {
}
```

A specific `Money` instance is typically per-operation data, not a shared singleton service.

It can be created directly:

```java
Money total = new Money(amount, currency);
```

Similarly, DTOs, request models, domain events, or pure calculators without container dependencies generally do not need bean registration.

### 24.1. Identification Criteria

An object is usually suitable as a Spring bean when it:

- Is a shared collaborator in the application context.
- Has dependencies that the container should inject.
- Needs a container-managed lifecycle.
- Needs Spring-provided proxy/transaction/security/async behavior.
- Is a controller, service, repository, or infrastructure component.

An object usually does not need to be a bean when it:

- Is short-lived per-request/use-case data.
- Is cheap to instantiate and holds per-invocation values.
- Has no shared dependencies or lifecycle.
- Has clearer ownership when constructed directly.

Do not register every domain object in the context just so you can autowire them.

## 25. Verifying Beans Registered via Component Scan

You can write tests using `ApplicationContextRunner` or `@SpringBootTest`.

Minimal context test example:

```java
class ComponentScanRegistrationTest {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withUserConfiguration(ScanConfiguration.class);

    @Test
    void discoversFormatterComponent() {
        contextRunner.run(context -> {
            assertThat(context)
                    .hasSingleBean(MessageFormatter.class);
        });
    }

    @Configuration
    @ComponentScan(basePackageClasses = DefaultMessageFormatter.class)
    static class ScanConfiguration {
    }
}
```

The example requires the appropriate imports for JUnit 5, AssertJ, Spring Boot's test context runner, and `@Configuration`.

`basePackageClasses` specifies the package using a marker class, avoiding hard-coded package strings.

### 25.1. Checking the Bean Name

```java
contextRunner.run(context -> {
    assertThat(context)
            .containsBean("defaultMessageFormatter");
});
```

The default bean name is derived from the class name; if a name was specified in `@Component`, the assertion must use the actual name.

## 26. Verifying Beans Registered via Java Configuration

```java
class JavaConfigurationRegistrationTest {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withUserConfiguration(MessageConfiguration.class);

    @Test
    void registersFormatterFromBeanMethod() {
        contextRunner.run(context -> {
            assertThat(context)
                    .hasSingleBean(MessageFormatter.class);

            MessageFormatter formatter =
                    context.getBean(MessageFormatter.class);

            assertThat(formatter.format("Lan"))
                    .isEqualTo("Hello, Lan!");
        });
    }
}
```

This test verifies two things:

1. The configuration registered exactly one `MessageFormatter` bean.
2. The bean performs the expected functionality.

### 26.1. Checking the Bean Name from the Method

```java
contextRunner.run(context -> {
    assertThat(context).containsBean("messageFormatter");
});
```

If the `@Bean` method has a different name or an explicit bean name, the assertion must reflect the actual configuration.

## 27. Comparing Both Registrations with the Same Contract Test

We can write a shared test for the service:

```java
class WelcomeServiceTest {

    @Test
    void returnsFormattedWelcomeMessage() {
        MessageFormatter formatter =
                new DefaultMessageFormatter();

        WelcomeService service =
                new WelcomeService(formatter);

        assertThat(service.welcome("Lan"))
                .isEqualTo("Hello, Lan!");
    }
}
```

This test does not require Spring. It verifies the behavior of the application service and implementation.

Then, each registration mechanism gets its own context test to verify wiring.

### 27.1. Component Scan Test

Verifies that the context discovers the implementation via its stereotype.

### 27.2. Java Configuration Test

Verifies that the factory method creates a bean matching the contract and dependencies.

### 27.3. Why Separate the Two Types of Tests?

If the behavior test fails, the formatting logic is likely wrong.

If the wiring test fails, component scan, packages, profiles, or bean definitions are likely misconfigured.

The two failures belong to two different layers. Separating the tests speeds up diagnosis.

## 28. Testing the Full Application with `@SpringBootTest`

An integration test can boot a context close to the real application:

```java
@SpringBootTest
class WelcomeApplicationTest {

    @Autowired
    WelcomeService welcomeService;

    @Test
    void applicationProvidesWelcomeService() {
        assertThat(welcomeService.welcome("Lan"))
                .isEqualTo("Hello, Lan!");
    }
}
```

This test verifies the project's actual application context and the injected service.

### 28.1. Use When Integration Verification Is Needed

`@SpringBootTest` is useful when you need to verify:

- The application context can start up.
- Component scan and Java configuration work together properly.
- Actual bean wiring succeeds.
- Relevant auto-configurations behave as expected.

### 28.2. Do Not Use It for Every Unit Test

Booting the full context is much more expensive than instantiating classes directly or using a lightweight context runner. Match the test level to what you need to verify.

## 29. Diagnosing When Component Scan Fails to Find a Bean

Symptom:

```text
No qualifying bean of type 'MessageFormatter' available
```

Check:

1. Does the implementation have a stereotype?
2. Is the package within the scan scope?
3. Does component scan have an exclude filter?
4. Was the bean excluded by a profile or property condition?
5. Is the class instantiable by Spring?
6. Did a dependency error on the implementation itself prevent bean creation?
7. Was a configuration class left un-imported?

### 29.1. Fixing the Scan Package

If the class is outside the root package:

```java
@SpringBootApplication(scanBasePackages = {
        "com.example.welcome",
        "com.example.shared.formatting"
})
```

### 29.2. Using `@Import`

If a module provides a configuration class:

```java
@Import(FormattingConfiguration.class)
```

### 29.3. Do Not Add Another `@Bean` to Mask Broken Scanning

If an implementation was designed as a component, fix the scan scope. Registering the same implementation again via `@Bean` can create two beans and hide the root cause.

## 30. Diagnosing When Java Configuration Fails to Register a Bean

Symptom:

```text
No qualifying bean of type 'MessageFormatter' available
```

Check:

- Is the configuration class component-scanned or imported?
- Does the method have `@Bean`?
- Was the configuration excluded by a profile or condition?
- Did the factory method throw an exception when invoked?
- Does the return type/object satisfy the contract?
- Was the bean registered under a different name or qualifier than what the client requested?
- Is a property condition misconfigured?

### 30.1. `@Configuration` Is Not Automatically Found in Every Package

A configuration class must also be brought into the context via scanning or importing. Merely adding `@Configuration` to a class outside the scan scope does not make Spring aware of it.

### 30.2. Factory Method Is Not Called

If a condition does not match, Spring may skip registering a bean definition from that method.

Check active profiles, property sources, and condition evaluation when needed.

### 30.3. Factory Method Throws an Exception

If a `@Bean` method calls a constructor or client factory that fails, Spring may report `BeanCreationException` or a related exception. Read `Caused by` to pinpoint the failing constructor or factory operation.

## 31. Diagnosing Duplicate Beans for the Same Functionality

Common symptom:

```text
NoUniqueBeanDefinitionException:
expected single matching bean but found 2
```

Inspect bean names:

```java
String[] names =
        context.getBeanNamesForType(MessageFormatter.class);
```

In debug/test environments, you can print non-sensitive bean names:

```java
Arrays.stream(names).forEach(System.out::println);
```

Sample output:

```text
defaultMessageFormatter
messageFormatter
```

This suggests the implementation was registered via both component scan and Java configuration.

### 31.1. Pick One Registration Path

If both beans actually represent the same functionality and do not need to coexist, remove one registration path.

### 31.2. Add Qualifiers When Multiple Beans Are Truly Needed

If two formatters serve distinct purposes, name them clearly and inject the right bean.

### 31.3. Avoid Enabling Bean Overriding to Mask Conflicts

Allowing bean definition overriding can cause one registration to replace another depending on order and configuration. This makes startup results unpredictable.

Clarify bean ownership and registration conditions instead of relying on overriding.

## 32. `@Bean` Methods Can Return a Concrete Implementation or an Interface

Two examples:

```java
@Bean
MessageFormatter messageFormatter() {
    return new DefaultMessageFormatter();
}
```

and:

```java
@Bean
DefaultMessageFormatter messageFormatter() {
    return new DefaultMessageFormatter();
}
```

Both return an object that can be injected as `MessageFormatter`.

### 32.1. When Is an Interface Return Type Suitable?

When the bean is consumed through its contract and there is no need to expose implementation-specific APIs during wiring.

### 32.2. When Is a Concrete Return Type Suitable?

When configuration or other beans genuinely need the concrete type, or when the framework needs metadata/type prediction at registration time. Avoid coupling clients to concrete classes merely because a method returns a concrete type.

### 32.3. Bean Type Prediction

Spring may need to predict a bean's type before executing the factory method. Declaring a concrete return type can provide better metadata in some situations, especially when beans must be looked up by implementation type or when handling complex configurations.

For ordinary contracts, declaring an interface return type clearly communicates the abstraction clients depend on.

## 33. Bean Names, Aliases, and Qualifiers

A bean can have:

- A primary bean name.
- Aliases.
- Qualifier metadata.
- Primary status.

Example:

```java
@Bean(name = {"primaryFormatter", "welcomeFormatter"})
@Primary
MessageFormatter messageFormatter() {
    return new DefaultMessageFormatter();
}
```

Client:

```java
public WelcomeService(
        @Qualifier("primaryFormatter")
        MessageFormatter formatter) {
    this.formatter = formatter;
}
```

### 33.1. Bean Names Are Not Always the Only Qualifiers

`@Qualifier` can use qualifier metadata values, not just bean names. You can create custom qualifier annotations to express semantic roles:

```java
@Target({
        ElementType.FIELD,
        ElementType.PARAMETER,
        ElementType.METHOD,
        ElementType.TYPE
})
@Retention(RetentionPolicy.RUNTIME)
@Qualifier
public @interface Formal {
}
```

Registration:

```java
@Bean
@Formal
MessageFormatter formalFormatter() {
    return new FormalFormatter();
}
```

Injection:

```java
public ReportService(@Formal MessageFormatter formatter) {
    this.formatter = formatter;
}
```

Custom qualifiers are useful when the meaning of the selection matters more than a bean name string.

## 34. Java Configuration and Auto-Configuration

Spring Boot auto-configuration also relies heavily on Java configuration and conditional bean definitions.

For example, an auto-configuration can provide a bean when:

- A class is present on the classpath.
- A property has an appropriate value.
- The user has not already declared a matching bean.

A common pattern:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(SomeClient.class)
public class SomeClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    SomeClient someClient(SomeClientProperties properties) {
        return new SomeClient(properties.endpoint());
    }
}
```

This example only illustrates auto-configuration structure; real projects need the appropriate annotations, imports, and conditions for their framework version.

### 34.1. `@ConditionalOnMissingBean`

This condition allows an auto-configuration to provide a default bean when the user has not defined a matching bean.

It is an intentional extension mechanism: users can replace the implementation with their own bean.

### 34.2. Difference from Component Scan

Component scan discovers stereotyped classes within a scan scope.

Auto-configuration typically registers beans based on classpath conditions, properties, existing beans, and configuration ordering.

### 34.3. Do Not Write Auto-Configuration for Every Small Module

If an application only has an internal service, `@Service` or a simple `@Bean` is usually enough. Auto-configuration is better suited when building a starter or integration module with configuration APIs shared across multiple applications.

## 35. A Second Practice Exercise: Configuring `Clock`

`Clock` is a good example for Java configuration because it is a standard Java class and often needs environment- or test-specific implementations.

### 35.1. Registering with `@Bean`

```java
@Configuration(proxyBeanMethods = false)
public class TimeConfiguration {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }
}
```

Service:

```java
@Service
public class ExpirationService {

    private final Clock clock;

    public ExpirationService(Clock clock) {
        this.clock = clock;
    }

    public Instant now() {
        return clock.instant();
    }
}
```

### 35.2. Replacing with a Fixed Clock in Tests

```java
@TestConfiguration
public class FixedTimeTestConfiguration {

    @Bean
    @Primary
    Clock fixedClock() {
        return Clock.fixed(
                Instant.parse("2026-01-01T00:00:00Z"),
                ZoneOffset.UTC
        );
    }
}
```

Tests can import the test configuration to control time.

### 35.3. Why Is `ClockImpl` Unnecessary?

There is no need to create:

```java
interface ClockProvider { ... }
class ClockProviderImpl implements ClockProvider { ... }
```

if Java's `Clock` is already a suitable abstraction. You can register an instance of the standard class directly using `@Bean`.

This demonstrates how Java configuration can supply dependencies without creating custom interface/implementation pairs.

## 36. A Third Practice Exercise: Registering a Mapper

Suppose an application uses a plain Java mapper:

```java
public class OrderMapper {

    public OrderResponse toResponse(Order order) {
        return new OrderResponse(
                order.id().value(),
                order.total().amount()
        );
    }
}
```

If the mapper does not need Spring annotations, it can be registered via:

```java
@Configuration(proxyBeanMethods = false)
public class MappingConfiguration {

    @Bean
    OrderMapper orderMapper() {
        return new OrderMapper();
    }
}
```

Or if the mapper is application-managed and can carry a stereotype:

```java
@Component
public class OrderMapper {
}
```

Both approaches can provide `OrderMapper` to services.

### 36.1. Choosing by Responsibility

If the mapper is generated by an annotation processor or a library with its own factory, Java configuration may fit best.

If the mapper is a simple application-authored component that needs injected dependencies, component scan may be more concise.

If the mapper is pure, cheap to create, and has no dependencies, instantiating it directly in the appropriate scope may be enough.

Do not turn every helper class into a singleton bean just because Spring can manage it.

## 37. Organizing Configuration by Module

As an application grows, do not dump every `@Bean` into one giant file.

You can organize them as:

```text
config/
├── WebConfiguration.java
├── PersistenceConfiguration.java
├── MessagingConfiguration.java
├── PaymentConfiguration.java
└── TimeConfiguration.java
```

Each configuration should focus on one group of related beans.

### 37.1. Do Not Create a Configuration Class for a Bean Requiring No Configuration

If a service is simple:

```java
@Service
public class OrderService {
}
```

then there is no need to add an `OrderServiceConfiguration` just to return `new OrderService()`, unless there is a special wiring reason.

### 37.2. Configuration Classes Are Not for Business Logic

Avoid:

```java
@Configuration
public class OrderConfiguration {

    @Bean
    OrderService orderService() {
        // Compute pricing, write to database, send email...
        return new OrderService();
    }
}
```

Configuration is responsible for assembling objects. Business logic belongs in services and the domain.

### 37.3. Separating Property Binding

Complex configurations can use `@ConfigurationProperties`:

```java
@ConfigurationProperties(prefix = "mail")
public record MailProperties(
        URI endpoint,
        Duration timeout
) {
}
```

Register properties with `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties` according to application structure.

Then `@Bean` methods receive properties via parameter injection.

## 38. Common Pitfalls

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` | Component not scanned or configuration not imported | Check package, scan base, `@Import` |
| `No qualifying bean` | No matching implementation | Check stereotypes, `@Bean`, profiles, and conditions |
| `NoUniqueBeanDefinitionException` | Multiple beans of the same type | Pick one registration or use qualifier/primary |
| Bean definition override conflict | Two registration paths share the same bean name | Clarify ownership and remove duplicate registration |
| `@Bean` method does not run | Configuration not loaded or condition did not match | Check configuration registration |
| `NullPointerException` in service | Instantiated object with `new` and bypassed injection | Inject bean via constructor |
| Multiple unintended instances created | Direct call to `@Bean` method in lite configuration | Use method parameter injection |
| Client not closed | Missing destroy method/lifecycle | Declare `destroyMethod` or callback |
| Local profile missing formatter | Profile inactive or wrong condition | Verify runtime configuration |
| Component outside package not found | Scan scope too narrow | Use base packages or import config |
| Right bean type, wrong implementation | Unclear condition/qualifier/primary | Define explicit implementation selection rule |
| Slow context startup | Overly broad scan or heavy I/O in factory method | Narrow scan, separate startup work |

## 39. Practical Workflow for Migrating from Component Scan to Java Configuration

Suppose the current project has:

```java
@Component
public class DefaultMessageFormatter implements MessageFormatter {
}
```

You want to remove the annotation to keep the class pure Java and register it from configuration.

Steps:

### Step 1 — Identify the Bean Currently in Use

Find clients injecting `MessageFormatter` and note the current bean name/qualifier.

### Step 2 — Create the Configuration

```java
@Configuration(proxyBeanMethods = false)
public class MessageConfiguration {

    @Bean
    MessageFormatter messageFormatter() {
        return new DefaultMessageFormatter();
    }
}
```

### Step 3 — Remove the Stereotype from the Class

```java
public class DefaultMessageFormatter implements MessageFormatter {
}
```

### Step 4 — Keep the Client Unchanged

```java
public WelcomeService(MessageFormatter formatter) {
    this.formatter = formatter;
}
```

### Step 5 — Verify the Context

Confirm there is exactly one `MessageFormatter` bean and that it has the expected name.

### Step 6 — Verify Behavior

Call the service and confirm the output remains unchanged.

### Step 7 — Verify Lifecycle if Resources Exist

If the implementation opens sockets or pools, verify the destroy callback runs when the context closes.

### Step 8 — Document the Reason for Choosing Java Configuration

For example: the implementation comes from a library, needs constructor arguments, or you want to consolidate integration wiring in a module config.

Do not change registration mechanisms just to add an extra configuration layer if there is no concrete benefit.

## 40. Comprehensive Exercises

### Exercise 1 — Registering via Component Scan

Create `MessageFormatter`, `DefaultMessageFormatter`, and `WelcomeService`.

Annotate the implementation with `@Component`, start the Spring Boot context, and call the service.

Verify the bean is discovered within the component scan scope.

### Exercise 2 — Switching to Java Configuration

Remove `@Component` from the implementation, and create `MessageConfiguration` with a `@Bean` method.

Keep the service unchanged and verify the output does not change.

### Exercise 3 — Comparing Bean Names

Record the bean name when registered via component scan and when registered via `@Bean`.

Change the method name and explicit bean name, and observe the results.

### Exercise 4 — Duplicate Registration

Keep `@Component` while also adding a `@Bean` method that creates a new instance for the same interface.

Start the context and observe the ambiguity or bean name conflict. Then remove one registration path.

### Exercise 5 — Multiple Implementations

Create `PlainFormatter` and `FormalFormatter`.

Register one with component scan and one with Java configuration. Use `@Qualifier` to inject the right bean.

### Exercise 6 — Using `@Primary`

Mark one formatter as primary. Inject `MessageFormatter` without a qualifier.

Observe which implementation is selected and explain when primary is appropriate.

### Exercise 7 — Selecting via Profile

Create local and production formatters, registering them with `@Profile` under both approaches.

Run the application with different profiles and confirm which bean exists.

### Exercise 8 — Selecting via Property

Use `@ConditionalOnProperty` to choose the implementation.

Test with a missing property, `simple`, `template`, and an invalid value.

Identify when the application lacks a bean or has multiple beans.

### Exercise 9 — Registering a Library Class

Create a client class without Spring annotations whose constructor takes an endpoint and timeout.

Register it with `@Bean` and inject it into a service.

### Exercise 10 — Destroy Method

Create a fake client with `close()` and register it using:

```java
@Bean(destroyMethod = "close")
```

Close the context and verify the method is called.

### Exercise 11 — `proxyBeanMethods = false`

Create two `@Bean` methods. Try calling one method directly from the other and observe the instances created.

Then switch to method parameter injection and confirm the same bean instance is used.

### Exercise 12 — Component Scan Package

Place an implementation in a sibling package outside the application root. Observe that the bean is not found.

Fix it with `scanBasePackages` or `@Import` on the appropriate configuration.

### Exercise 13 — Testing with `ApplicationContextRunner`

Write two tests:

- One registering the component via scan.
- One registering via `@Bean`.

Assert there is exactly one bean of the type and that behavior is correct.

### Exercise 14 — Testing the Full Application

Use `@SpringBootTest` to verify the controller, service, and formatter are wired in the application context.

### Exercise 15 — Evaluating Whether a Class Needs to Be a Bean

Given `Money`, `OrderMapper`, `PaymentGateway`, `OrderService`, and `RequestDto`, decide which classes should be beans and which should be instantiated directly.

Explain based on dependencies, lifecycle, and usage scope.

### Exercise 16 — Choosing a Registration Strategy

An application has:

- A team-authored service.
- A JPA repository.
- A partner SDK.
- A `Clock`.
- Profile-specific formatters.

Propose a registration strategy for each and explain why.

### Exercise 17 — Investigating Startup Failures

Create a `@Bean` method that throws an exception when an endpoint is missing.

Read the stack trace, locate the root bean, and fix the property. Distinguish factory method errors from component scan errors.

### Exercise 18 — Refactoring Configuration

Create a configuration class containing multiple unrelated beans. Split it into module-focused configurations.

Verify the application context still starts without duplicate beans.

## 41. Key Takeaways

Component scan and Java configuration are two ways to register objects in the Spring IoC container. Component scan fits application classes with stereotypes located within the scan scope. Java configuration fits when objects must be created from factory methods, configured with constructor arguments, integrated from external libraries, or selected conditionally.

When both approaches supply the same implementation with the same dependencies, clients can consume them without modification. `WelcomeService` only depends on `MessageFormatter`; it does not need to know whether the bean came from `@Component` or `@Bean`.

Do not register the same functionality twice unless you intentionally need multiple implementations. Two beans of the same type can cause ambiguity; the same bean name can cause conflicts. When multiple beans are genuinely needed, use `@Qualifier`, `@Primary`, profiles, or conditions for explicit selection.

**Use component scan for natural discovery of application components, and use Java configuration for explicit assembly and dependency integration.** Both create Spring-managed beans; what matters is that each bean has one clear registration source, dependencies are expressed transparently, and lifecycle is handled properly.
