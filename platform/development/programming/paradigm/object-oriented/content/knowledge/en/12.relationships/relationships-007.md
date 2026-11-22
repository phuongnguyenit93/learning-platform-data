# Circular dependencies and how to break them in Java OOP design

> **Goal:** Identify circular dependencies between classes, objects, packages, modules, or beans; understand their practical consequences; and refactor to unidirectional collaboration without changing business behavior.

## 1. What is a circular dependency?

Suppose `OrderService` needs `ShippingService` to ship orders, but `ShippingService` calls back into `OrderService` to update order status.

~~~mermaid
flowchart LR
    O[OrderService] -->|cần để giao hàng| S[ShippingService]
    S -->|gọi để đổi trạng thái| O
~~~

This is a **directed cycle** in the dependency graph: starting from `OrderService`, following dependencies eventually leads back to itself. In a larger system, the cycle may be longer: `A → B → C → A`.

Several concepts must be distinguished:

- **Design-level dependency:** `A` needs the API, behavior, or structure of `B` to fulfill its responsibility. Mutual dependencies between classes or modules make changes and tests harder to isolate.
- **Object-construction cycle:** creating `A` requires `B`, but creating `B` requires `A`. If both must be supplied through constructors, the pair cannot be assembled in the usual way.
- **Runtime call cycle:** `A.method()` calls `B.method()`, and `B.method()` calls `A.method()` again without a termination condition. This can cause `StackOverflowError` even if the code compiles and objects have been initialized.
- **Reference cycle in an object graph:** `Parent` contains `Child`, and `Child` retains a `parent` reference for navigation. This is **not necessarily** a design defect or a Java memory leak; whether it is appropriate depends on the model, API, and lifecycle management.
- **Module/build cycle:** module `orders` depends on `shipping` while `shipping` depends on `orders`. Build tools may reject project/module cycles, even though two classes in the same compilation unit or source set can reference each other.

So the main question is not "are there arrows pointing in both directions?" but **do these responsibilities require mutual knowledge of implementation details, making initialization, testing, replacement, or evolution difficult?**

## 2. Example of a design with a cycle

The following code shows two services that require each other through their constructors:

~~~java
final class OrderService {
    private final ShippingService shippingService;

    OrderService(ShippingService shippingService) {
        this.shippingService = shippingService;
    }

    void confirm(String orderId) {
        shippingService.schedule(orderId);
    }

    void markShipped(String orderId) {
        System.out.println("Order shipped: " + orderId);
    }
}

final class ShippingService {
    private final OrderService orderService;

    ShippingService(OrderService orderService) {
        this.orderService = orderService;
    }

    void schedule(String orderId) {
        // Giả lập thao tác giao hàng
        orderService.markShipped(orderId);
    }
}
~~~

The class definitions compile when compiled together, but constructing the objects becomes a circular problem:

~~~java
// Không thể có đối tượng hoàn chỉnh để truyền vào ngay từ đầu.
// OrderService order = new OrderService(shipping);  // shipping chưa tồn tại
// ShippingService shipping = new ShippingService(order); // order chưa tồn tại
~~~

Passing `null`, using setters to "patch" the cycle, or creating partially initialized objects weakens design safety; an object might be invoked before its dependencies are ready. A DI container must also confront the construction cycle.

**Design cause:** `OrderService` both confirms orders and orchestrates shipping, while `ShippingService` both handles shipping and knows how to update order business state. The two responsibilities are entangled through two-way calls.

## 3. Breaking the cycle with a clearly responsible coordinator

A sensible refactoring introduces a **use-case coordinator** responsible for "placing an order and requesting shipment," while lower-level components perform separate tasks.

~~~mermaid
flowchart TD
    C[CheckoutCoordinator] --> R[OrderRepository]
    C --> G[ShippingGateway]
    R --> D[(Order data)]
    G --> E[Hệ thống vận chuyển]
~~~

In this design, `OrderRepository` never calls back into `CheckoutCoordinator`, and `ShippingGateway` does not depend on the coordinator either. Components used by the same coordinator need not know one another.

**Complete Java 17+ example, runnable as a standalone `OrderFlowDemo.java` file:**

~~~java
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;

record Order(String id, long totalCents) {
    Order {
        Objects.requireNonNull(id, "id");
        if (id.isBlank() || totalCents <= 0) {
            throw new IllegalArgumentException("Invalid order");
        }
    }
}

interface OrderRepository {
    void save(Order order);
    Order findById(String id);
}

final class InMemoryOrderRepository implements OrderRepository {
    private final Map<String, Order> data = new ConcurrentHashMap<>();

    @Override
    public void save(Order order) {
        data.put(order.id(), order);
    }

    @Override
    public Order findById(String id) {
        return data.get(id);
    }
}

interface ShippingGateway {
    void requestShipment(Order order);
}

final class ConsoleShippingGateway implements ShippingGateway {
    @Override
    public void requestShipment(Order order) {
        System.out.println("Request shipment for " + order.id());
    }
}

final class CheckoutCoordinator {
    private final OrderRepository orders;
    private final ShippingGateway shipping;

    CheckoutCoordinator(OrderRepository orders, ShippingGateway shipping) {
        this.orders = Objects.requireNonNull(orders, "orders");
        this.shipping = Objects.requireNonNull(shipping, "shipping");
    }

    void checkout(Order order) {
        Objects.requireNonNull(order, "order");
        orders.save(order);
        shipping.requestShipment(order);
    }
}

public class OrderFlowDemo {
    public static void main(String[] args) {
        OrderRepository repository = new InMemoryOrderRepository();
        ShippingGateway shipping = new ConsoleShippingGateway();
        CheckoutCoordinator checkout = new CheckoutCoordinator(repository, shipping);

        Order order = new Order("ORD-42", 250_000);
        checkout.checkout(order);

        System.out.println(repository.findById("ORD-42"));
    }
}
~~~

Run `javac OrderFlowDemo.java` followed by `java OrderFlowDemo` with JDK 17 or later. Expected output:

~~~text
Request shipment for ORD-42
Order[id=ORD-42, totalCents=250000]
~~~

Important points about this code:

1. **The dependency graph is unidirectional:** `CheckoutCoordinator` knows two ports (`OrderRepository`, `ShippingGateway`); neither port needs a reference back to the coordinator.
2. **Constructor injection:** both collaborators are supplied when the object is constructed, and `Objects.requireNonNull` ensures they are present.
3. **Ports are small interfaces:** the repository manages storage; the gateway handles shipment requests. Concrete implementations can change without modifying the business flow.
4. **Responsibilities have clear boundaries:** orchestration belongs in the coordinator instead of being spread across services that call each other.
5. **Do not gloss over transactional failures:** this code illustrates dependency structure only; saving an order successfully but failing to request shipment can leave inconsistent state. Real systems need suitable transactions, retries/idempotency, or a *transactional outbox* for communication between a database and an external system.

**Note:** Introducing an interface **does not automatically break a cycle**. With `OrderService → ShippingPort → ShippingService → OrderService`, the **bean/implementation graph** is still cyclic even though one edge goes through an abstraction. The interaction direction or actual responsibilities must change.

## 4. Ways to break cycles and when to use them

| Approach | Idea | Suitable when | Pitfall to avoid |
|---|---|---|---|
| **Extract shared responsibility** | Move shared logic into an independent `Policy`, `Calculator`, or domain service | Both components call each other only to reuse the same rule | Creating a giant `Utils` class and losing domain boundaries |
| **Coordinate at a higher layer** | A coordinator/use case invokes components in order | Two services call back to complete one workflow | Coordinator takes over all logic and becomes a "god object" |
| **Dependency Inversion** | Define a small port at the appropriate layer and implement it in a lower layer | The business layer depends directly on infrastructure | Merely renaming or inserting an interface while the runtime graph stays cyclic |
| **Domain event / message** | A publisher announces events; registered handlers react | Handling reactions to state changes without direct calls | Synchronous events can still nest calls or recurse; async requires idempotency and error observability |
| **Extract a contract module** | Move shared DTOs/interfaces to an independent module | Projects/modules import each other only for shared types | Moving all business logic into "common" |
| **Merge components with truly shared responsibility** | A new component owns one invariant and lifecycle | Original boundaries were artificially split | Merging merely to pass a build check and creating a huge class |
| **Remove unnecessary dependencies** | Pass minimal data such as IDs/values instead of an entire service | Calls exist only to retrieve a few fields or status values | Moving all state through redundant DTOs and creating new coupling |

Choose based on **the cycle's root cause**. If two classes merely share a fee-calculation function, extracting that calculation is often simplest. If both orchestrate a process, move the workflow into a coordinator. If two packages import each other for a few types, extracting a contract module may be appropriate. There is no need for an event bus in a simple synchronous workflow merely to make the arrows look cleaner.

## 5. Extracting a shared dependency: from A ↔ B to A → C ← B

Suppose `InvoiceService` needs `DiscountService` for pricing, but `DiscountService` calls back into `InvoiceService` only to learn the maximum discount. This design places the "maximum discount" rule in the wrong class.

**Before:**

~~~mermaid
flowchart LR
    I[InvoiceService] --> D[DiscountService]
    D --> I
~~~

**After:** extract the discount rule into an independent policy.

~~~mermaid
flowchart TD
    I[InvoiceService] --> P[DiscountPolicy]
    D[DiscountService] --> P
~~~

Example Java classes (in one file or their corresponding separate files):

~~~java
final class DiscountPolicy {
    // Dùng long vì đơn vị là cents; không dùng double cho tiền.
    long apply(long originalCents, int percent) {
        if (originalCents < 0 || percent < 0 || percent > 30) {
            throw new IllegalArgumentException("Invalid discount");
        }
        long discount = Math.multiplyExact(originalCents, percent) / 100;
        return originalCents - discount;
    }
}

final class InvoiceService {
    private final DiscountPolicy policy;

    InvoiceService(DiscountPolicy policy) {
        this.policy = policy;
    }

    long amountAfterDiscount(long cents, int percent) {
        return policy.apply(cents, percent);
    }
}

final class DiscountService {
    private final DiscountPolicy policy;

    DiscountService(DiscountPolicy policy) {
        this.policy = policy;
    }

    long quote(long cents, int percent) {
        return policy.apply(cents, percent);
    }
}
~~~

Both `InvoiceService` and `DiscountService` know `DiscountPolicy`, but need not know each other. `Math.multiplyExact` signals an error if integer multiplication overflows `long`; even when `long` represents cents, business rounding rules are needed, and this example uses integer division.

A `DiscountPolicy` object is an independent, stateless component across calls; sharing one instance or creating separate instances depends on application lifecycle and configuration.

## 6. Dependency Inversion: what direction actually changes?

In layered design, the domain should generally not import infrastructure directly.

**Design dependent on implementation:**

~~~mermaid
flowchart LR
    S[ApplicationService] --> J[JdbcOrderRepository]
~~~

**Design depending on a contract owned by the business layer:**

~~~mermaid
flowchart LR
    S[ApplicationService] --> P[OrderRepository interface]
    J[JdbcOrderRepository] -. implements .-> P
~~~

The `OrderRepository` port belongs in an appropriate application/domain module, and the `JdbcOrderRepository` adapter implements it. The adapter's package/module can depend on the contract, while the application service no longer depends directly on the adapter. This **inverts the source-code dependency** even though a real adapter object is still injected into the service at runtime.

Do not inspect only the imports in one file. If runtime wiring looks like:

~~~text
A -> PortB -> ImplementationB -> A
~~~

then **the object dependency cycle still exists**. Examine both **the class graph** and **the instantiated component graph**; they are not always identical.

## 7. Domain events can break direct calls, but need clear boundaries

Rather than have `OrderService` call `EmailService` and then have `EmailService` call back into `OrderService` to find an order, the domain can publish `OrderPlaced(orderId, customerId)`. An independent handler reads the required data and sends an email:

~~~mermaid
flowchart LR
    O[PlaceOrderUseCase] --> R[(OrderRepository)]
    O --> E[OrderPlaced event]
    E --> H[SendEmailHandler]
    H --> M[EmailGateway]
~~~

Use an event only when "the order was placed" is a **meaningful domain event**. If handlers need to query data, define a stable contract boundary (IDs or a minimal snapshot) rather than sending an entire ORM entity with lazy-loaded state through messages.

Distinguish three cases:

- **Synchronous event in the same process:** reduces direct coupling, but handlers still execute on the publisher's call stack. If a handler triggers the original event again, it may cause infinite recursive calls.
- **Asynchronous event:** the publisher does not wait for the handler on the same stack, but must handle at-least-once delivery, retries, duplicate messages, ordering, and eventual consistency.
- **Transactional outbox:** write data changes and an outbox record in the same database transaction, then have a worker turn outbox records into messages. Duplicate publication and consumer idempotency still need handling; an outbox does not guarantee end-to-end exactly-once delivery by itself.

If sending email does not determine whether an order can be created, an event may be appropriate. If the rules require an inventory check **before** confirming an order, a synchronous call with a clear contract may be easier to control.

## 8. Spring bean cycles and how to address them

The following example illustrates a cycle created by **constructor injection**:

~~~java
import org.springframework.stereotype.Service;

@Service
class OrderApplicationService {
    OrderApplicationService(ShippingApplicationService shipping) {
    }
}

@Service
class ShippingApplicationService {
    ShippingApplicationService(OrderApplicationService orders) {
    }
}
~~~

When the application context needs both singleton beans, neither can be fully constructed first and supplied to the other. Spring generally reports a circular-dependency initialization error, such as `BeanCurrentlyInCreationException` or a cycle analysis, depending on version and wiring.

**Design-level fix:** restructure into a `CheckoutCoordinator` using independent ports, as in section 3. Spring injects implementations through constructors, leaving a unidirectional runtime graph. With Spring annotations, coordinator/adapter classes may use `@Service`/`@Repository` or be configured through `@Bean`; get the architecture right before wiring it.

Workarounds have limitations:

- `@Lazy` on one edge can delay bean resolution but **does not turn** a logical cycle into a healthy graph. If operations still call each other recursively, the problem remains.
- `ObjectProvider<T>` or `Provider<T>` supports late dependency lookup and can help with dynamic scope/lifecycle needs, but is not the default remedy for architectural cycles.
- Setter/field injection can allow certain singleton cycles to initialize under suitable configuration, but objects may be used before all dependencies are ready; cyclic method calls still exist.
- Allowing circular references in configuration (if supported by the framework version) is **a temporary compatibility workaround**, not a replacement for correcting responsibilities.

**Another pitfall:** `@Transactional`, `@Async`, AOP proxies, and initialization callbacks can affect when beans are accessed. During refactoring, review transaction boundaries, proxy-mediated calls, exceptions, rollbacks, and event publication to avoid accidentally changing transaction semantics.

## 9. Circular dependencies at package and module levels

Suppose a Java project has this structure:

~~~text
orders/
    OrderService.java      -> import shipping.ShippingService
shipping/
    ShippingService.java   -> import orders.OrderService
~~~

Two packages in the same module may still compile, but the design creates an architectural cycle. With separate projects/modules, if `orders` depends on `shipping` while `shipping` depends on `orders`, the build system may be unable to find a valid build order. In the Java Platform Module System (JPMS), the `requires` graph between named modules may not contain cycles.

One possible organization:

~~~text
order-contract/
    OrderId.java
    ShippingRequest.java
orders/
    OrderService.java      -> order-contract
shipping/
    ShippingAdapter.java   -> order-contract
application/
    CheckoutCoordinator.java -> orders, shipping, order-contract
~~~

`order-contract` should contain only genuinely shared, stable contracts, not become a dumping ground for models and utilities. A dependency from the application to both adapters may be appropriate at the **composition root** where components are constructed, but application business logic should prefer interfaces and avoid importing concrete adapters.

For system modules, examine **build-time edges** (project dependencies), **compile-time edges** (imports/type references), and **runtime edges** (bean/provider wiring). Breaking an import cycle does not guarantee the runtime cycle is gone.

## 10. Diagnosing and refactoring with control

A practical process:

1. **Draw the real edges:** record which class/module depends on which, why, and whether the dependency is through a constructor, field, static call, or callback. Do not infer dependencies from names alone.
2. **Identify the level:** is the cycle in imports/project modules, bean constructors, runtime calls, or an ordinary object graph? A cycle at one level need not exist at another.
3. **Trace why each edge is needed:** does the caller need the whole service or just a value, rule, or event notification? Use this to identify misplaced responsibilities.
4. **Choose a meaningful cut:** eliminate unnecessary calls, extract a policy, move orchestration to a use case, use a correctly placed port, or extract shared contracts to an independent module.
5. **Migrate callers one by one:** update constructors, methods, and dependency-injection configuration. Avoid keeping old aliases indefinitely if they recreate the cycle.
6. **Test behavior:** preserve important operation order, results, exceptions, transactions, and state. For public APIs, assess source and binary compatibility.
7. **Recheck the graph:** inspect both static architecture and runtime wiring; try starting the application in a clean context.
8. **Monitor operational limitations:** for events, watch retries/duplicates and temporarily inconsistent states; for coordinators, avoid making them responsible for everything.

Example diagnostic commands (depending on the build tool):

~~~bash
# Maven: xem quan hệ dependency giữa các artifact
mvn dependency:tree

# Gradle: xem project dependencies ở cấu hình phù hợp
./gradlew dependencies

# JDK: phân tích phụ thuộc class/package của mã đã biên dịch
jdeps -verbose:class -filter:none -cp target/classes target/classes
~~~

Interpret the results according to their scope: `mvn dependency:tree` and `gradlew dependencies` show artifact/project relationships, **not enough** to find call cycles between every class. `jdeps` analyzes static bytecode dependencies but cannot fully see reflection, dynamic callbacks, or runtime bean wiring. On Windows with Gradle, use `gradlew.bat dependencies`; `target/classes` is a common Maven example path and must be adapted to the project. Complex architectures can enforce package/module dependency rules through architecture tests.

## 11. Ensure tests detect defects, not merely successful bean creation

Using `CheckoutCoordinator`, we can test the **order** "save first, then request shipment," correct data propagation, and the absence of callbacks into the coordinator. The following JUnit Jupiter 5 test uses fakes without a mocking framework:

**`CheckoutCoordinatorTest.java`** (place it alongside the classes from `OrderFlowDemo.java` in the same package):

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.util.ArrayList;
import java.util.List;

class CheckoutCoordinatorTest {
    @Test
    void savesThenRequestsShipment() {
        List<String> calls = new ArrayList<>();

        OrderRepository repository = new OrderRepository() {
            @Override
            public void save(Order order) {
                calls.add("save:" + order.id());
            }

            @Override
            public Order findById(String id) {
                return null;
            }
        };

        ShippingGateway gateway = order ->
                calls.add("ship:" + order.id());

        CheckoutCoordinator checkout =
                new CheckoutCoordinator(repository, gateway);

        checkout.checkout(new Order("ORD-42", 250_000));

        assertEquals(List.of("save:ORD-42", "ship:ORD-42"), calls);
    }

    @Test
    void missingDependenciesAreRejectedAtConstruction() {
        OrderRepository repository = new InMemoryOrderRepository();
        ShippingGateway shipping = new ConsoleShippingGateway();

        assertThrows(NullPointerException.class,
                () -> new CheckoutCoordinator(null, shipping));
        assertThrows(NullPointerException.class,
                () -> new CheckoutCoordinator(repository, null));
    }
}
~~~

These tests protect the required contracts and interactions. A test using reflection only to confirm a `private final ShippingGateway` field, or merely searching source text for the absence of `extends`, is too implementation-dependent. For Spring applications, add **application-context startup integration tests** to catch bean cycles; with database/messaging integrations, test transactions and retries in a suitable test environment.

**Be careful about shipment failures:** the test establishes method order but does not prove atomicity across database writes and external-system actions. An integration test should cover gateway failure, the resulting order state, and recovery behavior.

## 12. Common misconceptions

| Claim | Accurate assessment |
|---|---|
| "Every reference cycle is wrong" | No. Bidirectional parent–child links can be useful; Java GC can reclaim an unreachable group when no GC-root path reaches it |
| "Adding an interface breaks the cycle" | Only if **the actual dependency graph** changes direction with no return path |
| "`@Lazy` completely solves circular dependencies" | It often merely defers initialization without fixing responsibilities or runtime call cycles |
| "An event bus solves every cycle" | Coupling may shift to schemas/events and create reaction cycles; failure/consistency complexity increases |
| "A Spring context error is the only evidence of a cycle" | Compilers, tests, runtime recursion, and package/module architecture must also be examined |
| "Bidirectional links cause memory leaks in Java" | Reference cycles alone do not prevent GC; leaks happen when GC-root references keep objects reachable |
| "The more dependencies a coordinator has, the better" | A coordinator should orchestrate use cases; distinct business rules belong in suitable components |

## 13. Application exercise: refactor course-enrollment notifications

**Original design:** `EnrollmentService` calls `NotificationService` after enrollment, but `NotificationService` calls back into `EnrollmentService` to obtain the email address and course name. Each service receives the other through constructor injection.

Rewrite it using either approach:

- **Synchronous:** `EnrollStudentUseCase` obtains information through `EnrollmentRepository`/`StudentDirectory`, saves the enrollment, and calls `NotificationGateway.sendConfirmation(recipient, courseName)`. The gateway does not call back into the use case.
- **Asynchronous:** After successful enrollment, publish `StudentEnrolled(enrollmentId)` and process notification through an independent handler. With a database and message broker, describe how an outbox, retries, and idempotency protect the workflow.

Self-check criteria: Can you draw a dependency graph **with no path back** to the use case? Can all components be constructor-injected from one composition root? Is the data sufficient at call or event boundaries? Is the enrollment state well-defined if notification fails?

---

**Remember:** To break a dependency cycle, identify **responsibilities pointing in the wrong direction**, move them to appropriate components or coordinators, then verify both **the dependency graph** and **actual behavior**. Successful initialization is necessary, but the design must also remain understandable, testable, and resilient to operational failures.
