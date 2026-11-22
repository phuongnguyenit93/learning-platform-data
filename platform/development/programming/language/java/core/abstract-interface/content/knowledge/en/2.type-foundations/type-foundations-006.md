# Access Levels `public`, `protected`, package-private, and `private` in Java

In Java, an **access modifier** specifies where code is permitted to reference a type, constructor, field, or method. Choosing the right access level is the foundation of **encapsulation**: hiding state and implementation details while exposing only the operations that other classes actually need. Access levels are checked by the compiler and are also subject to access-checking rules during linking/runtime.

## 1. Quick Comparison Table

| Where the declared member is accessed from | `public` | `protected` | package-private (no modifier written) | `private` |
| --- | :---: | :---: | :---: | :---: |
| Inside the declaring class (including nested classes under nestmate rules) | ✓ | ✓ | ✓ | ✓ |
| Another class in the **same package** | ✓ | ✓ | ✓ | ✗ |
| Subclass in a **different package** | ✓ | ✓* | ✗ | ✗ |
| Any class in a **different package** with no inheritance relationship | ✓ | ✗ | ✗ | ✗ |

The ✓* mark has an important condition: from a different package, a subclass can only access a `protected` member in an inheritance context and must obey the rule regarding the **type of the receiver expression** (see Section 4). The table assumes the type containing the member is itself accessible; Java module barriers may also apply.

A common order used to remember the visibility level of **class members**:

```text
private  →  package-private  →  protected  →  public
fewer access locations         more access locations
```

This is an ordering of **the set of entities that have access**, not advice to always increase visibility.

## 2. Meaning of Each Access Level

### `public`: exposing an interface to external code

A `public` member can be accessed by code in another package if the type containing it and the path to that type are also accessible. For applications using the Java Platform Module System (JPMS), the type's package must also be declared with `exports` by its module to the calling module (except in special cases such as code in the same module).

```java
package shop.api;

public class Product {
    public String name() {
        return "Notebook";
    }
}
```

Code in another package can call `new Product().name()` when the library is placed on the appropriate classpath/module path and the package is exposed according to the module configuration. **You should not make state fields `public` just for quick reads**: doing so creates a dependency on internal structure and causes difficulties when invariants need to be enforced.

### `protected`: sharing with the same package and subclasses

A `protected` field/method/constructor is accessible by every class in the same package as the declaring class. Outside that package, access is granted to code inside a subclass and is subject to the special rule in Section 4. `protected` does not mean "subclasses only": **every class in the same package**, even without inheritance, can still access it.

```java
package shop.core;

public class Item {
    protected int stock = 5;

    protected int available() {
        return stock;
    }
}
```

Use `protected` when the class is designed for valid extension; if you only want to expose functionality to users of the class, consider `public` methods with `private` state.

### Package-private: only types in the same package

When declaring a member or top-level type **without writing an access modifier**, Java uses *package-private* access, often called *default access*. There is no Java keyword `package-private` or `default` to declare this access level.

```java
package shop.core;

class InventoryHelper {  // Top-level type: package-private
    static int normalize(int count) { // Member: package-private
        return Math.max(count, 0);
    }
}
```

Any code belonging to the **same package `shop.core`** can use `InventoryHelper` and `normalize` (provided there are no other barriers). The subpackage `shop.core.internal` is a different package; having a shared name prefix does not grant access. Packages are determined by the `package` declaration, not by parent–child directory relationships.

Package-private is useful for internal collaborating classes, helpers, and implementation models that you do not want to put into the public API.

### `private`: hiding details of a class/group of nested classes

A `private` field, method, or constructor can only be accessed by code within the declaration of its containing class/type and the nested contexts permitted by the language. Java supports `private` access between classes belonging to the same **nest** (for example, an outer class and its nested classes); that is not access granted to other classes in the same package.

```java
public class Wallet {
    private int balance;

    public Wallet(int initialBalance) {
        if (initialBalance < 0) {
            throw new IllegalArgumentException("negative balance");
        }
        balance = initialBalance;
    }

    public void deposit(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        balance += amount;
    }

    public int getBalance() {
        return balance;
    }
}
```

`balance` is protected by the class's update rules; external code cannot write `wallet.balance = -100`. `private` access is also useful for factory constructors, helper methods, and internal constants. **Access control does not replace authentication, business authorization, or data encryption.**

## 3. Runnable Example: Same Package, Different Package, Subclass

Create four files with the following structure:

```text
src/
  demo/
    api/
      Account.java
      SamePackage.java
    app/
      VipAccount.java
      Main.java
```

File `src/demo/api/Account.java`:

```java
package demo.api;

public class Account {
    public String owner = "Lan";
    protected int points = 10;
    String id = "A-01";           // package-private
    private int pin = 1234;

    public String maskedPin() {
        return "****";
    }

    protected String score() {
        return "P" + points;
    }

    String packageLabel() {
        return "internal";
    }

    private String secret() {
        return "hidden";
    }

    public String inspect() {
        return id + ":" + secret(); // Private access is allowed within the class itself
    }
}
```

File `src/demo/api/SamePackage.java`:

```java
package demo.api;

public class SamePackage {
    public static String read(Account account) {
        return account.owner + " | " + account.points
                + " | " + account.id + " | " + account.maskedPin();
        // account.pin; // Error: pin is private to Account
    }
}
```

`SamePackage` does not extend `Account`, yet it can still read `points` (`protected`) and `id` (package-private) because both classes are in `demo.api`.

File `src/demo/app/VipAccount.java`:

```java
package demo.app;

import demo.api.Account;

public class VipAccount extends Account {
    public String vipInfo() {
        return owner + " | " + points + " | " + score()
                + " | " + maskedPin();
        // id;  // Error: package-private, does not belong to package demo.app
        // pin; // Error: private, not inherited
    }

    public int pointsOf(VipAccount otherVip) {
        return otherVip.points; // Valid: the expression type is VipAccount
    }

    // Invalid if uncommented:
    // public int pointsOfAny(Account other) {
    //     return other.points; // Protected error: the expression type is Account
    // }
}
```

File `src/demo/app/Main.java`:

```java
package demo.app;

import demo.api.Account;
import demo.api.SamePackage;

public class Main {
    public static void main(String[] args) {
        Account account = new Account();
        VipAccount vip = new VipAccount();

        System.out.println(account.owner + " / " + account.maskedPin()
                + " / " + account.inspect());
        System.out.println(SamePackage.read(account));
        System.out.println(vip.vipInfo());
        System.out.println(vip.owner);

        // account.points; // Error: protected, Main is not a subclass
        // account.id;     // Error: package-private in a different package
        // account.pin;    // Error: private
    }
}
```

Run in the project directory, with JDK 17 or later:

```bash
mkdir out
javac -d out src/demo/api/Account.java src/demo/api/SamePackage.java src/demo/app/VipAccount.java src/demo/app/Main.java
java -cp out demo.app.Main
```

Exact output:

```text
Lan / **** / A-01:hidden
Lan | 10 | A-01 | ****
Lan | 10 | P10 | ****
Lan
```

The lines starting with `//` only illustrate prohibited accesses; they are not executed and do not cause compilation errors. Uncommenting the expressions marked "Error" will cause `javac` to report access errors.

## 4. Important `protected` Pitfall Across Different Packages

The `protected` rule is the most common source of confusion. Consider `Account` declared in `demo.api`, and `VipAccount extends Account` in `demo.app`:

- Inside `VipAccount`, `this.points`, `super.score()`, or `points` are valid because they access an inherited member from the subclass.
- Within the declaration of `VipAccount` itself, `otherVip.points` is valid when `otherVip` has a **compile-time type** of `VipAccount` or one of its subclasses.
- `otherAccount.points` is **not valid** when `otherAccount` has a compile-time type of `Account`, even though the actual object may be a `VipAccount`.
- A non-inheriting class located in `demo.app` cannot read `account.points` merely because it is in the same package as `VipAccount`.

A helpful way to remember this: from a different package, code in a subclass is allowed to use `protected` to operate on "the object branch of that subclass itself"; this permission does not grant the privilege to operate on every instance of the superclass.

**`protected` constructors have their own exception:** a subclass in a different package can call `super(...)` to initialize the superclass part; this does not mean it can freely call `new Superclass(...)`. Constructors are not inherited. Avoid applying the receiver rule for fields/methods to draw wrong conclusions about constructors.

## 5. Which Declarations Do Access Levels Apply To?

| Declaration Kind | Levels That Can Be Declared Directly | Notes |
| --- | --- | --- |
| **Top-level** class/interface/enum/record | `public` or package-private | `protected` and `private` are invalid for a top-level type. A top-level public class/other public type follows Java's source file naming rules. |
| Member field, method, or constructor in a class | `public`, `protected`, package-private, `private` | Constructors are not inherited; the accessibility of a member is also constrained by the accessibility of its enclosing type. |
| Nested member type in a class (member class/interface/enum/record) | Levels permitted by the language; a class can use all four | Member types inside an interface have different rules than in a class. |
| Local variables, parameters, variables caught in `catch` | Do not use the four access modifiers | Their scope is determined by their declaration location and block. |
| Members in an interface | Separate rules | See Section 6. |

For example, a top-level class `public class Customer` is normally saved in `Customer.java`. A source file may contain supporting package-private top-level types (subject to the limit on the number of public types). Writing `private class Customer` or `protected class Customer` at the top level causes a compilation error.

Within a class, **the outer type must also be accessible**. For example, a `public` method on a package-private class does not automatically make that class an API accessible from another package. Similarly, a public nested class inside a private enclosing type is still subject to the barrier of the enclosing type.

## 6. Interfaces and Easily Confused Defaults

Interfaces have stricter rules than classes:

- Fields declared in an interface are always implicitly `public static final`. You cannot declare `private` or `protected` instance fields in an interface.
- Ordinary abstract methods of an interface are implicitly `public abstract` (except for special method kinds permitted by the syntax); an implementing class must use `public` and cannot narrow it down to package-private.
- Ordinary `default` and `static` methods in an interface are `public`. The `default` keyword here does **not** mean package-private access.
- Starting in Java 9, interfaces can have **`private` instance methods** and **`private static` methods** to support reusing logic inside the interface; they are not part of the API for implementing classes.
- Member types declared in an interface are implicitly `public static`; you cannot declare `private`/`protected` member types as in a class.

Standalone example, saved in `Greeting.java`:

```java
public interface Greeting {
    String PREFIX = "Hi"; // public static final

    default String greet(String name) {
        return decorate(PREFIX + ", " + name);
    }

    private String decorate(String message) {
        return "[" + message + "]";
    }
}
```

`decorate` can only be called within the body of `Greeting`; a class that `implements Greeting` can call `greet` but cannot access `decorate` directly. For an interface abstract method, `void run();` is equivalent in access level to `public abstract void run();`.

## 7. Inheritance, Overriding, and Access Levels

When overriding an inherited instance method, a subclass **must not narrow** the access level:

```java
class Parent {
    protected String label() {
        return "parent";
    }
}

class Child extends Parent {
    @Override
    public String label() { // Widening from protected to public: valid
        return "child";
    }
}
```

Changing `Child`'s `public String label()` to `private` or package-private will cause a compilation error. For a `public` method in the superclass, the overriding method must also be `public`. If a method in the superclass is package-private and the subclass is in a **different package**, that method is not inherited for overriding through the normal mechanism; declaring a method with the same name/signature in the subclass may be a separate method, so do not infer access permissions just by looking at matching names. Use `@Override` so the compiler catches this mistake.

A class's `private` methods are not inherited/overridden. A method with the same signature in a subclass is a different method (as long as other rules are satisfied). `static` methods can be *hidden* rather than overridden; fields can also be *hidden*. Access modifiers do not make fields polymorphic.

**Other independent overriding conditions:** `final` methods cannot be overridden; return types, checked exceptions, and certain signature rules must still be valid. Access level is only one of the checks.

## 8. Nested Classes and the `private` Exception

Nested classes help organize implementation details. `private` access between an outer class and its nested member classes is permitted by Java under lexical/nestmate rules; it does not mean the entire package can read private members.

```java
public class Container {
    private int count = 7;

    private static class Reader {
        static int read(Container value) {
            return value.count;
        }
    }

    public int readCount() {
        return Reader.read(this);
    }
}
```

`Container.Reader` is a `private` nested type; code outside `Container` cannot call `Reader.read(...)` directly. Even so, `Reader` can still read `Container`'s `count`. Modern JVM classes (Java 11+) have the concept of *nestmates* to support this scenario; the language-level access permission existed prior to that.

## 9. Access Modifiers vs. Packages, Modules, and Reflection

**Packages:** two classes with the same `package demo.api;` line belong to the same package by name, but in the module system there are additional module/visibility constraints; do not treat placement in the same directory or a subpackage as proof of accessibility.

**Modules (Java 9+):** `public` is a necessary condition at the type/member level, not necessarily sufficient for another module to use that class. For example, `module-info.java`:

```java
module shop.catalog {
    exports shop.api;
}
```

Another module with a `requires shop.catalog;` relationship can use the public API in `shop.api`, whereas internal packages without `exports` do not automatically become part of the API. `opens` primarily serves reflective access at runtime and does not mean exporting an API for normal Java code.

**Reflection:** `setAccessible(true)` can permit certain forms of reflective access when the environment/module allows it; module strong encapsulation can deny it and throw `InaccessibleObjectException`. Do not rely on `private` as a security barrier against malicious code in the same process; use proper authorization checks and trust boundaries.

## 10. How to Choose Modifiers in a Project

A practical way to make decisions:

1. **Default to trying `private`** for mutable state, helper methods, and internal constructors; control reads and writes using methods with business meaning.
2. Choose **package-private** for classes/collaborators that only need to be used by components in the same package. It reduces the API surface without having to add many unnecessary getters.
3. Choose **`protected`** when a superclass has a clear extension contract needed by subclasses. You should document invariants and extension points; mutable `protected` fields make it easy for subclasses to break state, so controlled `protected` methods are usually preferred.
4. Choose **`public`** for types and behaviors intended to be used by consumers of the library/product. Consider API stability and future modifiability.

Example of improving encapsulation:

```java
// Design whose invariant is easily broken:
public int balance;

// Controlled design (placed inside a class):
private int balance;

public void deposit(int amount) {
    if (amount <= 0) throw new IllegalArgumentException();
    balance += amount;
}

public int balance() {
    return balance;
}
```

The snippet above illustrates **two separate approaches**, not a standalone Java program to copy verbatim (you cannot declare `balance` twice in the same class).

## 11. Common Mistakes and How to Check

| Misconception | Correct Understanding |
| --- | --- |
| "`protected` is only for subclasses" | Every class in the same package also has access. |
| "A subclass in another package can read `baseRef.protectedField` on any `Base`" | The receiver/compile-time type rule in Section 4 restricts access. |
| "A subpackage belongs to the same package" | `a.b` and `a.b.c` are two different packages. |
| "Omitting a modifier is equivalent to `private`" | Omitting a modifier is package-private, visible to the same package. |
| "An interface's `default` method has default access" | `default` is the keyword for a method with a body in an interface; that method is public under interface rules. |
| "A `public` member can always be called from anywhere" | The enclosing type, module, and other access conditions must still be satisfied. |
| "A subclass can override a `private` method" | `private` methods are not inherited, so they are not overridden. |
| "An override can narrow `public` down to `protected`" | Java forbids narrowing access levels when overriding. |

When the compiler reports `has private access`, `is not public ... cannot be accessed from outside package`, or `has protected access`, determine the following in order: **type declaring the member → package of the calling code → subclass relationship → compile-time type of the receiver → accessibility of the enclosing type/module**. Do not fix errors by changing everything to `public`.

## 12. Self-Check

**Scenario A.** `p1.Base` has `protected void run()`; `p2.Child extends Base`. Inside a method of `Child`, is `this.run()` valid? Is `new Base().run()` valid?

**Answer:** `this.run()` is valid; `new Base().run()` is invalid from a different package because the receiver has type `Base`.

**Scenario B.** `p1.Helper` is a top-level class with no access modifier; can `p1.internal.UseHelper` use `Helper`?

**Answer:** No; `p1.internal` is different from `p1`, so it cannot reference the package-private top-level class.

**Scenario C.** An interface declares `void save();`. Can an implementing class define `protected void save()`?

**Answer:** No. `save` in the interface is `public abstract`, so the implementing method must be `public`.

**Key takeaway:** Access control is part of API design. Choose the smallest scope that meets real needs, carefully verify `protected` cases across different packages, and always consider the access level of the enclosing type itself at the same time.
