# 19.1. When You Need a Debugger to Inspect State That Logs or Profilers Cannot Explain

## Learning Objectives

After this lesson, you will be able to:

- Decide **when to use a debugger** instead of adding more logs, running a profiler, or taking a thread dump.
- Distinguish **evidence about state and control flow** (debugger), **event progression** (logs/traces), **cost statistics** (profiler/JFR), and **thread snapshots** (thread dump).
- Use breakpoints, conditional breakpoints, exception breakpoints, call stack, variables, watches, and **Step Into / Over / Out** to find the root cause of a broken invariant.
- Reproduce and analyze a Java 17+ bug where the final output shows an incorrect result without indicating **which intermediate variable** was used incorrectly.
- Understand the limitations when debugging multithreaded systems, virtual threads, and production applications: **pausing can alter timing**, cause artificial timeouts/deadlocks, disrupt service, or create security risks if JDWP is exposed.

The focus is not "how to click every button in a specific IDE," but rather **choosing the debugger at the right time and using it to ask questions about program state**. Menu names in IntelliJ IDEA, Eclipse, and VS Code Java Debugger may differ, but the principles are equivalent.

## 1. One Problem, Four Different Ways to Observe It

When an application behaves incorrectly, diagnostic tools do not all answer the same question.

| Tool | Typically answers well | Typically cannot prove directly |
|---|---|---|
| **Structured logs** | What events the system recorded, when, and with which request/correlation ID; which logged branch was taken | The exact value of a local variable **at an unlogged line**, or where a variable was just overwritten |
| **Metrics, tracing** | Error rates, latency, throughput; which services/spans a request traversed | The full object graph/branches inside a Java stack frame |
| **Profiler, JFR, CPU/allocation profiles** | Which stacks consume CPU, whether allocation/GC/lock/I/O increased; trends over a time window | Why **a field holds a wrong value** if that operation is very fast, rare, and has no matching event |
| **Thread dump** | Which threads are running/waiting, stacks, and lock/deadlock indicators at sample time | Most local values and step-by-step state transitions |
| **Debugger** | At a pause point: local variables, fields, parameter values, object identity, call order, conditional branches, and the **specific** call stack | The overall performance picture when breakpoints alter timing; data that disappeared before pausing |

**Selection rule:** When the question is still **"which part consumes CPU / waits on I/O / allocates heavily?"**, prefer a profiler, JFR, and metrics. When the question shifts to **"why did this request take this branch, and why does this object hold this value at this moment?"**, a debugger is usually more valuable.

A debugger works by **pausing or conditionally observing** a JVM. Values shown in the IDE represent **state at the observation point**; it does not automatically provide full prior history unless you placed breakpoints/watchpoints or recorded data beforehand.

### Example of a Signal That Is Not Enough to Conclude

Suppose logs show:

```text
checkout request=EDGE finished payable=-500
```

The log confirms **the output is wrong**. A CPU profiler may report no hotspot because the calculation only takes a few microseconds. Yet the remaining questions are: **From which parameter was the negative `payable` value computed? Was a field normalized or not? Who called the method?**

This is a scenario suited for a debugger: pause **before the assignment**, inspect values **at the exact same moment**, then step to see which statement breaks the invariant.

## 2. Signs You Should Switch to a Debugger

### 2.1. An Invariant Is Violated, but Logs Do Not Show Intermediate State

An **invariant** is a condition that must always hold within a business/model scope, for example:

- `payableCents >= 0`.
- `payableCents + appliedDiscountCents == subtotalCents`.
- An order in `PAID` status must have a confirmed transaction.
- An object is processed under a consistent tenant/session.

When only the final result is logged, you know **the invariant is broken**, but not **at which assignment line** it broke. Placing breakpoints before and after state changes is a direct way to observe the state transition.

### 2.2. A Conditional Branch Executes Differently Than Expected

For example, `if (user.hasPermission())` enters the allow branch while the user is denied elsewhere. This can happen because:

- The `user` object is different from the object you think it is.
- Roles/feature flags/configs were loaded from another source or at another time.
- A boolean expression has `&&`/`||` short-circuiting or `null` values handled under a different convention.
- The condition is checked **before** state is updated.

A debugger lets you see **input arguments, operand values, the actual instance, the caller, and the executing line**. A log containing only `allowed=true` cannot prove all of those hypotheses.

### 2.3. A Value Is Modified Somewhere Along a Call Chain

An object field is correct at the start of a request, but wrong at the end. Many setters, callbacks, mappers, or consumers are involved, and grepping logs fails to pinpoint the modification.

This is when to use a **field modification watchpoint** (if supported by the debugger/JVM) or breakpoints at write sites. A watchpoint pauses when the field is assigned, identifying **the actual stack/caller causing the change**; do not confuse it with a local-variable watch in the UI that only displays values. Watchpoints can be very expensive on frequently updated fields.

### 2.4. An Exception or Error Only Appears Through a Rare Path

When an exception is caught, wrapped, and logged only at a high layer, the final call stack may lack the state where the error was **first thrown**. An **exception breakpoint** (caught/uncaught depending on the case) pauses near the throw site to inspect related variables, conditions, and stacks.

Filter by exception class or context; pausing on **every exception** can create massive noise because some frameworks use exceptions in normal execution paths.

### 2.5. A Bug Reproduces with Specific Data, but the Profiler Shows Nothing

Very fast logic bugs (wrong rounding, using a stale variable, comparing the wrong ID, miscalculating money, wrong update order) usually **do not consume CPU**. Having no "hot method" does not mean the application is correct. A test with stable input and a breakpoint near the invariant can save time compared to capturing more profiles.

**Priority condition:** it can be reproduced in a development/test environment with known input, state close enough to production, and without touching sensitive data. If the bug only happens rarely under load, collect evidence first and then decide whether a debugger would make the bug disappear.

## 3. When Should You Not Use a Debugger Yet?

A debugger is not the first step for every incident.

| Situation | Tool to prioritize first | Reason |
|---|---|---|
| 100% CPU, slow application, unknown method | JFR/CPU profiler, per-process/thread CPU | Breakpoints distort execution time and are hard to place without a hypothesis |
| Memory footprint growing over many hours | Heap histogram/dump, JFR allocation, NMT/OS metrics | Inspecting one object at one breakpoint does not reflect retained memory or native usage |
| Service hung, thousands of threads waiting | Thread dump/JFR Locks/I/O | Pausing the JVM further can worsen the symptoms |
| Errors occurring across millions of requests, different each time | Structured logs, correlation IDs, metrics, sampling traces | Debugging individual requests does not scale and may alter load |
| Race condition occurring only under contention | Stress/reproduction tests, JFR/thread dumps, verified synchronization | Breakpoints can skew thread ordering, making the bug vanish or creating a new scenario |
| Production serving customers, pausing not permitted | Non-intrusive evidence first | "Suspend all threads" can cause timeouts, lock stalls, and SLO violations |
| Issue in native code/JNI | Native debugger, native profiler, JVM crash logs | A Java debugger does not necessarily see underlying C/C++ state |
| Logs with stack + sufficient state already prove the cause | Regression test and bug fix | A debugger may not add any necessary evidence |

**Effective decision pattern:** Observe externally → form a specific hypothesis → attempt to verify with low-intrusion logs/tests/JFR → use a debugger if **state at a specific execution point** is still missing → fix and re-verify with tests, not just a debug session.

## 4. What Does a Debugger Observe When the JVM Is Paused?

A breakpoint at a line can show you:

1. **Line and source location:** the exact position where the JVM can pause, along with the loaded class/method; requires source matching the running bytecode.
2. **Local variables:** parameters, temporary variables, and values in the selected frame, if debug information is available and provided by the debugger/JVM.
3. **Object fields:** `this`, fields within the object, referenced objects, `null` values, collections/maps (with the risk that rendering may invoke code).
4. **Call stack:** which method called the current method, along with values and context of each live frame.
5. **Threads:** which threads are suspended, which are still running; thread state and locks can help inspect concurrency status.
6. **Control flow:** which branch execution will follow next when you Step Over or Step Into.

### Distinguishing Step Over, Into, and Out

- **Step Over:** executes the current line (including method calls if any) and pauses at the next appropriate line in the current frame. Use when you already know child methods are not suspect.
- **Step Into:** enters the called method, if the debugger has source and stepping settings allow it. Use to trace where a condition or data is computed incorrectly.
- **Step Out:** continues until exiting the current method and returning to the caller. Use to compare the child method's result with the caller's state.
- **Resume/Continue:** runs until the next breakpoint/exception; it does not mean running just one more line.

**Do not Step Into every method**; framework code, lambdas, JDK internals, and dozens of auxiliary calls will make you lose your bearings. Start from the invariant and relevant variables, and dig deeper when you have evidence.

### Evaluate Expression and Side Effects

Many IDEs have **Evaluate Expression** to compute expressions on objects/locals. Be careful: evaluating `object.toString()`, calling lazy getters, querying a DB, reading an iterator, or calling methods with side effects can **execute real code inside the JVM**, mutate state, or cause deadlocks when threads are suspended.

Prefer **inspecting primitive fields/locals directly**, and only evaluate pure expressions when you understand side effects. Do not modify variables in a debug session to "prove it's fixed" and skip regression tests; that is a temporary experiment, not a patch.

## 5. Breakpoint Types to Use for the Right Situation

| Type | Suitable for | What to watch out for |
|---|---|---|
| **Line breakpoint** | Pausing before a specific assignment, condition, or method call | The line may run very frequently; pauses the JVM |
| **Conditional breakpoint** | Pausing only for a specific request ID, abnormal value, or instance | The condition expression is evaluated many times; adds overhead and must have no side effects |
| **Exception breakpoint** | Pausing when an error is thrown, even if a framework catches and logs generically | Pausing on "normal" exceptions causes noise; filter by class/path |
| **Field access/modification watchpoint** | Finding the call site reading/writing a field that changes unexpectedly | Can incur heavy overhead; a local variable is not a field watchpoint |
| **Method breakpoint** | Unknown line, but wanting to observe method entry/exit | Frequently called methods can be extremely expensive; a line breakpoint is sometimes better |
| **Non-suspending logpoint/tracepoint** | Collecting a value conditionally without pausing | Still has overhead; logpoint expressions can execute code and leak data |

A **conditional breakpoint** is useful when a method is called 100,000 times but only one case fails: pause when `invoice.id.equals("EDGE")` or `requestedDiscountCents > subtotalCents` instead of pausing every time. The condition must **not mutate state** and must be cheap to evaluate.

A debugger can choose **Suspend: All threads** or **Suspend: Thread** depending on the IDE/JVM. "All" gives a more synchronized snapshot but stops the whole process; "Thread" reduces impact on other threads, but those other threads **continue mutating shared state** while you inspect. This choice can determine whether the observed result remains meaningful.

## 6. Java 17+ Hands-On: Logs Show Wrong Output, Debugger Finds the Faulty Line

Scenario: an invoice has `subtotalCents`, a coupon requests a discount amount, and the system must **cap the discount so it does not exceed subtotal**. The invariants are:

```text
0 <= appliedDiscountCents <= subtotalCents
payableCents >= 0
payableCents + appliedDiscountCents == subtotalCents
```

The program has a tiny bug: the `appliedDiscountCents` field is capped properly, but the `payableCents` calculation uses **the requested value before capping**. A profiler may see nothing unusual because the calculation takes almost zero CPU.

### 6.1. Complete Source Code

Create the file **`DebuggerStateDemo.java`**:

```java
public class DebuggerStateDemo {
    private static final class Invoice {
        private final String id;
        private final int subtotalCents;
        private int appliedDiscountCents;
        private int payableCents;

        Invoice(String id, int subtotalCents) {
            this.id = id;
            this.subtotalCents = subtotalCents;
            this.payableCents = subtotalCents;
        }

        void applyCoupon(int requestedDiscountCents) {
            int capped = Math.min(Math.max(0, requestedDiscountCents), subtotalCents);
            appliedDiscountCents = capped;
            payableCents = subtotalCents - requestedDiscountCents;
        }

        boolean valid() {
            return payableCents >= 0
                    && payableCents + appliedDiscountCents == subtotalCents;
        }

        void printSummary() {
            System.out.printf("%s subtotal=%d discount=%d payable=%d valid=%s%n",
                    id, subtotalCents, appliedDiscountCents, payableCents, valid());
        }
    }

    private static void checkout(Invoice invoice, int couponCents) {
        invoice.applyCoupon(couponCents);
        invoice.printSummary();
    }

    public static void main(String[] args) {
        checkout(new Invoice("NORMAL", 1000), 250);
        checkout(new Invoice("EDGE", 1000), 1500);
    }
}
```

### 6.2. Compile and Run Normally

Use JDK 17 or later; the `-g` option embeds local-variable/source info into `.class` files so the debugger can display them better:

```bash
javac --release 17 -g DebuggerStateDemo.java
java DebuggerStateDemo
```

**Exact stdout** of the buggy version:

```text
NORMAL subtotal=1000 discount=250 payable=750 valid=true
EDGE subtotal=1000 discount=1000 payable=-500 valid=false
```

The output shows `EDGE` is wrong, yet does not reveal **why discount is stored as 1,000 while payable subtracted 1,500**. This is the gap the debugger fills with local and field values at the assignment.

### 6.3. Set the Breakpoint at the Right Spot

Open `DebuggerStateDemo.java` in an IDE with a Java Debugger and run via **Debug**, not Run. Inside `Invoice.applyCoupon`:

1. Set a **line breakpoint** on `payableCents = subtotalCents - requestedDiscountCents;`.
2. Add a **condition** `requestedDiscountCents > subtotalCents` to pause only on the abnormal case; the IDE can also filter by `id.equals("EDGE")`.
3. When paused, select the `applyCoupon` stack frame, and open **Variables** or **Evaluate** using only read-only expressions.
4. Observe before executing the buggy line:
   - `id = "EDGE"`.
   - `subtotalCents = 1000`.
   - `requestedDiscountCents = 1500`.
   - `capped = 1000`.
   - `appliedDiscountCents = 1000`.
   - `payableCents = 1000` **before the assignment** (value from the constructor).
5. Choose **Step Over** one line: `payableCents` becomes **-500**.
6. Check the **Call Stack**: `main() → checkout(...) → Invoice.applyCoupon(...)`. The caller passed `1500`; the bug is not data loss in the logger, but that the method used **the wrong variable**.

**Remember:** a line breakpoint normally pauses **before** the current line executes. If you see a field has not changed yet, check the highlighted line and step once; do not assume a statement already ran while it is still pending.

### 6.4. Fix the Bug and Verify the Invariant

Change **only** the line using the wrong variable:

```java
payableCents = subtotalCents - capped;
```

This is a **one-line fix in `Invoice.applyCoupon`**, not a standalone program. After fixing, the same two inputs produce:

```text
NORMAL subtotal=1000 discount=250 payable=750 valid=true
EDGE subtotal=1000 discount=1000 payable=0 valid=true
```

The lesson more important than fixing a subtraction: the debugger proves **exact state before/after an assignment**, on the exact input, exact instance, and exact call path. Next, add **unit tests** for coupons smaller than, equal to, and greater than subtotal, as well as negative coupons (if business rules permit). When handling money in real applications, specify integer cents/valid decimal units, overflow, currency, and dedicated refund rules rather than over-generalizing a simple example.

## 7. Debugging with an IDE and jdb/JDWP: Two Ways to Observe the Same JVM

### 7.1. Using an IDE When You Have Source Code and a Reproducible Input

Practical workflow:

1. Open the right project/commit and ensure the running bytecode matches the source in the IDE.
2. Run the test or application in **Debug mode** with the reproducible input; place breakpoints where an invariant could break.
3. Choose **conditional breakpoints** to skip normal requests.
4. When paused, inspect **Parameters → Locals → Fields → Call Stack** first, before doing Step Over/Into.
5. Record the concrete state: "before assignment, capped=1000 but calculation used requested=1500."
6. Fix the code, run regression tests without the debugger, and confirm logs/metrics return to normal.

If source mismatches the build, breakpoints may not hit, jump to other lines, or locals may not display fully. Check jars/classpath, source maps/symbols, compiler options, and optimizations; `javac -g` is helpful for the Java examples in this lesson.

### 7.2. JDWP and the Command-Line Tool jdb

The Java Platform Debugger Architecture (**JPDA**) comprises components that allow a debugger to control/observe a JVM; the **JDWP** protocol connects the debugger with the debuggee. The JDK includes `jdb`, a CLI debugger. With the compiled example, in the **first** terminal run the local JVM waiting for a debugger:

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005 DebuggerStateDemo
```

In a **second** terminal on the **same machine**:

```bash
jdb -attach 127.0.0.1:5005
```

`suspend=y` means the JVM pauses at startup until a debugger connects; useful for startup bugs, but unsuitable if you want the process to serve requests immediately. `suspend=n` lets the application run without waiting for a debugger, though you may miss a bug that occurs too early.

Example JDB operations in an **interactive session** after attaching and pausing at a breakpoint:

```text
help
where
locals
print this.subtotalCents
print this.payableCents
next
cont
```

These are **illustrative interactive commands**, not program stdout; `where`/`locals` require **a suspended thread and selected frame**. To create a method breakpoint, JDB has `stop in FullyQualifiedClass.method`; for nested classes, the bytecode name contains `$` (for example `DebuggerStateDemo$Invoice.applyCoupon`). You can use `stop at Class:line` if you know the line number in the current file. For complex conditions/correlation IDs, an IDE debugger is usually more convenient than JDB.

**Never expose JDWP to the Internet or public networks.** A debugger can control execution and modify JVM state; JDWP must not be treated as an application API with secure authentication and encryption. The example binds only to **127.0.0.1** for local practice. When remote debugging is necessary, use a dedicated permission-controlled environment, secure tunneling/access control, and allow only approved personnel; close the port immediately when done. Do not copy `address=*:5005` into production.

## 8. Major Limitations of Debuggers in Multithreaded Systems

### 8.1. "Pausing" Alters the Process Being Observed

When pausing a thread:

- Other threads can keep updating shared fields, causing state to change while you inspect.
- If the paused thread holds a `synchronized` monitor/lock, other threads may wait on it, creating **artificial hangs/timeouts**.
- When choosing **Suspend All**, the whole JVM stops; external clients/networks do not pause with it, so timeouts/retries can spike.
- Time spent paused is not counted like a normal run; latency/throughput benchmarks during a breakpoint session are usually **unreliable**.

A race bug can **disappear** because a breakpoint alters interleaving, or a new bug can appear because the environment is held at an unnatural point (the *Heisenbug* phenomenon).

### 8.2. Use Less Intrusive Tools for Concurrency First

For contention or thread-ordering bugs, start with:

- Thread dumps, JFR thread/lock events, and timelines.
- Counters/structured logs with appropriate correlation and timestamps.
- Stress tests reproducing the right pool size, data, timing, and contention.
- Tests for invariants/linearizability or synchronization/visibility when needed.

After narrowing the scope, you can debug a specific thread/case. Do not infer **"I saw the right value while paused"** means there is no data race; the debugger may accidentally provide an extra synchronization point or alter scheduling.

### 8.3. Virtual Threads and Async Callbacks

In Java applications using virtual threads or `CompletableFuture` chains, one request does not necessarily correspond to a fixed OS thread. Modern debuggers/JDI support virtual threads, though how threads are listed/breakpointed depends on JDK and debugger versions; per Java 21 JDB documentation, the debugger may **not list all virtual threads by default** to avoid overload. Do not treat a thread list missing a virtual thread as proof that the task does not exist.

For async flows, the current call stack may **not contain the full history** before the callback was scheduled. Use correlation IDs, IDE async stack support (if available), structured traces, and event logs to supplement context.

## 9. Diagnostic Workflow When "Logs/Profilers Have Not Explained It"

To avoid wandering into hours of random stepping, use a repeatable workflow:

### Step 1 — Describe the Failure in a Verifiable Form

Instead of "checkout fails occasionally," write: "with subtotal=1000, coupon=1500, `payable` must be 0, but actual is -500." Record input, expected, actual, code version, and environment.

### Step 2 — Use Existing Data to Narrow Where to Set Breakpoints

Read logs, traces, and exception stacks; use a profiler/JFR if the symptom is **cost**. Do not add 20 breakpoints where you have no hypothesis. Find **the first broken invariant**: where is state created, transformed, or written?

### Step 3 — Build a Reproducible Test Without Harming Real Data

Create a unit/integration test or safe local fixture. Replace external services with reasonable stubs if the bug does not depend on networking; keep edge data, feature flags, and necessary task ordering intact. Avoid real tokens/PII on debug screens or screenshots.

### Step 4 — Choose Filtered Breakpoints

For example, pause in the coupon-applying method only when `requestedDiscountCents > subtotalCents`; for multi-user requests, use a request ID (if passed within that scope). Avoid pausing a million times through a hot loop.

### Step 5 — Capture State in a Structured Way

At the pause point, record:

- Which **method/line**, commit/build, and frame are active?
- What are the actual inputs/parameters? Is `this` the right instance/tenant?
- Which fields/locals are the **source of truth**, and which variables are transformed values?
- Which condition drives the next branch; is the boolean result right?
- Who called this method? Could the same method be called again from another caller?

### Step 6 — Step Across One Change and Compare the Invariant

Compare **before** and **after** an assignment, method call, or branch. If the invariant holds before the line and breaks after it, you have strong evidence. If it was already broken **before entering the method**, Step Out/call stack is not enough: place breakpoints **earlier in the caller or at write sites**.

### Step 7 — Verify the Fix Outside the Debugger

Fix the code and run tests without pausing; rerun edge inputs multiple times under appropriate load. If performance is affected, measure with a profiler/JFR **without breakpoints enabled**. Base conclusions on invariants and tests, not on temporarily assigning the right value with Evaluate.

## 10. Real-World Java Scenarios for Choosing a Debugger

| Situation | What logs/profiler are showing | What to use the debugger to learn | Additional verification |
|---|---|---|---|
| **Wrong value after a very fast calculation** | Logs record result, profiler shows no hotspot | Where a variable was normalized, which variable the calculation used | Boundary-case unit tests |
| **Entered an "impossible" branch** | Logs only record branch name | Boolean operands and actual config/identity | Tests for condition combinations |
| **A field gets overwritten** | Earlier log is right, later log is wrong | Watchpoint finds exact call site and thread modifying field | Test side effects, ownership, and invariants |
| **An exception is swallowed/wrapped** | Final stack only points to controller/framework | Exception breakpoint at first throw, locals and frame | Failure-path tests |
| **Stale cache within a request** | Cache hit metrics look normal, but data is wrong | Key, entry version, tenant context, state in cache and caller | Invalidation/freshness tests |
| **Bug only happens with multiple threads** | JFR lock/time, logs hard to reconstruct order | Per-thread state around suspect point, *if pausing does not mask bug* | Stress test/JFR/thread dump as primary evidence |
| **Hot method using high CPU** | CPU profiler already found the call stack | Debugger helps inspect concrete input triggering expensive algorithm branch | JMH/load test verifies performance, never breakpoint timing |
| **Bug in production not yet reproducible** | Traces/logs have correlation, lack full state | Do not attach yet; gather safe evidence/fixture first | Conditional instrumentation, sanitized reproducible test |

### Three Examples Where "Adding More Logs Is Not Always Better"

**Case A — State comes from a different object.** Logs say `userId=42`, yet the method is called with an old session object that also has `userId=42`. The debugger inspects `this`, version fields, instance identity, and frames, showing the input holds **stale state**. Conclusions rely on identity/state, not just the same ID string.

**Case B — Feature flag changed before the check.** Logs only record "flag enabled." A conditional breakpoint pauses at the branch and discovers the effective configuration at request time differs from the configuration logged at startup. Timestamps and tenant/environment/config revisions must be compared; the debugger gives current state, while logs help explain history.

**Case C — A field is updated twice.** Code computes the right amount, yet a later callback overwrites it. A watchpoint/breakpoint on the setter reveals the second write along with its call stack; the final log alone cannot tell which write caused the bug. Fix with ownership/state-transition rules or remove the side effect, then add a regression test.

## 11. Common Mistakes and Safety Limits

1. **"Profiler shows no hotspot means there is no bug."** False: logic bugs can execute very quickly.
2. **"Logging every line will solve it."** Not necessarily: heavy logging increases I/O/CPU, leaks sensitive data, and can alter timing. Targeted logs with correlation are usually better.
3. **"A breakpoint gives full history."** False: a breakpoint gives a snapshot; knowing who modified a field requires stopping earlier/watchpoints or recording evidence over time.
4. **"Pausing a thread does not change concurrency bugs."** False: pausing alters scheduling, timeouts, and lock ownership.
5. **"`RUNNABLE` in a thread dump definitely means consuming CPU."** False: cross-check with OS/JFR CPU sampling; Java thread state does not directly reflect CPU consumption.
6. **"Evaluate Expression is always read-only."** False: getters, `toString()`, or methods can mutate state, do I/O, or deadlock.
7. **"Changing a variable in the debugger fixed the bug."** False: temporary runtime edits do not change code, do not replace tests, and can create fake data.
8. **"Conditional breakpoints are free because they rarely hit."** False: the condition may still be evaluated on every pass, impacting hot paths.
9. **"Expose JDWP port in production for convenience."** Very dangerous: a debugger has privileges to manipulate the JVM; never expose the port to untrusted networks.
10. **"The open source file is definitely the running code."** False: different containers/jars, class loaders, modules, shaded artifacts, or deployment versions can misalign breakpoints/locals.
11. **"A slow request = thread consuming CPU."** False: wall time may be spent waiting on I/O/locks/schedulers; use a profiler/JFR to distinguish.
12. **"Not seeing a thread in the debugger means the task does not exist."** False in async/virtual-thread environments; tools and thread-listing policies vary.

## 12. Pre- and Post-Debugging Checklist

**Before attaching:**

- [ ] Have **expected vs actual** and a reproducible case/sanitized input.
- [ ] Know that the question to answer is **state/control flow**, not just aggregate CPU/memory cost.
- [ ] Have matching source/classes/JDK and required debug symbols.
- [ ] Know which method the breakpoint will pause in, with what condition, and which threads are affected.
- [ ] The environment permits pausing; JDWP is not publicly exposed; there is a plan to close the debug listener.
- [ ] If suspecting production race/latency, considered less intrusive logs/JFR/thread dumps.

**After debugging:**

- [ ] Recorded exact **before/after state** of the assignment, selected stack frame, and caller.
- [ ] Proved a specific invariant or hypothesis was violated; avoided extrapolating from a snapshot.
- [ ] Created a regression test for the corresponding edge case, exception path, or concurrency scenario.
- [ ] Re-ran **without breakpoints**; for performance issues, measured with profiler/JFR/load tests.
- [ ] Disconnected debugger/closed ports, and avoided saving secrets in screenshots, logs, or artifacts.

### Self-Check Questions

1. When is adding logs enough, and when is a debugger more worthwhile than a profiler/JFR?
2. In the coupon example, before executing the `payableCents` assignment line, what are the values of `requestedDiscountCents`, `capped`, and `subtotalCents`? Why does this prove the bug?
3. Why do you need a conditional breakpoint on a frequently called method?
4. What is the difference between a field modification watchpoint and the Watches pane displaying expressions in an IDE?
5. Why can stepping over in a multithreaded request cause artificial timeouts or make a race disappear?
6. Why does `jdb where` not work if the JVM has not paused at an appropriate frame/thread?
7. After fixing the code, why is passing one debugger session not enough to conclude the issue is resolved?

## Official References

- [Oracle Java SE 21 — jdb Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdb.html): breakpoints, stepping, `where`/`locals`, attach, and virtual threads guidance.
- [Oracle Java SE 21 — JPDA Connection and Invocation](https://docs.oracle.com/en/java/javase/21/docs/specs/jpda/conninv.html): `-agentlib:jdwp`, `suspend`, `address`, transport, connection limits.
- [Oracle Java SE 21 — Troubleshooting Guide](https://docs.oracle.com/en/java/javase/21/troubleshoot/introduction-client-issues.html): JDWP and diagnostic tools suited to each problem type.
- [Oracle Java SE 21 — jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): thread dumps and JFR commands when evidence should be collected instead of pausing.
- [Oracle Java SE 21 — jfr](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html): viewing and filtering JFR events for profiling before stepping into a debugger.
- [Oracle JDK Mission Control](https://www.oracle.com/java/technologies/jdk-mission-control.html): tool for viewing JFR on CPU, allocation, lock, and I/O.
