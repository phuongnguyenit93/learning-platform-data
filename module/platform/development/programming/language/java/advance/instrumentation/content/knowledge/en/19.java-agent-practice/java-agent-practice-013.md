# Measuring Overhead and Resilience When Event Export Is Slow

**Context:** Java Advance → instrumentation → **Agent practice**.

Java agents that collect traces, metrics, or events typically insert a short hook into a business method. Behind that hook may sit serialization, queues, batching, a network exporter, and a collector. If the exporter is slow or unresponsive, a design lacking backpressure can turn a **telemetry failure** into an **application failure**: response times spike, thread pools stall, out-of-memory errors occur, or business exceptions are masked by exporter errors.

This lesson builds a reproducible experiment to answer:

1. **Overhead:** How does enabling the agent affect throughput, p50/p95/p99 latency, and CPU/GC?
2. **When the exporter is slow:** Do business threads wait? Does the queue fill up, and is memory bounded?
3. **When the exporter stops completely:** Does the business logic keep running, and are dropped events accounted for?
4. **When the exporter recovers:** Are remaining queued events processed, does the worker survive exceptions, and does shutdown have a deadline?
5. **Reliability:** Do the counts of business calls, received events, sent events, failures, and pending events match the chosen contract?

The main example uses **JDK 17+, Maven, ASM, and a `-javaagent` Java agent that actually inserts the hook**. The exporter is simply a simulated sink using a worker thread and controllable `Thread.sleep`, so there is no need to configure an external collector. Nanosecond/throughput measurements must be run on a specific machine; this document only states **logically deterministic stdout** and formulas for calculating overhead yourself, without fabricating measurement results.

> **Lab policy:** fail-open for telemetry. If the exporter stalls, the application **does not wait for queue space**; events that cannot be enqueued are discarded and recorded as `dropped`. This is an appropriate choice for illustrating tracing/metrics, **not the default choice for mandatory lossless audit events**.

## 1. Comparing Two Event Export Architectures

### 1.1. Synchronous Export on the Request Thread

```text
Request
  -> Service.work()
       -> instrumentation hook
            -> encode event
            -> send HTTP to exporter
            -> await ACK/timeout
       -> execute original method
  -> response
```

If the exporter waits 300 ms, the hook can hold the request for an extra 300 ms. Even a single `Future.get()`, `CompletableFuture.join()`, `BlockingQueue.put()`, or `CountDownLatch.await()` placed on the request path is enough to introduce wait time.

Anti-pattern example (fragment, not a standalone program):

```java
public static void onEntry() {
    exporter.sendSynchronously(buildEvent());
    // The business method must wait for the exporter.
}
```

A class name like `AsyncExporter` does not guarantee non-blocking behavior: inspect the **actual calls on the application thread**, including serializers, logging, and callbacks.

### 1.2. Export via a Bounded Queue and a Dedicated Worker

```text
Business thread A, B, C...         Worker export thread
       │                                    │
       ▼                                    ▼
  Agent.onEntry()                      poll event
       │                                    │
  ArrayBlockingQueue.offer(event)         send
       │                              ┌─────┴──────┐
       ├── accepted                   │            │
       │       └─────────────► bounded queue      │
       └── dropped if full            success      failure
                                       │            │
                                    exported       failed

Business path continues even if the queue is full.
```

`ArrayBlockingQueue.offer(E)` does not wait until space becomes available: when full, it returns `false`. However, the queue has an internal lock, so it is **not lock-free** and does not provide hard real-time guarantees. You still need to measure `Long` allocation, `System.nanoTime()`, atomic counters, GC, and CPU contention.

The lab bounds the queue to **256 elements** and uses a single exporter worker. During a sustained backlog, new events are dropped rather than letting RAM grow without bound.

## 2. Metrics to Separate

| Metric | Definition | Notes |
| --- | --- | --- |
| `businessCalls` | Number of times the `HotService.work` body actually executes in the measurement phase | Do not include warmup calls |
| `attempted` | Number of events the hook attempts to enqueue when recording is enabled | Verifies transformer effectiveness |
| `accepted` | Events that entered the queue | **Does not yet mean** successfully sent |
| `dropped` | Events rejected by the queue when full | Policy-driven loss |
| `exported` | Events successfully processed by the simulated sink | Success in simulation only |
| `failed` | Events processed by the worker where the sink threw an exception | Not counted as exported |
| `pending` | Events that were accepted but have neither succeeded nor failed at the stats snapshot point | May be queued or in-flight |
| `queued` | Number of events still sitting in the queue | May be one less than pending |
| `latency p50/p95/p99` | Duration percentiles of the sampled business method | Not full end-to-end request latency |
| `throughput` | Business invocations completed per second during the measurement phase | Do not mix in exporter drain time |
| `drop rate` | `dropped/attempted` | Compute only when denominator is greater than 0 |
| `export lag` | Time from event creation to collector acknowledgement | The lab has no real collector |

Once all producer threads have stopped, we verify:

```text
attempted == accepted + dropped
accepted  == exported + failed + pending
pending  >= 0
queued   <= 256

Agent mode:
  attempted == businessCallsMeasured

Without agent:
  attempted = 0
```

**Why does `pending` not necessarily equal `queued`?** The worker calls `poll` to remove an event from the queue and then waits/sleeps/sends. That event is now **in-flight**: it has not yet been counted as `exported` or `failed`, yet it is no longer in the queue.

### 2.1. Overhead Formulas

```text
p99 overhead (%) =
  100 * (p99_agent - p99_baseline) / p99_baseline

Throughput degradation (%) =
  100 * (throughput_baseline - throughput_agent)
       / throughput_baseline

Drop rate (%) = 100 * dropped / attempted
```

These are **calculation formulas**, not pre-measured numbers. Always report **absolute differences**, sample counts, JDK/GC/CPU configuration, and variance across runs. If the baseline is only a few tens of nanoseconds, `System.nanoTime()` and the JIT/scheduler can introduce significant noise.

## 3. Experiment Matrix

| Case | Agent | Exporter | Expected Behavior |
| --- | --- | --- | --- |
| A — baseline | No | No queued events | Business logic correct, `attempted=0` |
| B — fast | Yes | `delayMs=0` | Compare hook + queue + worker overhead |
| C — slow | Yes | `delayMs=10`/event | Queue fills up, loss and tail latency |
| D — stalled | Yes | Block worker with `CountDownLatch` until business work finishes | Loss occurs **deterministically** when calls exceed capacity+1; business threads do not block waiting on the queue |
| E — failure | Yes | Fail once every N send attempts | Worker continues, exporter errors do not alter return value |
| F — recovery | Yes | Open the gate after producers finish and allow a bounded-deadline drain | `exported` progresses, `pending` can decrease |

The difference between slow and stalled: a slow worker **still makes progress**, whereas a gated worker cannot export any events before the gate opens. Case D makes drops deterministic, avoiding tests that rely on CPU speed assumptions.

## 4. Java 17+ Project with a Real Agent and Invoked Exporter

### 4.1. Structure

```text
slow-exporter-lab/
├── pom.xml
└── src/main/java/demo/
    ├── HotService.java
    ├── Probe.java
    ├── TraceAgent.java
    └── Bench.java
```

Requires JDK 17+, Maven 3.x, and ASM dependencies from Maven Central or a local cache. No HTTP server or network is needed for the simulated exporter. The **same JAR** is run twice, with or without `-javaagent`, keeping the business bytecode identical before the agent intervenes.

### 4.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>slow-exporter-lab</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.ow2.asm</groupId>
      <artifactId>asm</artifactId>
      <version>9.7.1</version>
    </dependency>
    <dependency>
      <groupId>org.ow2.asm</groupId>
      <artifactId>asm-commons</artifactId>
      <version>9.7.1</version>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.0</version>
        <configuration><release>17</release></configuration>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-shade-plugin</artifactId>
        <version>3.6.0</version>
        <executions>
          <execution>
            <phase>package</phase>
            <goals><goal>shade</goal></goals>
            <configuration>
              <createDependencyReducedPom>false</createDependencyReducedPom>
              <transformers>
                <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                  <manifestEntries>
                    <Premain-Class>demo.TraceAgent</Premain-Class>
                  </manifestEntries>
                </transformer>
              </transformers>
            </configuration>
          </execution>
        </executions>
      </plugin>
    </plugins>
  </build>
</project>
```

Maven Shade bundles `asm` and `asm-commons` so the transformer works inside `premain`. An agent JAR missing ASM on the agent classpath can fail with `NoClassDefFoundError` before application `main`. `Can-Retransform-Classes` is not needed in this lab because the hook is attached at **load time** and does not require retransformation.

### 4.3. `src/main/java/demo/HotService.java`

```java
package demo;

import java.util.concurrent.atomic.AtomicLong;

public final class HotService {
    private final AtomicLong calls = new AtomicLong();

    public long work(int input) {
        calls.incrementAndGet();
        return input * 31L + 7L;
    }

    public long calls() {
        return calls.get();
    }
}
```

`work(int)` is intentionally tiny so the hook's overhead is clearly visible. Incrementing an `AtomicLong` inside the business method helps detect cases where the agent accidentally re-invokes the method or drops an invocation. The return value is a deterministic function:

```text
If one thread calls work(i) for i = 0..n-1:
  checksum = 31 * n * (n - 1) / 2 + 7*n

If T threads call the same sequence:
  calls    = T*n
  checksum = T * (31*n*(n-1)/2 + 7*n)
```

`n` is bounded in the program so the `long` arithmetic does not overflow.

## 5. Bounded Exporter: Code and Explanation

### 5.1. `src/main/java/demo/Probe.java`

```java
package demo;

import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.LongAdder;

public final class Probe {
    public static final int CAPACITY = 256;

    private static final int DELAY_MS =
            Math.max(0, Integer.getInteger("export.delayMs", 0));
    private static final int FAIL_EVERY =
            Math.max(0, Integer.getInteger("export.failEvery", 0));
    private static final boolean STALLED =
            Boolean.getBoolean("export.stall");

    private static final ArrayBlockingQueue<Long> QUEUE =
            new ArrayBlockingQueue<>(CAPACITY);
    private static final LongAdder ACCEPTED = new LongAdder();
    private static final LongAdder DROPPED = new LongAdder();
    private static final LongAdder EXPORTED = new LongAdder();
    private static final LongAdder FAILED = new LongAdder();
    private static final AtomicLong SEND_ATTEMPTS = new AtomicLong();

    private static final CountDownLatch RELEASE = new CountDownLatch(1);
    private static final AtomicBoolean STOPPING = new AtomicBoolean();
    private static volatile boolean recording;
    private static final Thread WORKER;

    static {
        if (!STALLED) {
            RELEASE.countDown();
        }
        WORKER = new Thread(Probe::exportLoop, "demo-exporter");
        WORKER.setDaemon(true);
        WORKER.start();
    }

    private Probe() {}

    public static void beginRecording() {
        recording = true;
    }

    // Runs on the business thread. Does not wait for the exporter.
    public static void onEntry() {
        if (!recording) {
            return; // skip warmup
        }
        if (QUEUE.offer(System.nanoTime())) {
            ACCEPTED.increment();
        } else {
            DROPPED.increment();
        }
    }

    private static void sendToSimulatedExporter(Long timestamp) {
        long n = SEND_ATTEMPTS.incrementAndGet();
        if (FAIL_EVERY > 0 && n % FAIL_EVERY == 0) {
            throw new IllegalStateException("simulated exporter failure");
        }
        // Event is simulated as processed; no network opened.
    }

    private static void exportLoop() {
        while (!STOPPING.get() || !QUEUE.isEmpty()) {
            try {
                Long event = QUEUE.poll(50, TimeUnit.MILLISECONDS);
                if (event == null) {
                    continue;
                }
                RELEASE.await();
                if (DELAY_MS > 0) {
                    Thread.sleep(DELAY_MS);
                }
                sendToSimulatedExporter(event);
                EXPORTED.increment();
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                return;
            } catch (RuntimeException exporterFailure) {
                FAILED.increment();
                // Exporter error is not thrown to the business thread.
                // Worker continues processing the next event.
            }
        }
    }

    public record Snapshot(
            long accepted,
            long dropped,
            long exported,
            long failed,
            int queued) {

        public long attempted() {
            return accepted + dropped;
        }

        public long pending() {
            return accepted - exported - failed;
        }
    }

    public static Snapshot snapshot() {
        return new Snapshot(
                ACCEPTED.sum(), DROPPED.sum(),
                EXPORTED.sum(), FAILED.sum(), QUEUE.size());
    }

    public static Snapshot releaseAndStop(long waitMillis)
            throws InterruptedException {
        recording = false;
        RELEASE.countDown();
        STOPPING.set(true);
        WORKER.join(waitMillis);
        return snapshot();
    }
}
```

### 5.2. Why Is It Non-Blocking?

`onEntry` only calls `offer`—there is no `put`, `join`, or `sleep`. When the queue is full, `offer` returns `false` and increments `DROPPED`. Whether the worker sleeps for 10 ms or holds the gate for a full minute, business threads **never wait for capacity**.

This does not eliminate other costs: boxing `long` to `Long`, `nanoTime`, short queue locks, `LongAdder`, and scheduling/GC. An overhead experiment must still measure CPU/latency on a specific machine rather than assuming zero cost.

### 5.3. Why Use a Gate and a Daemon Worker?

`STALLED=true` keeps the `CountDownLatch` initialized at 1; the exporter can take at most one event from the queue and then blocks on `RELEASE.await()`. Once the workload finishes, `releaseAndStop` calls `countDown()`, allowing the exporter to resume.

If more than `CAPACITY + 1` events are generated, **at least one event is guaranteed to be dropped** while the gate is closed, regardless of whether the worker already polled the first event. This provides a deterministic test criterion.

The worker is a **daemon** thread and shutdown waits only for a finite timeout. If events remain in the queue when the JVM exits, they **may be lost**; `pending` must be reported. An in-memory daemon queue is **not a durable export system**.

### 5.4. Handling Exporter Failures

With `-Dexport.failEvery=4`, every fourth call to `sendToSimulatedExporter` throws an `IllegalStateException` on the **worker thread**. The loop catches `RuntimeException`, increments `FAILED`, and continues. Business logic is never retried. For out-of-scope failures such as `OutOfMemoryError` or native crashes, **absolute fail-open cannot be guaranteed**; production systems need resource budgets and health checks.

### 5.5. Event Accounting

Suppose the queue is full and the worker has already polled one event but has not sent it yet:

```text
accepted = 257
exported = 0
failed   = 0
queued   = 256
pending  = 257
```

This is **an illustrative state**, not a hardcoded value for every JVM run. If the worker has not yet been scheduled, you might see `accepted=256` and `queued=256`. Therefore, do not assert `accepted==257` or `pending==queued`.

If the worker is released and successfully sends 100 events, `pending` drops to 157 **without changing `accepted`**. If it fails to send 10 events, `failed` increases by 10 and `pending` decreases by 10. Do not fold `failed` into `dropped`: in one case the event entered the queue and failed during processing; in the other, the event was rejected immediately.

## 6. ASM Java Agent Targeting Only the Business Method

### 6.1. `src/main/java/demo/TraceAgent.java`

```java
package demo;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.commons.AdviceAdapter;

public final class TraceAgent {
    private TraceAgent() {}

    public static void premain(String args, Instrumentation inst) {
        inst.addTransformer(new HookTransformer());
    }

    private static final class HookTransformer
            implements ClassFileTransformer {
        @Override
        public byte[] transform(
                ClassLoader loader,
                String className,
                Class<?> beingRedefined,
                ProtectionDomain domain,
                byte[] classfileBuffer) {

            if (!"demo/HotService".equals(className)) {
                return null;
            }

            try {
                ClassReader reader = new ClassReader(classfileBuffer);
                ClassWriter writer = new ClassWriter(
                        reader, ClassWriter.COMPUTE_MAXS);

                ClassVisitor visitor =
                        new ClassVisitor(Opcodes.ASM9, writer) {
                    @Override
                    public MethodVisitor visitMethod(
                            int access, String name, String desc,
                            String signature, String[] exceptions) {
                        MethodVisitor next = super.visitMethod(
                                access, name, desc,
                                signature, exceptions);

                        if (next == null
                                || !"work".equals(name)
                                || !"(I)J".equals(desc)) {
                            return next;
                        }

                        return new AdviceAdapter(
                                Opcodes.ASM9, next, access,
                                name, desc) {
                            @Override
                            protected void onMethodEnter() {
                                visitMethodInsn(
                                        Opcodes.INVOKESTATIC,
                                        "demo/Probe",
                                        "onEntry",
                                        "()V",
                                        false);
                            }
                        };
                    }
                };

                reader.accept(visitor, 0);
                return writer.toByteArray();
            } catch (RuntimeException transformerFailure) {
                // Do not transform; benchmark will FAIL due to missing hook.
                return null;
            }
        }
    }
}
```

QA points:

- The agent `premain` registers the transformer **before application `main`**.
- Only the class with internal name `demo/HotService` and method `work(I)J` is instrumented. Helper classes (`Probe`, `Bench`) and JDK classes are left untouched.
- `AdviceAdapter` inserts exactly **one `INVOKESTATIC`** at method entry. It does not re-invoke business logic and does not alter the return value.
- `ClassWriter.COMPUTE_MAXS` recomputes stack requirements for this small change. When adding branches/handlers or altering complex control flow, you must handle frames and verification properly rather than treating `COMPUTE_MAXS` as a universal solution.
- `ClassFileTransformer` receives `classfileBuffer` from the JVM; it must not be mutated in place. Return a new `byte[]` or `null` if not transforming.
- Java 17 still supports the five-parameter `transform` overload; the six-parameter overload adding `Module` on JDK 9+ delegates to it by default.
- If the transformer fails, the JVM may proceed with the original bytes. Therefore, the benchmark app must **assert that hook attempts equal business invocations** when the agent is enabled, rather than reporting a false PASS when the agent is inactive.

In production, you also need class-loader identity checks, module visibility handling, reentrant loading prevention, and idempotency if retransforming multiple times. This lab only transforms a single class at load time.

## 7. Benchmark Program with Warmup, Multiple Threads, and Assertions

### 7.1. `src/main/java/demo/Bench.java`

```java
package demo;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class Bench {
    private static final int SAMPLE_EVERY = 32;

    private Bench() {}

    private record TaskResult(long checksum, long[] samples) {}

    private static void require(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError("Invariant failed: " + message);
        }
    }

    private static long percentile(
            long[] sorted, double fraction) {
        int index = Math.max(0,
                (int) Math.ceil(sorted.length * fraction) - 1);
        return sorted[index];
    }

    public static void main(String[] args) throws Exception {
        int threads = Integer.getInteger("bench.threads", 4);
        int n = Integer.getInteger("bench.ops", 20_000);
        boolean agent = Boolean.getBoolean("bench.agent");

        require(threads >= 1 && threads <= 16, "threads range");
        require(n >= 1 && n <= 250_000, "operations range");

        HotService service = new HotService();
        for (int i = 0; i < 20_000; i++) {
            service.work(i); // warmup, not recording events yet
        }
        long beforeCalls = service.calls();

        if (agent) {
            Probe.beginRecording();
        }

        ExecutorService executor =
                Executors.newFixedThreadPool(threads);
        CountDownLatch gate = new CountDownLatch(1);
        List<Future<TaskResult>> futures = new ArrayList<>();

        for (int t = 0; t < threads; t++) {
            futures.add(executor.submit(() -> {
                long sum = 0;
                long[] samples = new long[
                        (n + SAMPLE_EVERY - 1) / SAMPLE_EVERY];
                int index = 0;
                gate.await();

                for (int i = 0; i < n; i++) {
                    if (i % SAMPLE_EVERY == 0) {
                        long start = System.nanoTime();
                        long value = service.work(i);
                        samples[index++] = System.nanoTime() - start;
                        sum += value;
                    } else {
                        sum += service.work(i);
                    }
                }
                return new TaskResult(
                        sum, Arrays.copyOf(samples, index));
            }));
        }

        long start = System.nanoTime();
        gate.countDown();

        int samplesPerWorker =
                (n + SAMPLE_EVERY - 1) / SAMPLE_EVERY;
        long[] latencies = new long[threads * samplesPerWorker];
        long sum = 0;
        int position = 0;

        try {
            for (Future<TaskResult> future : futures) {
                TaskResult r = future.get();
                sum += r.checksum();
                System.arraycopy(
                        r.samples(), 0, latencies, position,
                        r.samples().length);
                position += r.samples().length;
            }
        } finally {
            executor.shutdownNow();
        }

        long durationNanos = System.nanoTime() - start;
        long calls = service.calls() - beforeCalls;
        long expectedCalls = (long) threads * n;
        long expectedSum = (long) threads
                * (31L * n * (n - 1) / 2 + 7L * n);

        require(calls == expectedCalls, "business calls");
        require(sum == expectedSum, "business checksum");

        Arrays.sort(latencies);
        long p50 = percentile(latencies, 0.50);
        long p95 = percentile(latencies, 0.95);
        long p99 = percentile(latencies, 0.99);

        Probe.Snapshot beforeRelease = null;
        Probe.Snapshot afterDrain = null;

        if (agent) {
            beforeRelease = Probe.snapshot();
            long waitMs = Math.max(1,
                    Integer.getInteger("export.awaitMs", 250));
            afterDrain = Probe.releaseAndStop(waitMs);

            require(afterDrain.attempted() == expectedCalls,
                    "agent hook entries");
            require(afterDrain.accepted()
                    == afterDrain.exported()
                    + afterDrain.failed()
                    + afterDrain.pending(),
                    "event conservation");
            require(afterDrain.pending() >= 0,
                    "pending not negative");
            require(afterDrain.queued() <= Probe.CAPACITY,
                    "queue is bounded");

            if (Boolean.getBoolean("export.stall")
                    && expectedCalls > Probe.CAPACITY + 1) {
                require(afterDrain.dropped() > 0,
                        "stall must produce drops");
            }
        }

        double seconds = durationNanos / 1_000_000_000.0;
        double throughput = expectedCalls / seconds;

        System.out.println("MODE="
                + (agent ? "AGENT" : "BASELINE"));
        System.out.println("BUSINESS_CALLS=" + calls);
        System.out.println("CHECKSUM_OK=true");
        System.out.printf(Locale.ROOT,
                "LATENCY_NS=p50:%d,p95:%d,p99:%d%n",
                p50, p95, p99);
        System.out.printf(Locale.ROOT,
                "THROUGHPUT_OPS_PER_SEC=%.2f%n", throughput);

        if (agent) {
            System.out.println("PRE_RELEASE=accepted:"
                    + beforeRelease.accepted()
                    + ",dropped:" + beforeRelease.dropped()
                    + ",queued:" + beforeRelease.queued());
            System.out.println("EVENTS=attempted:"
                    + afterDrain.attempted()
                    + ",accepted:" + afterDrain.accepted()
                    + ",dropped:" + afterDrain.dropped()
                    + ",exported:" + afterDrain.exported()
                    + ",failed:" + afterDrain.failed()
                    + ",pending:" + afterDrain.pending()
                    + ",queued:" + afterDrain.queued());
        } else {
            System.out.println(
                    "EVENTS=attempted:0,accepted:0,dropped:0,"
                    + "exported:0,failed:0,pending:0,queued:0");
        }
        System.out.println("ASSERTIONS=PASS");
    }
}
```

### 7.2. Checking the Benchmark Logic

- **Warmup:** `service.work` runs 20,000 times before `Probe.recording` is enabled; warmup calls are excluded from the measurement phase `calls`. In an agent run, the hook may already be inserted, but `onEntry` returns immediately while recording is false.
- **Start gate:** Worker threads all wait on `CountDownLatch` before `durationNanos` starts; threads are not intentionally measured sequentially.
- **Result integrity:** `checksum` is computed from the return values of `work`; if an agent re-invokes the business method or alters its result, assertions fail.
- **Sampling:** Only 1 in every 32 invocations has its elapsed time measured directly to reduce measurement overhead. This is sampled method latency, not end-to-end HTTP request latency.
- **Percentiles:** The program sorts samples and takes nearest-rank p50/p95/p99. With small sample sizes, tail results are unstable; increase ops and use multiple JVM forks.
- **Business throughput:** Counts only completion of business tasks, excluding the time `releaseAndStop` waits for the exporter to drain.
- **Agent effectiveness check:** When `bench.agent=true`, `attempted == measured businessCalls`. If `-javaagent` is missing, the benchmark fails instead of reporting bogus overhead.
- **Deterministic stall:** When the gate is closed and there are more than 257 events, `dropped>0` must hold because there is no export path before the gate opens.

### 7.3. How Accurate Is It?

This code is a **teaching experiment for mechanics**, not a production-grade benchmark suite: JIT, GC, timer resolution, CPU quotas, background processes, `AtomicLong` contention, and safepoints still introduce noise. Do not conclude a fixed nanosecond overhead from a single run. For microbenchmarks, use JMH; for production services, run end-to-end request load tests.

## 8. Building and Running Each Case

Build once in the `slow-exporter-lab` directory:

```bash
mvn -q -DskipTests package
```

Maven Shade produces the expected JAR `target/slow-exporter-lab-1.0.0.jar`. The build succeeds when JDK 17+, Maven 3.x, and dependencies are available. The following commands all use **that same JAR**.

### 8.1. Baseline Without Agent

```bash
java -Dbench.threads=4 -Dbench.ops=20000 \
    -cp target/slow-exporter-lab-1.0.0.jar demo.Bench
```

Logically deterministic stdout lines:

```text
MODE=BASELINE
BUSINESS_CALLS=80000
CHECKSUM_OK=true
```

After those three lines come `LATENCY_NS` and `THROUGHPUT_OPS_PER_SEC` with **actual measured values**. At the end of the output:

```text
EVENTS=attempted:0,accepted:0,dropped:0,exported:0,failed:0,pending:0,queued:0
ASSERTIONS=PASS
```

Without an agent, no events are enqueued. Latency and throughput values **cannot be predicted precisely in advance**.

### 8.2. Agent with Fast Exporter

```bash
java -Dbench.threads=4 -Dbench.ops=20000 \
    -Dbench.agent=true -Dexport.delayMs=0 \
    -javaagent:target/slow-exporter-lab-1.0.0.jar \
    -cp target/slow-exporter-lab-1.0.0.jar demo.Bench
```

Stdout begins with:

```text
MODE=AGENT
BUSINESS_CALLS=80000
CHECKSUM_OK=true
```

The command also prints `PRE_RELEASE` and `EVENTS`, where `attempted=80000`; `accepted`, `dropped`, `exported`, and `pending` depend on producer/worker speed. **Even with `delayMs=0`, the 256-element queue can still fill up** if producers outpace the exporter, so `dropped=0` is never guaranteed.

### 8.3. Agent with Slow Exporter

```bash
java -Dbench.threads=4 -Dbench.ops=20000 \
    -Dbench.agent=true -Dexport.delayMs=10 \
    -Dexport.awaitMs=3000 \
    -javaagent:target/slow-exporter-lab-1.0.0.jar \
    -cp target/slow-exporter-lab-1.0.0.jar demo.Bench
```

`delayMs=10` simulates roughly 10 ms per event on the worker. With 80k calls, the worker is typically much slower than producers and the queue fills easily; however, do not **hardcode drop counts** because scheduler/CPU/JIT behavior affects them. Setting `export.awaitMs=3000` allows waiting up to 3 seconds to drain after business work finishes. If `pending>0` when the timeout expires, the unfinished backlog must be clearly reported.

### 8.4. Agent with Completely Stalled Exporter

```bash
java -Dbench.threads=4 -Dbench.ops=20000 \
    -Dbench.agent=true -Dexport.stall=true \
    -Dexport.delayMs=10 -Dexport.awaitMs=4000 \
    -javaagent:target/slow-exporter-lab-1.0.0.jar \
    -cp target/slow-exporter-lab-1.0.0.jar demo.Bench
```

When `export.stall=true`, the worker cannot send anything before `Bench` calls `releaseAndStop`, which happens **after all 80k business calls have completed**. The queue holds at most 256 events and at most one event can be in-flight. Therefore, **`dropped>0` is a deterministic invariant**; the program asserts it.

After the gate opens, the worker resumes processing. With a 4-second wait and `delayMs=10`, a small backlog may drain completely on a quiet machine, but if any `pending` events remain, they must not be reported as exported. The goal is to verify that **business logic does not wait for the exporter** during the measurement phase and that **the export pipeline has a recovery path**, not to force a fixed pending count.

### 8.5. Exporter Throwing Errors Periodically

```bash
java -Dbench.threads=4 -Dbench.ops=20000 \
    -Dbench.agent=true -Dexport.failEvery=4 \
    -Dexport.awaitMs=2000 \
    -javaagent:target/slow-exporter-lab-1.0.0.jar \
    -cp target/slow-exporter-lab-1.0.0.jar demo.Bench
```

If the worker processes at least four events, `failed` will increment; it continues processing subsequent events via the `catch(RuntimeException)` loop. Business checksum and call counts must still pass. `failed` does not increment `dropped` because the event was accepted by the queue and failed during worker delivery.

**Windows PowerShell:** put the `java` commands on a single line instead of using Bash's `\` line continuation. No real collector needs to be running.

## 9. Analyzing the Measurement Table

Fill in **actual** results after running multiple times:

| Case | Throughput ops/s | p50 ns | p95 ns | p99 ns | Drop rate | Pending | Business PASS |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| A baseline | *measure* | *measure* | *measure* | *measure* | 0 | 0 | yes/no |
| B fast | *measure* | *measure* | *measure* | *measure* | *measure* | *measure* | yes/no |
| C slow | *measure* | *measure* | *measure* | *measure* | *measure* | *measure* | yes/no |
| D stalled | *measure* | *measure* | *measure* | *measure* | **>0** | *measure* | yes/no |
| E failure | *measure* | *measure* | *measure* | *measure* | *measure* | *measure* | yes/no |

Do not fill in fake millisecond numbers and compute ratios from them. Use **multiple JVM forks** and record the JDK version/GC flags, warmup duration, sample count, and CPU quota/heap. Because the method is tiny, `nanoTime`/sampling overhead can be significant and p99 is hard to interpret; when official performance numbers are needed, add **JMH** and end-to-end load tests.

### 9.1. Reading Pipeline Accounting

**Illustrative example only**, not measured output:

```text
attempted=1000
accepted=257
dropped=743
exported=200
failed=10
pending=47
```

Check: `257 + 743 = 1000` and `200 + 10 + 47 = 257`. If a report only prints `exported=200`, the reader cannot tell that 743 events were dropped and 47 remain unprocessed. If application p99 stays healthy while event loss is high, report **business protected, telemetry fidelity reduced** rather than claiming everything is fine.

### 9.2. Arrival Rate and Service Rate Model

```text
Arrival rate  λ = events/s generated by the application
Service rate  μ = events/s processed by the exporter

λ < μ : backlog can decrease once the burst passes
λ > μ : backlog tends to grow toward capacity
        and requires dropping, sampling, or blocking
```

This is a simple model for reasoning about saturation, not a quantitative guarantee about the scheduler or JVM. With an unbounded queue, sustained `λ > μ` risks an `OutOfMemoryError`. A larger queue only buys **time**; it does not solve a sustained rate mismatch.

## 10. Choosing a Backpressure Policy for Your Data

| Policy | Business Impact | Telemetry Impact | Best Fit |
| --- | --- | --- | --- |
| **Drop newest** when queue is full | Does not wait for capacity | Loses newest events, needs a dropped metric | Tracing/metrics where sampling/loss is acceptable |
| Drop oldest | Does not wait for capacity if implemented properly | Loses oldest events, introduces bias | Only when policy permits |
| Block producer `put` | Can increase p99/timeouts | Preserves events better within memory bounds | Only when consistency requirements allow |
| Timed offer | Blocks at most timeout per event | May drop after timeout | When a clear latency budget exists |
| Head sampling | Reduces cost before creating events | Introduces declared sampling bias | High load needing cost control |
| Tail sampling | Decides after seeing trace outcome | Requires temporary state retention and memory budget | Retaining rare errors/spans |
| Batching | Does not block producers if done on worker | Latency/event size tradeoff | Network exporters |
| Retry/backoff | Should run only on the exporter worker | Can grow queue and cause duplicate attempts | Transient collector errors |
| Durable WAL/outbox | Incurs transaction/disk cost | Preserves events across restarts | Audit/financial compliance |

### 10.1. Why Not Use an Unbounded Queue?

An unbounded `LinkedBlockingQueue` can accumulate backlog for hours when a collector is down. Each event can retain objects, strings, stack traces, and classloaders; heap grows, GC pauses lengthen, and eventually the JVM crashes. A **bounded queue** combined with a drop, sampling, or durable policy is part of resource protection.

### 10.2. How Does Event Payload Affect Memory?

The lab uses only a `Long` timestamp. A real agent may retain a `Throwable` graph, request headers, user data, `Class<?>`, or servlet request objects. A 4 KiB event in a 100,000-element queue already consumes hundreds of MiB before queue/GC overhead. Do not hold references to entire object graphs when you only need a few IDs and redacted attributes.

### 10.3. Recovery Does Not Mean "Zero Data Loss"

When the exporter recovers, **already dropped** events do not come back. It only processes events that were still accepted/pending or generated afterward. Reducing data loss requires appropriate upstream sampling, controlled capacity increases, additional workers/batching, or durable storage. Never advertise exactly-once delivery based solely on retries: a lost ACK can cause an event to be sent multiple times.

## 11. Exporter Failures Must Not Alter Business Behavior

If a hook throws an exception on the request thread, the caller may see a telemetry error instead of the business result. In the lab, exporter failures are generated **on the worker** and caught there. `Probe.onEntry` only enqueues; risks from static initialization, CPU, or memory pressure still exist, which this experiment does not prove are completely eliminated.

Contrasting fragment example:

```java
// Wrong: sendBlocking can throw an exception to the caller.
public static void badHook() {
    remoteExporter.sendBlocking(event);
}

// Better model when the policy is fail-open:
public static void safeHook() {
    boolean accepted = boundedQueue.offer(event);
    if (!accepted) {
        droppedCounter.increment();
    }
}
```

This is **pseudocode** because `remoteExporter`, `event`, `boundedQueue`, and `droppedCounter` are not defined in a standalone file. Do not assume `safeHook` is completely immune to `OutOfMemoryError` or `LinkageError`. Initialize helpers early, limit allocations, avoid recursive instrumentation, and design a health indicator.

**Separate retries:** retrying event delivery on the worker can be valid; retrying **a business method** just because telemetry failed produces extra side effects and can be very dangerous. High-assurance audit/transaction data must follow a separate durable contract.

## 12. Comparing Microbenchmarks and Real Load Tests

### 12.1. Microbenchmarking with JMH

When measuring just a few ns/call, a hand-rolled benchmark can suffer from JIT dead-code elimination, code hoisting, timer resolution limits, and sampling bias. **JMH** provides forks/warmup/measurement and `Blackhole`; use it to quantify hook/queue/serialization cost at the method level.

However, JMH does not replace full-service load testing with thread pools, HTTP, DB, and networking. A hook that adds only a few tens of nanoseconds in a microbenchmark can still push request p99 up if the exporter consumes CPU or logging causes contention.

### 12.2. End-to-End Load Testing

Beyond a toy lab, track:

- Request rate, completed requests/s, reject/timeout/error counts.
- Request latency p50/p95/p99/p99.9 by endpoint type.
- CPU utilization, container throttling, heap allocation/op, and GC pauses.
- Export queue high-water mark, queue utilization, drops/s, failed sends/s.
- Export lag from event creation to collector acknowledgement.
- Backlog drain time and pending/lost counts at shutdown.
- Business method call counts, DB writes, messages, and return/exception contracts.

Test across multiple cycles: **healthy → slow → outage → recovery → shutdown**. An exporter that is fast for only the first 10 seconds does not tell you how the system survives a 30-minute outage.

### 12.3. Designing a Fair Comparison

Keep the same JDK vendor/version, GC/heap flags, CPU quota, inputs, artifacts, and load level. Run multiple forks, alternate the order of baseline/agent runs, and avoid enabling debuggers or profilers on only one group. Report the median and spread across runs rather than cherry-picking the best run. Note whenever container CPU is throttled or unusual GC pauses occur.

## 13. Testing Exceptions, Async, and Concurrency

Add these business variations to the lab:

1. **Method throws an exception:** verify that the contract's `Throwable` type/message/cause are preserved when the exporter fails. An entry-only hook must still not introduce a replacement exception.
2. **Method returns `CompletableFuture`:** event export errors must not `join` the future on the request thread, alter the result, or change cancellation/exceptional completion.
3. **Multiple business threads:** with 4/8/16 threads, the `AtomicLong` count and checksum remain exact; `LongAdder` event metrics must not lose counts due to counter races.
4. **Recursive methods:** a single logical request can generate multiple method-entry events. Distinguish **invocations** from **requests** when computing sampling.
5. **Repeated transformation:** if retransforming after load, ensure the same hook is not inserted twice. This lab is load-time only and does not prove idempotency by itself.
6. **Reentrant exporter:** do not instrument `Probe` itself or logging helpers, otherwise you risk recursion/`StackOverflowError` or deadlock.
7. **Exporter shutdown/death:** if the worker dies, producers must still have a clear timeout/queue policy rather than silently consuming unbounded RAM.

Also test return values, static/instance state, and external side effects. Good latency is not proof of business correctness.

## 14. Lab Limitations to State Explicitly

- **No real HTTP exporter:** `Thread.sleep` and injected `RuntimeException` do not simulate all network failures, TLS handshakes, retry jitter, 429/503 responses, partial ACKs, or duplicate deliveries.
- **No durability:** a daemon thread + in-memory queue can lose pending events when the JVM stops or crashes.
- **Not hard real-time:** `offer` does not wait for capacity, but it still involves lock contention and allocation/JIT/GC.
- **Not measuring every call:** latency is sampled only every 32 invocations; call counts are exact.
- **Warmup does not guarantee steady state:** JIT, GC, and branch profiles may continue changing.
- **Very short business method:** `AtomicLong` and the hook may represent a larger share of runtime than in a real application.
- **Bounded shutdown:** if `pending>0` after `join(timeout)`, the daemon worker continues running until process exit; do not treat this as a completed flush.
- **Separate process samples:** each `java` command starts a new JVM. Do not compare raw `nanoTime` values across processes; only compute durations.
- **Fatal VM errors not tested:** fail-open is demonstrated only for simulated exporter errors on the worker, not severe memory or OS errors.
- **No overhead number claimed before running:** stdout timings depend on the machine and must be measured yourself.

## 15. Diagnosing Anomalies

| Symptom | Likely Cause | How to Check |
| --- | --- | --- |
| `bench.agent=true` but `attempted=0` | Hook not installed, wrong manifest/name, or transformer failed | `-javaagent`, `Premain-Class`, ASM transform; assertion should fail |
| Business p99 rises with exporter delay | Synchronous export, `put`, `get`, `join`, lock, or sync logging on request path | Thread dumps and producer call paths |
| Throughput drops even though sampled p99 looks fine | CPU/GC/queue contention outside sampled calls | CPU/op, allocations, end-to-end throughput |
| `attempted != businessCalls` | Missing/duplicate hook, miscounted warmup, different sampling policy | Method owner/descriptor and recording window |
| `accepted + dropped != attempted` | Accounting bug or racing snapshot | Measure after producers finish, separate attempts |
| `accepted != exported + failed + pending` | Unaccounted drops, duplicate retries, bad snapshot | In-flight state, counters, terminal outcomes |
| `queued != pending` | An event is currently in the worker | This can be valid |
| No drops when exporter stalls | Gate opened too early, recording not enabled, or hook not running | Check `export.stall`, call count, capacity |
| Worker dies after one exporter exception | `catch` in wrong scope or uncaught error | Per-event exception handling, worker health |
| `failed=0` in failure case | Not enough send attempts or worker not released | `export.awaitMs`, send attempts, and queue |
| Agent causes `VerifyError` | Incorrect ASM frames/stack/method descriptor | `-Xverify:all`, test on target VM |
| Agent doubles business counter | Instrumenter re-invokes method or inserts duplicate hook | Dump class bytes, method count |
| JVM runs out of heap | Unbounded queue/large payloads or classloader leak | Bounded capacity, heap dump, allocation analysis |
| Slow recovery even when backend is healthy | Large backlog or retry storm | Pending age, batching, and concurrency |
| Shutdown hangs | Waiting indefinitely to flush | Deadline and loss reporting |
| Few drops but many errors | Worker repeatedly failing sends | Add backoff/circuit breaker/alerts |
| Many drops but business still PASSes | Business fail-open working, poor telemetry fidelity | Report both sides; tune sampling/capacity |
| Unstable measurement output | JIT/GC/CPU noise or small sample size | Increase workload, use multiple forks and JMH |

## 16. Experiment Checklist

- [ ] Include both no-agent baseline and fast-agent runs using the same JAR/JDK/configuration.
- [ ] Include slow exporter, stalled exporter, and failure injection.
- [ ] Business return values, checksum, and call counts remain correct across all cases.
- [ ] Agent mode requires `attempted == businessCallsMeasured` to avoid false PASSes.
- [ ] Queue has finite capacity and uses `offer` rather than `put`.
- [ ] Separate counters exist for attempted/accepted/dropped/exported/failed/pending.
- [ ] Stalled exporter with >257 events produces `dropped>0` without blocking business threads on capacity.
- [ ] After opening the gate, the worker has a recovery path; pending is reported rather than faked as exported.
- [ ] Exporter exceptions never propagate to business threads.
- [ ] Never re-run the business method to retry telemetry.
- [ ] Measure throughput and p50/p95/p99 during the business phase; separate drain time.
- [ ] Ensure warmup/sampling/forks are clearly documented.
- [ ] Measure CPU, allocation/GC, and contention, not just latency.
- [ ] For production tracing, measure event lag, collector ACKs, and drop rate.
- [ ] Have appropriate rate limiting, backoff, sampling, or circuit breakers.
- [ ] For lossless audit data, never replace durable storage with an in-memory drop queue.
- [ ] Have shutdown timeouts, health alerts, and a way to disable/rollback the agent.
- [ ] Test multiple agents/retransformation to rule out duplicate hooks.
- [ ] Protect event payloads from containing secrets or retaining request objects too long.
- [ ] Never claim measured nanosecond numbers without actually running the experiment.

## 17. Self-Check Questions

1. **If the exporter is 500 ms slow and the hook calls `sendBlocking` on the request thread, what is the impact?**  
   Yes, there is an impact: business latency can incur nearly the full wait time, causing timeouts and thread starvation.

2. **Does `ArrayBlockingQueue.offer` block when full like `put`?**  
   It does not wait for capacity; it returns `false`. However, it still has brief lock overhead and is not lock-free.

3. **Is `attempted=1000, accepted=257, dropped=743` valid?**  
   Yes: `257 + 743 = 1000`. You still need to inspect exported, failed, and pending for the 257 accepted events.

4. **If `accepted=257, exported=200, failed=10`, what is `pending`?**  
   47; you must not report that 257 events were successfully sent.

5. **Why can `pending` be greater than `queueSize`?**  
   The worker may have polled an event from the queue and is currently processing it.

6. **Why does a stalled gate deterministically produce `dropped>0` with 80k calls?**  
   The queue capacity is only 256 and the worker is held, so at most one more event is in-flight; the remaining events have no room.

7. **Should an exporter failure retry the business method?**  
   No. Retries belong in telemetry delivery, without causing a second business side effect.

8. **Does an agent with `delayMs=0` guarantee `drop=0`?**  
   No. Producers can outpace the worker even without any sleep.

9. **Why not include the 4-second drain in business throughput?**  
   We want to measure how fast business methods complete; exporter flushing is a separate metric.

10. **If the worker fails to send an event and continues, can business logic be preserved?**  
    Yes, under a fail-open policy for errors handled on the worker; you still need to check business assertions and resource pressure.

11. **Does JMH replace end-to-end HTTP load testing?**  
    No. JMH measures micro-costs, whereas tail request latency involves thread pools, GC, networking, and concurrency.

12. **An unbounded queue avoids drops—is it definitely better?**  
    No. During a prolonged exporter outage, the backlog can exhaust the heap and crash the application.

13. **Does `pending=0` prove no events were lost?**  
    No. Many events may have been `dropped` or `failed`; you must check all counters.

14. **Why does an "agent loaded" status not prove overhead was measured accurately?**  
    The transformer might not match the target class or might fail; you must assert that probe attempts match business invocations.

15. **If an app uses tracing sampling, what should `attempted` mean?**  
    Define clearly whether it means hook attempts or post-sampling event candidates; keep `sampledOut` separate from capacity drops.

16. **For mandatory lossless audit events, should you drop events when the queue is full to protect p99?**  
    Do not decide that unilaterally. You must use a durable pipeline/transactional outbox and an approved transaction/latency policy.

17. **Does negative overhead in a single benchmark run prove the agent improves performance?**  
    No. That can be JIT/GC/scheduler noise; multiple forks and variance analysis are required.

18. **Can you consider the exporter recovered just because a single "resumed" line is logged?**  
    No. You need to see `exported` advancing, `pending` decreasing, business SLAs holding, and loss accounting remaining accurate.

## 18. References

1. Oracle JDK 17 — **`ArrayBlockingQueue`** and `offer`/`put`/`poll`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html
2. Oracle JDK 17 — **`CountDownLatch`**, one-shot gate: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html
3. Oracle JDK 17 — **`ClassFileTransformer`**, `classfileBuffer`, returning `null` or new bytes: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html
4. Oracle JDK 17 — **`Instrumentation`**, `addTransformer`, retransform rules: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
5. Oracle JDK 17 — **`java.lang.instrument` package**, `Premain-Class` and `premain`: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
6. Oracle JDK 17 — **`LongAdder`**, multi-threaded counters: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html
7. Oracle JDK 17 — **`Future`/`ExecutorService`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html
8. Oracle JDK 17 — **`System.nanoTime()`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html
9. ASM — **`AdviceAdapter`**, `ClassWriter`, and visitor API: https://asm.ow2.io/javadoc/org/objectweb/asm/commons/AdviceAdapter.html
10. ASM — versions/releases: https://asm.ow2.io/
11. OpenJDK **JMH** microbenchmark: https://github.com/openjdk/jmh
12. Oracle JDK 17 — **`ThreadPoolExecutor`**, unbounded/bounded queues: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html

**Conclusion:** For an agent to withstand a slow exporter, it must be designed with a **bounded queue, an explicit backpressure policy, isolation of exporter errors from the business path, accounting for event loss/pending, and a bounded-deadline shutdown**. Measure with baseline/fast/slow/stalled/failure runs, verifying business correctness and latency/throughput together. When the exporter recovers, only events still accepted/pending can continue being sent; already dropped events **do not come back on their own**.
