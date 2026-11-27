# Continuation Rules for Subinterfaces in Java 17

In Java 17, `sealed interface` enables designing a controlled type hierarchy: the parent interface specifies **which classes and interfaces are permitted to inherit or implement it directly**. When a **subinterface directly `extends` a `sealed interface`**, the subinterface must explicitly declare how the hierarchy continues: **continue restricting via `sealed`** or **open freely via `non-sealed`**.

This rule matters because as soon as a branch is opened with `non-sealed`, types deeper down that branch can continue extending without their names appearing in the root interface's `permits`.

> **Scope:** This lesson uses **standard Java 17** syntax. Sealed classes and sealed interfaces were standardized in Java 17 (JEP 409), requiring no `--enable-preview`. The focus here is on **subinterfaces**, while distinguishing implementing classes where needed.

## 1. Two concepts to establish first

Suppose we have the hierarchy:

```java
sealed interface Message permits TextMessage, BinaryMessage {}

sealed interface TextMessage extends Message permits PlainText {}
non-sealed interface BinaryMessage extends Message {}

record PlainText(String value) implements TextMessage {}
```

Here:

- `Message` is the **parent sealed interface**.
- `TextMessage` and `BinaryMessage` are **direct subinterfaces** of `Message` because each directly declares `extends Message`.
- `PlainText` is a record **directly implementing** `TextMessage`, and at the same time an **indirect** implementation of `Message`.
- `Message`'s `permits TextMessage, BinaryMessage` governs the **direct child layer**, rather than listing every type at deeper tiers.

Relationship diagram:

```text
Message                           (sealed)
├── TextMessage                   (sealed: continues restricting)
│   └── PlainText                 (record: cannot be inherited further)
└── BinaryMessage                 (non-sealed: opens branch)
    └── New interfaces/classes    (under standard Java rules)
```

**The word "direct" determines the rule.** An interface that indirectly belongs to `Message`'s hierarchy by directly extending only `BinaryMessage` is not required to use `sealed` or `non-sealed` just because its distant ancestor is `Message`.

## 2. Mandatory rules for a direct subinterface of a sealed interface

According to the **Java Language Specification (JLS) 17, §9.1.1.4**, if an interface `Child` has a **direct superinterface** declared `sealed`, then `Child`:

1. Must be permitted to directly inherit from the parent interface, either via its `permits` list or via the `permits` inference rule.
2. Must declare **one of the two** modifiers: `sealed` or `non-sealed`.
3. Must not declare both `sealed` and `non-sealed` at the same time.
4. Cannot choose `final`, because **an interface cannot be declared `final`**.

Minimal valid example:

```java
sealed interface Parent permits RestrictedChild, OpenChild {}

sealed interface RestrictedChild extends Parent
        permits RestrictedImplementation {}

non-sealed interface OpenChild extends Parent {}

final class RestrictedImplementation implements RestrictedChild {}
```

**Invalid** example:

```java
sealed interface Parent permits Child {}

interface Child extends Parent {} // ERROR: missing sealed or non-sealed
```

Merely having `Child` appear in `permits` is **not enough**: `Child` must still state its extension policy for the next tier. Nor can `abstract` substitute for `sealed` or `non-sealed`, because every interface is already implicitly abstract.

| Direct subinterface `extends` a sealed interface | Allowed in Java 17? | Meaning |
| --- | --- | --- |
| `sealed interface Child extends Parent ...` | Yes, if `Parent` permits `Child` and `Child` has valid direct subtypes | Continues controlling direct subtypes of `Child`. |
| `non-sealed interface Child extends Parent {}` | Yes, if `Parent` permits `Child` | Allows extending the `Child` branch under standard inheritance rules. |
| `interface Child extends Parent {}` | No | Missing mandatory hierarchy policy. |
| `final interface Child extends Parent {}` | No | `final` is not a valid modifier for interfaces. |
| `sealed non-sealed interface Child extends Parent ...` | No | Conflicting modifiers. |

## 3. Choosing `sealed`: restricting further at the subinterface level

When declaring `sealed interface Child extends Parent`, `Child` itself becomes a new hierarchy boundary. It must specify the classes or interfaces **permitted to directly `implements`/`extends Child`**.

```java
sealed interface Document permits EditableDocument {}

sealed interface EditableDocument extends Document
        permits TextDocument, SpreadsheetDocument {}

final class TextDocument implements EditableDocument {}
record SpreadsheetDocument(int rows) implements EditableDocument {}
```

There are two independent lists:

- `Document permits EditableDocument`: only `EditableDocument` may directly inherit `Document`.
- `EditableDocument permits TextDocument, SpreadsheetDocument`: only the two named types may directly implement `EditableDocument`.

`TextDocument` and `SpreadsheetDocument` do not need to appear in `Document.permits`, because they do **not directly** declare `implements Document`.

### 3.1. What must a direct subtype of `sealed interface` at the next tier do?

| Direct subtype of `EditableDocument` | Valid hierarchy directive |
| --- | --- |
| Subinterface | Declare `sealed` or `non-sealed`. |
| Regular class | Declare `final`, `sealed`, or `non-sealed`. |
| `record` | Allowed if in `permits`; records are implicitly `final`. |
| `enum` | Implicitly `final` or `sealed` depending on enum structure; must still be permitted. |

Thus, **a subinterface does not have the `final` option**, whereas a class directly implementing a sealed interface does. Do not mechanically apply all three class modifiers to interfaces.

### 3.2. Each `sealed` tier has its own `permits` list

Three-tier hierarchy example:

```java
sealed interface Node permits CompositeNode {}

sealed interface CompositeNode extends Node permits BranchNode {}

sealed interface BranchNode extends CompositeNode permits LeafNode {}

record LeafNode(String value) implements BranchNode {}
```

`Node` permits `CompositeNode`; `CompositeNode` permits `BranchNode`; `BranchNode` permits `LeafNode`. Each boundary controls only **its direct subtypes**, allowing multi-tier expansion while keeping every permitted branch explicit.

**Note:** A `sealed interface` must have at least one permitted direct subtype. If `permits` is omitted, Java can only infer them from eligible types declared **in the same compilation unit** (usually the same `.java` file); see Section 6.

## 4. Choosing `non-sealed`: opening the hierarchy branch from a subinterface

`non-sealed interface Child extends Parent` announces that `Child` **stops imposing `permits` restrictions on its own subtypes**. Other interfaces and classes can extend or implement `Child` under normal access, module, and inheritance rules.

```java
sealed interface Operation permits ReadOperation, WriteOperation {}

sealed interface ReadOperation extends Operation permits ReadById {}
non-sealed interface WriteOperation extends Operation {}

record ReadById(long id) implements ReadOperation {}

// Valid: extending the non-sealed branch with a regular interface.
interface BatchWrite extends WriteOperation {}

// Valid: class implementing that regular interface.
class InsertMany implements BatchWrite {}

// Valid: class directly implementing WriteOperation.
class UpdateOne implements WriteOperation {}
```

`Operation` remains `sealed`: not every new type can directly `implements Operation`. However, `InsertMany` and `UpdateOne` are accepted through the reopened `WriteOperation` branch.

### 4.1. Must a grandchild interface use `non-sealed`?

**No.** If its direct superinterface is `non-sealed`, a grandchild interface is declared normally:

```java
sealed interface Root permits OpenBranch {}

non-sealed interface OpenBranch extends Root {}

interface Grandchild extends OpenBranch {} // Valid
class GrandchildImpl implements Grandchild {} // Valid
```

Here, `Grandchild` does **not directly `extends Root`**, so it is not subject to the `sealed`/`non-sealed` requirement for direct subinterfaces of a sealed interface.

Conversely, the following is invalid:

```java
sealed interface Root permits OpenBranch {}
non-sealed interface OpenBranch extends Root {}

non-sealed interface Grandchild extends OpenBranch {}
// ERROR: Grandchild has no direct superinterface that is sealed.
```

`non-sealed` may only be declared on an interface that has **at least one direct superinterface that is `sealed`**. It is a modifier marking where a locked branch is **reopened**—not a keyword to sprinkle onto arbitrary interfaces.

### 4.2. Once a branch is opened, can it deliberately be sealed again?

**Yes.** A grandchild interface can declare itself `sealed` to establish a new boundary, even when its direct parent is `non-sealed`:

```java
sealed interface Event permits ExtensibleEvent {}
non-sealed interface ExtensibleEvent extends Event {}

// Create a new sealed branch under an open interface.
sealed interface AuditEvent extends ExtensibleEvent permits AuditCreated {}
record AuditCreated(String actor) implements AuditEvent {}
```

In this example, `ExtensibleEvent` does not restrict new types, while `AuditEvent` controls which types directly implement `AuditEvent`. An opened branch does not force all descendants to remain open forever.

## 5. Complete Java 17 example: locking one branch while opening another

Save the entire example below into **`HierarchyDemo.java`**; all types are in the same compilation unit and no preview features are used.

```java
sealed interface Request permits Query, Command {
    String describe();
}

// Restricted branch: only the two records below may implement Query.
sealed interface Query extends Request permits FindById, CountAll {}

// Open branch: new interfaces/implementing classes may be added.
non-sealed interface Command extends Request {}

// Records are implicitly final, so they validly implement Query directly.
record FindById(long id) implements Query {
    @Override
    public String describe() {
        return "FindById: " + id;
    }
}

record CountAll() implements Query {
    @Override
    public String describe() {
        return "CountAll";
    }
}

// No sealed/non-sealed needed: direct superinterface is Command (non-sealed).
interface BatchCommand extends Command {}

final class UpdateMany implements BatchCommand {
    @Override
    public String describe() {
        return "UpdateMany";
    }
}

public class HierarchyDemo {
    public static void main(String[] args) {
        Request[] requests = {
            new FindById(42),
            new CountAll(),
            new UpdateMany()
        };

        for (Request request : requests) {
            System.out.println(request.describe());
        }
    }
}
```

Compile and run:

```bash
javac --release 17 HierarchyDemo.java
java HierarchyDemo
```

Output:

```text
FindById: 42
CountAll
UpdateMany
```

Hierarchy diagram:

```text
Request (sealed; permits Query, Command)
├── Query (sealed; permits FindById, CountAll)
│   ├── FindById (record, implicitly final)
│   └── CountAll (record, implicitly final)
└── Command (non-sealed)
    └── BatchCommand (regular interface)
        └── UpdateMany (final class)
```

The key point is that `UpdateMany` does not appear in `Request.permits`, because it does not directly `implements Request`. It passes through `BatchCommand` and `Command`. `Request` can still serve as the common type for all three objects while restricting **the branches emerging directly from the root**.

## 6. `permits` conditions for subinterfaces

For a subinterface directly extending a sealed interface to be valid, you must check **inheritance relationship, permission, and declaration location** simultaneously.

### 6.1. `permits` must match the direct relationship

```java
sealed interface Transport permits RoadTransport {}
non-sealed interface RoadTransport extends Transport {}
```

Here `RoadTransport` appears in `Transport.permits` **and** directly `extends Transport`, so it is valid.

Two common mistakes:

```java
// Separate example; do not combine with the valid code above.
sealed interface Parent permits Allowed {}

non-sealed interface Allowed extends Parent {}
non-sealed interface NotAllowed extends Parent {} // ERROR: not permitted by Parent
```

```java
// Separate example.
interface Other {}
sealed interface Parent permits NotItsChild {} // ERROR: NotItsChild does not extend Parent
sealed interface NotItsChild extends Other permits Leaf {}
record Leaf() implements NotItsChild {}
```

Merely writing a name in `permits` does not create an inheritance relationship; the `extends` or `implements` clause creates that relationship.

### 6.2. `permits` can be omitted when the compiler can infer it

For direct types in the **same compilation unit**, Java 17 allows inferring the list:

```java
sealed interface Notification {}

sealed interface SystemNotification extends Notification {}
non-sealed interface UserNotification extends Notification {}

record Shutdown() implements SystemNotification {}
```

The compiler infers that `Notification` permits `SystemNotification` and `UserNotification`, and also infers that `SystemNotification` permits `Shutdown`. Inferred types must have canonical names and directly inherit/implement the corresponding sealed interface. You cannot omit `permits` and leave a sealed interface with zero permitted subtypes.

When subtypes reside in separate files, writing `permits` explicitly clarifies the hierarchy contract and is required when the compiler cannot infer from the same compilation unit.

### 6.3. Permitted types must share the module or package depending on project layout

Per JLS 17 §9.1.4:

| Environment where sealed interface is declared | Location constraint for permitted direct subtypes |
| --- | --- |
| **Named module** (with `module-info.java`) | Must belong to the **same module** as the parent sealed interface; may be in a different package in that module if access rules permit. |
| **Unnamed module** (applications not organized with named modules) | Must belong to the **same package** as the parent sealed interface. |

For example, two types in different packages **within the same named module** can form a valid sealed hierarchy, provided type names are accessible and `permits`/`extends` declarations align. In an unnamed-module application, you cannot directly extend a sealed interface from another package merely by adding the name to `permits`.

These package/module rules apply **to direct subtypes of a sealed interface**. Once a branch becomes `non-sealed`, subtypes of that branch follow normal Java accessibility rules; they are not forced into the same package/module **solely because of an indirect ancestor's sealedness**.

## 7. When a subinterface has multiple superinterfaces

Java allows an interface to `extends` multiple interfaces. If **at least one** direct superinterface is `sealed`, the subinterface must still declare `sealed` or `non-sealed`, and must be permitted by **all of its sealed direct superinterfaces**.

Valid example:

```java
sealed interface Printable permits PrintableAndExportable {}
sealed interface Exportable permits PrintableAndExportable {}

non-sealed interface PrintableAndExportable
        extends Printable, Exportable {}

class Report implements PrintableAndExportable {}
```

`PrintableAndExportable` must be named in both `Printable.permits` and `Exportable.permits`. Removing it from either list makes that inheritance relationship invalid even though the subinterface has `non-sealed`.

If a subinterface extends only regular or `non-sealed` interfaces, it **must not declare `non-sealed`** because it has no sealed direct superinterface. However, it can still choose `sealed` to introduce a new restriction.

## 8. Typical compilation errors and how to fix them

### Error A: Subinterface omits its hierarchy policy

```java
sealed interface Device permits MobileDevice {}
interface MobileDevice extends Device {} // Invalid
```

Fix: declare `sealed` and list its direct subtypes, or declare `non-sealed` if this branch is open to extension:

```java
sealed interface Device permits MobileDevice {}
non-sealed interface MobileDevice extends Device {} // Valid
```

### Error B: Using `final` on a subinterface

```java
sealed interface Service permits PaymentService {}
final interface PaymentService extends Service {} // Invalid
```

`final` blocks subclassing a **class**. For an interface, to close the list of direct subtypes use `sealed` with one or more valid subtypes; there is no `final interface`.

### Error C: Declaring `non-sealed` when the direct parent is not sealed

```java
interface Base {}
non-sealed interface Child extends Base {} // Invalid
```

Fix by removing `non-sealed` if you just need a regular interface:

```java
interface Base {}
interface Child extends Base {} // Valid
```

### Error D: Parent interface does not permit the subinterface

```java
sealed interface AuthMethod permits PasswordAuth {}
non-sealed interface PasswordAuth extends AuthMethod {}
non-sealed interface TokenAuth extends AuthMethod {} // Invalid
```

Fix by adding `TokenAuth` to `AuthMethod.permits` if it genuinely belongs to the direct branches the design intends to support:

```java
sealed interface AuthMethod permits PasswordAuth, TokenAuth {}
non-sealed interface PasswordAuth extends AuthMethod {}
non-sealed interface TokenAuth extends AuthMethod {}
```

This is an API design decision, not just a trick to make the compiler stop complaining. Expanding `permits` expands the set of cases covered by the parent interface's hierarchy contract.

## 9. When to choose `sealed` vs. `non-sealed` for a subinterface

| Context | Usually appropriate choice | Reason |
|---|---|---|
| System has a tightly managed set of business variants, such as internal result or command kinds | `sealed interface Child` | Keeps the list of direct variants explicit. |
| Wanting to lock root branches while letting a feature team add custom types | `non-sealed interface Child` | Opens an intentional extension point while keeping root branches controlled. |
| Building a sub-layer under a `non-sealed interface` without wanting extra restrictions | Regular `interface Grandchild` | Has no sealed direct superinterface, so `non-sealed` is neither needed nor allowed. |
| A part of an open branch needs to return to a restricted set of variants | `sealed interface Grandchild` | Can deliberately introduce a new `permits` boundary. |

Choose `sealed` when you **know the direct subtypes** and want to govern adding variants; choose `non-sealed` when the API's intent is to let other teams extend that branch. Either way, type visibility (`public`, package-private), module scope, and API constraints still apply.

## 10. Practice exercises

**Exercise 1 — Determine validity**

Which snippets are valid and why?

```java
sealed interface Media permits Audio {}
sealed interface Audio extends Media permits Song {}
record Song(String title) implements Audio {}
```

```java
sealed interface Media permits Audio {}
interface Audio extends Media {}
```

```java
sealed interface Media permits Audio {}
non-sealed interface Audio extends Media {}
interface Podcast extends Audio {}
```

Hint: check in order: `permits`, direct `extends`/`implements` relationship, and then the subinterface's modifier.

**Exercise 2 — Open one branch and lock one branch**

Design a `sealed interface Payment` with two subinterfaces:

- `CardPayment` permits only predefined implementation types.
- `CustomPayment` lets other teams create custom payment kinds.

Choose the modifier for each branch, write appropriate `permits` clauses, then add a record for `CardPayment` and a regular grandchild interface under `CustomPayment`.

**Exercise 3 — Check a multi-tier hierarchy**

Given `Root (sealed) → Open (non-sealed) → Mid (regular interface) → Leaf (regular interface)`. Answer: must `Leaf` appear in `Root.permits`? Does `Mid` need `non-sealed`? To restrict direct subtypes of `Mid`, how should `Mid`'s declaration be changed?

**Exercise 4 — Multiple parent interfaces**

Write two `sealed interface A` and `B`, both permitting `non-sealed interface Both extends A, B`. Try removing `Both` from one of the two `permits` lists and predict the error based on JLS rules.

## 11. Official references for deeper lookup

- [JLS Java SE 17 §9.1.1.4 — `sealed` and `non-sealed` Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.1.4): modifier requirements for an interface with a sealed direct superinterface.
- [JLS Java SE 17 §9.1.3 — Superinterfaces and Subinterfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.3): how direct superinterfaces and inheritance relationships are determined.
- [JLS Java SE 17 §9.1.4 — Permitted Direct Subclasses and Subinterfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.4): `permits` list, `permits` inference, and module/package limits.
- [JLS Java SE 17 §8.1.1.2 — `sealed`, `non-sealed`, and `final` Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.1.2): comparing rules for classes directly implementing a sealed interface.
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): design motivation and finalized status in JDK 17.

When reading a sealed hierarchy in Java 17, walk **one direct inheritance edge at a time**: does the parent permit the child, does the child declare `sealed` or `non-sealed`, and if the child remains `sealed`, which types are permitted at the next tier. Doing so accurately pinpoints which parts of the hierarchy are restricted and which are open for extension.
