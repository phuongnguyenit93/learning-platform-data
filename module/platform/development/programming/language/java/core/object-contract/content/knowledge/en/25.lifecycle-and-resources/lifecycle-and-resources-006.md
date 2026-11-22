# Recognizing Cleaner as a Limited Fallback Mechanism

## 1. What Problem Does Cleaner Solve?

In Java, the **garbage collector (GC)** manages the memory of Java objects that the program no longer uses. However, the GC does not directly guarantee releasing **resources outside the Java heap** at the exact time the application needs, such as file descriptors, sockets, native memory, native library pointers, or operating system handles.

A resource-managing object may no longer be referenced while the operating system resource remains unclosed. If a program creates many resources and waits for GC, handle limits can be exhausted before the JVM needs or manages to collect the heap.

Since Java 9, `java.lang.ref.Cleaner` allows **registering a cleaning action** tied to an object's collectable state. Cleaner is a useful fallback mechanism in some resource-managing libraries; **it is not a reliable resource-closing schedule**.

Core rule:

> Resources that must be closed on time should use `AutoCloseable`, `close()`, and `try-with-resources`. Cleaner can only serve as a supporting layer when a programmer omits the explicit closing path, with limitations that must be accepted.

### Three Different Things Commonly Confused

| Mechanism | Responsibility | What Not to Assume |
| --- | --- | --- |
| GC | Reclaim JVM-managed memory when objects are no longer needed | That GC will call `close()` or close OS handles immediately |
| `AutoCloseable` / `try-with-resources` | Express ownership and close resources at a deterministic point in control flow | That it protects resources if the `close()` path is completely bypassed |
| `Cleaner` | Register an action that may run when an object becomes **phantom reachable**, or runs when calling `Cleanable.clean()` | That the action is guaranteed to run on time, run on JVM exit, or replace explicit closing |

Cleaner is built on top of `PhantomReference` and `ReferenceQueue`. Learners at this level only need to grasp the relationship **object loses reachability → JVM may notify via reference mechanism → cleaning action gets a chance to run**; there is no need to implement reference queues manually to use the API.

## 2. Lifecycle of a Cleaner Registration

Main components of the API:

- `Cleaner.create()` creates a manager for cleaning actions.
- `cleaner.register(referent, action)` registers the **tracked object** (referent) and a cleanup `Runnable`; returns `Cleaner.Cleanable`.
- `cleanable.clean()` requests executing the cleaning action **immediately upon call**, if that action has not already been executed.
- If `clean()` is not called, Cleaner **may** run the action after the tracked object becomes phantom reachable and Cleaner is notified.
- A cleaning action executes **at most once** per registration: calling `clean()` again will not run the same action a second time.

Recommended usage flow:

~~~text
Create resource-managing object
        |
        v
Register Cleaner(referent, cleanupState)
        |
        +--> Normal path: try-with-resources / close()
        |                   |
        |                   v
        |             Cleanable.clean()
        |             runs the cleaning action
        |
        +--> Forgotten close() path:
                            |
                            v
               Object is no longer reachable
                            |
                            v
               GC/Cleaner may trigger
               the cleaning action after an
               INDETERMINATE delay, or not run
               before the process exits
~~~

The word “may” is crucial: **there is no SLA, maximum deadline, or guarantee it will run before the JVM stops**. Without heap memory pressure, the GC may not process objects for a long time, even while file/socket/native handle counts grow excessively.

Cleaner typically uses a daemon thread for automatic processing. Background actions should be **short, non-blocking**, and not depend on application threads or require UI interaction. A failing cleaning action is not a reliable business-error channel: exceptions thrown by a cleaning action are ignored by the Cleaner mechanism; resource error observability must be designed through the proactive closing path.

## 3. Java 17+ Example: Proactive `close()`, Fallback Cleaner

The following example **simulates** a resource using an integer ID. It logs output to illustrate exact cleanup timing; **it does not open or release real operating system resources**. The key technique is placing data needed for cleanup in a **static `State` class independent of the tracked object**.

Save as file **CleanerDemo.java**:

~~~java
import java.lang.ref.Cleaner;
import java.util.concurrent.atomic.AtomicBoolean;

public class CleanerDemo {
    private static final Cleaner CLEANER = Cleaner.create();

    // Holds only data needed for cleanup; DO NOT hold a reference to Handle.
    private static final class State implements Runnable {
        private final int id;
        private final AtomicBoolean released = new AtomicBoolean();

        State(int id) {
            this.id = id;
            System.out.println("open " + id);
        }

        void requireOpen() {
            if (released.get()) {
                throw new IllegalStateException("resource closed");
            }
        }

        @Override
        public void run() {
            // Simulates releasing an off-heap resource.
            if (released.compareAndSet(false, true)) {
                System.out.println("release " + id);
            }
        }
    }

    private static final class Handle implements AutoCloseable {
        private final State state;
        private final Cleaner.Cleanable cleanable;

        Handle(int id) {
            this.state = new State(id);
            this.cleanable = CLEANER.register(this, state);
        }

        void use() {
            state.requireOpen();
            System.out.println("use " + state.id);
        }

        @Override
        public void close() {
            // Proactively clean up when the user closes Handle.
            cleanable.clean();
        }
    }

    public static void main(String[] args) {
        try (Handle handle = new Handle(7)) {
            handle.use();

            // Repeated calls do not re-run the same cleaning action.
            handle.close();
            handle.close();
        } // try-with-resources automatically calls close() one more time.

        System.out.println("done");
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 CleanerDemo.java
java CleanerDemo
~~~

Deterministic output of the **proactive closing path**:

~~~text
open 7
use 7
release 7
done
~~~

Explanation:

1. `new State(7)` creates the independent state required for cleanup and prints `open 7`.
2. `CLEANER.register(this, state)` tracks the `Handle` object, while `state` stores only the ID and released status.
3. `handle.close()` calls `cleanable.clean()` directly, so `release 7` appears before `done`. Any subsequent `clean()` calls on the same registration do not re-run the action.
4. `AtomicBoolean.compareAndSet(false, true)` illustrates once-only behavior at the state layer and avoids executing the release portion twice if application logic also needs guarding. `Cleanable` itself already guarantees the registered action is called at most once.
5. `try-with-resources` remains the mechanism responsible for closing in normal flow. Even if the `try` body errors, Java still attempts to call `close()` when exiting the block.

The example does not wait for GC and does not rely on Cleaner running in the background; consequently stdout is verifiable. In production code, the simulated `System.out.println("release " + id)` must be replaced by real resource-release logic, with proper ownership rules, exception safety, and thread safety.

**Do not write unit tests that wait on `System.gc()` and assert Cleaner must run.** `System.gc()` is only a request for the JVM to consider running GC, and does not guarantee the cleaning action completes or gets called within a test timeout.

## 4. Most Important Trap: The Cleaning Action Retaining a Back-Reference

The registered object must have a chance to become **unreachable** for the automatic Cleaner path to work. If the cleaning action itself holds a strong reference to that object, the object's lifetime is extended and the action is never automatically triggered.

**Flawed example — solely to illustrate an anti-pattern, do not use in production:**

~~~java
// Inside class Handle:
cleanable = CLEANER.register(this, () -> {
    // Reading a field via "this" makes the lambda capture Handle.
    System.out.println(this.state);
});
~~~

Because the lambda above captures `this`, Cleaner holds a reference back to the very object being tracked. `Handle` never reaches the state required for Cleaner to process it automatically. This situation can cause a silent, persistent leak.

Ways of accidentally retaining the referent:

- `Runnable` is a **non-static inner class** of the tracked object: non-static nested classes typically hold a reference to the enclosing instance.
- A lambda calls an instance method or accesses a field via `this`.
- `State` indirectly holds the outer object via a collection, callback, listener, or another object.

**Safe pattern:** use a `static nested class State implements Runnable` or an independent action containing only **the information actually needed to release the resource**, with no pointers back to the registered object. If `State` holds another resource, verify that resource does not indirectly retain `Handle`.

Additional note: separating the tracked object and cleanup state does not mean releasing can happen safely at any arbitrary moment. For native handles still used during a long operation, synchronizing close/use, handle validity, and using `Reference.reachabilityFence(...)` when needed are separate concerns that must be carefully designed.

## 5. Limitations to Remember Before Choosing Cleaner

### 5.1. Nondeterministic Timing

An object becoming phantom reachable **does not mean** the action runs immediately. When GC runs, when the object is processed in the reference queue, and when the Cleaner thread executes are all outside business code's scheduling control.

Practical consequence: file descriptors/native memory can run out before Cleaner catches up. Do not design connection limits, open file counts, or native memory budgets around a promise that “GC will clean up soon”.

### 5.2. No Guarantee on Process Termination

With `System.exit(...)`, cleaner behavior is implementation-dependent; the API does not guarantee actions are called. When the JVM is killed, power fails, or the OS abruptly terminates the process, you certainly cannot demand Java callbacks run.

Do not use Cleaner as the sole place to write transactions, emit critical events, perform guaranteed data flushes, or promise releasing resource locks at a specific time.

### 5.3. Runs Outside Business Control Flow

Automatic actions typically run on a thread managed by Cleaner. Never assume that thread has a transaction context, request context, MDC logging, UI thread access, thread-local state, or active dependencies as when the resource was opened.

Actions must be short, self-contained, and safe when multiple cleanups run concurrently. A long-blocking action can delay other actions sharing the same cleaner. If cleanup requires reliable I/O, controlled retries, error reporting to the caller, or deterministic ordering, use proactive lifecycle management.

### 5.4. Hard to Observe Errors and Test

Do not expect exceptions from automatic actions to surface on the caller's thread. Cleaner ignores exceptions thrown by actions; this makes failed cleanups hard to detect and increases leak risk.

Tests for primary behavior should call `close()`, verify the resource is released exactly once, and test `try-with-resources` exception paths as well. Do not write tests relying on GC timing or Cleaner thread ordering; if you need to test the action logic itself, extract that logic and run it directly in tests.

### 5.5. Cleaner Cannot Manage All Resources

For connections, files, transactions, executors, subscriptions, or locks with clear lifetime rules, **explicit close/destroy APIs remain the primary source of control**. In particular, operations needing commit/rollback, guaranteed flush, or timely return of connections to a pool are unsuitable for arbitrarily deferred cleanup.

Cleaner also does not mean just any `Runnable` is safe to run in the background. It requires checking ownership, idempotency, concurrency, and ensuring references do not retain the referent.

## 6. Choosing the Right Mechanism by Resource Type

| Situation | Preferred Approach | Role of Cleaner |
| --- | --- | --- |
| Reading a file or accessing a socket within a scope | `try-with-resources` around `AutoCloseable` | Usually no custom Cleaner needed |
| Resource tied to service/application lifecycle | Close in an explicit lifecycle hook or owner's `close()` | Does not replace shutdown/lifecycle logic |
| Native handle owned by a Java wrapper | Explicit `close()` API with ownership policy | Can be considered as a fallback if close is forgotten |
| Transactions, database connections, locks | Commit/rollback/release at designated business scope | Must not be treated as a time-guaranteed mechanism |
| Object holding only ordinary Java data | Let GC manage memory | Usually no Cleaner needed |
| Collecting telemetry/logs when an object is GC'd | Use only if uncertainty is fully acceptable | Do not use as a mandatory exact metrics source |

For native resource wrapper libraries, a common design is **one shared cleanup path** used by both proactive `close()` and the Cleaner fallback. This reduces duplicate release logic; however, you must still avoid back-references and ensure the action can run from multiple thread contexts.

## 7. Cleaner and `finalize()`: Related, Not Identical

Older Java used `Object.finalize()` to run a method when an object was about to be collected. Finalization suffered from predictability, reliability, performance, and safety issues; `finalize()` is **deprecated for removal**. New Java code should not rely on it.

Cleaner is a structured API that separates the action from the tracked object, avoids many finalization problems, and allows **proactive `clean()` calls**. However, Cleaner **does not fix the nondeterministic nature of GC**. Therefore:

- Do not mechanically convert every `finalize()` into a Cleaner and keep omitting `close()`.
- First determine who owns the resource and when its lifetime must end.
- Prefer `AutoCloseable` / `try-with-resources`. Only add Cleaner when there is a specific fallback reason and its limitations are acceptable.

Cleaner does not “run a C++-style destructor”. Java has no automatic scope-based destructors with RAII semantics; `try-with-resources` is how deterministic resource closing is expressed in Java.

## 8. Applied Scenarios: Assessing the True Nature of Requirements

**Scenario A — Processing a report file.** A program opens a file, writes data, and must guarantee closing/flushing before reporting “export completed”. Cleaner is unsuitable as the primary path: the resource must close after a `try-with-resources` scope; I/O errors must be observed and handled.

**Scenario B — JNI wrapper holding a native pointer.** User code occasionally forgets to call `close()`, risking native memory leaks. A Cleaner can serve as a fallback when the wrapper becomes unreachable, yet the wrapper must still have a deterministic close path, cleanup state must not retain the wrapper, and the library must accept that the fallback may be delayed or not run before process exit.

**Scenario C — Service holding a connection pool.** The pool must be initialized, used, and shut down according to the application lifecycle; Cleaner does not know when the application is about to stop, does not guarantee ordered shutdown, and does not replace pool shutdown hooks.

**Scenario D — Task requiring mandatory audit logging.** Do not register audit emission as a cleaning action: if the JVM exits, the action may never run; if the action fails, the exception never reaches business flow. Record audits in the transactional path or a reliable delivery mechanism.

## 9. Common Mistakes When Using Cleaner

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Assuming `System.gc()` triggers Cleaner on time | Unstable GC-dependent tests and logic | Test `close()`; avoid forcing GC as a guarantee |
| Only Cleaner, no `close()` | Resources are not released according to desired lifetime | Design `AutoCloseable` and clear ownership |
| Action is a lambda capturing `this` | Referent is kept alive; fallback rarely or never runs | Independent `static State`, no back-references |
| Cleanup takes a long time or waits indefinitely | Blocks processing of other actions | Keep actions fast, decouple business operations |
| Treating cleanup exceptions as “succeeded” | Errors are hidden | Proactively close where errors can be reported |
| Using Cleaner to replace `finally`/try-with-resources | No guarantee of closing after scope | Close explicitly in the main execution path |
| Creating one cleaner/thread per instance unnecessarily | Increases management overhead | Consider sharing a Cleaner at library or class scope |
| Releasing native handle while another operation still uses it | Resource access errors, races | Design consistent synchronization, ownership, and lifetime |

## 10. Self-Check Questions

**1. Does creating a `Cleaner.Cleanable` cause the resource to close when scope ends?**

No. Leaving scope does not guarantee the object immediately becomes phantom reachable or the action runs. Only proactive `close()`/`clean()` executes the cleanup path immediately on call.

**2. Why must the action's state not contain `this`?**

Because the action could hold a strong reference to the referent, preventing the referent itself from becoming phantom reachable; thus the automatic fallback will not trigger.

**3. Can `try-with-resources` be replaced with Cleaner for an output file that needs flushing?**

No. Flushing/closing a file needs to happen at a deterministic time and errors must be observed; use `try-with-resources`.

**4. Does calling `cleanable.clean()` twice run the action twice?**

No. An action that has already been executed will not run again via the same `Cleanable`.

**5. In one sentence, how should Cleaner be remembered?**

Cleaner is an **opportunistic fallback cleanup path**, not a mechanism guaranteeing timely cleanup completion. For resources with deterministic lifecycles, use owner + `AutoCloseable` + `try-with-resources` as the primary design.

## Official References

- [Java SE 21 — java.lang.ref.Cleaner](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ref/Cleaner.html)
- [Java SE 21 — AutoCloseable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/AutoCloseable.html)
- [Java SE 21 — Object.finalize() (deprecated for removal)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Object.html#finalize())
- [JEP 421 — Deprecate Finalization for Removal](https://openjdk.org/jeps/421)
