# Sealed Declarations and the permits List in Java 17+

**Sealed classes** and **sealed interfaces** allow API designers to **directly control which classes or interfaces are allowed to extend/implement a type**. Java 17 supports this feature officially, without needing to enable preview.

Basic example:

~~~java
sealed interface Result permits Success, Failure {}

record Success(String value) implements Result {}

record Failure(String message) implements Result {}
~~~

`Result` is a **sealed interface**; only `Success` and `Failure` are designated as **permitted direct implementations**. A class outside the list cannot directly `implements Result`, even if it resides in the same package.

For a class:

~~~java
sealed abstract class Shape permits Circle, Rectangle {}

final class Circle extends Shape {}

non-sealed class Rectangle extends Shape {}
~~~

Here `Circle` closes off the inheritance path with `final`, while `Rectangle` reopens subclassing because it is declared `non-sealed`. The `permits` list only controls the **direct inheritance step**; it does not by itself forbid all indirect descendants.

This lesson belongs to **Java Core — Class & Object / Sealed Classes**, focusing directly on the topic **“Sealed Declarations and the permits List”**. Every complete program uses Java 17+ with a file name, compile/run commands, and expected stdout. Intentionally invalid snippets are separately annotated so they are not confused with runnable code.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Declare `sealed class` and `sealed interface` using Java 17 syntax.
2. Write the `permits` list with the correct **direct subclasses/direct subinterfaces/direct implementing classes**.
3. Distinguish between `extends`, `implements`, and `permits`; understand that they do not replace one another.
4. Know when `permits` must be written explicitly and when Java infers the list.
5. Grasp the restriction of being in the **same named module** or the **same package in an unnamed module**.
6. Explain the obligation of a permitted subtype: `final`, `sealed`, or `non-sealed` when required.
7. Distinguish between `final` terminating the hierarchy, `sealed` continuing to restrict it, and `non-sealed` opening the hierarchy.
8. Understand the difference between being **directly permitted** and **validly inheriting indirectly**.
9. Use records, enums, and ordinary classes appropriately with sealed interfaces.
10. Declare multi-level, multi-branch hierarchies and design leaf types.
11. Understand `abstract sealed class` and abstract methods of a hierarchy.
12. Avoid mistakenly assuming `sealed` means a data type is immutable, thread-safe, or cannot be instantiated.
13. Understand how valid modifiers for permitted interfaces differ from those for permitted classes.
14. Distinguish between generic sealed types and generic permitted subtypes.
15. Understand how accessibility/package/module constraints bind the permits list.
16. Read compiler errors when a listed type does not directly extend/implement the root type.
17. Know that a sealed class can still have ordinary constructors, fields, and methods.
18. Distinguish between designing with a sealed hierarchy and a finite enum.
19. Understand Java 17 `instanceof` pattern matching while not assuming switch pattern matching is stable by default.
20. Use Reflection `Class.isSealed()` and `getPermittedSubclasses()`.
21. Evaluate versioning when adding/removing permitted types.
22. Test both compile-time constraints and runtime behavior.

## 2. Why Do We Need to Restrict the Subtype Hierarchy?

Suppose an API models the outcome of processing:

~~~java
interface Outcome {}

class Success implements Outcome {}
class Failure implements Outcome {}
~~~

If an ordinary interface is accessible, another module can additionally define:

~~~java
class UnknownOutcome implements Outcome {}
~~~

Such extensibility is sometimes useful for plugins. However, sometimes the domain wants to guarantee that **only certain known variants exist**, in order to:

- control the validity of those states/variants;
- clarify the hierarchy architecture;
- prevent external implementations from breaking the API's invariants;
- centralize the logic for handling each variant;
- help the compiler and analysis tools know which direct branches can exist.

A sealed type meets that goal through **language rules and compiler/runtime checks**, rather than merely comments or conventions.

## 3. sealed class Syntax

Pattern:

~~~java
public sealed class Parent
        permits ChildA, ChildB {
    // Constructors, methods, fields...
}
~~~

The classes `ChildA` and `ChildB` must actually **directly extend Parent** and obey the location/modifier rules.

Example:

~~~java
sealed class Vehicle permits Car, Truck {}

final class Car extends Vehicle {}

final class Truck extends Vehicle {}
~~~

Within a single source file with package-private top-level types like the one above, the Java compiler determines the list of permitted direct subclasses.

**Remember these three sentences:**

- `extends` is written on the **subclass** to declare an inheritance relationship.
- `permits` is written on the **sealed parent** to restrict direct subtypes.
- A type in `permits` **does not automatically become a subclass** just by being listed; it must also declare the appropriate inheritance relationship.

## 4. Runnable Program: A sealed class with Two Leaf Types

Create the file **`SealedClassBasicsDemo.java`**:

~~~java
public class SealedClassBasicsDemo {
    static abstract sealed class Vehicle permits Car, Truck {
        abstract String label();
    }

    static final class Car extends Vehicle {
        @Override
        String label() {
            return "car";
        }
    }

    static final class Truck extends Vehicle {
        @Override
        String label() {
            return "truck";
        }
    }

    static String describe(Vehicle vehicle) {
        return vehicle.label();
    }

    public static void main(String[] args) {
        System.out.println(describe(new Car()));
        System.out.println(describe(new Truck()));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 SealedClassBasicsDemo.java
java SealedClassBasicsDemo
~~~

Stdout:

~~~text
car
truck
~~~

`Vehicle` is an abstract sealed class. Only `Car` and `Truck` directly extend Vehicle. The compiler guarantees the hierarchy contract; runtime dispatch selects the corresponding `label()` method.

## 5. sealed interface Syntax

Pattern:

~~~java
sealed interface Message
        permits TextMessage, BinaryMessage {
}
~~~

The permitted direct implementors or extending subinterfaces must declare their relationship with Message:

~~~java
record TextMessage(String text) implements Message {}

final class BinaryMessage implements Message {}
~~~

An interface can be:
- directly **implemented** by an appropriate class/record/enum;
- directly **extended** by a subinterface.

Like a sealed class, `permits` controls **the direct subtypes**, not the list of object instances.

### How Do Classes and Interfaces Differ?

A sealed class controls direct classes using `extends`. A sealed interface controls **directly implementing classes** and **directly extending interfaces**. Therefore, a sealed interface is often very convenient for modeling a set of variants that have both data and behavior.

## 6. Runnable Program: A sealed interface with Records

Create **`SealedInterfaceBasicsDemo.java`**:

~~~java
public class SealedInterfaceBasicsDemo {
    sealed interface Result permits Ok, Error {}

    record Ok(String value) implements Result {}

    record Error(String reason) implements Result {}

    static String describe(Result result) {
        if (result instanceof Ok ok) {
            return "ok:" + ok.value();
        }
        if (result instanceof Error error) {
            return "error:" + error.reason();
        }
        throw new IllegalStateException("unexpected result");
    }

    public static void main(String[] args) {
        System.out.println(describe(new Ok("data")));
        System.out.println(describe(new Error("missing")));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 SealedInterfaceBasicsDemo.java
java SealedInterfaceBasicsDemo
~~~

Stdout:

~~~text
ok:data
error:missing
~~~

Records are final types according to the language, so they are well suited as leaves of a sealed interface. `instanceof` type patterns were finalized in Java 16 and work normally on Java 17.

## 7. Exact Meaning of `permits`

The list:

~~~java
sealed class Base permits A, B {}
~~~

states: **The direct subclasses of Base can only be among the listed classes A and B, provided that A/B fully satisfy all other rules.**

It does **not** state:
- A or B have objects created automatically;
- A/B may only have a single instance;
- A/B must be final in all cases;
- all subclasses of A/B must be listed at Base;
- A/B are exempt from Java access control;
- Base cannot have methods or constructors;
- Base automatically becomes immutable;
- every object type in the system is completely closed if there is a non-sealed branch.

Example:

~~~java
sealed class Base permits Branch {}
non-sealed class Branch extends Base {}
class Grandchild extends Branch {}
~~~

`Grandchild` **does not directly extend Base**, so it does not belong to Base's permits list and remains valid. `Branch` has intentionally opened the sub-branch.

## 8. Runnable Program: An Indirect Subtype Does Not Need to Appear in Root permits

Create **`IndirectSubtypeDemo.java`**:

~~~java
public class IndirectSubtypeDemo {
    static sealed class Base permits Branch {}

    static non-sealed class Branch extends Base {}

    static final class Leaf extends Branch {}

    public static void main(String[] args) {
        Base value = new Leaf();

        System.out.println("Base=" + (value instanceof Base));
        System.out.println("Branch=" + (value instanceof Branch));
        System.out.println("Leaf=" + (value instanceof Leaf));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 IndirectSubtypeDemo.java
java IndirectSubtypeDemo
~~~

Stdout:

~~~text
Base=true
Branch=true
Leaf=true
~~~

`Leaf` inherits from Base indirectly through Branch. Because Branch is non-sealed, it is allowed to have additional subclasses without Base listing them individually.

## 9. Three Outcomes for a Permitted Class: final, sealed, non-sealed

A **directly permitted class** in a sealed hierarchy must use one of the appropriate declaration forms:

| Modifier | Meaning | Has descendants? |
| --- | --- | --- |
| `final` | Does not allow other classes to subclass this class | No |
| `sealed` | Allows a set of direct subclasses to be controlled further | Yes, but restricted |
| `non-sealed` | Reopens subclassing according to normal access rules | Yes, not restricted by permits on this branch itself |

Example:

~~~java
sealed class Root permits FinalLeaf, RestrictedBranch, OpenBranch {}

final class FinalLeaf extends Root {}

sealed class RestrictedBranch extends Root permits InnerLeaf {}

final class InnerLeaf extends RestrictedBranch {}

non-sealed class OpenBranch extends Root {}
~~~

Do not write an ordinary direct child missing a modifier:

~~~java
// class InvalidChild extends Root {} // Invalid as a direct permitted subtype.
~~~

Modifier syntax exceptions: records are already implicitly final, so a record implementing a sealed interface does not need `final` typed; enums have their own special rules.

## 10. Runnable Program: final, sealed, and non-sealed in the Same Tree

Create **`ThreeBranchesDemo.java`**:

~~~java
public class ThreeBranchesDemo {
    static sealed class Root
            permits FinalLeaf, RestrictedBranch, OpenBranch {}

    static final class FinalLeaf extends Root {}

    static sealed class RestrictedBranch extends Root
            permits InnerLeaf {}

    static final class InnerLeaf extends RestrictedBranch {}

    static non-sealed class OpenBranch extends Root {}

    static final class FurtherChild extends OpenBranch {}

    public static void main(String[] args) {
        Root a = new FinalLeaf();
        Root b = new InnerLeaf();
        Root c = new FurtherChild();

        System.out.println(a.getClass().getSimpleName());
        System.out.println(b.getClass().getSimpleName());
        System.out.println(c.getClass().getSimpleName());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ThreeBranchesDemo.java
java ThreeBranchesDemo
~~~

Stdout:

~~~text
FinalLeaf
InnerLeaf
FurtherChild
~~~

`Root` only permits **FinalLeaf, RestrictedBranch, OpenBranch**. `InnerLeaf` is permitted by RestrictedBranch, while `FurtherChild` lies beneath the non-sealed branch.

## 11. A Permitted Subinterface Chooses sealed or non-sealed

An **interface** cannot be a `final interface`, because an interface remains a contract meant for implementations/extension.

If a sealed interface directly permits a subinterface, this subinterface must itself be declared **sealed** or **non-sealed**.

~~~java
sealed interface Event permits InternalEvent, ExtensionEvent {}

sealed interface InternalEvent extends Event permits Started {}

non-sealed interface ExtensionEvent extends Event {}

record Started(long id) implements InternalEvent {}
~~~

`Started` is an implicitly final record. `ExtensionEvent` opens extension: new classes can implement ExtensionEvent (within normal accessibility scope), and therefore are indirect implementations of Event.

### Difference from a Permitted Class

For a direct child class, the three choices are final/sealed/non-sealed. For a direct child interface, only sealed/non-sealed are valid because `final` is not a valid interface modifier.

## 12. Runnable Program: A sealed interface Chained with a non-sealed interface

Create **`InterfaceBranchDemo.java`**:

~~~java
public class InterfaceBranchDemo {
    sealed interface Event permits Internal, External {}

    sealed interface Internal extends Event permits Started {}

    non-sealed interface External extends Event {}

    record Started(int id) implements Internal {}

    static final class ExternalNotice implements External {
        @Override
        public String toString() {
            return "external";
        }
    }

    public static void main(String[] args) {
        Event internal = new Started(7);
        Event external = new ExternalNotice();

        System.out.println(internal);
        System.out.println(external);
        System.out.println(external instanceof Event);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 InterfaceBranchDemo.java
java InterfaceBranchDemo
~~~

Stdout:

~~~text
Started[id=7]
external
true
~~~

Sealed Event does not directly permit ExternalNotice. ExternalNotice implements non-sealed External, and thus is indirectly an Event. Distinguishing the two levels is essential.

## 13. `sealed` Is Not Synonymous with `abstract`

A sealed **class** can be abstract or concrete. The sealed modifier only restricts **who is permitted to extend it**; it does not automatically force the class to be abstract.

Concrete example:

~~~java
sealed class Base permits Child {
    String name() {
        return "base";
    }
}

final class Child extends Base {}
~~~

If the constructor/accessibility allows, code can use `new Base()`; sealed does not forbid instantiating Base itself. Conversely, if `abstract sealed class Base` is used, Base cannot be instantiated directly because it is abstract.

### When to Choose abstract sealed?

When the root represents a common contract but it makes no sense to instantiate it directly, for example `Shape` with an abstract `area()` or `Expression` with distinct semantics per variant.

## 14. Runnable Program: A Concrete sealed class Can Still Be Instantiated

Create **`ConcreteSealedDemo.java`**:

~~~java
public class ConcreteSealedDemo {
    static sealed class Base permits Child {
        String label() {
            return "base";
        }
    }

    static final class Child extends Base {}

    public static void main(String[] args) {
        Base direct = new Base();
        Base child = new Child();

        System.out.println(direct.label());
        System.out.println(child.label());
        System.out.println("same type=" +
                (direct.getClass() == child.getClass()));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ConcreteSealedDemo.java
java ConcreteSealedDemo
~~~

Stdout:

~~~text
base
base
same type=false
~~~

`Base` is a concrete sealed class, so it can be instantiated. `Child` is a valid subtype and inherits the `label` method.

## 15. `permits` with Fully Qualified Class Names

`permits` usually lists simple names when the types are in the same name-lookup scope:

~~~java
sealed class Document permits TextDocument, PdfDocument {}
~~~

If the types are in different packages within the **same named module**, fully qualified names or valid imports may be needed, for example:

~~~java
public sealed interface Document
        permits example.impl.TextDocument, example.impl.PdfDocument {
}
~~~

**This snippet is an illustrative skeleton**; it only compiles when the packages/module/types exist and Java visibility rules allow it. It is not a standalone runnable file.

`permits` uses type names, not object expressions or enum constants:

~~~java
// permits new TextDocument() // Invalid syntax.
// permits SomeEnum.CONSTANT // Invalid: a list of type names, not values.
~~~

At the same time, being listed does not replace the requirement of actual direct inheritance.

## 16. Common Misconception: `permits` Is Not `implements`

Wrong mindset:

~~~java
sealed interface Role permits Admin {}
class Admin {}
~~~

Type `Admin` is listed, but does not `implements Role`. The compiler will not treat Admin as a valid permitted implementation merely by name.

Correct:

~~~java
sealed interface Role permits Admin {}

final class Admin implements Role {}
~~~

The reverse direction is also wrong:

~~~java
sealed interface Role permits Admin {}
final class Guest implements Role {} // Guest is not in permits.
~~~

In a sealed hierarchy with an explicit permits list, the direct implementing class Guest will be rejected.

## 17. If the permits List Is Omitted: When Does Java Infer It?

When there is no explicit `permits`, the compiler can only infer **appropriately declared direct children in the same compilation unit**:

~~~java
sealed interface Value {}
record TextValue(String text) implements Value {}
record NumberValue(int number) implements Value {}
~~~

Within the same source file, the two records are inferred permitted implementations. The compiler **does not search all files in the package/module** to update the whitelist. When separating the types into different compilation units, use an explicit `permits` and verify direct inheritance. Cases involving canonical names, nested/local declarations, classes not directly belonging to the hierarchy, and errors when splitting files are systematically analyzed in the lesson **Conditions for Inferring the Subclass List When Omitting permits**.

## 18. Runnable Program: Inferring permits from the Same File

Create **`InferredPermitsDemo.java`**:

~~~java
sealed interface Transport {}

final class Bus implements Transport {
    @Override
    public String toString() {
        return "bus";
    }
}

final class Train implements Transport {
    @Override
    public String toString() {
        return "train";
    }
}

public class InferredPermitsDemo {
    public static void main(String[] args) {
        Transport first = new Bus();
        Transport second = new Train();

        System.out.println(first);
        System.out.println(second);
        System.out.println("sealed=" + Transport.class.isSealed());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 InferredPermitsDemo.java
java InferredPermitsDemo
~~~

Stdout:

~~~text
bus
train
sealed=true
~~~

Parent `Transport` has no explicit permits; `Bus` and `Train` are direct implementors in the same source file, so the list is inferred.

## 19. Explicit permits Even When Types Are in the Same File

Omitting permits is not required when all types are in the same compilation unit:

~~~java
sealed interface Payment permits Cash, Card {}

record Cash(int cents) implements Payment {}

record Card(String lastFour) implements Payment {}
~~~

Writing explicit `permits Cash, Card` is beneficial when:
- you want API readers to see the list of allowed variants immediately;
- you want to clearly restrict the types when the file contains many declarations;
- reviewing versioning/architecture is easier;
- you plan to move the types to other source files later.

### Not Repeating for No Reason

If the types and hierarchy are small, inferred permits keeps examples concise. However, for a large public API, an explicit list often helps express intentional restriction.

## 20. Runnable Program: Explicit permits in the Same Compilation Unit

Create **`ExplicitPermitsDemo.java`**:

~~~java
public class ExplicitPermitsDemo {
    sealed interface Payment permits Cash, Card {}

    record Cash(int cents) implements Payment {}

    record Card(String number) implements Payment {}

    static String text(Payment payment) {
        if (payment instanceof Cash cash) {
            return "cash:" + cash.cents();
        }
        if (payment instanceof Card card) {
            return "card:" + card.number();
        }
        throw new IllegalStateException();
    }

    public static void main(String[] args) {
        System.out.println(text(new Cash(100)));
        System.out.println(text(new Card("****")));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ExplicitPermitsDemo.java
java ExplicitPermitsDemo
~~~

Stdout:

~~~text
cash:100
card:****
~~~

Explicit `permits` and inferred `permits` both enforce language-level restrictions; they differ in how the declared permitted types are determined.

## 21. Location Rules: Named Modules and Unnamed Modules

In addition to `permits` and the modifiers of children, the declaration locations must be valid:

- Parent belongs to a **named module**: permitted direct subtypes must be in the **same named module** (they may be in a different package if access is appropriate).
- Parent belongs to an **unnamed module**: permitted direct subtypes must be in the **same package**.

`exports` and `requires` do not relax the `permits` condition. Multi-package/classpath source layout examples and how to inspect `javac` errors are the focus of the lesson **Same-Module or Same-Package Constraint**.

## 22. Multiple Packages in the Same Named Module: Illustrative Structure

This example is **not a single-file runnable**; it illustrates a valid project layout:

~~~text
src/
  edu.demo.sealed/
    module-info.java
    demo/api/Result.java
    demo/impl/Ok.java
    demo/impl/Error.java
~~~

`module-info.java`:

~~~java
module edu.demo.sealed {
    exports demo.api;
    exports demo.impl;
}
~~~

`demo/api/Result.java`:

~~~java
package demo.api;

public sealed interface Result
        permits demo.impl.Ok, demo.impl.Error {
}
~~~

`demo/impl/Ok.java`:

~~~java
package demo.impl;

public record Ok(String value)
        implements demo.api.Result {
}
~~~

`demo/impl/Error.java`:

~~~java
package demo.impl;

public record Error(String reason)
        implements demo.api.Result {
}
~~~

The permitted implementations are in a different package, but **within the same named module**. In a real project, adjust `exports` according to the desired public API/visibility; this is an illustrative example to simplify reading.

## 23. The Same-Package Rule in an Unnamed Module

Suppose `module-info.java` is not used:

~~~text
src/
  demo/
    Result.java
    Ok.java
    Error.java
~~~

`demo/Result.java`:

~~~java
package demo;

public sealed interface Result permits Ok, Error {}
~~~

`demo/Ok.java`:

~~~java
package demo;

public record Ok(String value) implements Result {}
~~~

`demo/Error.java`:

~~~java
package demo;

public record Error(String reason) implements Result {}
~~~

This is an **illustrative set of files**, not run as a single-file demo. Because they are in the same package demo, explicit permits works in the unnamed module. If Error is moved to a different package without moving the entire hierarchy into the same appropriate named module, it will violate the location rule.

## 24. Compile-Time Errors from Module/Package Mismatch

With an **unnamed module**, you cannot:

~~~java
// package a;
// public sealed interface Result permits b.Ok {}
~~~

and define `b.Ok` in another package and expect the compiler to accept it. Even if a class is public and importable, it still violates the same-package rule.

With **different named modules**, having both modules `requires` each other does not make the permitted subclass belong to the same named module. Java also does not allow “just having a permits list” to cross a module boundary.

### Appropriate Module Design

If implementations need to be extended in independent plugins/modules, consider:
- a public **non-sealed interface** extension point;
- a sealed core hierarchy with a **non-sealed permitted branch**;
- composition and registration;
- ServiceLoader via an appropriate interface that is not sealed.

The sealed root should represent the scope of control that the module actually owns.

## 25. Access Modifiers Still Apply

`permits` **does not relax accessibility**. A direct subtype must be allowed to extend/implement the supertype according to Java access rules.

For example, if a sealed class has a `private` constructor that is inaccessible to the permitted subclass, subclassing may fail even though the subtype's name is in the permits list.

Similarly, package-private types are only accessible within the appropriate package; private nested types have their own lexical access rules.

Especially with a sealed class, design constructor accessibility appropriately for allowed subclasses:

~~~java
sealed abstract class Command permits Start, Stop {
    protected Command() {}
}

final class Start extends Command {}

final class Stop extends Command {}
~~~

A `protected` constructor enables a permitted subclass to call `super()` validly, but it does not turn every class into a permitted subtype.

## 26. Runnable Program: Constructor of a Sealed Superclass

Create **`SealedConstructorDemo.java`**:

~~~java
public class SealedConstructorDemo {
    static abstract sealed class Message permits Notice, Alert {
        private final String text;

        protected Message(String text) {
            this.text = java.util.Objects.requireNonNull(
                    text, "text");
        }

        String text() {
            return text;
        }
    }

    static final class Notice extends Message {
        Notice(String text) {
            super(text);
        }
    }

    static final class Alert extends Message {
        Alert(String text) {
            super(text);
        }
    }

    public static void main(String[] args) {
        Message first = new Notice("Hello");
        Message second = new Alert("Danger");

        System.out.println(first.text());
        System.out.println(second.text());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 SealedConstructorDemo.java
java SealedConstructorDemo
~~~

Stdout:

~~~text
Hello
Danger
~~~

A sealed superclass still has ordinary instance fields and constructors; permits controls the type hierarchy and does not alter constructor chaining rules.

## 27. Sealed and `final` Are Different

`final class`: allows no subclasses at all.

`sealed class`: can allow **a specific list of direct subclasses**.

`non-sealed class`: restores subclassing capability on a branch that directly extends/implements a sealed supertype.

Example:

~~~java
final class Closed {}
// class SubClosed extends Closed {} // Invalid.

sealed class Limited permits Allowed {}
final class Allowed extends Limited {}
~~~

In Limited, the subclass Allowed is valid; in Closed, there are no permitted subtypes because `final` closes it completely.

**Do not write `final sealed class`**: the two modifiers have conflicting meanings regarding subclassing, and Java does not allow that combination.

## 28. `non-sealed` Is Only Valid in the Right Place

`non-sealed` is meaningful when the declaration is a **direct subtype of a sealed class/interface**. A class completely unrelated to a sealed parent cannot arbitrarily write non-sealed on itself:

~~~java
// non-sealed class Ordinary {} // Invalid: does not directly extend a sealed type.
~~~

Correct:

~~~java
sealed class Base permits Open {}

non-sealed class Open extends Base {}
~~~

`Open` on that branch allows subclasses according to usual Java rules. Direct descendants of Open **do not have to** keep adding `non-sealed` or `final` because Open itself has already reopened the branch.

## 29. Runnable Program: Opening a Branch and Subclassing Normally

Create **`NonSealedContinuationDemo.java`**:

~~~java
public class NonSealedContinuationDemo {
    static sealed class Entry permits Extension {}

    static non-sealed class Extension extends Entry {
        String describe() {
            return "extension";
        }
    }

    static class Plugin extends Extension {
        @Override
        String describe() {
            return "plugin";
        }
    }

    public static void main(String[] args) {
        Entry value = new Plugin();

        System.out.println(value instanceof Entry);
        System.out.println(((Extension) value).describe());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 NonSealedContinuationDemo.java
java NonSealedContinuationDemo
~~~

Stdout:

~~~text
true
plugin
~~~

`Plugin` only `extends Extension`. It does not directly extend sealed Entry and does not need to be listed by Entry in permits.

## 30. Hierarchy Continuing as sealed at Lower Levels

A permitted class using `sealed` means **it itself becomes a sealed parent for the next level**:

~~~java
sealed class Parent permits Intermediate {}

sealed class Intermediate extends Parent permits Leaf {}

final class Leaf extends Intermediate {}
~~~

`Parent` does not need to list Leaf because Leaf is not a direct subclass of Parent.

There can be multiple branches:

~~~text
Parent [sealed]
  |
  +-- Intermediate [sealed]
  |       |
  |       +-- Leaf [final]
  |
  +-- Open [non-sealed]
          |
          +-- arbitrary descendants
~~~

The closedness of the entire tree depends on **each branch**, not only the root's declaration.

## 31. Runnable Program: Multi-Level Hierarchy

Create **`MultiLevelSealedDemo.java`**:

~~~java
public class MultiLevelSealedDemo {
    static sealed interface Expression
            permits Literal, Compound {}

    static record Literal(int value) implements Expression {}

    static sealed interface Compound extends Expression
            permits Add, Multiply {}

    static record Add(Expression left, Expression right)
            implements Compound {}

    static record Multiply(Expression left, Expression right)
            implements Compound {}

    static int evaluate(Expression expression) {
        if (expression instanceof Literal literal) {
            return literal.value();
        }
        if (expression instanceof Add add) {
            return evaluate(add.left()) + evaluate(add.right());
        }
        if (expression instanceof Multiply multiply) {
            return evaluate(multiply.left()) *
                    evaluate(multiply.right());
        }
        throw new IllegalStateException("unknown expression");
    }

    public static void main(String[] args) {
        Expression expression =
                new Add(new Literal(2),
                        new Multiply(new Literal(3),
                                new Literal(4)));

        System.out.println(evaluate(expression));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 MultiLevelSealedDemo.java
java MultiLevelSealedDemo
~~~

Stdout:

~~~text
14
~~~

`Expression` permits Literal and Compound; Compound in turn permits Add and Multiply. All leaf records directly implement one of the appropriate permitted interfaces, while indirectly being Expressions.

## 32. Why Must a Class in permits Be a **Direct** Child?

Incorrect:

~~~java
sealed class Parent permits Child, Grandchild {}
non-sealed class Child extends Parent {}
final class Grandchild extends Child {}
~~~

`Grandchild` **does not directly extend Parent**, so it cannot be listed as a direct permitted subclass of Parent.

Correct:

~~~java
sealed class Parent permits Child {}
non-sealed class Child extends Parent {}
final class Grandchild extends Child {}
~~~

Or if you want Grandchild to directly extend Parent, it must change its superclass declaration to actually `extends Parent` (and satisfy the related dependencies/constructors).

### Quick Check Rule

For each name in `Parent`'s `permits` list, go to that declaration and read `extends Parent` or `implements Parent`/`extends Parent` for interfaces as applicable. If no **direct** relationship is seen, it is incorrect.

## 33. Runnable Program: The Compiler Controls Root Direct Children

Create **`DirectChildDemo.java`**:

~~~java
public class DirectChildDemo {
    sealed interface Root permits Alpha, Beta {}

    record Alpha(int value) implements Root {}

    final static class Beta implements Root {}

    static String type(Root root) {
        if (root instanceof Alpha) {
            return "alpha";
        }
        if (root instanceof Beta) {
            return "beta";
        }
        throw new IllegalStateException();
    }

    public static void main(String[] args) {
        System.out.println(type(new Alpha(1)));
        System.out.println(type(new Beta()));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 DirectChildDemo.java
java DirectChildDemo
~~~

Stdout:

~~~text
alpha
beta
~~~

Both Alpha and Beta directly implement Root and are in the permits list. If you add `class Gamma implements Root` which is not in permits, javac will reject it.

## 34. In a sealed interface: A Permitted Class Must Actually Implement It Directly

An easily confused case:

~~~java
sealed interface Root permits A {}

non-sealed interface A extends Root {}

final class C implements A {}
~~~

`C` is a Root **indirectly**, and is valid even though it is not in Root.permits.

Conversely:

~~~java
// final class C implements Root {} // Invalid if C is not permitted.
~~~

The restriction applies to the direct extension/implementation edge of the sealed type, not endlessly to every subclass after a non-sealed branch.

## 35. Runnable Program: Subinterface as an Extension Point

Create **`ExtensionPointDemo.java`**:

~~~java
public class ExtensionPointDemo {
    sealed interface Command permits BuiltinCommand, PluginCommand {}

    record BuiltinCommand(String name) implements Command {}

    non-sealed interface PluginCommand extends Command {
        String execute();
    }

    static final class EchoPlugin implements PluginCommand {
        @Override
        public String execute() {
            return "echo";
        }
    }

    public static void main(String[] args) {
        Command builtin = new BuiltinCommand("help");
        Command plugin = new EchoPlugin();

        System.out.println(builtin instanceof Command);
        System.out.println(((PluginCommand) plugin).execute());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ExtensionPointDemo.java
java ExtensionPointDemo
~~~

Stdout:

~~~text
true
echo
~~~

This structure allows a sealed root to represent **a few controlled broad categories**, one of which is a non-sealed extension interface.

## 36. Records Are Natural Permitted Leaves

A `record` is an **implicitly final** class, so it fits very well as a leaf of a sealed interface:

~~~java
sealed interface Payment permits Cash, Card {}
record Cash(int cents) implements Payment {}
record Card(String lastFour) implements Payment {}
~~~

Permits controls the **direct subtypes**; record components describe the payload of each variant. A record does not automatically guarantee deep immutability if it contains mutable components. Practical abstract/record/enum combinations and inheritance constraints are covered in the lesson **Combining sealed with Abstract Classes, Records, and Enums**; the runnable example immediately following this section still illustrates record variants.

## 37. Runnable Program: Permitted Records

Create **`SealedRecordsDemo.java`**:

~~~java
public class SealedRecordsDemo {
    sealed interface Payment permits Cash, Card {}

    record Cash(int cents) implements Payment {
        Cash {
            if (cents < 0) {
                throw new IllegalArgumentException("cents");
            }
        }
    }

    record Card(String lastFour) implements Payment {
        Card {
            if (lastFour == null || lastFour.length() != 4) {
                throw new IllegalArgumentException("lastFour");
            }
        }
    }

    public static void main(String[] args) {
        Payment a = new Cash(100);
        Payment b = new Card("1234");

        System.out.println(a);
        System.out.println(b);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 SealedRecordsDemo.java
java SealedRecordsDemo
~~~

Stdout:

~~~text
Cash[cents=100]
Card[lastFour=1234]
~~~

`Cash` and `Card` are both final because they are records; Payment's permitted list is complete with these two direct implementations.

## 38. Sealed Interfaces and Enums

An `enum` can be a **direct permitted implementation** of a sealed interface. The `permits` list lists the **enum type**, not each individual enum constant:

~~~java
sealed interface Action permits FixedAction, CustomAction {}
enum FixedAction implements Action { START, STOP }
record CustomAction(String name) implements Action {}
~~~

Enums follow a special rule: an enum declaration is treated as implicitly final or sealed depending on whether it has constant-specific class bodies, without the author needing to write `final enum`. All constants still belong to the same enum type; they do not become multiple direct permitted types. The case of enum constant bodies is explained in depth in the lesson **Combining sealed with Abstract Classes, Records, and Enums**.

## 39. Runnable Program: Directly Permitted Enum

Create **`SealedEnumDemo.java`**:

~~~java
public class SealedEnumDemo {
    sealed interface Command permits Fixed, Custom {}

    enum Fixed implements Command {
        START, STOP
    }

    record Custom(String name) implements Command {}

    public static void main(String[] args) {
        Command a = Fixed.START;
        Command b = new Custom("build");

        System.out.println(a);
        System.out.println(b);
        System.out.println(Fixed.START instanceof Command);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 SealedEnumDemo.java
java SealedEnumDemo
~~~

Stdout:

~~~text
START
Custom[name=build]
true
~~~

`Command.permits` lists Fixed and Custom, not START/STOP; the enum constants are instances, not direct subtypes of interface Command.

## 40. Generic Sealed Classes and Interfaces

Sealed types can be generic:

~~~java
sealed interface Box<T> permits ValueBox, EmptyBox {}

record ValueBox<T>(T value) implements Box<T> {}

record EmptyBox<T>() implements Box<T> {}
~~~

The language checks generic supertype signatures and direct permission. `permits` only lists the **names of the permitted types**, not each generic instantiation:

~~~java
// permits ValueBox<String>, ValueBox<Integer> // Wrong idea.
~~~

Java generics primarily use type erasure; a generic class declaration remains a single permitted type, not a new subtype for each type argument.

## 41. Runnable Program: Generic Sealed Hierarchy

Create **`GenericSealedDemo.java`**:

~~~java
public class GenericSealedDemo {
    sealed interface Maybe<T> permits Present, Absent {}

    record Present<T>(T value) implements Maybe<T> {}

    record Absent<T>() implements Maybe<T> {}

    static <T> String show(Maybe<T> maybe) {
        if (maybe instanceof Present<?> present) {
            return "present:" + present.value();
        }
        if (maybe instanceof Absent<?>) {
            return "absent";
        }
        throw new IllegalStateException();
    }

    public static void main(String[] args) {
        Maybe<String> first = new Present<>("Java");
        Maybe<Integer> second = new Absent<>();

        System.out.println(show(first));
        System.out.println(show(second));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 GenericSealedDemo.java
java GenericSealedDemo
~~~

Stdout:

~~~text
present:Java
absent
~~~

Present and Absent are generic records, permitted to directly implement Maybe<T>. `Maybe.permits` does not need to mention String/Integer.

## 42. Multiple Interfaces: All Sealed Parents Must Be Satisfied

A class can implement multiple interfaces. If it directly implements two sealed interfaces, both direct permission lists must allow that class:

~~~java
sealed interface A permits C {}
sealed interface B permits C {}

final class C implements A, B {}
~~~

If B does not permit C, C cannot directly implement B even though A has permitted it.

In practice, types with multiple contracts require careful review of hierarchy boundaries; sealed permission is **per parent edge**, and there is no “shared permission” when one interface has approved.

## 43. Runnable Program: Implementing Two Sealed Interfaces

Create **`MultipleSealedParentsDemo.java`**:

~~~java
public class MultipleSealedParentsDemo {
    sealed interface Readable permits Combined {
        String read();
    }

    sealed interface Writable permits Combined {
        void write(String value);
    }

    static final class Combined implements Readable, Writable {
        private String value = "";

        @Override
        public String read() {
            return value;
        }

        @Override
        public void write(String value) {
            this.value = value;
        }
    }

    public static void main(String[] args) {
        Combined object = new Combined();
        Readable readable = object;
        Writable writable = object;

        writable.write("Java");
        System.out.println(readable.read());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 MultipleSealedParentsDemo.java
java MultipleSealedParentsDemo
~~~

Stdout:

~~~text
Java
~~~

Both Readable and Writable permit Combined. Sealed does not mean an object is immutable; Combined in this example has mutable state.

## 44. The `non-sealed` Modifier Does Not Automatically Make a Class public

A `non-sealed class` still obeys access modifiers such as package-private, public, and protected/private nested classes depending on location.

Example:

~~~java
sealed class Root permits Branch {}
non-sealed class Branch extends Root {}
~~~

If Branch is package-private, code from another package cannot simply `extends Branch` by relying solely on the non-sealed modifier. Actual extensibility depends on a **combination**: accessibility, constructors, package/module boundaries, and other restrictions.

Read `non-sealed` as “remove the sealing restriction of this branch”, not “drop all Java access rules”.

## 45. A Sealed Type Controls Direct Inheritance, Not Method Overrides

A sealed class can still have:
- `final` methods that cannot be overridden;
- `abstract` methods requiring implementation;
- concrete virtual methods that can be overridden;
- private fields and methods;
- constructors with access restrictions.

`permits` does not replace method visibility/override rules.

If the goal is to forbid overriding a method while still allowing a number of types to subclass, use a `final method` in the right place. If the goal is to restrict **who can subclass**, use a sealed type.

Example:

~~~java
abstract sealed class Task permits LocalTask {
    final String category() {
        return "task";
    }

    abstract void run();
}

final class LocalTask extends Task {
    @Override
    void run() {
    }
}
~~~

LocalTask cannot override `category()` because the method is final, independent of permits.

## 46. Runnable Program: final Method Inside a Sealed Hierarchy

Create **`FinalMethodSealedDemo.java`**:

~~~java
public class FinalMethodSealedDemo {
    static abstract sealed class Task permits PrintTask {
        final String category() {
            return "task";
        }

        abstract String execute();
    }

    static final class PrintTask extends Task {
        @Override
        String execute() {
            return "printed";
        }
    }

    public static void main(String[] args) {
        Task task = new PrintTask();

        System.out.println(task.category());
        System.out.println(task.execute());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 FinalMethodSealedDemo.java
java FinalMethodSealedDemo
~~~

Stdout:

~~~text
task
printed
~~~

Two different layers of control: the sealed root restricts the subclass list; the final method restricts overriding the category behavior.

## 47. Reflection: `isSealed()` and `getPermittedSubclasses()`

Java 17 provides Reflection on `Class`:

- `Class.isSealed()` → true if the class/interface is sealed.
- `Class.getPermittedSubclasses()` → a `Class<?>` array representing the **direct permitted subclasses/implementations** of the sealed type.
- For a type that is not sealed, `getPermittedSubclasses()` returns `null` per the API contract.
- Iteration/display order should be controlled if output/logging needs to be stable.

Do not confuse `getPermittedSubclasses()` with “listing every transitive descendant in the entire program”. Reflection returns the list of direct permissions and does not automatically traverse deeply through non-sealed branches.

### Note

Reflection does not replace the compiler's ability to check source code. It helps with inspection/debugging/framework tooling; do not design a plugin loader based on the assumption that a direct permitted type can be added at runtime.

## 48. Runnable Program: Metadata of a Sealed Hierarchy

Create **`SealedReflectionDemo.java`**:

~~~java
import java.util.Arrays;

public class SealedReflectionDemo {
    sealed interface Root permits Alpha, Beta {}

    record Alpha(int value) implements Root {}

    record Beta(String value) implements Root {}

    public static void main(String[] args) {
        System.out.println("sealed=" + Root.class.isSealed());
        System.out.println("alpha sealed=" + Alpha.class.isSealed());

        String[] names = Arrays.stream(
                Root.class.getPermittedSubclasses())
                .map(Class::getSimpleName)
                .sorted()
                .toArray(String[]::new);

        System.out.println(Arrays.toString(names));
        System.out.println("alpha permits=null=" +
                (Alpha.class.getPermittedSubclasses() == null));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 SealedReflectionDemo.java
java SealedReflectionDemo
~~~

Stdout:

~~~text
sealed=true
alpha sealed=false
[Alpha, Beta]
alpha permits=null=true
~~~

The code sorts names to avoid depending on the array order returned by Reflection. `Alpha` is a final record, not sealed.

## 49. No Need to Create an Instance to Query Permissions

`Root.class.getPermittedSubclasses()` is a metadata query. It does not create `new Alpha()` or `new Beta()`.

The permits list is a **compile-time class hierarchy contract**, not a service registry of object instances. If you need a runtime registry/factory, design a separate API to create variant objects or read configuration.

A permitted class may be abstract or non-sealed, lacking an appropriate constructor for direct instantiation. Therefore, enumerating Class metadata is not equivalent to immediately enumerating valid “object values”.

## 50. Java 17: Handling Variants with `instanceof`

Java 17 has standardized pattern variables with `instanceof`:

~~~java
if (value instanceof Success success) {
    return success.message();
}
~~~

This is a snippet assuming `value`, `Success`, and a method returning String have been declared. With `javac --release 17` without preview enabled, **pattern switch over sealed types is not yet a standard feature**; use polymorphic methods, `if/else instanceof` with a fallback, or `switch` on an appropriate enum. Do not copy record patterns or switch syntax from newer Java releases into a Java 17 demo and treat it as code that compiles by default.

## 51. Runnable Program: Exhaustiveness Using Simple Constructs

Create **`SealedDispatchDemo.java`**:

~~~java
public class SealedDispatchDemo {
    sealed interface Event permits Created, Deleted {}

    record Created(long id) implements Event {}

    record Deleted(long id) implements Event {}

    static String describe(Event event) {
        if (event instanceof Created created) {
            return "created:" + created.id();
        }
        if (event instanceof Deleted deleted) {
            return "deleted:" + deleted.id();
        }
        throw new IllegalStateException("unhandled event");
    }

    public static void main(String[] args) {
        System.out.println(describe(new Created(7)));
        System.out.println(describe(new Deleted(7)));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 SealedDispatchDemo.java
java SealedDispatchDemo
~~~

Stdout:

~~~text
created:7
deleted:7
~~~

The final `throw` is a defensive fallback when writing if-chains in Java 17; one should not claim that the compiler has performed a compile-time exhaustiveness check on this kind of chain like an exhaustive pattern switch from other Java versions.

## 52. Sealed Interface + Polymorphic Method, Without Type Tests

An alternative is to have the sealed interface declare a method:

~~~java
sealed interface Event permits Created, Deleted {
    String describe();
}

record Created(long id) implements Event {
    @Override
    public String describe() {
        return "created:" + id;
    }
}

record Deleted(long id) implements Event {
    @Override
    public String describe() {
        return "deleted:" + id;
    }
}
~~~

The caller invokes `event.describe()` without needing if/instanceof.

### When to Choose This?

- If the behavior **truly belongs to each variant**, polymorphism is appropriate.
- If the operation is only a client-specific visualization/serialization concern, the function can be placed outside the hierarchy.
- If adding many operations to the base interface makes the variants depend on unnecessary services, extract a separate service/controller.

Sealed controls the hierarchy; how behavior is organized is a separate design decision.

## 53. Runnable Program: Sealed Polymorphism

Create **`SealedPolymorphismDemo.java`**:

~~~java
public class SealedPolymorphismDemo {
    sealed interface Operation permits Add, Multiply {
        int compute(int a, int b);
    }

    record Add() implements Operation {
        @Override
        public int compute(int a, int b) {
            return a + b;
        }
    }

    record Multiply() implements Operation {
        @Override
        public int compute(int a, int b) {
            return a * b;
        }
    }

    public static void main(String[] args) {
        Operation add = new Add();
        Operation multiply = new Multiply();

        System.out.println(add.compute(3, 4));
        System.out.println(multiply.compute(3, 4));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 SealedPolymorphismDemo.java
java SealedPolymorphismDemo
~~~

Stdout:

~~~text
7
12
~~~

Permits determines the direct variants, while `compute` provides the shared interface behavior used by callers.

## 54. A Sealed Hierarchy Is Not an Enum

An enum:

~~~java
enum Status {
    NEW, ACTIVE, DONE
}
~~~

is suitable when there are **fixed constant instances** belonging to one type. A sealed interface:

~~~java
sealed interface Status permits New, Active, Done {}

record New() implements Status {}
record Active(long sinceMillis) implements Status {}
record Done(String result) implements Status {}
~~~

allows **variants with different data shapes**, and multiple record instances can be created for Active/Done according to constructor arguments.

### Key Differences

- An enum closes the set of **constant objects**.
- A sealed type closes the set of **direct subtype declarations** (or opens it in a controlled manner via non-sealed).
- A permitted class can create multiple objects.
- Enum `values()` gives the constants; a sealed interface does not automatically have `values()` to produce all variant instances.

Choose based on the domain model, not merely the desire for something “finite”.

## 55. Runnable Program: Enum and Sealed Models Differ

Create **`EnumVsSealedDemo.java`**:

~~~java
public class EnumVsSealedDemo {
    enum SimpleState {
        READY, DONE
    }

    sealed interface DetailedState permits Ready, Done {}

    record Ready() implements DetailedState {}

    record Done(String message) implements DetailedState {}

    public static void main(String[] args) {
        System.out.println(SimpleState.READY);
        System.out.println(SimpleState.values().length);

        DetailedState first = new Done("A");
        DetailedState second = new Done("B");

        System.out.println(first);
        System.out.println(second);
        System.out.println(first.equals(second));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 EnumVsSealedDemo.java
java EnumVsSealedDemo
~~~

Stdout:

~~~text
READY
2
Done[message=A]
Done[message=B]
false
~~~

Sealed permits the Done class; it does not limit it to only a single Done object. An enum constant Done (if present) would be a single fixed instance belonging to the declaring enum.

## 56. Adding a Variant: What Needs to Be Updated?

For example, suppose `Result permits Ok, Error` is published. Adding `Cancelled` means you must:

1. Declare a valid direct implementation and update `permits` if explicit.
2. Satisfy final/sealed/non-sealed, same module/package, and accessibility.
3. Update business dispatch, serialization/UI/schema, and regression tests.
4. Check consumers' assumptions about the variant set and versioning policy.

Extending a **sealed intermediate type** only requires updating the permitted children list at that level, without necessarily modifying the root; a `non-sealed` branch allows adding descendants without editing the root whitelist. Migration patterns and closed/open API trade-offs are taught specifically in the lesson **Comparing Closed Hierarchies with Freely Extensible Classes**.

## 57. API Evolution with a `non-sealed` Extension Point

A sealed root can contain a valid extension branch:

~~~java
sealed interface Message permits KnownMessage, PluginMessage {}
record KnownMessage(String text) implements Message {}
non-sealed interface PluginMessage extends Message {
    String pluginId();
}
~~~

Plugins implement `PluginMessage`, rather than directly implementing the root `Message` themselves. The root only has two **permitted direct branches**, yet the total descendants of the `non-sealed` branch are not finite. This approach requires public visibility, module exports, a compatibility policy, and contract-based fallback. The lesson **Comparing Closed Hierarchies with Freely Extensible Classes** analyzes the hybrid extension vs. open strategy in depth.

## 58. Nested Sealed Types Can Be Easier to Organize Than Multiple Files

An outer class can contain a sealed interface and permitted nested records:

~~~java
final class Results {
    sealed interface Result permits Success, Failure {}

    record Success(String data) implements Result {}

    record Failure(String error) implements Result {}
}
~~~

The members have canonical names and visibility according to outer/nested modifiers. Since they are in the same compilation unit, inferred permits can be used if an explicit list is not needed.

Benefits:
- keeps variants close together for easy review;
- reduces the risk of declarations drifting out of sync across source files;
- scopes can be private/package-private depending on the API;
- simple single-file examples.

However, if each subtype is large, splitting into separate files within the same package/module with explicit permits may be easier to maintain.

## 59. Runnable Program: Nested Sealed Hierarchy

Create **`NestedSealedDemo.java`**:

~~~java
public class NestedSealedDemo {
    static final class Results {
        sealed interface Result permits Success, Failure {}

        record Success(String data) implements Result {}

        record Failure(String reason) implements Result {}
    }

    public static void main(String[] args) {
        Results.Result first = new Results.Success("ok");
        Results.Result second = new Results.Failure("bad");

        System.out.println(first);
        System.out.println(second);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 NestedSealedDemo.java
java NestedSealedDemo
~~~

Stdout:

~~~text
Success[data=ok]
Failure[reason=bad]
~~~

The permitted nested records are in the same source file as the parent sealed interface. `Results.Result` is an implicitly static nested interface according to Java rules.

## 60. Sealed and Interfaces with Default Methods

A sealed interface can still declare default methods:

~~~java
sealed interface Coded permits A, B {
    String code();

    default String display() {
        return "[" + code() + "]";
    }
}

record A() implements Coded {
    @Override
    public String code() {
        return "A";
    }
}

record B() implements Coded {
    @Override
    public String code() {
        return "B";
    }
}
~~~

`permits` does not change method inheritance behavior. Default methods with a body are inherited unless there is a conflict/override.

When using multiple interfaces with defaults of the same signature, subtypes must resolve conflicts according to normal Java rules. Sealed permission does **not** automatically select a default implementation.

## 61. Runnable Program: Default Method in a Sealed Interface

Create **`SealedDefaultMethodDemo.java`**:

~~~java
public class SealedDefaultMethodDemo {
    sealed interface Coded permits A, B {
        String code();

        default String display() {
            return "[" + code() + "]";
        }
    }

    record A() implements Coded {
        @Override
        public String code() {
            return "A";
        }
    }

    record B() implements Coded {
        @Override
        public String code() {
            return "B";
        }
    }

    public static void main(String[] args) {
        Coded first = new A();
        Coded second = new B();

        System.out.println(first.display());
        System.out.println(second.display());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 SealedDefaultMethodDemo.java
java SealedDefaultMethodDemo
~~~

Stdout:

~~~text
[A]
[B]
~~~

Records provide the required `code()`; shared formatting lives in the default method.

## 62. Sealed Does Not Prevent Creating an Anonymous Subclass When Not Permitted

The anonymous subclass syntax:

~~~java
Base value = new Base() {
    // ...
};
~~~

will create an **anonymous subclass** of Base. If Base is sealed and the anonymous class is not among the permitted direct subtype declarations, this expression will be rejected by sealing rules.

With a sealed interface:

~~~java
sealed interface Action permits KnownAction {}

final class KnownAction implements Action {}

// Action a = new Action() {}; // Invalid: anonymous direct implementation.
~~~

Anonymous classes do not have canonical names to be declared arbitrarily in the permits list the way ordinary named permitted types do; do not use them to bypass restrictions.

### Using a Permitted Branch

If one-off implementations are needed, design a non-sealed extension interface/class below the sealed root and implement/extend that branch according to the appropriate context.

## 63. Sealed and Lambdas: Need to Distinguish SAM Targets

A sealed interface having one abstract method looks on the surface like a functional interface:

~~~java
sealed interface Task permits BuiltinTask {
    void run();
}
~~~

However, Java sealed interfaces **are not valid functional interfaces** under the functional interface semantics required for a lambda target. There is no way for a lambda implementation to be listed as a permitted direct subtype of a sealed interface.

Therefore:

~~~java
// Task task = () -> System.out.println("run"); // Invalid.
~~~

If a lambda callback is needed, use **a functional non-sealed interface**, such as `Runnable` or a separate `@FunctionalInterface` interface, at the appropriate contract.

**Design rule:** Sealed roots are used to restrict **implementing types**; functional interfaces are used to allow clients to supply lambdas flexibly. The two purposes can conflict on a single interface.

## 64. Runnable Program: Sealed Type Accepting Runnable as a Component

Instead of using a lambda directly as an instance of the sealed interface, you can wrap a Runnable inside a permitted record:

Create **`SealedWithLambdaDemo.java`**:

~~~java
public class SealedWithLambdaDemo {
    sealed interface Command permits NamedCommand, CallbackCommand {
        void execute();
    }

    record NamedCommand(String name) implements Command {
        @Override
        public void execute() {
            System.out.println("named:" + name);
        }
    }

    record CallbackCommand(Runnable action) implements Command {
        CallbackCommand {
            java.util.Objects.requireNonNull(action);
        }

        @Override
        public void execute() {
            action.run();
        }
    }

    public static void main(String[] args) {
        Command first = new NamedCommand("A");
        Command second = new CallbackCommand(
                () -> System.out.println("callback"));

        first.execute();
        second.execute();
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 SealedWithLambdaDemo.java
java SealedWithLambdaDemo
~~~

Stdout:

~~~text
named:A
callback
~~~

The sealed interface still has only two permitted variants. The lambda implements Runnable, while the permitted CallbackCommand record wraps Runnable and implements Command.

## 65. Error: Missing Modifier on a Direct Permitted Class

Incorrect example:

~~~java
sealed class Parent permits Child {}

// class Child extends Parent {} // Invalid: missing final/sealed/non-sealed.
~~~

Correct:

~~~java
sealed class Parent permits Child {}

final class Child extends Parent {}
~~~

Or if it needs to be opened:

~~~java
sealed class Parent permits Child {}

non-sealed class Child extends Parent {}
~~~

Or to continue restricting:

~~~java
sealed class Parent permits Child {}

sealed class Child extends Parent permits Grandchild {}

final class Grandchild extends Child {}
~~~

Do not fix it by removing `sealed` from Parent unless you truly want to **open up the API**; the modifier on a permitted type expresses an important architectural decision.

## 66. Error: Subtype Not Listed in permits

Conceptual example:

~~~java
sealed interface Shape permits Circle {}

record Circle(int radius) implements Shape {}

// record Square(int side) implements Shape {} // Compile error.
~~~

`Square` directly implements Shape, but is not permitted by Shape.

To add Square:
- update `permits Circle, Square`;
- declare Square within the proper source/module/package boundary;
- ensure the subtype conforms to modifier semantics (records are implicitly final);
- update tests/API behavior.

No annotation or reflection API replaces directly editing the sealed hierarchy declaration.

## 67. Error: `permits` Lists a Type That Is Not a Direct Subtype

Incorrect:

~~~java
sealed interface Root permits A, B {}

non-sealed interface A extends Root {}

// class B implements A {} // B does not directly implement Root.
~~~

The name B appears in permits, but its declaration only implements A; thus B **is not a direct permitted child of Root**.

Correct:

~~~java
sealed interface Root permits A {}

non-sealed interface A extends Root {}

class B implements A {}
~~~

If you want B to be a direct implementor, change the relationship declaration accordingly and check for conflicts across the interface edges.

## 68. Error: Using `non-sealed` Without a Direct Sealed Supertype

Incorrect:

~~~java
// non-sealed class Helper {} // Does not directly extend a sealed type.
~~~

Correct:

~~~java
sealed class Parent permits Helper {}

non-sealed class Helper extends Parent {}
~~~

Similarly, a non-sealed interface must directly extend an appropriate sealed interface. `non-sealed` is not a synonym for “public/extensible”.

## 69. Error: A Sealed Type with No Permitted Direct Subtype

A sealed type is designed to permit a set of direct subtypes. If the declaration has no permits clause and the compiler cannot infer allowed direct subtypes in the same compilation unit, the source may be rejected for having no valid permitted subclasses.

In practice:
- declare the permitted types;
- or if you want absolutely no subclasses, use `final class` for a concrete class;
- for an interface that needs a contract but currently has no implementations, consider whether it truly needs to be sealed right now.

Do not use `sealed` as an alternative way of writing `final`. Those are two different intents.

## 70. Compile-Time Tests for the Hierarchy

Many sealed/permits restrictions can be verified right at compile time. Proactively test:
- a child listed in permits with a valid modifier → compiles.
- a direct child not in permits → compile error.
- a listed child that does not directly extend/implement the parent → compile error.
- a child using plain class modifiers without final/sealed/non-sealed → compile error.
- non-sealed without a sealed direct supertype → compile error.
- wrong package/module boundary → compile error.
- a child attempting to extend a final leaf → compile error.
- a child continuing to extend a sealed branch while not permitted by the branch → compile error.

Negative tests must run in a separate environment and **expect javac to exit nonzero**; do not mix invalid snippets into programs intended to run and demonstrate stdout.

## 71. Runnable Program: Unit-Like Assertions for Variants

Create **`SealedContractTestDemo.java`**:

~~~java
public class SealedContractTestDemo {
    sealed interface Expr permits IntValue, Negate {
        int evaluate();
    }

    record IntValue(int value) implements Expr {
        @Override
        public int evaluate() {
            return value;
        }
    }

    record Negate(Expr value) implements Expr {
        @Override
        public int evaluate() {
            return -value.evaluate();
        }
    }

    static void check(int actual, int expected) {
        if (actual != expected) {
            throw new AssertionError(
                    actual + " != " + expected);
        }
    }

    public static void main(String[] args) {
        Expr one = new IntValue(5);
        Expr two = new Negate(one);

        check(one.evaluate(), 5);
        check(two.evaluate(), -5);
        check(new Negate(two).evaluate(), 5);

        System.out.println("all behavior tests PASS");
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 SealedContractTestDemo.java
java SealedContractTestDemo
~~~

Stdout:

~~~text
all behavior tests PASS
~~~

The compiler verifies the direct permitted types; tests verify the business method behavior, which the compiler does not prove on its own.

## 72. Does Sealed Make Code Thread-Safe or Immutable?

No. Sealed only restricts the type hierarchy. A permitted non-sealed class can have mutable state; a final permitted class can also have mutable fields if defined that way.

Example:

~~~java
sealed interface Counter permits MutableCounter {}

final class MutableCounter implements Counter {
    int value;

    void increment() {
        value++;
    }
}
~~~

This is a mutable class even though Counter is sealed and MutableCounter is final. `value++` is not atomic under concurrent access.

Separate three concepts:
- **Sealing:** who is allowed to directly extend/implement?
- **Final field/immutability:** can state mutate?
- **Thread safety:** how are concurrent operations safeguarded?

Do not use one keyword to draw conclusions about the other two concerns.

## 73. API Design: Sealed Hierarchy or Ordinary Extensible Interface?

Choose sealed if the team/module truly owns **a bounded set of direct variants** and wants consumers to recognize all major branches. Choose an ordinary open interface if the goal is to allow many externally implemented plugins that cannot be listed in advance. Need both controlled built-in variants and plugins? Use an appropriate permitted `non-sealed` extension point, as in the earlier section. The lesson **Comparing Closed Hierarchies with Freely Extensible Classes** presents the decision tree, OCP, composition, and versioning plans; in this syntax lesson, you only need to understand how the declarations carry out that choice.

## 74. Versioning: Adding a Branch Can Affect Consumers

Adding `Pending` to permitted direct variants may leave consumers unable to handle the new branch, alter serialization schemas, reflection metadata, or assumptions about exhaustiveness. Therefore, release notes, tests, and a compatibility strategy are needed; the compiler does not automatically make every business method understand the new variant. The lessons **Comparing Closed Hierarchies with Freely Extensible Classes** and **When sealed Is Appropriate for Modeling Value Types** analyze API evolution in depth from user and domain-design perspectives.

## 75. Beware of Public Sealed Classes with Overly Broad Constructors

A `public sealed class`, if **concrete** and having an accessible constructor, can still be instantiated directly; `sealed` **is not synonymous with** `abstract`. If the domain only allows specialized variants, consider `abstract sealed class` and a constructor with appropriate visibility.

In all cases, constructors must protect invariants, even when only permitted children are allowed to extend the root. `permits` does not grant permission to invoke a private constructor, does not replace validation, and does not guarantee immutability. Details on shared state/constructors belong to the lesson **Combining sealed with Abstract Classes, Records, and Enums**.

## 76. Reflection and the List of Transitive Descendants

`getPermittedSubclasses()` returns direct permissions. If you want to build a tree report, you can recurse through **the children that remain sealed**; upon encountering:
- a final leaf: no subclasses;
- a non-sealed branch: all future descendant types cannot be inferred solely from root permits;
- a sealed child: has its own list of direct permitted subtypes.

Therefore, a code generation tool can present **controlled branches**, but should not claim to “list all runtime subclasses” if a non-sealed extension point exists.

## 77. Runnable Program: Inspecting Each Branch via Metadata

Create **`SealedHierarchyMetadataDemo.java`**:

~~~java
public class SealedHierarchyMetadataDemo {
    sealed interface Root permits Leaf, Branch {}

    record Leaf(int n) implements Root {}

    non-sealed interface Branch extends Root {}

    public static void main(String[] args) {
        System.out.println("root sealed=" +
                Root.class.isSealed());
        System.out.println("leaf sealed=" +
                Leaf.class.isSealed());
        System.out.println("branch sealed=" +
                Branch.class.isSealed());

        System.out.println("root direct allowed=" +
                Root.class.getPermittedSubclasses().length);
        System.out.println("branch permits=null=" +
                (Branch.class.getPermittedSubclasses() == null));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 SealedHierarchyMetadataDemo.java
java SealedHierarchyMetadataDemo
~~~

Stdout:

~~~text
root sealed=true
leaf sealed=false
branch sealed=false
root direct allowed=2
branch permits=null=true
~~~

Root is sealed, Leaf is a final record, and Branch is a non-sealed interface. Only Root has a direct permits list in Reflection metadata.

## 78. Common Misconceptions

| Misconception | What Is True in Java 17 |
| --- | --- |
| `sealed` forbids all subclasses | It allows direct subtypes listed in the permits list |
| `sealed` is the same as `final` | Final closes completely; sealed opens in a controlled manner |
| `permits` automatically makes that class extend the parent | The child must declare the relation directly |
| A listed child can omit a modifier | An ordinary direct child must be final/sealed/non-sealed |
| `non-sealed` means every class is public | Accessibility rules still apply |
| `non-sealed` can be used on any class | Requires a sealed direct supertype |
| `final interface` is valid | Interfaces cannot use the final modifier |
| Parent needs to list all indirect descendants | Only direct subtypes |
| Java infers permits by scanning the package | Inference is limited to the same compilation unit |
| A subclass in a different package in an unnamed module is still allowed | Must be in the same package |
| A subclass in a different named module is still allowed | Must be in the same named module |
| `permits` bypasses constructor access rules | No |
| A sealed class is abstract by default | No; the class can be concrete |
| A sealed interface automatically has `values()` | No, only enums have the values() API |
| Permits lists enum constants instead of the enum type | Must list the type |
| A record must be declared `final` when permitted | Records are implicitly final |
| A sealed interface with a single SAM can use a lambda directly like a functional interface | A sealed interface is not a valid functional lambda target |
| A sealed type is automatically deep immutable | No |
| A sealed type is automatically thread-safe | No |
| `getPermittedSubclasses` returns all transitive subclasses | Only direct permissions |
| `instanceof` type patterns are a preview feature in Java 17 | Standardized and usable |
| Pattern switch is a non-preview standard feature in Java 17 | No; avoid in standard Java 17 examples |
| Adding a variant does not affect the API | It can affect consumers and behavior |
| Sealed is a good choice for every plugin API | Plugins often need an open extension point |

## 79. Exercise 1 — Declaring a sealed class

Requirement: Vehicle only permits Car and Truck to directly extend it, and both are leaf classes.

**Answer:**

~~~java
sealed class Vehicle permits Car, Truck {}

final class Car extends Vehicle {}

final class Truck extends Vehicle {}
~~~

Clearly explain why `Vehicle` does not necessarily have to be abstract: sealed restricts subclasses, not instantiation if the class is concrete and its constructor is accessible.

## 80. Exercise 2 — Sealed Interface with Records

Requirement: Response has variants Success(String) and Failure(String).

**Answer:**

~~~java
sealed interface Response permits Success, Failure {}

record Success(String value) implements Response {}

record Failure(String error) implements Response {}
~~~

Both records are automatically final according to language rules. Add validation if null or blank input is disallowed.

## 81. Exercise 3 — Child Missing a Modifier

~~~java
sealed class A permits B {}

// class B extends A {}
~~~

**Answer:** If uncommented, B is missing one of `final`, `sealed`, or `non-sealed`. If no subclasses of B are desired, write `final class B extends A {}`.

## 82. Exercise 4 — Indirect Descendant

~~~java
sealed class A permits B {}
non-sealed class B extends A {}
class C extends B {}
~~~

Is C valid even though it is not in A.permits?

**Answer:** Yes. C does not directly extend A; rather, it extends B, which is a non-sealed branch.

## 83. Exercise 5 — Listing at the Wrong Level

~~~java
sealed class A permits B, C {}
non-sealed class B extends A {}
class C extends B {}
~~~

**Answer:** Invalid because C is not a direct subclass of A. Change to A permits B, removing C from the root list.

## 84. Exercise 6 — Inferred permits

~~~java
sealed interface Event {}
record Started(int id) implements Event {}
record Stopped(int id) implements Event {}
~~~

All three are declared in a single compilation unit, without explicit permits.

**Answer:** The compiler can infer Started and Stopped as direct permitted implementations, provided the remaining rules are satisfied.

## 85. Exercise 7 — Different Package in an Unnamed Module

Result is declared in package a; record Ok is in package b; both are in an unnamed module. Parent writes `permits b.Ok`.

**Answer:** Invalid: a direct permitted subclass/implementation must be in the same package when the sealed type belongs to an unnamed module. Move them to the same package or design an appropriate named module if different packages are truly needed.

## 86. Exercise 8 — Named Module

A sealed interface belongs to named module M, and the permitted record is in a different package but also in module M; accessibility is valid.

**Answer:** Can be valid. The named-module rule requires the same module, not necessarily the same package. Proper direct inheritance/visibility/modifiers are still required.

## 87. Exercise 9 — Subinterface

~~~java
sealed interface Root permits Child {}
// final interface Child extends Root {} // Invalid.
~~~

**Answer:** An interface cannot be final. Use `sealed interface Child extends Root permits Leaf {}` or `non-sealed interface Child extends Root {}`, depending on the extension policy.

## 88. Exercise 10 — Is Sealed Immutable?

A `final class Counter implements SealedCounter` holds `int count` and an `increment()` method.

**Answer:** Neither automatically immutable nor thread-safe. final only blocks subclassing, and sealed only controls the permitted hierarchy. Concurrent increments must consider synchronization separately.

## 89. Exercise 11 — Reflection

`Root.class.isSealed()` is true, and `Root.class.getPermittedSubclasses()` has length 2. Does this prove there are exactly two object instances of Root?

**Answer:** No. The metadata states there are two direct permitted subtype declarations, not a limit on the number of objects created by each subtype. If a non-sealed branch exists, indirect descendants can also expand.

## 90. Exercise 12 — Sealed Interface and Lambdas

Suppose there is a sealed interface Task with method `void run()` and a permitted record wrapper. Can you write `Task t = () -> ...;` directly?

**Answer:** No. A sealed interface is not a valid functional interface target for a lambda. You can use `Runnable` as a callback and wrap it in a permitted record `CallbackTask(Runnable action) implements Task`.

## 91. Exercise 13 — Creating a Class Outside permits

~~~java
sealed interface Expression permits Literal {}
record Literal(int value) implements Expression {}
// record Add(Expression a, Expression b) implements Expression {}
~~~

**Answer:** If Add is uncommented, the compiler rejects it because Add is not in permits. To add the variant, declare `permits Literal, Add` and review the expression-handling logic.

## 92. Exercise 14 — Final Leaf

~~~java
sealed class Base permits Leaf {}
final class Leaf extends Base {}
// class More extends Leaf {} // Invalid.
~~~

**Answer:** More cannot extend Leaf because Leaf is final, even though every type is in the same compilation unit and Base has permitted Leaf.

## 93. Exercise 15 — Opening an Extension Branch

Design Command with two branches: Builtin (closed) and Plugin (for third parties to implement).

**Suggested answer:**

~~~java
sealed interface Command permits Builtin, Plugin {}

record Builtin(String name) implements Command {}

non-sealed interface Plugin extends Command {
    String pluginId();
}
~~~

Third-party classes will `implements Plugin` according to the accessibility contract, rather than implementing Command directly.

## 94. Exercise 16 — API Impact

Initially sealed Result permits Success, Failure; later Cancelled is added.

**Answer:** Update the permits list and declaration, review business handlers, schemas, tests, and compatibility. The sealed constraint does not automatically make clients understand the behavior of Cancelled.

## 95. Exercise 17 — Sealed or Enum?

There are only the states NEW, ACTIVE, DONE; they carry no different data.

**Answer:** An enum is usually simpler. If each state variant contains a different data shape such as Active(startTime) and Done(result), a sealed interface + records may be more appropriate.

## 96. Exercise 18 — Common Methods of a Sealed Superclass

An abstract sealed class has a protected constructor and a final method category(), and permitted subclasses override abstract execute().

**Answer:** Valid. Sealed controls the direct subclass list; the final method prevents overriding; the abstract method still forces concrete subclasses to implement it.

## 97. Workflow for Designing a permits List

**Step 1 — Name the root type.** What category/abstraction does it represent?

**Step 2 — Decide closed or open.** If arbitrary extensions are needed, usually do not use a sealed root, or design a non-sealed branch.

**Step 3 — Identify direct variants.** List the exact class/interface types that directly extend/implement the root.

**Step 4 — Choose an abstract/concrete root.** Sealed is not automatically abstract; decide on constructors/base behavior.

**Step 5 — Choose a modifier for each permitted child.** Final to terminate; sealed to restrict further; non-sealed to open the branch. For records/enums, special rules apply.

**Step 6 — Choose explicit or inferred permits.** Inference applies only when the direct types are in the same compilation unit; across multiple files, use explicit.

**Step 7 — Check package/module.** Same named module; unnamed module → same package.

**Step 8 — Check accessibility/constructors.** A listed name does not waive inheritance access rules.

**Step 9 — Check nested hierarchy.** A sealed child branch has its own permits list; non-sealed opens up descendants.

**Step 10 — Test compiler and runtime.** Negative compile tests and behavior tests for each variant.

**Step 11 — Consider versioning.** Adding a direct subtype is a contract change that requires review.

**Step 12 — Consider alternative models.** Enum, ordinary interface, named class, composition, or sealed+records.

## 98. End-of-Lesson Checklist

- [ ] I know that Java 17 supports sealed class/interface without needing preview.
- [ ] I can write `sealed class Parent permits ChildA, ChildB`.
- [ ] I can write `sealed interface Parent permits A, B`.
- [ ] I can distinguish `permits` from `extends` and `implements`.
- [ ] I know that permits applies only to direct subtypes.
- [ ] I do not put grandchildren in the root permits list.
- [ ] I know that a direct child must appear in explicit permits if the parent has a list.
- [ ] I know that a direct child class chooses final/sealed/non-sealed.
- [ ] I know that a direct child interface chooses sealed/non-sealed, not final.
- [ ] I know that a record is implicitly final, making it a natural permitted leaf.
- [ ] I know that a permitted enum lists the enum type, not the enum constants.
- [ ] I understand that non-sealed opens the branch rather than opening the root's direct permits.
- [ ] I know that a sealed child has its own permits list.
- [ ] I know that a sealed root can be concrete or abstract.
- [ ] I do not confuse a final class with a sealed class.
- [ ] I know that non-sealed cannot be used arbitrarily without a direct sealed supertype.
- [ ] I know that Java infers permits when direct types are in the same compilation unit.
- [ ] I know that inference does not automatically scan the entire package.
- [ ] I know that a named module requires permitted direct types to be in the same module.
- [ ] I know that an unnamed module requires the same package.
- [ ] I do not assume that permits eliminates visibility/constructor rules.
- [ ] I understand that sealed does not automatically mean immutable, thread-safe, or singleton.
- [ ] I know that a generic sealed interface can have permitted generic records.
- [ ] I know `Class.isSealed()`.
- [ ] I know that `Class.getPermittedSubclasses()` returns direct types, not instances.
- [ ] I know that `instanceof` patterns are standard in Java 17.
- [ ] I do not use pattern switch/record patterns as Java 17 non-preview syntax.
- [ ] I know that a sealed interface cannot be used directly as a lambda target.
- [ ] I know how to design a wrapper record with Runnable if a callback is needed.
- [ ] I know when a sealed hierarchy is better than an enum.
- [ ] I know when an ordinary extensible interface is better than sealed.
- [ ] I evaluate API evolution when modifying the permits list.
- [ ] I can explain the compiler errors in the exercises.
- [ ] I verify the entire hierarchy and contracts with tests.

**Conclusion:** `sealed` and `permits` in Java 17 define the **direct extension boundary of a data type**. The parent has the authority to declare the permitted direct classes/interfaces, while each permitted type must actively choose its continuation policy for further extension (`final`, `sealed`, `non-sealed`, or the special implicit semantics of record/enum). The list can be written explicitly or inferred when direct types are in the same compilation unit; the same-module/same-package restrictions and accessibility rules always apply. Use sealed to model **controlled hierarchies**, without confusing it with immutability, singletons, or a runtime registry.
