# Calling Business Services from Functions and Managing Dependencies

In a Spring Cloud Stream application, a `Supplier`, `Function`, or `Consumer` serves as the entry or exit point for messages. The function should focus on translating message data into a business invocation and converting business results into output messages. Rules such as order validation, fee calculation, inventory updates, and persistence should live in Spring-managed business services.

This structure keeps event-processing code easy to test and loosely coupled to Kafka, RabbitMQ, or Pulsar. Spring Dependency Injection supplies the required services to function beans; Spring Cloud Stream manages bindings and binders to deliver messages to those functions. Keeping a clear boundary between message adapters and business services allows changing brokers or test approaches with minimal impact on core logic.

## 1. Dividing Responsibilities Between Function and Service

An event-processing flow typically follows these steps:

1. The binder receives a message from a destination and converts the payload into the Java type declared by the function.
2. Spring Cloud Stream invokes the configured function.
3. The function reads the required payload and metadata, then calls the business service.
4. The service executes business rules, accesses repositories, or calls dependent ports.
5. If it is a `Function`, the result is returned so the framework can emit an output message; if it is a `Consumer`, the function finishes after its processing work.
6. The binder sends or acknowledges the message according to the broker configuration.

The function is an adapter at the system boundary. The service is where business actions are expressed. For example, an `acceptOrder` function can receive `OrderCreated` and invoke `OrderApplicationService.accept()`. The service decides whether the order is valid, persists state, and produces the business result.

Avoid placing all database queries, business calculations, multiple API calls, and transaction handling directly inside the function lambda. The shorter the lambda, the easier it is to read, test, and reuse from a REST controller, scheduler, or another processing flow.

## 2. Declaring Business Services with Spring

Spring manages components such as services and repositories through the ApplicationContext. You can annotate business classes with `@Service` and use constructor injection to declare mandatory dependencies.

Example of a service that accepts an order:

```java
@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;

    public OrderApplicationService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public OrderAccepted accept(OrderCreated event) {
        return accept(event, null, null);
    }

    @Transactional
    public OrderAccepted accept(
            OrderCreated event, String eventId, String correlationId) {
        if (event.orderId() == null || event.orderId().isBlank()) {
            throw new InvalidOrderException("orderId is required");
        }

        Order order = Order.create(
            event.orderId(),
            event.customerId(),
            event.items()
        );

        // eventId/correlationId can be used for audit and idempotency.
        orderRepository.save(order);

        return new OrderAccepted(order.id(), "ACCEPTED");
    }
}
```

This example assumes the project already defines `OrderCreated`, `OrderAccepted`, `Order`, `OrderRepository`, and `InvalidOrderException`. The service receives an event object already converted into a Java type; it does not need to know whether the message arrived from a Kafka topic or a RabbitMQ queue.

Constructor injection offers several benefits:

- Mandatory dependencies are explicit in the constructor.
- Fields can be declared `final`, preventing an object from existing without required dependencies.
- Unit tests can instantiate the service easily with mock or fake repositories.
- Spring can validate and resolve dependencies when creating beans.

With a single constructor, Spring automatically uses that constructor for dependency injection without needing `@Autowired`. When multiple constructors exist, specify which constructor or factory method Spring should use.

Do not call `new OrderApplicationService(...)` inside a function if the service relies on transactions, caching, security, or other Spring proxies. Instantiating objects manually bypasses Spring's lifecycle and bean management mechanisms.

## 3. Injecting Services into Functions via @Bean Parameters

A common way to declare a function is via a bean in a `@Configuration` class. Spring can inject services directly into the parameters of the `@Bean` method.

```java
@Configuration
public class OrderFunctions {

    @Bean
    public Function<OrderCreated, OrderAccepted> acceptOrder(
            OrderApplicationService orderService) {

        return orderService::accept;
    }
}
```

The `acceptOrder` method returns a `Function<OrderCreated, OrderAccepted>`. Spring resolves `OrderApplicationService` from the ApplicationContext and passes it to the factory method. The function receives the event and delegates processing to the service.

If you need boundary data mapping or an extra adapter step, replace the method body above with a lambda:

```java
@Bean
public Function<OrderCreated, OrderAccepted> acceptOrder(
        OrderApplicationService orderService) {

    return event -> {
        // Perform boundary-only conversion here if needed.
        return orderService.accept(event);
    };
}
```

Both styles share the same goal. A method reference is concise when the function simply forwards the call; a lambda is useful when you need boundary validation, type mapping, or metadata enrichment. Business rules should still reside in the service.

When Spring Cloud Stream discovers the function bean, the bean name can be selected through configuration:

```yaml
spring:
  cloud:
    function:
      definition: acceptOrder
    stream:
      bindings:
        acceptOrder-in-0:
          destination: orders.created
          group: order-service
        acceptOrder-out-0:
          destination: orders.accepted
```

The input binding `acceptOrder-in-0` connects to the `orders.created` destination; the output binding `acceptOrder-out-0` connects to `orders.accepted`. The active binder maps the destination and group to broker resources. The function does not need to create Kafka/RabbitMQ consumers or producers directly.

With a `Consumer<OrderCreated>`, there is only an input binding. With a `Supplier<OrderCreated>`, the function produces output data and is typically invoked by the framework according to the configured poller. Injecting services via `@Bean` parameters applies to these function types as well:

```java
@Bean
public Consumer<PaymentReceived> recordPayment(
        PaymentApplicationService paymentService) {
    return paymentService::record;
}
```

The snippet above illustrates another function; in a real application, select the corresponding function definition and configure bindings for the deployed bean.

## 4. Injecting Services via a Function Component Constructor

Besides factory methods, you can declare a class that directly implements `Consumer` or `Function` and inject services through its constructor. This is useful when the adapter has multiple processing steps or needs its own class structure.

```java
@Component("recordPayment")
public class RecordPaymentFunction
        implements Consumer<PaymentReceived> {

    private final PaymentApplicationService paymentService;

    public RecordPaymentFunction(
            PaymentApplicationService paymentService) {
        this.paymentService = paymentService;
    }

    @Override
    public void accept(PaymentReceived event) {
        paymentService.record(event);
    }
}
```

Spring creates the `recordPayment` bean and injects `PaymentApplicationService`. Spring Cloud Function recognizes the bean by its functional interface type; Spring Cloud Stream can select the function by name:

```yaml
spring:
  cloud:
    function:
      definition: recordPayment
    stream:
      bindings:
        recordPayment-in-0:
          destination: payments.received
          group: payment-service
```

Do not simultaneously declare another `@Bean Consumer` with the same functionality and the same name. Choose one registration approach per bean to avoid naming conflicts or confusing configuration.

### Choosing Between @Bean and Component

| Criterion | Function from @Bean Method | @Component Class Implementing Function/Consumer |
|---|---|---|
| Declaration | Factory method returning a functional interface | Class directly implementing the interface |
| Service injection | `@Bean` method parameters | Constructor |
| Best suited for | Short adapters delegating to a service | Adapters with structure or multiple boundary steps |
| Testing | Call factory method and execute the returned function | Instantiate component with mock service or load bean from context |
| Function name | `@Bean` method name | Component/bean name |

Both approaches use Spring Dependency Injection and can be recognized by Spring Cloud Function. Which one you choose depends on adapter complexity and project conventions.

## 5. Managing Multiple Service Dependencies

A function sometimes needs to coordinate several actions: checking customer eligibility, reserving inventory, calculating fees, and recording the order. You can inject multiple services directly into a `@Bean` method, but if the function starts orchestrating multiple business steps, create a dedicated application service or use case instead.

Example:

```java
@Service
public class CheckoutService {

    private final CustomerService customerService;
    private final InventoryService inventoryService;
    private final OrderRepository orderRepository;

    public CheckoutService(
            CustomerService customerService,
            InventoryService inventoryService,
            OrderRepository orderRepository) {
        this.customerService = customerService;
        this.inventoryService = inventoryService;
        this.orderRepository = orderRepository;
    }

    public OrderAccepted checkout(OrderCreated event) {
        customerService.assertCanOrder(event.customerId());
        inventoryService.reserve(event.items());

        Order order = Order.create(
            event.orderId(),
            event.customerId(),
            event.items()
        );

        orderRepository.save(order);
        return new OrderAccepted(order.id(), "ACCEPTED");
    }
}
```

The function only needs a single coordinating dependency:

```java
@Bean
Function<OrderCreated, OrderAccepted> checkout(
        CheckoutService checkoutService) {
    return checkoutService::checkout;
}
```

This structure keeps the function in its adapter role while the service expresses the use case. Sub-services can be reused across other flows. When a use case spans multiple systems, clearly define transaction boundaries and compensation strategies in case one step succeeds and a subsequent step fails.

Avoid creating a catch-all service just to bundle every dependency without a cohesive business responsibility. Group operations around a use case with a clear name and purpose.

## 6. Passing Payload and Metadata to Services

A function can accept the payload directly:

```java
@Bean
Consumer<OrderCreated> recordOrder(OrderApplicationService service) {
    return event -> service.accept(event);
}
```

If the adapter needs to read headers such as event ID or correlation ID, declare the input as `Message<T>`:

```java
@Bean
Consumer<Message<OrderCreated>> recordOrder(
        OrderApplicationService service) {

    return message -> {
        OrderCreated event = message.getPayload();
        String eventId = (String) message.getHeaders().get("eventId");
        String correlationId =
            (String) message.getHeaders().get("correlationId");

        service.accept(event, eventId, correlationId);
    };
}
```

In this example, the adapter extracts information from the message envelope into use-case parameters. The service receives the data needed for business logic without depending on `MessageHeaders`, `MessageChannel`, or binder APIs.

Distinguish technical metadata from business data. Correlation ID can be used to trace a processing flow; event ID can be used to prevent duplicate processing. If the event ID is part of an idempotency rule, pass it to the service or a dedicated component. Do not pass the entire header map into the service merely because it is available.

When a function creates an output message, it can construct new headers:

```java
@Bean
Function<Message<OrderCreated>, Message<OrderAccepted>> acceptOrder(
        OrderApplicationService service) {

    return input -> {
        OrderAccepted result = service.accept(input.getPayload());

        return MessageBuilder
            .withPayload(result)
            .setHeader("correlationId",
                input.getHeaders().get("correlationId"))
            .build();
    };
}
```

Forward only the necessary headers. Binders may apply their own header mapping rules; test against a real broker if headers are part of the integration contract.

## 7. Managing Transactions and Errors When Calling Services

Business services are usually the right place to define transactions for database operations. For example, `@Transactional` on `OrderApplicationService.accept()` establishes a Spring-managed transaction boundary when the function invokes the service bean through its proxy.

For transactions to work properly:

- The service must be managed by Spring as a bean.
- Invocations must pass through the configured transaction proxy.
- Database operations must participate in the appropriate transaction manager.
- Rollback rules must be understood, especially for checked exceptions vs. runtime exceptions under your transaction settings.

Separating the service into its own bean also prevents a common pitfall: self-invocation. If a method on the same object directly calls another `@Transactional` method on itself, that internal call may bypass the proxy and fail to start a transaction as expected.

### Letting Errors Reach the Binder's Error Handling

If a service throws an exception while processing a message, the function should generally let the exception propagate so the framework/binder can apply the configured error-handling mechanism. Avoid catching every exception only to ignore it or return a dummy result, because the message may then be treated as processed successfully.

Classify errors by nature:

- Transient errors, such as brief database or downstream service disconnects, may be suitable for retries.
- Data or business-rule errors that retries cannot fix typically belong in a non-retry error policy or a DLQ/DLT.
- Programming bugs must be logged, monitored, and fixed in the application.

Retries and DLQs are configured at the binder/broker level; calling a service does not create a retry policy on its own. If the broker redelivers a message, the service may be called multiple times. Write operations must be idempotent or backed by deduplication using an event ID or business key.

### Database Transactions Do Not Automatically Span the Broker

A database transaction opened by a service does not automatically encompass Kafka offset commits or RabbitMQ message acknowledgments. If the database commits successfully but the process fails before the broker records completion, the message can be redelivered. Conversely, if a message is acknowledged before business data is persisted, the event can appear lost from the consumer's perspective.

For flows requiring consistency between a database and a broker, consider the transactional outbox pattern, inbox/deduplication, or broker-supported integrated transactions. Evaluate the exact guarantee scope of your binder and broker; do not assume `@Transactional` on a service creates a distributed transaction.

## 8. Managing State and Thread Safety of Function Beans

Spring beans default to singleton scope unless another scope is specified. A function bean is created once and may be invoked many times over the application's lifetime. Depending on the binder, concurrency, and consumer configuration, multiple messages may be processed concurrently.

Therefore, functions should avoid storing per-message state in fields:

```java
// Avoid: data from concurrent or consecutive invocations can overwrite each other.
@Component
class UnsafeOrderFunction implements Consumer<OrderCreated> {

    private OrderCreated currentOrder;

    @Override
    public void accept(OrderCreated event) {
        this.currentOrder = event;
        // Further processing based on this mutable field.
    }
}
```

Use local variables per invocation and keep business state in the database or a properly synchronized storage component:

```java
@Component
class SafeOrderFunction implements Consumer<OrderCreated> {

    private final OrderApplicationService service;

    SafeOrderFunction(OrderApplicationService service) {
        this.service = service;
    }

    @Override
    public void accept(OrderCreated event) {
        service.accept(event);
    }
}
```

Shared services and dependencies must also be safe under concurrent invocation. Spring repositories are generally designed for use through bean proxies, but mutable business objects, custom caches, or custom clients still require review. Never create a shared object to hold the currently processing payload without proper synchronization and a clear reason.

If you need to limit concurrent message processing, configure concurrency or resource limits at the binder/container layer according to the broker. Do not use instance fields on a function to throttle message volume manually.

## 9. Testing Functions and Dependency Injection

Test service logic, function behavior, and Spring dependency wiring separately.

### Unit Testing the Function

You can invoke the `@Bean` method directly with a mocked service, then execute the function:

```java
class OrderFunctionsTest {

    @Test
    void delegatesOrderToApplicationService() {
        OrderApplicationService service =
            mock(OrderApplicationService.class);

        OrderFunctions functions = new OrderFunctions();

        Function<OrderCreated, OrderAccepted> function =
            functions.acceptOrder(service);

        OrderCreated event = new OrderCreated("order-42");
        OrderAccepted expected =
            new OrderAccepted("order-42", "ACCEPTED");

        when(service.accept(event)).thenReturn(expected);

        OrderAccepted actual = function.apply(event);

        assertThat(actual).isEqualTo(expected);
        verify(service).accept(event);
    }
}
```

This unit test verifies that the function forwards the event to the service and returns the result. It does not need to start a Spring context or a broker.

### Unit Testing the Service

The service should be tested independently of the binder. Mock repositories or external dependencies to verify business rules: invalid data is rejected, valid orders are saved, and expected results are returned. If transactions are used, add integration tests with appropriate persistence configuration to verify commit and rollback behavior.

### Testing the Spring Context

A `@SpringBootTest` can verify that function beans are registered, services are injected, and the function definition resolves properly. If testing bindings as well, the Spring Cloud Stream Test Binder can send messages into bindings and read output messages in memory.

The Test Binder does not verify database transactions, offsets, acknowledgments, retries, or DLQs on a real broker. For broker-dependent behaviors, write integration tests with real Kafka, RabbitMQ, or Pulsar, typically via Testcontainers.

## 10. Checklist When Designing Functions That Call Services

- Keep the function focused on its adapter role: receive payload/headers, invoke the use case, and map any result to the output.
- Declare business services as Spring beans and inject them via constructor or `@Bean` parameters.
- Do not instantiate services with `new`, and do not use a static ApplicationContext to pull dependencies.
- Place transactions on the service/use case aligned with the data boundaries to protect.
- Let appropriate exceptions propagate to the binder; never silently turn errors into success.
- Design processing to be idempotent because messages may be redelivered.
- Avoid storing per-message data in mutable fields of singleton function beans.
- Test functions and services independently; test wiring, bindings, and broker behavior in separate layers.
- Recognize that database transactions do not automatically guarantee atomic transactions with the broker.

When functions call services through Dependency Injection, event-processing code stays clean with explicit dependencies. Spring manages service lifecycles, while the binder manages message connectivity with the broker. This separation of responsibilities allows the same use case to be invoked from Spring Cloud Stream, a REST API, or a scheduler without duplicating business rules.
