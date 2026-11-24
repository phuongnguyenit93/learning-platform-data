# Boundary of Responsibility Between Container and Business Code

One of the easiest misunderstandings when learning Spring Boot is: **Spring creates and wires objects for us—so does Spring also take responsibility for how the application handles business logic?** The answer is no. The container gives the application the components it needs to operate; developers still must define **what the application needs to do**, which rules must be enforced, and how data should change.

In a small Java program, you can call **new** yourself, pass dependencies to constructors, and invoke methods. As a program grows, objects accumulate many dependency relationships: controllers use services, services use repositories, repositories use datasources, and many components share configuration. The **Spring IoC container** handles managing and assembling the components registered with it.

This lesson focuses on the boundary between **the container's object-management infrastructure** and **the business code owned by the application**. Understanding this boundary helps you use dependency injection, bean lifecycles, scopes, configuration, and Spring features for their intended purpose.

## 1. What Problem Does the IoC Container Solve?

**IoC (Inversion of Control)** is shifting control over certain program activities to another component or framework. In Spring, the closest example is **instantiating, managing, and supplying dependencies for objects**.

Look at manual Java code:

~~~java
public class Main {

    public static void main(String[] args) {
        ProductRepository repository = new ProductRepository();
        ProductService service = new ProductService(repository);
        ProductController controller = new ProductController(service);

        // The program decides how to create and connect each object itself.
    }
}
~~~

Here, code inside **main()** owns how each object is instantiated and the order in which they are wired. As the number of components grows, manual assembly easily turns into a long constructor chain that is hard to reconfigure and hard to manage for resource lifecycles.

With Spring, components can be declared as **beans**. The container reads configuration metadata, creates managed objects, and connects them:

~~~java
@Repository
public class ProductRepository {
    // Data access component.
}

@Service
public class ProductService {
    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }
}

@RestController
public class ProductController {
    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service;
    }
}
~~~

The example above illustrates three standalone classes; in a real project, each public class should live in its own file, packages/imports must be declared, and the startup class must sit within an appropriate component scan scope.

When the application starts, Spring can:

1. Find classes annotated with appropriate annotations such as **@Repository**, **@Service**, and **@RestController**.
2. Register bean definitions for those components.
3. Instantiate objects according to configured lifecycles and scopes.
4. Provide **ProductRepository** to **ProductService**, and then provide **ProductService** to **ProductController**.
5. Manage initialization/destruction callbacks and enabled infrastructure features.

**What Spring does not decide automatically** is which products are sold, when refunds are allowed, how much discount an order receives, or who is authorized to approve a request. Those decisions must appear in the application's domain model and business code.

### Diagram of the Two Layers of Responsibility

~~~text
                Spring IoC container
        ┌────────────────────────────────┐
        │ Read bean definitions           │
        │ Create objects per config/scope │
        │ Resolve and inject dependencies │
        │ Manage lifecycle and infra      │
        └────────────────────────────────┘
                     │ supplies beans
                     ▼
              Application code runs
        ┌────────────────────────────────┐
        │ Controller receives requests    │
        │ Service executes use cases      │
        │ Domain enforces rules           │
        │ Repository/adapter handles I/O  │
        └────────────────────────────────┘
                     │
                     ▼
               Business outcome
~~~

The container **makes it possible for components to collaborate**, while the content of that collaboration is defined by the application.

## 2. Beans, ApplicationContext, and Business Code

In Spring, a **bean** is an object managed by the IoC container. **ApplicationContext** is the high-level container interface commonly used in Spring Boot applications; it includes bean management, configuration, and many integrated services.

A Java object **does not need to become a bean** to hold business logic. For instance, **Money**, **Order**, **Address**, or **DiscountRule** can be ordinary Java classes or records created with **new** or via factories. Spring does not need to manage every individual data value in every request.

| Object Type | Usually Created By Whom? | Why |
|---|---|---|
| **OrderService**, **PaymentGateway**, **OrderController** | Spring container | Long-lived collaborators with dependencies and configuration |
| **DataSource**, configured HTTP client, shared **Clock** | Spring via auto-configuration or **@Bean** | Requires wiring, reuse, or resource management |
| **CreateOrderRequest** from JSON | Web deserialization mechanism per request | Input data for an individual call, not a singleton service |
| **Order** domain object | Business code, mapper, persistence layer | Represents a specific order |
| **BigDecimal** for totals, list of line items | Business code | Short-lived data values |

Do not interpret "Spring Boot application" as "every object must be injected." **Plain Java business code** is often easier to test and express rules in when it does not depend on the container.

### Difference Between a Bean and an Annotated Class

A class with **@Service** is only a candidate for bean registration. It must be discovered by **component scanning** or declared/imported through an appropriate configuration mechanism. If the class lies outside the scan scope or is excluded by a configuration condition, the container may lack a corresponding bean.

Conversely, a class without a stereotype annotation can still be created as a bean:

~~~java
@Configuration
public class AppConfiguration {

    @Bean
    public Clock clock() {
        return Clock.systemUTC();
    }
}
~~~

**Clock** is a Java standard library class without **@Service**. The **@Bean** method instructs the container to manage the returned object. This is especially useful for objects from libraries whose source code you cannot modify.

## 3. What the Container Is Actually Responsible For

| Responsibility | What Does the Container Do? | What Must the Application Still Decide? |
|---|---|---|
| **Bean registration** | Discovers or receives bean definitions via scanning, configuration, imports, auto-configuration | Which components are beans; which modules should be enabled |
| **Bean creation** | Invokes constructors/factory methods according to bean definitions | Which parameters constructors take, what objects represent |
| **Dependency injection** | Finds matching beans and passes them to required dependencies | Dependency contracts, usage patterns, and business flows |
| **Bean scope** | Manages instance count/lifespan by scope | Which state may be shared; whether it is concurrency-safe |
| **Lifecycle** | Invokes bean init/destroy callbacks via supported mechanisms | Which resources to open/close; avoiding unsuitable business work at startup |
| **Configuration** | Binds properties and creates beans per declared configuration | Which values make sense; which conditions are business rules |
| **AOP infrastructure** | Creates proxies and applies configured interceptors | Choosing transaction boundaries, caching behavior, and operation semantics |

**The container does not "understand" the name OrderService to infer an order-placement flow.** It knows which dependencies a bean requires and which infrastructure annotations/configs a method carries; the business content of the method remains Java code written by the developer.

### Responsibilities the Container Does Not Replace

- **Business rules:** pricing, limits, approval conditions, state validity.
- **Business outcomes:** when an order succeeds; when it is rejected; what error must be reported to users.
- **Data design:** which data to persist, data relationships, constraints, migrations, and handling concurrency conflicts.
- **Cross-system consistency:** retries, idempotency, outbox patterns, compensation when calling multiple independent services.
- **Business authorization rules:** who is permitted to act on a specific order, based on role and relationship to that order.
- **Error behavior:** whether a failure should be retried, refunded, or aborted.

Spring Boot supplies tools for some of these concerns, yet **using a tool does not mean the tool decides the right product rules itself**.

## 4. Dependency Injection: Who Creates Dependencies, Who Uses Them?

Suppose a service needs somewhere to store orders:

~~~java
public interface OrderStore {
    Order save(Order order);
}
~~~

The service can declare the dependency via constructor:

~~~java
@Service
public class OrderService {

    private final OrderStore store;

    public OrderService(OrderStore store) {
        this.store = store;
    }

    public Order create(Order order) {
        return store.save(order);
    }
}
~~~

With a single bean implementing **OrderStore** in the context, Spring can inject it into **OrderService**. The service receives a **storage contract**, rather than having to decide at runtime which kind of database client to instantiate.

**Division of responsibility:**

- **Container:** locates the matching implementation, creates the object, and passes it to the constructor.
- **OrderService:** decides when to call **store.save**, what data checks must happen beforehand, and what the returned result means.
- **OrderStore implementation:** performs storage using a concrete technology, handles data mapping, and manages infrastructure errors within its scope.

### Why Prefer Constructor Injection?

Constructors make mandatory dependencies explicit. A class can be instantiated in tests by passing a substitute dependency without booting the entire Spring context.

~~~java
OrderStore fakeStore = order -> order;
OrderService service = new OrderService(fakeStore);
~~~

Here Java code instantiates the service itself to verify behavior. **A Spring container is not needed for every unit test.** Precisely because the service asks only for an interface, tests can swap the storage layer.

For a class with a single constructor, Spring normally injects that constructor without needing the **@Autowired** annotation. When multiple constructors or multiple candidate beans exist, how Spring chooses dependencies must be specified with clear configuration.

### When Dependencies Are Missing or Too Numerous

If a service requires **OrderStore** yet the context lacks a matching implementation, Spring typically fails during bean creation. If the context holds two implementations of the same type, Spring may not know which bean to pick.

Tools such as **@Qualifier**, **@Primary**, or conditional configuration can resolve implementation selection. However, **choosing which storage technology to use** is an application configuration decision; the container only enforces the selection rules you provided.

## 5. End-to-End Example: Same Business Logic, Spring Only Assembles

Let us build a small example: a system accepting an order quantity and calculating the total amount. A product has a preconfigured unit price; when buying **10 units** or more, the order receives a **10%** discount. To keep focus on IoC, order data is stored in memory. This is a learning example, not a real payment system.

Application structure:

~~~text
src/main/java/com/example/checkout/
├── CheckoutApplication.java
├── domain/
│   ├── Order.java
│   └── PricingPolicy.java
├── application/
│   ├── OrderService.java
│   └── OrderStore.java
├── infrastructure/
│   ├── InMemoryOrderStore.java
│   ├── ShopProperties.java
│   └── BusinessConfiguration.java
└── web/
    ├── OrderController.java
    └── OrderErrorHandler.java

src/main/resources/
└── application.yml
~~~

In a Spring Initializr app, the **Spring Web** dependency suffices for the HTTP layer and basic configuration in this example. Java classes use **Java 21**; no database starter is needed because data stays in memory.

### 5.1. Domain Object: Concrete Data Is Not a Bean

File **domain/Order.java**:

~~~java
package com.example.checkout.domain;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record Order(
        UUID id,
        int quantity,
        BigDecimal total,
        Instant createdAt) {
}
~~~

Each **Order** represents a specific order. It is a **business value**, not a singleton bean shared across requests.

### 5.2. Pricing Rules: Plain Java

File **domain/PricingPolicy.java**:

~~~java
package com.example.checkout.domain;

import java.math.BigDecimal;

public final class PricingPolicy {

    private static final BigDecimal BULK_RATE =
            new BigDecimal("0.90");

    private final BigDecimal unitPrice;

    public PricingPolicy(BigDecimal unitPrice) {
        if (unitPrice == null || unitPrice.signum() <= 0) {
            throw new IllegalArgumentException(
                    "Unit price must be greater than 0");
        }
        this.unitPrice = unitPrice;
    }

    public BigDecimal calculateTotal(int quantity) {
        if (quantity <= 0 || quantity > 100) {
            throw new IllegalArgumentException(
                    "Quantity must be between 1 and 100");
        }

        BigDecimal subtotal =
                unitPrice.multiply(BigDecimal.valueOf(quantity));

        // Business rule: buying 10 or more units gets a 10% discount.
        return quantity >= 10
                ? subtotal.multiply(BULK_RATE)
                : subtotal;
    }
}
~~~

**PricingPolicy** carries no Spring annotations. The rule "buy 10 or more units for 10% off" is plain Java code. Spring does not know or enforce that rule itself; it only manages a **PricingPolicy** instance if we declare it as a bean.

Because **PricingPolicy** holds an **immutable BigDecimal** value and its method uses only local variables, using a singleton bean for this policy fits well in this example.

### 5.3. Configuration: Creating Beans from Configured Values

We use Spring Boot **@ConfigurationProperties** to read the unit price from external configuration rather than hardcoding a fixed value inside the configuration class. In a real application, unit prices might also come from a database or a pricing management system suited to the business.

File **infrastructure/ShopProperties.java**:

~~~java
package com.example.checkout.infrastructure;

import java.math.BigDecimal;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "shop")
public record ShopProperties(BigDecimal unitPrice) {
}
~~~

File **infrastructure/BusinessConfiguration.java**:

~~~java
package com.example.checkout.infrastructure;

import java.time.Clock;

import com.example.checkout.domain.PricingPolicy;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(ShopProperties.class)
public class BusinessConfiguration {

    @Bean
    public PricingPolicy pricingPolicy(ShopProperties properties) {
        return new PricingPolicy(properties.unitPrice());
    }

    @Bean
    public Clock clock() {
        return Clock.systemUTC();
    }
}
~~~

And file **application.yml**:

~~~yaml
shop:
  unit-price: 250000
~~~

Spring Boot binds the **shop.unit-price** key to **unitPrice**, and the container passes **ShopProperties** to the factory method to construct **PricingPolicy**.

Here, the boundary is crisp:

- **Spring** reads configuration, binds the object, and calls the **@Bean** methods.
- **BusinessConfiguration** only describes how to instantiate **PricingPolicy** and **Clock**.
- **PricingPolicy.calculateTotal** still executes the discount rule itself.

### 5.4. Storage Contract and Adapter

File **application/OrderStore.java**:

~~~java
package com.example.checkout.application;

import java.util.Optional;
import java.util.UUID;

import com.example.checkout.domain.Order;

public interface OrderStore {

    Order save(Order order);

    Optional<Order> findById(UUID id);
}
~~~

File **infrastructure/InMemoryOrderStore.java**:

~~~java
package com.example.checkout.infrastructure;

import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

import com.example.checkout.application.OrderStore;
import com.example.checkout.domain.Order;
import org.springframework.stereotype.Repository;

@Repository
public class InMemoryOrderStore implements OrderStore {

    private final Map<UUID, Order> orders =
            new ConcurrentHashMap<>();

    @Override
    public Order save(Order order) {
        orders.put(order.id(), order);
        return order;
    }

    @Override
    public Optional<Order> findById(UUID id) {
        return Optional.ofNullable(orders.get(id));
    }
}
~~~

**@Repository** lets the class be discovered as a Spring component inside scanned packages. The container can create **one shared storage instance**; **put**, **findById**, and the **ConcurrentHashMap** storage logic are Java code written by the application.

This store keeps data only in memory and loses it when the application stops. The container does not automatically turn it into a durable database, persist data across restarts, or enforce business constraints of real payment workflows.

### 5.5. Application Service: Coordinating the Use Case

File **application/OrderService.java**:

~~~java
package com.example.checkout.application;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

import com.example.checkout.domain.Order;
import com.example.checkout.domain.PricingPolicy;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final PricingPolicy pricingPolicy;
    private final OrderStore store;
    private final Clock clock;

    public OrderService(
            PricingPolicy pricingPolicy,
            OrderStore store,
            Clock clock) {
        this.pricingPolicy = pricingPolicy;
        this.store = store;
        this.clock = clock;
    }

    public Order createOrder(int quantity) {
        BigDecimal total = pricingPolicy.calculateTotal(quantity);

        Order order = new Order(
                UUID.randomUUID(),
                quantity,
                total,
                Instant.now(clock));

        return store.save(order);
    }

    public Optional<Order> findById(UUID id) {
        return store.findById(id);
    }
}
~~~

Spring injects the three dependencies the service needs, yet **does not decide when to create an order**, **does not calculate totals on behalf of PricingPolicy**, and **does not call store.save itself**. Those calls live inside **OrderService.createOrder(...)**, which is business code owned by the application.

### 5.6. Web Adapter: Exposing HTTP to the Use Case

File **web/OrderController.java**:

~~~java
package com.example.checkout.web;

import java.net.URI;
import java.util.UUID;

import com.example.checkout.application.OrderService;
import com.example.checkout.domain.Order;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<Order> create(
            @RequestBody CreateOrderRequest request) {
        Order order = service.createOrder(request.quantity());

        return ResponseEntity
                .created(URI.create("/orders/" + order.id()))
                .body(order);
    }

    @GetMapping("/{id}")
    public ResponseEntity<Order> get(@PathVariable UUID id) {
        return service.findById(id)
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    public record CreateOrderRequest(int quantity) {
    }
}
~~~

File **web/OrderErrorHandler.java**:

~~~java
package com.example.checkout.web;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class OrderErrorHandler {

    @ExceptionHandler(IllegalArgumentException.class)
    public ProblemDetail invalidOrder(
            IllegalArgumentException exception) {
        return ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                exception.getMessage());
    }
}
~~~

**OrderController** decides HTTP methods, paths, response statuses, and how to invoke the service. **OrderErrorHandler** translates input errors thrown from business logic into HTTP 400 responses for clients. The container discovers and registers the controller and advice as beans, while their methods are invoked by Spring MVC when matching requests arrive.

In larger projects, response DTOs can be separated instead of returning domain models directly. This example uses the domain record directly so readers stay focused on the boundary between container and business logic.

### 5.7. Starting Up and Sending a Request

File **CheckoutApplication.java**:

~~~java
package com.example.checkout;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CheckoutApplication {

    public static void main(String[] args) {
        SpringApplication.run(CheckoutApplication.class, args);
    }
}
~~~

The **domain**, **application**, **infrastructure**, and **web** packages sit under **com.example.checkout**, so default component scanning finds the registered classes. Spring Boot starts the ApplicationContext and, since the project includes Spring Web, sets up appropriate HTTP infrastructure.

Send a request:

~~~bash
curl -i -X POST http://localhost:8080/orders \
  -H "Content-Type: application/json" \
  -d '{"quantity":10}'
~~~

Example response:

~~~http
HTTP/1.1 201 Created
Location: /orders/6a3514cd-93e2-4b54-9e58-614e12bf798d
Content-Type: application/json

{
  "id": "6a3514cd-93e2-4b54-9e58-614e12bf798d",
  "quantity": 10,
  "total": 2250000.00,
  "createdAt": "2026-01-01T00:00:00Z"
}
~~~

The UUID and timestamp in the response are illustrative values. The total comes from the rule in **PricingPolicy**: 250,000 × 10 × 0.90 = 2,250,000.

With quantity **0**, **PricingPolicy** throws **IllegalArgumentException**; the web adapter converts the error into HTTP 400. The container did not invent the 1–100 limit or that discount policy.

### 5.8. Container and Business Logic Engage at Two Different Times

~~~text
APPLICATION STARTUP

Spring Boot creates ApplicationContext
        │
        ├── Reads shop.unit-price config
        ├── Binds ShopProperties
        ├── Calls @Bean to create PricingPolicy and Clock
        ├── Creates InMemoryOrderStore
        ├── Injects beans into OrderService
        └── Injects OrderService into OrderController
                                      │
                                      ▼
                              Application is ready

ON HTTP REQUEST POST /orders

Spring MVC receives and parses JSON
        │
        ▼
OrderController.create(...)
        │
        ▼
OrderService.createOrder(...)
        │
        ├── PricingPolicy.calculateTotal(...)  ← business rule
        ├── Create Order                       ← business data
        └── OrderStore.save(...)               ← storage operation
        │
        ▼
OrderController returns 201 + result
~~~

Distinguishing **startup/bean assembly** from **runtime/business execution** is one of the keys to understanding the IoC container.

## 6. Scope: The Container Manages Instances, Business Code Manages State

By default, Spring beans have **singleton scope**: within one Spring container, there is typically **one instance per bean definition** shared wherever injected. This differs from a "JVM-wide singleton" and does not mean an instance is shared across multiple application processes.

A singleton **@Service** can be invoked by many requests concurrently. Therefore:

~~~java
@Service
public class UnsafeOrderService {

    private String currentCustomerId;

    public void process(String customerId) {
        currentCustomerId = customerId;
        // Another request can overwrite this field.
    }
}
~~~

The **currentCustomerId** field is per-request state placed on a shared bean. When multiple requests run concurrently, data can be overwritten or leak across executions.

A more suitable organization:

~~~java
@Service
public class OrderService {

    public void process(String customerId) {
        // customerId is a parameter local to the current call.
        // Shared dependencies are held in final fields.
    }
}
~~~

**The container is responsible for instance count and lifecycle per scope**, whereas **the application is responsible for whether state is concurrency-safe**. Spring does not automatically add locks around mutable fields.

### Common Scopes

| Scope | Meaning | Considerations |
|---|---|---|
| **singleton** | One instance per bean definition in each Spring container | Fits stateless services and shared configuration |
| **prototype** | Creates a new instance when the container is asked to supply the bean | Does not automatically mean one instance per HTTP request; the container does not manage full destruction of each instance like singletons |
| **request** | Instance per HTTP request in a web-aware context | Fits state genuinely bound to a request; use only when an appropriate web context exists |
| **session** | Instance per HTTP session in a web-aware context | Requires considering session lifecycle, memory, and distributed deployments |

Do not convert every service to **prototype** or **request scope** to patch misplaced state. Prefer low-state services where per-request data is passed via parameters or dedicated objects.

A singleton bean directly injecting a prototype bean normally receives the instance created during dependency resolution, **not automatically a fresh instance on every method call**. If dynamic instance creation is genuinely needed, use **ObjectProvider** or an appropriate factory.

## 7. Lifecycle: The Container Knows When to Call Callbacks, Business Code Knows What They Do

For a Spring-managed bean, a simplified lifecycle looks like:

~~~text
Read bean definition
        │
        ▼
Instantiate object / constructor
        │
        ▼
Inject dependencies and configuration
        │
        ▼
BeanPostProcessor steps and init callbacks
        │
        ▼
Bean ready to serve the application
        │
        ▼
Context closes
        │
        ▼
Destroy callbacks for appropriately managed beans
~~~

Spring supports callbacks such as **@PostConstruct** and **@PreDestroy** for beans with appropriately managed lifecycles:

~~~java
@Component
public class ConnectionMonitor {

    @PostConstruct
    public void initialize() {
        // Prepare required technical state.
    }

    @PreDestroy
    public void cleanup() {
        // Release resources if the component owns them.
    }
}
~~~

In Spring Boot 3.x, the lifecycle annotations in the example belong to the **jakarta.annotation** package. Imports have been omitted in the snippet.

**The container decides when to call the callbacks** according to the lifecycle, while **the callback body** is defined by the class. It does not automatically know to "send customer emails" or "lock paid orders."

### Should Heavy Business Logic Go Inside `@PostConstruct`?

Usually no. **@PostConstruct** serves bean initialization and runs while the context is being set up. If you import millions of records, call an unstable external service, or emit business notifications here, startup can slow down, fail, or produce hard-to-control side effects.

Spring Boot provides **ApplicationRunner** and **CommandLineRunner** to run logic after the context has been initialized; schedulers, message listeners, or job orchestrators can serve background tasks. Even with those mechanisms, the application must still design retries, idempotency, job state, and business outcomes appropriately.

**Object lifecycle is not business lifecycle.** A bean being created/destroyed is completely different from an order transitioning **CREATED → PAID → SHIPPED**. State machines and transition conditions belong to business logic.

## 8. `@Transactional`: The Boundary Between Business Declaration and Execution Mechanics

**@Transactional** is a clear example of framework and application code collaborating. Suppose placing an order must both create the order and deduct inventory in the same database. The application service decides these two operations must form one consistent unit:

~~~java
@Service
public class CheckoutService {

    @Transactional
    public void checkout(CheckoutCommand command) {
        stockRepository.decrease(command.productId(),
                                 command.quantity());
        orderRepository.save(newOrder(command));
    }
}
~~~

This snippet only illustrates a transaction boundary; types and methods such as **CheckoutCommand**, **stockRepository**, and **newOrder** must be defined in the corresponding application.

Here:

- **The business author** decides which operations belong in the same transaction and their execution order.
- **Spring transaction infrastructure**, via a transaction manager and usually a proxy/interceptor, opens, commits, or rolls back the transaction according to configuration and rollback rules.
- **The database/persistence provider** enforces the transactional guarantees supported by that technology.

The framework **does not automatically know** that "deducting stock must accompany creating an order" if the use case is not structured properly. Nor does it automatically solve every form of distributed consistency.

### Three Very Important Limitations to Remember

**1. Transactions usually operate via proxies.** If a bean calls another **@Transactional** method on itself via **this.method(...)**, the internal call may bypass the proxy and fail to trigger interception as expected.

**2. Rollback follows rules.** By default, Spring typically rolls back on **RuntimeException** and **Error**, yet does not roll back every checked exception by default; explicit configuration is needed if the use case requires it.

**3. Database transactions do not automatically wrap HTTP/email/queues.** If you write to the database and then sending an email fails, **@Transactional** on the service will not automatically undo the email or turn two systems into a distributed transaction. The application needs an appropriate strategy such as an outbox, safe retries, or business orchestration.

**@Transactional(readOnly = true)** is a hint to the transaction/persistence infrastructure, not a way to enforce a business rule prohibiting users from modifying data.

## 9. Validation: The Framework Checks Constraints, Who Defines Them?

Spring and Bean Validation can help trigger checks against constraints declared by the developer:

~~~java
public record CreateAccountRequest(
        @NotBlank String customerName,
        @Email String email) {
}
~~~

When a request body is annotated with **@Valid** in a controller and proper validation infrastructure is present, the framework can check **@NotBlank** and **@Email** and produce errors when data fails to satisfy them.

However, the constraint "email has valid syntax" differs from rules such as:

- A customer cannot open two active accounts for the same product.
- Credit limits vary according to transaction history.
- An order can only be canceled before handover to the shipping carrier.
- Promotions apply only when the customer meets multiple criteria.

The latter rules may require domain/application services, repository data, concurrency controls, and proper transactions. **Validation infrastructure enforces declared constraints; it does not infer the entire product policy itself.**

Therefore, distinguish:

| Concern | Usually Handled Where |
|---|---|
| Is JSON properly formatted to convert into a DTO? | HTTP framework / message converter |
| Is a required field blank? | Bean Validation at the input boundary, or business layer when needed |
| Is the user allowed to cancel this order? | Authorization and business rules |
| Can an order already SHIPPED revert to CREATED? | Domain/application logic |
| Does a transaction roll back properly? | Transaction infrastructure applied per configuration and business flow |

## 10. Configuration and `@Profile` Are Not Business Rules

Spring supports **@Configuration**, **@Bean**, **@Conditional**, **@Profile**, **@ConfigurationProperties**, and other mechanisms to create or choose beans by environment. They fit the question:

> Which environment is this application running in, which implementation should it use, and how should dependencies be configured?

For example, you can use a mock email-sending implementation in a development environment and a real adapter in an environment configured to send emails.

By contrast, questions like:

> Does customer A qualify for free shipping? Is order B eligible for a refund?

are decisions driven by business data and runtime state, not reasons to create a different Spring bean for **each customer** using **@Profile**.

**Distinguish clearly:**

- **Bean configuration** is primarily about selecting and wiring components for an application context.
- **Business decisions** are executed while handling a use case, typically depending on input, data, and state at that moment.

Do not design elaborate configuration annotations to replace a clear business method. Spring's tools should serve application logic, not obscure it.

## 11. When Does the Container Actually Call Code You Wrote?

The container and integrated frameworks can invoke application code at multiple points:

| Moment | Who Initiates the Call? | What Does Application Code Do? |
|---|---|---|
| Bean creation | IoC container | Constructor/factory method instantiates the object |
| After initialization | Lifecycle infrastructure | Callback initializes required resources |
| HTTP request arrives | Spring MVC/WebFlux infrastructure | Controller handles the request and calls the service |
| Schedule triggers | Scheduling infrastructure | **@Scheduled** method executes the authored task |
| Message arrives | Messaging integration | Listener turns the message into a use case |
| Transactional method called via proxy | AOP/transaction interceptor | Service executes business logic within transaction boundaries |
| Application stops | ApplicationContext lifecycle | Cleanup callback releases resources |

**IoC is not just "Spring calls constructors for you,"** because the framework can also orchestrate lifecycles and configured entry points. Still, **what gets invoked is application code** with rules, conditions, and outcomes defined by the developer.

In a web application, for instance:

~~~text
Spring MVC selects the right controller method
                   │
                   ▼
Controller calls OrderService
                   │
                   ▼
OrderService enforces rules
                   │
                   ▼
Repository persists data
                   │
                   ▼
Spring MVC converts result to HTTP response
~~~

Spring MVC manages **dispatching and HTTP mechanics**; the service manages the **business meaning** of the operation.

## 12. Do Not Use `ApplicationContext` as a "Lookup Warehouse" in Every Service

A common design mistake is injecting the container into a service and requesting beans by name in every method:

~~~java
@Service
public class PaymentService {

    private final ApplicationContext context;

    public PaymentService(ApplicationContext context) {
        this.context = context;
    }

    public void pay() {
        PaymentGateway gateway =
                context.getBean(PaymentGateway.class);
        gateway.charge();
    }
}
~~~

The code above illustrates direct dependence on the container. Reading the constructor, you cannot tell the service actually needs **PaymentGateway**; only by reading the method body does it become visible. This obscures dependencies and easily pulls the Spring context into tests.

Normally you should write:

~~~java
@Service
public class PaymentService {

    private final PaymentGateway gateway;

    public PaymentService(PaymentGateway gateway) {
        this.gateway = gateway;
    }

    public void pay() {
        gateway.charge();
    }
}
~~~

The example assumes **PaymentGateway** has a **charge()** method and a matching implementation bean. The container still selects and injects the dependency, while the business service depends only on **the contract it needs**.

Using **ApplicationContext** directly is not always wrong: framework bootstrap code, plugin hosts, dynamic bean discovery, or tooling sometimes have genuine needs. For a typical business service, however, **constructor injection** expresses dependencies far more transparently.

## 13. Common Misconceptions

### "Adding `@Service` Makes Spring Automatically Understand What the Class Does"

No. **@Service** registers a bean via Spring mechanics. Class names, annotations, and the container do not replace implementing business methods.

### "Container Manages Beans Means the Container Manages All Application Data"

No. The container manages **beans**; order data, request payloads, database entities, and domain objects have different lifecycles. Never store per-user changing data in fields of a singleton service just because it is a Spring bean.

### "With Dependency Injection, You Don't Need to Design Boundaries"

No. Dependency injection will happily wire a tangled, multi-responsibility, hard-to-maintain design if code still depends in the wrong direction. The container does not choose the right architecture for your application.

### "`@Transactional` Makes Every Task Automatically Consistent"

No. Transactions apply per supported scope and technology, with specific proxy and rollback rules. Business consistency across multiple systems still has to be designed.

### "Singleton Beans Are Guaranteed Concurrency-Safe"

No. Singleton is a **scope**, not a thread-safety guarantee. Mutable state on singletons must be designed carefully.

### "Use `@PostConstruct` to Run All One-Off Business Work"

You should not default to this. Init callbacks belong to bean lifecycles. One-off, scheduled, or durable-state business jobs usually have better orchestration mechanisms.

### "Just Add a Package to Component Scan and Spring Finds Every Dependency"

No. Classes must exist on the runtime classpath, be registered through matching mechanisms, and not be excluded by configuration conditions. JPA entities, repository proxies, and configuration properties each have their own registration mechanisms.

### "Removing Spring Means Rewriting All Business Code"

Not necessarily. Plain Java business code separated from HTTP, databases, and container APIs can keep running with manually supplied dependencies or in other test environments. The more tightly business logic couples to framework APIs and service locators, the harder reuse becomes.

## 14. Experiments to Distinguish Container and Business Responsibilities

After understanding the **PricingPolicy** and **OrderService** example, try the changes below and predict the outcome before running:

| Change | Component to Edit | What You Observe |
|---|---|---|
| Change unit price from 250,000 to 300,000 | **application.yml** or pricing config source | Total changes; service still calls the same policy |
| Change bulk threshold from 10 units to 5 | **PricingPolicy** | Pricing rule changes without changing how Spring injects beans |
| Use a database store instead of in-memory | **OrderStore implementation** and persistence config | Business code can keep the same contract; storage infra changes |
| Add an HTTP endpoint to read orders | **OrderController** | Web adapter changes; service/repository are reused |
| Missing **Clock** bean | Configuration | Container cannot satisfy `OrderService`'s dependency |
| Create two **OrderStore** beans of the same type with no selection rule | Configuration/bean registration | Spring may report ambiguous dependency |
| Store `currentOrderId` in a singleton `OrderService` field | Service state design | Concurrent requests can interfere with each other; container does not protect it |
| Call an `@Transactional` method from another method on the same object | Transaction boundary design | Risks bypassing the transaction proxy as expected |

Each scenario answers: **is this a change in how the system is assembled, or a change in the rules and behavior when a use case runs?**

### Unit Testing Rules Without Spring

Because **PricingPolicy** is a plain Java class, JUnit can test it directly:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import com.example.checkout.domain.PricingPolicy;

class PricingPolicyTest {

    @Test
    void appliesDiscountForTenOrMoreItems() {
        PricingPolicy policy =
                new PricingPolicy(new BigDecimal("250000"));

        BigDecimal actual = policy.calculateTotal(10);

        assertEquals(
                0,
                new BigDecimal("2250000.00").compareTo(actual));
    }
}
~~~

This test verifies the **discount rule**, not the container. When you want to test **@ConfigurationProperties**, bean registration, constructor injection, or context initialization, that is when a test with an appropriate Spring context is needed.

That is the practical payoff of a clear boundary: **rules are tested independently of the framework; assembly is tested where framework participation is needed**.

## 15. Questions That Help Identify the Right Boundary

When deciding where a piece of code belongs, ask yourself:

1. **If we switched from a REST API to a CLI, would this rule still hold?** If yes, it is likely business logic and should not be coupled to controllers or `HttpServletRequest`.
2. **Is this code deciding how a bean is created, or how an order is processed?** The former usually belongs to configuration/container; the latter belongs to service/domain.
3. **Does this value live for the entire lifetime of the application or only for a single request?** Shared collaborators can be singletons; per-request data should have an appropriate lifespan.
4. **When something fails, who knows the right business action?** The framework knows how to throw exceptions or roll back per technical rules; the application knows whether to cancel an order, refund, retry, or notify the user.
5. **Can the rule be tested in plain Java?** If so, business code is relatively decoupled from infrastructure and easier to test.
6. **Will widening component scan or adding annotations actually fix the root cause?** If a bean is missing due to classpath, configuration conditions, or mismatched dependency types, tweaking scans does not solve the real problem.

## Conclusion

**The Spring IoC container is responsible for managing and assembling beans:** discovering/registering, instantiating, injecting dependencies, applying scopes, lifecycles, and configured infrastructure capabilities. The container keeps the application organized as component count grows.

**Business code is responsible for the meaning and outcome of each use case:** which data is valid, which rules apply, which operations must execute, and what happens on success or failure. Spring can assist with validation, transactions, web dispatch, and many other mechanisms, yet they do not define business policy themselves.

Let **the container answer "which components are created, connected, and managed how?"** and let **services/domain answer "how must the application process this work?"**. By preserving that boundary, Spring Boot unlocks the power of dependency injection while business code stays clear, testable, and maintainable.
