# Combining sealed with abstract classes, records, and enums in Java 17+

> **Module:** Java Core — class/object  
> **Group:** Sealed classes  
> **Topic:** Combining sealed with abstract classes, records, and enums  
> **Environment:** Java 17+ with standard language features; programs run with regular `javac`/`java`, without enabling preview.

## 1. Mental map: sealed controls the type tree, not the entire object

`sealed` is a modifier used to **restrict which classes/interfaces are permitted to directly extend or implement a type**. Since Java 17, sealed classes and sealed interfaces are standard Java features.

The point of this lesson is not just learning the `sealed ... permits ...` syntax, but how it interacts with:

- **`abstract class`**: a class that cannot be instantiated directly, typically defines shared state/behavior, and can itself be `sealed` or `non-sealed`.
- **`record`**: a special, final class that implicitly extends `java.lang.Record` and cannot extend a custom class; **it can implement a sealed interface**.
- **`enum`**: a special class that implicitly extends `java.lang.Enum<E>` and cannot extend a custom class; **it can implement a sealed interface**. If it has constant-specific class bodies, the enum has its own additional implicit sealing characteristics.
- **`interface`**: does not carry instance state like an ordinary class, allowing a sealed root to encompass multiple kinds of concrete representations, making it well-suited for combining records, enums, and class hierarchies.

**Key design takeaway:** When you want a type family consisting of **record + enum + abstract class**, use a **sealed interface as the root**. A record/enum cannot inherit from a sealed abstract class because neither is allowed to extend an arbitrary class.

The big picture:

~~~text
sealed interface Event
    |
    +-- record TextEvent(...) implements Event        [implicitly final]
    |
    +-- enum SystemEvent implements Event             [final or implicitly sealed]
    |
    +-- sealed abstract class Command implements Event
            |
            +-- final class RetryCommand extends Command
            |
            +-- final class StopCommand extends Command
~~~

A sealed interface restricts **direct implementors**. A sealed abstract class restricts **direct subclasses**. Permitted subtypes must explicitly specify whether they **stop inheritance** (`final`), **continue restricting** (`sealed`), or **reopen inheritance** (`non-sealed`) — except for special types like records and enums that have implicit rules.

## 2. Recap of sealed, permits, and direct subtypes

Consider:

~~~java
sealed interface Message permits TextMessage, SystemMessage {
}

record TextMessage(String value) implements Message {
}

enum SystemMessage implements Message {
    START, STOP
}
~~~

This is a declaration fragment. `Message` only allows `TextMessage` and `SystemMessage` as **direct implementors** according to the stated declaration.

Another class in the source:

~~~java
final class OtherMessage implements Message {
}
~~~

**Intentionally does not compile**, because OtherMessage is not in the permitted direct subtypes of Message.

### 2.1. Understanding the word “direct”

If:

~~~java
sealed interface Animal permits Mammal {
}

non-sealed interface Mammal extends Animal {
}

final class Dog implements Mammal {
}
~~~

then Dog is not a direct implementor of Animal; it directly implements Mammal. Mammal is `non-sealed`, so the hierarchy along this branch is open under normal rules. Animal still only permits the direct subtype Mammal.

This point is important because a sealed root **does not guarantee that every descendant belongs to a strictly closed set** if a permitted branch is `non-sealed`.

### 2.2. Directly extending/implementing a sealed parent requires the proper state

An ordinary permitted direct subtype must declare its next state:

- `final`: no further subclasses.
- `sealed`: continues to explicitly specify which direct subclasses/implementors are permitted.
- `non-sealed`: removes the sealing restriction for that branch.

An ordinary class in a direct permitted hierarchy cannot omit all three modifiers and expect Java to guess. For record/enum, implicit rules satisfy this special requirement, so `final`/`non-sealed` should not be arbitrarily attached to record/enum declarations.

### 2.3. Sealed does not replace access control

`permits` determines **who has permission to be a direct subtype**; it does not automatically make private members public, does not bypass package/module accessibility, and does not replace `abstract`. A sealed class can still have `private` constructors/fields; an abstract class still cannot be instantiated directly.

### 2.4. In which programs should it be used?

Sealed is suitable when domain variants are determined for the code version: command types, algebraic data types, workflow states, AST nodes, success/failure results, and internal protocols. For a plugin ecosystem needing arbitrary extensibility, a `non-sealed` branch or an open root interface may be more suitable.

## 3. Java 17: a sealed interface is a flexible composition point

Suppose an API returns three kinds of events:

- A concise data object: record `TextEvent`.
- Named predefined signals: enum `SystemSignal`.
- A family of commands with shared logic: sealed abstract class `Command`.

All of them can implement an interface:

~~~java
sealed interface Event
        permits TextEvent, SystemSignal, Command {
    String describe();
}

record TextEvent(String text) implements Event {
    public String describe() {
        return "text:" + text;
    }
}

enum SystemSignal implements Event {
    START, STOP;

    public String describe() {
        return "signal:" + name();
    }
}

abstract sealed class Command implements Event
        permits RetryCommand, StopCommand {
}

final class RetryCommand extends Command {
    public String describe() {
        return "retry";
    }
}

final class StopCommand extends Command {
    public String describe() {
        return "stop";
    }
}
~~~

This is an **illustrative set of type declarations**, not a standalone class with `main`. All of `TextEvent`, `SystemSignal`, and `Command` are direct permitted subtypes of Event. RetryCommand and StopCommand are direct subclasses of Command, not direct subtypes of Event.

### 3.1. Why do records and enums work well with interfaces?

Java allows records/enums to implement interfaces. A record already has superclass `java.lang.Record` and an enum already has superclass `java.lang.Enum<E>`, so they cannot extend `Command` or another custom class. An interface directly solves the single-class inheritance constraint.

### 3.2. Why is an abstract class an intermediate branch?

`Command` can hold reusable state/constructors/validation/helper methods for command implementations. However, because Command is neither a record nor an enum, subclasses of Command can use `extends Command` normally.

### 3.3. Inheritance permission does not take “shortcuts”

`final class PluginCommand extends Command` will be rejected if it is not in Command's permits list. Having `Command implements Event` is not sufficient permission for an arbitrary class to extend Command.

## 4. Complete program 1 — a sealed root mixing three kinds

Create the file **`SealedMixedFamilyDemo.java`**:

~~~java
public class SealedMixedFamilyDemo {
    sealed interface Event
            permits TextEvent, SystemSignal, Command {
        String describe();
    }

    record TextEvent(String text) implements Event {
        @Override
        public String describe() {
            return "text:" + text;
        }
    }

    enum SystemSignal implements Event {
        START, STOP;

        @Override
        public String describe() {
            return "signal:" + name();
        }
    }

    abstract static sealed class Command implements Event
            permits RetryCommand, StopCommand {
        protected final String target;

        Command(String target) {
            this.target = target;
        }
    }

    static final class RetryCommand extends Command {
        RetryCommand(String target) {
            super(target);
        }

        @Override
        public String describe() {
            return "retry:" + target;
        }
    }

    static final class StopCommand extends Command {
        StopCommand(String target) {
            super(target);
        }

        @Override
        public String describe() {
            return "stop:" + target;
        }
    }

    public static void main(String[] args) {
        Event[] events = {
            new TextEvent("hello"),
            SystemSignal.START,
            new RetryCommand("job-7"),
            new StopCommand("worker-2")
        };

        for (Event event : events) {
            System.out.println(event.describe());
        }

        System.out.println("Text is record = "
                + TextEvent.class.isRecord());
        System.out.println("Signal is enum = "
                + SystemSignal.class.isEnum());
        System.out.println("Command is sealed = "
                + Command.class.isSealed());
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 SealedMixedFamilyDemo.java
java SealedMixedFamilyDemo
~~~

**Stdout:**

~~~text
text:hello
signal:START
retry:job-7
stop:worker-2
Text is record = true
Signal is enum = true
Command is sealed = true
~~~

### 4.1. Why does the TextEvent record compile?

`TextEvent` implements Event and is permitted by Event. A record is implicitly final; it is neither allowed nor required to specify the `final` modifier in the record declaration.

### 4.2. Why does the SystemSignal enum compile?

An enum can implement Event. This is an enum without constant-specific class bodies, so it is implicitly final, satisfying the direct permitted subtype rule. The signal instances remain START and STOP.

### 4.3. Why is Command both abstract and sealed?

`abstract` forbids creating `new Command(...)`; `sealed` forbids direct subclasses other than RetryCommand and StopCommand. They control **two different aspects**: instantiability and subclass permissions.

### 4.4. Why are the leaf subclasses final?

RetryCommand and StopCommand close off the two branches of the Command tree, disallowing further arbitrary subclasses. When a class directly extends a sealed parent, it requires final/sealed/non-sealed according to the rules.

## 5. Abstract class with sealed: two independent roles

`abstract` describes **that instances cannot be created directly** and can declare abstract methods. `sealed` describes **the permitted direct subtypes**.

A class can be both abstract and sealed:

~~~java
abstract sealed class Shape permits Circle, Square {
    abstract double area();
}

final class Circle extends Shape {
    private final double radius;

    Circle(double radius) {
        this.radius = radius;
    }

    @Override
    double area() {
        return Math.PI * radius * radius;
    }
}

final class Square extends Shape {
    private final double side;

    Square(double side) {
        this.side = side;
    }

    @Override
    double area() {
        return side * side;
    }
}
~~~

This is a fragment. `Shape` has a common contract and cannot be instantiated directly. Only Circle/Square can directly extend Shape.

### 5.1. Can a class be sealed without being abstract?

Yes. A non-abstract sealed ordinary class can still be instantiated directly if its constructor is accessible:

~~~java
sealed class Base permits Child {
    Base() {
    }
}

final class Child extends Base {
}
~~~

You can create `new Base()` in any scope with access to the constructor. `sealed` **does not automatically make a class abstract**.

### 5.2. Can a class be abstract without being sealed?

Yes. `abstract class OpenBase` can be extended by any valid class according to package/access rules; the compiler does not require `permits` unless the superclass is sealed.

### 5.3. Can a class be abstract final?

No. `abstract` means the class needs to be subclassed to complete its behavior; `final` forbids subclassing. The two modifiers are incompatible. However, `abstract sealed` is a meaningful combination: it requires subclassing while restricting the subclasses.

### 5.4. Constructor of an abstract sealed class

An abstract class has constructors for subclasses to call `super(...)`. That does not allow clients to create an abstract instance directly. A constructor can also establish shared invariants; remember not to call overridable methods before subclass initialization is complete.

### 5.5. Record/enum cannot extend Shape

If you try to write `record CircleRecord(double radius) extends Shape` or `enum ShapeKind extends Shape`, syntax/type rules do not allow it. A sealed class is only suitable as the base of **ordinary classes**.

## 6. Why can't a record inherit from a sealed abstract class?

A record is a special class, yet it always implicitly has the superclass `java.lang.Record`. It cannot specify `extends CustomBase`, even if CustomBase is sealed, abstract, concrete, or listed in the permits list.

Incorrect:

~~~java
abstract sealed class Node permits Literal {
}

record Literal(int value) extends Node {
}
~~~

This is **code that intentionally does not compile**. A record header does not have an extends clause like an ordinary class; it can only implement interfaces.

Even if you specify Node permits Literal, Java still cannot make Literal a direct subclass of Node because a record cannot extend Node. `permits` does not “force” Java to create an invalid inheritance relationship.

### 6.1. How to fix it

Make the shared contract a **sealed interface**:

~~~java
sealed interface Node permits Literal, OperatorNode {
}

record Literal(int value) implements Node {
}

abstract non-sealed class OperatorNode implements Node {
}
~~~

These are valid fragments (with appropriate package/module visibility). The Literal record implements Node; the OperatorNode abstract class also implements Node. Both types are direct subtypes of Node.

### 6.2. A record can still hold an ordinary class as a component

A record can hold `Node`/`OperatorNode` references as data, for example `record Wrapper(Node content) implements Node` if Wrapper is also validly permitted. This is **composition**, not Java class inheritance.

### 6.3. Why is choosing a sealed interface better?

A sealed interface describes a **domain category** rather than forcing every implementation to share the same superclass. Records, enums, and ordinary classes can all satisfy the interface contract, even when each kind must obey its own superclass rules.

### 6.4. An abstract class can implement the interface and serve as an intermediate ancestor

A sealed interface can permit an abstract class. That abstract class can be sealed, non-sealed, or designed with subclasses following the rules. Other records/enums **do not need** to go through the abstract class; instead, they implement the root interface directly.

## 7. An enum also cannot extend a sealed abstract class

An enum declaration does not support a custom extends clause because every enum implicitly extends `java.lang.Enum<E>`.

Incorrect:

~~~java
abstract sealed class Message permits Status {
}

enum Status extends Message {
    OK, ERROR
}
~~~

This is **code that intentionally does not compile**. An enum cannot extend an arbitrary class.

Correct:

~~~java
sealed interface Message permits Status, Payload {
}

enum Status implements Message {
    OK, ERROR
}

record Payload(String text) implements Message {
}
~~~

### 7.1. An enum has fixed instances

When implementing a sealed interface, Status still only has the declared OK/ERROR constants. `sealed interface Message` does not automatically allow creating more Status constants with `new`.

### 7.2. An enum can implement multiple interfaces

If an additional capability contract is needed:

~~~java
interface Coded {
    String code();
}

enum Status implements Message, Coded {
    OK, ERROR;

    public String code() {
        return name();
    }
}
~~~

This is a fragment assuming Message already permits Status. Sealed constraints still apply to Message; the Coded interface is an independent contract.

### 7.3. Do not confuse an enum's internal constant subclasses with external extension

An enum constant can have its own class body, creating a compiler-controlled anonymous subtype of the enum itself. This does not allow external code to extend Status or add constants on its own.

## 8. A record is final, but not necessarily deeply immutable

With:

~~~java
record ApiResult(String message, java.util.List<String> notes) {
}
~~~

the record is implicitly final and suitable as a permitted direct implementation of a sealed interface. However, if notes is a mutable ArrayList, the record can observe state changes through reference aliases. Sealed restricts subtyping, and a final record restricts subclassing; **neither automatically deep-copies mutable references**.

### 8.1. Defensive copying at the record boundary

~~~java
record ApiResult(String message, java.util.List<String> notes) {
    ApiResult {
        notes = java.util.List.copyOf(notes);
    }
}
~~~

The compact canonical constructor takes a snapshot of the List structure before the field is assigned. If the list elements are immutable Strings, the data is safer against external mutation.

### 8.2. Cannot attach `sealed` to a record to define a subclass tree

A record is defined by the language as final. Do not use:

~~~java
sealed record Result(String data) permits MoreResult {
}
~~~

**Intentionally does not compile**. If you want a family of record variants, use a sealed interface as the root and have each record implement it.

### 8.3. Value-based equality of records differs from enum identity

Two `new ApiResult("ok", List.of())` instances with the same component values can be equal according to the generated `equals()`. However, enum constants are canonical instances, using `==`. Having both implement the same sealed interface does not turn each kind's equals/identity semantics into a single unified one.

## 9. Complete program 2 — sealed abstract class as the base for ordinary classes

Create the file **`SealedAbstractClassDemo.java`**:

~~~java
public class SealedAbstractClassDemo {
    abstract static sealed class Operation permits Save, Fetch {
        abstract String execute();
    }

    static final class Save extends Operation {
        @Override
        String execute() {
            return "save";
        }
    }

    static non-sealed class Fetch extends Operation {
        @Override
        String execute() {
            return "fetch";
        }
    }

    static final class CachedFetch extends Fetch {
        @Override
        String execute() {
            return "fetch-cached";
        }
    }

    public static void main(String[] args) {
        Operation save = new Save();
        Operation fetch = new CachedFetch();

        System.out.println("Save = " + save.execute());
        System.out.println("Fetch = " + fetch.execute());
        System.out.println("Operation sealed = "
                + Operation.class.isSealed());
        System.out.println("Fetch sealed = "
                + Fetch.class.isSealed());
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 SealedAbstractClassDemo.java
java SealedAbstractClassDemo
~~~

**Stdout:**

~~~text
Save = save
Fetch = fetch-cached
Operation sealed = true
Fetch sealed = false
~~~

### 9.1. `Save` is a closed branch

Save is final and cannot be subclassed.

### 9.2. `Fetch` is an open branch

Fetch is a direct permitted subtype of Operation and declares itself `non-sealed`. Therefore, `CachedFetch extends Fetch` is allowed, even though CachedFetch is not in `Operation.permits`.

### 9.3. When should `non-sealed` be used?

When the root needs to know which kinds of extension points are permitted to appear directly, while one branch must allow third parties to add implementations. For example, the root `Operation` permits the `Fetch` type, and plugins are allowed to extend behavior based on Fetch.

### 9.4. `non-sealed` is not a decorative keyword

A class cannot attach non-sealed on its own unless it is a direct subtype within an appropriate sealed hierarchy. It is a modifier meaning “reopen a branch that was constrained by a sealed parent”.

## 10. Abstract non-sealed: still abstract but does not restrict subclasses

A direct subtype branch of a sealed interface can be an **abstract non-sealed class**:

~~~java
sealed interface Shape permits Polygon, Circle {
}

record Circle(double radius) implements Shape {
}

abstract non-sealed class Polygon implements Shape {
    abstract int edges();
}

final class Triangle extends Polygon {
    @Override
    int edges() {
        return 3;
    }
}
~~~

This is a fragment. `Polygon` is abstract so you cannot create `new Polygon()`, yet it is non-sealed so it can be extended by Triangle and other valid subclasses.

### 10.1. Comparing the three abstract variants

| Declaration | Create an instance of that type? | Extending subclasses |
| --- | --- | --- |
| `abstract class A` | No | Under normal rules |
| `abstract sealed class A permits B` | No | Only permitted direct subclasses |
| `abstract non-sealed class A` (after a sealed parent) | No | Subclassing branch is open |
| `final class A` | Yes, if constructor is accessible | Cannot be subclassed |
| `sealed class A permits B` without abstract | Yes, if constructor is accessible | Only permits direct subclasses |

A sealed abstract class can be used when strict control over an intermediate branch is needed. An abstract non-sealed class is suitable when you want implementors of a branch to still be able to come from plugins.

### 10.2. Warning when analyzing exhaustiveness

If a permitted direct subtype is non-sealed, the compiler knows it is a branch allowing many unlisted descendants. A handler with a pattern matching the **type of the non-sealed branch** can cover all those descendants; you must not assume that only the subclasses you know today exist.

### 10.3. Restrictions of accessible constructors

Even when non-sealed, an abstract superclass with an inaccessible constructor can make it hard for clients to extend. Inheritance modifiers and constructor access are two separate layers of control.

## 11. Complete program 3 — sealed interface with an abstract non-sealed branch

Create the file **`SealedAbstractBranchDemo.java`**:

~~~java
public class SealedAbstractBranchDemo {
    sealed interface Shape permits Circle, Polygon {
        double area();
    }

    record Circle(double radius) implements Shape {
        @Override
        public double area() {
            return 3.0 * radius * radius;
        }
    }

    abstract static non-sealed class Polygon implements Shape {
        protected final double side;

        Polygon(double side) {
            this.side = side;
        }
    }

    static final class Square extends Polygon {
        Square(double side) {
            super(side);
        }

        @Override
        public double area() {
            return side * side;
        }
    }

    public static void main(String[] args) {
        Shape circle = new Circle(2.0);
        Shape square = new Square(3.0);

        System.out.println("Circle area = " + circle.area());
        System.out.println("Square area = " + square.area());
        System.out.println("Circle is record = "
                + Circle.class.isRecord());
        System.out.println("Polygon sealed = "
                + Polygon.class.isSealed());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 SealedAbstractBranchDemo.java
java SealedAbstractBranchDemo
~~~

**Stdout:**

~~~text
Circle area = 12.0
Square area = 9.0
Circle is record = true
Polygon sealed = false
~~~

### 11.1. Why can Polygon further have Square?

Polygon is permitted by Shape and declared non-sealed. Square extends Polygon and is not a direct implementor of Shape, so it does not need to be listed in `Shape.permits`.

### 11.2. The Circle record does not need the final modifier

A record is automatically final and is a direct permitted implementation of Shape. You cannot extend Circle with an ordinary class to add behavior.

### 11.3. Why use 3.0 instead of Math.PI?

The demo intentionally uses a factor of 3.0 to keep stdout deterministic/simple and focus on sealed/abstract/record, not to teach the engineering formula for a circle. Real geometric business logic needs `Math.PI`, though the decimal output would differ.

## 12. The `final`, `sealed`, and `non-sealed` states for direct subtypes

A sealed parent requires an ordinary direct subclass or implementing class to choose its exact continuation path:

~~~java
sealed interface Command permits Simple, Group, Extension {
}

final class Simple implements Command {
}

sealed class Group implements Command permits GroupLeaf {
}

final class GroupLeaf extends Group {
}

non-sealed class Extension implements Command {
}
~~~

This is a declaration fragment.

### 12.1. `final`

Closes off the class branch. A permitted final class has no subclasses. A record has an implicit final state.

### 12.2. `sealed`

Continues restricting direct subtypes at the next level. Allows multi-level sealed hierarchies, for example Command → Group → GroupLeaf. Command's `permits` lists Group, **not** GroupLeaf, because GroupLeaf does not directly implement Command.

### 12.3. `non-sealed`

Opens the hierarchy at that branch. A non-sealed class can have subclasses under general inheritance rules; a non-sealed interface can be implemented by arbitrary implementations.

### 12.4. Cannot attach `final` to an interface

An interface cannot be `final`; a permitted interface must be sealed or non-sealed (depending on circumstances), without the final modifier. A final class or record is suitable for a closed branch.

### 12.5. `sealed` can be used on an interface without the abstract modifier

Every interface is already semantically abstract (cannot be instantiated with `new Interface()`). Writing `sealed interface I` is the standard idiom. There is no need to write `abstract sealed interface` to make it “more abstract”.

### 12.6. Enum and record are exceptions with implicit characteristics

For a record, the declaration is implicitly final. For an enum, if there is no constant class body, it is implicitly final; if there are constant class bodies, it is implicitly sealed. Do not try to add the `final`/`sealed` modifier directly to enum/record declarations.

## 13. Enum class bodies and the concept of implicitly sealed

An enum can contain individual constant-specific class bodies to override behavior:

~~~java
enum Calculation {
    ADD {
        @Override
        int calculate(int a, int b) {
            return a + b;
        }
    },
    MULTIPLY {
        @Override
        int calculate(int a, int b) {
            return a * b;
        }
    };

    abstract int calculate(int a, int b);
}
~~~

Java generates specialized anonymous subclasses for constants that have class bodies. In the Java 17 language model, an enum with at least one constant-specific class body is **implicitly sealed**, and the permitted direct subclasses are solely the anonymous classes corresponding to the constant-specific bodies.

### 13.1. An enum without class bodies is implicitly final

~~~java
enum Direction {
    NORTH, SOUTH
}
~~~

The enum has no subclasses for its constants, so it is implicitly final. You cannot create an arbitrary subclass of Direction.

### 13.2. Having an enum class body does not mean clients can extend the enum

An enum with constant bodies is handled specially by the compiler. You still **cannot** write `class MyOperation extends Calculation`, even though Calculation is implicitly sealed. There is no user-supplied `permits MyOperation` mechanism for an enum.

### 13.3. When an enum implements a sealed interface

An enum can be a **direct permitted implementation** of a sealed interface; the subtype continuation rules for the enum are determined by the implicit enum final/sealed behavior, without needing a `final class`/`non-sealed` modifier.

### 13.4. Distinguishing two layers of sealing

If `sealed interface Action permits Calculation` and Calculation is an enum with constant bodies:

1. Sealed Action restricts direct implementors to Calculation.
2. Implicitly sealed Calculation restricts direct subclasses of **the enum itself** to the constant-specific anonymous classes.

Those constant bodies should not be called “additional implementations of Action added by plugins” — they are tied to constants defined by the enum and do not open up the runtime enum set.

## 14. Complete program 4 — sealed interface with an enum having constant bodies

Create the file **`SealedEnumBodiesDemo.java`**:

~~~java
public class SealedEnumBodiesDemo {
    sealed interface Action permits BuiltinAction, UserAction {
        String execute();
    }

    enum BuiltinAction implements Action {
        READ {
            @Override
            public String execute() {
                return "read";
            }
        },
        WRITE {
            @Override
            public String execute() {
                return "write";
            }
        };
    }

    record UserAction(String name) implements Action {
        @Override
        public String execute() {
            return "user:" + name;
        }
    }

    public static void main(String[] args) {
        Action read = BuiltinAction.READ;
        Action write = BuiltinAction.WRITE;
        Action user = new UserAction("export");

        System.out.println(read.execute());
        System.out.println(write.execute());
        System.out.println(user.execute());

        System.out.println("Action sealed = "
                + Action.class.isSealed());
        System.out.println("Enum sealed = "
                + BuiltinAction.class.isSealed());
        System.out.println("Declaring enum = "
                + BuiltinAction.READ.getDeclaringClass()
                        .getSimpleName());
        System.out.println("Constant runtime class is enum = "
                + (BuiltinAction.READ.getClass()
                        == BuiltinAction.class));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 SealedEnumBodiesDemo.java
java SealedEnumBodiesDemo
~~~

**Stdout:**

~~~text
read
write
user:export
Action sealed = true
Enum sealed = true
Declaring enum = BuiltinAction
Constant runtime class is enum = false
~~~

### 14.1. Why is enum sealed = true?

BuiltinAction has READ and WRITE with constant-specific class bodies, so it is implicitly sealed in Java 17. Reflection `Class.isSealed()` reports that state.

### 14.2. Why does getClass differ from the declaring class?

`BuiltinAction.READ` is an instance of a compiler-generated anonymous subclass, yet `getDeclaringClass()` still returns BuiltinAction — the enum class that defines the constant.

### 14.3. Do not use synthetic subclass names as an API

The runtime names of synthetic classes for constant-specific bodies can depend on the compiler. Do not rely on `BuiltinAction$1` or similar to handle business logic.

### 14.4. Note on enum constant abstract methods

If an enum declares an abstract instance method and a constant does not override its implementation, the compiler will reject it. In this demo, the Action interface requires execute(); each constant-specific body provides an implementation, so it is valid.

## 15. Java 17 reflection: who is permitted to directly inherit?

Reflection provides convenient APIs for sealed classes/interfaces:

~~~java
SomeType.class.isSealed()
SomeType.class.getPermittedSubclasses()
~~~

`getPermittedSubclasses()` returns a `Class<?>[]` representing the direct permitted subclasses/implementors of the sealed type. If the type is not sealed, it normally returns null according to the API contract.

### 15.1. Direct permits do not equate to all transitive descendants

Suppose:

~~~text
sealed interface A permits B
non-sealed interface B extends A
class C implements B
~~~

`A.getPermittedSubclasses()` reflects B, rather than automatically listing C, D, E ... that may implement B in the future.

### 15.2. Do not rely on unspecified ordering

When you want deterministic output, sort the names of the Class objects instead of assuming the reflection array will always follow the order users expect across all tools/versions.

### 15.3. A non-sealed class is unsealed according to reflection

`isSealed()` returns false for an ordinary non-sealed class (it carries no sealing restriction). It can still be a direct permitted subtype of a sealed parent.

### 15.4. Reflection does not bypass inheritance permissions

Even when knowing a Class is in the permits list, you still cannot create an arbitrary additional direct subtype and replace the list at runtime under public Java source semantics.

## 16. Complete program 5 — reflection inspecting a sealed tree

Create the file **`SealedReflectionDemo.java`**:

~~~java
import java.lang.reflect.Modifier;
import java.util.Arrays;

public class SealedReflectionDemo {
    sealed interface Vehicle permits Bike, Car, Train, PluginVehicle {
    }

    record Bike(int wheels) implements Vehicle {
    }

    static final class Car implements Vehicle {
    }

    enum Train implements Vehicle {
        LOCAL
    }

    abstract static non-sealed class PluginVehicle
            implements Vehicle {
    }

    public static void main(String[] args) {
        Class<?>[] permitted =
                Vehicle.class.getPermittedSubclasses();

        System.out.println("Vehicle sealed = "
                + Vehicle.class.isSealed());
        System.out.println("Permitted = "
                + Arrays.stream(permitted)
                        .map(Class::getSimpleName)
                        .sorted()
                        .toList());
        System.out.println("Bike record = "
                + Bike.class.isRecord());
        System.out.println("Train enum = "
                + Train.class.isEnum());
        System.out.println("Car final = "
                + Modifier.isFinal(Car.class.getModifiers()));
        System.out.println("Plugin branch sealed = "
                + PluginVehicle.class.isSealed());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 SealedReflectionDemo.java
java SealedReflectionDemo
~~~

**Stdout:**

~~~text
Vehicle sealed = true
Permitted = [Bike, Car, PluginVehicle, Train]
Bike record = true
Train enum = true
Car final = true
Plugin branch sealed = false
~~~

### 16.1. Why does reflection see PluginVehicle?

PluginVehicle is a **direct permitted implementation** of Vehicle, even though the class is still abstract and non-sealed. Reflection identifies direct subtypes without requiring them to be instantiable.

### 16.2. Why doesn't it see all plugin subclasses?

Non-sealed PluginVehicle opens the branch, so direct children of PluginVehicle are descendants of Vehicle rather than direct implementations permitted by Vehicle. Vehicle's reflection only lists direct permitted types.

### 16.3. Record/enum metadata is independent of sealed metadata

`Bike.class.isRecord()` checks the record type, and `Train.class.isEnum()` checks the enum type. `Vehicle.class.isSealed()` checks the restriction of the sealed interface. These are three different aspects coexisting in a single type hierarchy.

## 17. Exhaustive handling: what does Java 17 have and not have yet?

A sealed type has a finite **set of direct permitted branches**, making it useful for exhaustive handling. However, it is important to distinguish feature availability by Java version:

- Java 17 **standardized sealed classes/interfaces**.
- Java 17 **supports pattern matching for `instanceof`** as a standard feature.
- **Type patterns in `switch` over sealed hierarchies are a preview feature in Java 17**, not standard Java 17 syntax when simply using `javac File.java`.
- Switch patterns were standardized in Java 21; the Java 17 examples in this lesson **do not use preview**.

Therefore, to handle mixed sealed variants reliably in Java 17, use `if / else if` combined with `instanceof` pattern variables.

### 17.1. Pattern matching with instanceof

~~~java
if (value instanceof DataEvent data) {
    return data.payload();
}
~~~

The pattern variable `data` exists within the flow scope where the compiler knows the type test succeeded.

### 17.2. Note when adding a new variant

With an `if / else if` chain in Java 17, the compiler **does not automatically guarantee exhaustiveness** across all sealed variants like exhaustive pattern switches available in later Java versions. If you add a permitted subtype but forget to handle it, execution can fall into the fallback branch at runtime.

### 17.3. Switch on enum is still standard in Java 17

A `switch` expression using enum constants and complete cases is standard Java 17. Do not confuse that with `switch (sealedInterface) { case Type t -> ... }`, which is a preview feature in Java 17.

### 17.4. Visitor-style polymorphism can be designed

A sealed interface with an `accept(Visitor)` method implemented by each subtype can provide a compile-time-oriented visitor API in Java 17. However, adding a new variant still requires updating the visitor contract, and the design involves boilerplate; choose according to API needs.

## 18. Complete program 6 — instanceof patterns with record + enum

Create the file **`SealedPatternDispatchDemo.java`**:

~~~java
public class SealedPatternDispatchDemo {
    sealed interface Notification permits Mail, Push, Alarm {
    }

    record Mail(String address) implements Notification {
    }

    record Push(int count) implements Notification {
    }

    enum Alarm implements Notification {
        FIRE
    }

    static String handle(Notification value) {
        if (value instanceof Mail mail) {
            return "mail:" + mail.address();
        }
        if (value instanceof Push push) {
            return "push:" + push.count();
        }
        if (value instanceof Alarm alarm) {
            return "alarm:" + alarm.name();
        }
        throw new IllegalArgumentException("Unexpected notification");
    }

    public static void main(String[] args) {
        System.out.println(handle(new Mail("a@example.org")));
        System.out.println(handle(new Push(3)));
        System.out.println(handle(Alarm.FIRE));
    }
}
~~~

Compile/run **without needing `--enable-preview`**:

~~~bash
javac -encoding UTF-8 SealedPatternDispatchDemo.java
java SealedPatternDispatchDemo
~~~

**Stdout:**

~~~text
mail:a@example.org
push:3
alarm:FIRE
~~~

### 18.1. Why is else-if not required?

Each branch returns if it matches. Subsequent branches only run if the previous test is false. Flow analysis with pattern variables makes `mail`, `push`, and `alarm` have their types properly determined within the body.

### 18.2. Why still throw at the end?

This lesson does not use Java 21 exhaustive pattern switches. To the Java 17 compiler, this chain is not automatically proven exhaustive against the sealed permits; the method needs a fallback. You may also want to reject null with a clearer message.

### 18.3. The null case

`null instanceof Type` returns false for type patterns, then falls through to the throw. If the API allows null, handle null separately right at the start of the function rather than mixing it with a business variant.

## 19. Permits rules with modules and packages

A sealed hierarchy is not just a list of type names: there are also compile-time deployment constraints.

### 19.1. Named module

If the sealed parent is in a **named module**, the direct permitted subclasses/implementors must be in the **same module** according to Java sealed rules. They can belong to different packages within the same module when declarations/accessibility and permits are all valid.

### 19.2. Unnamed module

If the sealed parent is in an **unnamed module**, the direct permitted subtypes must be in the **same package**. You cannot arbitrarily let a class in another package implement a sealed parent in a classpath project merely by writing its name in permits.

### 19.3. Same compilation unit can infer permits

In cases where all direct subclasses are declared in the same compilation unit as the sealed parent, you can **omit `permits`** and let Java infer the direct permitted types:

~~~java
sealed interface Message {
}

record Info(String value) implements Message {
}

final class ErrorMessage implements Message {
}
~~~

This is a declaration fragment. When the types are in the same compilation unit and valid, the compiler infers the permitted direct implementations. However, writing `permits` explicitly in lessons usually helps make the hierarchy visible and keeps design under control.

### 19.4. What if types are spread across multiple files?

If direct subtypes reside in different compilation units, use explicit `permits TypeA, TypeB` and satisfy package/module rules. The classes must be compiled in the appropriate dependency/source context.

### 19.5. Permits are not automatically updated via runtime registration

The permits hierarchy is a property of the compiled type system, not a mutable registry. Loading a plugin outside the allowed hierarchy will not make the sealed parent accept the plugin class as a direct implementation.

## 20. Adding a new subtype and source/binary compatibility

A sealed hierarchy is **closed for the compiled version** of the root, not unchangeable forever. A developer can update the source to add a new permitted variant:

~~~java
sealed interface Command
        permits Create, Update, Delete {
}
~~~

Adding Delete in a later version is an **API/model change**. It can affect:

- Clients with exhaustive patterns/switches on Java versions that support them.
- Visitors or explicit if/else handlers.
- Serialized message formats.
- Schema validation and JSON discriminators.
- Testing of all variants.
- Documentation and generated models.
- Ensuring permitted classes/records/enums are packaged in the module/package according to the rules.

### 20.1. Binary compatibility requires separate consideration

Compiled bytecode carries sealed/permitted-subclass metadata. If you change the permits list or subtype status without rebuilding/redeploying the appropriate components, class loading/linkage failures can occur. Do not treat a hierarchy change as “just adding a case so it is definitely safe”.

### 20.2. A non-sealed branch is an intentional extension point

Choose `non-sealed` when you want an open branch. However, a sealed root with a non-sealed branch no longer guarantees that all runtime descendants are finite; algorithms relying on exhaustive enumeration must account for that.

### 20.3. Records and enums also have versioning

Adding a new record variant to the permits list or adding an enum constant to a permitted enum branch are both domain changes. However, the two are different:

- **Adding a permitted record subtype**: expands the root's set of direct implementation classes.
- **Adding an enum constant**: keeps the enum implementation type the same while increasing the number of named constant instances.

Therefore, consumer behavior should be reviewed according to the exact type of change.

## 21. Designing success/failure outcomes with sealed + record + enum

A common pattern is a sealed interface serving as the outcome contract:

~~~java
sealed interface Outcome permits Success, Failure, Pending {
}

record Success(String value) implements Outcome {
}

record Failure(int code, String message) implements Outcome {
}

enum Pending implements Outcome {
    INSTANCE
}
~~~

This is a declaration fragment.

### 21.1. Why use records for Success/Failure?

Each success/failure has a different payload and can have many runtime values. A record creates concise immutable-like value instances with a canonical constructor, accessors, and generated equals/hashCode/toString.

### 21.2. Why use an enum for Pending?

If Pending is just a named singleton-like state without its own payload, the enum constant `INSTANCE` can represent this state without creating multiple pointless objects. An enum can have multiple constant states if the domain requires them.

### 21.3. Why a sealed interface instead of an abstract base?

The Success/Failure records and Pending enum cannot extend a custom abstract class. A sealed interface brings them under a single common domain type without violating superclass restrictions.

### 21.4. Note on null and validation

Record components can accept null if you do not validate them. For Success, you can check `Objects.requireNonNull(value)` in a compact constructor if the domain forbids null; sealed does not automatically enforce payload invariants.

## 22. Complete program 7 — Outcome using records and an enum

Create the file **`SealedOutcomeDemo.java`**:

~~~java
public class SealedOutcomeDemo {
    sealed interface Outcome permits Success, Failure, Pending {
    }

    record Success(String value) implements Outcome {
    }

    record Failure(int code, String message) implements Outcome {
    }

    enum Pending implements Outcome {
        INSTANCE
    }

    static String summary(Outcome outcome) {
        if (outcome instanceof Success success) {
            return "success:" + success.value();
        }
        if (outcome instanceof Failure failure) {
            return "failure:" + failure.code()
                    + ":" + failure.message();
        }
        if (outcome == Pending.INSTANCE) {
            return "pending";
        }
        throw new IllegalArgumentException("Unknown outcome");
    }

    public static void main(String[] args) {
        System.out.println(summary(new Success("saved")));
        System.out.println(summary(new Failure(404, "missing")));
        System.out.println(summary(Pending.INSTANCE));

        System.out.println("Success record = "
                + Success.class.isRecord());
        System.out.println("Pending enum = "
                + Pending.class.isEnum());
        System.out.println("Outcome sealed = "
                + Outcome.class.isSealed());
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 SealedOutcomeDemo.java
java SealedOutcomeDemo
~~~

**Stdout:**

~~~text
success:saved
failure:404:missing
pending
Success record = true
Pending enum = true
Outcome sealed = true
~~~

### 22.1. The Pending enum differs from the Success record

Pending.INSTANCE is a canonical enum constant. Two `new Success("saved")` objects can be equal according to the generated record equals, but do not share the same identity under `==`.

### 22.2. Why is `outcome == Pending.INSTANCE` valid?

`Outcome` is an interface type that can reference the Pending constant, so an identity comparison with Pending.INSTANCE is valid. For an enum constant, this is a clear way to compare.

### 22.3. What if Pending needs a payload?

If each pending task needs a different retryAt/jobId, convert Pending to a record variant `record Pending(String jobId, Instant retryAt)` rather than stuffing mutable per-request data into a shared enum singleton.

## 23. A sealed abstract class can share state that a record cannot inherit

Suppose both Retry and Stop commands need a `requestId` field, validation, and a shared constructor. An abstract class is useful:

~~~java
abstract sealed class BaseCommand
        permits RetryCommand, StopCommand {
    private final String requestId;

    BaseCommand(String requestId) {
        this.requestId =
                java.util.Objects.requireNonNull(requestId);
    }

    final String requestId() {
        return requestId;
    }

    abstract String perform();
}
~~~

This is a fragment. RetryCommand and StopCommand can extend BaseCommand, reuse the requestId field, and implement perform.

### 23.1. The problem if you want to add a record command

You cannot write `record Retry(String requestId) extends BaseCommand`. Instead, use:

~~~java
sealed interface Command permits RecordCommand, BaseCommand {
    String requestId();
}

record RecordCommand(String requestId) implements Command {
}

abstract sealed class BaseCommand implements Command
        permits LegacyCommand {
    // Shared state, constructors, methods.
}

final class LegacyCommand extends BaseCommand {
    // Implementation.
}
~~~

This is a conceptual fragment: BaseCommand will need to implement/declare `requestId()` to satisfy the Command contract (it can keep it abstract), and LegacyCommand needs to complete the implementation. This approach shows a **sealed interface contract at the root**, while an abstract class is an optional implementation branch.

### 23.2. Do not force records to simulate inheritance with complex forwarding

If all variants need to share mutable state and a complex lifecycle, records may not be suitable. Ordinary final classes under a sealed abstract base can be used. Conversely, if variants are pure data, interface + records are usually concise.

### 23.3. Composition is a way to reuse without class inheritance

A record can hold a shared value object:

~~~java
record Metadata(String requestId) {
}

record Save(Metadata meta, String path) implements Command {
    @Override
    public String requestId() {
        return meta.requestId();
    }
}
~~~

This is a fragment assuming Command permits Save and the corresponding contract. The Save record does not extend Metadata; it **contains** Metadata, using composition to reuse data.

## 24. Common mistakes when combining sealed, abstract, record, and enum

### 24.1. Letting a record extend an abstract class

~~~java
abstract sealed class Base permits R {
}
record R(int x) extends Base { // ERROR.
}
~~~

A record cannot extend an arbitrary class. Fix by using a sealed interface + record implements.

### 24.2. Letting an enum extend an abstract class

~~~java
abstract sealed class Base permits E {
}
enum E extends Base { A } // ERROR.
~~~

An enum implicitly extends Enum<E>; there is no custom extends clause. Fix by implementing a sealed interface.

### 24.3. Having an ordinary class implement a sealed interface without permits

~~~java
sealed interface Root permits Allowed {
}
record Allowed(int x) implements Root {
}
final class Surprise implements Root { // ERROR.
}
~~~

Surprise is not permitted by Root.

### 24.4. Forgetting `final/sealed/non-sealed` on an ordinary direct subtype

~~~java
sealed interface Root permits Node {
}
class Node implements Root { // ERROR: missing state modifier.
}
~~~

Node must choose final/sealed/non-sealed according to the rules. Final is not inferred merely because an extends clause is missing.

### 24.5. Trying to write `sealed record`

~~~java
sealed record Value(int x) { // ERROR.
}
~~~

A record is implicitly final; you cannot declare a sealed subclass hierarchy directly on a record.

### 24.6. Trying to write `final enum`

~~~java
final enum State { A } // ERROR: enum modifiers do not allow final like that.
~~~

Enum final/sealed semantics are determined by the compiler/language.

### 24.7. Abstract permitted class using final

~~~java
abstract final class Broken {
}
~~~

A class cannot be both abstract and final. Use abstract sealed/non-sealed depending on the sealed parent relationship and extensibility requirements.

### 24.8. Non-sealed without a direct sealed ancestor

~~~java
non-sealed class Open {
}
~~~

Invalid because the non-sealed modifier only applies properly to the structure of a direct subtype of a sealed parent.

### 24.9. Permitting a class in an invalid package/module

Permits must obey named module/unnamed module placement rules. Simply adding a fully qualified name is not enough.

### 24.10. Using Java 21 pattern switch in Java 17 without enabling preview

~~~java
return switch (value) {
    case MyRecord r -> r.field();
    case MyEnum e -> e.name();
};
~~~

In Java 17, type-pattern switch syntax is a preview feature and does not compile in the default standard mode. This lesson uses stable `instanceof` pattern matching.

### 24.11. Assuming a sealed root guarantees all descendants are closed after non-sealed

A permitted non-sealed branch allows new descendants. You need to clearly know which parts of the hierarchy are closed.

### 24.12. Thinking enum constants themselves are permitted interface implementations

If Root permits enum State, the **direct implementing class** is State; the constants State.A and State.B are **instances**, not two additional direct class declarations listed in Root's permits.

### 24.13. Thinking record component fields form a completely immutable object graph

Record fields are final, yet mutable referents can still be modified through aliases. Use defensive copying/immutability if needed.

### 24.14. Thinking reflective isSealed is synonymous with isAbstract

An ordinary class can be sealed without being abstract; an abstract class can be non-sealed. The two metadata properties are independent.

### 24.15. Thinking records/enums can manually extend java.lang.Record/Enum

Record/enum rules already handle those special superclasses. An ordinary class cannot manually extend `java.lang.Record` or `java.lang.Enum` to impersonate a record/enum type.

## 25. Mixed sealed hierarchy design checklist

1. Does the root need to close the set of **direct implementations**, or does it need plugin extensibility?
2. Are there record and enum variants? If so, choose a sealed interface root.
3. Does a branch need shared state/constructors? Consider a sealed abstract class for that branch.
4. Are you trying to have a record/enum extend an abstract class? If so, redesign it.
5. Is every ordinary direct subtype marked final/sealed/non-sealed?
6. Is the record left implicitly final instead of writing the final modifier?
7. Does the enum have no class body or a constant-specific class body?
8. If the enum has a class body, do you understand implicitly sealed and synthetic subclasses?
9. Are you using an enum constant as a singleton-like state?
10. If a variant needs an arbitrary payload, have you chosen a record/class instead of an enum?
11. Are the direct permitted types in the right module/package?
12. If all direct subtypes are in the same compilation unit, do you want permits inference?
13. For a multi-file project, have you declared permits explicitly and built in sync?
14. Is there any non-sealed branch making the hierarchy not truly closed?
15. If so, do handler/exhaustiveness assumptions account for new descendants?
16. Is the Java target actually ≥17 for sealed classes?
17. Is type-pattern switch using Java 21+ syntax, or has Java 17 preview been intentionally enabled?
18. In Java 17, have you used instanceof patterns/visitors compatibly?
19. Does the reflective API use isSealed/getPermittedSubclasses accurately at the direct level?
20. Is separate record.isRecord/enum.isEnum metadata used when needed?
21. Do record components perform defensive copying if mutable?
22. Do abstract constructors establish invariants while avoiding calling overridable methods?
23. Do interfaces have appropriate contract methods and accessors?
24. Is it clearly understood that record variants have value equality different from enum identity?
25. Are there tests for all variants, reflection hierarchy, and unknown/null inputs?
26. When adding a permitted subtype/enum constant, have serializers, handlers, and schemas been updated?
27. Are sealed modifiers compatible with module/package and library versioning?
28. Have you avoided hardcoding compiler-generated enum subclass names?
29. Have you considered composition instead of class inheritance when needing to reuse state in a record?
30. Have you clearly explained the rationale for sealed to the team rather than only using it to reduce boilerplate?

## 26. Exercises with answers

**Question 1.** Can you use `sealed interface Result permits Ok, Error` with `record Ok(...) implements Result`?

**Answer:** Yes. A record is implicitly final and can implement a sealed interface when permitted.

**Question 2.** Can you write `record Ok(...) extends AbstractResult`?

**Answer:** No. A record implicitly extends java.lang.Record and cannot extend a custom class.

**Question 3.** Can an enum implement a sealed interface?

**Answer:** Yes, when permitted and placement is valid.

**Question 4.** Can an enum extend a sealed abstract class?

**Answer:** No. An enum implicitly extends java.lang.Enum<E>.

**Question 5.** If you want a family containing records, enums, and an abstract class, which root is suitable?

**Answer:** A sealed interface, with the abstract class as a permitted branch when needed.

**Question 6.** How does `abstract sealed class` differ from `sealed class`?

**Answer:** An abstract class cannot be instantiated directly; sealed only restricts direct subtypes. They can be combined.

**Question 7.** Is `abstract final class` valid?

**Answer:** No, because abstract requires subclassability while final forbids subclassing.

**Question 8.** What modifiers must a direct permitted ordinary class have?

**Answer:** Choose `final`, `sealed`, or `non-sealed` as required.

**Question 9.** Does a record need to write the final modifier when implementing a sealed interface?

**Answer:** No; a record is implicitly final and the final modifier is not written like an ordinary class modifier.

**Question 10.** What is an enum without a constant class body implicitly?

**Answer:** Implicitly final.

**Question 11.** What is an enum with a constant-specific class body implicitly?

**Answer:** Implicitly sealed, with compiler-generated constant-specific anonymous subclasses.

**Question 12.** Can an enum be opened for client subclasses using permits?

**Answer:** No. Enum-specific subclassing is only according to declared constant bodies.

**Question 13.** Is `non-sealed class Extension implements SealedRoot` valid when permitted?

**Answer:** Yes, if Extension is a direct permitted subtype and syntax/placement are valid.

**Question 14.** Can there be `class Plugin extends Extension` afterward?

**Answer:** Yes, if Extension is non-sealed and normal access/inheritance rules allow it.

**Question 15.** Must Plugin appear in Root.permits?

**Answer:** No, if Plugin does not directly implement/extend Root and only goes through non-sealed Extension.

**Question 16.** Can `non-sealed class Open` exist without a direct sealed parent?

**Answer:** No.

**Question 17.** Does a sealed interface guarantee that every transitive descendant is always listed?

**Answer:** No, if there is a non-sealed branch.

**Question 18.** Does Java 17 have standard sealed classes yet?

**Answer:** Yes, sealed is a standard feature starting in Java 17.

**Question 19.** Is type-pattern switch on a sealed interface a standard feature of Java 17?

**Answer:** No, it is still preview; to run without preview, use instanceof patterns or another dispatch mechanism.

**Question 20.** Does Java 17 support standard instanceof pattern matching?

**Answer:** Yes.

**Question 21.** What is Class.isSealed used for?

**Answer:** Checking whether a Class object represents a sealed class/interface according to runtime metadata.

**Question 22.** What does getPermittedSubclasses list?

**Answer:** Direct permitted subtypes; it does not automatically list all deeper descendants.

**Question 23.** Does a List record component become deeply immutable automatically because the record is final?

**Answer:** No. Referent Lists/mutable elements require an ownership/copy policy.

**Question 24.** Can two `new Success("ok")` records have equals return true?

**Answer:** Yes, according to generated equality based on component fields when values match.

**Question 25.** Do two `Pending.INSTANCE` references to an enum constant compare == true?

**Answer:** Yes.

**Question 26.** If an enum implements a sealed interface, is each enum constant a direct interface implementor type?

**Answer:** No. The direct implementation class is the enum; constants are instances.

**Question 27.** Can an abstract class contain constructors and shared state?

**Answer:** Yes. Subclasses call the appropriate super constructor; the abstract class still cannot be instantiated directly.

**Question 28.** Does a named module allow direct permitted types in a package in a different module?

**Answer:** No. Direct permitted types must be in the same module as the sealed parent; they can be in different packages within the same named module when other rules allow.

**Question 29.** What does an unnamed module require for permitted direct types?

**Answer:** They must be in the same package as the sealed parent.

**Question 30.** Can `sealed interface Root {}` omit permits when the direct implementations are in the same compilation unit?

**Answer:** Yes, when Java has sufficient information and the corresponding rules are met.

**Question 31.** Is adding a new record variant to a sealed interface the same as adding an enum constant?

**Answer:** No. One adds a direct implementation class, while the other adds a named instance within the same enum implementation type.

**Question 32.** Does `sealed` forbid calling a constructor if the class is not abstract?

**Answer:** Not automatically; constructor accessibility and the abstract modifier determine instantiability.

**Question 33.** Can composition be used to share data with a record?

**Answer:** Yes; a record holds component references to shared value objects instead of extending a custom superclass.

**Question 34.** Is using `getClass()` to determine the declaring type of an enum with class bodies always accurate?

**Answer:** No. Use the enum constant's `getDeclaringClass()`.

**Question 35.** What are the different roles of sealed and enum?

**Answer:** Sealed restricts the direct subtype hierarchy; enum defines named constant instances and enum-specific subclassing—they are not the same mechanism.

## 27. Practice exercises

### Exercise 1 — outcome tree with records and an enum

Create `sealed interface ApiResult permits Ok, Fail, Pending`. Two records Ok/Fail hold payloads; the Pending enum has the constant INSTANCE. Write a Java 17 handler using instanceof patterns and == for Pending.

**Hint:** Do not write `record Ok(...) extends ApiResult`; a record uses `implements`.

### Exercise 2 — abstract branch sharing constructor state

Create sealed interface Action permits Builtin, ManualAction; Builtin is an enum; ManualAction is an abstract sealed class permitting StartAction/StopAction. Share final String id in ManualAction, then implement concrete action methods.

**Hint:** Ordinary direct subclasses require final/sealed/non-sealed.

### Exercise 3 — non-sealed extension point

Create sealed interface Handler permits CoreHandler, PluginHandler; CoreHandler is final, PluginHandler is abstract non-sealed. Create class CustomPluginHandler extends PluginHandler. Explain why PluginHandler is in permits but CustomPluginHandler is not.

**Hint:** Root permits only direct subtypes.

### Exercise 4 — enum constant bodies and reflection

Create sealed interface Operation permits MathOperation; enum MathOperation implements Operation has ADD/MULTIPLY with constant-specific implementations. Use `isSealed()` and `getDeclaringClass()` to inspect.

**Hint:** An enum is implicitly sealed when it has constant class bodies.

### Exercise 5 — reviewing the API when adding a variant

Add record Warning(String message) to sealed Outcome and update permits. Check all handler logic, tests, serializers, and consumer APIs. If using standard Java 17, do not use type-pattern switch without enabling preview.

**Hint:** Adding a direct permitted type differs from adding an enum constant to an existing enum.

## 28. Conclusion

**`sealed` controls the right to directly extend/implement a type; `abstract` controls direct instantiability; `record` and `enum` are special classes with their own superclass/instantiation rules.** They combine very well when arranged in their proper roles.

For a family containing **records, enums, and abstract classes**, use a **sealed interface as the root**. Records and enums implement the interface and are permitted; an abstract sealed/non-sealed class can also implement the interface and serve as a branch for ordinary subclasses. A sealed abstract class **cannot serve as the direct superclass of a record or enum**, because a record implicitly extends Record and an enum implicitly extends Enum.

Every ordinary permitted direct subtype must choose `final`, `sealed`, or `non-sealed`. A record is implicitly final; an enum is implicitly final if it has no constant bodies and implicitly sealed if it has constant-specific class bodies, though enum-specific anonymous subclasses do not open the enum to external subclassing. A non-sealed branch opens the hierarchy again, so “sealed” does not mean all descendants are always closed.

Finally, use Java 17 features according to the version: **sealed and `instanceof` patterns are standard**, whereas type-pattern `switch` is still preview in Java 17. Check module/package permits, reflection on direct subtypes, immutable payload design, and API/version compatibility to take advantage of sealed hierarchies without breaking extensibility or existing data.
