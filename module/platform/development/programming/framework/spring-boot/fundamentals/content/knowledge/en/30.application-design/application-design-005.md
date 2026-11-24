# Keeping the Dependency Graph Explicitly Directed and Resolving Cycles by Design

A Spring Boot application typically has dozens or hundreds of beans, packages, and modules. Each component uses several other components to accomplish its work. When these relationships are organized properly, it is easy to see which module owns business logic, which module provides infrastructure, and how far a change in one area will propagate.

Conversely, when components depend on one another in multiple directions—especially forming **dependency cycles**—the code becomes hard to initialize, hard to test, and hard to change. Spring may report `BeanCurrentlyInCreationException` when it cannot instantiate beans along the dependency graph; build tools may also reject a module graph containing a cycle. Even when a framework provides a way to defer or work around certain bean cycles, the architecture can remain tightly coupled.

The sustainable approach is to design dependency relationships with a clear direction, keep them as a directed acyclic graph (DAG) across key architectural boundaries, and resolve cycles by changing responsibilities, dependency direction, or how components coordinate.

## 1. What Is a Dependency Graph?

A **dependency graph** describes which components require which other components. It can be represented as:

- Each node is a class, bean, package, or module.
- Each directed edge is a dependency relationship.
- If A needs B to do its work, we draw the edge `A → B`.

Example:

~~~text
OrderController → PlaceOrderService
PlaceOrderService → OrderRepository
PlaceOrderService → PaymentPort
PaymentAdapter → PaymentPort
PaymentAdapter → PaymentClient
~~~

Arrow direction must be consistent: in this lesson, `A → B` means **A depends on B**. The arrow indicates dependency direction in source code or contracts, not necessarily the runtime call order as a request flows through components.

A directed graph helps answer:

- Which component owns a responsibility?
- If interface B changes, which components may be affected?
- Is any module depending on a lower-level module in the wrong architectural direction?
- Is there any path leading back to the starting node?
- Is a dependency genuinely needed, or does it exist only because responsibilities have not been separated?

### Direct vs. Transitive Dependencies

If `A → B` and `B → C`, then A depends directly on B and transitively on C:

~~~text
A → B → C
~~~

A does not necessarily import or call C directly. However, changes to C can affect A through B, depending on contracts and implementations.

Do not confuse a source-level dependency graph with a build-tool dependency graph. Maven/Gradle represent resolved artifacts and modules; the Spring container manages runtime bean relationships; package/class architecture describes source code relationships. They are related, not identical.

## 2. Directed Acyclic Graphs (DAGs)

A directed graph is **acyclic** when there is no directed path starting at a node and returning to that same node. A directed graph without cycles is commonly called a DAG (*Directed Acyclic Graph*).

Example DAG:

~~~text
Web layer
    |
    v
Application layer
    |
    v
Domain layer
~~~

A dependency graph with a cycle:

~~~text
OrderService → InventoryService
      ^                |
      |________________|
~~~

Here:

- `OrderService` needs `InventoryService`.
- `InventoryService` also needs `OrderService`.
- The path returns to the starting node, forming a cycle.

### Why Are DAGs Useful?

A DAG helps organize architecture into clearly ordered layers or modules:

- Dependencies can be initialized in a well-defined order.
- Lower-level modules do not need to know about higher-level modules.
- Build tools can determine a valid module build order.
- The impact scope of contract changes is easier to predict.
- Unit tests can substitute dependencies at clear boundaries.
- Splitting modules and reusing code becomes easier to manage.

For any DAG, there is always at least one *topological ordering* in which each dependency is processed before the component that depends on it. If a graph contains a cycle, no topological ordering exists covering all nodes.

This is one reason constructor injection detects circular dependencies early: Spring must create each dependency before passing it to the constructor of the bean that needs it.

## 3. Dependency Direction Matters More Than Dependency Count

A class with many dependencies does not automatically create a cycle. For instance, a use case may depend on a repository, clock, and payment port:

~~~text
PlaceOrderUseCase
    ├──→ OrderRepository
    ├──→ InventoryPort
    ├──→ PaymentPort
    └──→ Clock
~~~

This graph can still be a DAG as long as none of those dependencies call back into the use case.

Conversely, just two classes can create a cycle:

~~~text
OrderService → InventoryService
      ↑               |
      └───────────────┘
~~~

Therefore, do not judge an architecture solely by the number of constructor fields or modules. Examine the **dependency direction** and the responsibility of each node.

A practical rule: a component orchestrating a use case may call specialized collaborators; those collaborators should not call back into the orchestrating component just to ask it to complete the next step.

## 4. Organizing Dependencies by Layer

A common Spring Boot structure divides an application into layers:

~~~text
┌──────────────────────────┐
│       Web / API          │
└────────────┬─────────────┘
             |
             v
┌──────────────────────────┐
│     Application          │
│  Use cases / Services    │
└────────────┬─────────────┘
             |
             v
┌──────────────────────────┐
│        Domain            │
│ Entities / Value Objects │
└──────────────────────────┘

Infrastructure adapters implement
ports defined by Application/Domain.
~~~

A common dependency direction:

- Web depends on Application to invoke use cases.
- Application depends on Domain and the ports it requires.
- Infrastructure depends on contracts/ports to implement persistence, messaging, or remote APIs.
- Domain does not depend on Web, database frameworks, or specific clients.

Example package layout:

~~~text
com.example.orders
├── web
│   └── OrderController.java
├── application
│   ├── PlaceOrderUseCase.java
│   └── port
│       └── out
│           ├── OrderRepository.java
│           └── PaymentPort.java
├── domain
│   ├── Order.java
│   └── OrderPolicy.java
└── infrastructure
    ├── persistence
    │   └── JpaOrderRepository.java
    └── payment
        └── HttpPaymentAdapter.java
~~~

This is an illustrative layout; projects can use feature packages or separate modules. What matters is keeping dependency rules clear.

### Runtime Call Flow Can Point Opposite to Compile-Time Dependencies

A common point of confusion in ports-and-adapters architecture:

- Application calls a `PaymentPort` interface.
- An external adapter implements that interface.
- Application does not import `HttpPaymentAdapter`.

Compile-time relationships:

~~~text
Application → PaymentPort
HttpPaymentAdapter → PaymentPort
HttpPaymentAdapter → HTTP client
~~~

Runtime execution flow:

~~~text
PlaceOrderUseCase
        |
        v
     PaymentPort
        |
        v
HttpPaymentAdapter
        |
        v
   Payment API
~~~

Spring injects the port implementation into the use case. Runtime control flow passes through the adapter, while source dependencies still point inward toward contracts defined on the inside.

This is the Dependency Inversion Principle (DIP): high-level modules depend on abstractions; concrete implementations also depend on those abstractions.

## 5. Circular Dependencies in the Spring Bean Graph

The Spring container creates and manages beans based on dependencies declared through constructors, setters, fields, factory methods, and other mechanisms.

Example:

~~~java
@Service
public class OrderService {

    private final InventoryService inventoryService;

    public OrderService(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    public void placeOrder() {
        inventoryService.reserveStock();
    }
}
~~~

~~~java
@Service
public class InventoryService {

    private final OrderService orderService;

    public InventoryService(OrderService orderService) {
        this.orderService = orderService;
    }

    public void reserveStock() {
        // Check and reserve stock.
        orderService.markInventoryReserved();
    }
}
~~~

Graph:

~~~text
OrderService → InventoryService
      ^                |
      |                v
      └────────────────┘
~~~

To create `OrderService`, Spring needs `InventoryService`. To create `InventoryService`, Spring needs `OrderService`. Neither constructor can finish in normal order.

With constructor circular dependencies, the application typically fails during ApplicationContext creation with an error like `BeanCurrentlyInCreationException`, often wrapped in another bean creation exception.

### Why Does Constructor Injection Expose Cycles?

With constructor injection, an object is created only after all constructor arguments are ready:

~~~text
Create OrderService
       |
       v
Need InventoryService
       |
       v
Create InventoryService
       |
       v
Need OrderService
       |
       v
OrderService is not created yet
       |
       v
Circular creation failure
~~~

This is a helpful signal. It reveals that two objects require each other during construction, which is usually a design issue worth revisiting.

Constructor injection also makes dependencies explicit, supports `final` fields, and prevents beans from being created in an incomplete state.

## 6. Why Field or Setter Injection Sometimes Masks Cycles

Spring has a mechanism supporting certain circular references between singleton beans by exposing an early reference to a bean currently in creation. With field/setter injection, in some cases the container can instantiate objects first and inject remaining dependencies afterward.

Example:

~~~java
@Service
public class OrderService {

    @Autowired
    private InventoryService inventoryService;
}
~~~

~~~java
@Service
public class InventoryService {

    @Autowired
    private OrderService orderService;
}
~~~

This mechanism has limitations and depends on bean types, lifecycles, proxies, and creation strategies. It is not a general solution for all circular dependencies.

In modern Spring Boot versions, circular references are rejected by default. Since Spring Boot 2.6, `spring.main.allow-circular-references` defaults to `false`. If re-enabled, certain singleton cycles may be handled via early references, while constructor cycles still cannot be resolved that way.

Do not switch from constructor injection to field injection solely to make startup pass. That can mask a cycle and make the dependency graph harder to reason about.

### Configuring Circular References to Be Allowed

You may encounter this setting:

~~~yaml
spring:
  main:
    allow-circular-references: true
~~~

This is a compatibility mechanism for legacy applications that have singleton cycles resolvable via early references. It does not remove the architectural cycle and does not guarantee every type of cycle can initialize.

If you must temporarily enable it when upgrading an old application, document the specific cycle, plan a refactor, and re-verify after eliminating the dependency cycle. Do not treat it as a new design convention.

## 7. Distinguishing Cycles at Different Levels

The term "circular dependency" can refer to multiple distinct problems:

| Level | Example | Tool / Symptom |
|---|---|---|
| Class/package | Package A imports B, B imports A | Code review, ArchUnit |
| Spring bean | Bean A injects B, B injects A | ApplicationContext startup, BeanCurrentlyInCreationException |
| Module/build | Gradle project A depends on B, B depends on A | Build graph or Maven reactor failure |
| Runtime service | Service A calls B, B calls back A over HTTP | Traces, network flow, integration behavior |
| Event/workflow | Event A triggers B, then B emits an event re-triggering A | Event trace, retry loop, business workflow |

The fix must match the level. Enabling CGLIB does not fix a cycle between Gradle modules. Splitting Maven dependencies does not fix two Spring beans injecting each other in the same module. Switching to events does not automatically eliminate a cycle if event handlers still call back in a runtime loop.

## 8. Solution 1: Move Orchestration into a Dedicated Use Case

A common cause of cycles is two business services calling back into each other to coordinate a workflow.

For example, `OrderService` needs to reserve stock, and `InventoryService` calls back into `OrderService` to update status. Instead of having the two services coordinate each other, place a use case above them:

~~~text
             PlaceOrderUseCase
                /       \
               v         v
        OrderService  InventoryService
               |         |
               v         v
          OrderRepository
                    InventoryRepository
~~~

Illustrative code:

~~~java
@Service
public class PlaceOrderUseCase {

    private final OrderService orderService;
    private final InventoryService inventoryService;

    public PlaceOrderUseCase(
            OrderService orderService,
            InventoryService inventoryService) {
        this.orderService = orderService;
        this.inventoryService = inventoryService;
    }

    public void place(PlaceOrderCommand command) {
        Order order = orderService.createPending(command);

        inventoryService.reserve(
                order.getId(),
                order.getItems()
        );

        orderService.confirm(order.getId());
    }
}
~~~

`OrderService` manages only order rules and status:

~~~java
@Service
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public Order createPending(PlaceOrderCommand command) {
        Order order = Order.pending(command);
        return repository.save(order);
    }

    public void confirm(OrderId id) {
        Order order = repository.getRequired(id);
        order.confirm();
        repository.save(order);
    }
}
~~~

`InventoryService` manages only inventory:

~~~java
@Service
public class InventoryService {

    private final InventoryRepository repository;

    public InventoryService(InventoryRepository repository) {
        this.repository = repository;
    }

    public void reserve(OrderId orderId, List<OrderItem> items) {
        // Check and reserve stock according to inventory policy.
    }
}
~~~

The two services no longer inject each other. `PlaceOrderUseCase` owns the orchestration sequence of the use case.

If both steps share a database and require atomicity, an appropriate transaction boundary can be placed on the application service. If inventory resides in a separate system, a local transaction cannot guarantee cross-system rollback; in that case, design a distributed workflow such as a saga or outbox.

## 9. Solution 2: Extract Shared Logic into a Separate Abstraction

Sometimes a cycle appears because two services both need a rule or data, and one service holds the logic the other needs.

Example:

~~~text
PricingService → CustomerService
      ^                 |
      |_________________|
~~~

Instead of letting both services call each other, identify the shared concept and move it into a component with its own responsibility.

If both need to check whether a customer qualifies for a promotion, create `CustomerEligibilityPolicy`:

~~~java
public interface CustomerEligibilityPolicy {
    boolean isEligible(CustomerId customerId);
}
~~~

An implementation can depend on the required repository or domain data:

~~~java
@Service
public class DefaultCustomerEligibilityPolicy
        implements CustomerEligibilityPolicy {

    private final CustomerRepository repository;

    public DefaultCustomerEligibilityPolicy(
            CustomerRepository repository) {
        this.repository = repository;
    }

    @Override
    public boolean isEligible(CustomerId customerId) {
        Customer customer = repository.getRequired(customerId);
        return customer.isEligibleForPromotion();
    }
}
~~~

Services consume the abstraction:

~~~java
@Service
public class PricingService {

    private final CustomerEligibilityPolicy eligibility;

    public PricingService(CustomerEligibilityPolicy eligibility) {
        this.eligibility = eligibility;
    }
}
~~~

~~~java
@Service
public class CustomerService {

    private final CustomerEligibilityPolicy eligibility;

    public CustomerService(CustomerEligibilityPolicy eligibility) {
        this.eligibility = eligibility;
    }
}
~~~

New graph:

~~~text
PricingService ────────┐
                       v
          CustomerEligibilityPolicy
                       ^
CustomerService ───────┘
                       |
                       v
              CustomerRepository
~~~

Pay attention to where the abstraction lives. If the policy belongs to customer domain logic, place it in the module/domain owning that concept or in an appropriate contract layer. Do not dump everything into a `common` package just to break a cycle; shared modules need clear responsibility and ownership.

## 10. Solution 3: Invert Dependency Direction Using Dependency Inversion

A cycle often emerges when a high-level module depends directly on a low-level module's implementation, while that implementation also calls back into the high-level module.

Poor example:

~~~text
OrderApplicationService → HttpPaymentAdapter
HttpPaymentAdapter → OrderApplicationService
~~~

Instead of having the application depend on the adapter, define a port on the application side:

~~~java
package com.example.orders.application.port.out;

public interface PaymentPort {
    PaymentResult authorize(PaymentRequest request);
}
~~~

The use case depends on the port:

~~~java
package com.example.orders.application;

import com.example.orders.application.port.out.PaymentPort;

@Service
public class PlaceOrderService {

    private final PaymentPort paymentPort;

    public PlaceOrderService(PaymentPort paymentPort) {
        this.paymentPort = paymentPort;
    }

    public PaymentResult pay(PaymentRequest request) {
        return paymentPort.authorize(request);
    }
}
~~~

The adapter depends on the port and supplies the implementation:

~~~java
package com.example.orders.infrastructure.payment;

import com.example.orders.application.port.out.PaymentPort;

@Component
public class HttpPaymentAdapter implements PaymentPort {

    private final PaymentHttpClient client;

    public HttpPaymentAdapter(PaymentHttpClient client) {
        this.client = client;
    }

    @Override
    public PaymentResult authorize(PaymentRequest request) {
        return client.authorize(request);
    }
}
~~~

Compile-time graph:

~~~text
PlaceOrderService → PaymentPort
HttpPaymentAdapter → PaymentPort
HttpPaymentAdapter → PaymentHttpClient
~~~

There is no longer a `PlaceOrderService → HttpPaymentAdapter` edge. Spring injects the adapter into the port at context startup, yet the application only knows the abstraction.

This is an application of DIP and ports-and-adapters (hexagonal) architecture.

### Do Not Place the Port on the Wrong Side Just to Flip an Arrow

If the port is defined in the infrastructure module and the application must import it, the application still depends on the detail module. The abstraction must belong to the module owning the need, or a stable contract module on which both sides depend.

## 11. Solution 4: Use Events When Components Do Not Need Synchronous Calls

When one service needs to notify that something "has completed" so other components can react, you can use an event instead of a direct reverse call.

Example:

~~~text
OrderService
    |
    | publish OrderPlaced
    v
Application event bus
    |
    +------> Inventory handler
    |
    +------> Notification handler
    |
    +------> Analytics handler
~~~

Define the event:

~~~java
public record OrderPlaced(
        OrderId orderId,
        List<OrderItem> items
) {
}
~~~

Publisher:

~~~java
@Service
public class PlaceOrderService {

    private final OrderRepository repository;
    private final ApplicationEventPublisher events;

    public PlaceOrderService(
            OrderRepository repository,
            ApplicationEventPublisher events) {
        this.repository = repository;
        this.events = events;
    }

    public Order place(PlaceOrderCommand command) {
        Order order = repository.save(Order.create(command));

        events.publishEvent(
                new OrderPlaced(order.getId(), order.getItems())
        );

        return order;
    }
}
~~~

Listener:

~~~java
@Component
public class InventoryOrderListener {

    private final InventoryService inventoryService;

    public InventoryOrderListener(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    @EventListener
    public void on(OrderPlaced event) {
        inventoryService.reserve(
                event.orderId(),
                event.items()
        );
    }
}
~~~

`PlaceOrderService` does not need to know `InventoryService`. It simply emits an event representing what happened.

### Events Do Not Automatically Eliminate All Coupling

Events introduce a new contract and can reduce direct dependencies, but require careful thought:

- Who owns the event's schema and semantics?
- Does the listener execute synchronously or asynchronously?
- If the listener fails, will the event be retried?
- Is eventual consistency acceptable?
- Could an event be processed more than once?
- Is idempotency required?
- Must the event be emitted only after the database commit?

With Spring application events, standard listeners may run on the publishing thread. Using `@Async` changes timing and thread execution; never assume in-memory events are persisted durably.

If post-commit handling is needed:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void on(OrderPlaced event) {
    // Handle after the transaction containing the event commits.
}
~~~

`@TransactionalEventListener` requires an active transaction and can configure fallback behavior as needed. If the application must guarantee events are never lost between database commit and message dispatch, consider a transactional outbox rather than relying solely on an in-memory event publisher.

### Avoid Business Loops Created by Events

A chain of events can still form a runtime loop:

~~~text
OrderPlaced
   → InventoryReserved
      → OrderUpdated
         → OrderPlaced
            → ...
~~~

Turning direct method calls into events is insufficient if a workflow re-emits old events or listeners do not distinguish state transitions. Design events around facts that occurred, before/after state transitions, and idempotency rules.

## 12. Separate Queries from Commands and Avoid Calling Back to Fetch Data

Some cycles arise because a service updates state while also querying another service to retrieve data it actually needs for a decision.

For example, `InventoryService` calls `OrderService.getOrder()` to read order lines, while `OrderService` calls `InventoryService.reserve()`.

If inventory only needs the list of items and order ID, pass the required data via a command:

~~~java
public record ReserveInventoryCommand(
        OrderId orderId,
        List<InventoryItemRequest> items
) {
}
~~~

The use case prepares the command:

~~~java
inventoryService.reserve(
        new ReserveInventoryCommand(order.getId(), toRequests(order))
);
~~~

Inventory does not need to know `OrderService` or query back into the order. It simply processes a contract describing the data needed for inventory operations.

Do not pass a large entity object across modules if the target module only needs a few values. Using command/query DTOs or value objects keeps dependency boundaries clean and prevents detail modules from reaching deeply into another module's aggregates.

## 13. Keep the Domain Independent of Spring and Infrastructure

In layered or hexagonal architectures, the domain should focus on business rules:

~~~java
public class Order {

    private final OrderId id;
    private OrderStatus status;

    public void confirm() {
        if (status != OrderStatus.PENDING) {
            throw new IllegalStateException(
                    "Only pending orders can be confirmed"
            );
        }

        status = OrderStatus.CONFIRMED;
    }
}
~~~

The domain does not need to know about:

- `@RestController`.
- `JpaRepository`.
- `WebClient` or `RestClient`.
- `ApplicationContext`.
- `@Autowired`.
- Datasource configuration.
- Cache or message broker implementations.

Outer adapters translate data and calls through ports.

~~~text
         Web Adapter
              |
              v
      Application Use Case
              |
              v
            Domain
              ^
              |
    Repository / API Ports
              ^
              |
       Infrastructure
~~~

In source code, infrastructure may import contracts defined in application/domain. However, domain does not import infrastructure.

This avoids cycles like:

~~~text
Order domain → JPA entity adapter → Order domain
~~~

If the domain requires a repository interface, place the interface according to architectural boundaries; the persistence implementation lives in infrastructure.

## 14. Do Not Create a `common` Module to Hide Cycles

When discovering that two modules A and B depend on each other, a common reaction is moving some classes into a `common` module:

~~~text
Module A → Common ← Module B
~~~

This can make sense if `Common` genuinely contains stable contracts or value objects shared across many modules. However, if `Common` becomes a dumping ground for every class with no clear home, it gradually turns into a central hub with massive coupling.

Before creating a shared module, ask:

1. Which business area/module does this concept actually belong to?
2. Is it truly a contract co-owned by multiple modules?
3. Which module has the authority to change it?
4. Can a small value object or command be passed instead of sharing an entire implementation?
5. Can a use case orchestrate both modules without either module calling back?

A good common module is small, stable, and has a clear API. It must not depend on the business modules that consume it.

## 15. Circular Dependencies Between Maven Modules and Gradle Projects

Circular dependencies do not exist solely among Spring beans. They can occur in the build graph.

Gradle multi-project example:

~~~text
:orders → :inventory
:inventory → :orders
~~~

If two Gradle projects require each other via direct project dependencies, the build graph has a cycle and Gradle cannot compute a normal task execution order.

Maven multi-module builds also require an ordered reactor graph. If module A declares a dependency on B and B declares a dependency on A in the same reactor, Maven cannot determine a valid build order and will report a project cycle.

### How to Break Module Cycles

- Extract stable contracts into a separate module if genuinely co-owned by multiple modules.
- Convert one dependency direction into an interface/port in the inner module.
- Merge the two modules if they lack meaningful independent boundaries.
- Move implementing adapters to an outer module.
- Use events or message contracts when modules need looser communication.

Example:

~~~text
Before:
orders → inventory
inventory → orders

After:
orders → inventory-contract
inventory → inventory-contract
~~~

Or if the inventory module needs to emit events for orders:

~~~text
orders → order-contract
inventory → order-contract
~~~

A contract module should hold stable APIs/schemas, not service implementations or Spring configurations for either side.

### Distinguishing the Build Graph from the Dependency Tree

`mvn dependency:tree` and `gradle dependencies` show resolved artifact dependencies. They are useful for seeing which library pulls in which module, but they are not complete tools for detecting all cycles in source packages or the Spring bean graph.

Use the right tool for each level:
- Maven/Gradle project graph for build-module relationships.
- ArchUnit or architecture testing tools for package/class dependencies.
- Startup stack traces and Spring context tests for bean dependencies.
- Distributed tracing/log correlation for runtime inter-service calls.

## 16. Diagnosing Circular Dependencies in Spring Boot

When an application fails to start, look for clues such as:

~~~text
The dependencies of some of the beans in the application context form a cycle
~~~

Or:

~~~text
BeanCurrentlyInCreationException:
Requested bean is currently in creation
~~~

Exact messages vary by Spring version and bean creation path. A cycle can span many beans:

~~~text
AService
  → BService
      → CService
          → AService
~~~

It does not have to involve just two classes.

### Step 1 — Read the Cycle Path

Startup failure analysis often prints the bean chain. Write down each edge in the form:

~~~text
AService → BService
BService → CService
CService → AService
~~~

Do not just delete one injection at the bottom of the stack trace without determining each bean's responsibility.

### Step 2 — Check Whether the Dependency Is Actually Needed

A bean may call another bean only to:
- Read a single field or small status.
- Send a notification.
- Write an audit entry.
- Update state belonging to another module.
- Fetch data that the caller could pass in via a command.

If so, extract a port, value object, event, or orchestrating use case.

### Step 3 — Find Where the Beans Are Created

Look for:
- `@Component`, `@Service`, `@Repository`.
- `@Bean` factory methods.
- `@Import` and component scanning.
- `@Profile` and `@ConditionalOnProperty`.
- `@Lazy`, scoped proxies, or `FactoryBean`.
- Test configurations overriding beans.

A bean may be registered from another configuration rather than the class currently being inspected.

### Step 4 — Inspect the Constructor Graph

Constructor injection makes dependencies explicit. You can build a table:

| Bean | Constructor Dependencies |
|---|---|
| OrderService | OrderRepository, InventoryService |
| InventoryService | InventoryRepository, PricingService |
| PricingService | CustomerService |
| CustomerService | OrderService |

Cycle path: `OrderService → InventoryService → PricingService → CustomerService → OrderService`.

This table helps pinpoint which use case or abstraction has misplaced responsibilities.

### Step 5 — Write a Small Context Test

Use `ApplicationContextRunner` or a focused context test to reproduce the needed bean graph. A small test confirms the cycle is eliminated without starting the full application and all external services.

If a cycle only occurs under one profile, supply the relevant properties/profiles in the test. Do not disable half the application and conclude the production graph is valid.

## 17. @Lazy and ObjectProvider: When Should They Be Used?

There are situations where a dependency genuinely needs deferred resolution, such as an optional integration called only in a rare branch or a component with a different lifecycle.

### Using @Lazy at the Injection Point

~~~java
@Service
public class ReportService {

    private final ExportService exportService;

    public ReportService(@Lazy ExportService exportService) {
        this.exportService = exportService;
    }
}
~~~

`@Lazy` at an injection point can provide a proxy that defers resolving the target until it is used. This can break certain initialization cycles because the two beans do not immediately instantiate each other's targets.

However, if the two services depend tightly on each other for normal business work, the cycle still exists in the design. Errors may simply shift from startup to method invocation time, or cause other lifecycle issues.

### Using ObjectProvider

~~~java
@Service
public class AuditCoordinator {

    private final ObjectProvider<AuditService> auditServiceProvider;

    public AuditCoordinator(
            ObjectProvider<AuditService> auditServiceProvider) {
        this.auditServiceProvider = auditServiceProvider;
    }

    public void recordIfEnabled(AuditRecord record) {
        AuditService auditService =
                auditServiceProvider.getIfAvailable();

        if (auditService != null) {
            auditService.record(record);
        }
    }
}
~~~

`ObjectProvider<T>` lets you resolve a dependency on demand, check whether a bean exists, and access flexible lookup methods.

This is appropriate when a dependency is genuinely optional or requires lifecycle-specific lazy lookup. Do not use it to hide a required constructor dependency just to get the ApplicationContext to start.

### When Not to Use Them?

Do not add `@Lazy` or `ObjectProvider` if the sole aim is avoiding fixing two services that call each other. Re-examine the use cases, data ownership, and orchestration direction first.

## 18. Events, Callbacks, and Runtime Loops

A bean graph can be acyclic while runtime workflows still create infinite loops.

Example:

~~~text
OrderPlaced event
    → Inventory handler
        → StockReserved event
            → Order handler
                → OrderUpdated event
                    → Inventory handler
                        → ...
~~~

This can happen even when individual listeners do not inject each other. Therefore, distinguish:

- **Bean dependency cycle:** Spring cannot construct the bean graph due to dependency cycles.
- **Compile-time dependency cycle:** modules/packages depend on each other cyclically.
- **Runtime call cycle:** components call back and forth during execution.
- **Event feedback loop:** events repeatedly trigger new events without a termination condition.

To handle runtime loops:

- Define events expressing facts that happened, not vague commands.
- Distinguish event types from command types.
- Track correlation IDs and causation IDs.
- Design idempotent handlers.
- Specify which states are allowed to emit subsequent events.
- Enforce retry limits and dead-letter strategies for message brokers.
- Prevent listeners from re-emitting the same event when no new business change occurred.

Event-driven architecture reduces direct coupling, but requires deliberate workflow and eventual consistency management.

## 19. Enforcing Dependency Direction with ArchUnit

Architectural rules should not live only in documentation. Use ArchUnit to verify dependencies between packages or modules in tests.

Example Gradle dependency:

~~~groovy
dependencies {
    testImplementation 'com.tngtech.archunit:archunit-junit5:<version>'
}
~~~

Replace `<version>` with the ArchUnit version managed by your project.

### Preventing Domain from Depending on Infrastructure

~~~java
import com.tngtech.archunit.core.domain.JavaClasses;
import com.tngtech.archunit.core.importer.ClassFileImporter;
import com.tngtech.archunit.lang.ArchRule;
import org.junit.jupiter.api.Test;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;

class DomainDependencyTest {

    @Test
    void domainMustNotDependOnInfrastructure() {
        JavaClasses classes = new ClassFileImporter()
                .importPackages("com.example");

        ArchRule rule = noClasses()
                .that().resideInAPackage("..domain..")
                .should().dependOnClassesThat()
                .resideInAPackage("..infrastructure..");

        rule.check(classes);
    }
}
~~~

This test checks source-level dependencies: classes in `domain` packages must not depend on classes in `infrastructure` packages.

It does not inspect all runtime relationships or remote services; review the imported scope and dependency kinds ArchUnit analyzes.

### Detecting Cycles Between Package Slices

You can check module-level slices:

~~~java
import com.tngtech.archunit.junit.AnalyzeClasses;
import com.tngtech.archunit.junit.ArchTest;
import com.tngtech.archunit.lang.ArchRule;

import static com.tngtech.archunit.library.dependencies.SlicesRuleDefinition.slices;

@AnalyzeClasses(packages = "com.example")
class ModuleCycleTest {

    @ArchTest
    static final ArchRule modulesShouldBeFreeOfCycles =
            slices()
                    .matching("com.example.(*)..")
                    .should()
                    .beFreeOfCycles();
}
~~~

The pattern `com.example.(*)..` groups subpackages into slices. For instance, `orders`, `inventory`, and `payments` can become checked slices.

If one submodule depends on another and that module depends back, ArchUnit reports a cycle. Adjust the pattern to match your actual package layout; if package structure does not reflect module boundaries, the rule may group incorrectly or miss the intended scope.

### Explicit Layer Architecture

Beyond cycles, you can verify layer dependencies:

~~~java
@ArchTest
static final ArchRule layersAreRespected =
        layeredArchitecture()
                .consideringAllDependencies()
                .layer("Web").definedBy("..web..")
                .layer("Application").definedBy("..application..")
                .layer("Domain").definedBy("..domain..")
                .layer("Infrastructure").definedBy("..infrastructure..")
                .whereLayer("Web").mayNotBeAccessedByAnyLayer()
                .whereLayer("Application").mayOnlyBeAccessedByLayers("Web",
                        "Infrastructure")
                .whereLayer("Domain").mayOnlyBeAccessedByLayers("Application",
                        "Web", "Infrastructure");
~~~

This is an illustrative example of the DSL and rule; concrete constraints must match the dependency direction chosen by your project. In hexagonal architecture, infrastructure normally depends on ports/application contracts, and the domain must not depend on infrastructure. Write layer rules to reflect your actual model rather than copying a rule set that does not fit your architecture.

ArchUnit can run in CI like normal tests. When a pull request introduces a reverse dependency or new cycle, the build fails before the change is merged.

## 20. Controlling Modules with Spring Modulith

For Spring Boot applications organized into application modules, Spring Modulith can help define module boundaries, inspect inter-module relationships, and test structural rules.

A module can expose allowed APIs while keeping internal packages encapsulated. This prevents every module from directly importing each other's implementation classes.

Conceptual verification test example:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ApplicationModuleTests {

    @Test
    void verifiesModuleStructure() {
        ApplicationModules.of(Application.class).verify();
    }
}
~~~

Add the matching Spring Modulith dependency and configure module boundaries per your version. `Application` in the example is the application's main class.

Spring Modulith does not replace architectural design. It turns module rules into automated checks, especially when an application hosts multiple modules within a single Spring Boot deployment.

## 21. Organizing Packages by Feature to Reduce Coupling

A structure split solely by technical layers:

~~~text
com.example
├── controller
├── service
├── repository
├── entity
└── config
~~~

can mix all features into the same packages. A new feature easily requires edits across many areas and encourages cross-feature dependencies.

Feature-based organization:

~~~text
com.example
├── orders
│   ├── web
│   ├── application
│   ├── domain
│   └── infrastructure
├── inventory
│   ├── application
│   ├── domain
│   └── infrastructure
└── payments
    ├── application
    ├── domain
    └── infrastructure
~~~

Each feature owns its own responsibilities. When another module needs functionality, it uses the published API/port instead of importing internal repositories or implementations.

Not every feature needs every subpackage. For small modules, keep the layout simple; create layers only when they express meaningful boundaries.

### Public API vs. Internal Implementation

Example inventory module API:

~~~java
package com.example.inventory.api;

public interface InventoryReservation {
    ReservationResult reserve(ReservationRequest request);
}
~~~

Internal implementation:

~~~java
package com.example.inventory.internal;

@Service
class InventoryReservationService implements InventoryReservation {
    // ...
}
~~~

Other modules depend on the API package. Implementations are kept package-private or guarded via appropriate module boundaries.

This enables changing persistence or inventory algorithms without forcing the `orders` module to know internal details.

## 22. Complete Refactoring Example: From Cycle to DAG

Suppose the initial code is:

~~~java
@Service
public class OrderService {

    private final InventoryService inventory;

    public OrderService(InventoryService inventory) {
        this.inventory = inventory;
    }

    public void place(Order order) {
        inventory.reserve(order);
    }

    public void markReserved(OrderId id) {
        // Update order status.
    }
}
~~~

~~~java
@Service
public class InventoryService {

    private final OrderService orders;

    public InventoryService(OrderService orders) {
        this.orders = orders;
    }

    public void reserve(Order order) {
        // Check stock...
        orders.markReserved(order.getId());
    }
}
~~~

The cycle occurs because `inventory` calls back into `order` to finish the workflow.

### Step 1 — Identify Who Owns the Sequence

Place the order placement sequence in an application use case:

~~~java
@Service
public class PlaceOrderUseCase {

    private final OrderService orders;
    private final InventoryService inventory;

    public PlaceOrderUseCase(
            OrderService orders,
            InventoryService inventory) {
        this.orders = orders;
        this.inventory = inventory;
    }

    public void place(PlaceOrderCommand command) {
        Order order = orders.createPending(command);

        inventory.reserve(
                order.getId(),
                order.getItems()
        );

        orders.markReserved(order.getId());
    }
}
~~~

### Step 2 — Keep OrderService Owning Order State

~~~java
@Service
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public Order createPending(PlaceOrderCommand command) {
        return repository.save(Order.pending(command));
    }

    public void markReserved(OrderId id) {
        Order order = repository.getRequired(id);
        order.markReserved();
        repository.save(order);
    }
}
~~~

### Step 3 — Keep InventoryService Owning Inventory

~~~java
@Service
public class InventoryService {

    private final InventoryRepository repository;

    public InventoryService(InventoryRepository repository) {
        this.repository = repository;
    }

    public void reserve(
            OrderId orderId,
            List<OrderItem> items) {
        // Check availability and reserve stock.
    }
}
~~~

### Step 4 — Verify the New Graph

~~~text
PlaceOrderUseCase
       |       |
       v       v
 OrderService  InventoryService
       |       |
       v       v
 OrderRepository
           InventoryRepository
~~~

The two specialized services no longer call each other. The application use case is the orchestrating node. The dependency graph is now acyclic.

### Step 5 — Determine Consistency Semantics

If `order` and `inventory` share a database, consider a shared transaction boundary depending on the persistence model.

If `inventory` is an independent service, reservation can fail after the order is created. In that case, you need an intermediate state such as `PENDING_INVENTORY`, compensation, or a saga. Do not assume a local `@Transactional` can roll back data in a remote service.

### Step 6 — Write Tests for the New Responsibilities

- Unit test `PlaceOrderUseCase` to verify collaborator call sequence.
- Unit test `OrderService` to verify order state rules.
- Unit test `InventoryService` to verify inventory policies.
- Integration test persistence adapters or APIs as needed.

Each test focuses on a single contract and does not need to instantiate all three real services unless that is the test's objective.

## 23. Anti-patterns That Commonly Create Dependency Cycles

### Two Services Calling Each Other to Orchestrate

If A calls B and B calls A to complete the same use case, an application service sitting above them is probably missing.

### Business Services Calling Back into Controllers

Controllers are inbound adapters handling requests. Domain/application services should not depend on web controllers to send responses or read request data. Pass needed data via commands/context.

### Repositories Depending on Services

Repositories should focus on persistence. If a repository injects a business service, responsibility boundaries are usually inverted. Let services call repositories, not repositories orchestrate services.

### Lower Layers Depending on Higher Layers

For example, the domain importing a controller or infrastructure importing a concrete use case implementation. Move the contract to the module owning the need and have the adapter implement that contract.

### Shared Utilities Containing Business Logic

A `common` or `util` package can gradually accrue dependencies on many modules. Keep logic in the module owning the concept; utilities should hold only genuinely generic, stable, low-dependency functions.

### Using @Lazy for Every Cycle

`@Lazy` can defer initialization, but it does not separate two coupled responsibilities. If each service needs the other in almost every operation, refactor instead of deferring failures.

### Enabling allow-circular-references Application-Wide

This allows singleton cycles resolvable via early references to persist. It weakens early detection and can make the application rely on fragile initialization behavior.

### Using Events for Every Method Call

Events fit when decoupling producers from consumers or modeling business occurrences. If the caller needs an immediate synchronous result, an explicit interface call can be simpler and easier to follow.

## 24. Design Checklist Before Adding a New Dependency

Before injecting a bean into a service, ask:

1. Which module owns this bean, and does that module own the contract being used?
2. Does the caller need a stable API, or is it depending on a concrete implementation?
3. Is there any reverse dependency path from the injected module back to the caller?
4. Can required data be passed via a command/value object instead of calling back to read it?
5. Is an application use case needed to coordinate two collaborators?
6. Can shared logic be extracted into a policy or abstraction with a clear owner?
7. Is this synchronous communication or a time-decoupled event?
8. If using events, are retries, idempotency, outbox, or eventual consistency required?
9. Does the dependency couple the domain to frameworks or infrastructure?
10. Can an architecture test be written to prevent a similar cycle from returning?

A new dependency is not inherently bad. However, if it forces a module to learn internal details or call back, review the boundaries before adding the constructor parameter.

## 25. Refactoring Workflow When a Circular Dependency Already Exists

When a cycle is discovered in existing code:

**1. Map the current graph.** List nodes and edges in one consistent direction where `A → B` means A depends on B.

**2. Find the shortest cycle.** Trace a path from a node back to itself. For large graphs, analyze by package/module first, then drill down to beans.

**3. Identify actual responsibilities.** Determine which service orchestrates the workflow, which owns business rules, and which merely provides infrastructure.

**4. Choose the cycle-breaking technique based on root cause.**
- Misplaced orchestration: create an application use case.
- Both sides need the same rule: extract a policy/contract.
- Dependency points to an implementation: invert via a port.
- Communication does not need to be synchronous: consider an event.
- Modules lack independent boundaries: merge or re-partition modules.

**5. Replace dependencies incrementally.** Keep public APIs stable where possible, refactor implementations, and update tests alongside changes.

**6. Check lifecycle and transactions.** Especially when converting direct calls into events or remote calls, evaluate commit, rollback, retry, and consistency semantics.

**7. Run tests at the right layers.** Unit tests for logic, context tests for the bean graph, integration tests for adapters, and architecture tests for dependency direction.

**8. Remove workarounds.** Once the cycle is eliminated, remove `@Lazy` or `allow-circular-references` if they were previously added only to bypass errors.

**9. Enforce the rule in CI.** Use ArchUnit or module verification to catch new dependency cycles.

## 26. Distinguishing Bean Creation Errors from Method Call Loops

An application can start up successfully yet still have a runtime dependency loop in the form of mutual calls. For example, A calls B and B calls A without a stopping condition. That is not a Spring bean circular creation error.

Conversely, two beans can form a circular dependency at startup even if their methods never call each other. Circular constructor dependencies alone are enough.

| Situation | When Detected | Symptom |
|---|---|---|
| Constructor bean cycle | ApplicationContext startup | BeanCurrentlyInCreationException |
| Field/setter singleton cycle | Startup, depending on configuration | May be resolved or rejected |
| Runtime method recursion | When methods are invoked | StackOverflowError or repeating call chain |
| Event feedback loop | When events are processed | Repeating events, retries, growing message volume |
| Module dependency cycle | Build configuration/build graph | Maven/Gradle cannot compute build order |

Diagnosing the right kind of cycle leads to the right fix. Do not change Spring bean scopes or proxy strategies when the real issue is runtime recursion.

## 27. Measuring Dependency Graph Quality

Beyond checking "is there a cycle," watch for these signals:

- One module is depended upon by too many other modules.
- One module depends on many unrelated modules.
- A `common` package changes frequently and is imported by every feature.
- A small change in one module forces many other modules to rebuild/retest.
- Public interfaces expose too many infrastructure classes.
- The domain module depends on Spring/JPA/HTTP just to use a few annotations.
- Tests require heavy integration setups because component boundaries are unclear.

You do not need to optimize every metric to a fixed number. Use the dependency graph to understand coupling and locate areas with broad blast radius or unclear ownership.

A stable module with a small contract and few dependencies is usually easier to reuse than a central module packed with implementations.

## 28. Summary of Design Principles

An understandable dependency graph typically exhibits these traits:

- Every edge has a clear direction and reason.
- High-level modules depend on abstractions, not concrete implementation details.
- The domain stays independent of web, persistence, and frameworks.
- Application services orchestrate use cases; specialized collaborators do not call back to coordinate each other.
- Events are used when communication genuinely fits an event model and its semantics are accepted.
- Package/module dependencies are guarded by architecture tests.
- Workarounds like `@Lazy` or allowing circular references are used only for specific lifecycle needs, not as substitutes for refactoring.

**Keep dependency relationships explicitly directed and favor DAGs across architectural boundaries.** When a cycle appears, identify who owns the use case, who owns the business rules, and which side should own the abstraction. Separating orchestration, inverting dependencies, passing data via contracts, or using deliberate events produces a graph that is easier to initialize, test, and evolve.
