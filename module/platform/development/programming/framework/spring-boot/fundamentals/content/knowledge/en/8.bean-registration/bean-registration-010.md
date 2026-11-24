# Interface-Based Bean Registration and the Impact of `@Bean` Method Return Types

In a Spring Boot application, we usually want services to depend on **interfaces** rather than coupling tightly to concrete implementation classes. For example, `OrderService` only needs the ability to send notifications, so it can accept `NotificationSender`. At runtime, Spring supplies an appropriate implementation such as `EmailNotificationSender` or `ConsoleNotificationSender`.

There are two related but distinct decisions:

- **Interface-based bean registration:** the application exposes an object fulfilling a contract so other components can consume that contract.
- **Declaring the `@Bean` method return type:** tells Spring what type the factory method commits to returning. This return type affects Spring's type prediction and type-based bean lookup while the container prepares to construct other objects.

For instance, both of the following methods can return the exact same `EmailNotificationSender` object:

~~~java
@Bean
EmailNotificationSender emailNotificationSender() {
    return new EmailNotificationSender();
}
~~~

and:

~~~java
@Bean
NotificationSender notificationSender() {
    return new EmailNotificationSender();
}
~~~

However, the bean type metadata Spring can infer before invoking the factory method is not the same. This difference matters when another bean requests a dependency by interface or by concrete implementation class.

This lesson moves from interface contracts, bean registration approaches, and Spring's type prediction to autowiring scenarios, `@Qualifier`, `@Primary`, and choosing the right return type.

## 1. An Interface Is a Contract That a Bean Can Fulfill

Suppose a system needs to send notifications after creating an order. The business logic only needs a send operation:

~~~java
package com.example.notification;

public interface NotificationSender {
    void send(String recipient, String message);
}
~~~

`NotificationSender` describes the **capability** the application requires. It does not say whether notifications go via email, console, SMS, or an external service.

One implementation prints to the console:

~~~java
package com.example.notification;

public class ConsoleNotificationSender implements NotificationSender {

    @Override
    public void send(String recipient, String message) {
        System.out.println("[CONSOLE] To " + recipient + ": " + message);
    }
}
~~~

Another implementation can send email:

~~~java
package com.example.notification;

public class EmailNotificationSender implements NotificationSender {

    @Override
    public void send(String recipient, String message) {
        System.out.println("[EMAIL] To " + recipient + ": " + message);
        // In a real application, this could invoke a mail gateway.
    }
}
~~~

Both classes implement the same interface, so consumers can work with the shared type:

~~~java
public class OrderService {
    private final NotificationSender notificationSender;

    public OrderService(NotificationSender notificationSender) {
        this.notificationSender = notificationSender;
    }

    public void orderCreated(String customerEmail) {
        notificationSender.send(customerEmail, "Your order was created.");
    }
}
~~~

`OrderService` does not need to import or directly instantiate `EmailNotificationSender`. It depends solely on the `NotificationSender` contract. This design allows swapping implementations without modifying business logic.

~~~mermaid
classDiagram
    class NotificationSender {
        <<interface>>
        +send(recipient, message)
    }
    class ConsoleNotificationSender {
        +send(recipient, message)
    }
    class EmailNotificationSender {
        +send(recipient, message)
    }
    class OrderService {
        -NotificationSender notificationSender
        +orderCreated(customerEmail)
    }
    NotificationSender <|.. ConsoleNotificationSender
    NotificationSender <|.. EmailNotificationSender
    OrderService --> NotificationSender
~~~

An interface is a type by which a bean can be injected. However, Spring can only supply a bean if an implementation is registered and the candidate satisfies resolution rules.

## 2. Registering Beans via Component Scan

One way to register an implementation is annotating the class with a component annotation:

~~~java
package com.example.notification;

import org.springframework.stereotype.Component;

@Component
public class ConsoleNotificationSender implements NotificationSender {

    @Override
    public void send(String recipient, String message) {
        System.out.println("[CONSOLE] To " + recipient + ": " + message);
    }
}
~~~

Spring component scan can discover the class and register a bean definition for it, provided its package is within scan scope and no exclusion condition applies.

Common stereotype annotations:

| Annotation | Role |
| --- | --- |
| `@Component` | General Spring-managed component |
| `@Service` | Component representing the service/business layer |
| `@Repository` | Data access component |
| `@Controller` | Spring MVC controller |
| `@RestController` | Controller returning response bodies |
| `@Configuration` | Class declaring Spring configuration and `@Bean` factory methods |

Once `ConsoleNotificationSender` is registered, Spring can inject it into a constructor requesting `NotificationSender`:

~~~java
@Service
public class OrderService {
    private final NotificationSender notificationSender;

    public OrderService(NotificationSender notificationSender) {
        this.notificationSender = notificationSender;
    }
}
~~~

Spring searches for a bean compatible with `NotificationSender`. Because `ConsoleNotificationSender` implements that interface, the bean satisfies the injection point.

Here, the implementation class exposes its concrete type clearly in component metadata. By contrast, when using a `@Bean` factory method, Spring must infer the bean's type from the method declaration.

## 3. Registering Beans via `@Bean` Methods

When you need to instantiate objects manually, configure a third-party library, or control initialization, you can use `@Bean`.

~~~java
package com.example.notification;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class NotificationConfiguration {

    @Bean
    public NotificationSender notificationSender() {
        return new ConsoleNotificationSender();
    }
}
~~~

The `notificationSender()` method is a factory method. Spring invokes it to obtain the object and manages the returned object as a bean.

Points to note:

- `@Configuration` marks the class containing bean configuration.
- `@Bean` marks a method supplying a bean to the container.
- The method name typically becomes the default bean name: `notificationSender`.
- The method's declared return type is `NotificationSender`.
- The actual object returned is `ConsoleNotificationSender`.

This is abstraction-based bean registration: the configuration advertises the bean via the `NotificationSender` interface. Consumers can request the interface without knowing the implementation.

### 3.1. Registering by Interface Does Not Mean the Actual Object Is an Interface

An interface cannot be instantiated with `new`. In:

~~~java
@Bean
public NotificationSender notificationSender() {
    return new ConsoleNotificationSender();
}
~~~

the actual object is still an instance of `ConsoleNotificationSender`. Declaring the return type `NotificationSender` does not turn the object into an interface instance; it simply declares the type advertised by the factory method.

You can visualize this as:

~~~text
@Bean method
notificationSender()
        │
        │ declared return type
        ▼
NotificationSender
        │
        │ actually returns
        ▼
new ConsoleNotificationSender()
        │
        ▼
Spring-managed object
~~~

Once the object is instantiated, Spring can observe its actual runtime type in applicable situations. However, **before invoking the factory method**, the container must predict the bean type from metadata, and the method's declared return type is a critical piece of that information.

## 4. How Does `@Bean` Return Type Affect Type Prediction?

Spring needs to know bean types to resolve dependencies by type. In an application, the container might have to instantiate `OrderService` and find a bean satisfying its `NotificationSender` constructor parameter. It reads metadata to determine which beans are eligible candidates.

Consider two factory methods:

**Method A — declaring the interface type**

~~~java
@Bean
public NotificationSender notificationSender() {
    return new ConsoleNotificationSender();
}
~~~

**Method B — declaring the concrete implementation type**

~~~java
@Bean
public ConsoleNotificationSender notificationSender() {
    return new ConsoleNotificationSender();
}
~~~

Both return the same implementation, yet their method signature metadata differs:

| Characteristic | Method A | Method B |
| --- | --- | --- |
| Declared return type | `NotificationSender` | `ConsoleNotificationSender` |
| Contract explicitly advertised | Interface | Concrete class |
| Can Spring predict the interface type from signature? | Yes | Yes, because the class implements the interface |
| Can Spring predict the concrete class from signature? | Not guaranteed from interface type alone | Yes |
| Suitable for interface injection | Yes | Yes |
| Can use signature metadata to satisfy concrete-class injection before calling factory method? | Not guaranteed | Yes |

Key takeaways:

- When the return type is `NotificationSender`, Spring knows the bean provides the `NotificationSender` contract.
- When the return type is `ConsoleNotificationSender`, Spring knows the bean has that concrete type; since the class implements `NotificationSender`, it can also satisfy interface dependencies.
- If a bean requires `ConsoleNotificationSender` while the factory method only declares `NotificationSender`, the container may not predict the concrete implementation at the stage where candidates must be decided.

**Do not rely on Spring discovering the runtime type after the factory method has been invoked when designing concrete-class dependencies.** An eager bean might be created along some startup path before another resolution runs, yet initialization order is not a stable contract to depend upon. Metadata-based type prediction needs sufficient information upfront.

### 4.1. Interface Injection Case: Interface Return Type Fits Well

Configuration:

~~~java
@Configuration
public class NotificationConfiguration {

    @Bean
    public NotificationSender notificationSender() {
        return new ConsoleNotificationSender();
    }
}
~~~

Service:

~~~java
@Service
public class OrderService {
    private final NotificationSender sender;

    public OrderService(NotificationSender sender) {
        this.sender = sender;
    }
}
~~~

This is a consistent pair:

- The factory method advertises `NotificationSender`.
- The service requests `NotificationSender`.
- The actual object implements the interface.
- Spring has enough declared type information to resolve the dependency by contract.

If the application has no other same-type beans or qualifiers causing ambiguity, injection succeeds.

### 4.2. Implementation Injection Case: Interface Return Type May Be Too Broad

Suppose another service wants to call an API specific to `ConsoleNotificationSender`:

~~~java
@Service
public class ConsoleDiagnosticsService {
    private final ConsoleNotificationSender sender;

    public ConsoleDiagnosticsService(ConsoleNotificationSender sender) {
        this.sender = sender;
    }
}
~~~

while the configuration remains:

~~~java
@Bean
public NotificationSender notificationSender() {
    return new ConsoleNotificationSender();
}
~~~

At runtime, the factory method would return a `ConsoleNotificationSender`. Yet the method signature only advertises `NotificationSender`. When Spring analyzes candidates from metadata, the concrete class may still be unknown. Injection requesting `ConsoleNotificationSender` can therefore fail with no matching bean found.

If injecting by concrete implementation is truly required, declare the concrete return type:

~~~java
@Bean
public ConsoleNotificationSender notificationSender() {
    return new ConsoleNotificationSender();
}
~~~

Now Spring knows both the concrete class and every interface it implements. Injection by `ConsoleNotificationSender` and by `NotificationSender` are both supported.

Even so, if a service only needs to send notifications, **prefer injecting the interface**. Inject a concrete implementation only when there is a clear reason to depend on class-specific APIs.

### 4.3. Note on Actual Type and Bean Creation Timing

Spring includes mechanisms for bean type prediction and factory method introspection. Once a bean has been instantiated, the container can learn its runtime class. Some cases can succeed if another bean happened to be instantiated earlier.

However, creation order depends on the dependency graph and internal container mechanics; never rely on a bean happening to instantiate early to compensate for an overly broad method signature.

A solid design rule is:

> Declare a `@Bean` return type specific enough to expose the types the container needs to recognize before bean instantiation; at consumption sites, prefer depending on an interface aligned with the responsibility.

If a factory method returns an interface to hide the implementation, keep injection points using that interface too. If an integration genuinely requires the concrete class, expose a bean definition with an appropriately specific declared type or design a better abstraction.

## 5. Complete Example: Service Injecting by Interface

Let's build a small Spring Boot application:

~~~text
notification-demo/
└── src/main/java/com/example/demo/
    ├── DemoApplication.java
    ├── NotificationSender.java
    ├── ConsoleNotificationSender.java
    ├── NotificationConfiguration.java
    ├── OrderService.java
    └── OrderController.java
~~~

### 5.1. Interface `NotificationSender.java`

~~~java
package com.example.demo;

public interface NotificationSender {
    void send(String recipient, String message);
}
~~~

### 5.2. Implementation `ConsoleNotificationSender.java`

~~~java
package com.example.demo;

public class ConsoleNotificationSender implements NotificationSender {

    @Override
    public void send(String recipient, String message) {
        System.out.println("[CONSOLE] " + recipient + ": " + message);
    }
}
~~~

The class has no `@Component` because the bean will be created via a `@Bean` method.

### 5.3. Configuration `NotificationConfiguration.java`

~~~java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class NotificationConfiguration {

    @Bean
    public NotificationSender notificationSender() {
        return new ConsoleNotificationSender();
    }
}
~~~

The return type is the interface because the whole application only needs the notification contract.

### 5.4. Service `OrderService.java`

~~~java
package com.example.demo;

import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private final NotificationSender notificationSender;

    public OrderService(NotificationSender notificationSender) {
        this.notificationSender = notificationSender;
    }

    public String createOrder(String customerEmail) {
        notificationSender.send(customerEmail, "Your order has been created.");
        return "Order created for " + customerEmail;
    }
}
~~~

The service depends on the interface. It does not need to know whether the actual object is a console sender or an email sender.

### 5.5. Controller `OrderController.java`

~~~java
package com.example.demo;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
public class OrderController {
    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    public String create(@RequestParam String email) {
        return orderService.createOrder(email);
    }
}
~~~

The controller depends on `OrderService`. It does not manually instantiate the service or sender with `new`.

### 5.6. Startup Class `DemoApplication.java`

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Place configurations and components in `com.example.demo` or subpackages so default component scan discovers them.

### 5.7. Dependency Flow

~~~mermaid
flowchart TD
    A["Spring ApplicationContext"] --> B["NotificationConfiguration"]
    B --> C["BeanDefinition: notificationSender"]
    C --> D["ConsoleNotificationSender instance"]
    D -.-> E["NotificationSender interface"]
    E --> F["Inject into OrderService"]
    F --> G["OrderService bean"]
    G --> H["Inject into OrderController"]
    H --> I["HTTP request /orders"]
    I --> G
    G --> D
~~~

The diagram shows the bean factory method supplying the implementation, the container managing the object, and injecting it by interface. When a request arrives, the controller calls the service, and the service calls the sender through the contract.

### 5.8. Run and Observe

In a Maven project with `spring-boot-starter-web` and the Spring Boot Maven plugin:

~~~bash
mvn spring-boot:run
~~~

Send a request:

~~~bash
curl -X POST "http://localhost:8080/orders?email=lan@example.com"
~~~

Expected response:

~~~text
Order created for lan@example.com
~~~

In the server console:

~~~text
[CONSOLE] lan@example.com: Your order has been created.
~~~

The output proves the request path used the service and sender wired in the context. This demonstrates dependency wiring; creating an order here does not persist data to a database.

## 6. Swapping Implementations Without Modifying the Service

A major advantage of interface-based bean registration is being able to swap implementations in configuration.

Suppose we want to use an email sender. Add the class:

~~~java
package com.example.demo;

public class EmailNotificationSender implements NotificationSender {

    @Override
    public void send(String recipient, String message) {
        System.out.println("[EMAIL] " + recipient + ": " + message);
    }
}
~~~

Update the factory method:

~~~java
@Bean
public NotificationSender notificationSender() {
    return new EmailNotificationSender();
}
~~~

`OrderService` needs no changes:

~~~java
public OrderService(NotificationSender notificationSender) {
    this.notificationSender = notificationSender;
}
~~~

The reason is that the service knows only the contract. The container still supplies a bean matching `NotificationSender`, just backed by a different object.

~~~text
Run 1:
NotificationConfiguration
        │
        ▼
ConsoleNotificationSender
        │ implements
        ▼
NotificationSender
        │ inject
        ▼
OrderService

Run 2:
NotificationConfiguration
        │
        ▼
EmailNotificationSender
        │ implements
        ▼
NotificationSender
        │ inject
        ▼
OrderService
~~~

This applies **program to an interface** and Dependency Injection: business logic does not change when how a capability is implemented is swapped.

## 7. When Multiple Beans Implement the Same Interface

Once multiple implementations are registered, Spring may find several candidates for a single injection point.

Example:

~~~java
@Bean
public NotificationSender consoleSender() {
    return new ConsoleNotificationSender();
}

@Bean
public NotificationSender emailSender() {
    return new EmailNotificationSender();
}
~~~

Both beans have declared type `NotificationSender`. A service:

~~~java
@Service
public class OrderService {
    public OrderService(NotificationSender sender) {
        // ...
    }
}
~~~

may fail because the container does not know which bean to pick.

A common error message looks like:

~~~text
NoUniqueBeanDefinitionException:
No qualifying bean of type 'NotificationSender' available:
expected single matching bean but found 2
~~~

This is a **candidate selection** issue, not a bug with interfaces or `@Bean` return types.

### 7.1. Selecting with `@Qualifier`

You can specify the exact bean:

~~~java
@Bean
@Qualifier("primaryNotification")
public NotificationSender consoleSender() {
    return new ConsoleNotificationSender();
}

@Bean
@Qualifier("emailNotification")
public NotificationSender emailSender() {
    return new EmailNotificationSender();
}
~~~

Injection:

~~~java
@Service
public class OrderService {
    private final NotificationSender sender;

    public OrderService(
            @Qualifier("emailNotification") NotificationSender sender) {
        this.sender = sender;
    }
}
~~~

`@Qualifier` filters candidates by qualifier. Bean names can also act as default qualifiers in appropriate scenarios, though explicit qualifiers communicate intent better in complex setups.

### 7.2. Selecting with `@Primary`

If one implementation is the default choice when multiple candidates exist:

~~~java
@Bean
@Primary
public NotificationSender consoleSender() {
    return new ConsoleNotificationSender();
}

@Bean
public NotificationSender emailSender() {
    return new EmailNotificationSender();
}
~~~

When an injection requests a `NotificationSender` without a specific qualifier, `@Primary` tells Spring to prefer the console bean.

`@Primary` does not remove the other bean and does not force every injection point to use the primary bean. An explicit qualifier can still choose another candidate.

### 7.3. Injecting All Implementations via Collection

If business logic needs to invoke multiple senders:

~~~java
@Service
public class BroadcastService {
    private final List<NotificationSender> senders;

    public BroadcastService(List<NotificationSender> senders) {
        this.senders = senders;
    }

    public void broadcast(String recipient, String message) {
        for (NotificationSender sender : senders) {
            sender.send(recipient, message);
        }
    }
}
~~~

Spring can inject a collection containing all matching beans. Here the request is no longer "choose one bean", but "gather all candidates". Collection ordering can be affected by bean/order metadata; if order carries business meaning, declare and control it explicitly.

## 8. Bean Name and Return Type Are Two Distinct Pieces of Information

In:

~~~java
@Bean
public NotificationSender notificationSender() {
    return new ConsoleNotificationSender();
}
~~~

Spring normally registers the bean with name `notificationSender` and declared type `NotificationSender`.

You can change the name:

~~~java
@Bean("consoleSender")
public NotificationSender notificationSender() {
    return new ConsoleNotificationSender();
}
~~~

Or:

~~~java
@Bean(name = {"consoleSender", "defaultSender"})
public NotificationSender notificationSender() {
    return new ConsoleNotificationSender();
}
~~~

Bean names support name-based lookup and can participate in candidate selection where appropriate. **Changing the bean name does not change the declared return type**: in these examples, the advertised type remains `NotificationSender`.

Similarly, renaming the method does not turn an interface into a concrete class. When designing, separate:

- **Bean name:** identifier of the bean in the container.
- **Declared return type:** type advertised by the method to the container.
- **Runtime type:** actual class of the returned object.
- **Qualifier/Primary:** metadata assisting bean selection among candidates.

These four elements are related yet answer different questions.

## 9. `@Bean` Return Type and Pre-Instantiation Type Prediction

Spring must resolve dependencies even before every bean has been created. If a factory method declares an overly general return type, the container may lack information about the implementation.

Consider:

~~~java
@Bean
public Object notificationSender() {
    return new ConsoleNotificationSender();
}
~~~

The return type `Object` does not reveal the `NotificationSender` contract in the method signature. Although the actual object implements `NotificationSender`, Spring has less information when predicting the bean's type prior to calling the factory method.

If a service needs:

~~~java
OrderService(NotificationSender sender)
~~~

do not declare the factory method to return `Object`. Use:

~~~java
@Bean
public NotificationSender notificationSender() {
    return new ConsoleNotificationSender();
}
~~~

Or if the application has a valid reason to expose the concrete class:

~~~java
@Bean
public ConsoleNotificationSender notificationSender() {
    return new ConsoleNotificationSender();
}
~~~

### 9.1. Why Should You Avoid Returning `Object` or an Overly Generic Type?

Overly general return types can hinder:

- Candidate analysis by interface.
- Candidate analysis by concrete class.
- Determining generic type metadata.
- Auto-configuration or autowiring of related dependencies before instantiation.

In some situations Spring can infer additional type info from the factory method or instantiated object afterward. Still, never rely on that as justification for overly broad return declarations.

**Declare the most accurate and meaningful return type that consumers need recognized.** If only the abstraction is needed, use the interface; if there is a legitimate need for the concrete type, advertise the concrete type.

### 9.2. Does Returning an Interface Lose the Implementation?

No. The runtime object retains its actual class. You can observe:

~~~java
Object bean = applicationContext.getBean("notificationSender");
System.out.println(bean.getClass().getName());
~~~

In the example, the runtime result may be:

~~~text
com.example.demo.ConsoleNotificationSender
~~~

Yet observing the runtime type **after the object exists** differs from predicting the bean's type **before calling the factory method**. Do not conclude that because `getClass()` shows the implementation, concrete-class injection will always resolve reliably from the start.

## 10. Factory Methods Returning a Generic Interface

In some applications, interfaces carry type parameters:

~~~java
public interface Store<T> {
    void save(T value);
}
~~~

Implementation:

~~~java
public class StringStore implements Store<String> {
    @Override
    public void save(String value) {
        System.out.println("Save: " + value);
    }
}
~~~

Factory method:

~~~java
@Bean
public Store<String> stringStore() {
    return new StringStore();
}
~~~

The return type `Store<String>` gives Spring useful generic metadata when matching beans by generic type at eligible injection points.

Example:

~~~java
@Service
public class MessageArchive {
    private final Store<String> store;

    public MessageArchive(Store<String> store) {
        this.store = store;
    }
}
~~~

If the factory method declares only `Store<?>` or raw `Store`, generic information is less precise. When an application has multiple beans sharing an interface with different type arguments, generic types can disambiguate candidates.

Example:

~~~java
@Bean
Store<String> stringStore() {
    return new StringStore();
}

@Bean
Store<Integer> integerStore() {
    return new IntegerStore();
}
~~~

`IntegerStore` is an assumed implementation of `Store<Integer>`. Spring can use generic type metadata in matching autowiring scenarios to distinguish `Store<String>` from `Store<Integer>`.

Do not omit generic signatures when they are meaningful to the bean contract. Specific return types help both the compiler and the container understand what kind of data the factory supplies.

## 11. `@Bean` Methods in `@Configuration` and Calls Between Factory Methods

A `@Configuration` class can contain multiple factory methods:

~~~java
@Configuration
public class NotificationConfiguration {

    @Bean
    public MessageFormatter messageFormatter() {
        return new VietnameseMessageFormatter();
    }

    @Bean
    public NotificationSender notificationSender() {
        return new ConsoleNotificationSender();
    }
}
~~~

When one bean needs another bean, the cleanest way is declaring the dependency as a method parameter:

~~~java
@Configuration
public class NotificationConfiguration {

    @Bean
    public MessageFormatter messageFormatter() {
        return new VietnameseMessageFormatter();
    }

    @Bean
    public NotificationSender notificationSender(MessageFormatter formatter) {
        return new FormattedNotificationSender(formatter);
    }
}
~~~

`FormattedNotificationSender` is an assumed class implementing `NotificationSender` and taking `MessageFormatter` in its constructor.

Spring resolves the `formatter` parameter as a dependency of the bean being created. This states the relationship explicitly and avoids manually calling configuration methods to obtain beans.

### 11.1. Full `@Configuration` and Lite Mode

With full `@Configuration`, Spring typically enhances the configuration class via CGLIB to intercept calls between `@Bean` methods. Thus, when one `@Bean` method calls another `@Bean` method in the same class, Spring can return the container-managed bean rather than creating a brand-new object as an ordinary Java call would.

Example:

~~~java
@Configuration
public class FullConfiguration {

    @Bean
    public MessageFormatter formatter() {
        return new VietnameseMessageFormatter();
    }

    @Bean
    public NotificationSender sender() {
        return new FormattedNotificationSender(formatter());
    }
}
~~~

In full configuration mode, calling `formatter()` inside another factory method is handled through Spring's enhancement to reference the container-managed bean.

If a `@Bean` method sits in a class not processed as full `@Configuration` (lite mode), direct Java calls between methods are not necessarily intercepted. They can create new objects and violate singleton sharing intent.

To keep code clear and independent of enhancement mode, use factory method parameters:

~~~java
@Bean
public NotificationSender sender(MessageFormatter formatter) {
    return new FormattedNotificationSender(formatter);
}
~~~

This makes dependencies explicit and keeps bean management straightforward to read and maintain.

## 12. `@Bean` Methods Can Return a Concrete Type While Injecting via Interface

This is often a flexible approach when you want to give the container full type metadata while preserving abstraction at consumption sites.

Example:

~~~java
@Configuration
public class NotificationConfiguration {

    @Bean
    public ConsoleNotificationSender consoleNotificationSender() {
        return new ConsoleNotificationSender();
    }
}
~~~

In the service:

~~~java
@Service
public class OrderService {
    private final NotificationSender sender;

    public OrderService(NotificationSender sender) {
        this.sender = sender;
    }
}
~~~

Because `ConsoleNotificationSender` implements `NotificationSender`, the container recognizes the bean under the interface too. The service remains decoupled from the implementation.

This yields a helpful rule of thumb:

- **Factory method:** can return the concrete implementation to give full type metadata.
- **Consumer/service:** should accept the interface to keep coupling low.

However, you do not always have to declare the concrete implementation if the abstraction alone suffices and nothing injects by concrete class. Returning an interface in that situation is a valid, intentional choice.

## 13. Registering Multiple Implementations by Profile or Condition

An application may need different implementations in local, test, and production environments.

Example using profiles:

~~~java
@Configuration
public class NotificationConfiguration {

    @Bean
    @Profile("dev")
    public NotificationSender consoleSender() {
        return new ConsoleNotificationSender();
    }

    @Bean
    @Profile("prod")
    public NotificationSender emailSender() {
        return new EmailNotificationSender();
    }
}
~~~

When `dev` is active, the console bean is registered; when `prod` is active, the email bean is registered. This is a conceptual example; the configuration class must import `org.springframework.context.annotation.Profile`.

You can activate a profile with:

~~~properties
spring.profiles.active=dev
~~~

Or via command-line argument:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

The goal is ensuring each environment has the right candidate without letting two implementations coexist and cause injection ambiguity.

Beyond `@Profile`, Spring Boot offers conditions such as `@ConditionalOnProperty` and `@ConditionalOnMissingBean` in the auto-configuration ecosystem. They are especially useful when writing starters or replaceable default configurations.

Do not treat profiles as a security mechanism; they select bean configurations per environment rather than protecting endpoints or secrets.

## 14. Inspecting Which Type a Bean Is Registered Under

When hitting an injection error, inspect the context and bean definitions instead of guessing.

### 14.1. Querying a Bean by Interface

~~~java
@Bean
CommandLineRunner inspectSender(ApplicationContext context) {
    return args -> {
        NotificationSender sender =
                context.getBean(NotificationSender.class);

        System.out.println("Sender runtime type: " + sender.getClass().getName());
    };
}
~~~

If there is a single matching candidate, the type-based call returns that bean. If unresolved multiple candidates exist, type lookup throws an error.

This snippet requires importing `ApplicationContext` and `CommandLineRunner`. It is a learning observation tool and does not need to stay in production code.

### 14.2. Querying Bean Name and Runtime Type

~~~java
@Bean
CommandLineRunner inspectBean(ApplicationContext context) {
    return args -> {
        Object bean = context.getBean("notificationSender");
        System.out.println(bean.getClass().getName());
    };
}
~~~

The name `notificationSender` must match the actual registered bean name. If you specified a custom name in `@Bean("...")`, query using that name.

`getClass()` reports the runtime class. To know what type Spring predicts from the definition before instantiation, inspect bean definition metadata or debug the resolution step; runtime `getClass()` alone cannot reconstruct the entire pre-instantiation prediction.

### 14.3. Listing Bean Definitions

~~~java
@Bean
CommandLineRunner listDefinitions(ConfigurableApplicationContext context) {
    return args -> {
        for (String name : context.getBeanFactory().getBeanDefinitionNames()) {
            if (name.toLowerCase().contains("notification")) {
                System.out.println("Definition: " + name);
            }
        }
    };
}
~~~

Requires importing `ConfigurableApplicationContext` and `CommandLineRunner`. This listing confirms which definition names were registered.

Note: seeing a definition name does not prove all bean instances have been created. A lazy bean can have a definition without an instantiated object yet.

## 15. Common Errors and How to Understand Them Correctly

### 15.1. No Bean Found for Interface

Message may look like:

~~~text
No qualifying bean of type 'NotificationSender' available
~~~

Check:

- Was an implementation registered via `@Component` or `@Bean`?
- Is the package within component scan scope?
- Was the bean excluded by a profile or condition?
- Does the factory method have an overly general return type like `Object`, hindering type prediction?
- Was the bean excluded by another configuration?

Do not merely slap `@Autowired` onto a field expecting Spring to synthesize an implementation. The container needs a valid bean definition.

### 15.2. Multiple Beans Found for Interface

Error typically involves `NoUniqueBeanDefinitionException`.

Count how many beans share the type, then decide:

- Register only the implementation actually needed.
- Use `@Primary` if there is a default choice.
- Use `@Qualifier` if consumers need specific implementations.
- Inject a collection if business logic needs all of them.

Do not switch the return type to a concrete class merely to accidentally hide another candidate without clarifying the actual requirement.

### 15.3. Injection by Implementation Fails While Interface Injection Succeeds

A factory method declared as:

~~~java
@Bean
NotificationSender notificationSender() {
    return new ConsoleNotificationSender();
}
~~~

supports injection by `NotificationSender`, yet lacks metadata guaranteeing injection by `ConsoleNotificationSender` before instantiation.

If a consumer truly needs the implementation, consider declaring the concrete return type:

~~~java
@Bean
ConsoleNotificationSender notificationSender() {
    return new ConsoleNotificationSender();
}
~~~

Then re-verify the context. If the service only needs the send capability, switching the consumer to the interface is usually the cleaner design.

### 15.4. Returning `Object` or a Raw Type

Example:

~~~java
@Bean
Object messageStore() {
    return new StringStore();
}
~~~

`Object` fails to express the contract other beans need. If a service requests `Store<String>`, declaring `Object` as the return type can keep the container from predicting the match before running the factory method.

Advertise a meaningful type:

~~~java
@Bean
Store<String> messageStore() {
    return new StringStore();
}
~~~

or the concrete implementation type when recognition of that type is needed.

### 15.5. Two Beans with the Same Name

Bean names identify entries in the container. If two configurations register beans with the same name, behavior depends on the bean definition overriding policy and context settings. In modern Spring Boot versions, bean definition overriding is typically disabled by default for new applications; collisions can fail startup.

Do not rely on one bean "overriding" another based on file order. Use purposeful names, qualifiers, profiles, or conditions to control which bean is registered.

### 15.6. Depending on a Concrete Class in Consumers Loses Abstraction Benefits

If `OrderService` accepts `ConsoleNotificationSender` directly, the service becomes tied to console delivery. Switching to email forces modifying consumers or introducing conversions.

Accept `NotificationSender` whenever the service only needs the send capability. The factory method's return type and the consumer's parameter type do not have to be identical.

## 16. How to Choose a `@Bean` Return Type

Use these guidelines:

| Situation | Return type to consider | Reason |
| --- | --- | --- |
| All consumers only need a stable contract | Interface | Expresses abstraction, reduces coupling |
| A consumer needs the concrete implementation type | Implementation class, or a separate bean definition with that type | Enables type prediction to recognize the class |
| Bean has an important generic contract | Specific generic type like `Store<String>` | Supplies generic metadata for resolution |
| Returning `Object` or an overly broad type | Avoid if possible | Discards useful type information |
| Factory method wraps a third-party library | Specific public API type needed by consumers | Avoids forcing third-party classes into components |
| One logical factory has multiple implementations per profile | Interface if consumers only need the contract | Keeps consumers independent of environment choice |

There is no rigid rule that "every `@Bean` must return an interface" or "every `@Bean` must return a concrete class". Choose the type that accurately expresses the contract and provides the container with the metadata it needs.

A clean default is:

~~~java
@Bean
public NotificationSender notificationSender() {
    return new ConsoleNotificationSender();
}
~~~

when the application intends to expose the abstraction and all consumers rely only on the abstraction.

When there is a valid need for Spring to recognize the concrete class:

~~~java
@Bean
public ConsoleNotificationSender consoleNotificationSender() {
    return new ConsoleNotificationSender();
}
~~~

Consumers can still inject by interface:

~~~java
public OrderService(NotificationSender sender) {
    this.sender = sender;
}
~~~

That balances **sufficiently specific metadata at creation time** with **low coupling at consumption time**.

## 17. Practice Exercises

### Exercise A: Predict Bean Type

Given:

~~~java
@Bean
public NotificationSender sender() {
    return new ConsoleNotificationSender();
}
~~~

Answer:

1. What is the default bean name?
2. What is the declared return type?
3. What is the runtime type of the object?
4. Will a consumer requesting `NotificationSender` work?
5. What limitation might a consumer requesting `ConsoleNotificationSender` run into?

**Hint:** The bean name is typically `sender`; the declared return type is `NotificationSender`; the actual object is `ConsoleNotificationSender`. Interface injection works. Do not rely on type prediction to inject a concrete implementation when the method advertises only the interface.

### Exercise B: Compare Two Factory Methods

Write two independent configurations:

~~~java
@Bean
NotificationSender sender() {
    return new ConsoleNotificationSender();
}
~~~

and:

~~~java
@Bean
ConsoleNotificationSender sender() {
    return new ConsoleNotificationSender();
}
~~~

Try creating a consumer requesting the interface and a consumer requesting the concrete implementation. Observe the difference during context startup.

**Hint:** When the return type is the implementation, metadata lets Spring recognize both the concrete class and its implemented interfaces. When the return type is the interface, do not depend on an uncreated runtime object to infer the implementation.

### Exercise C: Handling Multiple Implementations

Register two beans:

~~~java
@Bean
NotificationSender consoleSender() {
    return new ConsoleNotificationSender();
}

@Bean
NotificationSender emailSender() {
    return new EmailNotificationSender();
}
~~~

Update `OrderService` to always use the email sender via `@Qualifier`. Then try marking the console sender `@Primary` and removing the qualifier. Observe which candidate gets chosen.

### Exercise D: Registering Implementations by Profile

Create two `NotificationSender` beans, one for `dev` and one for `prod`. Run the application under each profile and inspect logs to confirm the active implementation.

Explain why profiles prevent multiple-candidate errors when each environment registers only one implementation.

### Exercise E: Generic Interfaces

Create `Store<String>` and `Store<Integer>`. Inject each into two separate services. Then change the factory method return types to raw `Store` and observe generic type resolution.

The goal is understanding that generic signatures are also metadata Spring can use during autowiring.

## 18. Self-Check Questions

**1. What does interface-based bean registration mean?**

It means providing an object that fulfills an interface contract so other components can inject and consume it through that abstraction. The runtime object is still a concrete implementation class.

**2. Why does the return type of a `@Bean` method matter?**

Because Spring uses the method signature and metadata to predict the bean type, identify type-matching candidates, and resolve dependencies. An overly broad return type can deprive the container of information before the factory method runs.

**3. If `@Bean` returns `NotificationSender` while the actual object is `ConsoleNotificationSender`, does a service requesting the interface work?**

Yes, provided the bean is registered and there is no candidate ambiguity. The advertised type matches the contract requested by the service.

**4. What if a service requests `ConsoleNotificationSender`?**

An interface return type does not guarantee the container can predict the concrete implementation at resolution time. If that class is required, declare the concrete return type or refactor the consumer to depend on the interface.

**5. What do `@Qualifier` and `@Primary` solve?**

They select among multiple candidate beans matching the same injection type. `@Qualifier` picks candidates by qualifier; `@Primary` designates a default preferred candidate.

**6. Does a bean name replace the declared return type?**

No. A bean's identifying name is separate from its declared type and runtime type. Renaming a bean gives Spring no extra class information beyond what the factory method declares.

**7. Must factory methods always return concrete implementation classes?**

No. If consumers only need the interface and the method returns that interface, declaring the interface is valid and communicates the abstraction cleanly. Expose the concrete implementation only when concrete-type recognition is needed.

## 19. Conclusion

Interface-based bean registration keeps an application dependent on **contracts** rather than implementations. Spring supplies matching implementations via component scan or `@Bean` factory methods, injecting beans into consumer constructors.

The `@Bean` return type is critical metadata for the container. **Returning an interface** fits when exposing an abstraction that consumers also request by interface. **Returning a concrete class** gives Spring extra metadata when concrete-type recognition is needed. Avoid returning `Object` or raw types if doing so discards type information required for dependency resolution.

When designing, keep three layers distinct: **bean name for identification, return type for advertising predictable capabilities/types, and runtime type for the actual object**. Combined with `@Qualifier`, `@Primary`, and constructor injection, you can register multiple implementations while keeping services decoupled from implementation details.
