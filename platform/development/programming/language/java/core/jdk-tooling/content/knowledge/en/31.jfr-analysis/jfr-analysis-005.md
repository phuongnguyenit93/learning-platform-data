# Analyzing Lock Contention with Java Flight Recorder

**Lock contention** occurs when multiple threads need the same synchronized resource at the same time, but only one thread is allowed to pass through the lock-protected region at any given moment. The remaining threads must wait for the lock to be released. If wait times are long or occur frequently, throughput drops, latency increases, and requests can queue up even when CPU utilization is not high.

**Java Flight Recorder (JFR)** helps identify where and for how long threads are blocked or parked while waiting on synchronization. A recording can show which thread is waiting, what type of monitor/lock is involved, which thread previously owned the monitor, and the stack trace at the point where the thread had to wait. Combining this data with JDK Mission Control (JMC), thread dumps, and the actual workload helps pinpoint code that holds locks for too long.

Lock contention is different from a deadlock. With normal contention, the thread holding the lock eventually releases it and waiting threads resume execution. A deadlock is a state where threads wait on each other in a cycle and none of them can make progress. JFR helps analyze wait durations; thread dumps are critical data when a deadlock is suspected.

## 1. How does lock contention affect an application?

A critical section protected by a lock ensures that shared operations do not run concurrently in unintended ways. However, if many requests go through the same lock, they must queue up.

Example:

~~~java
public synchronized void updateSharedState() {
    loadDataFromRemoteService();
    updateCache();
    writeAuditLog();
}
~~~

The method above holds the monitor for the entire duration of the remote service call, cache update, and log write. If the I/O operation takes a long time, other threads calling the same method must wait even though the actual data update only takes a few milliseconds.

Common symptoms:

- Request latency increases as traffic grows.
- Throughput does not increase even after adding more threads or workers.
- Many threads are in the BLOCKED or PARKED state.
- CPU usage may be low because threads are waiting instead of executing code.
- Certain locks or monitor classes appear repeatedly in the recording.
- A group of requests slows down at the same time because they are waiting on the same shared resource.

Do not conclude there is contention solely because many threads are in the WAITING/BLOCKED state. You need to determine what the threads are waiting for, whether the wait time is significant, and whether that waiting affects critical requests or workloads.

## 2. JFR events to distinguish

JFR provides several synchronization-related events. Choosing the right event helps avoid confusing monitor entry blocking, condition waits, and thread parking.

| Event | Meaning | When to inspect |
|---|---|---|
| **jdk.JavaMonitorEnter** | Thread is blocked trying to enter a Java monitor, typically a synchronized block/method | Finding threads waiting to acquire an intrinsic monitor |
| **jdk.JavaMonitorWait** | Thread is inside an Object.wait() call, waiting for notify or timeout; Thread.join() also uses monitor wait | Analyzing condition waits, join, or wait/notify |
| **jdk.ThreadPark** | Thread is parked via LockSupport.park() | Analyzing ReentrantLock, AQS, semaphores, futures, and other park-based mechanisms |
| **jdk.ThreadSleep** | Thread intentionally sleeps for a duration | Distinguishing intentional sleep from lock waits |
| **jdk.SocketRead / jdk.FileRead** | Thread is waiting on an I/O operation | Checking for network or file bottlenecks instead of locks |

Not all events have the same meaning. Always inspect duration, thread, class, and stack trace before drawing conclusions.

### 2.1. JavaMonitorEnter: waiting on a synchronized monitor

**jdk.JavaMonitorEnter** has the label **Java Monitor Blocked** in JFR. This event records the time a thread is blocked trying to acquire a monitor currently owned by another thread.

Key fields:

- **duration:** time the thread was blocked before entering the monitor.
- **monitorClass:** class of the object used as the monitor.
- **previousOwner:** the thread that owned the monitor immediately before the waiting thread acquired it.
- **eventThread:** the thread experiencing contention.
- **stackTrace:** stack trace at the point where the thread attempted to enter the monitor.
- **address:** monitor address, useful for grouping events related to the same lock instance within a recording.

The stack trace in JavaMonitorEnter is the location of the **waiting thread**. The previousOwner field indicates the thread that previously held the monitor; to see what the owner was doing while holding the lock, correlate with the thread timeline, stack traces in other events, or a thread dump.

### 2.2. JavaMonitorWait: waiting on Object.wait or Thread.join

**jdk.JavaMonitorWait** is the event for waiting on a monitor. When calling **Object.wait()**, the thread must own the monitor; the JVM temporarily releases the monitor while waiting for a notify or timeout, and then the thread must reacquire the monitor before continuing.

The event may contain:

- **duration:** wait time.
- **monitorClass:** class of the object being waited on.
- **notifier:** the thread that sent the notify, if identifiable.
- **timeout** and **timedOut:** maximum wait time and whether the wait timed out.
- **eventThread** and **stackTrace:** the thread and location performing the wait operation.

Do not treat JavaMonitorWait as a substitute for JavaMonitorEnter. A thread blocked entering synchronized is represented by JavaMonitorEnter; a thread explicitly calling wait() is represented by JavaMonitorWait. For example, Thread.join() can also appear as JavaMonitorWait because its implementation uses monitor wait.

### 2.3. ThreadPark: waiting via LockSupport and AQS

Many synchronization APIs do not use intrinsic monitors directly. ReentrantLock, Semaphore, and many components built on AbstractQueuedSynchronizer can park threads using LockSupport.park().

**jdk.ThreadPark** typically has the following fields:

- **duration:** time the thread was parked.
- **parkedClass:** class of the object on which the thread is parked.
- **eventThread:** the parked thread.
- **stackTrace:** call path leading to the park operation.

Not every ThreadPark is lock contention. A thread can park while waiting for work, a future, a queue, or while idle in a pool. Read parkedClass and the stack trace to determine whether the thread is waiting on a ReentrantLock, queue, scheduler, or another mechanism.

## 3. Reading events to identify the contending lock

When you find a notable event, examine the following fields together:

1. **Duration:** wait time. An event lasting 150 ms can significantly impact a request if it occurs on the main processing path.
2. **Event thread:** the thread being blocked or parked.
3. **Monitor class / parked class:** the object type or synchronization mechanism involved.
4. **Previous owner / notifier:** the thread that previously owned the monitor or sent the notify, if provided by the event.
5. **Stack trace:** the code location attempting to acquire the lock or perform wait/park.
6. **Start time:** when it occurred, to correlate with latency, throughput, logs, and workload.

Example event:

~~~text
jdk.JavaMonitorEnter {
  startTime = 19:48:02.375
  duration = 102 ms
  monitorClass = java.lang.Object
  previousOwner = "monitor-owner-5" (javaThreadId = 59)
  eventThread = "monitor-waiter-5" (javaThreadId = 60)
  stackTrace = [
    LockProbe.lambda$monitorContention$1(CountDownLatch) line: 28
    java.lang.Thread.run() line: 1447
  ]
}
~~~

This is illustrative output from a test on JDK 24.0.2. Thread monitor-waiter-5 waited about 102 ms to acquire the monitor held by monitor-owner-5. The stack trace points to where the waiter tried to enter the synchronized block.

Do not look only at the single event with the longest duration. Also check the occurrence count and total wait time. A lock with thousands of 10–20 ms waits can have a larger overall impact than a single 200 ms wait. When comparing, keep in mind that JFR may omit events shorter than the configured threshold.

## 4. Starting a recording to analyze lock contention

Find the JVM PID:

~~~sh
jcmd -l
~~~

View the recording options supported by the target JVM:

~~~sh
jcmd <pid> help JFR.start
~~~

Start a short recording with the profile configuration and lower thresholds for synchronization events:

~~~sh
jcmd <pid> JFR.start name=LockStudy settings=profile disk=true maxage=2m maxsize=64m jdk.JavaMonitorEnter#threshold=5ms jdk.JavaMonitorEnter#stackTrace=true jdk.JavaMonitorWait#threshold=5ms jdk.JavaMonitorWait#stackTrace=true jdk.ThreadPark#threshold=5ms jdk.ThreadPark#stackTrace=true
~~~

Options explained:

- **name=LockStudy:** names the recording for use in check, dump, and stop commands.
- **settings=profile:** uses the profile template to collect detailed analysis data.
- **disk=true:** enables writing data to disk during the recording.
- **maxage=2m:** limits the age of data kept in the disk repository.
- **maxsize=64m:** limits the size of data kept in the disk repository.
- **#threshold=5ms:** records events with a duration of 5 ms or longer.
- **#stackTrace=true:** requests stack trace capture for the corresponding event.

In JDK 24, many Java Application duration events are only recorded by default when their duration exceeds 20 ms. Specific templates may set different thresholds; check the active configuration. Lowering the threshold captures more short waits, but also makes the recording larger and can increase overhead. Only lower thresholds for short recordings during deep investigation, while monitoring application performance.

Check the recording:

~~~sh
jcmd <pid> JFR.check name=LockStudy
~~~

Dump the current data to a file:

~~~sh
jcmd <pid> JFR.dump name=LockStudy filename=lock-contention.jfr
~~~

The dump command creates a file for analysis; the recording can continue running. When you no longer need to collect data, stop the recording:

~~~sh
jcmd <pid> JFR.stop name=LockStudy
~~~

If you want it to end automatically after a set period, you can add **duration=30s** to the JFR.start command. Check the target JVM's help to confirm available options.

## 5. Analyzing the file with the jfr CLI

Start with a summary:

~~~sh
jfr summary lock-contention.jfr
~~~

The summary shows the recording duration and event counts by type. Check whether the file contains jdk.JavaMonitorEnter, jdk.JavaMonitorWait, and jdk.ThreadPark.

Print synchronization events:

~~~sh
jfr print --events jdk.JavaMonitorEnter,jdk.JavaMonitorWait,jdk.ThreadPark lock-contention.jfr
~~~

Print only monitor contention:

~~~sh
jfr print --events jdk.JavaMonitorEnter lock-contention.jfr
~~~

Print only thread parks:

~~~sh
jfr print --events jdk.ThreadPark lock-contention.jfr
~~~

When reading the output:

- Look for events with high duration.
- Group events by monitorClass, parkedClass, or monitor address.
- Check which threads are frequently blocked.
- Read stack traces to find the methods and call paths causing contention.
- Check previousOwner to find which thread held the monitor earlier.
- Check timestamps to correlate with slow requests, batch jobs, or traffic spikes.

A ThreadPark example for ReentrantLock might look like this:

~~~text
jdk.ThreadPark {
  startTime = 19:45:56.025
  duration = 121 ms
  parkedClass = java.util.concurrent.locks.ReentrantLock$NonfairSync
  eventThread = "reentrant-waiter-3"
  stackTrace = [
    jdk.internal.misc.Unsafe.park(boolean, long)
    java.util.concurrent.locks.LockSupport.park(Object)
    java.util.concurrent.locks.AbstractQueuedSynchronizer.acquire(...)
    java.util.concurrent.locks.ReentrantLock$Sync.lock()
  ]
}
~~~

The stack trace shows the thread parking in the ReentrantLock call path. Follow the frames up into application code to find where lock() is called and understand why the lock is held for so long.

## 6. Analyzing with JDK Mission Control

JDK Mission Control (JMC) provides a graphical interface to inspect recordings. Open lock-contention.jfr and focus on the following areas:

| Area | How to use |
|---|---|
| Automated Analysis Results | View warnings or contention signs detected by JMC |
| Threads / Contention | View blocked threads, involved locks, and stack traces |
| Lock Instances | View lock instances appearing in contention and drill down into threads/stacks |
| Latencies | View latency-causing event types such as monitor blocked, monitor wait, or thread park |
| Thread Timeline | Correlate intervals when threads are running, waiting, parked, or blocked |

In Contention or Lock Instances, prioritize locks with high total blocked time, high contention counts, or those appearing on threads handling critical requests. When selecting a lock or thread, inspect the stack trace to find the waiting method.

To understand what the lock-owning thread was doing, select the owner thread on the timeline and correlate other events/stack traces during the same time window. The JavaMonitorEnter stack trace is the waiter's stack; it does not automatically replace the owner's stack.

## 7. Finding the root cause from stack traces

Once you identify a notable lock, trace up from the application frames along the call path to find the code holding the lock. Common patterns include:

### 7.1. Overly long critical sections

A synchronized method performs heavy computation or iterates over a large collection. Every thread needing the same monitor must wait until the entire processing finishes.

How to fix:

- Keep only the operations that actually require protection inside the critical section.
- Compute independent data before acquiring the lock.
- Prepare data outside the lock, then update shared state briefly.
- Do not invoke arbitrary callbacks while holding a lock if the callback might run for a long time or acquire other locks.

### 7.2. I/O or logging inside a lock

Writing files, calling databases, network calls, remote services, or synchronous logging can take significant time. If these operations run while holding a monitor, other threads must wait for I/O to complete.

How to fix:

- Collect the data to write while holding the lock, then release the lock before performing I/O if correctness allows.
- Use a queue and dedicated worker for I/O operations that can be handled asynchronously.
- Avoid calling remote services or potentially blocking logging inside a critical section.
- Check whether a lock is wrapping shared logging operations.

### 7.3. A single global lock protecting too much data

A static synchronized method or a global monitor can force unrelated requests to queue together.

How to fix:

- Partition locks by data scope where possible.
- Use concurrent data structures suited to the access pattern.
- Consider partitioning/sharding so independent data groups do not contend for the same lock.
- Evaluate consistency and update ordering before changing the synchronization mechanism.

### 7.4. Threads holding a lock while waiting on another resource

A thread that holds lock A and then waits on lock B, a database, or the network can block many other threads at A. Nested locks also introduce deadlock risk if threads acquire locks in different orders.

How to fix:

- Standardize the acquisition order when taking multiple locks.
- Do not wait on I/O or futures while holding a shared lock.
- Avoid calling code outside the module while still holding an internal lock.
- Set appropriate timeouts or cancellation mechanisms for operations that may wait for a long time.

### 7.5. Contention from logging or cache design

Synchronous logging sharing an appender, a cache with a single global lock, or a frequently updated registry can become an unexpected bottleneck.

How to fix:

- Inspect lock instances and stack traces to identify the component.
- Re-measure after switching to asynchronous logging or an appropriate cache structure.
- Check queue bounds and backpressure policies when using asynchronous processing.
- Do not merely swap synchronized for ReentrantLock without changing the lock scope or hold time; changing the lock type alone does not eliminate contention.

## 8. Distinguishing contention, wait, sleep, park, and deadlock

| State / event | What the thread is doing | How to check |
|---|---|---|
| JavaMonitorEnter | Waiting to acquire a monitor | Check monitor class, previous owner, duration, and stack |
| JavaMonitorWait | Waiting for notify/timeout in Object.wait or APIs using monitor wait | Check notifier, timeout, timedOut, and stack |
| ThreadPark | Parked via LockSupport or mechanisms using it | Check parked class and stack trace |
| ThreadSleep | Sleeping as requested by code | Check where sleep is called and duration |
| SocketRead / FileRead | Waiting on I/O | Check remote endpoint/file and duration |
| Deadlock | Threads waiting on locks in a cycle, unable to progress | Use thread dump and check deadlock report |

JFR duration events typically appear only after the operation finishes. If a thread is deadlocked and never acquires the monitor, do not wait for a completed JavaMonitorEnter event before investigating. Take a thread dump to see the full waiting state and lock relationships.

Run a thread dump:

~~~sh
jcmd <pid> Thread.print
~~~

To print additional information about java.util.concurrent locks:

~~~sh
jcmd <pid> Thread.print -l
~~~

In the thread dump, look for deadlock notices if detected by the JVM, thread states, locks being waited on, locks held, and stack traces of the involved threads. JFR and thread dumps complement each other: a recording gives the timeline and durations; a thread dump gives a point-in-time state snapshot.

## 9. Java 17+ example generating lock contention

The program below creates two controlled types of contention:

- Multiple threads contending on the same intrinsic monitor via synchronized.
- Multiple threads contending on the same ReentrantLock, typically going through LockSupport.park and AQS.

Create LockProbe.java:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.locks.ReentrantLock;

public class LockProbe {
    private static final Object monitor = new Object();
    private static final ReentrantLock reentrant = new ReentrantLock();

    public static void main(String[] args) throws Exception {
        System.out.println("lock-probe-ready");

        for (int i = 0; i < 20; i++) {
            monitorContention(i);
            reentrantContention(i);
        }

        Thread.sleep(30_000);
    }

    private static void monitorContention(int round) throws Exception {
        CountDownLatch held = new CountDownLatch(1);

        Thread owner = new Thread(() -> {
            synchronized (monitor) {
                held.countDown();
                sleep(100);
            }
        }, "monitor-owner-" + round);

        Thread waiter = new Thread(() -> {
            await(held);
            synchronized (monitor) {
                // Wait to acquire the monitor, then exit the critical section.
            }
        }, "monitor-waiter-" + round);

        owner.start();
        waiter.start();
        owner.join();
        waiter.join();
    }

    private static void reentrantContention(int round) throws Exception {
        CountDownLatch held = new CountDownLatch(1);

        Thread owner = new Thread(() -> {
            reentrant.lock();
            try {
                held.countDown();
                sleep(100);
            } finally {
                reentrant.unlock();
            }
        }, "reentrant-owner-" + round);

        Thread waiter = new Thread(() -> {
            await(held);
            reentrant.lock();
            try {
                // Acquire the lock, then exit the critical section.
            } finally {
                reentrant.unlock();
            }
        }, "reentrant-waiter-" + round);

        owner.start();
        waiter.start();
        owner.join();
        waiter.join();
    }

    private static void sleep(long ms) {
        try {
            Thread.sleep(ms);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    private static void await(CountDownLatch latch) {
        try {
            latch.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
~~~

Compile with Java 17 or later:

~~~sh
mkdir -p out
javac --release 17 -d out LockProbe.java
~~~

Run the program:

~~~sh
java -Xms128m -Xmx128m -cp out LockProbe
~~~

Exact stdout when the program starts:

~~~text
lock-probe-ready
~~~

Keep this terminal open. The program generates contention for a few seconds and then keeps the JVM running for another 30 seconds so you have time to capture a recording. Open a second terminal and find the PID:

~~~sh
jcmd -l
~~~

Suppose the PID is 49060. Start the recording:

~~~sh
jcmd 49060 JFR.start name=LockStudy settings=profile disk=true maxage=2m maxsize=64m jdk.JavaMonitorEnter#threshold=5ms jdk.JavaMonitorWait#threshold=5ms jdk.ThreadPark#threshold=5ms
~~~

Check and dump:

~~~sh
jcmd 49060 JFR.check name=LockStudy
jcmd 49060 JFR.dump name=LockStudy filename=lock-study.jfr
~~~

Inspect the events:

~~~sh
jfr summary lock-study.jfr
jfr print --events jdk.JavaMonitorEnter,jdk.JavaMonitorWait,jdk.ThreadPark lock-study.jfr
~~~

Stop the recording:

~~~sh
jcmd 49060 JFR.stop name=LockStudy
~~~

In testing with JDK 24.0.2, the program compiled with javac --release 17 and printed lock-probe-ready as expected. The profile recording was created successfully and contained JavaMonitorEnter, JavaMonitorWait, and ThreadPark events. One monitor contention event lasted about 102 ms, recording previousOwner=monitor-owner-5 and a stack trace pointing to LockProbe.monitorContention. One ThreadPark event for ReentrantLock lasted about 100 ms, with a stack trace through LockSupport.park and AbstractQueuedSynchronizer.acquire. Event counts and durations vary depending on the machine and when the recording starts.

When finished, the JVM exits automatically after about 30 seconds. If you want to stop early, return to the terminal running the program and press Ctrl+C.

## 10. Verifying improvements after optimization

After changing the code, capture a new recording with the same template, threshold, duration, and equivalent workload. Compare before and after:

| Metric | What to observe |
|---|---|
| JavaMonitorEnter event count | Number of contention occurrences recorded at the same threshold |
| Total blocked time | Total time threads were blocked across the recorded events |
| Max duration / duration distribution | Whether long waits have decreased |
| Most frequent lock instance | Whether the previously contending lock is still a bottleneck |
| Threads and stack traces | Whether request-handling threads still wait at the same location |
| Request latency and throughput | Whether users see actual improvement |
| CPU and I/O | Whether the bottleneck shifted to CPU, network, or database |

Do not rely solely on event counts to draw conclusions. If the threshold is 5 ms, waits shorter than the threshold will not appear in the recording. Keep the threshold identical when comparing so the measurements remain meaningful. Combine JFR with application metrics and benchmarks under an equivalent workload.

If contention decreases but latency does not improve, check for other bottlenecks such as I/O, GC, or CPU. An application can have multiple bottlenecks at the same time.

## 11. Common issues and troubleshooting

| Symptom | Common cause | How to resolve |
|---|---|---|
| No JavaMonitorEnter events seen | No monitor contention exceeded the threshold, or the event is disabled | Check event settings, lower the threshold in a short recording, and reproduce the workload |
| Only a few events seen | Most waits are shorter than the threshold | Check the template/threshold and try a lower threshold briefly |
| Many JavaMonitorWait events but no monitor blocked | Threads are using Object.wait or Thread.join | Read the stack trace and notifier/timeout fields to distinguish from JavaMonitorEnter |
| Many ThreadPark events seen | Threads are parking in AQS, queues, futures, or pools | Inspect parkedClass and stack trace; do not treat every park as lock contention |
| Long-duration event but owner is unclear | The stack trace belongs to the waiter; the event only provides previousOwner | Correlate the owner thread on the JMC timeline or take a thread dump |
| No events for a deadlock | Threads never reacquire the lock so the duration event may not complete | Run jcmd <pid> Thread.print -l and check for lock cycles |
| Recording has too many events | Threshold is too low or recording duration is too long | Increase threshold, limit duration/maxage/maxsize, and enable only needed events |
| Cannot attach to JVM | Wrong PID, different user, or attach is disabled | Verify PID, permissions, and JVM configuration |
| Contention remains after changing lock type | Critical section scope and lock hold time did not change | Reduce hold time or redesign shared resource access |

## 12. Lock contention investigation workflow

1. Identify symptoms via latency, throughput, and thread states.
2. Identify the JVM/PID using jcmd -l.
3. Start a JFR recording with monitor/park events and an appropriate threshold.
4. Reproduce the workload or record during the problem window.
5. Dump the file and inspect it with jfr summary.
6. Filter for JavaMonitorEnter, JavaMonitorWait, and ThreadPark.
7. Group by lock/monitor and inspect duration, thread, owner, and stack trace.
8. Use JMC Contention/Lock Instances to drill down into the contending lock.
9. Inspect the code holding the lock, I/O in critical sections, nested locks, and shared data structures.
10. If a deadlock is suspected, run jcmd <pid> Thread.print -l immediately.
11. Fix the root cause and re-measure with the same workload and recording settings.
12. Confirm that both contention and latency/throughput have improved.

### Checklist

- [ ] Identified the correct JVM/PID.
- [ ] Enabled the necessary synchronization events.
- [ ] Understood the threshold and limits on recorded events.
- [ ] Distinguished JavaMonitorEnter, JavaMonitorWait, and ThreadPark.
- [ ] Identified waiting threads and the involved lock/monitor.
- [ ] Read stack traces and correlated previousOwner where available.
- [ ] Checked whether critical sections perform I/O or logging.
- [ ] Distinguished normal contention from deadlocks.
- [ ] Used JMC or the jfr CLI to analyze the recording.
- [ ] Compared before/after using the same workload and threshold.
- [ ] Confirmed actual improvements in latency and throughput.

JFR helps identify which threads are waiting, which locks they are waiting on, and which call paths incur the wait time. By properly distinguishing JavaMonitorEnter, JavaMonitorWait, and ThreadPark, and correlating owners, stack traces, and thread timelines, you can locate the contending critical section, fix the root cause, and verify the improvement with before/after recordings.

## References

- [Oracle JDK 24 — Troubleshoot Performance Issues Using Flight Recorder](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
- [Oracle JDK 24 — The jcmd Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- [Oracle JDK 24 — The jfr Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jfr.html)
- [Oracle JDK 24 — JFR Event API](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jfr/jdk/jfr/Event.html)
- [Oracle — Java Mission Control and Flight Recorder Demo Series](https://www.oracle.com/webfolder/technetwork/tutorials/obe/java/mc-jfr/index.html)