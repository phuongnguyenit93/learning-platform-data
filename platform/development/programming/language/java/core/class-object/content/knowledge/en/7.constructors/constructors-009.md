# Constructor Access and Preventing External Object Creation in Java

In Java, a **constructor** determines how an object is initialized. Like fields and methods, a constructor has an **access level**, which affects which code locations are **allowed to call that constructor**. If developers do not want external code to freely write `new ClassName(...)`, they can **restrict constructor access**, most commonly to `private` or package-private, and provide a controlled object-creation method when needed.

Example:

```java
public final class Account {
    private final String owner;

    private Account(String owner) {
        this.owner = owner;
    }

    public static Account open(String owner) {
        return new Account(owner);
    }

    public String owner() {
        return owner;
    }
}
```

With this example, code outside `Account` **cannot call** `new Account("An")` under normal access rules, but it can call `Account.open("An")`. The `open` method runs **inside** the `Account` class, so it is allowed to call the `private` constructor.

Lesson objectives: distinguish between `public`, `protected`, package-private, and `private` on constructors; understand the limits of `new` from different scopes; know how to properly design factories, utility classes, and singletons; recognize compilation errors; and understand precisely what **preventing external object creation** means.

## 1. What Is Constructor Access?

A constructor declaration has the basic form:

```java
[public | protected | private] ClassName(parameters) {
    // Initialize the object
}
```

This is a **syntax diagram**, not a literal compilable Java snippet. You can **omit the access modifier** so the constructor has **package-private** access. You cannot use the `default` keyword to declare "default access".

For a regular class constructor, the four options are:

| Declaration | Access Level | Practical Meaning |
| --- | --- | --- |
| `public Person()` | `public` | Allows code that has visibility to the class to call the constructor, subject to module restrictions and other Java rules |
| `protected Person()` | `protected` | Allows calls within the same package; supports calling the superclass constructor in valid inheritance cases from another package |
| `Person()` | Package-private | Allows calls from the same package, including classes in other files; not exposed to other packages |
| `private Person()` | `private` | Restricts calls to the type's scope and contexts permitted by Java; external code normally cannot call it |

**Two things must be checked independently:**

1. **Is the class accessible?** For example, if a top-level `class Person` is not `public`, code in another package cannot directly use that type name.
2. **Is the chosen constructor accessible?** A `public class Person` can still provide only `private` or package-private constructors.

Making a class `public` **does not automatically make the constructors you declare `public`**. The syntax `new Person(...)` must satisfy the access rules for the type, the constructor, and the overload/argument conditions.

## 2. Comparison Table of Constructor Call Scopes

Consider a `Base` class in package `core` and code that wants to call one of its constructors:

| Call Location | `public` | `protected` | Package-private | `private` |
| --- | --- | --- | --- | --- |
| Inside the class declaring the constructor | Yes | Yes | Yes | Yes |
| Another class in the same package | Yes | Yes | Yes | No, except in special access contexts permitted by the language |
| Unrelated class in another package | Yes, if the type is accessible | No | No | No |
| Subclass constructor in another package calling `super(...)` | Yes | Yes | No | No |
| Subclass code in another package writing `new Base(...)` directly | Yes, if the type is accessible | **No, not merely because it is a subclass** | No | No |

The table describes typical situations for non-nested classes without special access mechanisms. The most important point to remember is that **`protected` does not mean "any code in a subclass can freely write `new Base(...)`"**. In another package, a subclass is generally allowed to call a `protected` parent constructor **to initialize the superclass part** via `super(...)`, but it is not automatically allowed to create an independent parent object via `new Base(...)`.

For `private`, Java permits access in contexts within the same type and among certain nested types/nestmates according to language rules. Therefore, saying "private can only be used strictly in lines of code inside one object" is too narrow a phrasing. In the standalone examples in this lesson, understand `private constructor` primarily as preventing code in **unrelated classes** from calling it directly.

## 3. `public constructor`: An API Allowing Direct Object Creation

Example of a class with a public constructor:

**File `src/model/Student.java`**

```java
package model;

public class Student {
    private final String name;

    public Student(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên trống");
        }
        this.name = name;
    }

    public String getName() {
        return name;
    }
}
```

**File `src/app/Main.java`**

```java
package app;

import model.Student;

public class Main {
    public static void main(String[] args) {
        Student student = new Student("An");
        System.out.println(student.getName());
    }
}
```

Compile and run with JDK 17+ from the directory containing `src`:

```bash
javac -encoding UTF-8 -d out src/model/Student.java src/app/Main.java
java -cp out app.Main
```

Stdout:

```text
An
```

Here:

- `Student` is a `public` top-level type, so `app.Main` can use the type `model.Student` when the classpath and other conditions are appropriate.
- `Student(String name)` is a `public` constructor, so calling `new Student("An")` from package `app` is valid.
- The `name` field is `private`, so `app.Main` cannot read `student.name` directly; it uses the `getName()` method.
- The constructor still performs data validation. `public` only allows **calling from outside**; it does not mean the constructor must accept every input value.

**When to use:** data types where direct object creation is straightforward, there is no need to control where instances come from, and the constructor fully expresses the object's invariant conditions.

## 4. Package-Private Constructor: Allowing Object Creation Within the Same Package

Omit the access modifier before the constructor name:

```java
package library;

public class Book {
    private final String title;

    Book(String title) {     // package-private constructor
        this.title = title;
    }

    public static Book of(String title) {
        return new Book(title);
    }

    public String title() {
        return title;
    }
}
```

Because `Book` is `public` while `Book(String)` is **not** `public`, code in another package can know about `Book` yet still **cannot** write `new Book("Java")`.

### 4.1. A Runnable Example Across Two Packages

**File `src/library/Book.java`**

```java
package library;

public class Book {
    private final String title;

    Book(String title) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("title is blank");
        }
        this.title = title;
    }

    public static Book of(String title) {
        return new Book(title);
    }

    public String title() {
        return title;
    }
}
```

**File `src/app/Main.java`**

```java
package app;

import library.Book;

public class Main {
    public static void main(String[] args) {
        Book book = Book.of("Java Core");
        System.out.println(book.title());

        // Book other = new Book("Advanced");
        // INVALID if uncommented: the Book(String) constructor is not public.
    }
}
```

Commands:

```bash
javac -encoding UTF-8 -d out src/library/Book.java src/app/Main.java
java -cp out app.Main
```

Stdout:

```text
Java Core
```

In the same `library` package, a class **in a different file** can still call `new Book("Java")` because a package-private constructor allows code in the same package to use it. However, `app.Main` in another package must use `Book.of(...)` or another public API.

**Note:** packages are determined by the `package` declaration, not merely by whether classes are in the same directory or different files. A package-private constructor is a good choice for **internal code within the same package**, not an absolute security mechanism against all forms of runtime interference.

## 5. `protected constructor`: Supporting Controlled Inheritance

`protected` on a constructor has two typical benefits:

- Classes in the **same package** can call the constructor according to package access rules.
- Subclasses in **another package** can call the superclass's `protected` constructor via `super(...)` to perform initialization.

Example with two packages:

**File `src/core/Vehicle.java`**

```java
package core;

public class Vehicle {
    private final String brand;

    protected Vehicle(String brand) {
        this.brand = brand;
    }

    public String brand() {
        return brand;
    }
}
```

**File `src/app/Car.java`**

```java
package app;

import core.Vehicle;

public class Car extends Vehicle {
    public Car(String brand) {
        super(brand); // Valid: calls the superclass's protected constructor
    }
}
```

**File `src/app/Main.java`**

```java
package app;

import core.Vehicle;

public class Main {
    public static void main(String[] args) {
        Car car = new Car("Toyota");
        System.out.println(car.brand());

        // Vehicle vehicle = new Vehicle("Honda");
        // INVALID: app.Main cannot call the protected constructor directly.
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 -d out src/core/Vehicle.java src/app/Car.java src/app/Main.java
java -cp out app.Main
```

Stdout:

```text
Toyota
```

Key point: **`app.Car` can extend `core.Vehicle`** and use `super(brand)` even though `Vehicle`'s constructor is not public. However, that does not expose `new Vehicle("Honda")` to all code outside `core`.

A subclass can write a `public` constructor so users can instantiate **subclass objects**, but doing so does not automatically make the parent constructor `public`.

### 5.1. `protected` Is Not "Private Exclusively for Subclasses"

Unlike `private`, a `protected` constructor allows **any other class in the same package** to call it under package access, not only subclasses. Therefore, if the requirement is that **no one other than the class itself and related nested code** can call it, `protected` does not satisfy that.

In another package, `protected` has subtle access rules: calling the constructor via `super(...)` in a subclass is allowed; using `new Base(...)` to create an independent `Base` object is not automatically allowed simply because the line of code is inside a subclass. Certain syntax forms involving anonymous classes have their own rules; when learning the fundamentals, use `super(...)` to express the intent of calling the parent constructor.

### 5.2. Abstract Classes Still Need Constructors

An abstract class cannot be instantiated directly with `new AbstractType()`, yet it still needs a constructor to initialize superclass state:

```java
abstract class Shape {
    private final String color;

    protected Shape(String color) {
        this.color = color;
    }

    String color() {
        return color;
    }

    abstract int area();
}

final class Square extends Shape {
    private final int side;

    Square(String color, int side) {
        super(color);
        this.side = side;
    }

    @Override
    int area() {
        return side * side;
    }
}
```

`protected Shape(String)` is appropriate when you want subclasses to initialize the shared part without turning the superclass into a directly instantiable type (here `Shape` itself is also `abstract`).

**Do not confuse them:** `abstract` restricts **creating instances of the class**, whereas `protected` restricts **where the constructor can be called**. The two mechanisms complement each other.

## 6. `private constructor`: Preventing External Code from Making Normal `new` Calls

Declaration:

```java
class Secret {
    private Secret() {
    }
}
```

Code belonging to a separate class outside `Secret` cannot write `new Secret()` under normal Java access rules, even if that class is in the same package.

Software may use a private constructor for several purposes:

1. **Controlling the object-creation path** via a static factory method.
2. **Preventing instantiation** of a utility class that contains only static methods.
3. **Limiting the number of instances** according to a specific design, such as a singleton or cache—this requires additional logic, not just `private`.
4. **Forcing inputs to be validated** or normalized before creation.
5. **Hiding an implementation class** inside the type's own factory API.

`private` is a **language-level access rule** for constructor calls. It does not by itself guarantee that "nobody can ever create an object" under all mechanisms such as reflection, serialization, instrumentation, or runtime manipulation tools; the notes at the end of this lesson will make the distinction clear.

## 7. Standard Example: Private Constructor + Public Static Factory

Suppose an account object requires a non-negative initial balance. We want callers to create an account through a clear API instead of calling the constructor directly.

Save the entire program as **`AccountFactoryDemo.java`**:

```java
final class Account {
    private final String owner;
    private int balance;

    private Account(String owner, int balance) {
        this.owner = owner;
        this.balance = balance;
    }

    static Account open(String owner, int initialBalance) {
        if (owner == null || owner.isBlank()) {
            throw new IllegalArgumentException("owner must not be blank");
        }
        if (initialBalance < 0) {
            throw new IllegalArgumentException("negative balance");
        }
        return new Account(owner, initialBalance);
    }

    String owner() {
        return owner;
    }

    int balance() {
        return balance;
    }

    void deposit(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("deposit must be positive");
        }
        balance = Math.addExact(balance, amount);
    }
}

public class AccountFactoryDemo {
    public static void main(String[] args) {
        Account account = Account.open("An", 100);
        account.deposit(50);

        System.out.println(account.owner());
        System.out.println(account.balance());

        // new Account("An", 100);
        // INVALID if uncommented: the Account(String, int) constructor is private.
    }
}
```

Compile/run with JDK 17+:

```bash
javac -encoding UTF-8 AccountFactoryDemo.java
java AccountFactoryDemo
```

**Exact stdout:**

```text
An
150
```

Analysis:

- `Account` is a package-private top-level class with a **private constructor**.
- `open(...)` is a **static factory method**. It is **not a constructor** because it has a return type of `Account`, a chosen name `open`, and is declared `static`.
- When a caller invokes `Account.open(...)`, data validation happens before the `new Account(...)` statement.
- The constructor still handles initializing the fields after the factory has verified that the data is valid.
- `deposit` is an instance method that modifies the state of **an already created object**, not a new constructor.
- Code outside `Account` cannot directly call the `private` constructor even in the same package.

Here the `open` factory has only package-private access to suit a single-file example. If you want an API for other packages, you typically declare **`public class Account`** in **`Account.java`** and **`public static Account open(...)`**, keeping the constructor `private`. External callers can be given access to the class and factory while being prevented from directly calling `new Account(...)`.

### 7.1. Constructor Call Access Differs from Factory Call Access

In the example above, `Account.open(...)` is a **static method** and can have a different access level from the `private Account(...)` constructor. Thus, code outside the class can use a permitted object-creation API while **not** being allowed to call `new Account(...)` directly. A factory has a chosen name and a return type; a constructor must have the same name as the class and declares no return type.

This access relationship is the key point here: **restricting a constructor does not mean prohibiting all ways of creating or using an object**. More advanced capabilities of factories (expressive naming, caching/reuse, returning subtypes/interfaces, trade-offs, and comparisons with public constructors) are analyzed thoroughly in the lesson **"Named Object-Creation Methods and Comparison with Constructors"**.

## 8. Unable to Create Instances from Outside, Yet Still Able to Use the Object

Restricting constructor calls **does not mean the class's objects cannot be used**. A public factory or another API can provide the object to callers:

```java
public final class Session {
    private final String token;

    private Session(String token) {
        this.token = token;
    }

    public static Session create(String token) {
        return new Session(token);
    }

    public String token() {
        return token;
    }
}
```

If saved as **`Session.java`** in an appropriate package, a caller can write:

```java
Session session = Session.create("abc");
System.out.println(session.token()); // abc
```

However, calling `new Session("abc")` from another independent class is not allowed because the constructor is private.

**Distinguish three different permissions**:

- **Seeing the type name `Session`**: depends on class access.
- **Receiving/holding a `Session` reference**: can happen via the return value of a valid API.
- **Creating a new instance through the `Session(...)` constructor**: depends specifically on constructor access.

An object can still be used through an interface or superclass visible to the caller, even when the concrete implementation class is hidden. This is the foundation of "program to an interface" and factory design.

## 9. Utility Classes: Private Constructors to Prevent Accidental `new`

A **utility class** simply groups static methods or constants that do not need per-object state. For example, `Math` in the standard library has `static` methods such as `Math.max`.

Save **`UtilityDemo.java`**:

```java
final class TextUtil {
    private TextUtil() {
        throw new AssertionError("No instances");
    }

    static String normalize(String input) {
        if (input == null) {
            return "";
        }
        return input.trim().toLowerCase(java.util.Locale.ROOT);
    }
}

public class UtilityDemo {
    public static void main(String[] args) {
        System.out.println(TextUtil.normalize("  JAVA Core  "));

        // TextUtil util = new TextUtil();
        // INVALID if uncommented: private constructor.
    }
}
```

Commands:

```bash
javac -encoding UTF-8 UtilityDemo.java
java UtilityDemo
```

Stdout:

```text
java core
```

Explanation:

- `TextUtil.normalize` is a static method, so you do not need `new TextUtil()` to call it.
- `private TextUtil()` blocks normal creation of a utility object from another class.
- `final class TextUtil` prevents subclassing the utility class.
- `throw new AssertionError("No instances")` inside the constructor is an extra defensive option in case the constructor is accidentally called from inside the class. It is not required for `private` to take effect.
- `java.util.Locale.ROOT` prevents results from changing due to the environment's locale when calling `toLowerCase`.

**A common misconception:** declaring methods as `static` **does not automatically make a class non-instantiable**. If no constructor is declared, a regular class can receive a compiler-generated default constructor. To prevent `new` calls from external code, explicitly declare a private constructor or choose an appropriate design.

## 10. Private Constructor and Singleton: Not Automatically Equivalent

A **singleton** is a design pattern aimed at providing a single shared instance within a predefined management scope. A private constructor **only restricts normal instantiation paths**; without an instance being created and an API returning that instance, it does not automatically create a singleton.

A simple way to write one, using eager initialization:

Save as **`SingletonDemo.java`**:

```java
final class Settings {
    private static final Settings INSTANCE = new Settings();

    private int level;

    private Settings() {
        level = 1;
    }

    static Settings getInstance() {
        return INSTANCE;
    }

    int getLevel() {
        return level;
    }

    void setLevel(int level) {
        this.level = level;
    }
}

public class SingletonDemo {
    public static void main(String[] args) {
        Settings first = Settings.getInstance();
        Settings second = Settings.getInstance();

        first.setLevel(3);

        System.out.println(first == second);
        System.out.println(second.getLevel());
    }
}
```

```bash
javac -encoding UTF-8 SingletonDemo.java
java SingletonDemo
```

**Stdout:**

```text
true
3
```

In this example:

- `Settings.INSTANCE` is a `static final` field initialized using the private constructor from **inside `Settings`**.
- `getInstance()` returns the **same reference value** across calls.
- Reassigning a reference variable in the caller does not change the shared instance; modifying `level` through one reference is visible through the other reference.
- `final class Settings` blocks subclassing, but does not automatically make its data immutable or thread-safe.
- The actual "one instance" scope also depends on the class-loading environment, such as different class loaders; careful consideration is needed if special guarantees are required.

### 10.1. Enum Singletons in Appropriate Situations

Java has the **enum singleton** pattern:

```java
enum GlobalCounter {
    INSTANCE;

    private int count;

    int next() {
        return ++count;
    }
}
```

With `GlobalCounter.INSTANCE.next()`, there is no way to call `new GlobalCounter()` from the application. Java enforces specialized guarantees for enums regarding constant creation, serialization, and reflective constructor invocation compared to regular classes.

However, `count++` in the example **is not safe when multiple threads increment concurrently**. An enum singleton helps restrict instance creation through language mechanisms; it **does not automatically make every method thread-safe**. When concurrency is needed, add `AtomicInteger`/synchronization or design immutable state.

Choose a singleton only when there is a genuine reason to need shared state; do not use a singleton merely to avoid passing dependencies in a testable design.

## 11. Private Constructors and Inheritance

A normal subclass must call an accessible superclass constructor, either directly or through constructor chaining. If the superclass only has private constructors and there is no access mechanism for the subclass in an appropriate context, an external class cannot extend that superclass in the normal way.

Example illustrating the error:

```java
class Base {
    private Base() {
    }
}

class Derived extends Base {
    Derived() {
        // Implicit super() cannot access Base().
    }
}
```

The `Derived` class fails to compile because the superclass constructor is not accessible from that context. Simply declaring `Derived()` does not resolve the issue when there is no suitable parent constructor to call.

**If the goal is to allow subclasses while prohibiting direct instantiation of the superclass from outside packages**, a `protected constructor` is typically used, combined with an abstract class if the base class should not be instantiated:

```java
abstract class Base {
    protected Base() {
    }
}

class Derived extends Base {
    Derived() {
        super();
    }
}
```

**If the goal is to forbid subclassing a class**, explicitly use `final class` rather than relying solely on private constructors. The reason is that private access in nested contexts and special mechanisms can make an absolute claim that "a private constructor makes subclasses impossible" inaccurate in all cases.

### Example to Avoid Misunderstanding: A Subclass Does Not "Inherit" Constructors from Its Parent

```java
class Parent {
    protected Parent(int code) {
    }
}

class Child extends Parent {
    Child(int code) {
        super(code);
    }
}
```

The `Child(int)` constructor is **Child's** constructor, not an inherited `Parent(int)` constructor. `super(code)` merely **calls** the superclass constructor as a step in creating `Child`.

## 12. Default Constructor: Default Access Is Not Always `public`

Java has a specific rule when you **declare no constructors**. The compiler supplies a **parameterless default constructor** if the class is of a kind to which this rule applies, with an access level matching the **access level of the class** according to language rules.

Example:

```java
public class PublicBox {
    int value;
}
```

If no special superclass prevents the implicit `super()`, `PublicBox` receives a parameterless default constructor with public access; external code can call `new PublicBox()` if the type is accessible.

Compare:

```java
class PackageBox {
    int value;
}
```

`PackageBox` is top-level package-private; the corresponding default constructor does not expose this type as a public API to other packages.

**However, as soon as you declare any constructor**, Java no longer automatically adds a default no-arg constructor:

```java
public class User {
    private User(String name) {
    }

    public static User create(String name) {
        return new User(name);
    }
}
```

Because `private User(String)` has been declared, Java does not automatically add `public User()`. Moreover, no `User()` constructor is declared. Therefore, external code cannot call `new User()` or `new User("An")`; it can only use `User.create(...)`.

### 12.1. Difference Between a "Default Constructor" and a "No-Arg Constructor"

- A **default constructor** is a constructor **automatically generated by the compiler** when no constructors are declared.
- An **explicit no-arg constructor** is a `Type() { ... }` constructor **written by the developer**, whose access level depends on its own modifier.

Example:

```java
public class Config {
    private Config() {
    }
}
```

The constructor here is an **explicit private no-arg constructor**, not a compiler-generated default constructor. Calling `new Config()` from another class is blocked by `private`; this is a common technique in utilities/factories.

## 13. Differences Between Class, Constructor, and Method Access

Notice three separate declarations:

```java
public final class Report {
    private final String title;

    private Report(String title) {
        this.title = title;
    }

    public static Report of(String title) {
        return new Report(title);
    }

    public String title() {
        return title;
    }
}
```

If saved as `Report.java`:

- `public final class Report`: external code can use the `Report` type if access conditions are met; `Report` cannot be subclassed.
- `private Report(String)`: external code normally cannot call the constructor directly.
- `public static Report of(String)`: external code can request object creation through the factory.
- `public String title()`: external code can read the title through the method.
- `private final String title`: external code cannot read the field directly via `report.title` and cannot reassign the field after initialization.

**Separating these three levels** enables flexible API design: callers see the public type and necessary operations without knowing or directly choosing how instances are created/initialized.

### 13.1. A Private Constructor Does Not Guarantee Every Field or Method Is Private

`private` applies only to **the modified constructor** and does not automatically propagate to the entire class. A class with a private constructor can still contain static/instance public methods, public constants, and other constructors with different access levels if declared by the developer.

Example:

```java
class Token {
    private Token() {
    }

    Token(String value) {
    }
}
```

The `Token()` constructor is private, whereas `Token(String)` is package-private. Another class **in the same package** can still write `new Token("abc")`. Therefore, if the goal is to **prevent any caller outside the type from invoking any `new` path**, you must review **all constructors**, not just one.

## 14. Factory Returning an Interface or Hidden Implementation

A factory can create an object of an implementation class without the calling code needing to know the constructor or even see the concrete type.

Save the file **`ServiceDemo.java`**:

```java
interface MessageService {
    String send(String message);
}

final class ConsoleMessageService implements MessageService {
    private final String prefix;

    private ConsoleMessageService(String prefix) {
        this.prefix = prefix;
    }

    static ConsoleMessageService create(String prefix) {
        return new ConsoleMessageService(prefix);
    }

    @Override
    public String send(String message) {
        return prefix + ": " + message;
    }
}

public class ServiceDemo {
    static MessageService messageService() {
        return ConsoleMessageService.create("INFO");
    }

    public static void main(String[] args) {
        MessageService service = messageService();
        System.out.println(service.send("Hello"));
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 ServiceDemo.java
java ServiceDemo
```

Stdout:

```text
INFO: Hello
```

In this program:

- Calling code holds a reference via **interface `MessageService`**, without needing `new ConsoleMessageService(...)`.
- `ConsoleMessageService` has a private constructor; only the internal static factory is allowed to call it in this example.
- `ServiceDemo.messageService()` decides which implementation type is used and returns the interface.
- To swap in another suitable implementation, you can modify the factory without changing the interface-based API at call sites.

The example above puts the types in a single file for ease of learning. In real projects, developers usually separate the public API, factory, and implementation into appropriate files/packages, especially if the implementation needs to be hidden as package-private.

**There is no requirement that every factory must return the exact type of its enclosing class.** A factory can return an interface, superclass, or another implementation as long as it is compatible with the declared return type.

## 15. Constructors with Multiple Access Levels: Choosing the Right Overload

A class can declare constructors with **different numbers or types of parameters**, each with its own access level:

```java
class Measurement {
    private final double value;

    public Measurement(int value) {
        this.value = value;
    }

    private Measurement(double value) {
        this.value = value;
    }

    static Measurement exact(double value) {
        return new Measurement(value);
    }

    double value() {
        return value;
    }
}
```

If the caller is in the same file/package but **outside the `Measurement` class**, it can call `new Measurement(5)` through the `public` constructor. Directly calling `new Measurement(2.5)` via the `private` constructor is not allowed; use `Measurement.exact(2.5)` instead.

**Point to remember:** each constructor overload has **its own access permission**. It is not true that "one public constructor makes every constructor in the class public".

When designing overloads, especially if there are both private and public constructors, check argument types as well as overload selection rules. Do not rely on "the compiler will automatically fall back to some public overload" if the most specific overload is inaccessible: selection rules and access checks may cause the call to fail. When a clear call path is needed, use a factory or cast intentionally in a way that matches the contract.

## 16. Constructors Are Not Methods: Easily Confused Rules

### 16.1. Constructors Have No Return Type

```java
class Device {
    Device() {            // Constructor
    }

    void Device(int id) { // Method, not a constructor
    }
}
```

`void Device(int)` is a method because it has the `void` keyword before its name. It is not called by `new Device(5)` as a constructor. A constructor must have **the same name as the class and declare no return type**.

### 16.2. Constructors Cannot Be Overridden

A subclass does not override a superclass constructor; it declares a constructor **bearing the subclass's own name** and can then call `super(...)`. Constructors also cannot be marked `static`, `abstract`, `final`, or `synchronized` as some methods can.

### 16.3. Private Constructors Still Run During Valid `new` Calls

`private` does not mean the constructor "does not run". When `Account.open(...)` calls `new Account(...)` from inside `Account`, the constructor executes normally. The restriction is only on **who is allowed to write a valid call**, not a mode that disables the constructor.

### 16.4. `return` in a Constructor Does Not Return an Object

A constructor can use `return;` (with no expression) in valid locations to exit early, but **it cannot write `return new Object();`** to replace the object being initialized. If you need to select/return an existing object, use a **factory method**.

### 16.5. `this(...)` and `super(...)` Must Still Respect Access Rules

In Java 17, an explicit `this(...)` or `super(...)` call must be the first statement in a constructor. `this(...)` calls another constructor in the same class; `super(...)` calls an **accessible** superclass constructor. A parent class's private constructor does not automatically become accessible simply because it appears in a `super(...)` position.

## 17. Practical Limitations of "Preventing External Creation"

Constructor access control is a **checking mechanism within the Java language**. It is very useful for shaping an API, but it is not a security sandbox protecting against every way of interfering with the JVM.

Distinguish between the following:

1. **Normal Java code following compile-time access checks:** a private constructor blocks `new Type(...)` from classes without permission.
2. **Reflection:** certain tools can attempt to access non-public constructors; the ability to bypass access checks depends on module openness, access permissions, and runtime rules. The Java Platform Module System can restrict deep reflection.
3. **Serialization:** with certain object restoration mechanisms, the creation/restoration process does not go through the class's constructor in the same way as a normal `new` expression. Singleton/factory designs may need to consider `readResolve` and other constraints.
4. **Frameworks/ORMs/DI:** these may require a parameterless constructor with an appropriate access level, or use reflection/proxies/bytecode. Do not make every constructor private if the framework in use requires a specific instantiation mechanism.
5. **Class loaders, instrumentation, or privileged code:** these can create situations outside the normal constructor-invocation model. `private` should not be promoted as an absolute security barrier.

**Practical conclusion:** "Preventing external object creation" here means **restricting direct constructor calls via access modifiers**. If stronger guarantees are needed (for example, a singleton regardless of serialization/reflection), you must consider both the object-creation mechanism and the runtime environment, not just add `private`.

## 18. Common Errors and How to Fix Them

| Symptom | Cause | Fix |
| --- | --- | --- |
| `new Account(...)` reports private constructor | Caller cannot access the private constructor | Use a public factory or intentionally adjust the API |
| Class is `public`, but `new Type(...)` from another package fails to compile | The constructor is declared package-private, protected, or private | Check **constructor access**, not only class access |
| `new Book(...)` cannot be called despite using `import` for `Book` | `import` does not change constructor access permissions | Use a public factory or an appropriate constructor |
| `protected` constructor is callable via `super(...)`, but `new Base(...)` fails | `protected` rules differ depending on inheritance context | Only use `super(...)` in a subclass or provide a public API |
| `new Type()` is unexpectedly allowed when no constructor is written | The compiler automatically supplies a default constructor when eligible | Declare a private constructor if you want to restrict external creation |
| Wrote `private Type(int)` while assuming a default `Type()` still exists | An explicit constructor exists, so the compiler does not add a no-arg one | Add an explicit no-arg constructor if needed |
| Only one overload is private, while another public overload can still instantiate | Access permissions belong to each individual constructor | Review all constructors |
| A subclass cannot extend a parent class with a private constructor | Unable to call a superclass constructor | Use an appropriate protected/package-private/public constructor or change the design |
| The factory still allows creating invalid data | A factory does not automatically validate every input | Write data validation and preserve invariants in the factory/constructor |
| Private constructor, yet the class is still subclassed in related nested code | Nested/nestmate rules can grant special access | Use `final class` when you truly want to forbid inheritance |
| Singleton has a private constructor, yet multiple threads update it incorrectly | `private` does not guarantee thread safety | Synchronize or use appropriate concurrent data types |
| Framework cannot instantiate the object | The constructor does not match the access/no-arg contract required by the framework | Follow the framework's contract or provide a factory/adapter |
| `void User()` is mistaken for a constructor | This is a method sharing the class name | Remove `void` if you intend to declare a constructor |
| A `private` constructor prevents another library from using the return type | Callers cannot instantiate directly, which does not mean they cannot **receive an instance** | Expose a factory/API that returns the object with the proper access level |

Specific error messages may vary depending on the JDK, package, module, and chosen signature. When diagnosing issues, start from the constructor declaration, not just the `new` expression.

## 19. Practice Exercises: Predict Access Permissions and Output

### Exercise 1 — Public Class, Private Constructor

```java
public class Card {
    private Card() {
    }

    public static Card issue() {
        return new Card();
    }
}
```

From another class in the same package, which calls are valid?

- `new Card()` → **No**: the constructor is private.
- `Card.issue()` → **Yes**: the public factory executes `new Card()` inside the `Card` class itself.
- Variable declaration `Card card = Card.issue();` → **Yes**: the caller can use the `Card` type and the instance provided by the factory.

### Exercise 2 — Package-Private Constructor

```java
package store;

public class Item {
    Item() {
    }
}
```

**Answer:** `new Item()` is valid from another class **in the same `store` package** when the code is accessible. From package `app`, even after `import store.Item;`, `new Item()` is still **not allowed** because the constructor is package-private.

### Exercise 3 — Protected Constructor and Subclass Outside the Package

Suppose `core.Base`:

```java
package core;

public class Base {
    protected Base() {
    }
}
```

And `app.Child`:

```java
package app;

public class Child extends core.Base {
    public Child() {
        super();
    }
}
```

**Answer:** `new Child()` is valid from anywhere with access to `Child`; `super()` can access the parent's protected constructor. An unrelated class in package `app` cannot call `new core.Base()` directly.

### Exercise 4 — Utility Class

```java
final class NumberUtil {
    private NumberUtil() {
    }

    static int doubleOf(int n) {
        return n * 2;
    }
}
```

**Answer:** `NumberUtil.doubleOf(6)` returns `12` without needing a `NumberUtil` instance. Calling `new NumberUtil()` from another class is invalid because the constructor is private. `final` forbids subclassing the class, while `private` blocks calling the constructor from outside.

### Exercise 5 — Is a Singleton Guaranteed to Be Immutable?

```java
final class Holder {
    static final Holder INSTANCE = new Holder();
    int value;

    private Holder() {
    }
}
```

**Answer:** No. `INSTANCE` is a `static final` reference field, but `INSTANCE.value` can still be modified by code that has access to that field. `static final` does not automatically make the referenced object immutable.

### Exercise 6 — How Do a Constructor and a Factory Differ?

```java
class Message {
    private Message(String value) {
    }

    static Message create(String value) {
        return new Message(value);
    }
}
```

**Answer:** `Message(String)` is a constructor (no return type, same name as the class). `create(String)` is a static method with return type `Message`. `new Message(value)` can only be called in an authorized location such as inside `Message.create`. It is not "a constructor returning Message".

### Exercise 7 — Find the Flaw in the Prediction

Someone says: "Just write `private User()`, and there will never be a `User` instance."

**Answer:** False. Right inside the `User` class, code can call the private constructor and pass the object to callers via a static factory. `private` restricts call paths from outside; it **does not** prohibit object creation in authorized contexts.

## 20. Constructor Access Design Checklist

1. **Does the class have a public API?** If not, you can make the top-level class package-private; you do not necessarily need a public class with a private constructor.
2. **Who needs to call `new` directly?** If external code must instantiate it directly, consider a public constructor; if only internal package code does, use package-private.
3. **Is subclassing from another package needed?** Consider a protected constructor and designing an abstract superclass if appropriate.
4. **Do you want only internal APIs to decide object creation?** Use a private constructor and a factory/entry point with appropriate access.
5. **How many constructor overloads exist?** Check the access of **every constructor** to avoid accidentally exposing an unintended creation path.
6. **Is there an implicit default constructor?** When no constructors are declared, the compiler may add a default constructor. Declare one explicitly to maintain control.
7. **Does the public API have appropriate methods and fields?** Callers can use objects created by a factory even if they cannot call `new` themselves.
8. **Should the class be inheritable?** If you want to block inheritance, mark it `final`; if inheritance is needed, ensure a parent constructor is accessible.
9. **Do the constructor/factory protect invariants?** Check for null, empty data, value ranges, mutable references, and business conditions.
10. **Is a framework involved?** Check no-arg constructor, access, and reflection requirements before hiding constructors.
11. **Is there shared/singleton state?** `private` does not guarantee a single instance or thread safety; add appropriate synchronization/initialization design.
12. **Do the example files have matching packages and file names?** Public/protected/private constructors must appear inside the class declaration; a `public` top-level class must be placed in a source file whose name matches the type in a standard compilation workflow.

## Key Takeaways

- **Constructor access differs from class access**. A `public` type can still disallow external code from calling `new` directly.
- **`public`:** opens constructor calls to code that can access the class; **package-private:** same package only; **`protected`:** same package and valid inheritance contexts; **`private`:** tightly restricts calls.
- **A private constructor does not forbid the class from creating objects itself**. It is commonly combined with a **static factory**, a utility class, or a design that controls object lifecycles.
- **A default constructor** is provided by the compiler when **no constructors are declared**; declaring a private constructor prevents automatic generation of a default constructor.
- **Parent constructors are not inherited**. A subclass must have an accessible way to call a superclass constructor; a protected constructor often serves this purpose.
- **Preventing `new` from outside does not mean objects cannot exist or cannot be used**, nor does it mean absolute security against reflection or serialization.
