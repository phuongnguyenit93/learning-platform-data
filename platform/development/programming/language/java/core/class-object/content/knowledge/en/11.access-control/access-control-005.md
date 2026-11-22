# Access from the Same Class, Same Package, and Different Package in Java

When writing a Java class, fields, methods, and constructors cannot necessarily be used freely from every location. Java controls access through **access modifiers** and the relationship between the accessing code and the code declaring the member: are they in the **same class**, **same package**, or a **different package**? If in a different package, is that code a **subclass**?

Example:

~~~java
class Account {
    private String password;
    String internalNote;
    protected int rewardPoints;
    public String accountId;
}
~~~

The four fields above have **four different access levels**. Another class in the same package can access `internalNote` and `rewardPoints`, but cannot directly read `password`. A non-subclass class in a different package can usually only use `accountId`, provided that `Account` itself is an accessible type.

The easiest point to misunderstand is **`protected`**: from a different package, a subclass cannot arbitrarily read a protected member through *any reference of the superclass type*. Java also has a rule regarding the **type of the expression used as the receiver**.

This article provides a complete guide on distinguishing **`public`**, **`protected`**, **package-private** (no modifier written), and **`private`**, as well as access-checking mechanisms across packages, constructors, inheritance, nested classes, and modules. The examples prioritize **Java 17+**, complete with directory layouts, compilation commands, and concrete outputs.

## 1. What Should You Be Able to Answer After Learning This?

1. How do a **class** and a **package** relate to each other in Java?
2. Who do the four access levels allow to read/call a member?
3. Why does **package-private** not mean the same thing as `protected`?
4. Why can a class in the **same package** access a package-private member without inheritance?
5. Why can a subclass in a different package use `this.protectedField` but usually cannot use `baseReference.protectedField`?
6. How do these rules apply to **fields**, **instance methods**, **static methods**, and **constructors**?
7. Why is a `public` member not enough if the **type containing the member** is not visible?
8. How does access control affect **overriding**, object creation, API design, and splitting packages?
9. Why does `import` not grant additional access?
10. How can Java modules (**JPMS**) restrict using a public API across module boundaries?

## 2. What Is a Package and How Is "Same Package" Understood?

A package is a mechanism for grouping related types in Java. A file can declare:

~~~java
package learn.access.base;

public class Account {
}
~~~

This is illustrative class code, saved in the file `Account.java`. By project convention, the source path usually corresponds to:

~~~text
src/
└── learn/
    └── access/
        └── base/
            └── Account.java
~~~

Two top-level classes that declare the same package `learn.access.base` have a **same-package** relationship in a standard compilation context, even if they reside in **two different files**. Merely having two physical folders near each other, having similar names, or having one package be a prefix of another **does not automatically create** a same-package relationship.

Example:

| Package of A | Package of B | Are they in the same package? |
| --- | --- | --- |
| `learn.access.base` | `learn.access.base` | Yes |
| `learn.access.base` | `learn.access.child` | No |
| `learn.access` | `learn.access.base` | No |
| `app` | `app.internal` | No |
| `app.model` | `app.model.sub` | No |

**A subpackage does not "inherit" package-private access from a parent package.** `app.internal` and `app` are two different packages even though their names suggest a hierarchical relationship. Dots in a package name only organize names; they do not grant access privileges.

### Package Is Not Synonymous with Class

Two classes in the same package are **two different classes**. They can read each other's package-private members, but **cannot directly read the other class's private members** merely because they are in the same package.

Example:

~~~java
package sample;

class First {
    private int pin = 7;
    int amount = 10;
}

class Second {
    void inspect(First first) {
        System.out.println(first.amount); // Valid: same package.
        // System.out.println(first.pin); // Error: private.
    }
}
~~~

This is a valid illustrative code snippet if the error line remains commented out. Both classes belong to package `sample` and do not need an inheritance relationship.

## 3. The Most Important Access Table

In the context of standard Java classes on the classpath, the following table is fundamental:

| Member access level | In the declaring class itself | Another class in the same package | Subclass in a different package | Non-subclass in a different package |
| --- | --- | --- | --- | --- |
| `public` | Yes | Yes | Yes | Yes |
| `protected` | Yes | Yes | Yes, **with conditions** | No |
| *No modifier* (package-private) | Yes | Yes | No | No |
| `private` | Yes | No via normal package relationship | No | No |

Read the table together with three notes:

- For **`protected` from a different package**, there are rules regarding the subclass and receiver type, which are explained separately in a later section. Simply having `extends` is not enough for every access expression.
- The table describes **members of an already accessible type**. If the class containing the member cannot be accessed from outside, a `public` method inside it does not by itself open access through that class's name.
- For **nested classes/nestmates**, Java allows some private accesses between types within the same top-level declaration; this is an exception based on the *nest*, **not because they are in the same package**.

One way to remember the increasing scope, ignoring the detailed conditions of `protected`, is:

~~~text
private ⊂ package-private ⊂ protected ⊂ public
           ^                  ^
           |                  |
      same package      adds subclass relationship
                        across different packages
~~~

This is an intuitive diagram of scope, **not a mechanical comparison for every receiver**. `protected` has special rules when crossing package boundaries, so you must not infer that every syntax allowed within the same package is also valid in a subclass in a different package.

## 4. `private`: Limiting Member Access

A field or method declared `private` is normally accessed by code **inside the declaring class** (and valid same-nest contexts), rather than by a separate class that is merely in the same package.

~~~java
public class BankAccount {
    private long balanceCents;

    public BankAccount(long initialBalanceCents) {
        if (initialBalanceCents < 0) {
            throw new IllegalArgumentException("negative balance");
        }
        this.balanceCents = initialBalanceCents;
    }

    public long balanceCents() {
        return balanceCents;
    }
}
~~~

This is a complete class, though it does not yet have `main`. A calling class in a different package can use `new BankAccount(100)` and `account.balanceCents()` if the class/method is public and accessible, but **cannot** use `account.balanceCents` as long as the field remains `private`.

`private` helps preserve **encapsulation**. It allows the class to control the operations that modify an object's state, instead of letting callers mutate fields arbitrarily.

### Inside the Same Class, You Can Read Private Fields of Another Object of the Same Class

A common misconception is: "`private` only allows using `this.privateField`, and does not allow reading the private field of *another object*." This understanding is incorrect.

Inside the body of the `BankAccount` class, you can write:

~~~java
boolean sameBalance(BankAccount other) {
    return this.balanceCents == other.balanceCents;
}
~~~

Because the code is inside the **class declaring the field**, it is allowed to access private members on appropriate `BankAccount` instances, not only the instance referenced via `this`.

### Standalone Runnable Program

Create the file **`PrivateAccessDemo.java`**:

~~~java
public class PrivateAccessDemo {
    static final class Box {
        private final int secret;

        Box(int secret) {
            this.secret = secret;
        }

        boolean sameSecret(Box other) {
            return this.secret == other.secret;
        }
    }

    public static void main(String[] args) {
        Box a = new Box(7);
        Box b = new Box(7);
        Box c = new Box(9);

        System.out.println("a/b=" + a.sameSecret(b));
        System.out.println("a/c=" + a.sameSecret(c));
        // System.out.println(a.secret); // In a same-nest nested example,
        // Java 17 may allow this: see the nested class section below.
    }
}
~~~

~~~bash
javac -encoding UTF-8 PrivateAccessDemo.java
java PrivateAccessDemo
~~~

Stdout:

~~~text
a/b=true
a/c=false
~~~

`sameSecret` is inside the `Box` class itself, so reading the private field of `other` is valid. `Box` is a nested class of `PrivateAccessDemo`; Java 17 also has a mechanism for private access between **nestmates**, so you should not use this nested example alone to conclude that any top-level class in a different package can also read `secret`.

## 5. Package-private: Writing No Access Modifier

In Java, **omitting `public`, `protected`, or `private`** on a member can give it **package-private** access (also commonly referred to as *default access*).

~~~java
package sample.orders;

class OrderHelper {
    static String tag() {
        return "internal";
    }
}
~~~

`OrderHelper` is a **package-private top-level class**; `tag()` is also package-private. Other classes in `sample.orders` can access them under the normal rules. A class in `sample.app` cannot use `OrderHelper` directly by this type name even if it writes `import sample.orders.OrderHelper;`.

**Do not write the `default` keyword to indicate package-private:**

~~~java
// default class OrderHelper {} // Not an access modifier syntax.
class OrderHelper {}             // Correct: package-private.
~~~

The keyword `default` is used in **interface default methods** and the `default` branch of `switch`, but it is not an access keyword equivalent to "package-private".

### When Should You Use Package-private?

- Helper classes intended only for a single package.
- Internal methods that need to collaborate across multiple classes in the same package without becoming part of the public API.
- Logic supporting internal testing or implementation details that do not need to be exposed outside the package.

Do not make every member `public` just so another class can call it conveniently, if the design relationship actually belongs inside the package.

## 6. `protected`: Allowed in the Same Package, Requires a Subclass Relationship in a Different Package

`protected` combines two groups permitted to access it:

1. **In the same package:** another class can access a protected member under package rules, **without needing** to be a subclass.
2. **In a different package:** the accessing class must be in a valid subclass context of the class declaring the member, and for many forms of qualified access it must also satisfy the **receiver condition**.

Example:

~~~java
package sample.base;

public class Base {
    protected int score = 10;
}
~~~

Another class **in the same `sample.base` package** can write:

~~~java
package sample.base;

class SamePackage {
    int read(Base base) {
        return base.score; // Valid because it is in the same package.
    }
}
~~~

However, a non-subclass class in a different package cannot access `base.score`:

~~~java
package sample.client;

import sample.base.Base;

class External {
    int read(Base base) {
        // return base.score; // Error: protected is not open to this client.
        return 0;
    }
}
~~~

The files above are multi-package illustrative examples; do not combine multiple `package` declarations into the same file.

### How Does `protected` Differ from Package-private?

A package-private member relies solely on the package boundary. A `protected` member is accessible within the package **and** can be used by a subclass in a different package under the conditions specified by the JLS.

However, **`protected` does not mean "any subclass can read that member through any Base object"**. This is a point that needs careful analysis in a later section.

## 7. The Receiver of `protected` When Accessed from a Different Package

With `Derived extends Base` where the two classes are in two different packages, the subclass can use the protected instance field `score` via `this` or an expression of static type `Derived` or a subtype of `Derived`; merely knowing that the reference has type `Base` is **not enough**.

~~~java
// In class Derived extends Base, in a different package from where score is declared:
int own() { return this.score; }         // Valid.
int peer(Derived other) { return other.score; } // Valid.
int arbitrary(Base base) {
    // return base.score;                 // Compile-time error.
    return this.score;
}
~~~

These are **method fragments** placed inside an appropriate subclass, not a standalone Java program. Quick comparison from the body of Derived:

| Expression | Valid? | Why |
| --- | --- | --- |
| `this.score` | Yes | Current subclass receiver |
| `other.score` with `Derived other` | Yes | Receiver of type Derived |
| `base.score` with `Base base` | No | Type Base is too broad |
| `new Base().score` | No | Receiver of type Base |
| `((Derived) base).score` | May compile | The cast makes the static type match, but it may throw ClassCastException at runtime |

**A cast is not an access-granting mechanism** and does not convert a Base object into a Derived object. Also, do not apply this instance-receiver table mechanically to protected constructors or static members. The dedicated article on `protected` through a subclass in a different package thoroughly analyzes receivers, `super`, casts, sibling subclasses, and the exceptions.

## 8. Complete Multi-Package Project: Verifying the Four Access Levels

Isolated examples may be easy to follow, but to **truly see package boundaries**, let's create a small project with five Java files. This example is designed to **compile and run directly on JDK 17+**.

### Directory Structure

~~~text
access-lab/
└── src/
    └── learn/
        └── access/
            ├── App.java
            ├── base/
            │   ├── Vault.java
            │   └── Neighbor.java
            ├── child/
            │   └── ChildVault.java
            └── client/
                └── Visitor.java
~~~

Each file has **one `package` declaration** matching its directory in this project.

### File 1: `src/learn/access/base/Vault.java`

~~~java
package learn.access.base;

public class Vault {
    private final int pin = 7;
    String packageNote = "package";
    protected int points = 5;
    public int id = 9;

    public Vault() {
    }

    private String privateInfo() {
        return "pin=" + pin;
    }

    public String inspectOwnMembers() {
        return pin + "|" + packageNote + "|" + points + "|" + id;
    }

    public String callPrivateMethod() {
        return privateInfo();
    }

    protected String kind() {
        return "base";
    }
}
~~~

Inside `Vault` itself, the `inspectOwnMembers` method can read all four fields because they are declared in the class itself. `callPrivateMethod` can invoke the private method `privateInfo`.

### File 2: `src/learn/access/base/Neighbor.java`

~~~java
package learn.access.base;

public class Neighbor {
    public static String inspect(Vault vault) {
        return vault.packageNote + "|" + vault.points + "|" + vault.id;
    }
}
~~~

`Neighbor` **does not extend Vault**. However, because it is in the same package `learn.access.base`, it can read `packageNote` (package-private) and `points` (protected). It cannot directly read `pin` because it is private.

### File 3: `src/learn/access/child/ChildVault.java`

~~~java
package learn.access.child;

import learn.access.base.Vault;

public class ChildVault extends Vault {
    public ChildVault() {
        super();
    }

    @Override
    protected String kind() {
        return "child";
    }

    public String inspectSelf() {
        return this.points + "|" + this.id + "|" + this.kind();
    }

    public String inspectPeer(ChildVault another) {
        return another.points + "|" + another.id;
    }

    public String inspectArbitraryBase(Vault another) {
        // return another.points; // Invalid: receiver type is Vault.
        // return another.packageNote; // Invalid: package-private.
        // return another.pin; // Invalid: private.
        return String.valueOf(another.id);
    }
}
~~~

`ChildVault` is in a **different package** from `Vault`, yet is a subclass. It can use `this.points` and `another.points` when `another` has type `ChildVault`. It cannot read `packageNote` because that member is only package-private in `learn.access.base`. It also cannot read `pin` even though it inherits from Vault in terms of type relationship.

### File 4: `src/learn/access/client/Visitor.java`

~~~java
package learn.access.client;

import learn.access.base.Vault;

public class Visitor {
    public static int readPublic(Vault vault) {
        // vault.pin;         // Invalid: private.
        // vault.packageNote; // Invalid: package-private.
        // vault.points;      // Invalid: protected outside package, not a subclass.
        return vault.id;
    }
}
~~~

`Visitor` is in a different package and **is not a subclass**, so it can directly read the public field `id` of the public class `Vault`, and cannot read the remaining three fields.

### File 5: `src/learn/access/App.java`

~~~java
package learn.access;

import learn.access.base.Neighbor;
import learn.access.base.Vault;
import learn.access.child.ChildVault;
import learn.access.client.Visitor;

public class App {
    public static void main(String[] args) {
        Vault base = new Vault();
        ChildVault child = new ChildVault();

        System.out.println("own=" + base.inspectOwnMembers());
        System.out.println("private method=" + base.callPrivateMethod());
        System.out.println("neighbor=" + Neighbor.inspect(base));
        System.out.println("child=" + child.inspectSelf());
        System.out.println("peer=" + child.inspectPeer(new ChildVault()));
        System.out.println("visitor=" + Visitor.readPublic(base));
    }
}
~~~

### Compiling and Running

From the `access-lab` directory, execute:

~~~bash
javac -encoding UTF-8 -sourcepath src -d out src/learn/access/App.java
java -cp out learn.access.App
~~~

`-sourcepath src` tells the compiler where to find referenced source classes when needed; `-d out` stores the resulting class files according to their package paths under the `out` directory. The main class name when running is the **fully qualified class name** `learn.access.App`, not a standalone `App` from the project directory.

Stdout:

~~~text
own=7|package|5|9
private method=pin=7
neighbor=package|5|9
child=5|9|child
peer=5|9
visitor=9
~~~

### Results Demonstrated

1. **Same class (`Vault`):** can access private, package-private, protected, and public fields.
2. **Same package (`Neighbor`):** reads package-private/protected/public members of `Vault`, even though it is not a subclass.
3. **Different package, subclass (`ChildVault`):** uses `protected points` via `this` and via a `ChildVault` receiver; cannot use Base's package-private field.
4. **Different package, non-subclass (`Visitor`):** can only use public members on the accessible `Vault` type.
5. **Subpackage (`learn.access`):** `App` is in a **different package** from `learn.access.base`, even though the package names share a common prefix.

The invalid access lines are **placed in comments**. When studying compiler errors, you can uncomment **one line at a time** and run `javac` to observe the error, then comment it out again so the program runs.

## 9. `import` Alone Does Not Grant Additional Access

`import` lets code use the short name of a class or static member according to Java rules; it **does not alter the access level**.

Example:

~~~java
package external.app;

import learn.access.base.Vault;

class Demo {
    void show(Vault vault) {
        System.out.println(vault.id); // Public: valid.
        // System.out.println(vault.points); // Protected: error.
    }
}
~~~

Successfully importing `Vault` in a class does not mean it can read every field in Vault. Similarly, writing the fully qualified name `learn.access.base.Vault` instead of `Vault` **does not bypass access control either**.

If a top-level class is package-private:

~~~java
package learn.access.base;

class InternalHelper {}
~~~

then in another package, attempting `import learn.access.base.InternalHelper;` will be rejected because the type is not accessible. You cannot use import to "unlock" a top-level class.

### `import static` Does Not Bypass Access Checks Either

~~~java
import static java.lang.Math.max;
~~~

It only allows using the name `max` according to the import rules; the member must still have valid access permissions. If a static member is private or is protected without meeting the required conditions, simply writing `import static` does not make it accessible.

## 10. Access Levels of Top-Level Classes

When declaring a **top-level class** (not nested inside another type), there are only two standard access choices:

- `public class Example`.
- `class Example` — package-private.

Do not declare:

~~~java
// private class TopLevel {}   // Error for a top-level class.
// protected class TopLevel {} // Error for a top-level class.
~~~

`private` and `protected` can be applied to **nested classes**, but cannot be applied directly to a top-level class.

### Member Access Does Not Widen the Enclosing Type's Access

~~~java
package lab.hidden;

class HiddenService {
    public void execute() {
        System.out.println("running");
    }
}
~~~

This is a package-private class. A class in `lab.client` normally **cannot directly use the `HiddenService` type** merely because `execute` is public. First and foremost, the enclosing type must be accessible at the call site.

Conversely, inside package `lab.hidden`, other classes can use `HiddenService` and call the public method, provided the remaining conditions are met.

## 11. How Constructor Access Affects Object Creation

Constructors can also be `public`, `protected`, package-private, or `private`.

~~~java
public class Resource {
    public Resource() { }

    protected Resource(int capacity) { }

    Resource(String key) { }

    private Resource(boolean internal) { }
}
~~~

This is an illustrative class with four constructors of different signatures.

| Constructor | Same class | Another class in the same package | Subclass in a different package | Non-subclass client in a different package |
| --- | --- | --- | --- | --- |
| `public Resource()` | Yes | Yes | Yes | Yes |
| `protected Resource(int)` | Yes | Yes | Callable in an appropriate inheritance constructor context | Cannot directly call to create a Base object in the usual way |
| `Resource(String)` | Yes | Yes | No | No |
| `private Resource(boolean)` | Yes | No via normal package rules | No | No |

**Constructors are not inherited**: when a subclass writes `super(...)`, that is a call to the superclass constructor during the initialization of **a subclass instance**, rather than "inheriting a constructor like a method".

### Java 17+ Example with a Protected Constructor

Create three files:

~~~text
constructor-lab/
└── src/
    └── lab/
        ├── App.java
        ├── base/
        │   └── Device.java
        └── child/
            └── Phone.java
~~~

`src/lab/base/Device.java`:

~~~java
package lab.base;

public class Device {
    private final int code;

    protected Device(int code) {
        this.code = code;
    }

    public int code() {
        return code;
    }
}
~~~

`src/lab/child/Phone.java`:

~~~java
package lab.child;

import lab.base.Device;

public class Phone extends Device {
    public Phone() {
        super(42);
    }
}
~~~

`src/lab/App.java`:

~~~java
package lab;

import lab.child.Phone;

public class App {
    public static void main(String[] args) {
        Phone phone = new Phone();
        System.out.println("code=" + phone.code());
    }
}
~~~

Compile/run in the `constructor-lab` directory:

~~~bash
javac -encoding UTF-8 -sourcepath src -d out src/lab/App.java
java -cp out lab.App
~~~

Stdout:

~~~text
code=42
~~~

`Phone` is in a different package, yet has permission to call `super(42)` to `Device`'s protected constructor within a valid inheritance context. However, an ordinary client in `lab` cannot write `new Device(42)` on its own as if calling a public constructor; for example, it is still restricted by protected access.

### `private` Constructor and Static Factory

A class may want complete control over how objects are created:

~~~java
public final class Token {
    private final String value;

    private Token(String value) {
        this.value = value;
    }

    public static Token of(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("value required");
        }
        return new Token(value);
    }
}
~~~

This illustrative class has a private constructor, but the public factory `Token.of(...)` can instantiate an object using that constructor **from inside the Token class** and return the reference. Clients call `Token.of("ABC")` instead of `new Token("ABC")`.

## 12. Access of Static Fields and Static Methods

Modifiers apply to **static members** with similar access rules, except static members belong to the class rather than to individual instances.

~~~java
package sample.base;

public class Settings {
    private static int secretCode = 1;
    static int packageSetting = 2;
    protected static int protectedSetting = 3;
    public static int publicSetting = 4;
}
~~~

A class in the same package can use `Settings.packageSetting`, `Settings.protectedSetting`, and `Settings.publicSetting`, but cannot read `secretCode` directly.

In a subclass in a different package, `protected static` follows protected access rules with respect to the **type used as the qualifier**. For example, a subclass `DerivedSettings extends Settings` can use `DerivedSettings.protectedSetting` in a valid context. You should not assume that specifying the superclass name `Settings.protectedSetting` in a different package is always valid.

### Do Not Access Static Members Through an Object When the Class Name Is Clear

Java may accept `instance.staticMethod()` in some cases, but that can easily mislead readers into thinking the method depends on instance state. Prefer:

~~~java
Settings.publicSetting
~~~

instead of using an instance variable as the qualifier. Access permissions are still checked based on the static member's declaration and the access location; this does not turn a static member into an instance member.

## 13. Special Rule for Protected Static Access from a Different Package

Suppose:

~~~java
package sample.base;

public class Base {
    protected static int counter = 1;
}
~~~

A subclass `Child extends Base` in a different package can use the inherited static member name in a valid context:

~~~java
package sample.child;

import sample.base.Base;

public class Child extends Base {
    public static int read() {
        return Child.counter;
    }
}
~~~

However, another class in package `sample.child` does not automatically gain access to `Child.counter` if the member remains protected and declared in `sample.base.Base`; merely being in the same package as the subclass **does not** turn a superclass's protected member into a package-private member in the subclass's package.

**Conclusion:** For an inherited protected member, ask **which class/package it is declared in**, rather than looking only at the class used as the qualifier. The package condition is evaluated against the **package of the class declaring the member**, and does not automatically shift to the package of each subclass.

## 14. Nested Classes and Private Access: An Exception to Know

From a basic perspective, `private` is only used inside the declaring class. However, Java also has **nested classes** belonging to a group of *nestmates*, which can access each other's private members according to language and JVM rules (Java 11+ has a direct nestmate model in bytecode).

Example file **`NestmateAccessDemo.java`**:

~~~java
public class NestmateAccessDemo {
    private int outerSecret = 7;

    private static class Nested {
        private int innerSecret = 9;
    }

    public int readNested(Nested nested) {
        return nested.innerSecret;
    }

    public static void main(String[] args) {
        NestmateAccessDemo outer = new NestmateAccessDemo();
        Nested nested = new Nested();

        System.out.println("outer=" + outer.outerSecret);
        System.out.println("nested=" + outer.readNested(nested));
    }
}
~~~

~~~bash
javac -encoding UTF-8 NestmateAccessDemo.java
java NestmateAccessDemo
~~~

Stdout:

~~~text
outer=7
nested=9
~~~

`NestmateAccessDemo` reads the private field `innerSecret` of a nested class in the same nest according to Java rules. This does **not** mean that any arbitrary class in the same package as `Nested` can also read `innerSecret`.

### Nested Classes Can Be `public`, `protected`, package-private, or `private`

~~~java
public class Container {
    public static class PublicPart { }
    protected static class ProtectedPart { }
    static class PackagePart { }
    private static class PrivatePart { }
}
~~~

These four levels are valid for member nested types of a class. However, when using them from outside, **every enclosing type in the name** must also be accessible. You must not overlook access checks on `Container` or other enclosing types.

For a non-static inner class, there is also an enclosing instance; that does not by itself widen access beyond the modifiers.

## 15. Access of Interface Members Differs from Ordinary Classes

Members declared in an interface follow different rules from those in a class:

~~~java
public interface Printable {
    void print(); // Implicitly public abstract.

    default String title() {
        return "Printable";
    }

    static String category() {
        return "Document";
    }
}
~~~

This is an illustrative interface. The abstract method `print()` is implicitly **public abstract**, not package-private due to omitting the `public` keyword. The `default` method is also public. The static interface method here is public.

Java 9+ also allows **private methods in an interface** as internal helpers. However, **you cannot use protected methods in an interface the way you do in an ordinary class**. Fields declared in an interface are **public static final** by default; you cannot treat an interface field without a modifier as package-private.

### When Implementing an Interface, the Implementation of a Public Method Must Be Public

~~~java
class ConsolePrintable implements Printable {
    @Override
    public void print() {
        System.out.println("print");
    }
}
~~~

`ConsolePrintable.print()` must be public; it cannot be lowered to package-private merely because the `ConsolePrintable` class omits `public`. Overriding/implementing cannot reduce access compared to the public inherited method contract.

**Distinction:** a top-level interface can be package-private when no modifier is written, yet **interface members** still follow the interface's own rules.

## 16. Overriding: Access Cannot Be Narrowed

Suppose a superclass has a protected instance method:

~~~java
public class Base {
    protected String label() {
        return "base";
    }
}
~~~

A subclass can override it with `protected` or **widen it to `public`**:

~~~java
public class Child extends Base {
    @Override
    public String label() {
        return "child";
    }
}
~~~

These are two illustrative classes, placed in two corresponding files or converted into valid nested classes. However, an override cannot change the access level to `private` or package-private, because doing so would **reduce the access** of the inherited method.

Intentionally invalid example:

~~~java
class Parent {
    public void execute() {}
}

class Child extends Parent {
    // void execute() {} // Error: cannot reduce public to package-private.
}
~~~

If a subclass truly overrides a method, the access level must be kept compatible with Java rules. Beyond visibility, there are also other requirements regarding return type, checked exceptions, and method signature.

### Not Every Method with the Same Name Overrides

- A **private method** of a superclass is not overridden in the normal way; the subclass can declare a method with the same name/signature as an independent method if other rules allow it.
- A **static method** is not overridden like an instance method; *method hiding* may occur according to the rules.
- A **package-private method** of a superclass in a different package may **not be inherited/overridden by the subclass** in the way beginners expect, because that member is not accessible from the subclass's package.

In particular, do not attach `@Override` and assume the compiler will recognize overriding a package-private method that is not inherited across a package boundary.

## 17. Different Packages with the Same Class Name: Access Is Not Based on Simple Names

Two different packages can have two classes with the same simple name:

~~~text
app.user.Account
app.admin.Account
~~~

`Account` is the simple name, while the fully qualified name includes the package. They are **two different types** and do not automatically share an inheritance relationship or package-private access.

Writing:

~~~java
import app.user.Account;
~~~

in a file belonging to `app.admin` only allows referring to the `app.user.Account` type by the name `Account` when there is no conflict. It **does not make the file a member of package `app.user`** and does not grant access to the package-private fields of `app.user.Account`.

If you need to use two types with the same simple name in the same file, you may have to use the fully qualified name for one or both according to import and shadowing rules. Naming issues do not alter access checks.

## 18. Compile-Time Accessibility and Runtime Behavior

Normal access control is checked by the compiler based on **type declarations, the location of the code, and the member being accessed**. Instantiating a runtime object of a subclass type does not automatically make protected/private fields "public".

Example:

~~~java
Vault reference = new ChildVault();
// reference.points; // Invalid in App belonging to a different package.
~~~

Even when the actual runtime object is a ChildVault, the access expression in `App` is not in a context that has permission to read the protected field `points`. Dynamic dispatch of overridden methods does not grant access to blocked fields.

### However, a Public Method Can Use a Private Field Internally

~~~java
System.out.println(base.callPrivateMethod());
~~~

Calling a public method is valid from the client. Inside `Vault.callPrivateMethod`, code belonging to class `Vault` has permission to call `privateInfo()`. This is how encapsulation is designed: **the caller uses public behavior**, while the class manages its private state itself.

The compiler does not open direct field access just because a caller "indirectly reads private data"; the method is fulfilling a contract deliberately published by the class.

## 19. Java Modules Can Add Another Access Boundary

Since Java 9, the **Java Platform Module System (JPMS)** can restrict whether a module's package can be used by another module. A `public` top-level type located in an **unexported** package may **not be accessible from another module** through normal module mechanisms.

Example file `module-info.java`:

~~~java
module learning.core {
    exports learning.api;
}
~~~

This allows modules that read `learning.core` to use the public API from package `learning.api` if other module conditions are satisfied. It **does not export** package `learning.internal` if that package is not listed.

Points to distinguish:

- `public` handles **type/member-level accessibility** under Java rules.
- `exports` concerns **package accessibility across a module boundary**.
- Exporting a package does not make `private` or package-private members inside it public.
- `opens` serves conditional reflective access mechanisms, which differs from normal code invocation by writing `obj.method()`.
- When running on the **standard classpath** with an unnamed module, examples in exercises do not need to create `module-info.java`.

This is an extension to avoid concluding absolutely that "public is always accessible across every module". For learning core Java, master **class/package access** first, and then study JPMS more deeply when a project uses named modules.

## 20. Reflection Is Not a Reason to Bypass Encapsulation

Reflection can provide a way to inspect field/method metadata and, under certain conditions, code can request deeper access via APIs such as `setAccessible`. However, reflective access capability is subject to access control conditions, module openness, policy, and runtime configuration.

**Do not treat reflection as a normal fix** when the compiler reports a private/protected member as inaccessible. Instead, you should typically:

1. Check whether the API already has an appropriate **public method**.
2. If it is internal logic, consider placing collaborating classes in the same package with a package-private contract.
3. If inheritance is needed, design `protected` intentionally.
4. If clients have a valid need, provide a public getter/operation with a clear contract or an appropriate facade.
5. If working with serialization or framework reflection, configure modules and access APIs according to the framework's documentation rather than disabling all restrictions arbitrarily.

Good access control is part of **API design and invariant protection**, not merely syntax to get past the compiler.

## 21. Designing Getters/Setters: A Public API Does Not Require Public Fields

An implementation lacking encapsulation:

~~~java
public class Account {
    public long balanceCents;
}
~~~

A caller can write `account.balanceCents = -999;`. If an invariant requires a non-negative balance, the class can hardly control this mutation.

A clearer version:

~~~java
public class Account {
    private long balanceCents;

    public Account(long initialBalanceCents) {
        if (initialBalanceCents < 0) {
            throw new IllegalArgumentException("negative balance");
        }
        this.balanceCents = initialBalanceCents;
    }

    public long balanceCents() {
        return balanceCents;
    }

    public void deposit(long amountCents) {
        if (amountCents <= 0) {
            throw new IllegalArgumentException("invalid deposit");
        }
        balanceCents = Math.addExact(balanceCents, amountCents);
    }
}
~~~

This illustrative class keeps the field private, while the public API only allows reading the balance or making a deposit through validation. It is not necessary to create a public setter for every field. **Visibility should follow usage needs**; having a private field does not automatically require adding a public setter for completeness.

### Guidelines for Choosing Access Levels

- **`private`:** implementation details and state that must be protected; a good default for internal fields.
- **Package-private:** shared collaborators within a package when a public API is not needed.
- **`protected`:** extension points for subclasses that are clearly designed and have a documented contract.
- **`public`:** intentional API for external callers; stability and compatibility must be considered when making changes.

Do not use protected fields as a quick convenience instead of designing a proper subclass API. A protected member is also a commitment to subclasses that depend on it.

## 22. Compatibility When Changing Access Modifiers

If a library already provides a public method:

~~~java
public void save() { /* ... */ }
~~~

and a new version lowers it to package-private, clients in other packages may fail to recompile. Already compiled binaries may also encounter access errors at link/run time depending on the circumstances.

Conversely, widening a member from package-private to public usually increases the scope of code that can use it, yet you still need to check the API design and overall compatibility. You should not widen access arbitrarily just to fix a compile-time error.

**Especially with protected and inheritance:** if a subclass in a different package is overriding a protected method, lowering the superclass method's access or changing its signature can break code in the subclass. Therefore, public APIs and protected extension points must be managed intentionally.

## 23. Reading Compiler Errors "has private access" and "is not public"

When the compiler reports that an expression is not accessible, follow these steps.

**Step 1:** Identify the **member being accessed** — field, method, constructor, or type.

**Step 2:** Identify the **class declaring the member** and its original modifier. Do not look only at the variable's type if the member is inherited from a superclass in a different package.

**Step 3:** Identify the location of the accessing code — same class/nest or different, same package or different.

**Step 4:** If in a different package and the member is protected, determine whether the code is inside an appropriate subclass; for an instance member, check the **type of the receiver expression**.

**Step 5:** Check whether the class containing the member and any required enclosing types are accessible.

**Step 6:** If using modules, check whether the package is properly exported/read.

**Step 7:** Choose a semantically sound fix — a public API, changing the package design, switching to a valid protected receiver, or keeping the member private and providing the necessary operation.

### Common Error Messages

| Error pattern | Common issue |
| --- | --- |
| `has private access in ...` | Private member; code is not in an allowed context |
| `is not public in ...; cannot be accessed from outside package` | Package-private top-level type or member cannot be accessed from another package |
| `has protected access in ...` | Outside the package or the subclass receiver does not satisfy the protected condition |
| `cannot be accessed from outside package` | May relate to a member, type, or package/module boundary |
| `attempting to assign weaker access privileges` | Overriding a method while lowering its access level |
| `constructor ... cannot be applied to given types` | Constructor signature does not match; may also involve an access issue |
| `constructor ... has private access` | Caller is not allowed to invoke the private constructor |

Messages may vary across compiler versions and code styles. Read the **member signature, declaring class, and source location** rather than relying on a single error string.

## 24. Exercise 1 — Predicting Access Within the Same Package

Given:

~~~java
package practice;

public class Alpha {
    private int a = 1;
    int b = 2;
    protected int c = 3;
    public int d = 4;
}
~~~

Another class `Beta` is in package `practice` but does not extend Alpha:

~~~java
package practice;

class Beta {
    int read(Alpha value) {
        // Which fields can be used here?
        return value.b + value.c + value.d;
    }
}
~~~

**Answer:** `b` (package-private), `c` (protected), and `d` (public) are all readable; `a` is not, because it is private. `Beta extends Alpha` is not required for same-package access.

## 25. Exercise 2 — Different Package, Not a Subclass

Suppose `Alpha` is in `practice`, and `Gamma` is in `client`:

~~~java
package client;

import practice.Alpha;

class Gamma {
    int read(Alpha value) {
        return value.d;
    }
}
~~~

**Answer:** `value.d` is valid because `d` is public and `Alpha` is public. `value.a`, `value.b`, and `value.c` are not allowed in this class. `import practice.Alpha` does not grant access to the remaining members.

## 26. Exercise 3 — Protected Receiver in a Different Package

Suppose `Alpha` is in `practice`, with subclass:

~~~java
package child;

import practice.Alpha;

class Delta extends Alpha {
    int readSelf() {
        return this.c;
    }

    int readPeer(Delta other) {
        return other.c;
    }

    int readBase(Alpha other) {
        // return other.c; // Error.
        return this.c;
    }
}
~~~

**Answer:** `this.c` and `other.c` when `other` has type `Delta` are valid. `other.c` when `other` has type `Alpha` is invalid in the context of `Delta` in a different package. Casting to Delta can make the expression compile if the actual runtime object is Delta, but it carries the risk of `ClassCastException` and is usually not good design.

## 27. Exercise 4 — Top-Level Type and Member Access

Given:

~~~java
package library.internal;

class Converter {
    public String format() {
        return "text";
    }
}
~~~

Why can a class in `library.app` not directly write `new Converter().format()`? **Because `Converter` is a package-private top-level class**. Making `format()` public does not make `Converter` itself public.

Propose a public facade in an appropriate package, or make the converter public if it truly is an API intended for external callers.

## 28. Exercise 5 — Constructor from a Different Package

A superclass has a constructor:

~~~java
package library.base;

public class Parent {
    protected Parent(int value) {}
}
~~~

A subclass in package `library.child`:

~~~java
package library.child;

import library.base.Parent;

public class Child extends Parent {
    public Child() {
        super(1);
    }
}
~~~

**Answer:** `super(1)` is valid from the subclass constructor in this case. However, an ordinary client in a different package cannot call `new Parent(1)` on its own because a protected constructor is not a public constructor.

Do not confuse a superclass constructor with an inherited method: constructors are not inherited like methods.

## 29. Exercise 6 — Lowering Access When Overriding

Given:

~~~java
class Base {
    protected void calculate() {}
}

class Child extends Base {
    @Override
    // void calculate() {} // Error if uncommented: lowers protected to package-private.
    protected void calculate() {}
}
~~~

**Answer:** Overriding with protected is valid; overriding with public is also valid. Overriding by lowering to package-private/private fails. For the code to run, in the given snippet there is only one uncommented `protected void calculate(){}` implementation.

## 30. Review Checklist

- [ ] I can accurately distinguish between a class, a package, and a subpackage.
- [ ] I know that a subpackage is **not** automatically in the same package as its parent package.
- [ ] I know the private/package-private/protected/public access table within a class and across packages.
- [ ] I understand that package-private means **writing no modifier**, not writing the `default` keyword.
- [ ] I know that another class in the same package can access a protected member **even without inheritance**.
- [ ] I know that another class in the same package **cannot automatically** read a private member.
- [ ] I understand that protected in a different package is only open within a valid subclass context.
- [ ] I understand that when accessing a protected instance member from a different package, the receiver type can make the expression valid or cause an error.
- [ ] I know that `Base other` and `Derived other` can yield different protected access permissions from subclass code.
- [ ] I know that `import` and `import static` do not grant additional access.
- [ ] I know that a top-level class can only be public or package-private.
- [ ] I know that the access level of an enclosing class also affects using public members.
- [ ] I know that constructors have their own access modifiers and are not inherited.
- [ ] I can distinguish between static members and instance members in access control.
- [ ] I know that nested classes/nestmates have their own private access rules.
- [ ] I know that an interface method without a modifier is not package-private like a class method.
- [ ] I know that an override cannot reduce the access level of a method.
- [ ] I understand that Java modules can restrict exported packages beyond the public level.
- [ ] I do not treat reflection as the default way to bypass compiler access errors.
- [ ] I can compile the five-file multi-package project and explain its stdout accurately.
- [ ] I know how to choose modifiers based on **API contracts and encapsulation**, not just to make code compile.

**Conclusion:** When you want to know whether a member can be used, ask in order: **(1) in which class and with what modifier is the member declared; (2) in which class/nest and package is the using code located; (3) if protected in a different package, is it a valid subclass and receiver; (4) do the type containing the member and the module allow access?** Same class, same package, and different package are distinct contexts; understanding those boundaries helps you write safe Java APIs, avoid leaking implementation details, and fix access errors properly.
