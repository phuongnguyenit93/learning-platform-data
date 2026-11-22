# Classifying `abstract`, `default`, `static`, and `private` methods in a Java interface

## 1. Why does an interface have multiple method types?

In Java, an `interface` defines the contract that implementing classes (`implements`) must follow. Since Java 8, an interface can not only contain abstract methods, but also provide implementation code through `default` and `static` methods. Since Java 9, an interface can additionally declare `private` methods to reuse internal logic.

The four method groups should be distinguished by **whether they have a body**, **how they are called**, **access scope**, and **inheritance/overriding capability**.

| Method type | Typical syntax | Method body | Access scope | Usage |
|---|---|---|---|---|
| `abstract` | `void execute();` or `public abstract void execute();` | **None**, ends with `;` | Always `public` | An implementing class must provide an implementation if no suitable implementation is inherited and it is a concrete class. |
| `default` | `default void log() { ... }` | **Required** | Always `public` | Called on an object implementing the interface; implementing classes can override it. |
| `static` | `static boolean valid() { ... }` | **Required** | `public` by default; can be declared `private static` for internal use | Public methods are called via the **interface name**; not inherited like instance methods. |
| `private` (instance) | `private void helper() { ... }` | **Required** | Only within the interface itself | Supports shared code among instance methods with a body; not part of the external API. |
| `private static` | `private static String normalize(...) { ... }` | **Required** | Only within the interface itself | Internal helper method usable from both `static` and instance contexts of the interface. |

**Version milestones:** `abstract` has been part of the interface model from the beginning; `default` and `static` methods with bodies have been supported since **Java 8**; `private` and `private static` methods in interfaces have been supported since **Java 9**. All examples below use valid syntax in **Java 17+**.

## 2. `abstract` methods: contracts without an implementation

An interface method without a body is implicitly **`public abstract`**. For example, `boolean pay(long amount);` below is a public contract even without writing those two modifiers:

~~~java
interface PaymentMethod {
    boolean pay(long amount);
}

final class CardPayment implements PaymentMethod {
    @Override
    public boolean pay(long amount) {
        return amount > 0; // Illustrates a minimal validation rule
    }
}
~~~

This snippet illustrates a valid declaration and does not yet include `main`. A concrete class must satisfy any remaining abstract methods with a compatible implementation that has **`public`** access; an `abstract` class can defer this. An `abstract` method has no body and cannot be combined with `private`, `protected`, `final`, or `static`.

A public method already inherited from `Object`, such as `equals(Object)`, can satisfy a corresponding abstract declaration in an interface. To verify modifiers using reflection and distinguish them from class abstract methods, see the article **Implicitly public abstract methods**.
## 3. `default` methods: default implementations for objects

`default` allows an interface to declare an **instance method with a body**. An implementing class can use the provided behavior or override it if needed:

~~~java
interface Named {
    String name();

    default String displayName() {
        return "Tên: " + name();
    }
}

class User implements Named {
    @Override
    public String name() {
        return "Lan";
    }
}
~~~

Here `name()` is implicitly `public abstract`. `displayName()` is implicitly `public default` in terms of access scope; it calls `name()` and receives the implementation of the actual object. A `new User()` object can call `displayName()` even though the `User` class does not write this method itself.

Important rules:

1. A `default` method **must have a body**, be written with the `default` keyword, and have `public` access (implicit or explicit).
2. It is an **instance method**; calls are made through an object such as `user.displayName()`, can participate in polymorphism, and can be overridden by an implementing class.
3. When a class overrides a `default` method, that method must still be `public`. If a class directly implements the interface and wants to call the default version from the overriding method, it can use `InterfaceName.super.method()` under Java syntax conditions.
4. `default` cannot be combined with `abstract`, `static`, or `private` on the same method.
5. An interface cannot provide a `default` method that overrides `public` methods of `Object`, such as `default String toString() { ... }`. An implementing class can still override `toString()` itself as usual.

One use case is **adding default behavior when evolving an interface API** without forcing all existing classes to immediately declare the new method. However, adding a `default` method can still create conflicts with other interfaces that a class implements; it is not a compatibility guarantee in every case.

## 4. `static` methods: utilities tied to the interface itself

A `static` method has a body and **does not depend on an implementing object**:

~~~java
interface TextRules {
    static boolean hasText(String input) {
        return input != null && !input.isBlank();
    }
}
~~~

Correct call:

~~~java
boolean result = TextRules.hasText("Java");
~~~

`result` has the value `true`. For a public `static` method in an interface, the interface name is the clear access point. If you have a variable of type `TextRules`, calling `variable.hasText(...)` is invalid; a class that `implements TextRules` also **does not inherit** the `hasText` method to call it as a static method of that class itself. Similarly, a subinterface does not inherit static methods from a superinterface the way instance methods are inherited.

An interface `static` method:

- Can directly call other static methods in the interface, including `private static`.
- Cannot directly call `default` instance methods or `private` instance methods without an appropriate object.
- Cannot be overridden in the polymorphic sense of instance methods; having the same name as another static method does not turn that method into `default` or `abstract`.
- When no access modifier is written, it is `public static`; to restrict it to internal use only, write **`private static`** (Java 9+).

Use `static` when a function is closely related to the interface contract, such as object creation operations, argument validation, or conversions independent of instance state.

## 5. `private` and `private static` methods: internal helper code

Java 9 allows interfaces to hide methods with bodies, avoiding duplicated logic across multiple `default`/`static` methods:

~~~java
interface Formatter {
    default String emphasize(String text) {
        return wrap(text);
    }

    default String label(String text) {
        return "Nhãn " + wrap(text);
    }

    static String normalize(String text) {
        return trim(text).toLowerCase(java.util.Locale.ROOT);
    }

    private String wrap(String text) {
        return "[" + trim(text) + "]";
    }

    private static String trim(String text) {
        return text.trim();
    }
}
~~~

Distinguishing the two forms:

- `private String wrap(String text)` is an **instance method**. It can only be called from code within the interface with an appropriate instance context; for example, both `emphasize` and `label` can call it.
- `private static String trim(String text)` is a **static method**. Both the instance method `wrap` and the static method `normalize` can call it.
- `private` and `private static` methods **must have a body** and cannot simultaneously be `abstract` or `default`; they are not API members that can be called from an implementing class.
- An implementing class **does not inherit** and cannot override an interface's `private` method. Writing a method with the same name in the implementing class creates a different method, not an override.
- Interface `private` methods do not increase the number of abstract methods that must be implemented, and do not participate in the implementation contract of `implements`.

If there is only a single helper snippet and no need to hide implementation details, writing the logic directly inside `default`/`static` is sometimes simpler. Use `private` when naming a processing step or reusing logic genuinely makes the code easier to understand.

## 6. Complete combined example: all four method types

In the following example, `Notifier` has `abstract`, `default`, `static`, `private` instance, and `private static` methods. One class uses the default version, and one class explicitly overrides the default version.

Save the **entire** code into the file **`Demo.java`**:

~~~java
import java.util.Locale;

interface Notifier {
    // Implicitly public abstract.
    String recipient();

    // Implicitly public; has a body and is an instance method.
    default String message() {
        return decorate(recipient());
    }

    // Implicitly public; called via Notifier.supports(...).
    static boolean supports(String languageCode) {
        return normalize(languageCode).equals("vi");
    }

    // Java 9+: used only within the interface itself.
    private String decorate(String rawName) {
        return "Xin chào " + rawName.trim() + "!";
    }

    // Java 9+: helper usable from static and instance methods.
    private static String normalize(String code) {
        return code.trim().toLowerCase(Locale.ROOT);
    }
}

final class StandardNotifier implements Notifier {
    private final String name;

    StandardNotifier(String name) {
        this.name = name;
    }

    @Override
    public String recipient() {
        return name;
    }
}

final class CustomNotifier implements Notifier {
    @Override
    public String recipient() {
        return "Mai";
    }

    @Override
    public String message() {
        return "Thông báo dành cho " + recipient();
    }
}

public class Demo {
    public static void main(String[] args) {
        Notifier standard = new StandardNotifier(" Lan ");
        Notifier custom = new CustomNotifier();

        System.out.println(standard.recipient().trim());
        System.out.println(standard.message());
        System.out.println(custom.message());
        System.out.println(Notifier.supports(" VI "));
    }
}
~~~

Compile/run with Java 17+:

~~~bash
javac Demo.java
java Demo
~~~

**Exact stdout output:**

~~~text
Lan
Xin chào Lan!
Thông báo dành cho Mai
true
~~~

Call flow analysis:

1. `standard.recipient()` calls `StandardNotifier`'s implementation of the **abstract contract**; `trim()` in the print statement removes leading/trailing whitespace, so it prints `Lan`.
2. `standard.message()` uses the **default** method from `Notifier`. Inside `message()`, it calls the **private instance** method `decorate(...)`; that method gets `recipient()` of the actual object and removes whitespace.
3. `custom.message()` calls `CustomNotifier`'s **override**, so it does not use the default `message()` body.
4. `Notifier.supports(" VI ")` calls the **public static** method via the interface name. It calls the **private static** `normalize(...)`: strips whitespace, converts to lowercase using `Locale.ROOT`, and then compares against `"vi"`, returning `true`.

The following calls are **invalid** outside `Notifier` (error illustrations, do not include in `Demo.java`):

~~~java
// standard.supports("vi");        // Error: static method cannot be called on an instance
// StandardNotifier.supports("vi"); // Error: interface static method is not inherited by the class
// standard.decorate("Lan");       // Error: private interface method is not accessible
// Notifier.normalize("vi");       // Error: private static method is not accessible
~~~

## 7. Inheritance, overriding, and `default` method conflicts

When multiple interfaces have methods with the same signature, understanding the implementation selection rules is very important:

1. **A concrete instance method from a superclass takes precedence** over the corresponding `default` implementation of an interface, if the signature and return type are compatible.
2. In an interface hierarchy with inheritance relationships, a `default` implementation from a **more specific** interface generally takes precedence over a `default` in a superinterface according to Java rules.
3. If a class receives **two unrelated `default` implementations** with the same signature from two interfaces, it must resolve the conflict by explicitly overriding it.
4. An `abstract` method still defines the contract; a matching `default` can satisfy that contract in valid inheritance structures.
5. Interface `static` and interface `private` methods are not subject to polymorphic `default` overriding.

Example of a `default` conflict, saved separately in **`ConflictDemo.java`**:

~~~java
interface Left {
    default String label() {
        return "L";
    }
}

interface Right {
    default String label() {
        return "R";
    }
}

final class Combined implements Left, Right {
    @Override
    public String label() {
        return Left.super.label() + "+" + Right.super.label();
    }
}

public class ConflictDemo {
    public static void main(String[] args) {
        System.out.println(new Combined().label());
    }
}
~~~

Run:

~~~bash
javac ConflictDemo.java
java ConflictDemo
~~~

Stdout:

~~~text
L+R
~~~

If `Combined.label()` is removed, the code will not compile because the class receives two `default` methods with the same signature without specifying how to resolve it. The syntax `Left.super.label()` and `Right.super.label()` allows calling specific default implementations in a valid inheritance context. You can also write a completely new override without calling either default version.

**Note:** only a concrete method from a superclass suffices to resolve precedence under the usual "class wins" rule. If the superclass leaves an abstract method with the same signature or the signatures/return types are incompatible, an explicit implementation and error handling according to Java rules may still be required; do not infer that any declaration in a class automatically resolves every conflict.

## 8. Common mistakes when classifying methods in an interface

| Incorrect code or misconception | Cause | Fix |
|---|---|---|
| `interface A { void run() {} }` | A method lacking a modifier that allows a body is interpreted as abstract. | Write `void run();` or `default void run() {}`. |
| `interface A { default void run(); }` | `default` must have a body. | Add `{ ... }` or declare it abstract. |
| `interface A { private void helper(); }` | Interface `private` methods must have a body. | Write `private void helper() { ... }`. |
| `interface A { static void work(); }` | Interface `static` methods must have a body. | Write `static void work() { ... }`. |
| `new Notifier()` | An interface cannot be instantiated directly. | Instantiate an implementing class, for example `new StandardNotifier("Lan")`. |
| `StandardNotifier.supports("vi")` | Interface `static` methods are not inherited by classes. | Call `Notifier.supports("vi")`. |
| Two unrelated interfaces have the same `default void f()` and the implementing class does not override it | The two default implementations conflict. | Override `public void f()` to resolve it. |
| `default String toString() { ... }` | `default` cannot override public methods of `Object`. | Let the implementing class override `toString()` itself. |

The incorrect examples only illustrate one error, not complete Java files. The article **Access restrictions and invalid modifiers** has a dedicated matrix for `private`, `protected`, `final`, and prohibited modifier combinations; the article **Implicitly public abstract methods** goes deeper into how the implementing class preserves `public` access.
## 9. How to choose the right method type

- Choose **`abstract`** when defining **required behavior** with no shared implementation: for example `save()`, `calculate()`, `validate()`.
- Choose **`default`** when there is **shared instance behavior** for implementing objects and implementing classes may be allowed to override it. Be careful about conflicts when an interface is shared or inherited from multiple branches.
- Choose **`static`** when there is a **public function related to the interface** that does not need to receive an implementing object, such as input format validation or a factory method.
- Choose **`private` instance** when you need to extract helper logic for **`default` or instance methods with a body** within the same interface.
- Choose **`private static`** when a helper does not depend on an object and needs to be used internally, including from public `static` methods.

Remember the difference between **inheritance** and **accessibility**: a `default` method is inherited by an implementing class as instance behavior; a public `static` method can be called from external code, but via the **interface name**, and is not inherited by an implementing class; a `private` method exists solely to support implementation inside the interface.

An interface annotated with `@FunctionalInterface` can still contain `default`, `static`, and `private` methods. These methods with bodies **do not count as the single abstract method** (SAM) of the functional interface. The main requirement for a functional interface is having only one matching abstract method contract after applying Java's rules.

### Self-check

1. What scope does `void run();` have in an interface? — **Implicitly `public abstract`**.
2. Is an implementing class required to write `default void log()`? — **No**, if the default version is satisfactory and there is no conflict; it can still override it.
3. `MyInterface.check()` and `object.check()`: which form is correct when `check` is a public `static` method of the interface? — **`MyInterface.check()`**.
4. Can a `private` method of an interface be overridden by an implementing class? — **No**, because it is not inherited and is only accessible inside the interface.
5. When should `private static` be used instead of `private` instance? — When the helper **does not need an object context**, especially when a `static` method of the interface also needs to call that helper.

**Key takeaway:** `abstract` = contract without a body; `default` = overridable instance implementation; `static` = behavior tied to the interface name; `private`/`private static` = internal-only helper logic.
