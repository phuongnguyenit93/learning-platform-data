# `permits` Defines the Subtype Set in a Sealed Hierarchy (Java 21)

In Java, the **`sealed`** keyword is used to control **which classes or interfaces are allowed to directly extend/implement a type**. The list after **`permits`** is the core of that contract. It does not list every object that may appear at runtime, but only lists **the permitted direct subclasses or direct subinterfaces**.

For example:

```java
sealed interface Message permits TextMessage, ErrorMessage {}

record TextMessage(String text) implements Message {}

record ErrorMessage(int code) implements Message {}
```

The two records `TextMessage` and `ErrorMessage` are permitted to **directly implement** `Message`; an arbitrary third class cannot write `implements Message` unless it has been added to `permits`. Because records are implicitly `final`, they also cannot have subclasses.

This control helps design closed data models, allowing the compiler to prove **exhaustive pattern `switch`** statements/expressions over the known subtypes. However, three concepts must be understood accurately:

- **Permitted direct subtypes:** determined by `permits` or the default inference rule.
- **Indirect subtypes:** depends on whether each branch below is `final`, `sealed`, or `non-sealed`.
- **Runtime instance set:** may differ from the assumptions of a previously compiled program when modules/JARs are upgraded out of sync.

This article uses Java 21 syntax; sealed classes/interfaces were standardized in Java 17 (JEP 409) and can be combined with Java 21's pattern matching for `switch` (JEP 441).

## 1. What Exact Question Does `permits` Answer?

For a **sealed class**:

```java
sealed class Document permits PdfDocument, TextDocument {}

final class PdfDocument extends Document {}

final class TextDocument extends Document {}
```

The compiler allows `PdfDocument` and `TextDocument` to directly `extends Document`. Another class is not permitted to directly extend `Document` merely because it is in the same package or has a similar name.

For a **sealed interface**:

```java
sealed interface Command permits Create, Delete {}

record Create(String id) implements Command {}

record Delete(String id) implements Command {}
```

Here, `permits` controls the **types that directly implement/extend the interface** `Command`, not the `id` values inside the records.

Core rules:

1. The sealed type declares `sealed`.
2. Each name in `permits` must denote an actual **direct subtype** of the corresponding sealed type.
3. For a direct subtype declaration to be valid, it must be in the permitted set, have a valid modifier declaration, and reside in a permitted module/package location.
4. Each direct subtype further decides how far subtypes beneath it are allowed, via `final`, `sealed`, or `non-sealed` (with the exception of implicitly `final` types such as records).
5. Only branches that the compiler can prove are covered make a pattern switch exhaustive without `default`.

**Common point of confusion:** `permits` is not a list of classes that "can be instantiated" from the sealed class. For example, a permitted subtype can be an `abstract sealed class` or a `sealed interface`, which itself cannot be instantiated directly but is still a valid branch in the hierarchy.

## 2. Distinguishing Direct Subtypes and Indirect Subtypes

Consider the hierarchy:

```text
Shape (sealed interface)
├── Circle (record; implicitly final)
└── Polygon (non-sealed class)
    ├── Triangle (class)
    └── Rectangle (class)
```

The `Shape` declaration only needs `permits Circle, Polygon`:

```java
sealed interface Shape permits Circle, Polygon {}

record Circle(double radius) implements Shape {}

non-sealed class Polygon implements Shape {}

final class Triangle extends Polygon {}

final class Rectangle extends Polygon {}
```

`Triangle` and `Rectangle` **do not need to be named in `Shape permits ...`**, because they do **not directly** implement `Shape`: they extend `Polygon`, and are thus indirectly `Shape`.

This **does not break the sealed rules**. `Shape` still controls all **direct entry points**: to become a `Shape`, a new type must enter through a permitted branch. If that branch is `non-sealed`, the hierarchy author has **intentionally opened up** inheritance below that branch.

Therefore, saying "`Shape` only has two subtypes" is inaccurate in this example. More accurately: **`Shape` has two direct permitted subtypes**, but there can be additional indirect subtypes of `Polygon`.

When doing pattern matching:

```java
static String kind(Shape shape) {
    return switch (shape) {
        case Circle circle -> "circle";
        case Polygon polygon -> "polygon family";
    };
}
```

`case Polygon polygon` catches `Polygon`, `Triangle`, and `Rectangle`. The two cases are sufficient to cover every **non-null** `Shape`, and the switch expression is exhaustive according to the declared hierarchy. If you only had `case Circle` and `case Triangle`, the compiler could not consider every `Polygon` covered.

The code snippets in this section are illustrative examples; a standalone runnable program is presented in Section 10.

## 3. Three Choices for a Permitted Subtype: `final`, `sealed`, `non-sealed`

A permitted direct subclass/subinterface must express how it continues to control inheritance.

### `final`: prevent further inheritance

```java
sealed interface Status permits Success, Failure {}

record Success(String value) implements Status {}

final class Failure implements Status {}
```

`Success` is a record so it is **implicitly final**; `Failure` explicitly declares `final`. No class can extend them. This is how to create a closed set of variants at the leaf level.

### `sealed`: continue restricting each sub-branch

```java
sealed interface Action permits ReadAction, WriteAction {}

final class ReadAction implements Action {}

sealed interface WriteAction extends Action
        permits InsertAction, RemoveAction {}

final class InsertAction implements WriteAction {}

final class RemoveAction implements WriteAction {}
```

`Action` only directly permits `ReadAction` and `WriteAction`. `WriteAction` in turn separately permits `InsertAction` and `RemoveAction`. A **multi-level hierarchy remains controlled**, as long as the branches continue to be `sealed`/`final`.

Do not put `InsertAction` in `Action permits` because `InsertAction` **directly extends/implements `WriteAction`**, not `Action`.

### `non-sealed`: open a branch for normal extension

```java
sealed interface PaymentMethod permits CardPayment, AlternativePayment {}

record CardPayment(String token) implements PaymentMethod {}

non-sealed class AlternativePayment implements PaymentMethod {}

final class BankTransfer extends AlternativePayment {}
```

`AlternativePayment` is a direct permitted subtype, but it allows subclasses to extend it like a regular class. `BankTransfer` does not need to be added to `PaymentMethod permits`.

**Syntax note:** `non-sealed` is not a modifier that can be arbitrarily attached to any class; in this context, it must be a direct subtype of a sealed type. An interface cannot be `final`, but it can continue to be `sealed` or choose `non-sealed` where valid.

| Choice | Can it have subtypes below it? | Consequence for the model |
| --- | --- | --- |
| `final` | No | The branch ends there |
| `sealed ... permits ...` | Only the branch's permitted direct subtypes | Continues controlling the hierarchy |
| `non-sealed` | Yes, following normal inheritance rules | Allows future extension without modifying `permits` on the ancestor |
| `record` | No, because it is implicitly `final` | Suitable for closed data variants |

Branches within the same sealed hierarchy are **not required** to choose the same modifier. This is a design tool: a closed core can coexist with a controlled "extension point".

## 4. When Can `permits` Be Omitted?

Java has a rule to **infer the list of permitted subtypes** if a sealed class/interface **omits `permits`**, provided that the direct subtypes are declared in the **same compilation unit**.

For example, all three types reside in **one file** `Signal.java`:

```java
sealed interface Signal {}

record Ping() implements Signal {}

record Pong() implements Signal {}
```

The compiler can infer the two permitted direct subtypes `Ping` and `Pong`; not simply because they are in the same package in general, but because the direct subtype declarations appear **in the same compilation unit** as `Signal`.

If `Signal`, `Ping`, and `Pong` are split into **separate files**, declare `permits` explicitly:

```java
sealed interface Signal permits Ping, Pong {}
```

Then place the types in a valid package/module. Compiler inference of `permits` does not make Java "automatically discover all implementations at runtime": the list is still determined **at compile time**.

You can choose to write `permits` explicitly even in the same file if you want the public contract to be easier to read. For large modules with subtypes spread across multiple source files, the explicit form is usually appropriate.

## 5. Module and Package Restrictions of `permits`

Not every class named in the list is allowed to become a direct subtype; **the location of the declarations also matters**:

- If the sealed type is in a **named module**, the permitted direct subtypes must be in the **same named module**. They may belong to different packages within that module.
- If the sealed type is in the **unnamed module** (e.g., a simple application running on the classpath), the permitted direct subtypes must be in the **same package** as the sealed type.
- If a class/interface is listed in `permits` but **does not directly extend/implement** the sealed type, the compiler rejects it.
- If a new class directly extends the sealed type without **being permitted**, the compiler rejects it.

`permits` is therefore not a "documentation-only list of names": the compiler and JVM enforce the constraints of the sealed hierarchy. One cannot "extend from any library" by declaring `implements` if the author of the sealed type did not grant the corresponding permission.

For example, a type in the `core` module cannot arbitrarily `permits` a direct implementation in another module just to create a cross-module plugin. If a plugin hook is needed, consider **a permitted `non-sealed` extension type** or a separate non-sealed SPI interface with clear contract boundaries.

The runnable examples in Section 10 use nested types inside a single class and do not declare a module, so no `module-info.java` configuration is required.

## 6. Common Mistakes When Writing `permits`

### Mistake 1: Forgetting a direct subtype name

```java
// INTENTIONALLY INVALID:
sealed interface Result permits Ok {}

record Ok() implements Result {}

record Error() implements Result {} // Not in Result permits.
```

`Error` directly implements `Result` but is not permitted. The compiler rejects it. Fix: add `Error` to `Result permits`, or redesign the inheritance relationship if `Error` should not be a direct subtype.

### Mistake 2: Listing an indirect subtype as a direct subtype

```java
// INTENTIONALLY INVALID:
sealed interface Base permits Middle, Leaf {}

non-sealed class Middle implements Base {}

final class Leaf extends Middle {} // Leaf does not directly implement Base.
```

Here `Leaf` is an **indirect** subtype through `Middle`, so it cannot be listed as a direct permitted subtype of `Base`. The fix is to only `permits Middle` and let the `Middle` branch govern extension below it.

### Mistake 3: Direct subtype missing a valid modifier

```java
// INTENTIONALLY INVALID:
sealed interface Outcome permits Accepted {}

class Accepted implements Outcome {} // Needs final, sealed, or non-sealed.
```

For a regular class `Accepted`, choose `final class Accepted`, `sealed class Accepted ...`, or `non-sealed class Accepted` depending on your extension intent. A **record implementing a sealed interface** is convenient because it is implicitly `final`, so there is no need to repeat `final`.

### Mistake 4: Arbitrarily implementing a sealed type in another module/package

Adding a class that directly implements a sealed type in another library without being listed in `permits`, or placing a permitted direct subtype in the wrong module/package, will be rejected. Do not work around this with an unchecked cast: this is a **class hierarchy** constraint, not a data casting issue.

### Mistake 5: Confusing `permits` with record component values

```java
sealed interface Report permits SuccessReport, FailureReport {}

record SuccessReport(String id) implements Report {}

record FailureReport(String message) implements Report {}
```

The `permits` list does not restrict the values of `id` or `message`. It only restricts the **type variants**. Components can still carry any data conforming to their declared types; to enforce valid data, you must use validation, constructors, or other business rules.

Do not put these **intentionally invalid** snippets into the runnable demo file in Section 10.

## 7. How `permits` Helps Pattern `switch` Be Exhaustive

A clear benefit in Java 21 is that the compiler can prove a `switch` on a sealed type covers **every permitted branch**.

```java
sealed interface Event permits Started, Finished {}

record Started(String name) implements Event {}

record Finished(String name) implements Event {}

static String describe(Event event) {
    return switch (event) {
        case Started started -> "started:" + started.name();
        case Finished finished -> "finished:" + finished.name();
    };
}
```

These are illustrative declarations that need to be placed in the same class or organized into valid compilation units. With selector `Event`, the two cases cover every possible **non-null** object of type `Event` in this closed hierarchy, so the `switch expression` **does not need `default`**.

Conversely, if only this remains:

```java
// DOES NOT COMPILE: non-exhaustive switch expression.
return switch (event) {
    case Started started -> "started:" + started.name();
};
```

Then `Finished` is unhandled, and the compiler rejects it.

In Java 21, an **enhanced switch statement** with patterns is also required to be exhaustive. Therefore, not only expressions but also statements like the following must cover all branches:

```java
static void printEvent(Event event) {
    switch (event) {
        case Started started ->
                System.out.println(started.name());
        case Finished finished ->
                System.out.println(finished.name());
    }
}
```

These examples are **illustrative snippets**, not standalone programs.

This provides an important guarantee: when designing a closed hierarchy, the compiler can immediately detect missing business branches instead of allowing `switch` to silently ignore a new variant.

## 8. `non-sealed` Does Not Break Exhaustiveness If a Case Covers the Open Branch

Consider:

```java
sealed interface Notification permits Email, External {}

record Email(String subject) implements Notification {}

non-sealed class External implements Notification {}
```

We can write:

```java
static String category(Notification item) {
    return switch (item) {
        case Email email -> "email";
        case External external -> "external";
    };
}
```

`case External external` covers **every instance of `External` and its subclasses**, including subclasses created later. Thus, the compiler can still recognize the switch as exhaustive when all direct permitted branches are covered.

However, having only `case Email` and some specific subclasses of `External` **is not necessarily sufficient**: because `External` is `non-sealed`, there may be other subclasses or an instance of `External` itself if the class is not abstract.

**Code review rule:** for a `non-sealed` branch, if the business logic wants to handle all current/future variants uniformly, match on the **type of the open branch**. If you want to classify deeper into specific subclasses, add an explicit fallback strategy rather than assuming the subset is closed.

## 9. Nested Sealed Hierarchies: Covering by Intermediate Branches or by Leaves

Given the diagram:

```text
Operation (sealed)
├── Query (final)
└── Change (sealed)
    ├── Insert (final)
    └── Remove (final)
```

We have two valid strategies.

**Matching by direct branch**:

```java
return switch (operation) {
    case Query query -> "query";
    case Change change -> "change";
};
```

`case Change change` covers all subtypes of `Change`, including `Insert` and `Remove`.

**Matching by specific leaves**:

```java
return switch (operation) {
    case Query query -> "query";
    case Insert insert -> "insert";
    case Remove remove -> "remove";
};
```

The compiler can prove exhaustiveness based on the fact that `Change` is also sealed and only has two leaf subtypes. The second approach is suitable when each variant needs its own business logic.

Note: case ordering is subject to **dominance**. If you place `case Change change` before `case Insert insert` in the same switch, the `Insert` branch will be shadowed because every `Insert` is also a `Change`, and the compiler will report a dominated case error.

An unguarded `case Operation op`, or `default`, can also make the switch exhaustive, but loses much of the subtype-checking value of the hierarchy.

## 10. Complete Program Runnable with JDK 21

Create the file **`PermitsHierarchyDemo.java`**:

```java
public class PermitsHierarchyDemo {
    sealed interface Message permits Joined, Left, Extension {}

    record Joined(String user) implements Message {}

    record Left(String user, int code) implements Message {}

    static non-sealed class Extension implements Message {
        private final String label;

        Extension(String label) {
            this.label = label;
        }

        String label() {
            return label;
        }
    }

    static final class PriorityExtension extends Extension {
        PriorityExtension(String label) {
            super(label);
        }
    }

    static String describe(Message message) {
        return switch (message) {
            case null -> "missing";
            case Joined joined -> "joined:" + joined.user();
            case Left left -> "left:" + left.user() + ":" + left.code();
            case Extension extension ->
                    "extension:" + extension.label();
        };
    }

    static void printKind(Message message) {
        switch (message) {
            case null -> System.out.println("kind:missing");
            case Joined joined -> System.out.println("kind:joined");
            case Left left -> System.out.println("kind:left");
            case Extension extension -> System.out.println("kind:extension");
        }
    }

    public static void main(String[] args) {
        System.out.println(describe(new Joined("Mai")));
        System.out.println(describe(new Left("Mai", 2)));
        System.out.println(describe(new Extension("basic")));
        System.out.println(describe(new PriorityExtension("priority")));
        System.out.println(describe(null));
        printKind(new PriorityExtension("priority"));
    }
}
```

Compile and run with **JDK 21**:

```bash
javac --release 21 PermitsHierarchyDemo.java
java PermitsHierarchyDemo
```

**Exact stdout:**

```text
joined:Mai
left:Mai:2
extension:basic
extension:priority
missing
kind:extension
```

Analysis:

1. `Message` is a sealed interface that only directly permits `Joined`, `Left`, and `Extension`.
2. `Joined` and `Left` are records, implicitly `final`, which closes these two branches.
3. `Extension` is declared `non-sealed` and allows `PriorityExtension extends Extension`. `PriorityExtension` does **not** need to be named in `Message permits`.
4. In both `describe` (switch expression) and `printKind` (enhanced switch statement), `case Extension extension` matches both `Extension` and `PriorityExtension`.
5. `case null` handles a `null` selector explicitly; without a null case, a pattern switch on a null reference typically throws `NullPointerException`. **Exhaustiveness over non-null subtypes does not automatically handle null.**
6. Neither switch has a `default`, yet both are exhaustive because every direct permitted branch is covered and there is a dedicated branch for null.

No `--enable-preview` is needed: both sealed hierarchies and pattern matching for switch used here are standardized in Java 21.

## 11. How Does `permits` Differ from a Non-Sealed Interface?

With a regular interface:

```java
interface OpenMessage {}

final class Alpha implements OpenMessage {}

final class Beta implements OpenMessage {}
```

Another module can still write `class Gamma implements OpenMessage` (if normal access rules allow). The compiler does not have a published finite list to assert that the `Alpha` and `Beta` cases are sufficient for every `OpenMessage`.

In contrast, when using:

```java
sealed interface ClosedMessage permits Alpha, Beta {}
```

With `Alpha` and `Beta` redeclared to implement `ClosedMessage` and satisfy `final`/appropriate modifiers, a new direct subtype cannot spontaneously appear in another module or while the compiler has not been updated with the new hierarchy.

That is the value of sealed types in **sum type / algebraic data type modeling**: a sum type consisting of permitted variants where the compiler knows the relationship among them to support exhaustiveness checking in pattern matching.

However, a sealed type is not a validation system for all data: for example, `Joined(String user)` can still receive `null` for its component if you do not add validation. `permits` controls **who can be a subtype**, not **property values**.

## 12. When the Hierarchy Changes: Benefits and Risks of Exhaustive Switch

Suppose initially:

```java
sealed interface Event permits Start, Stop {}

record Start() implements Event {}

record Stop() implements Event {}
```

A `switch` on `Event` with the two cases `Start` and `Stop` can be exhaustive without needing `default`.

Later, a developer adds `Pause`:

```java
sealed interface Event permits Start, Stop, Pause {}

record Start() implements Event {}

record Stop() implements Event {}

record Pause() implements Event {}
```

If you **recompile** the switch against the new hierarchy while it still only has cases `Start`/`Stop`, the compiler can report that it is non-exhaustive. This is the **intended effect**: forcing maintainers to consider how to handle `Pause`.

If you **only swap in the new library at runtime** while the client containing the switch still has old bytecode compiled against the v1 hierarchy, upon encountering `Pause`, Java 21 may throw **`MatchException`** because the old exhaustiveness assumption no longer holds. This is a *separate compilation* and out-of-sync deployment issue, not a bug in `permits` in the new source.

A `default` branch can provide a fallback for new subtypes, but it also means the compiler **no longer forces** you to add a dedicated case when the hierarchy expands. Considerations:

- **Every variant has distinct business logic:** prefer omitting `default` on a closed hierarchy so the compiler checks all cases on rebuild.
- **New variants may be handled generically:** you can use `default` or an explicit general type pattern, with logging/metrics where appropriate.
- **Multi-module deployments:** lock dependency versions consistently; rebuild and test modules containing pattern switches when changing the subtype list.

Do not confuse this situation with `NullPointerException` caused by a `null` selector: that is a separate null-handling path, not a missing permitted subtype.

## 13. Common Misconceptions

**"`permits A, B` means there are only two subtypes in the entire program."** Not necessarily. `A` or `B` can be `non-sealed` and have indirect subclasses/implementations. The list only restricts **direct subtypes**.

**"Every class that wants to create an instance of a sealed interface must appear in `permits`."** False. A class extending a permitted `non-sealed` branch can be a valid indirect subtype without being named in the ancestor's `permits`.

**"`permits` can list a class that does not directly extend the sealed type to allow it indirectly."** False. A name in `permits` must represent a direct subtype relationship with the corresponding sealed type.

**"Once it is a permitted direct subtype, it needs no modifier."** False for regular classes: it needs `final`, `sealed`, or `non-sealed`. Records are a convenient exception because they are implicitly `final`.

**"If `permits` is omitted, the sealed type automatically discovers all subtypes on the classpath at runtime."** False. The compiler only infers the direct list from the **same compilation unit** when omitting the clause is allowed; it does not scan the classpath or runtime.

**"A switch with all `permits` branches also handles null."** False. Type patterns do not match null; you can add `case null` if the selector is nullable.

**"Adding `default` is always safer."** Not necessarily. It provides a fallback, but it can also hide the need to handle a new subtype as the system evolves.

## 14. Design and Review Checklist

1. **Define the closed scope:** which type is the `sealed` root; which types are actually allowed to **directly** implement/extend it?
2. **Inspect every direct subtype:** does it declare `final`, `sealed`, `non-sealed`, or is it an implicitly `final` record?
3. **Verify direct relationships:** does each subtype listed in `permits` directly extend/implement the root type, or is it only an indirect descendant?
4. **Verify locations:** named module in the same module; unnamed module in the same package; only omit `permits` if the same-compilation-unit rule is satisfied.
5. **Evaluate open branches:** is `non-sealed` used, and does calling code mistakenly rely on the descendant set being closed?
6. **Write pattern switches:** are all permitted branches or all leaf branches in a multi-level sealed hierarchy covered?
7. **Check dominance:** does a supertype branch appear before a subtype branch, making the later case unreachable?
8. **Check null handling:** is `case null` or input validation needed? `default` does not implicitly catch null in a pattern switch.
9. **Evaluate API evolution:** does adding a direct permitted subtype require rebuilding modules containing old switches? Are there tests for the new variant?
10. **Decide on `default` based on business needs:** do you want the compiler to enforce handling new types, or an explicit fallback for forward compatibility?

**Conclusion:** `permits` is the **contract defining the permitted direct subtypes** of a sealed class/interface, not a list of all descendants or all runtime objects. Combining `final`, `sealed`, and `non-sealed` lets you design where the hierarchy is closed and where it is open. In Java 21, understanding this hierarchy tree is the key to writing pattern `switch` constructs that are **exhaustive, maintainable, and safer as the system evolves**.

### Official References

- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Java Language Specification 21 — §8.1.6, Permitted Direct Subclasses](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.1.6)
- [Java Language Specification 21 — §9.1.4, Sealed Interfaces](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.1.4)
- [Oracle Java 21 — Sealed Classes and Interfaces](https://docs.oracle.com/en/java/javase/21/language/sealed-classes-and-interfaces.html)
