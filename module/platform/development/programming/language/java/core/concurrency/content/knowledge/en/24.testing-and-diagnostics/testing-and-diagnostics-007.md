# Testing Contention and Concurrency Stress with jcstress (Non-JDK Tool)

## 1. Why Do We Need jcstress?

Multithreaded Java code can run correctly thousands of times and then fail once due to a rare execution schedule, lost update, visibility issue, race, or violation of Java Memory Model (JMM) ordering. Single-threaded tests, regular JUnit tests, or trying `Thread.sleep()` usually do not actively explore enough timing interactions between threads.

**Java Concurrency Stress (jcstress)** is an empirical testing harness under the OpenJDK Code Tools project. It creates many parallel runs of **actors**, collects resulting states, matches them against **classified outcomes**, and reports acceptable, interesting, or forbidden cases. jcstress is especially useful for studying JVM/JMM behavior and testing small-scale concurrency data structures and algorithms.

**Important note:** jcstress is a **non-JDK tool**. To use it, you need to download a compatible dependency/build harness (for example, via a Maven archetype); Java 17/21 does not provide a `jcstress` command or these annotations out of the box.

The scope of this lesson is general Java concurrency using the JDK and jcstress. Framework-dependent components are out of scope.

### After This Lesson, You Will Be Able To

1. Distinguish between **race condition**, **data race**, **contention**, **stress test**, **JCStress outcome**, and **performance benchmark**.
2. Create a standalone jcstress project with Maven, write a test with two actors and an arbiter, compile, and run it.
3. Explain why the `x++` increment can lose updates and how to replace it with `AtomicInteger`.
4. Use a "message passing" test to compare plain fields with `volatile` according to JMM happens-before.
5. Know how to test a manifestation of contention without confusing outcome counts with latency/throughput.
6. Interpret `ACCEPTABLE`, `ACCEPTABLE_INTERESTING`, and `FORBIDDEN` reports, as well as the limits of probabilistic verification.

## 2. What Issues Does jcstress Look For?

### 2.1. Race Condition and Data Race

- **Race condition**: the outcome depends on the execution order or timing of concurrent tasks. Not every race condition is a bug; some orderings are valid by design.
- **Data race** as described by the JMM: conflicting read/write actions on the same variable that are not ordered by happens-before; there is no proper synchronization to establish that relationship. A race can lead to unpredictable results, though Java still has JMM rules; you must not assume "anything can happen."
- **Atomicity**: an action or sequence of actions observed as an indivisible unit according to the contract. The `x++` operation consists of reading, adding, and writing; an `int` variable has atomic single reads/writes at its corresponding level, but `x++` is not atomic.
- **Visibility**: whether one thread sees data written by another thread. "Code running in line order" in each thread is not enough to guarantee that another thread observes writes in the same order if happens-before is missing.
- **Ordering**: the compiler, JIT, and CPU may optimize/reorder actions within JMM limits. You must reason using happens-before relationships rather than relying on the intuition that "this line comes before that line."

**Example:** two threads each increment an `int` variable from 0 once. If both read 0 and then write 1, the final result is 1 instead of 2. That is a lost update.

### 2.2. Contention Is Not the Same as a Data Race

**Contention** occurs when multiple threads compete for the same resource: a monitor/lock, semaphore, atomic variable, shared cache line, queue, CPU, or memory bandwidth. Contention can exist even when code is correct and has no data race.

- `synchronized` is correct regarding mutual exclusion, but many threads may wait on one lock, leading to increased tail latency.
- `AtomicInteger` avoids lost updates, but heavy updates to the same variable can still create cache coherence contention.
- Reducing contention via sharding, local accumulation, or `LongAdder` can improve throughput, but does not by itself prove every business contract.

**jcstress evaluates the observable correctness of concurrent outcomes.** The tool may induce contention while actors run in order to explore interleavings, but it is **not** a latency/throughput profiler or a monitor wait-time analyzer. To quantify contention, use JMH, JFR, `ThreadMXBean`, or OS profilers/counters in a separate experiment.

### 2.3. Why Is a Million-Iteration `for` Loop Not Enough?

A hand-written loop like the following is often misleading:

~~~java
for (int i = 0; i < 1_000_000; i++) {
    new Thread(() -> shared++).start();
}
~~~

It does not wait for all threads, incurs the overhead of a million threads, and does not automatically classify valid results. Even if fixed with `join()`, the program still explores schedules in a poorly controlled way and does not prevent JIT optimizations from masking the behavior.

jcstress organizes **rendezvous, multiple state instances, multiple trials, and multiple JVM/CPU configurations depending on the mode**, collects frequencies, and maps outcomes to an explicit contract. The harness cannot "control every schedule" and does not prove that a rare outcome will appear within a finite time.

## 3. The Execution Model of jcstress

A basic test has:

- **@JCStressTest** placed on the test class so the harness recognizes it.
- **@State** describes the state object that actors read from and write to together. In simple examples, you can annotate the test class with both `@JCStressTest` and `@State`.
- **@Actor** placed on methods that run concurrently. The completion order among actors **must not be assumed**.
- **@Arbiter** optional; reads the state after all actors have finished for that state instance; suitable for checking the final result without introducing an extra race with the actors.
- **@Outcome(id, expect, desc)** describes an expected result and its classification, based on the string representation of the result.
- **I_Result / II_Result / ...** are built-in result holders; the letter `I` denotes `int`, and `II_Result` has two `int` fields `r1`/`r2`. The result object is managed by the harness—do not instantiate it with `new` inside an actor.

Conceptual lifecycle:

~~~text
jcstress harness
  -> creates a new @State object for a trial
  -> runs actor1 and actor2 concurrently with non-deterministic scheduling
  -> (if present) invokes @Arbiter after both actors have finished
  -> retrieves the result, converts it to an outcome ID
  -> increments the frequency of the corresponding outcome
  -> repeats across many states/iterations/epochs
  -> classifies results and generates a report
~~~

Initial instance/constructor state is created for a trial before actors are scheduled; actors must not share static variables across trials unless you genuinely intend to test global state. Good tests keep state small, independent, and minimize side effects such as I/O.

### 3.1. Three Important Outcome Levels

| Expect | Meaning | Action When the Outcome Appears |
|---|---|---|
| ACCEPTABLE | An outcome **allowed** by the contract | Not treated as an error even if it appears at varying frequencies |
| ACCEPTABLE_INTERESTING | A valid outcome that is noteworthy to observe/investigate | Highlighted in the report, helping illustrate rare phenomena |
| FORBIDDEN | An outcome **not allowed** by the contract declared by the test | Treated as an anomaly; inspect the test, expectations, harness, JVM, hardware, and re-run |

**`ACCEPTABLE` does not mean it is guaranteed to appear.** A valid outcome may go unobserved. **`FORBIDDEN`** is only trustworthy when the oracle is correct: if a valid outcome is mistakenly classified as `FORBIDDEN`, the report will be a false positive.

Outcome IDs must match the actual format of the `Result` class. For `I_Result`, IDs are typically `"1"` or `"2"`; for `II_Result`, the format is `"0, 1"`. Do not infer IDs from the number of actor runs or thread order.

## 4. Setting Up jcstress: A Dedicated Maven Project

OpenJDK recommends creating a **separate jcstress module/project** because the harness requires annotation processing, test-list packaging, and an executable JAR. Simply adding `jcstress-core` to a normal Java module may not produce a properly runnable JAR.

Practical requirements:

- Java Development Kit (**JDK 17+** recommended for these examples), with working `java` and `javac` commands.
- Maven installed locally, with access to Maven Central to download artifacts if not already cached.
- An OS that allows launching multiple JVMs/threads and has enough CPU/memory to run stress tests.

Check your environment:

~~~bash
java -version
javac -version
mvn -version
~~~

Create the project using the Maven archetype recommended in the official OpenJDK README (a single-line command run in a standard shell):

~~~bash
mvn archetype:generate -DinteractiveMode=false -DarchetypeGroupId=org.openjdk.jcstress -DarchetypeArtifactId=jcstress-java-test-archetype -DgroupId=org.sample -DartifactId=jcstress-lab -Dversion=1.0
~~~

Here `-Dversion=1.0` is the version of the generated project; Maven resolves the archetype version from the repository. If the system prompts for a version, choose a compatible released jcstress archetype version and document it for your team so builds remain reproducible.

~~~bash
cd jcstress-lab
mvn clean verify
java -jar target/jcstress.jar -h
~~~

**`mvn clean verify`** compiles and packages the project, whereas **`java -jar target/jcstress.jar`** actually runs the stress tests. Building the artifact does not mean the full stress workload has been executed.

Key structure (exact names may vary by archetype):

~~~text
jcstress-lab/
  pom.xml
  src/main/java/org/sample/
    LostUpdateTest.java
    AtomicIncrementTest.java
    PlainPublicationTest.java
    VolatilePublicationTest.java
  target/jcstress.jar      (after mvn clean verify)
~~~

If the archetype generated sample tests, you can keep them and add the classes below. Do not overwrite sample files without checking them first. **Each public Java class must be in a file with the matching name**, and its package must match the directory path.

### 4.1. Running a Single Test and Choosing Intensity

~~~bash
mvn clean verify
java -jar target/jcstress.jar -t '.*LostUpdateTest' -m quick
~~~

In Windows PowerShell, you can use single quotes in the same way. The `-t` option filters tests by name; provide a pattern matching the class you want to run to avoid running the entire suite. The `-m` option selects an intensity/duration preset; `quick` is suitable for fast feedback, but **takes fewer samples** and can easily miss a rare outcome.

Check the actual options supported by your version using:

~~~bash
java -jar target/jcstress.jar -h
~~~

Do not guess fork counts, thread counts, stress times, or Java flags from a different version; options can change across versions. In fast CI runs you can use `-m quick`; when investigating a rare race, increase the duration/iterations, run across more CPUs/JDKs, and control system resources.

## 5. Example 1: Reproducing a Lost Update with Two Actors

File **src/main/java/org/sample/LostUpdateTest.java**:

~~~java
package org.sample;

import org.openjdk.jcstress.annotations.Actor;
import org.openjdk.jcstress.annotations.Arbiter;
import org.openjdk.jcstress.annotations.Expect;
import org.openjdk.jcstress.annotations.JCStressTest;
import org.openjdk.jcstress.annotations.Outcome;
import org.openjdk.jcstress.annotations.State;
import org.openjdk.jcstress.infra.results.I_Result;

@JCStressTest
@State
@Outcome(id = "1", expect = Expect.ACCEPTABLE_INTERESTING,
        desc = "Lost update: both actors read 0 then write 1.")
@Outcome(id = "2", expect = Expect.ACCEPTABLE,
        desc = "Both increments contributed to the final value.")
public class LostUpdateTest {
    private int counter;

    @Actor
    public void actor1() {
        counter++;
    }

    @Actor
    public void actor2() {
        counter++;
    }

    @Arbiter
    public void arbiter(I_Result result) {
        result.r1 = counter;
    }
}
~~~

**Why is the result 1 or 2?** Each actor performs a non-atomic increment on the same `counter` variable, which defaults to 0. If both read 0 before either writes, each actor writes 1 and one increment is lost. If one increment completes before the other reads, the result is 2.

Illustrative interleaving schedule:

~~~text
initial counter = 0

actor1                 actor2
  read 0
                         read 0
  compute 1
                         compute 1
  write 1
                         write 1

@Arbiter reads counter = 1
~~~

Do not claim that the harness is **guaranteed** to observe `1` in every run. If you only see `2`, the test still does not prove that `++` is atomic. Outcome `1` is **valid under the behavior of a program with a data race**, yet it is a warning sign if the business requirement is "no lost updates."

### 5.1. Verifying the Fix with `AtomicInteger`

File **src/main/java/org/sample/AtomicIncrementTest.java**:

~~~java
package org.sample;

import java.util.concurrent.atomic.AtomicInteger;
import org.openjdk.jcstress.annotations.Actor;
import org.openjdk.jcstress.annotations.Arbiter;
import org.openjdk.jcstress.annotations.Expect;
import org.openjdk.jcstress.annotations.JCStressTest;
import org.openjdk.jcstress.annotations.Outcome;
import org.openjdk.jcstress.annotations.State;
import org.openjdk.jcstress.infra.results.I_Result;

@JCStressTest
@State
@Outcome(id = "2", expect = Expect.ACCEPTABLE,
        desc = "Both atomic increments are counted.")
@Outcome(expect = Expect.FORBIDDEN,
        desc = "No other final result is allowed.")
public class AtomicIncrementTest {
    private final AtomicInteger counter = new AtomicInteger();

    @Actor
    public void actor1() {
        counter.incrementAndGet();
    }

    @Actor
    public void actor2() {
        counter.incrementAndGet();
    }

    @Arbiter
    public void arbiter(I_Result result) {
        result.r1 = counter.get();
    }
}
~~~

Here, two calls to **`incrementAndGet()`** on the same `AtomicInteger` have atomic update semantics; after both actors finish, the arbiter must see `2`. The second `@Outcome` without a specific `id` acts as the default rule for all unlisted results: **`FORBIDDEN`**.

Another solution is to use a shared `synchronized`/`Lock` around the increment operation. With just two increments, `AtomicInteger` makes atomicity easy to see and keeps the lesson simple. **Do not use `volatile int counter` with `counter++`** as a "fix": `volatile` provides visibility/ordering under the JMM for volatile accesses, but does not turn the read-modify-write `++` operator into an atomic operation.

### 5.2. Running and Interpreting

~~~bash
mvn clean verify
java -jar target/jcstress.jar -t '.*LostUpdateTest' -m quick
java -jar target/jcstress.jar -t '.*AtomicIncrementTest' -m quick
~~~

The harness summary output typically includes the outcome, observation count/frequency, expectation, and description. **There is no fixed stdout**: outcome frequencies depend on CPU/JIT/JVM/scheduling, duration, and mode. Open the HTML report generated by jcstress (usually under the `results/` directory in the working directory; the exact path is printed during the run).

Expected results regarding **contract correctness**:

| Test | Outcome | Classification | Meaning |
|---|---|---|---|
| LostUpdateTest | 1 | ACCEPTABLE_INTERESTING | An update can be lost |
| LostUpdateTest | 2 | ACCEPTABLE | No update lost in that trial |
| AtomicIncrementTest | 2 | ACCEPTABLE | Matches contract when both actors complete |
| AtomicIncrementTest | other than 2 | FORBIDDEN | Contract violation or bug in test/environment |

Do not turn the count of outcome `1` into "x% of real users hit this bug": the stress harness tries to increase the chance of exposing interleavings, not to simulate a production workload distribution.

## 6. Example 2: Testing Visibility and Message Passing

The following example examines publication through two variables:

- Writer assigns `data = 42` and then `ready = true`.
- Reader reads `ready`; if `true`, it reads `data`; if `false`, it writes `-1` into `result`.
- The notable symptom is when reader sees **`ready = true` but `data = 0`**, showing there is no guarantee that the earlier write to `data` is visible to another thread.

### 6.1. Unsynchronized Version: Plain Fields

File **src/main/java/org/sample/PlainPublicationTest.java**:

~~~java
package org.sample;

import org.openjdk.jcstress.annotations.Actor;
import org.openjdk.jcstress.annotations.Expect;
import org.openjdk.jcstress.annotations.JCStressTest;
import org.openjdk.jcstress.annotations.Outcome;
import org.openjdk.jcstress.annotations.State;
import org.openjdk.jcstress.infra.results.I_Result;

@JCStressTest
@State
@Outcome(id = "-1", expect = Expect.ACCEPTABLE,
        desc = "Reader checked ready before seeing publication.")
@Outcome(id = "42", expect = Expect.ACCEPTABLE,
        desc = "Reader saw data after publication.")
@Outcome(id = "0", expect = Expect.ACCEPTABLE_INTERESTING,
        desc = "Flag looked ready, payload was not visible.")
public class PlainPublicationTest {
    int data;
    boolean ready;

    @Actor
    public void writer() {
        data = 42;
        ready = true;
    }

    @Actor
    public void reader(I_Result result) {
        result.r1 = ready ? data : -1;
    }
}
~~~

Because `data` and `ready` are plain fields, the program **does not establish a happens-before** relationship from `writer` to `reader`. Outcome `0` is allowed by the JMM regarding visibility/ordering even though `writer` writes `data` before `ready` in source code. **Being allowed** does not mean every machine will observe outcome `0`. Not seeing `0` after some runs does not mean the data race is fixed.

If `reader` sees `ready` as `false` (regardless of where `writer` is), `-1` is allowed. If it sees both the flag and the payload correctly, `42` is also allowed.

### 6.2. `volatile` Version: Guaranteed Publication

File **src/main/java/org/sample/VolatilePublicationTest.java**:

~~~java
package org.sample;

import org.openjdk.jcstress.annotations.Actor;
import org.openjdk.jcstress.annotations.Expect;
import org.openjdk.jcstress.annotations.JCStressTest;
import org.openjdk.jcstress.annotations.Outcome;
import org.openjdk.jcstress.annotations.State;
import org.openjdk.jcstress.infra.results.I_Result;

@JCStressTest
@State
@Outcome(id = "-1", expect = Expect.ACCEPTABLE,
        desc = "Reader runs before it observes the ready flag.")
@Outcome(id = "42", expect = Expect.ACCEPTABLE,
        desc = "Volatile flag publishes preceding data write.")
@Outcome(expect = Expect.FORBIDDEN,
        desc = "Other outcomes violate the expected publication contract.")
public class VolatilePublicationTest {
    int data;
    volatile boolean ready;

    @Actor
    public void writer() {
        data = 42;
        ready = true;
    }

    @Actor
    public void reader(I_Result result) {
        result.r1 = ready ? data : -1;
    }
}
~~~

**Why must `data` be 42 when `ready` is `true`?** Writing to `volatile ready` **synchronizes-with** a volatile read of `ready` that observes that publication. By transitivity of happens-before, the plain write `data = 42` that precedes the volatile write must also be observed properly by `reader` once it sees `ready` is `true`. In this case, `reader` reads `ready` once and then reads `data`; no third actor modifies `data`.

If `reader` has not yet seen `ready == true`, `-1` remains valid. **You do not need to make `data` `volatile`** in this message-passing example, provided the entire publish/read protocol follows the same condition and no subsequent writes after publication introduce a new race.

### 6.3. Test Run

~~~bash
mvn clean verify
java -jar target/jcstress.jar -t '.*PlainPublicationTest' -m quick
java -jar target/jcstress.jar -t '.*VolatilePublicationTest' -m quick
~~~

| Outcome | PlainPublicationTest | VolatilePublicationTest |
|---|---|---|
| -1 | ACCEPTABLE | ACCEPTABLE |
| 42 | ACCEPTABLE | ACCEPTABLE |
| 0 | ACCEPTABLE_INTERESTING | FORBIDDEN |
| other unexpected result | Review the oracle | FORBIDDEN |

The table shows **logical classifications**, not measured frequencies. If a `FORBIDDEN` outcome appears, reproduce it and check how the test, annotations, and result are written before blaming the JVM or hardware.

## 7. Designing a Stress Test for a Real Contention Problem

### 7.1. Start from the Invariant, Not the Thread Count

Example problem: a balance is concurrently credited and debited. Define the invariant clearly first:

- If all operations complete before the arbiter reads, the final total must equal the expected value.
- If the contract allows an update attempt to fail, you must distinguish between success and rejection.
- If linearizability is required, check each operation/return value against a valid sequential order; checking only the final sum is **not enough**.
- If the target is a collection, you must also consider uniqueness, visibility, ordering, null/missing entries, or inconsistent state, depending on the API contract.
- If a concurrency primitive can time out or be canceled, include those paths in the state/outcomes.

Then reduce it to **few actors, few fields, and minimal logic**. The most important lesson is having a **correct oracle**: accurately describing which outcomes are permitted by the JMM/API and which are not. If the oracle is too strict, you will get false positives; if it is too weak, the test will miss bugs.

### 7.2. Exploring Controlled Contention

Example of a resource protected by `synchronized`:

~~~java
private final Object lock = new Object();
private int balance;

void deposit() {
    synchronized (lock) {
        balance++;
    }
}

void withdraw() {
    synchronized (lock) {
        balance--;
    }
}
~~~

This is an illustrative snippet, **not a standalone jcstress class yet**. If a test creates two actors calling `deposit()` and `withdraw()`, and an arbiter reads `balance` after both actors finish, the final value must be `0` starting from an initial state of `0`. However, to test contention **in terms of performance**, you must measure lock hold/wait times, throughput, and latency in a different workload; jcstress can only verify the atomicity/invariant of the simplified version.

Increasing the actor count or adding loops inside actors does not always make a better test. Long loops can cause one actor to dominate for too long, reducing interleaving diversity and amplifying test-harness overhead. Start with small litmus tests, and only add actors/operations when there is a specific invariant to observe.

### 7.3. States Worth Testing

- **Lost update**: unsynchronized read-modify-write operations.
- **Visibility/publication**: reader sees the flag but not the correct payload.
- **Check-then-act**: two actors check a condition simultaneously and both modify state in violation of the contract.
- **Unsafe lazy initialization**: an actor publishes an object before its constructor/state is properly synchronized.
- **Collection concurrency**: interleaved add/remove/get causing duplicate/missing items or violating size/invariants.
- **ABA or CAS loop**: lock-free algorithms handling state changing from A -> B -> A.
- **Lock ordering**: deadlock, livelock, or starvation; note that the test may hang, so configure timeouts and inspect thread dumps/logs.

Do not automatically classify every race condition as `FORBIDDEN`. For instance, a program that intentionally picks a "first winner" may allow multiple outcomes while still requiring consistency with its contract.

## 8. Reading jcstress Reports Correctly

A run typically reports for each test:

1. Test name, JVM configurations/forks, and stress level.
2. List of observed outcomes along with sample counts, frequencies, and classifications.
3. Outcome descriptions from `@Outcome(desc = "...")`.
4. Warnings about failures, unrecognized tests, JVM configurations that failed to run, or tests throwing exceptions.
5. An HTML report to view the full results, which is more convenient than reading a few console lines.

**Do not fabricate numbers.** The following report template only illustrates how to read the labels, not actual stdout or measurements:

~~~text
Test: LostUpdateTest
Outcome 1  -> ACCEPTABLE_INTERESTING (lost update)
Outcome 2  -> ACCEPTABLE             (both increments observed)
Observed frequencies: [taken only from an actual run]
~~~

If both `1` and `2` appear, the lost update has been demonstrated. If only `2` appears, **it does not prove** the code is thread-safe. If `FORBIDDEN` appears, the next steps include reproducing it, preserving logs/HTML reports, verifying the contract, and ruling out issues such as unintended shared state, wrong annotations, invalid initialization, or concurrent writes to the result object done incorrectly.

### 8.1. What Does the Absence of an Outcome Mean?

Stress testing is guided execution sampling, yet it remains subject to randomness and configuration. Not observing an outcome **does not prove it is impossible**. Empirically, increasing duration, forks, and CPU variety raises the chance of finding a rare bug, but it cannot exhaustively cover all schedules and JMM states.

A bug that only manifests under a certain JIT optimization level or a different CPU architecture may be missed in your current environment. Therefore, combine jcstress with **happens-before reasoning**, API contracts, code reviews, and other testing methods.

### 8.2. Why Do `FORBIDDEN` Counts Need Verification?

A `FORBIDDEN` output is only meaningful after confirming that the **expected oracle** is accurate. Common mistakes include:

- Declaring a fixed actor order when no ordering guarantee exists.
- Assuming `volatile` guarantees atomicity for `x++`.
- Assuming `synchronized` on two different objects protects the same state.
- Having the arbiter access mutable static state outside the lifecycle of a single test trial.
- Actors performing I/O or timing out, causing results to be affected by unintended exceptions.
- The test reading multiple fields without synchronization and reasoning as if they formed an atomic snapshot when no such contract exists.

Minimize the reproducer first; distinguish between a bug in the code under test, a bug in the test, a tool bug, and a JVM/hardware bug.

## 9. Comparing jcstress with JUnit, JMH, and Other JVM Tools

| Tool | Primary Focus | What Can Be Inferred? | Limitations |
|---|---|---|---|
| JUnit | Functional testing, contracts with normal inputs | Results of specific deterministic scenarios | Rare thread interleavings are usually missed |
| jcstress | Concurrent correctness, outcomes under JMM/API | Observed valid/rare/forbidden outcomes under test conditions | Cannot prove absolute absence of bugs; does not replace benchmarks |
| JMH | Throughput/latency microbenchmarks with a dedicated harness | Performance comparison of benchmarked workloads | Running fast does not prove thread safety |
| JFR | JVM event recording/profiling for contention/allocations/CPU | Traces, hotspots, wait/monitor events when recorded | Does not classify JMM outcomes |
| jstack/jcmd Thread.print | Thread state/stack snapshots | Waiting points, deadlocks, call stacks at sampling time | Does not cover all interleavings |
| ThreadMXBean | Thread/CPU time/blocked/waited counters if JVM supports them | Hints at contention and wait times | Not an oracle for races or linearizability |

### Case: `AtomicInteger` Is Correct but Still Slow

If `AtomicIncrementTest` only returns outcome `2`, the code avoids lost updates. Even so, 100 threads updating **one `AtomicInteger`** can cause contention on the same cache line; CPU/cache coherence traffic can yield worse throughput than sharding.

For "is it correct?", use jcstress and API reasoning; for "is it fast?", use benchmarks and profiling. **Do not use jcstress outcome histogram frequencies to infer production throughput or latency.**

### Case: `synchronized` Prevents Races but Causes Lock Contention

A shared lock that properly protects an invariant can be a good choice even if throughput drops; optimization requires balancing correctness and performance. To find where lock contention occurs, combine JFR `JavaMonitorEnter`/`ThreadPark` events with an appropriate load test. Do not remove `synchronized` just because a thread dump shows `BLOCKED`.

## 10. A Reliable Workflow

### Step A — Write the Contract and Rationale for Each Outcome

Create a short table before writing code:

| Outcome | Explanation per JMM or API | Allowed? |
|---|---|---|
| Both increments recorded | Both actors complete and atomic update works | Yes |
| One increment lost in plain `++` version | Read-modify-write can interleave | Yes in the racy program, but may be a business bug |
| One increment lost in `AtomicInteger` version | Contradicts atomic operation contract | No |

If you cannot explain every outcome, do not label anything `FORBIDDEN` yet.

### Step B — Minimize the Test, Isolate Shared State

Limit each actor to a few operations; do not add logging, `sleep`, network calls, database calls, `synchronized`, or `println` to a race test when they are not part of the behavior under test. Logging and `sleep` can introduce ordering or alter timing, making the bug disappear.

Do not use random seeds or time-dependent globals inside actors unless controlled. Avoid results that depend on two actors looping forever or background threads outliving the state trial.

### Step C — Run `quick` Mode First, Then Scale Intentionally

~~~bash
mvn clean verify
java -jar target/jcstress.jar -t '.*PublicationTest' -m quick
~~~

When higher confidence is needed, check the harness help to select a longer mode and tune forks, CPU affinity, JVM options, and duration. Run across diverse JDKs/CPUs when possible. Save environment details and logs for each run; differing results between two machines do not automatically indicate a fault on either machine.

### Step D — Handling Anomalies

1. Verify the test is in the right package, the filter name is correct, and the class was included in the JAR by the annotation processor.
2. Read the HTML report and record the test, outcome, count, JVM, mode, options, and machine.
3. Re-evaluate happens-before and ordering; write down the interleaving schedule believed to produce the result.
4. Minimize the code; replace the real system with a small `@State` class and two actors.
5. Re-run under multiple conditions. If `FORBIDDEN` persists, check the relevant library/JVM/hardware after ruling out oracle/test errors.
6. Only conclude "bug reproduced" once both the actual result and the contract have been verified.

### Step E — Integrating Stress Tests into CI

You can run a small set of tests with the `quick` preset as a **smoke signal** in CI, while scheduling longer runs (nightly/periodic) for rare races. A green CI run is evidence that "no forbidden outcome was observed in the sampled runs," **not absolute proof of thread safety**.

For tests that may hang due to deadlock/livelock, set a job timeout and collect thread dumps after timeout; balance resources since jcstress can spawn many forks over extended periods.

## 11. Frequently Asked Questions and Common Pitfalls

**Can I run jcstress using only `java`/`javac`?** That is not enough; the annotations, harness, and test-registry generation come from the jcstress artifacts/build. Use the Maven archetype or an equivalent build integration.

**Do I need Spring or an async framework?** No. These examples use only Java/JDK concurrency plus the non-JDK jcstress tool.

**Why doesn't a test annotated with `@JCStressTest` show up in `-t`?** Check the package/class path, Maven module, annotation processor, build logs, and filter pattern. The jcstress JAR must contain the test list generated by the processor, not just `.class` files.

**If a test always returns valid outcomes, can I conclude the code is thread-safe?** You can only conclude that no violation was observed in the tested executions. Concluding thread safety must also rely on the contract, JMM, algorithm, and the scope of all operations.

**Can I induce a race with `Thread.sleep(1)`?** `sleep` can be used in real applications, but adding it to a litmus test easily alters interleaving/scheduling and gives no guarantees. Prefer a small two-actor structure and let the harness generate diverse executions.

**Do I need to distinguish `ACCEPTABLE` from `ACCEPTABLE_INTERESTING`?** Both are allowed by the oracle, but the second is highlighted for analysis. Do not treat `ACCEPTABLE_INTERESTING` as a harness failure.

**Can I verify throughput gains under contention with jcstress?** That is not its primary purpose; use JMH or a load test instead. jcstress helps verify whether replacing a lock with an optimized mechanism still satisfies the contract.

**If `@Arbiter` sees the right final state, are all preceding operations linearizable?** No. A correct final state can mask incorrect intermediate states or return values. To test linearizability, design the result to capture sufficient history or the corresponding conditions.

**Does `volatile` fix lost updates?** No. `volatile` helps with visibility/ordering; an increment consists of multiple steps. Use atomic updates or proper synchronization.

**My program has a race, yet jcstress didn't observe `0` in `PlainPublicationTest`?** That is completely possible. Tests are sensitive to JIT/hardware/mode, and some allowed outcomes are very rare. Not observing it does not mean plain fields are safe.

## 12. Guided Practice Exercises

### Exercise 1 — Plain `x++` vs. `AtomicInteger`

Run the two tests from Section 5 on the same machine and on another machine/JDK if available. Record:

~~~text
JDK / CPU / OS:
jcstress version / mode:
LostUpdateTest: observed outcomes:
AtomicIncrementTest: observed outcomes:
Any FORBIDDEN outcomes?:
Interpretation based on update atomicity:
~~~

Keep your conclusion precise: "lost update observed" if outcome `1` appeared; "not observed" if it did not. Do not predict frequencies in advance.

### Exercise 2 — Message Passing

Run `PlainPublicationTest` and `VolatilePublicationTest`. Draw the happens-before graph:

~~~text
Writer: data=42 -> ready=true (volatile write)
                         |
                         | synchronizes-with
                         v
Reader:                  ready (volatile read) -> data read
~~~

Explain why `reader` seeing `ready == true` in the `volatile` version requires the payload to be `42`, whereas the unsynchronized plain version provides no such guarantee.

### Exercise 3 — Check-Then-Act Problem

Design a `@State` class containing a `boolean acquired` field and an unsynchronized `tryAcquire` method:

~~~java
boolean acquired;

boolean tryAcquire() {
    if (!acquired) {
        acquired = true;
        return true;
    }
    return false;
}
~~~

This is only an **illustrative code snippet**. Two actors call the method concurrently, and each records its boolean return value in a separate field of the result holder. Would you accept the outcome "both are true"? If the contract is "only one caller wins," **no**. Replace check-then-act with `AtomicBoolean.compareAndSet(false, true)`, then redefine the valid outcomes before running.

### Exercise 4 — Distinguishing Correctness from Contention

Suppose you write one counter using `synchronized` and another using `AtomicInteger`, and both pass jcstress. That **does not** answer which one is faster. Next, design a JMH benchmark with multiple threads, keeping the work constant and the result observed, and compare throughput along with latency/CPU distribution if appropriate. Document the test conditions clearly before drawing conclusions.

## 13. Key Takeaways

- **jcstress** is a harness for testing concurrency correctness by outcome states, and is not included in the JDK.
- **@Actor** models concurrent operations; **@Arbiter** observes state after actors finish; **@Outcome** is the oracle declared by the test author.
- **ACCEPTABLE_INTERESTING** is permitted but worth analyzing; **FORBIDDEN** requires seriously reviewing both the code and the oracle.
- **Finding no bugs in a stress run** does not prove the absence of bugs.
- **Contention** can exist in completely correct code. jcstress verifies the contract; JMH/JFR and other measurement tools help analyze contention cost.
- When dealing with the Java Memory Model, reason using **happens-before/atomicity/ordering**, not solely by observed outcome frequencies.

**Official sources for reference and cross-checking:** [OpenJDK jcstress project](https://openjdk.org/projects/code-tools/jcstress/), [OpenJDK jcstress GitHub README](https://github.com/openjdk/jcstress/blob/master/README.md), [jcstress samples](https://github.com/openjdk/jcstress/tree/master/jcstress-samples), [Java Language Specification §17 Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html), [java.util.concurrent.atomic](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/package-summary.html).
