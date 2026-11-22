# Distinguishing `Thread.start()` and `Thread.run()` in Java

## 1. Same `run` method, but two ways of calling it have different meanings

A `Thread` represents a Java thread of execution. The work that the thread will perform usually resides in `Runnable.run()` or an overridden `Thread.run()` method. A common point of confusion is that **calling `run()` directly does not create or start a new thread**.

- **`thread.start()`**: asks the JVM to start the thread represented by the `thread` object. Once the thread is scheduled, the JVM executes `run()` on the **new thread**. The `start()` method usually returns before the work completes; the caller continues executing independently of the new thread.
- **`thread.run()`**: invokes a normal Java method on the **calling thread**. The body of `run()` runs synchronously; the caller waits for the method call to return before executing the next statement. No new Java thread is created just by calling `run()`.

The difference lies in the **execution context**, not in the body of `run()` itself. The same `Runnable` can run on the `main` thread when called directly or on a newly created thread when `start()` is called.

```text
main thread
  |
  +-- thread.run() ------------------------+
  |     work runs immediately on main      |
  |     main waits for work to complete    |
  |<---------------------------------------+
  |
  +-- thread.start() -- requests creating a new thread
  |       |
  |       +---- worker thread runs run()
  |       |       (scheduled by JVM/OS)
  |       +---- terminates afterward
  |
  +-- main continues (can interleave with worker)
```

For a platform thread, `start()` starts a Java thread backed by an OS thread. For a virtual thread (Java 21+), `start()` starts a virtual thread scheduled by the JVM onto a carrier platform thread. **Both are separate Java threads** from the calling thread; whereas calling `run()` directly still runs on the current thread.

## 2. First example: identifying the exact executing thread

Create the file `StartVsRunDemo.java`:

```java
public class StartVsRunDemo {
    public static void main(String[] args) throws InterruptedException {
        Runnable job = () -> System.out.println(
                "Job đang chạy trên: " + Thread.currentThread().getName());

        Thread direct = new Thread(job, "worker-direct");
        direct.run();
        System.out.println("Trạng thái direct: " + direct.getState());

        Thread started = new Thread(job, "worker-started");
        started.start();
        started.join();
        System.out.println("Trạng thái started: " + started.getState());
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac StartVsRunDemo.java
java StartVsRunDemo
```

Output when using the standard Java launcher (the main thread's name is `main`):

```text
Job đang chạy trên: main
Trạng thái direct: NEW
Job đang chạy trên: worker-started
Trạng thái started: TERMINATED
```

Reading the output step by step:

1. `direct` is created with the name `worker-direct` but only `direct.run()` is called. During execution, `Thread.currentThread()` returns **main**, not `direct`. The name assigned to the `Thread` object does not change the executing thread's name.
2. Because `direct.start()` was never called, `direct.getState()` remains `NEW` even after `direct.run()` is called.
3. `started.start()` actually starts a thread named `worker-started` to run `job`. `Thread.currentThread()` then returns the new thread.
4. `started.join()` waits for the thread to finish, so the subsequent state check prints `TERMINATED`. Without `join()`, the thread might still be running when `main` checks it.

The first two output lines of the example have a deterministic order due to synchronous `run()`, while the last two lines have a deterministic order due to `join()`. In another program, `println` statements from `main` and a concurrently running worker can appear in different orders; **do not rely on incidental print order to draw conclusions about scheduling**.

## 3. Direct `run()` is a synchronous call

`Thread` implements `Runnable`; when creating `new Thread(job)`, `job` is set as the thread's target. In the normal case, when executing `Thread.run()`, the thread calls `job.run()`. If you call `thread.run()` from `main`, the call chain executes on `main`'s stack:

```text
main()
  -> Thread.run()
       -> Runnable.run()
            -> work
  <- return
main() continues
```

Therefore:

- Direct `run()` **does not initiate concurrency** from that `Thread` object.
- If `run()` takes two seconds, the calling thread is blocked in the call for about two seconds (unless the task itself delegates work to another thread). This is synchronous execution.
- `Thread.currentThread()` still returns the calling thread.
- `run()` is a Java method that can be called multiple times, because calling it **does not consume the one-time `start()` allowance** of the `Thread` object.
- An uncaught exception inside the `run()` call propagates up the calling thread's stack, just like a normal method call.

Do not use the variable name `thread`, the thread name passed to the constructor, or the presence of a `Runnable` object to infer that a program actually runs multithreaded. Observing `Thread.currentThread()` and how it is started reveals the execution context.

## 4. `start()` is the operation that starts a new thread

For a `Thread` object in the `NEW` state, calling `start()` registers a startup request so the JVM schedules `run()` for execution. The JVM invokes `run()` on the new thread; the programmer **does not need to and should not manually call `run()` after `start()` to launch the task**.

What `start()` does **not** guarantee:

- It does not guarantee that the worker has executed its first statement when `start()` returns.
- It does not guarantee whether the worker or `main` always runs first.
- It does not wait for the work to complete. To wait, use `join()` or a mechanism like `Future.get()`.
- It does not by itself guarantee that shared data access is safe from race conditions.
- It does not guarantee that the work runs on a different CPU core; the degree of parallelism depends on the scheduler and hardware.

`start()` creates a concurrent branch of execution progress. On a single-core CPU, two threads can still interleave; with multiple cores, they can actually run in parallel.

### `start()` can only be called successfully once per `Thread` object

Once a thread has been started, whether it is currently running or has already terminated, **that same object must not be started again**. Calling `start()` again throws `IllegalThreadStateException` (a `RuntimeException`). If you want to run the work again, create a new `Thread` object or submit a new task to an executor.

Example `StartOnceDemo.java`:

```java
public class StartOnceDemo {
    public static void main(String[] args) throws InterruptedException {
        Runnable job = () -> System.out.println("Thực thi công việc");

        Thread direct = new Thread(job);
        direct.run();
        direct.run();
        System.out.println("direct state: " + direct.getState());

        Thread worker = new Thread(job);
        worker.start();
        worker.join();

        try {
            worker.start();
        } catch (IllegalThreadStateException e) {
            System.out.println("Không thể start lại cùng Thread");
        }
    }
}
```

```bash
javac StartOnceDemo.java
java StartOnceDemo
```

Output:

```text
Thực thi công việc
Thực thi công việc
direct state: NEW
Thực thi công việc
Không thể start lại cùng Thread
```

The two `direct.run()` calls cause the same `Runnable` to run twice on `main`, while `direct` remains `NEW`. `worker.start()` executes the work on a new thread exactly once; the second `start()` call throws an exception. `join()` ensures the worker's output completes before the exception-catching block, so the output order is deterministic.

In particular, **"being able to call `run()` multiple times" does not mean "being able to start the same `Thread` multiple times"**. `run` is a method, whereas `start` triggers the lifecycle of the thread object.

## 5. Distinguishing `Runnable.run()`, `Thread.run()`, and overriding `run()`

There are two common ways to define the work that runs in a thread.

### 5.1. Passing a `Runnable` to `Thread`

```java
Runnable job = () -> System.out.println(Thread.currentThread().getName());
Thread worker = new Thread(job, "report-worker");
worker.start();
```

This is an **illustrative snippet** (not yet a class with `main`). `Runnable` describes the work; `Thread` provides the execution context. When `start()` starts the worker, the default `Thread.run()` method executes `job.run()` on the worker. This approach separates the responsibility of describing work from managing thread lifecycle.

### 5.2. Extending `Thread` and overriding `run()`

```java
class ReportThread extends Thread {
    @Override
    public void run() {
        System.out.println(Thread.currentThread().getName());
    }
}
```

This is an **illustrative class definition**. `new ReportThread().start()` executes the overridden `run()` method on a new thread. `new ReportThread().run()` only calls the overridden method on the current thread.

When a subclass overrides `run()`, whether a `Runnable` is also passed to the constructor **does not automatically guarantee that the `Runnable` target will be invoked**: the subclass's `run()` method decides whether to call `super.run()` or invoke the target. When you do not need to customize thread management mechanics, a design based on `Runnable`/`Callable` and executors is usually simpler and more reusable.

### 5.3. `Thread.currentThread()` is not `this`

Inside the `run()` method of `ReportThread`:

- `this` refers to the `ReportThread` instance containing the method.
- `Thread.currentThread()` refers to the thread **currently executing the statement**.

After `start()`, those two references normally point to the same worker. When `main` calls `worker.run()` directly, `this` is still `worker` while `Thread.currentThread()` is `main`. This is the most accurate way to verify the difference between the two methods while learning.

## 6. Synchronizing sequence with `join()`, not with `run()`

Beginners sometimes choose `run()` because they want to "wait for it to finish". That turns the work into a sequential call, giving up concurrency. If you need the worker to run independently but must wait for the result at a specific point, use `start()` combined with `join()`:

```java
Thread worker = new Thread(() -> performWork());
worker.start();

// main can do independent work here.
worker.join(); // Wait for worker to finish before continuing.
```

This is an **illustrative snippet**, where `performWork()` is an application-defined method. `join()` can throw `InterruptedException`; real programs need to propagate the exception or handle the interrupt signal properly.

In essence, `join()` makes `main` wait after allowing the worker to execute independently for a period of time. With `run()`, all the work is already inside the call on `main`; there is no new worker for `join()` to wait on.

## 7. `start()` establishes a happens-before relationship; `run()` does not create a thread-start edge

The Java Memory Model defines the **happens-before** relationship to describe ordering and memory visibility guarantees between threads:

- Actions in the calling thread **before a successful `thread.start()` call** happen-before any actions performed by the newly started thread.
- All actions in a thread happen-before another thread **successfully returns from `join()` on that thread**.
- Other explicit guarantees are still needed for shared access: `synchronized`, `volatile`, atomic types, or concurrent collections depending on the case.

Example `StartVisibilityDemo.java`:

```java
public class StartVisibilityDemo {
    private static int input;
    private static int result;

    public static void main(String[] args) throws InterruptedException {
        input = 21;

        Thread worker = new Thread(() -> result = input * 2);
        worker.start();
        worker.join();

        System.out.println("result=" + result);
    }
}
```

```bash
javac StartVisibilityDemo.java
java StartVisibilityDemo
```

Output:

```text
result=42
```

`input = 21` happens before `start()`, so the worker is guaranteed to see that update via the happens-before relationship. The worker's write to `result` is guaranteed to be visible after `join()` completes. The example does not need `volatile` because the two synchronization edges above establish the required ordering.

However, replacing `worker.join()` with a loop reading `result` without synchronization can introduce visibility bugs; `start()` alone does not guarantee that all future writes will be safely observed by `main`. And calling `worker.run()` directly executes the statements in program order on `main`, **without creating a startup edge between two threads**, because no second thread is started.

## 8. Exceptions: handled on the caller or on the worker?

When `run()` is called directly, an uncaught exception in `run()` propagates to the calling thread. When `run()` is executed by the JVM after `start()`, an unhandled exception occurs **in the worker**; a `try/catch` around `thread.start()` in `main` cannot catch an exception thrown later in the worker.

Create the file `ThreadExceptionDemo.java`:

```java
public class ThreadExceptionDemo {
    public static void main(String[] args) throws InterruptedException {
        Runnable failure = () -> {
            throw new IllegalStateException("boom");
        };

        Thread direct = new Thread(failure, "direct");
        try {
            direct.run();
        } catch (IllegalStateException e) {
            System.out.println("main bắt được: " + e.getMessage());
        }

        Thread worker = new Thread(failure, "worker");
        worker.setUncaughtExceptionHandler((thread, error) ->
                System.out.println("handler: " + thread.getName()
                        + " -> " + error.getMessage()));
        worker.start();
        worker.join();
    }
}
```

```bash
javac ThreadExceptionDemo.java
java ThreadExceptionDemo
```

Output:

```text
main bắt được: boom
handler: worker -> boom
```

In the first case, `direct.run()` throws on `main`'s stack, so the `catch` in `main` handles it. In the second case, the worker throws the exception on its own stack; the `UncaughtExceptionHandler` attached to the worker handles the error information. `join()` waits for the worker to terminate, but does not rethrow the worker's exception to `main`.

In applications that need to collect task results or failures, `ExecutorService.submit` with `Future.get` may be more appropriate: `get` reports task failures via `ExecutionException` and lets the caller handle them proactively. Executor error reporting is a task management mechanism and does not change the semantics of `Thread.start()` and `Thread.run()`.

## 9. `Thread` object states and common misconceptions

The states observed via `Thread.getState()` are `NEW`, `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING`, and `TERMINATED`. Instantaneous observation is affected by scheduling; do not write programs that depend on state checks between two racing statements.

| Operation | New thread started? | Execution context of `run()` | Effect on `thread` object lifecycle |
| --- | --- | --- | --- |
| `new Thread(job)` | Not yet | Not running task yet | `NEW` |
| `thread.run()` when thread has not started | No | Calling thread, e.g., `main` | Remains `NEW` |
| Successful `thread.start()` | Yes | Thread represented by `thread` | Leaves `NEW`, eventually `TERMINATED` |
| `thread.join()` after `start()` | Does not create another | Does not re-run task by itself | Caller waits for thread to terminate |
| Calling `start()` a second time | No | Does not run task again | Throws `IllegalThreadStateException` |

**A subtle point:** `run()` is a method that can be called directly under Java syntax, but a `Thread` object also has internal state managed by the JVM. Do not misuse `thread.run()` as an API for running work at arbitrary times. If you want to invoke work sequentially, call `job.run()` directly or extract the logic into a regular service method to keep the intent clear.

## 10. Virtual threads also have the `start`/`run` distinction

Since Java 21, a virtual thread is a JVM-managed `Thread` optimized for many waiting I/O-bound tasks. It still follows the fundamental rule:

- `Thread.ofVirtual().unstarted(job)` creates a virtual thread in the unstarted state.
- Calling `virtual.start()` starts a **new virtual thread** and lets the JVM schedule it onto a carrier.
- Calling `virtual.run()` directly on an unstarted object **does not start a virtual thread**; the work (if executed according to the invoked method) runs on the caller. To run virtual work as intended, always use a `start()` API or an executor that creates virtual threads.
- `Thread.ofVirtual().start(job)` combines creation and starting, equivalent in intent to creating an unstarted thread and then calling `start()`.
- `Executors.newVirtualThreadPerTaskExecutor()` creates a new virtual thread for each task submitted to the executor; this is not a direct `run()` call on `main`.

Example `VirtualStartDemo.java` (JDK 21+):

```java
public class VirtualStartDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread virtual = Thread.ofVirtual().unstarted(() ->
                System.out.println("isVirtual="
                        + Thread.currentThread().isVirtual()));

        virtual.start();
        virtual.join();
        System.out.println("done=" + !virtual.isAlive());
    }
}
```

```bash
javac VirtualStartDemo.java
java VirtualStartDemo
```

Output:

```text
isVirtual=true
done=true
```

`Thread.currentThread().isVirtual()` executes **inside** the virtual thread after `start()`, so it is `true`. The `done=true` line is only printed after `join()`. A virtual thread is not "fake" concurrency: it has its own Java thread identity and lifecycle, even though the JVM can mount/unmount it from carrier threads while waiting on I/O.

## 11. When to use `start()`, when to use `run()`, and when to use an executor?

### Wanting a task to run independently of the calling thread

Use `thread.start()`. Manage lifecycle, interruption, and resource cleanup explicitly; if you need the result, combine it with an appropriate waiting mechanism. For a few fixed threads with clear roles, working directly with `Thread` can be simple enough.

### Wanting to run a single task synchronously

Call **the work method itself**, such as `job.run()` or `service.perform()`. Calling `thread.run()` directly can technically execute the same work, but it misleads readers into thinking you are starting a thread.

### Wanting to manage many tasks, results, queues, and cancellation

Use `ExecutorService`. A fixed pool reuses platform threads across many tasks; `newVirtualThreadPerTaskExecutor()` creates a new virtual thread per task when appropriate for I/O-bound workloads. They differ in execution policy, but both decouple **tasks** from the low-level detail of calling `Thread.start()` directly. When using an executor, wait for results with `Future.get()` or another appropriate mechanism; do not manually call `run()` on an executor-managed `Thread` object.

Having many threads does not automatically make a system faster. If tasks are CPU-bound, the core count is the bottleneck; if waiting on network or database connections, there are also connection pools, downstream system limits, timeouts, and data safety to consider. Virtual threads do not make external resources infinite.

## 12. Common mistakes and how to fix them

**Mistake 1 — assuming it is already running multithreaded:**

```java
Thread t = new Thread(() -> doWork());
t.run(); // Wrong if the goal is to start a new thread.
```

An illustrative snippet, with `doWork()` defined by the application. Fix it to `t.start()`, then decide whether `t.join()` is needed.

**Mistake 2 — calling both `start()` and `run()` to "make sure it starts":**

```java
Thread t = new Thread(() -> doWork());
t.start();
t.run(); // May execute the work again on the caller!
```

This is not how you wait for a worker. It risks running `doWork()`'s logic twice or racing on data with the worker itself. If you want to wait for the started thread, call `t.join()`; if you just want to invoke the task sequentially again, use an explicit work API.

**Mistake 3 — calling `start()` again after the worker finishes:** a `Thread` cannot be restarted. Create a new thread or use an executor that accepts new tasks.

**Mistake 4 — assuming `start()` waits for completion before returning:** `start()` only starts the thread. To observe results after the worker finishes, use `join()`/`Future.get()` and set up proper synchronization.

**Mistake 5 — thinking `start()` automatically protects shared variables:** happens-before relationships at start and join do not replace synchronization while two threads concurrently modify data. For a shared counter, `counter++` can still lose updates; consider `AtomicInteger`, `synchronized`, or concurrent data structures.

**Mistake 6 — catching exceptions around `start()` to intercept task failures:** exceptions thrown later in the worker do not automatically return to the caller's stack. Use error handling inside the task, `UncaughtExceptionHandler`, or the executor's error-reporting mechanism.

## 13. Check your understanding

1. **Does the following run on a new thread?**
   `Thread t = new Thread(() -> System.out.println(Thread.currentThread().getName())); t.run();`

   **Answer:** No. The `run()` call executes on the calling thread, usually `main`. The object `t` remains `NEW` if it has not been `start()`ed.
2. **After `t.start()`, can `t.start()` be called again once `t` is `TERMINATED`?**

   **Answer:** No. A `Thread` object can only be started successfully once. A subsequent call throws `IllegalThreadStateException`.
3. **If `main` needs to perform task A while a worker performs B, and then use B's result, should you use `run()` or `start()`?**

   **Answer:** `start()` so B progresses independently; `main` does A; then wait with `join()` or retrieve the result via `Future`. Using `run()` will run B synchronously before A if B's call is placed first.
4. **Why can `Thread.currentThread() == t` be false inside `t.run()`?**

   **Answer:** When `t.run()` is called directly on `main`, `this` is still `t` but the running thread is `main`; only `start()` makes the JVM execute `run()` in thread `t`.
5. **Can you replace `t.start()` with `t.run()` to avoid race conditions?**

   **Answer:** That only makes that specific call sequential and can hide contention in tests. It gives up concurrency and does not fix shared access if other threads are still active.
6. **Does `t.start()` guarantee that `main` immediately sees every variable the worker modifies?**

   **Answer:** No. `start()` guarantees that the caller's actions before `start()` are visible to the worker via happens-before; for `main` to see results after the worker finishes, you can use `join()` or another synchronization mechanism.

## 14. Key takeaway

**`start()` starts a new Java thread; calling `run()` directly is a normal method call on the current thread.** A `Thread` object can only be `start()`ed successfully once, whereas `run()` can be called like a regular method without starting a thread. When you need concurrency, start the thread and manage completion with `join()` or an executor; when you need synchronous execution, call the work logic directly. Distinguishing the two calls helps you accurately read `Thread` states, execution order, exception propagation, and memory guarantees in Java programs.
