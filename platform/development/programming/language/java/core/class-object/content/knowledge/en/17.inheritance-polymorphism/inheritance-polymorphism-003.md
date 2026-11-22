# `implements` and the Contract Role of `interface` in Java

In Java, an **interface** is a reference type that describes **the capabilities or behaviors that implementing classes must provide**. The **`implements`** keyword declares that a class takes responsibility for implementing the interface's abstract methods according to Java rules.

Example:

~~~java
interface Printable {
    void print();
}

class Report implements Printable {
    @Override
    public void print() {
        System.out.println("Report printed");
    }
}
~~~

The `Printable` interface says: “An object of this type can be asked to `print()`.” The `Report` class decides **what to print and how**. The caller can work with the `Printable` type without needing to know the concrete class.

However, a **contract** is not just method names and signatures. The compiler checks **formal aspects** such as parameter types, return type, and access privileges; whereas guarantees like “do not deduct the balance when a transaction fails” or “sorting does not lose elements” must be **described, programmed, and tested**. A class that compiles successfully can still violate the semantic contract.

This lesson belongs to Java Core — **Class & Object / Inheritance and Polymorphism**. Examples use **Java 17+**, with a filename, compile command, and stdout output when presented as standalone programs. Illustrative code snippets or snippets intentionally written not to compile are clearly marked to avoid misunderstanding.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain an `interface` as a **type** and a **description of a behavioral contract**.
2. Write `class X implements Y` with proper syntax and understand the responsibilities of the implementing class.
3. Distinguish between an abstract method declaration in an interface and a method implementation in a class.
4. Understand why an implementing method must have compatible access privileges (usually `public`).
5. Use an **interface reference** to invoke methods through **runtime polymorphism**.
6. Implement **multiple interfaces** in the same class without inheriting from multiple superclasses.
7. Distinguish `implements` from `extends` for classes and interfaces.
8. Understand `default`, `static`, and `private` methods and resolve conflicting default implementations.
9. Know that fields in an interface are `public static final` by declaration semantics.
10. Understand **functional interfaces** and that lambda expressions do not mean every interface is functional.
11. Design generic interfaces and use interchangeable implementations.
12. Grasp the constraints of `throws`, return types, overriding, and method visibility.
13. Recognize the **Liskov Substitution Principle**, preconditions/postconditions, and invariants.
14. Know when interfaces are useful for dependency injection, testing, and API maintenance.
15. Avoid creating interfaces just to “give every class an interface”.
16. Understand Java 17 `sealed interface` and its relationship with `permits`.
17. Verify contracts using shared tests across multiple implementations.

## 2. What Is an Interface?

An interface declares a set of **member contracts** that implementing types can provide:

~~~java
interface Notifier {
    void send(String message);
}
~~~

The `send` method here is **implicitly `public abstract`**: it has no body. A concrete class implementing the method will provide the body:

~~~java
class ConsoleNotifier implements Notifier {
    @Override
    public void send(String message) {
        System.out.println(message);
    }
}
~~~

`ConsoleNotifier` is a **subtype** of `Notifier`. A variable of type `Notifier` can hold a reference to `ConsoleNotifier`.

### A Contract Has Multiple Levels

- **Signature/type contract:** `send` takes a `String` and returns `void`.
- **Visibility/access contract:** the method is made public so callers can invoke it through the interface.
- **Exception contract:** checked exceptions may only be declared in ways compatible with the interface method.
- **Behavioral contract:** `send` should carry out sending a notification in a documented sense.
- **State/invariant contract:** if it has state, the implementation maintains the relevant conditions.
- **Performance/concurrency contract:** exists only if the API or documentation genuinely promises it; an interface does not automatically make a method thread-safe or fast.

The compiler primarily enforces the **type-level** part. The semantic part must be verified by developers and tests.

## 3. `implements` Syntax

A class implements a single interface:

~~~java
class EmailSender implements Sender {
    // Implement the abstract methods of Sender.
}
~~~

Implementing multiple interfaces:

~~~java
class SmartDevice implements Switchable, Monitorable, Resettable {
    // Implement the required abstract methods.
}
~~~

If a class both extends a superclass and implements interfaces:

~~~java
class Employee extends Person implements Identifiable, Printable {
}
~~~

**Correct order:** `extends SuperClass` followed by `implements Interface1, Interface2`.

Java allows a class to have **at most one direct superclass** via `extends` (except Object as the root), but it can implement **multiple interfaces**. This makes it possible to combine multiple capabilities without needing multiple inheritance of class implementation/state.

### What Must a Class Implement?

A **concrete** class must have an implementation for the relevant abstract methods for which it has not already inherited a suitable implementation. If it does not implement them all, the class must be declared `abstract` or the compiler reports an error.

~~~java
interface RunnableTask {
    void run();
}

// Invalid if abstract is omitted without defining run().
abstract class TaskBase implements RunnableTask {
}
~~~

A concrete subclass can complete the rest.

## 4. First Runnable Example: Interface Reference and Runtime Dispatch

Create the file **`InterfacePolymorphismDemo.java`**:

~~~java
public class InterfacePolymorphismDemo {
    interface Greeter {
        String greet(String name);
    }

    static final class VietnameseGreeter implements Greeter {
        @Override
        public String greet(String name) {
            return "Xin chào, " + name;
        }
    }

    static final class EnglishGreeter implements Greeter {
        @Override
        public String greet(String name) {
            return "Hello, " + name;
        }
    }

    static void show(Greeter greeter) {
        System.out.println(greeter.greet("Mai"));
    }

    public static void main(String[] args) {
        Greeter first = new VietnameseGreeter();
        Greeter second = new EnglishGreeter();

        show(first);
        show(second);
    }
}
~~~

~~~bash
javac -encoding UTF-8 InterfacePolymorphismDemo.java
java InterfacePolymorphismDemo
~~~

Stdout:

~~~text
Xin chào, Mai
Hello, Mai
~~~

The same method `show(Greeter greeter)` receives two objects of two implementation classes. At runtime, `greeter.greet(...)` invokes **the implementation matching the actual object**.

**Two points to distinguish:**

1. The variable `first` is declared with type `Greeter`, while the actual object is `VietnameseGreeter`.
2. The compiler allows calling the methods present in the `Greeter` contract. You cannot arbitrarily call a method specific to VietnameseGreeter through a reference known only as type Greeter without a valid type cast.

This is a classic example of **programming to an interface**.

## 5. `@Override` and `public` Access

With an interface:

~~~java
interface Operation {
    int execute(int value);
}
~~~

Valid implementation:

~~~java
class DoubleOperation implements Operation {
    @Override
    public int execute(int value) {
        return value * 2;
    }
}
~~~

However:

~~~java
class Incorrect implements Operation {
    // int execute(int value) { return value * 2; }
    // Error if uncommented: weaker access privileges than public.
    @Override
    public int execute(int value) {
        return value * 2;
    }
}
~~~

In an interface, an abstract instance method is usually implicitly **public abstract**. When implemented, the method **cannot lower** its access level to package-private or protected.

`@Override` is strongly recommended because the compiler verifies that the method actually overrides/implements a matching member. If you mistype the name or parameters, the annotation helps catch it early.

### Why Shouldn't You Omit `public`?

In a class, a method **without an access modifier** is package-private, not public. Therefore:

~~~java
// int execute(int value) { ... }
~~~

does not satisfy the public access required by the interface. Adding `public` is the proper fix, not an accidental widening of access.

## 6. Method Signature: Name, Parameters, and Return Type

A class must implement the method with a matching signature.

Interface:

~~~java
interface Calculator {
    long calculate(int x, int y);
}
~~~

Correct:

~~~java
class AddCalculator implements Calculator {
    @Override
    public long calculate(int x, int y) {
        return (long) x + y;
    }
}
~~~

It is wrong to replace `calculate(int,int)` with `calculate(long,long)`: that is an **overload** with a different parameter list, not a method implementing the contract. If the concrete class has no implementation for `calculate(int,int)`, the compiler reports an error.

### Return Types Can Be Covariant

For reference return types, Java can allow an implementation to return a suitable subtype:

~~~java
interface Maker {
    Number make();
}

class IntegerMaker implements Maker {
    @Override
    public Integer make() {
        return 10;
    }
}
~~~

`Integer` is a subtype of `Number`. For primitive return types, covariance rules do not apply in the same way: changing `long` to `int` when overriding the `long calculate(...)` method is not a valid implementation.

## 7. Runnable Example: One Contract, Multiple Algorithms

Create the file **`StrategyInterfaceDemo.java`**:

~~~java
public class StrategyInterfaceDemo {
    interface DiscountPolicy {
        long apply(long originalCents);
    }

    static final class NoDiscount implements DiscountPolicy {
        @Override
        public long apply(long originalCents) {
            if (originalCents < 0) {
                throw new IllegalArgumentException("negative price");
            }
            return originalCents;
        }
    }

    static final class FixedDiscount implements DiscountPolicy {
        private final long discountCents;

        FixedDiscount(long discountCents) {
            if (discountCents < 0) {
                throw new IllegalArgumentException("negative discount");
            }
            this.discountCents = discountCents;
        }

        @Override
        public long apply(long originalCents) {
            if (originalCents < 0) {
                throw new IllegalArgumentException("negative price");
            }
            return Math.max(0, originalCents - discountCents);
        }
    }

    static void printResult(DiscountPolicy policy) {
        System.out.println("price=" + policy.apply(1_000));
    }

    public static void main(String[] args) {
        printResult(new NoDiscount());
        printResult(new FixedDiscount(250));
    }
}
~~~

~~~bash
javac -encoding UTF-8 StrategyInterfaceDemo.java
java StrategyInterfaceDemo
~~~

Stdout:

~~~text
price=1000
price=750
~~~

The caller accepts `DiscountPolicy`. The discount logic is swapped for another implementation without having to change the code of `printResult`.

**Limitations of the demo:** This is only a fixed discount rule in `long` cents. A real payment system must define currency, limits, rounding rules, overflow handling, and business rules. Both implementations follow the example contract “non-negative input, non-negative output no greater than the original”, while the compiler **does not automatically prove** that contract.

## 8. An Interface Variable Type Limits Visible Methods

Given:

~~~java
interface Worker {
    void work();
}

class Developer implements Worker {
    @Override
    public void work() {
        System.out.println("coding");
    }

    public void debug() {
        System.out.println("debugging");
    }
}
~~~

If:

~~~java
Worker worker = new Developer();
worker.work();
// worker.debug(); // Does not compile with declared type Worker.
~~~

The `debug` method is declared only in Developer, not in the Worker interface.

If you genuinely need the specific method, you can use a **checked cast**:

~~~java
if (worker instanceof Developer developer) {
    developer.debug();
}
~~~

Java 17 supports pattern variables in `instanceof`. However, frequently casting down to a concrete implementation is a sign that the caller may be **depending too heavily on a concrete class**, losing the benefit of interface abstraction.

### An Interface Reference Does Not Hide Runtime Identity

`Worker worker = new Developer()` does not create “a separate Worker object”. The reference still points to **the same Developer instance**, and virtual invocation uses the corresponding runtime method.

## 9. `implements` Does Not Create Object or State Copies

Example:

~~~java
interface Named {
    String name();
}

class Student implements Named {
    private String name;

    Student(String name) {
        this.name = name;
    }

    @Override
    public String name() {
        return name;
    }
}
~~~

If:

~~~java
Student student = new Student("Mai");
Named named = student;
~~~

then `student == named` is true. They are **two variables referencing the same Student object**; there is no independent interface object.

Because an interface has no instance fields of its own, `implements` does not “attach an additional interface instance state region” to the object in the sense of having a copy of an instance field declared in the interface. The abstract methods are simply responsibilities that the class must fulfill.

## 10. Interfaces Extend Interfaces Using `extends`

An interface can inherit from another interface:

~~~java
interface Readable {
    String read();
}

interface Writable {
    void write(String value);
}

interface ReadWrite extends Readable, Writable {
}
~~~

`ReadWrite` combines the two contracts. The class:

~~~java
class MemoryDocument implements ReadWrite {
    private String value = "";

    @Override
    public String read() {
        return value;
    }

    @Override
    public void write(String value) {
        this.value = java.util.Objects.requireNonNull(value);
    }
}
~~~

must satisfy both `read` and `write`.

**Important syntax:** An interface **extends** interfaces; a class **implements** interfaces. Do not write `interface ReadWrite implements Readable`.

An interface can `extends` **multiple interfaces**. This differs from a class, which only `extends` one direct superclass.

## 11. Runnable Example: Multiple Interface Capabilities

Create the file **`MultipleInterfacesDemo.java`**:

~~~java
public class MultipleInterfacesDemo {
    interface Printable {
        void print();
    }

    interface Saveable {
        void save();
    }

    static final class Document implements Printable, Saveable {
        private final String title;

        Document(String title) {
            this.title = title;
        }

        @Override
        public void print() {
            System.out.println("print: " + title);
        }

        @Override
        public void save() {
            System.out.println("save: " + title);
        }
    }

    static void printOnly(Printable item) {
        item.print();
    }

    static void saveOnly(Saveable item) {
        item.save();
    }

    public static void main(String[] args) {
        Document doc = new Document("README");
        printOnly(doc);
        saveOnly(doc);
    }
}
~~~

~~~bash
javac -encoding UTF-8 MultipleInterfacesDemo.java
java MultipleInterfacesDemo
~~~

Stdout:

~~~text
print: README
save: README
~~~

A Document object can be viewed as `Printable` or `Saveable`. The two references do not create two copies of the title data. Each method receives **the exact capability it needs**, reducing coupling to the entire Document class.

### Interface Segregation Principle

A small interface focused on meaningful behavior is usually easier to use than an interface that forces every implementation to provide dozens of unrelated methods. However, do not go to the extreme of splitting into countless single-method interfaces just for the sake of applying the principle. Group by **use case, responsibility, and contract consistency**.

## 12. An Abstract Class Partially Implementing an Interface

An abstract class can leave some abstract methods unimplemented:

~~~java
interface Processor {
    void validate();
    void process();
}

abstract class BaseProcessor implements Processor {
    @Override
    public void validate() {
        System.out.println("validated");
    }

    // process() is not yet implemented in this abstract class.
}

class ConcreteProcessor extends BaseProcessor {
    @Override
    public void process() {
        System.out.println("processed");
    }
}
~~~

ConcreteProcessor receives the `validate` implementation from its superclass and implements `process` itself. It still fulfills the Processor contract.

A concrete class must not leave out any abstract method, unless it inherits a suitable implementation from a superclass or an interface default method where applicable.

### Interfaces and Abstract Classes Solve Two Needs

- An interface defines a **capability and contract that multiple unrelated classes can implement**.
- An abstract class can share **instance state, constructors, and protected helper methods** among subclasses with a true is-a relationship.

Do not use an interface just to replace a superclass with shared mutable state. Interface fields are static constants, not per-instance state.

## 13. Fields in an Interface Are Constants, Not Instance Fields

Inside an interface:

~~~java
interface Limits {
    int MAX_RETRIES = 3;
}
~~~

The field `MAX_RETRIES` implicitly has the modifiers **`public static final`**, equivalent in meaning to:

~~~java
interface Limits {
    public static final int MAX_RETRIES = 3;
}
~~~

It is **not** an instance field dedicated to each implementing object.

### Cannot Reassign an Interface Field

~~~java
// Limits.MAX_RETRIES = 5; // Error: final variable.
~~~

An implementing class does not get its “own copy of MAX_RETRIES” just because it implements Limits. If the class needs per-instance configuration, declare a field in the class:

~~~java
class Retrier {
    private final int maxRetries;

    Retrier(int maxRetries) {
        this.maxRetries = maxRetries;
    }
}
~~~

### Interface Constants Carry Coupling Risks

Putting unrelated static constants into an interface just so classes can `implements Constants` and use short names is the **constant interface anti-pattern**. Prefer an appropriate utility/config class and access the qualified name `Limits.MAX_RETRIES`. An interface should describe a **capability**, not just be a bag of constants.

## 14. Types of Methods in an Interface (Java 17)

| Kind | Example | Meaning |
| --- | --- | --- |
| Abstract instance | `void send();` | Implementing class must provide a body if not already inherited |
| `default` instance | `default String label() { ... }` | Interface provides a default implementation that can be overridden |
| `static` | `static int max() { ... }` | Method belonging to the interface, called using the interface name |
| `private` instance | `private void helper() { ... }` | Helper used only within the code of the interface itself |
| `private static` | `private static int parse() { ... }` | Private static helper inside the interface |

**There are no constructors in an interface.** You cannot write `new InterfaceName()` to create an instance directly. An anonymous class, or a lambda for a functional interface, can create an object of an implementation type, but this does not turn the interface into a class with its own constructor.

### Abstract Method Defaults

~~~java
interface Action {
    void run(); // implicitly public abstract.
}
~~~

You can declare `public abstract void run();` explicitly, though it is usually unnecessary.

Do not confuse a `default` method with default access (package-private): `default` is **an interface method with a body and special inheritance mechanics**, whereas interface abstract methods are public by default.

## 15. Default Methods: Adding Default Behavior

~~~java
interface Named {
    String name();

    default String decoratedName() {
        return "[" + name() + "]";
    }
}
~~~

An implementing class only needs to implement `name()`; `decoratedName()` already has a default implementation and can invoke `name()` dynamically (dynamic dispatch) on the actual object.

### Runnable Example

Create the file **`DefaultMethodDemo.java`**:

~~~java
public class DefaultMethodDemo {
    interface Named {
        String name();

        default String decoratedName() {
            return "[" + name() + "]";
        }
    }

    static final class Person implements Named {
        private final String name;

        Person(String name) {
            this.name = name;
        }

        @Override
        public String name() {
            return name;
        }
    }

    public static void main(String[] args) {
        Named named = new Person("Mai");

        System.out.println(named.name());
        System.out.println(named.decoratedName());
    }
}
~~~

~~~bash
javac -encoding UTF-8 DefaultMethodDemo.java
java DefaultMethodDemo
~~~

Stdout:

~~~text
Mai
[Mai]
~~~

**Do not conclude:** a default method is “automatically right” for every implementing class. If the default behavior imposes assumptions that an implementation cannot satisfy, the class should override it or the interface contract must be redesigned.

Default methods are especially useful for adding an operation built on existing abstract methods without forcing every implementation to rewrite the same logic. However, API evolution requires care because default methods can conflict with other interfaces.

## 16. Static Interface Methods Are Not Called Like Instance Default Methods

~~~java
interface TextTools {
    static String upper(String input) {
        return input.toUpperCase(java.util.Locale.ROOT);
    }
}
~~~

Call it:

~~~java
String result = TextTools.upper("java");
~~~

Do not call `new SomeImplementation().upper(...)` just because the class implements TextTools. Static interface methods belong to the declaring interface and **are not inherited like instance methods**.

### Runnable Example

Create **`StaticInterfaceMethodDemo.java`**:

~~~java
import java.util.Locale;

public class StaticInterfaceMethodDemo {
    interface Formatter {
        String format(String value);

        static String normalized(String value) {
            return value.strip().toUpperCase(Locale.ROOT);
        }
    }

    static final class SimpleFormatter implements Formatter {
        @Override
        public String format(String value) {
            return "[" + Formatter.normalized(value) + "]";
        }
    }

    public static void main(String[] args) {
        Formatter formatter = new SimpleFormatter();
        System.out.println(formatter.format(" java "));
        System.out.println(Formatter.normalized(" hello "));
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticInterfaceMethodDemo.java
java StaticInterfaceMethodDemo
~~~

Stdout:

~~~text
[JAVA]
HELLO
~~~

The static method here is a helper that accompanies the contract. It does not require the class to implement another method.

## 17. Private Methods in Interfaces for Internal Implementation Reuse

Since Java 9, interfaces can declare private methods with a body:

~~~java
interface Greeting {
    String name();

    default String formal() {
        return wrap("Dear " + name());
    }

    default String casual() {
        return wrap("Hi " + name());
    }

    private String wrap(String text) {
        return "<" + text + ">";
    }
}
~~~

`wrap` serves the two default methods; it is not a public member for callers to invoke, and not an abstract method that an implementing class needs to implement.

### Runnable Example

Create **`PrivateInterfaceMethodDemo.java`**:

~~~java
public class PrivateInterfaceMethodDemo {
    interface Message {
        String content();

        default String markdown() {
            return decorate("**", content(), "**");
        }

        default String quoted() {
            return decorate("\"", content(), "\"");
        }

        private static String decorate(
                String before, String value, String after) {
            return before + value + after;
        }
    }

    record Note(String content) implements Message {}

    public static void main(String[] args) {
        Message m = new Note("Java");
        System.out.println(m.markdown());
        System.out.println(m.quoted());
    }
}
~~~

~~~bash
javac -encoding UTF-8 PrivateInterfaceMethodDemo.java
java PrivateInterfaceMethodDemo
~~~

Stdout:

~~~text
**Java**
"Java"
~~~

The record `Note` implements `Message` thanks to the `content()` accessor generated by the record, which has type `String` and is public. There is no need to rewrite the method just to satisfy the abstract accessor. `private static decorate` can only be executed from code within the interface and is not visible to callers.

## 18. Conflict Between Two Default Methods

If two unrelated interfaces both provide a default method with matching signatures, the implementing class may have to **override it and choose the behavior itself**.

~~~java
interface Left {
    default String value() {
        return "left";
    }
}

interface Right {
    default String value() {
        return "right";
    }
}
~~~

You cannot write a concrete class `implements Left, Right` and expect Java to randomly pick one method. You must resolve the conflict:

~~~java
class Both implements Left, Right {
    @Override
    public String value() {
        return Left.super.value() + "+" + Right.super.value();
    }
}
~~~

`Left.super.value()` and `Right.super.value()` invoke specific default implementations from the implementing class when valid.

### Runnable Example

Create **`DefaultConflictDemo.java`**:

~~~java
public class DefaultConflictDemo {
    interface Left {
        default String label() {
            return "L";
        }
    }

    interface Right {
        default String label() {
            return "R";
        }
    }

    static final class Both implements Left, Right {
        @Override
        public String label() {
            return Left.super.label() + Right.super.label();
        }
    }

    public static void main(String[] args) {
        Both object = new Both();
        System.out.println(object.label());
    }
}
~~~

~~~bash
javac -encoding UTF-8 DefaultConflictDemo.java
java DefaultConflictDemo
~~~

Stdout:

~~~text
LR
~~~

**Takeaway:** Java supports multiple interface inheritance, but does not automatically allow “two implementations with the same name to combine themselves” without an explicit resolution rule.

## 19. Precedence Rules: Class Methods and Specificity

When considering default methods, remember these general rules:

1. **A matching concrete method from a class/superclass generally wins over an interface default method** when inherited according to the rules.
2. In an interface hierarchy, **a more specific default method** can be chosen over a less specific inherited default method.
3. When two unrelated defaults conflict, the class must override to resolve it.

### Class Precedence Example

Create the file **`ClassWinsDefaultDemo.java`**:

~~~java
public class ClassWinsDefaultDemo {
    interface Speaker {
        default String speak() {
            return "interface";
        }
    }

    static class Base {
        public String speak() {
            return "class";
        }
    }

    static final class Child extends Base implements Speaker {
    }

    public static void main(String[] args) {
        Speaker speaker = new Child();
        System.out.println(speaker.speak());
    }
}
~~~

~~~bash
javac -encoding UTF-8 ClassWinsDefaultDemo.java
java ClassWinsDefaultDemo
~~~

Stdout:

~~~text
class
~~~

`Child` inherits the `speak` method from Base, so calling it through a Speaker reference still dispatches to the appropriate `Base.speak()` implementation.

**Be careful:** “Class wins” is a shorthand mnemonic, not a replacement for the full JLS rules regarding abstract/concrete methods, visibility, generic erasure, and inheritance. When signatures are complex, check the compiler and the Java specification.

## 20. Object Methods and Interfaces

Every class in Java ultimately has Object-related methods such as `toString()`, `equals(Object)`, and `hashCode()`. Interfaces also interact with these methods, but you should not arbitrarily create a default implementation that overrides an Object method.

Intentionally invalid snippet:

~~~java
interface Bad {
    // default String toString() {
    //     return "bad";
    // }
}
~~~

A default method in an interface that is override-equivalent to a non-private method of Object is not permitted under Java rules.

An implementation class can override Object methods normally to express equality/representation according to the contract:

~~~java
final class Id {
    private final String value;

    Id(String value) {
        this.value = value;
    }

    @Override
    public String toString() {
        return value;
    }
}
~~~

If an interface **mentions** identity/equality in its contract, clear documentation and consistent implementations are needed, especially when objects are used as keys in a Map/Set.

## 21. Functional Interfaces and Lambdas

A **functional interface** has exactly **one abstract method** according to Java rules, although it may contain multiple default/static/private methods. It can serve as the **target type** of a lambda expression or method reference.

~~~java
@FunctionalInterface
interface Transformer {
    String transform(String input);

    default String twice(String input) {
        return transform(transform(input));
    }
}
~~~

`@FunctionalInterface` is optional, but useful because the compiler verifies that the interface meets the functional interface criteria. If another independent abstract method is added, the compiler catches the error.

### Runnable Example

Create the file **`FunctionalInterfaceDemo.java`**:

~~~java
public class FunctionalInterfaceDemo {
    @FunctionalInterface
    interface Transformer {
        String transform(String input);

        default String twice(String input) {
            return transform(transform(input));
        }
    }

    public static void main(String[] args) {
        Transformer addX = text -> text + "X";

        System.out.println(addX.transform("A"));
        System.out.println(addX.twice("A"));
    }
}
~~~

~~~bash
javac -encoding UTF-8 FunctionalInterfaceDemo.java
java FunctionalInterfaceDemo
~~~

Stdout:

~~~text
AX
AXX
~~~

Java assigns the lambda to the functional interface `Transformer`. Not every interface supports lambdas: if there are two distinct abstract methods that need to be implemented, a single lambda is not enough.

**A note:** Abstract methods whose signatures correspond to public methods of `Object` are treated specially when determining a functional interface; it is not simply a matter of counting every method declaration line. Use `@FunctionalInterface` so the compiler checks it accurately.

## 22. Interface References and Collections

A collection can be declared with an interface type to store multiple implementations:

~~~java
java.util.List<Notifier> notifiers = new java.util.ArrayList<>();
notifiers.add(new ConsoleNotifier());
notifiers.add(new FileNotifier());
~~~

When iterating:

~~~java
for (Notifier notifier : notifiers) {
    notifier.send("hello");
}
~~~

the method is dispatched to each object's implementation.

This is illustrative code; `Notifier`, `ConsoleNotifier`, and `FileNotifier` must have corresponding declarations. The `List<Notifier>` type does not require the elements to belong to the same concrete class — each element only needs to have a type compatible with `Notifier`.

### But Remember Generic Invariance

`List<ConsoleNotifier>` **is not automatically a subtype** of `List<Notifier>` in Java generic types, even though ConsoleNotifier implements Notifier. If List<ConsoleNotifier> were allowed to be treated as List<Notifier>, a caller could add a FileNotifier into a list that is only supposed to hold ConsoleNotifier.

To only **read subtype implementations**, you can use:

~~~java
void broadcast(java.util.List<? extends Notifier> targets) {
    for (Notifier target : targets) {
        target.send("hello");
    }
}
~~~

The `? extends Notifier` wildcard fits a consumer method that only needs to read Notifier references to call `send`, without adding arbitrary elements to the list.

## 23. Generic Interfaces: Type-Reusable Contracts

An interface can be generic:

~~~java
interface Repository<T, ID> {
    T findById(ID id);
    void save(T entity);
}
~~~

A concrete implementation:

~~~java
class InMemoryBookRepository
        implements Repository<Book, String> {
    @Override
    public Book findById(String id) {
        // Lookup by id.
        return null;
    }

    @Override
    public void save(Book entity) {
        // Store entity.
    }
}
~~~

This is an illustrative code snippet (it requires a Book class and a real storage implementation). When implementing `Repository<Book, String>`, the method signatures are specialized for `Book` and `String` according to generics rules.

### Complete Runnable Example: Generic Box Contract

Create **`GenericInterfaceDemo.java`**:

~~~java
public class GenericInterfaceDemo {
    interface Box<T> {
        void put(T value);
        T get();
    }

    static final class MemoryBox<T> implements Box<T> {
        private T value;

        @Override
        public void put(T value) {
            this.value = value;
        }

        @Override
        public T get() {
            return value;
        }
    }

    public static void main(String[] args) {
        Box<String> message = new MemoryBox<>();
        Box<Integer> count = new MemoryBox<>();

        message.put("Java");
        count.put(17);

        System.out.println("message=" + message.get());
        System.out.println("count=" + count.get());
    }
}
~~~

~~~bash
javac -encoding UTF-8 GenericInterfaceDemo.java
java GenericInterfaceDemo
~~~

Stdout:

~~~text
message=Java
count=17
~~~

A generic interface helps reuse a contract while the compiler still checks element types. However, generics in Java have **type erasure**; `Box<String>` and `Box<Integer>` are not two distinct runtime interface classes merely because of their type arguments.

## 24. Checked Exceptions and `throws` in Implementations

An interface method can declare checked exceptions:

~~~java
interface Reader {
    String read() throws java.io.IOException;
}
~~~

An implementation can:

- Throw `IOException` according to a compatible declaration.
- Throw a checked subtype of IOException.
- Declare no checked exceptions at all.

However, it must not arbitrarily widen checked exceptions beyond the contract of the overridden method:

~~~java
class MemoryReader implements Reader {
    @Override
    public String read() {
        return "memory";
    }
}
~~~

**It is invalid if** an implementation changes this to `read() throws Exception`, because `Exception` is broader than IOException and does not satisfy the overriding rules for checked exceptions.

### A Subtle Point

An interface method **that declares no checked exception** does not prevent an implementation from throwing unchecked exceptions such as `IllegalArgumentException` or `IllegalStateException`. However, API designers should document predictable error conditions rather than hiding all failure behavior from the caller.

## 25. Runnable Example: Checked Exception Contract

Create the file **`CheckedExceptionInterfaceDemo.java`**:

~~~java
import java.io.IOException;

public class CheckedExceptionInterfaceDemo {
    interface DataSource {
        String load() throws IOException;
    }

    static final class MemorySource implements DataSource {
        @Override
        public String load() {
            return "cached";
        }
    }

    static final class FailingSource implements DataSource {
        @Override
        public String load() throws IOException {
            throw new IOException("unavailable");
        }
    }

    static void show(DataSource source) {
        try {
            System.out.println(source.load());
        } catch (IOException ex) {
            System.out.println("error=" + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        show(new MemorySource());
        show(new FailingSource());
    }
}
~~~

~~~bash
javac -encoding UTF-8 CheckedExceptionInterfaceDemo.java
java CheckedExceptionInterfaceDemo
~~~

Stdout:

~~~text
cached
error=unavailable
~~~

Because `show` calls through a `DataSource` reference, the compiler requires the code to handle or declare `IOException` even though the actual object might be a MemorySource that throws no checked exception. The **declared interface type** shapes the caller's compile-time obligations.

## 26. Semantic Contracts: The Compiler Does Not Prove a Method Is “Correct”

Consider:

~~~java
interface Sorter {
    void sort(int[] values);
}
~~~

A class might write:

~~~java
class BrokenSorter implements Sorter {
    @Override
    public void sort(int[] values) {
        java.util.Arrays.fill(values, 0);
    }
}
~~~

The signature is valid, and the compiler accepts it. However, if the contract requires:

- After sorting, the array is arranged in non-decreasing order.
- No elements are lost or added (the original multiset is preserved).
- The array length is not changed.

then `BrokenSorter` **violates the contract** by replacing all elements with 0. The code snippet above is only meant to distinguish a **syntactic contract** from a **behavioral contract**.

### Writing a Sufficiently Clear Contract

An interface should document meaningful requirements:

- **Preconditions:** can the input be null? Are there size limits?
- **Postconditions:** the result/observable state after success.
- **Failure behavior:** when the input is invalid or I/O fails, what happens?
- **Mutation ownership:** is the method allowed to mutate the input object?
- **Invariants:** conditions that always remain true across operations.
- **Concurrency guarantees:** thread-safe, nonblocking, or no guarantee.
- **Ordering/idempotence:** does the result depend on order, and can it be called repeatedly?

The compiler only verifies a portion of these rules; tests and reviews need to verify the rest.

## 27. Behavioral Substitutability and the Liskov Principle

The **Liskov Substitution Principle (LSP)** in the context of interfaces: an implementing class must be usable wherever the interface is expected **without breaking the caller's valid assumptions**.

For example, the interface:

~~~java
interface Queue<E> {
    void enqueue(E item);
    E dequeue();
}
~~~

If the contract states that `enqueue` of a non-null item adds it to the back of the queue and `dequeue` returns the earliest inserted element when non-empty, an implementation that accepts an item and silently discards it violates the behavior even though the signatures are valid.

### Signs of Violation

- An implementation unexpectedly throws `UnsupportedOperationException` for an operation that the contract promises to support.
- Strengthening a precondition in a way not permitted by the contract.
- Failing to preserve a postcondition or invariant that callers rely on.
- Altering the meaning of the returned data.
- Changing ordering or atomicity semantics contrary to documentation.

An overly broad interface can force an implementation that lacks genuine support for some methods. In that case, consider **splitting the interface by capability** instead of implementing methods by throwing exceptions unconditionally.

## 28. Shared Contract Tests Across Multiple Implementations

One way to verify behavior is to write **the same test logic** for every implementation.

Create the file **`ContractTestDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ContractTestDemo {
    interface Stack {
        void push(int value);
        int pop();
        boolean isEmpty();
    }

    static final class ArrayStack implements Stack {
        private final List<Integer> items = new ArrayList<>();

        @Override
        public void push(int value) {
            items.add(value);
        }

        @Override
        public int pop() {
            if (items.isEmpty()) {
                throw new IllegalStateException("empty stack");
            }
            return items.remove(items.size() - 1);
        }

        @Override
        public boolean isEmpty() {
            return items.isEmpty();
        }
    }

    static final class LinkedStack implements Stack {
        private final java.util.ArrayDeque<Integer> items =
                new java.util.ArrayDeque<>();

        @Override
        public void push(int value) {
            items.push(value);
        }

        @Override
        public int pop() {
            if (items.isEmpty()) {
                throw new IllegalStateException("empty stack");
            }
            return items.pop();
        }

        @Override
        public boolean isEmpty() {
            return items.isEmpty();
        }
    }

    static void verify(Stack stack) {
        if (!stack.isEmpty()) {
            throw new AssertionError("new stack must be empty");
        }
        stack.push(10);
        stack.push(20);

        if (stack.pop() != 20 || stack.pop() != 10) {
            throw new AssertionError("LIFO violated");
        }

        if (!stack.isEmpty()) {
            throw new AssertionError("stack must be empty");
        }
    }

    public static void main(String[] args) {
        verify(new ArrayStack());
        System.out.println("ArrayStack PASS");

        verify(new LinkedStack());
        System.out.println("LinkedStack PASS");
    }
}
~~~

~~~bash
javac -encoding UTF-8 ContractTestDemo.java
java ContractTestDemo
~~~

Stdout:

~~~text
ArrayStack PASS
LinkedStack PASS
~~~

The same `verify(Stack)` function accepts both implementations. It checks **LIFO** and the empty state after push/pop. If you swap in an implementation with broken semantics, the test can detect it.

**Limitations:** A few assertions cannot prove every scenario. Also test empty-pop behavior, pushing many elements, duplicates, boundary cases, and concurrency if the contract requires them. In real projects, you can use JUnit parameterized tests or an abstract contract-test suite.

## 29. Interfaces for Dependency Injection

A service uses a dependency via an interface:

~~~java
interface EmailGateway {
    void deliver(String to, String message);
}

class RegistrationService {
    private final EmailGateway gateway;

    RegistrationService(EmailGateway gateway) {
        this.gateway = java.util.Objects.requireNonNull(gateway);
    }

    void register(String email) {
        gateway.deliver(email, "Welcome");
    }
}
~~~

`RegistrationService` does not need to know whether the email is sent via SMTP, a cloud provider, or an in-memory fake. It only needs an `EmailGateway` that adheres to the contract.

In tests, you can supply a fake implementation to avoid sending real emails.

### Practical Benefits

1. **Swap implementations** without modifying the service.
2. **Isolate tests** from network/file/database dependencies when a suitable fake exists.
3. **Manage lifecycle** via constructor injection rather than static global fields.
4. **Reduce coupling** to implementation details.
5. Easy to introduce a logging/retry adapter if the contract allows.

This does not mean every class must have its own interface just for easy mocking. Create abstractions at **boundaries where multiple reasonable implementations exist or there is a clear need for substitution**.

## 30. Runnable Example: Fake Implementation in Testing

Create **`InterfaceInjectionDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class InterfaceInjectionDemo {
    interface Notifier {
        void notifyUser(String message);
    }

    static final class MemoryNotifier implements Notifier {
        private final List<String> messages = new ArrayList<>();

        @Override
        public void notifyUser(String message) {
            messages.add(message);
        }

        List<String> messagesSnapshot() {
            return List.copyOf(messages);
        }
    }

    static final class RegistrationService {
        private final Notifier notifier;

        RegistrationService(Notifier notifier) {
            this.notifier = Objects.requireNonNull(notifier);
        }

        void register(String userName) {
            if (userName == null || userName.isBlank()) {
                throw new IllegalArgumentException("name required");
            }
            notifier.notifyUser("Welcome " + userName);
        }
    }

    public static void main(String[] args) {
        MemoryNotifier fake = new MemoryNotifier();
        RegistrationService service = new RegistrationService(fake);

        service.register("Mai");
        service.register("An");

        System.out.println(fake.messagesSnapshot());
    }
}
~~~

~~~bash
javac -encoding UTF-8 InterfaceInjectionDemo.java
java InterfaceInjectionDemo
~~~

Stdout:

~~~text
[Welcome Mai, Welcome An]
~~~

`RegistrationService` only knows the `Notifier` contract; observing fake messages is a matter of test wiring, not the service depending on the fake implementation. In production, you can pass a different implementation that actually sends notifications.

**Do not misunderstand:** A fake implementation must still simulate the necessary semantics for the test to be trustworthy; if the fake skips retry logic, authorization, or important error conditions, integration tests with the real system are needed.

## 31. Interfaces vs. Abstract Classes

| Criterion | Interface | Abstract class |
| --- | --- | --- |
| Primary purpose | Capability/contract used across many types | Base class sharing implementation/state |
| Class relationship | `implements` | `extends` |
| Can a class use multiple? | Implements multiple interfaces | Extends one direct superclass |
| Constructors | No | Yes |
| Instance fields | No instance fields declared in an interface | Yes |
| Constants | Interface fields are public static final | Can have various kinds of fields |
| Methods without a body | Abstract methods | Abstract methods |
| Methods with a body | default/static/private per rules | Concrete instance/static methods |
| Protected members | Cannot use protected interface members | Can use protected |
| Best suited for | Contracts independent of a hierarchy | Shared behavior/state across subclasses |

### Guidelines for Choosing

- “A **is a kind of** B and genuinely inherits shared state/behavior”: consider class inheritance.
- “A is capable of performing B without necessarily belonging to the same class family”: consider an interface.
- “A **has a** B used to perform work”: consider composition/dependency injection.

Do not design an interface merely to replace inheriting from a stateful helper; nor force unrelated classes to extend an abstract base class when they only need a shared capability.

## 32. Interfaces with Records and Enums

Records can implement interfaces; for example:

~~~java
interface HasId {
    String id();
}

record Product(String id, String name) implements HasId {
}
~~~

The record component accessor `id()` satisfies the `HasId.id()` method. A record cannot extend an arbitrary application class; it has its own inheritance mechanism, yet it can still implement interfaces.

Enums can also implement interfaces:

~~~java
interface Action {
    String label();
}

enum Direction implements Action {
    NORTH, SOUTH;

    @Override
    public String label() {
        return name().toLowerCase(java.util.Locale.ROOT);
    }
}
~~~

These are two independent declarations to illustrate implementation capability. An enum constant can have its own behavior implementation via constant-specific class bodies in appropriate designs.

## 33. Runnable Example: A Record and an Enum Sharing One Interface

Create **`RecordEnumInterfaceDemo.java`**:

~~~java
public class RecordEnumInterfaceDemo {
    interface Labelled {
        String label();
    }

    record Tag(String label) implements Labelled {}

    enum Priority implements Labelled {
        LOW, HIGH;

        @Override
        public String label() {
            return name().toLowerCase(java.util.Locale.ROOT);
        }
    }

    static void print(Labelled item) {
        System.out.println(item.label());
    }

    public static void main(String[] args) {
        print(new Tag("Java"));
        print(Priority.HIGH);
    }
}
~~~

~~~bash
javac -encoding UTF-8 RecordEnumInterfaceDemo.java
java RecordEnumInterfaceDemo
~~~

Stdout:

~~~text
Java
high
~~~

The same `Labelled` contract is implemented by a record and an enum in two different ways. An interface does not force every implementing type to be a “normal class with a constructor” or have the same internal fields.

## 34. Sealed Interfaces in Java 17

Java 17 supports **sealed interfaces**, allowing you to restrict which types are directly permitted to extend/implement them:

~~~java
sealed interface Result permits Success, Failure {
}

record Success(String value) implements Result {
}

record Failure(String message) implements Result {
}
~~~

Records are implicitly final, making them valid permitted direct implementing types. Not just any class outside the `permits` list is allowed to directly `implements Result`.

### Why Use a Sealed Interface?

When a domain has a **closed set of cases**: success/failure results, or valid kinds of commands or shapes, sealed interfaces help restrict extensibility.

**Be careful:**

- Permitted subclasses/implementations must follow module/package rules as well as `final`, `sealed`, or `non-sealed` modifiers where applicable.
- Sealed **does not make instances immutable**. A permitted final class can still hold mutable state.
- Java 17 already has `instanceof` pattern matching; **pattern matching switch for sealed types** was in preview in Java 17 and cannot be used as standard Java 17 code without enabling the appropriate flags. To keep the program easy to run, use the `instanceof` pattern.

## 35. Runnable Example: Sealed Interface and `instanceof`

Create **`SealedInterfaceDemo.java`**:

~~~java
public class SealedInterfaceDemo {
    sealed interface Result permits Success, Failure {
    }

    record Success(String value) implements Result {
    }

    record Failure(String message) implements Result {
    }

    static String show(Result result) {
        if (result instanceof Success success) {
            return "OK: " + success.value();
        }
        if (result instanceof Failure failure) {
            return "ERROR: " + failure.message();
        }
        throw new IllegalStateException("unexpected result");
    }

    public static void main(String[] args) {
        System.out.println(show(new Success("saved")));
        System.out.println(show(new Failure("invalid")));
    }
}
~~~

~~~bash
javac -encoding UTF-8 SealedInterfaceDemo.java
java SealedInterfaceDemo
~~~

Stdout:

~~~text
OK: saved
ERROR: invalid
~~~

The sealed Result explicitly declares two permitted direct implementations. The type handling uses Java 17 `instanceof` patterns and does not require the preview switch feature. In terms of contract, Result represents an intentional set of cases, unlike an interface open to arbitrary plugin implementations.

## 36. Common Compiler Errors

| Code/Intent | Issue | Fix |
| --- | --- | --- |
| `class A implements I` missing an abstract method | Concrete class has not completed the contract | Implement the method or declare the class abstract |
| Package-private implementation method | Interface method is public | Write `public` |
| Wrong method name | Does not override the matching member | Use `@Override` and match the signature |
| Only overloading `process(long)` when the interface requires `process(int)` | Different method | Implement with the exact parameters |
| Different primitive return type | Incompatible return type | Use a valid return type |
| Adding `throws Exception` when the interface only allows `IOException` | Broader checked exception | Narrow it or update the contract |
| `new SomeInterface()` | Interfaces have no direct instances | Use an implementation, anonymous class, or suitable lambda |
| `interface B implements A` | Interfaces use `extends` | Fix the syntax |
| `class C extends A, B` with two classes | Java does not support multiple class inheritance | Use one superclass + interfaces/composition |
| Two unrelated defaults with the same signature | Ambiguous/conflicting inherited defaults | Override to resolve explicitly |
| Calling an interface static method via an instance | Not inherited like an instance method | Call `I.method()` |
| Reassigning an interface field | Interface field is final | Keep constants immutable; move state into a class |
| Assuming an interface has instance fields | No instance fields are declared in an interface | Store state in the implementing class |
| Lambda using an interface with multiple abstract methods | Not a functional interface | Use an anonymous/concrete class or split the contract |
| `@FunctionalInterface` without meeting requirements | Compiler reports an error | Ensure a single abstract method contract |
| Class not permitted by a sealed interface | Hierarchy is restricted | Add the permitted type per rules or redesign |
| Calling an implementation-specific method via an interface reference | Declared type does not see the member | Depend on the proper contract or use a checked cast with good reason |

Exact compiler messages vary across javac versions. Compare the **member declared in the interface**, the **actual implementation member**, and the **subtype/override rules** instead of trying random name edits.

## 37. Anti-patterns: Empty Interfaces, Overly Broad Interfaces, and Single-Class Interfaces

Not every interface automatically creates good architecture.

### Overly Broad Interfaces

~~~java
interface MegaService {
    void sendEmail();
    void generatePdf();
    void chargeCard();
    void renderChart();
}
~~~

If an implementation only genuinely does one thing, it may be forced to implement meaningless methods and throw `UnsupportedOperationException`, violating caller expectations.

**How to improve:** Split into capability interfaces aligned with use cases and inject the exact interface needed.

### Interfaces That Merely Duplicate Every Public Method of One Class

If a class has only one implementation, no external boundary/test seam, no interchangeability, and no independent contract, an interface `FooInterface` that merely mirrors `Foo` can add unnecessary files and coupling.

It is not true that “having only one implementation is always wrong”. A payment gateway boundary, even with only one current implementation, may still be worth abstracting because it is an **external dependency or stable contract**. Base the decision on substitution reasons, testability, and architecture, not the current class count.

### Marker Interfaces

An interface **with no methods** such as `java.io.Serializable` can be used to represent a marker contract with special platform/framework semantics. However, for arbitrary metadata, annotations or explicit capabilities are usually easier to understand; do not create a marker interface by default for every property.

## 38. Designing a Good Contract for a Scenario

Suppose we are designing `Storage`:

~~~java
interface Storage {
    void save(String key, byte[] data);
    byte[] load(String key);
}
~~~

Before writing an implementation, decide:

- Is `key == null` or blank allowed?
- When a key does not exist, does `load` return null, Optional, or throw an exception?
- Does `save` overwrite an existing key?
- Should mutable `byte[]` input/output data be protected with copies?
- Are I/O errors represented as checked or unchecked exceptions?
- Are concurrent readers/writers supported?
- Does calling `load` immediately after `save` return the same data?
- Is persistence guaranteed across process restarts?
- If the caller mutates the same byte array reference after save, does it alter the stored data?

Without determining these questions, two classes that both `implements Storage` may **behave very differently** and fail to be interchangeable in the program.

### A Clear Contract Enables Shared Tests

One concrete choice: “`save` keeps a snapshot of the data; `load` returns a copy; a nonexistent key throws `NoSuchElementException`; all keys are nonblank; no multi-thread guarantees.”

Then MemoryStorage and FileStorage can be tested with the same suite (aside from criteria related to the file implementation's durability).

## 39. Complete Example: Storage Interface with Defensive Copies

Create **`StorageContractDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;
import java.util.NoSuchElementException;

public class StorageContractDemo {
    interface Storage {
        void save(String key, byte[] data);
        byte[] load(String key);
    }

    static final class MemoryStorage implements Storage {
        private final Map<String, byte[]> entries = new HashMap<>();

        private static void checkKey(String key) {
            if (key == null || key.isBlank()) {
                throw new IllegalArgumentException("key required");
            }
        }

        @Override
        public void save(String key, byte[] data) {
            checkKey(key);
            if (data == null) {
                throw new IllegalArgumentException("data required");
            }
            entries.put(key, data.clone());
        }

        @Override
        public byte[] load(String key) {
            checkKey(key);
            byte[] data = entries.get(key);
            if (data == null) {
                throw new NoSuchElementException("missing: " + key);
            }
            return data.clone();
        }
    }

    public static void main(String[] args) {
        Storage storage = new MemoryStorage();
        byte[] input = {1, 2, 3};

        storage.save("A", input);
        input[0] = 9;

        byte[] result = storage.load("A");
        result[1] = 8;

        System.out.println("input=" + Arrays.toString(input));
        System.out.println("result=" + Arrays.toString(result));
        System.out.println("stored=" +
                Arrays.toString(storage.load("A")));
    }
}
~~~

~~~bash
javac -encoding UTF-8 StorageContractDemo.java
java StorageContractDemo
~~~

Stdout:

~~~text
input=[9, 2, 3]
result=[1, 8, 3]
stored=[1, 2, 3]
~~~

This example illustrates **contract semantics beyond syntax**: `Storage.save/load` operates on a mutable `byte[]`. If an implementation keeps the raw input reference or returns the internal array directly, the caller could modify stored data after `save` without calling `save` again, violating the chosen snapshot policy.

The `MemoryStorage` class uses `clone()` to copy the primitive array upon receiving and returning it; that property **does not emerge automatically just from implementing the interface**. For reference arrays or object graphs, clone is a shallow copy; a separate contract is needed.

## 40. Interface Inheritance and API Stability

When you publish an interface in a library, many classes written by others may implement it. Adding a new **abstract method** can force every implementation to update, creating a compatibility impact.

Adding a `default` method with a body sometimes helps evolve an API less disruptively, yet can still cause:

- Conflicts with a default method in another interface.
- Conflicts/override rules with methods in a class hierarchy.
- Default behavior unsuitable for an implementation's semantics.
- Compilation or linkage issues when library and client versions differ.
- Misunderstandings if the default method assumes an invariant not guaranteed by the contract.

### Principles of Contract Evolution

1. Design a small number of abstract methods that still express the capability sufficiently.
2. Clearly describe inputs, outputs, exceptions, side effects, and concurrency guarantees.
3. If a major capability needs to be added, consider **a new interface extending the old interface** instead of changing the old API.
4. Test old and new implementations with contract tests.
5. Avoid exposing mutable fields through interface constants.
6. Consider backward compatibility at both source and binary levels.

An interface is a **stability promise for callers and implementers**. Changing it can affect two different groups.

## 41. A Class Can Both Overload Methods and Implement an Interface

Example:

~~~java
interface Reader {
    String read();
}

class FileReader implements Reader {
    @Override
    public String read() {
        return "all";
    }

    public String read(int limit) {
        return "first " + limit;
    }
}
~~~

`read()` satisfies the Reader interface. `read(int)` is another overload, visible only through the declared type `FileReader` (or another interface declaring that signature).

When a method is overloaded:

~~~java
void show(Readable value) { ... }
void show(Object value) { ... }
~~~

overload selection depends on **compile-time types**, whereas the implementation of an overridden instance method depends on the actual receiver object at runtime. These are two different mechanisms: **overload resolution** and **dynamic dispatch**.

When learning polymorphism, do not assume that having the same method name automatically means overriding/implementing. The signatures must be compatible.

## 42. Exercise 1 — Interface and Two Implementations

Write an interface `Shape`:

~~~java
interface Shape {
    double area();
}
~~~

Create `Rectangle` accepting positive width/height and `Circle` accepting positive radius, with each class `implements Shape`. Then write the method:

~~~java
static void show(Shape shape) {
    System.out.println(shape.area());
}
~~~

Call it with two different kinds of shape. Use only the `area()` method inside `show`, without casting to Rectangle/Circle. Validate negative or zero inputs.

**Focus:** The caller works with the **area capability**, while each implementation defines its own formula.

## 43. Exercise 2 — Find the `public`/Signature Bug

Given:

~~~java
interface Report {
    void generate(String format);
}

class PdfReport implements Report {
    // void generate(String format) { ... }
}
~~~

If you uncomment it and write a body, why does it still fail? **Answer:** The interface method `generate` is public; the method in the class lacks a modifier, making it package-private. Fix it to:

~~~java
@Override
public void generate(String format) {
    System.out.println(format);
}
~~~

Next, try changing the parameter to `Object format`; that is an overload that does not implement the exact `generate(String)` signature.

## 44. Exercise 3 — Interface Reference and Class-Specific Methods

~~~java
interface Animal {
    void sound();
}

class Dog implements Animal {
    @Override
    public void sound() {
        System.out.println("woof");
    }

    public void fetch() {
        System.out.println("fetch");
    }
}
~~~

Suppose `Animal pet = new Dog();`. Why is `pet.sound()` valid while `pet.fetch()` does not compile?

**Answer:** The compile-time type Animal only has `sound()`; the runtime Dog object determines the implementation of sound. `fetch` is a Dog-specific method, not part of the Animal contract. Only use a checked cast/`instanceof` if the use case genuinely requires that specific capability.

## 45. Exercise 4 — Two Interfaces with Identical Default Method Names

Suppose `Left` and `Right` both have `default String label()`. Write a class `Both implements Left, Right` so that `label()` returns `"L+R"`.

**Suggested answer:**

~~~java
@Override
public String label() {
    return Left.super.label() + "+" + Right.super.label();
}
~~~

This is the method body placed inside Both. The exercise helps distinguish multiple interface inheritance from multiple class inheritance and conflicting default implementations.

## 46. Exercise 5 — Contract Tests and Broken Implementations

Given the interface:

~~~java
interface Counter {
    void increment();
    int value();
}
~~~

Contract: `value()` starts at 0; each successful `increment()` increases it by exactly 1, and it does not change when merely reading.

Write two implementations: one using `int`, and one using `AtomicInteger`. Write **one** function `verify(Counter c)` that checks the contract for both.

**Bonus question:** Does `AtomicInteger` mean the `Counter` contract automatically promises thread safety? **No.** If you want all implementations to be thread-safe, you must specify that in the contract and test concurrency separately.

## 47. Exercise 6 — Designing Interfaces by Capability

A system has an email sender, PDF printer, audit logger, and payment processor. Consider:

**Option A:** One `EverythingService` interface with four methods, forcing every class to implement all of them.

**Option B:** `Notifier`, `Printable`, `AuditSink`, and `PaymentGateway` aligned with clear capabilities.

**Answer:** Option B is usually more suitable when callers only need a single capability and implementations have distinct responsibilities. However, the number of interfaces should reflect real boundaries; do not split into dozens of meaningless abstractions just to follow a pattern.

## 48. Exercise 7 — Record Implementing an Interface

Given:

~~~java
interface HasCode {
    String code();
}
~~~

Write:

~~~java
record Product(String code, long price) implements HasCode {
}
~~~

Explain why the `Product` record can satisfy `code()` even without explicitly writing that method: the generated **record component accessor `code()`** matches the public method signature in the interface.

Extension task: add a compact constructor that checks `code` is nonblank and `price >= 0`. Remember that the compile-time contract does not automatically check price/ID invariants.

## 49. Exercise 8 — Reading a Sealed Interface Error

Suppose a sealed interface `Result` only `permits Success, Failure`. Why can a class `Pending implements Result` that is not in permits be rejected by the compiler?

**Answer:** `sealed` defines the permitted **direct** subclasses/implementations under Java 17 rules. To open up a Pending case, you must adjust the hierarchy/permits and comply with the `final`/`sealed`/`non-sealed` requirement for permitted declarations. Consider whether this change breaks the contract for callers assuming only Success/Failure exist.

## 50. Exercise 9 — Distinguishing Syntactic and Semantic Contracts

An interface:

~~~java
interface MoneyTransfer {
    void transfer(long amount);
}
~~~

A class implements the method, but deducts the money first and then reports an error if the balance becomes negative.

**Question:** Why can the compiler still accept the class? Why might the implementation be wrong?

**Answer:** The signature is compatible, yet the operation can break the invariants “balance must not be negative” and “a failed transaction must not lose money”. Define preconditions, postconditions, and failure behavior; validate all conditions before updating or use an appropriate transaction. A contract is useful when **verified by both code and tests**, not just signatures.

## 51. Frequently Asked Questions

### 51.1. Can an interface be instantiated into an object?

You cannot directly instantiate an interface like a concrete class. However, an interface-typed variable can reference an instance of an implementing class, an anonymous class, or an object created from a lambda when the target is a functional interface.

### 51.2. Does a class implementing two interfaces create two objects?

No. A class instance can be viewed through multiple interface types, yet it is **a single runtime object**.

### 51.3. Does an interface have constructors or instance state?

It does not have constructors or instance fields the way a class does. Fields declared in an interface are public static final; per-instance state must be managed by the implementing class.

### 51.4. What if a class does not implement all methods?

A concrete class will not compile if any required abstract method has not yet been implemented or inherited with a suitable implementation. You can declare the class `abstract` so subclasses complete it.

### 51.5. Must an interface method be `public` when implemented?

For public abstract interface methods, the implementation must have public access (or a valid inherited public method). Use `@Override` and declare `public` to avoid errors.

### 51.6. Why can't a method with a different return type implement the interface method?

Overriding requires return-type compatibility; reference types can be covariant in appropriate cases, but you cannot arbitrarily change a primitive return type.

### 51.7. Does a `default` method always run?

No. A class can override it; a matching concrete superclass method can take precedence; conflicts between unrelated defaults can require an explicit override.

### 51.8. Are interface static methods inherited by a class?

Not in the way instance methods/default methods are inherited. Typically, you call `InterfaceName.staticMethod()`.

### 51.9. Should every class have an interface?

No. Prefer an interface when there is a useful capability/contract, a need for polymorphism, a test seam, or a clear stable dependency boundary. A sole mirror interface with no distinct role can make the project more complex.

### 51.10. Do `implements` and `extends` differ in runtime dispatch?

Both a class implementing an interface and a class extending/overriding an instance method can participate in runtime polymorphism; however, hierarchy rules, method inheritance, and state sharing differ. `implements` does not make a class a direct subclass of an implementation class.

### 51.11. Can a lambda be used instead of an implementing class?

Only when the target interface is a **functional interface** and the lambda body satisfies the abstract method contract. You cannot use a lambda to instantiate an interface with multiple distinct abstract operations.

### 51.12. Does an interface guarantee thread safety?

No. Thread safety must be explicitly specified by the contract, and all relevant implementations must satisfy it using immutable state, synchronization, atomic operations, or appropriate ownership.

## 52. End-of-Lesson Checklist

- [ ] I can explain an interface as a reference type and a behavioral contract.
- [ ] I know `implements` in a class and `extends` in an interface.
- [ ] I distinguish compile-time method availability from runtime method dispatch.
- [ ] I know that a concrete class must implement the required abstract methods.
- [ ] I use `@Override` and `public` correctly when implementing.
- [ ] I recognize that an overload is not an override/implementation.
- [ ] I understand covariant reference returns and checked exception constraints.
- [ ] I can use a single interface reference for multiple implementations.
- [ ] I know a class implements multiple interfaces but extends at most one superclass.
- [ ] I understand that interface fields are public static final, not per-instance state.
- [ ] I can use `default` methods and know when they are overridden.
- [ ] I call `static` methods through the interface name.
- [ ] I understand `private` helper methods in Java 17 interfaces.
- [ ] I can resolve conflicts between two default methods.
- [ ] I understand that a superclass concrete method can take precedence over a default method.
- [ ] I distinguish between abstract classes and interfaces when choosing an architecture.
- [ ] I know what a functional interface is and can write a lambda for the right target type.
- [ ] I understand generic interfaces and why `List<Concrete>` is not automatically a `List<Interface>`.
- [ ] I can have a record/enum implement an interface.
- [ ] I understand sealed interfaces and restricting direct implementations in Java 17.
- [ ] I know the compiler checks signatures and does not automatically prove behavioral correctness.
- [ ] I can write preconditions, postconditions, invariants, and error behavior.
- [ ] I understand the substitutability of multiple implementations following the same contract.
- [ ] I can write a shared contract test for two implementations.
- [ ] I use constructor injection via an interface when there is a boundary that needs swapping.
- [ ] I know the benefits and risks of adding a method to a public library interface.
- [ ] I avoid creating overly broad interfaces or abstractions without a clear reason.
- [ ] I can run the Java 17+ examples and get the exact stdout shown in the lesson.

**Conclusion:** `implements` is not merely syntax for treating a class as a subtype of an interface. It is a declaration that the class provides **the capabilities that callers are entitled to expect**. Interfaces help separate **“what needs to be done”** from **“how it is done”**, laying the foundation for polymorphism, dependency injection, contract tests, and loosely coupled module design. However, a valid signature does not guarantee business-logic correctness: **substitutability across implementations depends on every class honoring the semantic contract**, error handling, invariants, and published constraints.
