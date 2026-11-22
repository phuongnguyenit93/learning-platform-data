# Excluding Agent, Helper, and Logging Classes to Avoid Self-Instrumentation

## 1. Why Must a Transformer Exclude the Instrumentation System Itself?

When a Java agent registers a `ClassFileTransformer`, the JVM may invoke `transform(...)` when a new class is defined, when a class is redefined, and—for a transformer with the corresponding capability—when a class is retransformed. The callback sits on the application's **class loading or transformation** path: code running inside the callback must be sufficiently lightweight, capable of running repeatedly, and especially avoid triggering a dependency class-loading chain that it then tries to instrument.

If the agent also transforms classes belonging to the **agent**, **helpers**, **loggers**, **metrics exporters**, or the bytecode library it uses itself, the instrumentation probe can alter the machinery that creates the probe. A loop can occur:

~~~text
JVM is loading example/app/InventoryService
    -> calls SafeTransformer.transform(...)
        -> transformer calls Logger.debug(...)
            -> logger is not loaded yet, JVM loads logger
                -> calls SafeTransformer.transform(logger)
                    -> transformer calls Logger.debug(...) again
                        -> loop, linkage error, hang, or stack overflow
~~~

Not every system reproduces the exact loop shown in the diagram. The JVM has some built-in protections for classes that the transformer directly depends on, but **you should not rely on those to assume every helper/logger is automatically safe**. The callback may call uninitialized code, trigger class loading/reentrancy, or cause lock contention. The consequences can be `StackOverflowError`, `ClassCircularityError`, `NoClassDefFoundError`, `LinkageError`, deadlock, or extreme overhead; the actual failure mode depends on the JVM and the dependency chain.

**Principle:** identify classes within the instrumentation scope using a **very early filter**, before creating an ASM parser, initializing Byte Buddy, calling reflection, accessing a logger, or creating a span. If the class is out of scope, return `null` immediately. Classes used to **perform instrumentation** must sit outside the scope to which instrumentation is applied.

This lesson focuses solely on the **filtering contract in a transformer**: selecting/excluding classes and avoiding self-instrumentation. Actual bytecode generation can be done with ASM, Byte Buddy, or another tool after passing the filter step.

## 2. `ClassFileTransformer.transform` Inputs and the Right Filtering Point

Java 17 has an overload that takes `Module`:

~~~java
byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain protectionDomain,
        byte[] classfileBuffer);
~~~

This is an **illustrative signature**, not a standalone program. With the five-parameter overload (without `Module`), Java 17 defaults to delegating from the six-parameter overload to the older method if you override it. Therefore, the standalone example in a later section uses the five-parameter overload for brevity.

| Parameter | Meaning for decision-making |
| --- | --- |
| `module` | Module of the class being transformed; useful when scoping by module in the Java 9+ overload |
| `loader` | The **defining** class loader of the class; may be `null` for the bootstrap class loader |
| `className` | JVM internal name, e.g., `java/lang/String`, `example/agent/SafeAgent$SafeTransformer`; may be `null` in some cases |
| `classBeingRedefined` | `null` on initial load; the `Class<?>` object during redefine/retransform |
| `protectionDomain` | Protection domain of the class, which can help identify the source when policy requires it |
| `classfileBuffer` | Input bytecode; **must not modify this array in place** |

**Specifically:** `className` uses forward slashes `/` instead of dots `.` like Java source names. A filter for `"example.agent."` will not match `"example/agent/SafeAgent"`. Nested classes also use the `$` symbol, such as `SafeAgent$SafeTransformer`, so a package prefix `"example/agent/"` will exclude nested classes as well.

The transformer follows this contract:

- **Returning `null`:** the current transformer **does not modify** the bytecode of this class. This **does not prevent** the JVM from loading the class and **does not prohibit** other transformers from acting on it.
- **Returning a new `byte[]`:** this is the transformed class file content; it must be valid and comply with redefine/retransform constraints. Do not modify the input `classfileBuffer` in place.
- **Throwing an exception:** the JVM still continues trying other transformers according to the contract. Do not expect an exception in a transformer to “safely abort” class loading; filter and code-weaving design must actively control errors.

For the goal of protecting the agent, checking `className`/`loader` must happen **before** any bytecode parsing or detailed logging. Even a single `Class.forName(...)` call or an un-warmed utility call can pull in class loading inside the callback itself.

Reference: [ClassFileTransformer — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html).

## 3. Designing a Multi-Layer Exclusion Policy

A practical filter has two layers:

1. **Mandatory denylist/ignore:** agent classes, helpers, loggers/metrics, JDK system classes, and sensitive components of the class-loading mechanism. The goal is to avoid touching the instrumentation execution path itself.
2. **Allowlist/scope restriction:** only instrument the business packages/classes that the problem actually requires. For example, only `example/app/`, without expanding to all third-party classes.

Examples of groups to consider:

| Group | Illustrative internal prefix | Why skip? |
| --- | --- | --- |
| Agent and transformer | `example/agent/` | Avoid applying instrumentation to the code that installs instrumentation |
| Internal helpers | `example/helper/` | Helpers are often called inside `transform`, recorders, or advice |
| Internal logging/telemetry | `example/logging/`, `example/telemetry/` | Avoid logs/spans recursively generating more logs/spans or triggering class loading |
| Logging frameworks | `org/slf4j/`, `ch/qos/logback/`, `org/apache/logging/log4j/` | Logging classes may sit on the agent's own execution path |
| Core JDK classes | `java/`, `javax/`, `jdk/`, `sun/`, `com/sun/` | Default safety filter for the lesson, reducing the risk of interfering with infrastructure classes |
| Business code to measure | `example/app/` | Only classes whose names fall within this scope are considered further |

This is an **illustrative policy**, not an exhaustive list for every project. If the agent uses ASM, Byte Buddy, Micrometer, or a custom exporter, you must exclude **the exact actual packages**, including versions that have been **relocated/shaded** into another namespace. An agent inside `company/observability/` needs to protect that entire namespace, rather than only excluding `example/agent/`. Do not add unfounded prefixes that cause important business classes to be missed.

**Package boundaries must be checked.** Use `"example/agent/"`, not `"example/agent"`: a prefix missing the trailing `/` can accidentally exclude `example/agentTools/Service`. Also do not only compare with `equals("example/agent/SafeAgent")` because that will miss nested classes and other helpers.

**Filtering by name alone is also insufficient in plugin systems:** two class loaders can define two classes with the same name. For multi-tenant environments, OSGi, application servers, or plugin loaders, you should identify the properly scoped class loader/module/`ProtectionDomain`; inside the callback, avoid complex operations to infer loader identity.

### 3.1. The Bootstrap Class Loader Issue

`loader == null` usually means the class was defined by the **bootstrap class loader**. This lesson's safe pattern excludes them, even if the name appears to match. This is a **policy choice**, not an API rule. Agents specialized in instrumenting JDK libraries may need to handle bootstrap deliberately, with a very strict class loader model, modules, bootstrap helpers, and compatibility testing. Do not relax the filter just because a probe has not appeared yet.

### 3.2. `className == null`

The callback should not assume every case has a name. The `className == null` condition must be handled immediately before calling `startsWith` to avoid a `NullPointerException`. For unknown names, the “do not instrument” policy is the safe default of the example.

## 4. Runnable Java 17+ Example: Safe Filter and Observing Agent

We build an agent that actually registers a `ClassFileTransformer` but **intentionally does not modify bytecode**. It confirms that the callback sees business classes, while classes on the denylist are not processed further. This helps test the exact filtering boundaries before attaching a bytecode library to the agent.

Example structure:

~~~text
demo/
├── MANIFEST.MF
├── example/
│   ├── agent/
│   │   ├── ClassNamePolicy.java
│   │   └── SafeAgent.java
│   └── app/
│       ├── InventoryService.java
│       └── DemoMain.java
└── out/                         (.class directory generated by javac)
~~~

### 4.1. Filtering Policy, Initialized Before Registering the Transformer

**File: `example/agent/ClassNamePolicy.java`**

~~~java
package example.agent;

public final class ClassNamePolicy {
    private static final String[] EXCLUDED_PREFIXES = {
        "example/agent/",
        "example/helper/",
        "example/logging/",
        "example/telemetry/",
        "org/slf4j/",
        "ch/qos/logback/",
        "org/apache/logging/log4j/",
        "java/",
        "javax/",
        "jdk/",
        "sun/",
        "com/sun/"
    };

    private ClassNamePolicy() {}

    public static void prepare() {
        // Load/initialize the policy before registering the transformer.
        shouldInspect(
                ClassNamePolicy.class.getClassLoader(),
                "example/agent/ClassNamePolicy");
    }

    public static boolean shouldInspect(
            ClassLoader loader, String internalName) {
        if (loader == null || internalName == null) {
            return false;
        }

        for (String prefix : EXCLUDED_PREFIXES) {
            if (internalName.startsWith(prefix)) {
                return false;
            }
        }

        // Only observe the allowed application namespace.
        return internalName.startsWith("example/app/");
    }
}
~~~

`prepare()` proactively initializes `ClassNamePolicy` and the prefix array **before** the JVM starts invoking the registered transformer. Without preparation, if the first callback causes the JVM to load an unready helper, the agent can trigger an unwanted class-loading chain itself. The filter only operates on initialized `String`/arrays; it does not use a logger, reflection, or classpath scanning.

### 4.2. Java Agent Placing the Filter at the Start of the Callback

**File: `example/agent/SafeAgent.java`**

~~~java
package example.agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class SafeAgent {
    private static volatile boolean serviceObserved;

    private SafeAgent() {}

    public static void premain(
            String options, Instrumentation instrumentation) {
        ClassNamePolicy.prepare();
        ClassFileTransformer transformer = new SafeTransformer();

        instrumentation.addTransformer(transformer, false);
        System.out.println("agent-installed");
    }

    public static boolean wasServiceObserved() {
        return serviceObserved;
    }

    private static final class SafeTransformer
            implements ClassFileTransformer {

        @Override
        public byte[] transform(
                ClassLoader loader,
                String className,
                Class<?> classBeingRedefined,
                ProtectionDomain protectionDomain,
                byte[] classfileBuffer) {

            // Filter immediately; do not call a logger or bytecode parser.
            if (!ClassNamePolicy.shouldInspect(loader, className)) {
                return null;
            }

            // Only record a marker to prove the class passed through the callback.
            if ("example/app/InventoryService".equals(className)) {
                serviceObserved = true;
            }

            // Demo does not inject bytecode; null = leave the class unchanged.
            return null;
        }
    }
}
~~~

`new SafeTransformer()` and `ClassNamePolicy.prepare()` run **before** `addTransformer(...)`, helping prepare the core classes that the transformer depends on. When the JVM loads `example/app/InventoryService`, the class name passes the filter and `serviceObserved` is set to true. All other classes are skipped or left unchanged; **no actual bytecode instrumentation occurs**. The `System.out.println(...)` line runs only once from `premain`, **not inside `transform`**.

The second argument `false` to `addTransformer(transformer, false)` means the registered transformer **does not support retransformation**. It still receives callbacks for newly defined classes after registration. If the goal is to retransform already-loaded classes, a separate capability and different registration are needed; this is unrelated to the basic exclusion rules.

### 4.3. Application Code

**File: `example/app/InventoryService.java`**

~~~java
package example.app;

public final class InventoryService {
    public int available() {
        return 42;
    }
}
~~~

**File: `example/app/DemoMain.java`**

~~~java
package example.app;

import example.agent.ClassNamePolicy;
import example.agent.SafeAgent;

public final class DemoMain {
    public static void main(String[] args) {
        ClassLoader loader = DemoMain.class.getClassLoader();

        System.out.println("agentExcluded="
                + !ClassNamePolicy.shouldInspect(
                        loader, "example/agent/SafeAgent"));
        System.out.println("helperExcluded="
                + !ClassNamePolicy.shouldInspect(
                        loader, "example/helper/Helper"));
        System.out.println("loggerExcluded="
                + !ClassNamePolicy.shouldInspect(
                        loader, "example/logging/LogSink"));
        System.out.println("jdkExcluded="
                + !ClassNamePolicy.shouldInspect(
                        loader, "java/lang/String"));
        System.out.println("bootstrapExcluded="
                + !ClassNamePolicy.shouldInspect(
                        null, "example/app/InventoryService"));
        System.out.println("nullNameExcluded="
                + !ClassNamePolicy.shouldInspect(loader, null));
        System.out.println("appIncluded="
                + ClassNamePolicy.shouldInspect(
                        loader, "example/app/InventoryService"));

        System.out.println("service="
                + new InventoryService().available());
        System.out.println("serviceObserved="
                + SafeAgent.wasServiceObserved());
    }
}
~~~

The demo program intentionally references `ClassNamePolicy` and `SafeAgent` in `DemoMain` so it can perform internal verification. **Production applications should not depend directly on the agent to read state like this**: collectors/metrics can export results through a separate observability channel. The names `example/helper/Helper` and `example/logging/LogSink` here are **simulated name strings for testing the policy**, not classes you need to write.

### 4.4. Agent Manifest

**File: `MANIFEST.MF`**

~~~text
Manifest-Version: 1.0
Premain-Class: example.agent.SafeAgent

~~~

In an actual manifest file, a trailing blank line is required to terminate the main attributes section. The example only needs `Premain-Class` because it uses `-javaagent` at startup. No `Agent-Class`/`agentmain` or retransformation capability is needed for this exercise.

### 4.5. Compile, Package, and Run

From the `demo/` directory containing the source files and manifest:

~~~bash
javac --release 17 -d out example/agent/ClassNamePolicy.java example/agent/SafeAgent.java example/app/InventoryService.java example/app/DemoMain.java
jar --create --file safe-agent.jar --manifest MANIFEST.MF -C out example/agent
java -javaagent:safe-agent.jar -cp out example.app.DemoMain
~~~

The commands above run on JDK 17+ in Windows PowerShell or a Unix shell when `javac`, `jar`, and `java` are on `PATH`. Create the `out` directory with `mkdir out` before compiling if needed; `javac -d out` requires the output directory to exist.

**Expected stdout of the program with the agent on a typical HotSpot/JDK:**

~~~text
agent-installed
agentExcluded=true
helperExcluded=true
loggerExcluded=true
jdkExcluded=true
bootstrapExcluded=true
nullNameExcluded=true
appIncluded=true
service=42
serviceObserved=true
~~~

The last line confirms that `InventoryService` was passed through the callback by the JVM, yet no bytecode was modified. `agentExcluded=true` tests the policy by name; for real code, the policy returns `false` immediately if the JVM invokes the transformer for `example/agent/SafeAgent` or helpers in the same package.

**Run again without the agent:**

~~~bash
java -cp out example.app.DemoMain
~~~

Without `-javaagent`, `premain` does not run and no transformer is registered, so stdout is the same as above except **there is no `agent-installed` line** and the last line is **`serviceObserved=false`**. The policy check results remain the same because they are pure functions of the name and class loader.

## 5. Why Does the Example Avoid Self-Instrumentation?

**First, namespace separation.** All agent tooling and the filter policy live in `example/agent/`, while application code lives in `example/app/`. An explicit prefix allows skipping the agent and nested classes like `example/agent/SafeAgent$SafeTransformer`. If parser/recorder tools live in `example/helper/` or `example/telemetry/`, they also belong on the denylist.

**Second, pre-initializing dependencies.** `ClassNamePolicy.prepare()` and the creation of `SafeTransformer` happen before `addTransformer`. In an agent that weaves with ASM/Byte Buddy, you must prepare the minimal classes that the filter/weaver depends on by your own design, while not loading libraries en masse when callbacks begin. Early initialization is not enough if an internal helper has new lazy dependencies, so namespace exclusion remains mandatory.

**Third, filtering based on callback data.** `shouldInspect(loader, className)` does not call `Class.forName(className)`, does not perform classpath scanning, and does not access `ClassLoader.loadClass`. In the initial callback, `classBeingRedefined` is usually null; to identify the class about to be defined, using the available name/loader/metadata is sufficient.

**Fourth, no logging inside `transform`.** The agent can log **once** after registering in `premain`, but the callback must not call a logging framework, network exporter, or recorder that could trigger class loading. If you need to track the total number of filter evaluations, design a lightweight pre-initialized counter and read/export it outside the callback; avoid creating distinct metric labels for every class name.

**Fifth, no bytecode modification when unnecessary.** `return null` keeps the input intact so the JVM continues loading the class. When actual weaving is needed, only construct a new `byte[]` **after** the filter and return valid bytes. Never modify in place the `classfileBuffer` handed to the transformer by the JVM.

### 5.1. Where Should Actual Bytecode Injection Go?

In an agent integrated with a bytecode transformation library, the logical structure should be:

~~~text
transform(loader, className, ..., bytes)
    if loader or className is invalid:     return null
    if agent/helper/logger/JDK:            return null
    if outside business packages:          return null
    check specific instrumentation conditions
    invoke pre-initialized bytecode weaver
    if unchanged:                          return null
    return valid NEW byte[]
~~~

This is a **processing-flow model**, not standalone runnable Java code. The experimental sample in Section 4 intentionally stops before the weaver step to demonstrate the boundary in a runnable, testable way.

If using **Byte Buddy**, configure `ignore(...)` or an equivalent exclusion matcher **before** the `type(...)` rules where the agent attaches advice, ensuring helpers/advice/plugins/loggers are excluded. If using **ASM directly** inside `ClassFileTransformer`, call the name/loader filter before constructing `ClassReader` or `ClassWriter`. Exact APIs and matchers depend on the library version; the exclusion-layer principle remains the same.

## 6. Common Pitfalls When Scaling to Production

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Putting `log.debug(...)` right at the top of `transform` | An unloaded logger can create a class-loading loop or reentrant callbacks | Filter first, remove logging from the critical callback path; emit info outside the callback |
| Only excluding the `SafeAgent` class | Nested transformers, helpers, and other libraries still get touched | Exclude the entire package with a trailing `/` and all dependent namespaces |
| Using `example.agent.` to match `className` | Does not match JVM internal name `example/agent/SafeAgent` | Use internal names with `/` |
| Forgetting to handle `className == null` | `NullPointerException` during class loading | Skip early with `return null` |
| Only excluding `java/` and instrumenting everything else | Easily touches loggers, instrumentation libraries, or framework class loaders | System denylist + business allowlist |
| Overly broad prefix like `example/` | Skips all application classes that need instrumentation | Restrict namespace exclusions specifically |
| Prefix missing boundary like `example/log` | May mistakenly exclude `example/login/...` | Use `example/logging/` |
| Thinking `loader == null` means an invalid name | Misinterprets the bootstrap loader indicator | Skipping bootstrap is a safe choice of the example, not an API requirement |
| Using `Class.forName` to resolve the class by name in the callback | Triggers additional class loading and transformer reentrancy | Rely on the available `className`, `loader`, `module` |
| Returning `classfileBuffer` after modifying its contents in place | Violates the contract not to mutate input | Return `null` if unchanged; when changed, create a new byte array |
| Treating `return null` as blocking all agents | Other transformers can still process the class | Policy only protects the transformer in question; other agents must be checked |
| Assuming `removeTransformer` stops all callbacks immediately | In-flight callbacks can still occur during removal | Handle concurrency, cleanup, and safe lifecycle |
| Instrumenting the collector/tracer itself | Can cause infinite span/metric/log generation or high overhead | Exclude logger, tracer SDK, and exporter by their actual packages |

### 6.1. Should You Filter Only by Class Loader?

No. A single class loader often holds both application classes and agent or framework libraries. `loader != null` is only a first step to skip bootstrap; **it does not mean all remaining classes are safe**. Combine **package-name** filtering with allowed class loaders/modules. If the same class name exists in multiple loaders, the policy must be applied properly to **each `(loader, name)` pair**.

An agent loaded into the system class loader may share it with application classes. Therefore, checking `loader == SafeAgent.class.getClassLoader()` can also mistakenly exclude **the entire application** if used as a denylist. Loader-based selection must be based on the actual architecture, not applied arbitrarily.

### 6.2. When Retransforming/Redefining Already-Loaded Classes

Package filtering still needs to apply during retransform/redefine. However:

- `classBeingRedefined` may be non-null, helping identify the exact `Class<?>` being modified.
- `Instrumentation.isRetransformClassesSupported()` and `isModifiableClass(type)` must be checked separately if actively calling `retransformClasses`.
- A transformer registered with `canRetransform=false` **is not called again** during a retransform pass; the JVM may reuse the previous transformation result per the contract.
- New rules added to the instrumentation system do not automatically strip bytecode from previously transformed classes. You need a deployment, retransform/redefine, and compatibility plan when changing instrumentation scope.

In the Section 4 example, `addTransformer(..., false)` intentionally tracks only **new class definitions**. You should not infer that the agent observed every class loaded prior to its registration.

### 6.3. What If the Filter/Weaver Throws an Exception?

Per the `ClassFileTransformer` contract, a transformer throwing an exception does not necessarily cause the JVM to abort all class loading; other transformers may still be invoked. Do not use exceptions as a “skip class” mechanism. For out-of-scope names/loaders, **return `null` before any risky operation**.

If a bytecode processing error occurs after passing the filter, record it through a safely pre-initialized diagnostic channel, rate-limit logging, and do not let secondary recorders cause further errors. You may need a `catch` at the transformation boundary to keep errors diagnosable; however, do not silently swallow serious errors and report “instrumentation succeeded”. Invalid input bytecode corresponds to `IllegalClassFormatException` per the API. Deciding whether to halt the application or continue must be handled by an explicit deployment policy, not by relying on an exception inside the callback.

## 7. Implementation and Filter Scope Testing Checklist

Before releasing a real-world agent, verify across three layers:

**A. Pure filter unit tests:**

- `example/agent/SafeAgent`, nested `example/agent/SafeAgent$SafeTransformer` → **exclude**.
- `example/helper/SomeHelper`, `example/logging/LogSink`, `org/slf4j/Logger` → **exclude**.
- `java/lang/String`, `jdk/internal/...`, null loader, null name → **exclude** under this policy.
- `example/app/InventoryService` with application loader → **include**.
- `example/app2/Other` → **exclude**, because the allowlist only grants access to `example/app/`.
- Verify prefixes have boundaries; new/shaded packages are re-declared.

**B. Agent tests in an isolated JVM:**

Run once **without the agent** and once with `-javaagent`. Observe the order where `premain` runs before `main`, the callback sees allowlisted classes defined after registration, and business output is unchanged. For an agent with a real weaver, verify that agent/helper/logger classes have unchanged bytecode, while verifying that business classes are transformed accurately.

**C. Stress and failure testing:**

Run with multiple threads, lazy initialization of logging libraries, new classloaders/plugins, slow startup, and shutdown; measure overhead, the number of classes inspected, and the number of bytecodes actually transformed. Test both when the transformer returns `null`, when the weaver encounters an unsupported class file, and when the agent must clean up. Limit logs/telemetry so the observability tool does not become a source of incidents.

### 7.1. Scenario for Detecting a “Self-Instrumenting Agent” Bug

Suppose after enabling the agent, startup becomes slow and a `ClassCircularityError` appears near logger classes. Check in order:

1. Check whether the filter runs **before** the logger/Byte Buddy/ASM.
2. List all agent, helper, advice, shaded dependency, and logging/telemetry exporter packages used by the callback.
3. Check whether `className` uses internal names and handles `null`.
4. Verify that deny/allow rules are not overridden by a later matcher when the framework builds its pipeline.
5. Test with a minimal agent that only does `return null` like the example to isolate callback/filter bugs from weaving bugs.
6. Re-enable instrumentation piece by piece with a narrow scope, collecting evidence of selected classes and resource fluctuations **outside the callback path**.

This is an analysis procedure, not a claim that every `ClassCircularityError` is caused by a logger. You need to inspect the stack trace, class loader structure, and the actual timing of the error.

## 8. Self-Check Questions

1. If the callback calls `Logger.debug(...)` before checking `className`, what situation can an unloaded logger lead to?
2. Why does `example/agent/` protect both `SafeAgent` and `SafeAgent$SafeTransformer`?
3. Does `className` have the format `example.app.InventoryService` or `example/app/InventoryService`?
4. Why is `return null` a safe way to skip out-of-scope classes, yet it does **not** block other agents?
5. Why can using only `loader != null` or only `loader == agentLoader` be wrong?
6. Why must you prepare filters/helpers before `addTransformer` while still needing a denylist?
7. Does the sample in Section 4 modify the bytecode of `InventoryService`? Which stdout line proves the callback was invoked?
8. If using ASM/Byte Buddy, should the filter step come before or after initializing the parser/weaving?

**Conclusion:** In Java instrumentation, **class name and class loader filtering must be the very first step of a transformer**. Exclude the agent, helpers, loggers, telemetry, and dependent libraries; at the same time, allowlist the exact business code to observe. Initialize dependencies before registering the transformer, do not log or actively load classes inside the callback, and use `return null` when there is no transformation. These measures reduce the risk of self-instrumentation, reentrancy, and recursion while the JVM is loading classes.

### References

- [Java 17 — ClassFileTransformer, transform contract and returning null](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html)
- [Java 17 — Instrumentation, addTransformer and removeTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html)
- [Java 17 — java.lang.instrument agent specification](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html)
