# Restricting Argument Data, Object Stringification, and the Risk of Helpers Calling Back into Application Code

A probe in a Java agent is typically inserted at the entry/exit of a method to collect timing, invocation counts, error status, or tracing information. Because the probe runs **directly on the application thread**, mistakes in argument capture can slow down the application, leak data, or even **execute additional business logic** that the original call never intended to run.

Three guiding design principles:

1. **Do not capture argument values by default.** Most latency/call count measurements only need a normalized method identifier, timestamps, a general outcome, and a few bounded-cardinality labels.
2. **Do not stringify application objects on the hot path.** `String.valueOf(value)`, string concatenation, formatters, loggers, and serializers can invoke `toString()`, getters, or serialization hooks on the object itself.
3. **Helpers must have reentrancy protection and self-limiting impact.** A helper calling a logger/client, serializer, JSON library, or an instrumented method can loop back into the probe, causing recursion, duplicate events, deadlocks, or `StackOverflowError`.

This lesson belongs to the **Probe Design** group of Java Instrumentation; the focus is on how to preserve application behavior when adding observability, not on how to collect as much data as possible.

## 1. Drawing the right boundary between transformer, probe, and helper

There are three parts that are easily confused:

```text
JVM defines / retransforms a class
          |
          v
ClassFileTransformer.transform(...)   [bytecode creation/modification time]
          |
          | inserts helper calls into the method body
          v
New class is used in the application
          |
          v
Application calls OrderService.process(request)
          |
          +--> ProbeHelper.enter(methodId, ...)
          |        |
          |        +--> records minimal event, does not call back into request
          |        +--> if calling formatter/logger/app code: RISK
          |
          +--> original process(request) body
          |
          +--> ProbeHelper.exit(methodId, duration, outcome)
```

`ClassFileTransformer.transform(...)` is called during the class load/redefine/retransform cycle, whereas `ProbeHelper.enter/exit` is called by the **injected bytecode** when the application method executes. Both carry class loading risks and dependencies on application code, but the timing and available data differ.

**Probes run in the same application context:** usually the same thread, stack, class-loader environment, and permissions that the original call has. If a helper throws an unchecked exception before the method body runs, the business outcome can already change. If a helper makes a synchronous network call inside a `synchronized` method, lock hold time is extended. If a helper calls `request.toString()`, `request`'s code has been executed an extra time.

| Component | What to do | What to avoid |
|---|---|---|
| Transformer | Filter classes/methods accurately, generate valid bytecode, update frames, and ensure helper visibility | Mass class loading, calling application serializers/loggers inside `transform` |
| Entry probe | Pass a method ID or minimal primitive data; decide sampling/budget early | Taking snapshots of all args, calling getters or `toString` |
| Exit probe | Measure elapsed time, mark success/error without exposing payload | Serializing return values or exception objects |
| Runtime helper | Guard against reentrancy, write to a bounded sink, do not alter application outcomes | Potentially blocking I/O, holding references to application objects, calling back into instrumented methods |
| Off-hot-path exporter | Batching, data policy, resource limits, controlled retries | Unbounded queues, synchronous retries on request-handling threads |

## 2. What methods can “just logging an object” actually invoke?

### 2.1. `toString()` is a virtual call, not a passive data read

`Object.toString()` can be overridden. The code inside can be arbitrary: accessing a database, waiting on a lock, calling a service, mutating object state, throwing an exception, or calling an instrumented method.

```java
// DO NOT use in a generic probe for arbitrary objects:
String message = "argument=" + argument;
String text = String.valueOf(argument);
String pretty = String.format("argument=%s", argument);
```

For a non-`null` object, the string-building approaches above can call `argument.toString()`. `Objects.toString(argument)` carries the same risk. Building strings with `%s` or string concatenation does not become safe merely because the syntax is shorter.

**Do not just truncate the string after creating it:**

```java
// WRONG for controlling side effects: toString already ran before truncation.
String shortText = String.valueOf(argument);
shortText = shortText.substring(0, Math.min(shortText.length(), 100));
```

The 100-character limit only bounds the **stored result**, not the work done by `toString()`: it may have already traversed an entire object graph, opened a connection, or generated a massive string beforehand.

### 2.2. Loggers and formatters do not automatically create a safe boundary

```java
logger.debug("request={}", request);
logger.info("request=" + request);
System.out.println(request);
```

These examples can cause the object to be formatted/stringified, whether evaluation is **eager** or **deferred** depending on the library, log level, and configuration. With a logging framework that supports lazy arguments, do not assume the object is definitely safe: the formatter can still call `toString` when the event is rendered, even on another thread. Some frameworks catch exceptions from `toString`, but that does not guarantee preventing side effects before the error occurs.

Even this code:

```java
if (logger.isDebugEnabled()) {
    logger.debug("request={}", request);
}
```

only avoids some cost when debug is disabled; **when debug is enabled**, stringification can still execute application code. Switching from concatenation to placeholder logging improves cost in certain cases, but **does not solve the risk of side effects or data secrets**.

### 2.3. Indirect invocation paths that are often overlooked

| Operation in helper | What can it trigger? | Risk |
|---|---|---|
| `String.valueOf(obj)`, `obj.toString()` | App's overridden `toString` | Calling back into business logic, exceptions, I/O |
| `List.toString()`, `Arrays.deepToString(...)` | Iterating elements and stringifying elements | Reference cycles, high cost, exposing nested objects |
| JSON mapper serializing an object | Getters, field accessors, custom serializers, proxy handling depending on library/config | Lazy loading, sensitive data, DB queries |
| Java `ObjectOutputStream.writeObject(obj)` | Graph traversal and serialization callbacks | `writeObject`/`writeReplace` running app code, high memory usage |
| Reflection invoking getters | User-defined getters/proxy interceptors | Not “read-only”: getters can cause side effects |
| `obj.hashCode()`/`obj.equals(...)` | Application-written overrides | HashMap/cache lookups can run arbitrary logic |
| `String.format("%s", obj)` | Formatter leading to string representation | Similar to `toString` |
| Throwable formatting / stack trace | Message, stack, cause chain, and formatter | Cost, log recursion, information disclosure, overrides |
| Log framework or exporter | Encoders, appenders, serializers, network clients | Calling back into instrumented code, blocking/throwing |

**Distinguish certainty levels:** Java `ObjectOutputStream` has specified custom serialization methods. JSON getter discovery depends on the library/configuration; not every mapper calls every getter, but a helper must not **assume it won't**. `System.identityHashCode(obj)` differs from an overridden `obj.hashCode()`: it does not call the class's `hashCode`, yet it still should not be used as a durable ID or secret; it is only suitable for deliberate diagnostic scenarios.

### 2.4. Java Serialization is not a “safe JSON copy”

Java Serialization can transitively write objects referenced from the root object, calling `writeObject` or `writeReplace` per the `Serializable` contract. If a helper proactively serializes an argument:

- It can cause **side effects from app-defined serialization hooks**.
- Data in the graph may contain tokens, passwords, personal information, and internal fields completely unnecessary for latency measurement.
- Cost and output size cannot be controlled merely by “truncating bytes after serialization”.
- Not every object is `Serializable`; a `NotSerializableException` can break the request if it escapes the helper.

Do not implement a generic snapshot using `ObjectOutputStream` just because the Java standard library provides it. If structured telemetry is needed, design an **explicit schema** from approved values rather than capturing the entire object graph.

## 3. Argument policy: from capture-nothing-by-default to bounded allowlisting

### 3.1. Classify data before writing bytecode

To measure the call duration of `PaymentService.submit(card, request)`, the information actually needed might just be:

```json
{
  "methodId": 2041,
  "outcome": "SUCCESS",
  "durationMicros": 840,
  "sampled": true
}
```

That is an illustrative schema, not an actual transaction. There is **no** card number, account ID, full name, email, or `request.toString()`. Even though the method signature contains data-rich objects, the arguments never need to pass through the helper.

A good capture policy:

1. **Starting point: `NO_ARGUMENT_VALUES`.** Default configuration for all methods.
2. **Use-case-based allowlist:** only methods/fields that have been evaluated and approved by data owners may have their values captured; do not allowlist by broad package and capture everything.
3. **Minimization:** if a “size bucket” is needed, obtain the bucket determined from trusted data rather than stringifying the object and measuring the string.
4. **Privacy consistency:** prohibit plaintext secrets, credentials, access tokens, session cookies, payment details, and sensitive PII. Request/tenant identifiers can be high-cardinality and sensitive labels; do not use them freely.
5. **Output constraints:** limit field count, length, element count, byte budget, time, throughput, retention period, and export destinations.
6. **Evidence:** `argument_capture_dropped` metrics and reasons such as `NOT_ALLOWLISTED`, `BUDGET_EXCEEDED`, `POLICY_DENIED` if needed, rather than silently falling back to stringification.

### 3.2. Argument capture decision table

| Desired data | Default | Appropriate approach if legitimately required |
|---|---|---|
| Method name/code | Allowed if declared upfront | Use registered `methodId`/descriptor; do not resolve reflectively on each call |
| Success/error outcome type | Usable | Enum/counter from instrumentation path; do not serialize exceptions |
| Duration | Usable | `System.nanoTime()` and duration; avoid conflating with wall-clock time |
| `int`/`long` parameter values | Off by default | Specific allowlist; primitive numbers can also be OTPs, card numbers, IDs |
| `String` from application | Off by default | Only for approved fields; block secrets and apply caps **before copying/exporting** |
| Arbitrary reference object | **Do not stringify** | At most record `null/non-null` when truly needed, without calling methods on the object |
| `Collection` or `Map` | Do not call `size/toString/iterator` automatically | Only use metadata provided by the application via a dedicated observability API or trusted adapter |
| Throwable/return value | Do not serialize | Static status/error classification only; do not capture arbitrary messages/stacks |
| Raw JSON/Java serialized graph | Do not use for generic probes | If strictly required by business needs, use a dedicated off-hot-path pipeline with its own policy and schema |

Some operations that seem cheap are still unsafe for arbitrary objects. `collection.size()` can be a call into an application implementation. `obj.getClass()` does not call an overridden `toString`, but type names can still reveal internal details and metadata processing has cost; if there is no measurement purpose, **do not capture it just because you can**.

### 3.3. Enforce budgets before expensive work

An example budget configuration:

```text
captureMode              = NO_ARGUMENT_VALUES   (default)
maxCapturedArguments     = 0
maxPayloadBytesPerEvent  = 256
maxExportQueueEvents     = 10_000
maxEventsPerSecond       = bounded per deployment
maxCaptureDuration       = bounded per latency budget
onOverflow               = DROP_WITH_COUNTER
```

These numbers are **design examples**, not recommended constants for every system. In `NO_ARGUMENT_VALUES` mode, `maxCapturedArguments=0` is a meaningful limit; if selective capture is enabled, all other limits must be realistically defined and tested.

**The right order:** method selection → sampling decision → capture permission check → apply budget before reading/copying data → build minimal event → non-blocking send. Do not do it in reverse by serializing tens of MB first and then truncating to 256 bytes.

### 3.4. Limits help performance but do not guarantee privacy on their own

Storing “only the first 8 characters of a token” **is still a leak**. String length, object type, or unkeyed hashes can also disclose information in some cases. Do not assume hashing anonymizes data: low-entropy IDs can be reversed. For sensitive data, prefer not collecting it or using purpose-built encryption/HMAC techniques with dedicated key management policies.

Accompanying measures include access control for logs/traces, encryption in transit/at rest, retention limits, auditing of capture configuration changes, and an emergency kill switch that does not require waiting for a new application code release.

## 4. Reentrancy: when a helper accidentally calls back into instrumented code

### 4.1. Call cycles emerge easily

```text
UserController.handle(req)         [instrumented]
  └─ ProbeHelper.enter(...)
       └─ logger.info("req={}", req)
            └─ req.toString()
                 └─ UserService.loadMetadata()   [also instrumented]
                      └─ ProbeHelper.enter(...)
                           └─ logger / serializer / ...
                                └─ ... repeats
```

Consequences can include:

- Recursive loops until `StackOverflowError`; the application thread's stack is exhausted.
- Helper and business code contending for locks, causing deadlocks or extending critical sections.
- DB queries, RPCs, I/O, or lazy loading triggered just to produce a log.
- Skewed measurements from instrumenting the agent's own logger/exporter, causing event counts to grow exponentially.
- Class-loading cycles when the helper first initializes a logger/JSON library while the JVM is defining a class.
- An exception in `toString` or a getter escaping through the probe, turning a successful call into a failure.

**The risk is not limited to `toString`.** Loggers, executors, telemetry exporters, HTTP clients, proxies, exception handlers, reflection, or instrumented utility methods can all lead to a callback loop.

### 4.2. ThreadLocal guard: useful, but scoped

A `ThreadLocal<Boolean>` flag set before the helper does work will detect **another probe invocation on the same thread** while the helper is active. For keeping a probe from re-instrumenting itself, this is a first line of defense.

```text
probe entry
  |
  +-- thread's guard active?  -- YES --> skip reentrant probe
  |
  +-- NO --> set guard=true
               |
               v
          execute minimal logic only
               |
               v
          finally: clear/remove guard
```

Keep in mind:

- Set the guard **before** any call that might trigger instrumented code.
- Always reset in `finally`, even if the recording logic throws an exception.
- `remove()` avoids retaining `ThreadLocal` values in thread pools; do not hold references to application objects in a `ThreadLocal`.
- The guard only works on the **same thread**. If the helper offloads work to another thread and that work calls back into the application, the original thread's flag does not follow it.
- If the helper triggers a callback into the application on the same thread, the guard can suppress **duplicate probes**, but **does not prevent the unwanted business code call itself**. It does not fix `toString` side effects.
- Initializing the guard/helper too late in a bytecode callback can cause unwanted class loading; manage helper and dependency loading through agent design.

Therefore, a **ThreadLocal guard is the second line of defense**, not a replacement for the first rule: “do not call arbitrary objects”.

## 5. Standalone Java 17+ experiment: `toString` calling back into the probe

This program does not require a `javaagent`, because the goal is to isolate **runtime helper** behavior before actually injecting bytecode. It demonstrates:

1. The safe entry accepts an object without **querying it**.
2. The unsafe branch attempts to stringify the object; `toString()` calls `ProbeGuard.record` and creates a **reentrant probe**.
3. Another `toString()` throws an exception and can alter control flow.
4. The guard uses `finally`, so calls after an error do not get stuck in the `IN_PROBE` state.

Create both files in the same directory.

### 5.1. File `ProbeGuard.java`

```java
public final class ProbeGuard {
    private static final ThreadLocal<Boolean> IN_PROBE =
            new ThreadLocal<>();

    // Simple counters for a single-threaded experiment only.
    private static int recorded;
    private static int reentries;

    private ProbeGuard() {
    }

    public static void record(int methodId, Object ignoredArgument) {
        if (Boolean.TRUE.equals(IN_PROBE.get())) {
            reentries++;
            return;
        }

        IN_PROBE.set(Boolean.TRUE);
        try {
            if (methodId >= 0) {
                // Do not touch ignoredArgument, no toString/getters.
                recorded++;
            }
        } finally {
            IN_PROBE.remove();
        }
    }

    // INTENTIONALLY UNSAFE: only used to demonstrate the bug in this demo.
    public static void unsafeInspect(Object argument) {
        if (Boolean.TRUE.equals(IN_PROBE.get())) {
            reentries++;
            return;
        }

        IN_PROBE.set(Boolean.TRUE);
        try {
            String text = String.valueOf(argument);
            if (!text.isEmpty()) {
                recorded++;
            }
        } finally {
            IN_PROBE.remove();
        }
    }

    public static String counters() {
        return "recorded=" + recorded + ", reentries=" + reentries;
    }
}
```

`record` is the **safer** path: it decides based on `methodId` and does not invoke methods on `ignoredArgument`. The object parameter in the demo is only for comparing the two strategies. In real bytecode instrumentation, if an argument is not needed, **do not pass that reference to the helper in the first place**; this reduces overhead, reduces reference retention risk, and reduces the attack surface.

`unsafeInspect` illustrates what **not to implement**: `String.valueOf(argument)` can invoke an application-overridden `toString()`. The guard prevents duplicate event recording on the same thread; it does not make stringification a safe operation.

The `recorded`/`reentries` variables are not thread-safe; the example only runs single-threaded. Do not copy these counters into multi-threaded production code: use `LongAdder`/appropriate counters and design sampling, exporter, and failure-handling policies.

### 5.2. File `ProbeDemo.java`

```java
public final class ProbeDemo {
    static final class ReentrantArgument {
        @Override
        public String toString() {
            // An application might accidentally call an instrumented method here.
            ProbeGuard.record(900, this);
            return "rendered";
        }
    }

    static final class ThrowingArgument {
        @Override
        public String toString() {
            throw new IllegalStateException("toString failed");
        }
    }

    public static void main(String[] args) {
        Object value = new ReentrantArgument();

        ProbeGuard.record(101, value);
        System.out.println("SAFE " + ProbeGuard.counters());

        ProbeGuard.unsafeInspect(value);
        System.out.println("UNSAFE " + ProbeGuard.counters());

        try {
            ProbeGuard.unsafeInspect(new ThrowingArgument());
        } catch (IllegalStateException e) {
            System.out.println("UNSAFE_ERROR " + e.getMessage());
        }

        ProbeGuard.record(102, value);
        System.out.println("AFTER " + ProbeGuard.counters());
    }
}
```

### 5.3. Compile and run

Use JDK 17 or later:

```shell
javac ProbeGuard.java ProbeDemo.java
java ProbeDemo
```

**Exact stdout for the two files above:**

```text
SAFE recorded=1, reentries=0
UNSAFE recorded=2, reentries=1
UNSAFE_ERROR toString failed
AFTER recorded=3, reentries=1
```

Step-by-step explanation:

- `SAFE`: `record(101, value)` only increments a counter. `ReentrantArgument.toString()` is **not** called, so `reentries=0`.
- `UNSAFE`: `unsafeInspect(value)` calls `String.valueOf(value)` → `ReentrantArgument.toString()` → `ProbeGuard.record(900, this)`. Because the guard is active on that thread, the reentrant call only increments `reentries` and returns; then `unsafeInspect` increments `recorded` to 2.
- `UNSAFE_ERROR`: `ThrowingArgument.toString()` throws `IllegalStateException`. Because `unsafeInspect` does not catch it, the error escapes to the `try/catch` in `main`. **This proves an unsafe helper can alter application execution flow.**
- `AFTER`: `finally` removed the guard despite the exception, so `record(102, value)` is accepted again; total `recorded=3`.

**Do not use `unsafeInspect` as a production probe.** This branch is intentionally flawed for educational purposes. Outside the experiment, if a helper error escapes from bytecode injected into a real method, it can cut off business logic or mask the original exception.

### 5.4. Why doesn't the example use a javaagent?

This standalone example tests **reentrancy protection inside the helper** without needing bytecode-generation libraries or a manifest. A real agent also requires `premain`/`agentmain`, `Instrumentation`, a valid transformer, class-loader visibility, and bytecode injecting calls to `ProbeGuard.record`. Those parts are a separate problem; a small example should not be turned into a complex agent just to demonstrate `toString` behavior.

## 6. Designing a production helper: no throwing, no blocking, no calling back into app code

### 6.1. A minimal interface is better than taking `Object[] args`

Prefer a contract like:

```java
// Design interface pattern (not a standalone runnable program):
void onEnter(int methodId);
void onExit(int methodId, long durationNanos, int outcomeCode);
```

Here `methodId` is an ID from the list of instrumented methods, `durationNanos` is computed from the difference of two `System.nanoTime()` calls on the same measurement, and `outcomeCode` is a static label such as success/error. There are no raw args, return objects, exception objects, `Map<String,Object>`, or serializers.

This helps:

- Limit memory retention and allocation.
- Control label counts; avoid metrics cardinality explosions on user IDs.
- Avoid exposing surface area for `toString`/getter/serialization hooks.
- Fix data types so bytecode injection can easily verify locals/stack maps.
- Remain independent of model/domain object class loaders.

If a measurement truly needs a business field (e.g., transaction type), provide it through an **explicit, application-controlled adapter** with an approved schema. Avoid a “generic argument exporter” that can inspect/serialize arbitrary objects.

### 6.2. Reentrancy guards should be combined with an exclude list

When an agent selects classes to instrument, it usually needs to **exclude**:

- The helper itself and the agent's sink/exporter classes.
- Logging/serialization/network libraries used by the helper, if instrumenting them causes call cycles or unacceptable overhead.
- Very sensitive classes during bootstrap/class loading before the agent finishes initialization.
- Runtime/framework infrastructure where instrumentation lacks sufficient compatibility testing.

Exclude lists and guards are two different layers of defense: excludes do not guarantee there is no other indirect call path; same-thread guards do not block tasks spawned on other threads. Good design minimizes the helper's dependencies rather than continually expanding the exclude list whenever a new recursion is discovered.

### 6.3. Bounded, nonblocking sink

On the method hot path, the helper should create a small event and attempt to push it into a bounded ring buffer/queue. If the queue is full, accept **dropping the event with a counter** according to the observability policy, rather than making the request wait on the network or buffering all events in unbounded memory.

```text
Application thread
    |
    v
cheap guard + policy + sampling
    |
    v
small immutable event (methodId, duration, outcome)
    |
    v
bounded queue  --full--> drop event + increment drop counter
    |
    v
exporter thread -> batching/encoding/transport
```

Even when the exporter runs on a separate thread, it must still avoid calling arbitrary application code (e.g., logging an original object held in the queue). **Only transfer allowed primitives/snapshots**, never transfer raw object references for late stringification: the app-code risk remains and object lifetimes are prolonged.

### 6.4. Ensure the original exception is not altered

Example probe insertion scheme at entry/exit:

```text
start = monotonic time
try:
    emit_enter(methodId)              // must be very lightweight and safe
    run original method body          // do not alter semantics
finally:
    emit_exit(methodId, elapsed, ...) // must not mask body errors
```

This is **pseudocode**, not compilable Java source or a bytecode recipe directly applicable to every method. Specifically:

- If `emit_enter` throws an exception, the original method body may not have run yet.
- If the method body throws an exception and `emit_exit` also throws, the helper's exception can **mask** the original exception.
- Constructors have an uninitialized `this` before the `invokespecial` to the parent constructor; do not arbitrarily insert instructions reading `this` where the verifier forbids it.
- Operations inside `synchronized`/monitors, `try-with-resources`, `finally`, or exceptional control flow must be transformed with valid bytecode frames/exception handlers.
- Avoid indiscriminately using a broad `catch(Throwable)` to swallow `OutOfMemoryError` and serious JVM errors. Design the helper with few failure points, handle recoverable errors, and let operational policy decide when unrecoverable errors occur.

## 7. Risks beyond recursion: class loading, locks, memory, cardinality

### 7.1. Class loading in the helper

The first probe invocation can cause the JVM to load/initialize the helper and its dependencies. If that happens during class loading, a constructor, a static initializer, or code under a lock, bugs become very hard to reproduce:

- `NoClassDefFoundError`/`LinkageError` if the application's class loader cannot see the helper.
- `ExceptionInInitializerError` if the helper's class initialization depends on unready configuration/loggers.
- Class-loading recursion when a resolver/logger uses a class currently being transformed.
- Deadlock due to locks on class initialization, loggers, or thread-safety primitives.

Helper placement must be designed carefully: which class loader will resolve calls from bytecode, whether `appendToBootstrapClassLoaderSearch` is required or the helper belongs on an appropriate classpath/module, and what dependencies a bootstrap helper has. Appending to bootstrap has linkage and trust trade-offs; do not automatically stuff a large JSON/logging library into the bootstrap loader just for convenient calling from everywhere.

### 7.2. Calling app code can happen even without stringification

`equals`/`hashCode` when using an object as a map key, getters when building telemetry records, proxy interceptors, lazy-loading ORMs, custom collection iteration, validation frameworks, and reflection can all invoke application code. When method probes are attached to such utilities, a helper that looks “read-only” can generate additional method invocations.

Anti-pattern examples:

```java
// May invoke overridden hashCode()/equals() on argument:
cache.put(argument, metadata);

// May invoke getters, proxy interceptors, or custom logic:
String customer = request.getCustomer().getName();

// May trigger lazy loading and traverse many objects:
String json = objectMapper.writeValueAsString(request);
```

These snippets **do not stand alone** (they depend on `cache`, `metadata`, `request`, `objectMapper`), and only illustrate operations to avoid in generic probes. Do not copy-paste such snippets for “quick diagnostics” in a production agent.

### 7.3. Retaining object references alters lifetimes

If a helper's queue/singleton holds `Object[] args` or a `Map` containing request objects, GC may not be able to reclaim the associated graph after the request finishes. A few thousand events can pin huge graphs, class loaders, or memory regions containing sensitive data.

The solution is to enqueue **small immutable events with primitives/enums or approved, boundedly copied data**. Do not pass raw `Throwable` or `request` objects to the exporter for “later processing”: that is still data retention and deferred app-code execution.

### 7.4. Metrics cardinality and storage cost

`methodId` has a bounded count; `requestId`, `email`, `orderId`, and strings from `toString` can create a distinct label per request. When many labels become metric dimensions, real-time systems can see spikes in memory, cost, and latency even when each individual event is small.

Choose labels with a **bounded and controllable** value set, such as feature, outcome code, method group, or percentile bucket. High-cardinality IDs should go into protected traces/logs when truly needed, not generic metric labels.

## 8. Decision table for a specific measurement requirement

| Goal | Need to pass object to helper? | Minimal approach | Remaining risks |
|---|---|---|---|
| Count method calls | No | `methodId` + counter | Overhead/reentrancy if counter path is complex |
| Measure latency | No | `methodId` + elapsed nanos | Clock overhead, stack/locals during bytecode injection |
| Error rate | No raw Throwable needed | `methodId` + outcome enum | Classification requires clear policy |
| Check if a parameter is `null` | No need to retain object | Bytecode null check and pass a flag | Metadata can still be sensitive in special contexts |
| Estimate payload size | Should not serialize object | Use application-reported size or contracted adapter | Adapter can still cause side effects if called on hot path |
| Log request JSON | **Unsuitable for generic probes** | Opt-in design at application layer, schema and redaction, with budget | Privacy risks, getters/lazy loading, performance |
| Investigate a specific bug | Only with explicit approval | Scoped temporary enablement, sampling, TTL, audit | Data may contain secrets; cannot rely solely on truncation |
| Debug argument type | Usually no | Attach caller-declared type category or static metadata | Runtime type names and class loaders can be sensitive |

## 9. Mandatory testing before deploying an agent

### 9.1. Correctness tests

- **No return value changes:** methods return identical results before/after instrumentation.
- **No exception changes:** methods throw the same expected type/cause; the helper does not replace the app's stack/exception.
- **No unintended `toString`/getter calls:** use test objects whose `toString` counts invocations or intentionally throws exceptions; a safe probe must not increment the count.
- **No reentrancy:** helper has a fake exporter/logger that calls back into an instrumented method; guard and exclude policy prevent loops.
- **Constructor/static initialization:** test methods with uninitialized `this`, static init, and different class loaders; bytecode must pass the verifier.
- **No object leaks:** test request and class loader lifecycles under stress; queues must not retain arbitrary references.

### 9.2. Performance and resilience tests

- High load on short methods to observe probe overhead, allocation rate, and p99/p999 latency.
- Full queue / unresponsive exporter: requests must not be blocked indefinitely; drop counters increment.
- Multi-thread, executor pools, virtual threads if supported by the runtime: guards are per-thread, metrics/counters are thread-safe.
- Uninitialized agent helper, failing logger, throwing exporter, or unavailable API: report internal errors properly and preserve app policy.
- Log/trace disabled: do not eagerly build argument strings before checking policy.
- Repeated retransformation: do not duplicate probes or create uncontrolled nested wrappers.

A useful failure matrix:

| Test | Expectation |
|---|---|
| `toString` throws exception | Default probe does not call it; business code sees no new error |
| `toString` calls back into instrumented method | Does not happen because no stringification; if another helper causes a cycle, guard suppresses reentrant probe |
| Queue full | Event is dropped per policy, no objects retained, no blocking |
| Request contains credentials | Telemetry contains no plaintext credentials |
| Custom collection `size()` has side effects | Generic probe does not automatically call `size()` |
| JSON mapper automatically calls getters | Do not use generic mapper on hot path |
| Instrumented method throws original error | Probe does not mask the original exception |
| Two class loaders have the same class name | Helper resolution, filters, and provenance are accurate per loader |

### 9.3. Monitoring the probe itself

Monitor the **collection system** too, not just the app:

```text
probe_events_accepted_total{feature,method_group}
probe_events_dropped_total{reason}
probe_reentrancy_suppressed_total{feature}
probe_capture_denied_total{policy}
probe_helper_errors_total{kind}
probe_queue_depth
probe_export_failures_total
```

These metric names are suggestions, not a standard API. Avoid labels like raw `argument`, `toString`, user ID, exception message, or dynamic full class name. If a metrics exporter itself uses an agent-instrumented method, the observability pipeline itself must be tested for loops.

## 10. Common misconceptions

1. **“`toString` only reads state, it cannot alter business logic.”** False: it is a virtual call that can contain arbitrary logic.
2. **“Capping output at 200 characters caps stringification cost.”** False: `toString`/serializer has already done its work before truncation.
3. **“Logging placeholder `{}` is always safe.”** False: the formatter can still call `toString` when rendering.
4. **“Using a JSON mapper is passive field reading.”** False for many serializers/configs: getters, custom adapters, and proxies can be invoked.
5. **“Java Serialization only writes bytes, it doesn't run object code.”** False: `writeObject`/`writeReplace` can execute.
6. **“A ThreadLocal guard prevents all kinds of recursion.”** False: it only stops certain cycles on the same thread and does not prevent side effects of the initial app-code call.
7. **“Passing the object to an exporter thread is safer.”** False: it still retains references, shifts stringification risk to another thread, and can cause leakage/retention.
8. **“Primitive arguments are harmless by default.”** False: a `long` can be a user ID, token, or sensitive information.
9. **“Capture the whole exception for easier debugging.”** False: keeping `Throwable` in a queue can pin graphs and leak messages/stacks.
10. **“If a helper fails, the JVM ignores it just like `ClassFileTransformer`.”** False: an exception from a **runtime helper injected into a method** is a normal runtime exception if unhandled.
11. **“The class is in the system loader, so every class loader can call the helper.”** False: helper visibility/module access must match the actual bytecode and loaders.
12. **“Sampling after stringification will significantly reduce overhead.”** False: the dangerous part already ran before the sampling decision.
13. **“Instrument all logging/network dependencies to get more telemetry.”** Can create self-loops. Choose explicit exclude scopes and guards.
14. **“No argument data means the probe is useless.”** False: latency, count, error-rate, and tracing remain mostly valuable from method ID/timing/status.

## 11. Self-check questions

1. **Why is `String.valueOf(request)` not a “read-only” operation?** Because an object can override `toString()` to run application logic, I/O, side effects, or throw exceptions.
2. **If stringification returns a one-million-character string and then truncates to 100 characters, are cost and privacy controlled?** No. All stringification/object traversal logic already ran before truncation.
3. **Why shouldn't `Object[] args` be put into a queue for later processing?** It retains object references/lifetimes, may contain sensitive data, and causes the exporter to execute application code later.
4. **Does a `ThreadLocal` guard guarantee there are no indirect call cycles on another thread?** No. It only tracks the state of the current thread.
5. **If a helper calls a logger and the logger calls an instrumented method, what can happen?** Reentrant probes, recursion, inflated metrics, high overhead, or deadlocks.
6. **When a method only needs latency measurement, what are the best helper parameters?** Method ID, duration, and outcome, without raw args or return objects.
7. **Is `Collection.size()` on an arbitrary object always safe?** No. An arbitrary implementation can call app code, have side effects, or incur high cost.
8. **Why shouldn't raw user IDs be used as metric labels?** High cardinality, potential sensitivity, increased storage cost, and performance impact.
9. **If the original method is throwing an exception and the exit helper also throws, what can happen?** The helper's exception can mask the original error and alter observable behavior.
10. **In the demo, when does `reentries` increment?** When `unsafeInspect` stringifies `ReentrantArgument`, and `toString()` calls `record` while the guard is active.
11. **Why is `finally` important for a reentrancy guard?** It clears the active state after both success and exception paths, avoiding “stuck” state in thread pools.
12. **Should you rely on character limits to confirm data is anonymized?** No. Redaction/privacy requires data policies, not just length limits.
13. **When does agent helper initialization require special care?** When the helper is loaded/initialized during class loading, constructors, or under locks, because dependencies can cause linkage errors/cycles/deadlocks.
14. **What is the first measure to avoid `toString` risks?** **Do not pass and do not stringify arguments** if the measurement does not truly need them.

## 12. Reliable references

- [Java SE 21 — `java.lang.Object`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Object.html): contract and overriding `toString()`, `equals()`, `hashCode()`.
- [Java SE 21 — `java.lang.ThreadLocal`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ThreadLocal.html): per-thread state and `remove()`.
- [Java SE 21 — `java.io.Serializable`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/Serializable.html): custom `writeObject`, `writeReplace`, and serialization contract.
- [Java SE 21 — `java.io.ObjectOutputStream`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectOutputStream.html): writing object graphs and limitations of Java Serialization.
- [Java SE 21 — `java.lang.instrument`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): Java agent model and bytecode instrumentation.
- [Java SE 21 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): transform callback at class load/redefine/retransform time.

**Takeaway:** a good probe is one that **does not turn an application object into a data graph to be logged**. Measure using static identifiers, primitive metadata, and clear budgets; avoid `toString`/serializers/getters on the hot path, use a reentrancy guard to reduce loops, and never treat the guard as a license to call back into application code. Observing a system without altering its outcome is the single most important standard.