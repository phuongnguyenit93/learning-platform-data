# Identifying the Bootstrap Class Loader via `loader == null` in `ClassFileTransformer`

## 1. Problem to Solve

When writing a Java agent or instrumentation tool, the `ClassFileTransformer.transform(...)` method receives a `ClassLoader loader` parameter. This value indicates the **class loader that defines the class being processed** (*defining loader*). In the Java Instrumentation contract:

> **If `loader == null`, the class being transformed is defined by the bootstrap class loader.**

The bootstrap loader is the JVM's core class-loading mechanism, typically not represented by a directly usable Java `ClassLoader` object. Therefore, the API uses `null` as a **sentinel value**, rather than meaning "unknown class loader", "missing dependency", or "broken callback".

For example, a transformer that tracks both application code and core classes can handle them differently:

```java
if (loader == null) {
    // Class is defined by the bootstrap loader.
} else {
    // Class is defined by a concrete Java ClassLoader.
}
```

This is a check for the **identity of the class-defining source**. It does not by itself prove whether a class belongs to the JDK or the application, does not reflect permission levels, does not guarantee the class is modifiable, and does not indicate which thread the class is running on.

This lesson belongs to the **transformer contract** section: accurately understanding the callback semantics, easily confused cases, and how to observe `loader == null` without relying on whether a JDK class happened to be loaded before the agent was registered.

## 2. Review of Common Loaders on Java 17+

| Loader Type | Typical Role | Value in `transform` |
| --- | --- | --- |
| **Bootstrap** | Defines foundational classes, e.g., `java.lang.Object`, `java.lang.String`; search path can be extended via the instrumentation API | **`null`** |
| **Platform** | Defines certain platform/JDK module classes depending on runtime configuration | **Non-null** `ClassLoader` object |
| **System/application** | Typically defines classes on the application classpath | **Non-null** `ClassLoader` object |
| **Custom loader** | Loaders for plugins, frameworks, application containers, test runtimes, etc. | **Non-null** loader object |

API examples:

```java
ClassLoader platform = ClassLoader.getPlatformClassLoader();
ClassLoader system = ClassLoader.getSystemClassLoader();
```

In common Java 17 JVMs, both `platform` and `system` are actual Java objects. **Do not use `ClassLoader.getPlatformClassLoader() == null` to identify the bootstrap loader**: the bootstrap loader is **distinct** from the platform loader. Nor should you assume the system always has only three loaders; frameworks can create many of their own loaders.

### How Does "Defining" Differ from "Initiating"?

Java class loading typically follows a **delegation** model. For example, the system class loader is asked to find `java.lang.String` but delegates the request to the bootstrap loader; the actual class is still **defined by the bootstrap loader**.

```text
App/System loader  --- requests java.lang.String ---+
                    (initiating loader)           |
                                                   v
                                        Bootstrap loader
                                        (defining loader)
                                                   |
                                                   v
                                         class java.lang.String
                                         getClassLoader() == null
```

Therefore, in a transformer, `loader` represents the **defining loader**, not the "first loader invoked" or a parent loader consulted in the delegation chain.

In particular, the **Thread Context ClassLoader (TCCL)** obtained via `Thread.currentThread().getContextClassLoader()` must not be used in place of `loader`. The TCCL may be set by a framework or application to a system/custom loader while the class being processed by the transformer belongs to the bootstrap loader.

## 3. Reading the Contract of Both `transform` Overloads Correctly

Java 17 has two callback methods:

**Legacy form:**

```java
byte[] transform(
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain protectionDomain,
        byte[] classfileBuffer);
```

**Module-aware form (Java 9+):**

```java
byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain protectionDomain,
        byte[] classfileBuffer);
```

In **both forms**, `loader == null` indicates the **bootstrap defining loader**. The `module` parameter helps distinguish classes according to the Java Platform Module System, and **does not replace** loader information.

The other parameters have **independent** meanings:

- `className`: class name in **internal form** using `/`, e.g., `java/lang/String` and `demo/boot/BootProbe`, not the binary name with `.`. Always handle the case where the class name is unavailable if special cases need to be supported.
- `classBeingRedefined`: `null` during normal class definition; may be non-null when the callback is triggered by redefine/retransform.
- `protectionDomain`: the protection domain associated with the class definition; do not use it as a substitute indicator for bootstrap.
- `classfileBuffer`: bytes of the class at the transformation stage; **do not modify the input array in place**. Return `null` when no transformation is desired; if modifying, return a new `byte[]` containing a valid class file.

Do not confuse:

| Condition | Meaning |
| --- | --- |
| `loader == null` | Class is defined by the **bootstrap loader** |
| `classBeingRedefined == null` | Callback is an initial definition, not a redefine/retransform |
| `className == null` | Class name is unavailable/not applicable in a special case; does not imply the loader |
| `transform(...)` returns `null` | Transformer does not replace the bytecode in this pass |
| `Thread.currentThread().getContextClassLoader() == null` | The thread's TCCL state, **not** a direct indicator of the defining loader of the class being transformed |

An important detail: on Java 17, both `transform` methods have default implementations in the interface. **Do not write a lambda assuming `ClassFileTransformer` is a functional interface**. Use an implementing class or an anonymous class and `@Override` the desired method. If you override the 5-parameter form, the default implementation of the `Module`-aware form delegates to it.

## 4. How to Write a Transformer That Safely Identifies Bootstrap

Example **illustrative snippet** placed inside `premain(String, Instrumentation)` or `agentmain(String, Instrumentation)`; the snippet below alone is not a standalone runnable program:

```java
inst.addTransformer(new ClassFileTransformer() {
    @Override
    public byte[] transform(
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain protectionDomain,
            byte[] classfileBuffer) {

        if ("java/lang/String".equals(className)
                || "demo/boot/BootProbe".equals(className)) {

            String kind = loader == null
                    ? "bootstrap"
                    : "non-bootstrap";

            System.out.println(className + " -> " + kind);
        }

        return null; // Do not modify bytecode.
    }
});
```

To compile this snippet in an agent class, the following imports are needed:

```java
import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;
```

Why check `"literal".equals(className)`? If a callback has `className == null`, this comparison avoids throwing a `NullPointerException`. Filtering for specific classes also reduces the risk of the agent flooding logs while the JVM loads many classes.

**Do not write:**

```java
loader.loadClass("example.Helper");
```

before checking `loader != null`. For a bootstrap class, this statement throws a `NullPointerException`. Even when `loader` is non-null, loading classes directly from inside `transform` can cause recursion, deadlocks, or altered load order; adding dependencies for transforming core classes requires careful design.

## 5. Why Can't You Just Filter by the `java/` Name or Inspect `getClassLoader()`?

### 5.1. A Prefix Does Not Prove the Defining Loader

The following is **incorrect**:

```java
boolean bootstrap = className.startsWith("java/");
```

Some platform/JDK classes are defined by the platform loader, and loader assignment depends on the module/runtime. Conversely, instrumentation can instruct the bootstrap loader to search for helper classes in an external JAR, whose packages **do not start with `java/`**.

Conclusions based on package names will fail when the JVM has other loaders or when an agent extends the bootstrap search path. **The source of truth is the callback's `loader`.**

### 5.2. `Class.getClassLoader() == null` Requires Understanding Its Scope

On a typical Java 17 HotSpot JVM:

```java
String.class.getClassLoader() == null
```

is `true` because `String` is defined by the bootstrap loader. However:

```java
int.class.getClassLoader() == null
int[].class.getClassLoader() == null
```

are also both `true`. Primitive types (`int`, `void`) are not defined from a class file like normal Java classes; array classes are created by the JVM according to special rules. **Do not infer that `int.class` or `int[].class` ever triggered a `ClassFileTransformer.transform` callback just because the loader is null.**

According to the `Class.getClassLoader()` contract, primitive types and `void` return `null`. An array class has the loader of its element type; an array of primitives has no class loader. When checking **a normally defined class**, `clazz.getClassLoader() == null` is a useful indicator to associate with bootstrap; when checking arbitrary `Class<?>` objects, primitives/arrays must be excluded if you are referring to transformable class files.

### 5.3. Classes Loaded Before the Agent Do Not Automatically Pass Through a New Transformer

`java.lang.String` is typically already present from JVM startup **before `premain` registers a transformer**. If you add a transformer and then call `String.class.getClassLoader()`, you will see `null` even though you **never received a callback** for `java/lang/String`.

A normally registered transformer processes class definitions **after** the point of registration; it does not automatically replay class loading history. To affect already-loaded classes, you must consider `Instrumentation.retransformClasses` and the corresponding capabilities/limitations. The next hands-on example will deliberately create an unloaded bootstrap class to avoid depending on JVM timing.

## 6. Practice A: Observing Java Class Loaders Without an Agent

Create the file **`LoaderFacts.java`**:

```java
public class LoaderFacts {
    public static void main(String[] args) throws Exception {
        Class<?> stringViaSystem = Class.forName(
                "java.lang.String",
                false,
                ClassLoader.getSystemClassLoader());

        System.out.println("String bootstrap=" +
                (String.class.getClassLoader() == null));
        System.out.println("String via system still bootstrap=" +
                (stringViaSystem.getClassLoader() == null));
        System.out.println("App bootstrap=" +
                (LoaderFacts.class.getClassLoader() == null));
        System.out.println("Primitive loader null=" +
                (int.class.getClassLoader() == null));
        System.out.println("Primitive array loader null=" +
                (int[].class.getClassLoader() == null));
    }
}
```

Using JDK 17+:

```bash
javac --release 17 LoaderFacts.java
java LoaderFacts
```

On a typical JDK 17+ runtime with a system/application loader, expected stdout:

```text
String bootstrap=true
String via system still bootstrap=true
App bootstrap=false
Primitive loader null=true
Primitive array loader null=true
```

Key takeaways:

- When requested through the system loader, `String` is **still defined by the bootstrap loader**; the loader argument passed to `Class.forName` is the loader asked to find it, and does not change the class's defining loader.
- `LoaderFacts` is defined by the application loader when run with `java LoaderFacts` on the standard classpath.
- The last two lines prove that checking `getClassLoader() == null` is **not sufficient** to claim that a class-file transformer callback occurred.

This example does not initialize a Java agent; it inspects loader identity on `Class` objects.

## 7. Practice B: A Java Agent Proactively Observing a Callback with `loader == null`

### 7.1. Experiment Design

To reliably receive a bootstrap loader callback in an environment that supports instrumentation, we create a small class in a separate JAR, then call:

```java
instrumentation.appendToBootstrapClassLoaderSearch(
        new JarFile("bootstrap-probe.jar"));
```

This API **adds the JAR to the list that the bootstrap loader will search**. Next, the application uses `Class.forName(name, true, null)` to ask the bootstrap loader to define that class. The chosen class has never been loaded before the agent starts, so the observed callback is meaningful.

Directory structure:

```text
demo/
├── src/
│   └── demo/
│       ├── agent/
│       │   └── LoaderAgent.java
│       ├── boot/
│       │   └── BootProbe.java
│       └── app/
│           ├── AppProbe.java
│           └── DemoApp.java
└── agent.mf
```

Create the exact five source/manifest files below. The `classes/` directory and the three JARs will be created by the compile/package commands.

### 7.2. File `src/demo/boot/BootProbe.java`

```java
package demo.boot;

public final class BootProbe {
    private BootProbe() {
    }

    public static String message() {
        return "from bootstrap";
    }
}
```

The `BootProbe` class intentionally depends only on `java.lang`, with no dependency on application classes. The bootstrap loader must be able to link all dependencies used by this class on its own.

### 7.3. File `src/demo/app/AppProbe.java`

```java
package demo.app;

public final class AppProbe {
    private AppProbe() {
    }

    public static String message() {
        return "from application";
    }
}
```

This class will be packaged in the **application JAR**, separate from `bootstrap-probe.jar`.

### 7.4. File `src/demo/agent/LoaderAgent.java`

```java
package demo.agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;
import java.util.jar.JarFile;

public final class LoaderAgent {
    // Keep the JarFile reference alive for the example JVM's lifetime.
    private static JarFile bootstrapJar;

    private LoaderAgent() {
    }

    public static void premain(String args, Instrumentation inst)
            throws Exception {

        bootstrapJar = new JarFile("bootstrap-probe.jar");
        inst.appendToBootstrapClassLoaderSearch(bootstrapJar);

        inst.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(
                    ClassLoader loader,
                    String className,
                    Class<?> classBeingRedefined,
                    ProtectionDomain protectionDomain,
                    byte[] classfileBuffer) {

                if ("demo/boot/BootProbe".equals(className)
                        || "demo/app/AppProbe".equals(className)) {

                    String owner = loader == null
                            ? "bootstrap"
                            : "non-bootstrap";

                    System.out.println("[transform] " +
                            className + ": " + owner);
                }

                // Do not modify any bytecode.
                return null;
            }
        }, false);
    }
}
```

The agent does two things **before `main`**:

1. Opens `bootstrap-probe.jar` and appends it to the bootstrap loader's search path.
2. Registers a transformer that observes the two class names, prints the corresponding loader, and always returns `null`.

Because the example only observes newly loaded classes, `addTransformer(..., false)` is sufficient; `Can-Retransform-Classes` is **not needed** in the manifest.

Note that `ClassFileTransformer` here uses an **anonymous class** and overrides the 5-parameter method. Java 17 has a default implementation of the 6-parameter callback that delegates to this form, so the pattern is suitable for Java 17+.

### 7.5. File `src/demo/app/DemoApp.java`

```java
package demo.app;

public final class DemoApp {
    private DemoApp() {
    }

    public static void main(String[] args) throws Exception {
        Class<?> boot = Class.forName(
                "demo.boot.BootProbe", true, null);

        System.out.println("[main] bootLoaderNull=" +
                (boot.getClassLoader() == null));
        System.out.println("[main] bootValue=" +
                boot.getMethod("message").invoke(null));

        Class<?> app = Class.forName(
                "demo.app.AppProbe",
                true,
                ClassLoader.getSystemClassLoader());

        System.out.println("[main] appLoaderNull=" +
                (app.getClassLoader() == null));
        System.out.println("[main] appValue=" +
                app.getMethod("message").invoke(null));
    }
}
```

The `Class.forName(String, boolean, ClassLoader)` calls mean:

- With `loader = null`, ask the bootstrap loader to find and initialize `demo.boot.BootProbe`.
- With `ClassLoader.getSystemClassLoader()`, ask the system loader to find `demo.app.AppProbe` on the application classpath.
- The code uses **reflection** to defer requesting the two classes until an explicit point in `main`, avoiding direct references in application bytecode that the JVM might resolve early.

### 7.6. File `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: demo.agent.LoaderAgent

```

The manifest requires `Premain-Class` because the command line uses `-javaagent`. The exercise does not use `Can-Retransform-Classes` because `retransformClasses` is not called. End the manifest with a **blank line**.

### 7.7. Compile, Package Three JARs, and Run

Open a terminal in the **`demo/` directory** above. Use a JDK 17+ supporting target 17:

```bash
javac --release 17 -d classes src/demo/agent/LoaderAgent.java src/demo/boot/BootProbe.java src/demo/app/AppProbe.java src/demo/app/DemoApp.java

jar --create --file bootstrap-probe.jar -C classes demo/boot
jar --create --file loader-agent.jar --manifest agent.mf -C classes demo/agent
jar --create --file app.jar -C classes demo/app

java -javaagent:loader-agent.jar -cp app.jar demo.app.DemoApp
```

Packaging explanation:

- `bootstrap-probe.jar` contains only the classes in `demo.boot`.
- `loader-agent.jar` contains `LoaderAgent.class` and **`LoaderAgent$1.class`** generated by the anonymous transformer; package the entire `demo/agent` directory so no auxiliary classes are missed.
- `app.jar` contains `DemoApp.class` and `AppProbe.class`, but **does not** contain `BootProbe.class`.
- The JVM runs the agent with `-javaagent`; when `DemoApp` calls `Class.forName`, the bootstrap loader finds `BootProbe` in the appended JAR.

**Expected stdout** on HotSpot/JDK 17+ with bootstrap search support:

```text
[transform] demo/boot/BootProbe: bootstrap
[main] bootLoaderNull=true
[main] bootValue=from bootstrap
[transform] demo/app/AppProbe: non-bootstrap
[main] appLoaderNull=false
[main] appValue=from application
```

Some JDKs may print additional warnings about Class Data Sharing or bootstrap classpath configuration on **stderr**; these warnings are not part of the illustrative stdout. If the application has other agents/JVMs involved, match the exact lines produced by the example.

Result explanation:

1. `BootProbe` is defined from `bootstrap-probe.jar` by the bootstrap loader, so the callback receives **`loader == null`**.
2. Reflection via `boot.getClassLoader()` also returns `null`, confirming the loader of the **actual class**.
3. `AppProbe` is defined by the system loader from `app.jar`, so the callback receives **`loader != null`**.
4. No bytecode was modified: the transformer returns `null`; the goal is to observe loader identity.
5. Both classes are code we wrote ourselves, yet one has the bootstrap loader and the other has the application loader. **Who wrote the source code does not determine `loader`**; the class definition mechanism is what determines it.

### 7.8. Inspecting Artifacts If the Result Differs

```bash
jar --list --file bootstrap-probe.jar
jar --list --file loader-agent.jar
jar --list --file app.jar
```

Inspect the class paths inside each JAR and the actual manifest. If `LoaderAgent$1.class` is missing, the agent will fail to instantiate the transformer because the anonymous class is absent. If `BootProbe.class` is placed in the wrong archive, `Class.forName("demo.boot.BootProbe", true, null)` may throw `ClassNotFoundException`. If you run the command from another directory, the relative path `bootstrap-probe.jar` in `new JarFile(...)` may not exist; in that case, specify a verified absolute path or run from `demo/`.

**This is an intentional demo.** In production, do not arbitrarily add the entire application to the bootstrap search path just to log loaders.

## 8. The Transformer Contract and the Retransform Case

For a **normal class load**, `classBeingRedefined == null`. For **redefine/retransform**, this parameter may hold the `Class<?>` of the class being processed. Even so, the meaning of `loader == null` **does not change**: it is always the defining loader of the class being transformed.

Example when branching on both loader type and phase is needed:

```java
boolean bootstrap = loader == null;
boolean revisiting = classBeingRedefined != null;

if (bootstrap && revisiting) {
    // A bootstrap class is passing through the redefine/retransform path.
}
```

The snippet above only illustrates the check; it is not standalone runnable code. To receive callbacks on retransform, the transformer must be registered with `canRetransform = true` **and** the JVM/agent must have the appropriate capability. Detecting bootstrap does not automatically grant permission to modify core classes.

If a class was already loaded before the agent became active, using `Instrumentation.getAllLoadedClasses()` and `Class.getClassLoader()` can help observe identity; modifying bytecode of already-loaded classes requires checking `isRetransformClassesSupported()`, `isModifiableClass()`, and specific JVM limitations. Do not call retransform indiscriminately just to inspect loaders.

## 9. Correctness and Safety When Handling Bootstrap Classes

### 9.1. Avoid Reverse References from Bootstrap Classes into the Application

Classes defined by the bootstrap loader **do not automatically see** classes that exist only in application/custom loaders. If a transformer injects into bootstrap bytecode a call to `com.myapp.AgentHelper` on the application classpath, the JVM may fail to resolve the dependency and throw `NoClassDefFoundError`/`LinkageError`.

Helpers needed by bootstrap classes must be placed where the bootstrap loader can find them, and must still properly handle access/module permissions on Java 9+. Adding helpers to the bootstrap search path should be limited to classes that genuinely serve instrumentation and use a dedicated package name to avoid collisions.

### 9.2. `appendToBootstrapClassLoaderSearch` Has Its Own Scope and Risks

`Instrumentation.appendToBootstrapClassLoaderSearch(JarFile)` only adds a **JAR file** to the bootstrap search path; it does not cause all classes in the JAR to be loaded automatically, nor does it act as a general mechanism to change the loader of already-defined classes.

Oracle notes to avoid putting classes that do not belong to instrumentation into an appended JAR, because delegation may pick the wrong class with the same name/package, causing `IllegalAccessError` or hard-to-diagnose errors. If the JVM has already failed to resolve a symbolic reference, appending the JAR afterward **does not guarantee** that a subsequent resolution attempt will succeed: the JVMS has rules for caching resolution failures of that reference.

### 9.3. Be Careful with Modules, Access Permissions, and Load Order

Since Java 9, class loading and module access are two distinct aspects. `loader == null` identifies the bootstrap loader, but does not determine whether the code belongs to a **named module** or an **unnamed module**, nor does it automatically grant read, export, or open package permissions. The transformer has an overload that accepts `Module` to provide additional module context.

Inside the callback, avoid:

- Calling many complex APIs or reflection that loads additional classes;
- Logging unboundedly for all of `java/`;
- Initializing new classes from the very package currently being processed by the transformer;
- Holding strong references to arbitrary `ClassLoader` instances and preventing class loaders from being garbage-collected;
- Assuming the callback always runs on a fixed thread or always has the same TCCL as the application.

Transformers can be invoked while the JVM is in the middle of defining a class. Any new class loading, I/O, or complex synchronization inside the callback can affect startup, performance, and thread safety. When observing a small number of classes as in the demo, short logs make verification easier.

## 10. Common Reasoning Errors

| Statement or Symptom | Correct Conclusion |
| --- | --- |
| "`loader == null` is an error because the JVM couldn't find the class loader" | False: for `transform`, that is the **bootstrap defining loader** |
| "`loader == null` means the class has not been loaded yet" | False: newly loaded vs. redefined status relates to `classBeingRedefined` and the callback path, not the loader alone |
| "If the name starts with `java/`, it is definitely bootstrap" | Cannot be inferred from the name; must inspect the actual loader |
| "`String.class.getClassLoader() == null`, so a newly registered transformer must have received `java/lang/String`" | False: `String` is typically loaded before the transformer is registered |
| "`int.class.getClassLoader() == null`, so the transformer processed the `int` class" | False: primitives are not regular Java class files that get transformed |
| "The system loader found `String`, so the system loader defined `String`" | False: it may have delegated to bootstrap; the callback reports the defining loader |
| "`ClassLoader.getPlatformClassLoader()` is bootstrap" | False: platform is a distinct loader object from bootstrap |
| "The TCCL is the system loader, so `loader` in the callback is always system" | False: TCCL and defining loader are two different pieces of information |
| `NullPointerException` when calling `loader.loadClass(...)` in transform | Must guard against `loader == null`; do not load classes arbitrarily inside the callback |
| Bootstrap class loads, but bytecode hook calling a helper cannot see it | Check class loader visibility, module access, and the helper's dependencies |

## 11. Checklist When Using `loader == null` in a Real Agent

1. Use the **`loader` parameter of `transform`** directly to identify bootstrap; check `loader == null` **before** calling methods on the loader.
2. Distinguish the defining loader from TCCL, initiating loader, parent loader, and module.
3. Compare `className` using **internal form with `/`**; write null-safe filters and limit logging.
4. Understand which classes were already loaded **before** registering the transformer; do not treat the absence of a callback as proof that a class does not belong to bootstrap.
5. When core classes must be processed, check retransform/modifiability capabilities and design helpers that can be linked by bootstrap.
6. If using `appendToBootstrapClassLoaderSearch`, keep the instrumentation JAR small with a dedicated package; check for class/resource collisions and module access permissions.
7. Verify on the **actual JVM and artifacts**, because classes loaded by frameworks/plugins may differ from development machine setups.

## 12. Official References

- [Java SE 17 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): defines `loader` as the defining loader; two `transform` overloads; requirement not to modify input bytes and to return `null` when unchanged.
- [Java SE 17 — `Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `addTransformer`, `appendToBootstrapClassLoaderSearch`, `retransformClasses`, and JVM capabilities.
- [Java SE 17 — `ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): delegation model, bootstrap/platform/system loaders, and handling of array classes.
- [Java SE 17 — `Class.getClassLoader()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getClassLoader()): primitives/void return `null`; loader is associated with each `Class<?>`.
- [Java SE 17 — `Class.forName`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#forName(java.lang.String,boolean,java.lang.ClassLoader)): `null` loader argument represents the bootstrap loader when looking up a class.

**Key takeaway:** In `ClassFileTransformer.transform`, **`loader == null` indicates the bootstrap defining loader**. Use this value directly to classify callbacks, while distinguishing it from package names, TCCL, classes loaded before the agent, and primitives/arrays without ordinary class files.
