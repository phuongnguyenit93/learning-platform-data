# Method Overriding and Checking with `@Override` in Java

**Method overriding** is the mechanism by which a subclass provides a new implementation for an **instance method** inherited from a superclass, or implements a method according to an interface contract. This is a cornerstone of **runtime polymorphism**: the same call on a variable of a superclass type can execute the subclass's implementation depending on the **actual type of the object**.

The `@Override` annotation helps the compiler verify that intention. If you mistype the name, use the wrong parameter types, or the method is actually just a new overload, the compiler reports an error instead of letting a similarly named method exist without being called as expected.

This lesson belongs to **Java core - class-object**, in the **Inheritance and Polymorphism** group. The content explains the overriding contract, the distinction from overloading, static hiding and field hiding, constraints on access levels, return types, and exceptions, how to use `super`, interface/default methods, generic bridge methods, common pitfalls, along with Java **17+** hands-on experiments with clear stdout.

## 1. The Idea Through a Small Example

The superclass defines a behavior that can be changed:

~~~java
class Animal {
    String sound() {
        return "unknown";
    }
}
~~~

The subclass provides a specialized behavior:

~~~java
class Cat extends Animal {
    @Override
    String sound() {
        return "meow";
    }
}
~~~

These two snippets are **illustrative class definitions** that can be placed in the same package. With the variable `Animal animal = new Cat();`, calling `animal.sound()` executes the `Cat.sound()` version and returns `"meow"`.

Let's separate two concepts:

- **Reference type at compile time:** `Animal`. The compiler uses it to check whether the `sound()` call is valid and which signature is selected.
- **Actual object type at runtime:** `Cat`. For an overridable instance method, Java selects the appropriate implementation based on the actual object.

`@Override` **does not create polymorphism**. Polymorphism is already defined by Java semantics. The annotation serves as a **compile-time check** and clarifies the intent for readers.

## 2. Complete Program 1 — Polymorphism with Overriding

Create the file **`OverrideBasicsDemo.java`**:

~~~java
class Creature {
    String describe() {
        return "creature";
    }

    String sound() {
        return "?";
    }
}

class Bird extends Creature {
    @Override
    String describe() {
        return "bird";
    }

    @Override
    String sound() {
        return "chirp";
    }
}

class Dog extends Creature {
    @Override
    String sound() {
        return "woof";
    }
}

public class OverrideBasicsDemo {
    static void print(Creature creature) {
        System.out.println(creature.describe()
                + " => " + creature.sound());
    }

    public static void main(String[] args) {
        Creature first = new Bird();
        Creature second = new Dog();
        Creature third = new Creature();

        print(first);
        print(second);
        print(third);
        System.out.println("bird by parent ref="
                + first.sound());
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 OverrideBasicsDemo.java
java OverrideBasicsDemo
~~~

**Exact stdout:**

~~~text
bird => chirp
creature => woof
creature => ?
bird by parent ref=chirp
~~~

**Analysis:**

- `Bird` overrides `describe` and `sound`; both calls execute the Bird version.
- `Dog` only overrides `sound`; it **inherits** `describe` from `Creature`, so the result is `creature => woof`.
- `Creature` does not need to override anything; when the actual object is a Creature, it uses Creature's own method.
- The `print(Creature)` method does not know specifically which subclass the object belongs to. It calls the same API, yet receives behavior depending on the object.

This is an important purpose of polymorphism: **code depends on a common contract**, while different object types provide different implementations.

## 3. What Does `@Override` Do?

When placed immediately before a method declaration:

~~~java
@Override
public String toString() {
    return "my object";
}
~~~

the compiler checks that the method actually overrides or implements a matching method from a supertype according to Java rules. If there is no suitable method to override, it reports a **compile-time error**.

Practical benefits:

1. **Catching typos:** `toStirng` does not accidentally become a separate method that is never called via `toString`.
2. **Catching parameter mismatches:** `draw(int)` is not mistaken for an override of `draw()`.
3. **Self-documenting:** readers recognize that this is an implementation of inherited behavior, not an entirely new method.
4. **Protection during refactoring:** if the supertype contract changes its name or changes its signature incompatibly, the compiler can detect that the subclass method no longer overrides it.
5. **Keeping intent clear during code reviews:** especially useful in systems with many subclasses.

This annotation is declared in `java.lang`, so normally **no import is needed** to write `@Override`. It is used on **method declarations**, not on fields or constructors.

Key point to remember: **omitting `@Override` does not mean the method does not override**. If the signature and rules are satisfied, Java still performs overriding as usual. Even so, in modern code, you should consistently use the annotation on methods that genuinely override.

## 4. Signature Errors Caught by `@Override`

Suppose the superclass has:

~~~java
class Canvas {
    void draw(int size) {
        System.out.println("Canvas size=" + size);
    }
}
~~~

Incorrect way:

~~~java
class BrokenCanvas extends Canvas {
    @Override
    void draw(long size) {
        System.out.println("Broken size=" + size);
    }
}
~~~

This is an **intentionally non-compiling example**: `draw(long)` differs from `draw(int)`, so it is an **overload** method, not an override of the superclass method. The annotation causes the compiler to reject it with an error such as “method does not override or implement a method from a supertype”.

The right way if you want to override:

~~~java
class FixedCanvas extends Canvas {
    @Override
    void draw(int size) {
        System.out.println("Fixed size=" + size);
    }
}
~~~

Both classes `Canvas` and `FixedCanvas` can be placed in the same file in the same package. Calling `Canvas c = new FixedCanvas(); c.draw(4);` will print `Fixed size=4`.

If you want to add `draw(long)` as a genuine overload, you can still do so, **but without attaching `@Override`** and you need to understand which overload the compiler selects at the call site.

## 5. Fundamental Differences Between Override and Overload

| Aspect | Overriding | Overloading |
| --- | --- | --- |
| Relationship | Method inherited/implemented from a supertype | Multiple methods with the same name, different parameter lists |
| Primary decision | Selects the instance implementation at runtime | Selects the appropriate signature at compile time |
| Name | Must match the supertype method | Same name |
| Parameters | Must satisfy the corresponding signature/subsignature | Must differ in type list/order/count |
| Return type | Must be return-type-substitutable | Return type alone is not enough to create an overload |
| `@Override` | Should be used | Not used for pure overloads |
| Static method | Not overridden in the sense of instance polymorphism | Can be overloaded; with a subclass, there is also hiding |

**Rule of thumb:** the compiler first decides **which method signature is called**, and then the runtime dispatches the instance implementation **if that method can be overridden**. Do not say “Java always chooses by runtime type” while ignoring the compile-time overload selection step.

## 6. Complete Program 2 — Overload Is Selected First, Override Is Dispatched Later

Create the file **`OverloadOverrideDemo.java`**:

~~~java
class BasePrinter {
    String print(Object value) {
        return "base:Object";
    }
}

class FancyPrinter extends BasePrinter {
    @Override
    String print(Object value) {
        return "fancy:Object";
    }

    String print(String value) {
        return "fancy:String";
    }
}

public class OverloadOverrideDemo {
    public static void main(String[] args) {
        BasePrinter asBase = new FancyPrinter();
        FancyPrinter asFancy = new FancyPrinter();

        System.out.println("base ref="
                + asBase.print("hello"));
        System.out.println("fancy ref="
                + asFancy.print("hello"));
        System.out.println("object cast="
                + asFancy.print((Object) "hello"));
        System.out.println("null="
                + asFancy.print(null));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 OverloadOverrideDemo.java
java OverloadOverrideDemo
~~~

**Stdout:**

~~~text
base ref=fancy:Object
fancy ref=fancy:String
object cast=fancy:Object
null=fancy:String
~~~

Line-by-line explanation:

- The variable `asBase` has declared type `BasePrinter`. At compile time, the compiler only considers the signatures available through that type, choosing `print(Object)`. At runtime, it sees a `FancyPrinter` object and therefore runs the **overridden version** `FancyPrinter.print(Object)`.
- The variable `asFancy` has type `FancyPrinter`, so the compiler sees both `print(Object)` and `print(String)`; for a string, the more specific `String` overload is selected.
- When cast to `(Object)`, the `Object` overload is selected, even though the actual object is still a string.
- With `null`, `String` is more specific than `Object`, so Java selects `print(String)`. If two overloads exist whose parameter types are unrelated, a `null` call can become **ambiguous** and fail to compile.

Do not rely on `@Override` to “replace” the overload selection step. These are two mechanisms that work together but have **different roles**.

## 7. Method Signatures in Overriding

In the basic case, the **same name** and a **parameter list compatible under signature/subsignature rules** are required. The return type is not part of what distinguishes two ordinary overloaded methods.

Example:

~~~java
class Report {
    void export(String format) {
    }
}

class CsvReport extends Report {
    @Override
    void export(String format) {
    }
}
~~~

The two classes above are **valid illustrative code**, in the same package. The `@Override` annotation is valid because `CsvReport.export(String)` overrides the corresponding method in `Report`.

The following changes **are not the same signature**:

- `export(Object)` instead of `export(String)`.
- `export(String, boolean)` instead of `export(String)`.
- `export(String... formats)` instead of `export(String)` (varargs is a `String[]` array, different from `String`).
- `Export(String)` with an uppercase initial letter compared to `export(String)` in lowercase.

Another misconception: a method with a different return type but the same name and parameters **does not automatically become a valid new overload**. Java does not support distinguishing overloads solely by return type.

### Varargs and Arrays

In Java, varargs `String...` has a method signature based on `String[]`. A method with `String[]` in the supertype can be overridden with a matching varargs declaration, although a mismatch in the varargs modifier can lead to warnings or make the code harder to read. When overriding an API, you should keep **a consistent parameter declaration** so callers are not surprised.

## 8. Access Level Rules: Must Not Narrow

When overriding an instance method, the access level of the subclass method **must not be more restrictive** than that permitted by the superclass method:

| Supertype method | Typical valid overriding method |
| --- | --- |
| `public` | `public` |
| `protected` | `protected` or `public` |
| Package-private, if the method is actually inherited/overridden under the package conditions | Appropriate package-private, `protected`, or `public` |
| `private` | **Cannot override** a private method of the superclass |

Illustrative example:

~~~java
class BaseTask {
    protected String status() {
        return "base";
    }
}

class PublicTask extends BaseTask {
    @Override
    public String status() {
        return "ready";
    }
}
~~~

This is valid code: widening from `protected` to `public` is allowed.

An **intentionally non-compiling** example:

~~~java
class BrokenTask extends BaseTask {
    @Override
    private String status() {
        return "hidden";
    }
}
~~~

The subclass method cannot lower the access level of the overridden `protected` method, and `private` cannot be used to override a superclass method in this way.

**Cross-package note:** package-private methods in a superclass from a different package have their own inheritance/overriding rules; do not simply assume every method with the same name in two classes is an override. `@Override` helps the compiler specifically check this.

## 9. Covariant Return: The Return Type Can Be More Specific

An overriding method does not necessarily have to have the **exact same return type by name** when returning a reference. Java allows a return type that satisfies the **return-type-substitutability** relationship; the common case is a **covariant return**: the subclass returns a more specific subtype.

Example:

~~~java
class Resource {
    String id() {
        return "resource";
    }
}

class ImageResource extends Resource {
    @Override
    String id() {
        return "image";
    }
}

class Creator {
    Resource create() {
        return new Resource();
    }
}

class ImageCreator extends Creator {
    @Override
    ImageResource create() {
        return new ImageResource();
    }
}
~~~

The definitions above are valid illustrative code. `ImageCreator.create()` has the return type `ImageResource`, which is a subtype of `Resource` declared by the superclass.

You cannot arbitrarily change `int` to `long` or `double` and call that a covariant return. For primitives and `void`, the return type rules are **stricter**: widening conversions cannot be used to make an override valid.

## 10. Complete Program 3 — Visibility, Covariance, and Checked Exceptions

Create the file **`OverrideRulesDemo.java`**:

~~~java
import java.io.IOException;

class BaseLoader {
    protected Number load() throws IOException {
        return 1;
    }
}

class FastLoader extends BaseLoader {
    @Override
    public Integer load() {
        return 42;
    }
}

public class OverrideRulesDemo {
    public static void main(String[] args) throws IOException {
        BaseLoader loader = new FastLoader();
        Number value = loader.load();

        System.out.println("value=" + value);
        System.out.println("runtime type="
                + value.getClass().getSimpleName());

        FastLoader direct = new FastLoader();
        Integer moreSpecific = direct.load();
        System.out.println("direct=" + moreSpecific);
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 OverrideRulesDemo.java
java OverrideRulesDemo
~~~

**Stdout:**

~~~text
value=42
runtime type=Integer
direct=42
~~~

Rules demonstrated here:

1. `BaseLoader.load()` is `protected`; `FastLoader.load()` widens it to `public`.
2. The superclass returns `Number`; the subclass validly returns `Integer` because `Integer extends Number`.
3. The superclass declares `throws IOException`; the subclass **does not need** to declare any checked exception.
4. When calling through the `BaseLoader` variable, the compiler checks the `load() throws IOException` contract, so `main` declares `throws IOException`.
5. Runtime dispatch still executes `FastLoader.load()`, returning 42.

If the subclass method tries to declare a **broader checked exception** not permitted by the superclass method's contract, the compiler will reject it. For example, if the superclass method only declares `IOException` but the subclass method declares `throws Exception`, that is invalid. For unchecked exceptions such as `RuntimeException`, the `throws` restriction rules are different; you should not treat all exceptions the same.

## 11. Exception Rules When Overriding

When a superclass method declares checked exceptions, an overriding method **must not arbitrarily broaden** the types of checked exceptions that callers are forced to handle.

Valid example:

~~~java
class ParentReader {
    void read() throws java.io.IOException {
    }
}

class ChildReader extends ParentReader {
    @Override
    void read() throws java.io.FileNotFoundException {
    }
}
~~~

`FileNotFoundException` is a subclass of `IOException`, so declaring a narrower checked exception is appropriate.

An **intentionally non-compiling** example:

~~~java
class BadReader extends ParentReader {
    @Override
    void read() throws Exception {
    }
}
~~~

`Exception` is broader than `IOException`, so it violates the checked exceptions contract of the overridden method.

A subclass may also declare no checked exceptions at all when its implementation handles errors internally. Conversely, a caller using a superclass-type reference **still sees the superclass's throws signature at compile time**, even if the actual object has an implementation that does not throw that exception.

### Does `@Override` Cause These Restrictions?

No. Signature, access level, return type, and `throws` are **the language's overriding rules**. The annotation only clarifies and verifies intent. Removing the annotation **does not** turn an illegal override into a valid one.

## 12. Which Methods Cannot Be Overridden?

Cases to distinguish:

| Member | Overriding? | Related mechanism |
| --- | --- | --- |
| Inheritable, non-`final` instance method | Yes, when rules are met | Virtual dispatch |
| `final` instance method | **No** | Cannot write an override in a subclass |
| `private` method in superclass | **No** | Not inherited as an overridable method; a method with the same name in a subclass is independent |
| `static` method | **No** | Static method hiding if matching signature |
| Constructor | **No** | Constructors are not inherited |
| Field | **No** | Field hiding; access is based on the reference type |
| `abstract` instance method | Can be / is implemented | Concrete subclass provides implementation |
| Interface abstract/default method | Can be implemented/overridden | Interface and default method rules |
| `Object.getClass()` | **No** | A `final` method in `Object` |

The `final` keyword placed on a **class** also prevents that class from having subclasses. A `final` class can still override methods inherited from its superclass or implement interfaces within **that class itself**, but no other class can `extends` it.

A `private` method in a superclass cannot be overridden because it is not an inherited method eligible for overriding under the corresponding semantics. A method with the same name in a subclass can exist independently, but it does not provide a **polymorphic replacement** for calls to the superclass's private method.

## 13. Static Method Hiding Is Not Method Overriding

`@Override` is used to check **instance method overrides** (and method implementations from interfaces) according to Java rules. You cannot use this annotation to turn a `static method` into a virtual method:

~~~java
class BaseView {
    static String label() { return "base"; }
    String kind() { return "base instance"; }
}
class SpecialView extends BaseView {
    static String label() { return "special"; } // Hiding.
    @Override String kind() { return "special instance"; }
}
~~~

The example above consists of valid class declarations without a `main`. With a reference `BaseView ref = new SpecialView();`, `ref.label()` selects BaseView.label() according to the static type, whereas `ref.kind()` dispatches to `SpecialView.kind()`. Do not add `@Override` before `SpecialView.label()`: the compiler will reject it because static methods **do not override**.

This rule is mentioned here so you know **when `@Override` is invalid**. The lesson **“Field and Static Method Hiding by Declared Type”** analyzes lookup, static hiding, fields, and casting scenarios in full. To achieve runtime polymorphism, use instance methods instead of static methods.

## 14. Why Is Field Hiding Easily Confused with Overriding?

Consider:

~~~java
class ParentState {
    int value = 1;

    int readValue() {
        return value;
    }
}

class ChildState extends ParentState {
    int value = 2;

    @Override
    int readValue() {
        return value;
    }
}
~~~

The two classes above are valid illustrative code. If:

~~~java
ParentState state = new ChildState();
~~~

then:

- `state.value` reads the field `ParentState.value`, returning 1.
- `state.readValue()` executes the method `ChildState.readValue()`, returning 2.

This is a difference between **field access vs virtual method invocation**, not a compiler error. Even so, having the same field name in both parent and child often makes code hard to read. In domain design, you should make fields `private`, provide query methods with clear contracts, and avoid unnecessary field shadowing/hiding.

## 15. Using `super` to Call the Superclass Version

Overriding does not require **completely replacing** the superclass implementation. A subclass can extend the behavior using `super.method(...)`:

~~~java
class BasicLogger {
    void log(String message) {
        System.out.println("base: " + message);
    }
}

class AuditedLogger extends BasicLogger {
    @Override
    void log(String message) {
        super.log(message);
        System.out.println("audit: " + message);
    }
}
~~~

This is valid illustrative code. When calling `new AuditedLogger().log("saved")`, the overriding method runs and explicitly calls the superclass's version before logging the additional audit information.

However, `super` **does not automatically disable virtual dispatch for other calls deep inside the superclass method**. If `super.log()` calls an overridable instance method such as `format()`, the `format()` call from the superclass body can still dispatch to the subclass.

## 16. Complete Program 4 — `super` and Dispatch Inside the Superclass Method

Create the file **`SuperDispatchDemo.java`**:

~~~java
class BaseLogger {
    String format(String value) {
        return "[" + value + "]";
    }

    void log(String value) {
        System.out.println("base.log="
                + format(value));
    }
}

class JsonLogger extends BaseLogger {
    @Override
    String format(String value) {
        return "{value:" + value + "}";
    }

    @Override
    void log(String value) {
        super.log(value);
        System.out.println("child.log="
                + format(value));
    }
}

public class SuperDispatchDemo {
    public static void main(String[] args) {
        BaseLogger logger = new JsonLogger();
        logger.log("ok");
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 SuperDispatchDemo.java
java SuperDispatchDemo
~~~

**Stdout:**

~~~text
base.log={value:ok}
child.log={value:ok}
~~~

`logger.log("ok")` selects the `JsonLogger.log` implementation. Inside it, `super.log(value)` executes the body of `BaseLogger.log`; however, the **`format(value)` call inside the BaseLogger method** is still an instance call on the actual `JsonLogger` object, so it selects `JsonLogger.format`.

**`super.method()` only specifies the superclass method to be called at that exact call site**; it does not create a separate parent object or lock all internal calls to the superclass.

Additionally, `super` cannot be used arbitrarily from a static context as if it were an instance. It has meaning within the inheritance context of an instance.

## 17. Interface Methods and `@Override`

When a class implements an interface, the methods fulfilling the interface contract are also commonly marked with `@Override`:

~~~java
interface Drawable {
    void draw();
}

class Circle implements Drawable {
    @Override
    public void draw() {
        System.out.println("circle");
    }
}
~~~

**Access level note:** interface methods of the form above are `public abstract` by default. Therefore, the implementation must be **`public`**; omitting `public` on `Circle.draw()` makes the access level narrower than the contract and will not compile.

Since Java 6, using `@Override` to mark methods implementing an interface contract has been a familiar syntax supported by the compiler. In Java 17, there is no reason to omit the annotation just because a method comes from an interface rather than a superclass.

Another subclass can inherit the implementation from a superclass that has already implemented the interface; there is no need to re-implement it if the contract is already satisfied.

## 18. Default Methods and Conflicts from Two Interfaces

An interface can provide a **default method**. If a class implements two interfaces that provide default methods with the same signature and there is no suitable automatic resolution rule, the class must resolve the conflict.

Create the file **`InterfaceDefaultDemo.java`**:

~~~java
interface NamedItem {
    default String label() {
        return "named";
    }
}

interface TimestampedItem {
    default String label() {
        return "timestamped";
    }
}

class ReportItem implements NamedItem, TimestampedItem {
    @Override
    public String label() {
        return NamedItem.super.label()
                + "+" + TimestampedItem.super.label();
    }
}

public class InterfaceDefaultDemo {
    public static void main(String[] args) {
        ReportItem report = new ReportItem();
        NamedItem asNamed = report;
        TimestampedItem asTimestamped = report;

        System.out.println("direct=" + report.label());
        System.out.println("named=" + asNamed.label());
        System.out.println("stamped="
                + asTimestamped.label());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 InterfaceDefaultDemo.java
java InterfaceDefaultDemo
~~~

**Stdout:**

~~~text
direct=named+timestamped
named=named+timestamped
stamped=named+timestamped
~~~

`ReportItem` must provide `label()` to clarify how to combine them, because the two interfaces have default implementations with the same signature. `NamedItem.super.label()` and `TimestampedItem.super.label()` are the syntax for directly calling the respective interface's default implementation in a valid context.

After the class overrides `label()`, **regardless of which interface type the variable has**, virtual dispatch still selects `ReportItem.label()`.

Another related rule: when a **superclass** already provides a matching instance method, the class method generally takes precedence under inheritance rules over an interface default method. However, do not oversimplify all complex interface inheritance cases into “the last interface in the list wins”; **the order in which interfaces are listed is not a conflict resolution mechanism**.

## 19. Abstract Methods and Implementations in Subclasses

An abstract superclass can define a contract:

~~~java
abstract class Shape {
    abstract double area();
}
~~~

A concrete subclass must implement any missing abstract methods (otherwise, the subclass itself must be abstract):

~~~java
final class Square extends Shape {
    private final double side;

    Square(double side) {
        if (side < 0) {
            throw new IllegalArgumentException("side âm");
        }
        this.side = side;
    }

    @Override
    double area() {
        return side * side;
    }
}
~~~

These are valid illustrative class definitions. `Square.area()` is the implementation of the `Shape.area()` contract and should use `@Override`.

An abstract method has no implementation to call via `super.area()` in that superclass. If a subclass wants to reuse shared logic, the superclass can provide an additional **concrete method** with an appropriate name/contract. Avoid mechanically “writing `super`” just because you are overriding.

## 20. `final` Methods and Template Method

A `final` method cannot be overridden in a subclass. This can be an intentional design choice: the superclass preserves the **sequence of operations** inside a `final` method, while specialized steps are placed in other overridable methods.

Create the file **`FinalTemplateDemo.java`**:

~~~java
abstract class Job {
    final void execute() {
        System.out.println("start");
        doWork();
        System.out.println("finish");
    }

    abstract void doWork();
}

class ExportJob extends Job {
    @Override
    void doWork() {
        System.out.println("export");
    }
}

public class FinalTemplateDemo {
    public static void main(String[] args) {
        Job job = new ExportJob();
        job.execute();
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 FinalTemplateDemo.java
java FinalTemplateDemo
~~~

**Stdout:**

~~~text
start
export
finish
~~~

The superclass controls the `execute()` template and prevents subclasses from altering the overall structure through overriding. However, the `doWork()` method is abstract and is implemented by `ExportJob`. When `execute()` calls `doWork()`, the JVM dispatches to the subclass.

**Trade-off:** `final` helps protect an algorithm, but it also limits extensibility. Only mark a method as final when you genuinely want to preserve a behavioral invariant, not because “every method should be final”.

## 21. Overriding Methods from `Object`

The most common overrides in domain code:

- `toString()` helps return a human-readable description.
- `equals(Object)` defines equality according to the type's contract.
- `hashCode()` must be consistent with `equals`.
- Some other Object methods can also be overridden depending on their rules, but `getClass()` is final and cannot be overridden.

**Exact signatures are especially important:**

~~~java
@Override
public boolean equals(Object other) {
    // meaningful implementation.
    return super.equals(other);
}
~~~

This is **an illustrative method**, not an example of value equality. If you replace `Object` with a domain type such as `Person`:

~~~java
public boolean equals(Person other) {
    return false;
}
~~~

then it becomes an **overload**, not an override of `Object.equals(Object)`. If you attach `@Override` to this overload without a matching method in a supertype, the compiler will catch it.

Do not automatically override `equals` for every mutable entity: choose an appropriate identity/value equality contract and always preserve the `equals/hashCode` rules.

## 22. Complete Program 5 — `equals`, `hashCode`, `toString` with `@Override`

Create the file **`EqualityOverrideDemo.java`**:

~~~java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

final class AccountKey {
    private final String id;

    AccountKey(String id) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id rỗng");
        }
        this.id = id;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof AccountKey key)) {
            return false;
        }
        return id.equals(key.id);
    }

    @Override
    public int hashCode() {
        return Objects.hash(id);
    }

    @Override
    public String toString() {
        return "AccountKey(" + id + ")";
    }
}

public class EqualityOverrideDemo {
    public static void main(String[] args) {
        AccountKey a = new AccountKey("K-01");
        AccountKey b = new AccountKey("K-01");
        AccountKey c = new AccountKey("K-02");

        System.out.println("a equals b=" + a.equals(b));
        System.out.println("a same b=" + (a == b));
        System.out.println("a equals c=" + a.equals(c));
        System.out.println("hash same="
                + (a.hashCode() == b.hashCode()));

        Set<AccountKey> keys = new HashSet<>();
        keys.add(a);
        keys.add(b);
        keys.add(c);
        System.out.println("set size=" + keys.size());
        System.out.println("text=" + a);
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 EqualityOverrideDemo.java
java EqualityOverrideDemo
~~~

**Stdout:**

~~~text
a equals b=true
a same b=false
a equals c=false
hash same=true
set size=2
text=AccountKey(K-01)
~~~

**Explanation:**

- `a` and `b` are two distinct objects (`a == b` is false) yet have the same `id`, so `equals` returns true.
- `hashCode` is based on the same `id`, ensuring equal objects have the same hash code.
- `HashSet` uses equality/hashing to avoid adding duplicate values, so there are only two keys.
- `System.out.println(a)` uses the overridden `toString()`.

This is a **value object** with an immutable `id`. If you override `hashCode()` based on a mutable field and then mutate the field while the object is inside a `HashSet`, the collection may fail to find/remove it properly. Using `@Override` does not by itself guarantee that the `equals` implementation is correct; the annotation only verifies the signature and inheritance relationship.

## 23. Generics, Type Erasure, and Bridge Methods

Generics make some overrides look different in runtime signature after **type erasure**, but the Java compiler can generate **bridge methods** in bytecode to preserve polymorphism and binary compatibility.

Example with a generic interface:

~~~java
interface Source<T> {
    T read();
}

final class StringSource implements Source<String> {
    @Override
    public String read() {
        return "java";
    }
}
~~~

At the source level, `StringSource.read()` conforms to `Source<String>.read()`. However, the JVM has method descriptor rules after erasure that the compiler needs to handle for compatibility.

Create the file **`GenericOverrideDemo.java`**:

~~~java
interface ValueSource<T> {
    T read();
}

class TextSource implements ValueSource<String> {
    @Override
    public String read() {
        return "java";
    }
}

public class GenericOverrideDemo {
    public static void main(String[] args) {
        ValueSource<String> source = new TextSource();
        System.out.println("value=" + source.read());

        TextSource concrete = new TextSource();
        System.out.println("direct=" + concrete.read());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 GenericOverrideDemo.java
java GenericOverrideDemo
~~~

**Stdout:**

~~~text
value=java
direct=java
~~~

If you want to observe the compiler generating the bridge method (diagnostic output depends on the tool/version and is not written as program stdout), after compiling you can run:

~~~bash
javap -c -p -v TextSource
~~~

Look for flags related to `ACC_BRIDGE` and `ACC_SYNTHETIC`. **Do not write a bridge method manually as a second override**, and do not mistake a generics name clash for a valid overload. The compiler also enforces **subsignature** and **erasure** rules to ensure generic methods follow contracts properly.

## 24. Overriding Can Call a Subclass Method in a Superclass Constructor: What Is the Risk?

In Java, a superclass constructor can call an instance method overridden by a subclass. The call still undergoes **virtual dispatch** to the implementation on the actual object, even when the **subclass's instance field initializers have not yet run**.

Create the file **`ConstructorOverrideRiskDemo.java`**:

~~~java
class ParentConstructor {
    ParentConstructor() {
        System.out.println("parent constructor");
        describe();
    }

    void describe() {
        System.out.println("parent describe");
    }
}

class ChildConstructor extends ParentConstructor {
    private String message = "ready";

    ChildConstructor() {
        System.out.println("child constructor: " + message);
    }

    @Override
    void describe() {
        System.out.println("child describe: " + message);
    }
}

public class ConstructorOverrideRiskDemo {
    public static void main(String[] args) {
        new ChildConstructor();
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 ConstructorOverrideRiskDemo.java
java ConstructorOverrideRiskDemo
~~~

**Stdout:**

~~~text
parent constructor
child describe: null
child constructor: ready
~~~

Analysis:

1. The `ChildConstructor` object is allocated with instance fields having default values, where `message=null`.
2. The superclass constructor runs before the subclass instance initializer.
3. `ParentConstructor()` calls `describe()` — which is an overridable method.
4. The JVM selects `ChildConstructor.describe()`, even though the subclass field is still `null`.
5. Only after the superclass constructor finishes does the initializer `message="ready"` run, and then the subclass constructor body prints the value `ready`.

**Recommendation:** do not call overridable methods from a constructor, especially when the subclass implementation depends on state initialized afterward. Avoid publishing `this` before object construction completes. `@Override` helps reveal the overriding relationship, but **does not fix** this lifecycle hazard.

## 25. Does Dynamic Dispatch Apply to Every Call?

No. Summary of common situations:

| Usage | Primary decision | Example |
| --- | --- | --- |
| Overridable instance method | Dispatched by the actual object after signature selection | `animal.sound()` |
| Overloaded method | Selects overload based on compile-time types | `print(Object)` vs `print(String)` |
| Static method | Static binding/hiding by declared type | `BaseView.label()` |
| Field access | Resolves field by compile-time type | `baseReference.code` |
| Constructor | Executes initialization chain according to `new`/`this`/`super` rules | `new Child()` |
| Private instance method of superclass | Not overridable from a subclass | `private void helper()` |
| Final method | Subclasses are not allowed to override | `final void execute()` |
| `super.method()` | Specifies the super implementation at the call site | `super.log(message)` |
| Interface default method | Subject to interface/class precedence and overriding rules | `NamedItem.super.label()` |

Do not solve polymorphism problems simply by counting `extends` keywords. Identify the **reference type**, the **selected signature**, and **whether the method can be overridden**, and only then consider the **runtime object type** and whether `super` is used.

## 26. Common Compilation Errors Related to `@Override`

| Symptom | Cause | Fix |
| --- | --- | --- |
| Method does not override/implement a method from a supertype | Wrong name or signature; actually an overload | Check the exact name/parameters |
| Attempting to assign weaker access privileges | Lowering `public`/`protected` | Keep or widen visibility |
| Return type is not compatible | Return type is not return-type-substitutable | Use the exact type/covariant reference |
| Overridden method does not throw Exception | Subclass method adds a checked exception violating the contract | Remove or narrow checked exceptions |
| Cannot override final method | Superclass method is `final` | Design a different extension point |
| Static method cannot override instance method | Mixing static and instance with the same inherited signature | Do not mix; choose the appropriate model |
| Static method annotated with `@Override` | Static hiding is not overriding | Remove the annotation; use the class name |
| Overloading `equals(Person)` while expecting it to override `equals(Object)` | Different parameter | Use `equals(Object)` |
| Interface implementation missing `public` | Interface method has public access | Declare the method as public |
| Two interface default methods with the same signature | Ambiguity that must be resolved | Override in the class, selecting/combining logic |
| Generic methods having a name clash after erasure | Two erased signatures conflict | Adjust the generic design/rename |
| Calling an overridden method in a parent constructor reads a null child field | Dynamic dispatch before child fields are initialized | Avoid calling overridable methods in constructors |

When the compiler reports an error, **do not immediately delete `@Override`** just to get past compilation. If the intent is to override, you must fix the signature/access/return/throws. Only remove the annotation when the author **genuinely wants a new overload** or valid static method hiding.

## 27. Designing a Good Hierarchy with Overriding

Some principles with practical value:

**Clear supertype contracts.** Superclass/interface methods need to state their meaning, preconditions, and postconditions. Subclasses may change the implementation, but should not break the reasonable expectations of callers using the supertype.

**Do not let the implementation depend on an uncontrolled subclass.** A superclass constructor calling an overridable method easily runs into the situation where fields are not ready yet. If initialization needs a shared step, use a `private` helper or logic that does not dispatch to the subclass while construction is incomplete.

**Prefer composition when there is no true “is-a” relationship.** Inheriting just to reuse a few lines of code can create a hard-to-manage hierarchy; composition/delegation can be clearer.

**Use `final` intentionally.** Extensible steps should be clearly defined. Invariant rules or algorithm structures that need protection can use a final method, such as `Job.execute()`.

**Do not confuse overriding with changing state directly.** Field hiding/overloading does not by itself guarantee polymorphism. Behavioral APIs should express meaningful operations, without trying to override getters/setters for every field.

**Test through the supertype.** If an API promises polymorphism, write tests using `Base b = new Child();` rather than only `Child c = new Child();`. This helps catch methods that were unintentionally written as overloads.

**Attach `@Override` consistently.** This is a small yet helpful signal for readers to distinguish inherited methods from new APIs of the class.

## 28. Process for Predicting What a Program Prints

When a problem presents a hierarchy and asks for stdout, follow this order:

1. Identify each **actual object** created with `new`.
2. Note the **compile-time type of the variable** where each method is called.
3. Determine the method name and **selected overload** from the compile-time parameter list/types.
4. Check whether that method is an **overridable instance method**, `final`, `private`, `static`, or a constructor.
5. If it is an overridable instance method, select the **runtime object's implementation**.
6. If the call uses `super`, consider the exact superclass method specified at the call site.
7. For `super.method()` that contains other instance calls inside it, continue applying dispatch where needed.
8. If there are fields with the same name, resolve them by **compile-time field type**, not virtual dispatch.
9. If a constructor is running, check the **order of instance initializers**, because an overridden method may observe fields still holding default values.
10. Finally, write out the output lines in the execution order of the statements.

For `OverloadOverrideDemo`, step 3 is especially important: `asBase.print("hello")` has the `print(Object)` signature selected first, and only then dispatches to `FancyPrinter.print(Object)`; it does **not** automatically switch to the `print(String)` overload just because the runtime object is a FancyPrinter.

## 29. Practice Exercises

**Exercise 1.** A superclass has `void show(int x)`. The subclass declares `void show(long x)` with `@Override`. How does the compiler react and why?

**Exercise 2.** `Animal a = new Dog(); a.sound();`. If Dog overrides `sound`, which body runs? Which part does the Animal-typed reference affect?

**Exercise 3.** If a superclass declares `public void run()`, can the subclass override it with `protected void run()`?

**Exercise 4.** A superclass method returns `Number`, and a subclass returns `Integer`. When is this valid? Is returning `long` instead of `int` automatically valid in the same way?

**Exercise 5.** Superclass `read() throws IOException`, subclass `read() throws Exception`. Why is this invalid? What if the subclass declares no throws?

**Exercise 6.** Both parent and child classes have `static String label()`. Does `Base ref = new Child(); ref.label()` perform dynamic dispatch like an instance method?

**Exercise 7.** Both parent and child classes have a field `value`. Which field does `Base ref = new Child(); ref.value` read? What about `ref.getValue()` if Child overrides the method?

**Exercise 8.** Does `public boolean equals(Person p)` override `Object.equals(Object)`? Does `@Override` help catch this mistake?

**Exercise 9.** A class implements two interfaces that have a default `label()` with the same signature. Can the conflict be avoided simply by changing the order in `implements`?

**Exercise 10.** Inside `super.log(x)`, if the superclass code calls `format(x)` and the subclass has overridden `format`, which version can run?

**Exercise 11.** Why can an overriding method without `@Override` still be dispatched by the JVM? Then what actual effect does the annotation have?

**Exercise 12.** A superclass constructor calls an overridable method, and the subclass override reads `String name="ready"`. Why can the output be `null`?

**Exercise 13.** A generic interface `Source<T>` has `T read()`, and class `TextSource implements Source<String>` has `String read()`. What kind of additional method can the compiler generate to preserve the contract in bytecode?

**Exercise 14.** A `final` method acts as a “template” calling an abstract method. Can a subclass override the template? Can it implement the abstract step?

**Exercise 15.** If the compiler reports `method does not override or implement`, why should you not immediately delete the annotation?

### Reference Answers

1. Compile-time error: `show(long)` is a new overload and does not override `show(int)`; change the parameter to `int` if you want to override.
2. The Dog implementation runs according to the runtime object; the Animal reference type is used to check the API/signature at compile time.
3. No; reducing visibility from public to protected is prohibited.
4. Valid because Integer is a subtype of Number; primitive returns do not have arbitrary widening covariance.
5. `Exception` is a broader checked exception, placing a heavier contract on callers; a subclass may omit the checked exception.
6. No; static method hiding follows compile-time rules, so `Base.label()` is selected via the Base type.
7. The field is resolved according to the Base type; the overridable instance method dispatches according to the Child object.
8. No, that is an overload. Attaching `@Override` will cause the compiler to report an error if there is no matching supertype method with the same signature.
9. No; the class must resolve it according to interface/default method rules, usually by overriding `label()`.
10. `super.log` selects the superclass body, but the instance call `format` inside that body can still dispatch to the subclass.
11. Overriding is a language rule; `@Override` is a compile-time check and a signal to readers.
12. The child field still holds its default value when the parent constructor calls the override before the child's initializer runs.
13. A synthetic bridge method, required by type erasure and dispatch compatibility.
14. The final template cannot be overridden; the subclass implements the abstract step, and the template calls the step via polymorphism.
15. Because there may be a typo, wrong parameter type, wrong access level, or a changed supertype. If the intent is to override, you must fix the contract mismatch rather than hiding the error.

## 30. Checklist When Writing an `@Override` Method

- Which **superclass or interface** does this method come from?
- Is it genuinely an **overridable instance method**, not static/private/final/constructor?
- Are the **name and parameters** exact? Is there an accidental overload due to primitive/wrapper, array/varargs, or extra/missing parameters?
- Does the return type satisfy **return-type-substitutability**?
- Are you accidentally **narrowing visibility**?
- Are checked exceptions broader than the supertype contract?
- If implementing an interface, is the method `public` when required?
- If overriding `equals`, is it properly `equals(Object)` and is `hashCode` consistent?
- If the subclass uses `super.method()`, do you understand the virtual calls inside the superclass method?
- If a superclass constructor has an overridable call, could it observe uninitialized subclass fields?
- If the method involves generics, is there a name clash after erasure?
- Have you tested through a **superclass/interface-typed variable** to verify polymorphism?
- If `@Override` reports an error, have you checked the cause instead of hastily removing the annotation?

## 31. Java 17 Official Documentation

- [JLS 17 §8.4.8.1 — Overriding (by Instance Methods)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8.1): rules for overriding instance methods.
- [JLS 17 §8.4.8.2 — Hiding (by Class Methods)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8.2): the difference between static method hiding and overriding.
- [JLS 17 §8.4.8.3 — Requirements in Overriding and Hiding](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8.3): visibility, return type, and throws.
- [JLS 17 §8.4.2 — Method Signature](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.2): signatures and subsignatures.
- [JLS 17 §8.4.5 — Method Result](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.5): return-type-substitutability.
- [JLS 17 §8.4.9 — Overloading](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.9): overloading and how methods are distinguished.
- [JLS 17 §9.4.1 — Inheritance and Overriding in Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.4.1): overriding interface methods.
- [JLS 17 §9.6.4.4 — @Override](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.4): meaning of the annotation.
- [JLS 17 §15.12 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12): method selection and runtime dispatch.
- [JLS 17 §12.5 — Creation of New Class Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.5): object initialization order and the danger of virtual calls in constructors.
- [Java SE 17 API — Override](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Override.html): annotation for checking overriding.
- [Java SE 17 API — Object](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html): `equals`, `hashCode`, `toString`, and `final` methods.

**Key takeaway:** overriding is how a subclass or implementation **changes the behavior of an instance method according to a supertype contract**. The compiler selects a valid signature based on the reference type, while runtime dispatch selects the appropriate body for the actual object. `@Override` does not trigger this mechanism, but it helps **catch wrong names/signatures and express intent**. Do not confuse overriding with overloading, static hiding, or field hiding; always consider visibility, return type, checked exceptions, default methods, `super`, and object initialization state when designing polymorphism.
