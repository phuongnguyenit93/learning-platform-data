# Accessibility of Inherited Members in Java

When a class **inherits** another class via `extends`, the subclass can use fields and methods exposed by its superclass. However, **superclass members do not all have the same accessibility from subclass code**. Access depends on modifiers (`public`, `protected`, no modifier, or `private`), package location, and sometimes the type of the expression used to access a member.

This is crucial in OOP inheritance: **an is-a relationship does not give a subclass unrestricted visibility into superclass internals**.

For example, `PremiumAccount extends Account` means a premium account is a type of account, but it does not let `PremiumAccount` directly read a `private` PIN inside `Account`.

This lesson uses **Java 17**. Cross-package examples are placed in separate files with compilation commands for verification.

## 1. Access Rules at a Glance

| Superclass member modifier | Declaring class | Other class in same package | Subclass in another package | Unrelated code in another package |
|---|---|---|---|---|
| `public` | Yes | Yes | Yes | Yes, if the type/API is accessible |
| `protected` | Yes | Yes | Yes, **subject to subclass access restrictions** | No |
| *Package-private* (no modifier) | Yes | Yes | No | No |
| `private` | Yes | No\* | No\* | No\* |

`*` Modern Java permits some `private` access between classes **in the same nest** (for example, nested classes and their enclosing class), but this is a *nestmate*-based exception, **not an inheritance privilege**. Ordinary top-level classes in the examples below cannot access one another's private members.

Read the following conditions alongside the table:

- **Same package** means the same `package` name, not just similar folder names or a shared prefix (`demo.core` and `demo.core.sub` are **different packages**).
- A `protected` member of a superclass **in another package** does not become public through arbitrary reference expressions. Java also checks the type of the receiving expression, as explained in Section 3.
- The table primarily describes **instance fields and instance methods**. Constructors, static fields, and some override rules differ.
- Member access does not make an **inaccessible containing class accessible**. For example, a package-private top-level class cannot be used from another package merely because one of its methods is public.
- With Java modules (JPMS), whether a package is `exports`-ed to the consuming module also affects cross-module public API accessibility.

## 2. Four Access Levels in the Context of Inheritance

### `public`: Exposed API

~~~java
package demo.core;

public class Document {
    public String getId() {
        return "DOC-01";
    }
}
~~~

Subclasses in other packages and unrelated code can call `getId()` as long as they can access `Document`.

`public` means the method is part of the class's published interface, so removing or changing its behavior may affect many clients. You do not need public fields merely to support subclasses; prefer intentional behavioral methods and appropriate getters.

### `protected`: Package Access and Subclass Support

~~~java
package demo.core;

public class Account {
    protected long balance;

    protected void markUpdated() {
        System.out.println("Cập nhật");
    }
}
~~~

Code **inside the same `demo.core` package** can access `balance` and `markUpdated()` even without being a subclass.

A subclass in another package may use these members where `protected` rules permit, such as `this.balance` and `super.markUpdated()`. However, outside the package, a subclass **cannot access protected members through every superclass-typed object**; the next section provides a complete example.

### No Access Modifier: *Package-private*

~~~java
package demo.core;

public class Account {
    int retryCount;
    void resetRetryCount() {
        retryCount = 0;
    }
}
~~~

`retryCount` and `resetRetryCount()` are accessible only to code in package `demo.core`. A subclass in `demo.feature` does not gain direct access merely through `extends Account`.

Do not call this access level `protected` or a “default method”: **package-private** is the access level resulting from an omitted access modifier, whereas an interface `default` method supplies an implementation.

### `private`: Implementation Details of the Declaring Class

~~~java
package demo.core;

public class Account {
    private String pin = "****";

    public boolean verifyPin(String candidate) {
        return pin.equals(candidate);
    }
}
~~~

A subclass cannot read `pin` directly, but can still **use public/protected superclass behavior** such as `verifyPin()`. Encapsulation lets the superclass change PIN storage without making subclasses depend on that representation.

Do not expose a public getter for every private field merely so “subclasses can see it.” Expose the capabilities the object actually needs to provide.

## 3. Runnable Example: Cross-Package `protected` Access

This is the lesson's most important example. The superclass and an inspector are in `demo.core`, a subclass is in `demo.feature`, and the application entry point is in `demo.app`.

File structure:

~~~text
src/
└── demo/
    ├── core/
    │   ├── Document.java
    │   └── CoreInspector.java
    ├── feature/
    │   └── ManagedDocument.java
    └── app/
        └── Main.java
~~~

**File `src/demo/core/Document.java`:**

~~~java
package demo.core;

import java.util.Objects;

public class Document {
    public final String id;
    protected String status;
    String internalNote;          // package-private
    private String accessToken;   // private

    public Document(String id) {
        this.id = Objects.requireNonNull(id, "id");
        this.status = "DRAFT";
        this.internalNote = "from core";
        this.accessToken = "secret-value";
    }

    protected void markReviewed() {
        status = "REVIEWED";
    }

    public String getStatus() {
        return status;
    }

    public String getMaskedToken() {
        return accessToken == null ? "" : "***";
    }
}
~~~

**File `src/demo/core/CoreInspector.java`:**

~~~java
package demo.core;

public final class CoreInspector {
    public static void inspect(Document doc) {
        System.out.println(
                "core sees: " + doc.id
                + ", " + doc.status
                + ", " + doc.internalNote
        );

        // System.out.println(doc.accessToken);
        // Không hợp lệ: accessToken là private của Document.
    }
}
~~~

`CoreInspector` **does not inherit** from `Document`, yet it can read `protected status` and package-private `internalNote` because it is in the same package.

**File `src/demo/feature/ManagedDocument.java`:**

~~~java
package demo.feature;

import demo.core.Document;

public final class ManagedDocument extends Document {
    public ManagedDocument(String id) {
        super(id); // Gọi constructor public của lớp cha.
    }

    public void review() {
        markReviewed(); // Hợp lệ: protected method được kế thừa.
        System.out.println("this.status: " + this.status);
        System.out.println("super.status: " + super.status);

        // System.out.println(internalNote);
        // Không hợp lệ: package-private ở package khác.

        // System.out.println(accessToken);
        // Không hợp lệ: private của lớp cha.
    }

    public void compare(ManagedDocument peer, Document base) {
        System.out.println("peer.status: " + peer.status);
        // Hợp lệ: peer có kiểu ManagedDocument.

        // System.out.println(base.status);
        // Lỗi biên dịch: protected member của lớp cha
        // không thể truy cập qua biểu thức kiểu Document
        // từ subclass ở package khác.
    }
}
~~~

**File `src/demo/app/Main.java`:**

~~~java
package demo.app;

import demo.core.CoreInspector;
import demo.core.Document;
import demo.feature.ManagedDocument;

public class Main {
    public static void main(String[] args) {
        Document base = new Document("DOC-01");
        ManagedDocument child = new ManagedDocument("DOC-02");

        child.review();
        child.compare(new ManagedDocument("DOC-03"), base);
        CoreInspector.inspect(base);

        System.out.println("id: " + child.id);
        System.out.println("status: " + child.getStatus());
        System.out.println("token: " + child.getMaskedToken());

        // System.out.println(child.status);
        // Lỗi: Main không cùng package, không phải subclass.

        // System.out.println(child.internalNote);
        // Lỗi: internalNote chỉ thuộc phạm vi package demo.core.
    }
}
~~~

Compile and run from the directory containing `src`:

~~~bash
javac -d out src/demo/core/Document.java src/demo/core/CoreInspector.java src/demo/feature/ManagedDocument.java src/demo/app/Main.java
java -cp out demo.app.Main
~~~

Output:

~~~text
this.status: REVIEWED
super.status: REVIEWED
peer.status: DRAFT
core sees: DOC-01, DRAFT, from core
id: DOC-02
status: REVIEWED
token: ***
~~~

Here, the same `status` field is accessed in three different ways:

- `ManagedDocument.review()` may use `this.status` and `super.status` because the subclass has protected access.
- `ManagedDocument.compare(...)` may use `peer.status` because expression `peer` has type `ManagedDocument`. It cannot use `base.status` because `base` has type `Document` (the superclass) in a different-package context.
- `Main` in an unrelated package cannot read `child.status`, even when the runtime object is a `ManagedDocument`. It can call public `child.getStatus()`.

### Why Does `protected` Restrict the Qualifier Type?

Java protects superclass encapsulation. A subclass in a different package may access protected state **through its own subclass role and appropriately typed subclass objects**, but cannot “borrow” subclass privileges to modify every unrelated superclass instance in the system.

In simplified terms for this example: inside `ManagedDocument`, when accessing a protected **instance** member declared in `Document` through `qualifier.member`, the qualifier's compile-time type must be `ManagedDocument` or its subtype. `this`, `super`, and `peer` are valid in the shown contexts; `Document base` is not. The full rules also distinguish `super` access forms and instance members, static members, and constructors.

~~~mermaid
flowchart TD
    A["Member protected trong Document"] --> B{"Code truy cập ở demo.core?"}
    B -->|Có| C["Cho phép theo quyền cùng package"]
    B -->|Không| D{"Code nằm trong subclass ManagedDocument?"}
    D -->|Không| E["Không cho truy cập protected trực tiếp"]
    D -->|Có| F{"Truy cập instance qua this/super hoặc qualifier hợp lệ?"}
    F -->|Có| G["Cho phép"]
    F -->|Không| H["Lỗi biên dịch"]
~~~

Do not treat protected as “public for all subclass objects.” It is a context-dependent inheritance privilege checked by the compiler.

## 4. Inheritance and Accessibility Are Different Questions

Two commonly conflated questions are:

1. **Does the member belong to the subclass's inherited member set?**
2. **May a particular code location access that member?**

A private superclass field still **exists in the state of a subclass instance** under Java's object model (the superclass has its own portion of the data), but Java does not let subclass code directly access it. Saying that “private fields are deleted from subclass objects” is incorrect.

Under Java's member-inheritance rules, private superclass members **are not inherited** as members directly usable by subclasses. Those private parts still operate through superclass methods on subclass instances.

For example:

~~~java
class Parent {
    private int counter;

    public void increase() {
        counter++;
    }

    public int value() {
        return counter;
    }
}

class Child extends Parent {}

class Demo {
    public static void main(String[] args) {
        Child child = new Child();
        child.increase();
        System.out.println(child.value()); // 1

        // System.out.println(child.counter); // Không hợp lệ.
    }
}
~~~

`Child` cannot directly access `counter`, but can invoke inherited public behavior `increase()` and `value()`. Code in `Parent` still manages the private field on a `Child` instance.

For a superclass in another package, package-private members are not accessible/inherited as directly named subclass members across packages as public/protected ones may be. Do not confuse runtime calls to a superclass implementation with the subclass's right to name an inaccessible member in source code.

## 5. Subclasses May Widen Access When Overriding but Cannot Narrow It

When overriding an instance method, Java requires the subclass implementation not to **reduce visibility** relative to the method it overrides.

Valid example:

~~~java
class Parent {
    protected String label() {
        return "parent";
    }
}

class Child extends Parent {
    @Override
    public String label() { // Mở rộng protected thành public.
        return "child";
    }
}
~~~

Invalid example:

~~~java
class Parent {
    public void process() {}
}

class Child extends Parent {
    // @Override
    // protected void process() {} // Lỗi: giảm quyền public xuống protected.
}
~~~

The supertype's callers were promised they could invoke a public method. If a subclass could turn it into protected, code receiving that subclass instance would lose access, violating substitutability.

**Additional notes:**

- A `protected` method may be overridden as `public`, but not the reverse.
- A public method must remain public in an override.
- A `final` method cannot be overridden, regardless of accessibility.
- Instance methods follow Java's overriding rules. Fields **are not overridden**; a subclass field may *hide* a same-named superclass field.
- A superclass `private` method cannot be overridden. A subclass may independently declare a same-named method with the same signature without using `@Override` on that private method.
- Package-private methods across package boundaries require actual inheritance/overriding analysis; a same-named method in an out-of-package subclass is not automatically an override of a non-public superclass method.

### Example: Field Hiding Versus Method Overriding

~~~java
class Parent {
    public String name = "Parent";

    public String who() {
        return "Parent";
    }
}

class Child extends Parent {
    public String name = "Child"; // Hides field Parent.name.

    @Override
    public String who() {
        return "Child";
    }
}

Parent value = new Child();

System.out.println(value.name);  // Parent
System.out.println(value.who()); // Child
~~~

For fields, Java selects by the reference's **compile-time type**. For overridden instance methods, Java selects the implementation by the **actual runtime object type** (dynamic dispatch). Do not use field hiding as a substitute for method polymorphism.

## 6. Subclass Creation Calls Superclass Constructors, but Does Not Inherit Them

Although subclasses can use many superclass members, **constructors are not inherited**.

~~~java
class Device {
    private final String serial;

    protected Device(String serial) {
        this.serial = java.util.Objects.requireNonNull(serial);
    }

    public String getSerial() {
        return serial;
    }
}

class Printer extends Device {
    public Printer(String serial) {
        super(serial); // Gọi constructor lớp cha, không kế thừa.
    }
}
~~~

A caller outside the package can create `new Printer("P-001")` if `Printer` and its constructor are accessible, but cannot automatically invoke `Device`'s protected constructor directly from unrelated external code.

Within a subclass, `super(...)` must follow Java constructor-chaining rules. If the relevant superclass constructor is `private` and the subclass lacks access, the compiler cannot construct the subclass through it.

Do not add a `public` superclass constructor solely to enable subclass construction if it also permits unwanted direct superclass instances. A `protected` constructor often suits an abstract superclass or a superclass intended to be used only through subclasses.

## 7. `super` Does Not Bypass Every Access Restriction

`super.method()` lets a subclass invoke an accessible/inherited superclass implementation and is useful when extending behavior:

~~~java
class Logger {
    protected void log(String message) {
        System.out.println("LOG: " + message);
    }
}

class TimestampLogger extends Logger {
    @Override
    protected void log(String message) {
        super.log("[EVENT] " + message);
    }
}
~~~

A subclass may use `super.log()` because the protected method is accessible. But writing `super.privateField` does not grant access merely because of `super`, nor can `super` bypass cross-package package-private restrictions.

Where possible, subclasses should **avoid depending on mutable protected fields** by using protected helper methods or public/protected APIs that enforce invariants. Protected fields let subclasses directly mutate data and make it harder for superclasses to change their internal representation.

## 8. Static Members, Fields, and Nested Types Follow Different Rules from Dynamic Methods

Inheritance is not limited to instance methods. Some superclass `static` members may be accessed through the subclass name under Java rules, but static methods **are not overridden through runtime polymorphism**; they may be *hidden*.

~~~java
class Parent {
    protected static String category() {
        return "BASE";
    }
}

class Child extends Parent {
    public static String category() {
        return "CHILD";
    }
}
~~~

These two methods are valid in the same-package (or otherwise accessible) context, but neither uses `@Override` because this is static method hiding. Java resolves static calls by the expression/class at compile time, unlike dynamic dispatch of instance methods.

Some nested classes and interface members can also be inherited or referenced by appropriate names, but accessibility of the nested type and its enclosing class must still be satisfied.

### Interface Access Rules Differ from Class Access Rules

In Java:

~~~java
interface Exportable {
    void export();
}

class PdfExport implements Exportable {
    @Override
    public void export() {
        System.out.println("Export PDF");
    }
}
~~~

An ordinary interface method declaring only a signature is implicitly **`public abstract`**. Its implementation must be `public`; package-private or protected access cannot hide a method promised by the interface.

Interfaces have no instance fields; their fields are implicitly `public static final`. Do not apply superclass `protected`/`private` field reasoning directly to interfaces.

## 9. Avoid Overusing `protected`: Design Intentional Extension Points

A protected field is convenient for subclasses but also makes them depend on superclass data structures:

~~~java
class Account {
    protected long balance;
}
~~~

Suppose the superclass later wants to change from `long` to a `Money` value object. Every subclass that reads or writes `balance` directly may need changes.

A more controlled approach is to keep the field private and expose validated behavior:

~~~java
class Account {
    private long balance;

    protected final long currentBalance() {
        return balance;
    }

    protected final void credit(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Số tiền phải dương");
        }
        balance = Math.addExact(balance, amount);
    }
}

class RewardAccount extends Account {
    public void receiveReward(long points) {
        credit(points);
    }

    public long availableBalance() {
        return currentBalance();
    }
}
~~~

Since `balance` is private, a subclass cannot arbitrarily assign a negative value. The two protected methods define operations the superclass permits subclasses to perform while enforcing invariants.

**However**, `protected final credit(...)` also becomes part of the API promised to subclasses. Do not add excessive protected hooks without a real extension need; they create future compatibility obligations.

If subclasses routinely need deep access to many internals, consider **composition**: move variable behavior to collaborators or strategies to reduce coupling across class generations.

## 10. Package and Module Implications for Library Distribution

Packages form important access boundaries when organizing source code:

~~~text
com.example.core            // package A
com.example.core.internal   // package B khác A
com.example.plugin          // package C
~~~

Despite sharing the prefix `com.example.core`, package `com.example.core.internal` **cannot** access package-private members of `com.example.core`.

With the Java Platform Module System (JPMS), libraries can also hide packages from other modules:

~~~java
module com.example.library {
    exports com.example.api;
}
~~~

Another module can use public APIs in an `exports`-ed package when module-access requirements are met. A public class in a package **that is not exported** does not automatically become usable public API for external modules.

This differs from member-level `protected`: member access applies only after the containing class/package is accessible in the program's context.

Do not assume reflection or `setAccessible(true)` automatically bypasses `private` restrictions. Reflection is subject to access checks and strong module encapsulation; relying on non-public details also makes code fragile.

## 11. Common Errors with Inherited Members

| Error | Cause | Correct approach |
|---|---|---|
| A cross-package subclass accesses a superclass package-private field directly | Package-private applies only within one package | Expose a necessary `protected`/`public` API or redesign |
| A cross-package subclass reads `base.protectedField` through `Base base` | Protected access also restricts qualifier types | Use `this`, `super`, suitably typed subclass references, or a public API |
| Unrelated code in another package invokes `child.protectedMethod()` | Not a subclass and not in the same package | Expose genuinely needed public behavior |
| Invoking `super.privateMethod()` | Superclass private members are not inherited/accessed this way | Use behavior the superclass deliberately exposes through public/protected APIs |
| Overriding a `public` method as `protected` | Reduces visibility relative to the superclass method | Keep it public or design another API |
| Adding `@Override` to a method named like a superclass private method | Private methods are not overridden | Treat it as a separate subclass declaration |
| Assuming superclass constructors are inherited | Constructors are not inherited members | Use `super(...)` to initialize the superclass portion |
| Letting subclasses freely modify protected fields | Easy to violate invariants | Prefer protected validating methods or composition |
| Assuming a `subpackage` is the same package | Java packages use complete qualified names | Respect package/module boundaries |
| Assuming `public` bypasses every JPMS boundary | Package/class must also be accessible to the consuming module | Design exported public APIs with suitable `exports` |

## 12. Practice

### Exercise 1: Predict the Result

~~~java
class Parent {
    private int value = 7;

    public int getValue() {
        return value;
    }
}

class Child extends Parent {}

Child child = new Child();
System.out.println(child.getValue());
~~~

**Answer:** Prints `7`. The `value` field is private, but the public `getValue()` method is inherited, and `Parent` code can read its own private field on a `Child` instance.

### Exercise 2: Two Packages

~~~java
// package alpha;
public class A {
    protected int number = 9;
}

// package beta;
public class B extends A {
    void print(A a, B b) {
        System.out.println(this.number);
        System.out.println(b.number);
        // System.out.println(a.number);
    }
}
~~~

Assume the classes are in valid files and packages. Which line in `print` fails compilation if uncommented?

**Answer:** `a.number`. Inside `B` in a different package, a protected instance member cannot be accessed through an expression statically typed as `A`. Both `this.number` and `b.number` are valid.

### Exercise 3: May an Override Widen Access?

~~~java
class A {
    protected void run() {}
}

class B extends A {
    @Override
    public void run() {}
}
~~~

**Answer:** Valid. `B.run()` widens visibility from protected to public. The opposite change—from public in the superclass to protected in the subclass—is invalid.

### Exercise 4: Constructors

~~~java
class Parent {
    protected Parent(int n) {}
}

class Child extends Parent {
    Child() {
        super(10);
    }
}
~~~

**Answer:** Subclass `Child` can invoke a protected superclass constructor through `super(10)` under constructor-invocation rules. It **does not inherit** `Parent(int)` as a constructor named `Child(int)`.

### Exercise 5: Preserving Invariants

A superclass has `protected int stock`; a subclass can assign `stock = -50`. How should the design change?

**Hint:** Make the field private and provide intentional `protected` or public methods, such as `receive(quantity)`, `reserve(quantity)`, and `ship(quantity)`, with validation. Subclasses should use permitted behavior rather than break invariants.

### Exercise 6: Field Hiding

~~~java
class P {
    public int number = 1;
}

class C extends P {
    public int number = 2;
}

P ref = new C();
System.out.println(ref.number);
~~~

**Answer:** Prints `1`. Java selects the field according to compile-time type `P` of `ref`. Field hiding should not serve as a polymorphism mechanism.

## 13. A Checklist for Determining Whether Access Is Legal

When reading expressions such as `obj.someMember` or `super.someMethod()`, ask in order:

1. **Where is the member declared?** Identify the superclass, member, modifier, and possible hiding/overriding.
2. **Which class and package contain the current code?** Being in one package permits package-private and protected access; cross-package subclasses follow additional rules.
3. **What is the receiver expression's compile-time type?** Particularly important for protected instance members declared in a different-package superclass.
4. **Is the member a field, instance method, static method, or constructor?** Overriding and dispatch rules depend on member kind.
5. **Is the type/module accessible?** With JPMS or package-private top-level classes, a `public` member alone may not be accessible.
6. **Is the access sound design?** Compilation success does not mean subclasses should directly mutate fields.

**Remember:** Inheritance lets subclasses reuse and extend superclass behavior, but `public`, `protected`, package-private, and `private` establish access boundaries. In Java, `protected` has special rules for subclasses outside the package; `private` is not inherited as an accessible API; constructors are not inherited. Design superclass methods with clear meaning and only the access needed to keep hierarchies usable without excessive dependency on internals.
