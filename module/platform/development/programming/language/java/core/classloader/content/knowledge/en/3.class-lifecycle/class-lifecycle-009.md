# Class Initialization Before Executing Operations That Require It in Java

A class may already be **loaded** and **linked**, yet its `static` block still has not run. The JVM only **initializes** a class or interface when a specific operation requires it. Before allowing the operation to proceed, the JVM guarantees that the required initialization has completed, or reports an error if initialization fails. This mechanism explains why `SomeType.class` typically does not print `static` logs, whereas `new SomeType()` or `SomeType.run()` can print logs on first use.

This lesson focuses on **when and in what order the JVM initializes a class before operations that require it**, under the **Class Lifecycle** group of Java core – classloader. The goal is to predict when `<clinit>` runs, identify operations that trigger and do not trigger initialization, understand the guarantees in a multithreaded environment, and analyze errors when a static initializer fails.

## 1. Distinguishing Loading, Linking, and Initialization

| Phase | Main Work | Does It Run Statements in `static { ... }`? |
| --- | --- | --- |
| **Loading** | Locate/read the binary definition and create the `Class` object corresponding to the name and defining class loader | Not the step that runs the static initializer |
| **Linking – verification** | Verify bytecode validity and structural safety | No |
| **Linking – preparation** | Allocate/provision state for static fields and set default values such as `0`, `false`, `null` | Does not run Java code of the static initializer |
| **Linking – resolution** | Resolve symbolic references to types, fields, and methods according to JVM rules; can happen eagerly or on demand | An ordinary resolution operation by itself does not mean initializing the referenced class |
| **Initialization** | Set constant values via `ConstantValue` metadata where applicable, initialize required superclasses/default-method superinterfaces, and execute class/interface initialization logic | Yes, when the class/interface has code to execute |

In the Java 17 JVM, the **initialization** phase is when `final static` fields with `ConstantValue` are assigned their specified values and the initialization method `<clinit>` is executed. Before that, static fields have already been prepared with default values. Therefore, you should not equate "a static field already exists" with "the static field has finished being assigned its initial value".

Example:

```java
class Settings {
    static int port = loadPort();

    static int loadPort() {
        System.out.println("Loading port");
        return 8080;
    }
}
```

The `loadPort()` code runs **when `Settings` is initialized**, not merely because a tool has loaded `Settings.class` into the JVM. This distinction is also important when using classpath scanning, reflection, plugin loaders, and metadata inspection tools.

A class that has completed initialization is considered initialized within the scope of **that class definition**. The same class name, if defined by two different defining loaders, will have two separate `Class` instances and separate initialization states; there is no "once for all classes with the same name across the entire application" rule.

## 2. Which Operations Force Initialization?

According to Java/JVM rules, the trigger timing depends on **the operation executed** and **the class/interface that actually declares the resolved member**, not merely the character string used to write the class name in source code.

| Operation / Scenario | Requires Initialization? | Explanation |
| --- | --- | --- |
| `new Worker()` | **Yes** for `Worker` before creating the instance | The `new` bytecode instruction requires the class to be initialized; superclasses and certain superinterfaces are also initialized according to the rules |
| `Worker.work()` where `static void work()` is declared by `Worker` | **Yes** | The `invokestatic` instruction requires initialization of the type declaring the resolved method |
| Reading `Worker.count` where `static int count` is not a constant variable | **Yes** | `getstatic` requires the type declaring the field to have been initialized |
| Writing `Worker.count = 5` | **Yes** | `putstatic` requires the type declaring the field to have been initialized |
| `Worker.COMPILE_TIME_CONST` with `static final int` assigned a constant expression | **Not solely from reading this constant** | The compiler can substitute the value directly into bytecode; no `getstatic` on the field is needed |
| `Worker.class` | **Not from the class literal alone** | You can obtain the `Class` object without initializing `Worker` |
| `new Worker[10]` | **Not from array creation alone** | Creating an object array is different from creating a `Worker` instance; the component class is not forced to initialize |
| `ClassLoader.loadClass("pkg.Worker")` | **Not from calling loadClass alone** | Typically brings the class to the loaded state; loading itself does not mean initialization |
| `Class.forName("pkg.Worker")` | **Yes** for the single-parameter overload | This overload requires initialization of the located type |
| `Class.forName(name, false, loader)` | **Does not require initialization** | The `initialize=false` parameter intentionally avoids triggering it |
| Retrieving metadata via APIs such as `getName()`, `getDeclaredMethods()` | **Not from ordinary metadata lookup operations alone** | Reflective inspection and reflective invocation/access are two different things |
| Invoking a static method via `Method.invoke` or reading a static field via `Field.get` | **Yes when the access actually requires it** | Certain reflection methods trigger initialization of the declaring class |
| The JVM selects the program's initial class | **Yes** | The initial class/interface is initialized according to JVM startup rules |
| Initializing a subclass | **Yes** for uninitialized superclasses | Ensures required parent classes are initialized before the child class |

At the bytecode level, the four key instructions are **`new`, `getstatic`, `putstatic`, `invokestatic`**. For `getstatic`, `putstatic`, and `invokestatic`, the type that must be initialized is the **declaring class/interface** of the field or method after the symbolic reference is resolved.

More specialized cases include the first invocation of a resolved `MethodHandle` of kind `REF_getStatic`, `REF_putStatic`, `REF_invokeStatic`, or `REF_newInvokeSpecial`; the bootstrap method of certain `invokedynamic` call sites can also trigger initialization. This is an extension of the same principle: the type's state must be finalized before executing the static or instance-creation operation that the call actually requires.

**Distinguish between these two statements:**

- "Java source mentions the name `Worker`" is **not enough** to conclude that `Worker` initializes.
- "The JVM executes `getstatic` or `invokestatic` targeting a member declared by `Worker`" is a **condition that requires initialization** of `Worker` if it is not yet initialized.

## 3. Runnable Example: What Triggers and What Does Not Trigger Initialization?

Create a single file `InitializationDemo.java`:

```java
public class InitializationDemo {
    static class Parent {
        static final int LIMIT = 42; // constant variable: can be inlined

        static int first = announce("Parent.first", 7);

        static {
            System.out.println("Parent.block");
        }

        static final Integer BOXED = createBoxed(); // not a constant variable

        static int announce(String label, int value) {
            System.out.println(label);
            return value;
        }

        static Integer createBoxed() {
            System.out.println("Parent.BOXED");
            return 99;
        }
    }

    static class Child extends Parent {
        static {
            System.out.println("Child.block");
        }

        static void ping() {
            System.out.println("Child.ping");
        }
    }

    static class Unused {
        static {
            System.out.println("Unused.block");
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("1 LIMIT=" + Child.LIMIT);
        System.out.println("2 literal=" + Unused.class.getSimpleName());
        System.out.println("3 array=" + new Unused[0].length);

        Class<?> type = Class.forName(
            "InitializationDemo$Unused",
            false,
            InitializationDemo.class.getClassLoader()
        );
        System.out.println("4 loaded=" + type.getSimpleName());

        System.out.println("5 call Child.ping()");
        Child.ping();

        System.out.println("6 BOXED=" + Child.BOXED);
        System.out.println("7 forName true");
        Class.forName("InitializationDemo$Unused");

        System.out.println("8 again");
        Child.ping();
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac --release 17 InitializationDemo.java
java InitializationDemo
```

Stdout:

```text
1 LIMIT=42
2 literal=Unused
3 array=0
4 loaded=Unused
5 call Child.ping()
Parent.first
Parent.block
Parent.BOXED
Child.block
Child.ping
6 BOXED=99
7 forName true
Unused.block
8 again
Child.ping
```

Reading in order:

1. `Child.LIMIT` accesses a compile-time constant **declared in `Parent`**. The value `42` can be inlined into the client code; in this example, neither `Parent.first` nor `Child.block` appears at step 1.
2. `Unused.class` only retrieves the `Class<?>` object; `new Unused[0]` only creates an array. Neither step forces `Unused.block` to run.
3. `Class.forName(name, false, loader)` only requests lookup/loading and on-demand linking, **without requiring** the static block to run; therefore the line `4 loaded=Unused` still appears before `Unused.block`.
4. On the first call to `Child.ping()`, the JVM must initialize `Child` before running the method body. `Parent` is an uninitialized superclass, so `Parent` runs first: assigns `first`, executes its static block, and computes `BOXED`; only then does `Child.block` run, and finally the method prints `Child.ping`.
5. `Child.BOXED` is actually a static field declared by `Parent`. `Parent` is already initialized, so it simply prints `99`; reading a field through a subclass name **does not itself trigger another `<clinit>` run**.
6. `Class.forName("InitializationDemo$Unused")` using the single-argument overload requires initializing `Unused`, so `Unused.block` appears at this point.
7. Calling `Child.ping()` again executes only the **method body**. Initialization of `Parent` and `Child` is already complete and is not repeated.

Note: The code above is **a standalone runnable program**. If you only run `javap` without running `java InitializationDemo`, inspecting the class file with a tool does not prove that the application's own static initializer actually ran.

## 4. How Is `<clinit>` Generated and Executed?

`javac` typically synthesizes static field initializers and `static { ... }` blocks of **the same class** into a class initialization method named **`<clinit>`** in bytecode. Java programs do not call this method directly.

For the `Parent` example, the logical order is:

```text
Initial static values after preparation: first=0, BOXED=null
          |
JVM decides Parent must be initialized
          |
Apply LIMIT ConstantValue (=42) if needed
          |
first = announce("Parent.first", 7)  -> prints "Parent.first"
          |
static { println("Parent.block"); } -> prints "Parent.block"
          |
BOXED = createBoxed()               -> prints "Parent.BOXED"
          |
Parent completes initialization
          |
JVM proceeds to initialize Child
```

**Order within the same class:** static field initializers and static blocks run in **the order they appear in source code**. Only after the superclass and any required superinterfaces have been initialized does the JVM execute the initialization logic of the current class.

Use:

```bash
javap -c -p 'InitializationDemo$Parent'
javap -c -p 'InitializationDemo$Child'
```

In PowerShell and shells that support single quotes, the syntax above preserves the `$` character in the nested class name. In Windows Command Prompt, you can use `javap -c -p "InitializationDemo$Parent"`. Look for the `static {};` block printed by `javap`: that is the bytecode representation of `<clinit>`, containing instructions such as `putstatic`, `invokestatic`, and the instructions that print output.

**Not every class necessarily has `<clinit>`.** A class that needs no runtime initialization work may omit that method. Even so, the JVM still tracks the "initialized" state to satisfy lifecycle rules.

### Default State and Reading Values Before Assignment

During initialization, a static field can already exist with its default value while its initializer has not yet been reached. To observe this, create `InitializationOrder.java`:

```java
public class InitializationOrder {
    static int first = readSecond();
    static int second = 9;

    static int readSecond() {
        return second;
    }

    public static void main(String[] args) {
        System.out.println(first + "," + second);
    }
}
```

```bash
javac --release 17 InitializationOrder.java
java InitializationOrder
```

Exact stdout:

```text
0,9
```

At the time `first` is assigned, `readSecond()` sees `second` still holding its default value `0`; the assignment `second = 9` only happens afterward. Directly reading a field declared *later* inside an initializer can violate the language's **illegal forward reference** rule; accessing it through a method as in this example is legal. You should not rely on such intricate ordering when designing shared state.

## 5. Superclasses and Superinterfaces: Which Is Initialized First?

When initializing a **class**, the JVM must initialize any uninitialized superclasses. In addition, **direct or indirect superinterfaces that declare a default method** are also subject to mandatory initialization under JVMS/JLS rules. This is subtler than saying "interfaces are always initialized after classes" or "all interfaces are initialized before classes": both statements are false.

In the earlier example, `Child` forces `Parent` to initialize first, so `Parent.first`, `Parent.block`, and `Parent.BOXED` always precede `Child.block`.

### Inherited Static Fields: The Declaring Type Is What Matters

Create the file `FieldOwnerDemo.java`:

```java
public class FieldOwnerDemo {
    static class Base {
        static int count = init();

        static int init() {
            System.out.println("Base.init");
            return 10;
        }
    }

    static class Derived extends Base {
        static {
            System.out.println("Derived.init");
        }
    }

    public static void main(String[] args) {
        System.out.println(Derived.count);
    }
}
```

```bash
javac --release 17 FieldOwnerDemo.java
java FieldOwnerDemo
```

Stdout:

```text
Base.init
10
```

`Derived.count` in source refers to a field **declared by `Base`**, so the JVM requires initializing `Base` and **does not automatically initialize `Derived`**. This differs from `new Derived()` or calling a static method actually declared by `Derived`.

### Interfaces with Default Methods

Create the file `DefaultInterfaceDemo.java`:

```java
public class DefaultInterfaceDemo {
    interface Feature {
        Object MARKER = report();

        static Object report() {
            System.out.println("Feature.init");
            return new Object();
        }

        default void execute() { }
    }

    static class Service implements Feature {
        static {
            System.out.println("Service.init");
        }
    }

    public static void main(String[] args) {
        new Service();
    }
}
```

```bash
javac --release 17 DefaultInterfaceDemo.java
java DefaultInterfaceDemo
```

Stdout:

```text
Feature.init
Service.init
```

`Service` is a class implementing `Feature`; `Feature` declares a `default` method, so the initialization of `Service` triggers initializing `Feature` first. `MARKER` is evaluated during the interface's initialization, even though the code in `main` does not directly access `MARKER`.

**The converse is not symmetric:** initializing an interface by itself does not implicitly initialize all of its superinterfaces. Accessing a static field through a subinterface name also depends on where the field **is actually declared**. If an interface has an inlined compile-time constant field, accessing that value does not necessarily initialize the declaring interface either.

## 6. Reflection and Class Loading Are Not the Same as Initialization

There are two easily confused overloads:

```java
Class<?> a = Class.forName("com.example.Plugin");
Class<?> b = Class.forName(
    "com.example.Plugin",
    false,
    Thread.currentThread().getContextClassLoader()
);
```

The snippet above is an **API illustration**; it runs only if `com.example.Plugin` exists and the class loader is appropriate. With the single-parameter overload, finding the class comes with a requirement to initialize it; with the three-parameter overload, `false` means **do not require initialization during lookup**. Later, when the client actually uses `new`, calls a static method, accesses a non-constant static field, or uses reflection to perform an operation requiring initialization, that initialization can still begin.

Operations that generally **do not by themselves require** initializing the target class include: obtaining `T.class`, creating `T[]`, inspecting the name from `Class<?>`, listing methods/fields, and checking types via `instanceof` or `checkcast`. A metadata API may still need to load/resolve related types or raise other errors; "not initializing the target class" does not mean "doing nothing at all".

Conversely, operations that actually **invoke** a static method (`Method.invoke`) or **read/write** a static field (`Field.get`/`Field.set`) follow the initialization rules for the declaring class. Distinguishing descriptor lookup from member usage helps avoid unintended side effects when a plugin scanner only intends to read metadata.

## 7. How Does the JVM Guarantee Exactly-Once Initialization Across Multiple Threads?

For a given **class/interface definition**, the initialization procedure coordinates threads to prevent running the static initializer twice. You can picture the states as follows:

```text
VERIFIED + PREPARED, NOT YET INITIALIZED
        |
        | first thread executes a requiring operation
        v
INITIALIZATION IN PROGRESS (owned by one thread)
        |               |
        |               +-- other threads wait for the result
        |               +-- same thread requests recursively: handled specially by the JVM
        |
        +-- completes successfully --> INITIALIZED
        |
        +-- fails -------------------> ERRONEOUS
                                           |
                                           +-- subsequent request: NoClassDefFoundError
```

Key rules:

- If thread A is currently initializing `T`, thread B concurrently executing an operation that requires `T` must wait for the result according to the JVM mechanism. Threads that subsequently use `T` after successful initialization observe the initialization results under the guarantees of the Java Memory Model.
- If thread A itself inadvertently triggers initialization of `T` again while executing `T.<clinit>`, the JVM recognizes the recursive request from the same thread and does not rerun the entire initializer.
- This **does not eliminate deadlocks** if two threads concurrently initialize two different classes and each class ends up waiting for the other. Avoid cross-locking, unbounded I/O, or thread joins inside static initializers.
- After successful initialization, the JVM **does not rerun** `<clinit>` simply because multiple instances of the class are created later. Each instance's constructor (`<init>`) is a separate mechanism.

### Application: Initialization-on-Demand Holder

A common pattern uses initialization state to lazily create a singleton:

```java
public final class LazyService {
    private LazyService() { }

    private static final class Holder {
        static final LazyService INSTANCE = new LazyService();
    }

    public static LazyService getInstance() {
        return Holder.INSTANCE;
    }
}
```

This is a **complete, compilable class**; this snippet has no `main` method. A call to `LazyService.getInstance()` must initialize `LazyService` before invoking the method, but **does not require initializing the nested `Holder` class before reaching the line that accesses `Holder.INSTANCE`**. Executing `getstatic` for `Holder.INSTANCE` triggers the initialization of `Holder` and creates a single `LazyService` instance for `Holder`'s defining loader. This pattern relies on the JVM's initialization synchronization mechanism, without needing to add `synchronized` to the getter.

A static field declared as `final` **does not automatically** become a constant variable; `Holder.INSTANCE` is a reference computed with `new`, so reading it must go through `getstatic`, unlike the primitive constant `static final int LIMIT = 42`.

## 8. What Happens If a Static Initializer Fails?

Create the file `FailedInitialization.java`:

```java
public class FailedInitialization {
    static class Broken {
        static int value = fail();

        static int fail() {
            throw new IllegalStateException("boom");
        }
    }

    public static void main(String[] args) {
        for (int attempt = 1; attempt <= 2; attempt++) {
            try {
                System.out.println(Broken.value);
            } catch (LinkageError error) {
                System.out.println(
                    attempt + ": " + error.getClass().getSimpleName()
                );
            }
        }
    }
}
```

```bash
javac --release 17 FailedInitialization.java
java FailedInitialization
```

Stdout:

```text
1: ExceptionInInitializerError
2: NoClassDefFoundError
```

On the first access to `Broken.value`, the JVM begins initialization and calls `fail()`. `IllegalStateException` is an exception that is not an `Error`, so the JVM wraps it in `ExceptionInInitializerError`, a subclass of `LinkageError`. The `Broken` definition transitions to the **erroneous** state. The second access does not re-initialize it; the JVM throws `NoClassDefFoundError` because the class previously failed during initialization.

If the original failure inside `<clinit>` is already a subclass of `Error`, the JVM typically propagates that `Error` on the initial failure attempt rather than wrapping it in `ExceptionInInitializerError`. If a superclass fails while initializing a subclass, the subclass can also be marked erroneous. When analyzing failures, inspect **the first exception and its cause**; looking only at the later `NoClassDefFoundError` line can easily mislead you into thinking the class file "disappeared".

Within an active class loader, an initialization failure generally cannot be recovered by invoking the same class again. You must fix the root cause (configuration, dependency, or exception in static code), then restart or load a new definition through an appropriate class loader when the architecture genuinely supports it.

**Practical design rule:** avoid network calls, DB queries, failure-prone file operations, and mutual dependencies across multiple classes inside static initializers. When a resource needs retry logic, use an initialization API with explicit state and error management rather than turning a transient failure into an erroneous class.

## 9. Using `javap` to Identify Triggers Before Running

After compiling `InitializationDemo.java`, run:

```bash
javap -c -p InitializationDemo
javap -c -p 'InitializationDemo$Parent'
javap -c -p 'InitializationDemo$Child'
javap -v -p InitializationDemo
```

What to look for:

1. Locate `invokestatic` at the `Child.ping()` call site. This instruction requires the JVM to ensure that the declaring class has been initialized before the method runs.
2. Locate `getstatic` for `Parent.BOXED` (it may be referenced via `Child` in source code, but the post-compilation owner is where the field is declared).
3. For `Child.LIMIT`, the compiler may generate the string literal `"1 LIMIT=42"` for printing or use an inline constant directly, **without** needing an instruction to read the static field `LIMIT` from `Parent`. Java can fold constant expressions at compile time; inspect the actual bytecode.
4. In the output of `javap -c -p 'InitializationDemo$Parent'`, the `static {};` block describes the sequence of class initialization logic, including writes to non-constant-variable static fields.
5. Use `javap -v` to inspect constant pool entries, field/method reference instructions, and `ConstantValue` metadata where present. **The mere presence of a type name in the constant pool does not prove that the class has been initialized.**

The key takeaway is: **symbolic references are recorded at compile time, resolution identifies the runtime entity, and initialization begins when JVM conditions require it**. Therefore, merely looking at dot notation `SomeClass.member` in source code is not enough; you must check whether the member is static or instance, whether it is a compile-time constant, who actually declares it, and which bytecode instruction is emitted.

If you need logging for loaded classes, you can try `java -Xlog:class+load=info InitializationDemo` on a HotSpot JVM that supports unified logging. However, **load logs are not initialization logs**. To verify initialization in the example, observe the lines printed by `static` blocks/initializers and the actual execution order.

## 10. Common Misconceptions

| Misconception | Correct Understanding |
| --- | --- |
| "Merely importing or mentioning a class name runs its static block." | `import` is compile-time syntax; class literals, metadata lookups, and array creation do not by themselves trigger initialization. |
| "Loading a class means initializing that class." | Loading/linking and initialization are distinct phases; `Class.forName(name, false, loader)` demonstrates this separation. |
| "Every static field access always runs the static block." | Compile-time constant fields can be inlined; inherited static fields only require initializing the type where the field is actually declared. |
| "A child class can run its static initializer before its superclass." | Once initialization of a subclass begins, required superclasses must finish initializing first. |
| "All parent interfaces are always initialized before child interfaces." | Initializing an interface by itself does not implicitly initialize its superinterfaces; default-method superinterfaces matter when initializing a class. |
| "Each `new` runs the static block again." | Static initialization for a class definition succeeds only once; the constructor runs for each instance. |
| "A failed initializer is automatically retried on the next access." | The class definition enters the erroneous state; subsequent attempts typically throw `NoClassDefFoundError`. |
| "Every `static final` field is inlined." | Only a **constant variable** of a primitive/String type initialized with a constant expression qualifies; objects created with `new` do not fall into this category. |
| "Two loaders loading the same class name share static state." | Class identity is tied to its defining loader; each definition has its own static state and initialization status. |

## 11. Self-Check Questions

**1.** How do `Report.class.getName()` and `new Report()` differ with respect to initialization?

**Answer:** The class literal and reading the name do not by themselves require `Report` initialization; creating a `Report` instance with `new` is an operation that requires the class to be initialized before the instance is created.

**2.** Why does `Derived.count` only print `Base.init` in the `FieldOwnerDemo` example?

**Answer:** `count` is a static field declared in `Base`. After resolution, `getstatic` applies to the declaring class `Base`, and does not force initializing `Derived` merely because the source syntax uses the name `Derived`.

**3.** Do `static final Integer ANSWER = 42` and `static final int ANSWER = 42` behave the same when read through the class?

**Answer:** No. `Integer` is not a constant variable type under the JLS, so its initializer and the associated `getstatic` can require initialization. `int` with the constant expression `42` is a constant variable and can be inlined into the consuming class.

**4.** Why do both `Parent.first` and `Parent.BOXED` print before `Child.block` in `InitializationDemo`?

**Answer:** Because `Child` is a subclass, its initialization process requires the superclass `Parent` to complete first. Inside `Parent`, static field initializers and static blocks execute in source order.

**5.** If thread A is executing `<clinit>` of a class and thread B needs to call a static method of that class, can B run the method before initialization finishes?

**Answer:** No. The JVM coordinates initialization across threads; B waits for the successful state or receives an error. This does not mean that static initializers with cross-class lock dependencies can never deadlock.

**6.** Why does an error log show `NoClassDefFoundError` even though the `.class` file is still present?

**Answer:** One possibility is that an earlier initialization failed, marking the class erroneous, and the subsequent request threw `NoClassDefFoundError`. You should inspect the initial root exception along with its cause, while still checking other possibilities such as missing dependencies or classpath entries.

## Summary of the Reasoning Process

When you want to know "has this line caused `static` to run yet?", determine:

1. Is the bytecode executing **`new`**, **`getstatic`**, **`putstatic`**, **`invokestatic`**, or an equivalent operation via reflection/MethodHandle?
2. Which type **is actually referenced and declares the member** after resolution? Is it a compile-time constant that has already been inlined?
3. Has that type already completed initialization successfully? If not, the JVM must process its superclasses and any required superinterfaces with default methods before running `<clinit>` for the type itself.
4. If another thread is concurrently initializing it or an initializer failed, the operation in question will wait or receive an error depending on the class state.

Two authoritative references for checking edge cases and error conditions:

- [Java Language Specification 17 – 12.4 Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4).
- [Java Virtual Machine Specification 17 – 5.5 Initialization](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5).

Applying these rules accurately helps predict class loader and reflection side effects, structure lazy singletons safely, and pinpoint the root cause of static initialization errors at runtime.
