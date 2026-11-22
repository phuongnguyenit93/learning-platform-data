# State Pattern: Organizing Behavior by Object State

**Topic:** OOP → Design Patterns → **State and state-dependent behavior**.

**Objective:** Understand why the same call may produce different outcomes depending on current state; implement State Pattern in Java, define valid transitions, test workflows, and recognize when an enum or simple switch suffices.

## 1. Why Does State Affect Behavior?

Consider an online order. The system lets customers or staff perform operations such as:

- **Confirm payment** for a newly created order.
- **Mark the order as handed over for shipping** after payment confirmation.
- **Cancel an order** while it is still awaiting payment.

The same **cancel()** request has different meanings: a new order can be canceled, but a shipped order cannot be canceled through the same workflow. Likewise, a paid order should not have its payment reconfirmed as if no payment had occurred.

In other words, **valid behavior depends on state**. Ignoring state can let the system accept meaningless operations or execute an incorrect workflow.

For a small version, a direct check works:

~~~java
void confirmPayment() {
    if (status != OrderStatus.CREATED) {
        throw new IllegalStateException(
                "Chỉ đơn mới tạo mới được xác nhận thanh toán");
    }
    status = OrderStatus.PAID;
}
~~~

This code is perfectly reasonable with only a few states and short rules. As operations and variants grow, **if/switch** conditions may spread across methods such as **confirmPayment()**, **markShipped()**, **cancel()**, **allowedActions()**, and **nextStep()**. Adding a state then requires editing multiple places, and branches can contradict one another.

**State Pattern** organizes those behaviors by placing each state's logic in a dedicated object and letting the business object delegate to its current state object.

## 2. What Is State Pattern?

State is a **behavioral design pattern** that lets an object respond differently to operations as its **internal state** changes. To callers, the object appears to change behavior while its public API can remain unchanged.

Four common roles:

| Role | Meaning | Example |
| --- | --- | --- |
| **Context** | Object used by clients; holds the current state and delegates behavior | **Order** |
| **State** | Contract for state-dependent operations | **OrderState** |
| **Concrete State** | Implements behavior for one state | **CreatedState**, **PaidState**, **ShippedState**, **CancelledState** |
| **Client** | Invokes Context APIs without directly controlling the state class | Controller, service, or code in **main** |

General relationship:

~~~mermaid
classDiagram
    class Order {
        -state: OrderState
        +confirmPayment()
        +markShipped()
        +cancel()
        +status() OrderStatus
        +allowedActions() Set~Action~
    }
    class OrderState {
        <<interface>>
        +status() OrderStatus
        +allowedActions() Set~Action~
        +confirmPayment(order)
        +markShipped(order)
        +cancel(order)
    }
    class CreatedState
    class PaidState
    class ShippedState
    class CancelledState
    Order o--> OrderState : trạng thái hiện tại
    OrderState <|.. CreatedState
    OrderState <|.. PaidState
    OrderState <|.. ShippedState
    OrderState <|.. CancelledState
~~~

Here **Order** does not have to ask “what is the current state?” in every operation. It invokes **state.confirmPayment(this)** or **state.cancel(this)**. Each state determines which behavior is allowed and which state follows.

**Key point:** State Pattern does not remove business rules. When state-specific differences are substantial, it places those rules in units that are easier to find, test, and extend.

## 3. Define the State Machine Before Writing Classes

Before writing Java, list states and transition events. This example simplifies the workflow to four states:

| Current state | Confirm payment | Mark shipped | Cancel |
| --- | --- | --- | --- |
| **CREATED** — newly created | Transition to **PAID** | Reject | Transition to **CANCELLED** |
| **PAID** — payment confirmed | Reject | Transition to **SHIPPED** | Reject |
| **SHIPPED** — handed over to shipping | Reject | Reject | Reject |
| **CANCELLED** — canceled | Reject | Reject | Reject |

**Example business assumption:** an order cannot be canceled after payment, because that case requires a separate refund workflow. Real systems may permit cancellation requests, refunds, returns, or additional intermediate states. Do not copy this table as a universal commerce policy.

State transition diagram:

~~~mermaid
stateDiagram-v2
    [*] --> CREATED
    CREATED --> PAID: confirmPayment()
    CREATED --> CANCELLED: cancel()
    PAID --> SHIPPED: markShipped()
    SHIPPED --> [*]
    CANCELLED --> [*]
~~~

In this diagram, **SHIPPED** and **CANCELLED** have no outgoing transitions *within the illustrative model*. That does not mean a shipped order cannot later become **DELIVERED**, **RETURNED**, or another state in a real workflow.

### Distinguish State, Event, and Behavior

- **State:** where the order currently is in its lifecycle, such as **PAID**.
- **Event/command:** an operation being requested, such as **markShipped()**.
- **Guard/condition:** what must be true to accept a command, such as being in **PAID** with confirmed handover information.
- **State transition:** a change from **PAID** to **SHIPPED**.
- **Side effect:** sending email, calling a payment gateway, or writing to a database. Design these separately to prevent duplicate execution.

State Pattern mainly organizes **behavior and transitions**; it does not guarantee transactions, authentication, synchronization, or validity of external events.

## 4. Complete Java 17+ Example

Create **OrderStateDemo.java**. The code is standalone and requires neither Spring nor external libraries.

**Chosen design:**

1. **Order** is the Context and keeps its current **OrderState** in a **private** field.
2. **OrderState** defines operations a state can handle; the default implementation rejects invalid transitions.
3. Each concrete state overrides only the operations it permits.
4. State objects are shared as singletons **because they hold no mutable state of their own**.
5. **allowedActions()** tells the UI which operations are allowed; the domain still enforces actual validity.

~~~java
import java.util.Objects;
import java.util.Set;

public class OrderStateDemo {

    public enum OrderStatus {
        CREATED, PAID, SHIPPED, CANCELLED
    }

    public enum Action {
        CONFIRM_PAYMENT, MARK_SHIPPED, CANCEL
    }

    public static final class Order {
        private static final OrderState CREATED_STATE = new CreatedState();
        private static final OrderState PAID_STATE = new PaidState();
        private static final OrderState SHIPPED_STATE = new ShippedState();
        private static final OrderState CANCELLED_STATE = new CancelledState();

        private final String id;
        private OrderState state = CREATED_STATE;

        public Order(String id) {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException(
                        "Mã đơn hàng không được rỗng");
            }
            this.id = id.trim();
        }

        public String id() {
            return id;
        }

        public OrderStatus status() {
            return state.status();
        }

        public Set<Action> allowedActions() {
            return state.allowedActions();
        }

        public String nextStep() {
            return state.nextStep();
        }

        // Client chỉ gọi API nghiệp vụ của Order.
        public void confirmPayment() {
            state.confirmPayment(this);
        }

        public void markShipped() {
            state.markShipped(this);
        }

        public void cancel() {
            state.cancel(this);
        }

        // Chỉ code bên trong Order được chuyển trạng thái trực tiếp.
        private void transitionTo(OrderState next) {
            state = Objects.requireNonNull(next, "next");
        }

        private static IllegalStateException invalid(
                OrderState state, String operation) {
            return new IllegalStateException(
                    operation + " is not allowed in " + state.status());
        }

        private interface OrderState {
            OrderStatus status();

            Set<Action> allowedActions();

            String nextStep();

            default void confirmPayment(Order order) {
                throw invalid(this, "confirmPayment");
            }

            default void markShipped(Order order) {
                throw invalid(this, "markShipped");
            }

            default void cancel(Order order) {
                throw invalid(this, "cancel");
            }
        }

        private static final class CreatedState implements OrderState {
            @Override
            public OrderStatus status() {
                return OrderStatus.CREATED;
            }

            @Override
            public Set<Action> allowedActions() {
                return Set.of(Action.CONFIRM_PAYMENT, Action.CANCEL);
            }

            @Override
            public String nextStep() {
                return "Chờ xác nhận thanh toán";
            }

            @Override
            public void confirmPayment(Order order) {
                order.transitionTo(PAID_STATE);
            }

            @Override
            public void cancel(Order order) {
                order.transitionTo(CANCELLED_STATE);
            }
        }

        private static final class PaidState implements OrderState {
            @Override
            public OrderStatus status() {
                return OrderStatus.PAID;
            }

            @Override
            public Set<Action> allowedActions() {
                return Set.of(Action.MARK_SHIPPED);
            }

            @Override
            public String nextStep() {
                return "Chờ bàn giao vận chuyển";
            }

            @Override
            public void markShipped(Order order) {
                order.transitionTo(SHIPPED_STATE);
            }
        }

        private static final class ShippedState implements OrderState {
            @Override
            public OrderStatus status() {
                return OrderStatus.SHIPPED;
            }

            @Override
            public Set<Action> allowedActions() {
                return Set.of();
            }

            @Override
            public String nextStep() {
                return "Đơn đã bàn giao vận chuyển";
            }
        }

        private static final class CancelledState implements OrderState {
            @Override
            public OrderStatus status() {
                return OrderStatus.CANCELLED;
            }

            @Override
            public Set<Action> allowedActions() {
                return Set.of();
            }

            @Override
            public String nextStep() {
                return "Đơn đã hủy";
            }
        }
    }

    public static void main(String[] args) {
        Order first = new Order("ORD-001");

        System.out.println(first.status());
        first.confirmPayment();
        System.out.println(first.status());

        try {
            first.cancel();
        } catch (IllegalStateException error) {
            System.out.println(error.getMessage());
        }

        System.out.println(first.status()); // Thao tác lỗi không đổi state.
        first.markShipped();
        System.out.println(first.status());

        Order second = new Order("ORD-002");
        second.cancel();
        System.out.println(second.status());
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac OrderStateDemo.java
java OrderStateDemo
~~~

Output:

~~~text
CREATED
PAID
cancel is not allowed in PAID
PAID
SHIPPED
CANCELLED
~~~

### Explanation of the Execution Flow

- **new Order("ORD-001")** creates the Context in **CREATED_STATE**.
- Calling **confirmPayment()** makes **Order** delegate to **CreatedState**, which transitions the Order to **PAID_STATE**.
- Calling **cancel()** in **PAID_STATE** finds no permitted override, so **OrderState.cancel()** throws **IllegalStateException**. The state remains **PAID**.
- Calling **markShipped()** makes **PaidState** permit a transition to **SHIPPED_STATE**.
- Another new order can be canceled while in **CREATED** and move to **CANCELLED_STATE**.

The **confirmPayment()** method simulates recording verified payment. **Do not invoke it merely because a client sends a “I have paid” message**: in a real integration, the server must check a trusted event/callback or a verified payment status with the payment system before recording the change.

### Why Use a Private State Instead of a Public Setter?

If **order.setStatus(OrderStatus.SHIPPED)** existed, any caller could jump directly from **CREATED** to **SHIPPED**, bypassing rules. The example uses meaningful **command methods** such as **confirmPayment()** and **markShipped()**, with direct transitions encapsulated inside **Order**.

State objects can be shared safely **with respect to their own internal data**, because they have no mutable state. However, **Order** still has a mutable **state** field, so the entire Order **is not automatically thread-safe**. Production concurrency is discussed later.

## 5. Same API, Different Behavior by State

State Pattern does more than “store an enum as a class.” It is especially useful when a state governs **many different behaviors**.

In this example:

| Behavior | CREATED | PAID | SHIPPED | CANCELLED |
| --- | --- | --- | --- | --- |
| **confirmPayment()** | Transition to PAID | Error | Error | Error |
| **markShipped()** | Error | Transition to SHIPPED | Error | Error |
| **cancel()** | Transition to CANCELLED | Error | Error | Error |
| **allowedActions()** | Confirm payment, cancel | Mark shipped | Empty | Empty |
| **nextStep()** | Await payment confirmation | Await shipping handover | Handed over to shipping | Canceled |

A client invokes the same **nextStep()** method yet receives different descriptions from the current state. When there are state-specific behaviors such as **calculating cancellation charges**, **allowing address changes**, **determining SLAs**, **checking operation permissions**, or **deciding next events**, organizing them by state may be clearer than sprawling switches across classes.

For a UI, **allowedActions()** helps hide or disable irrelevant buttons, but it is **not a security control**. The server must still authenticate the user, check permissions and business constraints, and verify current state when executing the command. State displayed by the UI may be stale.

## 6. Testing State Transition Rules

State Pattern needs tests for both **valid paths** and **rejected operations**. Adding an enum value or changing state permissions can easily cause bugs if only happy paths are tested.

Example with **JUnit 5 (Jupiter)**: place **OrderStateDemoTest.java** in the same package:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Set;
import org.junit.jupiter.api.Test;

class OrderStateDemoTest {

    @Test
    void dongThanhToanVaBanGiaoDungThuTu() {
        var order = new OrderStateDemo.Order("ORD-001");

        assertEquals(OrderStateDemo.OrderStatus.CREATED,
                order.status());

        order.confirmPayment();
        assertEquals(OrderStateDemo.OrderStatus.PAID,
                order.status());

        order.markShipped();
        assertEquals(OrderStateDemo.OrderStatus.SHIPPED,
                order.status());
    }

    @Test
    void donMoiTaoCoTheHuy() {
        var order = new OrderStateDemo.Order("ORD-002");
        order.cancel();

        assertEquals(OrderStateDemo.OrderStatus.CANCELLED,
                order.status());
        assertEquals(Set.of(), order.allowedActions());
    }

    @Test
    void khongDuocBanGiaoKhiChuaThanhToan() {
        var order = new OrderStateDemo.Order("ORD-003");

        assertThrows(IllegalStateException.class,
                order::markShipped);
        assertEquals(OrderStateDemo.OrderStatus.CREATED,
                order.status());
    }

    @Test
    void khongDuocHuySauKhiXacNhanThanhToan() {
        var order = new OrderStateDemo.Order("ORD-004");
        order.confirmPayment();

        assertThrows(IllegalStateException.class, order::cancel);
        assertEquals(OrderStateDemo.OrderStatus.PAID,
                order.status());
    }

    @Test
    void hanhDongDuocPhepThayDoiTheoState() {
        var order = new OrderStateDemo.Order("ORD-005");

        assertEquals(Set.of(
                OrderStateDemo.Action.CONFIRM_PAYMENT,
                OrderStateDemo.Action.CANCEL),
                order.allowedActions());

        order.confirmPayment();

        assertEquals(Set.of(OrderStateDemo.Action.MARK_SHIPPED),
                order.allowedActions());
    }
}
~~~

These tests require JUnit Jupiter on the classpath. **OrderStateDemo.java** runs independently without JUnit. In production, add tests for refunds, timeouts, duplicate confirmations, restoring state from a database, and concurrent operations.

### State-Matrix Tests

For systems with many states, create a **state × operation matrix** and test which cells accept or reject an operation. A single end-to-end happy path misses invalid transitions. Treat the transition table as a design artifact reviewed alongside code/tests when these rules form important business requirements.

## 7. How Does State Differ from Strategy, Enum, and State Machines?

These concepts are related but not identical:

| Technique | Primary mechanism | Appropriate when |
| --- | --- | --- |
| **Enum + if/switch** | Stores a state code, uses conditionals to decide behavior | Few states and operations; simple, stable rules |
| **State Pattern** | Context delegates to a state object; each state defines behavior/transitions | Many state-dependent behaviors, complex branches, or frequent changes |
| **Strategy Pattern** | Client/Context uses an interchangeable algorithm | Multiple approaches to one task: taxes, shipping costs, export formats |
| **Finite State Machine (FSM)** | Formal model of states, events, guards, and transitions | Need specifications, verification, detection of unreachable states, or complex flows |
| **Workflow/State Machine Framework** | Executes configured/coded transitions, guards, events, persistence, and actions | Long, branching workflows with async steps and specific operational requirements |

**State Pattern is one way to implement a state machine**, but not every FSM needs State Pattern. A transition table and pure function may suffice for a small workflow. Conversely, a workflow library can implement an FSM using data tables/configuration without one concrete class per state.

### State and Strategy Both Use Composition/Polymorphism but Serve Different Purposes

Suppose **ShippingFeePolicy** has two algorithms, **StandardFeePolicy** and **ExpressFeePolicy**. The client or configuration usually selects which policy to use; that suggests **Strategy**. An **Order** transitioning from **CREATED** to **PAID** following payment confirmation instead represents evolving **lifecycle state**, suggesting **State**.

A common distinction: **Strategy** may be selected externally and remain unchanged after a call; **State** often determines or influences the next state of Context. This is about **intent**, not a rigid syntactic restriction.

## 8. Who Decides the Next State?

In the example, each **concrete state** invokes **order.transitionTo(...)**. That is one valid design.

There are at least three reasonable options:

1. **State requests the transition:** the concrete state knows the next state, keeping code close to the deciding behavior. The Java example uses this approach.
2. **Context coordinates the transition:** the concrete state returns a result/event, and Context applies the transition. Useful when Context must enforce further invariants or execute a uniform workflow.
3. **External coordinator:** a workflow engine or application service evaluates guards, executes actions, and persists state. Useful when processes involve transactions, several aggregates, timeouts, or asynchronous events.

Do not introduce a coordinator merely to “follow the pattern.” Put rules where readers can easily answer: **in which state, which operation is allowed, why, and with what result?**

### Should Default Methods Reject Operations?

In the example, **OrderState** uses default methods that throw errors. This keeps concrete state code concise and focused on allowed operations, while providing consistent rejection behavior.

However, if a state fails to override a method because of a programming error, the default rejection may conceal missing behavior. For critical business rules, test the entire matrix. Another design could require interfaces to declare every behavior or use a data-driven transition table for easier audits. **Default methods here are illustrative, not a requirement of State Pattern.**

## 9. Production: Databases, Transactions, and Concurrency

The in-memory example teaches the State model but is not a complete ordering system. Three boundaries matter.

### 9.1. Persist State Durably

When the application restarts, the **state** field in RAM disappears. Real applications commonly store a state code such as **CREATED** or **PAID** in a database. When loading the aggregate, the system maps the stored code to its corresponding State object.

**There is no need to serialize the State implementation directly.** Storing a state code separates business data from Java class names and supports schema migrations. State restoration should be a controlled internal API, not a public setter allowing any client to jump between states.

### 9.2. Concurrent Requests Can Violate Expectations

Suppose an order is in **CREATED**. One request invokes **confirmPayment()** while another invokes **cancel()** at nearly the same time. If both read the old state and write a new one without coordination, the result may include a *lost update* or two conflicting business events.

Possible controls depend on the architecture:

- Transactions and database locks appropriate to the data model.
- **Optimistic locking** with a version column: only one update against the old version succeeds, while another request must recheck state.
- **Conditional updates** with state preconditions, such as “change CREATED → PAID only if current state is still CREATED.”
- Serializing commands per order ID if the architecture truly requires it.

Illustrative SQL idea (actual syntax and transaction semantics depend on the database):

~~~sql
UPDATE orders
SET status = 'PAID', version = version + 1
WHERE id = :order_id
  AND status = 'CREATED'
  AND version = :expected_version;
~~~

If the affected row count is **0**, the state/version may have changed or the order may be missing. The application must distinguish causes and respond appropriately. **State Pattern inside the JVM does not provide atomicity across requests or instances.**

### 9.3. Side Effects Must Match Transaction Outcomes

A transition may need to send an email or publish an event. Do not automatically send email before a transaction commits: if the commit fails, a customer may receive a “paid” email even though the database state was never updated.

Depending on requirements, a **transactional outbox** can persist an event in the same transaction as the state change, then a worker publishes it. Consumers need suitable idempotency/deduplication because events may be delivered more than once.

For payments, **confirmPayment** only illustrates a **CREATED** → **PAID** transition after verification. Real systems require transaction IDs, duplicate-callback protection, signature/event verification, refund handling, and pending/failed states. Those are business and infrastructure responsibilities, not guarantees obtained merely by creating State classes.

## 10. Common Mistakes with State Pattern

| Mistake | Consequence | Prevention |
| --- | --- | --- |
| Each state returns only an enum name without distinct behavior | More classes without less complexity | Keep **enum + switch** if it is clear enough |
| Context exposes public **setState(...)** | Clients bypass transition rules | Encapsulate state and expose meaningful business commands |
| Concrete states mix unrelated business operations with direct DB/email calls | High coupling, difficult tests and transaction control | Handle side effects and infrastructure at well-defined boundaries |
| Shared State instances contain mutable data for individual Orders | Cross-order interference and race conditions | Shared States should be stateless; per-order data belongs to Order or a separate State instance |
| State checks rely on UI data fetched earlier | Operations use stale state | Recheck during request handling, with conditional updates |
| Restoring from the DB allows arbitrary transitions | Lifecycle invariants are violated | Use a separate internal restore mechanism; validate data and events |
| Exceptions are inconsistent or swallowed | Clients cannot tell whether transitions failed | Define error outcomes and preserve state after rejected commands |
| Terminal/refund/failure paths are forgotten | Workflows become stuck or branch incorrectly | Diagram and review the full state matrix |
| State Pattern substitutes for authentication/authorization | Users may still call forbidden APIs | Check authorization on the server by user, resource, and operation |

**Do not confuse a change of state with a change of object type.** An **Order** remains the same order with the same identity while responding differently at different processing stages. It is not destroyed and replaced with a new Order subtype after each payment or shipment.

## 11. When to Apply State Pattern and When to Keep Things Simple

**Consider State Pattern when** behavior truly varies by state across many methods, transition logic grows tangled, business teams add states, or state-specific rules are substantial enough to encapsulate independently.

**Keep enum/switch when** there are only 2–3 states, a few readable rules, mostly identical behavior, and little pressure to change. Four classes replacing a short switch may not improve the code.

A practical design-selection process:

1. List states and events; draw a transition matrix.
2. Implement the simplest solution that still preserves invariants.
3. When many behaviors depend on the same state and conditions recur, group logic into State objects.
4. Test all important transitions and invalid cases.
5. Define transaction, persistence, permission, and external-integration boundaries separately from the pattern.
6. Measure readability and modification costs; remove abstractions that do not solve a problem.

The number of states **is not** the only criterion. Two states with complex behavior may warrant State Pattern; many states with data-driven transitions may fit an FSM engine or configuration table better.

## 12. Exercise: Customer Support Ticket Lifecycle

A support system has states **NEW**, **ASSIGNED**, **RESOLVED**, and **CLOSED**. The business rules are:

- From **NEW**, **assign(agentId)** transitions to **ASSIGNED**, or **close()** closes an erroneously created ticket.
- From **ASSIGNED**, **resolve(solution)** transitions to **RESOLVED**.
- From **RESOLVED**, **reopen()** goes back to **ASSIGNED**, or **close()** transitions to **CLOSED**.
- **CLOSED** permits no additional operations in this model.

Implement the exercise:

1. Draw a **Mermaid stateDiagram-v2** and a complete transition table including rejected cases.
2. Implement **Ticket** (Context), **TicketState**, and concrete states in Java. Keep **ticketId**, **agentId**, and **solution** as Ticket business data; never store per-ticket data in a shared singleton State.
3. Design **assign**, **resolve**, **reopen**, and **close** so clients cannot bypass transitions through a public setter.
4. Test the path **NEW → ASSIGNED → RESOLVED → CLOSED**, the path **RESOLVED → ASSIGNED**, and errors such as resolving before assignment or reopening a CLOSED ticket.
5. Explain how you would protect database-backed transitions when users A and B act on the same ticket concurrently.

**Completion criteria:** every event is accepted only in appropriate states, rejected commands leave state unchanged, responsibility for each state is explicit, and database/user-permission dependencies are handled at the proper boundary.

**Remember:** State Pattern organizes behavior that varies by **the current state of the same object**. Used well, transition rules become easier to find and test, avoiding conditionals spread throughout code. Its value follows from real business requirements; persistence, transaction, and concurrency control remain system-design responsibilities.
