# Locking In Consistent Configuration While Changing Filters or Toggling Probes

A Java agent measuring method execution time can be controlled **at runtime while the application is running**: enabling/disabling probes, adding method names to a filter, changing the sampling rate, switching the metric destination, or updating exclusion rules. These operations typically come from an administrative thread, while hundreds of application threads concurrently pass through the instrumented hooks.

The hardest problem is not writing `enabled = false`, but **determining which configuration version applies to a given method invocation**. If the entry hook reads the `enabled` flag of an old version, then reads the filter of a new version, and the exit hook reads the sink of a third version, the data can become inconsistent: an exit without an entry, a duration missing a start point, writing to the wrong sink, or lost events.

This topic belongs to the **Concurrency and Performance** section of Java Advance — instrumentation. The core solution is to **lock in an immutable configuration snapshot at the start of an invocation** and pass a token/scope for that invocation to its completion point. A configuration update is **published atomically as a whole** using `AtomicReference` or a `volatile` reference to an immutable object; the hot hook reads it **once** and uses that exact snapshot.

This article covers the consistency contract, the Java Memory Model, filter/version/sink design, configuration changes while invocations are in flight, a compilable and runnable Java 17+ example, performance costs, limitations with retransformation, and a production testing checklist.

## 1. Clearly Define What “Consistent” Means

Before writing code, you must define the **unit of configuration application**.

| Unit | What can be guaranteed | Consequence |
|---|---|---|
| **Per method invocation** (*per-invocation*) | Entry and exit use the same configuration locked in at entry | In-flight invocations can still emit events under the old configuration after disabling |
| **Per hook execution** (*per-hook*) | Entry/exit each time reads the current configuration | Easy to get an entry from version A and an exit from version B; must handle unpaired events |
| **Per request/trace** | Methods within the same request use one configuration version | Requires propagating the snapshot via request context, not just keeping it local to each method |
| **JVM-wide immediately** | Once an update finishes, no more events from the old configuration | Requires synchronization/blocking, revoking or draining in-flight invocations; a single atomic reference is not enough |

For most method-level **duration/counter/span** probes, the **per-invocation** choice is the easiest to preserve semantics for:

```text
entry(method="checkout") -- lock config v1, enabled=true
          |
          | method is running
          |
control thread: publish config v2, enabled=false
          |
          | method v1 still continues
          v
exit(checkout) ----------- uses token and sink of v1
```

**Correct result under the per-invocation policy:** the `checkout` event for version `v1` is still emitted when the method finishes. Configuration `v2` will apply to **invocations that start after v2 has been published and observed**.

This does not contradict “the probe has been disabled”: **disabling here means stopping acceptance of new invocations**, not erasing the history of an invocation already in flight. If the business requirement is “no events may be sent at all immediately after the disable operation”, a different policy is needed, which is discussed in Section 10.

## 2. Common Pitfall: Multiple `volatile` Variables Do Not Form a Transaction

Suppose an agent has:

```java
private static volatile boolean enabled = true;
private static volatile Set<String> allowedMethods =
        Set.of("checkout");
```

The administrative thread updates:

```java
allowedMethods = Set.of("inventory"); // New filter
enabled = false;                      // Disable probe
```

The instrumented thread runs:

```java
if (enabled && allowedMethods.contains(methodId)) {
    recordEvent();
}
```

This is a **standalone illustrative snippet**, not a self-contained class. `volatile` guarantees visibility/happens-before rules **for individual volatile operations**, but **it does not turn reading two fields into an atomic snapshot of both fields**.

For example, the operations can interleave as follows:

```text
Time            Control thread                 Worker thread
---------       --------------                 -------------
t0              enabled=true                   ...
                filter={checkout}
t1              allowedMethods={inventory}
t2                                             read enabled=true
t3                                             read filter={inventory}
t4              enabled=false
```

The worker observes a **combination of states** that was never published as a complete configuration intended by the administrator. If the worker also has to read `samplingRate`, `reporter`, and `excludedPackages` at different points in time, the number of mixed states grows even further.

Reordering the two assignments **does not solve the multi-field read bug in general**. `synchronized` guarding the same lock on **both readers and writers** can provide consistency, but locking on the hot path of every method invocation typically causes contention and increases latency. A cleaner solution is **immutable snapshot + atomic publication**.

### 2.1. Watch out for mutable collections

Even if the filter reference is `volatile`:

```java
private static volatile Set<String> methods = new HashSet<>();
```

if the administrative thread mutates the **contents directly** via `methods.add(...)`/`methods.remove(...)`, that does not make operations on `HashSet` thread-safe. Readers can see inconsistent state or encounter errors due to concurrent modification.

For configuration, you should create **a new validated `Set`**, wrap it inside an immutable configuration object, and swap **a single shared reference**. Do not mutate collections currently in use by older invocations.

## 3. Design: One `Config` Object Containing All Related Decisions

Model:

```text
Config v1 (immutable):
  version=1
  enabled=true
  methods={checkout}
  sink=SinkA
           |
           | AtomicReference<Config>
           v
        [v1 pointer]  -- atomic update --> [v2 pointer]
                                            |
                                            v
                                     Config v2:
                                       version=2
                                       enabled=false
                                       methods={}
                                       sink=SinkA
```

A worker does:

```java
Config snapshot = current.get();
if (!snapshot.enabled()) {
    return;
}
if (!snapshot.methods().contains(methodId)) {
    return;
}
```

`current.get()` appears **only once**. Both conditions read from **the exact same object**. A writer swapping the `current` pointer afterward **does not modify the `snapshot` object** held by the worker.

### 3.1. Using Java 17 `record` and copying collections

Conceptual example:

```java
record Config(
        long version,
        boolean enabled,
        Set<String> allowedMethods,
        Reporter reporter) {

    Config {
        allowedMethods = Set.copyOf(allowedMethods);
        Objects.requireNonNull(reporter);
    }
}
```

This is an **excerpt**: `Reporter` must be defined and imports for `Set` and `Objects` must be present. The complete example in Section 6 uses `Consumer<ProbeEvent>` instead of `Reporter`.

A `record` has `final` component fields, but it is **not automatically deep-immutable**: if a component points to a mutable `HashSet`, external code can still modify its contents. `Set.copyOf` protects the method set from being mutated through the source reference. If stateful maps/lists/predicates are used, immutability must be designed accordingly.

Note that `reporter`/`sink` may be a **stateful** object (queue, socket, metrics exporter). The snapshot locks in the **identity and configuration of the sink** according to a policy; it does not make the sink itself immutable or immortal.

### 3.2. `AtomicReference<Config>` and memory visibility

```java
private final AtomicReference<Config> current =
        new AtomicReference<>(initialConfig);
```

This is an **illustrative field**, where `initialConfig` already exists. Per the Java 17 Javadoc, `get()` has the memory effects of a volatile read, and `set()` has the memory effects of a volatile write. Threads can observe the fully constructed and properly published configuration object.

With a **single writer**, you can use:

```java
private volatile Config current;

void publish(Config next) {
    current = next;
}
```

Readers must capture `Config c = current;` and use `c` for all decisions within the invocation. **Do not** repeatedly read `current.enabled()`, `current.allowedMethods()`, `current.reporter()` on separate lines — doing so can still mix versions.

With **multiple writers** modifying parts of the configuration, `AtomicReference.updateAndGet` or a `compareAndSet` loop is more appropriate because it allows updating based on the current value atomically.

## 4. The Snapshot Must Live With the Invocation, Not Just One Hook

Locking in `Config` once at entry is **not enough** if the exit hook calls `current.get()` again.

Error-prone pattern:

```text
ENTRY:
  if currentConfig.accepts(method):
      start = nanoTime()

EXIT:
  if currentConfig.accepts(method):
      emit(now-start)
```

There are two serious bugs:

1. **Entry accepted, exit disabled:** no duration is recorded or the completion event is lost.
2. **Entry rejected, exit just enabled:** exit tries to use an uninitialized `start`, or emits an event with no corresponding enter event.

Correct design:

```text
ENTRY(methodId):
  Config c = current.get()       // read exactly one snapshot
  if (!c.accepts(methodId)):     // lock in enabled + filter + sampling
      return NO_TOKEN
  return Token(c, methodId, System.nanoTime())

EXIT(token, outcome):
  if token == NO_TOKEN:
      return
  token.finish(outcome)          // use the locked-in config + sink
```

`NO_TOKEN` can be represented as `null` in a demo; a real library might use a noop singleton scope or another optimized structure. **The token is per-invocation state**, not a global field overwritten across threads.

### 4.1. A consistent decision must include all related factors

A good snapshot holds not only `enabled`, but also:

- Allowed method/class sets, or frozen filter predicates.
- Sampling rate / seed / sampling rules applied to the invocation.
- Service name and resource metadata to attach to the event.
- Version/generation for post-reload diagnostics.
- Reporter/sink or a stable routing reference, if the policy is that each invocation sends to the sink chosen at its start.
- Data limits / sensitive-information redaction rules associated with the event itself.

If `enabled` comes from v1, the filter from v2, and the sampler from v3, a token can reflect a configuration that never existed. **A single snapshot object** lets us define an exact, consistent usage policy.

### 4.2. Choosing “per-invocation” or “per-request”?

Each invocation can start at different times. If a request calls method A before a reload and method B after the reload, **per-invocation** may produce A under v1 and B under v2; this is valid.

If the entire request must use the same version:

```text
request starts -> lock Config v1 into request context
   A uses v1
   config updated to v2
   B still uses v1
request ends
```

In that case, you must **propagate the snapshot through the request context**, including across async boundaries and related threads; merely reading `AtomicReference` at each method entry is not enough to achieve request-level consistency.

## 5. Rules When Toggling or Changing Filters

Suppose the configuration is:

```text
v1: enabled=true,  methods={checkout}
v2: enabled=false, methods={}
v3: enabled=true,  methods={inventory}
```

Results under the per-invocation policy:

| Invocation started at | Method | While running | Result |
|---|---|---|---|
| `v1` | `checkout` | Switched to `v2` before exit | **Emit one event under v1** |
| `v2` | `checkout` | Re-enabled `v3` before exit | **No event created** |
| `v3` | `checkout` | Unchanged | **No event created**, because v3 filter does not contain the method |
| `v3` | `inventory` | Unchanged | **Emit event under v3** |
| `v3` | `inventory` | Method throws an exception | **Emit exceptional event under v3** if the exit hook covers exceptions |

“Enabling/disabling a probe” in this runtime context refers to **whether an existing hook collects data or not**. It does not automatically add a hook to a method that **was never instrumented**; that distinction is important in Section 11.

## 6. Complete Java 17+ Example: Locking the Snapshot With `AtomicReference`

The example runs on JDK 17+ and **does not require a real Java agent** to test the concurrency logic. We simulate entry/exit hooks with `invoke(...)`, then use `CountDownLatch` to force a reload **to occur while an invocation is waiting**. This makes the result reproducible instead of relying on `Thread.sleep()` and machine speed.

This lab was compiled with `javac --release 17` and run on OpenJDK 24.0.2. This is a **test of controller/hook logic**; when integrating a real agent, `enter` and `finish` must be placed into appropriate bytecode advice.

### 6.1. Directory structure

```text
config-snapshot-demo/
└── ConfigSnapshotDemo.java
```

Only **one Java file** is needed.

### 6.2. Complete `ConfigSnapshotDemo.java`

```java
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Consumer;
import java.util.function.Supplier;

public final class ConfigSnapshotDemo {
    record ProbeEvent(String method, long version,
                      String outcome, long durationNanos) {}

    record ProbeConfig(long version, boolean enabled,
                       Set<String> methods, Consumer<ProbeEvent> sink) {
        ProbeConfig {
            methods = Set.copyOf(methods);
            Objects.requireNonNull(sink, "sink");
        }

        boolean accepts(String method) {
            return enabled && methods.contains(method);
        }
    }

    static final class ProbeController {
        private final AtomicReference<ProbeConfig> current;

        ProbeController(ProbeConfig initial) {
            current = new AtomicReference<>(initial);
        }

        Ticket enter(String method) {
            ProbeConfig snapshot = current.get();
            if (!snapshot.accepts(method)) {
                return null;
            }
            return new Ticket(method, snapshot, System.nanoTime());
        }

        ProbeConfig configure(boolean enabled, Set<String> methods) {
            return current.updateAndGet(old ->
                    new ProbeConfig(old.version() + 1, enabled,
                                    methods, old.sink()));
        }
    }

    static final class Ticket {
        private final String method;
        private final ProbeConfig snapshot;
        private final long startedAt;
        private final AtomicBoolean finished = new AtomicBoolean();

        Ticket(String method, ProbeConfig snapshot, long startedAt) {
            this.method = method;
            this.snapshot = snapshot;
            this.startedAt = startedAt;
        }

        void finish(String outcome) {
            if (finished.compareAndSet(false, true)) {
                long duration = System.nanoTime() - startedAt;
                snapshot.sink().accept(new ProbeEvent(
                        method, snapshot.version(), outcome, duration));
            }
        }
    }

    static <T> T invoke(ProbeController probe,
                        String method, Supplier<T> operation) {
        Ticket ticket = probe.enter(method);
        T value;
        try {
            value = operation.get();
        } catch (RuntimeException | Error original) {
            if (ticket != null) ticket.finish("EXCEPTIONAL");
            throw original;
        }
        if (ticket != null) ticket.finish("NORMAL");
        return value;
    }

    public static void main(String[] args) throws Exception {
        ConcurrentLinkedQueue<ProbeEvent> events =
                new ConcurrentLinkedQueue<>();
        ProbeController probe = new ProbeController(
                new ProbeConfig(1, true, Set.of("checkout"), events::add));

        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        Thread inFlight = new Thread(() -> {
            invoke(probe, "checkout", () -> {
                entered.countDown();
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(e);
                }
                return 10;
            });
        }, "checkout-worker");
        inFlight.start();

        entered.await(); // checkout has already acquired snapshot v1.
        ProbeConfig disabled = probe.configure(false, Set.of());
        System.out.println("[reload] version=" + disabled.version()
                + " enabled=" + disabled.enabled());
        release.countDown();
        inFlight.join();

        invoke(probe, "checkout", () -> 11);
        System.out.println("[disabled] events=" + events.size());

        ProbeConfig filtered = probe.configure(
                true, Set.of("inventory"));
        invoke(probe, "checkout", () -> 12);
        invoke(probe, "inventory", () -> 13);
        try {
            invoke(probe, "inventory", () -> {
                throw new IllegalArgumentException("demo");
            });
        } catch (IllegalArgumentException expected) {
            // The application still sees the original exception.
        }

        System.out.println("[filter] version=" + filtered.version()
                + " enabled=" + filtered.enabled());
        for (ProbeEvent e : events) {
            System.out.println("[event] " + e.method()
                    + " v=" + e.version()
                    + " outcome=" + e.outcome());
        }
        System.out.println("[total] events=" + events.size());
    }
}
```

### 6.3. Explaining the design decisions in the code

**`ProbeConfig` is a record:**

- `version`, `enabled`, `methods`, and `sink` are kept in **a single object**.
- `Set.copyOf(methods)` creates an immutable set by contract; code cannot mutate the filter currently used by old tokens.
- `Objects.requireNonNull` rejects a null sink before publication.
- `version` distinguishes which configuration point in time an event came from.

**`ProbeController` is the single place that publishes configuration:**

```java
private final AtomicReference<ProbeConfig> current;
```

All hooks access it only through `enter` and call `current.get()` **once**. The `configure` method uses `updateAndGet` to atomically publish a new configuration with `version+1`; if there is contention, the function may be re-applied. Therefore, the function here **does not log, emit events, or update auxiliary counters**.

**`Ticket` holds the state of exactly one invocation:**

- `snapshot` stores the configuration at entry time.
- `startedAt` is captured only when the method is accepted, reducing cost on the disabled branch.
- `AtomicBoolean finished` prevents a token from emitting an event **twice** if code calls `finish` repeatedly.
- `finish` emits the event to `snapshot.sink()`, **without re-reading** `ProbeController.current`.
- `durationNanos` is kept in the event but **not printed** in the expected stdout because timing values depend on the environment.

`AtomicBoolean` in the demo also shows how to protect a token against accidental double-finish. An optimized instrumentation might omit this atomic step if it can prove every invocation always terminates through exactly one hook, but then both normal and exceptional paths must be strictly controlled.

**`invoke` simulates entry/exit placement:**

- Acquires the ticket before executing the operation.
- Returns the original value after recording `NORMAL`.
- If the operation throws a `RuntimeException` or `Error`, records `EXCEPTIONAL` and **rethrows the same exception**.
- The `Supplier<T>` model does not support checked exceptions; when instrumenting arbitrary Java methods, you must handle all `Throwable` exit paths properly per the JVM contract, not just copy this wrapper.

**`CountDownLatch` makes the example deterministic in ordering:**

1. Worker creates the `checkout` ticket at v1.
2. Worker signals `entered.countDown()` and waits on `release`.
3. Main calls `entered.await()`, so it knows the ticket **has already been created**.
4. Main publishes v2 disabled.
5. Main calls `release.countDown()` and `inFlight.join()`.
6. Worker finishes with v1, even though v2 is already the current configuration.
7. Main verifies a new call under v2 emits no event; then publishes v3 with a filter accepting only `inventory`.

Thanks to this synchronization, the test does not need `Thread.sleep` or scheduler guesswork.

### 6.4. Compile and run commands

In the directory containing the file:

```bash
javac --release 17 -encoding UTF-8 ConfigSnapshotDemo.java
java -cp . ConfigSnapshotDemo
```

`record`, `AtomicReference`, `CountDownLatch`, `Set.copyOf`, and `ConcurrentLinkedQueue` are all available in Java 17; no ASM, Byte Buddy, or preview features are required.

**Observed stdout:**

```text
[reload] version=2 enabled=false
[disabled] events=1
[filter] version=3 enabled=true
[event] checkout v=1 outcome=NORMAL
[event] inventory v=3 outcome=NORMAL
[event] inventory v=3 outcome=EXCEPTIONAL
[total] events=3
```

**Reading the output semantically:**

- `events=1` after disabling **is not a bug**. One `checkout` was accepted at v1 and completed after the reload; its ticket locked in snapshot v1.
- The **new** `checkout` call at v2 emits no additional event.
- At v3, `checkout` is rejected by the filter, while the two `inventory` invocations are recorded.
- One `inventory` invocation returns normally and one throws `IllegalArgumentException`; both events share v3, with different outcomes.
- Total events is `3`; there are no duplicate events caused by the reload.

This is stable stdout for the **latch-enforced execution order** and the demo’s queue sink. The `durationNanos` value is actually present in the record but excluded from expected stdout.

### 6.5. What does this test prove, and what does it not prove yet?

It **proves**:

- An invocation can use snapshot v1 end-to-end, even when v2 is published between entry and exit.
- Filter, enabled, and sink decisions are taken from **the same object**.
- Reloading does not cause a v1 invocation to switch mid-flight to v2.
- New invocations use the new configuration when they start after publication.
- The code simulates normal/exceptional exits without altering the operation’s result when the sink behaves normally.

It **does not by itself prove** that a production Java agent has injected hooks on all return/exception paths, has avoided recursion, or that the event sink will never throw errors. Those are separate integration requirements.

## 7. When Multiple Threads Modify Configuration Concurrently

If only one control thread is allowed to publish the entire configuration, `volatile Config` with a single assignment suffices for **publication**. However, if there are multiple sources changing **individual parts** — e.g., UI toggling enabled, server changing the filter, pipeline swapping the sink — you must prevent **lost updates**.

### 7.1. Update pattern prone to data loss

Suppose:

```java
Config old = current.get();

// Admin A creates an enable/disable version from old.
Config a = new Config(old.version() + 1, false,
                      old.allowedMethods(), old.reporter());

// Admin B also creates a filter-change version from the same old.
Config b = new Config(old.version() + 1, old.enabled(),
                      Set.of("inventory"), old.reporter());

current.set(a);
current.set(b);
```

This is **Java pseudocode**, assuming existing variables/types. After `current.set(b)`, A’s `enabled=false` change can be overwritten with the old `enabled` value from B. Even though each `set` is published atomically, **two writers can still lose partial update intent**.

### 7.2. Using `updateAndGet` for atomic read-modify-write

To only toggle enabled while keeping the current filter:

```java
ProbeConfig updated = current.updateAndGet(old ->
        new ProbeConfig(
                old.version() + 1,
                false,
                old.methods(),
                old.sink()));
```

To only change the filter while keeping the current flag:

```java
ProbeConfig updated = current.updateAndGet(old ->
        new ProbeConfig(
                old.version() + 1,
                old.enabled(),
                Set.of("inventory"),
                old.sink()));
```

These two snippets are **illustrations belonging to a configuration management class**, not standalone runnable classes. `AtomicReference.updateAndGet` performs an atomic read-modify-write; the lambda can be re-executed when CAS contention occurs, so it **must be side-effect-free**.

If the system manages configuration using a **client-supplied revision**, you can use `compareAndSet(expected, next)` to reject an update based on a stale revision. A server-incremented `version` for auditing does not replace client concurrency checks; you need an explicit policy for last-write-wins, conflict rejection, or merging.

### 7.3. Build, validate, then publish

A safe rollout sequence:

```text
Receive update request
          |
          v
Parse + validate new config
          |
          v
Compile filters/patterns off the hot path
          |
          v
Create immutable Config snapshot
          |
          v
AtomicReference.set/updateAndGet/CAS
          |
          v
New invocations start seeing the new config
```

**Do not publish a half-baked configuration**, such as publishing `enabled=true` first and only then loading the regex list or creating the sink. If creating the new sink fails, keep the old configuration rather than exposing an unusable one.

If filters contain regexes, bound pattern length/complexity and detect regex errors **before publication**, rather than letting the hot hook discover invalid input configuration.

## 8. When Disabling Probes, Should Old Invocations Still Emit Events?

This is a business/product decision, not just a choice between `volatile` and `AtomicReference`.

| Policy | Benefit | Cost |
|---|---|---|
| **Per-invocation snapshot** | A selected invocation has complete data under the same version | v1 events may appear after v2 has disabled the probe |
| Re-check `enabled` flag at exit | Can prevent emitting events after disable | Easy to drop the exit of an invocation that already had an enter; timeline has missing data |
| Use an `epoch` to drop old events at the sink | Prevents storing events from old generations | Actively discards in-flight data; sampling/drop semantics must be documented |
| **Quiesce + drain** old invocations before declaring fully disabled | Can achieve a stronger boundary | Requires an admission/draining protocol, longer wait times, and synchronization cost |
| Re-instrument/retransform classes to remove hooks | Can reduce future overhead | High retransform cost, many old classes/frames still running, and JVM limitations |

An `AtomicReference.set(v2)` only states that **from now on the reference points to v2** under memory semantics; it **does not** wait for threads already holding v1 to finish, nor does it magically stop them from using v1.

If the requirement truly is “after the disable API returns, no old events will be sent anymore”, you must define a **linearization point** and acknowledgment contract:

1. Block new v1 admissions.
2. Track/catch admissions racing with disable.
3. Wait for or cancel/mark in-flight v1 invocations per policy.
4. Report completion only after the system’s promised condition is met.

**Counting `active` with an `AtomicInteger` and simply waiting for `0` is not enough if you cannot close the race where a reader just grabbed v1 but has not incremented `active` yet.** A proper drain protocol must synchronize **admission + counter + publication**; do not assume two separate atomic variables automatically form a transactional barrier.

### 8.1. “Late-arriving data after disable time” is not necessarily a violation

For an event containing:

```text
method=checkout
configVersion=1
startedAt=t1
finishedAt=t3
```

while config v2 was published at `t2` (`t1 < t2 < t3`), the event appears after `t2` but **belongs to an invocation that started before `t2`**. Attaching the appropriate version/generation and timestamps keeps dashboards from falsely reporting a configuration bug.

Do not label the field `currentVersion` if the event actually uses `entryVersion`; choose names that accurately express the contract.

## 9. Toggling a Runtime Guard vs. Changing Bytecode via Retransform

A Java agent can inject into a method body:

```text
onMethodEnter:
  ticket = ProbeRuntime.enter(methodId)

original method body

onMethodExitNormal:
  ProbeRuntime.finish(ticket, NORMAL)

onMethodExitExceptional(Throwable t):
  ProbeRuntime.finish(ticket, EXCEPTIONAL)
  rethrow same Throwable
```

This is **instrumentation pseudocode**, not runnable Java source. It illustrates that `ticket` data must flow from entry to both exit paths.

Once the bytecode hook is injected, you can swap `ProbeRuntime.currentConfig` to toggle collection **without retransforming classes on every toggle**. The disabled branch only reads the config and skips expensive event-recording work.

However, two layers must be distinguished:

- **Bytecode topology layer**: which classes/methods has the JVM instrumented? Requires a transformer, and sometimes `retransformClasses` if classes are already loaded.
- **Runtime policy layer**: among existing hooks, which invocations are recorded? Can be controlled via an immutable config snapshot.

**If a method does not yet have a hook, adding its name to the filter does not automatically instrument it.** You may need to retransform the relevant classes to add hooks, depending on strategy and capabilities.

### 9.1. `removeTransformer` does not remove hooks already installed in classes

`Instrumentation.removeTransformer(t)` only unregisters the transformer for **subsequent** eligible class transformation events. It does not automatically revert the bytecode of already loaded/transformed classes. Therefore, using `removeTransformer` instead of an enabled flag is wrong if the goal is to disable **event recording immediately in already-instrumented code**.

`retransformClasses` has its own costs and limitations: retransform capability is governed by the JVM/manifest; loaded classes must be modifiable; active frames may continue executing old bytecodes. If you change configuration by retransforming thousands of classes, do not call that an atomic transaction across all running methods.

## 10. Locking Filters and Sampling Under Async, Recursion, and Exceptions

### 10.1. Method IDs must be sufficiently distinct

Filtering by method name `"get"` alone easily matches hundreds of unrelated methods. A practical ID should include:

```text
class binary name + method name + descriptor
```

And when you need to avoid conflating different runtime classes, consider **defining class loader/module identity**.

For example:

```text
com.example.OrderService.checkout(Ljava/lang/String;)Z
```

This name captures the signature as well; do not rely on a specific overloaded method using only its simple name.

### 10.2. Sampling also needs to be decided once

If sampling is decided at entry but exit reads a new `samplingRate`, events can become unpaired. Determine `sampled` within the same snapshot (or a token created from the snapshot), and keep that decision throughout the invocation.

For distributed tracing, you may need to use the trace sampling decision from the request context instead of rolling random independently at every method. **Do not** use `ThreadLocalRandom` at exit to “re-check” a sampling decision made at entry.

### 10.3. Recursion and nested method calls

A method calling itself or another instrumented method causes invocations to **nest**:

```text
enter A (token A1)
  enter B (token B1)
    enter A (token A2)
    exit A (token A2)
  exit B (token B1)
exit A (token A1)
```

If code stores `currentToken` in **a static field**, A1’s token can be overwritten by A2/B1; the data is corrupted even if the configuration is atomic. A proper ticket must be tied to a **specific invocation**, usually stored in local state allocated by bytecode advice or an appropriate context stack structure.

If using `ThreadLocal`, there must be a **push/pop stack** rather than a single slot, ensuring pop happens even when an exception occurs and handling context propagation across async tasks. Do not assume every continuation runs on the same Java thread.

### 10.4. Exceptional exits must use the same token

A method can terminate via one of the six return opcodes or via an unhandled exception within the method itself. If an exit hook is inserted only before `return`, exceptional invocations will lose events and leak state. If you only hook `ATHROW`, you still miss exceptions raised implicitly by the JVM or propagated from callees.

Whether using ASM, Byte Buddy, or the Class-File API, ensure both normal and exceptional exits are observed properly and pass the **entry token** to the corresponding exit. The tracer must not alter the return value or original `Throwable`.

## 11. Performance: Keep the Disabled Branch as Cheap as Possible

Because hooks run on the application’s hot path, every small cost can be multiplied millions of times:

| Operation | Disabled branch | Enabled/accepted branch |
|---|---|---|
| Read `AtomicReference.get()` or `volatile Config` | **Once** | **Once** |
| Check enabled flag | Yes | Yes |
| Filter lookup | Can be skipped if disabled (short-circuit) | Yes |
| `System.nanoTime()` | **Not needed** | Yes if measuring duration |
| Allocate `Ticket` | **Not needed** | Yes in the demo |
| Allocate `ProbeEvent` | No | On completion |
| Push to sink/queue | No | On completion |
| Synchronize via shared lock | Avoid | Avoid on the hot path |

`AtomicReference.get()` has volatile-read memory semantics. It is not “free”, but it is usually cheaper than locking a shared mutex on every method entry. Exact results depend on JVM, CPU, JIT, allocation pressure, contention, and filter size; **measure with benchmarks/JFR on real workloads**, rather than quoting a generic nanosecond number.

### 11.1. Do not compile regexes in the hook

Do not do:

```java
if (Pattern.compile(config.regex()).matcher(methodId).matches()) {
    // ...
}
```

on every invocation. Prepare `Pattern` instances **before** publishing the config, or convert filters into optimized sets/hashes/predicates. Ensure predicates do not mutate shared state, perform I/O, or throw unexpected errors.

### 11.2. The sink needs a non-interfering contract

In the demo, `events::add` writes to a thread-safe `ConcurrentLinkedQueue`. This queue is **unbounded**, so it is **not suitable by default for high-throughput production telemetry**.

In practice:

- Choose a bounded queue / ring buffer or an explicit backpressure/drop policy.
- Do not perform synchronous logging, network calls, or config parsing in hot entry/exit hooks.
- Track accepted events, dropped events, exporter errors, and latency.
- Avoid high-cardinality labels (stack traces, request IDs, user-specific values) in metrics.
- The recorder should not throw exceptions that alter application outcomes.
- When swapping sinks, older tickets may still hold the old sink; do not close the old sink immediately if you still want in-flight events to complete.

### 11.3. `AtomicBoolean finished` does not mean exactly-once delivery

`Ticket.finished.compareAndSet(false, true)` prevents code from **attempting to send** from the same ticket multiple times. It **does not** guarantee that the exporter received/durably wrote the event. After `finished` becomes true, a sink failure can still lose the event, even though there is no duplicate.

If stronger delivery reliability is required, you must design queues, retries, idempotency, and event identification keys at the **transport/storage layer**; you cannot infer “end-to-end exactly once” from `AtomicBoolean` alone.

### 11.4. A Java agent must not cause infinite recursion

If the agent instruments classes inside the recorder itself, `ProbeRuntime.enter` could call instrumented code, which calls `ProbeRuntime.enter` again... leading to recursion or class-loading failures. In practice, you must **exclude helper/recorder classes from filters and transformers**, or have dedicated reentrancy guards.

## 12. When to Use `volatile`, `AtomicReference`, or Locks?

| Mechanism | When appropriate | What it does not automatically guarantee |
|---|---|---|
| Immutable `volatile Config` | Single writer publishes whole object; readers only read snapshot | Read-modify-write updates across multiple writers |
| `AtomicReference<Config>` + `set` | Publishes whole object with clear semantics | Does not prevent lost updates if writers build from stale snapshots |
| `AtomicReference.updateAndGet` | Multiple writers updating from the current version | Does not automatically resolve business/rollback conflicts |
| `compareAndSet(expected,next)` | Optimistic revision check, rejecting writers using stale state | Caller must retry or report conflict |
| `synchronized`/`Lock` | Need to coordinate multiple resources beyond config, or a true barrier | Increases contention if hot-path readers also lock |
| `ReadWriteLock` | Certain read-heavy workloads needing complex resource consistency | Can still be heavier than an immutable snapshot read |
| `LongAdder`/`AtomicLong` | Independently counting events or drops | Does not replace an atomic snapshot of multiple fields |

**No single primitive automatically turns configuration, classloaders, bytecode topology, and exporters into a single transaction.** Choose consistency boundaries based on the observability contract the system needs.

### 12.1. Avoiding ABA and unexpected rollbacks

If two snapshots have identical `enabled/filter` contents but were published at different times, they are still **two different generations**. Keeping a monotonically increasing `version` helps with auditing, rollout comparison, and detecting stale events.

`AtomicReference.compareAndSet` compares reference identity, not config contents; do not rely on `equals` as an automatic substitute when applying CAS. If you want to roll back, publish **a new snapshot with a new revision** containing the restored contents, rather than reverting the version to an old number and creating hard-to-trace events.

## 13. Reproducible Testing Strategy for Concurrent Reloads

Do not just write a test like:

```java
Thread.sleep(100);
config.enabled = false;
```

and guess how far the invocation has progressed. A `sleep` call does not prove the worker thread is at the intended stage. Use `CountDownLatch`, `CyclicBarrier`, or wait conditions with clear contracts.

Scenarios to test:

1. Invocation starts at v1 and is accepted; switch to disabled v2 before exit. **Exactly one v1 event**.
2. Invocation starts at disabled v2; enable v3 before exit. **No event emitted** for that invocation.
3. Filter v1 accepts only `checkout`, v3 accepts only `inventory`. Methods starting in each version must use the right filter.
4. Concurrent reloads from two control threads. No **mixed configuration** or lost updates outside the defined policy.
5. New configuration has an invalid regex/sink. No partial publication; keep the old snapshot.
6. Method throws an exception. Exit receives the same token, exceptional outcome, without losing the `Throwable`.
7. Nested or recursive method calls. Tokens of individual invocations do not overwrite each other.
8. Multiple class loaders define the same method name. Filter must identify unambiguously.
9. Disabled hot path allocates no event/ticket and avoids unnecessary clock calls.
10. Slow/failing/dropping exporter. Instrumentation does not alter business code behavior; loss counters accurately reflect drops.
11. Swapping sinks while old invocations are in flight. Old sink lives long enough or has a drain protocol.
12. Reconfiguration with thousands of concurrent readers; measure CPU, allocation, tail latency, and throughput.
13. If hard disable is required, test the race where a **reader grabs v1 but has not registered in-flight yet**.
14. If async continuations exist, test propagating request-level config/context and ensure no thread-local state leaks.

A log chart including `configVersion` on **events** will help distinguish “late-arriving event” from “probe reading the wrong version”.

## 14. Common Design Mistakes

| Mistake | Consequence | How to fix |
|---|---|---|
| Using two independent `volatile` flags | Reader sees mixed v1/v2 state | Publish one immutable `Config` |
| Locking config at entry but re-reading at exit | Mid-flight filter change causes unpaired events | Pass a ticket containing the snapshot |
| Mutating an in-use `HashSet` filter | Data race, nondeterministic results | `Set.copyOf`, swap the object |
| Using one static `startedAt` for all threads | Durations mix across invocations | Token per invocation |
| Single `ThreadLocal` slot for nested calls | Outer scope overwritten by inner scope | Stack/push-pop or local token |
| `updateAndGet` lambda performing I/O/logging | Lambda may re-run under contention | Side-effect-free lambda |
| Calling `set` from a stale snapshot across multiple writers | Lost updates | CAS / `updateAndGet` with merge policy |
| Publishing enabled before creating the sink | Hook may call an unready sink | Build/validate then publish once |
| Assuming disabling `enabled` waits for all old calls to finish | v1 events appear after disable time | Document per-invocation semantics or drain |
| Assuming changing the filter adds hooks to uninstrumented methods | No events even when allowed | Inject hooks by topology/retransform when needed |
| Using `removeTransformer` to remove old hooks | Already-installed bytecode still calls probe | Runtime guard or appropriate retransform |
| Sink callback throwing an exception | Alters business method outcome | Nonthrowing reporter / failure isolation |
| Unbounded queue | Memory grows when exporter is slow | Bounded buffer + drop policy |
| Printing actual duration in expected stdout | Flaky tests | Assert only outcome/version/count |
| Not recording version in events | Hard to explain late old events | Lock generation in the token |

## 15. Self-Check Questions

**Q1.** Why are two fields `volatile boolean enabled` and `volatile Set<String> filter` not enough?

**Answer:** They have individual visibility, but a reader reading at two different points in time can combine values from two versions. You need a single immutable snapshot object published through one reference.

**Q2.** Why is calling `current.get()` once at entry better than calling it again at exit?

**Answer:** Entry, filter, sampler, start timestamp, and sink all belong to the same configuration. Re-reading at exit can produce unpaired events or write to the wrong sink.

**Q3.** Disabled at v2, yet a v1 event arrives afterward. Under per-invocation semantics, is this a bug?

**Answer:** No. The invocation was accepted at v1 and is entitled to finish under snapshot v1. To guarantee no more old events, a stronger policy is needed.

**Q4.** Why is `Set.copyOf(methods)` important?

**Answer:** It prevents an external reference from mutating the filter set currently used by many invocations; a `final` record field alone does not make a mutable collection immutable.

**Q5.** Can `updateAndGet` invoke its lambda multiple times?

**Answer:** Yes, under CAS contention. The lambda must be side-effect-free.

**Q6.** A method was never instrumented, and the filter just added that method. Will events appear automatically?

**Answer:** No. A bytecode hook must exist first; runtime config only controls hooks that already exist.

**Q7.** Can a single-slot `ThreadLocal<Ticket>` be used for recursion?

**Answer:** It is unsafe for nested invocations because the inner token overwrites the outer token. Use a stack or a separate local token per invocation.

**Q8.** Does an `AtomicBoolean finished` guarantee that the server received the event exactly once?

**Answer:** No. It only prevents repeated `finish` calls on the ticket; the exporter/queue can still drop or duplicate events on retries without an appropriate protocol.

**Q9.** To prevent all old-version events after the disable API returns, is `AtomicReference.set` enough?

**Answer:** No. You must design admission/quiescence/drain or an appropriate epoch drop policy, paying attention to the race between reading the snapshot and registering in-flight.

**Q10.** In the example, why does the output print `checkout v=1` after logging `[reload] version=2`?

**Answer:** The worker thread created ticket v1 before main published v2, enforced by the latch. `finish` uses the snapshot in the ticket rather than re-reading the config.

**Q11.** What happens if two control threads want to change two independent fields and both call `set` from a stale snapshot?

**Answer:** There is a risk of lost updates. Use atomic read-modify-write (`updateAndGet`/CAS), and define a merge and conflict policy.

**Q12.** In the example, when `inventory` throws `IllegalArgumentException`, which event is recorded?

**Answer:** `inventory v=3 outcome=EXCEPTIONAL`; the exception is propagated back to the caller if the sink does not interfere.

## 16. Checklist for Real-World Java Instrumentation

| Item | What to verify |
|---|---|
| Consistency unit | Per-invocation or per-request; is hard disable required? |
| Atomic config publication | One immutable `Config` object |
| Mutable collections copied | Do not mutate filters in use |
| How many hot-path reads? | One atomic/volatile snapshot read at entry |
| What does the entry token hold? | Config version, sampling decision, start time, sink/routing |
| Disabled path | No ticket/event allocation, no unnecessary clock/I/O |
| Exit hook | Uses **the exact entry token**; covers normal/exceptional paths |
| Nested/recursive | Does not overwrite another invocation’s token |
| Async boundaries | Context propagated intentionally |
| Concurrent writers | CAS/`updateAndGet`, clear conflict policy |
| Validate before publish | Valid filter/sink/regex |
| In-flight policy | Are v1 events allowed to be sent after v2? |
| Sink lifetime | Old sink is not closed while old tokens remain |
| Exporter failures | Does not break business result; has drop metrics |
| Instrumentation topology | Does the method already have a hook? If not, needs a transformer |
| Performance | Measure allocation, CPU, tail latency under load |
| QA | Latches, exceptional paths, reload stress, event version |

## 17. Conclusion

- **Do not** update `enabled`, `filter`, `sampler`, and `sink` via multiple mutable fields and expect every thread to see a consistent configuration.
- Create an **immutable `Config`**, validate it first, and publish **one atomic reference**.
- At method entry, read the snapshot **exactly once** and store it in an **invocation-specific token**. Method exit must use that token and not read the current configuration again.
- Under the per-invocation policy, a call that started at **v1** is recorded under v1 even if the control thread published **v2 disabled** before it finished.
- `AtomicReference.updateAndGet` helps update from the current version when multiple writers compete; the lambda must have **no side effects**.
- Atomic config does not automatically remove bytecode hooks, hard-stop all old invocations, or solve exporter/backpressure. Those are separate contracts.
- The Java 17+ example proves with `CountDownLatch` that **filter, enabled, version, and sink are locked in consistently** under concurrent reloads.

## Official References

- Oracle JDK 17 — [`AtomicReference`: `get`, `set`, `compareAndSet`, `updateAndGet`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html).
- Oracle JDK 17 — [`AtomicBoolean`: `compareAndSet`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicBoolean.html).
- Oracle JDK 17 — [`CountDownLatch`: happens-before and `await`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html).
- Oracle JDK 17 — [`Set.copyOf` and immutable collections](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection)).
- Oracle JDK 17 — [`ConcurrentLinkedQueue`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentLinkedQueue.html).
- Oracle Java SE 17 — [Java Language Specification §17.4: Memory Model, synchronization and happens-before](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4).
- Oracle JDK 17 — [`Instrumentation`: transformer, retransform, removeTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html).
- Oracle JDK 17 — [`ClassFileTransformer`: callback and chaining contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html).
