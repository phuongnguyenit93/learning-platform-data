# Combining an Order Record with Sealed Events

## 1. The Problem: Order Is State, Event Is a Fact That Happened

In an ordering application, we often need to store the current state of an *order* and explain why that state changed. Java 21 lets us model those two roles using two complementary tools:

- **`record Order`:** an immutable *snapshot* describing the current state of an order: order ID, item, total amount, state, version/sequence, and tracking code if any.
- **`sealed interface OrderEvent`:** the set of event types owned by the domain, for example `OrderPlaced`, `PaymentCaptured`, `ParcelShipped`, and `OrderCancelled`. Each subtype is a record holding the event's own data.
- **Pattern matching for `switch`:** classifies each event, extracts components with a record pattern, checks business rules, and produces a **new Order** instead of mutating the old snapshot directly.

Data flow idea:

```text
OrderPlaced(id, item, seq=1)  ──>  Order(state=PLACED, seq=1)
PaymentCaptured(id, seq=2)    ──>  Order(state=PAID, seq=2)
ParcelShipped(id, code, seq=3)──>  Order(state=SHIPPED, seq=3)
```

In the diagram above, the arrow represents **applying a valid event to a snapshot** to produce the next snapshot. This is a small illustrative **event projector/reducer**; it is not a full event sourcing system yet.

**Important distinction:** `CapturePayment` (command) is a request to capture payment and may fail; `PaymentCaptured` (event) asserts that payment capture has already occurred according to a trusted event source. Therefore, the `apply` function in this lesson **does not call a payment gateway, does not ship parcels, and does not write to a database**. It only updates the state representation from accepted events.

The learning goal is to combine **record + sealed hierarchy + record pattern + state transition** properly while preserving data integrity and handling invalid cases.

## 2. Designing Immutable Order Data

A record can represent an item:

```java
record Item(String sku, int quantity, long unitPriceCents) {
    long subtotalCents() {
        return Math.multiplyExact((long) quantity, unitPriceCents);
    }
}
```

This is an illustrative declaration without constructor validation yet. `sku` is the item code; `quantity` is the quantity; `unitPriceCents` represents the price in the smallest currency unit (for example, cents) rather than using `double` to add money.

Choosing `long` instead of `double` for this currency example avoids certain binary floating-point inaccuracies when adding integer amounts in the smallest unit. It does **not** by itself solve multi-currency handling, tax rounding, exchange rates, or `long` overflow. For complex financial systems, `BigDecimal`, currency, and rounding rules may need to be modeled explicitly.

Order state:

```java
enum State {
    PLACED, PAID, SHIPPED, CANCELLED
}
```

Snapshot:

```java
record Order(
        String id,
        Item item,
        State state,
        long totalCents,
        long sequence,
        String trackingCode) {}
```

An `Order` object represents **one specific state**. When the next event arrives, the program creates a new `Order` with updated components.

Example logic for transitioning from `PLACED` to `PAID`:

```java
Order paid = new Order(
        previous.id(),
        previous.item(),
        State.PAID,
        previous.totalCents(),
        nextSequence,
        null);
```

This is an illustrative snippet: it assumes `previous` already exists, `nextSequence` is valid, and the types are declared. Records do not have automatic setters; data changes are represented by **new values**.

### Immutability Does Not Mean "Everything Inside Is Immutable"

A record's component fields are `final`, but a reference component can still point to a **mutable object**. In this lesson, `Item` is also a record containing only `String` and primitive types, so the data model is easy to keep stable. If an `Order` contains a `List<MutableItem>`, using a record alone **is not enough to guarantee deep immutability**; defensive copies and/or immutable objects are required.

### Domain-Managed States

The case study defines:

- `PLACED`: order created, payment not yet confirmed.
- `PAID`: payment recorded.
- `SHIPPED`: handed over to the carrier; has a tracking code.
- `CANCELLED`: cancelled before shipping.

Whether cancellation after payment is allowed is a business decision. This lesson **allows cancellation in PLACED or PAID**, but not after SHIPPED. If the domain requires a refund when cancelling a paid order, the refund process is behavior outside the projector and must have its own command/event; merely changing the enum to CANCELLED does not mean the money has been refunded.

## 3. Sealed Events Define the Allowed Variants

The system has four event types:

```java
sealed interface OrderEvent
        permits OrderPlaced, PaymentCaptured,
                ParcelShipped, OrderCancelled {}

record OrderPlaced(String orderId, Item item, long sequence)
        implements OrderEvent {}

record PaymentCaptured(String orderId, long sequence)
        implements OrderEvent {}

record ParcelShipped(
        String orderId, String trackingCode, long sequence)
        implements OrderEvent {}

record OrderCancelled(
        String orderId, String reason, long sequence)
        implements OrderEvent {}
```

These are illustrative declarations. The full program in section 8 adds validation to each event.

**Why is `sealed interface` useful here?**

1. The module owning the domain **explicitly lists the permitted direct subtypes**.
2. Direct implementing records are `final`, so the set of event shapes in the example is controlled.
3. A `switch expression` over `OrderEvent` can be checked for **exhaustiveness** by the Java 21 compiler: if a new subtype is added without handling it, the compiler can report a missing case on recompilation.
4. Because each event is a distinct record, `ParcelShipped` must carry a tracking code, while `PaymentCaptured` does not need a generic record cluttered with unrelated optional fields.

In a named module, permitted direct subtypes must be in the **same module**; in an unnamed module, they must be in the **same package** as the sealed interface. Nesting the record types inside the same class as a standalone example also suits instructional purposes.

**This does not mean sealed events automatically guarantee every event is genuine.** The Java type system does not verify signatures, event origin, business timestamp, or sender permissions. If events come from an untrusted source, a boundary is needed to validate them before feeding them into the projector.

### Why Is `sequence` in Every Event?

`sequence` represents the expected order **within the same order**. In this simple model:

- The first event must have sequence `1`.
- The next event must have sequence equal to `current.sequence() + 1`.
- An event belonging to a different order must not be applied to the current snapshot.

This rule helps detect **missing events, out-of-order events, duplicate sequences, or mixed-up orders**. It does not by itself provide distributed locking or guarantee exactly-once delivery.

## 4. Record Patterns Deconstruct Events Directly in `switch`

Starting in Java 21, pattern matching for `switch` can be used to apply events:

```java
static Order apply(Order current, OrderEvent event) {
    return switch (event) {
        case OrderPlaced(var id, var item, long seq)
                when current == null -> {
            // Check the initial seq, then create a PLACED Order.
            yield createSnapshot(id, item, seq);
        }

        case OrderPlaced placed ->
                throw new IllegalStateException(
                        "Order already exists: " + placed.orderId());

        case PaymentCaptured(var id, long seq) ->
                applyPayment(current, id, seq);

        case ParcelShipped(var id, var tracking, long seq) ->
                applyShipment(current, id, tracking, seq);

        case OrderCancelled(var id, var reason, long seq) ->
                applyCancellation(current, id, reason, seq);

        case null ->
                throw new IllegalArgumentException(
                        "event must not be null");
    };
}
```

This is a **structural illustrative example**, not a standalone compilable method: `createSnapshot`, `applyPayment`, `applyShipment`, and `applyCancellation` are explanatory placeholders. Section 8 provides a complete version without those hypothetical helper functions.

Java rules to observe:

- `OrderPlaced(var id, var item, long seq)` is a **record pattern**. `var` infers the component type from the record declaration; `seq` has type `long`.
- `when current == null` is the **guard** of the first case. A guard is evaluated **only after the record pattern matches**.
- When `current != null`, the first guard is false, so the next `OrderPlaced placed` case handles duplicate order creation.
- The broader `OrderPlaced placed` case must come **after** the guarded case; reversing the order causes a *dominated case* compile error.
- Each of `PaymentCaptured`, `ParcelShipped`, and `OrderCancelled` has its own state transition logic, avoiding lumping events into an ambiguous `default`.
- `case null` defines a null event as an input error. A `default` is not a substitute for an explicit null policy.
- In a `switch expression`, a block case needs `yield` to supply a value; `throw` can complete a branch with an exception.

### Flow Scope of Pattern Variables

The variables `id` and `seq` bound by the `PaymentCaptured` case **do not exist** in the `ParcelShipped` branch. Same-named variables in another case are **different pattern variables**. Java checks scope according to the matching flow, so data from one event cannot be used in a branch where it did not match.

## 5. State Transition Rules: Handling Events Meaningfully

The table below is the contract of the projector in this lesson:

| Event | Previous Snapshot | Next Snapshot | Required Conditions |
| --- | --- | --- | --- |
| `OrderPlaced` | None (`null`) | `PLACED` | `sequence = 1`, valid item |
| `PaymentCaptured` | `PLACED` | `PAID` | Matching orderId, next sequence |
| `ParcelShipped` | `PAID` | `SHIPPED` | Valid tracking code, matching orderId/sequence |
| `OrderCancelled` | `PLACED` | `CANCELLED` | Valid reason, matching orderId/sequence |
| `OrderCancelled` | `PAID` | `CANCELLED` | Valid reason, matching orderId/sequence |
| `OrderCancelled` | `SHIPPED` | Rejected | Cancellation not allowed after shipping |
| Second `PaymentCaptured` | `PAID` or later | Rejected | Do not arbitrarily transition back to PAID |
| `ParcelShipped` before payment | `PLACED` | Rejected | Missing PAID step |
| Any event other than `OrderPlaced` when no order exists | `null` | Rejected | Missing initial creation event |

We must distinguish **two types of errors**:

1. **Ordering/partitioning error:** wrong `orderId`, missing sequence, duplicate sequence, or an event arriving before the creation event.
2. **State transition error:** the event has the right ID and sequence, but is invalid for the current state, such as `ParcelShipped` before payment.

Neither should silently turn into "ignore the event" if the domain requires data to be applied strictly. If a system needs replay to skip duplicates, that must be an **explicit idempotency policy**, not an arbitrary `default -> current`.

### Why Check `orderId`?

If `PaymentCaptured("O-9", 2)` is accidentally fed into the snapshot of order `O-7`, the sequence might still match, yet the data **belongs to a different order**. Checking only the sequence is not enough. The `requireNext` method in the full example checks both ID and sequence before checking/transitioning state.

### Do Not Mutate When a Transition Fails

In this lesson, every snapshot is a record; `apply` creates a new `Order` **only after** validating the conditions. If applying an event throws an exception, the old snapshot object remains unchanged.

This is an advantage of writing an immutable reducer within a single process. It **does not guarantee** that external side effects (DB writes, sending emails, processing payments) will automatically roll back on error. Those operations must be managed at another layer with appropriate transactions and consistency mechanisms.

## 6. Nested Record Patterns: Reading `Order` and `Item` for Display

Record patterns are not limited to events. We can directly deconstruct a snapshot containing a nested record:

```java
static String summary(Object value) {
    return switch (value) {
        case Order(
                var id,
                Item(var sku, var quantity, var unitPriceCents),
                var state,
                var totalCents,
                var sequence,
                var trackingCode) ->
                id + " " + sku + "x" + quantity
                        + " " + state
                        + " total=" + totalCents
                        + " seq=" + sequence
                        + (trackingCode == null
                                ? ""
                                : " tracking=" + trackingCode);

        case null -> "NO_ORDER";
        default -> "UNSUPPORTED_ORDER";
    };
}
```

This is a complete Java 21 method **when the records are declared in the same context**. It demonstrates:

- The outer pattern matches `Order`; the nested pattern `Item(var sku, var quantity, var unitPriceCents)` matches the item record.
- Components are bound with concrete inferred types; `quantity` is `int`, `unitPriceCents` is `long`.
- `trackingCode` may be `null` in unshipped states; because `var` is used, the code checks for null before concatenating.
- If the input is not an `Order`, `default` returns a result indicating an unsupported type. This is intentional because the parameter here is `Object`, **not** a closed sealed hierarchy.

This is a **state-to-display-string transformation**, kept separate from `apply`. Keeping state projection logic and display logic in separate places prevents the domain from depending on a specific screen's formatting.

**Note on nested null:** If the `item` component of an `Order` were `null`, the nested pattern `Item(...)` would not match. In the full program, the `Order` constructor disallows a null item, so validly constructed snapshots never hit this case. A record pattern is not a replacement for object validation.

## 7. Validation at the Record and at the Boundary

A record compact constructor is the right place to validate the **intrinsic invariants** of an event:

```java
record OrderCancelled(
        String orderId, String reason, long sequence)
        implements OrderEvent {
    OrderCancelled {
        requireNonBlank(orderId, "orderId");
        requireNonBlank(reason, "reason");
        if (sequence <= 0) {
            throw new IllegalArgumentException(
                    "sequence must be positive");
        }
    }
}
```

The illustrative snippet above assumes `OrderEvent` and `requireNonBlank` are already declared. When creating `new OrderCancelled("O-7", " ", 4)`, the constructor rejects a blank reason instead of producing an event the projector cannot make sense of.

Distinguish three levels of checks:

1. **In the event constructor:** non-blank order ID, required data present, positive sequence, non-blank tracking code/reason.
2. **In the reducer/projector:** whether the event belongs to the right order, whether the sequence is consecutive, and whether the previous state allows that event.
3. **At the boundary/event-producing system:** source identity, permissions, actual payment outcome, data schema, version, and signature/trusted source.

A sealed interface restricts declared subtypes in Java, but does not verify that a business event actually occurred. Conversely, validation does not prove that the event was durably written to a log.

### Money Validation Principles

For an `Item` with `quantity` and `unitPriceCents`, we should check:

- `sku` is non-blank.
- `quantity > 0`.
- `unitPriceCents >= 0` if the domain allows free items; forbid negative prices if negatives do not represent discounts.
- The product of quantity and unit price **does not overflow `long`**, for example via `Math.multiplyExact`.

Shipping fees, discounts, and taxes are separate concerns requiring explicit total-calculation rules. Do not assume `quantity * unitPrice` alone suffices for all production invoices.

## 8. Standalone Runnable Java 21 Program

Create the file **`OrderRecordSealedEventDemo.java`** with the following content. The program requires JDK 21 or later, with no preview features or external libraries.

```java
import java.util.List;
import java.util.Objects;

public class OrderRecordSealedEventDemo {
    enum State {
        PLACED, PAID, SHIPPED, CANCELLED
    }

    static void requireNonBlank(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    field + " must not be blank");
        }
    }

    static void checkEventMeta(String orderId, long sequence) {
        requireNonBlank(orderId, "orderId");
        if (sequence <= 0) {
            throw new IllegalArgumentException(
                    "sequence must be positive");
        }
    }

    record Item(String sku, int quantity, long unitPriceCents) {
        Item {
            requireNonBlank(sku, "sku");
            if (quantity <= 0) {
                throw new IllegalArgumentException(
                        "quantity must be positive");
            }
            if (unitPriceCents < 0) {
                throw new IllegalArgumentException(
                        "unitPriceCents must not be negative");
            }
            Math.multiplyExact((long) quantity, unitPriceCents);
        }

        long subtotalCents() {
            return Math.multiplyExact(
                    (long) quantity, unitPriceCents);
        }
    }

    record Order(
            String id,
            Item item,
            State state,
            long totalCents,
            long sequence,
            String trackingCode) {
        Order {
            requireNonBlank(id, "orderId");
            Objects.requireNonNull(item, "item");
            Objects.requireNonNull(state, "state");

            if (sequence <= 0) {
                throw new IllegalArgumentException(
                        "sequence must be positive");
            }
            if (totalCents != item.subtotalCents()) {
                throw new IllegalArgumentException(
                        "total does not match item");
            }
            if (state == State.SHIPPED) {
                requireNonBlank(trackingCode, "trackingCode");
            } else if (trackingCode != null) {
                throw new IllegalArgumentException(
                        "trackingCode only allowed for SHIPPED");
            }
        }
    }

    sealed interface OrderEvent
            permits OrderPlaced, PaymentCaptured,
                    ParcelShipped, OrderCancelled {}

    record OrderPlaced(
            String orderId, Item item, long sequence)
            implements OrderEvent {
        OrderPlaced {
            checkEventMeta(orderId, sequence);
            Objects.requireNonNull(item, "item");
        }
    }

    record PaymentCaptured(String orderId, long sequence)
            implements OrderEvent {
        PaymentCaptured {
            checkEventMeta(orderId, sequence);
        }
    }

    record ParcelShipped(
            String orderId, String trackingCode, long sequence)
            implements OrderEvent {
        ParcelShipped {
            checkEventMeta(orderId, sequence);
            requireNonBlank(trackingCode, "trackingCode");
        }
    }

    record OrderCancelled(
            String orderId, String reason, long sequence)
            implements OrderEvent {
        OrderCancelled {
            checkEventMeta(orderId, sequence);
            requireNonBlank(reason, "reason");
        }
    }

    static Order requireNext(
            Order current, String orderId, long sequence) {
        if (current == null) {
            throw new IllegalStateException(
                    "Order not initialized: " + orderId);
        }
        if (!current.id().equals(orderId)) {
            throw new IllegalArgumentException(
                    "Event belongs to different order: " + orderId);
        }
        if (sequence != Math.addExact(current.sequence(), 1L)) {
            throw new IllegalStateException(
                    "Unexpected event sequence: " + sequence);
        }
        return current;
    }

    static Order apply(Order current, OrderEvent event) {
        return switch (event) {
            case OrderPlaced(var id, var item, long seq)
                    when current == null -> {
                if (seq != 1L) {
                    throw new IllegalStateException(
                            "First event sequence must be 1");
                }
                yield new Order(
                        id, item, State.PLACED,
                        item.subtotalCents(), seq, null);
            }

            case OrderPlaced placed ->
                    throw new IllegalStateException(
                            "Order already exists: " + placed.orderId());

            case PaymentCaptured(var id, long seq) -> {
                Order old = requireNext(current, id, seq);
                if (old.state() != State.PLACED) {
                    throw new IllegalStateException(
                            "Cannot pay order in state: " + old.state());
                }
                yield new Order(
                        old.id(), old.item(), State.PAID,
                        old.totalCents(), seq, null);
            }

            case ParcelShipped(var id, var tracking, long seq) -> {
                Order old = requireNext(current, id, seq);
                if (old.state() != State.PAID) {
                    throw new IllegalStateException(
                            "Cannot ship order in state: " + old.state());
                }
                yield new Order(
                        old.id(), old.item(), State.SHIPPED,
                        old.totalCents(), seq, tracking);
            }

            case OrderCancelled(var id, var reason, long seq) -> {
                Order old = requireNext(current, id, seq);
                if (old.state() != State.PLACED
                        && old.state() != State.PAID) {
                    throw new IllegalStateException(
                            "Cannot cancel order in state: "
                                    + old.state());
                }
                yield new Order(
                        old.id(), old.item(), State.CANCELLED,
                        old.totalCents(), seq, null);
            }

            case null ->
                    throw new IllegalArgumentException(
                            "event must not be null");
        };
    }

    // Replay a sequence of trusted and ordered events.
    static Order replay(List<? extends OrderEvent> events) {
        Order current = null;
        for (OrderEvent event : events) {
            current = apply(current, event);
        }
        return current;
    }

    // Nested record pattern: Order contains an Item record.
    static String summary(Object value) {
        return switch (value) {
            case Order(
                    var id,
                    Item(var sku, var quantity, var unitPriceCents),
                    var state,
                    var totalCents,
                    var sequence,
                    var trackingCode) ->
                    id + " " + sku + "x" + quantity
                            + " " + state
                            + " total=" + totalCents
                            + " seq=" + sequence
                            + (trackingCode == null
                                    ? ""
                                    : " tracking=" + trackingCode);

            case null -> "NO_ORDER";
            default -> "UNSUPPORTED_ORDER";
        };
    }

    static void expectFailure(String name, Runnable action) {
        try {
            action.run();
            System.out.println(name + " -> UNEXPECTED_SUCCESS");
        } catch (RuntimeException ex) {
            System.out.println(
                    name + " -> "
                            + ex.getClass().getSimpleName()
                            + ": " + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        Order placed = apply(null,
                new OrderPlaced("O-7",
                        new Item("BOOK", 2, 1500L), 1));
        Order paid = apply(placed,
                new PaymentCaptured("O-7", 2));
        Order shipped = apply(paid,
                new ParcelShipped("O-7", "TR-9", 3));

        System.out.println("placed -> " + summary(placed));
        System.out.println("paid -> " + summary(paid));
        System.out.println("shipped -> " + summary(shipped));

        Order cancelled = apply(
                apply(null, new OrderPlaced(
                        "O-8", new Item("PEN", 1, 200L), 1)),
                new OrderCancelled("O-8", "Changed mind", 2));
        System.out.println("cancelled -> " + summary(cancelled));

        Order replayed = replay(List.of(
                new OrderPlaced("O-7",
                        new Item("BOOK", 2, 1500L), 1),
                new PaymentCaptured("O-7", 2),
                new ParcelShipped("O-7", "TR-9", 3)));
        System.out.println("replay-equal -> "
                + shipped.equals(replayed));

        expectFailure("wrong-sequence",
                () -> apply(paid,
                        new ParcelShipped("O-7", "TR-9", 4)));

        expectFailure("cancel-shipped",
                () -> apply(shipped,
                        new OrderCancelled("O-7", "Too late", 4)));

        expectFailure("wrong-order",
                () -> apply(shipped,
                        new PaymentCaptured("O-9", 4)));

        expectFailure("repeat-paid",
                () -> apply(paid,
                        new PaymentCaptured("O-7", 2)));

        expectFailure("missing-place",
                () -> apply(null,
                        new PaymentCaptured("O-7", 1)));

        expectFailure("null-event",
                () -> apply(shipped, null));

        expectFailure("invalid-item",
                () -> new Item(" ", 2, 100L));

        expectFailure("overflow",
                () -> new Item(
                        "BULK", Integer.MAX_VALUE, Long.MAX_VALUE));
    }
}
```

Compile and run:

```bash
javac --release 21 -encoding UTF-8 OrderRecordSealedEventDemo.java
java OrderRecordSealedEventDemo
```

**Expected standard output, in exact order:**

```text
placed -> O-7 BOOKx2 PLACED total=3000 seq=1
paid -> O-7 BOOKx2 PAID total=3000 seq=2
shipped -> O-7 BOOKx2 SHIPPED total=3000 seq=3 tracking=TR-9
cancelled -> O-8 PENx1 CANCELLED total=200 seq=2
replay-equal -> true
wrong-sequence -> IllegalStateException: Unexpected event sequence: 4
cancel-shipped -> IllegalStateException: Cannot cancel order in state: SHIPPED
wrong-order -> IllegalArgumentException: Event belongs to different order: O-9
repeat-paid -> IllegalStateException: Unexpected event sequence: 2
missing-place -> IllegalStateException: Order not initialized: O-7
null-event -> IllegalArgumentException: event must not be null
invalid-item -> IllegalArgumentException: sku must not be blank
overflow -> ArithmeticException: long overflow
```

### Reading the Output Step by Step

1. **`placed`** is created from the first `OrderPlaced`; total amount `2 × 1500 = 3000` cents, state `PLACED`, sequence `1`.
2. **`paid`** is created from the `placed` snapshot and `PaymentCaptured` with sequence `2`. It preserves id/item/total, updating only state and sequence. `placed` remains the old object in the PLACED state.
3. **`shipped`** receives `ParcelShipped` with sequence `3`; it requires the prior state to be PAID and a tracking code `TR-9`, then produces a SHIPPED snapshot.
4. **`cancelled`** is an independent branch for order `O-8`, created and cancelled before payment; state is CANCELLED, total remains `200` because the projector does not infer refunds on its own.
5. **`replay-equal -> true`**: replaying the same events in order produces a record snapshot with equal components. This illustrates the *determinism* of the reducer for the same input; it does not prove a distributed system has exactly-once processing.
6. **`wrong-sequence`** uses event sequence `4` on a snapshot at sequence `2`, whereas the next sequence must be `3`. The event is rejected and no invalid snapshot is created.
7. **`cancel-shipped`** has a valid sequence and orderId, but the SHIPPED state cannot be cancelled according to the contract; this is a **state transition error**, not an ordering error.
8. **`wrong-order`** tries to apply an event for `O-9` onto snapshot `O-7`, and is rejected immediately upon checking `orderId`.
9. **`repeat-paid`** has an old sequence `2` and is therefore rejected. If the same event is redelivered under an intentional idempotency mechanism, production handling may differ; this program only illustrates a strict policy.
10. **`missing-place`** attempts to accept `PaymentCaptured` without an `OrderPlaced`; an order snapshot cannot be inferred from a standalone payment event.
11. **`null-event`** hits `case null` and throws `IllegalArgumentException`, rather than silently ignoring the event.
12. **`invalid-item`** creates a SKU containing only whitespace, which is rejected by the `Item` constructor.
13. **`overflow`** attempts to multiply two large positive numbers exceeding `long` range, causing `Math.multiplyExact` to throw `ArithmeticException` instead of producing an incorrect amount.

The `expectFailure` method only **prints expected exceptions for learning and manual testing**. It does not turn a failed event application into a success. In a real application, errors must be translated into appropriate results at the processing boundary or routed to observability/recovery channels, rather than always catching everything and continuing as if nothing happened.

## 9. Key Java 21 Mechanisms in the Program

### 9.1. Sealed Hierarchy + Exhaustive `switch`

`apply` has cases for all four subtypes plus a null selector. Because `OrderEvent` is sealed and its direct subtypes are `final` records, Java 21 can check exhaustiveness across all valid **types**. It avoids using `default -> current` to hide a missing event handler.

If we add:

```java
record OrderRefunded(String orderId, long sequence)
        implements OrderEvent {}
```

we must update `permits OrderEvent` and the reducer policy. For an exhaustive `switch expression` without `default`, the compiler can report a **missing case** on recompilation. This is a way to catch code that does not yet understand the new event, rather than a reason to add `default` indiscriminately.

### 9.2. Guard True/False and Case Ordering

Two cases for `OrderPlaced`:

```java
case OrderPlaced(var id, var item, long seq)
        when current == null -> {
    // Create the initial snapshot.
    yield new Order(
            id, item, State.PLACED, item.subtotalCents(), seq, null);
}
case OrderPlaced placed ->
        throw new IllegalStateException("Order already exists");
```

This is an **illustrative excerpt** of the `switch`, omitting the sequence check to focus on explaining the guard. `when current == null` is true only when no snapshot exists yet. When the guard is false, the subsequent case can match and report a duplicate creation error. If the broader case were placed first, the guarded case would be *dominated* and would fail to compile.

### 9.3. Record Patterns and Nested Record Patterns

In `summary`, the pattern:

```java
case Order(
        var id,
        Item(var sku, var quantity, var unitPriceCents),
        var state,
        var totalCents,
        var sequence,
        var trackingCode) -> ...
```

directly reads the structure of an `Order` containing an `Item`. A record pattern is evaluated by retrieving components via accessors to bind typed variables, not by constructing a new record. For inputs that are not `Order`, the display method meaningfully uses `default` because it accepts `Object`.

### 9.4. Null and Flow Scope

- `case null` in `apply` is the policy that **a null event is invalid**.
- `trackingCode` can be null in PLACED/PAID/CANCELLED states; `var trackingCode` can bind null and must be handled explicitly before access.
- `Item(var sku,...)` does not match if the `item` component itself is null. The `Order` constructor rejects that case.
- Variables `id` and `seq` in an event case cannot be referenced outside the scope of the matched case.

### 9.5. Record Value Semantics and Replay

Records provide component-based `equals`/`hashCode` according to the record contract. Because the components in the example are records, an enum, `String`, and primitives, comparing reconstructed snapshots has a clear meaning. However, equal snapshots **do not prove** that an event log system is not missing intermediate events if the data lacks proper sequences/identifiers; additional domain and storage checks are required.

## 10. Event Replay: Ordered, Not Automatically Exactly-Once

The method:

```java
static Order replay(List<? extends OrderEvent> events) {
    Order current = null;
    for (OrderEvent event : events) {
        current = apply(current, event);
    }
    return current;
}
```

has an important property: the same valid sequence of events in order, with the same pure reducer logic, produces the same snapshot by components (assuming no time-varying external inputs).

**What this replay does not solve yet:**

- **Durability:** an in-memory `List` is not a durably persisted event log.
- **Concurrency:** two events for the same order need serialization and/or an atomic version check when writing to the log.
- **Idempotency:** duplicate events may trigger sequence errors; a real system needs to know when skipping a duplicate is valid and how to prove it is the **exact same already-processed event**, not a different event reusing the same sequence.
- **Exactly-once side effects:** a replaying consumer could re-send emails or re-charge payments if the reducer mixes side effects with state logic. Separating a pure projector from external operations is an important design principle.
- **Editing or deleting events:** an event log is typically append-only; business reversals are modeled with new events, not by arbitrarily mutating historical events.
- **Schema evolution:** older event payloads may need conversion/translation to stay compatible with newer models.

### Sequence Is Not a Complete Idempotency Key

A `sequence` defines the expected order on an order. In a message broker environment, if a consumer receives the **same event** again, it may want to return the previous result; however, simply checking `sequence <= current.sequence()` and ignoring all older events is dangerous, because it can mask replaying the wrong event or data conflicts.

A production design may need an immutable `eventId`, a unique constraint, idempotency/result mapping, and payload/hash verification when the same ID appears again. The demo intentionally **throws an error when sequences are not consecutive** to expose ordering errors rather than guessing that an event is a safe duplicate.

### When Multiple Orders Exist

In practice, each event belongs to an aggregate/order. We need to route by `orderId` to apply it to the corresponding snapshot—for example, using a map `orderId → Order` or a database partitioned by ID. A single `current` variable should not be used for the entire system. The demo program uses `O-7` and `O-8` as two independent streams to illustrate this point.

## 11. Testing State Transitions with a Scenario Matrix

When combining records and sealed events, test both **data shapes** and **business rules**:

| Test Case | Event / Prior Snapshot | Expected Outcome |
| --- | --- | --- |
| Place initial order | `OrderPlaced` seq=1, current=null | PLACED snapshot, correct total. |
| Place order with seq != 1 | `OrderPlaced` seq=2, current=null | `IllegalStateException`. |
| Valid payment | `PaymentCaptured` seq=2 after PLACED seq=1 | PAID, item and total preserved. |
| Second payment | `PaymentCaptured` when state is PAID | Rejected; may be state or sequence error depending on data. |
| Ship before payment | `ParcelShipped` after PLACED | State transition rejected. |
| Ship after payment | `ParcelShipped` after PAID | SHIPPED, with tracking. |
| Cancel after placement | `OrderCancelled` after PLACED | CANCELLED. |
| Cancel after payment | `OrderCancelled` after PAID | CANCELLED per case study policy. |
| Cancel after shipping | `OrderCancelled` after SHIPPED | `IllegalStateException`. |
| Wrong orderId event | Event `O-9` applied to `O-7` | `IllegalArgumentException`. |
| Skipped sequence | Receiving seq=4 after seq=2 | `IllegalStateException`. |
| Non-OrderPlaced when current=null | `PaymentCaptured` seq=1 | `IllegalStateException`. |
| Null event | `apply(current, null)` | `IllegalArgumentException`. |
| Blank SKU or quantity <= 0 | Creating `Item` | `IllegalArgumentException`. |
| Amount product overflows `long` | Item with huge price and quantity | `ArithmeticException`. |
| Valid replay | Same event sequence and initial snapshot | Final snapshots have equal components. |

**Do not only test exceptions:** When an event is rejected, verify that the prior snapshot remains unchanged and no external side effects occurred. This is especially important if in production the handler is wired to storage or a message broker.

### JUnit Jupiter Unit Test Example

The illustrative test file below assumes `OrderRecordSealedEventDemo` is in the same package and the project is configured with **JUnit Jupiter**. It **does not** run with standalone `javac` when the test library is absent.

```java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class OrderRecordSealedEventDemoTest {
    @Test
    void placedThenPaid() {
        var item = new OrderRecordSealedEventDemo.Item(
                "BOOK", 2, 1500L);
        var placed = OrderRecordSealedEventDemo.apply(
                null,
                new OrderRecordSealedEventDemo.OrderPlaced(
                        "O-7", item, 1));
        var paid = OrderRecordSealedEventDemo.apply(
                placed,
                new OrderRecordSealedEventDemo.PaymentCaptured(
                        "O-7", 2));

        assertEquals(OrderRecordSealedEventDemo.State.PLACED,
                placed.state());
        assertEquals(OrderRecordSealedEventDemo.State.PAID,
                paid.state());
        assertEquals(3000L, paid.totalCents());
        assertEquals(1L, placed.sequence());
        assertEquals(2L, paid.sequence());
    }

    @Test
    void cannotShipBeforePayment() {
        var placed = OrderRecordSealedEventDemo.apply(
                null,
                new OrderRecordSealedEventDemo.OrderPlaced(
                        "O-1",
                        new OrderRecordSealedEventDemo.Item(
                                "PEN", 1, 200L),
                        1));
        assertThrows(IllegalStateException.class,
                () -> OrderRecordSealedEventDemo.apply(
                        placed,
                        new OrderRecordSealedEventDemo.ParcelShipped(
                                "O-1", "TR-1", 2)));
        assertEquals(OrderRecordSealedEventDemo.State.PLACED,
                placed.state());
    }

    @Test
    void rejectsDifferentOrderId() {
        var placed = OrderRecordSealedEventDemo.apply(
                null,
                new OrderRecordSealedEventDemo.OrderPlaced(
                        "O-1",
                        new OrderRecordSealedEventDemo.Item(
                                "PEN", 1, 200L),
                        1));
        assertThrows(IllegalArgumentException.class,
                () -> OrderRecordSealedEventDemo.apply(
                        placed,
                        new OrderRecordSealedEventDemo.PaymentCaptured(
                                "O-2", 2)));
    }
}
```

For production tests, add checks for null/blank inputs, wrong ordering, cancellation from each state, overflow, duplicates, replayability, and adding new subtypes. When new commands, events, or states appear, update event consumers as well—not only the main projector.

## 12. Adding a New Event Without Hiding Errors Using `default`

Suppose the domain adds `OrderRefunded`. The changes include at least:

1. Define the **business meaning**: full or partial refund, from which states, ordering relative to cancellation, currency, and amount.
2. Add the record with required components and validation.
3. Add the direct subtype to `permits OrderEvent`.
4. Recompile `switch expression`s to find missing handlers.
5. Add dedicated state transitions or projections; do not treat `OrderRefunded` as `OrderCancelled` if the two events mean different things.
6. Update message schemas, serializers/deserializers, auditing, event consumers, and replay.
7. Add regression tests for both old and new flows.

Do not fix the compiler error with:

```java
// Anti-pattern: silently ignore the new event.
default -> current;
```

This is an illustrative branch snippet, not a standalone runnable file. If a new event is unsupported, a meaningful error or explicit versioning mechanism is usually better than ignoring an important event. In an open interface for plugins, a catch-all branch may fit, but a closed sealed hierarchy helps catch missing handlers earlier.

### Adding a Field to a Record Is a Contract Change

When modifying `record OrderPlaced(...)` to add `currency` or `eventId`, constructors, accessors, record patterns, and payload formats can all be affected. Do not assume all historical events will deserialize automatically and preserve their meaning. For systems with long-lived event logs, **schema/version migration** or an adapter layer at the boundary is required.

## 13. Event Sourcing and Production Reality

The case study describes an **in-memory** reducer and replay function. A complete event sourcing solution must also address:

- **Durable event store:** append by aggregate ID, sequence/version, and control concurrent writes.
- **Snapshot persistence:** store snapshots to speed up replay when logs grow long; snapshots carry a version so events are not misapplied.
- **Concurrency control:** optimistic locking/expected version, transactions/unique constraints, or per-aggregate serialization.
- **Message delivery:** at-least-once delivery and idempotent consumers are common; do not promise exactly-once across the entire system.
- **Outbox/inbox:** synchronize transactions storing business state/events with message publishing and duplicate handling.
- **Schema evolution:** read old events, handle new fields, rename types, and test compatibility with deployed consumers.
- **Security:** protect event sources and sensitive data; record patterns do not check permissions or authenticity.
- **Observability:** logs/metrics by event type, aggregate ID, sequence, projector errors, and unsupported cases, while avoiding leaking personal payment details.
- **Time conditions:** event time and processing time are distinct concepts; use timestamps from trusted sources when required by business logic.

**Do not put side effects inside the reducer if you want safe replay.** For example, the `PaymentCaptured` case in `apply` must not call a payment API, because replaying the event would trigger payment again. Payment is executed during command handling, which then emits `PaymentCaptured` upon success; the projector only reflects the recorded outcome.

### One Event Does Not Necessarily Change Only a Single Enum

Complex domains may need multiple state attributes: payment, fulfillment, return/refund, fraud review, partial shipment. In such cases, a single simple `State` enum may not suffice. Even while still using sealed events, the snapshot model can contain multiple sub-records or independent states to avoid an explosion of enum values.

As the model grows, bound each aggregate's scope and define clear invariants instead of cramming every event type in the entire enterprise into a single `sealed interface`.

## 14. Common Mistakes When Combining Records and Sealed Events

### Mistake 1: Confusing Events with Commands

`PaymentCaptured` confirms an event that has already occurred. Never use replaying `PaymentCaptured` to invoke an actual payment again. To request payment, use an appropriate command/service.

### Mistake 2: Treating Records as Mutable Objects

Records do not provide setters to mutate components. When applying an event, create a new `Order` snapshot and persist the new version in a controlled way. Do not create global mutable state that defeats the benefits of a reducer.

### Mistake 3: Using `default` to Swallow New Events

`default -> current` lets the log contain a new event while the snapshot stays unchanged, masking a missing branch. With a sealed hierarchy owned by the module, let the compiler enforce handling new subtypes.

### Mistake 4: Checking Only State, Ignoring `orderId`/`sequence`

A `PaymentCaptured` from another order or a skipped-sequence event can still have a valid subtype name. The compiler does not know which aggregate the data belongs to; ID and sequence must be checked.

### Mistake 5: Using Record Patterns as a Substitute for Validation

`case OrderPlaced(var id, var item, long seq)` does not prove `id` is non-blank, `item` was validated at the boundary, or the event truly came from a trusted source. Constructors and business checks are still necessary.

### Mistake 6: Failing to Handle Null Components

The nested pattern `Item(...)` does not match if the `item` component is null. `var trackingCode` can bind null. Read record patterns according to exact null semantics rather than assuming every matched variable is non-null.

### Mistake 7: Leaving `totalCents` Wrong or Vulnerable to Overflow

`long totalCents = quantity * unitPriceCents` can overflow if unchecked. `Math.multiplyExact` detects overflow in the demo; when the domain allows very large values or multiple currencies, proper monetary type design is mandatory.

### Mistake 8: Using `sequence` as an Exactly-Once Mechanism

Checking `seq == current + 1` catches many ordering errors, but is not enough to prove an event was processed exactly once across distributed components. Idempotency keys, durable state, and concurrency control are needed in deployment.

### Mistake 9: Testing Only the Happy Path

A projector may work for `Placed → Paid → Shipped` and still fail on missing, duplicate, out-of-order, wrong-order, or post-shipment cancellation events. Failure paths and snapshot invariants must be tested.

### Mistake 10: Forgetting Historical Event Compatibility

Record patterns match the current Java structure; older JSON/Avro/Protobuf data may have different schemas. A decode/migrate/adapter layer is needed when reading long-lived logs; do not treat runtime type checks as a versioning strategy.

## 15. Design and Review Checklist

1. **Concepts:** Is Order the current snapshot, an event what happened, and a command a request?
2. **Type system:** Does the sealed `OrderEvent` have the right direct subtypes under module ownership?
3. **Data:** Does each event record hold its required components, rather than unrelated/arbitrarily nullable fields?
4. **Validation:** Are there clear validation rules for ID, quantity, price, tracking, reason, and sequence?
5. **State machine:** From which states is each event accepted, and which state does it produce?
6. **Ordering:** Are aggregate ID and expected sequence checked before any transition?
7. **Exhaustiveness:** Does `switch` list concrete events without a `default` faking success?
8. **Null:** Is there an explicit policy for null events and null components?
9. **Immutability:** Does the reducer return a new snapshot without mutating the old one?
10. **Replay:** Are there no external side effects during replay, and is the result deterministic for identical inputs?
11. **Idempotency:** Is duplicate/retry handling based on identity and storage rather than sequence alone?
12. **Concurrency:** Are version checks/transactions/locking in place for concurrent events?
13. **Schema evolution:** How are older events and older consumers handled when adding types/fields?
14. **Tests:** Are happy paths, invalid state transitions, wrong sequences, wrong orderIds, nulls, and overflows tested?
15. **Toolchain:** Is code using record patterns in `switch` compiled with **JDK 21** or later, without unnecessary preview flags?

## 16. Self-Check

**Question 1.** Why are `OrderPlaced` and `PaymentCaptured` two separate records instead of one `GenericEvent(String type, Object data)` record?

**Answer:** Each type has its own structure and meaning. With sealed events, the compiler knows the permitted subtypes; record patterns extract strongly typed components instead of casting from `Object`. A generic payload can still be used at the boundary, but should be decoded/validated into a trusted domain event before being applied.

**Question 2.** The `Order` snapshot is in `PAID` at sequence `2`. If `ParcelShipped("O-7", "TR-9", 4)` arrives, can it ship?

**Answer:** No, per the lesson's contract. The next sequence must be `3`. Rejecting an event of the right type but wrong order is a domain requirement, not something the compiler checks automatically.

**Question 3.** What happens if `OrderCancelled` arrives in the `SHIPPED` state with the right sequence?

**Answer:** The reducer rejects it with `IllegalStateException` because this lesson only allows cancellation from PLACED or PAID. If the business requires returns after shipping, a separate event/state should be designed rather than silently changing SHIPPED to CANCELLED.

**Question 4.** Can `sku` be extracted from `Order` using a nested record pattern without casting `Order` and `Item`?

**Answer:** Yes. `case Order(var id, Item(var sku, var quantity, var unitPriceCents), ...)` combines the type check and deconstruction. However, record patterns still invoke accessors, and nested record matching must handle null components with proper semantics.

**Question 5.** If `OrderRefunded` is added to the sealed hierarchy but the reducer has no case for it yet, what is the best fix?

**Answer:** Define the refund semantics and add the case along with state rules, payload/versioning, and tests; do not use `default -> current` to ignore the new event.

**Question 6.** What does `replay-equal -> true` prove, and what does it not prove?

**Answer:** It proves that the example reducer produces snapshots with equal components from the same valid event sequence. It does **not** prove that events were durably stored, that there are no duplicate retries, no concurrency races, or exactly-once external side effects.

## 17. References and Summary

- **JEP 395 – Records (Java 16):** https://openjdk.org/jeps/395
- **JEP 409 – Sealed Classes (Java 17):** https://openjdk.org/jeps/409
- **JEP 440 – Record Patterns (Java 21):** https://openjdk.org/jeps/440
- **JEP 441 – Pattern Matching for switch (Java 21):** https://openjdk.org/jeps/441
- **Java Language Specification 21 – Patterns (`14.30`):** https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30
- **Oracle Java 21 – Pattern Matching for switch:** https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html

**Key takeaway:** The **`Order` record** is the state snapshot, while **`sealed OrderEvent`** is a controlled set of domain events. **Record patterns + exhaustive `switch`** in Java 21 help implement a readable reducer, catch missing branches when adding events, and separate state logic from presentation data. To use this safely, check **orderId, sequence, state, validation, null, and overflow**; when moving to production, also address **versioning, durable storage, idempotency, transactions, and side effects**.
