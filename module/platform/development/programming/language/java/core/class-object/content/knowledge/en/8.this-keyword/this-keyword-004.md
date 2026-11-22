# Passing `this` as an Argument and Returning `this` in Java

In Java, the **`this`** keyword is an expression that refers to the **current object** when code is executing in an instance context. Beyond the familiar uses of `this.field` to refer to a data field and `this.method()` to invoke a method, `this` can also be used as **a reference value**:

- **Passing `this` as an argument:** `otherMethod(this)` passes a reference to the currently executing object to another method.
- **Returning `this`:** `return this;` provides the current object's own reference to the caller, commonly to build **fluent** APIs with *method chaining*.

Key point: neither operation **creates a new object** nor **copies the entire object**. Java passes arguments **by value**; when the argument is `this`, the copied value is the **reference** to the object. With `return this`, the returned value is a reference to **the current object itself**.

Introductory example:

```java
class Profile {
    String name;

    Profile(String name) {
        this.name = name;
    }

    void introduceTo(Printer printer) {
        printer.print(this);   // Pass the current Profile object
    }

    Profile rename(String newName) {
        this.name = newName;
        return this;          // Return the same Profile object
    }
}

class Printer {
    void print(Profile profile) {
        System.out.println(profile.name);
    }
}
```

If `Profile p = new Profile("An");`, and then `p.introduceTo(new Printer());` is called, `Printer.print` receives a reference to `p`. The statement `p.rename("Bình")` modifies the name and then returns **the same `p` instance**, allowing you to write `p.rename("Bình").introduceTo(new Printer());`.

The snippet above illustrates class declarations; a complete program with compilation commands and stdout is presented below.

## 1. What Is `this`? Distinguishing Syntaxes Using the `this` Keyword

Although it is the same keyword, its different syntactic forms serve different purposes:

| Syntax | Meaning | Example |
| --- | --- | --- |
| `this` | Reference to the current object | `register(this)` |
| `this.field` | Access a field of the current object | `this.name = name` |
| `this.method()` | Call an instance method via the current receiver | `this.validate()` |
| `this(arguments)` | Call **another constructor in the same class** | `this("Mặc định", 0);` |
| `return this;` | Return the current object reference from an appropriate method | `Builder step() { return this; }` |
| `Outer.this` | Refer to the enclosing `Outer` instance from an eligible inner class | `Printer.print(Outer.this)` |

**Do not equate `this` and `this(...)`:** standalone `this` is a reference expression; `this(...)` is a **constructor invocation** syntax that must obey special constructor placement rules (in Java 17, an explicit `this(...)` call must be the first statement).

In an **instance method** and a **constructor of a regular class**, `this` refers to the current object. In a **static method**, no current object exists, so **`this` cannot be used**.

`this` is also not the name of a variable that can be reassigned:

```java
// WRONG:
this = anotherObject;
```

You can modify the object's state via `this.field = value` if the field permits, but you cannot make `this` "point to" another object.

## 2. Passing `this` as an Argument: Core Principles

When an instance method of class `A` calls:

```java
receiver.process(this);
```

then:

1. The compiler checks that the `process` method is callable, accessible, and that the type of `this` can be converted to the corresponding parameter type.
2. The value of the `this` expression is the **reference to the `A` object currently executing the method**.
3. The `process` method receives **a copy of that reference value** through its formal parameter variable.
4. The object in the original call and the new parameter variable can be **the same object**.
5. When the receiving method **reassigns the parameter variable**, it does not reassign `this` or the caller's reference variable; **modifying fields of the shared referenced object** can be observed from multiple places.

For example:

```java
class Document {
    String title;

    void sendTo(Inspector inspector) {
        inspector.inspect(this);
    }
}

class Inspector {
    void inspect(Document document) {
        System.out.println(document.title);
    }
}
```

`Document.sendTo` passes the exact object receiving the call into `Inspector.inspect`. There is no need to create a `new Document()` just to provide the current information.

### `this` Is Not Limited to Arguments of the Same Class Type

A parameter can accept `this` if its type is compatible:

```java
class Task implements Runnable {
    @Override
    public void run() {
        System.out.println("Đang chạy");
    }

    void submit(Executor executor) {
        executor.execute(this); // this can be used as a Runnable
    }
}

interface Executor {
    void execute(Runnable job);
}
```

`Task` implements `Runnable`, so the `this` reference in an instance method of `Task` is used as an argument of type `Runnable`. Depending on the design, the parameter can also be a superclass, an interface, or `Object`.

This example is an **illustrative declaration**: `Executor` is a custom-defined interface in the code snippet, not the name of a specific class that must be available in the JDK. There is no `main` method to run it on its own.

## 3. Complete Program: An Object Passing Itself to Another Object

Save as **`PassThisDemo.java`**:

```java
class Cart {
    private int quantity;

    Cart(int quantity) {
        this.quantity = quantity;
    }

    void add(int amount) {
        quantity += amount;
    }

    int quantity() {
        return quantity;
    }

    void sendTo(Auditor auditor) {
        auditor.inspect(this);
    }
}

class Auditor {
    void inspect(Cart cart) {
        cart.add(2);                   // Modify the shared object
        cart = new Cart(99);           // Only reassign the parameter variable
        System.out.println("Trong auditor: " + cart.quantity());
    }
}

public class PassThisDemo {
    public static void main(String[] args) {
        Cart cart = new Cart(3);
        Auditor auditor = new Auditor();

        cart.sendTo(auditor);
        System.out.println("Ngoài auditor: " + cart.quantity());
    }
}
```

Run with JDK 17 or later:

```bash
javac -encoding UTF-8 PassThisDemo.java
java PassThisDemo
```

**Exact stdout:**

```text
Trong auditor: 99
Ngoài auditor: 5
```

**Why are the results different?**

- `cart.sendTo(auditor)` runs on the `Cart` object with `quantity = 3`.
- Inside `Cart.sendTo`, `this` refers to **that very `Cart` object**.
- When `Auditor.inspect(this)` runs, the parameter variable `cart` of `inspect` initially points to this same `Cart` object.
- `cart.add(2)` mutates the original object's state: `quantity` becomes `5`.
- `cart = new Cart(99)` **reassigns only the parameter variable** `cart` inside `inspect`. It neither modifies the `this` reference in `Cart.sendTo` nor modifies the `cart` variable in `PassThisDemo.main`.
- The line in `Auditor.inspect` prints the quantity of the new object, `99`; after the call returns, `main` still holds the original object with quantity `5`.

Reference diagram:

```text
Before inspect reassigns the parameter:

main.cart ─────────────────────┐
                               ├──> Cart #1 { quantity: 5 }
inspect.cart (ref copy) ───────┘

After inspect executes cart = new Cart(99):

main.cart ─────────────────────────> Cart #1 { quantity: 5 }
inspect.cart ──────────────────────> Cart #2 { quantity: 99 }
```

`#1` and `#2` are only illustrative labels, not JVM memory addresses.

**Conclusion:** passing `this` is **pass-by-value of the reference**, not pass-by-reference of the variable. To keep a new object, the receiving method must **return the reference**, and the caller decides whether to assign it to an outer variable.

## 4. How Does Passing `this` Differ from Passing the Fields of `this`?

Consider two APIs:

```java
static void printName(String name) {
    System.out.println(name);
}

static void printPerson(Person person) {
    System.out.println(person.name());
}
```

And a `Person` class:

```java
class Person {
    private final String name;

    Person(String name) {
        this.name = name;
    }

    String name() {
        return name;
    }

    void report() {
        Reporter.printName(this.name); // Pass the String field value
        Reporter.printPerson(this);    // Pass the current Person reference
    }
}
```

Here it is assumed that the two methods `printName`/`printPerson` are `static` methods of the `Reporter` class. These separate declarations are for illustration only; they do not form a complete runnable file.

Differences:

- `printName(this.name)` provides only the **value of the `name` field** to the receiver. The receiver does not automatically gain access to other fields of `Person`.
- `printPerson(this)` provides a **reference to the entire object**. The receiver can call public/accessible methods on the object according to the parameter type, and may mutate state if the API allows it.
- Passing a reference does not turn `private` fields into `public` ones. The receiver is still bound by Java's normal access control rules.

**API design:** if the receiver only needs `name`, prefer passing `String` or a narrower piece of data when appropriate; avoid passing the entire `this` if doing so would allow the receiver to retain or mutate the object unintentionally.

## 5. Passing `this` to Notify or Collaborate with Another Object

Some sensible use cases for passing `this`:

- **Visitor/processor:** the current object hands itself over to a processor accessible through an interface.
- **Observer or event source:** sends a reference of the event-emitting source to a listener.
- **Bidirectional relationship:** an object adds itself to a container or group.
- **Command/callback:** passes a reference to the current object to an orchestrating component.
- **Post-initialization registration:** lets a registry manage an already-constructed object.

A simple visitor example, file **`VisitorThisDemo.java`**:

```java
interface Printable {
    String text();
    void accept(PrintVisitor visitor);
}

class Note implements Printable {
    private final String content;

    Note(String content) {
        this.content = content;
    }

    @Override
    public String text() {
        return content;
    }

    @Override
    public void accept(PrintVisitor visitor) {
        visitor.visit(this);
    }
}

class PrintVisitor {
    void visit(Printable source) {
        System.out.println("Visit: " + source.text());
    }
}

public class VisitorThisDemo {
    public static void main(String[] args) {
        Printable note = new Note("Java");
        PrintVisitor visitor = new PrintVisitor();
        note.accept(visitor);
    }
}
```

Run:

```bash
javac -encoding UTF-8 VisitorThisDemo.java
java VisitorThisDemo
```

**Stdout:**

```text
Visit: Java
```

`Note.accept` calls `visitor.visit(this)` to pass **the current `Note` object**. The `visit` method accepts a parameter of interface type `Printable`, so the call is valid. The visitor can use `source.text()` without needing to know the private fields inside `Note`.

**Note on content scope:** this is an example of two objects collaborating, not yet a full implementation of the *Visitor Design Pattern* with multiple `visit(Type)` overloads. If subclass-specific overloads are used, you also have to consider compile-time overload resolution; the syntax for passing `this` itself remains the same.

## 6. Returning `this`: The Current Object Itself Is Returned

An instance method can return `this` if its declared return type is **compatible with the reference type of the current object**.

Example:

```java
class Counter {
    private int value;

    Counter increment() {
        value++;
        return this;
    }

    int getValue() {
        return value;
    }
}
```

Given `Counter counter = new Counter();`:

```java
Counter result = counter.increment();
System.out.println(result == counter); // true
```

`increment()` increments the `value` field of the `counter` object and returns the **same reference** `counter`. The `==` operator on the two reference variables returns `true` because they point to the same object.

**`return this` does not invoke a constructor**, does not copy the object, does not automatically make the object immutable, and does not guarantee that the method performs any "building" action if the author does not update state before returning.

### 6.1. Return Type Requirements

The following declarations can be valid:

```java
class Base {
    Base self() {
        return this;
    }

    Object asObject() {
        return this;
    }
}
```

In class `Base`, `this` has a type compatible with `Base` and `Object`. If `Base` implements an interface `Named`, an instance method of `Base` can return `Named` with `return this;`.

Conversely:

```java
class InvalidReturn {
    void self() {
        // return this; // WRONG: a void method cannot return a value
    }

    int number() {
        // return this; // WRONG: an InvalidReturn reference is not an int
        return 0;
    }
}
```

The return type must be compatible **at compile time**, not merely based on which subclass happens to be used at runtime.

### 6.2. How `return this` Differs from `return new Type(...)`

| Form | Result | Use Case |
| --- | --- | --- |
| `return this;` | Returns **the current receiver object itself** | Fluent API mutating the object in place |
| `return new Type(...);` | Returns a new object created by `new` | Modified copy, immutable objects, factory |
| `return other;` | Returns the object referenced by the `other` variable | Return selection/delegation |
| `return null;` | Returns a null reference if the return type allows | Requires a clear contract; error-prone when chaining |
| `return this.field;` | Returns the value of an object's field | Getter or returning related data |

Do not assume a method named `withName(...)` is immutable: you must check whether the implementation uses `return this` or creates a new object.

## 7. Method Chaining: The Typical Benefit of `return this`

**Method chaining** is the practice of invoking methods consecutively on the value returned by the preceding method. For methods that return `this`, each intermediate result remains **the same object**.

Example:

```java
draft.to("An").body("Chào").append(" Java").show();
```

The call chain is equivalent in order of effect to:

```java
draft.to("An");
draft.body("Chào");
draft.append(" Java");
draft.show();
```

Because each updating method returns `draft`, the next call can continue using that same receiver.

### 7.1. Complete Java 17 Program: Fluent Interface

Save the entire program to **`FluentDemo.java`**:

```java
class MessageDraft {
    private String recipient = "";
    private String content = "";

    MessageDraft to(String recipient) {
        this.recipient = recipient;
        return this;
    }

    MessageDraft body(String content) {
        this.content = content;
        return this;
    }

    MessageDraft append(String suffix) {
        this.content += suffix;
        return this;
    }

    String build() {
        return "To: " + recipient + " | Body: " + content;
    }
}

public class FluentDemo {
    public static void main(String[] args) {
        MessageDraft draft = new MessageDraft();

        MessageDraft same = draft.to("An")
                .body("Chào")
                .append(" Java");

        System.out.println(same == draft);
        System.out.println(draft.build());

        same.append(" 17");
        System.out.println(draft.build());
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 FluentDemo.java
java FluentDemo
```

**Exact stdout:**

```text
true
To: An | Body: Chào Java
To: An | Body: Chào Java 17
```

Analysis:

1. `new MessageDraft()` creates **a single instance** and stores the reference in `draft`.
2. `draft.to("An")` updates the `recipient` field and then executes `return this;`.
3. The result of `to` is used as the receiver for `body`; `body` updates the `content` field and also executes `return this;`.
4. `append(" Java")` further modifies `content` and returns the same object; therefore `same == draft` is `true`.
5. `same.append(" 17")` mutates the state of **`draft`'s very own object**; the final printed line reflects that change.

**Important:** the code above is a **mutable fluent API**. The chain only modifies the fields of **one object**. If you need to keep a previous version for separate use, you must create a copy or design an immutable API that returns a new object.

### 7.2. Why Is There No Need to Write `new` at Each Step?

Because `return this` preserves the same reference, each step can be written concisely:

```java
MessageDraft draft = new MessageDraft();
draft.to("An").body("Hello");
```

There is no hidden `new MessageDraft()` inside `to` or `body` in the example. Java also does not implicitly copy the object when receiving the result of `return this`.

This is often useful for configuration builders, sequential state processors, or objects requiring multiple consecutive operations. However, returning the same instance can lead to **shared mutable state** if multiple parts of the code hold onto the same reference.

## 8. Practical Designs: Return `this` or Return Another Result?

Not every method should return `this`.

| Behavior | Appropriate Return Type | Reason |
| --- | --- | --- |
| Modifying configuration and allowing subsequent calls | Current class type, `return this` | Fluent mutable |
| Performing a single action without the caller needing to chain | `void` | Simple API |
| Reading a value | `String`, `int`, appropriate type | Caller needs the result |
| Creating an independent version with changes | Class type, `return new ...` | Immutable/copy style |
| Checking success/failure | `boolean` or result type | Returns business outcome information |
| Finalizing a builder to create a product | Product type | `build()` does not necessarily return `this` |
| Searching | Element type/`Optional<T>` | Returns the found data |

For example, a builder might have:

```java
Builder setName(String name) {
    this.name = name;
    return this;
}

Product build() {
    return new Product(name);
}
```

These are **two illustrative methods** in a `Builder` class assumed to have a `name` field and an appropriate `Product` class, not a standalone runnable snippet. The setters return `this` for chaining; `build()` returns a **different product object**, so `build()` should not automatically use `return this` if the product type differs.

### 8.1. Should Every `void` Setter Be Changed to Return `this`?

Not mandatory. A simple `void` setter can be very clear:

```java
void setName(String name) {
    this.name = name;
}
```

Changing it to:

```java
Person setName(String name) {
    this.name = name;
    return this;
}
```

is only useful if the API genuinely intends to support operation chaining and the `Person` type is appropriate. For external libraries, changing the return type also affects binary/API compatibility; you should not arbitrarily alter a published contract.

## 9. Distinguishing Mutable Fluent Methods from Immutable "with" Methods

The two styles can **look identical at the call site** while having completely different semantics.

### Mutable: `return this`

```java
class MutablePoint {
    int x;

    MutablePoint move(int delta) {
        x += delta;
        return this;
    }
}
```

`point.move(2).move(3);` updates **the same object** twice.

### Immutable: Creating a New Object

```java
final class ImmutablePoint {
    private final int x;

    ImmutablePoint(int x) {
        this.x = x;
    }

    ImmutablePoint move(int delta) {
        return new ImmutablePoint(x + delta);
    }

    int x() {
        return x;
    }
}
```

`original.move(2)` returns a new object with an updated `x`, while `original` remains unchanged. Even though both can be chained, the immutable form requires **using the returned result**.

### Standalone Example Checking Object Identity

Save as **`MutableImmutableDemo.java`**:

```java
class MutablePoint {
    private int x;

    MutablePoint(int x) {
        this.x = x;
    }

    MutablePoint move(int delta) {
        this.x += delta;
        return this;
    }

    int x() {
        return x;
    }
}

final class ImmutablePoint {
    private final int x;

    ImmutablePoint(int x) {
        this.x = x;
    }

    ImmutablePoint move(int delta) {
        return new ImmutablePoint(x + delta);
    }

    int x() {
        return x;
    }
}

public class MutableImmutableDemo {
    public static void main(String[] args) {
        MutablePoint mutable = new MutablePoint(1);
        MutablePoint changed = mutable.move(2);

        ImmutablePoint immutable = new ImmutablePoint(1);
        ImmutablePoint next = immutable.move(2);

        System.out.println(mutable.x());
        System.out.println(mutable == changed);
        System.out.println(immutable.x());
        System.out.println(next.x());
        System.out.println(immutable == next);
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 MutableImmutableDemo.java
java MutableImmutableDemo
```

Stdout:

```text
3
true
1
3
false
```

The output shows that `return this` preserves the **identity** of the mutable object, whereas `return new ImmutablePoint(...)` creates a different object and leaves the original object unchanged.

**A chained call alone is not enough to infer** whether an API is mutable or immutable. Check the method body and the contract documented in its specification.

## 10. `return this` and the Declared Type of the Receiver Under Inheritance

With inheritance, `this` represents **the current runtime object**, but a method's **declared return type** determines which subsequent calls can be written at compile time.

Example:

```java
class BaseBuilder {
    BaseBuilder configure() {
        return this;
    }
}

class ExtendedBuilder extends BaseBuilder {
    void extra() {
        System.out.println("extra");
    }
}
```

Given:

```java
ExtendedBuilder builder = new ExtendedBuilder();
BaseBuilder result = builder.configure();
System.out.println(result == builder); // true

// builder.configure().extra(); // WRONG: configure() is declared to return BaseBuilder
```

Even though the actual object is an `ExtendedBuilder` and `return this` returns the same reference, **the static type of the expression `builder.configure()` is still `BaseBuilder`**; the `BaseBuilder` class does not declare an `extra` method.

### 10.1. Covariant Return When Overriding

A subclass can override a method with a **more specific** reference return type if Java's rules allow it:

```java
class BaseBuilder {
    BaseBuilder configure() {
        return this;
    }
}

class ExtendedBuilder extends BaseBuilder {
    @Override
    ExtendedBuilder configure() {
        super.configure();
        return this;
    }

    void extra() {
        System.out.println("extra");
    }
}
```

With an `ExtendedBuilder builder` variable, the call `builder.configure().extra();` is now **valid** because the overridden version declares a return type of `ExtendedBuilder`. If the receiver is only declared as type `BaseBuilder`, the compiler still checks the API visible through `BaseBuilder`.

**Do not confuse returning `this` with dynamic overload selection:** `return this` does not alter Java's rule of resolving overloads based on the compile-time types of arguments/receivers. For complex fluent hierarchies, you may need to design concrete return types or a generic self-type; you should not overuse casts to force the compiler.

### 10.2. Generic Self-Type (Extended Topic)

Some libraries use a *self-referential generic* pattern to preserve the fluent type for subclasses:

```java
abstract class BaseBuilder<T extends BaseBuilder<T>> {
    abstract T self();

    T configured() {
        // Modify shared configuration.
        return self();
    }
}

final class ConcreteBuilder extends BaseBuilder<ConcreteBuilder> {
    @Override
    ConcreteBuilder self() {
        return this;
    }

    ConcreteBuilder special() {
        return this;
    }
}
```

By returning `T`, the `configured()` method can produce the type matching `ConcreteBuilder` at the call site. This is an illustrative declaration snippet and has no `main` method.

**Limitation:** the generic self-type is a useful design pattern, but it can increase complexity and requires a strict contract between superclass and subclass. For small builders, using a concrete class with `return this` is usually simpler.

## 11. Using `this` in a Constructor: Caveats When Exposing It Externally

Inside a constructor, `this` refers to the object **currently being initialized**, which may not yet satisfy its final invariants. A statement like `this.name = name;` only updates state in place, whereas `registry.add(this)`, `executor.submit(this::run)`, or registering a callback can **publish the receiver before the constructor finishes**.

Example of what should not be done in a constructor:

~~~java
class EarlyListener {
    private String token;

    EarlyListener(Registry registry) {
        registry.register(this);  // Might be called back immediately
        token = "READY";
    }
}
~~~

This is an illustrative snippet; `Registry` is an assumed collaborator and is not declared to run standalone. If the registry uses the reference before `token` is assigned, it may observe null. Prefer **initializing all state first**, and then registering in a factory or lifecycle method; if multiple threads are involved, you also need to consider **safe publication**. The lesson **Risks of Letting this Escape Before Initialization Completes** thoroughly explains synchronous callbacks, dynamic dispatch in constructors, `final` fields, and the Java Memory Model.

## 12. Do Not Confuse the `this` Expression with Static Contexts or Constructor Chaining

| Syntax | When Is It Valid? | Meaning |
| --- | --- | --- |
| `processor.accept(this)` | In an instance context with a compatible type | Passes **the current object's reference** to `accept` |
| `return this;` | In an instance method with a compatible return type | Returns the current object |
| `this(field)` | In a valid explicit constructor invocation position | Calls **another constructor in the same class**, does not pass the `this` receiver |
| `this.field` | When a valid current instance exists | Accesses a field of the current object |
| `return this;` in a constructor | Invalid | A constructor does not return a reference value |
| `this` in a static method | Invalid | There is no current receiver |

In Java 17, an explicit `this(...)` or `super(...)` constructor call must be at the **beginning of the constructor body**; regular statements cannot precede it, nor can its argument expressions rely on the not-yet-initialized receiver. The lesson **Distinguishing this, this(), and Class Names** covers constructor chaining rules along with compile-time examples.

## 13. `this` in Inner Classes and `Outer.this`

Inside a **non-static inner class**, `this` represents the **inner instance**; when you want to pass the outer object, use qualified `Outer.this` if the context allows it:

~~~java
class Outer {
    class Inner {
        void send(Receiver receiver) {
            receiver.accept(this);       // Inner object
            receiver.accept(Outer.this); // Outer object
        }
    }

    interface Receiver {
        void accept(Object value);
    }
}
~~~

Both perform a "pass this" operation, yet the two expressions select **two different receivers**, so which object the callback receives depends on the syntax. A static nested class does not inherently have an enclosing `Outer.this`. To understand multiple levels of enclosing instances, study the dedicated lesson **Accessing the Enclosing Object with Outer.this**.

## 14. `this` in Lambdas and Anonymous Classes

A lambda **does not introduce a new `this` receiver**: `this` inside a lambda takes its meaning from the enclosing context. An anonymous class, by contrast, has **its own instance**, so `this` inside its body refers to the anonymous object:

~~~java
class Owner {
    Runnable lambda() {
        return () -> System.out.println(this == Owner.this);
    }

    Runnable anonymous() {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println(this == Owner.this);
            }
        };
    }
}
~~~

If you call `new Owner().lambda().run()`, it prints `true`; with `anonymous().run()`, it prints `false`. Therefore, code that passes `this` from a lambda versus an anonymous callback may pass **two different objects**. In a static context, a lambda does not automatically provide a `this` receiver. Exceptions regarding lexical enclosing/qualified `this` are covered in a separate lesson.

## 15. `return this` in an Interface Default Method

An interface **default** method has a body and can use `this` when invoked on an implementing object.

```java
interface Named {
    String name();

    default Named printName() {
        System.out.println(name());
        return this;
    }
}

class User implements Named {
    private final String value;

    User(String value) {
        this.value = value;
    }

    @Override
    public String name() {
        return value;
    }
}
```

`Named.printName()` returns **the current implementing object itself**, but its declared return type is `Named`. When chaining further, the compiler only allows methods available on the static type `Named` (or a more specific type provable in context).

Complete example **`DefaultThisDemo.java`**:

```java
interface Named {
    String name();

    default Named printName() {
        System.out.println(name());
        return this;
    }
}

class User implements Named {
    private final String value;

    User(String value) {
        this.value = value;
    }

    @Override
    public String name() {
        return value;
    }
}

public class DefaultThisDemo {
    public static void main(String[] args) {
        User user = new User("An");
        Named same = user.printName();
        System.out.println(same == user);
        same.printName();
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 DefaultThisDemo.java
java DefaultThisDemo
```

Stdout:

```text
An
true
An
```

This is a practical example: an interface can provide a default method that **both performs an operation and returns the receiver**. Returning the interface type preserves a general contract; if chaining `User`-specific methods is needed, the API or return type must be designed accordingly.

## 16. Common Compile-Time Errors When Passing or Returning `this`

| Code Snippet / Situation | Error or Misconception | How to Fix |
| --- | --- | --- |
| `static void f() { use(this); }` | No `this` exists in a static context | Pass the provided object via a variable/parameter |
| `void f() { return this; }` | `void` does not allow returning a value | Change to an appropriate return type or use `return;` |
| `int f() { return this; }` | `this` is a reference, not convertible to `int` | Return an `int` field or expression |
| `Constructor() { return this; }` | A constructor has no return type | Use an instance method or factory that returns an object |
| `target.use(this)` when `use` expects an incompatible type | No matching overload | Fix the parameter type, interface, or API |
| `this = other;` | `this` is not a reassignable variable | Assign to a field or a regular variable |
| `this(...)` placed after another statement in a Java 17 constructor | Violates constructor invocation placement rules | Place `this(...)` as the first statement |
| `return this;` when expecting a new object | `this` is the same receiver | Use `new`/a copy factory if a copy is desired |
| `Base fluent() { return this; }` followed by `sub.fluent().special()` | Static type of the result is `Base` | Use a covariant return or an appropriate self-type API |
| Passing `this` from a constructor to a listener | Risk of publishing an incomplete object | Register after initialization or design a factory |
| Calling a fluent method on a shared object | A mutating API changes the object for all aliases | Use copy/immutable style if independent state is required |
| Passing `this` to code that holds long-lived references | The object may be kept alive longer than intended | Manage lifecycle/callbacks and unregister |

Interpret `javac` errors by **context**: is `this` in a static or instance context? Does the argument have a compatible type? What is the method's return type? For method chaining, inspect the **declared return type**, not just the object's actual runtime class.

## 17. Practice Exercises with Answers

### Exercise 1 — Object Identity After `return this`

```java
class Box {
    int value;

    Box add(int amount) {
        value += amount;
        return this;
    }
}
```

Given:

```java
Box box = new Box();
Box result = box.add(3).add(5);
System.out.println(result == box);
System.out.println(box.value);
```

**Answer:**

```text
true
8
```

Both `add` calls operate on **the same `Box` instance**; `return this` preserves identity.

### Exercise 2 — Does Passing `this` Change the Caller's Variable?

```java
class Sender {
    int count = 1;

    void submit(Receiver receiver) {
        receiver.accept(this);
    }
}

class Receiver {
    void accept(Sender sender) {
        sender.count = 4;
        sender = new Sender();
        sender.count = 9;
    }
}
```

Inside a method:

```java
Sender original = new Sender();
original.submit(new Receiver());
System.out.println(original.count);
```

**Answer:** prints `4`. The `sender` parameter initially refers to the same `original` object, so assigning `count = 4` takes effect. Reassigning `sender = new Sender()` only changes the parameter variable and does not switch `original` to the new object.

### Exercise 3 — Can `return this` Be Used in a Static Method?

```java
class Item {
    static Item self() {
        // return this;
        return new Item();
    }
}
```

**Answer:** no. `static Item self()` has no `this` object; the uncommented line in the example uses `new Item()`, which returns a new object rather than returning a current object of the static method.

### Exercise 4 — Distinguishing `this(...)` and `return this`

```java
class Node {
    int value;

    Node() {
        this(10);
    }

    Node(int value) {
        this.value = value;
    }

    Node increment() {
        value++;
        return this;
    }
}
```

**Answer:**

- `this(10);` inside the `Node()` constructor calls **the `Node(int)` constructor** of the same class.
- `this.value = value;` assigns the field.
- `return this;` in `increment()` returns **the current `Node` object itself**.
- `new Node().increment()` creates a `Node` initialized with `10`, increments it to `11`, and returns a reference to that same object.

### Exercise 5 — Mutable or Immutable?

```java
class Config {
    String value;

    Config withValue(String newValue) {
        this.value = newValue;
        return this;
    }
}
```

**Answer:** this method is **mutable**, despite its `withValue` name. It modifies the `value` field on the object itself before executing `return this`. If you want an immutable API, you need to create and return a new object while designing it to avoid mutating the old object.

### Exercise 6 — Static Type After a Fluent Method

```java
class Parent {
    Parent chain() {
        return this;
    }
}

class Child extends Parent {
    void childOnly() {
    }
}
```

Given `Child child = new Child();`:

- `child.chain();` → valid.
- `Parent p = child.chain();` → valid.
- `child.chain().childOnly();` → **compile error** because `chain()` is declared to return type `Parent`.

To continue chaining with the subclass API, you can override `chain` in `Child` with return type `Child` if the overriding rules allow it.

## 18. API Design Checklist for Passing/Returning `this`

1. **Verify the instance context.** `this` is only usable when a current object exists; it cannot be used directly in a static method.
2. **Check types at compile time.** `receiver.process(this)` requires a parameter or overload compatible with the type of `this`.
3. **Distinguish between the reference value and the object.** Passing `this` copies the reference value; it does not clone the object and does not allow the receiver to reassign the caller's `this`.
4. **Check access control.** Passing a reference does not expose private fields publicly; the receiver's API remains governed by access modifiers.
5. **Consider the purpose of passing.** If the receiver only needs a string or an ID, consider passing just the needed data instead of the entire object.
6. **Avoid this escape.** Avoid passing `this` to a registry, thread, callback, or listener inside a constructor before the object is fully initialized.
7. **Determine the return type when using `return this`.** It must be compatible with the current type; `void` and primitive types cannot receive this reference.
8. **Distinguish between mutable and immutable fluent APIs.** `return this` generally preserves the same instance; `return new ...` generally creates a new version.
9. **Verify chaining under inheritance.** The static type of the result is determined by the method declaration; use a covariant return or self-type when required by a subclass API.
10. **Manage aliases.** Multiple variables receiving `return this` share the same object; updates from one place can affect the others.
11. **Consider multithreading.** `return this` does not provide thread safety. Shared mutable state requires synchronization mechanisms or an appropriate data design.
12. **Distinguish the forms of `this`.** `this.field`, `this.method()`, `this(...)`, `Outer.this`, and `return this` are distinct syntactic forms with their own roles.

## Key Takeaways

- **`this` is a reference to the current object**, which can be used as an argument expression or return value in an instance context.
- **`other.process(this)` passes the reference value** to the object; Java is always **pass-by-value**, so reassigning the parameter variable does not change the caller's variable.
- **`return this;` returns the currently executing object itself**, without creating a new object or making a copy, so it is commonly used for fluent APIs like `builder.step1().step2()`.
- **Method chaining does not imply immutability.** If the steps mutate fields and then execute `return this`, multiple reference variables can observe the same changes.
- **The static return type still matters** under inheritance: returning the same runtime object does not automatically unlock methods declared only on a subtype.
- **`this(...)` is constructor chaining**, completely different from passing `this` as an argument or returning `this`.
- **Avoid publishing `this` from a constructor prematurely** and control reference sharing with callbacks or other components.
