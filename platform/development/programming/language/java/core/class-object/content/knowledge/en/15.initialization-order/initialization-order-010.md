# Class Initialization Errors and Experiments for Predicting Print Order in Java

**Initialization order** is an easily confused topic when learning Java Core: when does a `static` block run, does a field initializer execute before or after a constructor, is a superclass initialized before a subclass, and why can a failed use of a class throw `ExceptionInInitializerError` while the next attempt throws `NoClassDefFoundError`?

To predict **stdout** accurately, you need to distinguish between **class initialization** and **object initialization**, and then track the points at which Java requires static initializers to execute. When static initialization fails, you need to understand the state of the class after the error: the JVM does not simply retry running the same static block every time someone accesses it.

This lesson belongs to **Java core - class-object**, in the **Initialization Order** section. Each experiment runs standalone on **Java 17+**, with a filename, `javac`/`java` commands, expected result, and solution. Cases that are intentionally non-compilable or are only illustrative snippets are clearly distinguished.

## 1. Learning Outcomes

After studying this lesson, you should be able to answer on your own:

1. When does the JVM execute `static` field initializer expressions and `static { ... }`?
2. Why can a `static final` compile-time constant be read **without** triggering class initialization?
3. In what order do the superclass, subclass, instance fields, instance initializer blocks, and constructors appear?
4. Why can a field read early via a method still be `0`, `false`, or `null`?
5. Why does a failed class initialization typically cause `ExceptionInInitializerError`, while a subsequent use may cause `NoClassDefFoundError`?
6. How does an exception in an **instance constructor** differ from an exception during **class initialization**?
7. How do you predict the output using a state table instead of guessing from the order of `println` lines in the source?

Core concept: **a runtime class is initialized according to JVM rules**, whereas **each object** has its own instance initialization process.

## 2. The Three Phases of a Class and the Object Creation Phase

First, let's separate the two levels.

At the class/interface level, the JVM performs the appropriate activities:

~~~text
Loading
  -> Linking (verification, preparation, resolution according to JVM rules)
  -> Initialization when there is a reason to initialize the class/interface

Class initialization:
  execute static field initializers and static initializer blocks
  in the specified order
~~~

At the instance level, when calling `new SomeClass()`:

~~~text
Require the class to be ready/initialized
  -> allocate the object and set default values for instance fields
  -> traverse the superclass/subclass constructor chain
  -> run instance field initializers and instance initializer blocks
  -> run the appropriate constructor body
  -> return the object if creation succeeds
~~~

**Loading is not synonymous with initialization.** A class may already be loaded or linked without having executed its static block yet. Conversely, a static block printing to the console only proves that the initialization phase of that class has started executing; it does not prove when the class file was first loaded.

**Preparation does not call** methods in the expression `static int x = compute();`: it prepares storage/initial values for static fields. The `compute()` call belongs to static initialization. Reference resolution (*resolution*) may be processed eagerly or lazily by the JVM according to the specification; all of resolution should not be treated as an event timeline easily observable with `println`.

## 3. Actions That Trigger Class Initialization

According to [JLS 17 §12.4.1](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.1), the key scenarios include:

| Action | Effect on initialization |
| --- | --- |
| `new Target()` | Target must be initialized before creating the appropriate instance |
| Calling a static method **declared** by Target | Target is initialized if not already |
| Reading a static field declared by Target that is **not a constant variable** | Target is initialized |
| Assigning a static field | The class/interface declaring the field must be initialized |
| Certain reflection calls requiring initialization | Depends on the API and parameters |
| JVM starts running `Main.main` | The main class is initialized before running `main` |
| Accessing an inherited field via a subclass name | Consider **the class that actually declares the field**, not just the name before the dot |

Actions that **do not on their own force Target to be initialized** merely because they appear in the source:

- Writing `Target.class` to obtain the class literal.
- Writing `new Target[3]` to create a reference array.
- Declaring `Target reference;`.
- Reading a `static final` primitive/`String` field that is a **constant variable** computed by a *constant expression*.
- `Class.forName(name, false, loader)`: requests finding/obtaining the `Class` **without requiring initialization** of that class.

You cannot predict static output without first identifying **which action is the first active use** of the class under consideration.

## 4. Experiment 1: `main` class, constant, static block, and constructor

Create the file **`FirstUseOrderDemo.java`**:

~~~java
class Warmup {
    static final int CONSTANT = 7;
    static int value = announce("Warmup.value", 3);

    static {
        System.out.println("Warmup.block value=" + value);
    }

    static int announce(String label, int result) {
        System.out.println(label);
        return result;
    }

    Warmup() {
        System.out.println("Warmup.constructor");
    }
}

public class FirstUseOrderDemo {
    static {
        System.out.println("Main.initialized");
    }

    public static void main(String[] args) {
        System.out.println("main.begin");
        System.out.println("constant=" + Warmup.CONSTANT);
        System.out.println("after.constant");
        System.out.println("value=" + Warmup.value);
        new Warmup();
        new Warmup();
        System.out.println("main.end");
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 FirstUseOrderDemo.java
java FirstUseOrderDemo
~~~

**Exact stdout:**

~~~text
Main.initialized
main.begin
constant=7
after.constant
Warmup.value
Warmup.block value=3
value=3
Warmup.constructor
Warmup.constructor
main.end
~~~

**Analysis:** The JVM initialized `FirstUseOrderDemo` before running `main`, so the line `Main.initialized` appears before `main.begin`. `Warmup.CONSTANT` is a compile-time constant, so the statement reading it does not by itself trigger `Warmup` initialization.

Only at `Warmup.value` (a static field that is not a constant variable) does Java need `Warmup` initialized. The initializer calls `announce` first, and the static block runs afterward. Once the class is initialized successfully, the two `new Warmup()` calls invoke the constructor **twice**; the static block does not repeat.

**Do not misinfer:** the fact that `Warmup.value` runs after `constant=7` does not determine the exact time when the JVM loaded the `Warmup.class` file. What we are predicting here is the **initialization output**.

## 5. Precedence Rules When the Same Class Has Multiple Static Initializers

Within a class, **static field initializers** and **static initializer blocks** execute in the order they appear in the source, after the conditions for class initialization have been satisfied.

Illustrative example:

~~~java
class StaticPlan {
    static int a = print("a", 1);
    static {
        System.out.println("block 1");
    }
    static int b = print("b", 2);
    static {
        System.out.println("block 2");
    }

    private static int print(String label, int result) {
        System.out.println(label);
        return result;
    }
}
~~~

This is a **valid illustrative class** without `main`. When initialized, the output of the static code alone is, in order:

~~~text
a
block 1
b
block 2
~~~

A common mistake is assuming that all static field initializers run before all static blocks. **Incorrect**: field initializers and blocks **interleave in textual order**.

Specifically, fields that are *constant variables* receive special constant handling and should not be used to infer the execution timing of initializer expressions as with `static int x = method();`.

## 6. Experiment 2: static first, superclass and subclass constructors per object

Create the file **`ParentChildTraceDemo.java`**:

~~~java
class ParentTrace {
    static {
        System.out.println("Parent.static");
    }

    int baseValue = mark("Parent.field", 10);

    {
        System.out.println("Parent.instance block");
    }

    ParentTrace() {
        System.out.println("Parent.constructor");
    }

    static int mark(String name, int value) {
        System.out.println(name);
        return value;
    }
}

class ChildTrace extends ParentTrace {
    static {
        System.out.println("Child.static");
    }

    int childValue = mark("Child.field", 20);

    {
        System.out.println("Child.instance block");
    }

    ChildTrace() {
        System.out.println("Child.constructor");
    }
}

public class ParentChildTraceDemo {
    public static void main(String[] args) {
        System.out.println("begin");
        new ChildTrace();
        System.out.println("again");
        new ChildTrace();
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 ParentChildTraceDemo.java
java ParentChildTraceDemo
~~~

**Exact stdout:**

~~~text
begin
Parent.static
Child.static
Parent.field
Parent.instance block
Parent.constructor
Child.field
Child.instance block
Child.constructor
again
Parent.field
Parent.instance block
Parent.constructor
Child.field
Child.instance block
Child.constructor
~~~

The first time `ChildTrace` is created, the JVM ensures that **ParentTrace is initialized before ChildTrace**. Next comes the object initialization phase: the instance field initializer and instance block of `ParentTrace`, the parent constructor body, and then the initializer/block and constructor of `ChildTrace`.

The second creation does not repeat static initialization, but **each new object** runs the instance initializers/constructors again.

**Distinction to keep in mind:** “the superclass is initialized before the subclass” is a **class-level** relationship. “the parent constructor runs before the child constructor” is an **object-level** relationship. These two things happen at different layers, even though both can be triggered by a single `new ChildTrace()` statement.

## 7. Experiment 3: Reading a Static Field Too Early Will See the Default Value

During **preparation**, ordinary static fields receive the appropriate default values before static initializers run. When a static initializer calls a helper method and the helper reads a field whose assignment has not yet had its turn, it can observe the default value.

Create the file **`StaticForwardReadDemo.java`**:

~~~java
class ForwardState {
    static int early = computeEarly();
    static int later = 10;

    static {
        System.out.println("block later=" + later);
    }

    private static int computeEarly() {
        System.out.println("during later=" + later);
        return later + 1;
    }
}

public class StaticForwardReadDemo {
    public static void main(String[] args) {
        System.out.println("begin");
        System.out.println("early=" + ForwardState.early);
        System.out.println("later=" + ForwardState.later);
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 StaticForwardReadDemo.java
java StaticForwardReadDemo
~~~

**Stdout:**

~~~text
begin
during later=0
block later=10
early=1
later=10
~~~

When `computeEarly()` runs, `later` has not yet reached its `= 10` initializer, so it is `0`. After `early` has received `1`, the assignment `later=10` **does not recalculate `early`**.

**Relying on default values from reading too early is not recommended.** If `early` truly needs `later=10`, place the initializer of `later` first or use an explicit initialization design.

Java also has an **illegal forward reference** rule (JLS §8.3.3): `static int x = y; static int y = 10;` may fail to compile due to reading a simple name too early. The complete example above is **valid** because the read of `later` occurs inside a **method body**, where that direct restriction does not block it. “The compiler allows it” does not mean “the value at the time of reading is already as intended”.

## 8. `static final` Does Not Always Trigger Initialization

Distinguish:

~~~java
static final int FIXED = 12;
static final String LABEL = "OK";
static final int COMPUTED = Integer.parseInt("13");
~~~

The first two fields are **constant variables** (primitive type or `String`, `final`, with a constant expression as the initializer). The `COMPUTED` field is not a constant variable because its initializer calls a method.

Create the file **`ConstantTriggerDemo.java`**:

~~~java
class ConfigTokens {
    static final int FIXED = 12;
    static final String LABEL = "OK";
    static final int COMPUTED = compute();

    static {
        System.out.println("ConfigTokens.static");
    }

    private static int compute() {
        System.out.println("ConfigTokens.compute");
        return 13;
    }
}

public class ConstantTriggerDemo {
    public static void main(String[] args) {
        System.out.println("start");
        System.out.println("fixed=" + ConfigTokens.FIXED);
        System.out.println("label=" + ConfigTokens.LABEL);
        System.out.println("computed=" + ConfigTokens.COMPUTED);
        System.out.println("end");
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 ConstantTriggerDemo.java
java ConstantTriggerDemo
~~~

**Stdout:**

~~~text
start
fixed=12
label=OK
ConfigTokens.compute
ConfigTokens.static
computed=13
end
~~~

Reading `FIXED` and `LABEL` **does not by itself initialize `ConfigTokens`**. Only the first read of `COMPUTED` requires initialization; the JVM executes the initializer that calls `compute()`, and then the static block.

**Warning:** do not treat every `static final` field as a compile-time constant. `static final Integer n = 12` is not a constant variable as defined by the JLS, because `Integer` is neither a primitive type nor `String`.

## 9. Class Literals, Arrays, and Reflection Can Defer Initialization

Create the file **`DeferredInitializationDemo.java`**:

~~~java
class Deferred {
    static {
        System.out.println("Deferred.static");
    }

    static int count = 5;

    Deferred() {
        System.out.println("Deferred.constructor");
    }
}

public class DeferredInitializationDemo {
    public static void main(String[] args) throws Exception {
        System.out.println("begin");

        Class<?> type = Deferred.class;
        System.out.println("literal=" + type.getSimpleName());

        Deferred[] array = new Deferred[2];
        System.out.println("array=" + array.length);

        ClassLoader loader =
                DeferredInitializationDemo.class.getClassLoader();
        Class<?> metadata =
                Class.forName("Deferred", false, loader);
        System.out.println("loaded=" + metadata.getSimpleName());

        System.out.println("before forName");
        Class.forName("Deferred");
        System.out.println("after forName");

        new Deferred();
        System.out.println("count=" + Deferred.count);
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 DeferredInitializationDemo.java
java DeferredInitializationDemo
~~~

**Stdout:**

~~~text
begin
literal=Deferred
array=2
loaded=Deferred
before forName
Deferred.static
after forName
Deferred.constructor
count=5
~~~

Analysis:

- `Deferred.class` obtains the `Class` object without by itself requiring `Deferred` to be initialized.
- `new Deferred[2]` only creates an **array object** with two reference slots initially set to `null`; it has not yet created two `Deferred` objects.
- `Class.forName("Deferred", false, loader)` may require loading/linking to obtain metadata, but **does not require initialization**.
- The single-argument `Class.forName("Deferred")` **requires initialization**, so the static block prints before `after forName`.
- The subsequent `new Deferred()` only runs the instance constructor; `Deferred.static` does not print again.

Note that `Class.forName(name)` only requests class initialization and **does not create a Deferred instance**. `ClassNotFoundException` occurs if the class cannot be found by name; that is a different error from an exception occurring **inside the static initializer** of a class that was found.

## 10. Failed Static Initialization: The Concept of an Erroneous Class State

A static field initializer or static initializer block can perform computations, read configuration, or invoke methods. If a step throws an unhandled exception and class initialization cannot complete normally, the JVM marks that class as **initialization failed/erroneous** according to the specification procedure.

Conceptual diagram:

~~~text
Class is not yet initialized
          |
          v
An active use requires initialization
          |
          v
Run static initializers and static blocks
          |
          +---- succeeds -----> Initialized
          |                     subsequent uses do not rerun static code
          |
          +---- throws error -> Erroneous
                                subsequent uses do not simply retry
                                may encounter NoClassDefFoundError
~~~

**Key point:** a failure during the class initialization phase is not like a normal method call throwing an exception. Class initialization is a stateful procedure in the JVM, shared by code using **the same runtime class**.

If a static initializer fails due to misconfiguration, you cannot assume that fixing an environment variable and calling that class again in the same class loader will make the JVM automatically rerun static initialization as it did the first time.

## 11. Experiment 4: First `ExceptionInInitializerError`, Next `NoClassDefFoundError`

Create the file **`FailedClassInitializationDemo.java`**:

~~~java
class FaultySettings {
    static int port = loadPort();

    private static int loadPort() {
        System.out.println("FaultySettings.init");
        throw new IllegalStateException("invalid port");
    }
}

public class FailedClassInitializationDemo {
    private static void use() {
        System.out.println(FaultySettings.port);
    }

    public static void main(String[] args) {
        try {
            use();
        } catch (ExceptionInInitializerError ex) {
            System.out.println("first="
                    + ex.getClass().getSimpleName());
            System.out.println("cause="
                    + ex.getCause().getClass().getSimpleName());
        }

        try {
            use();
        } catch (NoClassDefFoundError ex) {
            System.out.println("second="
                    + ex.getClass().getSimpleName());
        }

        System.out.println("main.end");
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 FailedClassInitializationDemo.java
java FailedClassInitializationDemo
~~~

**Exact stdout:**

~~~text
FaultySettings.init
first=ExceptionInInitializerError
cause=IllegalStateException
second=NoClassDefFoundError
main.end
~~~

### Line-by-Line Explanation

1. `use()` reads `FaultySettings.port` for the first time: it is a non-constant static field, so `FaultySettings` must be initialized.
2. `loadPort()` prints `FaultySettings.init`, then throws `IllegalStateException`.
3. According to class initialization rules, when the cause is not an `Error`, the JVM wraps the exception in an **`ExceptionInInitializerError`**; in this example, `getCause()` is `IllegalStateException`.
4. `FaultySettings` is marked as having failed initialization.
5. The second `use()` call does not reinitialize that class; the JVM throws **`NoClassDefFoundError`** in this situation. Therefore, there is no second `FaultySettings.init` line.

**`NoClassDefFoundError` does not always mean the class file was deleted.** It can be the direct consequence of **a class having been found earlier but failing to initialize**. You need to inspect the exception chain and the first error in the log.

## 12. An `Error` Thrown in a Static Initializer Is Not Necessarily Wrapped Further

JLS §12.4.2 specifies how the cause of a failed initialization is handled. If the exception/throwable causing the failure **is already an `Error`**, the JVM does not need to wrap it into a new `ExceptionInInitializerError` as in that case.

Create the file **`ErrorDuringInitializationDemo.java`**:

~~~java
class BrokenContract {
    static int value = check();

    private static int check() {
        System.out.println("BrokenContract.init");
        throw new AssertionError("contract broken");
    }
}

public class ErrorDuringInitializationDemo {
    public static void main(String[] args) {
        try {
            System.out.println(BrokenContract.value);
        } catch (AssertionError ex) {
            System.out.println("first="
                    + ex.getClass().getSimpleName());
        }

        try {
            System.out.println(BrokenContract.value);
        } catch (NoClassDefFoundError ex) {
            System.out.println("second="
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 ErrorDuringInitializationDemo.java
java ErrorDuringInitializationDemo
~~~

**Stdout:**

~~~text
BrokenContract.init
first=AssertionError
second=NoClassDefFoundError
~~~

Unlike the previous example, the cause is `AssertionError`, which itself belongs to `Error`; therefore, the first time the caller catches **`AssertionError`**, not an `ExceptionInInitializerError` created to wrap `IllegalStateException`.

The subsequent usage request still encounters `NoClassDefFoundError` because the class is already in an erroneous initialization state.

### Why Not Write `static { throw new RuntimeException(); }` Directly?

Java has a rule that **a static initializer block must be able to complete normally** under compile-time analysis. A block containing such an unconditional `throw` statement is rejected by the compiler. The runnable examples here use a **static field initializer that calls a method**, and the method throws an exception at runtime. This is a way to demonstrate an initialization failure while remaining syntactically valid.

## 13. Experiment 5: An Exception in a Constructor Does Not Make the Class Erroneous

Even for the same exception, where it originates changes its meaning.

Create the file **`ConstructorExceptionDemo.java`**:

~~~java
class RetryableObject {
    static {
        System.out.println("RetryableObject.static");
    }

    RetryableObject(int amount) {
        System.out.println("constructor amount=" + amount);
        if (amount < 0) {
            throw new IllegalArgumentException("negative");
        }
    }
}

public class ConstructorExceptionDemo {
    public static void main(String[] args) {
        try {
            new RetryableObject(-1);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected=" + ex.getMessage());
        }

        new RetryableObject(1);
        new RetryableObject(2);
        System.out.println("done");
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 ConstructorExceptionDemo.java
java ConstructorExceptionDemo
~~~

**Stdout:**

~~~text
RetryableObject.static
constructor amount=-1
rejected=negative
constructor amount=1
constructor amount=2
done
~~~

At the first `new RetryableObject(-1)` call, **class initialization has already completed successfully** before the constructor runs. The constructor throws `IllegalArgumentException`, so only the creation of **that instance** fails. The class remains normally initialized, so the next two calls can create valid objects.

Do not lump all errors occurring “near the `new` keyword” into class initialization errors. You need to determine whether the exception is thrown **inside `<clinit>`** or **inside the constructor/instance initializer chain**. An error in an instance field initializer also belongs to the instance creation process and does not by itself make the class erroneous if the class has already been initialized.

## 14. Experiment 6: A Subclass Does Not Run Its Static Block When Superclass Initialization Fails

When a subclass needs to be initialized, the JVM ensures that the required superclass is initialized first. If superclass initialization fails, the subclass cannot run its static initializers along the normal path.

Create the file **`FailedSuperclassDemo.java`**:

~~~java
class BadParent {
    static int value = read();

    private static int read() {
        System.out.println("BadParent.init");
        throw new IllegalStateException("bad parent config");
    }
}

class BlockedChild extends BadParent {
    static {
        System.out.println("BlockedChild.static");
    }

    BlockedChild() {
        System.out.println("BlockedChild.constructor");
    }
}

public class FailedSuperclassDemo {
    public static void main(String[] args) {
        try {
            new BlockedChild();
        } catch (ExceptionInInitializerError ex) {
            System.out.println("first="
                    + ex.getClass().getSimpleName());
        }

        try {
            new BlockedChild();
        } catch (NoClassDefFoundError ex) {
            System.out.println("second="
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 FailedSuperclassDemo.java
java FailedSuperclassDemo
~~~

**Stdout:**

~~~text
BadParent.init
first=ExceptionInInitializerError
second=NoClassDefFoundError
~~~

`BadParent` throws an error before completing static initialization. Therefore, **`BlockedChild.static` is not printed**, nor is there any `BlockedChild.constructor`. The subclass cannot proceed with normal initialization when a required superclass dependency has failed.

Diagnostic takeaway: if a stack trace reports an error in a subclass, **the root cause may lie in the static initialization of the superclass**. Do not look only at the subclass's `static { ... }` and ignore the inheritance chain.

## 15. Successful Class Initialization Runs Only Once per Runtime Class Identity

In a typical application, a class is successfully initialized **once per runtime definition** of that class. Later creating more objects, reading static fields, or calling static methods does not rerun the initializers.

However, you need to distinguish **runtime class identity** from source name. Class identity in the JVM consists of the binary name and the **defining class loader**. Two classes defined by two different loaders can have the same binary name yet still be two separate runtime classes with their own static state and initialization state.

This is useful for understanding plugins, application servers, and hot-reload mechanisms. It does **not** mean a class loader can simply “reinitialize an erroneous class” by calling a method again. If you need to load a **different runtime definition**, that is a separate class-loader architecture concern, not a simple static reset command.

**You should not use `System.gc()` or create a new object as a way to try rerunning a static block.** Garbage collection is not a mechanism for reinitializing an already-initialized class.

## 16. Multithreading: The JVM Coordinates Initialization, but Does Not Make All Static State Thread-Safe

According to [JLS §12.4.2](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2), class initialization is stateful and coordinated across threads. If multiple threads concurrently need **one runtime class** initialized for the first time, the JVM does not let each thread independently execute a copy of the same static initializer.

However, that does **not** make mutable fields thread-safe afterward.

~~~java
class SharedCounter {
    static int count;

    static void increment() {
        count++;
    }
}
~~~

This is a valid illustrative class. After initialization, multiple threads calling `increment()` concurrently can cause lost updates, because `count++` is a non-atomic read-modify-write operation.

Similarly, you should not use a static initializer to perform complex blocking tasks that depend on other threads waiting for the same class to be initialized. You can run into liveness issues or circular dependencies between initializers.

**Separate the two questions:** the JVM initializes the class safely according to its own rules; meanwhile, **business operations after initialization** must explicitly design their own synchronization, ownership, or immutable structures.

## 17. Experiment 7: Initialization-on-Demand Holder

One application of the class initialization mechanism is the **holder idiom**: deferring the creation of an instance until the first time it is needed.

Create the file **`HolderOrderDemo.java`**:

~~~java
final class SettingsService {
    private SettingsService() {
        System.out.println("SettingsService.constructor");
    }

    static SettingsService get() {
        System.out.println("SettingsService.get");
        return Holder.INSTANCE;
    }

    private static class Holder {
        static final SettingsService INSTANCE =
                new SettingsService();

        static {
            System.out.println("Holder.static");
        }
    }
}

public class HolderOrderDemo {
    public static void main(String[] args) {
        System.out.println("main.start");
        SettingsService a = SettingsService.get();
        SettingsService b = SettingsService.get();
        System.out.println("same=" + (a == b));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 HolderOrderDemo.java
java HolderOrderDemo
~~~

**Stdout:**

~~~text
main.start
SettingsService.get
SettingsService.constructor
Holder.static
SettingsService.get
same=true
~~~

The outer class `SettingsService` is initialized when the static method `get` needs to execute, but the nested class `Holder` **is not required to be initialized merely because it sits inside the outer class**. The first time code accesses `Holder.INSTANCE`, the JVM initializes `Holder`: the initializer creates the object (so the constructor prints first), and only then does the static block print `Holder.static`.

The second `get()` call reads the same already-assigned field; no second object is created. `a == b` is `true` because both variables receive the same reference.

**Limitation:** a singleton having a single instance does not mean the methods on that instance are thread-safe if it holds mutable state; the holder idiom is primarily used to leverage the JVM's initialization guarantee for creating and publishing the reference under an appropriate design.

## 18. Four Error Groups to Distinguish When Diagnosing

| Error/error group | Typical origin | Meaning |
| --- | --- | --- |
| `ClassNotFoundException` | Calling a name-based API such as `Class.forName`, but the class cannot be found | Checked exception because the request to find the class failed |
| `NoClassDefFoundError` | The runtime cannot use the required class definition; or the class previously failed initialization | Does not necessarily mean “the class file never existed” |
| `ExceptionInInitializerError` | Static initialization throws a throwable that is not an `Error` and the JVM must wrap it | Error observed during class initialization |
| `IllegalArgumentException` in constructor | Invalid argument passed to create an instance | Usually only the instance creation fails |
| `NoSuchMethodError`, `NoSuchFieldError` | Binary/linkage incompatibility at runtime | Different from faulty logic inside a static initializer |
| `StackOverflowError` or `AssertionError` during initialization | May arise directly as an `Error` from the initializer | May propagate without being wrapped in `ExceptionInInitializerError` |

Two effective diagnostic questions:

1. Did the error occur while **linking/resolving** a class, while **running static initializers**, or while **calling a normal constructor/method**?
2. Is this the **first time that class failed**, or only a **subsequent use after initialization has already failed**?

If you only look at the final exception line without following the `Caused by` chain or earlier logs, it is very easy to misdiagnose. In the `FailedClassInitializationDemo` example, the most informative error is the **initial `IllegalStateException("invalid port")`**, not the `NoClassDefFoundError` on the second use.

## 19. Principles for Predicting Stdout

Treat an output prediction problem as simulating a state machine, rather than reading each `println` statement from top to bottom.

**Step 1 — List the classes:** the class containing `main`, superclass/subclass, nested classes, and helper classes with static initializers.

**Step 2 — Record each class's state:** uninitialized, initializing, initialized, or erroneous. An already initialized class will not rerun its static code on subsequent uses.

**Step 3 — Find the first active use:** `new`, a static method call, reading a nonconstant static field, or `Class.forName` requiring initialization. Avoid treating class literals/arrays/compile-time constants as triggers.

**Step 4 — Check inheritance:** required superclasses are initialized before subclasses; for interfaces/default methods, follow the JLS rules rather than mechanically applying class rules to every interface.

**Step 5 — Run static code in textual order:** record default values from preparation for nonconstant static fields and update them when the initializer actually runs. Do not recalculate an earlier field when another field is assigned later.

**Step 6 — If `new` succeeds and enters the instance phase:** traverse the superclass constructor chain, with each class executing its instance initializers/constructors in the specified order.

**Step 7 — If an exception occurs:** stop the normal execution path and transfer appropriately to the matching `catch`; if class initialization fails, mark the class erroneous and do not assume the initializer will run again.

**Step 8 — Only then list stdout:** error messages or messages may depend on the JVM, so avoid guessing the full stack trace; prefer printing specific error type names/values to get deterministic output.

## 20. Experiment A: A Constructor Calling an Overridden Method Too Early

Predict the output before running the following program. Create the file **`OverrideDuringConstructionDemo.java`**:

~~~java
class BaseReader {
    BaseReader() {
        System.out.println("base.ctor");
        read();
    }

    void read() {
        System.out.println("base.read");
    }
}

class DetailReader extends BaseReader {
    private String name = "READY";

    {
        System.out.println("detail.block " + name);
    }

    DetailReader() {
        System.out.println("detail.ctor " + name);
    }

    @Override
    void read() {
        System.out.println("detail.read " + name);
    }
}

public class OverrideDuringConstructionDemo {
    public static void main(String[] args) {
        new DetailReader();
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 OverrideDuringConstructionDemo.java
java OverrideDuringConstructionDemo
~~~

**Stdout answer:**

~~~text
base.ctor
detail.read null
detail.block READY
detail.ctor READY
~~~

**Solution:** the `DetailReader` object has already been allocated with default instance fields, where `name=null`. The superclass constructor `BaseReader()` runs before the subclass initializer `name="READY"`. The `read()` call performs **dynamic dispatch** to the override `DetailReader.read()`, so it observes `null`. Only after the parent constructor finishes does the subclass execute its initializer and block, and then the child constructor body.

**Design lesson:** avoid calling overridable methods from a superclass constructor and avoid letting `this` escape before the object is fully initialized. This is an **object initialization** phenomenon, not a class initialization error.

## 21. Experiment B: Static Initializer and `try/catch`

Create the file **`CaughtDuringStaticDemo.java`**:

~~~java
class RecoveringClass {
    static int port = getPort();

    private static int getPort() {
        System.out.println("try port");
        try {
            return Integer.parseInt("bad");
        } catch (NumberFormatException ex) {
            System.out.println("fallback");
            return 8080;
        }
    }

    static {
        System.out.println("port initialized=" + port);
    }
}

public class CaughtDuringStaticDemo {
    public static void main(String[] args) {
        System.out.println("main");
        System.out.println("port=" + RecoveringClass.port);
        System.out.println("again=" + RecoveringClass.port);
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 CaughtDuringStaticDemo.java
java CaughtDuringStaticDemo
~~~

**Stdout:**

~~~text
main
try port
fallback
port initialized=8080
port=8080
again=8080
~~~

Here the `NumberFormatException` is **completely caught and handled** inside the initializer, so class initialization **succeeds**, with no `ExceptionInInitializerError`. The second access simply reads the field that already received 8080.

**Key point:** just because a method called from a static initializer **threw an exception** does not mean the class will become erroneous. What decides is whether the entire class initialization process **completes normally or not**.

In a real application, if you use a fallback, you must have a clear policy: whether misconfiguration can accept a fallback value or needs to halt startup. Do not silently swallow errors if a default value violates business logic.

## 22. Self-Practice Output Prediction Exercises

Write down the stdout on your own before viewing the solutions. The snippets below are standalone illustrative classes or are assumed to be placed in valid files matching their respective class names.

**Question 1 — Static once.**

~~~java
class A {
    static {
        System.out.print("S");
    }

    A() {
        System.out.print("C");
    }
}
~~~

If a `main` method in another class calls `new A(); new A();` for the first time and there is no other printing code, what is the output?

**Question 2 — Constant.**

~~~java
class B {
    static final int N = 5;
    static {
        System.out.print("I");
    }
}
~~~

In a `main` method of another class, only `System.out.print(B.N);` is called. Is `I` printed?

**Question 3 — Static method.**

~~~java
class C {
    static {
        System.out.print("I");
    }

    static void work() {
        System.out.print("W");
    }
}
~~~

In a `main` method of another class calling `C.work(); C.work();`, what string is printed?

**Question 4 — Field read early.**

~~~java
class D {
    static int x = init();
    static int y = 4;

    static int init() {
        System.out.print(y);
        return y + 1;
    }
}
~~~

When another `main` uses `D.x` for the first time, what character does the `init()` method print and what value does `D.x` have?

**Question 5 — Inheritance.** Class `P` prints `P` in its static block, and `Q extends P` prints `Q` in its static block. If neither class has been initialized yet and `new Q()` is called, in what order are the two letters printed?

**Question 6 — Failure.** The static initializer of `Broken` first calls a method that throws an uncaught `IllegalStateException`. The caller catches `ExceptionInInitializerError` and then **continues accessing a static field of the same Broken**. What error type is typically encountered the next time?

**Question 7 — Constructor.** A class has a valid static block, and its constructor throws `IllegalArgumentException` for an invalid argument. After catching the error, the caller creates another object with a valid argument. Does it automatically receive `NoClassDefFoundError`?

**Question 8 — Class literal.** Do `T.class` and `new T[2]` require the static block of `T` to run if no other action has triggered it?

**Question 9 — Direct Error.** A method called inside a static initializer throws `AssertionError`, and there is no catch. On the first time, must the error be wrapped in a new `ExceptionInInitializerError`?

**Question 10 — Holder.** Why does the second read of `Holder.INSTANCE` not print Holder's static block again, even though the code uses the same class name again?

**Question 11 — Catch inside initializer.** A static field initializer calls `parse()`; `parse()` catches `NumberFormatException` and returns a valid value. Must the class become erroneous?

**Question 12 — Inherited static field.** `Parent` declares `static int count`, and `Child extends Parent` has its own static block. Does reading only `Child.count` necessarily initialize `Child`?

### Detailed Answers

1. **`SCC`**: static code runs once, constructor runs for two objects.
2. **`5`**, without printing `I`: `N` is a compile-time constant variable.
3. **`IWW`**: `C` is initialized before the first static method call, then `work` runs twice.
4. Prints **`0`**, and afterward `D.x=1`; `y` is still at its default 0 when `init` runs.
5. **`PQ`**: the superclass is initialized before the subclass.
6. Typically **`NoClassDefFoundError`** within the same runtime class/class loader because the first initialization failed.
7. **No**. A constructor failure does not by itself make the class erroneous; another instantiation can succeed.
8. **Does not on its own require** initialization of the component class `T`; the array is created separately.
9. **No**. Because the cause is already an `Error`, it can be propagated directly according to the initialization rules.
10. The holder class has already been initialized successfully; the JVM does not re-execute the static initializer on every read.
11. **No**; the initializer completes normally, so the class can be initialized successfully.
12. **No**, because the field is declared by `Parent`. Consider the class declaring the field, not just the name `Child` before the dot.

## 23. Observation Matrix When Running the Examples

To verify on your own, you can run them in your own study directory (each standalone program has the name stated earlier):

| Program file | What to observe | Key indicator |
| --- | --- | --- |
| `FirstUseOrderDemo.java` | Main static, constant, static field, constructors | `Main.initialized` first; `Warmup` waits until nonconstant field |
| `ParentChildTraceDemo.java` | Parent/child and two objects | Parent/child static once; instance chain twice |
| `StaticForwardReadDemo.java` | Field read before initializer | `during later=0`, then `later=10` |
| `ConstantTriggerDemo.java` | Constant vs nonconstant | `compute` appears only before the line reading `COMPUTED` |
| `DeferredInitializationDemo.java` | Class literal/array/`forName(false)` | `Deferred.static` only when `forName(name)` requests init |
| `FailedClassInitializationDemo.java` | First failure vs subsequent use | `ExceptionInInitializerError` then `NoClassDefFoundError` |
| `ErrorDuringInitializationDemo.java` | Cause is an `Error` | `AssertionError` first, NCDFE afterward |
| `ConstructorExceptionDemo.java` | Instance failure | One static print, new constructor calls can be tried |
| `FailedSuperclassDemo.java` | Parent failure blocks child | No `BlockedChild.static` line |
| `HolderOrderDemo.java` | Lazy holder | Constructor once and `same=true` |
| `OverrideDuringConstructionDemo.java` | Premature dynamic dispatch | `detail.read null` |
| `CaughtDuringStaticDemo.java` | Handled exception | Fallback succeeds, no EIIE |

When the result differs from expectations, first check whether you actually ran **the right compiled file/class**. For programs using the default package, the `java ClassName` command must be run from where the appropriate class files reside; for named packages, the classpath and package-qualified name must be exact.

Each example has its own top-level public class to avoid conflicts between study snippets; if you copy multiple examples into the same project, keep class names and packages non-colliding as appropriate for your project.

## 24. Real-World Error Scenarios and Diagnosis

**Scenario A — Static configuration failure.** A class reads an environment variable inside a static initializer and throws `IllegalStateException`. When the application uses that class for the first time, the error may be wrapped in `ExceptionInInitializerError`. How to handle: find the initial cause; consider validating configuration at startup through a mechanism that reports errors clearly instead of waiting for the class to be used unexpectedly.

**Scenario B — Only `NoClassDefFoundError` remains in logs.** A later request reports that the class cannot be initialized. An earlier request may have caused class initialization to fail. How to handle: find the log from the **first use** and the cause chain; inspect the class loader, configuration, static code, and dependencies.

**Scenario C — First test passes, subsequent test differs.** Tests sharing the same JVM/class loader may encounter a class already initialized by an earlier test. Never assume the static initializer reruns when creating a new instance. Test design should avoid suite-wide ordering dependencies; reset mutable state in a controlled manner, use dependency injection, or isolate into separate processes when JVM-level isolation is truly needed.

**Scenario D — Thread deadlock around initialization.** Two complex static initializers can require each other or wait on other threads while class initialization is synchronized. How to handle: minimize side effects in static blocks, avoid I/O/complex lock waiting, and inspect a thread dump when needed.

**Scenario E — Subclass configuration is not yet available.** A superclass constructor calls an overridable method; the subclass field has not yet run its initializer and is `null`. This is an **object initialization/inheritance design** bug, not necessarily a class initialization failure.

**Scenario F — Binary errors after a library upgrade.** `NoSuchMethodError` or `NoSuchFieldError` may involve linking/resolution without any broken static initializer. Check binary compatibility and dependency versions.

## 25. Safe Static Initialization Design Checklist

- Do you really need to compute data immediately inside a `static` field initializer or static block?
- Can you use a **constant expression** for simple immutable constants?
- Does the initializer expression perform I/O, wait on locks, start threads, or call unpredictable external code?
- If reading configuration fails, should the program halt startup or use a clearly defined fallback?
- Are there circular dependencies between static fields/classes that cause default values to be read too early?
- Is the source order among static initializers kept clear?
- Are there superclasses/interfaces that must be initialized first according to the JLS?
- If a static initializer throws an error, does the first log entry contain enough context to trace the cause?
- Is there a false assumption that an erroneous class will automatically be reinitialized in the same loader?
- Is an overridable method accidentally called from a constructor, leaving subclass fields unready?
- If mutable static state is used across multiple threads, is there a dedicated synchronization/atomic update mechanism?
- Do tests avoid depending on execution order or static state from previous tests?

**Good design does not try to “catch every `Error`” and keep going.** You should reduce the likelihood of errors during class initialization, report the cause clearly, and choose an appropriate lifecycle for managing configuration and dependencies.

## 26. Authoritative Reference Documents

- [Java Language Specification 17, §12.2 — Loading of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.2): type loading and class loaders.
- [JLS 17, §12.3 — Linking of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.3): verification, preparation, and resolution.
- [JLS 17, §12.4.1 — When Initialization Occurs](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.1): active use, constants, static fields, and subclasses.
- [JLS 17, §12.4.2 — Detailed Initialization Procedure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2): class states, initialization synchronization, and failure handling.
- [JLS 17, §12.5 — Creation of New Class Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.5): instance initialization and constructor ordering.
- [JLS 17, §8.3.3 — Restrictions on Field References in Initializers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3.3): illegal forward references.
- [JLS 17, §8.7 — Static Initializers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.7): requirements for static initializers.
- [JLS 17, §4.12.4 — final Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): constant variables and how they are determined.
- [Java Virtual Machine Specification 17, §5.5 — Initialization](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5): class initialization mechanism in the JVM.
- [Java SE 17 API — Class.forName](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#forName(java.lang.String,boolean,java.lang.ClassLoader)): choosing initialization via reflection.
- [Java SE 17 API — ExceptionInInitializerError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ExceptionInInitializerError.html): error when a static initializer/field initializer throws an exception.
- [Java SE 17 API — NoClassDefFoundError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoClassDefFoundError.html): runtime error when a class definition cannot be used.

**Remember:** Class initialization proceeds according to **JVM triggers and states**, not the number of times a class appears in the source. Static code runs in **initializer order** when the class needs to be initialized; instance constructors run **for each object**. If class initialization throws a non-`Error` exception, the caller typically sees **`ExceptionInInitializerError` on the first attempt**; the class becomes **erroneous**, and **subsequent uses may see `NoClassDefFoundError`**. Trace back to the **first cause**, distinguish constructor errors from class errors, and use a state table to predict stdout accurately.
