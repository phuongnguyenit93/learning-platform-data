# Exercise: Encapsulating order business rules with Java OOP

> **Context:** Practice designing an `Order` object that is responsible for protecting its own state and business rules. The goal goes beyond hiding fields with `private`: every data modification path that could produce an invalid order must be prevented.

## 1. Scenario

You are building a shopping-cart/checkout component for an online store. The initial design might look like this:

~~~java
import java.util.ArrayList;
import java.util.List;

class OrderBad {
    public final List<OrderLineBad> lines = new ArrayList<>();
    public String status = "DRAFT";
}

class OrderLineBad {
    public String sku;
    public long priceCents;
    public int quantity;
}
~~~

Other code can perform all of the following:

~~~java
OrderBad order = new OrderBad();
order.status = "PLACED";
order.lines.add(new OrderLineBad()); // sku null, quantity 0
order.lines.get(0).quantity = -5;
order.lines.clear();                 // xóa sau khi đã đặt hàng
~~~

These defects occur because **users of the object have unrestricted control over its state**, so no one enforces business invariants. Changing `public List` to `private List` while returning the original list directly from a getter does not solve the problem either.

**Task:** Redesign `Order` as a simple *aggregate*: `Order` owns its order lines, controls updates, calculates totals, and manages its lifecycle. Clients can only invoke permitted operations.

## 2. Required specification before coding

### Data and rules

Each order has an `orderId`, a status, and a set of order lines. Each line contains a product identifier `sku`, a unit price `unitPriceCents`, and a `quantity`.

| Rule | Specific contract |
|---|---|
| Order ID | Must not be `null`, empty, or whitespace-only; normalize with `trim()` |
| SKU | Must not be `null`/empty; after `trim()` and uppercasing, accept only `A-Z`, `0-9`, and `-` |
| Duplicate SKU | Each normalized SKU occurs in at most one line; `setLine` replaces an existing line |
| Unit price | Measured in **cents**, within `1..1_000_000` |
| Quantity | Each line has `quantity` within `1..100` |
| Subtotal | `subtotal = Σ(unitPriceCents × quantity)`, not exceeding `10_000_000` cents |
| Quantity update | `changeQuantity(sku, 0)` removes a line; negative values or values over 100 are invalid |
| Remove SKU | `removeLine(sku)` returns `true` if a line was removed; `false` if absent |
| Shipping fee | Empty order: 0; `subtotal >= 100_000`: 0; otherwise: `15_000` cents |
| Discount | If `subtotal >= 200_000`, give `5%` using integer division `subtotal / 20`; otherwise 0 |
| Amount payable | `payable = subtotal - discount + shipping` |
| Exceptions | Invalid input: `IllegalArgumentException`; unknown SKU during quantity update: `NoSuchElementException`; operation prohibited by status: `IllegalStateException` |
| Failure effects | A rejected operation leaves the order in its previous state |

The pricing policies above are assumptions for this exercise. In a real system, monetary, tax, discount, and rounding policies must be explicitly agreed with business stakeholders.

### Order lifecycle

- **DRAFT:** adding/replacing lines, changing quantities, and removing lines are allowed.
- **PLACED:** the order has been placed; changing lines or placing it again is forbidden.
- **CANCELLED:** a terminal state; adding, changing, removing, or placing items is forbidden.
- `place()` transitions only from `DRAFT` to `PLACED`, and only when the order has at least one line.
- `cancel()` allows transitions from `DRAFT` or `PLACED` to `CANCELLED`; a second call is rejected.
- Cancellation here changes only the state of the in-memory example; it **does not automatically issue refunds or notifications**.

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT : tạo Order
    DRAFT --> DRAFT : setLine / changeQuantity / removeLine
    DRAFT --> PLACED : place() khi có dòng
    DRAFT --> CANCELLED : cancel()
    PLACED --> CANCELLED : cancel()
    CANCELLED --> [*]
~~~

### Expected API

~~~java
Order order = new Order("ORD-001");

order.setLine(" book ", 90_000, 1);
order.setLine("PEN", 10_000, 2);
order.changeQuantity("BOOK", 2);

List<OrderLine> snapshot = order.lines();  // chỉ đọc, không sửa đơn được
OrderSummary result = order.summary();     // do Order tự tính
order.place();                             // khóa các thao tác chỉnh dòng
~~~

This API exposes **meaningful actions**, rather than `setStatus("PLACED")`, `setSubtotal(...)`, or `getMutableLines()`. This keeps each rule in the object responsible for enforcing it.

## 3. Hints before viewing the solution

Try implementing the following steps yourself:

1. Define `enum OrderStatus { DRAFT, PLACED, CANCELLED }` to eliminate arbitrary status strings.
2. Use `record OrderLine(...)` so each order line has no setter and validates its data at construction.
3. Keep `Order` fields `private`; use `Map<String, OrderLine>` to maintain one line per SKU.
4. Put business logic in `setLine`, `changeQuantity`, `removeLine`, `place`, `cancel`, and `summary` methods.
5. Calculate the **proposed** result of a change before applying it. If it would exceed the subtotal limit, report an error without leaving partially updated data.
6. Return `List.copyOf(lines.values())` as a snapshot; because `OrderLine` has immutable components, callers cannot alter its structure or elements to change the cart.
7. Add tests for boundary values and operations forbidden after `place()`.

A reasonable allocation of responsibilities:

| Component | Responsibility | Should not do |
|---|---|---|
| `Order` | Control order status, lines, invariants, and money rules | Return the internal Map or let callers assign totals |
| `OrderLine` | Represent a valid immutable order line | Expose a setter for quantity or unit price |
| `OrderStatus` | Define the allowed statuses | Represent status with arbitrary strings |
| `OrderSummary` | Provide an immutable calculation result | Store a freely mutable total |
| Client/UI/API | Invoke behaviors and display snapshots | Recompute business rules and directly modify fields |

## 4. Standalone Java 17 reference solution

Create **`OrderExercise.java`**. The code below uses only the Java Standard Library and includes a `main` method to check its business behavior.

~~~java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.NoSuchElementException;

public class OrderExercise {
    static final long MAX_UNIT_PRICE = 1_000_000L;
    static final long MAX_SUBTOTAL = 10_000_000L;
    static final int MAX_QUANTITY = 100;

    enum OrderStatus {
        DRAFT, PLACED, CANCELLED
    }

    static String normalizeSku(String sku) {
        if (sku == null) {
            throw new IllegalArgumentException("sku must not be null");
        }
        String normalized = sku.trim().toUpperCase(Locale.ROOT);
        if (!normalized.matches("[A-Z0-9-]+")) {
            throw new IllegalArgumentException("Invalid SKU: " + sku);
        }
        return normalized;
    }

    // Immutable value object. Bất biến được kiểm tra ngay khi khởi tạo.
    record OrderLine(String sku, long unitPriceCents, int quantity) {
        OrderLine {
            sku = normalizeSku(sku);
            if (unitPriceCents < 1 || unitPriceCents > MAX_UNIT_PRICE) {
                throw new IllegalArgumentException("Invalid unit price");
            }
            if (quantity < 1 || quantity > MAX_QUANTITY) {
                throw new IllegalArgumentException("Invalid quantity");
            }
        }

        long lineTotalCents() {
            return Math.multiplyExact(unitPriceCents, quantity);
        }
    }

    // Snapshot số tiền; caller chỉ đọc các component.
    record OrderSummary(
            long subtotalCents,
            long discountCents,
            long shippingCents,
            long payableCents) {
    }

    static final class Order {
        private final String orderId;
        private final Map<String, OrderLine> lines = new LinkedHashMap<>();
        private OrderStatus status = OrderStatus.DRAFT;

        Order(String orderId) {
            if (orderId == null || orderId.isBlank()) {
                throw new IllegalArgumentException("orderId is required");
            }
            this.orderId = orderId.trim();
        }

        String orderId() {
            return orderId;
        }

        OrderStatus status() {
            return status;
        }

        int lineCount() {
            return lines.size();
        }

        // Không trả Map hoặc collection mutable đang được giữ bên trong.
        List<OrderLine> lines() {
            return List.copyOf(lines.values());
        }

        private void ensureDraft() {
            if (status != OrderStatus.DRAFT) {
                throw new IllegalStateException(
                    "Order cannot be modified in state " + status
                );
            }
        }

        // Tính trước và từ chối ứng viên sai trước khi sửa state thật.
        private static long subtotalOf(Map<String, OrderLine> candidate) {
            long sum = 0;
            try {
                for (OrderLine line : candidate.values()) {
                    sum = Math.addExact(sum, line.lineTotalCents());
                }
            } catch (ArithmeticException overflow) {
                throw new IllegalArgumentException(
                    "Subtotal arithmetic overflow", overflow
                );
            }
            if (sum > MAX_SUBTOTAL) {
                throw new IllegalArgumentException(
                    "Subtotal exceeds " + MAX_SUBTOTAL
                );
            }
            return sum;
        }

        // Thêm SKU mới hoặc thay thế dòng của SKU đã có.
        void setLine(String sku, long unitPriceCents, int quantity) {
            ensureDraft();
            OrderLine newLine = new OrderLine(sku, unitPriceCents, quantity);

            Map<String, OrderLine> candidate = new LinkedHashMap<>(lines);
            candidate.put(newLine.sku(), newLine);
            subtotalOf(candidate);             // có thể ném lỗi

            lines.put(newLine.sku(), newLine); // commit sau validation
        }

        void changeQuantity(String sku, int newQuantity) {
            ensureDraft();
            String key = normalizeSku(sku);
            if (newQuantity < 0 || newQuantity > MAX_QUANTITY) {
                throw new IllegalArgumentException("Invalid quantity");
            }

            OrderLine current = lines.get(key);
            if (current == null) {
                throw new NoSuchElementException("Unknown SKU: " + key);
            }

            if (newQuantity == 0) {
                lines.remove(key);
                return;
            }

            // Giữ đơn giá cũ và kiểm tra tổng trước khi cập nhật.
            setLine(key, current.unitPriceCents(), newQuantity);
        }

        boolean removeLine(String sku) {
            ensureDraft();
            return lines.remove(normalizeSku(sku)) != null;
        }

        OrderSummary summary() {
            long subtotal = subtotalOf(lines);
            long discount = subtotal >= 200_000 ? subtotal / 20 : 0;
            long shipping = (lines.isEmpty() || subtotal >= 100_000)
                    ? 0 : 15_000;
            long payable = Math.addExact(
                Math.subtractExact(subtotal, discount), shipping);
            return new OrderSummary(
                subtotal, discount, shipping, payable
            );
        }

        void place() {
            ensureDraft();
            if (lines.isEmpty()) {
                throw new IllegalStateException("Cannot place empty order");
            }
            status = OrderStatus.PLACED;
        }

        void cancel() {
            if (status == OrderStatus.CANCELLED) {
                throw new IllegalStateException("Order already cancelled");
            }
            status = OrderStatus.CANCELLED;
        }
    }

    private static void require(boolean value, String message) {
        if (!value) {
            throw new AssertionError(message);
        }
    }

    // Mini assertion utility, không cần dependency ngoài JDK.
    private static void expectThrows(
            Class<? extends RuntimeException> type, Runnable action) {
        try {
            action.run();
        } catch (RuntimeException ex) {
            if (type.isInstance(ex)) {
                return;
            }
            throw new AssertionError(
                "Expected " + type.getSimpleName()
                    + " but caught " + ex.getClass().getSimpleName(),
                ex
            );
        }
        throw new AssertionError(
            "Expected exception " + type.getSimpleName()
        );
    }

    private static OrderLine findLine(List<OrderLine> snapshot, String sku) {
        return snapshot.stream()
            .filter(line -> line.sku().equals(sku))
            .findFirst()
            .orElseThrow();
    }

    public static void main(String[] args) {
        // 1) Chuẩn hóa SKU và tính tiền.
        Order order = new Order(" ORD-001 ");
        require(order.status() == OrderStatus.DRAFT, "initial status");
        require(order.summary().equals(
                new OrderSummary(0, 0, 0, 0)), "empty summary");

        order.setLine(" book ", 90_000, 1);
        order.setLine("PEN", 10_000, 2);
        require(order.lineCount() == 2, "two unique SKUs");
        require(order.summary().equals(
                new OrderSummary(110_000, 0, 0, 110_000)),
                "no discount, free shipping above 100000");

        // 2) Snapshot không thể sửa và không đổi theo update sau đó.
        List<OrderLine> before = order.lines();
        expectThrows(UnsupportedOperationException.class, before::clear);
        require(findLine(before, "BOOK").quantity() == 1,
                "old quantity");

        order.changeQuantity("BOOK", 2);
        require(order.summary().equals(
                new OrderSummary(200_000, 10_000, 0, 190_000)),
                "5% discount from 200000");

        require(findLine(before, "BOOK").quantity() == 1,
                "old snapshot remains unchanged");
        require(findLine(order.lines(), "BOOK").quantity() == 2,
                "new snapshot sees new state");

        // 3) Validation thất bại không làm hỏng đơn.
        OrderSummary goodState = order.summary();
        expectThrows(IllegalArgumentException.class,
            () -> order.setLine("BAD", -1, 1));
        expectThrows(IllegalArgumentException.class,
            () -> order.setLine("?", 100, 1));
        expectThrows(IllegalArgumentException.class,
            () -> order.changeQuantity("BOOK", -3));
        expectThrows(NoSuchElementException.class,
            () -> order.changeQuantity("UNKNOWN", 1));
        expectThrows(IllegalArgumentException.class,
            () -> order.setLine("EXPENSIVE", 1_000_000, 11));

        require(order.summary().equals(goodState),
                "failed mutations must not change totals");
        require(order.lineCount() == 2,
                "failed mutations must not add/remove lines");

        // 4) Kiểm thử cả hai phía của ngưỡng phí ship và giảm giá.
        Order boundaries = new Order("ORD-002");
        boundaries.setLine("A", 99_999, 1);
        require(boundaries.summary().equals(
                new OrderSummary(99_999, 0, 15_000, 114_999)),
                "shipping below threshold");

        boundaries.setLine("A", 100_000, 1);
        require(boundaries.summary().equals(
                new OrderSummary(100_000, 0, 0, 100_000)),
                "shipping free at threshold");

        boundaries.setLine("A", 199_999, 1);
        require(boundaries.summary().discountCents() == 0,
                "no discount below 200000");

        boundaries.setLine("A", 200_000, 1);
        require(boundaries.summary().equals(
                new OrderSummary(200_000, 10_000, 0, 190_000)),
                "discount at threshold");

        // 5) Trạng thái quản lý hành động được phép.
        expectThrows(IllegalStateException.class,
            () -> new Order("EMPTY").place());

        order.place();
        require(order.status() == OrderStatus.PLACED, "placed status");
        expectThrows(IllegalStateException.class,
            () -> order.setLine("NEW", 50, 1));
        expectThrows(IllegalStateException.class,
            () -> order.removeLine("BOOK"));
        expectThrows(IllegalStateException.class, order::place);

        order.cancel();
        require(order.status() == OrderStatus.CANCELLED, "cancelled status");
        expectThrows(IllegalStateException.class, order::cancel);
        expectThrows(IllegalStateException.class,
            () -> order.changeQuantity("BOOK", 1));

        System.out.println("PASS: SKU and business-rule validation");
        System.out.println("PASS: defensive snapshot and protected state");
        System.out.println("PASS: pricing thresholds and unchanged state on error");
        System.out.println("PASS: order lifecycle");
    }
}
~~~

Run:

~~~bash
javac OrderExercise.java
java OrderExercise
~~~

Expected output:

~~~text
PASS: SKU and business-rule validation
PASS: defensive snapshot and protected state
PASS: pricing thresholds and unchanged state on error
PASS: order lifecycle
~~~

**Design explanation:** `Order` has neither `setStatus` nor `setTotal`. Calling code invokes `place()` or `cancel()` according to state-transition rules; `summary()` always calculates from the current lines. The `setLine()` method builds a candidate map and validates limits **before** updating the actual map. Consequently, an operation exceeding the subtotal limit leaves no invalid line behind.

The example uses `LinkedHashMap` to make data easier to inspect, but clients do not depend directly on this map type. `OrderLine` is a record containing only `String` and primitive values, so snapshots expose no mutable elements; if a record contained `Date`, `List`, or an array, using `record` alone would not guarantee deep immutability.

## 5. OOP principles practiced

### Encapsulation: owning the state

~~~mermaid
classDiagram
    class Order {
        -String orderId
        -Map~String,OrderLine~ lines
        -OrderStatus status
        +setLine(String,long,int)
        +changeQuantity(String,int)
        +removeLine(String) boolean
        +lines() List~OrderLine~
        +summary() OrderSummary
        +place()
        +cancel()
    }
    class OrderLine {
        <<record>>
        +sku() String
        +unitPriceCents() long
        +quantity() int
    }
    class OrderSummary {
        <<record>>
        +subtotalCents() long
        +discountCents() long
        +shippingCents() long
        +payableCents() long
    }
    class OrderStatus {
        <<enumeration>>
        DRAFT
        PLACED
        CANCELLED
    }
    Order "1" o-- "*" OrderLine : sở hữu
    Order --> OrderStatus : trạng thái
    Order --> OrderSummary : tạo bản đọc
~~~

In this exercise, **`Order` is the only component allowed to update its collection and status**. Clients invoke the `Order` API instead of modifying a `Map` or enum field directly.

### Invariants: validate every mutation path

Validating unit prices and quantities in the constructor is insufficient if another setter can still alter them. Rules must hold for **every public mutation**, including:

- Adding or replacing a line.
- Changing quantity, especially to `0` or a negative value.
- Removing lines and confirming/placing an order.
- Operations rejected because of status or subtotal limits.

### Information hiding: concealing storage choices

Using `Map<String,OrderLine>` is an internal decision; it can later be replaced with another structure while preserving the public business operations. `Order.lines()` returns a snapshot for UI display without letting the UI manage how lines are stored.

### Cohesion: what logic belongs to Order?

This example puts **totals, status, and order-line rules** inside `Order` because they directly concern an order. But `Order` need not open database connections, send emails, or call external payment gateways. These side effects should be coordinated by the application layer using appropriate services/ports.

## 6. Why avoid unrestricted setters or direct collection getters?

A common design looks like this:

~~~java
class Order {
    private List<OrderLine> lines;
    private long totalCents;
    private String status;

    public void setLines(List<OrderLine> lines) {
        this.lines = lines;
    }
    public void setTotalCents(long totalCents) {
        this.totalCents = totalCents;
    }
    public void setStatus(String status) {
        this.status = status;
    }
}
~~~

It could produce contract violations such as `status="PLACED"` with no items, a total that does not match the lines, or changed lines without updating `totalCents`. To prevent this:

- Allow **placing orders** through `place()`, rather than assigning arbitrary statuses.
- Allow **quantity changes** through `changeQuantity()` to handle `0` explicitly.
- Allow **reading totals** through `summary()`, rather than a total field assignable by clients.
- Allow **viewing order lines** through snapshots of immutable value objects, rather than returning internal mutable references.

This does not mean all objects must avoid setters. DTOs and data transferred through APIs can use JavaBeans/setters. This exercise focuses on **domain objects with rules that must be enforced**.

## 7. Acceptance test matrix

| ID | Action | Expected result |
|---|---|---|
| TC01 | Create a new order | DRAFT status, 0 lines, total 0 |
| TC02 | Add `" book "` then `"BOOK"` | A single normalized SKU remains; the second call replaces the first line |
| TC03 | Price 0, negative, or above 1.000.000 | Throw `IllegalArgumentException` |
| TC04 | Quantity 0 in `setLine`, or quantity 101 | Throw `IllegalArgumentException` |
| TC05 | `changeQuantity("BOOK", 0)` | Remove BOOK if present; leave no line with quantity 0 |
| TC06 | Change quantity for an unknown SKU | Throw `NoSuchElementException` |
| TC07 | Updated subtotal exceeds 10.000.000 | Reject; preserve previous total and lines |
| TC08 | Get `lines()` and then call `clear()` | Reject with `UnsupportedOperationException` |
| TC09 | Obtain snapshot A, then update order | A retains old data, while snapshot B contains new data |
| TC10 | Subtotal 99.999 cents | Shipping fee 15.000 |
| TC11 | Subtotal exactly 100.000 cents | Free shipping |
| TC12 | Subtotal exactly 200.000 cents | Discount 10.000 cents |
| TC13 | Call `place()` on an empty order | Throw `IllegalStateException`; remain DRAFT |
| TC14 | Call `place()` with nonempty order | Transition to PLACED; prohibit line changes |
| TC15 | Call `cancel()`, then try to change/place/cancel again | Throw `IllegalStateException` |
| TC16 | Any invalid input | No partial state changes |

You can write these tests before viewing the solution and use them for self-assessment. Even if the collection's storage representation changes, its behavioral tests must continue to pass.

### Selected JUnit 5 tests

For a project already using `JUnit Jupiter`, place `OrderExerciseTest.java` **in the same package** as `OrderExercise`:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class OrderExerciseTest {
    @Test
    void duplicateSkuIsReplacedAfterNormalization() {
        var order = new OrderExercise.Order("ORD-1");
        order.setLine("book", 100, 2);
        order.setLine(" BOOK ", 150, 3);

        assertEquals(1, order.lineCount());
        assertEquals("BOOK", order.lines().get(0).sku());
        assertEquals(450, order.summary().subtotalCents());
    }

    @Test
    void invalidUpdateLeavesOrderUnchanged() {
        var order = new OrderExercise.Order("ORD-2");
        order.setLine("BOOK", 100, 2);
        var before = order.summary();

        assertThrows(IllegalArgumentException.class,
            () -> order.setLine("EXPENSIVE", 1_000_000, 11));

        assertEquals(before, order.summary());
        assertEquals(1, order.lineCount());
    }

    @Test
    void returnedLinesCannotBypassRules() {
        var order = new OrderExercise.Order("ORD-3");
        order.setLine("BOOK", 100, 2);
        var snapshot = order.lines();

        assertThrows(UnsupportedOperationException.class, snapshot::clear);

        order.changeQuantity("BOOK", 3);
        assertEquals(2, snapshot.get(0).quantity());
        assertEquals(3, order.lines().get(0).quantity());
    }

    @Test
    void placingFreezesMutations() {
        var order = new OrderExercise.Order("ORD-4");
        order.setLine("PEN", 99_999, 1);

        assertEquals(15_000, order.summary().shippingCents());
        order.place();

        assertThrows(IllegalStateException.class,
            () -> order.setLine("NEW", 10, 1));
        assertThrows(IllegalStateException.class,
            () -> order.removeLine("PEN"));
        assertEquals(OrderExercise.OrderStatus.PLACED, order.status());
    }
}
~~~

In a real application, organize types as classes/records in appropriate files, choosing `public` or package-private according to API boundaries; the code above uses nested types so the example can run from one file.

## 8. Discussion: design decisions and solution limitations

**Why a Map?** Each SKU is a unique key, and a map directly represents the no-duplicate-SKU invariant. But the map must not be returned directly; clients need not know the storage structure. `LinkedHashMap` preserves insertion order for inspection, but if UI ordering is part of the **contract**, it must be documented and independently tested.

**Why cents and long?** They avoid the binary precision pitfalls of representing money with `double`. Currencies with more complex precision/rounding rules may require `BigDecimal` with specified scale, currency, and rounding mode. `long` in the smallest unit is suitable only if the system consistently defines units and limits.

**Why records?** `OrderLine` and `OrderSummary` are immutable values without separate identities in this example. A record **does not automatically guarantee deep immutability** if its components contain mutable objects; here they use `String` and primitives, which are safe across the chosen boundary.

**Why validate the subtotal before committing?** Adding a line before calculating the subtotal could leave invalid data in the actual map when the limit is exceeded. Constructing and validating a candidate first ensures failed operations do not cause partial changes.

**Why no public `isPlaced` flag?** A client could mark an empty order as placed without enforcing the nonempty-order condition. A status enum and transition methods express the rule in one place.

**Why no database connection inside Order?** Domain rules and infrastructure side effects belong to different responsibilities. An application service can load `Order` from a repository, call `order.place()`, and save it within a transaction, while `Order` is responsible only for validating its operation.

### Limitations to address in production

- **Concurrency:** `LinkedHashMap` and `Order` are not currently thread-safe. If multiple requests can update one order, use transactions, optimistic locking/versioning, and a conflict-handling strategy. Safe read snapshots do not automatically make concurrent updates safe.
- **Shipping and discounts:** Values may depend on coupons, addresses, carrier charges, and promotion dates; do not embed every infrastructure dependency in an entity. As requirements evolve, supply an external pricing policy to domain operations when appropriate.
- **Inventory and payments:** `place()` only changes status in this exercise. Stock deduction, payment gateway calls, emails, and event publication need controlled orchestration; do not assume those tasks finish when `place()` returns.
- **Historical accuracy:** A production system may need snapshots of product names/unit prices at placement time, a transition history, and versioned pricing policies.
- **Cancellation after payment:** This exercise allows `PLACED → CANCELLED` but does not address delivery deadlines or refunds. Real business rules involving `PAID` or `SHIPPED` require a precise state machine and cancellation policy.
- **API compatibility:** Replacing an anemic entity with public getters/setters by an aggregate can break client compilation; update clients, DTO mappings, and applicable ORM/JPA constraints.

## 9. Progressive extension exercises

**Level 1 — Strong encapsulation:** Add tests for blank SKUs, invalid characters, quantity 101, replacing duplicate SKUs, and removing nonexistent items with `removeLine`. Show that each failure preserves `OrderSummary`, `lineCount`, and `status`.

**Level 2 — Protecting monetary rules:** Try a subtotal near `10_000_000`; replace a line so the limit is exceeded, then confirm rejection preserves the original line. Adjust the limit assumption and retest the free-shipping and discount thresholds.

**Level 3 — Alternative policies:** Add free shipping for VIP customers. Consider whether to store `CustomerType` in `Order` or pass in a clearly contracted pricing policy. Justify the design using actual requirements and avoid adding interfaces solely to increase the class count.

**Level 4 — Protecting state:** Add `PAID` or `SHIPPED` and their corresponding transition rules. Write the state-transition table first, then implement and test every prohibited transition.

**Level 5 — Production application:** Implement `PlaceOrderUseCase` to load an order from a repository, call `order.place()`, and save it. Use a fake repository in unit tests; write an integration test for transactions/optimistic locking when two requests concurrently modify an order.

### Self-assessment rubric (10 points)

| Criterion | Points |
|---|---:|
| Status and lines are hidden; clients cannot change them directly | 2 |
| Input validation, unique SKUs, quantity and unit-price limits | 2 |
| Correct subtotal/discount/shipping/payable rules at boundaries | 2 |
| Correct DRAFT/PLACED/CANCELLED transitions | 2 |
| Tests against representation exposure and failed operations corrupting state | 2 |

**The exercise is complete** when every specified acceptance test passes and clients using only the public API cannot invent negative lines, exceed limits, modify placed orders, or bypass rules by altering internal collections. This demonstrates what **encapsulating order business rules** means in OOP.
