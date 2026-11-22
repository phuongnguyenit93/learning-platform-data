# Detecting Delegation Cycles and Avoiding Infinite Recursion in Java ClassLoader

## 1. The Problem: A Class Loading Request Loops Back to Its Starting Point

`ClassLoader` instances typically coordinate using a **delegation** mechanism: a loader receives a class name, asks its parent, and only searches for the class itself when the parent cannot find it. This workflow helps share foundational classes and common APIs/SPIs, and prevents creating duplicate runtime types. However, if an application builds custom delegation relationships across multiple loaders **without controlling directionality**, a request can loop back to the original loader.

Example of a misconfigured graph:

```text
                loadClass("plugin.Report")
                      |
                      v
                PluginLoader A
                      |
                 delegate to
                      v
                PluginLoader B
                      |
                 delegate to
                      v
                PluginLoader A
                      |
                 delegate to B
                      v
                     ...
```

If each loader simply forwards the request without recognizing that it has already appeared on the same call path, the Java call chain can recurse until the stack is exhausted, causing a `StackOverflowError`. In implementations that hold class-loading locks across multiple loaders, a request cycle can also lead to a **cross-thread deadlock**, depending on lock acquisition order and the delegation algorithm.

Topics to address include:

1. When does a delegation cycle occur?
2. How to distinguish a **cross-loader** cycle from valid recursion and from a **class inheritance** cycle.
3. How to design an **acyclic delegation graph**.
4. How to detect looping call paths using a **(loader, binary name)** key.
5. Why a thread-local guard only solves **same-thread recursion** and is insufficient for all multithreaded scenarios.
6. How to test and log without breaking class-loading rules, locking, parent delegation, and type identity.

## 2. Four Types of "Cycles" Must Be Distinguished

| Scenario | Example | Consequence / Interpretation |
| --- | --- | --- |
| Custom **delegation** cycle | A asks B, and B asks A for the same `com.acme.Widget` | Can cause infinite `loadClass` recursion if there is no guard or exit path |
| **Class/interface relationship** cycle in class files | Invalid bytecode where X extends Y and Y extends X | The JVM may throw `ClassCircularityError`; this is not merely a recursive call bug between two custom loaders |
| **Same-thread** recursive static initialization | Inside X's `<clinit>`, a method triggers initialization of X | The JVM has reentrant initialization rules; you cannot automatically infer that a custom loader's `loadClass` created a cycle |
| **Cross-thread** loading/initialization deadlock | Thread T1 holds a lock and waits for B; T2 holds a lock and waits for A | Can cause mutual hanging; per-thread recursion detection via `ThreadLocal` cannot solve this on its own |

Two Java errors that are frequently confused:

- **`StackOverflowError`:** usually the result of an excessively deep recursive Java call chain. A faulty custom `loadClass` can cause this error, but it is not unique to ClassLoader.
- **`ClassCircularityError`:** belongs to the `LinkageError` family and reports an invalid cycle in a class/interface hierarchy when the JVM verifies definitions. There is **no guarantee** that the JVM will turn every `A.loadClass → B.loadClass → A.loadClass` loop into this error.

You should not handle cycles by using `catch (StackOverflowError)` and continuing to load: by that point, stack resources have already been overconsumed. **Preventing recursion before it happens** is the right approach.

## 3. A Standard Parent Chain Is Not an Arbitrary Lateral Graph

In a simple example:

```text
Bootstrap
    ^
Platform
    ^
Application
    ^
Plugin A
    ^
Plugin B
```

The arrows represent the direction of delegation toward the parent. A `ClassLoader` typically receives its parent at construction time via `super(parent)`; the standard public API does not provide a setter to arbitrarily change the parent later. With a parent chain constructed in the usual way, a new loader points to an already existing loader, so an application cannot easily create a cycle **solely through the parent relationship stored in the constructor**.

By contrast, cycles usually come from **custom policies outside the parent chain**, such as:

- A overrides `loadClass` and forwards certain namespaces to B; B in turn forwards those same namespaces to A.
- Plugin A uses the TCCL or a service registry to look up plugin B; a callback from B goes back to A and repeats the request to load the same class.
- A router holds a `package → delegate` map with conflicting configuration: A routes `shared.*` to B and B routes `shared.*` to A.
- A custom loader overrides `findClass(name)` but, instead of looking up local bytecode, calls `this.loadClass(name)` or loops through another service and returns with the same request.

**Note:** `getParent()` lets you inspect the parent chain, but it **does not expose** delegation edges created by custom code. A normal parent chain can still coexist with a cyclic callback/delegation graph.

## 4. The Default loadClass Flow and Where It Easily Breaks

In the default model, `ClassLoader.loadClass(String, boolean)` essentially:

1. Acquires the appropriate loading lock from `getClassLoadingLock(name)`.
2. Calls `findLoadedClass(name)` to avoid searching for or redefining a class already recorded by the JVM.
3. If not found, asks the parent or the corresponding bootstrap mechanism.
4. If the parent cannot find it, calls `findClass(name)` to locate its own bytecode.
5. Depending on the parameter, performs resolution and returns `Class<?>`.

```text
loadClass("plugin.Report")
   |
   +-- findLoadedClass("plugin.Report") --- found ---> return existing Class
   |
   +-- parent.loadClass("plugin.Report") -- found ---> return parent's Class
   |
   +-- findClass("plugin.Report") ------- read bytecode -> defineClass
```

Overriding **only `findClass`** to change the bytecode source is generally safer than overriding all of `loadClass`, because it preserves the already-loaded check, parent-first delegation, and locking mechanisms. If you want **selective child-first** loading, overriding `loadClass` may be necessary, but you must actively maintain these critical contracts.

An anti-pattern that easily causes recursion:

```java
@Override
protected Class<?> findClass(String name)
        throws ClassNotFoundException {
    return loadClass(name); // Wrong: loops back into the current loadClass flow.
}
```

This is **broken code for analysis**, not a usable implementation. If the parent cannot find the class, `loadClass` calls `findClass`; this `findClass` implementation then calls `loadClass` with the same name, which can lead to a loop:

```text
loadClass -> not found in parent -> findClass
              ^                         |
              |_________________________|
```

The right approach is for `findClass` to **locate bytecode from a local source and call `defineClass`**, or throw `ClassNotFoundException` if no valid source is found—never re-run the entire loading algorithm for that same name.

## 5. Detecting Same-Thread Recursion with (loader, binary name) Pairs

A typical guard tracks requests currently on the **active call path**. Each node is identified by:

```text
(defining/visited loader object identity, requested binary name)
```

More precisely, before the class is defined, the node is the **loader object currently handling the request** paired with the requested class name; it is not yet certain to become the defining loader. Use the loader's object identity rather than just a loader name string, because two distinct loaders can share the same display name or `toString()`.

The idea:

1. Before the router processes `(A, "plugin.Report")`, add this pair to a thread-local *in-progress* set.
2. When A delegates to B, add `(B, "plugin.Report")`.
3. If B returns to A with the **same name**, `(A, "plugin.Report")` is already present; this immediately signals a looping call path on that thread.
4. Throw an error explaining the cycle, or exit via a **pre-designed** fallback strategy; do not continue forwarding indefinitely.
5. In `finally`, remove the added pair. When the call path finishes, clear the `ThreadLocal` to avoid retaining loader references in a thread pool.

**Why include the binary name?** Processing class A may legitimately require loading a **different class B**; not every reappearance of the same loader on a call stack is an invalid cycle. Tracking at least `(loader, name)` avoids falsely blocking most valid dependencies. However, a cycle can span multiple class names before looping back; if it never repeats the exact same pair yet still forms an infinite graph under application rules, you need depth/path-length limits and an overall loading policy.

**Why not just use a global boolean?** Two different threads can legitimately load different classes concurrently; a shared flag would easily cause false blocks. For cross-thread deadlocks, you need **wait-for/lock graph analysis**—a shared boolean cannot serve as a substitute.

## 6. Runnable Java 17 Example: A → B → A, Then Switching to an Acyclic Path

The following program intentionally constructs a **faulty** delegation graph between two loaders to observe the recursion guard. It **does not define any new classes**, instead illustrating how to detect a looping call path in a custom routing policy. Thus, the result is independent of external JARs and requires no generated class files.

One design point to state upfront: the example overrides `loadClass(String)` **only for the `demo.*` test namespace** to observe the guard; other names still use the standard parent-first implementation. This is a cycle-detection experiment, **not** a production-ready multithreaded plugin loader. Production designs require the constraints covered in later sections.

Save the file as `DelegationCycleDemo.java`:

```java
import java.util.HashSet;
import java.util.Set;

public class DelegationCycleDemo {

    static final class RoutingLoader extends ClassLoader {
        private static final ThreadLocal<Set<Key>> ACTIVE =
                ThreadLocal.withInitial(HashSet::new);

        private record Key(RoutingLoader loader, String name) {}

        private final String id;
        private RoutingLoader next;

        RoutingLoader(String id) {
            super(ClassLoader.getPlatformClassLoader());
            this.id = id;
        }

        void routeTo(RoutingLoader other) {
            this.next = other;
        }

        @Override
        public Class<?> loadClass(String name)
                throws ClassNotFoundException {

            if (!name.startsWith("demo.")) {
                return super.loadClass(name);
            }

            Set<Key> active = ACTIVE.get();
            Key current = new Key(this, name);

            if (!active.add(current)) {
                throw new ClassNotFoundException(
                        "Delegation cycle at " + id + ": " + name);
            }

            try {
                if (next != null) {
                    return next.loadClass(name);
                }
                return super.loadClass(name);
            } finally {
                active.remove(current);
                if (active.isEmpty()) {
                    ACTIVE.remove();
                }
            }
        }
    }

    public static void main(String[] args) throws Exception {
        RoutingLoader a = new RoutingLoader("A");
        RoutingLoader b = new RoutingLoader("B");

        a.routeTo(b);
        b.routeTo(a); // Invalid graph: A -> B -> A.

        try {
            a.loadClass("demo.Missing");
        } catch (ClassNotFoundException exception) {
            System.out.println(exception.getMessage());
        }

        b.routeTo(null); // A -> B -> platform; no longer a cycle.

        try {
            a.loadClass("demo.Missing");
        } catch (ClassNotFoundException exception) {
            System.out.println("acyclic="
                    + exception.getClass().getSimpleName());
        }

        System.out.println("bootstrapString="
                + (a.loadClass("java.lang.String")
                        .getClassLoader() == null));
    }
}
```

Run with JDK 17 or later:

```bash
javac DelegationCycleDemo.java
java DelegationCycleDemo
```

Deterministic stdout in a standard Java 17 environment:

```text
Delegation cycle at A: demo.Missing
acyclic=ClassNotFoundException
bootstrapString=true
```

**Step-by-step walkthrough:**

1. `a.loadClass("demo.Missing")` adds the pair `(A, demo.Missing)` to the current thread's set.
2. A delegates to B, and B adds `(B, demo.Missing)`.
3. B delegates back to A; when A tries to add the existing pair, `Set.add` returns `false`. The example proactively throws `ClassNotFoundException` with the message `Delegation cycle at A: demo.Missing` **before the stack grows unboundedly**.
4. The `finally` blocks on B and A clean up the trace path; B is then reconfigured to terminate at its platform parent.
5. The second request goes A → B → parent; there is no cycle, but `demo.Missing` is genuinely absent, so it ends with a normal `ClassNotFoundException`. `acyclic=...` shows that **class not found** is distinct from **cycle detected**.
6. For `java.lang.String`, the experiment bypasses custom routing and uses `super.loadClass`. Core JDK classes are defined by the bootstrap loader, so the last line prints `true`.

The program uses `record` and `ThreadLocal` available in Java 17; the `Key` record compares both the loader object reference and the class name. `ClassLoader` does not override `equals` with a different logical identity, so loader comparison in the record uses object identity by default.

### Important Limitations of This Example

- The custom `loadClass(String)` in the experiment is a **simulated router** for `demo.*`; it does not fully handle already-loaded classes, resolution, namespace policies, and synchronization like a production loader.
- `next` is mutated sequentially on a single thread before each load. If routing paths are updated concurrently while multiple threads are loading, you need safe publication or, better yet, an **immutable configuration**.
- A single-thread `ACTIVE` guard does not detect wait cycles when two different threads already hold locks/resources on two loaders.
- When a class named `demo.*` exists in the parent yet the custom router forces delegation to a peer first, the behavior differs from parent-first and must be documented as a specific policy, not treated as the default behavior of `URLClassLoader`.
- Throwing `ClassNotFoundException` with a cycle message keeps the example easy to run; real applications may use a dedicated exception at the **configuration/router layer** to distinguish cyclic configuration from a genuinely missing class. You should not catch arbitrary `LinkageError` or `Throwable` instances and convert them into class-not-found.

## 7. Best Strategy: Prevent Cycles at Configuration Time

Runtime guards help diagnose issues and fail fast; a more durable solution is to **reject any delegation graph that contains a cycle**.

Example of a policy relationship:

```text
Host / Shared API loader
       ^
       |
Plugin API loader
    ^       ^
    |       |
Plugin A   Plugin B

Every plugin -> Shared API in a fixed direction.
Do not add edges Plugin A -> B and B -> A for the same namespace.
```

A delegation graph only has precise meaning **per namespace**. A can forward `shared.*` to the host and `pluginB.public.*` to B, provided you verify paths for each name set so that no cycle can form for the same request.

### Checking the Graph with DFS

An algorithm taking a directed graph of router edges:

1. Each node is a loader or a `(loader, namespace)` pair if routing depends on package/name.
2. Run DFS from each node.
3. Mark a node as **GRAY** while it is on the DFS stack, and **BLACK** once all of its outgoing edges have been explored.
4. If an edge leads to a GRAY node, a **back edge** is found and a cycle exists.
5. Reject the configuration or report the exact path, such as `A → B → C → A`.

```text
DFS(A):
  mark A = GRAY
  visit B:
    mark B = GRAY
    visit C:
      mark C = GRAY
      edge C -> A where A = GRAY   => CYCLE A -> B -> C -> A
```

**Complexity:** for an explicit graph with V nodes and E edges, DFS detects cycles in `O(V + E)` time and `O(V)` space, excluding the cost of representing namespace policies.

However, if routing decisions depend on **specific class names, timing, versions, or runtime state**, a static DAG of loaders may not capture the full actual call graph. In that case, combine **configuration validation** with a runtime guard on the execution path, simulation tests, and forwarding-hop limits.

### Designing One-Way Responsibilities

- Shared APIs/SPIs are defined by the host/parent; plugin loaders only delegate upward to them.
- Private implementations are resolved by the plugin loader from its local source (when the parent does not have them, or under a selective policy).
- Avoid callback loops like "if a class isn't found, ask another plugin, which asks the first plugin" without a *visited set*.
- Do not route every namespace through every plugin to "increase the chance of finding it"; that makes type identity and dependency failures unpredictable.
- Freeze the route map before serving requests; if updates are needed, use immutable snapshots or versioned routing.

## 8. Cross-Thread Cycles: ThreadLocal Is Not Enough

Suppose custom loaders hold their own locks while forwarding:

```text
Thread T1:
  holds lock(A, "plugin.X")
  calls B.loadClass("plugin.X")
                  \
                   \ waits for lock(B, "plugin.X")

Thread T2:
  holds lock(B, "plugin.X")
  calls A.loadClass("plugin.X")
                   \
                    \ waits for lock(A, "plugin.X")
```

Under an unfortunate interleaving, T1 waits for T2 and T2 waits for T1. Each thread has its **own `ThreadLocal`**, and neither thread has necessarily processed the same-named pair twice. Consequently, a guard like the one in the example cannot catch a **cross-thread deadlock**.

Never assume that the JVM will always detect and automatically break wait cycles created by arbitrary custom `ClassLoader` implementations. Ways to reduce the risk:

1. **Eliminate cyclic delegation graphs in the architecture.** This is the primary defense.
2. **Avoid holding long-lived locks while forwarding to another loader** if you can design source lookup and class definition to stay within a single loader's ownership. However, never recklessly remove class-loading locks and allow two threads to define the same class twice.
3. If multiple locks are involved, enforce a consistent lock-acquisition order and avoid callbacks back to an earlier loader.
4. Distinguish JVM/loader class-loading locks from application locks on caches, artifact repositories, class-loading callbacks, and service registries.
5. Test concurrent loading for both the same class name and multiple class names, using timeouts in tests to surface hangs; a timeout test is **not** proof that a runtime deadlock has been "fixed."
6. When a deadlock is suspected, capture a **thread dump** and correlate stacks, monitors, and locks waiting on each other; some wait cycles do not show up as standard monitor deadlocks and require inspecting loader context.

### Parallel-Capable ClassLoaders Do Not Fix Cycles

`ClassLoader.registerAsParallelCapable()` and `getClassLoadingLock(name)` support designing loaders that load classes in parallel per class name when API requirements are met. They do not turn an A→B→A graph into a DAG, nor do they replace proper class lookup/definition logic.

A loader that overrides `loadClass` must understand synchronization and the constraints around `findLoadedClass`, `defineClass`, and `resolveClass`; choosing the wrong lock can cause races or deadlocks even when a `ThreadLocal` check is in place.

## 9. Logging to Reconstruct Delegation Loops

A useful log should record the following fields:

| Field | Example | Purpose |
| --- | --- | --- |
| Request ID | `req-42` | Correlate the path of a single request |
| Binary name | `plugin.Report` | Class name being looked up |
| Loader identity | `A#1`, `B#2` | Distinguish two loaders that may share a display name |
| Delegate edge | `A → B` | Identify the forwarding policy |
| Thread | `worker-7` | Distinguish single-thread recursion from cross-thread waiting |
| Stage | `delegating / defined / not-found` | See where lookup is happening and what occurred |
| Duration/depth | `depth=3` | Spot abnormal chains early |
| Final defining loader | `HostLoader` or `PluginLoader` | Verify the type identity of the returned class |

Illustrative log example (not the stdout of the Java program in Section 6):

```text
req=42 thread=main class=plugin.Report loader=A action=delegate target=B
req=42 thread=main class=plugin.Report loader=B action=delegate target=A
req=42 thread=main class=plugin.Report loader=A action=cycle-detected
```

Do not log full bytecode, repository tokens, secret URLs, or sensitive file paths. In multi-plugin environments, use a stable loader ID **within the current process** and treat `System.identityHashCode(loader)` only as a supporting hint, not an absolute global identifier (hash codes can collide).

If a class is loaded successfully, use `clazz.getClassLoader()` to verify its **actual defining loader**; do not confuse it with the initial loader that received the request or the thread's TCCL.

### When the Application Hangs

On JVMs that support attach tools and with appropriate permissions:

```bash
jcmd <pid> Thread.print
```

This is a reference command; replace `<pid>` with the actual PID. Stacks can reveal an `A.loadClass → B.loadClass` path or threads waiting on related monitors/locks. Inspect multiple threads together rather than only the first thread that hit the problem.

You can also combine unified logging:

```bash
java -Xlog:class+load=info -cp app/classes com.acme.Main
```

The classpath and class names here are examples. Class-loading logs reflect JVM class-load events; they **do not replace** logs of custom delegation calls. If a cycle blows up before any class is successfully defined, searching only for "class loaded" logs may show no trace of the loop.

## 10. ClassCircularityError: When Is It Actually Relevant?

`ClassCircularityError` belongs to `LinkageError` and relates to a cycle in class/interface definition relationships detected by the JVM during loading/verification. An invalid relationship graph might look like:

```text
class A extends B
class B extends A
```

This is an **invalid relationship diagram**, not Java code meant to be compiled. Standard `javac` already rejects inheritance cycles in source code; malformed or improperly transformed bytecode can cause the JVM to hit this circularity constraint at load time.

Comparison:

- **Delegation cycle:** A-loader asks B-loader, and B-loader asks A-loader for a class name; at its core, this is a **custom loader call graph**. Without a guard, it can cause `StackOverflowError` or deadlock.
- **Class circularity:** class/interface definitions form a **forbidden inheritance/structural dependency cycle** under the JVMS; this can trigger `ClassCircularityError`.
- **Static initialization cycle:** circular references can occur in static initializers; the JVM has its own initialization rules, and a wait cycle between two threads is a separate issue.

Do not write:

```java
try {
    loader.loadClass(name);
} catch (ClassCircularityError error) {
    // Assumes every loader cycle has been handled.
}
```

This is **broken code for analysis**, assuming `loader` and `name` exist; it neither detects ordinary custom delegation cycles nor avoids swallowing an `Error` that indicates a genuine bytecode/class-graph failure.

## 11. Common Design Mistakes

| Flawed Design | Consequence | Fix |
| --- | --- | --- |
| Calling `this.loadClass(name)` from `findClass(name)` | Recursion when the parent lacks the class | Read local bytes and call `defineClass`, or throw `ClassNotFoundException` |
| A delegates all `plugin.*` to B and B delegates back to A | Policy cycle for the same namespace | Make the graph one-way, or return not-found when the local source lacks the class |
| Using only a global `isLoading` boolean | False positives across threads and class names | Track requests per thread and `(loader, binary name)` pair; still design for concurrency |
| Tracking only class name without loader | Can falsely block valid loads of the same name across multiple loaders | Use loader identity plus name; account for path context |
| Not cleaning `ThreadLocal` on exception | Retains loaders, leaks memory, causes false cycles later | Clean up in `finally` and call `ThreadLocal.remove()` when empty |
| Catching `StackOverflowError` to fall back | Stack is already exhausted; state is unreliable | Detect before recursing using a graph/visited guard |
| Mutating route map while multiple threads load | A single request sees inconsistent configuration | Use immutable snapshots or synchronized publication |
| Custom `loadClass` skips `findLoadedClass`/locking | Duplicate `defineClass`, `LinkageError`, races | Keep the default when possible or implement the full API contract |
| Allowing unbounded "ask all plugins" | Unpredictable types, dependency cycles, high cost | Assign namespace ownership to loaders and bound depth/budget |
| Checking only thread-local state and declaring deadlocks solved | Misses cross-thread wait cycles | Eliminate cyclic edges, run concurrency tests, monitor locks |
| Confusing `ClassCircularityError` with delegation cycles | Misdiagnoses the root cause | Inspect stacks, class hierarchy, and custom loader paths |

## 12. Testing Delegation Policies

A minimal test suite for a loader/router should cover:

1. **Valid path:** a class name from a local source is defined properly, and shared API classes are returned by the parent.
2. **Non-existent class:** without a cycle, `ClassNotFoundException` is thrown in finite time without infinite looping.
3. **2-node cycle:** A→B→A must be rejected during configuration validation or caught early by the runtime guard.
4. **3-node cycle:** A→B→C→A must produce a similar outcome, with logs clearly identifying the edges and class name.
5. **No false blocks:** A→B to load `util.Helper` while A is processing `plugin.Service` can be a valid dependency if it does not loop back to the same pair or violate configuration.
6. **Mid-flight errors:** whether `ClassNotFoundException`, `IOException`, or a runtime exception is thrown, per-thread state must be cleaned up; subsequent loads must not mistakenly appear still in progress.
7. **Concurrency:** two threads loading the same class name and multiple different class names must neither duplicate definitions nor deadlock; use timeouts and capture thread dumps on test failure.
8. **Loader lifecycle:** after a plugin is unloaded, the registry/router, TCCL, and `ThreadLocal` must not unintentionally hold strong references to the old loader.
9. **Parent/bootstrap:** core platform classes must not be redefined, host APIs/SPIs must be shared properly, and type identity must remain intact.
10. **Class initialization:** static initializers must not call back into the plugin router in a cross-waiting manner not permitted by the design.

### Distinguishing Fail-Fast from Fallback

When a cycle is detected, some frameworks want to skip the looping branch and try **another source**. This is only safe if:

- The alternative lookup path is explicitly specified in the policy;
- It does not silently pick another version with the same binary name but a different API/ABI, causing unpredictable runtime types;
- Both the cycle event and the final chosen source are logged;
- Serious bytecode/linkage errors are not swallowed to pretend it was merely "class not found."

In many systems, **rejecting cyclic configurations at startup** is simpler and easier to debug than dynamic fallback.

## 13. Self-Check Exercises

**Q1.** If A calls B to find `plugin.Item` and B calls A to find the same name, is the JVM required to throw `ClassCircularityError`?

**Answer:** No. That is a custom delegation call cycle, which can lead to recursion/stack overflow or deadlock; `ClassCircularityError` relates to circularity in class/interface structure as defined by the JVM.

**Q2.** Why can tracking only `binaryName` in a `ThreadLocal Set<String>` cause false blocks?

**Answer:** Two different loaders can legitimately traverse the same binary name during delegation; you need to track the pair of loader object identity + name, and evaluate the request path.

**Q3.** Why does the example clean up `ACTIVE` in `finally` rather than right after `next.loadClass`?

**Answer:** Because downstream calls can throw exceptions. `finally` ensures in-progress state is cleared even when the class is not found or an error occurs.

**Q4.** If two threads T1 and T2 wait on each other's locks across two custom loaders, can a `ThreadLocal` guard solve it?

**Answer:** No. The two threads have separate paths; you need an acyclic graph design, lock ordering, and concurrency tests.

**Q5.** For a loader that only needs to change where bytecode is read from, which method should you prefer to override?

**Answer:** `findClass(String)`, so that the default `loadClass` continues to handle parent delegation, already-loaded classes, and locking.

**Q6.** A `findClass` implementation does not find local bytecode. Should it call `this.loadClass(name)` to "retry"?

**Answer:** Not for the same name when `findClass` was already called by `loadClass` after the parent failed; that can cause recursion. Throw `ClassNotFoundException` or follow a separate fallback designed to avoid cycles.

**Q7.** What should you inspect when `jcmd Thread.print` shows two threads stuck in two custom loaders?

**Answer:** The locks each thread holds, where it is waiting, the class names, delegation edges, callbacks, static initialization, and whether a request was forwarded back to an earlier loader via another thread.

**Q8.** Why isn't switching every package to child-first to "avoid calling the parent" a general-purpose solution?

**Answer:** It can cause loaders to define their own separate copies of APIs/SPIs and trigger type-identity conflicts. You need clear namespace design and controlled delegation directions.

## 14. Design and Operations Checklist

- [ ] Know which loader **owns** each namespace and which loaders only delegate.
- [ ] Model both the standard parent chain and **custom forwarding edges**, not just `getParent()`.
- [ ] Have DAG validation or one-way routing rules before serving requests.
- [ ] For dynamic routers, use a visited guard keyed by `(loader identity, binary name)` and ensure cleanup in `finally`.
- [ ] Do not treat a same-thread guard as a complete solution for cross-thread deadlocks.
- [ ] Do not override `loadClass` when overriding `findClass` suffices.
- [ ] Do not call `loadClass(name)` back from `findClass(name)` for the same name.
- [ ] Preserve loading locks, `findLoadedClass`, and proper `defineClass` policy if you must override.
- [ ] Do not use `catch (StackOverflowError)` as a cycle-detection mechanism.
- [ ] Log delegation paths with loader identity, class name, and thread/request ID without leaking sensitive information.
- [ ] Test 2/3-node cycles, valid paths, missing classes, and multi-thread contention.
- [ ] Have a cleanup strategy for loaders, `ThreadLocal`, and routing registries upon unload/redeploy.

## 15. Conclusion and References

To avoid infinite recursion when customizing `ClassLoader`, the primary solution is to **design a one-way or acyclic delegation graph** per namespace. When policies are complex enough to risk runtime cycles, use a guard keyed by **(loader object identity, binary name)** on the call path and clean up state in `finally` to fail fast. However, this guard mainly detects **same-thread recursion**; cross-thread wait cycles still require graph and lock control.

Continue distinguishing delegation cycles from `ClassCircularityError` and initialization cycles, keep `loadClass`/`findClass`/`findLoadedClass` rules compliant, and never treat class-not-found as a license to arbitrarily load a same-named class from another source.

Official documentation:

- Java SE 17 `ClassLoader` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 `ThreadLocal` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html
- Java SE 17 `ClassCircularityError`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassCircularityError.html
- JVMS 17 §5.3, *Creation of Classes and Interfaces*: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- JLS 17 §12.4.2, *Detailed Initialization Procedure*: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2
