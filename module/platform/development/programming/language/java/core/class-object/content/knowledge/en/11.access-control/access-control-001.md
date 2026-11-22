# `public`, `protected`, Package Access, and `private` in Java

**Access control** is an important part of Java class design: it determines **which code is allowed to reference which types, fields, constructors, and methods**. The four familiar access levels when learning Core Java are **`public`**, **`protected`**, **package access (*package-private*)**, and **`private`**.

Choosing the right access level helps a class protect its invariants, reduce dependencies between parts of the program, and define API boundaries. Just because an object can be referenced does not mean you have permission to read every field of that object: **the type and member must still be accessible from the source code location where the code is written**.

This lesson targets **Java 17+** and focuses on class and member declarations, distinguishing packages from inheritance, the subtleties of `protected`, constructors, method overriding, nested classes, interfaces, modules, and common compilation errors. All examples with `main` include compilation commands and expected stdout.

## 1. The Four Basic Access Levels

For **fields, methods, and constructors of a regular class**, you can think of the access scope from broadest to narrowest:

1. **`public`:** source code at locations that can access the type declaring the member can use that member, subject to other conditions such as the Java module system.
2. **`protected`:** can be used within the **same package**, and in **subclasses in other packages** under stricter rules regarding access location and receiver type.
3. **Package-private (no access modifier written):** classes and types in the **same package** can use it; it is not opened to code in another package solely through an inheritance relationship.
4. **`private`:** can only be used within the declaration scope permitted by Java, essentially the enclosing class/type and related nested contexts; not every class in the same package can access it.

Example:

~~~java
package learning.model;

public class Profile {
    public String displayName;
    protected int score;
    String internalCode; // package-private
    private String passwordHash;

    public Profile() {
        displayName = "Khách";
        score = 0;
        internalCode = "NEW";
        passwordHash = "not-a-real-hash";
    }
}
~~~

This is an **illustrative declaration snippet** without `main` yet. The four fields differ in access scope, though all belong to the same `Profile` object. Having no modifier on `internalCode` is **package-private**; **do not write `default String internalCode;`** to represent default access.

### 1.1. Common Access Permissions Table

| Where the code trying to access a member is written | `public` | `protected` | Package-private | `private` |
| --- | :---: | :---: | :---: | :---: |
| Within the declaring class itself | Yes | Yes | Yes | Yes |
| Another class in the same package, no inheritance needed | Yes | Yes | Yes | No |
| Subclass in a different package | Yes | **Conditional** | No | No |
| Class in a different package, not a subclass | Yes | No | No | No |

The **“Conditional”** entry is the most distinctive aspect of `protected`: a subclass in another package **cannot use an arbitrary superclass reference to call a protected instance member**. A dedicated section below provides examples that compile cleanly and invalid examples.

This table describes **standard member access**, assuming the class containing the member is also accessible and is not further restricted by modules. Member access **cannot be broader than the accessibility of the type containing the member** from the caller's location.

## 2. Distinguishing `public`, `protected`, and `private` from Package-Private

Suppose we have a class:

~~~java
package school.core;

public class Student {
    public String name = "Lan";
    protected int grade = 8;
    String schoolCode = "SCH-01";
    private String personalNote = "Riêng tư";
}
~~~

The modifiers here control **who is allowed to read or assign the fields directly**. The fact that a field can be `public` does not mean mutable state should be exposed arbitrarily. In a domain model, it is usually better to use `private` fields and a method API with a clear contract.

### 2.1. `public` Does Not Mean “Callable Everywhere Regardless of Context”

A `public` member is one exposed publicly according to Java rules. However:

- **The declaring type must be accessible:** a public method on a package-private top-level class does not suddenly make that top-level class public.
- **Java Platform Module System (JPMS):** for code in another **named module**, the package of the public class also needs to be appropriately exported and the module must be readable according to the configuration.
- **All other conditions still apply:** an instance method requires a valid receiver, proper syntax/argument types, and compliance with exceptions/contracts and actual runtime conditions.

For simple Java applications running on the classpath without named modules, you can approximate this as meaning that public classes and public members are accessible from other packages.

### 2.2. `protected` Does Not Mean “Subclasses Only”

A common misconception is that “`protected` only allows subclasses to call it.” In Java, **any class in the same package** can also use a protected member when normal conditions are met, **even without inheriting from** the declaring class.

Conversely, a subclass in another package has protected access through the inheritance mechanism, but with **special receiver restrictions**. This is why many `protected` examples compile in a single package yet fail with errors after moving the subclass to a different package.

### 2.3. Package-Private Is Not `protected`

When neither `public`, `protected`, nor `private` is written on a regular class member, its access level is generally **package access**. Other classes in the **exact same package** can access it, whereas a subclass in another package **cannot access it solely because of an `extends` relationship**.

### 2.4. `private` Does Not Mean “Accessible Only by the Same Object”

A method in the **same class** can access a private field of **another instance of that exact same class**:

~~~java
class PairNode {
    private int value;

    PairNode(int value) {
        this.value = value;
    }

    boolean sameValue(PairNode other) {
        return this.value == other.value;
    }
}
~~~

`other.value` is valid inside `PairNode` even though `other` references a different object. Access permissions **are checked based on where the code is declared**, not by asking “is the object receiving the call `this`?”.

## 3. A Package Is an Access Boundary, Not an Arbitrary Directory Path

Package declaration:

~~~java
package com.example.library;
~~~

Two classes declared in the **same package `com.example.library`** can access each other's package-private members according to the rules. However, **`com.example.library.internal` is not the same package** as `com.example.library` — it is merely a package name that shares a common prefix.

Example:

~~~text
com.example.library             (package A)
com.example.library.internal    (package B, DIFFERENT from A)
com.example.app                 (package C, DIFFERENT from A and B)
~~~

Packages in Java do not form an access-permission hierarchy where “a parent package automatically grants access to subpackages.” Dots in package names create hierarchical naming, **not additional access permissions**.

### 3.1. Package-Private Applies to Classes in the Same Package

~~~java
package com.example.library;

class CatalogIndex {
    static String normalize(String title) {
        return title.trim().toLowerCase(java.util.Locale.ROOT);
    }
}

public class Catalog {
    public String normalized(String title) {
        return CatalogIndex.normalize(title);
    }
}
~~~

The two classes are shown together for ease of learning. If saved as actual Java source files, you should use two corresponding files or keep `CatalogIndex` as a package-private top-level class in the same `Catalog.java` file (valid because only `Catalog` is a public top-level class).

`Catalog` and `CatalogIndex` are in the same package, so `Catalog` can use the `CatalogIndex` class and its package-private method. In another package, code cannot directly use `CatalogIndex` merely by knowing the class name and adding an `import`.

**`import` does not grant access permission.** It only lets you refer to a type name according to lookup rules; a package-private class still cannot be used from another package even if you try to import it.

### 3.2. The Default Package (Unnamed Package) Should Not Be Used for Multi-Package Code

Demo Java files without a `package` declaration are generally treated as belonging to the **unnamed package** depending on the compilation context. This is convenient for single-file examples, but unsuitable for organizing multi-package applications and comes with limitations when used from named packages.

For project code, declare packages explicitly and structure the source path appropriately, especially when learning about access control. Do not use the default package as a way to “bypass” visibility boundaries.

## 4. Multi-Package Example: Testing All Four Access Levels Precisely

Here is a Java 17+ example with **four source files across two packages**, intentionally keeping the invalid calls commented out so the program can compile and run.

File structure:

~~~text
src/
└── academy/
    ├── core/
    │   ├── Account.java
    │   └── Classmate.java
    └── app/
        ├── SpecialAccount.java
        └── Viewer.java
~~~

### 4.1. File `src/academy/core/Account.java`

~~~java
package academy.core;

public class Account {
    private String secretCode() {
        return "PRIVATE";
    }

    String packageCode() {
        return "PACKAGE";
    }

    protected String protectedCode() {
        return "PROTECTED";
    }

    public String publicCode() {
        return "PUBLIC";
    }

    public String insideAccount() {
        return secretCode() + "/" + packageCode()
                + "/" + protectedCode() + "/" + publicCode();
    }
}
~~~

Inside the **`Account` class itself**, the `insideAccount()` method is allowed to call all four members. `private` does not prevent code **within the class itself** from using private members.

### 4.2. File `src/academy/core/Classmate.java`

~~~java
package academy.core;

import academy.core.Account;

public class Classmate {
    public static String inspect(Account account) {
        // account.secretCode(); // Error: private

        return account.packageCode() + "/"
                + account.protectedCode() + "/"
                + account.publicCode();
    }
}
~~~

`Classmate` does not inherit from `Account` but is in the **same package `academy.core`**, so it can call the package-private, protected, and public methods. It **cannot** call the private `secretCode()`.

### 4.3. File `src/academy/app/SpecialAccount.java`

~~~java
package academy.app;

import academy.core.Account;

public class SpecialAccount extends Account {
    public String inheritedAccess() {
        // packageCode();      // Error: package-private from another package
        // secretCode();       // Error: private

        return this.protectedCode() + "/" + this.publicCode();
    }

    public String inspectPeer(SpecialAccount other) {
        return other.protectedCode(); // Valid: subclass-type receiver
    }

    public String invalidReceiver(Account other) {
        // return other.protectedCode(); // Error: receiver has type Account
        return "Không truy cập qua Account reference";
    }
}
~~~

`SpecialAccount` is located in **package `academy.app`**, which differs from `academy.core`, yet it `extends Account`, so:

- `this.protectedCode()` is valid from the subclass's code.
- `this.publicCode()` is valid.
- `this.packageCode()` is invalid because a package-private method in another package is not made accessible by inheritance.
- `this.secretCode()` is invalid because private members are not accessible in a subclass simply through `extends`.
- `other.protectedCode()` in `inspectPeer(SpecialAccount other)` is valid because `other` has a **type permitted by the protected receiver rule** in the `SpecialAccount` context.
- `other.protectedCode()` in `invalidReceiver(Account other)` is **invalid**: even though the method is inside the subclass, the receiver expression has compile-time type `Account`, not `SpecialAccount` or a compatible subtype.

This is a core difference compared to the oversimplified statement “a subclass can access all protected members of its superclass.”

### 4.4. File `src/academy/app/Viewer.java`

~~~java
package academy.app;

import academy.core.Account;
import academy.core.Classmate;

public class Viewer {
    public static void main(String[] args) {
        Account account = new Account();
        SpecialAccount special = new SpecialAccount();

        System.out.println("Inside = " + account.insideAccount());
        System.out.println("Same package = "
                + Classmate.inspect(account));

        System.out.println("Subclass = " + special.inheritedAccess());
        System.out.println("Peer = " + special.inspectPeer(
                new SpecialAccount()));

        System.out.println("Outside = " + account.publicCode());

        // account.packageCode();  // Error: different package
        // account.protectedCode(); // Error: not a subclass context
        // account.secretCode();    // Error: private
    }
}
~~~

`Viewer` belongs to `academy.app` and is not a subclass of `Account`. It cannot directly access protected or package-private members in `Account`; however, it can call **public methods** of `Account` and `SpecialAccount`. When `Viewer` calls `special.inheritedAccess()`, the method **inside the subclass** performs the valid protected access itself and returns the data to the caller — it is not that `Viewer` was granted direct protected access.

### 4.5. Compiling and Running

From the directory containing `src`, using JDK 17+:

~~~bash
javac -encoding UTF-8 -d out src/academy/core/Account.java src/academy/core/Classmate.java src/academy/app/SpecialAccount.java src/academy/app/Viewer.java
java -cp out academy.app.Viewer
~~~

**Exact stdout:**

~~~text
Inside = PRIVATE/PACKAGE/PROTECTED/PUBLIC
Same package = PACKAGE/PROTECTED/PUBLIC
Subclass = PROTECTED/PUBLIC
Peer = PROTECTED
Outside = PUBLIC
~~~

Explanation of results:

1. `Account.insideAccount()` is written in the same class as all the members, so it can call the private, package-private, protected, and public members.
2. `Classmate.inspect(...)` in the same package can call package-private and protected members, but not private ones.
3. `SpecialAccount.inheritedAccess()` calls the protected method on `this` and the public method, even though the subclass is in a different package.
4. `inspectPeer(...)` calls the protected method through a receiver with a matching `SpecialAccount` type.
5. `Viewer` is in a different package and does not inherit from `Account`, so it can directly call the public method `publicCode()`, but not the other three methods.

**Important note on verification:** The failing calls are intentionally commented out. Uncomment only **one call you want to test** at a time and re-run `javac` to observe the compiler rejecting it; exact error message details may vary depending on the JDK version.

## 5. `protected` When the Subclass Is in Another Package

`protected` allows access within the **same package** without requiring inheritance. When the accessing code is in **another package**, there must be a **valid subclass context**. For a protected **instance field/method** declared in superclass `C` and accessed from subclass `S` in another package, the receiver of the dot expression must have a static type of `S` or a subtype of `S` according to Java's rules; an arbitrary variable of type `C` cannot be used.

~~~java
// File pet/model/Animal.java
package pet.model;
public class Animal {
    protected void breathe() { System.out.println("Breathing"); }
}
~~~

~~~java
// File pet/client/Dog.java
package pet.client;
import pet.model.Animal;
public class Dog extends Animal {
    void demonstrate(Dog peer, Animal base) {
        this.breathe();       // Valid: current receiver.
        peer.breathe();       // Valid: peer has type Dog.
        // base.breathe();    // Error: receiver has type Animal.
        super.breathe();      // Valid: called on the superclass part of this.
    }
}
~~~

The blocks above depict **two separate Java files**; do not place two `package` declarations in the same file. Key observation: `protected` access does not grant Dog permission to call `breathe` on every Animal object from another package; Java checks the code context and **the static type of the receiver**, rather than guessing that the runtime object is a Dog.

**Exceptions to distinguish:** `protected static` members and `protected constructors` have their own conditions and do not mechanically apply the receiver condition of instance members. A subclass can call a protected superclass constructor via `super(...)` when valid; that does not allow calling `new Animal(...)` arbitrarily from another package. Protected receivers, casting, sibling subclasses, and constructor edge cases are analyzed in depth in the dedicated article on `protected` in another package.

## 6. Package-Private Members Are Not Opened to Subclasses in Other Packages

Example:

~~~java
// File: package-a/Base.java
package a;

public class Base {
    void internal() {
        System.out.println("Base internal");
    }

    protected void extendable() {
        System.out.println("Base protected");
    }
}
~~~

~~~java
// File: package-b/Derived.java
package b;

import a.Base;

public class Derived extends Base {
    public void run() {
        // internal(); // Inaccessible: different package
        this.extendable(); // Valid
    }
}
~~~

`internal()` is package-private and is not visible from `Derived` just because `Derived extends Base`. It is not a method with “protected-like access without writing the keyword.”

If a subclass in another package declares a new method named `internal()` with the same parameter list, it does not automatically override an uninherited package-private method under the relevant overriding rules; it can instead be a **separate method**. Be careful with the `@Override` annotation and visibility rules when working with package-private members in a multi-package hierarchy.

## 7. `private` Protects Implementation Details and Invariants

A practical pattern is to keep state `private` and expose **valid operations** through public methods:

~~~java
class Wallet {
    private long balance;

    Wallet(long openingBalance) {
        if (openingBalance < 0) {
            throw new IllegalArgumentException("Số dư âm");
        }
        balance = openingBalance;
    }

    public long balance() {
        return balance;
    }

    public void deposit(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Số tiền phải dương");
        }
        balance = Math.addExact(balance, amount);
    }
}
~~~

In this example:

- Callers cannot write `wallet.balance = -100;` from code outside the class because the `balance` field is private.
- Callers read the state via `balance()` and request updates via `deposit(...)`.
- `deposit` validates the input before modifying the field, helping maintain the “non-negative balance” invariant.
- `private` **does not automatically guarantee** correct business logic: if code inside the class itself writes `balance = -100`, the compiler still allows it. Invariants must be protected through design and logic.

### 7.1. Private Methods and Objects of the Same Class

~~~java
class PasswordToken {
    private final String value;

    PasswordToken(String value) {
        this.value = java.util.Objects.requireNonNull(value);
    }

    private String normalized() {
        return value.trim();
    }

    boolean sameNormalizedValue(PasswordToken other) {
        return this.normalized().equals(other.normalized());
    }
}
~~~

`other.normalized()` is valid because the code is written **inside the `PasswordToken` class itself**, even though the receiver is the `other` instance. This is not package-wide or public access scope.

**Do not store real passwords or tokens like this simple string example in real-world applications** without following the appropriate security requirements. The example is solely intended to clarify private access scope.

### 7.2. Subclasses Cannot Access Private Members Directly

~~~java
class Parent {
    private int secret = 10;

    public int readSecret() {
        return secret;
    }
}

class Child extends Parent {
    int read() {
        // return secret; // Invalid: secret is private
        return readSecret(); // Valid via public API
    }
}
~~~

`Child` cannot call or read a private field merely through inheritance. However, an accessible public, protected, or package-access method in `Parent` can provide the required behavior without exposing private state.

## 8. Access Levels for Constructors

Constructors also have access levels, and that affects where writing `new ClassName(...)` is permitted.

~~~java
class Document {
    private final String id;

    public Document(String id) {
        this.id = id;
    }

    protected Document() {
        this("NEW");
    }

    Document(int number) {
        this(Integer.toString(number));
    }

    private Document(boolean internal) {
        this(internal ? "INTERNAL" : "EXTERNAL");
    }
}
~~~

This is an illustrative declaration snippet; overloads are distinguished by parameters, not modifiers. Meaning:

| Constructor modifier | Typical intended use |
| --- | --- |
| `public` | Allows creating objects from external code when the class/constructor is accessible |
| `protected` | Allows creation within the same package and valid calls from subclasses in other packages |
| Package-private | Lets code in the same package create objects |
| `private` | Controls instantiation paths within the class/valid nested contexts, often paired with a factory |

### 8.1. Private Constructors and Static Factories

~~~java
public final class OrderId {
    private final String text;

    private OrderId(String text) {
        this.text = text;
    }

    public static OrderId of(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException("ID rỗng");
        }
        return new OrderId(raw);
    }

    public String value() {
        return text;
    }
}
~~~

This is a **public top-level class** declaration; to compile it standalone, save it in `OrderId.java`. Code outside the class cannot call `new OrderId("...")` because the constructor is private. Instead, the public factory `OrderId.of(...)` validates the input and explicitly calls the private constructor.

**A private constructor does not mean “instances cannot exist”**; code that has access (such as a factory inside the class) can still create instances.

### 8.2. Protected Constructors in Another Package

~~~java
// File: api/BaseTask.java
package api;

public class BaseTask {
    protected BaseTask(String name) {
    }
}
~~~

~~~java
// File: app/CustomTask.java
package app;

import api.BaseTask;

public class CustomTask extends BaseTask {
    public CustomTask() {
        super("custom"); // Valid via subclass constructor
    }

    public static void demo() {
        // new BaseTask("x"); // Invalid in another package
    }
}
~~~

These are two illustrative files. Code in the **same package** has broader access to a protected constructor; code in a **different package** only has access in the subclass instantiation contexts permitted by the JLS. `protected BaseTask(...)` must not be treated as equivalent to a public constructor.

## 9. Access Levels for Top-Level Classes and Top-Level Interfaces

**Top-level classes** and **top-level interfaces** cannot use all four access levels. In standard Java source code, only the following are available:

- `public`: the type can be used from other packages if the remaining access conditions are met.
- **Package-private** (no access modifier): accessible only from the same package.

Valid example:

~~~java
package store.model;

public class Product {
}

class ProductValidator {
}

interface InternalPolicy {
}

public interface NamedProduct {
    String name();
}
~~~

The snippet above shows **multiple top-level declarations** to explain visibility. When placed in real source files, **there must not be two public top-level types** such as `Product` and `NamedProduct` in the same `Product.java` compilation unit under standard file-naming rules. Place `Product` in `Product.java` and `NamedProduct` in `NamedProduct.java`, and arrange the package-private types appropriately.

**Invalid for top-level classes/interfaces:**

~~~java
// private class Hidden { }   // Compile error
// protected class Shared { } // Compile error
~~~

`private` and `protected` can only be used on **member types** in valid contexts, not on top-level types. This rule differs from fields, constructors, and methods.

### 9.1. Having No Access Modifier Is Not “Implicit public”

A top-level class written as `class Helper` (without `public`) has package access; it **does not become public** simply because the class is in a file named `Helper.java`. Similarly, a method in a regular class without an access modifier is package-private, not public.

## 10. Nested Classes Can Use All Four Access Levels

A **member class** declared inside another class can use `public`, `protected`, package-private, or `private` if the context permits.

~~~java
public class Outer {
    public static class PublicNested {
    }

    protected static class ProtectedNested {
    }

    static class PackageNested {
    }

    private static class PrivateNested {
    }

    private final PrivateNested helper = new PrivateNested();
}
~~~

A suitable standalone file name is `Outer.java`. This declaration compiles in Java 17.

Notes:

- The access level of a member type restricts where it can be **referenced by type name**.
- A public nested class inside an enclosing type that is inaccessible from outside **does not automatically bypass the visibility of the enclosing type**.
- Nested classes and inner classes follow **private access rules among nestmate contexts**. You should not oversimplify this as “private can only be used within one pair of curly braces with no exceptions.”
- Local classes and anonymous classes have their own syntax and rules; do not mechanically apply the member-class modifier table to every kind of nested class.

### 10.1. Outer and Inner Classes Can Access Each Other's Private Members

~~~java
public class NestAccessDemo {
    private String text = "Outer";

    private class Inner {
        private String suffix = "Inner";

        private String combine() {
            return text + "+" + suffix;
        }
    }

    public String view() {
        Inner inner = new Inner();
        return inner.combine();
    }

    public static void main(String[] args) {
        System.out.println(new NestAccessDemo().view());
    }
}
~~~

Save `NestAccessDemo.java` and run:

~~~bash
javac NestAccessDemo.java
java NestAccessDemo
~~~

Stdout:

~~~text
Outer+Inner
~~~

`Outer` uses a private member of the inner object, and `Inner` accesses a private field of the outer object under Java's nested/nestmate rules. This is **not** merely because they are in the “same package”; an unrelated external class in the same package still cannot access those private members.

## 11. Method Overriding and Not Narrowing Access

When a subclass **overrides** a validly inherited instance method, it must not choose an access level **narrower** than that required by the original method.

~~~java
class Parent {
    protected Number value() {
        return 10;
    }
}

class Child extends Parent {
    @Override
    public Integer value() {
        return 20;
    }
}
~~~

This declaration is valid: `protected` is **widened** to `public`, and the return type `Integer` is compatible with `Number` under covariant return rules.

Cases:

| Superclass method | Overriding method in subclass | Valid access level? |
| --- | --- | --- |
| `public` | `public` | Yes |
| `public` | `protected` | No: narrowed |
| `public` | Package-private | No: narrowed |
| `protected` | `public` | Yes: widened |
| `protected` | `protected` | Yes |
| `protected` | `private` | No: narrowed |
| Package-private in the same package | Package-private or broader access | Possible, if other override rules are met |
| `private` | Method with the same name in subclass | Not an override of the private method in the usual sense |

A class in another package can declare a method with the same name and signature as an **uninherited package-private method**; do not call that a valid override merely because the names match. Adding `@Override` lets the compiler verify that a method to override actually exists.

### 11.1. Compile Error Example: Reducing Visibility

~~~java
class ParentApi {
    public void execute() {
    }
}

class HiddenApi extends ParentApi {
    // @Override
    // protected void execute() { } // Wrong: weaker than public
}
~~~

If you uncomment the two method lines in `HiddenApi`, `javac` will reject it because an overriding method cannot downgrade access from `public` to `protected`. The reason is that code allowed to call `ParentApi.execute()` must not unexpectedly lose that access when the actual object is a `HiddenApi`.

### 11.2. Private Methods Are Not Overridden as Inherited Instance Methods

~~~java
class Base {
    private String secret() {
        return "Base";
    }
}

class Derived extends Base {
    String secret() {
        return "Derived";
    }
}
~~~

`Derived.secret()` is the subclass's own method, not a direct override of the private method `Base.secret()`, because private members are not inherited as overridable methods. Do not add `@Override` intending to override this private member.

## 12. Abstract Classes and Interfaces: Access Levels Have Their Own Rules

### 12.1. Abstract Methods Cannot Be Private When Overriding Is Required

~~~java
abstract class Workflow {
    protected abstract void execute();

    public void run() {
        execute();
    }
}
~~~

`execute()` is a protected abstract instance method: a subclass can provide its implementation. A private method cannot be overridden by a subclass to fulfill an abstract contract this way, so `private abstract void execute();` is invalid.

### 12.2. Interface Methods Do Not Share the Same Package-Private Default as Class Methods

In a Java interface:

- An **abstract interface method** with no access modifier written is implicitly **`public`**, not package-private.
- **`default`** and **`static` interface methods** also follow appropriate public rules; the word `default` here is the keyword for an interface method implementation, **completely different** from “default access” in a class.
- Since Java 9, an interface can define **private methods** to share internal code between default/static methods under valid conditions.
- Do not use `protected` methods in an interface as you would in a class.
- Interface fields are implicitly **`public static final`**, not package-private or private fields.

Example:

~~~java
interface Formatter {
    String format(String text); // public abstract (implicit)

    default String decorated(String text) {
        return "[" + normalize(text) + "]";
    }

    private String normalize(String text) {
        return text.trim();
    }
}

class UpperFormatter implements Formatter {
    @Override
    public String format(String text) {
        return text.toUpperCase(java.util.Locale.ROOT);
    }
}
~~~

This is a valid Java 17 declaration. The `format` method in the implementing class **must be public** because it implements a public interface method; it cannot be narrowed to package-private simply by omitting the modifier. The `normalize` method is a private helper of the interface, not part of the API for implementing classes to override.

**Do not write `private` on an abstract interface method that implementing classes must implement**; a private interface method must have a proper body and cannot be an abstract method under that mechanism.

## 13. Access Control and Encapsulation Are Not Completely Identical

`private`, package-private, `protected`, and `public` are **language mechanisms** for restricting where code can access a declaration. **Encapsulation** is the API design approach of hiding details and protecting business invariants. Using the right modifiers is a supporting tool, but not sufficient on its own.

Poor encapsulation example:

~~~java
public class Cart {
    public java.util.List<String> items =
            new java.util.ArrayList<>();
}
~~~

External code can call `cart.items.clear()` or `cart.items.add(null)` without the class controlling the invariant. Changing the field to `private` while still returning the mutable list directly also remains problematic:

~~~java
import java.util.ArrayList;
import java.util.List;

class UnsafeCart {
    private final List<String> items = new ArrayList<>();

    public List<String> getItems() {
        return items; // Callers can still mutate the internal List object
    }
}
~~~

A better design approach:

~~~java
import java.util.ArrayList;
import java.util.List;

class Cart {
    private final List<String> items = new ArrayList<>();

    public List<String> items() {
        return List.copyOf(items);
    }

    public void addItem(String item) {
        if (item == null || item.isBlank()) {
            throw new IllegalArgumentException("Tên item trống");
        }
        items.add(item);
    }
}
~~~

Callers only receive an unmodifiable snapshot list (containing immutable `String` elements), while all list modifications go through `addItem` with validation. **`private` protects field access, while defensive copying protects against mutable object aliasing**.

Not every class needs a getter/setter for every field. If a field must obey an invariant, **specific business operations** are usually safer than arbitrary setters.

## 14. Access Permissions Do Not Change Which Object Is Being Manipulated

Modifiers are not a copying or identity-control mechanism:

~~~java
class Counter {
    private int value;

    public void increment() {
        value++;
    }

    public int current() {
        return value;
    }
}
~~~

If you have:

~~~java
Counter first = new Counter();
Counter alias = first;
alias.increment();

System.out.println(first.current()); // 1
~~~

`first` and `alias` point to the same object, so the caller still sees the mutation. `private int value` only prevents **code outside the class from directly writing `alias.value = ...`**, rather than preventing valid changes through the public `increment` method.

Furthermore, `private` does not make `value++` **thread-safe**. If multiple threads share an instance, synchronization is a separate responsibility; access modifiers do not replace `synchronized`, locks, or atomic variables.

## 15. Access-Checking Rules at Compile Time and Runtime

Normally, the `javac` compiler checks access permissions when you write source code:

~~~java
package outside;

import academy.core.Account;

class UseAccount {
    void test(Account account) {
        account.publicCode();   // Valid
        // account.packageCode(); // Compile error
        // account.protectedCode(); // Compile error
        // account.secretCode(); // Compile error
    }
}
~~~

This is an illustrative snippet in a third package, assuming the `academy.core.Account` class from the multi-package example has already been compiled.

However, the JVM also performs linkage/access checks at runtime. If bytecode and classes change incompatibly (for example, a library changes a public member to private after the client has already been compiled), an error such as `IllegalAccessError` can occur during linking or execution, not necessarily a source-code error when you first write the file.

### 15.1. Reflection Does Not Render Access Modifiers Meaningless

Reflection APIs provide mechanisms to look up or attempt to access non-public members, but whether that succeeds depends on Java access checks, module boundaries, runtime configuration, and related security conditions. On modern Java, especially with named modules, you cannot assume that calling `setAccessible(true)` will always let you access every private member.

For Core Java class design, treat access modifiers as a **standard API contract**; do not use reflection to bypass a class's rules without a clear technical reason and appropriate access permissions.

## 16. Java Modules: `public` May Not Be Enough Across a Module Boundary

In Java 9+ and Java 17, the Java Platform Module System introduces an additional boundary outside packages. For example:

~~~java
// module-info.java of the module containing the API
module academy.model {
    exports academy.api;
}
~~~

This allows the `academy.api` package to be exported outside the module as configured. A `public` class in the `academy.internal` package is **not automatically accessible from another module** unless that package is appropriately exported.

The client module must declare the dependency when using named modules:

~~~java
module academy.client {
    requires academy.model;
}
~~~

These two snippets are `module-info.java` syntax examples, not standalone applications. For code on the **classpath/unnamed module**, typical behavior is simpler; with named modules, you must simultaneously consider:

1. The package containing the type is appropriately **exported**, or has corresponding readability/module accessibility.
2. The top-level or member type is accessible from the call site.
3. The member has appropriate visibility (`public`, `protected`, package-private, `private`).
4. All other compiler and JVM rules are still satisfied.

**`exports` differs from `opens`:** `exports` serves language-level public type access, whereas `opens` serves certain reflection/deep reflection capabilities. Do not use `opens` as a default replacement for all public APIs.

## 17. Runnable Java Example: Widening Access Level on Override

Create the file **`VisibilityOverrideDemo.java`**:

~~~java
public class VisibilityOverrideDemo {
    static class Parent {
        protected String label() {
            return "Parent";
        }

        public String display() {
            return "display: " + label();
        }
    }

    static class Child extends Parent {
        @Override
        public String label() {
            return "Child";
        }
    }

    public static void main(String[] args) {
        Parent parent = new Parent();
        Parent polymorphic = new Child();
        Child child = new Child();

        System.out.println(parent.display());
        System.out.println(polymorphic.display());
        System.out.println(child.label());

        // parent.label() is allowed here because the nested classes share
        // the same nest context and all classes are within this structure.
        // In another class in a different package, protected has
        // the restrictions explained in the earlier section.
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 VisibilityOverrideDemo.java
java VisibilityOverrideDemo
~~~

Stdout:

~~~text
display: Parent
display: Child
Child
~~~

Key takeaways:

- `Parent.label()` is protected, and `Child.label()` overrides it as public. This is **widening the access level**, which is valid.
- `Parent.display()` is public; when the runtime receiver is Child, the `label()` call dispatches to `Child.label()`.
- Access control and dynamic dispatch **serve different functions**. Modifiers answer whether code is allowed to call a member from that location; overriding and dispatch decide which implementation runs on the runtime object.

*Note:* Because both nested classes reside inside the same enclosing class in this example, real-world access from other packages will differ. This runnable demo mainly demonstrates **widening visibility on override and dispatch**, whereas the multi-package example in section 4 provides the full check of all four scopes.

## 18. Common Compilation Errors

### 18.1. Calling a Private Member from Another Class in the Same Package

~~~java
package example;

class A {
    private int secret = 1;
}

class B {
    int read(A a) {
        // return a.secret; // Error: private access
        return 0;
    }
}
~~~

Being in the same package does not grant private access. If B truly needs to read the data, A must deliberately provide a method/contract with appropriate visibility, or you should redesign the separation of responsibilities.

### 18.2. Trying `default` as an Access Modifier

~~~java
class Wrong {
    // default int count; // Invalid field access modifier syntax
    int count;            // package-private
}
~~~

In documentation, package-private is sometimes referred to as *default access*, but that does not mean field syntax is `default int`. The `default` keyword is used for other purposes such as `switch` labels and default methods in interfaces.

### 18.3. `private` or `protected` on a Top-Level Type

~~~java
// private class Utility { }   // Error
// protected class Store { }   // Error

class Utility { }             // Valid: package-private
public class Store { }        // Valid if file/scope matches
~~~

This snippet illustrates the declarations; if both top-level classes are in the same file, name the file `Store.java` after the public top-level class `Store`.

### 18.4. Overriding a Public Method with Protected

~~~java
class Parent {
    public void render() {
    }
}

class Child extends Parent {
    // @Override
    // protected void render() {} // Error: weaker access
}
~~~

An overriding method cannot narrow the visibility of a public method.

### 18.5. Thinking import Makes Package-Private Public

~~~java
// In package a:
class InternalHelper { }

// In package b:
// import a.InternalHelper; // Inaccessible
~~~

`import` only participates in name resolution; it does not alter a type's access permissions.

### 18.6. Subclass in Another Package Calling Protected via a Superclass Receiver

~~~java
// In a subclass in another package:
void inspect(Base base) {
    // base.protectedMethod(); // May be rejected due to receiver type
}
~~~

When using a protected instance member from a subclass in another package, you must check the static type of the receiver per the JLS, not just whether “the method is written inside a subclass.”

## 19. Comparing the Four Levels by Design Goal

| Access level | When to consider it | Benefits | Risks if overused |
| --- | --- | --- | --- |
| `private` | Fields, helpers, and implementation details that do not need to be exposed | Strong encapsulation, easy internal refactoring | Misuse can make collaboration between classes awkward, leading to unnecessary wrapper APIs |
| Package-private | Classes in the same package that need to collaborate internally | Hides implementation from external packages without making things public | Overly large packages can cause many classes to accidentally depend on internal details |
| `protected` | Intentional extension APIs for subclasses | Lets subclasses customize or access certain behaviors | Tight coupling to inheritance; hard to preserve invariants if mutable state is exposed |
| `public` | Contracts genuinely needed by callers outside the package | Clear API, broad reuse | Hard to change later; public mutable fields break encapsulation |

**Practical rule of thumb:** start with the **narrowest access level that still meets valid requirements**. Only widen it when there is a clear use case:

- A **private helper** does not need to be made public just to test every statement directly; you can test it through public behavior or extract logic that genuinely needs reuse.
- A **package-private collaborator** fits when multiple classes within a package need to collaborate while external code does not need to know about it.
- A **protected extension point** should have clear documentation and a clear contract, avoiding the shortcut of “make any field a subclass might need protected.”
- A **public API** is a commitment to callers; reducing unintentional public exposure makes code easier to evolve.

Do not use access modifiers to paper over design flaws: for instance, a private field paired with a public setter that accepts any invalid value is still an API that fails to protect invariants.

## 20. Check Your Understanding with Questions and Answers

**Question 1.** In a regular class, what access level does the field `int x;` have?

**Answer:** Package-private, because neither `public`, `protected`, nor `private` is written. Other classes in the same package can access it if all remaining conditions are met.

**Question 2.** Can another class in the same package access a `protected` field without using `extends` on the declaring class?

**Answer:** Yes. In Java, protected grants access within the **same package** and adds an access path for subclasses in other packages under special conditions.

**Question 3.** Can a subclass in another package access a package-private method of its superclass solely because of `extends`?

**Answer:** No. Package-private does not cross a package boundary via inheritance.

**Question 4.** Can a subclass `Dog extends Animal` in another package call `animal.protectedMethod()` on a parameter declared with type `Animal`?

**Answer:** Not by default. The protected instance receiver rule requires a receiver type compatible with the subclass where the access is declared; `Animal` is generally too broad when `Dog` is using a protected member of its superclass from another package.

**Question 5.** Can a method of `Person` access `other.privateField` when `other` is also an instance of `Person`?

**Answer:** Yes, provided the code is in a context of class `Person` allowed to access that private member. Private restricts access based on where code is declared, not exclusively to the `this` object.

**Question 6.** Can you declare `protected class Service` at the top level?

**Answer:** No. A regular top-level class can only be `public` or package-private; `protected` applies in appropriate member type contexts.

**Question 7.** Does `import com.example.Hidden;` allow using the package-private class `Hidden` from another package?

**Answer:** No. An import does not elevate visibility.

**Question 8.** Is an interface method `void run();` without a modifier package-private like a class method?

**Answer:** No. An abstract interface method like this is implicitly `public abstract`; its implementation in a class must be `public` when overridden.

**Question 9.** If Parent has `protected String name()`, is it valid for a subclass to override it as `public String name()`?

**Answer:** Yes, because it widens visibility. If the subclass narrowed protected to private, it would be invalid.

**Question 10.** Does a `private final List<String> items` field with a public getter returning the mutable list directly provide good protection?

**Answer:** Not yet. Private restricts field access and final prevents reassigning the reference, but a getter returning the internal mutable object lets callers modify the list. Consider returning a snapshot/view and exposing validated commands.

**Question 11.** Is a public class in a package not included in `exports` of a named module usable by default in another module?

**Answer:** No. Module boundaries and readability/exports also participate in access checking.

**Question 12.** Does a private constructor mean a class cannot have instances?

**Answer:** No. Code with access inside the class can call the private constructor, for example a static factory returning a valid object.

**Question 13.** Does accessing a `protected` member in the same package require the receiver to be of a subclass type?

**Answer:** It does not require the special receiver rule for subclasses in another package; the same-package access path applies.

**Question 14.** A class has `private void helper()`. If a subclass declares `void helper()` with the same signature, is it overriding the private method?

**Answer:** Not in the sense of overriding an inherited instance method. A superclass's private method is not overridden merely by declaring a method with the same name in a subclass.

**Question 15.** Can a package-private method in a class belonging to `a.b` be accessed directly from `a.b.test`?

**Answer:** No. `a.b` and `a.b.test` are two different packages; sharing a name prefix does not create an access relationship.

## 21. Checklist When Choosing and Checking Access Modifiers

1. **Identify the construct:** are you declaring a top-level type, member type, field, constructor, or method? Not every declaration kind permits all four modifiers.
2. **Identify the caller:** is the calling code inside the class itself, in another class in the same package, in a subclass in another package, or in unrelated code in another package?
3. **Identify the actual package:** `a.b` and `a.b.c` are different packages.
4. **If using protected from another package:** check the subclass relationship and **compile-time receiver type**; do not rely solely on the runtime type.
5. **If overriding in a subclass:** you must not reduce the visibility of the original method.
6. **If a member is private:** remember that same-class code can access private members of **another instance of the same class**; private is not arbitrarily opened to other classes in the same package.
7. **If a top-level type is not public:** do not expect an import from another package to make it accessible.
8. **If the code uses an interface:** abstract/default/static interface methods and fields follow their own public rules; `default` in an interface is not package-private.
9. **If using named modules:** check `requires`, `exports`, and the appropriate accessibility conditions.
10. **If you want to protect state:** combine private fields, validation, a proper API, and defensive copying; modifiers alone do not make an object immutable or thread-safe.
11. **If the API is public/protected:** consider extensibility, backward compatibility, and the contract for subclasses/callers.
12. **When encountering a compile error:** read “has private access”, “is not public”, “has protected access”, or “attempting to assign weaker access privileges” carefully; check from the caller's location rather than looking only at the member's modifier.

**Remember:** `public` exposes a broad API, `private` keeps details internal, **package-private** is for code in the same package, and `protected` supports **both same-package access and subclass access with specific restrictions across packages**. A good design uses the narrowest reasonable access level and opens access intentionally, so that the class protects its data and exposes exactly the behaviors that external code needs.
