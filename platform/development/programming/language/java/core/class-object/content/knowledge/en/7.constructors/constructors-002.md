# Constructors in Java: Syntax, Naming, and Differences from Methods

A **constructor** is a component of a class that is executed during instance creation to set up the initial state of the object. In Java, a constructor looks similar to a method with a name and parameter parentheses, but it has **its own rules**:

- **The constructor name must exactly match the simple name of the class** declaring it (case-sensitive).
- **A constructor does not declare a return type**, not even `void`. If you add `void`, that declaration is a **method**, not a constructor.
- A constructor of a regular class is invoked during object creation with `new ClassName(...)` or called from another constructor via `this(...)`/`super(...)`.
- Constructors can be **overloaded** by parameter list, but they are **not inherited or overridden** like instance methods.
- A constructor can validate data, initialize fields, and throw exceptions when input is invalid.

Short example:

```java
class Student {
    String name;

    Student(String name) {  // Constructor: no return type
        this.name = name;
    }

    void printName() {     // Method: has a void return type
        System.out.println(name);
    }
}
```

In `new Student("An")`, `Student(String name)` is the constructor invoked to initialize a new `Student`. `printName()` is a method called **later** on the object, for example `student.printName()`. The two constructs differ in purpose and syntax, even though both have a body inside curly braces.

## 1. Constructor declaration syntax

Basic declaration form for a regular class:

```java
[accessModifier] ClassName(parameterList) [throws ExceptionType] {
    // Validate input and initialize the object
}
```

This is a **syntax template**, not a standalone Java snippet to compile. A constructor can have annotations, generic type parameters, a `throws` declaration, and other special rules; in this introductory lesson, remember **class name + parameter list + body**, without placing a return type before the name.

Example:

```java
class Book {
    String title;
    int pages;

    Book() {
        this.title = "Chưa đặt tên";
        this.pages = 0;
    }

    Book(String title, int pages) {
        this.title = title;
        this.pages = pages;
    }
}
```

Both `Book()` and `Book(String title, int pages)` are constructors of the `Book` class. The name `Book` matches the class name. The two constructors differ in **number of parameters**, so they can coexist.

Components of a declaration:

| Component | Example | Role |
| --- | --- | --- |
| Optional access modifier | `public`, `protected`, `private`, or omit the modifier | Controls where the constructor may be called |
| Constructor name | `Book` | Must match the simple name of the class |
| Parameter list | `String title, int pages` | Input data for initialization |
| Optional `throws` clause | `throws IllegalArgumentException` | Declares relevant exception types (unchecked exceptions are not required to be declared) |
| Constructor body | `{ this.title = title; }` | Instance initialization logic |
| Return type | **None** | This is where a constructor differs from a method |

**Do not confuse a constructor with a `new` call:** in the expression `new Book("Java", 250)`, the `new` keyword participates in **creating and initializing the object**, and the expression has type `Book`. The constructor itself **is not a method returning `Book`**, nor do you write `return this;`.

## 2. The constructor name must match the class name

The constructor name is the simple name of the class that contains it and is case-sensitive.

Valid example:

```java
class Employee {
    Employee() {
        System.out.println("Đã tạo Employee");
    }
}
```

**Invalid** example:

```java
class Employee {
    employee() {                 // WRONG: case mismatch
        System.out.println("Hi");
    }
}
```

In this invalid example, `employee()` is not a constructor of `Employee`. Because it lacks a return type, it is not a valid method declaration either.

Similarly, a constructor cannot have an arbitrary name:

```java
class Employee {
    CreateEmployee() {           // WRONG: name does not match the class and lacks a return type
    }
}
```

If you want functionality named `createEmployee`, you can write a **factory method** with a specific return type instead of imitating a constructor:

```java
class Employee {
    Employee() {
    }

    static Employee createEmployee() {
        return new Employee();
    }
}
```

Here `Employee()` is a constructor, while `createEmployee()` is a **static method** returning an `Employee` reference. A factory method can be given a meaningful name such as `of(...)` or `create(...)`, whereas a constructor is required to carry the exact class name.

### 2.1. A method with the same name as the class can still exist

A declaration **with a return type** is a method even if its name matches the class name:

```java
class Robot {
    void Robot() {
        System.out.println("Đây là method, không phải constructor");
    }
}
```

`void Robot()` is **not** a constructor. Because the `Robot` class has not declared any real constructor, provided the superclass allows it, Java automatically supplies a **no-argument default constructor**. `new Robot()` does not print the message on its own; only an explicit call to `robot.Robot()` executes the method above.

Although it may be valid in the language, **you should not name a method the same as the class**: it is very easily confused with a constructor. Use names that describe behavior, such as `initialize()` or `printStatus()`.

## 3. Complete Java 17 example: constructor and method side by side

Save all of the following code to **`ConstructorVsMethodDemo.java`**:

```java
class Person {
    private final String name;
    private int age;

    Person(String name) {
        this(name, 0);
    }

    Person(String name, int age) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên không hợp lệ");
        }
        if (age < 0) {
            throw new IllegalArgumentException("Tuổi không hợp lệ");
        }
        this.name = name;
        this.age = age;
    }

    String describe() {
        return name + " (" + age + ")";
    }

    void birthday() {
        age++;
    }
}

public class ConstructorVsMethodDemo {
    public static void main(String[] args) {
        Person an = new Person("An");
        Person binh = new Person("Bình", 20);

        System.out.println(an.describe());
        System.out.println(binh.describe());

        binh.birthday();
        System.out.println(binh.describe());
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 ConstructorVsMethodDemo.java
java ConstructorVsMethodDemo
```

**Exact stdout:**

```text
An (0)
Bình (20)
Bình (21)
```

Explanation:

1. `Person(String name)` is a **one-parameter** constructor, while `Person(String name, int age)` is a **two-parameter** constructor. Both are named `Person` and declare no return type.
2. `new Person("An")` selects the one-parameter constructor. The statement `this(name, 0);` calls the two-parameter constructor **within the same class**, providing the default age value `0`.
3. `new Person("Bình", 20)` calls the two-parameter constructor directly.
4. Both initialization paths reach the name/age validation logic and assign the `name` and `age` fields.
5. `describe()` is a **method returning `String`**; the caller can pass the returned value to `System.out.println`.
6. `birthday()` is a **`void` method**; it updates the `age` field of an existing object. Calling `birthday()` does not create a new `Person` object.
7. `name` is a `final instance field`, assigned during initialization; `age` can change through a method.

Only `ConstructorVsMethodDemo` is top-level `public`, so the source file name is `ConstructorVsMethodDemo.java`. `Person` is top-level package-private in the same file.

## 4. Differences between a constructor and a method

| Criterion | Constructor | Method |
| --- | --- | --- |
| Primary purpose | Initializes an instance when it is created | Performs behavior; can read, modify, or compute |
| Name | Must match the simple name of the class | Chosen by the programmer following valid naming syntax |
| Return type in declaration | **Must not be specified**, not even `void` | Must declare a type or `void` |
| Typical invocation | `new Type(arguments)` or via `this(...)`/`super(...)` | `object.method(arguments)` or `Type.staticMethod(arguments)` |
| Overloading | Yes, by parameter list | Yes, by parameter list |
| Inheritance | **No**; a subclass does not inherit constructors from its superclass | Suitable instance methods can be inherited |
| Overriding | **No** | Eligible instance methods can be overridden |
| `static` | **Not allowed** | Allowed for static methods |
| `abstract`/`final` | **Not applicable as constructor modifiers** | Can be applied to methods in valid contexts |
| `return;` | Can be used to exit early without a value | Valid in `void` methods |
| `return expression;` | **Not allowed** | Required/allowed depending on the method's return type |
| Creates a new object? | Participates in the creation of a requested object | Not automatically; only creates an object if the method body performs the corresponding operation |
| Access level | Has `public`/`protected`/package-private/`private` levels | Also has the appropriate levels |

**Very important distinction:** the expression `new Student(...)` **yields a reference to the object**, but that does not mean the constructor has a return type of `Student`. The result of a `new` expression and the **return type of a method** are two different concepts.

### A constructor is not a “special method with a void return type”

The explanation that “a constructor is a `void` method that runs automatically” is **incorrect regarding syntax and the language model**. The two declarations:

```java
class Demo {
    Demo() { }          // Constructor
    void run() { }      // void method
}
```

differ because `Demo()` has no return type declaration, whereas `run()` has `void`. If you write `void Demo() { }`, that is a **method named Demo**, not a constructor.

## 5. Which constructor does `new` call?

When a class has multiple different constructors, Java selects the constructor that matches the **number and types of argument expressions**:

```java
class Box {
    int capacity;

    Box() {
        this.capacity = 0;
    }

    Box(int capacity) {
        this.capacity = capacity;
    }

    Box(String label) {
        this.capacity = label.length();
    }
}
```

Calls in a method that has access:

```java
Box a = new Box();             // Box()
Box b = new Box(10);           // Box(int)
Box c = new Box("Java");       // Box(String)
```

In this case, the `capacity` values are `0`, `10`, and `4`, respectively. This is **constructor overloading**. The constructors share the same name `Box` but have **different parameter lists**.

You cannot declare two constructors **that differ only in parameter names**:

```java
class Item {
    Item(int quantity) { }

    // Item(int amount) { }  // WRONG if uncommented: same signature Item(int)
}
```

Nor is there any such thing as “overloading constructors by return type,” because constructors **have no return type to overload on**.

### A constructor only accepts declared parameters

`new Box("Java", 3)` is invalid with the three `Box` constructors above because there is no signature accepting `(String, int)`. If you want to support that way of creating an instance, declare an additional matching constructor or use a factory.

The compiler checks the **types and number of arguments at compile time**, even when parameters use widening, boxing, or varargs according to Java rules. Constructor selection is not based on argument variable names.

## 6. No-argument constructor: default vs. explicit

There are two concepts commonly referred to together as a “default constructor”:

1. **Default constructor automatically provided by the compiler:** appears only if the class **declares no constructors at all**.
2. **No-argument constructor written by the programmer:** has an empty parameter list `()`, but is **not** a compiler-generated default constructor.

Example **without writing a constructor**:

```java
class EmptyBox {
    int size;
}
```

During compilation, Java implicitly supplies a no-argument constructor for `EmptyBox` if the superclass conditions allow it. You can create:

```java
EmptyBox box = new EmptyBox();
System.out.println(box.size); // 0
```

The `size` field receives the default value `0` of `int`. **Do not infer** that a default constructor automatically sets every field to a “sensible business value”; it merely participates in Java's normal initialization.

Example **where a parameterized constructor has been written**:

```java
class SizeBox {
    int size;

    SizeBox(int size) {
        this.size = size;
    }
}
```

`new SizeBox(5)` is valid, whereas `new SizeBox()` is **not** valid. Once the author declares `SizeBox(int size)`, Java **no longer automatically provides** a default no-arg constructor.

To allow both ways of creating an instance, declare two constructors:

```java
class SizeBox {
    int size;

    SizeBox() {
        this(0);
    }

    SizeBox(int size) {
        this.size = size;
    }
}
```

A `SizeBox()` constructor written by the programmer is an **explicit no-arg constructor**. It can set business defaults or delegate to another constructor.

### Runnable example: default and explicit no-arg

Save as **`DefaultConstructorDemo.java`**:

```java
class DefaultBox {
    int count;
}

class ManualBox {
    int count;

    ManualBox() {
        count = 10;
    }

    ManualBox(int count) {
        this.count = count;
    }
}

public class DefaultConstructorDemo {
    public static void main(String[] args) {
        DefaultBox first = new DefaultBox();
        ManualBox second = new ManualBox();
        ManualBox third = new ManualBox(7);

        System.out.println(first.count);
        System.out.println(second.count);
        System.out.println(third.count);
    }
}
```

```bash
javac -encoding UTF-8 DefaultConstructorDemo.java
java DefaultConstructorDemo
```

Stdout:

```text
0
10
7
```

`DefaultBox` declares no constructors, so the compiler provides a default constructor. `ManualBox` has two explicitly written constructors, consisting of a no-arg constructor and a one-parameter constructor.

**Important note about superclasses:** the default constructor must call an appropriate superclass constructor; if the superclass has no accessible no-argument constructor, the subclass cannot rely on an implicit `super()` without declaring an alternative.

## 7. Constructor chaining: `this(...)` and `super(...)`

A constructor can call another constructor during initialization:

- **`this(arguments);`**: calls another constructor **in the same class**.
- **`super(arguments);`**: calls a constructor of the **direct superclass**.

In **Java 17**, an explicit constructor invocation using `this(...)` or `super(...)` must appear as the **first statement in the constructor body**. You cannot place print statements, assignments, or other operations before that call.

### 7.1. `this(...)` reduces duplicated logic

```java
class Rectangle {
    final int width;
    final int height;

    Rectangle() {
        this(1, 1);
    }

    Rectangle(int width, int height) {
        this.width = width;
        this.height = height;
    }

    int area() {
        return width * height;
    }
}
```

`new Rectangle()` invokes `Rectangle()`, and then `this(1, 1)` delegates to `Rectangle(int, int)`. As a result, the field assignments reside in only one constructor.

`this(...)` **does not create a second object**. It transfers control to another constructor to initialize **the same object currently being created**.

Do not write:

```java
class Invalid {
    Invalid() {
        System.out.println("Trước");
        this(1);               // WRONG in Java 17: this(...) is not at the start of the body
    }

    Invalid(int value) {
    }
}
```

### 7.2. `super(...)` calls the superclass constructor

```java
class Vehicle {
    final String brand;

    Vehicle(String brand) {
        this.brand = brand;
    }
}

class Car extends Vehicle {
    final int seats;

    Car(String brand, int seats) {
        super(brand);
        this.seats = seats;
    }
}
```

With `new Car("Honda", 4)`, the `Car(String, int)` constructor needs to call `Vehicle(String)` to initialize the superclass's portion of the state before continuing to initialize `Car`'s own part.

If you write neither `this(...)` nor `super(...)`, the compiler normally inserts an **implicit `super();`** into the constructor (including a generated default constructor). This compiles only when the superclass has an accessible no-argument constructor. The following example is **invalid**:

```java
class Parent {
    Parent(int number) {
    }
}

class Child extends Parent {
    Child() {
        // Implicit super() fails because Parent has no Parent()
    }
}
```

Fix it to:

```java
class Child extends Parent {
    Child() {
        super(1);
    }
}
```

The two versions of the `Child` declaration are **alternative illustrative options**, not meant to be placed together in the same compilation. When a superclass does not have a zero-argument constructor, call the appropriate `super(arguments)` according to the superclass's contract.

### 7.3. Do not call both `this(...)` and `super(...)` in the same constructor

In Java 17 there is only one first-statement position for an **explicit constructor invocation**, so you cannot write:

```java
class Child extends Parent {
    Child() {
        this(1);
        super(1);              // WRONG: cannot have two such invocations
    }

    Child(int value) {
        super(value);
    }
}
```

If `Child()` calls `this(1)`, the `Child(int)` constructor is invoked and then calls `super(value)` itself. This is **a conceptually valid chain**: you neither need nor are allowed to insert an extra `super(...)` after `this(...)`.

**Do not create a constructor loop**:

```java
class Loop {
    Loop() {
        this(1);
    }

    Loop(int value) {
        this();                 // WRONG: recursive constructor invocation
    }
}
```

Every `this(...)` chain must eventually reach a constructor that completes the necessary superclass constructor call; it cannot loop indefinitely.

## 8. Initialization order during object creation

A constructor is not the entire object initialization process. In a simple case of creating a subclass instance:

1. Memory for the object is allocated and instance fields receive their **default values**.
2. The subclass constructor chain proceeds through `this(...)` or `super(...)` to initialize the superclass; the constructor chain goes up to `Object` according to Java rules.
3. The superclass's **instance field initializers** and **instance initializer blocks** execute in textual order before the superclass constructor body.
4. After the superclass is initialized, the subclass's field initializers and instance initializers run before the subclass constructor body.
5. The subclass constructor body continues running; the `new` expression completes normally and yields a reference value to the object.

A class also undergoes **static initialization** when initialized at the class level; that ordering is a separate matter from each object performing instance initialization.

### Java 17 example: superclass first, subclass second

Save as **`InitializationOrderDemo.java`**:

```java
class Base {
    int baseValue = trace("Base field");

    Base() {
        System.out.println("Base constructor");
    }

    static int trace(String text) {
        System.out.println(text);
        return 1;
    }
}

class Derived extends Base {
    int derivedValue = trace("Derived field");

    Derived() {
        super();
        System.out.println("Derived constructor");
    }
}

public class InitializationOrderDemo {
    public static void main(String[] args) {
        new Derived();
    }
}
```

Commands:

```bash
javac -encoding UTF-8 InitializationOrderDemo.java
java InitializationOrderDemo
```

**Exact stdout:**

```text
Base field
Base constructor
Derived field
Derived constructor
```

This is the order observed from field initialization and the execution of superclass/subclass constructors. The static method `trace` only helps print a line when a field initializer runs; it does not add a new constructor.

**Practical note:** avoid calling overridable instance methods from a constructor if those methods depend on subclass state that has not finished initializing. A superclass constructor can run before the subclass's field initializers, causing an overridden method call to observe an incomplete state.

## 9. Constructor accessibility

A constructor can declare an access modifier:

- **`public`:** can be called from code that has access to the class and satisfies the relevant module/package/classpath conditions.
- **`protected`:** permits access forms within the same package and according to `protected` access rules when subclassing from another package.
- **No modifier (package-private):** accessible only from code within the same package as permitted by the language.
- **`private`:** restricts invocation to the scope of the type and contexts permitted by Java; commonly used to control how instances are created.

Example:

```java
public class Service {
    private final String name;

    public Service(String name) {
        this.name = name;
    }

    private Service() {
        this("Mặc định");
    }

    public String name() {
        return name;
    }
}
```

If saved as `Service.java`, the `Service(String)` constructor is public while `Service()` is private. Code inside the `Service` class can call `new Service()` if needed; code in another class cannot call the private constructor merely because the `Service` class is declared `public`.

**A public class does not mean its constructors are automatically public.** If you write `public class User { User() {} }`, the `User()` constructor is **package-private**, so code from another package cannot call `new User()`.

### 9.1. Private constructor for a factory

Save as **`FactoryDemo.java`**:

```java
final class Ticket {
    private final int code;

    private Ticket(int code) {
        this.code = code;
    }

    static Ticket of(int code) {
        if (code <= 0) {
            throw new IllegalArgumentException("code must be positive");
        }
        return new Ticket(code);
    }

    int code() {
        return code;
    }
}

public class FactoryDemo {
    public static void main(String[] args) {
        Ticket ticket = Ticket.of(12);
        System.out.println(ticket.code());

        // new Ticket(12); // WRONG here: constructor is private
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 FactoryDemo.java
java FactoryDemo
```

Stdout:

```text
12
```

`Ticket.of(12)` is a static factory method allowed to call the private constructor from **inside the `Ticket` class**. External code only uses the factory, so object creation logic is controlled and can be changed in the future.

### 9.2. Private constructor in a utility class

A class containing only static methods can often use a private constructor to prevent meaningless instantiation:

```java
final class TextUtils {
    private TextUtils() {
        throw new AssertionError("No instances");
    }

    static String upper(String input) {
        return input.toUpperCase();
    }
}
```

This is an illustrative declaration snippet without `main`. `TextUtils.upper("java")` can be called wherever permitted, whereas `new TextUtils()` from code outside `TextUtils` is rejected due to `private` access.

A private constructor does **not** automatically make a class immutable or a singleton; those are separate design decisions.

## 10. Constructors can use `throws` and validate data

A constructor can throw an exception if it cannot create a valid object:

```java
class Temperature {
    private final double celsius;

    Temperature(double celsius) {
        if (Double.isNaN(celsius)) {
            throw new IllegalArgumentException("Temperature is NaN");
        }
        this.celsius = celsius;
    }

    double getCelsius() {
        return celsius;
    }
}
```

If a constructor throws an exception before completing, the object creation expression **does not complete normally** and the caller does not receive a result from `new` as in the successful case. For a constructor using a **checked exception**, the author must declare/follow exception handling rules.

Example of `throws` syntax:

```java
class Config {
    Config(String file) throws java.io.IOException {
        if (file == null) {
            throw new java.io.IOException("File path is null");
        }
    }
}
```

This illustrative snippet checks for a `null` path rather than performing a file read operation. Because the constructor declares the checked exception `IOException`, callers of `new Config(...)` must handle it with `try/catch` or propagate it according to Java rules.

A constructor can also call methods for validation, but you should be careful about letting `this` “escape” outside before the object is fully initialized—for example, registering the object with a callback or another thread right inside the constructor. That can expose an incomplete state to external code.

## 11. `return` in a constructor: what is allowed and what is not?

A constructor **does not declare a return type**, but it can use **`return;` without an expression** to exit the constructor body early when valid.

Example:

```java
class Flag {
    boolean enabled;

    Flag(boolean enabled) {
        this.enabled = enabled;
        if (!enabled) {
            return;             // Valid: ends the constructor body
        }
        System.out.println("Enabled");
    }
}
```

`new Flag(false)` still creates a `Flag` object with `enabled == false`; `return;` does not “return false”, does not destroy the object, and does not change the nature of a constructor. It is simply an early-exit statement.

You **cannot** use `return expression;` in a constructor:

```java
class InvalidReturn {
    InvalidReturn() {
        // return this;  // WRONG: a constructor cannot return a value
        // return 1;     // WRONG
    }
}
```

If you need to **return an object based on selection logic**, use a static factory method with a return type:

```java
class Result {
    private Result() {
    }

    static Result create() {
        return new Result(); // Method returns Result; the constructor still has no return type
    }
}
```

**For blank final fields**, Java also checks the *definite assignment* rule: every constructor path that can complete normally must validly assign the blank final instance fields. You cannot place `return;` on a branch that leaves a required final field uninitialized.

## 12. Modifiers that do not apply to constructors

Having valid access modifiers does not mean you can place just any modifier before a constructor.

| Keyword / form | Regular constructor | Why |
| --- | --- | --- |
| `public`/`protected`/`private` or omitted | **Valid** depending on context | Controls accessibility |
| `static` | **Invalid** | A constructor is tied to instance creation, not a static method |
| `final` | **Invalid** | Constructors cannot be overridden, so there is no concept of a final constructor |
| `abstract` | **Invalid** | A constructor must have a body; it is not an abstract method |
| `synchronized` | **Invalid** | Synchronized constructors cannot be declared |
| `native` | **Invalid** | A constructor has its own syntax and body, and is not a native method |
| `void` or any return type | **No longer a constructor** | If the name matches the class and there is a return type, it is a method; missing valid parts causes an error |
| `throws SomeException` | **Valid** | A constructor can declare exceptions |
| `<T>` before the constructor name | **Can be valid** | A constructor can declare a type parameter |

**Invalid** declarations:

```java
class BadConstructors {
    // static BadConstructors() { }       // WRONG: constructors cannot be static
    // final BadConstructors() { }        // WRONG: constructors cannot be final
    // abstract BadConstructors();        // WRONG: constructors cannot be abstract
    // synchronized BadConstructors() { } // WRONG: constructors cannot be synchronized
}
```

This cannot be resolved by reordering the modifiers: `static BadConstructors()` and `BadConstructors()` are not two different kinds of constructors. Remove the invalid modifier or move the behavior into a **method** if the actual need is to create a static/final/abstract member.

### 12.1. Generic constructors are valid

A constructor can declare its **own** generic type parameter, even when the class is not generic:

```java
class Holder {
    final String value;

    <T> Holder(T input) {
        this.value = String.valueOf(input);
    }
}
```

With `new Holder(123)`, the constructor `<T> Holder(T input)` receives an `Integer` value after boxing; the `value` field receives the string `"123"`. `<T>` is the constructor's type parameter, **not a return type**.

A generic constructor must be distinguished from the syntax `public <T> T create(T value)`: that has a return type `T`, so it is a **generic method**, not a constructor.

## 13. Constructors in inheritance: not inherited and not overridden

A subclass **does not inherit** constructors from its superclass, even though a subclass constructor can call a superclass constructor.

```java
class Parent {
    Parent(int value) {
        System.out.println("Parent: " + value);
    }
}

class Child extends Parent {
    Child(int value) {
        super(value);
        System.out.println("Child: " + value);
    }
}
```

`Child(int)` is **not** an override of `Parent(int)`. These are **two distinct constructors**, each bearing the name of its own declaring class and playing its role in the initialization chain.

If `Child` declares no constructor while `Parent` only has `Parent(int)`, `Child`'s default constructor will attempt to use `super()` and cause a **compilation error** because `Parent()` does not exist.

Constructors also cannot be invoked using regular method syntax:

```java
Child child = new Child(5);
// child.Child(5); // WRONG: a constructor is not an instance method that can be called again
```

If you need to “reset the state” of an object after creation, design a separate method such as `reset(...)` or create a new object instead of trying to call the constructor again.

**Inheritance rules and compile-time constructor selection:** `new Child(5)` is an expression requesting the matching `Child` constructor. Inside that constructor there may be `super(5)`, selected according to the rules for calling a superclass constructor. This is not dynamic dispatch to an “overridden” constructor at runtime.

## 14. Commonly confused cases: abstract class, enum, and record

### 14.1. An abstract class still has constructors

You cannot instantiate an abstract class directly with `new`, but its constructor **still exists** to initialize the state belonging to the abstract superclass when creating a subclass instance.

```java
abstract class Shape {
    final String color;

    Shape(String color) {
        this.color = color;
    }

    abstract double area();
}

class Square extends Shape {
    final double side;

    Square(String color, double side) {
        super(color);
        this.side = side;
    }

    @Override
    double area() {
        return side * side;
    }
}
```

`new Square("red", 3)` is valid; `new Shape("red")` is invalid because `Shape` is abstract. The `Shape(String)` constructor is invoked via `super(color)` in the `Square` constructor.

### 14.2. An enum has constructors but cannot be instantiated with `new` from outside

An enum can have a constructor to initialize data for its enum constants:

```java
enum Level {
    LOW(1),
    HIGH(2);

    private final int priority;

    Level(int priority) {
        this.priority = priority;
    }

    int priority() {
        return priority;
    }
}
```

The constants `LOW` and `HIGH` create enum instances according to Java rules. You cannot write `new Level(1)` in application code to create a new enum constant. Enum constructors have their own restrictions, such as not being allowed to be declared `public` or `protected`.

### 14.3. Records have canonical constructors and compact constructors

Java 17 supports `record` with a specialized constructor syntax:

```java
record Point(int x, int y) {
    Point {
        if (x < 0 || y < 0) {
            throw new IllegalArgumentException("Tọa độ âm");
        }
    }
}
```

`Point { ... }` is a **compact canonical constructor** of the `Point` record: this is a special syntactic form permitted by Java for records, not a method missing a return type. Parameters corresponding to the record components are provided according to language rules, and Java performs the necessary field assignments after the compact constructor body.

For a regular class, you cannot replace the `Point(int x, int y)` constructor declaration with the `Point { ... }` syntax above. When learning constructors, distinguish between **regular classes** and **special type kinds** such as enums and records.

## 15. Common errors and how to fix them

| Symptom | Cause | Fix |
| --- | --- | --- |
| `void Person()` does not run on `new Person()` | This is a method named `Person`, not a constructor | Remove `void` if the goal is initialization |
| `employee()` is not treated as an `Employee` constructor | Case mismatch with the class name | Name it `Employee()` |
| `new Account()` reports no matching constructor exists | The class only declares `Account(int)`; a default no-arg constructor is not generated | Write `Account()` explicitly or call `new Account(value)` |
| Subclass constructor reports an error on `super()` | The superclass has no accessible no-arg constructor | Call the appropriate `super(arguments)` as the first statement |
| `this(...)` placed after a print statement | Java 17 requires explicit constructor invocation at the start of the body | Move `this(...)` to the top or restructure |
| Both `this(...)` and `super(...)` appear in one constructor | Two invocations compete for the same position | Use `this(...)` to delegate through a final constructor that calls `super(...)` |
| Compiler reports recursive constructor invocation | Constructors call each other in a cycle via `this(...)` | Break the cycle; create a valid terminating chain |
| `new Child(5)` does not automatically invoke the `Parent(int)` constructor | Superclass constructors are not inherited | Declare a `Child(int)` constructor that calls `super(5)` |
| `static User()` or `final User()` is invalid | Constructors do not accept those modifiers | Remove the modifier or write a method according to your intent |
| `return new User();` inside a constructor | Constructors do not return values | Use a static factory method returning `User` |
| `private User()` prevents outside code from calling `new User()` | Constructor accessibility is restricted | Provide a public factory or a constructor with an appropriate access level |
| Blank final field assignment missing on a branch | Definite assignment rules | Ensure final fields are validly assigned along every path where the constructor completes normally |
| Calling an overridable method from a constructor produces unexpected results | The subclass has not initialized all of its state when the superclass constructor runs | Avoid dynamic dispatch into behavior that depends on incomplete state |
| File name does not match the public class containing the constructor | File naming constraint for public top-level classes | Name the file `ClassName.java`, not based on a method name |

`javac` messages can vary across JDK versions. When troubleshooting errors, check the **class name**, **presence or absence of a return type**, **parameter list**, **accessibility**, **superclass constructor**, and **placement of `this(...)`/`super(...)`**.

## 16. Practice exercises with answers

### Question 1. Which is a constructor and which is a method?

```java
class Sample {
    Sample() { }
    void Sample(int value) { }
    int getValue() { return 1; }
}
```

**Answer:** `Sample()` is a constructor. `void Sample(int value)` is a **`void` method with the same name as the class**, not a constructor. `getValue()` is a method returning `int`. Because an explicit `Sample()` constructor already exists, Java no longer generates a default constructor.

### Question 2. Which part runs when creating an object?

```java
class Greeter {
    Greeter() {
        System.out.println("constructor");
    }

    void greet() {
        System.out.println("method");
    }
}
```

With:

```java
Greeter item = new Greeter();
item.greet();
```

**Stdout:**

```text
constructor
method
```

The constructor runs during `new Greeter()`. The `greet()` method runs because it is explicitly called on the next line.

### Question 3. Is there a default constructor?

```java
class Size {
    Size(int value) {
    }
}
```

**Answer:** **No**. An explicit constructor already exists, so `new Size()` is invalid. To support it, add `Size() { this(0); }` or call `new Size(0)`.

### Question 4. Can a constructor return a different object?

**Answer:** You cannot write `return other;` inside the constructor of a regular class. If the goal is to select and return an existing instance, create a **static factory method** returning that class type. The expression `new Type(...)` provides a reference to the created object, but a constructor has no return type.

### Question 5. Which lines are valid constructor chaining?

```java
class Base {
    Base(int code) {
    }
}

class Derived extends Base {
    Derived() {
        this(1);
    }

    Derived(int code) {
        super(code);
    }
}
```

**Answer:** Valid in Java 17. `new Derived()` goes from `Derived()` to `Derived(int)` via `this(1)`, and then to `Base(int)` via `super(code)`. There is no cycle, and each explicit constructor invocation appears at the start of the body.

### Question 6. Fix the `final` field initialization error

```java
class Task {
    final String id;

    Task(boolean enabled) {
        if (enabled) {
            id = "ACTIVE";
        }
    }
}
```

**Answer:** It fails because if `enabled == false`, the blank final field `id` may remain unassigned when the constructor completes normally. One way to fix it:

```java
class Task {
    final String id;

    Task(boolean enabled) {
        id = enabled ? "ACTIVE" : "INACTIVE";
    }
}
```

Note that these are **two alternative versions** of the `Task` class; do not place both in the same package at the same time when compiling.

### Question 7. Interpreting the meaning of `new`

```java
class Box {
    Box() {
    }

    static Box make() {
        return new Box();
    }
}
```

**Answer:** `Box()` is a constructor and does not return a value in Java syntax. `make()` is a **static method** with return type `Box`; the statement `return new Box();` returns to the caller the reference obtained from the `new Box()` expression. It is not “the constructor returning Box”.

## 17. Checklist when declaring a Java constructor

1. **Does the name match the class name** exactly? Java is case-sensitive.
2. **Did you accidentally write `void` or a return type**? If so, it is not a constructor.
3. **Which parameters does the constructor accept**? Do you need multiple overloads or a no-arg constructor?
4. **If the class writes no constructors**, a default constructor can be supplied by the compiler; **if you have already written a constructor**, you must add any other overloads yourself if desired.
5. **Can the constructor be called from the intended scope**? Check `public`, `protected`, package-private, or `private`.
6. **If the class has a superclass**, which superclass constructor needs to be called? Is there an accessible no-arg `super()`?
7. **Java 17:** explicit `this(...)` or `super(...)` calls must appear at the **start of the constructor body** and must not form a cycle.
8. **Have `final` fields** been validly assigned on every initialization path that completes normally?
9. **Are there errors during data validation**? A constructor can throw an exception to prevent object creation from completing normally.
10. **Do not use method modifiers on constructors** such as `static`, `abstract`, `final`, or `synchronized`.
11. **Do not call a constructor again using dot notation** such as `object.ClassName()`; if you need to reset state, create another method.
12. **Do not confuse constructor chaining with overriding**: superclass constructors are not inherited, and calling `super(...)` serves to initialize the superclass portion.

## Key takeaways

- A constructor is the component that initializes an object: **`ClassName(parameters) { ... }`**, with a **name matching the class** and **no return type**.
- Methods always declare a return type or `void`; **`void ClassName()` is still a method**, not a constructor.
- `new Type(...)` creates/initializes an object and yields a reference if successful; it does **not** mean the constructor has return type `Type`.
- Constructors are **overloaded**, but **not inherited or overridden**.
- A default no-arg constructor is provided by the compiler only when **there are no explicit constructors**; a no-arg constructor declared by the programmer is a different concept.
- In **Java 17**, explicit `this(...)` and `super(...)` must be at the start of the constructor body; the call chain helps initialize the same object according to superclass rules.
- A constructor can declare an access modifier, parameters, `throws`, validate data, and update fields; do not use `static`, `final`, or `abstract` as constructor modifiers.
