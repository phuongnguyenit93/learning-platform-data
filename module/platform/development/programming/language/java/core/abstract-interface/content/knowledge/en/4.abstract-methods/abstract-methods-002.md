# Relationship Between an `abstract` Method and Its Enclosing Class in Java

An `abstract` method describes **a behavior that the supertype requires without providing an implementation body**. The relationship between this method and its enclosing type determines which type must be declared `abstract`, which type is allowed to instantiate objects, and which subclass is responsible for implementing the behavior.

## 1. Core Rules

For **regular classes (`class`) in Java**:

- If a class **directly declares at least one `abstract` method**, the class itself **must be declared `abstract`**.
- The converse is **not true**: an `abstract class` can certainly **have no `abstract` methods at all**. A designer can still use it to prevent direct instantiation or to serve as a base class for a hierarchy.
- A class without the `abstract` keyword (**concrete class**) must provide or inherit a valid implementation for **all remaining abstract methods** in its type hierarchy. If it has not met this requirement, that class must be an `abstract class`.
- Objects cannot be instantiated directly with `new` from an `abstract class`, even if that class has constructors and even if it has declared no abstract methods. However, the constructor of the abstract class is still called during the instantiation of a subclass object.
- `abstract` pertains to **methods that require implementation** and **classes that are incomplete for instantiation**, but the two concepts are not synonymous: an `abstract class` can contain methods with bodies, fields, constructors, and `static` and `final` methods.

In an `interface`, a method representing a contract without a body is typically **implicitly `public abstract`**. An interface is not declared with `abstract class`; it is a distinct kind of type. The case of an `enum` having an abstract method is a specialized exception, illustrated in Section 8.

## 2. Example of a Class with Both an Abstract Contract and Shared Logic

```java
abstract class DocumentJob {
    protected abstract String execute();

    public String report() {
        return "Result: " + execute();
    }
}
```

`DocumentJob` requires the `abstract` keyword because it directly declares `execute()` without a body. The `report()` method already has an implementation and is allowed to call `execute()`; when an object of a concrete subclass runs `report()`, the call to `execute()` uses the implementation corresponding to the actual class. This allows the base class to keep part of the common workflow and require subclasses to complete a missing step.

The fact that `execute()` has no body is a syntax rule of abstract methods, whereas the requirement that the enclosing class be abstract is a **class-level** rule. An `abstract class` that declares no abstract methods at all is still valid: it may simply hold constructors, shared data, or intentionally prevent direct instance creation. The syntax involving `;` and `interface` is covered separately in the introductory lesson of the chapter.

## 3. The Two Directions of the Relationship Are Not Equivalent

| Scenario | Valid? | Reason |
| --- | --- | --- |
| `abstract class A { abstract void run(); }` | Yes | The class is marked abstract to contain an abstract method. |
| `abstract class A { void run() {} }` | Yes | An abstract class is not required to declare any abstract methods. |
| `class A { abstract void run(); }` | No | A concrete class directly declares an abstract method. |
| `class A { void run() {} }` | Yes | The concrete class has a complete implementation. |
| `abstract final class A {}` | No | `abstract` requires allowing subclasses to implement it; `final` forbids inheritance. |
| `abstract class A { private abstract void run(); }` | No | `private` conflicts with the overriding contract of an abstract method. |

This table examines regular `class` declarations; `interface` and `enum` have their own syntax rules.

Further distinction:

- **Abstract method**: lacks a body at its declaration site, creating an implementation obligation in concrete subclasses.
- **Abstract class**: cannot yet be instantiated directly; it may contain or inherit implementation obligations, or simply serve as a base class.
- **Concrete class**: can be instantiated if a constructor is accessible and all abstract method contracts have been validly fulfilled.

Therefore, the statement "in an abstract class, all methods are abstract" is false; the statement "if there is an abstract method, the enclosing class is abstract" holds true for regular `class` declarations, while `interface` and `enum` must be considered separately.

## 4. Relationship with Subclasses: Inheritance, Implementation, and Instantiation

An abstract method in a superclass is **inherited as an obligation**. A subclass has two ways to handle it:

1. **The subclass remains abstract**: it is allowed not to implement the method yet. It can continue passing the obligation down to subsequent subclasses.
2. **The subclass is concrete**: it must implement the missing abstract method itself, or inherit a valid concrete implementation already present in the hierarchy.

When overriding, you should use `@Override` so the compiler checks the signature. The implementation must follow overriding rules: do not reduce the access level, use a compatible return type (including covariant return types if applicable), and do not broaden checked exceptions beyond the declaration of the overridden method.

Conceptual diagram:

```text
abstract class Ticket
  ├─ constructor, field, method with body header()
  └─ abstract int fee()
          ↓ inherits obligation
final class AdultTicket extends Ticket
  └─ @Override int fee() { ... }
          ↓
Can instantiate new AdultTicket(...)
Can assign to a Ticket reference to call fee() polymorphically
```

### Example 1: Abstract Superclass, Concrete Subclass

Save the entire following example in the file `AbstractMethodDemo.java`:

```java
abstract class Ticket {
    private final String holder;

    protected Ticket(String holder) {
        this.holder = holder;
    }

    public String header() {
        return "Ticket for " + holder;
    }

    public abstract int fee();
}

final class AdultTicket extends Ticket {
    AdultTicket(String holder) {
        super(holder);
    }

    @Override
    public int fee() {
        return 100;
    }
}

public class AbstractMethodDemo {
    public static void main(String[] args) {
        Ticket ticket = new AdultTicket("Lan");

        System.out.println(ticket.header());
        System.out.println("Fee: " + ticket.fee());
    }
}
```

Compile and run with Java 17+:

```bash
javac -encoding UTF-8 AbstractMethodDemo.java
java AbstractMethodDemo
```

Output:

```text
Ticket for Lan
Fee: 100
```

Points to observe:

- `Ticket` **cannot be instantiated directly**, because it is declared `abstract`.
- `Ticket` is still allowed to have the `holder` field, a constructor, and the concrete method `header()`.
- `AdultTicket` becomes a concrete class because it provides `fee()` according to the contract.
- The `ticket` variable has the reference type `Ticket`, while the actual object is `AdultTicket`; the call `ticket.fee()` runs the implementation in `AdultTicket` via **dynamic dispatch**.
- The `final` keyword on `AdultTicket` only prevents creating further subclasses; it is valid here because `AdultTicket` is not an abstract class.

### Example 2: Intermediate Subclass Remains Abstract

Save the entire example in `InheritanceDemo.java`:

```java
abstract class Device {
    public abstract String connect();
}

abstract class NetworkDevice extends Device {
    public String category() {
        return "Network device";
    }
    // connect() is not yet implemented: valid because the class is still abstract.
}

final class WifiDevice extends NetworkDevice {
    @Override
    public String connect() {
        return "Connected by WiFi";
    }
}

public class InheritanceDemo {
    public static void main(String[] args) {
        Device device = new WifiDevice();
        System.out.println(device.connect());
    }
}
```

```bash
javac -encoding UTF-8 InheritanceDemo.java
java InheritanceDemo
```

```text
Connected by WiFi
```

`NetworkDevice` does not need to repeat the line `abstract String connect();`. The implementation obligation is still inherited from `Device` and passed forward to `WifiDevice`. If you remove the `connect()` method from `WifiDevice` while keeping the class concrete, the program will not compile.

## 5. What If the Enclosing Class Does Not Directly Declare an Abstract Method?

The rule must account for **all unimplemented abstract methods**, including methods inherited from superclasses and from interfaces.

```java
interface Identifiable {
    String id();
}

abstract class BaseEntity implements Identifiable {
    // Does not redeclare id(); still carries the obligation from the interface.
}

final class UserEntity extends BaseEntity {
    @Override
    public String id() {
        return "U-001";
    }
}
```

The snippet above illustrates the type declarations (without `main`). `BaseEntity` must remain abstract because it has not implemented `id()`. `UserEntity` fulfills the obligation with a `public` method.

Conversely, if `BaseEntity` already provided a `public String id()` method with an appropriate body, `UserEntity` could inherit that implementation without needing to override it further.

A subclass **is not allowed to simply add the `abstract` keyword to a method while keeping the class itself concrete**. The obligation always accompanies the abstract status of an incomplete class.

## 6. Obligations Coming from Interfaces and Abstract Classes

It is not only abstract methods **declared directly** in a class that create an obligation. When an abstract class `implements` an interface without providing concrete methods, it is allowed to pass the obligation on to its subclasses. The `BaseEntity implements Identifiable` case in Section 5 illustrates this exact behavior.

| Aspect | `abstract class` | `interface` |
|---|---|---|
| Declaring abstract methods | Write `abstract`; can be `public`, `protected`, or package-private | Instance methods without a body default to `public abstract` |
| Role toward concrete classes | Must fulfill all remaining inherited abstract contracts | A class that `implements` it must fulfill all contracts lacking a suitable implementation |
| Shared members | Has constructors, instance state, and concrete methods | Has `default`/`static`/`private` methods per their own rules; no instance constructors |
| Direct inheritance limits | Can only `extends` one class | Can `implements` multiple interfaces |

**Important condition:** a method with the same name does not necessarily fulfill the obligation. You must verify the signature, return type, exceptions, and access scope, especially when the subclass resides in a different package. A validly inherited concrete method can satisfy the contract without needing to rewrite an override. Conversely, an interface's default method does not always win over a method inherited from a class; Java applies hierarchy-based conflict resolution rules. Subsequent lessons dive deeper into each exception.

## 7. Diagnosing a Concrete Class That Has Not Fulfilled Its Contract

When the compiler reports that a subclass has not implemented an abstract method, look for the **missing method**, rather than assuming the enclosing class is simply missing the `abstract` keyword.

| Symptom | Question to Check | How to Fix |
|---|---|---|
| Concrete class does not implement all methods | Is there an abstract method inherited from a class or interface? | Add a valid implementation or keep the subclass `abstract` |
| A method with the same name exists, yet it is still reported as missing | Does the parameter type list differ? | Use `@Override` to catch unintended overloads |
| An implementation exists, but the compiler reports weaker access privileges | Does the superclass or interface require `public`/`protected`? | Preserve or widen visibility according to overriding rules |
| A subclass in a different package cannot implement the hook | Is the hook in the superclass package-private? | Use `protected`/`public` if cross-package extension is needed, or complete the hook in the original package |
| Cannot instantiate the base class | Is the class itself still declared `abstract`? | Instantiate an object from a suitable concrete class |

Declaring `private abstract`, `static abstract`, `final abstract`, or giving an abstract method a `{ ... }` body are separate syntax/modifier errors. Detailed invalid examples and their fixes are covered in the dedicated lessons on syntax and modifiers; they do not change the obligation-inheritance rules here.

## 8. Subtle Details to Remember

### 8.1. An Abstract Class Is Not a "Class Without Constructors"

An abstract class can declare constructors to initialize shared state. The constructor runs when an object of a subclass is created; only a direct `new AbstractBase()` operation is invalid. A constructor cannot be declared `abstract`, because constructors are not overridden like instance methods.

Avoid directly calling overridable methods (especially abstract methods) from a superclass constructor: the call may dispatch to the subclass **before the subclass's own initialized fields are ready**, creating hard-to-detect state bugs.

### 8.2. An Abstract Class Can Redeclare an Implemented Method as Abstract

In an **abstract subclass**, a designer sometimes wants to force subsequent subclasses to re-decide the behavior even though the superclass already provides an implementation:

```java
class BaseNotifier {
    public void notifyUser() {
        System.out.println("Generic");
    }
}

abstract class CustomNotifier extends BaseNotifier {
    @Override
    public abstract void notifyUser();
}
```

This is a valid declaration: `CustomNotifier` turns `notifyUser()` into an abstract requirement for its concrete subclasses, provided overriding rules are followed. This code snippet illustrates the declaration and does not contain `main`.

### 8.3. Special Case: An Enum with an Abstract Method

An `enum` can declare an abstract instance method if **every enum constant provides an implementation** via its own constant-specific class body. You do not write `abstract enum`. Complete example in `EnumAbstractDemo.java`:

```java
enum Level {
    LOW {
        @Override
        int score() {
            return 1;
        }
    },
    HIGH {
        @Override
        int score() {
            return 10;
        }
    };

    abstract int score();
}

public class EnumAbstractDemo {
    public static void main(String[] args) {
        System.out.println(Level.HIGH.score());
    }
}
```

```bash
javac -encoding UTF-8 EnumAbstractDemo.java
java EnumAbstractDemo
```

```text
10
```

This is a special case in Java showing that the rule "whenever there is an abstract method, you must write `abstract class`" applies directly only to regular `class` declarations and should not be mechanically applied to interfaces or enums.

## 9. Should You Choose an Abstract Class or an Interface When Designing?

When you only need to specify **behaviors that multiple classes without a common ancestor can still perform**, an interface is usually the natural choice. When you need to **share state, constructors, and common logic** while leaving certain steps for subclasses to decide, an abstract class is more appropriate. A Java class can directly `extends` only one superclass, but can `implements` multiple interfaces.

Whichever option you choose, do not add an abstract method if no variant genuinely needs to provide its own implementation. An abstract contract creates an obligation for every concrete class in the relevant hierarchy, so it should be placed at the appropriate level and use clear names, return types, and parameters.

## 10. Self-Check

1. Is an `abstract class` required to declare at least one `abstract` method? **No.**
2. Can a normal `class` directly contain `abstract void go();`? **No; the class must be declared `abstract`, or the method must be changed to have a body.**
3. Can an `abstract` subclass defer implementing an inherited abstract method? **Yes.**
4. Can a concrete subclass simply inherit a valid implementation from another ancestor class without writing an override itself? **Yes, if the obligation has already been fully satisfied according to inheritance rules.**
5. What access level and characteristics does a bodyless method in an interface typically have? **Implicitly `public abstract`.**
6. Can `final` be combined with an `abstract` class declaration? **No.**
7. When a superclass variable of an abstract type calls an abstract method implemented by a subclass, which code runs? **The implementation corresponding to the actual object at runtime.**

**Remember:** For regular Java classes, *an abstract method forces its enclosing class to be marked abstract, but an abstract class does not have to contain any abstract methods*. During inheritance, the implementation obligation is passed forward until a concrete class provides or inherits a valid implementation.
