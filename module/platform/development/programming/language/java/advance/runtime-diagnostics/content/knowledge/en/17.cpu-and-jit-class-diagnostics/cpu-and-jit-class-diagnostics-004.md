# 17.4 Distinguishing a Method's Own Time from Costs Through Child Calls

## Learning Objectives

When reading Java Flight Recorder (JFR), Java Mission Control (JMC), call trees, flame graphs, or CPU profiler reports, the same method can appear with two very different numbers: **self/exclusive** and **total/inclusive**. A method with low self yet high total may simply be **orchestrating** expensive calls; a method with high self may actually be consuming heavy CPU in its own body. If you cannot distinguish the two calculations, it is easy to optimize the wrong place or misattribute database, GC, or thread-waiting latency to a Java method.

This lesson is framed within **CPU, JIT, and classes**: it focuses on reading JFR stack samples, analyzing call structures, and understanding the effect of inlining/JIT, rather than turning sampler counts into exact per-call execution durations.

After this lesson, you will be able to:

1. Explain self/exclusive and total/inclusive, how they are computed, and their relationship to the call tree.
2. Correctly read Hot Methods, Call Tree, and flame graphs over CPU sample data.
3. Distinguish a method's CPU cost from elapsed/wall-clock time, blocked/waiting time, and end-to-end latency.
4. Understand why recursion, the same method appearing in multiple branches, stack truncation, JIT inlining, and sampling cause metrics to be misread.
5. Trace from a high-total method down to the child calls creating cost and from a high-self method to the code needing measurement/evaluation.
6. Use JFR/JMC and external metrics to form testable performance hypotheses; avoid declaring a root cause from a single flame graph bar.

Scope: Java 17+ (HotSpot/OpenJDK, command examples for JDK 21). Column names, aggregation rules, and profiler units may differ; always verify whether **the input data is sample count, estimated CPU time, instrumented wall time, or another metric**.

## 1. Fundamental Model: Methods and Call Trees

Consider a synchronous call path:

~~~text
main()
  -> Controller.handle()
       -> Auth.check()
       -> Service.execute()
            -> Repository.query()
            -> Formatter.render()
~~~

At the moment the thread is running inside `Repository.query()`, the stack may contain `main`, `Controller.handle`, `Service.execute`, and `Repository.query`. If you ask "at **which frame** is code currently executing?", the answer is usually the frame at the **top of the stack** (a leaf in the caller-to-callee tree). If you ask "how much work across the whole branch is the `Controller.handle()` call responsible for?", you must include activity occurring in child methods.

Two concepts:

- **Self time / exclusive cost:** the portion of time or samples attributed to that method itself, **excluding work inside child calls** under the measurement model in use.
- **Total time / inclusive cost:** the portion of time or samples attributed to that method **plus all child calls** beneath it along the examined call path.

In a single-threaded sequential execution tree with no overlap, using the same clock and complete instrumentation data:

~~~text
inclusive(A) = exclusive(A)
             + inclusive(B) + inclusive(C) + ...
~~~

Here `B, C` are the **direct child calls of one single invocation of A**, not every method with the same name across the application. This identity does not automatically hold for multiple parallel threads, asynchronous calls, recursive loops collapsed into a method-level row, or sampling data with missing samples. When a method calls a child multiple times, its total includes all corresponding invocations, assuming complete measurement without double counting.

**Principle:** self answers "how much time/samples sit in A's own body?", while inclusive answers "when the stack passes through A, how much does that entire branch account for?". They answer **two different questions**, not two conflicting measurements.

## 2. Example Calculation Using Sequential, Non-Overlapping Elapsed Time

Suppose a request executes the exact sequential structure below. The values are **illustrative figures**, not measured JFR data:

~~~text
Controller.handle()       total 120 ms
├── Repository.load()      total  90 ms
│   └── Socket.read()      total  85 ms
└── Formatter.encode()     total  20 ms
~~~

If there are no other child calls and no overlap occurs:

| Method | Total / inclusive wall time | Time in direct children | Self / exclusive wall time |
| --- | ---: | ---: | ---: |
| Controller.handle | 120 ms | 90 + 20 = 110 ms | 10 ms |
| Repository.load | 90 ms | 85 ms | 5 ms |
| Socket.read | 85 ms | 0 ms | 85 ms |
| Formatter.encode | 20 ms | 0 ms | 20 ms |

The sum of self across all nodes in the tree is 10 + 5 + 85 + 20 = **120 ms**, matching the duration of the `Controller.handle` call under the assumptions above. Yet the sum of the inclusive values across the rows is 120 + 90 + 85 + 20 = **315 ms**: that **re-counts the same time intervals** across multiple caller/callee levels, not a 315 ms request.

How to read this properly:

- `Controller.handle` has total 120 ms yet self is only 10 ms: optimizing instructions inside the controller itself can affect at most a small fraction of time unless you change how it invokes its children.
- `Repository.load` has total 90 ms yet self 5 ms: most time comes from `Socket.read` underneath; investigate network/database, connection handling, or query patterns before optimizing a few Java lines in the repository.
- `Socket.read` has self wall time 85 ms, which **does not mean it used 85 ms of CPU**. The thread may be waiting for data while consuming very little CPU.
- `Formatter.encode` has self wall time 20 ms: if it is genuinely CPU-bound, it may be a CPU optimization target; verify with a CPU profiler.

This example uses **wall-clock instrumentation**. Do not label these wall numbers as JFR CPU samples.

### Why Is a High-Total Method Not Necessarily the Culprit?

A controller is the outer wrapper of a request, so it naturally has high total. For request handlers, thread roots, servlet dispatchers, executor workers, framework interceptors, or processing loops, inclusive is usually high because they are **coordination hubs calling lots of work**, not because the method body itself is slow. Expand child nodes down to where cost concentrates, then classify whether it is CPU computation, blocking I/O, scheduling, or waiting.

## 3. Formulas for Reading CPU Sampling Results

JFR typically supports **stack sampling** to locate hot execution paths. When sampling, the tool inspects stacks of eligible threads at points in time, emitting events such as `jdk.ExecutionSample` (depending on settings/JDK). Each sample is a snapshot, not a complete method invocation with start and end timestamps.

Suppose `N` samples are selected in a time window and each sample is a stack chain from caller to executing frame. For method `M`, when aggregating by **method identity** (not per call-path node):

- **Self samples(M):** the number of samples where `M` is the executing/leaf frame attributed to the sample.
- **Inclusive samples(M):** the number of samples where `M` appears in any eligible position on the stack, per the tool's aggregation rules.
- **Self share(M):** `self samples(M) / N`, when `N` is the exact sample set under the same filter.
- **Inclusive share(M):** `inclusive samples(M) / N`, when each sample is counted at most once for method `M` in that aggregation.

Example with 100 samples:

| Method | Self samples | Inclusive samples | Interpretation |
| --- | ---: | ---: | --- |
| Controller.handle | 3 | 80 | Very often on the stack, but few samples stop inside its own body |
| Repository.lookup | 2 | 60 | Repository's child call branch is prominent |
| Parser.parse | 35 | 35 | Many samples have `Parser.parse` as the executing frame |
| Hash.compute | 25 | 25 | Notable self hotspot worth inspecting |
| Thread.run | 0 | 100 | Root wrapping all selected threads; does not mean `Thread.run` uses CPU itself |

The rows only illustrate how to read the numbers, and do not require the self sum of these 5 rows to equal 100 because the table does not list every method. **Inclusive share across multiple methods can each be high and sum past 100%**: one sample can simultaneously contribute to `Controller.handle`, `Repository.lookup`, and `Hash.compute` because all three lie on the same stack.

Nor may you state "80 inclusive samples = 80 ms of CPU" unless the profiler provides a grounded conversion model. Sampling can be uneven, delayed, or skewed toward certain threads; sample counts are primarily **relative observation frequency**, not an exact execution-time counter.

### Self in Hot Methods vs. Self in Call Tree Can Differ in Scope

A row in **Hot Methods** can combine samples for the same method from **all call paths**. A node in **Call Tree** is typically tied to **one specific call path**. The same method can appear in multiple different nodes, each with its own inclusive/self. Therefore, do not compare a Hot Methods row against a single Call Tree node and claim they contradict without aligning scope first.

## 4. Three Views: Hot Methods, Call Tree, and Flame Graph

### 4.1. Hot Methods: "Where Is Self Concentrated?"

A hot methods list helps find frames that appear frequently at active execution points or carry high exclusive cost. Use it to spot math, loops, parsers, serializers, hashing, regexes, compression, or libraries likely consuming CPU.

Check:

- Does the column show self, total, or count? Does the tool group by thread, method, stack path, or class?
- Are there overloaded methods or identical names? Distinguish class, signature, and classloader when needed.
- Is the sample count representative? Is there sample bias or missing stacks?
- Was actual process/thread CPU high during that interval?
- Does the method involve JIT inlining, compiled/native frames, or missing metadata altering display?

A high-self hot method **suggests** a hot compute area, but has not yet measured the gain of changing it or proven it sits on the critical path of slow requests.

### 4.2. Call Tree, Top-Down: "Which Branch Does the Cost Flow Through?"

Start from an entry/root (`Thread.run`, request dispatcher, task/executor, or selected method) and walk caller → callee. At each node:

1. Check the node's inclusive share relative to the selected samples.
2. Check the node's self share.
3. If inclusive is high while self is low, **expand children**.
4. Keep descending to find child nodes with high self or branches taking a substantial share.
5. Verify this path belongs to the workload you want to optimize, rather than background worker/GC/compiler threads.

**Branch percentages:** A child node taking 70% of its **parent's** samples may represent only 7% of total samples across the recording if the parent accounts for only 10%. Always check the denominator of each column/view to avoid reading parent-relative percentages as system-wide CPU percentages.

### 4.3. Bottom-Up / Caller Tree: "Where Is the Hot Method Called From?"

Start from a high-self method (for example `Parser.parse`) and expand callers above it to see what triggers it: endpoint A, batch B, or framework C. This is valuable when the same method is invoked from many paths yet **only one path** creates the bottleneck.

For example, `Parser.parse` has 40 self samples across the application:
- 30 samples belong to `/import` with huge payloads;
- 10 samples belong to `/preview` with small payloads.

Optimizing `Parser.parse` may help both, yet inspecting the `/import` context reveals whether streaming or cutting repeated parses is needed. Looking only at Hot Methods makes it easy to miss **which caller** drives the processing demand.

### 4.4. Flame Graph: Width Does Not Equal Call Count

In a CPU sampling flame graph:

- Each stack sample contributes to aggregating the width of the frames along its call path.
- A parent node is wide because it encloses many stack samples; a leaf node is wide because it frequently appears at the executing tip.
- Height represents stack depth, not duration.
- The horizontal axis is usually a grouped stack layout, **not a chronological timeline** like timeline events.
- Colors in many flame graphs only aid distinction/grouping, and **do not by default indicate severity or CPU temperature**.

If 60% of samples pass through `Controller.handle` and 35% have `Parser.parse` at the leaf, you cannot say the controller spends 60% CPU **on top of** the parser's 35% CPU. The two have a containment relationship and cannot be added as two independent expenses.

## 5. How to Verify Calculations Using Concrete Stack Samples

Suppose we have 20 stack samples, with identical stacks grouped. Each line is written **leaf → root**; frequency is the sample count:

| Frequency | Stack (leaf → root) |
| ---: | --- |
| 6 | Parser.parse → Service.handle → Thread.run |
| 4 | Sorter.sort → Service.handle → Thread.run |
| 3 | Hash.compute → Cache.lookup → Service.handle → Thread.run |
| 2 | Service.handle → Thread.run |
| 5 | Scheduler.idle → Thread.run |

Result:

| Method | Self samples | Inclusive samples | Explanation |
| --- | ---: | ---: | --- |
| Parser.parse | 6 | 6 | Only appears at the leaf |
| Sorter.sort | 4 | 4 | Only appears at the leaf |
| Hash.compute | 3 | 3 | Self cost of hashing |
| Cache.lookup | 0 | 3 | Only a caller of hash in these samples |
| Service.handle | 2 | 15 | Present in 6 + 4 + 3 + 2 samples |
| Scheduler.idle | 5 | 5 | Remaining 5 samples on another branch |
| Thread.run | 0 | 20 | Root of all selected stacks |

**Conservation check at node `Service.handle`:** self 2 + inclusive of its three child branches (6 + 4 + 3) = 15. Yet if you add `Service.handle`'s inclusive (15) to its children's inclusive (6 + 4 + 3), you double-count.

This example intentionally uses **synthetic aggregate samples**, not real CPU time or default JMC output. With real tools, know whether the tool computes by sample/stack, weight, sample count, and thread/time-window filters.

## 6. Easy-to-Miss Edge Cases: Recursion and Multi-Occurrence Methods

### 6.1. One Method at Two Levels of the Same Stack

Recursion example:

~~~text
Worker.run()
  -> Factorial.compute(5)
       -> Factorial.compute(4)
            -> Factorial.compute(3)
~~~

If a sample has a stack containing `Factorial.compute` **three times**, when aggregating by **method identity**, `Factorial.compute`'s inclusive samples should normally count **one sample containing that method** (so inclusive cannot exceed total samples due to recursion). Yet when displaying a **call-path call tree**, the three `Factorial.compute` nodes at three depths are three distinct invocations/paths; the same sample can contribute to each node's inclusive count.

The two representations serve two purposes:

- **Method aggregate:** "In how many samples does method `Factorial.compute` appear?". Avoid counting the same method multiple times within one sample when defining inclusive as the number of samples containing the method.
- **Call-path/node aggregate:** "At this specific depth/call, how many samples belong to this branch?". Multiple nodes for the same method can be shown, and these nodes nest inside each other.

Check how your tool displays recursion; do not claim every profiler uses the exact same aggregation formula, especially when method-level rows and call-path nodes compute differently.

### 6.2. One Method Called by Multiple Parents

~~~text
RequestA.handle() -> JsonParser.parse()
RequestB.handle() -> JsonParser.parse()
~~~

Hot Methods combines `JsonParser.parse` self samples across both `RequestA` and `RequestB`. Call Tree separates the two branches. Inclusive for `RequestA` and `RequestB` only includes samples on their respective branches; inclusive for `JsonParser.parse` in Hot Methods can merge both sets. To decide whether to fix the parser or only optimize `RequestB`, inspect caller distribution, payloads, and per-route SLOs.

### 6.3. A Loop Calling Many Times ≠ "Cost of One Invocation"

A loop calling `decode()` 100,000 times can generate many CPU samples even if each `decode()` is cheap. Sampling profilers do not automatically give exact counts or individual duration **per invocation**. To decide whether to reduce call count, memoize, or optimize the body, add invocation counts, allocation metrics, proper benchmarks, and measure with a realistic workload. "Self 20%" does not tell you whether `decode()` ran 10 or 10 million times.

## 7. CPU Time Differs from Wall-Clock Elapsed Time

This is the most critical boundary when discussing "cost through child calls" in the CPU/JIT module:

- **Wall-clock/elapsed:** time elapsed from call start to finish; can include running on CPU, waiting on I/O, locks, sleep, scheduling, and interference from other threads.
- **Thread CPU time:** actual CPU time attributed by the OS to the thread, excluding most blocked/sleeping time; exact details vary by OS/JVM.
- **Process CPU time:** total CPU consumed by threads in the process; within 1 wall second, more than 1 CPU second can be used across multiple cores.
- **JFR execution samples:** recorded execution stack snapshots per configuration; sample share locates where code runs and **is not itself an exact duration timer**.

Suppose in a 200 ms request:
- 18 ms of CPU computation on the request thread;
- 160 ms waiting on network/DB;
- 22 ms other (queue wait, scheduling, serialization on another thread, or interleaved work).

A CPU flame graph can highlight the 18 ms portion and **not directly show** the 160 ms wait. Attributing 70% of CPU samples to `Parser.parse` does not mean the parser causes 70% of the 200 ms end-to-end latency.

Conversely, in an instrumented wall-time profiler, `Repository.load` shows total 160 ms because of I/O waiting, while `Socket.read`'s self may be huge in wall time. Both reports say "time" yet use **different clocks**. Always state units and source.

### 7.1. Do Not Sum Child Times When Children Run in Parallel

If a method dispatches two tasks concurrently, each taking 80 ms wall time while the parent finishes in 100 ms wall time, the sum of child durations can be 160 ms > 100 ms. The identity "parent inclusive = self + sum of child inclusives" under **non-overlapping wall-clock intervals** no longer holds for parallel work models.

Distinguish:
- **Critical-path latency:** the longest sequential execution chain the user must wait for.
- **Total CPU work:** total CPU across tasks/threads; can exceed wall duration.
- **Sum of child durations:** combined work, which can count overlap and fail to reflect response time.

With `StructuredTaskScope`, `CompletableFuture`, executor pools, and virtual threads, you especially need linked traces/contexts rather than assuming one thread's stack contains all asynchronous work. A JFR stack of one sampled thread does not automatically stitch cross-thread call chains.

### 7.2. Thread State Is a Crucial Filter

HotSpot JFR method profiling via execution sampling favors threads actively executing Java code; threads sleeping, waiting on locks, or blocking on I/O may be underrepresented in CPU-running sample events. To find waiting bottlenecks, inspect wait/park/monitor/socket/file events and distributed traces, not just Hot Methods.

If CPU is low while p99 is high, **do not conclude Java code has no bottleneck** from a sparse flame graph; the application may be waiting on pools, DB, network, disk, or backpressure. Depending on JFR configuration, `NativeMethodSample` and other events may exist; do not merge them with `ExecutionSample` without understanding their semantics.

## 8. JFR and JMC: Know for Sure Which Metric You Are Viewing

### 8.1. Which Data Sources Can a JFR Recording Contain?

A recording may contain:
- `jdk.ExecutionSample`: snapshots of threads executing Java code, with stacks within capture limits.
- `jdk.NativeMethodSample`: certain snapshots related to native code (scope/capture depends on JVM).
- `jdk.CPULoad` and `jdk.ThreadCPULoad`: CPU utilization view over time.
- `jdk.ThreadPark`, `jdk.JavaMonitorEnter`, `jdk.SocketRead`, `jdk.FileRead`, etc.: wait/I/O events **if enabled and above threshold**.
- JIT/classloading/compilation/deoptimization events **if configuration allows**, which can help explain warm-up windows.
- GC events: GC activity, sometimes needing GC logs to interpret pauses/concurrent phases.

This list does not guarantee your file contains all of them. Many events have their own thresholds, periods, filters, and stack trace settings. Without `jdk.ExecutionSample`, you cannot reliably reconstruct a CPU call tree from `jdk.CPULoad` totals alone.

### 8.2. Read Labels and Units Correctly in JMC

JMC versions typically have a Code/Hot Methods/Call Tree area. In each view:

1. Select the recording and time range matching the incident or representative load window.
2. Check thread/event filters: service workers, request threads, background jobs, GC/JIT workers if separated.
3. Check whether columns show **Self** or **Total**, **Samples** or **Estimated time**, and % of the whole view or of the parent.
4. Watch sample count `N`, missing-data warnings, and truncated stacks.
5. For high-total methods, expand children; for high-self methods, inspect leaf stacks and callers.
6. Cross-check with process CPU, thread CPU, RPS, payload, and p99; avoid picking a method caused only by a traffic peak without an actual regression.
7. Record JMC version, view name, `.jfc` settings, and time window when sharing findings.

Not every JMC version uses identical column labels or time interpolation algorithms. Never describe every number in a "Time" column as a method's exact complete execution time when the source is only sampled stacks.

### 8.3. Top-Down and Bottom-Up Are Not Two Different Cost Sets

Top-down groups stacks by caller → callee prefix; bottom-up groups by callee → caller suffix. Both can be generated from **the exact same sample set**, differing only in grouping. If the view-wide total self samples change between the two tabs, inspect filters, stack truncation, grouping, hidden threads, or conversions rather than assuming it is new evidence.

## 9. JIT Inlining and Compiled Code Change What You See

### 9.1. What Is Inlining in a Profiler Context?

The JIT can **inline** a call: the child method's machine code is merged into the caller's compiled code, removing call overhead and enabling further optimizations. The **Java source call graph** still has the logical call, yet machine instruction boundaries no longer necessarily contain an explicit call instruction.

Depending on profiler/JVM/compiler metadata, stack traces may reconstruct **logical inlined frames** to some degree or display differently from source-level stacks. Therefore:

- Do not conclude "method B didn't run" just because B does not appear as a separate frame in one view.
- Do not conclude "caller A used all the CPU" if B was inlined and the tool did not split the frames as expected.
- Do not claim "B self = 0" means B's body executes for free; it may be merged into the caller or lack samples.
- Do not trust every sample's exact line number when compiled-code mapping metadata is incomplete.

**JIT does not invalidate the definitions of self/inclusive**, but makes attribution from machine code back to individual Java methods/lines **dependent on how the tool collects stacks and metadata**.

### 9.2. Warm-Up, Tiered Compilation, and Deoptimization

A method can run in the interpreter, C1, then C2 (depending on HotSpot/compiler flags and conditions), be inlined, deoptimized, or recompiled when profiles change. This affects sample distributions, branch costs, and benchmark results.

When comparing two recordings:

- Do they share the same JDK/vendor, JVM flags, collector, and warm-up state?
- Did startup, lazy class loading, JIT compilation, code cache pressure, or deoptimization happen in one recording and not the other?
- Do they share the same request mix/payload/concurrency, cache state, and CPU quota?
- Is there enough **steady-state** duration, or are you intentionally investigating startup?
- Are classloading/compilation events and logs available to support the explanation?

Do not alter method logic based on 10 seconds of CPU samples taken while the app is still loading classes, then extrapolate to steady state.

### 9.3. Stack Depth and Metadata Limits

If stacks are very deep and recording truncates them, a sample may lose callers near the root or lack metadata on some frames. This lowers an ancestor's inclusive share or splits the call tree into an "unknown" branch. JFR stack depth is configurable (e.g., `FlightRecorderOptions=stackdepth` depending on JDK/version), yet increasing depth increases overhead/storage. Check JDK help/docs and measure overhead before changing production settings.

Do not add JIT diagnostic options "on every service" just for prettier profiles; some flags affect compiler metadata, memory, or code generation. Choose tools/depth per hypothesis and use A/B testing for exact comparisons.

## 10. Turning High Self and High Inclusive into Engineering Decisions

| Self (exclusive) | Inclusive (total) | Initial Interpretation | Next Evidence / Action |
| --- | --- | --- | --- |
| High | High | Method or node executes heavy work in its own body and its branch | Inspect CPU samples/lines, loops, algorithms, allocations, workload |
| Low | High | Method mainly acts as caller/dispatcher; cost concentrates in children | Expand Call Tree; find child hotspots or blocking |
| High | Low | Usually **impossible under the same metric, sample set, and scope**, since inclusive must be ≥ self | Check whether comparing different threads/time ranges, units, recursion grouping, or columns |
| Low | Low | Rarely observed in selected samples | Likely not a CPU priority; may still matter for tail latency/blocked I/O |

When profiling **a call path**, a high-total/low-self node naturally leads you downward into children; however, "drilling down until self is high" is insufficient if the goal is wall-clock latency and the child is waiting on the network. Classify the child's nature before editing code.

### 10.1. Reducing Inclusive Requires Intervening at the Right Place

To reduce `Service.handle`'s inclusive cost, several different options exist:
- Reduce self: improve algorithms running directly inside `Service.handle`.
- Reduce child inclusive: fix `Parser.parse`/`Serializer.encode`/`Repository.query` where cost truly lies.
- Reduce **child call count**: cache, batch, eliminate N+1 queries, coalesce requests, avoid repeated parsing.
- Change call path/parallelism: shorten wall critical path, though this may increase total CPU work or downstream pressure.
- Reduce waiting: address contention, pool saturation, network/DB latency (does not necessarily reduce Java method self CPU).

Choose based on cost type and SLOs, not merely by chasing the word "Total".

## 11. Scenarios That Easily Mislead Profiler Readers

### 11.1. Controller Total 95%, Self 1%

A team sees total 95% and decides to rewrite the controller. Yet the call tree shows 70% of samples go through `Serializer.encode` and 24% through `Crypto.hash`, with the controller body at only 1%. A better decision is to check caller-specific CPU, response size, serialization overhead, and hashing strategy. Only change controller orchestration if it calls children too often or in the wrong places.

### 11.2. Parser Self 40%, Yet Process CPU Is Only 5%

40% **of a small execution sample set** does not mean the parser takes 40% of machine CPU capacity. In a mostly-blocked workload where little CPU is used, the parser can look prominent because other samples are sparse. Before optimizing, check process CPU/quota, sample count, latency traces, and load demand. If p99 is dominated by the DB, optimizing the parser may be negligible.

### 11.3. Framework Dispatcher Inclusive 100%

`Thread.run` or a framework dispatcher typically has total near 100% of samples in the selected thread because it is the ancestor of every execution. This is not a "framework bug." Pick child branches by request/job and look for leaf hotspots or child waits. The dispatcher's self column reveals how often it was sampled as a leaf under the active configuration.

### 11.4. A Recursive Method Appears in Multiple Nodes

Method-level Hot Methods reports 30 inclusive samples, while Call Tree has three recursion nodes with inclusive 30/20/10. Do not add 30+20+10 and claim the method produced 60 independent samples. A single sample can pass through all three nodes. Decide whether to optimize recursion based on self samples, depth, input size, allocation/stack growth, and alternative algorithms.

### 11.5. CPU Is Not High, Yet Requests Are Slow Because of Waiting

`Repository.load` total wall time is 300 ms while CPU sampling self is near 0. There is no contradiction: the thread may be waiting on a database or network. You need JFR socket/file/park/monitor events, distributed tracing, and downstream metrics, rather than adding CPU or rewriting an unrelated Java loop.

### 11.6. Hot Methods Shift After Warm-Up

A appears hot at startup due to classloading/JIT, while B is hot in steady state due to payload parsing. Merging a long recording into one global chart can lead to the wrong conclusion. Split time segments and decide whether you are optimizing cold start or steady-state throughput.

### 11.7. Are Wide GC/JIT Flame Graph Bars Counted in Request CPU?

The JVM runs GC threads, compiler threads, service threads, and native runtime activity. Total process CPU encompasses many components, whereas `jdk.ExecutionSample` has a different scope. You cannot use a Java app-sample call tree to claim the entire process CPU has been attributed across methods. Cross-check `jdk.CPULoad`, `jdk.ThreadCPULoad`, GC logs, and runtime metrics before quoting whole-process CPU shares.

## 12. Hands-On: Reading JFR on JDK 21

The commands below illustrate an environment with JDK tools, an attachable JVM, and valid file read/write permissions. Do not run heavy profiling in production without evaluating overhead first.

### 12.1. Capture a Recording with Execution Samples

~~~bash
java -version
jcmd -l
PID=12345          # Replace with the actual PID of the JVM under investigation
jcmd "$PID" VM.command_line
jcmd "$PID" VM.flags
jcmd "$PID" help JFR.start
jcmd "$PID" JFR.start name=cpu_path_probe settings=profile \
  disk=true duration=2m filename=/var/tmp/cpu-path-probe.jfr
~~~

Explanation:

- `settings=profile` typically provides finer method profiling than `default`, depending on JDK and actual settings; it does not guarantee every event is enabled.
- `duration=2m` is an illustrative **recording** window, not a fixed recommendation for every workload.
- `filename` is a path in the JVM's context, requiring write permission and sufficient space. Verify the recording has actually finished/dumped before opening the file.
- To compare two runs, use **identical settings and windows under matching load**, with proper warm-up; a longer recording does not produce valid ratios if event settings differ.

### 12.2. Verify the File Contains the Needed Events

~~~bash
jfr summary /var/tmp/cpu-path-probe.jfr
jfr metadata /var/tmp/cpu-path-probe.jfr
jfr print --events jdk.ExecutionSample --stack-depth 64 \
  /var/tmp/cpu-path-probe.jfr
~~~

If output is very large, inspect a small sample in a controlled environment, then analyze with JMC or a tool supporting filtering/time ranges. `jfr print` with `--stack-depth` only **limits printed output**, and does not recover frames never saved in the recording.

Minimum checks:
- `jdk.ExecutionSample` count > 0 with useful stack traces.
- Timestamps cover the exact CPU spike/test window.
- Active threads, event types, and settings/periods are appropriate.
- CPU computation is separated from blocked/waiting as required by the problem.
- Do not read event counts from a `settings=profile` run and compare them directly against `settings=default` as if they sampled at the same rate.

If your tool version offers predefined views via `jfr view`, check the list via help before using; view names can change.

### 12.3. Combine CPU and Waiting Events

~~~bash
jfr print --events jdk.CPULoad /var/tmp/cpu-path-probe.jfr
jfr print --events jdk.ThreadCPULoad /var/tmp/cpu-path-probe.jfr
jfr print --events jdk.JavaMonitorEnter /var/tmp/cpu-path-probe.jfr
jfr print --events jdk.ThreadPark /var/tmp/cpu-path-probe.jfr
~~~

The commands print only events present in the file; absence of an event does not prove absence of CPU or waiting. Monitor and park events have their own thresholds and settings. For network I/O, inspect `jdk.SocketRead`/`jdk.SocketWrite` if contained in the recording; compare against request traces, DB/network metrics, and SLAs.

### 12.4. In JMC: Analyze Branch by Branch

1. Select the recording and a time range matching the SLO/test period.
2. In Code/Hot Methods, sort by **self samples/cost** if the view supports it; verify column names and units.
3. Pick a hot method and open Call Tree/Stack Trace; identify **the callers** driving most samples.
4. From key entries/endpoints, walk top-down by **inclusive**, expanding children down to hot leaves.
5. At hot leaves, classify CPU compute vs. blocking/native call; do not ignore waiting and load.
6. Try filtering by request worker threads/jobs if appropriate for the goal; also check other threads.
7. Cross-check process CPU/quota, p99, RPS, GC, allocations, and peak timing.
8. Record sample counts, time range, profiler settings, and parent→child relationships instead of just screenshotting a colored bar.

Tab locations and column names can change across JMC versions; focus on **grouping and semantics**, not specific mouse clicks.

## 13. Java 17+ Example: Computing Self and Inclusive from Synthetic Stack Samples

The standalone program below illustrates the **method-identity aggregation** algorithm. It does not read a `.jfr` file and does not measure CPU itself; input consists of fixed synthetic sample stack groups so calculations are easy to verify. Stacks are written **leaf to root**; each stack has a sample count.

Key point: a frame can appear multiple times in the same stack due to recursion. In method-identity aggregation, the program adds **once per method per sample** when computing inclusive; self takes the leaf frame. This is one consistent definition for illustration, not a claim that every profiler displays recursion identically.

Save as **`MethodCostSamples.java`**:

~~~java
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

public class MethodCostSamples {

    record Sample(long count, String... leafToRoot) {}

    public static void main(String[] args) {
        List<Sample> samples = List.of(
                new Sample(6, "parse", "handle", "run"),
                new Sample(4, "sort", "handle", "run"),
                new Sample(3, "hash", "lookup", "handle", "run"),
                new Sample(2, "handle", "run"),
                new Sample(5, "idle", "run"),
                new Sample(2, "recur", "recur", "run")
        );

        // Values: [0] = self samples; [1] = inclusive samples.
        Map<String, long[]> counts = new HashMap<>();
        long total = 0;

        for (Sample sample : samples) {
            total += sample.count();
            String[] stack = sample.leafToRoot();
            if (stack.length == 0) {
                continue;
            }

            counts.computeIfAbsent(stack[0], key -> new long[2])[0]
                    += sample.count();

            // Deduplicate the same method within one stack (e.g., recursion).
            Set<String> present = new HashSet<>();
            for (String method : stack) {
                if (present.add(method)) {
                    counts.computeIfAbsent(method, key -> new long[2])[1]
                            += sample.count();
                }
            }
        }

        System.out.println("samples=" + total);
        for (String method :
                List.of("handle", "parse", "lookup", "recur", "run")) {
            long[] pair = counts.get(method);
            System.out.printf(
                    Locale.ROOT,
                    "%s: self=%d, inclusive=%d%n",
                    method, pair[0], pair[1]);
        }
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac MethodCostSamples.java
java MethodCostSamples
~~~

Deterministic stdout determined by the fixed input:

~~~text
samples=22
handle: self=2, inclusive=15
parse: self=6, inclusive=6
lookup: self=0, inclusive=3
recur: self=2, inclusive=2
run: self=0, inclusive=22
~~~

Calculation breakdown:
- 6 + 4 + 3 + 2 + 5 + 2 = 22 samples.
- `handle` is in 6 + 4 + 3 + 2 = 15 samples; it is the leaf in exactly 2 samples.
- `lookup` appears on 3 samples where `hash` is the leaf; `lookup`'s self is 0.
- `recur` has two frames of the same name across 2 samples; inclusive by method identity is **2**, not 4. A call-tree path view can still show two nested `recur` nodes.
- `run` appears in every stack: inclusive 22 even though self is 0.

Even with 22 samples, the sum of inclusive across all methods on all rows exceeds 22 because **the same sample contributes to multiple ancestors**. That is a property of call-stack metrics, not a measurement error. The program does not infer wall time, CPU nanoseconds, or how many times methods were called in a real application.

### 13.1. If You Want to Aggregate per Call-Tree Node

Instead of keying by method name, you must use the **full call path** (e.g., `run→handle→lookup`) as the node key. One method can appear in multiple positions; each position has its own self/inclusive. With recursion, two identically named `recur` frames are two distinct nodes on one path. Path-level aggregation must preserve node identity rather than merely deduplicating method names.

Avoid turning a path-level problem into a method-level one by mistakenly summing rows that already contain one another. Converting samples into estimated CPU requires understanding the tool, sampling period/weighting, and measurement limits, not simply multiplying sample counts by an arbitrary constant.

## 14. Decision Example: Optimize Caller or Callee?

Suppose during 10 minutes of peak load:
- `Service.handle` appears in 60% of execution samples and only 2% of samples at the leaf;
- `Json.encode` sits under `Service.handle` with 35% self samples;
- `Cache.lookup` has only 2% self yet 20% inclusive due to `Hash.compute`;
- process CPU is near quota, RPS/payload are stable, and p99 rises.

**How to read this:**
1. High `Service.handle` inclusive: does not prove it is slow itself. Expand children.
2. `Json.encode` self 35%: inspect payload type/size, serialization hot path, allocations, and possible reduction of repeated serialization.
3. `Cache.lookup` inclusive 20% yet self 2%: follow down to `Hash.compute` and check key/data volume, concurrency, and cache design.
4. Confirm CPU quota/throttling: if CPU-saturated, optimizing compute or scaling appropriately is a strong hypothesis. If CPU is not high, look for I/O/waits.
5. Run a controlled comparison benchmark measuring throughput/p99/CPU with identical sampling settings.
6. Do not add 60 + 35 + 20 into 115% CPU: the sample sets overlap along call paths.

The investigation conclusion should be **"the `Service.handle` branch contains most samples; prominent self lies in `Json.encode` and `Hash.compute`"**, not **"it has been proven that `Service.handle` causes all of p99."**

## 15. From Sample Counts to Optimization Opportunities: Additional Evidence

### 15.1. CPU-Bound

When process CPU is high, worker threads are running, sample counts are sufficient, and hot leaf methods align:
- Check algorithm and complexity relative to input size.
- Check boxing, regexes, collections, compression, serialization, and repeated parsing.
- Check JIT warm-up, intrinsics/inlining, allocations, and code paths varying across inputs.
- Use JMH or appropriate benchmarks at the micro level; use end-to-end load tests to confirm real improvement.

**Note:** a faster microbenchmark does not guarantee better service p99 when the bottleneck is network, DB, or queuing.

### 15.2. Waiting / I/O-Bound

When method inclusive wall time is high while self CPU is low:
- Inspect socket/file/lock/park events and thread dumps.
- Compare traces with database/downstream latency, connection pools, rate limits, and retries.
- Look for synchronous fan-out, N+1 calls, timeouts/retries, and backlogs.
- Prioritize reducing roundtrips, bounded concurrency, lifecycle-appropriate caching, or optimizing the dependency.

Changing parallelism can lower wall time yet raise total CPU and pressure. Measure throughput, error rate, resource usage, and downstream SLOs together.

### 15.3. Allocation/GC-Bound

When many samples sit in allocation-heavy code, distinguish:
- Methods creating many objects that are collected quickly without significant pressure.
- Methods creating allocations that raise GC CPU/pause/throughput cost.
- Long-lived objects increasing live set/retention.

Use allocation profiles, GC events/logs, post-GC heap trends, and workload normalization. **High self CPU samples do not prove a memory leak**; object retention requires separate evidence.

## 16. Designing Trustworthy Measurements

### 16.1. Baseline and Candidate Must Be Compared Under Identical Conditions

Record:
- JDK/vendor, JVM flags, GC, JFR settings, sampling interval/stack depth;
- CPU/memory limits, replica/core counts, host contention, and throttling;
- Build version, cache/warm-up state, thread pools, and dependency behavior;
- Requests/s, request mix, payload size, batch volume, concurrency;
- Duration, exact time window, sample count, CPU, throughput, p95/p99, error rate.

A 30-second low-traffic recording and a 10-minute peak recording should not be used to claim "self share doubled" when sample counts are too small or the work mix differs. Normalize per request/byte/job when appropriate and always check **absolute impact**.

### 16.2. Verify Changes on Both Scales

If you optimized `Hash.compute`:
- **Mechanism:** did `Hash.compute` self samples/quantified CPU drop under equivalent workload?
- **System:** did process CPU/RPS, throughput/p99, and error rate improve?
- **Trade-offs:** did memory, allocations, GC, thread contention, or downstream calls rise?
- **Repeatability:** do results hold across multiple runs, not just one outlier?

If self share drops only because total CPU samples in other methods increased, real CPU may not have dropped at all. Evaluate absolute process CPU or work per request rather than relative percentages alone.

### 16.3. Estimating Gains and Amdahl's Limit

If a piece of code accounts for 20% of current CPU work and you make it 2x faster, the upper bound on gain **in a sequential, CPU-bound, fixed-workload model** is:

~~~text
Speedup <= 1 / ((1 - 0.20) + (0.20 / 2))
        = 1 / 0.90
        ≈ 1.11x
~~~

The number 1.11 does not mean system-wide p99 will definitely improve by 11%: systems involve concurrency, waiting, CPU quotas, caches, JIT, downstream bottlenecks, and tail latency. In particular, using a **caller's inclusive share** as the independently speedable fraction overstates gains because many children are unaffected by the change.

## 17. Four Common Pitfalls and How to Fix Them

| Pitfall | Why It Is Wrong | How to Read Correctly |
| --- | --- | --- |
| "Handler total is 90%, must optimize handler body." | Handler wraps the whole branch; self may be low | Expand children and identify the CPU/wait bottleneck |
| "Method B self is 30 ms because there are 30 samples." | Sample count is not an exact millisecond timer | Keep units as samples; correlate with sampling/CPU metrics |
| "Summing all method totals = total CPU time." | Parent/child overlap; recursion/grouping double-counts | Sum over non-overlapping regions or use self within the same scope |
| "Method missing after JIT means it didn't run." | Inlining, stack reconstruction, filters, and sample bias | Check compiled frames and JVM/JIT/recording settings |

Other pitfalls:

- Comparing a `% of node` column against `% of whole file` without checking denominators.
- Comparing method-identity Hot Methods against path-identity Call Tree.
- Attributing p99 wall latency to execution samples without checking I/O, locks, queues, and GC.
- Concluding `self=0` means the method is useless or does no work; it may simply call children or be affected by attribution rules.
- Inferring invocation count from sample count.
- Merging threads with different roles or mixing startup with steady state before calling a hotspot.
- Ignoring overloads, synthetic lambda methods, dynamic proxies, classloaders, and recursion when grouping by name.
- Relying on a flame graph screenshot without time window, sample count, settings, and process CPU metrics.
- Micro-optimizing a tiny self fraction while inclusive is dominated by downstream waits.
- Comparing recordings from two different JDKs/profile settings without accounting for sampling and JIT differences.

## 18. Pre-Conclusion Checklist

- [ ] I identified the data source: instrumented wall time, thread CPU time, process CPU, or JFR execution samples.
- [ ] I understand self as cost attributed to the method/node body, and inclusive as cost including child calls within the respective scope.
- [ ] I know whether I am viewing Hot Methods by method identity or Call Tree by call path.
- [ ] I did not sum parent and child inclusive values into a new total CPU/time.
- [ ] I accounted for recursion and methods called from multiple callers.
- [ ] I checked sample counts, event settings, thresholds, stack depth, and thread/time filters.
- [ ] I checked limits of JIT inlining, compilation, warm-up, and missing frames when relevant.
- [ ] I separated CPU computation from blocking/waiting and end-to-end latency.
- [ ] I correlated method hotspots with process CPU, CPU quota/throttling, GC, RPS, p99, and workload.
- [ ] For high inclusive / low self, I expanded children and located where cost actually concentrates.
- [ ] For high self, I checked algorithms, invocation counts, and realistic achievable benefit.
- [ ] I have competing hypotheses, an equivalent benchmark/load test, guardrails, and a rollback plan.
- [ ] Conclusions reflect the right certainty level: sample observation ≠ exact CPU time measurement ≠ proven root cause.

## 19. Conclusion

The two metrics complement each other:

**Self/exclusive** tells you which method body is directly credited with execution. **Inclusive/total** tells you which call path wraps most of the cost so you can drill down into child methods or trace back up to callers.

For JFR method profiling, most Call Tree/Hot Methods results rely on **sampled stacks**, so prioritize saying "where samples appeared" before claiming "how many milliseconds it took." CPU samples alone do not explain network/lock wait time or tail latency; JIT inlining and stack reconstruction can also alter how methods are displayed.

A reliable diagnostic flow:

**Confirm metric type → select exact thread and time window → inspect self/inclusive → expand call path → distinguish CPU vs. waiting → correlate JFR/OS/APM and load → test one controlled change → re-measure SLOs.**

### References

- Oracle Java 17 — Troubleshoot Performance Issues Using JFR, Code Execution Performance/Call Tree section: https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshoot-performance-issues-using-jfr.html
- Oracle JDK 21 — `jfr` command (`summary`, `metadata`, `print`, `view`): https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html
- Oracle JDK 21 — `jcmd` `JFR.start`/`JFR.check`/`VM.flags`: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Java SE 21 — Java Flight Recorder API/settings: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html
- OpenJDK JDK Mission Control project: https://github.com/openjdk/jmc
