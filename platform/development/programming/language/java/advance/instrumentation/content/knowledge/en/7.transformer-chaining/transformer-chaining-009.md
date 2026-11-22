# `removeTransformer` and the Possibility of In-Flight Callbacks Continuing

> **Context:** Java Advance → Instrumentation → **Transformer Chaining**. This content focuses on the `Instrumentation.removeTransformer(ClassFileTransformer)` contract, concurrent class loading scenarios, and how to stop a transformer without breaking an executing callback. The Java 17+ example uses a startup agent without any bytecode library dependencies.

## 1. `removeTransformer` unregisters; it does not cancel an invocation that has already started

An agent registers a transformer via `Instrumentation.addTransformer(...)`:

~~~java
instrumentation.addTransformer(transformer);
boolean removed = instrumentation.removeTransformer(transformer);
~~~

According to the Java SE API, `removeTransformer(transformer)`:

- **Removes one registration** of the supplied transformer object from the list managed by the JVM.
- Returns `true` when found and removed, `false` when not found. If `null` is passed, it throws `NullPointerException`.
- If **the same object** is registered multiple times, it removes the **most recently** added matching registration; the other registrations can still continue receiving callbacks. The Javadoc recommends avoiding duplicate registrations.
- Once removed, new class definition requests no longer pass through that registration. **However**, because class loading can occur on multiple threads, a transformer **may continue to receive callbacks after being removed**, or a callback that has already started may continue running.

Crucially: **`removed == true` only confirms that the registration was successfully removed; it does not confirm that threads have exited `transform(...)`.** There is no guarantee that `removeTransformer` will block, interrupt, cancel, or wait for all prior invocations.

### One view of the race

~~~text
Thread L (defines class)            Thread M (manages agent)
───────────────────────────         ────────────────────────
JVM starts defining class A
 └─ selects transformer T
    └─ T.transform(A) starts
       └─ processing...             removeTransformer(T) returns true
       └─ still processing...
       └─ T.transform(A) finishes
JVM finishes defining class A

Later, starts defining class B
 └─ T no longer has a registration
    (if there are no duplicate registrations or lingering races)
~~~

This is **one valid execution schedule**, not an ordering every JVM is required to follow. In another schedule, the JVM may have already decided to invoke T before unregistration, while the executing thread has not yet entered the Java body of `transform`. When that thread resumes, the callback **may even start after remove has returned**. That is why the Javadoc requires transformers to be written defensively against late callbacks.

Once a callback already holds references to agent resources, unregistering does not automatically clear those references. Closing shared queues, files, loggers, or connections immediately when `removeTransformer == true` can cause errors in a callback that is still running.

## 2. What can and cannot be concluded

| Scenario | Valid conclusion | False inference to avoid |
|---|---|---|
| `removeTransformer(t) == true` | Removed **one** registration of `t` | All callbacks of `t` have stopped |
| `removeTransformer(t) == false` | No matching registration found at the time of the call | `t` was definitely never registered |
| Callback logs still appear after remove | There is an active, late, or another registration's invocation | The JVM definitely ignored the remove request |
| Loading a new class after remove produces no callback | The removed registration did not handle the new load in that run | The bytecode of all old classes has been restored |
| Same object `t` registered twice, then removed once | One registration of `t` may still remain | Removing once deletes all registrations |
| Transformer A removed, but transformer B remains in the chain | B can still process new classes | `removeTransformer` clears the entire chain |

Distinguish between the **registration lifecycle** (currently registered vs. removed) and the **callback lifecycle** (not yet started, running, finished). `removeTransformer` only provides an API for the first part.

## 3. Contract when multiple transformers exist

Two overloads:

~~~java
instrumentation.addTransformer(t);        // equivalent to addTransformer(t, false)
instrumentation.addTransformer(t, false);
instrumentation.addTransformer(t, true); // if the JVM and agent support retransform
~~~

A transformer added with `canRetransform=false` can still run on class load/redefinition; it is not called again during retransformation, though its previous result may be reused by the JVM when appropriate. A transformer with `canRetransform=true` can receive callbacks on retransform, if the JVM supports it and the agent manifest declares the corresponding capability. **Both kinds are removed with the same `removeTransformer(t)`**.

When there are multiple transformers, the JVM orders processing by non-retransform-capable vs. retransform-capable groups (including native transformers), and by registration order within each group. Steps are linked into a chain: the byte array returned by one transformer can serve as input to the next transformer. Removing one registration does not cancel the remaining transformers, nor does it roll back bytes already installed into classes.

### Duplicate registration of the same instance

The following snippet is **illustrative code only**, assuming `instrumentation` and `t` already come from an external agent:

~~~java
instrumentation.addTransformer(t);
instrumentation.addTransformer(t); // should not do this

boolean first = instrumentation.removeTransformer(t);  // true
boolean second = instrumentation.removeTransformer(t); // true
boolean third = instrumentation.removeTransformer(t);  // false
~~~

The `first` call only removes the most recent registration. Without calling `second`, new callbacks can still happen even though the first remove call returned `true`. To manage the lifecycle properly, store **the exact same object reference** passed to `addTransformer`, and avoid creating a new object and calling `removeTransformer(new MyTransformer())`. If there are multiple transformers, each object must have clear ownership.

## 4. Java 17+ example: an in-flight callback still completes after remove

Goal: **control the ordering between the callback and unregistration** without relying on arbitrary `sleep` calls.

The design consists of:

1. A startup agent registers a logging-only transformer; the transformer always `return null`, meaning it **does not modify bytecode**.
2. The application has a worker thread load `FirstTarget`. Inside `transform`, the agent signals that it has entered the callback via `CountDownLatch ENTERED` and then waits on `RELEASE`.
3. The main thread awaits `ENTERED`, calls `removeTransformer`, and then opens `RELEASE`. The old callback can continue and print its completion line.
4. After the worker thread finishes loading, main loads `SecondTarget`. The new class is still defined, but the removed transformer no longer logs for this class.

### 4.1 Directory structure

~~~text
remove-transformer-lab/
├── manifest.mf
├── src/
│   └── lab/
│       ├── agent/
│       │   └── GateAgent.java
│       ├── app/
│       │   └── RemoveDemo.java
│       └── targets/
│           ├── FirstTarget.java
│           └── SecondTarget.java
└── out/                         # created when building
    ├── agent/
    ├── app/
    └── gate-agent.jar
~~~

Use JDK 17+ with `java`, `javac`, and `jar`. Run the commands from the `remove-transformer-lab` root directory; no Spring/Gradle/Maven is required.

### 4.2 Agent: `src/lab/agent/GateAgent.java`

~~~java
package lab.agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public final class GateAgent {
    private static final CountDownLatch ENTERED = new CountDownLatch(1);
    private static final CountDownLatch RELEASE = new CountDownLatch(1);
    private static final ClassFileTransformer PROBE = new GateProbe();
    private static Instrumentation instrumentation;

    private GateAgent() {}

    public static void premain(String options, Instrumentation inst) {
        instrumentation = inst;
        inst.addTransformer(PROBE);
        System.out.println("[AGENT] registered");
    }

    public static void awaitFirstCallback() throws InterruptedException {
        if (!ENTERED.await(10, TimeUnit.SECONDS)) {
            throw new IllegalStateException("FirstTarget callback not observed");
        }
    }

    public static boolean remove() {
        return instrumentation.removeTransformer(PROBE);
    }

    public static void releaseFirstCallback() {
        RELEASE.countDown();
    }

    private static final class GateProbe implements ClassFileTransformer {
        @Override
        public byte[] transform(Module module, ClassLoader loader, String className,
                Class<?> classBeingRedefined, ProtectionDomain protectionDomain,
                byte[] classfileBuffer) {

            if ("lab/targets/FirstTarget".equals(className)) {
                System.out.println("[CALLBACK] FirstTarget begin");
                ENTERED.countDown();

                try {
                    if (!RELEASE.await(15, TimeUnit.SECONDS)) {
                        System.out.println("[CALLBACK] safety timeout");
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }

                System.out.println("[CALLBACK] FirstTarget end");
            } else if ("lab/targets/SecondTarget".equals(className)) {
                System.out.println("[CALLBACK] SecondTarget observed");
            }
            return null;
        }
    }
}
~~~

Explanation:

- `premain` registers **the exact `PROBE` object** before the application starts; retransform is not used, so `Can-Retransform-Classes` is not needed in the manifest.
- In `transform`, comparing with `"literal".equals(className)` avoids an NPE if `className` is unknown. The JVM uses internal names with `/`, such as `lab/targets/FirstTarget`.
- When the first class is defined, the callback prints `begin`, signals `ENTERED`, and waits on `RELEASE`. While waiting, the callback **remains on the call stack**.
- The `SecondTarget observed` marker is dedicated to detecting whether a callback occurs for the second class.
- `return null` ensures this transformer does not alter bytecode. Blocking a callback with a latch is strictly for **the experiment**, not for production transformers.
- There is a 15-second timeout to avoid hanging forever if a runtime implements unregistration differently from the illustrated schedule. On timeout, `safety timeout` is also printed and the output may differ.

### 4.3 Two target classes

`src/lab/targets/FirstTarget.java`:

~~~java
package lab.targets;

public final class FirstTarget {
    static {
        System.out.println("[TARGET] FirstTarget initialized");
    }
}
~~~

`src/lab/targets/SecondTarget.java`:

~~~java
package lab.targets;

public final class SecondTarget {
    static {
        System.out.println("[TARGET] SecondTarget initialized");
    }
}
~~~

The `[TARGET] ... initialized` marker comes from **class initialization**, whereas `[CALLBACK]` comes from the JVM invoking the transformer during class definition processing. Do not confuse a static initializer running with a transformer callback.

### 4.4 Application: `src/lab/app/RemoveDemo.java`

~~~java
package lab.app;

import lab.agent.GateAgent;
import java.util.concurrent.atomic.AtomicReference;

public final class RemoveDemo {
    public static void main(String[] args) throws Exception {
        AtomicReference<Throwable> loadFailure = new AtomicReference<>();

        Thread loadingThread = new Thread(() -> {
            try {
                Class.forName("lab.targets.FirstTarget");
            } catch (Throwable failure) {
                loadFailure.set(failure);
            }
        }, "load-first-target");

        loadingThread.start();
        GateAgent.awaitFirstCallback();

        try {
            System.out.println("[APP] remove=" + GateAgent.remove());
        } finally {
            GateAgent.releaseFirstCallback();
        }

        loadingThread.join();
        if (loadFailure.get() != null) {
            throw new IllegalStateException("FirstTarget load failed", loadFailure.get());
        }

        Class.forName("lab.targets.SecondTarget");
        System.out.println("[APP] remove again=" + GateAgent.remove());
    }
}
~~~

Here the main thread only calls `remove()` **after** the callback has signaled `ENTERED`. Releasing in `finally` allows the callback to continue even if `remove` fails. `loadingThread.join()` ensures the second class is not loaded until the first class finishes; `AtomicReference<Throwable>` propagates any failure from the worker thread back to main, avoiding a false success result.

### 4.5 Manifest

`manifest.mf` (with a trailing blank line):

~~~text
Manifest-Version: 1.0
Premain-Class: lab.agent.GateAgent

~~~

Because `-javaagent` is used at startup, the entry point is `premain`; `Agent-Class` and the Attach API are not needed. If the class name in the manifest does not match the package, the JVM may abort before entering `main`.

### 4.6 Compile and run

**macOS/Linux (Bash):**

~~~bash
mkdir -p out/agent out/app
javac --release 17 -d out/agent src/lab/agent/GateAgent.java
javac --release 17 -cp out/agent -d out/app src/lab/targets/FirstTarget.java src/lab/targets/SecondTarget.java src/lab/app/RemoveDemo.java
jar --create --file out/gate-agent.jar --manifest manifest.mf -C out/agent .
java -javaagent:out/gate-agent.jar -cp out/agent:out/app lab.app.RemoveDemo
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force -Path out/agent, out/app | Out-Null
javac --release 17 -d out/agent src/lab/agent/GateAgent.java
javac --release 17 -cp out/agent -d out/app src/lab/targets/FirstTarget.java src/lab/targets/SecondTarget.java src/lab/app/RemoveDemo.java
jar --create --file out/gate-agent.jar --manifest manifest.mf -C out/agent .
java "-javaagent:out/gate-agent.jar" -cp "out/agent;out/app" lab.app.RemoveDemo
~~~

The classpath separator is `:` on macOS/Linux and `;` on Windows. The app puts `out/agent` on the classpath to call `GateAgent` methods directly; on the standard system classloader, the startup agent and app share the same `GateAgent` class identity, the same `PROBE` instance, and the same latches.

You can verify the JAR:

~~~bash
jar --list --file out/gate-agent.jar
~~~

You should see `META-INF/MANIFEST.MF`, `lab/agent/GateAgent.class`, and `lab/agent/GateAgent$GateProbe.class`. Place `-javaagent` **before** the main class name on the command line.

### 4.7 Expected stdout

With HotSpot/OpenJDK, in a typical schedule where remove completes while the callback is waiting on the latch:

~~~text
[AGENT] registered
[CALLBACK] FirstTarget begin
[APP] remove=true
[CALLBACK] FirstTarget end
[TARGET] FirstTarget initialized
[TARGET] SecondTarget initialized
[APP] remove again=false
~~~

Interpretation:

1. `registered`: a transformer is registered.
2. `FirstTarget begin`: the JVM has entered the callback. The `ENTERED` latch ensures the main thread observes this point before calling remove.
3. `remove=true`: the registration was removed while the callback had not yet been released.
4. `FirstTarget end` appears **after `remove=true`**: the in-flight `transform` invocation is not automatically canceled.
5. `FirstTarget initialized`: the class continues to be defined and initialized after the callback returns `null`.
6. `SecondTarget initialized` without a `SecondTarget observed` line: the new load after unregistration does not pass through the removed transformer.
7. `remove again=false`: no registration of this instance remains.

This is the **expected output of the example**, not a promise that the JVM will always schedule it this way. If the callback times out or is interrupted, the log may differ; if remove waits for the callback to finish on a particular JVM, the timeout prevents an indefinite hang. What the specification guarantees is that you **must not treat remove as a barrier confirming that all callbacks have finished**.

### 4.8 Two variants for comparison

**Skip the first remove:** replace the first `GateAgent.remove()` expression with a `remove=skipped` message, while still releasing the latch. When defining the second class, the transformer is still registered and prints `[CALLBACK] SecondTarget observed`. The final remove call returns `true`.

**Remove before loading FirstTarget:** call `GateAgent.remove()` at the start of main and **omit `awaitFirstCallback()`**, because no first callback will signal the latch. When loading both classes, the `[TARGET]` markers still appear, but no `[CALLBACK]` markers do. These two variants are for learning only; do not compare against the stdout in section 4.7 after modifying the code.

## 5. How can a transformer be shut down more safely?

One pattern is to use an `AtomicBoolean` so late callbacks check the state and return `null`:

~~~java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;
import java.util.concurrent.atomic.AtomicBoolean;

final class ManagedTransformer implements ClassFileTransformer {
    private final AtomicBoolean enabled = new AtomicBoolean(true);

    @Override
    public byte[] transform(Module module, ClassLoader loader, String className,
            Class<?> classBeingRedefined, ProtectionDomain pd, byte[] bytes) {
        if (!enabled.get()) {
            return null;
        }

        // stop() may run concurrently here.
        // Only operate on safely managed state/resources.
        return null;
    }

    void stop(Instrumentation inst) {
        enabled.set(false);
        inst.removeTransformer(this);
    }
}
~~~

This is an **illustrative class**, without an entry point to run standalone. `AtomicBoolean` publishes the stopped state with Java Memory Model visibility, but **does not cancel a callback that has already passed the `enabled.get()` check**. After a callback reads `true`, `stop` can occur and the callback still continues.

If shutdown must guarantee that no callbacks are still using resources, the agent must have its own coordination protocol between **entry**, **exit**, and **cleanup**. Merely checking `AtomicInteger inFlight == 0` once after remove can still miss a **late** callback from an earlier JVM decision. The design needs to control admission and exact in-flight state, or keep lightweight resources alive until the JVM exits.

In particular, avoid:

- Holding locks for a long time or performing blocking I/O in `transform`: callbacks run on the sensitive class-loading path; a circular dependency can cause a deadlock.
- Calling `Class.forName(...)` on the very class currently being processed by the transformer: this can cause recursive loading or linkage errors.
- Closing a logger, queue, or executor that an old callback may still access solely because `removeTransformer == true`.
- Throwing arbitrary exceptions to cancel transformation: the `ClassFileTransformer` specification still allows other transformers and the class-loading process to continue when one transformer throws an exception.

## 6. Unregistering does not automatically undo prior transformations

Suppose T altered the bytecode of class A when A was defined:

~~~text
original class A bytes
    |
    v
T.transform(A) returns new byte[]
    |
    v
JVM defines A from the instrumented result
    |
    +-- removeTransformer(T) -> true
    |
    v
A remains the defined class; bytes are not automatically restored
~~~

`removeTransformer` is not an `undo instrumentation` API. If you want to change an existing class, you need to examine `retransformClasses(...)` or `redefineClasses(...)`, JVM/manifest support capabilities, class modification limits, and the current pipeline. **Do not claim that retransforming after remove always returns the original bytes**, because the outcome depends on other transformers, input bytes, transformation history, and the runtime.

One detail to remember: a transformer registered with `canRetransform=false` is not invoked again via a Java callback on a retransform pass, but the JVM may reapply its old output according to the pipeline contract. Therefore, **seeing no callback log** does not mean a class has been restored.

## 7. Common pitfalls

| Symptom | Possible cause | How to check |
|---|---|---|
| `removeTransformer(t) == true` but callbacks are still seen | Callback already started or was selected before unregistration | Test with a latch; design callbacks to tolerate late calls |
| Remove succeeds, yet new classes still trigger the same transformer | Duplicate registration exists, or callback was queued beforehand | Audit all `addTransformer` calls; check identity and timing |
| `removeTransformer(new T()) == false` | Removing the wrong object instance | Store the original reference from registration |
| Second remove returns `false` | The previous call already removed the sole registration | Treat as normal cleanup state |
| Callback fails after shutdown | Agent resources were closed too early | Separate unregistration from drain/cleanup |
| Race test produces inconsistent results | Relies on `sleep`/scheduling | Use latch + timeout + join |
| Old classes still carry instrumented behavior | No automatic rollback | Distinguish unregister from retransform/redefine |
| No callback seen on `retransformClasses` | Transformer lacks `canRetransform=true` or is no longer registered | Check capabilities and transformer list |
| JVM slows down/hangs when testing blocking callbacks | Class-loading thread is blocked | Use controlled blocking only in labs; avoid in production |

## 8. Self-check questions

1. **Does `removeTransformer(t)` returning `true` mean all callbacks of `t` have finished?** No. It only indicates that one registration was removed.
2. **Can a callback start after remove has returned?** Yes, per the specification, due to concurrent class loading.
3. **If one instance is registered twice, does removing once remove both?** No; it removes the most recently registered matching entry.
4. **Is calling remove a second time and getting `false` a JVM bug?** No; when no registration remains, that is the normal result.
5. **What is the benefit of replacing `Thread.sleep` with a latch?** A latch confirms the callback has been entered, establishing event ordering instead of guessing by timing.
6. **Does `AtomicBoolean enabled=false` stop an in-progress callback immediately?** No; the invocation may have already passed the checkpoint.
7. **Does removing a transformer revert already-instrumented classes?** No; unregistering is not a rollback.
8. **What does returning `null` from `transform(...)` mean?** This transformer did not modify the bytes during that pass.
9. **Is the same remove method used for both `canRetransform=true` and `false` transformers?** Yes, both are managed with `removeTransformer`.
10. **When is it safe to close shared resources?** When the agent's shutdown protocol guarantees safety for all in-flight and late callbacks, not merely because remove returned `true`.

## 9. Production readiness checklist

- [ ] Keep the exact transformer instance reference and avoid duplicate registrations.
- [ ] Distinguish **registered**, **unregistered**, **in-flight**, and **drained** states.
- [ ] Ensure late callbacks can run safely or return `null` when no longer accepting new work.
- [ ] Do not treat `removeTransformer == true` as `join()` or cancellation.
- [ ] Do not close shared resources while callbacks may still be unfinished.
- [ ] Avoid blocking, heavy locking, loading extra classes, or complex I/O in production transformers.
- [ ] Do not confuse unregistering with bytecode rollback.
- [ ] Test in-flight callbacks, class loads after removal, and repeated cleanup.

## Official References

- [Java SE 21 — Instrumentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `addTransformer`, `removeTransformer`, return values, most-recent removal, concurrent callbacks, and `retransformClasses`.
- [Java SE 17 — Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): corresponding contract on Java 17.
- [Java SE 21 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): callback rules, chaining, returning `null`, `classfileBuffer` input, and retransform.
- [Java SE 21 — CountDownLatch](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CountDownLatch.html): thread synchronization in the experiment.