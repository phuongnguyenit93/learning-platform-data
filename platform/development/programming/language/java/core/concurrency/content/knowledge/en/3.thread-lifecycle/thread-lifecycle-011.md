# Distinguishing Thread State and Business State in Java

## 1. Why Must We Distinguish Them?

When building an asynchronous task, we usually want to know both of these things:

1. **What state is the thread currently in?** Has it not started yet, is it runnable, is it waiting on a lock/condition, or has it terminated?
2. **What state is the business work in?** Has the task been accepted, is it currently processing, did it succeed, fail, get cancelled, or does it need a retry?

These two questions are **not equivalent**.

**Thread state** is the state of an execution thread in Java, represented by the JVM via **Thread.State**. It is meant for lifecycle observation and diagnostics at the moment of reading.

**Business state** (also called *task/job/workflow status*) is a state **defined by the application** to represent progress and outcomes that are meaningful to users or business systems. For example, **PENDING → RUNNING → SUCCEEDED/FAILED**.

The most important point: **Thread.State.TERMINATED does not mean the work succeeded; Thread.State.WAITING does not mean the business work is pending; Thread.State.RUNNABLE does not mean the business work is RUNNING.**

This article covers **Java concurrency in general** and JDK APIs. Task management mechanisms, scheduler configuration, or events belonging to Spring are covered in a separate chapter.

## 2. Thread.State: The Six JVM States

Java provides the **java.lang.Thread.State** enum with six values:

| Thread.State | What does the JVM describe? | Example |
| --- | --- | --- |
| **NEW** | The Thread object has been created, but start() has not been called yet. | new Thread(task) |
| **RUNNABLE** | Executing or ready to be allocated CPU time by the scheduler. | Java code running or waiting for its CPU turn |
| **BLOCKED** | Waiting to acquire a **monitor lock** to enter a synchronized block/method. | Another thread holds the same monitor |
| **WAITING** | Waiting indefinitely for another action. | Object.wait(), Thread.join(), CountDownLatch.await() without timeout |
| **TIMED_WAITING** | Waiting for a bounded period of time. | Thread.sleep(...), join(timeout), await(timeout) |
| **TERMINATED** | The Thread's run() method has finished. | Completed normally, returned, or threw an unhandled exception |

Exact notes:

- **RUNNABLE** does not mean the thread is actively using the CPU at the exact moment of measurement.
- **BLOCKED** is the state of waiting for a **synchronized monitor**. A thread waiting on a **ReentrantLock** or an I/O operation may be observed in a different state depending on the API and implementation; do not infer that every kind of "blocking" is Thread.State.BLOCKED.
- **WAITING/TIMED_WAITING** does not tell you why a business task is waiting; it only indicates the waiting mode of the execution thread.
- **getState()** returns a **snapshot**, which can change immediately after it is read.
- **TERMINATED** tells you the thread has stopped; it **does not tell you** whether it completed successfully, threw an error, or stopped due to a cancellation request.
- A Thread object that is TERMINATED **cannot have start() called on it again**; to execute further, a new Thread or another task-execution mechanism is required.

Common lifecycle:

~~~text
NEW --start()--> RUNNABLE --run() ends--> TERMINATED
                    │   ^
                    v   │
           BLOCKED / WAITING / TIMED_WAITING
~~~

This is an overview diagram, not a business state machine. For instance, when a thread inside **run()** is calling **sleep()**, its thread state is TIMED_WAITING even though its task still has the business state **RUNNING**.

### Do Not Use getState() as a Coordination Protocol

The following example is an **anti-pattern**:

~~~java
// Faulty illustration code: worker is a Thread created elsewhere.
if (worker.getState() == Thread.State.TERMINATED) {
    markJobSucceeded();
}
~~~

First, **markJobSucceeded()** is a hypothetical application method, not a JDK API. Second, a thread may have died due to an error. Third, a snapshot cannot replace **join()**, **Future.get()**, a latch, or a completion event with proper synchronization. If you want to know whether a thread has finished, use **join()**; if you want to know the **work outcome**, you must record and check the business state/result.

## 3. Business State: An Application-Designed Model

The JDK does not have a universal enum named **BusinessState** or **JobStatus** suitable for every problem. The application defines its own states according to domain meaning.

A minimal model for a job:

~~~text
PENDING ──picked up──> RUNNING ──completed──> SUCCEEDED
                          │
                          ├── error ───────> FAILED
                          └── cancel ok ───> CANCELLED
~~~

You can add **QUEUED**, **RETRYING**, **TIMED_OUT**, **CANCEL_REQUESTED**, or **PAUSED** depending on requirements; do not add them just because Thread.State also has waiting states. In a real application, you need to define precisely when a transition is allowed to happen.

Example Java enum to model this:

~~~java
enum JobStatus {
    PENDING,
    RUNNING,
    SUCCEEDED,
    FAILED,
    CANCEL_REQUESTED,
    CANCELLED
}
~~~

This is an **illustrative code snippet**; the enum above does not have a **main()** yet. The meaning of each state must be agreed upon: for example, **CANCEL_REQUESTED** only indicates that a cancellation was requested, whereas **CANCELLED** indicates that the application has confirmed the work stopped according to the cancellation policy.

How it differs from Thread.State:

- Business state can be **persisted to a database** for use after the JVM exits.
- Business state can **exist before a thread is created**, or after a thread has finished.
- A single job can pass through multiple threads across different stages; a single worker thread can process many jobs.
- Business state represents the **unit of work** and its outcome under the application's contract, not the internal state of a worker.
- **SUCCEEDED**, **FAILED**, and **CANCELLED** are only reliable when there are clear recording rules; never infer them from thread state.

## 4. Direct Comparison

| Question | Thread state | Business state |
| --- | --- | --- |
| Subject being described | A specific **Thread** | A task, job, order, workflow, or operation |
| Who defines it | JDK: enum Thread.State | Application: enum, record, state machine |
| Observation source | Thread.getState() | Status field, event, Future/result, or storage |
| Stability | Instantaneous snapshot | Follows transitions and business policies |
| Implies success/failure? | No SUCCESS/FAILED state | Can have SUCCEEDED/FAILED |
| Can outlive a thread? | No, tied to the Thread object | Yes |
| Must it be persisted? | No | Depends on requirements; long-running jobs often need persistence |
| Replaces synchronization? | No | No; shared state must still be thread-safe |
| Terminal state | TERMINATED | SUCCEEDED, FAILED, CANCELLED, or another final state |

Some pairs that easily cause confusion:

| Observation | Business state could still be | Why |
| --- | --- | --- |
| Thread **NEW** | PENDING, QUEUED, or not yet bound to a job | Business status may have been created beforehand |
| Thread **RUNNABLE** | RUNNING, RETRYING, CANCEL_REQUESTED | The thread may be executing logic for various stages |
| Thread **WAITING** | RUNNING | The task is waiting on a response/condition to continue its current step |
| Thread **TIMED_WAITING** | RUNNING, RETRYING, CANCEL_REQUESTED | The thread is sleeping/backing off/waiting for a timeout |
| Thread **BLOCKED** | RUNNING | The task has started but is waiting for a monitor |
| Thread **TERMINATED** | SUCCEEDED, FAILED, CANCELLED | The worker finished in any of several ways |

This table only lists **valid possibilities** depending on each application's design; there is no automatic mapping guaranteed by the JDK.

## 5. Runnable Example: Thread Waiting While Job Is RUNNING

File **ThreadAndJobStateDemo.java** (Java 17+):

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;

public class ThreadAndJobStateDemo {
    enum JobStatus { PENDING, RUNNING, SUCCEEDED }

    public static void main(String[] args) throws InterruptedException {
        AtomicReference<JobStatus> status =
                new AtomicReference<>(JobStatus.PENDING);
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch proceed = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            status.set(JobStatus.RUNNING);
            started.countDown();
            try {
                proceed.await();
                status.set(JobStatus.SUCCEEDED);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }, "job-worker");

        System.out.println("before start: " + status.get());
        worker.start();

        started.await();
        System.out.println("after started signal: " + status.get());

        proceed.countDown();
        worker.join();
        System.out.println("after join: " + status.get());
        System.out.println("thread: " + worker.getState());
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 ThreadAndJobStateDemo.java
java ThreadAndJobStateDemo
~~~

Stdout (when there is no external interrupt):

~~~text
before start: PENDING
after started signal: RUNNING
after join: SUCCEEDED
thread: TERMINATED
~~~

**Explanation:**

1. **status** is the job's business state, stored independently by the application in an **AtomicReference**.
2. The worker transitions the job status to RUNNING and then signals **started.countDown()**. Main's **started.await()** ensures main observes the signal and the update that happened before countDown.
3. The worker waits on **proceed.await()**; during this wait it may be observed as **WAITING**, yet **status remains RUNNING**. The example intentionally does not print **worker.getState()** while running because a snapshot has no fixed result and races with releasing the latch.
4. Main signals **proceed.countDown()** and then calls **join()**. The worker updates the job to SUCCEEDED before finishing; main observes the stable result after join().
5. After an untimed **join()** returns normally because the worker has finished, **getState()** is TERMINATED. Success is represented by the **status** update, not inferred from TERMINATED.

The example uses latches to establish clear milestones rather than **Thread.sleep()** to guess how far the thread has progressed.

**Limitation of the example:** The worker has a branch catching InterruptedException to exit cooperatively, but the minimal enum model has no CANCELLED/FAILED state for that case. In a real design, every error and cancellation branch must update the corresponding state. The next section handles failure cases.

## 6. TERMINATED Does Not Mean SUCCEEDED

A thread can terminate because its run() method returns normally, because an uncaught exception was thrown, or because the code actively handled a cancellation request and returned. **Thread.State.TERMINATED** looks identical in all of these situations.

If an exception is not caught in the worker, an unhandled exception will be reported to the configured uncaught exception handler, but **the thread calling join() does not automatically receive that exception**. Therefore, simply doing:

~~~java
worker.start();
worker.join();
System.out.println("Success");
~~~

This is a **faulty logic illustration** if the "Success" line means the business task succeeded. **worker** must be an already-created Thread object, and this snippet needs to handle or declare **InterruptedException**. **join()** only confirms completion of the thread's lifecycle (when it returns due to termination), not success.

### Example Recording FAILED Separately

File **BusinessFailureDemo.java**:

~~~java
import java.util.concurrent.atomic.AtomicReference;

public class BusinessFailureDemo {
    enum JobStatus { PENDING, RUNNING, SUCCEEDED, FAILED }

    static void process(String input) {
        if (input.isBlank()) {
            throw new IllegalArgumentException("empty input");
        }
    }

    public static void main(String[] args) throws InterruptedException {
        AtomicReference<JobStatus> status =
                new AtomicReference<>(JobStatus.PENDING);
        AtomicReference<String> error = new AtomicReference<>();

        Thread worker = new Thread(() -> {
            status.set(JobStatus.RUNNING);
            try {
                process("");
                status.set(JobStatus.SUCCEEDED);
            } catch (RuntimeException ex) {
                error.set(ex.getMessage());
                status.set(JobStatus.FAILED);
            }
        }, "validation-worker");

        worker.start();
        worker.join();

        System.out.println("thread = " + worker.getState());
        System.out.println("job = " + status.get());
        System.out.println("error = " + error.get());
    }
}
~~~

~~~bash
javac -encoding UTF-8 BusinessFailureDemo.java
java BusinessFailureDemo
~~~

Stdout:

~~~text
thread = TERMINATED
job = FAILED
error = empty input
~~~

**Why is the result correct?** The business code intentionally throws an error on an empty string. The worker catches the error, stores the description, and updates status to FAILED before exiting. **join()** ensures main waits for the worker to finish and sees the writes made before the worker terminated; **AtomicReference** helps define and share the state cleanly.

In a real application, do not store raw messages containing sensitive data in public status logs. Establish a clear policy for which error types are retryable and whether you need to distinguish **FAILED** from **CANCELLED**, **TIMED_OUT**, or **PARTIALLY_COMPLETED**.

## 7. Why Is There No 1 Thread = 1 Job Mapping?

Simple examples when learning **new Thread(runnable)** can give the impression that every job has its own dedicated thread. That is not true in general:

- **One thread executes many tasks sequentially:** an executor with a worker pool reuses threads after each job. The worker stays alive after the previous job has SUCCEEDED or FAILED.
- **One job consists of multiple steps running across multiple threads:** with fan-out, callbacks, or stage-shifting pipelines, there is no single Thread.State representing the entire job.
- **A job is QUEUED with no worker running yet:** the business state is QUEUED, even though no thread exists for that job.
- **A task is waiting on I/O on a worker:** the worker may be observed in various Java states, while the business state remains RUNNING.
- **A job is persisted and awaiting retry:** one worker is already TERMINATED, while the job can transition to RETRYING and continue on another worker.

Do not use thread name, thread ID, or Thread.State as the unique identifier for a job. Use a dedicated **jobId/correlationId** that ties execution attempts to a single business unit of work.

### Future Is a JDK-Level Task State, Not Thread.State

In **java.util.concurrent**, **Future<T>** represents a result that may arrive after submitting a task:

- **isDone()** is true when the computation has completed **normally, failed, or been cancelled**.
- **isCancelled()** indicates that cancelling the Future succeeded, but it does not promise that side effects were rolled back.
- **get()** returns the result on normal completion; it can throw **ExecutionException** if the task code failed, **CancellationException** if cancelled, or **InterruptedException** if the waiting thread was interrupted.
- When using **cancel(true)**, the mechanism may send an interrupt to the executing thread, but the task must cooperate; **cancel()** does not guarantee undoing externally visible state changes.

Therefore, **Future.isDone() = true** is not enough to mark a job **SUCCEEDED**.

### Future Example: Work Outcome Differs from Worker Lifecycle

File **FutureOutcomeDemo.java**:

~~~java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class FutureOutcomeDemo {
    public static void main(String[] args)
            throws InterruptedException, ExecutionException {

        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            Future<Integer> future = executor.submit(() -> 6 * 7);
            int result = future.get();

            System.out.println("result = " + result);
            System.out.println("future done = " + future.isDone());
            System.out.println("future cancelled = " + future.isCancelled());
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 FutureOutcomeDemo.java
java FutureOutcomeDemo
~~~

Stdout:

~~~text
result = 42
future done = true
future cancelled = false
~~~

**future.get()** confirms the task returned the value 42 or would throw the corresponding exception. The result **does not imply** the worker thread has died: with **newSingleThreadExecutor()**, the worker can stay alive to accept the next job until the executor is shut down. The example calls shutdown to release resources in a controlled manner.

In a business system, you still need to define **when** to record SUCCEEDED: after computation, after a database commit, after publishing an event, or after an entire chain of steps. Future completion is an execution-layer signal; it does not define business transactions on its own.

## 8. Shared Business State Requires Synchronization

Because status can be read/written from multiple threads, a plain variable like:

~~~java
// Illustration code lacking visibility guarantees across threads:
JobStatus status = JobStatus.PENDING;
~~~

is insufficient if multiple threads read/write without a happens-before relationship. **volatile** guarantees visibility and appropriate ordering for individual reads/writes, but it **does not make a check-then-set sequence atomic**:

~~~java
// Faulty illustration code when two threads run concurrently:
if (status == JobStatus.PENDING) {
    status = JobStatus.RUNNING;
}
~~~

Both threads can read PENDING and both end up processing the same job. Appropriate solutions depending on your needs include:

- **AtomicReference.compareAndSet(expected, updated)** for atomic conditional updates on a single in-memory variable.
- **synchronized / Lock** when you need to protect multiple fields or a complex invariant.
- **BlockingQueue, CountDownLatch, Future** to exchange tasks/signals/results according to their contracts.
- **Transactions and conditional updates in storage** when multiple processes or instances process the same job; **AtomicReference only protects an object within a single JVM** and does not replace cross-process synchronization.

### Example: Preventing Two Threads from Both Transitioning PENDING → RUNNING

File **JobTransitionDemo.java**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class JobTransitionDemo {
    enum JobStatus { PENDING, RUNNING, SUCCEEDED }

    public static void main(String[] args) throws InterruptedException {
        AtomicReference<JobStatus> status =
                new AtomicReference<>(JobStatus.PENDING);
        AtomicInteger accepted = new AtomicInteger();
        AtomicInteger rejected = new AtomicInteger();

        Runnable requestStart = () -> {
            if (status.compareAndSet(
                    JobStatus.PENDING, JobStatus.RUNNING)) {
                accepted.incrementAndGet();
            } else {
                rejected.incrementAndGet();
            }
        };

        Thread a = new Thread(requestStart, "request-a");
        Thread b = new Thread(requestStart, "request-b");
        a.start();
        b.start();
        a.join();
        b.join();

        if (!status.compareAndSet(
                JobStatus.RUNNING, JobStatus.SUCCEEDED)) {
            throw new IllegalStateException("Unexpected job state");
        }

        System.out.println("accepted = " + accepted.get());
        System.out.println("rejected = " + rejected.get());
        System.out.println("job = " + status.get());
    }
}
~~~

~~~bash
javac -encoding UTF-8 JobTransitionDemo.java
java JobTransitionDemo
~~~

Stdout:

~~~text
accepted = 1
rejected = 1
job = SUCCEEDED
~~~

**One CAS succeeds**, while the other CAS sees that the state is no longer PENDING and rejects it. Because the aggregated totals are only printed after joining both threads, stdout does not depend on whether thread a or b won.

This is an example of **enforcing valid state transitions**; it does not yet execute real business logic. In a real job, only the accepted request may proceed with processing; the transition RUNNING → SUCCEEDED must occur **after** processing succeeds. On error, update to FAILED; on cancellation, apply your cancellation rules.

### Designing State Transition Rules

A state machine should be able to answer:

| Transition | When is it valid? |
| --- | --- |
| PENDING → RUNNING | A worker acquires the right to start processing |
| RUNNING → SUCCEEDED | The actual success conditions have been fulfilled |
| RUNNING → FAILED | An error occurred that prevents completion under the current contract |
| RUNNING → CANCEL_REQUESTED | An actor requests cancellation of the running work |
| CANCEL_REQUESTED → CANCELLED | The worker/protocol confirms it has stopped according to policy |
| FAILED → RETRYING | A retry policy applies and the attempt limit allows it |
| RETRYING → RUNNING | A new attempt is granted permission to execute |

These are example rules **defined by the application**, not mandatory JDK rules. When retrying, distinguish **jobId** (the work identity across multiple attempts) from **attemptId** (the identity of each individual run). Prevent late completions from an old attempt from overwriting the state of a newer attempt: use a version, an attempt token, or appropriate conditional updates.

## 9. Cancellation and Timeout: Technical State Differs from Business Decisions

When calling **worker.interrupt()**, you send an interruption request. That **does not by itself prove** the business state must be CANCELLED. The worker might:

- Not have observed the interrupt flag yet, or be in a non-interruptible step.
- Catch InterruptedException, then clean up and exit.
- Complete the work almost simultaneously with the cancellation request.
- Have already produced side effects before cancellation, requiring rollback/compensation under business rules.

A clear model can use **CANCEL_REQUESTED** first, and only transition to **CANCELLED** upon appropriate confirmation. If the work already succeeded before the cancellation request arrived, transition rules can reject the cancellation or simply record the late request.

**TIMED_WAITING** is not **TIMED_OUT**. A thread executing **Thread.sleep(1000)** is in TIMED_WAITING, yet the task is not necessarily overdue. Conversely, a business job may already have exceeded its policy deadline while the worker is still RUNNABLE, BLOCKED, or doing I/O.

When using **Future.get(timeout, unit)**, on timeout it throws **TimeoutException** to the **waiting caller**; this **does not automatically stop** the computation and **does not automatically cancel the Future**. You need an explicit policy if you want to cancel, retry, or mark the job TIMED_OUT.

### Two-Axis State Diagram

~~~text
Execution axis (JVM):
Thread NEW -> RUNNABLE <-> WAITING/TIMED_WAITING/BLOCKED -> TERMINATED

Business axis (application-defined):
Job PENDING -> RUNNING -> SUCCEEDED
                      \-> FAILED
                      \-> CANCEL_REQUESTED -> CANCELLED

A job can change threads/attempts; a thread can change jobs.
There is no automatic mapping from the JVM axis to the business axis.
~~~

When you need reliable timeout, cancellation, or retry states, update the business state through consistent, conditionally guarded steps; do not inspect Thread.State and automatically guess the job outcome.

## 10. Remembering Happens-Before and Result Publication Correctly

If a worker updates shared fields and then terminates, **Thread.join()** returning due to thread termination provides a *happens-before* relationship from the worker's actions to subsequent actions in the joining thread. This lets the calling thread safely read results after the job finishes.

In addition:

- **Thread.start()** establishes a happens-before relationship from the calling thread's actions before start() to actions inside the started thread.
- **CountDownLatch.countDown()** paired with a successful **await()** allows publishing results before the signal.
- **AtomicReference** provides safe read/write/CAS operations in accordance with the atomic class's memory contract.
- **volatile** and **synchronized** have visibility/happens-before contracts, though the scope of shared data must still be designed properly.

Do not assume **Thread.sleep()**, **Thread.yield()**, or merely checking **getState()** creates a happens-before relationship for business data. Observing that something "seems to work" across many runs does not prove a race-free protocol.

On the other hand, **join()** only waits for the **thread**. If the worker merely enqueues a task or triggers an asynchronous step and then exits, joining that worker does not mean the entire business job is done.

## 11. Distinguishing Observed State from the Source of Truth

A system typically has at least three layers of information:

1. **Thread.State**: a technical snapshot, suited for thread dumps, diagnosing BLOCKED/WAITING, and bottleneck analysis.
2. **Task execution outcome**: the value or exception of a Future, latch completion, or events from a worker; tied to a specific execution run.
3. **Business state**: the official business outcome under the contract (which may be persisted), encompassing retries, cancellation, timeouts, and compensation handling.

When displaying status to users, the API should return the **business state** with the **jobId** and safe error information; do not expose Thread.State as the status of an order, data processing job, or transaction.

For long-running jobs or jobs that must survive restarts, **status kept only in an AtomicReference will be lost when the process exits**. You must persist the state in an appropriate transaction/format and handle crashes between "side effect performed" and "status updated." Design idempotency, transaction boundaries, and controlled retries to avoid duplicate business execution. These concerns are independent of whatever Thread.State the JVM happens to report.

### A Useful Log Format

Instead of only logging:

~~~text
thread=worker-1 state=RUNNABLE
~~~

consider logging events at the task level, such as:

~~~text
jobId=import-842 attempt=2 status=RUNNING step=VALIDATING
jobId=import-842 attempt=2 status=FAILED reason=INVALID_INPUT
~~~

The lines above are **example log structures**, not the output of a specific program. Operational logs can also include timestamps, worker/thread names, and correlationId. Do not treat the ordering of logs from different threads as absolute proof of happens-before when there is no synchronization.

## 12. Common Conceptual Mistakes

| Wrong inference | Correct understanding |
| --- | --- |
| **Thread.State.RUNNABLE** means the job is RUNNING | RUNNABLE is only the thread's scheduling state; a thread can be performing various tasks |
| **Thread.State.WAITING** means the business job is PENDING | A RUNNING job can still wait on a latch, condition, or I/O result |
| **Thread.State.TERMINATED** means SUCCEEDED | A thread can terminate due to an exception, cancellation, or simply finishing the submission of another task |
| **Thread.sleep()** proves the job waited long enough, so mark SUCCESS | Sleep only pauses the thread; it does not prove side effects or business conditions |
| **Future.isDone()** means SUCCEEDED | Future done also includes failure and cancellation |
| **Future.get(timeout)** timing out means the worker stopped | Caller timeout does not automatically cancel the running task |
| Interrupt sent means the job is CANCELLED | Interrupt is a cooperative signal; cancellation requires confirmation rules |
| One worker thread equals one job | Thread pools reuse workers; a job can have multiple attempts |
| **volatile status** is enough to prevent two workers from picking up the same job | volatile guarantees visibility, not atomicity of check-then-set |
| **AtomicReference** is enough to protect a job across multiple JVMs | AtomicReference only synchronizes within one process; storage-level mechanisms are needed |
| Polling **getState()** in a loop is a reliable way to wait | getState() is a snapshot; use join, Future, latch, or a synchronized state protocol |
| **FAILED** then retried means SUCCESS can be written anytime | Version/attempt tracking and valid transitions are needed to prevent stale results from overwriting |

## 13. Self-Check

**Q1.** A thread is waiting on **CountDownLatch.await()**. Why can the work still be RUNNING?  
**Answer:** The thread is at a technical wait point to continue its active stage. RUNNING is a business label for the entire stage, not a snapshot of CPU usage.

**Q2.** The worker is TERMINATED, so what is the business outcome guaranteed to be?  
**Answer:** It cannot be determined from Thread.State alone. You need to know whether the worker returned a result, failed, was cancelled, or handed off work to another stage.

**Q3.** What risk usually arises when two threads pick up a PENDING job using check-then-set?  
**Answer:** Both can read PENDING and both execute it. Use an atomic conditional update such as CAS within a single JVM; across multiple processes, use conditional updates and transactions in the storage system.

**Q4.** Does **Future.isDone() == true** mean the work SUCCEEDED?  
**Answer:** No. A Future is also done when the computation fails or is cancelled. Check the result of get() and apply business rules.

**Q5.** Does **Future.get(1, TimeUnit.SECONDS)** throwing TimeoutException prove the worker has been stopped?  
**Answer:** No. It only means the caller timed out waiting; the computation may still be running.

**Q6.** When should you use Thread.getState(), and when should you read JobStatus?  
**Answer:** getState() is for observing/diagnosing a thread's lifecycle at a point in time; JobStatus is for knowing the progress and outcome of the work under the application contract.

**Q7.** Why is in-memory business state insufficient for jobs that need to resume after a crash?  
**Answer:** In-memory state disappears with the JVM and does not automatically provide transactions or prevent duplicate processing. Persistent storage, transition rules, and idempotency are required.

## 14. Conclusion

**Thread.State answers "how is the execution thread doing?"; business state answers "how far has the work progressed and what is its outcome?"** The two states can evolve independently. Use **Thread.getState()** for observation/diagnostics, use **join()/Future/latch** to wait for and collect execution results, and use a **business state machine** with appropriate synchronization/transactions to determine the true state of the work.