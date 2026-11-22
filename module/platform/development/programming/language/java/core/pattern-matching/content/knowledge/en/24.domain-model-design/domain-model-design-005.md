# Representing Commands with Records in Domain Model Design (Java 21+)

## 1. What Is a Command and Why Use a Record?

In domain model design, a **command** is a message expressing an *intent/request to perform an action*: creating an order, adding an item, submitting an order, or cancelling an order. A command may be accepted or rejected after checking business rules.

Examples:

- `CreateOrder(orderId, customerId)`: requests creating a new order.
- `AddItem(orderId, sku, quantity)`: requests adding a quantity of an item to an order.
- `SubmitOrder(orderId)`: requests confirming/submitting an order.
- `CancelOrder(orderId, reason)`: requests cancelling an order with a reason.

A **Java record** is a suitable choice for a data-carrying command because a record focuses on **data components**, automatically providing a constructor, accessors, `equals()`, `hashCode()`, and `toString()` based on its components. By default, a record cannot extend other classes and its component fields are `final`; this makes it easy to describe a message with stable data.

Minimal example:

~~~java
record CreateOrder(String orderId, String customerId) {}

CreateOrder command = new CreateOrder("ORD-1", "C-7");
System.out.println(command.orderId());   // ORD-1
System.out.println(command.customerId()); // C-7
~~~

There is no `setOrderId()` or `setCustomerId()`. A command should generally carry immutable data after creation so that the handler can process a single, clear request accurately.

**Distinguishing three concepts:**

| Concept | Meaning | Example |
| --- | --- | --- |
| **Command** | A request to do something; can be rejected | `SubmitOrder("ORD-1")` |
| **Event** | An event that has already occurred, expressing a past fact | `OrderSubmitted("ORD-1")` |
| **Domain state / entity** | The current business state that needs to be protected by rules | Order `ORD-1` is in `DRAFT` |

Records can be used for many kinds of messages and value objects, but **a command is not synonymous with an event**. Simply being able to instantiate a `SubmitOrder` record does not mean the order has been successfully submitted.

## 2. From Isolated Records to a Typed Command Model

An application with multiple command types usually needs a common type for a router/handler to accept. Java supports `sealed interface`, which allows declaring the **permitted set of commands**:

~~~java
sealed interface OrderCommand
        permits CreateOrder, AddItem, SubmitOrder, CancelOrder {}

record CreateOrder(String orderId, String customerId)
        implements OrderCommand {}

record AddItem(String orderId, String sku, int quantity)
        implements OrderCommand {}

record SubmitOrder(String orderId)
        implements OrderCommand {}

record CancelOrder(String orderId, String reason)
        implements OrderCommand {}
~~~

The example above illustrates the structure and should be placed in an appropriate file/class in real-world usage. The records listed in `permits` are all valid subtypes of `OrderCommand`, and since records are inherently `final`, no arbitrary subclasses can extend these records.

**Advantages of a sealed hierarchy:**

1. The source code clearly expresses the valid command types supported by the module.
2. The compiler can check **exhaustiveness** when using pattern matching in a `switch` over `OrderCommand`.
3. When adding a new command type, dispatch sites that do not handle it completely can produce a compile-time error, helping catch missing logic when the domain model changes.
4. Each record has the exact data needed for one intent; this avoids a "catch-all command" containing many nullable fields depending on a `type` string.

**Limitations:** a sealed hierarchy is only closed within the scope of compiled Java types; it does not automatically validate JSON, sender permissions, business validity, or commands coming from external sources. If the application needs dynamic third-party plugin extensibility, `sealed` may not fit the extensibility requirement.

## 3. Designing Command Data: Carrying Intent, Not Handling Behavior

A command should answer the question **"who is requesting to do what, on which target, and with what data?"** rather than deciding how to read from or write to the database. For example:

~~~java
record AddItem(String orderId, String sku, int quantity) {}
~~~

The components have clear roles:

- `orderId`: identifier of the affected aggregate/entity.
- `sku`: identifier of the product to add.
- `quantity`: requested quantity.
- **No** `EntityManager`, `Connection`, `Repository`, or `HttpClient` fields, because those are behavioral dependencies, not data of the business intent.

For commands, names typically use **imperative verbs**: `CreateOrder`, `AddItem`, `CancelOrder`. Avoid using a single record named `Order` both as an entity with a lifecycle and as all requests to mutate that entity; the two roles have different invariants and lifecycles.

A command may also include `actorId`, `requestId`, timestamp, or tracing metadata **if** they belong to the business contract. However, you should not automatically trust a client-supplied `actorId` value to grant permissions: authentication and authorization must still rely on a trusted identity source in the application layer.

## 4. Validating Commands Directly in the Compact Constructor

A record does not prevent creating an invalid command just because its fields are `final`. We need to protect **conditions that hold true for every instance**, such as non-null/non-blank IDs and positive quantities.

Java records support a **compact canonical constructor**:

~~~java
record AddItem(String orderId, String sku, int quantity) {
    public AddItem {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId không được trống");
        }
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku không được trống");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity phải > 0");
        }
        orderId = orderId.strip();
        sku = sku.strip();
    }
}
~~~

In a compact constructor, Java automatically assigns the **validated/normalized constructor parameters** to the component fields after the constructor body. There is no need for `this.orderId = orderId;` or manual assignment of component fields in the compact constructor form.

Distinguish two layers of checks:

- **Command data validation**: missing ID, blank string, non-positive quantity; can be checked immediately when instantiating the record.
- **Business state validation**: whether the order exists, whether it has already been submitted, whether the requester has permission, whether inventory is in stock; requires context and entity/repository access, and is typically handled by an application/domain service.

You should not force a command constructor to connect to a database to decide whether an order is in `DRAFT`. Doing so makes commands hard to instantiate, hard to test, and coupled to infrastructure.

## 5. Records Are Shallowly Immutable, Not Deeply Immutable

A record's component fields are `final`, but **the object a field references** can still mutate if it is a mutable object. For example, a record containing a `List` is not necessarily safely immutable:

~~~java
import java.util.ArrayList;
import java.util.List;

record UnsafeBatch(List<String> items) {}

List<String> list = new ArrayList<>();
list.add("A");
UnsafeBatch batch = new UnsafeBatch(list);
list.add("B");

// batch.items() now also observes the element "B".
~~~

External data modified the record's contents without creating a new instance. You can use a **defensive copy**:

~~~java
record Batch(List<String> items) {
    public Batch {
        items = List.copyOf(items);
    }
}

List<String> source = new ArrayList<>();
source.add("A");
Batch batch = new Batch(source);
source.add("B");

System.out.println(batch.items()); // [A]
~~~

`List.copyOf` creates an unmodifiable snapshot of the list structure and rejects null lists or null elements. However, this is only a **shallow copy**: if the elements are mutable objects, an element's state can still change. A command containing a list of truly immutable records/value objects gives a safer model.

Cases that require attention include `List`, `Map`, `Set`, arrays, `Date` (mutable), and mutable domain objects. For arrays, you must copy both on input **and** on output if you want to avoid exposing internal data. Never assume `record` means "deeply immutable".

## 6. Dispatching Commands with Pattern Matching in `switch`

Since Java 21, **record patterns** can be used in `switch` to deconstruct components directly:

~~~java
static String describe(OrderCommand command) {
    return switch (command) {
        case CreateOrder(var id, var customerId) ->
            "Tạo đơn " + id + " cho " + customerId;

        case AddItem(var id, var sku, var quantity) ->
            "Thêm " + quantity + " " + sku + " vào " + id;

        case SubmitOrder(var id) ->
            "Gửi đơn " + id;

        case CancelOrder(var id, var reason) ->
            "Hủy đơn " + id + ": " + reason;
    };
}
~~~

In each `case`:

1. The compiler determines whether the command has the matching record type.
2. The record pattern extracts components in the **exact declaration order**.
3. Pattern variables declared with `var` have their types inferred from the component types, for example `id` and `sku` are `String`, and `quantity` is `int`.
4. The matching branch produces the result of the `switch expression`.

There is no need for manual casting like `(AddItem) command` followed by calling each accessor. Because `OrderCommand` is sealed and the `switch` handles all permitted subtypes, the example above does not need a `default` branch. When a new subtype is added to the hierarchy, the compiler can report `switch` statements/expressions that are no longer exhaustive—a significant design benefit.

**Regarding `null`:** `switch (command)` on a reference selector does not automatically route `null` to `default`; you should define an explicit policy. In the complete handler example below, `Objects.requireNonNull(command)` rejects `null` before the `switch`. If you want to handle `null` into a result, add `case null -> ...`.

The cases above are examples of pure value dispatch; a **real-world handler** also needs to execute the use case, check state, and persist the result.

## 7. Placing Commands Alongside State and Handler: Processing Flow

A simple model of a single processing cycle:

~~~text
Command record
     |
     v
Application handler
     |
     +--> validate structural data (already protected by constructor)
     +--> load domain state / aggregate
     +--> apply business rules
     +--> produce new state / write transaction
     +--> return result or report error
~~~

Example with `AddItem("ORD-1", "SACH", 2)`:

- The command record only represents the request "add two items with SKU SACH to ORD-1".
- The handler looks up order `ORD-1`.
- The domain rule only allows adding items if the order is still `DRAFT`.
- If valid, it creates a new snapshot/state and saves it.
- If the order is already `SUBMITTED`, the handler **rejects** it; the command does not "mutate" the entity itself.

**Architectural note:** a command record is not an **event**. Only after successful execution does the system have grounds to emit an event such as `ItemAdded` or `OrderSubmitted` (if the application needs events). In the runnable example below, the handler only returns a message and updates an in-memory map; it does **not** build an event sourcing system.

## 8. End-to-End Program: Record Commands + Sealed Interface + Handler

Save the full code to **`CommandRecordDemo.java`** and run it with Java 21+:

~~~java
import java.util.*;

public class CommandRecordDemo {
    sealed interface Command
            permits CreateOrder, AddItem, SubmitOrder, CancelOrder {}

    record CreateOrder(String orderId, String customerId)
            implements Command {
        public CreateOrder {
            orderId = requireText(orderId, "orderId");
            customerId = requireText(customerId, "customerId");
        }
    }

    record AddItem(String orderId, String sku, int quantity)
            implements Command {
        public AddItem {
            orderId = requireText(orderId, "orderId");
            sku = requireText(sku, "sku");
            if (quantity <= 0)
                throw new IllegalArgumentException("quantity phải > 0");
        }
    }

    record SubmitOrder(String orderId) implements Command {
        public SubmitOrder {
            orderId = requireText(orderId, "orderId");
        }
    }

    record CancelOrder(String orderId, String reason)
            implements Command {
        public CancelOrder {
            orderId = requireText(orderId, "orderId");
            reason = requireText(reason, "reason");
        }
    }

    static String requireText(String value, String name) {
        if (value == null || value.isBlank())
            throw new IllegalArgumentException(name + " không được trống");
        return value.strip();
    }

    enum Status { DRAFT, SUBMITTED, CANCELLED }
    record Line(String sku, int quantity) {}

    record Order(String id, String customerId,
                 List<Line> lines, Status status) {
        public Order {
            Objects.requireNonNull(id);
            Objects.requireNonNull(customerId);
            lines = List.copyOf(lines);
            Objects.requireNonNull(status);
        }
    }

    static final class Handler {
        private final Map<String, Order> orders = new LinkedHashMap<>();

        String handle(Command command) {
            Objects.requireNonNull(command, "command");

            return switch (command) {
                case CreateOrder(var id, var customerId) -> {
                    if (orders.containsKey(id))
                        yield "Đơn đã tồn tại: " + id;

                    orders.put(id, new Order(
                            id, customerId, List.of(), Status.DRAFT));
                    yield "Tạo đơn " + id;
                }

                case AddItem(var id, var sku, var quantity) -> {
                    Order order = requireOrder(id);
                    requireDraft(order);

                    List<Line> next = new ArrayList<>(order.lines());
                    next.add(new Line(sku, quantity));
                    orders.put(id, new Order(
                            order.id(), order.customerId(),
                            next, order.status()));

                    yield "Thêm " + quantity + " " + sku
                            + " vào " + id;
                }

                case SubmitOrder(var id) -> {
                    Order order = requireOrder(id);
                    requireDraft(order);
                    if (order.lines().isEmpty())
                        throw new IllegalStateException("Đơn trống");

                    orders.put(id, new Order(
                            order.id(), order.customerId(),
                            order.lines(), Status.SUBMITTED));
                    yield "Gửi đơn " + id;
                }

                case CancelOrder(var id, var reason) -> {
                    Order order = requireOrder(id);
                    requireDraft(order);

                    orders.put(id, new Order(
                            order.id(), order.customerId(),
                            order.lines(), Status.CANCELLED));
                    yield "Hủy đơn " + id + ": " + reason;
                }
            };
        }

        private Order requireOrder(String id) {
            Order order = orders.get(id);
            if (order == null)
                throw new IllegalStateException(
                        "Không tìm thấy đơn: " + id);
            return order;
        }

        private static void requireDraft(Order order) {
            if (order.status() != Status.DRAFT)
                throw new IllegalStateException(
                        "Đơn không ở DRAFT");
        }

        Order find(String id) {
            return requireOrder(id);
        }
    }

    public static void main(String[] args) {
        Handler handler = new Handler();

        System.out.println(handler.handle(
                new CreateOrder("  ORD-1 ", " C-7 ")));
        System.out.println(handler.handle(
                new AddItem("ORD-1", "SACH", 2)));
        System.out.println(handler.handle(
                new SubmitOrder("ORD-1")));

        System.out.println(handler.find("ORD-1").status());
        System.out.println(handler.find("ORD-1").lines().size());

        System.out.println(handler.handle(
                new CreateOrder("ORD-1", "C-7")));

        try {
            new AddItem("ORD-1", "BUT", 0);
        } catch (IllegalArgumentException e) {
            System.out.println("Lỗi đầu vào: " + e.getMessage());
        }

        try {
            handler.handle(
                    new AddItem("ORD-1", "BUT", 1));
        } catch (IllegalStateException e) {
            System.out.println("Lỗi nghiệp vụ: " + e.getMessage());
        }

        System.out.println(handler.handle(
                new CreateOrder("ORD-2", "C-8")));
        System.out.println(handler.handle(
                new CancelOrder("ORD-2", " Khách đổi ý ")));
        System.out.println(handler.find("ORD-2").status());
    }
}
~~~

Compile/run:

~~~bash
javac --release 21 CommandRecordDemo.java
java CommandRecordDemo
~~~

Exact output:

~~~text
Tạo đơn ORD-1
Thêm 2 SACH vào ORD-1
Gửi đơn ORD-1
SUBMITTED
1
Đơn đã tồn tại: ORD-1
Lỗi đầu vào: quantity phải > 0
Lỗi nghiệp vụ: Đơn không ở DRAFT
Tạo đơn ORD-2
Hủy đơn ORD-2: Khách đổi ý
CANCELLED
~~~

**Analysis of key points:**

- `CreateOrder("  ORD-1 ", " C-7 ")` is normalized via `strip()` in the compact constructor, so the handler receives `ORD-1` and `C-7`.
- `AddItem` validates `quantity > 0` when the record is created, preventing a structurally invalid command from reaching deeper into the handler.
- The handler uses `switch (command)` and record patterns to match the exact command type and extract its components without casting.
- `Order` in the example is an **immutable state snapshot**; `List.copyOf` creates an unmodifiable list from `Line` instances whose components are `String` and `int`.
- When adding an item, the handler copies the list, appends a `Line`, and creates a new `Order`; it does not mutate an existing state record.
- Once the order is `SUBMITTED`, `AddItem` is still a **data-valid** command, but the handler rejects it due to the **business rule** "only DRAFT orders may be modified".
- When a create-order command with a duplicate ID is sent, the handler returns the message `Đơn đã tồn tại`. This is only an in-memory illustrative policy, **not a distributed idempotency guarantee**.
- `CancelOrder` stores the `CANCELLED` status and returns a message with the reason; the example does not persist the reason to an audit/event store.
- `Handler` uses a local `LinkedHashMap` with no database connection, transactions, or thread safety. Do not use the demo handler as-is in production.

## 9. Using `when` for a Prioritized Command Branch

Java 21 supports `when` guards in pattern `switch`. They can be used to specialize how a command is handled:

~~~java
static String category(Command command) {
    return switch (command) {
        case AddItem(var id, var sku, var qty) when qty >= 10 ->
                "Yêu cầu nhập số lượng lớn";
        case AddItem(var id, var sku, var qty) ->
                "Yêu cầu thêm sản phẩm";
        case CreateOrder(var id, var customerId) ->
                "Yêu cầu tạo đơn";
        case SubmitOrder(var id) ->
                "Yêu cầu gửi đơn";
        case CancelOrder(var id, var reason) ->
                "Yêu cầu hủy đơn";
    };
}
~~~

Place the `AddItem ... when qty >= 10` branch **before** the general `AddItem` branch; placing the general branch first can dominate the guarded branch and cause a compile-time error. The guard is evaluated **after** the pattern matches; `qty` already has type `int` and can be used in the guard expression.

The snippet above illustrates categorization. For input validation rules, keep validation in the constructor, and keep state-dependent rules in the handler/domain service. You should not turn your entire domain policy into a single `switch` packed with hard-to-test guards.

## 10. Design Choices and Limitations to Know

### 10.1. When Is a Record Not Suitable?

Records are suitable for **command messages, DTOs, or value objects**. An entity/aggregate with a complex identity and lifecycle is sometimes better modeled as a regular class, especially when state changes need to be guarded by domain methods.

Do not use a record just to create a "shorter object" if the entity requires its own identity rules, lazy loading, ORM proxies, or controlled mutable state. A `record` defines equality by **component values** (`equals()`), which does not inherently express entity identity. In the example, `Order` is only an immutable snapshot for simplicity; production code may replace it with a proper aggregate/entity.

### 10.2. Command Types with Many Parameters

When a command has too many parameters of the same `String` type, positional calls are easy to mix up:

~~~java
new CreateOrder("ORD-1", "C-7"); // orderId then customerId
~~~

You can use **value objects**:

~~~java
record OrderId(String value) {
    public OrderId {
        if (value == null || value.isBlank())
            throw new IllegalArgumentException("OrderId rỗng");
        value = value.strip();
    }
}

record CustomerId(String value) {
    public CustomerId {
        if (value == null || value.isBlank())
            throw new IllegalArgumentException("CustomerId rỗng");
        value = value.strip();
    }
}

record CreateOrderTyped(OrderId orderId, CustomerId customerId) {}
~~~

Then the compiler prevents accidentally passing a `CustomerId` into an `OrderId` parameter. Whether to split out dedicated value objects depends on domain complexity and frequency of use; avoid creating unnecessary wrapper types when the model is simple.

### 10.3. Command Records and Data from JSON/APIs

External messages must go through **parsing + validation + authorization**, rather than being mechanically instantiated into records:

~~~text
HTTP/Queue payload
    -> DTO/parser
    -> check types, required fields, data limits
    -> construct valid command record
    -> authenticate/authorize based on trusted context
    -> handler/domain
~~~

If using a JSON library, support for mapping records, constructors, and sealed hierarchies depends on the library, version, and configuration. Do not assume every serializer automatically knows how to pick the right command subtype. You may need a discriminator field like `kind` at the **API boundary**, while still converting it into a strongly typed hierarchy inside the domain.

Never use a client-supplied `actorId` as proof of permission to cancel an order; authorization must be verified from an authenticated session/token/context.

### 10.4. Idempotency and Duplicate Command Handling

A command may be resent due to client retries or a message broker providing at-least-once delivery. Having two command records with equal `equals()` **does not** automatically make side effects execute only once.

If a use case requires deduplication, an intentional policy is needed, such as:

- a valid, stable `requestId`/idempotency key for a single logical request;
- persisting idempotency processing state within the same transaction;
- unique constraints/optimistic locking or business-level duplicate handling;
- defining the response to return when a duplicate request arrives.

`CreateOrder` in the demo only checks a map for duplicate IDs and returns a string. It does not solve crashes/retries, race conditions, or exactly-once processing.

### 10.5. Concurrency, Transactions, and State Immutability

An immutable `Command` record **does not automatically make the handler thread-safe**. Two threads reading the same `DRAFT` order simultaneously, each creating a new state and writing it to the map/database, can cause a lost update.

In production, you need an appropriate mechanism: transactions, synchronization locks, version numbers with optimistic concurrency, per-aggregate sequencing, or actor/message-queue ordering. Using immutable commands is a good starting point, not a replacement for atomicity and consistency of business state.

### 10.6. Schema Evolution

Adding a new component to a record changes its canonical constructor, accessors, `equals()`/`hashCode()`, and representation. This can affect callers, serialization, and messages already sitting in queues or event logs.

For API/messaging communication, consider versioning, optional fields with defaults validated at the boundary, adapters converting old payloads to new commands, and compatibility tests. Do not treat adding a field to a record as a completely harmless change.

## 11. Common Pitfalls

| Pitfall | Why It Is a Problem | Appropriate Practice |
| --- | --- | --- |
| Putting a repository/database connection in a command record | Mixes intent with infrastructure, hard to test | Records hold only data; handlers hold dependencies |
| Assuming `final` fields mean deep immutability | Mutable lists/arrays and elements can still change | Defensive copies, immutable value objects |
| Using an entity record in place of a command record | Mixes entity identity/lifecycle with request messages | Separate commands from state/aggregates |
| Having a command constructor read from the database | Requires external context to check state | Constructors validate data invariants; handlers/domain check state |
| Using `switch` with `default` for all sealed commands | Easily hides newly added commands that were forgotten | Prefer exhaustive `switch` without `default` when appropriate |
| Forgetting `null` for the selector | Pattern `switch` on references does not accept `null` by default | Explicit `requireNonNull` or `case null` |
| Assuming creating a command means it has executed | A command is only a request | The handler returns a result/exception after domain checks |
| Treating `equals()` as duplicate-request protection | Value equality differs from transactional deduplication | Idempotency key + persistence policy |
| Assuming immutable commands make the handler thread-safe | State/repositories can still suffer race conditions | Transactions and concurrency control |
| Tagging commands with strings and casting manually | Bypasses static type and exhaustiveness checks | Use a `sealed interface` and pattern `switch` |
| Putting client data into a command and skipping authorization | Input data may be untrusted | Authenticate/authorize at the application boundary |

## 12. Exercises and Hints

**Exercise 1 — Add a new command.** Add `UpdateDeliveryAddress(orderId, address)` to the sealed interface `Command`. Observe how a `switch expression` without `default` requires you to handle the new branch. Validate `address` in the compact constructor, but check whether the order is eligible for an address change in the handler.

**Exercise 2 — Separate domain rules.** In the demo, which rules belong to the `AddItem` constructor and which belong to `Handler`? Why can `quantity > 0` be checked immediately, while "order must be in DRAFT" cannot?

**Exercise 3 — Immutability.** Write a record `BulkAdd(String orderId, List<Line> lines)` performing `List.copyOf(lines)` in its compact constructor. Why is this necessary? What would still be missing if `Line` contained a mutable `ArrayList`?

**Exercise 4 — Tests.** Write tests for the following paths of `Handler`: creating a new ID succeeds, creating a duplicate ID, submitting an empty order fails, submitting an order with lines succeeds, adding a line after submission fails, cancelling a `DRAFT` order succeeds, and cancelling a second time fails.

**Exercise 5 — Event vs. command.** When the handler successfully processes `SubmitOrder`, why should `OrderSubmitted` (if emitted) be a different message from `SubmitOrder`? What happens if validation of `SubmitOrder` fails?

**Guided answers:**

- Exercise 1: add the subtype to `permits` and add the corresponding pattern branch to the `switch`; otherwise, compile-time exhaustiveness will detect the missing case.
- Exercise 2: positive quantity is an independent property of the request; order status depends on the aggregate loaded from storage.
- Exercise 3: `List.copyOf` fixes the list structure, but it does not deep-copy mutable elements.
- Exercise 4: assert state, exceptions, and responses; do not only assert a single output string.
- Exercise 5: a command expresses what **is intended to be done**, while an event expresses what **has happened**. When a command is rejected, `OrderSubmitted` must not be emitted as if it succeeded.

## References

- [JEP 395 — Records](https://openjdk.org/jeps/395): record classes, purpose, and member synthesis mechanism.
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): closing the subtype set of an interface/class.
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): destructuring records in pattern matching (Java 21).
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): type/record patterns in `switch` and exhaustiveness.
- [Oracle Java 21 — Record Classes](https://docs.oracle.com/en/java/javase/21/language/records.html).
- [Java SE 21 API — List.copyOf](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): unmodifiable snapshot, null restrictions, and defensive copying.
