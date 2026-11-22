# Choosing Named Classes, Anonymous Classes, or Lambdas in Java 17+

The same behavior in Java can be expressed using a **named class**, an **anonymous class**, or a **lambda expression**. The three options can serve the same interface, yet they are **not completely equivalent** in terms of the type system, object identity, `this`/`super`, state, initialization, inheritance, scope of use, and maintainability.

This lesson presents a **decision-making approach** rather than simply replacing a long code snippet with a short one.

Example: a `Runnable` task that prints a message.

**Named class:**

~~~java
final class PrintTask implements Runnable {
    private final String text;

    PrintTask(String text) {
        this.text = text;
    }

    @Override
    public void run() {
        System.out.println(text);
    }
}
~~~

**Anonymous class:**

~~~java
String text = "Java";
Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println(text);
    }
};
~~~

**Lambda:**

~~~java
String text = "Java";
Runnable task = () -> System.out.println(text);
~~~

The three snippets illustrate implementing the same “print Java” behavior, but differ in encapsulation and organization. The named class has a constructor that accepts dependencies explicitly; the anonymous class creates an unnamed class at the expression; the lambda describes an implementation of a **functional interface** with a target type.

This lesson belongs to **Java Core — class-object / Anonymous Classes**, using **Java 17+**. Complete programs include a filename, `javac`/`java` commands, and expected stdout; non-standalone snippets are indicated by context.

## 1. Learning Objectives

After this lesson, you will:

1. Explain the nature of named classes, anonymous classes, and lambdas.
2. Know when a lambda is permitted: **functional interface/SAM** and target typing.
3. Know that a lambda does **not** directly extend any abstract/concrete class.
4. Know that an anonymous class can implement an interface or extend a non-final class and satisfy inheritance rules.
5. Know that a named class can share an implementation across multiple sites/modules.
6. Choose based on the number of abstract methods, constructors, fields, instance initialization, and behavior.
7. Distinguish explicit state fields from captured references and local values.
8. Distinguish `this`/`super` in an anonymous class from the lexical `this`/`super` of a lambda.
9. Grasp final/effectively-final capture in anonymous classes, local named classes, and lambdas.
10. Know that reassigning a captured local variable differs from mutating the referenced object.
11. Correctly read overload resolution and situations where a lambda lacks a target type or is ambiguous.
12. Use method references as a concise alternative when appropriate.
13. Understand the type identity of anonymous/named instances and the limitations on lambda identity guarantees.
14. Choose public APIs, test doubles, event listeners, and callbacks based on lifetime.
15. Handle checked exceptions according to SAM/override contracts.
16. Avoid huge class bodies at the call site and lambdas with many side effects.
17. Refactor among the three forms while still preserving semantics.
18. Design tests for behavior, captured state, and unsubscribing with the exact reference.
19. Understand Java 17 regarding records, sealed/final types, and default interfaces.
20. Have a checklist to help choose an implementation approach before writing code.

## 2. First: What Do the Three Styles Represent?

### Named Class

~~~java
final class PriceFormatter implements Formatter {
    // fields, constructors, methods...
}
~~~

A named class has a **source-level name**, and can be declared top-level or nested/member/local depending on placement. It is reused via its name/type, constructor, and class reference if access rules allow.

### Anonymous Class

~~~java
Formatter formatter = new Formatter() {
    @Override
    public String format(int cents) {
        return cents + " cents";
    }
};
~~~

An anonymous class expression both declares a class **with no name in source** and creates an instance. It has a **class body**, its own `this`, appropriate fields/methods/initializers, and is viewed through a base type.

### Lambda

~~~java
Formatter formatter = cents -> cents + " cents";
~~~

A lambda is an **expression whose target type is a functional interface**, not a declaration written in `class ...` syntax. The JVM is allowed to choose an appropriate instance representation; do not assume every lambda always creates an anonymous class with a fixed name/identity.

**Core difference:** “Shorter” is not enough. Ask about the type contract, state, lifecycle, and readability.

## 3. Runnable Example: All Three Implementing One Interface

Create **`ThreeStylesDemo.java`**:

~~~java
public class ThreeStylesDemo {
    interface Formatter {
        String format(String value);
    }

    static final class NamedFormatter implements Formatter {
        private final String prefix;

        NamedFormatter(String prefix) {
            this.prefix = prefix;
        }

        @Override
        public String format(String value) {
            return prefix + value;
        }
    }

    public static void main(String[] args) {
        Formatter named = new NamedFormatter("N:");
        String prefix = "A:";
        Formatter anonymous = new Formatter() {
            @Override
            public String format(String value) {
                return prefix + value;
            }
        };
        Formatter lambda = value -> "L:" + value;

        System.out.println(named.format("Java"));
        System.out.println(anonymous.format("Java"));
        System.out.println(lambda.format("Java"));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ThreeStylesDemo.java
java ThreeStylesDemo
~~~

Stdout:

~~~text
N:Java
A:Java
L:Java
~~~

All three are used through the interface Formatter. NamedFormatter receives prefix via constructor; anonymous captures the effectively-final local prefix; lambda creates a short implementation with a constant prefix.

## 4. 30-Second Decision Table

| Need | Typical Choice | Why |
| --- | --- | --- |
| A short behavior for a functional interface | **Lambda** | Compact, highlights the logic |
| Using a method of an existing object | **Method reference** | Direct and clear |
| Overriding a method of an abstract/concrete class | **Anonymous** or **named** | A lambda does not extend a class |
| Implementing an interface with multiple abstract methods | **Anonymous** or **named** | Lambdas only work with functional interfaces |
| Stateful callback with multiple fields/helper methods | **Named**, or a small anonymous class | Explicit state, lifecycle |
| Needing a constructor with validation and dependencies | **Named** | Constructor, invariants, testability |
| Single-use implementation with multiple small methods | **Anonymous** or local named | Keeps code close to the call site |
| Logic needed across multiple files/modules | **Named** | Reusability, name, and API |
| Complex generic implementation | **Named** | Type parameters, compiler errors easier to handle |
| Public stable extension point | **Named type** + interface | Does not rely on a generated class |
| Long callback with many branches and side effects | **Named/local named** | Easy to read and test |
| Pure one-line comparator | **Lambda/method reference** | Simple |
| Framework needing a concrete class/constructor via reflection | **Named** | Stable declaration |
| Long-lived listener capturing a large owner | Depends on how it is written, **prefer clear ownership** | Syntax does not automatically prevent retention |

This is a design guideline, not a compiler rule. Choose based on the **semantics to preserve**; do not turn every callback into a lambda just because it has fewer lines.

## 5. Prerequisite for Lambdas: Functional Interface

A lambda can only be used in a context with a **target functional interface type**, meaning an interface with exactly **one abstract method contract** after considering the rules on Object methods, overrides, inherited methods, and default/static/private methods.

Example:

~~~java
@FunctionalInterface
interface Calculator {
    int compute(int x, int y);
}
~~~

You can use:

~~~java
Calculator plus = (x, y) -> x + y;
~~~

### What Does `@FunctionalInterface` Do?

The annotation asks the compiler to verify that the interface is valid for a lambda. Writing the annotation is not required to use a lambda, but it should be placed on **interfaces intentionally designed to be functional**.

### Do Default/Static Methods Break Functional Status?

Not necessarily. They do not increase the number of abstract method contracts to implement. A functional interface can declare additional default and static methods.

~~~java
@FunctionalInterface
interface Transformer {
    String apply(String text);

    default String twice(String text) {
        return apply(apply(text));
    }

    static String identity(String text) {
        return text;
    }
}
~~~

## 6. Runnable Example: Functional Interface with Default/Static Methods

Create **`FunctionalInterfaceDemo.java`**:

~~~java
public class FunctionalInterfaceDemo {
    @FunctionalInterface
    interface Transformer {
        String apply(String value);

        default String twice(String value) {
            return apply(apply(value));
        }

        static String identity(String value) {
            return value;
        }
    }

    public static void main(String[] args) {
        Transformer addStar = value -> value + "*";

        System.out.println(addStar.apply("A"));
        System.out.println(addStar.twice("A"));
        System.out.println(Transformer.identity("A"));
    }
}
~~~

~~~bash
javac -encoding UTF-8 FunctionalInterfaceDemo.java
java FunctionalInterfaceDemo
~~~

Stdout:

~~~text
A*
A**
A
~~~

The lambda provides the `apply` implementation. Default `twice` calls `apply` twice. Static `identity` belongs to the interface, not an additional abstract contract.

## 7. Interface with Two Abstract Methods: Cannot Use a Lambda

~~~java
interface Validator {
    boolean isValid(String input);
    String errorMessage(String input);
}
~~~

This is not a functional interface because it has two distinct abstract methods. Writing:

~~~java
// Validator v = input -> input != null; // Compile error.
~~~

Replace with an **anonymous class**:

~~~java
Validator v = new Validator() {
    @Override
    public boolean isValid(String input) {
        return input != null && !input.isBlank();
    }

    @Override
    public String errorMessage(String input) {
        return isValid(input) ? "" : "blank";
    }
};
~~~

Or choose a **named class** if this implementation is reused or tested in multiple places.

## 8. Runnable Program: Interface with Multiple Abstract Methods

Create **`MultiMethodDecisionDemo.java`**:

~~~java
public class MultiMethodDecisionDemo {
    interface Validator {
        boolean isValid(String text);
        String errorMessage(String text);
    }

    public static void main(String[] args) {
        Validator validator = new Validator() {
            @Override
            public boolean isValid(String text) {
                return text != null && !text.isBlank();
            }

            @Override
            public String errorMessage(String text) {
                return isValid(text) ? "" : "blank";
            }
        };

        System.out.println(validator.isValid("Java"));
        System.out.println(validator.errorMessage("  "));
    }
}
~~~

~~~bash
javac -encoding UTF-8 MultiMethodDecisionDemo.java
java MultiMethodDecisionDemo
~~~

Stdout:

~~~text
true
blank
~~~

A lambda is not a direct option in this case; an anonymous or named class is the right choice. If you want a lambda, you must **redesign the API** into separate functional interfaces; do not try to force-cast the existing interface.

## 9. Extending an Abstract Class: Choose Anonymous or Named

A lambda cannot directly extend an abstract class, even if the class has only one abstract method:

~~~java
abstract class BaseJob {
    abstract void execute();
}

// BaseJob job = () -> {}; // Invalid: BaseJob is a class.
~~~

You can create an anonymous subclass:

~~~java
BaseJob job = new BaseJob() {
    @Override
    void execute() {
        System.out.println("execute");
    }
};
~~~

Or a named subclass:

~~~java
final class PrintJob extends BaseJob {
    @Override
    void execute() {
        System.out.println("execute");
    }
}
~~~

**Do not confuse them:** “Having only one abstract method” does not automatically turn a **class** into a functional interface. A lambda target must be a functional **interface**.

## 10. Runnable Example: A Lambda Does Not Replace an Anonymous Subclass

Create **`AbstractClassChoiceDemo.java`**:

~~~java
public class AbstractClassChoiceDemo {
    static abstract class BaseJob {
        private final String name;

        BaseJob(String name) {
            this.name = name;
        }

        String name() {
            return name;
        }

        abstract void execute();
    }

    static final class NamedJob extends BaseJob {
        NamedJob(String name) {
            super(name);
        }

        @Override
        void execute() {
            System.out.println("named:" + name());
        }
    }

    public static void main(String[] args) {
        BaseJob named = new NamedJob("A");

        BaseJob anonymous = new BaseJob("B") {
            @Override
            void execute() {
                System.out.println("anonymous:" + name());
            }
        };

        named.execute();
        anonymous.execute();
    }
}
~~~

~~~bash
javac -encoding UTF-8 AbstractClassChoiceDemo.java
java AbstractClassChoiceDemo
~~~

Stdout:

~~~text
named:A
anonymous:B
~~~

The anonymous expression passes "B" to the constructor of BaseJob. With multiple constructor parameters, validation, or varied subclass behavior, a named class is usually easier to manage.

## 11. Extending a Concrete Class to Customize Behavior

An anonymous subclass can also extend a **non-final concrete class** and override virtual methods:

~~~java
class Greeter {
    String greet() { return "Hello"; }
}

Greeter custom = new Greeter() {
    @Override
    String greet() { return "Xin chao"; }
};
~~~

A lambda does not replace `new Greeter(){...}` because Greeter is a class, not a functional interface.

**However, consider composition:** Instead of overriding a concrete class just to change how a message is printed, a `Greeter` that accepts a `Supplier<String>` or `Function<String,String>` can depend less on inheritance.

## 12. Constructor State and Dependency Injection

A named class has its own constructor with parameters, validation, and final fields:

~~~java
final class PrefixFormatter implements Formatter {
    private final String prefix;

    PrefixFormatter(String prefix) {
        this.prefix = java.util.Objects.requireNonNull(prefix);
    }

    @Override
    public String format(String text) {
        return prefix + text;
    }
}
~~~

This is an illustrative snippet that requires the Formatter interface in the same context. If the object has long-lived state, invariants, and a lifecycle, a constructor makes dependencies **explicit**.

An anonymous class cannot declare its own **named constructor**. It can:
- pass args to the superclass constructor via `new Base(args) { ... }`;
- have instance field initializers/instance initializer blocks;
- capture values from the lexical context.

A lambda has no class body to declare instance constructors or fields using named-class syntax.

## 13. Runnable Program: Named Class with an Invariant

Create **`NamedClassStateDemo.java`**:

~~~java
import java.util.Objects;
import java.util.function.Function;

public class NamedClassStateDemo {
    static final class Prefixer implements Function<String, String> {
        private final String prefix;

        Prefixer(String prefix) {
            this.prefix = Objects.requireNonNull(prefix, "prefix");
        }

        @Override
        public String apply(String value) {
            return prefix + value;
        }
    }

    public static void main(String[] args) {
        Function<String, String> formatter = new Prefixer("id:");
        System.out.println(formatter.apply("42"));

        try {
            new Prefixer(null);
        } catch (NullPointerException ex) {
            System.out.println("rejected=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 NamedClassStateDemo.java
java NamedClassStateDemo
~~~

Stdout:

~~~text
id:42
rejected=prefix
~~~

The named class makes the “non-null prefix” invariant clear at construction. With a lambda or anonymous class, you can validate parameters before creating the callback, but there is no separate constructor declared as shown above.

## 14. Captured Value Instead of a Constructor: When Is It Appropriate?

Anonymous classes and lambdas can read final/effectively-final locals:

~~~java
String prefix = "id:";

java.util.function.Function<String, String> a =
        new java.util.function.Function<String, String>() {
            @Override
            public String apply(String text) {
                return prefix + text;
            }
        };

java.util.function.Function<String, String> b =
        text -> prefix + text;
~~~

`prefix` is a local reference that is not reassigned, so both forms can capture it. If `prefix` is an immutable String, sharing the reference is safe for logical state.

If you want to:
- change the prefix per invocation;
- manage validation/ownership/resources;
- create a class used across multiple methods;

then a named class constructor makes the contract more transparent. Capture does not always replace dependency injection in an easily testable way.

## 15. The Final/Effectively Final Rule for Lambdas and Anonymous Classes

A local variable/parameter used from a lambda or anonymous body must be **final or effectively final**, and the same applies to a local named class.

Valid:

~~~java
int factor = 3;

java.util.function.IntUnaryOperator triple =
        value -> factor * value;
~~~

Invalid:

~~~java
int factor = 3;
factor = 4;

// IntUnaryOperator f = value -> factor * value; // Compile error.
~~~

**Must distinguish:**
- `factor = 4` reassigns the local variable → loses effectively final.
- `mutableObject.change()` only mutates the object → the local reference remains effectively final, though thread safety must be considered.

## 16. Runnable Program: Capturing a Mutable Holder

Create **`CapturedStateDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class CapturedStateDemo {
    public static void main(String[] args) {
        AtomicInteger counter = new AtomicInteger();

        Runnable lambda = () ->
                System.out.println("lambda=" +
                        counter.incrementAndGet());

        Runnable anonymous = new Runnable() {
            @Override
            public void run() {
                System.out.println("anonymous=" +
                        counter.incrementAndGet());
            }
        };

        lambda.run();
        anonymous.run();
        lambda.run();
    }
}
~~~

~~~bash
javac -encoding UTF-8 CapturedStateDemo.java
java CapturedStateDemo
~~~

Stdout:

~~~text
lambda=1
anonymous=2
lambda=3
~~~

The two callbacks share the same **AtomicInteger object**. The `counter` variable is effectively final, but state is mutated through the object. Do not assume that all captured state is independent between callbacks.

## 17. Does State Belong to the Callback Itself or to the Captured Object?

**Anonymous class instance field**:

~~~java
Runnable callback = new Runnable() {
    private int calls;

    @Override
    public void run() {
        System.out.println(++calls);
    }
};
~~~

Each anonymous object holds its own calls. A lambda has no syntax to declare an **instance field of the lambda object**. A lambda block can declare a local variable, but that local is recreated on each invocation:

~~~java
Runnable callback = () -> {
    int calls = 0;
    System.out.println(++calls);
};
~~~

When run multiple times, the callback above prints 1 each time, rather than retaining state 1,2,3.

**Choice:** Need a small per-callback private mutable field → anonymous or named. Need explicit shared mutable state → dependency holder + concurrency design. Need a stateless transform → lambda.

## 18. Runnable Program: Anonymous Field Differs from Lambda Local

Create **`CallbackStateComparisonDemo.java`**:

~~~java
public class CallbackStateComparisonDemo {
    public static void main(String[] args) {
        Runnable anonymous = new Runnable() {
            private int calls;

            @Override
            public void run() {
                calls++;
                System.out.println("anonymous=" + calls);
            }
        };

        Runnable lambda = () -> {
            int calls = 0;
            calls++;
            System.out.println("lambda=" + calls);
        };

        anonymous.run();
        anonymous.run();
        lambda.run();
        lambda.run();
    }
}
~~~

~~~bash
javac -encoding UTF-8 CallbackStateComparisonDemo.java
java CallbackStateComparisonDemo
~~~

Stdout:

~~~text
anonymous=1
anonymous=2
lambda=1
lambda=1
~~~

If you convert an anonymous callback to a lambda and drop the private field calls, **the behavior changes**. To preserve state, put it in a named class or an explicit mutable holder.

## 19. `this` in an Anonymous Class Differs from `this` in a Lambda

In an anonymous class, `this` in an instance method points to the **anonymous object**.

In a lambda, `this` is resolved according to the **lexical enclosing context**, just like `this` where the lambda is written. In an instance method of Outer, `this` inside the lambda is Outer.

In a static context, there is no enclosing `this` to use inside a lambda. Conversely, an anonymous class declared in a static method still has its own instance `this` inside its methods.

This is a **semantic difference**, not merely a compiler optimization.

## 20. A Decisive Case: Using `this` to Unregister a Callback

A useful case for choosing an anonymous class over a lambda is when a callback needs to pass **its own reference** into an API:

~~~java
void register(Runnable callback) { /* store the callback reference */ }
void unregister(Runnable callback) { /* remove the exact callback reference */ }

void install() {
    register(new Runnable() {
        @Override
        public void run() {
            unregister(this);
        }
    });
}
~~~

This is a **snippet** inside a class that provides actual `register` and `unregister` methods. `this` inside `run()` is the anonymous `Runnable`, so passing that reference to `unregister` is type-correct. If you mechanically change the callback to `() -> unregister(this)`, `this` will mean the **enclosing owner** where the lambda is written, not the callback itself; depending on the owner type, the code may fail to compile or remove the wrong registration.

**Safe approach when a lambda is needed:** keep a stable `Runnable listener` reference outside, and use that exact reference to register/unregister along the lifecycle; do not create a new lambda when unregistering. If the business logic has complex lifecycle/identity, a named class with `close()` or an explicit unsubscribe is usually easier to test. The lesson comparing scope and `this` already provided a program to observe the receiver; here the criterion is **the ability to preserve registration identity during refactoring**.

## 21. `super` and Inheritance Semantics

In an anonymous subclass of Base, `super.method()` calls the implementation from **superclass Base**.

In a lambda written in an instance method, `super`, when valid, refers to the lexical enclosing class's superclass (not “the superclass of the lambda object”).

Example:

~~~java
class Base {
    String label() {
        return "base";
    }
}

class Child extends Base {
    Runnable callback() {
        return () -> System.out.println(super.label());
    }
}
~~~

The lambda above is inside an instance method of Child and uses lexical `super`. Anonymous class:

~~~java
Runnable r = new Runnable() {
    public void run() {
        // super.label(); // Does not call Child's Base.label this way.
    }
};
~~~

In the anonymous Runnable implementation, the direct superclass in the class hierarchy is Object, which has no `label()`. To call the method of the outer Child's superclass in a valid context, you need the qualified syntax `Child.super.label()`, or an outer helper method with a clearer name.

## 22. Runnable Program: Anonymous super of a Base Class

Create **`SuperOverrideDemo.java`**:

~~~java
public class SuperOverrideDemo {
    static class Greeter {
        String greet() {
            return "Hello";
        }
    }

    public static void main(String[] args) {
        Greeter custom = new Greeter() {
            @Override
            String greet() {
                return super.greet() + ", Java";
            }
        };

        System.out.println(custom.greet());
        System.out.println("superclass Greeter=" +
                (custom.getClass().getSuperclass() ==
                        Greeter.class));
    }
}
~~~

~~~bash
javac -encoding UTF-8 SuperOverrideDemo.java
java SuperOverrideDemo
~~~

Stdout:

~~~text
Hello, Java
superclass Greeter=true
~~~

If converted to a lambda, it must implement a functional interface with a matching method; there is no longer an inheritance relationship with Greeter in the direct sense.

## 23. Target Typing: A Lambda Does Not Have a Standalone Type on Its Own

A lambda needs the compiler to know its functional interface target. Example:

~~~java
java.util.function.Function<String, Integer> len =
        text -> text.length();
~~~

The compiler uses `Function<String,Integer>` to infer the type of `text` and the return type.

Invalid:

~~~java
// Object obj = text -> text.length(); // Object is not a functional interface.
// var fn = text -> text.length();      // No target type.
~~~

Valid:

~~~java
var fn = (java.util.function.Function<String, Integer>)
        (text -> text.length());
~~~

Or simply assign directly to a Function declaration. Java `var` does not infer an arbitrary functional interface on its own from a lambda without a target.

### How Anonymous and Named Classes Differ

`new Runnable() {...}` has its own type at the expression because the `new` part states the interface/base type. `new NamedRunner()` also states the class name. A lambda depends more heavily on target typing.

## 24. Runnable Program: Target Typing and Function

Create **`TargetTypingDemo.java`**:

~~~java
import java.util.function.Function;

public class TargetTypingDemo {
    static void printLength(Function<String, Integer> length,
                            String value) {
        System.out.println(length.apply(value));
    }

    public static void main(String[] args) {
        Function<String, Integer> len = text -> text.length();

        printLength(len, "Java");
        printLength(text -> text.length(), "OpenAI");
    }
}
~~~

~~~bash
javac -encoding UTF-8 TargetTypingDemo.java
java TargetTypingDemo
~~~

Stdout:

~~~text
4
6
~~~

The method parameter `Function<String,Integer>` provides the target type for the lambda at the call site. Therefore, a lambda can be passed directly when the compiler can resolve the appropriate overload.

## 25. Overload Ambiguity: The Same Lambda Matches Two Functional Interfaces

If there are two unrelated functional interfaces with the same SAM shape:

~~~java
@FunctionalInterface
interface Left {
    String get();
}

@FunctionalInterface
interface Right {
    String get();
}

static void select(Left x) {}
static void select(Right x) {}
~~~

The expression `select(() -> "A")` can be ambiguous because both overloads accept a matching shape. A named class/anonymous class with an explicit target type usually avoids ambiguity at the call site.

Solution: declare a typed variable or cast the lambda to the intended functional interface.

## 26. Runnable Program: Resolving Overload with an Explicit Target

Create **`LambdaOverloadDemo.java`**:

~~~java
public class LambdaOverloadDemo {
    @FunctionalInterface
    interface Left {
        String get();
    }

    @FunctionalInterface
    interface Right {
        String get();
    }

    static void select(Left left) {
        System.out.println("left=" + left.get());
    }

    static void select(Right right) {
        System.out.println("right=" + right.get());
    }

    public static void main(String[] args) {
        // select(() -> "A"); // Ambiguous.

        select((Left) () -> "A");

        Right right = () -> "B";
        select(right);
    }
}
~~~

~~~bash
javac -encoding UTF-8 LambdaOverloadDemo.java
java LambdaOverloadDemo
~~~

Stdout:

~~~text
left=A
right=B
~~~

Do not blindly replace an anonymous class with a lambda at an overloaded call site without compiling and testing. Type inference and overload resolution can alter behavior/call binding or cause errors.

## 27. Method Reference: A More Concise Variant of a Lambda

If a lambda merely calls an existing method:

~~~java
java.util.function.Function<String, Integer> length =
        value -> value.length();
~~~

you can use:

~~~java
java.util.function.Function<String, Integer> length =
        String::length;
~~~

Common forms:

- `Type::staticMethod`
- `existingObject::instanceMethod`
- `Type::instanceMethod` (the receiver is an argument)
- `Type::new` (constructor reference)
- `ArrayType::new` (array constructor reference)

A method reference is still a **poly expression** that needs an appropriate functional target type. Not every multi-statement lambda body has a clear method-reference equivalent.

## 28. Runnable Program: Method Reference or Lambda?

Create **`MethodReferenceDecisionDemo.java`**:

~~~java
import java.util.List;
import java.util.function.Function;
import java.util.function.Supplier;

public class MethodReferenceDecisionDemo {
    public static void main(String[] args) {
        Function<String, Integer> size = String::length;
        Supplier<List<String>> empty = List::of;

        System.out.println("size=" + size.apply("Java"));
        System.out.println("empty=" + empty.get());

        Function<Integer, Integer> square = n -> n * n;
        System.out.println("square=" + square.apply(5));
    }
}
~~~

~~~bash
javac -encoding UTF-8 MethodReferenceDecisionDemo.java
java MethodReferenceDecisionDemo
~~~

Stdout:

~~~text
size=4
empty=[]
square=25
~~~

`String::length` is clearer than writing boilerplate again; `n -> n*n` is actual transformation logic, so a lambda is appropriate. `List::of` here is a method reference selecting the zero-argument overload based on the Supplier target, returning an immutable empty List.

## 29. Generic Typing and SAM: Do Not Let Raw Types Slip into the API

You should use a parameterized functional interface:

~~~java
java.util.function.Function<String, Integer> parse =
        Integer::parseInt;
~~~

Avoid raw `Function`, which loses compile-time generic checking and tends to cause runtime casts/unchecked warnings.

With a named implementation, the class can declare a type parameter:

~~~java
final class Identity<T>
        implements java.util.function.Function<T, T> {
    @Override
    public T apply(T value) {
        return value;
    }
}
~~~

A lambda does not have a named generic class declaration like Identity<T> on its own, but it can be used at invocations where the target generic type is known.

## 30. Runnable Program: Generic Named Class and Generic Factory Lambda

Create **`GenericChoiceDemo.java`**:

~~~java
import java.util.function.Function;

public class GenericChoiceDemo {
    static final class Identity<T> implements Function<T, T> {
        @Override
        public T apply(T value) {
            return value;
        }
    }

    static <T> Function<T, T> identityLambda() {
        return value -> value;
    }

    public static void main(String[] args) {
        Function<String, String> named = new Identity<>();
        Function<Integer, Integer> lambda = identityLambda();

        System.out.println(named.apply("Java"));
        System.out.println(lambda.apply(17));
    }
}
~~~

~~~bash
javac -encoding UTF-8 GenericChoiceDemo.java
java GenericChoiceDemo
~~~

Stdout:

~~~text
Java
17
~~~

A named type is reused in many places; a generic factory lambda can also be type-safe if the method/API provides a clear target type.

## 31. Checked Exceptions: Which Option Helps More?

None of the options removes checked-exception rules:

- A named implementation of Runnable.run() cannot arbitrarily add `throws IOException` if the contract does not allow it.
- An anonymous implementation of Runnable is the same.
- A lambda targeting Runnable cannot throw an unhandled checked IOException.
- If the target is `Callable<T>` (which allows `throws Exception`), the code can throw a checked exception according to the contract.

Example:

~~~java
java.util.concurrent.Callable<String> job =
        () -> {
            throw new java.io.IOException("missing");
        };
~~~

At the call site, `Callable.call()` declares `throws Exception`, so the caller must catch or declare it.

**Do not choose an anonymous class to “dodge the compiler”**. Design the functional interface/call contract properly or handle the exception at the boundary.

## 32. Runnable Program: Checked Exception with Callable

Create **`CheckedExceptionChoiceDemo.java`**:

~~~java
import java.io.IOException;
import java.util.concurrent.Callable;

public class CheckedExceptionChoiceDemo {
    public static void main(String[] args) {
        Callable<String> task =
                () -> { throw new IOException("missing"); };

        try {
            System.out.println(task.call());
        } catch (Exception ex) {
            System.out.println("error=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 CheckedExceptionChoiceDemo.java
java CheckedExceptionChoiceDemo
~~~

Stdout:

~~~text
error=missing
~~~

The same code can use an anonymous `new Callable<String>() { ... }` or a named class implementing Callable. The type contract determines which checked exceptions are valid.

## 33. Java 17: `final` and `sealed` Type Restrictions

An anonymous subclass cannot extend a **final class**:

~~~java
final class FinalService {
}

// FinalService service = new FinalService() {}; // Compile error.
~~~

A lambda also cannot directly extend FinalService because a lambda requires a functional interface.

With a **sealed class/interface** (Java 17), direct subclasses/implementations must follow the permits restrictions. An anonymous class is not automatically exempt from sealed rules:

~~~java
sealed interface Result permits Ok, Error {}

final class Ok implements Result {}

final class Error implements Result {}

// Result value = new Result() {}; // Cannot be a direct anonymous implementation.
~~~

If extensibility is needed, design permitted/non-sealed extension points or use composition; do not treat anonymous classes/lambdas as a way to bypass the closed model.

## 34. Anonymous Classes When an Interface Has Default Methods

A functional interface with default methods can still use a lambda:

~~~java
@FunctionalInterface
interface Greeting {
    String name();

    default String message() {
        return "Hello, " + name();
    }
}

Greeting lambda = () -> "Mai";
~~~

An anonymous class can also implement `name()` and override the default `message()` if custom logic is desired. If you need to override **multiple methods**, an anonymous or named class may be more suitable than a lambda because a lambda only provides the SAM implementation.

## 35. Runnable Program: Overriding a Default Method

Create **`DefaultMethodOverrideChoiceDemo.java`**:

~~~java
public class DefaultMethodOverrideChoiceDemo {
    @FunctionalInterface
    interface Greeting {
        String name();

        default String message() {
            return "Hello, " + name();
        }
    }

    public static void main(String[] args) {
        Greeting lambda = () -> "Mai";

        Greeting anonymous = new Greeting() {
            @Override
            public String name() {
                return "An";
            }

            @Override
            public String message() {
                return "Hi, " + name();
            }
        };

        System.out.println(lambda.message());
        System.out.println(anonymous.message());
    }
}
~~~

~~~bash
javac -encoding UTF-8 DefaultMethodOverrideChoiceDemo.java
java DefaultMethodOverrideChoiceDemo
~~~

Stdout:

~~~text
Hello, Mai
Hi, An
~~~

A lambda has no class body to override both name and message separately; to customize the behavior of multiple methods, use an anonymous/named class or change the contract.

## 36. Do `Object` Methods Make an Interface Lose SAM Status?

A functional interface can declare an abstract method matching a public instance method of Object and still remain functional under JLS rules, because these Object-method signatures are not simply counted as separate abstract contracts.

Example:

~~~java
@FunctionalInterface
interface Labeler {
    String label(String value);

    boolean equals(Object other);
}
~~~

The lambda only implements `label`; `equals` has its semantics through Object behavior/runtime implementation. You should not customize equals/hashCode of a lambda object because lambda identity/representation does not have guarantees you should rely on.

**If equality/identity is part of the business contract**, a named immutable value class or record holding data plus an explicit policy will be more suitable than a callback lambda.

## 37. Identity: Do Not Assume Lambda Caching

An anonymous class instance creation expression `new Interface() { ... }` creates a new object each time the expression executes (if creation succeeds). A named class `new Named()` also creates a new object.

A lambda **has no guarantee** that each evaluation creates a new object, or that two evaluations will always return the same object. The JVM may reuse instances, especially non-capturing lambdas, under Java language semantics.

Therefore:

~~~java
Runnable a = () -> {};
Runnable b = () -> {};
// Do not build a contract using a == b.
~~~

If lifecycle code needs **a specific handle to unsubscribe**, **store the exact callback reference that was registered**, regardless of whether it is a lambda, anonymous class, or named class.

Do not check `lambda.getClass().isAnonymousClass()` and conclude the object belongs to an anonymous class: lambda implementations have no such guarantee.

## 38. Runnable Program: Keeping the Exact Callback Reference

Create **`ListenerIdentityDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ListenerIdentityDemo {
    static final class Bus {
        private final List<Runnable> listeners = new ArrayList<>();

        void subscribe(Runnable listener) {
            listeners.add(listener);
        }

        void unsubscribe(Runnable listener) {
            listeners.remove(listener);
        }

        void publish() {
            for (Runnable listener : List.copyOf(listeners)) {
                listener.run();
            }
        }
    }

    public static void main(String[] args) {
        Bus bus = new Bus();
        Runnable listener = () -> System.out.println("event");

        bus.subscribe(listener);
        bus.publish();

        bus.unsubscribe(listener);
        System.out.println("unsubscribed");
        bus.publish();
    }
}
~~~

~~~bash
javac -encoding UTF-8 ListenerIdentityDemo.java
java ListenerIdentityDemo
~~~

Stdout:

~~~text
event
unsubscribed
~~~

Use the exact `listener` reference for both subscribe and unsubscribe. Rewriting `() -> System.out.println("event")` at the unsubscribe site may not point to the same registered object; do not rely on the identity of independent lambda expressions.

## 39. Class Names and Debugging/Logging

A named class has a clear source name, and stack traces usually make it easier to identify the implementation's responsibility. An anonymous class has a generated binary name that may contain the `$` character and a compiler-assigned sequence number. Lambda runtime representations can vary by JVM/implementation.

Do not build business logic using:

~~~java
callback.getClass().getName().contains("Lambda")
~~~

or by parsing `Outer$1`. Those generated names are unstable and are not an API contract.

**Tip:** If an important callback needs logging/metrics, attach an **explicit label/domain identifier** via a named class or wrapper, rather than inferring behavior from the runtime class name.

## 40. Scope and Reuse of a Named Class

A named class does not necessarily mean creating a **public top-level class**. You have multiple visibility levels:

- A top-level package-private class or public class in an appropriate file/module.
- A `private static nested class` used within the outer class.
- A `private inner member class` requiring an enclosing outer instance.
- A local named class inside a method/block.

### Streamlined Choices

If an implementation is used in only one method yet has multiple methods/fields, a **local named class** can be easier to read than a giant anonymous class. If an implementation is used across the class without needing outer state, choose a **private static nested class**. If the public API requires a class type, choose a **named accessible type** according to the package/module design.

Do not think in terms of “named class = adding lots of files”; choosing where to declare it helps balance scope and readability.

## 41. Runnable Program: Local Named Class Instead of a Long Anonymous Class

Create **`LocalNamedChoiceDemo.java`**:

~~~java
public class LocalNamedChoiceDemo {
    interface Report {
        String title();
        String body();
    }

    static Report build(String project) {
        class SimpleReport implements Report {
            private final String title;

            SimpleReport(String title) {
                this.title = title;
            }

            @Override
            public String title() {
                return title;
            }

            @Override
            public String body() {
                return "Project=" + project;
            }
        }

        return new SimpleReport("Summary");
    }

    public static void main(String[] args) {
        Report report = build("Java");
        System.out.println(report.title());
        System.out.println(report.body());
    }
}
~~~

~~~bash
javac -encoding UTF-8 LocalNamedChoiceDemo.java
java LocalNamedChoiceDemo
~~~

Stdout:

~~~text
Summary
Project=Java
~~~

SimpleReport is a local named class with a constructor and two methods; the implementation remains hidden behind the Report interface. It captures the effectively final parameter project while managing title through a constructor field.

## 42. Code with Multiple Nested Lambda Levels: Readability

Example functional pipeline:

~~~java
java.util.function.Function<String, java.util.function.Function<Integer, String>>
        repeat = text -> count -> text.repeat(count);
~~~

This is valid, but it can become hard to read as generic types, error handling, state, and branching grow. If the body turns into dozens of lines with nested conditionals, exception handling, and logging, **extract it into a named method** or a named class with a semantic title.

### Review Rules

Ask:

1. Looking at the call site, can you read its purpose in a few seconds?
2. If an exception is thrown, is the stack trace/handling location clear?
3. Are there hidden captured mutable dependencies?
4. Can it be tested independently?
5. Would a method reference or a short lambda make the logic clearer?
6. Does the contract need to be reused/extended?

The best expression is not necessarily the one with the fewest lines.

## 43. Refactoring an Anonymous Class to a Lambda: Safe Conditions

You can consider refactoring:

~~~java
Runnable callback = new Runnable() {
    @Override
    public void run() {
        perform();
    }
};
~~~

into:

~~~java
Runnable callback = () -> perform();
~~~

if the following conditions hold:

- The target is a **functional interface**.
- The anonymous class provides only the SAM implementation, with no additional overrides to keep.
- There are no anonymous-specific instance fields/initializers/helpers with behavior.
- The body does not rely on `this`/`super` with the anonymous receiver meaning.
- It does not depend on exact instance identity/class metadata/generation semantics.
- Capture/lifecycle/thread safety is preserved.
- Checked exceptions and overload target typing remain valid.

**You should add tests** before and after refactoring, especially if the callback is registered with a UI/executor or passed to overloaded methods.

## 44. Refactoring a Lambda to a Named Class: When Complexity Grows

Starting from:

~~~java
java.util.function.Predicate<Order> valid =
        order -> order.total() > 0;
~~~

This is an illustrative snippet; it requires an `Order` definition.

When business logic has many rules, metrics, config, and error messages, convert it to:

~~~java
final class OrderValidator
        implements java.util.function.Predicate<Order> {
    private final int minimum;

    OrderValidator(int minimum) {
        this.minimum = minimum;
    }

    @Override
    public boolean test(Order order) {
        return order.total() >= minimum;
    }
}
~~~

The named class has a constructor boundary, methods, and is easy to extend for testing. Alternatively, keep the functional interface while moving the lambda logic to a **named static method** and then using a method reference `Rules::isValid`. You are not required to choose a class every time logic grows by a few lines.

## 45. Case Study: Designing a Payment Policy with a Named Strategy

When behavior needs a name in the domain and validation:

Create **`StrategyChoiceDemo.java`**:

~~~java
public class StrategyChoiceDemo {
    interface Discount {
        int apply(int cents);
    }

    static final class PercentDiscount implements Discount {
        private final int percent;

        PercentDiscount(int percent) {
            if (percent < 0 || percent > 100) {
                throw new IllegalArgumentException("percent");
            }
            this.percent = percent;
        }

        @Override
        public int apply(int cents) {
            if (cents < 0) {
                throw new IllegalArgumentException("cents");
            }
            return cents - cents * percent / 100;
        }
    }

    public static void main(String[] args) {
        Discount permanent = new PercentDiscount(20);
        Discount promotion = cents -> cents - 50;

        System.out.println("permanent=" + permanent.apply(1000));
        System.out.println("promotion=" + promotion.apply(1000));
    }
}
~~~

~~~bash
javac -encoding UTF-8 StrategyChoiceDemo.java
java StrategyChoiceDemo
~~~

Stdout:

~~~text
permanent=800
promotion=950
~~~

The named PercentDiscount has the reusable invariant percent 0..100. The promotion lambda illustrates a one-off fixed adjustment; if it must handle negatives/capping/concurrency, it needs a stricter contract. **A short lambda does not automatically guarantee business correctness**.

## 46. Case Study: Multi-Method Callback Should Not Be Forced into a Lambda

If an interface has lifecycle methods:

~~~java
interface Listener {
    void onOpen();
    void onClose();
}
~~~

Use an anonymous class:

~~~java
Listener listener = new Listener() {
    public void onOpen() {
        System.out.println("open");
    }

    public void onClose() {
        System.out.println("close");
    }
};
~~~

Or a named class when the logic is large enough. A single lambda cannot be used because there are two abstract methods. If the library provides an adapter class or default implementations, an anonymous subclass or alternative functional hooks can make the code shorter, but **that is an API contract change**.

## 47. Runnable Program: Multi-Method Lifecycle Listener

Create **`LifecycleListenerDemo.java`**:

~~~java
public class LifecycleListenerDemo {
    interface Listener {
        void onOpen();
        void onClose();
    }

    static void simulate(Listener listener) {
        listener.onOpen();
        listener.onClose();
    }

    public static void main(String[] args) {
        Listener listener = new Listener() {
            @Override
            public void onOpen() {
                System.out.println("open");
            }

            @Override
            public void onClose() {
                System.out.println("close");
            }
        };

        simulate(listener);
    }
}
~~~

~~~bash
javac -encoding UTF-8 LifecycleListenerDemo.java
java LifecycleListenerDemo
~~~

Stdout:

~~~text
open
close
~~~

The anonymous class keeps the lifecycle logic at the call site. If multiple modules need the same implementation, a named Listener class helps avoid duplication.

## 48. Testing: Test Behavior Through the Interface, Not Form

If an API accepts `Function`, `Predicate`, `Runnable`, or a domain interface, **test observable behavior**:

- Correct inputs → outputs.
- Side effects/lifecycle matching the contract.
- Exception type/message on invalid input.
- Independence between instances when stateful.
- Thread safety when promised.
- No leaking of shared references.
- Constructor/initializers preserve invariants.
- Listener is unsubscribed properly.

Do not test `getClass().getName()` to force an implementation to be anonymous or a lambda unless the library itself defines a special reflection contract for a specific reason.

### Example of Testing Through an Interface

Create **`ChoiceContractTestDemo.java`**:

~~~java
import java.util.function.Function;

public class ChoiceContractTestDemo {
    static final class NamedPrefix implements Function<String, String> {
        private final String prefix;

        NamedPrefix(String prefix) {
            this.prefix = prefix;
        }

        @Override
        public String apply(String input) {
            return prefix + input;
        }
    }

    static void check(Function<String, String> f, String expected) {
        String result = f.apply("Java");
        if (!expected.equals(result)) {
            throw new AssertionError(expected + " != " + result);
        }
    }

    public static void main(String[] args) {
        check(new NamedPrefix("N:"), "N:");
    }
}
~~~

~~~bash
javac -encoding UTF-8 ChoiceContractTestDemo.java
java ChoiceContractTestDemo
~~~

**Note:** The snippet above intentionally keeps a **wrong test fixture**: the actual output is `N:Java` while expected is `N:`; running the program will throw an AssertionError. When writing real tests, expected must be `N:Java`. This snippet illustrates why you must test the observable result instead of just looking at the code. Fix the test case before using it in a project.

## 49. Runnable Example: Correct Contract Tests for All Three Forms

Create **`ThreeFormsContractDemo.java`**:

~~~java
import java.util.function.Function;

public class ThreeFormsContractDemo {
    static final class NamedPrefix implements Function<String, String> {
        private final String prefix;

        NamedPrefix(String prefix) {
            this.prefix = prefix;
        }

        @Override
        public String apply(String input) {
            return prefix + input;
        }
    }

    static void check(Function<String, String> formatter,
                      String expected) {
        String actual = formatter.apply("Java");
        if (!expected.equals(actual)) {
            throw new AssertionError(expected + " != " + actual);
        }
    }

    public static void main(String[] args) {
        Function<String, String> named = new NamedPrefix("N:");
        Function<String, String> anonymous =
                new Function<String, String>() {
                    @Override
                    public String apply(String input) {
                        return "A:" + input;
                    }
                };
        Function<String, String> lambda =
                input -> "L:" + input;

        check(named, "N:Java");
        check(anonymous, "A:Java");
        check(lambda, "L:Java");

        System.out.println("named PASS");
        System.out.println("anonymous PASS");
        System.out.println("lambda PASS");
    }
}
~~~

~~~bash
javac -encoding UTF-8 ThreeFormsContractDemo.java
java ThreeFormsContractDemo
~~~

Stdout:

~~~text
named PASS
anonymous PASS
lambda PASS
~~~

The three implementations have different source forms but share the same `Function<String,String>` type contract. Tests should measure **actual results**, not require type identity as an implementation detail.

## 50. Serialization and Long-Lived Contracts

Do not assume a lambda or anonymous class object has a stable serialized form, nor assume it implements `Serializable` by default.

- `Runnable`/`Function` do not extend Serializable on their own.
- A lambda can be serializable when the target type permits it, but format/compatibility/security is a separate contract.
- A named class has a more stable name, yet it does **not automatically become serializable**; it requires an explicit Serializable contract and a proper object graph.
- Captured/enclosing references may not be serializable.
- Persisting business intent should generally store **immutable command/DTO data**, not an arbitrary callback implementation.

If persistence or framework reflection is a primary requirement, design named types and schemas upfront instead of using anonymous classes/lambdas and relying on generated class names.

## 51. Performance and Allocation: Do Not Optimize by Guessing

Claims like “lambdas are faster than anonymous classes” or “named classes use more memory” are often stated as absolute rules. There is insufficient basis for that across all JVMs/JDKs/workloads.

- JVM JIT, escape analysis, inlining, and capture can affect the outcome.
- A non-capturing lambda may be reused, but there is no identity promise to rely on.
- Anonymous `new` has Java object creation semantics.
- State/lifetime/allocation of captured values matters greatly.
- Hot-loop API design and side effects can matter more than syntax.

**Recommendation:** Choose based on readability/correctness first; for truly performance-sensitive code, profile or run JMH benchmarks in the target environment. Do not change the implementation form merely because you guess it is faster.

## 52. API Boundaries: What Should the Caller Know?

A public API should usually not require a concrete anonymous class identity. If only behavior is needed, accept an interface:

~~~java
static void submit(Runnable job) {
    job.run();
}
~~~

The caller is free to pass:
- `new NamedJob()`;
- `new Runnable() { ... }`;
- `() -> ...`.

If the contract has multiple operations and a lifecycle, use a named domain interface or abstract class that is clearer than a generic Runnable. If the object has mutable state/invariants/business identity, a named concrete type is a sound design choice.

## 53. How to Recognize Code That Should Be Refactored

**Convert a lambda to a method reference** when the body simply forwards directly to the method and adds no logic that needs to be shown.

**Convert an anonymous class to a lambda** when it implements exactly the SAM, does not need the anonymous class's own state/this/super, and the semantics do not change.

**Convert a lambda to a named method/class** when the body is long, has many branches, validations, side effects, or unclear dependencies.

**Convert an anonymous class to a local named class** when you want a semantic name, constructor/state, or multiple instances sharing the same implementation inside a method.

**Convert a local named class to a static nested/top-level named class** when it needs to be reused in multiple places or tested independently.

**Do not convert just because “the style guide says every callback must be a lambda”.** Type restrictions and actual behavior decide.

## 54. Common Mistakes When Converting

| Refactoring Action | Common Mistake | How to Avoid |
| --- | --- | --- |
| Anonymous → lambda | `this` changes from anonymous to outer | Review the receiver; use an explicit self reference or another design |
| Anonymous → lambda | Loss of fields and instance initializers | Named class or explicit holder |
| Anonymous → lambda | Interface is not functional | Keep anonymous/named or change the API |
| Anonymous subclass → lambda | Lambdas cannot extend a class | Keep subclass or use composition |
| Lambda → method reference | Selecting a different method overload | Check target typing and test |
| Lambda → anonymous | Anonymous `this` is different | Do not copy the expression mechanically |
| Lambda → named class | Captured dependencies get turned into implicit globals | Pass them into constructor final fields |
| Named → anonymous | Loss of reuse and stable type name | Only apply for a one-off implementation |
| Named → lambda | Dropping validation/constructor semantics | Place validation at an equivalent boundary |
| Callback → lambda | Relying on lambda equality/identity | Store the callback reference |
| Callback → any form | Failing to unregister | Clear ownership/lifecycle |
| Refactoring an overload | Ambiguous target type | Explicit variable/cast, compile and test |
| Raw generics | Unchecked warnings/type safety | Parameterized interfaces |
| Changing Runnable → Callable | Different checked exceptions/call signature | Consider the contract and result type |
| Mutable state holder | Data race | Synchronization/immutable design |

## 55. Practical Selection Process

**Step 1 — Identify the contract to satisfy.** Is it a functional interface, an interface with multiple methods, or an abstract/concrete superclass?

**Step 2 — Determine the behavior's length and complexity.** A pure expression, multiple statements, helper methods, or domain invariants?

**Step 3 — Determine the state.** Stateless, per-instance mutable state, or capturing a shared dependency? Is constructor validation needed?

**Step 4 — Determine the scope of use.** A single call site or multiple methods/modules?

**Step 5 — Determine `this`/`super` semantics.** Is the callback object needed as the receiver? Is it necessary to call base class behavior?

**Step 6 — Check API overloads/generics/checked exceptions.** Does the lambda have a clear target type?

**Step 7 — Determine the lifecycle.** Can the callback outlive the owner? Will the exact instance be unsubscribed?

**Step 8 — Name the logic if it helps readability and debugging.** A named method/class is not a failure in conciseness.

**Step 9 — Write tests for observable behavior.** Specifically test state/repetition, exceptions, null, and type constraints.

**Step 10 — Only consider performance after profiling.**

## 56. Decision Diagram

~~~text
Need to implement a behavior?
    |
    +-- Must extend a class (abstract/concrete)?
    |       |
    |       +-- Yes --> Anonymous subclass if short, single-site;
    |                   named subclass if large state/reuse.
    |
    +-- Interface with multiple abstract methods?
    |       |
    |       +-- Yes --> Anonymous or named implementation.
    |
    +-- Functional interface with a single SAM?
            |
            +-- Body only calls an existing method?
            |       |
            |       +-- Yes --> Method reference (if clear).
            |
            +-- Own state, constructor, this, helpers?
            |       |
            |       +-- Yes --> Named or anonymous class.
            |
            +-- Reuse/cross-module/public stable type?
            |       |
            |       +-- Yes --> Named class or named helper method.
            |
            +-- Short, single-site, clear target type?
                    |
                    +-- Yes --> Lambda.
~~~

The diagram is a heuristic; performance, DI/frameworks, sealed types, and team conventions can all influence the choice. Language restrictions (lambdas only target functional interfaces, final/sealed subclass rules, checked exceptions) remain mandatory.

## 57. Exercise 1 — Choose Lambda or Anonymous?

A `Runnable` callback that only prints "done", with no state and no reuse.

**Suggested answer:** The lambda `() -> System.out.println("done")` because Runnable is a functional interface and the body is short. An anonymous class is still valid, but longer.

## 58. Exercise 2 — Abstract Class with One Method

An `abstract class Reader { abstract String read(); }` has one abstract method. Can you write `Reader r = () -> "A";`?

**Answer:** No. Reader is a **class**, not a functional interface. Use `new Reader() { @Override String read() { return "A"; } }` or a named subclass.

## 59. Exercise 3 — Interface with Two Abstract Methods

`interface Listener { void open(); void close(); }` requires implementing both.

**Answer:** An anonymous class or named class; a single lambda cannot be used directly because the interface is not functional. If the library wants lambdas, the API must be designed to accept two functional callbacks or a different adapter.

## 60. Exercise 4 — Named Class or Lambda?

A calculation policy used across multiple modules, needing to validate percentage 0..100 and having mutable per-customer config.

**Answer:** Usually choose a named class/interface design with an explicit constructor, config, and invariants. A lambda can work syntactically if the contract is a SAM, but ownership and validation become hard to see as state grows.

## 61. Exercise 5 — Anonymous `this`

~~~java
Runnable r = new Runnable() {
    public void run() {
        System.out.println(this.getClass().isAnonymousClass());
    }
};
~~~

**Answer:** Prints true when calling r.run(): `this` is the anonymous object. If converted to a lambda inside an instance method, `this` changes to the outer receiver; this is not a semantics-preserving refactoring.

## 62. Exercise 6 — Captured Mutable State

~~~java
int[] counter = {0};
Runnable r = () -> counter[0]++;
~~~

**Answer:** Valid if the reference variable counter is not reassigned, because the lambda captures the effectively final array reference and mutates an element. However, this is not automatically thread-safe; for shared concurrency, choose AtomicInteger or an explicit synchronized design.

## 63. Exercise 7 — Identity

Two lambda expressions written at two source locations both have the body `() -> {}`. Can you assert that `a == b` is false?

**Answer:** You should not rely on the identity of lambda evaluations. Lambda identity/reuse is an implementation detail permitted to vary flexibly; store the reference if identity is needed for lifecycle management.

## 64. Exercise 8 — Method Reference

How can `Function<String,Integer> f = s -> s.length();` be written?

**Answer:** `Function<String,Integer> f = String::length;`. A target type is required so the compiler knows the parameter and return types.

## 65. Exercise 9 — Overload

There are two overloads `select(Left)` and `select(Right)`, each interface having `String get()`. What can happen with `select(() -> "A")`?

**Answer:** Ambiguous. Use `select((Left) () -> "A")` or assign the lambda to a `Left` variable and pass it in. Do not blame it on “an invalid lambda”; the error is failing to disambiguate the overload target.

## 66. Exercise 10 — Constructor of an Anonymous Subclass

Base has a constructor `Base(int limit)` and no no-arg constructor. Is `new Base() { ... }` allowed?

**Answer:** No, you must provide matching args: `new Base(5) { ... }` and override the required methods. A lambda cannot replace extending Base if Base is a class.

## 67. Exercise 11 — Callback Needing Unsubscribe

A UI component registers `() -> handle()` with an EventBus and later wants to remove it.

**Answer:** Store the exact Runnable listener reference that was subscribed, and use the same reference to unsubscribe. Do not write a new lambda expression and assume it is guaranteed to equal the old callback.

## 68. Exercise 12 — Contract Testing

An API accepts `Predicate<String>`. Three implementations (named/anonymous/lambda) all return true when the String is not blank. What should be tested?

**Answer:** Test valid/blank/null inputs according to the contract, outputs and exceptions, and side effects if any. Do not test `getClass().getName()` to enforce an implementation style.

## 69. Common Mistakes

| Misconception | Fact |
| --- | --- |
| “Lambdas replace every anonymous class.” | Only when the target is a functional interface and the semantics match. |
| “One abstract method in an abstract class allows using a lambda.” | A lambda requires a functional **interface**. |
| “Anonymous classes can only implement interfaces.” | They can extend non-final concrete or abstract classes. |
| “Named classes are always public and require a separate file.” | There are top-level/package-private/nested/local forms. |
| “Lambdas have their own constructors and instance fields.” | They do not have a class body like named/anonymous classes. |
| “Effectively final means the object is immutable.” | It only restricts reassignment of the captured variable. |
| “Anonymous `this` and lambda `this` are the same.” | Anonymous has its own this; lambda has lexical this. |
| “Converting an anonymous class to a lambda always preserves behavior.” | State, this, identity, and target typing may differ. |
| “Lambdas do not need a target type.” | They need a functional interface target. |
| “`var f = x -> x;` always infers the type automatically.” | It lacks a functional target type. |
| “A lambda object is always new on every evaluation.” | Identity/reuse is not guaranteed that way. |
| “Lambdas are always faster.” | It depends on JVM/workload and requires benchmarking. |
| “A functional interface cannot have default methods.” | It can, as long as a SAM remains. |
| “An interface with multiple abstract methods can use a lambda.” | No. |
| “An interface method implementation can reduce public visibility.” | No. |
| “Anonymous classes have named constructors.” | No, only superclass constructor args and instance initializers. |
| “final/sealed restrictions do not apply to anonymous classes.” | They still apply. |
| “Method references and lambdas are always equivalent in every side effect.” | Evaluation/overloads and semantics must be checked. |
| “Registering a callback and forgetting to unregister is fine.” | It can keep the owner/resources reachable. |
| “Anonymous/named/lambda handle checked exceptions on their own.” | All follow the target/override contract. |
| “getClass().getName() is a stable business ID.” | Not for generated anonymous/lambda implementations. |
| “No contract tests are needed because the code is one line.” | The logic still needs verification. |

## 70. Final Checklist

- [ ] I can distinguish between a named class, an anonymous class, and a lambda expression.
- [ ] I know a lambda requires a functional interface target.
- [ ] I know `@FunctionalInterface` helps the compiler check the SAM.
- [ ] I know interface default/static methods do not break SAM on their own.
- [ ] I know a single-method abstract class is not a lambda target.
- [ ] I know an anonymous class can implement an interface or extend a class.
- [ ] I know concrete/final/sealed inheritance restrictions.
- [ ] I know a named class has clear constructors/invariants and reuse.
- [ ] I know an anonymous body can have fields/helper methods/initializers.
- [ ] I know a lambda block does not have anonymous instance fields.
- [ ] I can distinguish per-instance state from a captured mutable holder.
- [ ] I know captured locals must be final/effectively final.
- [ ] I understand a mutable referenced object can still be modified.
- [ ] I can distinguish anonymous `this` from lambda lexical this.
- [ ] I know `super` in an anonymous subclass differs from lambda lexical super.
- [ ] I know lambdas require target typing, including when using overloaded methods.
- [ ] I know a cast/typed variable can resolve overload ambiguity.
- [ ] I use a method reference when it is clearer than a lambda.
- [ ] I avoid raw generic functional interfaces.
- [ ] I do not treat lambda identity as stable.
- [ ] I store the listener reference for unsubscribing.
- [ ] I know checked exceptions depend on the interface/SAM contract.
- [ ] I know the type exposed in a public API matters more than syntax.
- [ ] I use a local named class when behavior is complex yet used only inside a block.
- [ ] I consider a static nested named class when reused internally within the outer class.
- [ ] I do not parse generated class names.
- [ ] I do not assume every lambda is faster than a named/anonymous class.
- [ ] I control the lifecycle and thread safety of captured references.
- [ ] I refactor guided by tests, not merely by line count.
- [ ] I can explain the stdout and compile errors in this lesson.

**Conclusion:** Choose a **lambda** when you need a short behavior for a **functional interface** with a clear target type and no need for its own instance state or inheritance. Choose an **anonymous class** when you need a one-off implementation with a class body, multiple interface methods, or overriding a **class** right at the call site. Choose a **named class** when the behavior has a large enough responsibility, is reused, requires constructors/invariants, a stable type/API, or an explicit lifecycle. **Form is only a tool**; the type contract, captured state, `this`/`super`, checked exceptions, ownership, and testability determine the right choice.
