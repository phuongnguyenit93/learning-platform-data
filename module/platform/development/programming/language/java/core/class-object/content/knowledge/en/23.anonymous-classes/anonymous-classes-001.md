# Declaring and Creating an Anonymous Object in One Expression — Java 17+

In Java, an **anonymous class** allows you to **declare a class without its own name and immediately create an object of that class using the same expression**. Instead of naming a class that implements `Runnable` or a class that extends `Base`, you write the class body right after `new`.

Example:

~~~java
Runnable action = new Runnable() {
    @Override
    public void run() {
        System.out.println("Xin chào từ anonymous class");
    }
};
action.run();
~~~

This is **valid Java code when placed inside a method**. The expression `new Runnable() { ... }` simultaneously:

1. Declares a **new anonymous class** that implements the `Runnable` interface.
2. Defines the required `run()` method.
3. Creates an **instance** of that anonymous class.
4. Returns a reference that can be assigned to a variable of type `Runnable`.

There is no named class such as `MyRunnable` in the source. Yet there is still **an actual class at runtime** and there is still **an actual object**, which can have fields, instance initializers, identity, and methods.

This lesson belongs to **Java core – class-object**, in the **Anonymous Classes** group. The focus is on the syntax and mechanism of *declaration + instantiation in one expression*, followed by the two forms `new Interface() { ... }` and `new Base(args) { ... }`, scope, the `this` expression, data capture, lifetime, comparison with lambdas/local classes, compilation errors, and how to apply them.

The runnable examples use **Java 17+**. Each standalone program includes a file name, `javac`/`java` commands, and a specific expected stdout. Snippets that intentionally cause errors are **marked as non-compiling** and must not be confused with complete runnable programs.

## 1. Why Are Anonymous Classes Needed?

Suppose an application needs to pass an object with `run()` behavior to an API that accepts a `Runnable`.

The approach with a dedicated name:

~~~java
class GreetingTask implements Runnable {
    @Override
    public void run() {
        System.out.println("Hello");
    }
}
~~~

In another location:

~~~java
Runnable action = new GreetingTask();
action.run();
~~~

The two snippets above are **illustrative** and can be combined within the appropriate scope. If the `GreetingTask` type is reused in multiple places, this approach is very clear.

However, if the implementation only makes sense **right at the creation point**, you can write:

~~~java
Runnable action = new Runnable() {
    @Override
    public void run() {
        System.out.println("Hello");
    }
};
action.run();
~~~

**Meaning:** there is no need to name a class that is only used once; the behavior is placed close to where the callback is configured/provided.

**It does not mean** an anonymous class “has no class” or is merely a function. It is an **actual class** declared anonymously, and each time the instantiation expression `new ... { ... }` is normally evaluated, a new instance is created.

## 2. Two Foundational Syntaxes to Master

**Implementing an interface:**

~~~java
SomeInterface value = new SomeInterface() {
    @Override
    public void requiredMethod() {
        // Implementation body conforming to the interface contract.
    }
};
~~~

This is an **illustrative syntax template**, not standalone runnable code because `SomeInterface` has not been defined. When the interface exists, the constructor arguments after the interface name in the form above must be an **empty pair of parentheses**: an interface has no constructor to call. The body must provide implementations for the unsatisfied abstract methods.

**Creating an anonymous subclass of an existing class:**

~~~java
SomeBase value = new SomeBase(constructorArgument) {
    @Override
    public String description() {
        return "Phiên bản được tùy biến";
    }
};
~~~

This is also a **syntax template**, assuming `SomeBase` is not final, has a constructor accepting `constructorArgument`, has an overridable `description()` method, and all required abstract methods are implemented.

In the second form, the expression invokes a matching constructor of the **superclass**, then performs the initialization of the anonymous subclass.

In both forms, **the `{ ... }` after `new` is a class body**, not a separate statement block after a `new` statement.

## 3. One Expression Both Declares the Class and Creates the Instance

A named class is declared in one place and used with `new` in another:

~~~java
class CounterTask implements Runnable {
    @Override
    public void run() {
        System.out.println("work");
    }
}

Runnable task = new CounterTask();
~~~

The lines above are **illustrative**, in which the task variable needs to be placed inside an appropriate method/initializer. The `CounterTask` declaration creates a **named type** that is referenced later by that name.

Whereas in:

~~~java
Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println("work");
    }
};
~~~

the `new Runnable() { ... }` part both **defines** the anonymous implementation and **creates** the instance.

**Exact breakdown of a call:**

~~~text
Runnable task = new Runnable() { ... };
                └──────────── expression ──────────┘
                ├─ target superclass/interface: Runnable
                ├─ class body: defines run()
                ├─ compiler generates an anonymous class
                └─ new creates object, returns a reference of Runnable-compatible type
~~~

Because an anonymous class has no **source-level simple name**, code elsewhere cannot write `new TênLớpVôDanh()` to re-instantiate that exact same class by an ordinary Java source name.

## 4. Complete Program 1 — Creating and Calling an Anonymous Runnable

Create the file **`AnonymousRunnableDemo.java`**:

~~~java
public class AnonymousRunnableDemo {
    public static void main(String[] args) {
        System.out.println("before");

        Runnable first = new Runnable() {
            @Override
            public void run() {
                System.out.println("first action");
            }
        };

        Runnable second = new Runnable() {
            @Override
            public void run() {
                System.out.println("second action");
            }
        };

        first.run();
        second.run();

        System.out.println("same object=" + (first == second));
        System.out.println("first anonymous="
                + first.getClass().isAnonymousClass());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 AnonymousRunnableDemo.java
java AnonymousRunnableDemo
~~~

**Exact stdout:**

~~~text
before
first action
second action
same object=false
first anonymous=true
~~~

`first` and `second` point to **two instances**, created from **two separate anonymous class declarations**. The body of each anonymous class provides an implementation of `Runnable.run()`.

`first.run()` is a normal call through an interface reference; Java selects the implementation on the actual object. The `Class.isAnonymousClass()` method lets you observe that the corresponding runtime class is an anonymous class.

**Note:** `new Runnable() { ... }` **does not call `run()` automatically**. `run()` only executes when you call it or pass the object to an API that actually invokes that method (for example, an appropriate scheduler).

## 5. Assigning to a Variable, Passing Directly as an Argument, Returning from a Method

An anonymous class is an **object-creation expression**, so it can appear in places where an appropriate object expression is accepted:

**Assigning to a variable:**

~~~java
Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println("A");
    }
};
~~~

**Passing directly to a method:**

~~~java
execute(new Runnable() {
    @Override
    public void run() {
        System.out.println("B");
    }
});
~~~

In the second snippet, the `execute(Runnable)` method is assumed to exist; this is a **snippet inside a method**, not a standalone program.

**Returning from a method:**

~~~java
static Runnable createTask() {
    return new Runnable() {
        @Override
        public void run() {
            System.out.println("C");
        }
    };
}
~~~

This is a **valid method when placed inside a class**. The caller receives the result under the `Runnable` interface; it does not need to know the bytecode name of the anonymous class.

**Calling a method immediately on the result:**

~~~java
new Runnable() {
    @Override
    public void run() {
        System.out.println("D");
    }
}.run();
~~~

This is valid code when placed at a statement position inside a method. **There is no need to store it in a variable** if the object is only used once right there.

## 6. Complete Program 2 — Three Positions Using an Anonymous Expression

Create the file **`AnonymousExpressionPositionsDemo.java`**:

~~~java
public class AnonymousExpressionPositionsDemo {
    static void execute(Runnable task) {
        System.out.println("execute begins");
        task.run();
    }

    static Runnable create(String message) {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println("created=" + message);
            }
        };
    }

    public static void main(String[] args) {
        Runnable variable = new Runnable() {
            @Override
            public void run() {
                System.out.println("variable");
            }
        };
        variable.run();

        execute(new Runnable() {
            @Override
            public void run() {
                System.out.println("argument");
            }
        });

        Runnable returned = create("done");
        returned.run();
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 AnonymousExpressionPositionsDemo.java
java AnonymousExpressionPositionsDemo
~~~

**Stdout:**

~~~text
variable
execute begins
argument
created=done
~~~

All three anonymous expressions create objects normally. Passing the object to a parameter or returning it via `return` is just a way of moving the **reference**; it does not cause the class body to be redeclared under a new name.

The `create(String message)` method also illustrates **parameter capture**: the anonymous body uses `message`, an effectively final parameter because it is not reassigned. Capture is explained in greater depth in a later section.

## 7. Anonymous Implementation Must Satisfy the Interface Contract

When writing:

~~~java
Runnable value = new Runnable() {
    @Override
    public void run() {
        System.out.println("ok");
    }
};
~~~

the compiler checks that the anonymous class implements all abstract methods it is responsible for implementing. `Runnable` has one abstract method `run()`, so the example is sufficient.

For an interface with **two abstract methods**:

~~~java
interface Observer {
    void onNext(String value);
    void onDone();
}
~~~

an anonymous class implementing Observer must implement both `onNext` and `onDone` (except for abstract implementation rules from a superclass where applicable; an anonymous class itself cannot be declared abstract).

**Invalid if only one method is implemented:**

~~~java
// INTENTIONALLY NON-COMPILING SNIPPET:
Observer incomplete = new Observer() {
    @Override
    public void onNext(String value) {
        System.out.println(value);
    }
    // Missing onDone().
};
~~~

This is a compile-time error; there is no stdout to simulate. Another error is misspelling the method name/signature: `@Override` helps the compiler detect that the method you wrote does not actually override the expected method.

## 8. Complete Program 3 — Multi-Method Interface and Its Own State

Create the file **`AnonymousObserverDemo.java`**:

~~~java
interface Observer {
    void onNext(String value);
    void onDone();
}

public class AnonymousObserverDemo {
    static void emit(Observer observer) {
        observer.onNext("start");
        observer.onNext("finish");
        observer.onDone();
    }

    public static void main(String[] args) {
        Observer observer = new Observer() {
            private int received;

            @Override
            public void onNext(String value) {
                received++;
                System.out.println("event#" + received + "=" + value);
            }

            @Override
            public void onDone() {
                System.out.println("total=" + received);
            }
        };

        emit(observer);
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 AnonymousObserverDemo.java
java AnonymousObserverDemo
~~~

**Exact stdout:**

~~~text
event#1=start
event#2=finish
total=2
~~~

The anonymous class has an **instance field `received`**, and two instance methods. This is an important difference from using a lambda: a lambda only directly provides an implementation for **one functional interface method**, and does not declare a class body containing multiple methods/instance fields like the one above.

An anonymous class is suitable when a local implementation needs **multiple callbacks** or **its own state tied to an object**. If the callback is actually executed from multiple threads, the `received++` field is still not automatically thread-safe.

## 9. Anonymous Class Inheriting from a Superclass

In addition to interfaces, an anonymous class can also **extend a valid non-final class**:

~~~java
abstract class Message {
    private final String receiver;

    Message(String receiver) {
        this.receiver = receiver;
    }

    protected String receiver() {
        return receiver;
    }

    abstract String render();
}
~~~

An object can be created as follows:

~~~java
Message message = new Message("An") {
    @Override
    String render() {
        return "Gửi tới " + receiver();
    }
};
~~~

These are **valid definitions/snippets when placed in their corresponding contexts**. In the expression `new Message("An") { ... }`:

1. `Message` is the selected superclass.
2. `("An")` provides the argument for the matching constructor of Message.
3. `{ ... }` defines an anonymous subclass of Message, implementing the abstract `render()` method.
4. `new` creates an object of the anonymous subclass, which can be assigned to a reference of type Message.

You must not write `implements InterfaceX` after the anonymous class body as in a named class declaration. The anonymous creation expression already specifies **one** class or interface type after `new`; inheriting/implementing additional relationships is determined through that type.

## 10. Complete Program 4 — Passing Arguments to a Superclass Constructor

Create the file **`AnonymousSuperclassDemo.java`**:

~~~java
abstract class Greeting {
    private final String name;

    Greeting(String name) {
        this.name = name;
    }

    protected final String name() {
        return name;
    }

    abstract String text();
}

public class AnonymousSuperclassDemo {
    public static void main(String[] args) {
        Greeting greeting = new Greeting("An") {
            @Override
            String text() {
                return "Xin chào, " + name();
            }
        };

        System.out.println(greeting.text());
        System.out.println("anonymous="
                + greeting.getClass().isAnonymousClass());
        System.out.println("superclass="
                + greeting.getClass()
                        .getSuperclass().getSimpleName());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 AnonymousSuperclassDemo.java
java AnonymousSuperclassDemo
~~~

**Stdout:**

~~~text
Xin chào, An
anonymous=true
superclass=Greeting
~~~

`Greeting` is an abstract class and **cannot** be instantiated directly with `new Greeting("An")` without an anonymous class body providing sufficient implementations. In the example, the anonymous subclass implements `text()`; the `Greeting(String)` constructor initializes the `name` field.

**Distinction to note:** the reference type in the source is Greeting, while the runtime type is an anonymous subclass. An anonymous class has no constructor **that you declare with its own name**, yet construction still takes place and the superclass constructor is still called according to Java rules.

## 11. No Named Constructor for an Anonymous Class

Because an anonymous class has no source-level simple name, you **cannot declare a constructor such as `AnonymousName(...)`** inside its body.

To supply initial data, the following are commonly used:

- **Superclass constructor arguments**, for example `new Base(10) { ... }`.
- **Instance field initializer**, for example `private final int initial = 10;`.
- **Instance initializer block**, for example `{ log("init"); }`.
- **Capturing final/effectively final variables** from the enclosing scope where appropriate.
- **Factory method** wrapping the creation expression to validate/prepare parameters beforehand.

Example:

~~~java
Runnable task = new Runnable() {
    private final String message = "start";

    {
        System.out.println("anonymous initializer");
    }

    @Override
    public void run() {
        System.out.println(message);
    }
};
~~~

This is a valid snippet inside a method. When `new Runnable() { ... }` is evaluated, the initializer runs during object creation; `task.run()` only runs later if the caller invokes it.

**Do not confuse an instance initializer with the run() method**: the initializer runs **at creation time**; `run()` runs **when called**. Avoid calling overridable methods from a constructor/initializer while the subclass is still incomplete, as this can cause code to run on a partially initialized object.

## 12. Complete Program 5 — Superclass Constructor and Instance Initializer

Create the file **`AnonymousInitializationDemo.java`**:

~~~java
abstract class Seed {
    private final int base;

    Seed(int base) {
        this.base = base;
        System.out.println("base constructor=" + base);
    }

    protected final int base() {
        return base;
    }

    abstract int result();
}

public class AnonymousInitializationDemo {
    public static void main(String[] args) {
        Seed value = new Seed(10) {
            private final int offset = 5;

            {
                System.out.println("anonymous init=" + offset);
            }

            @Override
            int result() {
                return base() + offset;
            }
        };

        System.out.println("result=" + value.result());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 AnonymousInitializationDemo.java
java AnonymousInitializationDemo
~~~

**Exact stdout:**

~~~text
base constructor=10
anonymous init=5
result=15
~~~

When creating an object, Java executes the **construction chain** through the appropriate superclass. In the example, the Seed constructor prints the first line; the anonymous subclass initializer reads the already-initialized `offset` and prints the second line. After the new expression returns the object, `result()` is called and prints 15.

**The `Seed(10)` constructor is not a constructor of the anonymous class named by you**. It is the superclass initialization path that the anonymous subclass uses.

## 13. An Anonymous Class's Own Instance Fields and Methods

An anonymous class can declare:

~~~java
Runnable counter = new Runnable() {
    private int times;

    private void log() {
        System.out.println("run#" + times);
    }

    @Override
    public void run() {
        times++;
        log();
    }
};
~~~

This is a valid snippet inside a method. `times` is an instance field **belonging to the anonymous object**, not a local variable of the method containing the expression.

Another variable pointing to the same `counter` object will observe the same internal state; creating **another object** by evaluating the creation expression again (in a factory or a loop) provides new instance state.

**External access:** when the reference is declared as `Runnable`, only methods available through `Runnable` (and Object) can be called directly according to the static type. The private helper `log()` does not become part of Runnable's API just because the anonymous class defines it.

## 14. Complete Program 6 — State Persisting Across Multiple Calls

Create the file **`AnonymousStateDemo.java`**:

~~~java
import java.util.function.IntSupplier;

public class AnonymousStateDemo {
    static IntSupplier counter(int start) {
        return new IntSupplier() {
            private int current = start;

            @Override
            public int getAsInt() {
                current++;
                return current;
            }
        };
    }

    public static void main(String[] args) {
        IntSupplier first = counter(10);
        IntSupplier second = counter(10);

        System.out.println("first#1=" + first.getAsInt());
        System.out.println("first#2=" + first.getAsInt());
        System.out.println("second#1=" + second.getAsInt());
        System.out.println("first#3=" + first.getAsInt());
        System.out.println("same=" + (first == second));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 AnonymousStateDemo.java
java AnonymousStateDemo
~~~

**Stdout:**

~~~text
first#1=11
first#2=12
second#1=11
first#3=13
same=false
~~~

Each call to `counter(10)` evaluates the anonymous creation expression and creates a new **IntSupplier object** with its own `current` field.

`start` is a parameter of the `counter` method, which is **captured** because it is effectively final; whereas `current` is an instance field and is allowed to change each time `getAsInt()` is called.

**Note:** the `getAsInt()` method here has no synchronization; if multiple threads call the same supplier concurrently, `current++` can race. The fact that the anonymous class has no name does not affect Java's concurrency rules.

## 15. What Does `this` Point to Inside an Anonymous Class?

Inside an instance method of an anonymous class, `this` is **the anonymous-class object itself**, not the enclosing object.

If the `new ... { ... }` expression is located inside an instance method of a class `Outer`, `Outer.this` can point to the enclosing Outer object when the context permits.

~~~java
class Screen {
    private final String label = "outer";

    Runnable makeTask() {
        return new Runnable() {
            private final String label = "anonymous";

            @Override
            public void run() {
                System.out.println(this.label);
                System.out.println(Screen.this.label);
            }
        };
    }
}
~~~

This is a valid illustrative class, without a main yet. `this.label` retrieves the field of the anonymous object; `Screen.this.label` retrieves the private field of the enclosing Screen. There is no need to make the outer field public because access is allowed under the nesting rules.

The anonymous class **is not automatically a subclass of Screen**: it implements Runnable. The lexical nesting relationship and the inheritance relationship are two different concepts.

## 16. Complete Program 7 — Shadowing Between the Anonymous Object and the Outer Object

Create the file **`AnonymousThisDemo.java`**:

~~~java
final class Page {
    private final String label;

    Page(String label) {
        this.label = label;
    }

    Runnable action() {
        return new Runnable() {
            private final String label = "anonymous";

            @Override
            public void run() {
                System.out.println("this=" + this.label);
                System.out.println("outer=" + Page.this.label);
                System.out.println("anonymous="
                        + this.getClass().isAnonymousClass());
            }
        };
    }
}

public class AnonymousThisDemo {
    public static void main(String[] args) {
        Page page = new Page("home");
        Runnable action = page.action();
        action.run();
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 AnonymousThisDemo.java
java AnonymousThisDemo
~~~

**Stdout:**

~~~text
this=anonymous
outer=home
anonymous=true
~~~

`Page.this` refers to the exact Page object on which `action()` was called, whereas `this` inside the `run()` method refers to the anonymous Runnable.

If the creation expression is inside a **static method** and there is no valid enclosing Page instance, `Page.this` is not available. In that case, you need to pass a Page reference explicitly if the anonymous object must access instance state.

## 17. Capturing Local Variables or Parameters: `final` and `effectively final`

An anonymous class can use local variables and parameters from the enclosing scope when they are **final or effectively final** and properly initialized.

~~~java
static Runnable printTimes(String message) {
    int repeats = 2;

    return new Runnable() {
        @Override
        public void run() {
            for (int i = 0; i < repeats; i++) {
                System.out.println(message);
            }
        }
    };
}
~~~

This is a valid illustrative method when placed inside a class. `message` is a parameter and `repeats` is a local variable: neither is reassigned, so both are effectively final.

**Invalid** if the code has the anonymous body read `count` while the method also reassigns count:

~~~java
// INTENTIONALLY NON-COMPILING:
int count = 1;
Runnable action = new Runnable() {
    @Override
    public void run() {
        System.out.println(count);
    }
};
count++;
~~~

Because `count++` updates the captured local variable, the compiler rejects it. Placing the update **after** the anonymous expression does not bypass the compile-time condition.

To normalize input, you should write `String normalized = input.trim();` and capture `normalized` instead of reassigning the parameter variable `input` itself.

## 18. Complete Program 8 — Capture and Lifetime After the Method Returns

Create the file **`AnonymousCaptureDemo.java`**:

~~~java
public class AnonymousCaptureDemo {
    static Runnable greet(String raw, int times) {
        if (raw == null || times < 0) {
            throw new IllegalArgumentException("invalid argument");
        }
        String message = raw.trim();

        return new Runnable() {
            @Override
            public void run() {
                for (int i = 0; i < times; i++) {
                    System.out.println(message + "#" + i);
                }
            }
        };
    }

    public static void main(String[] args) {
        Runnable first = greet(" An ", 2);
        Runnable second = greet(" Binh ", 1);

        first.run();
        second.run();
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 AnonymousCaptureDemo.java
java AnonymousCaptureDemo
~~~

**Stdout:**

~~~text
An#0
An#1
Binh#0
~~~

The Runnables still run after `greet` has returned. Java guarantees that the captured values remain usable, even though the local stack frame of the method invocation has ended.

**Do not infer** that the anonymous object holds a local variable that can be reassigned elsewhere. It is allowed to hold **the value of the captured variable**; if that value is a reference to a mutable object, the state inside the object can still change through aliases.

## 19. A Final Reference Does Not Make the Object It Points To Immutable

An example:

~~~java
StringBuilder text = new StringBuilder("A");

Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println(text.toString());
    }
};

text.append("B");
task.run();
~~~

This is a valid snippet inside a method, printing `AB`. The local variable `text` remains effectively final because it **is not reassigned**, even though the `StringBuilder` is modified with `append`.

Distinguish between the two:

| Operation | Does it break the reference's effectively final status? |
| --- | --- |
| `text = new StringBuilder(...)` | Yes |
| `text.append("x")` | No |
| `list.add("x")` | No |
| `array[0] = 5` | No |
| `index++` when capturing index | Yes |
| `final int constant = 5;` | Cannot reassign constant |

An anonymous class **does not automatically create an immutable snapshot** of the target object. If you need the content to stay fixed, convert the builder to a `String` before capturing; if you need multi-threaded shared mutable state, use synchronization or appropriate concurrency primitives.

## 20. Complete Program 9 — Capturing a Mutable Reference

Create the file **`AnonymousMutableCaptureDemo.java`**:

~~~java
public class AnonymousMutableCaptureDemo {
    public static void main(String[] args) {
        StringBuilder source = new StringBuilder("A");

        Runnable reader = new Runnable() {
            @Override
            public void run() {
                System.out.println("value=" + source);
            }
        };

        reader.run();
        source.append("B");
        reader.run();

        String snapshot = source.toString();
        Runnable frozen = new Runnable() {
            @Override
            public void run() {
                System.out.println("snapshot=" + snapshot);
            }
        };

        source.append("C");
        frozen.run();
        reader.run();
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 AnonymousMutableCaptureDemo.java
java AnonymousMutableCaptureDemo
~~~

**Stdout:**

~~~text
value=A
value=AB
snapshot=AB
value=ABC
~~~

Reader holds a reference to the same `StringBuilder`, so it observes the mutations. Frozen holds `String snapshot`, an immutable value created at the moment `source` had the content AB. Subsequent modifications to source do not affect snapshot.

**Concurrency note:** `StringBuilder` is not guaranteed to be thread-safe. Capturing an effectively final reference does not automatically protect operations when that object is accessed concurrently.

## 21. Loops and Each Evaluation of the Object-Creation Expression

The `new Runnable() { ... }` expression can be evaluated multiple times (for example inside a `for` loop), creating multiple **instances** of **the same anonymous class declaration** when it is the same source expression.

With `for (int i = 0; i < 3; i++)`, the variable `i` is not effectively final because of `i++`. You cannot capture `i` directly in the anonymous body. A snapshot variable is needed for each iteration:

~~~java
for (int i = 0; i < 3; i++) {
    int index = i;

    tasks.add(new Runnable() {
        @Override
        public void run() {
            System.out.println(index);
        }
    });
}
~~~

This is a valid snippet when `tasks` is a collection of Runnable with appropriate imports. Each execution of the loop body creates a new `index` with the corresponding value; it is effectively final and can be captured.

Subtle points:

- **The class declaration** resides at the same source code location inside the loop.
- **Each new** still creates a different instance.
- The instances can share the same runtime class while holding **different captured values**.
- To test `getClass()==`, you must use **the same anonymous class expression**, not two expressions on two different lines.

## 22. Complete Program 10 — Multiple Instances from One Anonymous Expression

Create the file **`AnonymousLoopInstancesDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class AnonymousLoopInstancesDemo {
    public static void main(String[] args) {
        List<Runnable> tasks = new ArrayList<>();

        for (int i = 0; i < 3; i++) {
            int capturedIndex = i;

            tasks.add(new Runnable() {
                @Override
                public void run() {
                    System.out.println("index=" + capturedIndex);
                }
            });
        }

        System.out.println("size=" + tasks.size());
        System.out.println("same instance="
                + (tasks.get(0) == tasks.get(1)));
        System.out.println("same runtime class="
                + (tasks.get(0).getClass()
                   == tasks.get(1).getClass()));

        for (Runnable task : tasks) {
            task.run();
        }
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 AnonymousLoopInstancesDemo.java
java AnonymousLoopInstancesDemo
~~~

**Stdout:**

~~~text
size=3
same instance=false
same runtime class=true
index=0
index=1
index=2
~~~

The three objects have different identities, yet they were created from **the same anonymous class declaration** and therefore share the same runtime class in this program. Each instance carries its own capturedIndex according to that execution of the expression.

Distinguish between **class identity** and **object identity**, especially when learning anonymous classes and when debugging class metadata.

## 23. `getClass()`: Anonymous in Source Does Not Mean Invisible in the JVM

An anonymous class has a runtime class, so the reflection methods of `Class` still work:

- `getClass().isAnonymousClass()`: identifies an anonymous class.
- `getClass().getSuperclass()`: returns the direct superclass.
- `getClass().getInterfaces()`: returns the direct interfaces.
- `getClass().getSimpleName()`: for an anonymous class, the simple name is the **empty string**.
- `getClass().getName()`: the binary name may contain `$` and a sequence number assigned by the compiler, and **should not be used as a business identifier**.

If an anonymous class implements Runnable, the runtime class typically has Object as its superclass and Runnable as its single direct interface. If it extends Base, the superclass is Base.

Do not write logic that depends on `Outer$1`, `Outer$2`, or compiler-generated sequence numbers: changing the source/compilation can make the names different.

## 24. Complete Program 11 — Inspecting Metadata Safely

Create the file **`AnonymousMetadataDemo.java`**:

~~~java
public class AnonymousMetadataDemo {
    public static void main(String[] args) {
        Runnable first = new Runnable() {
            @Override
            public void run() {
            }
        };

        Runnable second = new Runnable() {
            @Override
            public void run() {
            }
        };

        Class<?> type = first.getClass();

        System.out.println("anonymous=" + type.isAnonymousClass());
        System.out.println("simple empty="
                + type.getSimpleName().isEmpty());
        System.out.println("super is Object="
                + (type.getSuperclass() == Object.class));
        System.out.println("interface Runnable="
                + (type.getInterfaces()[0] == Runnable.class));
        System.out.println("different classes="
                + (first.getClass() != second.getClass()));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 AnonymousMetadataDemo.java
java AnonymousMetadataDemo
~~~

**Exact stdout:**

~~~text
anonymous=true
simple empty=true
super is Object=true
interface Runnable=true
different classes=true
~~~

Here `first` and `second` come from **two different class-declaring expressions**, so their runtime classes are also different. This **does not contradict** the previous loop example: in the loop, each instance originates from **the same declaration**.

The code avoids printing compiler-generated binary names, because they are not something an API should depend on long-term.

## 25. Anonymous Classes and Lambdas: Similar Usage Sites, Different Semantics

Since Java 8, functional interfaces like Runnable can often use a lambda:

~~~java
Runnable lambda = () -> System.out.println("Hello");
~~~

or an anonymous class:

~~~java
Runnable anonymous = new Runnable() {
    @Override
    public void run() {
        System.out.println("Hello");
    }
};
~~~

The two are snippets inside a method, yet **this does not mean all behaviors are completely identical**.

| Criterion | Anonymous class | Lambda |
| --- | --- | --- |
| Primary syntax | `new Interface() { ... }` | `() -> ...` |
| Directly usable with a functional interface? | Yes | Yes |
| Usable with an interface having multiple abstract methods? | Yes, by implementing all methods | No |
| Anonymous body has its own instance field? | Yes | No class body to declare such a field |
| `this` inside the body | Anonymous object | Lexical `this` of the site containing the lambda |
| Can extend a non-final class? | Yes | Cannot use a lambda to extend a class |
| Stable runtime class name for the app? | No | Also should not be relied upon |
| Capturing locals/parameters | Final/effectively final | Final/effectively final |
| Multiple overridden methods? | Yes, per the type contract | A lambda implements one abstract method |
| Boilerplate length when only printing one line | Long | Short |

**Recommendation:** for a short behavior targeting a functional interface, a lambda is usually clearer. When you need an anonymous **subclass of a class**, multiple methods, or instance fields attached to an object, an anonymous class remains useful.

## 26. When Converting an Anonymous Callback to a Lambda, Is `this` Still the Same Receiver?

An introductory lesson only needs one distinction: inside an **instance method** of an anonymous class, `this` refers to the **anonymous object**; inside a lambda written in an instance method of `Host`, `this` refers to the **Host object** according to lexical scope. It is not merely a shorter syntax that leaves semantics unchanged.

A **snippet placed inside an instance method of Host**:

~~~java
Runnable anonymous = new Runnable() {
    @Override
    public void run() {
        System.out.println(this.getClass().isAnonymousClass());
    }
};

Runnable lambda = () -> {
    System.out.println(this.getClass().getSimpleName());
};
~~~

If Host itself is the runtime class of the enclosing instance, the anonymous callback prints `true`, whereas the lambda prints `Host`. This section only introduces the warning about the receiver; the complete programs, scope tables, and `Outer.this` verification are covered in the dedicated lessons “Meaning of this and Accessing the Enclosing Object” and “Comparing Anonymous Classes and Lambdas in Usage Scope and this”.

**Refactoring criterion:** only switch to a lambda after confirming that the body does not rely on the anonymous callback's `this`, the anonymous subclass's `super`, or the anonymous class's own fields/methods.

## 27. Anonymous Classes and Named Local Classes

A **local class** is declared inside a method block with a name:

~~~java
void execute() {
    class Task implements Runnable {
        @Override
        public void run() {
            System.out.println("local");
        }
    }

    Runnable task = new Task();
    task.run();
}
~~~

This is a **valid illustrative method** when placed inside a class.

An anonymous class writes the same implementation inline:

~~~java
void execute() {
    Runnable task = new Runnable() {
        @Override
        public void run() {
            System.out.println("anonymous");
        }
    };
    task.run();
}
~~~

**Key difference:** a local class has a **type name within the block's scope**, so multiple instances can be created with `new Task()` from valid positions and multiple methods/fields can be organized under that name. An anonymous class **has no source-level name**, so implementation and creation reside in the same expression.

Both can still use final/effectively final captured variables from the enclosing scope and follow the corresponding enclosing-instance rules.

Is an implementation used multiple times, does it have significant logic, and does it deserve a name? A local class or member class can be easier to maintain than a long anonymous body.

## 28. Using an Anonymous Comparator with a Collection

A common use of an anonymous class is providing a comparator right at the sorting operation:

~~~java
List<String> words = new ArrayList<>(
        List.of("bbbb", "a", "ccc", "bb"));

words.sort(new Comparator<String>() {
    @Override
    public int compare(String left, String right) {
        int byLength =
                Integer.compare(left.length(), right.length());
        return byLength != 0
                ? byLength : left.compareTo(right);
    }
});
~~~

This is a valid snippet when placed inside a method with `List`, `ArrayList`, and `Comparator` imported.

`Comparator<String>` has the abstract method `compare`, and the anonymous class implements it. The sorting rule is by **ascending length**, and if lengths are equal, by **natural lexicographical order of String**.

Do not use `left.length() - right.length()` for general integers where overflow is possible; `Integer.compare(...)` expresses the intent more safely.

## 29. Complete Program 12 — Sorting with an Anonymous Comparator

Create the file **`AnonymousComparatorDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class AnonymousComparatorDemo {
    public static void main(String[] args) {
        List<String> words = new ArrayList<>(
                List.of("bbbb", "a", "ccc", "bb"));

        words.sort(new Comparator<String>() {
            @Override
            public int compare(String left, String right) {
                int length = Integer.compare(
                        left.length(), right.length());
                return length != 0
                        ? length : left.compareTo(right);
            }
        });

        System.out.println(words);
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 AnonymousComparatorDemo.java
java AnonymousComparatorDemo
~~~

**Stdout:**

~~~text
[a, bb, ccc, bbbb]
~~~

There is no separately named `LengthComparator` class in the source. Even so, the collection receives a **real Comparator object**. If that same comparator is used in multiple places or has lengthy business logic, making it a named class, static factory, or static constant is clearer.

With Java 17, you can use `Comparator.comparingInt(String::length).thenComparing(...)`, yet the anonymous class syntax remains important when reading legacy Java code and understanding object-oriented dispatch.

## 30. Anonymous Runnable and Thread: Creating the Object Does Not Automatically Run Multithreaded

The following two operations are **different**:

~~~java
Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println("working");
    }
};
task.run();
~~~

`task.run()` is a **synchronous method call on the current thread**.

If you want to execute the Runnable on a **new thread**, you pass it to Thread:

~~~java
Thread worker = new Thread(new Runnable() {
    @Override
    public void run() {
        System.out.println("working");
    }
});
worker.start();
~~~

These are two snippets inside a method. Only `worker.start()` requests starting a thread according to the Thread API. **No concurrency magic** is triggered simply by `new Runnable() { ... }`.

To get deterministic stdout in a demonstration, a complete program needs to wait for the thread to finish using `join()` before printing the next line in main.

## 31. Complete Program 13 — Passing an Anonymous Runnable to Thread

Create the file **`AnonymousThreadDemo.java`**:

~~~java
public class AnonymousThreadDemo {
    public static void main(String[] args)
            throws InterruptedException {
        String message = "task done";

        Thread worker = new Thread(new Runnable() {
            @Override
            public void run() {
                System.out.println(message);
            }
        });

        worker.start();
        worker.join();
        System.out.println("main done");
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 AnonymousThreadDemo.java
java AnonymousThreadDemo
~~~

**Stdout (when the thread runs successfully):**

~~~text
task done
main done
~~~

`message` is effectively final so the anonymous class can capture it. `worker.join()` makes main wait for worker to finish before printing `main done`, so the order of the two lines is deterministic in the program.

In a real application, an anonymous Runnable can be handed to an executor, callback, or event loop. In that case, you need to understand which API **actually calls** `run()` or another method, on which thread, and when.

## 32. Technique for Hiding Implementation via an Interface-Returning Factory

When an anonymous class is merely an implementation detail of a method, the method can return the interface:

~~~java
interface IntRule {
    boolean matches(int value);
}

final class Rules {
    private Rules() {
    }

    static IntRule atLeast(int threshold) {
        return new IntRule() {
            @Override
            public boolean matches(int value) {
                return value >= threshold;
            }
        };
    }
}
~~~

These are valid Java definitions, without a main yet. The caller only needs to use `IntRule`, without knowing or needing to know the compiler-generated anonymous class name.

**Advantages:** avoids publishing an extra named class used only inside a factory, while still providing an object with a clear interface contract. **Disadvantages:** as the implementation grows, code nested inside the method can be harder to read and test independently than a named class.

The `threshold` data is safely captured at the **primitive value level** because the parameter is not reassigned. If a mutable reference is captured, a separate ownership analysis is needed.

## 33. Complete Program 14 — Interface-Returning Factory

Create the file **`AnonymousFactoryDemo.java`**:

~~~java
interface IntRule {
    boolean matches(int value);
}

final class Rules {
    private Rules() {
    }

    static IntRule atLeast(int threshold) {
        return new IntRule() {
            @Override
            public boolean matches(int value) {
                return value >= threshold;
            }
        };
    }
}

public class AnonymousFactoryDemo {
    public static void main(String[] args) {
        IntRule adult = Rules.atLeast(18);
        IntRule positive = Rules.atLeast(1);

        System.out.println("adult 17=" + adult.matches(17));
        System.out.println("adult 20=" + adult.matches(20));
        System.out.println("positive 2="
                + positive.matches(2));
        System.out.println("different=" + (adult != positive));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 AnonymousFactoryDemo.java
java AnonymousFactoryDemo
~~~

**Stdout:**

~~~text
adult 17=false
adult 20=true
positive 2=true
different=true
~~~

The two calls to `Rules.atLeast(...)` create two instances of the same anonymous implementation declared in the factory, yet capture **two different thresholds**.

When the interface has only a single simple abstract method, the factory can be written more concisely with a lambda. An anonymous class remains a valid approach, especially if the implementation needs multiple methods or instance fields.

## 34. Accessing Methods Only Present on an Anonymous Implementation

With:

~~~java
Object value = new Object() {
    String describe() {
        return "local";
    }
};
~~~

this is a valid snippet inside a method. However, you **cannot** call `value.describe()` when the static type of the variable is Object, because Object does not declare a `describe()` method.

The case of `var` in Java 10+ has an interesting detail:

~~~java
var local = new Object() {
    String describe() {
        return "local";
    }
};

System.out.println(local.describe());
~~~

This is valid code inside a method in Java 17, because the compiler infers the type of `local` from the initializer expression and can allow access to the corresponding method within that scope.

**You should not use the `var` case as a way to build a public API**. An anonymous class has no name in source, and local variable type inference has its own rules; if callers need to invoke a method, it should be defined on a **published interface or superclass**, rather than relying on a method that only exists on an anonymous implementation.

## 35. Complete Program 15 — `var` and Additional Methods

Create the file **`AnonymousVarDemo.java`**:

~~~java
public class AnonymousVarDemo {
    public static void main(String[] args) {
        var local = new Object() {
            String describe() {
                return "extra method";
            }
        };

        Object wide = local;

        System.out.println("local=" + local.describe());
        System.out.println("wide anonymous="
                + wide.getClass().isAnonymousClass());
        System.out.println("same=" + (local == wide));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 AnonymousVarDemo.java
java AnonymousVarDemo
~~~

**Stdout:**

~~~text
local=extra method
wide anonymous=true
same=true
~~~

This is a **specialized case** of local variable type inference, and it does not change the rule that `Object wide` has no `describe()` method at compile time.

Even with the same reference, the methods that can be called directly depend on the **static type** of the expression at each site. Having an anonymous runtime type does not mean every Object reference can automatically access those custom methods.

## 36. An Anonymous Class Cannot Extend a `final` Class

When a class is declared `final`, no class may extend it, including an anonymous class.

~~~java
final class Closed {
}
~~~

A snippet that **intentionally does not compile** if added to a method:

~~~java
// Object bad = new Closed() { };
~~~

Even an empty class body is still requesting **an anonymous subclass declaration of Closed**, thus violating the final class restriction.

Do not confuse this with creating a normal Closed object:

~~~java
Closed okay = new Closed();
~~~

This is valid code if the constructor is accessible. **There is no class body**, so no anonymous subclass is declared.

Similarly, `new String() { ... }` is invalid because String is final; you cannot override `String` with an anonymous class.

## 37. Errors with Constructors, Method Signatures, and `@Override`

Common compile-time errors:

**No matching constructor:**

~~~java
class Base {
    Base(int id) {
    }
}
~~~

If you call `new Base() { ... }`, failing to supply an `int` argument causes an error, because Base has no accessible no-argument constructor.

**The overridden method is final:**

~~~java
class Base {
    final void locked() {
    }
}
~~~

You cannot use `new Base() { @Override void locked() {} }` to override locked.

**A superclass's private method is not overridden:**

~~~java
class Base {
    private void secret() {
    }
}
~~~

A method with the same name/signature inside the anonymous subclass **does not override** the private method from Base. If you add `@Override` on that method when there is no other suitable method to override, the compiler reports an error.

**Interface methods must use the proper access level:** when implementing `Runnable.run()`, the method must be `public void run()`; you cannot reduce its visibility to package-private or private.

The examples in this section are **independent illustrative definitions/snippets**; do not combine the three classes named Base into the same file.

## 38. `new Interface() { ... }` Is Not Calling an Interface Constructor

A Java interface **has no instance constructor**. Therefore:

~~~java
Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println("ok");
    }
};
~~~

does not mean you are “instantiating the Runnable interface”. You are creating **an anonymous class that implements Runnable**; every object in Java is an instance of some concrete class, even when the reference is assigned to an interface type.

Common misconceptions:

- “An interface cannot be instantiated with new, so this syntax ought to be invalid.” → No: there is an anonymous class body, so it is an object of **an anonymous implementation class**.
- “You need to write `implements Runnable` afterward.” → No: `new Runnable() { ... }` already supplies the superinterface name.
- “The run method runs automatically right away.” → No: creating the object does not automatically call run.
- “There is no class, so there is no state.” → No: an anonymous class can have instance fields.
- “Every interface can be used with a lambda.” → No: a lambda requires a functional interface, whereas an anonymous class can implement multiple abstract methods.

## 39. Some Constraints of an Anonymous Class Body

An anonymous class **has no source-level name and cannot declare a named constructor**. It can declare fields, instance methods, instance initializer blocks, and valid nested declarations under Java 17.

An anonymous class has the following contextual limitations:

- It cannot `extends` a final class.
- It cannot directly declare that an anonymous class extends two classes (Java has no multiple class inheritance).
- You cannot write `implements A, B` additionally after `new X() { ... }` as in named class declaration syntax.
- It must respect the access of the superclass constructor and the remaining abstract methods.
- It must not reduce visibility when implementing public interface methods.
- It must not override final/private methods in a way that violates the JLS.
- Captured locals/parameters must be final/effectively final.
- Its own named constructor cannot appear because an anonymous class has no source name.
- The `static` modifier on members is still subject to the rules for inner classes and static contexts in Java 17; you cannot arbitrarily declare any static state inside an anonymous class.

If an implementation has too many responsibilities, you should move it to a named local class, static nested class, or top-level class. An anonymous class is suited for **logic focused at the point of use**, not for hiding an entire subsystem.

## 40. Do Not Use an Anonymous Class as a Subclass Just to Access a Private Field

Nesting and inheritance are two different relationships:

- An anonymous class declared **inside an instance method** of Outer can access private state of the enclosing Outer when the context permits.
- An anonymous subclass **inheriting from Base** does not automatically have permission to read Base's private fields by inheritance. Use an appropriate protected/public API.
- An anonymous class created in a static method does not automatically have `Outer.this`.
- Using reflection to break encapsulation is not an idiomatic replacement for API design.

For example, in section 10, `Greeting` has `private String name`; the anonymous subclass calls `protected final String name()`, **without reading `name` directly** just because it is a subclass. This is an example of properly separating member access rights from the subclass relationship.

If the anonymous class is declared **lexically inside Greeting itself**, nesting access rules may grant different permissions. Consider the **specific declaration site**, not just the subtype name.

## 41. Side Effects and Lifetime of Anonymous Objects

An anonymous object can be:

- Used immediately with no remaining reference, for example `new Runnable(){...}.run()`.
- Held in a local variable.
- Returned via a factory/interface.
- Stored in a collection/listener registry.
- Passed to a Thread/Executor, potentially outliving the method that created it.

If an anonymous object **captures a reference to a large object** or to the enclosing Outer, it can extend that object's reachability. This is not an automatic language error, but it is something to consider when designing long-lived callbacks.

Do not assume that an anonymous class is automatically reclaimed after a single method call. GC is based on **reachability**, not on whether a class has a name.

Nor should you assume that a mutable field inside an anonymous class is already managed in a thread-safe way: state and synchronization are still up to you to design.

## 42. When Should You Choose Anonymous, Lambda, Named Local Class, or Nested Class?

| Need | Usually reasonable choice | Why |
| --- | --- | --- |
| A short behavior of a functional interface | Lambda | Concise, describes behavior directly |
| Overriding a method on a non-final class right at the point of use | Anonymous class | No need for a named class just to customize |
| Interface with multiple abstract methods | Anonymous or named class | A lambda does not directly provide multiple methods |
| Local implementation with multiple fields/methods needing a name | Named local class | Easier to read/create multiple instances from the local type |
| Helper/Builder with a long-term relationship to Outer | Static nested/member class | Clear API, visibility, and ownership |
| Type used widely in many places | Top-level/named class | Easy to reuse, test, and document |
| Callback used in only one call and relatively small | Anonymous class or lambda | Code stays close to the point of use |
| Large service/domain object with many invariants | Named class | Avoids overly long anonymous bodies that are hard to verify |

A practical criterion: **an anonymous class should make code easier to read**, not shorter at all costs. If you have to scroll through hundreds of lines to find logic outside an anonymous expression, consider extracting a class.

## 43. Common Mistakes and How to Fix Them

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| `new Runnable()` without a class body | An interface has no instance constructor | Use `new Runnable(){ public void run(){...} }` |
| Omitting `run()` or wrong signature | Does not implement all required abstract methods | Use `@Override` and the exact signature |
| Using non-public `void run()` | Cannot reduce interface method visibility | `public void run()` |
| Thinking `new Runnable(){...}` runs automatically | Creation is distinct from invocation | Call `run()` or pass to a task-managing API |
| Treating an anonymous object as a singleton | Each evaluated new expression creates an instance | Only share when intentionally storing the same reference |
| Treating `this` as Outer | `this` inside an anonymous body is the anonymous object | Use `Outer.this` when valid |
| Reassigning a captured local | Not effectively final | Snapshot into a new local variable |
| Capturing StringBuilder and expecting a fixed snapshot | The target object is mutable | Capture a newly created immutable String |
| Anonymous implementation needing to call a custom method via a Runnable ref | The static type does not declare that method | Publish the proper interface or named API |
| Using an anonymous subclass of a final class | Extending is not allowed | Create a normal object or use composition |
| Thinking an anonymous subclass runs a constructor you declared in its body | Anonymous classes have no separately declared constructor | Call the superclass constructor with args; use an appropriate initializer |
| Using a lambda for an interface with two abstract methods | Not a functional interface | Anonymous or named class |
| Comparing class names like `Outer$1` | Generated names can change | Use interfaces/contracts/reflection APIs |
| Using a counter field on an anonymous object across threads without synchronization | Race condition | Atomic/synchronized/immutable state |
| Keeping a long-lived callback that unnecessarily captures all of Outer | Retention/coupling | Keep only the needed data/dependencies |
| Writing an overly large anonymous body | Hard to test, hard to maintain | Local/nested/named class |

## 44. Process for Reading an Anonymous Creation Expression

When encountering the code `new X(args) { ... }`:

1. **Is X an interface or a class?** If an interface, the anonymous class implements X. If a class, the anonymous class extends X.
2. **Is X final?** If it is a final class, an anonymous subclass cannot be used.
3. **Which constructor is called?** For a class, check the overload/visibility of X's constructor accepting args; for an interface, empty parentheses.
4. **Which abstract methods must be implemented?** Check the signature, access, and `@Override`.
5. **Does the class body have fields/init blocks?** Distinguish between object construction time and method invocation time.
6. **What type is the returned reference?** The static type determines which methods callers are allowed to invoke directly.
7. **Does it capture any locals/parameters?** They must be final/effectively final and validly definitely assigned.
8. **Which object does `this` point to?** Inside the anonymous body, `this` is the anonymous instance.
9. **Is `Outer.this` valid?** Only when there is an appropriate enclosing instance in context.
10. **Are mutable references shared?** Capture does not guarantee immutability or thread safety.
11. **When is the method executed?** Creating the object does not automatically invoke the callback; the consuming API decides the timing.
12. **One declaration or multiple declarations?** The same expression repeated multiple times creates instances of the same runtime class; two different expressions define two separate anonymous classes.
13. **Are there long-term side effects/lifecycle concerns?** Evaluate object reachability, execution context, and cleanup per the API.
14. **Which style is most maintainable?** If the anonymous body is long or needs reuse, name the class or use an appropriate lambda.

## 45. Practice Exercises

**Question 1.** Explain why `new Runnable() { ... }` is valid even though the Runnable interface cannot be instantiated directly.

**Question 2.** With `Runnable action = new Runnable() { public void run() {...} };`, does the `run()` behavior execute immediately at the new expression?

**Question 3.** When using `new InterfaceName() { ... }`, can you write `implements InterfaceName` after the body?

**Question 4.** How many methods must an anonymous class implementing an interface with two abstract methods implement if there is no suitable inherited implementation?

**Question 5.** Which constructor does `new Base(10) { ... }` select? Can an anonymous subclass be created if Base is final?

**Question 6.** Can a constructor bearing the anonymous class's name be declared inside `{ ... }`? List the alternative ways to initialize fields.

**Question 7.** Which object does `this` inside an anonymous Runnable created in `Page.action()` refer to? Which object does `Page.this` refer to?

**Question 8.** A `Runnable` reference points to an anonymous implementation that has a private method `help()`; can `runnable.help()` be called from outside?

**Question 9.** `int n = 1;` is captured into an anonymous body; afterward, `n++` is written. Does it compile?

**Question 10.** Capture `StringBuilder builder`, then call `builder.append("x")`. Does that cause the builder variable to lose its effectively final status?

**Question 11.** An anonymous class declaration inside a loop is evaluated three times. How many instances are there? Can they have the same runtime class?

**Question 12.** Two anonymous creation expressions are written at two different source locations, both implementing Runnable. Are their runtime classes the same?

**Question 13.** What does `getClass().getSimpleName()` of an ordinary anonymous object return? Should `Outer$1` be stored in a database as a business identifier?

**Question 14.** How are anonymous classes and lambdas similar and different regarding `this`?

**Question 15.** Why cannot a lambda directly replace an anonymous subclass of the abstract class `Greeting`?

**Question 16.** When should a long anonymous implementation be converted into a named local class or static nested class?

**Question 17.** Why are `new Runnable(){...}.run()` and `new Thread(new Runnable(){...}).start()` not equivalent?

**Question 18.** If an anonymous class captures an `ArrayList` and two threads concurrently modify that list, does effectively final make the code safe?

**Question 19.** With `var local = new Object(){ String describe(){...} };`, Java 17 allows `local.describe()` in an appropriate declaration context. Why does the variable `Object wide = local` not allow calling `wide.describe()` directly?

**Question 20.** A factory returns an `IntRule` using an anonymous class. Does the caller need to know the bytecode implementation name to call `matches()`?

**Question 21.** When does the instance initializer in an anonymous class run compared to the superclass constructor and compared to `run()` afterward?

**Question 22.** Can an anonymous class declare separate instance fields for each object?

**Question 23.** What kind of error does `@Override` help detect when implementing `Runnable.run()`?

**Question 24.** If an anonymous Runnable is registered in a long-lived listener registry and captures the Outer object, what can the consequence be?

### Reference Answers

1. Because the expression creates an instance of an **anonymous class that implements Runnable**, not an abstract interface object.
2. No; new creates the object. `run()` only executes when called or invoked by an API using the object.
3. No; the new-interface syntax with an anonymous class body already specifies the superinterface.
4. Two, if both are unimplemented abstract methods.
5. It calls the Base constructor matching argument 10; if Base is final, it cannot be extended by an anonymous class.
6. No; use superclass constructor args, field initializers, instance initializers, or captured values.
7. `this` is the anonymous object; `Page.this` is the appropriate enclosing Page instance.
8. No, not through the static type Runnable; the interface does not have help, and the helper is private.
9. No; `n++` makes n not effectively final.
10. No. The builder reference is not reassigned; only the target object mutates.
11. Three instances; if from the same expression/declaration, they can share the same runtime class.
12. No; they are two separate anonymous class declarations, even with the same superinterface.
13. The empty string; do not rely on a compiler-generated binary name as a business ID.
14. Both can capture final/effectively final variables; `this` in an anonymous class is the anonymous object, whereas `this` in a lambda uses the lexical enclosing context.
15. A lambda implements a functional interface; it does not extend an arbitrary class.
16. When the logic is large, has multiple responsibilities, or needs reuse, testing, or a clearer public contract.
17. Calling `run()` directly on the current thread differs from `Thread.start()`, which creates an execution thread according to the API.
18. No; a mutable List needs separate concurrency protection.
19. The static type of wide is Object, so there is no describe method in the Object API; the local var infers the specialized expression type.
20. No; the caller works through `IntRule.matches`.
21. The superclass constructor runs before the anonymous subclass's instance initialization; `run()` only runs later when called.
22. Yes; each object has its own set of instance fields.
23. A misspelled name/signature, or a method that does not actually override a suitable method, is detected at compile time.
24. The registry may keep the anonymous object and the references it holds/captures reachable longer than intended, causing retention/coupling.

## 46. Checklist Before Adding an Anonymous Class to a Program

- Have you determined whether `new X(args) { ... }` extends a class or implements an interface?
- Is X not a final class when an anonymous subclass is needed?
- Are the constructor args appropriate if X is a superclass?
- Have all abstract methods been implemented accurately, with appropriate visibility?
- Is `@Override` used for the methods that should be overridden?
- Are the fields/initializers in the anonymous class body designed clearly and validly?
- Are captured variables final/effectively final and definitely assigned?
- Have you distinguished object creation from calling the callback method?
- If there is an outer instance, have you distinguished `this` from `Outer.this`?
- Have you avoided depending on the compiler-generated anonymous binary name?
- Does the returned interface/superclass expose all the methods the caller needs?
- If state is needed across callback calls, have you chosen an instance field instead of reassigning a captured local?
- If capturing a mutable object, have you analyzed aliasing and concurrency?
- Do you understand that a repeated expression creates multiple instances of the same anonymous class?
- Is the anonymous implementation short, close to the point of use, and easy to understand?
- If the implementation is large, have you considered a named local/member class?
- If it is a simple functional interface, have you considered a lambda?
- If the callback is long-lived, have you considered retention and cleanup?
- If using Thread/Executor, do you understand which thread executes it and how to manage its lifecycle?
- Have the examples been compiled with Java 17+ and does stdout reflect only a deterministic order?

## 47. Official Java 17 Documentation

- [JLS 17 §15.9.5 — Anonymous Class Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9.5): declaration placement and meaning of the anonymous class body.
- [JLS 17 §15.9 — Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9): `new` syntax, arguments, and instance creation.
- [JLS 17 §8.1.3 — Inner Classes and Enclosing Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.3): anonymous inner classes and enclosing context.
- [JLS 17 §4.12.4 — final Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): final/effectively final captured variables.
- [JLS 17 §16 — Definite Assignment](https://docs.oracle.com/javase/specs/jls/se17/html/jls-16.html): initialization of captured variables.
- [JLS 17 §8.4.8 — Inheritance, Overriding and Hiding](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8): overriding behavior and visibility.
- [JLS 17 §15.27 — Lambda Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27): comparing lexical `this` and capture.
- [Java SE 17 API — Runnable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runnable.html): the `run()` contract.
- [Java SE 17 API — Comparator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html): comparator objects and sorting.
- [Java SE 17 API — Class.isAnonymousClass](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#isAnonymousClass()): identifying a runtime anonymous class.
- [Java SE 17 API — Class.getSimpleName](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getSimpleName()): simple names for classes.
- [Java SE 17 API — Thread.start](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html#start()): executing a task on a thread.
- [Java SE 17 API — Thread.join](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html#join()): waiting for a thread to finish.

**Summary:** the `new Interface() { ... }` or `new Base(args) { ... }` expression allows **declaring an anonymous class and instantiating an object in the same step of source code**. The implementation is still a class with instance state, constructors inherited according to the rules, and runtime identity; it is not merely a function or an instance of an abstract interface. Use an anonymous class when behavior needs to be customized right at the point of use, especially for multi-method callbacks or anonymous subclasses. At the same time, control **`this`**, captured variables, object lifetimes, thread safety, and the static type of the reference. If the implementation is simple and targets a functional interface, a lambda is usually shorter; if the implementation is large or reused, a named class is easier to manage.
