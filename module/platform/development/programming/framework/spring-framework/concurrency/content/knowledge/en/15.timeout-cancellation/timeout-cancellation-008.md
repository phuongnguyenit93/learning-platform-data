# Preventing Expired or Obsolete Work from Continuing to Cause Side Effects

## 1. The Problem: Expiring Does Not Mean the Work Stopped

A Spring application receives requests to generate reports, send emails, update order statuses, or call payment APIs. The work runs asynchronously via `@Async`, `Executor`, or `CompletableFuture`. A user cancels, a request times out, or a newer request supersedes an older one. **The old worker may still be running and perform a side effect**: writing to the database, publishing a message, sending an email, calling an external API, writing a file, mutating a cache, or triggering an irreversible action.

Example:

1. 10:00:00, the user requests exporting report version 7. Worker A starts computing.
2. 10:00:02, the user changes filters; version 8 supersedes version 7.
3. 10:00:03, the controller marks request A expired, or future A completes with a timeout.
4. 10:00:05, worker A finishes computing and **overwrites version 8 with version 7's result**.

The caller no longer waiting for A **does not stop** A from mutating state. Similarly, if a user leaves a checkout page, that alone does not prove the order or payment must be cancelled. The application needs a **business contract**: when is work considered obsolete, and which side effects must be blocked.

**Goals after this lesson:**

- Distinguish wait timeouts, `CompletableFuture` state, interrupt signals, business cancel commands, and actually blocking side effects.
- Design `deadline`, cancellation tokens, revision/generation, and `latest-wins` rules where appropriate.
- Understand the race condition between **checking validity** and **performing a side effect**.
- Guard write boundaries with atomic checks, optimistic locking, fencing tokens, and idempotency.
- Know the limits of `@Async`, `Future.cancel(true)`, `CompletableFuture.cancel(true)`, `orTimeout`, and `get(timeout)`.
- Choose how to handle side effects outside the database: outbox, downstream token validation, compensation, or reporting uncertain state.
- Write and run Java 17+ examples with deterministic output, including bug scenarios caused by races.
- Test shutdown, retries, stale tasks, and observe blocked side-effect counts in Spring.

This lesson belongs to **Timeouts and Cancellation** in Spring Framework – concurrency. The focus is not “how to make a future return a timeout error”, but **how to guarantee work no longer has authority to produce side effects once invalidated under defined policy**.

## 2. First: Distinguish Five Concepts

| Concept | Meaning | Automatically prevents future side effects? |
| --- | --- | --- |
| Caller wait timeout | `Future.get(timeout, unit)` did not receive a result before the deadline | **No**; worker may continue |
| Future exceptional completion | `CompletableFuture.orTimeout` or `completeExceptionally` changes future state | **No**; background task may still run |
| Computation cancellation request | `Future.cancel(true)` may try interrupting; `CompletableFuture.cancel` has its own semantics | **Does not guarantee** stopping I/O, preventing code continuation, or rolling back |
| Business invalidation | Stale version, superseded by newer request, job cancelled, business deadline passed | Must **check and enforce rules** at the right boundaries |
| Side effect already committed/sent | DB committed, external API accepted command, email dispatched, message published | Usually **cannot be “unsent”**; needs policy, idempotency, compensation |

An operation may become **obsolete for the UI** yet still **require completion in business terms**. For example, an HTTP timeout after a bank accepted a transfer request does not allow automatically issuing a reverse transfer or resending without an idempotency key. “Obsolete” must be defined by domain rules, not browser deadlines alone.

### 2.1. Side Effects to Identify

- **In-JVM:** mutating singleton beans, caches, shared collections, writing temp files.
- **In database:** INSERT/UPDATE/DELETE, updating job state, committing transactions.
- **Over network:** sending emails, webhooks, push notifications, calling payment services, creating third-party orders.
- **Via message broker:** publishing events, sending commands, or acknowledging messages.
- **Out-of-process:** spawning processes, writing to object storage, provisioning cloud resources.

Putting `if (cancelled) return;` before every operation eliminates much wasted work. Yet if **cancellation happens after the check and before the write**, the side effect can still happen. That is the central check-then-act gap of this lesson.

## 3. State Model and Defining “Still Valid”

No single model fits every business domain, so document an explicit state machine. For example, a preview-generation job might look like:

```text
PENDING ---> RUNNING ---> SUCCEEDED
   |            |   \----> FAILED
   |            |
   |            +-----> CANCEL_REQUESTED ---> CANCELLED
   |            |
   |            +-----> EXPIRED
   |
   +-----> CANCELLED / EXPIRED
```

The arrows are conceptual: in a real system you must resolve **state contention** when one thread commits success at the exact instant another requests cancellation. Never allow arbitrary transitions from every state to every other state.

Work may produce a side effect only when every applicable condition holds, for instance:

```text
job.state == RUNNING
AND job.generation == currentGeneration(resourceId)
AND job.deadline > authoritativeNow()
AND operationId has not been applied yet
AND business invariant still holds
```

The `generation` condition fits “only the latest result may be written”. The deadline condition fits when results lose value after a cutoff time. Idempotency keys apply when the same command can be retried. They solve **different problems** and should not be used interchangeably.

### 3.1. Who Decides Validity?

- **Caller/UI:** can signal it no longer needs the result, but should not act as the source of truth for committed transactions.
- **Business service:** defines rules for “when a job may commit”, cancellation authority, and conflict responses.
- **Database/authoritative store:** holds revision, state, deadline, idempotency keys, and enforces atomic transitions.
- **Downstream:** if side effects happen outside the system, downstream needs a way to reject stale tokens or accept idempotency keys whenever possible.
- **Worker:** checks early to save resources and performs a final check at the commit boundary; never rely solely on local state when running multiple replicas.

When multiple requests update the same resource, an `AtomicBoolean` inside one worker is **insufficient** to synchronize across instances or JVM restarts. Execution authority and generation must live in shared storage when policy requires cluster-wide consistency.

## 4. Timeouts and Cancellation in Java: Reading API Contracts Accurately

### 4.1. Future.get(timeout, unit)

`future.get(2, TimeUnit.SECONDS)` bounds **how long the caller thread waits**. If expired, it throws `TimeoutException` to the caller; that does not mean the task stopped. The task can still complete in the background and produce side effects.

A conceptual example:

```java
Future<?> task = executor.submit(() -> sendEmail());
try {
    task.get(2, TimeUnit.SECONDS);
} catch (TimeoutException ex) {
    // Only know the caller waited too long.
    // sendEmail() may still be running or already finished sending.
}
```

This is a **fragment** requiring definitions for `executor`/`sendEmail`, Java imports, and an error policy; it is not a standalone runnable program. To cancel the task, you can **request** `task.cancel(true)`, yet you still must design business checks, client timeouts, and idempotency.

### 4.2. Future.cancel(true)

The `Future.cancel(boolean)` contract allows attempting to cancel a task. With implementations like `FutureTask`, if the task is running and the executing thread is known, `cancel(true)` can send an **interrupt** signal. It is not a forced thread-kill mechanism: code can ignore interrupts, I/O may not respond, or side effects may already have happened.

- If the task has not started, successful cancellation can prevent it from starting.
- If the task is running, interruption is a **cooperative** signal; it does not auto-rollback transactions or cancel an HTTP request already processed downstream.
- Once a `Future` is marked cancelled, `get()` is no longer a tool to prove physical work stopped; with background execution, observe actual stop status.
- The boolean return value depends on implementation and races with completion; do not treat it as proof an action was reversed.

### 4.3. CompletableFuture.cancel(true) Has Special Semantics

Per Java 17 Javadoc, `CompletableFuture.cancel(mayInterruptIfRunning)` completes the future with `CancellationException` if not yet completed; **the `mayInterruptIfRunning` parameter has no effect in this implementation**, because interrupts are not used to control computation.

Therefore:

```java
CompletableFuture<Result> stage =
        CompletableFuture.supplyAsync(() -> blockingCall(), executor);

stage.cancel(true);
```

is a **fragment** that does not guarantee `blockingCall()` is interrupted, does not guarantee HTTP/DB calls are cancelled, and does not stop subsequent logic in the supplier if already running. For cooperative stopping, use an explicit signal and check at checkpoints; for critical effects, use a **freshness guard at commit**.

### 4.4. orTimeout and completeOnTimeout

`orTimeout(timeout, unit)` completes the `CompletableFuture` itself with `TimeoutException` if not yet completed by the deadline. `completeOnTimeout(fallback, timeout, unit)` similarly completes it with a **fallback value** if the deadline wins the race. Neither means the source worker stopped.

Be careful with:

```java
CompletableFuture<Result> task = startAsync();
CompletableFuture<Result> timed = task.orTimeout(2, TimeUnit.SECONDS);
```

`orTimeout` returns **the same** `CompletableFuture` it was called on in standard Java APIs; do not assume it creates an isolated wrapper that only changes the caller's view. The Future can be marked timed out while the already-submitted supplier continues running.

`completeOnTimeout(defaultValue, ...)` carries another hazard: downstream callbacks reacting to normal completion can run with **the fallback value**. If a callback uses that fallback to mutate business state, verify that behavior is explicitly permitted.

### 4.5. Behavior Selection Table

| Need | Java API / mechanism | Caveat |
| --- | --- | --- |
| Caller must not wait past SLA | `get(timeout)` | Does not stop worker |
| Stage completes with error on expiration | `orTimeout` | Does not cancel side effects |
| Stage returns fallback at deadline | `completeOnTimeout` | Fallback can trigger normal callbacks |
| Request stopping submitted task | `Future.cancel(true)` | Interrupt depends on implementation; needs cooperation |
| Mark a `CompletableFuture` cancelled | `CompletableFuture.cancel(true)` | Does not use interrupts to control source |
| Stop useless work between phases | Atomic cancellation flag / token + interrupt check | Stops early, but has check-then-act race |
| Prevent writing stale value in DB | Conditional write / optimistic lock by generation | Check + mutation must be atomic |
| Prevent stale command in external system | Downstream checks fencing token or idempotent protocol | Requires downstream support |
| Do not lose jobs on restart | Durable queue / job store / outbox | In-memory Future is insufficient |

## 5. Java 17+ Example: Timeout Happened, Yet Side Effect Continues

This example intentionally demonstrates **behavior to avoid**. A worker waits on a latch; `main` times out the future; then `main` opens the latch so the worker performs the side effect. Using latches makes execution order explicit instead of relying on `Thread.sleep`.

File `TimeoutStillRunsDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class TimeoutStillRunsDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicInteger effects = new AtomicInteger();

        try {
            CompletableFuture<String> result =
                    CompletableFuture.supplyAsync(() -> {
                        started.countDown();
                        try {
                            release.await();
                        } catch (InterruptedException ex) {
                            Thread.currentThread().interrupt();
                            throw new IllegalStateException(ex);
                        }
                        effects.incrementAndGet();
                        return "stored";
                    }, executor);

            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("worker did not start");
            }

            result.orTimeout(0, TimeUnit.MILLISECONDS);
            try {
                result.join();
            } catch (CompletionException ex) {
                System.out.println("future-error="
                        + ex.getCause().getClass().getSimpleName());
            }

            release.countDown();
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("worker did not stop");
            }
            System.out.println("effects-after-timeout=" + effects.get());
        } finally {
            release.countDown();
            executor.shutdownNow();
        }
    }
}
```

Compile/run:

```bash
javac TimeoutStillRunsDemo.java
java TimeoutStillRunsDemo
```

Stdout on normal completion:

```text
future-error=TimeoutException
effects-after-timeout=1
```

**Explanation:** the worker started and blocked on `release`, allowing `orTimeout(0, ...)` to complete the future exceptionally before the worker resumed. `main` observes `TimeoutException`; only afterward does it open the latch. The worker still increments `effects` because there is no business guard before the side effect. `executor.awaitTermination` ensures the side effect finished before reading the counter.

This directly proves that **future state** is not **permission to produce side effects**. Do not fix it merely by adding `exceptionally(...)` so the future “has no error”; that only hides the issue further.

## 6. First Line of Defense: Cooperatively Stopping Before Unnecessary Work

A worker may execute several phases:

```text
received
  -> validate input
  -> load data
  -> compute result
  -> prepare change
  -> commit effect
```

Once work is known to be obsolete, stop as early as possible:

1. Before starting a CPU/I/O-heavy phase.
2. After a blocking call returns.
3. Before submitting the next subtask.
4. After receiving a cancellation signal from caller/broker.
5. **Right at the side-effect commit boundary**, using an atomic check when high correctness is required.

Within a single JVM, a simple token can be `AtomicBoolean cancelled` or `AtomicLong generation`. Workers can check `Thread.currentThread().isInterrupted()` when using interruption-based cancellation; when catching `InterruptedException`, typically exit cooperatively and restore interrupt status if propagating the signal.

### 6.1. Java 17+ Example: Token Blocks Work Before Side Effect

File `CooperativeGuardDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public class CooperativeGuardDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicBoolean obsolete = new AtomicBoolean(false);
        AtomicInteger effects = new AtomicInteger();

        try {
            Future<Boolean> job = executor.submit(() -> {
                started.countDown();
                release.await();
                if (obsolete.get()) {
                    return false; // Do not write when the request has been superseded.
                }
                effects.incrementAndGet();
                return true;
            });

            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("worker not started");
            }

            obsolete.set(true);
            release.countDown();

            System.out.println("applied=" +
                    job.get(5, TimeUnit.SECONDS));
            System.out.println("effects=" + effects.get());
        } finally {
            release.countDown();
            executor.shutdownNow();
        }
    }
}
```

```bash
javac CooperativeGuardDemo.java
java CooperativeGuardDemo
```

Output:

```text
applied=false
effects=0
```

Because `main` set `obsolete=true` before opening the latch, the worker observes the signal and skips the side effect. `AtomicBoolean` guarantees visibility/atomicity of the state variable within one JVM.

**Limitation:** if `main` sets `obsolete=true` **after the worker checked** yet **before the worker called `incrementAndGet()`**, the side effect can still occur. A boolean guard reduces wasted work, but does not strictly guarantee “no write after becoming obsolete”.

### 6.2. Java 17+ Example: Future.cancel(true) and Cooperative Interruption

File `InterruptCooperationDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public class InterruptCooperationDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch neverReleased = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        AtomicBoolean sawInterrupt = new AtomicBoolean(false);
        AtomicInteger effects = new AtomicInteger();

        try {
            Future<?> task = executor.submit(() -> {
                started.countDown();
                try {
                    neverReleased.await();
                    effects.incrementAndGet();
                } catch (InterruptedException ex) {
                    sawInterrupt.set(true);
                    Thread.currentThread().interrupt();
                } finally {
                    finished.countDown();
                }
            });

            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("worker not started");
            }

            boolean accepted = task.cancel(true);
            if (!finished.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("interrupt not observed");
            }

            System.out.println("cancel-accepted=" + accepted);
            System.out.println("interrupt-seen=" + sawInterrupt.get());
            System.out.println("effects=" + effects.get());
        } finally {
            executor.shutdownNow();
        }
    }
}
```

```bash
javac InterruptCooperationDemo.java
java InterruptCooperationDemo
```

Output when no external interrupts affect the program:

```text
cancel-accepted=true
interrupt-seen=true
effects=0
```

Here, the `Future` from `ExecutorService.submit` can interrupt the worker waiting on `CountDownLatch.await()`; the worker **proactively** handles `InterruptedException` and skips the effect. It illustrates cooperative interruption—it does **not** prove every JDBC/HTTP call is interruptible or that every `CompletableFuture.cancel(true)` sends an interrupt.

## 7. The Check-Then-Act Gap: Checking Right, Writing Wrong

A more dangerous scenario:

```java
if (generation.get() == expectedGeneration) {
    // The task can be superseded right here.
    writeResult();
}
```

**Reading status** and **writing the side effect** are two separate events. Another thread can cancel or supersede in between. `AtomicLong` makes reading the generation atomic and visible, yet **does not automatically turn** both steps into one transaction.

### 7.1. Java 17+ Example: Reproducing the Race with Latches

File `CheckThenActRaceDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

public class CheckThenActRaceDemo {
    public static void main(String[] args) throws Exception {
        AtomicLong generation = new AtomicLong(1);
        AtomicInteger effects = new AtomicInteger();
        CountDownLatch checked = new CountDownLatch(1);
        CountDownLatch continueTask = new CountDownLatch(1);
        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            long capturedGeneration = generation.get();

            Future<Boolean> stale = executor.submit(() -> {
                if (generation.get() != capturedGeneration) {
                    return false;
                }
                checked.countDown();
                continueTask.await();
                effects.incrementAndGet();
                return true;
            });

            if (!checked.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("not checked");
            }

            generation.incrementAndGet(); // New request superseded it.
            continueTask.countDown();

            System.out.println("stale-applied=" +
                    stale.get(5, TimeUnit.SECONDS));
            System.out.println("effects=" + effects.get());
        } finally {
            continueTask.countDown();
            executor.shutdownNow();
        }
    }
}
```

```bash
javac CheckThenActRaceDemo.java
java CheckThenActRaceDemo
```

Output:

```text
stale-applied=true
effects=1
```

The schedule was coordinated: the worker checked generation 1; `main` bumped it to 2; then the worker resumed and wrote. The worker “did check”, yet **the validity conclusion was no longer true at the moment of the effect**.

**Lesson:** checkpoints before CPU/I/O-heavy phases are great for performance; for effects impacting business correctness, you must have an **atomic rule at the side-effect boundary**, or a downstream contract capable of rejecting stale tokens. Do not treat separate `if` checks as a transaction.

## 8. Fencing Tokens, Generations, and Atomic Checks at Commit

A common solution for “only the latest work may write” is a **generation** (also called revision, epoch, or fencing token). Whenever a new request supersedes an old one, the authoritative store increments the generation. The worker carries the generation issued at start. Before applying the effect, the **data owner** only admits tokens matching the current generation.

### 8.1. Why Is a Fencing Token Better Than a Simple Cancelled Flag?

| Mechanism | What does it do? | Limitation |
| --- | --- | --- |
| `AtomicBoolean cancelled` in worker | Stops early in the same JVM | Does not synchronize across processes; check-then-act race |
| In-process `AtomicLong generation` | Detects stale results when the same process owns the resource | Restarts/other replicas have separate state; still requires atomic commit |
| DB-stored generation | Shared token across replicas/restarts | Requires proper transaction/conditional update |
| Downstream-checked fencing token | Downstream rejects commands from old owners/leases | Effective only if downstream **actually checks** the token |
| Idempotency key | Blocks duplicate effects of **the same command** | Does not block **an older command with a different ID** |
| Business deadline/state | Blocks effects after specified time/state | Must be checked at the authoritative source and within the commit boundary |

Tokens should increase monotonically or follow a verifiable version order. Do not use each instance's local clock timestamp as an absolute ordering if clocks can drift, and never arbitrarily reset tokens after JVM restarts while old workers could still arrive late.

### 8.2. Java 17+ Example: Atomic Gate Simulated with synchronized

File `AtomicFencingDemo.java`:

```java
import java.util.HashSet;
import java.util.Set;

public class AtomicFencingDemo {
    static final class Store {
        private long generation = 1;
        private int effectCount;
        private final Set<String> completedIds = new HashSet<>();

        synchronized long current() {
            return generation;
        }

        synchronized long supersede() {
            return ++generation;
        }

        synchronized String commit(long token, String operationId) {
            if (token != generation) {
                return "STALE";
            }
            if (!completedIds.add(operationId)) {
                return "DUPLICATE";
            }
            effectCount++;
            return "APPLIED";
        }

        synchronized int effects() {
            return effectCount;
        }
    }

    public static void main(String[] args) {
        Store store = new Store();
        long oldToken = store.current();
        long currentToken = store.supersede();

        System.out.println("old=" +
                store.commit(oldToken, "old-command"));
        System.out.println("current=" +
                store.commit(currentToken, "new-command"));
        System.out.println("retry=" +
                store.commit(currentToken, "new-command"));
        System.out.println("effects=" + store.effects());
    }
}
```

```bash
javac AtomicFencingDemo.java
java AtomicFencingDemo
```

Output:

```text
old=STALE
current=APPLIED
retry=DUPLICATE
effects=1
```

All of `current/supersede/commit` are synchronized on one `Store`; inside `commit`, **token check + duplicate check + effect application** happen in the same critical section. Another thread cannot interleave `supersede` between `commit`'s check and effect on that instance.

**Limitation to remember:** this code **only** holds within a single JVM and a single `Store`. In a multi-replica Spring application, the database or durable state store must enforce the equivalent mechanism. If the effect is sending an external email, holding Java `synchronized` cannot make the remote system reject an email after cancellation.

### 8.3. Choosing the Linearization Point

When commit and cancel occur concurrently, define which wins:

- If **cancel commits first**, every effect using the old token must be rejected.
- If **the effect commits first**, a late cancel command may report “too late to cancel”; never claim a rollback occurred.
- If business rules require “cancel before a timestamp” rather than before commit, evaluate and enforce the deadline at the authoritative boundary.
- For multi-minute work, do not hold a lock across the entire pipeline; protect only **the state transition / side-effect step** with a short transaction, keeping I/O steps outside.

This is a policy about **authoritative ordering of state transitions**, not a requirement that the scheduler run in wall-clock order.

## 9. Database Implementation: Conditional Writes and Optimistic Locking

In multi-instance systems, a stronger mechanism is a database statement that performs **check and mutation together**. Conceptual SQL example (PostgreSQL-style illustration; requires concrete schema, indexes, transactions, and state mappings):

```sql
UPDATE report_jobs
SET state = 'READY',
    result_ref = :result_ref
WHERE job_id = :job_id
  AND generation = :expected_generation
  AND state = 'RUNNING'
  AND expires_at > CURRENT_TIMESTAMP;
```

Inspect the updated row count:

- **1 row:** at the moment the database executed the UPDATE under proper transaction semantics, the conditions held and the DB effect was applied.
- **0 rows:** the job may have been cancelled/superseded, expired, completed elsewhere, or never existed. Do not unconditionally retry with stale data; classify the cause per business rules.
- **Database/transaction error:** state may not have committed; verify transaction outcome and idempotency before retrying.

For complex boundaries, use JPA `@Version`/optimistic locking or custom repository conditional updates. Never run `SELECT status`, wait a few seconds, and then run an unconditional `UPDATE`: that is a check-then-act race.

### 9.1. When Both State and Outbox Must Be Written

If the side effect is emitting an event to another service, write **state transition + outbox record** in **the same database transaction**:

```text
BEGIN TRANSACTION
    UPDATE job WHERE generation = expected AND state = RUNNING;
    if updatedRows != 1 -> ROLLBACK and report STALE/EXPIRED;
    INSERT outbox(eventId, operationId, generation, payload);
COMMIT
```

This is **pseudocode**, not standalone runnable SQL. Use unique constraints / idempotency keys on event or operation IDs to curb duplicates. An outbox relay worker publishes events with explicit retries and delivery tracking.

**Critically important:** the transaction guarantees **state + outbox commit together**; it **does not** guarantee downstream **never receives an old event** if the job is superseded **after the outbox committed**. If policy states “old commands must not take external effect once a newer request has won”, consumers/downstream services need generation/fencing validation at the point of **accepting the effect**. Checking only on the publisher right before sending still leaves a check-send race.

### 9.2. Fencing Tokens Downstream

Example of a service receiving a command to update a cache/resource:

```text
Command:
  resourceId = report-42
  generation = 18
  operationId = update-report-42-18

Downstream:
  if generation < currentGeneration(resourceId): REJECT_STALE
  if operationId already applied: DEDUPLICATE
  otherwise: apply and store generation/operationId ATOMICALLY
```

Downstream must maintain authoritative state it can check. If it merely trusts a passed `generation` field without storing and comparing it, the token **never blocks** stale requests.

**Difference from idempotency:** version 17 and version 18 commands have **different `operationId`s**. Idempotency stops command 17 from running twice, whereas only **fencing** stops command 17 from applying **after** version 18 has already been recognized as newer.

## 10. Spring @Async: Separating Result Preparation from Side-Effect Boundaries

In Spring, `@Async` normally applies through a proxy when `@EnableAsync` is present and the method is invoked on a Spring-managed bean. The controller may receive a `CompletableFuture` very early while the worker is still running.

To avoid stale side effects, separate:

1. **Worker/compute:** reads immutable input, computes result or builds payload; checks cancel/deadline periodically.
2. **Commit service:** **atomically** checks generation/state/deadline and writes business state/outbox inside a transaction.
3. **Delivery worker/downstream:** handles external side effects with idempotency, fencing, and appropriate retries.
4. **Caller/status API:** distinguishes `SUCCEEDED`, `SKIPPED_STALE`, `CANCELLED`, `TIMED_OUT`, `FAILED`, `UNKNOWN` instead of a bare boolean `done`.

### 10.1. Service-Splitting Pattern (Spring Snippet, Not a Standalone javac File)

```java
// File in Spring project: ReportWorker.java
@Service
public class ReportWorker {
    private final ReportCommitService commitService;

    public ReportWorker(ReportCommitService commitService) {
        this.commitService = commitService;
    }

    @Async("reportExecutor")
    public CompletableFuture<CommitOutcome> generate(
            ReportCommand command) {
        // Input should be an immutable snapshot.
        // Computation task can check token to stop early.
        String preparedResult = calculate(command);

        // Separate service owns transaction/conditional update.
        CommitOutcome outcome = commitService.applyIfCurrent(
                command.jobId(),
                command.generation(),
                preparedResult);

        return CompletableFuture.completedFuture(outcome);
    }
}
```

The snippet above is a **design fragment**, requiring definitions for `ReportCommand`, `CommitOutcome`, `calculate`, imports, the `reportExecutor` bean, and repositories. Do not copy verbatim expecting it to compile.

Part of `ReportCommitService` might be designed as:

```java
@Service
public class ReportCommitService {
    private final ReportRepository repository;
    private final OutboxRepository outbox;

    public ReportCommitService(
            ReportRepository repository,
            OutboxRepository outbox) {
        this.repository = repository;
        this.outbox = outbox;
    }

    @Transactional
    public CommitOutcome applyIfCurrent(
            long jobId, long generation, String result) {

        int updated = repository.writeIfRunningAndCurrent(
                jobId, generation, result);
        if (updated == 0) {
            return CommitOutcome.SKIPPED_STALE;
        }

        outbox.addForCommittedResult(jobId, generation);
        return CommitOutcome.APPLIED;
    }
}
```

Repository and enum names here illustrate **contracts**, not built-in Spring APIs. The repository must execute an atomic conditional update; the outbox must share **the same transaction** with the update and enforce appropriate unique constraints. `@Transactional` must be properly intercepted—for example, called from another bean through a Spring-managed proxy. If the Spring transaction is not actually active, “write job + outbox in one transaction” becomes a false promise.

**Do not** place `@Transactional` on a private method and call `this.applyIfCurrent(...)` from the same bean assuming the transaction proxy applies under default proxy configuration.

### 10.2. In Controllers, Timeout Is Not a Payment Cancel Command

For best-effort report generation, a request timeout can mark a job `EXPIRED` and cancel the worker if the contract permits. For payments, however, a timeout from an external API may mean **UNKNOWN**: downstream committed while the response was lost. In that case, query status by operation ID rather than creating a duplicate transaction or claiming cancellation succeeded.

A safe rule:

- **Preparation steps** can be discarded when no longer needed.
- **Committed steps** must be acknowledged, reconciled, or compensated per business rules.
- **In-flight external steps** may have an immediately unknown outcome; never blindly redo them.

### 10.3. @Async, CompletableFuture, and Cancellation

When a Spring `@Async` method returns `CompletableFuture<T>`, the caller holds a future representing the invocation. Calling `future.cancel(true)` does not automatically create a durable business cancellation token. Nor should the interruption semantics of an executor-specific `Future` be inferred from `CompletableFuture.cancel`.

A clearer design lets the caller invoke a **cancel command** with business effect—for instance transitioning `RUNNING` to `CANCEL_REQUESTED` or incrementing generation in the database. The worker checks the token to stop early, while the commit service checks authoritative state at the effect boundary.

## 11. Deadlines: Which Clock and Who Has Authority to Evaluate?

There are two kinds of deadlines:

- **Local elapsed-time deadline:** uses `System.nanoTime()` or `Duration` to measure elapsed time **within the same JVM**, unaffected by wall-clock adjustments. For example, a 200 ms computation budget.
- **Business expiration timestamp:** uses a durably stored `Instant`/timestamp and an authoritative time source, typically evaluated on the database or state-owning service. Used for jobs spanning multiple replicas or restarts.

Example local checkpoint (Java fragment):

```java
long deadlineNanos =
        System.nanoTime() + TimeUnit.MILLISECONDS.toNanos(200);

if (System.nanoTime() - deadlineNanos >= 0) {
    // Local budget exhausted; should stop preparation phase.
}
```

This illustrates a reasonably small budget; choose comparison and overflow handling appropriate to real durations. `System.nanoTime()` only measures **time intervals**, not an epoch timestamp to persist in a DB or compare across two JVMs.

Using `Instant.now()` independently on workers across replicas to decide commits can cause discrepancies when clocks skew. When strict consistency is required at the database boundary, use the database's clock inside **the same statement/transaction** guarding the effect and define rules for commits near the deadline boundary.

### 11.1. Propagating Deadlines to Subsequent Steps

If a request has a 2-second overall deadline, do not give every HTTP client retry an independent 2 seconds creating a 10-second total. Propagate remaining budget or an absolute deadline with a clear time source across layers; client connect/read/total timeouts must fit within the remaining budget.

If the budget runs out before calling an external API, skip when policy permits. Once the API request has been sent, a timeout is insufficient to know whether it applied side effects; you need an operation ID and reconciliation.

## 12. Do Not Apply “Latest-Only” to Every Domain

Latest-wins fits **previews, search suggestions, temporary image renders, UI draft predictions, and discardable stale computations**. It does not automatically fit commands that **record obligations, place orders, charge fees, or submit transactions**.

| Domain | Can old work be discarded? | Policy usually required |
| --- | --- | --- |
| Search suggestions | Yes, per session/query version | Generation/sequence per session; do not render stale responses |
| Unpublished PDF preview | Usually yes | Skip if stale version; commit by revision |
| Dashboard-only calculation | Yes when old data is no longer needed | Cancellation token + latest-wins cache update |
| Best-effort marketing notification | Depends on opt-out and send window | Check consent/expiry right at delivery; idempotency |
| Mandatory invoice email | Cannot arbitrarily drop once invoice was issued | Durable job, status audit, idempotent delivery |
| Payments / transfers | Cannot infer from HTTP timeout | Durable command ID, status lookup, reconciliation |
| Order status updates | Only when invariants allow | Optimistic lock/version, state machine, transaction |
| Mandatory audit | Cannot skip because caller left page | Persist event/outbox before acknowledging |

**Principle:** before blocking stale side effects, define “stale” from domain rules. A task timing out in the UI does not mean business authority to execute has expired.

## 13. External Side Effects: Why `if (cancelled)` Cannot Guarantee Safety

Suppose a worker sends an HTTP request to an external service:

```text
Worker          Local DB          External API
  |
  | check generation=8
  |-------------------------> (no effect yet)
  |
  |                        cancel/supersede to generation=9
  |
  | HTTP POST(generation=8) ---------------------->
  |                                              writes effect
```

Even though the local database already recorded generation 9 before the HTTP POST, a local pre-POST check cannot prevent the external API from processing version 8. **The final boundary controlling an effect is the system accepting the effect.**

Strategies depending on downstream capabilities:

1. **Downstream supports fencing/version checks:** pass resource ID and generation; the receiver atomically checks the token and updates state. This is the strongest approach when stale commands must be rejected.
2. **Downstream supports idempotency keys:** protects against duplicate retries; you still need business ordering/versioning if an older command with a different ID must not overwrite newer state.
3. **Transactional outbox + consumer:** guarantees delivery coupled to internal transactions; does not automatically eliminate stale deliveries after outbox commit.
4. **Reservation / prepare-commit protocol:** if the API supports reserving and confirming, define when a command takes effect and how reservations expire/cancel.
5. **Compensation / reconciliation:** when an effect already occurred or state is unknown, use business reversal/reconciliation; never pretend atomic rollback exists over HTTP.
6. **Avoid emitting effects after expiration** by having the final sender/decision-maker enforce policy, understanding that an effect already accepted externally may not be retractable.

Do not hold DB locks for long durations across HTTP calls hoping to prevent every race: locks exhaust connections, cause deadlocks, and do not create distributed transactions with external APIs. Global guarantees require a global protocol or reconcilable states.

## 14. Cancellation Status: Honest Responses to Callers

An API supporting cancellation should not always return “successfully cancelled” merely because it received a cancel request. Possible outcomes include:

- `CANCEL_REQUESTED`: stop intent recorded; worker/downstream has not yet confirmed.
- `CANCELLED`: business rules confirm no future effect is permitted within the guaranteed scope.
- `TOO_LATE`: the effect already committed before cancellation.
- `NOT_FOUND` or `ALREADY_TERMINAL`: job does not exist or already terminated.
- `UNKNOWN`: external request was sent and outcome is not yet known.
- `REJECTED_STALE`: old command rejected by an authoritative boundary.
- `EXPIRED`: expired per authoritative clock and policy.

Illustrative JSON response example (application-designed schema):

```json
{
  "jobId": "report-42",
  "status": "CANCEL_REQUESTED",
  "generation": 9,
  "effectCommitted": false
}
```

Never infer from `effectCommitted=false` at one instant that no external effect is currently in flight. For systems with critical side effects, status endpoints must rely on operation IDs and durable state.

### 14.1. Idempotent Cancel and Retries

Cancel commands should normally be idempotent: resending the same cancel request creates no new side effects. Still, **cancel** and **commit** race, so outcomes can differ depending on the order finalized in the authoritative store. Clients must handle `TOO_LATE`/`ALREADY_TERMINAL` instead of retrying forever.

## 15. Combining with CompletableFuture Pipelines and Callbacks

An easily overlooked bug occurs when the source times out yet an independent callback still runs:

```java
CompletableFuture<Result> source = runAsync();
CompletableFuture<Void> audit =
        source.thenAcceptAsync(result -> persist(result), auditExecutor);
```

This is a fragment. If `source` gets `orTimeout` **before** completing normally, the `thenAccept` callback depending on **normal completion** is skipped. However, **if the callback was already triggered/submitted before timeout/cancel**, cancelling a related future does not guarantee the already-running callback is interrupted or skips side effects.

Additionally, callbacks may attach to **another future**, use manual `complete`, or emit a separate command before timeout. Therefore, never treat normal-only `thenAccept` as the sole commit guard.

**Safer pattern:**

```java
CompletableFuture<Outcome> pipeline =
        source.thenApplyAsync(result ->
                commitService.applyIfCurrent(
                        jobId, expectedGeneration, result),
                commitExecutor);

return pipeline;
```

This fragment is only safe if `applyIfCurrent` **performs an atomic check at the boundary**; naming a method that way does not enforce the condition automatically. Using `thenApplyAsync` only chooses the executor for the commit step; it does not turn a plain `if` into a transaction.

### 15.1. Downstream and Upstream Cancellation Are Asymmetric

Cancelling a dependent future does not always cancel upstream computation; cancelling a source does not guarantee interrupting an already-running callback. In multi-branch pipelines, each branch can have its own state. Carry an **operation context** with job ID, generation, and deadline, and have every side-effect boundary validate its own authority to execute.

### 15.2. Reactor/WebFlux and Timeouts

In reactive pipelines, `timeout`/cancellation operators propagate subscription cancellation signals appropriately; still, they **do not guarantee rolling back side effects** already executed or making every external library stop immediately. Blocking clients offloaded onto workers can continue executing if cancellation is unsupported by the API. Guard with the same principles: idempotency, business state, and fencing/conditional commits where effects take place.

## 16. Deployment Strategy in Multi-Replica Spring Environments

A reference architecture:

```text
HTTP Controller
    |
    | create/cancel/replace command
    v
Job Application Service --transaction--> DB: state, generation, deadline
    |
    | enqueue job ID + expected generation
    v
Durable Queue ---------------------> Worker Instance A/B/C
                                         |
                                         | prepare/compute
                                         | cooperative stop checks
                                         v
                                   Commit Service
                                         |
                                         | conditional UPDATE + outbox
                                         v
                                 authoritative DB
                                         |
                                         v
                                   Outbox Delivery
                                         |
                                         | operationId + fencing token
                                         v
                                Downstream acceptance gate
```

Not every application needs a full queue and outbox; a simple preview problem in one JVM can use local tokens and versioned cache writes. However, **the level of guarantee must match the risk**. Across multiple replicas, an `AtomicBoolean` per pod is insufficient for a global latest-wins invariant.

### 16.1. Ownership Rules

- Controllers only request cancellation; they do not unilaterally write wrong terminal states.
- Job service/DB serves as the source of truth for state/generation.
- Workers may abort work early to save resources, but never decide last-write-wins using local timestamps.
- Commit services check state/revision in the same transaction.
- Downstream checks tokens or idempotency per contract; if unsupported, design reconciliation/compensation.
- Schedulers/retry controllers do not unconditionally replay stale commands.

### 16.2. @Transactional and @Async

`@Async` normally dispatches the method to a worker thread; a transaction on the caller thread does not automatically follow to the worker. `@Transactional` must be placed on a boundary running on the right thread and intercepted by Spring AOP through a bean reference. Avoid calling `this.commit()` inside the same bean when relying on default proxy transactions.

When an exception occurs, determine whether the transaction rolled back or committed before retrying; inspecting `CompletableFuture.isCompletedExceptionally()` alone cannot confirm external effects never happened.

### 16.3. Graceful Shutdown

When the application receives SIGTERM / closes the Spring context:

1. Stop accepting new jobs and update readiness as appropriate.
2. Mark worker lease/cancel intent per contract if work cannot finish within the grace period.
3. Ask tasks to check interruption/tokens at checkpoints.
4. Wait for critical commits within the allowed time limit.
5. Rely on the job store/queue to recover unconfirmed work, using idempotency and fencing to prevent old owners from writing late.
6. Never promise an in-memory `Future` survives process death.

If a task must survive restarts, do not launch work solely with `executor.execute(...)` and return HTTP `202 Accepted` before durable persistence.

## 17. Observability and Alerting: Measure Effects, Not Just Futures

Metrics to distinguish:

| Metric / log | Purpose |
| --- | --- |
| `jobs_expired_total` | How many jobs exceeded their business deadline |
| `cancel_requested_total` | How many cancel commands were accepted |
| `tasks_interrupt_observed_total` | How many tasks actually observed an interrupt signal |
| `effects_skipped_stale_total` | How many commits were rejected due to stale generation/state |
| `effects_applied_total` | How many effects were accepted by the authoritative boundary |
| `effects_duplicate_total` | How many commands with duplicate `operationId` were deduplicated |
| `effects_after_expiration_total` | By policy, is any effect allowed after expiry? If not, alert on this |
| `inflight_external_unknown` | How many external operations still have unreconciled outcomes |
| `queue_wait`, `active_workers`, `rejects` | Impact of overload on deadlines and cancellation |

Logs should include **job ID, operation ID, safe resource ID, generation, expected/current version, deadline, before/after states, and skip reason**. Never log sensitive personal data or full payment payloads.

Control metric cardinality: never turn each job ID into a metric label. Keep IDs in structured logs/traces, while metric labels use bounded sets like `status`, `executor`, and `operationType`.

## 18. Testing Races, Expiration, and Side Effects

Before deploying to production, test **the race conditions themselves**:

1. **Timeout before worker starts:** is the task skipped? Are stale queued tasks discarded appropriately?
2. **Cancel mid-computation:** worker detects token and skips calling downstream.
3. **Cancel right after check, before effect:** reproduce with latches as in `CheckThenActRaceDemo`; the real solution must block it at commit.
4. **Commit wins before cancel:** cancel API returns the accurate state (`TOO_LATE` or equivalent), without pretending rollback.
5. **Cancel wins before commit:** conditional write returns 0 rows; no new outbox effect is created.
6. **Retrying the same `operationId`:** idempotency/dedup prevents a second effect.
7. **Old command arrives after newer command:** downstream fencing rejects the stale token.
8. **Worker dies and restarts:** job recovers per policy; old worker's lease/token is no longer valid.
9. **I/O task unresponsive to interrupt:** does timeout only affect the caller or actually cancel the remote operation? Record `UNKNOWN` accurately when needed.
10. **Multiple replicas:** two workers with the same or different generations cannot overwrite valid results.
11. **Clock skew:** DB authoritative time still evaluates expiry consistently.
12. **Lost response after effect:** retries do not duplicate effects thanks to idempotency/reconciliation.

### 18.1. Unit Tests Do Not Replace Integration Tests

Examples using `AtomicLong`/`synchronized` test concepts in **one JVM**. You need integration tests for conditional UPDATEs (updated row count), transaction rollbacks, unique constraints, outbox, and real database isolation behavior. Use Testcontainers or a test database environment running the actual target engine.

For external APIs, write contract tests with fakes/servers supporting idempotency/fencing, and fault injection at the “request received, response lost” boundary. Never rely on `Thread.sleep` as the sole way to create races; use latches/barriers and bounded timeouts.

### 18.2. Business Correctness Criteria

A system is not proven correct simply because a test shows `cancelledFuture.isCancelled() == true`. Prove invariants such as:

- For resource `report-42`, a successful commit must carry **the current generation at the linearization point**.
- No two distinct commits exist for the same `operationId`.
- When cancellation is finalized before commit, old workers produce no DB effect.
- If an external effect was already accepted before cancellation, the system reports the honest state without “fake cancelling”.
- When `UNKNOWN` occurs, reconciliation runs without re-issuing dangerous commands.

## 19. Common Mistakes

| Mistake | Why it is dangerous | Fix |
| --- | --- | --- |
| “Future timeout means the worker stopped” | Timeouts usually affect only waiting/completion | Check task and guard effects |
| “`CompletableFuture.cancel(true)` always interrupts” | Javadoc says the interrupt flag does not drive this implementation | Cooperative token + authoritative gate |
| “Adding `if (!cancelled)` before writing is enough” | Check-then-act race | Atomic conditional commit / fencing |
| “`AtomicBoolean` suffices for multi-pod Kubernetes” | Each pod has isolated state | Shared authoritative state/generation |
| “Idempotency keys block all stale commands” | Older commands with different IDs can still win | Check version/fencing on the receiver |
| “Outbox prevents stale events from being published” | Outbox guarantees delivery after commit, not downstream freshness | Consumer/downstream gate or policy accepting committed events |
| “HTTP calls already made can still be rolled back via cancel” | External API may already have applied side effects | Idempotency, reconciliation, compensation |
| “Putting `@Transactional` on any method makes it atomic” | Self-invocation/proxy boundaries and transaction scopes may fail | Separate bean, verify transaction and SQL |
| “Leaving the UI page cancels the payment” | UI timeout says nothing about business commit | Distinguish `UNKNOWN`, `TOO_LATE`, `CANCELLED` |
| “Retry until success” | Duplicates side effects, sends stale commands | Bounded retries, idempotency, generation |
| “Use local clock deadlines cluster-wide” | Clock skew and restarts | Authoritative timestamp in shared store |
| “Silently ignore rejected tasks” | Lost work or wrong state | Return error, durable enqueue, or explicit policy |

## 20. Applied Exercise: Report Generation Allowing Only the Latest Version

Suppose users rapidly change report filters. The system runs multiple Spring Boot replicas, workers can take a long time, and results are written to a DB and published as events to refresh the UI.

**Design requirements:**

1. Name the resource `reportId`, plus an operation ID and generation. When a new request arrives, increment generation in the DB and mark old generations stale.
2. Workers receive an immutable command containing `reportId` + `generation` + deadline. During computation, check cancellation signals to stop early.
3. Upon finishing computation, run a conditional UPDATE on `reportId` and `generation` with appropriate state/expiry checks. If 0 rows, return `SKIPPED_STALE` and emit **no** effect.
4. If UPDATE succeeds, write the outbox in the same transaction. Generate a unique idempotency key for the event.
5. Consumers deliver events only to destinations enforcing version/fencing policies; if the UI only wants the latest version, the receiving protocol can reject messages with a lower version than already acknowledged.
6. When callers time out, do not merely call `future.cancel(true)` and delete job state; persist/coordinate cancellation policy.
7. When two workers race to commit, integration tests confirm only the authorized one updates and no duplicate outbox rows exist.
8. When cancellation arrives after DB commit, respond honestly with `TOO_LATE` or equivalent; never erase audit trails.
9. When upstream/downstream is unresponsive, apply timeouts, bounded retries, metrics, and `UNKNOWN` reconciliation.
10. Load-test bursts, executor shutdowns, and rolling restarts; measure stale skips, applied effects, and queue wait.

### 20.1. Self-Assessment Checklist

- [ ] I can distinguish caller timeout from a worker actually stopping.
- [ ] I understand `CompletableFuture.cancel(true)` does not force-interrupt the running source.
- [ ] I know how to use cooperative tokens/interrupts at checkpoints to reduce wasted work.
- [ ] I can reproduce a check-then-act race using latches.
- [ ] I understand why check and commit must be atomic when guaranteeing no stale effects.
- [ ] I know how generation/fencing differs from idempotency keys in purpose.
- [ ] I know how to use optimistic locking / conditional UPDATE when multiple replicas write.
- [ ] I understand the limits of outbox and local pre-send checks for external side effects.
- [ ] I can distinguish `CANCEL_REQUESTED`, `CANCELLED`, `TOO_LATE`, and `UNKNOWN`.
- [ ] I do not automatically cancel critical transactions just because of HTTP/UI timeouts.
- [ ] I verify Spring `@Async`, `@Transactional`, executors, and context at the actual execution boundary.
- [ ] I have tests for cancel-before-commit, commit-before-cancel, retries, and restarts.
- [ ] I observe real side effects, not just future state.

**Conclusion:** to **prevent expired or obsolete work from continuing to cause side effects**, multiple layers are needed: cooperative stopping to save resources, **explicit business validity definitions**, and **atomic enforcement at side-effect acceptance boundaries**. Timeouts and cancellation only alter waiting rights or send stop signals; they do not erase committed side effects. In distributed systems, generation/fencing, idempotency, transaction/outbox, and reconciliation must be designed around each system's **actual required guarantees**.

## 21. Official References

- Java SE 17 — [Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): `get(timeout)`, `cancel`, and cancellation contract.
- Java SE 17 — [CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `cancel`, `orTimeout`, `completeOnTimeout`, dependent stages, and exceptional completion.
- Java SE 17 — [CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): synchronizing steps in concurrency tests.
- Spring Framework — [Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@Async`, `TaskExecutor`, async method return types, and exception handling.
- Spring Framework — [Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): `@Transactional` boundaries and transaction advice application rules.
- Spring Framework — [Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): why self-invocation can bypass advice.

Practice on Java 17+ and verify against your actual Spring version, DB engine, and downstream systems. SQL and Spring snippets in this lesson are explicitly **design patterns**, not out-of-the-box APIs or automatic distributed transactions.
