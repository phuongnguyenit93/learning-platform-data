# Designing a Sealed Command Hierarchy in Java Pattern Matching

## 1. The Problem: From a Set of Business Commands to a Type-Safe Model

Suppose an order management application must accept four **commands**:

1. **PlaceOrder** — create an order with an order ID, customer ID, and amount.
2. **CancelOrder** — request cancellation of an existing order.
3. **PackOrder** — pack an order into a number of parcels.
4. **ShipOrder** — ship an order to a delivery address.

Each command carries **the intent to ask the system to do something**, not an assertion that the action has already succeeded. For example, receiving `ShipOrder("O-1", ...)` does not mean order `O-1` has already been shipped: the handler still must verify that the order is packed and eligible for the state transition.

An initial design might use a generic class containing an operation name and multiple optional fields:

```java
// Anti-pattern example of API design; not a standalone program.
record GenericCommand(
        String commandType,
        String orderId,
        String customerId,
        String reason,
        Integer parcelCount,
        String destinationCity) {}
```

This model permits meaningless states, such as a cancellation command that also has a `parcelCount`, a shipping command without an address, or a misspelled `commandType`. Handlers typically have to read strings and perform manual casts or null checks.

A **sealed command hierarchy** solves the structural part of the problem: declare an allowed set of command branches using `sealed`, represent each command's specific data using `record`, and use pattern matching to branch on **types known to the compiler**.

The goal is not to turn every business condition into a compiler rule. The compiler can guarantee that a subtype belongs to a valid hierarchy and enable exhaustiveness checking in `switch`, but it **cannot** know whether order `O-1` in the data store has already been packed. State rules, authorization, transactions, and idempotency still belong to business logic.

This article uses **Java 21+** to demonstrate record patterns, pattern `switch`, and `when` guards in full (JEP 440 and JEP 441). Sealed types and records themselves have been stable since Java 17.

## 2. Commands Differ from Events and Results

Three concepts are often placed close together but must not be conflated:

| Concept | Meaning | Illustrative Name | Timing |
| --- | --- | --- | --- |
| **Command** | A request to perform an action; may be rejected | `PlaceOrder`, `ShipOrder` | Before applying a change |
| **Domain event** | Something that has already happened in the domain | `OrderPlaced`, `OrderShipped` | After the change is accepted |
| **Command result** | Outcome returned to the command sender | `Accepted`, `Rejected` | After the handler processes it |

A method like `handle(Command)` should not be interpreted as "every command succeeds." If the order does not exist yet or is in an invalid state, the handler can return `Rejected`.

In this learning example, `Accepted` only indicates that **the in-memory handler accepted the operation**. It should not be interpreted as the order being durably persisted to a database, a message being delivered to a broker, or a distributed transaction being committed. In a real system, transaction boundaries and the meaning of results must be explicitly documented.

Naming also reflects intent:
- `PlaceOrder` is an active request (verb + noun).
- `OrderPlaced` describes an event that has already occurred (past tense).
- `Accepted`/`Rejected` describe processing outcomes, not subtypes of `Command`.

## 3. Designing a Sealed Hierarchy Tree with Subgroups

Instead of forcing all commands directly into a flat set, related commands can be grouped:

```text
Command (sealed interface)
├── PlaceOrder       (record; final)
├── CancelOrder      (record; final)
└── FulfillmentCommand (sealed interface)
    ├── PackOrder    (record; final)
    └── ShipOrder    (record; final)

CommandResult (sealed interface)
├── Accepted         (record; final)
└── Rejected         (record; final)

Address              (record used as a value object)
```

Intentional design decisions:

- `Command` allows only **three direct subtypes**: `PlaceOrder`, `CancelOrder`, and `FulfillmentCommand`.
- `FulfillmentCommand` is itself `sealed` and allows only **two direct subtypes**: `PackOrder` and `ShipOrder`.
- `PackOrder` and `ShipOrder` remain **indirect** subtypes of `Command`.
- Each concrete command is a `record`, which is implicitly `final`, so it cannot be extended in ways that introduce unanticipated subtypes.
- `CommandResult` is a **separate** sealed hierarchy from commands, allowing the handler to return two clearly typed outcomes.
- `Address` is a value object rather than a command: it describes data for the shipping command.

**Core syntax:**

```java
sealed interface Command
        permits PlaceOrder, CancelOrder, FulfillmentCommand {
    String orderId();
}

sealed interface FulfillmentCommand extends Command
        permits PackOrder, ShipOrder {}

record PlaceOrder(String orderId, String customerId, long amountInCents)
        implements Command {}

record CancelOrder(String orderId, String reason)
        implements Command {}

record PackOrder(String orderId, int parcelCount)
        implements FulfillmentCommand {}

record ShipOrder(String orderId, Address destination)
        implements FulfillmentCommand {}

record Address(String city, String countryCode) {}
```

This is a **structural snippet**, which can be placed inside an enclosing class along with supporting declarations. The complete program in Section 7 adds validation, the handler, and results.

To reduce duplication, the `Command` interface declares `orderId()`. Every command record has a `String` component named `orderId`, so the record-generated accessor satisfies the interface contract. If a command is not tied to a specific order, **do not force it into an interface requiring `orderId()`**; instead, redesign the shared contract or split out another command group.

## 4. Sealed Rules: `permits` Lists Only Direct Subtypes

One of the most important differences between a sealed hierarchy and an arbitrary inheritance diagram is that **the compiler enforces the set of direct children**.

In this example:

```java
sealed interface Command
        permits PlaceOrder, CancelOrder, FulfillmentCommand {}
```

This list **does not** contain `PackOrder` or `ShipOrder` because they directly implement `FulfillmentCommand`, not `Command`.

Direct subtypes of a sealed parent must declare their own inheritance policy:
- `final`: terminates the branch; records are implicitly `final`.
- `sealed`: allows further extension, but only through a new, controlled `permits` list.
- `non-sealed`: opens the branch so arbitrary subtypes can be added.

In this command model, `FulfillmentCommand` is declared `sealed` rather than `non-sealed` to **keep the system's command set closed and verifiable**. If `ReturnOrder`, `RefundOrder`, or `SchedulePickup` is needed later, the API owner must decide which group each belongs to and intentionally update the hierarchy.

**Declaration scope:** With named modules, direct permitted subclasses/interfaces must be in the same module as the sealed parent; with unnamed modules, they must be in the same package. An external plugin outside the module cannot arbitrarily `implements Command` directly if it is not in the permitted list. If a real system requires plugins to supply new commands, that is a signal to consider a `non-sealed` branch or a separate handler registry mechanism. Do not claim both "a closed exhaustive set" and "any client can directly add arbitrary commands."

### A Deep Tree Is Not Always Better

Only create an intermediate subtype like `FulfillmentCommand` if it carries domain meaning, shares a contract or policy, or is useful as a dispatch branch. For a very small project, four records directly in `Command permits ...` may be clearer. A sealed hierarchy should reflect **real variant boundaries**, not add extra layers just to look architectural.

## 5. Records for Command Data and Invariant Checks

`record` is a suitable choice for command data objects because:
- It provides clear components, constructor, and accessors.
- It generates `equals`, `hashCode`, and `toString` based on components, which is convenient for testing and controlled logging.
- It is `final`, preventing unintended subtypes.
- It pairs naturally with type patterns or record patterns to extract data.

However, `record` **does not automatically guarantee all data is valid**. For example:

```java
record PackOrder(String orderId, int parcelCount)
        implements FulfillmentCommand {}
```

The declaration above still allows `new PackOrder("", -3)`. You should add a **compact constructor** to enforce local invariants:

```java
record PackOrder(String orderId, int parcelCount)
        implements FulfillmentCommand {
    PackOrder {
        requireText(orderId, "orderId");
        if (parcelCount <= 0) {
            throw new IllegalArgumentException(
                    "parcelCount must be positive");
        }
    }
}
```

Here `requireText` is a helper method on the enclosing class in the full program. Placing validation **at command creation time** helps the handler avoid repetitive structural data checks.

Choose the appropriate validation level:

| Check Type | Example | Appropriate Place |
| --- | --- | --- |
| **Local invariants** | `orderId` non-blank, `parcelCount > 0`, `destination != null` | Command or value object constructor/factory |
| **State transition rules** | Only pack orders currently in `PLACED` | Handler/domain service with current state |
| **Permissions** | Is this user allowed to cancel this order? | Authorization layer/handler |
| **Cross-entity constraints** | Does the order exist? Is the address in a supported region? | Appropriate service/repository |
| **Concurrency consistency** | Two users packing/cancelling the same order simultaneously | Transaction/locking/optimistic concurrency control |

Do not query a database or make network calls **inside a record constructor** just to enforce every business rule. Command data objects should be cheap to construct and deterministic. On the other hand, if input is invalid, exception handling for constructor failures must happen at the appropriate request/API mapping layer, because the handler **has not even received the command** when the constructor throws.

### Avoid "Meaningful Names" Without Corresponding Checks

The name `amountInCents` helps prevent unit confusion, but it does not prevent negative numbers; the name `destination` does not verify that the country is deliverable. Contracts must be backed by concrete checks or clear input documentation.

### Records Are Shallowly Immutable

Record components are `final`, but if a record holds a `List` or mutable object, its internal contents can still be modified. For example, use immutable value objects or defensive copies when accepting collections. Do **not** assume every command is deeply immutable just because it is declared as a `record`.

## 6. Distinguishing Command Model, State Model, and Result Model

A sealed command hierarchy describes **the types of requests that can be received**. It is not necessarily the state model of the aggregate.

In this example:
- **Command:** `PlaceOrder`, `CancelOrder`, `PackOrder`, `ShipOrder`.
- **State:** `PLACED`, `PACKED`, `SHIPPED`, `CANCELLED`.
- **Result:** `Accepted` or `Rejected`.

A simple order state diagram:

```text
Not created yet
    │ PlaceOrder (valid)
    ▼
  PLACED ─── PackOrder ──► PACKED ─── ShipOrder ──► SHIPPED
    │                        │
    └──── CancelOrder ───────┘
             ▼
          CANCELLED
```

Rejection cases:
- `PackOrder` or `ShipOrder` when the order does not exist yet.
- `PlaceOrder` when the order ID already exists.
- `ShipOrder` when the order is not yet `PACKED`.
- `CancelOrder` when already `SHIPPED`.
- `PackOrder` when the order is already `CANCELLED`.
- Repeated `CancelOrder` when already `CANCELLED` (the example chooses to return `Rejected`, not auto-idempotent).

**The compiler does not know this state diagram.** It only checks that the `switch` handles every receivable subtype. Business correctness requires separate **state tests**, not just compiler exhaustiveness checks.

In particular, `PlaceOrder` is a "request to transition to PLACED," not the `PLACED` state itself. Sharing a single hierarchy for both requests and states often mixes up "what is being asked" with "what currently exists."

## 7. Complete Java 21 Program: Sealed Commands + Handler + Results

Save all the code below as **`SealedCommandHierarchyDemo.java`**. This example is a **single-file, standalone program** on JDK 21+, requiring no external frameworks. It stores state in a `HashMap` to focus on type modeling and dispatch, and is **not** intended as a production implementation with transactions or concurrency control.

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class SealedCommandHierarchyDemo {
    sealed interface Command
            permits PlaceOrder, CancelOrder, FulfillmentCommand {
        String orderId();
    }

    sealed interface FulfillmentCommand extends Command
            permits PackOrder, ShipOrder {}

    record PlaceOrder(String orderId, String customerId, long amountInCents)
            implements Command {
        PlaceOrder {
            requireText(orderId, "orderId");
            requireText(customerId, "customerId");
            if (amountInCents <= 0) {
                throw new IllegalArgumentException(
                        "amountInCents must be positive");
            }
        }
    }

    record CancelOrder(String orderId, String reason)
            implements Command {
        CancelOrder {
            requireText(orderId, "orderId");
            requireText(reason, "reason");
        }
    }

    record PackOrder(String orderId, int parcelCount)
            implements FulfillmentCommand {
        PackOrder {
            requireText(orderId, "orderId");
            if (parcelCount <= 0) {
                throw new IllegalArgumentException(
                        "parcelCount must be positive");
            }
        }
    }

    record Address(String city, String countryCode) {
        Address {
            requireText(city, "city");
            requireText(countryCode, "countryCode");
        }
    }

    record ShipOrder(String orderId, Address destination)
            implements FulfillmentCommand {
        ShipOrder {
            requireText(orderId, "orderId");
            Objects.requireNonNull(destination, "destination");
        }
    }

    sealed interface CommandResult permits Accepted, Rejected {}
    record Accepted(String message) implements CommandResult {}
    record Rejected(String reason) implements CommandResult {}

    enum Status { PLACED, PACKED, SHIPPED, CANCELLED }

    static final class OrderState {
        final String customerId;
        final long amountInCents;
        Status status = Status.PLACED;

        OrderState(String customerId, long amountInCents) {
            this.customerId = customerId;
            this.amountInCents = amountInCents;
        }
    }

    static String requireText(String value, String name) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    name + " must not be blank");
        }
        return value;
    }

    static final class Handler {
        private final Map<String, OrderState> orders = new HashMap<>();

        CommandResult handle(Command command) {
            Objects.requireNonNull(command, "command");

            return switch (command) {
                case PlaceOrder(
                        var orderId, var customerId, var amountInCents) -> {
                    if (orders.containsKey(orderId)) {
                        yield new Rejected("already-exists:" + orderId);
                    }
                    orders.put(orderId,
                            new OrderState(customerId, amountInCents));
                    yield new Accepted("placed:" + orderId);
                }

                case CancelOrder(var orderId, var reason) -> {
                    OrderState state = orders.get(orderId);
                    if (state == null) {
                        yield new Rejected("not-found:" + orderId);
                    }
                    if (state.status == Status.SHIPPED) {
                        yield new Rejected("already-shipped:" + orderId);
                    }
                    if (state.status == Status.CANCELLED) {
                        yield new Rejected("already-cancelled:" + orderId);
                    }

                    state.status = Status.CANCELLED;
                    yield new Accepted("cancelled:" + orderId);
                }

                case PackOrder(var orderId, var parcelCount) -> {
                    OrderState state = orders.get(orderId);
                    if (state == null) {
                        yield new Rejected("not-found:" + orderId);
                    }
                    if (state.status != Status.PLACED) {
                        yield new Rejected(
                                "not-placeable-for-pack:" + orderId);
                    }

                    state.status = Status.PACKED;
                    yield new Accepted(
                            "packed:" + orderId + ":parcels=" + parcelCount);
                }

                case ShipOrder(var orderId, var destination) -> {
                    OrderState state = orders.get(orderId);
                    if (state == null) {
                        yield new Rejected("not-found:" + orderId);
                    }
                    if (state.status != Status.PACKED) {
                        yield new Rejected("not-packed:" + orderId);
                    }

                    state.status = Status.SHIPPED;
                    yield new Accepted("shipped:" + orderId + ":to="
                            + destination.city() + "/"
                            + destination.countryCode());
                }
            };
        }
    }

    static String show(CommandResult result) {
        return switch (result) {
            case Accepted(var message) -> "OK " + message;
            case Rejected(var reason) -> "ERR " + reason;
        };
    }

    // Pattern matching on direct branches: grouping fulfillment types.
    static String category(Command command) {
        return switch (command) {
            case PlaceOrder placed -> "order";
            case CancelOrder cancelled -> "order";
            case FulfillmentCommand fulfillment -> "fulfillment";
        };
    }

    // Guarded pattern to classify high-value PlaceOrder commands.
    static String priority(Command command) {
        return switch (command) {
            case PlaceOrder(var orderId, var customerId, var cents)
                    when cents >= 100_000 -> "high-value";
            case PlaceOrder(var orderId, var customerId, var cents) ->
                    "standard";
            case CancelOrder cancelled -> "cancellation";
            case FulfillmentCommand fulfillment -> "fulfillment";
        };
    }

    // Nested record pattern: ShipOrder -> Address.
    static String preview(Command command) {
        return switch (command) {
            case PlaceOrder(var id, var customerId, var cents) ->
                    "place:" + id;
            case CancelOrder(var id, var reason) ->
                    "cancel:" + id;
            case PackOrder(var id, var count) ->
                    "pack:" + id;
            case ShipOrder(var id, Address(var city, var country)) ->
                    "ship:" + id + ":" + city + "/" + country;
            case ShipOrder(var id, var destination) ->
                    "ship-missing:" + id;
        };
    }

    static void run(Handler handler, Command command) {
        System.out.println(show(handler.handle(command)));
    }

    public static void main(String[] args) {
        Handler h = new Handler();

        run(h, new PackOrder("O-1", 2));
        run(h, new PlaceOrder("O-1", "C-1", 150_000));
        run(h, new PlaceOrder("O-1", "C-1", 150_000));
        run(h, new ShipOrder("O-1", new Address("Hue", "VN")));
        run(h, new PackOrder("O-1", 2));
        run(h, new ShipOrder("O-1", new Address("Hue", "VN")));
        run(h, new CancelOrder("O-1", "customer-request"));
        run(h, new PlaceOrder("O-2", "C-2", 5_000));
        run(h, new CancelOrder("O-2", "customer-request"));
        run(h, new PackOrder("O-2", 1));

        System.out.println("category="
                + category(new PackOrder("O-3", 1)));
        System.out.println("priority="
                + priority(new PlaceOrder("O-3", "C-3", 120_000)));
        System.out.println("preview="
                + preview(new ShipOrder(
                        "O-4", new Address("Da Nang", "VN"))));

        try {
            new PlaceOrder("", "C-1", 1_000);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }

        try {
            h.handle(null);
        } catch (NullPointerException ex) {
            System.out.println("null=" + ex.getMessage());
        }
    }
}
```

Compile and run:

```bash
javac --release 21 -encoding UTF-8 SealedCommandHierarchyDemo.java
java SealedCommandHierarchyDemo
```

**Exact output:**

```text
ERR not-found:O-1
OK placed:O-1
ERR already-exists:O-1
ERR not-packed:O-1
OK packed:O-1:parcels=2
OK shipped:O-1:to=Hue/VN
ERR already-shipped:O-1
OK placed:O-2
OK cancelled:O-2
ERR not-placeable-for-pack:O-2
category=fulfillment
priority=high-value
preview=ship:O-4:Da Nang/VN
invalid=orderId must not be blank
null=command
```

The program was verified in a compiler environment using `--release=21`, and the stdout lines above match the execution output. No file, database, or network operations are performed by this example; it is an in-memory model for learning the mechanics.

## 8. Explaining the Handler: Compiler Checks Types, Domain Checks State

### 8.1. Why Use a `switch` Expression Returning `CommandResult`?

The handler returns one of two types: `Accepted` or `Rejected`. In each branch, the result is a **value actually consumed by the caller**, so `return switch (command)` expresses the contract clearly:

```java
CommandResult handle(Command command) {
    Objects.requireNonNull(command, "command");

    return switch (command) {
        case PlaceOrder(var orderId, var customerId, var amountInCents) -> {
            // Read/access domain state...
            yield new Accepted("placed:" + orderId);
        }
        // Remaining cases must be covered.
    };
}
```

This is an **abbreviated illustrative snippet**, not a standalone exhaustive switch expression; see the full method in Section 7. `yield` produces the value from a multi-statement `case` block, while the outer `return` returns the method's result.

If a handler primarily orchestrates side effects and returns `void`, a `switch` statement with case blocks, handler methods, and early `return;` may be clearer. Do not force switch expressions on every command handler.

### 8.2. When the Order Does Not Exist, the Domain Result Is `Rejected`

`PackOrder("O-1", 2)` is sent before `PlaceOrder`, so the handler returns `Rejected("not-found:O-1")`. This is **not** a syntax error or pattern mismatch: the `PackOrder` type is recognized by the compiler, but the state does not yet allow processing.

### 8.3. When the Order Already Exists, Duplicate Creation Is Rejected

After the first creation succeeds, a `PlaceOrder` with the same order ID is rejected with `already-exists:O-1`. This is a simplified example policy, **not** a production idempotency mechanism. In distributed systems, a command may need an `idempotencyKey` and result persistence keyed by it so retries do not repeat side effects.

### 8.4. Shipping Requires the `PACKED` State

`ShipOrder` before `PackOrder` returns `not-packed:O-1`. After `PackOrder`, the state becomes `PACKED`, and `ShipOrder` can then transition it to `SHIPPED`.

### 8.5. Cancellation Must Check the Current State

The handler allows cancelling `PLACED` or `PACKED` orders but rejects cancelling `SHIPPED` orders. `CancelOrder.reason` is validated to be non-blank; the fact that the handler does not store the reason in state in this example is merely a simulation simplification. Real systems must decide where to store cancellation reasons (aggregate state, audit log, or event) and make that contract explicit.

### 8.6. Success/Failure Outcomes Are Typed

`show` uses a pattern `switch` over `CommandResult`. There are only `Accepted` and `Rejected`, so there is no need for manual casting or relying on a string flag like `"SUCCESS"`. When a new `CommandResult` subtype is added, exhaustive switches are a point where the compiler can prompt you to review handling.

## 9. Exhaustiveness Across Multi-Level Sealed Hierarchies

Every command belongs to one of the four concrete records, so in `handle` the program can enumerate:

```java
return switch (command) {
    case PlaceOrder(var id, var customerId, var cents) -> {
        yield /* appropriate CommandResult */;
    }
    case CancelOrder(var id, var reason) -> {
        yield /* appropriate CommandResult */;
    }
    case PackOrder(var id, var count) -> {
        yield /* appropriate CommandResult */;
    }
    case ShipOrder(var id, var destination) -> {
        yield /* appropriate CommandResult */;
    }
};
```

**Note:** this is a **structural illustration**, where `/* ... */` is not a complete Java expression; do not compile it on its own. Runnable code is in Section 7.

The compiler knows `Command` has three direct branches, of which `FulfillmentCommand` has exactly two child records. Therefore, listing `PlaceOrder`, `CancelOrder`, `PackOrder`, and `ShipOrder` suffices to cover the current hierarchy.

**Group-level** handling is even shorter:

```java
static String group(Command command) {
    return switch (command) {
        case PlaceOrder placed -> "commercial";
        case CancelOrder cancelled -> "commercial";
        case FulfillmentCommand fulfillment -> "fulfillment";
    };
}
```

This is an illustrative method in the context of the declared types; grouping by `FulfillmentCommand` allows a single `case` to cover both `PackOrder` and `ShipOrder`. **You cannot place a broader parent-type case before a specific child-type case** if doing so causes the child case to be dominated.

### What Happens When a New Command Is Added?

Suppose we add:

```java
record ReturnOrder(String orderId) implements FulfillmentCommand {}
```

For this declaration to be valid, `FulfillmentCommand permits PackOrder, ShipOrder, ReturnOrder` must be updated (or the corresponding subtype set inferred by the compiler under valid structure rules). Then:

- A `switch` in a handler listing **only `PackOrder` and `ShipOrder`** will miss the new subtype and can be rejected by the compiler upon **recompilation**.
- A `switch` that already has `case FulfillmentCommand fulfillment` still handles the new type via the general branch, though whether that logic is business-correct for `ReturnOrder` must be verified separately.
- Tests, serialization schemas, API documentation, and versioning must all be reviewed.

A key strength of sealed hierarchies is **forcing command-set changes to become explicit decisions**, rather than silently accepting a new `commandType` string at runtime.

### Do Not Add `default` Mechanically

A `default -> new Rejected("unsupported")` in a switch that handles all commands can forfeit the compiler's reminder when a new command is added. For an intentionally closed sealed command set, listing cases explicitly is usually more valuable. If the API has a `non-sealed` branch for plugins, you must design a meaningful fallback for that open branch.

## 10. Nested Record Patterns: Choosing the Right Depth

`ShipOrder` contains an `Address` record. If you only need the address as a value object, a shallow pattern is sufficient:

```java
case ShipOrder(var orderId, var destination) -> {
    // Can use destination.city(), destination.countryCode().
}
```

If you need to extract components to format labels or match deeply:

```java
case ShipOrder(var orderId, Address(var city, var countryCode)) ->
        "ship:" + orderId + ":" + city + "/" + countryCode;
```

These two snippets are **illustrative branches**, not complete switches. The nested pattern `Address(...)` only matches when the `destination` component is a **non-null** `Address` instance.

In the program, the `ShipOrder` constructor uses `Objects.requireNonNull(destination, "destination")`, so an instance created via the valid constructor will not have `destination == null`. Even so, **the compiler does not rely on constructor logic to prove that a nested pattern covers the entire `ShipOrder` subtype**. That is why `preview` includes an additional branch:

```java
case ShipOrder(var id, var destination) ->
        "ship-missing:" + id;
```

This branch expresses the remaining structural case of the `ShipOrder` pattern, even though normal constructor invariants prevent such input from being created through the standard API.

**Do not** assume `case ShipOrder(var id, Address(...))` always covers all of `ShipOrder` simply because the current constructor forbids null. The compiler's pattern matching analysis is based on **types and pattern totality**, not on verifying that business validation code ran under a particular history.

Furthermore, if `Address` had a custom accessor that threw an exception during record pattern deconstruction, matching would throw `MatchException` wrapping the original cause rather than falling through like an ordinary non-matching pattern. To keep commands predictable, use stable value objects with side-effect-free accessors.

## 11. The `when` Guard: Use in the Right Place and Always Have a Fallback

The `priority` method in the demo program:

```java
static String priority(Command command) {
    return switch (command) {
        case PlaceOrder(var orderId, var customerId, var cents)
                when cents >= 100_000 -> "high-value";

        case PlaceOrder(var orderId, var customerId, var cents) ->
                "standard";

        case CancelOrder cancelled -> "cancellation";
        case FulfillmentCommand fulfillment -> "fulfillment";
    };
}
```

There are two `PlaceOrder` cases:
1. A specialized guarded case for large amounts.
2. A general unguarded case for the remaining place-order commands.

**Why is the second case needed?** The guard only matches when `cents >= 100_000`. For valid place-order commands with smaller amounts, Java needs a remaining path so the `switch` remains exhaustive. Placing the general case **before** the guarded case is the wrong order because it can shadow (*dominate*) the narrower case.

Naming the variable `cents` makes it obvious which unit is stored in the command; in a full API, `amountInCents` may be preferable if multiple monetary calculations occur. **A classification guard** (`high-value`) does not mean the command is accepted; the handler still needs to check state or permissions.

If a guard performs data lookups, service calls, or state mutations, matching behavior becomes harder to predict. For complex business rules, handle them after the case matches inside the handler or domain service rather than stuffing all logic into `when`.

## 12. Choosing Domain Names and Preserving Context

Pattern variables in a command handler should reveal **roles**, not just data types:

| Avoid | Prefer | Reason |
| --- | --- | --- |
| `id` when multiple IDs exist | `orderId`, `customerId` | Avoid confusing order with customer |
| `n` in `PackOrder` | `parcelCount` | Clarifies parcel count |
| `price` when storing cents | `amountInCents` | Prevents currency-unit bugs |
| `addr` in `ShipOrder` | `destination` or `shippingAddress` | Distinguishes shipping destination from billing address |
| `reason` when ambiguous across branches | `cancellationReason` when needed | Clarifies the command/action |
| `cmd1`, `cmd2` | `placeCommand`, `cancelCommand` | Expresses variable intent |

Inside a case whose type is already clearly `CancelOrder`, a concise `reason` can still be enough. There is no need for overly verbose names like `cancelOrderCancellationReasonValue`. What matters is traceability: which component is bound, whether it shares a type with another component, and which business rule uses that value.

**Record patterns match by component position**, not by variable name. If two components are both `String`, accidentally swapping their positions may still compile while changing the meaning. That is why output tests and model reviews matter more than just seeing a green compile.

## 13. Null Policy and Invalid Inputs

There are at least three places where `null` can appear in this case study:

1. **`Command command == null`**: no request was provided.
2. **A required component is null**: such as `new ShipOrder("O-1", null)`.
3. **Missing state data**: `orders.get(orderId) == null`.

These are **three distinct situations**.

### Null Command

`Handler.handle` calls:

```java
Objects.requireNonNull(command, "command");
```

This establishes a contract: the handler does not accept a null command; the failure is a `NullPointerException` with the message `"command"`. If you want the API to return `Rejected("missing-command")` instead of throwing an exception, that is a different design choice. You can write `case null` in Java 21, but do not add it just to undermine the original contract.

An exhaustive `switch` over a sealed type **does not** automatically mean null-safe selector handling. Without `case null`, switching on a null reference normally throws NPE.

### Null Component

`ShipOrder` requires `destination`; its constructor throws NPE when that component is null. `PlaceOrder`, `CancelOrder`, and `PackOrder` check for non-blank strings and positive numbers with `IllegalArgumentException`. These errors occur **at command construction time**, before the handler dispatches.

### State Not Found

When the order does not exist in the `Map`, this is neither a null command nor a command-construction error. The handler returns `Rejected("not-found:" + orderId)`. This maintains a clean boundary between **invalid command shape** and **business rejection**.

At the HTTP/API layer, you can map error categories to appropriate HTTP statuses, but that is an adapter decision. Do not directly assume "`Rejected` is always HTTP 400" or "`IllegalArgumentException` is always HTTP 500."

## 14. Evolving from the In-Memory Example to a Layered Architecture

The example uses a single `Handler` holding a `Map<String, OrderState>` to demonstrate the technique. A real system might separate layers:

```text
HTTP / CLI / Message Adapter
          │ parse + authenticate
          ▼
Command Factory / Validation
          │ PlaceOrder | CancelOrder | ...
          ▼
Command Handler / Application Service
          │ authorize + load aggregate
          ▼
Domain State / Domain Service
          │ validate state transition
          ▼
Repository / Transaction Boundary
          │ persist or rollback
          ▼
CommandResult + Domain Events
          │ return response / publish reliable events
          ▼
Caller / Outbox / Event Consumers
```

Separating responsibilities does not require turning every box in the diagram into its own class. What matters is:

- **Command** represents request data, holding no repositories or stateful services.
- **Handler** performs dispatch and applies permissions/orchestration.
- **Domain model** decides the validity of state transitions.
- **Repository/transaction** is responsible for persistence consistency.
- **CommandResult** presents acceptance/rejection in semantics the caller uses.
- **Domain event** describes what happened and is published only under a strategy consistent with the transaction.

A large `switch` in a handler can be split into dedicated methods:

```java
// Illustrative snippet: the methods below are dedicated handlers.
return switch (command) {
    case PlaceOrder placed -> placeHandler.handle(placed);
    case CancelOrder cancelled -> cancelHandler.handle(cancelled);
    case PackOrder packed -> packHandler.handle(packed);
    case ShipOrder shipped -> shipHandler.handle(shipped);
};
```

This still leverages compiler exhaustiveness while keeping the application logic for each command in its own handler. There is no need to deconstruct every component right at the `switch` if passing the whole `placed` value object downstream is cleaner.

## 15. Testing the Hierarchy: Compile-Time and Behavior Are Two Separate Layers

### 15.1. Minimum Regression Matrix

| Input or Operation | Expected | What It Proves |
| --- | --- | --- |
| `PackOrder("O-1",2)` before order exists | `Rejected("not-found:O-1")` | Handler checks existence |
| First `PlaceOrder("O-1",...)` | `Accepted("placed:O-1")` | Order creation |
| Duplicate ID `PlaceOrder` | `Rejected("already-exists:O-1")` | Prevents duplicate creation |
| `ShipOrder` before `PackOrder` | `Rejected("not-packed:O-1")` | State precondition |
| `PackOrder` after `PlaceOrder` | `Accepted("packed:O-1:parcels=2")` | Transition `PLACED` → `PACKED` |
| `ShipOrder` after `PackOrder` | `Accepted("shipped:O-1:to=Hue/VN")` | Transition `PACKED` → `SHIPPED` |
| `CancelOrder` after `SHIPPED` | `Rejected("already-shipped:O-1")` | Forbids late cancellation |
| `CancelOrder` in `PLACED` | `Accepted("cancelled:O-2")` | Allows valid cancellation |
| `PackOrder` in `CANCELLED` | `Rejected("not-placeable-for-pack:O-2")` | Cancelled state is terminal |
| `new PlaceOrder("",...)` | `IllegalArgumentException` | Constructor invariant |
| `handler.handle(null)` | `NullPointerException` | Null contract |
| `category(new PackOrder(...))` | `"fulfillment"` | Intermediate sealed branch |
| `preview(new ShipOrder(...))` | `"ship:O-4:Da Nang/VN"` | Nested record pattern |
| `priority(new PlaceOrder(...,120_000))` | `"high-value"` | `when` guard |

This is **behavior** testing: correct values and correct states. Compile-time checking answers a different question: "Does every command subtype have a handling branch?"

### 15.2. JUnit 5 Using Record Equality

Because `Accepted` and `Rejected` are records, tests can assert typed outcomes directly instead of just printed strings:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class SealedCommandHierarchyTest {
    @Test
    void cannotPackAnOrderBeforeItExists() {
        var handler = new SealedCommandHierarchyDemo.Handler();
        var result = handler.handle(
                new SealedCommandHierarchyDemo.PackOrder("O-1", 2));

        assertEquals(
                new SealedCommandHierarchyDemo.Rejected("not-found:O-1"),
                result);
    }

    @Test
    void placeThenPackThenShip() {
        var handler = new SealedCommandHierarchyDemo.Handler();

        assertEquals(
                new SealedCommandHierarchyDemo.Accepted("placed:O-1"),
                handler.handle(
                        new SealedCommandHierarchyDemo.PlaceOrder(
                                "O-1", "C-1", 15_000)));

        assertEquals(
                new SealedCommandHierarchyDemo.Accepted(
                        "packed:O-1:parcels=1"),
                handler.handle(
                        new SealedCommandHierarchyDemo.PackOrder("O-1", 1)));

        assertEquals(
                new SealedCommandHierarchyDemo.Accepted(
                        "shipped:O-1:to=Hue/VN"),
                handler.handle(
                        new SealedCommandHierarchyDemo.ShipOrder(
                                "O-1",
                                new SealedCommandHierarchyDemo.Address(
                                        "Hue", "VN"))));
    }

    @Test
    void rejectInvalidShapesAndNullCommand() {
        assertThrows(IllegalArgumentException.class,
                () -> new SealedCommandHierarchyDemo.PlaceOrder(
                        "", "C-1", 1_000));
        assertThrows(NullPointerException.class,
                () -> new SealedCommandHierarchyDemo.Handler().handle(null));
    }
}
```

This is **illustrative JUnit 5 test code**, not a JDK-only standalone file. You need JUnit 5 on the classpath and must place the test in the same package as `SealedCommandHierarchyDemo` (nested types/methods in the example are package-private). In a real project, expose a public API or organize modules/packages intentionally.

### 15.3. Testing Missing-Case Errors at Compile Time

The following Java 21 snippet **intentionally fails to compile**:

```java
sealed interface SmallCommand permits OpenCommand, CloseCommand {}
record OpenCommand(String id) implements SmallCommand {}
record CloseCommand(String id) implements SmallCommand {}

class BadSwitch {
    static String classify(SmallCommand command) {
        return switch (command) {
            case OpenCommand c -> "open";
        };
    }
}
```

The compiler reports an error along the lines of:

```text
the switch expression does not cover all possible input values
```

This is a **compiler exhaustiveness test**, not a runtime unit test. Once you add the `CloseCommand` case (or another valid covering branch), the code compiles. Conversely, a successful compile does not verify that order state is updated properly; that is why the regression tests above are still required.

## 16. Production Concerns That a Sealed Hierarchy Does Not Solve Automatically

### 16.1. Concurrency and Transactions

The `HashMap` in the example is **not thread-safe**; two concurrent requests could both read `PLACED` or both see the order as non-existent. `OrderState.status` being a mutable field also requires protection against concurrent access.

In a real system, consider database transactions, optimistic locking via a `version` column, unique constraints on `orderId`, or serializing commands per aggregate. Do not treat `sealed` as a concurrency primitive.

### 16.2. Idempotency and Retries

A request may be retried due to a timeout. If `PlaceOrder` succeeded but the response was lost, a retry could encounter `already-exists`. That outcome is **different** from returning the original success of an idempotent operation.

To achieve idempotency, you must define an idempotency key, scope/TTL, result storage, and retry semantics—not rely merely on record `equals`.

### 16.3. Authorization

Constructing a valid `CancelOrder("O-1", "...")` at the constructor does not prove the caller has permission to cancel `O-1`. The application layer must verify identity/permissions and not trust client-supplied claims blindly. A sealed hierarchy restricts **command types**, not **who can send them**.

### 16.4. Serialization and Out-of-Process Inputs

JSON and message brokers do not natively understand `permits` the way the Java compiler does. You must configure type discriminators, schema versions, and safe mapping from payloads to command objects. Do not enable unrestricted polymorphic deserialization for arbitrary class names supplied by clients.

### 16.5. Error Handling and Transactions

`Rejected` is an expected business outcome; database exceptions, network errors, or programming bugs may require separate error-handling mechanisms. Do not catch all exceptions into `Rejected("error")` and act as if the transaction cleanly completed. Likewise, do not publish an `OrderShipped` event before durable state persistence is guaranteed by your design.

### 16.6. Observability and Sensitive Data

Records generate `toString()` from their components. Do not log raw commands containing customer data, addresses, tokens, or sensitive content without redaction. Consider structured logs containing only command type, correlation ID, and approved fields.

## 17. Choosing Between a Closed Command Set and Open Plugin Extensions

There are two distinct architectural goals:

**Closed command set:** the application owner controls all commands, and every change goes through an application release. `sealed` with `final` record leaves and `sealed` intermediate branches is a good fit: the compiler can help check every case.

**Open plugin system:** external partners or other teams add new commands that the core module does not know about at compile time. An extensible interface or handler registry may be more suitable. If a branch is `non-sealed`, pattern switches must have a handling path for unknown subtypes—there is no longer a guarantee that only the current concrete records exist.

This decision should be documented clearly in JavaDoc/API docs:
- Which direct subtypes are permitted?
- Which subtypes are closed, and which remain sealed?
- Are there extension points outside the module?
- When a new command is added, must clients update code or migrate?
- Will a handler that does not recognize a new variant return an error, delegate to a plugin dispatcher, or reject it at parse time?

**No single structure is always optimal.** A sealed hierarchy provides high value when the domain has a bounded set of variants and the application owner wants the compiler to catch missing branches. It is poorly suited if a core feature is allowing external parties to declare new command types freely without re-releasing core code.

## 18. Java Compatibility and API Evolution

### 18.1. Java 17 Supports Sealed Types and Records, but Not Finalized Record Patterns

You can write a Java 17-compatible version using `instanceof` type patterns:

```java
static String describeJava17(
        SealedCommandHierarchyDemo.Command command) {
    if (command instanceof SealedCommandHierarchyDemo.PlaceOrder placed) {
        return "place:" + placed.orderId();
    }
    if (command instanceof SealedCommandHierarchyDemo.CancelOrder cancelled) {
        return "cancel:" + cancelled.orderId();
    }
    if (command instanceof SealedCommandHierarchyDemo.PackOrder packed) {
        return "pack:" + packed.orderId();
    }
    if (command instanceof SealedCommandHierarchyDemo.ShipOrder shipped) {
        return "ship:" + shipped.orderId();
    }
    throw new IllegalArgumentException("unsupported command");
}
```

This is an **illustrative snippet** using types from the program in the same package. The `instanceof Type name` syntax is valid in Java 17; however, **the full program in Section 7 requires Java 21** because it uses pattern `switch` and record patterns. If you actually ship a Java 17 artifact, the entire module must use only Java 17 features and compile with `javac --release 17`.

### 18.2. Adding a Subtype Is an API Contract Change

When `RefundOrder` or `ReturnOrder` is added to the sealed set, **recompiling clients** may fail with missing-case errors in exhaustive switches. That is a safety benefit during development, but it is also a breaking impact that must be communicated.

Under **separate compilation** (client code compiled against an older hierarchy but running against a newer library), an already-compiled exhaustive switch can encounter an unanticipated new subtype and throw `MatchException` at runtime. Do not promise binary compatibility solely because the new library compiles cleanly; test against supported client versions.

### 18.3. Versioned Command Schemas

If commands are stored in queues or databases for replay months later, removing or renaming a subtype can make historical data unreadable. You need a strategy for versioning, schema migration, and message compatibility independent of Java's `sealed` feature.

## 19. Anti-Patterns in Command Hierarchy Design

### 19.1. Dispatching on Strings Instead of Types

`if ("SHIP".equals(command.type())) ...` is typo-prone and forces a generic object to carry many optional fields. Sealed records are usually clearer for a closed command set. On the wire, however, you still need a message type; map the discriminator safely to a typed command in the adapter.

### 19.2. Creating One Giant Record for Every Command

A `GenericCommand` with `orderId`, `amount`, `reason`, `parcelCount`, and `address`—where each operation uses only a subset—creates many meaningless data combinations. Splitting records per specific request reduces handler complexity.

### 19.3. Using `non-sealed` When You Actually Want a Closed Set

If all implementations are known internally and the business wants the compiler to flag newly added commands, unnecessarily opening a `non-sealed` branch weakens the closed hierarchy. Only open it when there is a genuine extension use case.

### 19.4. Using `default` to Ignore New Subtypes

A `default -> new Rejected("unsupported")` can hide the fact that a handler was not updated when a direct subtype was added. With a closed sealed hierarchy, letting exhaustive `switch` flag missing cases is an advantage.

### 19.5. Mixing Commands with Events

`ShipOrder` is a request; `OrderShipped` is an event that already happened. Putting both under one sealed root often blurs timing and validation boundaries. Keep hierarchies separated by role.

### 19.6. Using Pattern Guards for Every Business Condition

`when` is well suited for local, pure, readable branching. Calling databases, checking permissions, or mutating state inside a guard makes matching unpredictable. Move those into the handler or domain service.

### 19.7. Assuming `sealed`/`record` Guarantees Authorization and Concurrency

The compiler checks types; transactions, idempotency, and access control require separate checks. A structurally valid command can still be rejected by state or security policy.

### 19.8. Using Inheritance for Commands Without a Shared Contract

If a command has no `orderId()` but is forced to carry a dummy field just to implement `Command`, that is a sign of a flawed abstraction. Revisit the root contract or split bounded contexts.

### 19.9. Over-Deconstructing Records at the Dispatch Layer

`case ShipOrder(var id, Address(var city, var code))` is useful when the handler actually uses those fields. If the handler simply delegates to a dedicated service, `case ShipOrder ship -> shipHandler.handle(ship)` often preserves context better and avoids coupling dispatch logic to every component.

### 19.10. Relying Solely on Branch Coverage

Tests that exercise all four subtypes do not guarantee that rejection states, duplicate requests, nulls, concurrency, or invalid domain inputs are tested. Testing must cover the **command × state × validation matrix**, not just switch branch counts.

## 20. Design and Review Checklist

| Question | Good Sign |
| --- | --- |
| Does the command represent intent or an event that already occurred? | Verb naming and clear request semantics |
| Is the command set closed or open to plugin extensions? | Intentional choice of `sealed`/`non-sealed` |
| What are the direct permitted subtypes? | `permits` accurately lists direct relationships |
| Is there a domain-meaningful intermediate command group? | `FulfillmentCommand` shares role/contract |
| Does each command have its own complete and accurate data? | Clear record components, few optional fields |
| What does the constructor validate? | Local invariants; not confused with database state |
| Where do payload validation and authorization live? | Before/at the handler with clear boundaries |
| Is the result model typed? | `Accepted`/`Rejected` or equivalent variants |
| Is the handler exhaustive? | Every command type handled via pattern `switch` |
| Is a broad case placed before a narrow case? | No dominance issues; guards have fallbacks |
| Is there a clear policy for null selectors and components? | Asserted exception or explicit null branch per contract |
| Are valid state transitions defined? | State diagram and unit tests exist |
| Are retries and idempotency addressed? | Strategy for result storage / deduplication keys |
| Are concurrency and transactions protected? | Not relying on the sample `HashMap` as production |
| What is the impact of adding a new command? | Compile tests, migration, versioning, docs |
| Is it tested on the target Java release? | JDK 21+ for finalized pattern switch; Java 17 if using alternatives |

## 21. Exercises and Answers

**Exercise 1 — Direct subtype.** In `Command permits PlaceOrder, CancelOrder, FulfillmentCommand`, is `PackOrder` a direct subtype of `Command`?

**Answer:** No. `PackOrder` directly implements `FulfillmentCommand`, so it is an indirect subtype of `Command`. The direct permitted subtype set of `Command` contains only the three listed types.

**Exercise 2 — Why use `sealed` for `FulfillmentCommand`?** Compare it with `non-sealed`.

**Answer:** `sealed` restricts fulfillment commands to the declared list and supports exhaustive dispatch. `non-sealed` allows other implementations to appear without being added to that branch's `permits` list, which is useful for plugins but leaves the concrete type set open.

**Exercise 3 — Records do not automatically enforce business rules.** Does `record PackOrder(String orderId, int parcelCount)` automatically forbid `parcelCount == -2`?

**Answer:** No. A compact constructor or factory is needed to check for positive numbers or appropriate rules.

**Exercise 4 — Compile-time vs. domain validation.** Why is `PackOrder("O-1", 2)` validly typed yet returns `not-found`?

**Answer:** The compiler guarantees the command belongs to the hierarchy and its record data has the right types, but the handler must check whether order `O-1` exists in the state repository.

**Exercise 5 — State.** Order `O-1` is currently `PLACED`. Why is `ShipOrder` rejected before `PackOrder`?

**Answer:** The domain state diagram requires `PACKED` before `SHIPPED`; this is unrelated to whether `ShipOrder` belongs to the sealed hierarchy.

**Exercise 6 — Result model.** Why use `CommandResult` with `Accepted`/`Rejected` instead of just returning `boolean`?

**Answer:** A typed result model expresses accepted and rejected branches, carries messages/metadata, and enables pattern matching when the caller handles the outcome. A `boolean` gives no failure reason and can invite semantic ambiguity.

**Exercise 7 — Guards.** Why is `case PlaceOrder(...) when cents >= 100_000` insufficient to handle all `PlaceOrder` commands?

**Answer:** Valid orders with amounts below the guard threshold still need another branch; otherwise, an exhaustive switch may lack a handling path.

**Exercise 8 — Nested record patterns.** Does `case ShipOrder(var id, Address(var city, var code))` guarantee coverage of all `ShipOrder` instances if the current constructor forbids a null destination?

**Answer:** The compiler does not prove constructor invariants to treat a nested pattern as total over all values of type `ShipOrder`. Add `case ShipOrder(var id, var destination)` as a structural fallback when exhaustiveness requires it.

**Exercise 9 — Null.** Does `Handler.handle(null)` in the example return `Rejected` or throw an exception?

**Answer:** It throws `NullPointerException` with message `command` because `Objects.requireNonNull` is called before the `switch`. This is the contract chosen in the example and can be replaced by another design if the API requires it.

**Exercise 10 — Adding a command.** When adding `ReturnOrder` to `FulfillmentCommand permits`, why must `handle` be reviewed?

**Answer:** A `switch` listing the four old records may no longer be exhaustive upon recompilation. The compiler will point out the need to handle the new subtype; the domain handler and tests must define the concrete policy for return orders.

**Exercise 11 — Preserving state.** With the in-memory handler, if two threads concurrently execute `PlaceOrder` with the same ID, is only one guaranteed to succeed?

**Answer:** No. `HashMap` and the check-then-write sequence are not safe under concurrency. A real system needs unique constraints/transactions or appropriate synchronization.

**Exercise 12 — Command or event?** After the handler successfully processes `ShipOrder`, what kind of message is `OrderShipped` (if emitted)?

**Answer:** It is a domain event describing something that has happened, not a request command. Event publication must be kept consistent with the transaction.

**Exercise 13 — Java versions.** From which Java version are sealed interfaces and record classes officially available? What about pattern `switch` and record patterns in `handle`?

**Answer:** Sealed types stabilized in Java 17; records stabilized in Java 16. Pattern matching for `switch` and record patterns became final in Java 21. The complete example requires `--release 21`.

**Exercise 14 — Sign of flawed design.** A `RefreshCatalog` command has no `orderId`, yet `orderId = ""` is added just so it can implement the `Command` interface. What should be done?

**Answer:** Revisit the `Command` contract and bounded context—consider splitting the hierarchy or creating a root that does not force every command to have `orderId()`. Do not add dummy data just to satisfy an interface.

## 22. Summary

Good sealed command hierarchy design relies on **a clear, bounded set of commands**, each with a **record data model** and local validation, a handler using **exhaustive pattern `switch`** for dispatch, and a domain layer responsible for state and business rules.

Key takeaways:

- `permits` specifies **direct** subtypes. Multi-level structures help group commands, but direct/indirect relationships must remain accurate.
- `record` creates value-like command data; it does not replace validation, authorization, transactions, or idempotency.
- `switch` over a sealed hierarchy lets the compiler flag newly added subtypes; avoid using `default` just to hide missing cases.
- Record patterns deconstruct components structurally; `when` guards need a fallback path when the guard does not match.
- **Commands differ from events and results**: a request can be rejected, and success in the example does not imply durable persistence.
- Compiler checks and behavior tests must go hand in hand. Test **command type × state × invalid input**, not just one test per case.
- Java 21+ is required for pattern `switch` and record patterns in the full program; use `--release` matching your target environment.

**Official References:**
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409)
- [JEP 395 — Records](https://openjdk.org/jeps/395)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Java Language Specification 21 — Switch Statements and Pattern Matching](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html)
- [Java SE 21 — The javac Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
