# 1.1 What Is Runtime Diagnostics and How Does It Differ from Source-Level Bug Fixing?

## Objectives

After this lesson, you will be able to explain **runtime diagnostics** in Java applications, distinguish it from **source-based debugging**, choose appropriate evidence for an incident, and move from symptoms to testable hypotheses. The two approaches complement each other; they are not mutually exclusive activities.

## 1. What Is Runtime Diagnostics?

**Runtime diagnostics** is the process of collecting, correlating, and analyzing evidence about a program's behavior **while the program is executing** or from data recorded during execution. For Java, observed behavior comes from multiple layers simultaneously:

- **Code and build:** algorithms, control flow, bytecode, library versions, and deployment artifacts.
- **JVM:** heap, garbage collection (GC), threads, JIT, class loading, and startup arguments.
- **Configuration and data:** system properties, environment variables, feature flags, inputs, and workload.
- **External systems:** CPU, host memory, network, databases, dependent services, containers, and resource limits.

The central question is: **"What actually happened in this run, under these conditions, and what evidence explains the phenomenon?"**

For example, with the exact same source code, a service may respond quickly on a developer machine but slowly in production. The difference may stem from request volume, heap size, GC, database connections, timeout configuration, network latency, or logic bugs that only surface with real data. Reading source code alone is usually insufficient to conclude the cause.

The desired outcome of diagnostics is not merely "having logs," but **an evidence-backed conclusion or hypothesis** that specifies the impact, triggering conditions, whether the cause is confirmed or still suspected, and how to verify the remediation.

## 2. How Does It Differ from Source-Level Bug Fixing?

Here, "source-level bug fixing" refers to an investigation focused on statements, algorithms, variable states, boundary conditions, and program execution paths: reading code, writing tests, using breakpoints, stepping into/over, inspecting the call stack, and modifying logic.

| Criterion | Runtime Diagnostics | Source-Based Debugging / Bug Fixing |
| --- | --- | --- |
| First question | "In the running process, when does the symptom occur, and under what load, configuration, and resources?" | "Which code branch, variable value, or algorithm produces the wrong result?" |
| Starting point | Observed incident: rising errors, increased latency, hung threads, growing heap, crash, environment differences | Failing test, reproducible wrong output, exception tied to a code snippet, conditional/algorithmic bug |
| Common evidence | Logs, metrics, traces, stack/thread dumps, JFR, heap histogram/dump, configuration, build artifact | Source code, unit/integration tests, debugger, variable values, assertions, stack trace |
| Scope | The program **together with** the JVM, OS, resources, input, load, and dependent systems | Primarily program logic and state; may also run the program in a debugger |
| Output | Description of failure conditions, verified cause/hypothesis, impact scope, remediation direction | Code fix and tests proving correct behavior |

**A crucial overlap:** an IDE debugger also observes a running program; a stack trace is both runtime data and a pointer to a source line. The difference lies in **the question being asked and the scope of evidence**, not whether the program is executed. A runtime failure may ultimately still require a code fix; conversely, not every runtime incident is caused by wrong code.

Three examples help distinguish them:

1. A function sums the wrong elements because the loop condition is `i <= count`: inspecting code, writing a test, and fixing the condition is the shortest path.
2. After deployment, p99 latency spikes even though the commit did not change, while GC time or database latency increases concurrently: runtime evidence is needed to locate the bottleneck before choosing to change code, configuration, or infrastructure.
3. A `NullPointerException` appears in production: read the stack trace to narrow down the code, while still identifying what input, data, or configuration change caused that branch to execute.

## 3. Symptoms, Signals, Causes, and Fixes Are Four Different Things

For example, a user reports "the API occasionally takes 4 seconds":

- **Symptom:** slow requests, exceeding the latency target.
- **Signal:** p95/p99 charts spike, a trace records a dependency taking 3.5 seconds, and thread dumps show many threads waiting on I/O.
- **Causal hypothesis:** a slow dependency or a saturated connection pool.
- **Verification and remediation:** correlate timestamps, request IDs, dependency metrics, and pool metrics; adjust or fix the actual cause; re-measure under comparable load.

Do not equate "a thread in WAITING" with "deadlock," or see rising CPU/GC and assume it is the root cause. **Time correlation only helps generate hypotheses**; additional evidence or controlled experiments are required to confirm.

A **stack trace** shows the call path leading to the point where an exception was thrown, but the line that throws the exception is not necessarily where the fault began: invalid input or invalid state may have been created in an earlier step.

## 4. What Evidence Should You Collect in Java?

| Source | What Question Does It Answer Well? | Limitations to Remember |
| --- | --- | --- |
| **Application logs** (timestamp, level, request/correlation ID, stack trace) | Which request failed, how far did the business flow get, what exception occurred? | Missing context or asynchronous logging can mislead; avoid logging sensitive data |
| **Metrics** (error rate, throughput, p95/p99, CPU, heap, GC, threads/pools) | When did the incident start, how widespread is it, how does it change with load? | Aggregated metrics alone do not point to the faulty line of code |
| **Distributed tracing** | In which step and service was time spent for a request? | Requires trace context propagation; sampling can miss requests |
| **Thread dump / `jcmd Thread.print`** | Where are threads RUNNABLE, BLOCKED, or WAITING; are there signs of lock contention or deadlock? | Only a point-in-time snapshot; multiple samples are usually needed to see trends |
| **JDK Flight Recorder (JFR), profiler, GC logs** | Where is CPU being spent, how are allocation/GC and certain JVM events behaving? | Recording duration, observation overhead, and sample representativeness all matter |
| **Heap histogram / heap dump** | Which object types occupy space and what references keep them alive? | Heap dumps can be large and contain sensitive data; collect only when authorized and necessary |
| **Build, JDK, JVM flags, configuration, dependencies** | Are two environments actually running the same artifact/conditions? | "Same source" does not guarantee "same binary, flags, input, and dependencies" |

Choose tools based on the symptom. For instance: investigate timeouts starting with error rate, latency, traces, and dependency health; investigate hangs/locks starting with thread dumps; investigate sustained heap growth starting with post-GC heap charts and allocation rate before deciding whether a heap dump is needed.

Record **timestamps with timezone**, impact scope, service/instance, build version, and the failure time window. "Before-and-after" comparisons must keep load and input conditions sufficiently comparable.

## 5. Java 17+ Example: Same Source Code, Different Runtime Behavior

The following example **simulates a timeout decision** based on provided configuration and processing time. It does not perform a network call, measure a real clock, or create a real timeout; its purpose is to prove that you must inspect the values **actually used at runtime** before blaming the algorithm.

Create the file `RuntimeDiagnosisDemo.java`:

```java
public class RuntimeDiagnosisDemo {
    public static void main(String[] args) {
        int timeoutMs = Integer.parseInt(
                System.getProperty("app.timeout.ms", "100"));
        int downstreamMs = Integer.parseInt(
                System.getProperty("downstream.duration.ms", "80"));

        System.out.printf("timeout=%dms, downstream=%dms%n",
                timeoutMs, downstreamMs);

        if (downstreamMs > timeoutMs) {
            System.out.println("KET_QUA=TIMEOUT");
        } else {
            System.out.println("KET_QUA=OK");
        }
    }
}
```

Compile once with JDK 17 or higher:

```bash
javac RuntimeDiagnosisDemo.java
java -Dapp.timeout.ms=100 -Ddownstream.duration.ms=80 RuntimeDiagnosisDemo
```

Exact stdout:

```text
timeout=100ms, downstream=80ms
KET_QUA=OK
```

Keep the `.java` and `.class` files unchanged, and only change the JVM property passed in:

```bash
java -Dapp.timeout.ms=100 -Ddownstream.duration.ms=180 RuntimeDiagnosisDemo
```

Exact stdout:

```text
timeout=100ms, downstream=180ms
KET_QUA=TIMEOUT
```

**Analysis:** the same code produces different outcomes because `downstream.duration.ms` differs. The diagnostic step is to check which configuration, input, and runtime measurements changed; depending on the cause, the fix may be adjusting configuration, optimizing the dependency, or fixing timeout-handling logic. If you only open an IDE looking for a "wrong" line in the `if` statement without checking actual runtime values, you may fix the wrong place.

In a real service, do not use simulated values to conclude a timeout. Measure real latency with instrumentation/tracing and compare it against the timeout of the right client, while also accounting for queueing, retries, and deadlines. This example uses system properties for easy execution and reproduction; a real application also needs to validate configuration values.

## 6. Counterexample: Logic Bug in Source Code

The problem is to sum the **first `count` elements** of an array. Create the file `SourceLogicBugDemo.java`:

```java
public class SourceLogicBugDemo {
    static int sumFirst(int[] values, int count) {
        int sum = 0;
        for (int i = 0; i <= count; i++) {
            sum += values[i];
        }
        return sum;
    }

    public static void main(String[] args) {
        System.out.println(sumFirst(new int[]{2, 3, 5}, 2));
    }
}
```

Run:

```bash
javac SourceLogicBugDemo.java
java SourceLogicBugDemo
```

Stdout:

```text
10
```

The correct result per specification must be `5` (`2 + 3`). A debugger or a small unit test will reveal that the loop included an extra `values[2]`. Fixing the condition to `i < count` (and in real code, validating `0 <= count <= values.length`) then recompiling/rerunning will print `5`.

Here, the evidence is clear and reproducible with fixed input: **fixing the source logic and adding a regression test** is the primary solution. Adding CPU, heap, or thread dump dashboards will not help find the `<=` bug any faster.

## 7. Practical Diagnostic Workflow: From "Slow" to Root Cause

1. **Define the phenomenon and impact.** Describe what is wrong, when it started, frequency, affected requests/instances, and severity. Distinguish "rising 500 errors" from "users experiencing slowness."
2. **Freeze the comparison context.** Record build/version, JDK/JVM, relevant configuration, load, input, dependencies, deployment region, and recent changes near onset. Synchronize timezones/timestamps.
3. **Select signals by hypothesis.** For example: timeout → traces, latency, connection pools, and dependencies; crash → exceptions, exit reason, JVM/OS logs; hang → thread dumps and lock state; memory → heap/GC/allocation.
4. **Isolate and verify.** Use request IDs to link logs/traces; compare failing instances with healthy instances; form a falsifiable hypothesis. Test in a controlled environment or reproduce with the same input/configuration if appropriate. Only attach a debugger or take dumps when needed and safe to do so.
5. **Fix the right layer and re-measure.** Fix code with a regression test if it is a logic bug; fix configuration/dependency/resources if evidence points there. Compare metrics/errors/latency against baseline under equivalent conditions, monitor side effects, and record the conclusion.

Example investigation of "slow requests":

```text
Symptom: p99 /checkout increases from ~250 ms to ~4 s
    ↓
Metrics: errors concentrated in a specific time window and group of instances
    ↓
Trace: most of the time is spent inside a database call
    ↓
Correlation: connection pool saturates at the same time query volume increases
    ↓
Hypothesis: available connections cannot meet the load
    ↓
Verification: measure pool wait time + active connections in use,
              compare under equivalent load
    ↓
Action: fix the appropriate cause, then monitor p99 and error rate
```

This is an **illustrative scenario**, not a default conclusion that every slow request is caused by the pool. A trace showing time spent in the database also does not prove whether the query, locks, network, or pool is the ultimate cause.

## 8. When to Start with Runtime vs. When to Start with Source?

- **An incident on a running environment; hard to reproduce; occurs only under load or on a subset of instances:** start from runtime observation and environment conditions, then inspect the source of the suspected code path.
- **A failing unit test, an algorithm consistently returning wrong results on small inputs:** start from the specification, test, and source code.
- **An exception with a stack trace:** use the trace to locate the code path while verifying the input/state that led to the exception; do not conclude based solely on the final line.
- **A bug that appears only after deployment:** compare artifacts, JDK, flags, configuration, dependencies, data, and load, even when the source diff is small.
- **An incident with no exceptions:** still inspect metrics, traces, thread states, and wait times; slowdowns, contention, or leaks can occur without throwing an exception.

A useful rule: **If you do not yet know "what the system is doing," observe runtime first. If you already have a reliable reproduction pointing to faulty logic, inspect source/tests first.** In complex incidents, moving back and forth between the two approaches multiple times is normal.

## 9. Common Mistakes and How to Avoid Them

- **Confusing symptoms with causes:** a "large heap" does not by itself prove a memory leak; "many WAITING threads" does not by itself prove a deadlock. Build a chain of evidence and verify.
- **Reading source alone and guessing production:** you can miss JVM flags, configuration, load, network, data, and dependencies. Verify actual execution conditions.
- **Looking at a single snapshot:** CPU, a thread dump, or heap at one moment may not be representative. Check trends and multiple samples when needed.
- **Adding logs indiscriminately:** verbose logging creates noise, adds overhead, and can leak tokens or personal data. Prefer request IDs, structured context, sampling, and redacting sensitive data.
- **Enabling profilers/dumps without caution:** diagnostic tools also consume resources; heap dumps can be large and sensitive. Choose appropriate timing/scope, manage access permissions, and store safely.
- **Fixing before establishing a baseline:** without before-and-after measurements, it is hard to know whether a change fixed the true cause or only masked the symptom.
- **Not adding tests after finding a code bug:** the bug can return. Keep a regression test with the exact triggering input/conditions.

## 10. Self-Check Questions

1. The same Java artifact runs fine on staging but times out in production. Which conditions and signals would you record **before** modifying the algorithm?
2. A stack trace points to a `NullPointerException` on line 42. Why might line 42 only be where the error manifests, rather than the root cause?
3. In the `RuntimeDiagnosisDemo` example, what actually changed between the two runs? Why does this illustrate the need to read runtime configuration?
4. In the `SourceLogicBugDemo` example, what does a test with input `[2, 3, 5]` and `count = 2` prove that a JVM dashboard cannot prove directly?
5. If p99 drops after a change, what additional conditions must be checked to avoid confusing correlation with causation?

**Key takeaway:** runtime diagnostics uses evidence from a program under its execution conditions to find *what happened and why*; source debugging digs into code logic and state to find *which line or branch creates wrong behavior*. Choose your starting point based on the symptom and continuously verify hypotheses with appropriate evidence.