# Creating Threads with `Thread.ofVirtual()` and `Thread.startVirtualThread()` in Java

## 1. Purpose and Runtime Requirements

A **virtual thread** is a `java.lang.Thread` managed and scheduled by the Java runtime, rather than being tied to an operating system thread for its entire lifetime. Virtual threads are suited for large volumes of **I/O-bound waiting work**: database queries, HTTP calls, reading/writing sockets, and waiting for responses from other services. The goal is to preserve a readable sequential programming style while still supporting many concurrent waiting tasks.

This lesson focuses on two ways to create and start virtual threads in **plain Java**:

- `Thread.startVirtualThread(Runnable task)`: creates **and immediately starts** a virtual thread with a concise call.
- `Thread.ofVirtual()`: obtains a `Thread.Builder.OfVirtual` to configure the name, exception handler, create an unstarted thread, start a thread, or create a `ThreadFactory`.

**Requirement:** JDK **21 or later**; virtual threads became a standard feature in Java 21 (JEP 444). The examples below compile with `javac` and run with `java` without needing `--enable-preview`. In JDK 19–20, virtual threads were a preview feature, so the requirements and APIs differed.

Check your environment:

~~~bash
java -version
javac -version
~~~

Virtual threads should not be equated with making the CPU run faster. They help scale **the number of concurrent waiting tasks**, not increase the number of CPU cores.

## 2. Two Core APIs

### 2.1. `Thread.startVirtualThread(Runnable)` — create and start immediately

API signature:

~~~java
public static Thread startVirtualThread(Runnable task)
~~~

- Takes a `Runnable` and runs the body of `run()` on a **new virtual thread**.
- Returns a `Thread` object **that has already been started**; the work may execute before or after the call returns.
- To wait for completion, call `join()`. To request cancellation while waiting or processing, call `interrupt()` and design the task to cooperate with interruption.
- There is no direct option to set a name in this call; when configuration is needed, use the builder.

Standalone example, saved as **`StartVirtualThreadDemo.java`**:

~~~java
public class StartVirtualThreadDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = Thread.startVirtualThread(() -> {
            System.out.println(
                    "Đang chạy trên virtual thread: "
                            + Thread.currentThread().isVirtual());
        });

        worker.join();
        System.out.println("Đã kết thúc: " + !worker.isAlive());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 StartVirtualThreadDemo.java
java StartVirtualThreadDemo
~~~

Expected output:

~~~text
Đang chạy trên virtual thread: true
Đã kết thúc: true
~~~

`Thread.currentThread()` returns the **virtual thread currently executing** the code, and `isVirtual()` indicates the thread type. `join()` forces the `main` thread to wait for the worker to finish, so the order of the two output lines is deterministic. Virtual threads are **daemon threads** by default, so for short programs you need to wait or manage their lifecycle explicitly; do not rely on the JVM staying alive just because a virtual thread is still running.

### 2.2. `Thread.ofVirtual()` — configurable builder

`Thread.ofVirtual()` **does not itself create or start a thread**. It returns a builder:

~~~java
Thread.Builder.OfVirtual builder = Thread.ofVirtual();
~~~

Key operations:

| Method | Meaning |
| --- | --- |
| `builder.start(task)` | Creates and starts a virtual thread, returning the running `Thread` |
| `builder.unstarted(task)` | Creates a virtual thread in the `NEW` state; requires calling `thread.start()` |
| `builder.name("ten")` | Sets a fixed name for threads created from the builder |
| `builder.name("prefix-", 1)` | Sets a name prefix and counter, e.g. `prefix-1`, `prefix-2` |
| `builder.uncaughtExceptionHandler(handler)` | Handles uncaught exceptions thrown by the thread |
| `builder.inheritInheritableThreadLocals(false)` | Does not inherit `InheritableThreadLocal` values from the creating thread |
| `builder.factory()` | Creates a `ThreadFactory` with the corresponding configuration |

Standalone example, saved as **`VirtualThreadBuilderDemo.java`**:

~~~java
public class VirtualThreadBuilderDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = Thread.ofVirtual()
                .name("vt-report")
                .unstarted(() -> System.out.println(
                        "Tên worker: " + Thread.currentThread().getName()));

        System.out.println("Trước start: " + worker.getState());
        worker.start();
        worker.join();
        System.out.println("Sau join: " + worker.getState());
    }
}
~~~

~~~bash
javac -encoding UTF-8 VirtualThreadBuilderDemo.java
java VirtualThreadBuilderDemo
~~~

Expected output:

~~~text
Trước start: NEW
Tên worker: vt-report
Sau join: TERMINATED
~~~

Comparing the three styles:

~~~java
Runnable job = () -> System.out.println("Hello");

// A: shortest, creates and starts immediately
Thread a = Thread.startVirtualThread(job);

// B: creates and starts immediately, allows additional configuration on the builder
Thread b = Thread.ofVirtual().name("vt-b").start(job);

// C: creates first, explicitly controls when to start
Thread c = Thread.ofVirtual().name("vt-c").unstarted(job);
c.start();

a.join();
b.join();
c.join();
~~~

The snippet above is a **code fragment placed inside a method that can throw `InterruptedException`**, not a complete Java file. The three `Hello` lines may appear in any order; calling `start()` does **not** mean the work finishes before the next statement executes.

**Lifecycle rule:** a `Thread` object may only be `start()`ed **once**. Calling `start()` again (even after the thread has terminated) throws `IllegalThreadStateException`. Calling `run()` directly does not replace `start()`; for a virtual thread, calling `Thread.run()` directly does not execute the task attached to the thread as expected.

## 3. Which Approach to Choose for Each Situation?

| Need | Choice |
| --- | --- |
| Quickly run a `Runnable` and `join()` | `Thread.startVirtualThread(task)` |
| Set a name or handler for a single worker | `Thread.ofVirtual().name(...).start(task)` |
| Create a thread first and explicitly start it later | `Thread.ofVirtual().unstarted(task)` then `start()` |
| Create multiple workers with a shared naming convention | `Thread.ofVirtual().name(prefix, start).factory()` |
| Run many independent tasks needing `Future`/results | `Executors.newVirtualThreadPerTaskExecutor()` |

`Thread.startVirtualThread(task)` is equivalent in basic creation/starting behavior to `Thread.ofVirtual().start(task)`. The useful difference is that **the builder can be configured** before creating the thread. You do not need a builder just to use virtual threads.

When using `Thread.Builder.OfVirtual` to create multiple threads, do not arbitrarily share a mutable builder across threads: the builder is **not guaranteed to be thread-safe**. For many tasks, a `ThreadFactory` or `ExecutorService` is usually simpler.

## 4. `ThreadFactory` and Creating Multiple Named Virtual Threads

`factory()` returns a `java.util.concurrent.ThreadFactory`; calling `newThread(task)` creates an **unstarted** virtual thread. This differs from `builder.start(task)`.

Standalone example, saved as **`VirtualThreadFactoryDemo.java`**:

~~~java
import java.util.concurrent.ThreadFactory;

public class VirtualThreadFactoryDemo {
    public static void main(String[] args) throws InterruptedException {
        ThreadFactory factory = Thread.ofVirtual()
                .name("vt-worker-", 1)
                .factory();

        Thread first = factory.newThread(() -> {});
        Thread second = factory.newThread(() -> {});

        System.out.println(first.getName());
        System.out.println(second.getName());
        System.out.println("Chưa chạy: " + (first.getState() == Thread.State.NEW));

        first.start();
        second.start();
        first.join();
        second.join();
    }
}
~~~

~~~bash
javac -encoding UTF-8 VirtualThreadFactoryDemo.java
java VirtualThreadFactoryDemo
~~~

Expected output:

~~~text
vt-worker-1
vt-worker-2
Chưa chạy: true
~~~

`factory.newThread(...)` creates a thread according to the factory configuration; the caller is responsible for calling `start()` if using the factory directly. A factory can also be passed to APIs that accept a `ThreadFactory`, provided that API fits the thread-per-task model.

## 5. Running Many I/O-Bound Tasks: The One-Virtual-Thread-Per-Task Model

The two APIs in the title are suitable for understanding thread creation mechanics. When a program needs to return results, collect errors, and manage the lifecycle of **many tasks**, Java 21 also provides `Executors.newVirtualThreadPerTaskExecutor()`. This executor creates **a new virtual thread for each submitted task**; it is not a pool that reuses virtual threads.

Standalone example, saved as **`VirtualThreadTasksDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class VirtualThreadTasksDemo {
    public static void main(String[] args) throws Exception {
        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {

            List<Future<String>> futures = new ArrayList<>();

            for (int i = 1; i <= 3; i++) {
                int taskId = i; // each lambda captures its own copy
                futures.add(executor.submit(() -> {
                    Thread.sleep(100); // simulate an I/O wait operation
                    return "Task " + taskId
                            + ": virtual=" + Thread.currentThread().isVirtual();
                }));
            }

            for (Future<String> future : futures) {
                System.out.println(future.get());
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 VirtualThreadTasksDemo.java
java VirtualThreadTasksDemo
~~~

Expected output:

~~~text
Task 1: virtual=true
Task 2: virtual=true
Task 3: virtual=true
~~~

Key takeaways:

1. The three tasks can run **concurrently**; `Thread.sleep(100)` simulates waiting and does not demonstrate real-world performance.
2. The `get()` loop reads `Future`s in **submission order**, so the output order is deterministic even if completion times differ. If a task throws an error, `Future.get()` reports an `ExecutionException` wrapping the root cause.
3. `try-with-resources` calls `ExecutorService.close()`, waiting for all tasks to finish when exiting the scope; it avoids neglecting worker lifecycles.
4. Do not turn each virtual thread into a long-lived worker that receives multiple jobs. The recommended model is to **create a new virtual thread for each task**, and only limit access to genuinely scarce resources.

Example of limiting access to a service to only two concurrent requests using a `Semaphore` (code fragment inside an appropriate class/method):

~~~java
import java.util.concurrent.Semaphore;

Semaphore permits = new Semaphore(2);

Runnable job = () -> {
    try {
        permits.acquire();
        try {
            // Perform concurrency-limited I/O operation here.
        } finally {
            permits.release();
        }
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
    }
};

Thread worker = Thread.startVirtualThread(job);
~~~

A `Semaphore` is how you limit the number of concurrent I/O operations against a resource; there is no need to build a "virtual-thread pool" just to throttle concurrency. This example has an **illustrative** placeholder in the comment rather than a real I/O operation and has no fixed stdout.

## 6. Execution Mechanism and Differences from Platform Threads

A traditional platform `Thread` typically maps to an operating system thread; a large number of them incurs significant stack and scheduling overhead. With virtual threads, the Java runtime schedules many virtual threads onto a relatively small set of platform threads called **carrier threads**.

When a virtual thread is executing, it can be **mounted** onto a carrier. When it encounters a waiting operation supported by the runtime, such as `Thread.sleep` and many blocking I/O operations in the JDK, the virtual thread can **unmount** so the carrier can run other work. When ready, the virtual thread is scheduled to resume, possibly on a different carrier. Therefore, you must **not** rely on carrier identity or assume each virtual thread has its own OS thread.

### Differences in Purpose

| Aspect | Platform thread | Virtual thread |
| --- | --- | --- |
| Thread creation resources | Relatively expensive | Significantly cheaper for many tasks |
| Primary scheduling | Operating system | Java runtime schedules onto carriers |
| Many I/O-blocking tasks | Requires many OS threads, easily exhausts resources | Usually scales better |
| Long-running CPU-bound tasks | Suitable with an appropriate worker count | Does not inherently speed up CPU computation |
| Control APIs | `start`, `join`, `interrupt`... | Uses the same familiar `Thread` APIs |

**Version note on pinning:** on JDK **21–23**, a virtual thread can become *pinned* to its carrier when performing a blocking operation inside a `synchronized` block/method or when executing native/foreign code, reducing scalability. **JDK 24** implements JEP 491 to resolve most `synchronized`-related pinning cases. Native/foreign operations and unsupported blocking cases still need to be measured in practice. You should not mechanically apply the advice "replace all `synchronized` with `ReentrantLock`" across every version.

## 7. Lifecycle, Errors, and Task Cancellation

### 7.1. `join()` and Daemons

`start()` only schedules the work; it does not wait for the result. `join()` waits for the target thread to terminate; the method can throw `InterruptedException` if **the waiting thread** is interrupted. Virtual threads are daemon threads: when no non-daemon threads remain to keep the JVM alive, unfinished virtual threads may not get a chance to complete. For work that must finish, use `join()`, `Future.get()`, or an equivalent lifecycle-management mechanism.

Do not misuse `join()` **immediately after each start** inside a loop if you want tasks to run concurrently:

~~~java
// Serializes work (no benefit when waiting on I/O):
for (Runnable task : tasks) {
    Thread.startVirtualThread(task).join();
}

// Start all first, then wait for all:
List<Thread> workers = new ArrayList<>();
for (Runnable task : tasks) {
    workers.add(Thread.startVirtualThread(task));
}
for (Thread worker : workers) {
    worker.join();
}
~~~

This is an **illustrative snippet**: place it inside a method that has `tasks`, import `java.util.List` and `java.util.ArrayList`, and handle `InterruptedException`. In larger systems, an executor is usually more appropriate for managing many tasks.

### 7.2. `interrupt()` Is a Cooperative Cancellation Request

`interrupt()` does **not** forcibly stop executing bytecode. Many waiting operations such as `Thread.sleep` throw `InterruptedException`, usually clearing the interrupt flag at the same time; when you cannot fully handle the cancellation request, restore the flag with `Thread.currentThread().interrupt()`.

Standalone example, saved as **`VirtualThreadInterruptDemo.java`**:

~~~java
public class VirtualThreadInterruptDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = Thread.ofVirtual().name("vt-sleeper").start(() -> {
            try {
                Thread.sleep(10_000);
            } catch (InterruptedException e) {
                System.out.println("Worker nhận yêu cầu interrupt");
                Thread.currentThread().interrupt();
            }
        });

        worker.interrupt();
        worker.join();
        System.out.println("Worker đã dừng");
    }
}
~~~

~~~bash
javac -encoding UTF-8 VirtualThreadInterruptDemo.java
java VirtualThreadInterruptDemo
~~~

Expected output:

~~~text
Worker nhận yêu cầu interrupt
Worker đã dừng
~~~

Because `interrupt()` is sent almost immediately after `start()`, the worker may not have called `sleep()` yet; even so, `sleep()` checks the interrupt flag and throws the exception. Never use `Thread.stop()` to forcibly stop a thread.

### 7.3. Exceptions in `Runnable`

An uncaught exception in a `Runnable` terminates the virtual thread; `join()` **does not automatically rethrow** that exception to the caller. You can configure an `uncaughtExceptionHandler` when using the builder, or use `Callable` and `Future` if the caller needs to receive results/errors.

Standalone example, saved as **`VirtualThreadErrorDemo.java`**:

~~~java
public class VirtualThreadErrorDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = Thread.ofVirtual()
                .name("vt-validate")
                .uncaughtExceptionHandler((thread, error) ->
                        System.out.println(thread.getName()
                                + " báo lỗi: " + error.getMessage()))
                .start(() -> {
                    throw new IllegalStateException("Dữ liệu không hợp lệ");
                });

        worker.join();
        System.out.println("Đã join");
    }
}
~~~

~~~bash
javac -encoding UTF-8 VirtualThreadErrorDemo.java
java VirtualThreadErrorDemo
~~~

Expected output:

~~~text
vt-validate báo lỗi: Dữ liệu không hợp lệ
Đã join
~~~

The handler is only invoked when there is an **uncaught exception**; if the task catches the exception itself, the handler does not run. With an executor, exceptions in `submit`ted tasks are typically recorded in the `Future` and retrieved via `get()`.

## 8. Common Misconceptions and Mistakes

1. **"`Thread.ofVirtual()` already creates a thread."** Not true: it is a builder. Calling `start(task)` or `unstarted(task)` is what creates the thread.
2. **"`unstarted(task)` runs on its own."** False: the thread is in the `NEW` state. You must call `start()` exactly once.
3. **"`startVirtualThread(task)` finishes running before returning."** False: it creates and starts the thread; the worker runs asynchronously with respect to the caller.
4. **"You can `start()` a `Thread` multiple times."** False: calling it a second time throws `IllegalThreadStateException`.
5. **"Virtual threads make CPU-bound loops faster."** Not by default; CPU resources do not increase. Measure throughput and latency for your actual workload.
6. **"Virtual threads consume no memory."** False: their stack and state still consume memory; creating too many tasks holding `ThreadLocal`s or large data will put pressure on the heap/GC.
7. **"Virtual threads need pooling like OS threads."** Usually unnecessary. Start one thread per task, and limit connections or requests to a resource with a semaphore/connection pool when needed.
8. **"Using `synchronized` always causes a virtual thread to be pinned."** It depends on the JDK version and where blocking occurs; JDK 24 significantly improves monitor behavior, though native/foreign blocking still warrants attention.
9. **"`join()` propagates exceptions from the worker to main."** False: `join()` only waits. To capture results/errors, use `Future` or an explicit error-passing mechanism.
10. **"Every blocking I/O call is automatically efficient with virtual threads."** Not guaranteed for every library or native API; you should test, monitor, apply timeouts, and check system limits.

## 9. Adoption Checklist

- Use JDK 21+; choose `Thread.startVirtualThread` for simple tasks or `Thread.ofVirtual` when you need a name, handler, unstarted creation, or a factory.
- Give each task a termination point, timeout/cooperative cancellation, and error handling; decide who will `join`/`close`/get the `Future`.
- Use virtual threads for mostly I/O-bound workloads; keep reasonable limits on database connections, sockets, and downstream services.
- When measuring performance, distinguish throughput, latency, CPU, heap, connection count, and pinning scenarios. Do not draw conclusions from spawning many threads or simulated `sleep`s.
- Give workers meaningful names and use observability tools (thread dumps/JFR) when diagnosing waiting states; remember that virtual threads have an empty name by default if not set.
- Rely on `Thread` semantics (start once, cooperative interruption, join to wait), while keeping in mind that carrier behavior can vary by JDK version.

### Official Reference Documentation

- [Java SE 21 — `Thread`, `ofVirtual()`, and `startVirtualThread()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html).
- [Java SE 21 — `Thread.Builder.OfVirtual`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.Builder.OfVirtual.html).
- [JEP 444 — Virtual Threads (Java 21)](https://openjdk.org/jeps/444).
- [JEP 491 — Synchronize Virtual Threads without Pinning (JDK 24)](https://openjdk.org/jeps/491).
