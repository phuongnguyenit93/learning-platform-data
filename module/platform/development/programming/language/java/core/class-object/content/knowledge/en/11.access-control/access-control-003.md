# Field, Method, and Constructor Access in Java

**Access control** is the set of Java rules that determines which code is permitted to use a **field**, call a **method**, or invoke a **constructor**. These rules are checked primarily at **compile time**, based on the location of the calling code, the package, inheritance relationships, and the type of the receiving expression (*receiver*).

Java has four common **access levels** for members of a regular class:

1. `public` — grants the broadest access, though it still depends on the accessibility of the **class containing the member**, modules, and related rules.
2. `protected` — allows access to code in the **same package**, while also providing special access for **subclasses in other packages** under specific conditions.
3. **Package-private** — no modifier written; allows access only within the **same package** according to Java rules.
4. `private` — restricts access to the declaring scope and valid contexts such as members of the same *nest*; ordinary independent external class code cannot access it.

Example:

```java
public class Account {
    public String currency = "VND";
    protected String owner = "An";
    int level = 1;                     // package-private
    private long balance = 100;

    public Account() { }

    public void deposit(long amount) {
        balance += amount;
    }

    protected void audit() { }

    void updateLevel() {
        level++;
    }

    private void validate() { }
}
```

Each field, method, and constructor here has its own access level. A `public` class **does not automatically make all of its members public**.

> The goal is not to make everything `public` just to “eliminate errors”, but to create a **minimal, sufficient API**: other code is permitted to do what is necessary, while implementation details and data invariants are protected.

This lesson uses **Java 17+** syntax and behavior, clearly distinguishing illustrative declaration snippets from complete programs that can be compiled and run.

## 1. Scope and the Four Access Levels

Let's start with the summary table below. The table considers **non-nested regular classes** and common cases of instance members and constructors; `protected` from another package is analyzed in detail later.

| Location of code attempting to use the member | `public` | `protected` | Package-private | `private` |
| --- | --- | --- | --- | --- |
| Inside the declaring class itself | Yes | Yes | Yes | Yes |
| Another independent class in the same package | Yes | Yes | Yes | No |
| Unrelated independent class in another package | Yes if the class and API are visible | No | No | No |
| Subclass in another package | Yes if valid | **Yes, conditionally** | No | No |
| Non-subclass code in another package | Yes if valid | No | No | No |

**Important note on `private`:** Modern Java has access rules for **nested classes belonging to the same nest**, so the statement “private can only be read from exactly one class with absolutely no exceptions” is oversimplified. For independent classes, the examples in the table reflect the basic practical situation.

**Note on `protected`:** you cannot simply conclude “being inside a subclass allows reading every `protected` field of any object of the superclass type”. Java has a **condition on the type of the receiver** for certain ways of accessing from another package.

### 1.1. A Package Is the Unit of Access, Not an Arbitrary Directory

`package store;` declares a class belonging to the `store` package. Two classes in different files with the **same package name** have package-private access applied as code in the same package.

`store` and `store.inventory` are **not the same package**: the dotted naming relationship **does not** grant the parent package's package-private or protected access to the subpackage.

Example:

```java
package store;
class Product {
    int stock = 10;
}
```

A class in `package store;` can use `Product` and the `stock` field if other rules are satisfied. However, a class in `package store.inventory;` **does not** automatically have access because the name looks like a “subpackage”.

Placing two files next to each other on disk also does not replace the package declaration and classpath/module structure.

### 1.2. The `default` Keyword Is Not a “Default Access” Modifier

**Package-private** means **writing no access modifier**, for example:

```java
class Student {
    String name;                  // package-private field

    void printName() {            // package-private method
        System.out.println(name);
    }

    Student(String name) {        // package-private constructor
        this.name = name;
    }
}
```

Do not write `default String name;` or `default Student() { }` intending package-private access. The `default` keyword has a different meaning when declaring a **default method in an interface**.

## 2. Field Access

A **field** is a member variable belonging to an object (an instance field) or belonging to a class (a `static` field). A field can have its own separate modifier:

```java
class Profile {
    public String nickname;
    protected int rank;
    boolean active;              // package-private
    private String passwordHash;
}
```

Access conditions apply to the **field selected by the expression** itself. Having a reference to a `Profile` object does not mean the caller is permitted to read every field.

### 2.1. `public` Fields

`public String nickname;` allows code from anywhere the type containing the field is accessible to use `profile.nickname`.

However, **mutable public fields** often widen the possibility of unintended state changes:

```java
profile.nickname = null;
```

External code can bypass business validation steps if the field is exposed publicly. Therefore, for state that must be kept valid, you should generally choose **`private` fields + appropriate public methods**, rather than making every field public.

Not every public field is poor design: meaningful and stable constants are commonly declared `public static final` when appropriate, for example:

```java
public static final int MAX_ATTEMPTS = 3;
```

This is a primitive constant. If a public static final field points to a **mutable object**, `final` only prevents reassigning the field reference; it **does not** automatically prohibit modifying that object.

### 2.2. `private` Fields and Encapsulation

Save as **`PrivateFieldDemo.java`**:

```java
class Wallet {
    private int balance;

    Wallet(int balance) {
        if (balance < 0) {
            throw new IllegalArgumentException("Negative balance");
        }
        this.balance = balance;
    }

    int getBalance() {
        return balance;
    }

    void deposit(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Amount must be positive");
        }
        balance += amount;
    }
}

public class PrivateFieldDemo {
    public static void main(String[] args) {
        Wallet wallet = new Wallet(100);
        wallet.deposit(50);

        System.out.println(wallet.getBalance());

        // wallet.balance = -999;
        // INVALID if uncommented: balance is private.
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 PrivateFieldDemo.java
java PrivateFieldDemo
```

**Stdout:**

```text
150
```

In the example:
- `Wallet.balance` is `private`, so `PrivateFieldDemo` cannot access it directly, even though both classes are in the same source file.
- `deposit` controls increasing the balance through a business condition.
- `getBalance` only provides the value for reading. Here, the method has no modifier, so it is **package-private**, because the two classes are in the same default package.
- If `Wallet` is a public API from another package, you need to choose appropriate access permissions for the constructor/method that callers use.

**Encapsulation** does not mean a field must have a getter/setter in every case. Expose only the operations that are actually needed: some fields should be read-only, some do not need to be exposed, and some require validation when modified.

## 3. Instance Method Access

An **instance method** can read/modify the current object's state or perform behavior. Access modifiers determine **where the method can be called**:

```java
class Order {
    public void submit() {
        validate();
        markSubmitted();
    }

    protected void markSubmitted() {
        System.out.println("Submitted");
    }

    void recordAudit() {
        System.out.println("Audit");
    }

    private void validate() {
        // Check internal logic.
    }
}
```

- `submit()` is public: an intended entry point for callers permitted to use `Order`.
- `markSubmitted()` is protected: code in the same package and valid subclasses have access according to the rules.
- `recordAudit()` is package-private: for code in the same package.
- `validate()` is private: an internal implementation detail.

Having `submit()` **call the private method `validate()` is completely valid**: the code is inside the `Order` class, where it has permission to call `validate()`.

### 3.1. Public Methods Can Still Call Private Members

A public method is an **entry point**; it does not mean the internal actions it calls must also be public. For example:

```java
public void process() {
    checkInvariant();       // private
    executeInternal();      // private
}
```

This design keeps the API small and reduces external code's dependency on implementation details. When you change how `checkInvariant()` or `executeInternal()` works, callers only need to know the `process()` contract.

### 3.2. Private Methods Are Not Overridden Polymorphically

A `private` method is not inherited in a way that forms an overridable method from a subclass. A subclass can declare a method with **the same name and parameter list** as a private method in the superclass, but this is **not** an override of that private method.

Example:

```java
class Parent {
    private void secret() {
        System.out.println("Parent secret");
    }

    void callSecret() {
        secret();
    }
}

class Child extends Parent {
    void secret() {
        System.out.println("Child secret");
    }
}
```

If `new Child().callSecret()` is called, `Parent.callSecret()` invokes **`Parent.secret()`**, and does not dispatch to `Child.secret()`.

This differs from an appropriately overridden `protected` or `public` method: in that case, runtime dispatch can select the subclass implementation.

## 4. Constructor Access

A **constructor** is invoked when creating an instance with `new` or via constructor chaining `this(...)`/`super(...)`. A constructor's access level can differ from the access levels of fields and methods in the same class:

```java
public class Token {
    private final String value;

    private Token(String value) {
        this.value = value;
    }

    public static Token of(String value) {
        return new Token(value);
    }

    public String value() {
        return value;
    }
}
```

With this class (saved in **`Token.java`**):
- The **class** `Token` is `public`.
- The **constructor** `Token(String)` is `private`.
- The **method** `Token.of(String)` is `public static` and is allowed to call the private constructor **from inside `Token`**.
- The **field** `value` is `private final`.
- The **getter** `value()` is public.

External code can:

```java
Token token = Token.of("abc");
System.out.println(token.value()); // abc
```

However, you cannot write `new Token("abc")` from a class that does not have access to the private constructor.

**Important:** a constructor is not an instance method. Constructors **are not inherited or overridden**; constructor access and the `super(...)` mechanism must be considered separately from method overriding.

### 4.1. Public, Protected, Package-Private, and Private Constructors

| Declaration | Common Use Cases |
| --- | --- |
| `public Account()` | Allows external code to directly instantiate an `Account` |
| `protected Base()` | Allows appropriate subclasses to call the superclass constructor; code in the same package also has access |
| `Account()` | Opens instantiation only to code within the same package |
| `private Account()` | Controls creation via a factory or prevents external instantiation of a utility class |

If only one constructor is private while the class still has a public overload, callers can still invoke the public overload when appropriate:

```java
class Job {
    public Job(String name) {
    }

    private Job() {
    }
}
```

`new Job("A")` is valid in a context where `Job` is visible; `new Job()` from another independent class is blocked. **Access permissions are attached to each individual constructor**, not applied uniformly across all overloads.

## 5. Multi-Package Example: `public` and Package-Private

To observe scope across real packages, create the following file structure:

```text
src/
├── catalog/
│   ├── Product.java
│   └── CatalogDemo.java
└── app/
    └── Main.java
```

**File `src/catalog/Product.java`:**

```java
package catalog;

public class Product {
    public String name;
    int stock;
    private int secretCode;

    public Product(String name, int stock) {
        this.name = name;
        this.stock = stock;
        this.secretCode = 7;
    }

    public String label() {
        return name;
    }

    int stock() {
        return stock;
    }

    private int secretCode() {
        return secretCode;
    }

    public boolean hasSecretCode() {
        return secretCode() > 0;
    }
}
```

**File `src/catalog/CatalogDemo.java`:**

```java
package catalog;

public class CatalogDemo {
    public static void show(Product product) {
        System.out.println(product.stock);
        System.out.println(product.stock());
        // System.out.println(product.secretCode);
        // INVALID if uncommented: private field of Product.
    }
}
```

**File `src/app/Main.java`:**

```java
package app;

import catalog.CatalogDemo;
import catalog.Product;

public class Main {
    public static void main(String[] args) {
        Product product = new Product("Java Book", 3);

        System.out.println(product.name);
        System.out.println(product.label());
        System.out.println(product.hasSecretCode());

        CatalogDemo.show(product);

        // System.out.println(product.stock);
        // System.out.println(product.stock());
        // INVALID if uncommented: package-private in catalog.
    }
}
```

From the directory containing `src`, compile/run with JDK 17+:

```bash
javac -encoding UTF-8 -d out src/catalog/Product.java src/catalog/CatalogDemo.java src/app/Main.java
java -cp out app.Main
```

**Exact stdout:**

```text
Java Book
Java Book
true
3
3
```

Explanation:
- `Product` is a public top-level class with a public constructor, so `app.Main` can instantiate it via `new Product(...)`.
- `name` and `label()` are public, so accessing them from `app` is valid.
- `stock` and `stock()` are package-private, so `CatalogDemo` in the same package `catalog` can use them, whereas `Main` in package `app` cannot.
- `secretCode` and `secretCode()` are private, so **even `CatalogDemo`, despite being in the same package**, cannot access them directly.
- The public method `hasSecretCode()` inside `Product` is allowed to call the private `secretCode()` method and return a boolean result to the caller. The caller is still not allowed to call the private method directly.

**Note:** member access permissions are **independent** of whether classes are in the same source file or different files; Java relies on the declaration kind, package, nest, and type relationships.

## 6. `protected` for Fields and Methods: The Most Easily Misunderstood Rule

`protected` is not simply a “subclass-only” level. A `protected` member can be accessed:

- **From the same package** under package access rules, even without an inheritance relationship.
- **From a subclass in another package**, though instance member accesses are also subject to **receiver constraints**.

Suppose `Base` in package `core` has `protected int value`.

In a subclass `Derived` in package `client`, the snippet:

```java
this.value = 10;               // Valid inside an instance method of Derived
```

can be valid; however:

```java
Base base = new Base();
base.value = 10;                // Invalid in a subclass in another package
```

**Why?** When accessing a protected instance member from outside the declaring package, Java does not allow a subclass to freely interfere with the protected state of **any** superclass object. For accesses of the form `receiver.member`, the static type of the receiver must satisfy rules related to the subclass in which the code resides.

### 6.1. Runnable Multi-Package Example

**File `src/core/Base.java`:**

```java
package core;

public class Base {
    protected int value = 1;

    protected void increase() {
        value++;
    }

    public int getValue() {
        return value;
    }
}
```

**File `src/client/Derived.java`:**

```java
package client;

import core.Base;

public class Derived extends Base {
    public void updateSelf() {
        this.value += 2;       // Valid: receiver is Derived
        this.increase();       // Valid: calls inherited protected method
    }

    public void updatePeer(Derived peer) {
        peer.value += 3;       // Valid: peer has static type Derived
    }

    public void invalidExample(Base base) {
        // base.value = 10;
        // base.increase();
        // INVALID if uncommented: receiver of type Base across packages.
    }
}
```

**File `src/client/Main.java`:**

```java
package client;

public class Main {
    public static void main(String[] args) {
        Derived first = new Derived();
        Derived second = new Derived();

        first.updateSelf();
        first.updatePeer(second);

        System.out.println(first.getValue());
        System.out.println(second.getValue());

        // System.out.println(first.value);
        // INVALID if uncommented: Main is not a subclass and is in a different package from core.
    }
}
```

Run:

```bash
javac -encoding UTF-8 -d out src/core/Base.java src/client/Derived.java src/client/Main.java
java -cp out client.Main
```

Stdout:

```text
4
4
```

Analysis:
- `first` starts with `value = 1`, `updateSelf()` adds `2`, and then `increase()` adds `1` → **4**.
- `second` starts with `value = 1`, `updatePeer(second)` adds `3` → **4**.
- The code `peer.value` is **inside the subclass `Derived`** and `peer` has the static type `Derived`, so it is allowed under the protected access rules.
- `client.Main` does not automatically gain access to `first.value` merely because it uses a `Derived`; `Main` is not a subclass of `core.Base`.
- `Base base` in `Derived.invalidExample` does not meet the conditions to access `base.value` and `base.increase()` directly from outside package `core`.

**Tip:** if subclass code needs a public operation on an arbitrary superclass object, provide an appropriate public API or design a common method instead of misusing `protected`.

### 6.2. `protected static` Also Has Its Own Rules

For a **protected static field/method**, a subclass in another package can access the inherited member through valid contexts such as the subclass name or a simple name according to the rules. Do not infer that every other class in that package also gets access just because it has an import.

For readability and to avoid confusing a static member with an instance member, **you should call static methods through the class name** when access permissions and declarations allow it. For questions in this module, make sure you first master the difference between **same package** and **subclass outside the package**.

## 7. `protected` for Constructors Is Not the Same as `protected` Fields

A superclass constructor can be called by a subclass in another package using `super(...)`:

**File `src/core/Vehicle.java`:**

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

**File `src/garage/Car.java`:**

```java
package garage;

public class Car extends core.Vehicle {
    public Car(String brand) {
        super(brand);               // Valid: superclass constructor is protected
    }
}
```

**File `src/garage/Main.java`:**

```java
package garage;

public class Main {
    public static void main(String[] args) {
        Car car = new Car("Toyota");
        System.out.println(car.brand());

        // core.Vehicle v = new core.Vehicle("Honda");
        // INVALID: protected constructor does not grant new access to Main.
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 -d out src/core/Vehicle.java src/garage/Car.java src/garage/Main.java
java -cp out garage.Main
```

Stdout:

```text
Toyota
```

Why is this different from a field?
- `super(brand)` is an **explicit superclass constructor invocation** placed at the beginning of the `Car` constructor body under Java 17 rules.
- Code outside package `core` cannot directly create a standalone `Vehicle` using `new Vehicle(...)` simply because it can see the public class `Vehicle`.
- `Car` has a public constructor, so `garage.Main` can instantiate **Car**, and then the Car constructor calls the protected superclass constructor according to the rules.

For protected constructors, there are also a few specialized cases such as creating an anonymous subclass; these are exceptions according to language syntax rules, and a protected constructor should not be interpreted as fully public.

### Superclass Constructors Are Not Inherited

`class Car extends Vehicle` **does not inherit the `Vehicle(String)` constructor** as an overload of `Car`. To write `new Car("Toyota")`, the `Car` class must have a matching constructor of **`Car` itself**, which can then call `super("Toyota")`.

If the superclass does not have an accessible no-arg constructor and the subclass does not call a matching `super(arguments)`, the implicit insertion of `super()` can cause the code **not to compile**.

## 8. `private` with Constructors: Restricting Object Creation Paths

A **private constructor** is very useful when you want to:
- Prevent callers from choosing instantiation paths on their own;
- Apply validation/a factory before creation;
- Create a utility class containing only static functionality;
- Manage a set of instances according to a design policy.

### 8.1. Static Factory Method

Save as **`FactoryAccessDemo.java`**:

```java
final class Session {
    private final String id;

    private Session(String id) {
        this.id = id;
    }

    public static Session create(String id) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id required");
        }
        return new Session(id);
    }

    public String id() {
        return id;
    }
}

public class FactoryAccessDemo {
    public static void main(String[] args) {
        Session session = Session.create("S-01");
        System.out.println(session.id());

        // Session direct = new Session("S-02");
        // INVALID if uncommented: private constructor.
    }
}
```

Commands:

```bash
javac -encoding UTF-8 FactoryAccessDemo.java
java FactoryAccessDemo
```

Stdout:

```text
S-01
```

`Session.create(...)` is a **static method** with return type `Session`, **not a constructor**. It is called from outside, while the statement `new Session(id)` occurs **inside `Session`**, where the private constructor is accessible.

This example places the classes in the same file for convenience when running. If you want `Session` to be a public type for other packages, move `public final class Session` into `Session.java` and expose the appropriate APIs; **you do not need to make the constructor public**.

### 8.2. Utility Class That Does Not Need Instantiation

```java
public final class TextUtils {
    private TextUtils() {
        throw new AssertionError("No instances");
    }

    public static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }
}
```

This is a utility class with a private constructor. Callers use `TextUtils.isBlank(" ")` **without needing `new TextUtils()`**.

`final class` prohibits inheritance, while a `private constructor` prevents ordinary instantiation calls from external independent classes. Throwing `AssertionError` is merely a defensive layer in case the constructor is called from code that has access; `private` itself controls compile-time access.

You should not describe a private constructor as “absolute security”: reflection, serialization, instrumentation, or frameworks have their own mechanisms, and contexts within the same nest can gain access under Java rules. It is an **API/language boundary**, not a sandbox for untrusted code.

## 9. What Access Level Does a Default Constructor Have?

For a regular class that **does not declare any constructors**, Java provides a **no-argument default constructor** according to the language rules.

```java
public class Empty {
    int value;
}
```

If the superclass provides an accessible zero-argument constructor as expected, `Empty` receives a default constructor. For `public class Empty`, the default constructor has a corresponding **public** access level.

Therefore:

```java
Empty empty = new Empty();
System.out.println(empty.value); // 0 if the caller is in the same package to read the field
```

If the class is a **package-private top-level class**, the corresponding default constructor has package-private access; the class itself also cannot be used freely from another package.

**Important:** as soon as you declare **any explicit constructor**, even a private one, the compiler **no longer automatically adds** a default no-arg constructor.

```java
public class User {
    private final String name;

    private User(String name) {
        this.name = name;
    }

    public static User of(String name) {
        return new User(name);
    }
}
```

With `User`:
- `new User()` does not compile because **there is no no-arg constructor**.
- `new User("An")` from another class does not compile because this constructor is **private**.
- `User.of("An")` is valid from anywhere that has access to the public API.

Do not call the `private User(String)` constructor a “default constructor”. It is explicitly declared by the author, takes one parameter, and is not the compiler-generated default.

### 9.1. Author-Declared No-Arg Constructors

`public User() { }` is an **explicit public no-arg constructor**. `User() { }` without a modifier is an **explicit package-private no-arg constructor**. The term “no-argument” refers only to the **parameter list**, while the access level is an **independent** property.

## 10. A Public Class Might Still Not Be Instantiable from Outside

Let's analyze this independently:

```java
public final class Catalog {
    private Catalog() { }

    public static Catalog instance() {
        return new Catalog();
    }
}
```

- Public class: callers can **see the `Catalog` type** according to access rules.
- Private constructor: callers **cannot directly invoke `new Catalog()`** from an independent class without permission.
- Public static method: callers can **obtain an instance** via `Catalog.instance()`.

The existence of an external reference to a `Catalog` object **does not prove** that external code is allowed to call the constructor.

Similarly, a class can have **private fields** yet **public methods**, or a public constructor yet **private methods**. Each declaration is checked separately.

## 11. The Access Level of the Enclosing Class Always Matters

A non-public top-level class restricts the ability to use the type from another package:

```java
package internal;

class InternalEngine {
    public void run() {
        System.out.println("Run");
    }
}
```

The `run()` method is public, yet **the top-level type `InternalEngine` is package-private**. A file in package `external` cannot simply `import internal.InternalEngine;` and freely create/receive variables of that type in the usual way.

The **effective scope** of a member cannot bypass the accessibility barrier of **its enclosing type**.

### 11.1. Which Access Modifiers Can a Top-Level Class Have?

A top-level class can normally only be declared as:
- `public class Name`, or
- `class Name` (package-private).

You cannot write `private class TopLevel` or `protected class TopLevel` at the top level.

By contrast, a **member nested class** inside a class can be declared `public`, `protected`, package-private, or `private` as appropriate. This is why you must not apply the modifier table for **fields/methods/constructors** verbatim to every **top-level type**.

### 11.2. The Module System in Java 17

Since Java 9, the **Java Platform Module System** provides an additional layer of restriction. A `public class` in a package that is not **exported** to other modules may be inaccessible from a consuming module, even if its members are marked `public`.

When working with modules:
- Check `module-info.java`, especially `exports package.name;`.
- Distinguish ordinary Java access from **deep reflection** capabilities, which may involve `opens`.
- Do not interpret `public` as always meaning “accessible from everywhere across the entire JVM” regardless of modules.

For the examples run via the classpath in this lesson, no module declaration is needed to observe the basic mechanism.

## 12. Access Control and Overriding in Inheritance

Access control also affects **which methods can be overridden** and **the valid access levels of an override**.

Principles:
- If a `public` method is overridden, the overriding implementation must also be **public**.
- If a `protected` method is overridden, it can remain `protected` or be **widened to `public`**, but cannot be narrowed to package-private or `private`.
- A package-private method can be overridden under the rules for appropriately related classes **in the same package**; across packages, the fact that a package-private method is not inherited/accessed like a protected method must be considered carefully.
- `private` methods are not overridden.
- `static` methods are not dynamically overridden: a static method name can be **hidden** under the language conditions.

### 12.1. Overriding Cannot Reduce Visibility

Valid example:

```java
class Parent {
    protected void work() {
        System.out.println("Parent");
    }
}

class Child extends Parent {
    @Override
    public void work() {
        System.out.println("Child");
    }
}
```

`Child.work()` widens access from protected to public, which is valid.

Invalid example within the same hierarchy:

```java
class Parent {
    public void work() { }
}

class Child extends Parent {
    // protected void work() { } // INVALID: cannot narrow from public
}
```

**Why?** Callers permitted to use a public method through a superclass-typed reference must not lose that ability simply because the runtime object belongs to a subclass.

### 12.2. Runnable Program: Public Override of a Protected Method

Save as **`OverrideAccessDemo.java`**:

```java
class Parent {
    protected String identify() {
        return "Parent";
    }
}

class Child extends Parent {
    @Override
    public String identify() {
        return "Child";
    }
}

public class OverrideAccessDemo {
    public static void main(String[] args) {
        Parent value = new Child();
        System.out.println(value.identify());

        Child child = new Child();
        System.out.println(child.identify());
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 OverrideAccessDemo.java
java OverrideAccessDemo
```

Stdout:

```text
Child
Child
```

In `main`, all three classes belong to **the same default package**, so the code is allowed to call the protected `Parent.identify()`. The method is overridden and the runtime object is a `Child`, so the `Child.identify()` implementation runs in both calls.

**Key takeaway:** being able to access a method **does not mean the superclass's method is executed**. For an overridden instance method, runtime dispatch also selects the corresponding implementation after the call passes type and access checks.

### 12.3. Package-Private Methods and Inheritance Across Packages

Suppose `core.Base` has:

```java
package core;

public class Base {
    void internal() {
        System.out.println("Base");
    }
}
```

In package `client`, the class `Derived extends core.Base` **cannot access `internal()` as an ordinary inherited method from outside `core`**, because this method is package-private.

If `client.Derived` declares its own `void internal()` method, **you should not assume it is an override** of `core.Base.internal()`. A package-private superclass method is not inherited/overridden from another package in the way protected/public methods are.

This shows that **an `extends` relationship does not automatically expose all superclass members** to the subclass.

## 13. Access Control for Static Fields and Methods

A `static` field belongs to the type, whereas an instance field belongs to each object; **both are still subject to access control**:

```java
class Configuration {
    private static int retries = 3;

    public static int retries() {
        return retries;
    }
}
```

Another class cannot read `Configuration.retries` if the field is private, but can call `Configuration.retries()` when it has access to the public method.

For methods:
- A `public static` method can serve as a public API.
- A `private static` method is suitable for internal helper functionality.
- `protected static` and package-private static methods remain subject to their respective package/inheritance rules.
- Static methods **do not have `this`**, so they cannot directly reference an instance field/method simply because that field/method is public or protected.

### 13.1. Static Method Hiding Differs from Overriding

```java
class Parent {
    public static String label() {
        return "Parent";
    }
}

class Child extends Parent {
    public static String label() {
        return "Child";
    }
}
```

With:

```java
Parent variable = new Child();
System.out.println(variable.label());  // Parent
System.out.println(Child.label());     // Child
```

The static method is chosen based on the **declared/static type in a valid call**, rather than being dynamically dispatched based on the runtime object like an overridden instance method.

You should invoke it through the **class name**, such as `Parent.label()`, to make the intent clear; you should not call a static method through an object variable.

**A `private static` field/method is also not opened to other classes** merely because `ClassName.member` can be called; access permissions are still checked by the compiler.

## 14. `final`, Immutability, and Access Control Are Separate Concerns

A field:

```java
private final java.util.List<String> names = new java.util.ArrayList<>();
```

has **two independent rules**:

- `private`: which places have permission to directly access the `names` field.
- `final`: the reference field cannot be **reassigned** after valid initialization.

However, the `ArrayList` object is still mutable; a method in the class can call `names.add("An")`, modifying the data inside the list.

`public final int value = 3;` is also not a static field unless `static` is present. `final` does not automatically turn it into a global constant or alter its access level.

### 14.1. Quick Table: Access Modifiers vs. Other Modifiers

| Modifier | Question It Answers |
| --- | --- |
| `private`/`protected`/`public` or omitted | **Who is allowed to access it?** |
| `static` | Does the member belong to the class or to an instance? |
| `final` on a field | Can the field/variable be reassigned or not? |
| `final` on a class | Can this class be extended? |
| `final` on an instance method | Can this method be overridden? |
| `abstract` on a method/class | Does the member/class require a subclass implementation or disallow direct instantiation? |
| `synchronized` on a method | What synchronization mechanism applies to method calls? |

**Do not use access modifiers as a substitute for data validation or concurrency control.** A private field with a public setter that allows arbitrary writes can still break invariants if the setter does not validate. A public method is not automatically thread-safe simply because it is public.

## 15. Interfaces: Special Access Rules

In an **interface**, certain modifiers are implied differently than for class members.

Example:

```java
interface Named {
    String name();                    // public abstract (implicit)

    int MAX_LENGTH = 100;             // public static final (implicit)

    default String title() {          // public default method
        return name().toUpperCase(java.util.Locale.ROOT);
    }

    static boolean valid(String value) { // public static method
        return value != null && !value.isBlank();
    }

    private String helper() {         // private helper method (Java 9+)
        return name().trim();
    }

    default String normalized() {
        return helper();
    }
}
```

Things to remember:

1. **Fields declared in an interface** are always `public static final` according to Java rules, even when the author does not explicitly write all three keywords. Do not declare instance fields in an interface like in a class.
2. **Regular abstract methods in an interface** are implicitly `public abstract`; you cannot turn them into package-private by omitting `public`.
3. Interface **default methods** and **static methods** serve as public APIs in appropriate contexts; helper methods can be `private` starting from Java 9.
4. An interface **does not have constructors** to invoke `new InterfaceName()` directly.
5. A class implementing an interface must provide a public implementation method for the interface's public abstract method.

### 15.1. You Cannot Reduce Visibility When Implementing an Interface

```java
interface Named {
    String name();
}
```

The following implementation is invalid:

```java
class BadNamed implements Named {
    // String name() { return "bad"; }
    // INVALID if uncommented and no public method exists: visibility weaker than public.
}
```

Valid version:

```java
class GoodNamed implements Named {
    @Override
    public String name() {
        return "good";
    }
}
```

The interface and classes above are **illustrative declaration snippets** and are not meant to be run as a standalone file. Note that if `BadNamed` does not implement the `name()` method, it must still be declared `abstract`; the comment in the code illustrates an invalid access attempt during implementation.

### 15.2. Private Methods in an Interface Are Not External API

`private String helper()` in an interface is only for internal logic within the interface where appropriate, such as being called by a `default method`. Callers cannot invoke `object.helper()`, even if the object implements the interface.

This allows reusing logic across default methods without bloating the public API.

## 16. Nested Classes and `private` Access: Valid Scope Exceptions

Java allows member nested classes to access certain private members of the enclosing type and vice versa thanks to the access rules for the same *nest*.

Runnable example **`NestAccessDemo.java`**:

```java
public class NestAccessDemo {
    private int secret = 7;

    private static class Reader {
        static int read(NestAccessDemo owner) {
            return owner.secret;
        }
    }

    public static void main(String[] args) {
        NestAccessDemo owner = new NestAccessDemo();
        System.out.println(Reader.read(owner));
    }
}
```

```bash
javac -encoding UTF-8 NestAccessDemo.java
java NestAccessDemo
```

**Stdout:**

```text
7
```

`Reader` is a private static nested class belonging to `NestAccessDemo`. Even though `secret` is private, `Reader.read` accessing `owner.secret` is valid under the nested/nest member rules.

From this, you cannot infer that an **independent top-level class in the same package** can also access a private field. The two contexts are different.

**Private constructors also have scenarios where nested classes can access them**. Therefore, the accurate description is “preventing external code **without permission** from calling it directly”, rather than “no other code whatsoever can call it”.

## 17. Reading and Writing Fields: Accessibility Does Not Mean Modifiability

Suppose:

```java
class Example {
    public final int fixed = 10;
    public int mutable = 20;
    private int hidden = 30;
}
```

In code that can access the class:
- You can **read** `example.fixed` because the field is public.
- You **cannot reassign** `example.fixed = 99;` because the field is final.
- You can read/write `example.mutable` because it is public and not final.
- You cannot directly read/write `example.hidden` from another independent class because it is private.

These are **two different layers of conditions**: access control determines whether you have permission to use the member, while `final` and type rules determine whether a specific operation is valid.

A public getter also does not turn a private field into a public one; a getter simply returns a value or reference according to its contract. If a getter returns a reference to an internal mutable object, the caller can change that object's state **through the returned API**, even though the field holding the reference is private.

## 18. Compile-Time Access Checking and the Receiver's Static Type

Access permissions are not evaluated by the JVM inspecting the actual object and automatically “unlocking” a member at runtime.

Suppose:

```java
class Parent {
    public void common() {
    }
}

class Child extends Parent {
    public void childOnly() {
    }
}
```

With:

```java
Parent value = new Child();
value.common();           // Valid

// value.childOnly();     // INVALID: static type Parent does not have childOnly()
```

The error on `value.childOnly()` is first and foremost **that no matching method is found via the static type**, not that `childOnly` is private. Even though the method is declared public in `Child`, the compiler cannot invoke it through a receiver of static type `Parent` if `Parent` does not declare that method.

If the caller checks the subtype and performs a valid cast:

```java
if (value instanceof Child child) {
    child.childOnly();
}
```

then the compiler sees that the `child` variable has type `Child`, and the public method can be used validly.

**Practical checking process:** determine the **type of the receiving expression**, the **selected member**, and only then check **whether the member is accessible from the call site**. Avoid drawing conclusions solely from the runtime class.

## 19. Methods and Constructors: `this(...)` and `super(...)` Do Not Automatically Bypass Access

In a subclass constructor, you can call a superclass constructor with `super(...)` if **that superclass constructor is accessible under Java rules**.

```java
class Parent {
    private Parent(int code) {
    }
}

class Child extends Parent {
    Child() {
        // super(1); // INVALID if uncommented: Parent(int) is private
    }
}
```

The `Child` class snippet above **cannot compile even while the `super(1)` line is commented out**, because the compiler attempts to insert an implicit `super()`, yet `Parent` has no accessible zero-argument constructor. This is an **example intentionally illustrating an error**, not a runnable program.

If a superclass needs to be subclassed by external code, choose an appropriate `protected` or `public` constructor (and consider `abstract` for a superclass that should not be instantiated directly).

### 19.1. `this(...)` Calling Another Constructor in the Same Class

```java
class Rectangle {
    private final int width;
    private final int height;

    public Rectangle() {
        this(1, 1);
    }

    private Rectangle(int width, int height) {
        this.width = width;
        this.height = height;
    }
}
```

`public Rectangle()` **is allowed to call the private constructor `Rectangle(int, int)`**, because the `this(1, 1)` call takes place inside `Rectangle` itself. A private constructor does not mean internal code cannot use it.

In **Java 17**, an explicit constructor invocation `this(...)` or `super(...)` must appear at the beginning of the constructor body. Access control does not eliminate this syntax rule.

### 19.2. Constructors Do Not Override

A subclass cannot put `@Override` on a constructor, because constructors **are not inherited**. If the constructor name does not match the subclass name, the declaration may become a method (if it has a return type) or cause a syntax error.

Do not apply the “an override must preserve or widen access permissions” rule to superclass and subclass constructors: they **do not form an overriding relationship**.

## 20. Guidelines for Choosing Access Levels When Designing an API

A guiding table:

| Component | Level Usually Considered First | Why |
| --- | --- | --- |
| Field holding business state | `private` | Prevents callers from breaking invariants |
| Public constant field with a stable meaning | `public static final` | Exposes a clear shared value |
| Helper method used only inside the class | `private` | Reduces the API surface area |
| Helper for internal code in the same package | Package-private | Collaborates within the package without making it public externally |
| API entry point for callers | `public` | Exposes behavior that must be supported |
| Hook intended for subclasses | `protected` | Allows intentional extension |
| Constructor for a directly instantiated type | `public` or package-private | Matches the intended group of callers |
| Base-class constructor serving subclasses | `protected` | Allows subclasses to initialize the superclass |
| Constructor paired with a factory/utility | `private` | Controls creation paths |

These are not rigid rules. The access level depends on the API contract and on whether the class will be used within the same module, across multiple modules, within the same package, or what a framework requires.

### 20.1. “Prefer Private” Does Not Mean Everything Should Be Private

The **least privilege** principle: grant enough access for valid tasks without opening things up unnecessarily.

- If a subclass needs to alter behavior, a `protected` method may make more sense than a private one.
- If another part of the application needs to call a method, expose an appropriate public API rather than forcing callers to use reflection.
- If a helper is only meant for the same package, package-private can avoid exposing a public contract.
- If the class is part of a public library, note that changing access modifiers in a later version can **break dependent code**, especially when narrowing access.

A widely used public API must be modified carefully; you should not “fix security issues” by arbitrarily changing every public member to private without reviewing the contract.

## 21. Common Compile Errors

| Situation | Cause | Resolution |
| --- | --- | --- |
| `field has private access` | Caller reads/writes a private field from outside a valid context | Use a public method following the contract; do not expose the field arbitrarily |
| `method is not public ... cannot be accessed from outside package` | A package-private method is called from another package | Expose the API that is genuinely needed, or place the caller in the proper architectural package |
| `constructor ... has private access` | Caller invokes a private constructor | Use the factory; only open up the constructor if intended |
| `constructor ... has protected access` | Caller is not in a valid inheritance context or is in a different package | Call via `super(...)` in an appropriate subclass, or design a factory |
| `cannot find symbol` when the method exists on the runtime subclass | Variable has a superclass static type that does not declare the method | Use a common interface, a safe cast, or an appropriate static type |
| Subclass overrides a public method with protected | Reduces visibility | Keep it public |
| Class implements an interface with a package-private method | Interface abstract methods are public | Declare `public` on the implementation |
| `private class Foo` at top-level | Top-level classes do not accept private/protected | Use package-private or public; nested classes have different rules |
| `default void work()` in a regular class | Confusing the interface default-method keyword with package-private | Remove the `default` modifier in the class |
| Caller in the same folder but different package still cannot access | Package access is based on the `package` declaration, not apparent location on disk | Check the exact package name |
| `store.internal` assumed to be a “child” of `store` and thus have package-private access | They are two different package names | Design a public/protected API if needed |
| `public class` cannot be used from another module | The module's package may not be exported | Check `module-info.java` and `exports` |
| `super()` fails because the superclass constructor is private/missing | Subclass cannot call the required superclass constructor | Call `super(args)` to an accessible constructor; adjust the superclass API if appropriate |
| `public final` field can be read but not assigned | `final` prevents reassignment after initialization | Distinguish access from writability |
| Static helper using `this.privateField` produces an error | Static context has no `this` | Convert to an instance method or take the object as a parameter |
| Public getter returns a mutable list and caller can modify internal data | Getter exposes the mutable object via its return value | Return an appropriate snapshot/immutable view or adjust the contract |

Exact `javac` error messages may vary across versions, but the diagnostic approach still involves the **declaration type**, **package**, **inheritance relationship**, **member access level**, and **call context**.

## 22. Practice Exercises with Answers

### Exercise 1 — Private Field and Public Method

```java
class Student {
    private int score;

    public void setScore(int score) {
        if (score < 0) {
            throw new IllegalArgumentException("Invalid score");
        }
        this.score = score;
    }

    public int getScore() {
        return score;
    }
}
```

With `Student student = new Student();` in another class in the same package:

- `student.setScore(10);` → **valid**.
- `System.out.println(student.getScore());` → **valid**, prints `10`.
- `student.score = -5;` → **invalid**, because `score` is private.

**Lesson:** callers are allowed to invoke public methods, and cannot bypass checks by accessing the private field.

### Exercise 2 — Package-Private from Another Package

```java
package model;

public class User {
    int level = 1;

    void promote() {
        level++;
    }

    public int level() {
        return level;
    }
}
```

A class `app.Main` in package `app`:

- `User user = new User();` → valid if the default constructor is public and other access conditions are satisfied.
- `user.level;` → **invalid** from another package.
- `user.promote();` → **invalid** from another package.
- `user.level();` → **valid**, because the method is public.

**Lesson:** a public class does not make package-private fields/methods public.

### Exercise 3 — Protected Field from a Subclass Outside the Package

Suppose `core.Base` has `protected int count;` and `client.Child extends Base`. Inside an instance method of `Child`:

```java
this.count = 1;       // Valid
Child peer = new Child();
peer.count = 2;       // Valid
Base base = new Base();
// base.count = 3;    // Invalid via Base receiver from another package
```

**Lesson:** protected access outside the package has receiver constraints; you cannot access arbitrary superclass objects freely.

### Exercise 4 — Private Constructor and Factory

```java
public final class Ticket {
    private Ticket() {
    }

    public static Ticket create() {
        return new Ticket();
    }
}
```

From another independent class:

- `new Ticket()` → **invalid**.
- `Ticket.create()` → **valid**, receiving a `Ticket` object if the method runs successfully.

**Lesson:** permission to **receive/use** an object differs from permission to **directly call its constructor**.

### Exercise 5 — Is a Default Constructor Auto-Generated?

```java
class Box {
    private Box(int size) {
    }
}
```

Is `new Box()` from another class valid?

**No.** Because an explicit `Box(int)` constructor already exists, the compiler does not automatically add a no-arg constructor. You also cannot call `new Box(1)` from a class without access because that constructor is private.

### Exercise 6 — Interface Method Visibility

```java
interface RunnableTask {
    void run();
}

class Task implements RunnableTask {
    // void run() { } // Invalid if this is the implementation.
}
```

To implement it properly:

```java
class Task implements RunnableTask {
    @Override
    public void run() {
        System.out.println("Run");
    }
}
```

The two `Task` snippets are **alternative versions** and must not be placed simultaneously in the same package. The interface method `run()` is public by rule, so the implementation must be public.

### Exercise 7 — Is Overriding Allowed to Widen Access?

```java
class Parent {
    protected void work() {
    }
}

class Child extends Parent {
    @Override
    public void work() {
    }
}
```

**Answer:** valid. Overriding from protected to public **widens** access permissions. Conversely, overriding a public method with a protected method is rejected.

### Exercise 8 — Nested Class Reading a Private Field

Inside the same outer class:

```java
class Outer {
    private int value = 5;

    class Inner {
        int read() {
            return value;
        }
    }
}
```

**Answer:** `Inner.read()` is permitted to read `Outer.value` under nested-class rules. Another independent top-level class does not automatically gain access to read the private field merely by being in the same package.

### Exercise 9 — Accessing a Public Final Field

```java
class Settings {
    public final int limit = 10;
}
```

With `Settings settings = new Settings();`:

- `System.out.println(settings.limit);` → valid.
- `settings.limit = 20;` → **invalid**, because `limit` is final, even though the field is public.

**Lesson:** access control and assignment permissions are not the same thing.

## 23. Checklist Before Declaring a Field, Method, or Constructor

1. **Identify who the intended callers are:** the same class, the same package, a subclass outside the package, or public code from another package/module?
2. **Check whether the class containing the member is visible:** public/package-private top-level class, nested class, or module export.
3. **Choose an access modifier for each member**, rather than guessing based on the class's modifier.
4. **Does the field need to be modified directly by callers?** If not, consider private along with appropriate public methods.
5. **Which methods form the actual API contract?** Make the necessary methods public; keep helpers private or package-private when appropriate.
6. **Is an extension point needed for subclasses?** Use protected intentionally, and avoid exposing overly broad state to subclasses.
7. **If using protected from another package**, check the receiver type and the corresponding access rules.
8. **If a constructor is protected**, subclasses may need `super(...)`; a protected constructor does not grant `new Base(...)` access to all callers.
9. **If a constructor is private**, is there a factory/API providing instances as required? Have other constructor overloads been reviewed?
10. **If no constructor is declared**, remember that a default constructor may be generated; to control object creation, declare one explicitly.
11. **If overriding**, do not reduce access compared to the overridden method; private methods are not targets for overriding.
12. **If implementing an interface**, the implementation of a public abstract method must also be public.
13. **If `static` and `final` are present**, distinguish between access permissions, reassignment capability, and dynamic dispatch.
14. **If using nested classes**, do not mechanically apply the rule “another class can never read private members” to contexts within the same nest.
15. **If building a modular library**, also check exports/opens; `public` is not enough if the package is not exposed to other modules.
16. **Use the compiler and multi-package examples** to verify your assumptions; in particular, avoid “fixing errors” by making every member public.

## Key Takeaways

- Java controls the **accessibility** of **fields**, **methods**, and **constructors** based on the declared modifier and usage context.
- **`public`:** grants the broadest access when the type/module is also accessible; **package-private:** same package only; **`protected`:** same package plus special access for subclasses; **`private`:** strongly restricted, with valid same-nest contexts.
- **Private fields + controlled public methods** is a common encapsulation pattern; private does not automatically make an object immutable.
- **Constructors have their own access permissions**: a public class can still disallow `new` from outside via a private constructor, while providing a public static factory.
- **`protected` outside the package requires checking the receiver** when accessing fields/methods; a protected constructor lets subclasses call `super(...)`, not arbitrary code write `new Base(...)`.
- **Without an explicit constructor**, the compiler can generate a default no-arg constructor; **once any constructor is declared**, the compiler does not automatically add a no-arg one.
- **Overriding an instance method cannot reduce visibility**; private methods are not overridden polymorphically; interface abstract methods are implicitly public.
- **Access modifiers do not replace `final`, data validation, or thread safety**. Proper design must simultaneously consider visibility, how state is modified, and the object's contract.
