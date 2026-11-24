# Inversion of Control and the Object Graph Management Problem

A Java program rarely consists of a single object operating independently. A controller receiving an HTTP request needs to call a service; the service needs a repository, a pricing calculator, or a client calling an external system; the repository in turn needs a database connection object. Those objects **depend on one another** and form an **object graph**.

Spring Boot handles most of the work of creating and wiring this graph through the **Spring IoC container**. To understand that mechanism, we should start from the concrete problem: who is responsible for creating objects, choosing implementations, providing dependencies, managing lifecycles, and ensuring consistent configuration?

**Inversion of Control (IoC)** is the principle of transferring the decision of creating and connecting components from application code to an external orchestrating mechanism. **Dependency Injection (DI)** is one way of implementing IoC: an object receives the dependencies it needs from the outside instead of creating them itself. In Spring, that external mechanism is primarily the **ApplicationContext**, an IoC container capable of registering, instantiating, wiring, and managing **beans**.

## 1. What Is an Object Graph?

Suppose a bookstore application has an endpoint to calculate order pricing:

- `QuoteController` receives the HTTP request.
- `QuoteService` handles the quote calculation rules.
- `ProductCatalog` looks up book information.
- `PricingPolicy` calculates the total amount according to the pricing policy.
- `InMemoryProductCatalog` and `StandardPricingPolicy` are concrete implementations.

The relationship between them can be visualized as follows:

~~~text
HTTP request
     |
     v
QuoteController
     |
     v
QuoteService
     |                     |
     v                     v
ProductCatalog        PricingPolicy
     ^                     ^
     |                     |
InMemoryProductCatalog  StandardPricingPolicy
~~~

The **nodes** of the graph are the objects (or bean definitions when speaking of the configuration phase), and the **edges** represent the relationship where one object needs or holds a reference to another object. With the diagram above:

- The controller cannot work properly without the service.
- The service depends on two contracts, without needing to know how to create the implementations itself.
- The implementation of `ProductCatalog` can be swapped while keeping `QuoteService` code intact if the contract does not change.

A real graph can be much larger and **is not necessarily a tree**. Two services can share the same repository bean, configuration bean, or HTTP client. One object can be referenced by multiple other objects; even worse, if poorly designed, circular dependencies can form.

### Dependency Graph Is Not the Same as Call Flow

Two concepts are often confused:

- **Dependency graph:** which object needs a reference to which object in order to operate.
- **Execution flow:** during a request or event, which method is actually called and in what order.

The fact that `QuoteService` holds a reference to `ProductCatalog` does not mean every call to the service must call the catalog. A dependency describes the **capabilities and wiring requirements** of a component; execution flow depends on logic and input.

## 2. The Problem When Each Class Creates Dependencies with `new`

In a simple application, we might write:

~~~java
public class QuoteService {
    private final ProductCatalog catalog =
            new InMemoryProductCatalog();

    private final PricingPolicy pricing =
            new StandardPricingPolicy();

    public long quote(String sku, int quantity) {
        Product product = catalog.findBySku(sku)
                .orElseThrow();
        return pricing.total(product.unitPrice(), quantity);
    }
}
~~~

This code can run, but `QuoteService` is doing two things: **handling business logic** and **deciding how to construct the infrastructure supporting that business logic**. The consequences become clear when requirements change:

1. If we need to read the catalog from PostgreSQL instead of memory, we must modify how dependencies are created inside the service or add environment conditionals.
2. When testing, it is difficult to supply a fake catalog with controlled data because the service creates the real catalog itself.
3. When multiple services need the same catalog or network client, each place might create a different instance, potentially duplicating connection pools, caches, or configuration.
4. If `InMemoryProductCatalog` in turn needs a `DataSource` or configuration, the chain of `new` calls spreads to other classes.
5. Choices such as secrets, timeouts, or external endpoints may end up hardcoded inside business code.

The core issue is not that the `new` keyword is bad. Creating a short-lived value object, such as `new OrderLine(...)` or `new ArrayList<>()` inside a method, is completely normal. The problem arises when a business class **owns the creation of long-lived collaborators**, especially dependencies that vary by environment or need to be shared.

## 3. Dependency Injection Moves Assembly Outside

An important improvement is receiving dependencies through the constructor:

~~~java
public class QuoteService {
    private final ProductCatalog catalog;
    private final PricingPolicy pricing;

    public QuoteService(
            ProductCatalog catalog,
            PricingPolicy pricing
    ) {
        this.catalog = catalog;
        this.pricing = pricing;
    }

    public long quote(String sku, int quantity) {
        Product product = catalog.findBySku(sku)
                .orElseThrow();
        return pricing.total(product.unitPrice(), quantity);
    }
}
~~~

Now, the service simply states: "I need a `ProductCatalog` and a `PricingPolicy`." The assembly code lives elsewhere:

~~~java
ProductCatalog catalog = new InMemoryProductCatalog();
PricingPolicy pricing = new StandardPricingPolicy();

QuoteService quoteService = new QuoteService(catalog, pricing);
QuoteController controller = new QuoteController(quoteService);
~~~

With this approach, plain Java still has DI: objects are **injected via constructor**. We do not need Spring yet to apply the principle, because constructor injection is a standard Java design technique.

The central place where objects are created and wired together is often called the **composition root**. With Spring Boot, most of this role is shifted to bean definitions, component scanning, `@Configuration`, `@Bean`, and the auto-configuration mechanism. The ApplicationContext uses that information to perform the wiring.

### What Exactly Is Being "Inverted"?

Compare the two directions of control:

~~~text
Controlling dependency creation internally:

QuoteService
    |
    +-- new InMemoryProductCatalog()
    |
    +-- new StandardPricingPolicy()


Dependency Injection:

Composition root / Spring container
    |
    +-- creates InMemoryProductCatalog
    +-- creates StandardPricingPolicy
    +-- creates QuoteService(catalog, pricing)
                 |
                 +-- only uses provided dependencies
~~~

Before applying DI, `QuoteService` controlled choosing and creating the implementations. Afterward, **an external party** passes the implementations to the service. The service still retains full control over its business rules; IoC does not mean every Java statement is executed by the framework.

## 4. How Do IoC, DI, Bean, and ApplicationContext Differ?

| Concept | Meaning | Example |
|---|---|---|
| **IoC** | The principle of transferring part of the control over object assembly and lifecycle to an external mechanism | The container creates and wires components |
| **DI** | A way of providing dependencies from the outside to an object | `new QuoteService(catalog, pricing)` |
| **Bean** | An object managed by the Spring container | `QuoteService` annotated with `@Service` and scanned |
| **Bean definition** | Metadata telling the container how to create/configure a bean | Metadata from `@Component` or a `@Bean` method |
| **BeanFactory** | Core interface providing bean registration/retrieval and basic container mechanisms | The foundation of bean management |
| **ApplicationContext** | Common container interface extending BeanFactory with many integrated capabilities | Context created by `SpringApplication.run(...)` |
| **Auto-configuration** | Spring Boot mechanism that registers configuration based on classpath, beans, properties, and conditions | Automatically configuring a web server or DataSource when applicable |

An important point: **not every Java object is a Spring bean**. Objects created with regular `new` still exist and are useful; they simply do not automatically participate in the container's lifecycle management, wiring, AOP, or DI.

A bean typically has a **name**, **type**, **scope**, creation mechanism, dependencies, and other metadata. The container uses this information to build a working object graph.

## 5. Spring Boot Example: Letting the Container Assemble a Small Graph

The example below uses a Spring Boot web application with Java 17 or later and Spring MVC. To run in the usual way, the project needs the web starter corresponding to the Spring Boot version in use. The classes reside in the same package `com.example.shop` to focus on the DI mechanism; in real projects they can be split into multiple packages by feature.

### 5.1. Entry Point Placed in the Root Package

File `ShopApplication.java`:

~~~java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

`@SpringBootApplication` includes configuration and component scanning by package convention, while also enabling Spring Boot auto-configuration. Placing the class in `com.example.shop` lets Spring scan beans located in this package and its subpackages.

### 5.2. Defining Contracts Instead of Binding to Implementations

File `Product.java`:

~~~java
package com.example.shop;

public record Product(
        String sku,
        long unitPrice,
        int availableQuantity
) {}
~~~

File `ProductCatalog.java`:

~~~java
package com.example.shop;

import java.util.Optional;

public interface ProductCatalog {
    Optional<Product> findBySku(String sku);
}
~~~

File `PricingPolicy.java`:

~~~java
package com.example.shop;

public interface PricingPolicy {
    long total(long unitPrice, int quantity);
}
~~~

These are normal Java types; `Product` specifically is a data-holding record that does not necessarily need container management. The two interfaces describe the capabilities required by the service; they do not automatically become beans unless an implementation or corresponding bean is registered.

### 5.3. Registering Implementations with the Container

File `InMemoryProductCatalog.java`:

~~~java
package com.example.shop;

import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Repository;

@Repository
public class InMemoryProductCatalog implements ProductCatalog {
    private final Map<String, Product> products = Map.of(
            "BOOK-001",
            new Product("BOOK-001", 120_000L, 10)
    );

    @Override
    public Optional<Product> findBySku(String sku) {
        return Optional.ofNullable(products.get(sku));
    }
}
~~~

File `StandardPricingPolicy.java`:

~~~java
package com.example.shop;

import org.springframework.stereotype.Component;

@Component
public class StandardPricingPolicy implements PricingPolicy {
    @Override
    public long total(long unitPrice, int quantity) {
        return Math.multiplyExact(unitPrice, quantity);
    }
}
~~~

`@Repository` and `@Component` mark components so component scan registers bean definitions. `@Repository` is a specialization of `@Component` indicating data access semantics; the annotation name does not automatically turn an in-memory Map into a database.

### 5.4. The Service Only Declares Required Dependencies

File `QuoteService.java`:

~~~java
package com.example.shop;

import org.springframework.stereotype.Service;

@Service
public class QuoteService {
    private final ProductCatalog catalog;
    private final PricingPolicy pricing;

    public QuoteService(
            ProductCatalog catalog,
            PricingPolicy pricing
    ) {
        this.catalog = catalog;
        this.pricing = pricing;
    }

    public Quote quote(String sku, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "Quantity must be greater than 0"
            );
        }

        Product product = catalog.findBySku(sku)
                .orElseThrow(() ->
                        new IllegalArgumentException(
                                "Product not found"
                        )
                );

        if (quantity > product.availableQuantity()) {
            throw new IllegalArgumentException(
                    "Insufficient stock"
            );
        }

        long total = pricing.total(
                product.unitPrice(), quantity
        );

        return new Quote(sku, quantity, total);
    }
}
~~~

File `Quote.java`:

~~~java
package com.example.shop;

public record Quote(
        String sku,
        int quantity,
        long total
) {}
~~~

The service does not call `new InMemoryProductCatalog()` or `new StandardPricingPolicy()`. It depends on **contracts** and receives implementations through its constructor. When there is only one matching bean for each interface, Spring can automatically resolve the dependencies based on parameter types.

With a single constructor, Spring does not require adding `@Autowired` on that constructor in normal cases. Using constructor injection expresses mandatory dependencies and allows keeping fields `final`.

### 5.5. The Controller Receives the Service

File `QuoteController.java`:

~~~java
package com.example.shop;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class QuoteController {
    private final QuoteService quoteService;

    public QuoteController(QuoteService quoteService) {
        this.quoteService = quoteService;
    }

    @GetMapping("/quotes")
    public Quote quote(
            @RequestParam String sku,
            @RequestParam int quantity
    ) {
        return quoteService.quote(sku, quantity);
    }
}
~~~

Once the application starts and the necessary conditions are met, you can call:

~~~http
GET http://localhost:8080/quotes?sku=BOOK-001&quantity=2
~~~

Illustrative response:

~~~json
{
  "sku": "BOOK-001",
  "quantity": 2,
  "total": 240000
}
~~~

If the quantity is greater than `10` or the SKU does not exist, the service throws `IllegalArgumentException`. The code above only illustrates IoC and the DI flow; it does not yet implement dedicated HTTP exception handling, validation, a database, or currency handling for a production application.

### 5.6. The Bean Graph Spring Needs to Build

~~~text
                    ApplicationContext
                           |
           +---------------+------------------+
           |               |                  |
           v               v                  v
  InMemoryProductCatalog  StandardPricingPolicy  QuoteController
           |               |                  |
           |               |                  v
           |               +------------> QuoteService
           |                                      ^
           +--------------------------------------+
~~~

To read the relationships accurately, you can look from the component that requires dependencies:

~~~text
QuoteController
  └── QuoteService
      ├── ProductCatalog -> InMemoryProductCatalog
      └── PricingPolicy  -> StandardPricingPolicy
~~~

The container creates or finds matching beans, supplies them to the constructors, and continues wiring remaining objects. Application classes only declare **what they need**, while implementation selection can be decided in the configuration layer.

## 6. Where Does the Container Find Bean Definitions?

Spring can learn how to create a bean from several sources; the most common in Spring Boot are:

1. **Component scanning:** finding classes annotated with `@Component` or stereotypes such as `@Service`, `@Repository`, `@Controller`.
2. **Java configuration:** `@Bean` methods in `@Configuration` classes returning objects for the container to manage.
3. **Auto-configuration:** Spring Boot registers beans/configurations when specific conditions are satisfied.
4. **Other bean registration mechanisms:** libraries and specialized configuration code can register metadata directly when needed.

### `@Component` and Specialized Annotations

~~~java
@Component
public class DefaultClockService {
    // ...
}

@Service
public class InvoiceService {
    // ...
}

@Repository
public class InvoiceRepositoryAdapter {
    // ...
}
~~~

Stereotypes are not merely decorative labels. They help the component scanner identify classes that the application wants to put under management. However, whether Spring detects a class also depends on package location, component scan scope, applied conditions, and bean instantiability.

Using `@Service` for application logic or `@Repository` for data access components makes code easier to read, but Spring does not "automatically write business logic" just because a class has the corresponding annotation.

### `@Bean` Fits Objects Provided by External Libraries

Some dependencies do not have Spring annotations or belong to source code you cannot modify. You can register them using factory methods:

~~~java
package com.example.shop;

import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TimeConfiguration {

    @Bean
    public Clock applicationClock() {
        return Clock.systemUTC();
    }
}
~~~

If a service needs the system time:

~~~java
@Service
public class ExpirationService {
    private final Clock clock;

    public ExpirationService(Clock clock) {
        this.clock = clock;
    }
}
~~~

Here, the `Clock` object is created by the `applicationClock()` method, but once registered, it is a bean managed by the container. If another service also injects `Clock`, Spring by default can supply the same singleton bean.

When a `@Bean` needs another dependency, Spring can inject it directly into the method parameters:

~~~java
@Configuration
public class ClientConfiguration {

    @Bean
    public PricingClient pricingClient(
            ClientSettings settings
    ) {
        return new PricingClient(
                settings.baseUrl(),
                settings.timeout()
        );
    }
}
~~~

`ClientSettings` and `PricingClient` in the snippet above are illustrative types that the project must define; the point is to show that **`@Bean` methods also participate in the dependency graph**.

### When to Use `@Component` vs. `@Bean`?

| Scenario | Usually Appropriate Approach | Why |
|---|---|---|
| Service class owned by the project | `@Service` + constructor injection | Clear intent, simple |
| Component handling HTTP | `@RestController` | Recognized by Spring MVC |
| Converter or adapter written by the project | `@Component` or suitable stereotype | Easy to scan and wire |
| Object from a third-party library | `@Bean` method | No need to modify library source code |
| Object requiring factory construction or detailed configuration | `@Bean` | Gives control over the creation process |
| Short-lived data type created during business processing | Regular `new` | No need to manage it as a bean |

Both mechanisms create beans; they differ in how definitions are provided. You should not use both `@Component` and `@Bean` for the same object without clear intent, as it may accidentally create multiple beans of the same type.

## 7. How Does Spring Resolve Dependencies?

The container must determine which bean corresponds to each constructor parameter. The simplest case is **a single bean matching the requested type**.

~~~text
QuoteService(ProductCatalog catalog)
                     |
                     v
       InMemoryProductCatalog bean
           implements ProductCatalog
~~~

If there is no matching bean, the application typically cannot instantiate the service and reports a missing dependency error. If there are multiple beans of the same type and the container cannot determine which to choose, the application typically reports a non-unique dependency error.

### When Multiple Implementations Share an Interface

Suppose there are two pricing policies:

~~~java
@Component
public class StandardPricingPolicy implements PricingPolicy {
    @Override
    public long total(long price, int quantity) {
        return Math.multiplyExact(price, quantity);
    }
}
~~~

~~~java
@Component
public class DiscountPricingPolicy implements PricingPolicy {
    @Override
    public long total(long price, int quantity) {
        return Math.multiplyExact(price, quantity) * 9 / 10;
    }
}
~~~

Both classes provide `PricingPolicy`. The constructor:

~~~java
public QuoteService(
        ProductCatalog catalog,
        PricingPolicy pricing
) { /* ... */ }
~~~

becomes **ambiguous** if there is no explicit selection rule. Several ways to resolve this:

- Use `@Primary` on the implementation you want prioritized by default.
- Use `@Qualifier` at the injection point to pick the bean with a matching qualifier.
- Create conditional configurations, e.g., registering only one implementation per profile.
- If business logic needs all implementations, inject a list or map of beans and provide an appropriate selection mechanism at the application layer.

Example of explicitly selecting by bean name:

~~~java
@Service
public class QuoteService {
    private final ProductCatalog catalog;
    private final PricingPolicy pricing;

    public QuoteService(
            ProductCatalog catalog,
            @Qualifier("standardPricingPolicy")
            PricingPolicy pricing
    ) {
        this.catalog = catalog;
        this.pricing = pricing;
    }
}
~~~

Here, you need to import `org.springframework.beans.factory.annotation.Qualifier`. When component scan registers `StandardPricingPolicy` with the default name `standardPricingPolicy`, the qualifier can select that bean. In real code, you can define explicit names via annotations if you want to avoid relying on inferred naming conventions.

`@Primary` is useful when there is an application-wide default choice; `@Qualifier` is useful when a consumer needs a specific choice. Selecting by name is not the only option: Spring also has qualifier, priority, and other resolution rules; in this lesson, the key principle is that **a graph with multiple candidates requires an explicit decision**.

### Optional Dependencies and Dependency Groups

A dependency can be mandatory or optional. Spring supports patterns such as `Optional<T>`, `ObjectProvider<T>`, and injecting `List<T>` or `Map<String,T>` for multiple matching beans.

~~~java
@Service
public class NotificationDispatcher {
    private final List<NotificationChannel> channels;

    public NotificationDispatcher(
            List<NotificationChannel> channels
    ) {
        this.channels = channels;
    }
}
~~~

The example assumes multiple beans implement `NotificationChannel`; the container can provide a list of those beans. When order matters, you must explicitly design the ordering using appropriate Spring mechanisms instead of relying on an accidentally observed order.

You should not make every dependency optional just so the application can start. If a component **cannot operate validly** without a dependency, mandatory constructor injection helps catch configuration errors earlier.

## 8. The IoC Container Manages More Than Calling Constructors

The Spring container is responsible for coordinating the bean lifecycle. A simplified model of the initialization process is:

~~~text
Read configuration / bean definitions
              |
              v
Determine which beans need to be created
              |
              v
Find constructor and resolve dependencies
              |
              v
Create instance and inject dependencies
              |
              v
Apply processing, initialization callbacks,
BeanPostProcessor and proxy (if any)
              |
              v
Bean is ready for use
              |
              v
      Business processing
              |
              v
Close context and clean up resources
(for beans whose destruction lifecycle is
managed by the container)
~~~

This is a high-level diagram, not a description of the exact order of every internal hook. Some beans are created eagerly, some are lazily initialized; a bean post-processor or proxy can change the final object injected as a dependency.

### Initialization and Cleanup

Example of a bean that needs to open and close a resource:

~~~java
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

@Component
public class ManagedResource {
    @PostConstruct
    public void initialize() {
        // Prepare resources after injection
    }

    @PreDestroy
    public void close() {
        // Close resources when the bean is destroyed by the container
    }
}
~~~

In Spring Boot versions using Jakarta EE, `@PostConstruct` and `@PreDestroy` reside in the `jakarta.annotation` package. In older Spring Boot versions using Java EE, the namespace may differ.

If a Spring-managed bean has an appropriate lifecycle, the container can invoke registered callbacks during initialization and context shutdown. However, cleanup is not guaranteed if the process is killed abruptly or the server loses power. Particularly for prototype beans, Spring typically does not fully manage destruction after handing the instance to the caller.

You should not use constructors or `@PostConstruct` to start indefinitely running business work. Background tasks, connections, or processes requiring a clear lifecycle should use appropriate lifecycle mechanisms with safe shutdown strategies.

## 9. Bean Scopes Change the Graph Shape at Runtime

Not every bean is created strictly once. **Scope** defines how the container manages and reuses instances.

| Scope | Common Meaning | Notes |
|---|---|---|
| `singleton` | One instance per bean definition in a Spring container | Default; does not mean a single instance across the entire JVM |
| `prototype` | Container creates a new instance each time the bean is requested via the corresponding mechanism | Post-creation cleanup management differs from singleton |
| `request` | One instance per HTTP request | Requires a web-aware ApplicationContext |
| `session` | One instance per HTTP session | Depends on web and session context |
| `application` | One instance per ServletContext | Has semantics specific to servlet web applications |
| `websocket` | One instance per WebSocket session in supported environments | Only use when an appropriate context actually exists |

### Singleton Is Default but Does Not Guarantee Thread Safety

A singleton `@Service` can concurrently serve many HTTP requests. If the bean holds mutable state for per-request processing, it is prone to race conditions:

~~~java
@Service
public class UnsafeCounterService {
    private int count = 0;

    public int next() {
        return ++count;  // Not safe when multiple threads call concurrently
    }
}
~~~

The fact that Spring creates one instance and manages dependencies **does not make the `++count` increment atomic**. For per-request data, local variables inside methods are typically used; if shared state is truly needed, synchronization or appropriate concurrency types must be designed.

### What Is Surprising About Injecting a Prototype into a Singleton?

Suppose:

~~~java
@Component
@Scope("prototype")
public class RequestToken {
    // ...
}
~~~

And:

~~~java
@Service
public class TokenService {
    private final RequestToken token;

    public TokenService(RequestToken token) {
        this.token = token;
    }
}
~~~

`TokenService` is a singleton and its constructor is normally called only when creating the singleton. Spring supplies **one prototype instance at wiring time**. That does not mean every time `TokenService` accesses the `token` field it will receive a new prototype.

If you need to obtain an instance on demand:

~~~java
@Service
public class TokenService {
    private final ObjectProvider<RequestToken> tokenProvider;

    public TokenService(
            ObjectProvider<RequestToken> tokenProvider
    ) {
        this.tokenProvider = tokenProvider;
    }

    public RequestToken newToken() {
        return tokenProvider.getObject();
    }
}
~~~

You need to import `org.springframework.beans.factory.ObjectProvider`. The provider lets you request a bean at the time the method runs. This is an important distinction between **an object injected at initialization** and **requesting an object each time it is needed**.

### Request-Scoped Beans Inside a Singleton

A singleton should not directly hold an HTTP request or request data without understanding scopes. Spring supports scoped proxies or providers to resolve shorter-lived dependencies. For example, a proxy can be injected into a singleton and delegate calls to the actual bean belonging to the current request.

That approach is useful, but it does not replace analyzing responsibilities: simple request data can often be passed as explicit method parameters, avoiding making the service implicitly depend on web context.

## 10. When the Graph Has a Circular Dependency

Suppose:

~~~text
OrderService
     |
     v
PaymentService
     |
     v
OrderService
~~~

If both beans require each other through constructors:

~~~java
@Service
public class OrderService {
    public OrderService(PaymentService paymentService) {
        // ...
    }
}

@Service
public class PaymentService {
    public PaymentService(OrderService orderService) {
        // ...
    }
}
~~~

To create `OrderService`, the container needs `PaymentService`; but to create `PaymentService`, it needs `OrderService`, which does not yet exist. This is a **circular dependency**. A constructor cycle cannot be resolved merely by changing the order of declaration lines.

Some injection styles or deferral mechanisms can prevent the error from appearing immediately, yet circular dependencies usually signal that two components lack well-defined responsibility boundaries.

Better design directions usually include:

- Determining which service coordinates the use case and which service merely provides capabilities.
- Extracting shared business logic into a separate component with its own responsibility if truly needed.
- Clarifying a unidirectional call flow between business parts.
- Using events or callbacks only when the business flow truly fits that coordination style.

For example, instead of two services calling each other:

~~~text
CheckoutCoordinator
    |             |
    v             v
OrderService   PaymentService
~~~

`CheckoutCoordinator` coordinates payment and order placement according to application rules, while the two services do not need to inject each other back. With distributed transactions, consistency must also be designed; this example only illustrates clarifying dependency direction.

You should not treat `@Lazy` or enabling a setting that allows circular references as the default fix. They can hide design flaws and make behavior harder to predict.

## 11. Conditional Beans Make the Graph Vary by Environment

The object graph does not have to be identical across all runs of the same codebase. Spring Boot uses configuration, classpath, and conditions to decide whether to create beans.

### Selection by Profile

Suppose there are two `ProductCatalog` implementations:

~~~java
@Repository
@Profile("dev")
public class InMemoryProductCatalog implements ProductCatalog {
    // ...
}

@Repository
@Profile("prod")
public class DatabaseProductCatalog implements ProductCatalog {
    // ...
}
~~~

The code illustrates two configuration choices; in a real application, you must implement all interface methods and the dependencies of the database catalog. When the `dev` profile is active, Spring can register the in-memory bean; when the `prod` profile is active, Spring can register the database bean.

If no matching profile is active, `QuoteService` may lack a `ProductCatalog` and fail at initialization. If multiple profiles are active simultaneously leading to two implementations, the container may encounter ambiguity unless there is an explicit selection rule.

Spring profiles are **conditions for registering beans/configurations**; they do not automatically create the corresponding database, network, or secrets.

### Selection by Property

A bean can be registered only if configuration permits:

~~~java
@Configuration
public class PromotionConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "shop.promotion",
            name = "enabled",
            havingValue = "true"
    )
    public PromotionEngine promotionEngine() {
        return new PromotionEngine();
    }
}
~~~

In this snippet, `PromotionEngine` is an example type that must be defined by the application. `@ConditionalOnProperty` is a Spring Boot annotation. If the property does not satisfy the condition, the bean will not be declared by this method.

If a service **mandatorily** injects `PromotionEngine` while the feature is disabled, you need to redesign the dependency: for example, using an interface with a "no promotion" implementation, an optional provider, or creating the service only when the feature is enabled. Conditional annotations do not automatically turn a mandatory dependency into an optional one.

### Auto-Configuration Is Conditional Graph Creation at Framework Scale

Spring Boot auto-configuration typically relies on conditions such as:

- A specific class or library is on the classpath: `@ConditionalOnClass`.
- A bean has not yet been defined by the application: `@ConditionalOnMissingBean`.
- A property has a matching value: `@ConditionalOnProperty`.
- The application type or web technology being used.

Because of this, when an application has a web starter, the framework can configure many suitable HTTP components without manually creating every bean. When the application provides its own matching bean, some default configurations can **step aside** for that choice.

What matters is being able to read why **a bean is present or absent** in the ApplicationContext. "Spring Boot magic" is really a rule system for registering and wiring an object graph based on metadata and conditions.

## 12. Not Every Object with Annotations Is a Bean

A common misconception is that simply adding `@Autowired` or `@Service` in code will make dependencies work everywhere.

Consider this example:

~~~java
@Service
public class ReportService {
    private final ProductCatalog catalog;

    public ReportService(ProductCatalog catalog) {
        this.catalog = catalog;
    }
}
~~~

If you manually create an instance with:

~~~java
ReportService reportService = new ReportService(null);
~~~

that object does not receive dependencies from the container just because the class has `@Service`. It is an object created by ordinary Java code, not an instance whose constructor was resolved by Spring. It will hold `null` and may fail when used.

Similarly:

~~~java
public class ImportJob {
    @Autowired
    private ReportService reportService;
}

// Somewhere else:
ImportJob job = new ImportJob();
~~~

`job` is created with `new`, and will not automatically have `reportService` injected by the container. Merely adding an annotation on a field is not enough to trigger wiring. You need Spring to manage `ImportJob` or pass `ReportService` explicitly from the outside.

**A useful rule:** an object with annotations is only a **candidate** for container management; actually becoming a bean depends on the context's registration and initialization process.

## 13. Proxy: The Object a Consumer Receives May Not Be the Raw Instance

The graph provided by Spring may contain a **proxy**: an intermediary object that forwards calls to the target object while applying additional behavior such as transactions, method security, caching, or AOP depending on configuration.

Example:

~~~java
@Service
public class OrderService {
    @Transactional
    public void placeOrder() {
        // Transactional operation
    }
}
~~~

With transaction infrastructure properly configured, Spring can pass a proxy of `OrderService` to other beans. When another bean calls the method through the proxy, an interceptor can open or join a transaction before invoking the business code.

~~~text
OrderController
      |
      v
 OrderService proxy
      |
      | transaction advice
      v
 OrderService target
      |
      v
  Repository
~~~

This explains why a direct call from one method to another **on the same instance** may bypass the proxy in the default Spring AOP model:

~~~java
@Service
public class OrderService {
    public void submit() {
        saveOrder(); // self-invocation
    }

    @Transactional
    public void saveOrder() {
        // ...
    }
}
~~~

In the default proxy mechanism, calling `saveOrder()` from the target object itself normally bypasses the `@Transactional` interceptor, even though the annotation is present. When designing transactions, boundaries should be placed on methods called through an appropriate bean/proxy, or more explicit transaction management should be used.

Not every bean has a proxy; proxy creation depends on configuration, annotations, proxy type, and corresponding conditions. For someone learning IoC, the core point is that **an injected object may be an artifact processed by the container**, not simply the raw result of `new`.

## 14. Constructor Injection, Setter Injection, and Field Injection

Spring supports multiple ways to inject dependencies, each carrying different design implications.

### Constructor Injection

~~~java
@Service
public class EmailService {
    private final MailGateway gateway;

    public EmailService(MailGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

This is generally the preferred choice for **mandatory** dependencies:

- Clearly expresses what the object needs to be validly constructed.
- Allows keeping fields `final` and avoids a state missing dependencies after construction.
- Easy to instantiate in unit tests with fakes/stubs without starting a Spring context.
- When the number of constructor parameters grows too large, it can be a signal to review the class's responsibilities.

### Setter Injection

~~~java
@Component
public class ReportFormatter {
    private LocaleProvider localeProvider;

    @Autowired
    public void setLocaleProvider(LocaleProvider localeProvider) {
        this.localeProvider = localeProvider;
    }
}
~~~

This style fits when a dependency needs to be replaceable or is optional in a specific design, though it also allows the object to exist in a state without full dependencies assigned. If using setters for mandatory dependencies, you must understand how Spring ensures injection before the bean is used.

### Field Injection

~~~java
@Service
public class LegacyOrderService {
    @Autowired
    private OrderRepository repository;
}
~~~

The syntax is concise, but it hides dependencies from the constructor, makes instantiation outside the container harder, and does not work well with `final` fields. Therefore, in new application code, constructor injection should generally be preferred.

These three approaches do not change the essence of IoC. They are merely different **dependency reception points** for the container to wire the object graph.

## 15. The IoC Container Does Not Replace Good Design

Having Spring in the middle does not mean every dependency relationship makes sense.

For example, a controller directly injecting a slew of repositories:

~~~text
CheckoutController
   ├── OrderRepository
   ├── ProductRepository
   ├── CustomerRepository
   ├── PaymentRepository
   └── InventoryRepository
~~~

The container can assemble this graph, but the controller is taking on too many responsibilities. A more maintainable structure might be:

~~~text
CheckoutController
        |
        v
CheckoutUseCase
   |         |
   v         v
OrdersApi  InventoryApi
   |         |
   v         v
repository  repository
~~~

Here, the controller knows the use case; the use case coordinates business contracts; each domain owns its data. Spring helps supply the objects, while **dependency direction** remains the developer's architectural decision.

### DI and Service Locator

A pattern that can obscure dependencies is calling the container from inside business logic:

~~~java
public class QuoteService {
    private final ApplicationContext context;

    public QuoteService(ApplicationContext context) {
        this.context = context;
    }

    public long quote(...) {
        PricingPolicy pricing =
                context.getBean(PricingPolicy.class);
        // ...
    }
}
~~~

This is a form of **service locator**: the class fetches dependencies itself when needed. It still uses the container, but what the class needs is hidden from the constructor, making testing and replacement less transparent. For stable, mandatory dependencies, directly injecting interfaces is usually better.

Accessing the container programmatically is not always wrong; infrastructure code, plugin systems, or mechanisms requiring dynamic bean selection may have valid reasons. However, it should be a deliberate choice, not the default in business code.

## 16. Diagnosing Errors When Spring Cannot Build the Graph

If the ApplicationContext cannot create all mandatory dependencies, the application typically fails at startup. Error messages and the `Caused by` chain help trace the **broken point in the graph**.

| Symptom | Meaning in the Graph | What to Check |
|---|---|---|
| `NoSuchBeanDefinitionException` | An injection point could not find a matching bean | Annotations, component scan, `@Bean`, profiles, conditionals |
| `NoUniqueBeanDefinitionException` | Multiple candidates exist for the same dependency | `@Primary`, `@Qualifier`, bean names, duplicate definitions |
| `UnsatisfiedDependencyException` | Could not satisfy dependencies of the bean being created | Read the cause to find which dependency is missing or failing |
| `BeanCreationException` | Bean initialization process failed | Constructor, factory method, configuration, callbacks, external resources |
| `BeanCurrentlyInCreationException` | May relate to a circular dependency or bean creation cycle | Graph among constructors, proxies, initialization |
| `NullPointerException` on an `@Autowired` field in a manually created object | The object may not be managed by the container | Where `new` is called and how the bean is registered |
| Works in `dev` but fails in `prod` | Graph differs by configuration | Profiles, properties, conditional dependencies, infrastructure |

### Finding the Root Cause Through the Dependency Path

Suppose a log has the following conceptual form:

~~~text
Error creating bean with name 'quoteController'
  -> Unsatisfied dependency 'quoteService'
      -> Unsatisfied dependency 'productCatalog'
          -> No qualifying bean of type 'ProductCatalog'
~~~

The most helpful message is usually at the **deepest unsatisfied dependency**, here `ProductCatalog`. Renaming the controller will not fix the fact that the container has no catalog bean.

Troubleshooting steps:

1. Identify which bean is being created and which dependency is unsatisfied.
2. Check whether an implementation or `@Bean` method registers the required type.
3. Check whether the package falls within the component scan range.
4. Check whether profiles/conditionals are excluding that bean.
5. Check whether the runtime classpath is missing necessary dependencies or auto-configurations.
6. If the error is due to multiple beans, establish an explicit selection rule instead of randomly deleting an implementation.

For example, if `ShopApplication` is in `com.example.shop.web` while `ProductCatalog` is in `com.example.shop.catalog`, default component scanning from the `web` package may miss `catalog`. Placing the startup class in an appropriate root package usually prevents this issue.

In difficult cases, Spring Boot provides an auto-configuration condition evaluation report and context inspection mechanisms. You can use startup logging or appropriate management tools to find why a configuration was applied or skipped; sensitive configuration information should not be exposed publicly through management endpoints.

## 17. Testing Is Easier When Dependencies Are Declared Explicitly

A practical benefit of DI is being able to test service rules without starting the full application.

Example of testing quote calculation logic with a fake catalog supplied by the test:

~~~java
ProductCatalog fakeCatalog = sku ->
        Optional.of(new Product(sku, 50_000L, 3));

PricingPolicy pricing = new StandardPricingPolicy();
QuoteService service = new QuoteService(fakeCatalog, pricing);

Quote quote = service.quote("TEST-BOOK", 2);

// quote.total() is expected to be 100_000
~~~

This snippet uses the interface as a seam to supply test data. No Spring ApplicationContext is needed because `QuoteService` receives dependencies through a plain Java constructor. In a real test, JUnit and corresponding assertions would be used.

When you need to verify component scanning, auto-configuration, MVC mapping, or bean wiring, that is when you use a Spring test context, such as `@SpringBootTest` or an appropriate test slice. Both kinds of tests answer different questions:

| Test Type | Goal | Is a Real Container Needed? |
|---|---|---|
| Service unit test with fakes/stubs | Business rules inside the service | Usually no |
| Web slice test | Mapping, HTTP validation, controller behavior | Yes, a limited context |
| Integration test | Interaction of beans, configuration, and infrastructure | Usually needs an appropriate context |
| Startup test | Whether the bean graph can assemble under a specific configuration | Yes |

A clean dependency graph and clear contracts help focus tests on the right responsibilities. However, DI does not automatically guarantee good tests if the service still depends on global state, uncontrolled system time, or hidden APIs.

## 18. Connecting IoC with Configuration and Dependencies in Spring Boot

A defining feature of Spring Boot is that the bean graph is built from a combination of:

~~~text
Java source code              Dependencies / classpath
   |                                  |
   | @Component, @Configuration       | Starters, libraries, drivers
   v                                  v
       Bean definitions and conditions
                    ^
                    |
            Profiles / properties
                    |
                    v
              IoC container
                    |
                    v
       Application object graph
                    |
                    v
      Controllers, services, repositories
                    |
                    v
         Runtime application behavior
~~~

For example, when adding a web starter, many HTTP-related classes become available and auto-configuration can register corresponding beans. When properties change, certain beans or configuration values can change. When the profile changes, implementations can change. The Spring container combines all of these to produce the final graph.

Therefore, when reading dependency injection errors, you should not only ask "is the annotation correct?" but also examine **the intended graph** and **the graph the context is actually able to build in this environment**.

## 19. Thought Exercise: Designing the Graph for a Booking Application

Suppose you are building a Spring Boot clinic appointment booking application with three requirements:

1. An API accepting appointment bookings from users.
2. A service checking available slots and creating appointments.
3. Sending notifications via email; in the local environment, use a mock instead of sending real emails.

An initial design:

~~~text
AppointmentController
        |
        v
   BookingService
     |       |
     v       v
SlotCatalog  NotificationGateway
     |              |
     v              +-- LocalNotificationGateway
DatabaseSlotCatalog +-- EmailNotificationGateway
~~~

Determine:

- Which classes are beans that need container management, and which objects are just data for a single request?
- Which interfaces should `BookingService` inject and what parameters should its constructor take?
- How do you ensure only one `NotificationGateway` is chosen per environment?
- If `DatabaseSlotCatalog` needs a `DataSource`, who provides that dependency?
- If the container reports two `NotificationGateway` beans, at which edge does the ambiguity occur?
- If only one request needs to hold temporary appointment data, should it be stored in a mutable field of a singleton service?
- When writing a unit test for the rule disallowing booking a full slot, how can the real catalog be replaced by a fake?

A simple approach is registering the two `NotificationGateway` implementations with explicit profiles or conditions, so `BookingService` only depends on the interface while `AppointmentController` only knows the booking creation use case. Specific appointment data consists of plain objects passed via parameters, rather than everything becoming a bean.

## 20. Principles to Keep When Using the IoC Container

1. **Let classes declare dependencies, and place assembly in the container or composition root.** Constructor injection is the clearest choice for mandatory dependencies.
2. **Depend on meaningful contracts rather than directly binding to implementations when variation is needed.** Interfaces make swapping implementations and testing easier, though you do not need to create an interface for every class just to satisfy a formal rule.
3. **Know which beans are truly managed.** A `@Component` in a package outside the scan scope or a manually created object will not automatically receive full container features.
4. **Understand scopes and shared state.** Singleton does not guarantee thread safety; prototype does not automatically create a new instance every time a singleton calls a method.
5. **Keep the graph's dependency direction clear.** Circular dependencies and services taking on too many responsibilities usually require design improvements before resorting to workarounds.
6. **Distinguish real beans from proxies.** Transactions, caching, security, and scoped proxies can affect calls routed through the container.
7. **Read startup errors as graph assembly errors.** Find the deepest missing, ambiguous, or uninstantiable dependency; check classpath, configuration, and profiles too.
8. **Do not put every object into the container.** Spring manages suitable application-level collaborators and resources; data objects created per request or per calculation can remain plain Java objects.

## Conclusion

**IoC solves the problem of who controls creating and connecting components; DI is a way to pass dependencies to a component without forcing it to create them itself.** In Spring Boot, the ApplicationContext reads bean definitions and configuration conditions, resolves dependency relationships, instantiates beans according to their scopes, applies necessary lifecycle steps, and provides the object graph used by the application.

Once you understand that graph, you understand why Spring can inject an interface, why a missing bean prevents the application from starting, why two implementations cause ambiguity, why singletons carry shared-state risks, and why creating an object with `new` outside the container differs from receiving a Spring bean. From here, the IoC container is no longer a mysterious mechanism: it is a tool for organizing the **assembly, configuration, and management of collaborating objects** so business code can focus on its real work.
