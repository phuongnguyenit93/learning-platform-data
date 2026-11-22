# Separating Data and Behavior When Needed

**Topic:** Domain model design in Java Core Pattern Matching. The main example uses **Java 21+** with **sealed interfaces**, **record patterns**, and **pattern matching for switch**. These are standard Java 21 features; no preview flags are required.

## 1. The design problem: how much behavior should data carry?

In a domain model, **data** represents business facts, state, values, or events; **behavior** represents rules or operations related to that data. For example, an order-placed event carries an order ID and a customer name, while tasks such as generating an audit line, sending an email, exporting a report, or rendering on a UI may all read the same event for different purposes.

A traditional design approach is to place processing methods directly on the object itself:

~~~java
// Design sketch: not a standalone program.
interface OrderEvent {
    String auditLine();
    String notificationText();
}
~~~

This approach works well when the behavior is an essential part of the domain concept. However, if every new report type or output format requires modifying every subtype, domain classes gradually accumulate dependencies on unrelated concerns. Another model is to keep events carrying **structured data** and place their interpretations in separate processors.

**Key takeaway:** there is no rule that every domain object must be "data-only." Separate behavior when it belongs to a different consumer, workflow, or infrastructure layer; keep behavior in the domain when the object itself needs to protect invariants or enforce core business rules.

## 2. Leveraging sealed types and records to model data variants

Suppose the system has three order events:

- **Placed:** an order has just been placed; has an order ID and a customer name.
- **Shipped:** an order has been shipped; has an order ID and a carrier.
- **Cancelled:** an order has been cancelled; has an order ID and a reason.

They differ in data structure, yet all are a kind of **OrderEvent**. In Java 21, this can be represented with a sealed interface and records:

~~~java
sealed interface OrderEvent permits Placed, Shipped, Cancelled {
    long orderId();
}

record Placed(long orderId, String customer) implements OrderEvent {}
record Shipped(long orderId, String carrier) implements OrderEvent {}
record Cancelled(long orderId, String reason) implements OrderEvent {}
~~~

The snippet above only illustrates the type declarations. The complete program in section 5 also includes input validation.

**Why choose this structure?**

1. **OrderEvent** expresses a closed set of variants: only the direct subtypes listed in **permits** are allowed to implement it.
2. Each **record** declares the components of a value, while providing a constructor, accessors, **equals**, **hashCode**, and **toString** according to record semantics.
3. Records are final; the event type is represented as a recorded value rather than an object meant to be extended through inheritance.
4. Processors can use **switch** and record patterns to extract the corresponding components, while the compiler checks coverage of all event types.

Sealing only restricts **direct subtypes**. If a permitted branch is declared **non-sealed**, subclasses beneath that branch can continue extending it. In this example, all three subtypes are records (implicitly final), so each branch terminates there.

### Are records truly immutable?

Records have final component fields, but they are **not deeply immutable by default**. If a component references a **List** or a mutable object, that object's contents can still be modified through the reference. This example uses `String` and `long`, so the components themselves are well-suited for stable value data.

For collections, a constructor can use **List.copyOf(...)** or copy the data appropriately; you still need to consider whether the elements inside are mutable. Deep immutability is a design decision, not an automatic guarantee of records.

## 3. Separating data does not mean abandoning validation and invariants

A common mistake when applying the "data + functions" model is moving state-protection rules out of the record as well, allowing meaningless events to be constructed anywhere:

~~~java
// Without validation, invalid data can be constructed.
new Placed(0, "");
~~~

Core rules such as **orderId > 0** and **customer non-null/non-blank** should be enforced at the point of value creation. Records provide a **compact constructor** to validate those conditions.

~~~java
record Placed(long orderId, String customer) implements OrderEvent {
    Placed {
        checkId(orderId);
        if (customer == null || customer.isBlank()) {
            throw new IllegalArgumentException("customer");
        }
    }
}
~~~

This is an excerpt; the `checkId` method and all types are defined in the program in section 5. The compact constructor's parameter variables are automatically assigned to the components after validation completes, provided no exception is thrown.

Thus, **data and its validity invariants** stay in the same place. Behaviors such as **audit formatting**, **notification decisions**, **DTO conversion**, or **infrastructure persistence** can be separated from the data structure.

It is important to distinguish:

| Responsibility | Typical appropriate location | Why |
| --- | --- | --- |
| Required values, valid value ranges, value object invariants | Constructor or domain method | Protects data right at creation/modification time |
| Rules governing aggregate state transitions | Appropriate aggregate or domain service | Protects business consistency |
| Generating an audit line or read model from an event | Separate projector/formatter | Represents a specific consumer's view |
| Deciding email or push notification content | Notification policy/service | Avoids coupling the event to delivery channels |
| Calling a database, HTTP endpoint, or sending actual email | Adapter/infrastructure service | Avoids mixing infrastructure side effects into value objects |
| Converting events to external JSON/DTOs | Mapper/serializer boundary | Reduces domain dependency on transport formats |

You should not move every business rule out of objects and call that separation of responsibilities. What matters is **which subject owns the rule and at which boundary it must be enforced**.

## 4. Pattern matching enables placing behavior per consumer

When variants belong to a **sealed hierarchy**, a processor can write a **switch expression** over the parent type:

~~~java
// Illustrative excerpt, assuming the records are already declared.
static String auditLine(OrderEvent event) {
    return switch (event) {
        case Placed(long id, String customer) ->
                "AUDIT: " + id + " placed by " + customer;
        case Shipped(long id, String carrier) ->
                "AUDIT: " + id + " shipped via " + carrier;
        case Cancelled(long id, String reason) ->
                "AUDIT: " + id + " cancelled: " + reason;
    };
}
~~~

A **record pattern** such as **Placed(long id, String customer)** checks the record type and extracts its two components in declaration order. The switch branch requires no manual cast. Because the switch expression covers all three variants of the sealed `OrderEvent`, it can **omit default** and still remain exhaustive for non-null `OrderEvent` values.

From the same data, another consumer can produce a different reaction without making the record aware of the consumer's needs:

~~~java
static String notification(OrderEvent event) {
    return switch (event) {
        case Placed(long id, var customer) ->
                "EMAIL: receipt for " + id;
        case Shipped(long id, var carrier) ->
                "EMAIL: shipping update for " + id + " via " + carrier;
        case Cancelled(var id, var reason) -> "NO EMAIL";
    };
}
~~~

The two methods **auditLine** and **notification** are two **separate behaviors** sharing the same data types. This illustrates the idea of separating data from the **ways data is used**. In a real system, they may live in two different services with independent tests, dependencies, and evolution paths.

**Direct benefit of sealed + switch:** if a **Returned** event is added, once the permitted subtype is introduced, any switch expression without `default` that lacks a `Returned` branch will be flagged by the compiler on recompilation. Consumers that need to decide how to handle the new event will have to be reviewed.

**Trade-off:** the same hierarchy may appear in many different switches. If a new subtype is added frequently, updating many consumers can become costly. This is a key criterion for deciding whether behavior should live on each subtype instead.

## 5. Complete, runnable Java 21 program

Save the following code to **DataBehaviorSeparationDemo.java**. The example both keeps invariants inside the records and places two ways of reading events in separate methods. This is a minimal model: **notification** only *generates simulated content* and does not send a real email.

~~~java
import java.util.List;
import java.util.Objects;

public class DataBehaviorSeparationDemo {
    sealed interface OrderEvent permits Placed, Shipped, Cancelled {
        long orderId();
    }

    record Placed(long orderId, String customer) implements OrderEvent {
        Placed {
            checkId(orderId);
            if (customer == null || customer.isBlank()) {
                throw new IllegalArgumentException("customer");
            }
        }
    }

    record Shipped(long orderId, String carrier) implements OrderEvent {
        Shipped {
            checkId(orderId);
            if (carrier == null || carrier.isBlank()) {
                throw new IllegalArgumentException("carrier");
            }
        }
    }

    record Cancelled(long orderId, String reason) implements OrderEvent {
        Cancelled {
            checkId(orderId);
            if (reason == null || reason.isBlank()) {
                throw new IllegalArgumentException("reason");
            }
        }
    }

    private static void checkId(long id) {
        if (id <= 0) throw new IllegalArgumentException("orderId");
    }

    static String auditLine(OrderEvent event) {
        Objects.requireNonNull(event, "event");
        return switch (event) {
            case Placed(long id, String customer) ->
                    "AUDIT: " + id + " placed by " + customer;
            case Shipped(long id, String carrier) ->
                    "AUDIT: " + id + " shipped via " + carrier;
            case Cancelled(long id, String reason) ->
                    "AUDIT: " + id + " cancelled: " + reason;
        };
    }

    static String notification(OrderEvent event) {
        Objects.requireNonNull(event, "event");
        return switch (event) {
            case Placed(long id, var customer) ->
                    "EMAIL: receipt for " + id;
            case Shipped(long id, var carrier) ->
                    "EMAIL: shipping update for " + id + " via " + carrier;
            case Cancelled(var id, var reason) -> "NO EMAIL";
        };
    }

    public static void main(String[] args) {
        List<OrderEvent> events = List.of(
                new Placed(101, "An"),
                new Shipped(101, "DHL"),
                new Cancelled(102, "duplicate"));

        for (OrderEvent event : events) {
            System.out.println(auditLine(event));
            System.out.println(notification(event));
        }

        try {
            new Placed(0, "An");
        } catch (IllegalArgumentException ex) {
            System.out.println("INVALID: " + ex.getMessage());
        }

        try {
            auditLine(null);
        } catch (NullPointerException ex) {
            System.out.println("NULL REJECTED");
        }
    }
}
~~~

Compile and run with **JDK 21 or newer**:

~~~bash
javac DataBehaviorSeparationDemo.java
java DataBehaviorSeparationDemo
~~~

Exact output:

~~~text
AUDIT: 101 placed by An
EMAIL: receipt for 101
AUDIT: 101 shipped via DHL
EMAIL: shipping update for 101 via DHL
AUDIT: 102 cancelled: duplicate
NO EMAIL
INVALID: orderId
NULL REJECTED
~~~

**Result analysis:**

1. The input consists of three valid events; on each iteration, **auditLine** and **notification** interpret the same event for their own purposes.
2. **Cancelled** still produces an audit record but does not generate an email notification; there is no need to add an email method to the `Cancelled` record to achieve this.
3. **new Placed(0, "An")** is invalid and is rejected by the compact constructor with `IllegalArgumentException`. Thus, separating external processing does not weaken domain invariants.
4. Both processing methods use **Objects.requireNonNull(event, "event")**, explicitly defining a policy that rejects null selectors. Calling `auditLine(null)` throws `NullPointerException`, which `main` catches to print **NULL REJECTED**.
5. The switches omit `default` because all three subtypes are covered. Adding a new subtype without updating the switches will cause a compilation error when recompiling the model and consumers.

The example places the types and processors in the same class so it is easy to copy and run. In a real application, splitting them into **domain model**, **application service**, **read-model projector**, and **infrastructure adapter** is a separate code-organization decision, not a requirement for pattern matching to work.

## 6. Criteria: when to separate and when to keep behavior on the type?

The key question is: **what changes more frequently: the data variants or the operations applied to them?**

| Situation | Design often worth considering | Reason |
| --- | --- | --- |
| Subtype set is relatively stable; new reports/workflows are added often | Sealed + record + per-consumer switch | Easy to add new transformations without modifying records |
| Multiple ways to render the same event are needed | Extract external formatters/projectors | Domain events stay decoupled from UI or export formats |
| Behavior belongs to only one subtype and is tightly tied to its invariants | Method directly on the subtype | Keeps related logic and state close together |
| New subtypes are added frequently; operations are relatively stable | Polymorphism/virtual dispatch may be better | Adding a subtype includes its own behavior implementation |
| Logic governing entity/aggregate state transitions | Domain method or domain service | Protects consistency boundaries and avoids an anemic domain |
| Behavior depends on email, database, or external APIs | Application/infrastructure service | Isolates side effects and technical dependencies |
| Data type is a DTO or immutable event | Record is a strong candidate | Primarily carries values; easy to compare and deconstruct |
| Entity has identity, lifecycle, state transitions, and complex ORM | Class/aggregate fits better than a plain record | Records do not inherently manage identity and lifecycle |

**Neither choice is universally better.** Sealed + pattern switch favors designs where it is easy to **add new operations**; placing polymorphic behavior on each subtype favors designs where it is easy to **add new types** for an existing set of operations. Both have extension costs, and a single system can use both at different boundaries.

## 7. Comparison with a polymorphic design

Suppose the `OrderEvent` interface required the event itself to know how to produce an audit line:

~~~java
// Polymorphic alternative sketch; DO NOT merge into the section 5 program.
interface Auditable {
    String auditLine();
}

record Placed(long orderId, String customer) implements Auditable {
    @Override
    public String auditLine() {
        return "AUDIT: " + orderId + " placed by " + customer;
    }
}
~~~

In this approach, a client can call **event.auditLine()** through the interface. Adding a new subtype requires implementing `auditLine()` if the interface mandates it. However, if many brand-new operations are needed—such as **notificationText()**, **searchIndexDocument()**, or **exportCsv()**—adding methods to the interface forces edits across many subtypes or adapter classes.

With pattern matching, each processor has its own case branches by subtype. Adding an operation requires no changes to the records; adding a subtype forces updates to switches that must handle it.

These two directions are often described as choosing between extending by **rows (adding data types)** or by **columns (adding operations)**. Do not decide based solely on fewer lines of code: compare against the actual rate of change in the domain and where the logic is owned.

## 8. Avoiding turning the domain into an "anemic model"

An **anemic domain model** is when objects only hold data while nearly all important business rules are pushed out to external services, making invariants and state transitions hard to control. Separating audit formatting from an event does not automatically cause this problem.

The boundaries should be clear:

- **Event:** represents a fact that has already happened (for example, an order was shipped), usually produced by other business logic. An event can hold validation and stable data.
- **Command:** describes a request to perform an action, which may need a service/aggregate to validate before accepting.
- **Entity/Aggregate:** manages identity, lifecycle, and state-transition rules. Methods such as **ship()** may belong on the aggregate or domain service, rather than being executed solely through switches scattered across the system.
- **Projection/Notification:** reads events to produce a view or external side effect. This is where separating behavior is usually appropriate.

For example, the rule **an order cannot be shipped once cancelled** is not a presentation detail. It must be enforced where the state-transition command is executed, typically on the appropriate aggregate or domain service. Do not let formatters decide whether a domain state is valid.

Conversely, the message "shipping update for 101 via DHL" is an output serving a consumer; placing it in a notification service usually keeps the domain independent of wording and delivery channels.

## 9. Limitations and risks when using pattern matching to separate behavior

### 9.1. A new subtype affects many consumers

A sealed hierarchy helps the compiler detect non-exhaustive switches when a new subtype is added. That is an advantage for change control, but it can also create many places that need updating. If a subtype is added frequently and always carries the same abstract behavior, polymorphism can reduce edits across multiple processors.

If you still choose `switch`, **consolidate each responsibility into one service**. Do not place the same switch in controllers, repositories, schedulers, and mappers and let them evolve independently.

### 9.2. Leaking concrete types across the entire system

When every class knows about `Placed`, `Shipped`, and `Cancelled`, the code becomes tightly coupled to the subtype list. You can use a mapper/projector at a boundary to translate them into a more stable interface or DTO for downstream layers.

Pattern matching works well when a component **has a reason to understand all variants**. That does not mean every component should do so.

### 9.3. Long cases and deeply nested patterns

A case with three- or four-level record patterns and multiple **when** guards can be harder to read than a method call. If complex rule checks are needed, extract them into a method named after the business concept. Keep `switch` in the role of **branching by data shape**, rather than turning it into a long program inside a case.

### 9.4. Confusing exhaustiveness with validity

The compiler can prove that a switch covers all subtypes; it **does not prove** that `customer` is non-blank, `orderId` is positive, or sending an email is safe. Validation and invariants still need to live in the appropriate place. Nor does the compiler infer that arbitrary guards like **when x > 0** and **when x <= 0** cover all values: a corresponding general case is usually required.

### 9.5. Null and reference types

A switch over a sealed hierarchy can be exhaustive for all non-null values and still reject null. In the example, **Objects.requireNonNull** establishes the policy of rejecting null inputs. If null has business meaning, you can design a **case null** with appropriate behavior instead of letting an unexpected error occur.

With nested record patterns, if a child record component is null, the specific nested pattern does not match. For a reference component bound with **var** in a record pattern, the variable may hold null if the record constructor allows it. Do not equate "matches the pattern" with "all components are non-null."

### 9.6. Side effects and purity

A switch-based processor that only builds a `String` is an example of a **pure transformation** that is easy to test. If a case must send an email, write to a DB, or call an external service, consider separating the **decision** from **executing the side effect** to make retries, error observation, and consistency protection easier.

Do not build critical behavior on the assumption that every record's accessors are pure: Java allows writing explicit accessors, so deconstruction can trigger logic inside an accessor if the type is designed that way.

## 10. An applicable refactoring workflow

When you have a hierarchy with data and multiple behaviors mixed together, follow these steps:

1. **Classify responsibilities:** identify invariants, state rules, formatting, integrations, and consumer-specific processing.
2. **Identify the variant space:** which types are mutable, and which can be represented with a sealed interface and immutable records? Do not mechanically convert mutable entities into records.
3. **Keep invariants at data creation/modification boundaries:** add validation for conditions that can genuinely be guaranteed there.
4. **Extract one consumer at a time:** move a single operation such as audit formatting into a switch-based function/service, rather than changing everything at once.
5. **Verify behavior:** add tests for each subtype, null, invalid data, and new cases; check exceptions, logging, and side-effect ordering as well.
6. **Evaluate how many places know the subtypes:** if pattern switches proliferate and duplicate logic, redesign the boundary or return to polymorphism for shared responsibilities.
7. **Test extensibility:** try adding a new subtype and observe where the compiler flags switches that need handling; update them with clear business decisions.
8. **Do not overuse default:** on a sealed hierarchy, `default` can hide missing cases during extension. Use it only if a general fallback behavior is genuinely defined.

## 11. Code review checklist

| Question | Sign of good design |
| --- | --- |
| Which data are events/values, and which are entities with a lifecycle? | Types are chosen based on semantics, not shorter syntax |
| Are there invariants that must hold when creating or modifying an object? | Enforced in the constructor/aggregate/domain service |
| Do consumers have distinct reasons to interpret the data? | Formatters, projectors, and notifications are clearly separated |
| Is the subtype set closed and well-managed? | Sealed/record used appropriately; switches are exhaustive when needed |
| Does adding a new operation force edits across many subtypes? | Consider extracting behavior externally |
| Does adding a new subtype force edits across many switches? | Consider polymorphism or a stable boundary |
| Is logic or side-effect handling duplicated across multiple switches? | Consolidate responsibility or move into an appropriate service/method |
| Have null, invalid data, and wrong-type cases been tested? | Thoroughly tested, not relying solely on exhaustiveness |

**Conclusion:** Separating data and behavior **when responsibilities genuinely differ** keeps the domain model clean, lets consumers evolve independently, and leverages sealed types + record patterns for type-safe branching. Still, rules for constructing valid values and keeping domain state consistent must be protected by the right owner. Choose between **external pattern switches** and **internal polymorphism** based on the direction your system changes, rather than treating "data-only objects" as an absolute goal.