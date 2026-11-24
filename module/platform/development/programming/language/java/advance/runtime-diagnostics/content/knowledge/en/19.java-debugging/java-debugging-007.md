# 19.7. Impact of Suspend, Breakpoints, and Expression Evaluation on Threads and Locks

## Objectives

When debugging Java with a debugger, **pausing at a breakpoint** affects more than just the line of code you are viewing. A thread may be suspended while holding a monitor, other threads may fail to acquire a lock, timeouts can expire while you inspect variables, and an expression that looks "read-only just to view a value" can execute real code inside the target JVM.

After this lesson, you will be able to:

1. Distinguish **debugger suspend**, **breakpoints**, **stepping**, and `-agentlib:jdwp=...suspend=y` at JVM startup.
2. Explain the three **suspend policies** in the Java Debug Interface (JDI): `SUSPEND_ALL`, `SUSPEND_EVENT_THREAD`, `SUSPEND_NONE`.
3. Analyze the impact of breakpoints inside `synchronized`, `ReentrantLock`, I/O blocks, or critical paths on **lock owners, blocked threads, request latency, and timeouts**.
4. Understand why **Evaluate Expression**, Watches, getters, and `toString()` can mutate program state or hang waiting on locks; know the special caveats of JDI `invokeMethod`.
5. Run a standalone Java 17+ program to observe monitor-holding and monitor-waiting threads, and practice setting breakpoints under each policy.
6. Diagnose the "app hangs only under debug" phenomenon and apply a debugging workflow that minimizes production impact.

> **Main point:** **Suspend does not mean releasing locks**. A debugger pausing a monitor-holding thread can leave other threads `BLOCKED`, even when you select "Suspend: Thread." Evaluating a method can actually run that method inside the JVM, so debugging results may no longer reflect the state before you clicked Evaluate.

## 1. When Attaching a Debugger to a JVM, What Is Happening?

In the Java ecosystem, typical components include:

- **Target JVM (debuggee):** the Java process hosting the running application.
- **Debugger client:** an IDE such as IntelliJ IDEA, Eclipse, VS Code, or the CLI tool `jdb`.
- **JDWP (Java Debug Wire Protocol):** the protocol carrying debug requests/events between client and JVM.
- **JDI (Java Debug Interface):** the Java API for debuggers to interact with threads, stacks, breakpoints, objects, classes, and methods.
- **JVMTI:** the low-level tool interface used by the VM/agent; you normally do not call it directly when debugging in an IDE.

```text
IDE / jdb                    JDWP                      JVM debuggee
+----------------+       +-------------+          +--------------------+
| Breakpoint     | <---> | Debug agent | <------> | Thread A           |
| Resume / Step  |       | / transport |          | Thread B           |
| Variables      |       +-------------+          | Monitor / Lock     |
| Evaluate       |                                | Heap / Shared data |
+----------------+                                +--------------------+
```

A **breakpoint** is a request to pause or receive an event when execution reaches a location, condition, or debugger-defined trigger. **Suspend** is pausing progress of one or more threads on a debug request/event. **Step Into / Over / Out** normally run the thread until the next stop point and pause again per debugger behavior; they are not "safe operations with zero impact on other threads."

Distinguish two situations:

| Situation | Meaning |
| --- | --- |
| JVM launched with `-agentlib:jdwp=...,suspend=y` | JVM waits for debugger attach/resume **before `main` starts** per JDWP VM-start suspension. |
| JVM running with `suspend=n` | Application runs immediately, even before a debugger attaches. |
| Breakpoint with **Suspend: All** | When the breakpoint triggers, the debugger requests suspending all JDI-managed threads in the VM. |
| Breakpoint with **Suspend: Thread** | Suspends **the thread hitting the breakpoint**; other threads can keep running. |
| Non-suspending breakpoint (log/trace breakpoint, if supported) | Records events without pausing threads, though instrumentation and expression evaluation still incur cost. |

`-agentlib:jdwp=...suspend=y` at startup is **not** the per-breakpoint "Suspend All/Thread" option. Both names contain *suspend*, yet their trigger conditions differ.

## 2. Three Suspend Policies in JDI: Who Gets Paused?

`com.sun.jdi.request.EventRequest` defines:

| JDI policy | Behavior when event arrives | Typical impact |
| --- | --- | --- |
| `SUSPEND_ALL` | Suspends all target JVM threads within JDI scope. | Easier to capture a consistent snapshot at one point, yet **the whole application may stall** until Resume. |
| `SUSPEND_EVENT_THREAD` | Suspends **the thread that emitted the event**. | Other threads have a chance to run, yet may stall waiting on data/locks held by the suspended thread. |
| `SUSPEND_NONE` | Does not suspend threads for that event. | Useful for trace/logpoints; cannot reliably read locals/stacks while the program keeps running. |

In JDI, **the default for `EventRequest` is `SUSPEND_ALL`** unless the debugger changes it. IDE UIs may map it under different names or pick their own default; **inspect the configuration of each specific breakpoint** rather than guessing by IDE name alone.

### Does `SUSPEND_ALL` Always Mean "Everything Freezes Completely"?

Do not interpret it that way. JDWP/JDI manages suspension of threads observed by the debugger; activities outside the JVM such as wall-clock time, clients, remote servers, and timeouts on external systems **keep advancing**. Moreover, certain debugger actions like **method invocation during Evaluate** can temporarily resume threads per JDI rules. Hence even at a `Suspend All` breakpoint, never assume the JVM stays completely immutable throughout expression evaluation.

### `SUSPEND_EVENT_THREAD` Does Not Guarantee the Rest of the System Keeps Running

Suppose thread A holds a monitor needed by B, C, and D:

```text
Thread A: synchronized (LOCK) {
             ... BREAKPOINT: Suspend Thread ...
          }

Thread B: synchronized (LOCK) { ... }  // BLOCKED
Thread C: synchronized (LOCK) { ... }  // BLOCKED
Thread D: independent work             // Can keep running
```

Pausing A **does not automatically release the monitor**. B and C can run up to acquiring the monitor and turn `BLOCKED` until A resumes and exits the `synchronized` block. D, which does not depend on the lock, can keep running. The application can simultaneously appear "running" and **fail to respond** to critical requests.

## 3. Why Suspending While Holding a Lock Can Cause a Hang

Java has multiple synchronization primitives, each with distinct waiting and lock-release semantics.

### 3.1. `synchronized` and Monitor Ownership

```java
synchronized (LOCK) {
    updateSharedState();
    callOtherMethod();   // Pausing here still holds monitor LOCK
}
```

This is an **illustrative snippet**, not a standalone program.

Once a thread enters `synchronized (LOCK)`, it owns the monitor until leaving the synchronized block (normally or via exception and its corresponding unlock). **A debugger pausing the thread does not act like exiting `synchronized`**. If another thread tries to enter the same monitor, it can enter `BLOCKED` state.

- `Thread.sleep(...)` **does not release monitors** held by the thread.
- `LockSupport.park(...)` **does not automatically release monitors**.
- Valid `Object.wait()` inside a monitor-owned block **temporarily releases that monitor while waiting**, then must re-acquire it before returning. Yet **debugger suspend is not `Object.wait()`**.
- Java monitors are **reentrant**: the thread already owning the monitor can re-enter `synchronized` on that monitor; this matters when interpreting Evaluate.

### 3.2. `ReentrantLock` and `Condition`

```java
lock.lock();
try {
    updateState();
    inspectHere();       // Breakpoint: lock is still held by the thread
} finally {
    lock.unlock();
}
```

This is also an **illustrative snippet**, assuming `lock` is initialized and methods exist in the app. A breakpoint at `inspectHere()` pauses the thread **before entering `finally`**. Only when the thread advances and executes `unlock()` is the lock released.

Unlike intrinsic monitors, threads waiting on `ReentrantLock` typically enter `WAITING`/`TIMED_WAITING` via `LockSupport.park`, **not necessarily `BLOCKED`**. Never conclude "no `BLOCKED` threads means no lock contention."

A valid `Condition.await()` temporarily releases the **associated lock** while waiting; upon waking, it must re-acquire the lock. Never infer backward that a debugger pause also releases locks.

### 3.3. When Is It a "Debugger-Induced Stall" vs. a Real Deadlock?

**Debugger-induced stall:**

```text
Thread A holds LOCK -> breakpoint pauses A
Thread B needs LOCK -> waits on A
Resume A -> A advances and releases LOCK -> B proceeds
```

This is a **breakpoint-caused slowdown/stall**, insufficient to conclude there is a deadlock in normal application logic.

**Real deadlock:** threads wait on one another in an unresolvable cycle, e.g., A holds lock X waiting for Y while B holds Y waiting for X. A breakpoint can expose or trigger a wait chain, yet two threads waiting for a long time **is not enough** to prove a deadlock cycle. Inspect **who owns each monitor/lock**, stacks, dependency graphs, and behavior after Resume.

## 4. Java 17+ Program for Direct Observation

We create a standalone example using **two platform threads**:

- `lock-owner` acquires monitor `LOCK`, prints that it holds the lock, then waits for a signal from waiter.
- `lock-waiter` announces it is about to try acquiring the same monitor; while owner holds the lock, waiter can enter `BLOCKED` state.
- One statement on the owner thread serves as the **breakpoint location** inside `synchronized`.
- `EVENTS` proves **Evaluate Expression has side effects** when invoking a method that mutates state.

Create file **`DebugSuspendLab.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class DebugSuspendLab {
    private static final Object LOCK = new Object();
    private static final CountDownLatch HOLDER_ENTERED = new CountDownLatch(1);
    private static final CountDownLatch WAITER_READY = new CountDownLatch(1);
    private static final AtomicInteger EVENTS = new AtomicInteger();

    public static int peekEvents() {
        return EVENTS.get();
    }

    public static int changeEvents() {
        return EVENTS.incrementAndGet();
    }

    public static int readUnderLock() {
        synchronized (LOCK) {
            return EVENTS.get();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Thread owner = new Thread(() -> {
            synchronized (LOCK) {
                System.out.println("owner: has lock");
                HOLDER_ENTERED.countDown();
                try {
                    if (!WAITER_READY.await(3, TimeUnit.SECONDS)) {
                        throw new IllegalStateException("waiter not ready");
                    }
                    Thread.sleep(500);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return;
                }

                int seen = EVENTS.get(); // SET BREAKPOINT ON THIS LINE.
                System.out.println("owner: checkpoint=" + seen);
                EVENTS.incrementAndGet();
                System.out.println("owner: releasing");
            }
        }, "lock-owner");

        Thread waiter = new Thread(() -> {
            try {
                HOLDER_ENTERED.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
            System.out.println("waiter: attempting lock");
            WAITER_READY.countDown();
            synchronized (LOCK) {
                System.out.println("waiter: acquired lock");
            }
        }, "lock-waiter");

        owner.start();
        waiter.start();
        owner.join();
        waiter.join();
        System.out.println("main: finished counter=" + EVENTS.get());
    }
}
```

### 4.1. Normal Run Without Debugger

Compile with debug information for line numbers/local variables when debugging:

```bash
javac --release 17 -g DebugSuspendLab.java
java DebugSuspendLab
```

Output of this program when run normally (no Evaluate calls, no code edits):

```text
owner: has lock
waiter: attempting lock
owner: checkpoint=0
owner: releasing
waiter: acquired lock
main: finished counter=1
```

**Verified on a newer JDK in `--release 17` mode.** Two latches ensure owner takes the lock before waiter attempts entry, and waiter signals before owner reaches the checkpoint. The 500 ms sleep makes observing monitor waiting easier; during real debugging, durations and timing order can vary due to scheduling and suspension.

Explanation:

- `HOLDER_ENTERED` opens only after owner has acquired the monitor.
- `WAITER_READY` confirms waiter is about to enter `synchronized (LOCK)`. Owner still holds the monitor during `Thread.sleep(500)`.
- `int seen = EVENTS.get()` sits **inside** the synchronized block and is a suitable breakpoint site.
- `EVENTS.incrementAndGet()` below the checkpoint increments the variable once during a normal run.
- `owner.join()` and `waiter.join()` make `main` wait for both threads. If owner is paused at a breakpoint for long, **`main` also cannot finish**; this is normal dependency, not a `join()` bug.

### 4.2. Starting the JVM in Debug Mode Over Loopback

To have time to set breakpoints before worker threads run:

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005 DebugSuspendLab
```

In this example:

- `transport=dt_socket`: uses JDWP sockets.
- `server=y`: target JVM listens for debugger connections.
- `suspend=y`: JVM pauses **before running `main`** until resumed by the debugger.
- `address=127.0.0.1:5005`: listens only on **IPv4 localhost**, avoiding exposing a debug port to the network.

In your IDE, create a **Remote JVM Debug / Attach** configuration, host `127.0.0.1`, port `5005`, ensuring the IDE uses source matching the compiled class. Set a **line breakpoint on `int seen = EVENTS.get();`**, not on a comment line, then let the VM run.

**Note:** port 5005 is just an example and must be changed if another process occupies it. Debuggers may display source and frames differently depending on IDE/JDK; setting a breakpoint on a line without emitted bytecode may cause the IDE to shift it to the nearest executable line.

### 4.3. Experiment A: Suspend All

1. Set a breakpoint at `int seen = EVENTS.get();`.
2. Choose **Suspend: All** (or "Suspend all threads" per IDE naming).
3. Run until hitting the breakpoint and inspect thread states.
4. While paused, **owner still holds `LOCK`**, so waiter cannot enter its `synchronized` block.
5. While the entire VM is suspended, the console makes no application progress. Never treat a frozen console as proof of deadlock.
6. Click **Resume** to let owner finish and release the lock. The program normally finishes with the standard output from section 4.1 if you performed no side-effecting Evaluate calls.

**Conclusion:** `SUSPEND_ALL` is better for capturing a consistent snapshot across threads, yet a long enough pause can skew latency measurements or cause external clients to time out.

### 4.4. Experiment B: Suspend Thread (event thread)

1. Restart the example from the beginning, changing the breakpoint to **Suspend: Thread / Event thread**.
2. Thread `lock-owner` pauses at the checkpoint inside `synchronized`.
3. Other threads are not **directly suspended by that breakpoint**. However:
   - `lock-waiter` can advance up to `synchronized (LOCK)` and turn `BLOCKED`.
   - `main` continues waiting on `owner.join()` and cannot finish.
   - An **independent thread not needing the monitor** (if any) could keep running.
4. When you Resume owner, the monitor is released and waiter finishes.

**Conclusion:** Suspend Thread narrows the direct pause scope, **without eliminating** cascading stalls from locks and inter-thread dependencies.

### 4.5. Experiment C: Non-Suspending or Logpoint

If your IDE supports non-suspending logpoints/tracepoints, replace the line breakpoint with **logging without pausing**. The program is not held at the checkpoint by that debug request; there is still overhead from event transmission and formatting/logging. If the logpoint evaluates an expression, that expression can execute real code and is **not automatically safe**.

## 5. Evaluate Expression: Observation Is Not Always "Read-Only"

IDEs commonly offer **Evaluate Expression**, **Watch**, **Variables**, **Inspect**, and auto-invocation of getters/`toString()`. They can use different mechanisms:

- **Direct field reads via JDI:** retrieves values stored in an object without necessarily running a Java method.
- **Invoking methods inside the target JVM:** e.g., `list.size()`, `object.toString()`, `getState()`, `service.load()`, `someMap.computeIfAbsent(...)`; those methods can **mutate state, acquire locks, allocate, do I/O, or throw exceptions**.
- **Evaluating breakpoint conditions:** depending on IDE/expression type, the debugger may evaluate conditions by reading fields or calling methods in the target.
- **Automatic variable rendering:** the IDE may invoke `toString()` or getters to render previews even when you did not explicitly type a call.

### 5.1. Example of Reading and Mutating State in the Lab

While paused at `int seen = EVENTS.get();`, try **in order**:

```java
DebugSuspendLab.peekEvents()
```

This function returns the current `AtomicInteger` value and **its own code does not actively mutate `EVENTS`**. Still, invoking it via the debugger can affect scheduling because the JVM must run the method in debug context.

Next, **only in this lab program**:

```java
DebugSuspendLab.changeEvents()
```

This method actually calls `incrementAndGet()`, thereby **incrementing `EVENTS`**. After Resume, the values in `owner: checkpoint=...` and `main: finished counter=...` can **differ from non-debug output**. This proves Evaluate is not a read-only operation.

Example:

```text
Normal:  checkpoint=0, counter=1
After evaluating changeEvents() exactly once at the breakpoint:
         checkpoint=1, counter=2
```

The numbers on the second line are **logical expectations assuming a single mutating call and no other interference**, not a guarantee regardless of whether the debugger re-evaluates expressions multiple times.

### 5.2. When Evaluate Calls a `synchronized` Method

The program also includes:

```java
DebugSuspendLab.readUnderLock()
```

That method enters `synchronized (LOCK)` and returns the count. When the debugger invokes it on **`lock-owner` itself, which already owns the monitor**, re-entry can succeed because monitors are **reentrant**. Never oversimplify to "every Evaluate while holding a lock deadlocks."

However, if the debugger invokes a method on another thread and that method needs a monitor **held by a suspended thread**, the call can block. This scenario depends on **the thread chosen for invocation**, lock ownership, suspend state, debugger settings, and the method itself.

**Another dangerous example** (for reading/understanding only, never run on critical systems):

```java
// Could be a method invoked by Evaluate:
public String describe() {
    synchronized (sharedLock) {
        return expensiveLookup();
    }
}
```

If `sharedLock` is held by **another suspended thread**, evaluating `describe()` can hang forever. `expensiveLookup()` could also hit the network, files, database, or perform unintended mutations.

### 5.3. Crucial Behavior of JDI `invokeMethod`

Per the `com.sun.jdi.ObjectReference.invokeMethod(...)` API contract (and similar invoke APIs):

1. The debugger can request **running a method on a specific target VM thread** when that thread was suspended by an eligible event, such as a breakpoint. This is not always valid if the thread was suspended solely by another command.
2. The call can **block the debugger** until the method returns or throws; with locks/waits in the app, it may stall unexpectedly long.
3. **By default, JDI may resume other threads in the target during method invocation** to reduce the chance the method waits on a monitor owned by another suspended thread. After invocation, JDI restores suspend states per the API contract. Thus **Evaluate can allow code outside the current thread to keep running**.
4. If the debugger uses the **`INVOKE_SINGLE_THREADED`** flag, only the invoking thread is allowed to run; all other threads stay suspended. This can cause the method to wait for a lock, future, or timer with **no other thread running to release it**.
5. Suspend counts (*suspend count*), new breakpoints hit during invocation, and pending debugger events can still produce deadlocks or hangs, **even without single-threaded mode**.

**Do not assume every IDE uses the exact same invocation mode.** An IDE may optimize field reads, temporarily toggle breakpoints, change flags, or disallow Evaluate in certain states. The practical rule is to **check options like "Evaluate in single thread", "Resume other threads", "Invoke methods", "Show toString" if your tool provides them**, and avoid calling methods with unknown side effects.

### 5.4. `toString()`, Getters, and Properties Are Not Harmless by Name

Example of a getter with lazy initialization:

```java
public synchronized Data getData() {
    if (cached == null) {
        cached = loadFromDatabase();
    }
    return cached;
}
```

This is **illustrative code**, where `Data`, `cached`, and `loadFromDatabase()` belong to an application class. An IDE calling `getData()` to render an object can:

- Acquire the instance monitor and increase contention.
- Query the database while the JVM is paused for debugging.
- Populate `cached`, mutating state before you measure or snapshot it.
- Throw an exception/timeout causing the IDE to show an Evaluate error, or even alter subsequent app behavior.

`toString()` can also nest multiple getters, iterate over a mutating collection, call a remote service, or recurse over an object graph. **Never enable auto-evaluate for costly/uncertain methods in production.**

## 6. Conditional Breakpoints, Watchpoints, Logpoints, and Stepping Also Have Costs

### 6.1. Conditional Breakpoints

Example breakpoint pausing only when:

```java
requestId.equals("R-42")
```

This is an **illustrative expression** in a scope containing `requestId`. Evaluating `equals` is a method call; it may be simple on `String`, yet **you cannot generalize** that every `equals` method is safe. The IDE may invoke the expression every time code passes that location, even when the condition is false.

If a breakpoint sits in a hot loop executing millions of times per second, emitting events and evaluating conditions can severely hurt throughput. Choose **thread filters, hit counts, and instance filters** when supported by the debugger, and avoid conditions that touch DB/network/locks or mutate state.

### 6.2. Logpoints Do Not Equal "Zero Impact"

A logpoint can print info without suspending threads. Yet there is still overhead for event handling, string formatting, expression evaluation, and data transfer. If a logpoint calls a side-effecting `object.toString()`, the application can still be altered without ever pausing at a breakpoint.

### 6.3. Step Into/Over/Out

- **Step Over** continues executing code until the next stop point in the current method; it still must **run the actual code**. If that code calls a blocking/locking function, the thread can wait.
- **Step Into** enters the invoked method; it does not skip locks or side effects.
- **Step Out** runs until exiting the current frame; if the frame holds a monitor, it may release the lock only when actually leaving the synchronized block.
- IDEs may offer **Smart Step**, **Run to Cursor**, **Force Return**, or **Drop Frame**. Never treat those features like transaction rollback: prior I/O, DB updates, file writes, or counter increments **are not automatically undone**.

When you need to observe many invocations without heavy pausing, prefer controlled logging, JFR, profilers, or suitable metrics rather than stepping iteration by iteration in production.

## 7. Four Common Failure Patterns Caused by Debuggers

| Failure pattern | Mechanism | How to verify |
| --- | --- | --- |
| API stops responding when breakpoint pauses in `synchronized` | Owner holds lock while suspended; other workers wait on monitor. | Check owner frame inside critical section and other threads `BLOCKED`; Resume and see if activity recovers. |
| Heartbeats/timeouts/callbacks disappear on **Suspend All** | Threads handling those tasks are also suspended. | Check breakpoint policy, runtime timeline, and verify external clients/clocks keep advancing. |
| Evaluating `toString()`/getter hangs | Method waits on lock/future/I/O or hits another breakpoint; debugger waits on invocation. | Check for method invocation, resume policy, breakpoints/conditions, and lock ownership. |
| After Evaluate, data values or thread ordering change | Expression had side effects or debugger temporarily resumed other threads. | Compare snapshot before Evaluate; disable auto-evaluate; retry with simple field reads. |

### 7.1. Timeouts and Retries During a Pause

Suppose request A normally finishes in 200 ms. You suspend it for 30 seconds at a breakpoint while the HTTP client in **another process** keeps running. The client may time out and retry. Upon Resume, the JVM may process stale data, write duplicates, or hit closed connections.

```text
t=0 ms       request enters critical section
t=40 ms      breakpoint, thread suspended
t=2000 ms    client in another process times out
t=30000 ms   you click Resume
t=30001 ms   app resumes into an altered state/world
```

Do not conclude "the app's timeout logic is broken" if timeouts only occurred while you paused the JVM for a long time. Reproduce with metrics **without debugger pauses**, checking deadlines at clients, peer services, and timers.

Even when `Suspend All` pauses JVM threads, **real wall-clock time does not stop**; after Resume, deadlines may already have expired and a burst of timeouts/callbacks can fire at once.

### 7.2. A Thread in `BLOCKED` State Is Not Necessarily a Deadlock

You can observe `lock-waiter` in `BLOCKED` state when owner is paused in the lab. If Resuming owner immediately lets waiter proceed, that was a **predictable debugger side effect**. Production deadlocks typically require evidence of a wait cycle or inability to make progress even with no debugger pausing threads.

### 7.3. Suspend and Thread Dumps Do Not Provide the Same Evidence

- **Breakpoint:** pauses at a specific location/condition and exposes locals/stacks at debug time.
- **Thread dump:** snapshot of thread stacks/states at collection time; can identify owners/waited monitors when supported by the tool/runtime.
- **JFR:** time-ordered stream of events (lock contention, parks, GC, socket I/O, samples) per recording settings; does not automatically record every line executed.

When a JVM is heavily suspended, external diagnostic tools like `jcmd` may **respond slowly or be temporarily unavailable**, depending on the suspension type and runtime. **Do not automatically blame "JVM deadlock" simply because diagnostic tools fail to respond while a debugger is paused.**

## 8. Checklist When the App "Freezes" During a Debug Session

A safe, repeatable investigation workflow:

1. **Confirm whether the debugger is actually paused.** Check session status and which threads are suspended; did a breakpoint accidentally enable `Suspend All`?
2. **Locate the pause line and held monitors/locks.** Inspect `synchronized` frames, `ReentrantLock.lock`, `try/finally`, and I/O under locks.
3. **Inspect other threads:** which ones are `BLOCKED`, `WAITING`, `TIMED_WAITING`, and which locks/futures/conditions are they waiting on? Never infer deadlock from state names alone.
4. **Check if Evaluate is running:** are watches/conditions/`toString`/getters being auto-invoked by the debugger? Is a method invocation waiting?
5. **Stop triggering new side effects:** do not spam Evaluate or mash Step before understanding the situation. Be cautious with "Force Return", "Drop Frame", and variable edits.
6. **Once sufficient observation data is captured**, disable the pausing breakpoint or switch to a controlled logpoint; Resume with the appropriate scope. Note that suspend counts can exceed 1 if multiple pauses stacked.
7. **Verify post-Resume behavior:** did waiters clear the monitor? Did request timeouts already occur in external systems?
8. **Reproduce without a debugger** using logs/JFR/metrics. If stalls persist, prioritize a real concurrency bug; if they happen only while paused, investigate debugger impact.
9. **If production debugging is unavoidable**, obtain operational approval, strict time/scope limits, and a clear recovery plan; never place hot breakpoints on high-traffic request paths.

**Useful signal:** after Resume, threads waiting on a monitor immediately progressing is evidence the breakpoint contributed to the stall. Still, it does not rule out other issues; verify under normal workload.

## 9. Placing Breakpoints Wisely to Minimize Skew

| Practice | Benefit | Things to remember |
| --- | --- | --- |
| Pause before acquiring a lock or after releasing it | Avoids holding critical sections unnecessarily while reading variables. | You may miss state **inside** the critical section; use snapshots/logs appropriately. |
| Prefer **Suspend Thread** when only one worker is needed without whole-JVM state | Reduces direct pause blast radius. | If the worker holds a shared lock, impact still ripples outward. |
| Use bounded/throttled logpoints on hot paths | Reduces service stalls. | Logpoints still incur overhead and expression side effects. |
| Restrict conditions to simple field checks | Fewer side effects and calls. | Even reading fields is a moving snapshot; other threads can mutate state. |
| Disable auto-invoking `toString`/getters when untrusted | Prevents accidental Evaluate calls. | Different IDEs use different setting names. |
| Use JFR, logs, and metrics instead of breakpoints in production | Enables longer observation with lower impact when configured properly. | Still has overhead, thresholds, and sampling limits. |
| Use staging environments and non-sensitive data | Safer to pause and test side effects. | Concurrency/load may differ from production. |

### JDWP Security

A JDWP port grants powerful debugger access to JVM state and execution. Never expose a debug port to the Internet or untrusted networks, as it can allow reading sensitive data and controlling execution inside the application.

The lab uses:

```text
address=127.0.0.1:5005
```

to restrict to loopback. When debugging a remote JVM is required, use a secured/controlled channel (such as an approved tunnel), network policies, and infrastructure-layer authentication; never assume JDWP provides strong built-in authentication. **Never add `address=*:5005` in production**, as it listens on all interfaces when the server supports that syntax.

When finished, terminate the debug session safely and verify the app has resumed; do not leave debuggers/ports open longer than necessary.

## 10. Common Misconceptions

| Misconception | Correct explanation |
| --- | --- |
| "With Suspend Thread, other threads are definitely unaffected." | Other threads can still wait on locks, latches, queues, or data held/coordinated by the suspended thread. |
| "Pausing releases all monitors." | Debugger suspend **does not** execute `monitorexit` or `unlock()` on behalf of the app. |
| "`sleep()` inside `synchronized` frees the monitor." | `Thread.sleep()` does not release monitors. |
| "`Object.wait()` is the same as debugger suspend." | Valid `Object.wait()` temporarily releases its monitor; debugger suspend does not. |
| "Seeing `BLOCKED` means Java is deadlocked." | It may simply be waiting on a paused owner; inspect owner/wait cycles and Resume. |
| "No `BLOCKED` threads means no lock contention." | `ReentrantLock` and other primitives use `park`, resulting in `WAITING/TIMED_WAITING`. |
| "Evaluate only computes inside the IDE UI." | Methods in expressions can execute live inside the **debuggee JVM**. |
| "`toString()` and getters definitely do not mutate data." | They can lazy-init, lock, do I/O, write caches, throw, or recurse. |
| "Under Suspend All, no threads run during Evaluate." | Default JDI method invocation may temporarily resume other threads; depends on flags/IDE. |
| "Enabling single-threaded evaluation is always safer." | It can deadlock the invoked method because the lock-holding or notifying thread stays suspended. |
| "Step Over skips method side effects." | It still **executes** the method; only how the debugger picks the next pause point differs. |
| "Timeouts during a pause prove a network or code bug." | Clocks and remote clients keep running; pausing itself can induce timeouts. |
| "Non-suspending breakpoints have zero overhead." | They may still emit events, evaluate conditions, format logs, and invoke methods. |
| "Detaching always immediately fixes every freeze." | Check suspend counts, stuck method invocations, actual state, and IDE detach behavior; unfreezing is not guaranteed. |

## 11. Reasoning Exercises

### Scenario A: Stall Due to Monitor

`lock-owner` is suspended at `int seen = EVENTS.get()` while holding `LOCK`. `lock-waiter` is waiting to enter `synchronized (LOCK)`.

**Question:** Does `Suspend Thread` let waiter finish before owner Resumes?

**Answer:** No, because owner still owns the monitor. Waiter is not directly suspended yet becomes `BLOCKED` waiting on the monitor until owner advances and releases the lock.

### Scenario B: Evaluate Changes Output

At the checkpoint, Evaluate `DebugSuspendLab.changeEvents()` exactly once.

**Question:** After Resume, how might the final counter change?

**Answer:** With no other interference and the method running once, `EVENTS` increments from Evaluate, and then increments again in owner: the final result can be `2` instead of `1`. Post-Evaluate numbers must never be treated as a snapshot of the original state.

### Scenario C: Calling a Getter Hangs

The debugger pauses thread A and while rendering an object invokes a getter requiring a lock held by thread B. B is also suspended.

**Question:** Why can Evaluate hang, and why can `INVOKE_SINGLE_THREADED` make it worse?

**Answer:** The method actually executes and must wait for the lock; B is not resumed to release it. Single-threaded mode resumes only the invoking thread, guaranteeing the lock-owning thread makes no progress.

### Scenario D: Prolonged Pause in Production

You Suspend All for 20 seconds during a request while the client times out after 3 seconds. You Resume and observe exceptions or retries.

**Question:** Can you conclude the root cause is the network?

**Answer:** No. You must reproduce without pausing and compare timeout deadlines, logs/traces, and real I/O. The breakpoint was an interfering variable in the experiment.

### Scenario E: Non-Suspending Breakpoint

You replace a breakpoint with a logpoint whose condition calls `cache.computeIfAbsent(key, ...)`.

**Question:** Is it completely safe?

**Answer:** No. The method can update the cache, allocate, lock, or run value-computing code even though the debugger does not suspend threads. Use cheap field/value conditions and limit event frequency.

## 12. Checklist Before and During Multithreaded Java Debugging

- [ ] Identified the exact JVM, build/source, and breakpoint type.
- [ ] Checked **Suspend All / Thread / None** policy, without confusing it with startup `suspend=y`.
- [ ] Checked whether the breakpoint sits **inside a critical section** or while the thread holds a `ReentrantLock`.
- [ ] Identified the **lock owner** before treating `BLOCKED` threads as a logic bug.
- [ ] Verified `Thread.State`: `BLOCKED` for intrinsic monitors; `WAITING/TIMED_WAITING` can come from park/conditions; `RUNNABLE` does not necessarily mean consuming CPU.
- [ ] Avoided evaluating methods/`toString()`/getters with unknown side effects, especially in runtimes with locks.
- [ ] If Evaluate is unavoidable, remembered JDI may **resume other threads**, or single-threaded invocation can **deadlock**.
- [ ] Avoided using debugger pause durations to measure real program latency.
- [ ] Resumed/disabled breakpoints with the right scope and verified workers/locks made progress.
- [ ] Reproduced outside the debugger before drawing conclusions about real deadlocks or bottlenecks.
- [ ] Protected the JDWP port, data inside the debugger, and the service recovery plan.

## References

- [Oracle Java SE 21 — `EventRequest` (`SUSPEND_ALL`, `SUSPEND_EVENT_THREAD`, `SUSPEND_NONE`)](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jdi/com/sun/jdi/request/EventRequest.html).
- [Oracle Java SE 21 — `ThreadReference.suspend()` and deadlock risk when a thread holds a monitor](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jdi/com/sun/jdi/ThreadReference.html).
- [Oracle Java SE 21 — `ObjectReference.invokeMethod`, resume behavior, and `INVOKE_SINGLE_THREADED`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jdi/com/sun/jdi/ObjectReference.html).
- [Oracle Java SE 21 — JPDA Connection and Invocation Details, JDWP options](https://docs.oracle.com/en/java/javase/21/docs/specs/jpda/conninv.html).
- [Oracle Java SE 21 — `java` command, `-agentlib:jdwp`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html).
- [Java Language Specification §17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html).
