# Identifying `abstract` Classes and Restrictions on Direct Object Creation in Java

## 1. Core Conclusion: Abstract Classes Cannot Be Instantiated Directly

In Java, an **abstract class** is a class declared with the `abstract` keyword. It can describe **a common contract and shared behavior** for subclasses, while leaving operations that subclasses must complete.

Example:

```java
abstract class Animal {
    abstract String sound();
}
```

What is **invalid**:

```java
// Animal animal = new Animal();
// Invalid if uncommented: Animal is an abstract class,
// an instance cannot be created directly with new Animal().
```

What is **valid**:

```java
class Dog extends Animal {
    @Override
    String sound() {
        return "woof";
    }
}

Animal animal = new Dog(); // Valid code snippet when placed inside a method.
```

The `animal` variable has **static type `Animal`**, but the actual created object has runtime class `Dog`, a **concrete** class. Java allows this through **upcasting and polymorphism**.

**Distinction:**

- **Declaring an abstract class reference variable:** allowed.
- **Using an abstract class as a parameter/return/array element type:** allowed.
- **Creating an object directly with `new AbstractClass()`:** not allowed.
- **Creating an object with `new ConcreteSubclass()` and assigning it to an abstract-typed reference:** allowed.
- **Using an anonymous subclass with a complete implementation:** can be allowed, even though the syntax starts with `new AbstractClass() { ... }`; that is **not** directly creating an instance of the abstract class.

This lesson focuses on how to **identify abstract classes and restrictions on object instantiation**, without equating an abstract class with an interface, a utility class, or a class with only a private constructor.

## 2. Syntax for Declaring an `abstract class`

Template:

```java
abstract class BaseName {
    // Can have instance fields and static fields.
    // Can have constructors.
    // Can have abstract and concrete methods.
}
```

If declaring a public class at the top level:

```java
public abstract class Shape {
    public abstract double area();
}
```

then the source file must normally be named **`Shape.java`**. If you are only studying in a single demo file with one public main class, you can declare another abstract class as **package-private**, and create concrete subclasses in the same compilation unit.

The `abstract` keyword is a **class modifier**, not a standalone data type, and does not require a special constructor to activate it.

### Identification Clues from Source

1. The declaration includes `abstract class X` → X is an abstract class.
2. If a class contains a validly declared abstract method, the class itself **must** be declared abstract.
3. A class can be abstract **even if it declares no abstract methods**.
4. A class that does not write `abstract` but has not fully implemented the required abstract instance methods of its superclass/interface will **not compile**, rather than automatically becoming abstract.
5. `interface X` is an interface type, **not** an `abstract class`, even though some reflection/modifier rules of an interface have an abstract aspect.

**Do not infer from the name:** A class named `AbstractService` without the `abstract` modifier can still be a concrete class; conversely, a name `Device` can be completely abstract if the declaration says so.

## 3. Complete Java 17+ Example: Abstract Class, Concrete Subclass, and Polymorphism

Create **`AbstractBasicsDemo.java`**:

```java
abstract class Animal {
    private final String name;

    Animal(String name) {
        this.name = name;
        System.out.println("Animal constructor");
    }

    abstract String sound();

    String description() {
        return name + ":" + sound();
    }
}

final class Dog extends Animal {
    Dog(String name) {
        super(name);
        System.out.println("Dog constructor");
    }

    @Override
    String sound() {
        return "woof";
    }
}

public class AbstractBasicsDemo {
    public static void main(String[] args) {
        Animal animal = new Dog("Milo");

        System.out.println(animal.description());
        System.out.println(animal instanceof Animal);
        System.out.println(animal.getClass().getSimpleName());

        // Animal invalid = new Animal("Milo");
        // Invalid: cannot instantiate Animal directly.
    }
}
```

Compile and run:

```bash
javac AbstractBasicsDemo.java
java AbstractBasicsDemo
```

**Standard output:**

```text
Animal constructor
Dog constructor
Milo:woof
true
Dog
```

Explanation:

1. `Animal` is abstract because it has the `abstract` modifier and the `sound()` method has no body.
2. `Dog` is a concrete subclass, providing the `sound()` implementation with `@Override`.
3. `new Dog("Milo")` is allowed; the constructor chain runs `Animal(String)` and then `Dog(String)`.
4. `Animal animal = ...` is an upcast reference; it does not create a separate Animal instance.
5. `animal.description()` is a concrete method inherited from Animal. When `sound()` is called inside the method, Java dispatches to `Dog.sound()`.
6. `animal.getClass()` returns the runtime class Dog, not Animal.
7. If you uncomment the `new Animal("Milo")` line, the compiler reports an error because Animal is abstract.

**Key point:** An abstract class still has **constructors and instance state**, but it is only initialized as part of creating a concrete descendant object.

## 4. Why Does Java Forbid `new AbstractClass()`?

Suppose:

```java
abstract class Shape {
    abstract double area();
}
```

If Java allowed creating a `Shape` object directly, which implementation would execute when calling `area()`? The Shape class has no implementation for that method yet.

Java solves this with a **compile-time** constraint: it does not allow creating an instance of an abstract class directly, **even if that object is not intended to call the abstract method**.

Example:

```java
// Shape one = new Shape(); // Compile-time error.
```

The message from `javac` may be similar to “Shape is abstract; cannot be instantiated”; the specific wording depends on the compiler/version. That is not a runtime exception from the Shape constructor; the code **does not pass compilation**.

An important case: **Even an abstract class with no abstract methods cannot be directly instantiated with new**. The reason then is not necessarily “missing implementation”, but because the `abstract` modifier itself specifies that the class cannot be instantiated directly.

## 5. An Abstract Class May Have No Abstract Methods

Create **`AbstractWithoutAbstractMethodDemo.java`**:

```java
abstract class Ticket {
    private final String code;

    Ticket(String code) {
        this.code = code;
    }

    String code() {
        return code;
    }
}

final class VipTicket extends Ticket {
    VipTicket(String code) {
        super(code);
    }
}

public class AbstractWithoutAbstractMethodDemo {
    public static void main(String[] args) {
        Ticket ticket = new VipTicket("VIP-7");

        System.out.println(ticket.code());
        System.out.println(ticket instanceof Ticket);

        // Ticket invalid = new Ticket("X");
        // Invalid even though Ticket declares no abstract methods.
    }
}
```

```bash
javac AbstractWithoutAbstractMethodDemo.java
java AbstractWithoutAbstractMethodDemo
```

```text
VIP-7
true
```

Here:

- `Ticket` is marked abstract to express **that clients should not create a generic Ticket type**.
- `Ticket` only has the concrete method `code()`, which is completely valid.
- `VipTicket` is a concrete subclass; there are no outstanding abstract methods, so it does not have to override anything.
- `new VipTicket(...)` works, while `new Ticket(...)` is still forbidden.

**Accurate identification rule:** An abstract class **may** declare abstract methods; it is **not required** to have an abstract method.

## 6. What Is an Abstract Method?

An **abstract method** declares a method signature but **has no method body** in the declaring class. The familiar form:

```java
abstract class Calculator {
    abstract int compute(int a, int b);
}
```

The `;` character ends the declaration; there is no `{ ... }`.

Incorrect:

```java
// abstract class Calculator {
//     abstract int compute(int a, int b) {
//         return a + b;
//     }
// }
```

You cannot both declare `abstract` and write a body for **the same method**. If a shared implementation is needed, remove `abstract` from the method and provide a body.

### An Abstract Class Is Allowed to Have Both Abstract and Concrete Methods

```java
abstract class Document {
    abstract String content();

    String preview() {
        return "[" + content() + "]";
    }
}
```

`content()` is abstract and will be implemented by a concrete subclass. `preview()` is concrete and can call `content()` via dynamic dispatch on the runtime receiver.

**Why this is useful:** the parent class defines **the shared contract and workflow**, and subclasses only fill in the missing part instead of repeating the same logic across every document type.

## 7. A Concrete Subclass Must Complete Missing Abstract Methods

Create **`ConcreteImplementationDemo.java`**:

```java
abstract class Shape {
    abstract int area();

    String summary() {
        return "area=" + area();
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

public class ConcreteImplementationDemo {
    public static void main(String[] args) {
        Shape shape = new Rectangle(3, 4);

        System.out.println(shape.summary());
        System.out.println(shape.area());
    }
}
```

```bash
javac ConcreteImplementationDemo.java
java ConcreteImplementationDemo
```

```text
area=12
12
```

Explanation:

- `Shape.area()` has no implementation.
- `Rectangle.area()` provides an appropriate implementation and can use `@Override`.
- `Shape.summary()` is a concrete method in the parent class; it calls `area()` on the actual object.
- The `shape` variable has type Shape, but the `area()` method dispatches to Rectangle when the runtime receiver is Rectangle.

If you omit `Rectangle.area()` while keeping `Rectangle` concrete, the compiler will reject it because Rectangle has not implemented the required abstract method.

### No Need to Manually Write Overrides at Every Level

If an intermediate superclass has already implemented an abstract method and the subclass inherits that implementation, the concrete subclass is **not required to override it again**. The condition is that there are no remaining unimplemented abstract methods and all other method contracts are valid.

## 8. An Abstract Subclass Can Further Defer Implementation

A subclass can also be declared abstract so that **it does not yet need to complete all abstract methods at that level**.

Create **`AbstractHierarchyDemo.java`**:

```java
abstract class Device {
    abstract String kind();

    String description() {
        return "device:" + kind();
    }
}

abstract class MobileDevice extends Device {
    abstract int version();
}

final class Phone extends MobileDevice {
    @Override
    String kind() {
        return "phone";
    }

    @Override
    int version() {
        return 17;
    }
}

public class AbstractHierarchyDemo {
    public static void main(String[] args) {
        MobileDevice device = new Phone();

        System.out.println(device.description());
        System.out.println(device.version());
    }
}
```

```bash
javac AbstractHierarchyDemo.java
java AbstractHierarchyDemo
```

```text
device:phone
17
```

- `Device` declares abstract `kind()`.
- `MobileDevice` remains abstract, so it can leave `kind()` unimplemented while adding abstract `version()`.
- `Phone` is concrete, so it must fulfill both missing methods.
- Callers can still use `MobileDevice` as the **reference type**, while the created object is Phone.

**Common misconception:** “A subclass must immediately override every abstract method of its parent.” More accurately: a **concrete subclass** must have appropriate implementations; an **abstract subclass** can defer that.

## 9. `@Override` Does Not Replace the `abstract` Keyword

`@Override` is an annotation that helps the compiler verify that a method actually overrides or implements a compatible method from a superclass/interface.

```java
abstract class Base {
    abstract String name();
}

class Derived extends Base {
    @Override
    String name() {
        return "derived";
    }
}
```

If you mistype `names()` as another name, `@Override` helps detect the error early. Without `@Override`, overriding can still be valid, though it should be used when appropriate.

What is important:

- `abstract` on a method: **no body yet**, and subclasses must provide an implementation according to the rules.
- `@Override` on a concrete method: **is implementing/overriding** the corresponding contract.
- `@Override` does not by itself make a class abstract.
- You cannot turn an abstract method into a concrete one just by adding an annotation without writing a method body.

### Access Levels When Overriding

A subclass must not **narrow the access** of an inherited method in a valid override. For example, if a superclass method is `protected`, the overriding method cannot be `private`. A method from a public interface must normally be implemented with an appropriate **public instance method**.

Check the signature, return type, checked exceptions, and access according to Java's overriding rules; do not check only the method name.

## 10. An Abstract Class Still Has Constructors

“Cannot be instantiated directly” **does not mean** “an abstract class has no constructors”. An abstract class constructor is executed during the **initialization chain of a concrete subclass object**.

Create **`AbstractConstructorDemo.java`**:

```java
abstract class Account {
    private final String id;

    protected Account(String id) {
        this.id = id;
        System.out.println("Account constructor: " + id);
    }

    final String id() {
        return id;
    }

    abstract String type();
}

final class SavingsAccount extends Account {
    SavingsAccount(String id) {
        super(id);
        System.out.println("SavingsAccount constructor");
    }

    @Override
    String type() {
        return "savings";
    }
}

public class AbstractConstructorDemo {
    public static void main(String[] args) {
        Account account = new SavingsAccount("A-1");

        System.out.println(account.id());
        System.out.println(account.type());
    }
}
```

```bash
javac AbstractConstructorDemo.java
java AbstractConstructorDemo
```

```text
Account constructor: A-1
SavingsAccount constructor
A-1
savings
```

The `Account(String)` constructor runs **before** the body of the `SavingsAccount(String)` constructor, yet there is no valid `new Account("A-1")` expression to create an Account directly.

**Explanation:** A constructor declared in an abstract class is part of constructing a subclass instance. It can validate input, initialize instance fields, and perform common initialization, but that does not mean the abstract class becomes concrete.

### No Automatic No-Argument Constructor If Another Constructor Is Declared

If the base class only declares `Account(String)`, a subclass constructor must call `super(id)` or forward to a valid constructor. Writing a subclass constructor without a first invocation in Java 17 leads to an **implicit `super()`**; if the superclass has no accessible no-arg constructor, compilation fails.

## 11. An Abstract Class Constructor Can Accept Arguments and Check Invariants

An abstract superclass often holds shared data:

```java
abstract class Employee {
    private final String name;

    protected Employee(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name required");
        }
        this.name = name;
    }

    public final String name() {
        return name;
    }

    public abstract int salary();
}
```

This is a **valid class declaration**, without `main`. It illustrates:

- `protected` constructor: appropriate subclasses can call `super(name)`.
- `private final` field: the object holds the name after validation.
- `final` concrete method `name()`: subclasses cannot override it.
- `abstract` method `salary()`: a concrete descendant must provide an implementation according to the rules.

**Where to place the contract:** If every Employee must have a valid name, validating in the superclass constructor helps avoid subclasses forgetting to check it. However, this applies only when the superclass constructor can be invoked validly and does not cause uncontrolled side effects.

## 12. Abstract Methods Can Be Called from a Parent Class Concrete Method

An abstract class can define a complete portion of an algorithm, and then use an abstract method to obtain the “implementation step” from a subclass.

Create **`TemplateMethodDemo.java`**:

```java
abstract class ReportGenerator {
    final void generate() {
        System.out.println("prepare");
        String body = createBody();
        System.out.println("report=" + body);
        System.out.println("finish");
    }

    protected abstract String createBody();
}

final class SalesReport extends ReportGenerator {
    @Override
    protected String createBody() {
        return "sales:100";
    }
}

public class TemplateMethodDemo {
    public static void main(String[] args) {
        ReportGenerator generator = new SalesReport();
        generator.generate();
    }
}
```

```bash
javac TemplateMethodDemo.java
java TemplateMethodDemo
```

```text
prepare
report=sales:100
finish
```

This is the **Template Method** idea:

- `ReportGenerator.generate()` is a concrete `final` method that maintains the workflow.
- `createBody()` is an abstract hook.
- `SalesReport` implements the hook as needed.
- Callers see a stable `generate` API, while the runtime behavior of `createBody` depends on the concrete subclass.

**Distinction:** Template Method uses inheritance/overriding. If you want to swap strategies via an object passed in, you can use composition/delegation and Strategy; not every situation needs an abstract class.

## 13. Warning: Calling an Overridable Abstract Method from a Parent Class Constructor

An abstract class can call an abstract method inside a concrete method. However, **calling an abstract/overridable method in a superclass constructor** easily exposes subclass state that has not yet been fully initialized.

Create **`AbstractConstructorDispatchDemo.java`**:

```java
abstract class Parent {
    Parent() {
        printState();
    }

    abstract void printState();
}

final class Child extends Parent {
    private int number = 42;

    @Override
    void printState() {
        System.out.println("number=" + number);
    }
}

public class AbstractConstructorDispatchDemo {
    public static void main(String[] args) {
        Child child = new Child();
        child.printState();
    }
}
```

```bash
javac AbstractConstructorDispatchDemo.java
java AbstractConstructorDispatchDemo
```

```text
number=0
number=42
```

**Why is it 0 the first time?**

1. The object is allocated with the default value `0` for `number`.
2. The constructor chain enters `Parent()` before the Child instance field initializer runs.
3. Parent calls `printState()`, which dynamically dispatches to `Child.printState()`.
4. The Child initializer `number=42` has not run yet, so it prints `number=0`.
5. After the Parent constructor returns, the Child initializer runs and assigns 42.
6. The call after object creation finishes prints `number=42`.

**Recommendation:** Avoid calling overridable methods from constructors, especially abstract hooks that require subclass state. Finish object construction before performing behavior that can dispatch to a subclass. Do not let `this` escape early via callbacks, registries, or threads.

## 14. Abstract Modifiers Cannot Be Combined Arbitrarily

Some combinations are **invalid** due to the contradiction between “must be completed by a subclass” and “cannot be overridden/inherited in that way”.

| Declaration | Valid? | Why |
| --- | --- | --- |
| `abstract class Base { }` | Yes | An abstract class is not required to have abstract methods |
| `final class Base { }` | Yes | A concrete class that does not allow subclassing |
| `abstract final class Base { }` | **No** | An abstract class needs to allow subclasses to provide implementations; final forbids subclassing |
| `abstract void work();` in an abstract class | Yes | Declares an abstract instance method |
| `private abstract void work();` | **No** | A private method cannot be overridden according to the required inheritance contract |
| `static abstract void work();` | **No** | Static methods are not overridden like abstract instance methods |
| `final abstract void work();` | **No** | A final method cannot be overridden |
| `synchronized abstract void work();` | **No** | An abstract method has no body to use a synchronized method implementation in that way |
| `native abstract void work();` | **No** | Forbidden combination of method modifiers |
| `abstract void work() { }` | **No** | An abstract method has no body |
| `abstract class Base { static int x() { return 1; } }` | Yes | An abstract class can still have concrete static methods |
| `abstract class Base { final int x() { return 1; } }` | Yes | An abstract class can still have concrete final methods |

The table uses **standalone declaration snippets**; the rows marked invalid are not code to copy into a runnable example.

**Do not understand “abstract class” to mean “every method in the class is abstract”.** The `abstract` modifier on a class determines that the class cannot be instantiated directly; each method can be concrete, abstract, static, or final according to its own conditions.

## 15. Static Methods and Fields in an Abstract Class Can Still Be Used

Not being allowed to do `new AbstractClass()` **does not forbid calling static methods** that are validly accessible from that class.

Create **`AbstractStaticDemo.java`**:

```java
abstract class MathOperation {
    static int add(int a, int b) {
        return Math.addExact(a, b);
    }

    abstract int apply(int a, int b);
}

final class Addition extends MathOperation {
    @Override
    int apply(int a, int b) {
        return MathOperation.add(a, b);
    }
}

public class AbstractStaticDemo {
    public static void main(String[] args) {
        System.out.println(MathOperation.add(2, 3));

        MathOperation operation = new Addition();
        System.out.println(operation.apply(4, 5));
    }
}
```

```bash
javac AbstractStaticDemo.java
java AbstractStaticDemo
```

```text
5
9
```

- `MathOperation.add` is static: called directly via the abstract class name, with no object needed.
- `MathOperation.apply` is abstract: requires a concrete implementation when called on an instance.
- `Addition` is concrete, overrides `apply`, and reuses the static helper.
- No `MathOperation` object is created directly.

**A static method is not an instance abstract method.** Do not write `static abstract` expecting subclasses to override it dynamically; if you need runtime polymorphism, use an instance abstract method.

## 16. An Abstract Class Can Have `private` Helpers, but Not `private abstract` Methods

An abstract class is allowed to have **private concrete methods** for internal use:

```java
abstract class Pipeline {
    final String process(String input) {
        return normalize(input) + ":" + transform(input);
    }

    private String normalize(String input) {
        return input.trim();
    }

    protected abstract String transform(String input);
}
```

`normalize` is a private concrete instance method with a valid body. `transform` is a protected abstract instance method for subclasses to implement.

**Why is `private abstract` meaningless in the language?** An abstract instance method establishes an obligation to be overridden/implemented; a private method is not inherited/overridden through the required mechanism. The compiler does not allow that combination.

**Note:** Do not put a `private` helper in a superclass and expect a subclass to “override” it; a method with the same name/signature in a subclass does not override the private superclass method.

## 17. How Does an Abstract Class Differ from an Interface?

Both allow declaring contracts and using reference types to achieve polymorphism, but they differ in structure and declaration capabilities.

| Criterion | Abstract class | Interface |
| --- | --- | --- |
| Syntax | `abstract class Base` | `interface Contract` |
| Superclass | At most one direct class, defaulting to Object if it is an ordinary class | No class superclass chain like a class |
| Multiple direct supertypes | Only one superclass class; can implement multiple interfaces | Can extend multiple interfaces |
| Instance fields | Yes, including mutable state | Interface fields are `public static final` |
| Constructors | Yes, called through subclass construction | No instance constructors |
| Abstract instance methods | Can be declared | Interfaces typically declare abstract methods (with default/static/private methods per rules) |
| Concrete instance methods | Yes | Has `default` methods with their own rules |
| Static methods | Yes | Yes, static interface methods are not inherited the way class static members are |
| Direct instantiation | Forbidden when abstract | Cannot do `new Interface()` directly |
| Anonymous implementation | Can do `new AbstractBase() { ... }` if valid | Can do `new Interface() { ... }` |
| When is it commonly used? | Shared state/implementation and is-a relationships | Capability contracts across multiple unrelated types |

**Warning:** Do not say “an interface is an abstract class without fields”. Interfaces have their own language rules, and modern Java allows default/static/private interface methods under specific conditions.

You also cannot write `extends A, B` just because you want to inherit from two abstract classes. Java only allows one direct class superclass; you can use multiple interfaces or composition.

## 18. Example: An Abstract Class Implementing an Interface While Leaving Work to Subclasses

Create **`AbstractImplementsInterfaceDemo.java`**:

```java
interface Printable {
    void print();
}

abstract class BaseReport implements Printable {
    private final String title;

    BaseReport(String title) {
        this.title = title;
    }

    String title() {
        return title;
    }

    // BaseReport has not implemented print(), but it is still valid
    // because the class itself is declared abstract.
}

final class Report extends BaseReport {
    Report(String title) {
        super(title);
    }

    @Override
    public void print() {
        System.out.println("Report:" + title());
    }
}

public class AbstractImplementsInterfaceDemo {
    public static void main(String[] args) {
        Printable printable = new Report("Q3");
        printable.print();
    }
}
```

```bash
javac AbstractImplementsInterfaceDemo.java
java AbstractImplementsInterfaceDemo
```

```text
Report:Q3
```

Explanation:

- `BaseReport implements Printable` yet remains abstract, so it **is allowed not to implement `print()` yet**.
- `Report` is concrete, so it must provide `public void print()`; a method implementing a public interface method cannot reduce access privileges.
- Callers use a `Printable` interface reference to invoke the appropriate implementation.
- The created object is Report, not a direct BaseReport or Printable instance.

**Common mistake:** Removing `abstract` from BaseReport while still not implementing `Printable.print()`. In that case, the compiler reports that BaseReport must either be declared abstract or implement the required method.

## 19. Anonymous Subclass: The `new AbstractBase() { ... }` Syntax Is Still Valid

A point that very easily causes misconceptions:

```java
abstract class Operation {
    abstract int apply(int a, int b);
}
```

**Not allowed**:

```java
// Operation x = new Operation();
```

**But you can**:

```java
Operation sum = new Operation() {
    @Override
    int apply(int a, int b) {
        return a + b;
    }
};
```

In the second example, the expression **declares and instantiates a concrete anonymous subclass** of Operation, with an implementation of `apply`. It does not directly instantiate Operation.

### Runnable Example

File **`AnonymousAbstractDemo.java`**:

```java
abstract class Operation {
    abstract int apply(int left, int right);
}

public class AnonymousAbstractDemo {
    public static void main(String[] args) {
        Operation sum = new Operation() {
            @Override
            int apply(int left, int right) {
                return left + right;
            }
        };

        System.out.println(sum.apply(4, 5));
        System.out.println(sum.getClass().isAnonymousClass());
        System.out.println(
                sum.getClass().getSuperclass().getSimpleName());
    }
}
```

```bash
javac AnonymousAbstractDemo.java
java AnonymousAbstractDemo
```

```text
9
true
Operation
```

- `sum` is a variable of type Operation.
- The object's runtime class is an **anonymous subclass** generated by the compiler.
- `isAnonymousClass()` indicates that the runtime class is an anonymous class.
- The direct superclass of the anonymous class is Operation according to the structure in the example.

**Limitations:** An anonymous class must still satisfy abstract methods, constructor/access requirements, and inheritance rules. It is not a “loophole” for creating an abstract instance. If it does not implement all abstract methods of the parent class, compilation fails.

## 20. Abstract-Typed References, Parameters, and Return Types Are All Allowed

An abstract class can be used as a **type** in Java even though it has no direct instances.

Example:

```java
abstract class Shape {
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
```

You can use:

```java
Shape shape = new Square(3);
```

or:

```java
static int printArea(Shape shape) {
    return shape.area();
}
```

and a method returning an abstract-typed reference:

```java
static Shape unitSquare() {
    return new Square(1);
}
```

These snippets are **illustrative code fragments**, assuming they are declared inside a valid class/method. The `Shape` parameter and return type do not require creating a Shape object; they describe a **supertype contract**.

**General rule:** An abstract type can certainly appear at an API boundary to allow callers to supply any suitable concrete subtype.

## 21. Using a Static Factory in an Abstract Class to Return a Concrete Object

An abstract class can have a static factory method that creates an object of a concrete subtype:

File **`AbstractFactoryDemo.java`**:

```java
abstract class Message {
    private final String text;

    protected Message(String text) {
        this.text = text;
    }

    final String text() {
        return text;
    }

    abstract String render();

    static Message plain(String text) {
        return new PlainMessage(text);
    }
}

final class PlainMessage extends Message {
    PlainMessage(String text) {
        super(text);
    }

    @Override
    String render() {
        return text();
    }
}

public class AbstractFactoryDemo {
    public static void main(String[] args) {
        Message message = Message.plain("Hello");

        System.out.println(message.render());
        System.out.println(message.getClass().getSimpleName());
    }
}
```

```bash
javac AbstractFactoryDemo.java
java AbstractFactoryDemo
```

```text
Hello
PlainMessage
```

- `Message.plain` is a static method declared on the abstract class; it is called using the **class name**, without needing a Message instance.
- The method returns a `Message` reference, while the created object is a concrete `PlainMessage`.
- The `Message` constructor still runs as part of PlainMessage's constructor chain.
- A static factory can hide the concrete implementation from many callers, even though the example places all classes in the same package.

**Do not confuse:** Having a static factory that returns `Message` does not make the abstract class allow `new Message()`.

## 22. Arrays Whose Component Type Is an Abstract Class Are Still Valid

A Java array is a **separate object** containing reference slots. You can create an array with an abstract class component type without **creating abstract elements**.

File **`AbstractArrayDemo.java`**:

```java
abstract class Shape {
    abstract int area();
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

public class AbstractArrayDemo {
    public static void main(String[] args) {
        Shape[] shapes = new Shape[2];

        System.out.println(shapes[0] == null);

        shapes[0] = new Rectangle(3, 4);
        shapes[1] = new Rectangle(5, 2);

        for (Shape shape : shapes) {
            System.out.println(shape.area());
        }
    }
}
```

```bash
javac AbstractArrayDemo.java
java AbstractArrayDemo
```

```text
true
12
10
```

Why is `new Shape[2]` allowed while `new Shape()` is forbidden?

- `new Shape[2]` creates an **array object**, without creating any Shape instances.
- Both slots are initially null.
- Later, the slots are assigned references to **Rectangle objects**.
- Each `shape.area()` in the enhanced for loop calls the implementation of the runtime concrete subtype.

**Do not** infer from the `new Shape[2]` syntax that Java has created two abstract Shape objects.

## 23. `null` Can Be Assigned to an Abstract-Class-Typed Variable

A variable whose type is an abstract class is still a **reference-type variable** and can hold `null`:

```java
Shape shape = null;
```

That is valid regardless of whether Shape is abstract or concrete.

However:

```java
// shape.area(); // Throws NullPointerException at runtime if shape is null.
```

There is no receiver object on which to call the instance method. This is a **null dereference** issue, not an “abstract object creation” error.

If the design does not accept null, validate with `Objects.requireNonNull(shape)` or an appropriate contract. The `abstract` modifier does not automatically make every reference non-null.

## 24. A `Class` Object and Reflection Can Represent an Abstract Class

You cannot do `new AbstractClass()`, yet you can still do:

```java
Class<Shape> type = Shape.class;
```

That is a **Class object describing the Shape type**, not an instance of Shape.

Java Reflection allows inspecting modifiers:

File **`AbstractReflectionDemo.java`**:

```java
import java.lang.reflect.Modifier;

abstract class Base {
    abstract void perform();
}

final class Concrete extends Base {
    @Override
    void perform() {
    }
}

interface RunnableTask {
    void run();
}

public class AbstractReflectionDemo {
    public static void main(String[] args) {
        System.out.println(
                Modifier.isAbstract(Base.class.getModifiers()));
        System.out.println(
                Modifier.isAbstract(Concrete.class.getModifiers()));
        System.out.println(Base.class.isInterface());
        System.out.println(RunnableTask.class.isInterface());
        System.out.println(
                Modifier.isAbstract(RunnableTask.class.getModifiers()));
    }
}
```

```bash
javac AbstractReflectionDemo.java
java AbstractReflectionDemo
```

```text
true
false
false
true
true
```

**Important point:** `Modifier.isAbstract(...)` can return true for an **interface** because of how modifier flags are represented in reflection. Therefore, to classify an “abstract **class**”, you must also check the **not-an-interface** property such as `!type.isInterface()` or an appropriate type-kind API, rather than looking only at the abstract flag.

A `Class<?>`/`Class<T>` object exists to describe a type; retrieving metadata does not by itself create an instance of that type.

## 25. Reflection Cannot Instantiate an Abstract Class Directly Either

Do not think you can bypass the rule by looking up a `Constructor` via reflection and creating an abstract object like an ordinary concrete class.

Reflection APIs enforce the restrictions on abstract classes; an attempt to create an instance directly via `Constructor.newInstance` can fail with `InstantiationException` per its contract when the declaring class is abstract (alongside other access/exception issues).

Conceptual illustrative code:

```java
// Class<?> type = Shape.class;
// Object result = type.getDeclaredConstructor().newInstance();
// Not a valid strategy for creating an abstract Shape instance.
```

This snippet is not a runnable program; it also depends on which constructors Shape has and reflection access rights. **Do not state with certainty the exact first error type in every circumstance** if the constructor does not exist or is not accessible.

If you need to create a usable object, you must choose a **concrete subtype**, a factory, dependency injection, or a mechanism that produces an implementation fulfilling the contract.

## 26. An Abstract Class Differs from a Class That Only Has a `private` Constructor

A concrete class can **prevent external code from calling its constructor** because the constructor is private:

```java
final class Utility {
    private Utility() {
    }

    static int square(int value) {
        return value * value;
    }
}
```

`Utility` is **not abstract**; the barrier to `new Utility()` from another class comes from **constructor access privileges**, not the `abstract` modifier.

Comparison:

| Scenario | Why is `new X()` invalid from a caller? |
| --- | --- |
| `abstract class X`, with an accessible constructor | X is abstract: cannot be instantiated directly |
| `final class X { private X() {} }` | Constructor is not accessible from another caller |
| `class X { X(int a) {} }`, caller uses `new X()` | No matching no-argument constructor |
| `interface X`, caller uses `new X()` | Interfaces do not have direct instance construction |
| `enum X { A }`, caller uses `new X()` | Enum constants have construction controlled by the language |
| `record X(int a) {}`, caller uses `new X()` | No constructor with that signature unless appropriately declared |

**Do not lump every “cannot instantiate with new” message under abstract classes.** You must properly identify the modifier, type category, constructor signature, and access privileges.

## 27. Abstract Classes and Java's Single Inheritance

A concrete class can extend **one** abstract class; another abstract class also has at most one direct class superclass.

Example:

```java
abstract class Base {
    abstract void work();
}

abstract class Intermediate extends Base {
}

final class Concrete extends Intermediate {
    @Override
    void work() {
        System.out.println("done");
    }
}
```

Chain:

```text
Object
  |
  Base (abstract)
  |
  Intermediate (abstract)
  |
  Concrete (final, concrete)
```

`Concrete` does not directly extend both Base and Intermediate; it only has Intermediate as its direct superclass. Concrete inherits the **method obligation** from Base through Intermediate.

If you want a type to combine multiple behaviors, you can:

- `implements` multiple interfaces.
- Use composition/delegation for collaborator objects.
- Design a class hierarchy with a superclass that has a clear responsibility.

**You cannot** write `class C extends AbstractA, AbstractB` when both are classes. Being abstract creates no exception to the single class inheritance rule.

## 28. When Is an Abstract Class the Right Choice?

An abstract class is often useful if:

1. There is a **true is-a relationship** between the base type and concrete subtypes.
2. You need to share **instance state** or constructor validation.
3. There are multiple **concrete methods** you want to reuse.
4. You need to provide a **template algorithm** with abstract hooks.
5. You want to prevent clients from creating an overly general concept while still having valid concrete children.
6. You want to manage common invariants of the hierarchy.

Examples:

- `Shape` is abstract; `Rectangle` and `Circle` are concrete.
- `Account` is abstract and holds the shared ID, while concrete subclasses implement the business logic.
- `ReportGenerator` is abstract and holds the workflow, while subclasses provide the body.
- `InputStream` in the Java API is an abstract base class that provides common stream behavior, with concrete implementations.

### When Should You Consider an Interface Instead?

If you only need a **capability contract**, without needing common instance fields or constructors, an interface may be more flexible:

```java
interface Flyable {
    void fly();
}
```

A class can still extend its own parent class and implement Flyable along with other interfaces. Using an abstract class solely to enforce a method without shared implementation/state can unnecessarily occupy the single superclass slot.

### When Should You Consider Composition?

If A merely **uses** B to do work rather than being a kind of B, do not `extends B` just to reuse code. Use a component field and delegation:

```java
class Car {
    private final Engine engine = new Engine();

    void start() {
        engine.start();
    }
}

class Engine {
    void start() {
        System.out.println("engine started");
    }
}
```

These are valid class declarations, without `main`. Car has an Engine (*has-a*), and is not a subtype of Engine.

## 29. An Abstract Class Still Has Ordinary Members

An abstract class can contain:

- Instance fields (including `private final` or mutable fields).
- Static fields and constants.
- Constructors (which can be `protected`, package-private, public, or private in special designs).
- Concrete instance methods.
- Abstract instance methods.
- Static methods, private helpers.
- Static initialization blocks and instance initialization blocks.
- Nested classes or nested interfaces when valid.

Example:

```java
abstract class Storage {
    private final String name;
    private static int createdCount;

    protected Storage(String name) {
        this.name = name;
        createdCount++;
    }

    String name() {
        return name;
    }

    static int createdCount() {
        return createdCount;
    }

    abstract int size();
}
```

There is no `main` in the declaration snippet, but the code is valid. If concrete subclasses of Storage are created, the superclass constructors can increment the shared counter as written.

**Do not confuse:** `abstract` does not make every field `final` by default, does not make the class thread-safe, and does not turn static fields into instance fields. Those are independent design concerns.

## 30. The `sealed` Modifier Can Be Combined with an Abstract Class in Java 17

Java 17 supports `sealed` hierarchies, allowing you to restrict which direct subclasses are permitted to inherit.

Create **`SealedAbstractDemo.java`**:

```java
abstract sealed class Event permits LoginEvent, LogoutEvent {
    abstract String kind();
}

final class LoginEvent extends Event {
    @Override
    String kind() {
        return "LOGIN";
    }
}

final class LogoutEvent extends Event {
    @Override
    String kind() {
        return "LOGOUT";
    }
}

public class SealedAbstractDemo {
    public static void main(String[] args) {
        Event login = new LoginEvent();
        Event logout = new LogoutEvent();

        System.out.println(login.kind());
        System.out.println(logout.kind());
    }
}
```

```bash
javac SealedAbstractDemo.java
java SealedAbstractDemo
```

```text
LOGIN
LOGOUT
```

Explanation:

- `Event` is both `abstract` and `sealed`: it cannot be instantiated directly, and the list of direct subclasses is controlled.
- `LoginEvent` and `LogoutEvent` are in `permits` and are declared `final` appropriately.
- Both concrete classes override the abstract method `kind()`.
- `sealed` does not mean “you can instantiate an abstract class” and also does not mean “multiple inheritance of classes”.

**Distinguish combinations:** `abstract sealed class` can be valid; `abstract final class` is contradictory and forbidden.

## 31. Special Java Types That Should Not Be Confused with Ordinary Abstract Classes

### Interface

`interface Runnable { ... }` is an interface. You cannot do `new Runnable()` directly, but not because it is declared with `abstract class`.

### Enum

An `enum Status { NEW, DONE }` does not allow callers to use `new Status()`; enum instances are created according to enum constant rules. This is a special type and is not an “ordinary abstract class”.

### Record

A `record Point(int x, int y) {}` is a record class with its own constructor/component rules; records are not declared `abstract` and have `java.lang.Record` as their superclass. Records can normally be instantiated directly via an appropriate canonical constructor such as `new Point(1,2)`.

### Array

An `AbstractBase[] array = new AbstractBase[3]` is an **array object**, not three abstract instances. The array creation syntax is valid even when the component type is abstract.

### Primitive

`int` and `boolean` are not classes. They are neither abstract nor concrete subclasses of Object.

**Identification skill:** read the declaration kind (`class`, `interface`, `enum`, `record`) accurately before reasoning about abstract/constructors.

## 32. Common Compile-Time Errors and How to Fix Them

| Code / scenario | Why is it wrong? | How to fix |
| --- | --- | --- |
| `new AbstractBase()` | Base is abstract | Create a concrete subclass, use a factory, or use an anonymous concrete subclass |
| Concrete subclass does not implement missing abstract method | Contract not yet fulfilled | Override with a matching signature or declare the subclass abstract |
| Class declares an abstract method while the class is not abstract | Missing modifier on the class | Write `abstract class` or provide a body for the method |
| `abstract void run() { }` | An abstract method has no body | Remove the body or remove `abstract` |
| `abstract final class X` | Two conflicting class modifiers | Decide whether X is allowed to be subclassed |
| `private abstract void run();` | Private is incompatible with the override obligation | Use protected/package/public as appropriate |
| `static abstract void run();` | Static is not overridden like an instance method | Use an instance abstract method or a concrete static method |
| `final abstract void run();` | Final forbids overriding | Remove one modifier according to your intent |
| Overriding a method while reducing visibility | Violates override rules | Keep or widen the access |
| Implementing a public interface method with a package-private method | Implementation lacks public access | Declare it `public` |
| Using `new Base()` inside a base factory | Still instantiates the abstract class directly | Have the factory return a concrete subtype |
| Obtaining `Base.class` and thinking you have a Base instance | A Class object is metadata, not a Base instance | Instantiate a concrete subtype |
| Using `Modifier.isAbstract` alone to conclude it is an abstract class | Interfaces can carry the abstract flag | Check `!type.isInterface()`/category |
| Calling an abstract hook in a constructor | Subclass fields may not be initialized yet | Avoid virtual calls while constructing |
| Writing two `extends` classes | Java has single class inheritance | One superclass + interfaces/composition |
| Thinking an abstract class cannot have a constructor | Misunderstanding of direct instantiation | The constructor runs via the concrete subclass |
| Thinking an abstract class must have abstract methods | Incorrect | Use the abstract modifier to prevent direct instances when there is a reason |
| Using `new AbstractBase[5]` and thinking it creates five instances | Only creates an array of null slots | Create each concrete object if needed |

## 33. Comprehensive Practice: Predict and Explain the Output

Create **`AbstractTraceDemo.java`**:

```java
abstract class Worker {
    private final String name;

    Worker(String name) {
        this.name = name;
        System.out.println("Worker(" + name + ")");
    }

    final String name() {
        return name;
    }

    abstract int score();

    String summary() {
        return name() + ":" + score();
    }
}

abstract class SkilledWorker extends Worker {
    SkilledWorker(String name) {
        super(name);
        System.out.println("SkilledWorker()");
    }

    abstract String specialty();
}

final class Developer extends SkilledWorker {
    Developer(String name) {
        super(name);
        System.out.println("Developer()");
    }

    @Override
    int score() {
        return 95;
    }

    @Override
    String specialty() {
        return "Java";
    }
}

public class AbstractTraceDemo {
    public static void main(String[] args) {
        Worker worker = new Developer("An");

        System.out.println(worker.summary());
        System.out.println(worker.getClass().getSimpleName());

        if (worker instanceof SkilledWorker skilled) {
            System.out.println(skilled.specialty());
        }
    }
}
```

```bash
javac AbstractTraceDemo.java
java AbstractTraceDemo
```

**Output:**

```text
Worker(An)
SkilledWorker()
Developer()
An:95
Developer
Java
```

### Step-by-Step Solution

1. The expression `new Developer("An")` creates an object of the concrete class Developer.
2. The constructor chain runs `Worker(String)`, `SkilledWorker(String)`, and then `Developer(String)`; the two abstract parent classes **still have constructors** that execute.
3. The `worker` variable has static type Worker, while the reference points to a **Developer object**.
4. `worker.summary()` is a concrete method of Worker; when calling abstract `score()`, runtime dispatch invokes `Developer.score()`.
5. `getClass().getSimpleName()` returns the runtime class Developer.
6. The pattern `instanceof SkilledWorker skilled` succeeds because Developer extends SkilledWorker; it then calls the concrete implementation `Developer.specialty()`.

**No call creates an object using `new Worker()` or `new SkilledWorker()`**. The constructors of the two abstract classes are executed during the creation of an instance belonging to the concrete descendant Developer.

## 34. Practice Exercises with Solutions

**Exercise 1.** Write `abstract class Payment` with method `abstract int fee()` and concrete `String describe()`. Write concrete `CardPayment` returning a fee of 5. Is `Payment payment = new CardPayment()` allowed?

*Answer:* Yes. The object is CardPayment; the reference type is Payment. `new Payment()` directly is not allowed.

**Exercise 2.** Can `abstract class Base {}` be instantiated directly? Why?

*Answer:* No. The `abstract` modifier by itself forbids direct instantiation, even when the class has no abstract methods.

**Exercise 3.** Can an abstract class have a constructor with parameters?

*Answer:* Yes. A concrete subclass calls the appropriate superclass constructor via `super(args)`.

**Exercise 4.** Is `final class Child extends Base` with Base abstract valid?

*Answer:* Yes, if Child implements all missing abstract methods and inherits validly. Final on Child only forbids subclasses of Child.

**Exercise 5.** Is `abstract final class X` valid?

*Answer:* No. The two class modifiers contradict each other.

**Exercise 6.** If an abstract method is declared `protected abstract void work();`, can the subclass overriding method be `private`?

*Answer:* No. You cannot narrow visibility when overriding.

**Exercise 7.** Can an abstract class that implements an interface without implementing its methods compile?

*Answer:* It can, if the class remains abstract and declaration rules are satisfied. Concrete subclasses still must provide appropriate implementations.

**Exercise 8.** Is `new AbstractBase[10]` valid?

*Answer:* Yes. It only creates an array object with null slots, without creating AbstractBase instances.

**Exercise 9.** Does `new AbstractBase() { @Override ... }` create an instance of the abstract base directly?

*Answer:* No. It creates a concrete anonymous subclass (if all abstract methods are implemented).

**Exercise 10.** Is `AbstractBase.class` valid?

*Answer:* Yes. It is Class metadata and does not create an abstract instance.

**Exercise 11.** Can `Modifier.isAbstract(SomeInterface.class.getModifiers())` be true?

*Answer:* Yes. Also use `Class.isInterface()` when distinguishing an interface from an abstract class.

**Exercise 12.** In an abstract class, can `static int add(...)` be called via the class name without creating an instance?

*Answer:* Yes. A static method does not require an abstract class instance.

**Exercise 13.** A superclass constructor calls an abstract hook overridden in Child; have Child's field initializers run yet at that point?

*Answer:* Not yet under the normal constructor chain. The override may observe default values of Child's fields, so this pattern of calling should be avoided.

**Exercise 14.** Can `abstract` be used on a constructor?

*Answer:* No. Constructors are not abstract methods and cannot be declared abstract. They perform instance initialization along the constructor chain.

**Exercise 15.** Can `abstract class Service` hold mutable instance state?

*Answer:* Yes. Being abstract governs direct instantiation, not mutability by itself.

**Exercise 16.** Can two abstract classes A and B be direct superclasses of a class C?

*Answer:* No. Java still has single class inheritance; you can use interfaces or composition when the design requires multiple capabilities.

**Exercise 17.** Does a `final` concrete method in an abstract superclass need to be overridden in a subclass?

*Answer:* No, and it cannot be overridden either. The concrete method already has a shared implementation.

**Exercise 18.** If you want to provide only a contract for multiple unrelated classes, what should you use?

*Answer:* Consider an interface, because a class can implement multiple interfaces alongside an appropriate superclass.

## 35. Checklist When Reading and Writing Abstract Classes

- [ ] Did I look at the **`abstract` modifier on the class declaration**, rather than guessing from the name?
- [ ] Did I distinguish an abstract class from an interface, enum, record, and a concrete class with a private constructor?
- [ ] Do I know that `new AbstractBase()` directly is a compile-time error?
- [ ] Do I know that abstract-typed references, parameters, and return types are still valid?
- [ ] If using `new AbstractBase() { ... }`, do I understand that it is an anonymous subclass?
- [ ] Do concrete subclasses implement all missing abstract instance methods?
- [ ] Do overrides have the correct signature, access, checked exceptions, and `@Override` where appropriate?
- [ ] Did I avoid writing an abstract method with a body?
- [ ] Did I avoid combining abstract with private/static/final/synchronized/native in forbidden combinations?
- [ ] Did I avoid combining `abstract final` on a class?
- [ ] Do I understand that abstract classes have constructors and that they run through concrete subclass construction?
- [ ] If the superclass only has parameterized constructors, did the subclass make a valid `super(args)` call?
- [ ] Did I avoid calling overridable abstract hooks in constructors?
- [ ] Do I know an abstract class can have no abstract methods at all?
- [ ] Do I know an abstract class can contain concrete, final, static, private helpers and fields?
- [ ] Did I avoid confusing an abstract class with a “class with immutable state”?
- [ ] Do I know `Base.class`/`Class<?>` is not a Base instance?
- [ ] Do I know that a `Base[]` array does not create abstract elements?
- [ ] Do I use reflection flags alongside type-kind checks when identification is needed?
- [ ] Do I choose an abstract class when is-a/shared state/implementation is needed, and an interface when a capability contract is needed?
- [ ] Have I reviewed the public class file name, Java 17 syntax, `javac`/`java`, and stdout of the runnable examples?

---

**Final takeaway:** A class declared as **`abstract class` cannot be instantiated directly with `new AbstractClass()`**, regardless of whether it has abstract methods or not. However, it **remains a valid type** for reference variables, parameters, return types, arrays, static APIs, and class metadata. Actual objects are normally created via a **concrete subclass** or an **anonymous concrete subclass** that fully implements the abstract instance methods. An abstract class can contain fields, constructors, and concrete methods; its constructors still execute along the constructor chain when creating a subclass object. Clearly distinguish **direct instantiation restrictions** from **constructor access privileges**, interface semantics, and any mutability/concurrency concerns. That is the foundation for using inheritance and polymorphism safely in Java.
