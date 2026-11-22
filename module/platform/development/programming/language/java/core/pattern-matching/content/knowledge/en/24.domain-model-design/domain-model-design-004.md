# Representing Events with a Sealed Hierarchy in Java

In a domain model, an **event** represents something that **has already happened** and is meaningful to the business: an order was created, a payment was recorded, goods were shipped, or an order was cancelled. When events have different data structures but belong to the same group, Java allows modeling them using a **`sealed interface` (or `sealed class`) combined with `record`**. Then, **pattern matching** in `switch` can branch on each event variant while the compiler checks exhaustiveness.

This lesson belongs to **Java Core Pattern Matching → Domain Model Design**, focusing on how to design a closed **event type hierarchy**, destructure payloads with record patterns, handle events with `switch` expressions, ensure type safety, and distinguish compile-time guarantees from runtime validation.

**Java versions:** `sealed` has been stable since Java 17 (JEP 409), `record` since Java 16 (JEP 395), and record patterns and pattern matching for `switch` since **Java 21** (JEP 440, JEP 441). The complete example uses Java 21+ without requiring preview features.

## 1. What is an event, and how does it differ from a command?

- A **command** expresses a request or intention: “Create an order”, “Ship the order”. A command can be rejected because the business rules do not allow it yet.
- A **domain event** expresses a business fact that **has already happened**: `OrderPlaced`, `PaymentReceived`, `OrderShipped`, `OrderCancelled`. Event names are typically in the past tense so readers can distinguish them from actions about to be performed.
- **State** is the current state of an aggregate; many systems can compute or update state when processing the appropriate events.

Example sequence:

```text
OrderPlaced("O-7", 12500)
    ↓
PaymentReceived("O-7", "pay-1")
    ↓
OrderShipped("O-7", "TRK-9")
    ↓
OrderState(status = SHIPPED, totalCents = 12500)
```

This is an example of **event representation** and state updates; it does not automatically turn an application into an event-sourced system. Event sourcing also requires durable event storage, version control, ordering, replay, and other operational guarantees.

### Why not use a single record containing `String type`?

A common approach looks like this:

```java
// Design with many invalid data states.
record GenericEvent(
    String type,
    String orderId,
    Long totalCents,
    String paymentRef,
    String trackingCode,
    String cancellationReason
) {}
```

With this design, `type = "ORDER_PLACED"` can still carry a `trackingCode` and lack `totalCents`; the compiler does not know which fields are required for each event type. Handling logic often requires string comparisons, casts, or checking a series of `null` fields.

**Sealed hierarchy + record** separates each case into its own type and avoids “a single object holding every optional field”. Even so, the compiler still cannot automatically guarantee that each component value is valid from a business standpoint.

## 2. Declaring a sealed hierarchy for a domain event family

Java 21+ example:

```java
sealed interface OrderEvent
        permits OrderPlaced, PaymentReceived, OrderShipped, OrderCancelled {
    String orderId();
}

record OrderPlaced(String orderId, long totalCents) implements OrderEvent {}
record PaymentReceived(String orderId, String paymentRef) implements OrderEvent {}
record OrderShipped(String orderId, String trackingCode) implements OrderEvent {}
record OrderCancelled(String orderId, String reason) implements OrderEvent {}
```

The snippets here illustrate the structure; a standalone program with the full enclosing class is in Section 6.

### What does each part mean?

1. **`sealed interface OrderEvent`** defines an event family with a controlled set of variants.
2. **`permits`** lists the four allowed direct implementation types. Any arbitrary type cannot silently `implements OrderEvent` without satisfying the rules of the sealed hierarchy.
3. **`record OrderPlaced(...)`** and the remaining records carry different payloads. A record is implicitly `final`, making it well suited as a leaf type in the hierarchy.
4. **`String orderId();`** on the interface is a shared contract. Because every record has a `String orderId` component, the generated `orderId()` accessor satisfies the interface method.
5. The remaining components reflect data tied to that specific event: a newly placed order has a total amount, a payment has a reference code, a shipment has a tracking code, and a cancellation has a reason.

Thanks to the shared interface, a method can accept `OrderEvent` without accepting arbitrary unrelated `Object` instances:

```java
// Illustrative snippet.
void publish(OrderEvent event) {
    // Code calling this method knows the event belongs to the OrderEvent family.
}
```

If the business introduces a new variant `OrderReturned`, you must **add the new type to the hierarchy and update dependent code**. This is intentional: the event set should be managed as a domain contract, not extended arbitrarily.

### Source code structure

In the standalone program below, the interface and records are declared **nested inside a `public` class** so it can be compiled as a single file. In a real project, you can split them into separate files or packages following Java's `sealed` and `permits` rules, and set API visibility as needed. Do not make types `public` that should remain internal just because a single-file example does so.

## 3. Using a `switch` expression to handle all variants

When the selector has static type `OrderEvent`, the compiler knows the set of permitted variants. We can write a `switch` expression **without `default`**:

```java
// Snippet inside a method returning String; 'event' is an OrderEvent.
return switch (event) {
    case OrderPlaced(var id, var total) -> "Placed: " + id;
    case PaymentReceived(var id, var ref) -> "Paid: " + id;
    case OrderShipped(var id, var code) -> "Shipped: " + id;
    case OrderCancelled(var id, var reason) -> "Cancelled: " + id;
};
```

Each branch contains a **record pattern**: the compiler checks the record type and infers the types of its components; for example, `total` is `long` and `id` is `String`. There is no need to call `event.getClass()` or cast manually.

**Benefit of an exhaustive switch:** If you remove the `OrderCancelled` branch, the `switch` expression no longer covers every `OrderEvent` variant and the compiler reports an error. If you extend the hierarchy with a new permitted type, exhaustive switches without `default` will require updates upon recompilation.

**When should `default` be included?** When the selector belongs to an open set—such as `Object` containing unbounded types—or when the business genuinely wants a fallback policy. For a sealed hierarchy designed as a closed set, an overly broad `default` can **hide compiler signals** when a new event is added.

### Is `null` a fifth variant?

No. `null` is not an event record. In a `switch` over a reference type, if the selector is `null` and there is no matching branch, evaluation typically throws `NullPointerException`. You can explicitly choose one of two policies:

- Disallow null events by using `Objects.requireNonNull(event, "event")` at the start of the method to reject them immediately.
- If null has a business meaning, use `case null -> ...`.

In the sample program, a null event is invalid data, so it is rejected before the `switch`. Do not conflate `default` with null handling.

## 4. Pattern guards to classify a variant by its data

Sometimes an event is still an `OrderPlaced`, but you want to treat high-value orders differently from regular ones:

```java
// Switch expression snippet on OrderEvent.
return switch (event) {
    case OrderPlaced(var id, var total) when total >= 10_000 ->
            "Large placement " + id;
    case OrderPlaced(var id, var total) -> "Placement " + id;
    case PaymentReceived(var id, var ref) -> "Payment " + id;
    case OrderShipped(var id, var code) -> "Shipment " + id;
    case OrderCancelled(var id, var reason) -> "Cancellation " + id;
};
```

Here:

- The `OrderPlaced(...) when total >= 10_000` branch runs when both the record matches and the guard evaluates to true.
- The subsequent `OrderPlaced(...)` branch handles the remaining orders, ensuring full coverage of this variant.
- The pattern variable `total` is in scope in the guard because the compiler knows the pattern has already matched before evaluating the condition.
- If you place the unguarded `OrderPlaced(...)` branch **before** the guarded branch, the later branch is shadowed (**dominated case**) and Java will report a compile-time error.

Guards are well suited for classifying a value, but do not turn `when` into a place for I/O, payments, database updates, or side-effecting operations. In a testable domain model, event-handling branches should have a clear purpose and classification logic should be as pure as possible.

## 5. Applying events to state: what does the compiler help with?

In an order system, a typical lifecycle might be:

```text
(no order yet) --OrderPlaced--> PLACED
PLACED         --PaymentReceived--> PAID
PAID           --OrderShipped--> SHIPPED
PLACED/PAID    --OrderCancelled--> CANCELLED
```

A function that takes **current state + event** and returns a **new state** is commonly called a **reducer** or **event application function**:

```java
// Signature example; full class and method definitions are in Section 6.
static OrderState apply(OrderState state, OrderEvent event)
```

Benefits of the type design:

- The input is `OrderEvent`, not an unchecked string event name.
- The compiler forces a `switch` expression without `default` to handle every permitted event type.
- Record patterns extract the exact payload of each type; you cannot accidentally confuse `OrderShipped.trackingCode()` with `PaymentReceived.paymentRef()`.
- The return value is guaranteed to be of type `OrderState` when a branch completes normally.

**What the compiler does not automatically guarantee:** Did `PaymentReceived` actually arrive after `OrderPlaced`? Does an event's ID match the aggregate? Is the total amount positive? Is the tracking code non-blank? Is the user authorized to cancel the order? These require **runtime validation**, API contracts, and tests.

In the sample code, if a state transition is invalid, the method throws an explicit exception. In a real event-sourced system, detecting an invalid event sequence often indicates corrupted historical data or an event version mismatch, requiring specific operational and error-handling policies; errors should not simply be swallowed.

## 6. Complete, runnable Java 21+ example

Create the file **`SealedOrderEventsDemo.java`**:

```java
public class SealedOrderEventsDemo {
    sealed interface OrderEvent
            permits OrderPlaced, PaymentReceived, OrderShipped, OrderCancelled {
        String orderId();
    }

    record OrderPlaced(String orderId, long totalCents) implements OrderEvent {}
    record PaymentReceived(String orderId, String paymentRef) implements OrderEvent {}
    record OrderShipped(String orderId, String trackingCode) implements OrderEvent {}
    record OrderCancelled(String orderId, String reason) implements OrderEvent {}

    enum Status { PLACED, PAID, SHIPPED, CANCELLED }
    record OrderState(String orderId, Status status, long totalCents) {}

    static void requireStatus(OrderState state, Status expected) {
        if (state == null || state.status() != expected) {
            throw new IllegalStateException("Expected status " + expected);
        }
    }

    static OrderState apply(OrderState state, OrderEvent event) {
        java.util.Objects.requireNonNull(event, "event");

        if (state != null && !state.orderId().equals(event.orderId())) {
            throw new IllegalArgumentException("Mismatched order id");
        }

        return switch (event) {
            case OrderPlaced(var id, var total) -> {
                if (state != null) {
                    throw new IllegalStateException("Order already exists");
                }
                if (id == null || id.isBlank() || total <= 0) {
                    throw new IllegalArgumentException("Invalid placement");
                }
                yield new OrderState(id, Status.PLACED, total);
            }

            case PaymentReceived(var id, var paymentRef) -> {
                requireStatus(state, Status.PLACED);
                if (paymentRef == null || paymentRef.isBlank()) {
                    throw new IllegalArgumentException("Missing payment ref");
                }
                yield new OrderState(id, Status.PAID, state.totalCents());
            }

            case OrderShipped(var id, var trackingCode) -> {
                requireStatus(state, Status.PAID);
                if (trackingCode == null || trackingCode.isBlank()) {
                    throw new IllegalArgumentException("Missing tracking code");
                }
                yield new OrderState(id, Status.SHIPPED, state.totalCents());
            }

            case OrderCancelled(var id, var reason) -> {
                if (state == null
                        || state.status() == Status.SHIPPED
                        || state.status() == Status.CANCELLED) {
                    throw new IllegalStateException("Cannot cancel in current status");
                }
                if (reason == null || reason.isBlank()) {
                    throw new IllegalArgumentException("Missing cancellation reason");
                }
                yield new OrderState(id, Status.CANCELLED, state.totalCents());
            }
        };
    }

    static String describe(OrderEvent event) {
        java.util.Objects.requireNonNull(event, "event");

        return switch (event) {
            case OrderPlaced(var id, var total) when total >= 10_000 ->
                    "Large placement " + id;
            case OrderPlaced(var id, var total) -> "Placement " + id;
            case PaymentReceived(var id, var ref) -> "Payment " + id;
            case OrderShipped(var id, var code) -> "Shipment " + id;
            case OrderCancelled(var id, var reason) -> "Cancellation " + id;
        };
    }

    public static void main(String[] args) {
        OrderEvent[] timeline = {
                new OrderPlaced("O-7", 12_500),
                new PaymentReceived("O-7", "pay-1"),
                new OrderShipped("O-7", "TRK-9")
        };

        OrderState state = null;
        for (OrderEvent event : timeline) {
            state = apply(state, event);
            System.out.println(describe(event) + " -> " + state.status());
        }

        System.out.println("Final: " + state.orderId() + "/" + state.status()
                + "/" + state.totalCents());

        OrderState another = apply(null, new OrderPlaced("O-8", 500));
        another = apply(another, new OrderCancelled("O-8", "Changed mind"));
        System.out.println("Cancelled: " + another.status());

        try {
            apply(state, new OrderCancelled("O-7", "Late request"));
        } catch (IllegalStateException ex) {
            System.out.println("Rejected: " + ex.getMessage());
        }

        try {
            apply(state, new PaymentReceived("OTHER", "pay-x"));
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected: " + ex.getMessage());
        }
    }
}
```

Compile and run with **JDK 21 or later**:

```bash
javac --release 21 -encoding UTF-8 SealedOrderEventsDemo.java
java SealedOrderEventsDemo
```

Output:

```text
Large placement O-7 -> PLACED
Payment O-7 -> PAID
Shipment O-7 -> SHIPPED
Final: O-7/SHIPPED/12500
Cancelled: CANCELLED
Rejected: Cannot cancel in current status
Rejected: Mismatched order id
```

### Why does the example work this way?

1. `OrderPlaced("O-7", 12500)` is valid when `state == null`. `apply` creates a new `OrderState` with status `PLACED`. `describe` selects the guarded branch because `12500 >= 10000`.
2. `PaymentReceived("O-7", "pay-1")` requires the previous state to be `PLACED`; the reducer transitions to `PAID` and preserves `totalCents`.
3. `OrderShipped("O-7", "TRK-9")` requires the previous state to be `PAID`, transitioning to `SHIPPED`.
4. For a new order `O-8`, `OrderCancelled` is applied after placement; because it has not been shipped or cancelled yet, the state transitions to `CANCELLED`.
5. Cancelling `O-7` after the state is already `SHIPPED` is rejected by business rules inside `apply`, **not because the compiler forbids constructing an `OrderCancelled` instance**.
6. `PaymentReceived("OTHER", "pay-x")` has an `orderId` that does not match state `O-7`. The method rejects it before pattern matching.
7. `Objects.requireNonNull(event, "event")` makes it explicit that a `null` event is invalid input. Therefore, the `switch` does not need `case null` to represent an event kind.

**Why use `yield`?** Each reducer branch executes multiple validation statements before producing a new `OrderState`. `yield` returns the branch value for the **`switch` expression**. `return` would exit the enclosing method; in the code above, `return switch (...)` returns the result of the entire expression.

## 7. Good event design: decisions to make explicit

### 7.1. One event = one meaningful fact

Name variants after what happened—for example, `PaymentReceived` rather than `PayOrder` if the latter is actually a request. Name components after the event's content and unit of measurement:

- `totalCents` is the monetary amount in the smallest unit; avoid naming it `total` when there is a risk of unit confusion.
- `paymentRef` is the payment reference code, distinct from `trackingCode` on the shipment event.
- `reason` on `OrderCancelled` can be empty or `null` if the API allows it, but should be validated according to the contract.

Keep events as data describing the past. Avoid putting side-effecting operations such as sending emails or calling payment gateways inside event accessors or constructors.

### 7.2. Records are shallowly immutable at the component reference level, not deeply immutable

Record components cannot be reassigned after construction, but they **do not automatically make mutable objects they reference deeply immutable**.

```java
// Illustrative snippet: avoid holding a mutable list and exposing it.
record ItemsAdded(String orderId, java.util.List<String> skus) {
    ItemsAdded {
        skus = java.util.List.copyOf(skus);
    }
}
```

For records containing a `List`, making an immutable copy on construction protects the list contents from modification through the original reference; if elements inside the list are themselves mutable, consider deep copying accordingly. `List.copyOf` rejects `null` elements and a `null` list itself, so only use it when that constraint fits the domain.

In the main example, event components are `String` and primitive types, making them easy to keep as **value-like immutable objects**.

### 7.3. Shared event contracts

For production events, you often need additional metadata such as `eventId`, `aggregateId`, `occurredAt`, and `schemaVersion`. You can:

- Place the shared metadata in an **envelope** wrapping the payload.
- Or declare shared accessors on the sealed interface and let record implementations provide the corresponding data.

Avoid repeating all metadata fields in every record if it creates excessive duplication or hurts readability. Example envelope design:

```java
// Standalone snippet (Java 21+).
record EventEnvelope(
    String eventId,
    String aggregateId,
    java.time.Instant occurredAt,
    int schemaVersion,
    OrderEvent payload
) {}
```

This envelope is not required in the reducer example, but it clearly illustrates the separation between **delivery/storage metadata** and **business payload**. You can add validation for the metadata in the constructor or ingestion layer.

### 7.4. Choose `sealed` when the variant set has a clear owner

A sealed hierarchy fits when a single module or bounded context **actively owns and manages the set of variants**. If a platform allows external plugins to define new events without modifying the core module, a completely closed sealed hierarchy may be an unsuitable constraint.

Depending on the extensibility needed, consider a regular interface, a hierarchy with a controlled `non-sealed` branch, or communicating via a schema/message envelope. `switch` exhaustiveness depends strictly on the set of types known to the compiler; an open branch requires corresponding branching logic.

## 8. Evolution, versioning, and system boundaries

**A code change does not automatically upgrade previously stored events.** In systems with an event log, message broker, or JSON persistence, adding or modifying variants must be managed carefully:

1. **Adding a new variant:** The compiler helps locate exhaustive `switch` expressions without `default` that must handle the new variant in the recompiled codebase.
2. **Adding a new field to a record:** Changes the canonical constructor and payload schema. Consumers of older data may lack the new field; you need a compatibility policy such as default values during deserialization, adapters, or upcasting from older versions.
3. **Renaming an event or changing its meaning:** Can break integration contracts. Many systems choose to introduce a new event version rather than silently changing semantics.
4. **Transport over JSON/Kafka:** At runtime, JSON does not automatically preserve Java's sealed subtypes; serializers/deserializers need a convention to identify variants (an event type discriminator), validation, and handling for unrecognized events.
5. **Replay and ordering:** A reducer assumes events for the same order are processed in a valid order. Real systems must account for ordering, concurrency, idempotency, duplicate delivery, and persistence.
6. **Out-of-order events:** The compiler only checks **event types**, not business history. Runtime logic can reject, defer, or route them to exception handling according to the system contract.

If an event **actually occurred** but cannot be applied to the current state during replay, that may indicate an ordering, schema, or data issue; do not simply “ignore it and keep running”. The design should specify how to operate when an invalid event sequence occurs.

## 9. When to validate at runtime instead of relying on the compiler

| Issue | Can the compiler check it? | What else is needed |
| --- | --- | --- |
| An unauthorized class directly implements `OrderEvent` | Yes, via `sealed` rules | Clear module design and extension permissions |
| A `switch` expression misses a permitted subtype | Yes, when type info allows exhaustiveness checking | Write the corresponding `case` instead of a blind `default` |
| `case OrderPlaced(...)` uses the wrong number of components | Yes | Match the exact record shape |
| A broad `case` shadows a narrower or guarded branch | Detectable via dominance | Place specific/guarded cases before general cases |
| `paymentRef` is blank or `null` | Cannot know business constraints | Constructor validation or runtime guards |
| `PaymentReceived` arrives before `OrderPlaced` | No | State transition validation, testing |
| Event belongs to the wrong `orderId` | No | Aggregate ID matching |
| Event is processed twice (duplicate) | No | Event ID, deduplication, idempotent handlers |
| Consumer reads a newer event version from storage | Cannot resolve automatically | Versioned schema/adapter/upcaster and unknown-type strategy |
| Handler causes side effects twice | No | Transaction design, outbox/inbox, retries, and idempotency |

**Key takeaway:** A sealed hierarchy provides **type safety** and signals when the model evolves; it does not mean “every event is always valid and in the right order”.

## 10. Common mistakes when designing event hierarchies

### Mistake 1: One generic event with lots of optional fields

Using `GenericEvent(type, orderId, payloadA, payloadB, ...)` makes invalid combinations easy to construct. **Fix:** Use distinct records for variants with different payloads; use a separate generic envelope if shared metadata is needed.

### Mistake 2: Adding `default` to every sealed `switch`

`default` can hide new event branches upon recompilation. **Fix:** Prefer explicit branches and exhaustive switches when the variant set is closed; use `default` only when a genuine fallback is desired.

### Mistake 3: Assuming an immutable record means a deeply immutable payload

A record holding a `List`, `Map`, or mutable object can still expose mutable state. **Fix:** Choose immutable types/copies appropriately and protect invariants.

### Mistake 4: Confusing events with commands

Names like `CreateOrder` leave readers unsure whether it is a request or a past fact. **Fix:** Use `OrderPlaced` for the event and `PlaceOrder` for the command if the system has both.

### Mistake 5: Placing a guarded branch after a general branch

For example, putting `case OrderPlaced(var id, var total) -> ...` before `case OrderPlaced(var id, var total) when total > 10000 -> ...`. The second branch is dominated. **Fix:** Place guarded cases before unguarded cases of the same type.

### Mistake 6: Assuming record patterns validate business rules

`OrderPlaced(var id, var total)` can match an instance with `total <= 0`; `var id` can receive `null`. **Fix:** Validate values at boundaries, constructors, or reducers.

### Mistake 7: Assuming every consumer runs the same Java version and schema

An event persisted from an older version will not necessarily deserialize into the current record type. **Fix:** Define rules for versioning, migration, compatibility, and unknown event handling.

### Mistake 8: Using long `instanceof` chains instead of an exhaustive `switch` without reason

An `if (event instanceof A) ... else if ...` chain can work, but it does not force the compiler to verify full coverage of all variants like an exhaustive `switch` expression does. **Fix:** Prefer `switch` when branching across all subtypes.

## 11. Practice exercises

Suppose an inventory system has two event types:

```java
sealed interface InventoryEvent permits StockAdded, StockRemoved {}
record StockAdded(String sku, int units) implements InventoryEvent {}
record StockRemoved(String sku, int units) implements InventoryEvent {}
```

### Exercise 1 — Write an exhaustive `switch` expression

Write a method `int delta(InventoryEvent event)` returning the quantity change: positive for `StockAdded`, negative for `StockRemoved`. Do not use `default`.

**Answer:**

```java
static int delta(InventoryEvent event) {
    java.util.Objects.requireNonNull(event, "event");
    return switch (event) {
        case StockAdded(var sku, var units) -> units;
        case StockRemoved(var sku, var units) -> -units;
    };
}
```

This is a **method snippet** and must be placed in a class that contains or can see the corresponding event declarations. In a real application, you should validate `units > 0` so event values are meaningful. With that constraint, you avoid negative numbers or overflow from invalid input.

### Exercise 2 — Add a variant

Add `record StockReserved(String sku, int units) implements InventoryEvent {}` and update `permits`. What happens to `delta` before it is updated?

**Answer:** The `switch` expression is no longer exhaustive. The compiler requires handling `StockReserved`. The designer must decide whether a reservation event changes physical stock on hand, available stock, or only a separate reserved field; you should not arbitrarily return `0` without defining the business meaning.

### Exercise 3 — Use a guard

Write `String classify(InventoryEvent event)` where `StockAdded` events with `units >= 100` are labeled `"large intake"`, remaining `StockAdded` events are `"intake"`, and `StockRemoved` is `"outflow"`.

**Answer:**

```java
static String classify(InventoryEvent event) {
    java.util.Objects.requireNonNull(event, "event");
    return switch (event) {
        case StockAdded(var sku, var units) when units >= 100 -> "large intake";
        case StockAdded(var sku, var units) -> "intake";
        case StockRemoved(var sku, var units) -> "outflow";
    };
}
```

The guarded branch precedes the general branch. Separate validation is needed for `units <= 0` if the business disallows it.

### Exercise 4 — Distinguish compile-time from runtime

An event `PaymentReceived("O-7", "pay-1")` is created before order `O-7` exists. Will the compiler reject creating this record?

**Answer:** No. The record type is valid, so the compiler accepts it. Runtime event-application or service logic must check the state and decide whether to reject or handle it according to business policy.

## 12. Project adoption checklist

Before choosing a sealed hierarchy for events, check:

1. Is the set of variants managed by a clear module or bounded context?
2. Do event names represent **facts that already happened** rather than commands?
3. Does each event have a minimal payload with the right types and units of measurement?
4. Is delivery/storage metadata cleanly separated from business data?
5. Are `switch` expressions over the hierarchy exhaustive and free of `default` branches that hide new cases?
6. Where are `null`, invalid input, duplicates, out-of-order events, and mismatched IDs handled?
7. Is there a strategy for event persistence, serialization, schema versioning, and replay?
8. Are there tests for every event type and every state transition?

**Remember:** `sealed` controls **which event types can exist in a hierarchy**, `record` describes **what data each event carries**, and pattern matching + `switch` expresses **how each variant is handled**. Combining them properly makes the domain model readable, safely extensible, and supported by the compiler as it evolves. State transition rules, data validation, and event operations still need to be designed and tested separately.

**Official sources:** [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409), [JEP 395 — Records](https://openjdk.org/jeps/395), [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441), [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
