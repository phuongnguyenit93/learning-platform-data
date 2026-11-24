# Injecting Beans by Interface to Decouple Business Logic from Implementation

A service in a Spring Boot application may need to send emails, persist data, process payment fees, or call an external service. If the service creates and calls a concrete class directly, business logic becomes coupled to that technical implementation. When you want to switch providers, run in a different environment, or test without calling real external systems, you end up having to modify or rebuild many components.

A flexible design is to have business code depend on an **interface describing the capability it needs**, and then let the Spring IoC container inject a bean implementing that interface into the service.

Example:

~~~java
public interface PaymentGateway {
    PaymentResult charge(Money amount);
}
~~~

The service only needs to know the `PaymentGateway` contract. A class such as `CardPaymentAdapter` can implement the contract and call a payment provider. When application configuration swaps the implementation, the service remains unchanged.

This lesson focuses on how **interface-based Dependency Injection** separates business policy from implementation details. We will move from plain Java design, the Dependency Inversion Principle, and how Spring registers and selects beans, to testing and common pitfalls.

## 1. Why Shouldn't Business Code Be Tightly Coupled to One Implementation?

Suppose an application has an order placement feature. When creating an order, the system needs to send a notification to the customer.

An initial approach:

~~~java
public class OrderService {

    public void createOrder(String customerEmail) {
        // Save the order and process business rules...

        EmailNotificationSender sender =
                new EmailNotificationSender();

        sender.send(customerEmail, "Your order has been created.");
    }
}
~~~

The code is easy to read, but `OrderService` is taking on two responsibilities:

- Coordinating the order creation business flow.
- Choosing and instantiating a specific notification delivery mechanism.

If the application later switches to another email provider, uses a message queue, or simply logs notifications to the console in a development environment, the service has to change even though the order-creation rules did not change.

This is direct **coupling** to implementation details.

### 1.1. Consequences of direct coupling

**Hard to change implementations.** Every call site referencing the concrete class may need edits when technology changes.

**Hard to test in isolation.** Unit tests for the service might accidentally instantiate real clients, hit the network, or require credentials configuration.

**Hard to control lifecycle.** Because the service instantiates the dependency itself, Spring does not manage that object as a bean. Configuration mechanisms, proxies, lifecycle callbacks, or bean replacement do not automatically apply to objects created with `new`.

**Hard to separate business policy from infrastructure.** The rule for "when to send a notification" gets mixed with "send notifications via SMTP or HTTP."

Not every `new` statement is bad. Creating a small value object or an internal helper that does not need container management is completely reasonable. Problems arise when business code instantiates collaborators that have lifecycles, configuration, or infrastructure details it should not own.

## 2. Placing an Interface Between the Service and the Implementation

Instead of depending on `EmailNotificationSender`, define a contract:

~~~java
public interface NotificationSender {
    void send(String recipient, String message);
}
~~~

Concrete implementation:

~~~java
public class EmailNotificationSender implements NotificationSender {

    @Override
    public void send(String recipient, String message) {
        // Call email provider or SMTP client.
    }
}
~~~

The service receives the interface via its constructor:

~~~java
public class OrderService {
    private final NotificationSender notificationSender;

    public OrderService(NotificationSender notificationSender) {
        this.notificationSender = notificationSender;
    }

    public void createOrder(String customerEmail) {
        // Process order creation rules...

        notificationSender.send(
                customerEmail,
                "Your order has been created."
        );
    }
}
~~~

The dependency graph has changed:

~~~mermaid
flowchart TD
    A["Before: OrderService"] --> B["EmailNotificationSender"]
    C["After: OrderService"] --> D["NotificationSender interface"]
    E["EmailNotificationSender"] -. "implements" .-> D
~~~

The service only knows the capability it needs. The implementation is responsible for fulfilling that capability.

You can swap implementations without modifying the service:

~~~java
public class ConsoleNotificationSender implements NotificationSender {
    @Override
    public void send(String recipient, String message) {
        System.out.println(recipient + ": " + message);
    }
}
~~~

Or:

~~~java
public class QueueNotificationSender implements NotificationSender {
    @Override
    public void send(String recipient, String message) {
        // Enqueue the notification onto a message queue.
    }
}
~~~

All three classes satisfy the same contract. This is Java **polymorphism**: calling code targets the interface type, while the executed method belongs to the runtime object.

## 3. An Interface Is a Contract, Not a Mirror of the Implementation

A good interface describes **what the consumer needs**, without exposing every internal operation of the provider.

For example, the service needs to request sending a notification:

~~~java
public interface NotificationSender {
    void send(String recipient, String message);
}
~~~

The consumer does not need to know:

- How the email client connects to SMTP.
- How an HTTP adapter adds authorization headers.
- Which topic a queue producer selects.
- Which vendor-specific SDK and exceptions the provider uses.

Those details belong to the implementation.

### 3.1. Design interfaces around consumer needs

Avoid creating overly broad interfaces:

~~~java
public interface NotificationPlatform {
    void sendEmail(String recipient, String subject, String body);
    void sendSms(String phoneNumber, String body);
    void publishKafkaMessage(String topic, String payload);
    void connectSmtp();
    void refreshProviderToken();
    void openAdminDashboard();
}
~~~

A service that only needs to send email notifications ends up coupled to SMS, Kafka, SMTP, and admin dashboards. Implementations that do not support all operations will struggle to fulfill the contract.

Split into small, capability-focused interfaces:

~~~java
public interface EmailSender {
    void send(String recipient, String subject, String body);
}

public interface SmsSender {
    void send(String phoneNumber, String message);
}
~~~

`OrderService` only accepts the interface matching its responsibility. This applies the **Interface Segregation Principle**: consumers should not be forced to depend on methods they do not use.

### 3.2. Contracts should also express semantics and failure behavior

An interface is more than a list of methods. It also needs clear semantics:

- Does `send` deliver synchronously or merely enqueue?
- Does the method return when the provider confirms delivery or when the request is accepted?
- What exceptions indicate failures?
- Can the consumer safely retry?
- What side effects could duplicate sends cause?

If the contract implies "delivered" while the implementation only "enqueued," consumers may misinterpret the result. Method names, return types, exceptions, and documentation should accurately reflect semantics.

Example of a clearer contract when a result is needed:

~~~java
public interface NotificationSender {
    NotificationReceipt send(NotificationMessage message);
}
~~~

`NotificationMessage` and `NotificationReceipt` are application-owned types describing the request content and the outcome the business logic cares about. Avoid returning vendor SDK response types directly if doing so couples the service to the vendor.

## 4. How Do Dependency Injection and Dependency Inversion Differ?

These two terms often appear together, but they answer different questions.

**Dependency Injection (DI)** answers: "Who supplies the objects this class needs?" Instead of instantiating dependencies itself, the class receives them from outside, usually via its constructor.

**Dependency Inversion Principle (DIP)** answers: "Which abstractions should modules depend on?" This principle encourages high-level policies not to be bound directly to low-level details; instead, both should depend on appropriate abstractions.

Example:

~~~text
Business policy:
OrderService
      │
      ▼
NotificationSender (abstraction)
      ▲
      │
Infrastructure detail:
EmailNotificationSender
~~~

`OrderService` handles business orchestration. `EmailNotificationSender` implements the delivery details. Both connect through `NotificationSender`.

### 4.1. DI does not automatically guarantee DIP

This is still Dependency Injection:

~~~java
public class OrderService {
    private final EmailNotificationSender sender;

    public OrderService(EmailNotificationSender sender) {
        this.sender = sender;
    }
}
~~~

The object is passed from outside, yet the service still depends on a concrete class. DI is present, but no abstraction boundary has been introduced.

Conversely, merely declaring an interface while the service instantiates the implementation itself is not proper DI either:

~~~java
public class OrderService {
    private final NotificationSender sender =
            new EmailNotificationSender();
}
~~~

The service still chooses the implementation and instantiates it directly.

A well-structured design typically combines both:

1. An interface expresses the needed capability.
2. The service accepts the interface via its constructor.
3. Configuration or an IoC container chooses the implementation.
4. Spring manages and wires the beans.

## 5. Constructor Injection in Plain Java

Before using Spring, understand the mechanism in plain Java.

~~~java
public interface NotificationSender {
    void send(String recipient, String message);
}
~~~

Implementation:

~~~java
public class ConsoleNotificationSender implements NotificationSender {
    @Override
    public void send(String recipient, String message) {
        System.out.println("[CONSOLE] " + recipient + ": " + message);
    }
}
~~~

Service:

~~~java
public class OrderService {
    private final NotificationSender sender;

    public OrderService(NotificationSender sender) {
        this.sender = sender;
    }

    public void createOrder(String email) {
        // Simulate successful order creation rules.
        sender.send(email, "Order created.");
    }
}
~~~

The composition root (where objects are assembled) can be `main`:

~~~java
public class Main {
    public static void main(String[] args) {
        NotificationSender sender = new ConsoleNotificationSender();
        OrderService orderService = new OrderService(sender);

        orderService.createOrder("lan@example.com");
    }
}
~~~

Output:

~~~text
[CONSOLE] lan@example.com: Order created.
~~~

To switch to another implementation, only change the assembly code:

~~~java
NotificationSender sender = new EmailNotificationSender();
OrderService orderService = new OrderService(sender);
~~~

`OrderService` does not need any changes.

**Constructor injection** is especially suitable for required dependencies because:

- The constructor clearly exposes the collaborators the class requires.
- An object cannot be created via this constructor without its dependencies.
- Fields can be `final`.
- Unit tests can easily instantiate the object by passing a fake implementation.
- No Spring context is needed just to test service logic.

Spring performs the same assembly in a real application.

## 6. Registering an Implementation as a Spring Bean

The Spring IoC container can only inject an implementation if that bean is registered and satisfies configuration conditions.

There are two common ways.

### 6.1. Component scan

Annotate the implementation:

~~~java
import org.springframework.stereotype.Component;

@Component
public class ConsoleNotificationSender implements NotificationSender {
    @Override
    public void send(String recipient, String message) {
        System.out.println("[CONSOLE] " + recipient + ": " + message);
    }
}
~~~

If the class's package is within component scan scope, Spring registers a bean definition for the implementation.

Service:

~~~java
import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private final NotificationSender sender;

    public OrderService(NotificationSender sender) {
        this.sender = sender;
    }

    public void createOrder(String email) {
        sender.send(email, "Order created.");
    }
}
~~~

When creating `OrderService`, Spring looks for a bean satisfying `NotificationSender`. `ConsoleNotificationSender` implements the interface and can be selected if there are no ambiguous candidates.

### 6.2. `@Bean` factory method

If the implementation comes from an external library or you want full control over object creation, declare it in a configuration class:

~~~java
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

The `@Bean` method exposes the bean by its interface type. At runtime, the actual object is `ConsoleNotificationSender`.

The service continues to inject the interface:

~~~java
@Service
public class OrderService {
    private final NotificationSender sender;

    public OrderService(NotificationSender sender) {
        this.sender = sender;
    }
}
~~~

Here, configuration is responsible for choosing the implementation. The service only uses the contract.

### 6.3. Why not call `getBean()` directly inside the service?

An approach to avoid as a default:

~~~java
@Service
public class OrderService {
    private final NotificationSender sender;

    public OrderService(ApplicationContext context) {
        this.sender = context.getBean(NotificationSender.class);
    }
}
~~~

This couples the service directly to the container and makes it fetch dependencies itself. It turns the service into a **Service Locator** instead of letting the container inject dependencies via the constructor.

Constructor injection is clearer because:

- Dependencies appear directly in the constructor signature.
- The service does not need to know about Spring `ApplicationContext`.
- Unit tests do not need to construct or mock a container.
- Business logic can be used outside Spring if needed.

Let Spring wire objects at the application boundary; keep services focused on business rules.

## 7. Complete Spring Boot Example: Order Creation Using an Interface

Let's build a small example with a controller, service, and sender. By default, notifications print to the console, yet the service does not know that.

### 7.1. Project structure

~~~text
order-notification/
└── src/main/java/com/example/orders/
    ├── OrderApplication.java
    ├── application/
    │   ├── NotificationSender.java
    │   └── OrderService.java
    ├── infrastructure/
    │   └── ConsoleNotificationSender.java
    └── web/
        └── OrderController.java
~~~

This package layout shows responsibility boundaries:

- `application` contains business contracts and use cases.
- `infrastructure` contains technical implementations.
- `web` contains adapters receiving HTTP requests.

This is an illustrative organization; smaller projects can use a simpler structure as long as dependency directions remain clear.

### 7.2. Entry-point class

`OrderApplication.java`:

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Place this class in the root package so default component scanning discovers subpackages.

### 7.3. Required business interface

`application/NotificationSender.java`:

~~~java
package com.example.orders.application;

public interface NotificationSender {
    void sendOrderCreated(String recipient, String orderId);
}
~~~

The contract lives in the application layer because the order-creation use case is what requires the notification capability. Method names express the required business behavior rather than exposing email sending or vendor API names.

### 7.4. Business service

`application/OrderService.java`:

~~~java
package com.example.orders.application;

import org.springframework.stereotype.Service;

import java.util.UUID;

@Service
public class OrderService {
    private final NotificationSender notificationSender;

    public OrderService(NotificationSender notificationSender) {
        this.notificationSender = notificationSender;
    }

    public String createOrder(String customerEmail) {
        String orderId = UUID.randomUUID().toString();

        // In a real application, validation and order persistence happen here.
        notificationSender.sendOrderCreated(customerEmail, orderId);

        return orderId;
    }
}
~~~

The service generates an order ID, runs the illustrative business step, and invokes the contract. It does not import any concrete implementation.

In a real system, you must clearly define the ordering of order persistence and notification delivery, transaction boundaries, retries, idempotency, and failure handling. The current example focuses strictly on dependency wiring.

### 7.5. Infrastructure implementation

`infrastructure/ConsoleNotificationSender.java`:

~~~java
package com.example.orders.infrastructure;

import com.example.orders.application.NotificationSender;
import org.springframework.stereotype.Component;

@Component
public class ConsoleNotificationSender implements NotificationSender {

    @Override
    public void sendOrderCreated(String recipient, String orderId) {
        System.out.printf(
                "[NOTIFICATION] To=%s, orderId=%s%n",
                recipient,
                orderId
        );
    }
}
~~~

This class implements the contract and resides in infrastructure. It can be replaced with an email provider or queue adapter without touching `OrderService`.

### 7.6. Controller

`web/OrderController.java`:

~~~java
package com.example.orders.web;

import com.example.orders.application.OrderService;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/orders")
public class OrderController {
    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    public CreateOrderResponse create(@RequestParam String email) {
        String orderId = orderService.createOrder(email);
        return new CreateOrderResponse(orderId);
    }

    public record CreateOrderResponse(String orderId) {
    }
}
~~~

The controller simply handles the HTTP request and calls the use case. It also does not need to know the sender implementation.

### 7.7. Runtime flow

~~~mermaid
flowchart TD
    A["HTTP POST /orders?email=..."] --> B["OrderController"]
    B --> C["OrderService"]
    C --> D["NotificationSender interface"]
    E["ConsoleNotificationSender bean"] -. "implements" .-> D
    D --> E
    E --> F["Log notification to console"]
    C --> G["Return orderId"]
    G --> B
    B --> H["HTTP response"]
~~~

At startup, Spring discovers the controller, service, and sender component. When creating `OrderService`, the container injects the `ConsoleNotificationSender` bean via the `NotificationSender` type.

When a request arrives, the service calls the method on the interface. Java dynamic dispatch routes the call to the runtime object's implementation.

### 7.8. Running the application

With a Maven project declaring `spring-boot-starter-web` and the Spring Boot Maven plugin:

~~~bash
mvn spring-boot:run
~~~

Send a request:

~~~bash
curl -X POST "http://localhost:8080/orders?email=lan@example.com"
~~~

Response looks like:

~~~json
{
  "orderId": "a-runtime-generated-uuid"
}
~~~

In the application console, a log line similar to this appears:

~~~text
[NOTIFICATION] To=lan@example.com, orderId=...
~~~

The UUID changes with every call. The output shows the request passing through the controller, service, and the injected sender implementation.

## 8. Swapping Implementations by Environment Without Editing the Service

An application might use a console sender locally, an email sender in production, or a fake sender in tests.

### 8.1. Using @Profile

Create a console implementation active only in the `dev` profile:

~~~java
@Component
@Profile("dev")
public class ConsoleNotificationSender implements NotificationSender {
    @Override
    public void sendOrderCreated(String recipient, String orderId) {
        System.out.println("[DEV] " + recipient + ": " + orderId);
    }
}
~~~

Production implementation:

~~~java
@Component
@Profile("prod")
public class EmailNotificationSender implements NotificationSender {
    @Override
    public void sendOrderCreated(String recipient, String orderId) {
        // Send notification through the configured email provider.
    }
}
~~~

When `dev` is active, the console bean is registered. When `prod` is active, the email bean is registered. Each profile must provide a bean satisfying the contract if `OrderService` requires it.

Activate via configuration file:

~~~properties
spring.profiles.active=dev
~~~

Or command-line argument:

~~~bash
java -jar order-notification.jar --spring.profiles.active=prod
~~~

This example requires both classes to import `org.springframework.context.annotation.Profile`. The JAR filename is illustrative.

Profiles are a mechanism to select configuration/beans by environment. They do not protect endpoints on their own or replace secret management. The email provider still needs secure credentials configuration.

### 8.2. Using @ConditionalOnProperty

When you want to select an implementation based on a property, you can use Spring Boot conditionals:

~~~java
@Configuration
public class NotificationConfiguration {

    @Bean
    @ConditionalOnProperty(
            name = "notification.mode",
            havingValue = "console",
            matchIfMissing = true
    )
    NotificationSender consoleSender() {
        return new ConsoleNotificationSender();
    }

    @Bean
    @ConditionalOnProperty(
            name = "notification.mode",
            havingValue = "email"
    )
    NotificationSender emailSender(EmailClient emailClient) {
        return new EmailNotificationSender(emailClient);
    }
}
~~~

`EmailClient` is an assumed dependency that must be registered/configured separately. `EmailNotificationSender` here has a constructor taking `EmailClient`.

Configuration:

~~~properties
notification.mode=console
~~~

Or:

~~~properties
notification.mode=email
~~~

Conditions help select beans based on properties. If email is chosen but `EmailClient` is missing, the context still cannot create the corresponding bean. Conditions do not automatically provision the infrastructure required by an implementation.

### 8.3. Using @Qualifier when multiple implementations coexist

If the application needs both console and email senders at the same time, do not use profiles to exclude one of them. Register both with qualifiers:

~~~java
@Configuration
public class NotificationConfiguration {

    @Bean
    @Qualifier("console")
    NotificationSender consoleSender() {
        return new ConsoleNotificationSender();
    }

    @Bean
    @Qualifier("email")
    NotificationSender emailSender(EmailClient emailClient) {
        return new EmailNotificationSender(emailClient);
    }
}
~~~

The consumer selects the desired bean explicitly:

~~~java
@Service
public class OrderService {
    private final NotificationSender sender;

    public OrderService(@Qualifier("email") NotificationSender sender) {
        this.sender = sender;
    }
}
~~~

`@Qualifier` filters candidates by qualifier metadata. Default bean names can also participate in name-based selection in some situations, but explicit qualifiers communicate intent clearly.

### 8.4. When to use @Primary?

If multiple beans share the same type and one should be the default choice:

~~~java
@Bean
@Primary
NotificationSender consoleSender() {
    return new ConsoleNotificationSender();
}
~~~

`@Primary` gives this bean precedence when an injection point asks for a single bean without a more specific qualifier. It does not remove the other implementations.

Use `@Primary` when there is genuinely one sensible default. If different consumers need different choices, `@Qualifier` is usually clearer.

## 9. Testing Services Independently of Real Implementations

A direct benefit of interface injection is being able to test services without starting a Spring context or calling external systems.

### 9.1. Using a fake implementation

Create a fake sender in the test:

~~~java
class RecordingNotificationSender implements NotificationSender {
    private String recipient;
    private String orderId;

    @Override
    public void sendOrderCreated(String recipient, String orderId) {
        this.recipient = recipient;
        this.orderId = orderId;
    }

    String recipient() {
        return recipient;
    }

    String orderId() {
        return orderId;
    }
}
~~~

Test the service with Java/JUnit:

~~~java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class OrderServiceTest {

    @Test
    void createsOrderAndRequestsNotification() {
        RecordingNotificationSender sender =
                new RecordingNotificationSender();

        OrderService service = new OrderService(sender);

        String orderId = service.createOrder("lan@example.com");

        assertNotNull(orderId);
        assertEquals("lan@example.com", sender.recipient());
        assertEquals(orderId, sender.orderId());
    }
}
~~~

This test:

- Instantiates the fake implementation.
- Passes the fake into the service constructor.
- Invokes the use case.
- Verifies the service requested the notification with the expected data.

No `@SpringBootTest` is needed because the goal is to verify service logic and how the service collaborates with the contract. The test also makes no calls to a real email provider.

### 9.2. Using Mockito when interaction verification is needed

If the project uses Mockito via `spring-boot-starter-test`:

~~~java
import org.junit.jupiter.api.Test;

import static org.mockito.Mockito.*;

class OrderServiceMockitoTest {

    @Test
    void sendsNotificationAfterCreatingOrder() {
        NotificationSender sender = mock(NotificationSender.class);
        OrderService service = new OrderService(sender);

        String orderId = service.createOrder("lan@example.com");

        verify(sender).sendOrderCreated("lan@example.com", orderId);
    }
}
~~~

Mockito creates a mock of the interface and records invocations so tests can verify interactions. Fakes are often handy when simple behavior is desired, whereas mocks fit when asserting which method was called with which arguments.

Avoid overusing mocks to assert every internal detail of a service. Verify behavior that is meaningful with respect to the contract.

### 9.3. Unit tests vs. integration tests

| Test type | Goal | Spring context needed? |
| --- | --- | --- |
| Service unit test | Business logic and interaction through interfaces | Usually no |
| Wiring integration test | Beans are registered and injected properly in the context | Yes |
| Web integration test | Endpoints, controllers, services, and adapters collaborate | Usually yes |
| Adapter contract/integration test | Implementation communicates properly with external system or sandbox | Depends on design |

A passing unit test does not prove Spring registered the bean under the right profile. Conversely, a context starting successfully does not prove business rules are correct. Each test type answers a distinct question.

## 10. Isolating Contracts from Vendor Libraries

Suppose the application uses a specific payment SDK. Do not let business services accept SDK request/response types directly if doing so couples the entire business layer to the vendor.

Instead, create an application-owned contract:

~~~java
public interface PaymentGateway {
    PaymentResult charge(PaymentRequest request);
}
~~~

The types `PaymentRequest` and `PaymentResult` should belong to the application, describing the data and outcomes the business logic needs.

The implementation translates between the internal contract and the SDK:

~~~java
@Component
public class VendorPaymentAdapter implements PaymentGateway {

    private final VendorPaymentClient client;

    public VendorPaymentAdapter(VendorPaymentClient client) {
        this.client = client;
    }

    @Override
    public PaymentResult charge(PaymentRequest request) {
        VendorChargeRequest vendorRequest =
                new VendorChargeRequest(request.amount());

        VendorChargeResponse response =
                client.charge(vendorRequest);

        return new PaymentResult(
                response.transactionId(),
                response.approved()
        );
    }
}
~~~

`VendorPaymentClient`, `VendorChargeRequest`, and `VendorChargeResponse` are assumed SDK types. The adapter translates between the application's model and the provider's API.

Diagram:

~~~mermaid
flowchart LR
    A["OrderService / application policy"] --> B["PaymentGateway (port/interface)"]
    C["VendorPaymentAdapter"] -. "implements" .-> B
    C --> D["Vendor SDK"]
    D --> E["Payment Provider"]
~~~

This is the core idea of **Ports and Adapters (Hexagonal Architecture)**:

- A port is the contract the application needs.
- An adapter is the component that translates that contract to a specific technology.
- Spring DI connects the port to the appropriate adapter at runtime.

Not every Spring Boot application needs a full Hexagonal Architecture. Still, this boundary mindset is very helpful whenever an application integrates with multiple external systems.

## 11. Where Should Interfaces Live in the Architecture?

An important question is: does the interface belong to the service's package or the infrastructure package?

If the interface exists to serve the application's needs, it can live in the application layer:

~~~text
com.example.orders
├── application
│   ├── OrderService.java
│   └── port
│       └── out
│           └── NotificationSender.java
└── infrastructure
    └── notification
        └── EmailNotificationAdapter.java
~~~

In this layout:

- The application layer defines the required contract.
- Infrastructure depends on the contract to implement it.
- Application code does not import vendor or adapter packages.
- Spring configuration wires the two sides together.

Other layouts can also make sense in smaller projects. What matters is that **source-code dependency direction** aligns with architectural intent: business logic should not be dragged toward the technical details it uses.

An interface placed inside infrastructure and imported by the application can invert dependencies opposite to the original goal. Put the abstraction where the need for it lives, unless there is a specific architectural reason to do otherwise.

## 12. When Should You Create an Interface, and When Shouldn't You?

Not every class needs its own interface. Introducing an abstraction is only helpful when it represents a genuine boundary.

### Consider creating an interface when:

- Multiple valid implementations exist or swapping implementations is a real requirement.
- The component sits at an external boundary: email, payments, storage, messaging, external APIs.
- You want to test services independently of infrastructure.
- You want to separate business policy from technical execution.
- Another module needs to supply an implementation against a stable contract.
- You want to switch implementations by environment or configuration.

### An interface is probably unnecessary when:

- The class is just a simple value object.
- There is no variation boundary or replaceable collaborator.
- The interface merely mirrors every method of a single class without representing a meaningful contract.
- Adding the interface forces readers to jump across files without improving clarity or changeability.
- It is not yet clear what abstraction consumers actually need.

A service can inject a concrete class if that dependency is stable and there is no reason to abstract it. Good design is measured by clarity of responsibilities and dependencies, not by the number of interfaces.

## 13. Common Errors When Injecting by Interface

### 13.1. No bean implements the interface

Service:

~~~java
@Service
public class OrderService {
    public OrderService(NotificationSender sender) {
        // ...
    }
}
~~~

Yet no implementation has been registered. Spring may report:

~~~text
No qualifying bean of type 'NotificationSender' available
~~~

How to fix:

- Create an appropriate implementation.
- Register it with `@Component` or `@Bean`.
- Check package scanning and profile conditions.
- Check auto-configuration settings if a starter is expected to provide the bean.

Spring does not automatically generate implementations for application-defined interfaces.

### 13.2. Multiple beans implement the interface

If both `ConsoleNotificationSender` and `EmailNotificationSender` are registered while the service asks for a single `NotificationSender`, Spring may throw `NoUniqueBeanDefinitionException`.

Use `@Qualifier` to pick explicitly, `@Primary` to set a default, or profiles/conditions so only the intended implementation is registered.

Do not change the service to depend on a concrete class just to silence the error if the business logic genuinely only needs the interface.

### 13.3. Implementation is outside component scan

A class annotated with `@Component` outside the scanned packages will still not be registered.

Check the package containing `@SpringBootApplication`, the implementation's location, and scan configuration. If the class belongs to an external module, register it via `@Bean` in an appropriately imported configuration class.

### 13.4. Service instantiates the implementation with `new`

~~~java
@Service
public class OrderService {
    private final NotificationSender sender =
            new ConsoleNotificationSender();
}
~~~

This bypasses Spring-managed beans and locks the service to one implementation. Move the dependency into the constructor:

~~~java
public OrderService(NotificationSender sender) {
    this.sender = sender;
}
~~~

### 13.5. Interface leaks vendor details

If the contract returns a vendor SDK-specific response object, the service remains coupled to the provider despite having an interface.

Convert to application-owned data types. The adapter is where mapping and error translation between the two models belong.

### 13.6. Circular dependency

If `OrderService` requires `NotificationService`, and `NotificationService` also requires `OrderService`, the two dependencies can form a cycle.

Do not rush to use setter or lazy injection to hide a cycle. Review responsibilities and extract shared logic or orchestration into another component if appropriate.

### 13.7. Overly broad or ambiguous interfaces

A contract with unrelated methods makes fake implementations and tests cumbersome to write. Split by consumer role, choose clear method names, and document error behavior.

## 14. Implementation Selection Should Not Live Inside the Service

A poor design sign is having the service choose implementations itself:

~~~java
public class OrderService {
    public OrderService(boolean useEmail) {
        if (useEmail) {
            // instantiate EmailNotificationSender directly
        } else {
            // instantiate ConsoleNotificationSender directly
        }
    }
}
~~~

The service knows about all implementations and environment rules. Switching providers forces business code changes.

Move the decision into configuration:

~~~java
@Configuration
public class NotificationConfiguration {

    @Bean
    @Profile("dev")
    NotificationSender devSender() {
        return new ConsoleNotificationSender();
    }

    @Bean
    @Profile("prod")
    NotificationSender productionSender(EmailClient emailClient) {
        return new EmailNotificationSender(emailClient);
    }
}
~~~

This is an illustrative example; `EmailClient` must be configured separately. Each profile must ensure only one matching candidate exists if consumers require a single `NotificationSender`.

Now the service does not need to know which environment is running. The container selects the bean according to configuration and injects the contract into the service.

## 15. Transactions, Exceptions, and Side Effects Still Require Design

Decoupling implementations behind an interface does not automatically solve operational concerns.

For example, a service saves an order and then calls the sender:

~~~java
public String createOrder(Order order) {
    repository.save(order);
    notificationSender.sendOrderCreated(order.customerEmail(), order.id());
    return order.id();
}
~~~

If the database commits but sending the notification fails, the system state may violate business expectations. If sent before the transaction commits, a notification may go out even if the transaction later rolls back.

This is a question of **timing and consistency of side effects**, not merely interface injection.

A real-world system may need:

- Sending events after transaction commit.
- A transactional outbox to persist events alongside data changes in the same transaction.
- Bounded retries and idempotency handling.
- Recording delivery status and failure recovery.
- Separating synchronous operations from asynchronous processing when appropriate.

An interface decouples callers from delivery technology, yet the contract still needs accurate semantics and the application must design appropriate reliability guarantees.

## 16. Practice Exercises

### Exercise A: Converting a class dependency to an interface

Given the initial service:

~~~java
public class ReportService {
    private final PdfReportExporter exporter;

    public ReportService() {
        this.exporter = new PdfReportExporter();
    }

    public void export(Report report) {
        exporter.export(report);
    }
}
~~~

Tasks:

1. Create a `ReportExporter` interface.
2. Have `PdfReportExporter` implement the interface.
3. Update `ReportService`'s constructor to accept `ReportExporter`.
4. Instantiate the objects in `main` and pass the implementation in.
5. Add a `CsvReportExporter` without modifying service logic.

Goal: separate the business requirement to "export report" from PDF/CSV export details.

### Exercise B: Registering two Spring beans

Create two beans implementing `NotificationSender`:

- `ConsoleNotificationSender`.
- `EmailNotificationSender`.

Have `OrderService` accept `NotificationSender`. Observe the error when no selection rule exists. Then fix it using `@Qualifier` or `@Primary`.

Explain why the error occurs during context initialization rather than when sending a notification.

### Exercise C: Using profiles

Register the console sender for `dev` and the email sender for `prod`. Run the application with each profile. Confirm the logs reflect the active implementation while the service stays unchanged.

### Exercise D: Unit testing with a fake

Create `RecordingNotificationSender` to store the received recipient and message. Write `OrderServiceTest` using plain Java constructor injection. Assert that the use case passes the right data to the sender.

Do not create a Spring context in this unit test. Afterward, write a separate integration test if you want to verify bean wiring.

### Exercise E: Designing a contract for an external system

An application needs to store files on local disk in `dev` and in object storage in `production`.

Design:

~~~java
public interface DocumentStorage {
    StoredDocument store(DocumentContent content);
}
~~~

Create the two implementations and decide:

- Which package should the interface belong to?
- Which data types belong to the application?
- Where should object-storage-specific APIs be hidden?
- Should Spring choose the implementation by profile or by property?
- How will you test the service using a fake storage implementation?

This exercise applies the same principles to another infrastructure boundary.

## 17. Self-Check Questions

**1. Why should a service accept an interface instead of a concrete implementation?**

Because the service only needs a capability, while the way it is carried out may change. An interface keeps the contract stable and reduces coupling to infrastructure.

**2. Does an interface automatically make a dependency injectable?**

No. A bean implementation must be registered and selectable by Spring for the injection point.

**3. Are Dependency Injection and Dependency Inversion the same thing?**

No. DI is the technique of supplying dependencies from outside; DIP is the design principle of pointing dependencies toward appropriate abstractions.

**4. When two beans implement the same interface, what does Spring do?**

If an injection point requests a single bean without a clear selection rule, Spring fails with a multiple-candidates error. Use qualifiers, primary, profiles/conditions, or collection injection as needed.

**5. Why is constructor injection usually preferred?**

Because mandatory dependencies are explicit, the object is usable right after valid construction, fields can be `final`, and unit tests are easy to write in plain Java.

**6. Should you create an interface for every class?**

No. Create one only when the abstraction represents a meaningful boundary, contract, or variation point. Ceremonial interfaces do not automatically improve design.

**7. If an adapter switches from vendor A's SDK to vendor B's, what should change?**

The adapter implementation and bean configuration. The application service and its contract should stay untouched if the semantics the application relies on have not changed.

## 18. Conclusion

Interface-based bean injection connects Spring Boot components so that **business code depends on the capabilities it needs rather than the classes that execute them**. Interfaces define contracts; implementations handle details; constructor injection declares dependencies; and the Spring IoC container registers, selects, and supplies the right beans.

This approach combines Dependency Injection with Dependency Inversion, making it possible to swap implementations by environment, test services in isolation, and keep vendor details at the infrastructure boundary. Create interfaces when they express meaningful contracts, register implementations explicitly, and let consumers receive dependencies via constructors. That way, changing email, payment, storage, or external API technologies can be handled in adapters and configuration without disrupting business policies.
