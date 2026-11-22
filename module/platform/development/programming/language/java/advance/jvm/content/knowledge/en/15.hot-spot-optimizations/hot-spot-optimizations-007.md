# Eliminating Unnecessary Locks When an Object Is Not Shared

## 1. The problem: why does code with `synchronized` sometimes run without executing a lock?

In Java, the **`synchronized`** keyword provides a monitor locking mechanism and **happens-before** relationships according to the Java Memory Model (JMM). Having the `synchronized` keyword in Java source/bytecode **does not mean every execution on HotSpot is required to perform full monitor operations at the machine code level**.

When the **HotSpot C2 JIT compiler** proves that a monitor only protects an object that **cannot be shared in a way that leads to contention between threads**, it can **eliminate unnecessary locking operations** (*lock elimination*, also called *lock elision* in this context).

Basic example:

```java
static int calculate(int x) {
    Object privateLock = new Object();
    synchronized (privateLock) {
        return x * 3 + 1;
    }
}
```

At the source level:

1. Each call to `calculate` creates a new monitor object.
2. `privateLock` is not returned outside, not written to a field/static field, and not passed to another thread.
3. No other thread has a valid reference to request locking **that exact monitor object** while the object is used.
4. HotSpot can prove the condition and remove the **monitor enter/exit** operations in optimized machine code.

This does **not** mean Java ignores `synchronized` arbitrarily. This is an optimization **only valid when the compiler has sufficient proof**, and must preserve all observable behavior of the program.

### 1.1. Summary before diving deeper

- **Object does not escape and is not shared:** the lock may be redundant; C2 can eliminate it.
- **Object is shared between threads:** synchronization may be needed for **mutual exclusion, atomicity, and visibility**; it is not automatically removed.
- **Bytecode still has monitor instructions:** the JIT can eliminate them from **optimized machine code**, without needing to modify the `.class` file.
- **Do not write logic that depends on whether the optimization occurs:** HotSpot may not eliminate the lock when it does not inline enough, the profile is not yet hot, or the compiler cannot prove it.
- **Not the same thing as biased locking, lock coarsening, or scalar replacement**, although these optimizations are related.

This article focuses on HotSpot/JDK 17+ (especially C2) and clearly distinguishes **required Java semantics** from **implementation-specific optimizations**.

## 2. How do monitors and `synchronized` work semantically?

Java provides two common ways to use an intrinsic monitor:

```java
synchronized (someLock) {
    updateSharedState();
}
```

and:

```java
synchronized void update() {
    // locks the implicit monitor of this
}
```

These are **illustrative snippets**, without declaring `someLock`, `updateSharedState`, or a full class.

### 2.1. Mutual exclusion

Every Java object has a semantically associated monitor. If two threads try to **acquire the same monitor** via the `synchronized` mechanism, the JVM must obey mutual exclusion and monitor rules: at one time one thread holds ownership of that monitor (with **reentrant** capability for the same thread).

This helps protect *read-modify-write* operations on shared data, for example `count++` is not an atomic increment when proper synchronization is missing.

### 2.2. Visibility and happens-before

The **unlock of monitor M** *happens-before* the subsequent **lock of M** according to the JMM rules. Thanks to that, writes properly published through the monitor can be observed by a thread acquiring the same monitor according to the happens-before relationship.

Crucially: as long as a monitor is used exclusively for an object where **no second thread can participate in communication through that monitor**, the synchronization effects with other threads may **have no real effect**. The compiler can eliminate monitor operations when proving the relevant constraints are unnecessary, **but must not eliminate synchronizations that a valid program uses to share data**.

### 2.3. Reentrancy

A thread currently holding a monitor can acquire **the same monitor** again; the JVM must manage the reentrant level of synchronization semantically correctly.

Example:

```java
synchronized (lock) {
    synchronized (lock) {
        operation();
    }
}
```

This is an **illustrative snippet**; `lock` and `operation` must be defined. If the lock object is actually shared, locking operations may need to be preserved semantically; **nested lock elimination** optimizations are a separate topic, not proving the monitor is thread-private.

### 2.4. Synchronization still matters even when no data race is seen in testing

A program can "run correctly" 1,000 times missing a lock and still have a data race. HotSpot **must not** infer a lock is redundant just because a benchmark run had no contending threads.

The difference between **no observed contention** and **the compiler having proof that the object cannot be shared** is the core of lock elimination.

## 3. Distinguishing the lock object and the protected data

In the code:

```java
static final Object LOCK = new Object();
static int counter;

static void increment() {
    synchronized (LOCK) {
        counter++;
    }
}
```

`LOCK` is the **monitor object**, while `counter` is the **protected data**. Because `LOCK` resides in a static field, multiple threads can access the same monitor instance.

Do not reason "`LOCK` has no fields so the JIT will surely eliminate it". Having no fields does not make a shared monitor redundant. `synchronized` takes effect **by monitor identity**, not by the number of fields in the object.

Conversely:

```java
static int computeLocally(int x) {
    Object lock = new Object();
    synchronized (lock) {
        return x + 7;
    }
}
```

this monitor is created inside the method, not made public/published, so it is a good candidate for eliminating monitor operations. The result does not involve other threads because they cannot acquire that exact object through any reference.

### 3.1. A design bug: creating a new lock every time to protect static state

```java
static int unsafeCount;

static void unsafeIncrement() {
    Object lock = new Object();
    synchronized (lock) {
        unsafeCount++; // DOES NOT protect shared state between threads
    }
}
```

This is an **anti-pattern**, not a thread-safe example. Each call uses **a different object**. Two threads do not synchronize on **the same monitor**, so `unsafeCount++` still has data races/lost updates.

HotSpot may eliminate the lock, but **the correctness bug already exists in the source**. Do not solve it by "disabling escape analysis to keep the monitor", because a newly created monitor each time still does not protect static data between threads.

Rather, use a **shared monitor** or an appropriate atomic mechanism:

```java
static final Object COUNT_LOCK = new Object();
static int count;

static void safeIncrement() {
    synchronized (COUNT_LOCK) {
        count++;
    }
}
```

To protect the same resource, threads must synchronize on **the same monitor object**.

## 4. Escape analysis sets the condition to eliminate locks

To decide whether monitor enter/exit can be removed, C2 must prove the lock **is not needed to preserve synchronization and observable behavior**. HotSpot escape analysis (EA) helps identify objects that can be shared or escape outside the compiled scope. In implementation terminology, **NoEscape**, **ArgEscape**, and **GlobalEscape** describe different levels of escape; they are **not** a public Java API guarantee that the monitor will definitely be eliminated.

A local variable can still point to an object already published to a static field; conversely, the compiler can see through helper calls when **inlining** expands the analysis scope. Therefore "local object" does not by default mean "unnecessary monitor", and an object **not escaping the thread** is still not enough if the compiler cannot prove certain other conditions.

**Specific point of the lock elimination article:** the compiler can remove **unobservable locking operations** but must preserve `synchronized` rules, exceptions, happens-before, and identity when sharing actually occurs. Scalar replacement can support or accompany it, yet an allocation being eliminated **is not identical** to a monitor being eliminated; the previous article focused on escape states and the object/scalars model.

## 5. How HotSpot eliminates locks

A reasonable diagram for the private monitor example:

```text
Java source
  Object lock = new Object();
  synchronized (lock) { result = x * 3 + 1; }
                 |
                 v
javac generates bytecode containing monitorenter/monitorexit
                 |
                 v
HotSpot interpreter/C1/C2 execution
                 |
            method becomes hot
                 |
                 v
       C2 inlining / escape analysis
                 |
      can the compiler prove
      the object cannot globally escape?
            /                \
          Yes                 No
          |                    |
          v                    v
   Can eliminate          Keep full monitor
   monitor operations     runtime semantics
          |
          +-- is the object scalar-replaceable?
                /           \
              Yes            No
              |                |
              v                v
       Can eliminate       Object allocation
       object allocation   may still remain
```

This is a **conceptual** model, not promising every HotSpot release executes the passes in that exact simple order. EA can fail due to analysis limits, non-inlined calls, exception paths, or other conditions.

### 5.1. What does the compiler eliminate?

When safe, the compiler can eliminate the cost of:

- Monitor enter/exit on the optimized path.
- Monitor-related checks/bookkeeping if proven redundant.
- In cases where the object is scalar-replaced, even the allocation of the monitor object.
- Internal operations related to object header/locking that are no longer needed.

However, **generating/eliminating machine instructions** depends on the JIT build. Java source and bytecode still have `synchronized`/`monitorenter`/`monitorexit`.

### 5.2. Exception correctness must still be preserved

If code inside the critical section throws an exception, the Java compiler generates exception paths to **release the monitor** according to semantics. The JIT can optimize paths proven not to need the monitor, but exception propagation must be correct.

Do not assume removing the monitor means skipping exception handling or side effects of the body.

### 5.3. Compilation does not run interpreter and C2 at the same time

A method may initially be interpreted, then C1, and finally C2. **There is no guarantee of JIT level 4** after exactly 10,000 invocations. Therefore the same source code can see different runtime lock costs during warm-up and steady state.

## 6. `synchronized` in bytecode is still present

Consider the method snippet:

```java
static int localCriticalSection(int value) {
    Object privateLock = new Object();
    synchronized (privateLock) {
        return value * 3 + 1;
    }
}
```

Compile with `javac`, use:

```bash
javap -c -p LockElisionDemo
```

The bytecode for the synchronized block has **`monitorenter`** and **`monitorexit`**, along with an exception-handling path to ensure monitor exit on error. A logical pattern:

```text
... new java/lang/Object
... dup
... invokespecial java/lang/Object.<init>
... astore ...
... monitorenter
... iload ...
... imul
... iadd
... monitorexit
... ireturn
... monitorexit   // exception handling branch
... athrow
```

**This is an illustrative diagram, NOT a full bytecode dump from a specific compiler version.** Instruction offsets/local slots/exception table entries change when code/`javac` changes.

### 6.1. Why does `javap` not prove the lock still operates on the CPU?

`javap` only reads **class file bytecode**. C2 compiled machine code is generated **while the JVM is running**; that optimization does not modify the class file. Therefore seeing `monitorenter` in `javap` **does not refute lock elimination in the JIT**.

### 6.2. Why can the same bytecode execute differently?

The interpreter needs to execute monitor semantics according to bytecode. The C2 JIT can look at the entire control flow and escape state, and then choose an equivalent but cheaper machine code path.

A program running with `-Xint` or JIT disabled can have different locking costs; there is no requirement that two execution modes emit the same number of machine instructions, only that Java semantics are preserved.

## 7. Runnable Java 17+ example: private monitor and shared monitor

Create the file **`LockElisionDemo.java`**:

```java
public final class LockElisionDemo {
    private static final Object SHARED_LOCK = new Object();
    private static int sharedCount;
    private static volatile long checksumSink;

    static int localCriticalSection(int value) {
        Object privateLock = new Object();
        synchronized (privateLock) {
            return value * 3 + 1;
        }
    }

    static void incrementShared() {
        synchronized (SHARED_LOCK) {
            sharedCount++;
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        long total = 0;

        for (int i = 0; i < 100_000; i++) {
            total += localCriticalSection(i);
        }

        checksumSink = total;
        System.out.println("local checksum=" + checksumSink);

        Thread first = new Thread(() -> {
            for (int i = 0; i < 20_000; i++) {
                incrementShared();
            }
        });

        Thread second = new Thread(() -> {
            for (int i = 0; i < 20_000; i++) {
                incrementShared();
            }
        });

        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("shared count=" + sharedCount);
        System.out.println("expected shared=40000");
    }
}
```

### 7.1. Compile and run

Requires JDK 17 or higher:

```bash
javac --release 17 LockElisionDemo.java
java LockElisionDemo
```

**Exact stdout when running normally:**

```text
local checksum=14999950000
shared count=40000
expected shared=40000
```

This Java file was compiled with `javac --release 17` and executed successfully on HotSpot with default settings, `-Xint`, `-XX:-DoEscapeAnalysis`, and `-XX:-EliminateLocks`. **All configurations produce the same three lines above.**

### 7.2. Why is checksum equal to 14,999,950,000?

`localCriticalSection(i)` returns `3*i + 1` for `i` from 0 to 99,999. Total:

```text
sum(i=0..99999) (3*i + 1)
= 3 * (99999 * 100000 / 2) + 100000
= 3 * 4,999,950,000 + 100000
= 14,999,950,000
```

This is arithmetic in Java `long total`, so it does not overflow at this sum. Inside `localCriticalSection`, the operation `value * 3 + 1` also does not exceed the `int` limit for the program's inputs.

### 7.3. Why is sharedCount exactly 40,000?

Two threads both call `incrementShared()` 20,000 times. Each increment is inside:

```java
synchronized (SHARED_LOCK) {
    sharedCount++;
}
```

Because the same **static final monitor object** is used, increments on `sharedCount` are protected by mutual exclusion. The `Thread.join()` calls create the necessary happens-before relationship for `main` to read the result after both threads finish.

**If the shared lock is removed**, `sharedCount++` has a data race and the program may suffer lost updates; there is no longer a basis to guarantee the result is 40,000.

### 7.4. One example can have its lock eliminated; one example must keep semantics

- **`localCriticalSection`:** newly created lock, not published. This is a **good candidate** for HotSpot lock elimination.
- **`incrementShared`:** the lock is a shared object via a static field. Threads can contend; the JIT **is not allowed to eliminate monitor semantics** making the increment lose atomicity.

Note: **Identical stdout does not prove the machine code of localCriticalSection actually removed the monitor**. To confirm the optimizer eliminated instructions, you need compiled code analysis tools or controlled benchmarks plus supporting evidence.

## 8. HotSpot flags for observation and creating controls

### 8.1. Default

```bash
java LockElisionDemo
```

HotSpot typically enables escape analysis and lock elimination for the optimizing compiler when the feature/build supports it. Do not rely completely on default assumptions; check the current flags.

### 8.2. Disable escape analysis

```bash
java -XX:-DoEscapeAnalysis LockElisionDemo
```

This HotSpot flag disables escape analysis, which can affect **multiple optimizations at once**, including scalar replacement and lock elimination. Because multiple mechanisms change, **do not use timing differences to attribute the entire impact solely to locks**.

### 8.3. Disable lock elimination

```bash
java -XX:-EliminateLocks LockElisionDemo
```

Depending on build/version, this is a way to create a **more direct** control for lock-related optimizations. HotSpot's `EliminateLocks` flag has an implementation-specific scope related to lock optimizations (including lock coarsening according to source/flag descriptions). Therefore **do not claim it disables only a single transformation while keeping everything else unchanged**.

### 8.4. Run interpreter-only

```bash
java -Xint LockElisionDemo
```

This mode instructs executing Java bytecode with the interpreter, without JIT-compiling application bytecode. It is a **control**, but it removes **all JIT benefits**, not just lock elimination. If `-Xint` is slower, you cannot conclude the entire difference is "synchronized overhead".

### 8.5. Check actual flags at runtime

```bash
java -XX:+PrintFlagsFinal -version
```

Items of interest include `DoEscapeAnalysis`, `EliminateLocks`, `TieredCompilation`. Match the output to the specific JDK/vendor/architecture.

### 8.6. Why not use `-XX:+PrintEliminateLocks` by default?

Some older documentation recommends enabling `PrintEliminateLocks` or `PrintEscapeAnalysis`. In many **production HotSpot builds**, these are **non-product/debug-only flags** that do not work even with `-XX:+UnlockDiagnosticVMOptions`.

**Do not promise that a standard JDK 17 release will print a list of "eliminated locks" with that flag**. If you need to confirm the optimizer, use a VM/tool capable of analyzing machine code, controlled JMH experiments, or a supported debug/non-product build.

## 9. Using `javap` and `PrintCompilation` for the right purpose

### 9.1. `javap` proves the compiler generated monitor bytecode

```bash
javap -c -p LockElisionDemo
```

In testing with the code above, `javap` displays **`monitorenter`** and **`monitorexit`** in the corresponding methods. This is proof that `synchronized` exists in bytecode, **not a direct measurement of optimized JIT machine code**.

### 9.2. `PrintCompilation` confirms the JIT ran

```bash
java -XX:+PrintCompilation LockElisionDemo
```

Look for names such as:

```text
LockElisionDemo::localCriticalSection
LockElisionDemo::incrementShared
```

In a test run on HotSpot, the log contained lines like:

```text
... 3 ... LockElisionDemo::localCriticalSection (25 bytes)
... 4 ... LockElisionDemo::localCriticalSection (25 bytes)
... 3 ... LockElisionDemo::incrementShared (25 bytes)
... 4 ... LockElisionDemo::incrementShared (25 bytes)
```

**This is an example of the meaning of observed log lines, not full or fixed output.** Compile IDs, timestamps, and ordering vary by JVM. Level 3 is typically C1 with profiling, level 4 is typically C2.

### 9.3. Does Level 4 prove the lock was eliminated?

**No.** Level 4 only proves the method was compiled by C2 in that run, not that every `monitorenter` was eliminated. To prove lock elimination at a call site, you additionally need **observation of compiled IR/assembly or appropriate compiler information**.

### 9.4. Bytecode monitor and nmethod can differ

```text
javap:
  monitorenter / monitorexit present in class file
           |
           v
C2 optimized code:
  may still keep monitor operations
  OR eliminate them if proven safe
```

Optimization conclusions must be based on the **actual compiled execution path**, not inferred from an enabled flag or from the existence of `synchronized` in source.

## 10. How do scalar replacement and lock elimination differ?

These two optimizations are often mentioned together because both rely on escape analysis, but they are **not identical**.

### 10.1. Lock elimination

Goal: remove monitor overhead when the compiler proves synchronization operations are not needed to preserve Java semantics.

An object may still need to be materialized because identity is observed in a way that does not allow eliminating the allocation, yet the compiler may still have the opportunity to optimize the monitor if the object is sufficiently thread-local.

### 10.2. Scalar replacement

Goal: avoid materializing a full object on the Java heap when its fields can be represented by scalar values.

```java
static int computeFields(int x) {
    Pair pair = new Pair(x, x + 1);
    return pair.left + pair.right;
}
```

This is **illustrative code**; `Pair` needs to be defined. If `Pair` does not escape and all uses are suitable, C2 can replace the object with scalar values and avoid needing a physical heap allocation on the optimized path.

### 10.3. Allocation elimination is not "the object will live on the stack"

HotSpot C2, according to Oracle's description, does not perform general stack allocation for non-globally escaping objects. An optimized allocation disappearing due to scalar replacement is different from "moving a full object from heap to stack".

### 10.4. Can a lock be eliminated without the allocation being eliminated?

**Conceptually**, yes. Some escape states may be sufficient to eliminate a lock but not sufficient to scalar-replace the object. However, **whether a specific example does that** depends on the JDK/compiler graph.

Do not read benchmark results and claim "lock elimination is the sole cause" if allocation elimination, inlining, or loop optimization could happen at the same time.

## 11. Why is inlining so important?

EA is often more effective when the compiler sees **the entire usage path of the object**. If a monitor object is passed to a method and the compiler can inline that method, the reference path can become clear.

Example:

```java
static int guardedCompute(Object lock, int x) {
    synchronized (lock) {
        return x * 7;
    }
}

static int caller(int x) {
    Object fresh = new Object();
    return guardedCompute(fresh, x);
}
```

This is a **snippet** that needs to be placed in a class. In `guardedCompute` if analyzed in isolation, the `lock` parameter could come from any caller and could be shared. At the `caller` call site, the `fresh` object is newly created, not published, and the compiler **can see/inline** the code.

Therefore:

- If inlined enough, the compiler can prove the monitor is thread-private and eliminate the lock.
- If not inlined (method too large, polymorphic call site, limited profile, compilation budget...), the compiler may have to keep the monitor.
- There is no mandatory method size threshold across all JDKs where "below the threshold the lock is guaranteed to be elided".

### 11.1. Method boundaries do not equal EA boundaries

Some compiler optimizations work well when inlined across methods. However, the JIT does not always inline every helper, so the actual call graph structure matters.

### 11.2. Polymorphic calls can hinder optimization

If `guardedCompute` delegates to an interface call to an unpredictable implementation, the compiler may not know whether the callee publishes the monitor. Without proving no-escape, the safest choice is to keep monitor semantics.

### 11.3. Reflection and native calls

If an object is passed into reflective/JNI/native code, proving it does not escape can be harder. The JIT must not arbitrarily assume non-Java code does not publish the object or store a reference without an appropriate basis.

**Do not call internal/native code just to force a lock to be eliminated in a benchmark; doing so usually makes EA harder.**

## 12. Correctness when an object is actually shared

### 12.1. Static/shared monitor

```java
private static final Object LOCK = new Object();
private static int balance;

static void changeBalance() {
    synchronized (LOCK) {
        balance++;
    }
}
```

If multiple threads call `changeBalance` concurrently, the shared monitor serves to protect `balance++`. **Lock elimination must not break mutual exclusion** when the program shares the same lock.

### 12.2. Publishing a monitor through a field

```java
final class Service {
    final Object lock = new Object();
    int count;

    void increment() {
        synchronized (lock) {
            count++;
        }
    }
}
```

When a `Service` instance is shared between threads, the `lock` field of **the same instance** is also shared. Therefore the monitor has a real role.

Conversely, if the entire `Service` instance is proven to be used only on one thread within an optimized scope, the compiler may have an opportunity to optimize. **Do not decide from the word `final`**: `final Object lock` only makes the reference field unable to be reassigned after normal initialization; it does not guarantee the object is not published.

### 12.3. The Java Memory Model must still be preserved

If code properly uses the same monitor to publish shared state, the JIT must preserve happens-before relationships. It cannot eliminate locks based on the guess "there is no contention on the test machine".

### 12.4. A shared object does not mean every related lock must physically exist

The JIT can still optimize some nested/merged monitor operations or regions that do not affect observable synchronization according to the rules. But **do not equate** local optimization with eliminating all monitor semantics of shared synchronization.

## 13. Do not confuse three optimizations: elimination, coarsening, nesting

| Optimization | Effect | Intuitive condition | Example |
| --- | --- | --- | --- |
| **Lock elimination** | Remove monitor operations | Prove monitor is unnecessary, such as thread-private object | `synchronized(new Object())` with non-escaping object |
| **Lock coarsening** | Merge multiple consecutive small locks into a larger locked region | Compiler proves merging does not change semantics | Multiple consecutive synchronized blocks on the same monitor |
| **Nested lock elimination** | Remove redundant nested locking overhead | Reentrant lock on the same monitor within a suitable scope | `synchronized(lock)` inside `synchronized(lock)` |

### 13.1. Lock coarsening is not lock elimination

```java
synchronized (lock) { a(); }
synchronized (lock) { b(); }
```

This is an illustrative snippet. Some compiler optimizations may consider merging into a region:

```java
synchronized (lock) {
    a();
    b();
}
```

but **merging is not always valid**. It changes the duration the lock is held; if another thread can intervene between the two synchronized blocks, semantic differences must be considered. This is only a model illustrating the mechanism, not a direct refactoring guide for all code.

### 13.2. Lock elimination is not biased locking

**Biased locking** was a historical HotSpot mechanism aimed at optimizing certain low-contention locking scenarios by biasing toward a familiar thread. **JEP 374** disabled biased locking by default since JDK 15 and deprecated the related flags.

Key points:

- Lock elimination relies on **the compiler proving synchronized operations are redundant**.
- Biased locking was a way to optimize **performing locking** in HotSpot previously.
- Disabling biased locking **does not mean** disabling C2 escape analysis/lock elimination.
- Do not use the description "HotSpot currently always uses biased locking" as an invariant fact.

## 14. Why is `synchronized(new Object())` easy to optimize?

Look directly at it:

```java
static int local(int x) {
    synchronized (new Object()) {
        return x + 1;
    }
}
```

If no code receives a reference to the object literal allocation, another thread cannot acquire **the same monitor** to participate in synchronization together. The compiler can prove there is no useful observable synchronization through that monitor.

However, there are several caveats:

1. This is a **typical candidate**, not a guarantee that the JIT eliminates the lock in every JDK/compile mode.
2. Source still follows Java semantics and generates monitor-related bytecode; the interpreter still processes it.
3. The monitor object has identity and allocation semantics, though the optimized path can be scalar-replaced when eligible.
4. If the body has side effects, exceptions, or complex calls, the JIT must still preserve them.
5. If a reference to the lock is published outside, this reasoning is no longer valid.

**Never use a new lock every time to protect shared data**. Whether the compiler removes the lock or not, it cannot synchronize two threads on two different objects.

## 15. `synchronized` methods and lock elimination

An instance method:

```java
final class Counter {
    private int value;

    synchronized void addOne() {
        value++;
    }

    int value() {
        return value;
    }
}
```

locks the monitor of **`this`** when calling `addOne`.

If a `Counter` instance is created and then used privately within a method, does not escape, and the compiler clearly sees the usage path, the lock in `addOne` **can be an elimination candidate**, usually requiring inlining or equivalent analysis.

Illustrative example:

```java
static int isolated() {
    Counter counter = new Counter();
    counter.addOne();
    counter.addOne();
    return counter.value();
}
```

This is a snippet to be paired with the `Counter` class above. `Counter` is not published in this method, so optimized code can simultaneously apply **inlining**, **scalar replacement**, and **lock elimination**.

But if `counter` is accessed from a static registry, another thread can observe it and call `addOne`; **do not assume the lock is eliminated**.

### 15.1. What does `synchronized static` lock?

A `static synchronized` method locks the **Class object** of the class containing the method, not a separate `new Object()` per invocation. That class mirror can be shared by threads; do not infer that because a static method takes no object parameter, the lock is redundant.

### 15.2. Why is `StringBuffer` a classic historical example?

`StringBuffer` has many synchronized methods by API; when a `StringBuffer` is created and used completely locally, HotSpot can leverage EA/inlining to reduce monitor overhead in those synchronized methods.

However:

- `StringBuffer` still has its own allocation/backing array, buffer expansion, and copy costs.
- `StringBuilder` is designed for tasks not requiring synchronization and is usually the sensible source-level choice when not shared.
- Switching `StringBuffer` to `StringBuilder` must consider the **API contract and publication**, not just a single-case benchmark.
- There is no guarantee every `StringBuffer.append` has its lock eliminated on every JVM.

## 16. Factors that prevent C2 from eliminating a lock

A source case that "looks local" may still not be optimized due to:

1. **Object escape:** stored into a static/shared field or reference returned to an unanalyzable caller.
2. **Method not inlined:** compiler does not see all uses or the call graph is too large.
3. **Polymorphism:** receiver/callee varies widely, profile is not confident enough.
4. **JNI/native/reflective paths:** compiler lacks information to conclude non-escape.
5. **Compiler EA constraints:** control-flow complexity, memory graphs, or analysis limits/time.
6. **Cold method:** not yet compiled to a tier supporting that optimization.
7. **JVM flags:** `-Xint`, `-XX:-DoEscapeAnalysis`, `-XX:-EliminateLocks`, or compile directives.
8. **JDK/compiler version:** implementation changes, optimizations may appear/disappear.
9. **Observability requirements:** monitor/object identity is used in a way that cannot be eliminated while preserving semantics.
10. **Deoptimization/safepoint state:** the VM needs to restore correct state when optimized assumptions no longer hold.

**Do not modify code just to "make EA definitely optimize" using non-portable tricks**, especially in code with shared mutable state.

## 17. Observing performance scientifically

### 17.1. Suggested control experiment

Using the **same** `LockElisionDemo.class` and JDK build, run the modes:

```bash
java LockElisionDemo
java -XX:-EliminateLocks LockElisionDemo
java -XX:-DoEscapeAnalysis LockElisionDemo
java -Xint LockElisionDemo
```

These commands are suitable for **checking correctness**. The demo only prints checksum and count, **it does not print timing**; therefore do not use this output to claim speedup.

### 17.2. Why is comparing default mode with `-Xint` not enough to prove lock elimination?

`-Xint` disables **all JIT bytecode compilation**. Performance differences can come from:

- Method-call overhead.
- Inlining.
- Loop optimization.
- Bounds-check/branch optimizations.
- Allocation elimination.
- Lock elimination.
- Interpreter dispatch overhead.

To isolate the specific impact of lock elimination, `-XX:-EliminateLocks` is a closer-to-target control **if the build supports it** and you have checked interacting optimizations.

### 17.3. Using JMH for microbenchmarks

OpenJDK's **JMH (Java Microbenchmark Harness)** helps benchmarks have:

- Warm-up and measurement iterations.
- Forked JVM processes with separate flags.
- Blackhole/result consumption to avoid dead-code elimination.
- Statistical reporting, score units, and error estimation.
- A baseline controlling compiler optimization levels.

A reasonable JMH plan:

```text
Fork A:
  default HotSpot options

Fork B:
  -XX:-EliminateLocks

Fork C:
  -XX:-DoEscapeAnalysis  (auxiliary, does not isolate locks alone)

Same:
  JDK build
  CPU quota
  benchmark code
  data distribution
  warm-up and measurement parameters
```

If a benchmark method returns a simple result, the optimizer may eliminate a lot of computation; it must be designed so that **the measured workload actually remains**.

### 17.4. Why is a simple `System.nanoTime` loop error-prone?

A small loop can be:

- Fully inlined.
- Unrolled.
- Strength-reduced or constant-folded.
- Escape-analyzed and scalar-replaced.
- Dead-code eliminated if the result is unused.

That is precisely what you are studying. But if the experiment is uncontrolled, the result **does not tell you which lock was eliminated**.

### 17.5. Do not treat an "invisible optimization" as a guarantee

If the default benchmark is faster than when EliminateLocks is disabled, the result is **consistent with** the hypothesis that lock elimination reduces overhead, but statistical conditions and compiled-code evidence are still needed to assign causality with certainty.

## 18. Assembly analysis and compiler diagnostics

To observe whether a monitor site has been eliminated in machine code, specialized tools can be used depending on the JDK build:

- **`-XX:+PrintCompilation`:** shows compilation level/event, **does not tell whether the lock was eliminated**.
- **`-XX:+PrintInlining`:** helps understand some inlining decisions, **does not directly prove the lock was eliminated**.
- **`-XX:+PrintAssembly`** with a matching `hsdis` disassembler: views compiled code, but requires experience reading assembly/GC stubs.
- **JITWatch** or JIT log analysis tools: combine bytecode/assembly/compilation metadata.
- **Debug/non-product HotSpot builds:** may have flags to print compiler transformations not available in production releases.

### 18.1. Caution with PrintAssembly

```bash
java -XX:+UnlockDiagnosticVMOptions -XX:+PrintAssembly LockElisionDemo
```

This is a **suggested command to try on a build with disassembler support**; if `hsdis` is missing or output varies by architecture, you cannot expect a complete, easy-to-read assembly listing.

### 18.2. Deoptimization makes verification harder

A compiled method can be deoptimized or recompiled when assumptions change. Code measured at time A is not necessarily the same compiled version at time B. You need to inspect the compilation timeline/profile and warm-up.

### 18.3. C2 level 4 can still contain monitors

The C2 compiler is not required to eliminate a lock if EA lacks sufficient proof. Therefore:

```text
C2 compilation happened
             ≠
Every synchronized monitor in that method was removed
```

### 18.4. Reliable evidence

A strong conclusion needs:

1. Bytecode showing the synchronized source.
2. Identified HotSpot compiled version/machine code.
3. Analysis showing the corresponding monitor operations are no longer on the optimized path, or reliable compiler IR/debug evidence.
4. Control/timing experiments that do not contradict the inference.
5. Correctness preserved when running interpreter/JIT and multi-thread sharing cases.

## 19. Lock elimination does not solve all contention

A real-world program often locks a **shared object** to protect state:

```java
final class QueueState {
    private final Object lock = new Object();
    private int pending;

    void addTask() {
        synchronized (lock) {
            pending++;
        }
    }
}
```

If the same `QueueState` is accessed from multiple threads, this lock provides mutual exclusion. **There is no "EA magic" that automatically removes contention** while preserving the same semantics of `pending++`.

To optimize properly, consider:

- Reducing the time a shared lock is held.
- Moving I/O/blocking work outside the critical section if logic allows.
- Partitioning state per thread/shard to reduce sharing.
- Using atomic operations for truly independent counters.
- Using concurrent collections/pools instead of custom-written structures when appropriate.
- Checking false sharing, thread scheduling, and allocation rate with a profiler.
- Considering `ReentrantLock`/`StampedLock` or other structures when there is a clear need, **without assuming they are always faster than intrinsic locks**.

### 19.1. `LongAdder` and contended counters

If multiple threads increment a counter independent of a larger invariant, `LongAdder` may be more suitable than a single shared lock under contended workloads. However, `LongAdder.sum()` does not provide an atomic snapshot with respect to concurrent updates like arbitrary synchronized operations do.

Do not replace synchronized with `LongAdder` when logic requires a transaction across multiple fields or an invariant must be maintained within the same critical section.

### 19.2. Do not remove locks to fix a benchmark

If synchronization is needed, **do not remove `synchronized` just to achieve high speed**. A low-contention benchmark does not prove concurrency safety in production.

## 20. Issues with identity, null, and synchronized exceptions

### 20.1. `synchronized(null)`

Java throws `NullPointerException` when the monitor expression evaluates to `null`:

```java
Object lock = null;
synchronized (lock) {
    System.out.println("never reached");
}
```

This is an illustrative snippet. The JIT **must not** wrongly eliminate NPE semantics when optimizing; it can only transform when observable behavior is unchanged.

### 20.2. Lock identity matters

Two different objects can be `equals` to each other but **are not the same monitor**. Java `synchronized` locks by **object reference identity**, not by `equals()` or `hashCode()`.

Do not use a new object with the same `equals` value and expect threads using the two instances to automatically synchronize with each other.

### 20.3. Identity hash is not proof a lock cannot be eliminated

Calling `System.identityHashCode(lock)` may require the compiler to materialize identity under specific conditions. However, **there is no portable rule that "calling identityHashCode definitely forbids lock elimination"** or "it always pins the object at one address".

Whether identity is observed, allocation is scalar-replaced, and the lock can be eliminated are separate compiler decisions, depending on the behavior that must be preserved.

### 20.4. Wait/notify and monitor state

`Object.wait()`/`notify()` require monitor ownership and have their own semantics. If code calls them on a monitor, the compiler must preserve behavior regarding ownership, `IllegalMonitorStateException`, and necessary concurrency effects. **These operations cannot be arbitrarily removed** just because the variable name is local.

### 20.5. `volatile` does not replace locks in all cases

`volatile` is useful for visibility/ordering under the JMM; however, `counter++` consists of read-modify-write and **does not become atomic** just because `counter` is volatile. If atomic increment is needed, use a lock or appropriate atomic primitives.

## 21. Common misconceptions

| Misconception | Accurate interpretation |
| --- | --- |
| "Whenever `synchronized` is present, the CPU always executes full monitorenter/exit." | C2 can eliminate the monitor if it proves synchronization is unnecessary. |
| "If the lock variable is local, the object definitely does not escape." | The object can be returned, published to a static/shared field, or passed through a call. |
| "Lock elimination optimization makes `synchronized` lose Java semantics." | The JIT is required to preserve observable semantics. |
| "Testing showed no contention, so the compiler will surely remove the lock." | No observed contention **does not equal** proof of being thread-private. |
| "`synchronized(new Object())` is a way to protect a shared count." | Each call uses a different monitor, **not synchronizing threads with each other**. |
| "NoEscape is a Java keyword/type." | It is a compiler EA classification, not a language construct. |
| "A non-escaping object is guaranteed to be allocated on the stack." | C2 has scalar replacement; it does not promise stack allocation for objects. |
| "Lock elimination and scalar replacement always happen together." | They can have different conditions and separate compiler decisions. |
| "`-XX:-DoEscapeAnalysis` only disables lock elimination." | It can affect allocation/scalar replacement and many EA optimizations. |
| "`-XX:-EliminateLocks` is a production option that should be used." | It is primarily an experimental/control flag, and can worsen performance. |
| "`-Xint` is a control isolating only lock overhead." | It disables all JIT bytecode compilation and affects many other optimizations. |
| "`PrintCompilation` level 4 proves the monitor was removed." | It only shows C2 compilation, not proving a specific transformation. |
| "`javap` having monitorenter means the JIT cannot eliminate the lock." | `javap` reads pre-JIT bytecode, not optimized machine code. |
| "Lock coarsening also removes the entire monitor." | Coarsening merges/changes lock scope; different from elimination. |
| "Biased locking and C2 lock elimination are the same thing." | One was a historic runtime locking optimization; one is a compiler optimization. |
| "A `final lock` object cannot be shared." | `final` keeps the field reference unchanged, not preventing publishing the owner object. |
| "Every hot method is guaranteed to be EA-optimized." | Inlining, compiler limits, escape paths, and the build decide. |
| "A shared monitor can be removed because the JIT sees updates always succeed." | If threads share the monitor, mutual exclusion/JMM must be preserved. |
| "`synchronized(null)` might not throw an error if the JIT is good enough." | NPE semantics must still be preserved. |
| "`volatile int++` is atomic." | No; volatile does not automatically make compound increment atomic. |
| "One faster timing run proves lock elision." | Warm-up, repetition, profiler/assembly, or compiler evidence is needed. |

## 22. Self-check exercises with answers

**Question 1.** What is lock elimination?

**Answer:** A HotSpot JIT optimization that can remove monitor enter/exit in optimized machine code when the compiler proves the lock is not needed to preserve Java semantics, usually via escape analysis.

**Question 2.** Why can creating `new Object()` inside a synchronized block be a candidate for lock elimination?

**Answer:** If the object is not published/does not escape, other threads cannot acquire the same monitor to coordinate, so locking operations can be proven redundant.

**Question 3.** Does locking a `new Object()` on every call protect a static counter across multiple threads?

**Answer:** No. Each call has its own monitor, so there is no mutual exclusion between threads on the static counter.

**Question 4.** What are the well-known escape state groups of EA in HotSpot documentation?

**Answer:** NoEscape, ArgEscape, and GlobalEscape.

**Question 5.** Does `NoEscape` mean the JVM guarantees stack-allocating the object?

**Answer:** No. HotSpot can scalar-replace the allocation; you must not infer it creates the object on the stack.

**Question 6.** Should an object placed in a static field still be considered definitely non-escaping?

**Answer:** No. A static field is a publication path outside local scope, potentially accessible by multiple threads.

**Question 7.** Can `synchronized(lock)` on a static shared lock be removed unconditionally?

**Answer:** No. It may be needed to ensure atomicity/visibility between threads.

**Question 8.** Why does `javap` still show `monitorenter` after C2 optimizes?

**Answer:** `javap` reads `.class` bytecode; C2 optimizes machine code in the JVM runtime, without modifying the class file.

**Question 9.** Does `PrintCompilation` level 4 prove lock elimination occurred?

**Answer:** No. It only shows a C2 compilation event, not specifically reporting that a monitor was eliminated.

**Question 10.** What is the difference between lock elimination and lock coarsening?

**Answer:** Elimination removes monitor operations proven redundant; coarsening can merge synchronized regions under semantics-preserving conditions.

**Question 11.** Is `-Xint` a control solely for lock elimination?

**Answer:** No. It disables JIT compilation for bytecode, thus also removing many other optimizations.

**Question 12.** What else can `-XX:-DoEscapeAnalysis` affect besides locks?

**Answer:** Scalar replacement, allocation elimination, and other EA optimizations.

**Question 13.** Does JDK 17 still enable biased locking by default?

**Answer:** No. JEP 374 disabled biased locking by default since JDK 15; it is different from lock elimination.

**Question 14.** Which monitor does a synchronized instance method lock?

**Answer:** The monitor of the `this` instance receiving the call.

**Question 15.** Which monitor does a static synchronized method lock?

**Answer:** The monitor of the `Class` object representing the class containing the method.

**Question 16.** If `StringBuffer` is only used locally, are all synchronized methods guaranteed to have their locks removed by the JIT?

**Answer:** No. It is an optimization candidate when the compiler has sufficient proof; there is no Java/HotSpot guarantee for every case.

**Question 17.** Why is JMH better suited than a single `System.nanoTime` measurement?

**Answer:** JMH provides forks, warm-up, measurement, blackholes, and statistics, reducing many JIT benchmarking pitfalls.

**Question 18.** What is the `local checksum` result in the example?

**Answer:** `14999950000` for 100,000 values `i = 0..99999`.

**Question 19.** Two threads both increment sharedCount 20,000 times through the same monitor and join. Expected value?

**Answer:** `40000` when running normally to completion.

**Question 20.** Can a monitor actually used in wait/notify be arbitrarily removed?

**Answer:** No. Monitor ownership, wait/notify semantics, and exceptions must be preserved.

**Question 21.** If you want to prove a specific lock was eliminated in machine code, what do you need to observe?

**Answer:** Compiled code/IR or reliable compiler diagnostics on the specific HotSpot version, plus control experiments; a compilation log alone is not enough.

## 23. Practical application and diagnostics checklist

1. Confirm the JVM is HotSpot and record **JDK build, CPU architecture, VM flags**.
2. Distinguish the **monitor object** from the **protected data**.
3. Ensure all threads intending to protect the same invariant synchronize via the same appropriate mechanism.
4. Do not treat a local variable name as sufficient proof of non-escape.
5. Look for escape paths: return, static/shared fields, callbacks, native calls.
6. When code is hot, observe inlining/C1/C2/EA within tool limits.
7. Understand `javap` reports bytecode, not optimized assembly.
8. Use `-XX:-EliminateLocks` as a conditional control, not as a default tuning setting.
9. Know that `-XX:-DoEscapeAnalysis` also affects allocation optimizations.
10. Keep code correctness in `-Xint`, JIT, and multi-threaded contexts.
11. Use JMH/benchmarks with multiple forks and warm-up if evaluating performance.
12. Do not rely on `PrintEliminateLocks` on production JDK builds if the flag is not supported.
13. Do not confuse lock coarsening/nested locks/biased locking with compiler lock elimination.
14. When shared state has real contention, address it at the architecture/data sharing level rather than relying on EA.
15. Read JMM/happens-before before changing synchronization mechanisms.
16. Observe throughput, p95/p99 latency, CPU, and GC together when tuning HotSpot.
17. Do not change synchronization logic just because a small benchmark appears faster.
18. After upgrading JDK/changing JVM vendor, **re-verify performance assumptions** instead of hardcoding compiler behavior.

### End-of-article summary

```text
Java source synchronized(lock)
                |
                v
javac keeps monitorenter / monitorexit bytecode
                |
                v
HotSpot JIT (when code is hot enough)
                |
         Escape analysis
                |
     monitor is not shared?
          /           \
        Yes            No / cannot be proven
        |                       |
        v                       v
  Can eliminate lock      Keep monitor semantics
        |
        +--> If scalar-replaceable:
             can also eliminate object allocation

MANDATORY in both cases:
  - Mutual exclusion of shared synchronization remains correct.
  - Happens-before / memory visibility remains correct.
  - Exceptions, identity, and observable Java semantics remain correct.
```

**Core message:** **HotSpot can eliminate unnecessary `synchronized` locks thanks to escape analysis when the monitor object is not shared in a way that causes synchronization effects.** This is a compiler optimization capability, **not a promise that every local lock will be removed**, and certainly not license to remove synchronization protecting shared mutable state. Design code correctly according to the Java Memory Model first; let HotSpot optimize automatically when it has sufficient proof.

### Official and further reading

- [Oracle JDK 21 — Java HotSpot VM Performance Enhancements, Escape Analysis](https://docs.oracle.com/en/java/javase/21/vm/java-hotspot-virtual-machine-performance-enhancements.html): NoEscape/ArgEscape/GlobalEscape, scalar replacement, elimination of non-global-escaping locks, and local StringBuffer example.
- [Oracle JDK 17 — java Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): the `-XX:+DoEscapeAnalysis` flag and JIT/diagnostic flags.
- [OpenJDK JDK 17u — C2 compiler flags](https://github.com/openjdk/jdk17u/blob/master/src/hotspot/share/opto/c2_globals.hpp): `EliminateLocks`, `DoEscapeAnalysis`, `EliminateAllocations`, debugging flags not present in every product build.
- [OpenJDK — Escape Analysis and Scalar Replacement Status](https://cr.openjdk.org/~cslucas/escape-analysis/EscapeAnalysis.html): capabilities and limits of EA/C2, distinguishing stack allocation from scalar replacement.
- [JLS §17 — Threads and Locks (Java SE 17)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): synchronized, memory model, and happens-before.
- [JVMS §6.5 — monitorenter/monitorexit (Java SE 17)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html): semantics of bytecode synchronization.
- [OpenJDK JEP 374 — Disable and Deprecate Biased Locking](https://openjdk.org/jeps/374): distinguishing historical biased locking from C2 lock elimination.
- [OpenJDK JMH](https://openjdk.org/projects/code-tools/jmh/): Java microbenchmarks with warm-up, forks, and output statistics.
