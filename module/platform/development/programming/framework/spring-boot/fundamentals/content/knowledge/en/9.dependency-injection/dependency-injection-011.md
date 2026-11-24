# Keeping Dependencies Explicit Instead of Scattering Context Lookups Across Business Logic

In a Spring Boot application, components often need to call each other to complete a use case. For example, `CheckoutService` needs a `PaymentGateway` to charge payments, an `OrderRepository` to save orders, and perhaps a `NotificationSender` to send notifications. These components are **dependencies** of the service.

Spring provides `ApplicationContext` to manage beans and allows retrieving beans via `getBean(...)`. Because that capability exists, developers sometimes pass the entire `ApplicationContext` into a service and call `getBean` wherever an object is needed. That looks flexible, yet it hides dependencies: looking at the constructor tells you nothing about what the service actually needs, and missing-bean errors may only appear when a particular business branch runs.

In application design, you should **declare dependencies directly via constructors or explicit contracts**. The container is responsible for assembling the object graph; services focus on business logic. When dynamic implementation selection, optional dependencies, or on-demand instantiation are needed, Spring abstractions like `ObjectProvider`, factories, or registries express those needs without turning business logic into container lookup code.

## 1. What Is a Dependency and Why Should It Be Visible?

A dependency is a component an object needs in order to carry out its responsibility. Example:

~~~text
CheckoutController
       |
       v
CheckoutService
   |          |
   v          v
OrderRepository  PaymentGateway
~~~

`CheckoutService` depends on `OrderRepository` and `PaymentGateway`. These two relationships are part of the service's structure, not accidental details buried in a random line of code.

An explicit style:

~~~java
@Service
public class CheckoutService {
    private final OrderRepository orderRepository;
    private final PaymentGateway paymentGateway;

    public CheckoutService(
            OrderRepository orderRepository,
            PaymentGateway paymentGateway
    ) {
        this.orderRepository = orderRepository;
        this.paymentGateway = paymentGateway;
    }
}
~~~

By looking at the constructor, a reader immediately sees the service requires two collaborators. Spring also knows it must find matching beans for each parameter type when creating `CheckoutService`.

Conversely, if the constructor only accepts `ApplicationContext`:

~~~java
@Service
public class CheckoutService {
    private final ApplicationContext context;

    public CheckoutService(ApplicationContext context) {
        this.context = context;
    }
}
~~~

then the constructor shows only one dependency—the container—while internal logic may use many different beans. Business dependencies are hidden behind lookups.

### What do explicit dependencies give you?

- **Readability:** the constructor shows what the service needs to operate.
- **Testability:** tests can pass fakes or mocks via the constructor without booting a full Spring context.
- **Early error detection:** missing required dependencies usually cause the context to fail during bean creation.
- **Reduced coupling:** services depend on business interfaces, without knowing how the container locates implementations.
- **Easier refactoring:** changing a dependency exposes affected places through types and constructors.
- **Observable dependency graph:** relationships between components can be traced from constructors, configuration, and interfaces.

Explicit dependencies do not mean passing every value into the constructor. Per-request data such as `customerId`, `orderId`, or `quantity` belong in method parameters. Dependencies are collaborators or resources the object needs to perform its role, whereas inputs that vary per invocation belong in the business API.

## 2. What Is Bean Lookup via ApplicationContext?

`ApplicationContext` is Spring's primary container interface. It extends `BeanFactory`'s basic capabilities and adds application-environment services. One of its capabilities is looking up beans by type or name:

~~~java
PaymentGateway gateway =
        applicationContext.getBean(PaymentGateway.class);
~~~

Or:

~~~java
Object bean = applicationContext.getBean("paymentGateway");
~~~

This is called **dependency lookup**, or categorized under the **Service Locator** pattern when an object asks a container for its collaborators at runtime.

Service Locator is not a wrong API in every situation. It can be useful in infrastructure layers or in plugin frameworks that genuinely need dynamic component discovery. The problem arises when business services use it as their ordinary dependency injection mechanism.

### Example of scattered lookups in business logic

~~~java
@Service
public class CheckoutService {
    private final ApplicationContext context;

    public CheckoutService(ApplicationContext context) {
        this.context = context;
    }

    public Receipt checkout(CheckoutCommand command) {
        OrderRepository repository =
                context.getBean(OrderRepository.class);

        PaymentGateway gateway =
                context.getBean(PaymentGateway.class);

        Order order = repository.findDraft(command.orderId())
                .orElseThrow();

        PaymentResult result = gateway.charge(
                new ChargeCommand(order.id(), order.total())
        );

        if (result.success()) {
            repository.markPaid(order.id());
        }

        return new Receipt(order.id(), result.reference());
    }
}
~~~

This code illustrates a service looking up its collaborators itself. It can still run if the beans exist, but it creates several issues:

1. **The constructor does not describe all dependencies.** Readers must inspect the full method body to learn that the service needs a repository, a gateway, and potentially more beans.
2. **Failures are delayed.** If `PaymentGateway` is missing, the application may still start; the failure only happens when `checkout` runs.
3. **Harder unit testing.** Tests need an `ApplicationContext` or a mocked context even when the goal is solely to test checkout logic.
4. **The service depends on Spring APIs.** Business logic knows how to access the container, making reuse outside Spring harder.
5. **Name-based lookups are fragile.** Bean name strings can silently break after renames or configuration changes.
6. **Hard to control lookup timing and count.** One branch might fetch a different implementation than another if the context or configuration contains multiple candidates.
7. **Hard to trace the dependency graph.** Tools reading constructors, IDEs, and reviewers cannot easily spot hidden relationships.

The issue is not the character count of calling `getBean`. The issue is that the service is **responsible for discovering and fetching its own dependencies** instead of declaring what it needs.

## 3. How Do Dependency Injection and Service Locator Differ?

Both approaches can return the exact same bean, yet control sits in different places.

~~~text
Dependency Injection

Spring ApplicationContext
       |
       | finds and supplies beans
       v
CheckoutService(repository, gateway)
       |
       +---- uses repository
       |
       +---- uses gateway


Service Locator

CheckoutService(ApplicationContext)
       |
       +---- getBean(OrderRepository.class)
       |
       +---- getBean(PaymentGateway.class)
       |
       +---- can continue fetching more beans
~~~

| Criterion | Dependency Injection | Service Locator / context lookup |
|---|---|---|
| Where are dependencies declared? | Constructor or object-creation API | Inside method bodies or locator call sites |
| Who finds implementations? | The container at assembly time | The consuming object queries the locator itself |
| Are dependencies visible when reading the class? | Usually yes | Usually incomplete |
| Missing required dependency error | Typically surfaces during bean creation | May surface only when the lookup branch executes |
| Unit testing | Pass fakes/mocks directly | Must supply locator/context or alter lookup mechanism |
| Coupling to Spring | Can stay low in business layers | High if business layers call Spring APIs directly |
| Best suited for | Stable, mandatory collaborators of an object | Specific infrastructure needing dynamic discovery with clear boundaries |

Both DI and Service Locator can use a container behind the scenes. The difference is whether **the consumer explicitly declares what it needs or goes looking for it at runtime**.

## 4. Constructor Injection: The Preferred Default for Declaring Dependencies

In Spring, constructor injection is the clearest way to declare required dependencies.

~~~java
@Service
public class CheckoutService {
    private final OrderRepository orderRepository;
    private final PaymentGateway paymentGateway;

    public CheckoutService(
            OrderRepository orderRepository,
            PaymentGateway paymentGateway
    ) {
        this.orderRepository = orderRepository;
        this.paymentGateway = paymentGateway;
    }

    public Receipt checkout(CheckoutCommand command) {
        // Use the two supplied dependencies.
        return null;
    }
}
~~~

Spring finds beans matching each constructor parameter and supplies them when creating the service. If the class has a single constructor, under normal rules you do not need `@Autowired` on that constructor.

### Why do constructors fit required dependencies?

An object should only be created once all required collaborators are present. The constructor is the natural boundary to enforce this:

~~~java
public CheckoutService(
        OrderRepository orderRepository,
        PaymentGateway paymentGateway
) {
    this.orderRepository = Objects.requireNonNull(orderRepository);
    this.paymentGateway = Objects.requireNonNull(paymentGateway);
}
~~~

If instantiated manually, callers must also supply every dependency. If instantiated by Spring, the container must resolve all dependencies before completing the bean. Marking fields `final` prevents references from changing after construction finishes.

### Constructors also serve as a responsibility descriptor

If a service has fifteen dependencies, a long constructor is a useful warning sign. The class may be handling too many use cases or coordinating too many distinct parts. The fix is not necessarily moving everything into `ApplicationContext` to shorten the constructor; inspect responsibilities, split use cases, or extract meaningful abstractions.

**Do not disguise complexity by hiding dependencies.** A long constructor is often valuable design feedback: it reveals that a class knows too much.

## 5. Complete Spring Boot Example: Checkout with Explicit Dependencies

Let's build a small example containing a controller, service, repository, and payment gateway. Classes live under the root package `com.example.shop` so Spring Boot component scanning works by default. The example uses Java 17+ and Spring MVC; a real project needs the web starter and appropriate configuration.

### 5.1. Business data types

~~~java
package com.example.shop;

public record CheckoutCommand(Long orderId) {}

public record ChargeCommand(Long orderId, long amount) {}

public record PaymentResult(
        boolean success,
        String reference
) {}

public record Receipt(
        Long orderId,
        String paymentReference
) {}
~~~

These records represent input/output data. They do not need to be beans because they are created per business operation.

### 5.2. Declaring repository and gateway contracts

~~~java
package com.example.shop;

import java.util.Optional;

public interface OrderRepository {
    Optional<Order> findDraft(Long orderId);
    void markPaid(Long orderId);
}
~~~

~~~java
package com.example.shop;

public interface PaymentGateway {
    PaymentResult charge(ChargeCommand command);
}
~~~

Interfaces state what the service needs. They do not require the service to know whether implementations use JPA, JDBC, an HTTP client, or a payment vendor SDK.

### 5.3. Providing implementations as beans

In-memory repository:

~~~java
package com.example.shop;

import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Repository;

@Repository
public class InMemoryOrderRepository implements OrderRepository {
    private final Map<Long, Order> orders = Map.of(
            101L, new Order(101L, 250_000L)
    );

    @Override
    public Optional<Order> findDraft(Long orderId) {
        return Optional.ofNullable(orders.get(orderId));
    }

    @Override
    public void markPaid(Long orderId) {
        // Illustrative only. A real repository updates persisted state.
    }
}
~~~

`Order` type:

~~~java
package com.example.shop;

public record Order(Long id, long total) {}
~~~

Mock/demo gateway:

~~~java
package com.example.shop;

import org.springframework.stereotype.Component;

@Component
public class DemoPaymentGateway implements PaymentGateway {
    @Override
    public PaymentResult charge(ChargeCommand command) {
        return new PaymentResult(
                true,
                "DEMO-" + command.orderId()
        );
    }
}
~~~

Stereotype annotations let Spring component scanning register the implementations. In a real application, the repository and gateway would perform real persistence or external provider calls; the goal here is illustrating dependency relationships.

### 5.4. Service receiving dependencies via constructor

~~~java
package com.example.shop;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CheckoutService {
    private final OrderRepository orderRepository;
    private final PaymentGateway paymentGateway;

    public CheckoutService(
            OrderRepository orderRepository,
            PaymentGateway paymentGateway
    ) {
        this.orderRepository = orderRepository;
        this.paymentGateway = paymentGateway;
    }

    @Transactional
    public Receipt checkout(CheckoutCommand command) {
        Order order = orderRepository.findDraft(command.orderId())
                .orElseThrow(() ->
                        new IllegalArgumentException(
                                "Order not found"
                        )
                );

        PaymentResult payment = paymentGateway.charge(
                new ChargeCommand(order.id(), order.total())
        );

        if (!payment.success()) {
            throw new IllegalStateException(
                    "Payment failed"
            );
        }

        orderRepository.markPaid(order.id());

        return new Receipt(order.id(), payment.reference());
    }
}
~~~

`@Transactional` is only meaningful when transaction infrastructure and appropriate proxy invocation are configured. This example does not address full consistency concerns between a database and an external payment provider; a database transaction cannot roll back a charge already processed on an external system. For real workflows, consider idempotency, retries, and sagas/outbox as needed.

### 5.5. Controller also receives its service explicitly

~~~java
package com.example.shop;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CheckoutController {
    private final CheckoutService checkoutService;

    public CheckoutController(CheckoutService checkoutService) {
        this.checkoutService = checkoutService;
    }

    @PostMapping("/checkout")
    public Receipt checkout(@RequestBody CheckoutCommand command) {
        return checkoutService.checkout(command);
    }
}
~~~

Dependency graph:

~~~text
CheckoutController
        |
        v
CheckoutService
    |          |
    v          v
OrderRepository  PaymentGateway
    ^                  ^
    |                  |
InMemoryOrderRepository  DemoPaymentGateway
~~~

When Spring starts, the container discovers the beans and resolves the constructors of `CheckoutController` and `CheckoutService`. No service needs to know about `ApplicationContext` or call `getBean`.

### 5.6. What changes if an implementation changes?

Suppose later you replace `InMemoryOrderRepository` with `JpaOrderRepository`. As long as the application registers a single matching `OrderRepository` bean, `CheckoutService` keeps its constructor and logic untouched. Similarly, `DemoPaymentGateway` can be swapped for a live gateway.

That is the advantage of depending on contracts: **the consumer knows the capability it needs, not how the container finds the implementation**.

## 6. External Bean Configuration Does Not Mean Services Should Look Up Context

Sometimes an object carries no Spring annotations—for example, a client from a third-party library. We can declare the bean with `@Bean`:

~~~java
@Configuration
public class PaymentConfiguration {

    @Bean
    public VendorClient vendorClient(
            VendorSettings settings
    ) {
        return new VendorClient(
                settings.endpoint(),
                settings.apiKey()
        );
    }

    @Bean
    public PaymentGateway paymentGateway(
            VendorClient vendorClient
    ) {
        return new VendorPaymentGateway(vendorClient);
    }
}
~~~

`VendorClient`, `VendorSettings`, and `VendorPaymentGateway` are illustrative types defined in the project or integration library. The key point is that **the factory method receives dependencies via parameters**. Spring supplies `VendorSettings` to `vendorClient` and `VendorClient` to `paymentGateway` when the corresponding beans can be resolved.

Do not write:

~~~java
@Bean
public PaymentGateway paymentGateway(ApplicationContext context) {
    VendorClient client = context.getBean(VendorClient.class);
    return new VendorPaymentGateway(client);
}
~~~

The second form can work, yet it obscures the factory method's dependencies. In Spring configuration, `@Bean` method parameters are already the natural injection mechanism.

### Configuration as the composition root

You can view `@Configuration` classes and `@Bean` methods as part of the **composition root**: the place deciding which implementations connect together. Configuration is allowed to know about Spring and integration details; business services do not need to carry that responsibility.

~~~text
Configuration / ApplicationContext
       |
       +--> creates VendorClient
       |
       +--> creates VendorPaymentGateway(client)
       |
       +--> creates CheckoutService(repository, gateway)
                         |
                         v
                  checkout logic
~~~

This is the right place to centralize configuration, qualifiers, profiles, and conditional bean creation.

## 7. When Multiple Implementations Exist, Inject a Collection or Use a Registry

Scattered context lookups often start from a legitimate situation: an application has multiple implementations and wants to pick one based on input data. Yet dynamic selection does not require calling `getBean`.

For example, the system supports multiple payment methods:

~~~java
public enum PaymentMethod {
    CARD,
    BANK_TRANSFER
}
~~~

Contract:

~~~java
public interface PaymentGateway {
    boolean supports(PaymentMethod method);
    PaymentResult charge(ChargeCommand command);
}
~~~

Implementations:

~~~java
@Component
public class CardPaymentGateway implements PaymentGateway {
    @Override
    public boolean supports(PaymentMethod method) {
        return method == PaymentMethod.CARD;
    }

    @Override
    public PaymentResult charge(ChargeCommand command) {
        // Call card provider.
        return new PaymentResult(true, "CARD-REF");
    }
}
~~~

~~~java
@Component
public class BankTransferGateway implements PaymentGateway {
    @Override
    public boolean supports(PaymentMethod method) {
        return method == PaymentMethod.BANK_TRANSFER;
    }

    @Override
    public PaymentResult charge(ChargeCommand command) {
        // Create bank transfer request.
        return new PaymentResult(true, "BANK-REF");
    }
}
~~~

A resolver receives the list of gateways:

~~~java
@Component
public class PaymentGatewayResolver {
    private final List<PaymentGateway> gateways;

    public PaymentGatewayResolver(List<PaymentGateway> gateways) {
        this.gateways = List.copyOf(gateways);
    }

    public PaymentGateway resolve(PaymentMethod method) {
        return gateways.stream()
                .filter(gateway -> gateway.supports(method))
                .findFirst()
                .orElseThrow(() ->
                        new IllegalArgumentException(
                                "Unsupported payment method"
                        )
                );
    }
}
~~~

The service uses the resolver:

~~~java
@Service
public class CheckoutService {
    private final PaymentGatewayResolver gatewayResolver;

    public CheckoutService(PaymentGatewayResolver gatewayResolver) {
        this.gatewayResolver = gatewayResolver;
    }

    public PaymentResult pay(
            PaymentMethod method,
            ChargeCommand command
    ) {
        return gatewayResolver.resolve(method).charge(command);
    }
}
~~~

Here, the resolver's dependency is **the collection of gateways**. It selects by payment method without looking up `ApplicationContext`. Each gateway declares what it supports via its contract.

In real applications, handle the case where multiple gateways return true for `supports` if rules require uniqueness. You can check the candidate count and fail with a clear configuration error instead of grabbing the first element in an arbitrary order.

### Injecting a Map when bean names are part of configuration

Spring can inject `Map<String, PaymentGateway>`, where keys are usually bean names and values are the corresponding beans:

~~~java
@Component
public class GatewayRegistry {
    private final Map<String, PaymentGateway> gateways;

    public GatewayRegistry(Map<String, PaymentGateway> gateways) {
        this.gateways = Map.copyOf(gateways);
    }
}
~~~

This is still an explicit dependency: the constructor declares that the registry requires a map of gateways. However, if business code has to concatenate bean name strings from user input and look them up in the map, it still depends on container naming conventions. Convert input into an enum/domain type and validate with a resolver.

## 8. When Dependencies Are Truly Optional or Needed Lazily

Not every dependency must be present. For example, notification sending may be disabled locally. If a service cannot work without a dependency, mandatory constructor injection is appropriate. If a dependency is truly optional, express it using an appropriate type or abstraction.

### Using Optional for optional dependencies

~~~java
@Service
public class ReceiptService {
    private final Optional<ReceiptArchive> archive;

    public ReceiptService(Optional<ReceiptArchive> archive) {
        this.archive = archive;
    }

    public void archiveIfConfigured(Receipt receipt) {
        archive.ifPresent(value -> value.store(receipt));
    }
}
~~~

`Optional<ReceiptArchive>` signals that the dependency may not exist. This fits simple optional dependencies. If multiple beans of the same type exist, understand resolution rules; `Optional` does not decide between ambiguous implementations.

### Using ObjectProvider for deferred lookup via a typed abstraction

Spring provides `ObjectProvider<T>` to retrieve a bean on demand, handle absent beans, or access candidate collections:

~~~java
@Service
public class NotificationService {
    private final ObjectProvider<NotificationSender> senderProvider;

    public NotificationService(
            ObjectProvider<NotificationSender> senderProvider
    ) {
        this.senderProvider = senderProvider;
    }

    public void notifyIfEnabled(Notification message) {
        NotificationSender sender = senderProvider.getIfAvailable();

        if (sender != null) {
            sender.send(message);
        }
    }
}
~~~

Import `org.springframework.beans.factory.ObjectProvider`. `getIfAvailable()` returns `null` when no matching bean exists; if multiple unresolvable beans exist, it can throw a non-unique error. To process multiple candidates, use `orderedStream()` or an explicitly injected list/registry.

`ObjectProvider` is useful when:

- A bean may not exist depending on configuration.
- Retrieving the bean should be deferred until usage time.
- A fresh instance of a prototype bean is needed on every call.
- A typed collection of beans is needed.
- You want the dependency type explicit without passing the whole `ApplicationContext`.

However, do not replace every constructor parameter with `ObjectProvider` to avoid listing dependencies. When a bean is always required, injecting `T` directly is simpler and clearer.

### Prototype beans and instance retrieval timing

Suppose `ReportSession` has prototype scope:

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class ReportSession {
    // State dedicated to a single report generation.
}
~~~

If a singleton service injects `ReportSession` directly in its constructor, Spring creates the prototype when constructing the singleton; the service holds that same instance in its field. If you need a fresh instance per report:

~~~java
@Service
public class ReportService {
    private final ObjectProvider<ReportSession> sessionProvider;

    public ReportService(ObjectProvider<ReportSession> sessionProvider) {
        this.sessionProvider = sessionProvider;
    }

    public void generate() {
        ReportSession session = sessionProvider.getObject();
        // Use session for this report build.
    }
}
~~~

A provider keeps the bean request explicit and lets the container apply scope rules. Still, for plain data objects that do not need Spring scopes or lifecycles, a plain Java factory can be simpler.

### Using `@Lazy` when deferred initialization is needed

`@Lazy` can be placed on a bean or injection point to defer initialization per Spring's rules. Example:

~~~java
@Service
public class LargeReportService {
    private final ReportEngine reportEngine;

    public LargeReportService(@Lazy ReportEngine reportEngine) {
        this.reportEngine = reportEngine;
    }
}
~~~

This can help if initializing the engine is expensive and may not be used. Yet `@Lazy` is not a tool for masking bad dependencies or fixing circular dependencies by default. Proxy/lazy resolution has its own semantics, and errors may surface only when the real bean is called.

## 9. Do Not Route Business Data Through ApplicationContext

Another form of misuse is using the container to look up objects based on request data:

~~~java
public Receipt checkout(String customerType, CheckoutCommand command) {
    CustomerPolicy policy = context.getBean(
            customerType + "CustomerPolicy",
            CustomerPolicy.class
    );
    // ...
}
~~~

Here, `customerType` is business data. It should not be concatenated into a bean name and handed to the container for lookup. That forces business rules to know bean names and turns user input into part of the container lookup mechanism.

Instead, create a typed registry, inject the required policies, and select using domain types:

~~~java
public enum CustomerType {
    REGULAR,
    PREMIUM
}
~~~

~~~java
public interface CustomerPolicy {
    CustomerType type();
    Discount calculate(CheckoutCommand command);
}
~~~

~~~java
@Component
public class CustomerPolicyResolver {
    private final Map<CustomerType, CustomerPolicy> policies;

    public CustomerPolicyResolver(List<CustomerPolicy> candidates) {
        EnumMap<CustomerType, CustomerPolicy> map =
                new EnumMap<>(CustomerType.class);

        for (CustomerPolicy policy : candidates) {
            CustomerPolicy previous = map.put(policy.type(), policy);
            if (previous != null) {
                throw new IllegalStateException(
                        "Duplicate policy for " + policy.type()
                );
            }
        }

        this.policies = Map.copyOf(map);
    }

    public CustomerPolicy resolve(CustomerType type) {
        CustomerPolicy policy = policies.get(type);
        if (policy == null) {
            throw new IllegalArgumentException(
                    "No policy for " + type
            );
        }
        return policy;
    }
}
~~~

This resolver receives implementations explicitly via its constructor and builds a lookup table keyed by a domain type. Request data only selects a policy from the registered set; it has no authority to ask the container to instantiate or find arbitrary beans.

The principle is: **use data to select within a controlled set of choices**, do not turn data into container access commands.

## 10. Keeping Boundaries Between Business Logic and Spring Framework

A major benefit of explicit dependencies is that business logic can rely less on the framework.

For example, a plain Java service:

~~~java
public class PriceCalculator {
    private final PricingPolicy pricingPolicy;

    public PriceCalculator(PricingPolicy pricingPolicy) {
        this.pricingPolicy = pricingPolicy;
    }

    public long calculate(long unitPrice, int quantity) {
        if (quantity < 1) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        return pricingPolicy.total(unitPrice, quantity);
    }
}
~~~

This class needs no Spring imports. Spring can instantiate it via:

~~~java
@Configuration
public class PricingConfiguration {

    @Bean
    public PriceCalculator priceCalculator(
            PricingPolicy pricingPolicy
    ) {
        return new PriceCalculator(pricingPolicy);
    }
}
~~~

Or the class can carry a stereotype if the project prefers component scanning. Either way, `PriceCalculator` does not need to know `ApplicationContext` exists.

### Why is reducing coupling helpful?

- Logic can be reused in another Java program or plain test.
- The container or instantiation mechanism can change without editing business logic.
- Business interfaces become clear module boundaries.
- Readers do not have to know Spring APIs to understand core algorithms.
- Framework changes stay isolated in the composition root and adapters.

You do not need to strip every Spring annotation from every class. `@Service` or `@Transactional` can be pragmatic choices in Spring apps. The goal of this lesson is to avoid **business logic querying the container itself like a global object store**.

## 11. Why Do ApplicationContext Lookups Make Testing Harder?

Suppose a test needs to verify how checkout handles a failed payment. With constructor injection, the test can pass simple fakes:

~~~java
OrderRepository repository = new FakeOrderRepository();
PaymentGateway failingGateway = command ->
        new PaymentResult(false, null);

CheckoutService service =
        new CheckoutService(repository, failingGateway);

// Call service and assert failure behavior.
~~~

No Spring startup required. The test instantiates only the collaborators involved in the behavior under test.

With a service locator:

~~~java
CheckoutService service =
        new CheckoutService(applicationContext);
~~~

the test must supply a context containing matching beans, or mock `ApplicationContext` and stub every `getBean` call. That ties tests to lookup mechanics instead of focusing on business rules.

### Unit testing with Mockito

Example using JUnit 5 and Mockito:

~~~java
@ExtendWith(MockitoExtension.class)
class CheckoutServiceTest {

    @Mock
    OrderRepository orderRepository;

    @Mock
    PaymentGateway paymentGateway;

    @Test
    void usesInjectedDependencies() {
        CheckoutService service =
                new CheckoutService(orderRepository, paymentGateway);

        // Arrange fake data and mock outputs.
        // Call service.
        // Assert results and verify expected interactions.
    }
}
~~~

This is an illustrative skeleton; real tests must define data, stubbing, and assertions matching the service API. Notice that the test can instantiate the service directly with controlled dependencies.

### When are Spring context tests still needed?

Unit tests do not verify component scanning, bean conditions, qualifiers, or auto-configuration setup. To verify real wiring, write an integration test or `@SpringBootTest`:

~~~java
@SpringBootTest
class CheckoutContextTest {

    @Autowired
    CheckoutService checkoutService;

    @Test
    void contextProvidesCheckoutService() {
        assertNotNull(checkoutService);
    }
}
~~~

The two test types complement each other:

| Test | Primary question |
|---|---|
| Unit test | Is service logic correct when given controlled dependencies? |
| Spring context test | Does the container register and wire beans as configured? |
| Integration test | Do components collaborate properly with databases, HTTP clients, or external systems? |

Do not use `@SpringBootTest` for every unit test simply because the app uses Spring. When a service can be tested via a Java constructor, take advantage of it.

## 12. Static ApplicationContext Holder: A Disguised Global Variable

A common anti-pattern is creating a static context holder:

~~~java
@Component
public class SpringContextHolder implements ApplicationContextAware {
    private static ApplicationContext context;

    @Override
    public void setApplicationContext(ApplicationContext applicationContext) {
        context = applicationContext;
    }

    public static <T> T getBean(Class<T> type) {
        return context.getBean(type);
    }
}
~~~

Then anywhere in the codebase:

~~~java
PaymentGateway gateway =
        SpringContextHolder.getBean(PaymentGateway.class);
~~~

This makes it feel convenient to reach any bean globally without passing dependencies. Yet it brings real problems:

- **Global state:** any class can reach the container, leaving no clear dependency boundaries.
- **Initialization ordering:** calling the holder before Spring sets the context can hit `null`.
- **Multiple ApplicationContexts:** tests, parent/child contexts, or multiple apps in one JVM mean a single static variable may not represent the right context.
- **Hard to test in isolation:** tests must reset static state, risking leakage across tests.
- **Hard to change architecture:** every class calling the holder becomes coupled to this global mechanism.
- **Masks configuration errors:** beans are only requested at runtime, delaying missing-bean detection.

A specialized infrastructure class might need to interact with the context in specific framework or plugin systems. Never turn that mechanism into a general API for all business services.

If legacy code already has a holder, migrate gradually: identify each bean type being looked up, add corresponding constructor dependencies, move dynamic choices into registries/factories, and remove global access paths once no callers remain.

## 13. When Are Context Lookups Acceptable?

Do not turn "keep dependencies explicit" into a dogmatic ban on every container access. Some infrastructure scenarios genuinely require dynamic bean discovery:

- A framework extension needs to find handlers by metadata at runtime.
- A generic integration mechanism must work with bean types unknown at compile time.
- A bootstrap component or admin tool needs to inspect the context to observe application structure.
- An adapter at a framework boundary must interact with the container because an external contract requires it.

In those cases, isolate lookups inside **one infrastructure component with a dedicated responsibility**, and expose a typed API to the rest of the application.

~~~text
Business service
      |
      v
PluginRegistry (clear contract)
      |
      v
Spring-backed PluginRegistryAdapter
      |
      v
ApplicationContext / bean discovery
~~~

`PluginRegistryAdapter` understands Spring and can use the context if genuinely necessary. Business services know only `PluginRegistry` and the methods it exposes.

A helpful rule of thumb: if you removed Spring from a business class, could you still understand and test its responsibility? If the answer is no solely because the class keeps calling `getBean`, move the lookup out.

### Accessing context in configuration and bootstrap

In configuration layers, Spring already provides parameter injection for `@Bean`; use that instead of lookups. In bootstrap, admin, or framework-integration code, holding a reference to `ApplicationContext` can make sense when the purpose genuinely involves interacting with the container.

The difference lies in **the boundary of use**. An application can have a few Spring-aware infrastructure components while keeping most business logic container-independent.

## 14. Explicit Dependencies Make Lifecycles and Scopes Easier to Reason About

When a class declares dependencies in its constructor, scope relationships between beans become visible too. For instance, a singleton service receiving a singleton repository bean aligns naturally with application lifecycle. By contrast, if a singleton service injects a prototype bean directly, it holds only the single instance supplied when the singleton was created.

Context lookups inside methods can cause scope behavior to shift by call site in ways readers miss:

~~~java
public void generate() {
    ReportSession session =
            applicationContext.getBean(ReportSession.class);
}
~~~

If `ReportSession` is a prototype, each `getBean` call may return a new instance. Yet that intent is hidden behind a container call. Using `ObjectProvider<ReportSession>` makes the type and deferred retrieval explicit:

~~~java
@Service
public class ReportService {
    private final ObjectProvider<ReportSession> sessionProvider;

    public ReportService(ObjectProvider<ReportSession> sessionProvider) {
        this.sessionProvider = sessionProvider;
    }

    public void generate() {
        ReportSession session = sessionProvider.getObject();
        // ...
    }
}
~~~

Readers immediately see the service holds a provider for `ReportSession` and requests an instance when `generate` runs. This is typed and far more constrained than accepting the entire context.

However, if `ReportSession` is merely a short-lived data object needing no Spring scope or lifecycle, a plain Java factory may fit even better:

~~~java
public interface ReportSessionFactory {
    ReportSession create();
}
~~~

The factory is injected into the service and instantiates objects in plain Java. Choosing between a provider and a factory depends on whether the object genuinely needs container lifecycle/scoping.

## 15. `@Qualifier` and `@Primary` Handle Selection Without Manual Lookup

When two beans implement the same interface, the container needs to know which bean matches an injection point.

Example:

~~~java
@Component("cardGateway")
public class CardPaymentGateway implements PaymentGateway {
    // ...
}

@Component("bankGateway")
public class BankTransferGateway implements PaymentGateway {
    // ...
}
~~~

A consumer can choose explicitly:

~~~java
@Service
public class CardCheckoutService {
    private final PaymentGateway paymentGateway;

    public CardCheckoutService(
            @Qualifier("cardGateway") PaymentGateway paymentGateway
    ) {
        this.paymentGateway = paymentGateway;
    }
}
~~~

Or mark a default bean:

~~~java
@Component
@Primary
public class CardPaymentGateway implements PaymentGateway {
    // ...
}
~~~

`@Primary` picks the preferred bean when multiple candidates exist for an injection point without a specific qualifier. `@Qualifier` expresses selection at the consumption site. Both keep dependency relationships in constructors and configuration instead of writing `context.getBean("cardGateway")` inside method bodies.

If selection varies by request data, use a list-injected resolver/registry as shown earlier. `@Qualifier` is not a tool for picking a different bean on every method call; it determines bean wiring when the container instantiates objects.

## 16. Profile and Property Configuration Still Keeps Dependencies Explicit

Suppose local dev uses a mock gateway and production uses a live gateway. Register implementations per profile:

~~~java
@Component
@Profile("dev")
public class DemoPaymentGateway implements PaymentGateway {
    // ...
}
~~~

~~~java
@Component
@Profile("prod")
public class LivePaymentGateway implements PaymentGateway {
    // ...
}
~~~

`CheckoutService` still declares only:

~~~java
public CheckoutService(PaymentGateway paymentGateway) {
    this.paymentGateway = paymentGateway;
}
~~~

Profiles control which bean is present; constructor injection wires the active implementation. The service does not need to check `spring.profiles.active`, call `getBean` per profile, or instantiate gateways itself.

If no profile provides `PaymentGateway`, the context reports a missing bean. That is an early, clear configuration failure compared to letting the service run into a branch before discovering no bean exists.

For optional features, `@ConditionalOnProperty` can govern beans or configuration, while consumers express whether dependencies are required or optional. If an absent dependency is valid, use `Optional`, `ObjectProvider`, or a default implementation with clear semantics.

## 17. Practices to Avoid and How to Migrate

| Practice | Problem | Better alternative |
|---|---|---|
| Service injects `ApplicationContext` and calls `getBean` for every dependency | Hides dependencies, couples to Spring | Constructor injection |
| Calling `getBean("...")` with strings across many methods | Bean names scattered, fragile on refactors | `@Qualifier` or typed registry |
| Static holder storing context | Global state, hard to test, breaks with multiple contexts | Inject dependencies or infrastructure adapter |
| Passing context through multiple layers just for the leaf class to get a bean | Spreads framework coupling | Inject the exact bean the leaf class needs directly |
| Using lookup to avoid a long constructor | Masks overly broad service responsibilities | Split use cases or cohesive components |
| Using lookup with user-supplied values | Request data drives arbitrary bean access | Resolver validating domain types and allowed implementations |
| Using `ObjectProvider` for every dependency | Makes required dependencies look optional/lazy | Inject bean type directly when needed upfront |
| Using `@Lazy` to mask circular dependencies | Design flaw remains, only shifts detection timing | Split responsibilities, create unidirectional dependencies |

### Migrating a service currently using context

Suppose legacy code looks like:

~~~java
@Service
public class InvoiceService {
    private final ApplicationContext context;

    public InvoiceService(ApplicationContext context) {
        this.context = context;
    }

    public Invoice create(InvoiceCommand command) {
        InvoiceRepository repository =
                context.getBean(InvoiceRepository.class);

        TaxCalculator calculator =
                context.getBean(TaxCalculator.class);

        // ...
        return null;
    }
}
~~~

You can migrate it to:

~~~java
@Service
public class InvoiceService {
    private final InvoiceRepository repository;
    private final TaxCalculator calculator;

    public InvoiceService(
            InvoiceRepository repository,
            TaxCalculator calculator
    ) {
        this.repository = repository;
        this.calculator = calculator;
    }

    public Invoice create(InvoiceCommand command) {
        // Use the supplied repository and calculator.
        return null;
    }
}
~~~

Step-by-step migration:

1. Find all `getBean` calls in the class and note the bean types actually used.
2. Determine which dependencies are required, optional, or chosen by runtime data.
3. Add constructor parameters for required dependencies; use interfaces instead of concrete classes where boundaries matter.
4. For multiple implementations, configure `@Qualifier`/`@Primary` or create a resolver injecting the bean list.
5. For optional/lazy/prototype dependencies, consider `Optional`, `ObjectProvider`, or a factory.
6. Remove the `ApplicationContext` field and the replaced lookups.
7. Update unit tests to instantiate the service via constructor with fakes/mocks.
8. Use context tests to confirm Spring still locates and wires the right beans in the target environment.

Do not migrate mechanically by dumping every bean into the constructor if the class is genuinely coordinating too many features. Consider splitting the class before or during migration so each service stays cohesive and easy to follow.

## 18. Reading Errors After Switching to Explicit Dependencies

After replacing lookups with constructor injection, some errors may appear earlier when the application starts. This is usually helpful because the container detects an incomplete graph right away.

| Message or symptom | Common meaning | Investigation direction |
|---|---|---|
| `NoSuchBeanDefinitionException` | No bean matches required dependency | Component scan, `@Bean`, profiles, conditionals, classpath |
| `NoUniqueBeanDefinitionException` | Multiple matching beans without clear choice | `@Qualifier`, `@Primary`, list/registry |
| `UnsatisfiedDependencyException` | A dependency in the initialization chain was not satisfied | Read nested causes to find the root bean |
| Circular dependency error | Beans form a dependency cycle | Split responsibilities and establish one-way calls |
| Context starts, yet lookup fails when method runs | Lookup is still deferred to runtime or on a rare branch | Find remaining `getBean` calls and their execution conditions |
| Unit test needs to boot the entire app | Class depends on container or too many parts | Extract logic, inject dependencies, use fakes/mocks |

Constructor injection does not guarantee an application is free of runtime errors. It ensures dependencies that are **required and resolvable at startup** are verified earlier. Lost database connections, failed payments, or invalid inputs still need handling inside each use case.

## 19. Thought Exercise

Suppose a Spring Boot application has a service:

~~~java
@Service
public class ShippingService {
    private final ApplicationContext context;

    public ShippingService(ApplicationContext context) {
        this.context = context;
    }

    public void ship(ShipmentCommand command) {
        ShipmentRepository repository =
                context.getBean(ShipmentRepository.class);

        ShippingProvider provider =
                context.getBean("expressProvider",
                        ShippingProvider.class);

        // Create shipment and call shipping carrier.
    }
}
~~~

Analyze:

1. What are the actual dependencies of `ShippingService`?
2. Why can't a reviewer tell all of them from the constructor alone?
3. If `ShippingProvider` has no bean, when does the failure surface?
4. Should `ShippingProvider` be optional or required?
5. If `ExpressProvider` and `EconomyProvider` exist, should selection use a fixed qualifier or a resolver driven by the customer's shipping choice?
6. How would you test shipment creation logic without starting Spring?
7. If the provider comes from an external SDK, in which layer should its bean be created?

One possible design is `ShippingService(ShipmentRepository, ShippingProviderResolver)`. The resolver receives explicitly injected providers and selects based on a validated `ShippingMethod` type. That way, the service still states what it needs, and runtime selection lives in a component with its own clear responsibility.

## 20. Principles to Keep

- **Required dependencies belong in the constructor.** Do not hide them behind an `ApplicationContext` reference.
- **Business services should depend on meaningful contracts.** Services do not need to know whether beans were registered by `@Component`, `@Bean`, or auto-configuration.
- **Business data belongs in parameters or command objects.** Never use request data to build bean names and query the container.
- **Dynamic selection belongs in a typed resolver/registry.** Inject implementation collections instead of asking the context for arbitrary beans.
- **Optional and lazy must reflect real needs.** Use `Optional` or `ObjectProvider` when absence or deferral is intentionally designed.
- **Context lookups should stay confined to infrastructure boundaries that need them.** When unavoidable, wrap them in an adapter with a narrow API.
- **Do not use Service Locator to hide an overloaded class.** A long constructor is feedback to re-examine design.
- **Test at the right layer.** Unit test logic using Java constructors; integration test Spring wiring and configuration.

## Conclusion

Spring `ApplicationContext` can look up beans, yet that ability should not become the default way business services fetch collaborators. **Keeping dependencies explicit** with constructor injection lets readers see object structure, lets the container validate required dependencies at initialization, and allows unit tests to run without depending on the full Spring context.

When you need dynamic selection, multiple implementations, optional dependencies, or deferred instantiation, express that requirement using a typed resolver, registry, factory, `Optional`, or `ObjectProvider`. If accessing `ApplicationContext` is truly necessary, keep it inside an infrastructure boundary with clear responsibility. That lets the container do its job of assembling the object graph, while business code stays focused on the rules and behavior the application needs to deliver.
