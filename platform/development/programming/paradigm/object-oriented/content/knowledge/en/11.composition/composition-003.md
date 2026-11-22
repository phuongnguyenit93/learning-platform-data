# Delegating Work to Other Objects in Java OOP

When an object receives a request, it can **retain responsibility for the workflow** while asking other objects to perform specialized steps. That is **delegation**. Java has no dedicated keyword for delegation: this technique is implemented through **method calls to collaborators**.

For example, a support-request coordinator receives tickets from customers. It does not necessarily need to classify their severity or store them in queues itself:

- `TicketRouter` validates input, determines **the processing order**, and returns the final result.
- `TicketClassifier` classifies tickets according to a set of rules.
- `AssignmentPort` records tickets in the selected queue.
- The client only needs to call `router.route(ticket)` and receive an `Assignment`.

This lesson examines **who delegates to whom, which boundaries data crosses, and who is accountable for success or failure**, distinguishing delegation from object composition in general.

## 1. Understanding a Delegation Flow

~~~mermaid
sequenceDiagram
    actor Caller
    participant R as TicketRouter
    participant C as TicketClassifier
    participant P as AssignmentPort
    Caller->>R: route(ticket)
    R->>R: validate ticket
    R->>C: classify(ticket)
    C-->>R: Queue
    R->>P: assign(ticket.id, queue)
    P-->>R: Assignment
    R-->>Caller: Assignment
~~~

In the diagram, `TicketRouter` is the **delegator** because it accepts responsibility for coordination from the caller. `TicketClassifier` and `AssignmentPort` are **delegates** for their assigned steps. A collaborator may delegate further internally; "delegator" and "delegate" describe **roles in a call**, not special Java class types.

The boundaries to identify are:

| Step | Responsible object | What must be explicit |
| --- | --- | --- |
| Receive request | `TicketRouter` | Input validity and processing order |
| Determine queue | `TicketClassifier` | Classification rules and `Queue` code |
| Record assignment | `AssignmentPort` | Assignment result, errors, and what "accepted" means |
| Return result to client | `TicketRouter` | Never invent a result if a delegate fails |

**Delegation does not mean abandoning responsibility.** The router is still accountable for calling the right steps, handling or propagating errors appropriately, and avoiding fabricated results. It simply does not own the classification algorithm or queue-storage mechanism.

## 2. Standalone Program: Replace Delegates Without Changing the Router

Save as `TicketDelegationDemo.java` (Java 17 or later). This example models an **in-memory** queue and uses no database or remote service.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public class TicketDelegationDemo {
    enum Queue { STANDARD, URGENT, BILLING }

    record Ticket(String id, String summary, int severity) {
        Ticket {
            if (id == null || id.isBlank()
                    || summary == null || summary.isBlank()) {
                throw new IllegalArgumentException("Thiếu thông tin phiếu");
            }
            if (severity < 1 || severity > 5) {
                throw new IllegalArgumentException("Severity phải từ 1 đến 5");
            }
        }
    }

    record Assignment(String ticketId, Queue queue) {
        Assignment {
            if (ticketId == null || ticketId.isBlank()) {
                throw new IllegalArgumentException("Thiếu mã phiếu");
            }
            Objects.requireNonNull(queue, "queue");
        }
    }

    interface TicketClassifier {
        Queue classify(Ticket ticket);
    }

    interface AssignmentPort {
        // Chỉ mô tả hành vi "ghi nhận"; chưa cam kết lưu bền vững.
        Assignment assign(String ticketId, Queue queue);
    }

    static final class SeverityClassifier implements TicketClassifier {
        @Override
        public Queue classify(Ticket ticket) {
            Objects.requireNonNull(ticket, "ticket");
            return ticket.severity() >= 4 ? Queue.URGENT : Queue.STANDARD;
        }
    }

    static final class BillingKeywordClassifier
            implements TicketClassifier {
        @Override
        public Queue classify(Ticket ticket) {
            Objects.requireNonNull(ticket, "ticket");
            return ticket.summary()
                    .toLowerCase(Locale.ROOT)
                    .contains("thanh toán")
                    ? Queue.BILLING : Queue.STANDARD;
        }
    }

    static final class MemoryAssignmentPort implements AssignmentPort {
        private final List<Assignment> history = new ArrayList<>();

        @Override
        public Assignment assign(String ticketId, Queue queue) {
            Assignment result = new Assignment(ticketId, queue);
            history.add(result);
            return result;
        }

        List<Assignment> history() {
            return List.copyOf(history);
        }
    }

    static final class TicketRouter {
        private final TicketClassifier classifier;
        private final AssignmentPort assignments;

        TicketRouter(TicketClassifier classifier,
                     AssignmentPort assignments) {
            this.classifier =
                    Objects.requireNonNull(classifier, "classifier");
            this.assignments =
                    Objects.requireNonNull(assignments, "assignments");
        }

        Assignment route(Ticket ticket) {
            Objects.requireNonNull(ticket, "ticket");

            Queue queue = Objects.requireNonNull(
                    classifier.classify(ticket),
                    "Classifier không được trả null"
            );

            return Objects.requireNonNull(
                    assignments.assign(ticket.id(), queue),
                    "AssignmentPort không được trả null"
            );
        }
    }

    public static void main(String[] args) {
        MemoryAssignmentPort sharedPort = new MemoryAssignmentPort();

        TicketRouter bySeverity = new TicketRouter(
                new SeverityClassifier(), sharedPort
        );
        TicketRouter byTopic = new TicketRouter(
                new BillingKeywordClassifier(), sharedPort
        );

        Assignment first = bySeverity.route(
                new Ticket("T-17", "Không đăng nhập", 2)
        );
        Assignment second = byTopic.route(
                new Ticket("T-18", "Thanh toán lỗi", 5)
        );

        System.out.println(first);
        System.out.println(second);
        System.out.println("Số phân công: " + sharedPort.history().size());
    }
}
~~~

Run:

~~~bash
javac TicketDelegationDemo.java
java TicketDelegationDemo
~~~

Output:

~~~text
Assignment[ticketId=T-17, queue=STANDARD]
Assignment[ticketId=T-18, queue=BILLING]
Số phân công: 2
~~~

**Step-by-step behavior:**

1. `bySeverity` receives ticket `T-17` with severity 2. It **delegates classification** to `SeverityClassifier`; the `STANDARD` result is passed to `MemoryAssignmentPort`.
2. `byTopic` receives ticket `T-18` with severity 5 but uses a **topic-based** classifier. The text "Thanh toán lỗi" matches its keyword, producing `BILLING`. This is not a bug: the contract permits different classification strategies to use their own policies.
3. Both routers use **the same instance** of `sharedPort`, supplied by the application's assembly code. Therefore, the in-memory history contains exactly two records.
4. No object actually sends email or creates a real support ticket. `Assignment` only confirms that **the example's in-memory adapter recorded the request**; it does not represent a real support-service SLA.

Note: `BillingKeywordClassifier` deliberately ignores `severity`. If a real requirement says "every severity-5 ticket must go to URGENT," that must be **a shared rule published in the contract** and honored by every implementation, or enforced by an additional priority layer. Do not infer such a rule from the field name without a specification.

## 3. Composed Objects and Delegated Calls Answer Different Questions

~~~java
private final TicketClassifier classifier;
private final AssignmentPort assignments;
~~~

The two fields show that the router **holds references** to two collaborators. That is an association/object-composition structure (*has-a / uses-a*). Actual delegation happens only when the router calls:

~~~java
Queue queue = classifier.classify(ticket);
Assignment result = assignments.assign(ticket.id(), queue);
~~~

| Concept | Key question | What the example shows |
| --- | --- | --- |
| Composition / association | Which objects does the router use? | Two fields populated through the constructor |
| Delegation | Which work is handed to another object? | Classification and assignment |
| Polymorphism | Which implementation handles the same call? | Severity-based or keyword-based classifier |
| Dependency injection | Who supplies the collaborators? | `main` creates them and passes them to the constructor |
| Encapsulation | Who may modify the assignment history? | `MemoryAssignmentPort` keeps the list private |

A reference field may be used only for lookup or observation, without delegating any work from the public API. Do not label every field a "delegation pattern." Conversely, a method can **receive a delegate as a call-time argument** without storing it in a field.

~~~java
static Queue classifyOnce(
        Ticket ticket, TicketClassifier temporaryClassifier) {
    Objects.requireNonNull(temporaryClassifier, "temporaryClassifier");
    return temporaryClassifier.classify(
            Objects.requireNonNull(ticket, "ticket"));
}
~~~

This is an additional illustrative method: placing it inside `TicketDelegationDemo` makes the example's types available. It shows that delegation **does not require constructor injection**, although constructor injection fits a router that needs both collaborators throughout its lifetime.

## 4. The Router Relies on Delegate Contracts

Java checks the signatures of `classify(Ticket)` and `assign(String, Queue)`; it does not verify the behavior of each implementation.

| Required contract | Implication for the router |
| --- | --- |
| `TicketClassifier` returns a non-null `Queue` for a valid ticket | Its result can be passed to the adapter |
| Classification does not record or modify tickets itself | Easier testing and no hidden side effects |
| `AssignmentPort` returns an `Assignment` with the correct ticketId/queue, or reports an error | Callers know which adapter processed the ticket |
| Errors must not become fake "assigned" results | Preserves accurate business outcomes |
| Durability/timeouts/thread safety | Must be defined for each implementation and real-world requirement |

Example of a faulty `TicketClassifier`:

~~~java
static final class BrokenClassifier implements TicketClassifier {
    @Override
    public Queue classify(Ticket ticket) {
        return null;
    }
}
~~~

This class **compiles** but violates the non-null guarantee. `TicketRouter` rejects its result with a `NullPointerException` containing a clear message. However, a check in the router is not a substitute for contract tests of every classifier.

**Failure order:** If the `Ticket` constructor rejects input, the router is never invoked. If the classifier throws, the adapter is not called. If the adapter fails **after partially writing**, the router does not automatically roll back memory, files, or external transactions. The real adapter's contract must define its failure semantics.

## 5. Delegation Versus Forwarding: When Does an Intermediate Layer Add Value?

Consider pure forwarding:

~~~java
class BareRouter {
    private final AssignmentPort port;

    BareRouter(AssignmentPort port) {
        this.port = port;
    }

    Assignment assign(String id, Queue queue) {
        return port.assign(id, queue);
    }
}
~~~

If `BareRouter` adds no contract, validation, access control, or dependency isolation, it may only lengthen the call chain. Calling another object's method does not always justify creating a new class.

The main `TicketRouter` has a reason to exist: it **coordinates two specialized capabilities**, enforces "classify first → record second," and exposes a `route(Ticket)` API so callers do not have to invoke each component themselves.

A delegation layer is often useful when it:

- Defines a clear **business responsibility** for the caller.
- Centralizes validation or orchestration at the appropriate boundary.
- Hides infrastructure details the caller does not need.
- Allows **implementation substitution** without changing coordination logic.
- Makes it possible to test one boundary without starting the entire system.

On the other hand, multiple classes that each forward the same method call can become unnecessary **pass-through layers**. Evaluate the benefit of each layer before adding it.

## 6. Changing Delegates Does Not Require Inheritance

If the router inherits from the classifier merely to reuse its algorithm:

~~~java
// Thiết kế sai ý nghĩa trách nhiệm:
// class TicketRouter extends SeverityClassifier { ... }
~~~

we are claiming that "the router is a kind of classifier." But the router **uses a classifier** and is responsible for coordination. This relationship is better modeled as **has-a / uses-a**.

In the actual example, `SeverityClassifier` is marked `final` and cannot be subclassed even syntactically. The line above is deliberately commented out to illustrate an incorrect model; it is not valid demo code.

~~~mermaid
classDiagram
    class TicketRouter {
        -TicketClassifier classifier
        -AssignmentPort assignments
        +route(Ticket) Assignment
    }
    class TicketClassifier {
        <<interface>>
        +classify(Ticket) Queue
    }
    class AssignmentPort {
        <<interface>>
        +assign(String, Queue) Assignment
    }
    class SeverityClassifier
    class BillingKeywordClassifier
    class MemoryAssignmentPort
    TicketRouter --> TicketClassifier : classify
    TicketRouter --> AssignmentPort : assign
    TicketClassifier <|.. SeverityClassifier
    TicketClassifier <|.. BillingKeywordClassifier
    AssignmentPort <|.. MemoryAssignmentPort
~~~

**Inheritance remains appropriate** when a subclass truly is a subtype and honors its superclass contract. Delegation is an alternative when we need another object's **capability** without a genuine is-a relationship. The comparison between inheritance and composition can examine designs with several independent dimensions of variation in more detail.

## 7. Distinguishing Delegation from Related Patterns

Delegation is a building block of many design patterns, but each pattern serves a different purpose:

| Technique/pattern | Main purpose | Application in the ticket domain |
| --- | --- | --- |
| **Strategy** | Select a replaceable algorithm | `SeverityClassifier` or `BillingKeywordClassifier` |
| **Adapter** | Bridge an application contract to another technology's API | `AssignmentPort` → a task-management SDK |
| **Decorator** | Wrap an object with the same interface to add behavior | Log before/after `assign` |
| **Proxy** | Control access, lazy loading, or remote invocation | Reject assignments when the caller lacks permission |
| **Facade** | Provide clients a simple API across several components | `TicketRouter.route` coordinates the steps |

Decorator example, implemented as a nested class in `TicketDelegationDemo`:

~~~java
static final class LoggingAssignmentPort implements AssignmentPort {
    private final AssignmentPort delegate;

    LoggingAssignmentPort(AssignmentPort delegate) {
        this.delegate = Objects.requireNonNull(delegate, "delegate");
    }

    @Override
    public Assignment assign(String ticketId, Queue queue) {
        System.out.println("Gọi phân công: " + ticketId);
        Assignment result = delegate.assign(ticketId, queue);
        System.out.println("Adapter đã trả kết quả");
        return result;
    }
}
~~~

This decorator **does not guarantee** durable persistence just because its delegate returns. It also does not manage transactions automatically. Avoid applying a pattern label automatically when one field and a simple call are sufficient.

## 8. Testing Collaboration and Failure Paths

We can add a fake that records calls as a nested class in the demo:

~~~java
static final class RecordingAssignments implements AssignmentPort {
    int calls;
    String lastTicketId;
    Queue lastQueue;

    @Override
    public Assignment assign(String id, Queue queue) {
        calls++;
        lastTicketId = id;
        lastQueue = queue;
        return new Assignment(id, queue);
    }
}
~~~

Then add the following to the demo's `main`:

~~~java
RecordingAssignments recorder = new RecordingAssignments();
TicketRouter router = new TicketRouter(new SeverityClassifier(), recorder);
Assignment result = router.route(new Ticket("T-99", "Lỗi đăng nhập", 5));

if (recorder.calls != 1 || recorder.lastQueue != Queue.URGENT
        || !"T-99".equals(recorder.lastTicketId)
        || result.queue() != Queue.URGENT) {
    throw new AssertionError("Ủy quyền không đúng");
}
~~~

This test confirms that the router forwards the correct ID and queue, calls the adapter **exactly once**, and returns the adapter's result. In addition to testing the delegator, we need:

- **Classifier tests:** Check each strategy against known severity levels/keywords.
- **Contract tests:** Verify that every implementation returns non-null permitted results without modifying the ticket.
- **Integration tests:** Check that real HTTP/database adapters write correctly, report errors accurately, and close resources properly.
- **Failure tests:** An adapter must not be called when classification fails; the router must not return false success when the adapter fails.

These short tests do not require a mocking framework. Fakes help isolate boundaries but do not prove that external systems work correctly.

## 9. Lifecycles, Concurrency, and Delegated Outcomes

Both routers in `main` reference `sharedPort`. Holding a shared reference does not grant **exclusive ownership** to either router. If the port holds a socket or database client, its creator will usually manage its lifecycle unless an explicit ownership-transfer contract says otherwise.

`MemoryAssignmentPort` uses `ArrayList` and is **not thread-safe**. Two concurrent requests calling `assign` on the same port can cause a race condition. A `final` field in the router only fixes the reference; it does not make the port's mutable list safe for concurrent use.

For a real adapter, also distinguish:

1. Was the request **accepted**, or was it **durably recorded**?
2. Did the API call merely finish, or was the ticket **actually assigned** to someone?
3. Could failure and retry produce **duplicate assignments**?
4. If the classifier and port read data at different times, do they require **versioned rules** or a transaction?
5. After a delegate changes, do existing requests still use the old port/classifier or switch to the new one?

If the system requires idempotency, auditing, or transactions, those mechanisms must be designed and tested separately. Delegation **only organizes responsibilities and call paths**; it does not create these operational guarantees.

## 10. Self-Check Exercises

**1. Who is the delegator?** In `TicketRouter.route`, which component classifies and which records assignments?

**Answer:** The router is the delegator. `TicketClassifier` classifies; `AssignmentPort` records assignments. The router still controls the order and returns the result.

**2. If two routers share one `MemoryAssignmentPort`, are there two histories or one?**

**Answer:** One history in the shared instance. Provide two separate ports to isolate state, or define a safe sharing mechanism for concurrent use.

**3. If the classifier returns `null`, can the router proceed to `assign`?**

**Answer:** Not in this example. `Objects.requireNonNull` stops execution before assignment, so no new assignment occurs.

**4. Why does replacing `SeverityClassifier` with `BillingKeywordClassifier` require no change to `TicketRouter`?**

**Answer:** The router only depends on `TicketClassifier.classify`. The chosen implementation is supplied through constructor-based polymorphism.

**5. Can delegation work without a reference field?**

**Answer:** Yes. Accepting a classifier as a method parameter and invoking it is delegation when specialized work is being handed off.

**6. If `AssignmentPort.assign` partially persists data and then throws, does the router roll back automatically?**

**Answer:** No. Failures and side effects must be handled at the adapter or transaction boundary; avoid returning false success.

**7. Does delegation always improve a design?**

**Answer:** No. A wrapper layer that adds no meaningful boundary, validation, or responsibility may only make code harder to read. Introduce a delegate when there is a genuine division of work.

**Key takeaway:** Delegation means **assigning the right portion of work to an object equipped to perform it**. The coordinating object remains responsible for the flow and outcome; collaborators carry out specialized steps. A sound design needs clear contracts, meaningful results, controlled failure paths, and managed lifecycles—not merely another method call on a field.
