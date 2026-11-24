# Do not use configuration ordering to hide circular dependencies in Spring Boot design

## 1. The problem to solve

When a Spring Boot application has two beans that depend on each other, changing auto-configuration order usually only changes when Spring registers bean definitions. It does not remove the dependency relationship between the two objects.

Example:
- `OrderService` needs `PaymentService` to pay for an order.
- `PaymentService` in turn needs `OrderService` to update the order status.

This is a circular dependency in the design. If both use constructor injection, Spring cannot create either bean first because each constructor requires the other bean. The application can fail with `BeanCurrentlyInCreationException` or an `UnsatisfiedDependencyException` whose root cause is a circular reference.

A common mistaken fix is tweaking `@AutoConfigureBefore`, `@AutoConfigureAfter`, `@AutoConfigureOrder`, or `@DependsOn` until the application starts. These APIs have specific purposes around processing and initialization order; they do not replace redesigning the dependency graph.

The goal of this article is to clearly distinguish configuration processing order, bean creation order, and business dependency relationships; then choose how to refactor so components have clear responsibilities and the dependency graph is acyclic.

## 2. Distinguish three kinds of ordering in Spring

Three concepts are often lumped together:

| Concept | What is Spring ordering? | Typical mechanism |
| --- | --- | --- |
| Configuration discovery | Which auto-configurations are found and fed into the import process | `AutoConfiguration.imports`, `@EnableAutoConfiguration` |
| Bean definition registration | Which configuration is processed first to register metadata/bean definitions | `@AutoConfigureBefore`, `@AutoConfigureAfter`, `@AutoConfigureOrder` |
| Bean creation and initialization | Which bean must be created first because another bean needs it | Constructor/method injection, dependency graph, `@DependsOn` |

The first two layers relate to configuration processing. The third layer relates to the container actually instantiating objects.

For example, Spring can process `PaymentAutoConfiguration` before `OrderAutoConfiguration` to register bean definitions. However, if `PaymentService`'s constructor requires `OrderService` and `OrderService`'s constructor requires `PaymentService`, the dependency graph still contains a cycle.

## 3. What do @AutoConfigureBefore, @AutoConfigureAfter, and @AutoConfigureOrder do?

Spring Boot provides annotations to control the application order of auto-configurations:

- `@AutoConfigureBefore(OtherAutoConfiguration.class)` requests that the current auto-configuration be applied before the specified configuration.
- `@AutoConfigureAfter(OtherAutoConfiguration.class)` requests that the current auto-configuration be applied after the specified configuration.
- `@AutoConfigureOrder(100)` sets relative ordering between auto-configurations without needing direct references to one another.
- `@AutoConfiguration(before = ..., after = ...)` provides the corresponding attributes directly on the `@AutoConfiguration` annotation.

Key point in the Spring Boot 3.3 documentation: auto-configuration application order only affects the order in which bean definitions are registered. Subsequent bean creation order is still determined by each bean's dependencies and `@DependsOn` relationships.

Example of a web integration configuration that must be applied after Spring MVC configuration:

~~~java
@AutoConfiguration(after = WebMvcAutoConfiguration.class)
public class WidgetWebAutoConfiguration {
    // Spring MVC integration beans
}
~~~

This is a valid reason to use ordering: the configuration must be processed after another auto-configuration. It is not a fix for a circular dependency between services.

Do not use ordering annotations as a trick to force bean A to initialize before bean B when A and B require each other in their constructors.

## 4. Model the dependency graph

Represent each bean as a vertex and each dependency as a directed edge. If bean A requires bean B, draw edge A → B.

A design without circular dependencies can be represented as a directed acyclic graph (DAG):

~~~mermaid
flowchart TD
    A["OrderService"] --> B["PaymentProcessor"]
    A --> C["OrderRepository"]
    B --> D["PaymentGateway"]
~~~

A design with a circular dependency:

~~~mermaid
flowchart LR
    A["OrderService"] --> B["PaymentService"]
    B --> A
~~~

Changing configuration registration order cannot delete edge A → B or B → A. To resolve the cycle, you must change the responsibility relationship or how the components communicate.

This perspective is also useful outside Spring: a circular dependency is often a sign that two modules know too much about each other, or that a use case's responsibilities are split in the wrong place.

## 5. Example of a design with a circular dependency

The following two services constructor-depend on each other:

~~~java
@Service
public class OrderService {

    private final PaymentService paymentService;

    public OrderService(PaymentService paymentService) {
        this.paymentService = paymentService;
    }

    public void markPaid(String orderId) {
        // Update order status
    }
}
~~~

~~~java
@Service
public class PaymentService {

    private final OrderService orderService;

    public PaymentService(OrderService orderService) {
        this.orderService = orderService;
    }

    public void charge(String orderId) {
        // Execute payment
        orderService.markPaid(orderId);
    }
}
~~~

Dependency graph:

- Creating `OrderService` requires `PaymentService`.
- Creating `PaymentService` requires `OrderService`.
- There is no valid starting point for the constructor initialization chain.

This is not a missing-order issue between two configuration classes. It reflects that `PaymentService` is both handling payment and driving order status through another service.

A design smell to watch for is service A calling service B to do work, and B calling back into A to complete the same use case. Usually there should be a single component orchestrating that use case.

## 6. Why does changing configuration order fail to fix the cycle?

Suppose we try:

~~~java
@AutoConfiguration
@AutoConfigureBefore(OrderAutoConfiguration.class)
public class PaymentAutoConfiguration {
}
~~~

Or switch it to `@AutoConfigureAfter`. Spring can change the order in which configuration classes are processed, but when instantiating singletons, the container still must resolve dependencies declared in constructors, fields, setters, or `@Bean` method parameters.

With cycle A → B → A:

1. Spring needs to create A.
2. A's constructor requires B.
3. Spring starts creating B.
4. B's constructor requires A.
5. A is still currently in creation and cannot finish its constructor.
6. The container detects an unresolvable circular reference under constructor injection.

No configuration ordering turns this sequence into a valid object creation sequence. Changing ordering can cause bean registration conditions to be evaluated at a different point, but it does not change the runtime requirements of the two constructors.

## 7. @DependsOn is not a circular-dependency breaker

`@DependsOn` declares that the current bean depends on one or more other beans being initialized before it. It is useful when ensuring an initialization side effect has already happened, such as a bean registering a driver or preparing a global resource before another bean.

Example:

~~~java
@Component
@DependsOn("databaseDriverRegistrar")
public class DatabaseHealthProbe {
    // Requires driver registrar to be initialized first
}
~~~

`@DependsOn` does not pass collaborators into constructors and does not eliminate business dependencies between two services. If A depends on B and B depends on A, adding `@DependsOn` on both sides only adds extra ordering constraints without fixing the cycle.

Use `@DependsOn` only when there is an explicit initialization requirement that ordinary dependency injection cannot express, typically side-effect ordering. If a bean needs to call methods on another bean during normal operation, declare that collaborator via constructor or factory method parameters.

## 8. Refactor by choosing a use-case orchestrator

An often effective fix is identifying which service owns the use case and letting that service coordinate the steps.

In the payment example:
- `OrderService` owns the order-payment use case.
- `OrderService` calls `PaymentProcessor` to process the payment.
- `PaymentProcessor` returns the payment result.
- `OrderService` updates the order based on that result.
- `PaymentProcessor` does not need to call back into `OrderService`.

New dependency graph:

~~~mermaid
flowchart TD
    A["OrderService"] --> B["PaymentProcessor"]
    A --> C["OrderRepository"]
    B --> D["PaymentGateway"]
~~~

Example contracts:

~~~java
public interface PaymentProcessor {
    PaymentReceipt charge(Order order);
}
~~~

~~~java
public record PaymentReceipt(String transactionId, boolean successful) {
}
~~~

Orchestrating service:

~~~java
@Service
public class OrderService {

    private final PaymentProcessor paymentProcessor;
    private final OrderRepository orderRepository;

    public OrderService(
            PaymentProcessor paymentProcessor,
            OrderRepository orderRepository) {
        this.paymentProcessor = paymentProcessor;
        this.orderRepository = orderRepository;
    }

    public void pay(String orderId) {
        Order order = orderRepository.findById(orderId)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Order not found: " + orderId));

        PaymentReceipt receipt = paymentProcessor.charge(order);

        if (receipt.successful()) {
            order.markPaid(receipt.transactionId());
            orderRepository.save(order);
        }
    }
}
~~~

The payment implementation does only its own job:

~~~java
@Service
public class DefaultPaymentProcessor implements PaymentProcessor {

    private final PaymentGateway paymentGateway;

    public DefaultPaymentProcessor(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }

    @Override
    public PaymentReceipt charge(Order order) {
        return paymentGateway.charge(order.id(), order.total());
    }
}
~~~

After refactoring:
- `OrderService` can coordinate multiple steps of the use case.
- `PaymentProcessor` only needs order data and the payment gateway.
- The payment result is returned as a value object.
- There is no reverse dependency from payment back to the order service.

This is usually the easiest solution to test when payment is a synchronous step of the order use case.

## 9. Standalone Java 17+ example after refactoring

The program below models the same idea without Spring, a database, or external libraries. It shows a unidirectional dependency: `OrderService` depends on the `PaymentProcessor` interface.

File `OrderPaymentDemo.java`:

~~~java
import java.math.BigDecimal;
import java.util.Objects;

public class OrderPaymentDemo {

    record Order(String id, BigDecimal total) {
    }

    record PaymentReceipt(String transactionId, boolean successful) {
    }

    interface PaymentProcessor {
        PaymentReceipt charge(Order order);
    }

    static final class FakePaymentProcessor implements PaymentProcessor {

        @Override
        public PaymentReceipt charge(Order order) {
            return new PaymentReceipt("TX-42", true);
        }
    }

    static final class OrderService {

        private final PaymentProcessor paymentProcessor;

        OrderService(PaymentProcessor paymentProcessor) {
            this.paymentProcessor = Objects.requireNonNull(paymentProcessor);
        }

        String pay(Order order) {
            PaymentReceipt receipt = paymentProcessor.charge(order);
            if (!receipt.successful()) {
                return "Payment failed for " + order.id();
            }
            return "Order " + order.id() + " paid: " + receipt.transactionId();
        }
    }

    public static void main(String[] args) {
        PaymentProcessor processor = new FakePaymentProcessor();
        OrderService orderService = new OrderService(processor);

        Order order = new Order("ORD-42", new BigDecimal("125.00"));
        System.out.println(orderService.pay(order));
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac OrderPaymentDemo.java
java OrderPaymentDemo
~~~

Exact stdout:

~~~text
Order ORD-42 paid: TX-42
~~~

The example creates no Spring beans. It demonstrates that the core design works independently of the container: a use-case service receives its collaborator through its constructor and coordinates work in one direction.

## 10. Use interfaces and dependency inversion properly

Interfaces can invert dependencies between modules, but adding an interface alone may not break a cycle.

Example:
- The order module defines `PaymentProcessor` as a port needed by the use case.
- The payment adapter implements `PaymentProcessor`.
- `OrderService` depends on the port.
- The adapter depends on the external gateway.

The module graph becomes clearer:

~~~mermaid
flowchart LR
    A["Order application"] --> B["PaymentProcessor port"]
    C["Payment adapter"] -. "implements" .-> B
    C --> D["External payment gateway"]
~~~

If the adapter still injects `OrderService` back to update the order, the cycle was merely moved across another interface or module. Dependency inversion works when the dependency direction genuinely changes and the contract does not pull the high-level module back into the low-level module.

During review, inspect imports, constructors, factory methods, and module dependencies. Good interface names are not enough; the actual dependency graph determines whether the architecture is acyclic.

## 11. When should events be used to decouple two sides?

If a service needs to notify another part of a result without calling it directly or receiving an immediate return value, application/domain events can decouple both sides.

Example payment service publishing an event:

~~~java
public record PaymentCompleted(String orderId, String transactionId) {
}
~~~

~~~java
@Service
public class PaymentService {

    private final ApplicationEventPublisher events;

    public PaymentService(ApplicationEventPublisher events) {
        this.events = events;
    }

    public void charge(String orderId) {
        String transactionId = "TX-42";
        events.publishEvent(
                new PaymentCompleted(orderId, transactionId));
    }
}
~~~

A listener in the order component handles the event:

~~~java
@Component
public class PaymentCompletedHandler {

    private final OrderRepository orders;

    public PaymentCompletedHandler(OrderRepository orders) {
        this.orders = orders;
    }

    @EventListener
    public void on(PaymentCompleted event) {
        Order order = orders.findById(event.orderId())
                .orElseThrow();
        order.markPaid(event.transactionId());
        orders.save(order);
    }
}
~~~

Dependency graph:
- Payment service depends on `ApplicationEventPublisher`.
- Handler depends on `OrderRepository`.
- Payment service does not need to know about `OrderService` or specific handlers.

In Spring, `ApplicationEventPublisher` publishes events in-process by default; listeners are synchronous unless configured async. If processing must happen only after transaction commit, look at `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` and ensure the event is published inside an appropriate transaction.

Events are useful when the relationship is a one-way notification. Do not use events for every simple service call because they make execution flow and error tracking harder when that decoupling is unnecessary.

## 12. @Lazy and ObjectProvider should only be used for genuine deferral needs

Spring provides several mechanisms to defer dependency resolution:

- `@Lazy` on an injection point creates a proxy so the dependency is resolved when used.
- `ObjectProvider<T>` lets you fetch a bean on demand, check optional beans, or defer calling `getObject()`.
- `ObjectFactory<T>` also provides a way to retrieve objects when needed.

Example:

~~~java
@Service
public class ReportService {

    private final ObjectProvider<ExportClient> exportClientProvider;

    public ReportService(
            ObjectProvider<ExportClient> exportClientProvider) {
        this.exportClientProvider = exportClientProvider;
    }

    public void exportWhenEnabled(Report report) {
        ExportClient client = exportClientProvider.getIfAvailable();
        if (client != null) {
            client.export(report);
        }
    }
}
~~~

This is a valid case if export is an optional dependency or only needed in a rarely executed branch.

If `@Lazy` or `ObjectProvider` is used merely to mask A calling B and B calling A, the circular dependency still exists in the design. When methods are invoked, failures may appear later; back-and-forth calls can also cause recursion or unready object states.

Practical rule:
- Use deferral when a dependency is genuinely optional, heavy, or only needed later.
- Use interfaces/events/orchestrators when the dependency direction needs fixing.
- Do not use lazy proxies as a substitute for splitting responsibilities.

## 13. Setter injection is not a default architectural solution

Spring can resolve some circular references between singleton beans using setter or field injection via early references. However:
- A bean may be injected into another bean before finishing initialization.
- Incomplete state may be observed.
- Constructors no longer reveal all required dependencies.
- Unit tests are harder to construct in a valid state when dependencies are assigned later.
- Certain initialization paths, proxies, or lifecycles may be incompatible with that cycle resolution.

Spring recommends constructor injection for required dependencies. Setter/configuration methods fit optional dependencies with sensible defaults better.

Spring Boot disallows automatic circular reference resolution by default. The property `spring.main.allow-circular-references` defaults to `false`. Enabling it can allow some setter/field cycles to run, but does not improve the design graph and cannot resolve unconstructable constructor cycles.

Do not convert an entire application to setter injection just to bypass startup errors. Identify the backward dependency edge and refactor.

## 14. Use auto-configuration ordering in the right cases

Ordering remains very important in auto-configuration libraries, especially when conditions depend on already registered bean definitions.

For example, a metrics configuration needs to observe the `DataSource` bean created by Spring Boot JDBC auto-configuration:

~~~java
@AutoConfiguration(after = DataSourceAutoConfiguration.class)
public class JdbcMetricsAutoConfiguration {

    @Bean
    @ConditionalOnBean(DataSource.class)
    JdbcMetricsReporter jdbcMetricsReporter(DataSource dataSource) {
        return new JdbcMetricsReporter(dataSource);
    }
}
~~~

Here `after` serves a clear purpose:
1. Spring processes the datasource auto-configuration first.
2. The `DataSource` bean definition is registered.
3. The `@ConditionalOnBean(DataSource.class)` condition can inspect the existing bean definition.
4. If the condition matches, the reporter is registered.

Ordering is appropriate because it lets the condition see bean definitions from another configuration. When the reporter is created, the `DataSource` dependency is still resolved via the `@Bean` method parameter.

Do not use ordering to make two auto-configurations contain services whose constructors depend on each other. If one configuration only applies after the other registers a bean, use ordering for the condition; if two beans depend cyclically, refactor the bean graph.

## 15. @Bean method parameters express dependencies more clearly than direct method calls

In Java configuration, `@Bean` method parameters are dependencies the container must supply:

~~~java
@Configuration(proxyBeanMethods = false)
public class OrderConfiguration {

    @Bean
    PaymentProcessor paymentProcessor(PaymentGateway paymentGateway) {
        return new DefaultPaymentProcessor(paymentGateway);
    }

    @Bean
    OrderService orderService(
            PaymentProcessor paymentProcessor,
            OrderRepository orderRepository) {
        return new OrderService(paymentProcessor, orderRepository);
    }
}
~~~

This approach lets Spring manage dependency resolution and create beans according to proper bean definitions.

Avoid directly calling another `@Bean` method as a way to obtain an instance:

~~~java
@Bean
OrderService orderService() {
    return new OrderService(paymentProcessor(null));
}
~~~

This is a bad example because it passes an inappropriate argument and bypasses container dependency resolution. In a `proxyBeanMethods = false` configuration, method calls are plain Java calls and are not intercepted to retrieve beans from the container. Use method parameters to express relationships.

When a configuration class starts cross-calling multiple factory methods, review whether the dependencies can be expressed explicitly via parameters.

## 16. Testing to catch circular dependencies early

A test context should verify the application can instantiate the beans after refactoring. For auto-configuration, `ApplicationContextRunner` builds a lightweight context:

~~~java
class OrderPaymentAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    OrderPaymentAutoConfiguration.class));

    @Test
    void createsOrderAndPaymentBeansWithoutCircularDependency() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(OrderService.class);
            assertThat(context).hasSingleBean(PaymentProcessor.class);
        });
    }
}
~~~

This test fits when `OrderPaymentAutoConfiguration` is a real auto-configuration registering the required beans. If the configuration uses prerequisite beans, add the corresponding user configuration/properties to the runner.

Beyond context tests:
- Unit test `OrderService` with a fake `PaymentProcessor` to verify orchestration.
- Integration test to verify transactions or event listeners update state correctly.
- Test application startup with `@SpringBootTest` to verify configurations work together.
- When changing module boundaries, consider ArchUnit or dependency graph checks to catch reverse dependencies.

Do not assert only that the context starts. Test critical behavior and verify dependencies do not loop back through another service.

## 17. Anti-patterns and how to fix them

| Anti-pattern | Why it does not solve the root cause | Recommended fix |
| --- | --- | --- |
| Switching `@AutoConfigureBefore` to `@AutoConfigureAfter` to cure a constructor cycle | Only changes bean definition registration order | Refactor the dependency graph |
| Adding `@DependsOn` to both beans | Adds initialization constraints without removing the reverse dependency | Choose an orchestrator or split responsibilities |
| Enabling `spring.main.allow-circular-references=true` | Allows some setter/field cycles via early references | Keep required dependencies in constructors and fix the design |
| Converting all constructors to setters | Hides required dependencies and can expose incomplete beans | Use constructor injection; split collaborators |
| Adding `@Lazy` to every cyclic dependency | Defers errors or initialization without removing the cycle | Use lazy only when deferral is genuinely needed |
| Wrapping a service in an interface while the implementation still calls back | Changes reference type while preserving the cycle | Invert module dependencies and remove reverse callbacks |
| Creating extra configuration classes to cross-call beans | Adds classes without changing the dependency graph | Pass dependencies via `@Bean` parameters or the owning service |
| Using events for every synchronous call | Makes flow harder to follow without decoupling benefits | Use events only for appropriate one-way notifications |

## 18. Design review checklist

Before adding or changing ordering, ask yourself:

1. Am I ordering auto-configuration so a condition sees a bean definition, or trying to control when a service is instantiated?
2. Does bean A need bean B in its constructor while B needs A?
3. Is any service both orchestrating a use case and being called back by a lower-level service?
4. Can a single orchestrator be chosen to coordinate the flow?
5. Can results be returned via a return value/value object instead of a reverse callback?
6. If the relationship is a one-way notification, is an event cleaner than a direct service call?
7. Does a new interface genuinely reverse the dependency direction between modules?
8. Is the dependency genuinely optional/lazy, or are `@Lazy`/`ObjectProvider` merely hiding a cycle?
9. Is `@DependsOn` expressing real initialization side effects or just patching an injection failure?
10. Do context tests verify both startup and business behavior after refactoring?
11. Is `spring.main.allow-circular-references=true` accidentally masking errors?
12. Is ordering clearly documented with which condition or auto-configuration must run before/after?

## 19. Knowledge self-check

1. What order does `@AutoConfigureAfter` control? **Auto-configuration application and bean definition registration order.**
2. In what order are beans created? **According to the dependency graph and explicit initialization relationships such as `@DependsOn`.**
3. Can changing `@AutoConfigureBefore` break a constructor cycle? **No; the constructor dependency relationship still remains.**
4. What error does a constructor cycle A → B → A typically produce? **`BeanCurrentlyInCreationException` or a dependency error caused by a circular reference.**
5. When is `@DependsOn` appropriate? **Ensuring a bean with initialization side effects runs before another bean.**
6. Why is constructor injection helpful during reviews? **It makes required dependencies explicit and constructs objects in a complete state.**
7. Does `@Lazy` remove a dependency cycle? **No; it defers dependency resolution.**
8. When is `ObjectProvider<T>` useful? **When a dependency is optional or needs to be fetched on demand at a later point.**
9. When are events appropriate? **When a component needs to emit a one-way notification without calling the receiving service directly.**
10. Why is ordering useful with `@ConditionalOnBean`? **The prerequisite bean definition must be registered before the condition is evaluated.**
11. What is the default of `spring.main.allow-circular-references` in Spring Boot 3.3? **`false`.**
12. What is the first step when discovering two services calling each other? **Identify the service owning the use case and redesign orchestration/dependency direction.**

## Official references

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): auto-configuration application order, bean definition ordering, conditions, and dependency notes.
- [Spring Boot 3.3.13 — `@AutoConfigureBefore` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureBefore.html): purpose and limits of ordering.
- [Spring Boot 3.3.13 — `@AutoConfigureAfter` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureAfter.html): auto-configuration application order.
- [Spring Boot 3.3.13 — `@AutoConfigureOrder` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureOrder.html): relative ordering between auto-configurations.
- [Spring Boot 3.3.13 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): default of `spring.main.allow-circular-references`.
- [Spring Framework — Dependency Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html): constructor/setter injection, dependency resolution, and circular dependencies.
