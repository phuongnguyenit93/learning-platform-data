# Deadlock When Multiple Loaders Cross-Delegate

A custom `ClassLoader` can ask another class loader to find a class. This is necessary in plugin systems, application servers, OSGi, or architectures with multiple class-loading spaces. However, if **loader A holds its own class-loading lock and calls loader B**, while at the same time **loader B holds its own lock and calls back into loader A**, the two threads can wait on each other forever: **deadlock**.

Unlike `ClassNotFoundException` (class not found) or `ClassCastException` (type incompatibility), a deadlock typically causes the program to **hang at the class-loading step**, without advancing to the statements to be executed, and sometimes without printing any exception. The issue may only appear when loading plugins concurrently or when startup is optimized to run across multiple threads.

The focus of this lesson is the **relationship between the class-loading lock, delegation order, and the loader dependency graph**. It is important to clearly understand the risks in both regular loaders (loader-wide lock) and **parallel-capable** loaders (per-class-name lock): registering as parallel-capable can reduce unnecessary contention, but **does not automatically fix an actual delegation cycle**.

## 1. Which Locks Contribute to a Deadlock?
`ClassLoader.loadClass(name, resolve)` by default synchronizes on `getClassLoadingLock(name)` throughout the cycle `findLoadedClass` → parent/bootstrap → `findClass` → optional `resolveClass`. A loader not registered as parallel-capable uses the **monitor on the loader instance itself**; a registered loader uses a **per-binary-name lock**. Both must still coordinate so as not to call `defineClass` twice for the same name.
A deadlock occurs when **two threads hold two locks that the other needs**. In a cross-delegation model, a request can go from loader A to B while still holding lock A, and from B back to A while holding lock B. The following sections demonstrate the circular wait with a controlled program, and then analyze why per-name locking only reduces part of the risk.

## 2. How Deadlock Forms When Two Loaders Cross-Delegate

Suppose A and B have a policy of looking up classes through each other:

~~~text
           Thread T1                              Thread T2

     holds loader A lock                    holds loader B lock
             |                                      |
             v                                      v
    A.loadClass("lab.A")                    B.loadClass("lab.B")
             |                                      |
             v                                      v
  calls B.loadClass("lab.B")              calls A.loadClass("lab.A")
             |                                      |
             v                                      v
      WAITS for lock B                       WAITS for lock A
             |                                      |
             +---------------+----------------------+
                             |
                      CIRCULAR WAIT
                         DEADLOCK
~~~

T1 does not release lock A until B returns a result. T2 does not release lock B until A returns a result. If both monitors are held and both cross calls happen concurrently, neither thread can proceed.

One way to model this is with a **wait-for graph**:

~~~text
T1 holds A, wants B:    T1 ──wait-for──► T2
T2 holds B, wants A:    T2 ──wait-for──► T1

Cycle T1 → T2 → T1 → deadlock
~~~

The word "concurrently" here is important: with a single thread, a logical delegation cycle A→B→A can manifest as **infinite recursion / StackOverflowError** rather than a monitor deadlock, depending on how the loaders check their caches and report errors. With two threads holding locks in opposite orders, the same dependency graph can become a deadlock.

Not every case where A calls B and then B calls A immediately deadlocks. If a request is resolved by an already-loaded class, a valid parent, or a terminating fallback, there may be no cross-wait. The problem lies in a **delegation graph that does not guarantee termination** and in the lock acquisition order across threads.

## 3. Java 17 Example: Reproducing a Deadlock with Two Custom Loaders

This example **intentionally creates a real deadlock** at the Java monitor level to illustrate the mechanism; it requires no external ClassFile and defines no application classes. We create two `ClassLoader` subclasses that are **not registered as parallel-capable**, with each loader holding its monitor while calling the other loader.

So that the program **does not hang when test-run**, the two threads participating in the deadlock are marked `daemon`. The main thread simply confirms that both have entered the locked region and prints the result, after which the JVM can exit even though the two daemon threads are BLOCKED. This is a demonstration for learning purposes; **this cross-delegation structure must not be used in a real application**.

Create the file **`CrossLoaderDeadlockDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;

public class CrossLoaderDeadlockDemo {
    static final class CrossingLoader extends ClassLoader {
        private final String requestedName;
        private final CountDownLatch bothHoldingLocks;
        private CrossingLoader peer;

        CrossingLoader(String requestedName,
                       CountDownLatch bothHoldingLocks) {
            super(null);
            this.requestedName = requestedName;
            this.bothHoldingLocks = bothHoldingLocks;
        }

        void setPeer(CrossingLoader peer) {
            this.peer = peer;
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            synchronized (getClassLoadingLock(name)) {
                if (name.equals(requestedName)) {
                    bothHoldingLocks.countDown();

                    try {
                        bothHoldingLocks.await();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        throw new ClassNotFoundException(name, e);
                    }

                    // Cross-call while still holding this loader's own monitor.
                    return peer.loadClass(peer.requestedName);
                }

                return super.loadClass(name, resolve);
            }
        }
    }

    private static void request(CrossingLoader loader, String name) {
        try {
            loader.loadClass(name);
        } catch (ClassNotFoundException e) {
            throw new IllegalStateException(e);
        }
    }

    public static void main(String[] args) throws Exception {
        CountDownLatch bothHoldingLocks = new CountDownLatch(2);

        CrossingLoader loaderA =
                new CrossingLoader("lab.A", bothHoldingLocks);
        CrossingLoader loaderB =
                new CrossingLoader("lab.B", bothHoldingLocks);

        loaderA.setPeer(loaderB);
        loaderB.setPeer(loaderA);

        Thread threadA = new Thread(
                () -> request(loaderA, "lab.A"), "load-A");
        Thread threadB = new Thread(
                () -> request(loaderB, "lab.B"), "load-B");

        // Daemon: avoid keeping the JVM alive forever in this intentional deadlock example.
        threadA.setDaemon(true);
        threadB.setDaemon(true);

        threadA.start();
        threadB.start();

        // Proceed only once both threads are holding their own locks.
        bothHoldingLocks.await();

        // Thread A must acquire lock B, and thread B must acquire lock A.
        // Neither can complete while still holding its current lock.
        threadA.join(100);
        threadB.join(100);

        System.out.println("Crossed delegation deadlocked: "
                + (threadA.isAlive() && threadB.isAlive()));

        ClassLoader sharedParent =
                ClassLoader.getPlatformClassLoader();

        ClassLoader safeA = new ClassLoader(sharedParent) { };
        ClassLoader safeB = new ClassLoader(sharedParent) { };

        boolean sameRuntimeType =
                safeA.loadClass("java.lang.String")
                        == safeB.loadClass("java.lang.String");

        System.out.println("Shared parent String identity: "
                + sameRuntimeType);
    }
}
~~~

Compile and run with **JDK 17+**:

~~~bash
javac --release 17 CrossLoaderDeadlockDemo.java
java CrossLoaderDeadlockDemo
~~~

**Expected stdout according to the synchronization logic in the example:**

~~~text
Crossed delegation deadlocked: true
Shared parent String identity: true
~~~

**Explanation of each part:**

1. The two loaders `loaderA` and `loaderB` belong to a subclass without `registerAsParallelCapable`, so `getClassLoadingLock(name)` returns the loader lock. Each thread acquires a different monitor.
2. `CountDownLatch(2)` ensures that both threads have entered their respective loader's monitor before proceeding. This is not a circular wait on the latch: the second `countDown()` brings the latch to 0 and **wakes both up**.
3. After the latch, thread A still holds lock A and calls `loaderB.loadClass("lab.B")`; thread B still holds lock B and calls `loaderA.loadClass("lab.A")`. Each cross call needs the monitor held by the other side: a **deadlock** forms.
4. `join(100)` only waits up to 100 ms per thread and **does not resolve the deadlock**. Both threads are still alive, so the first line is `true`.
5. Both threads are marked `daemon` **before starting**, allowing the JVM to exit when the main thread finishes. In a real application, marking threads as daemon is **not a fix for a deadlock**.
6. The two loaders `safeA` and `safeB` share a common parent to load `java.lang.String`. They are written with the default `ClassLoader` without creating cross-delegation; the returned class is the same `String.class`, so the second line is `true`.

Note the goal of the demo: **to prove lock contention**, not to build a valid ClassFile or a production-ready class loader. The names `lab.A` / `lab.B` are used as triggers before looking up a ClassFile; the two threads block on the monitors, so no `A.class` or `B.class` needs to exist on disk.

### Why Does the Main Thread Not Hang Along with the Two Loaders?

The main thread does not invoke the two deadlocked loaders. It only waits for the latch to open and attempts a timed `join`. Because T1/T2 are daemon threads, the JVM can terminate when only daemon threads remain. If they were changed to **non-daemon** without breaking the delegation cycle, the JVM would typically not exit. That is why the example intentionally isolates the failure in daemon threads; do not infer that this approach protects a real system.

## 4. Does registerAsParallelCapable Help?

Java provides:

~~~java
static {
    ClassLoader.registerAsParallelCapable();
}
~~~

This is a **fragment inside the body of a ClassLoader subclass**; in a real application, it should be called once in the subclass's static initializer and superclass requirements should be checked according to the API. This protected static method is not a public call to be invoked arbitrarily from an unrelated class.

**What problem does parallel-capable solve?**

- When a loader is not parallel-capable, multiple threads loading **two different class names** may still have to wait on **a single loader monitor**.
- When parallel-capable, `getClassLoadingLock(name)` provides a **per-name lock** that allows loading different names to proceed in parallel, reducing certain bottlenecks or loader-wide locking cases.
- It does not automatically change the `parent-first`/`child-first` policy, create new paths between loaders, or fix class dependency cycles.

**Important: parallel-capable is not a cure-all for every deadlock.** If T1 holds the lock for `A` on loader A and needs `B` from loader B, while T2 holds the lock for `B` on loader B and needs `A` from loader A, then even **per-name** locks still form a circular wait on those exact two locks. In addition, a custom loader may itself hold a monitor, a `ReentrantLock`, a global cache, or a framework lock when calling into another loader.

You should not register as parallel-capable without verifying the thread-safety of:

- Bytecode caches, ClassFile maps, package/`ProtectionDomain` metadata, and resource sources.
- `findClass`, `loadClass` overrides, fallback/resolve methods, and custom locks.
- The load-exactly-once policy per binary name, avoiding races that lead to `LinkageError`.
- Deadlocks caused by loaders A/B cross-calling each other, along with locks outside `getClassLoadingLock`.

Practical rule: **design an acyclic delegation graph** first, and only then consider parallel loading as a concurrency optimization/correctness measure when needed.

## 5. How Does One-Way Parent Delegation Differ from a Cross-Call Cycle?

A **typical safe graph** is a one-way tree/DAG:

~~~text
Plugin-A loader ──► Shared API loader ──► Platform/Bootstrap
Plugin-B loader ──► Shared API loader ──► Platform/Bootstrap

There is no edge from Shared API loader back to Plugin-A/Plugin-B.
~~~

Both plugins can isolate their implementations while sharing a single API definition. For the same contract name, the parent loader is the **common defining loader**, avoiding `ClassCastException` caused by duplicate APIs.

**Dangerous graph:**

~~~text
Plugin-A loader ──► Plugin-B loader
        ▲                 |
        |                 ▼
        +─────────────────+
~~~

Even with fallback logic, the mechanism "if A cannot find it, ask B; if B cannot find it, ask A" may have no termination point. If two threads load concurrently, the deadlock risk is very high; if on a single thread, infinite recursion can occur.

Some plugin systems require **cross-plugin visibility**. Instead of letting two loaders query each other freely:

1. Place the **shared API** in a common parent loader without containing private implementations.
2. Define a **registry/route lookup** by package or module name, ensuring each request has an **owner** or a terminating lookup path.
3. If forwarding across multiple loaders is necessary, maintain a **visited set / cycle detection** at the appropriate coordination layer and fail explicitly when a cycle is encountered, rather than recursing infinitely.
4. Do not invoke arbitrary plugin code while holding a broad class-loading lock.
5. Do not alter type identity by asking another loader and then calling `defineClass` with the same bytes in the current loader; that will be a **second definition** with a different identity.

**Note:** Java does not require every custom loader to always have strictly a single parent path and no external interaction. However, when designing cross-loader class lookup paths, you must ensure that lookup branches **can terminate** and follow proper ownership and synchronization rules.

## 6. Which Real-World Scenarios Are Prone to Deadlock?

### 6.1. Two Plugins Directly Referencing Each Other's Implementations

Plugin A attempts to load `plugin.b.Helper` through loader B; at the same time, B attempts to load `plugin.a.Adapter` through loader A. If each loader holds a broad lock while calling into the other, a circular wait can form.

How to improve: have both call through a **shared interface/API**, exchange data via shared DTOs, or use a service registry with a clear lifecycle. Avoid hard-to-control cross-implementation dependencies.

### 6.2. Hand-Rolled "Peer Loader" Delegation in a Child-First Loader

A custom loader may write:

~~~java
// Anti-pattern fragment: no loop/cycle prevention mechanism yet.
try {
    return findClass(name);
} catch (ClassNotFoundException missing) {
    return peerLoader.loadClass(name);
}
~~~

If `peerLoader` also does the same and asks back to the first loader when a class is not found, it creates an A→B→A cycle. This fragment does not show complete handling of `findLoadedClass`, locks, or `resolveClass`; it only illustrates the risky policy.

**Do not swallow all `LinkageError`s and fall back to a peer**: a definition/linkage error is not equivalent to "the class is absent from this source". Catching exceptions too broadly can hide corrupted bytecode or type identity conflicts.

### 6.3. Class Initialization Overlapping with Class Loading

A `static initializer` can invoke other code/plugins, triggering new class loading. A deadlock can also come from the **class initialization lock**, a static cache lock, or an application lock, not just the class loader's monitor. For example, one thread holds an application lock and uses a class that needs initialization, while another thread is initializing that class and wants the application lock.

Therefore, it is necessary to distinguish between a **class-loading lock deadlock** and a **class-initialization deadlock**. The two types may look similar in "hung while using a class" logs, but their thread dumps and awaited locks can differ.

### 6.4. Thread Pools and Parallel Startup

In an application with multiple workers, the bug can be difficult to reproduce:

- When running single-threaded, one class lookup branch may complete or fail before another.
- When starting multiple plugins simultaneously, two threads can concurrently hold their respective loader locks and call each other.
- Different runs have different class initialization and cache timing, causing the error to appear inconsistently.
- Changing the thread count or timing may make the bug "temporarily disappear" but **does not eliminate the delegation cycle**.

You should not fix it with `Thread.sleep`, increasing timeouts, or shrinking the pool size and assuming the bug is gone; that only alters scheduling. The goal is to **eliminate the circular wait or establish an explicit lock ordering**.

## 7. Diagnosing with Thread Dumps and JVM Tools

When an application hangs during class loading:

1. Record which threads are BLOCKED/WAITING and their stack traces at `ClassLoader.loadClass`, `findClass`, `getClassLoadingLock`, synchronized blocks, or plugin code.
2. Capture a **thread dump** during the hang. With standard HotSpot/JDK, you can use the command:

~~~bash
jcmd <PID> Thread.print -l
~~~

Replace `<PID>` with the process ID of the JVM to inspect; this is a placeholder in a **tool command**, not a Java snippet to compile. Another option:

~~~bash
jstack -l <PID>
~~~

Tool availability may vary depending on the JDK distribution, OS, and process permissions. Do not run them in monitoring-restricted environments without authorization.

3. Look for lines describing a thread waiting for a monitor held by another thread, then cross-reference the monitors of `LoaderA` and `LoaderB`.
4. If the JVM detects a Java-level circular wait, the thread dump may include a section such as **"Found one Java-level deadlock"**. Not every hang scenario is automatically detected by this tool.
5. Inspect the class loader model and fallback policy: which name does loader A want from B, which name does loader B want from A; is there a termination path or clear class owner?
6. Check locks **outside the loader** (registry cache lock, framework synchronization, `<clinit>`, plugin locks); the class-loading lock is not necessarily the only cause.
7. Reproduce the issue in tests using a latch/barrier instead of `sleep`, to guarantee the order in which the two threads acquire locks as in the example above.

### Using ThreadMXBean When Needed

Java provides `java.lang.management.ThreadMXBean` to query deadlocks involving **object monitors** and, depending on the runtime/API, **ownable synchronizers**.

Example **fragment** (for illustration only; does not set up a deadlock itself):

~~~java
java.lang.management.ThreadMXBean bean =
        java.lang.management.ManagementFactory.getThreadMXBean();

long[] deadlocked = bean.findDeadlockedThreads();

if (deadlocked != null) {
    System.out.println("Deadlocked thread count: "
            + deadlocked.length);
}
~~~

`findDeadlockedThreads()` can return `null` if no cycle is detected at the time of the call. It does not guarantee detection of every form of circular wait at the application level, JNI, I/O, `CountDownLatch`, or class initialization, so you need to inspect stack traces and the actual lock hierarchy. Specifically, in the `CrossLoaderDeadlockDemo` example, the threads hang due to **two loader monitors**; taking a snapshot at the right moment may detect it, though it is not required to prove the deadlock.

**Details that help distinguish:**

| Symptom | Investigation clue |
| --- | --- |
| Both threads are `BLOCKED` and each holds a monitor the other loader needs | Suspected monitor/cross-delegation deadlock. |
| `WAITING` on class initialization | Could be a class initialization cycle or waiting on another task; do not jump to concluding a loader lock. |
| One long-running thread with a repeating `loadClass→findClass→peer.loadClass` stack | Likely **infinite delegation recursion** on a single thread. |
| Fast and deterministic `ClassNotFoundException` | Usually a missing-class lookup path, not a deadlock. |
| `LinkageError` during concurrent loading | Could be duplicate definitions or loader constraints; do not treat as a deadlock just because both occur during loading. |
| Hangs only after redeploy | Check for old class loaders retained by threads, caches, registries, and callbacks. |

## 8. Prevention and Remediation

### 8.1. Prefer an Acyclic Loading Graph

Parent delegation from plugins to a shared API/runtime usually creates a controllable, one-way directed graph. Move shared classes/APIs into a **higher or independent and stable** loader, and do not force a parent loader to query back down to a child loader for dependencies.

### 8.2. Unify Ownership for Each Binary Name

For `com.acme.api.*`, designate a single shared defining loader. For `plugin.a.impl.*` or `plugin.b.impl.*`, designate separate loaders. If a request falls outside a loader's scope and has no terminating route, throw `ClassNotFoundException` rather than querying peers endlessly.

### 8.3. Do Not Hold Broad Locks When Calling Uncontrolled Loaders

If custom code adds `synchronized (this)`, `synchronized (registry)`, or a global lock around cross-lookups, consider narrowing the critical section. However, **do not arbitrarily remove the standard class-loading lock**: the check-loaded, define, and resolve operations must still obey the JVM contract. A better approach is to design one-way routes and avoid arbitrary callbacks while holding locks.

### 8.4. Use Parallel-Capable When Thread-Safety Is Truly Satisfied

Registering as parallel-capable can reduce contention for **different** class names, but you must verify all shared loader state and **not treat it as a fix for an A→B→A cycle**. If a cycle exists across the very classes being loaded, per-name locks can still deadlock.

### 8.5. Block Cycles at the Coordination Layer and Fail Fast

If the architecture must perform lookups across multiple sources, you can build a resolver with a pre-validated graph, or track the traversal path `A → B → C` and reject revisited loaders/names according to appropriate logic. Do not rely on a simple `ThreadLocal` as the sole safeguard against a deadlock **between two threads**: each thread may only see one half of the cycle and miss the cross-thread wait relationship.

### 8.6. Write Concurrency Tests

- Create a scenario where two threads start requesting two loaders simultaneously using `CountDownLatch`/`CyclicBarrier`.
- Use a timeout in the **test harness** and capture a thread dump if the timeout is exceeded.
- Verify that the returned class has the expected defining loader and that no `LinkageError` occurs due to duplicate definitions.
- Test the success path, missing classes, plugin restart/redeploy, and shutdown.
- Use a model with a shared API and two separate implementations to verify that class loaders do not query each other infinitely.

For tests that intentionally create a deadlock, run them in an **isolated process** or with daemon threads as in the example, so as not to hang the entire test suite. Do not put intentional deadlock code into production loaders.

## 9. Misconceptions to Avoid

**"ClassLoader has only one global lock across the JVM."** No. The class-loading and locking mechanism depends on the loader and whether it is parallel-capable; in a non-parallel-capable loader, the default lock is tied to the **loader instance**, not a single monitor shared across all loaders in the JVM.

**"registerAsParallelCapable fixes all deadlocks."** No. It enables per-name locking and reduces contention, but **it does not resolve a circular wait between two specific locks** or external locks.

**"Having a common parent guarantees all types always share the same identity."** No. The parent must actually define that class. If each child still defines the same binary name itself, they are two distinct types; the delegation policy must be applied consistently.

**"If there is only one thread, there is no problem."** No. A *deadlock between two threads* may not occur, but a delegation cycle without a stopping point can cause infinite recursion or other failures.

**"Just increase the timeout or reduce the thread count."** This may mask the execution schedule that triggers the deadlock, without fixing the cyclic dependency graph.

**"The class initialization lock is the same as the loader's monitor."** No. The class initialization procedure has its own synchronization mechanism according to the JVM. Read the thread dump to identify the type of lock involved.

**"Catching all load errors and trying another loader is safe."** No. `ClassFormatError`, `LinkageError`, `NoClassDefFoundError`, or initialization errors may indicate serious code or dependency issues, and are not equivalent to `ClassNotFoundException` for blind fallback.

## 10. Self-Check

**Question 1.** T1 holds loader A's monitor and waits for monitor B; T2 holds loader B's monitor and waits for monitor A. What phenomenon is this?

**Answer:** **Deadlock** caused by circular wait; neither can complete while each thread holds the lock the other needs.

**Question 2.** What kind of lock does a non-parallel-capable `ClassLoader` typically return from `getClassLoadingLock(name)`?

**Answer:** The loader instance itself, meaning all class names in that loader share the same default monitor.

**Question 3.** Does switching to parallel-capable guarantee the elimination of cross-delegation A/B deadlocks?

**Answer:** No. If the requests form a circular wait on two per-name locks, a deadlock can still occur.

**Question 4.** If A asks B, and B fails to find it and asks back to A on a single thread, is a monitor deadlock guaranteed to occur?

**Answer:** No. A monitor lock on the same thread is reentrant; a path with no stopping point can recurse forever and eventually cause a `StackOverflowError` or another failure.

**Question 5.** When designing two plugins with a shared API and separate implementations, where should the classes be placed?

**Answer:** The shared API is defined by a shared/parent loader; implementations are placed in each plugin's own loader. Restrict cross-implementation lookups and ensure the directed delegation graph does not form cycles.

**Question 6.** Should you remove `synchronized` around all `loadClass` methods to fix hangs?

**Answer:** No. Arbitrarily removing synchronization can cause races or duplicate definitions. You must fix the cross-call graph and implement thread-safety and parent delegation/parallel loading according to the contract.

## Key Takeaways

**Deadlock when multiple loaders cross-delegate** occurs when class-loading threads hold different **class-loading locks** and wait in turn for the other loader's lock. To avoid this, **eliminate delegation cycles**, establish the defining loader that owns each class/API, use a parent/shared loader for common contracts, restrict cross-loader lookups, and verify concurrency with thread dumps. **Parallel-capable improves concurrent loading capability, but it does not replace an acyclic graph design.**

**Official documentation:**

- Java SE 17 API, `ClassLoader`: `loadClass`, `getClassLoadingLock`, and `registerAsParallelCapable` — https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java Virtual Machine Specification §5.3 — *Creation of Classes and Interfaces* — https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- Java SE 17 API, `ThreadMXBean` — https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html
- Java SE 17 API, `CountDownLatch` — https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html
- Java SE 17 API, `Thread` — https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html
