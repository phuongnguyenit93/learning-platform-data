# Default members and language-specific interface limitations

In OOP, **an interface** describes a capability or contract that different classes can implement. However, languages differ in which members interfaces may contain. Even within Java, interface features have evolved: besides abstract methods, modern Java supports **default methods (`default`)**, `static` methods, and `private` helper methods.

To understand the topic, distinguish two meanings of *default*:

- **Implicitly assigned modifiers:** for example, a regular signature-only method in a Java interface is implicitly `public abstract`; an interface field is implicitly `public static final`.
- **`default` methods:** methods with **an existing implementation body** in the interface, declared with the `default` keyword. Implementing classes may inherit or override that implementation under Java's rules.

Do not confuse **`default` on an interface method** with **package-private access**, often called “default access” in Java. They are entirely different concepts.

This lesson uses Java 17 to explain the rules, compile-ready examples, common errors, and differences when applying the concept in other languages.

## 1. Which members are permitted in Java interfaces?

| Member type | Supported in Java 17? | Meaning and limitations |
|---|---|---|
| `public abstract` method | Yes | Declares behavior that implementations must provide |
| `default` method | Yes (since Java 8) | Has a method body; implementations may reuse or override it |
| `public static` method | Yes (since Java 8) | Utility tied to the interface itself; called as `TenInterface.method()` |
| `private`, `private static` methods | Yes (since Java 9) | Internal helpers for interface methods with bodies |
| Field/constant | Yes | Every field is implicitly `public static final` and needs an initializer |
| Mutable instance field | No | A Java interface cannot directly store instance state |
| Constructor | No | Cannot directly instantiate an interface |
| Instance initializer block | No | There is no interface instance to initialize |
| `protected` / package-private methods | No | Interface methods follow valid `public` or `private` access rules |
| Nested interfaces | Yes | Can declare types nested in an interface, with their applicable modifier rules |
| Multiple interface inheritance | Yes | An interface can `extends` multiple interfaces |
| One class implementing multiple interfaces | Yes | Must resolve method conflicts according to Java rules |

Some syntax rules to remember:

~~~java
interface Auditable {
    String auditId();               // Ngầm là public abstract.
    int MAX_EVENTS = 100;           // Ngầm là public static final.

    default boolean canAudit() {    // Public default method.
        return !auditId().isBlank();
    }

    static boolean validId(String id) {
        return id != null && !id.isBlank();
    }

    private String normalizedId() {
        return auditId().strip();
    }
}
~~~

`normalizedId()` is a valid private helper here, although this small example does not call it. Non-`private` methods in an interface are generally public; fields cannot become per-object private variables.

### Why does `default` matter?

Before Java 8, adding an abstract method to an interface with many implementations usually required changes to those classes. A `default` method lets the interface provide **a valid common implementation**, allowing existing classes to adopt new behavior in many cases.

However, `default` does not guarantee compatibility for every change: method name collisions, inheritance, business semantics, and previously compiled code can still cause problems. Add a default method only when it provides behavior that is genuinely valid for every implementation to which it applies.

## 2. Complete Java example: abstract, default, static, and private

Imagine an application with different entities, such as users and invoices, whose names must be displayed. The `Named` interface declares the ability to provide a name and a common rule for constructing display labels.

An invoice plays both the `Named` and `Loggable` roles; each interface also provides `default label()`. The invoice class must resolve this conflict.

Save everything as **`Demo.java`** and use Java 17 or later:

~~~java
public class Demo {
    public static void main(String[] args) {
        User user = new User("  Lan  ");
        Invoice invoice = new Invoice("INV-07");

        System.out.println(user.label());
        System.out.println(user.shortLabel());
        System.out.println(invoice.label());
        System.out.println(Named.isValidName("  Mai  "));
        System.out.println(Named.MAX_NAME_LENGTH);
    }
}

// Hợp đồng: mọi đối tượng Named có thể trả về tên của nó.
interface Named {
    // Field của interface ngầm là public static final.
    int MAX_NAME_LENGTH = 40;

    // Phương thức trừu tượng ngầm là public abstract.
    String name();

    // Phương thức mặc định: có implementation chung.
    default String label() {
        return "Tên: " + normalize(name());
    }

    // Một default method có thể gọi abstract method và helper private.
    default String shortLabel() {
        String text = normalize(name());
        return text.length() <= 12
                ? text
                : text.substring(0, 12) + "...";
    }

    // Public static method: thuộc interface, không gắn với instance.
    static boolean isValidName(String candidate) {
        return candidate != null
                && !candidate.isBlank()
                && withinLimit(candidate.strip());
    }

    // Private instance method: helper cho default methods.
    private String normalize(String raw) {
        return raw.strip();
    }

    // Private static method: helper cho static method.
    private static boolean withinLimit(String text) {
        return text.length() <= MAX_NAME_LENGTH;
    }
}

// Một vai trò độc lập, tình cờ cũng có method label().
interface Loggable {
    default String label() {
        return "[log]";
    }
}

// Chỉ cần hiện thực abstract method name().
final class User implements Named {
    private final String displayName;

    User(String displayName) {
        if (!Named.isValidName(displayName)) {
            throw new IllegalArgumentException("Tên không hợp lệ");
        }
        this.displayName = displayName.strip();
    }

    @Override
    public String name() {
        return displayName;
    }
}

// Triển khai hai interface cùng có default label().
final class Invoice implements Named, Loggable {
    private final String number;

    Invoice(String number) {
        if (!Named.isValidName(number)) {
            throw new IllegalArgumentException("Mã không hợp lệ");
        }
        this.number = number;
    }

    @Override
    public String name() {
        return number;
    }

    // Bắt buộc giải quyết xung đột default label().
    @Override
    public String label() {
        return Named.super.label() + " | " + Loggable.super.label();
    }
}
~~~

Run:

~~~bash
javac Demo.java
java Demo
~~~

Output:

~~~text
Tên: Lan
Lan
Tên: INV-07 | [log]
true
40
~~~

**Explanation of notable points:**

1. `Named.name()` has no body: `User` and `Invoice` must implement it.
2. `Named.label()` and `Named.shortLabel()` have bodies: `User` inherits their default implementations without rewriting them.
3. `Named.isValidName(...)` is called by both class constructors. It is static, so it is called through **the interface name**.
4. `normalize()` and `withinLimit()` are private helpers inside `Named`. They are not exposed in the API callable by clients or implementing classes.
5. `MAX_NAME_LENGTH` is a shared constant; `User` and `Invoice` do not each get their own field copy.
6. `Invoice` cannot ambiguously inherit both `label()` defaults. It overrides the method and chooses the result, optionally invoking `Named.super.label()` or `Loggable.super.label()` to reuse both existing implementations.

This example shows **default behavior reuse without inheriting a stateful superclass**.

## 3. How default-method conflicts are resolved

Java allows classes to implement multiple interfaces, but does not arbitrarily select one implementation when methods have conflicting signatures.

Three practical rules:

| Situation | Rule |
|---|---|
| A superclass provides a matching instance method | The class method generally takes precedence over an interface default method (*class wins*) |
| A more specific subinterface overrides its parent interface's default | The more specific interface method is selected |
| Two unrelated default methods have the same signature | The implementing class must override the method to resolve the conflict |

### Case 1: class methods take precedence over interface defaults

~~~java
interface HasLabel {
    default String label() {
        return "interface";
    }
}

class Base {
    public String label() {
        return "class";
    }
}

class Derived extends Base implements HasLabel {}

class Test {
    public static void main(String[] args) {
        System.out.println(new Derived().label()); // class
    }
}
~~~

`Derived` inherits `label()` from `Base`. Java does not use the default `HasLabel.label()` to override the superclass method.

### Case 2: a more specific interface takes precedence

~~~java
interface ParentRole {
    default String role() { return "parent"; }
}

interface ChildRole extends ParentRole {
    @Override
    default String role() { return "child"; }
}

class Agent implements ParentRole, ChildRole {}

class Test {
    public static void main(String[] args) {
        System.out.println(new Agent().role()); // child
    }
}
~~~

Here `ChildRole` extends `ParentRole` and defines more specific behavior; that is the inherited implementation.

### Case 3: two unrelated defaults

~~~java
interface A {
    default String message() { return "A"; }
}

interface B {
    default String message() { return "B"; }
}

// class C implements A, B {} // Lỗi biên dịch: xung đột default.
class C implements A, B {
    @Override
    public String message() {
        return A.super.message() + B.super.message();
    }
}
~~~

When overriding, a class may write entirely new logic or use `InterfaceName.super.method()` to invoke a valid interface default method. This syntax has restrictions involving directly inherited interfaces and callable methods; it is not an arbitrary way to invoke defaults from any ancestor in the hierarchy.

High-level decision diagram:

~~~mermaid
flowchart TD
    A["Lời gọi instance method"] --> B{"Superclass có method phù hợp?"}
    B -->|Có| C["Ưu tiên implementation từ class"]
    B -->|Không| D{"Có default từ interface chuyên biệt hơn?"}
    D -->|Có| E["Chọn implementation chuyên biệt"]
    D -->|Không| F{"Có hai default độc lập xung đột?"}
    F -->|Có| G["Class phải override và giải quyết"]
    F -->|Không| H["Dùng default method hợp lệ"]
~~~

This diagram helps identify common situations; it does not replace the full method resolution rules in the Java Language Specification.

## 4. Modifier rules that are easy to misunderstand

### 4.1. Signature-only methods are `public abstract`

The following two declarations are equivalent:

~~~java
interface Vehicle {
    void move();
    public abstract int speed();
}
~~~

A non-abstract implementing class must declare its method `public`:

~~~java
class Bicycle implements Vehicle {
    @Override
    public void move() {
        System.out.println("Đang di chuyển");
    }

    @Override
    public int speed() {
        return 12;
    }
}
~~~

The following is invalid:

~~~java
// class BrokenBicycle implements Vehicle {
//     void move() {}   // Lỗi: đang giảm quyền truy cập public.
//     public int speed() { return 12; }
// }
~~~

An interface method cannot be made `protected` or package-private simply because its implementing class does not want it public.

### 4.2. `default` denotes a method with a body

~~~java
interface Greeting {
    default String greet() {
        return "Xin chào";
    }
}
~~~

Here, `default` **does not** mean package-private. Clients can publicly invoke the method through an interface reference. You cannot freely combine `default` with `abstract`, `static`, or `private` on the same method: each modifier has its own validity rules.

An implementation may override it:

~~~java
class FormalGreeting implements Greeting {
    @Override
    public String greet() {
        return "Kính chào quý khách";
    }
}
~~~

When overriding, preserve the required access level and honor the behavioral contract.

### 4.3. `static` methods must be called through the interface name

~~~java
interface TextTools {
    static boolean isBlank(String text) {
        return text == null || text.isBlank();
    }
}

System.out.println(TextTools.isBlank("  ")); // true
~~~

The `System.out.println` call belongs inside an appropriate Java method. Do not write `new TextTools()` because an interface has no constructor. An interface static method **is not inherited as an instance method** by its implementing class:

~~~java
class TextService implements TextTools {}

// TextService.isBlank("x"); // Không hợp lệ với static interface method.
// new TextService().isBlank("x"); // Cũng không hợp lệ.
~~~

Unlike instance default methods, `static` methods do not participate in polymorphic overriding based on an object's type. If a class declares a static method with the same name/signature, it is a separate declaration, not an override of the interface's static method.

### 4.4. `private` methods are internal implementation details

~~~java
interface GreetingFactory {
    default String greetUser(String name) {
        return wrap("Xin chào " + normalize(name));
    }

    static String greetGuest() {
        return wrapStatic("Xin chào khách");
    }

    private String normalize(String name) {
        return name == null ? "bạn" : name.strip();
    }

    private String wrap(String value) {
        return "[" + value + "]";
    }

    private static String wrapStatic(String value) {
        return "[" + value + "]";
    }
}
~~~

Private interface methods have bodies and are callable only from appropriate code **inside the interface itself**. Clients cannot call them, implementing classes cannot override them as part of the contract, and they cannot be abstract. Java 17 supports both private instance and private static interface methods.

A `private static` helper can be called from other interface methods, whereas a private instance method requires an interface instance context. The forms serve different purposes.

## 5. Interface fields are always public static final

This is especially important:

~~~java
interface Limits {
    int MAX_ITEMS = 100;
}
~~~

Java interprets the declaration above as equivalent to:

~~~java
interface Limits {
    public static final int MAX_ITEMS = 100;
}
~~~

`MAX_ITEMS` is **a constant associated with the interface**, not an item count for each instance.

You cannot write:

~~~java
// interface Wrong {
//     private int count = 0;  // Lỗi: field không thể private.
//     int count;              // Lỗi: field cần initializer.
// }
~~~

Even with `final`, a reference constant may still point to a **mutable** object:

~~~java
import java.util.ArrayList;
import java.util.List;

interface Settings {
    List<String> CODES = new ArrayList<>();
}

// Settings.CODES = new ArrayList<>(); // Lỗi: không gán lại field final.
// Settings.CODES.add("A1");          // Vẫn có thể sửa nội dung List!
~~~

This field is implicitly `public static final`, which **does not mean its list is immutable**. Exposing a mutable object as a constant is risky because callers can modify shared state without control.

Prefer an appropriate immutable representation, for example:

~~~java
interface SupportedCodes {
    List<String> VALUES = List.of("A1", "B2");
}
~~~

In real projects, if constants only concern one group of features, consider a `final` class or clearly named configuration instead of using an interface as a “constant repository” (*constant interface anti-pattern*).

Also, **interface fields must be initialized**, but not every initializer is necessarily a compile-time constant under JLS terminology. For example, `new Object()` is allowed, although shared state and lifecycle implications require care.

## 6. Interfaces have no instance state, constructor, or separate lifecycle

An interface cannot directly declare a mutable field that belongs independently to each implementing object:

~~~java
// interface Session {
//     int requestCount = 0; // Đây vẫn là static final, không phải instance.
//     Session() {}          // Không có constructor interface.
// }
~~~

If each session needs its own request counter, the implementing class stores the field:

~~~java
interface SessionCounter {
    int getRequestCount();
    void recordRequest();
}

final class UserSession implements SessionCounter {
    private int requestCount;

    @Override
    public int getRequestCount() {
        return requestCount;
    }

    @Override
    public void recordRequest() {
        requestCount++;
    }
}
~~~

Interfaces declare what a session can do; classes store state and implement behavior. Default methods may call getters/abstract methods to use an implementing object's state, but the interface itself **does not allocate separate instance fields**.

An interface cannot be instantiated using `new SessionCounter()`. You can instantiate an implementing class, or use an anonymous class/lambda when the interface type permits it.

## 7. Special restrictions involving `Object` methods

Every Java object has public methods such as `toString()`, `equals(Object)`, and `hashCode()` from `Object`. An interface may declare corresponding abstract signatures to describe a contract, but may not provide default implementations for methods matching public non-static methods of `Object`.

Invalid example:

~~~java
// interface Described {
//     default String toString() { // Lỗi biên dịch.
//         return "Đối tượng";
//     }
// }
~~~

To customize `toString()`, override it in a concrete **class**:

~~~java
interface Described {
    String description();
}

final class Note implements Described {
    private final String text;

    Note(String text) {
        this.text = text;
    }

    @Override
    public String description() {
        return text;
    }

    @Override
    public String toString() {
        return "Note[" + text + "]";
    }
}
~~~

The reason is that rules governing interactions between `Object` methods and interface methods differ from providing a default for an ordinary business operation. This is a Java-specific restriction; do not assume every language with interfaces applies precisely the same rule.

## 8. Interfaces may extend interfaces, but not classes

A Java interface can extend multiple interfaces:

~~~java
interface Readable {
    String read();
}

interface Writable {
    void write(String text);
}

interface ReadWrite extends Readable, Writable {
    default boolean canEdit() {
        return true;
    }
}
~~~

A class implementing `ReadWrite` must fulfill `read()` and `write()` unless it is abstract or valid implementations are already inherited from a superclass.

An `interface` cannot `extends` a class:

~~~java
// class Base {}
// interface Wrong extends Base {} // Lỗi.
~~~

A **class** may directly `extends` only one class but may `implements` multiple interfaces:

~~~java
class BasicDocument {}

class EditableDocument extends BasicDocument
        implements Readable, Writable {
    @Override
    public String read() {
        return "Nội dung";
    }

    @Override
    public void write(String text) {
        // Implementation minh họa.
    }
}
~~~

This enables **multiple roles** without forcing every class into a complex implementation inheritance tree.

### Default methods do not provide state inheritance

Multiple interfaces with default implementations do not turn Java into a language allowing a class to inherit several superclasses with instance fields, constructors, and initialization logic. Java still distinguishes **inheriting implementation from one class** from **implementing multiple interface contracts**.

## 9. Interfaces versus abstract classes: how do default methods differ from ordinary methods?

An interface default method and an abstract class's concrete method both have bodies, but play different design roles.

| Criterion | Interface with default methods | Abstract class with concrete methods |
|---|---|---|
| Instance fields | No | Yes |
| Constructors | No | Yes |
| How many can a class inherit from? | Can implement multiple interfaces | Can directly extend at most one class |
| Best suited for | Shared behavior derived from a capability/contract | Shared behavior and state of a class family |
| Method collision handling | Default-conflict rules apply; overrides may be necessary | Class method inheritance follows the class hierarchy |
| Can instance methods be `protected`? | No | Yes |
| Can have `private` helpers? | Yes | Yes |

For example, an abstract class can store shared state:

~~~java
abstract class BaseWorker {
    protected int completedJobs;

    protected BaseWorker() {
        completedJobs = 0;
    }

    public void markCompleted() {
        completedJobs++;
    }

    public abstract void perform();
}
~~~

An interface can simply specify:

~~~java
interface Worker {
    void perform();
    default boolean isAvailable() {
        return true;
    }
}
~~~

If a group of classes needs a common constructor, fields, and invariants, an abstract class or **composition** may be more suitable. If unrelated class types only need a shared capability, an interface is more appropriate. There is no rule that “default methods are always better than abstract classes.”

## 10. How does Java differ from other languages?

The idea of “an interface as a contract” is broadly applicable, but syntactic restrictions and implementation capabilities **depend on the language and version**.

| Language | Can an interface provide an implementation? | State and distinctive capabilities |
|---|---|---|
| **Java 17** | Yes, through `default`; also `static` and `private` methods | No interface instance fields/constructors; fields are implicitly `public static final` |
| **Modern C#** | Can provide default interface implementations | Its member, property, and implementation rules differ from Java; do not copy Java rules directly |
| **Kotlin** | Interface methods may have bodies | Interfaces may declare properties with accessors but no separate backing fields |
| **TypeScript** | Interfaces specify static types without runtime method implementations | Uses structural typing; interfaces are erased when compiling to JavaScript |

A roughly equivalent example in TypeScript:

~~~typescript
interface Greeter {
  greet(name: string): string;
}

class FriendlyGreeter implements Greeter {
  greet(name: string): string {
    return "Hello " + name;
  }
}
~~~

TypeScript interfaces do not directly contain executable code like Java `default method` implementations. To reuse implementations, TypeScript commonly uses classes, functions, mixins, or composition as appropriate.

In Kotlin, an interface can declare a property with an accessor but cannot store that property's backing field inside the interface as a regular class can. In C#, interface features and attached implementations depend on language/runtime versions. The presence of a feature similar to Java `default` does not mean that conflict, inheritance, and dispatch rules are identical.

In particular, **“interface” does not always mean “a construct containing only empty method signatures”** across languages and versions. When moving projects among Java, Kotlin, C#, and TypeScript, consult the relevant syntax, state-modeling, and execution rules for the technologies in use.

## 11. How Java interfaces have evolved

| Era | Notable capabilities |
|---|---|
| Before Java 8 | Interfaces mainly held abstract methods and constants, without modern default/static interface methods |
| Java 8 | Added `default` and `static` methods to interfaces |
| Java 9 | Added private instance/static helper methods to interfaces |
| Java 17 | Supports all of the above; Java also supports sealed classes/interfaces to restrict which types may extend them |

A sealed interface example (Java 17):

~~~java
sealed interface PaymentResult permits Approved, Declined {}

record Approved(String transactionId) implements PaymentResult {}
record Declined(String reason) implements PaymentResult {}
~~~

This is **a restriction on the set of classes permitted to implement the interface**, rather than a kind of default method. `permits` lists allowed direct subclasses; those classes follow applicable rules such as `final`, `sealed`, or `non-sealed` according to context.

Since the exercises use Java 17, the interface `private` method and sealed-interface examples will not compile unchanged on much older Java versions.

## 12. Using default methods responsibly

Default methods should not hide complex business logic or global state. A good default method usually:

- **Builds on existing contract methods**, as `label()` does by calling `name()`.
- Has a sensible implementation for **every implementation** that inherits the default.
- Does not assume the implementing class has particular fields, constructors, or internal structures.
- Preserves business meaning and clearly defines exceptions and side effects.
- Is tested when multiple inherited or implemented interfaces interact.

For example, `label()` derived from `name()` is natural. But a default `saveToDatabase()` that assumes every class has a connection, transaction, and table would be an unreliable abstraction unless the contract actually provides the required capabilities and rules.

### What are the risks of interface evolution?

Suppose a public interface has already been implemented by several plugins. Adding a new default method may mean:

1. Existing implementations **may** use it without adding a method.
2. If a class already declares a method with the same name/signature but incompatible access, source compatibility errors may occur.
3. If a plugin also implements another interface with the same default method signature, conflicts may arise.
4. If the default method introduces a new precondition or changes side effects, clients may encounter unexpected behavior.
5. Source, binary, and behavioral compatibility are distinct; verify each for the library's distributed version.

Thus `default` **reduces one kind of required change** when expanding interfaces; it does not give us permission to modify public APIs without testing.

## 13. Common compilation errors and misconceptions

| Mistake | Why it is wrong | Fix |
|---|---|---|
| Assuming all interface methods are abstract | Java 8+ permits `default`/`static`; Java 9+ permits `private` | Distinguish methods by modifier |
| Using `default` to mean package-private access | `default` on an interface method provides a public default implementation | Distinguish the `default` keyword from omitting access modifiers on a class |
| Calling a static method through an implementing object | Static interface methods are not inherited as instance methods | Use `InterfaceName.method()` |
| Declaring `private int count` in an interface | Fields are implicitly `public static final` | Put per-instance state in the implementing class |
| Assuming the contents of a `final List` field are immutable | Final prevents reassigning the reference only | Use immutable data/collections and manage state |
| Implementing two interfaces with the same default method without overriding | There is no automatic selection between unrelated defaults | Override to resolve it |
| Implementing an interface method with package-private access | Abstract interface methods are implicitly public | Override as `public` |
| Declaring `default toString()` in an interface | Cannot provide a default overriding a public non-static `Object` method | Override `toString()` in the class |
| Treating private interface helpers as APIs for implementations | Private helpers are not inherited contract members | Expose a suitable capability or keep helpers internal |
| Using interfaces merely to replace every class | Adds unnecessary abstractions while lacking shared state | Choose interfaces, classes, abstract classes, or composition by need |
| Copying syntax from another language | Interface rules differ between languages | Verify features by language and version |

## 14. Knowledge check

**Question 1.** An interface declares `int LIMIT = 10;`. Is `LIMIT` a separate field in every instance?

**Answer:** No. In a Java interface, fields are implicitly `public static final`; they belong to the interface and are initialized according to class/interface rules.

**Question 2.** A class implements an interface with `default greet()` but does not override it. Can code call `greet()` on a class instance?

**Answer:** Yes, provided there is no conflict or another rule that overrides the behavior. The class may inherit a valid default implementation.

**Question 3.** Two unrelated interfaces both declare `default String message()`. Can a class implementing both leave its body empty?

**Answer:** No. The class must override `message()` and select or combine suitable behavior.

**Question 4.** Can `User.isValidName("Lan")` replace `Named.isValidName("Lan")` when `User implements Named`?

**Answer:** No. Interface static methods are not inherited by `User`; they must be invoked through the declaring interface name.

**Question 5.** Can an interface in Java 17 declare a `private String normalize(...)` method with a body?

**Answer:** Yes. It is a private interface helper, not a method that implementing classes can override or clients can invoke.

**Question 6.** Should `default` implement an operation that directly modifies a `balance` field provided by only a few implementations?

**Answer:** Not when the interface lacks a shared contract and capabilities for that operation. Put the behavior in an appropriate class or define a narrower interface for classes that genuinely support it.

**Question 7.** Must Java and TypeScript interfaces have identical runtime behavior?

**Answer:** No. Java interfaces may provide executable default methods; TypeScript interfaces primarily enforce types at compile time and do not generate corresponding runtime implementations.

## Guidelines for applying these rules

When designing or reading a Java interface, identify **which methods implementers must supply**, **which methods already have shared implementations**, **which members belong to the interface itself**, and **which state belongs in implementing classes**.

Use `default` for genuinely meaningful shared behavior, `static` for contract-related utilities, and `private` for internal code reuse without expanding the public API. When combining interfaces, check default-method conflicts and inheritance rules. More broadly, consult the actual limits of each language and version instead of assuming “interface” follows Java's rules everywhere.
