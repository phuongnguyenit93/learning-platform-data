# Writing a Transformer That Only Records the Target Class and Returns Null

## 1. Objective of the Experiment

In Java Instrumentation, the safest practical step before starting to modify bytecode is to create **a real Java agent**, register a `ClassFileTransformer`, accurately identify the **target class** when the JVM is defining it, **record an observable milestone**, and then **return `null`**.

The task **"Writing a transformer that only records the target class and returns null"** requires understanding two independent behaviors correctly:

1. **Observe:** only when the class name provided by the JVM matches the target class does the transformer print a log or record a diagnostic event.
2. **No-op transformation:** the transformer **always returns `null`**, even for the target class. According to the Java SE contract, `null` means **this transformer does not produce a replacement classfile**. The JVM continues the class loading process with the bytes from the previous step and the remaining transformers, if any.

This lesson builds an agent using **Java 17+**, without needing ASM, Byte Buddy, external libraries, or retransform/redefine permissions. The demo has two application classes: `demo.Unrelated` as a control **that is not logged**, and `demo.Target` as the class to observe. When creating two instances of `Target`, the target log appears **once** in the experiment because the JVM defines a class once per class loader.

You will learn:

- The signature and meaning of the parameters of `ClassFileTransformer.transform`.
- Why `"demo/Target"` is compared instead of `"demo.Target"`.
- How to register a transformer in `premain`.
- The difference between `return null`, `return originalBytes`, `return modifiedBytes`, and `throw`.
- Why recording a log does not mean the class has been successfully defined.
- How to compile for Java 17, create a manifest/JAR, and run with `-javaagent`, `-Xverify:all`.
- How to compare stdout **with** and **without** the agent to ensure the app's logic does not change.
- How to limit overhead, manage class loaders/modules, handle errors, and extend the demo in a controlled manner.

## 2. What Happens When the JVM Loads a Class?

A class is used by the JVM through stages: finding bytes from the class loader, transforming the classfile when transformers are present, verifying format/bytecode, defining the class, linking, and initializing at appropriate times.

In the demo:

~~~text
Application calls: new demo.Target()
                 |
                 v
Class loader prepares to define "demo/Target"
                 |
                 v
Instrumentation calls transformer
                 |
                 +--> Is className "demo/Target"?
                         |
                         +--> No: return null, do not print log
                         |
                         +--> Yes:
                               print "transform:seen=demo/Target"
                               print "transform:redefine=false"
                               return null
                 |
                 v
JVM continues defining the class from bytes unmodified by this transformer
                 |
                 v
Target.greet("Java") -> "Hello, Java"
~~~

**Distinguish the timing:** `transform` is called **before the class definition process completes**. In the callback, you know the JVM is processing the bytes of the target class; you **cannot confirm from that log alone that the JVM has verified and defined it successfully**. The subsequent proof in the demo is that the application creates an instance, calls a method, and receives the expected value.

If the JVM has **multiple agents/transformers**, one transformer returning `null` only states that **that transformer did not replace the bytes**. Another transformer can still modify the classfile. Therefore, do not claim that `return null` guarantees **the entire JVM** has no bytecode modification at all.

## 3. ClassFileTransformer Contract in Java 17

Public interface:

~~~java
java.lang.instrument.ClassFileTransformer
~~~

The five-parameter overload signature used by the demo:

~~~java
public byte[] transform(
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        ProtectionDomain protectionDomain,
        byte[] classfileBuffer);
~~~

In the complete Java source, you must import `java.lang.instrument.ClassFileTransformer` and `java.security.ProtectionDomain`. Since Java 9, the interface also has an overload taking a `Module` parameter, explained in section 12.

| Parameter | Meaning | Things to Note |
|---|---|---|
| `loader` | ClassLoader defining the class | Can be `null` for the bootstrap loader |
| `className` | Class name in **internal form** | Uses slashes: `demo/Target`; may need `null`-safe handling |
| `classBeingRedefined` | `Class<?>` if callback is due to redefine/retransform | **`null`** during initial class load |
| `protectionDomain` | ProtectionDomain of the class | Used for protection context control, not for guessing the class name |
| `classfileBuffer` | Input bytes of the classfile | **Do not modify this input array directly** |

### 3.1. Return Value

- `return null;` — **no transform** from the current transformer.
- `return newBytes;` — provides **a valid classfile** for the pipeline to continue; responsibility for valid generation/verification belongs to the transformer side.
- `return classfileBuffer;` — unnecessary in a no-op demo. This is not a better way to say "do not modify"; it returns a byte array and creates a different execution path than the no-op intent.
- Throwing `IllegalClassFormatException` or an unchecked exception — **not a guaranteed way to block class loading**. The Javadoc specifies that remaining transformers are still called; for a callback that throws an exception, handling is equivalent to `null`.

For this practical exercise, the expected answer is:

~~~java
if ("demo/Target".equals(className)) {
    System.out.println("transform:seen=" + className);
}
return null;
~~~

The snippet above only illustrates the logic portion and does not contain the full class/manifest. **Do not** modify `classfileBuffer`, no bytecode parser is needed, do not rename methods or add fields.

### 3.2. Returning Null Does Not Mean "Skip Loading the Class"

It is easy to mistake `return null` as a kind of "forbid the JVM from loading this class". The actual meaning is **the transformer does not submit replacement bytes**. The JVM still attempts to define the class using the pipeline's bytes. If the final bytes are valid and class loading conditions are met, the class is still loaded and the application continues.

In the demo, even though `Target` is recorded and the callback returns null, the `Target.greet` method runs normally, producing the exact same result as without the agent.

## 4. Scoped Design: One Target, Silence for the Rest

The lesson uses a fixed class name:

~~~text
demo.Target           Binary name in Java source
demo/Target           Internal name in ClassFileTransformer
Ldemo/Target;         Descriptor representing reference type in JVM
demo/Target.class     Class entry file name in JAR/directory
~~~

Do not put `demo.Target` as-is into `className.equals(...)`. When the callback receives `"demo/Target"`, a dot-format comparison returns false and the agent will **not print the log**.

Write the condition safely:

~~~java
if (!"demo/Target".equals(className)) {
    return null;
}
~~~

Placing the literal on the left prevents the code from throwing `NullPointerException` if `className` is null. For non-target classes, the transformer **does not log** and returns `null` immediately.

Other extension directions might observe namespaces, packages, or class loaders, but that is unnecessary in the basic lab. Keeping the filter as specific as possible makes comparison easier.

### 4.1. Why Create Unrelated?

If there is only one class `Target`, a single log appearing does not prove the filter refrains from logging other classes. Therefore, the application intentionally loads `demo.Unrelated` **before** `demo.Target`. Output with the agent only contains the line `transform:seen=demo/Target`, with no `transform:seen=demo/Unrelated` line.

### 4.2. Why Create Two Instances of Target?

To distinguish **class loading** from **object creation**. A class is defined by the JVM by an identity consisting of its binary name and defining class loader, not redefined every time `new` is called.

In the experiment, two `new Target()` objects on the same application class loader result in the transformer seeing `demo/Target` **once**, because the callback is invoked on the first class definition. This is not a rule that "every JVM will log exactly once forever": a class with the same name can be defined by another class loader, or an agent configured to redefine/retransform can trigger the callback again depending on conditions.

## 5. Lab Structure

Create the directory:

~~~text
target-only-null-agent/
├── agent.mf
├── src/
│   ├── agent/
│   │   └── demo/
│   │       └── agent/
│   │           └── TargetOnlyAgent.java
│   └── app/
│       └── demo/
│           ├── Main.java
│           ├── Target.java
│           └── Unrelated.java
└── out/                      # generated after build
    ├── agent/
    ├── app/
    └── target-only-agent.jar
~~~

Maven or Gradle is not needed for this experiment. `javac` and `jar` from the JDK are sufficient.

**Verified environment:** code compiled with `javac 24.0.2 --release 17`, run with `java 24.0.2 -Xverify:all`. Because the source uses the `java.lang.instrument` API already present in Java 17, it can run on compatible JDK 17+; for production, integration tests must be run on the exact JDK/vendor you support.

## 6. Complete Agent: Log Target Only and Return Null

File **`src/agent/demo/agent/TargetOnlyAgent.java`**:

~~~java
package demo.agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class TargetOnlyAgent {
    public static void premain(
            String args, Instrumentation inst) {

        System.out.println("agent:premain");

        inst.addTransformer(
                new TargetOnlyTransformer(),
                false);

        System.out.println("agent:registered");
    }

    static final class TargetOnlyTransformer
            implements ClassFileTransformer {

        @Override
        public byte[] transform(
                ClassLoader loader,
                String className,
                Class<?> classBeingRedefined,
                ProtectionDomain domain,
                byte[] originalBytes) {

            if (!"demo/Target".equals(className)) {
                return null;
            }

            System.out.println(
                    "transform:seen=" + className);

            System.out.println(
                    "transform:redefine="
                    + (classBeingRedefined != null));

            return null;
        }
    }
}
~~~

This is **complete, self-compilable Java source** using JDK 17+. It does not import `jdk.internal.*`, ASM, Byte Buddy, or any external library.

### 6.1. Explaining Each Block

**`premain(String, Instrumentation)`**

- Is the startup Java agent entry point when the JVM reads `Premain-Class` from the manifest.
- The JVM itself supplies the `Instrumentation` object; the application does not `new Instrumentation()`.
- The `agent:premain` log confirms the entry point was called.
- `addTransformer(..., false)` registers a **non-retransform-capable** transformer; sufficient to observe the target class when it is loaded in the demo.
- The `agent:registered` log only appears after the registration call completes. This is a registration milestone, **not proof that the target has been loaded**.

**`TargetOnlyTransformer`**

- Placed as a nested static class so the lab only needs one agent source file.
- Implements `ClassFileTransformer` using the five-parameter overload.
- Receives `className` in internal name form, matching `demo/Target` exactly.
- When it does not match, returns null immediately without logging.
- When it matches, logs the class name and checks `classBeingRedefined != null`.
- Even for the target class, it still **`return null`** at the end: does not replace the class's bytes.

**`classBeingRedefined` in the demo**

Because the transformer is called on the **first load**, this variable is null; it logs `transform:redefine=false`. If the callback comes from a redefine or retransform (in a differently designed agent), the variable may be non-null. This log cannot be used to tell whether the JVM has finished verifying the classfile.

### 6.2. Why Is Can-Retransform-Classes Not Needed?

`inst.addTransformer(transformer, false)` registers a transformer with `canRetransform=false`. Neither `retransformClasses` nor `redefineClasses` is called. Therefore the manifest does not need:

~~~text
Can-Retransform-Classes: true
Can-Redefine-Classes: true
~~~

The two lines above are only for comparing capabilities **not required** in the lab, and must not be added to the example's manifest. If later you want to observe already-loaded classes via retransformation, you must design it separately and check both VM support and manifest capabilities.

### 6.3. Should You Keep the Transformer Object to Remove It Later?

In the lab, the transformer is registered only once and lives until the JVM exits, so no reference field is needed. In a real application, if you want `inst.removeTransformer(transformer)`, you must keep a reference to **the exact instance registered**. Creating another `new TargetOnlyTransformer()` will not remove the old transformer.

At the same time, because class loading can be concurrent, callbacks may still appear for a short time after `removeTransformer`. The API does not guarantee that removing a transformer rolls back any previously transformed classes—in the lab no bytes are transformed, so no class rollback is needed either.

## 7. Demo Application: Target and Unrelated

File **`src/app/demo/Target.java`**:

~~~java
package demo;

public final class Target {
    public String greet(String value) {
        return "Hello, " + value;
    }
}
~~~

File **`src/app/demo/Unrelated.java`**:

~~~java
package demo;

public final class Unrelated {
    public String ping() {
        return "OK";
    }
}
~~~

File **`src/app/demo/Main.java`**:

~~~java
package demo;

public final class Main {
    public static void main(String[] args) {
        System.out.println("main:start");

        System.out.println(
                "main:other=" + new Unrelated().ping());

        System.out.println("main:before-target");

        Target first = new Target();

        System.out.println(
                "main:result=" + first.greet("Java"));

        System.out.println(
                "main:second="
                + new Target().greet("World"));

        System.out.println("main:end");
    }
}
~~~

**Intentional order:**

1. `main:start` proves application main started **after `premain`**.
2. `new Unrelated()` asks the JVM to load the control class; the transformer returns null **without logging**, because it is not `demo/Target`.
3. `main:before-target` serves as a timing marker before the target class is instantiated.
4. The first `new Target()` triggers class loading if the class has not been defined previously.
5. The transformer observes the target, prints `transform:seen=demo/Target`, and then returns null.
6. `greet("Java")` still returns `Hello, Java`.
7. The second `new Target()` does not automatically cause the JVM to redefine the same class, so it does not print another target hit in the lab.
8. `main:end` confirms the program finishes normally.

Because the demo relies on class loading order, run it from a **fresh JVM** and do not add another agent or other initialization code that preloads `Target` before `Main` if you want exact stdout.

## 8. Manifest: Required for -javaagent to Find premain

File **`agent.mf`**:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.TargetOnlyAgent

~~~

**Important:**

- `Premain-Class` contains the **binary class name** with dots: `demo.agent.TargetOnlyAgent`, different from the internal class name `demo/Target` inside the transformer.
- The manifest needs proper newlines, and in the lab version an extra trailing blank line is used.
- The Java agent JAR must contain both `TargetOnlyAgent.class` and the nested `TargetOnlyAgent$TargetOnlyTransformer.class`. `jar -C out/agent .` bundles both properly.
- `Main-Class` is not needed for the agent JAR, because the application runs separately via `-cp out/app demo.Main`.
- `Agent-Class` is not needed because the demo does not support dynamic attach.
- `Can-Redefine-Classes` or `Can-Retransform-Classes` are not needed as explained.

**Avoid a very practical pitfall:** an agent source that compiles successfully but whose final JAR lacks the right `Premain-Class` still causes `java -javaagent:...` to fail **before the application runs**. Always inspect the actual JAR.

## 9. Step-by-Step Build with javac, jar

Stand in the root directory `target-only-null-agent`.

If using Bash:

~~~bash
mkdir -p out/agent out/app
~~~

If using PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out/agent, out/app
~~~

Compile the **agent** (Java 17 target):

~~~bash
javac --release 17 -d out/agent src/agent/demo/agent/TargetOnlyAgent.java
~~~

Compile the **application**:

~~~bash
javac --release 17 -d out/app src/app/demo/Main.java src/app/demo/Target.java src/app/demo/Unrelated.java
~~~

Package the agent:

~~~bash
jar --create --file out/target-only-agent.jar --manifest agent.mf -C out/agent .
~~~

**No need to add the application to the agent JAR.** The application uses classpath `out/app`, and the agent uses a separate JAR. This makes the role of `-javaagent` versus app classes clear.

Inspect the JAR contents:

~~~bash
jar --list --file out/target-only-agent.jar
~~~

Expected key entries:

~~~text
META-INF/
META-INF/MANIFEST.MF
demo/
demo/agent/
demo/agent/TargetOnlyAgent.class
demo/agent/TargetOnlyAgent$TargetOnlyTransformer.class
~~~

The JAR may have additional directory entries or a different order depending on the tool; do not exact-match the entire list. What is mandatory is that **the manifest and agent classes are present**.

### 9.1. Inspecting the Actual Manifest

On systems with `unzip`:

~~~bash
unzip -p out/target-only-agent.jar META-INF/MANIFEST.MF
~~~

If `unzip` is not available, use `jar --extract` in a **temporary directory**:

~~~bash
jar --extract --file out/target-only-agent.jar META-INF/MANIFEST.MF
~~~

This command writes `META-INF/MANIFEST.MF` into the working directory; therefore **it should be run in a temporary inspection directory** to avoid overwriting existing paths. Read the extracted file and verify `Premain-Class: demo.agent.TargetOnlyAgent`.

### 9.2. Scanning JDK Internal Dependencies

~~~bash
jdeps --jdk-internals out/target-only-agent.jar
~~~

The demo agent only uses public APIs `java.lang.instrument`, `java.lang`, and `java.security`, without depending on internal ASM or JDK internal APIs. The `jdeps` tool helps detect static dependencies, but does not replace runtime testing.

## 10. Control 1: Running the Application Without the Agent

Run:

~~~bash
java -Xverify:all -cp out/app demo.Main
~~~

**Exact tested stdout:**

~~~text
main:start
main:other=OK
main:before-target
main:result=Hello, Java
main:second=Hello, World
main:end
~~~

This establishes the baseline:

- `Unrelated.ping()` returns `OK`.
- The two calls to `Target.greet` return `Hello, Java` and `Hello, World` respectively.
- There are no lines starting with `agent:` or `transform:`.
- The program exits normally, with no verifier errors.

The baseline is an essential condition for evaluating whether the agent changes behavior. If the application logic is already wrong without the agent, not all errors should be blamed on the transformer.

## 11. Control 2: Running the Same Application With -javaagent

Run:

~~~bash
java -Xverify:all -javaagent:out/target-only-agent.jar -cp out/app demo.Main
~~~

**Exact tested stdout:**

~~~text
agent:premain
agent:registered
main:start
main:other=OK
main:before-target
transform:seen=demo/Target
transform:redefine=false
main:result=Hello, Java
main:second=Hello, World
main:end
~~~

### 11.1. Before/After Comparison

| Criterion | Without Agent | With Agent |
|---|---|---|
| `agent:premain` log | No | Yes |
| `agent:registered` log | No | Yes |
| `transform:seen=demo/Target` log | No | Yes, **once** in the lab |
| Log for `demo/Unrelated` | No | No |
| `main:other` | `OK` | `OK` |
| `Target.greet("Java")` | `Hello, Java` | `Hello, Java` |
| `Target.greet("World")` | `Hello, World` | `Hello, World` |
| Normal exit | Yes | Yes |
| Bytecode modification by this transformer | None | **None** (`return null`) |

**Evidence that the practical exercise meets requirements:**

1. `premain` runs and registers the transformer before `main` starts.
2. `demo.Unrelated` is created **without a corresponding transformer log**, confirming the filter stays silent for other classes.
3. When the JVM defines `demo.Target`, the callback logs the exact internal name.
4. `classBeingRedefined == null` on initial load → `transform:redefine=false`.
5. Both `Target` objects still run the original logic correctly; the transformer does not supply replacement bytes.
6. With one defining class loader, `Target` is defined once even though the code creates two instances.

Do not print `class:transformed=true` in the lab. A more accurate log is **observed/seen**; this class **was recorded**, not rewritten by the transformer.

## 12. Since Java 9: Overload With Module and Compatibility

Java 17 `ClassFileTransformer` has two default overloads of `transform`. In this lesson, we override the **five-parameter** version:

~~~java
byte[] transform(
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        ProtectionDomain protectionDomain,
        byte[] classfileBuffer);
~~~

Since Java 9, the **six-parameter** overload adds `Module`:

~~~java
byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        ProtectionDomain protectionDomain,
        byte[] classfileBuffer);
~~~

In Java SE 17, the default implementation of the `Module` overload **delegates back to the five-parameter overload**. Therefore, a demo agent overriding the five-parameter method still observes classes on modern JVMs, even when the VM can provide module information.

**The following snippet only illustrates upgrading the observation approach** (do not replace the entire demo source):

~~~java
@Override
public byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        ProtectionDomain domain,
        byte[] originalBytes) {

    if (!"demo/Target".equals(className)) {
        return null;
    }

    String moduleName =
            module != null && module.isNamed()
            ? module.getName() : "unnamed";

    System.out.println("target-module=" + moduleName);
    return null;
}
~~~

If you override the six-parameter overload, you can read `module` directly. However, **do not assume** the JVM will call both overloads: the default 6-arg only forwards to 5-arg when 6-arg is not overridden. Choose **one** clear organization style and test the callback properly.

### 12.1. Class Loader Is Part of Identity

Two different class loaders can define **two classes with the same binary name `demo.Target`**. A filter using only `className` may record both. In the lab there is only one application class loader, so there is exactly one hit.

For a production agent, if you want to observe **a specific class identity**, consider combining:

- Internal class name;
- `ClassLoader` identity and origin/code source;
- `Module` for named modules;
- artifact/packaging source if policy allows;
- load timing vs retransform/redefine.

Do not call `loader.toString()` unconditionally: `loader` can be null if bootstrap, and complex `toString`/formatting inside a callback can trigger other class loading.

### 12.2. If className Is Null or During Bootstrap Phase

Write `"demo/Target".equals(className)` safely against null. Do not log blindly on every invocation because the transformer receives many system classes during JVM bootstrap; logging can suffer from reentrancy, performance overhead, or initialization-order issues.

## 13. How Does Returning Null Differ From Other Options?

### 13.1. Return null — No Change From the Current Transformer

~~~java
@Override
public byte[] transform(
        ClassLoader loader, String className,
        Class<?> classBeingRedefined,
        ProtectionDomain domain, byte[] originalBytes) {

    if ("demo/Target".equals(className)) {
        System.out.println("observed-target");
    }
    return null;
}
~~~

This is a snippet inside a class implementing `ClassFileTransformer`, not a standalone program. `null` tells the JVM there is no replacement classfile from this transformer.

### 13.2. Return originalBytes — Unnecessary and Misleading

~~~java
return originalBytes;
~~~

This supplies **the input byte buffer as the result**, instead of using the special value `null` to signal no transformation. It is unnecessary in the lab; it is better to always return null when you do not actually generate a new classfile.

Furthermore, **do not mutate `originalBytes`**; if a transformer modifies the input directly to "test" and then returns null, you have violated the non-mutating input contract. When real transformation is needed, use a valid new output array, and test the verifier and classfile semantics.

### 13.3. Return modifiedBytes — A Different Problem

~~~java
return transformedClassfileBytes;
~~~

This is pseudocode: a `transformedClassfileBytes` variable containing a complete classfile is required. To produce new bytes, you can use OW2 ASM, Byte Buddy, or Java `java.lang.classfile` from JDK 24+, but **that is not the goal of this lesson**.

Going from observing the target to transforming bytecode is a different quality step: you must preserve stack maps, methods, exception semantics, class loader/module visibility, and rules against changing schema when a class is already loaded.

### 13.4. Throw — Not a Supported Way to Reject a Class

The Javadoc specifies that a transformer callback throwing an uncaught exception is equivalent to returning null for that transformer; the JVM still tries the remaining steps. Therefore, `throw new RuntimeException(...)` to "block the target class" misses the mark.

The practical exercise **does not intentionally throw exceptions** in the callback, because it only needs to record the class name and return null.

## 14. Notes on Class Loading, Retransformation, and Redefinition

### 14.1. Classes Already Loaded Before the Transformer Is Registered

`addTransformer` does not mean the JVM will invoke the callback again for **all previously loaded classes**. A transformer generally receives **future** class definitions and eligible redefine/retransform operations.

If `demo.Target` was already loaded before you registered the transformer, subsequent `new Target()` calls do not necessarily trigger a new callback. That is a very common reason learners think their filter is wrong, when in reality **registration happened too late**.

With `-javaagent` and `premain`, application code `Main.main` only starts after the agent entry point has returned. Thus the demo is able to catch the first load of `Target`, provided no other code loads it beforehand.

### 14.2. Observing Already-Loaded Classes Is a Different Task

To retransform an already-loaded class, you cannot just blindly change `false` to `true`:

- The manifest needs `Can-Retransform-Classes: true`.
- The JVM must report `inst.isRetransformClassesSupported() == true`.
- The transformer must be registered with `addTransformer(transformer, true)`.
- The agent needs the exact `Class<?>` object and the class must be modifiable.
- Call `inst.retransformClasses(targetClass)` when permitted.
- Schema/VM restrictions still apply; `return null` is still a no-op from the transformer.

In Java Instrumentation, `addTransformer(transformer, false)` **does not receive callbacks when a class is retransformed** in a retransformation-capable manner, though it can still participate in the class load and redefinition paths per the contract. You cannot take the log count from the demo and infer `retransformClasses` counts in another agent.

### 14.3. If the Class Is Defined, Is the Method Called?

The transformer log `transform:seen=demo/Target` is only a **class load path** milestone. A class can be loaded without being initialized, without instantiating objects, or without executing methods. Conversely, a class loaded before you registered the transformer can execute many times without any log.

Distinguish telemetry:

~~~text
transform:seen=demo/Target      -> JVM prepares to process class bytes
main:result=Hello, Java        -> method executed and returned result
main:second=Hello, World       -> method called again, class not redefined
~~~

Do not call a transformer that only logs class names a **method profiler**: it does not count invocations, latency, exceptions, or CPU. Measuring method execution requires different instrumentation/monitoring points.

## 15. Why Does a No-Op Exercise Have Technical Value?

### 15.1. Verifying Packaging Before Modifying Bytecode

Before bringing ASM/Byte Buddy into an agent, simply recording the target class is enough to verify:

- The JVM read `Premain-Class` in the agent JAR correctly;
- `premain` executed successfully;
- the transformer was registered;
- application code loads the expected class **after registration**;
- the internal name is correct;
- the loader/module path does not cause the target class to be loaded from a different source;
- the agent causes no obvious behavioral differences in tests.

A no-op transformer is a **pipeline smoke test**, not proof that a future bytecode transformer will be correct.

### 15.2. Can Be Used in Class Loading Diagnostic Tools

When a plugin library uses multiple class loaders, a no-op transformer can record where and when the target class is loaded. It is a simple way to find why a class the agent wants to patch is not getting a callback: wrong binary name, class loaded too early, or target residing in an unexpected loader.

However, **logging directly inside the callback** should be limited to experiments; production needs low-overhead event recording, bounded buffers, or a logging system that does not itself cause classloading recursion.

### 15.3. No ASM/JDK Internal Dependencies

The demo code uses only:

~~~text
java.lang.instrument.Instrumentation
java.lang.instrument.ClassFileTransformer
java.security.ProtectionDomain
java.lang.String / System / ClassLoader
~~~

So the agent JAR can be small, needs no shaded bytecode library, and needs no `--add-exports` to access JDK internal packages. This is an advantage when building initial test/diagnostic suites.

## 16. Common Errors and Diagnostics

| Symptom | Likely Cause | How to Check |
|---|---|---|
| JVM reports missing `Premain-Class` | Final JAR's manifest is incorrect | Extract `META-INF/MANIFEST.MF` from the released JAR |
| `ClassNotFoundException` for agent entry | Wrong `Premain-Class` name or missing class in JAR | `jar --list --file ...` |
| Only `main:start` is seen, no `agent:premain` | Run command missing `-javaagent` or agent not loaded | Print the actual command line |
| `agent:registered` present but no target hit | Target loaded earlier, wrong filter, or app does not use target | Check class-loading timing and `demo/Target` |
| Callback has logs for `Unrelated` | Filter written incorrectly or log placed outside condition | Place early return before the log statement |
| Log prints `demo.Target` but filter `demo/Target` does not match | Name format confusion | Use internal slash name |
| `NullPointerException` from `className.equals(...)` | `className` can be null | Change to `"demo/Target".equals(className)` |
| Log repeats multiple times despite one source class | Multiple defining loaders or redefine/retransform | Log loader identity and callback lifecycle |
| Thousands of logs per request | Filter too broad or excessive class loading | Narrow the target, use sampling/buffering |
| Probe prints but Target method fails | App bug or another transformer; no-op does not edit bytes | Compare baseline, full stack trace, all agents |
| `VerifyError` after registering only a no-op transformer | Possibly another transformer or corrupted source classfile | Identify final bytes and list of agents |
| Running on Java 17 throws `UnsupportedClassVersionError` | Agent/app compiled with newer JDK without `--release 17` | Use `javap -verbose` to check major version, rebuild |
| `-javaagent` makes JVM abort before main | Manifest/entrypoint error or `premain` threw uncaught exception | Read stderr/root exception |
| Still seeing a callback after `removeTransformer` | Race with concurrent class loading | Javadoc states callbacks can arrive after removal |
| `Target` not seen even though callback works on other classes | JVM may have loaded Target earlier or different class name/loader | Use control logs and class loader introspection |
| Returning `originalBytes` in every callback | No-op but reports as if new bytes were provided | Use `return null` for clearer intent |

### 16.1. Debugging Wrong Class Names

To find the Java source name of the target:

~~~java
System.out.println(Target.class.getName());   // demo.Target
~~~

This example **is placed in code that has permission to import or access `Target`**; do not reference `Target.class` directly inside `premain` just to find its name, because referencing it can **load the target class before the transformer is registered**.

In the callback, always compare against the internal name passed by the JVM, such as `demo/Target`.

### 16.2. Debugging Classloaders With Multiple Modules/Plugins

When extending the code, you can log classloader identity but avoid calling complex methods inside the callback. Research-only example:

~~~java
if ("demo/Target".equals(className)) {
    String loaderKind = loader == null
            ? "bootstrap"
            : loader.getClass().getName();
    System.out.println("target-loader-kind=" + loaderKind);
}
return null;
~~~

This is an **illustrative snippet**, placed inside `transform`. It identifies the **loader kind**, without distinguishing two instances of the same class loader type. If you truly need identity, you can use `System.identityHashCode(loader)` and log PID/context; however, that number is not stable across runs, so avoid putting it in the lab's exact stdout.

### 16.3. Do Not Scan All of getAllLoadedClasses Inside transform

`Instrumentation.getAllLoadedClasses()` can be useful for diagnostics, but scanning all classes **inside every callback** is very expensive and can cause concurrency/initialization issues. If a snapshot is needed, take it at a controlled operational point outside the hot path.

## 17. Safety, Performance, and Production Hardening

### 17.1. Transformer Is Called on the Class-Loading Path

A JVM can define thousands of classes at startup. If every callback creates complex formatters, makes network queries, or logs synchronously, you can slow down startup or cause classloading recursion. This lesson **filters before logging**, and prints very few lines.

Practical recommendations:

1. Return `null` as early as possible for non-matching classes.
2. Avoid loading large logging/JSON libraries inside the callback.
3. Do not intentionally block, sleep, acquire dangerous global locks, or open network connections inside the callback.
4. Avoid instrumenting the agent's own and helper classes unless explicitly designed.
5. If multiple threads/class loaders define the target name concurrently, do not assume the callback runs on a single thread.
6. If recording counters, use thread-safe structures like `AtomicLong` when needed and distinguish class-name hits from identity.
7. Do not log sensitive data from `classfileBuffer`; the demo code does not need to read the buffer.
8. Measure actual cost in the target application instead of assuming a no-op has zero overhead.

### 17.2. Observation Does Not Modify Bytecode, but Logging Is Still a Side Effect

`return null` ensures this transformer **does not change class bytes**, but `System.out.println` still causes **I/O side effects** and latency. Thus "no-op transformer" here means **no-op with respect to bytecode**, not zero performance impact or no logs.

A high-throughput application should use an appropriate queue/buffer, sampling, or JFR mechanism instead of printing every hit to stdout.

### 17.3. Do Not Use Throw to Forbid Loading

If a transformer throws an exception upon seeing a disallowed class, the Javadoc does not guarantee the class will not be defined. Exception handling in the contract is equivalent to returning `null` for that callback. If the problem is security/enforcement, a proper policy mechanism at the right layer is needed, not using "transformer throw" as a policy gate.

### 17.4. Do Not Assume One Agent Is All Transformations

When running multiple `-javaagent` flags, Java Instrumentation has a transformer invocation order. `return null` only omits changes from the current transformer; another transformer can still modify bytes. When investigating behavioral differences, record **all agents** and transformer ordering, rather than looking only at the target-only agent.

### 17.5. Java 17 Minimum and Portability

This pattern uses the five-parameter transformer overload available in Java 17 and classfile instrumentation features of `java.instrument`. The command `javac --release 17` produces classfile major version **61** for the demo sources; compatible JDK 17+ runtimes can load them. If a JVM vendor/version has specific Java agent restrictions, check your project's runtime matrix.

## 18. Guided Extension Exercises

### Exercise A — Misconfiguring the Filter

Change the condition to:

~~~java
if (!"demo.Target".equals(className)) {
    return null;
}
~~~

Run again. Why is `transform:seen=demo/Target` no longer there? **Answer:** the JVM passes the internal name `demo/Target` with a slash, not the binary name `demo.Target`. Restore the correct condition.

### Exercise B — Logging the Control Class

Move `System.out.println("transform:seen=" + className)` **outside the target condition**, then run again. Observe the log line count surge because the JVM loads many classes. Why does this violate the requirement "record only the target class"? Restore the early return.

### Exercise C — return null or return originalBytes?

Replace `return null` with `return originalBytes` in an isolated test copy. The business outcome may remain the same, but why should null still be used for no-op? **Answer:** it is the explicit contract for "no transform"; no array needs to be returned, and do not operate on the input buffer.

### Exercise D — Creating Many Objects

Increase to 100 calls of `new Target().greet("Java")` in the same process/class loader. Predict how many times `transform:seen=demo/Target` will be printed. **In this lab**, still once if the class is defined once and there is no redefine/retransform; 100 objects do not mean 100 class definitions.

### Exercise E — When Target Is Already Loaded

Design a separate test where the `Target` class is loaded **before registering the transformer** (without overwriting the working demo), then just create more objects. Why might the callback not be called? Explain the limitation of `addTransformer(..., false)` and the retransform approach if genuinely needed.

### Exercise F — Filtering by Class Loader

Adjust the six-parameter transformer to log only when `className` equals `demo/Target` **and** the defining loader matches a known loader. Why is verifying the loader necessary in apps with plugin isolation? Explain the case of two classes with the same name defined by two loaders.

### Exercise G — Checking the Real Manifest

Intentionally change `Premain-Class` to a class name not present in the agent JAR, and repackage in a test directory. Run `-javaagent`: does the JVM reach `main:start`? Restore the manifest and re-verify. **Do not test by replacing a production agent** with an intentionally broken artifact.

### Exercise H — Thread-Safe Hit Counter

Replace direct logging with an `AtomicLong` counting how many times the callback sees the target, still returning `null`. Explain that the counter measures **class transformation callbacks**, not `greet` call counts. Place counter publication safely, avoiding scanning counters inside the transformer while the JVM is loading.

### Exercise I — Extending to Multi-Target

Create a set of internal names allowed to be observed:

~~~java
Set<String> allowedNames = Set.of(
        "demo/Target", "demo/Unrelated");
~~~

This is an **illustrative snippet** (requires importing `java.util.Set` and placing the variable in the class). Replace the condition with `allowedNames.contains(className)`. At that point it no longer follows the single-target prompt, but it helps understand how to evolve filters in a controlled way. By default, still log only `demo/Target`.

### Review Questions

1. **What does `ClassFileTransformer.transform` returning `null` mean?** — That transformer does not provide a replacement classfile.
2. **Does `return null` block class loading?** — No.
3. **Does the callback name for `demo.Target` have dots or slashes?** — `demo/Target`.
4. **What is `classBeingRedefined` on initial class load?** — `null`.
5. **Can `loader` be null?** — Yes, for the bootstrap loader.
6. **Why does the target log appear only once despite two `new Target` calls?** — One class definition for the same loader in the lab.
7. **Which name does `Premain-Class` in the manifest use?** — `demo.agent.TargetOnlyAgent`.
8. **Is `Can-Retransform-Classes` needed for the lab?** — No.
9. **Does `-Xverify:all` turn a no-op agent into a bytecode modifier?** — No.
10. **Does a log inside the callback mean the JVM has defined the class successfully?** — Not enough evidence.
11. **With multiple transformers, does one transformer returning `null` guarantee none of them modified the class?** — No.
12. **Does removing a transformer automatically undo bytecode installed by another agent?** — No.

## 19. Completion Checklist and Official Documentation

### Before Running

- [ ] There is exactly **one target class** `demo.Target` to observe.
- [ ] The transformer compares `"demo/Target".equals(className)`.
- [ ] Non-target: **do not log** and `return null`.
- [ ] Target: log the class name clearly but still `return null`.
- [ ] Do not mutate `classfileBuffer`, do not return replacement bytes.
- [ ] The agent uses `premain` and `addTransformer(..., false)`.
- [ ] `Premain-Class: demo.agent.TargetOnlyAgent` is present in the final JAR manifest.
- [ ] Agent and app output directories are separate.
- [ ] Compiled with `--release 17` if the minimum runtime is Java 17.
- [ ] Ensure `-javaagent` appears in the JVM command running the app.

### When Testing

- [ ] Run the baseline **without agent**, record stdout/exit code.
- [ ] Run **with agent** using `-Xverify:all`.
- [ ] Verify the order `agent:premain`, `agent:registered`, `main:start`.
- [ ] Verify the target hit appears **after `main:before-target`** and before the method call lines in the lab.
- [ ] Verify `transform:seen=demo/Target` appears exactly **once** in the isolated lab.
- [ ] Verify `demo.Unrelated` **is not logged**.
- [ ] Verify the two values `Hello, Java` and `Hello, World` remain unchanged.
- [ ] Verify `transform:redefine=false` on the initial load.
- [ ] Check that the agent JAR contains both the nested transformer class and the correct manifest entry.
- [ ] Verify the JAR does not pull in unnecessary JDK internal ASM dependencies.
- [ ] Do not confuse "target observed" with "bytecode rewritten/installed".

### When Moving to Production

- [ ] Limit logging on the class loading path and avoid blocking/recursion.
- [ ] Ensure accurate filtering by class name, loader/module if needed.
- [ ] Design for thread-safety when multiple class definitions occur concurrently.
- [ ] If observing already-loaded classes is desired, plan retransformation separately with capabilities.
- [ ] Do not use transformer exceptions as a class-loading rejection policy.
- [ ] Test on the actual runtime/JDK/vendor/module topology.
- [ ] If multiple agents are enabled, record the entire transformer chain.
- [ ] Separate transformer logging outcomes from verification/definition and business behavior.
- [ ] Only expand to bytecode rewriting after the no-op baseline has been verified.

**Conclusion:** a transformer for this practical exercise only needs to **filter `className` correctly**, **record the exact target class**, and **return `null` in all branches**. It is a way to verify the `premain` initialization path and the class loading path of `demo.Target` without adding bytecode. The before/after results show the application preserves both business values; the only difference in stdout is the diagnostic lines actively printed by the agent.

### Official Documentation

- [Java SE 17 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): 5/6-parameter overloads, internal form names, `return null`, and non-mutating input buffer.
- [Java SE 17 — Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `addTransformer`, `removeTransformer`, `isRetransformClassesSupported`, and `retransformClasses`.
- [Java SE 17 — java.lang.instrument](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): `premain`, `-javaagent`, manifest attributes.
- [JVMS Java SE 17 — Class File Format](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html): binary/internal names, classfile structure.
- [JVMS Java SE 17 — Loading, Linking and Initialization](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): class definition, linking, and resolution stages.
