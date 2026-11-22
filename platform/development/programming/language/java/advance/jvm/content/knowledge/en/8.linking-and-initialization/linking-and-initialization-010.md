# Class Initialization Lock, Recursive Initialization, and Deadlock Risks in the JVM

## 1. Concept: Why Does Class Initialization Need Synchronization?

When a Java program first **actively uses** a class or interface according to the language/JVM rules, the runtime may need to perform **class initialization**: executing `static` field initializer expressions and `static { ... }` blocks. This is a distinct phase from *loading*, *verification/preparation*, or *resolution*.

Because Java allows multiple threads to execute concurrently, two threads may simultaneously want to use an **uninitialized** class. The JVM must ensure that the initialization process is properly managed: while one thread is performing initialization, another thread must not arbitrarily re-run the `static` part of the same class before it completes.

According to **JLS `12.4.2 — Detailed Initialization Procedure**, each class/interface `C` has an **initialization lock `LC`**. How the JVM maps `C` to an actual lock is an implementation detail; `LC` should not automatically be equated with the monitor of `C.class`.

Three situations determine the behavior:

1. **Uninitialized:** one thread is recorded as the thread performing initialization and runs the initialization sequence.
2. **Being initialized by the same thread:** if code inside `<clinit>` requests initialization of the same class again, this is **same-thread recursive initialization**; the repeated request **completes normally**, without waiting for itself.
3. **Being initialized by another thread:** the requesting thread must **wait** for the current process to finish, then recheck the class state. If multiple classes have mutually dependent initialization across multiple threads, a waiting cycle can create a **deadlock**.

```text
      Class C: uninitialized
                |
                | Thread T1 requests active use
                v
    C is being initialized by T1
         /              \
        /                \
 T1 requests C again    T2 requests C
        |                     |
  Returns normally         Waits for T1
 (does not run <clinit>    to finish
  a second time)
        |
        v
 T1 continues running outer initializer
        |
        +-- succeeds ---> C initialized, wakes waiting threads
        |
        +-- fails ------> C erroneous, wakes waiting threads
```

Key takeaway: **the initialization mechanism protects itself against same-thread recursive requests**, but **there is no automatic guarantee preventing all dependency cycles across different threads**.

## 2. Distinguishing Loading, Linking, Initialization, and Instance Construction

A class may already be known to the runtime without its `static` blocks ever having run.

| Phase | General meaning | Has the class's `static` code run yet? |
| --- | --- | --- |
| **Loading** | Finding/defining the runtime class/interface representation via a class loader | Not necessarily |
| **Linking: verification** | Checking the structure and type safety of the class file | Not `static` execution |
| **Linking: preparation** | Preparing `static` variables and setting default values per JVM rules | Does not run arbitrary initializer expressions |
| **Linking: resolution** | Resolving symbolic references per linking rules | Does not mean the class initializer has completed |
| **Initialization** | Executing `static` initializer expressions and `static { }` blocks per JLS rules | Yes |
| **Instance construction** | Allocating an object and running `<init>` for the instance | Distinct from `<clinit>` |

Class initialization usually involves the special method **`<clinit>`** in the class file: the compiler may combine the initialization code of static fields and static blocks into one method executed by the JVM according to initialization rules. `<clinit>` must not be confused with an instance constructor.

```java
class Config {
    static int PORT = loadPort();

    static int loadPort() {
        return 8080;
    }

    Config() {
        // Instance constructor
    }
}
```

This is **illustrative class code**, not a program with `main`. The default value of `PORT` during preparation is `0`; when initialization executes the `loadPort()` expression, the value is assigned to `8080`. Creating multiple `new Config()` instances afterward **does not re-run the class initializer**.

### When Does Class Initialization Typically Occur?

Active-use (*active use*) operations such as:

- Creating an instance of the class using `new`.
- Calling a `static` method declared by the class.
- Reading/writing a `static` field declared by the class, **with some exceptions for constant variables** per the JLS.
- Certain reflection operations that require initialization.

Conversely, referencing `SomeClass.class`, using `Class.forName(name, false, loader)`, or creating `new SomeClass[10]` **does not necessarily initialize `SomeClass`**. A `static final` field that is a **compile-time constant variable** may be inlined at the use site and does not trigger initialization of the declaring class when read under the corresponding rules.

**Be careful:** when a class is initialized, its superclass and any superinterfaces that declare default methods are initialized in the order specified by the JLS if not yet initialized. It is incorrect to say "every interface a class implements is forced to run its initializer" or "interface initialization always triggers initialization of all superinterfaces."

## 3. Initialization States and the Initialization Lock `LC`

The model in JLS `12.4.2 assumes each class/interface has a state representing one of four situations:

1. **Verified and prepared, not initialized.**
2. **Initialization in progress** by a specific thread.
3. **Fully initialized.**
4. **Erroneous state** because initialization could not complete validly.

These states help distinguish:

- A class that is loaded but still uninitialized.
- A class currently initializing with an active owning thread.
- A class initialized successfully, usable according to synchronization rules.
- A class whose initialization failed and **cannot normally be re-attempted** within the same class identity.

### 3.1. Summary of the JLS Algorithm (Intentionally Simplified)

For class/interface `C` and requesting thread `T`:

1. **Synchronize on the initialization lock `LC`**.
2. If `C` is being initialized by **another thread**, release the lock and **wait** for notification that the process has finished; then recheck the state.
3. If `C` is being initialized by **`T` itself**, this is a recursive request: release the lock and **return normally** from the repeated initialization request.
4. If `C` is **already initialized**, release the lock and return normally.
5. If `C` is in an **erroneous state**, release the lock and throw `NoClassDefFoundError`.
6. If uninitialized, record that **`T` is initializing `C`** and **release `LC`** before running the rest of initialization.
7. Perform pre-initialization steps involving constant variables, superclass and superinterfaces with default methods per the rules, assertion status, then run class/interface variable initializers and static initializer blocks in the appropriate textual order.
8. Upon success, re-synchronize on `LC`, transition the state to **initialized**, notify waiting threads, and return normally.
9. Upon failure, handle the throwable per the rules (possibly wrapping it in `ExceptionInInitializerError`), mark the class **erroneous**, notify waiting threads, and complete abnormally.

This is a **summary for learning purposes** and does not replace the full text of the algorithm including the specific exceptions and constraints of the JLS.

### 3.2. The Lock Is Not Necessarily Held Throughout `static` Block Execution

A very important detail: in the JLS algorithm, the thread **marks** itself as initializing the class while holding `LC`, then **releases the lock** before running superclass/default-interface initialization and the body of static initializers.

So why must other threads still wait? Because the JVM checks the **"initialization in progress by another thread"** state; upon encountering that state, a thread waits until initialization completes.

Therefore, we must distinguish:

- **Initialization lock `LC`:** used to coordinate state transitions and notifications.
- **State "being initialized by T":** tells the JVM which thread is currently responsible.
- **Execution time of initializer code:** may run after `LC` has been released.

One should not teach that "Thread A holds the `SomeClass.class` monitor from entering to leaving the `static` block" as a mandatory requirement of the specification. The JVM is free to optimize/transform the locking mechanism as long as it preserves the synchronization and observability required by the specification.

### 3.3. Why Not Use `synchronized(SomeClass.class)` Instead of Initialization Rules?

`SomeClass.class` is a `Class` object that application code can use as a monitor, but the JLS **does not require** the initialization lock `LC` to be that monitor object. Synchronizing on `SomeClass.class` is **not** an API for managing class initialization state.

Furthermore, when accessing `SomeClass.class`, a class literal does not automatically force the static initializer to run. Thus writing:

```java
synchronized (SomeClass.class) {
    // This is a monitor used by application code.
}
```

is an **illustration of synchronized syntax**; it does not replace the JVM's policy for `<clinit>`, nor is it a general solution for class-dependency deadlocks.

## 4. One Thread Initializes, Another Waits — `<clinit>` Does Not Run Twice

Suppose two threads almost simultaneously call `Cache.get()` and `Cache` is not yet initialized:

```text
Thread T1                            Thread T2
---------                            ---------
get Cache.value                     get Cache.value
    |                                    |
C not initialized                    C being initialized by T1
    |                                    |
mark C initializing by T1            wait for C state change
    |
run Cache.<clinit>
    |
set static fields
    |
mark C initialized, notify
    |                                    |
read Cache.value                     proceed, read Cache.value
```

After initialization completes successfully, both threads can continue using the class. The JVM must uphold the required synchronization relationships of initialization; it must not allow a waiting thread to proceed as if the class were initialized while the initializer is still partway through execution.

### 4.1. Java 17+ Example: Initializer Runs Only Once Despite Two Threads

Create the file **`ClassInitWaitDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class ClassInitWaitDemo {
    private static final CountDownLatch entered = new CountDownLatch(1);
    private static final CountDownLatch release = new CountDownLatch(1);
    private static final AtomicInteger runs = new AtomicInteger();

    static class Slow {
        static int value = initialize();

        static int initialize() {
            runs.incrementAndGet();
            entered.countDown();
            try {
                release.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(ex);
            }
            return 42;
        }
    }

    public static void main(String[] args) throws Exception {
        AtomicInteger first = new AtomicInteger();
        AtomicInteger second = new AtomicInteger();

        Thread t1 = new Thread(() -> first.set(Slow.value), "reader-1");
        t1.start();
        entered.await(); // Wait for t1 to actually enter the initializer.

        Thread t2 = new Thread(() -> second.set(Slow.value), "reader-2");
        t2.start();

        release.countDown(); // Allow the initializer to finish.
        t1.join();
        t2.join();

        System.out.println("initializer runs: " + runs.get());
        System.out.println("first: " + first.get());
        System.out.println("second: " + second.get());
    }
}
```

Compile/run:

```bash
javac --release 17 ClassInitWaitDemo.java
java ClassInitWaitDemo
```

**Exact stdout when the program completes normally:**

```text
initializer runs: 1
first: 42
second: 42
```

Explanation:

- Thread `t1` becomes the thread responsible for initializing `Slow`.
- It increments `runs` exactly once and waits on the `release` latch inside the initializer.
- Thread `t2` also accesses `Slow.value`. If it arrives while `Slow` is not yet initialized, it must wait for the JVM to complete initialization; if it arrives after `t1` completes, it reads the available value.
- Even though the scheduling order between `t2` and the release is non-deterministic, **the result is still one initializer run** and both read 42 under normal execution.

**Illustration limitation:** the synchronization latches in the program are tools for easy observation, **not the JVM's initialization lock `LC`**. One must not infer that the JVM implements class initialization using `CountDownLatch`.

## 5. Same-Thread Recursive Initialization: Default Values Can Be Observed

A static initializer can indirectly refer back to the very class currently being initialized:

```text
T1 starts initializing A
    |
    +→ A initializer needs B.value
                      |
                      +→ T1 starts initializing B
                                         |
                                         +→ B initializer reads A.value
                                                                    |
                                                                    +→ JVM sees A being initialized by T1
                                                                        → recursive init request for A returns
                                                                        → B reads current A.value
```

The JLS specifies that when the same thread requests initialization of a class **currently being initialized by it**, that request completes normally. It **does not** re-run `A.<clinit>` from the beginning and **does not** wait for work that the same thread is already doing.

Important consequence: a static field can be read while it still holds its **default value from preparation**, before the initializer expression in source completes.

### 5.1. Standalone Java 17+ Example: Dependency Cycle A → B → A

Create **`RecursiveInitDemo.java`**:

```java
public class RecursiveInitDemo {
    static class A {
        static int value = calculate();

        static int calculate() {
            return B.value + 1;
        }
    }

    static class B {
        static int value = A.value + 10;
    }

    public static void main(String[] args) {
        System.out.println("A.value = " + A.value);
        System.out.println("B.value = " + B.value);
    }
}
```

Run:

```bash
javac --release 17 RecursiveInitDemo.java
java RecursiveInitDemo
```

**Exact stdout:**

```text
A.value = 11
B.value = 10
```

### 5.2. Step-by-Step Walkthrough

Initially, during preparation, the `static int` fields hold the default value **0**:

```text
A.value = 0   (initializer expression not yet run)
B.value = 0   (initializer expression not yet run)
```

When `main` reads `A.value`:

1. The main thread starts `A.<clinit>`.
2. `A.value = calculate()` needs `B.value`.
3. The JVM starts `B.<clinit>` **on the same thread**.
4. `B.value = A.value + 10` reads `A.value`, while `A` is still being initialized by **the main thread**.
5. The repeated init request for `A` is treated by the JVM as a same-thread recursive request and **returns normally**; the field `A.value` is still **0** at this moment.
6. `B.value` gets `0 + 10 = 10`; `B` completes initialization.
7. `A.calculate()` reads `B.value = 10`, returns 11; `A.value` gets 11; `A` completes.
8. `main` prints `A.value = 11` and `B.value = 10`.

This is **not** a race condition because the example uses only a single thread for the initialization chain. Nor is it the JVM "skipping an assignment": the JVM intentionally handles same-thread recursive init requests by not waiting, and the default value can be read before the assignment expression finishes running.

### 5.3. Is Deadlock Always Avoided with Circular References?

No. Only the case where **the same thread** requests initialization of **the same class currently being initialized by it** has the recursive handling branch described above.

If a dependency cycle spans **two threads**, one thread may need a class currently being initialized by the other thread, and vice versa. In that case each thread must wait for **the other thread**; the JVM cannot resolve it using only the "same-thread recursion" rule.

### 5.4. Do Not Turn Dependency Cycles into an API Contract

If you edit the code or change the first-call order, the initialization timing of A/B can change. For example, reading `B.value` before `A.value` can produce a different sequence of results than reading A first. Therefore, production code should not rely on "default values observed mid-init-cycle" as intended business behavior.

To reduce risk, avoid static initializers accessing each other across multiple classes when possible; consider initializing later via explicit initialization, dependency injection, or creating config objects independent of class-loading order.

## 6. Class Initialization Deadlock: Two Threads Waiting on Two Different Classes

Now consider two classes `Alpha` and `Beta` whose static initializers reference each other:

```text
Thread T1                              Thread T2
---------                              ---------
start Alpha.<clinit>                   start Beta.<clinit>
Alpha: initializing by T1              Beta: initializing by T2
      |                                      |
      +→ needs Beta.value                    +→ needs Alpha.value
                |                                      |
                v                                      v
    Beta being init by T2                  Alpha being init by T1
                |                                      |
           T1 waits for T2                        T2 waits for T1
                |                                      |
                +--------------- cycle ----------------+
```

Neither thread can complete its own initializer because both are waiting for the other's class.

**This is a class initialization deadlock**, not necessarily a pure deadlock caused by two application threads holding `synchronized` monitors. The fact that initializers run after the JVM releases `LC` does not eliminate the issue, because the state **"class is being initialized by the other thread"** still forces the remaining thread to wait.

### 6.1. Why Doesn't the JVM Let Thread T1 Read Unfinished Beta Data?

The same-thread recursion mechanism only allows **the responsible thread** to continue when it requests re-initialization of its own class. Another thread does not have that same privilege: it must wait for the class's init process to finish per JLS rules.

If the JVM arbitrarily let T1 read `Beta.value` before `Beta` finished initializing, it would break the initialization synchronization contract with other threads. Therefore, the right solution is **avoiding cross-dependency cycles between initializers**, not forcing the JVM to skip waiting.

### 6.2. Java 17+ Example Reproducing the Wait Cycle with Daemon Threads

The following experiment **intentionally creates a deadlock**. Do not use this pattern in real applications. Both threads are set as **daemon** so that when the `main` thread prints the result and exits, the demo program is not kept alive by the two stuck threads themselves. Each class uses `CountDownLatch` to ensure **both initializers have started** before they access each other's static field.

Create the file **`InitDeadlockDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;

public class InitDeadlockDemo {
    private static final CountDownLatch bothStarted = new CountDownLatch(2);

    static void rendezvous() {
        bothStarted.countDown();
        try {
            bothStarted.await();
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(ex);
        }
    }

    static class Alpha {
        static int value = initialize();

        static int initialize() {
            rendezvous();
            return Beta.value + 1;
        }
    }

    static class Beta {
        static int value = initialize();

        static int initialize() {
            rendezvous();
            return Alpha.value + 1;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Thread t1 = new Thread(() -> {
            int unused = Alpha.value;
        }, "alpha-initializer");

        Thread t2 = new Thread(() -> {
            int unused = Beta.value;
        }, "beta-initializer");

        t1.setDaemon(true);
        t2.setDaemon(true);

        t1.start();
        t2.start();

        bothStarted.await();
        t1.join(300);
        t2.join(300);

        System.out.println("both initializers started: true");
        System.out.println("both threads alive: "
                + (t1.isAlive() && t2.isAlive()));
    }
}
```

Run with JDK 17+:

```bash
javac --release 17 InitDeadlockDemo.java
java InitDeadlockDemo
```

**Expected stdout in a normal execution environment:**

```text
both initializers started: true
both threads alive: true
```

The exact time the two threads are scheduled is not fixed, so **do not use the millisecond count in `join(300)` as a general proof of deadlock**. However, the latch guarantees both `Alpha` and `Beta` have entered their initializers before they reference the other class's value. In this situation, each side waits for the class being initialized by the other side.

Do not change `t1`/`t2` to non-daemon if just experimenting: then the process may never terminate. Only use the demo in an isolated learning environment; after the main thread finishes, the runtime can terminate daemon threads in the same process.

### 6.3. Why Is `CountDownLatch` Not the Source of the Deadlock?

The two `rendezvous()` calls serve to **synchronize the starting point**: they only wait until both class initializers have reached the barrier, and then both are released. Afterward:

- `Alpha.initialize()` needs to read `Beta.value`, while `Beta` is being initialized by T2.
- `Beta.initialize()` needs to read `Alpha.value`, while `Alpha` is being initialized by T1.

The actual wait cycle lies in the **class initialization dependencies**. Removing the latch could let one thread initialize both classes sequentially and accidentally avoid the deadlock, making the test non-reproducible.

### 6.4. Will `ClassCircularityError` Appear Automatically?

**No.** `ClassCircularityError` relates to detecting invalid cycles in **class or interface inheritance/implementation structures** during loading under its own rules. A cycle in **static initializer execution** across two threads is not automatically converted into `ClassCircularityError`.

A JVM may support various thread and lock diagnostic tools, but **one should not assume a class initialization deadlock will always be broken automatically by the runtime or always appear in every monitor-deadlock detection tool**. When investigating, combine thread dumps, `<clinit>` locations, stack traces, and the states of dependent classes.

## 7. How Does a Same-Thread Dependency Cycle Differ from a Cross-Thread Wait Cycle?

| Property | Same-thread recursive initialization | Cross-thread initialization deadlock |
| --- | --- | --- |
| Who is initializing A? | T1 | T1 |
| Who is initializing B? | T1 | T2 |
| B needs A while A is unfinished | T1 requests A, which is being initialized by T1 itself | T2 requests A, which is being initialized by T1 |
| Applicable JLS rule | Same-thread recursive request **returns normally** | Request from another thread **must wait** |
| Necessarily deadlocked? | No under this specific waiting mechanism | Can deadlock if a T1 → T2 → T1 cycle is formed |
| Can default static values be seen? | Yes, if the field has not been assigned yet in the initializer | Another thread cannot arbitrarily treat an in-progress class as fully initialized |
| Main risk | Partially initialized state; access order causes unexpected results | Threads make no progress, application hangs |
| How to avoid | Reduce recursive static dependencies; avoid reading fields before they are set | Do not create dependency cycles between initializers, especially in multithreaded execution |

A reference cycle in **code** does not necessarily cause a deadlock. The outcome depends on **which thread initializes which class first**, **at what time**, and **the initializer call path**.

## 8. When Initialization Fails: The Class Can Enter an Erroneous State

Not every initializer finishes successfully. Consider a static field initializer calling a method that throws an exception:

```java
static int value = fail();
```

When an ordinary exception causes initialization to complete abnormally, the JLS requires appropriate throwable handling, usually **wrapping in `ExceptionInInitializerError`**. The class/interface is marked in an **erroneous state**.

Subsequent active-use attempts on **that same runtime class** do not simply re-run the static initializer; they typically lead to **`NoClassDefFoundError`** related to the inability to initialize the class.

### 8.1. Runnable Java 17+ Example: First Attempt Fails, Subsequent Attempts Do Not Retry

Create the file **`FailedInitDemo.java`**:

```java
public class FailedInitDemo {
    static class Broken {
        static int value = initialize();

        static int initialize() {
            throw new IllegalStateException("bad configuration");
        }
    }

    public static void main(String[] args) {
        for (int attempt = 1; attempt <= 2; attempt++) {
            try {
                System.out.println(Broken.value);
            } catch (LinkageError error) {
                System.out.println("attempt " + attempt + ": "
                        + error.getClass().getSimpleName());
            }
        }
    }
}
```

Run:

```bash
javac --release 17 FailedInitDemo.java
java FailedInitDemo
```

**Exact stdout:**

```text
attempt 1: ExceptionInInitializerError
attempt 2: NoClassDefFoundError
```

Explanation:

1. The first read of `Broken.value` triggers initialization of `Broken`. `initialize()` throws `IllegalStateException`, which is wrapped in `ExceptionInInitializerError` per the rules because the original throwable is not an `Error`.
2. `Broken` is marked erroneous.
3. On the second attempt, the JVM does not re-run `initialize()` as if nothing had happened; active use leads to `NoClassDefFoundError`.

**Careful note:** If the initializer failure cause is already a subtype of `Error`, error propagation on the first attempt may differ; not every initialization failure is guaranteed to surface `ExceptionInInitializerError`. If superclass initialization fails, propagation also follows specific branches in the JLS.

### 8.2. When Multiple Threads Are Waiting on a Failed Class

If T1 is initializing class C, T2/T3 are waiting, and then C's initializer completes abnormally:

- The JVM marks C **erroneous**.
- Waiting threads are notified to recheck the state.
- Subsequent usage requests do not return C to an "uninitialized" state; they encounter the appropriate error rule, typically `NoClassDefFoundError`.

One should distinguish **the root cause** in the first initialization attempt from **subsequent symptoms** in logs from other threads.

### 8.3. Can Reflection "Reset a Static Initializer"?

There is no standard Java API to reset an erroneous `Class` back to an "uninitialized" state and re-run `<clinit>` at will. Creating **a new class definition via another class loader** can result in a different class identity, but that is a different runtime class with its own lifecycle/identity, not an in-place "repair" of the old class.

For configuration that may change after startup, avoid placing all external connection operations and unstable validation inside a `static initializer`. Designing controlled explicit initialization is usually easier to retry and monitor for errors.

## 9. Related Mechanisms: Superclasses, Interface Default Methods, and Constant Variables

### 9.1. Superclass Initialization

When the JVM initializes a class, required superclasses are initialized in the proper order (if not already initialized). For example:

```java
class Base {
    static {
        System.out.println("Base initialized");
    }
}

class Derived extends Base {
    static {
        System.out.println("Derived initialized");
    }
}
```

If `Derived` is actively used first and `Base` is not yet initialized, `Base` is normally initialized before `Derived`. This snippet is **illustrative class code**, without a standalone `main`.

### 9.2. Interfaces with Default Methods

In modern Java, initialization of a class also involves **superinterfaces that declare default methods** according to the JLS algorithm, not only the direct superclass. This is a detail often overlooked when debugging `<clinit>` ordering.

Conversely, **initializing an interface** does not automatically force all of its superinterfaces to be initialized merely because of an interface inheritance relationship.

### 9.3. Compile-Time Constants

Example:

```java
class Constants {
    static final int LIMIT = 100;
    static final Integer BOXED = Integer.valueOf(100);
}
```

`LIMIT` is a compile-time constant variable under normal conditions and can be inlined by the compiler. `BOXED` is **not** a constant variable in the same sense, because its initializer is not a constant expression of a primitive/String type per the JLS.

Reading `Constants.LIMIT` from elsewhere may not trigger class initialization of `Constants`; reading `Constants.BOXED` is a qualifying active-use situation. Therefore, using a compile-time constant to "trigger static initialization" is an unreliable approach.

## 10. How Do Class Loaders Affect Initialization Scope?

In the JVM, the runtime identity of a class/interface is tied to **binary name + defining class loader**. Two loaders can define two classes with the same binary name that are **two different runtime types**, each with its own initialization state.

```text
("demo.Cache", LoaderA) → class A, init state A, lock LA
("demo.Cache", LoaderB) → class B, init state B, lock LB
```

Therefore:

- Each class definition has its own initialization managed by the JVM.
- An application server/plugin host may have multiple copies of `demo.Cache` defined by different loaders.
- The static fields of those two runtime classes are **not automatically shared** even if the binary name is the same.
- "A static field is JVM-wide global by class name" is a misconception.

This is why issues involving hot reload, plugin loaders, and static singletons require considering class-loader boundaries as well.

**Do not rely on using a new loader as a general solution for deadlock**: it can create new type identities and more complex linking/API constraints. It is best to fix the initializer dependency design.

## 11. Diagnosing a Process That Appears Hung in `<clinit>`

When an application stops making progress at startup without an obvious exception, one may suspect:

- A static initializer is performing a slow operation / waiting on I/O.
- T1 is initializing class A, T2 requests A and is legitimately waiting.
- T1 and T2 form an A ↔ B wait cycle.
- An initializer holds an application lock and then needs another class, combining with another thread to form a mixed wait cycle (monitor + class initialization).
- A static initializer calls `Future.get()`, `join()`, `CountDownLatch.await()`, or an API waiting on a task that itself requires the class currently being initialized.

### 11.1. Collecting Thread Dumps

With a HotSpot JDK, you can try:

```bash
jcmd <pid> Thread.print
```

In many environments, you can also use:

```bash
jstack <pid>
```

The commands above are **diagnostic operation examples**; replace `<pid>` with the actual PID of the Java process. `jcmd`/`jstack` usually belong to the JDK toolset; output and support may vary by runtime/version.

To investigate:

1. Find threads currently running inside `<clinit>` or methods called by an initializer.
2. Find threads waiting on class initialization, monitors, latches, or joins.
3. Determine the relationship of **which class is being initialized by which thread**.
4. Draw a **wait-for graph**, e.g., `T1 → Class B (T2)` and `T2 → Class A (T1)`.
5. Inspect static field initializers, static blocks, dependency cycles, logging, and I/O inside initializers.
6. Identify class-loader identities as well if multiple loaders create classes with duplicate binary names.

### 11.2. Deadlock Detectors May Not Show All Wait Cycles

Some tools search for deadlocks via **monitors/ownable synchronizers**. Class initialization waiting may not appear like an ordinary monitor lock in every thread dump or tool. Do not conclude "no deadlock" merely because a `findDeadlockedThreads()` report returns null.

Use both stack traces and class initialization information. When necessary, add logging before/after static initialization (in a test environment) to identify which class does not complete.

### 11.3. Logging Class Initialization Properly

On some modern HotSpot JVMs, **Unified Logging** has tags for class loading/initialization; choose the level and tags supported by the actual JVM, checking with:

```bash
java -Xlog:help
```

Do not enforce a fixed combination of tags/levels across all Java implementations. For investigation, one can also log the lifecycle of application components **before** active-use of a class instead of stuffing complex logging into `<clinit>` itself and unintentionally altering deadlock timing.

## 12. Designing to Avoid Circular Dependencies in Static Initializers

### 12.1. Avoid Blocking Operations in `<clinit>`

Risky activities when placed directly inside static initialization:

- Waiting on network/database.
- Waiting on another thread/task with `join()`, `Future.get()`, `await()`.
- Acquiring multiple locks in inconsistent order.
- Initializing another plugin/module that might reference back to the current class.
- Reading configuration that can fail and put the class into an erroneous state, making retries difficult.

Not every such task is forbidden by the JVM. The risk lies in **the initialization mechanism being synchronized and potentially waited on by multiple threads**.

### 12.2. Acyclic Dependency Graph

Instead of:

```text
A.<clinit> → B.<clinit> → A.<clinit>
```

separate responsibilities:

```text
Config values
      |
      v
Service A        Service B
      \            /
       \          /
        explicit startup coordinator
```

Objects can be constructed in an explicit initialization step with ordering, timeouts, and recovery policies. Classes do not need to pull each other into a static initializer cycle during loading.

### 12.3. Initialization-on-Demand Holder: Use Within Its Proper Scope

A common Java idiom:

```java
public final class Service {
    private Service() {}

    private static class Holder {
        static final Service INSTANCE = new Service();
    }

    public static Service getInstance() {
        return Holder.INSTANCE;
    }
}
```

This is an **illustrative class**, not a standalone program. It relies on class initialization to create the singleton when `Holder` is first actively used, following the JVM's synchronization mechanism.

Advantages: lazy initialization, no manual synchronization needed in `getInstance()`, other threads wait properly while initialization is in progress.

**Limitation:** The Holder idiom does **not** automatically resolve dependency cycles between `Holder` and other classes; if `Service`'s constructor invokes initialization code of a class waiting back on it, deadlock can still occur.

### 12.4. Explicit Lifecycle and Retryable Errors

For external resources (database connections, clients, remote configuration), use a startup lifecycle with timeouts and retryable state, rather than putting all connections inside `static final`:

```java
final class ServiceManager {
    private volatile boolean ready;

    public synchronized void initialize() {
        // Load config, connect, check dependencies in a clear order.
        ready = true;
    }

    public boolean isReady() {
        return ready;
    }
}
```

The snippet above **only illustrates API shape** and does not yet handle errors, multiple calls, idempotency, shutdown, or full resource cleanup. The learning point is: **a controllable explicit initialization process** is easier to observe and retry than a failed class initializer that turns a class erroneous.

### 12.5. Avoid Publishing Incomplete Objects from Initializers

Class initialization has its own synchronization guarantees, but **same-thread cycles** can still observe unassigned static fields. Do not publish references to partially constructed static state via callbacks or dependent classes.

If multiple components must reference each other, consider:

- Separating object creation from dependency wiring.
- Using dependency injection or factories.
- Designing invariants to be fully established before the object is published.
- Writing tests for different active-use orders and concurrent startup cases.

## 13. Common Misconceptions

| Misconception | Correct understanding |
| --- | --- |
| “The JVM holds the `SomeClass.class` monitor throughout `<clinit>`.” | `LC` is the specification's initialization lock, mapped per JVM; the procedure marks the state and releases the lock before running the rest of initialization. |
| “Other threads can read static fields while a class is partway through initializing.” | Other threads must follow the rule of **waiting** for a class being initialized by another thread before completing active use. |
| “Circular reference A → B → A always deadlocks.” | Same-thread handles recursive requests by returning normally; default values may be observed. |
| “Cycle A → B → A is always safe.” | Multiple threads can form a real wait cycle. |
| “The initialization lock is the application's `synchronized(SomeClass.class)`.” | There is no such guarantee; do not use the class literal monitor as a replacement API. |
| “Static initializers only ever run when `new`-ing an object.” | Static method/field active use and reflection can trigger it; creating an array of the type does not create instances. |
| “Accessing `static final` always initializes the class.” | Compile-time constant variables have exceptions. |
| “`ClassCircularityError` will resolve a static initialization deadlock.” | Not a general mechanism for wait cycles between static initializers. |
| “Once init fails, the JVM automatically retries next time.” | The runtime class is in an erroneous state; subsequent uses typically encounter `NoClassDefFoundError`. |
| “`ExceptionInInitializerError` is always the first error.” | If the root throwable is a subtype of `Error` or the error originates in a superclass, the propagation path may differ. |
| “A static singleton is shared JVM-wide by default regardless of class loader.” | Same binary name under different loaders can be different runtime classes, each with its own static state. |
| “If a thread dump doesn't report a monitor deadlock, there is no initialization deadlock.” | Class-init waiting is not always detected by tools the same way as a monitor deadlock. |
| “The Holder idiom handles all dependency cycles.” | It only helps lazy init in a simple case and does not automatically eliminate dependency cycles. |
| “Adding `Thread.sleep` in `<clinit>` is a way to stabilize concurrency.” | Sleep alters scheduling, does not redesign dependencies, and can mask the problem. |

## 14. Self-Check Exercises with Answers

**Question 1.** Two threads simultaneously access a non-compile-time-constant `static` field of an uninitialized class. Does the JVM run the initializer twice in parallel?

**Answer:** No. One thread is responsible for initializing the runtime class; the other thread waits or receives the result after the class is initialized.

**Question 2.** Why does the thread currently initializing A not deadlock on itself when A's initializer indirectly calls A?

**Answer:** According to JLS `12.4.2, if A is currently being initialized by that same thread, the recursive initialization request **returns normally**.

**Question 3.** In `RecursiveInitDemo`, why does B receive `A.value == 0`?

**Answer:** `A.value` already has the default value 0 from preparation, while the expression `A.value = calculate()` has not yet completed. The same thread is allowed to continue the recursive init request, so B reads the current value, which is 0.

**Question 4.** Two threads T1/T2 initialize A/B respectively; A needs B and B needs A. What can happen?

**Answer:** T1 waits for B, which is being initialized by T2; T2 waits for A, which is being initialized by T1. This is a **cross-thread class initialization deadlock**.

**Question 5.** Must the lock `LC` be the monitor of the `A.class` object?

**Answer:** No. The specification allows the JVM to decide how to map the initialization lock. Do not use `synchronized(A.class)` as a substitute for the initialization mechanism.

**Question 6.** What happens when class initialization fails with an ordinary exception like `IllegalStateException`?

**Answer:** The first attempt usually throws `ExceptionInInitializerError` wrapping the original exception, and the class is marked erroneous; subsequent active use typically leads to `NoClassDefFoundError`.

**Question 7.** Does creating `new SomeClass[10]` run the constructor of ten `SomeClass` instances?

**Answer:** No. An array object is created, with element references initially null.

**Question 8.** Two separate loaders define a class with the same binary name. Do they share an initialization lock and static fields?

**Answer:** Not by default. These are two different runtime classes, each with its own static state and initialization process.

**Question 9.** Does the Holder idiom guarantee no deadlock even if the singleton constructor calls back into multiple other static classes?

**Answer:** No. It is only a form of lazy initialization relying on the JVM mechanism; dependency cycles can still cause errors/deadlocks.

**Question 10.** Why should the class literal `SomeClass.class` not be used to force a static initializer to run?

**Answer:** A class literal only creates/provides the `Class` object; it is not an active-use operation that forces `SomeClass`'s initializer to run under the corresponding rules.

**Question 11.** Why is the class initialization lock important even though Java source already has `synchronized` and `volatile`?

**Answer:** The JVM must have a mechanism to coordinate **class initialization before necessary first use**, both for bytecode-generated code and across multiple threads. That is a separate runtime responsibility and does not require every class to declare its own monitor or volatile field.

**Question 12.** App startup simply hangs without any `VerifyError`. Could this be an initialization issue?

**Answer:** Yes. Bytecode can still be valid while multiple static initializers wait on each other. Check thread dumps, `<clinit>`, init dependencies, and blocking points.

## 15. Operational Checklist and Summary

When writing or reviewing class initialization:

1. Identify static field initializers and static blocks that can trigger other classes.
2. Map dependency relationships A → B → C; watch for cycles returning to the starting class.
3. Flag code paths that may run on multiple threads at startup.
4. Avoid blocking I/O, `join`, `await`, and complex lock synchronization inside `<clinit>`.
5. Do not rely on an "accidental" first active-use order to achieve invariants.
6. If initialization can fail due to external factors, consider an explicit lifecycle with timeout/retry.
7. When seeing `ExceptionInInitializerError` or `NoClassDefFoundError`, find the **first initialization attempt** and root cause.
8. When startup hangs, collect thread dumps, build a wait-for graph, and inspect `<clinit>`.
9. For plugins/application servers, identify the **defining class loader**, because the same class name does not guarantee the same class identity.
10. Test different init orders, concurrent startup, and failure paths.

**Three most important conclusions:**

- The JVM synchronizes class initialization using states and the initialization lock `LC`; other threads may have to wait for a class currently being initialized by another thread.
- Recursive initialization **within the same thread** does not wait for itself; this can allow code to observe the default value of a static field not yet assigned.
- Circular initialization dependencies **across multiple threads** can lead to **real deadlock**. Sustainable solutions lie in dependency and lifecycle design, not in bypassing the JVM's synchronization mechanism.

### Official Specifications

- [JLS 12.4.1 — When Initialization Occurs (Java SE 17)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.1): active use, superclass/default-interface initialization, and constant variables.
- [JLS 12.4.2 — Detailed Initialization Procedure (Java SE 17)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2): initialization lock `LC`, states, same-thread recursion, wait/notify, and failure.
- [JVMS 5.5 — Initialization (Java SE 17)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5): class/interface initialization at the JVM level.
- [JVMS 5.4 — Linking (Java SE 17)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4): distinguishing verification, preparation, and resolution.
- [JLS 17 — Threads and Locks (Java SE 17)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): synchronization, visibility relationships, and the Java Memory Model.
- [CountDownLatch — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): barrier used in the thread experiments in this article.
