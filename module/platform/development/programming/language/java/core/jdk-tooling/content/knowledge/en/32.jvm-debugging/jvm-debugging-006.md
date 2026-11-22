# Suspend policy in Java debugging

## 1. What is a suspend policy?

In the Java Platform Debugger Architecture (JPDA), a debugger can register requests to receive events from the JVM being debugged (the debuggee). Examples include breakpoints, method entry, method exit, exceptions, single-step, thread start, or class prepare events.

When an event matches an enabled `EventRequest`, the JVM sends an `EventSet` to the debugger's `EventQueue`. The **suspend policy** determines which threads in the debuggee are suspended when that `EventSet` is emitted.

A suspend policy is a property of each `EventRequest` in the Java Debug Interface (JDI). It determines the scope of program suspension at an event so that the debugger can inspect thread state, stack frames, and runtime data.

Suspending a thread does not mean stopping or terminating the Java process. After the debugger processes the event and resumes properly, the thread or JVM continues running.

## 2. Three suspend policies in JDI

JDI defines three constants in the `EventRequest` interface:

| Constant | Value | Behavior |
|---|---:|---|
| SUSPEND_NONE | 0 | Suspends no threads when the event occurs. |
| SUSPEND_EVENT_THREAD | 1 | Suspends only the thread that generated the event. |
| SUSPEND_ALL | 2 | Suspends all threads in the target JVM. |

The numeric values are constants defined by JDI, not application-defined priority levels.

**SUSPEND_ALL is the default** for an `EventRequest` if the debugger does not set another policy.

### SUSPEND_NONE

When the event occurs, the JVM continues running all threads. The debugger still receives the event, but the application state may change before the debugger finishes processing it.

This is suitable for monitoring or event-collection tools that need to minimize impact on the application. It is not suitable if you need a stable stack trace at the exact moment the event occurs.

### SUSPEND_EVENT_THREAD

Only the thread that generated the event is suspended. All other threads continue running.

This is suitable when debugging a specific execution flow in a multi-threaded application, reducing whole-system pause time. Note that other threads may continue modifying shared data while the debugger is inspecting the suspended thread.

### SUSPEND_ALL

All threads in the target JVM are suspended when the event occurs.

This is suitable when you need to inspect the simultaneous state of multiple threads, examine lock relationships, or compare stack traces at the same point in time. In return, the entire application pauses progress for as long as the debugger holds the `EventSet` without resuming it.

## 3. Choosing the right policy

| Debugging need | Typically suitable policy | Reason |
|---|---|---|
| Inspect a breakpoint in one thread | SUSPEND_EVENT_THREAD | Holds the thread at the breakpoint while letting other threads continue. |
| Inspect a deadlock or relationships across multiple threads | SUSPEND_ALL | Requires a stable snapshot of threads to examine state and locks. |
| Record events without pausing the application | SUSPEND_NONE | Minimizes pauses introduced by the debugger. |
| Analyze local variables and stack frames of the event thread | SUSPEND_EVENT_THREAD or SUSPEND_ALL | The thread must be suspended to read stack frames. |
| Observe events in an application with high availability requirements | SUSPEND_NONE, if reading the stack is not needed | Avoids disrupting execution flows. |

There is no single best policy for every situation. Choose based on the information the debugger needs to read and the application's tolerance for pauses.

## 4. Setting the suspend policy on an EventRequest

JDI provides the `setSuspendPolicy(int)` method on `EventRequest`. It can be applied to `BreakpointRequest`, `ExceptionRequest`, `MethodEntryRequest`, `StepRequest`, and other request types that extend `EventRequest`.

Example creating a breakpoint and suspending only the thread that hits it:

~~~java
BreakpointRequest breakpoint =
        eventRequestManager.createBreakpointRequest(location);

breakpoint.setSuspendPolicy(EventRequest.SUSPEND_EVENT_THREAD);
breakpoint.enable();
~~~

If you want to suspend all threads:

~~~java
breakpoint.setSuspendPolicy(EventRequest.SUSPEND_ALL);
breakpoint.enable();
~~~

If you only need to receive notifications:

~~~java
breakpoint.setSuspendPolicy(EventRequest.SUSPEND_NONE);
breakpoint.enable();
~~~

**Configuration order is critical:** create the request, add filters if needed, set the suspend policy, and only then enable the request.

JDI only allows calling `setSuspendPolicy` while the request is disabled. If the request is already enabled or has been deleted, the operation may throw `InvalidRequestStateException`. Passing an invalid policy value may throw `IllegalArgumentException`.

Example applied to `MethodEntryRequest`:

~~~java
MethodEntryRequest methodEntry =
        eventRequestManager.createMethodEntryRequest();

methodEntry.addClassFilter("com.example.OrderService");
methodEntry.setSuspendPolicy(EventRequest.SUSPEND_EVENT_THREAD);
methodEntry.enable();
~~~

Filters help restrict events by class. When there are many unrelated events, filters also reduce the volume of events the debugger has to process.

## 5. EventSet and the actual suspend policy

Events are delivered to the debugger grouped in an `EventSet`. An `EventSet` may contain multiple events occurring at the same time, such as multiple `BreakpointEvent`s at the same location or events related to the same execution.

When multiple `EventRequest`s generate events in the same `EventSet`, the target JVM chooses the policy with the broadest suspension scope among those requests:

- `SUSPEND_NONE` suspends no threads.
- `SUSPEND_EVENT_THREAD` suspends the event-generating thread.
- `SUSPEND_ALL` suspends all threads.

Therefore, if one event request uses `SUSPEND_NONE` but the `EventSet` simultaneously contains an event request using `SUSPEND_ALL`, the actual policy of the `EventSet` will be `SUSPEND_ALL`.

You can read the actual policy with:

~~~java
int actualPolicy = eventSet.suspendPolicy();
~~~

In rare cases, the actual policy may differ from the requested policy if a `ClassPrepareEvent` occurs on a debugger system thread. When handling an `EventSet`, rely on `eventSet.suspendPolicy()` to know which policy the target JVM applied.

## 6. Resuming an EventSet properly

After the debugger retrieves an `EventSet` from the `EventQueue`, it must release the threads suspended by that event once processing is complete.

Standard pattern:

~~~java
EventSet eventSet = vm.eventQueue().remove();

try {
    for (Event event : eventSet) {
        // Read and process the event here.
    }
} finally {
    eventSet.resume();
}
~~~

`EventSet.resume()` behaves according to the actual policy:

- `SUSPEND_ALL`: equivalent to `VirtualMachine.resume()`.
- `SUSPEND_EVENT_THREAD`: equivalent to `ThreadReference.resume()` on the event thread.
- `SUSPEND_NONE`: does nothing because no thread was suspended by the `EventSet`.

Using `finally` ensures the `EventSet` is resumed even if event processing throws an exception. If an `EventSet` is not resumed, the threads it suspended may remain stuck in a suspended state and the target JVM may hang.

JDI recommends retrieving and processing `EventSet`s from the `EventQueue` until a `VMDisconnectEvent` is received; each `EventSet` should be resumed unless the debugger program manages resumption through another mechanism.

## 7. Suspend count and multiple resumes

Thread and JVM suspensions are reference-counted. A thread can be suspended by an event, by `VirtualMachine.suspend()`, or by `ThreadReference.suspend()`.

You can check:

~~~java
int count = thread.suspendCount();
boolean suspended = thread.isSuspended();
~~~

Each suspension requires a corresponding resume before the thread can run again. If the suspend count is still greater than 0, a single resume will not necessarily let the thread continue running.

For suspensions created by an `EventSet`, the standard approach is to call `EventSet.resume()` to release that exact `EventSet`'s suspension.

Do not arbitrarily call `ThreadReference.resume()` or `VirtualMachine.resume()` multiple times to force the application to run. Doing so can skew the suspend count and release another suspension that the debugger or another tool is managing.

## 8. Reading stack frames under each policy

To read a thread's stack frames via JDI, that thread must be suspended.

Example:

~~~java
List<StackFrame> frames = thread.frames();
~~~

If the thread is not suspended, JDI may throw `IncompatibleThreadStateException`.

This creates practical differences:

- With `SUSPEND_NONE`, the thread keeps running; the debugger cannot rely on the current stack frame to analyze state at the event.
- With `SUSPEND_EVENT_THREAD`, the debugger can read the stack of the event thread. Other threads keep running, so shared state may change.
- With `SUSPEND_ALL`, the debugger can read the stacks of all suspended threads and compare them within the same time window.

A `StackFrame` is only valid while the thread remains suspended. Once the thread is resumed, previously obtained `StackFrame` mirrors are no longer valid for continued use.

## 9. Deadlocks and the impact of suspending a single thread

`SUSPEND_EVENT_THREAD` reduces pause scope, but it can create a temporary deadlock situation.

Example:

1. Thread A enters a `synchronized` block and holds monitor M.
2. Thread A hits a breakpoint, and the debugger suspends only A.
3. Thread B continues running and needs monitor M.
4. Thread B must wait for A to release the monitor.
5. If the debugger waits for a result from Thread B while still keeping A suspended, debugging can get stuck.

This is why caution is needed when suspending a single thread that holds a lock or resource required by other threads.

`SUSPEND_ALL` stops all threads, so other threads cannot continue running to create further contention while the debugger inspects state. However, it also freezes the entire application until resumed; long-held requests can increase latency, cause timeouts, or disrupt service.

`SUSPEND_NONE` avoids event-induced pauses, but the debugger must accept that the application continues changing while data is being read.

## 10. Suspend policies in IDEs and breakpoints

Many IDEs allow configuring the suspend policy directly in breakpoint properties. Display names may include:

- Suspend All: corresponds to `SUSPEND_ALL`.
- Suspend Thread: corresponds to `SUSPEND_EVENT_THREAD`.
- None: corresponds to `SUSPEND_NONE`.

When placing a breakpoint on a line of code, check the policy if the application is multi-threaded.

For example, when debugging an HTTP request in a server:

- Suspend Thread keeps the thread handling the request paused so you can inspect variables and the call stack.
- Suspend All helps compare worker thread states or analyze locks.
- None is suitable for breakpoints/events used for observation without stopping workers, though you cannot view a running thread's stack as a stable snapshot.

Some IDEs also offer options to log a message or evaluate an expression when a breakpoint is hit. These actions do not automatically change the suspend policy; check the breakpoint configuration separately.

## 11. Distinguishing EventRequest policy from JDWP startup suspend

Another configuration often confused with a breakpoint's suspend policy is the `suspend` option in the JDWP agent at JVM startup.

Example:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,address=localhost:5005,suspend=y com.example.Main
~~~

The `suspend=y` option causes the JVM to emit a `VMStartEvent` with policy `SUSPEND_ALL`. The JVM is suspended before the main class is loaded and waits for a debugger to connect and resume it.

If you use:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,address=localhost:5005,suspend=n com.example.Main
~~~

The JVM can begin executing before a debugger attaches; `VMStartEvent` uses `SUSPEND_NONE`.

These are two different mechanisms:

| Configuration | Scope | Timing |
|---|---|---|
| JDWP suspend=y/n | VMStartEvent at startup | When the debugger connects or the JVM starts running. |
| EventRequest.setSuspendPolicy(...) | Events generated by breakpoints, exceptions, steps, or other requests | Each time the corresponding event occurs. |

Changing a breakpoint's suspend policy does not change the `suspend=y/n` option at JVM startup. Conversely, `suspend=n` does not mean all subsequent breakpoints use `SUSPEND_NONE`.

With JDI `LaunchingConnector`, the default `suspend=true` argument asks the target JVM to pause right before the main class is loaded; the debugger typically registers event requests before resuming the JVM.

## 12. Hands-on example: a two-thread program

Create the file **SuspendTarget.java**:

~~~java
public class SuspendTarget {
    static volatile boolean running = true;

    public static void main(String[] args) throws Exception {
        Thread worker = new Thread(() -> {
            while (running) {
                try {
                    Thread.sleep(10);
                } catch (InterruptedException ignored) {
                    Thread.currentThread().interrupt();
                    return;
                }
            }
        }, "policy-worker");

        worker.start();
        Thread.sleep(1500);
        hit();
        Thread.sleep(2500);

        running = false;
        worker.join();
    }

    static void hit() {
        // Method entry event monitored by the debugger.
    }
}
~~~

The program creates a `policy-worker` thread and then calls `hit()` on the `main` thread. The worker is still alive when `main` enters `hit()`, so the debugger can observe the difference between the policies.

Create the file **SuspendPolicyHarness.java**:

~~~java
import com.sun.jdi.Bootstrap;
import com.sun.jdi.ThreadReference;
import com.sun.jdi.VirtualMachine;
import com.sun.jdi.VMDisconnectedException;
import com.sun.jdi.connect.LaunchingConnector;
import com.sun.jdi.connect.Connector;
import com.sun.jdi.event.Event;
import com.sun.jdi.event.EventSet;
import com.sun.jdi.event.MethodEntryEvent;
import com.sun.jdi.event.VMDisconnectEvent;
import com.sun.jdi.event.VMDeathEvent;
import com.sun.jdi.request.EventRequest;
import com.sun.jdi.request.MethodEntryRequest;
import java.util.Map;

public class SuspendPolicyHarness {
    public static void main(String[] args) throws Exception {
        String policyName = args[0];

        int policy = switch (policyName) {
            case "NONE" -> EventRequest.SUSPEND_NONE;
            case "EVENT_THREAD" -> EventRequest.SUSPEND_EVENT_THREAD;
            case "ALL" -> EventRequest.SUSPEND_ALL;
            default -> throw new IllegalArgumentException(policyName);
        };

        LaunchingConnector connector =
                Bootstrap.virtualMachineManager().defaultConnector();

        Map<String, Connector.Argument> launchArgs =
                connector.defaultArguments();

        launchArgs.get("main").setValue("SuspendTarget");
        launchArgs.get("options").setValue("-cp " + args[1]);
        launchArgs.get("suspend").setValue("true");

        VirtualMachine vm = connector.launch(launchArgs);

        MethodEntryRequest request =
                vm.eventRequestManager().createMethodEntryRequest();

        request.addClassFilter("SuspendTarget");
        request.setSuspendPolicy(policy);
        request.enable();

        System.out.println("Requested policy: " + policyName);
        vm.resume();

        boolean found = false;

        while (!found) {
            EventSet eventSet = vm.eventQueue().remove(10000);

            if (eventSet == null) {
                throw new IllegalStateException("Timed out");
            }

            try {
                for (Event event : eventSet) {
                    if (event instanceof MethodEntryEvent methodEvent
                            && methodEvent.method().name().equals("hit")) {
                        found = true;

                        System.out.println(
                                "EventSet policy: " +
                                eventSet.suspendPolicy());

                        System.out.println(
                                "Event thread: " +
                                methodEvent.thread().name());

                        for (ThreadReference thread : vm.allThreads()) {
                            if (thread.name().equals("main")
                                    || thread.name().equals("policy-worker")) {
                                System.out.println(
                                        thread.name()
                                        + " suspended=" + thread.isSuspended()
                                        + " suspendCount=" + thread.suspendCount());
                            }
                        }
                    } else if (event instanceof VMDeathEvent
                            || event instanceof VMDisconnectEvent) {
                        throw new IllegalStateException(
                                "Target ended before hit event");
                    }
                }
            } finally {
                eventSet.resume();
            }
        }

        int exitCode = vm.process().waitFor();
        System.out.println("Target exit code: " + exitCode);

        try {
            vm.dispose();
        } catch (VMDisconnectedException expectedAfterTargetExit) {
            // Target has exited and closed the debugger connection.
        }
    }
}
~~~

The harness uses `MethodEntryRequest` to observe when `main` enters `hit()`. `MethodEntryRequest` extends `EventRequest`, so it can be configured with the same three suspend policies. In a real debugger, `BreakpointRequest` uses the same configuration mechanism.

## 13. Compiling and testing the three policies

A JDK with the `jdk.jdi` module is required. Open a terminal in the directory containing the two files.

Compile the target program:

~~~bash
javac --release 17 -encoding UTF-8 SuspendTarget.java
~~~

Compile the debugger harness:

~~~bash
javac --release 17 --add-modules jdk.jdi -encoding UTF-8 SuspendPolicyHarness.java
~~~

Run each policy:

~~~bash
java --add-modules jdk.jdi SuspendPolicyHarness NONE .
java --add-modules jdk.jdi SuspendPolicyHarness EVENT_THREAD .
java --add-modules jdk.jdi SuspendPolicyHarness ALL .
~~~

Each command launches a new target JVM. Actual output on JDK 24.0.2:

~~~text
Requested policy: NONE
EventSet policy: 0
Event thread: main
main suspended=false suspendCount=0
policy-worker suspended=false suspendCount=0
Target exit code: 0

Requested policy: EVENT_THREAD
EventSet policy: 1
Event thread: main
main suspended=true suspendCount=1
policy-worker suspended=false suspendCount=0
Target exit code: 0

Requested policy: ALL
EventSet policy: 2
Event thread: main
main suspended=true suspendCount=1
policy-worker suspended=true suspendCount=1
Target exit code: 0
~~~

The results show:

- `NONE`: both `main` and `policy-worker` continue running.
- `EVENT_THREAD`: `main` is suspended, `policy-worker` continues running.
- `ALL`: both `main` and `policy-worker` are suspended.
- After `EventSet.resume()` is called, the target JVM continues and exits with code 0.

The example was compiled with `javac --release 17`, run with the `jdk.jdi` module on JDK 24.0.2, and verified for all three policies.

## 14. Common errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| Application hangs after a breakpoint is hit | The `EventSet` has `SUSPEND_ALL` or `SUSPEND_EVENT_THREAD` but was not resumed. | Process the `EventSet` and call `resume()` in a `finally` block. |
| Other threads keep running while the debugger is paused | The request uses `SUSPEND_EVENT_THREAD`. | Switch to `SUSPEND_ALL` if you need a full-JVM snapshot. |
| Cannot read stack frames | The thread is not suspended or has already been resumed. | Use an appropriate policy and read `frames()` before resuming. |
| IncompatibleThreadStateException | Calling `frames()` on a thread that is not suspended. | Check `isSuspended()` and `EventSet.suspendPolicy()`. |
| setSuspendPolicy throws InvalidRequestStateException | The request is already enabled or has been deleted. | Disable the request, set the policy, and then re-enable it. |
| Other threads get blocked while debugging | The event thread was suspended while holding a monitor. | Check lock ownership; consider `SUSPEND_ALL` or a different debugging approach. |
| Application continues modifying data during debugging | The request uses `SUSPEND_NONE` or only suspends the event thread. | Use `SUSPEND_ALL` when consistent state is required. |
| Thread remains suspended after one resume | The suspend count is still greater than 0 due to multiple suspensions. | Check `suspendCount()` and balance the resume calls. |
| Target does not run main after attaching | JDWP startup `suspend=y` or `LaunchingConnector` `suspend=true` has not been resumed. | Handle `VMStartEvent` and resume the VM. |
| EventSet policy differs from request policy | The `EventSet` contains multiple requests or a special `ClassPrepareEvent` case. | Check the actual policy using `eventSet.suspendPolicy()`. |

## 15. Controlled debugging workflow

A repeatable workflow:

1. Identify the event to monitor: breakpoint, exception, method entry, or step.
2. Create an `EventRequest` and add class/thread/count filters as needed.
3. Choose the suspend policy based on the level of observation required.
4. Set the policy while the request is still disabled.
5. Enable the request and start receiving events.
6. Retrieve the `EventSet` from the `EventQueue`.
7. Check `eventSet.suspendPolicy()` to determine the actual policy applied.
8. Read stack frames only for suspended threads.
9. Process the event within the necessary scope and avoid keeping threads suspended for too long.
10. Call `EventSet.resume()` in a `finally` block to release the suspension.
11. If a thread remains suspended, check `suspendCount()` and other suspensions.
12. Delete or disable the request when monitoring is no longer needed.

## 16. Security when enabling the debugger

JDWP gives a debugger powerful control over the target JVM, including suspending threads, reading stacks, and altering debug state. Do not expose the debug port on public or untrusted networks.

When remote attachment is necessary:

- Bind only to loopback or a restricted management network address.
- Use a firewall or allow-list to restrict which debugger addresses are permitted to connect.
- Apply the principle of least privilege: grant attach and debug permissions only to personnel who need them for their work.
- Disable the debug endpoint when the investigation session ends if the environment does not need to keep it active.
- Do not share the debug address or configuration as a public service endpoint.

On JDK 24, the JDWP socket transport provides an `allow` option to restrict client addresses. If remote debugging is not required, prefer a local transport.

## 17. Checklist for choosing a suspend policy

- [ ] Clearly identified which event request generates the event.
- [ ] Distinguished between `SUSPEND_NONE`, `SUSPEND_EVENT_THREAD`, and `SUSPEND_ALL`.
- [ ] Aware that `EventRequest` defaults to `SUSPEND_ALL`.
- [ ] Set the policy before enabling the request.
- [ ] Verified the actual policy via `EventSet.suspendPolicy()`.
- [ ] Used `EventSet.resume()` to balance event suspensions.
- [ ] Checked `suspendCount()` if a thread has not resumed running.
- [ ] Ensured the thread is suspended before reading stack frames.
- [ ] Considered deadlocks when suspending only a thread holding a monitor.
- [ ] Evaluated the impact of suspending all threads in production.
- [ ] Distinguished event suspend policies from JDWP startup `suspend=y/n`.
- [ ] Restricted debugger access following the principle of least privilege.
- [ ] Disabled or deleted event requests when the debug session ends.

## 18. References

- Oracle Java SE 24 — JDI EventRequest: https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jdi/com/sun/jdi/request/EventRequest.html
- Oracle Java SE 24 — JDI EventQueue: https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jdi/com/sun/jdi/event/EventQueue.html
- Oracle Java SE 24 — JDI EventSet: https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jdi/com/sun/jdi/event/EventSet.html
- Oracle Java SE 24 — JDI ThreadReference: https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jdi/com/sun/jdi/ThreadReference.html
- Oracle JDK 24 — JPDA Connection and Invocation Details: https://docs.oracle.com/en/java/javase/24/docs/specs/jpda/conninv.html

The suspend policy controls how much of the debuggee is paused at each event request. `SUSPEND_NONE` keeps the application running, `SUSPEND_EVENT_THREAD` pauses only the event-generating thread, and `SUSPEND_ALL` pauses the entire JVM. Choosing the right policy, checking the actual `EventSet` policy, and always resuming properly enables the debugger to observe the needed state while minimizing unintended pauses.