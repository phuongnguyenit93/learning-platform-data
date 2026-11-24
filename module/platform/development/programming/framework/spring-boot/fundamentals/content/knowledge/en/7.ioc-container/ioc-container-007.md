# Distinguishing Objects Created with `new` from Beans in the Context

In Java, to obtain an object, we typically use the **new** keyword:

~~~java
GreetingService service = new GreetingService();
~~~

Yet in a Spring Boot application, we also commonly see a class with **@Service**, **@Component**, or returned from a **@Bean** method, and then passed into another class's constructor without a **new** call at the usage site:

~~~java
@Service
public class GreetingService {
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

~~~java
@RestController
public class GreetingController {
    private final GreetingService greetingService;

    public GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }
}
~~~

The core question is not "whether the object was created with **new** or not." Spring itself can still use constructors, factory methods, and ultimately normal Java object creation operations. **The difference is who registers, creates, assembles, manages the lifecycle of, and supplies the object to the rest of the application.**

- **Object created with new in application code**: the call at that location directly creates the instance; your code is responsible for holding the reference, supplying dependencies, and managing associated resources.
- **Spring bean**: an object placed under the management of the **Spring IoC container** (typically accessed via **ApplicationContext**) according to a **bean definition** or a valid bean registration mechanism. Spring can supply dependencies, apply initialization steps, bean post-processors, scopes, and appropriate integrated services.

A bean is not a special Java data type. The very same **GreetingService** class can be instantiated manually or managed by the container; the difference lies in **the creation process and instance management mechanism**, not in the class name.

## 1. Plain Java Objects and Spring Beans

Consider a Java class:

~~~java
public class DiscountCalculator {
    public int applyTenPercent(int price) {
        return price - price / 10;
    }
}
~~~

Manually creating an object:

~~~java
DiscountCalculator calculator = new DiscountCalculator();
int discounted = calculator.applyTenPercent(200);
~~~

The call **new DiscountCalculator()** creates an instance via its constructor. That object is not automatically registered in the Spring ApplicationContext simply because the program runs under Spring Boot.

If we register a bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class PricingConfiguration {

    @Bean
    DiscountCalculator discountCalculator() {
        return new DiscountCalculator();
    }
}
~~~

The object returned from **discountCalculator()** is indeed a **bean**, provided this configuration is processed by Spring and the bean definition is registered in the corresponding context.

There is an important detail here: **inside @Bean, new is still used**. Therefore:

> You cannot identify a bean merely by asking whether the new keyword appears in the code. You need to ask whether the instance is registered and managed by the Spring context.

### 1.1. Comparison Table

| Aspect | Object Created Directly with `new` Outside Container | Bean Managed by Spring Context |
|---|---|---|
| Nature | Java object. | Still a Java object, sometimes exposed via a proxy. |
| Creation source | Constructor call in your code. | Bean definition, constructor, factory method, supplier, or matching registration mechanism. |
| Who manages dependencies | Code creating the object must supply or assemble them itself. | Container can resolve and inject matching dependencies. |
| Has name/definition in context | Not automatically. | Has a bean definition or registration managed by the context under the corresponding mechanism. |
| Lifecycle | Managed by your code; later reclaimed by GC when no longer referenced, if eligible. | Spring provides initialization/destruction steps and manages lifecycle per scope. |
| Scope | Depends on how you hold and reuse the reference. | Can be singleton, prototype, request, session... per context. |
| AOP/transactions/cache | Does not automatically receive Spring proxy mechanisms. | Can be applied when eligible and calls pass through the appropriate Spring mechanism. |
| Configuration from Environment | Does not automatically bind/inject merely because the class has annotations. | Can receive `@Value`, `@ConfigurationProperties`, or config dependencies when properly enabled. |
| Suitable places | DTOs, value objects, entities, temporary objects, standalone unit tests, small algorithms. | Services, repositories, controllers, configurations, collaborators needing Spring DI or lifecycle. |

**Not every bean receives every capability in the table.** For instance, transactions only work if appropriate transaction infrastructure is set up and calls meet conditions; a plain singleton bean does not automatically have transactions.

## 2. How Does the Spring IoC Container Manage Beans?

**Inversion of Control (IoC)** means part of the control over creating and connecting components is shifted from business code to the container. **Dependency Injection (DI)** is an important mechanism for achieving this: an object receives required dependencies instead of creating them itself.

Model:

~~~text
Without container:

OrderService
  └── calls new PaymentGateway itself
          └── calls new HttpClient itself

With Spring IoC container:

ApplicationContext
  ├── defines / creates PaymentGateway bean
  ├── defines / creates OrderService bean
  └── provides PaymentGateway to OrderService
              │
              ▼
        OrderService uses the dependency
        provided via its constructor
~~~

During configuration processing, Spring learns which **bean definitions** are registered. A bean definition can describe the class, scope, bean creation strategy, dependencies, and related metadata. From that information, the container creates and assembles instances at appropriate times.

A conceptual diagram:

~~~text
@Component / @Service / @Bean / configuration imports
                      │
                      ▼
              Bean definitions
                      │
                      ▼
             ApplicationContext
                      │
             ┌────────┴────────┐
             │                 │
       Create instance   Resolve dependencies
             │                 │
             └────────┬────────┘
                      │
             Initialization and
             bean post-processors
                      │
                      ▼
               Bean is ready
                      │
                      ▼
        Injection / lookup / usage
                      │
                      ▼
        End of lifecycle per scope
~~~

This is a simplified diagram. Spring has many more phases and extension points, such as processing `BeanFactoryPostProcessor`, `BeanPostProcessor`, and proxy creation steps. Not every bean is created immediately when the application context starts; actual timing depends on scope and settings such as lazy initialization.

### 2.1. What Is ApplicationContext?

**ApplicationContext** is a Spring interface serving as the access point to the IoC container and application-supporting services. It extends the capabilities of `BeanFactory`, adding features such as event publishing, resource support, internationalization, and context integrations.

For example, you can retrieve a bean:

~~~java
import org.springframework.context.ApplicationContext;

public class Example {
    public void run(ApplicationContext context) {
        DiscountCalculator calculator =
                context.getBean(DiscountCalculator.class);
        System.out.println(calculator.applyTenPercent(200));
    }
}
~~~

The **getBean** method asks the container to provide a matching bean. It differs from **new DiscountCalculator()** because creating and selecting the instance is orchestrated by Spring.

However, in most business code, **constructor injection** is usually preferred over scattering **getBean** calls. Code needing a dependency should declare it clearly on the constructor; the container will assemble it when creating the bean.

### 2.2. Bean Definition Differs from Bean Instance

Distinguish:

- **Bean definition**: describes how Spring supplies a bean, including configuration metadata, scope, and factory method.
- **Bean instance**: the concrete object created or returned according to the definition.
- **Bean name**: the identifier of a bean within a container.

With the default singleton scope, one bean definition normally corresponds to one instance reused across the context after the bean initializes. With prototype scope, the same definition can produce **multiple instances** when requests to retrieve the bean occur.

Therefore, **having a bean definition** does not mean an object already exists at the moment you observe it. Spring may defer initialization, or create new objects per scope when requested.

## 3. Two Ways of Creating the Same Class: A Manual Object and a Spring Bean

Suppose there is a simple service:

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

Suppose the application has:

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

By standard component scanning conventions, **GreetingService** resides in the application class's package and is scanned by Spring to be registered as a bean.

In other application code, you can still write:

~~~java
GreetingService manual = new GreetingService();
~~~

Inside the context, Spring may hold:

~~~java
GreetingService managed = context.getBean(GreetingService.class);
~~~

These two variables refer to **two different objects** in this common scenario:

~~~text
manual = new GreetingService()
          │
          ▼
      Instance A
      Not automatically managed by Spring

context.getBean(GreetingService.class)
          │
          ▼
      Instance B (bean managed by the context)
~~~

Example with a normal non-proxied singleton bean:

~~~java
GreetingService fromContext1 = context.getBean(GreetingService.class);
GreetingService fromContext2 = context.getBean(GreetingService.class);

System.out.println(fromContext1 == fromContext2); // usually true
System.out.println(manual == fromContext1);       // false
~~~

With an ordinary singleton bean, two lookups return the same instance managed by the context. However, if the bean is wrapped by a Spring AOP proxy, the exposed object can be a **proxy**. If the scope is prototype, two lookups can return two distinct instances.

Do not reason solely by comparing Java class names: **same class does not mean same instance, same bean name, or same lifecycle**.

### 3.1. The `@Service` Annotation Does Not Turn Every Instance into a Bean

This is a common misconception:

~~~java
@Service
public class GreetingService {
    // ...
}
~~~

The **@Service** annotation tells Spring this class is a specialized component **when the component discovery/registration mechanism processes that class**. It does not change the meaning of the **new** keyword in Java.

~~~java
GreetingService service = new GreetingService();
~~~

The newly created object **is not registered as a bean just because the class has @Service**. It does not automatically join the lifecycle, autowiring, or proxy mechanisms of a bean living in the Spring context.

Conversely, a class **without @Service** can still become a bean if registered using **@Bean** or another mechanism.

### 3.2. Having `@SpringBootApplication` Does Not Mean Every Class Is Scanned

By default, **@SpringBootApplication** enables component scanning starting from the package containing the main class and its subpackages. For example:

~~~text
com.example.demo
├── DemoApplication        @SpringBootApplication
├── web
│   └── GreetingController @RestController
└── service
    └── GreetingService    @Service
~~~

In this structure, **GreetingController** and **GreetingService** are scanned under standard conventions.

If a component lives in a package outside the scan scope, Spring will not automatically know about it just from its annotation. In that case, you need proper package placement, configuration imports, or deliberate scan adjustments.

This differs from **new**: a Java constructor does not require component scanning. Yet creating an object with `new` also does not make the object a bean.

## 4. Dependency Injection: The Most Visible Impact

A service class often depends on a repository or client:

~~~java
package com.example.orders;

import org.springframework.stereotype.Repository;

@Repository
public class OrderRepository {
    public String findDescription(long orderId) {
        return "Order #" + orderId;
    }
}
~~~

~~~java
package com.example.orders;

import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public String describe(long orderId) {
        return repository.findDescription(orderId);
    }
}
~~~

When **OrderRepository** and **OrderService** are both registered as beans, the container can select the matching repository bean and pass it to the service constructor.

If code constructs the service itself:

~~~java
OrderService service = new OrderService(new OrderRepository());
~~~

this snippet **still works** for simple logic because you actively created and provided every dependency. However, both the service and repository here are manually created instances; they do not automatically carry lifecycle services, proxies, or Spring-context wiring.

This is an important distinction:

> DI is not magic that eliminates constructors in Java. DI is a way to shift **the responsibility of assembling the object graph** to a dedicated component, which in Spring is the IoC container.

### 4.1. Constructor Injection Is Easiest to Observe

With a constructor:

~~~java
public OrderService(OrderRepository repository) {
    this.repository = repository;
}
~~~

The dependency is **mandatory** as soon as the object is created. If you call `new` yourself, Java requires you to supply the argument; if Spring creates the bean, Spring must locate a matching dependency. This makes dependency relationships clear when reading code and convenient during unit tests.

### 4.2. Field Injection Easily Causes Confusion When Using `new`

Example:

~~~java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

@Service
public class LegacyOrderService {

    @Autowired
    private OrderRepository repository;

    public String describe(long orderId) {
        return repository.findDescription(orderId);
    }
}
~~~

If Spring creates the bean and appropriate autowiring mechanisms operate, the **repository** field can be injected.

However:

~~~java
LegacyOrderService manual = new LegacyOrderService();
manual.describe(42L);
~~~

the manual object does not pass through Spring autowiring. The **repository** field keeps its default value **null**, and the call can throw **NullPointerException**.

**@Autowired is not a statement automatically executed by the JVM every time an object is created with new.** It is metadata processed by Spring for objects managed by the container or objects explicitly requested to be autowired via specialized APIs.

For new code, constructor injection usually helps prevent situations where an object exists without critical dependencies.

### 4.3. What If Multiple Beans Have the Same Type?

Suppose Spring has two beans implementing the **PaymentGateway** interface:

~~~java
public interface PaymentGateway {
    void pay(long orderId);
}
~~~

If a constructor requests a **PaymentGateway** yet the context has multiple candidates and no suitable selection rule, injection can fail with **NoUniqueBeanDefinitionException** or a related exception.

You can use **@Qualifier**, **@Primary**, or design clearer injection:

~~~java
public CheckoutService(
        @org.springframework.beans.factory.annotation.Qualifier("stripeGateway")
        PaymentGateway gateway) {
    this.gateway = gateway;
}
~~~

When calling `new` yourself, you choose the implementation directly:

~~~java
CheckoutService checkout = new CheckoutService(new LocalPaymentGateway());
~~~

Choosing directly is not wrong, yet you are deciding the dependency at **the object creation site** rather than letting Spring determine it from the container.

## 5. `@Bean` Can Return an Object Created with `new`

This is the strongest counterexample to the notion that "`new` is the opposite of a bean."

~~~java
package com.example.demo.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class PricingConfiguration {

    @Bean
    PricePolicy pricePolicy() {
        return new PricePolicy(0.10);
    }
}
~~~

~~~java
package com.example.demo.config;

public class PricePolicy {
    private final double discountRate;

    public PricePolicy(double discountRate) {
        this.discountRate = discountRate;
    }

    public double apply(double price) {
        return price * (1 - discountRate);
    }
}
~~~

**PricePolicy** has no **@Component**, **@Service**, or **@Repository**. Even so, the object returned by the **@Bean** method can still be registered and managed as a bean.

Diagram:

~~~text
Spring ApplicationContext
      │
      ├── processes PricingConfiguration
      │
      ├── finds @Bean PricePolicy pricePolicy()
      │
      ├── invokes factory method:
      │       return new PricePolicy(0.10)
      │
      └── manages the returned object
              as a PricePolicy bean
~~~

Hence the right question is **where the new call is executed and whether the result is placed under Spring's bean management**.

### 5.1. When to Use `@Bean`?

**@Bean** is typically appropriate when:

- You want to register a third-party class whose source cannot be annotated with Spring annotations.
- You need to pass constructor arguments determined by configuration.
- You want a factory method to clearly express how the instance is created.
- You want to select implementations or configure integrated objects based on dependencies.

Example:

~~~java
@Configuration
public class ClientConfiguration {

    @Bean
    ApiClient apiClient(ApiClientProperties properties) {
        return new ApiClient(properties.getBaseUrl());
    }
}
~~~

Assume **ApiClient** is a library class and **ApiClientProperties** has been registered by Spring as a configuration bean. Spring can inject properties into the factory method, then manage the returned `ApiClient` according to the bean definition.

### 5.2. Can You Create an Object and Register It Directly?

Spring provides low-level APIs to register already-created singletons or register bean definitions/suppliers into an appropriate `BeanFactory`/registry. Those are advanced cases, such as framework integration or dynamic programmatic configuration.

However, calling **new** and storing the result in a local variable, field, or collection **is not** bean registration. There must be an explicit registration step or creation through a bean definition.

APIs registering pre-existing instances can differ in how full lifecycle and bean post-processing apply compared to the standard bean creation path. Therefore, for common applications, **@Component** or **@Bean** is an easier-to-understand and easier-to-control starting point.

## 6. Who Manages an Object's Lifecycle?

For a manually created object:

~~~java
ReportClient client = new ReportClient();
client.connect();
client.sendReport();
client.close();
~~~

Your code must know when to initialize, use, and close resources. If you forget to close a client holding sockets or thread pools, resource leaks can happen. **The garbage collector does not replace the obligation to close off-heap resources**.

With a Spring bean, the container can process lifecycle callbacks and extension points. Example:

~~~java
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

@Component
public class CacheWarmup {

    @PostConstruct
    public void initialize() {
        System.out.println("Initializing bean resources");
    }

    @PreDestroy
    public void shutdown() {
        System.out.println("Releasing bean resources");
    }
}
~~~

For singleton beans created and managed by Spring, the corresponding callbacks can be processed when the bean initializes and when the `ApplicationContext` closes normally.

If you instantiate manually:

~~~java
CacheWarmup manual = new CacheWarmup();
~~~

Spring does not automatically call **initialize()** for that object, and does not automatically call **shutdown()** when the context closes. Lifecycle annotations are meaningful only when applied by an appropriate processing mechanism.

### 6.1. Common Lifecycle Steps

A conceptual model for a singleton bean:

~~~text
Read BeanDefinition / resolve dependencies
                     │
                     ▼
               Create object
                     │
                     ▼
             Dependency injection
                     │
                     ▼
         Pre-init BeanPostProcessors
                     │
                     ▼
      @PostConstruct / initializing callbacks
                     │
                     ▼
          Post-init BeanPostProcessors
                     │
                     ▼
           Bean is ready for use
                     │
                     ▼
            Context closes normally
                     │
                     ▼
         @PreDestroy / destroy callbacks
~~~

The full sequence in Spring contains more details and can vary by bean creation strategy, scope, proxy, or extension points. The diagram merely shows that the container does **more than calling a constructor**.

### 6.2. Constructors Still Run When Spring Creates Beans

An ordinary bean still needs an actual Java instance. When the container creates it via a constructor, that constructor **is still called**, just as when you call `new`. Spring does not bypass Java's object initialization process.

The difference is that Spring can:

1. Select the constructor and resolve dependencies.
2. Create the instance or invoke the factory method.
3. Apply injection, callbacks, and post-processing steps.
4. Manage scope and return the appropriate object/proxy to consumers.

Thus the phrase "a bean is created by Spring so it doesn't use `new`" is an oversimplified statement that easily misleads.

### 6.3. Not Every Scope Is Destroyed by the Container Like a Singleton

Spring manages lifecycles differently depending on scope. For **singleton**, Spring typically manages destruction callbacks when the context closes. For **prototype**, the container creates and initializes the object on request, yet **does not automatically track every prototype instance to invoke full destruction callbacks on context close**. Consumers using prototypes must handle cleanup themselves when needed.

With **request** or **session** scopes in an appropriate web environment, lifecycles are tied to requests or sessions. Accessing a bean in an environment that does not support its scope can fail.

## 7. Singleton Beans Differ from Hand-Rolled Singleton Objects

A Java class can implement a singleton itself using a static field:

~~~java
public final class ManualRegistry {
    private static final ManualRegistry INSTANCE = new ManualRegistry();

    private ManualRegistry() {
    }

    public static ManualRegistry getInstance() {
        return INSTANCE;
    }
}
~~~

This is a design pattern controlled by the Java class, independent of Spring.

By contrast:

~~~java
@Service
public class OrderService {
    // ...
}
~~~

if registered by Spring under the default singleton scope, the container typically creates and reuses **one instance per bean definition within one ApplicationContext**.

Two different concepts:

| Criterion | Hand-Rolled Java Singleton | Spring Singleton Scope |
|---|---|---|
| Who decides the instance? | The application's class/static field/factory. | The Spring container and bean definition. |
| Typical scope | Per class loader / JVM static mechanics. | Within one Spring container for that bean definition. |
| Initialization | Decided by static/factory code. | Follows bean lifecycle and creation timing. |
| Dependency injection | Must be designed or wired manually. | Can be resolved/injected by Spring. |
| Spring lifecycle callbacks | Not automatic. | Can be processed according to bean mechanics. |

An application can have **multiple ApplicationContexts**, or multiple bean definitions for the same class. In such cases, "Spring singleton" does not mean a single object across the entire JVM.

### 7.1. Are Singleton Beans Automatically Thread-Safe?

**No.** Singleton scope only dictates instance sharing; it does not automatically ensure data synchronization.

Example of why request state should not be placed in a shared field:

~~~java
@Service
public class UnsafeCounterService {
    private int counter;

    public int next() {
        return ++counter;
    }
}
~~~

Multiple requests can invoke **next()** concurrently. The **++counter** increment is not an atomic thread-safe operation, risking incorrect results.

If you need a shared counter within a single process, you can use an appropriate construct such as **AtomicInteger**:

~~~java
@Service
public class CounterService {
    private final java.util.concurrent.atomic.AtomicInteger counter =
            new java.util.concurrent.atomic.AtomicInteger();

    public int next() {
        return counter.incrementAndGet();
    }
}
~~~

This resolves atomicity of a simple counter within a single JVM; it does not replace a distributed counter when an application runs multiple instances.

## 8. Scope: Spring Can Create One or Many Instances

Beans can exist under different scopes:

| Scope | Common Meaning |
|---|---|
| **singleton** | One instance per bean definition in one container; common default. |
| **prototype** | Creates a new instance when the container receives a request for that bean. |
| **request** | Instance bound to an HTTP request in a web-aware context. |
| **session** | Instance bound to an HTTP session in a web-aware context. |
| **application** | Scope bound to `ServletContext` in a matching environment. |
| **websocket** | Scope bound to a WebSocket session when a supporting environment exists. |

Prototype example:

~~~java
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.Scope;
import org.springframework.stereotype.Component;

@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class ReportDraft {
    private final java.util.UUID id = java.util.UUID.randomUUID();

    public java.util.UUID getId() {
        return id;
    }
}
~~~

When calling:

~~~java
ReportDraft first = context.getBean(ReportDraft.class);
ReportDraft second = context.getBean(ReportDraft.class);

System.out.println(first == second); // false for typical prototypes
~~~

Thus **being a bean does not mean singleton**. Spring manages bean provisioning according to scope, whereas objects created with `new` follow only the logic you wrote.

### 8.1. Does a Prototype Injected into a Singleton Create a New Object on Every Call?

Suppose:

~~~java
@Service
public class ReportService {
    private final ReportDraft draft;

    public ReportService(ReportDraft draft) {
        this.draft = draft;
    }
}
~~~

If **ReportService** is a singleton and **ReportDraft** is a prototype, Spring normally resolves one prototype instance **at the time the ReportService singleton is created**. The `draft` field continues referencing that same instance for the lifetime of the service. It **does not automatically create a new ReportDraft for every method call**.

When you want a fresh prototype on demand, you can inject **ObjectProvider**:

~~~java
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    private final ObjectProvider<ReportDraft> draftProvider;

    public ReportService(ObjectProvider<ReportDraft> draftProvider) {
        this.draftProvider = draftProvider;
    }

    public ReportDraft createDraft() {
        return draftProvider.getObject();
    }
}
~~~

Each time **getObject()** is called under typical prototype settings, Spring supplies a new instance. This is a clear difference between **requesting a bean through the container** and **retaining an injected reference**.

### 8.2. Request-Scoped Beans and Scoped Proxies

A bean bound to an HTTP request may need to be used from a singleton service. You cannot simply hold a fixed request-scoped object for the entire life of the singleton. Spring supports scoped proxies or providers to route calls to the instance belonging to the current request.

Declaration example:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.RequestScope;

@Component
@RequestScope
public class RequestMetadata {
    // Data bound to the current request.
}
~~~

**@RequestScope** by default uses an appropriate proxy mechanism so injecting into longer-lived beans can work. However, the actual instance still requires an **active request context**. Calling a request-scoped bean from a background thread outside a request may fail if no matching context exists.

Do not use a request-scoped bean as a static Java singleton or retain instances manually across multiple requests.

## 9. Proxy: What You Inject May Differ from the Underlying Instance

An important benefit of Spring beans is that the container can apply **BeanPostProcessors** and **AOP proxy** mechanisms when appropriate infrastructure is enabled.

Example of a Spring-managed service:

~~~java
@Service
public class OrderService {

    @Transactional
    public void placeOrder() {
        // Business logic involving the database.
    }
}
~~~

If Spring transaction management is properly configured, a call to the bean provided by Spring can pass through a proxy to open/coordinate a transaction around the method.

~~~text
Controller
    │ calls bean injected by Spring
    ▼
OrderService proxy
    │
    ├── Transaction interceptor
    │      ├── start / join transaction
    │      ├── invoke real logic
    │      └── commit / rollback per rules
    │
    ▼
OrderService target instance
~~~

However:

~~~java
OrderService manual = new OrderService();
manual.placeOrder();
~~~

this object is not automatically wrapped in a Spring transaction proxy. The **@Transactional** annotation is not understood natively by the JVM as a command to open a database transaction. It is metadata for appropriate Spring infrastructure to process calls under supported conditions.

**Note:** transactions cannot operate merely by annotating a method. The application must have a **PlatformTransactionManager** or matching transaction infrastructure and a proper call path. The minimal example above only illustrates the difference in object management, without claiming transactions work automatically before a datasource/transaction manager is configured.

### 9.1. Transaction Proxies Do Not Trigger on Every Call

In standard proxy mode, the call must pass through the proxy:

~~~text
Bean A → OrderService proxy → @Transactional method
~~~

If the target calls another method on itself:

~~~java
@Service
public class OrderService {
    public void placeAndNotify() {
        placeOrder();
    }

    @Transactional
    public void placeOrder() {
        // ...
    }
}
~~~

Calling **placeOrder()** from **placeAndNotify()** is **self-invocation** on the current object; in standard proxy-based Spring AOP, it does not pass through the proxy to start separate transaction advice for **placeOrder()**. If **placeAndNotify()** is already running inside a transaction opened elsewhere, the logic can remain within the existing transaction; what does not occur here is applying fresh advice via self-invocation.

This proves that **having a bean** is a necessary condition to leverage many Spring features, yet not sufficient to guarantee every call path passes through AOP.

### 9.2. Other Features That Can Rely on Proxies

Depending on configuration and technology:

- **@Transactional** can use an interceptor to manage transaction boundaries.
- **@Cacheable** can use a cache interceptor when Spring caching is enabled.
- **@Async** can use a proxy to dispatch calls to an executor when asynchronous method execution is enabled.
- Custom aspects can insert cross-cutting logic around method calls.

All have their own infrastructure and invocation-path requirements. **Objects created with new outside the container do not automatically receive these proxies and interceptors.**

### 9.3. Comparing References of Proxied Beans

With Spring AOP, **context.getBean(OrderService.class)** may return a proxy, depending on how Spring selects proxy types and type compatibility. The real target can differ from the proxy instance.

Do not treat printing **getClass()**, using **==**, or checking an annotation on a runtime proxy as absolute proof that an object is not a bean. You must understand bean definitions, scopes, and the active proxy mechanism.

## 10. End-to-End Example in Spring Boot: Controller, Service, and Repository

Let us build an API to read product information, focusing on **who creates objects and who provides dependencies**.

### 10.1. Repository

~~~java
package com.example.store.repository;

import org.springframework.stereotype.Repository;

@Repository
public class ProductRepository {
    public String findName(long id) {
        if (id == 1L) {
            return "Fountain pen";
        }
        return "Product #" + id;
    }
}
~~~

This example uses a plain Java repository to illustrate IoC without connecting to a database yet. The **@Repository** annotation lets the class be discovered as a component when scanned. It also carries specialized data-access semantics and can participate in persistence exception translation when corresponding infrastructure is configured.

### 10.2. Service with Constructor Injection

~~~java
package com.example.store.service;

import com.example.store.repository.ProductRepository;
import org.springframework.stereotype.Service;

@Service
public class ProductService {
    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public String describe(long productId) {
        return "Product name: " + repository.findName(productId);
    }
}
~~~

The service does not call **new ProductRepository()**. It declares its need via constructor and lets whoever constructs the service provide the dependency.

### 10.3. Controller Using the Service

~~~java
package com.example.store.web;

import com.example.store.service.ProductService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProductController {
    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    @GetMapping("/products/{id}/description")
    public String description(@PathVariable long id) {
        return productService.describe(id);
    }
}
~~~

In a Spring MVC application with full web infrastructure, **@RestController** registers a web component, while **@GetMapping** declares the mapping for the request-handling method.

### 10.4. Entry Point

~~~java
package com.example.store;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StoreApplication {
    public static void main(String[] args) {
        SpringApplication.run(StoreApplication.class, args);
    }
}
~~~

If the project has the appropriate **spring-boot-starter-web** dependency and the classes sit inside subpackages of **com.example.store**, standard component scanning discovers the repository, service, and controller.

Spring assembles them:

~~~text
                  ApplicationContext
                         │
             ┌───────────┴───────────┐
             │                       │
     ProductRepository          ProductService
          bean                       bean
             │                       │
             └─────inject───────────►│
                                     │
                               ProductController
                                     bean
                                      ▲
                       inject service │
                                      │
                            HTTP GET /products/1/description
~~~

In the diagram, the arrows indicate dependency provisioning; label placement is not a strict Spring timeline.

Illustrative request:

~~~http
GET /products/1/description HTTP/1.1
Host: localhost:8080
~~~

Response body:

~~~text
Product name: Fountain pen
~~~

This is the expected result if the application starts properly on port 8080, without other path/security configurations intervening, and Spring MVC components operate normally.

### 10.5. What Happens If the Controller Calls `new` on the Service Itself?

Replacing constructor injection with:

~~~java
@RestController
public class ProductController {
    private final ProductService productService =
            new ProductService(new ProductRepository());

    // Handlers using productService...
}
~~~

This code can still work for the simple example because you supplied sufficient constructor arguments. However:

- **ProductController** is a bean if scanned by Spring; the **ProductService** in this field is not necessarily a context bean.
- The newly created **ProductRepository** is also not the repository bean managed by the context.
- Configuration changes, mocks, wrappers, and proxies on the real context beans may not affect these two manual objects.
- The controller takes on choosing and assembling dependencies itself, coupling directly to implementations.

Suppose later the service is designed with **@Transactional** and the repository becomes a real database-access bean; manually instantiating the service/repository with `new` does not guarantee transactions, exception translation, dependency injection, or Spring-managed `DataSource` configuration will work.

**The difference is not whether the current describe() method returns the same string, but the management and extensibility contract of the objects being used.**

## 11. Beans Receiving Configuration Differ from Manually `new`ed Objects

Spring Boot frequently uses **externalized configuration** to pass values from config files, environment variables, and matching property sources into the application.

Example component:

~~~java
package com.example.store;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class ReceiptFormatter {
    private final String prefix;

    public ReceiptFormatter(
            @Value("${store.receipt-prefix:Receipt}") String prefix) {
        this.prefix = prefix;
    }

    public String format(long orderId) {
        return prefix + " #" + orderId;
    }
}
~~~

With configuration:

~~~yaml
store:
  receipt-prefix: "Invoice"
~~~

if the class is scanned by Spring and Spring processes **@Value** properly, the container can pass **"Invoice"** to the constructor.

Yet calling directly:

~~~java
ReceiptFormatter formatter = new ReceiptFormatter("Manual receipt");
~~~

means you decide the passed string yourself. Java does not read **application.yml** automatically just because a constructor parameter is annotated with **@Value**. If the constructor takes a String argument, you still have to pass an argument when using `new`.

With field injection:

~~~java
@Component
public class LegacyFormatter {
    @Value("${store.receipt-prefix:Receipt}")
    private String prefix;

    public String format(long id) {
        return prefix + " #" + id;
    }
}
~~~

Calling **new LegacyFormatter()** will not trigger Spring property injection. The **prefix** field may remain **null**, producing incorrect output or exceptions depending on usage.

### 11.1. Configuration Properties Are Bound for Beans

Spring Boot also supports **@ConfigurationProperties** objects to bind a group of properties into structured configuration. This binding needs to be activated through appropriate mechanisms such as **@EnableConfigurationProperties** or **@ConfigurationPropertiesScan**, or through a bean registered for supported binding mechanisms.

Merely declaring:

~~~java
@org.springframework.boot.context.properties.ConfigurationProperties(
        prefix = "store")
public class StoreProperties {
    private String receiptPrefix;

    public String getReceiptPrefix() {
        return receiptPrefix;
    }

    public void setReceiptPrefix(String receiptPrefix) {
        this.receiptPrefix = receiptPrefix;
    }
}
~~~

and running:

~~~java
StoreProperties properties = new StoreProperties();
~~~

will not make Spring Boot populate values into that manual instance. Property binding is a configuration process requiring an execution mechanism, not a behavior of the `new` keyword.

## 12. When Should You Use `new`? Not Every Object Needs to Become a Bean

A mistake in the opposite direction is trying to turn **every object** in the application into a bean. Spring IoC is not meant to manage every string, DTO, record, entity, or collection element.

### 12.1. Value Objects and DTOs

Example:

~~~java
public record Money(long amount, String currency) {
}
~~~

~~~java
Money price = new Money(120_000L, "VND");
~~~

**Money** is a business value. Usually there is no need to register each `Money` instance as a bean. Each monetary value can be created on demand and passed through methods as an ordinary Java object.

Similarly:

~~~java
public record CreateOrderRequest(long productId, int quantity) {
}
~~~

**CreateOrderRequest** is a DTO describing request data. Spring MVC can use conversion/binding mechanisms to construct the DTO from a request, yet **that DTO is not automatically a singleton bean managed in the ApplicationContext**.

Do not store per-request state in fields of a singleton bean just because you "want to use Spring for everything."

### 12.2. JPA Entities

An entity such as:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;

@Entity
public class Order {
    @Id
    @GeneratedValue
    private Long id;

    private String description;

    protected Order() {
    }

    public Order(String description) {
        this.description = description;
    }
}
~~~

is typically a persistence-model object with a lifecycle tied to **JPA EntityManager / persistence context**. It does not automatically become a Spring bean just because it carries **@Entity**.

In business code, you can create:

~~~java
Order order = new Order("Buy pens");
~~~

and ask a repository/entity manager to persist it per JPA mechanics. Managing **JPA entity lifecycle** and managing **Spring bean lifecycle** are two distinct concepts.

### 12.3. Temporary Objects or Small Algorithms

An object used only for local computation without needing DI/lifecycle can be created directly:

~~~java
StringBuilder builder = new StringBuilder();
builder.append("ORDER-").append(123L);
String code = builder.toString();
~~~

There is no benefit in turning every `StringBuilder` into a bean. The same applies to most data structures and objects created for short-lived requests.

### 12.4. Services/Repositories/Controllers and Shared Collaborators

Components that have dependencies, configuration, transactions, lifecycles, or need reuse across multiple consumers are usually well suited for Spring management:

- Business services such as **OrderService**, **PaymentService**.
- Repositories or data-access adapters.
- Shared configured HTTP clients, serializers, or connection-pool wrappers.
- Controllers, filters, or framework integration components.
- Services holding environment configuration and injected dependencies.

However, a short-lived object **may need a factory** rather than a singleton bean if each usage requires separate state. In that case, Spring can manage the **factory** without necessarily managing every result the factory produces.

### 12.5. Selection Table for Creation Strategy

| Scenario | Usually Suitable Approach | Why |
|---|---|---|
| Create a DTO from a request | Constructor, record, mapper, or data binding | Request-specific data, no singleton bean needed. |
| Create a new JPA entity | Constructor/factory/domain method, then persist | Entity belongs to persistence lifecycle. |
| Service with repositories and transactions | Spring bean + constructor injection | Container manages dependencies, proxies, and appropriate lifecycle. |
| Shared third-party library client | **@Bean** returning configured instance | May use `new` inside the factory method while still being managed. |
| Temporary value for computation | **new** or plain Java factory | Lightweight, no container needed. |
| Object with per-operation state | **new**, factory, prototype, or matching scope | Prevents unintended shared state. |
| Unit testing pure logic | **new** combined with mock/fake dependencies | Fast tests, no need to boot Spring. |
| Testing wiring/auto-configuration | Spring test context | Needed to actually verify container configuration. |

## 13. Unit Tests and Integration Tests: Why `new` Remains Very Useful

When using constructor injection, business logic can be tested **without starting a Spring context**.

Example service:

~~~java
public class TaxService {
    private final TaxRateProvider rateProvider;

    public TaxService(TaxRateProvider rateProvider) {
        this.rateProvider = rateProvider;
    }

    public long calculate(long amount) {
        return Math.round(amount * rateProvider.currentRate());
    }
}
~~~

Interface:

~~~java
public interface TaxRateProvider {
    double currentRate();
}
~~~

Standalone unit test:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class TaxServiceTest {

    @Test
    void calculatesTaxUsingProvidedRate() {
        TaxRateProvider fakeRateProvider = () -> 0.10;
        TaxService service = new TaxService(fakeRateProvider);

        assertEquals(10L, service.calculate(100L));
    }
}
~~~

This is an example where **new is a great choice**. The service is designed to receive its dependency via constructor, so the test does not need to build an entire `ApplicationContext`.

Conversely, if you want to verify that **@Transactional**, autowiring, component scanning, bean scopes, or auto-configuration actually work, a test that only calls `new` on objects will not prove those features. You need a test with a Spring context and corresponding infrastructure.

### 13.1. Two Test Levels Have Different Goals

| Goal | Unit Test with `new` | Test with Spring Context |
|---|---|---|
| Calculation logic or business conditions | Suitable. | Can work, though usually heavier than needed. |
| Constructor accepts dependency per contract | Suitable. | Also checked during wiring. |
| Does component scanning register the bean? | Not proven automatically. | Suitable. |
| Does property binding work? | Not proven automatically. | Suitable. |
| Is the AOP transaction interceptor applied? | Not proven automatically. | Requires context and transaction infrastructure. |
| Does HTTP mapping work in MVC? | Not proven automatically. | Requires appropriate web testing tools. |

Do not turn every unit test into an integration test just because the production class is **@Service**. Yet also do not assume a unit test instantiating objects with `new` proves all Spring behavior.

## 14. Common Mistakes When Mixing `new` with Spring Beans

### 14.1. `NullPointerException` on an `@Autowired` Field

Code:

~~~java
@Service
public class InvoiceService {
    @Autowired
    private InvoiceRepository repository;

    public void createInvoice() {
        repository.save();
    }
}
~~~

Call site:

~~~java
new InvoiceService().createInvoice();
~~~

May throw **NullPointerException** because **repository** was not injected. The cause is not that the annotation broke; this object was never processed by Spring.

The usual fix is **constructor injection** and letting consumers receive the `InvoiceService` bean if container features are needed:

~~~java
@Service
public class InvoiceService {
    private final InvoiceRepository repository;

    public InvoiceService(InvoiceRepository repository) {
        this.repository = repository;
    }
}
~~~

If `InvoiceService` is used as a plain Java class in unit tests, you can pass a fake repository directly to the constructor.

### 14.2. `@PostConstruct` Is Not Called

Suppose:

~~~java
@Component
public class TemplateRegistry {
    private java.util.Map<String, String> templates;

    @PostConstruct
    void initialize() {
        templates = java.util.Map.of("default", "Hello");
    }
}
~~~

Manually creating with **new TemplateRegistry()** does not trigger the **@PostConstruct** callback. If code uses the **templates** field right away, it may be null.

Good design usually passes mandatory state into the constructor if feasible; if container lifecycle is genuinely needed, use the bean instance managed by the context.

### 14.3. `@Transactional` Does Not Take Effect as Expected

~~~java
@Service
public class TransferService {
    @Transactional
    public void transfer() {
        // Money transfer operation.
    }
}
~~~

If the service is manually instantiated with `new` and called directly, no Spring transaction advice wraps that object.

Even when using a bean, internal self-calls bypassing the proxy are another case to understand. Determine **who created the object, whether the call passes through a proxy, and whether transaction infrastructure is properly configured** before tweaking annotations.

### 14.4. Configuration in `application.yml` Is Not Applied

An object instantiated with `new` does not automatically have Spring read **@Value** or bind **@ConfigurationProperties**. If a bean is created by Spring through a constructor/factory method and configuration is properly registered, values can be supplied from `Environment`.

Trace carefully: who passed the value, which bean was registered, which properties were loaded, and which profile is active.

### 14.5. Having Two Instances While Thinking Only One Exists

~~~java
@Service
public class SequenceGenerator {
    private int value;

    public int next() {
        return ++value;
    }
}
~~~

If one place uses the bean and another writes **new SequenceGenerator()**, the two sites hold independent state. Sequence numbers or login states can behave confusingly.

This also highlights the risk of race conditions when using mutable singletons; even with a single bean, **++value** is not automatically thread-safe.

### 14.6. Bean Not Found Despite Adding `@Service`

**NoSuchBeanDefinitionException** or **UnsatisfiedDependencyException** can happen because:

- The class is outside the component-scan scope.
- The bean is only created when a profile/condition matches.
- Another constructor dependency is not registered.
- The class is missing from the required runtime classpath.
- You are injecting a mismatched type or qualifier.

Do not fix every missing-bean error by calling **new** directly in the controller. Doing so masks the root cause and breaks DI across the entire dependency chain.

### 14.7. Multiple Beans of the Same Type

If the context has two **NotificationSender** beans, type-based injection without a qualifier can be ambiguous. This is a bean-selection problem, **not a bug where the container created useless extra objects**.

Check bean names, qualifiers, primary candidates, and configuration intent before deciding. Sometimes both beans are genuinely needed to handle two different notification channels.

## 15. How to Identify Whether an Object Belongs to the Spring Context

A Java variable by itself does not reliably tell you how the object was created. Many components can be passed through general APIs; proxies can also hide the real class.

Trace **where the reference came from**.

### 15.1. Find Where the Object Was Created

If the code reads:

~~~java
ReportService reportService = new ReportService(new ReportRepository());
~~~

then these are objects assembled manually in the current code.

If the code reads:

~~~java
public ReportController(ReportService reportService) {
    this.reportService = reportService;
}
~~~

and **ReportController** is a Spring-created bean, the **reportService** constructor parameter is normally resolved by Spring from the container. Still, verify the exact bean registration method and any custom factories if the app has special configuration.

### 15.2. Inspect Bean Registrations in `ApplicationContext`

Example:

~~~java
import org.springframework.context.ApplicationContext;
import org.springframework.stereotype.Component;

@Component
public class BeanInspector {
    private final ApplicationContext context;

    public BeanInspector(ApplicationContext context) {
        this.context = context;
    }

    public void inspect() {
        System.out.println(
                context.getBeanNamesForType(ReportService.class).length
        );
    }
}
~~~

This is a way to observe **which beans the context can find by type**. It does not check a specific object reference. Results also depend on bean types, factory beans, and context state. In business code, avoid using lookup or introspection commands instead of constructor injection just to fetch ordinary dependencies.

### 15.3. When Suspicion Falls on Auto-Configuration

Spring Boot has a **condition evaluation report** explaining which auto-configuration conditions matched or did not match. If a bean is created automatically by Boot, inspecting conditions and the classpath can be helpful.

If Actuator is added and the appropriate endpoint is exposed, the **beans** endpoint can help inspect beans across application contexts:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,beans
~~~

When enabled and accessed per configuration, the endpoint is typically at **/actuator/beans**. Restrict access to management endpoints according to security requirements, as the data can reveal internal application structure.

A bean missing from the report as expected may be due to scanning, profiles, conditions, scope, or context configuration. Cross-check against source code and startup logs.

## 16. A Decision Diagram: Should You `new` or Receive a Bean?

~~~text
You need an object
       │
       ▼
Does the object only hold data / state specific to one operation?
       │
       ├── Yes
       │     └── new / Java factory / binding is usually appropriate
       │
       └── No
             │
             ▼
Does it need application dependencies,
config, lifecycle, or Spring AOP?
             │
             ├── Yes
             │    └── Register a Spring bean and inject into consumers
             │
             └── No
                   │
                   ▼
Does it need to be shared/consistently configured
across multiple application components?
                   │
                   ├── Yes
                   │    └── Consider a managed bean or factory
                   │
                   └── No
                        └── Instantiate directly as needed
~~~

This diagram is not a rigid rule. A stateful object can be supplied via a **prototype bean** or a Spring-managed factory; a class that does not need Spring can be used inside a Spring bean without being a bean itself.

The deeper design principle is **separating business logic from object-graph assembly**. Objects managing dependencies and application infrastructure can be orchestrated by Spring, while objects representing short-lived data can be instantiated directly.

## 17. Self-Check Exercises

### Scenario 1: `new` Inside `@Bean`

~~~java
@Configuration
class MyConfig {
    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
~~~

**Is the returned Clock a bean?** Yes, provided the configuration is processed by Spring and the definition is registered. The fact that **Clock.systemUTC()** returns a Java object does not prevent that object from becoming a bean.

### Scenario 2: `@Service` Yet Calling `new`

~~~java
@Service
class ReportService {
}

ReportService report = new ReportService();
~~~

**Does the variable `report` reference a Spring-managed bean?** Not automatically. The class annotated with **@Service** may produce another bean when component scanning runs, yet the instance created directly on the **new** line is not registered merely by that annotation.

### Scenario 3: Singleton, Prototype, and Lookup

~~~java
@Component
@Scope("prototype")
class JobContext {
}
~~~

~~~java
JobContext first = context.getBean(JobContext.class);
JobContext second = context.getBean(JobContext.class);
~~~

**Are `first` and `second` the same instance?** Under standard prototype scope, no. Both are bean instances created by the container on demand, yet they are distinct objects.

### Scenario 4: Manually `new`ed Object with Lifecycle Annotation

~~~java
@Component
class WorkerClient {
    @PostConstruct
    void start() {
        System.out.println("Started");
    }
}

WorkerClient client = new WorkerClient();
~~~

**Does it automatically print Started?** No, because calling `new` alone does not trigger Spring lifecycle processing. If the class's constructor had print logic, that would be different; in this example, **start()** is only marked by an annotation.

### Scenario 5: DTO Created in a Controller

~~~java
@GetMapping("/status")
public StatusResponse status() {
    return new StatusResponse("OK");
}
~~~

**Does `StatusResponse` need to be a Spring bean?** Usually no. It is a response DTO created for returned data. The controller can be a bean, yet the DTO object it creates does not become a bean because of that.

### Scenario 6: Using the Same Class in Two Places

~~~java
PricingService fromContext = context.getBean(PricingService.class);
PricingService manual = new PricingService(...);
~~~

**Are the two references guaranteed to be the same object?** No. The manual object and the context bean are normally two distinct instances, even though they share the same Java type. You must understand constructors, scopes, and bean proxies when analyzing identity.

## 18. Common Misconceptions

**"A bean is not an ordinary Java object."**  
A bean is still a Java object. The difference is that the container manages creation, assembly, scope, and lifecycle; the reference may point to a Spring-generated proxy.

**"Spring does not use `new` when creating beans."**  
Spring can invoke constructors or call factory methods returning objects created with `new`. What matters is **ownership of instance management**.

**"Adding `@Component` to a class means every `new` of that class gets injected."**  
No. Component scanning registers matching bean definitions; it does not alter arbitrary `new` calls throughout the program.

**"Simply adding `@Autowired` fills fields regardless of who created the object."**  
No. Autowiring requires an appropriate Spring mechanism to process the object. On manual objects, fields can remain null.

**"Every bean is a singleton and every lookup returns the same object."**  
No. Scopes can be prototype, request, or session; proxies and multiple `ApplicationContext` instances also make identity context-dependent.

**"Singleton beans are automatically thread-safe."**  
No. Multiple threads can use the same instance; mutable state must be designed safely.

**"Putting `@Transactional` on a class means every call runs in a transaction."**  
No. Both transaction infrastructure and how calls route through proxies/aspects matter.

**"To unit test a `@Service`, you must boot Spring Boot."**  
No. Constructor injection lets you construct the service with fake dependencies and test logic in plain Java. A Spring context is only needed when verifying wiring or Spring-provided behavior.

**"A DTO created by Spring MVC must be a singleton bean."**  
No. Data binding/serialization creates objects for requests or responses; it differs from registering beans in `ApplicationContext`.

**"An object called by a bean automatically becomes a bean itself."**  
No. A bean can use many plain Java objects. Only objects registered/managed by the container via bean mechanics carry the corresponding bean contract.

**"Once beans exist in the context, you never need factories or `new` again."**  
No. Application code still creates value objects, entities, DTOs, or temporary objects. Factories and scopes help draw the right boundary between Spring management and on-demand creation.

## Conclusion: Distinguish by Ownership, Not by Keyword

Remember three points:

1. **`new` is Java's instance-creation operation**; it does not automatically register an instance in the Spring `ApplicationContext`.
2. **A Spring bean is an object managed by the container**; that object can still be created via a constructor or a factory method containing `new`.
3. **DI behavior, lifecycle, scope, and many AOP features** depend on the object participating in the appropriate management mechanism and how it is invoked, not merely on annotations present in source code.

In Spring Boot, let the container manage application components requiring dependencies and framework integration, while continuing to instantiate plain Java objects for data and short-lived work. Clearly distinguishing these two kinds of references makes it much easier to understand why a field wasn't injected, why a lifecycle callback didn't run, why a transaction didn't trigger, and why the same class can have multiple instances with different states.
