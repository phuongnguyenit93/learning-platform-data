# Preserving Domain Invariants and Input Validation When Designing with `sealed` in Java 17

In a *domain model*, there are states and data combinations that **must never be allowed to exist**. For example, a shipped order cannot revert to draft; an order line must have a quantity greater than 0; the shipping timestamp cannot precede the confirmation timestamp; and a cancelled order cannot simultaneously be treated as being shipped.

Java 17 provides `sealed class` and `sealed interface` to **control which subtypes are permitted to exist**. By combining `sealed` with `record`, validating constructors, and state-transition methods, you can express many domain rules directly in program structure. However, `sealed` **only restricts the type hierarchy**: it does not automatically validate field values, prevent invalid state transitions, or replace input validation at system boundaries.

This lesson focuses on how to divide responsibilities among **the set of valid variants**, **per-variant invariants**, **object lifecycle invariants**, and **boundary input validation**, using features standardized in Java 17.

## 1. What Is a Domain Invariant?

An **invariant** is a condition that must hold true at every moment a domain object is considered valid. It differs from a validation check applied only when a user submits form data in a UI.

For an order, we might have the following rules:

| Rule | Invariant category | Appropriate place to enforce |
| --- | --- | --- |
| Status must be one of `Draft`, `Confirmed`, `Shipped`, `Cancelled` | Permitted type set | `sealed interface State` with its permitted subtypes. |
| An order line has a non-blank SKU and quantity greater than 0 | Value invariant | `Line` constructor. |
| Line list is non-empty with no duplicate SKUs | Single-state invariant | Constructors of `Draft`, `Confirmed`, `Shipped`, or a shared validation helper. |
| `Shipped.shippedAt` is not before `confirmedAt` | Multi-field invariant | `Shipped` constructor. |
| Only `Draft` can be confirmed; only `Confirmed` can be shipped | State-transition invariant | Business methods on the `Order` aggregate. |
| State data cannot be mutated internally after creation | Data-ownership invariant | `record` and defensive copies of mutable structures. |
| Incoming API request has valid format, permissions, and business constraints | Boundary and contextual validation | DTOs, application services, and domain model, depending on condition type. |

Key point to remember: **type structure**, **values**, and **state transitions** are three distinct levels of control. No single Java keyword enforces all three.

## 2. `sealed` Closes the Variant Set, Not Data Validity

Consider a simple declaration:

```java
sealed interface OrderState permits Draft, Confirmed, Shipped, Cancelled {}

record Draft(String cartId) implements OrderState {}

record Confirmed(String confirmationId) implements OrderState {}

record Shipped(String trackingCode) implements OrderState {}

record Cancelled(String reason) implements OrderState {}
```

Within a valid declaration scope, any type not listed in `permits` cannot directly implement `OrderState`. For instance, an unpermitted `UnknownState implements OrderState` is rejected by the compiler. The `record` types above are implicitly `final`, so they cannot be subclassed to introduce new variants underneath.

Yet these declarations still allow constructing:

```java
new Draft(null);
new Confirmed("");
new Shipped("   ");
```

These objects have a **valid type** yet **invalid data** if the domain requires non-blank IDs and strings. Thus, `sealed` answers **"Which state kinds exist?"**, whereas constructors/factories answer **"With what data may a specific state be created?"**.

### Direct Inheritance Restrictions and `non-sealed`

Direct subtypes of a `sealed` type must be permitted and must declare their continuation policy as `final`, `sealed`, or `non-sealed`. A `record` is inherently `final`; for other classes or interfaces, you may choose to allow further extension.

```java
sealed interface Event permits KnownEvent, ExtensionEvent {}

record KnownEvent(String id) implements Event {}

non-sealed interface ExtensionEvent extends Event {}
```

`Event` permits only two **direct subtypes**, yet other classes can still implement `ExtensionEvent`. If a design requires a **truly closed variant set**, inspect the entire type tree and avoid unintentionally opening a branch with `non-sealed`.

In Java 17, permitted direct subtypes must be in the **same named module** as the root `sealed` type, or the **same package** if in an unnamed module. Closing a type hierarchy does not create a security boundary: `sealed` does not replace authorization, request authentication, or trust boundaries.

## 3. Designing Order States So Each Variant Holds Only Relevant Data

Suppose an order has the lifecycle:

```text
                confirm                 ship
    Draft  ----------------> Confirmed ---------> Shipped
      |                         |
      | cancel                  | cancel
      v                         v
   Cancelled <------------------+

    Shipped and Cancelled are terminal states.
```

Valid data for each state:

| Variant | Required data | Invariants |
| --- | --- | --- |
| `Draft` | List of order lines | At least one line, unique SKUs, each quantity positive. |
| `Confirmed` | Confirmation ID, confirmation time, list of lines | Non-blank ID, non-`null` timestamp, valid line list. |
| `Shipped` | Confirmation ID, confirmation/shipping times, list of lines | Shipping time not before confirmation time, remaining fields valid. |
| `Cancelled` | Cancellation reason | Non-blank reason. |

This avoids an object shaped like:

```java
// Illustrates a design prone to nonsensical states:
class MutableOrderData {
    boolean shipped;
    boolean cancelled;
    String confirmationId;
    String trackingCode;
    String cancellationReason;
}
```

With independent flags, you can end up with `shipped == true` **and** `cancelled == true`, or `shipped == true` without a shipping timestamp. When states carry different data, a `sealed interface` with separate variants expresses the contract much more clearly.

**However, separating variants only protects structure.** You still need to validate values inside each variant and prevent state changes along invalid paths.

## 4. Complete Example on Java 17

The example below declares an `Order` aggregate keeping its `state` field `private`, with the state variants also encapsulated inside the domain class. Each state's inputs are validated at construction time, and every state change goes through `Order`'s business methods.

Save as `OrderInvariantDemo.java`:

```java
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public final class OrderInvariantDemo {
    private OrderInvariantDemo() {}

    // Shared value object. Records cannot be subclassed.
    public record Line(String sku, int quantity) {
        public Line {
            sku = requireText(sku, "sku");
            if (quantity <= 0) {
                throw new IllegalArgumentException("quantity must be positive");
            }
        }
    }

    // Valid state set under the domain model's control.
    private sealed interface State
            permits Draft, Confirmed, Shipped, Cancelled {
    }

    private record Draft(List<Line> lines) implements State {
        Draft {
            lines = requireLines(lines);
        }
    }

    private record Confirmed(
            String confirmationId,
            Instant confirmedAt,
            List<Line> lines) implements State {

        Confirmed {
            confirmationId = requireText(confirmationId, "confirmationId");
            Objects.requireNonNull(confirmedAt, "confirmedAt");
            lines = requireLines(lines);
        }
    }

    private record Shipped(
            String confirmationId,
            Instant confirmedAt,
            Instant shippedAt,
            List<Line> lines) implements State {

        Shipped {
            confirmationId = requireText(confirmationId, "confirmationId");
            Objects.requireNonNull(confirmedAt, "confirmedAt");
            Objects.requireNonNull(shippedAt, "shippedAt");
            if (shippedAt.isBefore(confirmedAt)) {
                throw new IllegalArgumentException(
                        "shippedAt must not be before confirmedAt");
            }
            lines = requireLines(lines);
        }
    }

    private record Cancelled(String reason) implements State {
        Cancelled {
            reason = requireText(reason, "reason");
        }
    }

    // Aggregate exposes only permitted business operations.
    public static final class Order {
        private State state;

        public Order(List<Line> lines) {
            state = new Draft(lines);
        }

        public void confirm(String confirmationId, Instant confirmedAt) {
            if (!(state instanceof Draft draft)) {
                throw new IllegalStateException("Only Draft can be confirmed");
            }

            // Confirmed's constructor validates data before assigning state.
            state = new Confirmed(confirmationId, confirmedAt, draft.lines());
        }

        public void ship(Instant shippedAt) {
            if (!(state instanceof Confirmed confirmed)) {
                throw new IllegalStateException("Only Confirmed can be shipped");
            }

            state = new Shipped(
                    confirmed.confirmationId(),
                    confirmed.confirmedAt(),
                    shippedAt,
                    confirmed.lines());
        }

        public void cancel(String reason) {
            if (state instanceof Draft || state instanceof Confirmed) {
                state = new Cancelled(reason);
                return;
            }

            throw new IllegalStateException(
                    "Only Draft or Confirmed can be cancelled");
        }

        public String status() {
            if (state instanceof Draft) return "DRAFT";
            if (state instanceof Confirmed) return "CONFIRMED";
            if (state instanceof Shipped) return "SHIPPED";
            if (state instanceof Cancelled) return "CANCELLED";
            throw new IllegalStateException("Unhandled order state");
        }
    }

    private static String requireText(String text, String fieldName) {
        String normalized = Objects.requireNonNull(text, fieldName).strip();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException(fieldName + " must not be blank");
        }
        return normalized;
    }

    private static List<Line> requireLines(List<Line> input) {
        // List.copyOf rejects null elements and creates an unmodifiable copy.
        List<Line> copy = List.copyOf(Objects.requireNonNull(input, "lines"));
        if (copy.isEmpty()) {
            throw new IllegalArgumentException("order must contain at least one line");
        }

        Set<String> seenSkus = new HashSet<>();
        for (Line line : copy) {
            if (!seenSkus.add(line.sku())) {
                throw new IllegalArgumentException("duplicate sku: " + line.sku());
            }
        }
        return copy;
    }

    public static void main(String[] args) {
        List<Line> external = new ArrayList<>();
        external.add(new Line(" BOOK-17 ", 2));

        Order order = new Order(external);
        external.clear(); // Cannot empty the list held inside Draft.
        System.out.println(order.status()); // DRAFT

        order.confirm("CONF-100", Instant.parse("2026-02-01T10:00:00Z"));
        System.out.println(order.status()); // CONFIRMED

        order.ship(Instant.parse("2026-02-02T10:00:00Z"));
        System.out.println(order.status()); // SHIPPED

        try {
            order.cancel("Change of mind");
        } catch (IllegalStateException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
```

Compile and run with JDK 17:

```bash
javac --release 17 OrderInvariantDemo.java
java OrderInvariantDemo
```

Expected output:

```text
DRAFT
CONFIRMED
SHIPPED
Only Draft or Confirmed can be cancelled
```

This example demonstrates complementary mechanisms:

1. **`sealed`:** only the four declared records may directly implement `State`; because records are `final`, the leaf states cannot have additional subtypes.
2. **Constructors on `Line` and state records:** refuse values violating invariants, even when objects are constructed via another call path in domain code.
3. **`List.copyOf` copying:** does not retain a reference to an `ArrayList` that the caller could mutate after creating the state.
4. **Private `state` field:** callers cannot assign an arbitrary state object directly to `Order`.
5. **`confirm`, `ship`, and `cancel` methods:** govern state transitions, so `ship` cannot be called while still `Draft`, nor `cancel` once `Shipped`.
6. **Assigning only after creating the new state succeeds:** when a constructor throws an exception due to invalid data, `state = new ...` does not execute, preventing partial state corruption in these single-step operations.

Here `Order` is an intentionally mutable aggregate, while internal states are values immutable after creation. Combining them enables controlled business state transitions without exposing public field setters.

## 5. Constructors Enforce Each Value's Invariants

In Java 17, `record` is well suited for data-centric variants. Records auto-generate accessors, `equals`, `hashCode`, and `toString` from their declared components. Using a **compact constructor**, you can normalize and validate parameters before Java assigns them to record fields:

```java
record ProductCode(String value) {
    ProductCode {
        value = Objects.requireNonNull(value, "value").strip();
        if (value.isEmpty()) {
            throw new IllegalArgumentException("Product code must not be blank");
        }
    }
}
```

`Objects.requireNonNull` here requires `import java.util.Objects;`. After construction, `new ProductCode("  P-17  ").value()` returns `"P-17"`. Standard record accessors are named `value()`, not `getValue()`.

### Validate Early and Keep Objects in a Valid State

If a value **cannot be valid in any context**, validate it immediately in the value type's constructor or factory. For example:

- `quantity <= 0` is invalid for an order line: check in `Line`.
- `sku` is blank or whitespace-only: check in the SKU type or `Line`.
- `shippedAt` precedes `confirmedAt`: check right inside `Shipped`, since this is a relationship between that variant's own components.
- Empty line list or duplicate SKUs: check when creating any state holding that list.

Doing so ensures every caller obeys the same rules. If you only validate in a controller and allow other code paths to build records with invalid data, internal logic, tests, or data-hydration code may accidentally create invalid values.

Distinguishing commonly used exceptions:

| Situation | A common choice | Meaning |
| --- | --- | --- |
| Argument passed is `null` when the contract requires non-`null` | `NullPointerException` from `Objects.requireNonNull` | A required value is missing. |
| Value is present but violates parameter rules | `IllegalArgumentException` | For example, quantity 0, blank ID, out-of-order timestamps. |
| Parameter data is valid, but the operation does not fit the current state | `IllegalStateException` | For example, calling `ship` on an unconfirmed order. |

These are suitable choices for a standard Java API, **not HTTP mappings**. The API layer can translate input errors into `400` or `422` responses per its contract, while state conflicts might become `409`. HTTP status codes should not be derived mechanically solely from Java exception names.

### A `record` Does Not Guarantee Deep Immutability

Record fields are `private final`, yet a `List<T>` or array field can point to a mutable structure. The snippet below still has a loophole without copying:

```java
record UnsafeCart(List<String> skus) {}

List<String> source = new java.util.ArrayList<>();
source.add("A");
UnsafeCart cart = new UnsafeCart(source);
source.clear();
// cart.skus() has been mutated indirectly.
```

A safer approach for a list of strings is:

```java
record SafeCart(List<String> skus) {
    SafeCart {
        skus = List.copyOf(Objects.requireNonNull(skus, "skus"));
    }
}
```

`List.copyOf` creates a list unmodifiable through the `List` API, yet this is **shallow immutability**: if elements are mutable objects, their internal state can still change. If a component is an **array**, account for defensive copying both on input and in the accessor, because `final` does not stop array element mutation. For models needing deep immutability, prefer elements that are themselves immutable, such as `String`, `Instant`, validated value objects, or records containing only immutable components.

## 6. State-Transition Invariants Require Dedicated Business Logic

Even though the type tree has only `Draft`, `Confirmed`, `Shipped`, and `Cancelled`, that **does not prevent** code from constructing `Shipped` directly from unconfirmed input if `Shipped`'s constructor is public. `sealed` does not record object history and has no knowledge of which business commands ran.

Therefore, distinguish two concepts:

- **Self-consistent state:** any `Shipped` instance has valid `confirmedAt`, `shippedAt`, and line list.
- **Valid process producing that state:** an order may only move from `Confirmed` to `Shipped` through an authorized business operation.

In the main example, `State` and the state records are `private`, while `Order` exposes only `confirm`, `ship`, and `cancel`. This centralizes transitions and prevents callers from mutating `state` directly.

If the system needs richer rules, express transitions as clearly named business methods such as `approve`, `reject`, `pay`, or `refund` rather than a setter like `setState`. Choose method names in the **domain language**, because `setState(SHIPPED)` communicates neither shipping preconditions nor side effects.

### What If State Must Be Returned Externally?

In systems with public APIs, clients often need a read-only representation for display. Return a **mapped DTO/snapshot** from the aggregate rather than exposing references to state types that external callers could instantiate directly. Even when a public sealed hierarchy lets callers construct records, variant constructors must still validate field data; governing **aggregate lifecycle**, however, remains the responsibility of the aggregate/service rather than `permits`.

### Concurrency Considerations

`Order` in the example is **mutable and not designed for concurrent multi-threaded access**. If two threads invoke `confirm` or `cancel` simultaneously, checking state and assigning the new state must be coordinated via appropriate synchronization or transactions. In database-backed applications with concurrent sessions, you typically also need transactions, optimistic locking/versioning, or persistence constraints to prevent lost updates. `sealed`, records, and validating constructors do not solve race conditions by themselves.

## 7. Boundary Input Validation: Parse, Validate, Then Construct Domain Objects

Values arriving from HTTP requests, CSV rows, message queues, config files, or databases may be missing, malformed, or invalid in domain terms. Separate the steps:

```text
Raw request / JSON / Message
           |
           v
      Parse / deserialize
           |
           v
  Validate structure, types, formats
           |
           v
  Create value objects + domain records
  (constructors enforce invariants)
           |
           v
  Invoke aggregate methods
  (enforce state transitions)
           |
           v
     Persist / emit events / respond
```

For example, an API DTO may hold unvalidated input:

```java
record CreateLineRequest(String sku, Integer quantity) {}
```

Choosing `Integer` on the DTO models that quantity **may be absent** in an external request. When converting the DTO into a domain `Line`, check for `null` and convert to `int` only after validation:

```java
static OrderInvariantDemo.Line toDomain(CreateLineRequest request) {
    Objects.requireNonNull(request, "request");

    Integer quantity = request.quantity();
    if (quantity == null) {
        throw new IllegalArgumentException("quantity is required");
    }

    return new OrderInvariantDemo.Line(request.sku(), quantity);
}
```

In this snippet, `import java.util.Objects;` is required. Calling `new Line(...)` still validates the SKU and positive quantity, so invariants do not depend on whether the DTO was validated in a controller. For large DTOs or layered validation, you can use Bean Validation with constraints supported by your project, while still protecting **core domain rules** in constructors/factories and business methods; request-layer annotations cannot replace them.

### Value Validation vs. Contextual Validation

Not every rule belongs in a constructor:

| Condition | Where should the check live? | Reason |
| --- | --- | --- |
| Non-blank SKU | Value object or `Line` record | Holds in every context where an SKU is used. |
| Positive quantity | `Line` | Local invariant; requires no access to external systems. |
| SKU exists in the current catalog | Application/domain service and repository | Depends on data that changes over time. |
| Caller is authorized to confirm this order | Auth/authorization layer and use case | Depends on identity and access policies. |
| Only a confirmed order may be shipped | `Order` aggregate | Depends on the order's current state. |
| Shipping date not before confirmation date | `Shipped` constructor | Intrinsic relationship between fields of the variant. |
| No duplicate confirmation of the same ID system-wide | Persistence/transaction and uniqueness constraints | Spans multiple objects or concurrent transactions. |

The input boundary is responsible for reporting clear, contextual errors to callers, yet **the domain model must still guard its own valid state** across every allowed construction path. Do not rely solely on UI checks or a single controller.

## 8. `sealed` Variants Should Carry Data Matching Domain Semantics

A common design mistake is turning a record into a "bag of optional fields":

```java
record PaymentResult(
        boolean success,
        String transactionId,
        String rejectionReason) {}
```

That type allows `success = true`, `transactionId = null`, `rejectionReason = "Rejected"`, and many other nonsensical combinations. If the data genuinely has **two distinct shapes**, express them explicitly:

```java
sealed interface PaymentResult permits Approved, Rejected {}

record Approved(String transactionId) implements PaymentResult {
    Approved {
        transactionId = Objects.requireNonNull(transactionId, "transactionId").strip();
        if (transactionId.isEmpty()) {
            throw new IllegalArgumentException("transactionId is required");
        }
    }
}

record Rejected(String reason) implements PaymentResult {
    Rejected {
        reason = Objects.requireNonNull(reason, "reason").strip();
        if (reason.isEmpty()) {
            throw new IllegalArgumentException("reason is required");
        }
    }
}
```

The snippet uses `java.util.Objects`. In Java 17, these records cannot extend an arbitrary class (because records implicitly extend `java.lang.Record`), yet they can `implements PaymentResult`; hence `sealed interface` is a natural fit for a sum type with record variants.

This model eliminates the possibility of **the same value** being both `Approved` and `Rejected`, and forces each case's required data into its proper variant. Still, deciding **when** payment is approved, whether funds are sufficient, or whether a transaction was recorded remains business logic outside the scope of `sealed`.

## 9. Handling Variants Safely in Java 17

In Java 17, pattern matching with `instanceof` is a standard feature:

```java
static String message(PaymentResult result) {
    Objects.requireNonNull(result, "result");

    if (result instanceof Approved approved) {
        return "Paid: " + approved.transactionId();
    }
    if (result instanceof Rejected rejected) {
        return "Rejected: " + rejected.reason();
    }
    throw new IllegalStateException("Unhandled payment result");
}
```

The pattern `Approved approved` both tests the type and binds a variable of type `Approved`, avoiding manual casts. Note that `instanceof` on `null` evaluates to `false`; in the example, `null` input is explicitly rejected.

**Important limitation on Java 17:** an `if (result instanceof ...)` chain **is not checked by the compiler for exhaustiveness across a sealed hierarchy**. If a new variant like `Pending` is added to `permits`, old handler code can still compile and fail only when hitting the fallback branch at runtime. Therefore, when adding or removing variants, audit all related handling locations.

Pattern matching for `switch` and **record patterns** were only finalized in Java 21. In Java 17, pattern `switch` is still a preview feature and should not be relied upon in hands-on examples or stable Java 17 code. When branching by type in Java 17, `instanceof` pattern matching is the appropriate, standard choice.

## 10. Invariants During Data Rehydration, Deserialization, and Framework Integration

The fact that data was stored in a database or came from an external system does not guarantee it is valid when reloaded. For instance, a state record may be rehydrated from JSON, a JPA entity, a SQL row, or a message queue. With a strict domain design, use a **validated reconstruction path**:

1. Read raw data into an intermediate type capable of representing missing or invalid values.
2. Explicitly distinguish variants via a discriminator defined in the data contract (e.g., `kind = "CONFIRMED"`).
3. Construct value objects and states through validating constructors/factories.
4. Check any cross-state invariants, aggregate versions, or reference data if required.
5. Report concrete errors or route corrupt data to an error-handling flow instead of silently fabricating a pseudo-valid domain object.

For example, when storing a sealed set of variants as JSON, many libraries require explicit configuration to identify subtypes or map DTOs; `sealed` does not dictate JSON format or database schema. In Java 17, records have canonical constructors and distinct accessors, yet each library's support for records/sealed types depends on **library version and configuration**. Do not assume every framework automatically understands `permits` and enforces all business checks.

For databases, constraints such as `NOT NULL`, `CHECK`, `UNIQUE`, and foreign keys help keep data valid when multiple writers exist. They complement Java invariants: constructors protect objects in memory, while transactions and constraints protect consistency across requests and processes.

### Evolving Models Over Time

Adding a new variant to a `sealed` tree can affect API contracts and persisted data. Consider:

- Can older readers handle the tag for the new variant?
- Do all `if/instanceof` sites already have a branch for the new variant?
- Does adding a new invariant invalidate historical records?
- Is data migration needed, or a mechanism to accept legacy data and convert it to a valid new form?

A closed type hierarchy clarifies all current data shapes, yet **does not automatically make schema evolution backward-compatible**.

## 11. Testing State Creation and State Transition Paths

Two groups of scenarios are crucial to test in a real system:

**Valid objects and transitions succeed:**

- `Line("A", 1)` is valid.
- `Order` is created with at least one valid line and unique SKUs.
- `Draft → Confirmed → Shipped` succeeds when shipping time is not before confirmation time.
- `Draft → Cancelled` and `Confirmed → Cancelled` succeed when the cancellation reason is valid.

**Invalid objects or operations are rejected:**

- Blank SKU, zero or negative quantity.
- `null` or empty line list, `null` element, or duplicate SKUs.
- Blank confirmation ID or `null` confirmation timestamp.
- Shipping timestamp earlier than confirmation timestamp.
- `Draft → Shipped`, `Shipped → Cancelled`, `Cancelled → Confirmed`.
- Caller modifies the original list after creating `Order`, yet internal state remains unaffected.

Example JUnit Jupiter test when a project is configured with JUnit 5:

```java
import org.junit.jupiter.api.Test;
import java.time.Instant;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class OrderInvariantTest {
    @Test
    void invalidQuantityIsRejectedAtCreation() {
        assertThrows(IllegalArgumentException.class,
                () -> new OrderInvariantDemo.Line("A", 0));
    }

    @Test
    void cannotShipBeforeConfirmation() {
        var order = new OrderInvariantDemo.Order(
                List.of(new OrderInvariantDemo.Line("A", 1)));

        assertThrows(IllegalStateException.class,
                () -> order.ship(Instant.parse("2026-02-01T10:00:00Z")));
        assertEquals("DRAFT", order.status());
    }

    @Test
    void failedTransitionKeepsPreviousState() {
        var order = new OrderInvariantDemo.Order(
                List.of(new OrderInvariantDemo.Line("A", 1)));
        order.confirm("CONF-1", Instant.parse("2026-02-02T10:00:00Z"));

        assertThrows(IllegalArgumentException.class,
                () -> order.ship(Instant.parse("2026-02-01T10:00:00Z")));
        assertEquals("CONFIRMED", order.status());
    }
}
```

These tests verify **rejection of invalid data and preservation of prior state on failed operations**. They cannot replace runtime checks, transactions, or external data validation. If the system runs concurrently or uses persistence, add appropriate tests for concurrent updates and state rehydration.

## 12. Misconceptions That Cause Design Bugs

| Misconception | Reality in Java 17 | How to handle it |
| --- | --- | --- |
| "Once `sealed`, data is always valid" | `sealed` restricts only direct subtypes. | Validate fields in constructors/factories and transition preconditions in the aggregate. |
| "`record` is completely immutable" | A `final` reference field does not freeze a mutable object inside. | Make defensive copies and use immutable element types when needed. |
| "All variants must be public for pattern matching" | Variants can stay `private` inside the domain while exposing an appropriate read API. | Separate internal types from public DTOs/snapshots. |
| "Validating at the HTTP controller is enough" | Domain objects can be constructed in tests, workers, persistence loading, and internal code. | Keep core invariants inside the domain model itself. |
| "`permits` closes every descendant class" | A `non-sealed` branch still allows further extension. | Inspect the whole hierarchy and pick appropriate inheritance policies. |
| "Covering all `instanceof` branches is checked by the compiler" | `if/instanceof` chains in Java 17 have no exhaustiveness checking for sealed types. | Audit callers when adding variants and include explicit error branches. |
| "Valid field values mean a valid transition history" | A `Shipped` instance with valid fields does not prove `Order` went through `Confirmed`. | Allow transitions only through business methods and protect internal state. |
| "`sealed` prevents race conditions" | No synchronization or transaction semantics are added by this keyword. | Use synchronization, transactions, or optimistic locking when required. |
| "Java 17 supports type-pattern `switch` like Java 21" | Type-pattern `switch` is not a standard feature in Java 17. | Use `instanceof` pattern matching, which is standard in Java 17. |

## 13. Applying This to a New Domain Model

When starting on a requirement with multiple data cases, determine step by step:

1. **List genuinely distinct variants.** Create a variant only when it has distinct business meaning or data; if cases are just labels without differing payloads, an `enum` may be simpler.
2. **Decide whether the hierarchy should be closed.** If the team controls all variants, `sealed interface` is a good candidate; if the API intentionally lets others add subtypes, weigh the impact of `sealed`.
3. **Place local invariants in value objects/records.** Include non-`null`, non-blank, value bounds, cross-field rules, and defensive copies.
4. **Place lifecycle invariants in the aggregate.** Expose only valid business behaviors; avoid exposing setters for internal state if they could create rule-breaking states.
5. **Place contextual checks in the right layer.** Permissions, data existence, cross-object rules, or transactional constraints need service/repository/DB support.
6. **Let only valid objects enter the domain.** Parse and validate input, construct via constructors/factories, then execute operations on aggregates.
7. **Account for rejected cases as well.** Do not test only the happy path; invalid data and illegal transitions must have clearly defined behavior.

**Core principle:** `sealed` restricts **the valid shapes of the domain**, constructors and records protect **the valid values of each shape**, and aggregates with business methods protect **valid changes over time**. When input validation and data rehydration feed into these protective layers, Java 17 applications can drastically reduce nonsensical states and keep domain rules concentrated in controllable places.
