# 8.2 Capturing stacks with Thread.print, jstack, or OS-supported signal mechanisms

## Learning Objectives

When a Java application hangs, requests stall, a deadlock is suspected, or CPU spikes suddenly, a **thread dump** helps observe multiple threads executing, waiting on locks, or waiting for resources at the sampling moment. The problem is not just knowing the command: if you target the wrong PID, use a tool from a different namespace, send the wrong signal, or look for output in the wrong place, an investigator may **fail to collect evidence** or disrupt the service.

This lesson covers three primary mechanisms:

1. **`jcmd <PID> Thread.print`**: sends a diagnostic command to a running JVM.
2. **`jstack <PID>` / `jstack -l <PID>`**: prints stack traces and lock information using the JDK utility.
3. **Signals/console keys supported by the OS and JVM**: `SIGQUIT` and `Ctrl+\` on Linux; `Ctrl+Break` on Windows in cases where HotSpot handles it.

At the same time, you will understand how to use **`Thread.dump_to_file`** for virtual threads on Java 21 when supported by the JVM, why a snapshot is not a CPU profile, how to capture multiple dumps safely, how to choose storage locations, how to troubleshoot attach failures, and how to protect sensitive data in thread dumps.

After this lesson, you will be able to capture a complete dump from **the exact target JVM**, distinguish where each method writes its output, read key fields, and evaluate the limits of conclusions. The hands-on example uses **Java 17+** to create threads with easily observable states.

> Primary scope: HotSpot/JDK 21. Tools, output, permissions, and signal handlers depend on JDK/vendor/VM build, operating system, container, and operational policies. **Do not send signals or run diagnostics in production without verifying the exact PID and authorization.**

## 1. What is a thread dump and what is it not?

A **thread dump** is a snapshot of thread information in a JVM: names, states, Java methods on the stack, and potentially monitors, ownable synchronizers, or a deadlock report. Depending on the method, the VM may expose a different set of threads and data fields; some commands capture a more consistent snapshot or carry different costs than others.

| Data | Can answer | Cannot answer on its own |
| --- | --- | --- |
| **Exception stack trace** of `Throwable` | Where the exception was created/captured and which methods it passed through | What all threads were doing when the service hung |
| **Thread dump** | Which frame/state/lock threads were in around the capture moment | CPU percentage of each method across an entire 10-minute window |
| **CPU sampling profile** via JFR or profiler | Which stacks accounted for high sample shares over a time window | Automatically proving deadlock without lock/ownership evidence |
| **OS thread counters** | Which OS thread is consuming CPU, with what ID and scheduling state | The full Java call stack of the thread |
| **Distributed trace** | Which services/spans a request traversed and how long it took | The full list of threads in a JVM at the same point in time |

A `RUNNABLE` thread does not automatically mean it is using 100% CPU. `WAITING` can be an idle worker waiting on a queue. `BLOCKED` indicates waiting for an **intrinsic monitor** at the time of measurement, but is not always a deadlock: sometimes a thread legitimately holds a lock for a few milliseconds and releases it. Use stacks + lock owners + multiple snapshots + metrics before concluding.

### 1.1 What is typically seen in a dump?

An **illustrative HotSpot format** excerpt:

```text
"worker-17" #34 daemon prio=5 tid=0x... nid=0x2a waiting for monitor entry
   java.lang.Thread.State: BLOCKED (on object monitor)
        at com.example.OrderCache.update(OrderCache.java:88)
        - waiting to lock <0x...> (a java.lang.Object)
        at com.example.OrderService.handle(OrderService.java:40)

"worker-18" #35 daemon prio=5 tid=0x... nid=0x2b waiting on condition
   java.lang.Thread.State: TIMED_WAITING (parking)
        at jdk.internal.misc.Unsafe.park(Native Method)
        ...
```

Addresses and line numbers are abbreviated because **there is no data from a real JVM here**. You need to understand:

- Thread names help locate workloads, but multiple threads can **share the same name**.
- `nid` on HotSpot/Linux typically indicates the native thread ID in **hexadecimal**, which differs from the Java ID and from `tid` (an internal VM pointer/structure).
- `java.lang.Thread.State` is the Java state; it **does not map directly** to every OS scheduling state.
- `at ...` shows stack frames captured by the VM; frames near the top usually indicate where execution or waiting is happening.
- Lines such as `waiting to lock`, `locked`, and `Locked ownable synchronizers` help investigate locks when supported by the command.
- Some dumps also print `Found one Java-level deadlock` when a cycle is detected by the JVM mechanism; the **absence** of this report does not rule out all kinds of waiting.

### 1.2 The cost is not zero

According to Oracle JDK 21 documentation, `Thread.print` has **Impact: Medium — depends on the number of threads**. A JVM with thousands of threads and deep stacks can generate huge output. The dump tool also needs CPU, memory, and time to assemble and print it. Therefore, do not blindly run 100 dumps/second when you only need to observe an incident over several minutes.

For each capture, record the UTC timestamp, JVM identity, and incident window. If the process restarts between two measurements, **do not merge thread IDs from the two processes as if they were the same lifecycle**.

## 2. Which method should you choose?

| Method | Where does it run? | Where does the output go? | Key prerequisites |
| --- | --- | --- | --- |
| `jcmd PID Thread.print` | Terminal with JDK tools and attach permissions to the JVM | **stdout of the jcmd command**, on the caller side | Correct PID/namespace, user/group, target VM support |
| `jcmd PID Thread.print -l -e` | Same as above | stdout of `jcmd` | `help` confirms options; adds lock/extended info |
| `jstack -l PID` | Terminal with compatible `jstack` | **stdout of jstack** | Right process and attach/permissions; tool may be absent |
| `kill -QUIT PID` (Linux) | Host/container namespace seeing the right PID | **stdout/log stream of the target JVM** | HotSpot signal handler active; no `-Xrs` |
| `Ctrl+\` (Linux console) | Terminal attached to the Java foreground process group | JVM console/stdout | Controlling terminal active and JVM handles SIGQUIT |
| `Ctrl+Break` (Windows) | Console window owning the Java process | JVM console/stdout | JVM has console control handler and key event is forwarded |
| `jcmd PID Thread.dump_to_file ...` | Tool and target support this command | **File written by the target JVM** on its filesystem | `jcmd PID help Thread.dump_to_file` confirms command |
| `jhsdb jstack` | Advanced tool, commonly used with core dumps | Terminal/analysis file | Matching binary, permissions, and potentially higher-intrusion operation |

**A reasonable starting point for HotSpot/JDK 21:** prefer `jcmd Thread.print` if the tool is available and attachable; choose `-l` when ownable synchronizers are needed; if `jcmd` is unavailable but `jstack` works, try `jstack -l`. Signals should only be used when you clearly know the JVM supports them and where stdout goes. For applications with many **virtual threads**, also consider `Thread.dump_to_file` or JFR rather than relying solely on traditional dumps.

## 3. Verify the exact JVM before taking any action

### 3.1 Do not look only at the name “java”

One host can run the main service, build daemons, test runners, agents, auxiliary apps, or multiple replicas. PIDs can be **reused**. Record:

- Service/application, environment, host/node.
- Container/pod ID, namespace, or deployment revision if applicable.
- PID and **process start time**.
- JDK/VM vendor/version when retrievable.
- Time when the issue occurred and UTC timestamp of each capture.
- Permissions being used and where the dump will be saved.

On Linux, an example of inspecting a known PID:

```bash
ps -p 12345 -o pid,ppid,lstart,etime,comm,args
```

**12345 is only a placeholder PID.** The `args` field may contain tokens, passwords, or internal paths; do not share raw output publicly. If a process manager reports a different PID than the one found inside a container, identify the **namespace** before attaching tools.

### 3.2 Finding PIDs with jcmd -l

```bash
jcmd -l
```

This command lists JVMs visible to the tool; JDK 21 documentation notes that some JVMs running inside isolated Docker namespaces **do not appear in `jcmd -l`**. Therefore, “not found” is not proof that no Java application is running.

`jcmd` typically requires running on the **same machine** and under the effective user/group matching the target JVM. Do not try to bypass policy via `sudo`, privileged containers, or changing filesystem permissions without authorization. If the tool is unavailable in a minimal image, use approved/pre-deployed collection methods rather than modifying a production container just to add GUI/JDK tools.

### 3.3 Host PID and container PID

A JVM may have **PID 1 inside a container** while having PID 21874 on the host. Running `kill -QUIT 1` from the host could target the machine's init process; inside a container, PID 1 could also be a **shell/supervisor**, not the JVM. Always verify using process metadata in the **same namespace where the command is sent**.

In Kubernetes, verify the exact namespace/pod/container, restart count, image digest, and deployment revision; having the same logical pod name does not guarantee the JVM is still from the previous run. If there are multiple replicas, take dumps from the **replica experiencing the incident**.

## 4. jcmd Thread.print on JDK 21

### 4.1 Verify syntax directly against the target

```bash
jcmd 12345 help
jcmd 12345 help Thread.print
```

Use `help` because diagnostic commands belong to the VM implementation/version. On HotSpot/JDK 21, common commands are:

```bash
jcmd 12345 Thread.print
jcmd 12345 Thread.print -l
jcmd 12345 Thread.print -e
jcmd 12345 Thread.print -l -e
```

- **No options:** captures stacks and states of the threads presented by the command.
- **`-l`:** prints additional information about `java.util.concurrent` locks/ownable synchronizers when supported; useful when suspecting `ReentrantLock`.
- **`-e`:** prints VM-dependent extended thread information.
- **`-l -e`:** combines both detail levels when truly needed; larger output, not necessarily better for every incident.

This is a **data collection command**, not a GC or heap dump request; however, impact still depends on the number of threads. Do not run it continuously at tight intervals. If a command is not listed in `help`, do not guess syntax from another version.

### 4.2 Using shell redirection to save a file

```bash
jcmd 12345 Thread.print -l > threads-12345.txt
```

The output of `jcmd` goes to **stdout of the command in the running shell**. The `>` operator is handled by **the shell invoking the command**, so `threads-12345.txt` appears in that shell's working directory. It **does not automatically appear** inside the Java service's directory when the tool is invoked from another host/container.

A POSIX shell example that writes a timestamped file:

```bash
pid=12345
stamp=$(date -u +%Y%m%dT%H%M%SZ)
jcmd "$pid" Thread.print -l > "threads-$pid-$stamp.txt"
```

Do not use this shell syntax verbatim in PowerShell without converting it to Windows syntax. After capturing, verify the **exit code** and confirm the file actually contains thread entries rather than just an attach error message. A file existing does not prove the command succeeded.

### 4.3 When should you add lock details?

If you suspect a `synchronized` block is held for a long time or `ReentrantLock` contention, `-l` can help retrieve ownership/ownable synchronizer details. If you are investigating a blocked socket read, extra lock info may not answer it because external network/DB state cannot be inferred from monitor ownership.

Thread dumps captured at two different times do not have to be byte-for-byte identical: the JVM is running, and scheduling/GC/I/O continue to change.

## 5. jstack: alternative command and limitations

JDK 21 documentation describes:

```bash
jstack 12345
jstack -l 12345
```

`-l` prints additional lock information, useful for ownable synchronizers. You can use redirection:

```bash
jstack -l 12345 > jstack-12345.txt
```

**JDK 21 marks `jstack` as experimental and unsupported**, and it may not be present in future JDKs. Thus `jcmd` is usually the preferred tool if it meets your needs and is available on the target.

**Do not blindly use legacy options `jstack -F` or `-m`** from guides written for much older JDKs. Check `jstack -help` and the man page for the JDK being invoked. When `jstack` fails to attach, do not infer that the JVM is deadlocked: it may be due to permissions, namespace, process restart, attach disabled, a mismatched JDK tool version, or an unsupported VM.

### 5.1 How does jhsdb jstack differ from jstack?

`jhsdb jstack` is an advanced tool that can read core dumps and, in certain modes, attach to live processes under special permission conditions. Oracle JDK 21 documentation provides an example of reading a core file:

```bash
# Reference: requires actual Java binary and core dump, with analysis permissions.
jhsdb jstack --exe /path/to/java --core /path/to/core-file
```

This is an **advanced investigation option**, not a risk-free replacement for `jstack -l`. Analyzing a live process via the serviceability agent can pause/affect the process and requires its own plan. Without a core file or authorization, do not run it arbitrarily in production.

### 5.2 Only use jstack output when attached to the right process

Compared to `Thread.print`, the tool may add or omit headers and lock data; do not expect two dumps to match identically. Especially with short-lived threads, a thread may have exited before the second command runs.

If the PID disappears between two calls, record the status **process ended/restarted**, and do not keep using the old PID because the OS may have reused it.

## 6. Linux and Unix: SIGQUIT and Ctrl+\

### 6.1 HotSpot signal handler mechanism

According to the Oracle JDK 21 Troubleshooting Guide, on Linux when HotSpot has the appropriate handler installed, sending **SIGQUIT** to a Java process makes the JVM **print a thread dump to the application's stdout**, after which the application continues running. The command using the signal name:

```bash
# ONLY use after verifying the PID and that the HotSpot handler supports SIGQUIT.
kill -QUIT 12345
```

On some Unix/Linux systems, `kill -3` also sends SIGQUIT because signal number 3 is QUIT in that environment, but **signal names** should be preferred to avoid confusion with numbers that can differ on other OSes.

**Extremely important warning:** calling `kill` only sends a signal and does not guarantee the target will survive. If the target is not an appropriate HotSpot process or the SIGQUIT handler is disabled/not installed, **the default OS behavior may terminate the process and produce a core dump**. Never treat SIGQUIT as a “guaranteed read-only” action on an unverified PID.

### 6.2 Why does -Xrs make signal dumps unavailable?

`-Xrs` is a JVM option that reduces the use of OS signals. The JDK 21 `java` documentation states that when running with `-Xrs`, the JVM does not provide **SIGQUIT thread dumps** on non-Windows systems; on Windows it also does not provide dumps via the Ctrl+Break handler. Applications or native libraries installing custom signal handlers can also alter behavior.

Therefore, when a signal command does not print a dump:

- Check the PID, process start time, and that you targeted the right JVM.
- Check `-Xrs`, VM implementation, and signal handlers.
- Look where the Java process actually writes stdout/stderr.
- Check whether the log collector truncates, rate-limits, or rotates logs.
- **Do not repeatedly resend the signal** without verifying, as it can cause disruption.

### 6.3 Ctrl+\ and Ctrl+C are not the same

In a Linux/Unix terminal with an appropriate controlling terminal, **Ctrl+\** normally sends SIGQUIT to the **foreground process group**. If the Java terminal is in the foreground and the HotSpot handler is active, the JVM may print a dump. However, if another process is in the foreground, this key combination can signal the wrong process; therefore do not test it from an arbitrary terminal.

By contrast:

- **Ctrl+C** normally sends SIGINT and can stop the application; it is not the key combination for taking a dump.
- **SIGTERM** is normally a shutdown request.
- **`kill -9` / SIGKILL** terminates the process without normal Java shutdown; **it is not a method for generating a Java thread dump**.

Even though your goal is “capturing stacks”, a signal command still has real OS effects; you must know the exact signal type, JVM handler, and recipient.

### 6.4 Output goes to Java logs, not the kill terminal

If you SSH into a machine and run `kill -QUIT 12345`, **the terminal running `kill` will not display the thread dump**. The dump is written by HotSpot to **the target JVM's stdout**. It may be located in:

- The original console running the `java` command.
- A file to which the Java service redirected stdout.
- `journalctl` if systemd routes the service's stdout to the journal.
- Docker container logs or Kubernetes pod/container logs.
- A logging stream managed by a process manager/app server wrapper.

For example, for a **hypothetical** systemd service:

```bash
journalctl -u example-java.service --since "10 minutes ago"
```

This is a **log reading** command, not a dump generator. Before running it, you need the exact service name, incident time, and where stdout is routed. If the JVM runs in a container, output may be collected by the container logging driver; log retention limits or a multiline parser issue can split or truncate a thread dump.

### 6.5 Why not seeing a dump does not mean the JVM missed the signal

`kill -QUIT` returning a zero exit code only confirms the OS accepted sending the signal; it **does not prove** the JVM printed a complete dump or that the log collector stored it properly. Conversely, seeing no text in your SSH console does not mean failure, because stdout belongs to the process. Check service logs, handlers, PID namespace, and timestamps.

## 7. Windows: Ctrl+Break

For HotSpot running in a **Windows console** that supports control events, **Ctrl+Break** can instruct the JVM to print a thread dump to the **console/stdout of the Java process**. This is Ctrl + the Break/Pause key, **not Ctrl+C**. Some laptops/terminal emulators lack a Break key or do not forward it, so this method may not be available.

If the application runs as a **Windows Service** or under `javaw` without an interactive console, do not assume you can press Ctrl+Break. In that case, prefer `jcmd PID Thread.print` or `jstack -l PID` using JDK tools with appropriate permissions.

To verify the process in PowerShell:

```powershell
Get-Process -Id 12345 |
    Select-Object Id, ProcessName, StartTime
```

This is a **process inspection** command, not a dump generator. If you run `jcmd` from PowerShell, the output goes to that terminal or PowerShell's redirected file, independent of the console where the Java service was started.

**Windows `-Xrs`:** when the JVM enables this option, Ctrl+Break thread dumps are unavailable according to the Java launcher documentation. Do not “work around it” by sending other console events that could stop the service.

## 8. JDK 21 virtual threads: do not infer from traditional Thread.print

Virtual threads are a standard feature of Java 21. A virtual thread can **unmount** from its carrier platform thread while waiting, so traditional HotSpot thread dumps focused on platform threads may **not fully show waiting virtual threads**.

The Oracle JDK 21 “Virtual Threads” guide introduces `jcmd Thread.dump_to_file` to create a text or JSON file containing virtual thread information:

```bash
# Verify the target JVM supports the command before running.
jcmd 12345 help Thread.dump_to_file

# Only use if help confirms -format and filepath.
jcmd 12345 Thread.dump_to_file -format=json /path/approved/threads-12345.json
```

The JDK 21 virtual threads documentation illustrates `-format=text` and `-format=json`, though the command table in the JDK 21 `jcmd` man page does not always list these names identically; **treat `help` from the actual target JVM as authoritative**. Do not take syntax from JDK 22/25/26 and assume it is valid across all JDK 21 builds.

### 8.1 Where is the file located?

Compare the two commands:

```bash
jcmd 12345 Thread.print -l > caller-side.txt
jcmd 12345 Thread.dump_to_file -format=json /path/approved/target-side.json
```

- `caller-side.txt` is created by the shell invoking `jcmd` on **the machine/container running the shell**.
- `target-side.json` is created by **the target JVM** in the target JVM's filesystem. If the JVM runs inside a container, the file may reside inside the container and must be retrieved through an authorized process.
- The two commands are **not equivalent** in dataset contents. A virtual-thread dump file may omit some traditional details about object addresses/locks/JNI/heap, depending on the JDK and implementation.

If you need a timeline of pinning/blocking, combine JFR events such as `jdk.VirtualThreadPinned` and other monitoring data. `Thread.dump_to_file` captures the **current state** and does not reconstruct incidents that happened before capture.

### 8.2 Do not use ThreadMXBean as the total virtual thread count

On Java 21, `ThreadMXBean` primarily manages **platform threads** per the JDK contract. Therefore, the thread count reported by a platform-oriented source **is not** the count of all virtual tasks in the application. When an incident involves tens of thousands of virtual threads, use an appropriately scoped method and state its limits clearly.

## 9. Java 17+ Hands-on: creating BLOCKED and TIMED_WAITING threads

This lab creates three clearly named threads for observation:

- `lab-monitor-owner` holds an object monitor and sleeps for 90 seconds.
- `lab-monitor-contender` tries to enter the same monitor so it is normally `BLOCKED`.
- `lab-timed-waiter` waits on a `CountDownLatch` with a timeout so it is normally `TIMED_WAITING`.

**Holding a monitor while sleeping is an intentional anti-pattern for the lab**—do not copy it to production. The program requires no Internet access, frameworks, or third-party dependencies.

Create file **`ThreadDumpLab.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public final class ThreadDumpLab {
    private static final Object MONITOR = new Object();

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch monitorHeld = new CountDownLatch(1);
        CountDownLatch neverReleased = new CountDownLatch(1);

        Thread owner = new Thread(() -> {
            synchronized (MONITOR) {
                monitorHeld.countDown();
                try {
                    Thread.sleep(90_000L);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "lab-monitor-owner");

        owner.start();
        monitorHeld.await();

        Thread contender = new Thread(() -> {
            synchronized (MONITOR) {
                // Entered after owner releases the monitor.
            }
        }, "lab-monitor-contender");

        Thread timedWaiter = new Thread(() -> {
            try {
                neverReleased.await(90L, TimeUnit.SECONDS);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "lab-timed-waiter");

        contender.start();
        timedWaiter.start();

        System.out.println("ThreadDumpLab READY");
        System.out.println("PID=" + ProcessHandle.current().pid());

        owner.join();
        contender.join();
        timedWaiter.join();
        System.out.println("ThreadDumpLab DONE");
    }
}
```

Compile and run:

```bash
javac ThreadDumpLab.java
java ThreadDumpLab
```

**Exact first stdout line:**

```text
ThreadDumpLab READY
```

The second line has the form `PID=<actual-PID-value>`, varying on each run. After about 90 seconds if uninterrupted, the program prints `ThreadDumpLab DONE` and exits. `javac` prints nothing when compilation succeeds. Do not attempt to predict the PID number, `nid`, line numbers, or the exact moment the scheduler transitions the thread to BLOCKED.

### 9.1 Trying jcmd and jstack

Open a **second terminal** on the same machine/user and replace `12345` with the actual lab PID:

```bash
jcmd 12345 help Thread.print
jcmd 12345 Thread.print
jcmd 12345 Thread.print -l
jstack -l 12345
```

If timed before the threads finish:

| Thread | Expected | How to read |
| --- | --- | --- |
| `lab-monitor-owner` | `TIMED_WAITING (sleeping)` | Inside `Thread.sleep` while still holding the demo monitor |
| `lab-monitor-contender` | `BLOCKED (on object monitor)` | Waiting on the monitor currently held by owner |
| `lab-timed-waiter` | `TIMED_WAITING` | Waiting on the latch with a timeout |
| `main` | Usually waiting in `Thread.join` | Waiting for workers to finish |

These are **expected states within the lab window**. Due to scheduling and capture timing, output may vary; read the **actual result** rather than copying fake sample numbers.

### 9.2 Trying SIGQUIT on Linux with the lab JVM only

Once certain the PID belongs to **ThreadDumpLab** and HotSpot has the handler:

```bash
kill -QUIT 12345
```

Watch the terminal **running `java ThreadDumpLab`**, not only the terminal sending `kill`. The dump normally appears in the lab JVM's stdout. If it does not appear, check the signal handler and session; do not resend to another process.

### 9.3 Trying Ctrl+Break on Windows with the lab JVM only

If you have a real Windows console hosting the Java process, press **Ctrl+Break**. The dump, if supported by the VM, prints in that console. If the terminal lacks Break, try `jcmd` or `jstack` instead of using Ctrl+C or a key combination that could terminate the JVM.

### 9.4 Asking the right question when comparing two dumps

Two dumps 5 seconds apart do not have to be identical; thread states were captured at two different points in time. However, in the lab, `lab-monitor-contender` will typically **remain BLOCKED** until owner releases the lock. Seeing that gives you evidence of **contention persisting across multiple samples**, which is stronger than a single snapshot.

## 10. Capturing multiple dumps to observe trends

A snapshot at T0 is a single point in time. For a symptom where requests stall for 30–60 seconds, several snapshots 5–10 seconds apart can show the same thread/lock appearing repeatedly. Choose the interval based on **incident duration**—there is no immutable rule saying “3 dumps 5 seconds apart”.

The following POSIX shell template should only be run against a **lab JVM** or in production when authorized and overhead has been accounted for:

```bash
pid=12345
for i in 1 2 3; do
  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  jcmd "$pid" Thread.print -l > "threads-$pid-$i-$stamp.txt"
  code=$?
  printf 'sample=%s exitCode=%s\n' "$i" "$code"
  if [ "$code" -ne 0 ]; then
    break
  fi
  if [ "$i" -lt 3 ]; then
    sleep 5
  fi
done
```

Each file is written on **the shell invoking jcmd**, with a timestamp in its filename. Check exit codes, dump headers, and thread entry counts. If the JVM restarts, **stop** the measurement series and record the new identity. Do not run the script across all replicas simultaneously without an impact budget.

### 10.1 What else should be captured alongside thread dumps?

- UTC timestamp, host/container/pod, PID, and process start time.
- Error rate, p95/p99 request latency, throughput, and queue length over the same window.
- OS per-thread CPU when suspecting a hot loop, mapping native TIDs to HotSpot `nid`.
- GC pauses, heap pressure, and safepoint metrics/JFR when needed.
- App build/version and deployment/rollout events.
- Record the source of each snapshot: `jcmd`, `jstack`, `SIGQUIT`, or `Thread.dump_to_file`.

**Limitation:** timestamps from two different tools can drift due to clock skew and collection latency. Do not assert causality merely because two events look “simultaneous” on a dashboard.

## 11. Reading results after collection

### 11.1 Stack frames, lock owners, and states

A HotSpot dump may contain:

```text
"worker-A" ... nid=0x...
   java.lang.Thread.State: BLOCKED (on object monitor)
      at demo.Resource.lockedSection(Resource.java:42)
      - waiting to lock <0x111> (a java.lang.Object)

"worker-B" ... nid=0x...
   java.lang.Thread.State: TIMED_WAITING (sleeping)
      at java.base/java.lang.Thread.sleep(Native Method)
      - locked <0x111> (a java.lang.Object)
```

This excerpt **simulates the structure** and is not real output; the `<0x111>` address and source lines are illustrative only. If owner B holds the monitor for a long time and A waits on the same monitor across multiple dumps, that is lock contention. If A and B hold two different monitors while each waits for the other's monitor, a deadlock cycle may exist; inspect the complete owner relationships.

Not every `WAITING` is abnormal: thread pool workers, scheduled executors, and queue consumers routinely wait for tasks. For network I/O, the stack may start in `sun.nio.ch` or a driver; look at the application caller and downstream telemetry to understand why it is waiting.

### 11.2 RUNNABLE and high CPU

`RUNNABLE` is not equivalent to “consuming all CPU” because some threads may be executing or waiting in native I/O, and VM/OS representations differ. When OS metrics report high CPU:

1. Capture process/thread CPU at the same time.
2. On HotSpot/Linux, `nid=0x...` is typically the native TID in **hexadecimal**; some OS tools print decimal TIDs.
3. Convert the native TID from decimal to hex and match it against `nid`, **never use the internal pointer `tid` or Java thread ID**.
4. Compare the same thread across multiple snapshots and use JFR/CPU profiler if you need exact hotspots.

For example, **decimal 42 = hex `0x2a`**; this is only an illustration of the conversion, not a real measured TID.

### 11.3 Deadlock is not every kind of hang

Java-level deadlock detection finds monitor/ownable synchronizer cycles within its supported scope. A database lock, hung RPC, queue starvation, or missed signal can cause requests to hang **without creating a Java-level deadlock**. “No deadlocks found” does not mean “the application is not hung”.

When seeing many `BLOCKED` threads, ask **who holds the lock**, what the owner's stack is, how long it is held, whether there is progress across samples, and what the thread's role is (request worker, GC, housekeeping). A single snapshot is rarely enough to conclude a persistent issue.

## 12. Diagnosing tool or output problems

### 12.1 jcmd / jstack fails to attach

Some common causes:

- Wrong PID, or the process exited/restarted.
- Different user/group or attach policy.
- Different PID namespace/container mount.
- Runtime image lacks JDK tools.
- VM disabled attach, different JVM implementation, or incompatible tool.
- JVM deeply stuck or blocked by OS security policies.

Check each factor instead of immediately escalating privileges. If collection is not possible, record **diagnostic unavailable** rather than fabricating stacks. `jhsdb` or core analysis can help for severe incidents but carries its own permission/impact requirements.

### 12.2 SIGQUIT sent but no dump appears

Check the following:

1. Have the target JVM and PID/start time been verified?
2. Is `-Xrs` enabled or is the handler absent?
3. Does Java output go to the console, systemd journal, stdout redirect, Docker/Kubernetes logs, or elsewhere?
4. Is the log collector truncating, rate-limiting, or misparsing multiline logs?
5. Are you looking at the logs of the right container/replica and timestamps?
6. In which namespace was the signal sent; do host PID 1 and container PID 1 differ?

Even if the OS reports the signal was sent successfully, do not assume the JVM successfully printed the dump. Without a handler, **SIGQUIT can terminate the process**, so do not retry indiscriminately.

### 12.3 Windows Ctrl+Break does not work

The JVM may be running as a service with no attached console, running under `javaw`, started with `-Xrs`, or the terminal may not forward Break events. Use `jcmd`/`jstack` with proper permissions and never substitute Ctrl+C for Ctrl+Break.

### 12.4 File has data but is truncated

Thread dump output can be very large, especially with thousands of threads. If written via stdout logging, a multiline parser, buffer limit, quota, or log rotation can cut the dump mid-stream. When that happens:

- Mark **capture incomplete**.
- Check the beginning/end of the file and timestamps.
- Do not infer from a missing thread in the truncated portion that the thread did not exist.
- If permitted, try saving output directly with `jcmd` shell redirection instead of routing through the log pipeline.
- If using `Thread.dump_to_file`, verify the file on the right JVM filesystem and write permissions.

### 12.5 Connection failures inside containers

A container may lack `ps`/`jcmd`; `jcmd -l` from the host may also fail to see the JVM. If tools are needed, follow approved incident debugging procedures (such as approved ephemeral/debug tooling) instead of arbitrarily altering a running image. Preserve node/pod/container identity and check the PID namespace before sending any signal.

## 13. Safety, access permissions, and cost

A thread dump can contain **internal class/method names, thread names embedding user/request IDs, paths, endpoints, library details, object addresses, and lock metadata**. Even though it does not by default include all local variables, it is not public data. Protect it by:

- Collecting only from the right service and with authorized permissions.
- Storing in a restricted diagnostics directory; setting retention and deletion procedures.
- Redacting sensitive thread names/log labels or metadata before sharing.
- Not uploading raw dumps to third-party analysis services without authorization.
- Attaching process identity, timestamp, tool/command, and complete/truncated status to the artifact.
- Limiting frequency, number of replicas, disk, and logging overhead.

Capturing a dump can increase CPU/I/O and worsen load on an already overloaded service, especially if snapshots are taken frequently. Never send `SIGKILL`/`SIGTERM` just to “get thread stacks”. With `SIGQUIT`, verify the handler first because without it, **the effect can destroy the process**.

A **hypothetical** metadata record:

```yaml
captureTimeUtc: "2026-10-29T08:45:00Z"
service: "checkout-api"
environment: "staging"
instance: "checkout-2"
pid: 12345
processStartUtc: "2026-10-29T08:05:00Z"
javaRuntime: "21.0.x"
tool: "jcmd"
command: "jcmd 12345 Thread.print -l"
outputLocation: "restricted-diagnostics/threads-12345.txt"
captureComplete: true
redactedBeforeSharing: true
incidentWindow: "2026-10-29T08:44:00Z/2026-10-29T08:46:00Z"
```

All numbers and names above are **illustrative data**. Do not copy them into a real report without collecting data from a real JVM. If captured via signal, record `method: SIGQUIT` and where the JVM's stdout goes instead of recording `jcmd`.

## 14. Six-step incident workflow

**Step 1 — Define the symptom.** Stuck requests, lock contention, CPU spike, hung I/O, thread leak, or virtual-thread stalls? Define the time window and available telemetry.

**Step 2 — Select the exact JVM.** Verify service, host/container, PID, start time, runtime/version, and permissions. Do not capture a dump from a healthy replica and use it as evidence for a failing replica.

**Step 3 — Choose tool and output location.** Prefer `jcmd Thread.print` when supported; `jstack -l` as a fallback; signals only when the handler is verified; `Thread.dump_to_file` when virtual-thread visibility is needed and the command appears in `help`.

**Step 4 — Capture within an impact budget.** Several dumps within the incident window are enough to identify persistent states. Record timestamps, exit codes, and inspect files; if the process restarts, stop the old series.

**Step 5 — Analyze against telemetry.** Read states/monitors/lock owners, compare multiple snapshots, OS native TID CPU, GC pauses, request p99, and downstream metrics. Separate a single occurrence of `BLOCKED` from sustained contention or a deadlock cycle.

**Step 6 — Record observations and right-sized conclusions.** For example, “12 request workers are at the same `OrderRepository.save` across three dumps” is an observation. “The DB connection pool is too small” remains a hypothesis until corroborated by pool/DB/queue metrics. If dumps are incomplete, state the limitations explicitly.

## 15. Common misconceptions

| Misconception | Correct understanding |
| --- | --- |
| “`jcmd -l` not showing the process means the JVM is not running.” | PID namespaces/permissions can prevent the tool from listing every JVM. |
| “PID 1 in Docker is PID 1 on the host.” | Namespaces can differ; do not send signals without verifying the process. |
| “`Thread.print` always has zero impact.” | Impact is Medium, increasing with thread count and output size. |
| “`-l` only prints extra method names.” | It adds ownable synchronizers/`java.util.concurrent` locks. |
| “`jstack -F` is always available in JDK 21.” | Options change; read the man page/`-help` of the tool in use. |
| “`jstack -l` must match `jcmd Thread.print -l` character for character.” | Two captures occur at different moments and formatting can differ. |
| “`jcmd ... > file` saves the file inside the JVM/container.” | Redirection belongs to the shell **invoking jcmd**. |
| “`kill -QUIT PID` prints stacks in the kill command's terminal.” | Signal dumps go to the **target JVM's stdout/log stream**. |
| “SIGQUIT is guaranteed not to stop Java.” | Without a handler or with `-Xrs`, the OS may terminate/core dump. |
| “Ctrl+C is the Windows way to take a thread dump.” | Windows consoles use **Ctrl+Break** when supported. |
| “`kill -9` makes the JVM print a dump before dying.” | SIGKILL is never used to generate a Java thread dump. |
| “Not seeing output in the SSH terminal means the JVM missed the signal.” | Check app logs/stdout pipeline, PID, handler, and `-Xrs`. |
| “Thread.print is guaranteed to list every virtual thread.” | Traditional dumps can miss unmounted virtual threads; use Java 21-appropriate tools. |
| “`RUNNABLE` means the thread is using 100% CPU.” | OS CPU counters/JFR are needed, not just Java state. |
| “`WAITING` is always a deadlock.” | Idle pool/queue workers wait legitimately. |
| “No Java deadlock report means requests cannot hang.” | Network/DB waits, starvation, and missed signals can fall outside deadlock detection scope. |
| “A dump after restart describes the pre-restart incident.” | Snapshot data belongs to the new process/run and does not recover history. |
| “Having a file means capture succeeded.” | The file might only contain error text or be truncated; inspect the output. |
| “A raw thread dump contains no sensitive data.” | Thread names, paths, packages, hostnames, and structure can be sensitive. |

## 16. Self-check questions

**Q1.** Where does `jcmd 12345 Thread.print -l > a.txt` save `a.txt`?

**Answer:** in the working directory of **the shell invoking `jcmd`**. It is not automatically placed in the JVM container's filesystem if the command runs from another host.

**Q2.** You SSH into a machine, send `kill -QUIT` successfully, but the SSH terminal shows no dump. Does that prove failure?

**Answer:** no. The HotSpot handler writes the dump to the **Java process's stdout**; check journal, container logs, stdout redirects, or the console owning the JVM.

**Q3.** Can you send SIGQUIT to any PID named java without checking `-Xrs`?

**Answer:** no. Without a SIGQUIT handler, the OS can terminate/core dump the process; verify PID, VM handler, permissions, and risk first.

**Q4.** Why choose `Thread.print -l` when suspecting `ReentrantLock`?

**Answer:** `-l` adds ownable synchronizers/`java.util.concurrent` lock details when supported by the VM. You still need to verify owners, call stacks, and duration.

**Q5.** Java 21 uses many virtual threads, yet `Thread.print` returns few threads. Can you assert the virtual threads have finished?

**Answer:** no. Some unmounted virtual threads may not appear in a traditional thread dump. Use `Thread.dump_to_file` when supported by the target, or JFR/monitoring with the right scope.

**Q6.** Is a `RUNNABLE` thread appearing in a dump a CPU hotspot?

**Answer:** not yet. You need OS per-thread CPU, native `nid` correlation, and CPU sampling over an interval.

**Q7.** All three dumps over 15 seconds show thread A as `BLOCKED`. Is that sufficient proof of deadlock?

**Answer:** not yet. A lock may be held for a long time while still making progress. Check owners, wait cycles, throughput, and context; do not equate contention with deadlock.

**Q8.** Why shouldn't `kill -9` be used to collect a dump?

**Answer:** SIGKILL stops the process immediately at the OS level, giving the JVM no opportunity to handle a signal and emit Java stacks through this mechanism.

**Q9.** `jstack -l` fails after the lab prints `DONE`. Is the JVM deadlocked?

**Answer:** no. The lab JVM has exited; check the PID/start time and do not continue sending signals to a PID that may already have been reused.

**Q10.** Two dumps from the same JVM 5 seconds apart yield different results. Is the tool broken?

**Answer:** not necessarily. The JVM is running and threads change states continuously. What matters is recording timestamps, comparing relevant threads/locks, and identifying meaningful trends.

## 17. End-of-lesson checklist

- Verify the **exact JVM, PID/start time, host/container namespace, and permissions**.
- Choose **`jcmd Thread.print`** if supported; inspect `help`, add `-l`/`-e` when targeted.
- Use **`jstack -l`** when appropriate, keeping in mind JDK 21 marks the tool experimental/unsupported.
- Only use **Linux `SIGQUIT`/`Ctrl+\`, Windows `Ctrl+Break`** when the handler is verified; understand `-Xrs` and default signal risks.
- Distinguish **caller-side stdout/file** of `jcmd/jstack`, **target JVM stdout** of signals, and **target filesystem** of `Thread.dump_to_file`.
- Do not treat a traditional platform-thread dump as a complete list of all Java 21 virtual threads.
- Take several snapshots within the **incident window**, with UTC timestamps and process identity.
- Verify the file contains a **real, untruncated thread dump**, and store it securely.
- Read states, locks, owners, OS native TIDs, and stacks alongside telemetry; never conclude root cause from a single snapshot.
- Never use SIGKILL, Ctrl+C, or process-stopping actions when the goal is only to collect stacks.

**Conclusion:** capturing stacks properly means **identifying the JVM → choosing the right tool → knowing where output goes → limiting risk → reading snapshots in temporal context**. On HotSpot/JDK 21, `jcmd Thread.print` is usually the first step, `jstack` is a fallback option, and SIGQUIT/Ctrl+Break are useful when supported by the VM/OS, provided extreme care is taken not to disrupt the very application you are trying to diagnose.

### Official references

- [Oracle JDK 21 — The jcmd Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): `Thread.print` syntax, `-l`, `-e`, impact, and attach prerequisites.
- [Oracle JDK 21 — The jstack Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jstack.html): `jstack`/`-l`, experimental/unsupported tool status.
- [Oracle JDK 21 — Diagnostic Tools and Control+Break Handler](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html): Linux SIGQUIT, Windows Ctrl+Break, stdout, thread states, and deadlock reports.
- [Oracle JDK 21 — The java Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): `-Xrs` option and Java/OS signal handling.
- [Oracle JDK 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): virtual threads and text/JSON `Thread.dump_to_file`.
- [Java SE 21 — ThreadMXBean API](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html): thread diagnostics, locks, and platform thread monitoring capabilities.