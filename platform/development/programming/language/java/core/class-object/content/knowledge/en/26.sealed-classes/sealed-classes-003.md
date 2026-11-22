# Conditions for Inferring the Subclass List When Omitting `permits` in Java `sealed`

## 1. Central Question

Java 17 allows declaring a **`sealed`** class or interface to restrict which types may directly extend or implement it. You can explicitly specify the subtype list in `permits`:

```java
sealed interface Message permits TextMessage, ImageMessage {
}

record TextMessage(String text) implements Message {
}

record ImageMessage(String path) implements Message {
}
```

However, when the direct subtypes are declared **in the same compilation unit**, you can omit the `permits` clause:

```java
sealed interface Message {
}

record TextMessage(String text) implements Message {
}

record ImageMessage(String path) implements Message {
}
```

The two snippets above are **independent illustrative declaration options**; do not place both in the same file.

**Core inference condition:** When a `sealed` type **does not specify `permits`**, Java infers the permitted list from the **direct subtypes** that **have a canonical name** and **are declared in the same compilation unit** as the sealed type. If no suitable direct subtype can be found, a sealed declaration missing `permits` is a **compile-time error** (except for the special mechanism for enums, not the ordinary sealed classes/interfaces examined in this article).

In short:

- **Same source file/compilation unit:** required for inference.
- **Direct inheritance or implementation relationship:** required for inference.
- **Subtype with a canonical name:** required for inference.
- **Subtype declaring `final`, `sealed`, or `non-sealed` appropriately:** still mandatory under sealed hierarchy rules.
- **Same package or same module but in different files:** not sufficient for automatic inference.
- **Indirect subclasses, local classes, and anonymous classes:** not automatically inferred.

This article explains the conditions step by step, compilable Java 17+ examples, intentionally invalid cases, a comparison of explicit/inferred `permits`, package/module scope, and how to check at runtime.

## 2. Distinguishing Sealed Classes, Sealed Interfaces, and `permits`

Sealed class example:

```java
sealed abstract class Shape permits Circle, Rectangle {
}

final class Circle extends Shape {
}

final class Rectangle extends Shape {
}
```

Sealed interface example:

```java
sealed interface Command permits Start, Stop {
}

record Start() implements Command {
}

record Stop() implements Command {
}
```

Both are **illustrative declaration snippets**.

- A `sealed class` restricts the **direct subclasses** that can `extends` the class.
- A `sealed interface` restricts the **direct subclasses/direct subinterfaces** that can directly `implements` or `extends` the interface.
- `permits` is the list of **permitted direct subtypes**, not the list of all descendants.
- When **`permits` is absent**, the compiler infers the list if the conditions are met.
- When **`permits` is present**, the compiler uses the **explicitly enumerated** list and does not automatically merge in every type in the same file.

**Key point:** Omitting `permits` does not mean a sealed type becomes an unrestricted class or interface for any subtype to inherit from. The sealed type **remains closed with respect to its list of direct subtypes**.

## 3. Complete Example: The Compiler Infers Two Direct Subclasses

Create the file **`InferredPermitsClassDemo.java`**:

```java
sealed abstract class Shape {
    abstract int area();
}

final class Square extends Shape {
    private final int side;

    Square(int side) {
        this.side = side;
    }

    @Override
    int area() {
        return side * side;
    }
}

final class Rectangle extends Shape {
    private final int width;
    private final int height;

    Rectangle(int width, int height) {
        this.width = width;
        this.height = height;
    }

    @Override
    int area() {
        return width * height;
    }
}

public class InferredPermitsClassDemo {
    public static void main(String[] args) {
        Shape first = new Square(3);
        Shape second = new Rectangle(2, 5);

        System.out.println(first.area());
        System.out.println(second.area());
    }
}
```

```bash
javac InferredPermitsClassDemo.java
java InferredPermitsClassDemo
```

```text
9
10
```

Here the compiler infers `Square` and `Rectangle` because:

1. `Shape` is declared as `sealed`.
2. The Shape declaration does not write `permits`.
3. `Square` and `Rectangle` are declared **in the same Java file** as Shape.
4. Both have canonical names because they are top-level classes.
5. Both `extends Shape` **directly**.
6. Both are `final`, satisfying a valid choice for the direct subclass modifier.

**Not due to being implicitly in the same package:** Although being in the same file naturally means being in the same package, being in the **same compilation unit** is the decisive condition for inference.

## 4. Complete Example: Sealed Interface Without `permits`

Create the file **`InferredPermitsInterfaceDemo.java`**:

```java
sealed interface PaymentResult {
    String description();
}

record Paid(String reference) implements PaymentResult {
    @Override
    public String description() {
        return "paid:" + reference;
    }
}

record Declined(String reason) implements PaymentResult {
    @Override
    public String description() {
        return "declined:" + reason;
    }
}

public class InferredPermitsInterfaceDemo {
    public static void main(String[] args) {
        PaymentResult a = new Paid("TX-7");
        PaymentResult b = new Declined("limit");

        System.out.println(a.description());
        System.out.println(b.description());
    }
}
```

```bash
javac InferredPermitsInterfaceDemo.java
java InferredPermitsInterfaceDemo
```

```text
paid:TX-7
declined:limit
```

The compiler identifies `Paid` and `Declined` as **two classes that directly implement `PaymentResult`**, have canonical names, and are declared in the same compilation unit.

**Why does `record` work?** A record class is `final` by default, so it can serve as a direct permitted implementation of a sealed interface. The record only needs to declare `implements PaymentResult` and provide the method required by the interface.

A sealed **interface** can have both direct implementing classes and direct extending interfaces. The inference conditions consider both of those kinds, not just `record`.

## 5. What Is a “Compilation Unit” in Ordinary Situations?

An **ordinary compilation unit** corresponds to a Java source file containing top-level declarations and potentially containing nested types. For example, the file `Workflow.java` has:

```java
sealed interface Workflow {
}

final class Manual implements Workflow {
}

final class Automated implements Workflow {
}
```

The three types are declared in the same source file, so they satisfy the **same compilation unit** condition.

### What Is Not Sufficient

Two files in the **same directory/package**:

```text
src/example/Workflow.java
src/example/Manual.java
```

are not in the same compilation unit. When Workflow omits `permits`, the compiler does not automatically find Manual from another file and add it to the list, even if the build system compiles both files at the same time.

**Watch the wording:** “In the same `javac` run” does not mean “in the same compilation unit.” The command `javac A.java B.java` loads two different compilation units; it does not combine them into one.

## 6. Same Package but Different Files Still Requires Explicit `permits`

Suppose a design places the sealed interface and its implementations into three files in the `demo` package:

```text
demo/
  Operation.java
  Add.java
  Subtract.java
```

File **`demo/Operation.java`**:

```java
package demo;

public sealed interface Operation permits Add, Subtract {
    int apply(int a, int b);
}
```

File **`demo/Add.java`**:

```java
package demo;

public final class Add implements Operation {
    @Override
    public int apply(int a, int b) {
        return a + b;
    }
}
```

File **`demo/Subtract.java`**:

```java
package demo;

public final class Subtract implements Operation {
    @Override
    public int apply(int a, int b) {
        return a - b;
    }
}
```

In the root directory containing the `demo` folder, compile:

```bash
javac demo/Operation.java demo/Add.java demo/Subtract.java
```

This trio of files **compiles validly** on Java 17+. The names `Add` and `Subtract` can be listed in `permits` because they are direct implementations, are accessible, and are in the same package in the unnamed module.

If you remove `permits Add, Subtract` from `Operation.java` without moving the subtype declarations into the **same compilation unit**, the code no longer satisfies the inference conditions. The compiler does not use “two classes already available in the package” to infer them.

**Distinction:** The package/module co-location rule for permitted relationships in general **does not replace** the compilation-unit co-location rule specific to **omitting `permits`**.

## 7. A Compilation Unit Can Contain Multiple Top-Level Types

Java allows one file to contain multiple top-level declarations, provided it follows the filename rule for a top-level `public` type.

Create **`ManyTopLevelTypesDemo.java`**:

```java
sealed interface Message {
}

final class Text implements Message {
}

final class Image implements Message {
}

final class Video implements Message {
}

public class ManyTopLevelTypesDemo {
    public static void main(String[] args) {
        Message message = new Video();

        System.out.println(message instanceof Video);
        System.out.println(Message.class.isSealed());
    }
}
```

```bash
javac ManyTopLevelTypesDemo.java
java ManyTopLevelTypesDemo
```

```text
true
true
```

The three classes `Text`, `Image`, and `Video` are all inferred as permitted. They are top-level non-public types in the same compilation unit as Message. There is no need to write `permits Text, Image, Video`.

**Code organization note:** Having multiple top-level classes share a file is valid, which does not mean it is always good for maintainability. If each implementation is large and needs its own file, using explicit `permits` is clear and may be necessary.

## 8. Nested Types (*member nested type*) Can Also Be Inferred

A nested class has a **canonical name**, for example `Envelope.Letter`, if it is a validly declared member class. It can reside in the same compilation unit and directly implement a sealed interface.

Create **`NestedPermittedTypesDemo.java`**:

```java
sealed interface Message {
}

public class NestedPermittedTypesDemo {
    static final class Text implements Message {
    }

    static final class Binary implements Message {
    }

    public static void main(String[] args) {
        Message a = new Text();
        Message b = new Binary();

        System.out.println(a instanceof Text);
        System.out.println(b instanceof Binary);
    }
}
```

```bash
javac NestedPermittedTypesDemo.java
java NestedPermittedTypesDemo
```

```text
true
true
```

Although `Text` and `Binary` are not top-level classes, they are **member nested classes** that have canonical names, are in the same compilation unit, and directly implement Message. Therefore, they are inferred.

**Do not oversimplify the rule to “only top-level classes in the same file.”** More accurately: types that have a canonical name, belong to the same compilation unit, and have the corresponding direct subclass/subinterface relationship.

## 9. Subtypes Can Be Declared Directly Inside the Sealed Type

Create **`NestedInsideSealedDemo.java`**:

```java
sealed interface Event {
    record Started(String id) implements Event {
    }

    record Finished(String id) implements Event {
    }
}

public class NestedInsideSealedDemo {
    public static void main(String[] args) {
        Event first = new Event.Started("A");
        Event second = new Event.Finished("A");

        System.out.println(first);
        System.out.println(second);
    }
}
```

```bash
javac NestedInsideSealedDemo.java
java NestedInsideSealedDemo
```

```text
Started[id=A]
Finished[id=A]
```

The two records `Event.Started` and `Event.Finished` are declared inside the body of the sealed interface, lie in the same compilation unit, have canonical names, and directly implement Event.

**Why is this example beneficial?** The reader sees the complete set of variants close to the parent declaration. This is a case where omitting `permits` often makes the file very easy to understand.

A nested record is implicitly static in Java and does not capture an Event object; it is a separate type declaration implementing the Event interface.

## 10. A Sealed Class Can Have Nested Final Classes

Create **`SealedClassNestedChildrenDemo.java`**:

```java
sealed abstract class Result {
    abstract String text();

    static final class Success extends Result {
        @Override
        String text() {
            return "SUCCESS";
        }
    }

    static final class Failure extends Result {
        @Override
        String text() {
            return "FAILURE";
        }
    }
}

public class SealedClassNestedChildrenDemo {
    public static void main(String[] args) {
        Result a = new Result.Success();
        Result b = new Result.Failure();

        System.out.println(a.text());
        System.out.println(b.text());
    }
}
```

```bash
javac SealedClassNestedChildrenDemo.java
java SealedClassNestedChildrenDemo
```

```text
SUCCESS
FAILURE
```

The two nested classes have canonical names `Result.Success` and `Result.Failure`, are in the same compilation unit, and `extends Result` directly, so they are inferred.

**Do not confuse access modifiers with inference:** Although a member class can be private/package-private/public depending on the context, the key requirement here is that the type is validly declared and has a canonical name, not that every child must be a public top-level class.

## 11. What Exactly Does “Direct Child” of a Class Mean?

Given:

```java
sealed class Base {
}

non-sealed class Middle extends Base {
}

final class End extends Middle {
}
```

These three declarations are valid if they are in the same compilation unit and Base does not have `permits`.

**The inferred list of Base contains only `Middle`.**

- `Middle extends Base` → direct subclass.
- `End extends Middle` → indirect subclass of Base.
- `End` is not a direct child of Base, so it is not added to the inferred permitted set.

This still holds even though all three are in the same file.

### Why Is This Distinction Necessary?

`sealed` restricts the **direct branching points** from the parent. If a child is `non-sealed`, the sub-branch below it can be extended normally. If the child is `sealed`, it continues to restrict its own direct subclasses.

## 12. Runnable: Direct Is Inferred, Indirect Is Not Inferred

Create **`DirectVersusIndirectDemo.java`**:

```java
sealed abstract class Base {
}

non-sealed class Middle extends Base {
}

final class Leaf extends Middle {
}

public class DirectVersusIndirectDemo {
    public static void main(String[] args) {
        Base value = new Leaf();

        System.out.println(value instanceof Middle);
        System.out.println(value instanceof Leaf);
    }
}
```

```bash
javac DirectVersusIndirectDemo.java
java DirectVersusIndirectDemo
```

```text
true
true
```

Both Middle and Leaf are instances/subtypes related to Base along the inheritance chain. However, the **permitted direct subclasses** of Base consist only of Middle. Leaf does not need to be directly permitted by Base because it `extends Middle`, and Middle is non-sealed.

**Note:** An indirect subtype does not automatically violate the sealed contract. What must be checked is whether **every direct inheritance edge** passing through a sealed parent is permitted.

## 13. With a Sealed Interface, Both Classes and Interfaces Can Be Direct Children

Create **`SealedInterfaceMixedChildrenDemo.java`**:

```java
sealed interface Resource {
}

final class LocalResource implements Resource {
}

non-sealed interface RemoteResource extends Resource {
}

final class HttpResource implements RemoteResource {
}

public class SealedInterfaceMixedChildrenDemo {
    public static void main(String[] args) {
        Resource local = new LocalResource();
        Resource remote = new HttpResource();

        System.out.println(local instanceof LocalResource);
        System.out.println(remote instanceof RemoteResource);
    }
}
```

```bash
javac SealedInterfaceMixedChildrenDemo.java
java SealedInterfaceMixedChildrenDemo
```

```text
true
true
```

The compiler infers `LocalResource` (a class that directly implements Resource) and `RemoteResource` (an interface that directly extends Resource). `HttpResource` only directly implements RemoteResource, so it does not need to appear in the inferred permitted set of Resource.

**Distinction:** A `non-sealed interface` can reopen the branch for subsequent implementations. It must still be a valid direct permitted subinterface of Resource.

## 14. Direct Implementation Does Not Depend on Whether the Class Also Extends Another Class

A class can both `extends` an ordinary superclass and directly `implements` a sealed interface. In that case, it is still a **direct subclass under the interface relationship**.

Example:

```java
sealed interface Tag {
}

class BaseObject {
}

final class TaggedObject extends BaseObject implements Tag {
}
```

This is a **valid declaration**, if in the same compilation unit.

`TaggedObject` does not extend Tag (Tag is an interface), but `implements Tag` **directly**, so it is inferred when Tag omits permits. The fact that it also extends BaseObject does not make Tag an indirect relationship.

For a sealed **class**, the compiler checks that the direct superclass is the exact sealed class; an interface implementer is not a direct subclass of a sealed class.

## 15. What Is a “Canonical Name” and Why Is It Required?

A named top-level class has a canonical name such as `package.Type`. A member nested type has a canonical name such as `package.Outer.Nested`.

In contrast:

- A **local class** declared inside a method/block does not have a canonical name.
- An **anonymous class** created with `new SomeType() { ... }` does not have a canonical name.
- A local interface (in modern Java contexts where it is permitted) also does not have a canonical name.

When permits is absent, types without a canonical name **cannot belong to the inferred permitted set**.

### This Is Not Merely a Name Visibility Limitation

A local class can have a simple name within a block, for example `Local`. However, a **simple name is not a canonical name**. The JLS requirement is a canonical name, not “having a name to type inside a method.”

## 16. Why Is a Local Class Not Automatically Inferred?

This is **intentionally invalid code** that does not compile:

```java
sealed interface Task {
}

class Factory {
    static Task create() {
        final class LocalTask implements Task {
        }

        return new LocalTask();
    }
}
```

`LocalTask` is declared inside a method and does not have a canonical name. It cannot become a permitted direct implementation simply by appearing in the same file.

In addition, `Task` has no other valid permitted direct implementation, so the sealed declaration lacking permits is itself an error as well.

**How to fix:** Use a top-level or member nested type that has a canonical name, or choose an interface design that is not sealed if you need flexible local implementations.

## 17. Anonymous Classes Are Also Not Allowed to Bypass the Condition

The following code is **intentionally invalid**:

```java
sealed interface Task {
    void run();
}

class Factory {
    static Task create() {
        return new Task() {
            @Override
            public void run() {
                System.out.println("RUN");
            }
        };
    }
}
```

An anonymous class does not have a canonical name, cannot be inferred from the same compilation unit, and cannot be validly named in `permits`.

**Do not assume:** “If you omit `permits`, any anonymous implementation in the same file is allowed.” On the contrary, sealed is an intentional restriction, and an anonymous implementation does not satisfy the permitted direct type rules.

If you want a one-off callback implementation, you can use a named permitted class/record and then instantiate that class; if the domain needs countless anonymous implementations, reconsider using a sealed interface.

## 18. If No Suitable Direct Subtype Exists, the Compiler Reports an Error

This snippet is **intentionally invalid**:

```java
sealed interface EmptyHierarchy {
}
```

There is no `permits` and no suitable subtype in the same compilation unit. The compiler rejects it because it cannot infer a nonempty permitted direct set.

Similarly for:

```java
sealed class Lonely {
}
```

An ordinary sealed class (not the special enum case) lacking permits and having no valid direct subclasses is a **compile-time error**.

### The Right Approach If You Want to Forbid Subclasses Completely

If you only need a class **without any subclasses**, use a `final class` instead of a sealed class with no permitted child:

```java
final class NoSubclasses {
}
```

If you need a true sealed hierarchy, declare at least one corresponding direct permitted type.

## 19. The Modifier on a Direct Permitted Child Is Still Mandatory

Omitting `permits` only omits **listing the names**. It does not remove the requirement that a direct permitted subclass/subinterface explicitly declare its inheritance continuation policy.

A direct permitted **class** must normally be one of:

- `final`: forbids further subclassing.
- `sealed`: continues closing the list of direct children.
- `non-sealed`: reopens subclassing under the usual rules.

For a direct permitted **interface**, use `sealed` or `non-sealed` (an interface cannot be `final`).

If the direct child is a record, a record is final and therefore satisfies the branch-closing policy.

**Note:** `abstract` does not replace `sealed`/`non-sealed` on a direct permitted subtype when the rules require a policy modifier; you can combine abstract with sealed or non-sealed on a class when valid.

## 20. Error When Forgetting `final`/`sealed`/`non-sealed`

This is **intentionally invalid code**:

```java
sealed class Parent {
}

class Child extends Parent {
}
```

Although Child is in the same compilation unit and is inferred by name, it **does not declare the extension policy** that Java requires for a direct permitted class.

Fix:

```java
sealed class Parent {
}

final class Child extends Parent {
}
```

These are **two separate options**; do not declare them twice in the same source.

Or use `non-sealed class Child extends Parent` if you genuinely want other descendants to extend under Child, or `sealed class Child` if Child continues to close the branch with its own valid direct subclasses.

## 21. Inference and the `sealed -> sealed -> final` Chain

Create **`MultiLevelSealedDemo.java`**:

```java
sealed abstract class Root {
    abstract String label();
}

sealed abstract class Branch extends Root {
}

final class LeafA extends Branch {
    @Override
    String label() {
        return "A";
    }
}

final class LeafB extends Branch {
    @Override
    String label() {
        return "B";
    }
}

public class MultiLevelSealedDemo {
    public static void main(String[] args) {
        Root a = new LeafA();
        Root b = new LeafB();

        System.out.println(a.label());
        System.out.println(b.label());
    }
}
```

```bash
javac MultiLevelSealedDemo.java
java MultiLevelSealedDemo
```

```text
A
B
```

There are **two distinct inference processes**:

- `Root` has no permits, so it infers **Branch** because Branch directly extends Root.
- `Branch` has no permits, so it infers **LeafA, LeafB** because they directly extend Branch.

Root **does not directly permit LeafA and LeafB**. However, Root references can still point to LeafA/LeafB objects because they are indirect descendants through the permitted Branch.

**A multi-level sealed hierarchy must be examined edge by direct edge**, rather than forming a flat list of all terminal classes.

## 22. If a Direct Child Is `non-sealed`, That Branch Opens Up

Create **`NonSealedBranchDemo.java`**:

```java
sealed interface Device {
}

non-sealed class Computer implements Device {
}

final class Laptop extends Computer {
}

public class NonSealedBranchDemo {
    public static void main(String[] args) {
        Device device = new Laptop();

        System.out.println(device instanceof Computer);
        System.out.println(device instanceof Laptop);
    }
}
```

```bash
javac NonSealedBranchDemo.java
java NonSealedBranchDemo
```

```text
true
true
```

The compiler infers `Computer` as the direct permitted implementation of Device. `Laptop` does not directly implement Device; it inherits Device through Computer. Because Computer is `non-sealed`, it allows extension according to ordinary inheritance rules.

**No contradiction:** Device remains sealed even though indirectly many implementations pass through the non-sealed branch. Sealed only checks the direct children of each sealed type.

## 23. A Direct Implementation in the Same File Is Enough; It Does Not Need the Same Block

The condition is being in the same **compilation unit**, not necessarily that the declarations be adjacent or in the same lexical block.

Example:

```java
sealed interface Signal {
}

class Holder {
    static final class On implements Signal {
    }
}

final class Off implements Signal {
}
```

Here `Holder.On` and `Off` are both named types with canonical names, in the same compilation unit, directly implementing Signal. Both are inferred even though one is nested inside Holder and one is top-level.

**Key takeaway:** It is not “near the sealed declaration in the source” that makes it permitted; the compiler examines the set of declarations in the same compilation unit that satisfy the exact conditions.

## 24. Not Every Class in the Same File Belongs to the Inferred List

Suppose we have:

```java
sealed interface Command {
}

final class Start implements Command {
}

final class Other {
}

final class ExtendedStart {
}
```

Only `Start` is a direct implementation of Command. `Other` and `ExtendedStart` do not extend/implement Command, so they are not inferred.

The compiler does not list every named class in the same file. It filters by the **direct inheritance/implementation relationship**.

## 25. When `permits` Is Explicit, the Inferred Set Is Not Added

This is **intentionally invalid code**:

```java
sealed interface Choice permits A {
}

final class A implements Choice {
}

final class B implements Choice {
}
```

Although B is in the same compilation unit, has a canonical name, and directly implements Choice, it **is not listed in the explicit permits**. The compiler rejects B.

If you want B to be permitted, change the declaration to:

```java
sealed interface Choice permits A, B {
}
```

Or **omit the entire permits clause** when A and B are both in the same compilation unit; the compiler will then infer both.

**Do not confuse the two modes:** Without permits, inference happens from the same unit. With permits, the explicit list is used and is not automatically expanded.

## 26. `permits` Cannot List an Indirect Subtype

The following code is **invalid**:

```java
sealed class Root permits Leaf {
}

non-sealed class Branch extends Root {
}

final class Leaf extends Branch {
}
```

`Leaf` is an indirect subclass of Root, so it cannot be listed as a **direct permitted subclass** of Root. If Root wants to close the Branch branch, declare:

```java
sealed class Root permits Branch {
}

non-sealed class Branch extends Root {
}

final class Leaf extends Branch {
}
```

If the three declarations are in the same compilation unit, you can also omit `permits Branch` so that the compiler infers Branch. `Leaf` is still not in the direct permitted set.

**Why is precision necessary?** `permits` is not a list of “every class that can exist under the root.” It describes the **direct paths** opened from a sealed node.

## 27. Differences Between Sealed Classes and Sealed Interfaces During Inference

| Aspect | Sealed class | Sealed interface |
| --- | --- | --- |
| Declaration syntax | `sealed class C` | `sealed interface I` |
| Direct relationship examined | `extends C` | Direct `implements I` or `extends I` |
| Possible subtypes | Classes | Classes and subinterfaces |
| Without permits | Infers direct classes in the same compilation unit that have a canonical name | Infers direct classes/interfaces in the same compilation unit that have a canonical name |
| No suitable direct subtype | Compile-time error (normal sealed class) | Compile-time error |
| Local/anonymous types | Not inferred | Not inferred |
| Indirect children | Not inferred into the direct set | Not inferred into the direct set |
| Direct child modifier | `final` / `sealed` / `non-sealed` | Classes: same; interfaces: `sealed` / `non-sealed` |
| Adding a subtype from another compilation unit while omitting permits | No | No |

This table applies to **ordinary sealed classes/interfaces of Java 17+**. Enums have their own rules regarding constant-specific classes and implicit final/sealed semantics, which are not the typical `sealed class ...` case covered in this article.

## 28. Package and Module: Two Different Layers of Conditions

Java also constrains the location of direct permitted types:

- If the sealed type belongs to a **named module**, permitted direct types must be in the **same module**.
- If the sealed type belongs to an **unnamed module**, permitted direct types must be in the **same package**.

However, for **omitting permits**, a stronger requirement is needed: the **same compilation unit**. Being in the same module/package cannot substitute for it.

### Conceptual Example

```text
module app.core
  package app.core.model
    Result.java
    Success.java
    Failure.java
```

Suppose all three classes belong to the named module `app.core`. Being in the same module only makes them **capable of** satisfying the module-level condition of explicit permits. When Result, Success, and Failure are in **three compilation units**, Result cannot omit permits and expect the compiler to infer across the whole module.

**Good approach:** Keep `sealed interface Result permits Success, Failure` in Result's file, or move the direct descendants into the same compilation unit if you want inference.

## 29. “Compiling Together” Does Not Turn Multiple Source Files into One Compilation Unit

A common misconception:

> I ran `javac Root.java Child.java`, so can the compiler infer Child for Root?

**No.** Javac accepting multiple source files in the same invocation does not change the **compilation unit** boundary of each file.

Example:

```text
Root.java
Child.java
```

`Root.java`:

```java
sealed interface Root {
}
```

`Child.java`:

```java
final class Child implements Root {
}
```

These are **two files of an intentionally invalid example**, because Root lacks direct subtypes **inside Root.java itself**.

Fix `Root.java`:

```java
sealed interface Root permits Child {
}
```

Keep `Child.java` as before; with the same package (unnamed module) and explicit permits for Child, it compiles.

**Do not conflate** the concepts of “same compilation,” “same directory,” “same module,” and “same compilation unit.”

## 30. The `canonical name` Condition Excludes Local/Anonymous Types Even in the Same Source

A local class can have a **simple name**, for example `Worker` inside a method:

```java
void create() {
    class Worker {
    }
}
```

However, it does not have a canonical name in Java. An anonymous class does not even have a simple source-level class name.

Therefore:

- Same file: **yes**.
- Direct `implements SealedInterface`: one can attempt to write it.
- Has a canonical name: **no**.
- Result: **does not meet the inference conditions**, and directly subtyping the sealed type is not allowed.

This is the distinction between a **lexical name** and a **canonical name**; it is not simply “the compiler has not seen the type yet.”

## 31. When You Want a Local Implementation, What Design Options Exist?

If the logic is only used inside one method, yet the parent sealed interface requires a permitted named type, consider:

1. Declaring a **private static nested class** (which has a canonical name) inside a class in the same compilation unit as the sealed parent, if it suits visibility and architecture.
2. Declaring a **nested record** inside the corresponding sealed interface/class if it is a data variant with suitable immutable state.
3. Declaring a **top-level final class** in the same source file so that inference is valid.
4. Keeping the implementation in a separate file and using explicit `permits`.
5. If you genuinely must create arbitrary anonymous implementations in many places, reconsider using `sealed`: an ordinary interface or a strategy registry may be more appropriate.

**Do not try to use reflection or casting** to bypass the compiler. A sealed hierarchy also enforces corresponding runtime/linkage constraints; the extension path must be a properly designed API.

## 32. Checking at Runtime with `Class.isSealed()`

Java 17 provides a reflection API to tell whether a class/interface is sealed.

Create **`SealedReflectionDemo.java`**:

```java
sealed interface Event {
}

record Started(String id) implements Event {
}

record Finished(String id) implements Event {
}

public class SealedReflectionDemo {
    public static void main(String[] args) {
        System.out.println(Event.class.isSealed());
        System.out.println(Started.class.isSealed());
        System.out.println(Finished.class.isSealed());
    }
}
```

```bash
javac SealedReflectionDemo.java
java SealedReflectionDemo
```

```text
true
false
false
```

Event is sealed; the two records are final, not sealed, so isSealed is false.

**Reflection helps inspect type structure; it does not replace compile-time validation**. It does not add types to the allowed list and does not cause a class in another file to be inferred.

## 33. Observing Permitted Direct Types with `getPermittedSubclasses()`

In Java 17, `Class.getPermittedSubclasses()` reports the types **directly permitted** by a sealed type.

Create **`InferredPermitsReflectionDemo.java`**:

```java
import java.util.Arrays;

sealed interface Event {
}

record Started(int id) implements Event {
}

record Finished(int id) implements Event {
}

public class InferredPermitsReflectionDemo {
    public static void main(String[] args) {
        String[] names = Arrays.stream(
                        Event.class.getPermittedSubclasses())
                .map(Class::getSimpleName)
                .sorted()
                .toArray(String[]::new);

        System.out.println(Arrays.toString(names));
        System.out.println(
                Event.class.getPermittedSubclasses().length);
    }
}
```

```bash
javac InferredPermitsReflectionDemo.java
java InferredPermitsReflectionDemo
```

```text
[Finished, Started]
2
```

The program **sorts the names before printing**, without relying on a reflection order unnecessary for the knowledge in this article. The list consists of direct permitted classes, not all descendants.

For a non-sealed `Class`, `getPermittedSubclasses()` returns `null` per the API; when writing generic reflection code, you need to check for null before iterating.

## 34. Reflection: Direct vs. Indirect in an Inheritance Chain

Create **`SealedHierarchyReflectionDemo.java`**:

```java
import java.util.Arrays;

sealed abstract class Root {
}

sealed class Branch extends Root {
}

final class Leaf extends Branch {
}

public class SealedHierarchyReflectionDemo {
    static String permitted(Class<?> type) {
        return Arrays.toString(
                Arrays.stream(type.getPermittedSubclasses())
                        .map(Class::getSimpleName)
                        .sorted()
                        .toArray(String[]::new));
    }

    public static void main(String[] args) {
        System.out.println(permitted(Root.class));
        System.out.println(permitted(Branch.class));
    }
}
```

```bash
javac SealedHierarchyReflectionDemo.java
java SealedHierarchyReflectionDemo
```

```text
[Branch]
[Leaf]
```

The two lists are not the same:

- Root directly permits Branch.
- Branch directly permits Leaf.
- Leaf is an **indirect subclass of Root** and does not belong to Root.getPermittedSubclasses().

**Note:** The `permitted` method in the demo is only called with sealed types, so it does not handle a null result. In a reusable library, you must check `type.isSealed()` or null first.

## 35. `permits` Is Not a Feature Applicable to Every Class/Interface

An ordinary class that is not sealed cannot use permits to list subclasses:

```java
// class Open permits A, B { } // Invalid.
```

A `final` type forbids inheritance and cannot simultaneously be sealed under ordinary Java class syntax:

```java
// final sealed class Invalid { } // Invalid.
```

For an ordinary class hierarchy, `sealed` protects the **direct subtype set**; `permits` is a supporting clause that can be explicit or inferred when the same-compilation-unit conditions are satisfied.

## 36. The Compiler Infers from Declarations, Without Needing Object Creation

A sealed hierarchy is **information about types** and does not depend on how many instances have been created.

Example:

```java
sealed interface Marker {
}

final class One implements Marker {
}

final class Two implements Marker {
}
```

Even if the program **never calls `new One()` or `new Two()`**, the compiler still infers the two types if they are in the same compilation unit.

**Do not confuse:** “Permitted subtypes” is a compile/link-time rule for the type hierarchy; it is not the set of objects that have appeared on the heap.

## 37. Declaration Order of Subtypes in the File Is Not an Essential Condition

Top-level declarations in a compilation unit can reference one another according to Java name resolution. It is not mandatory to place the sealed parent before all children for inference to happen.

Example:

```java
final class Done implements State {
}

sealed interface State {
}
```

These are **two illustrative top-level declarations** in the same compilation unit, valid under the inference conditions. `Done` directly implements State and has a canonical name.

**The condition is the declaration relationship and the unit, not top/bottom line position in the file**. However, placing the parent before the children is usually easier for learners to read.

## 38. Nested Types Deeper Than One Level Still Have a Canonical Name

Example:

```java
sealed interface Message {
}

class Outer {
    static class Inner {
        static final class Email implements Message {
        }
    }
}
```

`Outer.Inner.Email` is a member nested class with a canonical name and in the same compilation unit. Because `Email implements Message` directly, it can belong to the inferred permitted set even when nested multiple levels deep.

**Do not generalize to every nested type:** Local/anonymous classes do not have canonical names. Only nested named types that have a canonical name under Java satisfy the condition.

## 39. A Sealed Interface Can Still Have Abstract Methods and Polymorphism

Having an inferred set of direct implementations does not cause the interface to lose its ability to dispatch through a shared API.

Create **`SealedPolymorphismDemo.java`**:

```java
sealed interface Calculation {
    int apply(int a, int b);
}

record Add() implements Calculation {
    @Override
    public int apply(int a, int b) {
        return a + b;
    }
}

record Multiply() implements Calculation {
    @Override
    public int apply(int a, int b) {
        return a * b;
    }
}

public class SealedPolymorphismDemo {
    public static void main(String[] args) {
        Calculation[] operations = {
                new Add(), new Multiply()
        };

        for (Calculation operation : operations) {
            System.out.println(operation.apply(3, 4));
        }
    }
}
```

```bash
javac SealedPolymorphismDemo.java
java SealedPolymorphismDemo
```

```text
7
12
```

The compiler knows the direct types Add/Multiply are permitted thanks to the same compilation unit. However, at runtime `apply` is still invoked according to the implementation object. `sealed` restricts inheritance relationships; it **does not turn every call into static dispatch**.

## 40. Avoid Confusing Exhaustive switch with `permits` Inference

Java inferring permitted classes when omitting `permits` is a rule for declaring a sealed hierarchy. It does not automatically mean every form of `switch` on a sealed interface is exhaustive in **every Java version** or in every syntax.

Specifically with **Java 17**:

- Pattern matching for `instanceof` is already available.
- Pattern matching for `switch` is a preview feature in Java 17 and should not be presented as a default example if the goal is compiling with standard `javac` without enabling preview.
- Traditional `switch` only uses types/labels compatible with the language; you cannot arbitrarily place `case SomeSubtype` as finalized default Java 17 syntax.

If building a runnable Java 17 sealed hierarchy example, use polymorphism, `instanceof` type patterns, or common methods. In Java 21+, finalized pattern switch and record patterns are a different version topic and must be version-labeled clearly.

## 41. Why Doesn't Java Infer Across an Entire Package or Module?

If the compiler automatically searched all classes in a package/module to form the permitted set when permits is omitted, the result would depend more heavily on build inputs and which files are present during compilation. This does not suit a hierarchy that needs a **closed, controllable, and stable list**.

Limiting inference to the compilation unit makes it possible to:

- See the child declarations directly within the corresponding source code unit.
- Check the parent/children relationship consistently.
- Avoid accidentally turning a newly added file in the same package into a permitted subtype of a sealed parent.
- Encourage explicit permits when members are split across files so that architectural intent is clear.

This is an **explanatory design rationale**, whereas the formal binding conditions are **same compilation unit + canonical name + direct relation**.

## 42. Comparing Explicit and Inferred `permits`

| Scenario | Can permits be omitted? | Explanation |
| --- | --- | --- |
| Sealed class and two direct final subclasses in the same file | Yes | Same compilation unit, canonical names |
| Sealed interface and two direct records in the same file | Yes | Direct implementations in the same unit |
| Direct child is a member nested class in the same unit | Yes | Member type has a canonical name |
| Direct child is a local class inside a method | No | Local class does not have a canonical name |
| Direct child is an anonymous class | No | Anonymous class does not have a canonical name |
| Child in another file but same package | Not allowed for inference | Explicit permits required |
| Child in another file but same named module | Not allowed for inference | Explicit permits required |
| Indirect grandchild in the same file | Not inferred into parent set | Does not directly extend/implement parent |
| Same file contains an unrelated class | Unrelated class is not inferred | Missing direct relation |
| Sealed with no subtypes and no permits | No | Compile-time error |
| Sealed already specifies permits A, same file adds B | B is not automatically added | Explicit list decides |
| `non-sealed` child in the same file | Possible | If the direct relation is correct and valid |
| `sealed` child in the same file | Possible | The child itself must have valid permitted descendants |
| Child record implements sealed interface | Possible | Record is final, valid direct implementation |

**Do not treat “being in the same file” as the sole condition.** All conditions must be met simultaneously.

## 43. Common Compile-Time Errors and How to Fix Them

| Error/Misconception | Cause | Proper Fix |
| --- | --- | --- |
| Sealed parent has no permits and no children in the same file | No set to infer from | Declare a direct child or change the design to final |
| Child is in another file in the same package while omitting permits | Not in the same compilation unit | Use explicit permits |
| Child is in the same module but a different file | Module scope does not replace unit scope | Use explicit permits |
| Local class directly implements a sealed interface | Has no canonical name | Use a top-level/member permitted type |
| Anonymous class extends a sealed parent | Has no canonical name/permitted declaration | Use a named child |
| Grandchild is expected to appear in parent permits | Indirect relationship | Only direct children are permitted |
| Forgetting `final`/`sealed`/`non-sealed` on a direct child | Inheritance policy not chosen | Choose an appropriate modifier |
| Sealed class does not accept a direct interface as a “subclass” | An interface cannot extend a class | Check extends/implements for the right kind |
| Explicit permits lists only A while B also extends parent | B is not permitted | Add B to permits or omit permits when in the same unit |
| Explicit permits names a class that does not directly extend parent | Permits is only for direct types | List the actual direct child |
| Thinking `javac A.java B.java` is a single unit | Each source file is a separate unit | Check source file boundaries |
| Wanting a sealed class that allows no children | Sealed requires a permitted set | Use `final class` |
| Using Java 17 preview pattern switch without enabling flags | Wrong version/compile flags | Use stable Java 17 features or specify the version |
| Trying to guess compiler-generated class names | Not a stable API | Use reflection `getPermittedSubclasses` |
| Placing a subclass in an inappropriate module/package | Violates co-location rules | Same module or same package (unnamed) |
| Thinking inferred permits forces every descendant to be final | `non-sealed` can open a branch | Check each direct child modifier |

## 44. Automated Self-Test on the Inferred List

Create **`InferredPermitsSelfTest.java`**:

```java
import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;

sealed interface Transport {
}

record Walk() implements Transport {
}

record Bike() implements Transport {
}

record Car() implements Transport {
}

public class InferredPermitsSelfTest {
    static void check(boolean value, String label) {
        if (!value) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        check(Transport.class.isSealed(), "sealed");

        Class<?>[] permitted =
                Transport.class.getPermittedSubclasses();

        check(permitted.length == 3, "three children");

        Set<String> names = Arrays.stream(permitted)
                .map(Class::getSimpleName)
                .collect(Collectors.toSet());

        check(names.equals(Set.of("Walk", "Bike", "Car")),
                "permitted names");

        check(!Walk.class.isSealed(), "record is final");

        System.out.println("inferred permits PASS");
    }
}
```

```bash
javac InferredPermitsSelfTest.java
java InferredPermitsSelfTest
```

```text
inferred permits PASS
```

`check` explicitly throws `AssertionError` on failure, so there is no need to enable the JVM `-ea` flag. The test does not assume reflection result ordering: it converts to a Set and compares all names.

**Test goal:** Confirm that `Transport` is sealed and the list of direct permitted implementations is exact after compiler inference. If `Scooter implements Transport` is accidentally added to the same unit, the count/names test catches that change.

## 45. Exercise 1: Examining a Compilation Unit

Suppose all are in **the same Java file**:

```java
sealed interface Vehicle {
}

final class Car implements Vehicle {
}

non-sealed class Bike implements Vehicle {
}

final class RacingBike extends Bike {
}

final class Boat {
}
```

**Question:** When Vehicle omits permits, which types are inferred by the compiler?

**Answer:** `Car` and `Bike`.

- Car and Bike **directly implement Vehicle**.
- RacingBike only extends Bike, belonging **indirectly** to Vehicle.
- Boat does not implement Vehicle.
- Car and Bike have canonical names and are in the same compilation unit.

If you want Bike to disallow further subclassing, change it to `final class Bike implements Vehicle`, though in that case RacingBike will not be able to extend Bike.

## 46. Exercise 2: Filtering Out Candidates Without a Canonical Name

Examine the **intentionally invalid** code:

```java
sealed interface Listener {
}

class Factory {
    static Listener make() {
        class LocalListener implements Listener {
        }

        return new LocalListener();
    }
}
```

**Issue:** LocalListener has no canonical name and does not belong to the inferred permitted set. Listener also has no other valid permitted direct subtype. The compiler rejects it.

### A Runnable Fix

Create **`NamedListenerDemo.java`**:

```java
sealed interface Listener {
    void onEvent();
}

public class NamedListenerDemo {
    private static final class LocalNamedListener
            implements Listener {
        @Override
        public void onEvent() {
            System.out.println("EVENT");
        }
    }

    static Listener make() {
        return new LocalNamedListener();
    }

    public static void main(String[] args) {
        make().onEvent();
    }
}
```

```bash
javac NamedListenerDemo.java
java NamedListenerDemo
```

```text
EVENT
```

`LocalNamedListener` is a **member nested class with a canonical name**, not a local class even though its name contains the word “Local”. It is a direct implementation of Listener, in the same compilation unit and final, so inference is valid.

**A type's name does not determine the declaration category.** The declaration location and Java's rules determine local vs. member.

## 47. Exercise 3: Distinguishing Direct Classes/Interfaces

File **`InterfaceHierarchyExercise.java`**:

```java
sealed interface Service {
}

non-sealed interface Online extends Service {
}

final class Web implements Online {
}

final class LocalService implements Service {
}

public class InterfaceHierarchyExercise {
    public static void main(String[] args) {
        Service a = new Web();
        Service b = new LocalService();

        System.out.println(a instanceof Online);
        System.out.println(b instanceof Online);
    }
}
```

```bash
javac InterfaceHierarchyExercise.java
java InterfaceHierarchyExercise
```

```text
true
false
```

**Question:** What are the direct permitted types of Service?

**Answer:** `Online` and `LocalService`. `Web` only directly implements Online, so it is an indirect descendant of Service.

## 48. Exercise 4: Fixing Split-File Code

Given:

```text
Shape.java
Square.java
Circle.java
```

File Shape.java:

```java
sealed interface Shape {
}
```

File Square.java:

```java
final class Square implements Shape {
}
```

File Circle.java:

```java
final class Circle implements Shape {
}
```

This is an **intentionally invalid trio of files** because Shape omits permits and has no direct children inside the Shape.java compilation unit.

**Two ways to fix:**

1. Keep the three files and change Shape to `sealed interface Shape permits Square, Circle`, ensuring package/module constraints are met.
2. Move the Square and Circle declarations into the **same compilation unit** as Shape and keep permits omitted if that file organization fits.

Simply compiling all three in a single `javac` command does not resolve the inference error.

## 49. Review Questions with Answers

**1.** When does a sealed class not need `permits`?

*When there is at least one direct subclass with a canonical name, declared in the same compilation unit; the compiler infers all direct subclasses that meet the conditions.*

**2.** If a direct child is in another file in the same package, is it inferred?

*No; being in the same package alone is not enough.*

**3.** What if the direct child is in a different module?

*Invalid for a permitted hierarchy under module rules. Inference also cannot cross compilation units.*

**4.** In a sealed interface, which kinds of direct types are inferred?

*Direct implementing classes and direct extending interfaces that have canonical names in the same unit.*

**5.** Does a local class inside a method have a canonical name?

*No, so it is not inferred.*

**6.** Can an anonymous class directly implement a sealed interface by omitting permits?

*No; it has no canonical name and cannot become a permitted direct implementation that way.*

**7.** Can a nested member class be inferred?

*Yes, if it has a canonical name, is in the same unit, and directly extends/implements the parent.*

**8.** Why must a direct child be `final`, `sealed`, or `non-sealed`?

*To clearly indicate whether the branch remains closed, remains sealed, or reopens according to the inheritance policy.*

**9.** Can a sealed type be declared without permits and with no direct children?

*Not for an ordinary sealed class/interface; it is a compile-time error.*

**10.** If you do not want any subclasses at all, what should you use?

*Final class.*

**11.** Does `Grandchild extends Child` automatically belong in Grandparent's permits?

*No, if it is only an indirect relationship.*

**12.** Does a direct `non-sealed` child allow subclasses beneath it?

*Yes, under ordinary inheritance rules.*

**13.** If the parent already specifies `permits A` while B in the same file also extends the parent, is B automatically added?

*No; you must list B or omit permits when the inference conditions are met.*

**14.** Does `Class.getPermittedSubclasses()` list direct or indirect descendants?

*Direct permitted types of the sealed declaration.*

**15.** What does `Class.isSealed()` check?

*Checks whether the corresponding class/interface is sealed.*

**16.** Does a single `javac A.java B.java` invocation make A.java/B.java the same compilation unit?

*No.*

**17.** Does inference depend on the order of declarations in the file?

*No; it depends on the type, canonical name, direct relationship, and compilation unit.*

**18.** Are unrelated classes in the same file inferred?

*No; they lack a direct inheritance/implementation relation.*

**19.** Why are enums generally not the example to use for explaining inference of ordinary sealed classes?

*Enums have special semantics regarding implicit subclasses due to constant-specific bodies; this topic covers ordinary sealed classes/interfaces.*

**20.** When is explicit permits better than inference?

*When direct subtypes are in separate source files, or when you want the permitted list clearly visible from the declaration for API control.*

## 50. Checklist Before Removing `permits`

- [ ] Is the parent truly declared `sealed`?
- [ ] Is the parent an ordinary sealed class or sealed interface, not confused with the enum special case?
- [ ] Is there at least one valid **direct** subtype?
- [ ] Are all direct subtypes you want to permit located in the **same compilation unit**?
- [ ] Are you avoiding relying solely on them being in the same package/directory/module?
- [ ] Are you avoiding relying on them being compiled in the same `javac` invocation?
- [ ] Does each inferred subtype have a **canonical name**?
- [ ] Are you avoiding trying to use a local/anonymous class as a direct permitted child?
- [ ] Is the `extends`/`implements` relationship truly direct?
- [ ] Are you avoiding confusing indirect descendants with the direct permitted list?
- [ ] For a sealed interface, have direct extending interfaces also been accounted for?
- [ ] Do the direct children have valid final/sealed/non-sealed modifiers?
- [ ] For a child that is itself sealed, have the descendants of that child been considered?
- [ ] If choosing `non-sealed`, is it understood that the branch below can be opened?
- [ ] Is there no other file attempting to directly extend/implement the parent after removing permits?
- [ ] If explicit permits is present, have all direct types been updated rather than assuming the compiler merges them?
- [ ] Do package/module constraints match the entire hierarchy?
- [ ] Are you avoiding relying on generated binary names to infer canonical names?
- [ ] Is there a `getPermittedSubclasses()` test if you want to lock down the API list?
- [ ] If the goal is to have no children, should `final` be used instead of `sealed`?
- [ ] Do Java 17 examples use stable syntax without relying on preview pattern switch?
- [ ] Do filenames/public class names, `javac` commands, and stdout match?
- [ ] Have you considered maintainability when putting multiple top-level classes into the same file?

---

**Final takeaway:** In Java 17+, when a **`sealed class` or `sealed interface` omits `permits`**, the compiler infers the list of permitted direct subtypes by selecting the **named types that have a canonical name, are declared in the same compilation unit, and directly extend/implement the sealed parent**. For a class, these are the **direct subclasses**; for an interface, they include direct implementing classes and direct extending interfaces. **Being in the same package/module but in different files is not enough**; **local/anonymous classes** and **indirect descendants** do not belong to the inferred set. If there is no valid direct subtype, a sealed declaration missing permits fails with an error. Omitting permits **does not remove** the `final`/`sealed`/`non-sealed` constraints on direct children or the package/module conditions. When direct implementations reside across multiple files, use **explicit permits**; when they are close together in a single file, inference can make the hierarchy cleaner and clearer.
