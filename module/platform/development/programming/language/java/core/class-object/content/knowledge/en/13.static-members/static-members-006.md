# Static Blocks and Class-Level Data Initialization in Java

## Learning Objectives

After this lesson, you can:

- Explain `static field`, `static initializer block`, and the **initialization of a class/interface** in Java; distinguish them from the data and initializer blocks of individual objects.
- Predict the evaluation order of **static field initializers** and **static blocks** according to their order of appearance in source code, after the default-value preparation step.
- Identify the situations that typically cause the JVM to **initialize a class for the first time**, and distinguish *loading*, *linking*, and *initialization*.
- Distinguish a `static final` **constant variable** with a compile-time constant value from a `static final` computed at class initialization time.
- Recognize the **illegal forward reference** restriction, the difference between accessing via a simple name and a qualified name, and logic bugs caused by reading default values too early.
- Understand the relationship between superclass, subclass, and interface initialization; avoid inferring that every mentioned class has already been initialized.
- Explain why a `static` block runs once per **class initialization by a defining class loader**, rather than per object or per method call.
- Identify the consequences of exceptions during static initialization, circular dependency risks, and the impact when multiple threads concurrently use a class.
- Design safe class-level data: immutable configuration, unmodifiable collections, static factories, and the *initialization-on-demand holder* technique.
- Compile/run Java 17+ examples and verify stdout accurately.

## 1. Static Members Are Data/Behavior Belonging to the Class

An **instance field** is tied to each object created with `new` (or an equivalent instance-creation mechanism); each instance typically has its own field state.

A **static field** is associated with the class declaration at runtime and is shared by code that sees the **same runtime class**. It is not recreated each time an object is created with `new`.

~~~java
class Counter {
    static int totalCreated;
    int id;

    Counter() {
        totalCreated++;
        id = totalCreated;
    }
}
~~~

This is an **illustrative declaration**, without `main` yet. After two sequential `new Counter()` creations in a single thread, `Counter.totalCreated` has the value 2, while each object has a different `id` according to the constructor logic.

However, `totalCreated++` is **not automatically thread-safe** just because the field is `static`. `static` describes what a member belongs to and its relative lifecycle; it does not provide synchronization.

### 1.1. Static Block Syntax

A class can contain one or more **static initializer blocks**:

~~~java
class Settings {
    static int timeoutSeconds;

    static {
        timeoutSeconds = 30;
        System.out.println("Settings initialized");
    }
}
~~~

The `static { ... }` block runs when the **class is initialized**, according to Java/JVM rules. It has no name, takes no parameters, has no return type, and is not called like an ordinary method.

You cannot write `Settings.staticBlock()` to "re-run" a static block. If you want to run an operation multiple times, place that operation in a separate method, and you can call that method from the static block when needed.

### 1.2. `static` in the Class Body vs. a Static Local Variable

Java does not support C/C++-style local variable declarations like `static int count;` directly inside a method to keep a local variable alive across multiple calls. For shared state, declare a **static field** at the class level, or use an object/class responsible for state according to your design.

~~~java
class Example {
    private static int calls;

    static void run() {
        calls++;
        int local = calls;
        System.out.println(local);
    }
}
~~~

`calls` is a static field. `local` is a local variable created on each call to `run()`. Both hold the same value at a given point in the example, but they belong to two different scopes and storage mechanisms.

## 2. Two Common Ways to Initialize Static Fields

**Approach 1 — directly at declaration:**

~~~java
class MathConstants {
    static final int BASE = 10;
    static final int SQUARED_BASE = BASE * BASE;
}
~~~

The expressions are assigned in the field declarators. The two values here are primitive-type constant expressions, which will be explained in detail in the *constant variables* section.

**Approach 2 — static initializer block:**

~~~java
class CacheConfig {
    static final java.util.Map<String, Integer> LIMITS;

    static {
        java.util.Map<String, Integer> data = new java.util.HashMap<>();
        data.put("FREE", 3);
        data.put("PRO", 20);
        LIMITS = java.util.Map.copyOf(data);
    }
}
~~~

A static block is useful when the data requires multiple computation steps or validation. `LIMITS` is `static final`: the field must be assigned in accordance with the definite assignment rules for a blank final field; once assigned, it cannot be reassigned at arbitrary places.

**Note:** `final` on `Map` only locks the **reference field**; whether the map itself is modifiable still depends on the object held. Here, `Map.copyOf` returns a map that cannot be modified through the standard API. If the values are mutable objects, those objects themselves can still be shared.

### 2.1. A Static Block Can Declare Local Variables

~~~java
static {
    int parsed = 12;
    // parsed only has scope within this block.
}
~~~

The variable `parsed` is local to the static block and does not become a class-level field. If you want methods to use the value afterward, you must assign it to a static field or store it in an appropriate object.

### 2.2. A Static Block Cannot Use `this` or `super`

`this` and `super` carry the meaning of an **instance** in appropriate contexts. A static initializer executes at the class-initialization level, without a "current object":

~~~java
class InvalidExample {
    int count = 1;

    static {
        // System.out.println(this.count); // Does not compile.
        // System.out.println(count);      // No instance receiver.
    }
}
~~~

You can access **static members**, call static methods, or explicitly create an object inside the block, but you cannot implicitly assume there is an instance of the class in order to use `this`.

## 3. Basic Class Initialization Sequence

At the Core Java learning level, a useful model is:

1. The runtime needs the class and performs the **loading/linking** steps according to the JVM mechanism.
2. During the **preparation** phase, static fields are allocated their appropriate default values (`0`, `false`, `null`...), and certain `static final` cases with a `ConstantValue` are handled according to JVM rules.
3. When the class is **initialized**, the JVM ensures that the relevant superclasses are initialized first according to the rules, along with superinterface cases that have default methods per the JLS.
4. Java executes the class's **static field initializer expressions** and **static initializer blocks** in their **order of appearance in the class body**. They participate together in the initialization process, not "all fields first and then blocks".
5. Once this succeeds, the class is in the initialized state. Reusing the class within the same runtime/defining-loader context does not automatically re-run those initializers.

In source code, you commonly observe two things: **declaration order** and **one-time initialization** (except for cases of a separate runtime class from a different loader, or rerunning the entire process).

### 3.1. Static Field Before/After a Static Block

Save the file **`StaticOrderDemo.java`**:

~~~java
public class StaticOrderDemo {
    static int first = log("first field", 10);

    static {
        System.out.println("block one: first=" + first);
    }

    static int second = log("second field", 20);

    static {
        System.out.println("block two: second=" + second);
    }

    private static int log(String name, int value) {
        System.out.println(name + "=" + value);
        return value;
    }

    public static void main(String[] args) {
        System.out.println("main: " + first + "," + second);
    }
}
~~~

Compile/run with JDK 17 or later:

~~~bash
javac StaticOrderDemo.java
java StaticOrderDemo
~~~

**Output:**

~~~text
first field=10
block one: first=10
second field=20
block two: second=20
main: 10,20
~~~

Order analysis:

- Before executing `main`, the `StaticOrderDemo` class must be initialized.
- `first = log(...)` runs first and prints `first field=10`.
- The first static block prints the assigned value of `first`.
- `second = log(...)` runs next.
- The second static block prints `second`.
- Only then does `main` print the final line.

It is **incorrect** to say that static blocks always run before all static field initializers; together they are ordered by **textual order** in the class.

### 3.2. Methods Can Be Declared Below

In the example, the `log` method is placed after the fields/blocks that call it. The method calls are still valid because method declarations in a class have their own naming/scoping rules. That does **not** mean the method runs beforehand: it is only executed when an initializer calls it.

## 4. Initializing Only When Needed According to Java Rules

A class is not necessarily initialized as soon as the virtual machine starts, merely because the source code contains that class name or a `.class` file exists on the classpath.

Situations that typically trigger initialization of a class `Target` include:

- Creating an instance with `new Target()` when Target is not yet initialized.
- Calling a **static method declared by Target** under the active-use rules.
- Reading or assigning a **static field declared by Target** if that field is not a qualifying constant variable.
- Certain reflection operations, such as `Class.forName(String)` which requests initialization by default.
- Starting the class containing the `main` method in a normal application.

The JLS precisely defines the triggers; you should not treat a simplistic rule of thumb like "mentioning a class name initializes the class" as an absolute rule.

### 4.1. Example of a Class Initialized Only on First Use

Save **`InitializeOnceDemo.java`**:

~~~java
public class InitializeOnceDemo {
    static class Config {
        static int VALUE = initialize();

        static {
            System.out.println("Config static block");
        }

        private static int initialize() {
            System.out.println("Config field initialized");
            return 7;
        }
    }

    public static void main(String[] args) {
        System.out.println("main begins");
        System.out.println("first access=" + Config.VALUE);
        System.out.println("second access=" + Config.VALUE);
        new Config();
        System.out.println("main ends");
    }
}
~~~

Run:

~~~bash
javac InitializeOnceDemo.java
java InitializeOnceDemo
~~~

Output:

~~~text
main begins
Config field initialized
Config static block
first access=7
second access=7
main ends
~~~

- `InitializeOnceDemo` is initialized to run `main`; however, `Config` is a separate nested class and is not necessarily initialized from the start.
- On the first read of `Config.VALUE`, the JVM initializes `Config`: running the field initializer and then the static block.
- The second read does not re-run the initialization process.
- `new Config()` creates a new object but does **not** re-run the static field/block of the already initialized `Config`.

Placing the nested class in this file allows the example to run standalone; in essence, it is still a `Config` class at runtime.

## 5. Distinguishing Static Initialization from Instance Initialization

**Static initialization:** logic belonging to the **class**, which runs when the class is initialized.

**Instance initialization:** logic belonging to **each object**, occurring during the constructor process when creating a new instance. It can use instance field initializers and **instance initializer blocks** `{ ... }` without `static`.

Save **`StaticVersusInstanceDemo.java`**:

~~~java
public class StaticVersusInstanceDemo {
    private static int nextId = boot();

    static {
        System.out.println("static block");
    }

    private final int id;

    {
        System.out.println("instance block");
    }

    StaticVersusInstanceDemo() {
        id = ++nextId;
        System.out.println("constructor id=" + id);
    }

    private static int boot() {
        System.out.println("static field initializer");
        return 100;
    }

    public static void main(String[] args) {
        System.out.println("main starts");
        new StaticVersusInstanceDemo();
        new StaticVersusInstanceDemo();
        System.out.println("nextId=" + nextId);
    }
}
~~~

Run:

~~~bash
javac StaticVersusInstanceDemo.java
java StaticVersusInstanceDemo
~~~

Output:

~~~text
static field initializer
static block
main starts
instance block
constructor id=101
instance block
constructor id=102
nextId=102
~~~

**Explanation:**

1. `nextId = boot()` and the static block run once before `main`.
2. Each `new StaticVersusInstanceDemo()` runs the **instance block** and constructor logic for that object.
3. `id` belongs to each instance, whereas `nextId` is a shared static field.
4. `nextId` is incremented in the constructor; it is **not** incremented merely by additional reads of the static field.

The example has no custom superclass, so the order is easy to observe. When a class has a superclass, the object-creation process also involves the `super(...)` constructor chain and the instance initializers at each level; that is different from the class initialization sequence.

### 5.1. Do Not Confuse a Static Block with a Constructor

| Characteristic | Static block | Constructor | Instance initializer block |
| --- | --- | --- | --- |
| Syntax | `static { ... }` | `ClassName(...) { ... }` | `{ ... }` in the class body |
| Tied to | Class initialization | Each instance creation | Each instance creation |
| Parameters | No | May have | No |
| `this` | Cannot be used | Usable in an appropriate instance context | Usable in an appropriate instance context |
| Used for | Setting up class-level state | Constructing a valid object | Shared per-object logic when appropriate |
| Repeats on `new` of a second object? | No, if the class is already initialized | Yes | Yes |

A constructor cannot replace the need to set class-level data properly before the first static method call. Conversely, a static block has no individual object, so it cannot initialize the instance fields of an object that has not yet been created.

## 6. Superclass and Subclass: Initialization Order

When initializing a subclass, the JVM must ensure that the relevant superclasses have already been initialized according to Java rules. This leads to an easily observed order:

- Static field/block of **Base**.
- Static field/block of **Child**.
- After that, if creating an object, the instance initialization chain of superclass then subclass.

Save **`InheritanceStaticOrderDemo.java`**:

~~~java
public class InheritanceStaticOrderDemo {
    static class Base {
        static int code = log("Base static field", 1);

        static {
            System.out.println("Base static block");
        }

        Base() {
            System.out.println("Base constructor");
        }
    }

    static class Child extends Base {
        static int version = log("Child static field", 2);

        static {
            System.out.println("Child static block");
        }

        Child() {
            System.out.println("Child constructor");
        }
    }

    private static int log(String name, int value) {
        System.out.println(name + "=" + value);
        return value;
    }

    public static void main(String[] args) {
        System.out.println("main begins");
        new Child();
        System.out.println("create second");
        new Child();
    }
}
~~~

Compile/run:

~~~bash
javac InheritanceStaticOrderDemo.java
java InheritanceStaticOrderDemo
~~~

Output:

~~~text
main begins
Base static field=1
Base static block
Child static field=2
Child static block
Base constructor
Child constructor
create second
Base constructor
Child constructor
~~~

On the first `Child` creation, class initialization occurs once; next, the constructor chain creates the object. The second creation only runs the constructors and does not re-run the static initializers.

### 6.1. A Static Field Declared in a Superclass

When accessing an inherited static field that is **actually declared** in the superclass, the subclass is not necessarily initialized merely because the expression writes the subclass name.

~~~java
class Base {
    static int VALUE = init();

    static int init() {
        System.out.println("Base initialized");
        return 10;
    }
}

class Child extends Base {
    static {
        System.out.println("Child initialized");
    }
}
~~~

This is an illustrative declaration; if another method uses `System.out.println(Child.VALUE);`, the field `VALUE` is actually declared by `Base`, so simply reading that field does not require initializing `Child`. Class initialization depends on **the class that declares the member** and the active-use rules, not just the character sequence before the dot.

### 6.2. Interface Initialization Has Its Own Rules

Initializing a subclass and initializing an interface are not completely identical:

- When initializing a class, its superclasses must be initialized according to the rules, and certain superinterfaces that declare default methods also participate in the initialization requirement.
- Initializing an interface **does not by default require initializing every superinterface** like a class's superclass chain process.
- Fields in an interface are implicitly `public static final`, yet not all of them are compile-time constants; an initializer may be executed when the interface is initialized.

Do not take an example of a class extending a class and assume that an interface extending an interface will produce the same order of printed lines in all cases.

## 7. `static final` Is Not Always a Constant Variable

Compare:

~~~java
static final int MAX_RETRIES = 3;
static final String PRODUCT = "Demo";
static final int GENERATED = compute();
static final java.util.List<String> LABELS =
        java.util.List.of("A", "B");
~~~

- `MAX_RETRIES` and `PRODUCT` are **constant variables** if declared final with a primitive or String type and initialized by **constant expressions**. The compiler can use the constant value without needing class initialization of where they are declared.
- `GENERATED` is static final but calls the `compute()` method; it is **not** a compile-time constant.
- `LABELS` is a static final reference to a List object; it is not a compile-time constant variable because its type is not primitive/String and it requires creating/obtaining an object at runtime.

Therefore, you cannot say **"reading any static final never initializes the class"** or **"every static final is deeply immutable"**.

### 7.1. Example of a Constant Variable That Does Not Trigger the Static Block

Save **`ConstantInitializationDemo.java`**:

~~~java
public class ConstantInitializationDemo {
    static class Constants {
        static final int LITERAL = 42;
        static final String GREETING = "Hello";
        static final int COMPUTED = compute();

        static {
            System.out.println("Constants initialized");
        }

        private static int compute() {
            System.out.println("compute called");
            return 7;
        }
    }

    public static void main(String[] args) {
        System.out.println("literal=" + Constants.LITERAL);
        System.out.println("greeting=" + Constants.GREETING);
        System.out.println("before computed");
        System.out.println("computed=" + Constants.COMPUTED);
    }
}
~~~

Run:

~~~bash
javac ConstantInitializationDemo.java
java ConstantInitializationDemo
~~~

Output:

~~~text
literal=42
greeting=Hello
before computed
compute called
Constants initialized
computed=7
~~~

Explanation:

1. The two reads `Constants.LITERAL` and `Constants.GREETING` can use the values of **constant expressions**, without initializing `Constants`.
2. Reading `Constants.COMPUTED` is an active use of a field that is not a constant variable; `Constants` is initialized.
3. The field initializer `compute()` prints `compute called`.
4. The static block prints `Constants initialized`.
5. Only at the end is `computed=7` printed.

### 7.2. Consequences of Changing Public Compile-Time Constants

For already-compiled code in other modules/projects, the value of a public compile-time constant may have already been **embedded into the client bytecode**. If the library changes `public static final int LIMIT = 10` to 20 while the client is **not recompiled**, the client may still use the old value.

This is a binary compatibility risk to keep in mind when publishing an API. If a configuration value needs to change across versions/actual runs, consider an **accessor method** or a field that is not a constant variable, rather than an inlined public constant.

At the same time, `final` on an object reference does not prevent other code from modifying the mutable object to which that reference points.

## 8. Static Forward Reference: A Name in Scope Is Not Enough

In a class body, fields are in scope according to Java rules; however, when a **static field initializer** or a **static initializer block** accesses a **static field declared later by its simple name**, **illegal forward reference** restrictions apply.

Intentionally invalid example:

~~~java
class BadOrder {
    static int a = b; // Compile error: illegal forward reference.
    static int b = 10;
}
~~~

This is an illustrative error example; do **not** put this block as-is into a project that you want to compile successfully.

A common approach is to **place the dependency declaration above**:

~~~java
class GoodOrder {
    static int b = 10;
    static int a = b;
}
~~~

You should not "work around" the restriction using a qualified name and then assume that the value is already ready. Qualified access or access through a method can lead to observing the **default value before initialization reaches that field**.

### 8.1. Example That Compiles but Produces an Unexpected Result

Save **`ForwardReferenceDemo.java`**:

~~~java
public class ForwardReferenceDemo {
    static class Values {
        static int first = Values.second;
        static int second = 10;

        static {
            System.out.println("first=" + first);
            System.out.println("second=" + second);
        }
    }

    public static void main(String[] args) {
        System.out.println("main first=" + Values.first);
        System.out.println("main second=" + Values.second);
    }
}
~~~

Run:

~~~bash
javac ForwardReferenceDemo.java
java ForwardReferenceDemo
~~~

Output:

~~~text
first=0
second=10
main first=0
main second=10
~~~

At the moment of evaluating `first = Values.second`, the `Values` class is undergoing initialization, but the initializer for `second = 10` **has not run yet**. The field `second` currently holds the default value `0` from preparation, so `first` is assigned 0. Afterward, `second` is assigned 10, which **does not update** `first`.

This example is especially useful for distinguishing:

- **Recognizable name** (the qualified reference compiles).
- **Whether the field has finished initializing** (no, so it holds the default value).
- **Proper data dependency** (the initialization order is contrary to intent).

In real code, declare the dependency before the dependent value, or use a factory method with a clear dependency structure; avoid tricks that fool the forward-reference check.

### 8.2. Why static final Does Not Always Save You

If the second field is a **compile-time constant variable**, its semantics differ from a static field that requires runtime computation. However, if you rely on `static final Value settings = load();` or `static final int value = compute();`, that is still initialization with a runtime execution point; `final` does not move the computation to some "magical time" before all other code.

Always analyze the **initializer kind**, **declaration order**, and **triggers** rather than relying solely on the `final` modifier.

## 9. Dependency Cycles During Static Initialization

An error-prone design is when class A needs a static value from B, while B also needs a static value from A. The JVM has a mechanism for handling recursive initialization on a per-thread basis, yet the logic may use an **incomplete default value**, producing strange results.

Save **`StaticCycleDemo.java`**:

~~~java
public class StaticCycleDemo {
    static class Alpha {
        static int value = Beta.value + 1;
    }

    static class Beta {
        static int value = Alpha.value + 1;
    }

    public static void main(String[] args) {
        System.out.println("alpha=" + Alpha.value);
        System.out.println("beta=" + Beta.value);
    }
}
~~~

Compile/run:

~~~bash
javac StaticCycleDemo.java
java StaticCycleDemo
~~~

Output:

~~~text
alpha=2
beta=1
~~~

Trace:

1. Reading `Alpha.value` starts the initialization of Alpha.
2. Alpha needs `Beta.value`, leading to the initialization of Beta.
3. Beta reads `Alpha.value` while Alpha is **currently being initialized by the same thread**. The value of Alpha's field at this moment is still the default 0.
4. Beta computes `0 + 1 = 1` and finishes.
5. Alpha computes `1 + 1 = 2` and finishes.
6. The two printed lines are `alpha=2` and `beta=1`, respectively.

**Note:** The result depends on the trigger path. If Beta is initialized before Alpha in a similar design, you may observe a different result. Circular static dependencies make code hard to understand and error-prone.

### 9.1. How to Avoid Circular Dependencies

- Place the required data in a single location with clear responsibility, rather than letting two classes depend on each other to complete `static` initialization.
- Use a constructor/factory to pass dependencies in during **object** initialization, if the dependency is application state.
- Use controlled **lazy initialization** when an object is expensive to create or needs to be deferred, while still avoiding cycles.
- Use initialization tests in a fresh JVM to verify results: a class already initialized in an earlier test can hide ordering bugs in a later test.

If multiple threads create a wait cycle during class initialization or while holding other locks, there is a risk of complex deadlocks. That is why static initialization should be kept simple.

## 10. Class Initialization Can Fail

If an exception occurs while evaluating a static field initializer or a static block, class initialization can fail.

Typically:

- If the cause is a non-`Error` throwable (such as `IllegalStateException`), the JVM reports the class initialization failure on the first attempt with an `ExceptionInInitializerError`, along with the cause.
- After a class is marked as having failed initialization, subsequent active uses of **that runtime class** may throw `NoClassDefFoundError` indicating that the class could not be initialized.
- If the original failure is an `Error`, Java has different propagation rules, and you must not claim that everything is always wrapped in `ExceptionInInitializerError`.
- There is no "re-running the static block" by trying `new` again on the same class already marked erroneous.

### 10.1. A Runnable Example That Catches the Error for Illustration

Save **`StaticInitializationFailureDemo.java`**:

~~~java
public class StaticInitializationFailureDemo {
    static class Broken {
        static int VALUE = load();

        private static int load() {
            System.out.println("load attempted");
            throw new IllegalStateException("invalid startup configuration");
        }
    }

    public static void main(String[] args) {
        for (int attempt = 1; attempt <= 2; attempt++) {
            try {
                System.out.println(Broken.VALUE);
            } catch (Error error) {
                System.out.println("attempt " + attempt + ": " +
                        error.getClass().getSimpleName());
            }
        }
    }
}
~~~

Run:

~~~bash
javac StaticInitializationFailureDemo.java
java StaticInitializationFailureDemo
~~~

Output:

~~~text
load attempted
attempt 1: ExceptionInInitializerError
attempt 2: NoClassDefFoundError
~~~

**Catching `Error` here is only in the example to observe the runtime mechanism**, not guidance for application code to catch/swallow every `Error`. For real applications, define a fail-fast startup policy, log the root cause, ensure valid configuration before loading, or recover using an explicit mechanism.

### 10.2. Can You Write `throw` for a Checked Exception Directly from a Static Block?

A static initializer **is not permitted to complete abruptly because of a checked exception** without handling it according to Java rules; you cannot simply write `static { throw new IOException(); }` and expect the compiler to accept it. If a file-loading operation throws a checked exception, you must catch/handle it, or translate it into an appropriate exception to reflect the initialization failure.

There is no concept of attaching `throws IOException` directly to a static block like a method signature.

## 11. Static Blocks with Complex Class-Level Data

An application has a fixed threshold table that needs to be built and validated:

~~~java
static final Map<String, Integer> LIMITS;

static {
    Map<String, Integer> draft = new HashMap<>();
    draft.put("BASIC", 3);
    draft.put("PLUS", 10);
    // Validate data before publishing.
    LIMITS = Map.copyOf(draft);
}
~~~

This is an **illustrative snippet** that requires importing `Map` and `HashMap` and placing it inside a class. Note that a class-level list/map should not be a mutable singleton that callers could accidentally modify outside the API.

### 11.1. Complete Program: Building an Immutable Map in a Static Block

Save **`StaticConfigurationDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;

public class StaticConfigurationDemo {
    private static final Map<String, Integer> LIMITS;

    static {
        Map<String, Integer> draft = new HashMap<>();
        draft.put("BASIC", 3);
        draft.put("PLUS", 10);

        if (draft.values().stream().anyMatch(value -> value <= 0)) {
            throw new IllegalStateException("invalid limit");
        }

        LIMITS = Map.copyOf(draft);
        System.out.println("configuration initialized");
    }

    public static int maxItems(String tier) {
        Integer value = LIMITS.get(tier);
        if (value == null) {
            throw new IllegalArgumentException("unknown tier");
        }
        return value;
    }

    public static void main(String[] args) {
        System.out.println("BASIC=" + maxItems("BASIC"));
        System.out.println("PLUS=" + maxItems("PLUS"));

        try {
            LIMITS.put("BASIC", 999);
        } catch (UnsupportedOperationException expected) {
            System.out.println("configuration read-only");
        }

        System.out.println("BASIC after attempt=" + maxItems("BASIC"));
    }
}
~~~

Compile/run:

~~~bash
javac StaticConfigurationDemo.java
java StaticConfigurationDemo
~~~

Output:

~~~text
configuration initialized
BASIC=3
PLUS=10
configuration read-only
BASIC after attempt=3
~~~

- The static block runs before `main` because the class is initialized to start the program.
- `draft` is just a mutable local Map used to construct the data.
- `Map.copyOf` returns an unmodifiable map, holding state responsibly at the class level.
- Callers cannot alter the contents of `LIMITS` via `put` on the resulting map.
- The values are immutable `Integer` instances, so there is no indirect mutability through values in the example.

### 11.2. Do Not Store Secrets in Public Static Fields

If configuration contains API keys, credentials, or other secrets, do not put them in public fields or print them in static initializer logs. `private` in Java helps reduce the API surface, but it is **not** a substitute for a secrets management model, access control, encryption, and a secure deployment environment.

## 12. Lazy Initialization with the Initialization-on-Demand Holder

If a class-level object is expensive to create and not needed on every execution path, initializing it eagerly in the main class can waste resources unnecessarily.

A commonly used Java idiom is **initialization-on-demand holder**:

- A public class contains a static method `get()`.
- A nested static class `Holder` holds the static final value to be initialized.
- `Holder` is initialized only upon appropriate active use.
- JVM class initialization provides a standard thread-safe initialization mechanism for the class; whether the returned object is thread-safe for subsequent use remains a separate question.

Save **`LazyHolderDemo.java`**:

~~~java
public class LazyHolderDemo {
    static final class Registry {
        private Registry() {
        }

        private static String make() {
            System.out.println("resource created");
            return "READY";
        }

        private static class Holder {
            static final String RESOURCE = make();
        }

        static String get() {
            return Holder.RESOURCE;
        }
    }

    public static void main(String[] args) {
        System.out.println("before first get");
        System.out.println("first=" + Registry.get());
        System.out.println("second=" + Registry.get());
    }
}
~~~

Run:

~~~bash
javac LazyHolderDemo.java
java LazyHolderDemo
~~~

Output:

~~~text
before first get
resource created
first=READY
second=READY
~~~

**Explanation:**

- `Registry.get()` is a static method, so calling it requires initializing `Registry`.
- `Holder` is a **separate** nested static class and is not necessarily initialized immediately when `Registry` is initialized.
- `Holder.RESOURCE` is assigned via a call to the `make()` method, so it is **not** a compile-time constant variable; the first read triggers `Holder` initialization.
- Subsequent reads receive the same stored value without calling `make()` again.

**Important:** The value `"READY"` is returned from a method, not declared directly as a string literal in `Holder.RESOURCE`. This avoids turning `RESOURCE` into an inlined constant variable, which would defeat the intent of the lazy initialization example.

### 12.1. What Limitations Does This Idiom Have?

- It is suitable for a resource/value initialized once, but if creation fails, the holder class can become erroneous; it does not automatically retry on each call.
- It does not address the need to close resources (`close()`) or lifecycles with complex start/stop/reset behavior.
- It does not make a shared mutable object automatically thread-safe.
- With dependency injection or a complex application lifecycle, managing objects in a container/service may be clearer.

## 13. `Class.forName` and Class Literals: They Can Differ in Initialization Timing

Evaluating `Target.class` to obtain the corresponding `Class` object **does not by itself require initializing Target** in typical examples. However, the simple overload `Class.forName(String)` initializes the requested class according to its API contract.

Save **`ClassLiteralInitializationDemo.java`**:

~~~java
public class ClassLiteralInitializationDemo {
    static class Target {
        static {
            System.out.println("Target initialized");
        }
    }

    public static void main(String[] args) throws ClassNotFoundException {
        System.out.println("before literal");
        Class<?> type = Target.class;
        System.out.println("after literal=" + type.getSimpleName());

        Class.forName(type.getName());
        System.out.println("after forName");

        Class.forName(type.getName());
        System.out.println("after second forName");
    }
}
~~~

Run:

~~~bash
javac ClassLiteralInitializationDemo.java
java ClassLiteralInitializationDemo
~~~

Output:

~~~text
before literal
after literal=Target
Target initialized
after forName
after second forName
~~~

The line `Target initialized` appears on the first call to `Class.forName(type.getName())`, **not** immediately after `Target.class`. Calling it again on the same runtime class does not re-run the static block.

If you need to load without initializing yet, the API provides the overload `Class.forName(String name, boolean initialize, ClassLoader loader)` with the `initialize` flag. However, class loading/reflective APIs have their own exception and class loader details; you should not use reflection merely to control order arbitrarily when source-level design can be clearer.

## 14. Static Block Initialization Is Synchronized, but Static State Is Not Automatically Thread-Safe

The JVM has a procedure for coordinating class initialization across threads. When one thread is initializing a class, other threads that need active use of that class must generally wait or follow the defined initialization states.

This creates a **safety point** for publishing state that was properly constructed during class initialization. However, after initialization completes:

~~~java
class SharedCounter {
    static int count;

    static void increment() {
        count++; // Not atomic across multiple threads.
    }
}
~~~

`count++` can still race if multiple threads call it concurrently. `static` does not guarantee atomicity, visibility of mutable updates, or preservation of invariants afterward.

If a shared mutable counter is needed, you can use `AtomicInteger` or appropriate synchronization:

~~~java
class SharedCounter {
    private static final java.util.concurrent.atomic.AtomicInteger COUNT =
            new java.util.concurrent.atomic.AtomicInteger();

    static int increment() {
        return COUNT.incrementAndGet();
    }
}
~~~

This is an illustrative class; `COUNT` is initialized once when the class is initialized. `AtomicInteger.incrementAndGet()` has atomic semantics suitable for a simple increment. If multiple fields must be updated consistently as a single transaction, a standalone atomic counter is not sufficient.

### 14.1. Class Initialization with Two Threads

If thread A is running a static initializer and thread B tries to use the class at the same time, the JVM must coordinate so the class is not treated as completely initialized along two independent paths. However, if the static initializer itself waits on another thread while that other thread waits on class initialization, the application can encounter a deadlock.

**Do not** perform network blocking, complex thread waiting, circular dependency calls, or event-loop creation inside a static block without a compelling reason and a clear startup contract.

## 15. The Number of Static Initializations Depends on Runtime Class Identity

A commonly heard statement is "a static block runs exactly once in the entire program." That phrasing **needs qualification**.

In reality, a runtime class is identified by its **binary name and defining class loader** according to Java/JVM rules. Two different class loaders can define two separate runtime classes for the same source/binary name, and each class has its own initialization state.

In a simple application using a single application class loader and running in a single JVM, you typically observe one initialization per class. However, in application servers, plugins, test frameworks, or hot reload environments, the **same class name** does not necessarily represent the same runtime class identity.

If the program is run again in a **new JVM process**, static initialization occurs again in the new process. Static fields should not be used as persistent data storage across runs.

### 15.1. Are Static Fields Truly Global Variables?

In a small application, a static field is shared by many objects, so it **resembles global state**. However:

- Access still depends on `private`/package/protected/public` and modules.
- Class loader boundaries can create multiple class runtimes.
- Mutable static state makes tests depend on one another, causing hidden coupling.
- All threads can touch the state concurrently if it is shared.

Therefore, limit **mutable public static fields**. Prefer immutable constants, stateless utilities, or explicitly passed dependencies when there is complex state.

## 16. Initialization Order When Fields and Static Blocks Depend on Each Other

Let's create a timeline table:

| Step | Declaration encountered in source | Behavior |
| --- | --- | --- |
| 1 | `static int a = initA();` | Compute/assign `a` |
| 2 | `static { configure(); }` | Run `configure()` |
| 3 | `static int b = initB();` | Compute/assign `b` |
| 4 | `static { verify(); }` | Run `verify()` |

If `initA()` reads `b` before step 3, it may receive the default value 0, depending on how the code is written and the forward-reference rules. If `verify()` relies on both `a` and `b`, placing it **after** the two initializers is clearer.

### 16.1. Consolidating Complex Initialization into a Named Method

Instead of a long static block:

~~~java
static final Settings SETTINGS = loadAndValidateSettings();

private static Settings loadAndValidateSettings() {
    // Read/configure/validate in a structured way.
    return new Settings();
}
~~~

This is an **illustrative snippet** requiring an appropriate `Settings` class/logic. Using a named method helps separate responsibilities, write tests for pure logic, and reduce static initialization to a single clear assignment step.

However, calling a method does not make this code lazy: because `SETTINGS` is a static field initializer calling a method, it still runs when the class is initialized. To defer it, you can use a holder or a lifecycle service as discussed above.

## 17. When Should Static Initialization Be Avoided?

Using a static initializer is generally appropriate for:

- Small, immutable lookup tables that do not need to read from external services.
- Constants/runtime values that remain unchanged throughout the class's lifecycle.
- Simple internal setup operations that can complete quickly and predictably.

Consider **avoiding static blocks** for:

- Database/network connections requiring retries, shutdown, credential management, metrics, or runtime configuration.
- State belonging to individual users/sessions/requests/tenants.
- Data that needs to be reloaded while the program is running.
- Logic that depends on unpredictable class initialization order or has circular dependencies.
- Work with large side effects; if it fails, the entire class becomes unusable within the defining-loader context.
- Test code that needs to substitute dependencies or create multiple independent states.

In such cases, a constructor, factory, dependency injection, application startup service, or a controlled lazy holder is usually easier to operate.

## 18. Common Mistakes and How to Fix Them

| Misconception/mistake | Correct explanation |
| --- | --- |
| "`static` block runs every time an object is created." | It is tied to class initialization, not to each instance. |
| "All static fields are assigned before all static blocks." | Field initializers and blocks run interleaved in declaration order. |
| "A method declared lower down cannot be called in a block above it." | Method declarations have their own scope rules; a method can be called from an initializer. |
| "`static final` is always a compile-time constant." | Only when it has a primitive/String type and the initializer is a constant expression per the JLS. |
| "Reading any static final initializes the class." | Reading a constant variable may not trigger initialization. |
| "`new` of a second object will re-run the static initializer." | An already-initialized class generally does not repeat static logic. |
| "`this` can be used in a static block." | A static context has no current instance. |
| "If a field name is in scope, its value has already been initialized." | It may still hold the default value because its initializer's turn has not arrived yet. |
| "Bypassing a forward reference with a qualified name is always safe." | Qualified access can observe the default value prematurely; that is a logic bug. |
| "`Child.VALUE` always initializes Child." | If the field is declared in Base, reading it may initialize only Base. |
| "Subclass initialization always follows the same rules as interfaces." | Interface initialization has its own rules. |
| "`Class.forName` and `Target.class` are always the same." | `Target.class` does not by itself initialize Target; `Class.forName(String)` can require initializing the class. |
| "An exception in a static block is retried on the next access." | Failed class initialization can mark the class erroneous, and subsequent uses encounter `NoClassDefFoundError`. |
| "Static blocks run once for all classes of the same name across all class loaders." | Each runtime class identified by its defining class loader has its own initialization state. |
| "`private static final List` is always immutable." | Final locks the reference; the list object can be mutable if not protected. |
| "A static Map can use a public mutable HashMap for convenience." | Callers can corrupt the shared configuration; use private + an unmodifiable map/appropriate API. |
| "Since static initialization is thread-safe, a static counter ++ is also thread-safe." | Initialization guarantees do not make subsequent mutable operations atomic. |
| "A static block is appropriate for starting all I/O and threads." | It makes lifecycle/retry management difficult; consider explicit startup services. |
| "To re-run a block, call a static method." | Calling another method does not automatically re-run the static block; only the code inside the called method runs. |

## 19. Checklist for Reading a Code Snippet with `static`

When encountering:

~~~java
class Example {
    static int a = calculateA();
    static { initialize(); }
    static final int b = 5;
}
~~~

ask yourself:

1. **Has the class been initialized yet?** If not, which piece of code triggers it?
2. **Is `b` a compile-time constant?** Reading `b` may not trigger the class.
3. **Has the superclass been initialized yet?** Are there superinterface default methods to consider?
4. **In what order do the static field initializers and blocks appear?**
5. **Is any field read before its initializer runs?** You might observe a default value or an illegal forward reference.
6. **Is there a circular dependency between classes?**
7. **Can the static block throw an exception?** If it fails, how does the application handle startup?
8. **Can the data be modified from outside after initialization?** A `static final` reference does not guarantee an immutable referent.
9. **If multiple threads access it, are subsequent mutations synchronized?**
10. **Does this state belong to the class, or does it actually belong to an instance/request/user?**
11. **Does the data need reloading/lazy loading?** Can a holder or a separate service be used?
12. **Do tests run in a single JVM or with multiple class loaders?** You should not rely on "only once across the entire system" if contexts differ.

## 20. Self-Check Exercises with Answers

**Question 1.** A class has `static { System.out.println("INIT"); }` and a constructor that prints `NEW`. If two objects are created consecutively in the same JVM/class loader, what is normally printed?  
**Answer:** `INIT` once before the first object, then `NEW` twice. Static initialization does not repeat for each `new`.

**Question 2.** There are two declarations: `static int a = log("A");` followed by `static { log("B"); }`. Which line is printed first?  
**Answer:** `A` before `B` because the field initializer and static block follow their order of appearance.

**Question 3.** Why cannot a static block use `this.value`?  
**Answer:** A static context has no current instance for `this` to point to.

**Question 4.** How does the field `static final int MAX = 10;` differ from `static final int MAX = calculate();`?  
**Answer:** The first case can be a constant variable; the second case must be computed at runtime, so it is not a compile-time constant.

**Question 5.** Does reading `Constants.MAX` when MAX is a constant variable necessarily print a line in Constants's static block?  
**Answer:** No. Reading a constant variable does not require initialization of the declaring class.

**Question 6.** `static int first = Later.second; static int second = 10;` (with the proper class name) can result in first having what value?  
**Answer:** It can receive the default 0 before the second initializer runs, if the code uses valid qualified access and has no other constant-value semantics.

**Question 7.** Why does `static int a=b; static int b=10;` in the same class typically report an illegal forward reference?  
**Answer:** Java restricts certain simple-name reads of fields declared later in static initializer contexts to reduce bugs from reading too early.

**Question 8.** If class Alpha is initialized and reads Beta in its initializer, while Beta reads Alpha in return, what is the concern?  
**Answer:** A dependency cycle can observe default values of incomplete fields, leading to unexpected state or deadlocks in complex designs.

**Question 9.** When a static initializer throws `IllegalStateException` the first time, what error does the caller typically see?  
**Answer:** `ExceptionInInitializerError` according to the applicable wrapping rules; subsequent active uses can throw `NoClassDefFoundError` on the same erroneous class.

**Question 10.** Can you place `throws IOException` after `static { ... }`?  
**Answer:** No. A static block does not have a method signature/throws clause. Checked exceptions must be handled according to Java rules.

**Question 11.** Creating `new Child()` causes the static initializers of Base and Child to run in what order when neither is initialized yet?  
**Answer:** Base before Child according to class initialization rules; afterward, the constructor chain executes for the object.

**Question 12.** Does `Child.BASE_FIELD` necessarily initialize Child if BASE_FIELD is declared in Base?  
**Answer:** No. Active use of a field depends on the class that declares the field.

**Question 13.** Does `Class<?> c = Target.class;` automatically run Target's static block?  
**Answer:** Not necessarily; an ordinary class literal does not trigger class initialization.

**Question 14.** Why is `Map.copyOf` useful when preparing static configuration?  
**Answer:** It provides an unmodifiable map via its API, preventing other code from mutating the map structure after initialization, provided no mutable values needing separate protection are exposed.

**Question 15.** Is `static final ArrayList<T> cache` deeply immutable?  
**Answer:** No. The reference field cannot be reassigned, but the ArrayList object can still be modified through the reference.

**Question 16.** At what point does an initialization-on-demand holder initialize the resource?  
**Answer:** When the nested holder class is initialized through appropriate active use, typically the first call to the accessor that reads the holder's non-constant static field.

**Question 17.** Does thread-safe holder initialization mean that an `ArrayList` returned from the Holder is automatically thread-safe?  
**Answer:** No. Creation/publication at class initialization time is distinct from the concurrency semantics of subsequent mutations.

**Question 18.** Do two separate JVM processes share the same static field instance?  
**Answer:** No. Static fields are state within each JVM's runtime class, not cross-process persistence.

**Question 19.** Can two different defining class loaders loading a class with the same name have different static state?  
**Answer:** Yes. Runtime class identity considers the defining loader together with the binary name, so initialization states can differ.

**Question 20.** If configuration needs to reload every hour, will a static final immutable map initialized only once reload automatically?  
**Answer:** No. You need to design a separate lifecycle/config service with explicit updates, rather than expecting the static block to re-run automatically.

## References

- Java Language Specification, [`12.4 — Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4): initialization timing and sequence.
- Java Language Specification, [`12.4.1 — When Initialization Occurs](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.1): triggers for initializing a class/interface.
- Java Language Specification, [`12.4.2 — Detailed Initialization Procedure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2): procedure, states, and multi-thread coordination.
- Java Language Specification, [`8.7 — Static Initializers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.7): static blocks and context restrictions.
- Java Language Specification, [`8.3.2 — Field Initialization](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3.2): initializers and forward-reference restrictions.
- Java Language Specification, [`4.12.4 — final Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): final/constant variables.
- Java Platform API, [`Class.forName](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#forName(java.lang.String)): reflective loading/initialization.

## Key Takeaways

**`static { ... }` blocks and static field initializers are used to set up class-level data when the JVM initializes a class.** They execute in their **order of appearance in the class body** and do not re-run for each object. Static initialization is fundamentally different from instance initialization and constructors.

Be especially careful with **constant variables that do not trigger initialization**, **illegal forward references and default values before a field initializer runs**, **circular dependencies between classes**, **initialization failures that can render a class unusable again**, and **mutable static state that is not automatically thread-safe**. Use static blocks for simple, fast, controllable class-level data; prefer immutable collections or a holder when lazy initialization is needed. For complex I/O, resource lifecycles, or per-user state, a service/factory with clear responsibility is usually more appropriate.
