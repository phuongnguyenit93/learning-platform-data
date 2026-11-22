# Race Conditions, Deadlocks, and Livelocks: High-Level Identification in Java

In concurrent programming, multiple threads can access data or resources simultaneously. A program can run very fast and still produce wrong results, or all threads may remain alive while no work makes progress. Three foundational issues to distinguish are **race condition**, **deadlock**, and **livelock**. This lesson covers Java in general (Java 17+) and does not go into Spring-specific mechanisms.

Learning objectives:
- Explain where each issue occurs, why it happens, and its impact.
- Look at incorrect results, thread states, thread dumps, and progress indicators for initial identification.
- Know appropriate ways to prevent them without confusing atomicity, data visibility, and lock contention/waiting.

## 1. The Big Picture: Data Safety and Liveness

**Thread safety** concerns keeping results and data invariants correct when multiple threads run concurrently. **Liveness** concerns whether operations can complete rather than getting stuck or looping fruitlessly.

- **Race condition:** the outcome depends on the execution order or timing of concurrent operations, leading to the potential violation of requirements. For example, two threads update a counter simultaneously and lose an increment.
- **Deadlock:** a set of threads are each waiting for conditions/resources held by other threads in that same set, causing none of them to make progress.
- **Livelock:** threads remain active and keep reacting to one another (yielding, aborting, retrying, etc.), but continuously loop without achieving useful progress.

A concise-looking Java operation is not necessarily atomic. With `count++`, the logic involves reading the value, computing the new value, and writing it back. If these steps interleave across threads without proper synchronization, the result can be wrong.

## 2. Race Condition: Wrong Results Due to Interleaved Ordering

### 2.1 How to Identify

Suppose `count = 0`, and two threads both want to increment it once:

| Step | Thread T1 | Thread T2 |
| --- | --- | --- |
| 1 | Read `count = 0` | |
| 2 | | Read `count = 0` |
| 3 | Compute `0 + 1`, write `count = 1` | |
| 4 | | Compute `0 + 1`, write `count = 1` |

The correct value after two increments is **2**, but the actual value is **1**: one update is lost (*lost update*). Another run might produce the right result; this dependence on execution scheduling makes the bug hard to reproduce.

A **race condition** is a concept about correctness depending on timing/ordering. A **data race** has a narrower meaning in the Java Memory Model: two operations access the same variable, at least one of them is a write, and they are not ordered by an appropriate *happens-before* relationship. A data race is often a source of bugs, but the two concepts should not be equated. Besides lost updates, there are *check-then-act* bugs—for example, two threads both check "does not exist yet" and then both insert an element.

### 2.2 Java 17+ Example Reproducing a Lost Update

The program below intentionally lets both threads read the counter before allowing them to write. `CountDownLatch` makes the interleaving schedule predictable in this **demonstration**; it does not make the shared update step atomic.

~~~java
// RaceConditionDemo.java
import java.util.concurrent.CountDownLatch;

public class RaceConditionDemo {
    static class Counter {
        int value = 0;
    }

    public static void main(String[] args) throws InterruptedException {
        Counter counter = new Counter();
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch allowWrite = new CountDownLatch(1);

        Runnable increment = () -> {
            int observed = counter.value;
            bothRead.countDown();
            try {
                allowWrite.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
            counter.value = observed + 1;
        };

        Thread first = new Thread(increment, "first");
        Thread second = new Thread(increment, "second");
        first.start();
        second.start();

        bothRead.await();
        allowWrite.countDown();
        first.join();
        second.join();

        System.out.println("Expected: 2");
        System.out.println("Actual: " + counter.value);
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac RaceConditionDemo.java
java RaceConditionDemo
~~~

Output:

~~~text
Expected: 2
Actual: 1
~~~

**Why is it guaranteed to output 1?** Both threads store `0` in their local variable `observed` before `bothRead` reaches 0. Only after that does the main thread open `allowWrite`, so both threads write `0 + 1`. `join()` ensures the main thread waits for them to finish before printing. In a normal application without two coordinating latches, the bug usually appears intermittently and depends on load/scheduling.

### 2.3 The Right Fix: Make the Operation Atomic or Protect the Invariant

For a standalone counter, `AtomicInteger.incrementAndGet()` provides an atomic increment operation:

~~~java
// AtomicCounterDemo.java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicCounterDemo {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger counter = new AtomicInteger();
        Runnable increment = () -> counter.incrementAndGet();

        Thread first = new Thread(increment);
        Thread second = new Thread(increment);
        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("Actual: " + counter.get());
    }
}
~~~

~~~bash
javac AtomicCounterDemo.java
java AtomicCounterDemo
~~~

The output is always:

~~~text
Actual: 2
~~~

Common options:
- `synchronized` or `Lock`: protects a *critical section* where multiple operations must remain consistent with each other.
- `AtomicInteger`, `AtomicLong`, `AtomicReference`, and atomic update operations: suitable for simple operations on specific shared state.
- Immutable data types, thread-local data, or reducing shared state: often simpler and less risky.
- Concurrent collections such as `ConcurrentHashMap`: keep supported operations safe within the API's guarantees; a "read-then-check-then-write" sequence may still require a compound atomic operation like `putIfAbsent` or `compute`.

**Do not use `volatile` to fix `count++`.** `volatile` guarantees visibility of values and certain memory-ordering constraints, but it does not combine read–compute–write into a single atomic action. Similarly, `Thread.sleep()` only changes execution timing and does not provide any data protection mechanism.

## 3. Deadlock: Threads Waiting on Each Other Indefinitely

### 3.1 Typical Scenario

Suppose there are two independent locks, `lockA` and `lockB`:

~~~text
T1: holds lockA  ──> waits for lockB
                        ▲
                        │
T2: holds lockB  ──> waits for lockA
        ▲               │
        └───────────────┘
~~~

For example, thread T1 enters `synchronized(lockA)` and then requests `lockB`, while thread T2 enters `synchronized(lockB)` and then requests `lockA`. Once each thread holds its first lock, neither can acquire the second. This is a **lock-ordering deadlock**.

The following is **illustrative code showing two execution paths**, not a complete program; assume `lockA` and `lockB` are two shared lock objects:

~~~java
// T1
synchronized (lockA) {
    synchronized (lockB) {
        // Work requiring both A and B.
    }
}

// T2: reverse order, risk of deadlock.
synchronized (lockB) {
    synchronized (lockA) {
        // Work requiring both B and A.
    }
}
~~~

The four classic conditions commonly used to analyze deadlock are: mutual exclusion, hold and wait, no preemption, and circular wait. Breaking an appropriate condition can prevent deadlock in the corresponding lock design.

### 3.2 Symptoms in a Java Application

- Certain requests or tasks stop indefinitely with no completion logs, even though the JVM process is still alive.
- The involved threads wait on each other in a cycle in the *thread dump*: "T1 holds A and waits for B; T2 holds B and waits for A".
- For a `synchronized` monitor, a thread waiting to acquire the monitor is typically in `Thread.State.BLOCKED`. For `ReentrantLock`, the thread may show `WAITING` or `TIMED_WAITING` due to the parking mechanism; **looking at thread state alone is not enough to conclude**.
- CPU usage may be low because many threads are waiting, but low CPU alone does not prove a deadlock.

Gather information when there are signs of hanging (requires JDK tools and the process PID):

~~~bash
jcmd <PID> Thread.print -l
~~~

In Java, `ThreadMXBean.findDeadlockedThreads()` can detect wait cycles involving monitors and *ownable synchronizers* managed by the JVM, such as `ReentrantLock`. The method may return `null` if none are found; it is not guaranteed to detect all types of logical waits, I/O waits, or locks in systems outside the JVM. A single thread dump also cannot prove every hang scenario.

### 3.3 How to Prevent

- **Establish a consistent lock acquisition order** across all execution paths: if both A and B must be acquired, always acquire A before B. With multiple dynamic objects, define a stable order by key/ID; handle tie cases as well.
- Keep lock scopes short, and avoid calling long-blocking operations or hard-to-control external code while holding a lock.
- Where appropriate, use `ReentrantLock.tryLock()` or its timed variant, properly release the lock in `finally`, and have a clear retry/cancellation strategy. Timeouts can help with recovery, but they do not by themselves guarantee that the system always makes progress.
- Avoid unnecessary nested locking; consider a single consistent synchronization point when the invariant to protect is truly one unit.

There is no rule to "add `synchronized` everywhere" to prevent deadlock: holding more locks in different orders can create new wait cycles.

## 4. Livelock: Continuous Reaction Without Work Progress

Two threads or two actors both try to be "polite": when contention occurs, each yields the resource and immediately retries. They can repeatedly detect each other and change direction together:

~~~text
Round 1: T1 detects conflict -> yields; T2 detects conflict -> yields
Round 2: T1 retries immediately -> conflict; T2 retries immediately -> conflict
Round 3: both yield, both retry, ...
Result: there is activity, but the number of completed operations remains 0
~~~

This is a **scenario illustrating the mechanism**; real execution scheduling can break symmetry, so not every retry loop is a livelock. Livelock can also occur when multiple threads continuously abort/defer operations to avoid conflict, or when two sides repeatedly transition states in response to each other.

Common symptoms:
- Logs repeatedly show "retry", "conflict", "yield", "rollback", or state changes without any task completing.
- Threads keep running or waking up frequently; CPU usage may be high, though not necessarily.
- No "holds lock and waits for lock" cycle as in deadlock; a thread dump at a single point in time may not be enough. You need to monitor **progress** over multiple points in time: number of completed operations, retry counts, and processing time.

Remediation:
- Retry with a **limit on attempts or a deadline**; when exceeded, report a clear error or execute a fallback plan.
- Use *backoff* with varying wait intervals, sometimes adding randomness (*jitter*) to prevent two actors from acting in lockstep. This reduces probability rather than providing a formal guarantee of progress.
- Introduce priority ordering, coordinate one side to go first, or use a queue to break symmetry.
- Design retry conditions so they can reach termination; measure completion rate as well, not just CPU activity.

## 5. Quick Comparison During Incident Triage

| Perspective | Race condition | Deadlock | Livelock |
| --- | --- | --- | --- |
| Core issue | Interleaved operations corrupt data/decisions | Parties wait on each other | Parties react and retry forever without completing |
| Are threads running? | Usually still run and finish | Participating threads are blocked/waiting | Active or repeatedly waking up |
| Observable symptoms | Wrong results, lost updates, intermittent bugs | Tasks hang; resource wait cycle exists | Many retries, no increase in completed work |
| Evidence to look for | Shared state, invariants, operation order, synchronization | Lock owners, awaited locks, wait cycles | Retry logs, state transitions, throughput over time |
| Resolution direction | Make operations atomic, protect invariants, reduce sharing | Fixed lock order, reduce lock nesting, appropriate timeouts | Break symmetry, backoff, retry limits, coordination |

**Further distinction from starvation:** a thread waits for too long because other threads continually win the resources/CPU schedule, while those other threads continue making progress. Starvation does not necessarily involve the wait cycle of a deadlock or the symmetric reaction loop of a livelock. A system can also suffer from multiple issues at the same time.

## 6. Practical Identification Workflow

1. **Identify the symptom and invariant.** Is there incorrect data or an incomplete task? Write down the expected result and the observed result (for example, total increment count, number of completed requests).
2. **Isolate shared state and lock acquisition paths.** For incorrect results, find read–modify–write or check-then-act sequences and check whether the entire sequence is protected. For hanging tasks, trace which locks are held and which locks are awaited.
3. **Collect evidence over time.** Capture multiple thread dumps spaced at an appropriate interval, along with logs, retry counts, and completion rates. A single `RUNNABLE` or `WAITING` snapshot is not enough to confirm livelock or deadlock.
4. **Match against the model.** Wrong data due to interleaving -> suspect race condition. Resource wait cycle -> suspect deadlock. Activity/retries with no progress -> suspect livelock. If only one thread is starved while others complete -> consider starvation.
5. **Fix the root cause and verify.** Add concurrency tests, invariant assertions, monitor latency/throughput, and run under varying load levels. Stress tests can help reproduce a race, but a single successful run does not prove the program is race-free.

### Common Misconceptions

- "I added `volatile`, so `counter++` is safe" — **false**; visibility does not replace atomicity.
- "I use `ConcurrentHashMap`, so every sequence of operations on the map is atomic" — **false**; you must consider the contract of each method and multi-step invariants.
- "A few milliseconds of `sleep` fixes the bug" — **not guaranteed**; it only shifts the execution schedule.
- "Low CPU means deadlock, high CPU means livelock" — **insufficient**; you must rely on wait cycles or lack of progress.
- "Seeing `BLOCKED` means there is a deadlock" — **false**; brief lock waiting is normal. You must prove a persistent wait cycle.
- "Using `tryLock` with infinite retries will solve deadlock" — **insufficient**; it can turn into livelock or starvation if there is no progress strategy.

## 7. Self-Check

1. Two threads update `balance` using the "read, compute, write" pattern; occasionally money is lost or over-credited. What is this a sign of? **Race condition**; you must check the atomicity of the entire update and related invariants.
2. T1 holds lock A and waits for B; T2 holds B and waits for A. What is this? **Deadlock**; unify lock ordering or redesign lock scope.
3. Two workers keep detecting conflicts, yielding, and retrying thousands of times, yet no task completes. What could this be? **Livelock**; check logs/throughput and ways to break symmetry and limit retries.
4. One worker waits for a very long time while other workers keep completing. Is this necessarily a deadlock? **No**; it could be **starvation**.

**Key takeaway:** Race conditions threaten **result correctness**; deadlocks and livelocks threaten **liveness**, but through two different mechanisms. Diagnose based on invariants, wait relationships, and actual progress before choosing a fix.