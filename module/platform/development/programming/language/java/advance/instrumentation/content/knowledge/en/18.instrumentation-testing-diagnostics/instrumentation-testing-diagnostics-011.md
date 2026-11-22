# Testing Transformer Unregistration During Active Callbacks and Ordered Collection Shutdown

In Java Instrumentation, calling **Instrumentation.removeTransformer(transformer)** **unregisters** a ClassFileTransformer; it **is not a command that waits for all callbacks to finish**. The Java SE 17 Javadoc explicitly states that due to **multithreaded class loading**, a transformer **may still receive callbacks after it has been removed**. This means an agent that records metrics/tracing or generates bytecode cannot close its exporter as soon as it receives **removed=true**.

For example: thread A is executing **transform(ClassA)**, has already been admitted by the agent, and is recording an event; thread B calls **removeTransformer** and then closes the queue/file exporter; thread A resumes and writes to the closed resource. That is an agent shutdown ordering bug, not necessarily a JVM bug.

The solution pattern is: **close the admission gate → unregister the exact transformer → drain already-admitted callbacks → process the entire queue and flush → close exporter/resources**. If the agent has injected runtime hooks into bytecode, **hook admission** must also be disabled, because unregistering the transformer **does not remove hook calls already installed in classes**.

This lesson belongs to the **Testing and Diagnostics** group, targeting Java 17+. Beyond the API contract, it includes a **complete program** that triggers a real class-load callback, intentionally holds the callback while calling removeTransformer, uses CountDownLatch to verify the schedule, and simulates a late-arriving callback to test defensive behavior.

## 1. Understanding the Exact API

~~~java
// Illustrative snippet in premain/agentmain with Instrumentation inst.
ClassFileTransformer t = new MyTransformer();
inst.addTransformer(t, false);

// Remove the exact instance that was added.
boolean removed = inst.removeTransformer(t);
~~~

According to the Java SE 17 documentation:

- **addTransformer(transformer, false)** registers the transformer to receive matching class definitions, where false means not to invoke this transformer again during **retransform**. If canRetransform=true is needed, both the JVM and the manifest must support it.
- **removeTransformer(transformer)** returns **true** when a matching registration is found and removed, and **false** when none is found.
- If the same transformer instance is registered **multiple times**, a single remove call only removes the **most recent matching registration**. Duplicate registration is permitted but discouraged.
- **removeTransformer(null)** throws **NullPointerException**.
- Because class loading can run across multiple threads, **callbacks can still appear after removal**. The transformer must be written to handle this.

**Removed=true does not imply inFlight=0**, nor does it imply the exporter has been flushed. When testing, you must separate **registration state**, **callback state**, and **event delivery state**.

### 1.1. Distinguishing Lifecycle States

| State | Meaning |
| --- | --- |
| REGISTERED | Instrumentation currently holds the transformer's registration |
| CALLBACK_INVOKED | The JVM actually invoked transform; the agent may not have admitted collection yet |
| ADMITTED | The gate allowed the callback to proceed and incremented inFlight |
| IN_FLIGHT | The callback has been admitted but has not yet left |
| ADMISSION_CLOSED | From this point on, new callbacks are rejected by the gate |
| DETACHED | removeTransformer has processed the registration |
| PRODUCERS_DRAINED | All already-admitted callbacks/hooks have finished |
| QUEUE_DRAINED | The exporter queue/batch has no remaining data to process |
| FLUSHED | The exporter has flushed according to its contract |
| STOPPED | Resources needing closure are closed; late calls are safe |

These are **agent-designed labels**, not a Java Instrumentation enum. **DETACHED** and **IN_FLIGHT=1** can be true at the same time.

## 2. Two Typical Races When Stopping

### 2.1. Callback Already Running Before Remove

~~~text
Class-loader thread                        Controller thread
----------------------------------------   ------------------------
JVM calls transform(ClassA)
callback passes gate; inFlight = 1
callback waits on I/O or latch
                                           removeTransformer(t) -> true
                                           exporter.close()  (TOO EARLY)
callback continues
callback writes event                      write-after-close!
callback finally leaves; inFlight = 0
~~~

Because removeTransformer does not wait for callbacks, calling exporter.close immediately after remove is unsafe. You must **drain accepted work** before closing.

### 2.2. Callback Arriving After Remove

~~~text
Class-loader thread                        Controller thread
----------------------------------------   ------------------------
JVM has prepared transformer call path
                                           removeTransformer(t) -> true
transform callback starts late
~~~

The Java API allows late callbacks, though it **does not guarantee one will occur in every test run**. Therefore, the transformer needs a **guard right at the start of the collection section**:

~~~java
if (!gate.enter()) {
    return null;          // Stopped: do not modify bytes, do not record events.
}
try {
    // Transformation/collection has been admitted.
    return null;
} finally {
    gate.leave();
}
~~~

**return null** means the transformer provides no modifications. Do not throw an exception just to signal shutdown: per the ClassFileTransformer contract, the JVM can still proceed to other transformers, and the side effects of throwing will complicate diagnostics.

### 2.3. Can an Already-Admitted Invocation Record Events After Closing the Gate?

**Yes**, if the shutdown policy is to **drain accepted invocations before stopping**. After closing the gate, new callbacks are not admitted, but a callback that entered before stopping can finish, enqueue its event, and then leave. Therefore, the exporter must remain active until **producers drained + queue flushed**. The **gate closed** milestone is the boundary for **not accepting new work**, not the point at which **all events have immediately vanished**.

## 3. Invariants That Must Be Tested

**I1 — Atomic admission:** After the gate's **close()** completes, no callback can simultaneously read the OPEN state and increment inFlight late without the controller knowing.

**I2 — Exactly-once in-flight:** Every successful enter increments inFlight once; finally decrements it once, even on exception/interrupt/early return.

**I3 — Remove the exact instance:** Only the transformer's owner calls remove, without creating a new instance. Do not accidentally add the same instance multiple times.

**I4 — Late callback no-op:** A callback passing through the gate after close receives false and returns null, without touching the closed queue/exporter.

**I5 — Real drain:** The **inFlight=0** condition must be awaited using a synchronization primitive, not guessed via Thread.sleep.

**I6 — No premature close:** Exporter.close runs only after producers and queue drain, or after a clearly decided timeout/fallback policy.

**I7 — No self-join:** A callback does not wait for the drain of a work group in which it itself is counted.

**I8 — No fake rollback:** removeTransformer does not revert already-installed bytecode back to the original version.

## 4. A Gate Using synchronized to Prevent Races

A concise and easily verifiable Java 17 implementation:

~~~java
// Component of the full example in the following section.
private static final class Gate {
    private boolean accepting = true;
    private int inFlight;

    synchronized boolean enter() {
        if (!accepting) {
            return false;
        }
        inFlight++;
        return true;
    }

    synchronized void leave() {
        inFlight--;
        if (inFlight == 0) {
            notifyAll();
        }
    }

    synchronized void close() {
        accepting = false;
    }

    synchronized int active() {
        return inFlight;
    }

    synchronized void awaitZero() throws InterruptedException {
        while (inFlight != 0) {
            wait();
        }
    }
}
~~~

Both **checking accepting** and **incrementing inFlight** happen inside one synchronized region, sharing the same monitor as close. Thus there are exactly two cases:

1. **enter acquires the lock first**: the callback is admitted and inFlight is already incremented; shutdown must subsequently wait for it.
2. **close acquires the lock first**: the callback sees accepting=false and does not increment inFlight.

Do not hold the gate monitor while performing I/O, logging, or bytecode transformation. The monitor only manages lifecycle counters. **Object.wait()** is used in a while loop to handle both spurious wakeups and unexpected condition changes.

### 4.1. Why Are Two Separate Atomic Variables Not Enough?

~~~java
// INCORRECT pseudocode: check-then-increment has a race.
if (!closed.get()) {         // A sees false
    // B: closed=true; sees active=0; closes exporter.
    active.incrementAndGet();
    sendEvent();             // A touches the closed exporter!
    active.decrementAndGet();
}
~~~

AtomicBoolean and AtomicInteger guarantee individual operations, but **check + increment** is not atomic as a pair. A lock-free version requires a shared CAS state machine encoding both the **closed bit and active count** with a complete proof. For learning and for many agents, a synchronized gate is clearer and less error-prone.

## 5. Complete Java 17 Example: Real Callback Held During Remove

The demo uses a single source file **UnregisterLab.java**, acting as both the Java agent (with **premain**) and the test program (with **main**). The code requires no external libraries.

Flow:

1. **premain** registers **Observer** once, with **canRetransform=false**.
2. Main creates a loader thread, asking the JVM to define the class **UnregisterLab$Subject** via Class.forName.
3. The JVM invokes the real **transform**; the callback passes the gate, signals **ENTERED**, and then waits on **RELEASE**.
4. Main waits for ENTERED to know the callback is already running, closes the gate, and calls **removeTransformer(observer)**. At the time of the check, inFlight is still 1.
5. Main **directly calls transform** with the class name **UnregisterLab$Late** to simulate a late callback; the gate is already closed so it returns null. This is a **unit-level simulation**, not a JVM-generated late callback.
6. A waiter thread waits on awaitZero and cannot finish while RELEASE has not opened.
7. Main counts down RELEASE; the real callback increments EVENTS, calls finally leave, and the waiter completes.
8. Assertions verify the results and print eight fixed stdout lines.

**Note:** The demo transformer **always returns null**, because this exercise is about callback lifecycle, not about modifying classfileBuffer. If a real agent needs to transform, the transform logic can live in the admitted section and must return a valid new byte[] when modifying, without mutating the input bytes.

### 5.1. UnregisterLab.java

~~~java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public final class UnregisterLab {
    private static final Gate GATE = new Gate();
    private static final CountDownLatch ENTERED = new CountDownLatch(1);
    private static final CountDownLatch RELEASE = new CountDownLatch(1);
    private static final AtomicInteger EVENTS = new AtomicInteger();
    private static volatile Instrumentation instrumentation;
    private static volatile Observer observer;

    public static void premain(String args, Instrumentation inst) {
        instrumentation = inst;
        observer = new Observer();
        inst.addTransformer(observer, false);
    }

    public static final class Subject {
        public static int answer() {
            return 42;
        }
    }

    private static final class Gate {
        private boolean accepting = true;
        private int inFlight;

        synchronized boolean enter() {
            if (!accepting) {
                return false;
            }
            inFlight++;
            return true;
        }

        synchronized void leave() {
            inFlight--;
            if (inFlight == 0) {
                notifyAll();
            }
        }

        synchronized void close() {
            accepting = false;
        }

        synchronized int active() {
            return inFlight;
        }

        synchronized void awaitZero()
                throws InterruptedException {
            while (inFlight != 0) {
                wait();
            }
        }
    }

    private static final class Observer
            implements ClassFileTransformer {

        @Override
        public byte[] transform(
                ClassLoader loader,
                String className,
                Class<?> classBeingRedefined,
                ProtectionDomain domain,
                byte[] classfileBuffer) {

            if (!"UnregisterLab$Subject".equals(className)
                    && !"UnregisterLab$Late".equals(className)) {
                return null;
            }

            if (!GATE.enter()) {
                return null;
            }

            try {
                if ("UnregisterLab$Subject".equals(className)) {
                    ENTERED.countDown();

                    try {
                        RELEASE.await();
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                        return null;
                    }

                    EVENTS.incrementAndGet();
                }

                return null;  // Do not modify class bytes.
            } finally {
                GATE.leave();
            }
        }
    }

    public static void main(String[] args)
            throws Exception {

        if (instrumentation == null || observer == null) {
            throw new IllegalStateException(
                    "Run with -javaagent");
        }

        AtomicReference<Throwable> loadFailure =
                new AtomicReference<>();

        Thread loader = new Thread(() -> {
            try {
                Class.forName(
                        "UnregisterLab$Subject",
                        true,
                        UnregisterLab.class.getClassLoader());
            } catch (Throwable failure) {
                loadFailure.set(failure);
            }
        }, "load-subject");

        loader.start();

        if (!ENTERED.await(5, TimeUnit.SECONDS)) {
            throw new AssertionError(
                    "No real JVM callback arrived");
        }

        GATE.close();
        boolean removed =
                instrumentation.removeTransformer(observer);
        int activeAtRemove = GATE.active();

        // Simulate a callback arriving after close to test the gate.
        byte[] skipped = observer.transform(
                null, "UnregisterLab$Late",
                null, null, new byte[] { 0 });

        int beforeRelease = EVENTS.get();

        CountDownLatch drained = new CountDownLatch(1);
        Thread waiter = new Thread(() -> {
            try {
                GATE.awaitZero();
                drained.countDown();
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            }
        }, "await-drain");
        waiter.start();

        boolean drainedBeforeRelease =
                drained.await(100, TimeUnit.MILLISECONDS);

        RELEASE.countDown();
        loader.join(5000);
        waiter.join(5000);

        if (loader.isAlive() || waiter.isAlive()
                || loadFailure.get() != null) {
            throw new AssertionError(
                    "Loader/drain did not complete",
                    loadFailure.get());
        }

        if (!removed || activeAtRemove != 1
                || skipped != null || beforeRelease != 0
                || drainedBeforeRelease || EVENTS.get() != 1
                || GATE.active() != 0) {
            throw new AssertionError(
                    "Shutdown contract violated");
        }

        System.out.println("CALLBACK_ENTERED=true");
        System.out.println("REMOVED=true");
        System.out.println("ACTIVE_AT_REMOVE=" + activeAtRemove);
        System.out.println("LATE_CALLBACK_SKIPPED=true");
        System.out.println(
                "DRAIN_BLOCKED_UNTIL_RELEASE=true");
        System.out.println(
                "EVENTS_AFTER_DRAIN=" + EVENTS.get());
        System.out.println(
                "ACTIVE_AFTER_DRAIN=" + GATE.active());
        System.out.println("SHUTDOWN_OK");
    }
}
~~~

Java 9 and above has the **ClassFileTransformer.transform(Module, ...)** overload; its default implementation can forward to the five-parameter overload used in the example. Filtering via string comparison **"name".equals(className)** is safe if className is null.

### 5.2. agent.mf

~~~text
Manifest-Version: 1.0
Premain-Class: UnregisterLab
~~~

Keep a trailing newline at the end of the file. The demo only tests initial class definition, so **Can-Retransform-Classes: true** is not needed.

### 5.3. Building and Running

~~~bash
mkdir -p out

javac --release 17 -d out UnregisterLab.java

jar cfm unregister-agent.jar agent.mf -C out .

java -javaagent:unregister-agent.jar \
     -cp unregister-agent.jar UnregisterLab
~~~

The JAR contains the main class and all nested classes. On Windows PowerShell or cmd.exe, type the java command on a single line:

~~~text
java -javaagent:unregister-agent.jar -cp unregister-agent.jar UnregisterLab
~~~

### 5.4. Output

~~~text
CALLBACK_ENTERED=true
REMOVED=true
ACTIVE_AT_REMOVE=1
LATE_CALLBACK_SKIPPED=true
DRAIN_BLOCKED_UNTIL_RELEASE=true
EVENTS_AFTER_DRAIN=1
ACTIVE_AFTER_DRAIN=0
SHUTDOWN_OK
~~~

**Verification:** The core logic above was compiled with **javac --release 17** and run successfully on **OpenJDK 24** in a temporary directory. The actual test passed assertions for a real in-flight JVM callback, remove returning true, the simulated late callback being skipped, and the waiter completing only after release. The code has not been tested on every JVM vendor/build; re-run it on your target JDK.

### 5.5. What Does Each Line Mean?

| Line | Evidence |
| --- | --- |
| CALLBACK_ENTERED=true | The JVM actually invoked the transformer for Subject |
| REMOVED=true | The exact instance was unregistered |
| ACTIVE_AT_REMOVE=1 | There was an unfinished callback at the moment remove returned |
| LATE_CALLBACK_SKIPPED=true | The gate blocked a direct transform call after close |
| DRAIN_BLOCKED_UNTIL_RELEASE=true | awaitZero could not finish while the callback was waiting |
| EVENTS_AFTER_DRAIN=1 | The callback admitted before stop still completed |
| ACTIVE_AFTER_DRAIN=0 | No admitted in-flight callbacks remain |
| SHUTDOWN_OK | All invariants of the test passed |

**LATE_CALLBACK_SKIPPED** is a **simulated unit test**, and must not be described as "the JVM definitely emitted a callback after remove." The JVM only allows that to happen per the API; you cannot force every execution to exhibit that interleaving.

## 6. Why Is CountDownLatch Better Than sleep?

If you only do:

~~~java
Thread loader = new Thread(() -> Class.forName("..."));
loader.start();
Thread.sleep(100);
inst.removeTransformer(transformer);
~~~

the test does not know whether the callback has entered yet. A slow machine might not have defined the class yet; on another machine the callback might have already finished. That is a flaky race test.

In the demo, **ENTERED.await** only completes after the real callback calls ENTERED.countDown. The callback pauses at RELEASE.await until main permits it to proceed. The waiter thread uses **awaitZero** to verify the drain condition independently. The test uses bounded wait/join timeouts, so if a thread gets stuck it throws an **AssertionError** instead of pretending to succeed.

Distinguish between a **real JVM callback** and a **simulated transform call to test the guard**. Combining these two checks is stronger than hoping the JVM produces a late callback on every run.

## 7. Complete Shutdown for a Collector/Exporter

For an agent with a queue and runtime hooks, the sequence is:

~~~text
ACTIVE
   |
   v
CLOSE_ADMISSION       transformerGate.close(), hookGate.close()
   |
   v
REMOVE_TRANSFORMER    removeTransformer with exact reference
   |
   v
DRAIN_PRODUCERS       inFlight callbacks and runtime hooks drop to 0
   |
   v
DRAIN_QUEUE           consumer processes all accepted events
   |
   v
FLUSH_EXPORTER        receive flush/ack result
   |
   v
CLOSE_RESOURCES       exporter.close()
   |
   v
STOPPED
~~~

If the exporter is asynchronous, **inFlight==0** only proves callbacks have left the collector; **it does not prove the queue or network buffers are empty**.

~~~java
// Service-level pseudocode, not a standalone runnable file.
transformerGate.close();
hookGate.close();

boolean removed = instrumentation.removeTransformer(transformer);

transformerGate.awaitZero();
hookGate.awaitZero();

queue.awaitDrained();
exporter.flush();
exporter.close();
~~~

The remove call may return false if it was already removed earlier, but only a state machine managing ownership allows treating that as an idempotent stop. If flush times out, it must report **FLUSH_FAILED/TIMED_OUT**, rather than assuming all events were delivered.

## 8. Injected Runtime Hooks Do Not Disappear on Remove

If the transformer previously injected:

~~~text
INVOKESTATIC my/agent/Hooks.record()V
~~~

then this instruction remains in the bytecode already installed by the JVM. **removeTransformer does not rewrite those methods**. New invocations and active frames can still call the helper. Therefore, the hook must **no-op when collection is closed**:

~~~java
// Design pseudocode; Gate and exporter are separate components.
public static void record() {
    if (!hookGate.enter()) {
        return;
    }
    try {
        enqueueSafely();
    } finally {
        hookGate.leave();
    }
}
~~~

Do not unload the helper or delete dependencies that the bytecode still needs. If you truly need to remove advice from already-loaded classes, consider **retransformClasses/redefineClasses** within capability and class schema limits, check other transformers in the chain, and verify behavior. removeTransformer does not automatically roll back class definitions.

## 9. Timeouts, Interruption, and Edge Cases

**Timeout:** A callback can get stuck due to classloader locks, I/O, or recursion. You should not wait indefinitely in production. Use **Condition.awaitNanos** or a wait method with a deadline, and when time expires return a **TIMED_OUT** status with the remaining inFlight count instead of declaring DRAINED.

~~~java
// Pseudocode inside Gate using ReentrantLock and Condition.
long remaining = timeout.toNanos();
lock.lock();
try {
    while (inFlight > 0) {
        if (remaining <= 0) {
            return false;
        }
        remaining = zero.awaitNanos(remaining);
    }
    return true;
} finally {
    lock.unlock();
}
~~~

**Interrupt:** If the controller receives InterruptedException, it must propagate it or restore the interrupt flag according to policy. Do not mark drain as successful when the wait was canceled. The demo callback can be interrupted and always decrements inFlight in finally.

**Self-deadlock:** Do not call awaitZero from inside the same transform that called enter, because the callback would wait for itself to leave. The controller should run on a separate thread.

**Logger recursion:** ClassFileTransformer should not hold the gate lock during logging/network I/O; a logger can itself trigger class loads and nested callbacks.

**Native/classloader state:** Do not force Thread.stop on class-loader threads. If shutdown exceeds the timeout, capture a thread dump and choose a safe policy instead of arbitrarily killing a JVM thread holding locks.

## 10. Duplicate Registration, Wrong Instance, and Double Stop

~~~java
ClassFileTransformer a = new MyTransformer();
inst.addTransformer(a, false);

// This is a different object even though it is the same class:
boolean wrong = inst.removeTransformer(new MyTransformer());

// This is the original registration:
boolean right = inst.removeTransformer(a);
~~~

Do not rely on overriding equals/hashCode of a transformer class to replace identity/ownership. Store the exact reference.

If you add the same instance twice, the API removes one most-recent matching registration per remove call. It is best to use a **single owner** and avoid duplicate adds.

If SIGTERM, a shutdown hook, and an operator API call stop at the same time, you need an **ACTIVE → STOPPING → STOPPED** state machine so only **one controller** runs close/remove/drain/flush. Other callers wait for the same completion; this avoids double-closing the exporter, double-flushing, or mistaking remove=false for a critical failure.

## 11. What If a Callback Already Returned Bytes Before Close?

If the transformer modifies bytecode, there are three points in time:

1. Callback arrives after close → gate rejects it, returns null.
2. Callback was admitted but has not returned yet → it can finish or check generation before returning per policy.
3. Callback already returned bytes before close → the JVM may still be verifying/defining the class, and **remove does not retract already-returned byte[]**.

Therefore, a gate does not strictly guarantee "no new class definition carrying advice can exist after time T." If business requirements demand a stricter code-deployment cutoff point, a separate class-loading/quiescence/redefinition strategy is needed. For **stopping collection**, a hook gate/no-op is a different mechanism from removing bytecode.

If the transformer returns null when stopped, that is a no-op per contract. If the transformer returns new data, it must create a **different byte[]** and keep **classfileBuffer immutable**. Do not use unchecked exceptions in the callback as a control-flow mechanism for shutdown; the JVM may still continue the transformation pipeline.

## 12. Mandatory Test Matrix

| Scenario | Assertion |
| --- | --- |
| Gate OPEN | enter=true, inFlight increments |
| Gate CLOSED | enter=false, no increment |
| enter racing close | No callback admitted after close milestone |
| Exception/interrupt in callback | finally decrements inFlight |
| JVM class load of Subject | Real callback enters before removal |
| remove while callback held | removed=true, inFlight can equal 1 |
| Simulated late callback | Returns null, no new event |
| Drain before release | Does not complete |
| Drain after release | inFlight=0 |
| Wrong transformer instance | remove=false |
| Add same object twice | One remove may not clear all |
| Stop twice | No double-close, idempotent state |
| Callback blocks long | TIMEOUT reported clearly |
| Callback thread awaits drain itself | Self-deadlock disallowed |
| Queue still has pending items | Exporter does not close before flush |
| Already instrumented class | Hook can still be called; guard no-ops |
| Multiple class loaders | No race/confusion of className |
| Multiple agents | Stopping this agent does not remove another agent's transformer |
| Stress class loading | No deadlock and event counters accurate |

A stress test may not encounter a late callback even after many iterations. Because the API only says **may**, the absence of a late callback **does not prove safety**. Simulated unit tests and deterministic latch integration tests are required.

## 13. Metrics and Diagnostics

You should separate:

| Name | Definition |
| --- | --- |
| callback_invocations_total | Each time the JVM calls transform |
| callback_admitted_total | Passed the gate while OPEN |
| callback_rejected_total | Arrived after close and was rejected |
| inflight_callbacks | Admitted and not yet left |
| events_enqueued_total | Placed into the queue |
| events_exported_total | Confirmed processed by exporter |
| events_dropped_total | Dropped per policy |
| exporter_pending | Backlogged records |
| shutdown_duration_ms | Time from stop request to STOPPED |
| shutdown_timeout_total | Drain/flush exceeded deadline |
| remove_false_total | No matching registration found |

If **callback_invocations_total** still increases after remove, that is not automatically a bug. What matters is that **admitted_total does not increase after close** and there is no write-after-close. LongAdder.sum() while writers are still running is not an atomic snapshot of all metrics; take the snapshot after producer drain if you need a consistent report.

### 13.1. Common Symptoms

| Symptom | Cause | Fix |
| --- | --- | --- |
| remove=true but callbacks remain | Race allowed by Javadoc | Gate, return null, drain |
| remove=false on first attempt | Wrong reference/never added/already removed | Track registration owner |
| inFlight stays >0 | Missing finally or blocked callback | Thread dump, timeout |
| Negative inFlight | Duplicate leave or leave after failed enter | Assert invariants |
| Events still emitted after stop | Injected hooks or unflushed queue | Separate hook gate and exporter lifecycle |
| Class loading hangs | Logging recursion/lock contention | Reduce blocking in transform |
| Flaky race test | Using sleep, Subject class loaded too early | Latches and exact class filter |
| Events lost on close | Exporter closed before producers/queue drain | Reorder shutdown steps |
| Bytecode still instrumented | remove does not roll back definitions | Hook no-op or valid retransform |

## 14. Self-Check Questions

1. **If removeTransformer returns true, does that guarantee inFlight=0?** No.
2. **Can the JVM invoke the transformer after remove?** Yes, per the Java 17 Javadoc on concurrency.
3. **Close the gate before or after remove?** Before, to block new admissions from the close point onward.
4. **Why do separate AtomicBoolean and AtomicInteger have a race?** Check and increment are not linearized with close.
5. **Why is finally necessary?** To guarantee leave on every exit path of an admitted callback.
6. **Why is CountDownLatch better than sleep?** It signals that a real callback has entered and provides a way to hold it in-flight.
7. **Is the late callback in the demo emitted by the JVM itself?** No, it is a direct call to test the guard.
8. **Can a callback admitted before stop emit after stop?** Yes, when draining accepted work; the exporter must still be open.
9. **Does remove delete injected INVOKESTATIC instructions?** No.
10. **Does inFlight=0 mean the queue is flushed?** No.
11. **Should stop from inside a callback wait for all inFlight?** No, that easily causes self-deadlock.
12. **If remove returns false, should the exporter close immediately?** Not without verifying ownership and producers.
13. **Should you register the same transformer multiple times?** No; one remove only clears the most recent matching registration.
14. **How do you ensure runtime hooks stop emitting?** Use a separate gate/no-op for hooks and drain before closing the exporter.

## 15. Implementation Checklist

- Understand that **removeTransformer only unregisters, it does not drain callbacks**.
- Hold the exact transformer reference and use single-owner registration.
- Make gate check/enter/close atomic with respect to one another.
- Every admitted callback decrements inFlight via finally.
- Close the exporter only after producers drained + queue flushed.
- Have a timeout/interrupt/failure policy when callbacks block.
- Test a real JVM callback actively running during remove.
- Test a simulated late callback and verify no-op.
- Do not hold the gate lock inside the transform body or exporter I/O.
- Injected runtime hooks remain present and become no-ops when collection is closed.
- Make stop idempotent, with no double-remove/double-close.
- Do not promise automatic rollback of class definitions after remove.
- Expose metrics for admitted/rejected/inFlight/queue/flush/drops.
- Run smoke and stress tests on the deployed JDK vendor/version.

## 16. Reference Documentation

- [Java SE 17 — Instrumentation.removeTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#removeTransformer(java.lang.instrument.ClassFileTransformer)): remove contract, boolean return, duplicate instances, and callbacks after removal.
- [Java SE 17 — Instrumentation.addTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#addTransformer(java.lang.instrument.ClassFileTransformer,boolean)): registration and canRetransform mode.
- [Java SE 17 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): class-load callbacks, returning null/new byte[], and immutable input.
- [Java SE 17 — java.lang.instrument package](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): how agents are started and entry points.
- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): thread synchronization for deterministic tests.
- [Java SE 17 — Object.wait/notifyAll](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html): condition waiting and spurious wakeups.
- [Java SE 17 — ReentrantLock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): alternative lock/condition for bounded waits.

**Conclusion:** When an agent stops collection, **removeTransformer is not a barrier guaranteeing callbacks have exited**. **Close the admission gate → remove the exact instance → drain callbacks/hooks → drain the queue and flush → close resources**. You must test both a **real JVM callback actively in-flight during remove** and a **simulated late callback being rejected**, while remembering that **instrumented bytecode is not automatically reverted** just because the transformer was removed.
