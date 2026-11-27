# Choosing `record` vs. `class` for DTOs and Domain Models in Java 17

Java 17 lets you declare a data-carrying type with `record` instead of manually writing a `class` with constructors, `final` fields, accessors, `equals`, `hashCode`, and `toString`. However, syntactic brevity **is not a sufficient criterion** for turning every class into a record.

When designing an application, first ask: does this object **represent a value**, **a data-transfer message**, or **an entity with its own identity and lifecycle**? Does the object need to mutate state across business operations? Does it need class inheritance or to satisfy framework contracts?

An effective rule of thumb:

- Use **`record`** for simple DTOs, computation results, messages, and *value objects* with fixed components, especially when equality is data-based.
- Use **`class`** for entities and aggregates with stable identity, lifecycles, mutable state, or implementation/hierarchy requirements that records cannot satisfy.
- Use an **immutable class** if you need immutability while controlling internal structure, representation, or an `equals` contract that differs from record semantics.

These are **design guidelines**, not rigid mandates. An immutable domain entity can still be a class; a record can hold business behavior and enforce invariants. Do not equate "DTO = record" or "domain = class."

## 1. What Characteristics Do Records Actually Have in Java 17?

`record` has been an official feature since Java 16, so it is stable in Java 17 without `--enable-preview`.

Example:

```java
public record UserSummary(long id, String displayName) {}
```

This declaration describes two **record components**: `id` and `displayName`. The compiler automatically provides:

- Corresponding fields stored as `private final`.
- A **canonical constructor** taking `long id` and `String displayName`.
- Accessors `id()` and `displayName()`; these are not `getId()`-convention getters.
- `equals(Object)` and `hashCode()` based on all components.
- `toString()` displaying the record name and components.

Usage:

```java
UserSummary first = new UserSummary(42, "Lan");
UserSummary second = new UserSummary(42, "Lan");

System.out.println(first.id());           // 42
System.out.println(first.displayName());  // Lan
System.out.println(first.equals(second)); // true
System.out.println(first);                // UserSummary[id=42, displayName=Lan]
```

Unlike regular classes, records impose several design constraints:

| Property | `record` in Java 17 | Regular `class` |
| --- | --- | --- |
| Data declaration | Component list in the record header is the published state | Can choose fields, API, and internal representation freely |
| Inheriting another class | No; records are implicitly `final` and inherit `java.lang.Record` | Can extend a class if contracts permit |
| Implementing interfaces | Yes, including `sealed interface` when permitted | Yes |
| Extra instance fields | Cannot declare instance fields beyond components | Can add fields, caches, or internal state |
| Mutating component values | No auto-generated setters; fields are `final` | Can be immutable or mutable per design |
| Default `equals` / `hashCode` | Based on components | Inherited from `Object` (identity-based) unless overridden |
| Constructors | Has canonical, compact, and valid auxiliary constructors | Choose constructors, factories, and initialization rules freely |
| Representation structure | Becomes a visible part of the public contract | Can hide, evolve, or refactor more flexibly |

A record is still a **class** in Java's type system. A record can define methods, implement interfaces, have static members, declare generics, validate data, and implement behavior. It is not merely a "struct with fields."

### Compact Constructors Help Protect Data

A record can validate and normalize components inside a compact constructor:

```java
import java.util.Locale;
import java.util.Objects;

public record ProductCode(String value) {
    public ProductCode {
        value = Objects.requireNonNull(value, "value")
                .strip()
                .toUpperCase(Locale.ROOT);
        if (value.isEmpty()) {
            throw new IllegalArgumentException("Product code must not be blank");
        }
    }
}
```

In a compact constructor, you modify the `value` **parameter**; after validation runs, Java automatically assigns the final parameter value to the record field. Uppercasing only fits when **domain rules specify case-insensitive product codes**. Do not normalize arbitrarily if letter casing carries domain meaning.

When an invalid value cannot exist in any context, checking upfront in a constructor/factory ensures every creation site enforces the same invariant. However, conditions depending on databases, user permissions, or aggregate state usually belong in services/aggregates rather than cramming everything into a record constructor.

## 2. DTOs: Why Do Records Often Fit Well?

A **DTO (Data Transfer Object)** exists to carry data across layers or boundaries: HTTP API responses, messages, query results, service return values, or use-case input payloads.

A DTO typically has a fixed structure, needs no setters, and is constructed then read. Records fit well because they declare structure clearly, minimize boilerplate, and make values easy to inspect.

### Output DTOs

```java
import java.util.List;
import java.util.Objects;

public record OrderResponse(
        String orderId,
        String status,
        List<LineResponse> lines,
        long totalCents) {

    public OrderResponse {
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(status, "status");
        lines = List.copyOf(Objects.requireNonNull(lines, "lines"));
        if (totalCents < 0) {
            throw new IllegalArgumentException("totalCents must not be negative");
        }
    }
}

record LineResponse(String productCode, int quantity, long unitPriceCents) {}
```

`OrderResponse` expresses the exact fields returned by an endpoint, while `LineResponse` describes each line's data. Components have matching accessors, such as `response.orderId()` and `response.lines()`.

`List.copyOf` protects the list from indirect mutation through the caller's original list; the list stored in the record also forbids modification via `add` or `clear`. Still, this is **shallow immutability**: if elements had mutable state, mutating an element could still change observable contents. In the example above, `LineResponse` contains only `String` and primitives, avoiding that issue.

### Input DTOs

Example request to add an order line:

```java
public record AddLineRequest(String productCode, Integer quantity) {}
```

Input DTOs typically describe what **the caller sent**, including missing or invalid data. Choosing `Integer` instead of `int` can represent an absent `quantity` field as `null`; however, distinguishing absence, explicit JSON `null`, and default values also depends on the deserialization library and mapping configuration.

At the domain conversion boundary:

```java
static OrderLine toDomain(AddLineRequest request) {
    Objects.requireNonNull(request, "request");
    if (request.quantity() == null) {
        throw new IllegalArgumentException("quantity is required");
    }
    return new OrderLine(
            new ProductCode(request.productCode()),
            request.quantity());
}
```

This conversion snippet assumes `OrderLine` and `ProductCode` are defined in the domain model and `java.util.Objects` is imported. `OrderLine` itself must enforce positive quantity. Thus:

1. **DTO** accepts raw data arriving at the boundary.
2. **Parser/validator** checks types, required fields, formats, and errors to report back to the caller.
3. **Domain value objects** enforce invariants that must always hold.
4. **Aggregates/services** enforce rules depending on state or business context.

If an API must support partial updates, a record DTO can still work, though you must design carefully to distinguish "field omitted" from "explicit `null` sent to clear a value." Bare record components alone are often **insufficient** to express the three states *absent*, *explicit null*, and *value*; you may need wrapper types, dedicated patch models, or specialized deserialization mechanisms.

### Records Do Not Automatically Define JSON Contracts or Validation

The Java language specifies record structure and methods, **not JSON**. Libraries like Jackson can serialize/deserialize records in supported versions, yet field names, aliases, null handling, constructor binding, polymorphism, and annotations depend on **the actual library and configuration**.

Similarly, Bean Validation annotations (`@NotNull`, `@Size`, `@Positive`, ...) can be placed on DTOs if the project uses a supporting validation framework, but adding annotations **does not mean** every `new SomeRecord(...)` call automatically triggers a validator. When data is a core domain invariant, constructors/factories still need to enforce it—or an equivalent controlled construction mechanism must exist.

## 3. Domain Modeling: Separating *Value Objects* from Entities/Aggregates

In Domain-Driven Design, two categories of objects usually mean very different things:

- **Value object:** identified by **its values**. Two values with identical attributes are considered equivalent under domain rules—for example, product codes, date ranges, coordinates, certain money types, or immutable states.
- **Entity:** has **stable identity** across changes. Two orders with identical contents are still two distinct orders if they have different identifiers. An aggregate coordinates operations and invariants across related objects within its boundary.

Because `record` generates `equals`/`hashCode` across **all components**, it is often a strong candidate for value objects; entities with identity and lifecycles are usually clearer as classes.

| Domain Scenario | Suggested Choice | Reason |
| --- | --- | --- |
| `ProductCode("P-17")` | `record` | Small data, well-defined value, easy to normalize and validate |
| A coordinate or read-only config | `record` | Components define the value; changes typically produce a new value |
| Business `Success` / `Failure` outcomes | `record` with `sealed interface` when fitting | Each variant carries distinct components, handled by type |
| Order with ID and status moving from draft to submitted | `class` | Has identity, lifecycle, and state-mutating behavior |
| Account with balance, debit, and credit rules | `class` or suitable aggregate | State changes need control per business rules, transactions, and concurrency |
| Immutable object needing hidden internal representation or inheritance | `class` | Records expose components publicly and are implicitly `final` |

### Value Objects with Records

```java
import java.util.Currency;
import java.util.Objects;

public record Money(long minorUnits, Currency currency) {
    public Money {
        Objects.requireNonNull(currency, "currency");
    }

    public Money plus(Money other) {
        Objects.requireNonNull(other, "other");
        if (!currency.equals(other.currency())) {
            throw new IllegalArgumentException("Currency mismatch");
        }
        return new Money(Math.addExact(minorUnits, other.minorUnits()), currency);
    }
}
```

`Money` does not mutate the current instance when adding: `plus` returns **a new Money**. `Math.addExact` detects integer overflow; addition only permits two amounts in the same currency. `minorUnits` is the smallest unit per the chosen model (such as cents in some currencies); real systems must explicitly define unit and rounding rules per currency rather than assuming every currency uses two decimal places. Whether negatives or positives are allowed depends on the specific domain invariant (adjustments, refunds, receivables, etc.).

Crucial point: value objects **have business behavior**. There is no need to turn it into a class merely because it has methods like `plus`, `overlaps`, `contains`, or `isValidFor`; a record can still express a value with meaningful operations.

### Entities/Aggregates with Classes

Suppose an order must:

- Keep an unchanging identifier throughout its lifecycle.
- Only allow adding lines while still in draft status.
- Only submit when at least one line exists.
- Expose only **snapshots** externally, never leaking its internal list for callers to mutate arbitrarily.

A class with private fields and business methods expresses this model more clearly than a record with public component accessors. A model can use **classes for aggregates**, **records for internal value objects**, and **records for output DTOs** at the same time; there is no need to force everything into one form.

## 4. Complete Example: Records for DTOs and Value Objects, Class for Order

The example below uses features official in Java 17, with no external libraries. Save as `RecordClassChoiceDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.UUID;

public class RecordClassChoiceDemo {

    // Input DTO: holds data arriving from caller, quantity may be absent.
    public record AddLineRequest(String productCode, Integer quantity) {}

    // Value object: value invariant is always enforced on creation.
    public record ProductCode(String value) {
        public ProductCode {
            value = Objects.requireNonNull(value, "value")
                    .strip()
                    .toUpperCase(Locale.ROOT);
            if (value.isEmpty()) {
                throw new IllegalArgumentException("productCode must not be blank");
            }
        }
    }

    // Output DTO: carries only data needed externally.
    public record LineView(String productCode, int quantity, long unitPriceCents) {}

    public record OrderView(
            String orderId,
            String status,
            List<LineView> lines,
            long totalCents) {

        public OrderView {
            Objects.requireNonNull(orderId, "orderId");
            Objects.requireNonNull(status, "status");
            lines = List.copyOf(Objects.requireNonNull(lines, "lines"));
            if (totalCents < 0) {
                throw new IllegalArgumentException("totalCents must not be negative");
            }
        }
    }

    // Aggregate: has identity and changes state via business operations.
    public static final class Order {
        private enum Status { DRAFT, SUBMITTED }

        private record OrderLine(
                ProductCode productCode,
                int quantity,
                long unitPriceCents) {

            private OrderLine {
                Objects.requireNonNull(productCode, "productCode");
                if (quantity <= 0) {
                    throw new IllegalArgumentException("quantity must be positive");
                }
                if (unitPriceCents < 0) {
                    throw new IllegalArgumentException("price must not be negative");
                }
            }
        }

        private final UUID id;
        private final List<OrderLine> lines = new ArrayList<>();
        private Status status = Status.DRAFT;

        public Order(UUID id) {
            this.id = Objects.requireNonNull(id, "id");
        }

        public void addLine(ProductCode code, int quantity, long unitPriceCents) {
            if (status != Status.DRAFT) {
                throw new IllegalStateException("Cannot add lines after submission");
            }
            lines.add(new OrderLine(code, quantity, unitPriceCents));
        }

        public void submit() {
            if (status != Status.DRAFT) {
                throw new IllegalStateException("Order was already submitted");
            }
            if (lines.isEmpty()) {
                throw new IllegalStateException("Cannot submit an empty order");
            }
            status = Status.SUBMITTED;
        }

        public OrderView snapshot() {
            List<LineView> views = new ArrayList<>();
            long total = 0;

            for (OrderLine line : lines) {
                total = Math.addExact(total,
                        Math.multiplyExact(line.quantity(), line.unitPriceCents()));
                views.add(new LineView(
                        line.productCode().value(),
                        line.quantity(),
                        line.unitPriceCents()));
            }

            return new OrderView(
                    id.toString(), status.name(), views, total);
        }
    }

    public static void main(String[] args) {
        AddLineRequest request = new AddLineRequest(" p-17 ", 2);
        if (request.quantity() == null) {
            throw new IllegalArgumentException("quantity is required");
        }

        Order order = new Order(
                UUID.fromString("00000000-0000-0000-0000-000000000017"));
        order.addLine(new ProductCode(request.productCode()),
                request.quantity(), 1_250);

        System.out.println(order.snapshot().status());
        order.submit();

        OrderView response = order.snapshot();
        System.out.println(response.status());
        System.out.println(response.totalCents());
        System.out.println(response.lines().get(0).productCode());
    }
}
```

Run with JDK 17:

```bash
javac --release 17 RecordClassChoiceDemo.java
java RecordClassChoiceDemo
```

Expected output:

```text
DRAFT
SUBMITTED
2500
P-17
```

In the example:

1. `AddLineRequest` accepts input data, **without claiming** every input combination is a valid domain value.
2. `ProductCode` is a value object: equal normalized codes are equal by value.
3. `OrderLine` is an internal record rejecting non-positive quantities and negative prices.
4. `Order` is a class with an ID and `addLine`/`submit` methods. Callers cannot alter state with setters or access the `lines` list directly.
5. `OrderView` and `LineView` are snapshots/DTOs. Once `OrderView` is created, updating `Order` does not alter the older snapshot. The list in `OrderView` is defensively copied.

This is an in-memory aggregate example without transaction or concurrent-access handling; real applications may require transactions and optimistic locking when multiple processes modify the same order. The notable design point is that each type fulfills **its own responsibility**, rather than forcing one record/class choice across the whole project.

## 5. Records Do Not Mean Deep Immutability

A record has no auto-generated setters and its component fields are `final`. However, a **`final` reference** does not mean **the referenced object cannot change**:

```java
import java.util.ArrayList;
import java.util.List;

record UnsafeTags(List<String> values) {}

List<String> original = new ArrayList<>(List.of("java"));
UnsafeTags tags = new UnsafeTags(original);
original.add("changed");

System.out.println(tags.values()); // [java, changed]
```

To keep a DTO or value object's list from being mutated via the original list:

```java
import java.util.List;
import java.util.Objects;

record Tags(List<String> values) {
    public Tags {
        values = List.copyOf(Objects.requireNonNull(values, "values"));
    }
}
```

`List.copyOf` creates an unmodifiable list and rejects `null` elements. Still, when elements are mutable types like `List<MutableAddress>`, objects inside the list can still be mutated. Deep immutability requires choosing immutable element types or copying properly, including across nested structures.

### Special Attention with Arrays

```java
record Bytes(byte[] data) {}
```

`Bytes` does not automatically copy the array. Callers can mutate the array after record creation, and the `data()` accessor returns the raw array reference. Furthermore, generated `equals` for an array component compares **array references**, not deep byte-by-byte equality. For array-backed types, design explicit copying and equality mechanisms or replace with another immutable value type; **records do not handle these automatically**.

## 6. Value Equality vs. Identity Equality

Two records of the same type with equivalent components are considered equal under generated `equals`:

```java
record Point(int x, int y) {}

Point a = new Point(3, 5);
Point b = new Point(3, 5);
System.out.println(a.equals(b)); // true
```

If an order is modeled as `record Order(long id, String status, long total)`, changing `status` or `total` produces a new record **not equal** to the old one, even though both describe the same order with ID 123. That can conflict with how an entity defines **identity by ID**. For entities, deliberately define the equality/identity contract, especially when using ORMs, proxies, and persistence-assigned IDs.

Conversely, not every class carries identity: an immutable `final class Color` can deliberately override value-based `equals`/`hashCode` and still be clean. Choose the construct based on **domain semantics** first, syntax second.

### When Should You Avoid Record-Generated Equality?

- Only a subset of components defines equality, while other components are auxiliary data.
- A component is an array needing content comparison.
- A value requires normalization before comparison, such as a case-insensitive code.
- The object has fixed identity even when state changes.

A record can override `equals` and `hashCode` when necessary, yet if you have to heavily override its default data and equality contract, consider whether an **immutable class** communicates the model better. When using records as keys in `HashMap`/`HashSet`, components and equality must remain stable over time; avoid holding mutable references that alter observable values.

## 7. A Record's Public Structure Affects API Evolution

When you write:

```java
public record CustomerView(String name, String email) {}
```

both components are an explicit part of the API: callers can invoke the canonical constructor `new CustomerView(name, email)` and accessors `name()`, `email()`. If you later change it to:

```java
public record CustomerView(String name, String email, String phone) {}
```

the old two-parameter constructor is no longer auto-generated by the record. Java callers may need updates or the developer must add a compatibility overload:

```java
public record CustomerView(String name, String email, String phone) {
    public CustomerView(String name, String email) {
        this(name, email, null);
    }
}
```

Record auxiliary constructors must delegate to the canonical constructor per Java rules. Adding a component also changes `equals`, `hashCode`, `toString`, reflection components, and can affect framework serialization/binding.

A regular class can be easier when you need to **hide internal fields**, keep old constructors/factories, and evolve representation without breaking the entire API. Even so, any change to DTOs sent over HTTP/JSON/messages must consider **consumer compatibility**, not only Java compilation; adding a JSON field may be harmless for some clients yet break clients enforcing strict schemas.

Tip: DTOs for stable APIs should have an explicit versioning/schema strategy, and mappers should decouple domain models from public representations when the two evolve at different paces.

## 8. Framework Requirements May Dictate Using a Class

### REST and JSON Libraries

Records work well for request/response DTOs when the framework supports Java records and is configured accordingly. Before adopting them in an existing project, check **the actual serialization library version**, constructor/component mapping, annotations, null handling, and polymorphic type handling. Do not assume every library supports records identically just because the app runs on JDK 17.

In particular, records used as **responses** face fewer constraints than records used as **patch requests**: responses represent complete snapshots, whereas patches often need to represent distinct field-presence states.

### JPA/Hibernate and Persistence Entities

JPA entities normally require contracts around constructors, identity, lifecycle, and state management; many usages also depend on proxies, lazy loading, or dirty checking. Because records are `final`, lack a default no-arg constructor, and have `final` component fields, they are **not portable choices for standard JPA entities**.

For JPA entities, classes are usually more natural:

```java
// Entity structure sketch, not a standalone runnable example.
@Entity
public class OrderEntity {
    @Id
    private Long id;

    private String status;

    protected OrderEntity() {
        // Constructor for persistence provider.
    }

    // Operations and mappings per application contract.
}
```

The annotations in this snippet belong to whichever JPA API the project selects; the example merely illustrates how an entity class satisfies the provider's constructor requirement. **Domain entities** and **persistence entities** do not have to be the same class: in layered architectures, repositories can map between JPA entities and domain models with their own rules.

Some providers and framework versions support records for DTO projections, constructor results, or special value mappings; that capability **does not mean** any record can replace a JPA entity. When using `@Embeddable`, projections, or provider-specific features, check the documentation for your exact provider version.

### JavaBeans and Getter/Setter-Based Libraries

Some legacy libraries, form binders, or mappers rely on JavaBeans conventions `getName()`, `setName()`, and a no-arg constructor. A record's auto-generated accessor is `name()`, not `getName()`; therefore, check whether the library supports record components and canonical constructors. Do not add fake setters to a record or warp your whole model just to appease a library that could be wired with an appropriate mapper.

## 9. Records Are Not an Automatic Performance Optimization

Both records and classes are reference types in Java 17 and are allocated as objects like normal classes. **Records are not automatically stack-allocated, do not automatically occupy less memory, do not automatically avoid allocation, and do not automatically have faster access than an equivalent class**.

The main benefits of records are **clear data contracts, concise declaration syntax, and consistently generated standard methods**. If memory or performance optimization is a key requirement, measure with real workloads on your target JVM; do not choose records assuming they are faster.

Likewise, records are not synonymous with JVM-level *value types*. Language/JVM features under development in other releases must not be assumed to exist in Java 17.

## 10. Using Records with `sealed` for Multi-Variant Business Outcomes

A strong pattern is using a **sealed interface** for the possible outcome set and records for each variant's data:

```java
import java.util.Objects;

sealed interface PaymentResult permits Paid, Declined {}

record Paid(String transactionId) implements PaymentResult {
    Paid {
        transactionId = Objects.requireNonNull(transactionId, "transactionId").strip();
        if (transactionId.isEmpty()) {
            throw new IllegalArgumentException("transactionId is required");
        }
    }
}

record Declined(String reason) implements PaymentResult {
    Declined {
        reason = Objects.requireNonNull(reason, "reason").strip();
        if (reason.isEmpty()) {
            throw new IllegalArgumentException("reason is required");
        }
    }
}
```

Here `sealed` controls which direct variants may implement `PaymentResult`, while record constructors validate each variant's **values**. If an in-flight payment needs mutable tracking (ID, retries, status transitions), a separate aggregate class can still manage that lifecycle.

In Java 17, pattern matching with `instanceof` can handle outcomes:

```java
static String describe(PaymentResult result) {
    Objects.requireNonNull(result, "result");
    if (result instanceof Paid paid) {
        return "Paid: " + paid.transactionId();
    }
    if (result instanceof Declined declined) {
        return "Declined: " + declined.reason();
    }
    throw new IllegalStateException("Unhandled result");
}
```

An `if/instanceof` chain **is not exhaustiveness-checked by the Java 17 compiler** against the sealed hierarchy. When adding a new permitted subtype, audit all handling sites. Pattern matching for `switch` and record patterns became standard only in Java 21, so do not use Java 21 syntax in examples requiring stable Java 17 compilation.

## 11. Data Security and Auto-Generated `toString()`

Records generate `toString()` containing component names and values. This is convenient in logs and debugging for non-sensitive data, yet can **accidentally leak sensitive info into logs**:

```java
record LoginRequest(String username, String password) {}

LoginRequest request = new LoginRequest("lan", "secret");
// Do not log request directly when it contains passwords/tokens/sensitive info.
```

When a DTO carries secrets or personal data, choose an appropriate logging policy: avoid logging whole objects, actively redact fields, and limit returned data. You can override `toString()` if needed, yet **do not rely solely on `toString()`** to conceal data across all serialization, debugging, and monitoring paths.

## 12. When an Immutable Class Fits Better than a Record

Not everything immutable has to be a record. For example, a type that wants to hide storage behind a cache or expose a specific method set rather than raw components:

```java
import java.util.Objects;

public final class NormalizedCode {
    private final String normalized;

    private NormalizedCode(String normalized) {
        this.normalized = normalized;
    }

    public static NormalizedCode of(String raw) {
        String value = Objects.requireNonNull(raw, "raw").strip();
        if (value.isEmpty()) {
            throw new IllegalArgumentException("code must not be blank");
        }
        return new NormalizedCode(value);
    }

    public String asText() {
        return normalized;
    }

    @Override
    public boolean equals(Object other) {
        return this == other || (other instanceof NormalizedCode code
                && normalized.equals(code.normalized));
    }

    @Override
    public int hashCode() {
        return normalized.hashCode();
    }
}
```

`NormalizedCode` is still an **immutable value object**, yet it controls its own `of`/`asText` API, private constructor, and representation. Records can have auxiliary factories, yet a record's canonical constructor and components/accessors always remain a core part of its contract. When you want to **avoid publishing the component list** or when equality must be independent of auxiliary technical fields, a class can be the better fit.

If you choose a class for immutability, do not forget to implement the safeguards a record normally gives you: `final` fields, constructor/factory validation, avoiding leaking mutable references, and accurate `equals`/`hashCode` when value equality is needed.

## 13. Common Mistakes When Converting DTOs or Domain Classes to Records

| Mistake | Why It Causes Problems | How to Handle |
| --- | --- | --- |
| Converting all entities to records for less code | Entities typically have identity, lifecycle, persistence mapping, and update behavior | Evaluate entities/aggregates separately; classes are usually clearer |
| Treating every record as deeply immutable | List, array, or mutable-object components can still be mutated indirectly | Copy defensively and choose immutable components |
| Validating DTOs only in controllers | Domain objects may be created via multiple other paths | Enforce core invariants in value objects/aggregates |
| Using records for public APIs while frequently changing components | A record's canonical constructor and accessors are a direct contract | Separate API DTOs from domain; apply versioning/mapping when needed |
| Assuming records automatically work with all JSON/ORM libraries | Mapping support depends on library version and configuration | Test real integration; use classes/mappers where suitable |
| Using a record for a continuously changing entity and recreating it on every action | Equality, identity, and lifecycle management can become confusing | Consider an aggregate class or a controlled immutable state model |
| Using a record holding an array as a map key | Arrays are mutable and default equality is reference-based | Use an immutable representation and appropriate equality |
| Logging record DTOs containing passwords/tokens | `toString()` can emit components into logs | Redact and control logging/serialization |
| Thinking records must be pure DTOs with no methods | Records can define behavior and invariants | Use records for value objects with fitting behavior |
| Thinking classes cannot be immutable | Classes can be `final` with `final` fields and validated constructors/factories | Use an immutable class when hiding representation |
| Assuming records always outperform classes in CPU/RAM | Java 17 still allocates and manages records as reference objects | Choose for semantics; benchmark if performance matters |

## 14. Decision Process in a Java 17 Project

For a new type, decide in order:

1. **Does the type represent data or an object with a lifecycle?** If mainly data constructed and read, consider a record. If it has identity, mutation, and state transitions, evaluate a class first.
2. **Should two instances be equal when their components are equal?** If yes, a record is natural. If equality relies on an ID or custom contract, design a class/equality deliberately.
3. **Can data change indirectly via collections/arrays?** If yes, design a defensive copying strategy. Records do not protect mutable contents automatically.
4. **Does this type sit on an API boundary?** For DTOs, distinguish requests from responses; consider schemas, null/missing fields, validation, and version evolution.
5. **Does a framework require specific constructors or inheritance/proxy mechanisms?** If yes, verify concrete record support; JPA entities typically use classes.
6. **Does the type enforce domain invariants?** Use constructors/factories to reject invalid values; use services/aggregates for contextual rules.
7. **Is the component structure the desired public contract?** If you need to hide representation or evolve it independently of the API, an immutable class is often easier to evolve.

### Quick Selection Flow

```text
Type being designed
        |
        +-- Needs ID/lifecycle/state transitions? -- Yes --> entity/aggregate class
        |                                                    (can use records internally)
        |
        +-- Mainly transferring data across API? --- Yes --> record DTO if
        |                                                    framework/schema fits
        |
        +-- Value object with clear components? ---- Yes --> record + constructor
        |                                                    enforcing invariants
        |
        +-- Needs hidden structure, class inheritance,
            or special equality/implementation? ---- Yes --> class (possibly immutable)
```

This flow is a guiding aid, not a substitute for analyzing specific requirements. An application can seamlessly combine **records for input/output DTOs**, **records for value objects**, **sealed interfaces for multi-variant outcomes**, and **classes for aggregates/entities**. In Java 17, that split preserves the concise syntax of records while safeguarding the semantics, immutability, and lifecycles of the domain model.
