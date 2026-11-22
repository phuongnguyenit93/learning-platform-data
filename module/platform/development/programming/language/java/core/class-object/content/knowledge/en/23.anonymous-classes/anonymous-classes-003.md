# Passing Arguments to a Superclass Constructor When Creating an Anonymous Class in Java

In Java, an **anonymous class** lets you create a subclass or an interface implementation directly in an object creation expression without declaring a class name in the source code. When an anonymous class **extends a class whose constructor takes parameters**, Java allows you to place arguments inside the parentheses of the `new SuperClass(arguments) { ... }` expression. These arguments are used to select and invoke the **superclass constructor**, not a user-defined constructor inside the anonymous class body.

Minimal example:

```java
abstract class Greeting {
    protected final String name;

    Greeting(String name) {
        this.name = name;
    }

    abstract String say();
}

public class Main {
    public static void main(String[] args) {
        Greeting greeting = new Greeting("An") {
            @Override
            String say() {
                return "Xin chào " + name;
            }
        };

        System.out.println(greeting.say());
    }
}
```

Save as `Main.java` and run:

```bash
javac --release 17 -encoding UTF-8 Main.java
java Main
```

Stdout:

```text
Xin chào An
```

Here:

- `Greeting` is an **abstract superclass** with the constructor `Greeting(String name)`.
- `new Greeting("An") { ... }` both declares an **anonymous subclass** and creates an instance of that subclass.
- `"An"` is the argument passed into the **`Greeting(String)` constructor** to initialize the superclass's state.
- The `say()` method is overridden to complete the concrete subclass.
- There is **no** constructor declaration bearing the anonymous class's name inside `{ ... }`.

This lesson targets **Java 17+**, focusing on syntax, overload resolution, argument evaluation and object initialization order, access/checked exception checks, anonymous subclasses of inner classes, differences when implementing interfaces, generics, initializer blocks, common compilation errors, practical design scenarios, and self-check exercises.

## 1. Distinguishing Between the “Superclass Constructor” and the “Anonymous Class Constructor”

An anonymous class **has no declared name in the source code**, so you cannot define your own constructor with the syntax:

```java
new Greeting("An") {
    // Greeting(String name) { ... } // This is not how a constructor is declared here.
};
```

In the expression `new Greeting("An") { ... }`, the compiler determines the matching constructor of `Greeting` using the constructor selection rules that apply to class instance creation. The anonymous class has a **compiler-generated constructor** to perform the initialization process, in which the superclass constructor is invoked with the matching arguments.

You **should not think** of this as having two objects—one `Greeting` and one anonymous wrapper. There is only **one object of the anonymous subclass**, whose superclass portion is initialized by the `Greeting` constructor.

### How to Visualize It

```text
Expression: new Greeting("An") { override say() }
            │
            ├─ creates an anonymous subclass of Greeting
            ├─ selects Greeting(String) based on "An"
            ├─ creates a subclass object
            ├─ executes the superclass constructor
            ├─ executes the anonymous subclass initialization
            └─ returns a reference of type Greeting
```

`Greeting greeting` is **the type of the reference variable**. The runtime object is an anonymous subtype of Greeting. When calling `greeting.say()`, dynamic dispatch selects the overridden implementation in the anonymous class.

## 2. Key Syntax

General form when the superclass is a named class:

```java
SuperType reference = new SuperType(arg1, arg2) {
    // Fields, instance initializers, overridden methods...
};
```

Components:

| Syntax element | Meaning |
| --- | --- |
| `SuperType` right after `new` | The class extended by the anonymous class |
| `(arg1, arg2)` | Argument list used to select the superclass constructor |
| `{ ... }` | Body declaring the anonymous subclass |
| `SuperType reference` | Static type used by the caller to access the API |
| `@Override` | Checks whether the method actually overrides/implements |
| `super.someMethod()` inside an override | Calls the superclass method implementation when valid |

Distinguish this from the form without a class body:

```java
new SuperType(arg1, arg2);
```

This form directly creates an instance of `SuperType`, so it is only valid when SuperType is concrete and the constructor matches. The form with `{ ... }` creates an **anonymous subclass**, which can be used with an abstract superclass if the implementation satisfies the abstract methods.

### Distinguishing from the Constructor Call `super(...)`

`super(arguments);` is an **explicit constructor invocation** written inside the constructor body of **a named subclass** according to Java rules. In an anonymous class, you **cannot declare a constructor yourself** to put `super(arguments);` inside it. Instead, pass the arguments in the **`new Base(arguments) { ... }` expression**.

## 3. First Example: Superclass Holding Data from the Constructor

Save as **`AnonymousConstructorBasic.java`**:

```java
abstract class Shape {
    private final String color;

    Shape(String color) {
        this.color = color;
    }

    public String description() {
        return "color=" + color;
    }

    abstract int area();
}

public class AnonymousConstructorBasic {
    public static void main(String[] args) {
        Shape square = new Shape("blue") {
            @Override
            int area() {
                return 4 * 4;
            }
        };

        System.out.println(square.description());
        System.out.println(square.area());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AnonymousConstructorBasic.java
java AnonymousConstructorBasic
```

Stdout:

```text
color=blue
16
```

The `Shape` constructor receives the color and initializes the private field `color`. The anonymous subclass **does not directly access the private field** from the subclass code, but can still call the public inherited method `description()`. The anonymous subclass overrides `area()` to implement the abstract method.

**Takeaway:** Passing arguments to a superclass constructor works normally with an **abstract superclass**. Java does not require you to be able to call `new Shape("blue")` directly.

## 4. When Should You Use an Anonymous Subclass That Accepts Arguments?

An anonymous subclass makes sense when:

- There is a **superclass** with a constructor that establishes an invariant or dependency.
- You only need a **specialized implementation at a single point of use**.
- The subclass overrides a few methods within a short, easy-to-understand scope.
- There is no need to reuse the implementation under a separate class name.
- The superclass allows inheritance and the constructor is accessible from this context.

Practical examples:
- Specializing an abstract `Processor` with configuration parameters.
- Providing a callback object that extends a base adapter with state.
- Using a specialized test fixture that extends an abstract base with a constructor.
- Overriding a method of a framework component that has a parameterized constructor, if the framework API supports subclassing.

If the logic is long, used in multiple places, or requires complex constructors/state, a **named subclass** is usually easier to test and maintain than an anonymous class.

## 5. Constructor Overload Resolution

Superclasses can have multiple constructors:

```java
class Item {
    Item(int value) {
        // ...
    }

    Item(String name) {
        // ...
    }
}
```

When you write:

```java
new Item(7) { };
new Item("A") { };
```

the compiler inspects **the types of the argument expressions at compile time**, looks for matching constructors, and selects the overload according to Java's method/constructor invocation rules.

It is not the case that an anonymous class has a separate constructor that you freely choose in the body. The choice of superclass constructor has already been decided by the **`new` expression**.

### Key Rules

- The number and types of arguments must match an accessible constructor.
- If multiple constructors are applicable, Java applies overload resolution.
- Widening, boxing/unboxing, and varargs may be used according to specific rules and the order of selection phases.
- If no matching constructor exists: compile error.
- If two candidates are equally optimal and no single most-specific candidate can be selected: ambiguous constructor call.
- A runtime value cannot on its own switch the overload selection already decided by the compiler based on static types.

## 6. Runnable: Selecting a Constructor by Argument Type

Save as **`AnonymousOverloadDemo.java`**:

```java
class Message {
    private final String chosen;

    Message(int number) {
        chosen = "int:" + number;
    }

    Message(String text) {
        chosen = "String:" + text;
    }

    String describe() {
        return chosen;
    }
}

public class AnonymousOverloadDemo {
    public static void main(String[] args) {
        Message first = new Message(7) {
        };

        Message second = new Message("A") {
        };

        System.out.println(first.describe());
        System.out.println(second.describe());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AnonymousOverloadDemo.java
java AnonymousOverloadDemo
```

Stdout:

```text
int:7
String:A
```

The constructors are selected because `7` has type `int` and `"A"` has type `String`. The two anonymous objects do not necessarily have the same anonymous class at runtime, yet both have superclass `Message` and use the matching constructor.

## 7. Widening, Boxing, and Selection Order

Consider:

```java
class Base {
    Base(long value) {
        System.out.println("long");
    }

    Base(Integer value) {
        System.out.println("Integer");
    }
}
```

With `new Base(7) { }`, `7` is an int literal. In overload resolution, primitive widening from `int` to `long` can take precedence in the phase before boxing to `Integer`.

With `new Base(Integer.valueOf(7)) { }`, the argument has type `Integer`, so the `Base(Integer)` constructor is a direct match.

### Runnable

Save as **`AnonymousWideningDemo.java`**:

```java
class NumericBase {
    NumericBase(long value) {
        System.out.println("long");
    }

    NumericBase(Integer value) {
        System.out.println("Integer");
    }
}

public class AnonymousWideningDemo {
    public static void main(String[] args) {
        NumericBase first = new NumericBase(7) {
        };

        NumericBase second =
                new NumericBase(Integer.valueOf(7)) {
                };

        System.out.println(first != second);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AnonymousWideningDemo.java
java AnonymousWideningDemo
```

Stdout:

```text
long
Integer
true
```

Note: This is a consequence of Java overload resolution, **not a rule specific to anonymous classes**. Anonymous syntax simply uses the result of that constructor selection.

## 8. Ambiguous Constructor with `null`

The following snippet **intentionally does not compile**:

```java
class Base {
    Base(String value) {
    }

    Base(Integer value) {
    }
}

Base object = new Base(null) {
};
```

Both overloads `Base(String)` and `Base(Integer)` accept `null`, but `String` and `Integer` have no type relationship that makes one constructor clearly more specific than the other. The compiler cannot choose.

Resolution using a **cast specifying the argument type**:

```java
Base first = new Base((String) null) {
};

Base second = new Base((Integer) null) {
};
```

These are illustrative snippets within the same scope containing `Base`; when compiling, do not place the unfixed ambiguous `new Base(null)` snippet into a runnable file.

### Takeaway

Do not assume that the anonymous class body or overridden methods help the compiler “guess” the superclass constructor. **Constructor overload resolution is chosen from the argument list**; method overrides in the body do not resolve `null` ambiguity.

## 9. Arguments Are Expressions, Not Just Literals

Constructor arguments can be ordinary Java expressions:

```java
new ServiceConfig(prefix + suffix, calculatePort()) {
    // ...
};
```

Before the superclass constructor can run, the expressions must be evaluated according to Java's evaluation rules.

### What Can Happen During Argument Evaluation

- Calling a method and obtaining a value.
- Creating intermediate objects.
- Performing arithmetic or string concatenation.
- Throwing a runtime exception before the constructor runs.
- Performing side effects such as logging or incrementing a counter.
- Passing an existing reference, **without automatically deep-copying** the object that the reference points to.

### Side Effects in the Argument List

You should not rely on complex side effects in constructor arguments because the code becomes hard to read. Java has a clear evaluation order, but good design usually separates important computations into clearly named variables before the `new` expression.

## 10. Argument Evaluation Order: Left to Right

Java evaluates argument expressions **in left-to-right order**. After evaluation succeeds and produces the appropriate values, the constructor is invoked via the class instance creation mechanism.

Save as **`AnonymousArgumentOrderDemo.java`**:

```java
class PairBase {
    PairBase(int left, int right) {
        System.out.println("constructor:" + left + "," + right);
    }
}

public class AnonymousArgumentOrderDemo {
    static int evaluate(String label, int value) {
        System.out.println("evaluate:" + label);
        return value;
    }

    public static void main(String[] args) {
        PairBase value = new PairBase(
                evaluate("left", 1),
                evaluate("right", 2)) {
        };

        System.out.println("created:" + (value != null));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AnonymousArgumentOrderDemo.java
java AnonymousArgumentOrderDemo
```

Stdout:

```text
evaluate:left
evaluate:right
constructor:1,2
created:true
```

The print order of the argument expressions is not automatically reordered. If an argument expression throws an exception, subsequent steps may not happen; the superclass constructor does not execute successfully.

## 11. What If the Superclass Constructor Takes No Arguments?

If the superclass has an accessible no-argument constructor, the anonymous syntax still uses empty parentheses:

```java
class Base {
    Base() {
        System.out.println("base");
    }
}

Base instance = new Base() {
};
```

Here `()` requests the appropriate no-arg constructor of Base.

If there is only:

```java
class Base {
    Base(int value) {
    }
}
```

then `new Base() { }` **does not compile** because there is no matching no-arg constructor; you must use `new Base(123) { }` or modify the superclass design.

### Is a Default Constructor Generated Automatically?

If a class **declares no constructors**, Java has rules to generate a default constructor. However, once you have declared a parameterized constructor, the compiler **does not automatically generate an additional no-arg constructor** just for an anonymous subclass to use.

## 12. Runnable: Only a Parameterized Constructor Exists

Save as **`AnonymousRequiredArgumentDemo.java`**:

```java
class RequiredBase {
    private final int id;

    RequiredBase(int id) {
        this.id = id;
    }

    int id() {
        return id;
    }
}

public class AnonymousRequiredArgumentDemo {
    public static void main(String[] args) {
        RequiredBase first = new RequiredBase(42) {
        };

        System.out.println(first.id());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AnonymousRequiredArgumentDemo.java
java AnonymousRequiredArgumentDemo
```

Stdout:

```text
42
```

If you omit `42` and write `new RequiredBase() { }`, the compiler rejects it; the superclass has no matching no-arg constructor.

## 13. Access Modifier of the Superclass Constructor

Even when the argument types match, the superclass constructor must be **accessible** at the point where the anonymous class is instantiated according to Java access rules.

| Superclass constructor | What to consider |
| --- | --- |
| `public` | Can be called from code that can access the type, also depending on module/type |
| Package-private | Restricted to package access according to the rules |
| `protected` | Has specific package/subclass rules; not automatically callable from everywhere |
| `private` | Cannot be used from code without private/nest access |
| No matching constructor | Compile error even if the class body has complete overrides |

**Important note about `protected`:** Protected constructors do not behave like a public method. For a subclass in a different package, the access mechanism and the form of the object creation expression must satisfy the JLS; you should not generalize that “if an anonymous class can extend it, every protected constructor is always callable.”

### Cannot Bypass Access via the Anonymous Body

Adding:

```java
new SecretBase(7) {
    // override someMethod...
};
```

does not make a private constructor public. Java checks access and constructor selection before creating the object.

## 14. Compile-Negative Example: Private Constructor

Suppose there are **two independent top-level classes**, not nestmates:

```java
class SecretBase {
    private SecretBase(int id) {
    }
}

class Client {
    void create() {
        // new SecretBase(7) { }; // Cannot call a private constructor.
    }
}
```

This snippet illustrates an access error. The compiler does not allow Client to call the private constructor of SecretBase.

How to handle this:
- Use a public/protected/package-private constructor **if the design genuinely permits it**.
- Use a factory API exposed by SecretBase if the caller only needs an object.
- If the superclass **intentionally forbids subclassing**, do not force an anonymous subclass; choose composition/strategy.
- In nested/nestmate contexts, private access permissions can differ; therefore, do not state that “a private constructor is never accessible anywhere.”

### Distinguishing Constructor Visibility from Class Visibility

Even if a constructor is public, if the superclass type is not accessible to the caller, the expression is still invalid. Conversely, a public type with an inaccessible constructor is still blocked.

## 15. A `final` Superclass Cannot Have an Anonymous Subclass

An anonymous class written as `new FinalBase(...) { ... }` is **a subclass** of FinalBase.

Therefore:

```java
final class FinalBase {
    FinalBase(int value) {
    }
}

// new FinalBase(3) { }; // Compile error.
```

It is invalid even when the anonymous body is **empty**. Simply having `{ }` after `new FinalBase(3)` already requests an anonymous subclass.

In contrast:

```java
FinalBase value = new FinalBase(3);
```

creates a FinalBase instance **directly**, which is valid if the constructor/type is accessible.

### Class Types That Are Inherently Final

- `String` is final.
- Record classes are final.
- Enum classes have specific subclass/constructor restrictions; do not use an anonymous `new EnumType(...) { }` to create an arbitrary enum instance.
- A `sealed` superclass only allows direct subclasses properly declared within the permitted hierarchy; an arbitrary anonymous subclass cannot bypass that restriction.

**The first question is not only “does the constructor take parameters?” but also “does the superclass allow inheritance?”.**

## 16. Anonymous Subclass of an Abstract Class

This is a natural use case:

```java
abstract class Processor {
    private final String name;

    Processor(String name) {
        this.name = name;
    }

    String name() {
        return name;
    }

    abstract int process(int input);
}
```

An anonymous subclass can pass `name` to the superclass constructor and implement the abstract method `process`:

```java
Processor twice = new Processor("twice") {
    @Override
    int process(int input) {
        return input * 2;
    }
};
```

In this case, **there is no way to write `new Processor("twice")` directly** because Processor is abstract. The `{ ... }` block both declares a concrete anonymous subtype and provides an implementation to obtain an object.

### Runnable

Save as **`AnonymousAbstractProcessorDemo.java`**:

```java
abstract class Processor {
    private final String label;

    Processor(String label) {
        this.label = label;
    }

    String label() {
        return label;
    }

    abstract int process(int input);
}

public class AnonymousAbstractProcessorDemo {
    public static void main(String[] args) {
        Processor twice = new Processor("twice") {
            @Override
            int process(int input) {
                return input * 2;
            }
        };

        System.out.println(twice.label());
        System.out.println(twice.process(9));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AnonymousAbstractProcessorDemo.java
java AnonymousAbstractProcessorDemo
```

Stdout:

```text
twice
18
```

The argument `"twice"` goes into the `Processor(String)` constructor; the process behavior comes from the anonymous subclass.

## 17. Constructor Arguments When an Anonymous Class Implements an Interface

The two syntaxes look similar, but **their semantics differ**:

**Anonymous subclass of a class:**

```java
new AbstractProcessor("A") {
    @Override
    void execute() {
        // ...
    }
};
```

**Anonymous implementation of an interface:**

```java
new Runnable() {
    @Override
    public void run() {
        // ...
    }
};
```

Since `Runnable` is an interface, there is no `Runnable(String)` constructor to accept arguments. An anonymous class implementing Runnable has the appropriate superclass Object and target interface Runnable.

Therefore, writing:

```java
// new Runnable("A") { ... } // Invalid.
```

is wrong. If the callback needs a parameter such as `"A"`, you can:
- Use a captured **effectively-final local variable**.
- Define an **instance field** and an instance initializer inside the anonymous class.
- Write a named class implementing Runnable with a constructor that accepts parameters.
- Use lambda capture if Runnable is a functional interface and the semantics fit.

## 18. Runnable: An Interface Does Not Take Constructor Arguments, Yet Captures Data

Save as **`AnonymousInterfaceCaptureDemo.java`**:

```java
public class AnonymousInterfaceCaptureDemo {
    static Runnable makeTask(String message) {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println("task:" + message);
            }
        };
    }

    public static void main(String[] args) {
        Runnable first = makeTask("A");
        Runnable second = makeTask("B");

        first.run();
        second.run();
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AnonymousInterfaceCaptureDemo.java
java AnonymousInterfaceCaptureDemo
```

Stdout:

```text
task:A
task:B
```

`message` is a method parameter of `makeTask`, captured by the anonymous class under the effectively final rule. It is **not an argument passed to a `Runnable` constructor**, because Runnable is an interface and has no such constructor.

## 19. Initializing the Anonymous Subclass Part Separately: Instance Fields and Initializers

Even without an explicit constructor bearing the anonymous class's name, the body can still contain **instance fields** and **instance initializer blocks**:

```java
Base value = new Base(7) {
    private final String tag;

    {
        tag = "configured";
    }

    @Override
    String describe() {
        return super.describe() + ":" + tag;
    }
};
```

Meaning:
- `Base(7)` initializes the superclass.
- Instance variable initializers/initializer blocks of the anonymous subclass execute after the superclass initialization according to Java's initialization sequence.
- An instance initializer can be used to set up state specific to the subclass.
- You do not declare `AnonymousClassName(...)` because there is no class name.
- Static methods/fields under current rules are a separate matter from constructors; **a static initializer does not replace an instance initializer**.

### Do Not Confuse an Initializer with a Constructor

An instance initializer is an unnamed block, such as `{ tag = "configured"; }`. It has no parameter list of its own for the caller to pass arguments into via the `new Base(7, "tag")` syntax unless the superclass has a constructor matching those arguments.

If you want multiple configuration parameters specific to the implementation, a **named subclass with an explicit constructor** is usually more suitable.

## 20. Runnable: Superclass Constructor Then Anonymous Class Initializer

Save as **`AnonymousInitializerOrderDemo.java`**:

```java
class Base {
    Base(int id) {
        System.out.println("base:" + id);
    }

    String describe() {
        return "base";
    }
}

public class AnonymousInitializerOrderDemo {
    public static void main(String[] args) {
        Base instance = new Base(7) {
            private final String tag;

            {
                tag = "ready";
                System.out.println("anonymous-initializer");
            }

            @Override
            String describe() {
                return super.describe() + ":" + tag;
            }
        };

        System.out.println(instance.describe());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AnonymousInitializerOrderDemo.java
java AnonymousInitializerOrderDemo
```

Stdout:

```text
base:7
anonymous-initializer
base:ready
```

The superclass constructor runs before the instance initializer of the anonymous subclass; afterward, calling `describe()` uses the overridden method.

### Note on the Order of Fields and Initializer Blocks

Within a class, instance field initializers and instance initializer blocks execute in the appropriate textual order during the subclass initialization phase. You should not change their positions if initialization has interdependent side effects.

## 21. A Complete Order: Evaluating Arguments, Superclass, Anonymous Initializer, Method

Save as **`AnonymousFullOrderDemo.java`**:

```java
class OrderedBase {
    OrderedBase(int number) {
        System.out.println("base-constructor:" + number);
    }

    String label() {
        return "base";
    }
}

public class AnonymousFullOrderDemo {
    private static int argument() {
        System.out.println("evaluating-argument");
        return 5;
    }

    public static void main(String[] args) {
        OrderedBase value = new OrderedBase(argument()) {
            private final String suffix = "ready";

            {
                System.out.println("anonymous-initializer");
            }

            @Override
            String label() {
                return super.label() + "-" + suffix;
            }
        };

        System.out.println(value.label());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AnonymousFullOrderDemo.java
java AnonymousFullOrderDemo
```

Stdout:

```text
evaluating-argument
base-constructor:5
anonymous-initializer
base-ready
```

**Four distinct points in time:**
1. `argument()` runs to produce the constructor argument.
2. The `OrderedBase(int)` constructor initializes the superclass portion.
3. The anonymous subclass initializes `suffix` and executes the initializer block.
4. The caller calls `label()` via dynamic dispatch after the object completes construction.

Use this example to predict the output rather than assuming every line in the anonymous body runs immediately when the compiler encounters `new`.

## 22. Serious Warning: Superclass Constructor Calling an Overridable Method

A superclass constructor can call a method overridden by the subclass. Java uses **dynamic dispatch** even inside a constructor, while the instance fields of the anonymous subclass **have not yet been initialized by the subclass's initializers**.

This can cause the override to observe default field values such as `null` or `0`.

**This is not a bug specific to anonymous classes**: any subclass can encounter this problem when a superclass constructor calls an overridable method.

### Runnable: Observing Uninitialized State

Save as **`AnonymousConstructorDispatchDemo.java`**:

```java
class DispatchBase {
    DispatchBase() {
        System.out.println("during-constructor:" + describe());
    }

    String describe() {
        return "base";
    }
}

public class AnonymousConstructorDispatchDemo {
    public static void main(String[] args) {
        DispatchBase instance = new DispatchBase() {
            private String state = "ready";

            @Override
            String describe() {
                return state;
            }
        };

        System.out.println("after-constructor:"
                + instance.describe());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AnonymousConstructorDispatchDemo.java
java AnonymousConstructorDispatchDemo
```

Stdout:

```text
during-constructor:null
after-constructor:ready
```

Inside `DispatchBase()`, the call to `describe()` dispatches to the anonymous subclass's override, but `state` has not yet run its `"ready"` initializer, so it is still `null`. After object construction finishes, it becomes `"ready"`.

### Design Rules

**Avoid calling overridable instance methods from constructors** when the method relies on subclass state. You can:
- Only call non-overridable private/final/static helpers when appropriate.
- Defer callbacks until after construction completes.
- Perform invariant validation in the constructor using already available data.
- Use an explicit factory/configuration API to avoid the override-before-initialization hazard.

## 23. Calling a Superclass Method with `super.method()`

An anonymous class can override an instance method and then call the superclass version:

```java
Base value = new Base("A") {
    @Override
    String render() {
        return "[" + super.render() + "]";
    }
};
```

`super.render()` is a valid **method invocation** inside an instance method override when the superclass has a matching method and access permits it.

**Do not confuse `super.render()` with `super("A");`**:
- `super.render()` calls the inherited superclass method.
- `super("A");` is a constructor invocation, which only appears inside a valid constructor body of a named class and cannot be placed arbitrarily inside an anonymous class body or initializer.

### Runnable

Save as **`AnonymousSuperMethodDemo.java`**:

```java
class TextBase {
    private final String text;

    TextBase(String text) {
        this.text = text;
    }

    String render() {
        return text;
    }
}

public class AnonymousSuperMethodDemo {
    public static void main(String[] args) {
        TextBase base = new TextBase("hi");

        TextBase decorated = new TextBase("hi") {
            @Override
            String render() {
                return "[" + super.render() + "]";
            }
        };

        System.out.println(base.render());
        System.out.println(decorated.render());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AnonymousSuperMethodDemo.java
java AnonymousSuperMethodDemo
```

Stdout:

```text
hi
[hi]
```

## 24. A Constructor Argument Passes a Reference, Without Automatically Cloning the Object

Suppose the superclass constructor accepts `List<String>`:

```java
class ConfigBase {
    final java.util.List<String> settings;

    ConfigBase(java.util.List<String> settings) {
        this.settings = settings;
    }
}
```

Writing `new ConfigBase(sourceList) { ... }` only passes **a reference** as an argument. If ConfigBase stores a direct alias, the caller can still modify that list.

Having an anonymous class extend ConfigBase **does not automatically add a defensive copy**, does not make the list immutable, and does not provide thread safety.

### If a Snapshot Is Needed

The superclass constructor should proactively decide:

```java
ConfigBase(java.util.List<String> settings) {
    this.settings = java.util.List.copyOf(settings);
}
```

With immutable String elements and a valid source, this is an appropriate structural snapshot. If the elements are mutable, `List.copyOf` is still only shallow.

**Ownership policy belongs to the contract of the class and constructor**, not to the anonymous keyword.

## 25. Runnable: Observing Aliasing Through a Constructor

Save as **`AnonymousMutableArgumentDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

class ListBase {
    private final List<String> values;

    ListBase(List<String> values) {
        this.values = values;
    }

    String display() {
        return values.toString();
    }
}

public class AnonymousMutableArgumentDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("A");

        ListBase object = new ListBase(source) {
        };

        System.out.println(object.display());

        source.add("B");
        System.out.println(object.display());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AnonymousMutableArgumentDemo.java
java AnonymousMutableArgumentDemo
```

Stdout:

```text
[A]
[A, B]
```

The superclass retains the list reference passed into it. The anonymous subclass does not change alias semantics.

## 26. Passing Arguments vs. Capturing Effectively-Final Local Variables

Two mechanisms need to be distinguished:

**Constructor argument:**

```java
String prefix = "A";
Base value = new Base(prefix) {
};
prefix = "B";
```

This can be valid if the anonymous body **does not capture** the variable `prefix`. The argument `prefix` is **evaluated at object creation time** and then passed to the constructor. Reassigning the variable `prefix` afterward does not change the argument that was passed.

**Local-variable capture:**

```java
String prefix = "A";

Base value = new Base(prefix) {
    @Override
    String render() {
        return prefix; // Captures the enclosing method's variable.
    }
};

prefix = "B"; // No longer effectively final: compile error.
```

When the anonymous body directly references a local variable from the enclosing scope, that variable must be final/effectively final according to the rules.

**Key point:** A variable used **in the argument list** does not automatically become a captured variable of the anonymous body. You also need to check the **syntactic scope where the variable is referenced**.

## 27. Runnable: Argument Value Before/After Variable Reassignment

Save as **`AnonymousArgumentVersusCaptureDemo.java`**:

```java
class LabelBase {
    private final String label;

    LabelBase(String label) {
        this.label = label;
    }

    String label() {
        return label;
    }
}

public class AnonymousArgumentVersusCaptureDemo {
    public static void main(String[] args) {
        String variable = "first";

        LabelBase snapshot = new LabelBase(variable) {
        };

        variable = "second";

        System.out.println(snapshot.label());
        System.out.println(variable);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AnonymousArgumentVersusCaptureDemo.java
java AnonymousArgumentVersusCaptureDemo
```

Stdout:

```text
first
second
```

There is no reference to `variable` inside the anonymous class body, so reassigning the local variable does not violate the capture rule. The argument `"first"` had already been passed to the constructor before the variable changed to `"second"`.

## 28. Checked Exceptions from a Superclass Constructor

If the superclass constructor declares a checked exception, the expression `new SuperType(args) { ... }` must follow the exception checking rules.

Example:

```java
abstract class ReaderBase {
    ReaderBase(String source) throws java.io.IOException {
        if (source.isBlank()) {
            throw new java.io.IOException("empty");
        }
    }

    abstract String kind();
}
```

Creating an anonymous subclass:

```java
new ReaderBase("") {
    @Override
    String kind() {
        return "anonymous";
    }
};
```

The constructor call can throw `IOException`, so the enclosing code must catch or declare `throws IOException` (or appropriate supertypes), unless corresponding handling is already in place.

### Cannot “Erase” a Checked Exception by Overriding a Method

Having the anonymous body override `kind()` does not change the `throws IOException` of the superclass constructor. The checked exception originates from **construction**, not from the overridden abstract method.

## 29. Runnable: Handling a Checked Exception in a Constructor

Save as **`AnonymousCheckedConstructorDemo.java`**:

```java
import java.io.IOException;

abstract class ReaderBase {
    ReaderBase(String source) throws IOException {
        if (source.isBlank()) {
            throw new IOException("empty-source");
        }
    }

    abstract String kind();
}

public class AnonymousCheckedConstructorDemo {
    public static void main(String[] args) {
        try {
            ReaderBase value = new ReaderBase("") {
                @Override
                String kind() {
                    return "anonymous";
                }
            };

            System.out.println(value.kind());
        } catch (IOException error) {
            System.out.println("caught:" + error.getMessage());
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AnonymousCheckedConstructorDemo.java
java AnonymousCheckedConstructorDemo
```

Stdout:

```text
caught:empty-source
```

The constructor throws the exception before the object is successfully created; the line calling `value.kind()` does not run. The catch block handles the exception according to the contract.

## 30. If an Argument Expression Throws an Exception Before the Constructor

Before the superclass constructor runs, Java must evaluate the expressions in the argument list. If they throw an exception, construction stops before reaching the constructor.

Save as **`AnonymousArgumentExceptionDemo.java`**:

```java
class BaseWithLog {
    BaseWithLog(int number) {
        System.out.println("constructor:" + number);
    }
}

public class AnonymousArgumentExceptionDemo {
    static int argument() {
        System.out.println("argument-start");
        throw new IllegalStateException("bad-input");
    }

    public static void main(String[] args) {
        try {
            BaseWithLog value =
                    new BaseWithLog(argument()) {
                    };

            System.out.println(value);
        } catch (IllegalStateException error) {
            System.out.println("caught:" + error.getMessage());
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AnonymousArgumentExceptionDemo.java
java AnonymousArgumentExceptionDemo
```

Stdout:

```text
argument-start
caught:bad-input
```

There is no `constructor:...` because the argument expression throws an exception before the constructor executes. The anonymous class syntax does not “swallow” exceptions.

## 31. Varargs Constructor of the Superclass

A superclass can declare a varargs constructor:

```java
class Labels {
    Labels(String... labels) {
        // ...
    }
}
```

You can write:

```java
new Labels("A", "B", "C") {
};
```

Anonymous classes still use Java's constructor selection rules, including varargs when appropriate.

### Runnable

Save as **`AnonymousVarargsDemo.java`**:

```java
import java.util.Arrays;

class LabelsBase {
    private final String[] labels;

    LabelsBase(String... labels) {
        this.labels = labels.clone();
    }

    String describe() {
        return Arrays.toString(labels);
    }
}

public class AnonymousVarargsDemo {
    public static void main(String[] args) {
        LabelsBase value = new LabelsBase("A", "B", "C") {
        };

        System.out.println(value.describe());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AnonymousVarargsDemo.java
java AnonymousVarargsDemo
```

Stdout:

```text
[A, B, C]
```

The constructor call receives 3 string arguments via varargs. Inside, `LabelsBase` proactively clones the array so it does not keep a direct alias; cloning is a decision of the superclass, not a feature of the anonymous syntax.

## 32. Anonymous Subclass of an Inner Class with Its Own Enclosing Instance

A **non-static member inner class** requires an enclosing instance of the outer class upon instantiation. If you create **an anonymous subclass of that inner class from outside code**, you usually must specify the owner:

```java
Outer outer = new Outer();
Outer.Inner value = outer.new Inner(args) {
    @Override
    void act() {
        // ...
    }
};
```

There are two distinct pieces of information:
- `outer` is the **enclosing instance** associated with the inner superclass.
- `args` are the **constructor arguments** used to select/call the constructor of Inner.

**Do not mix the two** into a single parameter. `outer.new Inner(3) { ... }` passes the enclosing owner via the qualifier and passes `3` via the argument list.

### When Inside an Instance Method of Outer

An explicit qualifier may not be needed because an enclosing Outer instance is already available—for example, `new Inner(3) { ... }` in a suitable instance method. From a static context, there is no implicit Outer instance, so an owner must be provided.

## 33. Runnable: Anonymous Subclass of a Member Inner Superclass

Save as **`AnonymousInnerSuperclassDemo.java`**:

```java
public class AnonymousInnerSuperclassDemo {
    private final String ownerName;

    AnonymousInnerSuperclassDemo(String ownerName) {
        this.ownerName = ownerName;
    }

    class Inner {
        private final int id;

        Inner(int id) {
            this.id = id;
        }

        String describe() {
            return ownerName + "#" + id;
        }
    }

    public static void main(String[] args) {
        AnonymousInnerSuperclassDemo owner =
                new AnonymousInnerSuperclassDemo("A");

        AnonymousInnerSuperclassDemo.Inner value =
                owner.new Inner(7) {
                    @Override
                    String describe() {
                        return "[" + super.describe() + "]";
                    }
                };

        System.out.println(value.describe());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AnonymousInnerSuperclassDemo.java
java AnonymousInnerSuperclassDemo
```

Stdout:

```text
[A#7]
```

`owner.new Inner(7)` provides the enclosing instance and constructor argument. The anonymous subclass can override the inherited instance method, call `super.describe()`, and return the decorated result.

### Cases Requiring Caution

For a nested class in another package/type, access rules still apply. The qualifier must have the appropriate static type. An anonymous subclass does not help bypass private/protected/module boundaries.

## 34. Static Type of the Reference and New Methods in an Anonymous Class

Example:

```java
Base value = new Base(7) {
    void onlyHere() {
        System.out.println("local behavior");
    }
};
```

`value` has **static type Base**. If Base does not declare `onlyHere()`, then `value.onlyHere()` is invalid when called via the Base reference.

An anonymous class can define its own methods, but it has no source type name for the caller to easily use as an API.

**The `var` context exception:** Java 10+ has type inference rules that allow `var` to hold an anonymous class type in some cases; therefore, the accurate statement is that **through a reference declared as Base/interface type**, you can only call the members that static type provides. Do not generalize absolutely that an anonymous class's own method “can never be called.”

### Design Guidance

If the caller needs new methods in multiple places, a named subclass or a clearer interface is usually better than an anonymous implementation. An anonymous class should primarily override a contract that the caller already knows.

## 35. Generic Superclass and Constructor Arguments

An anonymous class can extend a specific generic superclass:

```java
class Holder<T> {
    private final T value;

    Holder(T value) {
        this.value = value;
    }

    T value() {
        return value;
    }
}
```

Creating an anonymous subclass with a type argument:

```java
Holder<String> item = new Holder<String>("Java") {
    @Override
    String value() {
        return super.value() + " 17";
    }
};
```

The value `"Java"` is passed to the `Holder(T)` constructor after appropriate type substitution. The type parameter `T` shapes type checking in the source, while bytecode has the erasure semantics of Java generics.

### The `<>` Diamond Operator with Anonymous Classes in Java 17

Since Java 9, the diamond operator can be used in anonymous class instance creation when inference/denotability conditions are valid:

```java
Holder<String> item = new Holder<>("Java") {
};
```

This does **not** mean every anonymous+diamond is valid regardless of the body's contents. Certain restrictions on methods and inferred types still apply. If a complex generic example hits an inference error, check the compiler diagnostic and use explicit type arguments when clearer.

## 36. Runnable: Generic Anonymous Superclass

Save as **`AnonymousGenericSuperclassDemo.java`**:

```java
class Holder<T> {
    private final T value;

    Holder(T value) {
        this.value = value;
    }

    T value() {
        return value;
    }
}

public class AnonymousGenericSuperclassDemo {
    public static void main(String[] args) {
        Holder<String> text = new Holder<String>("Java") {
            @Override
            String value() {
                return super.value() + " 17";
            }
        };

        Holder<Integer> number = new Holder<>(42) {
        };

        System.out.println(text.value());
        System.out.println(number.value());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AnonymousGenericSuperclassDemo.java
java AnonymousGenericSuperclassDemo
```

Stdout:

```text
Java 17
42
```

The argument `"Java"` enters the generic superclass constructor with `T=String`; the argument `42` undergoes appropriate boxing/inference for `Holder<Integer>`. The anonymous body can override a method, or remain empty when the superclass is already concrete.

## 37. A Constructor Is Not a Method That Can Be Overridden

A superclass has:

```java
class Parent {
    Parent(String name) {
        // ...
    }
}
```

Subclasses **do not override constructors**. Constructors are not inherited in the sense of ordinary method members. In an anonymous class, you also do not “override” `Parent(String)` by writing a method named Parent.

These are three distinct operations:
- **Constructor invocation**: `new Parent("A") { ... }` selects/invokes the Parent constructor.
- **Method overriding**: `@Override String label() { ... }` replaces the behavior of an inherited instance method.
- **Instance initialization**: `{ ... }` inside the anonymous class sets up its own state after appropriate superclass initialization.

If the superclass constructor establishes an important invariant, the anonymous subclass **does not skip** that step. Conversely, if the superclass constructor cannot be accessed, the subclass cannot invent a replacement constructor to bypass the restriction.

## 38. `this` and `super` Inside the Anonymous Body

Inside an instance method of an anonymous class:
- `this` is the current **anonymous object**.
- `super.someMethod()` refers to a valid superclass implementation.
- `Outer.this` in a context with a suitable enclosing instance is a **different object** from the anonymous instance.
- `super(args)` is not a constructor-call expression inside a method body; an explicit constructor invocation requires a valid constructor body position, whereas an anonymous class in source declares no constructor.

### Do Not Confuse with Lambdas

`this` inside a lambda has the lexical meaning of the enclosing context, not an anonymous object's `this`. If you refactor an anonymous class into a lambda to reduce lines, the behavior can change if the code relies on `this` or `super`.

### Do Not Draw Conclusions from the Generated Class Name

`this.getClass().getName()` may produce a compiler-generated name of the anonymous class, but you should not hardcode it as expected stdout across toolchains or design APIs around that name.

## 39. Runnable: `this` Is the Anonymous Instance

Save as **`AnonymousThisDemo.java`**:

```java
class BaseWithId {
    private final int id;

    BaseWithId(int id) {
        this.id = id;
    }

    String identify() {
        return "base:" + id;
    }
}

public class AnonymousThisDemo {
    public static void main(String[] args) {
        BaseWithId value = new BaseWithId(9) {
            @Override
            String identify() {
                return super.identify()
                        + ",subclass="
                        + (getClass() != BaseWithId.class);
            }
        };

        System.out.println(value.identify());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AnonymousThisDemo.java
java AnonymousThisDemo
```

Stdout:

```text
base:9,subclass=true
```

The runtime class differs strictly from `BaseWithId.class` because the created object belongs to the anonymous subclass. However, this approach does not need to guess the binary `$1` name of the anonymous implementation.

## 40. When the Parameter Is a Mutable Object

A constructor can receive a `StringBuilder`, `ArrayList`, or another object that the caller continues to use. Passing a reference into the constructor **does not create an immutable snapshot**.

If the superclass stores the reference:
- The caller mutates the source object → the superclass/anonymous instance can observe the mutation.
- The anonymous subclass mutates the source via the superclass API → the caller can see the change.
- Using `final` for the reference field does not make the referent immutable.
- In concurrency, separate synchronization/safe publication is needed.

### Where Should Copying Happen?

If the superclass's goal is to retain a value snapshot:
- Copy in the superclass constructor or a factory with clear responsibility.
- Do not expose the internal mutable reference via a getter.
- For nested mutable elements, consider a properly scoped deep copy.

If the superclass's goal is to hold a live service/dependency, **do not copy indiscriminately**; document ownership/lifecycle.

This is a state-design policy, not an issue of adding parentheses to an anonymous expression.

## 41. Constructor Forwarding with a Named Subclass for Comparison

If the same behavior needs to be used multiple times, a named subclass provides an explicit constructor:

```java
abstract class Base {
    Base(String name) {
        // ...
    }

    abstract void execute();
}

final class Named extends Base {
    Named(String name) {
        super(name);
    }

    @Override
    void execute() {
        // ...
    }
}
```

In a **named subclass constructor**, you can write `super(name)` as an explicit constructor invocation. In an anonymous subclass, you write:

```java
Base instance = new Base("A") {
    @Override
    void execute() {
        // ...
    }
};
```

There is no named constructor in which to declare `super(name)` inside the anonymous body.

### Which Approach Should You Choose?

| Need | Anonymous subclass | Named subclass |
| --- | --- | --- |
| Concise override at a single call site | Suitable | Can be somewhat verbose |
| Dedicated constructor accepting multiple kinds of config | Limited | Clearer |
| Logic needs reuse | Prone to code duplication | Suitable |
| Need to test the class separately | Hard to invoke by name directly | Easier |
| Many custom fields/invariants | Instance initializer can be used, but complex | Explicit constructor |
| Public API needs its own type | Less suitable | Suitable |
| An abstract superclass with a parameterized constructor | `new Base(args){...}` | `extends Base` with `super(args)` |

**Do not overuse anonymous classes just to reduce the number of files** if the logic has a distinct responsibility.

## 42. Runnable: Named and Anonymous Subclasses Both Calling a Superclass Constructor

Save as **`NamedVsAnonymousConstructorDemo.java`**:

```java
abstract class ActionBase {
    private final String name;

    ActionBase(String name) {
        this.name = name;
    }

    String name() {
        return name;
    }

    abstract String execute();
}

final class NamedAction extends ActionBase {
    NamedAction(String name) {
        super(name);
    }

    @Override
    String execute() {
        return "named:" + name();
    }
}

public class NamedVsAnonymousConstructorDemo {
    public static void main(String[] args) {
        ActionBase named = new NamedAction("A");

        ActionBase anonymous = new ActionBase("B") {
            @Override
            String execute() {
                return "anonymous:" + name();
            }
        };

        System.out.println(named.execute());
        System.out.println(anonymous.execute());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 NamedVsAnonymousConstructorDemo.java
java NamedVsAnonymousConstructorDemo
```

Stdout:

```text
named:A
anonymous:B
```

NamedAction forwards the parameter via `super(name)` in a named constructor. The anonymous subclass passes `"B"` at `new ActionBase("B") { ... }`. The result is of the same kind: the superclass portion is initialized with state from the argument.

## 43. Relationship with Protected Constructor Access

A protected constructor can support subclassing, but the access rules are not as simple as “if you see the type, you can call the constructor.”

For example, within the same package, a protected member/constructor is normally accessible according to the appropriate package rules:

```java
class Base {
    protected Base(int id) {
    }
}

class Client {
    void create() {
        Base value = new Base(1) {
        };
    }
}
```

This is an illustrative **same-package** snippet. For a different-package case, you need to consider:
- Which class is a subclass of Base?
- Through which syntax is the constructor accessed?
- Is the qualified/unqualified new expression valid?
- Module/package exports?
- Whether nested access applies?

**Do not assume that `protected` is `public`**. If the compiler reports an access error, explain it based on package/subclass structure and declarations, rather than “fixing” it by casting arguments.

## 44. Constructors with Varargs Overloads and `null`

The presence of varargs requires care in constructor selection:

```java
class Base {
    Base(String single) {
    }

    Base(String... many) {
    }
}
```

With `new Base("A") { }`, the fixed-arity constructor `Base(String)` can be selected before a varargs invocation. However, with `new Base((String[]) null) { }`, it targets the varargs constructor with a `String[]` argument.

In some overload combinations, `null` still causes ambiguity. You should not select an overload based on “which constructor I want” while ignoring static argument types.

### Suggestions

- Define constructor signatures that are less prone to ambiguity.
- Provide clearly named factory methods if the overload set is complex.
- Add a cast only when you genuinely need to specify a concrete argument type.
- Use unit tests compiled with the matching `--release` when an API has overloads together with generics/varargs.

## 45. Handling Constructor Exceptions in Callback APIs

In frameworks, an anonymous subclass is often created once and registered:

```java
Processor callback = new Processor(config) {
    @Override
    void onEvent() {
        // ...
    }
};
registry.register(callback);
```

This is a design snippet, not a standalone runnable program. Two steps need to be distinguished:

1. **Construction:** selecting and calling the superclass constructor, which can throw an exception, trigger a validation failure, or have side effects.
2. **Callback execution:** the framework invokes `onEvent` later, with its own lifecycle/threading.

Do not mix construction errors with callback errors. If the constructor fails, the callback has not yet been registered in the normal flow. If the callback runs on another thread, object state/thread safety requires its own contract.

## 46. Capturing in an Anonymous Class Can Keep the Enclosing Object Alive Longer

If an anonymous class is created inside an instance method and accesses the owner's state, it can retain a reference to the enclosing instance:

```java
class Screen {
    private final String id = "screen";

    Runnable listener() {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println(id);
            }
        };
    }
}
```

If the listener is stored in a long-lived event bus and is not unregistered, Screen can remain reachable longer than expected.

A constructor argument in an anonymous subclass can also cause the object to store long-lived dependencies. Therefore, **enclosing instance capture** and **argument reference retention** are two different paths that can affect lifecycle.

Solutions:
- Only capture necessary state.
- Pass immutable values when appropriate.
- Unregister/close according to the lifecycle.
- For a callback that only needs a brief behavior, consider a lambda or static helper, while still reviewing captured references.

## 47. Choosing a Clearer API When an Anonymous Implementation Needs Many Custom Parameters

An anonymous class has no source constructor of its own, so configuration typically relies on:
- Parameters of the superclass constructor.
- Effectively-final captured local variables.
- Instance fields initialized from expressions/captured values.
- An instance initializer block.
- Methods called after construction.

When there is too much configuration, a dedicated constructor on a named subclass or composition is usually better because:
- Validation is centralized.
- Invariants are clear.
- Error handling is easy.
- Reuse and testing are easy.
- It does not depend on side effects scattered inside an anonymous initializer.

For example, if an implementation has 8 config parameters, 5 fields, and 4 overrides, that is a sign you should consider extracting a named type.

## 48. Checklist for Determining Which Constructor Is Called

When reading `new Parent(a,b) { ... }`, go in order:

1. Is `Parent` a **class**, not an interface?
2. Does `Parent` allow subclassing (not final, valid sealed constraints)?
3. Is `Parent` a generic class or a raw type?
4. What is the list of declared constructors?
5. Is there a default no-arg constructor, or has another constructor been declared?
6. Which constructors are accessible to the caller?
7. What static types do the argument expressions have?
8. Are they evaluated from left to right without throwing an exception?
9. Which overload is selected according to widening/boxing/varargs?
10. Is there ambiguity, such as `null` between unrelated reference types?
11. Does the constructor have a checked `throws` that must be caught/declared?
12. Does the superclass constructor call a hazardous overridable method?
13. Does the anonymous subclass implement all abstract methods?
14. What state do the anonymous class's fields/instance initializer depend on?
15. If the superclass is a member inner class, how is the enclosing instance provided?
16. Can a reference declared as type Base see anonymous-only methods?
17. Are there captured variables that must be effectively final?
18. Is there an alias to mutable state retained by the superclass?
19. Is there lifecycle/callback threading to inspect after construction?
20. If the logic is complex, would a named subclass be clearer?

**Only after answering these questions** should you conclude whether the anonymous creation expression compiles, which constructor runs, and what the stdout will be.

## 49. Exercise 1 — Identify Where the Argument Goes

```java
abstract class Base {
    Base(String name) {
        System.out.println(name);
    }

    abstract void run();
}

Base value = new Base("A") {
    @Override
    void run() {
    }
};
```

**Answer:** `"A"` is passed to the `Base(String)` constructor, printing `A` when creating the object. The anonymous class implements `run` and does not declare its own constructor.

## 50. Exercise 2 — Can an Anonymous Class Write Its Own Constructor?

```java
Base object = new Base("A") {
    Base(String name) {
        super(name);
    }
};
```

**Answer:** Invalid. An anonymous class does not have a source constructor named `Base`. `Base` is the superclass, not the name of the anonymous class. Use `new Base("A") { ... }` to pass arguments.

## 51. Exercise 3 — No-Arg Constructor Does Not Exist

```java
class Base {
    Base(int value) {
    }
}

Base value = new Base() {
};
```

**Answer:** Does not compile because there is no matching no-arg constructor. Change it to `new Base(3) { }` or add an appropriate no-arg constructor to Base according to the design.

## 52. Exercise 4 — Overload Resolution from Type `int`

A superclass has `Base(int)` and `Base(String)`. Which constructor does `new Base(7) { }` call?

**Answer:** `Base(int)`, because the argument `7` is an int literal.

## 53. Exercise 5 — Ambiguous null

A superclass has `Base(String)` and `Base(Integer)`. Is `new Base(null) { }` valid?

**Answer:** No, it is ambiguous when neither overload is more specific. Cast `(String) null` or `(Integer) null` if you want to select a specific one.

## 54. Exercise 6 — Private Superclass Constructor

An unrelated class tries `new SecretBase(1) { }` while `SecretBase(int)` is private.

**Answer:** Calling that private constructor is not allowed. An anonymous subclass does not automatically bypass access control. Review access/factory options or change the design.

## 55. Exercise 7 — Final Superclass

```java
final class Box {
    Box(int n) {
    }
}

Box box = new Box(1) {
};
```

**Answer:** Invalid because class `Box` is final and cannot have an anonymous subclass. `new Box(1)` without a body is a different case and can be valid.

## 56. Exercise 8 — Abstract Superclass Constructor

An abstract superclass `Base` has constructor `Base(String)` and abstract method `run()`.

**Answer:** You can create an anonymous subclass using `new Base("A") { @Override void run() {...} }` if the constructor is accessible and all abstract requirements are implemented.

## 57. Exercise 9 — Interface with Arguments

```java
Runnable r = new Runnable("A") {
    @Override
    public void run() {
    }
};
```

**Answer:** Invalid. `Runnable` is an interface and has no constructor accepting a String. Use `new Runnable() { ... }` with a captured variable or a named implementation with its own constructor.

## 58. Exercise 10 — Interface Capturing a Parameter

```java
static Runnable make(String message) {
    return new Runnable() {
        @Override
        public void run() {
            System.out.println(message);
        }
    };
}
```

**Answer:** Valid if `message` is effectively final. It is **captured**, not passed into a Runnable constructor.

## 59. Exercise 11 — Evaluation Order

`new Base(f(), g()) { }` where `f()` and `g()` both print their own names before returning an int.

**Answer:** Java evaluates `f()` before `g()`. The constructor runs after argument evaluation succeeds.

## 60. Exercise 12 — Argument Throws an Exception

`f()` in `new Base(f()) { }` throws `IllegalStateException` before returning.

**Answer:** The Base constructor has not run; the construction expression stops and the exception propagates according to Java rules, unless caught in outer code.

## 61. Exercise 13 — Checked Exception of a Constructor

`Base() throws IOException` and the caller uses `new Base() { }` inside a method that neither catches nor declares it.

**Answer:** Invalid if `IOException` is not handled. Anonymous override methods do not automatically eliminate checked exceptions from the constructor.

## 62. Exercise 14 — Instance Initializer

```java
Base value = new Base(3) {
    {
        System.out.println("init");
    }
};
```

**Answer:** The superclass constructor runs before the instance initializer of the anonymous subclass. An initializer is not a named explicit constructor.

## 63. Exercise 15 — Constructor Calling an Overridable Method

The superclass constructor calls `describe()`; the anonymous override uses a field initialized as `String text = "ready"`.

**Answer:** The override may observe `text == null` at the moment the superclass constructor calls it, because the subclass field initializer has not yet run. Avoid dispatching to overridable methods in constructors if the logic depends on subclass state.

## 64. Exercise 16 — Is `super.method()` Valid?

An anonymous subclass overrides `render` and calls `super.render()` inside it.

**Answer:** Valid if the inherited method is accessible and there are no other constraints. This is a **superclass method call**, not a `super(...)` constructor invocation.

## 65. Exercise 17 — `super(3)` Inside an Instance Initializer?

```java
new Base(3) {
    {
        // super(3); // Invalid.
    }
};
```

**Answer:** An explicit constructor invocation cannot be used in an instance initializer block. The superclass constructor is selected via `new Base(3)`.

## 66. Exercise 18 — What Else Does an Inner Superclass Need?

`Outer.Inner` is a non-static member inner class with constructor `Inner(int id)`, and the caller has `Outer owner`.

**Answer:** You can use `owner.new Inner(7) { ... }` in a valid access context. `owner` is the enclosing instance; `7` is the constructor argument.

## 67. Exercise 19 — Generics

`Holder<T>` has constructor `Holder(T value)`. Create a `Holder<String>` using an anonymous subclass.

**Answer:** `new Holder<String>("Java") { ... }` is an explicit way to write it. On Java 17, `new Holder<>("Java") { ... }` can be valid under the appropriate diamond/inference rules.

## 68. Exercise 20 — Varargs

The superclass has constructor `Base(String... values)`. How many elements does `new Base("A","B") { }` pass?

**Answer:** A varargs array containing two String elements for the constructor in a call of this form.

## 69. Exercise 21 — Constructor Argument and Reassignment

```java
String label = "A";
Base value = new Base(label) {
};
label = "B";
```

**Answer:** Can be valid. `label` is only used as an argument, not captured by the anonymous body. The constructor receives the value/reference corresponding to `"A"` at creation time.

## 70. Exercise 22 — Capture Violating Effectively Final

```java
String label = "A";
Base value = new Base(label) {
    @Override
    String render() {
        return label;
    }
};
label = "B";
```

**Answer:** Invalid if the override captures `label`, because it is reassigned. Argument evaluation and local-variable capture are two different mechanisms.

## 71. Exercise 23 — Does This Create Two Objects, Base and an Anonymous Wrapper?

**Answer:** No. A `new Base(3) { ... }` creates a single **anonymous subclass object** with its superclass portion initialized; it is not two independent Java objects following a “base inside a wrapper” model.

## 72. Exercise 24 — Runtime Type and Static Type

`Base value = new Base(7) { void extra() { } };`. Can you call `value.extra()`?

**Answer:** No, because the static type `Base` does not declare `extra`. If the anonymous body overrides methods belonging to Base, they can be called through a Base reference. The local `var` case has its own type inference and must be analyzed separately; it does not change the conclusion for a variable declared as `Base`.

## 73. Exercise 25 — Anonymous Class vs. Named Subclass

An implementation has 12 fields, complex validation, needs to be used in multiple places, and has its own unit tests.

**Answer:** A named subclass with an explicit constructor is usually more suitable. An anonymous class has no source constructor name and can easily scatter initialization logic.

## 74. Exercise 26 — Mutable Object Argument

`Base` accepts a mutable `List<String>` and stores the reference directly; an anonymous subclass is created via `new Base(source) { }`. The caller mutates source.

**Answer:** Base can observe the changes if it retains an alias. A constructor argument does not automatically make a defensive copy, and the anonymous keyword does not add immutability.

## 75. Exercise 27 — Sealed Hierarchy

The superclass is declared sealed, and the anonymous subclass is not among the permitted direct subclasses.

**Answer:** You cannot arbitrarily create an anonymous subclass to bypass sealed restrictions. Choose a permitted named subtype/strategy according to the API.

## 76. Exercise 28 — Callback Lifetime Differences

An anonymous subclass of a listener base is created, its constructor receives a service reference, and the callback is registered globally.

**Answer:** You need to check which references the constructor retains, which enclosing state the anonymous body captures, and how the callback is unregistered. Successful construction does not guarantee lifecycle/memory safety.

## 77. Exercise 29 — Does the Superclass Constructor Print First or the Anonymous Initializer?

**Answer:** The superclass constructor runs before the anonymous subclass instance initializer. Constructor argument expressions are even evaluated before the constructor itself if no exception occurs.

## 78. Exercise 30 — True/False Assessment

Consider the statements:

1. An anonymous class can call a parameterized constructor of its superclass.
2. You can declare an `Anonymous(int x)` constructor yourself inside the anonymous class body.
3. For an interface, `new Runnable("x") { ... }` can call a Runnable constructor.
4. An anonymous class is a subtype of the superclass written after `new`.
5. `super.render()` and `super("x")` are both method calls inside the anonymous body.
6. Having the superclass constructor throw IOException must be caught/declared.
7. A constructor argument reference is always deep-copied.
8. `owner.new Inner(args) { ... }` can require both an enclosing instance and constructor arguments.

**Answer:** 1 true; 2 false; 3 false; 4 true; 5 false; 6 true; 7 false; 8 true.

## 79. Common Mistakes When Learning Anonymous Superclass Constructors

| Misconception | Reality | How to fix |
| --- | --- | --- |
| “Anonymous classes have no constructor so they cannot take arguments” | It forwards arguments to the superclass constructor in the `new` expression | `new Base(args) { ... }` |
| “You can write a constructor named Base inside the anonymous body” | An anonymous class has no source constructor name | Use the superclass argument list or a named subclass |
| “`new Interface(args) { ... }` is like `new Base(args) { ... }`” | Interfaces have no constructors | Use `new Interface() { ... }` and capture/fields/another implementation |
| “You can override a constructor” | Constructors are not overridden like instance methods | Override methods, call the ctor via `new` |
| “`super(args)` can sit inside an instance initializer” | Explicit constructor invocation has its own placement | Put arguments in `new Base(args)` |
| “Having a constructor take the right types is enough” | Access, abstract methods, subclassability, and throws also apply | Check all compile constraints |
| “A private constructor becomes accessible because of the anonymous subclass” | An anonymous class does not bypass access control | Design access/factory properly |
| “A final class can create an anonymous subclass if the body is empty” | The `{ }` body is still a subclass declaration | Use `new FinalBase(args)` without a body |
| “The constructor is selected by the argument's runtime class” | Overload resolution is based on compile-time types | Determine static types/casts |
| “`null` always chooses an unambiguous ctor” | It can be ambiguous between unrelated reference types | Cast/factory |
| “Constructor args execute in whatever order the JVM chooses” | Java has left-to-right evaluation order | Read according to Java evaluation rules |
| “The anonymous instance initializer runs before the Base ctor” | The superclass is initialized before the subclass initializer | Predict the correct order |
| “When a superclass ctor calls an override, subclass fields are ready” | They may still hold default values | Do not call overridable methods in ctors |
| “A checked exception from a ctor disappears if a method is overridden” | Constructor exception checking is independent | Catch/declare |
| “A List argument is copied automatically” | A reference alias is passed | Defensive-copy when the contract requires it |
| “A local variable used as a constructor arg must be effectively final” | Using it only in an arg does not automatically capture it | Distinguish expression vs. body capture |
| “An anonymous subclass of an inner class needs no owner” | An inner superclass usually needs an enclosing instance | `owner.new Inner(args) { ... }` |
| “An anonymous-only method can always be called via a Base ref” | Static type Base restricts method lookup | Interface/named class |
| “The class name `$1` is a contract” | Generated binary naming should not be treated as fixed | Use APIs/types |
| “An anonymous class is always better than a named subclass” | Complexity/reuse/testability may be higher | Named subclass or composition |

## 80. Checklist Before Writing `new Base(args) { ... }`

- [ ] Is `Base` the right kind of class, rather than an interface being passed constructor args?
- [ ] Is `Base` non-final and not prevented by sealed restrictions from having an anonymous subclass?
- [ ] Is there a matching accessible superclass constructor for the argument list?
- [ ] Have the static types of the arguments been checked for overload resolution?
- [ ] Is there no overload ambiguity, especially with `null` and varargs?
- [ ] Do Base's constructors preserve invariants and handle invalid arguments?
- [ ] Does the constructor throw checked exceptions that need to be caught/declared?
- [ ] Are the arguments evaluated without unexpected side effects?
- [ ] Does the anonymous body implement all abstract methods?
- [ ] Are you using `@Override` to catch method signature errors?
- [ ] Are you avoiding declaring a constructor yourself or writing `super(args)` inside an initializer?
- [ ] If subclass-specific state is needed, is an instance initializer clear enough or should you create a named subclass?
- [ ] Does the superclass constructor call an overridable method before subclass state is ready?
- [ ] If the superclass is an inner class, is the correct enclosing owner provided?
- [ ] If using generics/diamond, does the Java 17 compiler infer types properly?
- [ ] Are local variables **captured in the body** final/effectively final?
- [ ] Do mutable arguments need explicit copying/ownership?
- [ ] Does the reference static type provide the methods the caller needs?
- [ ] Is any dependency/resource held too long after callback registration?
- [ ] Are the filename, public class, and `javac --release 17` command consistent?
- [ ] Have **compile-negative** examples been separated from runnable files?
- [ ] Does stdout avoid depending on compiler-generated class names and thread scheduling?

## 81. Key Takeaways

1. When an **anonymous class extends a class**, the `new SuperClass(arguments) { ... }` syntax passes arguments to the **superclass constructor**, not a constructor declared inside the anonymous body.
2. An anonymous class has no source name and cannot declare a constructor using the superclass's name; the compiler handles constructor forwarding.
3. Constructor selection is governed by **overload resolution, accessibility, abstract/final/sealed restrictions, and checked exceptions**, just like other valid constructor calls.
4. **Argument expression evaluation** happens before the constructor call; subclass instance initialization runs only after superclass initialization.
5. Do not call overridable methods from a superclass constructor when subclass fields are not yet ready.
6. `super.someMethod()` in an anonymous override differs from a `super(arguments)` constructor invocation.
7. `new Runnable() { ... }` implements an interface; `Runnable` has no constructor that accepts args. Use effectively-final captures or a named implementation if configuration is needed.
8. If the superclass is a **non-static member inner class**, the syntax may require `owner.new Inner(arguments) { ... }`: the owner reference and constructor arguments have separate roles.
9. Constructor arguments **do not automatically deep-copy** mutable objects; ownership must be defined separately.
10. If an implementation is large enough to need its own constructor, complex invariants, or reuse, a **named subclass** is usually a more maintainable choice.

**Quick check question:** With `new Base(10) { @Override void run() { ... } }`, where is `10` used? — It is evaluated at the call site and passed to the **compiler-selected `Base` constructor**. The anonymous class body determines the subclass implementation, without redeclaring that constructor.

## Java Specification Sources

- **JLS Java SE 17 §15.9 — Class Instance Creation Expressions:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9
- **JLS Java SE 17 §15.9.5 — Anonymous Class Declarations:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9.5
- **JLS Java SE 17 §8.8 — Constructor Declarations:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8
- **JLS Java SE 17 §8.8.7.1 — Explicit Constructor Invocations:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8.7.1
- **JLS Java SE 17 §12.5 — Creation of New Class Instances:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.5
