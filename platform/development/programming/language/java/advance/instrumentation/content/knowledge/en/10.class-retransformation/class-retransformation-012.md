# Retransforming Multiple Classes as a Set: Atomic Success or No Class Installed on Request Failure

In Java Instrumentation, **Instrumentation.retransformClasses(Class<?>... classes)** does not only accept a single class. The API allows passing **a set of multiple classes in the same call** so the JVM can process changes that have dependency relationships—for example, when an agent needs to instrument both **Service** and **Repository** with the same logic version. The most important point of the Java 17 contract is:

> **If the retransformClasses call throws an exception, no class in the requested set has been retransformed by that call.**

Therefore, the two operations **retransformClasses(A.class, B.class)** in *one call* and **retransformClasses(A.class)** followed by **retransformClasses(B.class)** in *two calls* have different failure semantics. With one call, the JVM provides an **all-or-none guarantee for installing the class definitions of the set**. With two separate calls, A may have already been updated successfully and then B fails, and the API does not automatically revert A.

This lesson focuses on **how to select, prepare, execute, and verify a set of classes**, what happens when a class in the set has invalid or unmodifiable bytecode, and the **limits of atomicity**: application state, logs/metrics, callback side effects, running threads, and previous batches are **not** automatically rolled back.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Distinguish **a single multi-class call** from **multiple single-class calls**.
2. Understand the exact guarantee: **a failed call ⇒ no class definition in the set is installed by that call**.
3. Check **isRetransformClassesSupported()**, **isModifiableClass(...)**, and identify the **exact Class object**, not just the class name.
4. Register an appropriate **ClassFileTransformer** with **canRetransform=true**, while understanding that the results of **canRetransform=false** transformers are reapplied by the JVM without invoking the callback again.
5. Handle valid errors: **UnmodifiableClassException**, **UnsupportedOperationException**, **ClassFormatError**, **LinkageError**, and the errors listed by the API.
6. Avoid confusing the fact that a callback has run with the fact that the class **has been installed by the JVM**.
7. Write a Java 17 test using a two-class batch: one successful run, one run that intentionally produces invalid bytecode, and one run that includes an unmodifiable array class.
8. Design reporting and safe retry workflows, avoiding accidentally creating a "half-new, half-old" state due to improper batch splitting.

## 2. Visualizing a Multi-Class Request

Suppose the application has two loaded classes:

~~~text
Class A: com.example.Service
Class B: com.example.Repository
~~~

The agent needs to modify both in the same instrumentation version. With a single call:

~~~java
// Illustrative snippet in agent code that already has Instrumentation inst.
inst.retransformClasses(Service.class, Repository.class);
~~~

Conceptually, the JVM processes this as:

~~~text
retransformClasses(A, B)
          │
          ▼
  prepare class bytes for A and B
          │
          ▼
  apply the transformer chain to A and B
          │
          ▼
  check format, validity, and class change limits
          │
          ├── any class fails
          │           │
          │           ▼
          │     throw exception
          │     DO NOT install new definitions for A or B
          │
          └── all are accepted
                      │
                      ▼
              install the new definitions of the set
              the call returns normally
~~~

The diagram describes the **guarantee at the API boundary**; it does not prescribe the order in which the JVM must invoke the transformer for each class or require all callbacks to be invoked when an error is detected early. The practical guarantee to remember is: when **the call throws an exception**, no element of the set is successfully retransformed by that call.

### 2.1. Comparison with Two Separate Calls

~~~java
// Approach 1: one multi-class request.
inst.retransformClasses(A.class, B.class);

// Approach 2: two independent requests.
inst.retransformClasses(A.class);
inst.retransformClasses(B.class);
~~~

| Scenario | One call A+B | Two calls A then B |
| --- | --- | --- |
| Both A and B are valid | Both are processed in the same request | Two independent requests can both succeed |
| B fails before installation | **Neither A nor B is installed from the failed batch** | A may have already succeeded and still keeps the new definition |
| Want A/B updated to the same version | Better suited when two classes depend on each other | Requires a separate coordination/rollback mechanism |
| Retry after failure | Can fix the root cause and retry the same set | Must distinguish which class was already updated in earlier calls |
| Error on an unmodifiable class | The request fails and installs no class | If detected on B's turn, the earlier A turn is not automatically reverted |

**Do not treat two consecutive calls as a single transaction.** The API does not provide a shared commit/rollback mechanism across two separate calls.

## 3. Transformation Chain Applied to Each Element in the Set

**retransformClasses** reruns the transformation process from the base bytes of each class according to the Instrumentation mechanism. In Java 17:

- **Transformers registered with canRetransform=false**: are not invoked again during retransformation; the JVM automatically **reapplies the saved result** from the previous class load/redefine, equivalent to applying the old result without invoking the callback.
- **Transformers registered with canRetransform=true**: may be invoked again by the JVM for the classes in the set being retransformed.
- **Each transformer** must keep the input buffer immutable, **return null** if it makes no changes, and **return a new byte[]** if it provides a replacement class file.
- **Base bytes during retransform** are not necessarily byte-for-byte identical to the class file on disk/at initial definition: the constant pool/attributes may be represented differently.
- **The final result** must be a valid class definition and stay within the change limits supported by the JVM for an already-loaded class.

~~~text
Initial bytes of A ── non-retransform results for A ── retransform-capable transformers for A ── A'
Initial bytes of B ── non-retransform results for B ── retransform-capable transformers for B ── B'
                                                                                                 │
                                                                                          validate the set
                                                                                                 │
                                                                                          accept or fail
~~~

In the example, A' and B' are **proposed definitions**, not necessarily installed immediately when the transformer returns bytes. A callback that logs **A_REPLACEMENT_READY** only proves that a transformation result exists for A; if B has invalid bytecode and the whole call fails, A' **is not committed**.

### 3.1. The Order of Classes in Varargs Is Not a Callback Order Guarantee

~~~java
inst.retransformClasses(B.class, A.class);
~~~

Programs should treat this as a **target set**, without relying on assumptions like "B's callback always runs before A's" or "seeing A's log means A is already installed". The main reason the API supports multiple classes is to allow **related changes** to be processed in the same request. A JVM may check for errors at multiple stages; how many callbacks have run before an error is not an indicator of commit.

At the same time, the order of **transformers for a single class** follows the **ClassFileTransformer** groups and the registration order within each group; that is a **different** matter from the order of elements A and B in the varargs parameter.

### 3.2. Not Every Batch Actually Changes Bytecode

If every transformer returns **null** or a result equivalent to the old bytes, **retransformClasses(A,B)** may return normally while the behavior of A/B remains unchanged. "Batch completed" does not equate to "the right new feature has taken effect".

To report **business-level instrumentation success**, additional verification is needed:

- The right classes were targeted (binary name, defining loader, module).
- The transformer actually supplied a new class file matching the requirement.
- The JVM did not reject it and the call returned normally.
- A **new** method invocation exhibits the expected behavior after retransformation.

## 4. Preconditions Before Retransforming Multiple Classes

### 4.1. JVM Capability and Agent Manifest

Retransformation capability is **optional** depending on the JVM and agent configuration. For a startup agent, the manifest must request:

~~~text
Manifest-Version: 1.0
Premain-Class: BatchAgent
Can-Retransform-Classes: true
~~~

The default value of **Can-Retransform-Classes** is **false** if omitted. Even if the manifest specifies **true**, the JVM must still support it; check **inst.isRetransformClassesSupported()** before calling **addTransformer(transformer, true)** and **retransformClasses(...)**.

If the agent can only operate when this capability is present, failing fast at startup is appropriate. If the feature is only optional, you can report **UNSUPPORTED** and skip installing a retransform-capable transformer; do not claim that classes were updated.

### 4.2. Modifiability of Each Class

~~~java
// Illustrative snippet in a service that has Instrumentation inst.
for (Class<?> type : targets) {
    if (!inst.isModifiableClass(type)) {
        throw new IllegalArgumentException(
                "Class not modifiable: " + type.getName());
    }
}
inst.retransformClasses(targets);
~~~

**isModifiableClass(Class)** is a necessary condition for a class to be retransformed, but **not sufficient**: the capability must also be present, the transformer must produce valid bytes, the class schema must not be modified in ways the JVM does not support, and linkage dependencies must be valid.

**Primitive classes and array classes are not modifiable** according to the Javadoc. For example, **int.class** and **int[].class** cannot be included in a batch expecting the JVM to change their bytecode. Keep the list as a **real Class<?>[]**, rather than using a list of string names as a substitute for class identity.

### 4.3. Selecting the Right Class Object

Two classes with the same name **com.acme.Service** defined by two different defining class loaders are **two different runtime types**. Picking the wrong **Class** can update the wrong application/plugin. To build the set:

1. Use **inst.getAllLoadedClasses()** or a trusted class-identity source when you must find loaded classes.
2. Filter by binary name.
3. Check the **defining class loader**, module, and version/module layer if needed.
4. Check **isModifiableClass** on each element.
5. Pass only the exact identified set into a single call.

Do not arbitrarily call **Class.forName** for an unloaded class just to "have a target": doing so can alter class loading timing, trigger initialization if using the default overload, or put a class from the wrong loader into the set.

### 4.4. Null Data, Empty Arrays, and Pre-Processing Errors

The Java 17 Javadoc specifies:

- **retransformClasses()** with a **zero-length array** is valid and **does nothing**.
- A **classes == null** parameter or a **null element** causes **NullPointerException**.
- An unmodifiable class is present: **UnmodifiableClassException**.
- The JVM/agent does not support retransformation or an unsupported schema change is attempted: **UnsupportedOperationException**.
- Invalid class bytes/constraint violations: **ClassFormatError**, **UnsupportedClassVersionError**, **NoClassDefFoundError**, **ClassCircularityError**, **LinkageError**, depending on the cause.

In real systems, preflight as much as possible, and **still handle exceptions from the actual call**. Preflight checks do not eliminate races with other agents, class loaders, or errors raised by transformers at update time.

## 5. Java 17 Hands-On Lab: A Batch Containing Alpha and Beta

We will build a standalone Java 17 program with no external libraries, consisting of:

- **BatchApp$Alpha.value()** initially returning **ALPHA0**.
- **BatchApp$Beta.value()** initially returning **BETA_0**.
- **BatchAgent** loaded by the JVM at startup via **-javaagent**, storing the **Instrumentation** handle and registering a **canRetransform=true** transformer.
- **BatchTransformer** replacing strings in `classfileBuffer` only when the class is being **retransformed**, not on the initial class load.
- The **success** command updates both literals to **ALPHA1** and **BETA_1** in a single call.
- The **failure** command intentionally returns **invalid class file bytes for Beta**, to verify the guarantee that neither A nor B is installed.
- The **reject-array** command adds **int[].class** (unmodifiable) to the set to test failure before/or during processing without partial updates.

The transformation approach uses a helper that reads **CONSTANT_Utf8** entries in the class file constant pool. It only replaces **6 ASCII bytes with 6 ASCII bytes**, which is sufficient for the demo classes compiled by **javac --release 17** and is **not** a general-purpose bytecode library. In real systems, use ASM/Byte Buddy or a class-file toolkit with an appropriate verifier.

### 5.1. File BatchApp.java

~~~java
// File: BatchApp.java
import java.lang.instrument.Instrumentation;
import java.lang.instrument.UnmodifiableClassException;

public final class BatchApp {

    static final class Alpha {
        static String value() {
            return "ALPHA0";
        }
    }

    static final class Beta {
        static String value() {
            return "BETA_0";
        }
    }

    private static String snapshot() {
        return Alpha.value() + "|" + Beta.value();
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1 ||
                (!"success".equals(args[0])
                 && !"failure".equals(args[0])
                 && !"reject-array".equals(args[0]))) {
            throw new IllegalArgumentException(
                    "Usage: BatchApp success|failure|reject-array");
        }

        String mode = args[0];
        Instrumentation inst = AgentState.required();

        // snapshot() calls both methods and ensures both classes
        // are loaded before the retransformClasses call.
        String before = snapshot();
        System.out.println("BEFORE=" + before);

        if (!inst.isRetransformClassesSupported()) {
            throw new IllegalStateException(
                    "Retransform capability is not available");
        }

        if (!inst.isModifiableClass(Alpha.class)
                || !inst.isModifiableClass(Beta.class)) {
            throw new IllegalStateException(
                    "The demo classes must be modifiable");
        }

        AgentState.mode = mode;

        Class<?>[] batch = "reject-array".equals(mode)
                ? new Class<?>[] {
                        Alpha.class, int[].class, Beta.class
                  }
                : new Class<?>[] {
                        Alpha.class, Beta.class
                  };

        boolean failed = false;
        try {
            // ONLY ONE CALL for the entire set.
            inst.retransformClasses(batch);
            System.out.println("BATCH_OK");
        } catch (UnmodifiableClassException
                 | UnsupportedOperationException
                 | LinkageError error) {
            failed = true;
            System.out.println("BATCH_FAILED");
        }

        String after = snapshot();
        System.out.println("AFTER=" + after);

        if ("success".equals(mode)) {
            if (failed || !"ALPHA1|BETA_1".equals(after)) {
                throw new AssertionError(
                        "Expected both new definitions");
            }
        } else {
            if (!failed || !before.equals(after)) {
                throw new AssertionError(
                        "Failed batch must install neither class");
            }
        }
    }
}
~~~

Why must **before** invoke both methods? Because the targets of **retransformClasses** are **Class objects that have already been loaded by the JVM**. In this program, **snapshot()** actively causes both classes to be defined and executed in their original state before the retransform request is sent.

**AgentState.required()** throws a clear exception when the application is run without the agent, avoiding a false "success". Depending on the mode, the program prints **BATCH_OK** or **BATCH_FAILED** and verifies the final result. Omitting the exception name keeps the transcript reproducible; in a real tool, log the exception's **class, message, and stack trace** for diagnostics.

**Note on catch:** Here **LinkageError** covers class format/linkage errors from the JVM in the test. The example catches only the relevant failure classes; do not catch and swallow every **Throwable** as a production policy. The **AssertionError** from the final check is allowed to propagate so the test genuinely fails if the result does not meet the requirement.

### 5.2. File BatchAgent.java

~~~java
// File: BatchAgent.java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.nio.charset.StandardCharsets;
import java.security.ProtectionDomain;

public final class BatchAgent {
    private BatchAgent() {
    }

    public static void premain(String options, Instrumentation inst) {
        if (!inst.isRetransformClassesSupported()) {
            throw new IllegalStateException(
                    "This agent requires retransformation support");
        }
        AgentState.install(inst);
        inst.addTransformer(new BatchTransformer(), true);
    }
}

final class AgentState {
    private static volatile Instrumentation instrumentation;
    static volatile String mode = "off";

    private AgentState() {
    }

    static void install(Instrumentation inst) {
        if (inst == null) {
            throw new NullPointerException("Instrumentation missing");
        }
        if (instrumentation != null) {
            throw new IllegalStateException("Agent already installed");
        }
        instrumentation = inst;
    }

    static Instrumentation required() {
        Instrumentation current = instrumentation;
        if (current == null) {
            throw new IllegalStateException("Run with -javaagent");
        }
        return current;
    }
}

final class BatchTransformer implements ClassFileTransformer {
    @Override
    public byte[] transform(
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain domain,
            byte[] classfileBuffer) {

        // Skip initial class load: only transform during retransformation.
        if (classBeingRedefined == null) {
            return null;
        }

        if ("BatchApp$Alpha".equals(className)) {
            return replaceUtf8(
                    classfileBuffer, "ALPHA0", "ALPHA1");
        }

        if ("BatchApp$Beta".equals(className)) {
            if ("failure".equals(AgentState.mode)) {
                // Intentionally not a valid class file.
                // This is the FAIL test for the entire batch.
                return new byte[] {0, 1, 2};
            }
            return replaceUtf8(
                    classfileBuffer, "BETA_0", "BETA_1");
        }

        return null;
    }

    private static byte[] replaceUtf8(
            byte[] original, String oldValue, String newValue) {

        byte[] before = oldValue.getBytes(StandardCharsets.US_ASCII);
        byte[] after = newValue.getBytes(StandardCharsets.US_ASCII);

        if (before.length != after.length
                || original.length < 10
                || (original[0] & 0xff) != 0xca
                || (original[1] & 0xff) != 0xfe
                || (original[2] & 0xff) != 0xba
                || (original[3] & 0xff) != 0xbe) {
            return null;
        }

        int poolCount = u2(original, 8);
        int p = 10;

        for (int i = 1; i < poolCount; i++) {
            int tag = original[p++] & 0xff;
            switch (tag) {
                case 1 -> {
                    // CONSTANT_Utf8_info.
                    int len = u2(original, p);
                    p += 2;

                    if (len == before.length
                            && matches(original, p, before)) {
                        byte[] result = original.clone();
                        System.arraycopy(
                                after, 0, result, p, after.length);
                        return result;
                    }

                    p += len;
                }

                case 3, 4, 9, 10, 11, 12, 17, 18 -> p += 4;
                case 5, 6 -> {
                    // CONSTANT_Long / CONSTANT_Double
                    // occupy two entries in the constant pool.
                    p += 8;
                    i++;
                }
                case 7, 8, 16, 19, 20 -> p += 2;
                case 15 -> p += 3;
                default -> throw new IllegalArgumentException(
                        "Unsupported constant-pool tag " + tag);
            }
        }

        return null;
    }

    private static int u2(byte[] bytes, int index) {
        return ((bytes[index] & 0xff) << 8)
                | (bytes[index + 1] & 0xff);
    }

    private static boolean matches(
            byte[] bytes, int position, byte[] expected) {
        if (position + expected.length > bytes.length) {
            return false;
        }
        for (int i = 0; i < expected.length; i++) {
            if (bytes[position + i] != expected[i]) {
                return false;
            }
        }
        return true;
    }
}
~~~

Detailed analysis:

1. **premain(String, Instrumentation)** is the startup agent entry point. The JVM provides **Instrumentation** directly; you do not instantiate a new interface implementation yourself.
2. The agent checks **isRetransformClassesSupported()** before registering a **canRetransform=true** transformer. The example's manifest must also request that capability.
3. **AgentState** holds the handle and mode for the same JVM. The code in **main** sets **mode** before calling retransform. **volatile** allows a callback on another thread to read the new configuration, though it does not make all agent data thread-safe.
4. **classBeingRedefined == null** on the initial class load: the transformer **returns null**. Thus, the two classes Alpha/Beta initially execute their original literals.
5. In the batch, **Alpha** can return replacement bytes containing **ALPHA1**, while **Beta** can return bytes containing **BETA_1** or an array without class file formatting when mode is **failure**.
6. **replaceUtf8** creates a **new array** from the input and only replaces ASCII strings of the same length. It does not mutate **classfileBuffer** directly.
7. **return new byte[] {0,1,2}** is strictly for the failure test. It causes the JVM to reject Beta's class file result, and **must not be used in a real agent**. It is not equivalent to **return null**: **null** means no modification, whereas an invalid array is an unacceptable replacement.
8. The agent does not intentionally throw an exception inside the transformer to fail the batch. By contract, an exception thrown from a **ClassFileTransformer** callback may be treated as providing no transformation and the JVM continues with other transformers; therefore, **returning invalid bytes** is a more observable test for definition validation/installation failure.

**Helper limitations:** The constant pool reader above is written only for valid demo classes; it is not a full parser, does not handle all Modified UTF-8 cases, lacks strict bounds checking for malicious input, and does not modify complex method bodies. Do not apply it to real classes. Use ASM, Byte Buddy, or an appropriate class-file toolkit when general bytecode instrumentation is needed.

### 5.3. File agent.mf

Create the text file **agent.mf** with a trailing newline character:

~~~text
Manifest-Version: 1.0
Premain-Class: BatchAgent
Can-Retransform-Classes: true
~~~

**Can-Retransform-Classes: true** is a capability request, not a promise that every JVM supports it. If running via dynamic attach instead of a startup agent, you must use the **Agent-Class** manifest attribute and an appropriate **agentmain** callback; that is not the mechanism used in this demo.

### 5.4. Compiling and Packaging

Place the three files **BatchApp.java**, **BatchAgent.java**, and **agent.mf** in the same directory. On JDK 17:

~~~bash
javac --release 17 BatchApp.java BatchAgent.java
jar cfm batch-agent.jar agent.mf \
    BatchAgent.class AgentState.class BatchTransformer.class
~~~

The **jar** command above uses **backslashes** for line continuation in POSIX shell syntax. If using Windows cmd.exe/PowerShell, put the jar command on **a single line**:

~~~text
jar cfm batch-agent.jar agent.mf BatchAgent.class AgentState.class BatchTransformer.class
~~~

After packaging, **BatchApp.class**, **BatchApp$Alpha.class**, and **BatchApp$Beta.class** are on the application classpath (current directory). The agent JAR needs the three classes **BatchAgent, AgentState, BatchTransformer** and the manifest. The demo uses no package to keep class names and the jar command simple; production code should use clear namespaces/packages.

Inspect the agent JAR:

~~~bash
jar tf batch-agent.jar
~~~

The listing must include **META-INF/MANIFEST.MF** along with the three agent classes. If **AgentState.class** is missing, the JVM may fail to load the agent properly at startup.

### 5.5. Case Where Both Classes Are Valid: success

~~~bash
java -javaagent:batch-agent.jar -cp . BatchApp success
~~~

Expected output on HotSpot Java 17 with retransform capability:

~~~text
BEFORE=ALPHA0|BETA_0
BATCH_OK
AFTER=ALPHA1|BETA_1
~~~

Explanation:

- **BEFORE** is computed from the original methods, while also ensuring both classes are loaded.
- In **success** mode, the agent returns modified bytes for both Alpha and Beta.
- **retransformClasses(Alpha.class, Beta.class)** completes normally, meaning the JVM processed the batch without throwing an error.
- **AFTER** is computed via new invocations and observes both new values.

If the output shows **BATCH_OK** but **AFTER** remains unchanged, the transformation may have produced no change; the example's assertion will detect this and fail. API completion alone is not sufficient proof for business logic.

### 5.6. One Class Has Format Errors: failure

Run in **a new JVM process** to start from a clean baseline:

~~~bash
java -javaagent:batch-agent.jar -cp . BatchApp failure
~~~

Expected output:

~~~text
BEFORE=ALPHA0|BETA_0
BATCH_FAILED
AFTER=ALPHA0|BETA_0
~~~

In **failure** mode, the transformer for Alpha may still have produced valid bytes containing ALPHA1. The transformer for Beta returns the array **{0,1,2}**, which is not a class file with the **CAFEBABE** magic header. The JVM must reject the invalid definition, and the retransform call throws a class-format/linkage error (caught via **LinkageError** in the demo code).

By the **retransformClasses** contract, **no class in the batch is successfully retransformed** if the call throws an exception. Thus **AFTER** remains **ALPHA0|BETA_0**. The fact that Alpha **may have passed through the callback** or that a new `byte[]` **was created** does not mean Alpha was installed.

**Do not infer** that the JVM must invoke Alpha's callback before Beta's, or that it must invoke every transformer before detecting an error. We rely on **the outcome guaranteed by the API**, not on log print order.

### 5.7. One Unmodifiable Class: reject-array

Run in a new JVM:

~~~bash
java -javaagent:batch-agent.jar -cp . BatchApp reject-array
~~~

Expected output:

~~~text
BEFORE=ALPHA0|BETA_0
BATCH_FAILED
AFTER=ALPHA0|BETA_0
~~~

In this mode, the target array is:

~~~java
// Illustrative snippet from BatchApp, not a standalone Java file.
new Class<?>[] {
    BatchApp.Alpha.class, int[].class, BatchApp.Beta.class
}
~~~

**int[].class** is an array class; per the Javadoc, array classes are **not modifiable**. The call can throw **UnmodifiableClassException**. Because **one call processes the entire set**, Alpha and Beta retain their definitions from before the failed request.

**Key takeaway:** For an array class, the system can easily detect **isModifiableClass(int[].class) == false** during preflight and avoid sending the request. The test sends it intentionally to demonstrate the API's failure behavior; doing so in production is not recommended.

### 5.8. What If -javaagent Is Forgotten?

~~~bash
java -cp . BatchApp success
~~~

The application will fail intentionally at **AgentState.required()**, because no **Instrumentation** was passed to the agent by the JVM. There is no Java SE API for a normal application to obtain Instrumentation as a global static variable without an appropriate agent mechanism.

## 6. How Exact Is the All-or-None Guarantee?

We must clearly separate **installed classes** from **any events that occur during preparation**.

### 6.1. What Is Guaranteed If the Call Throws an Exception

According to the Java 17 Instrumentation API:

**If retransformClasses(...) throws an exception, no class in the parameters of that call has been retransformed by that call.**

This is sufficient to avoid a state where "A already carries the new code from batch N, while B does not because batch N failed" **due to batch N itself**. This is precisely why the API supports a set of classes—to apply interdependent updates together.

If individual classes were already successfully retransformed in **an earlier batch**, a failure in the new batch **does not revert the earlier batch**. For example:

~~~text
Initially: A0, B0

Batch #1: retransformClasses(A, B)
  → succeeds; now A1, B1

Batch #2: retransformClasses(A, B)
  → fails on B
  → result remains A1, B1
  → NO automatic rollback to A0, B0
~~~

### 6.2. What Is Not Automatically Rolled Back

| Subject | When a batch fails, what happens? |
| --- | --- |
| **Class definitions of the set passed to the batch** | No class has a new definition installed by the failed batch |
| **Logs printed by the transformer before the error** | Still remain in the console/file |
| **Counters/metrics incremented in the callback** | Remain incremented unless the agent manages state itself |
| **Static configuration of the agent** | Remains at the value the agent wrote; not automatically rolled back |
| **Network requests/I/O performed by the agent** | Not undone by the JVM |
| **Class loading or other side effects occurring in the callback** | Not included in the class-definition transaction by default |
| **A previously succeeded batch** | Retains its previously installed definition |
| **Definitions of classes outside the set updated independently by another agent** | Not protected by this batch |
| **Existing objects and static fields of the application** | Not reset to initial values |
| **Method invocations on active stack frames** | May continue running old bytecode per JVM rules; cannot "turn back time" |

Therefore, **all-or-none is not a JVM-wide database transaction**. It only applies to **installing the definitions of the class set** within the retransform call. There is no ACID transaction covering all process state, all threads, and all agent side effects.

### 6.3. When a Batch Succeeds, Do Threads See an Instant "Version Switch"?

According to the Javadoc, **active stack frames** of retransformed methods may continue running the **original method bytecode**; **new invocations** use the updated definition. This means a running workload may still have an old A frame while new invocations are already running the new A.

Even when a batch is successfully installed as a set, **do not promise callers that every in-flight business request will see the "new A/B version" as a perfectly linearizable snapshot**. If the application requires a protocol change between A and B where every request must pick the same version, design **quiescence, version gating, feature flags, or application-level coordination**. A retransform batch does not replace business transaction coordination mechanisms.

### 6.4. Static Initializers and Object Instances Are Not Reset

Retransformation does not automatically re-run **<clinit>**, does not recreate existing objects, and does not reset static field values. For example, changing the bytecode of a method that reads a static field does not mean the field's value immediately switches to a new value. When testing results, distinguish **the new class definition** from **the existing state of instances and static variables**.

## 7. Why Is a Multi-Class Set Useful for Dependent Changes?

Consider two classes sharing a protocol:

~~~java
// Conceptual pseudocode, not a standalone Java file.
class Service {
    Response handle(Request r) {
        return Repository.lookup(r);
    }
}

class Repository {
    static Response lookup(Request r) {
        // ...
    }
}
~~~

If an agent wants to install new tracing logic for both caller and callee, it may need A/B updated together to avoid a state where method A emits a new span format while B still uses the old format.

A batch **retransformClasses(Service.class, Repository.class)** is appropriate when **class definition changes** have dependencies. However, if you intend to add new methods/fields or modify descriptors in ways the JVM disallows during retransformation, batching **does not make those structural changes valid**. Choose the right instrumentation approach: modify method bodies within supported limits, or use an external helper architecture/another deployment path.

### 7.1. A Batch Only Processes the Exact Selected Classes

If Service calls a third class **Cache** that was not added to the set, there is no guarantee that Cache will be automatically included in the batch. Transformations of Cache may occur independently due to class loading or another agent. To update a protocol involving A, B, and C, you must assemble the complete target set of **classes that need to change** and manage dependencies deliberately.

### 7.2. Distinguishing a "Set of Classes" from "All Instances"

**retransformClasses(Class<?>...)** accepts **Class objects**, not a list of instances. The JVM updates the method definitions of the classes; existing instances of those classes remain the same objects. You do not need to list every object to retransform it separately, nor is class identity changed into a new `Class` just because the bytecode changed.

## 8. Classifying Errors from retransformClasses

| Error or error group | Common condition | How to handle |
| --- | --- | --- |
| **UnmodifiableClassException** | An element is not modifiable | Check class identity; exclude unsupported classes before sending |
| **UnsupportedOperationException** | JVM/manifest lacks support, or change exceeds retransformation limits | Check capability and class schema |
| **ClassFormatError** | Transformer returns invalid class file data | Inspect `classfileBuffer` and the returned `byte[]` |
| **UnsupportedClassVersionError** | Class file version is not supported by the JVM | Check major version and the toolchain generating the bytes |
| **NoClassDefFoundError** (when the name in the classfile differs from the target class) | Wrong internal/binary name in the result | Do not change class identity/name during retransformation |
| **ClassCircularityError** | Result introduces an invalid type dependency cycle | Analyze hierarchy and linking |
| **LinkageError** | Related linkage/verification conflict | Inspect cause and class loader/module |
| **NullPointerException** | `classes` array or an element is null | Validate input before sending |
| Call returns normally but no new behavior | Transformer returned null, equivalent bytes, or wrong target was checked | Check transformer, class identity, and post-retransform invocation |

**Never catch an exception and report "part of the batch was installed".** By contract, if the `retransformClasses` call itself throws an exception, the commit outcome of the batch is **none**. Multiple callbacks may have run, but that is not proof of installation.

### 8.1. A Transformer Throwing an Exception Differs from Returning Invalid Bytes

Per the ClassFileTransformer Javadoc, if **transform() throws an exception**, the JVM may still invoke other transformers and proceed with defining/retransforming; for that callback, the exception may be treated the same as returning no replacement bytes. Therefore:

~~~java
// Illustrative snippet solely to distinguish behavior.
throw new IllegalStateException("failed inside transform");
~~~

is not a reliable way to **force retransformClasses to fail**. In the demo, the failure branch returns **an array that is not a valid class file**, leading to an error when the JVM validates the result. In production, a transformer should **return null** if intentionally skipping; report business errors through a separate management channel when needed.

### 8.2. API-Level Atomicity Does Not Mean Exceptions Are Automatically Diagnosed

When a 20-class batch fails, the general exception does not necessarily identify which class caused the error; callback logs can help narrow it down, though they are not a commit log either. Diagnostic design:

- Log the request ID, list of class identities (class name, loader/module), capability, and agent version.
- Log the classes received by the transformer, null/new bytes results, and byte sizes/hashes if needed.
- Log the exception type/message/stack trace from **retransformClasses**.
- When needed, test **smaller sets in a test environment** to isolate the failing class, understanding that splitting into new calls **changes the atomicity guarantee**. Do not perform binary search in production and accidentally install half a fix when the first subset succeeds.

## 9. Designing a Safe Production Batch

### 9.1. Preparation Phase

1. **Identify requirements**: which classes must change together to preserve compatibility?
2. **Resolve Class objects** from the right JVM, loader, and module; do not rely on class name alone.
3. **Check capability** with **isRetransformClassesSupported()**.
4. **Check modifiability** for each element; do not include arrays/primitives or unsupported classes.
5. **Configure the transformer** before calling: class filters, advice version, ready dependency/helper classes, and thread-safe state.
6. **Plan for overhead**: large class files, retransformation, and the verifier can cause pauses/CPU overhead, especially when many classes are processed in one request.
7. **Establish evidence**: before state and expected after state, with probes/tests using new invocations.

### 9.2. API Invocation Phase

~~~java
// Illustrative programming pattern inside an agent service.
if (!inst.isRetransformClassesSupported()) {
    throw new IllegalStateException("Retransform unavailable");
}

Class<?>[] targets = { Service.class, Repository.class };
for (Class<?> target : targets) {
    if (!inst.isModifiableClass(target)) {
        throw new IllegalArgumentException(
                "Not modifiable: " + target.getName());
    }
}

// One call containing the entire dependent set.
inst.retransformClasses(targets);
~~~

This snippet uses **Service/Repository** as illustrative placeholders and must be placed inside a real program with appropriate imports/class declarations. It is not a standalone runnable Java file.

### 9.3. Verification Phase

When **retransformClasses** returns normally:

1. Do not only check "no exception"; verify that the actual classes produce the expected results.
2. Use **new invocations** to avoid misreading old active frames.
3. Confirm that dependent components are compatible with one another.
4. Record the batch version and application timestamp for diagnostics.
5. If evidence of new behavior is missing, report **APPLIED_UNVERIFIED** or an appropriate status instead of "everything succeeded".

When the call throws an exception:

1. Report **BATCH_FAILED**, along with the root error, request ID, and target set.
2. **Do not mark any element as installed by the failed batch**.
3. Do not erase the state of previously succeeded batches.
4. You may keep agent configuration in a "pending" state or revert it per your own policy, but this **is not done automatically by the JVM**.
5. After fixing the root cause, you may retry the **same set**, provided the classes remain modifiable and transform cleanly from their current state.

### 9.4. Retries Must Not Cause Double Instrumentation

If a batch succeeds but the operator fails to receive acknowledgment at the management layer, a retry could inject advice twice if the transformer is not idempotent. Design so that:

- The transformer recognizes its own markers/callsites or builds deterministic output from the bytes provided by the JVM.
- It does not blindly prepend the same instructions on every callback.
- It does not cache solely by FQCN when multiple loaders exist.
- When using versions, verify the installed version via verifiable behavior or metadata.
- Avoid infinite retries on **ClassFormatError**: fix the transformer logic rather than simply calling again.

### 9.5. Batching by Size and Dependencies

An overly large batch can impact processing time, debuggability, and the blast radius of rollback when one class fails; an overly small batch can break the requirement to update dependent classes together. **Group by sets of classes that must be logically consistent**:

~~~text
Protocol group A:
   Service, Repository, QueryMapper
   → 1 batch because they share the same instrumentation version

Independent group B:
   MetricsPrinter
   → separate batch if it does not affect protocol A
~~~

There is no "bigger batch is always better" rule. The goal is to choose **meaningful atomic boundaries**—small enough to operate cleanly, large enough to avoid half-deployed dependent class definitions.

## 10. Comparison with redefineClasses

**Instrumentation.redefineClasses(ClassDefinition...)** also accepts **a set of class definitions** and guarantees that *if the call throws an exception, no class in the set is redefined*. However, the two APIs differ:

| Property | **retransformClasses** | **redefineClasses** |
| --- | --- | --- |
| Input | Loaded `Class` objects | `ClassDefinition` objects containing `Class` and new bytes |
| Source of bytes | JVM reconstructs base bytes and applies transformers | Caller supplies class file bytes; JVM applies appropriate transformers |
| Typical purpose | Rerun instrumentation to modify running classes | Directly install caller-supplied class definitions |
| Capability | **Can-Retransform-Classes** / JVM support | **Can-Redefine-Classes** / JVM support |
| Multi-class atomic failure | Yes | Yes |
| Schema limits | Yes | Yes |
| Active frames | May continue old code | May continue old code |

You cannot use **redefineClasses** as a way to bypass all schema limits or as an automatic rollback for retransformation. If you need to revert an earlier modification, you must have valid bytes and account for other transformers, class identity, redefinition capability, and business goals; simply removing a transformer does not erase already-installed code.

## 11. Common Misconceptions

### 11.1. "Seeing transformer A's log" means A was installed?

**No.** The transformer may have run and returned bytes A', yet the batch still failed when validating B'. That log is just a side effect of the byte-generation phase and is not rolled back.

### 11.2. "Class B has an error, so the JVM will keep the new A and only skip B"?

**Not in the same retransformClasses(A,B) call.** If the call throws an exception, no element is retransformed. This differs from two independent calls.

### 11.3. "When a batch fails, all classes revert to the original JAR file"?

**No.** They retain the definitions that were installed **before the failed call**, which may already have been retransformed earlier; there is no reset of classes or static state.

### 11.4. "Batch success means A and B changed behavior"?

**Not necessarily.** The transformer may have returned null or equivalent bytes. Evidence of change must be verified separately.

### 11.5. "All-or-none guarantees in-flight requests only see all-new code"?

**Not at the business transaction level.** The JVM may keep active frames running old code; application-level coordination is required if every request must traverse a consistent protocol version.

### 11.6. "I split the set into 10 small batches and still call it one transaction"?

**No.** Each call only has a failure guarantee over **its own set**. Earlier successful batches are not rolled back if a later batch fails.

### 11.7. "isModifiableClass returning true guarantees retransformation will succeed"?

**No.** It only confirms one condition. Capability, class format, module/helper linkage, schema restrictions, and bytes from the transformer must still be valid.

## 12. Recommended Test Matrix

| Test | Setup | Expected |
| --- | --- | --- |
| Two valid classes | Alpha, Beta; transformer returns valid bytes | Batch completes; both new methods produce new results |
| Invalid Beta class file | Alpha valid; Beta returns invalid bytes | Batch throws; both methods keep prior behavior |
| Contains array class | Alpha, int[].class, Beta | **UnmodifiableClassException**; no new updates |
| Contains null | Alpha, null, Beta | **NullPointerException**; no updates |
| Empty set | **retransformClasses()** | No error, as the API allows a no-op |
| Missing capability | Manifest/JVM does not support it | Rejected; do not attempt `addTransformer(true)` |
| Transformer returns null | No new output | API may complete while behavior stays unchanged |
| Callback throws RuntimeException | Internal transformer error | Not equivalent to batch throw; JVM may treat callback as skipped |
| Two independent batches | A succeeds, B fails | A still has the new definition from the earlier batch |
| Retry same batch | Idempotent transformer | Does not duplicate advice |
| Two loaders with same name | Two independent `Class` identities | Right class selected, no accidental wrong-class edit |
| Running method | Active frame before retransformation | Old frame may continue old code; new invocation uses new code |
| Multiple agents | Different transformer chains | Valid final result; order dependency tested |

### 12.1. When Deeper Verification Is Needed

- Running **javap** on the original class file only shows the file on disk; it does not automatically show runtime-installed bytes.
- You can dump **bytes returned by the transformer** in a test environment and inspect the class file, though that alone is not proof of commit.
- If behavioral confirmation is needed, build a probe that invokes the exact class/method **after the API returns**, reading the expected result/metric.
- Do not argue that all callbacks must have been invoked before the JVM reports an error; rely only on the API guarantee.
- If a class has complex handlers/stack frames, test the verifier, exception semantics, thread safety, and helper accessibility under the actual JDK.

## 13. Operational Checklist for a Multi-Class Batch

- I fully identify the set by **Class + defining loader + module**.
- I understand why these classes require a single request rather than splitting into multiple requests.
- The agent has declared and checked **Can-Retransform-Classes** / JVM capability.
- All targets are checked with **isModifiableClass**.
- Each transformer only modifies classes/methods within its scope; it does not mutate `classfileBuffer`.
- **canRetransform=false** transformers are properly understood to reapply old results without being invoked again.
- Proposed `byte[]` values are valid in format, class name, class version, and schema limits.
- A single **retransformClasses(targets)** call is used for the dependent set.
- **If the call throws**, the system reports *none installed for that batch*, never partial success.
- Do not expect the JVM to roll back logs, counters, I/O, static fields, or earlier batches.
- When **the call succeeds**, I verify new invocations and the behavior of **all related classes**.
- Retries are idempotent; callbacks, shared state, and multiple agents can run concurrently without corrupting results.

## 14. Official Java Documentation

- [Java 17 — Instrumentation.retransformClasses](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#retransformClasses(java.lang.Class...)): describes processing a set, retransformation steps, and the guarantee that no class is installed if the call throws an exception.
- [Java 17 — Instrumentation.isModifiableClass](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#isModifiableClass(java.lang.Class)): arrays/primitives are not modifiable and check conditions.
- [Java 17 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): transformer chain, immutable `classfileBuffer`, returning null/bytes, and exception handling in callbacks.
- [Java 17 — java.lang.instrument package specification](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): Premain-Class, Agent-Class, and Can-Retransform-Classes.
- [Java Virtual Machine Specification 17 — Class File Format](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html): constant pool, class format, and class file constraints.

**Key takeaway:** a single call **retransformClasses(A, B, ...)** lets the JVM update **a set of class definitions** under an *all-or-none on failure* contract. If any element causes the call to throw an exception, **no class definition in that batch is installed**. This is not a rollback for transformer side effects or for previously succeeded batches; applications still need to manage versioning, side effects, retries, and behavioral verification.
