# Enum for Modeling a Finite Set of Named Instances in Java

## 1. Goal: Representing a Closed, Named, and Meaningful Set of Choices

Some domain concepts have only **a predefined set of states or values**: priority levels `LOW`, `MEDIUM`, `HIGH`; directions `NORTH`, `EAST`, `SOUTH`, `WEST`; order statuses `NEW`, `PAID`, `SHIPPED`, `CANCELLED`. When the choices are named, meaningful, and not arbitrarily created by users at any time, Java provides the **`enum`** type to model them.

```java
enum Priority {
    LOW, MEDIUM, HIGH
}
```

This is **a valid enum declaration** that can be placed at file level or as a nested type, not yet a standalone runnable program.

With the `Priority` enum:

- `LOW`, `MEDIUM`, `HIGH` are **named enum constants** and are **objects** of the enum type `Priority`.
- A variable of type `Priority` can only reference constant instances of that type **or `null`**, rather than accepting any string/integer.
- The constant instances are defined by the enum declaration; a new constant cannot be created using `new Priority()` from a client.
- The constants are used via `Priority.LOW`, `Priority.MEDIUM`, `Priority.HIGH`.
- An enum has **its own type**, so the compiler distinguishes Priority from other enums, even if they have the same constant names.
- The number and names of constants **are closed in the version of the enum declaration**, rather than being a dynamic set extended by users at runtime.

> **Idea:** When the value domain is truly a **pre-known finite set in which each element has a clear name**, `enum` serves as a data structure that reflects the value domain more accurately than using "magic" numbers or arbitrary input strings.

The goal of this lesson is to understand **when, why, and how** to use enums to model a finite set of values; to recognize their limitations; and to verify them through runnable Java 17+ examples.

## 2. A First Program

Create the file **`PriorityBasicsDemo.java`**:

```java
enum Priority {
    LOW, MEDIUM, HIGH
}

public class PriorityBasicsDemo {
    public static void main(String[] args) {
        Priority current = Priority.HIGH;

        System.out.println(current);
        System.out.println(current == Priority.HIGH);
        System.out.println(current == Priority.LOW);
        System.out.println(Priority.values().length);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac PriorityBasicsDemo.java
java PriorityBasicsDemo
```

**Standard output:**

```text
HIGH
true
false
3
```

Explanation:

1. `Priority.HIGH` is a defined constant of type Priority.
2. `current == Priority.HIGH` is true because both reference the same constant instance.
3. `current == Priority.LOW` is false because they are two different constants.
4. The compiler provides `values()` for the enum, returning an array of constants in declaration order, so there are 3.
5. `System.out.println(current)` uses `toString()`; when not overridden, the output is the constant name `HIGH`.

**Note:** `enum` does not mean "contains only numbers". In Java, each constant is an **object** that can have its own fields, methods, and behavior. However, the set of constant instances is still determined by the enum declaration.

## 3. Comparison with String and int: Why Do We Need a Dedicated Type?

Before enums, one might write:

```java
String priority = "HGIH"; // Misspelled, yet still a String.
int level = 17;           // Unclear whether 17 is valid or not.
```

These two lines are **an illustrative snippet** of a design flaw:

- `String` accepts any content, including typos, different uppercase/lowercase casing, and invalid values.
- `int` accepts a very large numeric range, whereas the business domain may only have three levels.
- Code scattering strings/numeric constants causes duplication, making it hard to refactor and control.
- A method accepting a String/primitive does not clearly state the valid set of values on its own.

With an enum:

```java
Priority priority = Priority.HIGH;
```

The compiler checks types. The following snippet is invalid:

```java
// Priority wrong = "HIGH";      // String is not a Priority.
// Priority wrong = 17;          // int is not a Priority.
// Priority wrong = Priority.HGIH; // Constant does not exist.
```

**Main benefit:** *type safety*. Readers of the API `schedule(Priority level)` know that level belongs to the defined Priority set. A typo when referencing a constant is usually caught at compile time instead of persisting as incorrect data at runtime.

**Limitation:** The compiler does not automatically protect against `null`, or invalid input coming from JSON/HTTP/database. Mapping data from external sources to an enum still requires appropriate validation/parsing.

## 4. Finite Count and Meaningful Constant Names

A good enum typically describes **discrete choices with stable names in the domain**.

Examples:

```java
enum Direction {
    NORTH, EAST, SOUTH, WEST
}

enum Light {
    RED, YELLOW, GREEN
}

enum AccessLevel {
    GUEST, MEMBER, ADMIN
}
```

These are **illustrative declarations**.

Looking at the type, we can identify the choices that have been modeled.

However, these names are only examples of a **bounded set defined by the application**. Not every system has exactly three access levels, nor do traffic lights in every country have only three states. When the domain changes, the enum declaration itself also needs to be updated and downstream consumers checked.

### When Is It Not Suitable?

Cases such as usernames, user-entered product codes, thousands of different orders, continuously generated IDs, lists of countries/currencies fetched from dynamic providers… should generally **not be forced into an application enum** if the set of values can expand independently of release cycles.

A set that merely "has a finite number of values at this moment" is not enough; what is required is a value set that is **known in advance and intentionally closed at the design level**.

## 5. A Named Finite Set Differs from an Arbitrary Set of Objects

Suppose a system has delivery statuses:

```java
enum DeliveryStatus {
    CREATED, PACKED, SENT, DELIVERED
}
```

`DeliveryStatus.SENT` is a constant instance. Everywhere within the same normal runtime context that uses `DeliveryStatus.SENT` references that same constant object.

Conversely, if you design a class yourself:

```java
final class DeliveryStatusValue {
    private final String label;

    DeliveryStatusValue(String label) {
        this.label = label;
    }
}
```

This class **allows creating multiple instances** via `new DeliveryStatusValue("SENT")`. It does not automatically guarantee closing the set of instances to four names like an enum does.

**Do not infer that an enum is a class without methods.** An enum is a special language mechanism for named declared constant objects, while also having behavior like other objects wherever Java permits.

## 6. Enums Are Identified by Type: Two Enums with Constants of the Same Name Are Still Different

Create **`EnumTypeSafetyDemo.java`**:

```java
enum ShippingStatus {
    NEW, DONE
}

enum PaymentStatus {
    NEW, DONE
}

public class EnumTypeSafetyDemo {
    static String summarize(ShippingStatus status) {
        return "shipping=" + status;
    }

    public static void main(String[] args) {
        ShippingStatus shipping = ShippingStatus.DONE;
        PaymentStatus payment = PaymentStatus.DONE;

        System.out.println(summarize(shipping));
        System.out.println(payment.name());

        // summarize(payment); // Compile-time error:
        // PaymentStatus is different from ShippingStatus.
    }
}
```

```bash
javac EnumTypeSafetyDemo.java
java EnumTypeSafetyDemo
```

```text
shipping=DONE
DONE
```

Two enums have a constant named `DONE`, yet:

- `ShippingStatus.DONE` is a ShippingStatus.
- `PaymentStatus.DONE` is a PaymentStatus.
- You cannot mistakenly pass a PaymentStatus to a method requiring a ShippingStatus and have the compiler silently accept it.

This is an important difference from using the String `"DONE"`: String does not carry the concepts of "payment's DONE" and "shipping's DONE" as distinct Java types.

## 7. Enum Constants Are Per-Constant Singleton Objects

With:

```java
enum Size {
    SMALL, MEDIUM, LARGE
}
```

each constant `SMALL`, `MEDIUM`, `LARGE` is initialized by Java as an object of the enum type. Within a normal runtime/class loader scope, a client cannot call `new Size()` to create a fourth Size constant.

A commonly used comparison with enums is `==` because constants are identified by identity:

```java
Size a = Size.SMALL;
Size b = Size.SMALL;
System.out.println(a == b); // true.
```

This is a **code snippet** inside a valid method.

### Comparing `==` and `equals()`

`Enum.equals()` has identity semantics. For non-null enum references of the same type, `a == b` and `a.equals(b)` have the same constant-comparison meaning, but `a.equals(b)` can throw a `NullPointerException` if a is null.

Therefore:

```java
if (status == DeliveryStatus.SENT) {
    // ...
}
```

is a clear and null-safe way when status may be null.

**Do not claim "a singleton across the entire JVM universe" while ignoring class loader boundaries**. For a typical application, each enum constant has a stable identity within the class-loading context of that type. The API goal is the set of constant instances specified by the enum declaration.

## 8. `values()` and `valueOf()`: Observing the Defined Set

Java provides two special methods on enum types:

- `Priority.values()`: an array containing the constants in declaration order.
- `Priority.valueOf("HIGH")`: looks up the constant with **the exact declared name** or throws `IllegalArgumentException` if no such name exists.

Create **`EnumValuesDemo.java`**:

```java
enum Priority {
    LOW, MEDIUM, HIGH
}

public class EnumValuesDemo {
    public static void main(String[] args) {
        for (Priority value : Priority.values()) {
            System.out.println(value.name());
        }

        System.out.println(
                Priority.valueOf("HIGH") == Priority.HIGH);

        try {
            Priority.valueOf("high");
        } catch (IllegalArgumentException ex) {
            System.out.println("unknown name");
        }
    }
}
```

```bash
javac EnumValuesDemo.java
java EnumValuesDemo
```

```text
LOW
MEDIUM
HIGH
true
unknown name
```

**Important limitations:**

- `valueOf` is **case-sensitive**: `"high"` is not `"HIGH"`.
- `valueOf(null)` throws `NullPointerException` according to the API.
- `values()` returns a **new array**, not a direct reference to the internal array storing the constants.
- The array's slots can be modified, but doing so **does not create or change the set of constants declared by the enum type**.
- Enum constants can have a customized `toString()`. `valueOf` looks up by **`name()`**, not by the result of the customized toString.

**Do not use `values()` as a mechanism to let clients register new constants.** The enum set is closed at the declaration.

## 9. Proving That `values()` Returns a Different Array Containing the Same Constant Objects

Create **`EnumValuesArrayDemo.java`**:

```java
enum Status {
    OPEN, CLOSED
}

public class EnumValuesArrayDemo {
    public static void main(String[] args) {
        Status[] first = Status.values();
        Status[] second = Status.values();

        System.out.println(first == second);
        System.out.println(first[0] == second[0]);

        first[0] = Status.CLOSED;

        System.out.println(first[0]);
        System.out.println(second[0]);
        System.out.println(Status.values()[0]);
    }
}
```

```bash
javac EnumValuesArrayDemo.java
java EnumValuesArrayDemo
```

```text
false
true
CLOSED
OPEN
OPEN
```

**Distinguishing two levels:**

1. `first` and `second` are **two different array objects**.
2. `first[0]` and `second[0]` initially point to **the same Status.OPEN enum constant instance**.
3. Assigning `first[0] = Status.CLOSED` modifies only one slot of the first array.
4. It does not delete or rename Status.OPEN; `Status.values()[0]` still returns OPEN in declaration order.

## 10. Choosing Enum Names and Scope in Design

The enum type name should describe **the value domain**: `OrderStatus`, `Priority`, `Direction`, `PaymentMethod`. Constants should describe **specific elements**: `PAID`, `HIGH`, `NORTH`.

The common convention is:

- Type: PascalCase, such as `OrderStatus`.
- Constants: UPPER_SNAKE_CASE, such as `IN_PROGRESS`.
- Fields/methods: camelCase following standard Java conventions.

Names must be **unambiguous**. If there is a general `Status` for payments, shipping, and accounts, using an overly broad enum easily mixes up semantics. Separate enums can be used:

```java
enum AccountStatus {
    ACTIVE, SUSPENDED, CLOSED
}

enum InvoiceStatus {
    DRAFT, ISSUED, PAID
}
```

These two types reflect two different status domains.

### Where to Place Them?

- A public top-level enum can be placed in the file `OrderStatus.java` following the filename/public type rule.
- A nested enum inside a class is suitable when it is tied only to a domain concept local to that class.
- A `private enum` can be a nested member type, useful if an implementation detail should not become part of the API.
- In Java 17, a **local enum** can be declared inside a block; a local enum is implicitly static and does not capture local variables like a local inner class.
- Do not expose an enum in the public API merely for calling convenience if consumers do not genuinely need that type name.

## 11. Using Enums in Signatures Makes the Contract Clear

Create **`PriorityApiDemo.java`**:

```java
import java.util.Objects;

enum Priority {
    LOW, MEDIUM, HIGH
}

public class PriorityApiDemo {
    static String deliveryChannel(Priority priority) {
        Objects.requireNonNull(priority, "priority");

        return switch (priority) {
            case LOW -> "batch";
            case MEDIUM -> "normal";
            case HIGH -> "express";
        };
    }

    public static void main(String[] args) {
        System.out.println(
                deliveryChannel(Priority.HIGH));
        System.out.println(
                deliveryChannel(Priority.LOW));
    }
}
```

```bash
javac PriorityApiDemo.java
java PriorityApiDemo
```

```text
express
batch
```

Instead of the method accepting `String priority` and comparing against multiple literals, the API uses `Priority` to **restrict the type of valid values**. `Objects.requireNonNull` checks the null boundary, avoiding unintended null-handling code.

**Benefit at the call site:** `deliveryChannel(Priority.HIGH)` is more self-descriptive than `deliveryChannel(3)`. The compiler detects mistakenly passing a different enum type.

### About the `switch` Expression

In the example, `switch` is a Java 17 **expression** returning a String. The cases cover all current constants of Priority, so `default` is not needed. If a constant is added to Priority within the same source/module upon rebuilding, the compiler can help detect the missing case and force you to consider the new meaning.

**Do not equate a compile-time exhaustive check with a guarantee that input from another data version is always safe.** Public APIs/serialized values have their own compatibility requirements when an enum evolves.

## 12. An Enum Is a Finite Set of Names, Yet Each Element Can Carry Data

Sometimes constant names alone are not enough for display or computation. An enum can store **metadata attached to each choice**, instead of scattering `if/switch` across many places.

Create **`PriorityWithFieldsDemo.java`**:

```java
enum Priority {
    LOW(1, "thap"),
    MEDIUM(2, "trung binh"),
    HIGH(3, "cao");

    private final int weight;
    private final String label;

    Priority(int weight, String label) {
        this.weight = weight;
        this.label = label;
    }

    int weight() {
        return weight;
    }

    String label() {
        return label;
    }
}

public class PriorityWithFieldsDemo {
    public static void main(String[] args) {
        for (Priority priority : Priority.values()) {
            System.out.println(priority.name() + ":" +
                    priority.weight() + ":" +
                    priority.label());
        }
    }
}
```

```bash
javac PriorityWithFieldsDemo.java
java PriorityWithFieldsDemo
```

```text
LOW:1:thap
MEDIUM:2:trung binh
HIGH:3:cao
```

Points to remember:

- Constant declarations are placed at the beginning of the enum body.
- A `;` after the constant list is required when fields/methods are declared afterward.
- The constructor `Priority(int, String)` is used by the runtime/compiler when initializing constants; clients do not call `new Priority(...)`.
- Enum constructors cannot be public/protected; they are typically left implicit/private.
- `weight` and `label` are final fields so that each constant has immutable metadata in the example.
- `Priority.values()` still contains the exact three constants LOW/MEDIUM/HIGH; adding metadata does not create new constants.

**Good model:** An enum is a set of choices with stable identities, while the attached data describes the meaning of each choice.

## 13. An Enum Constructor Is Not a Public Factory

The syntax `LOW(1, "thap")` looks like a constructor call, but it is an **enum constant declaration** inside the enum body itself.

A client cannot:

```java
// Priority fourth = new Priority(4, "very high");
```

Even when the constructor is present in the source code, Java forbids creating arbitrary enum instances from a client. This helps preserve **the closed nature** of the set of constant instances.

**Caution regarding constructors and initialization:**

- Enum constants are created when the enum class is initialized according to class initialization rules.
- Do not rely on obscure side effects or initialization order across multiple classes.
- Avoid manipulating mutable global state in enum constructors.
- Enum constant fields should be initialized explicitly, with immutable data when possible.
- Java enforces special restrictions on referencing the enum's static fields from constructors/instance initializers to prevent access before the class is completely initialized.

A finite set should be **stable and easy to reason about**; do not turn an enum constructor into a place that opens sockets, writes to a database, or registers resources without a clear lifecycle.

## 14. Each Constant Can Have Behavior via Methods

Domain-specific data and behavior can be placed close to the constants. For example, different fee calculation rules for three delivery methods.

Create **`DeliveryMethodBehaviorDemo.java`**:

```java
enum DeliveryMethod {
    STANDARD {
        @Override
        int fee(int items) {
            return 10;
        }
    },
    EXPRESS {
        @Override
        int fee(int items) {
            return 20 + items * 2;
        }
    },
    PICKUP {
        @Override
        int fee(int items) {
            return 0;
        }
    };

    abstract int fee(int items);
}

public class DeliveryMethodBehaviorDemo {
    public static void main(String[] args) {
        for (DeliveryMethod method : DeliveryMethod.values()) {
            System.out.println(method.name() + "=" +
                    method.fee(3));
        }
    }
}
```

```bash
javac DeliveryMethodBehaviorDemo.java
java DeliveryMethodBehaviorDemo
```

```text
STANDARD=10
EXPRESS=26
PICKUP=0
```

Each enum constant here has its own class body overriding the `fee` method. However, **the set of choices is still finite**: STANDARD, EXPRESS, PICKUP; they are not plugin types that can be additionally registered from outside.

**When should behavior be placed inside an enum?**

- When the logic is small, directly tied to, and stable for each choice.
- When avoiding scattered `switch` statements that repeat the same rules.
- When the interface/method has a clear contract and simple inputs.

**When not?** If each choice requires a dependency injection system, database/network access, or hundreds of lines of workflow, an enum can become too heavy. Keeping the enum as **a type identifier** and moving complex behavior to external strategies/services makes testing and dependency management easier.

## 15. Different Behavior Does Not Make an Enum Set Dynamically Extensible

An enum is not a plugin registry mechanism. Even though a constant has its own class body such as `EXPRESS { ... }`, another application **cannot declare an additional `DeliveryMethod.DRONE` from an external class** at runtime.

To add a choice, you typically have to:

1. Change the source enum declaration.
2. Rebuild/deploy the relevant Java parts.
3. Check exhaustive switches, routing, validation, and mapping from external codes.
4. Review backward/forward compatibility with persisted data and clients.

If business requirements call for users to create new types themselves in a database or for third parties to register behavior at runtime, consider **interface + classes + registry**, a sealed hierarchy with appropriate boundaries, or value objects/dynamic configuration. An enum is suitable only when having a *closed* set of elements is an intentional part of the design.

## 16. Enums Used in `EnumSet`

When an object needs to store **multiple enum choices at the same time**, Java provides the `EnumSet<E>` collection optimized for enum types.

Create **`EnumSetDemo.java`**:

```java
import java.util.EnumSet;

enum Permission {
    READ, WRITE, EXECUTE, DELETE
}

public class EnumSetDemo {
    public static void main(String[] args) {
        EnumSet<Permission> allowed =
                EnumSet.of(Permission.READ, Permission.EXECUTE);

        System.out.println(allowed);
        System.out.println(allowed.contains(Permission.READ));
        System.out.println(allowed.contains(Permission.WRITE));

        allowed.add(Permission.WRITE);
        System.out.println(allowed);
    }
}
```

```bash
javac EnumSetDemo.java
java EnumSetDemo
```

```text
[READ, EXECUTE]
true
false
[READ, WRITE, EXECUTE]
```

`EnumSet` uses **declaration order** for iteration/output in the example. It accepts only constants of the same enum type under its generic contract, so `Permission.READ` cannot be mixed with another enum.

A typical `EnumSet` is a **mutable collection**. `allowed.add(...)` is permitted and modifies the set, even though additional enum constants still cannot be created.

### `EnumSet.allOf`, `noneOf`, and `complementOf`

```java
EnumSet<Permission> all = EnumSet.allOf(Permission.class);
EnumSet<Permission> none = EnumSet.noneOf(Permission.class);
EnumSet<Permission> others = EnumSet.complementOf(allowed);
```

This is an **illustrative code snippet** assuming Permission/allowed exist. A set of enum values does not imply EnumSet is immutable; it is simply a specialized collection for a finite domain.

## 17. Enums as Keys of `EnumMap`

A configuration mapped per enum choice can use `EnumMap`, avoiding arbitrary String keys.

Create **`EnumMapDemo.java`**:

```java
import java.util.EnumMap;

enum Priority {
    LOW, MEDIUM, HIGH
}

public class EnumMapDemo {
    public static void main(String[] args) {
        EnumMap<Priority, Integer> targets =
                new EnumMap<>(Priority.class);

        targets.put(Priority.HIGH, 5);
        targets.put(Priority.LOW, 1);
        targets.put(Priority.MEDIUM, 3);

        for (Priority priority : targets.keySet()) {
            System.out.println(priority + "=" +
                    targets.get(priority));
        }
    }
}
```

```bash
javac EnumMapDemo.java
java EnumMapDemo
```

```text
LOW=1
MEDIUM=3
HIGH=5
```

Even though `put` is not called in enum declaration order, EnumMap has an iteration order following **the natural order of the keys** (the declaration order of the constants).

**Boundary:** EnumMap does not automatically enforce having a mapping for **every** constant. You still need to check for missing keys. If you want a complete mapping, design validations or explicitly initialize every constant.

**This illustrates a design benefit:** the domain of keys is defined by the enum type, while the values are data that can change according to business logic.

## 18. Comparing an Enum with Multiple Booleans

Suppose a ticket has exactly one status at a time:

```java
boolean newTicket;
boolean assigned;
boolean closed;
```

Three booleans produce **8 combinations**, including contradictory states such as both new and closed being true at the same time.

If the domain allows only one of the three states, an enum is more suitable:

```java
enum TicketStatus {
    NEW, ASSIGNED, CLOSED
}
```

`TicketStatus status` models **a single choice** from a finite set. There is no "both NEW and CLOSED" configuration in the same enum variable.

**What about when multiple choices apply simultaneously?** If an account has multiple permissions, using `EnumSet<Permission>` is more suitable than a single Permission variable.

**Do not force an enum to replace every boolean:** If two attributes are genuinely independent, such as `isVerified` and `hasPremiumPlan`, keeping two booleans may be right. Use an enum only when the domain consists of **mutually exclusive states** or **named finite kinds**.

## 19. Distinguishing Between "State" and "Event"

A modeling mistake is mixing an event occurring in time with a lasting state.

Example:

```java
enum OrderStatus {
    NEW, PAID, SHIPPED, CANCELLED
}

enum OrderEvent {
    PAYMENT_RECEIVED, SHIPMENT_SENT, CANCELLATION_REQUESTED
}
```

`OrderStatus.PAID` describes the current state. `OrderEvent.PAYMENT_RECEIVED` describes an event that can cause a state transition.

Both can be enums, but they are **two value domains with different meanings**. Separating the types makes the method `apply(OrderEvent event)` and the property `OrderStatus status` clearer.

**You should not** add vague values like `UPDATED` or `PROCESSED` into the same enum merely to lump all domain vocabulary together, if they do not belong to the same kind of concept.

## 20. An Enum State Does Not Automatically Forbid Invalid State Transitions

The `OrderStatus` type restricts the set of constants, but it **does not automatically enforce** valid state transitions.

For example, an application might forbid:

- `NEW -> SHIPPED` if payment has not been made.
- `CANCELLED -> PAID` if the order has already been closed.
- `SHIPPED -> NEW` if the workflow does not support going backward.

An enum helps model **the representable states**, whereas **transition** rules must be enforced by business code.

Create **`EnumTransitionDemo.java`**:

```java
enum OrderStatus {
    NEW, PAID, SHIPPED, CANCELLED
}

public class EnumTransitionDemo {
    static boolean canAdvance(OrderStatus from,
                              OrderStatus to) {
        if (from == null || to == null) {
            return false;
        }

        return switch (from) {
            case NEW -> to == OrderStatus.PAID
                    || to == OrderStatus.CANCELLED;
            case PAID -> to == OrderStatus.SHIPPED
                    || to == OrderStatus.CANCELLED;
            case SHIPPED, CANCELLED -> false;
        };
    }

    public static void main(String[] args) {
        System.out.println(canAdvance(
                OrderStatus.NEW, OrderStatus.PAID));
        System.out.println(canAdvance(
                OrderStatus.NEW, OrderStatus.SHIPPED));
        System.out.println(canAdvance(
                OrderStatus.CANCELLED, OrderStatus.PAID));
    }
}
```

```bash
javac EnumTransitionDemo.java
java EnumTransitionDemo
```

```text
true
false
false
```

**Scope:** This is only an example transition rule, not a full workflow engine. Order invariants (payment, inventory, refunds, idempotency) require additional separate conditions.

## 21. Parsing External Input: Do Not Assume Text Is Always an Enum Constant

In compiled Java code, `Priority.HIGH` is type-safe. However, input from UI, REST, CSV, or a database is usually a `String`. You must distinguish **Java constant names** from **external codes**.

Create **`EnumInputParsingDemo.java`**:

```java
import java.util.Locale;
import java.util.Optional;

enum Priority {
    LOW, MEDIUM, HIGH
}

public class EnumInputParsingDemo {
    static Optional<Priority> parse(String raw) {
        if (raw == null) {
            return Optional.empty();
        }

        String normalized =
                raw.trim().toUpperCase(Locale.ROOT);

        if (normalized.isEmpty()) {
            return Optional.empty();
        }

        try {
            return Optional.of(Priority.valueOf(normalized));
        } catch (IllegalArgumentException ex) {
            return Optional.empty();
        }
    }

    public static void main(String[] args) {
        System.out.println(parse(" high "));
        System.out.println(parse("urgent"));
        System.out.println(parse(null));
    }
}
```

```bash
javac EnumInputParsingDemo.java
java EnumInputParsingDemo
```

```text
Optional[HIGH]
Optional.empty
Optional.empty
```

Here, the parser intentionally accepts lowercase/surrounding whitespace, but **does not automatically accept every value**. `"urgent"` is not yet in the enum, so the result is Optional.empty.

**API rule:** Establish a consistent policy when input is invalid: return an Optional, a result type with a specific error, throw a meaningful exception, or send HTTP 400. Do not silently map every unknown value to an arbitrary constant if doing so loses business information.

### Uppercase Normalization with Locale

`toUpperCase(Locale.ROOT)` avoids relying on unsuitable regional rules when handling **technical codes**. However, **not every external code should be uppercased**: if the contract specifies case-sensitivity, respect that contract.

## 22. A Stable External Code Differs from `name()`

Using `name()` to store in a database or send over an API is simple, but **renaming an enum constant in code** can break existing data/clients.

A controlled approach is to **declare a stable external code**:

Create **`EnumStableCodeDemo.java`**:

```java
import java.util.Optional;

enum PaymentState {
    WAITING("P0"),
    SETTLED("P1"),
    REJECTED("P2");

    private final String code;

    PaymentState(String code) {
        this.code = code;
    }

    String code() {
        return code;
    }

    static Optional<PaymentState> fromCode(String raw) {
        if (raw == null) {
            return Optional.empty();
        }

        for (PaymentState state : values()) {
            if (state.code.equals(raw)) {
                return Optional.of(state);
            }
        }
        return Optional.empty();
    }
}

public class EnumStableCodeDemo {
    public static void main(String[] args) {
        System.out.println(PaymentState.SETTLED.code());
        System.out.println(PaymentState.fromCode("P2"));
        System.out.println(PaymentState.fromCode("P9"));
    }
}
```

```bash
javac EnumStableCodeDemo.java
java EnumStableCodeDemo
```

```text
P1
Optional[REJECTED]
Optional.empty
```

`WAITING` is the Java constant name, and `"P0"` is the external code. You can rename the Java identifier when refactoring is needed while preserving the external code, as long as mapping/compatibility is managed consistently.

**Do not use `ordinal()` as a stable storage code.** We will analyze why in the next section.

## 23. Why Not Use `ordinal()` as a Business ID?

Each enum constant has an `ordinal()` representing its 0-based declaration position.

```java
enum Priority {
    LOW, MEDIUM, HIGH
}
```

Here LOW has ordinal 0, MEDIUM has 1, and HIGH has 2. If in the future a constant is inserted at the beginning or the declaration order changes, the other ordinals can change.

Create **`EnumOrdinalDemo.java`**:

```java
enum Priority {
    LOW, MEDIUM, HIGH
}

public class EnumOrdinalDemo {
    public static void main(String[] args) {
        for (Priority p : Priority.values()) {
            System.out.println(p.name() + ":" + p.ordinal());
        }
    }
}
```

```bash
javac EnumOrdinalDemo.java
java EnumOrdinalDemo
```

```text
LOW:0
MEDIUM:1
HIGH:2
```

**Pitfall:** If the database has already stored 1 meaning MEDIUM and later you add `URGENT` before MEDIUM, 1 can become URGENT. The meaning of existing data changes without any compiler warning.

- `ordinal()` is useful for certain internal implementations/collections.
- `EnumSet` and `EnumMap` handle it efficiently without clients needing to store ordinals.
- In persistence/external APIs, choose an **explicit stable code** if compatibility matters.
- Even storing `name()` requires a migration policy when renaming/removing constants.

## 24. `toString()` Can Serve for Display, Not as the Default Parsing Contract

`name()` is the declared constant name and cannot be overridden. `toString()` can be overridden for friendly presentation.

Create **`EnumDisplayDemo.java`**:

```java
enum Status {
    IN_PROGRESS("Dang xu ly"),
    COMPLETED("Hoan thanh");

    private final String display;

    Status(String display) {
        this.display = display;
    }

    @Override
    public String toString() {
        return display;
    }
}

public class EnumDisplayDemo {
    public static void main(String[] args) {
        Status status = Status.IN_PROGRESS;

        System.out.println(status.name());
        System.out.println(status.toString());
        System.out.println(Status.valueOf("IN_PROGRESS"));
    }
}
```

```bash
javac EnumDisplayDemo.java
java EnumDisplayDemo
```

```text
IN_PROGRESS
Dang xu ly
Dang xu ly
```

The third line returns `Status.IN_PROGRESS` from `valueOf` and then `println` invokes the **overridden `toString()`**, so it prints `Dang xu ly`, not the constant name.

**Conclusion:** Distinguish **identifier**, **display text**, and **external serialization code**. Three different values may be needed; do not force `toString` to serve both the database and the UI at the same time.

In multilingual applications, message keys/resource bundles should be used instead of embedding all translations into the enum, if the domain requires dynamic localization.

## 25. An Enum Can Implement Interfaces, but Cannot Extend Arbitrary Classes

An enum type inherits from `java.lang.Enum<E>` by language mechanism; it cannot explicitly `extends MyBaseClass` on its own.

However, an enum **can implement interfaces**, allowing multiple enum types to participate in the same contract.

Create **`EnumInterfaceDemo.java`**:

```java
interface Code {
    String code();
}

enum Severity implements Code {
    INFO("I"),
    WARNING("W"),
    ERROR("E");

    private final String value;

    Severity(String value) {
        this.value = value;
    }

    @Override
    public String code() {
        return value;
    }
}

public class EnumInterfaceDemo {
    static void printCode(Code value) {
        System.out.println(value.code());
    }

    public static void main(String[] args) {
        printCode(Severity.WARNING);
        System.out.println(Severity.ERROR instanceof Code);
    }
}
```

```bash
javac EnumInterfaceDemo.java
java EnumInterfaceDemo
```

```text
W
true
```

`Severity` has exactly three named constants, while `Code` is a shared interface. Implementing an interface **does not make the enum's constant set extensible**; it only provides an additional behavioral contract.

**If new unknown implementations are genuinely needed**, an interface + concrete classes/registry will be more suitable than a closed enum.

## 26. Beware of Mutable Fields in Enum Constants

Although additional constants cannot be created by clients, **fields of an enum object are not automatically immutable**.

This is an example of **a design intentionally exposing the risk**:

```java
enum Mode {
    STANDARD;

    private int counter;

    void increment() {
        counter++;
    }

    int counter() {
        return counter;
    }
}
```

`Mode.STANDARD` is a shared enum constant object. If one module calls `increment()`, another module can see counter change. That is not per-user/per-request state.

### Recommendations

- Enum constants should have **immutable metadata**, typically `private final`.
- Do not place request-specific/user-specific counters or hard-to-control mutable caches into an enum.
- If data needs to change per request, place the state in a **separate class instance** or a properly managed service/collection.
- A mutable enum field shared across threads requires synchronization/atomicity; the enum type does not automatically provide thread safety for that mutable state.

**Distinction:** Stable constant identity does not imply immutable state.

## 27. `null` Is Still a Reference Value That Can Appear

Even though the type is an enum:

```java
Priority priority = null;
```

the statement is valid under Java reference typing. Therefore, an enum **does not completely eliminate invalid runtime state** if the business contract forbids null.

When validating the boundary:

```java
Objects.requireNonNull(priority, "priority");
```

This is a code snippet, assuming `java.util.Objects` has already been imported.

A comparison:

```java
if (priority == Priority.HIGH) {
    // ...
}
```

is **null-safe**, but does not necessarily replace validation: if a business operation requires a priority, silently treating null as false can hide a bug. Decide explicitly whether null is acceptable.

Do not overuse an `UNKNOWN` constant merely to avoid handling null if `UNKNOWN` is not a valid domain state. `UNKNOWN` makes sense when it **truly** is a designed value kind, for example an undetermined state clearly distinguished from invalid data.

## 28. Enums and `switch`: Adding a Constant Is a Domain Change

An enum is considered a closed set **within the current version**. When adding a constant, operations based on that set may need to be updated.

Initial example:

```java
enum Priority {
    LOW, MEDIUM, HIGH
}
```

If `CRITICAL` is added, review:

- `switch` expressions need to handle CRITICAL according to business logic.
- Does `EnumMap` have a complete mapping?
- Do `EnumSet` rules automatically include the new constant?
- Does the input/output API accept the new external code?
- Does already persisted data need migration/compatibility?
- Does the UI have a new label, new sorting order, or new analytics grouping?
- Did previous tests implicitly assume `values().length == 3`?

**A closed set does not mean it never changes across software versions**. It means changing the set is an **intentional code/schema change**, unlike a user adding values into a runtime table.

## 29. Do Not Use Enums to Represent Individual Data Records

Compare the following:

- `OrderStatus` has a few shared business values: an enum is suitable.
- `Order` is a record with an ID, customer, items, and timestamps: it needs its own **class/record/entity**, not one enum constant per order.
- `UserRole` can be an enum if the role policy is closed in code: ADMIN, USER, REVIEWER.
- If roles are created dynamically by administrators and assigned arbitrary permissions: a database-backed Role entity or configuration may be more suitable.

**Distinguishing set-of-types from set-of-data-records:** An enum describes a **number of named choices**, and does not replace a data table or a collection of instances with their own lifecycles.

## 30. Modeling Exercise: Choosing an Enum, a Boolean, or a Class?

| Problem | Potentially Suitable Model | Reason |
| --- | --- | --- |
| Red/yellow/green traffic light signal | `enum Signal` | Finite named set, one selected at a time |
| North/east/south/west direction | `enum Direction` | Four clear domain names |
| Which stage an order is currently in | `enum OrderStatus` | One state from a defined set |
| Permissions enabled at the same time | `EnumSet<Permission>` | Multiple choices active simultaneously |
| A quantity from 0–100 | `int` with validation | No 101 useful constant names |
| A user's username | `String`/value object | Dynamic values, not closed |
| Whether confirmed or not | `boolean` if strictly two cases | Easy to understand when genuinely binary |
| Three booleans representing one mutually exclusive status | `enum` is better | Avoids contradictory combinations |
| Plugin configuration registrable at runtime | Interface + registry/classes | Closed enum is not dynamically extensible |
| Alert level with fixed code and label | Enum with final fields | Data attached to each constant |
| Product codes in a catalog changing daily | Entity/value type | Set determined by data |
| Days of the week | `DayOfWeek` in the JDK | Standard enum already exists in `java.time` |
| Country values from an updating service | Consider a data-driven source | Not closed by default in Java code |

**Self-check rule:** "Can you write out the full names of every choice directly in the source code today, and will changes to the set only happen through controlled releases?" If yes, an enum is a strong candidate.

## 31. Self-Testing with Assertions Independent of `-ea`

A self-test suite can verify the contract of the constant set and mappings, not just print names.

Create **`EnumContractSelfTest.java`**:

```java
import java.util.EnumMap;
import java.util.EnumSet;

enum Priority {
    LOW, MEDIUM, HIGH
}

public class EnumContractSelfTest {
    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        check(Priority.values().length == 3, "count");
        check(Priority.valueOf("HIGH") == Priority.HIGH,
                "valueOf mapping");
        check(Priority.HIGH == Priority.HIGH, "identity");

        EnumSet<Priority> selected =
                EnumSet.of(Priority.LOW, Priority.HIGH);

        check(selected.contains(Priority.HIGH),
                "set membership");
        check(!selected.contains(Priority.MEDIUM),
                "set non-membership");

        EnumMap<Priority, Integer> weights =
                new EnumMap<>(Priority.class);

        weights.put(Priority.LOW, 1);
        weights.put(Priority.MEDIUM, 2);
        weights.put(Priority.HIGH, 3);

        for (Priority value : Priority.values()) {
            check(weights.containsKey(value),
                    "missing mapping for " + value);
        }

        check(weights.get(Priority.HIGH) == 3,
                "high weight");
        System.out.println("enum contract PASS");
    }
}
```

```bash
javac EnumContractSelfTest.java
java EnumContractSelfTest
```

```text
enum contract PASS
```

`check` actively throws `AssertionError` when false, without requiring JVM assertions to be enabled via `-ea`. This self-test only covers a Priority set with three constants; when a constant is added, it intentionally signals that the test/EnumMap mapping needs updating.

**Important:** Do not hardcode checks on the number of constants everywhere in production if growth across releases is expected. In a self-test for a specific domain contract, checking the exact count can be intentional; in application code, prefer iterating over `values()` or using an appropriate rule.

## 32. Common Mistakes and Fixes

| Misconception | Issue | Fix |
| --- | --- | --- |
| "An enum is just a few constant strings" | Loses understanding of type safety/object semantics | Treat an enum as a type with named constant instances |
| "Any string can be assigned to an enum" | Compile-time type mismatch | Parse/validate the String first |
| "`valueOf` is automatically case-insensitive" | Matches the exact name case-sensitively | Normalize intentionally or use an external-code parser |
| "`values()` allows modifying the constant set" | Only returns an array containing references | Do not treat the array as an open registry |
| "New constants can be created on an enum with new" | Enum constructors do not publicly create instances | Define constants in the declaration |
| "Enum singletons mean all state is immutable" | Mutable fields on shared constants still change | Keep final immutable metadata |
| "Ordinal is a stable ID" | Declaration order can change | Use an explicit external code |
| "`toString()` is always `name()`" | Can be overridden | Separate name, code, and display |
| "An enum cannot be null" | Enum is a reference type | Validate at the boundary if null is not accepted |
| "Two enums with the same constant name are interchangeable" | Two different Java types | Have the API accept the domain-specific enum |
| "A status enum automatically guards transitions" | The type only restricts values | Add a state machine/validation |
| "EnumMap automatically has all constant keys" | The map may be missing mappings | Check completeness if the contract requires it |
| "EnumSet is immutable" | EnumSet is normally mutable | Copy/wrap according to the contract |
| "An enum replaces dynamic data" | A closed set does not suit a runtime-updated catalog | Use a value object/DB registry |
| "Adding a constant is a small change, no review needed" | Switches/mappings/APIs/persistence may be affected | Review exhaustive consumers and migration |
| "One shared enum for all statuses" | Mixes domains and loses type safety | Split enums by semantics |
| "Use an enum instead of every boolean" | Truly binary cases exist | Choose a simpler type that is clear enough |
| "Adding multiple boolean flags for mutually exclusive states" | Allows contradictory states | Use a single-value enum |
| "An enum is an open plugin system" | Constants cannot be self-registered | Use an interface/registry when extensibility is needed |
| "A default in switch is always better" | Can hide newly added unhandled constants | Consider an exhaustive switch expression without default |
| "All enums have a business ordering" | Declaration order is not necessarily domain order | Define an explicit rank if needed |

## 33. Self-Check Questions

**Question 1.** Why is an enum suitable for `Priority { LOW, MEDIUM, HIGH }`?

*Answer:* It is a named, finite set of choices closed in source code; having its own type prevents confusion with String/int or other enums.

**Question 2.** Can you write `new Priority()` from client code?

*Answer:* No; Java manages enum constants and does not allow creating arbitrary enum instances.

**Question 3.** What does `Priority.HIGH == Priority.HIGH` evaluate to?

*Answer:* true, the same constant instance.

**Question 4.** Does `Priority.valueOf("high")` work?

*Answer:* Not for the declared name HIGH; valueOf is case-sensitive and throws IllegalArgumentException.

**Question 5.** What does `Priority.values()` return?

*Answer:* A new array of the constants in declaration order.

**Question 6.** Can you assign `Priority p = null`?

*Answer:* Yes; you must validate if the domain forbids null.

**Question 7.** Can two enums that both have a `DONE` constant be used interchangeably in a method parameter?

*Answer:* No; Java distinguishes enum types.

**Question 8.** Why should ordinal not be stored in a database?

*Answer:* Ordinal is the declaration position, which can change when constants are inserted or reordered.

**Question 9.** Are `name()` and `toString()` always the same?

*Answer:* No; an enum can override toString, while name remains the constant identifier.

**Question 10.** How do you store a stable `"P1"` code for `PaymentState.SETTLED`?

*Answer:* Attach a final code field and a parse/fromCode method using an explicit mapping.

**Question 11.** Can an enum have constructors and methods?

*Answer:* Yes, subject to enum restrictions; constructors are used to create the constants defined by the declaration.

**Question 12.** Can an enum constant have its own class body overriding behavior?

*Answer:* Yes; this does not make the set of constants dynamically extensible.

**Question 13.** When is `EnumSet` suitable?

*Answer:* Storing a set of multiple constants of the same enum type, such as enabled permissions.

**Question 14.** Does `EnumMap` guarantee every enum key has an entry?

*Answer:* No; entries can still be missing, so mappings must be validated according to the contract.

**Question 15.** When is a boolean better than an enum?

*Answer:* For questions that truly have only two independent values and where the boolean name is clear.

**Question 16.** Should an enum be used for IDs of millions of orders?

*Answer:* No; that is dynamic data and should use a value/entity type.

**Question 17.** Does an enum automatically block `NEW -> SHIPPED`?

*Answer:* No; transitions require separate business validation.

**Question 18.** Where can adding a constant to an enum have an impact?

*Answer:* Exhaustive switches, mappings, UI, persistence, serialization, tests, and integrations.

**Question 19.** Can an enum implement an interface?

*Answer:* Yes; however, it cannot arbitrarily extend a user-defined class because an enum inherits from Enum by language mechanism.

**Question 20.** Why is a mutable counter inside an enum constant dangerous?

*Answer:* The constant object is shared; the counter is shared mutable state, which can cause aliasing/concurrency issues.

**Question 21.** Does `EnumSet.allOf(Priority.class)` create an immutable object?

*Answer:* No; it creates an EnumSet containing all current constants, and the resulting set is normally still mutable.

**Question 22.** Can an enum be used when users are allowed to create new types themselves on a website without deploying code?

*Answer:* Usually no; a data-driven model/registry is needed.

**Question 23.** If both `OrderStatus.PAID` and `PaymentStatus.PAID` exist, are they the same constant?

*Answer:* No, they are constants of two different types.

**Question 24.** What is the essence of a "named finite set" in an enum?

*Answer:* A Java type explicitly declares the entire set of named constant instances supported by that version of the source code, instead of allowing arbitrary objects/strings.

## 34. Enum Design Checklist

- [ ] Is the domain truly a **discrete, named set of choices closed by code version**?
- [ ] Do the constant names accurately express the domain semantics?
- [ ] Is the enum type specific enough without lumping different domains together?
- [ ] Do method signatures use the enum instead of String/int where appropriate?
- [ ] Have you distinguished a single choice from a set of multiple choices (`EnumSet`)?
- [ ] If the enum represents states, are transition rules checked separately?
- [ ] Are you avoiding using enums for IDs/data with a dynamic count that cannot be known in advance?
- [ ] Are `null` and unknown external inputs validated?
- [ ] Is `valueOf` being used strictly with case-sensitive constant names?
- [ ] If the external contract uses text codes, is the stable code separated from `name()`?
- [ ] Are you avoiding storing `ordinal()` as a business ID or persisted code?
- [ ] Does `toString()` serve only for display if overridden?
- [ ] Do constant metadata use immutable fields when possible?
- [ ] Are you avoiding placing per-request mutable state into enum constants?
- [ ] If per-constant behavior is complex, have you considered a separate strategy/service?
- [ ] Do `EnumMap` instances have complete mappings if required?
- [ ] Do `switch` expressions reflect all constants that need handling?
- [ ] Are adding/renaming constants accompanied by tests and schema/API reviews?
- [ ] Is an interface/registry used when the system genuinely needs runtime extensibility?
- [ ] Do code samples have matching file/public class names and do `javac`/`java` commands run on Java 17+?
- [ ] Does stdout avoid depending on unstable data such as hash codes, timing, or non-deterministic Map iteration order?

---

**Final takeaway:** In Java, **`enum` is a type that models a set of **named constant instances** finitely specified in the source declaration**. It is suitable for value domains such as priority levels, directions, statuses, modes, or permissions, where the compiler can distinguish types and verify valid choices. An enum is not merely strings or numbers: constants are objects, can carry metadata/behavior, and work with `==`, `switch`, `EnumSet`, and `EnumMap`. However, a closed constant set does not make all data immutable or all state transitions valid; `null`/external inputs still must be validated, and `ordinal()` is not a stable storage ID. **Use an enum when the list of choices is a version-stable design decision; use data-driven models or interfaces when the list needs to be dynamically extended.**
