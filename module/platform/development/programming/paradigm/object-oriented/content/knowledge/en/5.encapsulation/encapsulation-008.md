# Encapsulating behavior rather than merely wrapping data in Java OOP

**Encapsulation** involves more than making fields `private` and generating getters/setters. Its greater value is making **an object responsible for performing valid operations on its own state**. External code expresses an *intention*, such as “confirm an order” or “add a product”; the object decides whether the operation is allowed and updates related properties consistently.

For example, instead of requiring callers to check conditions and then invoke `order.setStatus(CONFIRMED)`, give `Order` a `confirm()` method. When confirmation rules change, update them where the order's behavior is owned.

## 1. Why is merely wrapping data insufficient?

Consider a simple order class:

~~~java
import java.math.BigDecimal;

public class OrderData {
    private String status;
    private BigDecimal total;

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public BigDecimal getTotal() {
        return total;
    }

    public void setTotal(BigDecimal total) {
        this.total = total;
    }
}
~~~

Although all fields are `private`, this class still allows:

~~~java
OrderData order = new OrderData();

order.setStatus("CONFIRMED");
order.setTotal(new BigDecimal("-90000"));
~~~

Nothing prevents an order with no products or a negative total from being confirmed. All knowledge of valid states may be pushed outside:

~~~java
// Mỗi đoạn code gọi tới OrderData có nguy cơ phải kiểm tra lại:
if (order.getTotal() != null &&
        order.getTotal().signum() > 0 &&
        !"CANCELLED".equals(order.getStatus())) {
    order.setStatus("CONFIRMED");
}
~~~

If the system adds rules such as “products cannot be added after confirmation” or “canceled orders cannot be confirmed again,” many callers must remember and enforce them independently. This design is often called an **anemic domain model** (a domain model that mainly carries data and has little business behavior).

The problem is not with getters/setters themselves. They suit many data-transfer types or simple configuration objects. The problem occurs when **state carries business rules** but every caller can control it through unconstrained setters.

| Question | Class that merely wraps data | Object that encapsulates behavior |
| --- | --- | --- |
| Who decides which states are valid? | Usually external calling code | The object that owns the state |
| How does external code request a change? | `setStatus(...)`, `setTotal(...)` | `confirm()`, `addLine(...)`, `cancel()` |
| Where do the rules live? | Easily duplicated across controllers/services/UIs | Centered around protected behavior |
| What happens when rules are added? | Many field assignments must be found | Related behavior methods are updated |
| Risk of invalid states? | High if checks are forgotten | Lower when all mutation paths are controlled |

A method name describing **a business action** usually communicates intent more effectively than a setter name describing data storage.

## 2. Complete Java example: let Order manage its own lifecycle

Suppose the following rules apply:

- A new order starts in the `DRAFT` state.
- While in `DRAFT`, products may be added with nonblank SKUs, positive unit prices, and positive quantities.
- Only a `DRAFT` order with at least one line item can be confirmed.
- No line items may be added after confirmation.
- Only a `CONFIRMED` order can be canceled; once canceled, it cannot be confirmed again.
- The total is **calculated from line items**, never assigned directly by external code.

This is a self-contained illustrative model without payment, shipping, or database integration. Run it on **Java 11+**, saving everything in `EncapsulatedOrderDemo.java`.

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class EncapsulatedOrderDemo {

    enum Status {
        DRAFT, CONFIRMED, CANCELLED
    }

    // Dòng hàng là một value object: không có setter.
    static final class OrderLine {
        private final String sku;
        private final BigDecimal unitPrice;
        private final int quantity;

        OrderLine(String sku, BigDecimal unitPrice, int quantity) {
            String checkedSku =
                    Objects.requireNonNull(sku, "sku").trim();
            Objects.requireNonNull(unitPrice, "unitPrice");

            if (checkedSku.isEmpty()) {
                throw new IllegalArgumentException("SKU không được rỗng");
            }
            if (unitPrice.signum() <= 0) {
                throw new IllegalArgumentException("Giá phải dương");
            }
            if (quantity <= 0) {
                throw new IllegalArgumentException("Số lượng phải dương");
            }

            this.sku = checkedSku;
            this.unitPrice = unitPrice;
            this.quantity = quantity;
        }

        String getSku() {
            return sku;
        }

        BigDecimal subtotal() {
            return unitPrice.multiply(BigDecimal.valueOf(quantity));
        }
    }

    static final class Order {
        private final String id;
        private final List<OrderLine> lines = new ArrayList<>();
        private Status status = Status.DRAFT;

        Order(String id) {
            String checkedId =
                    Objects.requireNonNull(id, "id").trim();
            if (checkedId.isEmpty()) {
                throw new IllegalArgumentException("Mã đơn không được rỗng");
            }
            this.id = checkedId;
        }

        public String getId() {
            return id;
        }

        public Status getStatus() {
            return status;
        }

        public List<OrderLine> getLines() {
            // Bản sao không thể sửa cấu trúc; OrderLine cũng bất biến.
            return List.copyOf(lines);
        }

        public BigDecimal getTotal() {
            BigDecimal total = BigDecimal.ZERO;
            for (OrderLine line : lines) {
                total = total.add(line.subtotal());
            }
            return total;
        }

        public void addLine(String sku, BigDecimal price, int quantity) {
            requireDraft();
            // Kiểm tra xong trước khi cập nhật danh sách.
            OrderLine candidate = new OrderLine(sku, price, quantity);
            lines.add(candidate);
        }

        public void confirm() {
            requireDraft();
            if (lines.isEmpty()) {
                throw new IllegalStateException(
                        "Không thể xác nhận đơn hàng rỗng"
                );
            }
            status = Status.CONFIRMED;
        }

        public void cancel() {
            if (status != Status.CONFIRMED) {
                throw new IllegalStateException(
                        "Chỉ đơn đã xác nhận mới được hủy"
                );
            }
            status = Status.CANCELLED;
        }

        private void requireDraft() {
            if (status != Status.DRAFT) {
                throw new IllegalStateException(
                        "Chỉ được sửa đơn ở trạng thái DRAFT"
                );
            }
        }
    }

    public static void main(String[] args) {
        Order order = new Order("ORD-101");

        try {
            order.confirm();
        } catch (IllegalStateException ex) {
            System.out.println("Từ chối: " + ex.getMessage());
        }

        order.addLine("BOOK-01", new BigDecimal("80000"), 2);
        order.addLine("PEN-01", new BigDecimal("50000"), 1);

        System.out.println("Tổng tiền: "
                + order.getTotal().toPlainString());

        order.confirm();
        System.out.println("Trạng thái: " + order.getStatus());

        try {
            order.addLine("BOOK-02", new BigDecimal("90000"), 1);
        } catch (IllegalStateException ex) {
            System.out.println("Từ chối: " + ex.getMessage());
        }

        order.cancel();
        System.out.println("Sau hủy: " + order.getStatus());
        System.out.println("Số dòng hàng: " + order.getLines().size());
    }
}
~~~

Compile and run:

~~~bash
javac EncapsulatedOrderDemo.java
java EncapsulatedOrderDemo
~~~

Output:

~~~text
Từ chối: Không thể xác nhận đơn hàng rỗng
Tổng tiền: 210000
Trạng thái: CONFIRMED
Từ chối: Chỉ được sửa đơn ở trạng thái DRAFT
Sau hủy: CANCELLED
Số dòng hàng: 2
~~~

The key point: `Order` enforces each rule where its state actually changes. Calling code **does not need to know** how to assign the `status` field or how a `total` would be updated alongside `lines`.

### Why is this design safer?

**No `setStatus()` method.** Callers express only the intent to `confirm()` or `cancel()`; state transitions are validated.

**No `setTotal()` method.** `getTotal()` computes its result from source data, preventing a separately assigned total from becoming inconsistent with the product list.

**No exposure of an internal mutable list.** `getLines()` returns a structural snapshot via `List.copyOf(lines)`. If it returned `lines` directly, external code could call `clear()` to remove products from a confirmed order, bypassing `requireDraft()`. In this example, `OrderLine` is also immutable, so callers cannot circumvent the rules by modifying elements.

**Validate before writing.** `addLine()` creates and validates an `OrderLine` before appending it to the list; `confirm()` and `cancel()` assign `status` only after their conditions are satisfied. Rejected operations leave no partial updates.

## 3. Tracking state through diagrams and tables

Valid state transitions of `Order`:

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT : new Order(...)
    DRAFT --> DRAFT : addLine(...)
    DRAFT --> CONFIRMED : confirm() khi có dòng hàng
    CONFIRMED --> CANCELLED : cancel()
~~~

Transitions **without arrows** (such as `CANCELLED → CONFIRMED` or `CONFIRMED → DRAFT`) are not permitted by the example API.

| Current state | Call | Result |
| --- | --- | --- |
| `DRAFT`, no line items | `confirm()` | Throws `IllegalStateException`; remains `DRAFT` |
| `DRAFT`, valid product provided | `addLine(...)` | Adds a line item; remains `DRAFT` |
| `DRAFT`, contains products | `confirm()` | Transitions to `CONFIRMED` |
| `CONFIRMED` | `addLine(...)` | Rejected; no product added |
| `CONFIRMED` | `cancel()` | Transitions to `CANCELLED` |
| `CANCELLED` | `confirm()` or `cancel()` | Rejected |

This model's **invariants** (conditions that must hold whenever the object can validly be observed) include: nonblank order codes; valid SKUs, positive prices, and quantities for every `OrderLine`; a list that cannot be directly modified by external code; a state that belongs to one of the three enum values; and at least one line item from prior confirmation whenever the state is `CONFIRMED` or `CANCELLED`.

A well-designed behavior method should preserve invariants before and after every successful operation. For rejected operations, it should fail **before changing state** whenever feasible.

## 4. “Tell, Don't Ask”: ask an object to act instead of extracting data to act on it

The **Tell, Don't Ask** principle encourages sending a business request to the object that owns the data rather than repeatedly inspecting its state and performing the operation externally.

**An approach that scatters rules:**

~~~java
// Chỉ minh họa phong cách code: một kiểu Order khác có các setter này.
if (order.getStatus() == Status.DRAFT
        && !order.getLines().isEmpty()) {
    order.setStatus(Status.CONFIRMED);
}
~~~

**An intention-revealing approach:**

~~~java
order.confirm();
~~~

The `confirm()` method defines the conditions and state transition. When new rules appear, such as checking the delivery address before confirmation, the confirmation behavior or an appropriate collaborator can be extended without searching for `setStatus` calls throughout the application.

This **does not mean getters are bad**. Getters are useful for display, logging, and reporting:

~~~java
System.out.println(order.getStatus());
System.out.println(order.getTotal());
~~~

The difference is **purpose**: *reading for presentation* is reasonable; *reading all state to make a business decision and then assigning several fields externally* often suggests misplaced responsibility.

## 5. What should a good behavioral interface hide?

An object's API should expose **operations meaningful to the business domain** while hiding implementation details that may change.

| Data/operation | Expose publicly? | Reason |
| --- | --- | --- |
| `getStatus()` | Possibly | The UI needs to know the current state |
| `getTotal()` | Possibly | Display totals and support reconciliation |
| `addLine(...)` | Yes | Expresses adding a product and allows validation |
| `confirm()`, `cancel()` | Yes | Express business state transitions |
| `setStatus(Status)` | No in this example | Would bypass the confirmation/cancellation workflow |
| `setTotal(BigDecimal)` | No | Could make the total inconsistent with line items |
| `getMutableLines()` returns the internal `ArrayList` | No | Callers could modify the list without following rules |
| Helper `requireDraft()` | `private` | Implements internal rules |

Also avoid the opposite mistake: creating a method such as `setDataWithValidation()` that merely renames a setter while external code still decides the entire workflow and state. Ask: **“What real operation does this method represent for the object?”**

For complex objects, not every statement needs its own public method. Expose only behavior useful to clients and keep internal details at an appropriate `private` level.

## 6. Dividing responsibilities between entities and services

Behavioral encapsulation **does not mean cramming all application logic into one entity**. Distinguish:

- **Entity / domain object**: enforces its own state and directly related rules, such as `Order.confirm()`, `Order.addLine()`, and `Order.cancel()`.
- **Application service**: coordinates a use case involving repositories, payment gateways, shipping services, or notifications.
- **Infrastructure adapter**: handles HTTP, database, message broker, and other connections.

For example, an order-confirmation flow **illustrating only the architecture**:

~~~java
// Pseudocode: minh họa trách nhiệm, không phải đoạn chạy độc lập.
public void confirmOrder(String orderId) {
    Order order = repository.findById(orderId);

    order.confirm();            // Quy tắc của chính Order
    repository.save(order);     // Lưu trữ qua repository
    eventPublisher.publishOrderConfirmed(order.getId());
}
~~~

`Order` does not need to know how to connect to databases or send emails. `OrderService` (or a use-case service) should not need to reimplement the “order has items and is in DRAFT” condition by reading multiple `Order` fields.

**Consistency note:** the pseudocode only illustrates separation of responsibilities. In a real system, persisting orders and publishing events may fail at different times; transactions, transactional outboxes, retries, or other mechanisms may be needed. Moving rules into an entity **does not automatically solve** distributed-system and transaction problems.

A clear guide for locating logic:

| Logic to enforce | Typical location |
| --- | --- |
| “Only draft orders can accept new items” | `Order` |
| “Cannot confirm an empty order” | `Order` |
| “Line total = price × quantity” | `OrderLine` |
| “Find an order in the database” | Repository |
| “Call the bank to collect payment” | Payment gateway / service |
| “Coordinate confirmation, persistence, and event publishing” | Application service |
| “Rules involving several entities but owned by none individually” | Domain service or an appropriate business workflow |

The boundary depends on the business domain; there is no mandatory formula for every application.

## 7. Why must returned data be protected too?

Declaring `private List<OrderLine> lines` is **not sufficient** if a getter returns the list directly:

~~~java
class UnsafeOrder {
    private final List<String> skus = new ArrayList<>();

    List<String> getSkus() {
        return skus; // Trả về danh sách mutable bên trong
    }
}
~~~

Calling code can modify object state without using the designed behavior:

~~~java
UnsafeOrder order = new UnsafeOrder();
order.getSkus().add("ITEM-001");
~~~

Common choices include:

| How data is exposed | Effect |
| --- | --- |
| `return lines;` | Exposes a mutable collection if `lines` is mutable |
| `return Collections.unmodifiableList(lines);` | An unmodifiable view through the getter that still reflects subsequent changes to the internal list |
| `return List.copyOf(lines);` | An unmodifiable structural snapshot, but **does not deep-copy** elements |
| Return an immutable DTO/value object | May also protect element state, depending on the design |

In `EncapsulatedOrderDemo`, `OrderLine` has `private final` fields containing `String`, `BigDecimal`, and `int` (none exposing mutable internal contents), and no setters. Thus, combining them with `List.copyOf(lines)` meets the list-protection requirements of this example. If elements contain mutable `List` or `Date` values, deeper defensive copying must be considered.

## 8. Test behavior, not just getters and setters

A good test expresses **business rules**, including what happens when an operation is rejected.

For example, using **JUnit 5**, place a test in the same package as `EncapsulatedOrderDemo`:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class OrderBehaviorTest {

    @Test
    void cannotConfirmEmptyOrder() {
        EncapsulatedOrderDemo.Order order =
                new EncapsulatedOrderDemo.Order("ORD-101");

        assertThrows(IllegalStateException.class, order::confirm);
        assertEquals(EncapsulatedOrderDemo.Status.DRAFT,
                order.getStatus());
    }

    @Test
    void confirmedOrderCannotBeEdited() {
        EncapsulatedOrderDemo.Order order =
                new EncapsulatedOrderDemo.Order("ORD-102");

        order.addLine("BOOK", new BigDecimal("100000"), 2);
        order.confirm();

        assertThrows(IllegalStateException.class,
                () -> order.addLine("PEN", BigDecimal.TEN, 1));

        assertEquals(new BigDecimal("200000"), order.getTotal());
        assertEquals(1, order.getLines().size());
    }

    @Test
    void callerCannotModifyInternalLines() {
        EncapsulatedOrderDemo.Order order =
                new EncapsulatedOrderDemo.Order("ORD-103");
        order.addLine("BOOK", BigDecimal.TEN, 1);

        assertThrows(UnsupportedOperationException.class,
                () -> order.getLines().clear());
        assertEquals(1, order.getLines().size());
    }

    @Test
    void cannotConfirmAgainAfterCancellation() {
        EncapsulatedOrderDemo.Order order =
                new EncapsulatedOrderDemo.Order("ORD-104");

        order.addLine("BOOK", BigDecimal.TEN, 1);
        order.confirm();
        order.cancel();

        assertThrows(IllegalStateException.class, order::confirm);
        assertEquals(EncapsulatedOrderDemo.Status.CANCELLED,
                order.getStatus());
    }
}
~~~

The sample test requires the appropriate JUnit Jupiter dependency and test runner; the `EncapsulatedOrderDemo.java` program in section 2 **runs independently** using the Java standard library.

These tests do not merely prove that setters work; they verify that **the object rejects invalid operations** and maintains correct state after rejection. That is the behavior worth preserving during refactoring.

## 9. When is a behavior-rich model useful?

Favor moving behavior into an object when:

- A data field has **state-transition rules** or constraints involving other fields.
- Multiple callers repeat the same `get... → if... → set...` sequence.
- Incorrect updates can create invalid business data.
- The object has natural actions such as `approve`, `reserve`, `withdraw`, `activate`, or `close`.
- You want to test business logic through a clear API without depending directly on field structure.

This approach is not necessary for every object:

- **DTO/request/response** types primarily transfer or display data and may need only constructors, getters, and boundary mapping/validation.
- **Immutable value objects** can focus on constructor validation and transformations returning new objects.
- **Integration tasks or workflows spanning multiple objects** generally need coordinating services.
- Simple configuration data without complex invariants need not be forced into a state machine.

A useful example of shifting from data-oriented to behavior-oriented design:

| Field-oriented thinking | Action-oriented thinking |
| --- | --- |
| “Allow modifying `status`” | “Under what conditions may confirmation/cancellation happen?” |
| “Need a setter to change `balance`” | “What rules govern deposits, withdrawals, and transfers?” |
| “Change `reserved` from 2 to 5” | “Is requesting 3 additional reserved units valid?” |
| “Change `isActive`” | “Who may activate or deactivate it, and when?” |
| “The total is a stored number” | “Which source data determines the total?” |

## 10. Common mistakes when moving to behavioral encapsulation

**1. Merely renaming a setter.** `updateStatus(CONFIRMED)` still lets callers choose state directly. Design a `confirm()` operation with explicit conditions.

**2. Validating in a controller while leaving the entity freely mutable.** Another API, batch job, or test can bypass the controller. Core entity rules belong in its state-changing API, unless there is a clear architectural reason otherwise.

**3. Exposing mutable collections.** A getter returning a reference to an internal collection creates a mutation path that bypasses behaviors.

**4. Partially updating state before throwing.** Validate all conditions and necessary data before assignment when possible; operations involving multiple objects require a suitable consistency strategy.

**5. Putting all logic into one enormous class.** Divide responsibilities according to the data the object actually owns; let services coordinate external interactions.

**6. Assuming encapsulation guarantees concurrency safety.** If multiple threads call `addLine()` or `confirm()` concurrently on the same `Order`, the sample using `ArrayList` and ordinary fields here **is not thread-safe**. Real systems need request/aggregate boundaries and synchronization, transactions, optimistic locking, or equivalent mechanisms.

## 11. Practice exercises

**Exercise 1.** A `BankAccount` class has `getBalance()` and `setBalance(BigDecimal)`. Propose an API that expresses business intent better.

**Hint:** `deposit(amount)`, `withdraw(amount)`, and perhaps `transferTo(target, amount)` if the design can protect both accounts. Enforce positive amounts, sufficient funds, limits, and consistency in appropriate methods; transfers between accounts may require transactions/locking.

**Exercise 2.** Where should the rule “delivered orders cannot be canceled” be checked?

**Hint:** Cancellation behavior in `Order` (or its related lifecycle/authorization model) must know the relevant shipping status. Avoid checking only in a UI while allowing `setStatus(CANCELLED)` elsewhere.

**Exercise 3.** Should every getter on `Order` be removed to follow Tell, Don't Ask?

**Answer:** No. Reading data for display, queries, and reports is legitimate. The warning applies when external code repeatedly reads state to **make decisions on the object's behalf** and then directly modifies multiple fields.

**Exercise 4.** If `Order.getLines()` returns `List.copyOf(lines)` but each `OrderLine` has a `setPrice()` method, is the object fully protected?

**Answer:** No. The collection's structure cannot be changed, but callers can still modify mutable elements through their references. Design immutable `OrderLine` objects, use suitable defensive copies, or expose only safe observable data.

**Exercise 5.** If confirming an order requires payment through an API and persistence to a database, should `Order.confirm()` make the HTTP call directly?

**Hint:** Usually not. Let `Order` decide whether the transition is valid; an application service coordinates the payment gateway, persistence, and event publishing. The design must consider what happens if part of an external workflow fails.

A key design question is: **“What is this object responsible for protecting, and what actions do its clients need to request?”** When an API describes behavior instead of merely exposing data, the class is generally easier to use correctly, harder to misuse, and easier to test against business rules.
