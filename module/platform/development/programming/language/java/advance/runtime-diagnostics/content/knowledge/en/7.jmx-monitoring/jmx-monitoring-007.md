# 7.7 Exposing custom application metrics MBeans with appropriate data types

## Learning objectives

JMX (Java Management Extensions) does not provide only JVM metrics like heap, GC, or threads. A Java service can **register application-owned MBeans** so administrative tools can observe completed requests, failed requests, backlog, in-flight tasks, health status, or the state of a business component.

The hard part is not writing a getter that returns an integer; the hard part is **exposing the right semantics and data types**, avoiding lost counts under concurrent updates, avoiding heavy load on every client poll, and preventing a management MBean from accidentally exposing runtime mutation rights.

After this lesson, you will be able to:

- Distinguish **Standard MBean**, **MXBean**, and **Dynamic MBean**, choosing the right option for Java 17.
- Design JMX attributes with meaningful data types: `long` counter, `int`/`long` gauge, `double` ratio, `boolean` health flag, bounded `String` state.
- Know when to expose a snapshot using **Open Types**, `CompositeData`, or `TabularData`, instead of passing custom Java objects over JMX.
- Build a **read-only** Standard MBean using an `*MBean` interface, `StandardMBean`, `MBeanServer`, and `ObjectName`.
- Verify actual names, types, and read/write permissions using `getAttribute()` and `getMBeanInfo()`.
- Update counters and gauges safely across multiple threads; explain the limits of getters read at different instants.
- Run a standalone Java 17 program with deterministic stdout and a keep-alive mode for observing via local JConsole.
- Write a metrics specification covering units, reset semantics, scope, cardinality, sampling window, security, and multi-replica aggregation.

## 1. What is an MBean, and why do applications need custom MBeans?

A **Managed Bean (MBean)** is a Java object whose management interface is exposed through an **MBeanServer**. Authorized clients can read attributes, invoke exposed operations, and sometimes receive notifications. An MBean does not have to be a traditional JavaBean; it follows JMX conventions and metadata rules.

```text
Application / Java service
  ├── Business requests and background jobs
  │     └── update component counters/gauges
  ├── Metrics implementation
  └── Management interface (MBean/MXBean)
                 │
                 v
        Platform MBeanServer
                 │
      Unique ObjectName in JVM
                 │
        ┌────────┴─────────┐
        v                  v
     JConsole        JMX connector/exporter
                      → monitoring system
```

**What an MBean provides:**

- **Attribute:** a named, typed value; getter `getRequestsTotal()` exposes attribute `RequestsTotal`.
- **Operation:** an action exposed for clients to invoke; e.g., `resetCache()` if and only if you intentionally expose it.
- **Notification:** an event pushed to listeners per the JMX mechanism.
- **Metadata:** `MBeanInfo` describing names, types, readability/writability, operations, and more.

For observation-only metrics, **the interface should contain only getters**. Never add setters or side-effecting operations to a metrics MBean just for convenience. An application-specific MBean forms part of an **operational contract**: dashboards can depend on attribute names, ObjectNames, and data types across many deployments.

**Critical scope:** each JVM has its own platform MBeanServer; `RequestsTotal` on replica A is **replica A's** counter, not automatically the cluster-wide total. When scaling across replicas, the monitoring system must attach instance identity and aggregation rules.

## 2. Standard MBean, MXBean, or Dynamic MBean?

| Type | Model | Benefits | When appropriate |
| --- | --- | --- | --- |
| Standard MBean | Public interface ending in `MBean`, getters/setters and operations per JMX conventions | Simple, readable schema, easy to test | Basic metrics with primitive/`String` types |
| MXBean | Public interface ending in `MXBean` or annotated `@MXBean`; values mapped to Open Types | Clients do not need custom application data classes | Multi-field snapshots, supported structs/maps/lists |
| Dynamic MBean | Custom implementation of `DynamicMBean` and metadata/attribute access | Flexible when schema is genuinely dynamic | Frameworks, custom diagnostic engines |
| `StandardMBean` wrapper | Uses `StandardMBean(implementation, interfaceClass, false)` for Standard MBean | Exposes the exact chosen interface regardless of implementation class name | Single-file demos, implementation names not matching naming convention |

**Default Standard MBean:** per JMX conventions, class `CheckoutMetrics` implements public interface `CheckoutMetricsMBean`. A `boolean isHealthy()` becomes attribute `Healthy`; `long getRequestsTotal()` becomes attribute `RequestsTotal`.

This lesson's example uses `StandardMBean(..., false)` to explicitly designate the **management interface**. The `false` argument here means **do not create an MXBean**. The JDK also supports `StandardMBean(..., true)` when building an MXBean from a compliant interface.

**There is no need for Dynamic MBean** just to return a counter and a ratio. Manually managing dynamic `MBeanInfo`/`getAttribute` adds complexity, type mismatches, and schema drift risk.

## 3. Choosing data types suited to the measurement

| Metric | Quantity kind | Java/JMX type | Definition and unit |
| --- | --- | --- | --- |
| Completed requests | Cumulative counter | `long` | Count; since instance startup |
| Failed completed requests | Cumulative counter | `long` | Count; clear failure definition |
| In-flight requests | Instantaneous gauge | `int` or `long` | Current request count |
| Queued tasks | Instantaneous gauge | `int`/`long` | Queue depth, measured at read time |
| Error ratio | Ratio | `double` | Fraction from 0 to 1 |
| Utilization ratio | Ratio | `double` | Fraction 0–1, explicit denominator |
| Meets health criteria? | Boolean | `boolean` | `true`/`false` |
| Lifecycle state | Categorical value | `String` | Finite set: `STARTING`, `RUNNING`, `DRAINING`, etc. |
| Last success time | Timestamp | `long` | Unix epoch milliseconds |
| Total queue wait time | Duration accumulator | `long` | Nanoseconds or milliseconds, explicitly documented |
| Latency p95 | Snapshot quantile | `double` | Milliseconds, **must** include window and sample count |

### 3.1 Counter: use `long` for cumulative counts

A counter increments on a defined event and **never decreases** during a normal instance lifetime. `RequestsTotal` is not RPS; you need the **difference between two samples**:

```text
Rate(T1,T2) =
  (RequestsTotal(T2) - RequestsTotal(T1)) / elapsedSeconds
```

For example, if a JVM completes 240 requests in 30 seconds, the average rate in that window is **8 requests/second**, provided the counter did not reset. If the JVM restarts during the window, detect the reset and never treat a negative delta as throughput.

`long` avoids the small ceiling of `int` in long-running services. Never use `double` for exact integer counts just because dashboards prefer floats; large integers lose precision in floating-point representation.

A counter needs a clear contract:

- Does `RequestsTotal` count requests **started**, **received**, or **completed**?
- Are retries counted as separate requests?
- Does `FailuresTotal` include 5xx, timeouts, validation/business errors, or uncaught exceptions?
- Do both share the exact same instance/lifecycle scope?

A pretty name without a definition is still an untrustworthy metric.

### 3.2 Gauge: values that can go up and down

`InFlight` is the number of currently executing requests; it is not a lifetime counter.

```text
T1 InFlight=5
T2 InFlight=17
T3 InFlight=2
```

All three values are valid. A gauge must increment on entry and **decrement exactly once** when processing ends, including on exceptions, cancellations, or timeouts. An appropriate `finally` block helps prevent missed decrements.

`QueueDepth` should read from the actual queue mechanism. Calling `size()` on a queue does not necessarily give an exact snapshot under concurrent modifications; check the queue/JDK implementation's contract. Never invoke APIs that scan millions of elements inside a getter just to get queue size.

### 3.3 Ratio: `double` with an explicit denominator

Under the **completed requests** contract, cumulative ratio:

```text
RequestsTotal = 300
FailuresTotal = 9
ErrorRatio = 9 / 300 = 0.03 = 3%
```

`0.03` in `ErrorRatio` means **3%**, not **0.03%**. If you want `3.0`, name it `ErrorPercent` and document 0–100; never mix the two conventions.

When the denominator is 0, decide and publish a no-data policy. The Java demo below returns `0.0` before any completed request, meaning **"no errors recorded yet" per demo convention**, not proof the system is healthy. Analytical systems may need `HasSamples` or sample-count metadata.

`NaN` and infinity can break or complicate JMX clients, exporters, or time-series pipelines; avoid using them casually to represent no-data.

### 3.4 Boolean and String: do not turn them into ambiguous text or numbers

`boolean isHealthy()` creates a JMX attribute named `Healthy` of type Boolean. Returning `String "true"` forces clients to parse text and risks incompatibility. Returning `int 0/1` fits only when a numeric code contract is intentionally defined; never convert clear two-state booleans into numbers casually.

`String getState()` suits a finite state set. Avoid placing stack traces, personal data, request IDs, tokens, or arbitrary error messages inside a `String` attribute. Those belong in logs/traces with dedicated access controls.

A Boolean `Healthy=true` **does not automatically prove** an endpoint responds fast; document exact health criteria, e.g., "component loaded config, essential dependency connections ready, accepting new tasks."

### 3.5 Timestamps and durations are not the same type

- `LastSuccessEpochMillis`: `long` milliseconds since Unix epoch; used to align timelines across systems.
- `QueueWaitNanosTotal`: `long` cumulative nanoseconds; supports deltas and averages when paired with a corresponding task counter.
- `System.nanoTime()`: suited for measuring **elapsed deltas inside one JVM**, not UTC epoch timestamps.
- Never return `String "23 ms"` when dashboards need numeric math; return numbers and specify units in names/docs.

## 4. Designing a metrics contract before coding

Example checkout component management contract:

| Attribute | Type | Kind | Unit | Rule |
| --- | --- | --- | --- | --- |
| `RequestsTotal` | `long` | Counter | requests | Increments once when a request completes |
| `FailuresTotal` | `long` | Counter | requests | Increments for a failed completed request |
| `InFlight` | `int` | Gauge | requests | Increments on start, decrements on completion |
| `ErrorRatio` | `double` | Ratio | fraction 0–1 | `FailuresTotal / RequestsTotal`, returns 0 if denominator is 0 |
| `Healthy` | `boolean` | State | — | Defined readiness/health criteria |
| `State` | `String` | State | enum-like | `STARTING`, `RUNNING`, `DRAINING`, `STOPPED` |

At the contract level, also document: owner, where updates occur, thread-safety, reset policy, time scale, and missing-data semantics. Dedicated p95/p99 metrics should specify **window** and estimation method. Without proper distribution data, never put a fake p95 number into JMX.

Crucial point: each getter may be invoked independently by a JMX client. Never assume `ErrorRatio` was computed from the **exact same atomic snapshot** of `RequestsTotal` and `FailuresTotal` read moments earlier while requests continue completing.

## 5. Choosing clear ObjectNames with bounded cardinality

Every MBean is registered under a `javax.management.ObjectName`. Common form:

```text
domain:key1=value1,key2=value2
```

Example:

```text
demo.metrics:type=Checkout,name=Primary
```

Code:

```java
ObjectName name = new ObjectName(
        "demo.metrics:type=Checkout,name=Primary");
```

This snippet belongs inside a method handling `MalformedObjectNameException`. For a real service JVM, the domain is typically organization-owned, such as `com.example.app.metrics`.

**Never use unbounded values** in an ObjectName:

- Never create an MBean per request, session, order, or user.
- Never use emails, customer IDs, or trace IDs as `name=...`.
- Never build keys/values from URLs containing dynamic IDs without normalization.
- Never concatenate arbitrary input containing `,`, `=`, `:`, `*`, or `?` into an ObjectName unchecked.

`ObjectName.quote(value)` quotes a **key property value** containing special characters; it does not replace cardinality controls or the rule against leaking PII. `ObjectName` has distinct syntax rules for quoted vs. unquoted values.

A usable schema:

```text
com.example.app.metrics:type=WorkerPool,name=Payments
com.example.app.metrics:type=Cache,name=Products
com.example.app.metrics:type=Queue,name=Invoices
```

Names stable across rollouts keep dashboard queries resilient. One `ObjectName` can appear across multiple JVMs: cluster-wide identity must combine **service/instance/pod** at the monitoring layer.

The MBeanServer enforces **unique ObjectNames per server**. Collisions cause `registerMBean` to throw `InstanceAlreadyExistsException`. Never unregister another component's bean just to "steal the name."

## 6. Read-only Standard MBean: getters and interface

A simple management interface:

```java
public interface CheckoutMetricsMBean {
    long getRequestsTotal();
    long getFailuresTotal();
    int getInFlight();
    double getErrorRatio();
    boolean isHealthy();
    String getState();
}
```

This is an **illustrative interface snippet**; the standalone program in section 9 declares an equivalent interface inside the public class.

With JMX:

- `getRequestsTotal()` → attribute `RequestsTotal`, type `long`.
- `getInFlight()` → attribute `InFlight`, type `int`.
- `getErrorRatio()` → attribute `ErrorRatio`, type `double`.
- `isHealthy()` → attribute `Healthy`, type `boolean`.
- `getState()` → attribute `State`, type `java.lang.String`.
- **No corresponding setters:** all attributes are **read-only**.

If you add `void resetAllCounters()` **to the management interface**, JMX exposes it as an **operation**, even if you only intended it as a helper. Since our goal here is metrics, omit side-effecting operations from observation interfaces.

Omitting setters on your custom MBean reduces control surface, yet **does not make remote JMX read-only overall**: the platform MBeanServer still hosts other MBeans with state-mutating operations. Connector security must still be managed separately.

## 7. Thread-safety and what getters are allowed to do

Java services usually handle concurrent requests. If multiple threads run `requestsTotal++` on an ordinary field without proper synchronization, **updates get lost**. If one thread writes state while another reads without visibility guarantees, getters see stale data.

Common choices:

- `AtomicLong`: cumulative counters via `incrementAndGet`, `get`.
- `AtomicInteger`: gauges needing thread-safe increment/decrement.
- `LongAdder`: high-contention counters updated heavily by many threads, though `sum()` is **not an atomic snapshot** while updates continue.
- `volatile boolean`/`volatile String`: publishes latest state across threads per the Java Memory Model.
- `AtomicReference<ImmutableSnapshot>`: when multiple fields **must remain mutually consistent**.
- Very short-held locks: usable to preserve complex invariants, avoiding long lock holds inside JMX getters.

### 7.1 Request lifecycle needs paired begin/finish

Integration snippet (`failed` must be initialized before `try`):

```java
metrics.beginRequest();
boolean failed = false;
try {
    // Invoke request handling logic.
} catch (RuntimeException ex) {
    failed = true;
    throw ex;
} finally {
    metrics.finishRequest(failed);
}
```

In practice, HTTP errors, timeouts, or cancellations may bypass this exact `catch`; place `finishRequest` and classify failures consistently with your framework/lifecycle. Also ensure no code path calls finish **twice**, driving `InFlight` negative.

### 7.2 Multiple getters do not form a joint snapshot

Example while workers are still running:

```text
T1: client reads RequestsTotal = 100
T2: several requests finish, including failures
T3: client reads FailuresTotal = 11
T4: client reads ErrorRatio = 0.101
```

Numbers will not necessarily match when dividing values fetched at different instants. Even bulk `getAttributes()` does not automatically guarantee atomicity across getters.

When a report requires a mutually consistent tuple, build an immutable snapshot published with proper synchronization and expose it as a single composite MXBean/Open Type attribute. For trend monitoring, reading independent counters in the same window is usually sufficient.

**Never** hold a service-wide lock just so JMX clients can read every attribute "strictly consistently": heavy locking can inflate the very request latency you are investigating.

### 7.3 JMX getters must be lightweight and side-effect-free

Avoid getters that perform:

```java
// DO NOT put these tasks in periodically polled getters:
// 1. Scanning all heap objects to compute a histogram.
// 2. Querying a database/network to count items on every poll.
// 3. Sorting millions of latency samples to compute p99.
// 4. Writing large log files, resetting counters, or mutating component state.
```

Instead, update metrics along the processing path or via budgeted periodic snapshots. JMX getters only read prepared values. Document update lag explicitly if snapshots are not instantaneous.

## 8. MBeanServer, metadata, and lifecycle

Obtain the JVM's shared server:

```java
MBeanServer server =
        ManagementFactory.getPlatformMBeanServer();
```

Register:

```java
StandardMBean bean = new StandardMBean(
        metrics, CheckoutMetricsMBean.class, false);
server.registerMBean(bean, objectName);
```

These are integration snippets; `metrics`, `objectName`, and imports are provided in the complete example below.

After registration, clients can read:

```java
Object value = server.getAttribute(objectName, "RequestsTotal");
MBeanInfo info = server.getMBeanInfo(objectName);
```

**Verify using real metadata:**

- `MBeanAttributeInfo.getName()`: attribute name.
- `getType()`: exposed type.
- `isReadable()`: readable flag.
- `isWritable()`: writable flag.
- `MBeanInfo.getOperations()`: exposed operations.

Never inspect the Java implementation class and assume every method is exposed; the management interface defines the Standard MBean schema.

When the component shuts down, `server.unregisterMBean(objectName)` cleans up the registry. In apps with component restarts/reloads, track ownership carefully so you never blindly unregister a bean replaced by a new owner. A bean holding references to stale state objects yields stale metrics and leaks memory.

## 9. Complete Java 17 example: read-only Standard MBean

The program below:

1. Defines a public management interface with six strongly typed getters.
2. Uses `AtomicLong` and `AtomicInteger` to update metrics from a simulated scenario.
3. Registers via `StandardMBean` with an explicitly selected interface.
4. Reads attributes through `MBeanServer` (not merely calling the implementation directly).
5. Inspects metadata to confirm six attributes and **none writable**.
6. Unregisters inside `finally`.
7. Supports a `serve` mode keeping the JVM alive ~60 seconds for observation via local JConsole.

Create **`AppJmxMetricsDemo.java`**:

```java
import java.lang.management.ManagementFactory;
import java.util.Arrays;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import javax.management.StandardMBean;

public class AppJmxMetricsDemo {
    public interface CheckoutMetricsMBean {
        long getRequestsTotal();
        long getFailuresTotal();
        int getInFlight();
        double getErrorRatio();
        boolean isHealthy();
        String getState();
    }

    public static final class CheckoutMetrics
            implements CheckoutMetricsMBean {
        private final AtomicLong completed = new AtomicLong();
        private final AtomicLong failed = new AtomicLong();
        private final AtomicInteger inFlight = new AtomicInteger();
        private volatile boolean healthy = true;
        private volatile String state = "RUNNING";

        // Internal updates, not exposed as JMX operations.
        void beginRequest() {
            inFlight.incrementAndGet();
        }

        void finishRequest(boolean requestFailed) {
            completed.incrementAndGet();
            if (requestFailed) {
                failed.incrementAndGet();
            }
            inFlight.decrementAndGet();
        }

        @Override
        public long getRequestsTotal() {
            return completed.get();
        }

        @Override
        public long getFailuresTotal() {
            return failed.get();
        }

        @Override
        public int getInFlight() {
            return inFlight.get();
        }

        @Override
        public double getErrorRatio() {
            long total = completed.get();
            return total == 0 ? 0.0
                    : (double) failed.get() / total;
        }

        @Override
        public boolean isHealthy() {
            return healthy;
        }

        @Override
        public String getState() {
            return state;
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length > 1 ||
                (args.length == 1 && !args[0].equals("serve"))) {
            System.out.println(
                    "Usage: java AppJmxMetricsDemo [serve]");
            return;
        }

        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
                "demo.metrics:type=Checkout,name=Primary");

        CheckoutMetrics metrics = new CheckoutMetrics();
        StandardMBean bean = new StandardMBean(
                metrics, CheckoutMetricsMBean.class, false);

        server.registerMBean(bean, name);
        try {
            metrics.beginRequest();
            metrics.finishRequest(false);

            metrics.beginRequest();
            metrics.finishRequest(true);

            metrics.beginRequest();
            metrics.finishRequest(false);

            System.out.println("registered="
                    + server.isRegistered(name));
            System.out.println("requestsTotal="
                    + server.getAttribute(name, "RequestsTotal"));
            System.out.println("failuresTotal="
                    + server.getAttribute(name, "FailuresTotal"));
            System.out.println("inFlight="
                    + server.getAttribute(name, "InFlight"));

            double errorRatio = (Double) server.getAttribute(
                    name, "ErrorRatio");
            System.out.printf(Locale.ROOT,
                    "errorRatio=%.4f%n", errorRatio);

            System.out.println("healthy="
                    + server.getAttribute(name, "Healthy"));
            System.out.println("state="
                    + server.getAttribute(name, "State"));

            MBeanInfo info = server.getMBeanInfo(name);
            MBeanAttributeInfo[] attrs = info.getAttributes();
            boolean allReadOnly = Arrays.stream(attrs)
                    .allMatch(a -> a.isReadable() && !a.isWritable());

            System.out.println("attributeCount=" + attrs.length);
            System.out.println("allReadOnly=" + allReadOnly);

            if (args.length == 1) {
                System.out.println("localPid="
                        + ProcessHandle.current().pid());
                Thread.sleep(60_000L);
            }
        } finally {
            server.unregisterMBean(name);
        }
        System.out.println("unregistered="
                + !server.isRegistered(name));
    }
}
```

Compile and run:

```bash
javac AppJmxMetricsDemo.java
java AppJmxMetricsDemo
```

**Exact stdout** in zero-argument mode on a standard Java 17 JVM with JMX:

```text
registered=true
requestsTotal=3
failuresTotal=1
inFlight=0
errorRatio=0.3333
healthy=true
state=RUNNING
attributeCount=6
allReadOnly=true
unregistered=true
```

**Output explanation:**

- The MBean registers and `server.isRegistered(name)` returns `true`.
- Three `beginRequest()`/`finishRequest()` pairs produce `RequestsTotal=3`, `FailuresTotal=1`, `InFlight=0`.
- `ErrorRatio=1/3` is formatted with `Locale.ROOT` as `0.3333`; JMX still returns type `double`.
- `isHealthy()` produces `Healthy=true`; the sample state is `RUNNING`.
- The interface declares six getters and no setters, so all six JMX attributes are read-only.
- `unregisterMBean` runs in `finally`; afterward `isRegistered(name)` returns `false`.

**Important:** the demo simulates three **sequential** requests so stdout stays deterministic; it does not prove invariants hold under every production race. `healthy=true` is an initialized demo flag, not a real health check.

### 9.1 Observing live via local JConsole

Run:

```bash
java AppJmxMetricsDemo serve
```

This mode prints `localPid=<PID>` and keeps the JVM alive for about **60 seconds**. Within that window, launch JConsole from a desktop JDK:

```bash
jconsole
```

Select the local Java process matching the printed PID and locate in the MBeans tree:

```text
demo.metrics:type=Checkout,name=Primary
```

UI versions may group `type`/`name` slightly differently; locate by **ObjectName** and verify the six attributes, their types, and read-only status. No remote JMX port is needed for this lab.

The `serve` mode has no fixed stdout because PID and timing depend on the machine. If attach fails, check JDK tools, OS permissions, whether the process is still alive, and local monitoring support; never conclude "the service has no MBean" from an attach failure alone.

### 9.2 Why do clients use MBeanServer instead of calling the implementation directly?

A remote JMX client holds no Java object reference to the `CheckoutMetrics` instance inside another JVM. It uses an **ObjectName** with `MBeanServerConnection` or a proxy. Primitive/`String` types are broadly supported by JMX and Java clients.

A client reading `RequestsTotal` from `MBeanServer` receives a boxed `Long` matching Java `long`. Metric contracts should not depend on internal classes absent from the client's classpath.

### 9.3 What if registration fails?

- `InstanceAlreadyExistsException`: the ObjectName already exists in the same server.
- `NotCompliantMBeanException`: the object/interface violates JMX conventions.
- `MBeanRegistrationException`: an error occurred during registration lifecycle callbacks.
- `MalformedObjectNameException`: invalid ObjectName syntax (when constructing `ObjectName`).

Never automatically delete another component's colliding bean. In real services, handle startup errors with clear context and ownership; unregister only the beans **you registered** when the component shuts down.

## 10. When are MXBeans and Open Types needed?

When exposing multi-field data so clients lacking your custom model classes can still read it, **MXBeans** are helpful because supported Java types map onto **JMX Open Types**.

**Illustrative** contract example (requires an implementation to run):

```java
import javax.management.MXBean;

@MXBean
public interface CacheView {
    long getEntriesTotal();
    java.util.Map<String, Long> getEntriesByTier();
}
```

MXBeans define mappings to `SimpleType`, `ArrayType`, `CompositeType`, and `TabularType`, with `CompositeData` and `TabularData` representing composite structures on the JMX side.

| Data type | When appropriate | What to watch out for |
| --- | --- | --- |
| Primitive, wrapper, `String` | Simple counter/gauge/ratio/status | Document units and semantics |
| Enum with stable value set | Finite states | Do not rename schema/values casually |
| `CompositeData` from a snapshot | Multiple fields needed together in one read | Clear mapping/metadata; snapshot taken consistently |
| `TabularData` from a small map/table | Breakdown across a few bounded dimensions | Limit cardinality and response size |
| Custom Java object in Standard MBean | Internal Java client sharing the same model | Remote clients may need the class; prefer MXBean/Open Types for wide compatibility |

An **immutable snapshot** holding `sampleEpochMillis`, `completed`, `failed`, and `inFlight` can be captured under proper synchronization and exposed as a single composite MXBean attribute. That gives consumers a tighter, mutually consistent tuple than multiple independent getter calls.

Even with MXBeans, not every arbitrary Java object maps automatically; check the Javadoc and test on your target JDK. Never turn a `Map<String,Long>` with millions of request IDs into a massive `TabularData` just because the interface allows it.

## 11. Why high cardinality is still dangerous with a single MBean

There are two kinds of cardinality:

1. **MBean cardinality:** number of ObjectNames in the registry. One MBean per session/user/order is dangerous.
2. **Attribute value cardinality:** even a single MBean returning a `Map<String,Long>` with millions of keys can grow too huge.

For monitoring:

- Pool/cache/dependency names should be a finite documented set.
- Operation groups should be normalized, e.g., `READ`, `WRITE`, `DELETE`.
- Never put URL paths with dynamic IDs or user-supplied strings into metric labels.
- Send per-request details to logs/traces with trace IDs rather than JMX.
- Cap entry counts, payload sizes, and getter execution time.

Application availability matters far more than exporting "every dimension" on one monitoring endpoint.

## 12. Read-only metrics vs. administrative operations

Certain methods should not appear on a default metrics interface:

```java
void resetCounters();
void clearCache();
void drainWorkerPool();
void setHealthy(boolean value);
```

These are **side-effecting** methods. Exposing them on the MBean turns it into a runtime control API, not just telemetry.

If business workflows genuinely need a control plane, separate the interface/object and permissions, enforce auditing, verify identity, and build rollback/guardrails. Never grant periodic dashboards permission to reset counters just because both live in the same `MBeanServer`.

**Note:** a getter can also cause accidental side effects if its implementation queries a DB, clears a cache, creates files, or holds locks. "Read-only" must hold in both **schema** and **implementation**.

## 13. Integrating with JMX exporters and time-series monitoring

JMX is commonly **polled** periodically by a collector. For example, an exporter reads `RequestsTotal` every 15 seconds and translates it into time series. The exporter must configure the right **metric type**, units, and labels; JMX does not turn `RequestsTotal` into a semantically valid Prometheus Counter automatically.

Key points:

- Lifetime counter: compute rates/increases per instance and handle restarts/resets.
- Gauge: use current values, never `rate` by default.
- Ratio: distinguish lifetime ratios from rolling/window error ratios.
- Percentiles: never average per-replica p95s to obtain global p95.
- Missing data: JMX disconnect / exporter failure means **no sample**, not zero.
- Poll timing skew: two attributes read milliseconds apart are not an atomic snapshot.
- Java process restarts: instance identity and uptime/start timestamps detect resets.
- Sampling frequency: never poll so aggressively that getters contend for CPU/locks.
- Cardinality: domain/keys/schema must remain stable across rollouts.

A counter can drop after a restart:

```text
09:00 RequestsTotal = 152000
09:01 RequestsTotal = 153800
09:02 JVM restarted
09:03 RequestsTotal = 230
```

Never compute `230 - 153800` as negative throughput. The pipeline must detect the instance reset and handle it properly.

### 13.1 Rolling vs. lifetime error ratio

`ErrorRatio` in the demo is the ratio since JVM startup. In a long-running service, a brief error burst can be "diluted" by millions of earlier successful requests.

Over window `[T1,T2]` on the same instance with no reset:

```text
windowErrorRatio =
    delta(FailuresTotal) / delta(RequestsTotal)
```

Compute only when the delta of completed requests exceeds 0; otherwise keep a no-data state. Never alert on "error ratio below 0.1%" using a lifetime metric if your goal is detecting an outage in the last 5 minutes.

### 13.2 How should quantiles/histograms be exposed?

If p95/p99 latency is needed:

- Document units (`Millis`/`Seconds`), window size, sample count, and estimation method.
- Never sort a list of all requests on client poll; use pre-aggregated histograms/snapshots.
- Never average per-replica p95s to claim cluster-wide p95.
- To compute global quantiles, export histogram buckets/distributions aggregatable by supported methods.
- Handle `Double.NaN`/Infinity per pipeline contract; never emit them as fake metrics.
- Never serialize histogram buckets as one hard-to-parse long `String`; use Open Types or proper metric exporters.

## 14. Local JMX, remote JMX, and security

**Local JMX** is helpful when a developer inspects a Java process on the same host. **Remote JMX** is a sensitive control surface because the platform MBeanServer can contain MBeans with operations affecting the application or JVM.

Principles:

- Never open public remote JMX ports or disable authentication/TLS just to debug.
- Enforce network controls, identity, authorization, auditing, and least privilege.
- Never place tokens, passwords, or customer IDs in ObjectNames or `String` attributes.
- In container environments, verify the **exact PID, container, pod, JVM build, and timeframe**.
- Separate metric-reading permissions from configuration-changing operations on other MBeans.
- If external clients need metrics, prefer a secured exporter exposing only necessary figures.

Even when your custom MBean is strictly read-only, that does not change policies on other platform MBeans. Never treat the presence of one read-only `*MBean` interface as proof remote JMX is safe.

## 15. Workflow for implementing metrics MBeans in a Java service

### Step 1 — Define the concrete diagnostic question

For instance: "Did failed requests rise in the last 5 minutes?", "Is the pool backed up?", or "Are workers processing tasks or blocked on dependencies?" Expose measurements that drive decisions rather than every internal field.

### Step 2 — Write the contract

Specify name, ObjectName, data type, counter/gauge/ratio/state, unit, update trigger, reset semantics, no-data rule, concurrency/snapshot guarantees, owner, and consumers.

### Step 3 — Instrument at the right business boundary

Ensure the completed counter increments once; failures are classified consistently; `InFlight` cleans up even on errors; health/state reflects explicit criteria. Never increment counters only when logging succeeds, since logging failures are not business failures.

### Step 4 — Register the MBean with proper lifecycle

Use bounded, stable ObjectNames. Register once the component has real state, handle collisions and startup rollback cleanly, and unregister on shutdown. Never register per request.

### Step 5 — Test via real JMX APIs

Query `isRegistered`, `getMBeanInfo`, and `getAttribute` to confirm names, types, and read-only schema. The section 9 demo serves as a baseline for this step.

### Step 6 — Concurrency stress test

Drive concurrent requests including failures, timeouts, and cancellations. Reconcile counters against task totals; verify `InFlight` never goes negative or leaks. Verify metric getters do not contend heavily on locks with request processing.

### Step 7 — Test exporter and dashboards

Verify metric type mapping, units, labels, resets/restarts, missing data, multi-replica aggregation, and alerts. Never stop at checking that a chart "shows numbers."

### Step 8 — Monitor cost and security

Test polling at target cadence; measure overhead, response size, remote permissions, and schema compatibility. Document measurement limits and a change plan as the API evolves.

## 16. Three diagnostic scenarios

### 16.1 RequestsTotal climbs slowly while InFlight and QueueDepth rise

This points toward a backlog or slow downstream processing, yet **is not enough** to blame CPU or locks alone. Cross-check offered/completed RPS, latency, queue wait, thread dumps/JFR, CPU/GC, and dependency traces over the same window. Never blindly raise thread pool sizes.

### 16.2 Healthy=true while the service returns many timeouts

A `Healthy` flag is only as strong as **its implementation criteria**. If it merely checks "process alive," a service can report `healthy=true` while queues overflow or critical dependencies fail. Separate liveness, readiness, and degraded states; add error ratio metrics and sound health policies.

### 16.3 MBean appears in staging yet is missing in production

Verify exact build/PID/container, component initialization, ObjectName, and exporter queries. Check for `InstanceAlreadyExistsException`, `NotCompliantMBeanException`, JMX permissions, connector/agent errors, and unregistration. A blank dashboard **does not prove** the bean does not exist.

## 17. Operational specification template

```text
COMPONENT
- Service/build/JDK, owner:
- ObjectName domain/key schema:
- Scope: JVM instance/replica/component:
- Expected number of MBeans and cardinality cap:

METRIC CONTRACT
- Attribute name:
- Type: long/int/double/boolean/String/Open Type:
- Kind: counter/gauge/ratio/state:
- Unit, bounds and no-data rule:
- Precise update trigger:
- Reset/restart behavior and lifetime/window:
- Concurrency and snapshot consistency guarantees:
- Sensitive-data classification:

COLLECTION
- Local JMX / authenticated remote JMX / exporter:
- Poll interval, timeout and failure behavior:
- Exported metric type/name/units/labels:
- Multi-instance aggregation rule:

VALIDATION
- MBeanInfo name/type/readable/writable:
- Functional events vs observed values:
- Parallel load, failure/cancellation coverage:
- Restart/reset, missing data and scale-out:
- Getter overhead and access-control review:

CONCLUSION
- Observations backed by measurements:
- Limits: window, race, stale data, scope:
- Known unsupported questions:
- Change owner and rollback criteria:
```

This is a **report template**, not numbers observed from a real JVM. Record evidence, environment, versions, and timestamps so others can verify.

## 18. Common mistakes

1. **Returning Strings for every number.** Loses type safety, forces parsing, breaks on units/locales.
2. **Using `int` for lifetime counters.** Risks overflow over long uptimes.
3. **Using `double` for integer counts.** Unsuitable for exact counting.
4. **Confusing `RequestsTotal` with requests/second.** Rates require deltas over time.
5. **Confusing `ErrorRatio` 0–1 with `ErrorPercent` 0–100.** Dashboards can be off by 100x.
6. **Lumping all errors into `FailuresTotal` without defining failure.** Prevents comparing endpoints/versions.
7. **Failing to decrement `InFlight` on errors.** Causes phantom gauge drift.
8. **Incrementing counters with `++` on non-thread-safe fields.** Loses updates.
9. **Expecting separate getters to return an atomic snapshot.** Each getter runs at a different instant.
10. **Using a health boolean as sole proof of SLO compliance.** Misses latency, correctness, and capacity.
11. **Scanning DBs or sorting histograms inside getters.** Polling can degrade the service.
12. **Exposing reset/shutdown operations in metrics interfaces.** Increases configuration/admin risk.
13. **Registering MBeans per request, user, or session.** Explodes cardinality and privacy risks.
14. **Putting untrusted input into ObjectNames.** Risks syntax errors or unintended wildcards/patterns.
15. **Failing to unregister on component shutdown.** Stale beans retain old state and objects.
16. **Deleting colliding beans without knowing the owner.** Can break another component's monitoring.
17. **Assuming MXBeans accept arbitrary Java objects.** Must follow Open Type mapping rules.
18. **Using oversized dynamic `Map`s in an MXBean.** Still creates cardinality and response-size risk.
19. **Averaging p95 across replicas.** Never produces an accurate global percentile.
20. **Turning missing data into 0.** Hides exporter/JMX failures.
21. **Ignoring counter resets after JVM restarts.** Causes negative rates or false alerts.
22. **Renaming attributes or changing types without migration.** Breaks dashboards and alerts.
23. **Testing only sequential demos.** Does not prove concurrency correctness.
24. **Opening remote JMX without auth/TLS.** Widens the attack surface for the entire JVM, not just your metrics.
25. **Confusing single-instance metrics with cluster totals.** Requires instance identity and aggregation rules.
26. **Omitting the window on p95/ratios.** Leaves unclear which interval the value represents.
27. **Using `System.nanoTime` as a UTC timestamp.** Wrong clock semantics.
28. **Skipping `MBeanInfo` schema verification.** Implementation methods do not equal exposed attributes.

## 19. Self-check

1. What attribute does `long getRequestsTotal()` create in a Standard MBean? How are its type and read-only status verified?
2. Why should lifetime counts use `long` while ratios use `double`?
3. What percentage does `ErrorRatio=0.025` under a `[0,1]` contract correspond to?
4. If a counter rises from 1,000 to 1,300 over 60 seconds with no restart, what is the average completion rate?
5. Why must `InFlight` decrement in `finally`, and why can't the rate of `InFlight` replace request throughput?
6. While many requests run concurrently, do `getAttribute` calls for `RequestsTotal` and `FailuresTotal` automatically guarantee the same snapshot?
7. What two major risks arise from putting a user ID inside an `ObjectName`?
8. When should an MXBean return `CompositeData` instead of exposing multiple separate getters?
9. Does `isHealthy()` returning `true` prove every request is succeeding? What else must be verified?
10. If `MBeanAttributeInfo.isWritable()` returns `true` for an attribute meant to be read-only, what should you inspect?
11. When a counter drops sharply after a restart, what should an exporter do instead of computing a negative rate?
12. Can you average per-replica p95s to obtain cluster-wide p95?
13. Why can a getter calling the DB on every poll trigger a new incident?
14. When an `ObjectName` already exists, why shouldn't you unregister it without knowing which component owns it?
15. What tests should pass before letting an exporter scrape a new MBean in production?

## Reference documentation

- Oracle Java SE 17 — JMX package/MBeans: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/package-summary.html
- Oracle Java SE 17 — StandardMBean: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/StandardMBean.html
- Oracle Java SE 17 — MBeanServer: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/MBeanServer.html
- Oracle Java SE 17 — ObjectName: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/ObjectName.html
- Oracle Java SE 17 — MXBean: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/MXBean.html
- Oracle Java SE 17 — MBeanAttributeInfo: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/MBeanAttributeInfo.html

**Key takeaway:** exposing a custom MBean does not mean publishing every internal variable in the application. An MBean is valuable only when its metrics have **appropriate types, clear units, exact update and reset definitions, lightweight getters, stable ObjectNames, safe concurrent reads, and controlled access**. Only then does the MBean serve as trustworthy evidence for operational diagnostics.