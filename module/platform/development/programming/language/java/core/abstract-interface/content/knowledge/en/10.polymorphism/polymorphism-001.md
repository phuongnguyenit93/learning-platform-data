# Declaring Variables, Parameters, and Return Types with Abstract Types in Java

A key principle of **polymorphism** is that code using an object can work through an **abstract type** instead of needing to know the exact implementation class. In Java, an abstract type in this lesson is primarily an **interface** or **abstract class**. We can declare variables, method parameters, fields, and return types using those types, even though they themselves cannot be instantiated directly in the usual way.

Short example:

```java
interface Notifier {
    void send(String message);
}

class EmailNotifier implements Notifier {
    @Override
    public void send(String message) {
        System.out.println("Email: " + message);
    }
}
```

With the two declarations above, we can write:

```java
Notifier notifier = new EmailNotifier();
notifier.send("Hello");
```

The two snippets above are syntax examples; the second snippet must be placed inside a method or initializer block and is not yet a standalone program. The meaning is:

- **`Notifier`** is the *declared type* (declared/static type) of the variable `notifier`.
- **`EmailNotifier`** is the *actual class* of the object created by `new`.
- The `EmailNotifier` class implements the `Notifier` contract, so a reference of type `Notifier` can point to that object.
- The compiler checks the call `notifier.send(...)` against the methods declared by `Notifier`. At runtime, the appropriate implementation of `EmailNotifier` is executed.

The goal is not to “hide every class”, but rather to let the *consuming* code depend on a stable contract, while the object-creation part is allowed to choose a suitable implementation.

## 1. Distinguishing the Declared Type from the Actual Type

Consider the illustrative code snippet:

```java
Notifier channel = new EmailNotifier();
```

| Component | Meaning |
| --- | --- |
| `Notifier` | Declared type of the variable; determines the API that can be called directly at compile time. |
| `channel` | Reference variable; can be assigned `null` or a reference to a compatible object. |
| `new EmailNotifier()` | Creates an object of the concrete class `EmailNotifier`. |
| Runtime type of the object | `EmailNotifier`, even when the variable holding it has type `Notifier`. |
| `channel.send("Hi")` | Valid because `send` is declared in `Notifier`; the implementation is selected based on the runtime object. |

Assigning from a subtype to a supertype (`EmailNotifier` → `Notifier`) is **upcasting**. Java usually performs it automatically, without requiring an explicit cast. This relationship also applies to an abstract superclass:

```java
abstract class Animal {
    abstract String sound();
}

final class Dog extends Animal {
    @Override
    String sound() {
        return "woof";
    }
}

// Valid when placed inside a method:
Animal pet = new Dog();
```

An interface can have many implementing classes; an abstract class can also have many concrete subclasses. Polymorphism takes effect when the same call on a parent type is fulfilled by different child objects.

**Do not confuse this:** the declared type does not change the nature of the object. Assigning an `EmailNotifier` to a `Notifier` variable does not turn the object into an “interface object”, nor does it create a copy or remove methods from the object. Only **the operations allowed through the variable** depend on the declared type.

## 2. Using Abstract Types to Declare Variables and Fields

Instead of writing:

```java
EmailNotifier notifier = new EmailNotifier();
```

we can write:

```java
Notifier notifier = new EmailNotifier();
```

The second approach is useful when the subsequent code only needs `send`: the implementation can be switched to `SmsNotifier`, `PushNotifier`, or another class that implements `Notifier`. The compiler still guarantees that the assigned object conforms to the contract.

A field can also be declared using an interface:

```java
final class NotificationService {
    private final Notifier notifier;

    NotificationService(Notifier notifier) {
        this.notifier = java.util.Objects.requireNonNull(notifier);
    }

    void notifyUser(String message) {
        notifier.send(message);
    }
}
```

This is an illustrative class snippet; to run it, you need the `Notifier` declaration and an implementation as in the complete program in section 5.

- `private final Notifier notifier` indicates that the service **depends on the capability to send notifications**, not tied to a specific `EmailNotifier`.
- The constructor receives a `Notifier` reference from outside (**constructor injection**).
- `final` on a field means the reference cannot be reassigned after valid initialization; it does **not** mean the referenced object is immutable.
- Checking for `null` at the boundary helps prevent errors when the service calls `notifier.send(...)` later.

Using an abstract type for a field makes it easy to swap implementations in code, but it does not guarantee a good design if the interface has too many unrelated methods or callers still frequently cast back to a concrete class.

## 3. Using Abstract Types as Method Parameters

The signature:

```java
static void deliver(Notifier notifier, String message) {
    notifier.send(message);
}
```

allows passing **any object whose type is compatible with `Notifier`**, without forcing the caller to provide an exact `EmailNotifier`.

Example calls (within the same scope where `Notifier`, `EmailNotifier`, and `SmsNotifier` are declared):

```java
deliver(new EmailNotifier(), "Đơn hàng đã tạo");
deliver(new SmsNotifier(), "Đơn hàng đã tạo");
```

These two snippets illustrate a signature and calls, not standalone runnable files. Benefits:

1. **Decoupling the caller from the implementation:** the `deliver` method only performs one operation on the `Notifier` contract.
2. **Minimal impact when adding new classes:** a new class that `implements Notifier` can be passed in without modifying the method parameter.
3. **Easier behavior testing:** a fake/stub implementation can be passed in to record calls, as long as it satisfies the contract.
4. **Avoiding code duplication:** there is no need to create `deliver(EmailNotifier)` and `deliver(SmsNotifier)` versions just to call the same method.

**Limitations of the contract:** inside `deliver`, the compiler only guarantees the members of `Notifier` and any related superinterfaces. A method that exists only on `EmailNotifier` cannot naturally be called through the `Notifier` parameter.

If a method truly needs email-specific features, consider whether a more expressive interface is needed (such as `EmailSender`) or use a concrete parameter type; you should not declare a broad interface and then always cast to the implementation inside.

## 4. Using Abstract Types as Return Types

A method can commit to returning **`Notifier`** even though internally it chooses a concrete class:

```java
static Notifier chooseNotifier(boolean useEmail) {
    if (useEmail) {
        return new EmailNotifier();
    }
    return new SmsNotifier();
}
```

When calling `Notifier result = chooseNotifier(true);`, the caller only needs to know that the received object supports `send`. The channel selection logic remains encapsulated where the object is created.

Key points to remember:

- `return new EmailNotifier();` is valid if `EmailNotifier implements Notifier`.
- `return new SmsNotifier();` is also valid if `SmsNotifier implements Notifier`.
- If a method is declared to return `Notifier` but returns an incompatible object, the program will not compile.
- `return null;` may be syntactically valid for reference types, but it easily causes a `NullPointerException` for the caller; the contract must explicitly document this if you choose this approach.
- No interface object is automatically generated from the `return` statement; **an object still needs to be created** through a concrete class, a factory, or another data source.

Interface return types also appear commonly in Java Collections APIs, such as a method returning `List<String>` instead of forcing callers to depend on `ArrayList<String>`. `List` is an interface; `ArrayList` is an implementation. When returning a collection, additional decisions must be made about mutability and ownership; **the `List` type itself does not guarantee that the list is modifiable**.

### Covariant Return

When overriding a method in Java, the implementation can return a compatible subtype of the return type in the parent contract.

```java
interface Factory {
    Notifier create();
}

final class EmailFactory implements Factory {
    @Override
    public EmailNotifier create() {
        return new EmailNotifier();
    }
}
```

This snippet illustrates syntax; it assumes `Notifier` and `EmailNotifier` are already defined as above. `EmailNotifier` is a subtype of `Notifier`, so the return type on the overriding method is valid. When called through a `Factory factory` variable, the expression `factory.create()` still has the **static type `Notifier`**, even though the implementation returns an `EmailNotifier`.

You must not arbitrarily change parameter types when overriding: for example, `send(Object)` does not override `send(String)`. You need to distinguish **overriding** (same contract, runtime polymorphism) from **overloading** (multiple distinct signatures, selected by type at compile time).

## 5. Complete Java 17+ Program: Variables, Parameters, and Return Types

Save all of the following code to the file **`Main.java`**:

```java
import java.util.Objects;

interface Notifier {
    String channel();
    void send(String recipient, String message);
}

final class EmailNotifier implements Notifier {
    @Override
    public String channel() {
        return "Email";
    }

    @Override
    public void send(String recipient, String message) {
        System.out.println("Email to " + recipient + ": " + message);
    }
}

final class SmsNotifier implements Notifier {
    @Override
    public String channel() {
        return "SMS";
    }

    @Override
    public void send(String recipient, String message) {
        System.out.println("SMS to " + recipient + ": " + message);
    }
}

final class NotificationService {
    private final Notifier notifier;

    NotificationService(Notifier notifier) {
        this.notifier = Objects.requireNonNull(notifier);
    }

    void notifyUser(String recipient) {
        notifier.send(recipient, "Ready");
    }
}

public class Main {
    static void deliver(Notifier notifier, String recipient) {
        notifier.send(recipient, "Updated");
    }

    static Notifier chooseNotifier(String channel) {
        return switch (channel) {
            case "email" -> new EmailNotifier();
            case "sms" -> new SmsNotifier();
            default -> throw new IllegalArgumentException("Unknown channel");
        };
    }

    public static void main(String[] args) {
        Notifier primary = new EmailNotifier();
        Notifier secondary = new SmsNotifier();

        System.out.println(primary.channel());
        deliver(primary, "Lan");

        NotificationService service = new NotificationService(secondary);
        service.notifyUser("Minh");

        Notifier chosen = chooseNotifier("sms");
        System.out.println(chosen.channel());
        deliver(chosen, "An");
    }
}
```

Run with JDK 17 or later in the directory containing `Main.java`:

```bash
javac Main.java
java Main
```

**Expected output:**

```text
Email
Email to Lan: Updated
SMS to Minh: Ready
SMS
SMS to An: Updated
```

Read the program according to the three positions where abstract types are declared:

| Position | Code | Role |
| --- | --- | --- |
| Variable | `Notifier primary = new EmailNotifier();` | Holds an object of a concrete class through an interface. |
| Field | `private final Notifier notifier;` | The service does not need to know the specific channel. |
| Parameter | `deliver(Notifier notifier, ...)` | One method accepts multiple implementations. |
| Constructor parameter | `NotificationService(Notifier notifier)` | Provides the dependency when creating the service. |
| Return type | `static Notifier chooseNotifier(...)` | Allows selecting the implementation at runtime. |

The command `javac Main.java` compiles the top-level classes/interfaces in the same file; `java Main` runs the entry point `Main.main`. In `chooseNotifier`, `switch` is a **switch expression** supported in Java 17. Both branches `new EmailNotifier()` and `new SmsNotifier()` match the return type `Notifier`.

If a class `PushNotifier implements Notifier` is added, the signatures of `deliver` and `NotificationService` do not have to change. The selection logic inside the factory may need a new case added according to business requirements; that is the responsibility of the place that decides object creation.

## 6. Boundary Between Abstract Types and Polymorphism Mechanisms

When `Notifier notifier = new EmailNotifier();`, the compiler allows `notifier.send(...)` because `send` belongs to the `Notifier` contract; at runtime, the implementation of `EmailNotifier` executes. This is why variables, fields, parameters, and return types can use a stable abstraction instead of depending on one implementation class.

Other decisions have their own rules: overloads are selected based on static type; fields and `static` methods are not dispatched based on the runtime object; calling an instance method through `null` throws a `NullPointerException`. See the lessons **Dynamic Binding When Calling Instance Methods**, **Compile-Time Overload Selection and Runtime Override Selection**, **Null Objects and Calls Through Interface References**, and **Why Accessing Fields and Static Methods Is Not Polymorphic** to learn each mechanism.

## 7. Abstract Classes Can Also Be Used for Variables, Parameters, and Return Types

An abstract class provides a parent type that can include **state, constructors, concrete methods, and abstract methods**. You can still use it as a declared type, but you must instantiate objects from a **concrete subclass**.

Standalone file **`ShapeDemo.java`**:

```java
import java.util.Locale;

abstract class Shape {
    abstract double area();

    String label() {
        return "Shape";
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

    @Override
    String label() {
        return "Square";
    }
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

    @Override
    String label() {
        return "Circle";
    }
}

public class ShapeDemo {
    static Shape choose(boolean square) {
        return square ? new Square(2.0) : new Circle(1.0);
    }

    static void printShape(Shape shape) {
        System.out.printf(Locale.ROOT, "%s: %.2f%n",
                shape.label(), shape.area());
    }

    public static void main(String[] args) {
        Shape first = choose(true);
        Shape second = choose(false);
        printShape(first);
        printShape(second);
    }
}
```

```bash
javac ShapeDemo.java
java ShapeDemo
```

```text
Square: 4.00
Circle: 3.14
```

Here `Shape` appears as a **variable type**, **parameter** (`printShape`), and **return type** (`choose`). The two subclasses provide the implementation for `area()` and override `label()`. The `printShape` method works using the `Shape` API, so there is no need to write two separate versions for squares and circles.

Distinguishing between choosing an abstract class and an interface:

| Need | Interface | Abstract class |
| --- | --- | --- |
| Polymorphic variable/parameter/return declarations | Yes | Yes |
| Using `new` directly on the abstract type itself | No | No |
| One class having multiple such types at the same time | Can `implements` multiple interfaces | Can only `extends` one direct class |
| Sharing instance state and constructors | No instance fields or constructors | Can have them |
| Sharing default behavior | `default` methods when appropriate | Concrete instance methods |
| Typically suited for | Capability contracts, flexible APIs | A single family of types needing shared inherited mechanisms/state |

There is no rule that “abstract classes are always inferior to interfaces”. Choose the appropriate kind based on the contract and the actual inheritance characteristics of the problem.

## 8. Upcasting, Downcasting, and `instanceof`

Assigning an `EmailNotifier` to a `Notifier` is an upcast, usually implicit; the reference still points to the same object. When behavior specific to the concrete class is needed, a downcast must be compatible with the runtime type and can throw a `ClassCastException` if incorrect. `instanceof` (with pattern matching since Java 16) allows checking before using a subtype; with `null`, the check returns `false`. A cast does not create or convert an object.

The lessons **Upcasting and Downcasting Between Classes, Abstract Classes, and Interfaces**, **instanceof, Pattern Matching, and Checking Before Casting**, and **ClassCastException and Invalid Cast Limitations** present these cases in detail.

## 9. Abstract Types in Collections and Generics

Java generally encourages using interfaces as declared collection types:

```java
import java.util.ArrayList;
import java.util.List;

List<String> names = new ArrayList<>();
names.add("Lan");
names.add("Minh");
```

`List` is an interface, and `ArrayList` is an implementation class. Callers work through the methods declared by `List`; the implementation can be swapped as long as the contract and application requirements allow it.

You can also declare a collection holding objects of multiple implementations:

```java
List<Notifier> channels = new ArrayList<>();
channels.add(new EmailNotifier());
channels.add(new SmsNotifier());

for (Notifier channel : channels) {
    System.out.println(channel.channel());
}
```

The examples above are illustrative code snippets that must be placed in an appropriate scope with the `Notifier`, `EmailNotifier`, and `SmsNotifier` classes already declared; they are not yet standalone runnable programs.

**Important note on generic invariance:** even though `EmailNotifier` is a subtype of `Notifier`, **`List<EmailNotifier>` is not a subtype of `List<Notifier>`**. If a method only reads and calls the notifier API, consider a parameter like:

```java
static void showChannels(List<? extends Notifier> channels) {
    for (Notifier item : channels) {
        System.out.println(item.channel());
    }
}
```

`List<? extends Notifier>` accepts a list of `Notifier` or compatible subtypes. However, you cannot arbitrarily add a `new SmsNotifier()` to that list because the specific element type is not guaranteed. This is how generics preserve type safety; **polymorphism of elements does not automatically turn `List<T>` types into corresponding subtype relationships**.

## 10. Design Benefits and Conditions for Polymorphism to Be Truly Useful

When depending only on an interface, you can:

- **Swap implementations at the instantiation site:** the same service accepts an email or SMS channel.
- **Pass many different objects into one API:** the `deliver(Notifier, ...)` method does not need to know the subtype.
- **Return a unified contract:** a factory returns `Notifier` regardless of which class each branch creates.
- **Make testing easier:** provide a fake implementation that records parameters instead of sending real notifications.
- **Limit what the caller knows:** APIs specific to a concrete class are not introduced as implicit dependencies.

However, **an abstract type is still a real contract**. Two classes merely having the same method signatures do not automatically become subtypes of an interface without an appropriate type relationship (except for other mechanisms per language rules). An interface by itself also does not guarantee that implementations share the same business semantics. For example, if `send` promises “send once”, an implementation that sends repeatedly multiple times can violate expectations even though it still compiles. Polymorphic design requires compatibility in both **type** and **behavior** (the substitution principle).

You should not always declare every variable with the highest supertype such as `Object`. If `Object` is used, the compiler knows nothing about `send`; to call it, you would have to check and cast. Choose **the smallest abstract type that still provides all operations the caller actually needs**, while keeping the contract clear.

## 11. Common Mistakes

| Mistake or misconception | Why it is wrong / how to fix it |
| --- | --- |
| `Notifier n = new Notifier();` | Cannot instantiate an interface directly; use `new EmailNotifier()` or another implementation. |
| `Shape s = new Shape();` | An abstract class cannot be instantiated directly; use a concrete subclass. |
| `Notifier n = new EmailNotifier(); n.onlyEmailFeature();` | `onlyEmailFeature` is not in the declared type `Notifier`; only call the contract API or use a narrower type when truly needed. |
| `EmailNotifier n = chooseNotifier("email");` | The method declares a return type of `Notifier` and cannot be automatically assigned to a subclass variable; use `Notifier n` or check the type before casting. |
| Assuming an interface-typed variable always holds the same implementation | A variable can point to multiple subtypes sequentially; the runtime type of each object itself remains fixed. |
| Assuming `implements` automatically provides every method | A concrete class must fulfill any remaining abstract methods; a default method only provides an implementation when applicable. |
| Writing multiple overloads accepting each implementation just to call the same contract | These can be consolidated into one method accepting the appropriate interface. |
| Downcasting to an implementation class without checking | Can throw `ClassCastException`; use `instanceof` when needed or redesign the API. |
| Assigning `List<EmailNotifier>` to `List<Notifier>` | Generics are invariant; consider `List<? extends Notifier>` if you only need to read. |
| Assuming the `List` type guarantees the object allows adding/removing | The contract and implementation may not support modification; mutability requirements should be stated explicitly. |

## 12. Knowledge Self-Check

**1. Does `Notifier n = new EmailNotifier();` create an object of type `Notifier` or `EmailNotifier`?**  
It creates an `EmailNotifier` object. `Notifier` is the declared type of the reference and the contract visible to the caller.

**2. If `deliver(Notifier notifier)` only calls `notifier.send(...)`, is passing `SmsNotifier` valid?**  
Yes, as long as `SmsNotifier implements Notifier` and satisfies the required methods. That is polymorphism via parameters.

**3. Can a method declared as `Notifier create()` return a `new EmailNotifier()` object?**  
Yes, because `EmailNotifier` is a subtype of `Notifier`. The caller receives the static type `Notifier` when calling through that signature.

**4. Why is `new Shape()` invalid while `Shape x = new Square(2.0);` is valid?**  
`Shape` is an abstract class so it cannot be instantiated directly; `Square` is a concrete subclass and can be assigned to a `Shape` reference.

**5. Can a method that exists only in `EmailNotifier` be called through a variable declared with type `Notifier`?**  
Not directly. The compiler only allows access to members belonging to the `Notifier` API. You can check and downcast, but you should reconsider the design if that operation occurs frequently.

**6. Can `List<EmailNotifier>` be directly assigned to `List<Notifier>`?**  
No. Java generics are invariant. If you only need to read the objects from the `Notifier` perspective, a `List<? extends Notifier>` parameter may be suitable.

**7. When replacing `EmailNotifier` with `SmsNotifier` in the service, do you need to modify the constructor signature `NotificationService(Notifier notifier)`?**  
No. Both classes implement the same `Notifier` contract. The initialization code chooses the implementation, while the service calls the common API.

Remember the three core patterns: **variable `Notifier n`**, **parameter `void send(Notifier n)`**, **return type `Notifier create()`**. Each pattern allows working through an abstract contract, while the runtime object is supplied by a compatible concrete class; this is the foundation for using polymorphism in a controlled way in Java.
