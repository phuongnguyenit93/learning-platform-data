# Documenting Permitted Subtypes in Java Pattern Matching

## 1. Why is the list of permitted subtypes an important part of the API?

When designing a Java API with a `sealed class` or `sealed interface`, a major design decision is **which types are allowed to directly extend or implement** the root type. Java lets you express this decision using the `permits` clause:

```java
sealed interface OrderEvent permits Placed, Cancelled, FulfillmentEvent {
}
```

This clause is a **language-level constraint**, not just a comment: apart from the directly permitted types `Placed`, `Cancelled`, and `FulfillmentEvent`, no other type can directly `implements OrderEvent` in a valid program.

However, when **documenting an API**, simply copying class names from `permits` is not enough. API consumers need to understand:

- This list contains **direct subtypes**, not necessarily every concrete subtype that may appear at runtime.
- Whether each permitted subtype is **`final`**, **`sealed`**, or **`non-sealed`**, because those three choices determine how extensible each branch is.
- What business cases each type represents, which data components are guaranteed, and which cases require handling such as `null` or invalid data.
- Which types a `switch` with type/record patterns can treat as **exhaustive**, and which cases should have a fallback.
- When the library adds a new subtype, whether client code needs to **recompile** or add handling.
- Whether extensibility is a **long-term commitment** or only reflects the current structure of the API version.

In Java, **sealed types** became standard in Java 17 (JEP 409). **Pattern matching for `switch`** and **record patterns** became standard in Java 21 (JEP 441 and JEP 440). Therefore, a sealed hierarchy can be used in a library targeting Java 17, while handling it via pattern `switch` as shown in this lesson requires Java 21+.

**Lesson goal:** write documentation that is both accurate with respect to the compiler's `permits` rules and genuinely helpful for JavaDoc readers, pattern-switch authors, maintainers, and library release managers.

## 2. Distinguishing direct, indirect, and concrete implementations

Consider the inheritance tree:

```text
OrderEvent  (sealed interface)
├── Placed                 (record, implicitly final)
├── Cancelled              (record, implicitly final)
└── FulfillmentEvent       (non-sealed interface)
    ├── Packed             (record)
    ├── Shipped            (record)
    └── CustomerPickup     (record)
         ... other subtypes may be added later
```

The `permits` list of `OrderEvent` only contains:

```text
Placed, Cancelled, FulfillmentEvent
```

It does **not** directly list `Packed`, `Shipped`, or `CustomerPickup`, because those types implement **`FulfillmentEvent`**, not `OrderEvent` directly.

There are three concepts that should be recorded accurately in the documentation:

| Concept | Meaning | In the example |
| --- | --- | --- |
| **Permitted direct subtype** | A type declared in the sealed parent's `permits` clause that directly extends/implements the parent | `Placed`, `Cancelled`, `FulfillmentEvent` |
| **Indirect subtype** | A type that inherits from the parent through one or more intermediate levels | `Packed`, `Shipped`, `CustomerPickup` |
| **Concrete subtype** | A type that can be instantiated and used as an instance of the parent | The three records above together with `Placed`, `Cancelled` |

**Do not equate “permitted” with “all objects that can actually be encountered”.** A `non-sealed` branch allows additional subtypes to extend beneath it. Therefore, documenting “there are only three event types at runtime” is wrong if one of the three permitted branches remains open for extension.

For a completely closed hierarchy (every branch terminates at `final` or continues as `sealed` and eventually terminates), you can document the current set of concrete subtypes. Even then, it is still best to distinguish the **direct** set of each sealed node from the **leaf** set of the entire tree.

## 3. Compiler rules for `sealed`, `permits`, and permitted subtypes

### 3.1. A permitted subtype must inherit directly

```java
sealed interface Command permits Start, Stop {}

record Start(String id) implements Command {}
record Stop(String id) implements Command {}
```

Both records directly implement `Command`, so they are permitted. However, you cannot simply add the name of a class that **only inherits indirectly** to `Command`'s `permits` clause to make it a direct subtype. The parent must list its exact direct children.

Example of a valid indirect inheritance path:

```java
sealed interface Command permits Task {}
non-sealed interface Task extends Command {}
record StartTask(String id) implements Task {}
```

Here `Command` only `permits Task`. `StartTask` is an indirect subtype via `Task`, so it neither needs to be nor should be listed in `Command`'s `permits` clause.

### 3.2. A direct subtype must decide whether to allow further inheritance

A class or interface that directly inherits from a sealed type must have one of the valid modifiers:

- **`final`:** terminates the inheritance chain at that class. A record class is implicitly `final`.
- **`sealed`:** continues restricting its own direct subtypes using `permits`.
- **`non-sealed`:** reopens the inheritance chain on that branch; there is no `permits` list for the `non-sealed` branch itself.

Example:

```java
sealed interface Result permits Success, Failure, Retryable {}

record Success(String data) implements Result {}

final class Failure implements Result {
    final String message;
    Failure(String message) { this.message = message; }
}

non-sealed interface Retryable extends Result {
    boolean shouldRetry();
}
```

This is valid Java 17+ code when the declarations are placed in an appropriate compilation context. `Success` is a record (implicitly final), `Failure` is explicitly final, and `Retryable` can be extended further. **Documentation should clearly state which branches are open**, rather than just listing `Success, Failure, Retryable`.

If an interface directly extends a sealed interface without specifying `sealed` or `non-sealed`, the compiler rejects it. Likewise, a class that directly extends a sealed class without being `final`, `sealed`, or `non-sealed` as required is also invalid.

### 3.3. `non-sealed` is not the default state of every interface

The `non-sealed` keyword is only used when a type directly inherits from a relevant sealed type. Do not arbitrarily add `non-sealed` to an ordinary interface that has no sealed parent just to “say that it is extensible”. For ordinary interfaces, extensibility is already the default.

### 3.4. Module/package scope is part of the constraint

A direct permitted subtype must belong to a code scope compatible with the sealed parent:

- If the sealed type is in a **named module**, the direct permitted subtype must be in the **same module**.
- If the sealed type belongs to an **unnamed module**, the direct permitted subtype must be in the **same package** as the sealed type.

This means a library publishing a public sealed parent cannot invite users in another module to arbitrarily write a new **direct implementation** of that parent. To support client-side extension, design a public `non-sealed` branch within the library's module, and let clients implement that branch.

Explicitly document the supported **extension point** (if any). Do not write in JavaDoc “clients can implement `OrderEvent`” if the sealed parent does not allow it.

### 3.5. `permits` can be inferred under appropriate compilation conditions

In cases where all direct subtypes reside in the same compilation unit as the sealed parent, Java can infer the permitted subclasses set when the `permits` clause is omitted. However, public API documentation should make the subtypes clear with a verifiable description, and an explicit `permits` clause often helps readers and reviewers recognize the architectural decision more quickly.

**Do not rely on vague JavaDoc to replace compiler rules.** `permits` (or the compiler-inferred subtype set) is the actual constraint. JavaDoc supplements it with **domain semantics and API evolution policy** that syntax alone cannot express.

## 4. What should be documented for a sealed API?

Good documentation has at least four layers:

### 4.1. Semantic layer: what does the sealed parent represent?

For example: “`OrderEvent` is an immutable event describing a notable state change in an order's lifecycle.” This answers *why the root type exists*, not just “this is a sealed interface”.

### 4.2. Structural layer: what are the **direct permitted subtypes**?

List their names and explain them:

| Direct subtype | Structure | Meaning |
| --- | --- | --- |
| `Placed` | Record, final | The order has just been created |
| `Cancelled` | Record, final | The order was cancelled |
| `FulfillmentEvent` | Non-sealed interface | Family of order fulfillment events, open for other implementations |

A comment like “Possible event types: `Placed`, `Cancelled`, `FulfillmentEvent`” is easily misread as “there are only three concrete events”; add the word **direct** and state clearly that the third branch is **open**.

### 4.3. Contract layer: how should clients handle it?

Specify the supported branching model, required properties, `null` policy, and relevant exceptions. For example, for Java 21 clients: “An exhaustive switch on `OrderEvent` can handle `Placed`, `Cancelled`, and a general `case FulfillmentEvent`.” If you want to distinguish specific current fulfillment events, handle the specific cases first, while still keeping a `FulfillmentEvent` case to cover new subtypes of the open branch.

### 4.4. Evolution layer: is the API stable?

State whether the library may add subtypes in future updates and how clients should respond. Being “sealed” **is not by itself a promise that the subtype list will never change across versions**; that is a versioning/release policy declared by the API owner.

Documentation should distinguish:
- Restrictions **enforced by the compiler in the current version**.
- **Source compatibility** guarantees when upgrading the library.
- **Binary/runtime compatibility** guarantees for already-compiled clients.

Do not make absolute claims like “every client will always keep working” merely because the root type is sealed.

## 5. Complete Java 21 example with JavaDoc and reflection

The following example demonstrates an API with an open branch, the use of pattern `switch`, and reading **direct permitted subclasses** via reflection. Save it verbatim as **`PermittedSubtypeDocsDemo.java`**.

```java
import java.util.Arrays;
import java.util.stream.Collectors;

public class PermittedSubtypeDocsDemo {
    /**
     * Domain contract for an order event.
     *
     * <p>Direct permitted subtypes: Placed, Cancelled,
     * and FulfillmentEvent.
     *
     * @apiNote FulfillmentEvent is an open extension branch.
     *          Consumers should handle that branch as a whole
     *          unless their use case needs more detail.
     * @since 17
     */
    public sealed interface OrderEvent
            permits Placed, Cancelled, FulfillmentEvent {}

    /** An order was placed. */
    public record Placed(
            String orderId, String customerId) implements OrderEvent {}

    /** An order was cancelled. */
    public record Cancelled(
            String orderId, String reason) implements OrderEvent {}

    /**
     * Open family of events concerned with fulfillment.
     * Other implementations may be added without changing
     * the direct permitted subtype set of OrderEvent.
     */
    public non-sealed interface FulfillmentEvent extends OrderEvent {
        String orderId();
    }

    public record Packed(
            String orderId, int boxCount) implements FulfillmentEvent {}

    public record Shipped(
            String orderId, String destinationCity) implements FulfillmentEvent {}

    public record CustomerPickup(
            String orderId) implements FulfillmentEvent {}

    // Java 21: exhaustive because all three direct branches are covered.
    static String describe(OrderEvent event) {
        return switch (event) {
            case Placed(var orderId, var customerId) ->
                    "placed:" + orderId + ":" + customerId;
            case Cancelled(var orderId, var reason) ->
                    "cancelled:" + orderId + ":" + reason;
            case FulfillmentEvent fulfillment ->
                    "fulfillment:" + fulfillment.orderId();
        };
    }

    // Specific patterns first, open-branch pattern last.
    static String detail(OrderEvent event) {
        return switch (event) {
            case Placed(var orderId, var customerId) -> "placed";
            case Cancelled(var orderId, var reason) -> "cancelled";
            case Packed(var orderId, var boxCount) ->
                    "packed:" + boxCount;
            case Shipped(var orderId, var destinationCity) ->
                    "shipped:" + destinationCity;
            case FulfillmentEvent fulfillment ->
                    "other-fulfillment:" + fulfillment.orderId();
        };
    }

    // Reflection returns direct permitted subclasses only.
    static String permittedDirectNames(Class<?> sealedType) {
        Class<?>[] directTypes = sealedType.getPermittedSubclasses();
        if (directTypes == null) return "not-sealed";

        return Arrays.stream(directTypes)
                .map(Class::getSimpleName)
                .sorted()
                .collect(Collectors.joining(","));
    }

    public static void main(String[] args) {
        System.out.println(
                "root.sealed=" + OrderEvent.class.isSealed());
        System.out.println(
                "root.permits=" + permittedDirectNames(OrderEvent.class));
        System.out.println(
                "fulfillment.sealed=" + FulfillmentEvent.class.isSealed());
        System.out.println(
                "fulfillment.permits="
                        + permittedDirectNames(FulfillmentEvent.class));

        System.out.println("event1="
                + describe(new Placed("O-1", "C-1")));
        System.out.println("event2="
                + describe(new Cancelled("O-2", "duplicate")));
        System.out.println("event3="
                + describe(new Packed("O-3", 2)));

        System.out.println("detail1="
                + detail(new Packed("O-3", 2)));
        System.out.println("detail2="
                + detail(new Shipped("O-4", "Hue")));
        System.out.println("detail3="
                + detail(new CustomerPickup("O-5")));
    }
}
```

Compile and run with JDK 21 or newer:

```bash
javac --release 21 -encoding UTF-8 PermittedSubtypeDocsDemo.java
java PermittedSubtypeDocsDemo
```

**Exact output:**

```text
root.sealed=true
root.permits=Cancelled,FulfillmentEvent,Placed
fulfillment.sealed=false
fulfillment.permits=not-sealed
event1=placed:O-1:C-1
event2=cancelled:O-2:duplicate
event3=fulfillment:O-3
detail1=packed:2
detail2=shipped:Hue
detail3=other-fulfillment:O-5
```

### Explaining the output

- `OrderEvent.class.isSealed()` is `true`: the root hierarchy restricts its direct children.
- `getPermittedSubclasses()` returns **`Cancelled`, `FulfillmentEvent`, `Placed`** after sorting by name. **Neither `Packed` nor `Shipped` is present** because they are indirect implementations of `OrderEvent`.
- `FulfillmentEvent.class.isSealed()` is `false` and `getPermittedSubclasses()` returns `null` for a non-sealed interface; the demo method formats this as `"not-sealed"`.
- `describe` has three cases covering the three **direct permitted branches**, so it is exhaustive without needing a `default` for non-`null` instances.
- `detail` places the specific `Packed` and `Shipped` cases before the broader `FulfillmentEvent` case. The new `CustomerPickup` still falls into the open branch's fallback, producing `other-fulfillment:O-5`.
- Even though the example defines three fulfillment types, `FulfillmentEvent`'s documentation should not promise that “there are only three types”. Any valid implementation of the open interface belongs to the `FulfillmentEvent` family.

The example has been verified in Java 21 language mode. Sorting names with `sorted()` is intentional: the natural order of the array returned by reflection **should not be treated as an API ordering contract**.

## 6. Reflection helps verify documentation, but only shows one layer of information

Since Java 17, `java.lang.Class` provides two related methods:

```java
boolean isSealed();
Class<?>[] getPermittedSubclasses();
```

For a sealed class/interface:
- `isSealed()` is `true`.
- `getPermittedSubclasses()` returns the list of classes/interfaces **permitted to inherit directly**. These classes/interfaces are represented by `Class<?>` objects.

For a non-sealed type:
- `isSealed()` is `false`.
- `getPermittedSubclasses()` returns `null`, **not** an automatic list of all subtypes that may exist.

Therefore, the following is an **incorrect check**:

```java
// CONCEPTUALLY WRONG: getPermittedSubclasses() is not
// a function that lists every subtype at every level of the tree.
var descendants = OrderEvent.class.getPermittedSubclasses();
// Cannot infer here that Packed is an unsupported type.
```

To understand the entire tree, you must inspect each direct permitted type in turn:
- If a subtype is `final`, there are no further inheritance branches below it.
- If a subtype is `sealed`, inspect its own list of permitted direct subtypes.
- If a subtype is `non-sealed`, the tree opens at that branch; you cannot infer all descendants from the sealed root's `permits` clause.

A documentation-generation or validation tool using reflection can produce the **direct** list for each sealed node. However, an API with plugin implementations or dynamically loaded classes should not claim to have enumerated every subtype of an open branch through a single reflection call.

### A unit test to guard the direct subtype list

The following JUnit 5 snippet is based on `PermittedSubtypeDocsDemo` and can be placed in the same package (with JUnit 5 on the test classpath):

```java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;

class PermitsContractTest {
    @Test
    void permittedDirectTypesAreDocumented() {
        Class<?>[] permitted =
                PermittedSubtypeDocsDemo.OrderEvent.class
                        .getPermittedSubclasses();

        assertNotNull(permitted);
        Set<Class<?>> actual = Arrays.stream(permitted)
                .collect(Collectors.toSet());

        assertEquals(Set.of(
                PermittedSubtypeDocsDemo.Placed.class,
                PermittedSubtypeDocsDemo.Cancelled.class,
                PermittedSubtypeDocsDemo.FulfillmentEvent.class),
                actual);
    }

    @Test
    void fulfillmentBranchIsOpen() {
        assertFalse(
                PermittedSubtypeDocsDemo.FulfillmentEvent.class.isSealed());
        assertNull(
                PermittedSubtypeDocsDemo.FulfillmentEvent.class
                        .getPermittedSubclasses());
    }
}
```

The first test guards the **published direct subtype set**, and the second test guards the **open-branch policy**. A change such as adding a direct subtype to `OrderEvent` will cause the first test to fail, reminding maintainers to review JavaDoc, client switches, and versioning policy.

**You should not always hard-lock the list with a test.** If the API is designed to add direct subtypes in future versions, the test can act as a *change detection gate* requiring review/documentation updates, rather than making people assume adding a subtype is always wrong.

## 7. Documenting closed branches, nested sealed branches, and open branches

The three declaration styles express three different policies.

### 7.1. Branch closed by a record or `final`

```java
sealed interface PaymentResult permits Paid, Rejected {}
record Paid(String receiptId) implements PaymentResult {}
record Rejected(String errorCode) implements PaymentResult {}
```

Both `Paid` and `Rejected` are records, implicitly `final`. In this version, the directly modeled set of concrete subtypes is closed, and a pattern switch can cover the two cases.

Appropriate documentation: “PaymentResult represents a payment outcome; the two current cases are `Paid` and `Rejected`. When a new case is added in an API release, exhaustive clients must be reviewed.”

### 7.2. Branch that remains `sealed` across multiple levels

```java
sealed interface Operation permits ReadOp, WriteOp {}
record ReadOp(String key) implements Operation {}

sealed interface WriteOp extends Operation permits PutOp, DeleteOp {}
record PutOp(String key, String value) implements WriteOp {}
record DeleteOp(String key) implements WriteOp {}
```

`Operation` has two direct permitted subtypes: `ReadOp` and `WriteOp`. `WriteOp` in turn has two direct permitted subtypes: `PutOp` and `DeleteOp`.

Documentation should use a **two-level** diagram or table, rather than listing `PutOp` as a direct permitted subtype of `Operation`.

```text
Operation (sealed)
├── ReadOp (final record)
└── WriteOp (sealed)
    ├── PutOp (final record)
    └── DeleteOp (final record)
```

### 7.3. Branch opened with `non-sealed`

```java
sealed interface Message permits TextMessage, ExtensionMessage {}
record TextMessage(String text) implements Message {}

non-sealed interface ExtensionMessage extends Message {
    String extensionId();
}
```

Appropriate documentation: “`Message` permits only two direct subtypes; `ExtensionMessage` is an **extension point** that may have multiple implementations, including client implementations if properly exported/exposed by the API.”

**Do not write** “Message only accepts TextMessage and ExtensionMessage as two instantiable classes”. `ExtensionMessage` is an interface and allows further subtypes beneath it. When saying “two”, specify “two **direct permitted branches**”.

## 8. Documenting how to write an exhaustive pattern switch

One of the major benefits of a sealed hierarchy is that the compiler can prove a `switch` with patterns covers every required direct branch, **without needing a blind `default`**.

Based on `OrderEvent` from the full program:

```java
static String category(
        PermittedSubtypeDocsDemo.OrderEvent event) {
    return switch (event) {
        case PermittedSubtypeDocsDemo.Placed placed -> "placed";
        case PermittedSubtypeDocsDemo.Cancelled cancelled -> "cancelled";
        case PermittedSubtypeDocsDemo.FulfillmentEvent fulfillment ->
                "fulfillment";
    };
}
```

This is an **illustrative snippet** meant to be placed in a valid Java 21 class. It expresses clear intent: each direct permitted branch has a case.

For a sealed root with a `non-sealed` branch, **you cannot just list the currently known concrete implementations** of the open branch and assume exhaustiveness. For example:

```java
// INTENTIONALLY NON-EXHAUSTIVE with non-sealed FulfillmentEvent.
return switch (event) {
    case Placed placed -> "placed";
    case Cancelled cancelled -> "cancelled";
    case Packed packed -> "packed";
    case Shipped shipped -> "shipped";
};
```

This illustrative code lacks a handling path for other implementations of `FulfillmentEvent`. With a Java 21 switch expression, if the compiler cannot prove coverage of the selector type, it reports an error such as `the switch expression does not cover all possible input values`.

A better approach:

```java
return switch (event) {
    case Placed placed -> "placed";
    case Cancelled cancelled -> "cancelled";
    case Packed packed -> "packed";
    case Shipped shipped -> "shipped";
    case FulfillmentEvent other -> "other-fulfillment";
};
```

In the snippet above, `Placed`, `Cancelled`, `Packed`, `Shipped`, and `FulfillmentEvent` are assumed to be declared in the same class or imported. **Specific patterns must come before broader patterns**; if `FulfillmentEvent` is placed before `Packed` or `Shipped`, the specific cases become *dominated cases* and are rejected by the compiler.

**API documentation should give clear guidance:** if an open branch exists, clients must have a strategy to handle every subtype of that branch, even subtypes that do not yet exist in the current library version.

## 9. Do not confuse exhaustiveness with `null` handling

When using a Java 21 pattern switch:

```java
static String describe(OrderEvent event) {
    return switch (event) {
        case Placed placed -> "placed";
        case Cancelled cancelled -> "cancelled";
        case FulfillmentEvent fulfillment -> "fulfillment";
    };
}
```

The switch may be exhaustive for **non-null instances** of `OrderEvent`. However, calling `describe(null)` normally throws a **`NullPointerException`** because there is no matching `case null`.

If the API contract **allows** null values:

```java
return switch (event) {
    case null -> "missing";
    case Placed placed -> "placed";
    case Cancelled cancelled -> "cancelled";
    case FulfillmentEvent fulfillment -> "fulfillment";
};
```

This is an illustrative snippet inside a method with an appropriate `event` variable. If the API contract forbids null, you do not necessarily need `case null`: you can document the input precondition and use `Objects.requireNonNull` at the appropriate layer.

With record subtypes, **null components** and a **null selector** are two separate concerns. For example, `new Placed("O-1", null)` is still a valid `Placed` instance; the type pattern `case Placed p` matches it. However, a null component can affect guards or downstream logic. The `permits` list does not by itself guarantee component validity.

JavaDoc should distinguish:
- Which subtypes belong to the API model.
- Which data conditions on a subtype are valid.
- Whether a null selector is rejected or handled.
- Where invalid component values are checked (constructor, accessor, or service).

These are distinct contracts and should not be lumped together into “it is sealed so it is safe”.

## 10. Writing JavaDoc that adds more value than a copy of `permits`

Good JavaDoc should describe **semantics and extension policy**, not merely repeat compiler syntax.

Sample:

```java
/**
 * A domain event emitted for an order.
 *
 * <p>Direct permitted types:
 * {@link Placed}, {@link Cancelled}, and {@link FulfillmentEvent}.
 *
 * <p>{@code Placed} and {@code Cancelled} are final record
 * variants. {@code FulfillmentEvent} is a non-sealed extension
 * branch: clients should not assume its current concrete
 * implementations form an exhaustive set.
 *
 * @apiNote A pattern switch may handle each final record variant
 *          and include a single FulfillmentEvent branch.
 *          New concrete fulfillment variants may appear without
 *          changing this sealed parent's direct permitted set.
 * @since 17
 */
public sealed interface OrderEvent
        permits Placed, Cancelled, FulfillmentEvent {}
```

This is an illustrative JavaDoc snippet to place on the declared type model, not a standalone runnable file. It clarifies:

1. **Domain purpose:** an order event.
2. **Direct permitted subtypes:** their names, without confusing them with indirect subclasses.
3. **Characteristics of each branch:** final record or non-sealed interface.
4. **Consequence for pattern switches:** the open branch needs a broad case.
5. **Evolution policy:** new implementations may appear under the open branch.
6. **API introduction version:** `@since` is documentation metadata, not compiler-enforced Java compatibility.

Add `@param` to record components' JavaDoc when you need to explain meaning, units, or constraints:

```java
/**
 * Event created when an order is packed.
 *
 * @param orderId stable identifier of the associated order
 * @param boxCount number of packed boxes, non-negative
 */
public record Packed(String orderId, int boxCount)
        implements FulfillmentEvent {}
```

If you write “non-negative” in the documentation, **there should be actual validation** or a clear statement that this is a caller precondition. Java does not automatically forbid `new Packed("O-1", -1)` just because JavaDoc says the number must be non-negative.

### Descriptions to avoid

| Weak or incorrect description | Recommended description |
| --- | --- |
| “OrderEvent has exactly three implementations.” | “OrderEvent permits three **direct subtypes**: ...” |
| “FulfillmentEvent only consists of Packed and Shipped.” | “FulfillmentEvent is a `non-sealed` branch; Packed and Shipped are the current implementations.” |
| “Every client must have a case for each subclass.” | “Clients can group via `case FulfillmentEvent`; if detailed handling is needed, place specific cases before the general branch.” |
| “JavaDoc @since 17 makes code run on Java 17.” | “@since 17 documents when the API was introduced; compile with `--release 17` and test on JVM 17 to verify compatibility.” |
| “Since it is exhaustive, null is also safe.” | “Type exhaustiveness does not replace a `null` selector handling policy.” |
| “Adding a new subtype never affects clients.” | “Subtype changes require re-evaluating source, binary, and runtime behavior for clients.” |

## 11. Documentation review when adding, changing, or removing subtypes

For a public API, changing the `permits` list is a structural type change. A review checklist should ask:

1. Is the new type a **direct subtype** of the sealed parent or an **indirect subtype** of another branch?
2. Is the new type `final`, `sealed`, or `non-sealed`? If it opens a branch, does a new extension point need to be announced?
3. Is the sealed parent's JavaDoc updated with the exact direct permitted set and description?
4. Do API tables/diagrams avoid confusing direct/indirect or concrete/abstract?
5. Will clients' exhaustive switches need new cases when recompiled?
6. Is a fallback still needed to handle implementations in a `non-sealed` branch?
7. Does the set of JSON/event names/serialization types change?
8. Does any code branch or business rule rely on the assumption “only the currently known types exist”?
9. At what levels (source, binary, or runtime) does this release change the contract?
10. Have regression tests been run with both the new type and at least one existing type?

**Do not equate** “just editing one line of `permits`” with “no public impact”. A new subtype can affect exhaustiveness handling, serializers, dispatchers, persistence mappings, and schemas that API consumers depend on.

### Example: adding a new direct subtype

Initially:

```java
sealed interface Status permits Ready, Failed {}
record Ready() implements Status {}
record Failed(String reason) implements Status {}
```

A Java 21 client has an exhaustive switch expression:

```java
static String label(Status status) {
    return switch (status) {
        case Ready r -> "ready";
        case Failed f -> "failed";
    };
}
```

After the API adds `TimedOut` to the direct permitted subtypes list, **client source code when recompiled** may be required to add a handling path because the sealed set has changed. This is usually a helpful compiler warning that catches un-updated code.

With **separate compilation** (an older client not recompiled, running against the new library at runtime), a switch already compiled against the old subtype set can encounter the new unhandled value and throw **`MatchException`** at runtime in Java 21. This depends on versioning and classpath setup; you should not claim every library upgrade throws this exact exception, but it is a risk that must be part of your testing strategy.

**Versioning documentation should clearly state** whether adding a direct subtype is considered a breaking change for exhaustive clients, or whether the API's policy requires clients to keep an appropriate fallback.

### Conversely: adding a subtype under a `non-sealed` branch

With `OrderEvent` and `FulfillmentEvent` in the main example, adding `CustomerPickup` under `FulfillmentEvent` **does not require adding its name to `OrderEvent permits`**. Clients with `case FulfillmentEvent fulfillment` still handle the new instance via the general branch.

Still, you must test:
- If clients need to distinguish `CustomerPickup`, they must add a specific case before the general case.
- Serialization/deserialization may need a mapping for the new type name.
- Enum-like documentation titled “Supported fulfillment events” must state whether it is an illustrative list or a restricted API policy.
- If a client handles every `FulfillmentEvent` with logic assuming only `Packed` and `Shipped` exist, business-logic bugs can occur even though the Java compiler allows it.

An open branch is a **commitment to type extensibility**, not a guarantee that every client will automatically handle the semantics of new variants correctly.

## 12. Public API, Java versions, and describing support levels

Sealed constructs are officially supported since Java 17:

```java
public class SealedPermitJava17 {
    public sealed interface Signal permits Started, Stopped {}
    public record Started(String id) implements Signal {}
    public record Stopped(String id) implements Signal {}

    static String label(Signal signal) {
        if (signal instanceof Started started) {
            return "started:" + started.id();
        }
        if (signal instanceof Stopped stopped) {
            return "stopped:" + stopped.id();
        }
        return "other";
    }

    public static void main(String[] args) {
        System.out.println(label(new Started("S-17")));
    }
}
```

Run with a JDK supporting target 17:

```bash
javac --release 17 -encoding UTF-8 SealedPermitJava17.java
java SealedPermitJava17
```

Output:

```text
started:S-17
```

At Java 17, clients can use `instanceof` type patterns and sealed hierarchies. When the intended usage is **exhaustive pattern switch with record deconstruction**, the Java 21 language level is required (even though the sealed hierarchy itself may live in a Java 17 artifact).

Therefore, JavaDoc should distinguish:
- The sealed API available since Java 17 (`@since` may record the library release).
- Consumption examples using `switch` with type/record patterns requiring Java 21+.
- The permitted subtype set is an API constraint; the syntax used to consume the API depends on the Java version the client compiles with.

Do not put an example like `case Placed(var id, var customer)` into a “Java 17 compatible” guide without marking it as Java 21 syntax.

## 13. Compile-error cases that help verify real constraints

### 13.1. Missing `sealed`/`non-sealed` on a direct subtype

The following snippet **intentionally does not compile**:

```java
sealed interface Root permits Open {}
interface Open extends Root {}
```

The Java 21 compiler may report something like:

```text
sealed or non-sealed modifiers expected
```

Reason: `Open` is a direct subtype of `Root` but does not specify either `sealed` or `non-sealed` (an interface cannot be `final`). Fix it as:

```java
sealed interface Root permits Open {}
non-sealed interface Open extends Root {}
```

When documentation says “Open is an open branch” but the code omits `non-sealed`, the compiler catches it. Conversely, when the code has `non-sealed` while JavaDoc claims “all subtypes have been listed”, the documentation is wrong even though the code compiles.

### 13.2. Listing an indirect subtype in `permits`

The following snippet **intentionally does not compile**:

```java
sealed interface Root permits Direct, Indirect {}
non-sealed interface Direct extends Root {}
final class Indirect implements Direct {}
```

`Indirect` does not directly `implements Root`, so it cannot be a direct permitted subtype of `Root`. The valid version lists only `Direct`:

```java
sealed interface Root permits Direct {}
non-sealed interface Direct extends Root {}
final class Indirect implements Direct {}
```

Use **compiler checks** to catch invalid structure; do not work around type errors by adding names to JavaDoc while ignoring the compiler.

### 13.3. Attempting to add a new class implementing the sealed parent

If `OrderEvent` only permits `Placed, Cancelled, FulfillmentEvent`, a new class:

```java
// INVALID: not in the direct permitted types list of OrderEvent.
final class ExtraOrderEvent implements OrderEvent {}
```

is not allowed to directly implement `OrderEvent`. If this is an event in the fulfillment family, implementing `FulfillmentEvent` (when its contract and required methods fit) is the designed extension path. If it represents a new event category, the API owner must evaluate adding a direct permitted subtype, announce the impact, and update the documentation.

## 14. Generating documentation and API consumption guides

For public API documentation, provide a combination of:

**Prose description:** why the sealed type exists, which direct subtypes it is restricted to, which branches are open, and the domain meaning of each branch.

**Diagrams or tables:** easier to read than a long multi-level `permits` clause, clearly showing `sealed`/`non-sealed`/`final` and direct/indirect relationships.

**Linked JavaDoc:** use `{@link TypeName}`, `@apiNote`, `@since`, and `@param` for record components where appropriate. Do not copy lists with broken package links or maintain a docs page that goes stale when subtypes are added.

**Valid consumption examples:** if publishing cases for Java 21, include an exhaustive switch over direct branches; if supporting Java 17, also include an `instanceof`-based example. Always state the baseline.

**Extension guide:** if there is a `non-sealed` extension point, state the minimum methods to implement, stability rules, validation, and supported extension scope. Do not suggest that users directly implement the sealed parent from an external module.

**Versioning rules:** when adding a subtype is a notable change, what clients must do when upgrading, and which tests detect hierarchy changes.

**Runtime information:** `getPermittedSubclasses()` only reveals direct permitted subtypes; it is not a complete discovery mechanism for every provider/implementation of an open branch.

Good JavaDoc does not need to be long. The goal is for API consumers to understand **what types are allowed, what the compiler proves, and what the API may still change**.

## 15. Suggested tests for closed APIs and open branches

Alongside the reflection test in Section 6, you can use behavior tests to verify how clients handle each branch.

### Testing direct branches

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class OrderEventContractTest {
    @Test
    void sealedBranchesHaveExpectedBehavior() {
        assertAll(
                () -> assertEquals("placed:O-1:C-1",
                        PermittedSubtypeDocsDemo.describe(
                                new PermittedSubtypeDocsDemo.Placed("O-1", "C-1"))),
                () -> assertEquals("cancelled:O-2:duplicate",
                        PermittedSubtypeDocsDemo.describe(
                                new PermittedSubtypeDocsDemo.Cancelled(
                                        "O-2", "duplicate"))),
                () -> assertEquals("fulfillment:O-3",
                        PermittedSubtypeDocsDemo.describe(
                                new PermittedSubtypeDocsDemo.Packed("O-3", 2)))
        );
    }

    @Test
    void openBranchHasGenericFallback() {
        assertEquals("other-fulfillment:O-5",
                PermittedSubtypeDocsDemo.detail(
                        new PermittedSubtypeDocsDemo.CustomerPickup("O-5")));
    }
}
```

This is an **illustrative JUnit 5 class**, requiring JUnit on the test classpath and placement in the same package (or adjusted visibility). It is not part of the standalone `PermittedSubtypeDocsDemo.java` program.

These tests verify:
- Direct subtypes `Placed`/`Cancelled` behave as expected.
- The `FulfillmentEvent` branch handles its implementations.
- Specific cases and the open fallback are distinguished by `detail`.

### Testing API changes with compile checks

In addition to runtime tests, verify the following in CI:
1. The library itself **compiles successfully** with the published `--release`.
2. New direct subtypes must be authorized by the sealed parent; structurally invalid subtypes are rejected by the compiler.
3. Examples in JavaDoc/guides (if executable) are compiled/tested against the corresponding Java release.
4. Sample clients using exhaustive `switch` are recompiled when the API version updates to expose new branches needing handling.
5. Regression tests against old and new versions distinguish binary loading, runtime behavior, and serialization compatibility.

A test that only asserts `getPermittedSubclasses().length == 3` is not enough: swapping one subtype for another while keeping the same count would still pass. Compare the **actual set of types**, not just the array length.

## 16. Pre-release documentation checklist

| Question to answer | Sign of good documentation |
| --- | --- |
| What domain does the sealed parent represent? | States business purpose, not just a class list |
| What are the direct permitted subtypes? | List/table matches `permits` accurately |
| Is there a `non-sealed` branch? | Clearly documented as an extension point |
| Is there a multi-level `sealed` branch? | Has a layered diagram, does not confuse direct with indirect |
| Are there records or `final` classes? | Clearly noted as inheritance-terminating branches |
| Where are clients allowed to implement subtypes? | Only on open interfaces/classes with valid visibility/module |
| For Java 21, how is an exhaustive switch written? | Example covers direct branches, with a broad case for open branches |
| For Java 17, what is the consumption guide? | Uses `instanceof` type patterns/accessors, without mixing in record patterns |
| How are null selectors and component data handled? | Separate null contract is stated |
| Is adding a new subtype a breaking change? | Has versioning policy and migration guidance |
| What does reflection return? | Clearly states direct permitted subtypes only |
| Does JavaDoc have links, version, and component contracts? | Uses `{@link}`, `@since`, `@param` where needed |
| Which tests guard the contract? | Reflection set + behavior cases + compile/runtime tests |
| Does documentation match the release code? | Has an appropriate review/automated check step |

If you only have time to fix one documentation item, prioritize one accurate sentence: **“The types in `permits` are the permitted direct subtypes; any `non-sealed` branch can still be extended.”** This is the point where most sealed APIs are misdocumented.

## 17. Common mistakes

### 17.1. Calling all descendants “permitted”

`Packed` is an `OrderEvent` by type relationship, but it is not a direct permitted subtype of `OrderEvent` in the model above. Documentation should use “indirect implementation” or “concrete variant of the fulfillment branch”.

### 17.2. Assuming `non-sealed` means only currently known implementations exist

`non-sealed` allows further extension. If consumers build logic around the current list without a fallback, they may encounter new subtypes later.

### 17.3. Adding `default` to hide every API change

An exhaustive switch on a closed sealed hierarchy with explicit cases lets the compiler alert you when a new subtype is added. `default` can mask that signal. For a `non-sealed` branch, a case for the broad branch itself is usually more meaningful than an anonymous `default` because it still names the recognized domain group.

### 17.4. Assuming a sealed parent never changes

Sealing is an inheritance rule **of the current artifact**, not a promise against evolution. Adding direct subtypes, changing modifiers, or closing an open branch requires a release policy and compatibility testing.

### 17.5. Confusing the API contract with runtime enumeration

`getPermittedSubclasses()` is reflection for the direct permitted set; it does not scan the classpath for every implementation under a `non-sealed` branch. If provider discovery is needed, use a dedicated mechanism (configuration, `ServiceLoader`, registry, etc.).

### 17.6. JavaDoc that only repeats syntax

“`OrderEvent permits A, B, C`” does not explain why each variant exists, how clients should handle it, how null behaves, which branches are open, or how versioning applies. Add the semantics that the compiler cannot express.

### 17.7. Publishing Java 21 examples as Java 17-compatible code

Sealed hierarchies exist since Java 17, but pattern switch and record patterns became standard in Java 21. Clearly state the Java level of each example and run `javac --release` accordingly.

### 17.8. Changing direct subtypes without evaluating external clients

When adding a direct subtype, maintainers can cause exhaustive clients to miss a case upon recompilation, or encounter unexpected values at runtime in separately compiled versions. Test and announce changes rather than only editing Javadoc.

### 17.9. Saying “clients can implement the sealed parent” across modules

With named modules, direct permitted implementations must be in the same module as the sealed parent. Clients outside the module cannot simply become direct subtypes; point them to a public `non-sealed` branch if extension is intended.

### 17.10. Subtype names that do not reflect the domain

`Status1`, `Status2`, or `EventX` make pattern switches hard to read even when the compiler proves exhaustiveness. Choose domain-meaningful names like `Placed`, `Cancelled`, and `FulfillmentEvent`, and clearly describe their state/meaning for API readers.

## 18. Exercises and answers

**Exercise 1 — Direct or indirect?** Given `sealed interface Root permits A, Open`, `record A() implements Root`, `non-sealed interface Open extends Root`, `record B() implements Open`. Which types are in `Root`'s direct permitted set?

**Answer:** `A` and `Open`. `B` is an indirect subtype via `Open`; it is not in `Root.permits`.

**Exercise 2 — Does an open branch have a fixed set of subtypes?** If `B` and `C` currently implement `Open`, can you document “`Open` only has B and C” as an invariant?

**Answer:** No, unless an external non-language constraint enforces it and the documentation states that clearly. `Open` is non-sealed, allowing additional implementations.

**Exercise 3 — Modifiers.** Is an interface that directly extends a sealed interface valid if it only writes `interface Child extends Parent`?

**Answer:** No, when `Child` is a direct permitted interface; it must be declared `sealed` or `non-sealed` per language rules. A record direct subtype is implicitly final.

**Exercise 4 — Exhaustive switch.** Given direct permitted branches `Placed`, `Cancelled`, and `FulfillmentEvent` (non-sealed), is listing `Placed`, `Cancelled`, `Packed`, and `Shipped` exhaustive?

**Answer:** No; `FulfillmentEvent` may have other implementations. You need a broad `FulfillmentEvent` case or another valid covering path.

**Exercise 5 — Reflection.** Why does `OrderEvent.class.getPermittedSubclasses()` not return `Packed` in the sample program?

**Answer:** Because `Packed` only directly implements `FulfillmentEvent`. Reflection on `OrderEvent` returns direct permitted types, not all descendants.

**Exercise 6 — Named module.** Can a plugin in another module directly implement a sealed `OrderEvent` from a library module?

**Answer:** No, unless it is a direct permitted subtype in the same module. If the API exposes a public `non-sealed FulfillmentEvent` branch, the plugin can implement that branch when it satisfies visibility and contract rules.

**Exercise 7 — API evolution.** Why can adding a new direct subtype cause a Java 21 client to fail recompilation?

**Answer:** A switch expression that was previously exhaustive over the old set may no longer cover all direct branches. The compiler requires a new case or an appropriate fallback.

**Exercise 8 — Binary/runtime.** An older client compiled against the old sealed hierarchy later runs with a library containing a new subtype. Is it guaranteed to keep running without error?

**Answer:** No. With separate compilation, a switch compiled as exhaustive can encounter the new unhandled subtype and throw `MatchException` when executed. Compatibility testing is required, not just a clean compile of the new library.

**Exercise 9 — Null.** An exhaustive switch on `OrderEvent` covers `Placed`, `Cancelled`, and `FulfillmentEvent` without `case null`. Does `describe(null)` automatically enter one of the branches?

**Answer:** Normally it throws `NullPointerException`. The permitted subtype set does not define null policy by itself.

**Exercise 10 — Writing JavaDoc.** Write one accurate sentence describing the `OrderEvent` hierarchy with an open branch.

**Reference answer:** “OrderEvent is a sealed interface that directly permits Placed, Cancelled, and FulfillmentEvent; FulfillmentEvent is a non-sealed extension point, so the set of concrete fulfillment events is extensible.”

**Exercise 11 — Java version.** From which Java version can the sealed hierarchy above be used? What about `case Packed(var id, var count)` with a record pattern?

**Answer:** Sealed types became standard in Java 17; record patterns combined with pattern switch became standard in Java 21. Clients must choose the appropriate `--release` and test on a supported runtime.

**Exercise 12 — Change review.** When a developer adds `Returned` implementing `FulfillmentEvent`, does `OrderEvent permits` need to be edited?

**Answer:** No, because `FulfillmentEvent` is a permitted non-sealed branch. However, you should review documentation listing fulfillment variants, serialization, domain behavior, and regression tests for the new event.

## 19. Key takeaways

- A sealed type's `permits` list defines **direct permitted subtypes**, not every indirect or concrete subtype.
- A direct subtype must terminate with `final` (records are implicitly final), continue restricting with `sealed`, or open up with `non-sealed`.
- In a **named module**, direct permitted subtypes must be in the same module; in an **unnamed module**, in the same package.
- **JavaDoc must state domain semantics, whether each branch is closed or open, and the evolution policy**, not just copy syntax.
- **`non-sealed`** is a true extension point; in a pattern switch, cover the open branch itself rather than only currently known concrete implementations.
- `Class.isSealed()` and `Class.getPermittedSubclasses()` help verify the **direct permitted set**; the latter is not a scanner for all subtypes.
- **Sealed APIs from Java 17; pattern switch/record patterns standard from Java 21.** Clearly state the Java baseline of examples.
- An exhaustive switch still needs a separate contract for **null selectors** and invalid component values.
- When changing the direct permitted set, evaluate **source recompilation**, **runtime under separate compilation**, serialization, and client migration.
- Good testing includes **reflection sets**, branch behavior, compile checks, and regression tests for new variants.

**Official references:**
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Java SE 21 API — Class.getPermittedSubclasses()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#getPermittedSubclasses())
- [Java Language Specification 21 — Classes (`8)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html)
- [Java Language Specification 21 — Interfaces (`9)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html)
