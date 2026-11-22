# Circular dependencies and deep object navigation in OOP design

**Topic:** OOP → Design Pitfalls  
**Focus:** Recognize two design smells that often coexist — **circular dependencies** and **deep object navigation / message chains** — and refactor without breaking business behavior.

## 1. A small change can affect the entire system

Suppose a sales application has two services:

- `OrderService` accepts orders and calls `ShippingService` to arrange shipping.
- `ShippingService` needs a delivery address, so it calls back into `OrderService` for order details.

Dependency graph:

~~~mermaid
flowchart LR
    O["OrderService"] -->|gọi ship| S["ShippingService"]
    S -->|gọi findOrder / findAddress| O
~~~

In code, we might see:

~~~java
// Phác thảo mùi thiết kế — KHÔNG phải chương trình hoàn chỉnh.
final class OrderService {
    private final ShippingService shippingService;

    OrderService(ShippingService shippingService) {
        this.shippingService = shippingService;
    }

    void submit(Order order) {
        shippingService.ship(order.id());
    }
}

final class ShippingService {
    private final OrderService orderService;

    ShippingService(OrderService orderService) {
        this.orderService = orderService;
    }

    void ship(String orderId) {
        Order order = orderService.findOrder(orderId);
        // ...
    }
}
~~~

The two objects must know and reference each other. With constructor injection, we cannot construct `OrderService` without `ShippingService`, but cannot construct `ShippingService` without `OrderService` either.

Elsewhere, shipping-fee code contains:

~~~java
// Phác thảo truy cập sâu — tên getter chỉ mang tính minh họa.
String city = order.getCustomer()
                   .getContactInfo()
                   .getDeliveryAddress()
                   .getCity();
~~~

The caller must know how data is nested in `Order → Customer → ContactInfo → DeliveryAddress`. If the model replaces `getContactInfo()` with another address representation, many callers following that chain may need changes.

**Related but distinct problems:** circular dependency is **a dependency path that returns to an earlier component**; deep navigation **exposes paths through internal object structures**. A system can exhibit either one without the other.

## 2. What is a circular dependency?

In a directed graph, each vertex represents a class, service, package, or module; an edge `A → B` means `A` **depends on** `B` according to the chosen criterion (type reference, method call, import, DI configuration, build dependency, etc.).

**A cycle exists** when a path of dependency edges returns to its starting component, for example:

~~~text
A → B → C → A
~~~

| Level | Example | Possible impact |
| --- | --- | --- |
| Object/service | `OrderService → ShippingService → OrderService` | Harder initialization, unit tests, and responsibility ownership |
| Package | `order → shipping → customer → order` | Unclear package boundaries; changes spread widely |
| Module/build | `module-a → module-b → module-a` | Some module/build systems reject cycles; deployment organization becomes difficult |
| Application layer | `controller → service → controller` | Responsibility direction is reversed; architecture becomes confusing |
| Runtime call chain | `A.foo() → B.bar() → A.foo()` without a stopping condition | Can cause infinite recursion/`StackOverflowError` |

**Distinction:** a circular dependency graph does not necessarily imply infinite recursion. Two objects can reference each other but interact only one way in a particular scenario. Conversely, a function can recurse forever without a cycle between two services.

Some bidirectional references in domain models or object graphs are legitimate (for example, parent/child back-references), but still require careful ownership, lifecycle, serialization, equality, and maintenance analysis. **Not every bidirectional reference is automatically an architectural flaw.**

## 3. Why do dependency cycles cause problems?

### 3.1. Initialization with dependency injection

With constructor injection:

~~~java
// Phác thảo Spring beans.
@Service
class OrderService {
    OrderService(ShippingService shipping) { /* ... */ }
}

@Service
class ShippingService {
    ShippingService(OrderService orders) { /* ... */ }
}
~~~

Each bean requires the other before either constructor completes. Typical Spring/Spring Boot configurations detect and reject such constructor cycles during context initialization.

Workarounds such as setter injection, `@Lazy`, and `ObjectProvider` may defer bean resolution or allow some initialization scenarios, but **do not fix responsibility boundaries or dependency direction**. If a workaround is truly necessary, understand lifecycle, possible runtime failures, and architectural reasons; successful startup is not proof of sound design.

### 3.2. Tests and change propagation

Testing `OrderService` may require `ShippingService`; constructing `ShippingService` in turn requires `OrderService`. Tests become nested mocks or complicated containers instead of verification of a clear contract.

When both services know each other's structure and policies, ownership of decisions becomes ambiguous. Small contract changes can break both directions. Package/module cycles especially make independent evolution and releases costly.

### 3.3. Unclear business boundaries

An `Order ↔ Shipping` cycle sometimes means two components are trying to orchestrate the same workflow. Ask:

- Who **decides** when an order is ready for handoff?
- Who **owns** delivery-address data?
- Who **performs** the carrier call?
- Who **orchestrates** the multi-step process?
- Which component needs only values rather than knowing the other service?

There is no formula that "extracting an interface fixes it." Determine genuine responsibilities before redrawing dependency arrows.

## 4. Detecting dependency cycles in graphs

~~~mermaid
flowchart LR
    subgraph "Trước"
      O1["OrderService"] --> S1["ShippingService"]
      S1 --> O1
    end
    subgraph "Sau"
      O2["OrderWorkflow"] --> S2["ShippingService"]
      O2 --> R2["OrderRepository"]
      S2 --> G2["DeliveryGateway"]
    end
~~~

**Reading the diagram:** on the "after" side, the higher-level workflow depends on lower-level capabilities; no arrow returns from `ShippingService` to `OrderWorkflow`. This illustrates a direction, not a requirement that every project have a class named `OrderWorkflow`.

If the graph is written as an edge list:

~~~text
Trước: OrderService -> ShippingService
       ShippingService -> OrderService

Sau:   OrderWorkflow -> OrderRepository
       OrderWorkflow -> ShippingService
       ShippingService -> DeliveryGateway
~~~

A cycle forms a **strongly connected component** containing multiple vertices: every component in the group can reach the others through dependency paths. Static analysis can detect package/module cycles by examining imports or class references. But tools that only inspect imports **may miss cycles** introduced through DI configuration, reflection, or runtime calls.

During review, clarify whether the graph represents **compile-time dependencies**, **runtime beans**, or **business workflows**, because each answers a different question.

## 5. Strategies for breaking dependency cycles

| Strategy | When appropriate | What to preserve |
| --- | --- | --- |
| **Pass required data as arguments** | B calls A only to retrieve a few values already available during orchestration | Pass sufficient correct data without exposing entire internals |
| **Extract a service with its own responsibility** | Two services rely on a genuinely shared rule | The new service must own a meaningful capability, not become a third "GodService" |
| **Orchestrator/application service** | Several operations must be coordinated in order | Keep workflow decisions in one place |
| **Invert dependency using an interface/port** | Core logic directly depends on infrastructure/providers | Place abstractions at the right boundary, not merely replace a class with an interface pointing the same way |
| **Domain event** | Other components need to react after an event | Understand timing, failures, delivery semantics, and eventual consistency |
| **Split modules/ownership** | The cycle stems from shared concepts spanning modules | Redefine responsibility and dependency direction, not only package names |

Example of **passing data instead of calling back**:

~~~java
// Trước: ShippingService tự tìm đơn thông qua OrderService.
shippingService.ship(orderId); // Bên trong gọi orderService.findOrder

// Sau: tầng điều phối đã có dữ liệu và truyền yêu cầu đúng nhu cầu.
shippingService.ship(
        new ShipmentRequest(order.id(), order.shippingDestination()));
~~~

`ShippingService` no longer needs to know `OrderService`; it only knows a **request** containing the order ID and destination.

**Note:** passing an entire `Order` object may break a cycle while coupling ShippingService to a complex aggregate. Choose the minimal data that fits the responsibility, often a value object such as `ShipmentRequest` or `DeliveryAddress`.

## 6. What is Deep Object Navigation?

Consider this code:

~~~java
String city = order.getCustomer()
                   .getContactInfo()
                   .getDeliveryAddress()
                   .getCity();
~~~

This is often called a **message chain** or **train wreck** when a caller navigates multiple objects to make a decision.

The issue is not **the number of dots**. Expressions such as `Math.max(a, b)`, `stream.map(...).filter(...).toList()`, and `builder.address(...).build()` have multiple dots and may be perfectly clear. A design smell arises when callers **know too much about the structure, relationships, and internal data of collaborators**.

Three risks arise:

1. **Structural coupling:** when `Order → Customer → ContactInfo → Address` changes, every caller following that path must change.
2. **Many null/missing-data points:** any nullable link can cause `NullPointerException`; repeated null checks along the chain make code unwieldy.
3. **Misplaced responsibility:** multiple callers deriving shipping decisions from the same structure may interpret business rules inconsistently.

### Law of Demeter — "talk only to close collaborators"

A practical interpretation of the **Law of Demeter (LoD)** is to interact primarily with objects a method knows directly, instead of repeatedly calling methods on objects returned by other objects.

As a rule of thumb, prefer interacting with:

- The current object (`this`).
- Parameters passed to the method.
- Fields/direct collaborators.
- Objects created by the method or directly under its responsibility.

This is a **heuristic for coupling**, not a compiler rule or ban on chaining. Value objects/DTOs, builders, `Stream`, deliberate traversal APIs, and query projections can make method chains clear and appropriate.

**Do not "fix" LoD by hiding traversal in an arbitrary utility**, such as `DeepGetterUtil.getCity(order)`: callers may use fewer dots, but the structural dependency remains in the utility and can spread elsewhere.

## 7. Refactoring deep navigation around business intent

### Approach 1: ask the object that owns the knowledge

Instead of callers knowing the customer/contact/address graph:

~~~java
// Dễ phụ thuộc sâu vào mô hình.
String city = order.getCustomer()
                   .getContactInfo()
                   .getDeliveryAddress()
                   .getCity();
~~~

provide an API with clear meaning:

~~~java
// Order công bố thông tin tối thiểu bên ngoài cần.
DeliveryAddress destination = order.shippingDestination();
~~~

`Order` still knows how to access its own internal data. Callers no longer depend on that object graph. If address representation changes, the change is localized near its owner.

**Warning:** do not give `Order` hundreds of `getCustomerContactAddressCityCountryCode...` methods. Name APIs by business meaning (**shippingDestination**, **billingContact**, **eligibleForCancellation**) and keep only responsibilities owned by that aggregate.

### Approach 2: use a narrow Value Object/DTO

If shipping only needs an order ID and address, pass:

~~~java
record ShipmentRequest(
        String orderId,
        DeliveryAddress destination
) {}
~~~

This contract frees shipping services from knowing `Customer`, `Order`, or intermediate classes. Normalize data in a suitable boundary/assembler when needed.

### Approach 3: "Tell, Don't Ask" for behavior

When an object owns state involved in a business decision, ask it to perform the behavior:

~~~java
// Mùi thiết kế nếu logic kiểm tra bị lặp ở nhiều nơi:
if (order.getStatus() == PAID
        && !order.getItems().isEmpty()) {
    order.setStatus(SHIPPED);
}

// API có ý định rõ, bảo vệ invariant:
order.markShipped(); // tự xác nhận precondition phù hợp
~~~

This is a sketch; `markShipped()` must be designed for the actual aggregate. The key is that **external code does not arbitrarily read fields and assign state**, bypassing domain invariants.

Not every value needs to become object behavior. If a UI only shows `city` from an immutable DTO, accessing `dto.address().city()` can be clear and appropriate.

## 8. Complete Java 17 example: shipping workflow without circular dependencies

This example simulates creating a shipment request in memory. **Order** owns its order address, **OrderService** orchestrates, and **ShippingService** handles requests and depends only on **DeliveryGateway**. No arrow returns from `ShippingService` to `OrderService`.

Save as **DependencyRefactorDemo.java**:

~~~java
import java.util.Objects;

public class DependencyRefactorDemo {

    public record DeliveryAddress(String city, String street) {
        public DeliveryAddress {
            city = requiredText(city, "city");
            street = requiredText(street, "street");
        }
    }

    public record Customer(String id, DeliveryAddress address) {
        public Customer {
            id = requiredText(id, "customerId");
            Objects.requireNonNull(address, "address");
        }
    }

    public record Order(String id, Customer customer) {
        public Order {
            id = requiredText(id, "orderId");
            Objects.requireNonNull(customer, "customer");
        }

        // Công bố nhu cầu nghiệp vụ, không buộc caller lần theo Customer.
        public DeliveryAddress shippingDestination() {
            return customer.address();
        }
    }

    public record ShipmentRequest(
            String orderId,
            DeliveryAddress destination) {
        public ShipmentRequest {
            orderId = requiredText(orderId, "orderId");
            Objects.requireNonNull(destination, "destination");
        }
    }

    public record DispatchReceipt(String orderId, String trackingCode) {
        public DispatchReceipt {
            orderId = requiredText(orderId, "orderId");
            trackingCode = requiredText(trackingCode, "trackingCode");
        }
    }

    // Port: hợp đồng hạ tầng ở ranh giới gửi đơn.
    public interface DeliveryGateway {
        String dispatch(String orderId, DeliveryAddress destination);
    }

    // Fake adapter cho ví dụ; không có kết nối nhà vận chuyển thật.
    public static final class FakeDeliveryGateway implements DeliveryGateway {
        @Override
        public String dispatch(String orderId, DeliveryAddress destination) {
            Objects.requireNonNull(destination, "destination");
            return "TRACK-" + orderId;
        }
    }

    public static final class ShippingService {
        private final DeliveryGateway gateway;

        public ShippingService(DeliveryGateway gateway) {
            this.gateway = Objects.requireNonNull(gateway, "gateway");
        }

        public DispatchReceipt ship(ShipmentRequest request) {
            Objects.requireNonNull(request, "request");
            String trackingCode = gateway.dispatch(
                    request.orderId(), request.destination());
            return new DispatchReceipt(request.orderId(), trackingCode);
        }
    }

    public static final class OrderService {
        private final ShippingService shipping;

        public OrderService(ShippingService shipping) {
            this.shipping = Objects.requireNonNull(shipping, "shipping");
        }

        public DispatchReceipt requestShipment(Order order) {
            Objects.requireNonNull(order, "order");

            ShipmentRequest request = new ShipmentRequest(
                    order.id(),
                    order.shippingDestination());

            return shipping.ship(request);
        }
    }

    private static String requiredText(String value, String name) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    name + " không được rỗng");
        }
        return value.trim();
    }

    public static void main(String[] args) {
        Order order = new Order(
                "ORD-42",
                new Customer(
                        "CUS-7",
                        new DeliveryAddress("Hà Nội", "Tràng Tiền")
                )
        );

        // Composition root: lắp ráp một chiều từ ngoài.
        DeliveryGateway gateway = new FakeDeliveryGateway();
        ShippingService shipping = new ShippingService(gateway);
        OrderService orders = new OrderService(shipping);

        DispatchReceipt receipt = orders.requestShipment(order);

        System.out.println(order.shippingDestination().city());
        System.out.println(receipt.trackingCode());
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac DependencyRefactorDemo.java
java DependencyRefactorDemo
~~~

Output:

~~~text
Hà Nội
TRACK-ORD-42
~~~

### Why does this example improve both design smells?

**Dependencies:**

~~~text
OrderService → ShippingService → DeliveryGateway
OrderService → Order (dữ liệu)
ShippingService → ShipmentRequest (dữ liệu)
~~~

There is no `ShippingService → OrderService`. `OrderService` builds a **ShipmentRequest** and passes it downstream; `ShippingService` does not call back to load an address.

**Deep navigation:** previously, ShippingService could traverse `Order.Customer.Address`. After refactoring, it only knows **ShipmentRequest.destination()**. If `Order` changes how it stores customer details, ShippingService's API need not change.

**Interfaces:** `DeliveryGateway` has a real purpose: it separates shipping logic from adapters calling external systems. It is not a trick to create an interface for each class; abstraction belongs at an actual infrastructure boundary.

**Responsibilities:** `OrderService` acts as the orchestrator in this example. If more steps span inventory, payment, and shipping, an `OrderWorkflow` or suitable application service can coordinate them without circular calls among specialized services.

**Limitations:** there is no database, user authorization, transaction, or real carrier integration. `TRACK-ORD-42` is a dummy identifier; shipment handoff is not guaranteed. Real integration requires success-state definitions, acknowledgments, and retry/idempotency policies.

## 9. Unit tests demonstrating reduced coupling

With `ShippingService` depending only on `DeliveryGateway`, tests need no `OrderService` to verify request handoff. A recording fake is sufficient:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class DependencyRefactorDemoTest {

    static final class RecordingGateway
            implements DependencyRefactorDemo.DeliveryGateway {
        String lastOrderId;
        DependencyRefactorDemo.DeliveryAddress lastAddress;
        int calls;

        @Override
        public String dispatch(
                String orderId,
                DependencyRefactorDemo.DeliveryAddress destination) {
            calls++;
            lastOrderId = orderId;
            lastAddress = destination;
            return "TEST-001";
        }
    }

    @Test
    void shippingChiCanRequestVaGateway() {
        var gateway = new RecordingGateway();
        var shipping = new DependencyRefactorDemo.ShippingService(gateway);

        var address = new DependencyRefactorDemo.DeliveryAddress(
                "Đà Nẵng", "Bạch Đằng");

        var receipt = shipping.ship(
                new DependencyRefactorDemo.ShipmentRequest(
                        "ORD-1", address));

        assertEquals("ORD-1", gateway.lastOrderId);
        assertEquals(address, gateway.lastAddress);
        assertEquals(1, gateway.calls);
        assertEquals("TEST-001", receipt.trackingCode());
    }

    @Test
    void orderServiceKhongCanShippingGoiNguoc() {
        var gateway = new RecordingGateway();
        var shipping = new DependencyRefactorDemo.ShippingService(gateway);
        var orders = new DependencyRefactorDemo.OrderService(shipping);

        var order = new DependencyRefactorDemo.Order(
                "ORD-2",
                new DependencyRefactorDemo.Customer(
                        "CUS-1",
                        new DependencyRefactorDemo.DeliveryAddress(
                                "Huế", "Hùng Vương")
                )
        );

        orders.requestShipment(order);

        assertEquals("ORD-2", gateway.lastOrderId);
        assertEquals("Huế", gateway.lastAddress.city());
    }

    @Test
    void duLieuDauVaoKhongHopLeBiTuChoiSom() {
        assertThrows(IllegalArgumentException.class,
                () -> new DependencyRefactorDemo.DeliveryAddress(
                        " ", "Đường A"));
    }
}
~~~

The tests use **JUnit Jupiter 5** and belong in **DependencyRefactorDemoTest.java**. The standalone Java demo needs no JUnit. Tests verify business results at the boundary rather than depending on `Order` internals.

After refactoring production code, add integration tests for existing business cases: missing addresses, orders ineligible for shipping, gateway failures, timeouts, and duplicate requests.

## 10. Deep navigation is not always bad

A useful principle should help **make decisions**, not merely increase wrapper and method counts.

| Code | Concern? | Reason |
| --- | --- | --- |
| `order.customer().address().city()` in many business services | **Possibly** | Many callers know the aggregate structure, causing cascading changes |
| `order.shippingDestination()` | Usually clearer | Business-intent API reduces callers' knowledge of internals |
| `dto.customer().address().city()` in a mapper/view | Context-dependent | DTOs are designed for data reading; mappers often own traversal |
| `stream.filter(...).map(...).toList()` | Not automatically | An intentional API pipeline |
| `builder.address(...).note(...).build()` | Not automatically | Chaining represents object construction |
| `config.getDb().getPool().getMaxConnections()` scattered across modules | Worth reviewing | Couples many modules to deeply nested configuration |
| `apiResponse.data().items()` in a boundary adapter | Usually acceptable | Adapters map external API structures to internal types |

**Do not count dots to decide.** Ask: "If the internal structure changes but business meaning stays the same, how many callers must change?" If the answer is many and they do not own that structure, refactoring may help.

Do not "hide" traversal by putting everything in a **God object**. New methods should represent clear responsibilities that can be maintained independently.

## 11. Common pitfalls when refactoring circular dependencies

### 11.1. Extract an interface but retain the cycle

Before:

~~~text
AService → BService → AService
~~~

After merely replacing a class with an interface:

~~~text
AService → BPort → BService → APort → AService
~~~

If the real graph still points back along this path, the cycle remains. Proper refactoring requires **changing where responsibility or information flows**, not just renaming dependencies. Interfaces express boundaries; they do not cure every cycle.

### 11.2. Move everything to "CommonService"

Extracting shared logic from mutually dependent services works only if the third service has **a narrow, independent responsibility**. If it handles orders, shipping, payments, persistence, and notifications, the cycle has merely become a hard-to-maintain **God Service**.

### 11.3. Replace direct calls with events but lose timing contracts

An `OrderPaid` event may trigger Shipping without a direct call from OrderService. But ask: can shipping happen later? What if the consumer fails? Can events be duplicated? Which transaction guarantees publication?

Events **decouple communication** but do not automatically guarantee transactions, exactly-once delivery, or immediate consistency. These concerns may matter more than the original dependency cycle.

### 11.4. Duplicate state across components

To avoid deep navigation, developers sometimes copy every `Customer` field into `Order` and then let every class modify both copies, creating synchronization risks.

Distinguish:

- **Intentional snapshot:** the delivery address at order placement remains fixed even if a customer later updates their account address; that may be a valid business rule.
- **Accidental duplication:** two copies represent the same current fact and must change together; errors are likely.

Value objects or read models may intentionally duplicate data, but their authoritative source and update timing must be explicit.

## 12. Diagnosing Java/Spring projects

Signs in code, tests, and operations:

- Spring reports circular bean references, or class A requires B while B requires A.
- Many classes use `@Lazy` to hide bean cycles without explaining responsibilities.
- Unit-testing one service requires constructing a deep chain of others.
- Changing one object's field forces edits in services using `getA().getB().getC()`.
- Many helpers read data across layers but have no domain-oriented names.
- Higher-level modules import infrastructure, while infrastructure imports packages back from those modules.
- Debugging requires jumping among services to locate decisions and execution points.

### Diagnostic procedure

1. **Classify the symptom:** is it a bean cycle, compile/build cycle, runtime call cycle, or message chain?
2. **Draw current dependency edges:** what does `A → B` mean, and does a real cycle exist?
3. **Identify owners of data and behavior:** which object enforces invariants? Which service orchestrates?
4. **Determine minimal data needs:** does a caller need a value object, a decision, or an entire domain object?
5. **Choose a small refactoring:** pass parameters, move behavior, extract ports, or add an orchestrator; do not redesign everything over one getter.
6. **Write behavior tests first:** capture existing results and error paths; verify they survive refactoring.
7. **Recheck the graph:** confirm the cycle-causing edge is gone, not merely renamed to another interface.
8. **Check change propagation across modules:** internal changes should not force unrelated edits merely because of deep navigation.

IDE call hierarchies, dependency graphs, and static architecture tests (such as package-dependency tests) can help. Tools discover edges; **domain analysis still determines responsibility boundaries**.

## 13. When should these principles *not* be applied mechanically?

### Circular dependencies

In graph/tree data models with back-references (for example, a node with parent and children), reference cycles can be useful and controlled by clear invariants. The larger concerns often involve **lifecycle, ownership, serialization/recursion, and module dependencies**, not merely two arrows.

For business logic or DI, remain cautious when services orchestrate each other. Still, four interfaces, an event bus, and two adapters are not always justified for replacing one simple dependency.

### Deep navigation

Mapping a JSON response/DTO into a view may legitimately involve `response.data().user().name()`. Using `Stream` or a fluent API is not inherently contrary to the Law of Demeter.

Ask whether **the caller depends on internal structure outside its responsibility**. Reading a public data contract designed for traversal may produce acceptable coupling.

## 14. Refactoring exercise

A book-lending system has these components:

~~~text
LoanService → MemberService
MemberService → NotificationService
NotificationService → LoanService
~~~

`NotificationService` calls back into `LoanService` for the due date and contact address. The administration UI also contains many chains like:

~~~java
loan.getMember().getProfile().getContact().getEmail();
~~~

**Exercise requirements:**

1. Draw the dependency graph, identify its cycle, and locate deep-navigation code.
2. Explain what `LoanService` needs from `MemberService` and what data `NotificationService` actually requires to send notifications.
3. Design `ReminderRequest(loanId, dueDate, email)` or a suitable value object so orchestration passes data **according to need** into NotificationService.
4. Decide who owns loan states, member information, and email delivery. Do not combine everything into one service.
5. Define an interface for notification delivery if external provider separation is needed; do not reflexively create an interface for every class.
6. Unit-test correct reminder data, missing email, gateway errors, and duplicate suppression when idempotency is required.
7. Redraw the graph to demonstrate no service-layer cycles remain.
8. Explain whether `loan.member().profile().contact().email()` in a DTO mapper necessarily needs refactoring, and why.

**Assessment criteria:** easy-to-follow one-way dependencies, correct responsibility ownership, notification delivery without knowing the loan object's internal structure, unchanged error and business-result semantics, and independently constructible tests without a bean cycle.

---

**Conclusion:** *Circular dependencies* make components difficult to construct, test, and evolve independently; *deep navigation* exposes too much of the object model to callers. Improvements are not about adding interfaces or removing dots for appearances. Identify who owns data, behavior, and orchestration; pass narrow data contracts, encapsulate business decisions, and maintain clear dependency direction.
