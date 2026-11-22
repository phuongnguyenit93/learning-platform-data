# Tracing Object Interactions in a Scenario (Java OOP)

When an object-oriented program handles a request, the work is often divided among multiple **objects**. Each object owns part of the state and has a particular responsibility. To understand the actual execution, we need to trace **which object receives a call, which other object it calls, what data is passed, what results are returned, and which state changes occur**.

This lesson uses a small ordering scenario to connect Java code with execution timelines and **UML sequence diagrams**. These skills are useful when reading other people's code, debugging, explaining processing flows in interviews, and designing multilayer systems.

## 1. What Does Tracing Objects Involve?

Suppose a customer orders **2 books**. The system must:

1. Obtain the total price from the cart.
2. Check and reserve available inventory.
3. Call the payment processor.
4. Create the order information if payment succeeds.
5. Send a notification.
6. Return the order to the code that requested checkout.

These tasks belong to different objects:

| Object | Responsibility | Important state |
| --- | --- | --- |
| `Cart` | Provides item details, quantity, unit price, and total | SKU, quantity, unit price |
| `Inventory` | Manages stock quantities for each SKU | SKU-to-quantity map |
| `PaymentGateway` | Simulates approving or declining a payment | Simulated approval configuration |
| `OrderService` | Coordinates the checkout sequence | References to collaborating objects |
| `Order` | Holds data about the created order | Order ID, item, quantity, amount, transaction ID |
| `Notifier` | Sends an order notification | Only prints logs in this example |

**A note about abstraction levels:** `Cart`, `Inventory`, and `OrderService` are *classes*; `new Cart(...)` and `new Inventory(...)` create *concrete objects*. Arrows in interaction diagrams represent **runtime calls between instances**, not inheritance relationships between classes.

A useful trace answers five questions:

- **Who initiates the call?** For example, `main` invokes `OrderService.checkout(cart)`.
- **Who receives it?** Variable `service` references an `OrderService` instance.
- **What message/call is made?** The method name and arguments, such as `inventory.reserve("BOOK", 2)`.
- **What result comes back?** A returned value or exception, such as `"TX-001"`.
- **What changes afterward?** Stock decreases from 5 to 3; a new `Order` is created.

## 2. Complete Example: Checkout with Multiple Collaborating Objects

Run with **Java 11 or later**. Save the entire code sample in a single file named `ObjectInteractionDemo.java`; it uses only the Java standard library.

~~~java
import java.math.BigDecimal;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class ObjectInteractionDemo {

    // Ghi lại thứ tự các sự kiện để quan sát luồng chạy.
    static class Trace {
        private static int step = 0;

        static void log(String message) {
            System.out.printf("%02d %s%n", ++step, message);
        }
    }

    // Giỏ hàng chứa một mặt hàng cho ví dụ dễ theo dõi.
    static class Cart {
        final String sku;
        final int quantity;
        final BigDecimal unitPrice;

        Cart(String sku, int quantity, BigDecimal unitPrice) {
            if (sku == null || sku.isBlank()) {
                throw new IllegalArgumentException("SKU không hợp lệ");
            }
            if (quantity <= 0) {
                throw new IllegalArgumentException("Số lượng phải dương");
            }
            Objects.requireNonNull(unitPrice, "unitPrice");
            if (unitPrice.signum() <= 0) {
                throw new IllegalArgumentException("Đơn giá phải dương");
            }
            this.sku = sku;
            this.quantity = quantity;
            this.unitPrice = unitPrice;
        }

        BigDecimal total() {
            BigDecimal amount = unitPrice.multiply(
                    BigDecimal.valueOf(quantity)
            );
            Trace.log("Cart.total() -> " + amount.toPlainString());
            return amount;
        }
    }

    // Chỉ Inventory có trách nhiệm thay đổi tồn kho.
    static class Inventory {
        private final Map<String, Integer> stock = new HashMap<>();

        Inventory(String sku, int initialQuantity) {
            if (initialQuantity < 0) {
                throw new IllegalArgumentException("Tồn kho âm");
            }
            stock.put(sku, initialQuantity);
        }

        int available(String sku) {
            return stock.getOrDefault(sku, 0);
        }

        void reserve(String sku, int quantity) {
            Trace.log("Inventory.reserve(" + sku + ", " + quantity + ")");
            if (quantity <= 0) {
                throw new IllegalArgumentException("Số lượng phải dương");
            }
            int before = available(sku);
            if (before < quantity) {
                throw new IllegalStateException("Không đủ hàng");
            }
            stock.put(sku, before - quantity);
            Trace.log("Inventory: " + sku + " từ " + before
                    + " còn " + available(sku));
        }

        void release(String sku, int quantity) {
            Trace.log("Inventory.release(" + sku + ", " + quantity + ")");
            stock.put(sku, available(sku) + quantity);
            Trace.log("Inventory: " + sku + " trở lại "
                    + available(sku));
        }
    }

    static class PaymentDeclinedException extends RuntimeException {
        PaymentDeclinedException() {
            super("Thanh toán bị từ chối");
        }
    }

    static class PaymentGateway {
        private final boolean approved;

        PaymentGateway(boolean approved) {
            this.approved = approved;
        }

        String pay(BigDecimal amount) {
            Trace.log("PaymentGateway.pay(" + amount.toPlainString() + ")");
            if (!approved) {
                Trace.log("PaymentGateway: từ chối");
                throw new PaymentDeclinedException();
            }
            Trace.log("PaymentGateway: thành công TX-001");
            return "TX-001";
        }
    }

    static class Order {
        final String id;
        final String sku;
        final int quantity;
        final BigDecimal amount;
        final String transactionId;

        Order(String id, Cart cart, BigDecimal amount,
              String transactionId) {
            this.id = id;
            this.sku = cart.sku;
            this.quantity = cart.quantity;
            this.amount = amount;
            this.transactionId = transactionId;
        }
    }

    static class Notifier {
        void send(Order order) {
            Trace.log("Notifier.send(" + order.id + ")");
        }
    }

    // OrderService phối hợp những đối tượng khác.
    static class OrderService {
        private final Inventory inventory;
        private final PaymentGateway payment;
        private final Notifier notifier;

        OrderService(Inventory inventory, PaymentGateway payment,
                     Notifier notifier) {
            this.inventory = inventory;
            this.payment = payment;
            this.notifier = notifier;
        }

        Order checkout(Cart cart) {
            Trace.log("OrderService.checkout()");

            BigDecimal total = cart.total();
            inventory.reserve(cart.sku, cart.quantity);

            final String transactionId;
            try {
                transactionId = payment.pay(total);
            } catch (PaymentDeclinedException ex) {
                inventory.release(cart.sku, cart.quantity);
                Trace.log("OrderService: hủy do thanh toán thất bại");
                throw ex;
            }

            Order order = new Order("ORD-001", cart, total, transactionId);
            Trace.log("OrderService: tạo " + order.id);
            notifier.send(order);
            return order;
        }
    }

    public static void main(String[] args) {
        Cart cart = new Cart("BOOK", 2, new BigDecimal("100000"));
        Inventory inventory = new Inventory("BOOK", 5);
        PaymentGateway payment = new PaymentGateway(true);
        Notifier notifier = new Notifier();

        OrderService service =
                new OrderService(inventory, payment, notifier);

        Trace.log("Main: gọi checkout(cart)");
        Order order = service.checkout(cart);
        Trace.log("Main: nhận " + order.id);

        System.out.println("Tồn cuối: " + inventory.available("BOOK"));
    }
}
~~~

To run:

~~~bash
javac ObjectInteractionDemo.java
java ObjectInteractionDemo
~~~

Output with `new PaymentGateway(true)`:

~~~text
01 Main: gọi checkout(cart)
02 OrderService.checkout()
03 Cart.total() -> 200000
04 Inventory.reserve(BOOK, 2)
05 Inventory: BOOK từ 5 còn 3
06 PaymentGateway.pay(200000)
07 PaymentGateway: thành công TX-001
08 OrderService: tạo ORD-001
09 Notifier.send(ORD-001)
10 Main: nhận ORD-001
Tồn cuối: 3
~~~

The example deliberately uses one product and fixed order/transaction identifiers for clarity. In production, order and transaction IDs must be generated or obtained from suitably reliable sources; inventory, payments, and notifications generally require more sophisticated persistence, error handling, transactions, and concurrency control.

## 3. Reading the Execution Timeline from Start to Finish

The following table describes the **main messages** and model changes rather than merely listing isolated lines of code.

| Step | Caller → receiver | Method/operation | Result and effects |
| --- | --- | --- | --- |
| 1 | `Main → OrderService` | `checkout(cart)` | Starts the checkout request |
| 2 | `OrderService → Cart` | `total()` | Returns `BigDecimal("200000")` |
| 3 | `OrderService → Inventory` | `reserve("BOOK", 2)` | Decreases `BOOK` stock from 5 to 3 |
| 4 | `OrderService → PaymentGateway` | `pay(200000)` | Returns transaction ID `"TX-001"` |
| 5 | `OrderService` | `new Order(...)` | Creates a new `Order` object |
| 6 | `OrderService → Notifier` | `send(order)` | Sends a notification (only logs here) |
| 7 | `OrderService → Main` | `return order` | Returns a reference to the created `Order` |

One operation can produce **multiple log lines**. For example, the `Inventory.reserve` call is logged at step 04, and step 05 logs the updated state. Console sequence numbers represent **the order of recorded events**, not necessarily the number of objects or method calls.

A useful way to verify the flow is to construct a state table:

| Point in time | `cart.quantity` | `inventory.available("BOOK")` | Payment | `order` |
| --- | ---: | ---: | --- | --- |
| Before `checkout` | 2 | 5 | Not called | Does not exist |
| After `cart.total()` | 2 | 5 | Not called | Does not exist |
| After `reserve` | 2 | 3 | Not called | Does not exist |
| After successful `pay` | 2 | 3 | Approved, `TX-001` | Not yet created |
| After `new Order` | 2 | 3 | Approved | `ORD-001` |
| After `return` | 2 | 3 | Approved | Variable `order` in `main` points to the new order |

Note: `Cart.total()` only calculates and returns a value; it **does not** reduce stock. Stock reduction is the responsibility of `Inventory.reserve`. Keeping these responsibilities distinct helps locate bugs accurately.

## 4. UML Sequence Diagram: Who Calls Whom, and in What Order?

A sequence diagram represents interactions along **a top-to-bottom timeline**. Each column represents an object or actor; horizontal arrows represent calls or replies. Compare it with the program's successful path:

~~~mermaid
sequenceDiagram
    actor Main
    participant Service as OrderService
    participant Cart
    participant Stock as Inventory
    participant Pay as PaymentGateway
    participant Notice as Notifier

    Main->>Service: checkout(cart)
    activate Service
    Service->>Cart: total()
    Cart-->>Service: 200000
    Service->>Stock: reserve("BOOK", 2)
    Stock-->>Service: hoàn tất, tồn còn 3
    Service->>Pay: pay(200000)
    Pay-->>Service: "TX-001"
    Note over Service: new Order("ORD-001", ...)
    Service->>Notice: send(order)
    Notice-->>Service: hoàn tất
    Service-->>Main: order
    deactivate Service
~~~

How to read it:

- **`Main → OrderService`**: the coordinator receives a request from the calling code.
- **`OrderService → Cart`**: requests price information and receives the result.
- **`OrderService → Inventory`**: requests an operation on inventory state.
- **`OrderService → PaymentGateway`**: requests payment and receives a transaction ID.
- **`OrderService → Notifier`**: passes the order object to the notification component.
- **Return arrow for `order`**: the `Order` object is not duplicated when returned; the method returns **a reference value**.

These arrows show **synchronous calls**: the caller waits for a method to complete before continuing. When using queues, asynchronous events, callbacks, or multiple threads, both the diagram and the reasoning about order must reflect the actual execution mechanism.

## 5. How Do Objects Hold References to One Another?

In the constructor:

~~~java
OrderService service =
        new OrderService(inventory, payment, notifier);
~~~

`service` is a reference variable pointing to an `OrderService` instance. Inside that object, the `inventory`, `payment`, and `notifier` fields also hold references to three instances created in `main`.

~~~mermaid
flowchart LR
    M["Biến service ở main"] --> S["OrderService instance"]
    V["Biến inventory ở main"] --> I["Inventory instance"]
    S -->|inventory| I
    S -->|payment| P["PaymentGateway instance"]
    S -->|notifier| N["Notifier instance"]
~~~

Because `service.inventory` and variable `inventory` in `main` refer to the same instance:

~~~java
inventory.reserve("BOOK", 1);
~~~

and:

~~~java
// Bên trong OrderService:
this.inventory.reserve("BOOK", 1);
~~~

both calls operate on **the same inventory** if made in a valid state. This is a natural example of **multiple references pointing to the same object** during an interaction flow.

When `OrderService.checkout` calls `notifier.send(order)`, the `order` parameter of `send` receives a copy of the reference value to **the same Order object** created inside `checkout`. Java passes arguments **by value**, even when the value is a reference.

Two references pointing to the same instance do not imply they are the same *variable*. Reassigning one reference variable does not automatically change the reference value in the other.

## 6. Tracing the Failure Path: Payment Declined

If you change the following in `main`:

~~~java
PaymentGateway payment = new PaymentGateway(false);
~~~

`PaymentGateway.pay` throws `PaymentDeclinedException`. `OrderService.checkout` catches that exception type, calls `inventory.release` to release reserved stock, then rethrows the exception. It creates no `Order` and never calls `Notifier`.

To observe the result without ending in a stack trace, inside `main` replace the `checkout` call and final inventory printout with:

~~~java
Trace.log("Main: gọi checkout(cart)");
try {
    Order order = service.checkout(cart);
    Trace.log("Main: nhận " + order.id);
} catch (PaymentDeclinedException ex) {
    Trace.log("Main: nhận lỗi " + ex.getMessage());
}
System.out.println("Tồn cuối: " + inventory.available("BOOK"));
~~~

Output for this path:

~~~text
01 Main: gọi checkout(cart)
02 OrderService.checkout()
03 Cart.total() -> 200000
04 Inventory.reserve(BOOK, 2)
05 Inventory: BOOK từ 5 còn 3
06 PaymentGateway.pay(200000)
07 PaymentGateway: từ chối
08 Inventory.release(BOOK, 2)
09 Inventory: BOOK trở lại 5
10 OrderService: hủy do thanh toán thất bại
11 Main: nhận lỗi Thanh toán bị từ chối
Tồn cuối: 5
~~~

~~~mermaid
sequenceDiagram
    actor Main
    participant Service as OrderService
    participant Stock as Inventory
    participant Pay as PaymentGateway

    Main->>Service: checkout(cart)
    Note over Service: total = 200000
    Service->>Stock: reserve("BOOK", 2)
    Stock-->>Service: tồn còn 3
    Service->>Pay: pay(200000)
    Pay--xService: PaymentDeclinedException
    Service->>Stock: release("BOOK", 2)
    Stock-->>Service: tồn trở lại 5
    Service--xMain: ném lại ngoại lệ
~~~

Compare **the successful path** and **the failure path**:

| Condition | Calls `release`? | Creates `Order`? | Calls `Notifier`? | Final stock |
| --- | --- | --- | --- | ---: |
| Payment approved | No | Yes | Yes | 3 |
| Payment declined | Yes | No | No | 5 |
| Insufficient stock at `reserve` | Not in this catch branch | No | No | Unchanged from initial stock |

**Example limitations:** releasing inventory here models only one specific failure path in a **single-threaded, in-memory** program. Real applications must address network errors, timeouts, successful payments with lost responses, concurrent shoppers, idempotency, and durable transactions. Mechanically calling `release` after every error can be wrong, especially when it is uncertain whether the payment provider processed the transaction. Notifications are also often sent asynchronously with retries after successful order persistence.

## 7. How the Call Stack Explains Execution Order

Suppose execution is inside `Inventory.reserve` after a call from `OrderService.checkout`:

~~~text
[Đỉnh call stack]
Inventory.reserve(...)
OrderService.checkout(...)
ObjectInteractionDemo.main(...)
[Đáy call stack]
~~~

When `reserve` returns, its stack frame ends, and execution resumes in `checkout` after the `reserve` call. Then `checkout` invokes `PaymentGateway.pay`; a `pay` frame appears on the stack, and control returns to `checkout` after `pay` finishes.

The call stack answers **“Which method is currently calling which other method?”**. By contrast:

- **Object diagrams** answer “Which instances exist and reference one another?”
- **Sequence diagrams** answer “In what order do calls occur?”
- **State tables** answer “How do values inside each object change?”
- **Logs/breakpoints** provide concrete execution evidence to compare against expectations.

Do not confuse **a stack frame** with **an object**. A method may be invoked repeatedly on the same instance, and multiple different methods may act on one shared instance.

## 8. Practicing Debugging an Interaction Flow

In IntelliJ IDEA, Eclipse, or VS Code with a Java debugger, set breakpoints at the following locations:

1. `OrderService.checkout`, immediately before `cart.total()`: inspect which instance the `cart` parameter references and whether `quantity = 2`.
2. `Inventory.reserve`, before `stock.put(...)`: inspect `sku`, `quantity`, and `before = 5`.
3. After `inventory.reserve(...)` in `checkout`: verify that inventory is now 3.
4. Inside `PaymentGateway.pay`: inspect `amount = 200000` and the `approved` flag.
5. Immediately before `return order`: inspect `order.id`, `order.amount`, `order.transactionId`, and final stock.

During debugging, **Step Into** enters the called method; **Step Over** executes the call and moves to the next statement; **Step Out** runs until the current method returns control to its caller.

This table is useful when investigating defects:

| Point in time | Executing object | Method | Input | Output/exception | State before → after |
| --- | --- | --- | --- | --- | --- |
| T1 | `Cart` | `total` | No arguments | 200000 | Unchanged |
| T2 | `Inventory` | `reserve` | BOOK, 2 | Completed | 5 → 3 |
| T3 | `PaymentGateway` | `pay` | 200000 | TX-001 | Unchanged in this example |
| T4 | `OrderService` | `checkout` | `cart` | `order` | Creates an order object |
| T5 | `Notifier` | `send` | `order` | Completed | Logs only |

In larger applications, include **request IDs/correlation IDs** in logs to connect events belonging to one request; when several requests run concurrently, log-line order alone can be misleading. There is no need to log passwords, card numbers, or sensitive data merely to understand object calls.

## 9. Common Misconceptions

### Confusing Which Object Owns an Update

If the inventory count is wrong, inspect the updating `Inventory` object—for example, `reserve` and `release`—rather than looking only at the result printed by `main`. `main` merely observes state.

### Confusing a Returned Reference with Object Creation

~~~java
Order order = service.checkout(cart);
~~~

`checkout` creates an `Order` and returns a reference to it. The statement in `main` **does not create a second Order**. Likewise, passing `order` to `Notifier.send` does not duplicate that object.

### Confusing a Method's Statement Order with the Complete Flow

Within `checkout`, statements execute sequentially, but a call such as `reserve` executes code inside another object. To determine the final state, trace **into the invoked methods** rather than reading only their names.

### Diagramming Only the Successful Path

If `reserve` throws `IllegalStateException`, neither `payment.pay` nor `new Order` runs. If `pay` throws `PaymentDeclinedException`, the `catch` branch executes and no `Order` is created. A diagram that shows only success and omits exceptions can conceal critical behavior.

### Treating a Diagram as Complete Proof

A diagram is a model created by a designer or reader. To verify that the program actually follows it, compare **code, breakpoints, logs, and state**. With asynchronous or multithreaded flows, completion order may differ from initial assumptions.

## 10. Exercises and Answers

**Exercise 1.** The cart has `quantity = 2` and initial inventory is `5`. On the successful path, how much remains after `reserve`, and who performs the update?

**Answer:** 3 remain. The `Inventory` instance updates its state when `OrderService` calls `reserve("BOOK", 2)`.

**Exercise 2.** Why can `Main` observe a stock level of 3 when the deduction happens inside `OrderService`?

**Answer:** The `inventory` variable in `main` and the `inventory` field inside `service` point to **the same instance**. `Inventory.reserve` modifies that instance's state.

**Exercise 3.** With `new PaymentGateway(false)`, does `Notifier.send` execute? Why?

**Answer:** No. `pay` throws `PaymentDeclinedException`, and `catch` restores inventory and rethrows; control never reaches order creation or notification.

**Exercise 4.** `OrderService` calls `notifier.send(order)`. Does `Notifier` receive an independent copy of the entire `Order`?

**Answer:** No. Java passes a copy of **the reference value** to the parameter; the caller and receiver initially refer to the same `Order` object.

**Exercise 5.** What should you add to a trace to distinguish two concurrent checkout requests?

**Answer:** A correlation/request ID associated with each checkout and propagated through its steps; in multithreaded programs, add thread/request information appropriate to the infrastructure. The single-threaded example's `Trace.step` counter does not reliably describe concurrent requests.

**Exercise 6.** When the error is “payment collected but no order created,” which interactions should you trace?

**Suggested answer:** Start with what `PaymentGateway.pay` returned, whether it timed out or threw, what `OrderService` did afterward, whether `new Order` was invoked, whether the order was persisted (if the real system has a repository), and whether retry/compensation paths exist. Do not infer outcomes from a single “pay called” log line.

## Putting It All Together

To analyze an OOP scenario, proceed through these steps: **list the instances → identify the entry point → trace calls and return values → record before/after state → examine failure paths → verify with a debugger/logs → represent the flow in a sequence diagram**.

A good diagram always connects a method name and receiving object to **a concrete effect**. Understanding how call flow combines with object state is what lets us explain accurately how an OOP program operates.
