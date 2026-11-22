# Comparing Anonymous Classes and Lambdas: Scope of Use and the Meaning of `this` in Java 17

An **anonymous class** and a **lambda expression** both allow you to place behavior directly where the program needs it, such as a `Runnable` callback, a `Comparator`, or a data-processing strategy. However, they are **not two completely equivalent ways of writing the same mechanism**.

- `new Runnable() { ... }` is actually an **expression that declares and instantiates an anonymous class**. Inside an instance method of the anonymous class, **`this` refers to the anonymous object**.
- `() -> ...` is a **lambda expression**, used when there is a **functional interface as the target type**. A lambda **does not create a new scope for `this`**: `this` retains the meaning of `this` in the lexical enclosing context where the lambda is written.
- Both can capture **`final`/effectively final** local variables or parameters, but name handling, new variable declarations, overloading, methods, state, and `super` have practical differences.

This lesson belongs to **Java core – class-object**, under the **Anonymous Classes** group. Its direct goal is **comparing the scope of use and `this`**, framed within Java **17+** knowledge. Each complete program is presented in a separate file with deterministic stdout; snippets with intentional compile-time errors are clearly marked.

## 1. Learning Objectives

After this lesson, you should be able to:

1. Recognize that `new Interface() { ... }` and `() -> ...` are two different kinds of expressions.
2. Choose a lambda for a **functional interface**; recognize when an anonymous class is still necessary.
3. Explain `this` in an **anonymous method**, a **lambda inside an instance method**, and a **lambda inside a static method**.
4. Distinguish between `Outer.this`, `this.field`, simple field names, and captured local variables.
5. Predict the impact of **shadowing**: an anonymous class opens a new class scope, whereas a lambda uses the same lexical scope close to the enclosing context.
6. Compare dedicated state in an anonymous object with state residing in an external object referenced by a lambda.
7. Understand that both require captured local variables/parameters to be final or effectively final.
8. Understand that a return in a lambda or an anonymous method does not itself terminate the enclosing method.
9. Distinguish target typing, overloading, `@Override`, checked exceptions, and the ability to override superclass methods.
10. Analyze maintenance cost, lifetime, concurrency, and misconceptions about runtime identity.

## 2. Two Syntaxes Side by Side

Anonymous class:

~~~java
Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println("anonymous");
    }
};
~~~

Lambda:

~~~java
Runnable task = () -> System.out.println("lambda");
~~~

These are **two valid snippets inside a method**; do not combine two declarations with the same name `task` into the same block.

Both can be assigned to `Runnable`, because Runnable has exactly one abstract method `void run()` for functional interface purposes. However, the conceptual steps are different:

| Question | Anonymous class | Lambda |
| --- | --- | --- |
| What do you write? | A class body without a source name, along with `new` | An expression providing a function body for a SAM |
| Target type | An interface or class that can serve as a valid supertype | Functional interface |
| Needs a new class body? | Yes | No class body is written |
| Can declare its own instance fields? | Yes | No |
| Can implement multiple abstract methods at once? | Yes, if all are implemented | No |
| `this` inside the body | Anonymous instance | `this` of the lexical enclosing context |
| `super` inside the body | Superclass of the anonymous instance when valid | Lexical enclosing context when valid |
| Use `@Override` on a method? | Yes | No method declaration to attach this annotation to |
| Capture local variables | Final/effectively final | Final/effectively final |
| Class extends an abstract class? | Possible, if the superclass and constructor are valid | No |
| Short expression for a callback | Usually longer | Usually shorter |
| Automatically runs the callback when created? | No | No |

**Not every interface is a functional interface.** A lambda is only valid when the target type has **one functional abstract method** (after Java's rules on methods from Object, generic signatures, etc.). The `@FunctionalInterface` annotation helps the compiler verify the contract, but it is **not required** for an interface to qualify as a lambda target.

## 3. Program 1 — Same Functionality, Two Ways of Writing

File **`AnonymousLambdaBasicsDemo.java`**:

~~~java
public class AnonymousLambdaBasicsDemo {
    static void execute(String label, Runnable action) {
        System.out.println("begin=" + label);
        action.run();
    }

    public static void main(String[] args) {
        Runnable anonymous = new Runnable() {
            @Override
            public void run() {
                System.out.println("hello from anonymous");
            }
        };

        Runnable lambda = () ->
                System.out.println("hello from lambda");

        execute("A", anonymous);
        execute("L", lambda);
        System.out.println("anonymous class="
                + anonymous.getClass().isAnonymousClass());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 AnonymousLambdaBasicsDemo.java
java AnonymousLambdaBasicsDemo
~~~

**Stdout:**

~~~text
begin=A
hello from anonymous
begin=L
hello from lambda
anonymous class=true
~~~

Two objects are provided under the `Runnable` interface. The `execute` method does not need to know how the implementation was written: it simply calls `run()` according to Runnable's contract.

`anonymous.getClass().isAnonymousClass()` returns true because the expression `new Runnable() { ... }` actually declares an anonymous class. **Do not infer in reverse** that a lambda must have the same runtime class shape as an anonymous class. Java specifies lambdas by their semantics, without promising a binary class name or a fixed implementation mechanism for applications to depend on.

## 4. Scope of Use: Lambdas Need a Functional Interface, Anonymous Classes Are More Flexible

An interface with **two abstract methods**:

~~~java
interface EventSink {
    void onEvent(String value);
    void onComplete();
}
~~~

You **can** use an anonymous class:

~~~java
EventSink sink = new EventSink() {
    @Override
    public void onEvent(String value) {
        System.out.println("event=" + value);
    }

    @Override
    public void onComplete() {
        System.out.println("complete");
    }
};
~~~

The two fragments above are **valid snippets** in appropriate declaration positions.

However, you cannot write a lambda `value -> System.out.println(value)` and assign it to EventSink, because this interface is **not a functional interface**. A lambda does not contain multiple method declarations to implement two abstract methods.

On the other hand, with functional interfaces such as `Runnable`, `Supplier<T>`, `Predicate<T>`, and `Comparator<T>`, both approaches can usually be used; the next selection criteria are the need for **state**, **`this`**, **multiple methods**, **multi-line logic**, and readability.

## 5. Program 2 — An Interface with Two Abstract Methods

File **`MultiMethodInterfaceDemo.java`**:

~~~java
interface EventSink {
    void onEvent(String value);
    void onComplete();
}

public class MultiMethodInterfaceDemo {
    static void publish(EventSink sink) {
        sink.onEvent("A");
        sink.onEvent("B");
        sink.onComplete();
    }

    public static void main(String[] args) {
        EventSink sink = new EventSink() {
            private int count;

            @Override
            public void onEvent(String value) {
                count++;
                System.out.println(count + ":" + value);
            }

            @Override
            public void onComplete() {
                System.out.println("total=" + count);
            }
        };

        publish(sink);
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 MultiMethodInterfaceDemo.java
java MultiMethodInterfaceDemo
~~~

**Stdout:**

~~~text
1:A
2:B
total=2
~~~

The anonymous class implements both methods itself and holds the `count` instance field. You **cannot** replace the `new EventSink() { ... }` part in this program with a single lambda because `EventSink` has two abstract methods.

If a lambda is needed, you must **redesign the API** to accept a different functional interface; there is no lambda syntax that creates two independent method bodies in a single construct.

## 6. Anonymous Classes Can Extend a Class; Lambdas Cannot

When an API accepts or expects a subclass of an abstract class, an anonymous class is the direct choice:

~~~java
abstract class Formatter {
    private final String prefix;

    Formatter(String prefix) {
        this.prefix = prefix;
    }

    protected String prefix() {
        return prefix;
    }

    abstract String format(String input);
}
~~~

You can create:

~~~java
Formatter formatter = new Formatter("OUT:") {
    @Override
    String format(String input) {
        return prefix() + input;
    }
};
~~~

These are **valid snippets** if placed in the same scope. The anonymous class extends Formatter, calls the `Formatter(String)` constructor, and then overrides the abstract method.

A lambda **cannot use the abstract class Formatter as its target type**. A lambda requires a functional interface, not a “class with exactly one abstract method”. This is a **type-kind** limitation, not merely a syntactic difference.

A `final class` also cannot be extended by an anonymous subclass, even when the class body is empty.

## 7. Program 3 — Anonymous Subclass Using `super`

File **`AnonymousSubclassDemo.java`**:

~~~java
class Greeting {
    private final String name;

    Greeting(String name) {
        this.name = name;
    }

    String text() {
        return "Hello " + name;
    }
}

public class AnonymousSubclassDemo {
    public static void main(String[] args) {
        Greeting greeting = new Greeting("An") {
            @Override
            String text() {
                return super.text() + "!";
            }
        };

        System.out.println(greeting.text());
        System.out.println("superclass="
                + greeting.getClass()
                        .getSuperclass().getSimpleName());
        System.out.println("anonymous="
                + greeting.getClass().isAnonymousClass());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 AnonymousSubclassDemo.java
java AnonymousSubclassDemo
~~~

**Stdout:**

~~~text
Hello An!
superclass=Greeting
anonymous=true
~~~

`super.text()` in the anonymous subclass calls the `Greeting` superclass method. **Do not apply the same explanation** to `super` inside a lambda: a lambda is not used to create a subclass of Greeting.

Turn large override code into a named class if it is reused, needs thorough testing, or has important state/invariants.

## 8. Core Focus: Which Object Is `this`?

Inside an **instance method** of a class `Outer`:

~~~java
class Outer {
    private final String name = "outer";

    Runnable anonymous() {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println(this.getClass()
                        .isAnonymousClass());
                System.out.println(Outer.this.name);
            }
        };
    }

    Runnable lambda() {
        return () -> {
            System.out.println(
                    this.getClass().getSimpleName());
            System.out.println(this.name);
        };
    }
}
~~~

This is a valid illustrative class, without a main method.

- `this` inside the **anonymous `run()`** is the object of the anonymous class. Because that object implements Runnable, `this` **is not Outer**.
- `Outer.this` inside the anonymous `run()` refers to the exact enclosing Outer object if the expression is created from an appropriate instance context.
- `this` inside the **lambda body** has the same meaning as `this` at the point where the lambda is written, which is the **Outer instance** in the two instance methods of the example.
- A lambda does not have a new `this` to express “the lambda object currently executing”.

This is a difference in **lexical scope**. It has nothing to do with whether the anonymous class is used as a callback: both can implement Runnable, yet `this` refers to different objects.

## 9. Program 4 — Checking `this` Without Guessing

File **`ThisBindingDemo.java`**:

~~~java
final class Controller {
    private final String name;

    Controller(String name) {
        this.name = name;
    }

    Runnable anonymousTask() {
        return new Runnable() {
            @Override
            public void run() {
                Object current = this;
                System.out.println("anonymous class="
                        + current.getClass().isAnonymousClass());
                System.out.println("anonymous outer="
                        + Controller.this.name);
            }
        };
    }

    Runnable lambdaTask() {
        return () -> {
            System.out.println("lambda this class="
                    + this.getClass().getSimpleName());
            System.out.println("lambda this name=" + this.name);
        };
    }
}

public class ThisBindingDemo {
    public static void main(String[] args) {
        Controller controller = new Controller("C1");
        controller.anonymousTask().run();
        controller.lambdaTask().run();
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 ThisBindingDemo.java
java ThisBindingDemo
~~~

**Stdout:**

~~~text
anonymous class=true
anonymous outer=C1
lambda this class=Controller
lambda this name=C1
~~~

In the lambda, `this.getClass()` is the class of **Controller**, not the class of some “lambda closure”. In the anonymous class, `Object current = this` points to the **anonymous object**, so `isAnonymousClass()` is true.

**Note:** use `Object current` if you want to analyze the runtime type more broadly, avoiding direct `instanceof` checks between classes that statically cannot have a common subtype. Here `Class.isAnonymousClass()` is used for clear, easily determinable observation.

## 10. Inside a `static` Method: Anonymous Classes Have `this`, Lambdas Do Not Automatically Have an Enclosing `this`

In a static method, there is no enclosing instance `this` of the class containing the method.

~~~java
class Utility {
    static Runnable makeAnonymous() {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println(this.getClass()
                        .isAnonymousClass());
            }
        };
    }

    static Runnable makeLambda() {
        return () -> System.out.println("hello");
    }
}
~~~

This is a valid illustrative class. The anonymous `run()` is an **instance method of the anonymous object**, so `this` inside that method is valid. However, in a lambda written inside a static method, **there is no enclosing `Utility.this`** to use.

Snippet that **intentionally does not compile** if placed inside a static method:

~~~java
// Runnable invalid = () -> System.out.println(this);
~~~

The error is not because Runnable or lambdas “never support this”. The error occurs because a lambda **inherits the lexical context**, and a static method **has no instance this**.

## 11. Program 5 — Comparison in a Static Context

File **`StaticContextThisDemo.java`**:

~~~java
public class StaticContextThisDemo {
    static Runnable anonymous() {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println("anonymous self="
                        + this.getClass().isAnonymousClass());
            }
        };
    }

    static Runnable lambda() {
        return () -> System.out.println("lambda from static");
    }

    public static void main(String[] args) {
        anonymous().run();
        lambda().run();
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 StaticContextThisDemo.java
java StaticContextThisDemo
~~~

**Stdout:**

~~~text
anonymous self=true
lambda from static
~~~

`static` is a property of the **method containing the expression**; it does not make the anonymous instance method static. Meanwhile, a lambda does not generate a new `this` of its own for the programmer to reference.

If a lambda needs a specific object, pass it as a parameter or capture a validly declared reference, instead of treating `this` as the lambda object.

## 12. `Outer.this` in an Anonymous Class and in a Lambda

An anonymous class in an instance context can use `Outer.this` to **explicitly refer to the enclosing object**. A lambda in the same instance context can also use `Outer.this` when that qualified this is valid in the lexical enclosing context; normally `this` already points to Outer itself, so writing `this.field` is clear enough.

Not just any lambda can use `Outer.this`. If a lambda is written in a static method that has no enclosing instance Outer, `Outer.this` is still invalid.

**Distinguish between the name and the receiver:**

| Expression | Inside an anonymous Runnable of Outer | Inside a lambda written in an instance method of Outer |
| --- | --- | --- |
| `this` | Anonymous object | Outer object |
| `Outer.this` | Outer object if the enclosing context is valid | Outer object if the qualified this is valid |
| `this.toString()` | ToString of the anonymous object | ToString of the Outer object |
| `this.field` | Field of the anonymous object if present | Field of the Outer object if present |
| `Outer.this.field` | Field of the Outer object | Field of the Outer object |

What matters is **which object is actually selected**, not merely whether a field is `private` or `public`. Java has private access rules for nested declarations, but **access permission** does not create a receiver when in a static context.

## 13. Program 6 — Outer Field and Same-Named Field

File **`FieldShadowingDemo.java`**:

~~~java
final class Panel {
    private final String label = "outer";

    Runnable anonymous() {
        return new Runnable() {
            private final String label = "anonymous";

            @Override
            public void run() {
                System.out.println("anonymous this=" + this.label);
                System.out.println("anonymous outer="
                        + Panel.this.label);
            }
        };
    }

    Runnable lambda() {
        return () -> {
            System.out.println("lambda this=" + this.label);
            System.out.println("lambda outer="
                    + Panel.this.label);
        };
    }
}

public class FieldShadowingDemo {
    public static void main(String[] args) {
        Panel panel = new Panel();
        panel.anonymous().run();
        panel.lambda().run();
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 FieldShadowingDemo.java
java FieldShadowingDemo
~~~

**Stdout:**

~~~text
anonymous this=anonymous
anonymous outer=outer
lambda this=outer
lambda outer=outer
~~~

The anonymous class creates its **own instance scope** containing the field `label="anonymous"`. A lambda **does not have a class body declaring its own `label` field**; `this.label` is the field of Outer Panel.

If an enclosing method has a local variable also named `label`, name lookup can select the local variable when using the simple name. In that case, `Panel.this.label` and `this.label` help specify the field on the object.

## 14. Shadowing Local Variables: A Lambda's Scope Is Tighter

A lambda **does not open an independent lexical scope like a class declaration where you can redeclare a local name already present in the enclosing scope**.

Snippet that **intentionally does not compile**:

~~~java
void invalid() {
    int value = 10;

    Runnable lambda = () -> {
        // int value = 20; // Cannot declare a duplicate of local value.
        System.out.println(value);
    };
}
~~~

The illustrative method above **compiles if the same-named line is kept commented out**; uncommenting it produces a duplicate declaration error. The outer `value` remains in scope inside the lambda body.

An anonymous class, by contrast, has the **scope of a separate class**. It can declare an instance field or parameter with the same name as the outer local value according to the lexical scope rules of nested classes:

~~~java
void allowed() {
    int value = 10;

    Runnable anonymous = new Runnable() {
        private int value = 20;

        @Override
        public void run() {
            System.out.println(this.value);
        }
    };

    anonymous.run();
}
~~~

This is a valid illustrative method when placed inside a class. Here `this.value` is the anonymous class field, not the local `value=10`. Redeclaring a field can make code harder to read; you should not reuse the same name without good reason.

**In summary:** a lambda uses the lexical scope close to the enclosing context; an anonymous class adds a **new class scope** containing its own fields/method parameters. This is the most clearly visible difference when the compiler reports the error “variable ... is already defined”.

## 15. Program 7 — Different Scope and Shadowing

File **`LexicalScopeDemo.java`**:

~~~java
public class LexicalScopeDemo {
    public static void main(String[] args) {
        int value = 10;

        Runnable anonymous = new Runnable() {
            private int value = 20;

            @Override
            public void run() {
                int local = 30;
                System.out.println("anonymous field="
                        + this.value);
                System.out.println("anonymous local=" + local);
            }
        };

        Runnable lambda = () -> {
            int additional = 40;
            System.out.println("lambda captured=" + value);
            System.out.println("lambda local=" + additional);
        };

        anonymous.run();
        lambda.run();
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 LexicalScopeDemo.java
java LexicalScopeDemo
~~~

**Stdout:**

~~~text
anonymous field=20
anonymous local=30
lambda captured=10
lambda local=40
~~~

The program does not abuse duplicate names for local variables inside the lambda. `additional` is a new name, so it is completely valid; `value` is captured and not reassigned.

To see the actual error, try adding **a single non-running line** `int value = 99;` inside the lambda body in an experimental copy; the compiler will reject the duplicate declaration. There is no need to change runtime behavior or try assigning the `value` variable with another statement to test the difference in scope.

## 16. Both Capture `final` or `effectively final` Local Variables

Despite differences in scope and `this`, anonymous classes and lambdas share the same constraint when reading **local variables or formal parameters** from the enclosing scope:

- The referenced variable must have a valid scope and be **definitely assigned**.
- For a local variable/parameter, the variable must be **final or effectively final** according to the JLS.
- **Reassigning** the variable after its initializer, `++`, `--`, compound assignment `+=`, etc. breaks the effectively final condition in normal situations.
- Writing the `final` keyword is not mandatory if the assignment pattern already satisfies effectively final.
- Both can be returned from a method and use the captured values later.

Illustrative pair of snippets:

~~~java
int number = 5;

Runnable anonymous = new Runnable() {
    @Override
    public void run() {
        System.out.println(number);
    }
};

Runnable lambda = () -> System.out.println(number);
~~~

This is valid code when placed inside a method where `number` is not reassigned.

If `number++;` is added in the method, **both** expressions are disallowed from capturing `number`. This is a **compile-time error**, not an error that only occurs when the callback runs.

## 17. Program 8 — Each Factory Call Captures Its Own Values

File **`CaptureBothFormsDemo.java`**:

~~~java
public class CaptureBothFormsDemo {
    static Runnable anonymous(String name) {
        int repeats = 2;

        return new Runnable() {
            @Override
            public void run() {
                for (int i = 0; i < repeats; i++) {
                    System.out.println("A:" + name + ":" + i);
                }
            }
        };
    }

    static Runnable lambda(String name) {
        int repeats = 2;
        return () -> {
            for (int i = 0; i < repeats; i++) {
                System.out.println("L:" + name + ":" + i);
            }
        };
    }

    public static void main(String[] args) {
        Runnable first = anonymous("An");
        Runnable second = lambda("Binh");

        first.run();
        second.run();
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 CaptureBothFormsDemo.java
java CaptureBothFormsDemo
~~~

**Stdout:**

~~~text
A:An:0
A:An:1
L:Binh:0
L:Binh:1
~~~

The `name` parameter and the local variable `repeats` of each method are not reassigned, so both are effectively final. The created objects/actions can run after `anonymous()` and `lambda()` return.

**Do not conflate** the two `repeats` variables from two invocations into a single shared static variable: each method call has an independent source of values, and the capturing expression follows the values of that specific call.

## 18. Capturing a Reference Does Not Mean Taking an Object Snapshot

If a local variable is a `StringBuilder`, `List`, or array, that variable being effectively final **only prevents reassigning the reference**. It does not prohibit other methods from modifying the object that the reference points to.

~~~java
StringBuilder text = new StringBuilder("A");

Runnable anonymous = new Runnable() {
    @Override
    public void run() {
        System.out.println(text);
    }
};

Runnable lambda = () -> System.out.println(text);
text.append("B");
~~~

This is a valid snippet inside a method. Both callbacks will see **AB** if run after `append`, because they hold a reference to the same mutable StringBuilder.

If you need a snapshot of the value at creation time, write `String frozen = text.toString();` and then capture `frozen`, rather than capturing the mutable builder.

If the data is shared across threads, final/effectively final **does not automatically guarantee visibility or atomicity of writes on the mutable object**.

## 19. Program 9 — Both Forms Observe the Same Mutable Object

File **`MutableCaptureComparisonDemo.java`**:

~~~java
public class MutableCaptureComparisonDemo {
    public static void main(String[] args) {
        StringBuilder shared = new StringBuilder("A");

        Runnable anonymous = new Runnable() {
            @Override
            public void run() {
                System.out.println("anonymous=" + shared);
            }
        };

        Runnable lambda =
                () -> System.out.println("lambda=" + shared);

        anonymous.run();
        lambda.run();

        shared.append("B");
        anonymous.run();
        lambda.run();

        String snapshot = shared.toString();
        Runnable frozen =
                () -> System.out.println("frozen=" + snapshot);
        shared.append("C");
        frozen.run();
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 MutableCaptureComparisonDemo.java
java MutableCaptureComparisonDemo
~~~

**Stdout:**

~~~text
anonymous=A
lambda=A
anonymous=AB
lambda=AB
frozen=AB
~~~

The difference between anonymous classes and lambdas regarding `this` **does not turn the shared variable into immutable data**. Both callbacks observe the StringBuilder across the `append` calls.

`frozen` captures a `String` independent of subsequent changes to the builder; it continues to print AB, not ABC.

## 20. Own State of an Anonymous Object and State Outside a Lambda

An anonymous class can **declare its own instance field** inside its body:

~~~java
java.util.function.IntSupplier supplier =
        new java.util.function.IntSupplier() {
            private int count;

            @Override
            public int getAsInt() {
                return ++count;
            }
        };
~~~

This is a valid snippet inside a method. `count` is a **field of the anonymous object**, and the effectively final local capture rule does not apply to it.

The lambda `() -> ++count` does not have its own `count` declared inside a class body. If `count` is an enclosing **local variable**, incrementing it causes the compiler to reject capturing it. However, a lambda can still use state in a **captured object**, a **field of the enclosing object**, or an explicitly designed **holder**.

A controlled alternative is `AtomicInteger` or a `Counter` class with clear methods. Do not use `int[] cell={0}` to “work around” final in multithreaded code without understanding thread safety.

## 21. Program 10 — Anonymous Class Has a Field, Lambda Uses an Explicit Holder

File **`StateOwnershipDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.IntSupplier;

public class StateOwnershipDemo {
    static IntSupplier anonymous() {
        return new IntSupplier() {
            private int count;

            @Override
            public int getAsInt() {
                return ++count;
            }
        };
    }

    static IntSupplier lambda() {
        AtomicInteger counter = new AtomicInteger();
        return () -> counter.incrementAndGet();
    }

    public static void main(String[] args) {
        IntSupplier a = anonymous();
        IntSupplier b = lambda();

        System.out.println("anonymous=" + a.getAsInt());
        System.out.println("anonymous=" + a.getAsInt());
        System.out.println("lambda=" + b.getAsInt());
        System.out.println("lambda=" + b.getAsInt());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 StateOwnershipDemo.java
java StateOwnershipDemo
~~~

**Stdout:**

~~~text
anonymous=1
anonymous=2
lambda=1
lambda=2
~~~

In the anonymous class, `count` is a private **instance field** of the anonymous object. In the lambda, `counter` is an effectively final local variable pointing to an **AtomicInteger object**; the `incrementAndGet()` method modifies the state of AtomicInteger rather than reassigning the counter reference.

These are **two different ways of managing state** that produce similar values; this does not prove that a lambda “has no state”. It simply does not have a class body for the programmer to declare fields/methods as with an anonymous class.

## 22. Inside a Loop: The Same Index Snapshot Rule

Neither may directly capture the basic-for index `i` when `i++` makes it not effectively final:

~~~java
// INTENTIONALLY DOES NOT COMPILE if uncommented:
for (int i = 0; i < 3; i++) {
    // Runnable invalid = () -> System.out.println(i);
}
~~~

An anonymous class is subject to the same restriction.

The correct way:

~~~java
for (int i = 0; i < 3; i++) {
    int index = i;

    Runnable anonymous = new Runnable() {
        @Override
        public void run() {
            System.out.println("A:" + index);
        }
    };

    Runnable lambda = () -> System.out.println("L:" + index);
    anonymous.run();
    lambda.run();
}
~~~

This is a valid snippet inside a method. Each iteration has an `index` variable assigned once in the body and not reassigned, so capturing it is valid.

An **enhanced for** loop such as `for (String word : words)` also usually allows capturing `word` if the code does not reassign that variable. You must not infer that every loop variable is not effectively final; you must look closely at the loop kind and how the variable is assigned.

## 23. Program 11 — Two Callbacks Holding Each Index

File **`LoopCaptureComparisonDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class LoopCaptureComparisonDemo {
    public static void main(String[] args) {
        List<Runnable> actions = new ArrayList<>();

        for (int i = 0; i < 2; i++) {
            int index = i;

            actions.add(new Runnable() {
                @Override
                public void run() {
                    System.out.println("anonymous=" + index);
                }
            });

            actions.add(() ->
                    System.out.println("lambda=" + index));
        }

        System.out.println("actions=" + actions.size());
        for (Runnable action : actions) {
            action.run();
        }
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 LoopCaptureComparisonDemo.java
java LoopCaptureComparisonDemo
~~~

**Stdout:**

~~~text
actions=4
anonymous=0
lambda=0
anonymous=1
lambda=1
~~~

Four callbacks were created first and executed afterward. Each anonymous/lambda pair captures the same index of the corresponding iteration. **Neither mechanism automatically references “the final value of i after the loop”.**

## 24. `return` in a Lambda and an Anonymous Method

A lambda with a block body and a value-returning target type can write `return` to return **the value of that execution of the lambda body**:

~~~java
java.util.function.IntUnaryOperator twice = value -> {
    return value * 2;
};
~~~

In an anonymous class, `return` returns the result from **the overridden instance method**:

~~~java
java.util.function.IntUnaryOperator twice =
        new java.util.function.IntUnaryOperator() {
            @Override
            public int applyAsInt(int value) {
                return value * 2;
            }
        };
~~~

Both fragments are valid snippets when placed inside a method; do not declare two `twice` variables in the same scope in real code.

**Neither `return` automatically returns from the enclosing method** that creates and returns the object. Nor can you use `break` inside a lambda body to exit a loop **outside the lambda**; jump statements must obey valid lexical targets.

An important difference in formulation: an anonymous class **defines the `applyAsInt` method**, whereas a lambda supplies a body matching the function type determined by the compiler from the target interface.

## 25. Program 12 — `return` Only Ends the Callback Invocation

File **`ReturnSemanticsDemo.java`**:

~~~java
import java.util.function.IntUnaryOperator;

public class ReturnSemanticsDemo {
    static IntUnaryOperator anonymous() {
        System.out.println("make anonymous");
        return new IntUnaryOperator() {
            @Override
            public int applyAsInt(int value) {
                if (value < 0) {
                    return 0;
                }
                return value + 1;
            }
        };
    }

    static IntUnaryOperator lambda() {
        System.out.println("make lambda");
        return value -> {
            if (value < 0) {
                return 0;
            }
            return value + 1;
        };
    }

    public static void main(String[] args) {
        IntUnaryOperator a = anonymous();
        IntUnaryOperator b = lambda();

        System.out.println("a=" + a.applyAsInt(-5));
        System.out.println("b=" + b.applyAsInt(2));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 ReturnSemanticsDemo.java
java ReturnSemanticsDemo
~~~

**Stdout:**

~~~text
make anonymous
make lambda
a=0
b=3
~~~

The `anonymous()` and `lambda()` methods print messages and return callbacks. Later when `applyAsInt(...)` runs, the `return` resides **inside the callback implementation**; it does not reach back to terminate `main()` early.

## 26. Target Typing: Why a Lambda Cannot Stand “Alone” Like `new Runnable`

An anonymous creation expression explicitly states the type after `new`:

~~~java
new Runnable() {
    @Override
    public void run() {
    }
}
~~~

A lambda, by contrast, does not carry a single source-level object type on its own; it requires a **target functional interface** from the context:

~~~java
Runnable r = () -> System.out.println("work");
~~~

The following lambda example **intentionally does not compile**:

~~~java
// Object invalid = () -> System.out.println("work");
~~~

Because `Object` **is not a functional interface**, the compiler has no target function type to convert the lambda directly into Object. To store it as an Object, create the lambda with an explicit target first and then upcast:

~~~java
Object value = (Runnable) () -> System.out.println("work");
~~~

This is a valid snippet inside a method: the cast provides the target type Runnable for the lambda, and the result is then assigned to Object.

For an anonymous class, `Object value = new Runnable() { ... };` is valid because the `new` expression creates an object of an anonymous class that implements Runnable and can be upcast to Object.

## 27. Program 13 — A Cast Provides the Target Type for a Lambda

Complete **`LambdaTargetTypeDemo.java`** file, runnable standalone on Java 17+:

~~~java
public class LambdaTargetTypeDemo {
    static void accept(Object value) {
        System.out.println("runnable=" + (value instanceof Runnable));
        if (value instanceof Runnable task) {
            task.run();
        }
    }

    public static void main(String[] args) {
        Object anonymous = new Runnable() {
            @Override
            public void run() {
                System.out.println("from anonymous");
            }
        };

        Object lambda = (Runnable) () ->
                System.out.println("from lambda");

        accept(anonymous);
        accept(lambda);
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 LambdaTargetTypeDemo.java
java LambdaTargetTypeDemo
~~~

**Exact stdout of the program above:**

~~~text
runnable=true
from anonymous
runnable=true
from lambda
~~~

The `(Runnable)` cast provides the target type for the lambda in the assignment expression to `Object`. Both the anonymous class and the lambda implement `Runnable`; the `instanceof` check and the two callbacks produce four deterministic output lines, independent of the implementation class name generated by the JVM.

## 28. Overloads and Target Types: Lambdas May Need Explicit Typing

If there are overloads accepting different functional interfaces, a lambda can:

- Select one overload because parameter types/return shapes are sufficiently distinct;
- Or **cause ambiguity** if multiple target function types are compatible.

For example:

~~~java
void use(Runnable task) {
    task.run();
}

void use(java.util.concurrent.Callable<String> task)
        throws Exception {
    System.out.println(task.call());
}
~~~

These are **method snippets**, placed inside a class.

The call `use(() -> "hi")` is compatible with `Callable<String>` (which returns String), not with `Runnable` (which does not allow an expression body yielding a String result in this case). However, a lambda body such as `() -> someVoidMethod()` follows different overload resolution rules, and overloads with the same arity/SAM shape can cause ambiguity.

When it is hard to read, **place it in a variable with a declared target type**:

~~~java
Runnable action = () -> System.out.println("work");
use(action);
~~~

Or use an explicit cast `use((Runnable) () -> ...)` if the API requires it.

With an anonymous class, the type `new Runnable() { ... }` is already right inside the creation expression, so the compiler generally has more type information from the outset.

## 29. Program 14 — Resolving Overloads with Explicit Types

File **`OverloadTargetDemo.java`**:

~~~java
import java.util.concurrent.Callable;

public class OverloadTargetDemo {
    static void use(Runnable action) {
        System.out.print("runnable=");
        action.run();
    }

    static void use(Callable<String> action)
            throws Exception {
        System.out.println("callable=" + action.call());
    }

    public static void main(String[] args)
            throws Exception {
        Runnable anonymous = new Runnable() {
            @Override
            public void run() {
                System.out.println("A");
            }
        };

        Runnable lambda =
                () -> System.out.println("L");

        use(anonymous);
        use(lambda);
        use((Callable<String>) () -> "C");
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 OverloadTargetDemo.java
java OverloadTargetDemo
~~~

**Stdout:**

~~~text
runnable=A
runnable=L
callable=C
~~~

Both `anonymous` and `lambda` are explicitly declared with the type Runnable, so `use(...)` selects the right overload. The cast on the last lambda explicitly specifies `Callable<String>`.

You should not infer from this example that every overload with a lambda requires a cast; it is a way to make code unambiguous when target types risk being ambiguous.

## 30. A Functional Interface Can Have default/static Methods

An interface is still a functional interface if it has **exactly one abstract method** under the SAM rule, even if it also has default or static methods.

~~~java
@FunctionalInterface
interface Transformer {
    String apply(String text);

    default String applyUpper(String text) {
        return apply(text).toUpperCase(
                java.util.Locale.ROOT);
    }
}
~~~

Both a lambda and an anonymous class can provide an implementation for `apply`:

~~~java
Transformer lambda = text -> "L:" + text;

Transformer anonymous = new Transformer() {
    @Override
    public String apply(String text) {
        return "A:" + text;
    }
};
~~~

These are valid snippets if `Transformer` has been declared. The `applyUpper` method is an **existing default method** on the interface; both objects can invoke it through the interface reference.

An anonymous class can **override a default method** if desired. A lambda body is not a class declaration with its own method overrides; to customize multiple methods, use an anonymous/named implementation or adjust the interface design.

## 31. Program 15 — Default Methods and Lambdas/Anonymous Classes

File **`DefaultMethodComparisonDemo.java`**:

~~~java
import java.util.Locale;

@FunctionalInterface
interface Transformer {
    String apply(String value);

    default String upper(String value) {
        return apply(value).toUpperCase(Locale.ROOT);
    }
}

public class DefaultMethodComparisonDemo {
    public static void main(String[] args) {
        Transformer anonymous = new Transformer() {
            @Override
            public String apply(String value) {
                return "A:" + value;
            }

            @Override
            public String upper(String value) {
                return "CUSTOM:" + apply(value);
            }
        };

        Transformer lambda = value -> "L:" + value;

        System.out.println("anonymous apply="
                + anonymous.apply("java"));
        System.out.println("anonymous upper="
                + anonymous.upper("java"));
        System.out.println("lambda apply="
                + lambda.apply("java"));
        System.out.println("lambda upper="
                + lambda.upper("java"));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 DefaultMethodComparisonDemo.java
java DefaultMethodComparisonDemo
~~~

**Stdout:**

~~~text
anonymous apply=A:java
anonymous upper=CUSTOM:A:java
lambda apply=L:java
lambda upper=L:JAVA
~~~

The anonymous class overrides both `apply` and the default method `upper`, while the lambda only supplies the SAM behavior `apply`; `upper` still runs the interface's default implementation.

Because `upper` uses `Locale.ROOT`, converting the string `"L:java"` to `"L:JAVA"` produces a consistent result independent of the machine's default locale.

## 32. Method References: A Third Option When Simply Forwarding to a Method

In addition to anonymous classes and lambdas, Java allows a **method reference** when the target functional interface is appropriate:

~~~java
Runnable lambda = () -> System.out.println("ready");
Runnable methodReference = System.out::println;
~~~

This is a syntax snippet, but `System.out::println` **is not suitable as a zero-argument Runnable** because `PrintStream.println` has a zero-argument overload and can match; when this Runnable runs, it merely prints a blank line. It does not have the same behavior as the lambda that prints "ready".

If you want true equivalence in the printed value, write:

~~~java
java.util.function.Consumer<String> a =
        value -> System.out.println(value);

java.util.function.Consumer<String> b =
        System.out::println;
~~~

Both Consumers accept a String and call println.

A method reference is like a lambda with respect to the **target functional interface**, except it has no lambda parameter body for you to write `this`. When using `this::method` inside an instance method, `this` still refers to the enclosing instance according to the lexical context.

There is no need to choose a method reference at all costs: if binding or overloading makes it hard for the reader to tell which method is called, an explicit lambda is often clearer.

## 33. Program 16 — Method Reference and Lambda with the Same Target Type

File **`MethodReferenceDemo.java`**:

~~~java
import java.util.function.Function;

public class MethodReferenceDemo {
    public static void main(String[] args) {
        Function<String, Integer> lambda =
                text -> text.length();

        Function<String, Integer> reference =
                String::length;

        System.out.println("lambda=" + lambda.apply("Java"));
        System.out.println("reference="
                + reference.apply("Java"));
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 MethodReferenceDemo.java
java MethodReferenceDemo
~~~

**Stdout:**

~~~text
lambda=4
reference=4
~~~

Both have the target type `Function<String,Integer>`; the compiler adapts the `int` return from `String.length()` to `Integer` via appropriate boxing.

The method reference here is a shorthand for forwarding to an existing method; there is no additional state, constructor, or separate `this` in the source.

## 34. `super` in a Lambda Is Lexical, Not the Superclass of a Lambda Object

In an anonymous subclass of a class, `super.method()` inside an anonymous method invokes the implementation from the anonymous class's superclass.

In a lambda written inside an **instance method of a subclass with a named superclass**, `super.method()` (when valid) is interpreted according to **the lexical context of the class containing the lambda**. It does not refer to the superclass of a lambda class that the JVM might use in its implementation.

Conceptual example:

~~~java
class Base {
    String label() {
        return "base";
    }
}

class Derived extends Base {
    Runnable action() {
        return () -> System.out.println(super.label());
    }
}
~~~

This is a valid illustrative class. When calling `new Derived().action().run()`, the lambda invokes `Base.label()` through Derived's `super`. That aligns with `this` inside the lambda referring to the Derived instance.

Do not use reflection to inspect which class the JVM generated in order to infer backward about a lambda's `super` or `this`. The lexical rules of Java source code are the accurate basis.

## 35. Program 17 — `super` in a Subclass's Lambda

File **`LexicalSuperDemo.java`**:

~~~java
class Parent {
    String name() {
        return "Parent";
    }
}

class Child extends Parent {
    @Override
    String name() {
        return "Child";
    }

    Runnable lambda() {
        return () -> {
            System.out.println("this=" + this.name());
            System.out.println("super=" + super.name());
        };
    }

    Runnable anonymous() {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println("outer="
                        + Child.this.name());
            }
        };
    }
}

public class LexicalSuperDemo {
    public static void main(String[] args) {
        Child child = new Child();
        child.lambda().run();
        child.anonymous().run();
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 LexicalSuperDemo.java
java LexicalSuperDemo
~~~

**Stdout:**

~~~text
this=Child
super=Parent
outer=Child
~~~

In the lambda, `this` and `super` correspond to the Child instance and Child's Parent implementation. In the anonymous Runnable, `Child.this` is used to call the exact enclosing Child instance.

If you write `super.name()` **directly** inside the anonymous Runnable, the superclass of the anonymous Runnable is typically Object, which has no `name()`; it does **not** automatically call `Parent.name()` of the enclosing Child. That is the exact difference to remember.

## 36. `equals`, Object Identity, and Runtime Implementation

An anonymous creation expression has `new` and a class body, so each successful evaluation of a new object creation yields a new object reference, according to Java rules.

With lambdas, **you should not assume** that evaluating the same lambda expression twice always produces two different identities. The JLS gives the implementation flexibility in allocating/reusing function objects. Therefore, **do not use `==` between lambda objects to make business decisions**.

Similarly:

- `getClass().getName()` of an anonymous object can contain a compiler-generated binary name; it is not stable like a business ID.
- The implementation class/name of a lambda is a JVM/runtime detail, not an API contract to serialize or store in a database.
- `toString()`, `hashCode()`, and object identity do not replace a business identifier.
- If you need to compare the configuration of two callbacks, keep **the configuration data in a value object with clear equality**, instead of hoping two executable objects will implement `equals` by their code body.

**Do not infer** that “lambdas are faster than anonymous classes in every case” just because lambdas can be optimized by the runtime. Profile the actual workload if performance is a requirement.

## 37. Program 18 — Identity of Two Anonymous Instances

File **`AnonymousIdentityDemo.java`**:

~~~java
public class AnonymousIdentityDemo {
    static Runnable anonymous(String text) {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println(text);
            }
        };
    }

    static Runnable lambda(String text) {
        return () -> System.out.println(text);
    }

    public static void main(String[] args) {
        Runnable first = anonymous("A");
        Runnable second = anonymous("B");
        Runnable third = lambda("C");

        System.out.println("anonymous distinct="
                + (first != second));
        System.out.println("anonymous same class="
                + (first.getClass() == second.getClass()));
        System.out.println("lambda Runnable="
                + (third instanceof Runnable));
        first.run();
        second.run();
        third.run();
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 AnonymousIdentityDemo.java
java AnonymousIdentityDemo
~~~

**Stdout:**

~~~text
anonymous distinct=true
anonymous same class=true
lambda Runnable=true
A
B
C
~~~

Two calls to `anonymous(...)` create different instances of the anonymous class declared in **the same expression** of the factory, so they have the same runtime class but different identities.

For the lambda, the program only checks **the Runnable contract**, without predicting the identity or implementation class chosen by the JVM. This is a durable way to write tests.

## 38. Scope of Impact of `this`: Callbacks Running on Another Thread

If a lambda is written inside an instance method and holds a reference to `this`, it can maintain **reachability** of the enclosing object as long as the callback is retained. An anonymous class created in an instance context can also be bound to the corresponding enclosing instance when it needs to use it.

However, **`this` does not change because the callback is run from another thread**. It still refers to the object according to the lexical/anonymous scope rules, and does not automatically become the running Thread.

To find the executing thread, use `Thread.currentThread()` — that is the **current thread**, distinct from the callback's `this` object.

Things to consider:

- A callback stored in a long-lived registry can keep objects reachable longer than expected.
- Capturing a mutable field/object does not create synchronization.
- If a lambda/callback has side effects inside `AtomicReference.updateAndGet`, the logic may be invoked multiple times due to CAS retries, causing repeated side effects.
- For listeners with a long lifecycle, there should be an unsubscribe/close policy when provided by the API.
- `final` on a reference does not make a mutable object thread-safe.

## 39. Program 19 — `this` Differs from the Current Thread

File **`CallbackThreadContextDemo.java`**:

~~~java
final class Service {
    private final String label = "service";

    Runnable lambda() {
        return () -> {
            System.out.println("lambda owner=" + this.label);
            System.out.println("worker thread="
                    + Thread.currentThread().getName());
        };
    }

    Runnable anonymous() {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println("anonymous owner="
                        + Service.this.label);
            }
        };
    }
}

public class CallbackThreadContextDemo {
    public static void main(String[] args)
            throws InterruptedException {
        Service service = new Service();
        Thread worker = new Thread(service.lambda(), "worker-1");
        worker.start();
        worker.join();
        service.anonymous().run();
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 CallbackThreadContextDemo.java
java CallbackThreadContextDemo
~~~

**Stdout (when the worker finishes normally):**

~~~text
lambda owner=service
worker thread=worker-1
anonymous owner=service
~~~

The lambda body runs on the thread with the name specified by the program itself, yet `this` is still the Service instance. Calling `worker.join()` ensures the two lines from the worker finish before main invokes the anonymous Runnable, making the output order deterministic.

**There is no rule** that “anonymous classes are always synchronous” or “lambdas are always asynchronous”. Threading depends on **the API invoking the callback**; both are simply ways of supplying behavior.

## 40. Exceptions and Method Signatures

An anonymous class implementing an interface method must adhere to the signature, checked exceptions, and visibility rules:

~~~java
java.util.concurrent.Callable<String> task =
        new java.util.concurrent.Callable<>() {
            @Override
            public String call() throws Exception {
                return "done";
            }
        };
~~~

Lambda:

~~~java
java.util.concurrent.Callable<String> task =
        () -> "done";
~~~

Both snippets are valid separately when placed inside a method. Both create a Callable whose `call()` returns String. If the body throws a **checked exception**, validity is checked against the `throws` clause of the corresponding abstract method and the target typing rules; a lambda does not automatically eliminate checked exceptions.

For Runnable, `run()` does not declare checked exceptions, so a checked IOException cannot be thrown outward without being handled inside the body, whether using an anonymous class or a lambda.

`@Override` only appears on a method declaration in an anonymous class; a lambda has no separate `run()` declaration to attach that annotation to.

## 41. Choosing the Form Based on Needs — Not Just Character Count

**Choose a lambda** when:

- The target type is genuinely a functional interface.
- You only need to implement a short behavior, without adding instance fields/methods.
- You want `this` to refer to the lexical enclosing instance, or simply do not need `this`.
- Functional composition (`map`, `filter`, `Comparator.comparing`, `Predicate.and`) makes the code natural.
- You want to focus on **behavior** rather than a class declaration.

**Choose an anonymous class** when:

- You need a subclass of a non-final superclass at the point of use.
- The interface has multiple abstract methods that need to be implemented.
- You need to override an interface's default method along with the abstract method.
- You want instance fields, an initializer, or helper methods inside a local object.
- You need `this` to point to the anonymous instance itself or `super` of the anonymous superclass.
- The implementation is short and used in only one place.

**Choose a named local/static nested/top-level class** when the implementation is complex, needs reuse, separate testing, explicit contract declarations, or risks obscuring surrounding logic with a long anonymous body.

There is no criterion that “lambdas are more modern so they are always right”. Choose based on **type contract, scope, state ownership, `this`, and readability**.

## 42. Common Mistakes

| Mistake | Why is it wrong? | How to fix it |
| --- | --- | --- |
| Using a lambda with an interface that has two abstract methods | It is not a functional interface | Anonymous/named class or change the API |
| Using a lambda to extend an abstract class | Lambdas only use a functional interface target | Anonymous subclass |
| Thinking `this` in an anonymous class is the enclosing object | `this` refers to the anonymous instance | `Outer.this` when valid |
| Thinking `this` in a lambda is the lambda object | A lambda keeps the lexical this | `this` is the enclosing instance in an instance context |
| Writing `this` inside a lambda in a static method | There is no lexical enclosing instance | Explicitly capture the dependency |
| Writing a local variable with the same name as an enclosing local in a lambda body | Lambdas do not allow that kind of redeclaration | Use a new name |
| Reassigning a captured variable | Not effectively final | Create a new local snapshot |
| Capturing a StringBuilder and expecting a snapshot | The mutable object still changes | `toString()`/immutable copy |
| Updating a local counter with `counter++` inside a lambda | Captured local is not effectively final | Use a field/holder with a clear contract |
| Thinking anonymous creation automatically calls run | `new` differs from method invocation | Call `run()` or pass it to an executor |
| Using `==` to compare lambda business behavior | Identity/runtime representation is not guaranteed | Compare state/config by value |
| Relying on `Outer$1` or the lambda class name | Compiler/JVM implementation details | Use interfaces and type contracts |
| Printing stdout that depends on thread scheduling | Output can be nondeterministic | `join`/synchronization when teaching |
| Assuming lambdas are always thread-safe | Capturing does not synchronize mutable state | Appropriate synchronization and ownership |
| Missing public on the `run()` method in an anonymous Runnable | Implementing an interface method must be public | `@Override public void run()` |
| Lambda missing a target type when assigned to Object | Object is not a functional interface | Cast to Runnable or use a typed variable |
| Treating `super` in a lambda as belonging to a generated lambda class | `super` uses the lexical context | Analyze the enclosing class |
| Anonymous body becomes too long | Hard to debug and maintain | Extract into a named class |

## 43. Guide to Analyzing a Code Snippet Yourself

When encountering a lambda or anonymous class, analyze it in order:

1. **What is the target type?** Interface or superclass? Is it a functional interface?
2. **Source form:** `new T(args) { ... }`, `() -> ...`, `T::method`?
3. **What methods/fields/init blocks does the anonymous body have?** Does it have sufficient override/constructor access?
4. **Which lexical context is the lambda body in?** Static method or instance method?
5. **What does `this` inside the body refer to?** Anonymous object or enclosing instance?
6. **Is `Outer.this` valid?** Is the enclosing instance selected properly?
7. **Is there shadowing?** Do the anonymous class's fields hide outer fields? Does the lambda improperly redeclare a local name?
8. **What local variables are captured?** Are they definitely assigned and effectively final?
9. **Are mutable references aliased?** Does state continue changing after the callback is created?
10. **When does the callback run?** Creating the object does not execute it automatically; who invokes the SAM method?
11. **Are there checked exceptions, return statements, or overload ambiguities?**
12. **How many times is an expression evaluated?** With anonymous classes, each `new` creates a different instance; lambda identity is not used as a contract.
13. **Does the thread/context change?** That does not change the lexical `this` binding, though it affects mutable state.
14. **Which expression form is clearest for the reader?** Lambda/anonymous/named class.

Always check **compile-time validity before figuring out stdout**. If code lacks a target functional interface or uses `this` in a static context, you should not guess a runtime result for a program that does not compile.

## 44. Practice Exercises

**Question 1.** `Runnable a = new Runnable(){ public void run(){} };` and `Runnable b = () -> {};` are similar in the API invoked; how do they differ in type definition?

**Question 2.** An interface has two abstract methods. Should you choose a lambda or an anonymous class? Why?

**Question 3.** An abstract class has one abstract method. Can you assign a lambda directly to that abstract class type?

**Question 4.** An anonymous class created inside `Controller.action()` reads `this`. Which object does `this` refer to?

**Question 5.** A lambda created inside `Controller.action()` reads `this`. Which object does `this` refer to?

**Question 6.** A lambda created inside a static method reads `this.name`. Is it valid?

**Question 7.** Can an anonymous class created inside a static method call `this.getClass()` inside its instance method?

**Question 8.** An anonymous class has `private int count` and increments count inside run. Does that violate effectively final?

**Question 9.** A lambda reads `int count=0` in the enclosing method and increments `count++`. Is that allowed?

**Question 10.** Capture an effectively final `StringBuilder` and then call append elsewhere. Will the anonymous class/lambda read the old or new value?

**Question 11.** Can an anonymous body declare a field with the same name as a local variable in the enclosing method? Can a lambda body declare a local variable with that same name?

**Question 12.** Can `this.label` inside an anonymous class and `Outer.this.label` read two different fields?

**Question 13.** Which field does `this.label` in an instance-method lambda refer to?

**Question 14.** Must evaluating the same anonymous `new ... { ... }` twice return the same instance?

**Question 15.** Is comparing `lambda1==lambda2` appropriate for making business decisions?

**Question 16.** Method `use(Object)` is called with the literal `() -> run()` without a cast. Why might it be invalid?

**Question 17.** When two overloads both accept functional interfaces with compatible signatures, how can lambda ambiguity be resolved?

**Question 18.** Does `return 1;` inside a lambda body cause the enclosing method to terminate and return 1 as well?

**Question 19.** If an interface has one abstract method and one default method, can a lambda use the default method?

**Question 20.** If you need to override both the abstract method and the default method, which approach is more direct?

**Question 21.** Inside a subclass method, which class's superclass does `super.name()` placed inside a lambda target?

**Question 22.** When an anonymous Runnable created inside a subclass calls `super.name()` directly, does it automatically select the enclosing subclass's superclass?

**Question 23.** If the callback is executed from another thread, does the lambda's `this` automatically become the Thread object?

**Question 24.** Why does capturing a mutable ArrayList in an anonymous class/lambda require separate concurrency attention?

**Question 25.** When can a method reference replace a lambda to simplify code?

**Question 26.** Can `@Override` be used on a lambda body? How is it useful on an anonymous method?

**Question 27.** A callback is registered in a long-lived registry and captures the enclosing service. What lifecycle risk exists?

**Question 28.** If an implementation has many fields, many methods, and is hundreds of lines long, is an anonymous class still the only choice?

### Answers and Explanations

1. Both provide a Runnable, but the anonymous form declares an anonymous class + object; the lambda is an expression of the target functional interface.
2. An anonymous/named class; a lambda requires a functional interface with one abstract method.
3. No. A lambda cannot use an abstract class as its target type.
4. `this` is the anonymous-class object.
5. `this` is the Controller instance according to the lexical context.
6. No, because a static method has no enclosing this.
7. Yes. `this` is valid inside an instance method of the anonymous object.
8. No. `count` is a field of the anonymous object, not a captured local variable.
9. No. A captured local `count` must be final/effectively final.
10. The new value of the StringBuilder after mutation; capturing a reference does not snapshot its contents.
11. You can declare a field in an anonymous class according to scope rules; a lambda does not allow redeclaring a local name that is already in the scope of the enclosing method.
12. Yes. `this.label` belongs to the anonymous object; `Outer.this.label` belongs to the enclosing Outer.
13. A field of the lexical enclosing instance if the name is valid, not a field of a source-level lambda object.
14. No; each successful `new` creates a new object.
15. No. The runtime may reuse lambda objects; identity does not describe business functionality.
16. Object is not a functional interface, so it does not provide a target type for the lambda.
17. Assign the lambda to a variable of a specific functional interface or cast the lambda to an explicit target.
18. No. `return` returns from the invocation of the functional method body.
19. Yes. An object/function of the target type can use the default method on the interface.
20. An anonymous/named class, because it can declare both method implementations/overrides.
21. The superclass of the lexical enclosing subclass, not a generated lambda class.
22. No. `super` inside an anonymous body refers to the superclass of the anonymous class itself; use `Outer.this` or an appropriate API.
23. No. The binding of `this` does not depend on the executing thread.
24. Final/effectively final only governs the reference variable; it does not synchronize writes on a mutable list.
25. When simply forwarding to an existing method and the target function signature matches, for example `String::length`.
26. A lambda does not declare a method, so it has no `@Override`; in an anonymous class, `@Override` helps the compiler validate the method properly.
27. The callback keeps the enclosing object reachable for a long time, which can cause object retention and requires an unregister/close policy.
28. No. A local/static nested/top-level named class improves readability and testability.

## 45. Code Review Checklist

- Is the lambda's target type genuinely a functional interface?
- Does the anonymous expression choose a valid, non-final interface or superclass?
- If an interface has multiple abstract methods and an anonymous class is used, are all implementations provided?
- When referring to `this`, is it clear whether it is the anonymous object or the enclosing object?
- If the expression is written in a static context, has lexical `this` inside a lambda been avoided?
- Is `Outer.this` used properly where an enclosing instance exists?
- Is any local name inside the lambda redeclared in the same lexical scope?
- Are captured variables final/effectively final and definitely assigned?
- Does a captured mutable object introduce aliasing/concurrency risks?
- If dedicated state is needed, are fields/holders clearly designed?
- Is `return` inside the callback distinguished from returning from the enclosing method?
- Are lambda target typing and overload ambiguity understood?
- Is guessing the class name/identity of a lambda implementation avoided?
- Is using `==` on callbacks as value equality avoided?
- With `super`, is the right lexical superclass or anonymous superclass targeted?
- If the code relies on default interface methods, is the override difference understood?
- If a method reference is used, is overload binding unambiguous?
- Are methods/callbacks invoked at the right time as determined by the API?
- For concurrency, is appropriate synchronization/immutable state used?
- For long-lived callbacks, have reachability and cleanup been considered?
- Has Java 17 compilation been tested and stdout checked to ensure deterministic ordering/behavior?
- If the implementation is large, has a named class been considered instead of an overly long anonymous body?

## 46. Official Java 17 Documentation

- [JLS 17 §15.9.5 — Anonymous Class Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9.5): anonymous class body, constructors, and `new` syntax.
- [JLS 17 §15.27 — Lambda Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27): lambda body, target type, and lexical semantics.
- [JLS 17 §15.27.2 — Lambda Body](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27.2): body and statement rules.
- [JLS 17 §15.27.3 — Type of a Lambda Expression](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27.3): functional interface target typing.
- [JLS 17 §9.8 — Functional Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.8): SAM definition and valid interfaces.
- [JLS 17 §6.4 — Shadowing and Obscuring](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.4): duplicate names and scope.
- [JLS 17 §8.1.3 — Inner Classes and Enclosing Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.3): enclosing objects.
- [JLS 17 §15.8.3 — this](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.8.3): the `this` expression in a valid context.
- [JLS 17 §15.8.4 — Qualified this](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.8.4): `Outer.this`.
- [JLS 17 §4.12.4 — final Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): captured variables and effectively final.
- [JLS 17 §15.12 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12): overload resolution.
- [Java SE 17 — FunctionalInterface](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/FunctionalInterface.html): annotation checking the SAM contract.
- [Java SE 17 — Runnable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runnable.html): callback interface returning no result.
- [Java SE 17 — Callable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Callable.html): callback interface with a result and checked exceptions.
- [Java SE 17 — AtomicInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): purposeful management of a mutable counter.
- [Java SE 17 — Class.isAnonymousClass](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#isAnonymousClass()): identifying an anonymous runtime class.

**Summary:** When implementing a short callback for a functional interface, a **lambda** is usually concise and keeps `this` tied to the lexical enclosing context. When you need an object that implements multiple methods, has its own instance fields, overrides a default method, or extends a class, an **anonymous class** is more suitable; `this` in its instance method refers to the **anonymous object**. Both obey the final/effectively final capture rule, yet they differ clearly in **name declaration scope, target typing, inheritance, and object identity**. Before choosing, answer three questions: *what is the target type, which object must `this` point to, and how long will the state/callback live?*
