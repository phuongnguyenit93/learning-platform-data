# Stop-the-world and safepoint; distinguishing GC time from total pause time

## 1. Overview: GC, STW, and safepoint are not synonymous

In a JVM, **garbage collection (GC)** manages heap reachability and resource reclamation, **stop-the-world (STW)** describes the interval during which the involved Java threads must stop executing normal application code so the VM can perform an operation, and **safepoint** is the coordination mechanism that brings threads to a safe state for those operations.

Distinguish three observations:

- **There is GC, but not all GC time is STW.** A concurrent collector can mark or perform other phases while application threads are still running.
- **There is a safepoint, but no GC is running at all.** The VM may need to coordinate a global safepoint for other internal tasks, depending on the JDK and implementation.
- **Request latency increases, but it is not due to GC or safepoint.** Locks, sockets, CPU starvation, scheduling, I/O, or cgroup throttling can slow down the application.

The goal of this lesson is to **distinguish the scope of those clocks**: a GC line `Pause ... 0.5ms`, a safepoint line `Total: ... ns`, a GC CPU time chart, and a 120 ms request latency **do not automatically measure the same interval**.

> **Right mindset:** ask whether each metric records **GC work**, **wall-clock GC pause**, **time to reach a safepoint**, **total VM-coordinated stop interval**, or **user end-to-end time**.

### Two opposite scenarios

**Case 1:** GC performs STW work in 2 ms, but has to wait up to 30 ms for Java threads to reach safe states. The safepoint-related JVM stop interval can be significantly longer than 2 ms. Optimizing the object-copying algorithm may not solve the **time to safepoint** bottleneck.

**Case 2:** a concurrent GC cycle takes 500 ms wall-clock, but for most of the time Java threads are still executing, with only a few short pauses. Calling the entire 500 ms “application stopped” would be wrong.

## 2. How does a safepoint work?

The JVM needs to know when a thread is in a state where certain runtime operations can consistently inspect or modify object references, stacks, metadata, and internal structures. In HotSpot, compiled/interpreted code and thread transitions support appropriate **safepoint polls** or safe states. Poll placement and strategy are decided by the JVM/JIT, not manually placed by Java source code on each line.

A global safepoint can be pictured as:

~~~text
              JVM requests a global safepoint
                          |
           +--------------+---------------+
           |              |               |
 Thread A in Java  Thread B in Java  Thread C blocked/native
           |              |               |
     poll / safe   a few more instr.  VM evaluates
       state        then safe          safe state
           |              |               |
           +--------------+---------------+
                          |
                  Conditions met
                          |
                  VM operation runs
                          |
                   Java resumes
~~~

Threads do not necessarily stop together within the same microsecond. Thread A may stop early and wait for thread B. This is part of the reason **reaching safepoint** can affect application experience even when the work at the safepoint is relatively short.

**Further distinctions:**

- A global safepoint is a global coordination mechanism for the required Java threads.
- Some operations can use a **thread-local handshake**, targeting one or more threads instead of causing a global pause.
- `Thread.sleep`, `Thread.yield`, and `Thread.State.WAITING` are not APIs for Java developers to manually force a VM safepoint.
- Native OS threads are not necessarily completely stopped just because Java mutators are STW. Native transitions and certain JNI critical regions have their own rules.

**Stop-the-world does not mean the entire machine, kernel, native code, GC workers, and every other process are frozen.** It is a constraint on Java application activity according to the runtime protocol.

## 3. Decomposing a safepoint into measurement intervals

In a **conceptual timeline**, there are four milestones:

~~~text
        t_request              t_safe           t_work_end       t_resume
             |                    |                  |               |
             v                    v                  v               v
 Java running   |--- coordinate --|--- VM work ------|-- complete ---| Java runs
                 reaching/TTSP       at safepoint       leaving
             |<---------------- total safepoint --------------------->|
~~~

In modern HotSpot logs, you may encounter these fields:

- **Reaching safepoint:** the coordination interval from the start of the request until the required threads are in safe states. Often associated with **time to safepoint (TTSP)**.
- **At safepoint:** the elapsed interval when the VM is at the safepoint condition performing the operation and related overhead.
- **Leaving safepoint:** the completion part / allowing Java execution to continue.
- **Total:** the total safepoint scope according to the timer of that JVM and log.

These milestones are an explanatory model. **Do not treat the labels of one HotSpot build as the JVM Specification standard for every collector/JDK.**

### 3.1. Reaching safepoint is not GC heap work

High TTSP can be caused by:

- A thread responding slowly to a safepoint poll due to compiled code or a native transition.
- A thread not being scheduled enough CPU in time to reach a safe state.
- CPU saturation, container CPU throttling, or excessive concurrency.
- JNI critical regions and special runtime conditions.
- Synchronization/coordination overhead among threads.

Do not conclude “GC mark is slow” when the log shows most of the time is spent in **reaching**: GC work at the safepoint has not even started yet.

### 3.2. At safepoint does not necessarily equal GC elapsed

The at-safepoint interval may include actual GC work along with VM operation overhead, safepoint bookkeeping, preparation, or corresponding completion. A GC summary line has its own timer boundaries and may be smaller than the **At safepoint** or **Total** figure.

If the safepoint reason is unrelated to GC, there can be significant **At safepoint** time with **no GC pause work**.

### 3.3. Leaving safepoint is not the entire request recovery time

The VM completing the handoff to application threads does not guarantee that every thread is immediately scheduled to run by the OS. CPU contention, the ready queue, and remaining business code can push the request well beyond the `Total` reported by the JVM.

Therefore, **total safepoint wall time** differs from **the added latency observed by the user/client**.

## 4. Mathematical model: only add intervals of the same scope

If all milestones are on a single monotonic clock:

~~~text
TTSP              = t_safe - t_request
GC_work_elapsed   = t_work_end - t_safe   (simple single-GC model)
At_safepoint      = t_resume - t_safe
Total_safepoint   = t_resume - t_request
Request_latency   = t_response - t_request_start
~~~

In this model, At-safepoint can be greater than `GC_work_elapsed` because of overhead after the GC algorithm finishes. Request latency can include processing, queueing, I/O, and other pauses.

**Cannot be generalized:** a concurrent GC cycle with multiple pauses or parallel work cannot be reduced to a single `t_safe` and a single `t_work_end`. Do not sum the durations of multiple GC worker threads into an elapsed duration when they run concurrently; that may be **CPU time**.

### Hypothetical numerical example

| Quantity | Value |
| --- | ---: |
| VM requests safepoint | 4.0 ms from request start |
| Last thread reaches safe state | 6.5 ms |
| GC work ends | 13.0 ms |
| JVM allows Java to resume | 14.0 ms |
| Request returns response | 23.5 ms |

The calculated results are TTSP = **2.5 ms**, GC work = **6.5 ms**, At-safepoint = **7.5 ms**, Total-safepoint = **10.0 ms**, Request latency = **23.5 ms**. These are not “mismatched” values; they are different measurement intervals.

## 5. Java 17 program to verify the calculation deterministically

Create the file **`PauseBudgetDemo.java`**:

~~~java
import java.util.Locale;

public final class PauseBudgetDemo {
    static String ms(long micros) {
        return String.format(Locale.ROOT, "%.1f ms", micros / 1000.0);
    }

    public static void main(String[] args) {
        // All simulated timestamps are in microseconds.
        long requestStart = 0;
        long safepointRequested = 4_000;
        long allThreadsSafe = 6_500;
        long gcWorkFinished = 13_000;
        long threadsResumed = 14_000;
        long requestFinished = 23_500;

        System.out.println("sync=" +
                ms(allThreadsSafe - safepointRequested));
        System.out.println("gcWork=" +
                ms(gcWorkFinished - allThreadsSafe));
        System.out.println("atSafepoint=" +
                ms(threadsResumed - allThreadsSafe));
        System.out.println("totalSafepoint=" +
                ms(threadsResumed - safepointRequested));
        System.out.println("requestLatency=" +
                ms(requestFinished - requestStart));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac --release 17 PauseBudgetDemo.java
java PauseBudgetDemo
~~~

**Actual compiled/run stdout for reference (JDK 24, Java 17 target):**

~~~text
sync=2.5 ms
gcWork=6.5 ms
atSafepoint=7.5 ms
totalSafepoint=10.0 ms
requestLatency=23.5 ms
~~~

Key takeaways:

1. `sync` is safepoint coordination latency, **not itself the GC algorithm time**.
2. `gcWork` measures a single hypothetical work region; it is not the total CPU time of multiple GC workers.
3. `atSafepoint` = 7.5 ms, 1.0 ms larger than GC work due to the assumed overhead.
4. `totalSafepoint` = 10 ms adds the coordination phase and the VM-at-safepoint phase.
5. Request latency = 23.5 ms because outside the safepoint interval there is also business processing/waiting.

**This is a program that analyzes simulated timestamps, not a Java API that reads actual safepoint time.** To observe a real JVM, you must use logs/JFR in the following sections.

## 6. Stop-the-world in common collectors

### Serial GC and Parallel GC

- The Serial collector performs collection pauses that require stopping Java mutators; it uses fewer GC workers than parallel collectors.
- Parallel GC can use multiple GC workers to collect **during an STW pause**. Because they operate in parallel, the **total CPU time** of GC workers can be **greater than** the wall-clock elapsed pause.
- When the GC log records `User`, `Sys`, `Real` (depending on collector/level), `Real` reflects the elapsed wall-clock time within the event's scope, not the sum of CPU time across multiple cores.
- A short but frequent GC pause can still affect throughput; a rare and long pause can affect tail latency.

### G1 GC

G1 uses evacuation pauses while also having multiple concurrent steps such as concurrent marking. On HotSpot/JDK 17, depending on the workload, you may see young/mixed pauses, remark/cleanup phases, or failure-related full collections.

**Do not call the entire concurrent marking time “application stopped”.** The Java application can run during most of the concurrent cycle. At the same time, concurrent GC can still compete for CPU/memory bandwidth, changing throughput/latency without being STW.

`-XX:MaxGCPauseMillis` is a **corresponding tuning target**, not a hard deadline for every GC event, safepoint, or request p99.

### ZGC and Shenandoah

Concurrent low-latency collectors aim to move a lot of GC work out of global STW and reduce the necessary pauses, but you should not claim they **never STW** or have no other safepoint operations.

Support levels, collector phases, and flags differ across JDK builds/versions; for example, some Java 17 distributions do not bundle Shenandoah. Check `java -version`, the flags, and the collector in use before comparing.

### Concurrent GC can slow things down even when pause logs are small

If the collector's concurrent threads use many cores and memory bandwidth, business threads can run slower even when stop intervals are short. When p99 is high but safepoint total is low, investigate **CPU contention, allocator pressure, work queues, and system throttling** instead of concluding that GC is definitely unrelated.

## 7. Java 17 lab to generate actual GC logs and safepoint logs

Create the file **`GcTraceLab.java`**:

~~~java
import java.lang.ref.Reference;

public final class GcTraceLab {
    public static void main(String[] args) {
        byte[][] recent = new byte[4][];
        long allocated = 0;

        for (int i = 0; i < 240; i++) {
            recent[i % recent.length] = new byte[256 * 1024];
            allocated += recent[i % recent.length].length;

            if (i % 60 == 0) {
                System.out.println("phase=" + (i / 60));
            }
        }

        System.out.println("allocatedMiB=" +
                (allocated / (1024 * 1024)));

        Reference.reachabilityFence(recent);
    }
}
~~~

Compile:

~~~bash
javac --release 17 GcTraceLab.java
~~~

With **HotSpot** and Bash/Linux/macOS, run with a 32 MiB heap, Serial GC, and write logs to a file:

~~~bash
java -Xms32m -Xmx32m -XX:+UseSerialGC \
  '-Xlog:gc=info,safepoint=info:file=gc-safepoint.log:uptime,level,tags' \
  GcTraceLab
~~~

In PowerShell on Windows, use a single line:

~~~powershell
java -Xms32m -Xmx32m -XX:+UseSerialGC '-Xlog:gc=info,safepoint=info:file=gc-safepoint.log:uptime,level,tags' GcTraceLab
~~~

**Program stdout in a normal run:**

~~~text
phase=0
phase=1
phase=2
phase=3
allocatedMiB=60
~~~

The program was **compiled with `javac --release 17` and run on JDK 24** with these flags, producing exact 5-line stdout. Total cumulative allocation = 240 × 256 KiB = 60 MiB; **this does not mean retaining 60 MiB simultaneously**, because the `recent` array has 4 slots continuously replaced by new arrays.

**VM log numbers are not fixed:** the number of GCs, pause types, heap occupancy, and durations depend on the JDK, machine, collector, and run. Forcing Serial GC and a small heap makes the log easy to observe, without turning GC timing into a deterministic result under the Java Specification.

### An actually observed GC and safepoint log pair

In the aforementioned JDK 24 run, the log file had the pair:

~~~text
[0.032s][info][gc] GC(0) Pause Young (Allocation Failure) 9M->2M(30M) 0.496ms
[0.032s][info][safepoint] Safepoint "SerialCollectForAllocation", Time since last: 16604300 ns, Reaching safepoint: 7500 ns, At safepoint: 573500 ns, Leaving safepoint: 1400 ns, Total: 582400 ns
~~~

Analysis:

- `GC(0)` with cause `Allocation Failure` is associated with a young collection requiring STW.
- The GC summary records **0.496 ms** according to the GC summary's timer scope.
- The safepoint line records `Reaching = 7500 ns` (**0.0075 ms**), `At = 573500 ns` (**0.5735 ms**), `Leaving = 1400 ns` (**0.0014 ms**), Total = **582400 ns = 0.5824 ms**.
- In this event, total safepoint **does not equal** the GC summary duration; the timers cover different parts, which does not prove the metric is broken.
- This is **one data sample from HotSpot 24**, not a fixed format or result for all JDK 17, G1, ZGC, or another production process.

The right way to read: observe **related phase intervals on the same timeline**; do not take an arbitrary GC id and pair it with a safepoint at a different time.

## 8. The `-Xlog` tool: GC and safepoint are two measurement sources

Unified Logging of HotSpot Java 17+:

~~~bash
java -Xlog:gc=info,safepoint=info Main
~~~

`Main` is an **illustrative main class name** and must be replaced with the actual class. Use `java -Xlog:help` to see the tags/levels supported by the specific JVM build.

| Configuration | What do you observe? |
| --- | --- |
| `-Xlog:gc=info` | GC cause/type, event summaries, and some elapsed pauses |
| `-Xlog:safepoint=info` | Safepoint operation name, reaching/at/leaving/total when present in that version's format |
| `-Xlog:gc*=debug` | More information on GC phases and subtags; logs can be very large |
| `-Xlog:safepoint=debug` | Higher-level details of safepoint coordination if supported by the JVM |
| `-Xlog:gc+cpu=info` | Some GC user/sys/real CPU metrics if supported by the tag/event |
| `-Xlog:help` | Verify tags, decorators, and syntax on the actual runtime |

A GC summary line can have the format:

~~~text
[0.123s][info][gc] GC(7) Pause Young (...) 64M->19M(128M) 1.234ms
~~~

The line above is **illustrative**, not fixed stdout. Do not treat `1.234ms` as the entire time all requests were stopped, or assume GC events consist of only one pause.

### Pitfalls when cross-referencing

1. Different units: GC pause may be printed in **ms**, safepoint fields may be printed in **ns**; **1 ms = 1,000,000 ns**.
2. Concurrent phases run overlapping with Java work; do not add their wall time to the STW total.
3. Worker phase durations can run in parallel; **total work time** does not equal elapsed wall time.
4. GC events and safepoint events have different identifiers; match by **operation cause, timestamp, and timeline**, do not blindly match by line order when there are multiple activities.
5. Detailed GC logging also creates overhead; benchmarks need to keep the logging configuration fixed across runs.
6. `-Xlog` and GC tuning flags are HotSpot-specific tools; other JVMs have different logging interfaces.
7. The `GC Pause` line does not encompass all VM work at a safepoint, and a safepoint may be unrelated to GC.

## 9. JFR, JMC, and analysis on the same timeline

**Java Flight Recorder (JFR)** provides events with timestamps and durations, which is more useful than looking at just a single GC number. Event names or thresholds depend on the JDK configuration, but commonly relevant groups include:

- `jdk.GarbageCollection` and `jdk.GCPhasePause` for GC events/phases.
- Safepoint-related events such as `jdk.SafepointBegin`/`jdk.SafepointEnd` when available and enabled.
- Some VM operation, class loading, compilation, allocation, and thread scheduling/park/monitor events.
- CPU, I/O, and thread stacks to help identify non-GC causes.

**Do not assume every event is enabled by the default recording settings.** You must check the JFR event settings of the running JDK and know what the duration field measures.

### Collecting JFR

When starting the application:

~~~bash
java '-XX:StartFlightRecording=filename=latency.jfr,duration=60s,settings=profile' -jar app.jar
~~~

`app.jar` is only an illustrative artifact and must be replaced with the actual file.

When you already have a real JVM PID, use `jcmd`:

~~~text
jcmd PID JFR.start name=Latency settings=profile
jcmd PID JFR.dump name=Latency filename=latency.jfr
jcmd PID JFR.stop name=Latency
~~~

Replace `PID` with the process ID number; the commands require appropriate OS/JVM permissions. You can view the recording with JDK Mission Control (JMC) or the `jfr` CLI:

~~~bash
jfr summary latency.jfr
jfr print --events jdk.GarbageCollection,jdk.GCPhasePause latency.jfr
~~~

JFR data may contain method names, stack traces, and internal application information; keep the file in a location with controlled access permissions.

### Why is app tracing needed alongside JFR?

Suppose a request takes 200 ms, during which there is a 4 ms safepoint but 160 ms is spent waiting for the database. Seeing only a 4 ms GC coinciding in time is **not enough** to attribute the entire request latency to GC. Only when you have request spans and JFR can you identify which critical path was blocked.

## 10. Distinguishing GC CPU time, elapsed time, and total application pause

**GC CPU time**: CPU time consumed by GC threads (depending on how it is accounted), which may be aggregated across multiple cores/threads. When four GC workers run 5 ms of CPU each concurrently, total GC user CPU can be close to **20 ms** while the elapsed pause is approximately **5 ms** plus overhead.

**GC wall elapsed time**: the real-clock duration of a GC event, pause, or concurrent cycle, depending on the event type. The elapsed time of a concurrent cycle **does not equal** STW.

**Safepoint total elapsed**: from the milestone the JVM requests it until completion/release according to the log's timer, which may include reaching and overhead, and may be **a non-GC VM operation**.

**Application stopped time**: the time Java mutator progress is stopped/restricted by safepoints and VM operations, recorded by tools according to their own scope.

**Request end-to-end latency**: includes application compute, locks, queuing, network, downstream services, scheduling, concurrent CPU contention, and STW intervals on the processing path.

These metrics must not be used interchangeably.

| Question | Metric to check |
| --- | --- |
| How long did GC work pause an event? | GC pause summary/phase event |
| How long did it wait for all threads to reach safe states? | `Reaching safepoint`, TTSP |
| How long was the JVM at the global safepoint? | `At safepoint` and `Total` |
| How much CPU did GC workers consume? | GC user/sys CPU times |
| How long did the user feel the slowdown? | Request latency tracing/p99 |
| Did concurrent GC affect CPU/throughput? | CPU utilization, allocation rate, concurrent phases |
| Why did a request pause coincide with a GC milestone? | Correlated GC + safepoint + JFR + request spans |

### P99 cannot be inferred by dividing total GC time by total uptime

For example, a total of 300 ms STW in one minute does not tell you exactly how many ms p99 latency increased. A single 100 ms pause hitting the request critical path can impact tail latency very differently from 100 pauses × 1 ms scattered across time. You need a histogram/distribution and the likelihood of overlap with requests.

## 11. Non-GC safepoint causes

Not every global safepoint is for garbage collection. In HotSpot, depending on JVM version and mechanism:

- Some operations related to deoptimization or management of compiled code.
- Some class redefinition/instrumentation/tooling actions.
- Some VM runtime maintenance tasks.
- Some diagnostics requiring consistency across multiple Java stacks/threads.

Many modern operations can use **thread-local handshakes**, so do not assert that **every thread dump, every stack inspection, or every deoptimization** is a global STW. Read the **safepoint operation name** and JFR events of the actual JVM build.

If a 20 ms safepoint does not belong to GC, it can still affect throughput/latency, but it must not be recorded as “GC algorithm took 20 ms”.

## 12. Diagnosing long TTSP, long GC, and long request latency

A short branching checklist:

**Case A — High `Reaching safepoint`, low GC summary.** Investigate safepoint poll responsiveness, native/JNI transitions, scheduling, and CPU quota. Do not rush to increase the number of GC threads.

**Case B — High `At safepoint`, low reaching.** Identify the operation name. If it is GC, examine collector phases/root scanning, heap pressure, reference processing, and evacuation; if it is another VM op, pivot to the corresponding operation.

**Case C — GC CPU higher than GC wall elapsed.** This may be due to GC workers running in parallel or concurrently; do not treat user CPU as an elapsed pause.

**Case D — Low GC pause, p99 still high.** Check CPU contention from concurrent GC, locks, I/O, TCP/DB latency, OS scheduling, queue depth, and other safepoints.

**Case E — Low total safepoint, but service throughput drops.** Concurrent GC work competes for CPU/memory bandwidth; allocator churn and object allocation rate may cause pressure. Check GC frequency and CPU utilization.

**Case F — One very slow request overlaps multiple safepoints.** Cross-reference each interval and the request critical path, avoiding summing overlapping intervals or adding the entire concurrent cycle.

### A simulated event where TTSP causes a slowdown

~~~text
Reaching safepoint  = 41 ms
At safepoint        =  2 ms
Leaving safepoint   =  1 ms
Total               = 44 ms

GC work summary might be only ~1.6 ms.
~~~

This is a **hypothetical numerical scenario**. Even though the GC algorithm takes just over 1 ms, the total VM safepoint interval can be long due to thread coordination. Do not conclude that the JVM “paused 44ms just to scan objects”.

### A simulated non-GC safepoint event

~~~text
Operation = VM maintenance (not GC)
Reaching  = 1 ms
At        = 30 ms
Leaving   = 1 ms
Total     = 32 ms
~~~

This is also a **simulation**, not an exact JDK event name/format. The 32 ms line can affect application latency, but it should not be added to **GC pause work**.

## 13. Common misconceptions

1. **“GC time = all the time the Java application is stopped.”** False; you must read the timer scope.
2. **“Safepoint is GC.”** False; the VM has safepoints for other operations.
3. **“All concurrent GC time is STW.”** False.
4. **“Stop-the-world stops every native OS thread.”** False.
5. **“All Java threads stop at the exact same nanosecond.”** False; there is a reaching/synchronization phase.
6. **“If GC Pause is 1 ms, then request p99 increases by at most 1 ms.”** False.
7. **“At safepoint has no overhead.”** False.
8. **“Long TTSP proves GC mark is slow.”** False; GC work may not have started yet.
9. **“GC CPU time is the same as wall-clock pause.”** False for parallel/concurrent work.
10. **“Concurrent GC does not affect latency.”** False; there is CPU/memory bandwidth contention.
11. **“ZGC needs no safepoints in any case.”** There is no such guarantee.
12. **“MaxGCPauseMillis is a hard limit on request latency.”** False.
13. **“Summing all GC worker thread durations equals STW elapsed.”** False.
14. **“A single GC summary is enough to explain a 500 ms HTTP request.”** False.
15. **“If a safepoint occurs, every request slows down by that exact entire duration.”** False; it depends on the critical path.
16. **“If concurrent GC is 500 ms, the application stops for 500 ms.”** False.
17. **“The GC log and safepoint log must have the exact same duration.”** False.
18. **“Safepoint poll is a Java statement that can be called manually.”** False.
19. **“The line Total 582400 ns equals 582.4 ms.”** False: it equals 0.5824 ms.
20. **“If GC does not appear in the log, there is definitely no other JVM cause.”** False.

## 14. Self-check and answers

1. GC work 7 ms, reaching 3 ms, remaining overhead 2 ms. In a non-overlapping model, what is total safepoint? **12 ms**.
2. G1 concurrent marking 400 ms, two pauses of 5 and 3 ms. Did the application stop for 400 ms? **No**, a concurrent phase is not synonymous with STW.
3. Four GC workers run concurrently for 5 ms CPU each. Can total CPU be ~20 ms and wall elapsed ~5 ms? **Yes**, plus overhead.
4. Is a 12 ms VM maintenance safepoint recorded as a 12 ms GC pause? **No**.
5. Does safepoint reaching 20 ms and GC work 1 ms prove the GC algorithm took 21 ms? **No**.
6. Can a 150 ms request overlapping a 2 ms safepoint be attributed entirely (all 150 ms) to GC? **No**.
7. Basic HotSpot option to view GC/safepoint? **`-Xlog:gc=info,safepoint=info`**.
8. How many milliseconds is 582400 nanoseconds? **0.5824 ms**.
9. Is every modern thread inspection a global safepoint? **No**, there are targeted handshakes.
10. Can a concurrent collector cause CPU contention even when pauses are small? **Yes**.
11. Is `MaxGCPauseMillis` a hard bound on p99 latency? **No**.
12. Does `System.gc()` always force an immediate STW GC? **No**; it depends on the VM/collector/flags.
13. Why can GC CPU user be higher than GC elapsed? **Multiple parallel GC workers**.
14. If total safepoint is higher than GC pause, what should you check? **Reaching/At/Leaving, operation name, timer boundary**.
15. If a safepoint operation is not GC, should it be ignored when investigating latency? **No**, but classify it properly as non-GC.

## 15. Java 17 and HotSpot references

- Oracle JDK 17 `java` tool: Unified JVM Logging, `-Xlog`, tags and decorators: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Java SE 17 Garbage Collection Tuning Guide (Serial, Parallel, G1, low-latency collector): https://docs.oracle.com/en/java/javase/17/gctuning/
- Oracle JDK 17 Diagnostic Tools (JFR/JMC, GC pause and troubleshooting): https://docs.oracle.com/en/java/javase/17/troubleshoot/diagnostic-tools.html
- JDK 17 `jcmd`, JFR.start/JFR.dump/JFR.stop: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- JDK 17 `jfr` command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html
- JDK 17 Java Flight Recorder module documentation: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/module-summary.html
- JVM Specification 17, Runtime Data Areas: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5

**Conclusion:** **GC** is the memory collection process; **STW** is the interval during which the Java application is stopped/coordinated; **safepoint** is the mechanism by which the VM brings Java threads into a safe state when needed. The **GC pause** figure does not automatically equal **total safepoint**, **GC CPU** does not equal **elapsed wall time**, and **request latency** also contains other causes. You need to read **GC logs**, **safepoint logs**, **JFR events**, and **application tracing** together on the same timeline, event, cause, and unit before diagnosing or optimizing.
