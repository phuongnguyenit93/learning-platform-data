# Cost and Reference Lifetimes When Repeating Class Inspection with Java Instrumentation

## 1. The Problem: A Cheap One-Time Inspection Does Not Mean Repeating It Forever Is Cheap

In a Java agent, calling `Instrumentation.getAllLoadedClasses()` to see which classes the JVM currently has is a very useful operation when investigating class loading, checking instrumentation scope, gathering class loader statistics, or deciding whether an already-loaded class is eligible for retransformation.

However, **class inspection is not a free operation**. Each call can allocate a new array containing a large number of `Class<?>` references. If you continue iterating over the array, querying modules, loaders, modifiability, reflection, or storing the results, the cost can increase significantly. And if the agent holds onto `Class<?>` or `ClassLoader` references for too long, it can inadvertently **prevent the class loader and the classes it defined from being reclaimed**, even after the plugin or application has unloaded them.

There are two independent questions to address:

1. **Execution cost:** how long does each inspection take, how much temporary data does it allocate, and does it affect latency and JVM behavior?
2. **Reference lifetime:** after the inspection, which objects does the agent still hold; does it keep class loaders that could otherwise be GC'd alive longer than necessary?

This lesson belongs to the **Runtime Class Inspection** section. The focus is on `getAllLoadedClasses()`, `getInitiatedClasses(ClassLoader)`, `isModifiableClass(Class<?>)`, and designing data lifetimes in an agent. The examples use **Java 17+** and the official `java.lang.instrument` API.

**Key takeaway:** treat an inspection pass as a **temporary snapshot**, extract the needed metrics, and drop the references; do not turn every snapshot into a `Class<?>` list that lives for the entire lifetime of the JVM.

## 2. Three Commonly Used APIs for Class Inspection

### 2.1. `getAllLoadedClasses()`: Capturing a JVM-Wide List

```java
Class<?>[] classes = instrumentation.getAllLoadedClasses();
```

According to the Java 17 Javadoc, this API returns an array of all classes/interfaces **currently loaded by the JVM**. The result includes:

- Regular classes and interfaces;
- **Hidden classes/interfaces**;
- **Array classes** of various element types.

This array is **not a live view** that updates automatically. After the call returns, the JVM may continue loading or unloading classes; the old array does not automatically reflect those changes.

Points to understand accurately:

- The result is **a `Class<?>[]`**, not class names or statistical records.
- On Java 17, **hidden classes** can appear in the list, even though they cannot be looked up by name through a class loader like regular classes.
- Elements may include array types; an array class does not imply there is a standalone class file to transform.
- Do not assume element ordering is stable across passes, JVMs, or restarts.
- The API does not guarantee "freezing" all application class loading/unloading after the snapshot point.
- Do not infer that every `Class<?>` is a class that can be redefined/retransformed; separate eligibility checks are required.

Counting-only example:

```java
Class<?>[] snapshot = inst.getAllLoadedClasses();
int total = snapshot.length;
// Use the snapshot within a short scope, then do not retain it.
```

This is an **illustrative snippet**, where the `inst` variable is passed into the agent; it is not a standalone program.

### 2.2. `getInitiatedClasses(loader)`: Inspecting by Initiating Loader

```java
Class<?>[] initiated =
        instrumentation.getInitiatedClasses(targetLoader);
```

This method returns the classes for which `targetLoader` can find by name according to `ClassLoader.loadClass`, `Class.forName`, and bytecode linking rules — meaning classes for which the loader has been recorded as an **initiating loader**.

**An initiating loader is not necessarily the defining loader.**

For example, the system loader may initiate a request to find `java.lang.String` and delegate to the bootstrap loader. The `String` class is **defined by the bootstrap loader** even though the system loader may be an initiating loader in a resolution path.

Differences compared to `getAllLoadedClasses()`:

- Queries **for a specific loader**, not the entire JVM.
- If the `loader == null` argument is passed, it queries the list of classes that the **bootstrap loader** can find by name.
- The result **does not contain hidden classes/interfaces** or array classes whose element type is a hidden class/interface, because they cannot be found by name in the usual way.
- If you call it for multiple loaders and sum all the lengths, **it will not necessarily yield the unique class count of the JVM**: the same class defined by a parent can appear in the initiated set of multiple loaders.
- Do not treat this as an API that "only lists classes directly defined by this loader."

**When should you use it?** When you only care about a known initiating loader and your problem definition matches initiating semantics, such as observing classes that have been resolved through a plugin loader. Do not use it as a semantically equivalent replacement for `getAllLoadedClasses()`.

### 2.3. `isModifiableClass(type)`: Checking Each Class, Not Every Class Is Modifiable

```java
boolean candidate = instrumentation.isModifiableClass(type);
```

This method returns whether the JVM allows modifying that class via redefinition or retransformation **in terms of class kind**. It does **not** itself confirm that the agent has been granted retransform/redefine capabilities; `isRetransformClassesSupported()` and `isRedefineClassesSupported()` are separate preconditions.

Notes:

- Primitive and array classes are **never modifiable**.
- `isModifiableClass(type) == true` **does not guarantee that every classfile replacement is valid**.
- Checking modifiability for **tens of thousands of classes on every inspection** is extra work; it is not free and is usually unnecessary if the goal is just counting classes.
- You should **filter to the classes of interest first**, and only then call `isModifiableClass` for the classes the agent actually intends to process.

Do not call `retransformClasses` or `redefineClasses` just to check whether a class exists: those are **runtime-mutating operations**, not pure enumeration.

## 3. Where Does the Cost Come From?

A JVM-wide inspection pass typically incurs the following categories of cost:

| Item | Cause | What to Measure |
| --- | --- | --- |
| Taking the snapshot | The JVM must provide an array containing references to loaded classes | Duration of `getAllLoadedClasses()`, array length |
| Allocation | Each `Class<?>[]` array occupies heap and holds references while alive | *Shallow* size of the array, allocation rate |
| Iteration/filtering | Each element needs name, loader, module, array/hidden checks | Processing time per pass, number of elements iterated |
| Additional queries | `isModifiableClass`, reflection, annotation inspection, resource lookup | Call count and added time |
| Data transfer/logging | Writing every class name, JSON serialization, pushing telemetry/network | Bytes/log records, blocking time, backpressure |
| Storing results | Caching or retaining snapshots on the heap | Retained heap, classloader retention/unloading |
| Concurrency | Overlapping scans or scans competing with class loading | Contention, tail latency, queue backlog |

### 3.1. Cost Grows with the Number of Classes

Suppose at a given moment the JVM has `N` `Class<?>` objects within the inspection scope. Merely returning an array of `N` elements already requires resources proportional to the element count; if the agent iterates over each element, the work of the **loop in the agent** is `O(N)`.

Do not turn this description into an exact guarantee that the internal implementation of `getAllLoadedClasses()` has a fixed complexity or pause time on every JVM. The specification does not guarantee speed; actual numbers depend on the runtime, class count, GC, class loaders, and configuration.

If run **once per second** in a system with many classes, even a few milliseconds per pass accumulates into significant CPU/heap pressure. If each pass also logs all class names or checks modifiability, the overhead can exceed that of the snapshot itself.

### 3.2. The Snapshot Array Lives on the Heap, Not Measuring All of Metaspace

A `Class<?>[]` holds **references** to `Class<?>` objects. If it has `N` elements, the array size consists of the header and space for `N` references; the number of bytes per reference depends on the JVM and compressed references settings.

`Instrumentation.getObjectSize(snapshot)` returns an **implementation-specific approximation of the *shallow* object size**, useful for comparisons within the same environment. It is **not**:

- The total heap of all `Class<?>` objects in the array;
- The total metadata/Metaspace of the classes;
- The total retained heap of the classloader/object graph;
- An exact measurement tool for GC pauses or memory leaks;
- A portable byte count across two different JVMs.

Do not multiply the result of `getObjectSize(Class<?>[])` and claim "it costs that much Metaspace." If you need to evaluate impact on Metaspace/class unloading, combine JFR, GC logs, or heap/classloader diagnostic tools on the target JVM.

### 3.3. Post-Snapshot Cost Is Usually Created by the Agent Itself

This snippet is relatively lightweight:

```java
Class<?>[] classes = inst.getAllLoadedClasses();
int count = classes.length;
```

But the following logic can be very expensive:

```java
for (Class<?> c : classes) {
    System.out.println(c.getName());
    // Deep reflection, reading annotations, calling other APIs for every class...
}
```

Printing every line synchronously can dominate the total time. Analyzing annotations or reflective members can trigger substantial secondary work, module/security checks, or loading additional dependent classes depending on how it is used. If deep metadata is needed, restrict it to **truly relevant classes** rather than the entire JVM.

## 4. `Class<?>` Reference Lifetimes and the Risk of Keeping Loaders Alive

### 4.1. The Critical Reference Path

According to the Java 17 `ClassLoader` Javadoc, a `Class` object contains a reference to its **defining class loader**.

```text
Agent's GC root
      |
      v
static Map<Class<?>, Metadata>
      |
      +---- key: plugin's Class<?>
                  |
                  v
           defining ClassLoader
                  |
                  v
           plugin's classes/resources
```

If an agent holds `Class<?>` in a static collection, it can keep the defining loader reachable. For a plugin loader that is no longer used by the application, **a strong reference from the agent can prevent the loader from being reclaimed**. As a consequence, the associated class metadata/Metaspace may not be freed when the system expects.

The same thing can happen if you store:

- A `Class<?>[]` snapshot in a static field;
- `List<Class<?>>`, `Set<Class<?>>`, or `Map<Class<?>, ...>` without eviction;
- `ClassLoader` directly as a map key or value;
- `Method`, `Field`, `Constructor`, or reflective metadata that holds references to the declaring class;
- Object instances created by plugin classes, or lambdas/tasks/thread contexts holding the plugin loader;
- `Throwable`/stack traces or infrastructure objects holding unreleased references.

**Not every `String` containing a class name retains a ClassLoader.** Storing counts/plain names can avoid retaining `Class<?>`, but still carries the risk of **unbounded heap growth** if you create a key for every loader/class/inspection pass. Avoiding memory leaks requires both the **right reference type** and **bounded data size**.

### 4.2. Class Unloading Is Not Guaranteed Just by Dropping One Reference

According to JLS `12.7, a class/interface may be unloaded **only if its defining class loader may be reclaimed**; classes defined by the bootstrap loader cannot be unloaded under this rule.

However, "may" **does not mean will**:

- GC may not have run yet or may not decide to unload immediately;
- The plugin may still have threads, instances, thread-locals, callbacks, caches, or executors holding the loader;
- Another agent may also be holding the class/loader;
- The runtime behavior depends on GC/class unloading policies and reachability state.

Therefore, after clearing a cache, **you must not assert that a class has definitely been unloaded**. You need to measure using class unload/JFR events, JVM logs, or heap/classloader tools if you want to draw a conclusion. `System.gc()` is not a portable guarantee of reclaim/unload timing.

### 4.3. A Short-Lived Snapshot Is Still a Strong Reference While in Use

A `Class<?>[]` returned from `getAllLoadedClasses()` is an array of strong references for as long as the agent holds it. It can extend the lifetime of classes/loaders **until the array and its references are no longer reachable**.

That is normal for a short scan:

```java
static int countLoaded(Instrumentation inst) {
    Class<?>[] snapshot = inst.getAllLoadedClasses();
    return snapshot.length;
}
```

After the method returns, if the snapshot is not stored elsewhere, the array is no longer held by this method. **There is no need to call `System.gc()` or manually null out every element** to "free" it; the GC decides the actual timing.

Conversely:

```java
static final java.util.List<Class<?>> ALL_EVER_SEEN =
        new java.util.ArrayList<>();

static void badPoll(Instrumentation inst) {
    java.util.Collections.addAll(
            ALL_EVER_SEEN, inst.getAllLoadedClasses());
}
```

This is an **illustrative anti-pattern snippet**, not a standalone program. Every pass appends a large batch of references (many duplicate elements). The list grows with the number of passes, retains classes/loaders long-term, and makes it hard to distinguish unloaded classes from current ones.

A variant like `static Class<?>[] lastSnapshot`, while not duplicating data endlessly like the list above, **still** retains every class from the most recent snapshot; after overwriting the old array, the new snapshot continues holding references to many classes. "Only storing one snapshot" does not mean there is no impact on class unloading.

## 5. Inspection Records Have a Different Lifetime Than Snapshots

A simple design rule:

```text
getAllLoadedClasses()
        |
        v
Class<?>[] snapshot — SHORT SCOPE
        |
        +--> Iterate/classify
        |      |
        |      +--> count (int)
        |      +--> durationNanos (long)
        |      +--> bounded-size histogram
        |      +--> normalized module/loader name if truly needed
        |
        v
End of scan pass
        |
        +--> Do not retain snapshot/Class<?>/ClassLoader
        |
        v
Store only scalars or DTOs containing no class references
```

A **`record ScanStats(int total, int arrays, long durationNanos)`** contains only integers and does not reference class loaders through its fields. That is a good design for long-term statistics.

If you need to track a specific class long-term, treat that as an explicit functional requirement. You can use weak references, `ClassValue`, epoch-scoped caches, or plugin lifecycle hooks — but do not assume any "magic" cache type automatically solves all retention issues.

## 6. Complete Java 17 Example: Repeating Inspections While Retaining Only Aggregated Metrics

This example uses a Java agent started with `-javaagent` to obtain `Instrumentation`, after which the application explicitly invokes **three sequential scan passes**:

1. A scan that only counts class groups.
2. A similar scan to observe cost and runtime changes.
3. A deeper scan that only checks `isModifiableClass` for **classes defined by the system loader**.

The learning point is that **the snapshot is locally scoped**, while the return value is only a record containing primitives. The lesson does not try to prove that the JVM will have a fixed class count or fixed duration; those numbers vary by environment.

### 6.1. Directory Structure

```text
class-survey-demo/
├── SurveyAgent.java
├── SurveyTarget.java
├── SurveyApp.java
└── agent.mf
```

The sources are in the default package so the compile commands are easy to follow. Use JDK 17+.

### 6.2. `SurveyAgent.java`

```java
import java.lang.instrument.Instrumentation;

public final class SurveyAgent {
    private static volatile Instrumentation instrumentation;

    private SurveyAgent() {
    }

    public static void premain(
            String agentArgs, Instrumentation inst) {
        instrumentation = inst;
    }

    // Contains only primitives, does not retain Class<?> or ClassLoader.
    public record Stats(
            int total,
            int arrayClasses,
            int hiddenClasses,
            int systemDefined,
            int modifiableSystemDefined,
            long snapshotShallowBytes,
            long elapsedNanos) {
    }

    public static Stats scan(boolean deep) {
        Instrumentation inst = instrumentation;
        if (inst == null) {
            throw new IllegalStateException("Agent not installed");
        }

        long started = System.nanoTime();

        // Keep the array only within this method.
        Class<?>[] snapshot = inst.getAllLoadedClasses();

        int arrays = 0;
        int hidden = 0;
        int system = 0;
        int modifiable = 0;

        ClassLoader systemLoader =
                ClassLoader.getSystemClassLoader();

        for (Class<?> type : snapshot) {
            if (type.isArray()) {
                arrays++;
            }
            if (type.isHidden()) {
                hidden++;
            }

            // Filter before attempting isModifiableClass.
            // This classification selects defining loader, not initiating.
            if (!type.isArray()
                    && !type.isPrimitive()
                    && type.getClassLoader() == systemLoader) {
                system++;

                if (deep && inst.isModifiableClass(type)) {
                    modifiable++;
                }
            }
        }

        // Shallow size estimate of the ARRAY, not Metaspace.
        long arrayBytes = inst.getObjectSize(snapshot);
        long elapsed = System.nanoTime() - started;

        // Do not return snapshot, Class<?>, or loader.
        return new Stats(
                snapshot.length,
                arrays,
                hidden,
                system,
                deep ? modifiable : -1,
                arrayBytes,
                elapsed);
    }
}
```

**Code explanation:**

- `premain` stores `Instrumentation` so the demo application can call `scan` after the JVM starts. In production, restrict this API to authorized agent components and do not expose the `Instrumentation` object to untrusted code.
- `Class<?>[] snapshot` is a **local** variable; it only lives for the scope needed to iterate.
- `Stats` contains all metrics as primitives; it contains no `Class<?>`, `ClassLoader`, or snapshot array.
- `isArray()` and `isHidden()` serve for fast classification. Hidden classes are included by the `getAllLoadedClasses` Javadoc; array types can also be present.
- `systemDefined` here refers to classes whose **defining loader is strictly the system loader** (reference identity comparison), not all classes the system loader can initiate.
- `deep=false` mode **does not** call `isModifiableClass` for each class, and `modifiableSystemDefined=-1` means "not measured," not that there are -1 classes.
- `deep=true` mode only checks modifiability within the **filtered set**; if you want to measure all classes, you must accept higher cost and separate out non-modifiable classes.
- `getObjectSize(snapshot)` is the **shallow size of the array** and is implementation-specific.
- `elapsedNanos` includes fetching the array, iterating, filtering, mode-dependent checking, and getting the shallow size; it does **not** measure the cost of `getAllLoadedClasses` in isolation. To isolate it, place an independent timer right around the call.
- There is no class loading by name inside the loop; the program only uses the `Class<?>` objects provided by the JVM.

### 6.3. `SurveyTarget.java`

```java
public final class SurveyTarget {
    private SurveyTarget() {
    }

    public static int value() {
        return 42;
    }
}
```

This class gives the application deterministic work to perform before starting the scans.

### 6.4. `SurveyApp.java`

```java
public final class SurveyApp {
    private SurveyApp() {
    }

    private static void print(String label, SurveyAgent.Stats s) {
        System.out.println("[scan] " + label
                + " total=" + s.total()
                + " arrays=" + s.arrayClasses()
                + " hidden=" + s.hiddenClasses()
                + " system=" + s.systemDefined()
                + " modifiable=" + s.modifiableSystemDefined()
                + " arrayBytes=" + s.snapshotShallowBytes()
                + " elapsedNanos=" + s.elapsedNanos());
    }

    public static void main(String[] args) {
        System.out.println("[app] target=" + SurveyTarget.value());

        // Do not retain Class<?> lists across passes.
        SurveyAgent.Stats first = SurveyAgent.scan(false);
        SurveyAgent.Stats second = SurveyAgent.scan(false);
        SurveyAgent.Stats deep = SurveyAgent.scan(true);

        System.out.println("[app] completedScans=3");
        System.out.println("[app] allNonEmpty="
                + (first.total() > 0
                && second.total() > 0
                && deep.total() > 0));

        print("first", first);
        print("second", second);
        print("deep", deep);
    }
}
```

You cannot treat `first.total()` or `deep.elapsedNanos()` as constant numbers across all JVMs. Even while the agent is running, the runtime may load additional helper classes or unload classes from other plugins.

### 6.5. `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: SurveyAgent

```

Only `Premain-Class` is needed. Because the example **does not** call retransform/redefine, `Can-Retransform-Classes` or `Can-Redefine-Classes` are not required.

### 6.6. Compile, Package, and Run on Linux/macOS/WSL

From the `class-survey-demo/` directory:

```bash
mkdir -p out

javac --release 17 -d out \
  SurveyAgent.java SurveyTarget.java SurveyApp.java

# Agent JAR contains the agent and the nested record Stats.
jar --create --file survey-agent.jar --manifest agent.mf \
  -C out SurveyAgent.class -C out 'SurveyAgent$Stats.class'

# App JAR contains the two application classes.
jar --create --file survey-app.jar \
  -C out SurveyApp.class -C out SurveyTarget.class

java -javaagent:survey-agent.jar \
  -cp "survey-agent.jar:survey-app.jar" SurveyApp
```

`SurveyAgent$Stats.class` is the file generated by the compiler for the nested record. Single quotes protect the `$` character from the POSIX shell. Do not omit the nested record file when packaging the agent JAR.

### 6.7. Windows PowerShell

```powershell
New-Item -ItemType Directory -Force out | Out-Null

javac --release 17 -d out SurveyAgent.java SurveyTarget.java SurveyApp.java

jar --create --file survey-agent.jar --manifest agent.mf -C out SurveyAgent.class -C out 'SurveyAgent$Stats.class'
jar --create --file survey-app.jar -C out SurveyApp.class -C out SurveyTarget.class

java -javaagent:survey-agent.jar -cp "survey-agent.jar;survey-app.jar" SurveyApp
```

Run the commands in the same directory containing the three source files and `agent.mf`.

### 6.8. Output: What Is Fixed, What Varies?

The first three lines are **deterministic results when the demo succeeds**:

```text
[app] target=42
[app] completedScans=3
[app] allNonEmpty=true
```

After that are **three lines starting with** `[scan] first`, `[scan] second`, and `[scan] deep`. Each line contains the fields `total`, `arrays`, `hidden`, `system`, `modifiable`, `arrayBytes`, and `elapsedNanos` with **actual measured values**, with no fixed portable numbers.

Note the order: the program prints `[app] completedScans=3` and `[app] allNonEmpty=true` **before** the three `[scan]` data lines, even though the inspections were already performed earlier.

In the `first` and `second` passes, the `modifiable=-1` field (not measured). In the `deep` pass, this value is a non-negative number, because the program checks a filtered set of classes. Do not assert `second.total >= first.total`: the JVM can load **and unload** classes between two snapshots.

### 6.9. How to Evaluate the Results

- If `elapsedNanos` of the `deep` pass is larger than the two basic passes, it may be due to many `isModifiableClass` calls; however, **a single trial is not enough to conclude average overhead**.
- If `total` increases across passes, check whether the runtime loaded new classes, rather than immediately concluding the agent has a leak.
- If `arrayBytes` increases, the snapshot array is larger; that number **does not directly measure retained Metaspace**.
- When the three scans complete, the application still holds no `Class<?>[]` **after `scan` returns**. This eliminates one retention source created by the example itself, **and does not prove the entire JVM has no caches retaining class loaders**.

## 7. Anti-patterns: Retaining Snapshot History and Previously Seen Classes

### 7.1. Storing Every Snapshot Over Time

```java
static final java.util.List<Class<?>[]> HISTORY =
        new java.util.ArrayList<>();

static void retainEveryScan(Instrumentation inst) {
    HISTORY.add(inst.getAllLoadedClasses());
}
```

This is an **illustrative anti-pattern**, not a standalone program. After `K` passes, the agent is holding `K` arrays — each array potentially containing many duplicate references. Class loaders that the application has stopped using may remain reachable through old snapshots.

If you need history for charting, store:

```text
timestamp, totalLoadedCount, arrayCount, hiddenCount, scanDuration
```

as bounded scalar/time-series data, rather than storing every `Class<?>[]` array.

### 7.2. Caching `Class<?>` Without Eviction

```java
static final java.util.Map<Class<?>, String> NAMES =
        new java.util.concurrent.ConcurrentHashMap<>();

static void remember(Class<?> type) {
    NAMES.putIfAbsent(type, type.getName());
}
```

Even though the value is only a `String`, **the `Class<?>` key is a strong reference**. A static map can keep the class and its defining loader alive forever.

If a cache is required, you need a clear contract on lifetime, entry limits, plugin unload/stop events, and cleanup. Do not put an unbounded cache in an agent just to optimize a cheap lookup like `Class.getName()`.

### 7.3. Storing the `ClassLoader` from Every Class

```java
static final java.util.Set<ClassLoader> LOADERS =
        java.util.concurrent.ConcurrentHashMap.newKeySet();

static void record(Class<?> type) {
    ClassLoader loader = type.getClassLoader();
    if (loader != null) {
        LOADERS.add(loader);
    }
}
```

This is also an **anti-pattern if keys are never removed**. In a hot-deploy system with thousands of loaders, the Set grows continuously and directly prevents the GC from reclaiming loaders that the application has unloaded.

If you only need to **count loaders in a single snapshot**, use a local structure (during the scan) and do not store the set of loader objects outside. If you need distinct IDs for long-term telemetry, design a bounded ID/lifecycle scheme and avoid relying solely on `System.identityHashCode(loader)`, as it can collide and is not a permanent identifier.

## 8. Data Lifecycle Management Practices

### 8.1. Prefer Returning DTOs Containing Only Primitives or Bounded Immutable Strings

Good design example:

```java
public record Summary(
        long timestampMillis,
        int classes,
        int hiddenClasses,
        long durationNanos) {
}
```

This snippet is an illustrative Java 17 `record`. There is no `Class<?>` or `ClassLoader` in the structure. If you add a histogram by package/module, bound the number of buckets, entries, and retention period.

**A `String` is not a class identity.** Two classes defined by two different loaders can share the same name; if you use the name as a key, their metadata will be merged. Do not solve this by strongly retaining every loader in a map that never expires.

### 8.2. `WeakReference<ClassLoader>`: Useful for Observation, Not an Unload Guarantee

```java
java.lang.ref.WeakReference<ClassLoader> ref =
        new java.lang.ref.WeakReference<>(pluginLoader);
```

This is an illustrative snippet: `pluginLoader` is a loader provided by the application/plugin lifecycle. A weak reference **does not itself keep the referent alive**, so it can serve to observe "is the loader still reachable or has it been cleared by GC?". However:

- If there is a strong reference elsewhere, `ref.get()` can still be non-`null`.
- After dropping strong references, GC **may not have run yet**; `ref.get() != null` does not prove a leak.
- When `ref.get() == null`, the loader is no longer weakly reachable according to reference semantics; however, do not infer from that alone that all external resources have been freed.
- If code retrieves `ClassLoader active = ref.get()`, the `active` variable is temporarily a **strong reference** while in use.
- Do not store additional `Class<?>`/`Method`/instances inside the value of a weak-loader-keyed cache; doing so can defeat the intent of a weak-key cache.

A `WeakHashMap<ClassLoader, Metadata>` using weak keys can be useful, **but it is not thread-safe by itself** and the value can indirectly retain the key/loader. If the value points to a `Class<?>` defined by that loader, the reference cycle from value to loader can prevent the key from being reclaimed as expected.

### 8.3. `ClassValue<T>`: Attaching Metadata per `Class<?>`

Java provides `java.lang.ClassValue<T>` to associate computed values with each class. This is a worthwhile option when you genuinely need to cache metadata **per class** without maintaining a `static Map<Class<?>, T>` with strong keys:

```java
private static final ClassValue<String> CLASS_LABEL =
        new ClassValue<>() {
            @Override
            protected String computeValue(Class<?> type) {
                return type.getName();
            }
        };
```

This is an **illustrative snippet** inside a Java class; it has no standalone entry point. `CLASS_LABEL.get(type)` retrieves the value associated with the type; `remove(type)` clears the associated value so it can be recomputed when needed.

`ClassValue` should not be understood as a promise that all data/references are always freed at the right time; the computed value may hold external resources, threads, other class loaders, or large arrays. You must control **the value's contents**, **the lifetime of the `ClassValue` itself**, and the appropriateness of caching.

### 8.4. Bounded Caches and Lifecycle Hooks

If the goal is to make instrumentation decisions for already-inspected classes:

- Bound the cache by entry count/bytes or time;
- Have TTL/epoch/invalidation tied to the plugin/module lifecycle;
- Do not use a standalone class name as identity in a multi-loader environment;
- Clear the cache when a module/plugin stops or when the policy version changes;
- Avoid holding strong references to class loaders just to remember that they were inspected;
- Control thread safety and races between scanning and unloading;
- If you need to hold class identity to actually call `retransformClasses`, hold it only in a **short-lived batch** and release it immediately upon completion.

Do not try to "measure the exact loaders" by capturing the entire graph of class loaders in a static field that is never reset.

## 9. Use Event-Driven Approaches Instead of JVM-Wide Polling When Appropriate

If the goal is to know when **a new class has just been defined** to decide whether to insert instrumentation, `ClassFileTransformer` is usually a better fit than repeatedly calling `getAllLoadedClasses()`:

```java
inst.addTransformer(new ClassFileTransformer() {
    @Override
    public byte[] transform(
            Module module,
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain protectionDomain,
            byte[] classfileBuffer) {

        if ("demo/Target".equals(className)) {
            // Record a brief event or apply policy.
        }
        return null;
    }
}, false);
```

This is an **illustrative snippet in `premain`/`agentmain`**, requiring imports for `ClassFileTransformer`, `ProtectionDomain`, and an `Instrumentation inst`. The transformer observes classes **loaded in the future** (and can redefine according to its contract). It does not automatically replay the entire history of classes loaded **before registration**.

Be careful: the callback runs on the class loading path, so work inside the callback must be **very short, free of blocking I/O, and must not trigger recursive class loading**. Event-driven approaches also have overhead; they are not a "zero overhead" solution.

When you need a full picture right at the moment the agent attaches:

1. Take **one initial snapshot** using `getAllLoadedClasses()`;
2. Filter to the classes of interest and keep only the necessary metadata;
3. Track new classes using a transformer or JVM events;
4. Periodically **reconcile** against a JVM-wide snapshot at low frequency to detect drift;
5. Do not treat the delta between two snapshots as a complete event log.

### Class Unloading Is Not Fully Represented by a Load-Time Transformer

`ClassFileTransformer` is not a callback that notifies about class unloading. If you need to determine whether a loader/class has actually unloaded, use JFR events or JVMTI/JVM class-unload diagnostics depending on the runtime. Do not treat "a class present in snapshot A but absent in snapshot B" as absolute proof of unloading when snapshots do not store full identity or when class loading/unloading occur concurrently.

## 10. Inspection Schedule: Frequency, Limits, and Backpressure

### 10.1. Choose Frequency Based on the Goal

For one-off diagnostics, a single snapshot may suffice. For long-term telemetry, polling every few seconds/minutes should only begin after measuring overhead under a realistic workload.

An operational model:

```text
Scheduled task triggers
        |
        v
Check if previous scan finished?
        |
   +----+----+
   |         |
  Yes        No
   |         |
   v         v
  Scan      Skip pass / mark skipped
   |
   v
Count / aggregate
   |
   v
Emit bounded metrics
   |
   v
Drop Class<?>[] and local references
```

Do not let the scheduler spawn another scan pass while the previous pass is still running and build up an unbounded queue. If a scan takes longer than the interval, **skip the pass** instead of opening multiple concurrent runs.

### 10.2. Set a Budget

Metrics worth recording:

- `scan_duration_ms`: total duration;
- `loaded_class_count`: snapshot size;
- `array_class_count`, `hidden_class_count`;
- `survey_failures_total` and `survey_skipped_total`;
- `scan_frequency`, `scan_overlap_count`;
- `approx_array_shallow_bytes` if needed;
- JFR/GC: heap allocation, pauses, Metaspace, and class-unload trends.

Additional details can be useful depending on the use case: number of loaders with active classes, number of classes in named modules, number of modifiable classes after filtering. Do not push every metric into a production pipeline without knowing its utility and overhead.

### 10.3. Separate API Time from Analysis Time

It is often useful to measure two intervals:

```java
long t0 = System.nanoTime();
Class<?>[] classes = inst.getAllLoadedClasses();
long t1 = System.nanoTime();

// Iterate, filter, get module, isModifiableClass...
long t2 = System.nanoTime();

long snapshotNanos = t1 - t0;
long processingNanos = t2 - t1;
```

This is an **illustrative code skeleton**: the snippet has no processing loop in between, so `processingNanos` does not represent a real pipeline. Add real logic, run warm-up, measure multiple passes, and inspect percentiles rather than a single sample. The timer also has a small overhead; keep the environment stable when comparing.

In particular, if you measure `System.nanoTime` in a JIT-warmed JVM while some modules/plugins are still loading classes, passes do not share identical conditions. Do not conclude "the API automatically slows down over time" just because the workload accumulates more classes.

## 11. Snapshots Are Not a Fixed Class List Over Time

### 11.1. Diffing Two Snapshots Has Pitfalls

Suppose:

```java
Class<?>[] previous = inst.getAllLoadedClasses();
// ... some time passes ...
Class<?>[] current = inst.getAllLoadedClasses();
```

If you retain `previous` for a long time to diff, retaining it can itself prevent some class loaders from unloading. Thus, the measurement method **has affected the subject being measured**.

You can compute a diff **within a short window**, return aggregated metrics, and then release both arrays. However, if you want to compare every class identity across many hours, a long-lived `Class<?>` set is incompatible with the requirement that class unloading remain unaffected.

### 11.2. Keying by Name Does Not Uniquely Identify a Class

Two plugin loaders can both define `com.example.Plugin`. Then:

```text
Plugin loader A -> Class<?> com.example.Plugin (A)
Plugin loader B -> Class<?> com.example.Plugin (B)
```

The two `Class<?>` objects have the same name from `getName()`, but **different class identities**. If you only store names to compare snapshots, you cannot accurately conclude how many class identities were added/removed.

Options:

- If you only want **total counts**, accept identity-free statistics;
- If you need grouping by name/module, make clear this is **aggregation** rather than per-class tracking;
- If you need true class identity, design a short-lived epoch or weak-key tracking, accounting for races and garbage collection;
- If you need accurate unload events, use dedicated JVM mechanisms instead of inferring from names and snapshot sizes.

### 11.3. Do Not Confuse Current Loaders with History

`getAllLoadedClasses()` captures the classes currently loaded at the moment the array is taken. It is not a log of "all classes ever loaded by the JVM since startup." A class may appear in an earlier snapshot, then its loader unloads and the class is absent from a later snapshot. If the agent retains a reference from the earlier snapshot, that very retention can keep the class reachable.

## 12. Diagnosing Classloader Retention and Metaspace Growth

If a hot-deploy service consumes more and more Metaspace after each plugin reload, check two categories of causes:

**Application:** threads, schedulers, thread-locals, static listeners, caches, or callbacks still holding the plugin loader/instances.

**Agent:** retained snapshots, `Map<Class<?>, ...>`, `Set<ClassLoader>`, transformer state, callbacks/handlers, or reflective metadata retaining classes/loaders.

Suggested workflow:

1. Record baselines before/during/after each plugin deployment cycle.
2. Observe classloader counts, class loading/unloading, and Metaspace via JFR/GC logs or JVM tools.
3. Inspect heap dumps/retained paths if loader counts grow abnormally; look for GC roots leading from the agent to `Class<?>`/`ClassLoader`.
4. Temporarily disable/remove **the agent-owned inspection feature** in a controlled environment to compare.
5. Fix by lifecycle: remove static snapshots, replace strong-key caches, close lifecycle listeners, and bound tracking tables.
6. Test across multiple warm-up, GC, and unload cycles; do not rely on a single `System.gc()` call.
7. Do not jump to concluding that all Metaspace growth is a leak: JIT, legitimate class loading, and GC policies can cause the curve to rise without unbounded retention.

### Using `WeakReference` as a Conditional Check

You can create a `WeakReference<ClassLoader>` to a plugin loader **that the application has just decided to unload**, drop strong references, and wait for GC to have a chance to run. If after a while `ref.get() == null`, that is evidence the loader was no longer weakly reachable at the time GC processed it. If `ref.get() != null`, **that is not enough to conclude a leak**: GC may not have collected it yet or the loader may still be legitimately in use.

When diagnosing, do not let the test itself create a `Class<?>`/ClassLoader strong reference in a static collection; otherwise the results will be polluted by the measurement code itself.

## 13. Comparing Three Approaches

| Approach | Primary Cost | Reference Lifetime | Best Suited When |
| --- | --- | --- | --- |
| `getAllLoadedClasses()` on demand | JVM-wide snapshot + per-class processing | Local array if kept brief; risky if cached | Ad-hoc investigation, infrequent reconciliation |
| `getInitiatedClasses(loader)` | Snapshot per initiating loader | Holds loader during query; local result | Only interested in classes a loader **can find by name** |
| Event-driven transformer | Callback on class load/redefine path | Retains only aggregated event data | Need to track future definitions, apply policy |
| JFR/JVMTI class events | Depends on runtime config and event types | Has its own buffer/event retention to manage | Need class load/unload history or profiling |
| Storing full `Class<?>[]` every minute | Allocation + growing retained refs | Can block unloading, grows heap over time | **Should not be used for long-term history** |
| Storing primitive summary every minute | Scan allocation/CPU + small data | Does not retain class loaders via summary results | Periodic telemetry needing trend charts |

No approach is "zero cost." Choose based on the question you need to answer, the required accuracy, and the acceptable budget.

## 14. Common Pitfalls

| Symptom | Possible Cause | Remediation |
| --- | --- | --- |
| CPU spikes every minute when agent scans | Scanning entire JVM and querying deeply for every class | Reduce frequency, filter early, measure each stage |
| GC/heap allocation increases | Creating large snapshots and logging/serializing lots of metadata each pass | Store aggregated metrics, reduce/bound exports |
| Plugin unloaded but loader remains in heap | Agent holds `Class<?>[]`, map keys, or loader references | Check GC roots, remove strong retention by lifecycle |
| Loader still not gone after `System.gc()` | GC/unloading is not guaranteed immediately or other references remain | Do not conclude a leak from one run; measure retained paths |
| `getAllLoadedClasses` returns more classes than can be retransformed | Result includes arrays/hidden/unmodifiable classes | Use `isModifiableClass` and capability checks on the target set |
| `getInitiatedClasses` summed across loaders gives too large a count | Same parent-defined class can be initiated through multiple loaders | Do not sum directly to get unique classes |
| Hidden classes missing from `getInitiatedClasses` | Hidden classes are not discoverable by name | Use the API matching the question, read the Javadoc carefully |
| `getAllLoadedClasses` contains hidden/array classes | API is specified to include them | Classify/exclude intentionally |
| Snapshots A and B have different lengths | Class loading/unloading occurred; agent/JVM may load extra classes | Do not infer leak/unload from a single diff |
| Cache keyed by `getName()` behaves wrongly | Same-named classes in two different loaders | Distinguish namespace/identity when truly needed |
| `getObjectSize(snapshot)` mistaken for Metaspace | Only the shallow size of one object | Use other classloader/JFR/GC/Metaspace metrics |
| `WeakHashMap` still retains plugin loader | Value references back to class/loader, or cache has other strong refs | Inspect object graph, do not blindly trust weak keys |
| `ClassValue` holds large data | Associated value holds resources or unbounded refs | Clean up data/lifecycle and bound caches |
| Overlapping scheduled scans | Scheduler lacks overlap/backpressure protection | Use a single worker, skip/delay pass if previous is still running |
| Trying to list unloaded classes via `getAllLoadedClasses` | Snapshot is not event history | Use JFR/JVMTI events or appropriate tracking |
| Transformer causes deadlock during inspection | Callback does I/O/locking/recursive class loading | Minimize work in callback, decouple processing, control concurrency |

## 15. Operational Checklist

1. **Define the question:** do you need the current total class count, the initiated set of one loader, or class load/unload events over time?
2. **Right API:** `getAllLoadedClasses()` is JVM-wide; `getInitiatedClasses(loader)` is by initiating loader; the two sets are not interchangeable.
3. **Short-lived snapshots:** the `Class<?>[]` array stays within the scan scope; do not retain it in static history.
4. **Filter early:** avoid calling `isModifiableClass`/deep reflection on every class when unnecessary.
5. **Do not retain loaders long-term:** audit all `Class<?>`, `ClassLoader`, reflection metadata, and plugin instance caches.
6. **Lightweight summaries:** store only scalar metrics, bounded string labels, or bounded aggregations.
7. **Lifecycle-aware caches:** consider `ClassValue`/weak references/TTL, but verify value references and thread safety.
8. **Appropriate frequency:** measure overhead on real workloads, apply backpressure, and prevent overlapping scans.
9. **Measure the right cost:** separate snapshot/processing/export times; `getObjectSize` only measures a shallow object approximation.
10. **Do not assume absolute GC:** dropping strong refs enables unloading, **it does not force the JVM to unload immediately**.
11. **Track actual unloading:** use JFR/GC logs/classloader diagnostics, do not infer from class names.
12. **Respect class identity:** loader + binary name is the basis of class definition; aggregation by name is only statistics.
13. **Do not mutate runtime to inspect:** avoid `retransformClasses` or proactive class loading when the goal is purely enumeration.
14. **Test on real Java 17:** compare behavior on a normal app and an app with many plugins/custom loaders.
15. **Preserve operational safety:** all metrics and callbacks must be compact, never creating unbounded queues or deadlocks.

## 16. Self-Check Questions

**Question 1.** Why is `getAllLoadedClasses()` unsuitable as a "history" kept forever in a static list?

**Answer:** Each call returns an array containing strong `Class<?>` references. Keeping a history can grow the heap and keep classes/defining class loaders reachable, preventing some class loaders from having a chance to be GC'd/unloaded.

**Question 2.** Does `getInitiatedClasses(loader)` only return classes defined by that loader itself?

**Answer:** No. It follows **initiating loader** semantics; classes defined by a parent/bootstrap loader can still appear in another loader's initiated set.

**Question 3.** Does `getAllLoadedClasses()` exclude hidden classes or array classes?

**Answer:** No. The Java 17 Javadoc specifies that it includes hidden classes/interfaces and array classes. Conversely, `getInitiatedClasses` does not list hidden classes or array classes of hidden element types because they are not discoverable by name.

**Question 4.** Why can a static `Map<Class<?>, Metadata>` cause a classloader leak?

**Answer:** The strong key references the `Class<?>` object; that object links to its defining `ClassLoader`. If the map retains the key long-term, the loader can remain reachable even after the application has stopped using the plugin.

**Question 5.** Does clearing all agent snapshots guarantee the class loader will be GC'd immediately?

**Answer:** No. There may still be references elsewhere, and GC/unloading is behavior decided by the JVM. Clearing snapshots only removes one source of retention.

**Question 6.** Does `getObjectSize(snapshot)` measure the total Metaspace of all classes in the array?

**Answer:** No. It is an implementation-specific estimate of the shallow size of the array object.

**Question 7.** Two scans return `total` values of 10,000 and 9,900 respectively. Can we conclude that exactly 100 classes unloaded?

**Answer:** No. Between two snapshots both loading and unloading can occur concurrently, the result also includes arrays/hidden classes, and the measurement itself does not carry full history.

**Question 8.** When you only need to instrument newly loaded classes, do you need to poll `getAllLoadedClasses()` every second?

**Answer:** Usually no. You can use an event-driven `ClassFileTransformer` for classes defined after registration, combined with one initial scan if you need to process already-loaded classes.

## 17. Official Documentation

- [Java SE 17 — `Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `getAllLoadedClasses`, `getInitiatedClasses`, `getObjectSize`, `isModifiableClass`, and transform/retransform.
- [Java SE 17 — `ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): defining vs initiating loader; `Class` holds a reference to its defining loader.
- [Java Language Specification SE 17 — `12.7 Unloading of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.7): conditions for class unloading, no guarantee of unloading while the loader remains reachable.
- [Java SE 17 — `WeakReference`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html): weak reachability and referent collection.
- [Java SE 17 — `ClassValue`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassValue.html): associating metadata per class without designing a static map with strong keys.
- [Java SE 17 — `Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getName`, `getClassLoader`, `isArray`, `isHidden`, and class identity.
- [Java SE 17 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): callback on define/redefine/retransform, limiting work on the class loading path.

**Remember:** **Class inspection is an operation that creates a temporary snapshot and temporary strong references.** When repeating `getAllLoadedClasses()`, measure the cost, filter the work, keep the snapshot alive as briefly as possible, and store only aggregated data. A `Class<?>` retained in the agent can keep its defining class loader alive, whereas dropping references only enables — and does not immediately guarantee — class unloading.
