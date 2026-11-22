# Using Exhaustive Switch for a Command Handler

**Topic:** Java Core Pattern Matching — Command Case Study. This article uses **Java 21 or later**, where **pattern matching for switch** (JEP 441) and **record patterns** (JEP 440) are standard features. The focus is on building a **command handler that covers every command variant** using a sealed hierarchy and a switch expression, ensuring new commands are never silently ignored.

## 1. The Problem: Which Commands Must a Handler Know How to Process?

In an application, a **command** expresses a *request to perform an action*, such as opening an item, renaming it, or closing it. It represents an intent that must be validated and can be rejected; this differs from an **event**, which describes something that has already happened.

Suppose an application maintains a list of items managed by an identifier. There are three commands:

- **Open(id, title):** create a new item with an id and a title.
- **Rename(id, title):** rename an existing item.
- **Close(id):** close or remove an item from memory.

A handler must select the right branch by subtype, enforce business rules, and return a clear result. When the command domain is controlled, we also want the compiler to remind us of every place that needs updating if a fourth command—such as **Archive(id)**—is added later.

A legacy conditional chain often looks like this:

~~~java
// Illustration in a context that has the Command, Open, Rename, and Close types.
if (command instanceof Open open) {
    return open(open.id(), open.title());
} else if (command instanceof Rename rename) {
    return rename(rename.id(), rename.title());
} else if (command instanceof Close close) {
    return close(close.id());
}
return new Rejected("unsupported");
~~~

This code works for the current three commands, but it **does not require checking every subtype**. When `Archive` is added, an older handler can still compile and return `unsupported`, even when the business logic requires handling `Archive` explicitly.

**The goal of an exhaustive switch is not merely to replace `if-else` with `switch`.** The goal is to let the compiler verify that the handler makes a **decision for every variant** permitted by the command type, while preserving intentional null behavior, validation, and side effects.

## 2. Designing a Closed Command Domain with a Sealed Interface

Start with the model:

~~~java
sealed interface Command permits Open, Rename, Close {}

record Open(long id, String title) implements Command {}
record Rename(long id, String title) implements Command {}
record Close(long id) implements Command {}
~~~

This is an **illustrative declaration snippet**; the complete runnable code in Section 5 adds invariant checks in the constructors.

The **sealed interface** specifies which types are permitted to directly implement `Command`. All three records are implicitly **final**, so each branch has no further subtype hierarchy underneath it. The compiler has enough information to analyze the set of variants when given a selector whose static type is **Command**.

Useful characteristics:

1. Command creators must choose a specific type, rather than passing a `String` with an arbitrary command name.
2. Each record's components have explicit names and types; `Open` has `id` and `title`, while `Close` only needs `id`.
3. A **record pattern** in a `switch` both selects the variant and extracts that variant's data.
4. When a new subtype is added to the `permits` list and recompiled, any `switch` expression that does not cover the new subtype produces a compile error instead of silently falling through to a fallback branch.
5. The command data types are independent of HTTP, CLI, or message queue code: outer layers can convert incoming requests into a `Command` before calling the handler.

**Important limitation:** `sealed` only restricts direct subtypes. A permitted branch can declare itself **non-sealed**, allowing unknown descendants below it. In the model here using `final` records, each branch is a closed command type; there are no new descendants under `Open`/`Rename`/`Close`.

## 3. Protecting Command Data at Record Creation Time

A command with a non-positive `id` or a whitespace-only `title` is not meaningful in this example. This can be checked in a **compact constructor**, so the handler does not have to repeat the same validation in every `case`:

~~~java
record Open(long id, String title) implements Command {
    Open {
        requireId(id);
        requireTitle(title);
    }
}
~~~

The two helpers **requireId** and **requireTitle** will be defined in the complete class in Section 5. They enforce:

- **id > 0**;
- **title != null** and **!title.isBlank()**.

Records use `final` components, but they **do not validate invariants automatically**. A compact constructor is the right choice to guarantee that a valid `Open` cannot be constructed with a negative `id` or a blank `title`. Similarly, `Rename` requires a valid `id` and `title`; `Close` only requires a valid `id`.

**Distinguishing two kinds of errors:**

| Situation | When does it occur? | How it is handled in the example |
| --- | --- | --- |
| **new Open(0, "Bad")** | Before a valid `Command` object exists | Constructor throws `IllegalArgumentException` |
| **new Rename(25, "   ")** | Before calling the handler | Constructor throws `IllegalArgumentException` |
| **Open(10, "Duplicate")** when id 10 already exists | During command business-logic processing | Handler returns `Rejected("already exists 10")` |
| **Close(99)** when id 99 does not exist | During command business-logic processing | Handler returns `Rejected("not found 99")` |
| **handle(null)** | At the handler boundary | Handler returns `Rejected("null command")` |

Placing validation in the constructor is appropriate when an invariant holds for **every instance** of the command. If external input has not been parsed yet or has missing fields, a separate request/DTO class can be used to report errors before constructing the domain command.

## 4. Don't Make the Caller Guess Success or Failure

Instead of having the handler return an ambiguous `String` or `null`, model the result as two variants:

~~~java
sealed interface Result permits Applied, Rejected {}

record Applied(String detail) implements Result {}
record Rejected(String reason) implements Result {}
~~~

- **Applied:** the command was accepted and executed in the example.
- **Rejected:** the command could not be completed due to a defined condition.

Consumers can render the result using a second exhaustive switch expression:

~~~java
static String render(Result result) {
    return switch (result) {
        case Applied(String detail) -> "OK: " + detail;
        case Rejected(String reason) -> "ERR: " + reason;
    };
}
~~~

Here **Result** is a `sealed interface` and both `Applied` and `Rejected` are `final` records. No **default** is needed; if a new result type such as `Pending` is added later, the compiler will remind you to update `render` upon recompilation.

**These are two separate responsibilities:** the handler turns a `Command` into a `Result`; the formatter turns a `Result` into display text. In a production system, `String detail`/`reason` can be replaced with error codes, IDs, result payloads, or an API-specific structure. You should not rely on parsing the `"ERR:"` prefix to determine business outcomes.

If **render(null)** is called, the `switch` has no `case null` and may throw a `NullPointerException`; this design assumes a `Result` returned by the handler is **never null**. If another API allows a `null` result, it needs its own explicit contract.

## 5. Complete Java 21 Example: Exhaustive Handler

The program uses a **TreeMap** as an in-memory store to illustrate state transitions. There is no database, transaction, or concurrency handling. This keeps the branching mechanism clear without introducing infrastructure complexity into the example.

Save everything to **ExhaustiveCommandHandlerDemo.java**:

~~~java
import java.util.Map;
import java.util.TreeMap;

public class ExhaustiveCommandHandlerDemo {
    sealed interface Command permits Open, Rename, Close {}

    record Open(long id, String title) implements Command {
        Open {
            requireId(id);
            requireTitle(title);
        }
    }

    record Rename(long id, String title) implements Command {
        Rename {
            requireId(id);
            requireTitle(title);
        }
    }

    record Close(long id) implements Command {
        Close {
            requireId(id);
        }
    }

    sealed interface Result permits Applied, Rejected {}
    record Applied(String detail) implements Result {}
    record Rejected(String reason) implements Result {}

    private static void requireId(long id) {
        if (id <= 0) throw new IllegalArgumentException("id");
    }

    private static void requireTitle(String title) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("title");
        }
    }

    private final Map<Long, String> titles = new TreeMap<>();

    Result handle(Command command) {
        return switch (command) {
            case Open(long id, String title) -> open(id, title);
            case Rename(long id, String title) -> rename(id, title);
            case Close(long id) -> close(id);
            case null -> new Rejected("null command");
        };
    }

    private Result open(long id, String title) {
        if (titles.putIfAbsent(id, title) != null) {
            return new Rejected("already exists " + id);
        }
        return new Applied("opened " + id + " " + title);
    }

    private Result rename(long id, String title) {
        if (!titles.containsKey(id)) {
            return new Rejected("not found " + id);
        }
        titles.put(id, title);
        return new Applied("renamed " + id + " " + title);
    }

    private Result close(long id) {
        if (titles.remove(id) == null) {
            return new Rejected("not found " + id);
        }
        return new Applied("closed " + id);
    }

    static String render(Result result) {
        return switch (result) {
            case Applied(String detail) -> "OK: " + detail;
            case Rejected(String reason) -> "ERR: " + reason;
        };
    }

    public static void main(String[] args) {
        var handler = new ExhaustiveCommandHandlerDemo();

        Command[] commands = {
            new Open(10, "Atlas"),
            new Rename(10, "Orion"),
            new Open(10, "Duplicate"),
            new Close(99),
            new Close(10),
            new Rename(10, "Nova"),
            new Open(20, "Solar"),
            new Rename(20, "Lunar"),
            null
        };

        for (Command command : commands) {
            System.out.println(render(handler.handle(command)));
        }

        try {
            new Open(0, "Invalid");
        } catch (IllegalArgumentException ex) {
            System.out.println("INVALID: " + ex.getMessage());
        }

        try {
            new Rename(25, "   ");
        } catch (IllegalArgumentException ex) {
            System.out.println("INVALID: " + ex.getMessage());
        }

        System.out.println("STATE: " + handler.titles);
    }
}
~~~

### Compiling and Running

Use JDK 21 or newer:

~~~bash
javac ExhaustiveCommandHandlerDemo.java
java ExhaustiveCommandHandlerDemo
~~~

**Exact output:**

~~~text
OK: opened 10 Atlas
OK: renamed 10 Orion
ERR: already exists 10
ERR: not found 99
OK: closed 10
ERR: not found 10
OK: opened 20 Solar
OK: renamed 20 Lunar
ERR: null command
INVALID: id
INVALID: title
STATE: {20=Lunar}
~~~

### Reading Each Group of Results

1. **Open(10, "Atlas")** succeeds and creates item 10.
2. **Rename(10, "Orion")** renames item 10 to `Orion`.
3. **Open(10, "Duplicate")** is rejected because id 10 already exists; the `Map` keeps its existing value.
4. **Close(99)** does not find the item and returns `Rejected`.
5. **Close(10)** removes item 10 and succeeds.
6. **Rename(10, "Nova")** is rejected because the item has already been closed.
7. **Open(20, "Solar")** followed by **Rename(20, "Lunar")** creates and renames item 20.
8. **null command** is handled by `case null` and becomes a `Rejected` `Result` rather than an implicit `NullPointerException`.
9. The two invalid command constructions throw exceptions from their constructors, which `main` catches and prints as **INVALID: id/title**.
10. The `Map` retains only **20=Lunar**, so **STATE: {20=Lunar}**.

**This output is a behavioral check, not a benchmark.** The lines are produced from a deterministic input sequence; because `TreeMap` is used, keys are ordered, and only one key remains in the example. In a real system, you need to test concurrency, transactions, and consistency at the storage layer.

## 6. Why Is the Switch Handler Considered Exhaustive?

The core part is:

~~~java
Result handle(Command command) {
    return switch (command) {
        case Open(long id, String title) -> open(id, title);
        case Rename(long id, String title) -> rename(id, title);
        case Close(long id) -> close(id);
        case null -> new Rejected("null command");
    };
}
~~~

Breaking it down factor by factor:

- The **selector** has static type `Command`.
- The **permits** clause of `Command` lists exactly `Open`, `Rename`, and `Close`.
- All three direct subtypes are `final` records, with no open branches beneath them.
- Each **record pattern** matches every instance of the corresponding record; its `long`/`String` components are bound unconditionally by the pattern, with no guard restricting values.
- **case null** defines behavior when the selector itself has no command; it does not replace a subtype case.
- There is no **default**, so the compiler can detect when a new subtype is added without updating the handler.

A `switch` expression must be **exhaustive**. In the example, whenever the selector holds a non-null `Command` value, it must be one of the three permitted variants. The record patterns cover those three variants, and `case null` adds a contract for a `null` selector. Each branch returns a `Result`, so the entire expression has type `Result`.

**Exhaustive does not mean the command always succeeds.** A case can return **Rejected** or throw an exception. Exhaustiveness only guarantees that a matching branch exists for every type and pattern; business correctness still depends on `open`/`rename`/`close` and tests.

## 7. What Does the Compiler Protect When You Add a New Subtype?

Suppose the system later adds an `Archive` command. The model changes as follows:

~~~java
// Illustration of the extended version; do not merge verbatim into the demo file.
sealed interface Command permits Open, Rename, Close, Archive {}

record Archive(long id) implements Command {}
~~~

When recompiling the old handler, the compiler sees **Archive** as a permitted variant with no matching `case`. A `switch` expression without `default` like the one above will report an error such as:

~~~text
the switch expression does not cover all possible input values
~~~

To fix it properly, do not rush to add `default`. Decide what `Archive` means and update the handler:

~~~java
// Illustration snippet requiring an archive(id) method in the extended handler.
case Archive(long id) -> archive(id);
~~~

Then add tests for `Archive`, including non-existent ids, states that cannot be archived, and related side effects. You may also need to update parsers/mappers, authorization, logging, API contracts, or emitted events; the `switch` only flags part of the places that need attention.

**Compile-time protection is conditional:** It works when recompiling against the new hierarchy definition. If previously built binaries are deployed out of sync with a newer library, a `switch` that was exhaustive at compile time can encounter an unmatched runtime type and throw **MatchException**. Therefore, dependent modules must be built, tested, and deployed compatibly.

### Why Not Use `default` to Avoid the Error?

~~~java
// Anti-pattern if the business logic requires the handler to consider every command.
return switch (command) {
    case Open(var id, var title) -> open(id, title);
    case Rename(var id, var title) -> rename(id, title);
    case Close(var id) -> close(id);
    case null -> new Rejected("null command");
    default -> new Rejected("unsupported");
};
~~~

When `Archive` appears, it can silently fall into `unsupported` without forcing the developer to design its specific handling. That is not always wrong: with a genuinely **open** selector type and a contract that allows rejecting any unsupported kind, a fallback is necessary. But with a **sealed command model that has a controlled set of commands**, omitting `default` helps catch omissions much earlier.

If you still want to reject invalid external commands, reject them at the **parsing/validation boundary**, rather than turning every new domain subtype into `"unsupported"` by default.

## 8. `when` Guards Can Make a Handler Non-Exhaustive

Suppose `Rename` is only allowed when the `title` satisfies a certain condition:

~~~java
// This is a negative example: only a subset of Rename is handled.
return switch (command) {
    case Open(var id, var title) -> open(id, title);
    case Rename(long id, String title) when title.startsWith("A") ->
            rename(id, title);
    case Close(var id) -> close(id);
    case null -> new Rejected("null command");
};
~~~

For a `Rename` whose `title` does not start with `"A"`, the guard evaluates to `false`; there is no other branch for the `Rename` subtype, so the compiler rejects the `switch` expression as **not exhaustive**. Add an unguarded branch specifically for the remaining cases:

~~~java
case Rename(var id, var title) ->
        new Rejected("rename policy not satisfied");
~~~

The guarded `Rename` branch must appear **before** the general `Rename` branch. Putting the broader branch first would shadow (**dominate**) the later branch and cause a compiler error.

**Limit of exhaustiveness:** The compiler does not infer arbitrary business conditions such as `x > 0` and `x <= 0` to prove coverage. A guard is a runtime check; when a guard is `false`, the `switch` tries subsequent matching cases; when a guard throws an exception, it is not treated as `false`.

For complex conditions, you can keep the `switch` purely for dispatch and perform the checks inside the corresponding handler method. For example, **case Rename(var id, var title) -> rename(id, title)** is both readable and keeps long business rules out of `case` labels.

## 9. Null Command vs. Null Component: Do Not Confuse the Two

In the demo, **case null** handles the case where the entire command is `null`:

~~~java
case null -> new Rejected("null command");
~~~

However, it **does not handle a null `title`** inside an `Open` or `Rename` object. That is handled by the compact constructor:

~~~java
record Rename(long id, String title) implements Command {
    Rename {
        requireId(id);
        requireTitle(title);
    }
}
~~~

Therefore:

- **handler.handle(null)** returns `Rejected` according to the contract.
- **new Rename(1, null)** throws `IllegalArgumentException("title")` **before** the handler is called.
- **new Rename(1, " ")** is also rejected by the constructor.
- **new Close(1)** has no `title` component, so no `title` check is needed.

If a system chooses a command model that allows `null` components, a record pattern can still match the record and bind a `null` `title` variable in an unguarded branch. In that case, you must check `title` in the body or in a validation layer, and never assume **case Rename(var id, var title)** guarantees a non-null `title`.

Another API option is calling **Objects.requireNonNull(command, "command")** before the `switch`, causing a `null` selector to throw `NullPointerException`. This makes sense if `null` is a programming error. However, that is a **different contract** from the demo returning `Rejected`; changing the policy requires updating Javadoc and tests.

**Do not treat a null command as a valid command by default:** returning `Rejected` here is simply to illustrate a structured error-handling API.

## 10. Side Effects in the Handler: Switch Does Not Replace Transactions

The demo uses a `Map` to simulate state changes. Picking the right `case` is only the first step of handling a real command.

### 10.1. Separating Dispatch from Business Logic

A handler `case` is usually clearer when it simply calls a named method:

~~~java
case Open(long id, String title) -> open(id, title);
case Rename(long id, String title) -> rename(id, title);
case Close(long id) -> close(id);
~~~

Helper methods can use repositories, check permissions, validate state, and return a `Result`. This avoids stuffing dozens of lines of I/O and validation into a `switch`, while keeping the **subtype dispatch** easy to review.

### 10.2. The Demo's State Is Not Thread-Safe

**TreeMap** is not designed for unsynchronized concurrent mutation by multiple threads. The check-then-update sequence in `rename` is not atomic either. If multiple commands are processed concurrently, you need an appropriate concurrency control mechanism: locks, transactions, optimistic locking, or a data store with atomic conditional operations.

Do not simply replace `TreeMap` with `ConcurrentHashMap` and assume the entire **containsKey → put** sequence is atomic; the atomicity of a complete business operation must be designed explicitly.

### 10.3. Duplicate Commands and Idempotency

A message queue may redeliver a command; an API may be retried by a client after a timeout. If a handler performs side effects like sending an email or charging a payment and then times out, a retry can duplicate the side effect. Depending on the domain, you may need an **idempotency key**, transaction/outbox patterns, processing state tracking, or deduplication.

In the demo, an `Open` with a duplicate `id` is `Rejected`, but that is **not** a complete idempotency guarantee for every business workflow. Duplicate commands must be designed around system requirements; a retry's result may need to match the original result rather than returning a new error.

### 10.4. Intentional Error Boundaries

A command can be rejected due to input data or business state; it can also fail due to database, network, or application bugs. Never catch every `Exception` and return `Applied` or swallow the failure:

~~~java
// Anti-pattern: turning an execution failure into a false success.
try {
    performOperation();
    return new Applied("done");
} catch (Exception ex) {
    return new Applied("done");
}
~~~

If you need to model infrastructure failures with a dedicated `Result` type, clearly define the categories and where retries occur. A more complex system might use **Applied**, **Rejected**, and **Failed** (or a hierarchy of errors) with an exhaustive `switch` at the consumer.

## 11. When to Use a Switch Expression, Switch Statement, or Polymorphism?

### Switch Expression

Best suited when the handler **selects a single result** based on the command subtype and all branches share a unified return type:

~~~java
return switch (command) {
    case Open(var id, var title) -> open(id, title);
    case Rename(var id, var title) -> rename(id, title);
    case Close(var id) -> close(id);
    case null -> new Rejected("null command");
};
~~~

All cases produce a `Result`; if a case needs multiple statements, you can use a block and **yield**:

~~~java
// Illustration: assumes audit(...) and open(...) are defined by the application.
case Open(var id, var title) -> {
    audit("open", id);
    yield open(id, title);
}
~~~

A branch may throw an exception instead of `yield`. However, avoid packing multiple side-effecting operations into a `switch` expression if you need to manage transactions or rollbacks; extract a dedicated method instead.

### Switch Statement

A `switch` statement is usually appropriate when you primarily **execute actions** and do not need to produce a value directly. With **pattern switch** in Java 21, `switch` statements are also subject to the corresponding exhaustiveness rules when using patterns/null/etc. in certain forms—do not confuse them with traditional constant-label `switch` statements, which can omit `default`.

### Polymorphism

If each command has stable, self-contained behavior and the operation naturally belongs inside the subtype itself, a polymorphic design can work well:

~~~java
// Sketch of an alternative design approach; do not merge into the demo.
interface ExecutableCommand {
    Result execute(Context context);
}
~~~

However, if you want to keep DTO/command records independent of databases, services, and infrastructure, an **external handler using an exhaustive switch** is often cleaner. Some systems use a class-to-handler registry/map, but that approach does not provide static exhaustiveness guarantees like a `switch` over a sealed hierarchy and requires its own registration checks.

| Criterion | Sealed + exhaustive switch | Polymorphism / registry |
| --- | --- | --- |
| Closed and controlled command domain | Very well suited | Usable |
| Compiler reminder when adding a subtype | Clear advantage | Requires interface contract or registration checks |
| Multiple consumers reading the same command | Can write separate switches per responsibility | Depends on handler organization |
| Plugins adding commands dynamically at runtime | Limited by the sealed domain | Registry or extension mechanism may fit better |
| Each command tightly coupled to one domain behavior | Can lead to a long switch | Polymorphism can be clearer |
| Separating command data from services/infrastructure | Convenient | Requires careful interface/dependency design |

There is no single right solution for every application. Prioritize a clear dispatch boundary, practical extensibility, and testable error handling.

## 12. Testing the Handler: Do Not Only Verify That Code Compiles

The compiler catches **missing branches**, but it does not prove that the business logic in each branch is correct. A test matrix for the demo:

| Command / situation | Expected | What is verified |
| --- | --- | --- |
| New `Open` | `Applied`; item created | Correct subtype selection and state creation |
| `Rename` existing item | `Applied`; `title` updated | Correct `id`, no duplicate record created |
| `Open` existing `id` | `Rejected`; old value preserved | No unintended data overwrite |
| `Close` non-existent `id` | `Rejected` | No false success |
| `Close` existing `id` | `Applied`; item removed | Correct side effect |
| `Rename` after `Close` | `Rejected` | State validated before update |
| `handle(null)` | `Rejected("null command")` | Null selector contract |
| `Open` invalid `id` | `IllegalArgumentException` from constructor | Invariant before dispatch |
| `Rename` blank/null `title` | `IllegalArgumentException` from constructor | Null/blank component |
| Add new subtype to `permits` | Exhaustiveness error in switch missing a case | Compile-time regression |
| Command with `false` guard | Must have a matching case for the remainder | No missed pattern |

### Simple Framework-Free Tests

Place the following illustrative statements within the scope of the demo class (or a test with appropriate access):

~~~java
var handler = new ExhaustiveCommandHandlerDemo();

Result first = handler.handle(new Open(1, "A"));
if (!(first instanceof Applied)) {
    throw new AssertionError("Open should succeed");
}

Result duplicate = handler.handle(new Open(1, "B"));
if (!(duplicate instanceof Rejected)) {
    throw new AssertionError("Duplicate id should fail");
}

Result missing = handler.handle(null);
if (!(missing instanceof Rejected)) {
    throw new AssertionError("Null command contract");
}
~~~

This is an **additional test snippet**, not a standalone Java program outside the class. With JUnit, you can use **assertInstanceOf**, **assertEquals**, **assertThrows**, and assert state after each command. In larger projects, tests should also verify transaction boundaries, authorization, and side effects such as events or notifications.

### Compile-Time Testing When Adding a Subtype

A useful review technique is to add a new subtype on a development branch, update the **permits** list, and recompile all related modules. Wherever a handler lacks a corresponding `case` and has no broad `default`, the compiler will pinpoint where updates are needed. Then add the proper business-logic `case` and regression tests, rather than just inserting `default` to make the build pass.

Note that the compiler inspects the **static type**. If you widen the parameter to `Object` or an unsealed open interface, you cannot expect the compiler to know all command types in the application from the class name alone.

## 13. Common Mistakes When Building a Command Handler

**Mistake 1 — Always using `default -> unsupported`.** With a sealed hierarchy that has a closed set of subtypes, this stops the compiler from reminding you when a new command is added. If the goal is to review every command, omit `default` and list all cases explicitly.

**Mistake 2 — Having only a guarded `case` for a subtype.** A guard can evaluate to `false`, leaving the `switch` expression missing a branch. Add an unguarded `case` for the same subtype or move the validation into the handler method.

**Mistake 3 — Placing `case Command c` before `case Open`.** A general type pattern can shadow specific patterns and cause a dominance error. Put specific cases first when a broad fallback is truly needed.

**Mistake 4 — Treating exhaustiveness as validation.** A `switch` can cover every case while a command still carries an invalid `id`, insufficient permissions, or an invalid state for the operation. Business correctness requires invariants and tests.

**Mistake 5 — Forgetting a `null` selector.** An `instanceof` chain with `null` usually falls into `else`, whereas pattern `switch` has its own `null` rules. Choose `case null` or reject with `Objects.requireNonNull` according to your contract.

**Mistake 6 — Ignoring `null` components.** A record pattern does not automatically guarantee a `String` component is non-null if the constructor allows it. Do not call methods on pattern variables without invariants or explicit checks.

**Mistake 7 — Confusing commands with events.** A command can be rejected and may produce side effects; an event is a fact that has already occurred. Never treat receiving a command as a guarantee that an event has been emitted.

**Mistake 8 — Putting all I/O, transactions, retries, and logging inside `case` blocks.** Dispatch becomes hard to review, errors become hard to test, and side effects become hard to manage. Use separate methods or services.

**Mistake 9 — Seeing `Map` in the example and assuming thread safety.** `TreeMap` must not be used concurrently without synchronization; multi-step read-then-write sequences are not atomic.

**Mistake 10 — Relying solely on the compiler to validate domain changes.** It detects missing subtypes in recompiled switches, not whether internal operations, permissions, or JSON responses are correct.

## 14. Design and Code Review Checklist

- [ ] Is the command hierarchy genuinely closed and appropriate to declare as **sealed**?
- [ ] Is each command represented by a type with clear components?
- [ ] Are common command invariants checked when the object is constructed?
- [ ] Does the handler have a selector with static type **Command**, rather than being widened to `Object` unintentionally?
- [ ] Are the cases for **Open, Rename, Close** all present and free of dominance errors?
- [ ] Does the `switch` expression **omit `default`** when you want the compiler to flag new subtypes?
- [ ] If **when** is used, is there a fallback `case` for when the guard is `false`?
- [ ] Are `null` commands and `null` components governed by explicit rules?
- [ ] Does the handler return an appropriate `Result`, without mixing business rejections and infrastructure exceptions?
- [ ] Are there tests for before/after state, duplicate commands, non-existent ids, and invalid command data?
- [ ] Are side effects, concurrent updates, retries, and idempotency addressed at the appropriate layer?
- [ ] When a new command is added, are all switches and consumers recompiled and retested?

**Conclusion:** **Using an exhaustive switch for a handler** combines the strengths of **sealed interfaces**, **record patterns**, and **switch expressions** to express the supported set of commands clearly. The compiler helps detect **missing handling when new subtypes appear**; dedicated methods keep business logic clean; an explicit `Result` helps callers distinguish between acceptance and rejection. Still, exhaustiveness does not replace validation, transactions, or testing: a reliable handler needs both **compile-time coverage** and **correct runtime behavior**.