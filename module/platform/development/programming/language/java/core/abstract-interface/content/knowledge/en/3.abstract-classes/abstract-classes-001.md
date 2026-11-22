# `abstract class` Declaration Syntax in Java

## 1. Meaning of `abstract class`

An `abstract class` is a class marked with the `abstract` keyword. This class can provide shared data and behavior for subclasses, while also being able to declare methods that subclasses must complete.

Two basic rules:

- **Objects cannot be created directly** with `new` from an `abstract` class. However, variables, parameters, or return types can be declared as the abstract class and used to refer to objects of a concrete subclass.
- **An abstract class is not required to have abstract methods.** Conversely, any class that directly declares an `abstract` method must be declared `abstract`.

Use an abstract class when subclasses share state, constructors, or common processing, while some behaviors still vary by subclass.

## 2. Declaration Syntax Template

General template (parts inside `[ ]` are optional, not Java code to be compiled verbatim):

~~~text
[access-modifier] abstract class ClassName
        [extends ParentClass]
        [implements Interface1, Interface2, ...] {
    // fields, constructors, concrete methods, abstract methods...
}
~~~

Simplest example:

~~~java
abstract class Shape {
}
~~~

Example with an abstract method:

~~~java
abstract class Shape {
    abstract double area();
}
~~~

The `abstract double area();` part **has no method body** and ends with a semicolon `;`. The method currently has package-private access. For an API that needs to be implemented by subclasses in another package, `public` or `protected` is typically used.

| Component | Meaning and Rules |
|---|---|
| `abstract` | Keyword marking an abstract class; placed before `class`. |
| `class ClassName` | Class name following Java class naming syntax. |
| `public` (optional) | A top-level class can be declared `public` or without a modifier (package-private). |
| `extends ParentClass` | Inherits from at most **one** parent class. |
| `implements Interface1, ...` | Can implement **multiple** interfaces, separated by commas. |
| `{ ... }` | The class body can contain fields, constructors, regular methods, abstract methods, and other valid members. |

**Modifier and file rules:** a top-level class cannot be declared `private` or `protected`; these two modifiers can only be used for nested classes when valid. If a top-level class is declared `public abstract class Shape`, the code must be in `Shape.java`. Writing `public abstract class` is a common convention; `abstract public class` is also valid, but less commonly used.

## 3. Complete Example Running on Java 17+

The `Vehicle` class declares a field, a constructor, an implemented method, and an abstract method. `ElectricCar` implements the abstract method and becomes a concrete class.

Save all of the following code to **`Demo.java`**:

~~~java
abstract class Vehicle {
    private final String brand;

    protected Vehicle(String brand) {
        this.brand = brand;
    }

    public final String getBrand() {
        return brand;
    }

    public abstract String start();

    public void stop() {
        System.out.println("Xe đã dừng.");
    }
}

final class ElectricCar extends Vehicle {
    public ElectricCar(String brand) {
        super(brand);
    }

    @Override
    public String start() {
        return getBrand() + " khởi động bằng điện.";
    }
}

public class Demo {
    public static void main(String[] args) {
        Vehicle vehicle = new ElectricCar("VinFast");
        System.out.println(vehicle.start());
        vehicle.stop();
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac Demo.java
java Demo
~~~

Exact stdout output:

~~~text
VinFast khởi động bằng điện.
Xe đã dừng.
~~~

Explanation:

1. `abstract class Vehicle` is an abstract parent class, and **can still** have the `brand` field and the implemented `stop()` method.
2. `protected Vehicle(String brand)` is a valid constructor. The `super(brand)` statement from the `ElectricCar` constructor calls the parent class constructor and initializes the shared state.
3. `public abstract String start();` declares an instance method without a body. The concrete subclass `ElectricCar` overrides this method with a complete implementation.
4. `@Override` helps the compiler verify the override. The `getBrand()` method is declared `final`, so subclasses cannot override that method itself.
5. `final class ElectricCar` is still valid: the `final` modifier applies to the **concrete subclass**, not together with `abstract` on the same class.
6. The `Vehicle vehicle` variable uses an abstract reference type while holding an `ElectricCar` object. The `vehicle.start()` call runs `ElectricCar`'s version, demonstrating polymorphism.

Trying to replace `new ElectricCar("VinFast")` with `new Vehicle("VinFast")` will cause a compilation error, because an abstract class cannot be instantiated directly.

## 4. `abstract` Method Syntax

In an abstract class, `abstract` instance methods can be declared:

~~~java
abstract class Task {
    protected abstract void execute();

    public abstract int priority();

    public void printStatus() {
        System.out.println("Ready");
    }
}
~~~

`execute()` and `priority()` have only a signature and `;`, while `printStatus()` has a normal body. Note the constraints:

- An `abstract` method **has no curly braces for a method body**. To have a body, remove the `abstract` keyword from the method.
- An `abstract` method cannot be combined with `private`, `static`, or `final`: `private` does not allow overriding, `static` is not an instance method that can be overridden, and `final` forbids overriding. `abstract` also cannot be combined with the `native` or `synchronized` modifiers on the same method.
- When overriding, the implementing method must not narrow access privileges. For example, a `protected abstract` method in the parent class can be overridden in a subclass as `protected` or `public`.
- If a subclass is not declared `abstract`, it must implement all missing abstract methods in the inheritance chain, except for methods that already have a suitable inherited concrete implementation.
- An `abstract` class can contain regular methods, `static` methods with a body, and `final` methods with a body; it is just that **a single method** cannot be both `abstract` and `static` or `final`.

## 5. Subclass Syntax and Obligations

Declaring an `abstract class` allows a class to retain inherited abstract methods while an intermediate class continues to define shared state or behavior. A class may drop `abstract` only when all missing obligations have valid concrete implementations. Tracking obligations across multiple levels is explained in the lesson on the inheritance chain; there is no need to repeat another inheritance example here.

## 6. Combining `extends`, `implements`, and Generic Types

`extends` must come **before** `implements`. An `abstract` class does not have to implement all methods required by interfaces:

~~~java
interface Printable {
    void print();
}

interface Resettable {
    void reset();
}

class Parent {
    void ping() {
        System.out.println("pong");
    }
}

abstract class AbstractPrinter extends Parent
        implements Printable, Resettable {

    @Override
    public void print() {
        System.out.println("print");
    }

    // reset() has not been implemented yet.
}
~~~

`AbstractPrinter` remains valid because it is declared `abstract`. A **concrete** subclass must implement `reset()` if no suitable implementation is inherited. Note that the implementing method for a `public` method in an interface must also be declared `public`.

An `abstract` class can use type parameters just like a regular Java class:

~~~java
abstract class Repository<T> {
    abstract T findById(long id);
}
~~~

`T` is a type parameter; generics do not change how an `abstract class` is declared or the rules for abstract methods.

## 7. Common Syntax Errors

| Incorrect Declaration | Why It Is Invalid | How to Fix |
|---|---|---|
| `class Shape abstract {}` | Modifier placed in the wrong position. | `abstract class Shape {}` |
| `abstract class {}` | Missing class name. | `abstract class Shape {}` |
| `class Shape { abstract double area(); }` | The class directly declares an `abstract` method, yet is not an `abstract` class. | Add `abstract` to the class or provide a body for the method. |
| `abstract class Shape { abstract double area() {} }` | An `abstract` method cannot have a body. | End the declaration with `;` or remove `abstract` from the method. |
| `private abstract class Shape {}` at top level | A top-level class cannot be declared `private` or `protected`. | Use package-private or `public`. |

If the top-level class is `public`, the source file name must match the class name. Conflicting modifier combinations such as `abstract final` are analyzed separately in the lesson on modifiers; there is no need to repeat the entire matrix in this syntax lesson.

## 8. Key Takeaways and Application

When declaring an abstract parent class, identify the **shared** part (fields, constructors, regular methods) and the part **each subclass must decide** (`abstract` methods). Then verify that the concrete subclass has implemented all missing methods.

Short template to remember:

~~~java
public abstract class AbstractService {
    protected AbstractService() {
    }

    public abstract void execute();

    public void printStatus() {
        System.out.println("Ready");
    }
}
~~~

This is a valid class declaration if saved in `AbstractService.java`; it does not have a `main()` method to run on its own. The class has a constructor, a regular method with a body, and an abstract method ending with `;`.

If you only want to define a contract for multiple types that do not share state or an inheritance hierarchy, consider an `interface`. Java interfaces can also have `default` and `static` methods with bodies, so you should not distinguish the two with the simple conclusion that an interface "contains no code".

**Core of the syntax:** `abstract` is placed before `class` to declare an abstract class; `abstract` is placed on a method to require subclasses to implement it; this method ends with `;`; and `new` is only used with an instantiable concrete class.
