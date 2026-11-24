# Synthesizing Startup Timelines, Bean Graphs, and Application Behavior Evidence

When a Spring Boot application starts, many components participate: the Java launcher creates the JVM, Spring Boot prepares the `Environment`, the Spring container reads bean definitions, resolves dependencies, creates beans, runs initialization callbacks, starts the web server, and finally transitions the application to ready.

When a request arrives, the controller calls an application service, the service calls collaborators, and a response is returned. When proving an application works properly, a single `Started ...` log line or a health endpoint returning `UP` is not enough. We need evidence matched to each question:

- **Startup:** was the context created and did mandatory startup steps finish?
- **Wiring:** which beans were registered, which dependencies were injected, and which implementations were selected?
- **Behavior:** given specific inputs, does the application return the expected output and produce the right side effects?
- **Runtime:** are real requests handled reliably, fast enough, and observably when failures occur?

This practice lesson brings together three perspectives: **startup timeline**, **bean graph**, and **application behavior evidence**. We build a small Order API example, trace its lifecycle, map its dependency graph, write tests at multiple levels, and connect them to logs, metrics, traces, and health probes.

> Every diagram and check proves only a specific scope. Successful startup proves startup milestones passed; the bean graph shows how objects are wired; tests and runtime signals provide evidence only for the behaviors they actually verify.

## 1. Objectives of This Practice Lesson

After this lesson, you will be able to:

1. Describe the main sequence of Spring Boot startup from `SpringApplication.run()` to `ApplicationReadyEvent`.
2. Distinguish bean definitions, bean instances, dependency graphs, and runtime call graphs.
3. Draw a dependency graph from constructor injection and Java configuration.
4. Identify which beans come from component scan and which come from `@Bean`.
5. Prove a feature using unit tests, context tests, MVC tests, and integration tests.
6. Select appropriate evidence for startup, wiring, HTTP behavior, and business correctness.
7. Use logs, metrics, traces, and health endpoints for diagnosis without treating a single signal as universal proof.
8. Organize a design review or deployment review grounded in reproducible evidence.

## 2. Three Models to View Together

An application can be described through three distinct models.

### 2.1. Startup Timeline

The startup timeline answers: **Which steps did Spring Boot pass through, and in what order?**

```text
Java launcher
    |
    v
JVM starts
    |
    v
SpringApplication.run(...)
    |
    v
Prepare Environment
    |
    v
Create / prepare ApplicationContext
    |
    v
Load bean definitions
    |
    v
Refresh context
    |
    +--> Instantiate non-lazy singletons
    +--> Resolve dependencies
    +--> Initialize beans
    +--> Apply BeanPostProcessors / proxies
    +--> Start lifecycle components
    +--> Start embedded web server when applicable
    |
    v
ApplicationStartedEvent
    |
    v
ApplicationRunner / CommandLineRunner
    |
    v
ApplicationReadyEvent
    |
    v
Application available for normal traffic
```

This is a high-level diagram. Internal details and exact log lines vary by Spring Boot version, application type, and customization. Key milestones to remember are that context refresh finishes before `ApplicationStartedEvent`; runners execute afterward; `ApplicationReadyEvent` is published after runners complete on the normal startup path.

### 2.2. Bean Dependency Graph

The bean graph answers: **Which object depends on which object in order to be created and operate?**

Example:

```text
OrderController
      |
      v
PlaceOrderService
    /       \
   v         v
OrderStore  Clock
   ^          ^
   |          |
InMemory   Java Configuration
OrderStore @Bean
```

Arrows show dependencies: `PlaceOrderService` requires `OrderStore` and `Clock`. Spring uses constructor/method parameters and bean definitions to resolve those dependencies.

### 2.3. Runtime Call Graph

The runtime call graph answers: **When a specific request executes, which methods are called and in what order?**

```text
POST /orders
     |
     v
OrderController.create(...)
     |
     v
PlaceOrderService.place(...)
     |
     +--> OrderPolicy.validate(...)
     |
     +--> Clock.instant()
     |
     +--> OrderStore.save(...)
     |
     v
HTTP 201 + OrderResponse
```

The bean graph and call graph are related, not identical. A bean may be injected yet never called during a particular request. Conversely, one method can invoke multiple objects at runtime without altering the static dependency graph.

## 3. Matching the Three Models to Three Types of Evidence

| Model | What it describes | Appropriate evidence |
| --- | --- | --- |
| Startup timeline | Lifecycle milestones | Events, startup logs, context state |
| Bean dependency graph | Wiring relationships among beans | Context tests, bean inspection, constructor graph |
| Runtime call graph | Execution flow for a use case | Unit/integration tests, traces, structured logs |

Examples:

- A `Started OrderApplication ...` log line does not tell you which implementation a service injected.
- A bean graph showing `OrderStore -> InMemoryOrderStore` does not prove `save()` persists data properly.
- A passing unit test for `PlaceOrderService` does not prove Spring scanned the controller.
- `GET /actuator/health` returning `UP` does not prove `POST /orders` returns 201 and saves orders properly.

To state accurate conclusions, always clarify **what was verified, how it was verified, and the limits of the check**.

## 4. Building the Sample Order API Application

We use a small use case:

> Receive order input, validate data, stamp creation time, and store the order; return the order ID and status.

Components:

```text
API layer
  OrderController

Application layer
  PlaceOrderService
  OrderPolicy
  OrderStore (port)

Infrastructure / wiring
  InMemoryOrderStore
  Clock bean
```

This is an illustrative application for learning startup, wiring, and evidence. `InMemoryOrderStore` stores data in process memory; data is lost when the process exits. In a production system, you can swap in a JPA adapter or a suitable persistence implementation.

### 4.1. Package Structure

```text
com.example.orders
├── OrderApplication.java
├── api
│   ├── CreateOrderRequest.java
│   ├── OrderResponse.java
│   └── OrderController.java
├── application
│   ├── PlaceOrderService.java
│   └── OrderPolicy.java
├── domain
│   ├── Order.java
│   └── OrderStatus.java
├── port
│   └── OrderStore.java
└── infrastructure
    ├── InMemoryOrderStore.java
    └── TimeConfiguration.java
```

Placing the application class in the root package lets default component scanning discover all sub-packages.

## 5. Creating the Domain Model

`OrderStatus.java`:

```java
package com.example.orders.domain;

public enum OrderStatus {
    CREATED
}
```

`Order.java`:

```java
package com.example.orders.domain;

import java.math.BigDecimal;
import java.time.Instant;

public record Order(
        String id,
        String customerId,
        BigDecimal amount,
        Instant createdAt,
        OrderStatus status
) {
}
```

This is a plain Java domain data model. It does not need to be a Spring bean because each order represents transaction-specific data, not a shared collaborator in the application context.

### 5.1. Why Not Autowire `Order`?

Each specific `Order` is created per request:

```java
Order order = new Order(...);
```

Its lifecycle belongs to the use case and data. Registering every order as a singleton bean would be the wrong scope. Spring beans fit shared collaborators such as services, policies, repository adapters, or shared clients.

## 6. Defining the Persistence Port

`OrderStore.java`:

```java
package com.example.orders.port;

import com.example.orders.domain.Order;
import java.util.Optional;

public interface OrderStore {

    Order save(Order order);

    Optional<Order> findById(String id);
}
```

`OrderStore` expresses the capability the application service needs: saving and finding orders.

The application layer does not need to know whether data is stored in:

- An in-memory map.
- A JPA repository.
- JDBC.
- A remote order service.

This is a meaningful abstraction because it isolates the use case from persistence details.

## 7. Creating the Business Policy

`OrderPolicy.java`:

```java
package com.example.orders.application;

import com.example.orders.domain.Order;
import java.math.BigDecimal;
import org.springframework.stereotype.Component;

@Component
public class OrderPolicy {

    public void validate(String customerId, BigDecimal amount) {
        if (customerId == null || customerId.isBlank()) {
            throw new IllegalArgumentException(
                    "Customer ID is required"
            );
        }

        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException(
                    "Order amount must be positive"
            );
        }
    }
}
```

In this example, `OrderPolicy` is registered via component scanning. The policy is a shared collaborator, making it suitable as a bean.

The `Order` import is not yet used in this class and can be removed if your IDE flags an unused import; the snippet focuses on input validation.

## 8. Creating the Persistence Adapter

`InMemoryOrderStore.java`:

```java
package com.example.orders.infrastructure;

import com.example.orders.domain.Order;
import com.example.orders.port.OrderStore;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import org.springframework.stereotype.Repository;

@Repository
public class InMemoryOrderStore implements OrderStore {

    private final ConcurrentMap<String, Order> orders =
            new ConcurrentHashMap<>();

    @Override
    public Order save(Order order) {
        orders.put(order.id(), order);
        return order;
    }

    @Override
    public Optional<Order> findById(String id) {
        return Optional.ofNullable(orders.get(id));
    }
}
```

`@Repository` is a stereotype allowing component scan to discover the adapter. In a real application, a JPA repository can implement the same port and map between domain objects and persistence entities.

`ConcurrentHashMap` provides thread-safe concurrent access at the map structure level. It does not make data durable storage and does not replace database transaction semantics.

## 9. Registering `Clock` with Java Configuration

`TimeConfiguration.java`:

```java
package com.example.orders.infrastructure;

import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class TimeConfiguration {

    @Bean
    public Clock applicationClock() {
        return Clock.systemUTC();
    }
}
```

This is a Java configuration example:

- `@Configuration` declares a configuration class.
- `@Bean` registers the object returned from the factory method.
- The default bean name is `applicationClock`.
- `Clock` can be injected into services.

`Clock` is Java's abstraction for reading time. In tests, we can swap in a fixed clock so results do not depend on wall-clock time.

## 10. Creating the Application Service

`PlaceOrderService.java`:

```java
package com.example.orders.application;

import com.example.orders.domain.Order;
import com.example.orders.domain.OrderStatus;
import com.example.orders.port.OrderStore;
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class PlaceOrderService {

    private final OrderStore orderStore;
    private final OrderPolicy orderPolicy;
    private final Clock clock;

    public PlaceOrderService(
            OrderStore orderStore,
            OrderPolicy orderPolicy,
            Clock clock) {
        this.orderStore = orderStore;
        this.orderPolicy = orderPolicy;
        this.clock = clock;
    }

    public Order place(String customerId, BigDecimal amount) {
        orderPolicy.validate(customerId, amount);

        Order order = new Order(
                UUID.randomUUID().toString(),
                customerId,
                amount,
                Instant.now(clock),
                OrderStatus.CREATED
        );

        return orderStore.save(order);
    }

    public Order findById(String id) {
        return orderStore.findById(id)
                .orElseThrow(() ->
                        new OrderNotFoundException(id)
                );
    }
}
```

Exception:

```java
package com.example.orders.application;

public class OrderNotFoundException extends RuntimeException {

    public OrderNotFoundException(String id) {
        super("Order not found: " + id);
    }
}
```

The service depends on three collaborators through its constructor:

- `OrderStore`: persistence port.
- `OrderPolicy`: validation policy.
- `Clock`: time source.

It does not construct collaborators with `new`. `UUID` and `Order` are value/data objects created inside the use case and do not need to be registered as Spring beans.

## 11. Creating API Request and Response Types

`CreateOrderRequest.java`:

```java
package com.example.orders.api;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import java.math.BigDecimal;

public record CreateOrderRequest(
        @NotBlank String customerId,
        @NotNull @Positive BigDecimal amount
) {
}
```

To use `@Valid` with Spring Boot, you need a matching validation dependency, typically `spring-boot-starter-validation`.

`OrderResponse.java`:

```java
package com.example.orders.api;

import com.example.orders.domain.Order;
import java.math.BigDecimal;
import java.time.Instant;

public record OrderResponse(
        String id,
        String customerId,
        BigDecimal amount,
        Instant createdAt,
        String status
) {
    public static OrderResponse from(Order order) {
        return new OrderResponse(
                order.id(),
                order.customerId(),
                order.amount(),
                order.createdAt(),
                order.status().name()
        );
    }
}
```

Response DTOs prevent the API from directly exposing every detail of domain objects.

## 12. Creating the Controller

`OrderController.java`:

```java
package com.example.orders.api;

import com.example.orders.application.PlaceOrderService;
import com.example.orders.domain.Order;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final PlaceOrderService placeOrderService;

    public OrderController(PlaceOrderService placeOrderService) {
        this.placeOrderService = placeOrderService;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public OrderResponse create(
            @Valid @RequestBody CreateOrderRequest request) {

        Order order = placeOrderService.place(
                request.customerId(),
                request.amount()
        );

        return OrderResponse.from(order);
    }

    @GetMapping("/{id}")
    public OrderResponse findById(@PathVariable String id) {
        return OrderResponse.from(
                placeOrderService.findById(id)
        );
    }
}
```

Here the controller is registered via component scan thanks to `@RestController`. It receives the request, invokes the application service, and maps the domain result into a response DTO.

### 12.1. Handling Not-Found Errors

You can add an exception handler:

```java
package com.example.orders.api;

import com.example.orders.application.OrderNotFoundException;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    @ResponseStatus(HttpStatus.NOT_FOUND)
    public Map<String, String> handleNotFound(
            OrderNotFoundException exception) {

        return Map.of(
                "error", "ORDER_NOT_FOUND",
                "message", exception.getMessage()
        );
    }
}
```

In real APIs, consider how much detail messages expose so internal data does not leak. This example uses a non-sensitive message.

## 13. Application Class and Component Scan Scope

`OrderApplication.java`:

```java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
```

The application class lives in `com.example.orders`, so default component scan discovers:

- `api.OrderController`.
- `api.ApiExceptionHandler`.
- `application.PlaceOrderService`.
- `application.OrderPolicy`.
- `infrastructure.InMemoryOrderStore`.
- `infrastructure.TimeConfiguration`.

`TimeConfiguration` provides the `Clock` bean via Java configuration.

## 14. Bean Graph of the Sample Application

From constructor parameters and configuration, we can draw:

```text
OrderController (@RestController)
        |
        v
PlaceOrderService (@Service)
        |
        +--------------------+
        |                    |
        v                    v
OrderPolicy (@Component)   OrderStore (interface)
                             ^
                             |
                    InMemoryOrderStore
                       (@Repository)

PlaceOrderService
        |
        v
Clock
  ^
  |
TimeConfiguration
  @Bean applicationClock()
```

### 14.1. Reading the Graph in Dependency Direction

`PlaceOrderService` requires `OrderStore`, `OrderPolicy`, and `Clock`. Spring locates matching beans using type, qualifier, primary, and registration conditions.

In the current configuration:

- `OrderStore` has one implementation: `InMemoryOrderStore`.
- `OrderPolicy` has one component.
- `Clock` has one bean created by `TimeConfiguration`.

Because each constructor dependency has a single candidate, Spring can instantiate `PlaceOrderService`.

### 14.2. The Bean Graph Is Not a Package Tree

A package tree shows where files live. A bean graph shows which objects require which other objects. The two diagrams answer different questions.

For example, `TimeConfiguration` lives in package `infrastructure`, yet `PlaceOrderService` depends on `Clock`, not directly on `TimeConfiguration`.

### 14.3. The Bean Graph Is Not a Complete Object Allocation Graph

The graph focuses on Spring-managed dependencies. Objects such as `Order`, `UUID`, and `OrderResponse` instantiated inside methods are not Spring beans and do not appear in the bean graph.

## 15. Startup Timeline of the Sample Application

When running:

```bash
java -jar order-service.jar
```

Spring Boot executes a high-level sequence of steps:

```text
1. Java launcher starts JVM
2. Calls OrderApplication.main(args)
3. SpringApplication.run(...)
4. Prepare Environment and property sources
5. Create ApplicationContext
6. Register/load configuration and bean definitions
7. Component scan discovers stereotype classes
8. Process @Bean methods in TimeConfiguration
9. Refresh ApplicationContext
10. Resolve dependencies and instantiate eager singleton beans
11. Initialize beans, run callbacks and post-processors
12. Start embedded web server
13. Publish ApplicationStartedEvent
14. Run ApplicationRunner / CommandLineRunner
15. Publish ApplicationReadyEvent
16. Readiness transitions to accepting traffic per lifecycle
```

Activities such as auto-configuration, proxy creation, and lifecycle component startup occur inside refresh; the list above is a conceptual learning sequence rather than a trace of every internal method.

### 15.1. Context Refresh

This is the critical phase where Spring instantiates non-lazy singleton beans and resolves the dependency graph. If a required bean's constructor or initialization callback fails, context refresh fails and the application never reaches the ready state.

### 15.2. `ApplicationStartedEvent`

This event is published after the context has refreshed. Runners have not yet been invoked at this point in the normal Spring Boot flow.

### 15.3. Runners

`ApplicationRunner` receives `ApplicationArguments`; `CommandLineRunner` receives `String... args`.

They are typically used for post-refresh steps such as validation or required initialization. If a runner throws an unhandled exception, startup fails and `ApplicationReadyEvent` is not published on the success path.

### 15.4. `ApplicationReadyEvent`

This event signals the application completed startup steps in the Spring Boot lifecycle and is ready to serve as designed. It does not prove all business workflows are bug-free or that every asynchronous background task has completed.

## 16. Observing Startup Events

You can register a listener to record lifecycle milestones.

```java
package com.example.orders.observability;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class StartupEventLogger {

    private static final Logger log =
            LoggerFactory.getLogger(StartupEventLogger.class);

    @EventListener
    public void onStarted(ApplicationStartedEvent event) {
        log.info("event=application.started");
    }

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        log.info("event=application.ready");
    }
}
```

Sample log:

```text
INFO event=application.started
INFO event=application.ready
```

### 16.1. Logging Meaningful Events

Logs should include:

- Event name or lifecycle phase.
- Application/service name.
- Deployment version if available.
- Timestamp or duration as appropriate.
- Instance identifier if distinguishing replicas.

Never log passwords, tokens, or entire environment properties.

### 16.2. Do Not Infer Everything from a Single `Started ...` Line

Startup log formats and placement vary across versions, listeners, and configurations. When you need confirmation that runners finished, use the appropriate event/lifecycle signal and inspect runner logs.

### 16.3. Ready Events Are Not Synthetic Tests

`ApplicationReadyEvent` is lifecycle evidence. It does not send an HTTP request through ingress, check authorization, or verify that an order is stored accurately.

## 17. Inspecting the Bean Graph via `ApplicationContext`

In tests or internal diagnostics, you can list bean names by type:

```java
String[] names =
        context.getBeanNamesForType(OrderStore.class);
```

Expected result in the sample app:

```text
inMemoryOrderStore
```

Similarly:

```java
String[] clocks =
        context.getBeanNamesForType(Clock.class);
```

Expected result:

```text
applicationClock
```

### 17.1. Checking Bean Count

```java
assertThat(context.getBeansOfType(OrderStore.class))
        .hasSize(1);
```

This proves the context contains exactly one bean of the inspected type within that specific test context.

It does not prove `save()` persists business data correctly. That is a separate behavioral question.

### 17.2. Do Not Expose Bean Inventory Publicly

Bean names can disclose modules, vendors, or internal architecture. Use them in tests or secured internal endpoints when needed; never expose the whole inventory in a public API.

## 18. Behavior Evidence: Choosing the Right Testing Level

No single test proves the entire application. Pick tests by scope:

| Level | Checks | Primary evidence |
| --- | --- | --- |
| Unit test | Logic of a single class | Input/output, exceptions, side effects via fakes/mocks |
| Context test | Bean registration and wiring | Context starts, bean types/names are right |
| Slice test | One framework slice, e.g. MVC | Routing, validation, serialization, controller behavior |
| Integration test | Interaction across components | Persistence, transactions, configuration |
| Contract test | API between two modules/services | Request/response schemas and semantics |
| End-to-end test | User journey across layers | Combined behavior in a test environment |
| Synthetic monitoring | Periodic journeys on runtime | Ability to execute a specific flow when measured |
| Production telemetry | Real traffic over time | Availability, latency, errors, business outcomes |

These levels complement each other. Unit tests are fast and isolated; E2E tests sit closer to user behavior yet cost more and depend on environments.

## 19. Unit Testing the Application Service

`PlaceOrderService` has three dependencies. Unit tests can use a fake `OrderStore`, the real `OrderPolicy`, and a fixed `Clock`.

### 19.1. Fake Store

```java
class FakeOrderStore implements OrderStore {

    private final Map<String, Order> orders = new HashMap<>();

    @Override
    public Order save(Order order) {
        orders.put(order.id(), order);
        return order;
    }

    @Override
    public Optional<Order> findById(String id) {
        return Optional.ofNullable(orders.get(id));
    }
}
```

### 19.2. Happy-Path Test

```java
class PlaceOrderServiceTest {

    private final FakeOrderStore store = new FakeOrderStore();

    private final Clock clock = Clock.fixed(
            Instant.parse("2026-01-15T10:00:00Z"),
            ZoneOffset.UTC
    );

    private final PlaceOrderService service =
            new PlaceOrderService(
                    store,
                    new OrderPolicy(),
                    clock
            );

    @Test
    void createsAndStoresAnOrder() {
        Order order = service.place(
                "customer-1",
                new BigDecimal("125000")
        );

        assertThat(order.id()).isNotBlank();
        assertThat(order.customerId()).isEqualTo("customer-1");
        assertThat(order.amount())
                .isEqualByComparingTo("125000");
        assertThat(order.createdAt())
                .isEqualTo(Instant.parse("2026-01-15T10:00:00Z"));
        assertThat(order.status()).isEqualTo(OrderStatus.CREATED);
        assertThat(store.findById(order.id())).contains(order);
    }
}
```

This test provides evidence that for the chosen input:

- The policy accepts the data.
- The service creates an order with a deterministic timestamp.
- The store accepts and returns the order.
- Initial status is `CREATED`.

It does not boot a Spring context and does not prove component scan or `@Bean` wiring works.

### 19.3. Validation Test

```java
@Test
void rejectsNonPositiveAmount() {
    assertThatThrownBy(() ->
            service.place(
                    "customer-1",
                    BigDecimal.ZERO
            )
    ).isInstanceOf(IllegalArgumentException.class)
     .hasMessage("Order amount must be positive");
}
```

This test proves a specific validation rule. It does not check HTTP request-body validation; that belongs in an MVC test.

### 19.4. Why Use `Clock`?

If the service called `Instant.now()` directly, tests would depend on real time and be harder to assert accurately. Injecting `Clock` lets tests supply `Clock.fixed(...)` while production uses `Clock.systemUTC()`.

This is an example of a dependency that directly improves behavioral controllability.

## 20. Context Test: Proving Wiring

The unit test above constructs the service with `new`. To prove Spring can register and inject beans, boot a context.

### 20.1. Testing with `ApplicationContextRunner`

`ApplicationContextRunner` works well for a lightweight context:

```java
class OrderWiringTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(OrderTestConfiguration.class);

    @Test
    void wiresOrderServiceAndItsDependencies() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(PlaceOrderService.class);
            assertThat(context).hasSingleBean(OrderStore.class);
            assertThat(context).hasSingleBean(Clock.class);
        });
    }

    @Configuration(proxyBeanMethods = false)
    @Import({
            PlaceOrderService.class,
            OrderPolicy.class,
            InMemoryOrderStore.class,
            TimeConfiguration.class
    })
    static class OrderTestConfiguration {
    }
}
```

This is a test skeleton; include imports for Spring Boot's test context runner, Spring `@Configuration`, `@Import`, JUnit 5, and AssertJ. In a real project, the test configuration imports the exact required configurations/components.

### 20.2. What This Test Proves

- The small context can refresh.
- Exactly one `PlaceOrderService` bean exists.
- `OrderStore` and `Clock` beans exist.
- Constructor dependencies resolve cleanly.

### 20.3. What This Test Does Not Prove

- The HTTP route `/api/orders` is registered.
- JSON requests deserialize properly.
- Bean validation is active.
- Error mapping returns the right status.
- Requests through a real web server succeed.

Those belong to other layers.

## 21. Full Application Context Test

`@SpringBootTest` initializes the application's context under test configuration.

```java
@SpringBootTest
class OrderApplicationContextTest {

    @Autowired
    PlaceOrderService placeOrderService;

    @Autowired
    OrderStore orderStore;

    @Test
    void applicationWiresOrderUseCase() {
        Order order = placeOrderService.place(
                "customer-2",
                new BigDecimal("50000")
        );

        assertThat(orderStore.findById(order.id()))
                .contains(order);
    }
}
```

This test verifies wiring through the real application context and a service/store flow.

### 21.1. Benefits

- Catches bad component scans.
- Catches missing beans or bean ambiguity.
- Catches un-imported configurations.
- Catches some auto-configuration and property binding bugs.

### 21.2. Cost

Full context tests are slower than unit tests and may require databases, brokers, or stubbed services depending on the application. Do not use them for every small business rule.

## 22. MVC Slice Test: Proving the HTTP Contract

`@WebMvcTest` focuses on the Spring MVC layer. Use `@MockBean` or the mock bean annotation suited to your Spring Boot version to replace the application service.

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    PlaceOrderService placeOrderService;

    @Test
    void createsOrderAndReturnsCreated() throws Exception {
        Order order = new Order(
                "order-1",
                "customer-1",
                new BigDecimal("125000"),
                Instant.parse("2026-01-15T10:00:00Z"),
                OrderStatus.CREATED
        );

        given(placeOrderService.place(
                "customer-1",
                new BigDecimal("125000")
        )).willReturn(order);

        mockMvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "customerId": "customer-1",
                                  "amount": 125000
                                }
                                """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").value("order-1"))
                .andExpect(jsonPath("$.customerId").value("customer-1"))
                .andExpect(jsonPath("$.status").value("CREATED"));
    }
}
```

This test requires Mockito BDD imports, MockMvc request builders, `MediaType`, `jsonPath`, JUnit 5, and Spring test annotations. The mock bean annotation name varies across Spring Boot generations; use the API compatible with your project's version.

### 22.1. Testing HTTP Validation

If a request omits `customerId` or passes an invalid amount, MVC validation returns 400 when:

- Validation dependency is present.
- Controller uses `@Valid`.
- Request model declares constraints.
- MVC validation infrastructure is configured.

Example:

```java
mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
                {
                  "customerId": "",
                  "amount": 0
                }
                """))
        .andExpect(status().isBadRequest());
```

This is evidence for request validation and HTTP responses in an MVC slice test.

### 22.2. Mocking the Service Limits the Test

Because the service is mocked, this test does not prove `PlaceOrderService` saves orders. It only proves the controller invokes the service with the input and maps the return value to a response.

To prove persistence flows, you need an integration test or full context test with an appropriate store.

## 23. Integration Test: Proving Components Collaborate

An integration test exercises multiple real components together:

```text
MockMvc / HTTP client
       |
       v
OrderController
       |
       v
PlaceOrderService
       |
       +--> OrderPolicy
       |
       +--> OrderStore adapter
       |
       v
Response
```

With the in-memory example, you can boot the full context and exercise controller/service together. With real persistence, swap `InMemoryOrderStore` for a JPA adapter and a test database.

### 23.1. When to Use `@DataJpaTest`

If the application has a JPA adapter, `@DataJpaTest` focuses on entity mapping, repositories, and database interactions. It does not load the entire web/application layer.

### 23.2. When to Use Testcontainers

When you need to verify behavior against the real database engine, Testcontainers can spin up database containers for integration tests. That yields stronger environmental evidence than H2 whenever SQL dialect or schema differences matter.

### 23.3. Checking Transactions and Constraints

Integration tests can verify:

- Unique constraints.
- Foreign keys.
- Transaction rollback.
- Mapping.
- Query behavior.
- Required concurrency semantics.

A unit test with a fake map proves none of those.

## 24. End-to-End Test: Proving a Multi-Layer Flow

An E2E test verifies a journey close to how clients consume the application:

```text
HTTP POST /api/orders
        |
        v
Request parsing / validation
        |
        v
Controller
        |
        v
Application service
        |
        v
Persistence adapter
        |
        v
HTTP 201 + response body
        |
        v
HTTP GET /api/orders/{id}
        |
        v
HTTP 200 + stored order
```

An E2E test can:

1. Start the application in a test environment.
2. Send a POST request to create an order.
3. Extract `id` from the response.
4. Send a GET request with `id`.
5. Compare returned data against submitted data.

### 24.1. What an E2E Test Proves

Under that specific environment and input, the traversed components collaborate to produce the expected behavior.

### 24.2. What an E2E Test Does Not Prove

- All inputs are handled properly.
- Every role or tenant works.
- The system sustains production load.
- Every replica behaves identically.
- No rare or timing-dependent bugs exist.

An E2E test is strong evidence for one specific flow, not universal proof of all behavior.

## 25. Evidence from Logs

Logs help reconstruct events chronologically. In the sample app, you can log at the use-case boundary:

```java
log.info(
        "event=order.created orderId={} customerId={}",
        order.id(),
        order.customerId()
);
```

In real systems, consider whether `customerId` is allowed in logs. You can use a pseudonymized reference or a safe correlation identifier.

### 25.1. What Do Logs Prove?

A trustworthy log event shows execution passed a point and recorded values at that instant.

Example:

```text
event=order.created orderId=... traceId=...
```

It does not by itself prove data was durably committed if logged before transaction commit or if the store is in-memory.

### 25.2. Log at the Right Moment

When recording committed outcomes, place events relative to transaction boundaries or use after-commit events. Logs emitted before commit can still appear even if the transaction later rolls back.

### 25.3. Never Log Entire Requests

Avoid logging:

- Passwords.
- Access tokens.
- Payment credentials.
- Unnecessary raw personal data.
- Full request/response bodies containing sensitive fields.

Logs should capture event, outcome, duration, error code, and needed correlation IDs.

## 26. Evidence from Metrics

Metrics describe numbers aggregated over time.

Useful metrics for the Order API:

- Request count by route and status.
- Error count by failure category.
- Request latency histogram.
- Count of orders created successfully.
- Order failure rate by cause.
- In-flight request count.

Example with Micrometer:

```java
@Service
public class OrderMetrics {

    private final Counter createdOrders;

    public OrderMetrics(MeterRegistry registry) {
        this.createdOrders = Counter.builder("orders.created")
                .description("Number of orders created")
                .register(registry);
    }

    public void recordCreated() {
        createdOrders.increment();
    }
}
```

The service can invoke `recordCreated()` after the store returns success per the intended semantics.

### 26.1. Choosing When to Increment Counters

If you increment before persistence completes, the count may include failed orders. Clarify whether a metric measures:

- Request received.
- Validation succeeded.
- Write invoked.
- Transaction committed.
- Order confirmed.

Metric names and instrumentation sites must reflect the exact event.

### 26.2. Do Not Use IDs as Metric Tags

Never put `orderId`, `customerId`, or request IDs into metric labels/tags. High-cardinality values inflate storage costs and can cause operational incidents.

Use metric tags with small bounded value sets such as route, outcome, or normalized error category.

## 27. Evidence from Tracing

Distributed tracing shows which spans a request traversed and how long each segment took.

Example:

```text
HTTP POST /api/orders
    |
    +--> OrderController.create
            |
            +--> PlaceOrderService.place
                    |
                    +--> OrderPolicy.validate
                    |
                    +--> OrderStore.save
```

If persistence is remote or database-backed, traces reveal which span was slow or errored.

### 27.1. Traces Locate Bottlenecks, Not Business Correctness

A trace with status OK can still accompany a wrong response if code misses a logic bug.

Example:

```text
HTTP status = 201
trace status = OK
order amount = 0
```

If an amount of 0 violates business rules yet validation is missing, the trace can still finish cleanly.

Combine telemetry with assertions and business invariants.

### 27.2. Correlating Logs and Traces

With a trace ID, logs from controller, service, and adapter link to the same request. This lets you investigate a specific transaction without logging raw payloads.

## 28. Health Checks and Readiness in the Evidence Picture

Spring Boot Actuator can expose:

```text
/actuator/health
/actuator/health/liveness
/actuator/health/readiness
```

Available endpoints and probe behavior depend on version and configuration.

### 28.1. What Does Health `UP` Prove?

Health status reflects contributors in the health group per aggregation policy. It does not by default exercise every controller or business use case.

### 28.2. What Does Readiness `UP` Prove?

Readiness means the instance is currently judged able to receive traffic according to configured readiness conditions. It does not guarantee the next request will succeed.

### 28.3. What Does Liveness `UP` Prove?

Liveness means the instance meets criteria to remain running per liveness policy. It should not blindly depend on every remote dependency, as doing so can trigger restart storms when a shared dependency degrades.

### 28.4. Do Not Substitute Health Checks for E2E Tests

Health probes must be fast, safe, and repeatable. Deep business workflows require dedicated tests or synthetic checks with controlled inputs and safe side effects.

## 29. Summary Table: Which Question Requires Which Evidence?

| Question | Preferred evidence | Conclusion you can draw |
| --- | --- | --- |
| Did the JVM start? | Process/container state | Process existed at observation time |
| Did the context refresh? | Startup event/context test | Context passed the refresh milestone |
| Did runners finish? | `ApplicationReadyEvent` and runner outcomes | Startup lifecycle succeeded through runners |
| Are beans wired properly? | Context test, bean type assertions | Context resolved expected dependencies in tests |
| Is calculation logic right? | Unit test with expected values | Specific rules passed for tested inputs |
| Does the HTTP route work? | MVC test/MockMvc | Routing, validation, and response contract verified |
| Does persistence work? | Integration test with database | Mapping/queries/transactions verified in test env |
| Does the user journey work? | E2E/synthetic | Specific flow completed under test conditions |
| Are production users seeing errors? | Metrics, logs, traces, business events | Actual runtime behavior in observation window |
| Should instance receive traffic? | Readiness probe | Instance passed defined readiness conditions |
| Is the service reliable over time? | SLIs/SLOs and metric history | Service quality over defined measurement window |

## 30. Practice Running the Application

After completing the classes, run the project with Gradle or Maven per your setup.

Gradle example:

```bash
./gradlew bootRun
```

Or build the executable JAR:

```bash
./gradlew bootJar
java -jar build/libs/order-service.jar
```

Actual JAR filename depends on `project.name`, version, and archive settings.

### 30.1. Creating an Order

```bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"customerId":"customer-1","amount":125000}'
```

Illustrative response:

```http
HTTP/1.1 201
Content-Type: application/json
```

```json
{
  "id": "generated-order-id",
  "customerId": "customer-1",
  "amount": 125000,
  "createdAt": "2026-01-15T10:00:00Z",
  "status": "CREATED"
}
```

The actual timestamp comes from `Clock.systemUTC()`, so real responses reflect runtime clock time rather than the fixed example timestamp.

### 30.2. Reading the Created Order

```bash
curl -i http://localhost:8080/api/orders/<order-id>
```

Replace `<order-id>` with the actual ID returned by POST.

### 30.3. Testing Invalid Input

```bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"customerId":"","amount":0}'
```

With the validation dependency and `@Valid` configured, the request is rejected at the MVC layer before reaching the service.

If validation is disabled, the service policy still rejects the input when called. The two validation layers serve distinct purposes.

## 31. A Deployment Can Start Successfully Yet Still Have Broken Behavior

Consider these scenarios:

### Scenario A — Wrong Implementation Injected

Two beans implement `OrderStore`, yet qualifier/primary picked the wrong adapter. The context boots cleanly because wiring is valid; data gets saved to the wrong place.

**Evidence needed:** context assertions on bean selection, configuration tests, and integration tests confirming the persistence target.

### Scenario B — Wrong Service Logic

`PlaceOrderService` creates an order but assigns the wrong amount or status.

**Evidence needed:** unit tests asserting expected values and business invariants.

### Scenario C — Wrong HTTP Mapping

The service works properly yet the controller returns 200 instead of 201 or serializes the wrong field.

**Evidence needed:** MVC tests or HTTP integration tests.

### Scenario D — Non-Durable Persistence

An in-memory store returns orders correctly, yet data vanishes across restarts.

**Evidence needed:** integration tests against real persistence checking state across new transactions/contexts/processes.

### Scenario E — Runtime Degradation

One replica suffers thread-pool exhaustion or high database latency even while readiness remains UP.

**Evidence needed:** per-route metrics, traces, pool metrics, and request outcomes.

### Scenario F — Stale Startup Log

A `Started ...` log came from an earlier pod before rollout, while the new pod is crash-looping.

**Evidence needed:** timestamps, instance IDs, restart counts, and current status of the specific replica.

## 32. Assembling an Evidence Package for a Change

When reviewing a Spring Boot change, organize evidence into four parts:

### 32.1. Startup Evidence

- Application context starts cleanly.
- Profiles and critical configuration match.
- Mandatory runners complete.
- Readiness transitions to accepting traffic per policy.

### 32.2. Wiring Evidence

- Required bean definitions exist.
- Dependencies resolve properly.
- No unintended bean ambiguity exists.
- Implementations are selected accurately per profile/property.

### 32.3. Behavior Evidence

- Unit tests for business rules.
- MVC tests for HTTP contracts.
- Integration tests for persistence and transactions.
- E2E tests for critical user journeys.

### 32.4. Runtime Evidence

- Request rate, error rate, and latency.
- Dependency health and resource pool metrics.
- Structured logs with correlation.
- Traces for slow/failed requests.
- Synthetic checks and business outcome metrics.

You do not need every test tier for every tiny change. Match evidence to the code area and risk affected by the change.

## 33. Tracing an Error from Startup to Behavior

Suppose a new deployment reports:

```text
INFO  event=application.started
INFO  event=application.ready
INFO  readiness=UP
```

Yet POST order returns 500.

Investigation sequence:

1. Verify logs came from the right instance and version.
2. Inspect the controller/service exception via trace ID.
3. Check which bean implementation was injected for `OrderStore`.
4. Determine whether the error occurred in policy, store adapter, or an external dependency.
5. Compare input against expected business outcomes.
6. Write a reproducing test at the matching layer.
7. Fix the root cause and keep the test to prevent regressions.

Do not conclude the startup log was lying. Startup can succeed while request behavior fails at runtime; those are two separate conclusions with different scopes.

## 34. Diagnosing Wiring Errors from the Bean Graph

If startup fails:

```text
No qualifying bean of type 'OrderStore'
```

Check:

- Does `InMemoryOrderStore` carry a stereotype?
- Is the package within component scan scope?
- Did a profile or condition exclude the bean?
- Did another configuration register a competing adapter?
- Did a constructor/init failure prevent bean creation?

If the error is:

```text
NoUniqueBeanDefinitionException
```

Inspect bean names:

```java
context.getBeanNamesForType(OrderStore.class)
```

Then:

- Remove duplicate registrations if unnecessary.
- Use `@Qualifier` when adapters serve distinct roles.
- Use `@Primary` when one implementation is truly the default.
- Clarify profiles and conditions.

### 34.1. Drawing the Bean Graph from Constructors

Example:

```java
public PlaceOrderService(
        OrderStore orderStore,
        OrderPolicy orderPolicy,
        Clock clock) {
}
```

Reading constructors is the quickest way to identify required service dependencies. For `@Bean` methods, read method parameters to see the created bean's dependencies.

## 35. Mistakes When Reading Diagrams

| Mistake | Accurate understanding |
| --- | --- |
| Treating a package tree as a bean graph | A package tree only describes file locations |
| Treating a bean graph as a call graph | Being injected does not mean every method gets called |
| Treating `Started ...` as proof all runners finished | Use lifecycle events and runner outcomes |
| Treating `ApplicationReadyEvent` as E2E pass | The event only reflects startup lifecycle |
| Treating health `UP` as all APIs working | Health only evaluates contributors in its group |
| Treating passing unit tests as valid Spring wiring | Unit tests may never start a context |
| Treating passing context tests as valid DB transactions | Integration tests are required for persistence behavior |
| Treating HTTP 201 as durable persistence | Confirm adapter and storage semantics |
| Treating trace OK as valid business results | Verify expected values and business invariants |
| Treating one healthy replica as the whole deployment | Observe per instance, version, and zone when needed |

## 36. Practice Exercises

### Exercise 1 — Draw the Startup Timeline

Draw the timeline from `SpringApplication.run()` to `ApplicationReadyEvent`.

Mark:

- Environment preparation.
- Context refresh.
- Singleton creation.
- `ApplicationStartedEvent`.
- `ApplicationRunner`.
- `ApplicationReadyEvent`.

Explain how a runner throwing an exception affects startup state.

### Exercise 2 — Draw the Bean Dependency Graph

For `OrderController`, `PlaceOrderService`, `OrderPolicy`, `OrderStore`, `InMemoryOrderStore`, and `Clock`, draw the dependency graph.

Distinguish beans registered by component scan from beans created via `@Bean`.

### Exercise 3 — Draw the Runtime Call Graph

For `POST /api/orders`, trace the method call order from controller to store.

Identify which objects are Spring beans and which are data objects created inside methods.

### Exercise 4 — Swap Implementations

Create a `JpaOrderStore` or another fake adapter implementing `OrderStore`.

Select the implementation via profile or condition. Confirm the context holds only the intended implementation.

### Exercise 5 — Unit-Test the Service

Write a fake store and fixed clock. Verify:

- Order ID is non-blank.
- Customer ID matches.
- Amount matches.
- Creation time matches.
- Status matches.
- Order can be read back from the fake store.

### Exercise 6 — Test Validation

Test blank customer ID, null amount, and zero amount.

Assert the exact exceptions and messages/contracts defined by the application.

### Exercise 7 — Context Wiring Test

Use `ApplicationContextRunner` to verify there is one `OrderStore`, one `Clock`, and one `PlaceOrderService`.

Then deliberately register a second adapter and observe the ambiguity.

### Exercise 8 — MVC Test

Use `@WebMvcTest` and `MockMvc` to verify:

- Valid POST returns 201.
- Response JSON has expected fields.
- Invalid input returns 400.
- GET order returns 200 when the service finds the order.

Remember that a mocked service does not prove real persistence.

### Exercise 9 — Full Context Test

Use `@SpringBootTest` to create an order through the Spring-injected service and read it back from the store bean.

Explain what this test covers that unit tests do not.

### Exercise 10 — Database Integration Test

Replace the in-memory adapter with a JPA adapter and a test database.

Verify mapping, transactions, unique constraints, and that data persists after the transaction completes.

### Exercise 11 — Startup Event Test

Record `ApplicationStartedEvent` and `ApplicationReadyEvent`.

Add a succeeding runner, then a failing runner. Observe which events fire in each case.

### Exercise 12 — Check Readiness

Enable Actuator probes per your project's Spring Boot version.

Inspect liveness/readiness and explain why readiness UP does not prove POST order succeeds.

### Exercise 13 — Structured Logging

Add structured log events when an order is created and when validation fails.

Include correlation/trace IDs. Never log raw request bodies or secrets.

### Exercise 14 — Metrics

Add a counter for confirmed orders and a timer for processing duration.

Clarify exact increment timing and how to avoid high-cardinality tags.

### Exercise 15 — Trace a Request

Enable tracing/instrumentation suited to your stack.

Send POST order and inspect spans from HTTP through the application service to the persistence adapter.

Explain why a completed trace does not prove the amount is valid.

### Exercise 16 — Investigate a Hypothetical Deployment

Given:

```text
ApplicationReadyEvent: present
Readiness: UP
POST /api/orders: 500
```

List the evidence to collect from the right instance, logs, traces, metrics, bean wiring, and reproducing tests.

### Exercise 17 — Build an Evidence Package

For a change in `PlaceOrderService`, choose which tests to run and which runtime signals to monitor.

Explain why not every E2E test must run if a change affects only an internal rule, while still providing evidence proportional to risk.

### Exercise 18 — Diagram Review

A document currently contains only a package tree and a startup log. Add:

- A startup timeline.
- A bean dependency graph.
- A runtime call graph.
- Test evidence.
- Runtime telemetry.

Clearly label which conclusions each type of evidence supports.

## 37. Key Takeaways

A Spring Boot application becomes much clearer when viewed through three models: the **startup timeline** shows which lifecycle milestones passed; the **bean dependency graph** shows how Spring wired objects together; the **runtime call graph** shows which components a use case actually executes.

Each model requires its own evidence. Events and startup logs confirm lifecycle milestones. Context tests confirm bean registration and dependency wiring. Unit tests prove specific rules; MVC tests prove HTTP contracts; integration and E2E tests verify collaborating components. Logs, metrics, and traces illuminate runtime behavior, while health/readiness probes guide instance routing decisions.

Never use a single `Started ...` line, a bean inventory, an HTTP 200, or a health `UP` to conclude the entire application works properly. Clearly state the inputs, conditions, expected behavior, checks executed, and limits of those results. **Strong evidence directly answers the question being asked and can be reproduced or re-observed.**
