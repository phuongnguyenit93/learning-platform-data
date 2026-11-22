# Comparing Sealed Hierarchies with Openly Extensible Classes in Java

## 1. The Design Problem: Who Is Allowed to Create New Subtypes?

When designing an object-oriented Java library or application, we often have to choose between two policies:

- **Open hierarchy** (*open hierarchy*): other classes can extend/implement a type and provide a new implementation, as long as they follow standard Java rules.
- **Controlled closed hierarchy** (*sealed hierarchy*): the author of a class/interface specifies **which direct subtypes are permitted**. Child branches can be further closed, end with `final`, or be intentionally reopened with `non-sealed`.

For example, a result-returning protocol with only two variants:

```java
sealed interface Result permits Success, Failure {}

record Success(String value) implements Result {}

record Failure(String message) implements Result {}
```

This is a valid Java 17 declaration snippet if the three types are in the same compilation unit; there is no `main` yet. Because `Result` is `sealed`, any external class **is not allowed to arbitrarily** add a third direct implementation.

Conversely:

```java
interface Result {}

record Success(String value) implements Result {}

record Failure(String message) implements Result {}
```

In this version, `Result` is a regular interface: other classes can write `implements Result` if the type is accessible and regular Java constraints allow it.

**The central question is not “which syntax is shorter”, but rather:** Is the set of implementations a **closed part controlled by the type owner**, or an **extension point** for modules, plugins, and library users?

This article compares Java 17+ behavior, extensibility permission models, compiler errors, API design, software upgradability, and approaches for combining both directions. Complete programs include files, `javac`/`java` commands, and deterministic outputs; invalid snippets are labeled to illustrate errors.

## 2. What Does an Open Hierarchy Look Like?

Consider a regular abstract class:

```java
abstract class Message {
    abstract String text();
}
```

A subclass elsewhere can define:

```java
final class Greeting extends Message {
    @Override
    String text() {
        return "hello";
    }
}
```

These are two illustrative declarations that can belong to a valid program. `Message` is neither `sealed` nor `final`, so Java has no **closed `permits` list** applied to direct subclasses.

It is necessary to distinguish:

- **Open for inheritance:** The type does not prohibit subclasses under sealed/final rules.
- **Accessible from where inheritance is desired:** Access modifiers, package, module exports, and constructor visibility still matter.
- **Having a useful extension point:** To be subclassed in practice, the superclass must have an appropriate contract, methods, and constructor.
- **Not inherently safe:** Third parties may implement it differently than expected; API authors need to write the contract properly and avoid assuming a finite list.

An abstract class **does not automatically close** the set of subclasses. It merely cannot be instantiated directly, and it can force subclasses to implement abstract methods.

## 3. Runnable Program: An Open Hierarchy Allows Adding Behavior

Create the file **`OpenHierarchyDemo.java`**:

```java
abstract class Notification {
    abstract String send(String target);
}

final class EmailNotification extends Notification {
    @Override
    String send(String target) {
        return "email:" + target;
    }
}

final class SmsNotification extends Notification {
    @Override
    String send(String target) {
        return "sms:" + target;
    }
}

public class OpenHierarchyDemo {
    static void deliver(Notification notification) {
        System.out.println(notification.send("An"));
    }

    public static void main(String[] args) {
        deliver(new EmailNotification());
        deliver(new SmsNotification());
    }
}
```

```bash
javac OpenHierarchyDemo.java
java OpenHierarchyDemo
```

```text
email:An
sms:An
```

The `deliver` method only knows the abstract superclass `Notification`. When adding a new implementation following normal rules, callers can still pass an instance to `deliver` if the subclass satisfies the contract.

**Benefit:** Polymorphism creates a clear extension point, especially when an ecosystem has multiple implementations developed by different organizations.

**Cost:** The designer of `Notification` is not allowed to assume that only EmailNotification and SmsNotification exist. If a method in the library uses `if (notification instanceof EmailNotification) ... else ...`, future subclasses risk not being handled.

## 4. How Does a Closed Hierarchy Using `sealed` Work?

With Java 17:

```java
sealed abstract class Notification
        permits EmailNotification, SmsNotification {
    abstract String send(String target);
}

final class EmailNotification extends Notification {
    @Override
    String send(String target) {
        return "email:" + target;
    }
}

final class SmsNotification extends Notification {
    @Override
    String send(String target) {
        return "sms:" + target;
    }
}
```

This is an independent illustrative declaration, **not placed simultaneously with the open `Notification` example** in the same scope.

In the sealed version:

1. `Notification` remains an abstract class, not instantiated directly.
2. It only allows **permitted direct subclasses**.
3. `EmailNotification` and `SmsNotification` are `final`, so they cannot be subclassed further.
4. A direct subclass `PushNotification extends Notification` will be rejected by the compiler if it is not permitted.
5. Polymorphic calls through `Notification` still work normally: `sealed` does not disable dynamic dispatch.

**Closed does not mean “not using inheritance”.** Sealed controls **which direct inheritance branches** are permitted.

## 5. Runnable Program: sealed and Dynamic Dispatch Still Coexist

Create **`SealedHierarchyDemo.java`**:

```java
sealed abstract class Notification
        permits EmailNotification, SmsNotification {
    abstract String send(String target);
}

final class EmailNotification extends Notification {
    @Override
    String send(String target) {
        return "email:" + target;
    }
}

final class SmsNotification extends Notification {
    @Override
    String send(String target) {
        return "sms:" + target;
    }
}

public class SealedHierarchyDemo {
    static void deliver(Notification notification) {
        System.out.println(notification.send("An"));
    }

    public static void main(String[] args) {
        deliver(new EmailNotification());
        deliver(new SmsNotification());
        System.out.println(Notification.class.isSealed());
    }
}
```

```bash
javac SealedHierarchyDemo.java
java SealedHierarchyDemo
```

```text
email:An
sms:An
true
```

Compared to the open version, **the code using polymorphism in `deliver` does not change**. The only difference is that the compiler/runtime constrains the direct subclass set.

**Design consequence:** You can choose sealed while still benefiting from OOP abstraction, overriding, method dispatch, and constructor chaining. Sealed does not turn the entire class hierarchy into a `switch` or an enumeration.

## 6. Three Keywords to Place Side by Side: `final`, `sealed`, `non-sealed`

| Modifier | Allows new direct subclasses? | Design meaning |
| --- | --- | --- |
| `final class` | No | Blocks inheritance completely at that node |
| `sealed class/interface` | Only permitted direct types | Allows controlled inheritance |
| `non-sealed class/interface` | Reopens under standard rules | Intentionally opens a branch beneath a sealed parent |
| Regular class/interface | Can be open, depending on access and other rules | Not locked by a permits list |
| `abstract class` | Depends on sealed/final policy; abstract alone does not lock | Not instantiated directly; can contain abstract methods |

A `non-sealed` declaration only has meaning at the position of a **direct subtype of a sealed type**; `non-sealed` cannot be placed arbitrarily on just any regular class.

**Do not confuse the two axes:** `abstract` is about instantiation and abstract methods; `sealed` is about the right to create a **direct subtype**. For example, `abstract sealed class` is valid: it both prevents direct instantiation and locks the list of subtypes.

## 7. The Permission Mechanism Only Considers Direct Branches

Suppose:

```java
sealed class Base permits Middle {}

non-sealed class Middle extends Base {}

final class Leaf extends Middle {}
```

This illustrative code is valid within the same appropriate package.

- `Middle` is a **direct subclass** permitted by Base.
- `Leaf` is an **indirect subclass** of Base.
- `Leaf` does not need to appear in `Base permits ...` because it does not directly `extends Base`.
- Because Middle is `non-sealed`, it allows subclasses like Leaf according to regular class rules.

Sealed **does not guarantee that the list of all descendants across all levels is finite** if a `non-sealed` branch exists. It only guarantees that the set of **direct permitted subtypes** is controlled for each sealed node.

## 8. Runnable Program: One sealed Branch, One non-sealed Branch

Create **`SelectiveOpenHierarchyDemo.java`**:

```java
sealed abstract class Document
        permits OfficialDocument, CustomDocument {
    abstract String label();
}

final class OfficialDocument extends Document {
    @Override
    String label() {
        return "official";
    }
}

non-sealed class CustomDocument extends Document {
    @Override
    String label() {
        return "custom";
    }
}

final class UserDocument extends CustomDocument {
    @Override
    String label() {
        return "user";
    }
}

public class SelectiveOpenHierarchyDemo {
    public static void main(String[] args) {
        Document[] documents = {
                new OfficialDocument(),
                new CustomDocument(),
                new UserDocument()
        };

        for (Document document : documents) {
            System.out.println(document.label());
        }
    }
}
```

```bash
javac SelectiveOpenHierarchyDemo.java
java SelectiveOpenHierarchyDemo
```

```text
official
custom
user
```

`Document` only permits OfficialDocument and CustomDocument directly. UserDocument is created through the `non-sealed` CustomDocument branch. This is the **closed at the core, selectively open at the extension branch** model.

**Design point:** There is no need to choose “everything closed” or “everything open”. Java allows combining the two policies at the appropriate layers.

## 9. A Table of Extensibility Permissions by Scenario

| Scenario | Open class | Sealed hierarchy |
| --- | --- | --- |
| Another developer writes a direct subclass | Possible, if Java access/rules allow | Only when the child is permitted |
| A plugin outside the library extends via inheritance | More convenient | Not at a sealed node, except for a non-sealed branch |
| Author knows all direct variants | Not guaranteed by the compiler to be the only ones | Has a controlled list |
| Adding an implementation in another module | Possible if the API/module allows | Cannot become a direct permitted child when named-module co-location forbids it |
| Dynamic polymorphism | Yes | Yes |
| Forbidding inheritance of a specific branch | Put final on the child | Put final on the permitted child |
| Allowing extension of a specific branch | Usually already open | Use a non-sealed child |
| Changing the set of direct subtypes | External consumers can add without modifying the parent | The hierarchy owner updates permits/source |
| Static reasoning about the direct hierarchy | Limited | Better when all branches are sufficiently closed |
| Risk of unexpected future subtypes | Higher | Reduced at sealed nodes |
| Compatibility when changing the parent | Must preserve the contract for external subclasses | Must still consider permitted clients and binary/serialization |

**Note:** “Open” does not mean it is easy to extend from anywhere. A private constructor or an inaccessible package-private class still restricts external code. Sealed is specifically a **type hierarchy** constraint with its own semantics.

## 10. A Sealed Interface Often Fits a Set of Data Variants

When business logic has several kinds of results with different data shapes, a sealed interface and records are a powerful representation.

Create **`ResultVariantsDemo.java`**:

```java
sealed interface Result
        permits Success, Failure, Pending {
    String describe();
}

record Success(String value) implements Result {
    @Override
    public String describe() {
        return "success:" + value;
    }
}

record Failure(int code) implements Result {
    @Override
    public String describe() {
        return "failure:" + code;
    }
}

record Pending() implements Result {
    @Override
    public String describe() {
        return "pending";
    }
}

public class ResultVariantsDemo {
    public static void main(String[] args) {
        Result[] results = {
                new Success("A"),
                new Failure(404),
                new Pending()
        };

        for (Result result : results) {
            System.out.println(result.describe());
        }
    }
}
```

```bash
javac ResultVariantsDemo.java
java ResultVariantsDemo
```

```text
success:A
failure:404
pending
```

The three record classes are final by the nature of records, so there is no further extension on each variant. `Result` describes a **set of domain possibilities** with precise names.

**When it fits:** protocol states, AST nodes, outcome types, and messages with a fixed schema per version. However, the model does not automatically forbid `null` as a reference value, does not automatically validate fields, and does not automatically generate logic to handle all variants.

## 11. An Open Interface Hierarchy Fits a True Extension Point

If the goal is to allow other developers to add new ways of processing, an interface that is **not sealed** is often appropriate.

Create **`OpenStrategyDemo.java`**:

```java
interface Compression {
    String name();
    String compress(String input);
}

final class NoCompression implements Compression {
    @Override
    public String name() {
        return "none";
    }

    @Override
    public String compress(String input) {
        return input;
    }
}

final class UppercaseDemoCompression implements Compression {
    @Override
    public String name() {
        return "uppercase";
    }

    @Override
    public String compress(String input) {
        return input.toUpperCase(java.util.Locale.ROOT);
    }
}

public class OpenStrategyDemo {
    static void run(Compression compression) {
        System.out.println(compression.name() + ":"
                + compression.compress("java"));
    }

    public static void main(String[] args) {
        run(new NoCompression());
        run(new UppercaseDemoCompression());
    }
}
```

```bash
javac OpenStrategyDemo.java
java OpenStrategyDemo
```

```text
none:java
uppercase:JAVA
```

Here, `UppercaseDemoCompression` is only an illustrative algorithm, **not real data compression**. The purpose is to show that a framework can accept implementations by interface contract; adding a new class does not require modifying a `permits` list.

In a plugin architecture, the ability to register implementations and how plugins are loaded are separate responsibilities of a registry, ServiceLoader, or dependency injection; an open interface only provides **the ability to implement the type**.

## 12. It Does Not Depend Only on `sealed`: Access Levels and Constructors Also Impose Practical Limits

A class that is not sealed yet not public may only be accessible within its package. A private constructor can also prevent callers from subclassing because they cannot invoke a valid constructor.

For example:

```java
public abstract class ServiceBase {
    protected ServiceBase() {
    }

    public abstract void run();
}
```

This is an **illustrative file `ServiceBase.java`**, without a main method. A protected constructor allows valid subclasses in another package to call `super()` under Java rules.

Conversely, if all constructors of a superclass are private and there is no appropriate Java mechanism for subclassing, inheriting from code outside the class may be impossible, even if the superclass is not sealed.

**Distinguish 3 layers of restriction:**

1. `public`/package-private/protected/private: **access control**.
2. `final`/`sealed`/`non-sealed`: **inheritance policy**.
3. Module exports/reads: **accessibility between modules**.

You should not conclude that “if a class does not specify sealed, then any plugin elsewhere can definitely inherit from it”.

## 13. Module and Package Conditions of `sealed`

Java 17 restricts the location of permitted direct subtypes:

- If the sealed type is in a **named module**, permitted direct subtypes must be in the **same named module**.
- If the sealed type is in an **unnamed module**, permitted direct subtypes must be in the **same package**.

This makes `sealed` suitable for a **closed family controlled by the same module/namespace**. It is usually **not** suitable as a direct extension point for code in a named module from another plugin vendor.

### Multi-Module Design Illustration

```text
module app.core
  app.core.model.Event
  app.core.model.Started
  app.core.model.Finished

module app.plugin
  app.plugin.CustomEvent
```

This is an **architecture diagram**, not a complete Java project. If Event is a sealed interface in `app.core`, the type `CustomEvent` in module `app.plugin` cannot become a direct permitted implementation of Event under the same-named-module rule. That does not change merely because app.plugin declares `requires app.core`.

To allow plugins to extend in another module, use an interface that is not sealed or expose a permitted `non-sealed` branch by design, along with appropriate access constraints.

## 14. When `permits` Is Omitted: The Compiler Only Infers Within the Same Compilation Unit

A sealed type does not necessarily have to list children explicitly if the direct subtypes have a **canonical name** and are declared in the **same compilation unit**.

Create **`ImplicitPermitsDemo.java`**:

```java
sealed interface Action {
    String label();
}

record Start() implements Action {
    @Override
    public String label() {
        return "start";
    }
}

record Stop() implements Action {
    @Override
    public String label() {
        return "stop";
    }
}

public class ImplicitPermitsDemo {
    public static void main(String[] args) {
        Action a = new Start();
        Action b = new Stop();

        System.out.println(a.label());
        System.out.println(b.label());
    }
}
```

```bash
javac ImplicitPermitsDemo.java
java ImplicitPermitsDemo
```

```text
start
stop
```

The compiler infers Start/Stop because they are in the same source file, have canonical names, and directly implement Action.

**What is insufficient:** Being in the same package or module but in **different source files** does not cause the compiler to automatically find children without permits. If you want to place implementations in separate files, an explicit `permits` is normally used.

## 15. A Completely Closed Sealed Hierarchy and an Open Branch

Two conceptual examples:

```java
sealed interface CompletelyClosed
        permits A, B {}

record A() implements CompletelyClosed {}

record B() implements CompletelyClosed {}
```

All children are final (records), so in terms of inheritance **there is no longer any path to create a new subtype**.

```java
sealed interface SelectivelyOpen
        permits Standard, Extension {}

record Standard() implements SelectivelyOpen {}

non-sealed interface Extension extends SelectivelyOpen {}
```

Here, `Extension` is open for other implementations to enter the hierarchy through that branch. Any new implementation that **directly extends Extension** does not need to appear in the permits of SelectivelyOpen.

**When saying “closed”, you must specify at which level:** Being closed at the **direct permitted set** is the default of sealed; being closed across **all descendants** is only true when every branch is closed down to the leaves and there is no `non-sealed` branch.

## 16. Runnable Example: An Interface Closing One Branch and Opening a Plugin Branch

Create **`HybridExtensionDemo.java`**:

```java
sealed interface Rule
        permits BuiltinRule, PluginRule {
    String apply(String value);
}

record BuiltinRule() implements Rule {
    @Override
    public String apply(String value) {
        return "builtin:" + value;
    }
}

non-sealed interface PluginRule extends Rule {
}

final class ExternalRule implements PluginRule {
    @Override
    public String apply(String value) {
        return "plugin:" + value;
    }
}

public class HybridExtensionDemo {
    public static void main(String[] args) {
        Rule a = new BuiltinRule();
        Rule b = new ExternalRule();

        System.out.println(a.apply("A"));
        System.out.println(b.apply("A"));
    }
}
```

```bash
javac HybridExtensionDemo.java
java HybridExtensionDemo
```

```text
builtin:A
plugin:A
```

`Rule` only permits BuiltinRule and PluginRule directly. `ExternalRule` implements PluginRule and does not directly implement Rule, so it does not violate the list of direct permitted types.

**This is a practical structure when wanting to distinguish** closed built-in variants from an explicit extension branch with its own interface. Using sealed is not mandatory for every plugin system; it is worth using when this intentional boundary provides modeling value.

## 17. Why Is `final` Different from `sealed`?

`final class` forbids subclasses completely:

```java
final class ImmutableToken {
}
```

`sealed class` allows **certain** direct subclasses:

```java
sealed abstract class Token
        permits IdentifierToken, NumberToken {
}

final class IdentifierToken extends Token {
}

final class NumberToken extends Token {
}
```

The two snippets are illustrative declarations.

| Question | `final` | `sealed` |
| --- | --- | --- |
| Can there be new direct subtypes? | No | Yes, if permitted |
| Can multiple variants be modeled under one parent? | Not via subclasses | Yes |
| Needs `permits`? | No | Explicit or inferred |
| Can it be declared abstract? | Cannot be both abstract and final on a class | Can be abstract sealed |
| Suitable for a standalone value object | Often suitable | Only when there is a family of variants |
| Suitable for AST/result variants | A leaf can be final | A sealed parent is often suitable |

Choose `final` when you have no intention of allowing subclasses at that node at all. Choose `sealed` when you need **a closed hierarchy with multiple variants**.

## 18. Abstract Does Not Mean Sealed

For example:

```java
abstract class OpenProcessor {
    abstract void process();
}
```

The author can force subclasses to implement `process` without limiting the number of subclasses. Meanwhile:

```java
abstract sealed class ClosedProcessor
        permits BatchProcessor, LiveProcessor {
    abstract void process();
}

final class BatchProcessor extends ClosedProcessor {
    @Override
    void process() {
    }
}

final class LiveProcessor extends ClosedProcessor {
    @Override
    void process() {
    }
}
```

also has an abstract contract but **restricts direct subtypes**.

**Clear separation of definitions:** Abstract is a policy for **objects and implementation**; sealed is a policy for **inheritance and the subtype set**. The two concepts can be combined.

## 19. If a Direct Child Misses Its Modifier, the Compiler Reports an Error

In a sealed hierarchy, a direct permitted subclass must declare an appropriate inheritance policy.

**Intentionally invalid code:**

```java
sealed class Parent {
}

class Child extends Parent {
}
```

Even though Child is in the same compilation unit and is inferred, it does not have `final`, `sealed`, or `non-sealed`. The compiler reports an error.

Fix if Child is a leaf:

```java
sealed class Parent {
}

final class Child extends Parent {
}
```

Fix if an extension branch is desired:

```java
sealed class Parent {
}

non-sealed class Child extends Parent {
}
```

The three snippets should be understood as **three separate options**, not duplicate declarations of `Parent` in a single source file. `non-sealed` is only used validly when Child directly extends a sealed superclass or implements a sealed interface according to the rules.

## 20. An Open Hierarchy Increases Extensibility, but Reduces Complete Enumerability

An open class/interface API cannot assume that all implementations are known at compile time.

For example:

```java
interface PaymentGateway {
    boolean charge(int amount);
}
```

The library may integrate another gateway in the future; callers usually must depend on the **contract `charge`**, rather than writing code based on a list of subclasses they happen to see in the repository today.

Conversely, with a sealed interface:

```java
sealed interface PaymentEvent
        permits Authorized, Declined {}

record Authorized(String id) implements PaymentEvent {}

record Declined(String reason) implements PaymentEvent {}
```

the author proactively defines **two event variants**. This is a model of data/events **known in advance per schema version**, unlike the goal of a provider-facing gateway API.

**Do not choose sealed just to “make code stricter”.** It has value when a closed set of variants is a fact of the domain or of the architectural contract.

## 21. Sealed Is Not Synonymous with a “Data-Rich Enum” in Every Situation

`enum` is also a way to describe a closed set of named constants:

```java
enum Status {
    NEW, PAID, CANCELLED
}
```

But if each variant has a **different payload shape**:

```java
sealed interface PaymentResult
        permits PaymentSuccess, PaymentFailure {}

record PaymentSuccess(String receipt)
        implements PaymentResult {}

record PaymentFailure(int code, String reason)
        implements PaymentResult {}
```

a sealed interface + records can express this better because each variant carries **different components**.

| Requirement | Enum | Sealed hierarchy |
| --- | --- | --- |
| A set of named constant instances | Very suitable | Can have too much boilerplate |
| Each variant has its own payload | Possible, but unnatural for many per-request payloads | Record/class variants are natural |
| Auto-generated data accessors per variant | No | Record variants have them |
| Closed set of type variants | Yes, as a constant set | Yes, as a direct permitted set if all branches are closed |
| Has a `non-sealed` branch | No such extension style | Yes |
| Behavior polymorphism | Possible via constant-specific bodies | Yes, via classes/records/interfaces |

**Sealed is not mandatory for every state enum.** Choose based on whether the domain needs **constant values** or **object types with their own payloads**.

## 22. An Open Interface Without Exhaustive Variant Rules

Example of an application handling events via a method contract:

```java
interface Event {
    void dispatch();
}
```

An open interface can have an unlimited number of implementations by design. Therefore, the method:

```java
void inspect(Event event) {
    if (event instanceof AuditEvent) {
        // ...
    } else if (event instanceof UserEvent) {
        // ...
    }
}
```

is an **illustrative code snippet**, where `AuditEvent` and `UserEvent` are assumed to be declared. Nothing in an open interface guarantees that only those two types exist; the else branch may miss future implementations.

**How to handle this in an open hierarchy:** Prefer calling a common virtual method or using a visitor/registry/dispatch strategy with a clear fallback. If the business code truly requires **enumerating all variants**, the domain may already be a better fit for sealed.

## 23. Java 17: Be Careful with Pattern Matching and `switch`

A sealed hierarchy helps with reasoning about finite variants. However, **exhaustive handling syntax** depends on the Java version.

In **Java 17**:

- `instanceof` with a type pattern is a stable feature.
- Pattern matching for `switch` is still a preview feature in Java 17.
- You should not include `case SomeRecord(...)` or a record pattern `switch` as normally compiling Java 17 code.
- Only Java 21+ has pattern switch and record patterns in final form; you must explicitly note the separate version if using them.

Create **`SealedInstanceofDemo.java`** running on Java 17:

```java
sealed interface Event permits Started, Finished {
}

record Started(String id) implements Event {
}

record Finished(String id) implements Event {
}

public class SealedInstanceofDemo {
    static String describe(Event event) {
        if (event instanceof Started started) {
            return "start:" + started.id();
        }
        if (event instanceof Finished finished) {
            return "finish:" + finished.id();
        }
        throw new IllegalStateException("unexpected type");
    }

    public static void main(String[] args) {
        System.out.println(describe(new Started("A")));
        System.out.println(describe(new Finished("B")));
    }
}
```

```bash
javac SealedInstanceofDemo.java
java SealedInstanceofDemo
```

```text
start:A
finish:B
```

These are `instanceof` patterns, not a pattern `switch`. Because the current direct variants are known, the fallback exception can express a violation of expectations, but **the compiler does not automatically prove this `if` chain exhaustive**. If a variant is added, the author must update it and the tests accordingly.

## 24. Benefits of Sealed When Working with Hierarchies

A sealed hierarchy closed across its branches provides:

1. **Restricted inheritance paths:** Types outside the direct permits list cannot open unexpected branches.
2. **Clear ownership:** The parent author declares which variants are permitted.
3. **Easier invariant checking:** It is possible to inspect/evaluate a known set of direct implementations.
4. **Support for exhaustiveness analysis** in appropriate language features/static analyzers, especially Java versions with a stable pattern switch.
5. **Good domain organization:** When business logic only has a few variants, the type system reflects that.
6. **Controlled branching:** Each child chooses final, sealed, or non-sealed.
7. **Easy to audit:** Adding a direct subtype requires modifying the declaration/list or the appropriate source scope.

**However, the compiler does not prove all business logic automatically:** It verifies type/subtype constraints; it does not verify that every implementation returns valid data, that every transition is valid, or that all serialized inputs are safe.

## 25. The Cost of Sealed: Changing the Variant Set Requires Coordination

Suppose a library publishes:

```java
public sealed interface Outcome
        permits Success, Failure {}
```

with valid `Success` and `Failure` classes. Later, the library wants to add `Retry`. This may entail:

- Updating `permits` (or declarations in the same compilation unit if inferred).
- Adding a direct permitted implementation that complies with the modifier rules.
- Reviewing `switch`/pattern handling in applicable consumer Java versions.
- Updating tests, serializers, schemas, and deserializers.
- Determining whether legacy clients will encounter the new subtype and how it should be handled.
- Reviewing binary/source compatibility and the deployment order of libraries.

**Avoid claiming that “adding a subtype is always binary-compatible and completely safe”.** Compatibility depends on APIs, build setup, linked artifacts, patterns, data, and contracts; specific testing per deployment is required.

Sealed turns changes to the variant list into **intentional schema changes**, which is an advantage for closed models but can be a burden for an ecosystem needing continuous extension.

## 26. The Cost of an Open Hierarchy: Long-Term Contracts Must Be Maintained for External Subclasses

An open superclass/interface often appears in extension libraries. Once published, developers can:

- Override methods validly.
- Call accessible constructors.
- Rely on protected hooks.
- Add fields and behavior.
- Subclass intermediate classes.

Therefore, changes such as **making a method final**, **closing constructors**, **changing the abstract contract**, or **turning an open class into sealed/final** can break source/binary compatibility for code that has already extended it.

**Changing an open class to sealed is not just an internal refactor** if third parties have already been allowed to subclass it. Unpermitted subclasses will no longer be valid. For a public API, a migration strategy should be used instead of suddenly locking the hierarchy.

## 27. Why Is Sealed Not Inherently Secure?

Sealed controls **type inheritance**; it does not automatically:

- Check user roles/permissions.
- Validate network input.
- Encrypt data.
- Guarantee thread safety.
- Block reflection for all data.
- Prevent buggy logic inside permitted subclasses.
- Protect services from injection/serialization issues.
- Guarantee that a list of variants corresponds to every business state.

For example, `Success(String token)` as a valid record in a sealed hierarchy can still contain `null` or leak the token via `toString()` if there is no validation/display policy.

**Do not use `sealed` as a “secure” label.** It is a tool for expressing **ownership and the closed/open status of the direct subtype set**.

## 28. Why Should `non-sealed` Be Used Intentionally?

If a sealed parent permits `CustomExtension` and CustomExtension is `non-sealed`, other classes can extend further through that branch according to standard Java rules.

This helps:

- Keep standard variants under control.
- Provide a dedicated plugin extension interface.
- Distinguish stable internal branches from branches owned by third parties.
- Avoid having to modify parent permits for every new plugin.

However, it also means that logic relying on **“knowing all instance types”** at the root will no longer be guaranteed. Consumers should handle a generic `CustomExtension` according to the interface contract, rather than assuming every descendant has a published name.

## 29. When Should You Choose Sealed? Strong Indicators

Sealed is usually appropriate when:

- The value domain has **a known set of data/behavior forms in advance**.
- The library author **owns all direct variants** and wants to block external implementers.
- You want to separate payloads using records/classes instead of enum constants that lack sufficient expressiveness.
- The set of variants needs to be thoroughly reviewed/tested.
- Changes of variants occur by **release/schema migration**, not runtime plugins.
- A **sum-type-like** design is needed using a sealed interface/abstract class and variant classes.
- The author is ready to manage API compatibility when adding/removing a direct type.

Examples: AST syntax for a compiler, parser results, event types from a bounded domain context, a fixed set of request/response variants, and workflow state types with different payloads.

**Be careful:** A set that “currently only has three implementations” does not prove it should be sealed. Ask whether the business **allows** external parties to add a fourth implementation in the future.

## 30. When Should You Choose an Open Hierarchy? Strong Indicators

An open hierarchy is usually appropriate when:

- The framework/library provides an **extension point** for other applications.
- Plugin authors can add implementations without modifying core code.
- Behavior variations are determined by configuration/modules/dependency injection.
- It is not possible to know all implementations at compile time.
- Implementations may be supplied by another library/module.
- The stable contract is based on methods/semantics, not on a list of concrete types.
- The API intentionally follows the Open/Closed Principle in the sense of being open for extension while avoiding modifying consumers.

Examples: `Comparator<T>`, `Runnable`, a `StorageProvider`, `AuthenticationStrategy`, and `MessageTransport` for plugins.

**Open does not mean everything becomes public API.** Design a small interface with a clear contract, and restrict via access/module/lifecycle where appropriate.

## 31. Instead of Opening Everything Directly, You Can Use Composition

Not every variation requires subclassing. A final class can accept an open strategy interface:

```java
interface PricingRule {
    int calculate(int amount);
}

final class Checkout {
    private final PricingRule rule;

    Checkout(PricingRule rule) {
        this.rule = java.util.Objects.requireNonNull(rule);
    }

    int total(int amount) {
        return rule.calculate(amount);
    }
}
```

This is a **valid illustrative declaration**, without main yet.

`Checkout` is final and disallows subclassing; however, the `PricingRule` behavior can be swapped via composition. This satisfies the extension need without having to let clients directly inherit from a class carrying sensitive invariants.

**Design mindset:** Sometimes you want to **close the model hierarchy**, yet **open behavior injection** through interfaces. It is not mandatory to open the entire inheritance of an aggregate/entity.

## 32. Runnable Example: Final Core, Open Strategy

Create **`CompositionInsteadOfInheritanceDemo.java`**:

```java
import java.util.Objects;

interface Discount {
    int apply(int total);
}

final class Basket {
    private final Discount discount;

    Basket(Discount discount) {
        this.discount = Objects.requireNonNull(discount);
    }

    int payable(int total) {
        return discount.apply(total);
    }
}

final class NoDiscount implements Discount {
    @Override
    public int apply(int total) {
        return total;
    }
}

final class FixedDiscount implements Discount {
    @Override
    public int apply(int total) {
        return Math.max(0, total - 10);
    }
}

public class CompositionInsteadOfInheritanceDemo {
    public static void main(String[] args) {
        Basket normal = new Basket(new NoDiscount());
        Basket special = new Basket(new FixedDiscount());

        System.out.println(normal.payable(40));
        System.out.println(special.payable(40));
    }
}
```

```bash
javac CompositionInsteadOfInheritanceDemo.java
java CompositionInsteadOfInheritanceDemo
```

```text
40
30
```

`Basket` has no subclasses, yet it can change logic via `Discount`. This is a concrete illustration that “wanting extension” **does not mean making every class non-final**.

If pricing rules only have a few closed choices according to the domain, `Discount` can be sealed; if plugins are added arbitrarily, keep it open. Choose according to the right boundary.

## 33. Do Not Confuse “Closed Variants” with “Data Immutability”

A final subclass or final record does not automatically make all object state immutable:

```java
sealed interface Container
        permits MutableContainer {}

final class MutableContainer implements Container {
    private int count;

    void increment() {
        count++;
    }

    int count() {
        return count;
    }
}
```

This is a valid declaration in the same compilation unit. The hierarchy is **closed**, yet instances of MutableContainer have **mutable state**.

Sealed/final governs **subtyping**, not **mutability**. If thread safety is needed, use immutable state, synchronization, or concurrency primitives according to your own logic.

## 34. A Sealed Interface Can Also Be Implemented by an Enum

An enum is a final class or implicitly sealed in certain cases with constant-specific bodies; it can implement a sealed interface with the corresponding permission.

Create **`SealedInterfaceEnumDemo.java`**:

```java
sealed interface ColorSignal permits Signal {
    String label();
}

enum Signal implements ColorSignal {
    RED, GREEN;

    @Override
    public String label() {
        return name().toLowerCase(java.util.Locale.ROOT);
    }
}

public class SealedInterfaceEnumDemo {
    public static void main(String[] args) {
        ColorSignal a = Signal.RED;
        ColorSignal b = Signal.GREEN;

        System.out.println(a.label());
        System.out.println(b.label());
    }
}
```

```bash
javac SealedInterfaceEnumDemo.java
java SealedInterfaceEnumDemo
```

```text
red
green
```

`Signal` is the direct permitted implementation type of ColorSignal, while RED/GREEN are constants belonging to Signal. `permits` lists **types**, not enum constant values.

**Do not declare `non-sealed enum`**: Enum types have their own rules regarding inheritance/finality. They can implement interfaces, but are not open for user subclasses like regular classes.

## 35. What Happens If External Code Tries to Create an Unpermitted Direct Subtype?

Code that is **intentionally invalid**, not a runnable example:

```java
sealed interface Result permits Success {}

record Success(String value) implements Result {}

final class UnknownResult implements Result {}
```

`UnknownResult` is not listed in `permits`, so it is rejected by the compiler. Being in the same source file does not save it when the parent already has **explicit permits**.

**If you want to allow adding a variant:** The owner of Result updates `permits Success, UnknownResult` and ensures UnknownResult is valid, or omits permits if all direct children have canonical names in the same compilation unit.

**If you want third parties to add variants freely:** You can choose an open interface or a permitted non-sealed branch. Do not tamper with the type system via casting/reflection to “bypass” the sealed contract.

## 36. A Direct Subtype Can Be Further Sealed and Manage Its Own Subtypes

Create **`MultiLevelSealedHierarchyDemo.java`**:

```java
sealed abstract class Expression permits NumberExpr, OperationExpr {
    abstract int eval();
}

final class NumberExpr extends Expression {
    private final int number;

    NumberExpr(int number) {
        this.number = number;
    }

    @Override
    int eval() {
        return number;
    }
}

sealed abstract class OperationExpr
        extends Expression permits SumExpr {
}

final class SumExpr extends OperationExpr {
    private final Expression left;
    private final Expression right;

    SumExpr(Expression left, Expression right) {
        this.left = left;
        this.right = right;
    }

    @Override
    int eval() {
        return left.eval() + right.eval();
    }
}

public class MultiLevelSealedHierarchyDemo {
    public static void main(String[] args) {
        Expression value = new SumExpr(
                new NumberExpr(2), new NumberExpr(5));

        System.out.println(value.eval());
    }
}
```

```bash
javac MultiLevelSealedHierarchyDemo.java
java MultiLevelSealedHierarchyDemo
```

```text
7
```

- Expression permits NumberExpr and OperationExpr **directly**.
- OperationExpr permits SumExpr **directly**.
- SumExpr is an **indirect** descendant of Expression, and is not needed in Expression's permits.
- NumberExpr and SumExpr are final, so those branches terminate.

**Implication:** You can build a fully closed multi-level hierarchy tree to express a domain AST, but each sealed level must have valid permits and each direct child must declare an appropriate final/sealed/non-sealed policy.

## 37. The Runtime Can Recognize a Sealed Type

Java 17 provides reflection:

- `Class.isSealed()`: whether the type is sealed or not.
- `Class.getPermittedSubclasses()`: an array of **permitted direct classes/interfaces** for a sealed type; returns null for a type that is not sealed.

Create **`SealedReflectionComparisonDemo.java`**:

```java
import java.util.Arrays;

sealed interface ClosedMessage permits Letter, Notice {
}

record Letter(String text) implements ClosedMessage {
}

record Notice(int code) implements ClosedMessage {
}

interface OpenMessage {
}

public class SealedReflectionComparisonDemo {
    static String[] names(Class<?> type) {
        Class<?>[] permitted = type.getPermittedSubclasses();
        if (permitted == null) {
            return new String[0];
        }

        String[] result = Arrays.stream(permitted)
                .map(Class::getSimpleName)
                .sorted()
                .toArray(String[]::new);
        return result;
    }

    public static void main(String[] args) {
        System.out.println(ClosedMessage.class.isSealed());
        System.out.println(OpenMessage.class.isSealed());

        System.out.println(Arrays.toString(
                names(ClosedMessage.class)));
        System.out.println(Arrays.toString(
                names(OpenMessage.class)));
    }
}
```

```bash
javac SealedReflectionComparisonDemo.java
java SealedReflectionComparisonDemo
```

```text
true
false
[Letter, Notice]
[]
```

The output is sorted so it does not rely on reflection order. `OpenMessage` is not sealed, so the helper converts null into an empty array. **An empty array here does not prove that an open interface has no implementations**; it only indicates that it has no sealed permits metadata.

Do not use `Class.getPermittedSubclasses()` as a “registry of every loaded subtype” of an open interface. That is not what this tool is for.

## 38. Additional Options: enum, sealed, Open Interface, final + Strategy

| Domain problem | Option to consider | Reason |
| --- | --- | --- |
| Three state names without separate payloads | `enum Status` | Closed, concise set of constant values |
| Multiple results with different payloads, closed set | Sealed interface + records | Variants have different data structures |
| Several behavior strategies installed from plugins | Open interface | Open set of implementations |
| A domain class with invariants, no subclassing desired | Final class | Locks inheritance of the core |
| Wanting replaceable behavior on a final class | Composition + open interface | Opens behavior, does not open the entity |
| Standard variants exist, plus a custom branch | Sealed root + non-sealed branch | Keeps the core closed, with a clear extension branch |
| The system needs exhaustiveness testing of direct variants | Sealed fully-closed hierarchy | Type constraints reflect the set |
| Users directly configure type names in the DB | Entity/registry/config | The set changes at runtime, not compile time |
| Base class needs protected hooks for app customization | Open abstract class | Inheritance is the extension contract |
| Base type must not be extended due to security/invariants | Final or sealed, depending on whether children are needed | Blocks unauthorized subclasses |

Do not choose based solely on “the fewest lines”. The degree of openness or closure is a decision about **extension rights and maintenance costs**.

## 39. A Note on the Open/Closed Principle

In SOLID, “open for extension, closed for modification” is frequently cited. However, that does not mean **every class must be non-final or every interface must not be sealed**.

The two are different concepts:

- **Open/Closed Principle**: a guideline for organizing code to add behavior without modifying already stable parts, when appropriate.
- **Java `sealed`**: a language mechanism that manages the list of permitted direct subtypes.

An application can **close its domain hierarchy** to protect invariants while simultaneously **opening extension through composition/services**. Conversely, an open interface where consumers repeatedly check `instanceof` for each implementation can still violate the spirit of extensible design.

**Practical question:** Should extension happen **in the type hierarchy**, **via an injected behavior object**, or **via data/config**? Sealed is only one of the tools for answering that.

## 40. Cases Where You Should Not Rush to Turn an Open Class into Sealed

- The library has published a superclass that is subclassed by hundreds of other packages.
- You do not control or cannot enumerate direct client subclasses.
- Plugins in different named modules must directly implement the interface.
- Each tenant has its own implementation at runtime.
- Tests currently use subclass test doubles of the parent; after sealing, they may need to switch to a mock interface/composition/permitted extension point.
- The parent does not represent a closed set of variants, but only a behavior contract.

**Before migrating**, classify usages: internal subclasses, external subclasses, mocks, generated proxies, runtime code generators, and serialization frameworks. Sealing changes the ability to create subclasses, so it can also affect tooling.

## 41. Cases Where You Should Not Rush to Remove Sealed

- There are protocol enum-like variants that need clear boundaries.
- There are AST families that need auditing.
- Record variants are closed according to a schema version.
- Encountering an unintended subtype could cause business logic to be handled incorrectly or break assumptions.
- All types belong to the same group/module and are managed by the author.
- You want the compiler to remind you to handle new subtypes wherever exhaustive constructs appropriate for the Java version are used.

Removing sealed to handle an edge case can lose **important domain information**. It can be solved with a carefully considered `non-sealed` branch or with external strategy composition while keeping the root closed.

## 42. Design Plan for a New API

When creating an API with multiple implementations, ask yourself in sequence:

1. **Is this type an open contract or a closed sum of variants?**
2. Are there implementations that will be **added by the app/third parties after deployment**?
3. Who is the **owner** of the inheritance hierarchy?
4. Are the implementations in the same named module/package?
5. Are different data/fields needed in each variant?
6. Should inheritance be closed at the leaves with `final`?
7. Is there any branch that needs to be reopened with `non-sealed`?
8. If a new subtype is added, which consumers need to be updated?
9. Can data serialization/API compatibility tolerate changes?
10. Can behavior extension be separated into a strategy interface while keeping the domain class final?
11. Do tests protect the expected direct subtype set?
12. Does the target Java version support the patterns/switch features you intend to use?

Only after that should you choose `sealed`/`non-sealed`/`final`/ordinary interface/class. Defining a clear contract will reduce the risk of refactoring causing breaking changes later.

## 43. Testing a Sealed Hierarchy

Create **`SealedHierarchySelfTest.java`**:

```java
import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;

sealed interface Response permits Accepted, Rejected {
}

record Accepted(int id) implements Response {
}

record Rejected(String message) implements Response {
}

public class SealedHierarchySelfTest {
    static void check(boolean passed, String label) {
        if (!passed) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        check(Response.class.isSealed(), "root sealed");
        check(!Accepted.class.isSealed(), "record leaf");

        Class<?>[] permitted =
                Response.class.getPermittedSubclasses();

        check(permitted.length == 2, "two direct variants");

        Set<String> names = Arrays.stream(permitted)
                .map(Class::getSimpleName)
                .collect(Collectors.toSet());

        check(names.equals(Set.of("Accepted", "Rejected")),
                "permitted types");

        Response result = new Accepted(7);
        check(result instanceof Accepted, "runtime variant");

        System.out.println("sealed hierarchy PASS");
    }
}
```

```bash
javac SealedHierarchySelfTest.java
java SealedHierarchySelfTest
```

```text
sealed hierarchy PASS
```

The self-test directly checks the runtime reflection type set and one polymorphic assignment. It does not depend on reflection order. `check` explicitly throws AssertionError; there is no need to enable `-ea`.

**Limitation:** The test does not prove that the business logic of Accepted/Rejected is correct in all cases; constructors, payload invariants, and consumers still require separate tests.

## 44. Testing an Open Extension Point

An open interface has no reflection metadata listing all implementations. The right tests are **contract tests** executed against registered/provided implementations.

Create **`OpenContractSelfTest.java`**:

```java
interface Formatter {
    String format(String input);
}

final class PlainFormatter implements Formatter {
    @Override
    public String format(String input) {
        return input;
    }
}

final class BracketFormatter implements Formatter {
    @Override
    public String format(String input) {
        return "[" + input + "]";
    }
}

public class OpenContractSelfTest {
    static void check(boolean passed, String label) {
        if (!passed) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        Formatter[] examples = {
                new PlainFormatter(),
                new BracketFormatter()
        };

        for (Formatter formatter : examples) {
            String output = formatter.format("A");
            check(output != null, "non-null output");
            check(output.contains("A"), "preserves input");
        }

        System.out.println("open contract PASS");
    }
}
```

```bash
javac OpenContractSelfTest.java
java OpenContractSelfTest
```

```text
open contract PASS
```

The two formatters are the implementations currently tested, **not proof that only two valid implementations exist**. In an open hierarchy, you need to publish invariants/contracts for any new extension and provide a suite of conformance tests when needed.

## 45. Prediction Exercise: Which Hierarchy Is Completely Closed?

Consider:

```java
sealed interface Node permits Leaf, Branch {}

record Leaf(String value) implements Node {}

sealed interface Branch extends Node permits BranchEnd {}

record BranchEnd(int number) implements Branch {}
```

This is a valid illustrative declaration in the same compilation unit.

**Question:** Can you freely add a class `NewLeaf implements Node` from another file without modifying Node? Can you freely add `NewBranchEnd implements Branch`?

**Answer:** No. Node and Branch are both sealed, and their direct permitted sets are fixed. `Leaf` and `BranchEnd` are final records. The entire inheritance hierarchy in the example is **closed across all branches**.

If you want to open Branch alone, you need a direct permitted non-sealed subtype of Branch or a design change. You cannot take a “shortcut” with a cast or annotation.

## 46. Prediction Exercise: What Reopens?

Consider:

```java
sealed interface Process permits Internal, External {}

record Internal(String id) implements Process {}

non-sealed interface External extends Process {}

final class VendorProcess implements External {}
```

**Question:** What is the set of direct permitted types of Process? Can an `OtherVendor implements External` be added?

**Answer:** The direct permitted types are Internal and External. Implementations of `External` can be added if normal Java access/module rules are satisfied, because External is `non-sealed`. This is a hierarchy with a sealed root but **one open branch**; it must not be interpreted to mean that only Internal and VendorProcess are all the final subtypes.

## 47. Model Selection Exercise

| Requirement | Reference choice | Explanation |
| --- | --- | --- |
| Parse result types: Ok(payload), Error(message) | Sealed interface + records | Closed set of variants with payloads |
| An editor needs new render plugins | Open interface | Third-party implementations |
| Data class must not be subclassed | Final class/record | Closes inheritance of a single node |
| Fixed AST operator variants in a compiler | Sealed hierarchy | Owner controls variants |
| Multiple payment tools depending on provider | Open PaymentProvider interface | Extensible set of providers |
| Closed built-in parsers, external extension parsers | Sealed root + non-sealed extension branch | Separates extension permissions |
| A boolean isActive | Boolean | No hierarchy needed |
| Three levels LOW/MEDIUM/HIGH | Enum | Set of named constant values |
| Immutable domain object, but validation logic varies | Final domain class + Strategy | Closes entity inheritance, opens behavior |
| Users create dynamic status names in the admin UI | Data-driven model | Not a closed compile-time type family |

**Thought exercise:** Choose a model for your project and explain it in terms of **subtype creation rights** and **the lifecycle of variant-set changes**, rather than just saying “sealed looks professional”.

## 48. Common Pitfalls

| Misconception | Fact to remember |
| --- | --- |
| “Sealed means it cannot be subclassed” | Can be subclassed directly if permitted |
| “Sealed means there is no polymorphism” | Dynamic dispatch still works |
| “Abstract locks the hierarchy automatically” | Abstract does not restrict subclasses by itself |
| “Final and sealed are the same” | Final forbids children; sealed permits a direct list |
| “A non-sealed child makes the root unsealed” | The root remains sealed; only the child branch opens |
| “Permits lists all descendants” | Only direct permitted subtypes |
| “Sealed always has a finite set of all descendants” | A non-sealed branch can open without limit |
| “Every implementation must be in the same source file” | With explicit permits, they can be in different files, provided package/module rules are satisfied |
| “Same file is enough if permits is omitted” | Direct relation and canonical names are required |
| “An open interface means anyone can implement it” | Access, modules, and normal Java rules still apply |
| “Sealed guarantees thread safety/immutability” | Not directly related |
| “A record is always sealed” | A record is a final class and can implement a sealed interface |
| “Each enum constant is listed in permits” | Permits lists types, not object constants |
| “Java 17 supports final pattern switch” | Java 17 pattern switch is still preview |
| “Adding a variant does not affect clients” | Consumers, serialization, and source/binary compatibility must be considered |
| “An open class is always better because it is extensible” | Extensibility also has costs and risks of breaking invariants |
| “Every class should be sealed for safety” | The domain and extension contract decide |
| “Having non-sealed means plugins register automatically” | Registry/loading/lifecycle are still required |
| “getPermittedSubclasses also lists subclasses of an open interface” | This reflection API is for sealed permits, not a registry |
| “A sealed interface can implement a class” | Interfaces extend interfaces; classes implement interfaces |
| “Simply compiling the example proves business logic is correct” | Tests/invariants beyond type constraints are needed |

## 49. Code Review Checklist

- [ ] Does the type represent a **closed** set of variants or an **open** extension contract?
- [ ] Who is allowed to add a direct subtype and when?
- [ ] If sealed, has the list of permitted direct types been correctly determined?
- [ ] Do all direct permitted classes have an appropriate final/sealed/non-sealed policy?
- [ ] Do direct permitted interfaces have an appropriate sealed/non-sealed policy?
- [ ] Are indirect subtypes not confused with direct permits?
- [ ] Is there a non-sealed branch that reopens the family?
- [ ] Is the module/package location valid?
- [ ] If permits is omitted, do all direct children to be inferred have canonical names in the same compilation unit?
- [ ] If opening a public API, do access/constructors/module exports allow inheritance as intended?
- [ ] Are abstract methods or default methods needed to define the behavior contract?
- [ ] If the hierarchy is open, do consumers avoid assuming only a few implementations exist?
- [ ] If the hierarchy is closed, do variant changes review consumers/tests/serialization?
- [ ] Are record variants used when payload shapes differ?
- [ ] Should an enum be used instead of an overly complex hierarchy?
- [ ] Can behavior extension be separated into composition/strategy?
- [ ] Is sealed not mistaken for thread safety, immutability, or security?
- [ ] For Java 17, is preview pattern `switch` not used without flags?
- [ ] Does the reflection test check only **direct** permitted types?
- [ ] Does it avoid relying on the order of `getPermittedSubclasses()` if the test does not need it?
- [ ] Do code samples have valid filenames/public classes, `javac`/`java` commands, and stdout?

## 50. Review Questions with Answers

**1.** What is an open hierarchy?

*It is a class/interface hierarchy that allows adding subclasses/implementations under normal Java access/inheritance rules, without a closed sealed permits list.*

**2.** What does sealed control directly?

*The list of permitted direct subclasses or direct subinterfaces.*

**3.** Does sealed forbid virtual method dispatch?

*No.*

**4.** How does a `final class` differ from a `sealed class`?

*Final forbids subclassing; sealed allows certain permitted direct subclasses.*

**5.** Does an `abstract class` close subclasses by itself?

*No.*

**6.** Where is `non-sealed` used?

*Used on a valid direct subtype of a sealed type to reopen the inheritance branch.*

**7.** If a child is non-sealed, does the root remain sealed?

*Yes. The root still restricts its own direct children.*

**8.** Does an indirect grandchild need to be in the root permits?

*No; permits is only for direct types.*

**9.** When can permits be omitted?

*When valid direct subtypes have canonical names in the same compilation unit so the compiler can infer them.*

**10.** Are types in the same package but different files inferred automatically?

*No.*

**11.** Can two different modules share a direct permitted subtype when the parent is in a named module?

*No; direct permitted subtypes must reside in the same named module.*

**12.** Can a record implement a sealed interface?

*Yes, if it is a permitted direct implementation; a record is itself final.*

**13.** Can an enum implement a sealed interface?

*Yes, if permitted by the rules; enum constants are not the names listed in permits.*

**14.** Does sealed make all fields immutable?

*No.*

**15.** In what situations is an open hierarchy suitable?

*Plugin/strategy extension contracts where third parties can add implementations.*

**16.** In what situations is sealed suitable?

*Sets of variants defined by the owner and changed through controlled releases/schemas.*

**17.** Can a closed core be combined with open plugins?

*Yes, for example a sealed root permitting a non-sealed extension interface.*

**18.** Why might you choose a final class with an injected interface?

*To protect the class's invariants while still allowing behavior to vary via composition.*

**19.** What does `Class.getPermittedSubclasses()` return?

*The direct permitted types of the sealed class/interface, not all descendants or all loaded plugins.*

**20.** Does Java 17 have a final pattern switch yet?

*Not yet; it is a preview feature, so when using stable Java 17, prefer instanceof type patterns and polymorphism.*

**21.** What can converting a public open class to sealed cause?

*It can break the contract of unpermitted client subclasses; a migration/compatibility review is needed.*

**22.** What can adding a new variant to a sealed hierarchy cause?

*Consumers/tests/serializers need updating, especially exhaustive logic.*

**23.** If there are only a few constant values without payloads, what should be considered?

*An enum can be shorter and better fit the domain than a sealed hierarchy.*

**24.** If each variant has a different payload, what should be considered?

*A sealed interface + records/classes usually expresses it clearly.*

**25.** Why shouldn't sealed be used as a general security tool?

*Because it restricts type inheritance and does not automatically handle validation, permissions, synchronization, or secrets.*

---

**Final takeaway:** **An open hierarchy** allows adding implementations under standard inheritance/implementation contracts; it suits frameworks and plugin extensions but demands an API that holds up against unknown subclasses. **A `sealed` hierarchy** allows the author to control **direct permitted types**, helping model a closed, clear, and easily reviewable set of domain variants. Direct children must choose `final` (close the branch), `sealed` (continue sealing), or `non-sealed` (reopen the branch) according to Java rules. Sealed **does not eliminate polymorphism**, **does not guarantee that all descendants are finite** if a non-sealed branch exists, and **does not replace validation, immutability, or security**. Choose based on **who owns the right to create subtypes and through which process the set of variants changes**; consider enums, composition, and strategies when inheritance is not the appropriate extension point.
