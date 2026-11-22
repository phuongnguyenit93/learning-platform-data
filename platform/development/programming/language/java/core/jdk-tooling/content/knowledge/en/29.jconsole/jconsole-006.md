# Monitoring the Threads Tab in JConsole

**JConsole** is a graphical tool based on Java Management Extensions (JMX) used to monitor the activity and resources of a Java Virtual Machine (JVM). The **Threads** tab focuses on thread health: the number of live threads over time, the list of active threads, each thread's state, stack traces, and deadlock detection.

Basic workflow:

1. Launch JConsole from the JDK.
2. Connect to a local JVM or a remote JMX agent.
3. Open the Threads tab.
4. Observe the live/peak thread chart.
5. Filter the list by thread name.
6. Select a thread to inspect its state and stack trace.
7. Use Detect Deadlock when a deadlock is suspected.
8. Compare multiple points in time and use jstack/jcmd when deeper diagnostics are needed.

JConsole is an observation tool. It does not unblock threads, open latches, release locks, or resolve deadlocks on its own.

## 1. What Does the Threads Tab Display?

After connecting successfully, JConsole presents the Overview, Memory, Threads, Classes, VM, and MBeans tabs. Select **Threads** to view JVM thread activity.

According to the JDK 24 documentation, the Threads tab has three main areas:

- **Thread count chart:** shows the number of live threads over time along with the peak level.
- **Threads list:** lists the currently active threads.
- **Selected thread details:** displays the thread name, state, and stack trace.

In the thread list, enter a string in the Filter field to keep only threads whose names contain that string. Select a thread name to view its details in the adjacent pane.

The chart in JDK 24 has two lines:

- Red line: Peak number of threads, the highest number of live threads reached since the JVM started.
- Blue line: Number of live threads, the number of threads currently alive at each point in time.

Daemon and total started metrics can be viewed in VM Summary or via the Threading MXBean on the MBeans tab.

## 2. Understanding Thread Metrics

These metrics help distinguish between the current thread count, the highest recorded count, and the total number of threads created.

| Metric | Meaning |
|---|---|
| Live threads | Number of daemon and non-daemon threads currently alive |
| Peak | Highest number of live threads since the JVM started or since the last peak reset |
| Daemon threads | Number of daemon threads currently alive |
| Total threads started | Total number of threads started since the JVM started, including terminated threads |

Example:

~~~text
Live threads:          24
Peak:                  41
Daemon threads:        18
Total threads started: 126
~~~

Interpretation:

- The JVM currently has 24 live threads.
- Previously, the JVM reached 41 live threads.
- Out of the 24 current threads, 18 are daemon threads.
- A total of 126 threads have been started, including threads that have already terminated.

Total threads started typically does not decrease because terminating a thread does not decrement the cumulative counter. Live threads can increase or decrease as threads are created and terminated.

### Live threads

Live threads is the number of threads currently existing in the JVM, including both daemon and non-daemon threads. A thread can be in RUNNABLE, BLOCKED, WAITING, or TIMED_WAITING and still count as live.

Do not equate live threads with threads actively using CPU. A worker waiting on a queue is still a live thread.

### Peak

Peak helps identify thread load spikes. If live threads are currently low while peak is high, the application may have created a large burst of threads that later terminated.

Peak alone does not tell you the cause. Correlate it with request spikes, batch jobs, deployments, retries, or background load.

### Daemon threads

A daemon thread is a background thread that does not keep the JVM alive once all non-daemon threads have finished. Common examples include certain runtime, scheduler, or platform threads.

Daemon does not mean unimportant. A daemon thread can still consume CPU, hold resources, wait on I/O, or encounter a deadlock. When the JVM exits, daemon threads may be stopped as part of the shutdown process.

### Total threads started

This metric includes terminated threads. If total started rises rapidly while live threads remain stable, the application may be creating and terminating many short-lived threads. This can be an intentional design or a sign of overly frequent thread creation.

If both live threads and total started rise continuously, check for thread leaks, unbounded executors, or uncontrolled thread creation.

## 3. Filtering and Selecting Threads

The Threads list can be long because the JVM runs many runtime, GC, compiler, cleaner, JMX, and application threads.

How to filter:

1. Open the Threads tab.
2. Enter part of a thread name in the Filter field.
3. The list narrows to threads whose names contain the entered string.
4. Select a thread to view its details.
5. Clear the filter to return to the full list.

Example thread names:

~~~text
http-nio-8080-exec-1
http-nio-8080-exec-2
pool-3-thread-1
scheduler-1
demo-WAITING-latch
demo-BLOCKED-monitor
~~~

Enter `http-nio-8080` to focus on web server workers; enter `pool-3` to inspect an executor group; enter `demo-` to find threads from the lab.

Giving threads meaningful names in your application makes observation and investigation much easier. With `ExecutorService`, you can use a custom `ThreadFactory` to name threads by function or worker group.

### Selected thread details

When you select a thread, JConsole displays:

- Thread name.
- Thread state.
- Stack trace at the time of sampling.

The stack trace shows which method the thread is executing or waiting in. Look for the first frame belonging to an application package to locate the relevant business code.

Example:

~~~text
Name: demo-WAITING-latch
State: WAITING

Stack trace:
    at jdk.internal.misc.Unsafe.park(...)
    at java.util.concurrent.locks.LockSupport.park(...)
    at java.util.concurrent.CountDownLatch.await(...)
    at com.example.JConsoleThreadTabDemo.await(...)
~~~

Interpretation: the thread is waiting on a `CountDownLatch`. Find where `countDown()` is called on that latch to determine whether the wake-up condition is ever met.

A stack trace is a snapshot. If you need to save a full thread dump or analyze many threads at once, use `jstack` or `jcmd Thread.print`.

## 4. Reading Thread States

Java defines six states in `Thread.State`:

| State | Meaning |
|---|---|
| NEW | Thread has been created but not yet started |
| RUNNABLE | Thread is running or ready to be scheduled by the OS scheduler |
| BLOCKED | Thread is waiting to acquire an intrinsic monitor lock |
| WAITING | Thread is waiting indefinitely for another action without a timeout |
| TIMED_WAITING | Thread is waiting for a bounded period of time |
| TERMINATED | Thread has finished execution |

JConsole lists active threads, so `NEW` and `TERMINATED` generally do not appear in the live thread list.

### RUNNABLE

`RUNNABLE` does not guarantee the thread is actively executing on a CPU core at the exact moment of observation. The thread may be scheduled on a CPU, waiting for CPU time, or executing a native operation.

If a thread stays `RUNNABLE` for a long time and its stack trace does not change, check for CPU-bound loops, large data processing, or native calls. You can cross-check CPU time via the Threading MXBean.

### BLOCKED

`BLOCKED` means the thread is waiting to acquire an intrinsic monitor to enter a `synchronized` block or `synchronized` method.

Example:

~~~java
synchronized (sharedLock) {
    updateState();
}
~~~

If another thread holds `sharedLock`, this thread may be in `BLOCKED`. Inspect the stack trace and lock information via Threading MXBean or `jstack -l` to identify the owner.

### WAITING

`WAITING` is an indefinite wait state, commonly caused by:

- `Object.wait()` without a timeout.
- `Thread.join()` without a timeout.
- `CountDownLatch.await()`.
- `Condition.await()`.
- `LockSupport.park()`.
- A blocking queue or synchronizer waiting for data or a signal.

`WAITING` does not automatically mean the thread is hung. A worker waiting on an empty queue may be operating normally.

### TIMED_WAITING

`TIMED_WAITING` is waiting with a timeout, commonly caused by:

- `Thread.sleep()`.
- `Object.wait(timeout)`.
- `Thread.join(timeout)`.
- `LockSupport.parkNanos()`.
- Synchronization operations with a timeout.

A thread sleeping between retries can be in `TIMED_WAITING`. Check the timeout, backoff strategy, and stack trace before concluding there is an issue.

### Why not look at state alone?

Many threads in `WAITING` can be completely normal in a thread pool. Conversely, a single `BLOCKED` thread can bottleneck all requests if it holds a critical lock.

Combine state, thread name, stack trace, lock owner, CPU time, and trends across multiple points in time.

## 5. Detecting Deadlocks with Detect Deadlock

A deadlock occurs when threads hold resources that other threads in a cycle need, preventing any thread in the cycle from making progress.

Example:

- Thread A holds lock X and waits for lock Y.
- Thread B holds lock Y and waits for lock X.
- A cannot acquire Y until B releases Y.
- B cannot release Y because it is waiting for A to release X.

In the Threads tab, click **Detect Deadlock**. If a deadlock is detected, JConsole opens a new tab displaying the threads involved in the deadlock cycle.

JConsole detects cycles involving:

- Object monitor locks, such as `synchronized`.
- Ownable synchronizers, such as locks based on `AbstractQueuedSynchronizer` like `ReentrantLock`.

Detection capabilities depend on the JVM and Threading MXBean support.

### How to investigate the results

1. Click Detect Deadlock.
2. Open the newly created deadlock tab.
3. Select each thread in the cycle.
4. Read its state and stack trace.
5. Identify the lock the thread is waiting for.
6. Identify the thread holding that lock.
7. Trace the entire cycle to find the lock acquisition order.
8. Cross-reference with the source code and synchronization design.

Detect Deadlock only detects and presents evidence. JConsole does not release locks or fix code automatically.

### Deadlock vs. long-waiting threads

A thread waiting on a `CountDownLatch` where nothing ever calls `countDown()` may be logically stuck, but it is not necessarily a monitor deadlock. Similarly, a thread waiting for a database or HTTP response may wait for a long time without forming a lock cycle.

If Detect Deadlock finds no cycles, the application can still suffer from starvation, thread pool exhaustion, I/O hangs, or missing synchronization signals.

## 6. Threading MXBean in the MBeans Tab

JConsole is built on JMX. Much of the thread information is exposed by the Threading MXBean, which has the ObjectName:

~~~text
java.lang:type=Threading
~~~

Open the MBeans tab, locate `java.lang`, and select `Threading`. Depending on the JConsole version, the MBeans tree may be grouped by object name.

Useful attributes:

| Attribute | Meaning |
|---|---|
| ThreadCount | Current number of live threads |
| PeakThreadCount | Peak number of live threads |
| DaemonThreadCount | Current number of daemon threads |
| TotalStartedThreadCount | Total number of threads started |
| CurrentThreadCpuTime | CPU time of the current thread |
| CurrentThreadUserTime | User-mode CPU time of the current thread |
| ThreadContentionMonitoringEnabled | Whether contention monitoring is enabled |

Key operations:

| Operation | Function |
|---|---|
| getThreadInfo | Retrieves thread name, state, stack trace, and lock info |
| getThreadCpuTime | Retrieves CPU time for a specific thread |
| findMonitorDeadlockedThreads | Finds deadlocks involving object monitors |
| findDeadlockedThreads | Finds deadlocks involving monitors and ownable synchronizers |
| resetPeakThreadCount | Resets the peak thread count |

Not all attributes or operations are available in every JVM. Check `MBeanInfo` and the actual results from the connected runtime.

### CPU time vs. elapsed time

CPU time is the amount of CPU time the thread has consumed. Elapsed time is the actual wall-clock time that has passed.

A thread waiting on the network for 30 seconds may have a large elapsed time but very little CPU time. A thread running a computation loop may show rapidly increasing CPU time.

If `ThreadMXBean` does not support CPU time measurement or it is not enabled, the value may be unavailable. Do not infer CPU usage from thread state alone.

## 7. Comparing Multiple Snapshots

The Threads tab updates over time. A single glance only reflects the state at one moment.

During investigation:

1. Observe the current list and chart.
2. Note the name, state, and stack trace of threads of interest.
3. Wait an interval appropriate for the workload.
4. Observe the same threads again.
5. Compare states and stack traces.
6. If a thread is consistently waiting on the same condition or lock, find the producer or lock owner.
7. If the thread moves across different stack frames, it may still be making progress.

Example:

| Snapshot | Thread | State | Stack |
|---|---|---|---|
| T1 | worker-1 | WAITING | BlockingQueue.take |
| T2 | worker-1 | WAITING | BlockingQueue.take |
| T3 | worker-1 | RUNNABLE | OrderService.process |

The worker may have received work between T2 and T3. Seeing `WAITING` in two snapshots is not enough to conclude a thread is stuck.

### Signs of a thread leak

Signs worth investigating:

- Live threads increase continuously and do not drop after load subsides.
- Peak increases across successive load bursts.
- Many threads share the same naming group and never terminate.
- A thread pool has more workers than expected by its configuration.
- Many threads wait on the same service or lock.
- Total started grows very rapidly because a new thread is created per request.

Correlate thread counts with request rate, queue depth, executor configuration, deployments, and workload. Do not assume a leak just because live threads are high; a server may be configured to maintain a large worker pool.

## 8. Saving Chart Data

JConsole allows saving chart data as CSV:

1. Right-click on the chart.
2. Select Save data as...
3. Choose the location and CSV filename.
4. Open the CSV in a spreadsheet or analysis tool.

The CSV contains a timestamp column and one or more value columns. It can be used to compare live threads and peak counts over a period.

When saving data, record the timestamp, JVM, environment, application load, and observation window to avoid interpreting the chart out of context.

## 9. Connecting JConsole to a Local JVM

JConsole is located in the JDK's `bin` directory. Check the executable:

Windows PowerShell:

~~~powershell
Get-Command jconsole
where.exe jconsole
~~~

Linux/macOS:

~~~bash
command -v jconsole
~~~

Launch the UI:

~~~bash
jconsole
~~~

JConsole displays a list of local JVMs it can access. Select the JVM to monitor and click Connect.

If you already know the PID:

~~~bash
jconsole 12345
~~~

Replace `12345` with the actual PID.

### Local monitoring requirements

According to the JDK 24 documentation:

- JConsole and the target JVM must run under the same user ID.
- Local connections use the management/Attach mechanism and OS file permissions.
- A JVM can be attached to dynamically enable the management agent if the JVM supports it.
- A JVM that is not attachable and does not have the management agent enabled may not be connectable.
- A JVM launched with `DisableAttachMechanism` can block attach-based local connections.

If the JVM does not appear in the list, check the PID, user, JDK, container namespace, and attachability.

### Connecting by PID does not imply root privileges

Running under the operational account that owns the JVM is the standard approach. Do not automatically run JConsole as Administrator/root to work around connection errors. Verify the process permission policy and environment first.

## 10. Connecting JConsole to a Remote JVM via JMX

To monitor a JVM on another machine, the application must enable the JMX remote agent and open the configured management port.

Example configuration with explicit authentication and SSL:

~~~bash
java \
    -Dcom.sun.management.jmxremote.port=9010 \
    -Dcom.sun.management.jmxremote.rmi.port=9010 \
    -Dcom.sun.management.jmxremote.authenticate=true \
    -Dcom.sun.management.jmxremote.ssl=true \
    -jar app.jar
~~~

Then on the administration machine:

~~~bash
jconsole app-server.example.com:9010
~~~

If the JMX agent requires authentication, JConsole will prompt for a username and password in the connection dialog.

Configure the password/access files, TLS keystore/truststore, and firewall according to the JDK JMX documentation. Allow connections only from the management network or authorized hosts.

Do not expose unauthenticated remote JMX to the Internet. Anyone with JMX access can read sensitive management data and invoke operations on MBeans. Protect the JMX port like a production admin interface.

### Differences between Remote JMX and Local Attach

| Local | Remote |
|---|---|
| Connects to a JVM on the same machine | Connects through the JMX agent |
| Relies on local/Attach permissions | Relies on JMX connector, network, authentication, and TLS |
| Usually requires the same user ID | Uses credentials configured for JMX |
| Useful for development | Better suited to isolate the tool from production JVMs |

## 11. Can JConsole Affect the Application?

JConsole continuously queries MBeans to update charts and details. Monitoring introduces CPU, thread, and network overhead.

Oracle notes that local monitoring is useful for development/prototyping but is not recommended in production because JConsole itself consumes significant resources. Remote monitoring helps offload the UI resources from the machine running the application.

Best practices:

- Open only the tabs and charts you need.
- Avoid connecting too many JConsole instances to the same JVM.
- Do not run heavy diagnostic operations continuously.
- Choose an observation window appropriate for the incident.
- Use remote monitoring from an admin machine when appropriate.
- Compare metrics before and during monitoring to identify overhead.

JConsole is a live observation tool, not a long-term metrics system or an alerting replacement for a monitoring platform.

## 12. Troubleshooting the Threads Tab

### Cannot connect to local JVM

Check:

- Do JConsole and the JVM share the same user ID?
- Does the PID still exist?
- Does the JVM support Attach?
- Was `DisableAttachMechanism` used?
- Is JConsole from a compatible JDK environment?
- Is the JVM running inside a different container or process namespace?

### JVM appears grayed out or cannot be selected

The JVM may not have the management agent enabled and may not support dynamic attach. Restart the application with appropriate management agent settings or use secured remote JMX.

### Thread list does not show the expected thread

The thread may have terminated, its name may differ from expected, or the filter may be hiding it. Clear the Filter and check again. Verify further with `jstack` or `jcmd Thread.print`.

### Thread state does not appear to change

The thread may be waiting on a long-lived condition, or the chart may not have enough observation time yet. Select the thread, inspect the stack trace, and compare multiple snapshots. Check producers, queues, latches, futures, timeouts, or lock owners.

### Detect Deadlock finds nothing

No detected deadlock cycle does not mean the application is not hung. The cause may be an I/O hang, starvation, thread pool exhaustion, a missing signal, or a logical deadlock outside the locks the JVM can detect.

### Remote JMX connection refused

Check the host/port, whether the JMX agent is enabled, the RMI port, firewalls, routing, credentials, and TLS certificates. Do not disable authentication/SSL for a quick test on an untrusted network.

### Stack trace is not deep enough

Use `jstack` or `jcmd Thread.print` to capture a more complete thread dump. Target the same PID and record the dump timestamp to correlate with the JConsole capture.

## 13. Combining the Threads Tab with jstack and jcmd

JConsole is well suited for observing trends and selecting individual threads. When you need to preserve full evidence, use command-line tools.

List JVMs:

~~~bash
jcmd -l
~~~

Print a thread dump:

~~~bash
jcmd 12345 Thread.print
~~~

Include lock information:

~~~bash
jcmd 12345 Thread.print -l
~~~

Or:

~~~bash
jstack -l 12345
~~~

Replace `12345` with the actual PID.

| Tool | Purpose |
|---|---|
| JConsole Threads | Monitor live/peak, filter threads, inspect state and stack traces |
| Detect Deadlock | Detect deadlock cycles |
| Threading MXBean | Read thread metrics, stack info, CPU time, and deadlock operations |
| jstack -l | Capture a thread dump with lock information |
| jcmd Thread.print -l | Capture a thread dump using diagnostic commands |

JConsole does not replace thread dumps for investigations that require archiving, comparison, or offline analysis.

## 14. Complete Java 17+ Example: Creating States to Observe

The following program creates threads with names that are easy to filter in JConsole:

- `demo-WAITING-latch`: waits on a `CountDownLatch` that is never released.
- `demo-TIMED_WAITING-sleep`: sleeps with a timeout.
- `demo-monitor-owner`: holds a `synchronized` monitor.
- `demo-BLOCKED-monitor`: waits on the monitor held by the owner.
- `demo-daemon-WAITING`: daemon thread waiting on a latch.
- `demo-short-lived`: thread that finishes quickly to increment total threads started.

### JConsoleThreadTabDemo.java

~~~java
package com.example;

import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;
import java.util.concurrent.CountDownLatch;

public final class JConsoleThreadTabDemo {
    private static final Object LOCK = new Object();
    private static final CountDownLatch OWNER_HAS_LOCK = new CountDownLatch(1);
    private static final CountDownLatch NEVER_RELEASED = new CountDownLatch(1);

    private JConsoleThreadTabDemo() {
    }

    public static void main(String[] args) throws Exception {
        Thread waiting = new Thread(
                () -> await(NEVER_RELEASED), "demo-WAITING-latch");

        Thread timed = new Thread(
                () -> sleepFor(120_000), "demo-TIMED_WAITING-sleep");

        Thread owner = new Thread(() -> {
            synchronized (LOCK) {
                OWNER_HAS_LOCK.countDown();
                sleepFor(120_000);
            }
        }, "demo-monitor-owner");

        Thread blocked = new Thread(() -> {
            await(OWNER_HAS_LOCK);
            synchronized (LOCK) {
                System.out.println("demo-BLOCKED acquired monitor");
            }
        }, "demo-BLOCKED-monitor");

        Thread daemon = new Thread(
                () -> await(NEVER_RELEASED), "demo-daemon-WAITING");
        daemon.setDaemon(true);

        waiting.start();
        timed.start();
        owner.start();
        blocked.start();
        daemon.start();

        OWNER_HAS_LOCK.await();
        Thread.sleep(500);

        Thread shortLived = new Thread(() -> { }, "demo-short-lived");
        shortLived.start();
        shortLived.join();

        ThreadMXBean bean = ManagementFactory.getThreadMXBean();

        System.out.println(
                "JConsoleThreadTabDemo ready; pid=" + ProcessHandle.current().pid());
        System.out.println("Live threads=" + bean.getThreadCount());
        System.out.println("Daemon threads=" + bean.getDaemonThreadCount());
        System.out.println("Peak threads=" + bean.getPeakThreadCount());
        System.out.println(
                "Total threads started=" + bean.getTotalStartedThreadCount());
        System.out.println("demo-WAITING-latch=" + waiting.getState());
        System.out.println("demo-TIMED_WAITING-sleep=" + timed.getState());
        System.out.println("demo-BLOCKED-monitor=" + blocked.getState());
        System.out.println("demo-daemon-WAITING daemon=" + daemon.isDaemon());

        Thread.sleep(120_000);
    }

    private static void await(CountDownLatch latch) {
        try {
            latch.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    private static void sleepFor(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
~~~

### Compiling

From the project root directory:

~~~bash
mkdir -p build/classes

javac --release 17 \
    -d build/classes \
    src/com/example/JConsoleThreadTabDemo.java
~~~

### Running the application

~~~bash
java -cp build/classes com.example.JConsoleThreadTabDemo
~~~

Sample output observed on JDK 24.0.2:

~~~text
JConsoleThreadTabDemo ready; pid=37548
Live threads=12
Daemon threads=7
Peak threads=13
Total threads started=13
demo-WAITING-latch=WAITING
demo-TIMED_WAITING-sleep=TIMED_WAITING
demo-BLOCKED-monitor=BLOCKED
demo-daemon-WAITING daemon=true
~~~

The PID and counters may differ on other machines or after JConsole connects, because the JVM, GC, and management agent can create additional threads.

### Opening JConsole

In a second terminal under the same OS user account:

~~~bash
jconsole 37548
~~~

Replace `37548` with the PID printed by the program.

Select the Threads tab. In Filter, enter `demo-` to view only the lab threads. Select each thread and inspect its state and stack trace.

Observations:

- `demo-WAITING-latch` is in `WAITING`, with a stack trace passing through `CountDownLatch.await`.
- `demo-TIMED_WAITING-sleep` is in `TIMED_WAITING`, with a stack trace passing through `Thread.sleep`.
- `demo-BLOCKED-monitor` is in `BLOCKED`, with a stack trace waiting to enter the `synchronized` block.
- `demo-monitor-owner` holds the monitor and is sleeping.
- `demo-daemon-WAITING` is a daemon thread.

If you select the `BLOCKED` thread and inspect lock details via MBeans or a thread dump, the object monitor it is waiting on matches the monitor held by `demo-monitor-owner`.

The program exits automatically after about two minutes. You can press `Ctrl+C` in the terminal running the application to stop the lab early.

## 15. Deadlock Example for Testing Detect Deadlock

The following code creates two threads that acquire two monitors in opposite orders.

~~~java
package com.example;

public final class JConsoleDeadlockDemo {
    private static final Object A = new Object();
    private static final Object B = new Object();

    public static void main(String[] args) throws Exception {
        Thread first = new Thread(() -> {
            synchronized (A) {
                pause();
                synchronized (B) {
                    System.out.println("first acquired both");
                }
            }
        }, "demo-deadlock-A-then-B");

        Thread second = new Thread(() -> {
            synchronized (B) {
                pause();
                synchronized (A) {
                    System.out.println("second acquired both");
                }
            }
        }, "demo-deadlock-B-then-A");

        first.start();
        second.start();
        Thread.sleep(120_000);
    }

    private static void pause() {
        try {
            Thread.sleep(500);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 -d build/classes \
    src/com/example/JConsoleDeadlockDemo.java

java -cp build/classes com.example.JConsoleDeadlockDemo
~~~

Connect JConsole to the program's PID, open Threads, and click Detect Deadlock. JConsole will display the deadlock cycle if the JVM detects it.

This example intentionally creates a deadlock and does not terminate on its own. Run it only in a lab environment, never in a production application.

The typical fix is to enforce a consistent lock acquisition order, such as having every thread always acquire A before B. You can also reduce the number of locks, avoid nested locks, or use appropriate concurrency utilities.

## 16. Threads Tab Investigation Checklist

- [ ] Connected to the right JVM and recorded the PID.
- [ ] Confirmed local/remote environment and access identity.
- [ ] Observed live threads and peak over time.
- [ ] Distinguished live, daemon, peak, and total started counts.
- [ ] Filtered the thread group by name.
- [ ] Selected threads of interest and read their states.
- [ ] Identified the first frame belonging to application code.
- [ ] Distinguished `BLOCKED`, `WAITING`, and `TIMED_WAITING`.
- [ ] Identified the lock owner when monitor contention occurred.
- [ ] Ran Detect Deadlock when a deadlock was suspected.
- [ ] Compared multiple snapshots before concluding a thread is stuck.
- [ ] Checked CPU time or captured a thread dump when needed.
- [ ] Saved CSV/thread dumps if evidence was required.
- [ ] Protected sensitive information in stack traces and JMX credentials.

## 17. Operation Summary

~~~text
jconsole
jconsole <pid>
jconsole hostName:portNum
~~~

In JConsole:

1. Connect to a local or remote JVM.
2. Select Threads.
3. Monitor the live and peak lines.
4. Filter the list by thread name.
5. Select a thread to read its state and stack trace.
6. Click Detect Deadlock when checking for deadlocks.
7. Open MBeans > Threading for advanced operations and attributes.
8. Use `jstack`/`jcmd` to capture full thread dumps when needed.

The Threads tab makes live concurrency behavior inside the JVM visible. Read the chart alongside the thread list, understand what each state means, and use stack traces to locate where code is waiting. Combining Detect Deadlock, Threading MXBean, and multiple snapshots over time helps distinguish normal thread load, thread leaks, contention, and deadlocks.

## References

- [Using JConsole — Java SE 24](https://docs.oracle.com/en/java/javase/24/management/using-jconsole.html)
- [The jconsole Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jconsole.html)
- [ThreadMXBean API — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/java.management/java/lang/management/ThreadMXBean.html)
- [ThreadInfo API — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/java.management/java/lang/management/ThreadInfo.html)
- [Thread.State API — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/Thread.State.html)
- [Remote Monitoring and Management — Java SE 24](https://docs.oracle.com/en/java/javase/24/management/monitoring-and-management-using-jmx-technology.html)
