# Common `sealed` Compilation Errors in Java 17 and Side-by-Side Examples

`sealed` is a mechanism for **restricting which types may inherit a class or implement an interface**. It is a standard feature in Java 17. When a `sealed class` or `sealed interface` declares its set of permitted direct subtypes, the compiler can catch many hierarchy design mistakes early.

This lesson focuses on **common compilation errors** and contrasts **invalid code** with **valid code** within the scope of Java 17. Snippets marked "Invalid" are intentionally written to trigger errors; each example should be tested separately because those snippets cannot compile together.

## 1. Quick rule recap before inspecting errors

A type declared `sealed` imposes rules on its **direct subtypes**:

1. A direct subtype must belong to the list in the `permits` clause, or to the list inferred by the compiler in the same *compilation unit* (usually the same `.java` file).
2. A `class` directly extending a `sealed class` or directly implementing a `sealed interface` must explicitly declare one of three states: **`final`**, **`sealed`**, or **`non-sealed`**; `record` is already implicitly `final`.
3. Permitted subtypes must actually `extends` or `implements` that `sealed` type **directly**.
4. In a **named module**, direct subtypes must reside in the **same module** as the `sealed` type. In an **unnamed module** (a project without a module declaration), direct subtypes must reside in the **same package**.

Meaning of the three choices for a direct subtype:

| Keyword | Meaning | Can it be extended further? |
| --- | --- | --- |
| `final` | Locks the inheritance branch at that subclass. | No class may inherit from a `final` class. |
| `sealed` | Continues controlling the direct subtype list at the next tier. | Yes, but only by subtypes permitted at that tier. |
| `non-sealed` | Reopens standard inheritance/implementation for that branch. | Yes, under normal Java inheritance rules. |

> `permits` controls only **direct inheritance or implementation relationships**. It does not list every indirect subtype across the entire inheritance tree.

## 2. Valid baseline example for comparison

Save the code below into **`SealedDemo.java`**:

```java
sealed interface Payment permits CashPayment, CardPayment, PartnerPayment {
}

record CashPayment(int amount) implements Payment {
    // record is implicitly final, so writing "final" is unnecessary.
}

final class CardPayment implements Payment {
}

non-sealed class PartnerPayment implements Payment {
}

final class FastPartnerPayment extends PartnerPayment {
    // This is an indirect subtype of Payment; does not need to be in permits.
}

public class SealedDemo {
    public static void main(String[] args) {
        Payment[] payments = {
                new CashPayment(100),
                new CardPayment(),
                new PartnerPayment(),
                new FastPartnerPayment()
        };

        for (Payment payment : payments) {
            System.out.println(payment.getClass().getSimpleName());
        }
    }
}
```

Compile and run with JDK 17 or a JDK supporting target Java 17:

```bash
mkdir out
javac --release 17 -encoding UTF-8 -d out SealedDemo.java
java -cp out SealedDemo
```

Expected output:

```text
CashPayment
CardPayment
PartnerPayment
FastPartnerPayment
```

Note the following details:

- `Payment` is a `sealed interface`, allowing only three **direct** implementing types: `CashPayment`, `CardPayment`, and `PartnerPayment`.
- `CashPayment` is a `record`, treated as `final`; it can directly implement a `sealed interface` without writing `final`.
- `CardPayment` uses `final` to terminate the branch.
- `PartnerPayment` uses `non-sealed`, so `FastPartnerPayment` is allowed to extend it. `FastPartnerPayment` does not directly implement `Payment`, so it does not appear in `permits`.

The error examples below vary one rule of this baseline at a time.

## 3. Error 1: Direct subtype missing from `permits`

**Invalid — `TextFile` directly implements `FileType` without being permitted:**

```java
sealed interface FileType permits PdfFile {
}

final class PdfFile implements FileType {
}

final class TextFile implements FileType { // ERROR
}
```

`TextFile` directly implements `FileType`, while `permits` only lists `PdfFile`. The compiler rejects it because `TextFile` is not a permitted subtype. The error message may resemble `class is not allowed to extend sealed class`; exact wording depends on the JDK and compiler environment.

**Valid — add the direct subtype to the list:**

```java
sealed interface FileType permits PdfFile, TextFile {
}

final class PdfFile implements FileType {
}

final class TextFile implements FileType {
}
```

**How to spot:** When seeing an error about a type not being allowed to extend a `sealed` type, immediately check its `extends`/`implements` clause and compare it against the parent's `permits`.

## 4. Error 2: Forgetting `final`, `sealed`, or `non-sealed` on a direct subtype

**Invalid — `EmailTask` does not state how its inheritance branch continues:**

```java
sealed interface Task permits EmailTask {
}

class EmailTask implements Task { // ERROR
}
```

A class directly implementing a `sealed interface` cannot leave its inheritance status unspecified. The compiler requires declaring one of the three keywords: `final`, `sealed`, or `non-sealed`.

**Valid — if no subclasses are desired:**

```java
sealed interface Task permits EmailTask {
}

final class EmailTask implements Task {
}
```

**Valid — if reopening the inheritance branch:**

```java
sealed interface Task permits EmailTask {
}

non-sealed class EmailTask implements Task {
}

class ScheduledEmailTask extends EmailTask {
}
```

**Valid — if controlling one more tier:**

```java
sealed interface Task permits EmailTask {
}

sealed class EmailTask implements Task permits ScheduledEmailTask {
}

final class ScheduledEmailTask extends EmailTask {
}
```

If directly implementing a `sealed interface` with a `record`, none of those three keywords is needed because `record` is already a `final` type:

```java
sealed interface Task permits EmailTask {
}

record EmailTask(String recipient) implements Task {
}
```

## 5. Error 3: Naming a type in `permits` that does not directly inherit

**Invalid — `Printer` is listed in `permits` but does not `extends Device`:**

```java
sealed class Device permits Printer {
}

final class Printer { // ERROR
}
```

Declaring `permits Printer` does not create an inheritance relationship by itself. The `permits` list only states **which types are permitted** to inherit; the type itself must still declare `extends` or `implements`.

**Valid:**

```java
sealed class Device permits Printer {
}

final class Printer extends Device {
}
```

The same principle applies to interfaces:

```java
sealed interface Device permits Printer {
}

final class Printer implements Device {
}
```

A related error is putting a **grandchild** (indirect subtype) into a grandparent's `permits` even though it does not inherit directly. Each `sealed` tier declares only **its own direct** subtypes.

## 6. Error 4: Combining conflicting inheritance modifiers

The states `final`, `sealed`, and `non-sealed` express different policies, so two of them cannot be used together on the same class.

**Invalid — simultaneously sealing completely and keeping sealed for subclasses:**

```java
final sealed class Message permits TextMessage { // ERROR
}

final class TextMessage extends Message {
}
```

**Valid — choose one policy:**

```java
sealed class Message permits TextMessage {
}

final class TextMessage extends Message {
}
```

Likewise, `final non-sealed class` and `sealed non-sealed class` are invalid modifier combinations.

Distinguish this from `abstract`: a `sealed` class **can also be `abstract`**, because those two modifiers do not conflict:

```java
abstract sealed class Message permits TextMessage {
    abstract String content();
}

final class TextMessage extends Message {
    @Override
    String content() {
        return "Hello";
    }
}
```

`abstract` specifies that the class cannot be instantiated directly and may declare abstract methods; `sealed` specifies who may inherit the class.

## 7. Error 5: Using `non-sealed` without a `sealed` direct parent

`non-sealed` is not an arbitrary modifier usable on any class. It applies only to a class or interface that is a **direct subtype of a `sealed` type**.

**Invalid:**

```java
class Base {
}

non-sealed class Child extends Base { // ERROR
}
```

`Base` is a regular class; `Child` has no `sealed` direct parent, so `non-sealed` is invalid.

**Valid — if standard inheritance is all you want:**

```java
class Base {
}

class Child extends Base {
}

class Grandchild extends Child {
}
```

**Valid — if genuinely reopening a branch from a `sealed` type:**

```java
sealed class Base permits Child {
}

non-sealed class Child extends Base {
}

class Grandchild extends Child {
}
```

For interfaces, the rule is the same:

```java
sealed interface Plugin permits ExternalPlugin {
}

non-sealed interface ExternalPlugin extends Plugin {
}

class CustomPlugin implements ExternalPlugin {
}
```

## 8. Error 6: Misunderstanding `permits` scope for indirect subtypes

Consider the inheritance tree:

```text
sealed interface Operation
       |
       +-- final class SaveOperation
       |
       +-- non-sealed class CustomOperation
                    |
                    +-- final class AuditOperation
```

**Valid — indirect subtypes do not belong in `Operation.permits`:**

```java
sealed interface Operation permits SaveOperation, CustomOperation {
}

final class SaveOperation implements Operation {
}

non-sealed class CustomOperation implements Operation {
}

final class AuditOperation extends CustomOperation {
}
```

**Invalid — `AuditOperation` attempts to implement `Operation` directly outside the permitted list:**

```java
sealed interface Operation permits SaveOperation, CustomOperation {
}

final class SaveOperation implements Operation {
}

non-sealed class CustomOperation implements Operation {
}

final class AuditOperation implements Operation { // ERROR
}
```

The difference is `extends CustomOperation` versus `implements Operation`. A `non-sealed` branch can have many subclasses, but a new class cannot bypass the intermediate branch to become an unauthorized direct subtype.

In addition, if the direct branch is declared `final` instead of `non-sealed`, any attempt to `extends` that `final` class triggers a separate inheritance error (`cannot inherit from final`).

## 9. Error 7: Declaring `sealed` with no valid permitted subtypes

When `permits` is omitted, `javac` can infer only direct subtypes declared **in the same compilation unit** as the `sealed` type.

**Invalid — two separate source files without `permits`:**

File `Animal.java`:

```java
public sealed interface Animal {
}
```

File `Dog.java`:

```java
public final class Dog implements Animal {
}
```

Even when compiling both files together, `Animal` still lacks a valid permitted subtype list: there is no explicit `permits`, and `Dog` is not in the same compilation unit. An error may be reported on `Animal` and/or `Dog`'s `implements` clause.

**Valid — two separate files, explicit declaration:**

`Animal.java`:

```java
public sealed interface Animal permits Dog {
}
```

`Dog.java`:

```java
public final class Dog implements Animal {
}
```

**Valid — single compilation unit, `permits` may be omitted:**

File `Animal.java`:

```java
public sealed interface Animal {
}

final class Dog implements Animal {
}
```

The latter case uses **subtype list inference**, not unlimited implementation permission. When moving a subtype to another file, add `permits` explicitly.

## 10. Error 8: Subtype placed in the wrong package or module

One subtle mistake is naming subtypes accurately while placing them in a disallowed scope.

### 10.1. Unnamed-module project: same package required

**Invalid — two different packages in a project without `module-info.java`:**

`src/api/Request.java`:

```java
package api;

public sealed interface Request permits impl.HttpRequest {
}
```

`src/impl/HttpRequest.java`:

```java
package impl;

public final class HttpRequest implements api.Request {
}
```

Even though `HttpRequest` appears in `permits` and directly implements `Request`, Java 17 rejects it because the two types belong to **different packages in an unnamed module**.

**Valid — place in the same package:** 

`src/api/Request.java`:

```java
package api;

public sealed interface Request permits HttpRequest {
}
```

`src/api/HttpRequest.java`:

```java
package api;

public final class HttpRequest implements Request {
}
```

Compile:

```bash
javac --release 17 -d out src/api/Request.java src/api/HttpRequest.java
```

Both belong to package `api`, satisfying the unnamed-module rule.

### 10.2. Named module: different packages allowed, but same module required

If the project **explicitly declares a module**, the `sealed` type and its permitted direct subtypes may reside in different packages **as long as they are in the same named module**.

Example structure:

```text
src/
├── module-info.java
└── shop/
    ├── api/
    │   └── Request.java
    └── impl/
        └── HttpRequest.java
```

`src/module-info.java`:

```java
module shop.core {
    exports shop.api;
}
```

`src/shop/api/Request.java`:

```java
package shop.api;

public sealed interface Request permits shop.impl.HttpRequest {
}
```

`src/shop/impl/HttpRequest.java`:

```java
package shop.impl;

public final class HttpRequest implements shop.api.Request {
}
```

Compile:

```bash
javac --release 17 -d out src/module-info.java src/shop/api/Request.java src/shop/impl/HttpRequest.java
```

In this example, `shop.api.Request` and `shop.impl.HttpRequest` both belong to module `shop.core`. You cannot move `HttpRequest` alone into a **different named module** and keep it a valid direct subtype of `Request`.

## 11. Error 9: Marking the next tier `sealed` while forgetting to declare its branches

A direct subtype can itself declare `sealed`. At that new tier, however, that subtype must have its own valid direct subtype list.

**Invalid — `Approved` is `sealed` without any permitted subtypes:**

```java
sealed interface Review permits Approved {
}

sealed class Approved implements Review { // ERROR
}
```

`Approved` has no sub-branches in the same compilation unit to infer from and declares no `permits` of its own.

**Valid — if this is the final branch, use `final`:**

```java
sealed interface Review permits Approved {
}

final class Approved implements Review {
}
```

**Valid — if sealing another tier:**

```java
sealed interface Review permits Approved {
}

sealed class Approved implements Review permits AutoApproved {
}

final class AutoApproved extends Approved {
}
```

Note: `AutoApproved` is a direct subtype of `Approved`, not a direct subtype of `Review`, so it does not appear in `Review.permits`.

## 12. Error 10: Compiling `sealed` at a language level below Java 17

`sealed` and `non-sealed` became **standard** language features in Java 17. Setting an older release target causes the compiler to reject Java 17 sealed code.

The following assumes you created `SealedDemo.java` from Section 2:

```bash
# Wrong release target for a Java 17 example:
javac --release 11 -d out SealedDemo.java

# Correct target:
javac --release 17 -d out SealedDemo.java
```

If `--release 17` itself reports `release version 17 not supported`, the cause is that **the `javac` being invoked does not support target 17**; check:

```bash
javac -version
javac --help
```

Select a JDK that supports `--release 17` and verify that your terminal, IDE, and build tool are actually using that JDK.

## 13. Easy confusion with pattern-matching `switch` errors

A learner may write a completely valid sealed hierarchy and then write a `switch` dispatching by type and hit a compile error. In that case, the error may come from **`switch` syntax**, not from `sealed`.

Example:

```java
sealed interface Shape permits Circle, Rectangle {
}

record Circle(double radius) implements Shape {
}

record Rectangle(double width, double height) implements Shape {
}

class ShapePrinter {
    static String describe(Shape shape) {
        return switch (shape) {
            case Circle c -> "Circle: " + c.radius();
            case Rectangle r -> "Rectangle: " + r.width();
        };
    }
}
```

In **Java 17**, pattern matching in `switch` is still a *preview* feature, so this snippet will not compile with a standard Java 17 command without preview flags enabled. Making `Shape` `sealed` does not automatically enable preview features or turn pattern `switch` into standard Java 17 syntax.

**Java 17-compatible alternative without preview:** use pattern matching with `instanceof`, which is already standard:

```java
sealed interface Shape permits Circle, Rectangle {
}

record Circle(double radius) implements Shape {
}

record Rectangle(double width, double height) implements Shape {
}

class ShapePrinter {
    static String describe(Shape shape) {
        if (shape instanceof Circle c) {
            return "Circle: " + c.radius();
        }

        if (shape instanceof Rectangle r) {
            return "Rectangle: " + r.width();
        }

        throw new IllegalArgumentException("Unexpected shape: " + shape);
    }
}
```

In this `if` version, the compiler **does not check branch completeness the way a `switch` supporting exhaustive pattern matching can**. If a new permitted `Shape` subtype is added later, developers must review handling logic manually. This is the difference between `sealed`'s hierarchy-closing rule and the branch-checking rules of individual control-flow constructs.

## 14. Quick lookup table: which rule does each error point to?

| Error symptom | Cause to check | Common fix |
| --- | --- | --- |
| `class is not allowed to extend sealed class` or equivalent | A direct subtype is missing from a valid `permits` list. | Add the right type to `permits` or fix the inheritance relationship. |
| Missing one of `final`, `sealed`, `non-sealed` | A class directly inheriting/implementing `sealed` left its inheritance status unspecified. | Choose an inheritance policy on the subclass. |
| `invalid permits clause` | Name in `permits` is not a valid direct subtype, or module/package scope disallows it. | Check `extends`/`implements` and source/module organization. |
| `non-sealed modifier not allowed here` | `non-sealed` is not attached to a type with a `sealed` direct parent. | Remove `non-sealed` or fix the relationship with an actual `sealed` parent. |
| `illegal combination of modifiers` | Invalid combination of `final`, `sealed`, `non-sealed`. | Choose only one appropriate inheritance policy. |
| `sealed class must have subclasses` or equivalent | No valid explicit or inferred permitted direct subtypes. | Add subtypes and `permits` as needed, or reconsider removing `sealed`. |
| Cannot extend from another package | Using an unnamed module with a direct subtype in a different package. | Place in the same package or design an appropriate named module. |
| `preview features are disabled by default` at `switch` | Writing pattern matching for `switch` on Java 17 without enabling preview. | Use `instanceof` pattern matching if keeping Java 17 code preview-free. |
| `release version 17 not supported` | Selected `javac` does not support target 17. | Use a JDK supporting `--release 17`. |

Exact message wording can vary across `javac` releases; diagnosing the cause still rests on **direct subtypes**, **modifiers**, **`permits`**, and **module/package scope**.

## 15. How to isolate errors on your own when practicing

When a `sealed` example fails to compile, instead of changing multiple things at once, check in order:

1. **Java version:** Check `javac -version` and compile targeting `--release 17`.
2. **Direct relationship:** Identify which `sealed` type is targeted by `extends` or `implements`.
3. **Permitted list:** Check that `sealed` type's `permits`; if omitted, verify same-compilation-unit inference conditions.
4. **Subclass modifier:** Choose `final`, `sealed`, or `non-sealed`; for `record`, `final` is already implicit.
5. **Next sealed tier:** If the subclass is itself `sealed`, ensure it has its own valid direct subtypes.
6. **Package/module:** In an unnamed module, same package is required; in a named module, same module is required.
7. **Other language features:** If the error is in a `switch` or another newer syntax, separate that issue from `sealed` rules.

To practice side-by-side comparison, save each "Invalid" example into its own standalone file, observe `javac`'s message, then replace it with the "Valid" variant directly below it and recompile. Do not place all examples into the same directory/package at once, as many intentionally reuse type names (`Task`, `Request`, `Shape`, etc.).

Mastering three questions—**"Who is allowed to be a direct subtype?"**, **"How does that subtype continue inheritance?"**, and **"Are the types in the right module/package?"**—will help you resolve most compilation errors involving `sealed` in Java 17.
