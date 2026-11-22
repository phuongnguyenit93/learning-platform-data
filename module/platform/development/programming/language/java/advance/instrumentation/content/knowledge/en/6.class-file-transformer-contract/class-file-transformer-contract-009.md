# IllegalClassFormatException and Transformer Exceptions Do Not Guarantee Preventing Class Loading

## 1. Why understand the ClassFileTransformer error contract?

In Java Instrumentation, a `ClassFileTransformer` receives class file data before the JVM defines, redefines, or retransforms a class. A transformer can return replacement bytecode, return `null` if it does not want to make changes, or encounter an error during analysis/transformation.

A misleading intuition is: **"A transformer throwing an exception means the JVM will abort the class loading operation."** Under the Java SE 17 `java.lang.instrument.ClassFileTransformer` contract, that is **false**. If `transform` throws an uncaught exception, **subsequent transformers are still called** and the JVM still **attempts** to perform the load/redefine/retransform. As far as selecting the output of the failing transformer is concerned, throwing an exception has the same effect as **returning `null`**.

Key points to distinguish clearly:

1. **`IllegalClassFormatException`** is a signal that a transformer can throw when it considers the **classfile input invalid**.
2. An exception from a transformer callback is **not a command to stop the JVM from loading the class**.
3. **`return null`**, **throwing from a transformer**, and **returning an invalid bytecode array** are three different behaviors.
4. The JVM can still fail when the **final bytecode is invalid**, or due to linkage errors, missing dependent classes, or class initialization errors.
5. If an operation must be rejected for policy reasons, **do not use transformer exceptions as a reliable access control mechanism**.

The goal of this article is to read the API contract accurately, know what is guaranteed and what is not, verify it yourself with Java 17+, and design fault-safe transformers.

## 2. Bytecode flow through multiple transformers

Suppose an agent registers two transformers, A then B, in the same ordering group:

~~~text
ClassLoader / JVM requests to define demo.Target
              |
              v
      original classfile bytes
              |
              v
       Transformer A
          /        \
     return bytes   throw exception / return null
          |                     |
      new bytes            bytes before A
          \                     /
           v                   v
                Transformer B
                     |
               bytes or null
                     |
                     v
               JVM checks bytes
                     |
           +---------+---------+
           |                   |
      valid bytes        invalid bytes
           |                   |
      define class    format/verification error
~~~

**Important semantics:**

- If a transformer **returns `null`**, it does not modify the bytecode; the next transformer is evaluated against the current bytes.
- If a transformer **returns a new `byte[]`**, its output becomes the input to the next transformer.
- If a transformer **throws an exception**, the JVM still calls the subsequent transformers and still attempts the corresponding class operation. In terms of the byte stream, the effect of this callback is the same as returning `null`.
- The JVM **attempting** to define a class does not mean **defining the class is guaranteed to succeed**. After the callbacks, the class file still has to be verified and linked according to JVM rules.
- Side effects performed by a callback before throwing an exception, such as logging or incrementing a counter, are not automatically rolled back by the JVM. "Same as `return null`" refers to the **transformation output**, not rolling back all Java side effects.

Ordering note in the general case: the specification divides transformers into **retransformation-incapable / retransformation-capable** groups and native transformers; within each group, ordering follows registration order. With **two Java transformers registered via `addTransformer(transformer)`** as in the demo below, both are in the same retransformation-incapable group and run in the order they were registered.

## 3. What is IllegalClassFormatException?

`java.lang.instrument.IllegalClassFormatException` belongs to the `java.instrument` module and extends `Exception`, so it is a **checked exception**. The `ClassFileTransformer.transform` method may declare `throws IllegalClassFormatException`.

Meaning according to the Javadoc: the transformer reports that **its input parameter** does not represent a valid class file. The cause may be corrupted original class bytes, or **a previous transformer** returning corrupted bytes.

~~~java
@Override
public byte[] transform(ClassLoader loader, String className,
        Class<?> classBeingRedefined, ProtectionDomain protectionDomain,
        byte[] classfileBuffer) throws IllegalClassFormatException {
    // If analysis finds the input is malformed:
    throw new IllegalClassFormatException("unexpected classfile input");
}
~~~

This is an **illustrative snippet**, not a standalone runnable Java class. In a production transformer, you should actually **inspect the data** before concluding the format is invalid; do not throw this exception unconditionally for every class.

**Effect:** The JVM ignores the transformation result of the throwing callback, continues calling subsequent transformers, and still attempts the load/redefine/retransform. `IllegalClassFormatException` helps tools and developers **identify/investigate format errors**; it is **not a condition that rejects class loading**.

The two statements below are different:

- **"Transformer A detected anomalous input and threw `IllegalClassFormatException`."** This is a signal from **A**, not the JVM's final verdict.
- **"The JVM could not define the class because the final class file is malformed."** This is a JVM class-checking error, which may manifest as **`ClassFormatError`**.

If the original class is genuinely corrupted and no transformer repairs it, A throwing `IllegalClassFormatException` does not save the class from failing later. Conversely, if the original class is valid but A throws an error due to a bug in A itself, the JVM can continue loading the class **normally** from the valid bytes.

## 4. Possible outcomes at the callback

| Behavior in `transform` | Remaining transformers | Does the JVM attempt the class operation? | Observable outcome |
|---|---|---|---|
| `return null;` | Yes | Yes | Class still loads if final bytes are valid |
| `throw new IllegalClassFormatException(...);` | Yes | Yes | This callback is ignored for bytes; class can still load |
| `throw new IllegalStateException(...);` | Yes | Yes | A callback runtime exception is not a class-blocking mechanism |
| `return transformedBytes;`, valid bytes | Yes, receives new output | Yes | Class can use the new bytecode if all checks succeed |
| `return malformedBytes;` | Yes, receives corrupted bytes | Yes | JVM may throw `ClassFormatError` or a corresponding verification/linkage error |
| Error in `premain` or `agentmain` outside the callback | Callback rules do not apply | Depends on agent startup mode | Agent initialization may fail according to its own rules |

**Do not equate "exception was ignored at transform" with "the entire JVM is immune to all errors".** A transformer can cause unsafe side effects, return bad bytes, or invoke code that causes class loading issues. The contract only guarantees how **callback exceptions** are handled and that the pipeline attempts to continue; it does not guarantee that the final application will always run.

## 5. Java 17+ experiment: callback fails yet the class still loads

We will create a startup agent with **two transformers**. The first transformer has three modes: throw `IllegalClassFormatException`, throw `IllegalStateException`, or **return malformed bytes**. The second transformer simply prints a marker that it was called and returns `null`. The application will call a method on `demo.Target`.

The example uses only JDK 17+, with no third-party libraries, and can run on Windows, Linux, or macOS as long as a full JDK is installed.

### 5.1. Project structure

~~~text
transformer-failure-lab/
├── agent.mf
├── src/
│   ├── agent/
│   │   └── demo/
│   │       └── FailureAgent.java
│   └── app/
│       └── demo/
│           ├── Target.java
│           └── Main.java
└── out/                    # created during build
    ├── agent/
    ├── app/
    └── failure-agent.jar
~~~

Only three Java files are needed; the agent and application code are compiled into **two separate class directories** to clearly separate responsibilities.

### 5.2. FailureAgent.java

Save at **`src/agent/demo/FailureAgent.java`**:

~~~java
package demo;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.IllegalClassFormatException;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class FailureAgent {
    public static void premain(String mode, Instrumentation inst) {
        inst.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(ClassLoader loader, String className,
                    Class<?> redefined, ProtectionDomain domain,
                    byte[] original) throws IllegalClassFormatException {
                if (!"demo/Target".equals(className)) {
                    return null;
                }

                System.out.println("first:" + mode);

                if ("checked".equals(mode)) {
                    throw new IllegalClassFormatException(
                            "demo format signal");
                }

                if ("runtime".equals(mode)) {
                    throw new IllegalStateException(
                            "demo runtime fault");
                }

                if ("badbytes".equals(mode)) {
                    return new byte[] { 0x01, 0x02, 0x03 };
                }

                return null;
            }
        });

        inst.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(ClassLoader loader, String className,
                    Class<?> redefined, ProtectionDomain domain,
                    byte[] bytes) {
                if ("demo/Target".equals(className)) {
                    System.out.println("second:called");
                }
                return null;
            }
        });
    }
}
~~~

**Analysis:**

1. Two transformers are registered **in order** using `inst.addTransformer(...)`, which defaults to retransformation-incapable.
2. The `"demo/Target".equals(className)` filter avoids accidentally processing JDK/agent classes. Class names in the callback use **forward slashes `/`** in JVM internal name form.
3. With **`checked`**, transformer A throws **`IllegalClassFormatException`** even though the demo's original bytes are valid. This is **intentional behavior to test error-handling rules**, not a format check pattern to use in production.
4. With **`runtime`**, transformer A throws **`IllegalStateException`**, an unchecked exception. It does not automatically turn into a load-abort command.
5. With **`badbytes`**, transformer A **returns** a three-byte array that is not a class file, to distinguish **corrupted output** from **throwing an exception**.
6. Transformer B prints **`second:called`** if it receives the callback for `Target`. If A throws an error, B must still be called by the JVM; if A returns corrupted bytes, B is also called with the bytes from A.
7. Transformer B returns `null`, so it does not change the bytes continuing down the pipeline.

**Why override the 5-parameter method?** Java 17 also supports the `transform(Module, ClassLoader, String, Class<?>, ProtectionDomain, byte[])` overload. The default implementation of the 6-parameter version delegates to the 5-parameter version if not overridden, so the example code is valid in Java 17.

Do not directly mutate the passed-in `original` or `bytes` array. The contract specifies that a transformer must **create a new byte array** if it wants to transform, and return `null` if there are no changes.

### 5.3. Target.java

Save at **`src/app/demo/Target.java`**:

~~~java
package demo;

public final class Target {
    public static String message() {
        return "TARGET-OK";
    }
}
~~~

This is the class the agent observes; it contains no instrumentation and does not call the agent directly.

### 5.4. Main.java

Save at **`src/app/demo/Main.java`**:

~~~java
package demo;

public final class Main {
    public static void main(String[] args) {
        System.out.println("main:" + Target.message());
    }
}
~~~

The `Target` class is used when `main` runs, **after** the startup agent's `premain` has finished registering the transformers.

### 5.5. Agent manifest

Save at **`agent.mf`**:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.FailureAgent

~~~

Keep the **trailing newline at the end of the file**. `Premain-Class` tells the Java launcher which class has `premain`. `Can-Retransform-Classes` is not needed because this exercise only tests **initial class loading**, without calling `retransformClasses`.

### 5.6. Compile and package

In the **`transformer-failure-lab`** directory, in Bash:

~~~bash
mkdir -p out/agent out/app
~~~

Or PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out/agent, out/app
~~~

The following JDK commands can be run in either environment while in the root directory:

~~~bash
javac --release 17 -d out/agent src/agent/demo/FailureAgent.java
javac --release 17 -d out/app src/app/demo/Target.java src/app/demo/Main.java
jar --create --file out/failure-agent.jar --manifest agent.mf -C out/agent .
jar --list --file out/failure-agent.jar
~~~

The JAR should contain the key entries:

~~~text
META-INF/
META-INF/MANIFEST.MF
demo/
demo/FailureAgent.class
~~~

The application classes are in **`out/app`**, while the agent is in **`out/failure-agent.jar`**. There is no need to make the application an executable JAR for this exercise.

### 5.7. Case A: throwing IllegalClassFormatException

Run:

~~~bash
java -javaagent:out/failure-agent.jar=checked -cp out/app demo.Main
~~~

**Stdout** of the demo:

~~~text
first:checked
second:called
main:TARGET-OK
~~~

**Evidence explanation:** Transformer A threw `IllegalClassFormatException`. Transformer B **was still called**. The `Target` class is valid, so the JVM can load and run it; `Main` prints **`TARGET-OK`**. The program exits successfully.

This result refutes the assumption that "throwing `IllegalClassFormatException` guarantees the `ClassLoader` will reject the class".

### 5.8. Case B: throwing a RuntimeException

Run:

~~~bash
java -javaagent:out/failure-agent.jar=runtime -cp out/app demo.Main
~~~

Stdout:

~~~text
first:runtime
second:called
main:TARGET-OK
~~~

The **`IllegalStateException`** thrown by transformer A **also does not block** transformer B or the loading of `Target` in the demo. This is a callback error, which does not mean the JVM sees the final classfile as malformed.

**Caution:** This result does not mean every severe error in a transformer can be treated as harmless. For example, out-of-memory errors, deadlocks, mutating global state, or a transformer emitting bad bytes can cause serious impact. The key Javadoc statement is that **an exception from a callback does not automatically create a fail-closed mechanism**.

### 5.9. Case C: returning non-class-file bytes

Run:

~~~bash
java -javaagent:out/failure-agent.jar=badbytes -cp out/app demo.Main
~~~

Beginning of the demo's stdout:

~~~text
first:badbytes
second:called
~~~

In this case there is **no** `main:TARGET-OK` line. On the tested HotSpot JDK, **stderr** contains:

~~~text
Exception in thread "main" java.lang.ClassFormatError: Truncated class file
~~~

followed by a stack trace; the process exits with a non-zero code. Exact messages may differ across JVMs/JDKs, so do not treat the full stack trace as fixed output.

**The difference:** A **did not throw `IllegalClassFormatException`** in this mode. A **returned corrupted bytes**. B was still called and returned `null`, so the corrupted bytes proceeded to the JVM verification step. The JVM could not define `Target` from that bytecode and reported **`ClassFormatError`**. The error comes from the **final classfile**, not from an exception signal in callback A.

### 5.10. Evidence table

| Agent mode | What does A do? | Does B run? | Does `main:TARGET-OK` appear? | Conclusion |
|---|---|---|---|---|
| `checked` | Throws `IllegalClassFormatException` | Yes | Yes | Callback exception does not block a valid class |
| `runtime` | Throws `IllegalStateException` | Yes | Yes | Unchecked callback exception is not fail-closed |
| `badbytes` | Returns malformed class bytes array | Yes | No | JVM may reject final bytes with `ClassFormatError` |

The experiment tests **initial class definition**. It does not require retransform or modifying an already active class.

## 6. Boundary between transformer errors and JVM errors

### 6.1. Do not conflate IllegalClassFormatException with ClassFormatError

| Characteristic | `IllegalClassFormatException` | `ClassFormatError` |
|---|---|---|
| Java type | Checked exception, extends `Exception` | Error, extends `LinkageError` |
| Where does it occur? | Transformer may throw when it considers input invalid | JVM may throw when the classfile used to define/retransform is invalid |
| Role | Diagnostic signal inside a callback | Reports class operation failure at the checking/definition layer |
| Blocks loading on its own? | No, only an error in that callback | Can cause the class operation itself to fail |
| How to catch/handle? | Declared in `transform` or handled inside the transformer | Usually a serious error requiring finding and fixing the classfile/transformer |

`ClassFormatError` is **not** an unchecked version of `IllegalClassFormatException`. You should not throw `ClassFormatError` in a transformer to control class loading; you must distinguish **errors caused by a callback** from **final bytecode errors** detected by the VM itself.

### 6.2. Errors occurring at other steps follow different rules

The `ClassFileTransformer.transform` contract does not cover every piece of code that can fail:

- **In `premain` of a startup agent:** an unhandled error can prevent the JVM from completing application startup.
- **In `agentmain` of an attached agent:** initialization rules differ; failures are typically reported back to the attach helper and do not by default terminate the target JVM, though side effects already performed by the agent may remain.
- **In ClassLoader or during linking:** `ClassNotFoundException`, `NoClassDefFoundError`, `VerifyError`, `UnsupportedClassVersionError`, `ClassCircularityError`, and other errors can occur independently of whether a transformer throws anything.
- **In `Instrumentation.retransformClasses`:** if the final bytes are invalid, the API may throw `ClassFormatError` or another specified error; if the retransform operation throws an error, the API documentation states **no classes in the set are retransformed**.
- **In application code when using the class:** initializer, null, race, or business logic errors can still occur after the class has been validly loaded.

The key takeaway is that **"throwing in a callback does not block loading" does not mean "loading cannot fail"**.

## 7. Multi-transformer chains and cascading errors

An application may be instrumented by multiple agents or libraries, so **transformer N's input is not necessarily the original bytes**. Application order changes the result:

~~~text
valid original bytes
    |
Transformer A: returns transformed bytes
    |
Transformer B: receives A's output
    |
Transformer C: receives B's output
    |
JVM verifies final bytes
~~~

Suppose A returns corrupted bytes. B checks them and throws `IllegalClassFormatException`. The JVM **does not stop the pipeline just because B threw an exception**. If no transformer repairs the current bytes, the JVM may still reject the final bytes. Conversely, if B merely hits a logic bug while the bytes from A are valid, the remaining transformers/JVM can still proceed normally.

The specification also stipulates **not modifying `classfileBuffer` directly**; to transform, create a new `byte[]`. Mutating the input array in place and then throwing an exception violates the contract, and you must not assume the JVM will restore the bytes to their pre-mutation state.

Another issue: **the same transformer instance should not be registered repeatedly**. The API allows it, but the documentation advises against it; duplicate callbacks can increase overhead or apply instrumentation twice. When tracking errors, record the transformer name, class, class loader, timestamp, agent version, and callback type.

## 8. Reasonable error-handling strategy in a transformer

### 8.1. Triage before deciding

| Situation | Behavior to consider |
|---|---|
| Class is outside instrumentation scope | Return `null` immediately without unnecessary bytecode parsing |
| Analysis succeeds and changes are needed | Create a valid new `byte[]`; return verified bytes |
| No need or unable to instrument this class | Return `null`, record a skip metric if needed |
| Detected genuinely malformed input classfile | May throw `IllegalClassFormatException` for diagnostics, but do not treat it as blocking the class |
| Internal bug while generating output | Log the cause within safe limits; do not emit corrupted bytes; consider returning `null` to keep the app running |
| Policy requires blocking class loading | Enforce control at a point with real rejection authority (build/deployment pipeline, environment, controlled class loader), not via transformer exceptions |

The API contract notes that a transformer may catch **`Throwable`** to avoid surprises from unchecked exceptions. However, in production application code you should not use a broad `catch(Throwable)` that **silently swallows all severe errors** such as out-of-memory errors. Organizations should clearly define recoverable error types, minimal logging, and how to safely disable the instrumenter.

### 8.2. Fail-open pattern and telemetry

**Fail-open** means: if **only the instrumenter layer fails**, the goal is to let **the valid original bytecode continue being processed by the JVM**; skip instrumentation rather than breaking the application. This is a deliberate design policy, not a guarantee that every error is recoverable.

Illustrative code used inside a transformer that already has a filter:

~~~java
try {
    byte[] result = performSafeRewrite(classfileBuffer);
    return result; // Must be a valid classfile, new array.
} catch (KnownRewriteException ex) {
    recordFailure(className, ex);
    return null; // Do not apply this callback's transformation.
}
~~~

**This is only an error-handling structure snippet**, not a standalone compilable program; `performSafeRewrite`, `KnownRewriteException`, and `recordFailure` are components to be implemented according to your bytecode library and telemetry system.

Design principles:

1. **Filter fast:** check class name, module, and loader before parsing. Avoid instrumenting the agent's own classes or its underlying libraries.
2. **Do not mutate the input buffer:** copy when needed, create new output, and ensure valid class structure.
3. **Catch scoped errors:** handle expected parser/rewrite errors; log enough information to investigate while rate-limiting logs because transformers can run very frequently.
4. **Do not rely on throwing to reject:** security controls must sit at a point with real rejection authority and be independently verifiable.
5. **Test the chain:** when multiple transformers exist, verify the outcome even when one callback fails.
6. **Measure instrumentation quality:** number of classes processed, number of classes skipped, exception counts, transform latency, and startup/runtime impact.
7. **Test both load and retransform if the agent supports it:** the same callback may encounter different bytes and redefinition validity rules.

Do not print full stack traces on every `transform` on the hot path; it can cause heavy I/O, class loading recursion, or obscure diagnostics when errors spike.

## 9. What changes in redefine and retransform?

The rule regarding callback exceptions still applies when a class is **redefined** or **retransformed**. However, the full workflow has different conditions:

- Only transformers registered with `canRetransform=true` receive a new callback during each retransformation. For incapable transformers, the JVM reuses their previous transformation result per the contract.
- If a callback throws during retransformation, **subsequent transformers are still called** and the JVM still attempts the operation. Do not interpret throwing as canceling the request.
- If the **final bytes** after all transformations are invalid, `retransformClasses` may report an error; the Javadoc specifies that when a retransform call throws an exception, **no classes in that request are retransformed**.
- The JVM enforces class structure change constraints. Even bytes that parse successfully may not be a **valid redefinition** of an already loaded class.
- On a class currently in use by threads, if retransformation succeeds, active frames may continue running the old bytecode while new invocations use the new bytecode.

Therefore, you must distinguish **transformer receives callback**, **transformer returns output**, **JVM verifies and applies output**, and **application observes new behavior**. These are distinct milestones, especially when errors occur.

## 10. Common misconceptions

**Misconception 1 — "Throw IllegalClassFormatException to reject a dangerous class."**  
Incorrect under the contract. The JVM continues calling subsequent transformers and attempts to load. To enforce policy, you need a different specified enforcement point.

**Misconception 2 — "If a transformer hits a RuntimeException, the whole JVM is sure to stop."**  
False. In the demo, the callback exception is handled per the contract and the class still loads. Do not infer that the application is always safe if the callback has side effects or other VM errors occur.

**Misconception 3 — "A ClassFormatError means a transformer threw IllegalClassFormatException."**  
Not necessarily. The input class bytes or **final output** may be invalid; an error detected by the JVM does not prove a callback threw the checked exception.

**Misconception 4 — "Returning null means nothing happened."**  
It only means **the callback did not provide replacement bytes**. The callback could still have logged, mutated state, spent time, or caused side-effect errors.

**Misconception 5 — "If A throws, B does not run."**  
Contrary to the documentation. The JVM still calls B and subsequent transformers in the pipeline.

**Misconception 6 — "Catching Throwable and staying silent is always safe."**  
Dangerous. Severe errors are not appropriate to ignore; at a minimum, you need classification, controlled logging, and an operational plan.

**Misconception 7 — "If a transformer returns bad bytes, the JVM automatically falls back to the original bytes."**  
There is no such general fallback rule. Returning corrupted bytes and throwing an exception are two different outcomes; the JVM may reject the operation at the verification step.

**Misconception 8 — "Every callback receives the same input bytecode."**  
False. Output from a previous transformer becomes input to the next transformer, unless the previous one returned `null` or threw an exception.

## 11. Verification exercises

### Exercise A — predict before running

Before running the three modes in section 5, write down your predictions:

1. Is `second:called` printed after `first:checked`?
2. Is `main:TARGET-OK` printed after `first:runtime`?
3. Does `badbytes` mode throw `IllegalClassFormatException` from Java code, or fail at the JVM class verification step?

Compare with actual stdout/stderr. Key result: **checked and runtime do not block on their own**, while corrupted bytes can cause the JVM to reject the class.

### Exercise B — have the second transformer validly modify the class

Extend transformer B using a reliable bytecode library such as ASM or Byte Buddy to replace a method while ensuring a valid class file. Run when A throws `IllegalClassFormatException`. If B returns valid bytes and the JVM accepts them, you can prove **A's exception does not prevent B from applying its transformation**. This is an advanced exercise; the library must be configured separately and is not part of the pure-JDK demo.

### Exercise C — test bad input and parse errors

In an isolated test environment, replace A's output with corrupted class file bytes as in `badbytes` mode. Ask: what does B receive? Which layer emits the final error? Explain why you should not rely on callback exceptions to predict verifier outcomes.

### Exercise D — outline a production strategy

Suppose the instrumenter parser fails on 2% of framework classes while the original classes remain valid. Design a way to log a rate-limited sample of errors, increment an error counter, and return `null` for classes that cannot be instrumented; then measure whether the application continues running and the remaining telemetry coverage.

### Short self-check

- **Does `IllegalClassFormatException` force the JVM to abort class loading?** No. It has the same effect as returning `null` for the failing callback.
- **Do subsequent transformers still run when a previous transformer throws?** Yes, per the contract.
- **Is `return new byte[]{1,2,3}` the same as `throw IllegalClassFormatException`?** No. Returning corrupted bytes can cause the JVM to reject the class with `ClassFormatError`.
- **Is `ClassFormatError` a checked exception from a callback?** No. It is a `LinkageError` that the JVM may throw when class bytes are invalid.
- **Does a callback exception guarantee the class will load successfully?** No. The JVM still needs to verify, link, and run the associated code.
- **What mechanism is appropriate for measuring transformer errors?** Record rate-limited counters/logs, distinguish callback errors from JVM class failures, and do not infer from a single signal.

## 12. Conclusion and references

**The `ClassFileTransformer` contract specifies that an exception thrown from `transform` is not a command to prevent class loading.** Subsequent transformers are still called and the load/redefine/retransform operation is still attempted by the JVM. **`IllegalClassFormatException`** is a diagnostic signal for anomalous classfile input, with the same effect as returning `null` in that callback.

To determine whether the final class can run, you must look at the **bytes after the entire pipeline**, the JVM verification steps, and other independent errors. Agent design should return `null` when a safe transformation is not possible, log errors in a controlled manner, test multiple chained transformers, and place class-rejection mechanisms at the proper control layer rather than depending on throws from a transformer.

**Java SE 17 official documentation:**

- [ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html) — callback ordering, `null`/exception contract, bytes, and the two `transform` signatures.
- [IllegalClassFormatException](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/IllegalClassFormatException.html) — purpose of the checked exception when classfile input is invalid.
- [Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html) — transformer registration, ordering, and errors in retransformation.
- [ClassFormatError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassFormatError.html) — JVM error when a malformed class file is detected.
