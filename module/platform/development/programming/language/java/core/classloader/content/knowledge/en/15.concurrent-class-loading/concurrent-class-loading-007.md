# Distinguishing the Class-Loading Lock from the Class-Initialization Lock in Java

When multiple threads concurrently use a class, Java needs to handle two different problems: **preventing two threads from defining the same class twice in the same class loader**, and **preventing multiple threads from executing the static initializer of the same runtime class independently**. These two problems are solved by the **class-loading lock** and the **class-initialization lock mechanism** — they are related to the class lifecycle, but they are **not the same lock**.

- **Class-loading lock** belongs to the `java.lang.ClassLoader` mechanism and is typically obtained via `getClassLoadingLock(String name)` in `loadClass`. It coordinates `findLoadedClass`, parent delegation, and `findClass/defineClass`, especially when multiple threads request the same binary name.
- **Class-initialization lock `LC`** is described by the Java Language Specification §12.4.2 as an internal lock **per runtime class or interface `C`**. The JVM uses it to coordinate the `not initialized / initializing / initialized / erroneous` states and the execution of `<clinit>`. There is no public API for applications to obtain `LC` as a `java.util.concurrent.locks.Lock`.

**Key takeaway:** Standard `ClassLoader.loadClass(...)` **does not require static initialization**; `Class.forName(name, true, loader)`, calling a static method, or creating an instance can require initialization. Registering a loader as **parallel-capable** helps load *different class names* in parallel, but it does not cause **`<clinit>` of the same runtime class** to run twice.

This lesson belongs to **Java core – classloader / Concurrent Class Loading**, using compilable/runnable Java 17+ examples, a comparison table, the JVM state model, and common deadlock/initialization-failure scenarios.

## 1. Two Types of Locks Protecting Two Different Invariants

| Perspective | Class-Loading Lock | Class-Initialization Lock |
| --- | --- | --- |
| Goal | Prevent duplicate lookup/definition races within a loader | Coordinate exactly one initialization process per runtime class/interface |
| Scope | Class loader instance; the lock may be shared across all names or separate per binary name | A runtime `Class<?>`/interface `C` and its JVM-managed initialization state |
| API/Specification | `ClassLoader.getClassLoadingLock` and `loadClass` | JLS §12.4.2 with lock `LC` |
| When used | On the loader's loading/delegation path | When active use needs to initialize an uninitialized class |
| Affected by parallel-capable loader? | Yes: typically has per-class-name locks | No: the JVM still preserves initialization semantics |
| Does it guard every line of `static { ... }`? | No | The lock is used for state coordination; it is not necessarily held throughout the `<clinit>` body |
| Typical errors | `ClassNotFoundException`, `LinkageError` during lookup/definition/linking | `ExceptionInInitializerError`, erroneous class, subsequent active use produces `NoClassDefFoundError` |
| Who controls it? | Loader subclass authors can influence lock acquisition when overriding `loadClass` | The JVM, per JLS/JVMS; applications cannot replace it directly |

**Do not confuse the class-loading lock with the monitor of the `Class<?>` object.** `synchronized (SomeClass.class)` locks a monitor visible to Java code; the specification does not guarantee that this object monitor is the internal `LC` across all JVMs/optimizations.

### A Timeline with Two Mechanisms

```text
T1 needs demo.Widget
  │
  ├── Loading: loader.lookup / defineClass
  │       └── class-loading lock coordinates when multiple threads load concurrently
  │
  ├── Linking: verification / preparation / resolution
  │
  └── Active use: demo.Widget.perform()
          └── JVM checks Widget initialization state
                ├── another thread is initializing → wait
                ├── not yet initialized → this thread runs <clinit>
                └── already initialized → use normally
```

The JVM steps may interleave or defer some resolution; the diagram emphasizes **purpose and boundaries**, rather than imposing a rigid lock-holding order across all JVMs.

## 2. Recap of Loading, Linking, Initialization, and Constructors

**Loading:** identifies the class by **binary name and defining loader**, reads/defines bytecode if needed, and obtains a `Class<?>` object. For the same binary name in the same defining loader, the JVM does not allow a valid `defineClass` to happen a second time as a new class.

**Linking:** verification, preparation, and resolution according to the JVM specification. Preparation prepares static fields with default values and dedicated mechanisms for constant values. Linking does not mean the `static { ... }` body has run.

**Initialization:** executes static field initializers and static initializer blocks (the class initialization method `<clinit>` when required by the compiler/JVM) according to Java rules. Only one successful initialization process occurs per runtime class.

**Instantiation:** creates an instance using `new` or a reflective constructor. An instance constructor (`<init>`) is not `<clinit>`. Once a class is initialized, many instances can be created concurrently; `LC` does not serialize subsequent constructors.

Example:

```java
ClassLoader loader = Example.class.getClassLoader();
Class<?> type = loader.loadClass("demo.Widget");
Class<?> noInit = Class.forName("demo.Widget", false, loader);
Class<?> initialized = Class.forName("demo.Widget", true, loader);
```

This is an **illustrative snippet** that requires the `Example` class, `demo.Widget`, and handling `ClassNotFoundException`. The first two calls **do not require the static initializer to run**; the final call with `initialize=true` requires initialization before returning successfully. All three return `Class<?>`, without creating an instance of `Widget` on their own.

## 3. Which Phase Does the Class-Loading Lock Protect?
In the default implementation, `ClassLoader.loadClass(name, resolve)` holds `getClassLoadingLock(name)` while checking `findLoadedClass`, delegating to the parent/bootstrap loader, calling `findClass` if needed, and calling `resolveClass` when requested. This path ensures the loader does not redundantly define the same name itself under concurrent requests.
**`loadClass` does not by itself require running `<clinit>`**. If the JVM later needs to initialize the runtime class, it uses the separate `LC` procedure and state as in §7. Diagnostics must separate loading/linking errors from initialization errors.

## 4. Parallel-Capable Only Changes the Loader's Lock
An unregistered loader uses the `this` monitor for all names; a parallel-capable registered loader uses a separate lock per name. This allows multiple names to be loaded concurrently without changing the initialization state per runtime `Class<?>`. `registerAsParallelCapable` must be called from the subclass's static initializer when all superclass loaders are already registered. Experiment A verifies the lock object, while B proves that the same name is defined once.

## 5. Lab A — Inspecting the Class-Loading Lock Object

Structure:

```text
lock-scope-lab/
└── src/demo/LockScopeDemo.java
```

**`src/demo/LockScopeDemo.java`:**

```java
package demo;

public final class LockScopeDemo {
    static final class SerialLoader extends ClassLoader {
        SerialLoader() {
            super(ClassLoader.getPlatformClassLoader());
        }

        boolean same(String a, String b) {
            return getClassLoadingLock(a) == getClassLoadingLock(b);
        }

        boolean lockIsLoader(String name) {
            return getClassLoadingLock(name) == this;
        }
    }

    static final class ParallelLoader extends ClassLoader {
        static {
            if (!registerAsParallelCapable()) {
                throw new ExceptionInInitializerError(
                        "Parallel registration failed");
            }
        }

        ParallelLoader() {
            super(ClassLoader.getPlatformClassLoader());
        }

        boolean same(String a, String b) {
            return getClassLoadingLock(a) == getClassLoadingLock(b);
        }
    }

    public static void main(String[] args) {
        SerialLoader serial = new SerialLoader();
        ParallelLoader parallel = new ParallelLoader();

        System.out.println("serial same A/B: " +
                serial.same("demo.A", "demo.B"));
        System.out.println("serial lock is loader: " +
                serial.lockIsLoader("demo.A"));
        System.out.println("parallel different A/B: " +
                !parallel.same("demo.A", "demo.B"));
        System.out.println("parallel same A/A: " +
                parallel.same("demo.A", "demo.A"));
    }
}
```

Run on **JDK 17+** from `lock-scope-lab`:

```sh
javac --release 17 -d out src/demo/LockScopeDemo.java
java -cp out demo.LockScopeDemo
```

**Expected stdout:**

```text
serial same A/B: true
serial lock is loader: true
parallel different A/B: true
parallel same A/A: true
```

Analysis:

1. `SerialLoader` is not registered, so all names use the same lock, which is the **`serial` instance**.
2. `ParallelLoader` registers in its static initializer before any instance is created; locks for two different names can be different.
3. The same name on the same parallel-capable loader consistently returns its corresponding lock.
4. The program only queries the lock object and compares identity; it **does not** load `demo.A`, `demo.B`, or run their static initializers.
5. `getClassLoadingLock` is a `protected` API for loader implementers; applications have no way to use it to obtain the JVM's `LC`.

**Do not infer:** that registering as parallel-capable forces the JVM to run static blocks concurrently. It only affects synchronization within the loader's class-loading operations.

## 6. Lab B — Two Threads Load the Same Class Concurrently, Only One Definition Succeeds

We create a custom loader whose `findClass` reads bytes from an output directory not on the application classpath. Two threads call `loadClass("payload.Target")` concurrently after a latch.

File tree:

```text
load-once-lab/
├── src/payload/Target.java
└── src/demo/LoadOnceDemo.java
```

**`src/payload/Target.java`:**

```java
package payload;

public final class Target {
    public static String message() {
        return "payload";
    }
}
```

**`src/demo/LoadOnceDemo.java`:**

```java
package demo;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public final class LoadOnceDemo {
    static final class CountingLoader extends ClassLoader {
        final AtomicInteger findCalls = new AtomicInteger();

        CountingLoader() {
            super(ClassLoader.getPlatformClassLoader());
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            if (!name.equals("payload.Target")) {
                throw new ClassNotFoundException(name);
            }

            try {
                byte[] bytes = Files.readAllBytes(
                        Path.of("payload-out", "payload", "Target.class"));
                findCalls.incrementAndGet();
                return defineClass(name, bytes, 0, bytes.length);
            } catch (IOException e) {
                throw new ClassNotFoundException(name, e);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        CountingLoader loader = new CountingLoader();
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch go = new CountDownLatch(1);

        Callable<Class<?>> task = () -> {
            go.await();
            return loader.loadClass("payload.Target");
        };

        try {
            Future<Class<?>> first = pool.submit(task);
            Future<Class<?>> second = pool.submit(task);
            go.countDown();

            Class<?> a = first.get();
            Class<?> b = second.get();

            System.out.println("same Class: " + (a == b));
            System.out.println("defined by child: " +
                    (a.getClassLoader() == loader));
            System.out.println("findClass calls: " +
                    loader.findCalls.get());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

**Compile** from the `load-once-lab` directory:

```sh
javac --release 17 -d payload-out src/payload/Target.java
javac --release 17 -d app-out src/demo/LoadOnceDemo.java
```

**Run** (put only `app-out` on the classpath, do not add `payload-out`):

```sh
java -cp app-out demo.LoadOnceDemo
```

**Stdout:**

```text
same Class: true
defined by child: true
findClass calls: 1
```

Why?

- The parent is the platform loader, so it cannot see `payload.Target` in the separate `payload-out` directory.
- Both tasks are started from the same latch and request the same loader instance to load the exact same binary name.
- `CountingLoader` is not registered as parallel-capable, so the default `loadClass` path locks on the loader.
- One thread reads the bytes and calls `defineClass`. The other thread receives the already-recorded class via `findLoadedClass`, without defining it twice.
- `findClass calls: 1` occurs because the first definition succeeds. If the class is always absent, multiple failed lookups **can call `findClass` multiple times**.
- The program does not call `Target.message()`; there is no reason to treat the result as evidence that the static initializer ran.

**Environment note:** all commands are run from the project root because `Path.of("payload-out",...)` is relative to the working directory. On Windows and Linux/macOS, the `java -cp app-out` command is the same when there is only one entry.

## 7. The `LC` Lock and JVM Initialization States

JLS §12.4.2 specifies a procedure for each runtime class/interface `C`, along with an initialization lock `LC`. Its goal is to ensure:

1. If `C` **is already initialized**, active uses do not run `<clinit>` again.
2. If `C` **is not yet initialized and no thread is currently initializing it**, one thread is recorded as the thread performing initialization.
3. If **the initializing thread itself** recursively requests initialization of `C`, the algorithm recognizes same-thread recursion and does not wait for itself.
4. If **another thread** requests initialization while `C` is initializing, that thread **waits** for the appropriate outcome instead of executing the `<clinit>` body in parallel.
5. If initialization completes successfully, the state transitions to **initialized** and waiting threads are allowed to proceed appropriately.
6. If initialization fails, the class becomes **erroneous**; subsequent active uses on the same runtime class do not automatically re-run the initializer.

Model:

```text
C is loaded and prepared
          │
          ▼
   not initialized
          │
          ▼
 initializing by thread T
    ┌──────┴────────┐
    │               │
 succeeds         fails
    │               │
    ▼               ▼
 initialized      erroneous
    │               │
subsequent       subsequent active use
active use:      may throw
normal           NoClassDefFoundError
```

**Subtle but important:** `LC` is used to check/update state and coordinate waiting; **the JLS does not require holding the `LC` monitor throughout every line of user code in a static initializer**. A JVM implementation is allowed to optimize synchronization as long as the corresponding semantics and happens-before guarantees are preserved.

Therefore, an application's `synchronized (C.class)` **must not be treated as a public interface for acquiring `LC`**. If you need to synchronize mutable application state, use the application's own `synchronized`/`Lock`/atomics.

## 8. When Is Class Initialization Required?

The following operations are typically active uses:

- `new C()`: creating an instance of class `C`.
- `C.staticMethod()`: invoking a static method declared by `C`.
- Reading/writing a static field of `C` in the cases specified by the JLS; **reading a constant variable** may be inlined and does not force initialization.
- `Class.forName("pkg.C", true, loader)`: requires initialization.
- Certain specified reflection operations and JVM bootstrap behaviors.

Operations that **do not by themselves require initialization** of the target in the usual way:

- `loader.loadClass("pkg.C")`.
- `Class.forName("pkg.C", false, loader)`.
- `C.class` or certain metadata accesses.
- Merely having the class name in the constant pool without an active use.

In a class hierarchy, initialization of the superclass and relevant superinterfaces follows its own ordering rules. Do not assume that every implemented interface is guaranteed to be initialized simply because the class is initialized.

**Do not confuse static constructors with instance constructors:** `<clinit>` refers to class/interface initialization; `<init>` refers to constructors executed when creating each instance. The `LC` lock does not by itself serialize all `new C()` calls after the class is initialized.

## 9. Lab C — Two Tasks Call a Static Method, but `<clinit>` Runs Only Once

This exercise uses latches to observe initialization in progress. We intentionally make the static initializer **wait for the main thread** before finishing; another worker also prepares to call the static method.

File **`src/demo/InitializationDemo.java`:**

```java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public final class InitializationDemo {
    private static final CountDownLatch INIT_ENTERED =
            new CountDownLatch(1);
    private static final CountDownLatch LET_FINISH =
            new CountDownLatch(1);
    private static final CountDownLatch SECOND_READY =
            new CountDownLatch(1);
    private static final AtomicInteger CALLS = new AtomicInteger();

    static final class SlowInit {
        static {
            System.out.println("<clinit>: begin");
            INIT_ENTERED.countDown();
            try {
                LET_FINISH.await();
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                throw new ExceptionInInitializerError(error);
            }
            System.out.println("<clinit>: end");
        }

        static void ping() {
            CALLS.incrementAndGet();
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        System.out.println("main: start");
        try {
            Future<?> first = pool.submit(() -> SlowInit.ping());
            INIT_ENTERED.await();

            Future<?> second = pool.submit(() -> {
                SECOND_READY.countDown();
                SlowInit.ping();
            });
            SECOND_READY.await();

            System.out.println("main: release initializer");
            LET_FINISH.countDown();

            first.get();
            second.get();
            System.out.println("method calls=" + CALLS.get());
        } finally {
            LET_FINISH.countDown();
            pool.shutdownNow();
        }
    }
}
```

Compile/run in a new JVM using JDK 17+:

```sh
javac --release 17 -d out src/demo/InitializationDemo.java
java -cp out demo.InitializationDemo
```

**Stdout:**

```text
main: start
<clinit>: begin
main: release initializer
<clinit>: end
method calls=2
```

Explanation:

1. Main prints `main: start` before submitting, so this message appears first.
2. The first worker performs an active use via `SlowInit.ping()` and triggers initialization; `<clinit>` prints `begin`, signals main, and then waits on the latch.
3. Main only creates the second worker after knowing the initializer has started. The second thread is ready to call `ping()`, but is not allowed to improperly complete its active use while the class is still initializing.
4. Main prints `release` and opens the latch; the initializer prints `end` and completes successfully.
5. Both `ping()` calls eventually complete, so `CALLS == 2`. The static initializer executes only once despite having two tasks.

**This is not a way to acquire `LC`.** `CountDownLatch` is synchronization **built by the program inside the initializer body** to create observable milestones. `SECOND_READY` reports that the thread has arrived right before the call; it **does not guarantee** that at the exact moment main opens the latch, that thread is already waiting inside the `LC` mechanism. Do not write assertions that depend on instantaneous thread state or `Thread.sleep`.

## 10. Class Loading and Class Initialization Can Follow One Another in a Single Operation

A call:

```java
Class<?> c = Class.forName("demo.Widget", true, loader);
```

can require both **loading** and **initialization**:

```text
If Widget is not yet loaded:
    loader lookup and define/link according to the rules
    └── appropriate class-loading synchronization

When Widget must be initialized:
    JVM checks the initialization state of runtime Widget
    └── coordinates via LC per JLS 12.4.2
        and then runs <clinit> when appropriate
```

However, **one cannot infer** that "a single lock is held across both phases." Linking/resolution behavior may not match a rigid timeline, and custom loaders can perform additional work. With the default implementation, `loadClass` does not itself execute `<clinit>` to prepare the application.

### Loader Locks Differ by Instance

If `loaderA` and `loaderB` each define the same binary name `pkg.C`, they can have independent class-loading locks. The two defined runtime classes also have **separate initialization states**:

```text
(pkg.C, loaderA) → Class<?> A → initialization state of A
(pkg.C, loaderB) → Class<?> B → initialization state of B
```

A class with the same name can be initialized once **per runtime definition**. Do not describe it as "there is only one `<clinit>` per binary name across the entire JVM."

If `loaderB` asks its parent and receives the `C` defined by `loaderA`, then both callers still use **the same Class<?>** and the same initialization state. The defining loader is what forms part of type identity, not the loader merely used to initiate the lookup.

## 11. Same-Thread Initialization Recursion and Default Static Values

The JLS also describes the case where **the thread currently initializing `C` requests initialization of `C` again**. The JVM recognizes the same thread and does not wait for itself.

**Illustrative** example (requires an active-use caller to run):

```java
class Recursive {
    static int x = compute();

    private static int compute() {
        return Recursive.x;
    }
}
```

During preparation, `x` has the default value `0`. When `compute()` runs during initialization, it can read `Recursive.x` before the final assignment completes. A recursive initialization request on the same thread does not cause waiting; the returned value can come from the preparation state or partially executed initializers.

This proves that **the dependency order of static state matters greatly**; it does not mean the JVM locks the entire class on a monitor so that nothing can touch any field.

**Avoid cyclic static initialization** when code cannot tolerate default values or incomplete state. Move cyclically dependent work into a factory or startup phase with an explicit ordering.

## 12. Cross-Thread Class Initialization Deadlock

A typical scenario when two threads concurrently initialize **two different classes**:

```text
Thread A                           Thread B
initialize Alpha                   initialize Beta
    │                                  │
    ▼                                  ▼
Alpha.<clinit>                    Beta.<clinit>
    │                                  │
needs Beta                        needs Alpha
    │                                  │
    └── waits for Beta                └── waits for Alpha

          Wait cycle A ↔ B
```

This is a **deadlock diagram**, not a demo program that should be run (as it can hang indefinitely). The class-initialization waiting mechanism can contribute to deadlock even when **both classes have already finished loading**. Switching the loader to parallel-capable does not by itself fix a `<clinit>` wait cycle.

Sources of risk:

- A static initializer performs slow I/O, network calls, or waits for asynchronous tasks.
- Two classes statically initialize while depending on each other via locks/futures.
- A class initializer holds an application lock and then performs an active use of another class; the other thread holds the locks in the reverse order.
- Plugin callbacks are invoked during static initialization while the host waits for plugin readiness.

**Better design:** keep `<clinit>` lightweight, avoid spawning nested threads/callbacks, place startup logic with explicit dependencies after classes are initialized, and define lock ordering for application locks.

The `LC` locks of two different runtime classes **are not a shared mutex** protecting all global mutable state. If two static initializers concurrently write to a shared map, application-level synchronization is still required.

## 13. Failed Initialization and the Erroneous State

When a class initializer throws an exception, the JVM handles initialization failure according to the JLS/JVMS. If the initializer completes abruptly due to an exception that is not an `Error`, the first use typically receives `ExceptionInInitializerError`. The runtime class may be marked **erroneous**, and subsequent active uses may receive `NoClassDefFoundError` instead of re-running `<clinit>`.

A very common point of confusion: `NoClassDefFoundError` on a subsequent attempt **does not necessarily** mean the `.class` file is missing from the classpath.

## 14. Lab D — Initializer Throws an Error, Subsequent Attempts Do Not Re-Run It

File **`src/demo/InitializationFailureDemo.java`:**

```java
package demo;

public final class InitializationFailureDemo {
    static final class Broken {
        static int value = fail();

        static int fail() {
            System.out.println("initializer executes");
            throw new IllegalStateException("bad configuration");
        }
    }

    public static void main(String[] args) {
        for (int attempt = 1; attempt <= 2; attempt++) {
            try {
                int value = Broken.value;
                System.out.println(value);
            } catch (LinkageError error) {
                System.out.println("attempt " + attempt + ": " +
                        error.getClass().getSimpleName());
            }
        }
    }
}
```

Compile and run in **a new JVM process**:

```sh
javac --release 17 -d out src/demo/InitializationFailureDemo.java
java -cp out demo.InitializationFailureDemo
```

**Stdout:**

```text
initializer executes
attempt 1: ExceptionInInitializerError
attempt 2: NoClassDefFoundError
```

Analysis:

1. The first access to `Broken.value` forces `Broken` to initialize; `fail()` runs and throws `IllegalStateException`.
2. Because the thrown exception is not an `Error`, the JVM wraps it in `ExceptionInInitializerError`, leaving the class in the erroneous state.
3. The subsequent access on the same runtime class does not re-run `fail()`. The JVM reports `NoClassDefFoundError`.
4. `catch (LinkageError)` here is only for printing the outcome label for learning purposes. Real applications need to preserve the stack trace/cause and typically should not continue business processing if a required class has failed initialization.
5. Do not try to "fix" this by calling `loader.loadClass` again: `loadClass` does not reset the erroneous state of the runtime definition.

To obtain a new runtime class with a separate initialization lifecycle, a proper class-loading mechanism with a **new defining loader identity** is required; that is a plugin/version lifecycle concern, not an ad-hoc error retry technique.

## 15. How Do `<clinit>` and `<init>` Differ?

| Property | `<clinit>` | `<init>` |
| --- | --- | --- |
| Role | Class/interface initialization | Object constructor/instance initialization |
| Occurrences in lifecycle | Once successfully for a runtime class when initialized | Per instance construction |
| Relationship with JVM `LC` | State/waiting coordinated by the JVM | Not serialized by `LC` across all instances after the class is initialized |
| Can it be invoked directly like a Java method? | No | Via `new` or a reflection constructor according to Java access rules |
| Does it produce distinct errors? | `ExceptionInInitializerError`, erroneous class | Constructor body may throw exceptions; reflection may wrap in `InvocationTargetException` |

An initialized class can have instances created by multiple threads concurrently. If a constructor manipulates a mutable counter or collection, the caller must protect state with appropriate primitives. Do not use the class-loading lock to synchronize business code inside a constructor.

## 16. Differences Among Loading, Linking, and Initialization Errors

| Symptom | Typical phase | What to check |
| --- | --- | --- |
| `ClassNotFoundException` when calling `loadClass` | Lookup failed to find the class | Binary name, parent graph, classpath/JAR/URL |
| `ClassFormatError` | Class bytes/verification | Format, bytecode version, source JAR |
| `LinkageError` duplicate definition | Custom loader race during `defineClass` | `getClassLoadingLock`, `findLoadedClass`, concurrency |
| `NoSuchMethodError` / `NoSuchFieldError` | Resolution/linking against a wrong binary API version | Descriptors, dependency collision |
| `ExceptionInInitializerError` | `<clinit>` failed | First cause, static blocks, I/O/callbacks |
| `NoClassDefFoundError` on an active use after an init failure | Erroneous runtime class | Find the exception from the initial initialization |
| Program hangs only with multiple threads | Loading lock, class-init state, or application lock/deadlock | Thread dumps, lock ordering, stack traces |
| Static block runs again after plugin reload | Different runtime class due to a new defining loader | Class identity, class loader lifecycle |
| `ClassCastException` with the same binary name | Two different runtime type identities | Print defining loaders, shared API graph |

**Do not apply a single fix to every error.** Correct class loading does not guarantee binary compatibility. Successful class initialization does not replace synchronization for mutable state in the application.

## 17. Debugging: Observing Class Loading and Class Initialization Independently

### API for Inspecting the Defining Loader

```java
static void describe(Class<?> type) {
    System.out.println("name=" + type.getName());
    System.out.println("defining loader=" + type.getClassLoader());
    System.out.println("module=" + type.getModule().getName());
}
```

This is an **illustrative method** that needs to be placed inside a class. `getClassLoader() == null` typically represents the bootstrap loader; `getModule().getName() == null` may indicate an unnamed module.

### JVM Logging

On HotSpot, Unified Logging is supported:

```sh
java -Xlog:class+load=info -cp out demo.InitializationDemo
java -Xlog:class+init=info -cp out demo.InitializationDemo
java -Xlog:help
```

Tag availability depends on the JVM/JDK build; `class+load` helps inspect loading events, and `class+init` can help inspect initialization events if supported by the runtime. The log output is long and its order depends on the runtime, so there is **no fixed stdout** for this logging command. `-Xlog:help` lists supported tags/levels.

### Thread Dumps

Use `jcmd <pid> Thread.print` on a supported JVM or an equivalent thread dump tool. When inspecting the dump:

1. Look for threads in `ClassLoader.loadClass`, `findClass`, or a loader callback.
2. Look for threads in a static initializer `<clinit>` or waiting for another class's initialization.
3. Cross-check parent loader relationships and any application locks currently held.
4. Capture multiple snapshots if possible to avoid drawing conclusions from a transient state.
5. Do not assume the JVM's `LC` always appears as a Java monitor identical to `getClassLoadingLock`.

### Bytecode

```sh
javap -classpath out -c -p demo.InitializationFailureDemo
javap -classpath out -c -p 'demo.InitializationFailureDemo$Broken'
```

`javap` can display `<clinit>`, field operations, and invocation bytecode; it **does not** prove at what moment a runtime thread held initialization coordination. In PowerShell and POSIX shells, single quotes protect the `$` character in a nested binary name from expansion.

## 18. Multithreaded Class Loader Design Rules

- **Prefer overriding `findClass`** when you only need to read bytecode from a custom source; keep the standard `loadClass` if you do not need a custom delegation policy.
- When overriding `loadClass`, use `synchronized (getClassLoadingLock(name))` appropriately, check `findLoadedClass`, and call `defineClass` only once per binary name within a loader instance.
- If you need to load different class names concurrently, understand `registerAsParallelCapable` and its superclass requirement; do not enable it merely to run `<clinit>` faster.
- Avoid holding the loader lock during prolonged I/O/blocking/callback operations if the architecture allows separating those responsibilities.
- Do not swallow `Throwable` and try loading another class: that can mask a `LinkageError`, security failure, or serious resource error.
- Ensure shared APIs/DTOs/exceptions from the host resolve to **the same runtime `Class<?>`** on both sides, regardless of a parent-first or child-first policy.
- Avoid heavy side effects and circular dependencies in static initializers; separate type initialization from plugin startup lifecycle.
- Test with a **real loader graph** and multiple threads, not only by running all classes on the same system classpath in an IDE.
- Manage loader lifecycle and references; `URLClassLoader.close()` closes resource handles but does not guarantee immediate class unloading.
- If you observe a waiting thread, determine whether it is waiting on a **loading lock**, **class initialization state**, or **application synchronization** before modifying code.

## 19. Misconceptions to Avoid

- **"The class-loading lock protects the static initializer."** That is not the role of the class-loading lock.
- **"The `LC` lock is the object returned by `getClassLoadingLock`."** No API contract states this.
- **"`synchronized (MyClass.class)` always blocks JVM initialization."** Do not assume this; the JVM has its own internal `LC` rules.
- **"Parallel-capable means two threads run `<clinit>` of the same class concurrently."** False.
- **"Once loading completes, `<clinit>` has already run."** Not necessarily.
- **"`findClass` is called only once in all cases."** False if the lookups all fail.
- **"A static initializer runs once per binary name across the entire JVM."** False if two defining loaders create two runtime class identities.
- **"If `<clinit>` fails, call `loadClass` again to retry initialization."** No; the class may already be in the erroneous state.
- **"The `LC` lock is held throughout the entire static block body."** That cannot be inferred from the JLS.
- **"Class-init deadlock goes away if parallel-capable is enabled."** No; these are two different mechanisms.
- **"Instance constructors are serialized by the class-init lock."** Not after the class is initialized.
- **"A thread dump showing `BLOCKED` is definitely a loading-lock deadlock."** No: you need to inspect stacks and monitor relationships.
- **"The class-initialization lock protects all shared mutable fields of the application."** No; the application must still synchronize its own state.

## 20. Self-Check Questions with Answers

**1. Which API is associated with the class-loading lock?** `ClassLoader.getClassLoadingLock(String)`.

**2. What lock does a non-parallel-capable loader typically use for different names?** The loader instance itself.

**3. How does parallel-capable help?** It allows locking per class name, enabling different class names to be loaded concurrently.

**4. Who manages the class-initialization lock `LC`?** The JVM according to the JLS §12.4.2 procedure, associated with a runtime class/interface.

**5. Does `ClassLoader.loadClass` automatically run the static block?** Normally it does not require initialization.

**6. If two threads concurrently perform an active use of an uninitialized class, does `<clinit>` run twice?** No; the JVM coordinates a single initialization process according to its semantics.

**7. Is there a public Java API to obtain `LC`?** No.

**8. Must the JVM hold `LC` throughout the `<clinit>` body?** Do not treat that as a guarantee; `LC` coordinates state and waiting.

**9. Does `registerAsParallelCapable` change initialization semantics?** No.

**10. Why can a loader call `findClass` twice for the same name?** If a lookup fails to find the class, a later lookup can retry; only a successful definition creates a class for reuse.

**11. When `<clinit>` throws an exception, what might a subsequent active use observe?** `NoClassDefFoundError` because the class is in the erroneous state.

**12. Do two loaders defining the same binary name share the same initialization state?** No; they create two runtime type identities.

**13. Why can two static initializers deadlock?** Two threads can wait on each other when each initializer performs an active use of the class that the other thread is initializing.

**14. How does `<init>` differ from `<clinit>`?** `<init>` is an instance constructor, whereas `<clinit>` is runtime class/interface initialization.

**15. What should you check first when debugging a hung thread?** Thread stacks, loader object/parent, `<clinit>` state, application locks, and runtime class identity.

## 21. Authoritative References

- [Java SE 17 `ClassLoader` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `findLoadedClass`, `getClassLoadingLock`, and `registerAsParallelCapable`.
- [Java Language Specification 17 — §12.4.2 Detailed Initialization Procedure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2): `LC`, same-thread recursion, waiting, initialized, and erroneous states.
- [Java Language Specification 17 — §12.4.1 When Initialization Occurs](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.1): active use, constant variables, and initiation.
- [Java Virtual Machine Specification 17 — Chapter 5](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): loading, linking, initialization, defining loader, and runtime type identity.
- [Java SE 17 `CountDownLatch`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): custom synchronization designed in the example for deterministic observations.

**Conclusion:** The **class-loading lock** coordinates **looking up/defining a class through a loader**, either sequentially across the whole loader or per name when parallel-capable. The **class-initialization lock `LC`** is a **JVM mechanism per runtime class/interface**, ensuring initialization obeys state transitions and thread ownership. Both locks may appear close together during a single class usage, yet they **differ in object, scope, and errors, and do not replace one another**.
