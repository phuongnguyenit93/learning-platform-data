# Comparing Pattern Matching vs. Registry Handler: Command Case Study in Java 21+

## 1. The problem: routing multiple command types

In an order processing application, a dispatcher layer may receive commands such as:

- **`Create(id, units)`:** creates a new order with an order ID and quantity.
- **`Cancel(id, reason)`:** cancels an order with a reason.
- **`Ship(id, tracking)`:** hands over an order to the carrier with a tracking number.
- **`Export(report)`:** requests a report export, illustrating an extension that may be added by another module.

A common design question is: **should you write a `switch` with pattern matching for each command, or build a registry mapping command types to handlers?**

Both approaches can be right, but they optimize for different characteristics:

1. **Pattern `switch` over a `sealed` subtype set:** easy to see all cases at a glance, no handler registration needed, and the compiler helps verify *exhaustiveness*.
2. **Registry handler:** each handler is registered under a key (for example `Class<?>`); the dispatcher looks up the handler at runtime. Suitable when handler configuration, module assembly, or extensions vary by environment.
3. **Hybrid:** handle **core commands** with `sealed` and pattern matching; provide an open layer for **plugin actions** if the system genuinely needs to add command types externally.

You should not assume a registry is automatically a "better architecture" because it has more classes, or that `switch` is always better because it has less code. You need to consider **whether the command set is closed or open**, where business logic lives, type safety, clarity of missing-handler errors, operational overhead, and frequency of extension.

This article uses **Java 21+** with `sealed interface`, `record`, type patterns in `switch`, generic handlers, and `Map.copyOf`. A standalone program verifies both strategies on the same business logic, with **28 checks**.

## 2. Modeling the domain: intentionally separating closed and open sets

We define an open interface for all actions, and then a `sealed` interface dedicated to the core commands:

~~~java
interface Action {}

sealed interface CoreCommand extends Action
        permits Create, Cancel, Ship {}

record Create(String id, int units) implements CoreCommand {}
record Cancel(String id, String reason) implements CoreCommand {}
record Ship(String id, String tracking) implements CoreCommand {}

// Extension: belongs to Action, but not CoreCommand.
record Export(String report) implements Action {}
~~~

These are **illustrative declarations**. They are placed inside a runnable class in section 8.

Type hierarchy:

~~~text
Action (open interface)
├── CoreCommand (sealed)
│   ├── Create (record/final)
│   ├── Cancel (record/final)
│   └── Ship (record/final)
└── Export (record/final, extension example)
~~~

This separation is intentional:

- `CoreCommand` is a **closed set**: the compiler knows the exact three permitted direct subtypes. A `switch expression` handling `Create`, `Cancel`, and `Ship` can omit `default`.
- `Action` is an **open interface**: other modules can declare additional implementations. The registry accepts objects of type `Action` and looks up the handler by runtime type.
- `Export` is an implementation of `Action`, **not** a subtype of `CoreCommand`. Therefore, a method taking a `CoreCommand` parameter cannot accept `Export` directly; this is a useful type boundary, not an unexpected error.

**Note:** the `Export` example only illustrates extensibility via in-code registration. It does **not** automatically perform plugin discovery, hot reload, dependency injection, or external JAR loading. Those mechanisms must be designed separately if the project requires them.

### Two levels of responsibility

- **Command model** answers "what is the command, and what data does it carry?".
- **Dispatcher** answers "which handler should this command be routed to?".
- **Handler/service** answers "is the data valid and do the business rules allow this action?".

Keeping these three responsibilities separate makes the comparison fair: **both `switch` and registry will call the exact same set of business handler functions**, rather than writing two different versions of the logic and comparing readability or outcomes.

## 3. Shared business contract so both dispatch approaches are equivalent

We use an order state enum:

~~~java
enum State { MISSING, CREATED, PAID, SHIPPED }

record Context(State state) {
    Context {
        java.util.Objects.requireNonNull(state, "state");
    }
}
~~~

`Context` holds the current state of the target object to be processed. In a real application, the state might come from a database along with user permissions, versioning/locking, or other constraints; this article intentionally uses a small value object and **does not mutate state** to keep the focus on the dispatch mechanism.

Outcomes are categorized by a data type:

~~~java
enum Code { OK, INVALID, REJECTED, UNSUPPORTED }
record Outcome(Code code, String detail) {}
~~~

Where:

| Outcome | Meaning in the example |
| --- | --- |
| `OK` | Data and state allow the operation to succeed |
| `INVALID` | Payload is missing or fails validation |
| `REJECTED` | Payload is valid, but the current state does not allow it |
| `UNSUPPORTED` | The registry has no handler for the received action type |

**Clear distinction**: `UNSUPPORTED` is not a `ClassCastException`; it is an intentional outcome when no handler is found. `REJECTED` does not mean invalid data: for example, a `Ship` command has a well-formed tracking number, but the order state is not yet `PAID`.

Illustrative rules:

- `Create`: `id` is non-blank, `units > 0`; can only be created when state is `MISSING`.
- `Cancel`: `id` and `reason` are non-blank; can only be cancelled when state is `CREATED` or `PAID`.
- `Ship`: `id` and `tracking` are non-blank; can only be shipped when state is `PAID`.
- `Export`: `report` is non-blank; is an extension in the registry and does not check order state.

These numbers, names, and policies are only rules **for this case study**; they are not meant to prescribe rules for every e-commerce system.

Example of a business handler:

~~~java
static Outcome onShip(Ship command, Context context) {
    if (blank(command.id())) return invalid("orderId");
    if (blank(command.tracking())) return invalid("tracking");
    if (context.state() != State.PAID) return rejected("requires-paid");

    return ok("shipped:" + command.id() + ":" + command.tracking());
}
~~~

This is an **illustrative method** using the `blank`, `invalid`, `rejected`, and `ok` helpers fully declared in the program in section 8.

Crucial point for the comparison: **do not put validation logic inside only one dispatcher**. If both dispatchers call `onShip(...)`, the only remaining difference is how the handler is selected.

## 4. Approach A — Pattern `switch` over `sealed CoreCommand`

Concise dispatch method:

~~~java
static Outcome viaSwitch(CoreCommand command, Context context) {
    java.util.Objects.requireNonNull(context, "context");

    return switch (command) {
        case null -> invalid("request");
        case Create c -> onCreate(c, context);
        case Cancel c -> onCancel(c, context);
        case Ship c -> onShip(c, context);
    };
}
~~~

This is a **runnable method when placed inside the full class** in section 8.

### Why is this approach easy to read?

- Each `case` represents a concrete command type.
- The pattern variable `c` has the exact static type (`Create`, `Cancel`, `Ship`), with no cast required.
- There is no lookup in a `Map` or registration configuration located elsewhere.
- Because `CoreCommand` is `sealed` and the three `record` subtypes are final, the Java 21 compiler verifies that the branches **cover all non-null core commands**.
- `case null` explicitly declares the null-selector policy: return `INVALID:request`, preventing an unexpected `NullPointerException`.

**Case to remember:** `default` in a Java 21 pattern `switch` **does not automatically handle a `null` selector**. Therefore, if the API allows null, use `case null`; if the API forbids null, you can proactively call `Objects.requireNonNull(command, "command")` before the `switch`.

### When adding a new core command

Suppose we have:

~~~java
// Illustrative declaration, not part of the main program:
record Refund(String id, long cents) implements CoreCommand {}
~~~

If `Refund` is added to `CoreCommand`'s `permits` clause but `viaSwitch` does not yet have a `Refund` branch, the compiler can reject it because the `switch expression` is not exhaustive. **This is a safety advantage during maintenance**, especially when the core command set is controlled by the same team.

You should not add `default -> unsupported(...)` to `viaSwitch` just to avoid updating it when expanding the core set: a broad default branch can mask an omission that the compiler ought to warn about.

### Limitations

The `switch` approach does not allow automatically "plugging in" a handler for a brand-new command type without modifying the type declaration or the call site. An `Export` that only implements the open `Action` interface cannot be passed directly to `viaSwitch(CoreCommand, ...)`. If the runtime needs to accept many command types declared by independent plugins, a `sealed` hierarchy may not be suitable as the sole dispatch layer.

## 5. Approach B — Registry handler: mapping classes to handler functions

The registry maintains a table:

~~~text
Create.class  -> onCreate(Create, Context)
Cancel.class  -> onCancel(Cancel, Context)
Ship.class    -> onShip(Ship, Context)
Export.class  -> onExport(Export, Context)   // only in extended registry
~~~

When an action arrives, it looks up the table by the action's runtime class:

~~~java
Registration<? extends Action> match =
        handlers.get(action.getClass());

if (match == null) {
    return unsupported(action.getClass().getSimpleName());
}
return match.run(action, context);
~~~

This is the **illustrative body** of the `Registry.dispatch` method. It is fully tested in the program in section 8.

### Why use `Class` instead of strings?

You could write `Map<String, Handler>` with keys like `"CREATE"`, `"CANCEL"`, etc. However, strings are prone to typos, collisions, or renames that the compiler cannot catch. In this case study, `Class<C>` is a key tied to a concrete Java type and enables **registering handlers with the right type parameter**.

Desired registration syntax:

~~~java
new Registry.Builder()
        .add(Create.class, CommandRegistryComparisonDemo::onCreate)
        .add(Cancel.class, CommandRegistryComparisonDemo::onCancel)
        .add(Ship.class, CommandRegistryComparisonDemo::onShip)
        .build();
~~~

Each call to `add(Class<C>, Handler<C>)` requires a handler that accepts commands of type `C`. For instance, you cannot easily register `onShip(Ship, Context)` under the key `Create.class` when keeping the generic signature and exact method reference.

**However**, runtime handler lookup is not proven exhaustive by the compiler like a `switch` over `sealed`: forgetting to register `Ship.class` still compiles and is only discovered at runtime or by tests checking coverage.

## 6. Writing a registry without unchecked casts

An overly naive registry is often written as:

~~~java
// Illustrative anti-pattern: unchecked cast, which can hide type-safety errors.
Map<Class<?>, Object> handlers = new java.util.HashMap<>();
Object handler = handlers.get(command.getClass());
// Casting to an arbitrary generic handler here is very error-prone and unsafe.
~~~

In Java, type erasure means a direct cast from `Handler<?>` to `Handler<Create>` cannot be fully verified at runtime. You should not overuse `@SuppressWarnings("unchecked")` when a safer alternative exists.

Use a `Registration<C extends Action>` class that **encapsulates the key and handler pair under the same type parameter**:

~~~java
@FunctionalInterface
interface Handler<C extends Action> {
    Outcome handle(C command, Context context);
}

static final class Registration<C extends Action> {
    private final Class<C> type;
    private final Handler<C> handler;

    Registration(Class<C> type, Handler<C> handler) {
        this.type = type;
        this.handler = handler;
    }

    Outcome run(Action action, Context context) {
        return handler.handle(type.cast(action), context);
    }
}
~~~

Here:

1. `Class<C> type` and `Handler<C> handler` share `C`, so the registration is type-consistent.
2. `Class.cast(action)` checks at runtime that the object actually belongs to the registered type; there is no need for an unchecked generic handler cast.
3. `Registry.dispatch` only calls `run` on `Registration<? extends Action>`; the wildcard is encapsulated inside the registration, where `C` remains consistent.
4. `Class.cast` **can still throw `ClassCastException`** if called with the wrong object or if the registry data is constructed improperly. In the normal dispatch path, looking up by `action.getClass()` and adding entries via the generic builder avoids that situation.

A builder:

~~~java
static final class Builder {
    private final java.util.Map<Class<? extends Action>,
            Registration<? extends Action>> entries =
            new java.util.HashMap<>();

    <C extends Action> Builder add(Class<C> type, Handler<C> handler) {
        java.util.Objects.requireNonNull(type, "type");
        java.util.Objects.requireNonNull(handler, "handler");

        if (entries.putIfAbsent(type,
                new Registration<>(type, handler)) != null) {
            throw new IllegalArgumentException(
                    "duplicate handler: " + type.getSimpleName());
        }
        return this;
    }
}
~~~

The snippet above is **the core part of the builder**; the `build()` method and full `Registry` class are in section 8. Checking `putIfAbsent` causes duplicate registration errors to surface **immediately during initialization**, rather than silently overwriting the previous handler.

### Freezing the registry after registration

The program uses:

~~~java
this.handlers = java.util.Map.copyOf(handlers);
~~~

`Map.copyOf` creates an unmodifiable map through the map API. After `build()`, the registry does not accept new registrations; adding extensions requires creating **a new registry with a new set of registrations**.

This reduces the risk of handlers changing mid-flight while multiple threads are dispatching. However, **an immutable map does not automatically make handlers thread-safe**. If a handler holds mutable state, connections, or shared caches, synchronization and lifecycle must still be protected at the appropriate layer.

## 7. Fair comparison: two dispatchers calling shared business logic

We do not duplicate `onCreate`, `onCancel`, and `onShip` per architecture. Both `viaSwitch` and `Registry.dispatch` select **the exact same business function**.

For example, with `Create("O1", 3)` and `Context(MISSING)`:

~~~text
             +----------------------+
             | CoreCommand: Create  |
             +----------------------+
                      |
           +----------+-----------+
           |                      |
           v                      v
    Pattern switch             Registry
    case Create c        handlers[Create.class]
           |                      |
           +----------+-----------+
                      |
                      v
            onCreate(Create, Context)
                      |
                      v
           Outcome(OK, "created:O1:3")
~~~

When `Create("O1", 0)`, both return `Outcome(INVALID, "units")`. When the context is already `CREATED`, both return `Outcome(REJECTED, "order-exists")`.

**An important detail:** business validation rules are checked **before verifying whether the state permits the action**. For example, `Create(" ", 0)` even when the order already exists will report the `orderId` data error first. If you change the check order in the handlers, both dispatch strategies will still match, but **the API's error contract has changed**; you should test precedence order.

### How the registry method handles null and missing handlers

The main program uses:

~~~java
Outcome dispatch(Action action, Context context) {
    java.util.Objects.requireNonNull(context, "context");

    if (action == null) return invalid("request");

    Registration<? extends Action> match =
            handlers.get(action.getClass());

    if (match == null) {
        return unsupported(action.getClass().getSimpleName());
    }
    return match.run(action, context);
}
~~~

The registry distinguishes:

- `null` action → `INVALID:request`.
- No handler for the runtime class → `UNSUPPORTED:<type>`.
- Handler present → returns `OK`, `INVALID`, or `REJECTED` depending on business logic.

**You should not** replace this entire path with `try/catch (ClassCastException | NullPointerException)` and treat everything as a data error. Programming exceptions, missing handlers, and invalid payloads are distinct events.

## 8. Complete Java 21 program — 28 test cases

Save the exact code as **`CommandRegistryComparisonDemo.java`**. The program uses only the JDK, requiring no Maven, DI framework, or external libraries.

~~~java
public class CommandRegistryComparisonDemo {
    interface Action {}

    sealed interface CoreCommand extends Action
            permits Create, Cancel, Ship {}

    record Create(String id, int units) implements CoreCommand {}
    record Cancel(String id, String reason) implements CoreCommand {}
    record Ship(String id, String tracking) implements CoreCommand {}
    record Export(String report) implements Action {}

    enum State { MISSING, CREATED, PAID, SHIPPED }
    enum Code { OK, INVALID, REJECTED, UNSUPPORTED }

    record Context(State state) {
        Context {
            java.util.Objects.requireNonNull(state, "state");
        }
    }

    record Outcome(Code code, String detail) {}
    record Case(String name, CoreCommand command, Context context,
                Outcome expected) {}

    static Outcome ok(String detail) {
        return new Outcome(Code.OK, detail);
    }

    static Outcome invalid(String detail) {
        return new Outcome(Code.INVALID, detail);
    }

    static Outcome rejected(String detail) {
        return new Outcome(Code.REJECTED, detail);
    }

    static Outcome unsupported(String detail) {
        return new Outcome(Code.UNSUPPORTED, detail);
    }

    static boolean blank(String text) {
        return text == null || text.isBlank();
    }

    static Outcome onCreate(Create command, Context context) {
        if (blank(command.id())) return invalid("orderId");
        if (command.units() <= 0) return invalid("units");
        if (context.state() != State.MISSING) return rejected("order-exists");
        return ok("created:" + command.id() + ":" + command.units());
    }

    static Outcome onCancel(Cancel command, Context context) {
        if (blank(command.id())) return invalid("orderId");
        if (blank(command.reason())) return invalid("reason");
        if (context.state() == State.MISSING) {
            return rejected("order-not-found");
        }
        if (context.state() == State.SHIPPED) {
            return rejected("already-shipped");
        }
        return ok("cancelled:" + command.id());
    }

    static Outcome onShip(Ship command, Context context) {
        if (blank(command.id())) return invalid("orderId");
        if (blank(command.tracking())) return invalid("tracking");
        if (context.state() != State.PAID) {
            return rejected("requires-paid");
        }
        return ok("shipped:" + command.id() + ":" + command.tracking());
    }

    static Outcome onExport(Export action, Context context) {
        if (blank(action.report())) return invalid("report");
        return ok("export:" + action.report());
    }

    static Outcome viaSwitch(CoreCommand command, Context context) {
        java.util.Objects.requireNonNull(context, "context");
        return switch (command) {
            case null -> invalid("request");
            case Create c -> onCreate(c, context);
            case Cancel c -> onCancel(c, context);
            case Ship c -> onShip(c, context);
        };
    }

    @FunctionalInterface
    interface Handler<C extends Action> {
        Outcome handle(C command, Context context);
    }

    static final class Registration<C extends Action> {
        private final Class<C> type;
        private final Handler<C> handler;

        Registration(Class<C> type, Handler<C> handler) {
            this.type = type;
            this.handler = handler;
        }

        Outcome run(Action action, Context context) {
            return handler.handle(type.cast(action), context);
        }
    }

    static final class Registry {
        private final java.util.Map<Class<? extends Action>,
                Registration<? extends Action>> handlers;

        private Registry(java.util.Map<Class<? extends Action>,
                Registration<? extends Action>> handlers) {
            this.handlers = java.util.Map.copyOf(handlers);
        }

        Outcome dispatch(Action action, Context context) {
            java.util.Objects.requireNonNull(context, "context");
            if (action == null) return invalid("request");

            Registration<? extends Action> match =
                    handlers.get(action.getClass());

            if (match == null) {
                return unsupported(action.getClass().getSimpleName());
            }
            return match.run(action, context);
        }

        java.util.Set<Class<? extends Action>> types() {
            return handlers.keySet();
        }

        static final class Builder {
            private final java.util.Map<Class<? extends Action>,
                    Registration<? extends Action>> entries =
                    new java.util.HashMap<>();

            <C extends Action> Builder add(
                    Class<C> type, Handler<C> handler) {
                java.util.Objects.requireNonNull(type, "type");
                java.util.Objects.requireNonNull(handler, "handler");

                if (entries.putIfAbsent(type,
                        new Registration<>(type, handler)) != null) {
                    throw new IllegalArgumentException(
                            "duplicate handler: "
                            + type.getSimpleName());
                }
                return this;
            }

            Registry build() {
                return new Registry(entries);
            }
        }
    }

    static Registry.Builder coreBuilder() {
        return new Registry.Builder()
                .add(Create.class,
                        CommandRegistryComparisonDemo::onCreate)
                .add(Cancel.class,
                        CommandRegistryComparisonDemo::onCancel)
                .add(Ship.class,
                        CommandRegistryComparisonDemo::onShip);
    }

    static final Registry CORE = coreBuilder().build();
    static final Registry EXTENDED = coreBuilder()
            .add(Export.class, CommandRegistryComparisonDemo::onExport)
            .build();

    private static int passed = 0;

    static void check(String label, boolean condition) {
        if (!condition) throw new AssertionError(label);
        passed++;
        System.out.println("PASS " + label);
    }

    static void compare(Case item) {
        Outcome expected = item.expected();
        Outcome bySwitch =
                viaSwitch(item.command(), item.context());
        Outcome byRegistry =
                CORE.dispatch(item.command(), item.context());

        if (!expected.equals(bySwitch)
                || !expected.equals(byRegistry)) {
            throw new AssertionError(
                    item.name() + ": expected=" + expected
                    + ", switch=" + bySwitch
                    + ", registry=" + byRegistry);
        }
        check(item.name(), true);
    }

    static void duplicateRegistration() {
        try {
            new Registry.Builder()
                    .add(Create.class,
                            CommandRegistryComparisonDemo::onCreate)
                    .add(Create.class,
                            CommandRegistryComparisonDemo::onCreate);
            throw new AssertionError(
                    "expected duplicate handler error");
        } catch (IllegalArgumentException expected) {
            check("duplicate-handler-rejected", true);
        }
    }

    static void nullContext(String label, Runnable operation) {
        try {
            operation.run();
            throw new AssertionError(
                    "expected null context error");
        } catch (NullPointerException expected) {
            check(label, true);
        }
    }

    public static void main(String[] args) {
        Context missing = new Context(State.MISSING);
        Context created = new Context(State.CREATED);
        Context paid = new Context(State.PAID);
        Context shipped = new Context(State.SHIPPED);

        Case[] cases = {
            new Case("create-ok", new Create("O1", 3), missing,
                    ok("created:O1:3")),
            new Case("create-existing", new Create("O1", 3), created,
                    rejected("order-exists")),
            new Case("create-null-id", new Create(null, 3), missing,
                    invalid("orderId")),
            new Case("create-blank-id", new Create(" ", 3), missing,
                    invalid("orderId")),
            new Case("create-zero", new Create("O1", 0), missing,
                    invalid("units")),
            new Case("create-negative", new Create("O1", -1), missing,
                    invalid("units")),
            new Case("cancel-created",
                    new Cancel("O1", "changed"), created,
                    ok("cancelled:O1")),
            new Case("cancel-paid",
                    new Cancel("O1", "changed"), paid,
                    ok("cancelled:O1")),
            new Case("cancel-missing",
                    new Cancel("O1", "changed"), missing,
                    rejected("order-not-found")),
            new Case("cancel-shipped",
                    new Cancel("O1", "changed"), shipped,
                    rejected("already-shipped")),
            new Case("cancel-null-id",
                    new Cancel(null, "changed"), created,
                    invalid("orderId")),
            new Case("cancel-blank-reason",
                    new Cancel("O1", " "), created,
                    invalid("reason")),
            new Case("ship-paid", new Ship("O1", "TR-5"), paid,
                    ok("shipped:O1:TR-5")),
            new Case("ship-created",
                    new Ship("O1", "TR-5"), created,
                    rejected("requires-paid")),
            new Case("ship-missing",
                    new Ship("O1", "TR-5"), missing,
                    rejected("requires-paid")),
            new Case("ship-shipped",
                    new Ship("O1", "TR-5"), shipped,
                    rejected("requires-paid")),
            new Case("ship-null-id",
                    new Ship(null, "TR-5"), paid,
                    invalid("orderId")),
            new Case("ship-blank-tracking",
                    new Ship("O1", " "), paid,
                    invalid("tracking")),
            new Case("ship-long-code",
                    new Ship("O2", "TRACK-123"), paid,
                    ok("shipped:O2:TRACK-123")),
            new Case("null-command",
                    null, paid, invalid("request"))
        };

        for (Case test : cases) compare(test);

        check("complete-registry-coverage", CORE.types().equals(
                java.util.Set.of(
                        Create.class, Cancel.class, Ship.class)));

        check("extension-registered", EXTENDED.dispatch(
                new Export("monthly"), missing)
                .equals(ok("export:monthly")));

        check("extension-invalid", EXTENDED.dispatch(
                new Export(" "), missing)
                .equals(invalid("report")));

        check("extension-unregistered", CORE.dispatch(
                new Export("monthly"), missing)
                .equals(unsupported("Export")));

        Registry partial = new Registry.Builder()
                .add(Create.class,
                        CommandRegistryComparisonDemo::onCreate)
                .build();

        check("missing-core-handler", partial.dispatch(
                new Ship("O1", "TR-5"), paid)
                .equals(unsupported("Ship")));

        duplicateRegistration();

        nullContext("null-context-switch",
                () -> viaSwitch(new Create("O1", 1), null));

        nullContext("null-context-registry",
                () -> CORE.dispatch(new Create("O1", 1), null));

        System.out.println("ALL PASSED: " + passed);
    }
}
~~~

### Compile and run commands

Use JDK 21 or later:

~~~bash
javac --release 21 CommandRegistryComparisonDemo.java
java CommandRegistryComparisonDemo
~~~

**Exact output:**

~~~text
PASS create-ok
PASS create-existing
PASS create-null-id
PASS create-blank-id
PASS create-zero
PASS create-negative
PASS cancel-created
PASS cancel-paid
PASS cancel-missing
PASS cancel-shipped
PASS cancel-null-id
PASS cancel-blank-reason
PASS ship-paid
PASS ship-created
PASS ship-missing
PASS ship-shipped
PASS ship-null-id
PASS ship-blank-tracking
PASS ship-long-code
PASS null-command
PASS complete-registry-coverage
PASS extension-registered
PASS extension-invalid
PASS extension-unregistered
PASS missing-core-handler
PASS duplicate-handler-rejected
PASS null-context-switch
PASS null-context-registry
ALL PASSED: 28
~~~

### What does this result prove?

**The first 20 cases** test both `viaSwitch` and `CORE.dispatch` on a list of core commands and compare both outcomes against the expected `Outcome`. Because the `Outcome` record implements component-wise `equals`, the comparison checks both the outcome code and detail, not just the class name.

**The last 8 cases** test conditions that typical dispatch examples easily overlook:

1. `complete-registry-coverage`: manually checks that `CORE` has registered the exact three currently known core classes.
2. `extension-registered`: the extended registry accepts the registered `Export`.
3. `extension-invalid`: the extension must still validate its own data.
4. `extension-unregistered`: the core registry returns `UNSUPPORTED` for an unregistered `Export`.
5. `missing-core-handler`: a registry missing the `Ship` handler still builds; it only returns `UNSUPPORTED` at runtime.
6. `duplicate-handler-rejected`: the builder rejects two handlers for the same `Create.class` key.
7. `null-context-switch`: the `switch`-based dispatcher rejects a null context.
8. `null-context-registry`: the registry also rejects a null context, preserving the same contract.

**Important:** the manual coverage check is a test based on the current `Create/Cancel/Ship` list. It **does not provide compiler exhaustiveness guarantees** if `Refund` is added later and you forget to update the test list as well. A registry still requires its own registration discipline and runtime checks.

The program only **computes and returns simulated outcomes**; it does not write to a database, send shipping requests, or perform real exports. Thus, this is an example for testing dispatch and validation, not a complete order-system implementation.

## 9. The real difference when adding a new command

### 9.1. Adding a core command

Suppose we add `Refund` as a subtype of `CoreCommand`:

~~~java
// Illustrative, do not add to the main file without updating permits.
record Refund(String id, long cents) implements CoreCommand {}
~~~

To stay consistent with the `sealed` model, `CoreCommand`'s `permits` clause must be updated. Then:

- **Pattern `switch`:** `viaSwitch` can report a **non-exhaustive** error upon recompilation because it lacks a `Refund` branch.
- **Registry:** the old core registry can still be built without a `Refund` handler; when receiving that command, it returns `UNSUPPORTED`. The missing registration is only caught by startup validation, tests, or at runtime.
- **Business logic:** both approaches must define a handler and tests for the refund logic; dispatch does not generate business rules on its own.

A small **negative compile test** to observe the compiler:

~~~java
// Illustrative file that intentionally does not compile:
public class MissingCommandCase {
    sealed interface C permits A, B {}
    record A() implements C {}
    record B() implements C {}

    static int route(C cmd) {
        return switch (cmd) {
            case null -> 0;
            case A a -> 1;
        };
    }
}
~~~

Running `javac --release 21 MissingCommandCase.java` will be rejected because the `switch expression` **does not cover `B`**. This file is a **negative compile test** and must not be merged into the runnable program in section 8.

### 9.2. Adding an extension action

An extension like `Export` only implements `Action`. It does not alter `CoreCommand.permits`, so `viaSwitch(CoreCommand, ...)` remains exhaustive for the current core set.

For the registry to recognize the extension, you need to build an instance that registers it:

~~~java
Registry extended = coreBuilder()
        .add(Export.class, CommandRegistryComparisonDemo::onExport)
        .build();
~~~

**A registry does not auto-discover handlers** just because an implementation exists. `Export` only works if it is registered in the builder or via a plugin discovery/DI mechanism that the application actually provides.

In production systems, plugin loading may use `ServiceLoader`, dependency injection, or module configuration. In that case, you must clearly define lifecycle, access permissions, duplicate registration handling, initialization errors, load order, safety, and version contracts. You should not treat a simple registry map as proof that a system safely supports plugins.

## 10. Architecture comparison table

| Criterion | Pattern `switch` over `sealed` | Registry handler |
| --- | --- | --- |
| Ideal command set | Closed, known at compile time | Open or configurable |
| Dispatch | `case` branches on command type | Handler lookup by runtime key |
| Checking for missing handlers | Compiler checks exhaustiveness | Startup validation, tests, or runtime |
| Type-safety mechanism | Pattern variables have static types | Generic registration + `Class.cast` |
| Handler configuration | Lives in the `switch` code | Centralized or assembled from modules |
| Adding a core subtype | Must update `permits` and related `switch`es | Must register handler; if missing, may only fail at runtime |
| Adding external plugins | `sealed` intentionally restricts this | Can support when interfaces and lifecycle allow |
| Framework dependency | Not required | Not required, though DI/discovery can help |
| Debugging | Inspect the matching case and guard | Inspect registered entries, class key, handler, and logic |
| Null handling | Needs `case null` or early rejection | Needs `action == null` branch or rejection contract |
| Initial complexity | Low for a few commands | Higher due to builder/map/registration |
| Testability | Test each handler and `switch` branch | Test handlers, coverage, duplicates, missing, lookup |
| Performance | Depends on JVM/JIT and workload | Depends on map lookup, cast, handler dispatch, JVM/JIT |
| Observability | Can attach metrics in dispatcher/handler | Can attach metrics around each entry/handler |

A registry can integrate with the **Command Pattern** (each command is an object representing a request and a handler executes it), but design patterns have no exclusivity rules: a centralized `switch` or polymorphic method can also execute commands cleanly.

## 11. Easy-to-miss details with registries

### 11.1. Exact class lookup, not automatic superclass traversal

The example code uses:

~~~java
handlers.get(action.getClass())
~~~

It looks up an entry by the **exact runtime class** of the object, without automatically walking superclasses or interfaces to find the "closest matching" handler.

This fits the final records in the case study. However, if commands have an open hierarchy, framework-generated proxies, or subtypes of a command class, exact-class lookup may fail to find a handler registered for a parent class.

You can design **assignable matching** or register a shared interface, but when multiple handlers match, you must define **precedence/specificity rules**, and lookup complexity can increase. Do not silently switch `get(action.getClass())` to scanning `isAssignableFrom` without ambiguity-resolution rules.

### 11.2. Generic registration does not eliminate all mistakes

`Builder.add(Create.class, Handler<Create>)` enforces the type relationship for each entry. Still, a runtime registry needs checks for:

- Is there a handler for every expected command?
- Are there duplicate registrations?
- Do handlers return outcomes conforming to the contract?
- Is any code using raw types or unchecked casts that break type safety?
- Do different classloaders produce nominally identical classes with different identities?

`Class.cast` is a useful runtime check, not a replacement for integration tests.

### 11.3. Difference between mutable builder and immutable registry

`Builder` uses a `HashMap` during the **assembly phase** and should not be shared arbitrarily across threads. After `build()`, `Registry` uses `Map.copyOf` and exposes no API to mutate registrations.

If plugin hot reload is needed, consider building a new registry and **atomically swapping the reference** at the application boundary, rather than mutating a map that active threads are reading. Even then, hot reload is a separate requirement that demands managing shutdown, consistency, and handler lifecycle.

### 11.4. A registered handler does not guarantee business success

The registry may find a handler and the handler can still return `INVALID` or `REJECTED`. Conversely, a missing handler yields `UNSUPPORTED`. Separating these outcome kinds keeps logs, metrics, and API responses from making operators confuse "no handling code exists" with "the user sent invalid fields".

## 12. Common pitfalls when using Pattern Matching for commands

**Pitfall 1 — using `default` and losing exhaustiveness.** If `CoreCommand` is sealed, a missing new case should be flagged by the compiler; a broad `default` can hide forgetting to handle `Refund`.

**Pitfall 2 — misunderstanding `null`.** In a Java 21 pattern `switch`, a null selector does not fall into `default`. Define `case null` or check `requireNonNull` per your contract.

**Pitfall 3 — putting validation in one set of `switch` cases while the registry calls different logic.** That causes the two strategies to diverge in behavior and makes comparison invalid. Sharing business services/handlers lets you refactor dispatch without changing rules.

**Pitfall 4 — assuming a `record` is always valid.** `Create(null, -1)` is still a type-valid record if there is no constructor validation. Pattern matching checks types, not whether an order ID is non-blank or quantity is positive.

**Pitfall 5 — using a giant `switch` to do all the work.** When each command has dozens of steps and dependencies, move the business logic into clearly named handlers/services. Let `switch` only perform dispatch.

**Pitfall 6 — expecting a registry to auto-discover every new class.** Having an `Action` implementation does not create a registration. It must be registered via code, DI, or controlled plugin discovery.

**Pitfall 7 — using `Map<Class<?>, Object>` with unchecked casts everywhere.** Prone to runtime failures and hard to review. Pair `Class<C>` + `Handler<C>` inside a typed registration to confine the cast point.

**Pitfall 8 — silently overwriting an existing handler.** `map.put(...)` can replace a handler without the operator noticing. For a single-handler-per-type registry, use `putIfAbsent` and fail fast on duplicates.

**Pitfall 9 — treating manual test coverage as equivalent to compiler exhaustiveness.** `Set.of(Create.class, Cancel.class, Ship.class)` is only accurate if maintainers remember to update the list; a compiler `switch` relies directly on the sealed type's subtype set.

**Pitfall 10 — assuming an immutable registry map makes every handler thread-safe.** A handler with mutable state can still suffer from race conditions. The registry and the handler are two separate levels of responsibility.

**Pitfall 11 — assuming `Class` lookup matches subclasses/proxies.** `map.get(actualClass)` only matches the exact key; you must explicitly support inheritance if your application requires it.

**Pitfall 12 — drawing performance conclusions without measuring.** `switch` can be well optimized by the JIT; a registry has lookup/cast overhead, but real impact depends on workload. To draw conclusions, run a controlled benchmark and measure the actual hot path.

## 13. Choosing a strategy by context

### Prefer `switch` with pattern matching when

- The number of commands is moderate, the variant set is **closed**, and it is controlled by a single development team.
- Adding a new command should force maintainers to review every dispatch point.
- Business logic for each type is extracted into short methods, and `switch` only maps cases.
- You want **compiler exhaustiveness**, readable code, and minimal runtime configuration.

### Consider a registry handler when

- Commands are provided by multiple modules or plugins, or handlers must be selected by configuration.
- Each handler has different dependencies/lifecycles managed by a DI container.
- You want to add/remove handlers at the assembly layer without editing a central `switch` for an open interface.
- You accept and thoroughly control missing-handler, duplicate-handler, and misconfiguration errors.

### Combine both when

- There is a **stable protocol core** and a closed `CoreCommand` set that needs exhaustiveness guarantees.
- Beyond the core, additional actions are needed and registered in a shared registry.
- You need a clear boundary: which types belong to the core and which can be contributed by plugin developers.

**Do not introduce a registry** just because "we might add a command later". A plugin mechanism carries design, maintenance, and safety costs. Conversely, if dozens of independent modules genuinely contribute handlers, a central `switch` that must be edited on every integration can become an organizational bottleneck.

## 14. Migration strategy from legacy code

If you currently have code like:

~~~java
// Illustrative legacy style, requires the corresponding types.
if (raw instanceof Create) {
    Create c = (Create) raw;
    return onCreate(c, context);
}
if (raw instanceof Cancel) {
    Cancel c = (Cancel) raw;
    return onCancel(c, context);
}
if (raw instanceof Ship) {
    Ship c = (Ship) raw;
    return onShip(c, context);
}
~~~

You can migrate step by step:

1. **Lock down input and null contracts:** does data come from a public API or already-parsed commands? Is null a validation error or a programming error?
2. **Separate business logic from dispatch:** extract each case into methods like `onCreate`, `onCancel`, `onShip`. Write tests on outcomes.
3. **If the core set is closed:** declare `sealed CoreCommand` and migrate the dispatcher to a `switch expression`, without adding a `default` that hides missing subtypes.
4. **If true extensions exist:** define an open `Action` interface and a typed handler registration mechanism; define the `UNSUPPORTED` policy.
5. **Validate at startup:** check for duplicates, missing handlers (if the required handler list is known), dependencies, and configuration.
6. **Keep comparison tests:** run the same command set through old/new dispatchers and compare results. For handlers with side effects, use fake dependencies or transaction/test isolation so operations are not executed twice against real data.
7. **Only measure performance when needed:** if dispatch is a hot spot, use JMH or profile the real path rather than guessing from line counts.

You can keep `switch` as a routing "adapter" while using handler classes to execute business logic. The two techniques are **not mutually exclusive**.

## 15. Review checklist and exercises

### Checklist

1. Is the dispatcher input a closed `CoreCommand` or an open `Action`? Does that decision match the extension strategy?
2. Is the `switch` exhaustive when a new subtype is added to `permits`?
3. Do null selectors and null `Context` have clear contracts?
4. Do handlers validate data before checking state conditions?
5. Do both dispatch approaches share business logic and return the same `Outcome`?
6. Does the registry register typed handlers and avoid raw/unchecked casts?
7. Are duplicate registrations rejected immediately when building the registry?
8. Are missing handlers tested, and is `UNSUPPORTED` handled when lookup fails?
9. Is exact runtime class lookup compatible with proxies/subclasses/modules?
10. Is the registry immutable after initialization, and are individual handlers thread-safe if needed?
11. Are extensions explicitly registered, with controlled dependencies and access permissions?
12. Are there tests for null, blank strings, boundary values, invalid states, and adding a new command?
13. Is `default` avoided so it does not hide missing subtypes in the closed core set?
14. Are expected business errors separated from bugs or infrastructure failures?
15. Are extensibility and API compatibility consequences documented when adding subtypes?

### Exercises

- **Exercise 1:** Add `Refund(String id, long cents)` to `CoreCommand`. Observe the compiler reporting a missing branch in `viaSwitch`, then add `onRefund` and the registry registration. Write a test comparing both dispatchers.
- **Exercise 2:** Create a registry missing `Cancel.class` and run a `Cancel` command. Write startup validation to catch the error before accepting requests.
- **Exercise 3:** Try registering two different handlers for the same `Create.class`. Explain why failing fast in the builder is better than silently overwriting.
- **Exercise 4:** Add `ExportJson(String report)` implementing only `Action`, register it in `EXTENDED` without modifying `CoreCommand`. Test the extension path and missing data.
- **Exercise 5:** Change `Registry.dispatch` to allow superclass/interface lookup, then register two matching handlers. Define precedence rules and test the ambiguous case.
- **Exercise 6:** Write a test suite for a side-effecting handler using a fake repository, verifying the handler is not executed twice when comparing the two strategies.
- **Exercise 7:** Use JMH to measure dispatch cost over a mixed command set, ensuring handler logic stays identical and without fabricating numbers from a single run.
- **Exercise 8:** Try adding `case Create(var id, var units) when units > 0` without an unguarded `Create` branch. Explain why a guard does not automatically guarantee exhaustiveness for the entire subtype.

**Takeaway:** **Pattern `switch` + `sealed CoreCommand`** optimizes for a closed command set, readability, and compile-time exhaustiveness checking. **Registry handlers** fit when you need typed handler assembly and runtime extensibility, at the cost of managing duplicate registrations, missing handlers, lookup semantics, and lifecycle. The right way to compare them is to keep **the same business logic and the same outcomes**, test error cases as well, and choose the dispatch mechanism that fits your architectural boundaries—rather than chasing a design pattern by name.
