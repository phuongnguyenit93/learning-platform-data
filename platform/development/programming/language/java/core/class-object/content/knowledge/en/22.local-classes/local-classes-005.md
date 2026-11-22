# Local Classes in Static Context and Instance Context — Java 17+

A **local class** is a named class declared inside a block, such as a method body, constructor, instance initializer, or static initializer. **Both are local classes, yet the declaring environment determines whether it can access the enclosing object (`Outer.this`).**

- In an **instance context** of `Outer`, the local class can access instance fields/methods of the current `Outer` object and use `Outer.this`.
- In a **`static` context**, no implicit `Outer.this` receiver exists. The local class can still access static members and capture eligible local variables/parameters.
- Both contexts share the capture rule: local variables or parameters used by the local class must be **`final` or `effectively final`**; this does not mean the referenced object becomes immutable.

Comparison example:

~~~java
class Counter {
    private int count = 10;
    private static int seed = 100;

    int instanceExample(int delta) {
        class InstanceLocal {
            int value() {
                return Counter.this.count + delta;
            }
        }
        return new InstanceLocal().value();
    }

    static int staticExample(int delta) {
        class StaticLocal {
            int value() {
                return seed + delta;
            }
        }
        return new StaticLocal().value();
    }
}
~~~

The `instanceExample` method can use `Counter.this.count`. The `staticExample` method does not have `Counter.this`, but it can read `seed` because it is a static field and `delta` because the parameter is effectively final.

This lesson belongs to **Java Core — Class & Object / Local Classes**, using Java 17+. Standalone runnable examples specify the file name, `javac`/`java` commands, and expected stdout. Compilation-error snippets are **clearly commented** so they are not mistaken for runnable programs.

## 1. Objectives

After this lesson, you will be able to:

1. Distinguish between the *lexical scope of a local class* and the *static/instance context where it is declared*.
2. Declare and create a local class object inside an instance method.
3. Declare and create a local class object inside a static method.
4. Use `Outer.this` only in contexts that have an enclosing Outer instance.
5. Distinguish the local class's `this` from the enclosing object's `Outer.this`.
6. Correctly read instance fields, static fields, instance methods, and static methods.
7. Explain why a static method does not automatically know which Outer object to use.
8. Pass an explicit Outer reference when static logic needs a specific object.
9. Understand local classes in instance/static initializer blocks and constructors.
10. Distinguish capturing local variables from accessing outer instance fields.
11. Know that captured locals must be final/effectively final, whether declared in a static or instance method.
12. Distinguish reassigning a variable from mutating the object pointed to by a captured reference.
13. Understand why outer instance fields can change even though captured method locals cannot be reassigned.
14. Avoid confusing a static nested member class with a local class declared inside a static method.
15. Understand that Java 17 allows static declarations in inner/local classes under current rules.
16. Know that a local record/enum is implicitly static and does not capture an enclosing instance like an ordinary local class.
17. Distinguish lambda `this` from local-class `this`.
18. Distinguish local classes in generic static and generic instance methods.
19. Understand that a local class can escape its enclosing method via an interface reference.
20. Recognize memory retention, unsafe publication, thread safety, and lifecycle.
21. Analyze reflection `isLocalClass`, `getEnclosingMethod`, and runtime identity.
22. Fix common compiler errors through output-prediction exercises.

## 2. Two Meanings of “Enclosing”

It is necessary to separate **lexical enclosure** from **being tied to an enclosing instance**.

A local class inside `Outer.staticMethod()` is still **written inside the source of Outer**, and reflection can report that the enclosing method is staticMethod. However, that local class **does not automatically have an Outer object** for `Outer.this` to point to.

A local class inside `outer.instanceMethod()` has a lexical context corresponding to the instance method and can reference `Outer.this` — that is, the object used as the receiver of the method invocation.

~~~text
Outer type
  |
  +--- instanceMethod()        [has receiver Outer.this]
  |      |
  |      +--- class LocalA    [can access outer instance]
  |
  +--- staticMethod()          [no Outer.this]
         |
         +--- class LocalB    [can access static members]
~~~

“Static context” here refers to **the code region where the declaration resides**, not that `LocalB` turns into a `static member class`. LocalB is still a local class, and its name is valid only inside the block; you cannot call `new Outer.LocalB()` from outside.

## 3. Quick Comparison

| Aspect | Local class in instance context | Local class in static context |
| --- | --- | --- |
| Has an implicit enclosing Outer instance | Yes, in the appropriate context | No |
| Uses `Outer.this` | Yes | No |
| Reads Outer's instance field without an explicit reference | Yes | No |
| Reads Outer's static field | Yes | Yes |
| Reads effectively final local variable | Yes | Yes |
| Has fields/constructors/instance methods | Yes | Yes |
| Has a name like `Outer.Local` usable outside the method | No | No |
| Can use `new Local()` in scope after the declaration | Yes | Yes |
| Can return object via an interface | Yes | Yes |
| Class metadata `isLocalClass()` | True | True |
| Automatically a singleton or a new object per declaration | No | No |
| Automatically thread-safe | No | No |

**Key rule:** A static method belongs to the **class-level API** and is not invoked on an implicit receiver instance. Any access to the state of an Outer object in a static context requires an **explicit reference** to that object.

## 4. Local Class in an Instance Method

Consider:

~~~java
class Notebook {
    private final String name;

    Notebook(String name) {
        this.name = name;
    }

    String describe(int page) {
        class PageDescription {
            String text() {
                return Notebook.this.name + ":page=" + page;
            }
        }
        return new PageDescription().text();
    }
}
~~~

In `describe`:

- `this` when in the body of `Notebook.describe` is the Notebook receiver.
- `this` inside `PageDescription.text` is the PageDescription object.
- `Notebook.this` inside PageDescription is the Notebook receiver that created the local class object.
- `page` is an effectively final method parameter captured by the local class.

You do not need to declare a `Notebook` reference in the PageDescription constructor to use `Notebook.this`. Java defines enclosing-instance semantics for a local class in an instance context.

## 5. Runnable Program: Instance Method

Create **`InstanceContextDemo.java`**:

~~~java
public class InstanceContextDemo {
    static final class Notebook {
        private final String name;

        Notebook(String name) {
            this.name = name;
        }

        String describe(int page) {
            class PageDescription {
                String text() {
                    return Notebook.this.name + ":page=" + page;
                }
            }
            return new PageDescription().text();
        }
    }

    public static void main(String[] args) {
        Notebook first = new Notebook("Java");
        Notebook second = new Notebook("Algorithms");

        System.out.println(first.describe(3));
        System.out.println(second.describe(7));
    }
}
~~~

~~~bash
javac -encoding UTF-8 InstanceContextDemo.java
java InstanceContextDemo
~~~

Stdout:

~~~text
Java:page=3
Algorithms:page=7
~~~

It is the same local class declaration `PageDescription` in the describe method, but each object uses the enclosing Notebook corresponding to the invocation that created it.

## 6. Local Class in a Static Method

A static method does not have an `Outer.this` receiver instance. Example:

~~~java
class Notebook {
    private static final String PREFIX = "book:";

    static String label(String name) {
        class Formatter {
            String result() {
                return PREFIX + name;
            }
        }
        return new Formatter().result();
    }
}
~~~

Formatter has access to `PREFIX`, which is a static member; `name` is an effectively final parameter. However, Formatter **cannot** use `Notebook.this` because it is declared from a static context.

### Runnable Program

Create **`StaticContextDemo.java`**:

~~~java
public class StaticContextDemo {
    private static final String PREFIX = "book:";

    static String label(String name) {
        class Formatter {
            String result() {
                return PREFIX + name;
            }
        }

        return new Formatter().result();
    }

    public static void main(String[] args) {
        System.out.println(label("Java"));
        System.out.println(label("Algorithms"));
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticContextDemo.java
java StaticContextDemo
~~~

Stdout:

~~~text
book:Java
book:Algorithms
~~~

The code is valid even though Formatter is not tied to any StaticContextDemo instance. `name` is still captured per method invocation.

## 7. Why Is `Outer.this` Invalid in a Static Context?

Suppose:

~~~java
class Outer {
    private int instanceValue = 7;

    static void method() {
        class Local {
            int wrong() {
                // return Outer.this.instanceValue; // Compile error.
                return 0;
            }
        }
    }
}
~~~

A static method is called via `Outer.method()`. There might not be any Outer object yet, or there might be multiple Outer objects. Java cannot infer a single receiver object for `Outer.this` to point to.

Similarly:

~~~java
// return instanceValue; // Invalid in a static local context without a receiver.
~~~

This is a **context error**, not an access modifier error: even if the field is public, a static method still needs an object reference to read a particular instance field.

## 8. Need an Outer Instance in a Static Method? Pass an Explicit Reference

If a static method must process an object's state, pass it via a parameter:

~~~java
class Outer {
    private final int value;

    Outer(int value) {
        this.value = value;
    }

    static int read(Outer target) {
        class Reader {
            int get() {
                return target.value;
            }
        }
        return new Reader().get();
    }
}
~~~

`target` is an effectively final parameter and is captured. Here, Reader does not have an implicit `Outer.this`, but it has **an explicit reference** to target and uses that reference to access the private field according to Java access rules.

We need to distinguish:
- *Automatic enclosing instance*: `Outer.this` in an instance context.
- *Explicit object dependency*: `target` captured by a local class in a static context.

Both approaches can read the same field, but they have different ownership and lifetime semantics.

## 9. Runnable Program: Explicit Outer Reference in a Static Method

Create **`ExplicitReceiverDemo.java`**:

~~~java
public class ExplicitReceiverDemo {
    static final class Account {
        private final int number;

        Account(int number) {
            this.number = number;
        }

        static String describe(Account account) {
            class Reader {
                String read() {
                    return "account-" + account.number;
                }
            }
            return new Reader().read();
        }
    }

    public static void main(String[] args) {
        Account a = new Account(10);
        Account b = new Account(20);

        System.out.println(Account.describe(a));
        System.out.println(Account.describe(b));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ExplicitReceiverDemo.java
java ExplicitReceiverDemo
~~~

Stdout:

~~~text
account-10
account-20
~~~

The local Reader in the static method does not have `Account.this`. It references the **account parameter**, so the caller decides which Account object is read.

## 10. A Local Class's `this` Is Not `Outer.this`

Inside a method of a local class, `this` is the **instance of the local class**, regardless of whether it is declared in an instance or static method.

~~~java
class Outer {
    void act() {
        class Local {
            boolean selfCheck() {
                return this instanceof Local;
            }

            boolean ownerCheck() {
                return Outer.this != null;
            }
        }
    }
}
~~~

`this` in `selfCheck` does not automatically become the Outer object. `Outer.this` refers to the separate Outer receiver.

In a **static context**, `this` **is still valid inside an instance method of the local class**, because `this` is the local class object there. Only `Outer.this` does not exist.

## 11. Runnable Program: `this` in Both Contexts

Create **`ThisScopeDemo.java`**:

~~~java
public class ThisScopeDemo {
    private final String id;

    ThisScopeDemo(String id) {
        this.id = id;
    }

    String instanceRun() {
        class Local {
            String show() {
                return "local=" + (this instanceof Local)
                        + ", outer=" + ThisScopeDemo.this.id;
            }
        }

        return new Local().show();
    }

    static String staticRun() {
        class Local {
            String show() {
                return "local=" + (this instanceof Local);
            }
        }

        return new Local().show();
    }

    public static void main(String[] args) {
        System.out.println(new ThisScopeDemo("A").instanceRun());
        System.out.println(ThisScopeDemo.staticRun());
    }
}
~~~

~~~bash
javac -encoding UTF-8 ThisScopeDemo.java
java ThisScopeDemo
~~~

Stdout:

~~~text
local=true, outer=A
local=true
~~~

Both local class objects have the instance receiver `this` in the show method. Only the local class of `instanceRun` has an enclosing ThisScopeDemo instance to use `ThisScopeDemo.this`.

## 12. Capturing Local Variables: The Same Rule

Both instance and static contexts allow a local class to use surrounding method locals/parameters if they are **final or effectively final**, and definitely assigned before being used.

~~~java
int base = 10; // Effectively final if not reassigned.

class Local {
    int compute(int input) {
        return base + input;
    }
}
~~~

The variable `base` does not have the final keyword, but it can be used validly if it is not reassigned according to Java rules.

**Example that breaks effectively final:**

~~~java
int base = 10;
base = 20;

class Local {
    int compute() {
        // return base; // Compile error: base is not effectively final.
        return 0;
    }
}
~~~

The error stems from **capturing a local variable**, independent of whether the declaration resides in a static or instance method.

## 13. Runnable Program: Capture in Both Contexts

Create **`CaptureInBothContextsDemo.java`**:

~~~java
public class CaptureInBothContextsDemo {
    private final int multiplier;

    CaptureInBothContextsDemo(int multiplier) {
        this.multiplier = multiplier;
    }

    int instanceCalculate(int input) {
        int offset = 2;

        class Calculator {
            int result() {
                return multiplier * input + offset;
            }
        }

        return new Calculator().result();
    }

    static int staticCalculate(int input) {
        int multiplier = 3;
        int offset = 2;

        class Calculator {
            int result() {
                return multiplier * input + offset;
            }
        }

        return new Calculator().result();
    }

    public static void main(String[] args) {
        CaptureInBothContextsDemo value =
                new CaptureInBothContextsDemo(4);

        System.out.println("instance=" +
                value.instanceCalculate(5));
        System.out.println("static=" +
                staticCalculate(5));
    }
}
~~~

~~~bash
javac -encoding UTF-8 CaptureInBothContextsDemo.java
java CaptureInBothContextsDemo
~~~

Stdout:

~~~text
instance=22
static=17
~~~

In the instance method, `multiplier` is an outer field, while input/offset are captured method values. In the static method, multiplier/offset are both captured local values, with no outer instance field at all.

## 14. Outer Instance Fields Are Not Required to Be Effectively Final

An `Outer.counter` field can change over time:

~~~java
class Outer {
    private int counter;

    Runnable createTask() {
        class Task implements Runnable {
            @Override
            public void run() {
                System.out.println(Outer.this.counter);
            }
        }
        return new Task();
    }

    void setCounter(int next) {
        counter = next;
    }
}
~~~

Task reads **the current field of the enclosing Outer object** on each run, not a snapshot of counter at the time of createTask.

Compared with a method-local variable:

~~~java
int initialCounter = counter;

class Task {
    int snapshot() {
        return initialCounter;
    }
}
~~~

`initialCounter` is a captured local value; if it is a primitive int, each Task has the semantics of reading the value captured when the instance was created, rather than reading a field that changes later.

## 15. Runnable Program: Dynamic Field and Local Snapshot

Create **`FieldVsCapturedLocalDemo.java`**:

~~~java
public class FieldVsCapturedLocalDemo {
    private int count;

    FieldVsCapturedLocalDemo(int count) {
        this.count = count;
    }

    interface Reader {
        String read();
    }

    Reader createReader() {
        int snapshot = count;

        class ReaderImpl implements Reader {
            @Override
            public String read() {
                return "field=" + FieldVsCapturedLocalDemo.this.count
                        + ", snapshot=" + snapshot;
            }
        }

        return new ReaderImpl();
    }

    void setCount(int next) {
        count = next;
    }

    public static void main(String[] args) {
        FieldVsCapturedLocalDemo owner =
                new FieldVsCapturedLocalDemo(10);

        Reader reader = owner.createReader();
        System.out.println(reader.read());

        owner.setCount(99);
        System.out.println(reader.read());
    }
}
~~~

~~~bash
javac -encoding UTF-8 FieldVsCapturedLocalDemo.java
java FieldVsCapturedLocalDemo
~~~

Stdout:

~~~text
field=10, snapshot=10
field=99, snapshot=10
~~~

The core difference: `Outer.this.count` reads the field state of the retained object, whereas `snapshot` is a captured primitive local value. A local class can combine both semantics in the same method.

## 16. Reassigning a Local Reference Differs from Mutating the Referenced Object

Effectively final applies to **the variable**, and does not automatically freeze the object the variable points to.

~~~java
java.util.List<String> names =
        new java.util.ArrayList<>();

class Collector {
    void add(String name) {
        names.add(name); // Valid: names is not reassigned.
    }
}
~~~

`names.add` modifies the List object, but does not reassign the local variable `names`. Therefore, the capture is valid in either a static or instance method.

Conversely:

~~~java
// names = new ArrayList<>(); // If done, names is no longer effectively final.
~~~

Declaring the variable as `final` does not make the `ArrayList` thread-safe or immutable either. If a shared mutable object escapes the method or is used across threads, separate ownership/synchronization is required.

## 17. Runnable Program: Capturing a Mutable Reference in a Static Method

Create **`MutableCaptureDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class MutableCaptureDemo {
    static List<String> collect() {
        List<String> names = new ArrayList<>();

        class Collector {
            void add(String name) {
                names.add(name);
            }
        }

        Collector collector = new Collector();
        collector.add("Mai");
        collector.add("An");

        return names;
    }

    public static void main(String[] args) {
        System.out.println(collect());
    }
}
~~~

~~~bash
javac -encoding UTF-8 MutableCaptureDemo.java
java MutableCaptureDemo
~~~

Stdout:

~~~text
[Mai, An]
~~~

The method is static, yet the capture has no issue because the List reference is effectively final. The List contents remain mutable and are modified through Collector.

## 18. A Local Class Can Outlive Its Method

The scope of the local class name ends at the closing `}` of the block, but an object created from the local class can be returned via an accessible interface/superclass:

~~~java
static Runnable task(String message) {
    class PrintTask implements Runnable {
        @Override
        public void run() {
            System.out.println(message);
        }
    }

    return new PrintTask();
}
~~~

After `task(...)` returns, the caller cannot see the name `PrintTask`, but the object still exists and uses the captured message.

**This holds true for both static methods and instance methods.** The difference is that a local class in an instance method can retain the enclosing owner in addition to captured local values, if the implementation needs outer state.

## 19. Runnable Program: Task from Both Contexts

Create **`EscapingLocalClassDemo.java`**:

~~~java
public class EscapingLocalClassDemo {
    private final String owner;

    EscapingLocalClassDemo(String owner) {
        this.owner = owner;
    }

    Runnable fromInstance(String message) {
        class Task implements Runnable {
            @Override
            public void run() {
                System.out.println(owner + ":" + message);
            }
        }
        return new Task();
    }

    static Runnable fromStatic(String message) {
        class Task implements Runnable {
            @Override
            public void run() {
                System.out.println("static:" + message);
            }
        }
        return new Task();
    }

    public static void main(String[] args) {
        Runnable first = new EscapingLocalClassDemo("A")
                .fromInstance("hello");
        Runnable second = fromStatic("world");

        first.run();
        second.run();
    }
}
~~~

~~~bash
javac -encoding UTF-8 EscapingLocalClassDemo.java
java EscapingLocalClassDemo
~~~

Stdout:

~~~text
A:hello
static:world
~~~

Both local Task objects are retained after the factory method returns. The Task from the instance context uses the enclosing object state; the Task from the static context uses only the captured message and static-context code.

## 20. Can a Static Method Be Called via an Object Reference?

Java allows calling a static method through an expression in certain syntactic forms, though this is a style that should not be used:

~~~java
Owner owner = new Owner();
// owner.staticFactory(); // May be valid, but does not turn staticFactory into an instance method.
Owner.staticFactory();    // Use this style.
~~~

**Important:** Having an object as a syntactic qualifier does not make a local class inside staticFactory automatically receive an enclosing owner instance. A static method remains static; the instance reference does not become `Owner.this` for the local class.

If an owner is needed, make the parameter explicit:

~~~java
static Runnable factory(Owner owner) {
    // Create a local class capturing owner.
}
~~~

The explicit choice ensures correct semantics and avoids wrong expectations about `this`.

## 21. Static Fields and Instance Fields When Names Are Shadowed

Suppose Outer has:

~~~java
class Outer {
    private static int shared = 100;
    private int own = 10;
}
~~~

A local class in an instance method can read both `shared` and `Outer.this.own`. In a static method, only `shared` can be read without an explicit Outer reference.

If the local class has a field named `shared`:

~~~java
class Local {
    private int shared = 5;

    int sum() {
        return shared + Outer.shared;
    }
}
~~~

Unqualified `shared` refers to the Local field, whereas `Outer.shared` refers to the static field. If the local class needs an outer instance field, write `Outer.this.own` when the context permits.

**Remember:** `Outer.this` is an object-level reference; `Outer.shared` is class-level access.

## 22. Runnable Program: Static and Instance with the Same Name

Create **`FieldResolutionDemo.java`**:

~~~java
public class FieldResolutionDemo {
    private static int shared = 100;
    private int own = 10;

    String instanceView() {
        class Local {
            int shared = 5;

            String show() {
                return shared + "/" + FieldResolutionDemo.shared
                        + "/" + FieldResolutionDemo.this.own;
            }
        }

        return new Local().show();
    }

    static String staticView() {
        class Local {
            int shared = 7;

            String show() {
                return shared + "/" + FieldResolutionDemo.shared;
            }
        }

        return new Local().show();
    }

    public static void main(String[] args) {
        System.out.println(new FieldResolutionDemo().instanceView());
        System.out.println(staticView());
    }
}
~~~

~~~bash
javac -encoding UTF-8 FieldResolutionDemo.java
java FieldResolutionDemo
~~~

Stdout:

~~~text
5/100/10
7/100
~~~

The local fields and the outer static field share the same name, but they are distinct fields. `FieldResolutionDemo.this.own` is available only in the instance context; it does not exist in `staticView`.

## 23. Local Class in a Constructor: Instance Context and Initialization

A constructor is not a static method. A local class declared inside a constructor generally has access to the enclosing object in the appropriate context, and can capture final/effectively final constructor parameters.

However, **be careful when accessing incomplete state**. If a local object is published from a constructor or calls overridable methods while the object is still under construction, the code may observe fields that are not yet fully initialized.

A safe example is a local class performing validation on a constructor parameter before assigning a field:

~~~java
final class Amount {
    private final int value;

    Amount(int value) {
        class Validator {
            boolean positive() {
                return value > 0;
            }
        }
        if (!new Validator().positive()) {
            throw new IllegalArgumentException("non-positive");
        }
        this.value = value;
    }
}
~~~

This is an illustrative class (without a main); the local Validator reads the captured constructor parameter. For validating a single simple condition, using `if (value <= 0)` is less complex; a local class is not needed unconditionally.

## 24. Runnable Program: Constructor Local Class

Create **`ConstructorContextDemo.java`**:

~~~java
public class ConstructorContextDemo {
    static final class Interval {
        private final int length;

        Interval(int value) {
            class Validator {
                boolean valid() {
                    return value > 0;
                }
            }

            if (!new Validator().valid()) {
                throw new IllegalArgumentException("length must be positive");
            }
            length = value;
        }

        int length() {
            return length;
        }
    }

    public static void main(String[] args) {
        Interval first = new Interval(7);
        System.out.println("length=" + first.length());

        try {
            new Interval(0);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ConstructorContextDemo.java
java ConstructorContextDemo
~~~

Stdout:

~~~text
length=7
rejected=length must be positive
~~~

The constructor parameter `value` is not reassigned, so it is effectively final. The local Validator only uses the parameter, does not access partial object state, and does not publish `this`.

## 25. Local Class in an Instance Initializer

An instance initializer block executes during the construction of each object according to Java initialization order. A local class declared here has an instance context and can access outer members that have already been initialized in the appropriate order.

Create **`InstanceInitializerDemo.java`**:

~~~java
public class InstanceInitializerDemo {
    static final class Holder {
        private final String text;

        {
            class Formatter {
                String format() {
                    return "ready";
                }
            }

            text = new Formatter().format();
        }

        String text() {
            return text;
        }
    }

    public static void main(String[] args) {
        Holder holder = new Holder();
        System.out.println(holder.text());
    }
}
~~~

~~~bash
javac -encoding UTF-8 InstanceInitializerDemo.java
java InstanceInitializerDemo
~~~

Stdout:

~~~text
ready
~~~

The local Formatter is only visible inside the initializer block. The demo intentionally avoids reading uninitialized fields; in real code, understand the order of field initializers, instance initializer blocks, and constructor chaining before adding complex logic.

## 26. Local Class in a Static Initializer

A static initializer block executes when the class is initialized according to JVM semantics. There is no enclosing Outer instance; a local class here belongs to a static context.

Create **`StaticInitializerDemo.java`**:

~~~java
public class StaticInitializerDemo {
    private static final String STATUS;

    static {
        class Builder {
            String build() {
                return "initialized";
            }
        }

        STATUS = new Builder().build();
    }

    public static void main(String[] args) {
        System.out.println(STATUS);
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticInitializerDemo.java
java StaticInitializerDemo
~~~

Stdout:

~~~text
initialized
~~~

Do not mistake a local class in a static initializer for a static nested member class. `Builder` remains a local name inside the `static { ... }` block, not a `StaticInitializerDemo.Builder` that clients are allowed to use.

## 27. Inside Nested Blocks: Context Is Inherited by Lexical Position

The static/instance context of a local class depends on where it is declared:

~~~java
class Outer {
    void instanceMethod(boolean enabled) {
        if (enabled) {
            class InstanceLocal {
                String show() {
                    return Outer.this.toString();
                }
            }
        }
    }

    static void staticMethod(boolean enabled) {
        if (enabled) {
            class StaticLocal {
                String show() {
                    return "static";
                }
            }
        }
    }
}
~~~

A nested `if` block does not turn an instance method into static or vice versa. It only narrows the **scope of the local class name and local variables**.

### Name Scope

In the example above, `InstanceLocal` is not visible outside the `if` block. You cannot call `new InstanceLocal()` from code on lines after the block, even within the same instanceMethod.

Name scope does not cause the object to be destroyed automatically: if the object is assigned to a more accessible interface reference, it can continue living after the block.

## 28. A Static Nested Member Class Is Not a “Local Class in a Static Method”

The two declarations:

~~~java
class Outer {
    static class MemberNested {
    }

    static void method() {
        class MethodLocal {
        }
    }
}
~~~

are different:

- `MemberNested` is a **member class** declared in the class body, with the name `Outer.MemberNested`.
- `MethodLocal` is a **local class** declared in the method body, with a name only in method scope.
- `MemberNested` can be created from appropriate code using `new Outer.MemberNested()`.
- `MethodLocal` cannot be created using `new Outer.MethodLocal()` from outside.
- Neither in this example has an implicit enclosing Outer instance, but **the reasons regarding declaration scope are different**.

Do not use the phrase “static local class” as if there were a `static class Local` syntax directly inside a method. A local class declared in a static context is not **given the member modifier `static`** just because the method is static.

## 29. Comparison Example: Static Nested Member vs. Static-Method Local

Create **`NestedVsStaticLocalDemo.java`**:

~~~java
public class NestedVsStaticLocalDemo {
    static class MemberNested {
        String name() {
            return "member-nested";
        }
    }

    static String fromMethod() {
        class Local {
            String name() {
                return "method-local";
            }
        }
        return new Local().name();
    }

    public static void main(String[] args) {
        MemberNested nested = new MemberNested();

        System.out.println(nested.name());
        System.out.println(fromMethod());
        System.out.println("member=" +
                MemberNested.class.isMemberClass());
    }
}
~~~

~~~bash
javac -encoding UTF-8 NestedVsStaticLocalDemo.java
java NestedVsStaticLocalDemo
~~~

Stdout:

~~~text
member-nested
method-local
member=true
~~~

MemberNested.class.isMemberClass is true. A local class also has Class metadata, but its `isLocalClass()` is true; it is not a member class type.

## 30. Local Classes and Generic Method Type Parameters

In a generic instance or static method, a local class can reference type parameters in scope:

~~~java
static <T> String describe(T input) {
    class Description {
        String text() {
            return String.valueOf(input);
        }
    }
    return new Description().text();
}
~~~

`T` is a compile-time type parameter. The local class reads `input` because it is effectively final, not because there is an enclosing outer object.

In a similar generic instance method, a local class can also use `Outer.this` to access the outer instance. Generic context and static/instance context are **two independent axes**.

## 31. Runnable Program: Generic Local Class in Both Contexts

Create **`GenericContextsDemo.java`**:

~~~java
public class GenericContextsDemo {
    private final String prefix;

    GenericContextsDemo(String prefix) {
        this.prefix = prefix;
    }

    <T> String instanceDescribe(T input) {
        class Description {
            String text() {
                return prefix + String.valueOf(input);
            }
        }
        return new Description().text();
    }

    static <T> String staticDescribe(T input) {
        class Description {
            String text() {
                return "static:" + String.valueOf(input);
            }
        }
        return new Description().text();
    }

    public static void main(String[] args) {
        GenericContextsDemo demo = new GenericContextsDemo("owner:");

        System.out.println(demo.instanceDescribe(17));
        System.out.println(staticDescribe("Java"));
    }
}
~~~

~~~bash
javac -encoding UTF-8 GenericContextsDemo.java
java GenericContextsDemo
~~~

Stdout:

~~~text
owner:17
static:Java
~~~

Both generic methods have T used at compile time. There is no new Class object per generic argument due to type erasure.

## 32. A Local Class Can Also Have Its Own Type Parameters

~~~java
static void method() {
    class Holder<T> {
        private final T value;

        Holder(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    Holder<String> text = new Holder<>("Java");
    Holder<Integer> number = new Holder<>(17);
}
~~~

`Holder<T>` is a generic local class; its declaration still has lexical scope. It can be created with different type arguments within that block.

### Runnable Program

Create **`GenericLocalTypeDemo.java`**:

~~~java
public class GenericLocalTypeDemo {
    static void run() {
        class Holder<T> {
            private final T value;

            Holder(T value) {
                this.value = value;
            }

            T get() {
                return value;
            }
        }

        Holder<String> words = new Holder<>("Java");
        Holder<Integer> number = new Holder<>(17);

        System.out.println("words=" + words.get());
        System.out.println("number=" + number.get());
        System.out.println("same runtime type=" +
                (words.getClass() == number.getClass()));
    }

    public static void main(String[] args) {
        run();
    }
}
~~~

~~~bash
javac -encoding UTF-8 GenericLocalTypeDemo.java
java GenericLocalTypeDemo
~~~

Stdout:

~~~text
words=Java
number=17
same runtime type=true
~~~

Each instance differs in value and generic T at compile time, but belongs to the same erased runtime local class type in the same defining-loader context.

## 33. Local Classes Have Constructors, Instance Fields, and Interfaces in Both Contexts

Even though the declaration is inside a static method, a local class is **not restricted to being a static utility**. It can still have instance fields, constructors, methods, and implement an interface.

~~~java
static Runnable makeJob(String text) {
    class Job implements Runnable {
        private final String message;

        Job(String message) {
            this.message = message;
        }

        @Override
        public void run() {
            System.out.println(message);
        }
    }

    return new Job(text);
}
~~~

The Job object has its own instance field. Its constructor accepts an explicit String. No Outer instance is needed because Job is declared in a static context; the presence of an instance field in Job does not change that.

In an instance method, a similar structure can also be written while accessing outer instance state if needed.

## 34. Java 17: Static Declarations Inside a Local Class

Some older textbooks (prior to Java SE 16) state that inner classes cannot declare static methods/fields, except for constant variables. **Java SE 16 relaxed this restriction**, so in **Java 17**, a local class can have static methods according to current Java language rules.

This **does not change** the fact that a local class resides inside a block and does not change the existence of an outer instance in the declaring context.

### Runnable Program

Create **`StaticMemberInLocalDemo.java`**:

~~~java
public class StaticMemberInLocalDemo {
    static int compute() {
        class LocalMath {
            static int doubleOf(int value) {
                return value * 2;
            }

            int increment(int value) {
                return value + 1;
            }
        }

        return LocalMath.doubleOf(4)
                + new LocalMath().increment(2);
    }

    public static void main(String[] args) {
        System.out.println("result=" + compute());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 StaticMemberInLocalDemo.java
java StaticMemberInLocalDemo
~~~

Stdout:

~~~text
result=11
~~~

`LocalMath` is declared inside a static method, yet the `increment` method is an instance method of the LocalMath object itself, while `doubleOf` is a static method of LocalMath. The class name LocalMath is still visible only inside the compute block.

**Note:** A static method of a local class does not automatically have a receiver for local/outer instances. Do not expect it to use `Outer.this` or captured method locals like an instance method.

## 35. A Local Record Is Implicitly Static, Even in an Instance Method

Java 17 allows **local record declarations**:

~~~java
void process(int input) {
    record Pair(int left, int right) {}

    Pair pair = new Pair(input, 2);
}
~~~

A local record has **implicitly static semantics**. It cannot directly capture `Outer.this` or local variables from the enclosing method inside the record body like an ordinary local class. To use data from the context, **pass it through record components/constructor**.

Subtle point: **A record declared inside an instance method** does not gain an enclosing Outer instance just because of that location. A record has the characteristics specific to static nested record declarations.

## 36. Runnable Program: Local Class vs. Local Record in an Instance Method

Create **`LocalRecordContrastDemo.java`**:

~~~java
public class LocalRecordContrastDemo {
    private final int factor;

    LocalRecordContrastDemo(int factor) {
        this.factor = factor;
    }

    int calculate(int input) {
        class LocalCalculator {
            int result() {
                return LocalRecordContrastDemo.this.factor * input;
            }
        }

        record Pair(int left, int right) {
            int product() {
                return left * right;
            }
        }

        LocalCalculator calculator = new LocalCalculator();
        Pair pair = new Pair(factor, input);

        System.out.println("class=" + calculator.result());
        System.out.println("record=" + pair.product());

        return pair.product();
    }

    public static void main(String[] args) {
        new LocalRecordContrastDemo(4).calculate(5);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 LocalRecordContrastDemo.java
java LocalRecordContrastDemo
~~~

Stdout:

~~~text
class=20
record=20
~~~

LocalCalculator reads the outer field directly. Pair does not capture Outer; `factor` and `input` are explicitly passed to the record components at `new Pair(factor, input)`.

## 37. A Local Enum Has No Enclosing Instance, Even in an Instance Method

A local enum has **implicitly static** semantics whether declared in an instance method or a static method. It is still a named type within the block, but the enum body cannot automatically access `Outer.this` or fields of a particular outer instance:

~~~java
class Outer {
    int value = 8;

    void instanceWork() {
        enum State { NEW, DONE }
        System.out.println(State.NEW.name());
        // Enum State does not automatically capture an Outer instance.
    }

    static void staticWork() {
        enum State { NEW, DONE }
        System.out.println(State.DONE.name());
    }
}
~~~

This is a **class fragment**, where the two `State` enums are two distinct type declarations according to their lexical location. If outer data is needed, pass it to a collaborator or handle it outside the enum body. The local enum/record lesson covers constants, constructors, and explicit data flow in depth; here the focus is distinguishing **declaration location** from the **enclosing instance relationship**.

## 38. `this` in a Lambda Differs from `this` in a Local Class

In an instance method of outer:

- `this` in a **method of a local class** points to the local object.
- `Outer.this` in a local class points to the outer object.
- `this` inside a **lambda** uses the lexical `this` of the enclosing context, typically the outer object.

In a static method, there is no outer `this` to use from a lambda; a local class still has its instance `this` when a method of the local class is invoked.

### Runnable Program: Identity of `this`

Create **`LambdaVsLocalThisDemo.java`**:

~~~java
public class LambdaVsLocalThisDemo {
    private final String id;

    LambdaVsLocalThisDemo(String id) {
        this.id = id;
    }

    void compare() {
        class Local {
            String who() {
                return "local:" +
                        (this instanceof Local) + ":" +
                        LambdaVsLocalThisDemo.this.id;
            }
        }

        java.util.function.Supplier<String> lambda =
                () -> "lambda:" + this.id;

        System.out.println(new Local().who());
        System.out.println(lambda.get());
    }

    public static void main(String[] args) {
        new LambdaVsLocalThisDemo("A").compare();
    }
}
~~~

~~~bash
javac -encoding UTF-8 LambdaVsLocalThisDemo.java
java LambdaVsLocalThisDemo
~~~

Stdout:

~~~text
local:true:A
lambda:A
~~~

A lambda does not declare a local class name and does not share the same `this` semantics. It is not simply a local class with shorter syntax in every respect.

## 39. The Name Scope of a Local Class Does Not Change Between Static and Instance

In both contexts, a local class name has scope from its declaration until the end of the enclosing block:

~~~java
static void example() {
    {
        class Local {}
        Local first = new Local();
    }

    // Local second = new Local(); // Compile error: out of scope.
}
~~~

The same applies in an instance method. The method being static does not turn the local class into a member type `Outer.Local` accessible from outside.

### Two Local Classes with the Same Simple Name in Two Methods

If instanceMethod declares `class Task` and staticMethod also declares `class Task`, these are **two separate declarations**, not one shared Java class just because the name is identical. Each class has its own lexical declaring location.

Do not infer class identity solely from `getSimpleName()`; generated binary names/class loaders determine runtime type identity.

## 40. Runtime Metadata Is Not the Enclosing Object

Reflection can return:

- `type.isLocalClass()` — true for a local class.
- `type.getEnclosingMethod()` — enclosing method metadata when the local class is declared inside a method.
- `type.getEnclosingConstructor()` — constructor metadata if the local class is declared inside a constructor.
- `type.getEnclosingClass()` — the Class object of the enclosing type.
- `type.getDeclaringClass()` — typically null for a local class because it is not a member class.

**Important:** `getEnclosingClass()` returns a **Class metadata object**, not a specific **Outer instance**. Reflection does not provide `getCapturedOuterObject()` by default through the Class API.

To distinguish a local class in a static method from one in an instance method, you can inspect the modifiers of `getEnclosingMethod()` together with behavior, rather than treating `isLocalClass` alone as sufficient.

## 41. Runnable Program: Reflection Distinguishes the Two Contexts

Create **`LocalContextMetadataDemo.java`**:

~~~java
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;

public class LocalContextMetadataDemo {
    Class<?> instanceType() {
        class InstanceLocal {}
        return InstanceLocal.class;
    }

    static Class<?> staticType() {
        class StaticLocal {}
        return StaticLocal.class;
    }

    public static void main(String[] args) {
        LocalContextMetadataDemo owner =
                new LocalContextMetadataDemo();

        Class<?> a = owner.instanceType();
        Class<?> b = staticType();

        Method m1 = a.getEnclosingMethod();
        Method m2 = b.getEnclosingMethod();

        System.out.println("instance local=" + a.isLocalClass());
        System.out.println("static local=" + b.isLocalClass());
        System.out.println("first method=" + m1.getName());
        System.out.println("second method=" + m2.getName());
        System.out.println("first is static=" +
                Modifier.isStatic(m1.getModifiers()));
        System.out.println("second is static=" +
                Modifier.isStatic(m2.getModifiers()));
    }
}
~~~

~~~bash
javac -encoding UTF-8 LocalContextMetadataDemo.java
java LocalContextMetadataDemo
~~~

Stdout:

~~~text
instance local=true
static local=true
first method=instanceType
second method=staticType
first is static=false
second is static=true
~~~

Both are local classes. Reflection knows the enclosing **method declaration**, not “an owner object of all instances”; a local class in a static context also has enclosing class metadata.

## 42. Reflection Constructors and Captured Parameters: Do Not Rely on Synthetic Details

The compiler may represent captured locals, the enclosing instance, or other captured values using synthetic fields/constructor parameters in bytecode. These details serve the implementation of Java language semantics.

- Do not hardcode `this$0` or other synthetic field names.
- Do not assume the constructor signature matches the source declaration merely by looking at the parameter count via reflection.
- Do not rely on generated binary class names like `Outer$1Local` to distinguish between static and instance contexts.
- Prefer creating the local object with `new Local(...)` directly within lexical scope.
- If reflection is unavoidable, rely on public `Class/Method/Constructor` APIs and check their contracts.

Local classes and anonymous classes have compiler-generated names; the name/number contents may differ depending on the compiler, version, or source changes.

## 43. An Enclosing Method Does Not Mean Each Call Creates a New Class Object

If a method contains `class Task` and returns `new Task()`, multiple method calls can create multiple Task **instances**, but they are instances of the **same runtime local class definition** within a class-loader context.

Example:

~~~java
static Runnable task(String text) {
    class Task implements Runnable {
        public void run() {
            System.out.println(text);
        }
    }
    return new Task();
}
~~~

The two objects have different captured texts, yet `a.getClass() == b.getClass()` is true in the same runtime environment.

### Runnable Program

Create **`LocalClassIdentityDemo.java`**:

~~~java
public class LocalClassIdentityDemo {
    static Runnable task(String text) {
        class Task implements Runnable {
            @Override
            public void run() {
                System.out.println(text);
            }
        }
        return new Task();
    }

    public static void main(String[] args) {
        Runnable a = task("A");
        Runnable b = task("B");

        System.out.println("same object=" + (a == b));
        System.out.println("same Class=" +
                (a.getClass() == b.getClass()));
        a.run();
        b.run();
    }
}
~~~

~~~bash
javac -encoding UTF-8 LocalClassIdentityDemo.java
java LocalClassIdentityDemo
~~~

Stdout:

~~~text
same object=false
same Class=true
A
B
~~~

A static context does not turn each invocation into a separate class type. Captured state is **per-instance behavior/data**, not a new class for each argument.

## 44. Static Nested Code and Enclosing Static Method: What Can Be Captured?

A local class inside a static method of a **static nested class** also does not automatically have an enclosing object of the nested class:

~~~java
class Outer {
    static class Helper {
        private final String id;

        Helper(String id) {
            this.id = id;
        }

        static Runnable fromStatic(Helper helper) {
            class Task implements Runnable {
                public void run() {
                    System.out.println(helper.id);
                }
            }
            return new Task();
        }
    }
}
~~~

Task has the explicit `helper` reference, and does not have `Outer.this` or `Helper.this` because the declaration is in a static method. However, if Helper declares an instance method containing a local class, it can access `Helper.this` — which is the **Helper instance**, without automatically having an enclosing Outer instance because Helper is a static nested member class.

**Conclusion:** Identify precisely **which class has a receiver**, rather than merely looking at a chain of nested class names.

## 45. Instance Method of an Inner Member Class: Multiple Levels of Enclosing Instances

If `Inner` is a **non-static member class** of Outer, and it declares an instance method with a local class:

~~~java
class Outer {
    private final String name;

    Outer(String name) {
        this.name = name;
    }

    class Inner {
        Runnable task() {
            class LocalTask implements Runnable {
                public void run() {
                    System.out.println(Outer.this.name);
                }
            }
            return new LocalTask();
        }
    }
}
~~~

LocalTask is declared in **the instance context of Inner**, and can validly reference `Outer.this` through the enclosing instance relationships. It does not need to create another Outer itself.

In the static context of a static nested class, this chain of enclosing instances does not exist in that way.

### Do Not Overuse

When code has multiple levels such as Outer.Inner.Local, qualified `this` can become hard to read. It is often better to extract the dependency into an explicit interface/constructor argument if only a small value is needed.

## 46. Runnable Program: Multiple Enclosing Levels

Create **`MultiLevelContextDemo.java`**:

~~~java
public class MultiLevelContextDemo {
    private final String label;

    MultiLevelContextDemo(String label) {
        this.label = label;
    }

    class Inner {
        Runnable task(String suffix) {
            class LocalTask implements Runnable {
                @Override
                public void run() {
                    System.out.println(
                            MultiLevelContextDemo.this.label + ":" + suffix);
                }
            }
            return new LocalTask();
        }
    }

    public static void main(String[] args) {
        MultiLevelContextDemo outer = new MultiLevelContextDemo("A");
        Inner inner = outer.new Inner();
        Runnable task = inner.task("done");

        task.run();
    }
}
~~~

~~~bash
javac -encoding UTF-8 MultiLevelContextDemo.java
java MultiLevelContextDemo
~~~

Stdout:

~~~text
A:done
~~~

In static main, creating `Inner` requires `outer.new Inner()`; after that, the instance method `inner.task(...)` has sufficient context to create LocalTask. The code does not infer an enclosing outer from static main.

## 47. Static and Instance Contexts in Callbacks/Lifecycles

A local class returned as a `Runnable` can be stored in an event listener registry or executor queue longer than the method that created it.

- A local class from an instance method that uses outer state can keep Outer reachable.
- A local class from a static method that captures an explicit Outer reference can also keep Outer reachable.
- A local class from a static method that uses only a small String snapshot may not need to retain the owner object.
- Lambdas/anonymous classes also have capture semantics and retention risks when required by the reference graph.

**The `static` keyword is not a cure for memory leaks.** If you capture a large service/entity reference and hold the task in a global registry, the resource can still be kept alive. Unregister callbacks/close lifecycles according to API contracts.

## 48. Thread Safety Does Not Come Automatically from Effectively Final

A captured local reference can point to a mutable List, Map, counter, or object graph. Multiple threads calling local-class methods concurrently can cause a data race if proper synchronization is not used.

For example:

~~~java
static Runnable task(java.util.List<String> shared) {
    class LocalTask implements Runnable {
        public void run() {
            shared.add("x");
        }
    }
    return new LocalTask();
}
~~~

The `shared` parameter is effectively final, yet `ArrayList.add` is not automatically thread-safe. Synchronized ownership, concurrent collections, immutable snapshots, or an appropriate threading design are required.

### Runnable Program: Thread-Safe Counter via Capture

Create **`AtomicCaptureDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicCaptureDemo {
    static Runnable incrementer(AtomicInteger target) {
        class IncrementTask implements Runnable {
            @Override
            public void run() {
                target.incrementAndGet();
            }
        }
        return new IncrementTask();
    }

    public static void main(String[] args) {
        AtomicInteger counter = new AtomicInteger();
        Runnable increment = incrementer(counter);

        increment.run();
        increment.run();

        System.out.println("counter=" + counter.get());
    }
}
~~~

~~~bash
javac -encoding UTF-8 AtomicCaptureDemo.java
java AtomicCaptureDemo
~~~

Stdout:

~~~text
counter=2
~~~

AtomicInteger guarantees atomic increment semantics for that operation; the effectively-final rule only protects the parameter target from being reassigned, and does not create synchronization for the mutable object.

## 49. Memory/CPU: Choose a Local Class When Justified

A local named class can be useful when you need:

- A small, meaningful implementation used only within a single method/block.
- Multiple instance methods or instance fields.
- A parameterized constructor to create configurable behavior.
- To implement an interface and hide the concrete type from the public API.
- To capture a few clear final/effectively final dependencies.

There is no need to create a local class for a simple addition. If logic needs to be reused across multiple methods, a private static nested/top-level class or a helper method may be clearer and more test-friendly.

**Design rule:** Declare in an instance context when the behavior genuinely depends on the enclosing owner; use a static context or explicit dependencies when the owner is unnecessary. Do not move a class merely to work around the compiler while forgetting to update the ownership contract.

## 50. Comparison Table of Five Options

| Option | Named inside block? | Outer instance access | Local capture |
| --- | --- | --- | --- |
| Local class in instance method | Yes | Can use `Outer.this` | Final/effectively final |
| Local class in static method | Yes | No implicit `Outer.this` | Final/effectively final |
| Static nested member class | Not local; has member type name | No implicit Outer instance | Does not capture arbitrary method locals |
| Anonymous class in instance context | No simple name declaration | Can use outer instance | Final/effectively final |
| Lambda in instance context | No class name in source | Lexical `this` of outer | Final/effectively final |

If you need a **local record** inside an instance method, remember that it is implicitly static and receives surrounding values via its constructor/components; do not treat it as an ordinary capture-enabled local inner class.

## 51. Common Errors and Fixes

| Error | Cause | Fix |
| --- | --- | --- |
| `Outer.this` in a static-method local class | No enclosing Outer instance | Pass `Outer target` explicitly |
| Reading `outerField` in a static-method local class | Instance field requires a receiver | `target.outerField` |
| `return localVar` after `localVar++` | Variable is not effectively final | Do not reassign; pass value into constructor |
| Using `this` expecting Outer from a local-class instance method | `this` is the Local instance | Use `Outer.this` in an instance context |
| Expecting captured int to update with a mutable outer field | Capturing local value differs from outer-field lookup | Read `Outer.this.field` when live state is needed |
| Reassigning a captured List to another List | Reassignment breaks effectively final | Do not reassign the local or use an explicit holder |
| Thinking `names.add` breaks effectively final | Mutating object differs from reassignment | Capture is valid, but manage mutability |
| Calling `new Outer.Local()` | Local is not an Outer member type | `new Local()` in scope |
| Calling `Outer.this` in a local record | Local record is implicitly static | Pass data via components |
| Thinking Java 17 forbids static methods in a local class | Outdated rule prior to Java SE 16 | Use Java 17 syntax when genuinely needed |
| Letting a task escape constructor and use partial state | Object is not finished constructing | Do not publish `this` prematurely |
| Storing a callback long-term and forgetting cleanup | Captured refs keep resources reachable | Lifecycle/unregister/ownership |
| Letting multiple threads modify a captured ArrayList | Not thread-safe | Synchronization/concurrent structure |
| Parsing `Outer$1Local` name as a contract | Generated names are unstable | Use Reflection APIs |
| Treating static context as “cannot create objects” | A static method can still call `new Local()` | No outer instance, yet local objects still work normally |

## 52. Exercise 1 — Comparing Instance and Static

Given:

~~~java
class Sample {
    int own = 4;
    static int shared = 8;

    int runInstance() {
        class Local {
            int x() { return Sample.this.own + shared; }
        }
        return new Local().x();
    }

    static int runStatic() {
        class Local {
            int x() { return shared; }
        }
        return new Local().x();
    }
}
~~~

**Answer:** `new Sample().runInstance()` returns 12; `Sample.runStatic()` returns 8. The instance local reads own+shared; the static local reads only shared.

## 53. Exercise 2 — Why Does It Error?

~~~java
static void run() {
    int number = 10;
    number++;
    class Local {
        int value() {
            // return number;
            return 0;
        }
    }
}
~~~

**Answer:** If return number is uncommented, the compiler rejects the capture because number was reassigned via ++ and is no longer effectively final. The static context is not the cause of the capture error.

## 54. Exercise 3 — Can a Mutable Reference Be Captured?

~~~java
static void run() {
    java.util.List<String> list =
            new java.util.ArrayList<>();

    class Local {
        void add() {
            list.add("Java");
        }
    }

    new Local().add();
}
~~~

**Answer:** Valid. The list variable is not reassigned; `add` mutates the List object. Do not automatically infer thread safety.

## 55. Exercise 4 — Capture vs. Field

A local class in an instance method has `int snapshot = owner.count`, and a method of the local class reads both `snapshot` and `Owner.this.count`. Owner.count changes from 5 to 9.

**Answer:** snapshot remains 5; the field lookup returns 9. Snapshot is a captured primitive local value, whereas the field lookup reads the current state of the enclosing object.

## 56. Exercise 5 — Static Method Receiving Outer

~~~java
static Runnable task(Outer owner) {
    class Local implements Runnable {
        public void run() {
            System.out.println(owner.id);
        }
    }
    return new Local();
}
~~~

**Answer:** Valid if Outer.id is accessible under nesting rules and owner is not reassigned; the local class captures the explicit owner reference. It does not have an automatic `Outer.this`.

## 57. Exercise 6 — `this` in a Static-Method Local Class

Inside `static void method()`, declare `class Local { boolean check(){ return this instanceof Local; }}` and then call `new Local().check()`.

**Answer:** Valid and returns true. `this` in Local.check is the Local object; a static context only forbids **an enclosing Outer.this**, not instance methods of Local.

## 58. Exercise 7 — Local Record in an Instance Method

~~~java
int compute(int n) {
    record Pair(int a, int b) {
        int sum() { return a + b; }
    }
    return new Pair(n, 2).sum();
}
~~~

**Answer:** Valid in Java 17. Pair receives n via its constructor and **does not directly capture** the parameter n from the body of the local record. The result is n+2.

## 59. Exercise 8 — Distinguishing Local and Member Nested

In `static void work() { class Helper {} }`, can `new Outer.Helper()` be created elsewhere?

**Answer:** No. Helper is a local class whose name is scoped only to work. If access from multiple methods is needed, declare `static class Helper` in the class body, not inside a method.

## 60. Exercise 9 — Runtime Class Metadata

An instance-method local class and a static-method local class both call `getClass().isLocalClass()`. Result?

**Answer:** Both are true. To know whether the enclosing method has the static modifier, use `getEnclosingMethod()` and `Modifier.isStatic(...)` from the metadata.

## 61. Exercise 10 — Lifecycle and Capture

An instance method returns a local Runnable using `Outer.this`. The caller stores the Runnable in a global registry for a long time. What is the risk?

**Answer:** The Runnable can keep the enclosing Outer reachable, extending the lifecycle of Outer. Ownership/unregistration is needed. Creating a task in a static method and capturing an explicit Outer reference carries a similar risk.

## 62. End-of-Lesson Checklist

- [ ] I know a local class is a named class declared inside a block.
- [ ] I do not confuse a local class with a static nested member class.
- [ ] I understand that the lexical enclosing class and the enclosing object are not the same.
- [ ] I know an instance-method local class can use Outer.this.
- [ ] I know a static-method local class does not have Outer.this.
- [ ] I know a local class in a static context still has its own `this`.
- [ ] I know a static method can call new Local inside the block.
- [ ] I pass an explicit owner reference if static logic needs an instance.
- [ ] I distinguish static field access from instance field access.
- [ ] I distinguish a captured local value from an outer field lookup.
- [ ] I know captured locals/parameters must be final or effectively final.
- [ ] I know ++ and reassignment cause a variable to lose effectively final status.
- [ ] I do not treat a captured mutable reference as an immutable object.
- [ ] I know a local object can outlive its method via an interface.
- [ ] I know a local class in a constructor/instance initializer has an instance context.
- [ ] I know a static initializer does not have Outer.this.
- [ ] I do not publish a partial object from a constructor.
- [ ] I correctly read shadowing of local class fields and outer members.
- [ ] I know generic local classes and generic method type parameters.
- [ ] I understand Java 17 allows static declarations inside a local class.
- [ ] I do not confuse an implicitly static local record/enum with an ordinary local class.
- [ ] I distinguish lambda lexical this from local-class this.
- [ ] I know class metadata `isLocalClass` does not provide the enclosing instance object.
- [ ] I use `getEnclosingMethod` and Modifier when I need to check the context.
- [ ] I do not hardcode compiler-generated class names.
- [ ] I understand the lifetime of captured references and memory retention.
- [ ] I know effectively final does not automatically solve concurrency.
- [ ] I choose a static nested/top-level class when logic needs to be reused.
- [ ] I can explain the Java 17+ programs and exercises above.

**Conclusion:** A **local class in an instance context** can access the enclosing instance via `Outer.this` together with outer instance members; a **local class in a `static` context** has no implicit enclosing object, yet still has its own instances, constructors, methods, and captures final/effectively final locals. This difference belongs to **the declaration location and context**, not a local class in a static method becoming a static nested member class. When an owner is needed in static code, **pass the reference explicitly**; when a snapshot is needed, capture immutable values; and when a local object escapes the block, manage mutability, lifetime, and thread safety according to the contract.
