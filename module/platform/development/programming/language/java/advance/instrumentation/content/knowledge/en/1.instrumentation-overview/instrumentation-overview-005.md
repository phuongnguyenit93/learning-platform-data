# Distinguishing Offline Transformation, Load-Time Transformation, and Modifying Loaded Classes

In Java, **instrumentation** is a technique for observing or intervening in program behavior by processing class bytecode. Three approaches that are often confused are **offline transformation**, **load-time transformation**, and **modifying classes already loaded by the JVM (retransformation/redefinition)**. While all of them can use new bytecode, they differ in **when they are applied, where the bytecode comes from, the triggering API, and class structure limitations**.

After this lesson, you should be able to explain: which `.class` file is used at each stage; why replacing a JAR on disk does not automatically update running classes; the difference between `retransformClasses` and `redefineClasses`; when an application must be restarted; and how to verify at which point an agent actually intervenes.

## 1. First: Bytecode on Disk Differs from Class Definitions in the JVM

Typical flow:

```text
.java --javac--> .class/JAR --[read by ClassLoader]--> defineClass
          ^                              |
          |                              +-- load-time transformer (if registered)
          |                              v
  offline transformation         JVM verifies/links/initializes/uses class
                                             |
                                             +-- retransform/redefine (if supported and requested)
```

- **A class file** is bytecode stored in a directory, JAR, or another data source. Changing the bytes there does not automatically change the class definition already created by the JVM.
- **A loaded class definition** belongs to a specific JVM and a specific **defining ClassLoader**. The same binary name defined by two different class loaders still results in two distinct classes.
- **Loading, linking, and initialization** are distinct steps. The load-time transformation callback occurs before the new definition is verified and used by the JVM; `retransform` acts on an already existing class.
- Java does not define a mechanism to "reload the same class on every method call." Once a class is loaded, replacing the source `.class` or JAR generally only takes effect on a new load in an appropriate JVM/class loader, or after a class modification operation supported by the JVM.

**Core distinction:** "When is the agent started?" and "When is the class transformed?" are two separate questions. An agent attached to the JVM after startup can still process *classes loaded in the future*; to touch already-loaded classes, it must request an appropriate retransform/redefine.

## 2. Offline Transformation

**Timing:** after the bytecode generation step and **before** the target JVM defines the class. A build tool, plugin, packaging tool, or file-processing step reads `.class`/JAR files, writes out new bytecode, and then the application runs using the transformed artifact.

For example, a coverage system needs to insert counter instructions into every method during packaging:

```text
Java source --> javac --> build/classes
                            |
                    Offline transformer
                            |
                            v
                   build/instrumented
                            |
                      Packaging/JAR
                            |
                    JVM loads new class
```

Characteristics:

1. **Input/output:** class file bytes or JARs; the result is usually a new artifact that can be inspected, stored, and released.
2. **No agent needed in the target JVM** if all required classes have been transformed before runtime. Classes are loaded through the normal path from the new artifact.
3. **Broader structural modification capabilities:** can add methods/fields/classes and change bytecode structure as long as the class file is valid and the program remains compatible. Not constrained by the structural replacement rules of *already-existing classes*.
4. **Does not update a running JVM:** overwriting a JAR or `.class` after classes have already been defined does not make existing objects and methods automatically switch to the new version.
5. **Trade-offs:** adds a build step, difficult to apply if bytecode is only generated at runtime or comes from libraries outside the pipeline; must preserve debug information, class file version compatibility, packaged resources, and JAR signatures if present.

An offline transformation operation *in principle* reads a byte array, converts it using a library that understands the class file format (such as ASM or Byte Buddy), and writes another artifact. It is a build step, not a call to `Instrumentation.retransformClasses`.

**Use when:** the set of classes to be run is known in advance, a repeatable/inspectable build is needed, major structural changes are required, or you want to reduce instrumentation logic at startup time.

## 3. Load-Time Transformation

**Timing:** when the JVM is about to define a new class. A Java agent registers a `ClassFileTransformer` with `Instrumentation.addTransformer(...)`. When a class goes through the definition process, the JVM passes the input bytecode through the transformer chain before verifying and putting that definition into use.

An early-starting Java agent typically has an entry point:

```java
public static void premain(String agentArgs, Instrumentation instrumentation) {
    instrumentation.addTransformer(new MyTransformer());
}
```

In `transform`, for a class being loaded for the first time, `classBeingRedefined == null`. The `className` uses the internal form, for example `com/example/OrderService`, and may not be available for some kinds of classes. The transformer returns:

- `null`: no bytecode modification on this callback invocation;
- a **new, valid** `byte[]`: the JVM uses the new bytecode as input for subsequent steps in the transformer chain/class definition. Do not modify `classfileBuffer` directly.

Example transformer body using a bytecode library (**illustrative** code; `rewriteWithAsmOrByteBuddy` is a function you must implement yourself; this snippet is not a standalone program):

```java
@Override
public byte[] transform(ClassLoader loader, String className,
                        Class<?> classBeingRedefined,
                        ProtectionDomain domain, byte[] classfileBuffer) {
    if (!"com/example/OrderService".equals(className)) {
        return null;
    }
    return rewriteWithAsmOrByteBuddy(classfileBuffer);
}
```

### What Load-Time Transformation *Does* and *Does Not* Guarantee

- **Only processes on a class definition event:** if a transformer is registered *after* `OrderService` has already been loaded, adding the transformer does not cause that class to automatically re-run the callback.
- **Can intervene structurally before definition:** unlike redefinition/retransformation, there is no old definition whose structure must be preserved; however, the bytecode must still be valid, dependent classes must be compatible, and the class loader/module must be able to access whatever the new code uses.
- **Agent started with `-javaagent`:** the `premain` method runs before the application's `main`, helping set up the transformer early. Some platform/agent classes may have already been loaded before the transformer is ready; do not assume every class in the JVM will pass through it.
- **Dynamically attached agent:** `agentmain` can register a transformer for **subsequent loads**, but does not automatically modify already-loaded classes.
- **Multiple transformers can be chained:** the output of an earlier transformer becomes the input to the next transformer; order and conflicts can affect the result. Process only target classes and avoid creating dependency cycles when the transformer itself loads its own libraries.

**Use when:** you need to automatically add tracing, metrics, profiling, coverage, or proxy behavior at the time classes are loaded, including for libraries whose source is not modified.

## 4. Loaded Classes — Retransformation and Redefinition

Once a class has been defined, the JVM **does not simply re-run `defineClass` with the same name and same loader** to overwrite it. The `java.lang.instrument.Instrumentation` API provides two mechanisms to modify an existing definition, depending on JVM capabilities and agent permissions/configuration.

### 4.1. `retransformClasses(Class<?>... classes)`

This is the way to **ask the JVM to re-run the transformer pipeline** for the specified classes:

1. The agent has `Instrumentation` and `isRetransformClassesSupported() == true`; the agent's manifest permits it with `Can-Retransform-Classes: true`.
2. The transformer must be registered with `addTransformer(transformer, true)` if it wants to **be called again** during retransformation.
3. Check the specific class via `isModifiableClass(target)` and then call `retransformClasses(target)`.
4. The JVM creates input bytecode from the original definition or the most recent redefinition; transformations from transformers *without retransform capability* are reapplied as their previous results, while transformers *with retransform capability* are called again. You should not assume the input is a byte array with all previous instrumentations stacked together.
5. The JVM verifies and installs the new definition if the changes are valid; if an error occurs, the operation fails according to the API contract.

`retransformClasses` **does not accept replacement bytecode directly** from the caller. You update the transformation behavior of your transformer and then ask the JVM to reapply it to the target class. `classBeingRedefined` in the callback is non-`null` at this time.

### 4.2. `redefineClasses(ClassDefinition... definitions)`

This is the way to **directly supply replacement bytecode** for one or more existing classes:

```java
// API illustration, not a standalone program:
byte[] replacement = /* valid .class bytecode for the exact existing class */;
instrumentation.redefineClasses(
    new ClassDefinition(ExistingService.class, replacement)
);
```

Requirements: `isRedefineClassesSupported() == true`, the manifest has `Can-Redefine-Classes: true`, the class is modifiable, and the bytecode meets modification constraints. The JVM may still pass the class bytes through transformers according to the API's rules.

**Key difference:** retransform is suitable when you want registered transformers to reprocess the class; redefine is suitable when you already have an exact replacement class file (for example, a debugger recompiles a method and hot-swaps it).

### 4.3. Limitations of Loaded Classes

With the standard mechanism on common HotSpot/JDKs, retransform/redefine allows changing the executable code of methods within compatibility limits, but **does not allow arbitrarily changing the class schema**. Changes such as adding/removing/renaming fields or methods, changing signatures or modifiers, or changing the superclass or interface list may be rejected. Supported capabilities are **JVM-dependent**; always check the API and handle exceptions, and do not treat HotSwap as a replacement for a full build.

Effects after a successful replacement:

- **New method invocations** generally run the new definition; **currently executing stack frames** of the replaced method continue running the old bytecode for that invocation.
- **Does not automatically re-run the static initializer (`<clinit>`)**, does not recreate existing objects, and does not reset static field state; changing logic does not mean migrating object structure or data.
- **Exact class/exact loader:** `com.example.Foo` in two different defining class loaders are two distinct targets.
- **Not every class can be modified:** retransform/redefine capabilities may be disabled or unsupported by the JVM; individual classes may not be modifiable.
- **Do not infer "directly changing bytecode on disk":** the new version installed in the JVM is not necessarily written back to the JAR. When starting a new process from the old artifact, the application will revert to the bytecode from that artifact.
- **Synchronized multi-class changes:** a single API operation can include multiple related classes, but it must still preserve constraints and binary linkage.

### 4.4. Attaching an Agent Is Not Automatically Retransformation

`premain` is called when running with `-javaagent`; `agentmain` is for agents loaded into a running JVM via the corresponding attach mechanism. Both can receive `Instrumentation`. From there, the agent **can** register a transformer to process later-loaded classes or proactively request `retransformClasses`/`redefineClasses` for current classes.

JDK 21 (JEP 451) emits a warning when an agent is loaded dynamically; the `-XX:+EnableDynamicAgentLoading` flag indicates the option to allow it in JDK 21. Default policies for dynamic loading vary by JVM version/implementation. Starting with `-javaagent` and modifying an already-loaded class are two independent aspects.

## 5. Comparison Table of the Three Paths

| Criterion | Offline | Load-time | Loaded classes (retransform/redefine) |
|---|---|---|---|
| **Timing** | Before the target JVM loads the class | Right when the JVM is about to define a new class | After the JVM has defined the class |
| **Where it intervenes** | `.class`/JAR files or build artifacts | Transformer chain in the JVM | Existing class definition in the JVM |
| **Bytecode source** | Input artifact | Bytes the JVM/ClassLoader is about to define | Base bytes + reapplied transformers; or new bytes supplied to redefine |
| **Trigger** | Build/packaging/rewriter tool | Registering `ClassFileTransformer`; class loading event | Calling `retransformClasses` or `redefineClasses` |
| **Affects already-loaded classes?** | Not automatically | Not automatically | Yes, if the class/JVM supports it and bytecode is valid |
| **Changes class schema?** | Possible within class file/compatibility limits | Possible before definition, if bytecode is valid | Heavily restricted by loaded-class modification mechanisms |
| **Persistence of change** | In the output artifact | In the process's loaded definition | In the process's current definition |
| **Examples** | Build-time coverage, weaving for release builds | Startup tracing agent | Debugger HotSwap, updating probes in a running JVM |

**Note:** `-javaagent` by itself does not mean "load-time only": the same agent can perform load-time transformation and later proactively call retransform.

## 6. Runnable Java 17+ Experiment: Observing Both Callbacks

This example **observes timing** and intentionally returns `null`, so it **does not modify bytecode**. It helps demonstrate that "first load" and "reprocessing an already-loaded class" are two separate events. Requires a standard JDK with `javac`, `jar`, and retransformation support.

Create three Java files and one manifest file **in the same directory**:

**`TraceAgent.java`**

```java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.lang.instrument.UnmodifiableClassException;
import java.security.ProtectionDomain;

public final class TraceAgent implements ClassFileTransformer {
    private static Instrumentation instrumentation;

    public static void premain(String agentArgs, Instrumentation inst) {
        instrumentation = inst;
        boolean supported = inst.isRetransformClassesSupported();
        inst.addTransformer(new TraceAgent(), supported);
        System.out.println("agent ready; retransformation=" + supported);
    }

    public static void retransform(Class<?> target)
            throws UnmodifiableClassException {
        if (!instrumentation.isRetransformClassesSupported()
                || !instrumentation.isModifiableClass(target)) {
            System.out.println("retransform unavailable");
            return;
        }
        instrumentation.retransformClasses(target);
    }

    @Override
    public byte[] transform(ClassLoader loader, String className,
            Class<?> classBeingRedefined, ProtectionDomain domain,
            byte[] classfileBuffer) {
        if ("Sample".equals(className)) {
            String phase = classBeingRedefined == null
                    ? "first load" : "retransform/redefine";
            System.out.println("transform Sample: " + phase);
        }
        return null; // observe only, do not modify bytecode
    }
}
```

**`Sample.java`**

```java
public final class Sample {
    public static String message() {
        return "hello";
    }
}
```

**`Demo.java`**

```java
public final class Demo {
    public static void main(String[] args) throws Exception {
        System.out.println("Demo.main");
        Class<?> target = Class.forName("Sample");
        System.out.println("before: "
                + target.getMethod("message").invoke(null));
        TraceAgent.retransform(target);
        System.out.println("after: "
                + target.getMethod("message").invoke(null));
    }
}
```

**`manifest.mf`** (ending with a blank line):

```text
Manifest-Version: 1.0
Premain-Class: TraceAgent
Can-Retransform-Classes: true

```

Compile, package, and run in the directory containing the four files above:

```shell
javac TraceAgent.java Sample.java Demo.java
jar cfm trace-agent.jar manifest.mf TraceAgent.class
java -javaagent:trace-agent.jar -cp . Demo
```

On HotSpot JDK 17/21 with retransformation support, the expected output is:

```text
agent ready; retransformation=true
Demo.main
transform Sample: first load
before: hello
transform Sample: retransform/redefine
after: hello
```

**Result explanation:**

1. `premain` registers the transformer before `Demo.main` runs.
2. `Class.forName("Sample")` loads `Sample` for the first time; the callback receives `classBeingRedefined == null`.
3. `retransformClasses(target)` triggers a new callback with `classBeingRedefined != null`. The string `retransform/redefine` is just the example's observation label; here the actual call is **retransform**.
4. Both prints of `hello` are identical because the transformer always returns `null`. To actually change behavior, replace that logic with a valid bytecode transformation, such as via ASM/Byte Buddy; it must still obey the limitations of loaded classes.

If the JVM reports `retransformation=false`, the example prints `retransform unavailable` and there is no second callback; this is evidence that you need to check environment capabilities, not proof that `Sample` code cannot be instrumented by other means.

## 7. Choosing a Mechanism Through Practical Scenarios

**Scenario A — Need to add a new field to a class for the next release deployment.** Transform during the build or change the source and rebuild; run the new version in a new process/class loader. Do not plan around adding fields to loaded classes using standard HotSwap.

**Scenario B — Measure the duration of every HTTP call in a third-party library right from startup.** Use `-javaagent`, register the transformer as early as possible, filter `className` accurately, and inject probes when classes are loaded. Check which classes may have already been loaded by the JVM before the agent registered.

**Scenario C — The application is running; you want to enable an additional probe for a class already in use.** The agent must have JVM access and retransformation permission, locate the exact `Class<?>`/class loader, check `isModifiableClass`, implement a retransform-capable transformer, and call `retransformClasses`. If you already have appropriate replacement bytecode, consider `redefineClasses`. Both must satisfy structural constraints.

**Scenario D — Simply replacing the service's JAR on disk and expecting the next request to use the new code.** That does not automatically change existing class definitions. You need a restart/redeploy, a new class loader with its own lifecycle management strategy, or a valid retransform/redefine mechanism depending on the goal.

## 8. Common Mistakes and How to Check

- **Confusing files with live classes:** cross-check the artifact, class loader, and `defineClass` timing; do not draw conclusions from the fact that the `.class` file has changed.
- **Registering a transformer too late:** already-loaded classes do not trigger load-time callbacks again. If immediate effect is needed, check the retransform/redefine path.
- **Not enabling capabilities:** `addTransformer(t, true)` may be invalid if the JVM/manifest does not support it; `Can-Retransform-Classes` and `Can-Redefine-Classes` are two distinct capabilities.
- **Expecting schema changes after loading:** loaded classes generally do not accept adding fields/methods or changing inheritance. Move structural changes to build/deploy or a different class loader model.
- **Generating invalid bytecode:** you may encounter `ClassFormatError`, `VerifyError`, `LinkageError`, or operation-support exceptions; check stack map frames, version, and dependencies. Transformations must produce valid bytecode for the exact class definition.
- **Forgetting concurrency/recursion:** a transformer can be called on multiple threads and while loading dependent classes; avoid reloading the very class being processed, excessive logging, and unsafe shared state.
- **Confusing a callback with a successful change:** seeing `transform` run does not guarantee the bytecode changed (returning `null` means unchanged) or that the result is valid; check behavior and errors after the JVM verifies/installs the class.
- **Assuming every running method switches code immediately:** active frames may continue running old bytecode; observe new invocations and consider the impact on existing state.
- **Ignoring class loaders/modules:** matching class names do not prove the same class; an agent may need to handle module encapsulation if deeply accessing non-open packages.
- **Using dynamic attach without checking the JDK:** starting from JDK 21 there is a warning related to JEP 451, and later versions may set different policies; check supported flags and runtime environment policies.

### Self-Check

1. **A transformer is added after class A has already loaded; will class A automatically re-run the callback?** No. An appropriate retransform/redefine request is needed if you want to process the existing class.
2. **Can an offline transformer modify a JAR file while the JVM uses the old definition?** Yes. Those are two different locations; the live definition does not update automatically.
3. **How does `retransformClasses` differ from `redefineClasses`?** Retransform asks the JVM to reapply the transformer chain according to capability rules; redefine accepts replacement bytecode for a `ClassDefinition`.
4. **Why is changing a method's body easier than adding a field to a running class?** A method body can be replaced within class modification limits; adding a field changes the schema, which standard HotSwap generally does not accept.
5. **Can a dynamically loaded agent perform load-time transformation?** Yes, for classes **loaded after** it registers the transformer. To change earlier classes, an operation for loaded classes is required.

## Official References

- [Java SE 21 — Instrumentation API](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `addTransformer`, `retransformClasses`, `redefineClasses`, and JVM capabilities.
- [Java SE 21 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): callback, bytecode passing, and transformer ordering.
- [Java SE 21 — java.lang.instrument](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): `premain`, `agentmain`, and agent manifest.
- [OpenJDK JEP 451](https://openjdk.org/jeps/451): warnings and policies when dynamically loading agents.

**Key takeaway:** Offline modifies **artifacts before loading**; load-time modifies **the input of the first class definition**; retransform/redefine modifies **an already-existing definition** within what the JVM permits.