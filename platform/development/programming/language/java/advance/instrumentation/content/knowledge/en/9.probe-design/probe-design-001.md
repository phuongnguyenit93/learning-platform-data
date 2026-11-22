# Choosing Instrumentation Points by the Question to Answer Rather Than Instrumenting Every Method

> **Design Principle:** An *instrumentation point* is not chosen by asking "How many methods can we inject bytecode into?", but by asking **"Once the data appears, what operational question will we answer and what decision will we make?"**. Measuring the right business, dependency, or queue boundary is usually far more useful than inserting timers/logs into every method. Indiscriminate instrumentation can incur massive CPU, allocation, I/O, trace size, and label data costs while still failing to explain the end-to-end experience.

This lesson belongs to the **Probe Design** topic of Java Advance – instrumentation. It presents how to turn a hypothesis into a minimal list of instrumentation points, identify suitable signals, design filters for `ClassFileTransformer`, control overhead, and verify with a runnable startup Java agent on JDK 17+.

## 1. Start With a Question, Not a Method List

Suppose a payment API has the symptom: "Recently checkout has been slow, even though the server is not overloaded." An unfocused approach is to measure every method in the `com.shop` package: `toString()`, getters, `validate()`, `price()`, `charge()`, serializers, repositories, helpers, and thousands of framework calls. A huge amount of data is collected, yet the question **"Where is checkout slow?"** may still remain unanswered.

Instead, ask three questions in sequence:

1. **What is affected?** End-to-end latency, error rate, order count, latency of a dependency, or queue wait time?
2. **Which boundary produces an observable outcome?** When a request arrives and sends a response; when a checkout operation starts/ends; when calling the payment gateway and receiving a result; when enqueuing/dequeuing; when acquiring a connection from a pool?
3. **What decision will be made after measuring?** Scaling the service, optimizing a query, lowering a timeout, draining a queue backlog, tuning the connection pool, rolling back a release, or simply adding one more span to narrow down further?

If you cannot explain how a piece of data will change the operations team's actions, that instrumentation point does not yet have a strong enough justification to be enabled by default in production.

### Example Question Tree

~~~text
Symptom: checkout p95 increased
    |
    +-- Did p95 at HTTP ingress increase?
    |       |
    |       +-- Yes: measure request boundary (route, status, duration)
    |       |
    |       +-- No: check client, proxy, network outside the service
    |
    +-- Is the checkout span/operation slow?
            |
            +-- Yes: selectively break down into payment call, database wait, queue wait
            |
            +-- No: inspect pre/post-checkout overhead, serialization, or HTTP transport
~~~

This is an **analytical diagram**, not an assumption that every system has these exact layers. A measurement on `CheckoutService.checkout()` only covers code running inside that method; it **does not automatically measure** the time a request waits at the load balancer, servlet queue, HTTP parsing, or writing the response to the network.

## 2. Translating Questions into Meaningful Signals and Instrumentation Points

A quick selection table:

| Question to answer | Recommended signal | Priority instrumentation point | Avoid before having evidence |
| --- | --- | --- | --- |
| "Which route is slow for customers?" | Latency histogram, request count, error rate | HTTP server boundary, using route template | Timers on every getter, entity, serializer |
| "Which step in checkout takes time?" | Overall checkout span + child spans for suspected dependencies | `checkout()`, `PaymentGateway.charge()`, DB wait points if any | Creating spans for every small calculation helper |
| "Where do transaction errors come from?" | Error count by outcome type, normalized exception class | Boundary where errors are determined/caught and dependency return points | Logging the same exception at every stack frame |
| "Is the queue growing because of producers or consumers?" | Queue depth, enqueue/dequeue times, processing time, retry count | Message send, processing start, completion/ack | Measuring every method inside the worker |
| "Is the connection pool causing a bottleneck?" | Acquire wait time, timeout rate, pool utilization | `DataSource.getConnection()` or pool hook | Measuring every DAO without knowing wait time |
| "Is latency increasing due to allocation/JIT/GC?" | Allocation/CPU profile, GC metrics, JFR events | Profiler/JFR, JVM metrics | Replacing every method with heavy timers |
| "Is a remote call timing out?" | Duration, attempt count, outcome, retry/backoff | Outbound RPC/HTTP client boundary | Adding logs to every internal HTTP layer |

**Start with signals that are cheap, stable, and directly answer the question.** For example, p95 requires a distribution (a histogram or a source with enough data to compute quantiles); it cannot be derived from `sum(duration)/count`. Only after observing that checkout is slow in a specific segment should you add instrumentation inside that segment.

A good instrumentation point must have: an **operation name**, a **start point**, an **end point**, an **outcome**, **necessary attributes**, and an **owner**. Without an end boundary, duration usually cannot be measured; without an outcome, high latency due to timeouts and high latency due to successful processing can get mixed together.

## 3. Defining Measurement Boundaries by Semantics, Not Method Count

### 3.1. Business and Dependency Boundaries

For example, a transaction calls:

~~~text
HTTP POST /checkouts/{id}
   |
   v
CheckoutController
   |
   v
CheckoutService.checkout(sku)     <-- operation/business boundary
   +--> Catalog.price(sku)        <-- internal helper
   +--> PaymentGateway.charge(x)  <-- dependency boundary
   +--> AuditEvent.write(...)     <-- depends on configuration
   |
   v
HTTP response                      <-- request boundary
~~~

In the first pass, you can place **one HTTP-server metric/span** and **one checkout instrumentation point**. If checkout is the source of increased latency, add an instrumentation point for `PaymentGateway.charge(...)`. Only add `Catalog.price(...)` if it carries real risk (e.g., calling a pricing service over the network, cache miss, I/O), not simply because it is also a method.

There is a distinction:

- **HTTP boundary** lets you evaluate the request experience **within the server's scope**.
- **Checkout boundary** lets you evaluate the business operation; it can be invoked from HTTP, a batch job, or a message consumer.
- **Dependency boundary** lets you identify latency/errors caused by another service or database.
- **Pure CPU helper calls** can usually be measured with a sampling profiler when needed, instead of creating millions of spans.

### 3.2. Entry/Exit Must Match Exactly One Unit of Work

To measure synchronous duration in the JVM, start right before the operation and end on every exit path:

~~~java
long started = System.nanoTime();
try {
    return operation();
} finally {
    long elapsedNanos = System.nanoTime() - started;
    // Record one observation for this operation.
}
~~~

This is an **illustrative code snippet**, not a standalone program. `System.nanoTime()` is the appropriate clock for measuring **relative elapsed time within the same JVM**, not a wall-clock timestamp; do not arbitrarily substitute `System.currentTimeMillis()` when measuring elapsed time.

Start/end timing must be chosen precisely:

- Measuring `PaymentGateway.charge(...)` includes the time the caller code actually spends inside that method call, but **does not** automatically include any external retries or prior queue wait.
- If an operation returns a `CompletableFuture` immediately, a timer around the **call that creates the future** only measures *scheduling* time, not until the async work completes. To measure an end-to-end asynchronous operation, you must close the span/record the observation when the future finishes (and handle exceptional completion/cancellation).
- For streams, consumers, or message processing, define whether "completed" means message received, business logic processed, or **successfully acknowledged**. Without agreement, two teams may measure the same operation with two different meanings.
- For exceptions, `finally` ensures recording one observation when the operation exits due to an error. The `success` status must be based on business semantics, not automatically treating every exception as HTTP 500.

### 3.3. Avoid Double Counting Yourself

If a request calls `CheckoutService.checkout` and inside it calls `PaymentGateway.charge`, the durations of both are **nested**. Do not sum the two durations into "total request time" because that **double-counts the overlapping interval**. Tracing represents parent/child relationships; per-operation metrics must be analyzed by operation name and boundary.

Similarly, logging the same exception in the HTTP filter, controller, service, repository, and interceptor can create multiple log entries for **a single error**. You need to designate the layer responsible for final logging and use trace correlation when tracing the path instead of duplicating stack traces everywhere.

## 4. Choosing the Right Signal for the Goal: Metrics, Traces, Logs, or Profiler?

| Signal | Answers well | Cost/Limitations |
| --- | --- | --- |
| **Metrics** (counter, histogram, gauge) | Trends, SLI/SLO, error rates, p95/p99 by route/operation | Usually low cost if labels are bounded; does not pinpoint individual calls within a request |
| **Traces** (root span + child spans) | Which call is slow, dependency order, retries | Must propagate context properly across threads/async; too many spans increase overhead |
| **Structured logs** | Context of an anomalous event, error type, fallback decision | Avoid logging every method and sensitive data; can attach trace ID |
| **Profiler/JFR** | Hot methods, allocation, lock contention, CPU/GC | Suitable for discovering unknown bottlenecks; does not always carry business semantics |

A specific question may require a **combination of signals**:

- SLI "checkout p95" → histogram metric by route or operation.
- Knowing p95 increased but not knowing why → trace on checkout and suspected dependencies.
- Knowing payment timed out → one log with sufficient context at the error-handling point, linked to the trace.
- Knowing CPU increased during requests → CPU/allocation profile/JFR to find hot paths before adding more instrumentation.

**Sample with purpose:** metrics used for rate/error SLIs typically need full counting or a clear statistical adjustment mechanism. Detailed traces can be sampled, sometimes prioritizing keeping error/slow traces according to an appropriate policy. Do not use an arbitrarily sampled set of traces to claim an accurate error rate for all traffic.

**Low-cardinality labels/attributes:** group by `http.route="/orders/{id}"` or `operation="checkout"`; do not create a series for each `orderId`, `userId`, request ID, or raw URL. Errors should be grouped into `timeout`, `rejected`, `invalid_input`, or controlled exception classes, rather than taking the entire message containing variable information. Monitoring libraries may enforce **cardinality limits**, but those limits do not make an inappropriate label useful.

## 5. Choosing a Minimal Set of Instrumentation Points and Expanding Based on Evidence

A process that can be applied to every observability requirement:

1. **Write down the operational question** and the required precision: "Did p95 on the checkout route increase because of payment or internal computation?" rather than "record the time of every method."
2. **Draw a minimal execution path** of the work: entry, operation, high-impact dependencies, queue boundaries, exit. Only a responsibility map is needed, not a full call graph yet.
3. **Pick 1–3 priority instrumentation points** for the initial hypothesis: HTTP request boundary, checkout operation, and payment dependency. Explicitly note what **not** to instrument in this round.
4. **Define signal names, labels, outcomes, and recording timing**: `checkout.duration`, `checkout.result`, `payment.attempts`; label by bounded business codes rather than user IDs.
5. **Estimate overhead/cardinality**: invocations/sec, clock reads, extra object allocations, exported bytes, export retries, number of series/spans, and potential backpressure. Attach observation thresholds and a kill switch.
6. **Verify semantics with tests**: a successful operation, an exception, retries, concurrency, and asynchronous completion if applicable. Confirm exact observation counts, unchanged business results, and no data leaks.
7. **Roll out to canary** and compare latency, CPU, allocation, memory, export queue, and telemetry volume. Only expand scope when new data provides additional actionable diagnostic capability.
8. **Stop when the question is answered**: do not add instrumentation for `equals`/getters just because you can.

For example, if the checkout span increases while the payment span does not, the "slow gateway" hypothesis weakens. Then you can measure pool wait, transaction locks, or allocations inside checkout. This approach is more economical and less noisy than turning every method into a span.

## 6. Runnable Java 17+ Example: Instrumenting Exactly One Operation

The following example uses a **startup Java agent with a real `ClassFileTransformer`**. To avoid depending on Byte Buddy/ASM in this lesson, we prepare **two structurally identical versions** of `CheckoutService.class` using `javac`:

- Original version: executes checkout logic, **does not record metrics**.
- Instrumented version: has **one measurement added around `checkout()`**; does not modify `Catalog.price()` or `PaymentGateway.charge()`.

The transformer only swaps bytes when the JVM defines the class named `CheckoutService`. This is a way to test **selecting an instrumentation point** on a specific class; in a production agent, the transformer typically generates valid bytecode using a bytecode library and filters by **exact method + descriptor** within the class, rather than loading a pre-built replacement class file.

The experiment can be run with JDK 17+ and **requires no dependencies outside the JDK**.

### 6.1. Create the Original Business Logic

**`Catalog.java`**

~~~java
public final class Catalog {
    public int price(String sku) {
        return switch (sku) {
            case "book" -> 1200;
            case "desk" -> 3500;
            default -> throw new IllegalArgumentException("unknown sku");
        };
    }
}
~~~

**`PaymentGateway.java`**

~~~java
public final class PaymentGateway {
    public void charge(int cents) {
        if (cents <= 0) throw new IllegalArgumentException("invalid amount");
    }
}
~~~

These two classes only simulate synchronous dependencies. There is no network, database, or real payment; any measured duration, if displayed, reflects the experiment code and **must not be used as a payment latency benchmark**.

**`CheckoutService.java`** placed in the root directory:

~~~java
public final class CheckoutService {
    private final Catalog catalog = new Catalog();
    private final PaymentGateway payment = new PaymentGateway();

    public void checkout(String sku) {
        int cents = catalog.price(sku);
        payment.charge(cents);
    }
}
~~~

At the initial stage, **do not instrument `price` or `charge`**. The initial question is "how many checkouts succeed/fail at the business boundary?" — measuring once at `checkout` is enough.

### 6.2. Build a Simple Measurement Aggregator

**`Measurements.java`**

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.LongAdder;

public final class Measurements {
    private static final AtomicInteger successes = new AtomicInteger();
    private static final AtomicInteger failures = new AtomicInteger();
    private static final LongAdder durationNanos = new LongAdder();

    private Measurements() {}

    public static void record(String operation, boolean success, long elapsedNanos) {
        if (!"checkout".equals(operation)) return;
        if (success) successes.incrementAndGet();
        else failures.incrementAndGet();
        durationNanos.add(elapsedNanos);
    }

    public static int successCount() { return successes.get(); }
    public static int failureCount() { return failures.get(); }
    public static long totalDurationNanos() { return durationNanos.sum(); }
}
~~~

`AtomicInteger` and `LongAdder` serve a simple thread-safe experiment; `durationNanos` only stores **total duration**, so **p95 cannot be computed** from it. In a real application, use a histogram with bounded cardinality and an appropriate exporter/sampling. The demo counter has no user ID or SKU labels to avoid high-dimensional series.

**`instrumented/CheckoutService.java`** placed in the `instrumented` subdirectory:

~~~java
public final class CheckoutService {
    private final Catalog catalog = new Catalog();
    private final PaymentGateway payment = new PaymentGateway();

    public void checkout(String sku) {
        long started = System.nanoTime();
        boolean success = false;
        try {
            int cents = catalog.price(sku);
            payment.charge(cents);
            success = true;
        } finally {
            Measurements.record("checkout", success, System.nanoTime() - started);
        }
    }
}
~~~

This is the **replacement class file** version and must not be added to the application's classpath directory. Because `record` is in `finally`, both the success branch and an exception from `Catalog.price` produce **one observation**. The business exception is not caught and is still propagated to the caller.

In production, the telemetry hook also needs a mechanism so that errors from the exporter or observability library **do not accidentally mask business exceptions**, and synchronous I/O should be avoided on the hot path. This exercise uses in-JVM atomic counters, so no network export occurs.

### 6.3. Write a Transformer That Selects Only One Target Class

**`SelectiveTransformer.java`**

~~~java
import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;

public final class SelectiveTransformer implements ClassFileTransformer {
    private final byte[] checkoutBytes;

    public SelectiveTransformer(byte[] checkoutBytes) {
        this.checkoutBytes = checkoutBytes.clone();
    }

    @Override
    public byte[] transform(Module module, ClassLoader loader, String className,
                            Class<?> beingRedefined, ProtectionDomain domain,
                            byte[] classfileBuffer) {
        if (!"CheckoutService".equals(className)) return null;
        System.out.println("instrumented=CheckoutService");
        return checkoutBytes.clone();
    }
}
~~~

The filter **only** matches the JVM internal name `CheckoutService`; other classes pass through via `return null`. For a class in the `com.shop.service` package, the callback name is typically `com/shop/service/CheckoutService`, not `com.shop.service.CheckoutService`.

**Important:** this example has only one default class loader and two class versions with the same name and member layout. In an app with multiple class loaders/modules, you should not return a replacement class file to any loader that happens to have the same name; filter by class loader/module/class version and method descriptor as needed. A transformer must also avoid instrumenting its own helper classes to prevent class-loading recursion.

**`SelectionAgent.java`**

~~~java
import java.io.IOException;
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;

public final class SelectionAgent {
    public static void premain(String args, Instrumentation inst) throws IOException {
        byte[] checkoutBytes = Files.readAllBytes(Path.of("instrumented/CheckoutService.class"));
        inst.addTransformer(new SelectiveTransformer(checkoutBytes));
    }
}
~~~

The agent reads the bytes **before registering**, so the callback only checks the class name and returns the byte array. `Can-Retransform-Classes` is not needed for this example because the checkout class is loaded **after `premain`**, at its first definition. The path `instrumented/CheckoutService.class` is relative to the **working directory when running `java`**.

**`agent.mf`**:

~~~text
Manifest-Version: 1.0
Premain-Class: SelectionAgent
~~~

The manifest needs a trailing newline, so save it in proper JAR manifest text format.

### 6.4. Program to Verify Observation Counts

**`App.java`**

~~~java
public final class App {
    public static void main(String[] args) {
        CheckoutService checkout = new CheckoutService();
        checkout.checkout("book");
        checkout.checkout("desk");
        try {
            checkout.checkout("missing");
        } catch (IllegalArgumentException expected) {
            System.out.println("business_error=" + expected.getMessage());
        }
        System.out.println("success_count=" + Measurements.successCount());
        System.out.println("failure_count=" + Measurements.failureCount());
    }
}
~~~

We have **two valid transactions** and **one failed transaction**. If the instrumentation point is placed correctly, the result must be **2 successes, 1 failure** — even though `Catalog.price()` and `PaymentGateway.charge()` are called multiple times. This is an important test: total observations correspond to **operations**, not total method invocations.

### 6.5. Compile and Run With/Without the Agent

From the root directory containing `Catalog.java`, `PaymentGateway.java`, `CheckoutService.java`, `Measurements.java`, `App.java`, `SelectiveTransformer.java`, `SelectionAgent.java`, `agent.mf`, and the `instrumented/CheckoutService.java` directory:

~~~bash
javac --release 17 Catalog.java PaymentGateway.java CheckoutService.java Measurements.java App.java SelectiveTransformer.java SelectionAgent.java

javac --release 17 -classpath . -d instrumented instrumented/CheckoutService.java

jar --create --file selection-agent.jar --manifest agent.mf SelectionAgent.class SelectiveTransformer.class

java App
java -javaagent:selection-agent.jar App
~~~

The `javac --release 17` command ensures Java 17 compatible syntax and classfiles. Only use the **original `CheckoutService.class`** on the application classpath; the replacement in `instrumented/` is read as data by the agent. The agent JAR must contain **`SelectionAgent.class`** and **`SelectiveTransformer.class`**.

**Running without the agent**, stdout:

~~~text
business_error=unknown sku
success_count=0
failure_count=0
~~~

This is the baseline: the application still executes checkout and catches the business error properly, but the original `CheckoutService` class **records no telemetry**.

**Running with the agent**, stdout:

~~~text
instrumented=CheckoutService
business_error=unknown sku
success_count=2
failure_count=1
~~~

This pair of results was compiled with `javac --release 17` and run on OpenJDK 21. If you run with a different JDK/JVM, a wrong working directory, or a class already loaded before the agent, results may differ; verify the exact bytecode and command line before drawing conclusions.

### 6.6. Why the Example Proves Question-Driven Probe Selection

| Verified observation | Design implication |
| --- | --- |
| Only `instrumented=CheckoutService` appears | The transformer focuses on **one class**, not attempting to transform every class in the JVM |
| `success_count=2` and `failure_count=1` are counted | The instrumentation point at the checkout boundary fits the question "how many operations succeeded/failed?" |
| The `unknown sku` error appears in both modes | Adding measurement does not alter exception semantics in this exercise |
| No `instrumented=Catalog` or `instrumented=PaymentGateway` log | You do not need to inject into helpers to answer the initial question |
| Only total nanos are stored in the demo | Must switch to a histogram if the real question is **p95 latency**, rather than claiming to compute p95 from a sum |

The example uses a **pre-compiled variant class file** to easily verify the mechanism, rather than illustrating a full ASM/Byte Buddy pipeline. In a real agent, prefer patching the exact method on the incoming class bytes instead of replacing the entire class with a pre-built file.

## 7. Safely Selecting Classes and Methods When Using `ClassFileTransformer`

### 7.1. Two Filtering Layers

To reduce overhead and avoid instrumenting the wrong targets:

**Layer 1 — inside the class callback**: check module, loader, `className`, namespace, and excluded class lists. For unrelated classes, `return null` immediately. Do not parse the bytecode of every class if you are only tracking one operation.

**Layer 2 — after selecting the class**: the bytecode library selects only the exact **method name + descriptor** and necessary constraints (e.g., `checkout(Ljava/lang/String;)V`), avoiding matching all overloads with the same name. Check whether the method is already instrumented to avoid double-injection during retransform/redefine passes.

~~~text
ClassFileTransformer.transform(...)
    |
    +-- className not in allowlist --> return null
    |
    +-- agent/library/framework helper --> return null
    |
    +-- wrong loader/module --> return null
    |
    +-- parse only the selected class
            |
            +-- target method name + descriptor?
            |       |
            |       +-- No --> leave method unchanged
            |       +-- Yes --> insert valid start/end/outcome hook
            |
            +-- return new bytes only if the class actually changed
~~~

Java Instrumentation does not provide a built-in method-level matcher in `transform`; the callback receives **class-file bytes**. To modify methods, the transformer must parse/generate valid classfiles or use a JDK-compatible supporting library.

### 7.2. Context-Aware Filtering

- **Class loader:** the same internal class name can be defined by multiple loaders; a policy for service A is not automatically valid for service B.
- **Module:** in JPMS applications, check the module and readability/access to helper classes when new bytecode invokes them; a loader being able to see a class does not guarantee proper module access.
- **Lifecycle:** a startup agent can intercept classes as they are defined; dynamic attach may arrive after classes are already loaded. For already-loaded classes, appropriate retransformation/redefinition capabilities, `isModifiableClass` checks, and structural change limits are required.
- **Canary/filter:** allowlists by service/route/operation or sampling rates must be independent of sensitive business input. It should be possible to disable a specific hook type individually to reduce overhead during an incident.
- **Callback errors:** a transformer producing invalid classfiles can prevent classes from loading; test across target JDKs and realistic bytecode patterns. Do not just test counter values while ignoring startup/class loading.

## 8. Overhead, Cardinality, and Instrumentation Points to Avoid

Every instrumentation point has a cost: clock reads, conditional branches, context propagation, object allocations, atomic updates, trace storage, exporter flushing, and backend queries. In particular, a **small per-invocation cost** can become significant when a method sits in a hot loop; the number of instrumented methods **does not reflect total overhead as directly** as invocation frequency.

Warning signs:

- Instrumenting every getter/constructor generates tens of millions of events even when the question only concerns a single HTTP request.
- Recording spans for very short pure-CPU operations leads to many spans with no business meaning.
- Tagging metric labels with `orderId`, raw URL, token, email, or request ID creates high time-series cardinality and information-leak risks.
- Exporting telemetry synchronously on the request thread impacts the very latency being measured; a slow exporter can create a feedback loop.
- Logging exceptions at every layer both wastes resources and makes one error look like multiple incidents.
- Putting a timer around `CompletableFuture.supplyAsync(...)` and concluding that it is the actual async processing time.
- Measuring multiple nested intervals and directly summing them into end-to-end latency.

**Safe approach:** prefer low-cardinality counters/histograms, tracing along semantic spans, bounded queues/exporters, purposeful sampling, and profiling when discovering CPU paths. If a clear question is not yet formed, measure at a few stable boundaries and use a profiler/JFR to form hypotheses before injecting more probes.

**Measuring real overhead:** compare canary runs with instrumentation on vs. off under the same traffic and same JVM, checking p50/p95/p99, CPU, allocation, GC, memory, span/metric series counts, queue lag, and drop rate. Do not treat `elapsedNanos` of the hot hook itself as complete evidence of system overhead: enabling an agent can affect JIT compilation, allocation, and backpressure.

## 9. Pre-Deployment Correctness Verification

| Aspect | Minimum test | Consequence if skipped |
| --- | --- | --- |
| **Semantics** | Both success and exception preserve original business behavior | Hook masks original errors or alters return values |
| **Counting** | One checkout produces exactly one observation; retries are clearly defined | Metric counts do not match operation counts |
| **Boundary** | Distinguish HTTP end-to-end, checkout, payment call, queue wait | Misattributed blame when latency rises |
| **Async** | Test future success, failure, and cancellation | Span closes too early or leaks span/context |
| **Concurrency** | Multiple threads increment counters accurately; no global request state | Miscounting or data cross-talk between requests |
| **Labels** | Allowlist route/outcome values; no IDs/PII | High cardinality and privacy risk |
| **Class filtering** | Exact internal class name, loader, module, method descriptor | Wrong class instrumented or linkage errors |
| **Startup/lifecycle** | Agent loads, helper classes available, rollback/toggle works | JVM fails to start or hook is hard to disable |
| **Cost** | A/B canary on target workload and JDK | Measurement degrades latency |
| **Signal observability** | Dashboard can query by operation and outcome | Events exist but still cannot answer the question |

Remember that **not every metric, span, or log is injected by a `ClassFileTransformer`**. A Java agent can instrument framework boundaries, use JFR/JMX, register listeners, or use the application's telemetry APIs. How you choose instrumentation points always starts from the question and semantics; the instrumentation mechanism comes second.

## 10. Reasoning and Decision Exercises

**Scenario A — "request p95 increased":** You have 300 methods and are allowed to add only three initial instrumentation points. What do you choose?

A reasonable choice: HTTP server duration by route, the main business operation, and the most suspected dependency. If requests queue before reaching the handler, queue wait is a strong candidate. Do not assume every system has these exact three boundaries; final choices depend on the actual architecture diagram.

**Scenario B — "a transaction has six helper methods":** If a checkout calls six synchronous helpers, do you need six metric observations for "successful checkouts"?

No. Record **one outcome at the checkout boundary**. Counting helper invocations answers a different question and can inflate results if interpreted as transaction counts.

**Scenario C — "checkout is known to be slow, but the component is unclear":** Should you add every method or selective spans for `PaymentGateway.charge` and DB wait points?

Add boundaries backed by a hypothesis that can change operational decisions. If the results are still insufficient, narrow down further with a profiler or additional targeted probes.

**Scenario D — "API uses async":** A timer around the future-creating call records 2 ms; the future completes after 700 ms. Can you report business latency as 2 ms?

No, if the question is the time until the operation completes. You must measure through completion/cancellation and propagate context across the async boundary.

**Scenario E — "metric has too many series":** A metric contains `http.route` and `userId`, with constantly changing userIds. Should you add logging to every method for debugging?

No. Remove high-cardinality labels from the metric, use a route template and stable outcomes, and use sampled traces plus logs with trace IDs when investigating a specific request; never export sensitive information just for extra detail.

## 11. Checklist for Choosing Instrumentation Points in a Java Agent

- [ ] Can the question be written as **one short sentence**, with an action if the answer is A/B?
- [ ] Is the **unit of measurement** clearly identified: request, checkout, dependency call, queue wait, or message processing?
- [ ] Do you know **when the operation starts and ends**, including exceptions, retries, and async?
- [ ] Do you know which signal fits best: metric, trace, log, JFR/profiler, without forcing every signal from a single timer?
- [ ] Did you choose the smallest set of instrumentation points to distinguish meaningful hypotheses?
- [ ] Are labels/attributes bounded, containing no IDs or sensitive data?
- [ ] Are class/module/loader and method descriptor filters in place when applying `ClassFileTransformer`?
- [ ] Are there tests for startup, valid classfiles, code equivalence, concurrency, and rollback?
- [ ] Is there a plan to measure overhead and disable hooks in production?
- [ ] Is every metric and span tied to **a specific operational question**?

**Conclusion:** Quality instrumentation is not about "how many methods are transformed" but **the fewest instrumentation points that still provide enough information to make the right decision**. Start from the question, pick boundaries, define semantics, verify via output, and expand only when evidence shows more data is needed.

### References

- [Java SE 17 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): callback contract and classfile bytes.
- [Java SE 17 — `Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): registering/removing transformers and redefine/retransform capabilities.
- [OpenTelemetry — HTTP span semantic conventions](https://opentelemetry.io/docs/specs/semconv/http/http-spans/): naming by route template and HTTP boundaries.
- [OpenTelemetry — Metrics overview](https://opentelemetry.io/docs/concepts/signals/metrics/): metric cost, cardinality, and cardinality-reduction mechanisms.
- [OpenTelemetry — Metrics SDK specification](https://opentelemetry.io/docs/specs/otel/metrics/sdk/): attribute filtering and metric data point limits.
