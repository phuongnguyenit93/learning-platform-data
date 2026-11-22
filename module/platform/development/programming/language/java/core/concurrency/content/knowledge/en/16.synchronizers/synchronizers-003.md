# Phaser for a Flexible Number of Participants in Java Concurrency

> **Context:** `java.util.concurrent.Phaser` is a Java SE synchronizer for work that proceeds through **multiple phases**, where the **number of participating threads/tasks can change** via `register()`, `bulkRegister()`, and `arriveAndDeregister()`. This lesson belongs to **Synchronizers** and covers Java concurrency in general; Spring-specific content is placed in another chapter.

## 1. Learning Objectives

After this lesson, you will be able to:

- Understand the concepts of **phase**, **registered party**, **arrived/unarrived parties**, and **phase advance**.
- Explain why a barrier with a fixed number of participants is not always suitable when tasks join or leave at runtime.
- Correctly choose among `register()`, `bulkRegister(n)`, `arrive()`, `arriveAndAwaitAdvance()`, `arriveAndDeregister()`, `awaitAdvance(phase)`, and `awaitAdvanceInterruptibly(...)`.
- Distinguish **marking arrival at a barrier** from **waiting for the barrier to open**, and distinguish **deregistering** from merely exiting a method or terminating a thread.
- Design a protocol that registers parties before starting tasks, deregisters exactly once, uses a coordinator, and avoids stalled phases.
- Explain how **registering a participant while a phase is in progress** can affect the current phase rather than automatically meaning "register for the next round."
- Use `onAdvance` to control the termination policy, while recognizing that by default `Phaser` terminates when the number of registered parties reaches 0.
- Understand how exceptions, interruption, timeouts, and `forceTermination()` affect liveness.
- Write and run a Java 17 program with **two initial participants, one participant joining after phase 0, and participants deregistering one by one**.
- Analyze the limitations of `Phaser`: it does not manage threads, does not roll back side effects, and does not replace an event queue or transaction.

**Core idea:** `Phaser` does not "count live threads"; it manages **registered parties** along with **their arrivals in each phase**. A phase advances only when all remaining registered parties required for that phase have arrived or deregistered according to the protocol.

## 2. The Problem: A Variable Number of Participants

Suppose a program processes data in three stages:

1. Workers read and parse input.
2. Some workers continue to transform the data; others exit because their work is done.
3. A new worker is added to validate or aggregate, and then all remaining participants wait for the final stage to finish.

If there are exactly 3 workers from start to finish, a barrier with a fixed party count may suffice. However, in a dynamic pipeline:

- Some workers only participate in the early phases.
- Some workers are created after the first phase.
- Some phases require more workers than the previous phase.
- Some workers finish their own work and **must withdraw** so they do not block the remaining phases.

`Phaser` supports **dynamic registration and deregistration**. This is a key difference compared to `CyclicBarrier`, where the party count is provided in the constructor and cannot be directly increased or decreased via a `register/deregister` pair.

### Visualizing a Phase

```text
PHASE = 3, registered = 4, unarrived = 4

Worker A: do phase 3 step ----------> arrive ----\
Worker B: do phase 3 step ----------> arrive -----+--> advance to phase 4
Worker C: do phase 3 step ----------> arrive -----|
Coordinator: prepare barrier -------> arrive ----/

If Worker C no longer participates in subsequent phases:
Worker C: arriveAndDeregister() instead of arrive()
=> counts as an arrival for the current phase AND reduces registered parties for future phases
```

The essence of the model is not "four callbacks that need to run," but **four registered parties responsible for arriving**. A registered party that forgets to report arrival can cause the phase to wait indefinitely, regardless of idle CPU or whether all other tasks have finished.

## 3. Reading the Core Concepts

| Term | Meaning | Observation API |
|---|---|---|
| **Phase** | Current phase index; typically starts at 0 | `getPhase()` |
| **Registered parties** | Number of registrations currently participating in the Phaser | `getRegisteredParties()` |
| **Unarrived parties** | Number of registrations that have not yet reported arrival in the current phase | `getUnarrivedParties()` |
| **Arrived parties** | Number of registrations that have reported arrival in the current phase | `getArrivedParties()` |
| **Arrival** | Signal that a party has completed its share of work for the phase | `arrive()` |
| **Advance** | Transition to the next phase after enough arrivals | `arriveAndAwaitAdvance()`, final arrival |
| **Deregistration** | Arrival for the current phase and withdrawal of one registration for future phases | `arriveAndDeregister()` |
| **Termination** | State where the Phaser no longer operates as a normal barrier | `isTerminated()`, `forceTermination()`, `onAdvance` |

A registration is **not automatically bound to a specific `Thread`**. `Phaser` does not record a Java thread ID and require that exact thread to arrive. That is the responsibility of the application protocol. You can register in the coordinator and have a worker report arrival, but you must ensure each registration has exactly one arrival/deregistration for each required phase.

### Constructors

```java
Phaser phaser = new Phaser();    // No registered parties initially.
Phaser withMain = new Phaser(1); // Main/coordinator is one party.
Phaser fixedInitially = new Phaser(3);
```

This snippet is inside a method with `import java.util.concurrent.Phaser;`. You can start with 0 and register later, but many workflows are easier to control if the coordinator **holds one registration** so the phase does not advance prematurely while participants are still being added.

**Note:** By default, `Phaser.onAdvance` returns `true` when `registeredParties == 0`, leading to termination when a phase advances with no remaining parties. A `Phaser` created with zero registered parties does not necessarily mean all its methods behave as terminated along every code path; do not infer termination from `getRegisteredParties() == 0` while ignoring the lifecycle contract. To check termination accurately, use `isTerminated()`.

## 4. Structure of Phase Advance

A phase opens/advances when the registrations applicable to that phase **have all arrived or deregistered**. A party signaling that it has reached the barrier is an arrival.

Example with a coordinator + two workers, all registered:

```text
Phase 0: registered = 3
  A.arrive()       -> unarrived 3 -> 2
  B.arrive()       -> unarrived 2 -> 1
  Main.arrive()    -> unarrived 1 -> 0
                     advance: phase 0 -> phase 1
Phase 1: remaining registered parties have a new arrival obligation
```

When the phase advances, the unarrived count is reset to the number of registered parties for the new phase, unless the termination policy causes the `Phaser` to stop.

**Do not read `getArrivedParties()` and manually add numbers for coordination.** The getters return **snapshots that can change immediately**; other callers can arrive, deregister, or register at any time according to the program's protocol.

## 5. Key APIs and Behavior

### `register()`

```java
int phaseAtRegistration = phaser.register();
```

Registers one additional party. The return value is the phase to which the registration applies per the contract; if the `Phaser` is already terminated, the method may return a negative phase number consistent with the terminated state. **Registration does not create a thread or start a task.**

Important: while the `Phaser` is active, the registration can join the **current phase**. If you register while existing parties are waiting for the phase to advance, the new participant is obligated to arrive before the phase can complete.

### `bulkRegister(int parties)`

```java
phaser.bulkRegister(3);
```

Increases the number of registrations at once, useful when you know N workers are needed for the same phase. `parties` must be non-negative; if `parties == 0`, the method adds no registrations. Registering beyond the internal limit can throw `IllegalStateException`.

If you need to register a batch of workers **before submitting tasks**, `bulkRegister` expresses the invariant clearly. Avoid letting workers execute before their obligations are fully registered.

### `arrive()`

```java
int arrivedAtPhase = phaser.arrive();
```

Marks one registration as having reached the barrier of the current phase **without waiting** for the phase to advance. The method returns the phase at which the arrival was recorded (not necessarily the subsequent phase).

A thread can call `arrive` and then do other work, and if it later needs to wait, it should use `awaitAdvance(arrivedAtPhase)`. **Do not call `arrive` twice for the same registration in the same phase**; doing so can throw `IllegalStateException` or corrupt the protocol.

### `arriveAndAwaitAdvance()`

```java
int nextPhase = phaser.arriveAndAwaitAdvance();
```

Both arrives and waits for all required parties of the phase to complete. Under normal operation, it returns the phase after advance (for example, 1 when leaving phase 0). This method **does not respond to interruption by throwing `InterruptedException`**; if you need a timeout or interruptibility, see `awaitAdvanceInterruptibly` combined with `arrive`.

### `arriveAndDeregister()`

```java
int oldPhase = phaser.arriveAndDeregister();
```

Signals completion of the current phase **and withdraws the registration**. This is what a worker should call in the last phase it participates in. It **does not wait** for the remaining parties, and its return value relates to the phase at deregistration—it is not a guarantee that all other tasks have finished.

If you need both to withdraw and to wait for the phase to open, you can do `int p = phaser.arriveAndDeregister(); phaser.awaitAdvance(p);` in an appropriate protocol; after deregistering, the thread becomes an **observer**, no longer a party required to arrive.

### `awaitAdvance(int phase)`

```java
int advanced = phaser.awaitAdvance(phase);
```

Waits until the current phase differs from the passed `phase` value. This API **does not arrive on its own** and **does not require the calling thread to be a party**. Therefore, it is useful for an observer or after having already called `arrive`.

Note: if you pass an already past phase, the method may return immediately; if you pass the current phase and no party reports arrival, it can wait forever. Do not confuse it with `arriveAndAwaitAdvance`.

### `awaitAdvanceInterruptibly(int phase, ...)`

There are two overloads:

```java
phaser.awaitAdvanceInterruptibly(phase);
phaser.awaitAdvanceInterruptibly(phase, 500, TimeUnit.MILLISECONDS);
```

This is illustrative code inside a method; it requires importing `TimeUnit` and declaring/handling `InterruptedException`; the timed overload can also throw `TimeoutException`.

**Subtle point:** calling `awaitAdvanceInterruptibly` **does not arrive or deregister**. Typically a party calls `int p = phaser.arrive();` first, and then waits interruptibly. If the timeout expires or the thread is interrupted, the party that already arrived in that phase remains registered for the next phase. You must have a separate shutdown/cancellation protocol to avoid leaked registrations or workers exiting while the next phase still expects them.

### `forceTermination()`

Puts the `Phaser` into the terminated state, releasing threads waiting for advance according to the contract. It **does not cancel or interrupt tasks currently computing**, nor does it automatically roll back or call `ExecutorService.shutdownNow()`.

After termination, phase-related methods may return negative phase numbers to indicate the state; the application must check for this and exit, rather than continuing to loop as if phases were still advancing normally.

## 6. What Makes Phaser Flexible: Parties Joining and Leaving Between Phases

Suppose two workers A/B together with a coordinator participate in phase 0. After phase 0:

- A and B have one final step in phase 1 and will then withdraw.
- The coordinator registers an additional worker C before closing phase 1.
- C only performs phase 1 work and withdraws.
- The coordinator reaches the phase 1 barrier, waiting for A/B/C.
- After phase 1, only the coordinator remains registered.
- The coordinator withdraws, leading to default termination.

```text
Phase 0:
  Main registered + A + B       = 3 parties
  A, B, Main all arrive         -> phase 1

Phase 1:
  Main + A + B, register C      = 4 parties
  A, B, C arriveAndDeregister  -> only Main remains
  Main arriveAndAwaitAdvance   -> phase 2

After phase 1:
  Main only                     = 1 registered
  Main arriveAndDeregister      -> no parties; terminated
```

This is the model for the Java 17 program below. **The registration counts noted between steps represent the logical state at the described point**, not a claim that calling getters concurrently captures an atomic snapshot of the entire system.

### What Does "Mid-Phase Registration" Mean?

If the coordinator calls `phaser.register()` when phase 1 **is already open and has not yet advanced**, C must have an arrival for phase 1. It is not automatically "deferred to phase 2" just because C is a newcomer.

For applications that need a participant to join **only starting from the next phase**, it is best to use a coordination protocol: the coordinator holds a registration, waits for the current phase to finish advancing, and then registers newcomers **before the coordinator allows the next phase to complete**. You must avoid racing with workers that may already have run ahead to the arrival of the new phase.

## 7. Runnable Java 17 Program

This program demonstrates **dynamic registration/deregistration** with three worker tasks and a main coordinator. The initial workers participate in phase 0 and then phase 1; the new worker participates only in phase 1. `AtomicInteger` counts the work in each phase; `Future.get()` ensures main waits for the tasks to finish before printing counters.

Create the file **`DynamicPhaserDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Phaser;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class DynamicPhaserDemo {
    public static void main(String[] args) throws Exception {
        Phaser phaser = new Phaser(1); // Main owns one registration.
        ExecutorService pool = Executors.newFixedThreadPool(3);
        AtomicInteger phase0Work = new AtomicInteger();
        AtomicInteger phase1Work = new AtomicInteger();
        List<Future<?>> tasks = new ArrayList<>();

        try {
            phaser.bulkRegister(2);
            for (int i = 0; i < 2; i++) {
                tasks.add(pool.submit(() -> {
                    phase0Work.incrementAndGet();
                    phaser.arriveAndAwaitAdvance(); // End of phase 0
                    phase1Work.incrementAndGet();
                    phaser.arriveAndDeregister(); // Exit during phase 1
                }));
            }
            int afterFirstBarrier = phaser.arriveAndAwaitAdvance();
            System.out.println("afterPhase0=" + afterFirstBarrier);

            phaser.register(); // Join before main closes phase 1.
            tasks.add(pool.submit(() -> {
                phase1Work.incrementAndGet();
                phaser.arriveAndDeregister(); // Only participates in phase 1
            }));

            int afterSecondBarrier = phaser.arriveAndAwaitAdvance();
            for (Future<?> task : tasks) task.get();
            System.out.println("afterPhase1=" + afterSecondBarrier);
            System.out.println("phase0Workers=" + phase0Work.get());
            System.out.println("phase1Workers=" + phase1Work.get());
            System.out.println("remainingParties=" + phaser.getRegisteredParties());

            phaser.arriveAndDeregister(); // Main exits, zero registrations.
            System.out.println("terminated=" + phaser.isTerminated());
        } finally {
            phaser.forceTermination();
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("pool did not stop");
            }
        }
    }
}
```

Compile and run:

```bash
javac --release 17 DynamicPhaserDemo.java
java DynamicPhaserDemo
```

**Stdout verified by compiling and running on Java 17:**

```text
afterPhase0=1
afterPhase1=2
phase0Workers=2
phase1Workers=3
remainingParties=1
terminated=true
```

### Step-by-Step Explanation

**`new Phaser(1)`:** main holds one registration. While the two workers have not yet reached the barrier, main can call `arriveAndAwaitAdvance` to wait. Once the workers arrive at phase 0, the new phase opens.

**`bulkRegister(2)` before submit:** two arrival obligations are registered **before** any worker task can run. This avoids the bug where a worker reaches arrival before being counted, or the coordinator advances while still submitting workers.

**`arriveAndAwaitAdvance()` in the two workers:** each worker completes phase 0 work and waits for all participants (A, B, main) to reach the barrier together. After phase 0 advances, A/B perform phase 1.

**`phaser.register()` after the first barrier:** main registers C when phase 1 has already started, but main still holds an arrival obligation, so phase 1 cannot advance before C is registered.

**`arriveAndDeregister()` in A/B/C:** they finish phase 1 and withdraw from subsequent phases. That is why after phase 1 only main remains.

**`Future.get()`:** main waits for all worker tasks to complete. Thus the counters in the output do not depend on worker scheduling even though the tasks run concurrently.

**`main.arriveAndDeregister()`:** after all workers have withdrawn, main withdraws last. With the default `onAdvance`, when registered parties reach 0, the `Phaser` terminates; `isTerminated()` is `true`.

**`finally`:** `forceTermination()` and `shutdownNow()` serve as cleanup for the demo even if main encounters an error. This is a fail-fast strategy for a short example; production code should choose graceful shutdown, timeouts, and explicit cancellation rather than treating `forceTermination` as a way to "automatically clean up all tasks."

## 8. Why Does the Program Above Produce Deterministic Output?

None of the printed lines depend on whether worker A or B is scheduled first:

- `afterPhase0=1` comes from main's phase 0 boundary, ensuring the initial obligations have arrived.
- The two workers A/B each increment `phase0Work` once before arrival; `phase0Workers=2` after awaiting the phase and `Future` completion.
- In phase 1, A/B each increment once, and C also increments once. `phase1Workers=3` after all three `Future`s complete.
- A/B/C all deregister, so `remainingParties=1` with only main left.
- Main withdraws the final party, resulting in `terminated=true` under the default termination policy.
- `AtomicInteger` keeps increments safe when sharing the same variable across multiple threads.
- `Future.get()` ensures exceptions from workers are not swallowed and provides memory visibility to main for the completed work.

If `AtomicInteger` were replaced with `int counter++` across multiple workers, lost updates could occur regardless of whether the `Phaser` barriers are correct, because multiple workers can still increment the counter **concurrently within the same phase**.

## 9. Why Not Use Thread.sleep to Wait for a Phase?

An incorrect approach:

```java
// Do not use sleep as a synchronization protocol.
Thread.sleep(200);
System.out.println(phaser.getPhase());
```

This is an illustrative snippet inside a method declaring `throws InterruptedException`. Sleeping 200 ms does not guarantee workers have finished, does not fulfill arrival obligations, and does not provide an appropriate happens-before boundary.

Instead:

- A party that has work and needs to wait: `arriveAndAwaitAdvance()`.
- A party that has arrived and needs a timed wait: `awaitAdvanceInterruptibly(phase, timeout, unit)`.
- A non-party observer that only needs to know when the phase changes: `awaitAdvance(phase)` or its interruptible variant.
- A caller that needs to know **the task has truly completed** (not just reached the barrier): `Future.get()`/`join()` with a timeout policy.

Time should only be used for timeouts/deadlines and simulating workloads in tests, never as a synchronization contract.

## 10. Differences Between arrive(), awaitAdvance(), and arriveAndAwaitAdvance()

These three calls are related but not equivalent:

```java
int phase = phaser.arrive();
doIndependentWork();
phaser.awaitAdvance(phase);
```

This is illustrative code inside a method. It is conceptually equivalent to "arrive then wait," but allows a window to run other work between the two calls. The thread has **already marked itself arrived** and is not entitled to arrive again in the same phase simply because it did extra work.

By contrast:

```java
int nextPhase = phaser.arriveAndAwaitAdvance();
```

Both arrives and waits at the barrier in a single operation. If there is no work to do while waiting, this is usually clearer.

**Hazard:** if a thread calls `awaitAdvance(currentPhase)` without having arrived for its registration and no one else can perform the arrival on its behalf, the phase cannot advance. This is a logical deadlock: it is waiting for **the very arrival it still owes**.

## 11. Register Before Starting the Task: Avoiding "Arrival Without Registration"

If you start the task first:

```java
// Incorrect order of registration responsibility:
pool.submit(() -> {
    doWork();
    phaser.arriveAndDeregister();
});
phaser.register(); // May happen too late.
```

This is a dangerous illustrative snippet; variables/methods are defined externally.

A worker may reach `arriveAndDeregister()` **before main registers it**. Depending on the current state, the arrival may corrupt another party's obligation or throw an error; the intent "this task owns a dedicated registration" is unprotected.

The correct way:

```java
phaser.register();
Future<?> task = pool.submit(() -> {
    try {
        doWork();
    } finally {
        phaser.arriveAndDeregister();
    }
});
```

This is illustrative code inside a method where `pool` is an `ExecutorService` and `Future` is imported; when the task runs, the registration already exists. **However, this snippet needs an error policy:** if `submit` is rejected or the task **never starts** due to pool shutdown, the registration was added but no worker will deregister it; the coordinator must roll back the registration under a safe protocol. If the task throws an exception, `finally` deregisters to avoid holding up the barrier, but the business task must not be treated as successful merely because the barrier opened.

### Register in the Task or in the Coordinator?

Registering from the worker is possible, but if the coordinator wants to wait for "all N newly submitted tasks," registering when the worker starts has a race: the coordinator could reach the barrier before the worker registers. Having a coordinator hold a party and call **`bulkRegister(N)` before submitting** makes the invariant clearer.

All paths such as rejection, cancellation before task execution, and pool failure must have a plan to withdraw registrations **not yet claimed by a worker**.

## 12. Late Registration and Races While a Phase Is Advancing

Another common mistake:

```java
// Main does not hold the phase open; workers may advance early.
Phaser phaser = new Phaser(2);
startTwoWorkers(phaser);
// Some time later:
phaser.register();  // No guarantee of joining the intended phase.
```

This is an illustrative snippet; `startTwoWorkers` is defined externally. If the two workers have already arrived and the phase has advanced, the new registration may attach to a **different** phase than you expected.

A good design:

- Create a **coordinator registration** to prevent the phase from advancing until setup is complete.
- Clearly define "join current phase" versus "join next phase."
- Keep phase boundaries and registration under a **single-owner protocol**; avoid multiple components registering ad hoc at arbitrary times.
- Before declaring "phase finished," verify **no pending registrations or submissions remain** according to the caller's logic, rather than only looking at the current unarrived snapshot.

There is no API like "registerForExactlyPhaseNAtFutureTime" with the semantics of a task scheduler. If joining on a complex schedule is required, use a coordinator to control when registration occurs.

## 13. arriveAndDeregister(): Leaving a Stage Without Blocking Later Rounds

A party only needs to participate in two phases, while the coordinator will run three phases. After its final round, it should do:

```java
// Final phase this worker participates in:
doLastStage();
phaser.arriveAndDeregister();
```

This is an illustrative snippet inside a method.

If it only calls `arriveAndAwaitAdvance()` in its final phase and then returns from the task **without deregistering**, the `Phaser` still considers the registration active in the next phase. The coordinator may hang waiting for a party that has no code left to arrive.

**Distinguish clearly:**

- `arrive()`: remains registered, still has an obligation in future phases.
- `arriveAndAwaitAdvance()`: remains registered, has arrived and waits for the new phase.
- `arriveAndDeregister()`: withdraws the party for future phases, does not wait for the current phase.
- `forceTermination()`: terminates the entire `Phaser`, not "withdraw one party."

### If a Worker Fails Before the Barrier

One pattern:

```java
try {
    processStage();
} catch (RuntimeException e) {
    recordFailure(e);
    throw e;
} finally {
    phaser.arriveAndDeregister();
}
```

This is an illustrative snippet; `recordFailure`, `processStage`, and `phaser` are in an outer context.

It avoids an abandoned registration when a task **has already started** and can still complete `finally`. However, this is a policy choice: deregistering may allow other parties to **advance even though the stage failed**. If subsequent stages depend on the failed worker's output, you need shared failure state and a fail-fast/termination protocol rather than simply deregistering and pretending it succeeded.

**Do not call `arriveAndDeregister()` twice for the same logical registration.** Deregistration responsibility must belong to one clear path, such as the owner task once it has started, or the coordinator on the rejection path *before the worker starts*.

## 14. Interruption: Phaser Does Not Automatically Remove Interrupted Parties

`arriveAndAwaitAdvance()` and `awaitAdvance()` are **wait methods that cannot be interrupted with a checked `InterruptedException` per their contract**. If the application needs an interrupt-responsive wait, use:

```java
int phase = phaser.arrive();
try {
    phaser.awaitAdvanceInterruptibly(
            phase, 1, TimeUnit.SECONDS);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    handleInterruptedWait(e);
} catch (TimeoutException e) {
    handlePhaseTimeout(e);
}
```

This is an illustrative snippet inside a method; it requires importing `TimeUnit` and `TimeoutException` and application-defined handler methods.

Common pitfall: after `arrive()`, the party **is still registered**; a timeout or interrupt of the **wait** does not cancel the arrival or withdraw the registration. If a worker abandons the task permanently, the coordinator must decide:

- Terminate the `Phaser` because the phase is no longer safe.
- Use an appropriate deregistration protocol when the phase changes, avoiding arriving twice in the same phase.
- Transfer arrival responsibility in later phases to another worker under a controlled protocol.
- Record the failure and ensure remaining parties do not wait indefinitely.

**Do not immediately call `arriveAndDeregister()` after `arrive()` in the same phase just because the timed await failed.** That would be **a second arrival** for the same registration/phase, which can skew the count or throw `IllegalStateException`. You need a controller/termination protocol rather than "fixing" it with another arrival.

### Timeout Differs From Termination

`awaitAdvanceInterruptibly(phase, timeout, unit)` throwing `TimeoutException` only means the thread has not seen the phase advance within the deadline. It **does not call `forceTermination`**, and other parties may still be making valid progress or may actually be stuck.

`forceTermination()` is a separate action affecting the entire `Phaser`, not a harmless local timeout. Only the owner/coordinator should decide to invoke it if the contract permits.

## 15. Phase Termination and onAdvance()

By default, when a phase advances with **zero registered parties**, the `Phaser` becomes terminated. To define a different policy, you can subclass and override `protected boolean onAdvance(int phase, int registeredParties)`.

Example allowing at most three phases:

```java
import java.util.concurrent.Phaser;

public final class ThreeRoundsPhaser extends Phaser {
    public ThreeRoundsPhaser(int parties) {
        super(parties);
    }

    @Override
    protected boolean onAdvance(int phase, int registeredParties) {
        return phase >= 2 || registeredParties == 0;
    }
}
```

This is a **standalone, compilable Java class** in `ThreeRoundsPhaser.java`; it has no `main` method. `onAdvance` receives the phase just completed and the current number of registered parties. With phases starting at 0, the callback returns `true` when phase 2 finishes (or earlier if no parties remain), so the `Phaser` terminates according to the policy.

### Notes on onAdvance

- The callback may be invoked by the thread performing the **final arrival that advances the phase**; do not assume the main thread owns the callback.
- The callback should be **fast and non-blocking**. If it performs long I/O or waits for a party that needs the phase to advance in order to progress, the system can deadlock.
- Returning `true` requests termination, not "advance further."
- Returning `false` allows a new phase to begin, if conditions are met.
- Do not mutate the `Phaser`'s registry inside the callback in a way that creates a self-dependency.
- If you override it to always return `false`, you need **another termination policy**, especially when the registered count reaches 0; do not assume every subclass retains the default termination behavior.

### Termination and Negative Phase Numbers

After termination, some methods such as `getPhase()` may return a negative phase number to indicate the state. Application loops must check `phaser.isTerminated()` or a negative phase after waiting so they do not continue doing meaningless work.

Do not compare an indefinitely increasing phase against integer overflow without a lifecycle policy. Per the API, phase numbers have specific semantics when terminated and wrap around over very long runs; normal applications should use a finite number of stages or clear lifecycle control.

## 16. Coordinator and Worker: Who Owns a Party?

`Phaser` itself does not tie a registration to a thread ID. Therefore, if you have 1,000 jobs but create a `Phaser` with 3 parties, you may be modeling **three worker loops** rather than 1,000 jobs. That is valid if each worker is responsible for arriving in each phase; however, if the business logic wants to wait for **all 1,000 jobs**, the party/registration count must accurately reflect those obligations.

There are three common patterns:

**One party per worker:** suitable when a fixed or temporary worker participates in every phase and deregisters when no work remains.

**One party per job:** the coordinator registers before submitting each job, and the job calls arrive/deregister upon completing its stage. Clarify whether a job spans multiple phases or belongs to a single phase.

**A coordinator as a "gatekeeper" party:** main holds a registration so the phase cannot advance until all participants of a batch have been registered. The coordinator does not need to do heavy work, but must arrive accurately once registration and preparation are complete.

Do not use `getRegisteredParties()` as the count of live threads; do not use `Thread.activeCount()` as a party count; do not treat `ExecutorService.getPoolSize()` as the number of arrival obligations.

## 17. Registration and Submit/Rejection Errors

A real-world pipeline might do:

1. `phaser.register()` for a task.
2. Call `executor.submit(task)`.
3. The task starts, runs, reaches the barrier, and deregisters.

However, if step 2 throws `RejectedExecutionException` because the pool is shut down or saturated, no worker will perform step 3. The registration is left behind, which can cause the phase to wait forever.

You must handle this:

```java
phaser.register();
try {
    executor.execute(() -> {
        try {
            doWork();
        } finally {
            phaser.arriveAndDeregister();
        }
    });
} catch (RejectedExecutionException e) {
    phaser.arriveAndDeregister();
    throw e;
}
```

This is an **illustrative** snippet inside a method where `executor` is an executor that rejects by throwing an exception, `doWork` is defined, and `RejectedExecutionException` is imported. It works when the executor uses a policy that **explicitly throws an exception**, such as `AbortPolicy`.

**Do not apply this blindly to every handler:** `CallerRunsPolicy` can run the task immediately on the caller thread; `DiscardPolicy` can silently drop the task **without throwing an exception**, leaving the registration stranded. Executor ownership and rejection semantics must be well-defined; otherwise, registration cleanup cannot be guaranteed.

In addition, if a task is successfully enqueued but **canceled or returned by `shutdownNow()` before starting**, the worker's `finally` block never runs. The caller/coordinator must know whether the task was executed and manage the registration accordingly.

## 18. A Classic Deadlock: Party Count Mismatched With Actual Workers

Suppose you use `Phaser(3)` with a coordinator and expect two workers, but the executor has only **one thread**:

```java
ExecutorService pool = Executors.newSingleThreadExecutor();
Phaser phaser = new Phaser(3); // main + 2 worker obligations

pool.submit(() -> phaser.arriveAndAwaitAdvance());
pool.submit(() -> phaser.arriveAndAwaitAdvance());
phaser.arriveAndAwaitAdvance(); // Can hang indefinitely.
```

This is an **incorrect illustrative snippet**; do not run it as-is for practice. The first worker can block at the barrier; the second worker **remains in the work queue** with no thread available to run it; main also waits for the second worker. This is **thread starvation deadlock**.

How to handle it:

- Ensure enough workers can **reach the barrier simultaneously** to match the number of concurrently blocking parties required.
- Do not use a small executor to run multiple tasks that must all arrive concurrently in order to make progress.
- Design nonblocking completion/async orchestration, or let registrations represent actual worker loops rather than all queued jobs.
- Use timeouts or `forceTermination` for error paths, but do not treat a timeout as a fix for an architecture that cannot make progress.

A flexible `Phaser` does not create extra threads or add capacity to an executor.

## 19. Comparison With CountDownLatch and CyclicBarrier

| Criterion | `CountDownLatch` | `CyclicBarrier` | `Phaser` |
|---|---|---|---|
| Purpose | Wait for count to reach 0, typically **one-shot** | Repeated rendezvous with a fixed number of parties | Multiple phases with a **variable** number of parties |
| Dynamic participant registration | No register API | No dynamic register/deregister | `register`, `bulkRegister` |
| Withdrawing a participating party | Not in the sense of an individual participant | No direct dynamic deregister | `arriveAndDeregister` |
| Reusability | Does not reset after reaching 0 | Reusable across generations | Advances across phases |
| Interruptible wait | `await` is interruptible | `await` has interruptible/broken-barrier semantics | `awaitAdvanceInterruptibly`; `arriveAndAwaitAdvance` does not throw on interrupt |
| When a party fails | Caller must decide whether `countDown` happens | Has broken-barrier semantics per contract | Does not automatically break on party failure; needs deregister/`forceTermination` policy |
| Behavior when parties = 0 | Latch count=0 -> `await` returns immediately | Barrier parties must be valid per constructor | Can start with zero parties; termination is a separate lifecycle |

### When to Choose Phaser?

- You have **multiple stages** requiring barriers and **the number of participants grows/shrinks**.
- You want a coordinator to manage new batches of workers and allow workers to leave the pipeline.
- You need a termination policy at phase boundaries via `onAdvance`.
- You can manage registration/arrival with a clear protocol and have tests for failure/cancellation.

### When Not to Use Phaser?

- Only waiting for N tasks to finish once: `CountDownLatch` or `CompletableFuture.allOf` is simpler.
- Always having the exact same N workers across every round: `CyclicBarrier` may be easier to understand.
- Needing producer-consumer message passing: use `BlockingQueue`, do not use `Phaser` as a data transport.
- Needing locking to protect shared state in a critical section: `synchronized`, `Lock`, atomics, or ownership.
- Needing multi-resource transactions or durable job orchestration across process crashes: `Phaser` does not provide this.

## 20. Hierarchical Phaser

Java `Phaser` supports constructors taking a parent:

```java
Phaser parent = new Phaser(1);       // Coordinator.
Phaser childGroup = new Phaser(parent, 0);
childGroup.bulkRegister(3);
```

This is an illustrative snippet inside a method. `childGroup` has parent `parent` and manages three local parties. In a multi-tier structure, a child `Phaser` can represent **a single party node** to its parent whenever it has registered parties, reducing contention at the root when the participant count is very large.

### Things to Understand Before Using It

- Parent/child registration and deregistration follow automatic rules when a child transitions from 0 to non-zero or back; it does not simply add three local parties to the parent as three independent registrations.
- Child `Phaser`s are linked to the root phase; phase advances and termination are coordinated across the hierarchy.
- Observing `parent.getRegisteredParties()` does not give the **total number of leaf participants across the whole system**.
- When participant counts are very large or contention on a single `Phaser` is high, hierarchy can improve performance, at the cost of added debugging and lifecycle complexity.
- For most small exercises, a single flat `Phaser` is enough. Use a hierarchy only when there is a demonstrated need and appropriate benchmarks.

According to the Java documentation, the limit on direct registrations on a single `Phaser` is **65,535 parties**; if you need more, consider a hierarchy or another synchronization design. Do not confuse this limit with the number of Java threads allowed to exist.

## 21. Memory Consistency and Happens-Before

`Phaser` does more than count: it also provides synchronization boundaries.

The JavaDoc states: **actions in a thread prior to an arrival operation** *happen-before* actions corresponding to the phase advance; actions observed after the phase advance are ordered **after** the corresponding phase boundary in memory ordering.

Example of two workers building data before the barrier and main reading it:

```java
// Worker A:
resultsA[0] = 10;
phaser.arriveAndAwaitAdvance();

// Worker B:
resultsB[0] = 20;
phaser.arriveAndAwaitAdvance();

// Main, if also registered and participating in the same phase:
phaser.arriveAndAwaitAdvance();
int sum = resultsA[0] + resultsB[0];
```

This is **pseudocode with fragments running across multiple threads**, not standalone code. The guarantee applies only if all three belong to the **same phase** and do not continue mutating the data without synchronization.

### Does Not Imply All State Outside Phaser Is Safe

If A and B both execute `sharedCounter++` during the preceding phase, they can still race with each other before the barrier. Phase advance makes completion/visibility observable, **it does not turn a non-atomic increment into an atomic one**.

Use `AtomicInteger`, have each worker write to its own partition, or use locks/immutable state according to your invariants. In the runnable demo, `AtomicInteger` protects the counters; `Phaser` coordinates the phases; `Future.get()` adds a task-completion boundary.

### When Is Phase Advance Enough, and When Is Future Needed?

- If you need data that workers constructed before arrival and main has crossed the matching phase boundary, `Phaser` provides the necessary synchronization.
- If you need to know whether a worker has **exited its method and run cleanup after arriving/deregistering**, the barrier is not necessarily enough; wait on `Future.get()`/`join()`.
- If a worker calls `arriveAndDeregister()` and then continues performing side effects afterward, main crossing the phase boundary **does not automatically wait** for those side effects.
- If a worker outside the `Phaser` modifies shared data, the barrier does not cover that worker.

That is why the demo calls `task.get()` before printing totals and cleaning up.

## 22. Observing Metrics and Debugging a Stalled Phase

Observation APIs:

```java
int phase = phaser.getPhase();
int registered = phaser.getRegisteredParties();
int arrived = phaser.getArrivedParties();
int unarrived = phaser.getUnarrivedParties();
boolean terminated = phaser.isTerminated();
```

This is code inside a method with a `phaser` variable.

These values help you:

- Know which phase is currently active.
- See how many registrations are currently held.
- See how many obligations have not yet arrived.
- Distinguish an active `Phaser` from a terminated one.

**Caution:** getters may be read at different instants. Do not assert `registered == arrived + unarrived` from a composite snapshot taken across three concurrent calls if phases or registrations are changing between reads.

### Investigating a Hang

1. Check `phase`, `registered`, `unarrived`, and `terminated`.
2. Check whether tasks were submitted successfully; check for rejections or cancellations before execution started.
3. Check which workers reached the barrier and which are still running or blocked in work prior to the barrier.
4. Check whether a worker exited without calling `arriveAndDeregister`.
5. Check thread pool capacity: are tasks blocked at the barrier holding all worker threads while another party is still waiting in the executor queue?
6. Check whether someone called `awaitAdvance` without arriving for an owed registration.
7. Check for late registrations or double arrivals.
8. If the cancellation policy allows, use `forceTermination` to release waiters and then address the root cause.

### Thread Dump

```bash
jcmd <PID> Thread.print -l
```

Replace `<PID>` with the actual process ID. A thread dump may show waiting/parking states in `Phaser`/`ForkJoinPool.managedBlock` or related primitives. A `WAITING (parking)` thread is not automatically a deadlock: legitimately waiting at a barrier also shows a waiting state.

To prove a bug, combine stack traces with the **business-level list of registrations/participants**; `Phaser` itself has no API to list party identities by task ID.

## 23. Common Mistakes

1. **Creating a `Phaser` with a party count matching expected tasks without running enough worker threads.** Can cause thread-starvation deadlock.
2. **Forgetting to register a worker before it arrives.** The arrival can skew another party's obligation or throw an exception.
3. **Registering too late when the current phase has already advanced.** The new worker may join a different phase than intended.
4. **Adding a new registration during a waiting phase with no one arriving for it.** The phase stalls.
5. **Forgetting to deregister a worker that has finished its work.** The next phase still expects that worker's arrival.
6. **Deregistering twice for the same logical registration.** Corrupts state or throws `IllegalStateException`.
7. **Confusing `arrive()` with `arriveAndAwaitAdvance()`.** `arrive` does not wait, so the thread can proceed ahead of other parties.
8. **Calling `awaitAdvance(current)` without arriving for one's own registration.** The thread waits for a condition that it is itself blocking.
9. **Calling `awaitAdvanceInterruptibly` and assuming you have arrived.** It only waits; a party must arrive separately.
10. **Timing out after `arrive` and immediately calling `arriveAndDeregister` in the same phase.** Risks a double arrival; a clear failure/termination policy is required.
11. **Assuming an interrupt automatically reduces `Phaser` registered parties.** It does not; deregistration/termination must be managed explicitly.
12. **Assuming `forceTermination` kills workers and rolls back all side effects.** It does not; it only terminates barrier coordination.
13. **Treating `getRegisteredParties` as the count of live threads.** A registration is a logical obligation, not bound to thread identity.
14. **Putting long I/O or locks waiting on other tasks inside `onAdvance`.** Can block phase advance and cause deadlock.
15. **Overriding `onAdvance` to always return `false` without a shutdown policy.** The `Phaser` may not auto-terminate at zero parties as expected.
16. **Using getters to decide register/arrive based on an unsynchronized snapshot.** State can change immediately.
17. **Ignoring submission rejection after registering.** No worker will arrive, and other parties will hang.
18. **Ignoring task cancellation before execution starts.** The worker's `finally` never runs, leaving the registration stranded.
19. **Handling a worker error by deregistering and treating the phase as successful.** The barrier opening does not confirm that the business stage succeeded.
20. **Using `Phaser` to protect `counter++` across workers.** A barrier does not make updates within the same phase atomic.
21. **Using one-shot `CountDownLatch` semantics for `Phaser` without managing later phases.** A still-registered party must arrive again in the new phase.
22. **Assuming all phase advances happen on the main thread.** The final arrival can come from any worker.
23. **Assuming a terminated `Phaser` means all `Future`s are complete.** Workers may still perform cleanup after deregistering; await completion separately.
24. **Confusing hierarchy party counts with total leaf registrations.** A parent may only see a child `Phaser` as a single node party.
25. **Using `Thread.sleep` so a producer/worker "has time to register."** Timing cannot replace a register-before-execute protocol.
26. **Assuming `awaitAdvance` always blocks.** If the passed phase already differs from the current phase, it can return immediately.
27. **Assuming an `awaitAdvanceInterruptibly` timeout cancels the entire `Phaser`.** No; the timeout applies only to the waiting thread.
28. **Omitting deadlines/alerts for long-waiting phases.** One failed party can make everyone wait forever.
29. **Using `Phaser` as a data queue.** `Phaser` is only for barrier/phase coordination; it does not store or pass messages.
30. **Using `Phaser` as a distributed synchronizer.** It manages synchronization within a single JVM and does not handle node crashes, network partitions, or durability.

## 24. Practice Exercises

### Exercise A — Five Workers, Two Exit After Phase 0

Initialize `Phaser(1)` for the coordinator and call `bulkRegister(5)` before submitting 5 tasks. In phase 0, all five do work; two tasks call `arriveAndDeregister()`, and three tasks call `arriveAndAwaitAdvance()` and then perform phase 1. The coordinator passes barrier 0 and then barrier 1. Check the remaining party count and ensure main does not advance prematurely before registration finishes.

### Exercise B — Late Join at a Phase Boundary

Start with A/B + coordinator; after phase 0, register C/D and submit them. Have A/B/C/D perform phase 1, all deregister, and main withdraw after awaiting phase 1. Use `Future.get()` to confirm task completion. Avoid printing worker sequence numbers since the scheduler does not guarantee order.

### Exercise C — Controlled Timeout

One worker intentionally fails to reach the barrier. The coordinator has already arrived via `arrive()` and then calls `awaitAdvanceInterruptibly(phase, timeout, unit)`. On timeout, the coordinator logs the cause, calls `forceTermination()` under a fail-fast policy, cancels workers, and shuts down the pool. Explain why you should not call `arriveAndDeregister()` again for an already-arrived registration in the same phase.

### Exercise D — Executor With Insufficient Workers

Write a test with two tasks waiting at a barrier while the pool has only one worker thread. Use a test harness timeout to demonstrate that progress is impossible, avoiding an example that hangs forever. Then increase worker capacity or adjust the architecture so both parties can reach the barrier concurrently.

### Exercise E — Custom onAdvance

Create the `ThreeRoundsPhaser` subclass to terminate after three phases. Use two parties executing exactly three rounds. Analyze how the return value from `arriveAndAwaitAdvance` on the final round can signal termination via a negative phase, and why code must check `isTerminated()`.

### Exercise F — Hierarchy

Create a root `Phaser` with a coordinator and two child `Phaser`s, each with 3 local parties. Compare the root's registered count against the total local parties, and explain why the root does not directly store six registrations. Write a test where all local parties pass one phase and then shut down cleanly.

## 25. Review Questions and Answers

**Q1.** Why is `Phaser` suitable when the number of participants changes?  
**Answer:** It supports `register`/`bulkRegister` to add parties and `arriveAndDeregister` to withdraw parties across multiple phases.

**Q2.** Does `new Phaser(1)` create a worker thread?  
**Answer:** No. It registers one initial logical party; the caller must execute code and report arrival for that party.

**Q3.** Does `arrive()` wait for the remaining parties?  
**Answer:** No. It marks the party as arrived and returns the current phase.

**Q4.** How does `arriveAndAwaitAdvance()` differ from `arrive()`?  
**Answer:** It both reports arrival and waits for the phase to advance.

**Q5.** When a worker stops participating, why must it call `arriveAndDeregister`?  
**Answer:** If it only arrives and never returns, its registration remains in the next phase, which can cause the barrier to wait forever.

**Q6.** Does `awaitAdvance(phase)` require the caller to be a party?  
**Answer:** No. A non-party observer can wait; the method does not arrive on its own.

**Q7.** Does an `awaitAdvanceInterruptibly` timeout automatically deregister the party?  
**Answer:** No. It only ends the caller's wait; registration and arrival state require a separate protocol.

**Q8.** Can you call `arriveAndDeregister` right after `arrive()` on the same party and phase to "clean up"?  
**Answer:** No. That is a double arrival for the same registration/phase and can corrupt obligations. You need an owner-managed failure/termination protocol.

**Q9.** If a new worker registers while phase 2 is open, is it guaranteed to only have to arrive starting in phase 3?  
**Answer:** No. An active registration generally applies to the current phase; a coordinator must manage the phase boundary.

**Q10.** Why can a single-worker executor + two tasks waiting at a barrier deadlock?  
**Answer:** The first task holds the worker thread and waits for the second task to arrive; the second task stays queued with no worker thread to run it.

**Q11.** Does `getRegisteredParties()` tell you how many Java threads are alive?  
**Answer:** No. It counts logical registrations, not thread identities.

**Q12.** When registered parties reach 0 in a default `Phaser` and the phase advances, what happens?  
**Answer:** The default `onAdvance` returns `true`, causing the `Phaser` to terminate.

**Q13.** Does `onAdvance` returning `true` mean "advance further"?  
**Answer:** No; `true` signals termination.

**Q14.** Does `forceTermination()` immediately stop all computing business tasks?  
**Answer:** No. It terminates synchronization and releases waiters; it does not kill threads or roll back side effects.

**Q15.** If both workers execute `counter++` before the barrier, will main see the exact total after crossing the barrier?  
**Answer:** Not necessarily. The barrier does not fix lost updates occurring between workers within the phase; atomic, locked, or partitioned writes are required.

**Q16.** Why does the demo program output `phase0Workers=2` and `phase1Workers=3`?  
**Answer:** A/B participate in both phases; C is registered after phase 0 and participates only in phase 1.

**Q17.** Does `arriveAndDeregister` mean "all of the worker's `finally`/cleanup code has finished"?  
**Answer:** No. The worker may still run code after arrival; the caller must wait on `Future`/`join` if it needs full task completion.

**Q18.** If the pool rejects a task after registration, what must be done?  
**Answer:** Handle the rejection and withdraw the registration per policy if the task never started, or terminate/cancel in a controlled manner. Do not leave an orphaned party blocking the phase.

**Q19.** Do `getArrivedParties` and `getUnarrivedParties` provide a single shared atomic snapshot when read sequentially?  
**Answer:** No. Phases or registrations can change between reads.

**Q20.** When should you choose `CountDownLatch` over `Phaser`?  
**Answer:** When you only need to wait for a set of operations to complete **once** and do not need dynamic multi-phase participation.

## 26. Practical Design Checklist

Before using `Phaser` in a project, check:

- **Scope:** Which job/pipeline does the `Phaser` belong to, and who owns its lifecycle?
- **Party identity:** Does each registration correspond to a worker, a task, or a coordinator?
- **Registration timing:** Are parties added **before tasks can arrive**?
- **Phase protocol:** Which tasks must arrive in each phase, and which must deregister?
- **Join semantics:** Do newcomers join the current or next phase, and who holds the phase open?
- **Failure handling:** Will a task failing before the barrier leave other parties waiting indefinitely?
- **Submission/cancel:** Do rejections and cancellations before task start have a registration cleanup path?
- **Interrupt:** Do you need an interruptible/timed wait or an uninterruptible barrier?
- **Timeout:** If a phase stalls, does the coordinator have a deadline and a `forceTermination` policy?
- **Termination:** Default last-party deregistration or a custom `onAdvance`?
- **Executor capacity:** Are there enough workers for all blocking parties to reach the barrier together?
- **State safety:** Does data used across phases have proper publication, atomicity, and ownership?
- **Completion:** Do you need to wait on the barrier, on `Future`, or both?
- **Observability:** Phase, registered/unarrived counts, last progress, task failures, and deadlines?
- **Scalability:** Does a large participant count require a hierarchical `Phaser` or a different model?
- **Testing:** Test one/zero/many parties, dynamic register/deregister, phase timeouts, worker failures, and shutdown?
- **Version:** Deploy on a JDK supporting the required APIs (e.g., Java 17).

A solid `Phaser` design starts from **a table of each party's arrival responsibilities per phase**, not from a guessed thread count.

## 27. Official References

- [Java SE 17 — Phaser](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Phaser.html): constructors, `register`/`bulkRegister`, `arrive`/`await`/`deregister`, termination, `onAdvance`, hierarchy, and memory consistency.
- [Java SE 17 — CyclicBarrier](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CyclicBarrier.html): cyclic barrier with a fixed number of parties.
- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): one-shot count-down synchronization.
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): submit, `Future`, shutdown, and lifecycle.
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): completion and memory-consistency effects.
- [Java SE 17 — AtomicInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): atomic counters used in the example.
- [Java Language Specification 17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): Java Memory Model, happens-before, and thread communication.

**Summary:** `Phaser` is a multi-round barrier for a **flexible set of participants**. Its power comes from `register`/`bulkRegister` and `arriveAndDeregister`, but that same flexibility increases the need to manage ownership, phase timing, and failure paths. Register properly before workers can arrive, give each party a clear obligation per phase, deregister on exit, and use `Future.get` when you need to know a task has actually finished. If a participant goes missing, `Phaser` cannot guess how to recover: you need a coordinator, a timeout/interrupt policy, and consistent recovery/termination.
