# Single Class Inheritance and Multiple Interface Inheritance in Java

In Java, **a class can directly inherit from only one superclass**, but **can implement multiple interfaces**. An interface itself can also **inherit from multiple other interfaces**. This mechanism allows reusing state and behavior along a clear class hierarchy while allowing an object to fulfill multiple behavioral contracts.

This lesson focuses on the relationship between class types and interface types, Java 17+ syntax, how the JVM/Java selects methods when there are multiple sources of inherited behavior, and how to design to avoid conflicts.

## 1. Three Core Rules

| Relationship | Syntax | Direct Count | Meaning |
| --- | --- | --- | --- |
| Class inherits from class | class Child extends Parent | At most **one** superclass | Receives inheritable state and behavior from the superclass. |
| Class implements interface | class Child implements A, B | **Multiple** interfaces | Commits to providing the behaviors required by the interfaces' contracts; can inherit default methods. |
| Interface inherits from interface | interface C extends A, B | **Multiple** interfaces | Combines or extends contracts, and can inherit default methods. |

Syntax example:

~~~java
class Animal {
    void sleep() {}
}

interface Swimmable {
    void swim();
}

interface Trackable {
    String trackingId();
}

class Dolphin extends Animal implements Swimmable, Trackable {
    @Override
    public void swim() {}

    @Override
    public String trackingId() {
        return "D-01";
    }
}

interface Monitored extends Swimmable, Trackable {
    void report();
}
~~~

This is a **declaration illustration snippet**, not a program with a main method. A class places extends before implements; implements lists interfaces separated by commas. An interface uses extends, not implements. A class that does not declare extends implicitly inherits directly from Object (except Object itself).

It is important to distinguish **class inheritance** from **type polymorphism**: Dolphin has only one direct superclass, Animal, but an instance of Dolphin can be referenced by the type Dolphin, Animal, Swimmable, Trackable, or Object.

## 2. Why Does Java Only Allow Single Class Inheritance?

A class can carry **object state** (instance fields), constructors, concrete methods, abstract methods, and initialization rules. If a class were allowed to directly inherit from multiple classes, the system would have to resolve many issues such as superclass initialization paths, field conflicts, and versions of methods with the same name. Java chooses a single superclass chain to maintain a simple and deterministic model.

~~~java
class Vehicle {}
class Machine {}

// Invalid in Java:
// class Robot extends Vehicle, Machine {}
~~~

A subclass can extend the inheritance chain (Car extends Vehicle, ElectricCar extends Car), but at **each level**, that class still declares at most one direct superclass. You cannot use commas after extends to inherit from multiple classes.

Important conditions:

- A final class does not allow other classes to extend it.
- Constructors are not inherited; a subclass constructor invokes the superclass constructor using super(...) or the corresponding default call.
- Private members of a superclass cannot be accessed directly from a subclass; access levels and overriding rules still follow Java rules.
- An abstract class can also extend only one other class. The final concrete class must implement all abstract methods for which it is still responsible; an abstract class may leave them unimplemented.

**Single inheritance does not mean you can only use one kind of behavior.** Additional behavior should be described using interfaces or composed from collaborating objects (composition).

## 3. How Does Multiple Interface Inheritance Work?

An interface primarily describes **a type and behavioral contract**. A class implements multiple interfaces at the same time and must satisfy their abstract methods (directly or via a public method inherited from a superclass), unless the class itself is abstract.

~~~java
interface Readable {
    String read();
}

interface Writable {
    void write(String value);
}

interface ReadWritable extends Readable, Writable {
    void clear();
}
~~~

ReadWritable extends both Readable and Writable. Any concrete class that implements ReadWritable must provide all of read(), write(String), and clear(). It is also considered a Readable and a Writable. This can be visualized as:

~~~text
Readable       Writable
      \         /
       ReadWritable
             ^
             | implements
         MemoryStore
~~~

Unlike classes, interfaces **do not hold instance state** and **do not have constructors**. Fields declared in an interface are implicitly public static final, so they are typically used for constants rather than storing per-object state.

Since Java 8, interfaces have default methods (methods with a body inherited as default behavior) and static methods. Since Java 9, interfaces also have private methods as internal helpers for methods inside the interface. Those capabilities **do not turn interfaces into classes with instance state or multiple class inheritance**.

## 4. Complete Example: One Superclass, Multiple Interfaces, Polymorphism

Create the file Main.java:

~~~java
public class Main {
    interface Identifiable {
        String id();
    }

    interface Named {
        default String label() {
            return "item-" + name();
        }

        String name();
    }

    interface Auditable {
        default String auditType() {
            return "tracked";
        }
    }

    static abstract class Entity {
        private final String id;

        protected Entity(String id) {
            this.id = id;
        }

        public String id() {
            return id;
        }
    }

    static final class Product extends Entity
            implements Identifiable, Named, Auditable {
        private final String name;

        Product(String id, String name) {
            super(id);
            this.name = name;
        }

        @Override
        public String name() {
            return name;
        }
    }

    public static void main(String[] args) {
        Product product = new Product("P-07", "book");

        Identifiable byId = product;
        Named byName = product;
        Auditable byAudit = product;
        Entity byBase = product;

        System.out.println(byId.id());
        System.out.println(byName.label());
        System.out.println(byAudit.auditType());
        System.out.println(byBase.id());
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac Main.java
java Main
~~~

Exact output:

~~~text
P-07
item-book
tracked
P-07
~~~

Explanation:

1. Product extends **only one** superclass, Entity, and receives the id field along with the id() method through class inheritance; the private id field is only used directly inside Entity.
2. Product simultaneously implements **three** interfaces: Identifiable, Named, and Auditable.
3. The existing public id() method in Entity satisfies the Identifiable.id() contract because its signature and access level match; Product does not need to rewrite it.
4. Product implements Named.name() itself. The default method Named.label() invokes name() on the actual object, so it returns item-book.
5. Auditable.auditType() is inherited as a default method. The variables byId, byName, and byAudit only allow calling methods visible through their respective reference types, even though they all point to the same Product.
6. Entity is abstract but still has a constructor and a concrete method. Product is a concrete class that can be instantiated and fulfills all contracts.

**No cast is needed to assign** Product to each interface it implements. Conversely, to use a member belonging only to Product from an interface-typed variable, you must perform an appropriate type check/cast, such as using instanceof, and avoid assuming that every object implementing the same interface is a Product.

## 5. What Happens When Multiple Interfaces Have Matching Methods?

First, we need to distinguish three cases.

### 5.1. Same Abstract Method: Usually Only One Implementation Is Needed

~~~java
interface Printable {
    void render();
}

interface Previewable {
    void render();
}

class Report implements Printable, Previewable {
    @Override
    public void render() {
        System.out.println("report");
    }
}
~~~

A single public void render() method in Report satisfies both contracts simultaneously because the signatures are compatible. This is completely different from two default methods with competing bodies.

Note on **return types**: declarations with the same signature can only be combined if their return types are compatible according to Java's return-type-substitutability rules (for example, a covariant return type can satisfy multiple contracts). If two contracts require incompatible return types, a class cannot validly implement both merely by renaming variables or adding @Override.

### 5.2. Two Conflicting Default Methods: The Class Must Choose Explicitly

Create a standalone Main.java file for this example:

~~~java
public class Main {
    interface Left {
        default String source() {
            return "left";
        }
    }

    interface Right {
        default String source() {
            return "right";
        }
    }

    static class Combined implements Left, Right {
        @Override
        public String source() {
            return Left.super.source() + "+" + Right.super.source();
        }
    }

    public static void main(String[] args) {
        System.out.println(new Combined().source());
    }
}
~~~

Run:

~~~bash
javac Main.java
java Main
~~~

Output:

~~~text
left+right
~~~

If Combined.source() is omitted, the compiler reports a conflict because both Left and Right provide a default source() with the same signature. Combined **must override** it and define its own rule. The syntax Left.super.source() or Right.super.source() directly invokes the default method from the corresponding superinterface; you cannot arbitrarily use the name of an interface that is not in a valid superinterface relationship.

The class can also choose a simpler approach:

~~~java
@Override
public String source() {
    return "combined";
}
~~~

The snippet above is only an alternative override body placed inside Combined, not a standalone Java program.

### 5.3. Concrete Method from a Superclass Takes Precedence

Create a standalone Main.java file:

~~~java
public class Main {
    static class Parent {
        public String message() {
            return "class";
        }
    }

    interface Message {
        default String message() {
            return "interface";
        }
    }

    static class Child extends Parent implements Message {}

    public static void main(String[] args) {
        System.out.println(new Child().message());
    }
}
~~~

Running javac Main.java and java Main produces on stdout:

~~~text
class
~~~

This principle is commonly called **class wins**: a matching concrete instance method inherited from a superclass takes precedence over a default method with the same signature from an interface. The method in the class must still have a return type, access level, and overriding conditions compatible with the interface contract.

Do not apply this rule mechanically to an **abstract method** of a superclass: if the superclass declares an abstract method with the same signature, a concrete subclass must still provide an appropriate implementation; you cannot assume by default that the interface's default method automatically fulfills that requirement.

### 5.4. A Common Default Method Along Multiple Paths Does Not Necessarily Conflict

~~~java
interface Root {
    default String code() {
        return "root";
    }
}

interface A extends Root {}
interface B extends Root {}

class Both implements A, B {}
~~~

Both inherits the same default Root.code() through both branches and does not need to override it; these are not two independent competing implementations. When a subinterface redefines the method, the **more specific** declaration in the interface inheritance hierarchy is typically selected according to Java's rules. Therefore, you should examine the **origin and specificity of the method**, not just count the number of interfaces.

## 6. Commonly Confused Syntax and Access Rules

| Scenario | Valid? | Explanation |
| --- | --- | --- |
| class C extends A implements X, Y | Yes | One superclass, multiple interfaces; correct keyword order. |
| class C implements X, Y | Yes | The default direct superclass is Object. |
| interface Z extends X, Y | Yes | An interface can extend multiple interfaces. |
| class C extends A, B | No | Java does not support direct multiple class inheritance. |
| interface Z implements X | No | An interface uses extends to extend another interface. |
| class C implements X extends A | No | Invalid syntax; must use extends A implements X. |
| class C implements X but omits an abstract method | No, if C is a concrete class | Must implement it completely or declare C as abstract. |
| A class implements the same generic interface with two different type arguments | No | Conflict of inherited types due to the same generic interface and erasure. |

**Access level:** abstract methods declared in an interface are implicitly public. When a class implements them, write public; you cannot reduce the access level to package-private, protected, or private. The following example is invalid:

~~~java
interface Task {
    void execute();
}

class Job implements Task {
    // Invalid: this method is not public.
    // void execute() {}
}
~~~

Job here also lacks an actual implementation, so it will not compile. Fix it with public void execute() { ... } inside Job or make Job abstract if you want to defer implementation.

**Static methods in interfaces:** invoke them using the interface name; static methods are not inherited like instance methods of the implementing class.

~~~java
interface Numbers {
    static int twice(int n) {
        return n * 2;
    }
}

// Call: Numbers.twice(5)
~~~

**Fields in interfaces:** they are public static final constants and do not represent instance state; you cannot declare a mutable instance field in an interface. If multiple interfaces define constants with the same name, you should access them via the interface name to avoid ambiguity.

**Order and signature rules:** declaring implements in the order X, Y or Y, X is not a mechanism for prioritizing default methods. Java relies on inherited-method rules, interface specificity, and explicit overrides. Methods with the same name but different parameter lists are overloads and do not automatically cause a conflict due to sharing the same name.

## 7. When to Use an Abstract Class, Interface, or Composition?

Use an **abstract class** when multiple subclasses genuinely belong to the same family and need to share **state**, constructors, protected logic, or lifecycle invariants. Because only one superclass can be chosen, choose an “is-a” relationship with lasting meaning, and do not extend a class merely to inherit a utility method.

Use an **interface** to describe **independent capabilities or roles**: Comparable, AutoCloseable, Runnable, and custom contracts such as Printable and Retryable. An object can fulfill multiple roles without having to belong to multiple class hierarchies. Keep abstract contracts small with clear responsibilities; default methods should have safe, consistent default behavior and not rely on hidden instance state.

Use **composition** when you want to reuse an implementation but an “is-a” relationship does not hold or behavior needs to change flexibly. For example, class ReportService has a private final Formatter formatter field and delegates formatting to formatter, instead of extending Formatter just to reuse its processing code. Composition also avoids locking you into an unsuitable superclass.

A common design choice:

~~~text
Abstract class: share state/initialization across a family of objects
Interface:      expose multiple contracts/capabilities of the same object
Composition:    combine objects to reuse or replace behavior
~~~

All three can be combined: a class extends BaseEntity, implements Identifiable and Auditable, and holds a Validator passed in via its constructor.

## 8. Common Mistakes and How to Check

1. **Writing multiple classes after extends:** the compiler rejects it. Choose one superclass and replace the remaining roles with interfaces or composition.
2. **Forgetting public when implementing:** interface methods are public; raise the implementation's access level accordingly.
3. **Assuming implements automatically creates behavior:** abstract methods have no body; a concrete class must implement them. Only default methods come with an existing implementation.
4. **Relying on the implements order to resolve default conflicts:** order does not resolve conflicts. Override the method and decide explicitly.
5. **Confusing an interface with a stateful class:** interface fields are static final; use a class or collaborating object for per-instance data.
6. **Calling an interface static method on an instance:** call it using the interface name, such as Numbers.twice(5).
7. **Confusing the reference type with the actual type:** an interface-typed variable only exposes the interface's API at compile time; valid instance calls still dispatch to the implementation on the actual object.
8. **Inheriting from a class just to reuse a few methods:** makes the hierarchy meaningless and hard to change later; consider composition.

When encountering compilation errors related to inheritance, check in order: (a) extends/implements syntax; (b) the actual subtype relationship; (c) whether all abstract methods have matching public implementations; (d) whether methods with the same signature have compatible return types/throws clauses and access levels; (e) whether there are two default methods that cannot be automatically resolved.

## 9. Knowledge Self-Check

**Question 1.** How many direct superclasses does the class ElectricCar extends Car implements Chargeable, Trackable have? How many directly declared implemented interfaces does it have?

**Answer:** One direct superclass, Car, and two directly declared interfaces, Chargeable and Trackable. The object may also belong to other indirect superclasses and superinterfaces.

**Question 2.** Two interfaces have the same abstract void save(). How many save() methods does a class implementing both need if the signatures are compatible?

**Answer:** One public void save() implementation is enough.

**Question 3.** Two unrelated interfaces both have different default String status() methods. Is a concrete class implementing both without overriding valid?

**Answer:** No. The class must override status() to resolve the conflict. It can provide its own implementation or call the appropriate InterfaceName.super.status().

**Question 4.** A superclass has public String status(), an interface has default String status(), and a subclass extends the superclass and implements the interface. Which method is called?

**Answer:** The concrete instance method inherited from the superclass, provided the declarations are compatible.

## 10. Key Takeaways

- **Single class inheritance:** each class extends at most one direct class; the same applies to abstract classes.
- **Multiple interfaces:** a class can implement multiple interfaces; an interface can extend multiple interfaces.
- **Polymorphism:** the same object can be used through the multiple interface types it satisfies.
- **When methods overlap:** compatible abstract contracts can share a single implementation; two unresolvable default implementations must be overridden; a matching concrete method from a superclass takes precedence.
- **Design:** choose an abstract class for a family with shared state, an interface for roles, and composition when you need to assemble and swap behavior.

Understanding the boundary between **class inheritance**, **interface contract inheritance**, and **behavior delegation** will help you design Java APIs that are easy to understand, easy to extend, and less prone to method conflict errors.
