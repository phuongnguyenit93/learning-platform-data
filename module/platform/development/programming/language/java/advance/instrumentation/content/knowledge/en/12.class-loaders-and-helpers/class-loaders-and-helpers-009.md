# Appending a JAR to the Search Path Does Not Fix a Previously Failed Symbolic Reference Resolution

## 1. The Problem: Helper Is Already in the JAR, Yet the Old Call Site Still Fails

When building a Java agent, a common solution for making helpers visible to instrumented classes is to append a JAR to the search path using `Instrumentation`:

- `appendToBootstrapClassLoaderSearch(JarFile)`: extends the class search sources of the bootstrap loader.
- `appendToSystemClassLoaderSearch(JarFile)`: extends the class search sources of the system loader, when that loader supports the append mechanism.

What often surprises developers is: **if the JVM has already attempted to resolve a symbolic reference in the runtime constant pool and that attempt failed, adding the JAR afterward does not make subsequent resolution attempts of that same reference succeed automatically**.

Imagine this scenario:

1. The method `OldCaller.read()` contains the instruction `invokestatic demo/helper/BridgeHelper.value`.
2. `BridgeHelper` is not yet on the class search path at the time the method runs for the first time.
3. The JVM resolves the method reference from `OldCaller`'s constant pool and fails with `NoClassDefFoundError`.
4. The agent calls `appendToSystemClassLoaderSearch(helperJar)`.
5. The system loader can now find `BridgeHelper`, but **`OldCaller.read()` still receives an error for the old symbolic reference**.
6. A class `NewCaller` that has its **own** symbolic reference, which has never failed before, can call `BridgeHelper.value()` after the JAR is appended.

This is the key point: **the ability to find a new class** is different from **the recorded result when resolving a specific reference**.

### Learning Outcomes

After this lesson, you will be able to:

- Distinguish between class loading, linking, resolution, and initialization.
- Understand the exact contract of both append APIs, including cases where the system loader does not support appending and the fact that `java.class.path` does not change.
- Explain why `Class.forName` succeeding after appending **does not** prove that a previously failed bytecode call is fixed.
- Identify the scope of a "cached failure": **a single symbolic reference in a runtime constant pool**, not a global ban on a binary name.
- Reproduce the behavior with a **practically tested** Java 17+ example and build a safe helper JAR preparation workflow for a Java agent.

## 2. JVM Foundations: Three Operations to Separate

### 2.1. Loading, Linking, and Initialization

| Operation | Nature | Typical Outcome |
|---|---|---|
| **Loading** | A class loader finds bytes and defines a class with a name and a specific defining loader | A corresponding `Class<?>` exists |
| **Linking** | Verifies, prepares, and resolves symbolic references according to JVM rules | Targets of class/method/field references are determined or an error is thrown |
| **Initialization** | Executes `<clinit>` when class initialization is required | Static fields/logic are initialized |

**A loaded class does not mean every method reference in that class has been successfully resolved**. The JVM may perform lazy resolution when an instruction is executed, or eager resolution depending on the implementation's choice, subject to the specification's constraints on when errors are reported.

Example source:

~~~java
package demo.app;

import demo.helper.BridgeHelper;

public final class OldCaller {
    public static String read() {
        return BridgeHelper.value();
    }
}
~~~

The compiler generates a method reference to `demo/helper/BridgeHelper.value:()Ljava/lang/String;` in the constant pool of `OldCaller.class`. When the bytecode executes `invokestatic`, the JVM must determine the owner class and target method.

### 2.2. A Symbolic Reference Is a Specific Entry

You can picture the disassembly as follows (the `#N` index is illustrative, not fixed):

~~~text
Constant pool:
    #N = Methodref demo/helper/BridgeHelper.value:()Ljava/lang/String;

OldCaller.read:
    invokestatic #N
    areturn
~~~

A simple representation:

~~~text
OldCaller runtime constant pool
    #N -> Methodref BridgeHelper.value:()String
               |
               v
       JVM resolves symbolic reference
               |
       +-------+--------+
       |                |
    Success           Failure
       |                |
    Use resolved     Record resolution
    entity           error for #N
                        |
                        v
                   Calling #N again
                    still fails
~~~

JVMS `5.4.3` specifies that when an attempt to resolve a symbolic reference fails, subsequent attempts to resolve **that same reference** continue to fail with the error from the first attempt. Appending a JAR does not clear this state.

### 2.3. "Same Reference" Does Not Mean "Same Class Name Across the Entire JVM"

This applies to **one runtime constant-pool entry of a specific class/interface**. It does not mean:

- The entire JVM is permanently banned from loading `demo.helper.BridgeHelper`.
- Every class loader fails when looking up that class.
- Every class containing `BridgeHelper.value()` in its code shares the same resolution state.
- Any `ClassNotFoundException` from reflection must be cached under the exact same symbolic-reference resolution rules.

Two classes `OldCaller` and `NewCaller` have two separate constant pools. Even though the two source methods are identical, an entry in `OldCaller` failing **does not automatically cause the entry in `NewCaller` to fail**.

The phrase "same error" in the JVMS is a contract about the resolution outcome; you should not rely on comparing `Throwable` instances with `==` or expect identical stack traces/messages to be printed twice across all JVMs.

## 3. The JAR Append Mechanism and Its Limitations

### 3.1. Bootstrap Search

~~~java
// Illustrative code inside a Java agent with Instrumentation inst.
inst.appendToBootstrapClassLoaderSearch(helperJar);
~~~

When the bootstrap loader cannot find a class, entries from the appended JARs can be searched next. If multiple JARs are appended, the additional lookup order is based on **the order of the append calls**.

The Javadoc warns that a bootstrap helper JAR should contain **only the classes/resources necessary** for instrumentation. A large JAR or one containing classes whose names collide with classes of child loaders can be defined first by the bootstrap loader due to parent delegation, breaking class identity, package-private access, or the nestmate mechanism. One situation that can produce an `IllegalAccessError` is when a child loader expects an accessor class to belong to the same runtime package, but that class ends up being defined by the bootstrap loader instead. Place helpers in their own package with unique names and inspect the JAR contents.

**Appending to bootstrap does not turn a helper into a named module with access to all modules, nor does it revive a previously failed reference resolution.**

### 3.2. System Class Loader Search

~~~java
// Illustrative code inside a Java agent with Instrumentation inst.
inst.appendToSystemClassLoaderSearch(helperJar);
~~~

This method adds JAR entries to the class search sources of the **system loader** when the system loader supports the instrumentation append mechanism. According to the Java SE 17 Javadoc:

- It can be called multiple times, following the order of appended JARs.
- It **does not modify the value** of the `java.class.path` system property.
- It may throw `UnsupportedOperationException` if a custom system loader does not support it.
- The `appendToClassPathForInstrumentation(String)` method on the system loader is a supporting mechanism that the API relies on; this method does not have to be `public`.
- It does not force existing classes to re-resolve previously failed method/field/class references.

Both APIs accept a `JarFile`, not a classes directory or an arbitrary classpath string. Do not describe them as "changing the JVM-wide classpath" in a way that ignores class-loader delegation and the module graph.

### 3.3. Comparison Table: "Extending the Search Path" vs. "Fixing a Resolution Result"

| Scenario | Can Append Help? | Explanation |
|---|---|---|
| Searching for a helper never looked up before, after appending to the right loader | **Possibly** | The loader gains an additional class source |
| A call site has never resolved the reference, and the helper is now visible | **Possibly** | The first resolution attempt can succeed |
| A symbolic reference already failed **before** append | **No** | The JVMS preserves the failure result of that reference |
| A symbolic reference already resolved successfully to an old class/method | **Does not replace resolved entity** | Append does not replace an already loaded class |
| A custom plugin loader does not delegate to the appended loader | **Not guaranteed** | Depends on loader topology |
| A named module lacks read/export/open access to the helper | **Not sufficient** | JPMS access must be handled separately |
| Wanting to re-run a static initializer that previously failed | **No** | That is a separate initialization state |
| Wanting to transform the body of a currently running method | **No** | Requires valid Instrumentation redefine/retransform, not append |

## 4. Why Does the Old Call Still Fail After Appending?

A typical timeline:

~~~text
t0. JVM defines OldCaller.
t1. OldCaller.read() uses Methodref #N for the first time.
t2. JVM attempts to resolve #N; helper cannot be found -> error.
t3. Java agent appends helper.jar to the system search.
t4. System loader can now find BridgeHelper from helper.jar.
t5. OldCaller.read() uses the same #N again -> still gets the old resolution error.
t6. NewCaller.read() has its own Methodref -> first resolution succeeds.
~~~

**Points t4 and t5 answer two different questions.** At t4, we ask *can the loader load this class if searched now?* At t5, we ask *will the JVM retry resolving the same failed reference?* According to the specification, no.

### Is This a Class Loader Negative Cache?

Do not conflate the two mechanisms:

1. Some custom `ClassLoader` implementations may memoize/negative-cache a class name that was not found. That is a loader/implementation detail.
2. The JVM Specification has its own rule for **the resolution result of symbolic references in the runtime constant pool**.

A loader can find the class successfully **after appending**, while `OldCaller` using the old reference still fails. That is proof that diagnosing solely by checking "whether the loader can read the JAR" is not enough.

### `NoClassDefFoundError` vs. `ClassNotFoundException`

`ClassNotFoundException` is a checked exception that typically comes from APIs requested to find a class by name, such as `Class.forName`. `NoClassDefFoundError` is a `LinkageError` that can occur when the JVM needs a class definition during linking/resolution but no suitable class is available, even though the bytecode containing the reference was compiled earlier.

Do not write production logic assuming **every** `NoClassDefFoundError` is caused by a missing JAR; a class initialization failure can also cause a class to be marked erroneous, and subsequent uses will hit `NoClassDefFoundError: Could not initialize class ...`. Inspect the stack trace, `Caused by`, and the first failure.

## 5. Java 17+ Hands-On: Two Call Sites and One Helper JAR

The experiment will produce:

~~~text
OldCaller.read() before append -> NoClassDefFoundError
Agent appends helper.jar       -> append succeeds
Class.forName(BridgeHelper)    -> class lookup succeeds
OldCaller.read() after append  -> NoClassDefFoundError
NewCaller.read() after append  -> READY
~~~

**Why use two callers?** Each class contains a symbolic method reference in its **own constant pool**. We intentionally make `OldCaller`'s reference fail before appending, and then test `NewCaller`'s reference, which has never been used before.

The demo uses a **startup agent** to obtain `Instrumentation` upfront without having to attach to a running JVM. The agent will **not append the helper in `premain`**; the application explicitly calls the append API **after triggering the first failure**. This is an experimental setup, **not a recommended production strategy**.

### 5.1. Directory Tree

~~~text
resolution-demo/
├── AGENT.MF
├── src/
│   ├── helper/demo/helper/BridgeHelper.java
│   ├── agent/demo/agent/SearchAgent.java
│   └── app/demo/app/
│       ├── OldCaller.java
│       ├── NewCaller.java
│       └── App.java
└── out/
    ├── helper/
    ├── agent/
    ├── app/
    ├── helper.jar
    └── search-agent.jar
~~~

There are **five Java files** and **one manifest**. All of them use APIs available in Java 17. The example was compiled with `javac --release 17` and run compatibly on JDK 24; no ASM, Byte Buddy, or Attach API is required.

### 5.2. File `src/helper/demo/helper/BridgeHelper.java`

~~~java
package demo.helper;

public final class BridgeHelper {
    private BridgeHelper() {}

    public static String value() {
        return "READY";
    }
}
~~~

A simple static method allows verifying the exact result without depending on mutable state or I/O. This class is packaged into a separate JAR and is **not on the initial runtime classpath**.

### 5.3. File `src/app/demo/app/OldCaller.java`

~~~java
package demo.app;

import demo.helper.BridgeHelper;

public final class OldCaller {
    private OldCaller() {}

    public static String read() {
        return BridgeHelper.value();
    }
}
~~~

With `javac`, the `read()` method has a symbolic reference to `demo/helper/BridgeHelper.value:()Ljava/lang/String;`. The build must include the helper JAR on the **compile-time classpath** for type-checking; however, the helper file does not have to be on the runtime classpath when `OldCaller` first runs.

### 5.4. File `src/app/demo/app/NewCaller.java`

~~~java
package demo.app;

import demo.helper.BridgeHelper;

public final class NewCaller {
    private NewCaller() {}

    public static String read() {
        return BridgeHelper.value();
    }
}
~~~

The code in the `read` method is identical to `OldCaller`, but this is a **different class** with a different constant pool. The program only calls `NewCaller.read()` **after** the helper JAR has been appended. We do not assume they share a reference just because their method names or source code are identical.

### 5.5. File `src/agent/demo/agent/SearchAgent.java`

~~~java
package demo.agent;

import java.lang.instrument.Instrumentation;
import java.nio.file.Path;
import java.util.jar.JarFile;

public final class SearchAgent {
    private static Instrumentation instrumentation;
    private static JarFile keptOpen;

    private SearchAgent() {}

    public static void premain(String arg, Instrumentation inst) {
        instrumentation = inst;
    }

    public static synchronized void append(Path jarPath) throws Exception {
        if (keptOpen != null) {
            throw new IllegalStateException("already appended");
        }

        JarFile jar = new JarFile(jarPath.toFile());
        instrumentation.appendToSystemClassLoaderSearch(jar);
        keptOpen = jar;

        System.out.println("[agent] appended");
    }
}
~~~

Explanation:

- `premain` stores the `Instrumentation` instance given to the agent by the JVM; it **does not append immediately** because the exercise needs to trigger a failure in `OldCaller`.
- `append(Path)` opens the actual file using `JarFile` and then calls the API to extend the system loader's search path.
- `keptOpen` holds a reference to the appended JAR for the short lifetime of the demo; there is a guard to prevent repeated appends. Production applications need explicit lifecycle and cleanup design.
- A custom system loader that does not support appending may throw `UnsupportedOperationException`. This example uses the default system loader on a standard JDK.
- Neither `Can-Retransform-Classes` nor `Can-Redefine-Classes` is needed; we do not modify any classfiles.

### 5.6. File `src/app/demo/app/App.java`

~~~java
package demo.app;

import demo.agent.SearchAgent;
import java.nio.file.Path;

public final class App {
    private App() {}

    private static void oldCall(String phase) {
        try {
            System.out.println(
                    "[app] " + phase + "=" + OldCaller.read());
        } catch (NoClassDefFoundError error) {
            System.out.println(
                    "[app] " + phase + "=NoClassDefFoundError");
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "helper JAR path required");
        }

        // 1) Intentionally trigger a symbolic-reference resolution failure.
        oldCall("before");

        // 2) Extend the search path after the first error.
        SearchAgent.append(Path.of(args[0]).toAbsolutePath());

        // 3) A separate class lookup operation can now succeed.
        System.out.println(
                "[app] load="
                + Class.forName("demo.helper.BridgeHelper").getName());

        // 4) Same old symbolic reference => still fails.
        oldCall("after");

        // 5) Symbolic reference from another class => can succeed.
        System.out.println(
                "[app] fresh=" + NewCaller.read());
    }
}
~~~

In the demo, `oldCall` catches `NoClassDefFoundError` to print a stable string that is easy to compare. **Do not copy this pattern of swallowing linkage errors into production.** If a real application throws an error, preserve the stack trace and cause to know the exact location/type of the error. The catch block here is solely for the experiment.

### 5.7. Manifest File `AGENT.MF`

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.SearchAgent

~~~

Make sure the manifest ends with a newline and `Premain-Class` is in the **main section**. `jar cfm` packages the manifest as `META-INF/MANIFEST.MF` of the agent JAR.

### 5.8. Compile in the Exact Order

Create the output directories from the `resolution-demo` root.

**Bash / macOS / Linux:**

~~~bash
mkdir -p out/helper out/agent out/app
~~~

**PowerShell / Windows:**

~~~powershell
New-Item -ItemType Directory -Force out/helper, out/agent, out/app | Out-Null
~~~

Compile the helper and package the JAR:

~~~bash
javac --release 17 -d out/helper src/helper/demo/helper/BridgeHelper.java
jar cf out/helper.jar -C out/helper .
~~~

Compile the agent and package the JAR with the manifest:

~~~bash
javac --release 17 -d out/agent src/agent/demo/agent/SearchAgent.java
jar cfm out/search-agent.jar AGENT.MF -C out/agent .
~~~

**When compiling the application, both the helper JAR and the agent JAR must be visible.** Use `:` on Unix:

~~~bash
javac --release 17 -cp "out/helper.jar:out/search-agent.jar" -d out/app src/app/demo/app/OldCaller.java src/app/demo/app/NewCaller.java src/app/demo/app/App.java
~~~

Use `;` on Windows:

~~~powershell
javac --release 17 -cp "out/helper.jar;out/search-agent.jar" -d out/app src/app/demo/app/OldCaller.java src/app/demo/app/NewCaller.java src/app/demo/app/App.java
~~~

**Mandatory condition of the experiment:** although `out/helper.jar` is on the **compile-time classpath**, **do not add it to the runtime `-cp`** in the next step. If the helper is present from the start, the initial symbolic resolution error will not occur.

### 5.9. Run with the Exact Runtime Classpath

**Bash / macOS / Linux:**

~~~bash
java -javaagent:out/search-agent.jar -cp "out/app:out/search-agent.jar" demo.app.App out/helper.jar
~~~

**Windows:**

~~~powershell
java -javaagent:out/search-agent.jar -cp "out/app;out/search-agent.jar" demo.app.App out/helper.jar
~~~

`out/helper.jar` is only an **application argument** for `SearchAgent` to open **after** the first failure. It is **not** on the classpath when `OldCaller.read()` runs for the first time.

**Verified stdout on the test JDK:**

~~~text
[app] before=NoClassDefFoundError
[agent] appended
[app] load=demo.helper.BridgeHelper
[app] after=NoClassDefFoundError
[app] fresh=READY
~~~

The experiment compiled all sources with `--release 17` and ran successfully on JDK 24 (Java 17 target). The lines above reflect the default system class loader environment and must not be extrapolated as a guarantee for all custom class loaders, module topologies, or JVM policies.

### 5.10. Interpreting the Results

| Line | What Is Actually Proven |
|---|---|
| `before=NoClassDefFoundError` | The reference in `OldCaller` failed when the helper was not yet visible |
| `[agent] appended` | The API to add the JAR to the system search returned |
| `load=demo.helper.BridgeHelper` | A separate class loading request after appending found the helper |
| `after=NoClassDefFoundError` | The old reference of `OldCaller` remained in a failed state |
| `fresh=READY` | A separate reference in `NewCaller` resolved successfully after appending |

Two claims must be separated: **the agent JAR was appended successfully** and **the old execution path was healed**. Only the first claim is supported by the `[agent] appended` log; the final lines prove that the old call site **was not healed**, even though the search path was extended.

## 6. Inspecting Symbolic References with `javap`

From the demo directory, run:

~~~bash
javap -classpath out/app -c -v demo.app.OldCaller
javap -classpath out/app -c -v demo.app.NewCaller
~~~

Look for:

~~~text
Constant pool:
  #N = Methodref ... demo/helper/BridgeHelper.value:()Ljava/lang/String;
Code:
  invokestatic #N
  areturn
~~~

The `#N` index varies by compiler/build details; do not hard-code it. Each class file has its own constant pool, even when the text of the method reference is identical.

To verify the JARs contain the right files:

~~~bash
jar tf out/helper.jar
jar tf out/search-agent.jar
~~~

`helper.jar` must contain `demo/helper/BridgeHelper.class`. `search-agent.jar` must contain `META-INF/MANIFEST.MF` and `demo/agent/SearchAgent.class`. Inspect the actual artifacts instead of assuming `.java` files were compiled properly into the JARs.

If HotSpot class-loading logs are available, use `-Xlog:class+load=info` to examine class sources; however, **class-load logs cannot replace evidence of a resolution failure for a runtime constant-pool entry**.

## 7. Types of "Success" and "Failure" Commonly Confused

### 7.1. `Class.forName` Succeeding Does Not Restore `OldCaller`

After appending, the following test can succeed:

~~~java
Class<?> helper = Class.forName(
        "demo.helper.BridgeHelper",
        false,
        ClassLoader.getSystemClassLoader()
);
System.out.println(helper.getName());
~~~

It answers *can the loader find the class now?* rather than changing the previous resolution result. The `initialize=false` overload avoids **requiring immediate class initialization**, but it does not reset JVM state either.

Conversely, if `Class.forName` fails after appending, it could be due to the wrong JAR, wrong class entry, a loader that does not support appending, unexpected delegation, or JPMS access. **You cannot yet conclude** that it is the cached symbolic-reference mechanism from an old call site.

### 7.2. Changing the `java.class.path` System Property Does Not Extend Class Loader Search

~~~java
System.setProperty("java.class.path", "another.jar");
~~~

That updates a **system property**, not an Instrumentation API call to change class search sources. Even a real `appendToSystemClassLoaderSearch` call **does not change** the value of `java.class.path`, according to the Javadoc.

Verify that an append succeeded by performing **a new class load** through the appropriate loader, not by printing the property.

### 7.3. Symbolic-Reference Failure vs. Class Initialization Failure

Two situations can both show `NoClassDefFoundError` yet have different root causes:

~~~text
Missing class during resolution:
    OldCaller Methodref -> helper cannot be loaded yet
    -> resolution error of constant-pool reference
    -> appending later does not automatically re-resolve the old reference

Class initialization failure:
    BridgeHelper already loaded
    -> <clinit> throws an exception
    -> class is in an erroneous state
    -> subsequent uses may throw NoClassDefFoundError
    -> appending a JAR does not reset class initialization either
~~~

Therefore, you must preserve **the first failure**, `Caused by`, and the stack trace. For `ExceptionInInitializerError`/`Could not initialize class`, do not mechanically apply the "need to append JAR" fix.

### 7.4. Method/Field or Access Errors Are Also Resolution

`NoSuchMethodError`, `NoSuchFieldError`, `IllegalAccessError`, and other `LinkageError`s can arise from symbol/member resolution or access checks. Attaching a JAR containing a class with the same name **does not** make the JVM replace an already loaded class with a new definition. To change a method body or module permissions, you must use the corresponding mechanism, and any already recorded symbolic-reference error still needs to be accounted for.

## 8. **When** Should a Java Agent Prepare Helpers?

### 8.1. Startup Agent: Correct Ordering in `premain`

A more reliable sequence:

~~~text
JVM starts
     |
     v
premain(args, Instrumentation)
     |
     +-- identify small, properly sourced helper JAR
     +-- append to appropriate bootstrap or system search
     +-- prepare module access / helper visibility if needed
     +-- only then register transformers
     |
     v
Application loads business classes
     |
     +-- transformer emits bytecode calling helper
     |
     v
First resolution of helper reference -> class is already visible
~~~

If an agent instruments a class and lets bytecode call the helper **before** the helper JAR is appended, the agent itself can create a persistent resolution failure. Treat "helper ready before first resolution" as **a design invariant**, not an implementation detail whose order can be arbitrarily swapped.

### 8.2. Attach Agent: Already Loaded Classes Must Also Be Considered

In `agentmain`, many classes have already been loaded. Tooling can:

1. Check attach/dynamic agent loading permissions and the available `Instrumentation`.
2. Append the helper JAR to the appropriate loader search **before** instrumenting further.
3. Determine the loader identity and module readability/exports/opens of the target classes.
4. Register the transformer, check JVM capabilities, and then request `retransformClasses` for selected modifiable classes if already-loaded classes need instrumentation.
5. **Do not promise** that a retransform/redefine call will clear all old symbolic-resolution failures. These APIs are meant to change class definitions/transformations under their own constraints, not specified as `clearResolutionErrors()`.

What must be distinguished is **inserting a new reference into bytecode after the helper is visible** versus **a call site that already had an old reference and already failed**. A good instrumentation framework must analyze both situations.

### 8.3. Bootstrap Helper JAR: Minimal Package and Dependencies

A helper used by bytecode of a bootstrap class must reside in a loader that is visible to it. However, a bootstrap helper should not directly depend on libraries that only exist in the application loader; if a bootstrap helper calls an app class that is not visible, you can trigger a `NoClassDefFoundError` in the reverse direction.

A bridge design typically splits into a very small bootstrap helper API and an implementation in an appropriate loader. If using this pattern, you must check method descriptors, loader constraints, module visibility, and lifecycle. The helper package must be self-contained to avoid parent-loader collisions.

### 8.4. Named Modules and Access Permissions

Appending a JAR to the system/bootstrap search does not automatically:

- Grant a named module `requires` or readability to the module containing the helper.
- Export/open the helper's package to all modules.
- Change the package identity of a custom-loader class.
- Make other class loaders automatically see a JAR they do not delegate to.

`Instrumentation.redefineModule(...)` can help adjust certain JPMS relationships when valid, but **it has no retroactive effect on a symbolic reference that has already failed resolution**. The JVMS even gives an example: a type that was rejected during resolution because its package was not exported continues to fail for that reference even if the export is added later.

## 9. Remediation: Do Not Fix the Wrong Layer

| Strategy | When Appropriate | Limitations |
|---|---|---|
| Put helper on runtime classpath/module path at startup | Normal application dependency | Must choose the right loader and module |
| Append helper in `premain` before instrumented bytecode runs | Instrumentation helper needs to appear early | Does not fix references that failed before `premain` |
| Attach early, append helper, then retransform allowed classes | Running JVM, agent has permissions and capabilities | Already-failed references are not healed automatically |
| Create a **new class definition/call site** in a controlled loader/lifecycle | Plugin/hot-reload architectures that support it | Changes class identity and affects state/compatibility |
| Restart with the helper ready from the beginning | Old call site has no safe way to recover | Requires restart/rolling deployment planning |

**There is no standard Java API to "clear cached symbolic reference resolution failure"** to call after appending. If the state is already broken and strict correctness is required, restarting with dependencies in place on time is usually more reliable than trying to call `Class.forName` or appending repeatedly.

## 10. Diagnostic Checklist When Errors Persist After Appending

1. **Check the root error:** Is `NoClassDefFoundError` caused by a missing class, class initialization, or member resolution? Record `Caused by` and the first stack trace.
2. **Check the timing:** Was the call site's reference used before the append or not?
3. **Inspect caller bytecode:** Use `javap -c -v` to identify the instruction and corresponding class/method/field reference.
4. **Check the defining loader:** Having the same name does not guarantee the same class identity. Check the exact loader the caller uses.
5. **Inspect the JAR:** Run `jar tf` to confirm the binary name and package path inside the file.
6. **Check the append API:** Bootstrap or system? Does a custom system loader support appending?
7. **Test a new class lookup:** Try via the appropriate loader to separate search-path issues from resolution-failure history.
8. **Test a new call site:** Can a caller/reference that has never failed use the helper?
9. **Check JPMS:** Are module reads/exports/opens satisfied, especially for classes in named modules?
10. **Distinguish logs:** `append returned` ≠ `fresh class load succeeded` ≠ `old call site repaired`.
11. **Evaluate recovery strategy:** If the error is cached, do not retry infinitely; consider restarting or designing new classes per policy.
12. **Verify end-to-end:** Helper visibility is not enough; the instrumented functionality must actually run correctly.

Self-designed log sample (not a standard JDK log):

~~~text
helperJarOpened=true
appendToSystemClassLoaderSearch=returned
freshClassLookup=success
oldCallerResolution=failed
freshCallerResolution=success
~~~

These statuses provide evidence along two different axes: **class discovery** and **symbolic reference resolution**.

## 11. Common Misconceptions

### Myth 1 — "Appending a JAR makes the JVM retry every symbolic reference"

False. The JVM Specification requires a reference that failed resolution to continue failing with the old error. Appending changes class lookup sources **for the future**, not already-determined resolution results.

### Myth 2 — "`Class.forName` succeeding means the old method will succeed too"

False. `Class.forName` is a separate loading operation; the old method may be using a constant-pool reference that already failed. The demo shows both outcomes in the same process.

### Myth 3 — "A failed class name is broken across the entire JVM"

False. The error rule applies to **a specific symbolic reference**. Other classes/loaders can have their own references and behave differently.

### Myth 4 — "`java.class.path` must change after appending"

False. The Javadoc for `appendToSystemClassLoaderSearch` explicitly states it does not update this property.

### Myth 5 — "Just put all libraries into the bootstrap helper JAR"

Dangerous. Class-name collisions, class loader identity, package-private access, and module boundaries can be broken. Bootstrap helpers should be minimal and use their own namespace.

### Myth 6 — "`NoClassDefFoundError` is always a missing class"

No. Failed class initialization, linkage/access errors, and other forms require separate diagnosis. Do not ignore the first error and cause.

### Myth 7 — "Calling `retransformClasses` definitely clears the error cache"

Not specified. Retransformation replaces bytecode within limits; it is not a mechanism to reset all historical resolution state.

### Myth 8 — "Changing the `java.class.path` property fixes the class loader by itself"

No. A system property is not an append call, nor does it clear failed resolution state.

## 12. Self-Check Knowledge Questions

**Q1.** If `OldCaller` has already failed to resolve a reference to `Helper`, does appending the helper JAR automatically make that method stop failing?

> No. JVM Specification `5.4.3` specifies that re-resolving the same symbolic reference continues to receive the error from the previous attempt.

**Q2.** Why can `NewCaller` still call the helper after appending?

> NewCaller has its own runtime constant pool and a reference that has never failed resolution. After appending, the loader can find the helper, so the new reference can succeed.

**Q3.** What does `Class.forName` succeeding after appending prove?

> It proves that a new class lookup request through that loader succeeded; it does not prove that an old reference in another caller was reset.

**Q4.** What is the main difference between the two append APIs?

> One API extends the bootstrap search, while the other extends the system loader search when the system loader supports it. Choose based on the loader visibility of the classes that will use the helper.

**Q5.** After `appendToSystemClassLoaderSearch`, does `java.class.path` change automatically?

> No. The Javadoc explicitly states the API does not change this system property.

**Q6.** Is every `NoClassDefFoundError` in production a cached resolution failure?

> No. There may be class initialization issues, bytecode dependencies, class loader issues, or other module issues. Check the cause and first failure before concluding.

**Q7.** Why does a bootstrap helper JAR need an independent namespace and minimal dependencies?

> To reduce the risk of class-name collisions due to parent delegation, type/loader mismatches, and `IllegalAccessError` when classes are supposed to be defined by another loader.

**Q8.** What is the simplest strategy to avoid this error in a newly deployed application?

> Ensure the helper JAR is visible in the right loader/module **before the first symbolic reference is resolved**, typically via the startup classpath or early appending in `premain`.

**Q9.** If an old method has already failed, should you repeatedly call `Class.forName` until it stops failing?

> No. `Class.forName` succeeding does not clear the failure of the old reference; retrying does not target the JVM state that needs to be addressed.

**Q10.** If attaching an agent late, why must you be careful with helpers that callers have already referenced?

> The JVM may have already recorded resolution errors for those references before the agent appended the helper. Simply extending the search path cannot fix the linking history of those call sites.

## 13. Official References

- Java SE 17, `Instrumentation` — `appendToBootstrapClassLoaderSearch`, `appendToSystemClassLoaderSearch`, and the official warning regarding previously failed reference resolutions: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
- JVM Specification Java SE 17, `5.4.3 Resolution` — rules for recording symbolic-reference resolution results and the error from the first attempt: https://docs.oracle.com/en/java/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3
- JVM Specification Java SE 17, `5.3 Creation of Classes and Interfaces` — loader identity, class definition/creation: https://docs.oracle.com/en/java/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- JVM Specification Java SE 17, `5.5 Initialization` — class initialization state upon failure: https://docs.oracle.com/en/java/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5
- Java SE 17, `ClassLoader` — delegation and loading: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17, `JarFile` — JAR source used for Instrumentation append: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarFile.html
