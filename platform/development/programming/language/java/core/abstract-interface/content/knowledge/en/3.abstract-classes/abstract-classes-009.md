# Concrete Subclasses and the Responsibility of Completing Implementations in Java

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain why a **concrete** subclass (concrete class) must provide complete implementations for the abstract methods that remain in the inheritance hierarchy.
- Distinguish between methods implemented by the subclass itself and concrete methods that it **inherits** from a superclass or receives through an interface `default` method.
- Recognize when a subclass must continue to be declared `abstract`, how to check `@Override` signatures, and common compilation errors.
- Design an abstract superclass to describe common parts, and then implement varying behavior in the appropriate subclasses.

**Context:** This is a lesson on Java's *abstract class* (`abstract class`). The focus is on the responsibility of completing the implementation when a subclass transitions from an abstract state to being instantiable.

## 2. What Is a Concrete Subclass?

A class not declared `abstract` is a **concrete class**. If that class inherits from an abstract class, the compiler accepts it only when every abstract method that the class must implement already has a valid concrete implementation.

Conceptual example:

~~~java
abstract class Vehicle {
    abstract void move();
}

class Bicycle extends Vehicle {
    @Override
    void move() {
        System.out.println("Pedaling");
    }
}
~~~

`Vehicle` specifies that every vehicle subclass must have `move()` behavior, but does not yet specify how to implement it. `Bicycle` completes that contract with a method that has a body; therefore, `new Bicycle()` is valid. Conversely, `new Vehicle()` is invalid because `Vehicle` is an abstract class.

This responsibility applies across **the entire inheritance chain and related interfaces**, not just the abstract methods declared directly in the nearest superclass.

### Core Conditions

A concrete subclass must:

1. Have a valid implementation for all unresolved abstract methods, including indirectly inherited contracts and abstract methods from interfaces.
2. Follow Java's overriding rules: name, parameter list, return type, access level, and checked exceptions (`checked exception`).
3. Be able to invoke an appropriate superclass constructor upon instantiation; `final` fields must be initialized according to the rules, just as in any Java class.

The third condition belongs to general object initialization rules, while the first two conditions are the essential part of completing an abstract contract.

## 3. Who Is Responsible for Implementation and When Can It Be Deferred?

An intermediate class is allowed to defer `abstract` method obligations as long as it is itself declared `abstract`. The first class that is no longer `abstract` must have valid implementations for all missing obligations across the entire hierarchy; if it is not ready yet, keep that class `abstract` instead of leaving a concrete class declaration that does not compile.

What needs to be checked is **the remaining obligations**, not the number of methods that the final class writes itself. A suitable implementation may already have been provided in an ancestor class or through an interface `default` method; the next section clearly illustrates the case of inheriting an existing implementation.

## 4. The Final Subclass Does Not Necessarily Write Every Method Itself

The contract only requires that a **valid concrete implementation already exists in the hierarchy**, not that the final subclass rewrites every method. For example:

~~~java
interface Printer {
    void print();
}

abstract class BasePrinter implements Printer {
    @Override
    public void print() {
        System.out.println("Printed");
    }
}

class OfficePrinter extends BasePrinter {
    // Inherits the existing print() implementation.
}
~~~

`OfficePrinter` is a valid concrete class even though it does not declare `print()`. `BasePrinter`'s `public void print()` implementation already satisfies the `Printer` interface. The fact that `BasePrinter` is still declared `abstract` does not make its `print()` implementation abstract.

Similarly, a suitable `default` method from an interface can provide default behavior. However, when there is a conflict between unrelated `default` methods, the implementing class must resolve the conflict according to Java's inheritance rules.

Therefore, when reading a missing-implementation error, trace back up the entire hierarchy to find **the unmet abstract method**, rather than merely counting the number of `@Override` methods in the final class.

## 5. Complete Example: Completing Implementations Across Multiple Inheritance Levels

Save the entire following snippet to the file `Main.java`:

~~~java
interface Exportable {
    String format();

    default String fileExtension() {
        return ".txt";
    }
}

abstract class Document implements Exportable {
    private final String title;

    protected Document(String title) {
        this.title = title;
    }

    public final String title() {
        return title;
    }

    public abstract String body();

    public String preview() {
        return title + " | " + body();
    }
}

abstract class TextDocument extends Document {
    protected TextDocument(String title) {
        super(title);
    }

    @Override
    public final String format() {
        return "text/plain";
    }
}

final class Note extends TextDocument {
    private final String content;

    Note(String title, String content) {
        super(title);
        this.content = content;
    }

    @Override
    public String body() {
        return content;
    }
}

public class Main {
    public static void main(String[] args) {
        Document doc = new Note("Week 1", "Review contracts");
        Exportable export = (Exportable) doc;

        System.out.println(doc.preview());
        System.out.println(export.format());
        System.out.println(export.fileExtension());
    }
}
~~~

Compile/run with JDK 17 or newer:

~~~bash
javac --release 17 Main.java
java Main
~~~

Expected output:

~~~text
Week 1 | Review contracts
text/plain
.txt
~~~

**Layer-by-layer analysis:**

1. `Exportable` declares the abstract method `format()` and provides the `default fileExtension()` method.
2. `Document` is an abstract class that does not yet implement `format()` from the interface; it also adds the `body()` contract. In addition, `title()` and `preview()` already have bodies; `preview()` calls `body()` via polymorphism.
3. `TextDocument` resolves `format()` with a `final` implementation, yet still has an abstract `body()`, so it remains an `abstract` class.
4. `Note` implements `body()`. It **inherits** `format()`, `preview()`, and `title()`, while using the default `fileExtension()`. Thus, all contracts are completed, allowing `new Note(...)` to be created.
5. The variable `doc` has the declared type `Document` but holds a `Note` object. Calling `doc.preview()` runs the code defined in `Document`, while the `body()` call inside it is dynamically dispatched to `Note`'s implementation.

`final class Note` only expresses the choice to prevent further inheritance; it is **not** a requirement for a class to become concrete. Writing `class Note extends TextDocument` is also valid. Conversely, `final` cannot be used on an `abstract` method because one forbids overriding while the other requires subclasses to provide an implementation.

### Why Does the Superclass Constructor Still Run?

`Document` is an abstract class, so it cannot be created directly via `new Document(...)`, yet it still has a `protected Document(String)` constructor to initialize the shared state. When running `new Note(...)`, the constructor call chain is `Note` → `TextDocument` → `Document`, and initialization completes in top-down order from the superclass downward. A concrete subclass must invoke an appropriate superclass constructor via `super(...)`, either explicitly or implicitly.

**Design note:** You should not call overridable methods from the constructor of an abstract superclass. The method may dispatch down to the subclass while the subclass's fields have not yet finished initializing.

## 6. Direct Example: Combining Contracts from an Abstract Class and an Interface

Save the following snippet to `Example2.java` (independent from `Main.java` above):

~~~java
interface Describable {
    String describe();
}

abstract class Shape implements Describable {
    public abstract double area();

    public String kind() {
        return "shape";
    }
}

final class Square extends Shape {
    private final double side;

    Square(double side) {
        this.side = side;
    }

    @Override
    public double area() {
        return side * side;
    }

    @Override
    public String describe() {
        return "square: " + area();
    }
}

public class Example2 {
    public static void main(String[] args) {
        Shape shape = new Square(3.0);
        System.out.println(shape.kind());
        System.out.println(shape.describe());
    }
}
~~~

~~~bash
javac --release 17 Example2.java
java Example2
~~~

~~~text
shape
square: 9.0
~~~

`Shape` does not yet implement `Describable.describe()` and also declares `area()` as abstract. Therefore, `Square` must satisfy **both** methods. `kind()` has a body in `Shape`, so it is inherited directly; no override is needed.

## 7. Overriding with the Right Signature to Fulfill the Contract

A method completes an abstract contract only when it actually **overrides** the inherited method. You need to check:

| Element | Overriding Requirement | Example/Meaning |
| --- | --- | --- |
| Name and parameters | Same matching signature (accounting for Java's signature equivalence rules) | `run()` differs from `run(int)`; the latter declaration is only an overload. |
| Return type | Same type or a valid covariant return type for reference types | If the superclass returns `Number`, the subclass can return `Integer`. |
| Access level | Must not narrow the access level of the overridden method | If the superclass is `public`, the subclass must be `public`. |
| Checked exception | Must not declare new or broader checked exceptions than permitted by the rules | If the superclass `throws IOException`, the subclass can omit `throws`. |
| `@Override` | Should be used so the compiler checks the intent to override | Wrong name/parameters will be caught immediately. |

Example of a covariant return type:

~~~java
abstract class Provider {
    public abstract Number number();
}

class IntProvider extends Provider {
    @Override
    public Integer number() {
        return 42;
    }
}
~~~

`Integer` is a subclass of `Number`, so `IntProvider.number()` satisfies the contract and `IntProvider` is a concrete class.

Conversely, the following **intentionally incorrect, non-compiling** snippet demonstrates an overloading mistake:

~~~java
abstract class Base {
    abstract String read();
}

class Wrong extends Base {
    String read(int index) {
        return "item " + index;
    }
}
~~~

`read(int)` is a different method from `read()`; it does not complete `Base`'s contract. The compiler will report an error stating that `Wrong` has not implemented the abstract method `read()`. The fix is to declare `@Override String read() { ... }` with the correct signature, or keep `Wrong` as an `abstract` class if you want to continue deferring the implementation.

Another mistake is using a weaker access level:

~~~java
abstract class PublicBase {
    public abstract void execute();
}

// INTENTIONALLY WRONG: does not compile.
class InvalidChild extends PublicBase {
    @Override
    protected void execute() {
        // ...
    }
}
~~~

The superclass `execute()` is `public`, whereas the subclass writes `protected`, violating the overriding rules. Fix this by changing it to `public void execute()`.

Note: `private`, `static`, or `final` methods cannot be declared `abstract`; placing a `static` method with the same name in a subclass also does not replace an abstract instance method.

## 8. Process for Verifying a Concrete Subclass

When defining `class X extends Y`, follow these steps in order:

1. **List the contracts:** Inspect the remaining abstract methods from `Y`, ancestor classes, and interfaces that X must satisfy.
2. **Check for inherited implementations:** Check whether a superclass already provides a valid concrete method or an interface already provides a suitable `default` method.
3. **Implement the missing parts:** Write the methods with the exact signature and overriding rules; use `@Override` on every method to be overridden.
4. **Decide between abstract or concrete:** If any contracts remain unimplemented, leave the class as `abstract`; if you want it to be instantiable, you must complete all of them.
5. **Compile and test behavior:** Verify constructors, calls through superclass/interface types, and actual output.

Summary table:

| Case | Valid Declaration? | Can Instantiate Directly with `new`? |
| --- | --- | --- |
| Abstract superclass still having methods without a body | Yes, if the class remains `abstract` | No |
| `abstract` subclass that has not implemented everything | Yes | No |
| Non-`abstract` subclass still missing implementations | No: compilation error | No |
| Concrete subclass implementing everything itself | Yes | Yes, if the constructor is accessible |
| Concrete subclass inheriting complete implementations from ancestors | Yes | Yes, if the constructor is accessible |

### Common Mistakes and How to Handle Them

- **Implementing only methods from the direct superclass:** Forgetting abstract methods from ancestors or interfaces. Check the entire `extends` and `implements` chain.
- **Confusing overloading with overriding:** Writing `calculate(int)` when the contract requires `calculate()`. Add `@Override` to catch signature mismatches.
- **Omitting `public` when implementing an interface method:** Regular abstract methods in an interface are `public`, so the implementation must also be `public`.
- **Assuming that inheriting from an `abstract` class forces the subclass to also be `abstract`:** False; the subclass can be concrete if all implementation obligations have been met.
- **Overriding a method that is already sufficient:** Unnecessary; you can use the inherited implementation directly. Override only when the behavior genuinely needs to differ and the method allows overriding.
- **Calling an overridden method in a superclass constructor:** May encounter subclass state that is not ready yet; prefer completing initialization before calling polymorphic behavior.

## 9. Self-Check

Consider the following code:

~~~java
interface Identified {
    String id();
}

abstract class Entity implements Identified {
    public abstract boolean valid();

    public String label() {
        return id();
    }
}

abstract class StoredEntity extends Entity {
    @Override
    public final boolean valid() {
        return true;
    }
}

class Order extends StoredEntity {
    @Override
    public String id() {
        return "ORD-1";
    }
}
~~~

**Questions:**

1. Which method has `StoredEntity` completed? Why can it still be declared `abstract`?
2. Which methods must `Order` implement to be a concrete class?
3. What does `new Order().label()` return?
4. Can `valid()` be overridden in `Order`?

**Answers and explanation:** `StoredEntity` has implemented `valid()`, and it remains `abstract` because it has not implemented `id()` and because Java allows declaring a class as abstract even when no abstract methods remain. `Order` only needs to implement `id()`: it inherits `valid()` from `StoredEntity` and `label()` from `Entity`. The expression `new Order().label()` returns `"ORD-1"`. `Order` cannot override `valid()` because this method is declared `final`.

## 10. Key Takeaway

**A concrete subclass is responsible for ensuring that all abstract contracts have valid implementations by the end of the inheritance chain.** The implementation may come from the subclass itself, an ancestor class, or a suitable interface default method; an intermediate `abstract` class is allowed to defer this responsibility. The compiler checks this obligation using the overriding rules, but the behavioral quality of the implementation still needs to be verified through testing and clear contract design.
