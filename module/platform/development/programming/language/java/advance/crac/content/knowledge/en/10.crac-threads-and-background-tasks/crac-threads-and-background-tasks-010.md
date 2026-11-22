# Non-Daemon Threads and the Risk of the JVM Exiting Before Creating an Image

In a Java application using CRaC, the JVM process must still be alive when the system requests a checkpoint. If the JVM has already started shutting down, administrative tools no longer have a running process from which to request a checkpoint. A common mistake is starting background tasks on a daemon thread, after which the main thread exits. When no non-daemon threads remain running, the JVM can begin shutting down even while the daemon thread still has work.

Java classifies threads into two groups: **daemon threads** and **non-daemon threads**. Non-daemon threads can keep the JVM alive after the main thread finishes. Daemon threads support background work and do not prevent the JVM from exiting. This is a property of process lifecycle, not priority level, access permissions, or work reliability.

For CRaC, the application lifecycle must be designed intentionally: the process must stay alive and ready to accept checkpoint requests; workers must be coordinated into a safe state before checkpoint; after restore, paused workers must be resumed or recreated following the exact lifecycle. Merely setting a thread to non-daemon does not automatically guarantee a successful checkpoint, yet misusing daemon threads can cause the JVM to exit before the image is created.

## 1. When Does the JVM Exit?

Normally, the main() method runs on the main thread. The main thread is non-daemon. When main() finishes, the main thread finishes. If at least one non-daemon thread remains alive, the JVM typically continues running. Once all non-daemon threads have terminated, the JVM begins the shutdown process; remaining daemon threads do not keep the process alive.

Example:

~~~java
public class DaemonExitExample {
    public static void main(String[] args) {
        Thread background = new Thread(() -> {
            while (true) {
                System.out.println("Background work");
                try {
                    Thread.sleep(1_000);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return;
                }
            }
        }, "background-worker");

        background.setDaemon(true);
        background.start();

        System.out.println("main is returning");
    }
}
~~~

After main() returns, if no other non-daemon threads remain, the JVM begins shutting down. Daemon threads can be terminated when the JVM stops; the program has no guarantee that their loop will finish, finally blocks will run completely, or buffered data will be flushed.

If you omit the line setDaemon(true), a new thread created from the main thread normally inherits the non-daemon status of the thread that created it. In that case, background-worker can keep the JVM alive after main() finishes, as long as the worker keeps running.

Crucially, a non-daemon thread prevents natural JVM termination only while it remains alive. If the worker completes or exits due to an error before the checkpoint request arrives, the JVM can still shut down. If the application calls System.exit(), Runtime.exit(), is stopped by the deployment environment, or encounters another shutdown condition, non-daemon threads also do not guarantee the process stays alive.

## 2. Daemon Threads and Non-Daemon Threads

### 2.1. Non-Daemon Threads

A non-daemon thread is a thread that participates in keeping the JVM alive. This is usually the right choice for work the application must stay alive to finish, such as:

- Threads serving server requests or connections.
- Workers processing queues for which the application is responsible for guaranteeing completion.
- Schedulers running mandatory background tasks.
- Threads coordinating application lifecycle and waiting for stop signals.
- Monitoring or coordination components whose termination means the application can no longer serve.

A non-daemon thread waiting on a queue or waiting for a signal can still keep the JVM alive. Therefore, an executor creating non-daemon workers can keep the program from exiting even when no tasks are actively running.

### 2.2. Daemon Threads

A daemon thread is a supporting thread and should not be relied on as the sole reason the JVM stays alive. Common examples include certain cleanup threads, monitoring threads, or tasks that can be discarded when the process exits.

Daemon threads are suitable when:

- The work only has value while the application is actively serving.
- The work can be regenerated from durable data sources.
- Abrupt termination during JVM shutdown does not lose business data.
- The application has another non-daemon component managing process lifecycle.

Do not mark workers as daemon if they hold unpersisted work, are processing unacknowledged messages, or are writing critical data. During JVM shutdown, daemon threads are not guaranteed time to finish.

### 2.3. Comparison

| Characteristic | Non-daemon | Daemon |
|---|---|---|
| Keeps JVM alive when main thread finishes? | Yes, if the thread remains alive and an explicit JVM shutdown was not requested | No |
| Can be cut short when JVM exits? | Can be stopped once shutdown completes; needs graceful shutdown mechanisms | Can be terminated without completing its work |
| Commonly used for | Servers, mandatory workers, lifecycle threads | Supporting work that can be recreated or skipped |
| Guarantees checkpoint success? | No | No |
| Needs shutdown management? | Yes, so it does not keep the JVM alive indefinitely | Yes, so work or resources are not lost |

Daemon does not mean the thread runs at low priority. Non-daemon also does not mean the thread receives higher CPU priority. This attribute only affects the JVM rule determining when natural shutdown begins.

## 3. How to Set Daemon Status

For a standard Thread, status can be set with setDaemon(boolean). It must be called before start():

~~~java
Thread worker = new Thread(() -> processJobs(), "job-worker");
worker.setDaemon(false);
worker.start();
~~~

If setDaemon() is called after start(), Java throws IllegalThreadStateException. The daemon status of an already running thread cannot be changed.

New threads inherit daemon status from their creating thread by default. Thus, a thread created from a daemon thread may also be daemon unless reset. If daemon status matters to the application lifecycle, configure it explicitly instead of relying on the parent thread.

Example:

~~~java
Thread parent = new Thread(() -> {
    Thread child = new Thread(() -> runBackgroundTask());
    // Child inherits parent's daemon status.
    child.start();
}, "parent-worker");

parent.setDaemon(true);
parent.start();
~~~

In this example, child is created inside a daemon parent and is therefore also daemon by default. If child must keep the JVM alive, set child.setDaemon(false) before calling start().

Some factories have their own policies. For instance, Executors.defaultThreadFactory() creates non-daemon workers. Therefore, do not infer daemon status solely from the thread creating the executor; check the thread factory in use or configure it explicitly.

## 4. Why Can Daemon Threads Cause the JVM to Exit Before Checkpoint?

The checkpoint workflow requires an existing JVM. Depending on deployment, the checkpoint request may be sent from an administrative tool, script, orchestrator, or the application itself. Wherever the trigger comes from, if the JVM has already shut down, the request no longer has a running target process to handle it.

A common scenario:

1. main() creates a daemon worker.
2. The worker starts processing background tasks.
3. main() returns.
4. No other non-daemon threads remain.
5. The JVM begins shutting down and the daemon worker may be terminated.
6. The checkpoint tool runs afterward, yet the process is already gone.

Diagram:

~~~mermaid
flowchart TD
    A[JVM starts] --> B[main creates daemon worker]
    B --> C[worker starts running]
    C --> D[main exits]
    D --> E{Non-daemon threads remain?}
    E -->|No| F[JVM begins shutdown]
    F --> G[Daemon worker is terminated]
    G --> H[No JVM left to checkpoint]
    E -->|Yes| I[JVM stays alive]
    I --> J[Can receive checkpoint request]
~~~

The problem is not that daemon threads cannot be checkpointed. The problem is that daemon threads do not keep the process alive. If the application lacks an appropriate non-daemon component or the main thread does not await lifecycle completion, the JVM can exit before image creation is invoked.

### 4.1. A Buggy Example

~~~java
public final class EarlyExitApp {
    public static void main(String[] args) {
        Thread preparation = new Thread(() -> {
            prepareApplicationState();
            System.out.println("Preparation finished");
        }, "checkpoint-preparation");

        preparation.setDaemon(true);
        preparation.start();
        // main exits right after starting the worker.
    }

    private static void prepareApplicationState() {
        try {
            Thread.sleep(10_000);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
~~~

If no other non-daemon threads exist, the JVM can begin shutting down immediately after main() finishes. The worker may not finish prepareApplicationState(). If the checkpoint procedure is expected to run once application preparation completes, it will have no process left to operate on.

### 4.2. Non-Daemon Workers Can Also Exit Too Early

Switching the worker to non-daemon only keeps the JVM running while the worker stays alive. If the worker performs only a single preparation step and exits, and the main thread has already finished, the JVM can still shut down immediately afterward.

Example:

~~~java
Thread preparation = new Thread(() -> {
    prepareApplicationState();
}, "one-shot-preparation");

preparation.setDaemon(false);
preparation.start();
// Once preparation finishes, the JVM can shut down if no non-daemon threads remain.
~~~

If the JVM needs to remain alive after preparation, the application must have a lifecycle thread, server thread, or mechanism waiting for checkpoint/stop signals. Do not treat a short-lived task as a process keep-alive mechanism.

## 5. Threads in Executors and Async APIs

Not every worker is created directly via new Thread(). Concurrency APIs can choose different daemon policies.

### 5.1. Executors.newSingleThreadExecutor and Thread Pools

Common factories such as newSingleThreadExecutor(), newFixedThreadPool(), and newScheduledThreadPool() use Executors.defaultThreadFactory() by default. Workers created by the default factory are non-daemon.

This means an executor can keep the JVM alive even after main() has finished:

~~~java
ExecutorService executor =
        Executors.newSingleThreadExecutor();

executor.submit(() -> {
    System.out.println("Background task");
});

// executor.shutdown() is not called.
// The non-daemon worker can stay alive and keep the JVM running.
~~~

A thread pool can keep workers waiting on the queue for new tasks. If the application does not call shutdown() or lack an equivalent lifecycle management mechanism, the JVM may fail to exit naturally. In a CRaC environment, this can keep the JVM alive to receive a checkpoint, yet can also cause shutdown or checkpointing to hang if the executor is not stopped properly.

### 5.2. ScheduledExecutorService

ScheduledExecutorService creates workers according to its thread factory. With the default factory, workers are non-daemon. A periodic schedule can keep the JVM alive long-term:

~~~java
ScheduledExecutorService scheduler =
        Executors.newScheduledThreadPool(1);

scheduler.scheduleAtFixedRate(
        () -> refreshCache(),
        0,
        30,
        TimeUnit.SECONDS
);
~~~

If the scheduler must continue after restore, manage it as a resource. Before checkpoint, stop scheduling new tasks and handle running tasks per policy. After restore, reschedule appropriately relative to the current time. Do not assume runs missed while the JVM was stopped will automatically execute as desired.

### 5.3. CompletableFuture and Common Pool

Asynchronous calls without passing an Executor, such as CompletableFuture.runAsync(task), usually use ForkJoinPool.commonPool() when the environment can use that pool. Common pool workers are normally daemon threads. Therefore, merely submitting a CompletableFuture does not guarantee the JVM stays alive until the task completes.

Example:

~~~java
public static void main(String[] args) {
    CompletableFuture.runAsync(() -> {
        performPreparation();
    });
    // No await/join and no non-daemon lifecycle thread.
}
~~~

If main() finishes and no other non-daemon threads remain, the JVM can shut down before the future completes. If the task's result is mandatory, wait via join()/get() or use an executor with a managed lifecycle:

~~~java
CompletableFuture<Void> preparation =
        CompletableFuture.runAsync(
                () -> performPreparation(),
                managedExecutor
        );

preparation.join();
~~~

Calling join only ensures the main thread waits for that task to complete. It does not keep the application alive after the task finishes. If the application needs to keep waiting for a checkpoint, it must stay in a serving state or wait on signals via a dedicated lifecycle.

### 5.4. Virtual Threads

Virtual threads in JDKs supporting virtual threads are daemon threads. They do not keep the JVM alive once all non-daemon threads have terminated. An application creating virtual threads to perform background work and then letting main() return can face the same risk: the task is unfinished yet the JVM has started shutting down.

Virtual threads are suited for organizing many concurrent tasks, yet application lifecycle still must be managed by the main thread, server, or another non-daemon component. Do not use the count of living virtual threads as evidence that the JVM will stay alive.

### 5.5. Quick Comparison Table

| Way of creating work | Typical daemon status | What to note |
|---|---|---|
| new Thread() from main thread | Inherits main's non-daemon status | Set explicitly if threads are created from varied contexts |
| Executors.newSingleThreadExecutor() | Default workers are non-daemon | Call shutdown and manage lifecycle |
| Executors.newFixedThreadPool() | Default workers are non-daemon | Pool can keep the JVM alive while idle |
| Executors.newScheduledThreadPool() | Default workers are non-daemon | Cancel schedules and recalculate timing after restore |
| CompletableFuture.runAsync() without executor | Usually uses common pool with daemon workers | Use join/get or a managed executor if work is mandatory |
| ForkJoinPool.commonPool() | Default workers are daemon | Do not use it as a mechanism to keep the JVM alive |
| Thread.ofVirtual().start() | Virtual threads are daemon | Need another lifecycle thread to keep the application alive |

Daemon policy can differ when the application provides a custom ThreadFactory or a library creates its own threads. Verify the policy of the actual JDK and library rather than relying solely on API names.

## 6. Keeping the JVM Alive with an Explicit Lifecycle

An application that needs to remain alive to receive a checkpoint must have an explicit lifecycle mechanism. Common ways:

- The main thread continues waiting inside the server lifecycle.
- An application framework keeps the main thread running until a stop signal is received.
- A server or listener has non-daemon threads serving connections.
- A lifecycle coordinator awaits a stop state or administrative command.
- A non-daemon worker runs continuously if that worker itself is a mandatory serving component.

Do not create an empty thread merely to keep the JVM alive without lifecycle responsibilities. Such a thread can prevent the application from exiting when needed, mask shutdown errors, and cause checkpointing to hang because it is uncoordinated.

### 6.1. Main Thread Awaiting Lifecycle

The example below depicts an application with a lifecycle coordinator. Management components call requestStop() when the application needs to stop; the main thread awaits that signal and then closes the executor:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public final class LongLivedApplication implements AutoCloseable {
    private final CountDownLatch stopRequested = new CountDownLatch(1);
    private final AtomicBoolean running = new AtomicBoolean(true);
    private final BlockingQueue<Runnable> jobs = new LinkedBlockingQueue<>();
    private final ExecutorService worker =
            Executors.newSingleThreadExecutor(r -> {
                Thread thread = new Thread(r, "business-worker");
                thread.setDaemon(false);
                return thread;
            });

    public void start() {
        worker.submit(this::runWorker);
    }

    public void awaitStopRequest() throws InterruptedException {
        stopRequested.await();
    }

    // Called by the lifecycle manager or management endpoint.
    public synchronized void requestStop() {
        running.set(false);
        stopRequested.countDown();
    }

    public synchronized void submit(Runnable job) {
        if (!running.get()) {
            throw new IllegalStateException("Application is stopping");
        }
        jobs.add(job);
    }

    private void runWorker() {
        while ((running.get() || !jobs.isEmpty())
                && !Thread.currentThread().isInterrupted()) {
            try {
                Runnable job = jobs.poll(1, TimeUnit.SECONDS);
                if (job != null) {
                    job.run();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
        }
    }

    @Override
    public void close() throws InterruptedException {
        requestStop();
        worker.shutdown();
        if (!worker.awaitTermination(30, TimeUnit.SECONDS)) {
            worker.shutdownNow();
        }
    }

    public static void main(String[] args) throws Exception {
        try (LongLivedApplication app = new LongLivedApplication()) {
            app.start();
            app.awaitStopRequest();
        }
    }
}
~~~

In the example, the main thread waits on stopRequested. Because the main thread is non-daemon, the JVM stays alive even when the worker temporarily has no work. The worker executor is also explicitly set to non-daemon. The lifecycle manager is responsible for sending the stop request, and the application closes the executor with a time bound.

This is a structural example, not a complete OS signal handling mechanism. In real server applications, frameworks or containers usually already provide a lifecycle coordinator, management endpoints, and graceful shutdown mechanisms. Integrate with the existing lifecycle instead of adding another latch with no release path.

### 6.2. Using the Server Lifecycle

In web applications, the main thread usually does not need to hand-write an infinite loop. The server framework manages acceptors, event loops, and the application lifecycle. Ensure the process is kept alive by the official server mechanism and stops only on a valid shutdown command.

If the framework runs background tasks on daemon threads, that is not necessarily a bug as long as the main server still has non-daemon threads or the main thread stays inside the lifecycle. Conversely, if the server has stopped and only daemon tasks remain, the JVM can exit and lose the ability to accept a checkpoint.

### 6.3. Do Not Use a Shutdown Hook as a Keep-Alive Mechanism

Shutdown hooks are invoked after the JVM has already started shutting down. A hook is suitable for performing time-bounded cleanup work, yet it is not a mechanism to keep the JVM alive waiting for a checkpoint.

Do not assume that:

- Having a shutdown hook means the JVM will wait for a checkpoint.
- A hook can stop JVM shutdown merely by waiting indefinitely.
- A hook always has enough time to flush all data.
- The hook running means the checkpoint image was created.

If the application needs on-demand checkpointing from management tools, keep the JVM alive in its normal lifecycle and perform checkpointing before the shutdown sequence begins. Shutdown hooks should only assist graceful cleanup per application design.

## 7. Coordinating Threads with CRaC Resources

Keeping the JVM alive is a necessary condition to receive a checkpoint, yet running workers must also be in an appropriate state when the checkpoint runs. A background thread may be:

- Waiting on a BlockingQueue.
- Reading or writing a socket.
- Holding a database transaction.
- Holding an application lock.
- Executing a native or I/O operation.
- Waiting on a timer or scheduler.
- Processing a message without yet acknowledging it.

CRaC does not automatically understand the business semantics of these operations. The application must coordinate workers using resource callbacks or library-supported integrations.

### 7.1. Before Checkpoint: Quiesce and Drain

The beforeCheckpoint() callback should bring workers to a safe state:

1. Stop accepting new tasks or pause task-producing sources.
2. Mark the application as quiescing so producers do not keep pushing new work.
3. Wait for running tasks to complete within a defined timeout.
4. Commit or roll back transactions according to business rules.
5. Confirm messages are durably processed before acknowledgment.
6. Close or release external resources used by workers.
7. Put workers into an idle state or stop them completely if the library requires.

Do not simply call Thread.sleep() for a fixed duration and assume workers have stopped. Use synchronization mechanisms such as conditions, latches, semaphores, queue sentinels, or executor shutdown/awaitTermination APIs to verify actual state.

### 7.2. After Restore: Resume or Recreate Workers

The afterRestore() callback can:

- Restore connections and dependencies first.
- Recreate schedulers or consumers if they were stopped.
- Re-read task schedules from the authoritative data source.
- Skip or recalculate missed runs according to business policy.
- Start workers once dependencies are ready.
- Open readiness once mandatory components are operational.

Do not start workers before connection pools, broker clients, or foundational resources are ready. If multiple resource callbacks have dependencies, registration order and callback order must be designed appropriately.

### 7.3. Stopping and Recreating Executors

Some executors are unsuitable for continued use after being shut down. If the before-checkpoint callback calls shutdown() and the executor transitions to the terminated state, the after-restore callback cannot simply call submit() to reuse that executor. In that case, the resource should create a new executor and store the new reference.

Conceptual example:

~~~java
public final class WorkerResource implements Resource {
    private ExecutorService executor;

    private void startWorker() {
        executor = Executors.newSingleThreadExecutor();
        executor.submit(this::runLoop);
    }

    private void stopWorker() throws InterruptedException {
        ExecutorService current = executor;
        executor = null;
        if (current == null) {
            return;
        }

        current.shutdown();
        if (!current.awaitTermination(20, TimeUnit.SECONDS)) {
            current.shutdownNow();
        }
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        stopWorker();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        startWorker();
    }
}
~~~

This is lifecycle pseudocode; a complete implementation must declare imports, a constructor registering the resource, handle initialization state, and ensure runLoop has a stop mechanism. Determine whether workers should be paused and resumed or stopped and recreated. A single pattern cannot apply to every executor, scheduler, and framework.

## 8. Risks When Non-Daemon Threads Are Unmanaged

Non-daemon threads keep the JVM from exiting too early, yet without a shutdown policy they can create the opposite problem.

### 8.1. The JVM Fails to Exit After the Application Has Finished

A default executor can keep non-daemon workers waiting for new tasks. If main() exits yet the executor has not shut down, the JVM remains alive. This can prevent containers from terminating, hang deployment rollouts, or leave management scripts waiting forever.

Solutions:

- Call shutdown() when the application stops.
- Use awaitTermination() with a timeout.
- Call shutdownNow() only when policy allows interrupting tasks.
- Ensure tasks respond to interrupts and do not block indefinitely on I/O.
- Register the executor with the appropriate lifecycle manager or CRaC Resource.

### 8.2. Checkpoint Is Delayed Because Workers Do Not Reach a Safe State

Non-daemon workers may be processing transactions or waiting on long I/O. If a checkpoint callback waits for workers to complete without a timeout, the checkpoint process may never make progress.

Set a deadline for draining, log clearly which workers have not stopped, and decide whether to abort the checkpoint. Do not checkpoint while a transaction or critical write operation is in an indeterminate state.

### 8.3. A Worker Is Alive Yet No Longer Useful

A thread may still be alive yet have lost its connection, lost its lease, or hold stale data. Non-daemon status only states that the thread can keep the JVM alive; it does not prove the thread is healthy or capable of processing work.

After restore, verify dependencies and business state. If a worker holds a distributed lock or lease, it must re-register and verify ownership before writing. If a worker uses a cache, refresh data that may have become stale.

### 8.4. A Worker Is Blocked in a Native Call or I/O

A worker waiting on a native library or I/O may need special handling before checkpoint. The ability to checkpoint thread state and native resources depends on the runtime, platform, and library. Do not assume every wait point can be safely restored.

Check CRaC compatibility of the library, use I/O timeouts, and design callbacks to stop or recreate resources that cannot continue. If a worker cannot be brought to a safe state, the procedure should fail the checkpoint instead of silently continuing.

## 9. Easily Confused Scenarios

| Scenario | Possible outcome | Design approach |
|---|---|---|
| Main thread finishes, only daemon workers remain | JVM begins shutdown; workers may be stopped before checkpoint | Keep the main lifecycle alive via a non-daemon main/server thread |
| Main thread finishes, non-daemon worker still running | JVM stays alive while worker lives | Ensure the worker has a shutdown policy and safe state |
| Non-daemon worker finishes before checkpoint request | JVM can shut down if no other non-daemon threads remain | Use a lifecycle coordinator or long-lived server thread |
| CompletableFuture runs on common pool | Workers are usually daemon; tasks may be cut off during JVM shutdown | Wait for results or pass a managed executor |
| Scheduled executor has not shut down | Non-daemon workers can keep the JVM alive indefinitely | Cancel schedules and close the scheduler in the lifecycle |
| Virtual thread is the only background work | Virtual threads are daemon so they do not keep the JVM alive | Keep the main thread or server lifecycle alive |
| Non-daemon worker holds a transaction | JVM stays alive, yet checkpoint may be unsafe | Drain and complete/roll back transactions |
| Worker was shut down before checkpoint | Process may stay alive, yet worker is no longer active | Recreate the worker in after-restore callbacks if needed |
| Shutdown hook is running | JVM has already entered shutdown sequence | Checkpoint before shutdown; do not rely on hooks to keep the JVM alive |

## 10. Operational Workflow for a CRaC Application with Background Tasks

A practical workflow can be divided into phases:

### Startup

1. Initialize configuration and required dependencies.
2. Create executors, schedulers, and consumers with an intentional daemon policy.
3. Register Resources managing workers or resources needing callbacks.
4. Start workers once dependencies are ready.
5. Keep the main thread or server lifecycle alive so the process can receive a checkpoint.
6. Open readiness only after the application is ready.

### Before Checkpoint

1. Transition the application into the quiescing state.
2. Stop accepting new requests and tasks.
3. Drain workers and queues; complete or roll back transactions.
4. Stop schedulers or pause consumers per policy.
5. Close external resources and confirm workers are in a safe state.
6. Allow the runtime to proceed with checkpoint creation once resources have completed callbacks.

### After Restore

1. Recreate connections and dependencies.
2. Refresh tokens, sessions, leases, and time-sensitive data.
3. Reinitialize shut-down executors or schedulers.
4. Re-register consumers or subscriptions.
5. Recalculate task schedules based on current time.
6. Transition the application back to serving state and open readiness.

Flow:

~~~mermaid
flowchart TD
    A[JVM starts] --> B[Initialize dependencies]
    B --> C[Create and register worker Resource]
    C --> D[Start workers and server lifecycle]
    D --> E[JVM stays alive]
    E --> F[Receive checkpoint request]
    F --> G[Quiesce and drain tasks]
    G --> H[Close or pause worker resource]
    H --> I[CRaC creates checkpoint]
    I --> J[Restore JVM]
    J --> K[Recreate dependencies]
    K --> L[Resume or create new workers]
    L --> M[Readiness and continue serving]
~~~

## 11. Testing the Risk of the JVM Exiting Before Checkpoint

Test both daemon policy and the application lifecycle. Some useful scenarios:

- Run the application with main() exiting right after creating a daemon worker; verify the process exits when no non-daemon threads remain.
- Run with a non-daemon worker; verify the JVM stays alive after main() exits and exits properly when the worker is stopped.
- Create a default executor, submit a short task without shutting it down; observe whether the worker keeps the process alive after the task completes.
- Use CompletableFuture.runAsync() on the common pool without joining; verify the task is not a mechanism keeping the JVM alive.
- Create a virtual thread as the sole background work; verify the main/server lifecycle still must keep the process alive.
- Send a checkpoint request while a worker is waiting on a queue, running a task, and waiting on I/O.
- Send a checkpoint while a worker holds a transaction; verify callbacks drain or report an error per policy.
- Restore and verify workers are recreated or resumed exactly once, without creating duplicate consumers or schedulers.
- Send a normal shutdown signal and verify executors close within the timeout.
- Have a worker encounter an unexpected exception; verify the lifecycle manager detects the worker termination and the application does not silently lose serving capability.

When testing, log the thread name, daemon status, executor state, time when main() finishes, time of JVM shutdown, and time of the checkpoint request. Do not look only at the worker's log because a daemon thread can be terminated before finishing writing its final line.

## 12. Design Principles

- The main thread ending does not mean the JVM must exit immediately if non-daemon threads still remain.
- Daemon threads do not keep the JVM alive; do not assign sole work that must finish before checkpoint to a daemon worker.
- A non-daemon thread keeps the JVM alive only while it is still running and no explicit shutdown command has occurred.
- Set daemon status before calling start().
- Check the ThreadFactory of executors and libraries; do not guess from API names.
- Remember that virtual threads are daemon and the common pool typically uses daemon workers.
- Keep the JVM alive with a meaningful server lifecycle or coordinator, rather than creating infinite threads merely to keep the process alive.
- Manage executors, schedulers, and workers with timed shutdown/awaitTermination.
- Before checkpoint, quiesce and drain work; do not rely on fixed sleeps.
- After restore, recreate dependencies and workers in order; recalculate schedules and time-bounded state.
- Test natural JVM exit, explicit shutdown, and unexpected worker termination.

CRaC requires an existing JVM to receive and complete a checkpoint request. Daemon threads cannot keep the JVM alive once main and all non-daemon threads have exited. Non-daemon threads can keep the process running, yet must be managed so they do not hang the application at shutdown. A good design combines an explicit primary lifecycle, workers with appropriate daemon policies, CRaC callbacks to pause or recreate tasks, and time-bounded graceful shutdown mechanisms.