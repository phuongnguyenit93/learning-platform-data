# Handling InterruptedException and Wait Timeouts Under the Object Monitor Contract

## 1. Problem and objectives

A thread that wants to wait for state modified by another thread (for example, a queue has data, a job has completed) can use **Object**'s monitor together with **wait**, **notify**, and **notifyAll**. The waiting contract must distinguish three outcomes: **condition satisfied**, **timeout expired**, and **interruption request**. They are not equivalent: waking up does not mean success; timing out is not being interrupted; being interrupted is not a business failure of the condition.

This lesson belongs to the **Object Monitor** topic in Java Core. The goal is to write a proper predicate-waiting loop, design timeouts with a total budget, handle **InterruptedException** without losing the cancellation signal, and clearly state the limits of wait timeouts.

## 2. The monitor and wait contract

Every Java object has a monitor. A thread must **own the monitor of that exact object** when calling **wait**, **notify**, or **notifyAll**; typically **synchronized (monitor)** is used. Calling on the wrong monitor throws **IllegalMonitorStateException**.

| Method | Key behavior | Notes |
| --- | --- | --- |
| **monitor.wait()** | Releases this monitor and waits; before returning or throwing **InterruptedException**, the thread must reacquire the monitor. | Does not release other monitors held by the thread; can wake up without notify (spurious wakeup). |
| **monitor.wait(long millis)** | Waits up to the requested limit, can wake due to notify, timeout, or spurious wakeup; **millis = 0** means wait indefinitely. | Negative millis causes **IllegalArgumentException**; exact return timing is not guaranteed. |
| **monitor.wait(long millis, int nanos)** | Adds a nanos part in the range **0..999999**; negative duration/out-of-range nanos is invalid. | Does not promise nanosecond precision. |
| **monitor.notify()** | Selects one waiter on the same monitor to wake up. | Cannot select a specific waiter; it only continues after reacquiring the monitor. |
| **monitor.notifyAll()** | Wakes up the waiters on the same monitor. | Each waiter must recheck the condition itself; not all will succeed in processing. |

**`wait` returning normally does not prove the condition is true**, because there could be a timeout, a notification meant for another condition, or a spurious wakeup. Always check the predicate in a **while** loop under the same monitor:

~~~java
// The fields monitor and ready belong to the same shared object.
synchronized (monitor) {
    while (!ready) {
        monitor.wait();
    }
    // ready == true, checked while owning the monitor.
}

// On the signaling thread's side:
synchronized (monitor) {
    ready = true;
    monitor.notifyAll();
}
~~~

These are two illustrative snippets, not a standalone Java program. The predicate and state-changing operation need the same lock: reading **ready** outside synchronized before calling wait can miss a change occurring between the two steps. Using **if** instead of **while** easily causes the thread to proceed even when the condition is still false.

While **wait** is waiting, it releases the monitor of the target object; upon finishing, it must reacquire the monitor before the caller proceeds. Likewise, **notifyAll** does not hand the monitor to waiters immediately: the signaling thread keeps the lock until exiting synchronized. Therefore, delays may occur after notification or after timeout expiration.

## 3. InterruptedException: propagating the interrupt signal by contract

**Thread.interrupt()** is a cooperative request for a thread to stop or change its work. If the thread is inside **Object.wait**, the wait operation throws **InterruptedException** per the interruption-handling contract; the thread has already reacquired the monitor when the exception is thrown. The interrupt flag is cleared when this exception is thrown, so a caller that only checks the flag again could miss the request if someone swallowed the exception.

The handling policy depends on the calling layer:

- **Low-level methods that can declare throws InterruptedException:** propagate the exception upward so the caller decides cancellation. This is the clearest way not to confuse interruption with timeout.
- **Layers that cannot declare checked exceptions** (for example **Runnable.run()**): when catching, call **Thread.currentThread().interrupt()** to restore the flag and end the waiting work. That way outer layers can still observe the interruption request.
- **Do not write an empty catch, and do not merely log and wait again** without an explicit policy. This swallows the cancellation signal and can leave tasks stuck.
- **Do not routinely both restore the flag and throw InterruptedException** out of habit: a layer propagating the exception already carries the interrupt information; restoring the flag is generally for a catching layer that cannot propagate further.

~~~java
// Inside a Runnable with a field gate of type Gate from the full example.
@Override
public void run() {
    try {
        boolean ready = gate.awaitOpen(java.time.Duration.ofSeconds(3));
        if (!ready) {
            return; // Timed out per contract, not interruption.
        }
        // Continue processing only when the condition is true.
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        return; // Preserve interrupt request so the caller/outer layer can detect it.
    }
}
~~~

The snippet above is a partial example; a standalone program is in section 5. **Thread.interrupted()** reads and clears the interrupt flag; if you only want to inspect without clearing, use **Thread.currentThread().isInterrupted()**. Once the flag has been restored, continuing to run a blocking operation without a cancellation policy can cause it to immediately throw InterruptedException again.

Priority should be clearly specified when **the condition is already true** and **the interrupt flag is already set**. In the sample API below, if the predicate is already true upon entering synchronized, it returns true without needing to wait; interruption only manifests as an exception when the wait call has to handle interruption. If you want "if already interrupted then cancel regardless of state," you must add an explicit check and document a separate contract.

## 4. A timeout is not a single fixed wait call

Suppose the API contract is "wait for the condition within a 2-second budget." The following pattern is **wrong about total time**:

~~~java
synchronized (monitor) {
    while (!ready) {
        monitor.wait(2_000); // Each wakeup grants a fresh 2 seconds.
    }
}
~~~

If wakeups occur multiple times while the predicate remains false, total time can far exceed 2 seconds or never finish. The timeout must not be reset on every iteration. You must measure **elapsed time** and compute the remaining amount.

Use **System.nanoTime()** because it is the appropriate time source for measuring the interval between two readings; do not use **System.currentTimeMillis()** to measure deadlines when the wall clock can jump due to time adjustments. Only subtract nanoTime results to compute elapsed time; do not use nanoTime values as calendar timestamps.

**TimeUnit.NANOSECONDS.timedWait(monitor, remainingNanos)** converts a positive nanosecond budget into an appropriate wait. Always check **remainingNanos > 0** before calling; if you directly call **wait(0)** due to rounding down to 0 ms, the task may wait indefinitely.

Appropriate boundary conventions for a predicate-waiting API:
1. Negative timeout → **IllegalArgumentException**, do not begin waiting.
2. Zero timeout → check the predicate once and return true/false immediately.
3. Positive timeout → wait using the remaining budget, repeating while the condition is not satisfied.
4. Budget exhausted and predicate still false → return **false**, never conflating it with **InterruptedException**.
5. If the predicate is true when the thread reacquires the monitor (even if wall time exceeded the budget due to lock contention), the sample API returns **true**; true reflects the observed state, not proof that the change arrived before an absolute deadline.

Limitation: **synchronized** does not provide a timeout while a thread is contending for the lock *to enter* the synchronized block. Even after wait expires, the thread can be delayed while reacquiring the monitor or being scheduled by the OS. Therefore, the timeout in this lesson is the budget of the condition-waiting loop once inside the monitor, **not a guarantee that the method always returns before a hard cutoff**.

## 5. Compilable and runnable Java 17+ example

Create **MonitorContractDemo.java**:

~~~java
import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.TimeUnit;

public class MonitorContractDemo {
    static final class Gate {
        private final Object monitor = new Object();
        private boolean open;

        void open() {
            synchronized (monitor) {
                open = true;
                monitor.notifyAll();
            }
        }

        /**
         * @return true if open == true is observed; false if
         *         the budget expires while open is still false.
         * @throws InterruptedException if interrupted during wait.
         * @throws IllegalArgumentException if timeout is negative.
         * @throws ArithmeticException if Duration.toNanos() overflows long.
         */
        boolean awaitOpen(Duration timeout) throws InterruptedException {
            Objects.requireNonNull(timeout, "timeout");
            if (timeout.isNegative()) {
                throw new IllegalArgumentException("timeout must be >= 0");
            }

            long budgetNanos = timeout.toNanos();

            synchronized (monitor) {
                long started = System.nanoTime();
                long remainingNanos = budgetNanos;

                while (!open) {
                    if (remainingNanos <= 0) {
                        return false;
                    }

                    // Pass only remaining time, do not reset the budget.
                    TimeUnit.NANOSECONDS.timedWait(monitor, remainingNanos);

                    long elapsedNanos = System.nanoTime() - started;
                    remainingNanos = budgetNanos - elapsedNanos;
                }
                return true;
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Gate alreadyOpen = new Gate();
        alreadyOpen.open();
        System.out.println("Success: "
                + alreadyOpen.awaitOpen(Duration.ZERO));

        Gate neverOpen = new Gate();
        System.out.println("Timeout: "
                + neverOpen.awaitOpen(Duration.ofMillis(30)));

        Gate interruptedGate = new Gate();
        Thread worker = new Thread(() -> {
            try {
                interruptedGate.awaitOpen(Duration.ofSeconds(10));
                System.out.println("Interrupted: false");
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                System.out.println("Interrupted: true");
            }
        });

        worker.start();
        worker.interrupt();
        worker.join();
    }
}
~~~

Compile with Java 17 or later:

~~~text
javac MonitorContractDemo.java
java MonitorContractDemo
~~~

Expected stdout:

~~~text
Success: true
Timeout: false
Interrupted: true
~~~

Explanation: The first Gate is already open, so waiting with **Duration.ZERO** still returns true. The second Gate is never opened, so it returns false when the budget expires. The third Gate does not open and `worker` receives an interrupt request; `wait` handles the interruption with an exception, and `worker` restores the flag before exiting. Even if the interrupt arrives before `worker` calls `wait`, `wait` can still detect the flag when invoked: the example does not depend on whether `worker` has gone to sleep yet.

All accesses to the **open** variable are inside **synchronized (monitor)**. Writing the state then releasing the lock and reading the state after acquiring the lock creates a memory visibility guarantee across threads; the **open** variable does not need `volatile` in this design. **notifyAll()** wakes the waiters so they recheck the predicate once they acquire the lock. Do not call **Thread.sleep** instead of wait inside synchronized: sleep does not release the monitor, which can prevent the signaling thread from acquiring the lock to change the state.

**About arithmetic:** A large Duration can cause **toNanos()** to throw **ArithmeticException**; this is an input not representable within a long nanosecond budget, not a normal timeout. In the example, valid durations are very short so subtracting **System.nanoTime()** is appropriate. When designing a contract with very large or infinite timeouts yourself, decide how to handle oversized values explicitly rather than silently turning them into **wait(0)**.

## 6. Designing the calling contract and handling outcomes

| Situation when acquiring the monitor and checking | Result of awaitOpen | Appropriate caller action |
| --- | --- | --- |
| **open** is already true or observed true after a wakeup | **true** | Proceed with the step requiring Gate to be open. |
| Budget expired and **open** is still false | **false** | Report timeout, perform bounded retry, or choose a fallback path. |
| Interrupted while waiting | Throws **InterruptedException** | Stop the task or pass the cancellation request up to the responsible layer. |
| Negative timeout | Throws **IllegalArgumentException** | Fix the input argument. |
| Duration cannot convert to long nanoseconds | Throws **ArithmeticException** | Constrain the contract to the accepted value domain. |
| Null timeout | Throws **NullPointerException** | Do not pass a null argument. |

If a caller chooses to retry after **false**, it must use a **total budget** for the whole retry procedure; do not re-grant an unlimited timeout on every iteration. You also need to design the predicate to express terminal states adequately: a producer that fails or is canceled might never open the Gate. In real systems, if there are **done**, **failed**, **cancelled**, define branches handling those states; do not merely wait on a boolean that can never become true.

Monitor notifications are not retained like "tickets" for a future wait. Avoiding missed signals comes from **storing the condition state under the same monitor and checking before waiting**, not from the number of notify calls. With multiple waiters waiting on different conditions on the same monitor, **notifyAll** is usually safer than **notify**, even though it may wake multiple threads only for them to wait again.

## 7. Common mistakes and checklist

| Mistake | Why it is wrong | Right approach |
| --- | --- | --- |
| Calling **wait/notify** without holding the right monitor | Violates lock ownership; **IllegalMonitorStateException** | Use the same object in synchronized and when calling. |
| Using **if (!ready) wait()** | Spurious wakeups or notifications that do not make ready true | Use a **while (!ready)** loop. |
| Checking the predicate outside synchronized | Can read stale values and miss signals | Protect every read/write of state with the same monitor. |
| Catching InterruptedException and ignoring it | Loses cancellation signal; uncontrolled waiting | Propagate upward, or restore flag and exit in layers that cannot propagate. |
| Repeating wait with the same timeout | Total budget gets reset | Recompute remaining time after each wakeup. |
| Using **wait(0)** for "0 ms" | Actually waits forever | Check budget expiration before waiting. |
| Thinking notifyAll reports success | Wakeup does not replace condition checking | The predicate determines the outcome. |
| Using **currentTimeMillis** to measure elapsed | Wall-clock adjustments break the deadline | Use **nanoTime** difference. |
| Forgetting lock contention and thread scheduling | Method can return after the deadline | Document the exact timeout scope in the API. |
| Using **sleep** while holding the monitor | Sleep does not release the lock, making it hard for producer to change state | Use wait with a predicate. |

Before finishing your code, ask yourself: (1) Is the predicate always read and modified under the same monitor? (2) Are all waits inside **while**? (3) Does a 0 timeout return immediately? (4) Does each wakeup subtract the time already waited? (5) Does interruption have a separate handling path from false? (6) Does the catching layer propagate or restore the flag and exit cleanly? (7) Does the API state clearly that this is not a hard deadline for the entire method?

## 8. Self-review questions

1. List reasons **wait(1000)** can return normally while the predicate is still false. Why must while be used?
2. When **wait** throws **InterruptedException**, has the thread reacquired the monitor yet, and what is the state of the interrupt flag?
3. Why can five intermediate wakeups turn repeated **wait(2000)** calls into a total duration exceeding 2 seconds? What is the right calculation?
4. How do zero timeout, negative timeout, and oversized duration differ?
5. Why can synchronized + Object.wait not guarantee that the entire call always finishes before an absolute deadline?
6. Why is calling notifyAll only valid when state has been updated under the same monitor? What happens if updated outside the lock?

**Key takeaway:** **Object.wait** is a monitor waiting and coordination mechanism, not a sign of business completion. A proper contract clearly distinguishes **success**, **timeout**, and **interruption**; uses while to check state, remaining wait budget, and a policy for propagating/preserving the interrupt signal.
