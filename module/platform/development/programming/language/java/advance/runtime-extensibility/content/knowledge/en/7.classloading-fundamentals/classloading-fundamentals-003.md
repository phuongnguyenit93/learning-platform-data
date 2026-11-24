# Roles of Bootstrap, Platform, and Application Class Loaders in Java

## 1. Why Understand the Three Built-in Class Loaders?

When the JVM needs to use a class, the critical question is not only **where the `.class` file or JAR lives**, but also **which class loader found or defined that class**. This directly affects:

- How the JVM loads core Java classes, JDK APIs, and application code.
- Which classes, libraries, or resources a given class can see.
- How the classpath, module path, `ServiceLoader`, and runtime-loaded plugins behave.
- Separating library versions, identifying whether two Java types are the same, and diagnosing `ClassNotFoundException`, `NoClassDefFoundError`, or `ClassCastException`.

In Java 17+, three **built-in class loaders** are worth distinguishing:

1. **Bootstrap class loader:** the class loader built into the virtual machine, responsible for core platform classes.
2. **Platform class loader:** the class loader for Java/JDK platform classes assigned to it and classes visible via delegation.
3. **Application (system) class loader:** the standard class loader for application code, libraries on the application classpath, and modules assigned to it.

These are **three distinct roles in the class-loading mechanism**. They are not names of three directories, not synonymous with three module layers, and not three lifecycle states of a class.

## 2. Relationship Diagram and Scope

In the default Java launcher environment, a common mental model is:

~~~text
          Bootstrap class loader
       (provided by JVM; typically null)
                     ▲
                     │ parent / delegation
          Platform class loader
            (platform classes)
                     ▲
                     │ parent / delegation
     Application/System class loader
       (application classpath/modules)
                     ▲
                     │ parent / delegation, if any
      Custom/plugin class loader
       (created by the application)
~~~

Upward arrows indicate that a loader normally asks its parent loader before trying to locate a class itself under *parent-first* delegation. For built-in loaders in the default environment, the platform loader is the parent or ancestor of the system loader. Custom loaders can choose another parent and in some cases use a different class-lookup policy.

**Do not read the diagram as "every class below is loaded by the loader above."** A loader can **access a class defined by its parent** without redefining that class. JPMS also enforces module access rules, and delegation is sometimes not strictly a rigid tree.

| Criterion | Bootstrap | Platform | Application/System |
|---|---|---|---|
| Primary role | Handles core runtime classes and modules assigned to bootstrap | Makes Java SE/JDK platform classes accessible through the platform scope | Loads application code, dependencies, and application modules assigned to the system loader |
| Obtaining in Java | No equivalent public Java object; typically represented as `null` | `ClassLoader.getPlatformClassLoader()` | `ClassLoader.getSystemClassLoader()` |
| Parent | None | Typically bootstrap, represented by `getParent() == null` | Platform is parent or ancestor; system loader can be customized |
| Typical class sources | Core classes of `java.base` such as `java.lang.Object`, `String` | Certain platform/JDK modules and APIs | Classes in `-cp`, certain named modules on the application module path |
| Is it a `URLClassLoader`? | Not a `URLClassLoader` object | Should not be assumed | **Do not** cast to `URLClassLoader` on JDK 9+ |
| Use as plugin parent? | `null` can be passed, though usually too restrictive | Useful for loaders needing platform APIs while intentionally avoiding the parent application loader | Commonly used when plugins need to see the host's SPI, API, and shared libraries |

**Visibility scope is not identical to where a class is defined.** A platform class can be **defined by bootstrap** yet still **visible through the platform or application loader** via delegation.

## 3. Bootstrap Class Loader: The JVM Startup Foundation

### 3.1. Responsibilities

The bootstrap loader is built into the JVM. It is responsible for defining classes essential for the Java runtime to operate, such as `java.lang.Object`. Key components of the `java.base` module typically belong to the bootstrap scope.

Java does not provide `ClassLoader.getBootstrapClassLoader()`. In the `ClassLoader` API, bootstrap is normally represented by `null`:

~~~java
System.out.println(Object.class.getClassLoader() == null);
System.out.println(String.class.getClassLoader() == null);
~~~

Output on typical JDK 17+ implementations:

~~~text
true
true
~~~

**Here `null` does not mean the JVM "did not load the class."** It is the representation indicating that the class was defined by the bootstrap loader rather than a `ClassLoader` object retrievable directly through the Java API.

### 3.2. Bootstrap Does Not Load the Entire Standard Library

Since Java became modularized, **you must not assume every class in a `java.*` package or every Java SE class is defined by bootstrap**. Some platform APIs or implementation classes are defined by the platform loader. The official API guarantees that *the platform loader sees platform classes*, not that a particular platform class must be defined by platform or bootstrap.

Therefore:

~~~java
ClassLoader parent = null;
~~~

is the way to say "create a custom loader with bootstrap as parent" in the standard loader API; it is **not** a way to ensure the custom loader sees all Java SE APIs. A custom loader that needs broad platform classes should usually choose:

~~~java
ClassLoader parent = ClassLoader.getPlatformClassLoader();
~~~

In practice, do not build business logic on a fixed assumption that a specific Java SE class will always have `getClassLoader() == null` on every JDK, except for core cases you have actively verified.

### 3.3. Do Not Confuse the Bootstrap Loader with the Boot Module Layer

In JPMS, **`ModuleLayer.boot()`** is the layer containing named modules resolved at startup. The **bootstrap class loader** is a class-definition mechanism. These are two different concepts:

- A module in the boot layer can be assigned to the bootstrap, platform, or application loader.
- A class defined by bootstrap does not prove all modules in the boot layer are loaded by bootstrap.
- `Module#getClassLoader()` and `Class#getClassLoader()` let you inspect the loader attached to a module/class; `null` represents bootstrap in those APIs.

Both names contain "boot," but they are not synonymous.

## 4. Platform Class Loader: Scope of Platform Classes

### 4.1. Role and How to Obtain It

Java 9 introduced `ClassLoader.getPlatformClassLoader()`. The platform loader is responsible for platform classes defined by it or its ancestors. A custom loader can use the platform loader as its parent:

~~~java
ClassLoader platform = ClassLoader.getPlatformClassLoader();
ClassLoader child = new ClassLoader(platform) {};
~~~

This is valid Java code inside a method or initializer context; it creates a default child loader without defining any new classes.

Role of the platform loader:

- Makes platform classes accessible to code loaded through the platform scope.
- Serves as a parent/ancestor in the default startup loader hierarchy.
- Provides a suitable parent for extension loaders that need Java SE APIs without intentionally inheriting the entire application classpath.
- Participates in service discovery scoping: `ServiceLoader.loadInstalled(S.class)` is equivalent to locating providers using the platform loader.

Do not think of the platform loader as "the loader that loads all JDK classes." Many JDK/Java SE classes are defined by bootstrap; platform still sees them via delegation.

### 4.2. The Platform Loader Replaces the Old Extension Loader Role

In JDK 8 and earlier, the diagram commonly taught was:

~~~text
Bootstrap -> Extension -> Application
~~~

Java 9 removed the extension mechanism based on `jre/lib/ext` and `java.ext.dirs`, and introduced the term **platform class loader** in the modular loader hierarchy. In Java 17+, do not instruct learners to copy JARs into `lib/ext` to "install" extensions.

An application wanting external libraries should declare dependencies via a build tool, classpath/module path, or its own plugin-loading mechanism. The name `platform` does not mean the application has a "platform JAR" directory that is scanned automatically.

### 4.3. Platform Is Not an Absolute Isolation Boundary

Normal parent-first behavior keeps the platform loader from looking up code that exists only on the application classpath. However, the `ClassLoader` specification notes that in certain scenarios involving upgraded modules and module readability relationships, **the platform loader may have to delegate to other loaders, including the application loader**.

Thus, the claim "platform can never see any application class" is **too absolute**. A reliable design rule is:

- The platform loader represents the platform-classes scope and is an appropriate parent when platform APIs are needed.
- Do not use it as a security solution or sandbox to guarantee blocking all access to application code.
- For classes on the ordinary application classpath, the platform loader is **not** the mechanism used to load them.

## 5. Application/System Class Loader: Application Code and Dependencies

### 5.1. Responsibilities and Naming

`ClassLoader.getSystemClassLoader()` returns the **system class loader**, commonly called the **application class loader**. In a normal launch, this loader defines application classes located on the application classpath or application modules assigned to it.

Example:

~~~bash
java -cp "out:lib/*" com.example.Main
~~~

On Linux/macOS, `:` separates classpath entries; on Windows, `;` is used:

~~~powershell
java -cp "out;lib/*" com.example.Main
~~~

The application loader of a standard launcher can locate classes in `out` and direct JARs in `lib/*`. Actual lookup order also depends on parent delegation, resolved modules, and loader policy.

For JPMS applications:

~~~bash
java --module-path mods --module com.example.app/com.example.Main
~~~

The application module path serves **module discovery and resolution**; classes in those modules are defined by the loader that the runtime/layer assigns to the module. Many application modules in the default boot layer use the system loader, but **the module path is not an independent class loader**.

### 5.2. Distinguishing the System Loader from a Class's Class Loader

The following expression usually returns `true` when `Main` launches from the application classpath:

~~~java
Main.class.getClassLoader()
        == ClassLoader.getSystemClassLoader()
~~~

However, inside an application server, plugin environment, test runner, or custom module layer, **the current class may be defined by a custom loader**. `getSystemClassLoader()` is not always the loader that defined the currently running class.

Ask the right question:

- "What is the JVM's system loader?" → `ClassLoader.getSystemClassLoader()`.
- "Who defined this class?" → `SomeType.class.getClassLoader()`.
- "Which loader is associated with this module?" → `SomeType.class.getModule().getClassLoader()`.
- "Which loader is used as context by the thread?" → `Thread.currentThread().getContextClassLoader()`.

All four expressions can return different results.

### 5.3. Do Not Cast the System Loader to `URLClassLoader`

On Java 8, many examples did the following:

~~~java
URLClassLoader loader =
    (URLClassLoader) ClassLoader.getSystemClassLoader();
~~~

This is an **anti-pattern on JDK 9+**: the built-in application loader is no longer guaranteed to be a `URLClassLoader`; casting it can throw `ClassCastException`. Java SE also provides no supported API to arbitrarily append entries to the running application classpath.

To load plugin JARs after startup, the application should create **its own loader** (for example, `URLClassLoader`) or its own module layer, along with a clear plugin-management flow.

## 6. Parent Delegation Mechanism: Which Loader Actually Loads the Class?

### 6.1. Default Sequence

The default behavior of `ClassLoader.loadClass(name, resolve)`, if not overridden by a subclass, can be summarized as:

1. Check whether a class with the same name has already been found/initialized through this loader using `findLoadedClass`.
2. Ask the parent loader to load the class; if the parent is represented by `null`, ask the bootstrap mechanism.
3. If the parent cannot find it, invoke `findClass` on the current loader.
4. If found and `resolve == true`, link the class as needed using `resolveClass`.

A visual diagram:

~~~text
loadClass("com.example.Feature")
            |
            v
      Found earlier?
       /           \
     Yes            No
      |              |
 Return Class    Ask parent
                    /   \
                 Found  Not found
                  |         |
             Return Class  findClass on child loader
                              |
                         Class / ClassNotFoundException
~~~

With a parent-first plugin loader, if the parent already has `com.example.Feature`, the child loader normally gets back **the parent's own class**, even if the plugin JAR contains a class of the same name. Achieving a child-first policy requires designing a specific custom loader, resolving API conflicts, and respecting module system constraints; never assume all loaders are parent-first.

### 6.2. "Loader Being Asked" Differs from "Defining Loader"

Suppose:

~~~java
ClassLoader platform = ClassLoader.getPlatformClassLoader();
Class<?> type = platform.loadClass("java.lang.String");
~~~

A successful call means the platform loader **can obtain** the `String` class, yet `type.getClassLoader()` on a normal JDK is still `null`, because the class was **defined by bootstrap**.

Therefore, in logging/debugging you should distinguish:

- **Requesting/initiating loader:** the loader receiving the request, which may delegate elsewhere.
- **Defining loader:** the loader that actually defines the class from bytecode; bound to the class's runtime identity.

For a class loaded via a parent, the child loader can act as an initiating loader but is not the defining loader.

### 6.3. Class Identity Depends on the Loader

At runtime, type identity is bound to **binary class name + defining class loader**. Two loaders can define two classes both named `com.example.api.Widget`, yet the JVM does not treat them as one type:

~~~text
com.example.api.Widget [defined by Loader A]
                       ≠
com.example.api.Widget [defined by Loader B]
~~~

This explains a seemingly nonsensical `ClassCastException` when a plugin bundles **a copy** of the host's API/SPI. The common practice is to place shared interfaces in a parent loader or a shared API module; implementations live in the plugin loader.

## 7. Runnable Java 17+ Program: Observing the Three Loaders

The following example uses **a single standalone file**, allowing you to inspect the bootstrap, platform, and application loaders and the difference between choosing platform or system as a parent. No framework, Maven, or external libraries needed.

Create file `LoaderRolesDemo.java`:

~~~java
import java.net.URL;
import java.net.URLClassLoader;

public final class LoaderRolesDemo {

    public static void main(String[] args) throws Exception {
        ClassLoader platform = ClassLoader.getPlatformClassLoader();
        ClassLoader system = ClassLoader.getSystemClassLoader();

        System.out.println("Object-bootstrap="
                + (Object.class.getClassLoader() == null));
        System.out.println("Platform-present=" + (platform != null));
        System.out.println("System-parent-platform="
                + (system.getParent() == platform));
        System.out.println("Demo-defined-by-system="
                + (LoaderRolesDemo.class.getClassLoader() == system));
        System.out.println("Main-TCCL-system="
                + (Thread.currentThread().getContextClassLoader() == system));
        System.out.println("Platform-can-load-Object="
                + (platform.loadClass("java.lang.Object") == Object.class));

        try (URLClassLoader platformChild =
                     new URLClassLoader(new URL[0], platform);
             URLClassLoader systemChild =
                     new URLClassLoader(new URL[0], system)) {

            System.out.println("Platform-child-Object="
                    + canLoad(platformChild, "java.lang.Object"));
            System.out.println("Platform-child-Demo="
                    + canLoad(platformChild, "LoaderRolesDemo"));
            System.out.println("System-child-Demo="
                    + canLoad(systemChild, "LoaderRolesDemo"));
        }

        System.out.println("Demo-module-named="
                + LoaderRolesDemo.class.getModule().isNamed());
        System.out.println("Object-module="
                + Object.class.getModule().getName());
    }

    private static boolean canLoad(ClassLoader loader, String binaryName) {
        try {
            return loader.loadClass(binaryName) != null;
        } catch (ClassNotFoundException expected) {
            return false;
        }
    }
}
~~~

On Bash (Linux/macOS or Git Bash), in the directory containing the file:

~~~bash
mkdir -p out
javac --release 17 -d out LoaderRolesDemo.java
java -cp out LoaderRolesDemo
~~~

Output on a default JDK 17+ launch configuration (no custom system loader configured, no TCCL changes, no upgraded platform modules):

~~~text
Object-bootstrap=true
Platform-present=true
System-parent-platform=true
Demo-defined-by-system=true
Main-TCCL-system=true
Platform-can-load-Object=true
Platform-child-Object=true
Platform-child-Demo=false
System-child-Demo=true
Demo-module-named=false
Object-module=java.base
~~~

**Explanation of each output group:**

- `Object-bootstrap=true`: `Object` is a core class defined by bootstrap; `getClassLoader()` represents it as `null`.
- `Platform-present=true`: Java 17+ provides the platform loader via `getPlatformClassLoader()`.
- `System-parent-platform=true`: with the default JDK launcher, the system loader has platform as its direct parent. The general API contract allows platform to be **parent or ancestor**, because the system loader can be customized.
- `Demo-defined-by-system=true`: `LoaderRolesDemo.class` is on the application classpath `out` and defined by the standard launcher's system/application loader.
- `Main-TCCL-system=true`: the thread running `main` normally has the system loader as its TCCL. Frameworks may change TCCL.
- `Platform-can-load-Object=true`: the platform loader sees `Object` via delegation, even though it is not the loader defining `Object`.
- Both custom loaders have an empty URL array. Both see `Object` thanks to their parents, but only the loader with the **system parent** sees `LoaderRolesDemo` on the ordinary application classpath.
- `Demo-module-named=false` because code on `-cp out` belongs to the unnamed module. `Object` belongs to the named module `java.base`.

**Note:** the output intentionally checks *relationships with booleans* rather than printing implementation names like `jdk.internal.loader.ClassLoaders$AppClassLoader`, since those are internal details and can vary across JDKs. The "platform child does not see Demo" result is the typical classpath scenario of this example, not an absolute isolation law across every JPMS/module-upgrade setup.

With PowerShell/CMD on Windows, you can use `javac --release 17 -d out LoaderRolesDemo.java` and `java -cp out LoaderRolesDemo`; just create `out` with the shell's appropriate command (e.g., `New-Item -ItemType Directory -Force out` in PowerShell).

## 8. How Is the Thread Context Class Loader (TCCL) Related?

`Thread.currentThread().getContextClassLoader()` is the **context loader** attached to a thread. It is not necessarily the loader that defined the currently executing class; it lets platform/framework code work with classes or providers belonging to the application.

For example: a library calls `ServiceLoader.load(MyService.class)`. Per the API, this overload uses **the current thread's TCCL**. If a framework creates a thread whose TCCL only sees platform APIs, the library may fail to find the application's provider on the classpath. Conversely, a framework may intentionally set TCCL to a plugin loader so shared code can locate plugin providers.

Illustrative snippet inside a method:

~~~java
ClassLoader old = Thread.currentThread().getContextClassLoader();
try {
    Thread.currentThread().setContextClassLoader(
            ClassLoader.getPlatformClassLoader());

    // Code inside uses the new TCCL if it looks up TCCL itself.
    // The loader that defined this method's class does not change.
} finally {
    Thread.currentThread().setContextClassLoader(old);
}
~~~

Key distinctions:

1. `setContextClassLoader` **does not move** the running class to the new loader.
2. `Class.forName(String)`, `Class.forName(String, boolean, ClassLoader)`, `ServiceLoader`, and frameworks each have **their own loader selection rules**; do not assume all of them always use TCCL.
3. A new thread normally inherits the TCCL of the thread that created it, unless adjusted.
4. When temporarily changing TCCL, **always restore it** in `finally` to avoid affecting other calls on the same thread.

Specifically with `ServiceLoader`:

~~~java
ServiceLoader.load(MyService.class);  // Current TCCL

ServiceLoader.load(
    MyService.class,
    ClassLoader.getSystemClassLoader());  // Explicit system loader

ServiceLoader.loadInstalled(MyService.class);  // Platform loader
~~~

The snippet above requires importing `java.util.ServiceLoader` and having an actual `MyService` interface; this is an **API illustration, not a standalone program**. `loadInstalled` uses the platform loader and ignores providers located only on the application classpath or application module path. Do not use it as a substitute for plugin discovery.

## 9. Classpath, Module Path, and Loaders: Three Conceptual Layers

### 9.1. Classpath

`-cp`/`--class-path` is **the search path for classes and resources** when running a non-modular application or code belonging to unnamed modules. With the standard launcher, the system loader uses the application classpath.

~~~bash
java --class-path "out:lib/*" com.example.Main
~~~

In this command, there is no fourth loader called the "classpath loader." The **application loader** is the loader that normally uses those classpath entries. Using `URLClassLoader` or another custom loader can create additional **classpath-like search paths** at runtime, yet that is still a concrete loader managed by the application.

### 9.2. Module Path and JPMS

`--module-path` is the location where **JPMS searches for modules**. The module resolver selects which modules participate in the graph; then the module layer/runtime assigns each named module to a class loader.

~~~bash
java --module-path mods \
     --module com.example.app/com.example.Main
~~~

Separate three steps:

- Finding a JAR/module in `mods`.
- Resolving the module into a configuration/module layer via roots, `requires`, `--add-modules`, or other mechanisms.
- Defining the module's classes using the loader assigned to that module.

**Having a JAR on the module path does not mean every class in it has been loaded**, or that the module has automatically been resolved. A module on the application module path is usually assigned to the application loader in the default boot layer, though application-created module layers can use other loaders.

### 9.3. Module Exports/Opens Differ from Class Loader Delegation

A loader may find `com.example.impl.Secret`, yet the named module containing that class **does not export the package** to the caller, so `public` access from another module remains restricted. `exports` permits public API access under JPMS; `opens` controls deep reflection. Conversely, an `exports` declaration does not by itself help a loader load a JAR outside its scope.

To diagnose, ask both questions:

1. **Is the class found/defined by an appropriate loader?**
2. **Does the caller's module have the required readability/access to the module/package containing the class?**

## 10. Designing Runtime Extensibility or Plugins

A host can use the three built-in loaders as a base, though real plugins usually need additional mechanisms:

~~~text
JVM
├─ Bootstrap: core classes
├─ Platform: platform/JDK APIs
└─ Application: host + shared SPI/API + shared dependencies
   ├─ PluginLoader A: plugin A + A's dependencies
   └─ PluginLoader B: plugin B + B's dependencies
~~~

This is **one possible design**, not a structure the JVM automatically creates for every plugin. The plugin manager decides JAR placement, loaders/layers, provider discovery, compatibility checks, and plugin lifecycle.

### 10.1. Choosing a Parent Based on Shared APIs

- **Application/system loader as parent:** plugins can access APIs/SPIs and dependencies provided by the host, fitting when shared interfaces reside in the application loader.
- **Platform loader as parent:** plugins see platform APIs but **do not by default see APIs located only on the application classpath**. If a plugin implements a host interface and both sides do not share the exact same type identity, casting can fail.
- **Bootstrap as parent (passing `null`):** platform scope is narrowed; on JDK 9+ some Java SE classes may not be visible through this parent. Do not pick `null` merely thinking "all Java APIs are in bootstrap."

For each plugin, determine which class loader defines the **contract/interface**, which class loader defines the **implementation**, and the mechanism for exchanging objects, resources, or services.

### 10.2. Parent-First and Dependency Conflicts

If both host and plugin contain `org.example.lib.Helper` and a parent-first loader sees the host copy first, the plugin may receive **the host's version** instead of the version bundled in the plugin JAR. Conversely, child-first for all packages can cause duplicate loading of APIs/SPIs, or even mistakenly load classes that should be shared.

A controlled policy typically:

- Uses a single shared API class/interface copy at the host/shared module.
- Decides whether specific library packages are shared or isolated.
- Never reloads classes in core JDK packages as a conflict-resolution workaround.
- Logs the class name, defining loader, module, and JAR source when errors are detected.

### 10.3. Adding JARs After the JVM Starts

Calling `System.setProperty("java.class.path", ...)` after startup **does not automatically update** the system loader. `ClassLoader.getSystemClassLoader()` likewise provides no standard API to add arbitrary JARs at runtime.

An example of creating a new loader:

~~~java
// Integration snippet, not standalone:
// pluginJar is a Path pointing to an actual plugin JAR.
try (URLClassLoader pluginLoader = new URLClassLoader(
        new URL[] { pluginJar.toUri().toURL() },
        HostSpi.class.getClassLoader())) {

    Class<?> type = pluginLoader.loadClass("com.acme.plugin.Impl");
    // Check contract, instantiate provider, and manage lifecycle.
}
~~~

You must import `java.net.URL`, `java.net.URLClassLoader`, and have `java.nio.file.Path` along with the `HostSpi` interface. In a real application, the loader **must stay alive for the entire duration the plugin is active**. Closing `URLClassLoader` releases resources such as JAR handles and does not force the JVM to unload classes immediately; old classes and loaders can only be collected once no live references remain.

For plugins packaged as named modules, `ModuleFinder`, `Configuration`, and `ModuleLayer` can be used to resolve/create new layers. **This is the module-resolution and loader-assignment layer**, not something the three built-in loaders do automatically.

### 10.4. Class Loaders Do Not Create a Security Sandbox

Choosing the platform loader as a parent **does not make untrusted plugin code safe**. Class loaders primarily serve code organization and finding/defining classes. If a plugin runs in the same process, it can exercise the process's privileges through accessible APIs. For untrusted plugins, consider process/container-level isolation, OS permission policies, and constrained communication protocols.

## 11. Common Errors and How to Verify Them

| Symptom | Common cause | Check/fix |
|---|---|---|
| `Object.class.getClassLoader() == null` | Expected bootstrap behavior, **not** a missing loader | Understand `null` is the bootstrap marker |
| Custom loader with `null` parent cannot see a Java SE API | API belongs to platform part not defined by bootstrap | Consider `ClassLoader.getPlatformClassLoader()` as parent |
| `ClassNotFoundException` for an application class | Queried platform/boot or a plugin loader lacking the needed search path | Identify which loader the call used; inspect classpath/JAR/module resolution |
| `NoClassDefFoundError` | Main class was found, but a dependency, linking, or initialization step failed | Read the full cause; check dependencies and class-loading logs |
| `ClassCastException` between two same-named classes | Two defining loaders created two different types | Unify loader/module for shared API; avoid JARs duplicating contracts |
| `ClassCastException` casting system loader to `URLClassLoader` | JDK 9+ does not guarantee the system loader is `URLClassLoader` | Create a dedicated custom `URLClassLoader` if needed |
| `ServiceLoader` finds no providers | TCCL/loader cannot see providers, missing `META-INF/services` or module `provides` | Use the right overload, descriptor, and module graph |
| `IllegalAccessError` or `InaccessibleObjectException` | Inappropriate JPMS `exports`/`opens` rules | Adjust module descriptor/API design rather than bypassing encapsulation |
| Reloaded JAR yet old class persists | Class already defined in old loader; references/instances/threads remain | Stop plugin, drop references, use a new loader/layer |
| Modified `java.class.path` yet new code not visible | System loader has already been initialized | Restart with the proper classpath or create a dedicated loader |

When debugging, you can observe:

~~~java
System.out.println("Class defining loader: "
        + SomeType.class.getClassLoader());
System.out.println("Class module: " + SomeType.class.getModule());
System.out.println("System loader: "
        + ClassLoader.getSystemClassLoader());
System.out.println("Platform loader: "
        + ClassLoader.getPlatformClassLoader());
System.out.println("TCCL: "
        + Thread.currentThread().getContextClassLoader());
~~~

This is an illustrative snippet needing an actual `SomeType` class. On JDKs supporting the corresponding logging, you can run the application with `-Xlog:class+load=info` to view class-loading activity; log volume and formatting depend on the JDK. Avoid concluding "the class was defined by loader X" solely from a JAR path or from the class loader that was queried.

## 12. Common Pitfalls Moving from Java 8 to Java 17+

**Key changes since Java 9:**

- The Java 8 term **extension loader** was replaced by **platform loader**, and the old `lib/ext` mechanism is no longer supported.
- The application/system loader **is not guaranteed** to be a `URLClassLoader`.
- JPMS adds named modules, module path, module layers, and `requires`/`exports`/`opens` constraints. The "one classpath equals one loader" mental model becomes inaccurate when applications use multiple loaders/layers.
- Some Java SE classes are defined by the platform loader; some are defined by bootstrap. Do not depend on this internal mapping when designing apps.
- `ClassLoader.getPlatformClassLoader()` is the standard API to obtain the platform loader; applications can use it as an appropriate parent for a custom loader.

**Unchanged fundamentals:** parent delegation remains a useful default; classes derive identity from name + defining loader; applications wanting to load plugins at runtime still need to pick loaders/module layers and manage their lifecycle.

## 13. Self-Check

1. **Does `Object.class.getClassLoader()` returning `null` mean Java did not load `Object`?** No. `null` represents the bootstrap loader.
2. **Does the platform loader always directly define all Java SE classes?** No. Platform can see classes defined by bootstrap; actual mapping depends on the runtime/modules.
3. **Is the system loader always the loader of the current class?** No. A class may come from a plugin loader, test runner, application server, or custom layer.
4. **If a class is loaded through the platform loader via delegation, must `Class#getClassLoader` return platform?** No. You must distinguish initiating and defining loaders.
5. **Is `--module-path` a fourth class loader?** No. It is a module search path for JPMS resolution, after which modules are assigned to class loaders.
6. **Is passing `null` as parent enough for a custom loader to see all Java SE APIs?** Do not assume so, especially on JDK 9+.
7. **Why can loaders A and B create two `com.example.Widget` types that cannot be cast to each other?** Because the JVM distinguishes types by binary name plus defining class loader.
8. **Does TCCL determine the loader that defined the currently running method?** No. It is the thread's context loader, useful for frameworks/SPI.
9. **Does dropping a JAR into a plugins directory automatically make the system loader load it?** No. The host must configure loaders/layers and handle discovery, instantiation, and registration.
10. **Can a class loader be used as a sandbox for untrusted third-party code?** No. Loaders do not replace process isolation and permission controls.

## References

- [Java SE 17 — `ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): built-in loaders, delegation, `getPlatformClassLoader()`, and `getSystemClassLoader()`.
- [Java SE 17 — `Thread`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): thread context class loader.
- [Java SE 17 — `ServiceLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): provider lookup scope by TCCL/loader/layer.
- [JDK 9 Release Notes](https://www.oracle.com/java/technologies/javase/9-relnotes.html): changes to built-in loaders, module path, and the system loader no longer being `URLClassLoader`.
- [Oracle JDK Migration Guide — New Class Loader Implementations](https://docs.oracle.com/javase/11/migrate/): differences among bootstrap, platform, and application loaders since Java 9.
