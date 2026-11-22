# Named Factory Methods and Comparison with Constructors in Java

## Learning Objectives

After this lesson, you will be able to:

- Distinguish between a **constructor** and a **named factory method**, which is commonly implemented as a `static` method.
- Explain why `new ClassName(...)` and `ClassName.of(...)` can both create or provide objects while having different **syntax, access control, return types, and contracts**.
- Design readable APIs using names such as `of`, `from`, `valueOf`, `getInstance`, `newInstance`, `create`, `getDefault`, or names reflecting the domain.
- Choose between a constructor and a factory when you need to **express parameter meaning**, **validate data**, **cache/reuse instances**, **hide implementation classes**, or **return a subtype/interface**.
- Understand the limitations: a factory method **is not a constructor**; a `static` method cannot be overridden via dynamic dispatch; a factory does not automatically guarantee singleton behavior, thread safety, or object immutability.
- Recognize relationships with constructor chaining, access modifiers, `final` fields, exceptions, and method reference names in Java 17+.
- Compile and run a complete Java example while avoiding common pitfalls when designing factories.

## 1. Two Ways to Provide Objects

In Java, the most direct way to create an object is to invoke a **constructor** using the `new` operator:

~~~java
Book book = new Book("Java Core", 180);
~~~

This is an **illustrative snippet** placed inside a method where the `Book` class and its corresponding constructor exist.

Another approach is to define a **method with a name that describes the purpose of object creation**:

~~~java
Book book = Book.of("Java Core", 180);
~~~

`of` here is a method declared by the `Book` class, not special syntax or a Java keyword. A static factory typically accepts arguments, performs validation or selects how to provide an instance, and then **returns an object reference**.

Conceptual example:

~~~java
public final class Book {
    private final String title;
    private final int pages;

    private Book(String title, int pages) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("title is required");
        }
        if (pages <= 0) {
            throw new IllegalArgumentException("pages must be positive");
        }
        this.title = title;
        this.pages = pages;
    }

    public static Book of(String title, int pages) {
        return new Book(title, pages);
    }

    public String title() {
        return title;
    }

    public int pages() {
        return pages;
    }
}
~~~

Saving the class above in `Book.java` will compile. `Book.of(...)` is a **static method** with return type `Book`; the `Book(...)` constructor is **private**, so code outside the class cannot directly write `new Book(...)`. The factory is allowed to call the private constructor because it resides inside the class itself.

Key point: **A factory does not replace a constructor in the sense of eliminating the object initialization process altogether**. In the example, the factory still uses `new Book(...)` internally; it serves as the **public API that controls how objects are provided**.

## 2. Constructors and Named Factory Methods: An Exact Comparison

| Criterion | Constructor | Named static factory method |
| --- | --- | --- |
| Typical call syntax | `new Book("Java", 180)` | `Book.of("Java", 180)` |
| Declared name | Must **match the class name** | Any valid method name; should be chosen meaningfully |
| Return type in declaration | **None**, not even `void` | **Has** a return type, e.g., `Book`, `Shape`, `Optional<T>` |
| How the result is returned | The `new` expression returns a reference if initialization succeeds | The method uses `return` according to its declared return type |
| Must a new instance be created? | Each use of `new` denotes a new object per Java semantics | **No**: may return a new instance, a cached instance, a singleton, a subtype, or another value per the contract |
| Can it return a subtype/hidden implementation? | `new Book(...)` creates an object of the specified class (under that instantiation mechanism) | **Can** declare an interface/base class as the return type and return a suitable implementation |
| Argument validation | Yes | Yes |
| Rename by parameter meaning | No; constructors share the class name | Yes: `ofSeconds`, `ofMillis`, `fromText`… |
| Overloading | Yes, by parameter type list | Yes; additionally, different method names can be used |
| Access | Constructors have access modifiers; not inherited | Static methods have access modifiers and their own static member rules |
| `this(...)`/`super(...)` | Can be used inside a constructor per Java rules | **No**: cannot invoke a constructor using `this(...)`/`super(...)` syntax inside a method body |
| Calling `new ClassName()` externally | Requires a matching, accessible constructor | Can be **disallowed** if the constructor is private |
| Guarantees thread safety? | Not automatically guaranteed | Not automatically guaranteed |

A factory method **does not necessarily have to be `static`** in all software design patterns. However, when referring to a **named static factory** replacing a constructor API in Java, common examples include `Book.of(...)`, `LocalDate.of(...)`, and `List.of(...)`. This differs from the GoF **Factory Method pattern**, where a product-creation method can be defined for subclasses to override; this distinction will be covered in the final section.

### 2.1. Do Not Confuse the Word `factory` with a Java Keyword

Java has no `factory` keyword. Names like `of`, `from`, `valueOf`, and `create` are merely **API conventions**. A method named `of` only “creates an object” if its implementation and contract actually do so. You cannot infer from the name alone that a method always creates a new instance or always uses a cache.

Example:

~~~java
Book first = Book.of("Java", 180);
Book second = Book.of("Java", 180);
~~~

With the `Book.of` implementation in Section 1, `first` and `second` are **two distinct instances**, because the factory calls `new Book(...)` each time. Another factory might maintain a cache and return the same instance.

## 3. Benefit 1 — Factory Names Express Meaning and Units

Constructors are constrained to the class name. When two ways of creating an object take **the same argument types**, constructor overloading cannot distinguish their meaning solely by parameter names.

For example, lengths in meters and millimeters:

~~~java
// Cannot have two constructors with the same signature at the same time:
// Length(long meters) { ... }
// Length(long millimeters) { ... }
~~~

Even though the parameter names differ, both constructors have the signature `Length(long)`; they **cannot coexist in the same class**. If you keep only a single `Length(long)` constructor, API callers must remember the unit of the number.

Named methods solve this directly:

~~~java
Length a = Length.ofMeters(2);
Length b = Length.ofMillimeters(2);
~~~

The two method names describe **two interpretations of the argument** even though both have type `long`. This helps reduce unit-confusion bugs (length, time, temperature, mass, bytes/KB…).

Built-in APIs in Java also reflect this principle:

- `java.time.Duration.ofSeconds(30)`: unit is seconds.
- `java.time.Duration.ofMillis(500)`: unit is milliseconds.
- `java.time.LocalDate.of(2026, 10, 18)`: day, month, and year per the API contract.
- `java.util.List.of("A", "B")`: creates/provides an **unmodifiable** list per its contract.
- `java.util.Optional.of(value)` and `Optional.ofNullable(value)`: differ in **how null is handled**.

**However:** these names are APIs of specific classes in the Java Standard Library; they do not share the same caching, validation, or null-handling policies. Read the contract of each method rather than guessing from naming patterns.

## 4. Benefit 2 — Ability to Reuse Instances Without Requiring `new`

A constructor used with `new` carries the semantics of creating a new object. A static factory can decide to:

- Always create a new object.
- Return an **existing** object if the contract allows it.
- Return a **singleton** or one of a fixed set of instances.
- Return an object from an intentionally managed **cache/pool**.

Example of a factory returning a shared default configuration object:

~~~java
final class Settings {
    private static final Settings DEFAULT = new Settings("localhost", 8080);

    private final String host;
    private final int port;

    private Settings(String host, int port) {
        this.host = host;
        this.port = port;
    }

    static Settings defaultSettings() {
        return DEFAULT;
    }

    static Settings of(String host, int port) {
        return new Settings(host, port);
    }
}
~~~

This is a valid class declaration when placed in an appropriate Java file, without a `main` method yet. `Settings.defaultSettings()` returns the same `DEFAULT` reference across typical calls. `Settings.of(...)`, on the other hand, calls `new`, so it returns a new instance every time.

**Conditions for safe sharing:** in the example, both fields `host` and `port` are `final`, and `String` is immutable; the `Settings` object has no public state-mutating operations. If a factory returns a shared **mutable object**, callers can affect one another. Do not apply caching out of habit without requirements regarding identity, memory, concurrency, and lifecycle.

Do not assume that `newInstance` always returns a new object or that `getInstance` always returns a single unique object without a specific contract. **Names are design hints, not automatic runtime guarantees.**

### 4.1. Distinguishing Identity and Equality

Given two reference variables:

~~~java
Settings a = Settings.defaultSettings();
Settings b = Settings.defaultSettings();
// a == b can be true because the factory returns the same instance.
~~~

The `==` operator between two references checks whether they have **the same object identity**. `equals` depends on the class's implementation; you must not deduce that `==` has to be true simply because field values are the same. When a factory has the freedom to reuse instances, callers should not make assumptions about object identity unless explicitly stated by the API.

An API returning immutable values typically encourages using **value-based comparison**, rather than using `==` as a contract for all results.

## 5. Benefit 3 — Returning an Interface or Subtype Instead of Exposing the Implementation Class

A constructor explicitly indicates the concrete class on the `new` side. A factory can declare a **more abstract** return type, such as an interface, and select the implementing class internally.

Conceptual example:

~~~java
interface Message {
    String render();

    static Message text(String content) {
        return new TextMessage(content);
    }
}

final class TextMessage implements Message {
    private final String content;

    TextMessage(String content) {
        this.content = java.util.Objects.requireNonNull(content);
    }

    @Override
    public String render() {
        return content;
    }
}
~~~

This is valid code in an appropriate file when the types are non-`public` at the top level. A caller can write `Message message = Message.text("Hello");` and depend only on **interface `Message`**, rather than needing to know the implementation name `TextMessage`.

The factory can change the implementation later (for example, specialized message forms, caching, or an optimized implementation) **as long as it preserves the published public contract**. Changing the implementation does not mean every change is automatically compatible: semantics, equality, serialization, and performance can still be affected.

**Note:** Interface `static` methods are **not inherited** like instance methods; invoke them using the interface name, such as `Message.text(...)`. There is also no dynamic dispatch to override a static factory on an object. Polymorphism here is realized through **the `Message` return type and the instance methods of the resulting object**.

## 6. Complete Java 17+ Example: Hidden Constructors and Named Factories

Save the following program as **`NamedFactoryDemo.java`**. This program compiles standalone with JDK 17 or later.

~~~java
public class NamedFactoryDemo {
    static final class Length {
        private final long millimeters;

        private Length(long millimeters) {
            if (millimeters < 0) {
                throw new IllegalArgumentException("length must be nonnegative");
            }
            this.millimeters = millimeters;
        }

        static Length ofMillimeters(long value) {
            return new Length(value);
        }

        static Length ofMeters(long meters) {
            return new Length(Math.multiplyExact(meters, 1000));
        }

        long millimeters() {
            return millimeters;
        }
    }

    static final class Settings {
        private static final Settings DEFAULT =
                new Settings("localhost", 8080);

        private final String host;
        private final int port;

        private Settings(String host, int port) {
            if (host == null || host.isBlank()) {
                throw new IllegalArgumentException("host is required");
            }
            if (port < 1 || port > 65535) {
                throw new IllegalArgumentException("invalid port");
            }
            this.host = host;
            this.port = port;
        }

        static Settings defaultSettings() {
            return DEFAULT;
        }

        static Settings of(String host, int port) {
            return new Settings(host, port);
        }

        String describe() {
            return host + ":" + port;
        }
    }

    interface Greeting {
        String text();

        static Greeting forName(String name) {
            return new PersonalGreeting(name);
        }
    }

    static final class PersonalGreeting implements Greeting {
        private final String name;

        private PersonalGreeting(String name) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("name is required");
            }
            this.name = name;
        }

        @Override
        public String text() {
            return "Hello, " + name;
        }
    }

    public static void main(String[] args) {
        Length meters = Length.ofMeters(2);
        Length millis = Length.ofMillimeters(250);
        System.out.println("lengths=" + meters.millimeters()
                + "," + millis.millimeters());

        Settings default1 = Settings.defaultSettings();
        Settings default2 = Settings.defaultSettings();
        Settings custom = Settings.of("db.internal", 5432);

        System.out.println("same default=" + (default1 == default2));
        System.out.println("default=" + default1.describe());
        System.out.println("custom=" + custom.describe());

        Greeting greeting = Greeting.forName("Lan");
        System.out.println("greeting=" + greeting.text());

        try {
            Length.ofMillimeters(-1);
        } catch (IllegalArgumentException expected) {
            System.out.println("invalid length rejected");
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 NamedFactoryDemo.java
java NamedFactoryDemo
~~~

**Stdout output:**

~~~text
lengths=2000,250
same default=true
default=localhost:8080
custom=db.internal:5432
greeting=Hello, Lan
invalid length rejected
~~~

Analysis:

1. `Length.ofMeters(2)` and `Length.ofMillimeters(250)` both return `Length`, but the factory names describe **the unit of the parameter**. `Math.multiplyExact(2, 1000)` equals `2000`.
2. The `Length(long)` constructor is declared `private`, preventing code outside the class from directly specifying millimeters without going through the defined factories. Validation disallows negative lengths.
3. `Settings.defaultSettings()` returns the static final reference `DEFAULT`; the two calls create two **reference variables** pointing to the same object, so `default1 == default2` is `true`.
4. `Settings.of("db.internal", 5432)` returns a **new settings object**. Both creation paths go through the private constructor to validate host/port.
5. `Greeting.forName("Lan")` declares the return type as **interface `Greeting`** yet returns a `PersonalGreeting` instance, so the caller does not need to depend on the implementation class name.
6. When `Length.ofMillimeters(-1)` is called, the private constructor throws `IllegalArgumentException`; the factory does not swallow the error, so the `catch` block prints the final line.

The nested types are used only to put everything into **a single standalone runnable file**. In large projects, you typically place separate API types in appropriate files/packages.

**Numeric boundary warning:** `Math.multiplyExact` can throw `ArithmeticException` if the multiplication exceeds the `long` range. This is intentionally better than silently overflowing into a wrong number. If a unit-conversion API needs consistent error reporting, you can handle the overflow by turning it into a business/domain exception according to your contract.

## 7. Constructors Still Play an Important Role When Using Factories

Named factories **do not eliminate constructors during new instance creation**. Typically, the flow is:

~~~text
Caller
  |
  |  Money.ofCents(150)
  v
static factory ofCents(long)
  |
  | validate, convert units, decide cache/new
  v
private constructor Money(long)
  |
  | initialize final fields
  v
Money object returned to caller
~~~

When you write `new Money(150)` in the caller, the caller goes **directly through a public constructor** if the class provides one. When you write `Money.ofCents(150)`, the caller goes through a **method**, which can choose to create a new instance or return another instance.

### 7.1. Centralizing Invariants in the Constructor

A useful design is having every factory **delegate to the same private constructor**, which validates the essential invariants:

~~~java
final class Money {
    private final long cents;

    private Money(long cents) {
        if (cents < 0) {
            throw new IllegalArgumentException("negative money");
        }
        this.cents = cents;
    }

    static Money ofCents(long cents) {
        return new Money(cents);
    }

    static Money ofWholeUnits(long wholeUnits) {
        return new Money(Math.multiplyExact(wholeUnits, 100));
    }
}
~~~

This class is a standalone compilable snippet without a `main` method yet. The two factories express different units, but both go through the constructor that checks `cents >= 0`.

For data such as currency, modeling with `long` in the smallest unit is only **one strategy when appropriate unit/magnitude rules are defined**; many systems require `BigDecimal`, currency codes, scale, rounding, and other invariants.

### 7.2. Constructor Chaining Differs from a Factory Calling a Constructor

Inside a constructor, Java allows `this(...)` to **delegate to another constructor of the same class** and `super(...)` to select a superclass constructor:

~~~java
class Point {
    final int x;
    final int y;

    Point() {
        this(0, 0);
    }

    Point(int x, int y) {
        this.x = x;
        this.y = y;
    }

    static Point origin() {
        return new Point();
    }
}
~~~

This is a valid class declaration. `Point()` delegates using `this(0,0)`; `origin()` is a **static factory**—it cannot call `this(0,0)` itself because it is not a constructor. It uses `new Point()` to create the object. This distinction helps you read code accurately when encountering calls that look similar.

## 8. Public or Private Constructors: Deciding API Boundaries

There are two common API designs:

**Design A — public constructor:**

~~~java
public class Customer {
    private final String id;

    public Customer(String id) {
        this.id = java.util.Objects.requireNonNull(id);
    }

    public String id() {
        return id;
    }
}
~~~

Callers can write `new Customer("C01")`. This class has a single, direct creation path that is easy to discover in an IDE, making it suitable when object creation is simple and each `new` should produce a new instance.

**Design B — private constructor + public named factory:**

~~~java
public final class Customer {
    private final String id;

    private Customer(String id) {
        this.id = java.util.Objects.requireNonNull(id);
    }

    public static Customer fromId(String id) {
        return new Customer(id);
    }

    public String id() {
        return id;
    }
}
~~~

Callers must write `Customer.fromId("C01")`. The API designer can add clearly named factories by data source without opening a public constructor.

The two snippets above are **two alternative versions** of the `Customer` class and should not be declared simultaneously in the same source set. If you use a public class, save the chosen version in `Customer.java`.

**However:** a factory does not have to be paired with a private constructor; a class can provide both public constructors and static factories. The decision depends on API compatibility requirements, extensibility, and the level of initialization control.

### 8.1. You Cannot Force External Callers to Forgo Every Object Creation Mechanism

A private constructor restricts direct `new` calls according to Java access rules. It is **not an absolute security mechanism**, and it does not guarantee that all deserialization, authorized reflection, frameworks, cloning, or other runtime mechanisms are eliminated. When using Java modules, reflection also depends on access/module configuration. Use private constructors for **API design and encapsulation**, not to claim a general security boundary.

## 9. How to Choose Factory Names to Make Intent Clear

The common names below are **conventions**, not keywords or mandatory compiler rules:

| Suggested name | Common interpretation | Example |
| --- | --- | --- |
| `of(...)` | Create/provide a value from explicit components | `LocalDate.of(2026, 10, 18)` |
| `from(...)` | Convert from another representation/object | `MyValue.from(raw)` |
| `valueOf(...)` | Create/convert into a value according to the API | `Integer.valueOf("12")` |
| `parse(...)` / `parseX(...)` | Parse text into a value | `LocalDate.parse("2026-10-18")` |
| `getInstance(...)` | Obtain an instance, possibly cached/shared | `SomeService.getInstance()` |
| `newInstance(...)` | Suggests a new instance, if the contract truly guarantees it | `Session.newInstance(...)` |
| `create(...)` | Create/provide an object through an intentional initialization step | `Report.create(...)` |
| `getDefault()` / `defaultX()` | Return a clearly meaningful default value | `Settings.defaultSettings()` |
| `ofSeconds`, `ofMillis` | State the unit/source of the value directly | `Duration.ofSeconds(5)` |

Do not overuse overly generic names like `make()` if readers cannot tell how the object is created. Nor should you name a method `getInstance()` to implicitly promise a singleton if the actual implementation creates a new instance every time and the API has no such contract.

**Distinguishing `of` and `from`:** a common convention is `of` for creating a value from components and `from` for converting from a representation with the same meaning; however, many libraries use them differently. Consistency **within the same API** is more important than rigidly sticking to a single word.

## 10. Null Checks, Input, and Exceptions Across Both Creation Approaches

Both constructors and factories can validate parameters. The main difference is that a factory can provide **multiple named entry points** for different policies.

Standard library examples:

- `Optional.of(value)` does not accept `null`.
- `Optional.ofNullable(value)` allows `null`, returning an empty optional when the value is null.
- `List.of(...)` disallows `null` elements and produces an unmodifiable result.
- `List.copyOf(collection)` creates/provides an unmodifiable list from a collection while also disallowing null elements per its contract.

This allows factory names to **express input and output policies**, rather than forcing callers to memorize overloaded constructors with the same name. Nevertheless, the actual policy must still be documented and tested.

### 10.1. Can a Factory Return `null`?

At the language level, a static method with a reference return type **can return `null`**. However, if the intent is an object-creation API, returning `null` unexpectedly often makes the API difficult for callers to use. You can:

- Throw an appropriate exception when data is invalid.
- Return a result of type `Optional<T>` if **not found** is a normal possibility and the API wants to represent it explicitly.
- Return a default/special value with a clear contract.
- Never return `null` when the contract specifies that an object is always present.

You should not conclude that “a factory must always return a non-null object”; that is an **API contract decision**, not a Java rule.

### 10.2. Returning a Subtype Must Still Uphold the Contract

A factory declaring return type `Shape` might return `Circle`, `Rectangle`, or a private implementation. However, callers should rely only on **the `Shape` contract** (unless checking/casting for a valid reason). If the factory changes the subtype in a new version, calling code that depends on the concrete class, object identity, or implementation details may break.

## 11. Costs and Limitations of Static Factories

Static factories offer many benefits, but they are not a better choice than constructors in every situation.

### 11.1. Harder to Discover in Some APIs

Constructors stand out in IDEs and API documentation when users search for `new ClassName(...)`. A static factory is just an ordinary method; if its name is vague, learners may not find how to create an object.

**Solution:** use consistent naming, document usage, provide an initial object-creation example, and write clear Javadoc.

### 11.2. Can Restrict Inheritance

If a class has only **private constructors**, an external class cannot subclass it via `super(...)`, which requires access to a superclass constructor. This may be **intentional** if the type is immutable/final, but unsuitable if frameworks or users need inheritance.

This does not mean “a class with a static factory cannot be subclassed.” The issue is **whether a superclass constructor is accessible to the subclass**. A class with a static factory and a `protected` constructor can still support inheritance.

### 11.3. Static Factories Cannot Be Overridden Like Instance Methods

~~~java
class Base {
    static Base create() {
        return new Base();
    }
}

class Derived extends Base {
    static Derived create() {
        return new Derived();
    }
}
~~~

This is a valid class declaration snippet in Java 17; the `Derived.create()` method has the same signature and a compatible reference return type, so it **hides** `Base`'s static method rather than **dynamically overriding** it. Avoid relying on a runtime receiver expecting a static factory to be dispatched like an instance method.

If you need a creation mechanism that can be substituted polymorphically, consider an **instance factory interface**, a **supplier**, dependency injection, or an appropriate design pattern, rather than assuming a static method will be overridden.

### 11.4. Reusing Objects Is Not Always Good

A shared instance can reduce object creation overhead, but if it holds mutable state or lifecycle-bound resources such as a file handle or network connection, arbitrary caching easily causes shared errors, memory leaks, or concurrency bugs. A factory appropriate for its context sometimes must **always create a new instance** and clearly document the resource-closing method.

### 11.5. Adding an Indirection Layer Can Make Debugging Harder

If a factory contains validation, caching, subtype selection, and multiple logic branches, finding the root cause of an error can be harder than with a simple constructor. Keep factories small, have clear contracts, test every branch, and avoid hiding unnecessary side effects.

## 12. Standalone Runnable Example: Distinguishing Always-New vs. Reused Instances

Save as **`FactoryIdentityDemo.java`**:

~~~java
public class FactoryIdentityDemo {
    static final class Token {
        private static final Token SHARED = new Token("SHARED");
        private final String value;

        private Token(String value) {
            this.value = value;
        }

        static Token shared() {
            return SHARED;
        }

        static Token create(String value) {
            return new Token(value);
        }

        String value() {
            return value;
        }
    }

    public static void main(String[] args) {
        Token first = Token.shared();
        Token second = Token.shared();

        Token third = Token.create("SHARED");
        Token fourth = Token.create("SHARED");

        System.out.println("shared identity=" + (first == second));
        System.out.println("fresh identity=" + (third == fourth));
        System.out.println("same text=" + first.value().equals(third.value()));
    }
}
~~~

Compile/run:

~~~bash
javac FactoryIdentityDemo.java
java FactoryIdentityDemo
~~~

Output:

~~~text
shared identity=true
fresh identity=false
same text=true
~~~

Explanation: `shared()` always returns the static field `SHARED`; `create(...)` invokes `new Token(...)` each time. Two new tokens may contain the same string value yet not share the same identity. A factory **has the authority to decide the instantiation policy**, and its naming should communicate that policy clearly.

Here `Token` is immutable at the field level: the `value` field is final and `String` is immutable. Because of this, returning the shared `SHARED` instance creates no state-mutation issues for `Token` itself.

## 13. Integrated Example: Public Constructors and Named Factories Coexisting

There is no rule forcing a class to pick only one of the two approaches. For example, a coordinate class can have a public constructor and a factory for a commonly used value.

Save as **`ConstructorAndFactoryDemo.java`**:

~~~java
public class ConstructorAndFactoryDemo {
    public static final class Point {
        private final int x;
        private final int y;

        public Point(int x, int y) {
            this.x = x;
            this.y = y;
        }

        public static Point origin() {
            return new Point(0, 0);
        }

        public static Point of(int x, int y) {
            return new Point(x, y);
        }

        public String describe() {
            return "(" + x + "," + y + ")";
        }
    }

    public static void main(String[] args) {
        Point a = new Point(3, 4);
        Point b = Point.of(3, 4);
        Point center = Point.origin();

        System.out.println("constructor=" + a.describe());
        System.out.println("factory=" + b.describe());
        System.out.println("origin=" + center.describe());
        System.out.println("same instance=" + (a == b));
    }
}
~~~

Commands:

~~~bash
javac ConstructorAndFactoryDemo.java
java ConstructorAndFactoryDemo
~~~

Output:

~~~text
constructor=(3,4)
factory=(3,4)
origin=(0,0)
same instance=false
~~~

`new Point(3,4)` and `Point.of(3,4)` both represent the coordinate `(3,4)`, yet in this implementation the factory calls `new Point`, so each expression returns a **separate instance**. If business logic requires comparing coordinates **by value**, you should implement `equals`/`hashCode` consistently or use an appropriate value-oriented type (such as a record if design requirements permit). You should not replace value comparison with `==`.

**When should you keep both?** When the constructor is simple, easy to use, and unambiguous, while certain values benefit from expressive factory names (`origin`, `identity`, `zero`…). If the API needs tight control over creation paths, factories with a private constructor may be more appropriate.

## 14. Distinguishing Named Static Factories from Other Factory Patterns

The word “factory” is used in multiple contexts:

| Concept | Idea | Must it be `static`? |
| --- | --- | --- |
| **Named static factory method** | A named method on a class/type that provides an object, e.g., `Point.of(...)` | Usually **yes** |
| **Factory Method design pattern (GoF)** | Defines a product-creation method so implementations/subclasses can decide the product type | Not required; typically relies on instance polymorphism |
| **Abstract Factory design pattern** | A factory object that provides a **family of related products** | Not required; typically uses a factory interface |
| **Builder** | Assembles configuration parameters step by step and then calls `build()` for the final object | The builder is an object; the initial `builder()` method can be static |
| **Dependency Injection container** | A tool that configures and provides objects/dependencies according to scope and lifecycle | Framework-dependent |

Example of simple interfaces for an **instance factory** that can be substituted polymorphically:

~~~java
interface Greeter {
    String greet();
}

interface GreeterFactory {
    Greeter create(String name);
}
~~~

These are two valid interfaces without implementations yet. A concrete class can implement `GreeterFactory.create(...)`; callers hold a reference to `GreeterFactory` and can swap implementations at runtime. This mechanism **differs** from a `static Greeter of(String)` method, which is invoked only on the declaring type.

You do not need to learn the full set of design patterns to understand named factories. For this lesson, the focus is **choosing a clearly named object-creation API instead of relying solely on constructors**.

## 15. Constructor References and Factory Method References

In Java 8+, both constructors and static factories can be referenced as method references when the target functional type matches.

Example inside a method of a class where `Point` is available:

~~~java
java.util.function.BiFunction<Integer, Integer, Point> viaConstructor =
        Point::new;

java.util.function.BiFunction<Integer, Integer, Point> viaFactory =
        Point::of;
~~~

This is an **illustrative snippet** requiring the `Point` class to have an accessible `Point(int,int)` constructor and `static Point of(int,int)` method, as in the previous example. Both method references can be applied in a functional interface context; `Integer` in `BiFunction` can be unboxed to `int` when needed.

- `Point::new` is a **constructor reference**.
- `Point::of` is a **static method reference**.

Developers should choose the reference that accurately describes the contract. If a factory may cache or choose a subtype, `Point::of` reflects that policy; `Point::new` is tied to the specific constructor.

## 16. Common Pitfalls and How to Fix Them

| Misconception / mistake | Correct fact or how to handle it |
| --- | --- |
| “`of` is a constructor with a different name.” | `of` is a **method**, typically `static`, with a return type; a constructor must match the class name and has no return type. |
| “Factories never use `new`.” | Many factories still invoke a private/public constructor internally to create an object. |
| “Every factory returns a singleton.” | A factory may return a new object or a reused instance; check the implementation/contract. |
| “`create(...)` must create a new instance.” | The name is only a hint; to make it a commitment, define it in the API contract and stay consistent. |
| “The two constructors `Length(long meters)` and `Length(long mm)` have different signatures.” | No. Parameter names do not distinguish overloaded constructors. Use factories with unit names. |
| “Factory `private Constructor()` needs no constructor at all.” | When a factory creates a new instance, it must still use a valid initialization path; a private constructor is a common choice. |
| “A factory's return type must be the enclosing class itself.” | No. The method can return an interface/base type or a compatible subtype. |
| “Static factories are dynamically overridden based on the runtime object.” | No. Static methods do not use dynamic dispatch like instance methods. |
| “A private constructor absolutely prevents all forms of object creation.” | It is only a Java access rule with other runtime exceptions/contexts; it is not a general security mechanism. |
| “Reusing a shared mutable instance is always better.” | It can cause shared state and concurrency bugs; consider immutability and ownership. |
| “If there is a factory, subclassing is impossible.” | It depends on superclass constructor access and class design, not the presence of a factory. |
| “Factories automatically validate all inputs.” | It only validates when implemented that way; include real validation and error tests. |
| “`Point.of(3,4)` is always equal to `new Point(3,4)` via `==`.” | No; identity depends on the factory policy, and two `new` calls create separate instances. |
| “A factory method is the same as Builder/Abstract Factory.” | They are object-creation approaches with different goals and structures, not synonyms. |
| “Adding a factory is guaranteed to stay compatible with all existing APIs.” | If an existing public constructor is removed/hidden, callers may fail to recompile; compatibility must be considered. |

### 16.1. Why You Should Not Modify a Public API by Arbitrarily Turning a Constructor Private

Suppose an earlier version published `public Book(String title)`, and callers are using `new Book("Java")`. If a later version changes that constructor to `private` and keeps only `Book.of("Java")`, **existing source code cannot recompile** without modifying call sites. Changing a public API can also break binary compatibility for already compiled classes.

If you need to transition toward factories, consider **adding the factory first**, keeping the old constructor for a transition period, marking it deprecated when appropriate, and providing migration guidelines. Compatibility is an important part of Java library design.

## 17. Checklist for Choosing Between a Constructor and a Factory

When designing a data type, ask yourself:

1. **Does each creation genuinely require a new instance?** If not, a named factory preserves the option to reuse/cache, though you must document the identity semantics.
2. **Are there multiple ways to construct the object with the same parameter types but different meanings?** If so, names like `ofCelsius`, `ofFahrenheit`, `fromHex`, and `fromId` are clearer than constructors with identical signatures.
3. **Does the caller need to see the concrete implementation class?** If not, a factory returning an interface/base type helps with encapsulation.
4. **Are there invariants that must be checked across every creation path?** Centralize validation in a shared constructor/private method; the factory simply coordinates creation.
5. **Does the object have mutable state or closeable resources?** Do not cache/share arbitrarily; determine ownership, lifecycle, and thread safety.
6. **Do you require public subclassing?** Check constructor access and inheritability.
7. **Are factory names easy to discover in the API?** Documentation and examples should show how objects are actually created.
8. **Do you need to preserve backward compatibility with existing code?** Do not abruptly delete a public constructor when users are calling `new`.
9. **Are you adding a factory just to wrap a simple constructor?** If it adds no value in readability or creation policy, a public constructor may be simpler.

**Decision takeaway:** There is no rule saying “every constructor should be replaced by a static factory.” Constructors are appropriate when creation is simple, data is straightforward, and no subtype switching or caching is needed. Named static factories are especially valuable when **the creation method carries domain meaning worth naming or when you need control over the provided instance**.

## 18. Self-Check Questions

**Question 1.** Is `public static Book of(String title)` a constructor?  
**Answer:** No. It is a method named `of` with return type `Book` and the `static` modifier. A `Book` constructor must be named `Book` and declare no return type.

**Question 2.** Why cannot the two constructors `Temperature(double celsius)` and `Temperature(double fahrenheit)` coexist in the same class?  
**Answer:** They have the same signature `Temperature(double)`. Parameter names do not distinguish overloads; factories `ofCelsius(double)` and `ofFahrenheit(double)` convey different meanings.

**Question 3.** Is `Settings.defaultSettings()` required to create a new object every time?  
**Answer:** No. A factory can return the same cached instance if the contract allows it, as in the illustrative implementation.

**Question 4.** How do `new Settings()` and `Settings.of(...)` differ in terms of whether callers can invoke them?  
**Answer:** `new Settings()` requires an accessible no-arg constructor; `Settings.of(...)` requires the corresponding static method to be accessible. A class can publish only factories and hide its constructors.

**Question 5.** Can a factory declared as `static Shape create()` return a `Circle implements Shape`?  
**Answer:** Yes, if `Circle` is a `Shape`-compatible type, the class fulfills the contract, and the factory can create/provide that object.

**Question 6.** Does `private Book(...)` mean no method of the `Book` class can call this constructor?  
**Answer:** No. The `Book` class itself can invoke its private constructor inside its static factory, for example `return new Book(...);`.

**Question 7.** If both `Book.of(...)` and `new Book(...)` produce objects with the same field values, does `==` always return true?  
**Answer:** No. `==` compares identity; the result depends on the specific instance returned by the factory, not just field values.

**Question 8.** Is the static factory `Base.create()` dynamically overridden by a subclass like an instance method?  
**Answer:** No. Static methods are not overridden via dynamic dispatch; in class inheritance, static method hiding may occur according to Java rules.

**Question 9.** Why is `Optional.ofNullable(x)` a good example of a named factory?  
**Answer:** The method name clarifies the **null-handling policy**, distinct from `Optional.of(x)`, while providing an `Optional` object through a named API.

**Question 10.** What problem can arise if a factory returns a shared mutable `ArrayList`?  
**Answer:** A caller can modify the shared list and affect other callers; you must decide on ownership, defensive copying, an unmodifiable view, or separate instances depending on the contract.

**Question 11.** Are `Point::new` and `Point::of` both constructor references?  
**Answer:** No. `Point::new` is a constructor reference; `Point::of` is a method reference to a static factory.

**Question 12.** A class already has `public Book(String title)`; you change it to `private` and publish `Book.of(String)`. Will existing users have to modify their code?  
**Answer:** They may have to modify it, because `new Book(...)` is no longer accessible; this is an API change that requires evaluating compatibility and a migration path.

## Key Takeaways

A **constructor** shares the class name, has no return type, and is invoked via `new` or constructor chaining according to Java rules. A **named static factory method** is a **method with a name and a return type**, such as `Length.ofMeters(2)`, `Settings.defaultSettings()`, or `Message.text("Hi")`. A factory can invoke a private constructor to create a new instance, return a reused instance, convert data representations, or provide a subtype through an interface.

Choose a **constructor** when creation is simple and transparent; choose a **named factory** when you need meaningful names, validation across multiple entry points, control over reuse/identity, or hidden implementations. Either way, the API must still ensure that objects are used in a valid state, have a clear contract, and do not inadvertently share mutable state.
