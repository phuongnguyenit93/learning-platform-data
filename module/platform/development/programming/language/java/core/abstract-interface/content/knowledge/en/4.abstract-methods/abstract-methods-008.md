# Redeclaring a Method with a Body as `abstract` in Java

A method with a body (a concrete method) in a superclass **can be redeclared as an `abstract` method in an abstract subclass**, provided the superclass method can be overridden. This technique is commonly called **re-abstracting a method**. It allows an inheritance branch to **reject the superclass's default implementation** and force concrete subclasses in that branch to choose their own implementation.

This is a surprising rule: the fact that a superclass provides a full method body **does not mean** every subclass in every branch has to inherit that implementation. An `abstract` subclass can discard implementation inheritance for a method by declaring an abstract override.

## 1. Structure and Prerequisites

Basic pattern:

```java
class Parent {
    public void execute() {
        System.out.println("Cách làm mặc định");
    }
}

abstract class MustImplement extends Parent {
    @Override
    public abstract void execute();
}

class ConcreteChild extends MustImplement {
    @Override
    public void execute() {
        System.out.println("Cách làm được chọn rõ ràng");
    }
}
```

Here:

- `Parent.execute()` is a **concrete method**: it has a body, and `Parent` objects can call it directly.
- `MustImplement` is an **abstract class**. The line `public abstract void execute();` overrides `Parent`'s method but intentionally **has no body**. `@Override` is valid and helps the compiler verify that this is indeed an override.
- `ConcreteChild` is a concrete class: it must provide a valid `execute()` implementation in order to instantiate objects.
- Another subclass of `Parent` that does **not** go through `MustImplement` can still use the default `Parent.execute()`.

The semicolon `;` after the abstract declaration is mandatory; do not put braces `{}` on an `abstract` method even with an empty body. Here, `abstract` marks an implementation requirement, not a method with an empty body.

Important: **you cannot declare two methods with the same signature in the same class**, one concrete and then one abstract. Re-abstracting means **overriding a method inherited from a superclass**, not creating two methods with the same name and parameters within a single class.

## 2. Why Is This Needed?

Suppose a library has a `Formatter` class with a general formatting approach. A new group of applications requires each formatter to choose its own presentation style; implicitly using the default risks violating business rules.

We have three options:

1. Keep `Formatter` so existing cases still use the default implementation.
2. Create `StrictFormatter extends Formatter` and redeclare `render(...)` as `abstract` so **every concrete class inheriting through this branch must implement it**.
3. Have each concrete class, such as `UpperFormatter` or `SlugFormatter`, implement `render(...)`.

As a result, the requirement change affects only **the strict inheritance branch**. We do not need to remove the method body in `Formatter` and do not have to force all existing subclasses to reimplement the old behavior. This technique is useful when designing extensible frameworks, transitioning legacy APIs, or using a base class with shared utilities while requiring one branch to provide specific behavior.

However, re-abstracting is not a good default for every design. When there is no true inheritance relationship between object types, interfaces and composition are usually easier to organize.

## 3. Complete Runnable Java 17 Example

Save the entire following program as **`Main.java`**:

```java
import java.util.Locale;

public class Main {
    static class Formatter {
        public String render(String input) {
            return "DEFAULT(" + input + ")";
        }

        public final String describe(String input) {
            return "Result=" + render(input);
        }
    }

    static abstract class StrictFormatter extends Formatter {
        @Override
        public abstract String render(String input);
    }

    static final class UpperFormatter extends StrictFormatter {
        @Override
        public String render(String input) {
            return "UPPER(" + input.toUpperCase(Locale.ROOT) + ")";
        }
    }

    static final class SlugFormatter extends StrictFormatter {
        @Override
        public String render(String input) {
            return "SLUG(" + input.toLowerCase(Locale.ROOT)
                    .replace(' ', '-') + ")";
        }
    }

    public static void main(String[] args) {
        Formatter[] formatters = {
                new Formatter(),
                new UpperFormatter(),
                new SlugFormatter()
        };

        for (Formatter formatter : formatters) {
            System.out.println(formatter.describe("Java 17"));
        }
    }
}
```

With JDK 17 or later, run the following in the directory containing `Main.java`:

```bash
javac Main.java
java Main
```

**Expected output:**

```text
Result=DEFAULT(Java 17)
Result=UPPER(JAVA 17)
Result=SLUG(java-17)
```

**Explanation of output in execution order:**

1. The `new Formatter()` element uses `Formatter.render()`, which already has a body, producing `DEFAULT(Java 17)`.
2. The `new UpperFormatter()` element has the inheritance chain `Formatter → StrictFormatter → UpperFormatter`. Because `StrictFormatter` redeclared `render()` as abstract, `UpperFormatter` must define the method and returns `UPPER(JAVA 17)`.
3. The `new SlugFormatter()` element belongs to the same branch, so it must also define `render()`, returning `SLUG(java-17)`.
4. Even though the loop variable has type `Formatter`, the `render()` call inside `Formatter.describe()` is **dynamically dispatched** based on the actual object type. Therefore, `describe()` can use a single shared implementation while still receiving different formatting behaviors.
5. `describe()` is declared `final`, so subclasses cannot override it directly; the example can still re-abstract `render()` because **`render()` is not `final`**.

Note: `StrictFormatter` **cannot be instantiated directly** because it is an `abstract class`. A concrete class inheriting through `StrictFormatter` also cannot "reuse the default" simply by omitting `render()`, because the intermediate class's abstract requirement remains in effect.

## 4. What Exactly Changes in Inheritance?

Distinguish between the **method contract** and the **method body**:

| Class type | Status of `render(String)` | Can `new` be used? | At runtime |
| --- | --- | --- | --- |
| `Formatter` | Concrete, with default body | Yes | Uses `DEFAULT(...)` |
| `StrictFormatter` | Overridden as abstract, no body | No | No implementation in this branch yet |
| `UpperFormatter` | Overridden as concrete | Yes | Uses `UPPER(...)` |
| `SlugFormatter` | Overridden as concrete | Yes | Uses `SLUG(...)` |

The inheritance branch can be illustrated as follows:

```text
Formatter
  ├─ render(String): concrete
  └─ StrictFormatter (abstract)
       ├─ render(String): abstract  ← re-abstraction
       ├─ UpperFormatter
       │    └─ render(String): concrete
       └─ SlugFormatter
            └─ render(String): concrete
```

Re-abstracting **does not remove** the code of `Formatter.render()` from the root class: a `Formatter` object or another inheritance branch that does not override it can still call it. However, for a subclass inheriting through `StrictFormatter`, the method inherited in this branch is the nearest `abstract` declaration, and any concrete class must satisfy that requirement.

`@Override` is not what makes the method abstract; the `abstract` keyword determines that. `@Override` is recommended to catch typos, name mismatches, or parameter mismatches when the intent is to override.

## 5. Signature and Access Scope Rules

The redeclared method must follow Java's standard overriding rules:

- **Name and parameter list:** the overriding signature corresponds to the inherited method; changing the parameters creates an overload and does not force subclasses to implement the original method.
- **Return type:** keep a compatible type (covariant return types may be used for reference types). Do not change to an incompatible type.
- **Access level:** do not reduce the accessibility of the original method. A `public` superclass method must be overridden as `public`.
- **Checked exceptions:** the overriding method must not declare broader checked exceptions than those permitted by the superclass method; unchecked exceptions (`RuntimeException` and its subclasses) follow different rules.
- **`final` / `static` / `private`:** `final` forbids overriding; `static` uses hiding rather than instance method overriding; `private` is not inherited as a method that can be overridden in this way.
- **An `abstract` method cannot simultaneously be `final`, `static`, or `private`**. An abstract declaration has no body, whereas `final` forbids overriding to provide a body.

Valid example with access scope and covariant return type (this is a standalone illustration of type relationships, not part of the `Main.java` program above):

```java
class Metric {
    protected Number value() {
        return 1;
    }
}

abstract class ExactMetric extends Metric {
    @Override
    protected abstract Integer value();
}

class CountMetric extends ExactMetric {
    @Override
    protected Integer value() {
        return 5;
    }
}
```

`Integer` is a subtype of `Number`, so `ExactMetric.value()` has a compatible return type and the override is valid.

## 6. Examples That Fail to Compile and Why

The snippets below illustrate **intentional errors** and are not meant to be added to the runnable `Main.java`.

**Error 1 — a concrete class does not implement the newly re-abstracted method:**

```java
class IncompleteFormatter extends StrictFormatter {
    // Does not override render(String): compilation error.
}
```

If you want to keep this class without an implementation, you must declare it `abstract`, in which case you still cannot call `new IncompleteFormatter()`. If you want to instantiate objects, it must implement `render(String)` directly or inherit a valid concrete implementation from an appropriate class in the inheritance chain.

**Error 2 — attempting to re-abstract a `final` method:**

```java
class LockedParent {
    public final void save() {
        System.out.println("đã lưu");
    }
}

abstract class InvalidChild extends LockedParent {
    @Override
    public abstract void save(); // Error: cannot override final.
}
```

The `final` keyword in the superclass prohibits any override, including an abstract declaration.

**Error 3 — using `static` as an overridable method:**

```java
class Utility {
    public static void run() {}
}

abstract class InvalidUtility extends Utility {
    @Override
    public abstract void run(); // Error: instance method cannot override static.
}
```

Static methods belong to the class and do not participate in dynamic dispatch like instance methods. Redeclaring one as an abstract instance method causes a conflict.

**Error 4 — declaring abstract and concrete methods with the same signature in the same class:**

```java
abstract class Wrong {
    public void work() {}
    public abstract void work(); // Error: same signature in the same class.
}
```

Re-abstracting must happen **between classes in an inheritance relationship**, not through two duplicate declarations in a single class.

**Error 5 — calling `super.render()` from a grandchild class to recover the original body:**

```java
class BrokenFormatter extends StrictFormatter {
    @Override
    public String render(String input) {
        return super.render(input); // Error: render in StrictFormatter is abstract.
    }
}
```

Here `super` refers to the direct superclass's implementation according to `super` invocation rules; calling that abstract method provides no body to execute. Java does not support syntax like `super.super.render(...)` to "skip over" `StrictFormatter`. If you want to allow reusing the default logic, **explicitly design a separate concrete helper** in the root class (for example, `protected final String renderDefault(String input)`) so subclasses can call that helper.

## 7. Distinguishing Re-abstracting, Regular Overriding, and Overloading

| Action | Example | Result |
| --- | --- | --- |
| Override concrete with concrete | Subclass `public String render(...){...}` | Provides a new implementation |
| **Re-abstract concrete with abstract** | Abstract subclass `public abstract String render(...);` | Forces concrete classes further down the branch to implement it |
| Inherit without overriding | Subclass keeps the superclass's `render()` as is | Uses the existing implementation |
| Overload | Add `render(String, boolean)` | Creates a different signature; does not satisfy or replace `render(String)` |

Runtime polymorphism still takes effect once the concrete class provides a new body. Re-abstracting is primarily a **compile-time constraint**: it forces the author of a concrete class to explicitly decide on the behavior instead of accidentally inheriting the default.

### The Case of Interfaces with `default` Methods

A similar idea exists in **interface** inheritance. A subinterface can override an inherited `default` method with an abstract declaration to require implementers to provide it again:

```java
interface Greeter {
    default String greet() {
        return "Xin chào mặc định";
    }
}

interface CustomGreeter extends Greeter {
    @Override
    String greet();
}

class FriendlyGreeter implements CustomGreeter {
    @Override
    public String greet() {
        return "Xin chào từ lớp triển khai";
    }
}
```

This snippet illustrates interface relationships, **not** an abstract class. The original `Greeter` still retains its default method, but a concrete class that `implements CustomGreeter` must satisfy `greet()` according to the subinterface's contract. Do not confuse `default` methods in interfaces with `static` methods or with a case of Java allowing multiple class inheritance.

## 8. When to Use It, and When Not To?

**Consider re-abstracting when:**

- The base class has a reasonable default behavior for most cases.
- A special inheritance branch has strict rules: every concrete class must choose its own behavior.
- You need to keep the old API and behavior in the base class while requiring a new branch to provide an implementation.
- The abstract intermediate class has a clear design role and genuinely represents an `is-a` relationship.

**Consider interfaces/composition instead when:**

- Objects only share a capability without a meaningful class inheritance relationship.
- You need to swap strategies at runtime by passing different dependencies, rather than fixing them in the inheritance tree.
- The class tree grows deeper, making it hard to explain why one branch forbids the default implementation.
- You only need to fix a small call in the existing system and do not want to add an abstract layer that brings no useful constraint.

Choosing to re-abstract is a **decision about the inheritance contract**. If the goal is simply to place multiple algorithms under a single usable type, a shared interface and independent implementations may be clearer.

## 9. Self-Check Questions

1. In the example, why is `new Formatter()` valid while `new StrictFormatter()` is invalid?
2. What forces `UpperFormatter` to implement `render()`, even though `Formatter` already has a body?
3. Can `Formatter.describe()` be re-abstracted? Which keyword determines the answer?
4. If you create `class LegacyChild extends Formatter {}`, what will the result of `new LegacyChild().render("Java")` be?
5. Why does the method `render(String, boolean)` not replace overriding `render(String)`?
6. If you want a new implementation to reuse part of the logic from `Formatter.render()`, how should you design a helper so you do not rely on `super.super` syntax?
7. In a design without a natural parent–child relationship, why might an interface or composition be better than a re-abstracting intermediate class?

**Key takeaway:** Java allows an **abstract subclass to override an overridable concrete instance method of its superclass with an abstract method**. This preserves the default behavior in the root class while creating a new implementation obligation for concrete classes in an inheritance branch. Normal overriding rules still apply, especially regarding `final`, `static`, `private`, return types, and access levels.
