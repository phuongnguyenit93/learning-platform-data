# Objects, State, Behavior, and Responsibility in OOP

When learning object-oriented programming (OOP), we often hear: “An object has state and behavior.” This is true, but it is not enough to design software. We also need to understand **what the object is responsible for**, because that responsibility determines which data belongs to it and which behaviors should reside within it.

Imagine an order being created: it has an order ID, a list of products, and a draft status; the buyer can add products and then confirm it. The order must enforce the rule “once confirmed, the product list cannot be modified arbitrarily.” This illustrates the connection among **object → state → behavior → responsibility**.

## 1. How Are These Four Concepts Related?

| Concept | Question to answer | Order example |
| --- | --- | --- |
| **Object** | Who or what participates in the system? | A specific order with an `orderId` |
| **State** | What data does the object currently hold, and what condition is it in? | Order lines; `DRAFT`, `CONFIRMED`, or `CANCELLED` |
| **Behavior** | What meaningful operations can the object perform? | `addLine()`, `confirm()`, `cancel()`, `total()` |
| **Responsibility** | What must the object know, decide, and guarantee? | Keep order lines valid and control order-state transitions |

These four elements are not independent. If an object provides a `confirm()` operation, that operation must read the current state, check conditions, and update the state in accordance with the object's own responsibility.

For example, confirming an order should not merely assign `status = CONFIRMED`. It must answer: *Has the order been canceled? Does it contain at least one product? Is confirming it again allowed?* If these rules are scattered across the codebase, the software can easily create orders in invalid states.

## 2. What Is an Object? Distinguishing Objects from Classes

An **object** is an entity within a program that has data and operations related to that data. It can represent something in the real world (an order or customer), a business concept (a shopping cart or credit limit), or a technical component (a buffer or file reader). Not every object has to correspond to a tangible physical thing.

A **class** generally describes shared structure and behavior; an **object (instance)** is a concrete instance created from that class.

~~~java
Order firstOrder = new Order(UUID.randomUUID());
Order secondOrder = new Order(UUID.randomUUID());

// Cùng kiểu Order nhưng là hai đối tượng riêng.
// Mỗi đối tượng có id, danh sách hàng và trạng thái của riêng nó.
~~~

Two orders can both be in the `DRAFT` state while remaining **two distinct objects**. Conversely, an order that moves from `DRAFT` to `CONFIRMED` is still *the same order*; only its state has changed.

Two perspectives on identity must be distinguished:

- **Identity in Java memory:** `firstOrder == secondOrder` checks whether two variables refer to the same object.
- **Business identity:** `orderId` identifies an order across persistence, loading from a database, or transmission through an API. Two different Java instances can represent the same `orderId`. Whether to compare them using `equals()` or an ID depends on the particular design; it is not determined automatically by the class name.

The essential distinction: **identity answers “Which entity is this?”; state answers “What is its current condition?”**

## 3. State: What an Object Currently Holds

State is the set of values associated with an object at a given moment. For an order, these include:

- **Unchanged throughout the business lifecycle:** the order identifier `id`.
- **May change through valid behaviors:** order lines while the order is in draft; `status` after confirmation or cancellation.
- **May be derived from other state:** `total()` is calculated from order-line quantities and unit prices. There is no requirement to store an additional `total` variable and keep it synchronized whenever an item is added.

Consider the same order at three points in time:

| Point in time | Order lines | Status | Total |
| --- | --- | --- | --- |
| Newly created | Empty | `DRAFT` | 0 |
| Add 2 books × 125.000 | 1 order line, quantity 2 | `DRAFT` | 250.000 |
| Successfully confirmed | Unchanged | `CONFIRMED` | 250.000 |

A **valid** state must satisfy business rules (invariants). In this example:

1. The quantity of each order line must be greater than 0, and its unit price cannot be negative.
2. Confirmed or canceled orders must not accept additional lines through `addLine()`.
3. The `confirm()` operation is allowed only when an order is `DRAFT` and has at least one order line.
4. The ID does not change simply because the order changes state.

Not all state must be mutable. An immutable object still has state; it simply remains fixed after creation. And a `private` field does not guarantee valid data by itself: methods that can modify data must still be controlled.

## 4. Behavior: What an Object Can Do

**Behavior** is an operation an object exposes to the rest of the program. In Java, behavior is usually represented by methods. A behavior may:

- **Change state:** `addLine()`, `confirm()`, `cancel()`.
- **Return information without changing state:** `total()`, `status()`.
- **Reject invalid operations:** `confirm()` reports an error for an empty order and leaves it in `DRAFT`.

Method names should express an intention from the problem domain. Compare:

~~~java
// Khó kiểm soát: mã gọi bên ngoài tự quyết định trạng thái.
order.setStatus(OrderStatus.CONFIRMED);

// Thể hiện ý nghĩa nghiệp vụ: Order tự kiểm tra điều kiện.
order.confirm();
~~~

`confirm()` is preferable here because the caller requests **“confirm this order”**, while **the object decides whether the request is valid**. This does not mean every setter is bad: data transfer objects (DTOs), configuration objects, and simple beans serve their own purposes. What matters is avoiding bypasses of important rules for objects with a business lifecycle.

Behaviors should have clearly defined **inputs, preconditions, results, and postconditions**. If an operation fails, it should not unintentionally leave data partially modified.

## 5. Responsibility: Which Rules Should an Object Own?

Responsibilities are what an object must know or guarantee to fulfill its role correctly. They provide the basis for deciding **where to place data and methods**.

| Component | Appropriate responsibility | Should not also handle |
| --- | --- | --- |
| **`Order`** | Manage order lines, calculate totals, validate order-state transitions | Send HTTP requests to payment gateways, construct SQL, send emails |
| **`PaymentService`** | Coordinate payments, call payment systems, and process results | Directly modify the order lines inside `Order` |
| **`OrderRepository`** | Persist and load orders | Decide whether an empty order can be confirmed |
| **`NotificationService`** | Send order-related notifications | Change `Order.status` on its own |

This division is not universal for every system. What matters is that the rule **“Can this order be confirmed?”** has one clearly responsible owner instead of being duplicated across controllers, services, and repositories with different conditions.

**Responsibility differs from behavior:** “Ensure valid order-state transitions” is a *responsibility*; `confirm()` and `cancel()` are *behaviors* that carry it out. An object can have multiple methods that serve one responsibility.

Well-defined responsibilities tend to exhibit **cohesion**: data and behavior serve the same purpose. If `Order` manages orders, validates JWTs, opens database connections, and sends emails, the reasons for changing that class no longer belong to one coherent group.

## 6. Complete Java Example: An Order That Protects Its Own State

The following example uses Java 17 or later (which supports `record`) and can be saved as `Main.java` and run. It illustrates in-memory rules without yet addressing database persistence or concurrent requests.

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

enum OrderStatus {
    DRAFT, CONFIRMED, CANCELLED
}

// Một dòng hàng là value object: chứa dữ liệu hợp lệ và bất biến.
record OrderLine(String sku, int quantity, BigDecimal unitPrice) {
    OrderLine {
        Objects.requireNonNull(sku, "sku");
        Objects.requireNonNull(unitPrice, "unitPrice");

        if (sku.isBlank() || quantity <= 0 || unitPrice.signum() < 0) {
            throw new IllegalArgumentException("Invalid order line");
        }
    }

    BigDecimal subtotal() {
        return unitPrice.multiply(BigDecimal.valueOf(quantity));
    }
}

final class Order {
    private final UUID id;
    private final List<OrderLine> lines = new ArrayList<>();
    private OrderStatus status = OrderStatus.DRAFT;

    Order(UUID id) {
        this.id = Objects.requireNonNull(id, "id");
    }

    UUID id() {
        return id;
    }

    OrderStatus status() {
        return status;
    }

    List<OrderLine> lines() {
        return List.copyOf(lines); // Không lộ List mutable bên trong.
    }

    BigDecimal total() {
        return lines.stream()
                .map(OrderLine::subtotal)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
    }

    void addLine(String sku, int quantity, BigDecimal unitPrice) {
        requireDraft();
        lines.add(new OrderLine(sku, quantity, unitPrice));
    }

    void confirm() {
        requireDraft();
        if (lines.isEmpty()) {
            throw new IllegalStateException("Empty order cannot be confirmed");
        }
        status = OrderStatus.CONFIRMED;
    }

    void cancel() {
        requireDraft();
        status = OrderStatus.CANCELLED;
    }

    private void requireDraft() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                    "Order must be DRAFT, actual: " + status);
        }
    }
}

public class Main {
    public static void main(String[] args) {
        Order order = new Order(UUID.randomUUID());

        System.out.println(order.status()); // DRAFT
        System.out.println(order.total());  // 0

        order.addLine("BOOK-01", 2, new BigDecimal("125000"));
        System.out.println(order.total());  // 250000

        order.confirm();
        System.out.println(order.status()); // CONFIRMED

        try {
            order.addLine("PEN-01", 1, new BigDecimal("5000"));
        } catch (IllegalStateException ex) {
            System.out.println(ex.getMessage()); // Order must be DRAFT...
        }

        System.out.println(order.total()); // Vẫn 250000

        // Nhánh thất bại độc lập, không dùng lại đơn đã xác nhận.
        Order emptyOrder = new Order(UUID.randomUUID());
        try {
            emptyOrder.confirm();
        } catch (IllegalStateException ex) {
            System.out.println(ex.getMessage()); // Empty order...
        }
        System.out.println(emptyOrder.status()); // Vẫn DRAFT

        Order cancelledOrder = new Order(UUID.randomUUID());
        cancelledOrder.cancel();
        System.out.println(cancelledOrder.status()); // CANCELLED
    }
}
~~~

**Read the example from four perspectives:**

- **Object:** `order`, `emptyOrder`, and `cancelledOrder` are three instances with distinct IDs, even though all are created from `Order`.
- **State:** `id`, `lines`, and `status` make up the data managed by `Order`. `total()` derives its result from `lines`.
- **Behavior:** `addLine()` changes the list; `confirm()` and `cancel()` change state; `total()` only calculates.
- **Responsibility:** `Order` ensures that every public operation in this example preserves the state rules. It hides its mutable list using `List.copyOf(...)` and provides no unrestricted `setStatus()` method.

Run the example:

~~~bash
javac Main.java
java Main
~~~

**Note about this example:** We deliberately define cancellation as permitted only for `DRAFT` orders. A real project may allow confirmed orders to be canceled, include refunds, or introduce `PAID`/`SHIPPED` statuses; the rules and tests must then reflect those business requirements. `BigDecimal` avoids binary floating-point errors in decimal calculations, but real monetary systems also need currency-unit, rounding, tax, and fee policies.

## 7. Object Lifecycle: State Changes Through Behavior

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT: tạo Order
    DRAFT --> DRAFT: addLine(...) hợp lệ
    DRAFT --> CONFIRMED: confirm() và có hàng
    DRAFT --> CANCELLED: cancel()
    CONFIRMED --> [*]
    CANCELLED --> [*]
~~~

The diagram shows **successful state transitions** in the example. Invalid requests (confirming an empty order, adding items after confirmation, or attempting cancellation again) are rejected and leave the state unchanged.

Trace one flow step by step:

| Step | Operation | Before | After | Observable result |
| --- | --- | --- | --- | --- |
| 1 | `new Order(id)` | Does not exist | `DRAFT`, empty | A new order exists |
| 2 | `addLine("BOOK-01", 2, 125000)` | `DRAFT`, empty | `DRAFT`, 1 line | `total() = 250000` |
| 3 | `confirm()` | `DRAFT`, 1 line | `CONFIRMED`, 1 line | Confirmation succeeds |
| 4 | `addLine("PEN-01", 1, 5000)` | `CONFIRMED`, 1 line | **Unchanged** | Throws `IllegalStateException`; total remains 250000 |

To test the “confirm an empty order” error, use **a second order**: `new Order(id2)` → `confirm()` fails → status remains `DRAFT`. Using separate test branches avoids confusing the first order's results with those of the second.

## 8. What Happens When Multiple Objects Collaborate?

Each object has its own responsibility, but systems often require multiple objects to collaborate.

For example, consider an order-confirmation flow in a Spring Boot application:

~~~mermaid
sequenceDiagram
    participant C as OrderController
    participant S as OrderService
    participant R as OrderRepository
    participant O as Order
    C->>S: confirmOrder(orderId)
    S->>R: findById(orderId)
    R-->>S: Order
    S->>O: confirm()
    O-->>S: Thành công hoặc exception
    S->>R: save(Order) khi thành công
    S-->>C: Kết quả
~~~

In this organization, **OrderController** receives the request, **OrderService** coordinates the use case, **OrderRepository** handles retrieval and persistence, and **Order** validates conditions and changes state. This division allows the rule “Can an empty order be confirmed?” to be changed in `Order.confirm()`, while also allowing storage details to change without placing SQL inside `Order`.

This is **an illustrative design**, not a requirement that every OOP application contain classes named `Service`/`Repository`. A simple application might need fewer classes. Systems involving payments, inventory, and transactions will have more complex coordination responsibilities.

Note: in-memory validation inside `Order` **does not resolve** concurrent requests, failed updates, or database rollbacks. Those situations require appropriate transactions, locking/versioning, and error handling in persistence and business-process layers.

## 9. Common Design Mistakes

| Common misconception | Consequence | Better way to think |
| --- | --- | --- |
| “An object is just a group of fields.” | Classes contain only getters/setters, while rules are scattered outside. | Ask what conditions the object must enforce and what behaviors it must provide. |
| “Every method is a separate responsibility.” | Classes are split arbitrarily and become hard to follow. | Multiple methods can serve one consistent responsibility. |
| “`private` means state is always safe.” | An unrestricted setter can still break rules; mutable collections may leak. | Validate rules wherever state changes and restrict modification rights. |
| “State means a status enum.” | Order lines, quantities, and other values inside the object are overlooked. | State includes all relevant data at a point in time; status is just one part. |
| “Making everything a class produces good OOP.” | Unnecessary classes proliferate; responsibilities remain unclear. | Create an object when it has a role, data, or behavior that needs managing. |
| “An object can do everything on its own.” | One class handles APIs, databases, payments, email, and business logic. | Establish responsibility boundaries and collaborate through suitable methods. |

A sign that warrants review is code like `if (order.getStatus() == DRAFT) { ... }` appearing in many places before an order is changed. The rule may belong to `Order` and should perhaps become one of its behaviors. However, rules involving **multiple objects or multiple data sources** may still require a service or coordinating component.

## 10. Test Your Understanding

**Scenario 1.** Two orders both have `status = DRAFT` and `total = 0`. Are they the same object? **Not necessarily.** Identity matters; matching data does not imply the same instance or the same business order.

**Scenario 2.** An order is confirmed and its `status` changes to `CONFIRMED`. Is this a new object? **No.** Its identity remains the same; its state changes.

**Scenario 3.** Should a controller call `order.setStatus(CONFIRMED)`? **Not in this example.** The `confirm()` method lets Order validate the conditions itself before changing state.

**Scenario 4.** `total()` does not modify data. Is it still a behavior? **Yes.** Behavior can calculate or return information without changing state.

**Scenario 5.** Should email-sending code live inside `Order.confirm()`? **Usually not.** Sending emails is an integration/notification responsibility that another component can handle after the order is successfully confirmed.

When designing your own OOP class, ask these questions in order:

1. **Which objects** exist in the problem? What identifies a particular object?
2. **Which state** must each object own? What can change, and what is merely derived?
3. **Which behaviors** are meaningful to users or the business? What are their preconditions and postconditions?
4. **Which rules** must the object always enforce? What happens when an operation fails?
5. **Which responsibilities** belong to that object, and which should belong to others?

If you can answer these five questions with a concrete example, you understand the shift from passive data to **objects with clearly defined behaviors and responsibilities**, rather than merely memorizing the definition of OOP.
