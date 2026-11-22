# Initialization Errors: `ExceptionInInitializerError` and the Erroneous Class State in the JVM

A Java class can **load successfully**, **link validly**, yet **fail during static initialization**. When the initialization work of a class or interface completes abnormally, the JVM records that runtime definition in an **erroneous state**. From this point on, subsequent initialization requests **do not automatically re-run the static initializer**. The result is often surprising: the first time you may see `ExceptionInInitializerError`, while on a subsequent use you receive `NoClassDefFoundError`.

These are not two interchangeable names for the same error. They reflect **two different points in time and two different runtime states**:

- **First time:** code inside or associated with class initialization throws an exception; if the initial throwable is **not an `Error`**, the JVM typically wraps it in an **`ExceptionInInitializerError`** and marks the class as erroneous.
- **Subsequent times:** the JVM sees that the class is already in the **erroneous state**, so it does not re-initialize it and throws **`NoClassDefFoundError`** according to the initialization rules.
- If the initial initialization work throws an **`Error`** object, the JVM may propagate that `Error` itself instead of wrapping it in `ExceptionInInitializerError`; the class still fails initialization and is marked erroneous.
- Specific error messages, `cause` chains, and stack traces may vary across JVMs/versions; when analyzing, you must preserve **the entire error chain from the first occurrence**, not just look at the final error.

This lesson explains the initialization lifecycle, error mechanism, triggering cases, how to reproduce it in Java 17+, common causes, and safe handling approaches.

## 1. Loading, linking, and initialization are distinct tasks

In the JVM, a class/interface goes through logical phases:

```text
Class definition requested by the JVM
             │
             ▼
        Loading
             │
             ▼
        Linking
   ┌─────────┼─────────┐
 Verification Preparation Resolution
             │
             ▼
    Initialization when needed
      (runs <clinit>
       according to rules)
             │
     ┌───────┴────────┐
     ▼                ▼
  Success          Failure
     │                │
 initialized        erroneous
     │                │
 continue using   no automatic retry
```

The diagram is intended to **distinguish responsibilities**, not to assert that the JVM must resolve the entire constant pool before running `<clinit>`. Some references may be resolved lazily on demand. Loading a class does not mean it has been initialized.

| Phase | Meaning | Does it automatically run the class's static initializer? |
| --- | --- | --- |
| Loading | Creates a runtime representation from the definition provided by a loader | Not synonymous |
| Verification | Verifies that the class file/bytecode satisfies JVM rules | No |
| Preparation | Prepares static fields, sets default values and `ConstantValue` entries according to rules | Does not run the entire static initializer |
| Resolution | Converts symbolic references into appropriate runtime links | Not by default |
| Initialization | Executes the required class/interface initialization work | **Yes**, if `<clinit>` code and other required steps exist |

In Java source:

```java
class Config {
    static int port = parsePort();

    static int parsePort() {
        return Integer.parseInt("not-a-number");
    }
}
```

This is an **illustrative class** that can compile, but static initialization will fail when an active use requires `Config` initialization. That does not mean the ClassFile is malformed or that the verifier rejects the bytecode.

## 2. Where is `<clinit>` generated from?

The name **`<clinit>`** is the special class/interface initialization method in the JVM model. For a class with static work to run, `javac` typically synthesizes `<clinit>:()V` from **static field initializers** and **static initializer blocks**, executing them in an order matching the source declarations.

Example:

```java
class ServerSettings {
    static int base = loadBase();

    static {
        base += 2;
    }

    static int loadBase() {
        return 8000;
    }
}
```

The corresponding `<clinit>` body might perform:

```text
base = loadBase();
base = base + 2;
return;
```

This is **pseudocode describing behavior**, not complete bytecode. When initialization succeeds, `ServerSettings.base == 8002`.

If `loadBase()` is replaced with a method that throws an exception, `<clinit>` may stop midway: fields initialized earlier may have already been written with values, while later static initializers **have not run**. However, after the failure, the class does not automatically return to an "uninitialized" state to execute again from the beginning.

### `<init>` is not `<clinit>`

- `<init>` is a constructor/instance initialization method, tied to **the creation of each individual object**.
- `<clinit>` is tied to **class/interface initialization**, typically only once per runtime definition if successful.
- `new Example()` may **trigger class initialization first**, and only then can the constructor body run. If class initialization fails, the constructor body **is never reached**.
- An exception thrown **inside the `<init>` constructor body** does not automatically turn the class erroneous. Another instance can still be created using that constructor after catching the exception, if logic allows.

This distinction is especially important when reading stack traces: `ExceptionInInitializerError` reflects a failure in **class initialization**, not every exception during `new` is a `<clinit>` failure.

## 3. When does the JVM require initialization?

Class initialization is typically triggered prior to **active uses**, which include:

1. `new T()` when `T` is not yet initialized.
2. Execution of `getstatic`/`putstatic` involving a static field **declared in the class/interface to be initialized**, according to the corresponding rules.
3. `invokestatic` to a static method of the type needing initialization.
4. Certain reflection operations, method handles, or bootstrap mechanisms that require initialization.
5. Before the main class starts executing according to JVM rules; and other cases specified by the JVMS.

Example:

```java
class LazyStore {
    static int value = init();

    static int init() {
        System.out.println("LazyStore initialized");
        return 5;
    }
}
```

A normal `System.out.println(LazyStore.value)` statement requires initialization before reading the result. However, **not every mention of a class name is an active use**.

### 3.1. Operations that do not automatically force `<clinit>` to run

```java
Class<?> clazz = LazyStore.class;
```

A class literal allows obtaining the `Class` object without automatically requiring `LazyStore` initialization. Similarly, creating a **reference array** `new LazyStore[3]` does not automatically create three `LazyStore` instances and does not automatically invoke the constructor or static initializer of the component class.

A useful reflection overload:

```java
Class.forName("LazyStore", false, someClassLoader);
```

With `initialize=false`, the API requests not to initialize the target class merely for this lookup. The snippet above **only illustrates the syntax** and requires an appropriate `someClassLoader` variable, code to handle `ClassNotFoundException`, and the exact binary name.

### 3.2. Compile-time constants differ from static values computed at runtime

```java
class Constants {
    static final int LIMIT = 100;
    static int runtimeValue = compute();

    static int compute() {
        System.out.println("Constants initializing");
        return 3;
    }
}
```

`Constants.LIMIT` is a constant variable that the compiler may **inline** into the caller, so merely using this constant does not automatically cause the class to be initialized. `Constants.runtimeValue` requires static initialization work, so normal access triggers it.

Do not equate every `static final` with a compile-time constant. For example, `static final Object HOLDER = new Object();` is not a compile-time constant; it requires executing object initialization.

**Practical consequence:** an application can use certain constants or Class literals normally even if a later active use of the class leads to an initialization error.

## 4. The four states the JVM uses when initializing a class/interface

*JVMS §5.5* describes the initialization mechanism using four logical states:

| State | Interpretation | When an initialization request occurs |
| --- | --- | --- |
| Verified/prepared, not yet initialized | Initialization work has not started | The JVM begins the procedure |
| Initializing by a specific thread | One thread has taken responsibility for initialization | Other threads wait; recursive requests by that same thread are handled specially |
| Fully initialized | Initialization has succeeded | Does not re-run `<clinit>`; proceeds |
| **Erroneous** | Previous initialization failed | **No retry**; the JVM throws `NoClassDefFoundError` |

The JVM maintains a separate **initialization lock** per runtime class/interface to coordinate concurrency. When one thread begins initialization, another thread requesting initialization of the same class will not automatically execute `<clinit>` in parallel. The JVM allows a case of a **recursive initialization request within the same initializing thread** to complete the repeated request without waiting on itself.

There is no standard public Java API to reset a `Class` object from `erroneous` back to `uninitialized`. This state is bound to **a runtime class definition**, not merely to a name string or a single object instance.

### 4.1. A class is identified by its defining loader

Two runtime classes with the same binary name but defined by two different **defining class loaders** are two distinct runtime types. Each definition has its **own initialization state**, its own static fields, and its own errors.

Therefore, the accurate statement is:

> If initialization of **a runtime class/interface** fails, subsequent initialization requests for **that same runtime type** do not automatically retry.

Creating a new class loader and loading **a new class definition** can have a fresh initialization state; that is not "resetting" the old definition. In typical applications, fixing the error usually requires deploying the appropriate binary or restarting the process/application according to the architecture in use, rather than attempting to manipulate JVM state via reflection.

## 5. `ExceptionInInitializerError`: the first-time initialization error

When the JVM executes class initialization, the work can fail due to:

- A static field initializer reading invalid configuration.
- A static block operating on a missing file, environment, or resource.
- `Integer.parseInt`, type casting, `null` dereference, or invalid indexing in static code.
- A dependency that is actively used during class initialization failing its own initialization.
- A loading/linking/permission error or runtime error occurring in the initialization chain.
- Cyclic dependencies or overly complex static logic leading to an exception.

Example:

```java
class Broken {
    static int threshold = parse();

    static int parse() {
        return Integer.parseInt("invalid");
    }
}
```

This is an **illustrative class**. The source compiles, but `new Broken()` the first time can cause:

```text
ExceptionInInitializerError
  caused by NumberFormatException
```

**Why wrap it?** When initialization fails due to a throwable **that is not an `Error`**, the JVM procedure attempts to create an `ExceptionInInitializerError` with the original cause, mark the class erroneous, and throw the appropriate error. The goal is to indicate that a **class initialization process** failed, not merely that the `parse()` method returned an exception.

### 5.1. Which group does `ExceptionInInitializerError` belong to?

```text
Throwable
└── Error
    └── LinkageError
        └── ExceptionInInitializerError
```

It is an **`Error`**, not an `Exception`. Therefore:

```java
try {
    new Broken();
} catch (Exception e) {
    // Cannot catch ExceptionInInitializerError
}
```

This is **illustrative code**, not a complete runnable class. `catch (Exception)` does not catch `Error` in general. When demonstrating a lab, you can catch the exact known `ExceptionInInitializerError` or `LinkageError` to inspect the cause. In production code, **you should not swallow initialization errors to continue using an erroneous class**.

### 5.2. Inspecting the root cause

`ExceptionInInitializerError` supports:

```java
Throwable original = error.getCause();
Throwable legacy = error.getException();
```

Where `error` is a variable of type `ExceptionInInitializerError` with an appropriate value. `getException()` is a historical API; `getCause()` is more familiar in error-chain analysis. You should preserve **the original message, original stack trace, and the first frame belonging to your own source**.

Note that the constructors/overloads of `ExceptionInInitializerError` include cases without an attached cause; do not assume `getCause()` is always non-`null` if the application or a library **manually constructs** an error instance. In situations where the VM automatically wraps an appropriate throwable, the cause is usually very helpful.

### 5.3. What if `<clinit>` throws an `Error`?

JVM rules distinguish a throwable that is a subtype of `Error` from a throwable that is not an `Error`. If initialization code throws an `AssertionError` or another `Error`, the JVM **is not required to wrap it in `ExceptionInInitializerError`**; the original error may be thrown directly. **The runtime class still enters the erroneous state** after abnormal completion.

Therefore, the statement "every static init failure is an `ExceptionInInitializerError`" is **false**. The lab section will verify both the wrapped-exception branch and the preserved-`Error` branch.

## 6. `NoClassDefFoundError` on subsequent uses: the class is already erroneous, not always a missing file

When a runtime class is already in the erroneous state, a subsequent initialization request does not re-run the entire static initializer and instead causes **`NoClassDefFoundError`**.

```text
First active use
  → starts <clinit>
  → IllegalStateException
  → JVM wraps in ExceptionInInitializerError
  → class is marked erroneous

Second active use of the same runtime class
  → checks state
  → erroneous
  → NoClassDefFoundError
  → DOES NOT re-run <clinit>
```

You should not read just the words "NoClassDefFound" and immediately conclude a JAR/file is missing. `NoClassDefFoundError` can appear for several different reasons, including:

1. The JVM needs to define a class but cannot obtain it during loading/linking.
2. A runtime class **previously failed initialization**.
3. A linkage/initialization error in a dependency prevents a related class from being used as expected.

In the case of an erroneous class, the message typically takes a form related to **"Could not initialize class ..."**; the exact message **is not stable across JVMs/versions**. Look for the **first** error in the logs, especially `ExceptionInInitializerError` and its cause.

### 6.1. Why does catching the first error and retrying not fix it?

A snippet like:

```java
for (int i = 0; i < 3; i++) {
    try {
        useBrokenClass();
    } catch (LinkageError e) {
        // Log the error, but does not "reset" the class
    }
}
```

is **Java-style pseudocode**: a `useBrokenClass()` method in an appropriate context is needed to compile. If on the first iteration the class becomes erroneous, subsequent iterations do not return to `<clinit>`. Using `Thread.sleep(...)`, retrying immediately, or calling `System.gc()` does not make the JVM clear the erroneous state.

The fix must address **the root cause and the deployment/runtime class lifecycle**.

## 7. Runnable Java 17+ Lab: observing both failure modes

Create a single file **`InitializerFailureDemo.java`**:

```java
public class InitializerFailureDemo {
    static class Broken {
        static int configuration = load();

        static int load() {
            System.out.println("Broken initializing");
            throw new IllegalStateException("bad configuration");
        }

        Broken() {
            System.out.println("Broken constructor");
        }
    }

    static class Fatal {
        static int flag = fail();

        static int fail() {
            System.out.println("Fatal initializing");
            throw new AssertionError("fatal problem");
        }

        Fatal() {
            System.out.println("Fatal constructor");
        }
    }

    static class Healthy {
        static int count = init();

        static int init() {
            System.out.println("Healthy initializing");
            return 12;
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("start");

        Class<?> mirror = Broken.class;
        System.out.println("literal: " + mirror.getSimpleName());
        Class.forName(mirror.getName(), false, mirror.getClassLoader());
        System.out.println("lookup without initialization");

        try {
            new Broken();
        } catch (ExceptionInInitializerError e) {
            System.out.println("broken first: "
                    + e.getClass().getSimpleName());
            System.out.println("broken cause: "
                    + e.getCause().getClass().getSimpleName());
        }

        try {
            new Broken();
        } catch (NoClassDefFoundError e) {
            System.out.println("broken second: "
                    + e.getClass().getSimpleName());
        }

        try {
            new Fatal();
        } catch (AssertionError e) {
            System.out.println("fatal first: "
                    + e.getClass().getSimpleName());
        }

        try {
            new Fatal();
        } catch (NoClassDefFoundError e) {
            System.out.println("fatal second: "
                    + e.getClass().getSimpleName());
        }

        System.out.println("healthy first: " + Healthy.count);
        System.out.println("healthy second: " + Healthy.count);
        System.out.println("end");
    }
}
```

Run with JDK 17 or newer in the directory containing the file:

```bash
javac -encoding UTF-8 InitializerFailureDemo.java
java InitializerFailureDemo
```

**Exact standard output:**

```text
start
literal: Broken
lookup without initialization
Broken initializing
broken first: ExceptionInInitializerError
broken cause: IllegalStateException
broken second: NoClassDefFoundError
Fatal initializing
fatal first: AssertionError
fatal second: NoClassDefFoundError
Healthy initializing
healthy first: 12
healthy second: 12
end
```

### 7.1. Why does the output appear in this order?

1. `Broken.class` creates/obtains the `Class` mirror **without forcing `Broken` to initialize**; hence there is no `Broken initializing` line yet.
2. `Class.forName(name, false, loader)` also does not require initialization; it prints `lookup without initialization` as normal.
3. The first `new Broken()` requires class initialization, calling `Broken.load()` from static code. The method prints `Broken initializing` and then throws `IllegalStateException`.
4. The initial throwable is **not an `Error`**, so the JVM wraps it in `ExceptionInInitializerError`; the printed cause is `IllegalStateException`. The constructor body is never executed, so **there is no** `Broken constructor`.
5. The second `new Broken()` encounters the same **erroneous** runtime class, throws `NoClassDefFoundError`, and **does not print** `Broken initializing` again.
6. The first `new Fatal()` goes through static initialization and `Fatal.fail()` throws **`AssertionError`**. The JVM propagates this `Error` along the corresponding branch, so the first line prints `AssertionError` instead of `ExceptionInInitializerError`.
7. `Fatal` is still erroneous. The second attempt throws `NoClassDefFoundError`, and the constructor body is never executed either.
8. `Healthy.count` being used for the first time causes initialization to succeed, printing `Healthy initializing` once; the second read does not re-run the initializer.

The program intentionally catches the exact `Error` types to observe and prints the class name of the error instead of `getMessage()`; this keeps stdout stable against differences in stack traces/messages across JVMs. **In production, avoid catching linkage/initialization errors and treating the system as recovered.**

### 7.2. Inspecting the ClassFile yourself with `javap`

```bash
javap -c -p 'InitializerFailureDemo$Broken'
javap -c -p 'InitializerFailureDemo$Fatal'
javap -c -p 'InitializerFailureDemo$Healthy'
javap -c -p InitializerFailureDemo
```

Single quotes protect the `$` character of nested classes in Bash or PowerShell; in Windows `cmd.exe` you can use double quotes.

In the output for class `Broken`, look for the **`static {}`** section that `javap` displays for `<clinit>`:

```text
invokestatic ... load:()I
putstatic    ... configuration:I
return
```

This is a **sample instruction description**, not a listing with fixed offsets/constant-pool indexes. Because `load()` throws an exception, `putstatic` and `return` along the normal flow are not reached during the failing run. The JVM marks the class erroneous.

In the `main` method, observe the `new` instructions and the catch branches in the exception table. **There is no opcode named `retry_clinit`** automatically added by `javac` after catching the error.

## 8. Comparison: a constructor exception does not make a class erroneous

A class can initialize successfully while **an instance's constructor body** throws an exception. For instance:

```java
class ConstructorFails {
    static {
        System.out.println("Class initialized");
    }

    ConstructorFails() {
        throw new IllegalArgumentException("bad instance");
    }
}
```

This is an **illustrative class**, not a program with `main`. If the caller catches `IllegalArgumentException` when executing `new ConstructorFails()`, and then calls `new ConstructorFails()` again, the class remains successfully initialized; the constructor may throw an exception again. There is no class-erroneous rule merely because an instance's constructor failed.

Similarly, a **normal static method**, called **after the class has initialized successfully**, can throw `IllegalStateException` without causing the class to be marked erroneous. Class initialization is treated as a **distinct phase**, not just any code running "in a class".

### Comparison table of the three scenarios

| Where the exception occurs | Has class initialization succeeded? | Typical consequence |
| --- | --- | --- |
| Inside `<clinit>` or the initialization work chain | **No** | Initial throwable/error per JVM rules, class may enter erroneous state |
| Inside constructor `<init>` after class initialization | **Yes** | Object creation fails; class remains usable, subsequent constructors can still be attempted |
| Inside a normal static method after initialization | **Yes** | Method invocation fails; class does not become erroneous solely due to this exception |

**Caution:** if a static method is **called by `<clinit>`**, an exception escaping from that method will cause the class initialization work to fail. The same method might not make the class erroneous when called at another time, but when it is a link in an incomplete `<clinit>`, the consequence is different.

## 9. Errors when initializing a superclass or dependency

When the JVM initializes a subclass, the relevant superclass must be initialized in the prescribed order. If **superclass initialization** fails, the subclass cannot proceed with normal initialization.

```text
Active use of Child
       │
       ▼
Initialize Parent
       │
       ▼
Parent <clinit> fails
       │
       ├── Parent becomes erroneous
       │
       ▼
Child initialization cannot proceed
       │
       └── Child also cannot be used normally
```

In this kind of dependency, an error seen at the call site creating **Child** may have its root cause in the static initializer of **Parent** or an interface required to be initialized per JVM rules. Inspect the **cause chain** and the actual initialization frames, not just the class name mentioned on the top line of the `new Child()` call.

### Static dependencies can propagate errors

```java
class DatabaseConfig {
    static final String URL = loadUrl();

    static String loadUrl() {
        throw new IllegalStateException("missing URL");
    }
}

class Repository {
    static String connectionUrl = DatabaseConfig.URL;
}
```

These are two illustrative classes. When `Repository` initialization needs to read `DatabaseConfig.URL`, the JVM may have to initialize `DatabaseConfig`. If the dependency class fails, `Repository`'s initialization path cannot complete normally either.

**Do not assume that the original exception is always wrapped in an additional layer of `ExceptionInInitializerError` for every dependency.** The JVM has specific rules for `Error` and runtime state; the shape of the cause chain must be observed from the actual error.

### Static initialization and class loaders

If an application has multiple class loaders, a failure in the `Repository` definition belonging to loader A does not by default cause a class with the same binary name **independently defined by loader B** to become erroneous. Even with the same source bytes, these are two different runtime classes. However, this independence **is not an arbitrary recovery mechanism**: in practice there are still resource leaks, class loader constraints, and shared dependencies.

## 10. Concurrency: why doesn't the JVM let two threads "fix the error by trying in parallel"?

The JVM provides an **initialization lock** mechanism for each runtime class/interface:

1. The first thread needing to initialize the class takes responsibility and begins the procedure.
2. If another thread needs initialization of the same class while this is in progress, it waits for the resulting state according to JVM rules.
3. If initialization completes successfully, threads proceed to use the initialized class.
4. If initialization fails, the class transitions to erroneous; subsequent requests **are not allowed to re-run `<clinit>` concurrently or sequentially**.
5. If the initializing thread itself requests recursive initialization of that class, the JVM has special handling rules so it does not block itself.

It follows that: **launching 10 additional threads to initialize the same class does not produce 10 valid retries**. Some threads may see different error types because the timing at which they touch the class state differs; do not predict console output ordering in multithreaded examples without explicit synchronization.

### Warning about circular initialization

Static dependency cycles are a risky area:

- **Same thread:** a recursive initialization request for a class currently initializing may be permitted by the JVM per rules, causing code to read **default values** or partially assigned static values; it does not necessarily throw an exception.
- **Different threads:** class initialization locks and cross-dependencies can create mutual waiting situations, or even deadlocks if carelessly designed.
- **Incomplete state:** static fields assigned before the failure do not turn an erroneous class into a safe API; avoid trying to exploit intermediate state.

A minimal static initialization design with few side effects is generally safer than initialization that makes network calls, acquires external locks, awaits asynchronous tasks, or uses circularly dependent registries.

## 11. A static field can be read while still at its default value

An internal reference cycle **does not necessarily cause an initialization error**; it can produce unexpected results:

Create the file **`PartialInitializationDemo.java`**:

```java
public class PartialInitializationDemo {
    static class Order {
        static int early = readLater();
        static int later = 7;

        static int readLater() {
            return later;
        }
    }

    public static void main(String[] args) {
        System.out.println("early: " + Order.early);
        System.out.println("later: " + Order.later);
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 PartialInitializationDemo.java
java PartialInitializationDemo
```

**Standard output:**

```text
early: 0
later: 7
```

Explanation:

- **Preparation** provides the default value `0` for static `int` fields per the JVM model.
- When `Order.<clinit>` processes `early = readLater()`, the `later` field has not yet been assigned `7` from the initializer located **after** it.
- `readLater()` therefore reads the current value `0`.
- Afterward `later = 7` runs, but `early` is not automatically recomputed.
- Class initialization completes successfully: **there is no `ExceptionInInitializerError`**.

**Do not misunderstand that any static field can be read anywhere before its declaration:** Java source has rules regarding **illegal forward references**; in the example, reading via the `readLater()` method is legal. An initialization cycle does not only have the two outcomes "succeeds properly" or "throws an error": **succeeding with unexpected state** is also worth noting.

## 12. Diagnosing `ExceptionInInitializerError` and `NoClassDefFoundError`

When receiving an error report, proceed sequentially:

### Step 1 — Find the first failure

Prioritize the first log entry containing the class name in the initialization chain, which might look like:

```text
ExceptionInInitializerError
Caused by: IllegalStateException: bad configuration
...
```

This is an **illustrative structural excerpt**, not a full stack trace from a specific JVM. If you only see `NoClassDefFoundError: Could not initialize class ...`, search **earlier in the logs within the same process and class loader**.

### Step 2 — Inspect the cause and which static initializer ran

Look for `<clinit>` or methods called by the static initializer: `loadConfig`, `registerDriver`, `connect`, `parse`, `initializeCache`, etc. These methods are examples of functionality that can fail, not a list of methods the JVM calls automatically.

### Step 3 — Distinguish error paths

| Symptom | Diagnostic question |
| --- | --- |
| `ClassNotFoundException` from `Class.forName` | Are the name, loader, module path, and classpath correct? |
| `NoClassDefFoundError` when loading a dependency | Is a class file/dependency missing, or is a binary version incompatible? |
| `NoClassDefFoundError` after a static init failure | Was there an earlier `ExceptionInInitializerError` or initial `Error`? |
| `ExceptionInInitializerError` | What is the **root** throwable in the cause, and which initializer did it originate from? |
| `NoSuchMethodError` or `IllegalAccessError` | Is this a dependency linkage error along the initialization path? |
| `OutOfMemoryError` or `StackOverflowError` | Did the resource/recursion error occur during initialization or in later code? |

**Not every `NoClassDefFoundError` is caused by failed initialization**. Use the full context rather than inferring from the exception name alone.

### Step 4 — Verify the files/classes actually running

```bash
java --version
javac --version
javap -c -p 'InitializerFailureDemo$Broken'
```

For large projects, verify the runtime version of JARs/dependencies, classpath/module path, class loaders, environment variables, and configurations read inside the static initializer. `javap` helps check whether there is a `static {}` corresponding to `<clinit>` and what the bytecode order is; it does not run class initialization itself.

### Step 5 — Fix the cause and restart/re-initialize by design

Once a runtime class is erroneous, simply fixing an external configuration variable and continuing to access the same class **does not make the JVM automatically re-run `<clinit>`**. Usually you need to restart the process/application or use a controlled reload mechanism that creates a **new runtime class definition** after the root cause is fixed.

Do not use `System.gc()`, `Thread.sleep()`, changing file permissions mid-flight, or looping `Class.forName(name, true, sameLoader)` as a way to "clear the erroneous state".

## 13. Reducing risk through design and proper error handling

### 13.1. Keep static initialization minimal

Prefer static initialization of pure, immutable, deterministically computed data; limit performing operations that can fail due to the environment:

```java
class SafeConstants {
    static final int MAX_RETRIES = 3;
    static final String PREFIX = "app";
}
```

For work that can fail (reading config files, network access, opening connections), consider **explicit initialization in the application lifecycle**, returning clear errors to the caller, allowing controlled retries, and not tying retries to `<clinit>` of a broken class.

### 13.2. Separate dynamically initialized resources from static initializers

This snippet **illustrates design**, and is not a standalone runnable program:

```java
final class ConnectionManager {
    private ConnectionManager() {}

    static Connection open(String endpoint) {
        return connectWithTimeout(endpoint);
    }
}
```

Here `Connection` and `connectWithTimeout` are **application-dependent symbols** not defined in the example, merely illustrating moving error-prone operations out of `<clinit>`. In a real application, you must provide concrete types/APIs, close resources properly, and decide retry/backoff based on business requirements.

### 13.3. Initialization-on-demand holder can still fail

Holder pattern:

```java
class ServiceHolder {
    static class Holder {
        static final Service INSTANCE = createService();
    }

    static Service get() {
        return Holder.INSTANCE;
    }
}
```

This is **Java pseudocode requiring additional declarations of `Service` and `createService()`**. The holder defers initialization until active use, but **does not automatically provide retry capability if `Holder.<clinit>` fails**. After a failure, `Holder` can also become erroneous. Therefore, the holder is suitable for singletons with reliable initialization, not as a recovery mechanism for unstable connections.

### 13.4. Do not blindly swallow `Error`

`LinkageError`, `ExceptionInInitializerError`, and `OutOfMemoryError` carry serious meaning. Some labs catch them to inspect behavior, but in production, using `catch (Throwable)` just to "keep the application alive" can hide an untrustworthy runtime state.

If a handling boundary is needed in a container/test runner, log thoroughly, mark the application unhealthy, and decide on appropriate isolation/restart instead of continuing to call into an erroneous class.

### 13.5. Avoid circular-dependency static initialization

A design with:

```text
ServiceA.<clinit>
    ↳ ServiceB.staticMethod()
         ↳ ServiceC.INSTANCE
              ↳ ServiceA.otherStaticField
```

can lead to reading partial state, exceptions, or cross-waiting. This is a **dependency diagram**, not an order that always causes errors. Decouple the dependency graph, use runtime dependency injection, establish a clear initialization order, and avoid prolonged locking/I/O waiting inside static initializers.

## 14. Quick check of common misconceptions

| Statement | True or false? | Explanation |
| --- | --- | --- |
| "Reading `SomeClass.class` always executes `<clinit>`." | **False** | A class literal does not automatically trigger class initialization |
| "If a static initializer fails the first time, `NoClassDefFoundError` definitely appears immediately." | **False** | The first time is usually `ExceptionInInitializerError` or the original `Error`; subsequent times encounter the erroneous state |
| "`ExceptionInInitializerError` is an `Exception`." | **False** | It is an `Error`, under `LinkageError` |
| "Every Throwable from `<clinit>` is wrapped in a layer of `ExceptionInInitializerError`." | **False** | Throwables that are `Error`s may be preserved as-is |
| "Next time, just calling `new` on the class again makes the JVM re-run the static block." | **False** | The erroneous state does not automatically reset |
| "Every `NoClassDefFoundError` is due to a missing JAR." | **False** | It can be due to a previous class initialization failure |
| "A constructor `<init>` throwing an exception makes the class erroneous." | **False**, if `<clinit>` has already succeeded | An instance constructor failure differs from a runtime class initialization failure |
| "Using a new class loader can create a different runtime type even with the same name." | **True** | Class identity is tied to the defining loader |
| "If one thread fails in `<clinit>`, another thread automatically re-initializes the same class." | **False** | The JVM uses an initialization lock/state; an erroneous class is not retried |
| "Static initialization can read fields still at their default value." | **True** | When code uses certain initialization/recursion orders, partial state can be observed |

## 15. Practice exercises and self-check questions

**1. On the first use, an `IllegalArgumentException` is thrown in a static initializer; what does the caller see?**  
**Answer:** The JVM typically wraps it in **`ExceptionInInitializerError`** because `IllegalArgumentException` is not an `Error`. The runtime class becomes erroneous when initialization fails.

**2. After catching the error above, will calling `new` again on the same runtime class re-initialize it?**  
**Answer:** No. The JVM detects the erroneous state and throws **`NoClassDefFoundError`** according to the initialization rules.

**3. What if `<clinit>` throws `AssertionError` directly?**  
**Answer:** The JVM does not need to wrap that Error in `ExceptionInInitializerError`; the first time may show `AssertionError`, and subsequent uses of the erroneous class encounter `NoClassDefFoundError`.

**4. Why does `new Demo[5]` not run `Demo`'s static block?**  
**Answer:** It creates **an array object of type `Demo[]`** with five default `null` references, does not create five `Demo` instances, and does not automatically trigger class initialization of the component type.

**5. Does `static final int MAX = 8;` force the static block to run when a caller reads `MAX`?**  
**Answer:** No, when it is a compile-time constant variable inlined according to Java rules. Accessing a non-constant static field is a different case.

**6. What is the difference between `Class.forName(name, false, loader)` and `Class.forName(name, true, loader)` regarding initialization?**  
**Answer:** The overload with `false` does not request initialization; with `true` it requests initializing the class if appropriate and not yet initialized. If the class is erroneous, an initialization request for the same runtime definition will not succeed.

**7. `new Demo()` throws `IllegalStateException` from the constructor body after the static initializer succeeds; is `Demo` erroneous?**  
**Answer:** Not solely because of the constructor failure. The runtime class may already be initialized; subsequent object creations can still invoke that constructor.

**8. Can you fix the configuration and call `Class.forName(name, true, sameLoader)` to retry `<clinit>` of an erroneous class?**  
**Answer:** No. The JVM does not reset the erroneous state for the same runtime class simply through a subsequent reflection call.

**9. Why does the first `new Child()` report an error from `Parent`?**  
**Answer:** The JVM initializes required superclasses before the subclass. If `Parent` static initialization fails, `Child` cannot complete normal initialization.

**10. If two class loaders independently define the same binary name, does an init failure in loader A make the class in loader B erroneous?**  
**Answer:** Not by default. Two defining loaders create two different runtime classes, with separate initialization states; however, shared resources/dependencies can still cause errors when loader B initializes on its own.

**11. Why is `NoClassDefFoundError` at the end of a log alone not enough to conclude the cause?**  
**Answer:** It can arise from a missing class during loading/linking or from a runtime class already being erroneous. You need the **first** error, the cause chain, the class name, and the loader.

**12. Can the JVM let a static initializer run simultaneously in two threads on the same runtime class to speed things up?**  
**Answer:** Not in the sense of executing two separate initializations of the same runtime class. The JVM coordinates initialization using a lock/state; other threads must abide by the state of the class currently initializing.

## 16. Summary and official references

Treat initialization errors as **a state transition**, not just a caught exception:

```text
not initialized
       │ active use
       ▼
  initializing
       │
       ├── success ─────► initialized ──► continue using
       │
       └── failure ─────► erroneous
                            │
                       subsequent active use
                            │
                            ▼
                    NoClassDefFoundError
```

- **`ExceptionInInitializerError`** is usually the surface of an **initial failed initialization** caused by a non-`Error` exception.
- **`NoClassDefFoundError`** on subsequent attempts can be a **consequence of an erroneous class**, not proof of a missing file.
- An **original `Error`** in `<clinit>` may be propagated by the JVM instead of being wrapped.
- **Constructor failure ≠ class initialization failure**.
- **Runtime class identity** consists of the name and defining class loader; the same erroneous definition **cannot automatically retry**.
- You must address the **initial root cause** and design static initialization safely, rather than trying to make the JVM re-invoke `<clinit>`.

Official references for verification:

- *The Java Virtual Machine Specification*, section **§5.5 Initialization**, especially the initialization state algorithm, errors, and transition to erroneous: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5
- *The Java Language Specification*, **§12.4 Initialization of Classes and Interfaces**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4
- Java API **`ExceptionInInitializerError`** and **`NoClassDefFoundError`** in `java.lang`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ExceptionInInitializerError.html and https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoClassDefFoundError.html

**Practical conclusion:** when a program encounters `NoClassDefFoundError: Could not initialize class ...`, look for **the first time the class failed initialization**. The cause of `ExceptionInInitializerError` or the original `Error` usually points to the real failure. Once erroneous, retrying within the same runtime class will not cure the cause — you must fix the data/dependencies/design and initialize an appropriate runtime definition through a valid application lifecycle.