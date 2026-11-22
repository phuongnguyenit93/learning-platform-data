# Command Dispatch with Pattern Switch – Java 21 Case Study

When a system receives multiple types of **commands** (state-changing instructions), it needs to decide which business logic handles each command. A common approach is writing multiple `if (command instanceof ...)` checks and casting to each class. As the number of commands grows, the dispatch code easily becomes verbose, misses branches, repeats type checks, and mixes data validation logic with state update logic.

In **Java 21**, a command can be modeled as a **`sealed interface`** with `record` variants, and **pattern matching for `switch`** can be used to perform **dispatch**. The compiler helps check the **exhaustiveness** of a `switch` expression: if a new command type is added to the closed hierarchy and forgotten in the dispatcher, compilation can detect the missing case.

This lesson builds an in-memory order management command dispatcher with three command types: **create order**, **add items**, and **cancel order**. The examples use Java 21+; `sealed` has been final since Java 17, `record` since Java 16, and **record patterns** and **pattern switch** since Java 21. No `--enable-preview` is required.

## 1. What Is Command Dispatch?

A **command** expresses a request to perform an action, usually changing system state. For example:

- `CreateOrder("O-1", 2)`: creates order `O-1` with an initial quantity of 2.
- `AddItems("O-1", 3)`: increases the quantity of order `O-1` by 3.
- `CancelOrder("O-1")`: transitions the order to the canceled state.

The **dispatcher** receives a command, determines its type, and invokes the right business logic. A simple flow:

```text
            Input / API / message consumer
                         |
                     type check
                         |
                      Command
                         |
                 dispatch(Command)
                         |
                  pattern switch
               /       |        \
        CreateOrder  AddItems  CancelOrder
            |          |          |
          create()     add()     cancel()
               \        |        /
                Processing result
                         |
                Response / logging
```

Three responsibilities should be distinguished:

1. **Transport/adapter** receives the input; it may receive `Object`, JSON, a message from a queue, or a deserialized request. This lesson does not implement HTTP or a message broker.
2. **Dispatch** determines the command type, checks basic conditions, and selects the handler.
3. **Business handler** checks the current state and updates data according to business rules.

Using pattern switch **does not automatically create transactions, guarantee exactly-once delivery, or provide multi-threaded synchronization**. Those requirements belong to storage, message processing, and transaction design.

### Are the Command Pattern and Pattern Switch the Same Thing?

The **Command Pattern** in GoF design patterns typically encapsulates an action into an object, which may contain an `execute()` method and a receiver reference. **Pattern switch** is a Java language construct for matching types and data structures.

A command **is not required to have `execute()`**. In this case study, a command is purely immutable data, while the action resides in the dispatcher/handler. This is a reasonable architectural choice for a closed set of commands; it is not a mandatory rule for every Command Pattern system.

## 2. Closed Command Model with a Sealed Interface

The domain variants:

```java
sealed interface Command permits CreateOrder, AddItems, CancelOrder {}

record CreateOrder(String orderId, int quantity) implements Command {}
record AddItems(String orderId, int delta) implements Command {}
record CancelOrder(String orderId) implements Command {}
```

These are **illustrative declarations** belonging to the same class in the complete program in Section 9.

Design rationale:

- `Command` is the supertype of all commands supported by the dispatcher.
- `permits` specifies the three subtypes **allowed to directly implement** `Command`.
- The `record` types implementing `Command` are implicitly `final`. They hold only the data needed for each command and have no default setters.
- `CreateOrder` has `quantity` as the initial quantity; `AddItems` has `delta` as the quantity to add; `CancelOrder` only needs the order identifier.
- A class outside the `permits` list cannot arbitrarily `implements Command`. To add a new command type, the model must be intentionally updated.

Because all permitted subtypes are final records, the set of `Command` variants in the example is **closed**. This enables the compiler to determine which cases must be present in a `switch` over `Command`.

### Why Use Records to Carry Commands?

A command is typically a **message representing intent**: the operation name and its parameters. A `record` automatically provides a constructor, accessors such as `orderId()`, `quantity()`, and `delta()`, and component-based `equals/hashCode/toString` methods.

```java
Command cmd = new CreateOrder("O-1", 2);
```

There is no need for manual casting or building a large inheritance hierarchy to represent this message.

**Limitation:** records have *shallow immutability*. If a component is a mutable object, that object's state can still be modified. In the demo, the components are only `String` and `int`, keeping things simple.

### Command Objects Can Carry Invalid Data

```java
new CreateOrder(null, 2);
new CreateOrder(" ", 2);
new CreateOrder("O-1", 0);
```

These records **can still be constructed** because their default constructors do not enforce business rules. This lesson intentionally checks them in the dispatcher to demonstrate `when` guards. In a real system, you might choose to validate early in the constructor or in a request validation layer; however, ensure the boundary still handles invalid input and maintains an appropriate contract.

## 3. Record Holding Order State

Alongside commands, we need the current state:

```java
record Order(String id, int quantity, boolean canceled) {}
```

`Order` **does not implement `Command`**. It is domain data, distinct from a message requesting an action.

The sample system stores orders in:

```java
private final Map<String, Order> orders = new LinkedHashMap<>();
```

When the quantity or status changes, the code creates a **new `Order`** and replaces the value in the map, rather than mutating a record component. This choice ensures each created `Order` value is not modified in place.

In the example, the map lives only in the memory of a single dispatcher instance. It has no persistence, is not shared across processes, and is **not thread-safe** for concurrent updates. In real-world applications, an appropriate data store, transaction, or synchronization mechanism is required.

## 4. Core Focus: Dispatching with Pattern Switch

The dispatcher receives a `Command` and uses a `switch` expression to return a `String` result code:

```java
String dispatch(Command command) {
    return switch (command) {
        case null -> "INVALID_COMMAND";

        case CreateOrder(var id, var quantity) when invalidId(id) ->
                "INVALID_ID";
        case CreateOrder(var id, var quantity) when quantity <= 0 ->
                "INVALID_QUANTITY";
        case CreateOrder(var id, var quantity) ->
                create(id, quantity);

        case AddItems(var id, var delta) when invalidId(id) ->
                "INVALID_ID";
        case AddItems(var id, var delta) when delta <= 0 ->
                "INVALID_QUANTITY";
        case AddItems(var id, var delta) ->
                add(id, delta);

        case CancelOrder(var id) when invalidId(id) ->
                "INVALID_ID";
        case CancelOrder(var id) ->
                cancel(id);
    };
}
```

This method requires the `invalidId/create/add/cancel` methods included in the full program.

### Why Do Specific Cases with `when` Come Before General Cases?

For `CreateOrder`, the order is:

1. `CreateOrder(...) when invalidId(id)`: checks for null or blank-only IDs.
2. `CreateOrder(...) when quantity <= 0`: checks for non-positive quantities.
3. `CreateOrder(...)` without a guard: only handles cases where the ID and quantity have passed the preceding checks.

When the record pattern matches, the variables `id` and `quantity` are bound and can be used in `when`. A guard is an additional condition on a case, not a new command type.

The branch without `when` covers **every** structurally valid `CreateOrder`. If placed first, the guarded `CreateOrder` branches after it would be **dominated**; the Java compiler rejects this. The same applies to `AddItems` and `CancelOrder`.

**Correct ordering table:**

| Group | Cases checked first | Last case in group |
| --- | --- | --- |
| `CreateOrder` | Invalid ID, non-positive quantity | `create(id, quantity)` |
| `AddItems` | Invalid ID, non-positive delta | `add(id, delta)` |
| `CancelOrder` | Invalid ID | `cancel(id)` |

If both the ID and quantity are invalid, the dispatcher prioritizes returning `INVALID_ID` because that guard comes first. **Case ordering can express business error reporting priority**, not just a syntactic detail.

### Why Use `var` in Record Patterns?

For example, `CreateOrder(var id, var quantity)` deconstructs the two components of the record:

- `id` has static type `String`.
- `quantity` has static type `int`.

`var` does not create dynamic typing. The compiler infers the types from the record's component declarations. More importantly, the `id` component **can be null** because the record does not forbid it. Therefore, `invalidId(id)` must handle null safely.

## 5. Null at Transport vs. Null in Dispatcher

A common scenario: the message-receiving layer has no static `Command` type guarantee. It can be guarded using a type pattern and a negated check:

```java
String route(Object incoming) {
    if (!(incoming instanceof Command command)) {
        return "NOT_A_COMMAND";
    }
    return dispatch(command);
}
```

This snippet has two key points:

1. `incoming instanceof Command command` returns `false` if the input is `null` or an object not implementing `Command`. After the negated `return` branch, `command` is definitely bound and can be used in `dispatch(command)` (**flow scoping**).
2. `dispatch(null)` is handled separately by `case null -> "INVALID_COMMAND"`. Because `route` checks the type first, `route(null)` returns `NOT_A_COMMAND`, whereas calling `dispatch(null)` directly returns `INVALID_COMMAND`.

This difference is a **policy at two different boundaries**, not a Java bug. In a real product, unify the error model if clients expect the same message for null cases.

### Why Does `case null` Need Explicit Declaration?

In Java 21 pattern switch, a `null` selector is not automatically routed to `default` or ordinary type patterns. Without `case null`, a pattern `switch` receiving `null` typically throws `NullPointerException`.

`case null` lets the dispatcher return a predictable error code instead of throwing an unexpected exception. If the contract requires rejecting null with an exception, `Objects.requireNonNull` can be used before the switch; just document the choice clearly.

### Null in a Component vs. Null in the Selector

`new CreateOrder(null, 2)` is a **non-null `Command`**, so `case CreateOrder(var id, var quantity)` still matches with `id == null`. `case null` does not catch this situation. That is why the `invalidId(id)` guard is needed for the component.

A safe ID check:

```java
private static boolean invalidId(String id) {
    return id == null || id.isBlank();
}
```

The `||` operator short-circuits; when `id == null` is true, `id.isBlank()` is not called. Reversing it to `id.isBlank() || id == null` could cause a `NullPointerException`.

## 6. Dispatching vs. Business Processing

After identifying the command type and verifying basic data validity, the dispatcher calls small handler methods.

### `CreateOrder`: Creating with Duplicate Check

```java
private String create(String id, int quantity) {
    if (orders.containsKey(id)) {
        return "ALREADY_EXISTS";
    }
    orders.put(id, new Order(id, quantity, false));
    return "CREATED " + id + " qty=" + quantity;
}
```

`CreateOrder("O-1",2)` creates an active order with quantity 2. A repeated call `CreateOrder("O-1",3)` returns `ALREADY_EXISTS` and does **not** replace the existing order.

This is a simple in-memory duplicate-creation rule. It is **not** equivalent to a full idempotency mechanism for network retries or multiple replicas; see Section 12.

### `AddItems`: Checking Existence, Status, and Overflow

```java
private String add(String id, int delta) {
    Order previous = orders.get(id);
    if (previous == null) {
        return "NOT_FOUND";
    }
    if (previous.canceled()) {
        return "ORDER_CANCELED";
    }

    final int newQuantity;
    try {
        newQuantity = Math.addExact(previous.quantity(), delta);
    } catch (ArithmeticException overflow) {
        return "QUANTITY_OVERFLOW";
    }

    orders.put(id, new Order(id, newQuantity, false));
    return "UPDATED " + id + " qty=" + newQuantity;
}
```

Every `AddItems` command has already passed the `delta > 0` guard in the dispatcher. The handler still needs to check **existing state**: items cannot be added to a non-existent or canceled order.

`Math.addExact` detects `int` overflow. If `Integer.MAX_VALUE + 1` were performed with regular `int` addition, Java would wrap around to a negative number; in the order quantity domain, that result is invalid. The handler catches `ArithmeticException` from the addition and returns `QUANTITY_OVERFLOW`; **the map is not updated** on overflow.

### `CancelOrder`: Handling Repeated Commands

```java
private String cancel(String id) {
    Order previous = orders.get(id);
    if (previous == null) {
        return "NOT_FOUND";
    }
    if (previous.canceled()) {
        return "ALREADY_CANCELED";
    }
    orders.put(id, new Order(id, previous.quantity(), true));
    return "CANCELED " + id;
}
```

Canceling an already-canceled order returns `ALREADY_CANCELED`, without changing the quantity or status.

**Note the distinction:** the first response `CANCELED` and the second response `ALREADY_CANCELED` differ, even though the **state effect** of re-executing does not change. An API requiring the *exact same response* for retried commands may need to store results by command ID to replay the original response.

## 7. Queries Should Be Separated from State-Changing Commands

The dispatcher in this lesson supports only **three write commands**. To inspect the result, we use a separate read method:

```java
String snapshot(String id) {
    if (invalidId(id)) {
        return "INVALID_ID";
    }
    Order order = orders.get(id);
    if (order == null) {
        return "NOT_FOUND";
    }
    return "ORDER " + order.id()
            + " qty=" + order.quantity()
            + " status=" + (order.canceled() ? "CANCELED" : "ACTIVE");
}
```

This is a **state query**, not a state-changing command. Keeping `snapshot` outside `Command` clearly separates the **write model** from **read/query operations**.

In systems applying CQRS, commands and queries may go through two separate handlers/dispatchers or use different read models. This case study only illustrates the basic separation, without implementing full CQRS or event sourcing.

## 8. Processing Flow and Expected Results

After creating a new dispatcher instance, a typical scenario:

| Call | Result | State after command |
| --- | --- | --- |
| `CreateOrder("O-1",2)` | `CREATED O-1 qty=2` | O-1 active, quantity 2 |
| `CreateOrder("O-1",3)` | `ALREADY_EXISTS` | Still quantity 2 |
| `AddItems("O-1",3)` | `UPDATED O-1 qty=5` | O-1 active, quantity 5 |
| `CancelOrder("O-1")` | `CANCELED O-1` | O-1 canceled, quantity 5 |
| `CancelOrder("O-1")` second time | `ALREADY_CANCELED` | Unchanged |
| `AddItems("O-1",1)` | `ORDER_CANCELED` | Unchanged |

The test suite also covers:

- `null` at the transport layer and `null` at the dispatcher input.
- Commands with `orderId == null` or whitespace-only IDs.
- Zero quantity, negative delta.
- Adding to a non-existent order, canceling a non-existent order.
- Creating an order `MAX` with `Integer.MAX_VALUE`, then adding 1 and verifying **no state change** occurs due to overflow.

These cases are more valuable than testing only a happy path, because they verify **guard ordering**, **state constraints**, **basic retry behavior**, and **data preservation on error**.

## 9. Complete, Verified Java 21 Program

Save the exact content below in **`CommandDispatchDemo.java`**:

```java
import java.util.LinkedHashMap;
import java.util.Map;

public final class CommandDispatchDemo {
    sealed interface Command permits CreateOrder, AddItems, CancelOrder {}
    record CreateOrder(String orderId, int quantity) implements Command {}
    record AddItems(String orderId, int delta) implements Command {}
    record CancelOrder(String orderId) implements Command {}
    record Order(String id, int quantity, boolean canceled) {}

    private final Map<String, Order> orders = new LinkedHashMap<>();
    private static int checks;

    private static boolean invalidId(String id) {
        return id == null || id.isBlank();
    }

    String route(Object incoming) {
        if (!(incoming instanceof Command command)) {
            return "NOT_A_COMMAND";
        }
        return dispatch(command);
    }

    String dispatch(Command command) {
        return switch (command) {
            case null -> "INVALID_COMMAND";

            case CreateOrder(var id, var quantity) when invalidId(id) ->
                    "INVALID_ID";
            case CreateOrder(var id, var quantity) when quantity <= 0 ->
                    "INVALID_QUANTITY";
            case CreateOrder(var id, var quantity) ->
                    create(id, quantity);

            case AddItems(var id, var delta) when invalidId(id) ->
                    "INVALID_ID";
            case AddItems(var id, var delta) when delta <= 0 ->
                    "INVALID_QUANTITY";
            case AddItems(var id, var delta) ->
                    add(id, delta);

            case CancelOrder(var id) when invalidId(id) ->
                    "INVALID_ID";
            case CancelOrder(var id) ->
                    cancel(id);
        };
    }

    private String create(String id, int quantity) {
        if (orders.containsKey(id)) {
            return "ALREADY_EXISTS";
        }
        orders.put(id, new Order(id, quantity, false));
        return "CREATED " + id + " qty=" + quantity;
    }

    private String add(String id, int delta) {
        Order previous = orders.get(id);
        if (previous == null) {
            return "NOT_FOUND";
        }
        if (previous.canceled()) {
            return "ORDER_CANCELED";
        }

        final int newQuantity;
        try {
            newQuantity = Math.addExact(previous.quantity(), delta);
        } catch (ArithmeticException overflow) {
            return "QUANTITY_OVERFLOW";
        }

        orders.put(id, new Order(id, newQuantity, false));
        return "UPDATED " + id + " qty=" + newQuantity;
    }

    private String cancel(String id) {
        Order previous = orders.get(id);
        if (previous == null) {
            return "NOT_FOUND";
        }
        if (previous.canceled()) {
            return "ALREADY_CANCELED";
        }
        orders.put(id, new Order(id, previous.quantity(), true));
        return "CANCELED " + id;
    }

    String snapshot(String id) {
        if (invalidId(id)) {
            return "INVALID_ID";
        }
        Order order = orders.get(id);
        if (order == null) {
            return "NOT_FOUND";
        }
        return "ORDER " + order.id()
                + " qty=" + order.quantity()
                + " status=" + (order.canceled() ? "CANCELED" : "ACTIVE");
    }

    private static void expect(String label, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    label + ": expected=" + expected + ", actual=" + actual);
        }
        checks++;
    }

    public static void main(String[] args) {
        CommandDispatchDemo bus = new CommandDispatchDemo();

        expect("null command", "INVALID_COMMAND", bus.dispatch(null));
        expect("null transport", "NOT_A_COMMAND", bus.route(null));
        expect("wrong transport type", "NOT_A_COMMAND", bus.route("noise"));
        expect("create null id", "INVALID_ID", bus.dispatch(new CreateOrder(null, 2)));
        expect("create blank id", "INVALID_ID", bus.dispatch(new CreateOrder(" ", 2)));
        expect("create zero", "INVALID_QUANTITY", bus.dispatch(new CreateOrder("O-1", 0)));
        expect("add null id", "INVALID_ID", bus.dispatch(new AddItems(null, 1)));
        expect("add zero", "INVALID_QUANTITY", bus.dispatch(new AddItems("O-1", 0)));
        expect("cancel blank id", "INVALID_ID", bus.dispatch(new CancelOrder(" ")));
        expect("add missing order", "NOT_FOUND", bus.dispatch(new AddItems("O-1", 1)));
        expect("cancel missing order", "NOT_FOUND", bus.dispatch(new CancelOrder("O-1")));

        expect("create valid", "CREATED O-1 qty=2",
                bus.dispatch(new CreateOrder("O-1", 2)));
        expect("create duplicate", "ALREADY_EXISTS",
                bus.dispatch(new CreateOrder("O-1", 3)));
        expect("route add", "UPDATED O-1 qty=5",
                bus.route(new AddItems("O-1", 3)));
        expect("active snapshot", "ORDER O-1 qty=5 status=ACTIVE",
                bus.snapshot("O-1"));
        expect("cancel", "CANCELED O-1", bus.dispatch(new CancelOrder("O-1")));
        expect("cancel again", "ALREADY_CANCELED",
                bus.dispatch(new CancelOrder("O-1")));
        expect("add after cancel", "ORDER_CANCELED",
                bus.dispatch(new AddItems("O-1", 1)));
        expect("canceled snapshot", "ORDER O-1 qty=5 status=CANCELED",
                bus.snapshot("O-1"));

        expect("create max", "CREATED MAX qty=2147483647",
                bus.dispatch(new CreateOrder("MAX", Integer.MAX_VALUE)));
        expect("overflow", "QUANTITY_OVERFLOW",
                bus.dispatch(new AddItems("MAX", 1)));
        expect("max unchanged", "ORDER MAX qty=2147483647 status=ACTIVE",
                bus.snapshot("MAX"));
        expect("unknown snapshot", "NOT_FOUND", bus.snapshot("missing"));
        expect("null snapshot", "INVALID_ID", bus.snapshot(null));
        expect("duplicate max", "ALREADY_EXISTS",
                bus.dispatch(new CreateOrder("MAX", 2)));
        expect("negative delta", "INVALID_QUANTITY",
                bus.dispatch(new AddItems("MAX", -1)));
        expect("cancel null id", "INVALID_ID",
                bus.dispatch(new CancelOrder(null)));

        System.out.println("PASS assertions=" + checks);
        System.out.println("PASS stored-orders=" + bus.orders.size());
        System.out.println("O-1=" + bus.snapshot("O-1"));
        System.out.println("MAX=" + bus.snapshot("MAX"));
        System.out.println("unknown=" + bus.snapshot("none"));
    }
}
```

Compile and run with JDK 21 or a newer compiler supporting `--release 21`:

```bash
javac --release 21 -Xlint:all -Werror -encoding UTF-8 CommandDispatchDemo.java
java CommandDispatchDemo
```

**Verified exact stdout:**

```text
PASS assertions=27
PASS stored-orders=2
O-1=ORDER O-1 qty=5 status=CANCELED
MAX=ORDER MAX qty=2147483647 status=ACTIVE
unknown=NOT_FOUND
```

### Why Does the Program Print PASS?

The `expect` method compares the **actual** result with the expected string for each case. If they do not match, it throws `AssertionError`, so the program cannot print `PASS assertions=27` if any preceding comparison failed.

- **27 assertions:** covers wrong type, null, blank ID, invalid quantity, duplicate command, non-existent order, repeated cancel, updating a canceled order, and integer overflow.
- **stored-orders=2:** only the two IDs `O-1` and `MAX` were created successfully; invalid commands did not add orders.
- **O-1 ... CANCELED:** the order quantity increased from 2 to 5 before cancellation, and remained unchanged when receiving an add command afterward.
- **MAX ... 2147483647:** the `QUANTITY_OVERFLOW` error did not alter the stored maximum quantity.
- **unknown=NOT_FOUND:** the `snapshot` method reads state and handles non-existent orders without creating new data.

The program compiled cleanly with `javac --release 21 -Xlint:all -Werror`, **with zero warnings**, and produced the exact five lines of stdout shown above.

## 10. Compile-Time Check When a Command Case Is Missing

When a new variant is added to `Command`, a dispatcher using a `switch` expression without `default` forces the code to handle the new subtype.

Example that **intentionally fails to compile**:

```java
public class MissingCommandCase {
    sealed interface Command permits Create, Cancel, Refund {}
    record Create(String id) implements Command {}
    record Cancel(String id) implements Command {}
    record Refund(String id) implements Command {}

    static String handle(Command command) {
        return switch (command) {
            case Create(var id) -> "create";
            case Cancel(var id) -> "cancel";
            // Missing Refund case.
        };
    }
}
```

Compile:

```bash
javac --release 21 -encoding UTF-8 MissingCommandCase.java
```

Reproduced compiler error:

```text
error: the switch expression does not cover all possible input values
1 error
```

**Why:** `Command` permits three records—`Create`, `Cancel`, and `Refund`—but the `switch` only handles two. A `switch` expression must cover all possible input values; the compiler rejects the missing subtype.

The fix is to add `case Refund(var id) -> ...` with valid behavior, along with tests for the refund command. **Do not add `default -> "OK"` just to silence the error**, as it can hide an unimplemented new command.

### No `default` Does Not Mean Null Is Handled

A `switch` that is exhaustive over all subtypes of `Command` can still throw `NullPointerException` on a null selector if `case null` is absent. Hierarchy exhaustiveness and null policy are two separate concerns. The dispatcher in this lesson explicitly adds `case null` to return `INVALID_COMMAND`.

## 11. Compile-Time Check When a General Case Dominates a Specific Case

With pattern matching, **broader cases must come after narrower cases**. Intentionally incorrect example:

```java
public class DominatedCommandCase {
    sealed interface Command permits Create, Cancel {}
    record Create(String id) implements Command {}
    record Cancel(String id) implements Command {}

    static String handle(Command command) {
        return switch (command) {
            case Command any -> "generic";
            case Create(var id) -> "create";
            case Cancel(var id) -> "cancel";
        };
    }
}
```

`case Command any` matches every non-null subtype of `Command`, so the subsequent `Create` and `Cancel` cases can never be selected. Verified result with `javac --release 21`:

```text
error: this case label is dominated by a preceding case label
2 errors
```

This is a **compiler error**, not a warning. Fix it by removing `case Command any` if the hierarchy is closed and all cases are covered, or placing it last if a general fallback branch is genuinely needed.

In the main dispatcher, `when invalidId(id)` and `when quantity <= 0` cases precede the unguarded record case of the same type specifically to avoid this dominance error.

## 12. Idempotency, Retry, Concurrency, and Transactions

Pattern switch decides **which handler to invoke**; it does not solve the distributed systems challenges common in command processing.

### 12.1. Retries and Idempotency

- **`CreateOrder`:** creating with the same ID again returns `ALREADY_EXISTS`; no duplicate state is created. However, the second response differs from the first.
- **`CancelOrder`:** canceling again returns `ALREADY_CANCELED`; the state remains canceled.
- **`AddItems`:** **not idempotent**. Sending `AddItems("O-1",3)` twice will increase the quantity twice if the order is still active.

Therefore, when a consumer may receive duplicate messages due to retries or at-least-once delivery, **do not assume that using `sealed Command` or pattern switch guarantees exactly-once execution**. A common approach is attaching a **command ID/idempotency key** to each request and storing the processed result in the same transaction as the domain update whenever possible.

### 12.2. Concurrency and Lost Updates

The demo uses `LinkedHashMap` and a `get → compute → put` sequence. If multiple threads or processes update the same order concurrently, one update can overwrite another. Transactions, optimistic locking/versioning, locks, or another concurrency control mechanism is needed depending on the storage layer.

You cannot fix this simply by switching between `switch` and `if`. Type dispatching and state synchronization are **two different layers**.

### 12.3. Validation and Trust Boundaries

In the example, the record constructors allow some invalid inputs so the dispatcher's guards clearly demonstrate how they work. In a production system, you can:

- Validate requests during deserialization/parsing (schema, command type, length, required fields).
- Enforce invariants in the command constructor/factory if commands must always be valid upon creation.
- Check authorization before updating domain state.
- Validate current state in the handler, as input validation alone is not sufficient.
- Use structured result types like `Success/ValidationError/NotFound/Conflict` instead of plain strings as in the demo.

In particular, never pass arbitrary input directly into SQL, shell, or HTTP calls just because it matched a record pattern. Pattern matching does not replace input validation and access control.

## 13. Pattern Switch vs. Handler Registry and Polymorphism

Several other approaches can also dispatch commands.

| Criterion | Sealed command + pattern switch | Handler registry / polymorphism |
| --- | --- | --- |
| Command set | Closed, listed via `permits` | Often dynamically extensible |
| Adding a new command | Update `permits` and exhaustive switches | Register a new handler or add an implementation |
| Missing case analysis | Compiler-assisted with sealed hierarchy | May require registry/config/test checks |
| Dispatch code | One readable switch for moderate variant counts | Dispatcher may simply look up and invoke handler |
| Business logic | Should be extracted to methods/services | Can live inside individual handlers |
| Best suited for | Closed domains, internal tools, DSLs, small/medium command sets | Plugin APIs, modular/microservice systems, multi-team extensibility |
| Runtime configuration | Mostly static via Java types | Can rely on DI containers or configuration |

**When is pattern switch appropriate?** When the library controls all variants, you want the compiler to detect unsupported new commands, and the number of branches is small enough to keep the dispatcher readable.

**When should you move to a registry?** When each command handler has many dependencies, commands need to be added as plugins outside the module, or the dispatcher becomes too large. You can keep `sealed Command` in the domain module and delegate from `switch` to injected handlers/services to combine the benefits of both approaches.

The **Visitor Pattern** is another option: each command has `accept(visitor)`, and the visitor defines a `visit` method per subtype. It decouples operations but often increases boilerplate and requires updating the visitor interface when adding variants. Do not choose it merely because the word "pattern" appears; the choice depends on extensibility needs.

## 14. Testing the Dispatcher Properly

Both **the response and the resulting state** must be verified, because an `UPDATED` response could still be printed incorrectly if the map was not updated.

### Minimum Test Matrix

| Case | Input | Expected result |
| --- | --- | --- |
| Null selector | `dispatch(null)` | `INVALID_COMMAND` |
| Non-command transport | `route("noise")` | `NOT_A_COMMAND` |
| Null/blank ID | `CreateOrder(null,2)`, `CancelOrder(" ")` | `INVALID_ID` |
| Non-positive quantity/delta | `CreateOrder("O-1",0)`, `AddItems("O-1",-1)` | `INVALID_QUANTITY` |
| Operation on missing order | `AddItems("O-1",1)` | `NOT_FOUND` |
| Create new | `CreateOrder("O-1",2)` | `CREATED O-1 qty=2` |
| Duplicate create | `CreateOrder("O-1",3)` | `ALREADY_EXISTS`; order remains qty 2 |
| Add items | `AddItems("O-1",3)` | `UPDATED O-1 qty=5` |
| First cancel | `CancelOrder("O-1")` | `CANCELED O-1` |
| Repeated cancel | `CancelOrder("O-1")` | `ALREADY_CANCELED` |
| Add after cancel | `AddItems("O-1",1)` | `ORDER_CANCELED`; qty remains 5 |
| Overflow | `AddItems("MAX",1)` when qty is at max | `QUANTITY_OVERFLOW`; qty unchanged |
| Missing subtype in switch | `MissingCommandCase` example | Compiler must reject |
| Dominated case | `DominatedCommandCase` example | Compiler must reject |

The program in Section 9 executed **27 assertions against an independent oracle** and checked snapshots between operations. The PASS messages are only printed if all preceding assertions succeed.

### Additional Tests for Real Systems

1. **Contract tests:** input errors must map to the agreed API response/error codes.
2. **Persistence/transaction tests:** failed commands do not create records or leave invalid state changes.
3. **Concurrency tests:** two concurrent add-item commands do not lose an update.
4. **Retry/idempotency tests:** resending the same command ID does not apply side effects twice.
5. **Authorization tests:** unauthorized callers cannot create or cancel orders even with a type-valid command.
6. **Compatibility tests:** when adding a subtype or changing message schemas, older consumers have a clear handling strategy.
7. **Boundary tests:** `Integer.MAX_VALUE`, empty IDs, whitespace-only IDs, null values, records with invalid fields.

**Branch coverage** from JaCoCo can highlight unexecuted paths, but it does not prove logic correctness. Assert both results and state as in the table above; mutation testing can also be added to catch wrong guard operators (such as `delta <= 0` changed to `delta < 0`).

## 15. Common Pitfalls

1. **Switching on `Object` and manually casting in each branch.** When type/record patterns are available, declare commands via a `sealed interface` and use pattern variables instead of casts.
2. **Assuming `sealed` automatically validates command data.** `CreateOrder(null,0)` can still be created if the record does not enforce invariants; guards or constructors must handle it.
3. **Placing a broad case before a `when`-guarded case.** The broad case will shadow the specific case and cause a `dominated case` compile error.
4. **Adding `default -> "SUCCESS"` to satisfy exhaustiveness.** With a closed hierarchy, `default` can hide a new command without a handler; add the business case instead.
5. **Confusing a null selector with a null component.** `dispatch(null)` enters `case null`; `dispatch(new CreateOrder(null,2))` must enter the ID-checking guard.
6. **Calling `id.isBlank()` before checking for null.** `id==null || id.isBlank()` is safe; reversing the order can cause an NPE.
7. **Assuming `var` means dynamic typing.** `id` is inferred by the compiler as `String`, and `quantity` as `int` from the record.
8. **Putting all business logic into long case expressions.** The dispatcher should only contain branch selection and short conditions, keeping state updates in helpers/handlers.
9. **Not checking for overflow in quantity addition.** `int` can wrap around when exceeding its range; use `Math.addExact` or an appropriate numeric type.
10. **Retrying `AddItems` without an idempotency key.** Adding items has non-idempotent side effects; replay protection is needed at the business layer.
11. **Confusing commands with queries.** Viewing order state is not a write command; separate it into a dedicated read method/handler like `snapshot`.
12. **Assuming the demo map is thread-safe.** `LinkedHashMap` with a `get/put` sequence does not guarantee transactions or atomicity under concurrent updates.
13. **Treating compile-time exhaustiveness as a check for all bugs.** The compiler checks subtypes/cases, but not authorization, null fields inside records, or business policies.
14. **Running this lesson's pattern switch/record pattern code at Java 17 level.** These features became final in Java 21; use `--release 21` with an appropriate toolchain.

## 16. Practice Exercises

**Exercise 1.** If you add `record RestoreOrder(String orderId) implements Command {}`, what steps are needed to avoid breaking the `sealed` model?

*Answer:* Add `RestoreOrder` to `permits`, decide the invariants for the command, add a case in `switch` and a restore handler, and add state tests. If the new subtype is not handled yet, the compiler will report that the `switch` expression is not exhaustive.

**Exercise 2.** Why must the unguarded `case CreateOrder(var id, var quantity)` come after the two cases checking ID and quantity?

*Answer:* The unguarded case matches any non-null `CreateOrder`. If placed first, the two `when`-guarded cases after it are dominated. Place specialized guards first to validate data in the right order.

**Exercise 3.** Do `dispatch(null)` and `route(null)` return the same result?

*Answer:* No, according to the sample contract: `dispatch(null)` returns `INVALID_COMMAND` via `case null`, while `route(null)` returns `NOT_A_COMMAND` because `instanceof Command` fails. If the API requires a unified error code, change the policy at the boundary.

**Exercise 4.** Why is `AddItems("O-1",3)` not idempotent?

*Answer:* If the order is active and the command is executed twice, the quantity increases twice. Pattern switch does not prevent retries; a command ID/idempotency store and proper transactions are needed.

**Exercise 5.** Why is `Math.addExact` better than `previous.quantity() + delta` in this lesson?

*Answer:* It throws `ArithmeticException` on `int` overflow, allowing the handler to return `QUANTITY_OVERFLOW` and leave the state unchanged. Regular `int` addition can overflow and wrap to an invalid value.

**Exercise 6.** Can `record CancelOrder(String orderId) implements Command {}` contain `orderId == null`?

*Answer:* Yes, if the constructor does not validate it. The record pattern `CancelOrder(var id)` still matches that record; `invalidId(id)` must handle null safely.

**Exercise 7.** If the number of command types grows to hundreds and each handler needs many dependencies, what should you do?

*Answer:* You can keep the closed command model per module while delegating from `switch` to separate handlers/services, or use a handler registry with a mechanism to verify all handlers are registered. Evaluate modularity, extensibility rules, and missing-branch detection.

**Exercise 8.** After receiving `ORDER_CANCELED` from `AddItems`, what else should be asserted besides the response?

*Answer:* Read the order again (e.g., via `snapshot`) and verify that the status is still `CANCELED` and the quantity is unchanged. Testing side effects is just as important as testing result codes.

## 17. Official References

- [JEP 409 – Sealed Classes (Java 17)](https://openjdk.org/jeps/409)
- [JEP 395 – Records (Java 16)](https://openjdk.org/jeps/395)
- [JEP 394 – Pattern Matching for instanceof (Java 16)](https://openjdk.org/jeps/394)
- [JEP 440 – Record Patterns (Java 21)](https://openjdk.org/jeps/440)
- [JEP 441 – Pattern Matching for switch (Java 21)](https://openjdk.org/jeps/441)
- [Oracle Java 21 – Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Oracle Java 21 – Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Oracle Java 21 – Sealed Classes and Interfaces](https://docs.oracle.com/en/java/javase/21/language/sealed-classes-and-interfaces.html)
- [JLS Java 21 – Switch blocks, dominance/exhaustiveness](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1)
- [JLS Java 21 – Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
