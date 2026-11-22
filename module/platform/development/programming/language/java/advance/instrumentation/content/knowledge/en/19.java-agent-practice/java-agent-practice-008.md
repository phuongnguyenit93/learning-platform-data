# Redefining a Method Body While an Old Invocation Is Still Running

> **Context:** Java Advance → Instrumentation → **Agent Lab**. This article verifies an important JVM behavior: when `Instrumentation.redefineClasses(...)` installs a **new method body**, an invocation that already has an **active stack frame** continues executing the **bytecode of the old version**, whereas **new invocations after redefinition** use the new bytecode. We use a Java agent started with `-javaagent`, two independent class versions with the same structure, `CountDownLatch` to lock down exact timing, and then read the `OLD`/`NEW` results. The code is compiled at Java 17 level and executed on OpenJDK 24, including with the `-Xint` interpreter.

## 1. The Experiment Question

Suppose a thread has entered:

~~~java
public static String work(CountDownLatch entered, CountDownLatch release) {
    entered.countDown();
    release.await(); // Simplified syntax: the full version has try/catch.
    return "OLD";
}
~~~

Immediately after the thread signals `entered` but **before** it passes `release.await()`, the agent installs a new version of the **same class** with the method:

~~~java
public static String work(CountDownLatch entered, CountDownLatch release) {
    entered.countDown();
    release.await(); // Simplified syntax: the full version has try/catch.
    return "NEW";
}
~~~

**Which prediction is correct?**

- **A:** All invocations, including the invocation waiting at `await()`, immediately return `NEW`.
- **B:** The active invocation continues executing the old method and returns `OLD`; an invocation started after redefinition uses the new method and returns `NEW`.
- **C:** The JVM must wait for all old invocations to finish before returning from `redefineClasses`.
- **D:** By default, the JVM stops the thread and re-runs the method from the beginning.

**According to the specification, the answer is B.** JVM TI `RedefineClasses` states that the new method version applies to **new invokes**, while already-active frames continue running the original bytecodes. `Instrumentation.redefineClasses` describes the same semantics. This is neither a "race intuition" nor a Java-compiler-specific rule; it is the documented behavior of the redefinition mechanism.

The core point: a **new class definition** and an **old active invocation** can coexist in the same JVM for a period of time. They do not create two `Class<?>` objects for the application to choose between, but rather different **method versions** for already-started invocations versus new invocations.

## 2. Visualizing the Timeline: Active Stack Frame and Method Version

We use two threads:

- **Thread T1:** has called `VersionedTarget.work(...)` V1. It reaches `release.await()` and has not returned yet.
- **Thread T0 (main):** waits for T1 to signal `entered`, calls the agent's `redefineClasses` with V2 bytes, then makes a new call to `work(...)`, and finally lets T1 continue.

~~~text
Time          Thread T1: old invocation         Thread T0: main/agent
─────────     ──────────────────────────        ───────────────────────────
t0            enter work() V1                   create entered/release latches
t1            entered.countDown()               entered.await() succeeds
t2            release.await()  [WAITING]        agent prepares V2 class-file bytes
t3            V1 frame still active             redefineClasses(target, V2)
t4            V1 frame still active             redefineDone (V2 installed)
t5            V1 frame still active             call new work() -> "NEW"
t6            V1 frame still active             release.countDown()
t7            resume V1 body -> "OLD"           join(T1)
t8            old invocation finishes           print oldResult="OLD"
~~~

At `t3–t5`, the JVM does not need to "swap the instruction pointer" of the V1 frame to a corresponding position in V2. In practice, mapping an old program counter to new bytecode can be completely undefined: the new method body may have different branches, instruction counts, or layout. The JVM lets the old frame finish according to the **method version it started with**.

### An `active frame` is not a full state snapshot

An active frame holds the execution state of the invocation such as the program counter, local variables, and operand stack; it does not copy the entire heap or static fields. Therefore:

- **Bytecode:** the V1 frame continues executing V1 bytecode.
- **Shared data:** if the V1 method reads a field after redefinition, it can still observe normal data changes from other threads according to the Java Memory Model.
- **Class identity:** the same `Class<?>` and type system of the class being redefined; no class with a new name is created by default.
- **JIT:** the JVM may need to handle/deoptimize compiled code when swapping method versions. Do not infer semantics from whether a frame is interpreted or compiled; the old/new method versions rule must still be respected.
- **Side effects:** any I/O, mutation, or external request that already occurred before redefining **is not rolled back**.

Thus, "the old invocation runs the old version" means **the bytecodes of the active method**, not that the entire environment and data become an old snapshot.

## 3. What Is Redefinition, and How Does It Differ from Loading a New Class?

In Java Instrumentation:

~~~java
instrumentation.redefineClasses(
    new ClassDefinition(targetClass, replacementClassFileBytes)
);
~~~

`targetClass` is an already-loaded `Class<?>`. `replacementClassFileBytes` is **the entire bytes of the new `.class` file** with the **same binary name** and a valid structure within redefinition limits. Do not pass a `.java` source filename, a JAR path, or an array containing only the method's bytecode.

API:

- **`redefineClasses`:** takes the replacement class bytes directly, for example after building version V2. It does not need to rely on reading original bytes inside a transformer.
- **`retransformClasses`:** asks the JVM to re-run the transformer pipeline on an already-loaded class, suitable for instrumentation that modifies based on class bytes. It also has corresponding rules regarding **old active frames** and **new invokes**, but the mechanism for supplying bytes is different.
- **`ClassFileTransformer.transform`:** a callback that receives class bytes when defining/redefining/retransforming a class, **not** a callback on every method invocation.

An important entry in the manifest:

~~~text
Can-Redefine-Classes: true
~~~

And at runtime:

~~~java
boolean supported = instrumentation.isRedefineClassesSupported();
boolean modifiable = instrumentation.isModifiableClass(targetClass);
~~~

If `supported=false` or `modifiable=false`, do not run the experiment along this path. Redefinition is an **optional capability**, and `Can-Redefine-Classes` must be declared in the agent manifest. Do not use `Can-Retransform-Classes` as a substitute for the `redefineClasses` capability.

### Class schema restrictions

In Java 17+ per JVM TI, during standard redefinition, you cannot arbitrarily:

- Add, remove, or rename fields/methods.
- Change method signatures/descriptors, access modifiers, staticness, or superclass/interfaces.
- Change class-file attributes related to `NestHost`, `NestMembers`, `Record`, and `PermittedSubclasses` structures.
- Supply invalid bytes, a class file version too new for the JVM, or a class name different from the target.

You can **replace the method body** and other contents permitted by the JVM, such as the string constant returned in this lab. The two versions V1/V2 below have **the same package, class name, one field, constructor, and method signatures**; only the literal returned in `work` and the static initializer value are changed to prove the initializer does not re-run.

## 4. Designing the Lab to Avoid Races and Random Output

A weak experiment often writes:

~~~java
new Thread(() -> oldCall()).start();
Thread.sleep(100);
redefine();
~~~

This approach **does not confirm the thread has entered `oldCall`** before redefining. On a busy machine, the thread might be scheduled late; the result accidentally comes out `NEW` and the learner draws the wrong conclusion.

We use **two `CountDownLatch` instances**:

1. `entered = new CountDownLatch(1)`: thread T1 calls `entered.countDown()` **after entering method V1**.
2. `release = new CountDownLatch(1)`: thread T1 waits inside method V1, so the frame has not returned.
3. Main calls `entered.await(timeout)`, so it knows T1 has entered the method and hit the `entered` gate.
4. Main redefines the class, calls the new method with non-blocking latches, and then lets T1 continue via `release.countDown()`.
5. Main calls `join(timeout)`, confirming T1 has finished before reading `AtomicReference<String> oldResult`.

There is no need to rely on sleep, CPU timing, network latency, or a debugger UI. `CountDownLatch` and `Thread.join` also establish synchronization/happens-before relationships specified by the Java API, allowing safe reading of results in the test program.

**Do not use `Thread.stop()`, manual suspend, or `PopFrame`** to set up the test condition; we want to observe normal JVM redefinition, not force a stack frame change via debugging controls.

## 5. Project Structure and Keeping V2 Out of the Runtime Classpath

A Java class with the same binary name appears in **two source folders** for separate compilation:

~~~text
redefine-live-frame-lab/
├── manifest.mf
├── src/
│   ├── v1/
│   │   └── demo/target/VersionedTarget.java
│   ├── v2/
│   │   └── demo/target/VersionedTarget.java
│   ├── agent/
│   │   └── demo/agent/RedefineAgent.java
│   └── app/
│       └── demo/app/Main.java
└── out/                              # generated on build
    ├── v1/demo/target/VersionedTarget.class
    ├── v2/demo/target/VersionedTarget.class
    ├── agent/demo/agent/RedefineAgent.class
    ├── app/demo/app/Main.class
    └── redefine-agent.jar
~~~

During a run:

- **Only `out/v1`** is on the application classpath and is loaded first by the JVM.
- **`out/v2` is not on the classpath**; the agent reads the V2 file **using `Files.readAllBytes(Path)`** and then uses `ClassDefinition` to request redefining the already-loaded class.
- Agent classes reside in the agent JAR activated via `-javaagent`; the application can call the agent's public static method in this experiment because Java instrumentation adds the agent JAR to the system class loader's search mechanism. In production, business applications should generally **not** depend directly on agent classes as in this educational design.
- The V1 and V2 sources are **not compiled in the same `javac` invocation** due to the duplicate binary name.

If `out/v2` is accidentally placed on the runtime classpath before `out/v1`, the JVM may define V2 from the start, defeating the experiment. Keep the classpath in the run command exact.

## 6. Java 17+ Source: V1 and V2

### 6.1 V1 — the old invocation will return OLD

File `src/v1/demo/target/VersionedTarget.java`:

~~~java
package demo.target;

import java.util.concurrent.CountDownLatch;

public final class VersionedTarget {
    public static int marker = 41;

    private VersionedTarget() {}

    public static String work(CountDownLatch entered, CountDownLatch release) {
        entered.countDown();

        try {
            release.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return "INTERRUPTED";
        }

        return "OLD";
    }
}
~~~

Method V1:

1. Counts down `entered` so main knows the frame is active.
2. Waits on `release`; the `work` frame remains on T1's stack while execution is inside `CountDownLatch.await`.
3. If released normally, returns the string `OLD`.
4. If the thread is interrupted, restores the interrupt flag and returns `INTERRUPTED` so it does not masquerade as a normal V1 result.

The `marker` field is initialized to 41 by V1's class initialization. Because it is a `static int` **rather than a compile-time constant `static final`**, reading the field in the app is an actual field access rather than having the compiler inline the literal value from source.

### 6.2 V2 — an invocation started after redefine will return NEW

File `src/v2/demo/target/VersionedTarget.java`:

~~~java
package demo.target;

import java.util.concurrent.CountDownLatch;

public final class VersionedTarget {
    public static int marker = 99;

    private VersionedTarget() {}

    public static String work(CountDownLatch entered, CountDownLatch release) {
        entered.countDown();

        try {
            release.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return "INTERRUPTED";
        }

        return "NEW";
    }
}
~~~

Comparing V1/V2:

| Element | V1 | V2 | Does it change the class schema? |
|---|---|---|---|
| Binary name | `demo.target.VersionedTarget` | Identical | No |
| Class modifiers | `public final` | Identical | No |
| Constructor | `private VersionedTarget()` | Identical | No |
| Field | `public static int marker` | Identical | No |
| Method | `public static String work(CountDownLatch, CountDownLatch)` | Identical | No |
| Method body result | `"OLD"` | `"NEW"` | **Bytecode/constant change**, valid |
| Static initializer assigned value | 41 | 99 | Initializer body differs, but **does not re-run** on redefine |

**Important:** `marker = 99` is in V2's class initialization bytecode, but redefining **does not re-run the class initializer `<clinit>`**. The JVM preserves the already-established static value (41). We include this difference so learners do not confuse "installing a new class file" with "loading a new class from scratch."

No fields or methods are added in V2: replacing the method body is the focus, not attempting to break structure.

## 7. Java Agent Using `ClassDefinition`

File `src/agent/demo/agent/RedefineAgent.java`:

~~~java
package demo.agent;

import java.lang.instrument.ClassDefinition;
import java.lang.instrument.Instrumentation;
import java.lang.instrument.UnmodifiableClassException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.io.IOException;

public final class RedefineAgent {
    private static Instrumentation inst;

    private RedefineAgent() {}

    public static void premain(String args, Instrumentation instrumentation) {
        inst = instrumentation;
        System.out.println("[AGENT] redefineSupported="
                + inst.isRedefineClassesSupported());
    }

    public static void replace(Class<?> target, Path classFile)
            throws IOException, ClassNotFoundException, UnmodifiableClassException {
        if (inst == null || !inst.isRedefineClassesSupported()) {
            throw new IllegalStateException("Class redefinition not supported");
        }
        if (!inst.isModifiableClass(target)) {
            throw new IllegalStateException("Class not modifiable");
        }

        byte[] bytes = Files.readAllBytes(classFile);
        inst.redefineClasses(new ClassDefinition(target, bytes));

        System.out.println("[AGENT] redefineDone");
    }
}
~~~

This is the complete agent class, using the standard **`java.lang.instrument`** API:

- `premain(String, Instrumentation)` is invoked by the JVM when started with `-javaagent`.
- `isRedefineClassesSupported()` checks the capability. Requesting `Can-Redefine-Classes: true` in the manifest is **necessary but not sufficient** if the JVM does not support it.
- `isModifiableClass(target)` is a pre-check; `true` **does not guarantee** that any arbitrary replacement bytes are valid.
- `Files.readAllBytes(classFile)` reads **the exact pre-compiled V2 `VersionedTarget.class` file**, without loading V2 via a class loader.
- `new ClassDefinition(target, bytes)` pairs the existing `Class<?>` with the replacement bytes.
- `inst.redefineClasses(...)` is where the JVM **checks, verifies, and installs the new definition** (potentially passing through the JVM's transformer chain if other agents registered matching transformers).
- Only after the API **returns normally** does the code print `redefineDone`. If an exception occurs, it must not print a false success.

**No `ClassFileTransformer` registration is needed** for this demo approach using replacement class-file bytes directly. In a multi-agent system, registered transformers can affect the final class bytes; test with the actual agents in the same JVM.

**Regarding `inst` state:** the static field is set in `premain` before `main` runs in this lab, so the app can call `replace`. In production with dynamic Attach, multiple class loaders, or startup races, lifecycle/visibility must be designed more carefully; do not copy this static global into an unsynchronized public API without evaluation.

## 8. Application Holding a Running V1 Frame

File `src/app/demo/app/Main.java`:

~~~java
package demo.app;

import demo.agent.RedefineAgent;
import demo.target.VersionedTarget;
import java.nio.file.Path;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public final class Main {
    public static void main(String[] args) throws Exception {
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicReference<String> oldResult = new AtomicReference<>("UNSET");

        Thread active = new Thread(
                () -> oldResult.set(VersionedTarget.work(entered, release)),
                "active-v1");
        active.start();

        try {
            if (!entered.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Old method did not enter");
            }
            System.out.println("[APP] oldActive=true");
            System.out.println("[APP] markerBefore=" + VersionedTarget.marker);

            RedefineAgent.replace(
                    VersionedTarget.class,
                    Path.of("out", "v2", "demo", "target", "VersionedTarget.class"));

            String fresh = VersionedTarget.work(
                    new CountDownLatch(1), new CountDownLatch(0));
            System.out.println("[APP] freshResult=" + fresh);
            System.out.println("[APP] markerAfter=" + VersionedTarget.marker);
        } finally {
            release.countDown();
        }

        active.join(10000);
        if (active.isAlive()) {
            throw new IllegalStateException("Active call did not finish");
        }
        System.out.println("[APP] oldResult=" + oldResult.get());
    }
}
~~~

Step-by-step analysis:

1. `active.start()` creates T1. T1 starts method V1, counts down `entered`, and waits on `release`.
2. `entered.await(10, TimeUnit.SECONDS)` on T0 ensures T1 has passed the entry point **before redefinition**. If it times out, the program throws an error instead of continuing measurements under a false assumption.
3. `markerBefore=41` confirms V1 has undergone class initialization.
4. The agent redefines the target with V2 bytes.
5. T0 calls `VersionedTarget.work(new CountDownLatch(1), new CountDownLatch(0))`. The release latch at **0** does not block, so the invocation starts after redefine and returns `NEW` immediately.
6. `markerAfter=41` confirms the V2 class initializer **did not** re-run; the existing static value remains 41.
7. `finally { release.countDown(); }` releases thread T1 even if the redefine operation or printing throws an exception. This is important cleanup so the lab does not leave a hanging thread.
8. `active.join(10000)` waits for T1 to finish, then reads `oldResult`. The expected result is `OLD` because T1's frame is still running V1 bytecode.
9. `AtomicReference` ensures safe storing/reading of the result across threads. Although `join` also has a happens-before edge under the JMM, this form makes the intent to share the result explicit.

In an abnormal environment where T1 is interrupted, `work` returns `INTERRUPTED`. This is a **different** outcome from old/new semantics and must be investigated if it appears; do not conclude that redefinition "switched the frame" just because a thread was interrupted.

## 9. Manifest, Compile, and Run

### 9.1 `manifest.mf`

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.RedefineAgent
Can-Redefine-Classes: true

~~~

The manifest has a newline and a trailing blank line after the attributes. Some common mistakes:

- Misspelling the binary class name `demo.agent.RedefineAgent`.
- Missing `Can-Redefine-Classes: true` or mistakenly using `Can-Retransform-Classes: true`.
- Placing the manifest outside the JAR without passing it via `jar --manifest`.
- Packaging without `RedefineAgent.class`.
- Passing the replacement path to the V1 file or placing V2 on the runtime classpath.

### 9.2 Building on macOS/Linux (Bash)

Run from the root directory `redefine-live-frame-lab`:

~~~bash
mkdir -p out/v1 out/v2 out/agent out/app

javac --release 17 -d out/v1 src/v1/demo/target/VersionedTarget.java
javac --release 17 -d out/v2 src/v2/demo/target/VersionedTarget.java
javac --release 17 -d out/agent src/agent/demo/agent/RedefineAgent.java
javac --release 17 -cp out/v1:out/agent -d out/app src/app/demo/app/Main.java

jar --create --file out/redefine-agent.jar --manifest manifest.mf -C out/agent .

java -javaagent:out/redefine-agent.jar -cp out/app:out/v1 demo.app.Main
~~~

The `:` characters in the classpath are separators on macOS/Linux. At **compile time**, the app needs to know `RedefineAgent` and `VersionedTarget`, hence `-cp out/v1:out/agent`. At **runtime**, the agent JAR is passed via `-javaagent`; the app only uses `out/app:out/v1`, and agent classes are found by the system loader from the agent JAR per the instrumentation contract.

### 9.3 Building on Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force -Path out/v1, out/v2, out/agent, out/app | Out-Null

javac --release 17 -d out/v1 src/v1/demo/target/VersionedTarget.java
javac --release 17 -d out/v2 src/v2/demo/target/VersionedTarget.java
javac --release 17 -d out/agent src/agent/demo/agent/RedefineAgent.java
javac --release 17 -cp "out/v1;out/agent" -d out/app src/app/demo/app/Main.java

jar --create --file out/redefine-agent.jar --manifest manifest.mf -C out/agent .

java "-javaagent:out/redefine-agent.jar" -cp "out/app;out/v1" demo.app.Main
~~~

On Windows the classpath uses `;`, while `-javaagent:...` is a **separate JVM option**. The runtime command **intentionally omits `out/v2`**. Even though the V2 class file exists on disk, the JVM does not automatically define another class with the same binary name to replace V1; the agent only uses V2 bytes as a replacement.

### 9.4 Experimental Stdout

Compiled with `javac --release 17`, run on OpenJDK 24.0.2 (a Java 24 release):

~~~text
[AGENT] redefineSupported=true
[APP] oldActive=true
[APP] markerBefore=41
[AGENT] redefineDone
[APP] freshResult=NEW
[APP] markerAfter=41
[APP] oldResult=OLD
~~~

**Explanation in log order:**

| Milestone | Printed by | What it proves |
|---|---|---|
| `redefineSupported=true` | Agent `premain` | The test JVM provides the requested redefinition capability |
| `oldActive=true` | Main after latch | T1 invocation has entered V1 and is waiting for release, not yet returned |
| `markerBefore=41` | Main | Class was initialized according to V1 |
| `redefineDone` | Agent after API call | JVM accepted V2 bytes and installed the new definition |
| `freshResult=NEW` | Main after new call | **New invocation** uses the V2 method body |
| `markerAfter=41` | Main | Static field value is preserved; V2 class initializer did not re-run |
| `oldResult=OLD` | Main after release/join | **Active V1 invocation** finishes using the old bytecode |

Another machine/VM might not support redefinition; when `redefineSupported=false`, the test stops with an exception from the guard in the agent rather than claiming the feature exists. Only report PASS when the JVM reports the capability and all stdout matches the above.

### 9.5 Verifying V1/V2 Have the Same API Schema

After compiling:

~~~bash
javap -public out/v1/demo/target/VersionedTarget.class
javap -public out/v2/demo/target/VersionedTarget.class
~~~

Both produce the same representative public API:

~~~text
public final class demo.target.VersionedTarget {
  public static int marker;
  public static java.lang.String work(
      java.util.concurrent.CountDownLatch,
      java.util.concurrent.CountDownLatch);
}
~~~

**Note:** the example above is **wrapped across lines for readability**; `javap` normally prints the method signature on a single line. The private constructor is not shown with `-public`. To see more:

~~~bash
javap -p out/v1/demo/target/VersionedTarget.class
javap -p out/v2/demo/target/VersionedTarget.class
~~~

To inspect the specific bytecode:

~~~bash
javap -c -p out/v1/demo/target/VersionedTarget.class
javap -c -p out/v2/demo/target/VersionedTarget.class
~~~

Look for the paths returning the `OLD` literal in V1, `NEW` in V2, and the value in `<clinit>`. Do not compare raw class-file bytes, see a difference, and draw the wrong conclusion: method bodies, constant pools, and initializer bodies **are allowed to differ** within redefinition limits; what matters is valid schema/method semantics.

## 10. Additional Tests: `-Xint` and Multiple Iterations

### 10.1 Running in interpreted mode

If you want to distinguish this from JIT optimization, run:

**Bash:**

~~~bash
java -Xint -javaagent:out/redefine-agent.jar -cp out/app:out/v1 demo.app.Main
~~~

**PowerShell:**

~~~powershell
java -Xint "-javaagent:out/redefine-agent.jar" -cp "out/app;out/v1" demo.app.Main
~~~

In testing on OpenJDK 24, stdout is **identical** to section 9.4, including `freshResult=NEW` and `oldResult=OLD`. This matches the specification, rather than being an accidental JIT cache of the old method.

### 10.2 Repeating to rule out a random race

Re-run the default command several times and ensure both lines:

~~~text
[APP] freshResult=NEW
[APP] oldResult=OLD
~~~

still appear. The lab was verified with three default runs and one `-Xint` run; all four produced the expected results.

**Note:** repeated runs do not replace specification proof, but they are useful QA for catching setup mistakes such as accidentally putting V2 on the classpath or missing a latch. The primary proof still comes from the **JVM TI and Instrumentation contract**.

## 11. Why Doesn't the JVM Automatically "Replace the Frame"?

An active frame contains:

- A reference to the method version that the thread entered.
- Local variables and the operand stack of that invocation.
- A program counter corresponding to the instruction position of the frame's current method version.

If a new body is compiled from freely modified code, a position "equivalent" to the current instruction may not exist. An old frame might be in the middle of a `try/finally`, a monitor, a native call, or a sequence of side effects. Jumping into the middle of V2 could violate semantics or execute side effects incorrectly.

Therefore, JVM TI describes that **old method versions can become obsolete** when redefinition installs a new method version. An already-active frame **keeps running the old code**, while new invocations enter the new version.

### "Obsolete method" does not mean the thread is killed

In JVMTI, an old method version can be marked obsolete. That does not automatically:

- Terminate the thread, throw an exception, or alter `Thread.State`.
- Migrate local variables into a new frame.
- Re-run the method from the beginning.
- Re-invoke constructors/static initializers.
- Undo database transactions or outgoing HTTP requests already executed.

**Debuggers have special tools** such as JVMTI `PopFrame` to pop a frame under supported conditions and then re-execute logic under debugger control. This is a **different** mechanism from `Instrumentation.redefineClasses`, has its own constraints, and can affect side effects. Do not use `PopFrame` as an automatic "fix" for hot production traffic.

### Case where a V1 frame calls another method after redefinition

Suppose the V1 frame continues running and makes **a new invocation** to a method that was just redefined. That new invocation can use the **new version** of the called method, even though the **caller frame** is still executing V1 bytecode. Therefore, within a single running transaction, you can observe **mixed-version behavior** (old code in the caller, new code in the callee).

Do not infer from "an active frame keeps the old method body" that **the entire call tree** is frozen at V1. The JVM does not provide a transaction-level code-version snapshot for a request. If synchronized changes across multiple service methods are required, you must design backward-compatible behavior or a quiescence/drain strategy.

## 12. Redefine Does Not Reset Object or Static State

According to `Instrumentation.redefineClasses`:

- Redefine **does not create a new `Class` object** for the target in the way loading a binary name in a new class loader does.
- **It does not re-initialize the class** and does not re-run initializers.
- Static field values **are preserved**; existing object instances are not "re-created."
- Class schema changes are constrained so that existing objects/stack frames remain valid.

In the example, V2 writes `marker = 99`, yet after redefine `markerAfter=41`. This distinction is crucial when hotfixing a bug in initialization code:

~~~java
// V1
public static int marker = 41;

// V2
public static int marker = 99;
~~~

Merely changing the bytecode of `<clinit>` **does not** fix the value 41 already sitting in the static field. If the business logic truly needs state migration, you must design a separate migration operation, synchronize it safely, account for data currently in use, and not expect redefine to do it automatically.

Similarly, an instance holding field values does not automatically become a new object after redefine. When calling **a new method** on an old instance after redefine, the method can use the new bytecode while still reading the **old field values** of the instance.

**Data note:** the lab uses a simple static field and does not demonstrate migration mechanisms or atomic updates of multiple fields. A production agent must consider the Java Memory Model, happens-before, and data concurrency if a hotfix changes the meaning of fields.

## 13. Limitations and Failure Paths of `redefineClasses`

| Symptom | Common Cause | How to Handle |
|---|---|---|
| `isRedefineClassesSupported() == false` | Manifest missing `Can-Redefine-Classes: true` or JVM does not support it | Stop/report capability; do not call redefine |
| `isModifiableClass(target) == false` | Class belongs to a group the JVM does not allow modifying | Do not attempt to replace; use a fallback |
| `UnmodifiableClassException` | API rejects a non-modifiable class | Check the exact `Class<?>` and VM support |
| `UnsupportedOperationException` | JVM does not support redefinition or bytes change forbidden schema/attributes | Compare field/method descriptors/modifiers, hierarchy, nest/record/sealed attributes |
| `ClassFormatError`/`VerifyError` | Replacement bytes are not a valid class or verification fails | Build properly, inspect class-file/stack maps with javap/tests |
| `NoClassDefFoundError` | Binary name in replacement bytes does not match target or linkage differs | Read the exact V2 class file name |
| `UnsupportedClassVersionError` | V2 file requires a newer JDK than the running JVM | Compile with matching `--release` and check dependency versions |
| `IOException` when reading replacement | Path `out/v2/...` does not exist, file permissions, or wrong CWD | Run from project root, verify file |
| `IllegalStateException` from lab guard | `inst` not ready or capability/target not satisfied | Check `premain`, manifest, `isModifiableClass` |
| `oldActive=false` or timeout | T1 did not hit latch within allowed time | Check thread start/deadlock, do not skip precondition |
| `oldResult=INTERRUPTED` | T1 was interrupted while waiting on `release` | Investigate interrupting actor and test setup |
| `oldResult=NEW` | V2 may have been loaded from the start or test did not actually hold V1 frame | Check classpath, latch, output order, V1 source |
| `freshResult=OLD` | JVM has not installed V2 or read wrong replacement file | Check `redefineDone`, V2 bytes/path, transformers |
| `markerAfter=99` | May have run V2 from the start or mutated static state separately | Check classpath and before/after logs; do not assume initializer re-ran without checking |

**Atomicity:** `redefineClasses` accepts multiple `ClassDefinition`s in one call. Per Javadoc, if the method throws an exception, **none of the classes** in the set are redefined. Do not write a rollout procedure assuming "some classes may have changed" in a failed batch API call. However, side effects of previously executed code or redefinitions in **other API calls** are not rolled back.

**Thread safety:** Do not treat redefinition as a transaction that synchronizes application state. It replaces **code called after the installation point**, without waiting for all threads to finish operations. You must ensure V1/V2 compatibility during the period they both have active frames.

**JIT/safepoints:** The JVM may need internal work to install method versions. Do not interpret the lab's result as claiming `redefineClasses` never pauses threads or has no overhead. It only proves the API can complete **while an old frame is still active** and that frame, when resumed, will use the old bytecode.

## 14. Comparison with Retransformation and Debugger Hot Swap

| Criterion | `redefineClasses` | `retransformClasses` | Debugger hot swap |
|---|---|---|---|
| Input | Replacement class-file bytes via `ClassDefinition` | `Class<?>` instances needing transformer chain re-run | Debugger/VM wire protocol & capabilities |
| Capability | `Can-Redefine-Classes`, `isRedefineClassesSupported()` | `Can-Retransform-Classes`, `isRetransformClassesSupported()` | JDWP/JVM TI capabilities of target VM |
| Class schema limits | Cannot freely add/change fields/methods, inheritance, etc. | Similar for supported changes | VM-dependent, usually follows redefinition limits |
| Active frames | Continue old code | Continue old code | VM-dependent; debugger may show obsolete frames |
| New invocations | Use new body | Use body after transformer pipeline | Use new body after hot swap |
| Re-runs `<clinit>`? | No | No | Not under normal redefinition |
| Suitable use case | Installing new class bytes from build/hotfix lab | Instrumenting/reinstrumenting already-loaded classes | Debug fix-and-continue in a safe environment |

**Do not use `redefineClasses` as a "more powerful upgrade that removes all restrictions" compared to retransform.** The two APIs have different workflows but must obey the same class schema restrictions in Java 17+/JVM TI. And even when redefinition succeeds, old active frames still continue with the old version.

## 15. Production Scenario: Mixed-Version Windows and Limited Hotfixes

A service may run requests lasting several seconds. At the moment an agent redefines a method to fix a bug:

- Request A has already entered the old method: it can **continue the old code** until it returns.
- Request B starts the method after redefine: it runs **the new code**.
- Request A may subsequently call **another method via a new invocation** and receive the new version of that method.
- Both requests can see/write the same fields, databases, caches, and queues. **They are not automatically isolated by version.**

Therefore, redefinition is a **code replacement mechanism**, not an automatic safe deployment plan, transaction migration, or rollback strategy.

If the business requires all requests to be consistent on a single version:

1. You may need to **drain/quiesce** incoming new requests and wait for in-flight tasks to complete within SLA before switching versions.
2. Or design V1/V2 to be **backward-compatible** at boundaries and shared state, tolerating a period of mixed-version frames.
3. Distinguish **code** rollouts from **schema/database/config** rollouts. Replacing a method body does not change data fields or automatically run migrations.
4. Document testing boundaries: exact redefined method, target classloader/module, JVM version, and method stack frames that may still be active.
5. Have an alternative rollback/disable path (e.g., restarting the process with a tested build) if the JVM does not support it or bytes are invalid; do not rely on hot swap to solve every problem.
6. With third-party agents, remember the transformer chain can interact and alter final bytes; test in a production-like environment.

### Example of changing the return value without undoing an already-occurred error

If the old method already sent an email or deducted money before stopping at the latch, changing the return string to `NEW` does not undo the email or transaction. A hotfix cannot make past side effects "never happen." The lab intentionally only returns a string so there are no external side effects.

### Class loader identity

If an application has two class loaders both defining `demo.target.VersionedTarget`, they are two different `Class<?>` objects. `redefineClasses(new ClassDefinition(targetA,bytes))` only applies to **the provided `targetA` class**, and does not automatically modify `targetB` in another loader just because it shares the binary name. When locating the target, log/verify the exact defining loader rather than blindly selecting a class by string name.

## 16. Extension Exercises After the Main Lab Passes

**Exercise 1 — Change release order:** Call `release.countDown()` **before** redefining. Then thread T1 may finish with V1 before redefinition. This test **no longer** proves the "active frame at redefine time" behavior because the precondition is broken; observe the timing and do not draw the same conclusion.

**Exercise 2 — Multiple concurrent invocations:** Create two or more T1 threads, each with an `entered` latch and all waiting on one `release` latch. After both have signaled `entered`, redefine, make a new invocation, then release. Expect the old active frames to continue V1. Use `CountDownLatch(count=N)` and verify all N threads entered the method before redefining.

**Exercise 3 — Change logic in the method body:** Have V2 change `return "NEW"` to another calculation/branch, while keeping the exact same method descriptor and schema. Compare active V1 and new V2 invocations.

**Exercise 4 — Try adding a field in V2 (negative test):** Add `public int extra;` to V2 and compile. Per JVM TI restrictions for Java 17+, normal `redefineClasses` must reject adding fields. Do not run this case on a real service; if testing in the lab, handle `UnsupportedOperationException`/the corresponding JVM error. **Do not** treat a single rejection as proof that the capability is never supported: the error may be due to schema.

**Exercise 5 — Observe the initializer:** Change `marker = 99` in V2 to `1000`, recompile, and run. `markerAfter` must still reflect the value 41 initialized from V1 in the lab program.

**Exercise 6 — Use `-Xint`:** Run the same test with the interpreter and compare stdout. If a hypothesis only holds in JIT mode and not in the interpreter, check for race/optimization/testing assumptions before concluding anything about the JVM spec.

**Exercise 7 — Switch to `retransformClasses`:** Write a `ClassFileTransformer` with `canRetransform=true` that replaces the method body on retransform, enable the right manifest capability, and distinguish "reading replacement bytes" from "transform pipeline." Compare old/new frame semantics with the lab. This is a separate exercise; do not silently swap `redefineClasses` for retransform in the original lab.

## 17. Common Mistakes

| Mistake | Why It Is Wrong | How to Fix |
|---|---|---|
| "After `redefineDone`, all frames must run V2 immediately" | Active frames continue original method bytecodes | Distinguish active frame vs. new invoke |
| "The JVM must wait for old calls to finish before redefine returns" | The API can install the new method while old frames are still active | Use a latch to prove it, do not rely on timing |
| "`Thread.sleep` is enough to synchronize threads" | The scheduler does not guarantee method entry before redefine | Use a `CountDownLatch` handshake |
| "After redefine, `marker=99` because V2 code initializes it so" | Class initializer does not re-run | Verify persisted static field |
| "V2 must have a different class name" | `ClassDefinition` requires replacement for **the same target** | Keep binary name and schema, change only the body |
| "Keeping V2 on the runtime classpath is required" | The agent reads V2 bytes; the loader does not need to define V2 | Keep only `out/v1` on the runtime classpath |
| "Putting both V1/V2 on the classpath is fine" | V2 might be loaded from the start, breaking the precondition | Separate output paths clearly |
| "`isModifiableClass == true` allows adding methods" | Modifiability is distinct from schema restrictions | Keep field/method schema |
| "`Can-Retransform-Classes` replaces `Can-Redefine-Classes`" | Two different capabilities | Use the right manifest and API |
| "If an old invocation sees a new field value, it is using V2 bytecode" | Old bytecode can still read shared mutable fields | Separate code version and data state |
| "Redefine automatically rolls back old request side effects" | Does not undo DB/IO/heap mutations | Design separate migration/rollback |
| "No need to watch for errors because redefine only changes a string" | Can have wrong path, wrong class name, corrupt bytes, unsupported JVM | Preflight, catch/report errors, read output |
| "Debugger `PopFrame` is default behavior" | `PopFrame` is a separate debugger/JVMTI operation | Do not combine when testing redefinition |
| "An agent replaces the same FQCN across all plugin loaders" | Class identity includes the defining loader | Target the exact `Class<?>` in each loader |
| "A transformer callback proves the method was called" | Transformer callbacks occur on classfile events | Use execution output/latches and method body |

## 18. Self-Check Questions

1. **If a V1 frame is waiting on a latch and the agent redefines to V2, what does the V1 frame return when released?** According to the lab: `OLD`, because it continues the original bytecodes.
2. **What does an invocation started after a successful redefine return?** `NEW` if it calls the exact method of the redefined class and is not altered by another transformer.
3. **Why must we use the `entered` latch?** To confirm the thread has entered the old method before installing V2.
4. **Why is the `release` latch needed?** To keep the V1 frame active throughout redefinition.
5. **Can `CountDownLatch` be replaced with `Thread.sleep(50)` to guarantee correctness?** No; sleep does not prove the frame is active.
6. **Does `redefineClasses` take Java source or class file bytes?** Full class-file bytes, paired with the target `Class<?>` via `ClassDefinition`.
7. **Why does V2 not appear on the runtime classpath?** The agent reads V2 bytes from a file rather than loading V2 as a separate class.
8. **Which manifest entries are needed for the API?** `Premain-Class` and `Can-Redefine-Classes: true` for a startup agent.
9. **Does `isRedefineClassesSupported == true` allow adding a field to V2?** No; schema restrictions still apply.
10. **Is `markerAfter=41` abnormal when V2 declares `marker=99`?** No; the static initializer does not re-run.
11. **Can an old frame call another new method after redefine?** Yes; the new invocation uses the new method version per the specification.
12. **Does an old frame revert the heap to V1 state?** No; heap/static state is shared under normal rules.
13. **Is the JIT allowed to break the rule that old frames run old code?** No; the JVM must preserve observable semantics, even if it deoptimizes/recompiles internally.
14. **What happens if the class name is changed in V2?** `redefineClasses` must reject a class file that does not match the target, potentially with `NoClassDefFoundError`.
15. **If `redefineClasses` throws an exception for a batch of multiple classes, are some classes installed?** Per Javadoc: no class in the batch is redefined.
16. **Can debugger `PopFrame` be used to force re-execution of code?** That is a separate feature with conditions; it is not the default behavior of Instrumentation.
17. **How do you test with multiple old threads?** Synchronize to confirm all have entered V1 before redefining.
18. **Should hot redefinition be used to replace production rollouts/restarts?** Not by default; you must consider mixed-version execution, state, side effects, and rollback.

## 19. Checklist Before Calling `redefineClasses` in Practice

- [ ] The problem genuinely requires installing new code into an already-loaded class, not merely observing or logging.
- [ ] Target `Class<?>` belongs to the right defining loader/module; not just a matching binary name.
- [ ] Agent has manifest `Can-Redefine-Classes: true` and `isRedefineClassesSupported() == true`.
- [ ] `isModifiableClass(target)` returns `true`; still check classfile/schema restrictions.
- [ ] Replacement bytes are **a complete class file**, with the right target name/version, not source code.
- [ ] V1/V2 share field/method signatures, modifiers, superclass/interfaces, and restricted class attributes.
- [ ] Other agents/transformers are accounted for when testing final class bytes.
- [ ] Preconditions and synchronization exist to verify the active calls being observed.
- [ ] Output/metrics exist to distinguish old in-flight invocations from new invocations.
- [ ] No expectation that static initializers or constructors re-run or that object data resets.
- [ ] If changing the meaning of shared fields, separate data migration and concurrency compatibility are designed.
- [ ] No JNI/IO/DB side effects are performed under the assumption that redefinition rolls them back.
- [ ] Error paths exist for `UnmodifiableClassException`, `UnsupportedOperationException`, classfile/linkage errors, and missing files.
- [ ] Verified on the JDK/vendor the application will run on; not just the compile JDK.
- [ ] Ability to stop/deploy a controlled rollback and handle active requests exists.
- [ ] Debugger frame operations are not used when measuring default redefinition semantics.

## 20. Official References

- [Java SE 21 — `Instrumentation.redefineClasses`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#redefineClasses(java.lang.instrument.ClassDefinition...)): rule that **active stack frames run original bytecodes**, new invokes use redefined methods, static values do not reset, class initializers do not re-run, batch failure atomicity, and exceptions.
- [Java SE 17 — `Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): API/capabilities active on Java 17+.
- [Java SE 21 — `ClassDefinition`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassDefinition.html): class paired with replacement class-file bytes.
- [Java SE 21 — `java.lang.instrument` package specification](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): `Premain-Class`, `Can-Redefine-Classes`, agent startup.
- [JVM TI 21 — Redefine Classes](https://docs.oracle.com/en/java/javase/21/docs/specs/jvmti.html#RedefineClasses): obsolete method versions, old active frames, new invokes, schema restrictions.
- [JVM TI 21 — Retransform Classes](https://docs.oracle.com/en/java/javase/21/docs/specs/jvmti.html#RetransformClasses): corresponding mechanism and active frame semantics of retransformation.
- [Java SE 21 — `CountDownLatch`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CountDownLatch.html): entry/release synchronization, memory consistency effects.
- [Java SE 21 — `Thread.join`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html#join()): waiting for a thread to finish.
- [Java SE 21 — JVMS §5.3 Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3): runtime class identity and defining loader.
