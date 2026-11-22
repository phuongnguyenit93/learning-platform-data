# `class` Syntax and Class Body Structure in Java

## 1. What Does Declaring a Class Mean?

In Java, the **`class`** keyword begins a *class declaration*. The declaration creates a name for a new **reference type**, and defines the data and behavior that objects of that type can have.

Minimal declaration:

```java
class Book {
}
```

`Book` is already a valid type even though the class body is empty. If the code is within a permitted access scope, a programmer can declare `Book book;` or create an instance with `new Book()`. In this case, because no constructor is declared, the compiler provides a default no-argument constructor. Declaring the variable `Book book;` **does not create an object yet**.

The curly braces `{` and `}` delimit the **class body**. Declarations of fields, constructors, methods, initializer blocks, and nested types can appear inside, according to Java syntax rules.

## 2. General Form of a `class` Declaration

A syntax skeleton illustrating the optional components:

```java
[annotations] [modifiers] class ClassName [<T, ...>]
        [extends Superclass]
        [implements InterfaceA, InterfaceB, ...]
        [permits SubclassA, SubclassB, ...] {
    // Member declarations and initializer blocks
}
```

**This is descriptive syntax notation, not Java code to be compiled verbatim.** Square brackets indicate "may or may not be present"; `...` represents a list. Not every combination is valid.

| Part | Role and Key Rules |
| --- | --- |
| `class` | Required keyword when declaring a regular class. |
| `ClassName` | A valid identifier name, typically following the `UpperCamelCase` convention, for example `BankAccount`. |
| `[annotations]` | Metadata annotations on the class if needed, for example `@Deprecated`. |
| `[modifiers]` | Controls access level and class characteristics, such as `public`, `abstract`, `final`, `sealed`. |
| `<T, ...>` | *Type parameters* of a generic class; for example, `class Box<T>`. |
| `extends Superclass` | Specifies the direct superclass; a regular class can `extends` only **one class**. |
| `implements ...` | Specifies the implemented interfaces; there can be multiple interfaces, separated by commas. |
| `permits ...` | Used in a `sealed` class declaration when listing permitted subclasses; subject to the specific rules of sealed types. |
| `{ ... }` | The class body, containing syntactically valid declarations and initializer blocks. |

Valid example:

```java
class Account {
}

public class PremiumAccount extends Account implements java.io.Serializable {
    private static final long serialVersionUID = 1L;
}
```

This snippet illustrates the *declaration form*, not a standalone runnable file because it has no `main`. If placed in a file named `PremiumAccount.java` without adding a `package` declaration, the two top-level classes here compile. `PremiumAccount` is a `public` class; `Account` has **package-private** access because no modifier is specified. `extends` comes before `implements` in the declaration.

If `extends` is omitted, a regular class implicitly inherits from `java.lang.Object` (except for the `Object` class itself). Multiple superclasses such as `extends ParentA, ParentB` cannot be written. Java has polymorphism through interfaces and single inheritance between classes.

### Placement in a Source File

A `.java` file typically follows this order:

```java
// package example.study;        // If using a package, this is the first declaration
// import java.util.Objects;      // If imports are needed, place them after package

public class Demo {
    // Class body
}
```

The first two lines are commented out so the skeleton does not depend on a package directory. If you actually write `package example.study;`, the file must be compiled/run according to the proper package and an appropriate path structure. `import` allows using short type names in source code; it does not declare a new type.

At the **top-level**, a class can be `public` or have no access modifier (package-private); a top-level class cannot be declared with `private` or `protected`. A Java source file is allowed to contain multiple top-level classes, but at most **one `public` top-level class**, and the file name must match the name of that `public` class. For example, if there is `public class Demo`, save the file as `Demo.java`.

## 3. What Components Are Inside a Class Body?

The part between `{` and `}` of a class is not a sequential list of statements executed one after another. It consists primarily of **member declarations**, along with valid **initializer blocks**.

| Component | Example | Meaning |
| --- | --- | --- |
| Instance field | `private String title;` | State specific to each instance. |
| Static field | `private static int count;` | State belonging to the class. |
| Constructor | `Book(String title) { ... }` | Initializes an object; has the same name as the class and no return type. |
| Instance method | `String getTitle() { ... }` | Behavior invoked on an object; can use `this`. |
| Static method | `static int count() { ... }` | Behavior associated with the class; has no `this`. |
| Instance initializer | `{ /* lệnh */ }` | Instance initializer block; runs during object creation. |
| Static initializer | `static { /* lệnh */ }` | Static initializer block; runs when the class is initialized. |
| Nested type | `static class Helper { }` | A type declared inside another class. |
| Common constant | `static final int MAX = 100;` | A static field that cannot be reassigned after initialization. |

Besides nested classes, a class body can declare nested interfaces, enums, records, and annotation types when the context permits. A method or constructor can contain **executable statements**. Conversely, you cannot place a standalone statement such as `System.out.println("Hello");` directly between the field/method declarations of a class.

Fields and methods are not required to be ordered strictly as shown in the table. You can declare a method above a field it uses. However, **the order among field initializers and initializer blocks of the same kind is very important at runtime**, which will be explained later.

### Distinguishing Fields, Parameters, and Local Variables

```java
class Product {
    private String name;                 // Field: belongs to each Product

    Product(String name) {                // name: constructor parameter
        this.name = name;                // this.name: instance field
    }

    String format() {
        String prefix = "Product: ";      // Local variable of the method
        return prefix + name;
    }
}
```

Fields have default values if not explicitly initialized: reference fields have the value `null`, `int` has the value `0`, and `boolean` has the value `false`. A local variable cannot be read before it is definitely assigned. `this` refers to the current instance in an instance context, commonly used when a field and a parameter share the same name. Fields marked `private` only allow direct access from code within the scope defined by Java; methods of the class itself can still read or modify them.

## 4. Complete Program Showing Each Component in Action

Create the following **`ClassSyntaxDemo.java`** file; this is a complete example using Java 17 or later.

```java
class Device {
    // 1. Static field: shared across the Device class.
    private static int createdCount;

    // 2. Instance fields: each Device has its own values.
    private final String name;
    private boolean active; // Defaults to false.

    // 3. Static initializer: runs when the Device class is initialized.
    static {
        System.out.println("Device: static initializer");
    }

    // 4. Instance initializer: runs when creating each Device object.
    {
        System.out.println("Device: instance initializer");
    }

    // 5. Constructor: same name as Device, no return type.
    Device(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Name is required");
        }
        this.name = name;
        createdCount++;
        System.out.println("Device: constructor " + name);
    }

    // 6. Instance method.
    void activate() {
        active = true;
    }

    String describe() {
        return name + " = " + (active ? "on" : "off");
    }

    // 7. Static method.
    static int getCreatedCount() {
        return createdCount;
    }

    // 8. Static nested class.
    static class Category {
        static String label() {
            return "general";
        }
    }
}

public class ClassSyntaxDemo {
    public static void main(String[] args) {
        System.out.println("Begin");

        Device first = new Device("Laptop");
        first.activate();
        Device second = new Device("Speaker");

        System.out.println(first.describe());
        System.out.println(second.describe());
        System.out.println(Device.getCreatedCount());
        System.out.println(Device.Category.label());
    }
}
```

Compile and run in the directory containing `ClassSyntaxDemo.java`:

```bash
javac ClassSyntaxDemo.java
java ClassSyntaxDemo
```

**Exact standard output:**

```text
Begin
Device: static initializer
Device: instance initializer
Device: constructor Laptop
Device: instance initializer
Device: constructor Speaker
Laptop = on
Speaker = off
2
general
```

Explanation:

1. `ClassSyntaxDemo.main` prints `Begin` before using `Device`. The `new Device("Laptop")` statement triggers initialization of the `Device` class on this active use, so `static initializer` is printed only **once**.
2. Before the constructor body for each object, the instance initializers in the class are executed; therefore, the `instance initializer` message appears **twice**.
3. The constructor accepts a parameter, validates the input, assigns the `name` field, increments the static counter, and prints the device name. `Device` does not declare a no-argument constructor, so `new Device()` will not compile.
4. `active` is an instance field of type `boolean`, defaulting to `false`. Only `first.activate()` is called, so `first.describe()` prints `on` while `second.describe()` prints `off`.
5. `createdCount` is a `static` field updated by both object creations; `Device.getCreatedCount()` returns `2`.
6. `Category` is a **static nested class** inside `Device`; `Device.Category.label()` demonstrates the syntax for referencing a nested type and calling its static method.
7. `Device` is not `public` and resides in the same file and package as `ClassSyntaxDemo`; `ClassSyntaxDemo` is the `public` top-level class, so the correct file name is `ClassSyntaxDemo.java`.

The `javac ClassSyntaxDemo.java` command generates the corresponding `.class` files (for example, `Device.class`, `Device$Category.class`, and `ClassSyntaxDemo.class`), yet a single source file still has only one `public` top-level class.

## 5. Field Syntax Rules

Fields take the common form:

```java
[modifiers] Type fieldName [= expression];
```

This is illustrative notation; a real example:

```java
class InventoryItem {
    private String sku;
    private int stock = 0;
    public static final int MAX_STOCK = 1000;
}
```

- Each field declaration ends with a **semicolon `;`**.
- `private`, `protected`, `public`, or having no modifier determines accessibility; `static` specifies that the field belongs to the class; `final` requires the field to be assigned according to the rules and not reassigned afterward.
- `private final String sku;` is valid if every constructor that completes normally ensures the `sku` field has been assigned. In the example above, `sku` is not `final`, so it defaults to `null`.
- Multiple variables of the same type can be declared on one line, for example `int width, height;`, though separating each field onto its own line is usually easier to read and comment.
- `var` is only used for certain local variable declarations with an initializer; **do not use `var` as a field type**. For example, `private var stock = 1;` in a class body is a compile-time error.

`final` on a reference variable does not make the referenced object immutable. For example, a `final List<String> names` field cannot be reassigned to another list after initialization, but the contents of that list can still change if the list supports modification operations.

## 6. Constructor Syntax Rules

A constructor has the form:

```java
[access_modifier] ClassName(ParameterType parameter, ...) {
    // Initialize the object and ensure valid conditions
}
```

No return type is written, not even `void`. The name must match the **class name** exactly, and a class can declare multiple constructors differing by parameter list (*constructor overloading*).

Example:

```java
class Rectangle {
    private final int width;
    private final int height;

    Rectangle() {
        this(1, 1);
    }

    Rectangle(int width, int height) {
        if (width <= 0 || height <= 0) {
            throw new IllegalArgumentException("Dimensions must be positive");
        }
        this.width = width;
        this.height = height;
    }

    int area() {
        return width * height;
    }
}
```

This is a class declaration snippet that compiles, though it has no `main` of its own to run directly. `Rectangle()` calls `this(1, 1)` to reuse the two-parameter constructor. In Java 17, a call to another constructor using `this(...)` or to a superclass constructor using `super(...)` must be the first statement in a constructor if written explicitly, and both cannot be used in the same constructor. If neither call is written, the compiler typically inserts an appropriate `super()` call; therefore, the superclass needs a matching constructor.

Distinction:

```java
class Example {
    Example() { }        // Valid constructor.
    void Example() { }   // Method named "Example", NOT a constructor.
}
```

If a class **declares no constructors**, the compiler generates a default no-argument constructor; once **at least one constructor has been explicitly declared**, the compiler does not generate a default constructor. A constructor cannot be declared as `static`, `final`, or `abstract`.

## 7. Method Syntax Rules

A regular method consists of optional modifiers, a **return type**, a name, a parameter list, and a body inside curly braces:

```java
[modifiers] ReturnType methodName(ParameterType parameter, ...) {
    // Statements
}
```

Example:

```java
class Temperature {
    private double celsius;

    Temperature(double celsius) {
        this.celsius = celsius;
    }

    double fahrenheit() {
        return celsius * 9 / 5 + 32;
    }

    void setCelsius(double newValue) {
        celsius = newValue;
    }

    static String unit() {
        return "Celsius";
    }
}
```

`fahrenheit()` returns `double` and must return a value along the normal execution paths of the method. `setCelsius(...)` has a `void` return type, so it returns no value; `unit()` is a static method that can be called via `Temperature.unit()` without creating an instance.

Inside a static method, no `this` variable exists; to access an object's `celsius` field, you must have a specific reference to a `Temperature` instance. An instance method can access both permitted instance members and static members.

An `abstract` method and certain method declarations in an interface can **have no body**, in which case they end with `;`. Example:

```java
abstract class Task {
    abstract void execute(); // No body because it is an abstract method.

    void log() {              // Concrete method with a body.
        System.out.println("Task");
    }
}
```

A class with an abstract method must be declared `abstract`. You cannot instantiate it directly with `new Task()`. A non-abstract subclass must implement any missing abstract methods.

Punctuation note: a **field declaration** ends with `;`; a method/constructor **with a body** ends with `}` and does not need an extra `;`; statements inside a method body generally end with `;` according to the syntax of each statement kind. The class body is not a place for arbitrary statements.

## 8. Initialization Order: `static`, Instance Initializer, and Constructor

The declaration structures look similar, yet their execution timing differs:

1. **When a class is initialized**, the class's static field initializers and `static { ... }` blocks are processed in textual order under the appropriate initialization conditions. Class initialization does not mean merely loading the `.class` file. Static initializers do not run again for each instance.
2. **When creating an instance**, the JVM performs allocation and sets default field values first; after the superclass constructor step, the instance field initializers and instance initializer blocks of the current class are executed in textual order, before the constructor body of the current class.
3. **The constructor body** finishes setting up the object. With constructor chaining via `this(...)`, the class's instance initialization is not repeated for each constructor in the chain.

A dedicated example of the order within **the same class**, which can be placed in `InitOrderDemo.java`:

```java
class Counter {
    static int multiplier = 2;

    static {
        multiplier += 1;
    }

    private int value = 10;

    {
        value += multiplier;
    }

    Counter() {
        value *= 2;
    }

    int value() {
        return value;
    }
}

public class InitOrderDemo {
    public static void main(String[] args) {
        System.out.println(new Counter().value());
        System.out.println(new Counter().value());
    }
}
```

```bash
javac InitOrderDemo.java
java InitOrderDemo
```

```text
26
26
```

Reason: `multiplier` starts at `2` and increments to `3` when the class is initialized; each instance gets `value = 10`, the instance block adds `3` to make `13`, and the constructor doubles it to `26`. Static initialization does not repeat when creating the second instance.

**Do not overuse initializer blocks** merely to do something a constructor can express more clearly. The example uses initializer blocks to illustrate class structure; in applications, simple field initialization at the declaration site and state validation in the constructor are generally preferred.

Some advanced details lie outside the basic flow: referencing a static constant that is a *compile-time constant* may not trigger static initializers; initialization and inheritance interact according to strict rules; initializers cannot arbitrarily read an uninitialized instance field at an invalid position. When learning execution order, rely on the actual code and initialization rules rather than inferring from when the JVM has "loaded" the class.

## 9. Where Are Access Rights and Modifiers Used?

Not every modifier is valid in every context:

| Location | Common Modifiers/Characteristics | Notes |
| --- | --- | --- |
| Top-level class | `public` or package-private; `abstract`, `final`, `sealed` per rules | Do not declare a top-level class as `private`, `protected`, or `static`. |
| Member class (nested class inside a class) | Can be `public`, `protected`, `private`, or package-private; can be `static` | Has member access scope; a static nested class does not require an instance of the enclosing class. |
| Instance field | Access modifier, `final`, `transient`, `volatile` depending on the case | Do not declare a field as both `final` and `volatile`. |
| Static field | Access modifier and `static`, often combined with `final` for constants | Shared state and per-instance state must be distinguished. |
| Constructor | `public`, `protected`, `private`, or package-private | Has no return type; cannot be `static`, `final`, or `abstract`. |
| Method | Access modifier, `static`, `final`, `abstract`, `synchronized`, ... | Combinations have constraints; for instance, an abstract method cannot also be `final`. |

`abstract` means the class may lack a complete implementation; `final` prevents the class from being inherited. Therefore, `abstract final class X` is invalid. `sealed` is Java 17's way of controlling permitted subclasses; direct subclasses must declare an appropriate modifier such as `final`, `sealed`, or `non-sealed` and satisfy the other requirements of a sealed hierarchy. Example:

```java
sealed class Shape permits Circle, Square {
}

final class Circle extends Shape {
}

non-sealed class Square extends Shape {
}
```

The snippet above is a valid type declaration in Java 17, without `main`. `Square` allows further extension, while `Circle` terminates its inheritance branch. Sealed classes are not needed for every data model; the example only clarifies `permits` and `non-sealed` in class syntax.

A top-level class with no access modifier is **package-private**: code from the same package can reference it if other access conditions permit. A `private` member is only accessible according to Java's private-scope rules; being in the "same source file" does not automatically mean "has private access." Modifier choices are part of a class's API.

## 10. Nested Types Inside the Class Body

`class` is not limited to appearing at the top of a file: it can also reside inside another class or in a local type declaration context according to Java rules.

```java
class Outer {
    private int base = 10;

    class Inner {
        int addToBase(int n) {
            return base + n;
        }
    }

    static class Nested {
        static int doubleValue(int n) {
            return n * 2;
        }
    }
}

public class NestedDemo {
    public static void main(String[] args) {
        Outer outer = new Outer();
        Outer.Inner inner = outer.new Inner();

        System.out.println(inner.addToBase(5));
        System.out.println(Outer.Nested.doubleValue(5));
    }
}
```

Save as `NestedDemo.java` and run:

```bash
javac NestedDemo.java
java NestedDemo
```

```text
15
10
```

`Inner` is a **non-static member class** (*inner class*); each of its instances is associated with an `Outer` instance. That is why the code uses `outer.new Inner()`; the inner class can access `base` of the enclosing `Outer` object. `Nested` is a **static nested class**, so it uses the type name `Outer.Nested` without needing an `Outer` instance. Here, `static` describes the kind of nested class; it does not turn the class into a standalone function.

A *local class* can be declared in a block such as inside a method; an *anonymous class* has its own expression syntax. These are other forms of type organization in Java, while top-level and member class structures are sufficient to grasp the basic meaning of the class body.

## 11. How to Read and Review a Class Declaration

When encountering an unfamiliar class, you can scan it in sequence:

1. **Read the declaration line:** what is the type name; what access level does it have; are there `abstract`/`final`/`sealed`, generic parameters, `extends`, or `implements`?
2. **Identify state:** which fields belong to instances, and which are `static`? Which fields are `final`? Which fields are initialized directly at declaration?
3. **Find constructors:** what parameters do they accept, what data do they validate, do they call `this(...)`/`super(...)`? Is there a no-argument constructor or not?
4. **Find API methods:** return value types, access levels, side effects, and the distinction between instance and static methods.
5. **Find initializers and nested types:** which blocks run once upon class initialization, which blocks run per instance, and are there nested types that need further understanding?

By Java convention, class, field, and method names typically use `UpperCamelCase` for types (`OrderItem`), `lowerCamelCase` for variables/methods (`itemCount`, `calculateTotal`), and `UPPER_SNAKE_CASE` for constants (`MAX_RETRIES`). This is a readability convention, not a mandatory syntax requirement.

## 12. Common Mistakes When Writing `class`

| Situation | Wrong Example / How to Fix |
| --- | --- |
| Forgetting braces around the class body | `class User` missing `{ ... }` is a syntax error. |
| Writing a free-standing statement directly in the class body | `class A { System.out.println("Hi"); }` is invalid; place statements inside a method, constructor, or initializer block. |
| Writing `private class A` at the top level | `private` only applies to appropriate contexts such as member classes, not top-level classes. |
| Naming the file differently from the `public` class | `public class Report` must be in the file `Report.java`. |
| Placing two `public` top-level classes in the same file | Separate them into corresponding files, or change the design/access level as needed. |
| Confusing a method with a constructor | `void User() { }` is a method, not a constructor `User() { }`. |
| Assuming the compiler always generates a no-argument constructor | If `User(String name)` exists without declaring `User()`, `new User()` is a compile-time error. |
| Accessing an instance field directly from a static method | Need to create/obtain an object reference and access it per access rules; a static method has no `this`. |
| Using `var` as a field type | `class A { var x = 1; }` does not compile; declare a concrete type such as `int x = 1;`. |
| Thinking every `{ ... }` in a class is a method | A `static { ... }` block and a standalone `{ ... }` block in the class body are initializers; a method requires a declaration signature. |
| Writing multiple superclasses in `extends` | A Java class has only one direct superclass; use `implements` for multiple interfaces. |
| Thinking initializer order does not affect results | Field initializers and initializer blocks of the same kind are processed in declaration order during initialization; check before swapping them. |

The "wrong example" snippets in the table are provided to recognize errors and **are not meant to be compiled verbatim**.

## 13. Self-Check Exercises

**Exercise 1 — Identify Structure.** In `Device` from the main example, list: one static field, two instance fields, the constructor, the static initializer, the instance initializer, one instance method, one static method, and one nested type.

*Answer hint:* `createdCount`; `name` and `active`; `Device(String name)`; `static { ... }`; `{ ... }`; `activate()` or `describe()`; `getCreatedCount()`; `Category`.

**Exercise 2 — Check Order.** If `main` additionally calls `new Device("Tablet")` and then `System.out.println(Device.getCreatedCount());`, which initializers run and what is printed?

*Answer:* The static initializer **does not run again**; the instance initializer prints one line, the constructor prints `Device: constructor Tablet`, and then the printed count is `3`.

**Exercise 3 — Design a Class Yourself.** Write a `Wallet` class with `private int balance`, a constructor accepting a non-negative initial balance, a `deposit(int amount)` method that only accepts positive numbers, and a `getBalance()` method that returns the balance. Choose a valid file name if the top-level class is declared `public`. Identify on your own which parts are the field, constructor, methods, and where `;`/`{}` belong.

**Exercise 4 — Distinguish Declaration Skeletons.** Explain why `class A { }` is valid, `private class A { }` at the top level is an error, and `class A { private class B { } }` can be valid.

*Answer:* A top-level class can have no members; the `private` modifier is not used for top-level types; however, `B` is a **member class** of `A`, so it can be `private`.

**Exercise 5 — Diagnosis.** Can the class `class X { X(int n) { } }` be instantiated with `new X()`? To support that syntax, what must be changed?

*Answer:* No; you must add a constructor `X()` (for example calling `this(0);`), or pass an argument `new X(5)` matching the existing signature.

---

**Key Takeaway:** The line `class Name ... { ... }` declares a **type**; the header specifies the name, scope, and type relationships, while the **class body** holds fields, constructors, methods, initializers, and nested types. Properly distinguishing declaration placement, `;`/brace rules, `static` versus instance members, and initialization order will help you read and write Java classes more accurately.
