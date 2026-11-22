# `final` on methods and classes in Java

In Java, the **`final`** keyword has different meanings depending on where it is declared. For **methods**, it prevents subclasses from **overriding** the method according to inheritance rules. For **classes**, it prevents creating subclasses using `extends`. These are two mechanisms that help API authors define **allowed extension points** and **behavioral contracts that cannot be replaced by a subclass implementation**.

Two short examples:

```java
class Account {
    public final String type() {
        return "ACCOUNT";
    }
}

class SavingsAccount extends Account {
    // public String type() { return "SAVINGS"; }
    // INVALID if uncommented: cannot override a final method.
}
```

```java
final class SecurityToken {
    private final String value;

    SecurityToken(String value) {
        this.value = value;
    }
}

// class CustomToken extends SecurityToken { }
// INVALID if uncommented: cannot inherit from a final class.
```

**Remember right away:**

- `final` on an **instance method**: a subclass cannot provide an **override** for that method.
- `final` on a **static method**: a subclass cannot **hide** a static method with a matching signature according to language rules; static methods are not dynamically overridden in the first place.
- `final` on a **class**: that class cannot have subclasses under Java's standard inheritance mechanism.
- `final` does **not** prohibit calling the method, does not prohibit creating instances of a normal class with a valid constructor, and does not prohibit **overloading** the method name with a different parameter list.
- `final` on a method/class **does not mean an immutable object**, **does not change access modifiers**, and **does not automatically make code thread-safe**.

This lesson uses **Java 17+**. Snippets containing commented-out lines with error labels are **intentionally invalid examples if uncommented**; complete programs with their own file names and `javac`/`java` commands are presented so that they can be compiled and run independently.

## 1. First: override, overload, hiding, and extends

To understand `final` properly, you need to distinguish four terms:

| Term | Brief meaning | Example |
| --- | --- | --- |
| **Overriding** | A subclass provides an implementation of an inherited instance method with a matching compatible signature | `Child.work()` overrides `Parent.work()` |
| **Overloading** | Multiple methods with the same name but **different parameter lists** according to signature rules | `print(int)` and `print(String)` |
| **Static method hiding** | A subclass declares a corresponding static method, hiding the static method from the superclass, when permitted | `Child.label()` and `Parent.label()` |
| **Class inheritance** | A subclass extends a parent class using `extends` | `class Child extends Parent` |

When a method is **final**, what is locked is **the ability to override or hide it respectively**, not every occurrence of that method name. When a class is **final**, what is locked is **class inheritance from this class**, not the class being used as a type, holding state, or implementing interfaces.

### A contrasting example without final

```java
class Parent {
    String describe() {
        return "Parent";
    }
}

class Child extends Parent {
    @Override
    String describe() {
        return "Child";
    }
}
```

With:

```java
Parent value = new Child();
System.out.println(value.describe()); // Child
```

The call can select the overriding implementation at runtime based on the `Child` object.

If `Parent.describe()` is declared `final`, `Child` **cannot declare this override**. Meanwhile, `Parent.describe()` can still be called on a `Child` object as an inherited method.

## 2. `final` on an instance method: prevents overriding, not inheritance

Suppose a superclass has:

```java
class Base {
    public final String identity() {
        return "Base";
    }
}
```

A valid subclass:

```java
class Derived extends Base {
    void extra() {
        System.out.println(identity());
    }
}
```

`Derived` **still inherits and can call** `identity()`. It just cannot replace the implementation:

```java
class InvalidDerived extends Base {
    // @Override
    // public String identity() {
    //     return "Derived";
    // }
    // INVALID if uncommented: overridden method is final.
}
```

**You should not say "a final method is not inherited."** More accurately, **it cannot be overridden**. An eligible final method can be inherited, called through a parent-class or subclass variable, and used in subclasses that do not redeclare it.

### Why prohibit overriding?

When a class provides a final method, the class author wants to preserve that method's implementation across valid subclasses. This is useful when:

- The method maintains an important step in the object's **invariant**.
- A general algorithm needs to preserve its **execution order** or checks.
- The API needs uniform behavior across all subtypes.
- The design only lets subclasses extend via **selected hook methods**, without allowing them to replace the entry point.

However, **final does not replace input validation, authorization, or mutation control**. It is only a language-level constraint on the inheritance relationship.

## 3. Complete Java 17 example: inheriting without overriding a final method

Save the entire code as **`FinalMethodDemo.java`**:

```java
class Document {
    private final String title;

    Document(String title) {
        this.title = title;
    }

    public final String category() {
        return "DOCUMENT";
    }

    public String description() {
        return title;
    }
}

class Report extends Document {
    Report(String title) {
        super(title);
    }

    @Override
    public String description() {
        return "Report: " + super.description();
    }

    // @Override
    // public String category() { return "REPORT"; }
    // INVALID if uncommented: category() is final.
}

public class FinalMethodDemo {
    public static void main(String[] args) {
        Document first = new Document("Guide");
        Document second = new Report("Sales");

        System.out.println(first.category());
        System.out.println(second.category());
        System.out.println(first.description());
        System.out.println(second.description());
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 FinalMethodDemo.java
java FinalMethodDemo
```

**Exact stdout:**

```text
DOCUMENT
DOCUMENT
Guide
Report: Sales
```

Analysis:
1. `Report` is allowed to `extends Document` because the `Document` class is **not final**.
2. `Document`'s `category()` is final. Both `Document` and `Report` objects use that implementation and print `DOCUMENT`.
3. `description()` is not final, so `Report` can override it and change its behavior.
4. The variable `second` has declared type `Document`, while its runtime object is `Report`; the `description()` call dispatches to the `Report` implementation.
5. `super.description()` inside the instance method `Report.description()` validly calls the parent implementation.

**Conclusion:** `final` locks **a specific method**, not the entire class or all other methods.

## 4. `final` does not prevent **overloading**

Overloading is declaring the same method name with a **different parameter list**:

```java
class Formatter {
    public final String format(int value) {
        return "integer=" + value;
    }
}

class ExtendedFormatter extends Formatter {
    public String format(String value) {
        return "text=" + value;
    }
}
```

This is valid code because `format(String)` **does not override** `format(int)`. The two signatures are different.

### Runnable example

Save **`FinalOverloadDemo.java`**:

```java
class Formatter {
    public final String format(int value) {
        return "int: " + value;
    }
}

class TextFormatter extends Formatter {
    public String format(String value) {
        return "text: " + value;
    }
}

public class FinalOverloadDemo {
    public static void main(String[] args) {
        TextFormatter formatter = new TextFormatter();

        System.out.println(formatter.format(7));
        System.out.println(formatter.format("Java"));

        Formatter baseView = formatter;
        System.out.println(baseView.format(9));

        // baseView.format("Java");
        // INVALID if uncommented: Formatter does not declare a String overload.
    }
}
```

Commands:

```bash
javac -encoding UTF-8 FinalOverloadDemo.java
java FinalOverloadDemo
```

Stdout:

```text
int: 7
text: Java
int: 9
```

**Points to distinguish:**

- `TextFormatter.format(String)` is valid because it is only an **overload**.
- `Formatter.format(int)` remains **final** and cannot be overridden.
- Overload selection by the compiler depends on static types and resolution rules; because `baseView` has type `Formatter`, the compiler does not automatically use an overload that only exists in `TextFormatter`.
- The `final` modifier does not turn a method call into a method lookup based solely on the runtime type.

### Can you overload directly within the same class?

Yes:

```java
class Reader {
    final void read(int id) {
    }

    void read(String key) {
    }
}
```

`read(int)` is final and `read(String)` is not final. These are two methods with different signatures, each having its own modifier contract.

## 5. `final` and `@Override`

The `@Override` annotation requires the compiler to check that the declared method actually **overrides or implements a valid corresponding method** according to the rules.

Example:

```java
class Base {
    public final void send() {
    }
}

class Child extends Base {
    // @Override
    // public void send() { }
    // INVALID if uncommented: cannot override a final method.
}
```

Removing `@Override` from `Child`'s method **does not fix** the error:

```java
// public void send() { } // Still invalid in Child.
```

**The error lies in the prohibited override behavior**, not because the compiler "dislikes" the annotation.

Conversely, when you need to override a permitted method, `@Override` is a good practice for detecting mistyped signatures or superclass API changes.

## 6. Dynamic dispatch and `final`

For **non-final instance methods**, implementation selection can depend on the runtime object (dynamic dispatch).

```java
class Animal {
    String sound() {
        return "?";
    }
}

class Cat extends Animal {
    @Override
    String sound() {
        return "meow";
    }
}
```

`Animal a = new Cat(); a.sound();` calls `Cat.sound()`.

When `Animal.sound()` is marked final, **subclasses cannot define a valid overriding implementation**:

```java
class Animal {
    final String sound() {
        return "?";
    }
}

class Cat extends Animal {
    // Cannot override sound().
}
```

The compiler/JVM knows that the implementation cannot be replaced by a subclass override. However, you should not infer that every call to a final method is always JIT-inlined or always faster than a non-final method: optimizations depend on the JVM, profiling, and many other conditions.

### Final is an API contract, not a speed guarantee

Use `final` because you genuinely want to **lock an extension point**. Do not add it mechanically solely with the goal of "speeding things up" without measuring performance on a real workload.

In modern JVMs, many non-final calls can also be optimized through type analysis and speculative optimization.

## 7. Template method design: locking the workflow, allowing controlled extension

A reasonable pattern is to make the **orchestrating method** final, while **customizable steps** are protected/abstract or non-final hooks.

Example:

```java
abstract class Processor {
    public final String process(String input) {
        String normalized = input.trim();
        return transform(normalized);
    }

    protected abstract String transform(String normalized);
}
```

Subclasses **cannot** replace the `process` method (so they cannot bypass the `trim` step by overriding), yet can implement `transform`.

### Complete Java 17 program

Save **`FinalTemplateDemo.java`**:

```java
import java.util.Locale;

abstract class Processor {
    public final String process(String input) {
        if (input == null) {
            throw new IllegalArgumentException("input required");
        }

        String normalized = input.trim();
        return transform(normalized);
    }

    protected abstract String transform(String text);
}

class UpperProcessor extends Processor {
    @Override
    protected String transform(String text) {
        return text.toUpperCase(Locale.ROOT);
    }
}

class DashProcessor extends Processor {
    @Override
    protected String transform(String text) {
        return text.replace(" ", "-");
    }
}

public class FinalTemplateDemo {
    public static void main(String[] args) {
        Processor upper = new UpperProcessor();
        Processor dash = new DashProcessor();

        System.out.println(upper.process("  hello java  "));
        System.out.println(dash.process("  hello java  "));
    }
}
```

```bash
javac -encoding UTF-8 FinalTemplateDemo.java
java FinalTemplateDemo
```

**Stdout:**

```text
HELLO JAVA
hello-java
```

Analysis:
- `Processor.process` is final and always checks for null, trims the input string, and then calls `transform`.
- `UpperProcessor` and `DashProcessor` do not override `process`; they only override `transform`.
- The `final` keyword protects the **algorithm structure** from direct replacement by a subclass.
- The `transform` method still runs the corresponding subclass's implementation due to dynamic dispatch.

**Design note:** even though `process` is final, the `transform` hook can throw an exception or cause side effects. You should not claim that final by itself guarantees every invariant if a subclass hook has the potential to break them.

### When is a template method not suitable?

If subclasses do not need inheritance and you only want to plug in a handler function, **composition** or a functional interface may be simpler. `final` is a tool for controlling inheritance; it does not require every extensibility design to use subclasses.

## 8. `final` on a class: prohibiting `extends`

Declaration:

```java
public final class Token {
    private final String value;

    public Token(String value) {
        this.value = value;
    }

    public String value() {
        return value;
    }
}
```

With `Token`:
- Callers can **create instances** using the public constructor if the class can be validly accessed.
- Callers can call the public instance method `value()`.
- No class may declare `extends Token` using standard inheritance syntax.
- `Token` can still implement interfaces when declared, use helper methods, fields, constructors, static factories, etc.

**Invalid** example:

```java
// class AdvancedToken extends Token { }
// INVALID: cannot inherit from final Token.
```

Do not interpret "a final class cannot be inherited from" as "a final class has no instances", "has no constructors", or "cannot be used as a variable's type". These are completely different things.

## 9. Runnable example: creating and using a final class

Save **`FinalClassDemo.java`**:

```java
final class Ticket {
    private final int id;

    Ticket(int id) {
        this.id = id;
    }

    int id() {
        return id;
    }

    String label() {
        return "Ticket-" + id;
    }
}

public class FinalClassDemo {
    public static void main(String[] args) {
        Ticket first = new Ticket(10);
        Ticket second = new Ticket(20);

        System.out.println(first.label());
        System.out.println(second.id());

        // class SpecialTicket extends Ticket { }
        // INVALID if turned into a class declaration: Ticket is final.
    }
}
```

Commands:

```bash
javac -encoding UTF-8 FinalClassDemo.java
java FinalClassDemo
```

Stdout:

```text
Ticket-10
20
```

Point to observe: the final `Ticket` **is still instantiated twice**. The two instances have their own state and their own methods according to class semantics. The final modifier only locks the **inheritance path**.

### A final class can still have a private constructor

```java
final class Utility {
    private Utility() {
    }

    static int twice(int value) {
        return value * 2;
    }
}
```

`final` here prevents subclasses, while the private constructor restricts instantiation from external independent classes. The two modifiers serve **two different goals**.

## 10. A final class can still `implements` an interface

`final` on a class prohibits **subclasses**, not **this class committing to provide behavior through an interface**.

Example:

```java
interface Describable {
    String describe();
}

final class Book implements Describable {
    private final String title;

    Book(String title) {
        this.title = title;
    }

    @Override
    public String describe() {
        return "Book: " + title;
    }
}
```

`Book` is final, yet it still implements `Describable`. Callers can use interface-typed variables:

```java
Describable item = new Book("Java");
System.out.println(item.describe()); // Book: Java
```

### Complete program

Save **`FinalImplementsDemo.java`**:

```java
interface Named {
    String name();
}

final class Course implements Named {
    private final String name;

    Course(String name) {
        this.name = name;
    }

    @Override
    public String name() {
        return name;
    }
}

public class FinalImplementsDemo {
    public static void main(String[] args) {
        Named first = new Course("Java Core");
        Named second = new Course("OOP");

        System.out.println(first.name());
        System.out.println(second.name());
        System.out.println(first instanceof Course);
    }
}
```

```bash
javac -encoding UTF-8 FinalImplementsDemo.java
java FinalImplementsDemo
```

Stdout:

```text
Java Core
OOP
true
```

**Important:** `final class Course implements Named` does **not** make the `Named` interface final. Another class can still implement `Named` according to interface rules. What is prohibited is only `class AdvancedCourse extends Course`.

### Polymorphism through interfaces still exists

A variable of type `Named` can reference a `Course` object or an object of another class that implements `Named`. Runtime dispatch to the object's implementation still works. Therefore, `final` on a class does not eliminate all forms of polymorphism.

## 11. Can a final class inherit from another class?

**Yes.** A final class can **extend a non-final, accessible superclass**, yet that final class itself **cannot have any further subclasses**.

```java
class BaseService {
    String category() {
        return "BASE";
    }
}

final class BillingService extends BaseService {
    @Override
    String category() {
        return "BILLING";
    }
}
```

Model:

```text
BaseService (not final)
       |
       | extends
       v
BillingService (final)
       X
       |
 Cannot extend from BillingService
```

There is no rule saying "a class marked final cannot use extends". The restriction is that **no one may extend the final class afterward**.

### Inherited methods can be overridden when the subclass itself is declared final

`BillingService` can still override `BaseService`'s `category()` method because `BaseService.category` is not final and the override is valid. The final keyword on `BillingService` does not prohibit **that class from overriding inherited methods**; it prohibits **future subclasses from inheriting from BillingService**.

## 12. `final class` does not automatically turn all methods into `final` syntactically

Example:

```java
final class Counter {
    private int value;

    void increment() {
        value++;
    }

    int value() {
        return value;
    }
}
```

There is no valid subclass to override `increment()` or `value()` because the `Counter` class is final.

However, method declarations are not required to also write `final`. More accurately, **they cannot be overridden through a subclass of Counter**, not that Java automatically replaces every declaration modifier with the word `final` in the source.

Adding `final` to each method of a final class is usually **redundant for the goal of blocking subclass overrides**; it can be used to express a specific contract, but overusing it and causing clutter should be avoided.

## 13. A final class does not mean an immutable object

This is a major pitfall in OOP design.

```java
final class Counter {
    private int value;

    void increment() {
        value++;
    }

    int value() {
        return value;
    }
}
```

The `Counter` class is final, yet a `Counter` object is **mutable** because the instance field `value` changes.

### Java 17 example proving this

Save **`FinalNotImmutableDemo.java`**:

```java
final class Counter {
    private int value;

    Counter(int initial) {
        value = initial;
    }

    void increment() {
        value++;
    }

    int value() {
        return value;
    }
}

public class FinalNotImmutableDemo {
    public static void main(String[] args) {
        final Counter counter = new Counter(5);

        counter.increment();
        counter.increment();

        System.out.println(counter.value());

        // counter = new Counter(0); // INVALID: the counter variable is final.
        // class ChildCounter extends Counter { } // INVALID: the Counter class is final.
    }
}
```

Commands:

```bash
javac -encoding UTF-8 FinalNotImmutableDemo.java
java FinalNotImmutableDemo
```

Stdout:

```text
7
```

Here there are **two forms of final at the same time**:
1. `final Counter counter`: the local variable `counter` cannot be assigned a new reference.
2. `final class Counter`: `Counter` cannot be inherited from.

However, `Counter.value` is **not final**, and the `increment()` method mutates state, so the object is mutable.

### An immutable object requires additional conditions

An immutable design typically needs to combine:
- Keeping state unmodifiable outside the contract (usually private fields).
- Valid field/value initialization.
- Providing no mutators that change observable state.
- Not exposing mutable internal arrays/collections/objects.
- Defensive copies or immutable components when needed.
- Being careful with inheritance so subclasses cannot break the contract; `final class` can support this goal, but is not sufficient on its own.

**`String` is a classic example of a final class with immutable semantics, but not every final class is like String.** The mutable classes `StringBuilder` and `StringBuffer` are also declared final in Java, so final does not automatically make data immutable.

## 14. A `final` method also does not by itself prevent changing object state

A method marked final can still **mutate instance fields**:

```java
class Wallet {
    private int balance;

    public final void deposit(int amount) {
        balance += amount;
    }

    int balance() {
        return balance;
    }
}
```

`deposit` being final **does not mean the method is "read-only"**. It still modifies the `balance` field. Only subclasses are prevented from replacing the `deposit` implementation with an override.

If the method needs to protect an invariant, it should validate:

```java
public final void deposit(int amount) {
    if (amount <= 0) {
        throw new IllegalArgumentException("positive amount required");
    }
    balance += amount;
}
```

But overflow, synchronization, and business contracts still must be considered. `final` **does not replace validation**.

## 15. `final` and `private`: two different constraints

A regular `private` method is not overridden by subclasses in the polymorphic sense, because private methods are **not inherited for overriding** like public/protected instance methods.

Example:

```java
class Base {
    private void helper() {
        System.out.println("Base helper");
    }

    void run() {
        helper();
    }
}

class Child extends Base {
    public void helper() {
        System.out.println("Child helper");
    }
}
```

`Child.helper()` is the subclass's own method; it **does not override** `Base.helper()`.

### Runnable program

Save **`PrivateNotOverrideDemo.java`**:

```java
class Base {
    private final void helper() {
        System.out.println("Base helper");
    }

    void run() {
        helper();
    }
}

class Child extends Base {
    public void helper() {
        System.out.println("Child helper");
    }
}

public class PrivateNotOverrideDemo {
    public static void main(String[] args) {
        Child child = new Child();

        child.run();
        child.helper();
    }
}
```

```bash
javac -encoding UTF-8 PrivateNotOverrideDemo.java
java PrivateNotOverrideDemo
```

Stdout:

```text
Base helper
Child helper
```

**Why is this valid even though `Base.helper()` has `final`?** It is a private method of `Base`; `Child.helper()` **is not an override** of that method because private members do not participate in the corresponding overriding relationship. `Base.run()` still calls the private method `Base.helper()`.

This is completely different from an inherited `public final` or `protected final` instance method: a subclass cannot redeclare the same signature as an override.

### Should you write `private final`?

`private final void helper()` can be valid, yet it is usually **unnecessary for the goal of preventing overriding**, since private methods cannot be overridden anyway. Adding `final` mainly serves as emphasis in the source code without providing the override-locking benefit seen in public/protected methods.

**Do not confuse a private method with a non-private final method.**

## 16. Access permissions of a final method are still checked

`final` is not an access modifier. A method can be:

```java
class Example {
    public final void publicAction() {
    }

    protected final void protectedAction() {
    }

    final void packageAction() {
    }

    private final void privateAction() {
    }
}
```

The access levels still keep their own meanings:

- `public` can be called from any place eligible to see the type and member.
- `protected` has rules for the same package and subclasses outside the package.
- No modifier written → **package-private**.
- `private` is restricted directly according to Java rules, including applicable same-nest contexts.

`final` only adds a constraint regarding **overriding/hiding when the corresponding relationship exists**; it does not by itself make a method public or private.

### Advanced note on package-private

A package-private method in package A **is not inherited/overridden by a subclass in package B in the way public/protected methods are handled**. When looking at `final` in this situation, you must combine **accessibility and inheritance rules**, rather than concluding that two methods with the same name/signature always constitute an override.

For APIs meant for subclasses outside the package, use `protected` or `public` if you genuinely need to grant subclasses access.

## 17. `final` on a static method: preventing static hiding, not dynamic overriding

Static methods inherently do **not** use dynamic dispatch like instance methods. When a superclass and a subclass declare static methods with the same signature in a valid context, that is generally **method hiding**, not overriding.

Example when not final:

```java
class Parent {
    static String label() {
        return "Parent";
    }
}

class Child extends Parent {
    static String label() {
        return "Child";
    }
}
```

`Parent.label()` and `Child.label()` return results according to the class name. Calling a static method through an object such as `Parent ref = new Child(); ref.label();`, although it may compile, gives a misleading impression of dynamic dispatch; it should be avoided.

### When a static method is final

```java
class Parent {
    public static final String label() {
        return "Parent";
    }
}

class Child extends Parent {
    // public static String label() { return "Child"; }
    // INVALID if uncommented: cannot hide a static final method.
}
```

In this case, the subclass cannot declare a static method with the same signature to hide `Parent.label`.

**Terminology distinction:**
- For instance methods: final prohibits **overriding**.
- For static methods: final prohibits **hiding** when an applicable member relationship exists.

### Runnable example of a static final method

Save **`StaticFinalMethodDemo.java`**:

```java
class Base {
    public static final String version() {
        return "1.0";
    }

    public static String description() {
        return "BASE";
    }
}

class Derived extends Base {
    public static String description() {
        return "DERIVED";
    }

    // public static String version() { return "2.0"; }
    // INVALID if uncommented: Base.version is final.
}

public class StaticFinalMethodDemo {
    public static void main(String[] args) {
        System.out.println(Base.version());
        System.out.println(Base.description());
        System.out.println(Derived.description());
    }
}
```

Commands:

```bash
javac -encoding UTF-8 StaticFinalMethodDemo.java
java StaticFinalMethodDemo
```

Stdout:

```text
1.0
BASE
DERIVED
```

`description()` is not final, so `Derived` can hide it with a static method; `version()` is final, so it cannot be hidden in the same way. There is no instance runtime dispatch here.

## 18. Can you put `final` on a constructor?

**No.** Constructors are not inherited and are not overridden like instance methods, so Java does not allow declaring `final` on a constructor.

**Invalid** example:

```java
class Item {
    // final Item() { } // INVALID: constructors do not accept the final modifier.
}
```

A constructor can be `public`, `protected`, package-private, or `private` according to the rules, but `final` is not a valid constructor modifier.

If you want to prevent **subclasses**, mark the **class** as `final`:

```java
final class Item {
    Item() {
    }
}
```

If you want to **restrict who can create objects directly**, consider a `private`/package-private/protected constructor or a factory API. These are different goals.

### Constructors in a final class still work

A `final` class can have multiple constructors, call `this(...)`, initialize fields, and create multiple instances. The only point regarding inheritance is that no valid subclass can be created to call the superclass constructors of the final class.

## 19. Can `final` and `abstract` go together?

For a **class** or the same **method**, `final` and `abstract` conflict when used to control inheritance in standard declarations:

- `abstract class` exists to be made concrete by a subclass before instantiation.
- `final class` prohibits creating subclasses.
- `abstract method` requires an implementation from an appropriate subclass.
- `final method` prohibits overriding.

Invalid examples:

```java
// abstract final class InvalidType { }
// INVALID: abstract class and final class conflict.
```

```java
abstract class Parent {
    // abstract final void work();
    // INVALID if uncommented: an abstract method cannot be final.
}
```

### However, an abstract class **can contain final concrete methods**

```java
abstract class Base {
    public final void start() {
        System.out.println("Start");
    }

    protected abstract void execute();
}
```

`Base` is abstract, not final. The `start()` method **has a concrete implementation** and is final, while `execute()` is abstract. This is a valid design and is commonly seen in the template method pattern.

**Do not confuse this:** the conflict is marking *the class itself* as both final and abstract, or *the method itself* as both final and abstract; an abstract class having final concrete methods is completely valid.

## 20. A subclass can make a method final when overriding

A superclass provides a method that is allowed to be overridden. An intermediate subclass can **override and mark its own implementation as final**, preventing deeper subclasses from replacing it further.

```java
class Base {
    String label() {
        return "Base";
    }
}

class Middle extends Base {
    @Override
    final String label() {
        return "Middle";
    }
}

class Leaf extends Middle {
    // String label() { return "Leaf"; }
    // INVALID if uncommented: Middle.label() is final.
}
```

This is an option when a hierarchy needs to **leave it open once and then lock it** at a certain level.

### Complete Java 17 program

Save **`FinalOverrideChainDemo.java`**:

```java
class Base {
    String label() {
        return "Base";
    }
}

class Middle extends Base {
    @Override
    final String label() {
        return "Middle";
    }
}

class Leaf extends Middle {
    String extra() {
        return "Leaf extra";
    }
}

public class FinalOverrideChainDemo {
    public static void main(String[] args) {
        Base base = new Base();
        Base middle = new Middle();
        Base leaf = new Leaf();

        System.out.println(base.label());
        System.out.println(middle.label());
        System.out.println(leaf.label());
        System.out.println(((Leaf) leaf).extra());
    }
}
```

```bash
javac -encoding UTF-8 FinalOverrideChainDemo.java
java FinalOverrideChainDemo
```

Stdout:

```text
Base
Middle
Middle
Leaf extra
```

`Leaf` is still allowed to extend `Middle` because the `Middle` class is not final. However, `Leaf` can no longer override `label()`. This shows that **final methods and final classes are two different levels of locking**.

## 21. A subclass can implement an abstract method as `final`

When a superclass has an abstract method:

```java
abstract class Shape {
    abstract double area();
}
```

A concrete subclass can provide a **final implementation**:

```java
class FixedSquare extends Shape {
    private final double edge;

    FixedSquare(double edge) {
        this.edge = edge;
    }

    @Override
    final double area() {
        return edge * edge;
    }
}
```

`FixedSquare.area()` fulfills `Shape`'s abstract method requirement and then locks the ability of subsequent subclasses to override that implementation.

If `FixedSquare` is not marked as a final class, its subclasses can add other methods/fields, but they cannot override `area()`.

### Choosing between a final method and a final class

- Use a **final method** when you want to continue allowing class extension but **disallow replacing a core behavior**.
- Use a **final class** when **no further subclasses** of that class itself should be created.
- If neither requires subclassing capability, a final class usually eliminates the entire override issue; there is no need to attach final to every method just to prevent inheritance.

## 22. Final classes and `sealed` in Java 17

Since Java 17, **sealed classes/interfaces** allow authors to define the **set of permitted direct subclasses or implementations**.

Example:

```java
sealed interface Payment permits Cash, Card {
}

final class Cash implements Payment {
}

non-sealed class Card implements Payment {
}
```

`Cash` is declared final: it is a **terminal branch** in the hierarchy. `Card` is declared non-sealed: it allows the hierarchy to continue expanding under other rules.

For a direct subclass of a sealed class/interface, Java requires declaring an appropriate form, typically:
- `final`: does not allow the sub-branch to extend further;
- `sealed`: continues restricting direct subtypes via `permits`;
- `non-sealed`: removes the sealed restriction for that branch.

### Complete Java 17 program

Save **`SealedFinalDemo.java`**:

```java
sealed interface Payment permits Cash, Card {
    String label();
}

final class Cash implements Payment {
    @Override
    public String label() {
        return "CASH";
    }
}

non-sealed class Card implements Payment {
    @Override
    public String label() {
        return "CARD";
    }
}

class GiftCard extends Card {
    @Override
    public String label() {
        return "GIFT_CARD";
    }
}

public class SealedFinalDemo {
    public static void main(String[] args) {
        Payment first = new Cash();
        Payment second = new Card();
        Payment third = new GiftCard();

        System.out.println(first.label());
        System.out.println(second.label());
        System.out.println(third.label());

        // class OtherCash extends Cash { }
        // INVALID if added as a class: Cash is final.
    }
}
```

```bash
javac -encoding UTF-8 SealedFinalDemo.java
java SealedFinalDemo
```

**Stdout:**

```text
CASH
CARD
GIFT_CARD
```

**Meaning:** `Payment` being sealed does not mean "every subtype is final". It controls **direct permitted subtypes**. One branch can be final, while another branch can be sealed or non-sealed according to the rules.

### `sealed` and `final` are not two modifiers used simultaneously on the same class

Do not write `sealed final class X` with the meaning "allow only some subclasses and prohibit all subclasses" — the two requirements conflict on the same type. Choose one model:
- No subclasses allowed → `final class`.
- A permitted set of subtypes allowed → `sealed class`/`sealed interface`.
- Extension unrestricted by a sealed boundary → a regular class or a valid `non-sealed` subclass.

There is no need to apply a sealed hierarchy if the problem only calls for a simple value object type that cannot be inherited from.

## 23. A record is an implicitly final class

In Java 17, a **record class** is **implicitly final**. It cannot be subclassed using `extends`.

```java
record Point(int x, int y) {
}
```

You cannot:

```java
// class Point3D extends Point { }
// INVALID: cannot extend record Point.
```

A record also has a special superclass, `java.lang.Record`, by language definition, and cannot declare another `extends SomeClass` using regular class syntax.

### A record can still implement an interface

```java
interface Located {
    int x();
}

record Point(int x, int y) implements Located {
}
```

Because the record has a matching public `x()` accessor, it can satisfy that interface method according to Java rules.

### Runnable program

Save **`FinalRecordClassDemo.java`**:

```java
interface Named {
    String name();
}

record Item(String name) implements Named {
}

public class FinalRecordClassDemo {
    public static void main(String[] args) {
        Named value = new Item("Java");

        System.out.println(value.name());
        System.out.println(value instanceof Item);
    }
}
```

```bash
javac -encoding UTF-8 FinalRecordClassDemo.java
java FinalRecordClassDemo
```

Stdout:

```text
Java
true
```

**Do not equate "a record is a final class" with "every record is deeply immutable".** If a record component holds an array or a mutable object, the referenced object can still be modified through an alias. Subclassing capability and the degree of state immutability are **two independent concerns**.

## 24. An interface cannot be declared `final`

An interface is a type contract implemented by other classes or extended by other interfaces according to Java rules. Do not use `final` to declare a regular interface:

```java
// final interface Printable { }
// INVALID: final is not a valid modifier for an interface.
```

If you want to restrict implementations/subinterfaces, Java 17 lets you use a **sealed interface** and `permits`, and select valid subtypes.

### Do not put `final` on interface methods

In an interface, public abstract, default, static, or private methods have their own sets of modifiers. You cannot simply add `final` to an interface method:

```java
interface Printable {
    void print();

    default void run() {
        print();
    }

    // final default void runAgain() { } // INVALID
}
```

A **class implementing an interface** can still declare its implementation method as final:

```java
class Printer implements Printable {
    @Override
    public final void print() {
        System.out.println("Print");
    }
}
```

If the `Printer` class is not final, its subclasses still cannot override `print()`. The class's final method is a constraint imposed by the **implementing class**, not because the interface method itself is final.

## 25. A final method can fulfill an interface contract

A `public final` instance method can satisfy an interface requirement:

```java
interface Executable {
    void execute();
}

class BaseExecutor implements Executable {
    @Override
    public final void execute() {
        System.out.println("Execute");
    }
}

class WorkerExecutor extends BaseExecutor {
    // public void execute() { }
    // INVALID if uncommented: final inherited implementation.
}
```

`WorkerExecutor` is still a subtype of `Executable` through its superclass and can have `execute()` called normally.

### Complete Java 17 example

Save **`FinalInterfaceMethodDemo.java`**:

```java
interface Executable {
    void execute();
}

class BaseExecutor implements Executable {
    @Override
    public final void execute() {
        System.out.println("Base execution");
    }
}

class WorkerExecutor extends BaseExecutor {
    void extra() {
        System.out.println("Worker extra");
    }
}

public class FinalInterfaceMethodDemo {
    public static void main(String[] args) {
        Executable first = new BaseExecutor();
        Executable second = new WorkerExecutor();

        first.execute();
        second.execute();
        ((WorkerExecutor) second).extra();
    }
}
```

```bash
javac -encoding UTF-8 FinalInterfaceMethodDemo.java
java FinalInterfaceMethodDemo
```

Stdout:

```text
Base execution
Base execution
Worker extra
```

The `WorkerExecutor` class **does not override `execute()`**; it inherits the final implementation. Yet its objects still satisfy the `Executable` interface.

## 26. `final` does not change access modifiers or module exports

A final class can be:

```java
public final class PublicApi {
}
```

or package-private:

```java
final class InternalImplementation {
}
```

- `public` and package-private determine who is allowed to use the type according to Java access rules.
- `final` determines whether subclasses may be declared.

Similarly, `public final void work()` is a public final method; `private final void helper()` has private access. There is no "final automatically means private" relationship.

### If using Java modules

A `public final class` located in a package **not exported by a module** can still be directly inaccessible from another module.

`final` does not open a package and does not replace `requires`/`exports`/`opens` in JPMS. This is the **module boundary** layer, independent of inheritance.

When examining an import error, you need to determine whether it is due to type/module visibility or a final-class inheritance requirement, rather than arbitrarily modifying the final modifier.

## 27. `final` on a nested class

A **member nested class** can also be final:

```java
class Outer {
    static final class Nested {
        String value() {
            return "Nested";
        }
    }
}
```

`Outer.Nested` is a static nested class with no implicit enclosing `Outer` instance. The final keyword prevents subclasses of `Nested`, while `static` determines the relationship with the outer instance.

### A non-static inner class can also be final

```java
class Outer {
    final class Inner {
        String text() {
            return "Inner";
        }
    }
}
```

`Inner` is a non-static member inner class: to instantiate it from outside in an allowed context, an outer instance is needed, such as `outer.new Inner()`. It is final, so it cannot be subclassed.

**Static and final are two separate axes**:
- `static nested`: does not require an enclosing instance.
- `final nested`: prohibits inheriting from that nested type.

### Runnable program

Save **`FinalNestedDemo.java`**:

```java
public class FinalNestedDemo {
    static final class Nested {
        String label() {
            return "Nested";
        }
    }

    final class Inner {
        String label() {
            return "Inner";
        }
    }

    public static void main(String[] args) {
        Nested nested = new Nested();
        FinalNestedDemo outer = new FinalNestedDemo();
        Inner inner = outer.new Inner();

        System.out.println(nested.label());
        System.out.println(inner.label());
    }
}
```

```bash
javac -encoding UTF-8 FinalNestedDemo.java
java FinalNestedDemo
```

Stdout:

```text
Nested
Inner
```

The fact that both nested classes are final does not prevent instantiating them in a valid access context.

## 28. Does a `final` class prevent anonymous subclasses?

**Yes.** An anonymous class declared with the syntax `new SomeClass() { ... }` is a form of **subclass** of `SomeClass`, so that syntax cannot be used to extend a final class.

Example:

```java
final class Service {
    void run() {
    }
}

// Service service = new Service() {
//     @Override
//     void run() { }
// };
// INVALID: anonymous subclass of a final class.
```

However, creating an object directly **without a class body** is still valid if the constructor is accessible:

```java
Service service = new Service();
service.run();
```

### Distinguishing an anonymous class implementing an interface

You can write:

```java
Runnable action = new Runnable() {
    @Override
    public void run() {
        System.out.println("Running");
    }
};
```

Here, the anonymous class **implements the `Runnable` interface**, rather than subclassing a final class. Interfaces and final classes serve different roles.

If a framework uses subclass-based proxies to intercept behavior, a final class/final methods can affect the ability to create subclass-style proxies. Some frameworks/tools have other techniques such as delegation or instrumentation; you should not conclude that every mocking tool can never handle final types.

## 29. `Object.getClass()` is an example of a final method in the JDK

The `java.lang.Object` class declares the method:

```java
public final native Class<?> getClass();
```

The `getClass()` method returns a `Class` object representing the **runtime class** of the receiver. It is a final method on the common superclass of Java classes, so subclasses cannot override `getClass()`.

Example:

```java
class Sample {
}
```

```java
Object value = new Sample();
System.out.println(value.getClass().getSimpleName());
```

The result is typically `Sample` for a regular class with the exact name shown in the snippet. `getClass()` has a method implementation guaranteed not to be overridden by subclasses, even though it reflects the runtime class of the object.

**Do not confuse this:** a final method does not necessarily always return a fixed value; `getClass()` is final, yet its result depends on the receiver object.

Some other methods of `Object` are also final according to the specification, but you should rely on the JDK API rather than guessing which methods are "definitely final".

## 30. A final method can still call an overridable method

A final method can contain a call to another **non-final** method. When invoked on a subclass receiver, the inner call can still dispatch dynamically.

Example:

```java
class Parent {
    public final String build() {
        return "Result=" + value();
    }

    protected String value() {
        return "base";
    }
}

class Child extends Parent {
    @Override
    protected String value() {
        return "child";
    }
}
```

With `Parent p = new Child(); p.build();`, the result is `Result=child`.

The `build` method **is not overridden**: it executes `Parent`'s single implementation. However, it calls the `value` method (an overridable hook), so **the output still depends on the runtime subclass**.

### Runnable program

Save **`FinalCallsVirtualDemo.java`**:

```java
class Parent {
    public final String build() {
        return "Result=" + value();
    }

    protected String value() {
        return "base";
    }
}

class Child extends Parent {
    @Override
    protected String value() {
        return "child";
    }
}

public class FinalCallsVirtualDemo {
    public static void main(String[] args) {
        Parent parent = new Parent();
        Parent child = new Child();

        System.out.println(parent.build());
        System.out.println(child.build());
    }
}
```

```bash
javac -encoding UTF-8 FinalCallsVirtualDemo.java
java FinalCallsVirtualDemo
```

Stdout:

```text
Result=base
Result=child
```

**Takeaway:** final locks overriding of **the method marked final**, rather than turning every call inside it into static binding. Therefore, you need to understand all extension points if an invariant must be protected.

## 31. API design: when to choose a final method?

You should consider a **final method** when:

1. There is an **entry point** that must always run validation, normalization, or lifecycle control that subclasses cannot bypass via overriding.
2. The class is a **base class intentionally designed for extension**, where only certain hooks are allowed to be replaced.
3. The API has mandatory contract constraints while subclasses still need to extend via other methods.
4. You want to prevent subclasses from changing an implementation once it has been fixed in the hierarchy.

Example of a base class for a validate-then-execute workflow:

```java
abstract class Job {
    public final void run() {
        validate();
        execute();
    }

    private void validate() {
        // Check common conditions.
    }

    protected abstract void execute();
}
```

However, if `execute` can cause side effects that break invariants, `final run` does not solve the issue completely. You need to design appropriate hook contracts, exception handling, synchronization, and ownership.

### When should you not make a method final?

- You **genuinely want subclasses to replace that method's implementation**.
- A framework needs a specific override to provide behavior or a proxy according to your design.
- The method is a public extension point and overriding behavior is part of the API contract.
- You have not clearly identified why overriding needs to be locked; adding final without justification can make the library harder to extend.

Once a public API is released, changing a method from overridable to final can cause **existing subclass code to fail to compile or fail to link compatibly**, so source and binary compatibility must be considered.

## 32. API design: when to choose a final class?

You should consider a **final class** when:

1. The class is a **value object** or a representation type not intended to be extended through inheritance.
2. You want to retain invariant control that subclasses cannot alter via inheritance.
3. The class is a **utility**, implementation detail, or an object with a well-defined lifecycle not designed to serve as a superclass.
4. You provide extensibility via **interfaces/composition** instead of forcing users to extend a concrete implementation.
5. You want to simplify assumptions about the class's runtime object type by design.

However, a final class can cause friction when:
- Users need to subclass to extend a framework.
- A framework uses proxies via subclassing.
- Tests/mocks rely on subclass-based overriding instead of interfaces or instrumentation.
- You want the library to support intentional extension through inheritance.

**There is no single "every class must be final" rule that applies to every application.** Define a clear extensibility strategy.

### Composition instead of inheritance

If you want users to swap algorithms while keeping a service class final, you can inject an interface:

```java
interface Formatter {
    String format(String input);
}

final class DisplayService {
    private final Formatter formatter;

    DisplayService(Formatter formatter) {
        this.formatter = formatter;
    }

    String display(String value) {
        return formatter.format(value);
    }
}
```

Subclasses of `DisplayService` cannot be created, yet formatting behavior can be swapped via **objects implementing Formatter**.

### Runnable example

Save **`FinalCompositionDemo.java`**:

```java
import java.util.Locale;

interface Formatter {
    String format(String text);
}

final class DisplayService {
    private final Formatter formatter;

    DisplayService(Formatter formatter) {
        this.formatter = formatter;
    }

    String display(String text) {
        return formatter.format(text);
    }
}

public class FinalCompositionDemo {
    public static void main(String[] args) {
        Formatter upper = text -> text.toUpperCase(Locale.ROOT);
        Formatter bracket = text -> "[" + text + "]";

        DisplayService first = new DisplayService(upper);
        DisplayService second = new DisplayService(bracket);

        System.out.println(first.display("java"));
        System.out.println(second.display("java"));
    }
}
```

```bash
javac -encoding UTF-8 FinalCompositionDemo.java
java FinalCompositionDemo
```

Stdout:

```text
JAVA
[java]
```

`DisplayService` is final, yet accepts different implementations of `Formatter`. This is an example of "**closing implementation with a final class, opening behavior with interfaces/composition**".

## 33. Final class, abstract class, and sealed class: decision table

| Need | Common Java choice | Meaning |
| --- | --- | --- |
| No one may subclass this class | `final class` | Locks all class inheritance |
| Need a base class with abstract methods | `abstract class` | Subclasses must fulfill the contract to become concrete |
| Only a specific group of classes may inherit directly | `sealed class` with `permits` | Directly restricts permitted subtypes |
| Allow extending the class while locking one method | `final instance method` | Class remains subclassable; method overriding is locked |
| Allow replacing a few algorithm steps | `final template method` + non-final/abstract hooks | Preserves the main workflow while allowing controlled extension |
| Want callers to choose multiple strategies without extending an implementation | Interface + composition | Extends via collaborating objects |
| A simple data record | `record` | Implicitly final, provides a value-oriented API, though not automatically deeply immutable |

Choose based on **the system's goals**, not just to silence a temporary compile error.

## 34. Common false conclusions

| False conclusion | What is true |
| --- | --- |
| "Final methods cannot be called from a subclass" | They can be called/inherited if validly accessible; only overriding is disallowed |
| "A final method forbids all methods with the same name" | Overloading with a different signature is still valid |
| "Simply removing `@Override` lets you override a final method" | No, the error is in the override attempt |
| "Static final methods use dynamic dispatch" | Static methods are not dynamically overridden; final can prevent hiding |
| "A private final method prevents subclasses from declaring the same name" | Private methods are not inherited for overriding like public/protected methods; the same name in a subclass can be its own separate method |
| "A final class cannot be instantiated" | Objects can be created if a constructor is accessible |
| "A final class cannot implement interfaces" | It completely can |
| "A final class cannot extend any class" | It can extend a non-final superclass; it cannot be subclassed further |
| "Every method of a final class must be written with final" | Not required; a final class already cannot have subclasses |
| "A final class is immutable" | No; mutable fields/mutators can still exist |
| "A final method is read-only" | No; a final method can still update state |
| "Final is an access modifier" | No; `public`/`protected`/package-private/`private` is a separate aspect |
| "A constructor can be final because you do not want overriding" | Constructors are not overridden and cannot use the final modifier |
| "An abstract final class allows controlled implementation by subclasses" | The two modifiers conflict on the same class |
| "An interface method can be final just like a class method" | Interfaces do not support that kind of final method modifier |
| "A class being both sealed and final at the same time is safer" | The two states conflict on the same class |
| "Records are final so they hold immutable arrays" | A record class is final, but array components can still be mutable |
| "Final definitely makes every call faster" | There is no such performance guarantee |
| "Final prevents all frameworks from mocking/proxying" | Depends on the technique; subclass proxies are restricted, yet other techniques exist |
| "If a final method calls a hook, the hook is also locked" | A non-final hook can still be overridden and dynamically dispatched |

## 35. Self-check exercises with answers

### Exercise 1 — Overriding a final method

```java
class A {
    final void work() {
    }
}

class B extends A {
    // void work() { }
}
```

**Question:** Is uncommenting `B.work()` valid?

**Answer:** **No.** `B.work()` would override `A.work()`, which is final. Omitting `@Override` does not change the nature of the override relationship.

### Exercise 2 — Overloading with a final method

```java
class A {
    final void work(int id) {
    }
}

class B extends A {
    void work(String name) {
    }
}
```

**Answer:** Valid. `work(String)` and `work(int)` are two different signatures. `B` inherits `A.work(int)` and adds its own overload.

### Exercise 3 — Does a final class have a constructor?

```java
final class Key {
    Key() {
    }
}
```

**Answer:** Yes. `new Key()` is valid from a context permitted to call the constructor (for example, the same package). However, `class SubKey extends Key` is invalid.

### Exercise 4 — A final class implements an interface

```java
interface Named {
    String name();
}

final class User implements Named {
    @Override
    public String name() {
        return "An";
    }
}
```

**Answer:** Valid. A final class cannot be subclassed, yet it can completely implement an interface and be used through a `Named`-typed variable.

### Exercise 5 — Can a final class still have a mutable field?

```java
final class Box {
    int value;
}

Box box = new Box();
box.value = 5;
box.value = 8;
System.out.println(box.value);
```

**Answer:** Prints `8` in a valid field-access context. `final class` only locks inheritance; it does not automatically make instance fields final or private.

### Exercise 6 — Can a final instance method be called via a subclass?

```java
class Base {
    final String label() {
        return "Base";
    }
}

class Child extends Base {
}

System.out.println(new Child().label());
```

**Answer:** Prints `Base`. The final method is still inherited/callable. The subclass only cannot override it.

### Exercise 7 — Static final hiding

```java
class Base {
    static final String version() {
        return "1";
    }
}

class Child extends Base {
    // static String version() { return "2"; }
}
```

**Answer:** Uncommenting causes an error because `Child` attempts to hide the corresponding static final method. Static methods do not have dynamic overriding, yet final still imposes a restriction on hiding.

### Exercise 8 — Overriding and `final` in an intermediate class

```java
class Base {
    String value() {
        return "A";
    }
}

class Middle extends Base {
    @Override
    final String value() {
        return "B";
    }
}

class Leaf extends Middle {
}
```

**Answer:** `new Leaf().value()` returns `B`. `Middle` is allowed to override `Base`'s non-final method and then locks further overriding in `Leaf`.

### Exercise 9 — A final method calling a hook

```java
class Parent {
    final String message() {
        return text();
    }

    String text() {
        return "parent";
    }
}

class Child extends Parent {
    @Override
    String text() {
        return "child";
    }
}
```

**Answer:** `new Child().message()` returns `child`. `message()` is final and cannot be overridden, yet it calls the non-final `text()`, so virtual dispatch still selects `Child.text()`.

### Exercise 10 — Final constructor?

```java
class A {
    // final A() { }
}
```

**Answer:** Syntax with `final` on a constructor is invalid. Constructors are not inherited/overridden; if you want to prevent subclasses, declare `final class A`.

### Exercise 11 — Can an abstract class have a final method?

```java
abstract class Base {
    final void validate() {
        System.out.println("OK");
    }

    abstract void work();
}
```

**Answer:** Valid. `Base` is abstract, `validate()` is concrete and final; only `work()` is abstract and needs to be appropriately implemented.

### Exercise 12 — Records and `final`

```java
record Point(int x, int y) {
}
```

**Answer:** The `Point` class is implicitly final and cannot be extended. However, you can still instantiate `new Point(1, 2)` and implement interfaces in its declaration.

### Exercise 13 — Sealed hierarchy

```java
sealed interface Result permits Success, Failure {
}

final class Success implements Result {
}

non-sealed class Failure implements Result {
}
```

**Answer:** `Success` terminates the branch and has no subclasses. `Failure` can be subclassed according to regular class rules because it is `non-sealed`. The declared direct implementations are listed in `Result`'s permits clause.

### Exercise 14 — Final class and a mutable collection

```java
final class Basket {
    private final java.util.List<String> items =
            new java.util.ArrayList<>();

    void add(String name) {
        items.add(name);
    }

    int size() {
        return items.size();
    }
}
```

**Answer:** `Basket` cannot be subclassed, and the `items` field cannot be reassigned, yet elements can still be added/removed from the list via the API. You cannot infer that the object is immutable/thread-safe.

### Exercise 15 — Final or interface + composition?

You want to provide a `ReportService` class that is not intended to be subclassed, yet callers need to choose between a CSV and a JSON formatter.

**Suggested answer:** Use a `final class ReportService` that depends on a `Formatter` interface, allowing callers to pass in the appropriate implementation. This extends behavior via composition without forcing callers to extend `ReportService`.

## 36. Checklist when using `final` on a method/class

1. **Do you want to lock a method or an entire hierarchy?** Choose `final method` or `final class` according to the desired scope.
2. **Is the method being marked final an instance method or a static method?** Instance relates to overriding; static relates to hiding.
3. **Does the method need to be callable from subclasses?** A final method is still inherited/callable if access permits.
4. **Is overloading needed?** Final does not forbid overloading with a different signature.
5. **Are you using `@Override` while trying to rewrite a final method?** Removing the annotation does not solve it.
6. **Is there a non-final hook inside a final template method?** Understand that the hook still dispatches dynamically.
7. **Does a final class need to be instantiated?** Final does not prohibit regular constructors.
8. **Does a final class need to implement an interface?** That is still valid, as long as the interface contract is satisfied.
9. **Can a final class extend a parent class?** Yes, if the parent class is not final and other rules are satisfied.
10. **Distinguish a final class from an immutable object:** have mutable state and aliases been controlled?
11. **Distinguish a final method from a pure/read-only method:** a final method can still modify data.
12. **If a method is private, do you need to add final?** Private methods are not overridden in the normal way.
13. **If a method is package-private**, have you checked package/access rules before concluding a subclass overrides it?
14. **If a superclass method is static**, are we talking about hiding or overriding?
15. **If designing an abstract base class**, final concrete methods are valid, whereas abstract final on the same method is not.
16. **If designing a sealed hierarchy**, do direct subclasses have the appropriate modifiers? Do not put both sealed and final on the same class.
17. **If using a record**, remember records are implicitly final, yet mutable components can still expose state.
18. **If using an interface**, do not mark the interface or interface methods as final; use a sealed interface or a final implementing class as needed.
19. **If a framework requires proxies/subclassing**, does a final class or final method affect it? Is there a suitable API via interfaces/delegation?
20. **If changing an already-released public API**, have you evaluated the compatibility impact of locking overriding/subclassing?
21. **If the goal is performance**, have you benchmarked it? Do not treat final as a directive guaranteeing inlining.
22. **If the compiler reports an error**, distinguish errors for extending a final class, overriding a final instance method, hiding a static final method, or access/type mismatches.
23. **If the program has mutable shared state**, have you handled validation, encapsulation, and thread safety separately?
24. **If you want to provide safe extension points**, clearly document which methods are allowed to be overridden and which invariants the final method must preserve.

## Key takeaways

- **`final` on an instance method prevents overriding**, does not prevent **calling/inheriting** the method, and does not prevent **overloading** with a different signature.
- **`final` on a static method prevents valid hiding in a subclass**, and does not turn a static method into a dynamic-dispatch method.
- **`final class` prevents any other class from extending that class**, yet that class itself **can extend a superclass**, **implement interfaces**, have constructors, and create multiple objects.
- **`final` on classes and methods does not guarantee immutable state**. Mutable fields, mutable components, and side effects can still exist.
- **`private`/`public` and `final` are independent**: access modifiers determine accessibility, while `final` determines whether behavior can be replaced through inheritance.
- **Constructors cannot be final**, and **abstract + final** cannot be used simultaneously on the same class/method when they conflict.
- **A final method can call a non-final hook**: the final method itself cannot be overridden, yet the hook can still dispatch according to the subclass.
- In a Java 17 **sealed hierarchy**, `final` helps terminate a permitted branch. A **Record** is also an implicitly final class.
- Choose `final` to express a **clear extension contract**, not merely "to be safe" or expecting speed; if you need to open behavior without opening inheritance, use **interface + composition**.
