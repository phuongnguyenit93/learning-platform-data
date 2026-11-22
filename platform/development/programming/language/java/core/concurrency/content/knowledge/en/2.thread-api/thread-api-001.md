# Creating Threads with Thread and Runnable in Java

## 1. Objectives and Context

After this lesson, you will be able to:

- Create, name, start, and wait for the completion of a thread using the **Thread** class and the **Runnable** interface.
- Distinguish between **calling run()** and **calling start()**, and understand when code executes on the current thread or a new thread.
- Choose between extending Thread, implementing Runnable, and using a lambda; understand the relationship between a **task** and the **thread executing the task**.
- Manage the basic lifecycle, handle interruption with **interrupt()**, and recognize the risks when multiple threads share data.
- Correctly interpret the output of multithreaded programs: execution order is usually not guaranteed, and results depend on synchronization.

The scope is **general Java concurrency** through the core JDK APIs; Spring's thread management, asynchronous tasks, or configuration are not covered.

A **thread** is an independent flow of execution within the same Java process. Threads share the heap and shared objects, but each thread has its own call stack. When multiple threads coexist, tasks can *interleave* (concurrency); they can actually run *in parallel* (parallelism) if CPU resources and the scheduler allow. Execution order cannot be inferred from the order in which **start()** is called.

## 2. Two Core APIs: Thread and Runnable

**java.lang.Thread** represents a thread and provides operations such as **start()**, **join()**, **interrupt()**, **isAlive()**, **getState()**, and **getName()**. When **start()** is called on a Thread object in the NEW state, the JVM arranges for that thread's **run()** method to execute on a new flow of execution. **start()** returns without waiting for the work to complete.

**java.lang.Runnable** is a functional interface with a single abstract method:

~~~java
@FunctionalInterface
public interface Runnable {
    void run();
}
~~~

This is a simplified form to explain the API contract; **java.lang.Runnable** is already built into the JDK and does not need to be redeclared. A **Runnable** describes what needs to be done, but by itself **does not create or start a thread**. We pass a Runnable into a Thread, and then call **start()** on that Thread.

Relationship diagram:

~~~text
Runnable task ──(passed into constructor)──> Thread worker
                                              │
                                           start()
                                              │
                                  new thread calls task.run()
~~~

Key takeaway: **Thread is the execution mechanism; Runnable is the unit of work**. Thread also implements Runnable, so you can override **Thread.run()** to describe the work directly.

## 3. Three Ways to Create and Run a Thread

The following example runs standalone on **Java 17+** and demonstrates all three approaches: extending Thread, implementing Runnable, and using a lambda as a Runnable.

File **ThreadCreationDemo.java**:

~~~java
public class ThreadCreationDemo {

    static class ByThread extends Thread {
        ByThread() {
            super("class-thread");
        }

        @Override
        public void run() {
            System.out.println(getName() + ": chạy bằng Thread");
        }
    }

    static class ByRunnable implements Runnable {
        @Override
        public void run() {
            System.out.println(
                Thread.currentThread().getName() + ": chạy bằng Runnable"
            );
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Thread first = new ByThread();
        first.start();
        first.join();

        Thread second = new Thread(new ByRunnable(), "runnable-thread");
        second.start();
        second.join();

        Runnable task = () -> System.out.println(
            Thread.currentThread().getName() + ": chạy bằng lambda"
        );
        Thread third = new Thread(task, "lambda-thread");
        third.start();
        third.join();

        System.out.println("main: hoàn tất");
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac -encoding UTF-8 ThreadCreationDemo.java
java ThreadCreationDemo
~~~

Output when the terminal displays Unicode properly:

~~~text
class-thread: chạy bằng Thread
runnable-thread: chạy bằng Runnable
lambda-thread: chạy bằng lambda
main: hoàn tất
~~~

This example has deterministic output order **because each start() is followed by join() before starting the next thread**. If all three threads were started first and joined afterward, the lines from the three threads could appear in various orders.

### 3.1. Extending Thread

~~~java
class Worker extends Thread {
    @Override
    public void run() {
        // Work that runs when start() is called on Worker.
    }
}

Thread worker = new Worker();
worker.start();
~~~

The snippet above illustrates usage; the Worker class does not yet have a **main()** method to run as a standalone application. This approach is simple when you need a specialized thread type with its own behavior, but it couples the task code to the Thread object itself. Java only supports single-class inheritance, so a class that **extends Thread** cannot extend another class.

### 3.2. Implementing Runnable

~~~java
class ReportTask implements Runnable {
    @Override
    public void run() {
        System.out.println("Building report");
    }
}

Runnable task = new ReportTask();
Thread worker = new Thread(task, "report-worker");
worker.start();
~~~

This is also an illustrative snippet that needs to be placed inside a valid program. Using **implements Runnable** separates what needs to be done from how it is run; the same task class can be used to create multiple Threads. A single Runnable instance can also be passed to multiple Threads, but in that case **the state of that Runnable object itself will be shared**.

### 3.3. Lambda

Because Runnable is a functional interface, it can be written concisely:

~~~java
Runnable task = () -> System.out.println(
    "Running on " + Thread.currentThread().getName()
);
Thread worker = new Thread(task, "lambda-worker");
worker.start();
~~~

Lambdas are well suited for short tasks. Local variables captured by a lambda must be **final or effectively final**; this rule does not make a captured mutable object thread-safe.

### Which Approach Should You Choose?

| Criterion | extends Thread | implements Runnable / lambda |
| --- | --- | --- |
| Role | Defines behavior directly inside the thread class | Defines an independent task |
| Task reusability | Coupled to a specific Thread | Can create multiple Threads or pass to an executor |
| Inheriting another class | Cannot extend another class | Can extend another class |
| Separation of concerns | Lower | Higher |
| Default recommendation | When you genuinely need to customize Thread | **Prefer Runnable** for typical tasks |

Both paths still ultimately require a **Thread.start()** call to get a new thread when using the classic API directly.

## 4. How Does start() Differ from run()?

**run() is a normal Java method call**. When calling **worker.run()** directly, the code runs synchronously on the calling thread; no new thread is created. **start()** is what asks the JVM to begin another thread and then execute **run()** on that thread.

File **StartVsRunDemo.java**:

~~~java
public class StartVsRunDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(
            () -> System.out.println(
                "task: " + Thread.currentThread().getName()
            ),
            "worker-1"
        );

        worker.run();   // Runs directly on main.
        worker.start(); // Starts a new thread.
        worker.join();  // Waits for worker to finish.
    }
}
~~~

~~~bash
javac -encoding UTF-8 StartVsRunDemo.java
java StartVsRunDemo
~~~

Stdout:

~~~text
task: main
task: worker-1
~~~

You can call **run()** directly multiple times like a normal method, but **a Thread object can only have start() called on it once**. Calling **start()** again after it has already been started, even if it has finished, throws **IllegalThreadStateException**. To run the task again, create a **new Thread**; an old Thread cannot be reset back to NEW.

## 5. Thread Lifecycle and Scheduling

The states returned by **Thread.getState()**:

| State | Practical Meaning |
| --- | --- |
| **NEW** | The Thread object has been created, but start() has not been called yet. |
| **RUNNABLE** | Eligible to run or currently running in the JVM; does not necessarily mean it is currently occupying a CPU. |
| **BLOCKED** | Waiting to acquire a monitor lock when entering a synchronized block/method. |
| **WAITING** | Waiting indefinitely without a timeout, e.g., join() without timeout or Object.wait() without timeout. |
| **TIMED_WAITING** | Waiting for a bounded time, e.g., Thread.sleep(...) or join(timeout). |
| **TERMINATED** | The run() method has finished, either by completing normally or due to an uncaught error. |

Typical flow:

~~~text
NEW --start()--> RUNNABLE --run() finishes--> TERMINATED
                     │
            can transition through
            BLOCKED / WAITING / TIMED_WAITING
                     │
                 RUNNABLE
~~~

**getState() is only an instantaneous snapshot**, suitable for observation or diagnostics, not for building synchronization protocols. The scheduler does not guarantee which thread will run first, how long it will run, or whether threads will run in parallel.

**Thread.currentThread()** returns the Thread object currently executing the code, and **getName()** helps distinguish threads in logs. You can set the name via the constructor or **setName(...)**, ideally before **start()**. Names help with observability and do not determine scheduling order.

### Waiting for Completion with join()

**join()** causes the calling thread to wait for the target thread to finish. With the code:

~~~java
Thread worker = new Thread(() -> doWork());
worker.start();
worker.join();
consumeResult();
~~~

This is a control-flow example where **doWork()** and **consumeResult()** are hypothetical methods that would need to be defined. After **join() returns normally because worker has finished**, the memory effects of worker happen-before the subsequent operations of the thread that called join. This does not mean all accesses to the same variable are safe *while both threads are running*.

**join()** can throw **InterruptedException** if the waiting thread is interrupted. Overloads with a timeout, such as **join(1000)**, may return while worker is still alive: if you need to be certain it has finished, check **isAlive()** or use an appropriate waiting protocol.

## 6. Threads Sharing Data: The Risk of Race Conditions

Creating multiple threads does not automatically make a program thread-safe. Threads share the heap, so incrementing **count++** on a variable typically consists of read, add, and write; it is not an atomic operation. If two threads update it concurrently without synchronization, **lost updates** and memory *visibility* issues can occur. Marking the variable **volatile** only addresses certain visibility/ordering requirements; **it does not make count++ atomic**.

A correct example using **AtomicInteger**, sharing a single Runnable instance:

File **SharedCounterDemo.java**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class SharedCounterDemo {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger total = new AtomicInteger();

        Runnable increment = () -> {
            for (int i = 0; i < 10_000; i++) {
                total.incrementAndGet();
            }
        };

        Thread first = new Thread(increment, "counter-1");
        Thread second = new Thread(increment, "counter-2");

        first.start();
        second.start();

        first.join();
        second.join();

        System.out.println("total=" + total.get());
    }
}
~~~

~~~bash
javac -encoding UTF-8 SharedCounterDemo.java
java SharedCounterDemo
~~~

Stdout is always:

~~~text
total=20000
~~~

**Why is this correct?** Both Threads run the same Runnable, and both capture the same **AtomicInteger**. **incrementAndGet()** performs an atomic increment; **join()** ensures main waits for both threads to finish before reading the value. You must not replace this with **int[] total = {0}; total[0]++** and expect 20,000 every time: that is a data race.

Ways to protect shared state in Java include **synchronized**, locks, atomic classes, and concurrent data structures. Choose the mechanism suited to the operation being protected; **join()** only handles waiting for completion and publishing results when a thread finishes—it does not protect an ongoing sequence of concurrent updates.

## 7. Properly Interrupting Threads with interrupt()

**interrupt()** sends an interruption request signal; **it does not force a thread to stop immediately** and does not replace a safe cancellation mechanism. Running code must cooperate by checking **isInterrupted()** or reacting to **InterruptedException** in interruptible blocking operations (such as sleep, wait, and join).

File **InterruptDemo.java**:

~~~java
public class InterruptDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(() -> {
            try {
                while (!Thread.currentThread().isInterrupted()) {
                    Thread.sleep(1_000);
                }
            } catch (InterruptedException e) {
                // sleep() clears the interrupt status when throwing the exception.
                Thread.currentThread().interrupt();
            }

            System.out.println(
                "worker interrupted: "
                    + Thread.currentThread().isInterrupted()
            );
        }, "interruptible-worker");

        worker.start();
        worker.interrupt();
        worker.join();
    }
}
~~~

~~~bash
javac -encoding UTF-8 InterruptDemo.java
java InterruptDemo
~~~

Stdout:

~~~text
worker interrupted: true
~~~

This result holds whether the interrupt arrives before worker starts sleeping or while it is sleeping. If interrupted during **sleep()**, the method throws **InterruptedException** and clears the interrupt status; the **catch** branch restores the flag so the signal is not lost. If the flag was already set before the condition check, the loop exits. In practice, after receiving an interruption request, a task should release resources and terminate cooperatively; it should not continue indefinitely with the interrupt flag ignored.

Notes:

- **isInterrupted()** checks a Thread's flag without clearing it.
- **Thread.interrupted()** is a static method: it checks **and clears** the current thread's flag; do not use it interchangeably by mistake.
- **InterruptedException** is a checked exception. **Runnable.run()** does not declare any checked exceptions, so you must catch it inside run(), translate it appropriately, or restructure the method.
- When catching InterruptedException and unable to handle it completely, common practice is to restore the flag with **Thread.currentThread().interrupt()** and then exit or propagate handling to the appropriate layer. In methods that declare **throws InterruptedException**, you can let the exception propagate instead of swallowing it.

## 8. Errors in Threads and Program Termination

An uncaught exception in **run()** terminates that thread, and by default is reported via the thread/thread group's uncaught-exception handler. **join() does not automatically rethrow worker's exception on main**. If you need to record errors in a controlled manner, set a handler before starting:

~~~java
Thread worker = new Thread(() -> {
    throw new IllegalStateException("task failed");
}, "failing-worker");

worker.setUncaughtExceptionHandler((thread, error) ->
    System.err.println(thread.getName() + ": " + error.getMessage())
);
worker.start();
~~~

This snippet illustrates an error-handling callback and has no standalone main(). A handler is suitable for observation, but there is no default mechanism to transfer results or errors back to the thread creator. For tasks that need a **return value** or structured exception propagation, see **Callable/Future/ExecutorService** in the next section: **Runnable.run() returns void** and does not allow checked exceptions to escape directly.

Java has **user threads** (the default for normal threads) and **daemon threads**. The JVM can exit when only daemon threads remain; therefore, do not use daemon threads for work that must complete, such as writing critical data. You can call **setDaemon(true)** before **start()**, but calling it after the thread has started throws **IllegalThreadStateException**.

Do not call **Thread.stop()**, **suspend()**, or **resume()** to control the lifecycle: those legacy APIs are unsafe and have been removed or deprecated depending on the JDK version. Use a stop flag with proper memory guarantees, **interrupt()**, and controlled resource management.

## 9. When Should You Create a Thread Directly?

Creating a Thread directly is useful when learning fundamentals or running a short task with a small number of threads and a clear lifecycle. In applications with many tasks, **one Thread per request/task** can create too many platform threads, increasing stack overhead, context switching, and making shutdown hard to manage.

Higher-level Java APIs provide **ExecutorService** to manage task submission and execution, **Future** to observe results, and since **Java 21**, **virtual threads** (for example, **Thread.ofVirtual().start(task)**). These build upon the foundational concepts of **Thread** and **Runnable**, without changing the rules that tasks must be scheduled for execution and shared data must be protected. This lesson focuses on traditional Threads alongside Runnable.

## 10. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| **new Thread(task)** immediately creates a running thread | It only creates the object in the NEW state; **start()** is required. |
| Calling **run()** creates a new thread | **run()** runs on the calling thread; **start()** is what starts a new thread. |
| Each Runnable always corresponds to one thread | Runnable is just a task; the same Runnable can be passed to multiple Threads, or executed in other ways. |
| **start()** runs immediately and in the exact order called | The JVM/OS decides scheduling; there is no guarantee of execution order. |
| After **sleep(...)**, another thread is guaranteed to run or finish | sleep only pauses the current thread; it does not grant execution or ordering to other threads. |
| **join()** automatically makes all operations on shared data safe | join waits for completion and provides a happens-before relationship upon completion; concurrent operations still require synchronization. |
| **volatile int count** makes **count++** atomic | volatile does not turn a read-modify-write sequence into an atomic operation. |
| **interrupt()** kills the thread | interrupt only requests interruption; the task must handle the signal cooperatively. |
| An exception in a worker is automatically thrown in main | Errors are not automatically propagated through **join()**. |
| A TERMINATED thread can be **start()**ed again | Each Thread object can only be started once. |

## 11. Practice Checklist

1. Write tasks in **Runnable** (a class or lambda) when a specialized Thread subclass is not needed.
2. Create **new Thread(task, "meaningful-name")**, then call **start()**; do not call **run()** if you intend to run on another thread.
3. Clearly decide who is responsible for waiting, cancellation, monitoring errors, and releasing resources; use **join()** when you genuinely need to wait for completion.
4. Identify which mutable objects are shared across multiple threads. Use **synchronized**, **Lock**, **AtomicInteger**, or a non-shared-state design as needed.
5. When work can be cancelled, handle **interrupt()** and **InterruptedException** cooperatively; avoid busy-wait loops and avoid ignoring interrupts.
6. Do not write programs that rely on the order of log lines from multiple threads, **sleep()** durations, or **getState()** snapshots.

### Self-Check

**Q1.** If you write **Thread t = new Thread(task); t.run();**, is a new thread created?  
**Answer:** No. **task.run()** is executed on the thread that called **t.run()**.

**Q2.** If two Threads receive the same Runnable instance, do they share the same call stack?  
**Answer:** No. Each thread has its own stack, but both threads reference the **same Runnable object** and any shared objects that the task uses.

**Q3.** Can you call **start()** on the same Thread after **join()** finishes?  
**Answer:** No. Create a new Thread if you need to run the work again.

**Q4.** Why can the result of **count++** from two threads be wrong even when main calls **join()** on both?  
**Answer:** The increment is not atomic, so the two threads can overwrite each other's updates before finishing. **join()** does not fix lost updates; use synchronization or an atomic increment.

**Q5.** When a worker is interrupted while in **sleep()**, what should you keep in mind?  
**Answer:** **sleep()** throws **InterruptedException** and clears the interrupt status; the code needs to handle interruption cooperatively—typically restoring the flag if the exception cannot be propagated—and exit appropriately.
