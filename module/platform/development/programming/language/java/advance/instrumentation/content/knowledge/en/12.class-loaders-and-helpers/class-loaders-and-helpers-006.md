# Helpers in Bootstrap Only Link to Classes Bootstrap Can Load

In Java Instrumentation, an agent sometimes needs a **helper class** so that bytecode of system classes or classes defined by different class loaders can call a unified support method. One option is to place the helper into the **bootstrap class loader search** using `Instrumentation.appendToBootstrapClassLoaderSearch(...)` or the `Boot-Class-Path` manifest attribute.

However, once a helper is defined by the **bootstrap loader**, type/class references in the helper's bytecode must be resolved according to the **bootstrap loader's class-loading capability**, not based on the application's classpath. The `java.lang.instrument` package specification states directly: **supporting classes arranged by an agent to be defined by the bootstrap loader must only link to classes defined by the bootstrap loader**; nor is there **any guarantee that all platform classes are defined by the bootstrap loader**.

**Core rule:**

> **A helper loaded by the bootstrap loader must not depend directly on classes that exist only in the application/system/custom class loader.** Bootstrap sits at the top of the normal delegation mechanism; it does not ask child loaders whether they can resolve a dependency class.

This lesson explains the JVM principle, the practical meaning of *linking*, how to place a helper into bootstrap, a **runnable** Java 17+ example with `NoClassDefFoundError`, safe communication patterns, distinguishing loader visibility from Java module readability, and a checklist to avoid mistakes when writing an agent.

## 1. Why does instrumentation need a bootstrap helper?

A `ClassFileTransformer` can modify a class's bytes before the JVM defines it. For example, to measure every time `java.util.SomeClass` executes a method, the transformer can insert the call:

~~~text
invokestatic lab/boot/BootHelper.record(Ljava/lang/String;)V
~~~

This is a **symbolic bytecode description**, not a directly runnable Java statement. The JVM will have to locate and link `lab.boot.BootHelper` when the instrumented code is used.

If the helper only exists in the **agent JAR loaded by the system class loader**, a class defined by **bootstrap** may not be able to resolve that reference. The fact that the agent itself can call the helper does not mean code in `java.base` can call it too, because the **loader initiating the symbolic reference resolution** may be different.

Placing a small helper into bootstrap allows classes defined by bootstrap to find that helper through bootstrap's own class-loading mechanism. However, the bootstrap helper itself must be very careful about **the dependencies it uses**.

Typical diagram (simplified; the JDK also has the platform loader):

~~~text
                  Bootstrap class loader
                   (Class.getClassLoader() = null)
                      ├─ java.lang.String
                      ├─ java.util.function.Supplier
                      └─ lab.boot.BootHelper  ← added by agent
                                │
                                │ static reference to AppDependency?
                                ▼
                    does NOT search downward automatically
                                ✕
                  Platform class loader
                                ▲
                                │ normal delegation
                                │
                   System/Application class loader
                      ├─ lab.agent.BootAgent
                      ├─ lab.app.Main
                      └─ lab.app.AppDependency

             There may also be custom/plugin loaders below.
~~~

The delegation path normally goes **from child loader up to parent** when searching for a class. An upper-level loader **does not automatically search downward** into the classpath or classes defined in child loaders. Some custom loaders may use different strategies, but that **does not change the limits of a helper already defined by bootstrap**.

## 2. What does “only link to classes bootstrap can load” mean?

In a class file, a method may contain **symbolic references** to class names, methods, fields, and related types. The JVM needs to *resolve* these references before or when executing operations that require them.

For example, a helper defined by bootstrap:

~~~java
package lab.boot;

public final class BootHelper {
    public static String unsafe() {
        return lab.app.AppDependency.value();
    }
}
~~~

The class `lab.app.AppDependency` may be compiled and fully present in `app.jar`, and even **already loaded by the application class loader**. That still **does not give the bootstrap loader the ability to define/find `AppDependency` through direct linking from the helper**.

When the JVM needs to resolve the reference from `BootHelper` to `lab.app.AppDependency`, the typical error is:

~~~text
java.lang.NoClassDefFoundError: lab/app/AppDependency
~~~

When the error occurs can depend on the JVM and the timing of resolution: in the simple example below, it appears when calling `unsafe()`; in more complex code, verification, initialization, parameter types, superclass/interface, or deep reflective access can also surface the error earlier.

**Distinctions to make:**

| Question | Answer |
|---|---|
| Does `AppDependency.class` exist in the app JAR? | Possibly yes |
| Can the application class loader load `AppDependency`? | Possibly yes |
| Can the bootstrap loader load `AppDependency`? | **No**, if the class only exists on the application classpath and is not in the bootstrap search |
| Can a bootstrap helper link directly to `AppDependency` just because the app already loaded it? | **No** |
| Can a bootstrap helper call application code via a callback through an interface bootstrap already knows? | **Yes**, if designed with the right types and loaders as shown in the lab |

For the loader represented by the JVM via `Class.getClassLoader()`:

~~~java
System.out.println(String.class.getClassLoader()); // null
System.out.println(BootHelper.class.getClassLoader()); // null if loaded by bootstrap
~~~

This is a fragment inside the known `BootHelper` method. **`null` represents the bootstrap loader** in the `Class.getClassLoader()` API, not “a class with no loader” or “the JVM skips visibility checks”.

## 3. Bootstrap does not mean “sees every JDK class”

Modern JDKs typically have **bootstrap, platform, and system/application class loaders**. You should not conclude that “anything starting with `java.` or `javax.` is defined by bootstrap”.

- Many core classes of **`java.base`** such as `String`, `Object`, `Runnable`, and `Supplier` can be used as stable communication types for a bootstrap helper.
- Some **platform classes/modules** are defined by the **platform class loader** or in other module layers; the Instrumentation specification does not guarantee that bootstrap defines all platform classes.
- An **agent** class is usually defined by the **system loader**, unless the agent arranges an auxiliary JAR to be loaded by bootstrap.
- An **application** class is usually in the system loader or a **custom loader** (for example, plugin/container/framework).

**The question to ask is which loader defines which class**, not whether a class belongs to the JDK or is part of the same `.jar` file you are looking at.

Example of checking the loader in an application:

~~~java
static void showLoader(Class<?> type) {
    System.out.println(type.getName()
            + " -> " + type.getClassLoader());
}
~~~

This is an illustrative method to place inside a class, not a standalone runnable program. `getClassLoader() == null` indicates bootstrap; for platform/application/custom loaders, the result is the corresponding loader object. When logging in practice, include **class name, defining class loader, and module** if investigating Java 9+.

## 4. What does `appendToBootstrapClassLoaderSearch` do, and what does it not do?

Official API:

~~~java
void appendToBootstrapClassLoaderSearch(java.util.jar.JarFile jarfile);
~~~

In the `premain`/`agentmain` callback of a Java agent:

~~~java
java.util.jar.JarFile helperJar =
        new java.util.jar.JarFile("boot-helper.jar");
instrumentation.appendToBootstrapClassLoaderSearch(helperJar);
~~~

This snippet is a **fragment**: the `instrumentation` variable must be the `Instrumentation` instance provided by the JVM, and the path must point to an actual JAR.

`appendToBootstrapClassLoaderSearch` specifies a **JAR for bootstrap to search additionally when its built-in class lookup fails**. It can be called multiple times, and JARs are added to the search list in call order. It is not an API that “moves all loaded classes to bootstrap”.

**Do not infer the wrong things from the API name:**

1. It does not make bootstrap automatically see **every class on the application classpath**.
2. It does not automatically copy classes that the helper depends on from the agent JAR into bootstrap.
3. It does not convert a **`Class<?>` object already defined by the system loader** into a bootstrap class.
4. It does not retroactively undo **failed symbolic reference resolutions**: the JVM may cache failed reference resolution results; merely adding the JAR afterward may not fix an already-failed link.
5. It does not guarantee every class in the JAR will load successfully: the class itself must still obey linkage, accessibility, and class-file version rules.
6. It does not turn `-javaagent` into `-Xbootclasspath`; this is the JDK-defined Instrumentation mechanism.

**Append the helper JAR as early as possible** in `premain`, before transforming/loading classes that will call the helper. Be careful about referencing the helper from agent code before the JAR is appended, as that could cause the helper to be defined prematurely by an unintended loader.

The specification also warns that **a bootstrap helper JAR should only contain classes/resources truly intended for bootstrap instrumentation**. Do not put the entire agent, application, or unrelated libraries into it.

## 5. Java 17+ lab: demonstrating the direct error and the safe call

This lab uses **three separate JARs**:

1. `boot-helper.jar`: contains only `lab.boot.BootHelper`, loaded by the bootstrap loader.
2. `app.jar`: contains `lab.app.Main` and `lab.app.AppDependency`, loaded by the application loader.
3. `agent.jar`: contains `lab.agent.BootAgent`; `premain` adds `boot-helper.jar` to the bootstrap search.

The files are **compiled together** so the Java compiler checks syntax and references. Afterward, they are **packaged separately** to accurately simulate class loader boundaries at runtime. If you skip the separate packaging step and leave all classes on the same application classpath, the experiment no longer tests the bootstrap mechanism properly.

Directory tree:

~~~text
bootstrap-helper-lab/
├── src/
│   └── lab/
│       ├── boot/
│       │   └── BootHelper.java
│       ├── app/
│       │   ├── AppDependency.java
│       │   └── Main.java
│       └── agent/
│           └── BootAgent.java
├── MANIFEST.MF
└── out/                   will be created by javac
~~~

### 5.1. `src/lab/boot/BootHelper.java`

~~~java
package lab.boot;

import java.util.function.Supplier;

public final class BootHelper {
    private BootHelper() { }

    public static String safe() {
        return "boot-ok";
    }

    public static String unsafe() {
        return lab.app.AppDependency.value();
    }

    public static String viaCallback(Supplier<String> callback) {
        return callback.get();
    }
}
~~~

**Analysis of all three methods:**

- `safe()` only uses `String` from `java.base` and a literal; there are no references to application classes.
- `unsafe()` has a **static** call `AppDependency.value()`. In the class file there will be a symbolic reference to `lab/app/AppDependency`, which only exists in the **app JAR**. When `BootHelper` is defined by bootstrap, it cannot resolve this reference on its own, even though the application can.
- `viaCallback(Supplier<String>)` has a descriptor using **the `Supplier` interface and `String`, both known to bootstrap**. The method does not directly mention the application class name; it only calls `Supplier.get()`. The application itself is responsible for creating the implementation/lambda for this interface.

`unsafe()` should not be treated as a production design. It is kept in this lesson solely as an **intentional failure experiment**.

### 5.2. `src/lab/app/AppDependency.java`

~~~java
package lab.app;

public final class AppDependency {
    private AppDependency() { }

    public static String value() {
        return "app-ok";
    }
}
~~~

This class is packaged only in `app.jar`, **not in `boot-helper.jar`**. That is a necessary condition for the visibility experiment.

### 5.3. `src/lab/app/Main.java`

~~~java
package lab.app;

import lab.boot.BootHelper;

public final class Main {
    public static void main(String[] args) {
        System.out.println("helperBootstrap="
                + (BootHelper.class.getClassLoader() == null));
        System.out.println("safe=" + BootHelper.safe());
        System.out.println("viaCallback="
                + BootHelper.viaCallback(AppDependency::value));

        try {
            System.out.println("unsafe=" + BootHelper.unsafe());
        } catch (NoClassDefFoundError e) {
            System.out.println("unsafeError="
                    + e.getClass().getSimpleName());
        }
    }
}
~~~

**Why does the callback work?** `AppDependency::value` is created in the application's class as a `Supplier<String>`; the bootstrap helper only performs an **interface invocation on `Supplier.get()`**, without directly resolving the name `lab.app.AppDependency` in the helper's constant pool. The JVM can perform dynamic dispatch to the implementation created by the application. That is **communicating through a common bootstrap-visible type**, unlike the helper itself containing a direct symbolic reference to an app class.

This is an example illustrating the mechanism, **not a recommendation to pass arbitrary application objects into the helper**. In a real agent, you must control references, object lifetimes, and class loader leak risks.

`catch (NoClassDefFoundError)` is only there so the demo continues printing results. You should not swallow a similar `LinkageError` in production without diagnostics and a recovery strategy.

### 5.4. `src/lab/agent/BootAgent.java`

~~~java
package lab.agent;

import java.lang.instrument.Instrumentation;
import java.util.jar.JarFile;

public final class BootAgent {
    public static void premain(String jarPath, Instrumentation inst)
            throws Exception {
        if (jarPath == null || jarPath.isBlank()) {
            throw new IllegalArgumentException(
                    "bootstrap helper JAR required");
        }

        inst.appendToBootstrapClassLoaderSearch(
                new JarFile(jarPath));

        Class<?> helper =
                Class.forName("lab.boot.BootHelper", false, null);
        System.out.println("agentSawBootstrap="
                + (helper.getClassLoader() == null));
    }
}
~~~

In the example:

1. The JVM loads the **agent JAR** via `-javaagent`.
2. `premain` receives the path to the **bootstrap helper JAR** in the agent option.
3. `new JarFile(jarPath)` represents the JAR containing only helpers intended for bootstrap.
4. `inst.appendToBootstrapClassLoaderSearch(...)` adds the JAR to the bootstrap search.
5. `Class.forName(name, false, null)` asks to look up the class with the **bootstrap loader** (`null` is bootstrap), while `false` avoids running static initializers at this step.
6. `helper.getClassLoader() == null` confirms the class was actually defined by bootstrap.

At this point, `BootAgent` does **not** call `BootHelper.unsafe()`, because the goal is to verify the loader first and then let `Main` demonstrate the error when resolving the reference to `AppDependency`.

### 5.5. `MANIFEST.MF`

~~~text
Manifest-Version: 1.0
Premain-Class: lab.agent.BootAgent

~~~

The manifest must have a **trailing blank line**. `Premain-Class` points to the agent entrypoint; `BootHelper` is **not** `Premain-Class`. The example uses `appendToBootstrapClassLoaderSearch` directly, so `Boot-Class-Path` in the manifest is not required.

### 5.6. Compile and create the exact three JARs

Open a terminal in `bootstrap-helper-lab`. Create the compilation output directory.

Bash/Git Bash:

~~~bash
mkdir -p out
~~~

PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
~~~

Compile all files with **JDK 17 or newer**:

~~~bash
javac --release 17 -d out src/lab/boot/BootHelper.java src/lab/app/AppDependency.java src/lab/app/Main.java src/lab/agent/BootAgent.java
~~~

`--release 17` targets Java 17 bytecode; the example uses APIs available in that version. **This is only a shared compilation step**. The crucial part of the lab is **splitting the classes into three different JARs** in the next step:

~~~bash
jar --create --file boot-helper.jar -C out lab/boot/BootHelper.class
jar --create --file app.jar -C out lab/app/Main.class -C out lab/app/AppDependency.class
jar --create --file agent.jar --manifest MANIFEST.MF -C out lab/agent/BootAgent.class
~~~

Inspect the contents if needed:

~~~bash
jar --list --file boot-helper.jar
jar --list --file app.jar
jar --list --file agent.jar
~~~

`boot-helper.jar` must contain only `lab/boot/BootHelper.class` (apart from auto-generated JAR metadata). **Do not add** `AppDependency.class` or `Main.class` to the bootstrap JAR, as doing so would mask the mistake we want to observe and change class identity.

Run command:

~~~bash
java -javaagent:agent.jar=boot-helper.jar -cp app.jar lab.app.Main
~~~

At runtime, the main classpath **only has `app.jar`**; `agent.jar` is handled by the JVM as an agent, and `boot-helper.jar` is added via the API. Therefore `BootHelper` cannot accidentally be loaded by the application class loader from the main classpath.

**Verified stdout when compiled with `--release 17` and run on JDK 24:**

~~~text
agentSawBootstrap=true
helperBootstrap=true
safe=boot-ok
viaCallback=app-ok
unsafeError=NoClassDefFoundError
~~~

Some JVMs (including OpenJDK/HotSpot) may print an additional warning about **Class Data Sharing** when the bootstrap search path is extended, such as `Sharing is only supported for boot loader classes because bootstrap classpath has been appended`. This is normally **JVM stderr**, not a stdout line from the program, and does not change the demonstrated result. If another JVM behaves differently or does not support the mechanism as expected, check the specific configuration/distribution.

### 5.7. Line-by-line result interpretation

| Line | Evidence |
|---|---|
| `agentSawBootstrap=true` | The agent looked up `BootHelper` using `Class.forName(..., null)` and the class was indeed defined by bootstrap |
| `helperBootstrap=true` | The application also sees **the exact same bootstrap helper class** through delegation |
| `safe=boot-ok` | The helper runs when it only uses classes and types bootstrap can link |
| `viaCallback=app-ok` | Passing an implementation of a bootstrap-visible interface allows calling application code via dynamic dispatch |
| `unsafeError=NoClassDefFoundError` | A bootstrap helper **cannot link directly** to a class that only resides in the application loader |

This scenario proves that **the application knowing `AppDependency` does not extend class search for the bootstrap helper**.

## 6. Why can the app call the bootstrap helper, but the helper cannot call the app directly?

**Call direction does not equal class-lookup direction.**

When `Main` (application loader) references `BootHelper`, the loader/application runtime normally delegates to bootstrap to look up `BootHelper` first. Because the helper is already in the bootstrap search, the JVM can resolve that name.

Conversely, when code inside `BootHelper` contains a symbolic reference to `AppDependency`, the JVM resolves the reference in the context of a class **defined by the bootstrap loader**. Bootstrap does not by default ask downward to the system loader to find application classes.

~~~text
App Main (system loader)
    │  static reference to BootHelper
    └─────────────────────────────► bootstrap finds BootHelper      ✓

BootHelper (bootstrap loader)
    │  static reference to AppDependency
    └─────────────────────────────► bootstrap cannot see app class  ✗
                                      NoClassDefFoundError
~~~

This also explains why the error can occur even when:

- `java -cp app.jar ...` runs fine;
- `ClassLoader.getSystemClassLoader().loadClass("lab.app.AppDependency")` works;
- `AppDependency` has even been used by the system earlier;
- the Java agent (system loader) can call `AppDependency` from the agent's own code.

Those observations **do not change which loader resolves static references of the bootstrap helper**.

## 7. Safer bootstrap helper designs

### Approach A — Tiny helper, depending only on bootstrap-visible types

If the functionality is simple, such as counting events or producing primitive data, keep the helper self-contained:

~~~java
package lab.boot;

import java.util.concurrent.atomic.LongAdder;

public final class CounterHelper {
    private static final LongAdder CALLS = new LongAdder();

    private CounterHelper() { }

    public static void hit() {
        CALLS.increment();
    }

    public static long count() {
        return CALLS.sum();
    }
}
~~~

`LongAdder`, `String`, `Throwable`, `Runnable`, and `Supplier` are useful `java.base` types for bootstrap helper examples. This is a complete Java class, but it only runs when **compiled, packaged into a JAR, and loaded properly**; `hit()` is not called automatically unless some code invokes it.

Strength: no static references to agent or app classes; minimal risk of class-loader linkage issues. Keep in mind: a static field of a helper held in bootstrap can live for the entire JVM lifetime, so avoid storing application objects, `Class<?>`, loaders, or callbacks **forever** if hot-reload/plugin unloading exists.

### Approach B — Communicating via an interface known to bootstrap

In the experiment, `Supplier<String>` from `java.base` serves as the shared contract:

~~~java
public static String viaCallback(Supplier<String> callback) {
    return callback.get();
}
~~~

This is a **fragment inside `BootHelper`**, not a standalone runnable program. The helper only needs to resolve the `Supplier` interface. The app's lambda instance is **a runtime object**, and the JVM dispatches the call to the corresponding implementation without the helper needing to statically reference the class that created the lambda.

For more complex projects, you can define a **small dedicated interface placed in the bootstrap helper JAR**, while its implementation lives in the system/custom loader:

~~~java
package lab.boot;

public interface EventSink {
    void accept(String name, long elapsedNanos);
}
~~~

The interface above is a standalone Java file (`EventSink.java`) and must be **packaged into the bootstrap JAR** alongside the helper; each loader must not define its own duplicate copy with the same name. The application can provide the implementation, while the helper only calls through the interface defined by bootstrap.

**Important caveats:**

- Avoid bootstrap API signatures containing types that only exist in the app loader, including return types, field types, or generic code that triggers casts/reflective access.
- Only pass types/helper interfaces that bootstrap already knows; dynamic objects may be defined by the app loader, but the bootstrap helper must not be forced to statically link to the implementation class.
- Consider bounding callback lifetimes: a strong `static EventSink` in bootstrap can keep an entire application class loader alive and cause a **class loader leak** on redeploy.
- When multiple class loaders have implementations with the same name, check **class identity**, not just `getName()`.

### Approach C — Keeping application-dependent logic on the application side

There is no need to put the **entire agent** into bootstrap. A clean design:

~~~text
Bootstrap helper (minimal code, minimal dependencies)
    │
    ├── bootstrap-visible API for recording/signaling
    │
    ▼
System/app-side component (application dependencies live here)
    │
    ├── metrics SDK
    ├── logging/backend client
    └── application-specific classes
~~~

The helper only provides a small call site and forwards signals/data through a shared contract. Keep logging frameworks, HTTP clients, serializers, or framework-dependent code on the application/agent side when they are **not bootstrap-visible**. The connection mechanism can be a callback/interface, queue, or message abstraction, while avoiding deadlocks and recursive class loading.

Do not turn a bootstrap helper into an arbitrary *service locator* for all application classes.

## 8. Can you load an app class using an explicit loader?

**You can look up a class reflectively through an explicitly provided loader**, but that **does not change the static linking rules** of the helper.

Illustrative fragment:

~~~java
ClassLoader appLoader = ClassLoader.getSystemClassLoader();
Class<?> type = Class.forName(
        "lab.app.AppDependency", false, appLoader);
~~~

This snippet uses an **explicit loader** to look up a class name via the reflection API. It does not mean that an `invokestatic lab/app/AppDependency.value` instruction **already compiled into the helper's bytecode** will automatically change its loader resolution.

There is also no guarantee that the **system loader** contains every application class: application servers, plugins, OSGi, or isolated environments may use custom loaders. `Thread.currentThread().getContextClassLoader()` can sometimes help locate classes in the application's context, but the thread context loader is not guaranteed to point to the loader containing the needed dependency either.

When using reflection or `MethodHandle`, consider:

1. Providing the **right `ClassLoader`** and verifying the class's origin.
2. Java access rules: public, package-private, module exports/opens.
3. Method signature constraints and type/loader identity.
4. Failures when classes are unloaded/redeployed and long-lived references that may cause leaks.
5. Reflection overhead, exception handling, and API stability.

For a helper that needs to be called from `java.base` bytecode, communicating via a bootstrap-visible interface is usually easier to control than having the helper look up app classes by name.

## 9. How do `Boot-Class-Path` and `appendToSystemClassLoaderSearch` differ?

There are several mechanisms for an agent to place helpers, but they are **not equivalent in terms of loader**:

| Mechanism | Added to which loader's search? | Common use case |
|---|---|---|
| `Instrumentation.appendToBootstrapClassLoaderSearch(JarFile)` | **Bootstrap** | Helper needs to be called by bootstrap-loaded classes |
| Agent manifest `Boot-Class-Path` | **Bootstrap** | Agent declares helper paths directly in its manifest |
| `Instrumentation.appendToSystemClassLoaderSearch(JarFile)` | **System** | Helper used at the system/application loader and compatible child loaders |
| Application classpath `-cp` | **System** (in standard JVM configurations) | Application classes, libraries |
| A custom `ClassLoader#defineClass` | **That custom loader** | Plugins or module isolations |

**Example manifest using `Boot-Class-Path`:**

~~~text
Manifest-Version: 1.0
Premain-Class: lab.agent.BootAgent
Boot-Class-Path: boot-helper.jar

~~~

This is an **alternative configuration example**, not the manifest used in the runnable lab in Section 5. Relative paths in `Boot-Class-Path` are resolved according to agent manifest rules relative to the agent JAR's path; ensure the helper JAR exists and is in the right location.

`appendToSystemClassLoaderSearch` does not make the system loader see **all** classes loaded by custom child loaders. Similarly, you cannot use the system search to automatically resolve a symbolic reference inside a bootstrap class. **Choosing the right class loader for the helper** is an important design decision.

## 10. Java 9+ module readability does not replace class-loader visibility

Since Java 9, every class also belongs to a **module**. Classes placed in a bootstrap helper JAR via the bootstrap search typically reside in the **unnamed module of the bootstrap loader**.

The `java.lang.instrument` specification provides an important facility: so that classes transformed by a transformer can call supporting classes, the JVM **arranges for the transformed class's module to read the unnamed module of the bootstrap loader and the unnamed module of the loader that loaded the agent class**. This helps satisfy part of the **module readability** requirement when inserting helper references into transformed code.

However, **readability and class-loader visibility are two different checks**:

~~~text
Problem A: transformed class → bootstrap helper
  - Finding class: loader resolution
  - Reading module: JPMS readability
  - Access: public/package/exports and related JVM rules

Problem B: bootstrap helper → class present only in application loader
  - Bootstrap still does not search downward into the application loader.
  - Adding a read edge does NOT turn AppDependency into a bootstrap class.
~~~

Do not mechanically use `--add-reads` or `Instrumentation.redefineModule` as a “class not found fix”. They address **module read relationships**, not moving classes across loaders or changing delegation direction. If it truly is a module access error, identify which module reads which module, which package is exported/opened, and what the actual caller object is.

Conversely, if the error is `NoClassDefFoundError` because the class only exists in the app loader, adding a read edge **will not make bootstrap find that class**.

## 11. `NoClassDefFoundError`, `ClassNotFoundException`, and access errors

When designing a bootstrap helper, read the **error type** accurately:

| Error/Symptom | Common meaning | Diagnostic direction |
|---|---|---|
| `NoClassDefFoundError: lab/app/AppDependency` | Resolution of a class referenced from bytecode failed to find a suitable definition | Check the **helper's defining loader**, bootstrap search, classpath, and how the helper references it |
| `ClassNotFoundException` | Name-based loading APIs like `Class.forName`/`loadClass` did not find the class in the requested loader | Check the binary name and the loader passed to the API |
| `IllegalAccessError` | The class was found, but linking/access is not permitted | Check access flags, runtime package, module access, class identity |
| `NoSuchMethodError` / `NoSuchFieldError` | The class was found, but the member descriptor mismatches or is missing | Check which version of the helper was loaded, duplicate classes in JARs, linkage |
| `ClassCastException` | Two objects/types are incompatible; possibly same name but different loaders | Log `Class<?>`, loader, and module of both types |
| `UnsupportedClassVersionError` | Helper bytes were compiled for a higher version than the JVM supports | Use `javac --release` matching the runtime |
| `ExceptionInInitializerError` | Error while running a class's static initializer | Check the cause; may originate from a dependency/load |
| Helper loaded by system loader even though bootstrap was intended | JAR is on the app path or was loaded before appending | Check `getClassLoader()`, startup order, and packaging |

Dangerous pitfall: **the same package name does not guarantee the same runtime package**. A package is evaluated together with the **defining class loader**; class `p.C` defined by bootstrap and class `p.D` defined by the application loader do not automatically have package-private access to each other. The `appendToBootstrapClassLoaderSearch` specification even notes the case where an accessor class like `C$1` is inadvertently picked up by bootstrap from an appended JAR, leading to `IllegalAccessError`.

Do not treat every error as “just add the JAR to the classpath”. You need to know **who is trying to resolve which class**, and **the loader of the class containing the symbolic reference**.

## 12. Why use a dedicated package for the bootstrap helper?

When appending a JAR to the bootstrap search, that JAR can be found by **many child loaders** via delegation. If you use a package or class name that collides with an application class, the duplicate name may be loaded by bootstrap first:

~~~text
Not recommended:
  agent-helper.jar contains com/example/internal/Util.class
  app.jar          also has com/example/internal/Util.class

More intentional:
  agent-helper.jar contains io/example/instrumentation/boot/RecorderBridge.class
  app.jar          contains com/example/service/Util.class
~~~

The two paths above are **design examples**, not paths to real resources. A dedicated package name reduces the risks of:

- Bootstrap mistakenly defining a class that belongs to the application.
- A non-public accessor class being loaded under a different loader, causing package-private errors.
- Dependency/version collisions causing `NoSuchMethodError`.
- Unexpected class identity causing `ClassCastException`.
- Different custom loaders loading multiple copies of the same name, preventing static state from being shared as intended.

Do not place the agent's entire dependency tree into bootstrap just to “let the helper see everything”. That approach easily affects the entire JVM and is very hard to debug when multiple agents are present.

## 13. Early class-loading constraints and runtime verification

### Append as early as possible

In `premain`:

~~~text
JVM start
   ↓
load agent class
   ↓
premain → append bootstrap helper JAR
   ↓
register transformer / prepare instrumentation
   ↓
target class is transformed, defined, and calls helper
~~~

Reason: if a symbolic reference has already been attempted and **failed** to resolve by the JVM, appending the JAR afterward does not necessarily cause resolution to be retried. If the helper class was already defined by the application loader earlier, adding the same name to the bootstrap search **does not turn the existing class object into a bootstrap class**. Parallel class loading environments also make races hard to reproduce.

### Verify the loader in code, not just JAR placement

Illustrative checks:

~~~java
Class<?> helper =
        Class.forName("lab.boot.BootHelper", false, null);

System.out.println(helper.getClassLoader() == null);
System.out.println(helper.getModule());
~~~

`Class.forName(..., false, null)` asks bootstrap to look up the given name. `Class.getClassLoader() == null` confirms the defining loader in the API model. `getModule()` provides module info (in this lab, the helper is not a named module).

### Use JVM class-loading diagnostics when needed

With JDK 17+:

~~~bash
java -Xlog:class+load=info -javaagent:agent.jar=boot-helper.jar -cp app.jar lab.app.Main
~~~

`-Xlog:class+load` outputs a lot of information (often very verbose). Look for lines related to `lab.boot.BootHelper`, `lab.app.AppDependency`, and their load location/source. There is no need to enable verbose logging across an entire production workload without a specific diagnostic goal.

Avoid confusing **the classpath appearing to contain a class** with **the loader that actually defined the class**. In plugin/application server environments, classes can also be defined by custom loaders from sources that cannot be inferred from `java.class.path` alone.

## 14. When the helper wants to use application logging, metrics, or SDKs

A common anti-pattern:

~~~java
package lab.boot;

public final class TracingHelper {
    public static void record(String operation) {
        com.acme.app.metrics.MetricsClient.send(operation);
    }
}
~~~

This is a **fragment illustrating a class with an inappropriate dependency**, not an example to deploy. If `MetricsClient` is only loaded by the system/custom app loader, the bootstrap helper will not be able to link to it directly.

Reasonable options:

1. **Record/store minimal events in bootstrap** using bootstrap-visible JDK types, then push them outward through controlled communication.
2. **Define a small communication interface in bootstrap** and provide the implementation from the app/agent loader. Do not let bootstrap contain type signatures of the implementation.
3. **Keep SDK libraries on the agent/app loader side**, without pulling the entire SDK down into bootstrap; avoid dependency collisions and class identity issues.
4. **Manage lifetimes**: bootstrap static fields holding callbacks/loaders can block redeployment and unloading; provide a way to deregister/clean up.
5. **Control errors**: a helper injected into system bytecode should not let metrics errors mask business errors or break class loading.
6. **Consider recursion effects**: class loading, logging, `Class.forName`, or instrumentation inside the helper itself can trigger further transformers; filter helper classes out of transformation if the design requires it.

The `Supplier` bridge example is only meant to prove **there is no reverse static reference to an app class**. It is not a guarantee that an arbitrary callback is always thread-safe, deadlock-free, or suitable for every JVM version.

## 15. Bootstrap helper design checklist

Before placing a class into a bootstrap helper JAR:

1. **List static dependencies**: superclasses, interfaces, field/method descriptors, method bodies, library calls. Do not depend directly on classes that only exist in app/custom loaders.
2. **Check JDK types**: do not assume all platform modules are bootstrap-defined; use types that are truly bootstrap-visible.
3. **Package a small JAR with a dedicated package**: do not mix in app classes, the entire agent, or unnecessary third-party libraries.
4. **Append at the right time**: call `appendToBootstrapClassLoaderSearch` before target classes or the helper are resolved along an unintended path.
5. **Verify the defining loader**: `getClassLoader() == null` for the helper, and confirm app dependencies belong to another loader.
6. **Design the communication direction**: if you need to call application-side code, use a bootstrap-visible interface/callback or a controlled messaging mechanism.
7. **Consider modules/readability**: distinguish loader visibility from JPMS read/export/open; do not tweak modules when the root cause is class search.
8. **Test both success and failure**: helper using only JDK → works; helper referencing app class → may throw `NoClassDefFoundError`; callback via shared type → works under the right conditions.
9. **Preserve lifetimes and safety**: avoid holding long-lived static references to application class loaders; check concurrency, exceptions, and overhead.
10. **Check target runtime**: `javac --release` must match the JVM; both instrumented classes and helpers must pass the verifier/linker.

A “simple” bootstrap helper that implicitly depends on system libraries (logging, tracing, JSON) can break all instrumentation as soon as the first JDK class tries to call the helper.

## 16. Self-check questions

1. **Can a bootstrap helper directly call a class that only resides on the application classpath?** Not via normal static bytecode linking; bootstrap does not search downward into the application loader.
2. **Why does `BootHelper.safe()` work while `BootHelper.unsafe()` fails?** `safe` only uses bootstrap-visible types; `unsafe` contains a symbolic reference to `lab.app.AppDependency` loaded by the app loader.
3. **Does having `AppDependency` already loaded by the application loader fix the error?** No. Bootstrap still resolves references according to bootstrap's own capability.
4. **What does `Class.getClassLoader() == null` indicate?** The class is defined by the bootstrap loader (per the Java API).
5. **Does `appendToBootstrapClassLoaderSearch` automatically pull all of the agent's dependencies into bootstrap?** No; it only adds specific JARs to the bootstrap search.
6. **Why does `BootHelper.viaCallback(AppDependency::value)` work?** The helper only links to the bootstrap-visible `Supplier`/`String`; the implementation created by the application loader is called via interface dispatch.
7. **Can `Supplier` be replaced with a custom interface?** Yes, if the shared interface resides in bootstrap and does not contain types that only exist in the application loader.
8. **Why not put the entire agent JAR into bootstrap?** It easily causes class collisions, accessibility errors, dependency issues, and unintended class-loading changes.
9. **How does `Boot-Class-Path` differ from `-cp`?** It extends bootstrap's search path via the agent manifest; `-cp` normally belongs to the system/application loader.
10. **Does `--add-reads` make bootstrap find `AppDependency` defined by the app loader?** No. Module readability and class-loader visibility are two separate issues.
11. **Do `ClassNotFoundException` and `NoClassDefFoundError` always mean the same thing?** No. One typically comes from checked name-based lookup APIs, while the other typically comes from class linkage/resolution.
12. **Can a JAR appended to bootstrap cause `IllegalAccessError`?** Yes, if a non-public class/accessor is defined by a different loader, altering the runtime package/access.
13. **Can a bootstrap helper use every class in platform modules?** There is no such guarantee in the `java.lang.instrument` specification.
14. **Can unloading an app plugin be blocked if bootstrap holds a `static` reference to the plugin's implementation?** Yes. This is a source of class-loader leaks that must be managed.
15. **If you want to know which class a linkage error originates from, what should you do?** Inspect the class containing the symbolic reference, its defining loader, JAR search paths, module/access rules, and loader diagnostic output.

### Official references

- [Java SE 21 — `java.lang.instrument` package specification](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): **supporting bootstrap classes only link to bootstrap-defined classes**, agent class loader, `Boot-Class-Path`, and module readability support.
- [Java SE 21 — `Instrumentation.appendToBootstrapClassLoaderSearch`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): search path, warning not to mix classes/resources, `IllegalAccessError` example, and failed resolution caching.
- [Java SE 21 — `ClassLoader`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): bootstrap/platform/system loaders and delegation.
- [Java SE 21 — `Class`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): `getClassLoader`, `forName`, and defining loader.
- [Java Virtual Machine Specification SE 21, §5 — Loading, Linking, Initializing](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html): symbolic references, runtime packages, and resolution.
- [Java SE 21 — `Module`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html): module readability and module relationships.

**Key takeaway:** **a bootstrap helper only links directly to classes that bootstrap can load/define**. Placing a helper in bootstrap allows bootstrap code to call the helper, but **does not grant the helper permission to look downward into the application class loader**. When you need to call application logic, keep those dependencies on the application side and connect through a controlled, bootstrap-visible interface/callback.