# Synchronizing Class Initialization Across Multiple Threads in Java

## 1. The Problem: Multiple Threads Concurrently Using an Uninitialized Class

When a Java class is actively used (*active use*) for the first time, the JVM must ensure that the class is **initialized** before that operation proceeds. For example, multiple threads might simultaneously read `Configuration.PORT`, call `Registry.lookup()`, or execute `new Service()`. If the class is not yet initialized, it is necessary to determine **which thread executes the static initialization code**, how the remaining threads wait, and how the result is published.

For **a single runtime class definition**, the JVM guarantees:

- Only **one thread** performs the static initialization of the class in an initialization pass; other threads requesting initialization of the same class must wait when necessary.
- When initialization **succeeds**, the JVM records that the class has been initialized; subsequent uses do not re-run `<clinit>`.
- Threads that proceed after the class is initialized observe the initialization results according to the *happens-before* guarantee of the Java Memory Model.
- If initialization **fails**, the class transitions to an *erroneous* state; the JVM does not automatically re-run the initializer on the same class definition.

Important point: a class definition is identified by **(binary name, defining class loader)**. Two different class loaders that independently define the same name `com.example.Configuration` form two distinct runtime types, so they have their own initialization state and initialization process.

This mechanism belongs to the JVM and does not require programmers to manually use `synchronized` for every static initializer. However, it does **not** automatically guarantee thread safety for all operations modifying static fields after initialization completes.

## 2. Loading, Linking, and Initialization Must Be Distinguished

The lifecycle of a class consists of activities with distinct meanings:

1. **Loading:** finding or creating a runtime representation from the binary definition of a class/interface.
2. **Linking:** verification, preparation, and resolution according to JVM rules.
3. **Initialization:** executing static variable initializers and `static` blocks in the specified order; the compiler typically generates a special `<clinit>` method for the code to be executed.

This article analyzes the **initialization** step. Loading `SomeClass.class` does not mean the initializer has run.

Illustrative example (a class snippet, not yet a standalone program):

```java
class Settings {
    static final int PORT_CONSTANT = 8080;
    static final int PORT_RUNTIME = readPort();

    static int readPort() {
        System.out.println("Settings initialized");
        return 9090;
    }
}
```

- `Settings.PORT_CONSTANT` is a *constant variable* (a primitive `static final` assigned a compile-time constant expression); accessing this constant value may be inlined by the compiler and does **not force** initializing `Settings`.
- `Settings.PORT_RUNTIME` is assigned via a method call, not a constant variable. A `getstatic` access to this field is an active use and can trigger initialization.
- `Settings.class` or `Class.forName("Settings", false, loader)` does not actively request class initialization.
- `Class.forName("Settings", true, loader)` or `Class.forName("Settings")` requests initialization; if the class has already been initialized, it does not run again.

A thread may see the `Class<?>` object earlier than when the `static` code runs. Reading *class loading* logs is therefore different from reading log lines printed from an initializer.

## 3. JLS §12.4.2 Specification: Dedicated Initialization State and Lock per Class

Java Language Specification §12.4.2 describes a detailed procedure using a **unique initialization lock** `L_C` for each class or interface `C`.

| State of C | Meaning |
| --- | --- |
| Not yet initialized | No thread has performed initialization yet |
| Being initialized by thread T | T is responsible for running initialization |
| Successfully initialized | Subsequent requests use the published state |
| In an *erroneous* state | Initialization failed; it must not be retried on that same runtime class |

When a thread wants to initialize `C`, the JVM conceptually executes the procedure:

1. Synchronize on lock `L_C` to check the state of `C`.
2. **If already successfully initialized:** release the lock and finish the procedure.
3. **If another thread is initializing C:** release the lock and wait for that process to complete; after waking up, check the state again.
4. **If the current thread itself is initializing C:** handle the repeated initialization request on the same thread as a normal completion, avoiding waiting on itself.
5. **If C is erroneous:** release the lock and throw `NoClassDefFoundError` for subsequent initialization requests.
6. **If not yet initialized:** mark C as being initialized by the current thread, **release the initialization lock**, perform the relevant steps, and run initialization according to the specification.
7. Upon completion or failure, synchronize to record the resulting state and notify waiting threads.

**Lock L_C is not held throughout the entire initializer code.** This is a detail that is easy to misunderstand: the JVM uses the lock to coordinate waiting and completion states; it does not need to hold the init lock while executing all statements inside `<clinit>`. The JVM is also allowed to optimize synchronization while preserving the *happens-before* relationship.

Do not rely on the assumption that `synchronized (C.class)` is a public way to acquire the exact internal `L_C` lock of the JVM. The purpose of `synchronized (C.class)` is to lock the monitor of the `Class` object in application code; the initialization specification has its own rules.

### 3.1. What Do Two Threads See?

```text
Time        Thread A                          Thread B
---------   --------------------------------  ---------------------------------
t0          reads Config.VALUE                reads Config.VALUE
t1          gets right to init Config         sees Config being init by A
t2          runs initialization code          waits for initialization result
t3          marks init as succeeded
t4                                            wakes up, checks state
t5          continues using VALUE             continues using initialized VALUE
```

There is no guarantee that **A will always win**: the scheduler, prior loading, and invocation timing determine which thread arrives first. The JVM only guarantees that **no two initialization passes run concurrently on the same runtime Class**.

## 4. Java 17+ Example: Four Threads, One Static Initialization Pass

The program uses three `CountDownLatch` instances so that four workers become ready together and then start reading `Configuration.PORT`. To keep stdout deterministic, each worker only writes to its own array element; main waits for all of them to finish and prints the results in a known order.

Save the file `ConcurrentClassInitializationDemo.java`:

```java
import java.util.Arrays;
import java.util.concurrent.CountDownLatch;

public class ConcurrentClassInitializationDemo {

    static class Configuration {
        static int initializationCount;
        static final int PORT = initialize();

        private static int initialize() {
            initializationCount++;
            System.out.println("init: begin");
            try {
                Thread.sleep(150); // Simulate a slow init step.
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("init interrupted", e);
            }
            System.out.println("init: end");
            return 8080;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        int workers = 4;
        int[] observed = new int[workers];

        CountDownLatch ready = new CountDownLatch(workers);
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(workers);

        for (int i = 0; i < workers; i++) {
            final int index = i;
            Thread thread = new Thread(() -> {
                ready.countDown();
                try {
                    start.await();
                    observed[index] = Configuration.PORT;
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(e);
                } finally {
                    finished.countDown();
                }
            }, "reader-" + i);
            thread.start();
        }

        ready.await();
        start.countDown();
        finished.await();

        System.out.println("initializations=" +
                Configuration.initializationCount);
        System.out.println("values=" + Arrays.toString(observed));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac ConcurrentClassInitializationDemo.java
java ConcurrentClassInitializationDemo
```

Stdout under normal execution conditions, without unexpected interruption:

```text
init: begin
init: end
initializations=1
values=[8080, 8080, 8080, 8080]
```

Explanation:

1. `PORT` is assigned via `initialize()`, so it is **not** a compile-time constant and can trigger initialization when read.
2. `ready` ensures all four workers reach the waiting point before `start` is released. It creates conditions for contention, but does not guarantee that all of them actually execute the same `getstatic` instruction in the same nanosecond.
3. Whichever thread reaches `Configuration.PORT` first can obtain the right to run the initializer. Other threads requesting initialization in the meantime must wait and do not execute `initialize()` again.
4. `initializationCount` is therefore 1. The two `init` lines appear only once.
5. After `finished.await()` completes, main sees the workers' writes to `observed`; the array is printed in index order, so the result does not change due to the scheduler.
6. `Thread.sleep(150)` is only there to make the initialization duration easy to observe; it does **not** provide thread safety.

**Distinguishing two synchronization guarantees:** Class initialization publishes the value of `Configuration.PORT`; `CountDownLatch` in the example also ensures that main waits for all four workers to finish before reading the `observed` array.

## 5. Happens-Before: Why Is Initial Static State Published Correctly?

Allowing only one thread to run the initializer is not enough: the JVM must also ensure that threads that have passed the initialization check can observe the values set during that process.

According to the Java Memory Model and JLS §12.4.2, synchronization actions during initialization establish/preserve the necessary **happens-before** relationships. When a class initializes successfully, threads that use the class afterward do not need to create additional memory barriers on their own just to properly see the values that the initializer assigned.

Example (illustrative class):

```java
final class Catalog {
    static final java.util.Map<String, Integer> PORTS = build();

    private static java.util.Map<String, Integer> build() {
        java.util.Map<String, Integer> data = new java.util.HashMap<>();
        data.put("http", 8080);
        data.put("admin", 9090);
        return java.util.Collections.unmodifiableMap(data);
    }
}
```

Threads reading `Catalog.PORTS` after initialization succeeds will observe the structure already containing two entries. The original map is only a local variable inside `build()` and is not exposed elsewhere to be modified after initialization.

However, properly publishing the **initial state** does not make subsequent write operations automatically synchronized:

```java
class Counter {
    static int count;

    static void increment() {
        count++; // Not atomic when multiple threads update concurrently.
    }
}
```

`Counter.count++` is still a read–modify–write operation that can race across threads. An `AtomicInteger`, `synchronized`, a lock, or an appropriate immutable design is needed. `volatile` alone also does **not** turn `count++` into an atomic operation.

## 6. Repeated Initialization Requests on the Initializing Thread Itself

The distinction between **another thread** and **the initializing thread itself** is essential.

An initializer can call a static method of its own class or indirectly loop back to require initialization of the same class. The JVM recognizes the "being initialized by the current thread" state and does not wait again. However, because the initializer has not yet finished, static fields assigned **after** the current point may still hold their default values from the preparation step.

Save the standalone example `RecursiveInitializationDemo.java`:

```java
public class RecursiveInitializationDemo {

    static class State {
        static int early = readLater();
        static int later = 42;

        static int readLater() {
            return later;
        }
    }

    public static void main(String[] args) {
        System.out.println("early=" + State.early);
        System.out.println("later=" + State.later);
    }
}
```

```bash
javac RecursiveInitializationDemo.java
java RecursiveInitializationDemo
```

Stdout:

```text
early=0
later=42
```

At the time `readLater()` runs to assign `early`, the current thread is already in the middle of initializing `State`. `later` already has the default value `0` from preparation, but the assignment `later = 42` has not yet reached its turn to execute. Only when the initializer completes does `later` become `42`.

This serves as a warning about **static field declaration order** and call cycles inside initializers. **Same-thread** repeated initialization does not wait indefinitely, but it can cause logic to observe a partially initialized state.

## 7. Failure: What Happens to the Remaining Threads if the Initializer Fails?

If a static initializer throws an unhandled exception, the JVM marks the class as being in an **erroneous** state, wakes up the waiting threads, and does not attempt to initialize that class definition again.

- If the thrown cause is **not an `Error`**, the JVM typically wraps it in an `ExceptionInInitializerError` for the thread executing the initializer (according to the specification's rules).
- If the cause is already an `Error`, the JVM propagates the error object directly instead of wrapping it like a regular exception.
- Threads that were waiting and subsequent active uses after the class is in the erroneous state typically receive a `NoClassDefFoundError`. You should also check the original cause in the logs, because later messages may not reveal the full root error.

Standalone example `FailedInitializationDemo.java`:

```java
public class FailedInitializationDemo {

    static class Broken {
        static final int VALUE = parse();

        private static int parse() {
            throw new IllegalArgumentException("invalid configuration");
        }
    }

    public static void main(String[] args) {
        for (int attempt = 1; attempt <= 2; attempt++) {
            try {
                System.out.println(Broken.VALUE);
            } catch (LinkageError error) {
                System.out.println("attempt-" + attempt + ": " +
                        error.getClass().getSimpleName());
            }
        }
    }
}
```

```bash
javac FailedInitializationDemo.java
java FailedInitializationDemo
```

Stdout in the example:

```text
attempt-1: ExceptionInInitializerError
attempt-2: NoClassDefFoundError
```

On the first attempt, `Broken.VALUE` triggers `parse()`, which throws `IllegalArgumentException`. The JVM wraps it in `ExceptionInInitializerError` and marks `Broken` as erroneous. On the second attempt, the JVM does not call `parse()` again.

The `catch (LinkageError)` block is present in the example only to **observe the error name**; in a real system, critical `Error` instances should not be arbitrarily swallowed to keep running as if the application state were still valid.

### Failure from a Superclass or Superinterface

When initialization of a class must initialize its superclass and any superinterfaces that declare default methods according to the specification rules, a failure in a dependency requiring initialization can cause the subclass initialization to fail. The JVM does not ignore the failure to complete the subclass.

Two types of errors must be distinguished:
- **Missing class during loading/linking**: such as `NoClassDefFoundError` due to a missing required superclass.
- **Class was defined but the initializer failed**: the cause typically lies in `static` code, configuration, or a task invoked during init.

Having the same exception name in the logs is not enough to determine the type of error; you must inspect the timing, stack trace, and `Caused by` chain.

## 8. Deadlock Between Classes When Different Threads Cross-Initialize

The JVM avoids the case where **a single thread waits on itself when re-initializing the same class**, but it does not guarantee avoiding all kinds of deadlocks in a multi-class, multi-threaded system.

Suppose:
- Thread T1 is initializing `A`. In `A`'s static initializer, it needs to use `B` and requires `B` to finish initializing.
- Thread T2 is initializing `B`. In `B`'s static initializer, it in turn needs `A` to complete initialization.

```text
T1: owns initialization of A -> needs B -> waits for T2
T2: owns initialization of B -> needs A -> waits for T1
```

This is a **wait cycle**; the program can hang. Unlike the example of reading `State.later` on the same thread, two threads are not allowed to bypass a class currently being initialized by another thread.

To reduce the risk:

1. Keep static initializers short; prefer building immutable data without lengthy side effects.
2. Avoid operations in static initializers such as `Future.get()`, `Thread.join()`, callbacks, remote calls, or waiting on a singleton of a class with a circular dependency.
3. Extract bootstrapping steps that may wait or block into an explicitly ordered application procedure outside `<clinit>` when appropriate.
4. Do not spawn a thread inside an initializer and wait for that thread to complete if the new thread might reference back to the class being initialized.
5. When an application hangs at startup, capture a thread dump (for example, `jcmd <pid> Thread.print` when attach is available) and cross-reference the stacks of threads participating in class initialization.

One should not assume that every object-monitor deadlock detection tool automatically describes wait cycles involving initialization in full; thread dumps and dependency graphs still need to be analyzed.

## 9. ClassLoader Boundaries: Same Name Does Not Necessarily Mean the Same Initialization Pass

In plugin systems, containers, or dynamic reloading environments:

```text
ApplicationLoader
  |- Config (defined by application loader; one init state)
  |
  |- PluginLoader A
  |    |- PluginA (uses shared Config)
  |
  |- PluginLoader B
       |- PluginB (uses shared Config)
```

If both plugins **delegate** to the parent loader and receive the exact `Config` class defined by the parent, they share the single initialization state of `Config`.

Conversely:

```text
PluginLoader A -> defines com.example.Config -> init state A
PluginLoader B -> defines com.example.Config -> init state B
```

If each plugin **independently defines** `com.example.Config`, the JVM treats them as two separate runtime Classes. Each has its own static state, one successful initialization (if it succeeds), and its own coordination mechanism.

| Condition | Is initialization shared? |
| --- | --- |
| Multiple threads use the same `Class<?>` | Yes |
| Two child loaders both delegate to one definition from the parent | Yes |
| Two different loaders independently define the same binary name | No |
| A `Class<?>` has already been successfully initialized previously | Not re-initialized |
| A `Class<?>` is already erroneous | Not retried automatically; later init requests fail |

Therefore, seeing an "initialized" log twice is not enough to conclude that the JVM broke the rules; you must compare the **defining loaders** of the two versions of the class. Conversely, a class that became erroneous in an old loader does not make a completely new runtime definition in another loader automatically erroneous.

## 10. Application: Initialization-on-Demand Holder for a Lazy Singleton

A practical example of JVM synchronization is the **initialization-on-demand holder idiom**. The instance is created only when code first requests the static field of the `Holder` class.

Save the file `LazyHolderDemo.java`:

```java
public class LazyHolderDemo {

    static final class Service {
        private Service() {
            System.out.println("Service constructed");
        }

        static Service instance() {
            return Holder.INSTANCE;
        }

        private static final class Holder {
            static final Service INSTANCE = new Service();
        }
    }

    public static void main(String[] args) {
        System.out.println("before");
        Service a = Service.instance();
        Service b = Service.instance();
        System.out.println("same=" + (a == b));
    }
}
```

```bash
javac LazyHolderDemo.java
java LazyHolderDemo
```

Stdout:

```text
before
Service constructed
same=true
```

The first time `Holder.INSTANCE` is read, the JVM coordinates the initialization of `Holder`. The code creating `Service` runs once for the same runtime `Holder`, and the reference is safely published to threads. This approach avoids placing `synchronized` on every `instance()` call solely for lazy singleton initialization.

**Limitations:** another loader that independently defines `Holder` can create its own singleton; an error in the constructor causes `Holder` initialization to fail; mutable state inside `Service` still requires its own thread safety.

## 11. Common Misconceptions and Mistakes

| Misconception | Reality |
| --- | --- |
| "`static` runs only once across the entire JVM." | One successful initialization per **runtime Class definition**; multiple loaders can have multiple definitions. |
| "Two threads can run the same `<clinit>` concurrently." | The JVM coordinates so that only one thread performs initialization of the same class. |
| "The JVM holds `synchronized(C.class)` across the entire `<clinit>`." | The initialization lock is a separate specification mechanism; it should not be equated with the application monitor. |
| "Reading any `static final` initializes the class." | Constant variable fields can be inlined and therefore do not mandate initialization. |
| "Once initialization finishes, all static updates are thread-safe." | Subsequent mutable updates still require appropriate synchronization. |
| "If `<clinit>` fails, the next thread will retry it." | The same runtime Class remains in the erroneous state; subsequent init requests fail. |
| "A recursive static call on the same thread always deadlocks." | The JVM allows same-thread recursive initialization to complete normally; however, default values may be observed. |
| "The JVM cannot deadlock during class init." | Two threads waiting on two cross-initializing classes can deadlock. |
| "Logs inside `static` indicate loading order." | Those logs reflect initialization, not necessarily loading. |

## 12. Diagnosing a Multi-Threaded Initialization Issue

When an application hangs or multiple threads receive `NoClassDefFoundError` on the first use of a class:

1. **Identify the exact runtime class.** Print `type.getName()` and `type.getClassLoader()` when you have a `Class<?>` object; `null` from `getClassLoader()` typically indicates the bootstrap loader.
2. **Identify the active use that triggered init.** For example, `new`, accessing a static field that is not a compile-time constant, calling a static method, or calling a reflection API that requires init.
3. **Read all static field initializers and `static {}` blocks.** Pay attention to declaration order, indirect method calls, and superclass initializers.
4. **Find the first initializing thread.** Capture a thread dump to determine where the thread is running or waiting; do not look only at the final exception of the awakened threads.
5. **Find the root error.** The first attempt may report `ExceptionInInitializerError` with a helpful `Caused by`; subsequent attempts typically show only `NoClassDefFoundError` due to the erroneous state.
6. **Check for A–B class dependency cycles or waiting on a task launched from `<clinit>`.**
7. **For plugins, identify the defining loader and the actual JAR.** Two classes with the same name do not guarantee a shared initialization.
8. **If the initializer succeeded but data still races, inspect subsequent writes** and the application's happens-before relationships instead of mistakenly fixing the init flow.

On a Java 17+ JVM supporting unified logging, you can observe the **loading** process with:

```bash
java -Xlog:class+load=info ConcurrentClassInitializationDemo
```

This is loading log output; to know when the initializer executes, combine logs from `<clinit>` code with stack/thread dumps. The `jcmd <pid> Thread.print` command requires appropriate attach permissions and its availability may vary by environment.

## 13. Self-Check Questions

**Question 1.** Three threads touch `Config.VALUE` for the first time with the same defining loader. Can `Config`'s `static` code print "init" three times?

**Answer:** No. Only one thread performs initialization for the same runtime Class; the other threads wait when needed and then use the result.

**Question 2.** Once initialization has succeeded, two threads execute `Counter.count++`. Is it guaranteed to increment by two?

**Answer:** No. `count++` is not atomic; synchronization during initialization does not protect subsequent updates.

**Question 3.** Why is `State.early` equal to 0 in the recursive example?

**Answer:** `State.readLater()` runs before the `later = 42` assignment statement within the same initialization process; at that point, `later` still holds its default value from preparation.

**Question 4.** Why does accessing `Broken.VALUE` yield `ExceptionInInitializerError` the first time and `NoClassDefFoundError` the second time?

**Answer:** On the first attempt, the initializer throws an exception, causing the JVM to mark the class as erroneous; subsequent attempts do not re-run the initializer.

**Question 5.** Two plugins each independently define a `Config` class with the same name, and each prints "initialized" once. Does this violate the specification?

**Answer:** No. Each defining loader has a separate runtime Class, so each class has its own initialization pass.

**Question 6.** Thread A initializes class A and then needs B; thread B initializes B and then needs A. Can this deadlock?

**Answer:** Yes. Two initialization wait requests across two threads create a wait cycle, unlike same-thread recursion.

## 14. Conclusion and Standard References

Class initialization synchronization is a **JVM contract per runtime Class**: only one thread performs initialization, other threads wait for the result when necessary, successful results are properly published according to the *happens-before* relationship, and an erroneous state is recorded to prevent automatic retries. Leverage this behavior when constructing immutable static data or lazy holders, while keeping mutable state, inter-class dependency cycles, and class loader boundaries clearly separated.

Official documentation:

- JLS 17 §12.4.1, *When Initialization Occurs*: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.1
- JLS 17 §12.4.2, *Detailed Initialization Procedure*: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2
- JVMS 17 §5.5, *Initialization*: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5
- JLS 17 §17.4.5, *Happens-before Order*: https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.5
