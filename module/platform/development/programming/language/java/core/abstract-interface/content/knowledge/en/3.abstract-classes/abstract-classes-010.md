# Valid Modifier Combinations and the `abstract` vs. `final` Conflict in Java

`abstract` and `final` are both related to inheritance, but they carry different meanings. At the **class** level, `abstract` prevents direct instantiation and allows declaring methods that subclasses must implement; `final` prevents other classes from inheriting from it. At the **method** level, `abstract` declares behavior without a body, whereas `final` protects an existing implementation from being overridden.

A common point of confusion is that **an `abstract class` can contain `final` fields, `final` concrete methods, and be inherited by a `final` subclass**. A conflict only arises when both `abstract` and `final` are applied to **the exact same class or method declaration**.

This lesson uses Java 17+ and focuses on modifiers for abstract classes, abstract methods, as well as exceptions based on the declaration location.

## 1. Reading Modifiers by Where They Are Declared

| Target | `abstract` | `final` |
| --- | --- | --- |
| Class | Cannot be instantiated directly with `new`; may have abstract methods. | Cannot be extended via `extends` by another class. |
| Instance method | Has no method body and ends with `;`; concrete subclasses must fulfill the inheritance contract. | Has an implementation and cannot be overridden. |
| Field | Invalid. | Can only be assigned according to Java's initialization rules, and cannot be reassigned afterward. |
| Constructor | Invalid. | Invalid. |

An `abstract class` **may contain no `abstract` methods at all**. A class can be abstract solely to serve as a base class, share implementations, or prevent users from creating a meaningless instance. The converse is mandatory: **a class that declares an `abstract` method must be an `abstract` class**.

## 2. Modifiers on **Abstract Classes**

### 2.1. Top-level and Member Class Declarations

| Declaration | Valid? | Reason |
| --- | --- | --- |
| `abstract class Base {}` | Yes | Package-private top-level class. |
| `public abstract class Base {}` | Yes | Public top-level class; if it is a `public` top-level class, the source file must be named `Base.java`. |
| `final abstract class Base {}` | **No** | `final` forbids inheritance, whereas `abstract` requires leaving room for subclasses. |
| `private abstract class Base {}` at top-level | **No** | `private` cannot be applied to a top-level class. |
| `protected abstract class Base {}` at top-level | **No** | `protected` is for eligible member classes, not top-level classes. |
| `static abstract class Base {}` at top-level | **No** | A top-level class cannot be declared `static`. |
| `private static abstract class Base {}` inside a class | Yes | A **member** class can simultaneously be `private`, `static`, and `abstract`. |
| `protected abstract class Base {}` inside a class | Yes | A member class can be `protected abstract`. |
| `abstract sealed class Base permits Child {}` | Yes, when `Child` is valid | Only permitted classes may inherit directly. |
| `abstract non-sealed class Child extends Base {}` | Yes, if `Base` is a `sealed` class that directly permits `Child` | Reopens inheritance from the `Child` branch. |

`static abstract class` is only valid in a member-class context: `static` describes the relationship between the **nested class** and the enclosing class; it does not turn its `abstract` methods into static methods.

Since Java 17, `sealed` specifies the permitted direct subclasses; each such direct subclass must be `final`, `sealed`, or `non-sealed`. The three modifiers `final`, `sealed`, and `non-sealed` are mutually exclusive **on the same class**. `abstract sealed` makes sense because a superclass can still be abstract even while restricting which subclasses are allowed to exist. `non-sealed` cannot be used arbitrarily on a class that does not directly inherit from a `sealed` class or interface.

### 2.2. When an `abstract class` Contains `final` Members

The following declaration is **valid**:

```java
abstract class Parent {
    private final int id;

    protected Parent(int id) {
        this.id = id;
    }

    public final int id() {
        return id;
    }

    public abstract String name();
}
```

Here `Parent` is `abstract`, the field `id` is `final`, the method **with a body** `id()` is `final`, and `name()` is `abstract`. They apply to **three different targets**; there is no conflict.

A **concrete** subclass can be `final` and still `extends Parent`, provided it fully implements the inherited abstract methods. The subclass's `final` modifier only prevents other classes from inheriting further from that subclass. An abstract class can also contain constructors and `private`, `static`, `synchronized`, or `final` concrete methods in accordance with Java rules. Do not infer that every method of an `abstract` class must also be `abstract`.

## 3. Modifiers on **Abstract Methods**

An `abstract` method in an `abstract class` is an **instance** method without a body, ending with `;`. Allowed access levels: `public`, `protected`, or package-private when no access modifier is written.

| Declaration inside `abstract class` | Valid? | Reason |
| --- | --- | --- |
| `public abstract void run();` | Yes | Can be overridden and implemented by subclasses. |
| `protected abstract void run();` | Yes | Allows subclasses to access and override it. |
| `abstract void run();` | Yes | Package-private; requires consideration when subclasses exist in another package. |
| `private abstract void run();` | **No** | A `private` method cannot be overridden. |
| `abstract final void run();` | **No** | `final` forbids overriding, contradicting the implementation requirement of `abstract`. |
| `abstract static void run();` | **No** | `static` belongs to the class and performs *method hiding* rather than instance overriding. |
| `abstract synchronized void run();` | **No** | `synchronized` is an execution property of a method with a body. |
| `abstract native void run();` | **No** | `native` cannot be combined with `abstract`. |
| `abstract strictfp void run();` | **No** | These two modifiers are forbidden from being combined on a method; `strictfp` is also a property that has become redundant in modern Java. |
| `abstract void run() {}` | **No** | An abstract method must not have a body, even an empty one. |

Related notes:

- An `abstract` method can still declare parameters, generic types, a return type, and `throws`; the difference lies in having no body and needing to be implemented through inheritance.
- Constructors, fields, initializers, and static methods cannot be declared `abstract`.
- Modifiers such as `private`, `final`, `static`, and `synchronized` can be valid on **concrete methods with a body** inside an `abstract` class; only combining them with `abstract` on the same method causes an error.
- For an `interface`, a regular abstract method defaults to `public abstract`. An `interface` can declare `default`, `static`, or `private` methods **with a body**; this does not make `private abstract`, `static abstract`, or `final abstract` valid.

## 4. Complete Example Running on Java 17+

Create the file **`ModifierDemo.java`**:

```java
public class ModifierDemo {
    static abstract class Shape {
        private final String label;

        protected Shape(String label) {
            this.label = label;
        }

        public final String label() {
            return label;
        }

        public abstract int area();

        public String kind() {
            return "Shape";
        }

        public static String unit() {
            return "square units";
        }
    }

    static final class Rectangle extends Shape {
        private final int width;
        private final int height;

        Rectangle(int width, int height) {
            super("rectangle");
            this.width = width;
            this.height = height;
        }

        @Override
        public int area() {
            return width * height;
        }

        @Override
        public String kind() {
            return "Rectangle";
        }
    }

    public static void main(String[] args) {
        Shape shape = new Rectangle(3, 4);
        System.out.println(shape.label());
        System.out.println(shape.area());
        System.out.println(shape.kind());
        System.out.println(Shape.unit());
    }
}
```

Compile and run:

```bash
javac ModifierDemo.java
java ModifierDemo
```

Exact stdout output:

```text
rectangle
12
Rectangle
square units
```

Explanation:

1. `Shape` is a **member** class, so `static abstract` is valid. Using `new Shape(...)` directly is invalid because `Shape` is `abstract`.
2. `Shape.area()` has no body, so the concrete class `Rectangle` must provide an implementation.
3. `Shape.label()` is a `final` instance method **with a body**; subclasses cannot override `label()`.
4. The `private final String label` field is initialized in the parent constructor; it does not affect inheritability.
5. `Shape.unit()` is a **concrete** `static` method, so it does not conflict with the abstract class.
6. `Rectangle` is `final` yet still inherits validly from `Shape`: it only prevents **other** classes from inheriting further from `Rectangle`.
7. `kind()` is a concrete instance method that allows overriding; a call through a `Shape`-typed reference executes `Rectangle`'s version.

If you remove `Rectangle.area()` while keeping `Rectangle` as a concrete class, `javac` will report an error because the abstract method has not been implemented. If you try to add `@Override public String label() { return "new"; }` to `Rectangle`, it will also fail because it attempts to override a `final` method.

## 5. Valid `abstract sealed` Since Java 17

Create the file **`SealedAbstractDemo.java`**:

```java
public class SealedAbstractDemo {
    abstract static sealed class Result permits Success, Failure {
        abstract String describe();
    }

    static final class Success extends Result {
        @Override
        String describe() {
            return "OK";
        }
    }

    static non-sealed class Failure extends Result {
        @Override
        String describe() {
            return "ERROR";
        }
    }

    public static void main(String[] args) {
        Result result = new Success();
        System.out.println(result.describe());
    }
}
```

Commands:

```bash
javac SealedAbstractDemo.java
java SealedAbstractDemo
```

Stdout:

```text
OK
```

`Result` is abstract so it cannot be instantiated directly, yet it permits exactly two direct subclasses, `Success` and `Failure`. `Success` chooses `final` to terminate the inheritance branch; `Failure` chooses `non-sealed` to allow other classes to inherit from it. Both implement `describe()`. Another class that directly `extends Result` without being listed in `permits` will be rejected by the compiler.

## 6. Cases That **Intentionally Fail to Compile** and How to Fix Them

The snippets below are **standalone error examples**, not code meant to be run together with the two programs above. The exact text of `javac` error messages may vary by version.

### 6.1. `abstract final` Conflict on a Class

```java
abstract final class WrongBase {}
```

An `abstract` class needs to be inheritable by another class to become a concrete class; a `final` class forbids all subclasses. Change it to `abstract class WrongBase {}` when an abstract superclass is needed, or `final class WrongBase {}` when you want a concrete class that cannot be subclassed further.

### 6.2. `abstract final` Conflict on a Method

```java
abstract class WrongBase {
    public final abstract void execute();
}
```

`execute()` has no implementation yet forbids overriding. If this is a required contract, choose `public abstract void execute();`. If the implementation must be fixed, choose a **concrete method** with a body and `final`, for example `public final void execute() { System.out.println("run"); }`.

### 6.3. Abstract Method Marked `private`, `static`, or `synchronized`

```java
abstract class WrongBase {
    private abstract void a();
    static abstract void b();
    abstract synchronized void c();
}
```

`private` does not allow overriding, `static` does not participate in instance overriding, and `synchronized` belongs to the execution logic of a method with a body. When a contract is needed, choose `public abstract`, `protected abstract`, or package-private `abstract`; when a private/static helper or a synchronized method is needed, provide a concrete body and remove `abstract`.

Similarly, `abstract native` and `abstract strictfp` on the same method are both invalid.

### 6.4. Non-`abstract` Class Containing an `abstract` Method

```java
class WrongBase {
    abstract void execute();
}
```

Fix this by changing it to `abstract class WrongBase` or providing a body for `execute()`.

### 6.5. `abstract` Method with a Body

```java
abstract class WrongBase {
    abstract void execute() {
        System.out.println("run");
    }
}
```

Whether the body is empty or contains statements, the syntax is still invalid. Either remove the body and end with `;`, or remove `abstract`.

### 6.6. Applying `abstract` to a Record

```java
abstract record Point(int x, int y) {}
```

A record is a type that cannot be used as a base class for inheritance like a regular class; declaring an `abstract record` is not allowed. If a polymorphic contract is needed, consider an interface or an abstract class instead of a record.

## 7. Related Overriding Rules

A **concrete** subclass must complete the abstract methods that remain in effect; a subclass that is **still abstract** can continue deferring the implementation. An override must not make access more restrictive, must not broaden checked exceptions against the rules, and must preserve a compatible return type (which can be a covariant subtype). You should use `@Override` so the compiler verifies the signature.

Valid file-level example (without `main`):

```java
abstract class Processor {
    protected abstract String process(String input);
}

final class UpperProcessor extends Processor {
    @Override
    public final String process(String input) {
        return input.toUpperCase(java.util.Locale.ROOT);
    }
}
```

`Processor.process` is `protected abstract` in the superclass, while `UpperProcessor.process` is `public final` **with a body** in the subclass. Widening access from `protected` to `public` is valid. Once implemented, a method can certainly be marked `final`. The subclass can also be `final`.

Conversely, **a concrete method already marked `final` in the superclass** cannot be overridden in a subclass, regardless of whether the superclass is `abstract` or not. You need to check which declaration a modifier is attached to before diagnosing an error.

## 8. Checklist and Self-Check

1. Identify the target: top-level class, member class, instance method, static method, field, or constructor.
2. `abstract final` on **the same class** is always invalid, regardless of keyword order.
3. `abstract` together with `final`, `private`, `static`, `synchronized`, `native`, or `strictfp` on **the same method** is invalid.
4. An `abstract` method ends with `;` and has no body; the class declaring it must be `abstract`.
5. `final` on a **field**, on a **method with a body**, and on a **subclass that has fully implemented the contract** can coexist with an `abstract` superclass.
6. A top-level class does not accept `private`, `protected`, or `static`; member classes have their own rules.
7. With `sealed`, check `permits` and verify whether each direct subclass properly declares `final` / `sealed` / `non-sealed`.
8. For inheritance errors, check both abstract methods that have not been implemented and `final` methods that must not be overridden.

**Question:** Is `abstract class A { final int id = 1; abstract void run(); }` valid? **Yes.** `final` is attached to the field `id`, whereas `abstract` is attached to the class `A` and the method `run()`.

**Question:** Is `final class B extends A { @Override void run() {} }` valid (given `A` above)? **Yes.** `B` implements `run()` and then forbids other classes from inheriting further from `B`.
