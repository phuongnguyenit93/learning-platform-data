# Sealed Domain Model for Events and Commands in Java

## 1. Purpose of the Model

In a Java business application, a **command** and a **domain event** are not two names for the same thing:

- **Command** is a *request/intent*: "place order", "cancel order", "change address". A request may be valid in format yet still be rejected due to business state.
- **Domain event** is a *fact that has already happened*: "order was placed", "order was cancelled". An event should describe something that has been accepted/recorded, not a request to perform an action in the future.

A **sealed domain model** uses a `sealed interface` or `sealed class` to control the **set of direct subtypes** permitted for those message groups. Combined with `record` and pattern matching for `switch` (Java 21), we can represent **finite variants** of a domain in a type-safe manner.

~~~text
Client / API
     |
     v
PlaceOrder, CancelOrder             COMMAND: What do we want to do?
     |
     v
decide(currentState, command)       Check business rules
     |           \
     |            \-- Rejection / exception: no success event
     v
OrderPlaced, OrderCancelled         EVENT: What happened?
     |
     v
apply(currentState, event)          Build state / projection
     |
     v
OrderState
~~~

Key benefits:

1. **Clear semantics:** the `Command` type cannot be confused with the `Event` type.
2. **Finite and owned:** a sealed hierarchy defines the permitted direct variants.
3. **Explicit payload:** each `record` has fields matching the business domain, instead of a custom `Map<String, Object>` wrapper or `String type` code.
4. **Exhaustiveness:** Java 21 can check whether a `switch expression` handles all subtypes of a closed hierarchy, without needing `default`.
5. **Easy to test:** handlers, validation, state transitions, and projections can be tested independently.

**Limitations:** `sealed` does not automatically turn an application into *event sourcing*, does not persist events, and does not guarantee idempotency, transactions, delivery ordering, serialization, or version compatibility. Those are additional design decisions.

## 2. Separating Two Sealed Hierarchies Instead of Mixing Messages

Brief model:

~~~java
sealed interface Command permits PlaceOrder, CancelOrder {}

record PlaceOrder(String id, String sku, int quantity)
        implements Command {}

record CancelOrder(String id, String reason)
        implements Command {}

sealed interface Event permits OrderPlaced, OrderCancelled {}

record OrderPlaced(String id, String sku, int quantity)
        implements Event {}

record OrderCancelled(String id, String reason)
        implements Event {}
~~~

These are **illustrative declarations**, not a file with a `main` method. They can be types organized according to package/module rules or nested types inside a class.

| Command | Meaning | Corresponding success event in the example |
| --- | --- | --- |
| `PlaceOrder(id, sku, quantity)` | Request to place an order with product/quantity | `OrderPlaced(id, sku, quantity)` |
| `CancelOrder(id, reason)` | Request to cancel a valid order | `OrderCancelled(id, reason)` |

Even if the command and event records have the same fields, their semantics remain different:

- `CancelOrder` can be rejected if the order does not exist or has already been cancelled.
- `OrderCancelled` must be created after the business logic confirms that the cancellation has occurred.
- Do not automatically treat "request arrived at the API" as a "success event".
- A command can produce **0, 1, or multiple events** depending on the domain. The main example below chooses **one event per successful command** to make the data flow easy to see.

Separating `Command` and `Event` also lets the compiler prevent passing `OrderPlaced` into a handler expecting a `Command`, or passing `PlaceOrder` into a projector that only accepts `Event`.

## 3. Required Java Version

| Feature | Standard since | Role |
| --- | --- | --- |
| `record` | Java 16 | Data type with fixed components, accessors, value equality |
| Pattern matching for `instanceof` | Java 16 | `obj instanceof MyType t` |
| `sealed` and `permits` | Java 17 | Control direct subtypes |
| `switch expression` | Java 14 | Expression that produces a value |
| Pattern matching for `switch` | Java 21 | `case PlaceOrder p -> ...` |
| Record patterns | Java 21 | `case PlaceOrder(String id, String sku, int qty)` |

**The main program requires JDK 21+** because it combines sealed hierarchies and record patterns in `switch`. These features are all standard and do not require `--enable-preview`.

**Java 17** can still use `sealed` + `record`; you just need to dispatch using `instanceof` or another mechanism instead of Java 21 pattern `switch`. This article includes a separate Java 17-compatible program in section 9.

## 4. Complete Program: sealed command → event → state

The example is an **in-memory order aggregate**. The model has two commands, two events, and one state. The handler uses:

- `decide(state, command)`: checks rules and produces an event or rejects.
- `apply(state, event)`: builds the new state from an event.
- `show(event)`: displays the event to observe the selected branch.

Save **`SealedOrderDomainDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class SealedOrderDomainDemo {

    sealed interface Command permits PlaceOrder, CancelOrder {}

    record PlaceOrder(String id, String sku, int quantity)
            implements Command {
        PlaceOrder {
            Objects.requireNonNull(id);
            Objects.requireNonNull(sku);
            if (id.isBlank() || sku.isBlank() || quantity <= 0) {
                throw new IllegalArgumentException("invalid order");
            }
        }
    }

    record CancelOrder(String id, String reason)
            implements Command {
        CancelOrder {
            Objects.requireNonNull(id);
            Objects.requireNonNull(reason);
            if (id.isBlank() || reason.isBlank()) {
                throw new IllegalArgumentException("invalid cancellation");
            }
        }
    }

    sealed interface Event permits OrderPlaced, OrderCancelled {}

    record OrderPlaced(String id, String sku, int quantity)
            implements Event {}

    record OrderCancelled(String id, String reason)
            implements Event {}

    record OrderState(
            String id, String sku, int quantity, boolean cancelled) {}

    // Command + state => one event, or business error.
    static Event decide(OrderState state, Command command) {
        Objects.requireNonNull(command, "command");

        return switch (command) {
            case PlaceOrder(String id, String sku, int quantity) -> {
                if (state != null) {
                    throw new IllegalStateException("order exists");
                }
                yield new OrderPlaced(id, sku, quantity);
            }

            case CancelOrder(String id, String reason) -> {
                if (state == null
                        || !state.id().equals(id)
                        || state.cancelled()) {
                    throw new IllegalStateException("cannot cancel");
                }
                yield new OrderCancelled(id, reason);
            }
        };
    }

    // Event + state => next state, usable during replay.
    static OrderState apply(OrderState state, Event event) {
        Objects.requireNonNull(event, "event");

        return switch (event) {
            case OrderPlaced(String id, String sku, int quantity)
                    -> new OrderState(id, sku, quantity, false);

            case OrderCancelled(String id, String reason) -> {
                if (state == null || !state.id().equals(id)) {
                    throw new IllegalStateException("invalid history");
                }
                yield new OrderState(
                        id, state.sku(), state.quantity(), true);
            }
        };
    }

    static String show(Event event) {
        return switch (event) {
            case OrderPlaced(String id, String sku, int quantity)
                    -> "ORDER_PLACED " + id + " " + sku
                            + " x" + quantity;

            case OrderCancelled(String id, String reason)
                    -> "ORDER_CANCELLED " + id + " reason=" + reason;
        };
    }

    static String stateLine(String prefix, OrderState state) {
        return prefix + " " + state.id() + " "
                + (state.cancelled() ? "CANCELLED" : "ACTIVE");
    }

    public static void main(String[] args) {
        List<Command> commands = List.of(
                new PlaceOrder("O-17", "BOOK", 2),
                new CancelOrder("O-17", "customer request")
        );

        List<Event> history = new ArrayList<>();
        OrderState state = null;

        for (Command command : commands) {
            Event event = decide(state, command);
            history.add(event);
            System.out.println(show(event));
            state = apply(state, event);
        }

        System.out.println(stateLine("STATE", state));

        // Replay: rebuild state from the emitted events.
        OrderState replay = null;
        for (Event event : history) {
            replay = apply(replay, event);
        }
        System.out.println(stateLine("REPLAY", replay));

        // Second cancel command is rejected.
        try {
            decide(state, new CancelOrder("O-17", "again"));
        } catch (IllegalStateException ex) {
            System.out.println("REJECTED " + ex.getMessage());
        }
    }
}
~~~

Compile and run with JDK 21 or newer:

~~~bash
javac SealedOrderDomainDemo.java
java SealedOrderDomainDemo
~~~

Exact output:

~~~text
ORDER_PLACED O-17 BOOK x2
ORDER_CANCELLED O-17 reason=customer request
STATE O-17 CANCELLED
REPLAY O-17 CANCELLED
REJECTED cannot cancel
~~~

### Analyzing the Execution Flow

**For PlaceOrder:**

1. The record's compact constructor ensures `id`, `sku` are not null/blank and `quantity > 0`.
2. `decide(null, PlaceOrder(...))` matches the `PlaceOrder` record pattern.
3. Because the aggregate does not have a state yet, the branch produces `OrderPlaced`.
4. The event is added to the `history` list; `apply` creates an uncancelled `OrderState`.

**For CancelOrder:**

1. The record constructor validates `id`/`reason`.
2. `decide` checks that the order exists, matches `id`, and has not been cancelled.
3. The handler produces `OrderCancelled`; `apply` returns a new state with `cancelled = true`.

**For replay:** `apply` is called sequentially on the two events in history, starting from `state = null`, yielding the same final state. This is an in-memory demo, not a persistent event store.

**For the repeat cancel command:** `state.cancelled()` being `true` causes the handler to throw `IllegalStateException("cannot cancel")`. No success event is produced from that command.

### Why Use `yield` in `decide`/`apply`?

Both `decide` and `apply` use a **switch expression** to compute a value. In a case with multiple statements (checking state then creating an event), `yield value;` provides the result for the switch expression:

~~~java
case CancelOrder(String id, String reason) -> {
    if (state == null || state.cancelled()) {
        throw new IllegalStateException("cannot cancel");
    }
    yield new OrderCancelled(id, reason);
}
~~~

This is an **illustrative snippet**; the full `id` check rule is in the main program. `yield` is not a method `return`: it produces a value out of the switch expression. In a case with only a single expression, such as `case OrderPlaced(...) -> new OrderState(...);`, you do not need to write `yield`.

## 5. How Does `sealed` Help `switch` Check Exhaustiveness?

In the program, the `Command` hierarchy consists of exactly two direct subtypes, which are two records:

~~~java
sealed interface Command permits PlaceOrder, CancelOrder {}
~~~

And the handler has two corresponding cases:

~~~java
return switch (command) {
    case PlaceOrder(String id, String sku, int quantity) -> {
        // Handle PlaceOrder then yield Event.
    }
    case CancelOrder(String id, String reason) -> {
        // Handle CancelOrder then yield Event.
    }
};
~~~

The two blocks here are **explanatory snippets**, not standalone code to compile. In the full program, each case is completely implemented.

Because the subtype set is closed and the two records are implicitly `final`, the Java 21 compiler can prove that the switch expression handles all **non-null `Command`** variants. The same applies to `Event`: the two branches `OrderPlaced` and `OrderCancelled` are sufficient for `apply`/`show` to be exhaustive.

### When Adding a New Subtype

Suppose the business introduces `ChangeAddress`. We update:

~~~java
sealed interface Command
        permits PlaceOrder, CancelOrder, ChangeAddress {}

record ChangeAddress(String id, String newAddress)
        implements Command {}
~~~

This is a **hypothetical change**; do not add it to the demo file unless you also update the handler. If the `decide` switch still only has `PlaceOrder` and `CancelOrder` without a `default`, the compiler will report that **the switch expression is not exhaustive** after updating the hierarchy.

That is a major benefit: changing the list of variants forces all handling sites to revisit the new domain at **compile time**, instead of letting production receive a command that the application does not yet know how to handle.

### Why Not Add `default` Mechanically?

~~~java
return switch (command) {
    case PlaceOrder p -> handlePlace(p);
    case CancelOrder c -> handleCancel(c);
    default -> throw new IllegalArgumentException("unknown");
};
~~~

This is only an **illustrative snippet** (assuming `handlePlace` and `handleCancel` have been declared). `default` can allow the switch to **keep compiling** when a new command is added, but that valid command falls into the generic fallback.

For a hierarchy designed to be **closed**, consider **omitting `default`** so the compiler can help check exhaustiveness. However, if a boundary genuinely needs to accept extensions or an "unknown message", `default` can be an intentional decision. Choose according to the application's contract.

### Runtime and Binary Changes

If a module has already compiled an exhaustive switch, and later the sealed hierarchy is modified and released out of sync with an older consumer, the consumer may encounter a new subtype at runtime and throw **`MatchException`** (Java 21). Changing subtypes is a **contract change**: it requires recompiling, testing, and an appropriate rollout. `sealed` does not automatically solve multi-version deployment issues.

## 6. Rules for `permits`, `final`, and `non-sealed`

A sealed supertype controls its **direct subclasses/direct implementors**:

~~~java
sealed interface Command permits Create, Delete {}

record Create(String id) implements Command {}
record Delete(String id) implements Command {}
~~~

Records are **implicitly final**, so they satisfy the requirement for direct subtypes of a sealed interface. A class that directly extends/implements a sealed supertype must be permitted, and must also declare its further inheritance policy with `final`, `sealed`, or `non-sealed` (explicitly or implicitly like a record).

Intentionally invalid code:

~~~java
sealed interface Command permits Create, Delete {}

record Create(String id) implements Command {}
record Delete(String id) implements Command {}

// COMPILE ERROR: Unlisted is not in permits.
record Unlisted(String id) implements Command {}
~~~

**Package/module rule:** if a sealed supertype belongs to a named module, its direct permitted subclasses must belong to the **same named module**. If using the unnamed module, permitted subclasses must be in the **same package**. Therefore, a multi-file/multi-package design cannot arbitrarily list any subtype in any module.

### `non-sealed` No Longer Closes All Branches

~~~java
sealed interface Message permits Internal, Extension {}

record Internal(String id) implements Message {}

non-sealed interface Extension extends Message {}

final class ExternalMessage implements Extension {}
~~~

`Extension` is a permitted direct subtype, but it reopens a branch. New subtypes can implement `Extension` according to Java rules. Therefore, you cannot assume "every implementation at every level is listed in `permits`" if there is `non-sealed` in the tree.

If the event/command set must be finite so the compiler knows all leaves, prefer `record`/`final` or sealed hierarchies that remain closed down the branches. Only use `non-sealed` when the design has a genuine extension point.

**`sealed` is a type-management mechanism**, not a replacement for access control, untrusted input validation, or schema validation of messages crossing the network.

## 7. Record: Concise Data, Yet Invariants Still Must Be Designed

Records automatically generate constructors/accessors/value equality; for example, `PlaceOrder` has accessors `id()`, `sku()`, `quantity()`. Because a record's component fields are final, it is well suited for representing **value messages**.

Even so, do not skip **validation**:

~~~java
record PlaceOrder(String id, String sku, int quantity) {
    PlaceOrder {
        java.util.Objects.requireNonNull(id);
        java.util.Objects.requireNonNull(sku);
        if (id.isBlank() || sku.isBlank() || quantity <= 0) {
            throw new IllegalArgumentException("invalid order");
        }
    }
}
~~~

This is an **illustrative record snippet**, independent of implementing a sealed interface. The compact constructor is used to validate components before Java assigns the fields.

### Payloads Containing Collections Must Be Copied If Immutability Is Needed

A record is only **shallowly immutable**. If a component points to a mutable `ArrayList`, other code can modify the list after the event is created.

~~~java
record BatchCreated(String batchId, java.util.List<String> items) {
    BatchCreated {
        java.util.Objects.requireNonNull(batchId);
        items = java.util.List.copyOf(items);
    }
}
~~~

`List.copyOf` creates a list that cannot be modified through the `List` API and cannot contain `null`. If the **elements** are mutable objects, you also need to consider deep copying or using immutable value types for each element.

For events used as history/audit, avoid payloads with hidden state that changes over time. Records reduce boilerplate, but **do not automatically guarantee that all related objects are immutable**.

### Data Validation Differs from State Validation

- **Creating a command:** validate data independently of state, such as non-null `id`, positive `quantity`.
- **Handling a command:** check state-dependent business conditions, such as whether the order already exists or has already been cancelled.
- **Recording an event:** only produce a success event once the business logic has accepted it.
- **Applying an event:** compute the new state from an event that has occurred; if the history is invalid, handle the error according to the event store/replay policy.

In the example, `IllegalStateException` illustrates rejection. Larger applications may use a sealed `DecisionResult` with `Accepted`/`Rejected` records or dedicated business error types, though not every model necessarily needs an extra hierarchy.

## 8. Event Log, State Projection, and Replay

Core concept:

~~~java
Event event = decide(currentState, command);
OrderState nextState = apply(currentState, event);
~~~

In the example, `history` stores successful events. During replay:

~~~java
OrderState replay = null;
for (Event event : history) {
    replay = apply(replay, event);
}
~~~

Given a **valid and properly ordered history**, the state is reconstructed without re-running `decide`. This is the fundamental difference:

- `decide` handles **new requests** and must know the current acceptance rules.
- `apply` applies **events that have already happened**; during replay, you must not re-issue commands or call an external API to re-decide past facts.

For replay to be reproducible:

1. `apply` should be **deterministic** for the same state and event.
2. Store all facts needed for the state: for example, locked-in prices, business timestamps, or currencies if they affect the outcome.
3. Do not read the current time or call external services on each replay if doing so would alter the state.
4. Have a versioning policy to read older events when schemas/domain rules evolve.

The model in the program only stores `history` in RAM. It is **not yet** an event store with persistence, snapshots, optimistic locking, recovery, and event sequence control.

## 9. Java 17: Sealed Hierarchy with `instanceof` Patterns

Java 17 supports sealed interfaces and records, but **pattern matching for `switch`** is not standard in this version without enabling preview. A common Java 17 solution is dispatching via `instanceof` patterns.

Save **`SealedJava17Demo.java`**:

~~~java
public class SealedJava17Demo {

    sealed interface Command permits Register, Deactivate {}

    record Register(String userId) implements Command {}
    record Deactivate(String userId) implements Command {}

    static String route(Command command) {
        if (command instanceof Register r) {
            return "REGISTER:" + r.userId();
        }

        if (command instanceof Deactivate d) {
            return "DEACTIVATE:" + d.userId();
        }

        throw new IllegalStateException("unknown command");
    }

    public static void main(String[] args) {
        System.out.println(route(new Register("U1")));
        System.out.println(route(new Deactivate("U1")));
    }
}
~~~

~~~bash
javac SealedJava17Demo.java
java SealedJava17Demo
~~~

Output:

~~~text
REGISTER:U1
DEACTIVATE:U1
~~~

The difference: an `if/instanceof` chain must have a hand-written fallback. If a direct subtype is added to the hierarchy, Java 17 does not automatically check whether this `if` chain handles all types like a Java 21 pattern switch expression does.

Therefore, upgrading to Java 21 brings **exhaustiveness checking based on the selector's type**, in addition to more convenient record deconstruction syntax.

## 10. Scaling to Real-World Models: Guards, `null`, and Nested Patterns

### `when` Guards

Java 21 allows placing a condition after a pattern:

~~~java
case PlaceOrder p when p.quantity() >= 10 -> "BULK";
case PlaceOrder p -> "REGULAR";
~~~

These are **illustrative branches** in a switch expression whose selector has type `Command`. The `when` guard is evaluated only **after the pattern matches**. If the guard is false, Java continues checking subsequent cases.

Do not place a general `case PlaceOrder p` **before** a specialized `when` branch, because the broader case will dominate the guarded case behind it. A runtime-guarded case also does not automatically cover all `PlaceOrder` instances for exhaustiveness.

### Null

A sealed interface does not turn `null` into a valid instance. The main example uses `Objects.requireNonNull(command, "command")` before the switch to establish the input contract. If you want to handle `null` as a distinct value inside a Java 21 switch, you can add `case null -> ...`.

**Do not be mistaken:** a switch that is exhaustive over sealed subtypes can still throw `NullPointerException` if the selector is `null` and there is no label handling `null`.

### Nested Record Patterns

You can wrap a command in an envelope:

~~~java
record Envelope(Command command, String correlationId) {}
~~~

And destructure nested data shapes:

~~~java
return switch (incoming) {
    case Envelope(PlaceOrder(String id, String sku, int qty),
                  String correlationId)
            -> "order=" + id + ",trace=" + correlationId;
    default -> "OTHER";
};
~~~

This is an **illustrative switch snippet**, assuming `incoming` has a compatible static type and `Envelope`/`PlaceOrder` are declared. Java 21 record patterns allow accessing components after matching without manual casting.

Note: a record component can be `null`, and Java has specific **null-matching component pattern** rules. If a component can be `null`, validate or check it before calling methods on it; do not assume every component is automatically non-null just because the outer record matched.

## 11. Production: `sealed` Does Not Automatically Solve Distributed Correctness

### 11.1. Command Idempotency

A `PlaceOrder` request may arrive twice due to client retries or queue redelivery. If each attempt produces a different event, the system may record duplicates. Typically, you need a **command ID/idempotency key** and storage capable of recording the processed outcome to return the same result or safely reject duplicate requests.

### 11.2. Persisting Data and Publishing Events

If updating the database succeeds but sending the event to a broker fails, the system may lose integration notifications. Mechanisms such as **transactional outbox**, event store transactions, or an explicitly designed retry workflow may be necessary. No `sealed` feature automatically guarantees an **atomic commit** between a database and a broker.

### 11.3. Ordering and Concurrency

`OrderCancelled` is only valid after `OrderPlaced` in the example's state machine. With multiple workers processing concurrently, you need an **expected version / optimistic concurrency** policy, locking, or a single-writer approach to prevent two commands from updating based on stale state.

Immutable records do not mean a repository, event log, or workflow with shared mutable state is automatically thread-safe.

### 11.4. Schema Evolution and Multi-Version Support

When messages leave the process, Java sealed types are not an automatic wire-format contract. You may need an event type, schema version, and ID:

~~~json
{
  "eventType": "order.placed",
  "schemaVersion": 1,
  "eventId": "evt-123",
  "orderId": "O-17",
  "payload": { "sku": "BOOK", "quantity": 2 }
}
~~~

This is an **illustrative JSON** representation of a serialized event, not program output. When changing `OrderPlaced` or adding a new event, you must check older consumers, backward compatibility, upcasting/migration during history replay, rollout order, and contract tests.

Changing a sealed hierarchy only controls Java code compiled **within a known scope**. An external producer can still send invalid JSON strings or events from another version; adapters must deserialize, validate, and handle unsupported versions.

## 12. When to Use `sealed` and When Not To?

**Appropriate when** the set of domain variants has a clear owner, is finite, and adding a new type is a meaningful change that requires updating handlers. Examples include payment states, order commands, business outcomes, or internal events of a bounded context.

**Reconsider when** the application is designed as an open plugin system where third parties continuously register subtypes. In that case, an open interface, registry, or another handler architecture may be more suitable; using `non-sealed` is also an intentional option if you want to open a branch.

A sealed domain model does not need to become a **single giant shared hierarchy** for every message in an enterprise. Different bounded contexts can have their own command/event sets, their own versions, and adapters to translate between them.

### Reference Organization

~~~text
domain/
  command/        Command and its variants
  event/          Event and its variants
  model/          State / Value Objects
  service/        Decider and Projector
application/
  handler/        Coordinate transactions and results
infrastructure/
  persistence/    Repository / Event Store / Outbox
  transport/      HTTP, JSON, broker adapters
~~~

This is an **architectural suggestion**, not a mandatory package structure. Check the same-module/same-package constraints of sealed hierarchies if you decide to split subtypes into top-level classes across multiple files.

## 13. Common Mistakes

| Mistake | Why it is dangerous | How to handle it |
| --- | --- | --- |
| Treating a command as an event immediately upon receiving a request | May record a business fact that never happened | Validate, decide first, then emit events |
| Using `String type` and casting payloads everywhere | Lacks compiler guarantees | Use sealed variants + records |
| Adding `default -> ignore` to every switch | When a subtype is added, valid events may be silently skipped | Avoid `default` when you want exhaustiveness checking |
| Thinking `sealed` allows any subtype in any JAR | `permits` has module/package rules | Place types within the permitted scope |
| Using `non-sealed` while expecting a closed set of leaves | That branch is open to other subtypes | Only open it when truly needed |
| Thinking records are deeply immutable | Mutable components can still be modified | Defensive copies / value objects |
| Thinking every command produces exactly one event | A command can be rejected or produce multiple events | Design result/event lists per domain |
| Thinking an exhaustive switch handles `null` automatically | `null` still needs an explicit contract | `requireNonNull` or `case null` |
| Using `case Record(...)` in Java 17 as a standard feature | Record pattern switch requires Java 21 | Use JDK 21+ or Java 17 `instanceof` |
| Not preserving event order during replay | Reconstructed state may be wrong | Version/sequence + replay in exact order |
| Lacking idempotency/atomicity | Retries or network errors cause duplicates or lost events | Idempotency key, outbox/event store |
| Adding a subtype without updating consumers | Runtime/binary compatibility errors | Test and roll out in sync |

## 14. Self-Check Questions

**Question 1.** Why is `CancelOrder` not synonymous with `OrderCancelled`?

**Answer:** A cancel command is an intent. If the order does not exist or is already cancelled, no successful cancellation event should be recorded.

**Question 2.** When adding `ChangeAddress` to the sealed `Command`, why is a switch expression without `default` useful?

**Answer:** The compiler checks the closed hierarchy. Any handler missing a branch will report **not exhaustive**, helping locate where the new command must be handled.

**Question 3.** If a direct subtype of a sealed interface is `non-sealed`, is the final set of implementations still guaranteed to be finite?

**Answer:** No. The opened branch can have additional valid subtypes without listing each one in the outer supertype's `permits` clause.

**Question 4.** How does `case PlaceOrder(String id, String sku, int qty)` differ from `case PlaceOrder p`?

**Answer:** The first form is a record pattern that deconstructs the components into variables; the second binds the entire `PlaceOrder` object. Both are used in Java 21 switch patterns.

**Question 5.** Can `sealed` + `record` be used in Java 17? What about `case PlaceOrder p ->` in a standard pattern switch?

**Answer:** Both `sealed` and `record` are standard in Java 17; pattern switch and record patterns were finalized in Java 21. In Java 17, you should dispatch using `instanceof` or another approach.

**Question 6.** Why should `apply(state, event)` not call a service to fetch the "current price" when replaying historical events?

**Answer:** The price at replay time may differ from when the event occurred. Replay must have enough data to deterministically reconstruct the historical outcome, not re-decide the past using current data.

**Question 7.** What happens if a switch is exhaustive over sealed subtypes, but the selector is `null`?

**Answer:** `null` does not automatically match a record subtype. If `null` is not handled explicitly, a switch on a reference may throw an NPE; establish the contract with `Objects.requireNonNull` or `case null`.

## 15. Authoritative References

- [JLS 21 — sealed Interfaces, Section 9.1.1.4](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.1.1.4): `permits` and subtypes of sealed interfaces.
- [JLS 21 — sealed, non-sealed, final Classes, Section 8.1.1.2](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.1.1.2): inheritance policies of sealed hierarchies.
- [JLS 21 — Record Classes, Section 8.10](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10): records and compact constructors.
- [JLS 21 — Switch Statements, Section 14.11](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11): case labels and matching.
- [JLS 21 — Switch Expressions, Section 15.28](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): results and exhaustiveness.
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): sealed type coverage, pattern guards, null, and `MatchException`.
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409) and [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): design rationale and standardization milestones.

**Conclusion:** A sealed model for events and commands separates **intent** from **facts that have occurred** using expressive record types, a controlled set of subtypes, and exhaustive handlers with Java 21 pattern switches. To become a reliable production architecture, you still must properly design validation, state transitions, persistence, replay, idempotency, concurrency, and schema evolution.
