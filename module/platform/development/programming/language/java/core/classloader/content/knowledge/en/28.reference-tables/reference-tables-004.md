# Table of Class Loading Changes Between Java 8 and Modern Java

From **Java 8** to **Java 9+** and through **Java 17, 21, 25, and newer JDKs**, the JVM still preserves key concepts: **binary name**, **defining loader**, **parent delegation**, **loading → linking → initialization**, `ClassLoader.loadClass`, and runtime type identity. The biggest change is not that Java "removed ClassLoader", but rather that **JDK 9 introduced the JPMS module system into the runtime**, replaced the `rt.jar`/`tools.jar` layout with a modular runtime image, replaced the **extension loader** with the **platform loader**, and changed the implementation of the **application loader**. Subsequent JDKs further tightened several **reflection / JDK internals boundaries** and added tools and APIs for modules/code generation.

This Knowledge article is a **reference table of class loading changes between Java 8 and modern Java** under **Java core – classloader / Reference**. The content distinguishes **API rules** from **HotSpot/OpenJDK implementation details**, compares across version milestones, provides Java 8 and Java 17+ code for practical verification, and supplies a legacy code migration checklist.

> **Version scope:** "Modern Java" here primarily refers to **JDK 9+**, with hands-on examples on **JDK 17+**. JDK 21/25 milestones are noted where relevant changes or APIs exist; a HotSpot-specific behavior should not be inferred as a universal guarantee across every JVM or all future JDKs.

## 1. Quick Summary Table: What Changed, What Didn't?

| Topic | Java 8 | Java 9+ / Modern Java | Practical Impact |
| --- | --- | --- | --- |
| Built-in class loader model | Bootstrap → extension → application/system, in common runtimes | Bootstrap → **platform** → application/system | Do not look for `ExtClassLoader` or `lib/ext` as an extension loading mechanism |
| Application loader implementation | On Oracle/OpenJDK 8, typically a `URLClassLoader` subclass | Built-in loader is **no longer a `URLClassLoader`** | Do not cast `ClassLoader.getSystemClassLoader()` to `URLClassLoader` |
| Platform/extension loader | Extension loader used with the extension mechanism | Platform loader accessed via `ClassLoader.getPlatformClassLoader()` (since JDK 9) | A custom loader's parent can select the platform loader |
| Classpath | Primarily classpath + extension mechanism | Classpath **still exists**, alongside module path | App classpath belongs to the unnamed module; module path is for named modules |
| Packaging of JDK classes | `jre/lib/rt.jar`, `lib/tools.jar`, and internal JARs | **Modular runtime image**, no more `rt.jar`/`tools.jar` | Use `jrt:/`, `jmod`, `jlink`, or module APIs instead of hardcoded paths |
| Runtime type identity | Binary name + defining loader | **Unchanged** | Two different loaders can still produce two `Class<?>` instances with the same name |
| Parent delegation | Yes | Still present, but module loading has lookup mechanisms based on modules and loader graphs | Do not oversimplify all module resolution into a linear classpath |
| Module metadata | No `Class.getModule()`/`ModuleLayer` | `Class.getModule()`, `Module`, `ModuleLayer` | Log both the class loader **and** the module, especially on access errors |
| Class visibility | Java access + class loader + certain package/security rules | Adds **module readability / exports / opens** | `public` is not sufficient if the module does not export the appropriate package |
| JDK internal APIs | Many libraries used `sun.*`/reflective internals | JDK 9 introduced module boundaries; JDK 17 enforces **strong encapsulation** by default | Must remove dependencies on internal APIs or open packages in a controlled manner |
| Service discovery | `ServiceLoader` + `META-INF/services` | Adds `uses`/`provides` and `ServiceLoader.stream()` | SPI can operate across module layers, not just classpath resources |
| Resource lookup | `getResource(s)` via loader/classpath/JAR | Adds module encapsulation; JDK resource URLs are typically `jrt:` | `getResource` may not see resources inside an encapsulated named module |
| Code generation | `ClassLoader.defineClass`; Java 8 `MethodHandles` had different APIs | `Lookup.defineClass` since JDK 9, hidden classes since JDK 15 | Frameworks should use modern APIs with appropriate package/module privileges |
| Bytecode version | Java 8 class file major version **52** | Java 9=53, 11=55, 17=61, 21=65, 25=69 | `UnsupportedClassVersionError` if bytecode is newer than the JVM |
| Security Manager | Legacy mechanism and policies existed, though it did not automatically turn a loader into a sandbox | Deprecated for removal in JDK 17; **permanently disabled as of JDK 24** | Do not design new plugin sandboxes using only ClassLoader/Security Manager |
| Diagnostics | `-verbose:class`, `javap`, runtime class loader inspection | Unified Logging such as `-Xlog:class+load`, `Class.getModule`, `jrt:` | Also inspect the module graph, declaring class, and CodeSource |

**Read the table in three distinct categories:** (1) changes **actually in the Java/JDK API**, (2) changes in the **default implementation/layout**, and (3) changes in the **access control model**. Not every row is a "breaking change" for ordinary Java source code.

## 2. ClassLoader Diagrams Before and After JPMS

Java 8, typical JDK system model:

```text
bootstrap loader                (typically returns null from getClassLoader)
        │
        ▼
extension loader                (certain extension JARs)
        │
        ▼
application / system loader     (classpath)
        │
        ▼
custom loaders                 (plugin/webapp/test)
```

Java 9+, common model:

```text
bootstrap loader                     (java.base and several key modules)
        │
        ▼
platform loader                      (certain Java SE/JDK modules)
        │
        ▼
application / system loader          (classpath + appropriate modules)
        │
        ▼
custom loaders                       (depending on delegation/module policy)
```

**Be careful with this diagram:** this is a typical **delegation relationship**, **not a rule** that "every `java.*` class is defined by the platform loader". JDK 9 moved **some**, not all, Java SE/JDK classes between the bootstrap and platform loaders. The Javadoc guarantees that platform classes are **visible through** the platform loader, not that all of them are **defined by** the platform loader. Nor does parent delegation guarantee that a custom-built class loader is always parent-first if it has overridden `loadClass`.

**Remember:** `String.class.getClassLoader() == null` represents the bootstrap loader in both Java 8 and modern JDKs; there is no public API for a corresponding "bootstrap ClassLoader instance" in the way other loaders have.

## 3. Java 8: The Extension Loader and the `lib/ext` Directory Mechanism

In Java 8, the extension mechanism allowed the Java runtime to locate certain JARs in the extension directory without requiring each JAR to be specified on the classpath. It was tied to the **extension class loader** in the standard hierarchy. Some legacy code retrieved the parent of the system loader and assumed it was the extension loader, or copied JARs directly into `$JAVA_HOME/jre/lib/ext`.

Starting in **JDK 9**, the extension mechanism was removed. The solution is **not** to recreate `lib/ext` in newer JDKs, but to place needed libraries on the appropriate **classpath, module path, or module configuration**. The name "extension loader" in older descriptions was replaced by **platform loader**; even though the ancestry in the hierarchy may look similar, **the platform loader no longer scans `lib/ext` as Java 8 did**.

| Legacy Behavior/Code | Status on JDK 9+ | How to Handle |
| --- | --- | --- |
| Copying custom JARs into `jre/lib/ext` | Extension mechanism removed | Move them into app dependencies/classpath or module path |
| Using `-Djava.ext.dirs=...` | No longer a valid deployment option | Remove the property and configure dependencies explicitly |
| Relying on `lib/endorsed` / `java.endorsed.dirs` | Endorsed standards override mechanism removed | Look into upgradeable modules or appropriate module path/classpath |
| Assuming the app loader's parent can read legacy extension JARs | No longer true | Redesign the loader graph/dependencies |
| Using the literal class name `sun.misc.Launcher$ExtClassLoader` | Depends on an implementation that has changed | Use the `ClassLoader.getPlatformClassLoader()` API if a platform parent is needed |

Certain error messages starting in JDK 9/10 when `lib/ext` or legacy properties remain present can prevent the VM from starting. **Do not use `-XX:+IgnoreUnrecognizedVMOptions` as a primary "fix"**: the legacy configuration must be removed and replaced with the proper deployment model.

## 4. Application Loader: Why Can It No Longer Be Cast to `URLClassLoader`?

In Oracle/OpenJDK 8, many applications used to write:

```java
URLClassLoader app =
        (URLClassLoader) ClassLoader.getSystemClassLoader();
```

This is **implementation-dependent code**, not part of the portable Java SE contract. It typically worked on JDK 8 HotSpot, but **no longer works** on the JDK 9+ built-in app loader: the system loader is backed by an internal implementation that is **not a `URLClassLoader`**, so it can throw a `ClassCastException`.

**Fix according to your need:**

- **To read the application classpath:** inspect `System.getProperty("java.class.path")` (note that the module path is a separate mechanism) and the launcher/build configuration, without forcing a cast on the loader.
- **To load plugin JARs at runtime:** create a `new URLClassLoader(urls, parent)` that you **own** and manage its lifecycle; choose the right delegation and shared APIs.
- **To add a dependency to a named module:** use module resolution/layers or an appropriate instrumentation/launcher mechanism; do not expect the app loader to support `addURL` as in Java 8.
- **To locate JDK classes:** use the public APIs of modules/the runtime image instead of searching for system JARs to append to a search path manually.

**There is no universal Java SE API for "adding a URL to the system loader's classpath" across all implementations/JDKs.** Attempting to reflectively invoke internal methods on `BuiltinClassLoader` easily runs into JPMS strong encapsulation and should not be used as an architectural pattern.

## 5. Practice A — A Java 8 Source Program to Compare Both Runtimes

The code uses only APIs that already existed in Java 8, so it can be compiled with JDK 8 or **`javac --release 8`** on JDK 17+. Run that binary on each JDK to compare **runtime** differences, rather than inferring differences from compiler flags.

File **`src/demo/PortableLoaderProbe.java`**:

```java
package demo;

import java.net.URL;
import java.net.URLClassLoader;

public final class PortableLoaderProbe {
    public static void main(String[] args) {
        ClassLoader system = ClassLoader.getSystemClassLoader();
        URL coreResource =
                ClassLoader.getSystemResource("java/lang/String.class");

        System.out.println("bootstrap String=" +
                (String.class.getClassLoader() == null));
        System.out.println("system is URLClassLoader=" +
                (system instanceof URLClassLoader));
        System.out.println("system parent exists=" +
                (system.getParent() != null));
        System.out.println("core resource protocol=" +
                (coreResource == null
                        ? "<unavailable>"
                        : coreResource.getProtocol()));
    }
}
```

Compile/run on **JDK 17+** from the project directory:

```sh
javac --release 8 -d out src/demo/PortableLoaderProbe.java
java -cp out demo.PortableLoaderProbe
```

**Expected stdout on OpenJDK/HotSpot 17:**

```text
bootstrap String=true
system is URLClassLoader=false
system parent exists=true
core resource protocol=jrt
```

On a machine with a **standard Oracle/OpenJDK 8**, compile with JDK 8:

```sh
javac -source 8 -target 8 -d out src/demo/PortableLoaderProbe.java
java -cp out demo.PortableLoaderProbe
```

**Typical stdout on Oracle/OpenJDK 8:**

```text
bootstrap String=true
system is URLClassLoader=true
system parent exists=true
core resource protocol=jar
```

**Scope of claims:** the checks inspecting the system loader's implementation class and `getSystemResource` reflect **Oracle/OpenJDK/HotSpot in a standard configuration**, **not a requirement across every JVM**. A user-defined `java.system.class.loader` or a custom JDK image may produce different results. The `-source 8 -target 8` flags on JDK 8 merely illustrate the compile target; `--release 8` on JDK 17 **does not emulate Java 8's loaders**.

### What Can We Take Away from Those Four Lines?

1. The bootstrap loader is still represented by `null` in `String.class.getClassLoader()`.
2. The built-in application loader changed its implementation in the modular JDK.
3. The system loader still typically has a parent object, but on modern JDKs that parent is the platform loader.
4. JDK runtime class resources shifted from JAR resources (typically `jar:file:...rt.jar!...`) to **`jrt:` resources** of the modular runtime image.

## 6. `rt.jar`, `tools.jar`, `jrt:/`, and the Modular Runtime Image

**Java 8:** many JDK classes and resources resided in JARs such as `jre/lib/rt.jar` and `lib/tools.jar`. Older tools and software opened them using `JarFile` or read from hardcoded paths.

**JDK 9+:** JEP 220/JPMS transitioned the JDK image to a modular format. Those well-known JAR files **no longer exist in their old layout**. Resource access can use **`jrt:/`** (the JRT filesystem provider) to access runtime module contents.

Example of a Java SE class resource:

```text
Typical Java 8:
jar:file:/.../jre/lib/rt.jar!/java/lang/String.class

Typical JDK 9+:
jrt:/java.base/java/lang/String.class
```

These are **illustrative URL examples**, not the exact paths for every OS/JDK image. If code locates a source JAR by stripping `jar:file:` and searching for `!`, it will break on a modular JDK.

**Appropriate alternatives:**

| Purpose | Modern Approach |
| --- | --- |
| Reading JDK module resources | `ClassLoader.getSystemResource` when valid, `Module.getResourceAsStream`, `jrt:` filesystem |
| Listing runtime modules | `ModuleFinder.ofSystem()`, `java --list-modules` |
| Analyzing module dependencies | `jdeps` and module metadata |
| Packaging a minimal runtime | `jlink` (module-aware runtime image) |
| Internal app libraries | Manage separate JARs via classpath/module path; do not add to `rt.jar` |
| Inspecting loaded classes | `Class.getModule()`, `getClassLoader()`, optional `CodeSource`, `-Xlog:class+load` |

**A JMOD is not a regular classpath JAR.** `.jmod` files are used for packaging/linking modules in JDK tooling; you should not expect `URLClassLoader` to read `jmods/java.base.jmod` as a plugin JAR.

## 7. Practice B — Verifying `jrt:` and Module Metadata on Java 17+

File **`src/demo/ModernRuntimeProbe.java`**:

```java
package demo;

import java.net.URL;

public final class ModernRuntimeProbe {
    public static void main(String[] args) {
        ClassLoader platform =
                ClassLoader.getPlatformClassLoader();
        ClassLoader app =
                ClassLoader.getSystemClassLoader();

        URL core = ClassLoader.getSystemResource(
                "java/lang/String.class");

        System.out.println("java.base module=" +
                String.class.getModule().getName());
        System.out.println("app module named=" +
                ModernRuntimeProbe.class.getModule().isNamed());
        System.out.println("String bootstrap=" +
                (String.class.getClassLoader() == null));
        System.out.println("app parent is platform=" +
                (app.getParent() == platform));
        System.out.println("JDK resource jrt=" +
                (core != null && "jrt".equals(core.getProtocol())));
    }
}
```

Compile/run with JDK 17+:

```sh
javac --release 17 -d out src/demo/ModernRuntimeProbe.java
java -cp out demo.ModernRuntimeProbe
```

**Stdout on OpenJDK/HotSpot 17 without replacing the system loader:**

```text
java.base module=java.base
app module named=false
String bootstrap=true
app parent is platform=true
JDK resource jrt=true
```

The verification lines:

- `String` belongs to the named module **`java.base`**, yet is still defined by the bootstrap loader in a standard configuration.
- `ModernRuntimeProbe` is run with `-cp out`, so it belongs to the app loader's **unnamed module**, not a named module just because it has package `demo`.
- `ClassLoader.getPlatformClassLoader()` is a new API introduced in JDK 9.
- The built-in app loader typically has the platform loader as its parent. If the launcher replaces the system loader or the environment is non-standard, do not treat this parent-object detail as a contract across all implementations.
- `ClassLoader.getSystemResource("java/lang/String.class")` typically returns a `jrt:` URL on modular HotSpot. Do not equate `jrt:` with a CodeSource URL; a completely valid class can have `CodeSource == null`.

**Do not use this example on JDK 8**: the code references `getPlatformClassLoader` and `Class.getModule`, two APIs not present in Java 8 source or runtime.

## 8. JPMS Arrived in Java 9: The Classpath Did Not Disappear

JPMS (**Java Platform Module System**, JEP 261) brought:

- `module-info.java` / module descriptor (`requires`, `exports`, `opens`, `uses`, `provides`).
- **Named modules**, the module path, and a resolved module graph.
- **Unnamed modules** for classpath classes; module metadata can be queried via `Class.getModule()`.
- **Readability** between modules and **exports/opens** for packages.
- `ModuleLayer` to create new module configurations/layers at runtime.
- Integrated module-aware service discovery and resource access.
- Class loaders can define classes belonging to named modules, rather than only searching JARs along a classpath.

A class on the application classpath in JDK 17 still has a `ClassLoader`, is still loaded, and still has runtime type identity just as in Java 8, except `Class.getModule().isNamed()` is **false** (unnamed module). If that same class is packaged/launched as a **named module**, its module metadata and access rules differ.

**The right mental model:** starting from Java 9+, you need to think simultaneously about **"which loader defines the class?"** and **"which module/package does the class belong to, and is the module read/exported/opened?"**.

## 9. Practice C — Same Source, Comparing Classpath Mode with Named-Module Mode

Use a simple class to inspect **module identity**. File **`src/demo/ModuleModeDemo.java`**:

```java
package demo;

public final class ModuleModeDemo {
    public static void main(String[] args) {
        Module module = ModuleModeDemo.class.getModule();
        System.out.println("named=" + module.isNamed());
        System.out.println("module=" +
                (module.isNamed()
                        ? module.getName()
                        : "<unnamed>"));
    }
}
```

### C1. Run as a Java 8-Style Classpath (on JDK 17)

```sh
javac --release 17 -d out src/demo/ModuleModeDemo.java
java -cp out demo.ModuleModeDemo
```

**Stdout:**

```text
named=false
module=<unnamed>
```

### C2. Run as a Named Module on the Same JDK 17

Create **`module-info.java`** at the project root:

```java
module com.example.probe {
    exports demo;
}
```

Compile into a **different** output directory to avoid mixing classpath artifacts with module artifacts:

```sh
javac --release 17 -d mods/com.example.probe module-info.java src/demo/ModuleModeDemo.java
java --module-path mods -m com.example.probe/demo.ModuleModeDemo
```

**Stdout:**

```text
named=true
module=com.example.probe
```

**Key takeaway:** the `ModuleModeDemo.java` source did not change, yet the **launch mode and module descriptor** placed the runtime class into a different module. Do not infer from a package name or from `javac` producing a `.class` file that a class automatically belongs to a named module.

**Do not compile or run `module-info.java` with JDK 8**, because JPMS is an API/tooling feature introduced in Java 9. If a library needs to maintain Java 8 compatibility, consider a **multi-release JAR, separate artifacts, or a classpath-first build** depending on your needs, rather than writing `module-info.java` directly and trying to compile it with `-source 8`.

## 10. Module Layers and Custom ClassLoaders

In Java 8, plugin frameworks typically created a `URLClassLoader` for JARs and implemented parent-first or child-first delegation. JDK 9+ still allows this pattern **for classpath-style loading**, while also offering another option: resolving **named modules** and defining a new `ModuleLayer`.

Model:

```text
boot ModuleLayer
   ├─ java.base (bootstrap)
   ├─ java.logging, java.xml, ...
   └─ app modules
         │
         ▼
child ModuleLayer (plugin version/generation)
   ├─ com.example.plugin
   ├─ com.example.plugin.lib
   └─ loaders chosen by layer-definition API
```

Key APIs:

- `ModuleFinder`: locates descriptors/modules on a module path or given paths.
- `Configuration.resolve(...)`: creates a resolved module graph and validates dependencies.
- `ModuleLayer.defineModulesWithOneLoader(...)`, `defineModulesWithManyLoaders(...)`, or `defineModules(...)`: creates the layer and module-to-loader mappings.
- `ModuleLayer.findLoader(moduleName)`: identifies a module's loader within the layer.
- `Class.getModule()`: inspects the module of the actual runtime class.
- `ServiceLoader.load(layer, Service.class)`: discovers providers in the layer using module-aware semantics.

**Note:** **a module layer is not an OS sandbox**. It improves module organization, version/configuration management, and access checks; plugin code still typically runs **inside the same JVM/process and with the same OS permissions**. For untrusted code, process-, container-, or VM-level isolation may be required.

**Note on split packages:** named modules and class-loader mappings impose constraints on the package/module graph. Do not port a child-first loader design that "mixes multiple JARs sharing the same package" directly over to modules and assume it will work.

## 11. Exports and Opens: A Major Change for Reflection

Before Java 9, a library using reflection against private members of JDK internals typically depended on implementation details or security policy and could work on Java 8. Starting in Java 9, named modules enforce boundaries:

- **`requires`**: a module reads another module.
- **`exports p`**: package `p` is accessible via its public API to eligible modules.
- **`exports p to m`**: qualified (targeted) export.
- **`opens p` / `opens p to m`**: enables deep reflection within the given scope.
- **`open module ...`**: opens multiple packages for reflection, without making every member public API in the compile-time sense.

**`public` is no longer enough** if the target resides in a package of a named module that is not exported appropriately. Nor can `setAccessible(true)` automatically bypass JPMS when the package is not opened.

Across **JDK 9–16**, migration temporarily permitted certain relaxed illegal reflective access to JDK internals, subject to warnings/conditions. **JDK 17 (JEP 403)** enforces **strong encapsulation** by default for JDK internals (aside from certain critical APIs); the old blanket relaxation mechanism is gone. You should **migrate to supported public APIs**, using `--add-opens`/`--add-exports` selectively for migration only when genuinely necessary.

**Do not automatically treat every `InaccessibleObjectException` as a classpath issue.** The class was already found; the error lies in module/package reflective access.

## 12. Practice D — Deep Reflection into JDK Internals Blocked Since Java 17

File **`src/demo/ReflectionBoundaryDemo.java`**:

```java
package demo;

import java.lang.reflect.Field;
import java.lang.reflect.InaccessibleObjectException;

public final class ReflectionBoundaryDemo {
    public static void main(String[] args) throws Exception {
        Field internal = String.class.getDeclaredField("value");

        try {
            internal.setAccessible(true);
            System.out.println("opened=true");
        } catch (InaccessibleObjectException denied) {
            System.out.println("opened=false");
        }

        System.out.println("owner module=" +
                String.class.getModule().getName());
    }
}
```

Compile/run on **JDK 17+**, without adding `--add-opens`:

```sh
javac --release 17 -d out src/demo/ReflectionBoundaryDemo.java
java -cp out demo.ReflectionBoundaryDemo
```

**Expected stdout on OpenJDK/HotSpot 17 with JPMS defaults:**

```text
opened=false
owner module=java.base
```

If the operator **intentionally** opens the `java.lang` package of `java.base` to unnamed modules:

```sh
java --add-opens java.base/java.lang=ALL-UNNAMED -cp out demo.ReflectionBoundaryDemo
```

**Stdout when the opening is accepted by the JVM:**

```text
opened=true
owner module=java.base
```

**Takeaway:** the target class already exists and the loader has no issue. Only **module openness** changes the reflective access outcome. `--add-opens` carries risks and should specify the exact package/scope; **do not add blanket wildcard opens for the entire JDK** as a default solution.

**Caution:** this is a demo of access checks and **does not encourage reading or mutating `String`'s private representation** in production. Internal field details can change across JDK versions; the demo simply uses the metadata of the `value` field present on OpenJDK 17 and checks `setAccessible`.

## 13. Named Module vs. Classpath Resource Lookup

`ClassLoader.getResource` and `Class.getResource` have existed since Java 8, but JDK 9+ adds **module encapsulation** to resource lookup.

Example:

```java
URL resource =
        ClassLoader.getSystemResource("sample/config.properties");
```

This is a **snippet** that requires importing `java.net.URL` and having the resource present. On the classpath, the result is typically governed by class loader delegation and search paths. For a resource inside a named module, public resource lookup **can be restricted** if the package containing the resource is not **opened unconditionally**, per the `ClassLoader.getResource` Javadoc. There is a special exception for names ending in `".class"`, though that should not be treated as a way to access arbitrary module internals.

Comparison:

| Case | Java 8-Style Classpath | Java 9+ Named Module |
| --- | --- | --- |
| `config.properties` in the same JAR | Usually findable via loader resource lookup if the path is right | May be `null` if the package is not opened appropriately |
| JDK `.class` resources | Typically `jar:...rt.jar!...` | Typically `jrt:/module/...` |
| `Class.getResource` | Based on package-relative path and loader | For named modules, also involves module-scoped lookup/encapsulation |
| `Module.getResourceAsStream` | API did not exist yet | Uses module-specific resource lookup with access rules |
| Scanning `META-INF/services` | Classpath SPI descriptor | Adds JPMS provider declarations alongside descriptors |

**Debugging:** log the requested resource name, loader, module, package openness, and actual URL. A `null` from a resource lookup **does not always mean the file is missing from the artifact**.

## 14. ServiceLoader: Java 8 Descriptors and Java 9+ Module Providers

**Java 8/classpath SPI**:

```text
META-INF/services/com.example.spi.Parser
    └─ line: com.example.impl.FastParser
```

JDK 9+ still supports this mechanism for classpath/unnamed-module providers, while named modules have:

```java
module com.example.consumer {
    requires com.example.api;
    uses com.example.api.Parser;
}
```

and:

```java
module com.example.provider {
    requires com.example.api;
    provides com.example.api.Parser
        with com.example.impl.FastParser;
}
```

These are **module-info snippets** and require the corresponding modules and classes if you want to compile them. Java 9+ APIs:

- `ServiceLoader.load(layer, service)`: discovers providers within a module layer.
- `ServiceLoader.stream()`: returns a `Stream<ServiceLoader.Provider<S>>` to inspect provider metadata lazily.
- `Provider.type()` and `Provider.get()`: separates type inspection from retrieving the provider instance.

Important caveats remain on both old and new JDKs: `ServiceLoader` is **lazy**, maintains a provider cache, and is not thread-safe for concurrent use on the **same instance**. `reload()` clears the provider cache but **does not redefine JVM classes**. TCCL affects the `ServiceLoader.load(service)` overload; do not assume `Class.forName(String)` uses TCCL.

## 15. ClassLoader APIs: Old, New, and Scope of Use

| API | Available in Java 8? | Java 9+ | Notes |
| --- | --- | --- | --- |
| `ClassLoader.loadClass(String)` | Yes | Yes | Does not require initialization under standard behavior |
| `ClassLoader.defineClass` | Yes | Yes | Protected final, creates a runtime class, does not create an instance |
| `ClassLoader.findClass(String)` | Yes | Yes | Subclass hook; typically overridden instead of replacing all of `loadClass` |
| `ClassLoader.getSystemClassLoader()` | Yes | Yes | Returns the system loader, implementation-dependent |
| `ClassLoader.getPlatformClassLoader()` | **No** | **Yes, since 9** | Used when the platform loader is needed as parent |
| `ClassLoader.getName()` | **No** | **Yes, since 9** | Loader name may be null and is not unique |
| `ClassLoader.getUnnamedModule()` | **No** | **Yes, since 9** | Unnamed module associated with the loader |
| `Class.getModule()` | **No** | **Yes, since 9** | Module of the runtime type |
| `Class.forName(Module,String)` | **No** | **Yes, since 9** | Does not initialize the target; may return null |
| `ClassLoader.findClass(moduleName,name)` | **No** | **Yes, since 9** | For loaders that support named modules |
| `ClassLoader.findResource(moduleName,name)` | **No** | **Yes, since 9** | Module-scoped resource lookup |
| `ClassLoader.resources(String)` | **No** | **Yes, since 9** | Streams resource URLs |
| `ModuleLayer`/`ModuleFinder` | **No** | **Yes, since 9** | Module graph and layers |
| `MethodHandles.Lookup.defineClass(byte[])` | **No** | **Yes, since 9** | Defines a class in the same loader/runtime package from the lookup |
| `MethodHandles.Lookup.defineHiddenClass` | **No** | **Yes, since 15** | Hidden classes for runtime frameworks |
| `ClassLoader.registerAsParallelCapable()` | **Yes** | **Yes** | Not a new JPMS feature |
| `ClassLoader.getClassLoadingLock(String)` | **Yes** | **Yes** | Loader synchronization, distinct from the class-init lock |
| `Thread.getContextClassLoader()` | **Yes** | **Yes** | TCCL is still used by SPI/frameworks |

**Common mistake:** attributing every API with "loader" in its name to JDK 9. For example, `registerAsParallelCapable` existed earlier, and **ClassLoader parent delegation was not reinvented from scratch by JPMS**.

## 16. Binary Compatibility and Class-File Major Versions

| Java release | Class-file major |
| --- | ---: |
| Java 8 | 52 |
| Java 9 | 53 |
| Java 10 | 54 |
| Java 11 | 55 |
| Java 12 | 56 |
| Java 13 | 57 |
| Java 14 | 58 |
| Java 15 | 59 |
| Java 16 | 60 |
| Java 17 | 61 |
| Java 18 | 62 |
| Java 19 | 63 |
| Java 20 | 64 |
| Java 21 | 65 |
| Java 22 | 66 |
| Java 23 | 67 |
| Java 24 | 68 |
| Java 25 | 69 |

**Important:** a class compiled for Java 17 (major 61) **cannot run directly on a Java 8 JVM** (which understands up to 52). Modern JVMs generally support older classfile versions, but the fact that a library was "compiled on Java 8" does not guarantee it has no dependencies on **removed internal APIs** or reflective access blocked by JPMS.

Inspection commands:

```sh
java -version
javac -version
javap -verbose -classpath out demo.PortableLoaderProbe
```

In `javap -verbose`, look for **`major version`**. If you use JDK 17+ and want to build a library compatible with Java 8:

```sh
javac --release 8 -d out src/demo/PortableLoaderProbe.java
```

`--release 8` configures the target bytecode and supported API view matching release 8. However, it **does not turn a Java 17 runtime into Java 8**, does not restore `rt.jar`, and does not turn the system loader into a `URLClassLoader`.

### Multi-Release JAR (JDK 9+)

A **multi-release JAR** can contain baseline code (for example, Java 8) and overrides under `META-INF/versions/9`, `META-INF/versions/17`, etc., with `Multi-Release: true` in the manifest. Depending on the runtime, class and resource resolution selects the appropriate entry according to the JEP 238 mechanism. This is a compatibility strategy; it does not automatically resolve all differences in module encapsulation and loader identity.

**Do not** place two classes with the same binary name outside multi-release or loader boundaries and assume the JVM can pick the version you intend. You need proper packaging/build tooling and testing on the target runtimes.

## 17. Class Identity and Loader Constraints: Rules That Did Not Change

Even with JPMS, runtime classes are still distinguished by **binary name and defining loader**. An example:

```text
loader-A defines p.ServiceImpl → Class A
loader-B defines p.ServiceImpl → Class B

A.getName().equals(B.getName()) = true
A == B = false
```

If two loaders each define **a copy of an API interface** instead of delegating to the host, a plugin implementation can cause a `ClassCastException` or a loader-constraint `LinkageError`. This has been true since Java 8 and **is not automatically solved by the module path**.

Rules to keep in mind:

- Shared API/DTO/exception classes must have a consistent defining-loader strategy.
- A `Class<?>` may belong to a named or unnamed module; the module name does not replace the binary name.
- Having the same `Class.getPackageName()` **does not guarantee the same runtime package**, because runtime package identity also depends on the defining loader.
- Parent-first delegation is the default for many built-in/classpath loaders, whereas a custom child-first loader needs to control duplicate definitions and synchronization.
- Plugin reloads that need to redefine the same binary name typically use a **new defining loader generation**. `URLClassLoader.close()` does not unload classes immediately.
- Class loading, linking, and initialization remain distinct phases. `Class.forName(name,true,loader)` triggers initialization; standard `loadClass` does not.

**JPMS adds module readability/exports/opens**; it does not replace the JVM's identity and linking rules.

## 18. Should a Custom Loader's Parent Be `null` or the Platform Loader?

A Java 8 pattern:

```java
ClassLoader isolated =
        new java.net.URLClassLoader(urls, null);
```

This is a **snippet** that requires an `urls` variable. A `null` parent typically represents a bootstrap-only parent, yet **since JDK 9 the bootstrap loader defines fewer Java SE classes** than in Java 8. If a custom loader needs to see platform classes without depending on the system application loader, consider:

```java
ClassLoader platform =
        ClassLoader.getPlatformClassLoader();

java.net.URLClassLoader isolated =
        new java.net.URLClassLoader(urls, platform);
```

This is a **Java 9+ snippet** requiring valid `urls` and closing the loader when its lifecycle ends. Using the platform parent does not mean the plugin will see all application classes; that may be the exact isolation goal.

Consider the three options:

| Parent | Advantages | Risks / Things to Watch |
| --- | --- | --- |
| `null` | Reduces visibility to application/platform loader objects | May lack Java SE/JDK modules defined by the platform loader |
| `ClassLoader.getPlatformClassLoader()` | Sees platform classes while restricting app classes | Shared app APIs are not automatically visible; API sharing must be designed |
| `ClassLoader.getSystemClassLoader()` | Easily sees host APIs/dependencies | Parent-first may "shadow" the plugin's version if the host contains overlapping dependencies |

**There is no single optimal parent for every plugin.** It depends on shared contracts, API isolation, the module graph, the security threat model, and the lifecycle. `ClassLoader` is not a sandbox for untrusted code even when its parent is `null`.

## 19. Code Generation: `Lookup.defineClass` and Hidden Classes

Java 8 frameworks often used `ClassLoader#defineClass` (via subclassing), reflection into internals, or non-portable APIs to generate classes. Java 9 added:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
Class<?> generated = lookup.defineClass(bytes);
```

This is a **Java 9+ snippet** requiring an import of `java.lang.invoke.MethodHandles`, the bytes of a class in the **same package** as the lookup class, and a lookup holding **PACKAGE** privileges. The API defines a named class with the loader, runtime package, and protection domain matching the lookup class. You cannot use an arbitrary lookup to inject a class into another package or module.

Starting in **JDK 15**, `Lookup.defineHiddenClass` serves anonymous-like/hidden runtime implementation types (JEP 371). Hidden classes are not designed to be discovered by ordinary binary names; they are very useful for proxies, lambdas, and runtime language infrastructure, though not a direct replacement for plugin APIs built around `Class.forName("p.Name")`.

**Migrating bytecode generation libraries from Java 8:**

1. Select the appropriate JVM target major version.
2. Use the appropriate lookup/hidden-class API instead of reflecting into JDK internals.
3. Check `NestHost`/`NestMembers`, sealed classes, records, and package/module rules on JDK 17+.
4. Ensure released frameworks have versions supporting JDK 17/21/25 if used in production.
5. Do not rely on blanket `--add-opens` flags as a permanent architecture.

## 20. Security Manager Is Not the Future of Plugin Isolation

Java 8 had the Security Manager and a permission model that systems used to restrict code based on code source. Yet even when enabled, building a reliable sandbox out of **ClassLoader + SecurityManager** always required a sound threat model and proper configuration.

Change milestones:

| Milestone | Significance |
| --- | --- |
| Java 8 | Security Manager and policy-based permission checks were still in use |
| Java 17 | JEP 411 marked the Security Manager **deprecated for removal** |
| Java 24 | JEP 486 **permanently disables Security Manager** |
| Java 25+ | Do not use the Security Manager to build a traditional Java sandbox |

When untrusted plugin code must be executed, the practical solution is **separating processes/VMs/containers with OS permissions, resource quotas, filesystem/network policies, and IPC validation**, rather than merely customizing `ClassLoader`. A separate process that still holds full host privileges is **not automatically a sandbox either**.

## 21. Diagnostics: Common Old and New Errors After Migration

| Error / Symptom | Usually Related to in Java 8 | When Moving to Java 9+ | How to Investigate |
| --- | --- | --- | --- |
| `ClassCastException` from system loader → URLClassLoader | Implementation cast used to work | App loader is no longer a URLClassLoader | Remove the cast; use a custom URLClassLoader or official APIs |
| `ClassNotFoundException` for an extension JAR | JAR was located via `lib/ext` | Extension mechanism is gone | Move the dependency onto the classpath/module path |
| Tool reports missing `rt.jar`/`tools.jar` | Hardcoded JDK 8 layout | Modular runtime image, `jrt:` | Update the tool; use `ModuleReader`/jrt |
| `NoClassDefFoundError` for a platform API | Bootstrap parent previously saw the class | Class may be defined by the platform loader | Choose the appropriate platform parent |
| `IllegalAccessError` | Package/runtime type/access check | Adds module readability/exports | Log caller/target loader/module/package |
| `InaccessibleObjectException` | Java 8 did not have this JPMS error | Deep reflection blocked by module openness | Use public APIs, or `--add-opens` when unavoidable |
| `ServiceConfigurationError` | Descriptor/classpath/TCCL issue | Also involves `uses/provides` and module layers | Check service type, provider module, and loader |
| `UnsupportedClassVersionError` | Target bytecode > major 52 | Still occurs if target > JVM version | Check with `javap -verbose`, build with `--release` |
| Resource lookup returns `null` | Missing path/JAR | Named module package may not be opened | Check `Module.getResourceAsStream`/opens |
| `ClassNotFoundException` in plugin child | Wrong parent/classpath | Wrong parent or wrong module graph | Record requested/defining loader, layer, and code source |
| `NoSuchMethodError` after upgrading JDK/library | Binary signature mismatch | JDK internal APIs/version skew | Compare `javap -s` output and artifacts |
| Custom bytecode framework failure | Constructor/ASM verifier mismatch | New classfile attributes/modules/nests | Upgrade framework/ASM, test against target release |

**Do not guess the root cause solely from the exception class.** `NoClassDefFoundError` can stem from a missing dependency or a **failed class initialization**; `ClassCastException` can result from two types sharing the same binary name under different defining loaders. Record the **cause chain, loader identity, module, and code source** when available.

## 22. Useful Inspection Commands on Modern JDKs

### Module Inventory

```sh
java --list-modules
java --describe-module java.base
```

These commands help inspect the module graph and runtime image, though they do not automatically identify the custom loader of each plugin class.

### Inspecting Dependencies and JDK Internals

```sh
jdeps --jdk-internals path/to/application.jar
jdeps --multi-release 17 path/to/application.jar
```

These commands are **templates**—replace `path/to/application.jar`. `jdeps` helps detect dependencies on internal APIs and inspect multi-release JARs; it cannot guarantee that every reflective access via strings or dynamic loading will be caught.

### Class Loading Logs

```sh
java -Xlog:class+load=info -cp out demo.ModernRuntimeProbe
java -Xlog:help
```

`-Xlog:class+load` is the **HotSpot Unified Logging** interface on JDK 9+, not a syntax with identical semantics on every JVM. Java 8 used `-verbose:class` for similar observation, though the output formatting differs. Do not build business logic parsers relying on this text log.

### Inspecting Class File Version and Binary Methods

```sh
javap -verbose -classpath out demo.ModernRuntimeProbe
javap -s -classpath path/to/library.jar com.example.Library
```

`-verbose` displays `major version`; `-s` helps compare method descriptors when encountering `NoSuchMethodError`.

### Inspecting Resources from the Module Image

```sh
jimage list "$JAVA_HOME/lib/modules"
```

This command is for JDKs that include the `jimage` tool, with the path written in POSIX shell syntax. The runtime directory layout may vary in custom images; do not hardcode the directory layout when distributing portable applications.

## 23. Process for Migrating a Java 8 Plugin Framework to Java 17+

**Step 1 — classify legacy code.** Look for casts of the system loader to `URLClassLoader`, calls into `sun.*`/`com.sun.*` internals, usage of `lib/ext`/`rt.jar`, runtime modifications to `java.class.path`, and reflection into private JDK members.

**Step 2 — decide on the deployment model.** If all plugins are classpath JARs, you can keep a dedicated `URLClassLoader` per plugin under an appropriate parent. If the system targets **named modules**, design the `ModuleLayer`/module graph/`uses`/`provides`. Not every library needs to be modularized just to run on JDK 17.

**Step 3 — define shared API identity.** Ensure the host and plugins resolve API types (interfaces, DTOs, exceptions) through an agreed defining loader. Inspect `Class.getClassLoader()` and `Class.getModule()` during debugging.

**Step 4 — fix resource discovery.** Use `META-INF/services` properly on the classpath or module `uses/provides` in named modules. Do not assume a loader can see resources inside every named module; account for package opens.

**Step 5 — remove internal dependencies.** Replace reflective hacks with public Java APIs where available, and upgrade bytecode/framework dependencies. Use `--add-opens` temporarily, scoped narrowly to the exact module/package/caller, with a plan to remove it.

**Step 6 — verify multi-release/versions.** Distinguish `javac --release 8` (targeting the older API/bytecode) from JDK 17 runtime behavior. Inspect the `major version` of artifacts, and test on JDK 8 if compatibility is still claimed.

**Step 7 — test within the actual loader graph.** IDEs often place plugin JARs onto the host classpath, causing parent-first delegation to return the host's classes. Test with host and plugin artifacts separated, verifying defining loaders and module layers.

**Step 8 — manage lifecycle.** When reloading a plugin, create an appropriate new loader/layer generation, drain tasks, and release references. `URLClassLoader.close()` does not immediately unload all classes; `ServiceLoader.reload()` only clears the provider cache.

**Step 9 — build diagnostics.** Log the requested class, lookup loader/TCCL, runtime defining loader, named/unnamed module, CodeSource location if available, cause chain, artifact ID/version, and JDK release. Do not leak secrets or log URLs indiscriminately.

**Step 10 — separate the security boundary.** If plugins contain untrusted code, modules and class loaders are only part of the architecture and do not replace an OS sandbox or process separation.

## 24. Decision Table: Which Technology to Use?

| Need | Java 8-Style Solution | What to Consider on Modern JDKs |
| --- | --- | --- |
| Dynamically loading a plugin JAR | Dedicated `URLClassLoader` | Still usable for classpath plugins; choose parent and close properly |
| Isolating two versions of a library | Custom child loader | Child loaders or module layers depending on packaging |
| Describing API dependencies/module boundaries | Maven/Gradle + classpath | Add `module-info.java` when named modules are needed |
| Plugin discovery | `META-INF/services` | Descriptor or module `uses/provides`, ServiceLoader |
| Generating a runtime class in a host package | Custom `defineClass`/framework hacks | `MethodHandles.Lookup.defineClass` with proper lookup privileges |
| Generating an implementation class without binary name discovery | Framework-specific code gen | Hidden class API where appropriate |
| Browsing JDK classes | Reading `rt.jar` | `jrt:`, `ModuleReader`, `jimage`/`jmod` tools |
| Inspecting the loader | `Class.getClassLoader()` | Also inspect `getModule()`/module layer, loader name/code source |
| Using JDK internals | Reflection hack | Replace with supported APIs; avoid permanent `--add-opens` |
| Securing untrusted plugins | Legacy Security Manager/class loader | OS-sandboxed separate process/container/VM with IPC |
| Maintaining a library for Java 8 and 17 | Java 8 bytecode | `--release 8` + testing on both JDK 8/17; consider a multi-release JAR |

**There is no single all-encompassing "ClassLoader replacement technology".** Module layers manage graphs and encapsulation; ClassLoaders define and look up runtime types; process boundaries manage fault and security isolation at the OS level. Choose the tool according to the boundary you need to control.

## 25. Common Misconceptions After Upgrading the JDK

1. **"Java 9 removed the classpath."** False: the classpath and unnamed modules are still widely supported.
2. **"The extension loader is completely gone, so every parent is the bootstrap loader."** False: the extension mechanism was removed, but the **platform class loader** exists.
3. **"The platform loader defines every Java SE class."** False: some classes are defined by the bootstrap loader; the platform loader only ensures the required visibility.
4. **"`getSystemClassLoader()` always returns a `URLClassLoader`."** Not true in a modular JDK, and it was never part of the Java SE contract.
5. **"`ClassLoader.getPlatformClassLoader()` exists in Java 8."** False: added in Java 9.
6. **"`rt.jar` can still be read if you locate the right directory in JDK 17."** False: the modular runtime image uses a different layout.
7. **"`jrt:` is just a JAR URL."** False: it is a dedicated filesystem/scheme for the runtime image.
8. **"`Class.getModule().getName()==null` is an error."** False: an unnamed module is valid.
9. **"When using `module-info.java`, class loader identity no longer matters."** False: binary name + defining loader still matter.
10. **"`public` is always accessible from every module."** False: `exports` and readability also apply.
11. **"`--add-opens` fixes missing classes on the classpath."** False: it opens packages for deep reflection; it does not add missing dependencies.
12. **"`--add-exports` and `--add-opens` are the same."** No; one exports the public API, while the other grants scoped deep reflection.
13. **"`loadClass` runs the static initializer."** Not according to standard implementations; `Class.forName(name,true,loader)` is what triggers initialization.
14. **"A module layer is a sandbox."** No; plugins still typically share the same JVM and OS permissions.
15. **"Just moving a dependency onto the module path immediately makes every JAR modular with the same access rules as a named module."** No; automatic modules, explicit modules, and unnamed modules have different semantics.
16. **"JDK 17 allows legacy illegal reflective access via a single global flag."** Not true under JEP 403 strong encapsulation.
17. **"Any JDK 8 tool will run unchanged simply by building with `--release 8`."** Not if it hardcodes runtime internals, directory layouts, or reflection.
18. **"`ServiceLoader.reload()` redefines provider classes."** No; it clears the cache and does not replace runtime definitions.
19. **"A JAR on the module path is guaranteed to be resolved and loaded."** No; proper module roots, dependencies, and a valid graph are required.
20. **"Java 8 and Java 17 classfiles share the same major version."** False: 52 versus 61; JDK 21 is major 65, and JDK 25 is major 69.

## 26. Self-Check Questions

**1. What is the most prominent built-in class loader change in Java 9?** The extension loader was replaced by the **platform loader** in the new model; the built-in app loader is no longer a `URLClassLoader`.

**2. Did Java 9 remove parent delegation?** No; Java still has delegation, although module-aware loading is more complex.

**3. Should you cast the system loader to `URLClassLoader` on Java 17?** No. Use an application-owned custom `URLClassLoader` if you need URL-based plugin loading.

**4. When a custom loader needs platform classes without app dependencies, which parent should be considered?** `ClassLoader.getPlatformClassLoader()`.

**5. Which Java version introduced `Class.getModule()`?** Java 9.

**6. Does a class run on `-cp` in JDK 17 belong to a module?** Yes; it typically belongs to an **unnamed module**.

**7. Does JDK 17 still have `rt.jar` in the Java 8 location?** No; it uses a modular runtime image and `jrt:`.

**8. Is `String.class.getClassLoader()==null` still valid on Java 17?** Yes; it is typically the bootstrap representation.

**9. What are the classfile major versions of Java 8, 17, 21, and 25?** 52, 61, 65, 69.

**10. Does `--release 8` turn Java 17's app loader into the Java 8 app loader?** No; compile target and runtime behavior are two different things.

**11. What can happen on Java 17 when attempting deep reflection into JDK internals like `java.base/java.lang` from an unnamed module?** `InaccessibleObjectException`, unless openness has been explicitly granted.

**12. What mechanism did Java 9 add to define a class in the same package/loader as a lookup class?** `MethodHandles.Lookup.defineClass`.

**13. Which API do named modules use to declare service providers?** `uses`/`provides ... with ...`.

**14. Does ModuleLayer automatically separate the heap/process for a plugin?** No; a process boundary is required for stronger isolation.

**15. How do you locate JDK runtime class resources on a modular runtime?** Use `jrt:`/Module APIs instead of hardcoding `rt.jar`.

**16. Do classes with the same name but two different defining loaders share the same runtime type identity?** No.

**17. Does `ServiceLoader.reload()` make a new version of a class appear automatically if the old loader has already defined the class?** No.

**18. Why might `ClassLoader.getResource` still return null even though a resource exists in a named module?** The resource's package may not be appropriately opened under module encapsulation.

**19. Does a separate class loader guarantee that plugin code cannot access files or the network?** No; OS permissions/a sandbox are required.

**20. Which environments should you test on when migrating from Java 8 → 17?** Both the target build and runtime environments you need to support, with the proper module/classpath configuration and actual loader graph—not just inside an IDE.

## 27. Official References and Technical Milestones

- [Oracle JDK 17 Migration Guide — Migrating from JDK 8](https://docs.oracle.com/en/java/javase/17/migrate/migrating-jdk-8-later-jdk-releases.html): differences in class loaders, modular runtime images, extension mechanisms, and strong encapsulation.
- [Oracle JDK 9 Migration Guide](https://docs.oracle.com/javase/9/migrate/): Java 8 → 9 milestone, loader names, `rt.jar`, and the module system.
- [JEP 261 — Module System](https://openjdk.org/jeps/261): JPMS, module path, and module-aware class loading.
- [JEP 220 — Modular Run-Time Images](https://openjdk.org/jeps/220): JDK image/JRT and layout changes away from JARs.
- [JEP 238 — Multi-Release JAR Files](https://openjdk.org/jeps/238): JAR version-specific class entries.
- [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): strong encapsulation in JDK 17.
- [JEP 411 — Deprecate the Security Manager for Removal](https://openjdk.org/jeps/411): JDK 17 deprecation.
- [JEP 486 — Permanently Disable the Security Manager](https://openjdk.org/jeps/486): JDK 24 Security Manager change.
- [JEP 371 — Hidden Classes](https://openjdk.org/jeps/371): API for dynamic runtime code generation starting in JDK 15.
- [Java SE 17 ClassLoader Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `getPlatformClassLoader`, `getSystemClassLoader`, module-aware resource/findClass APIs.
- [Java SE 17 Class Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getModule`, `forName`, runtime class metadata.
- [Java SE 25 ClassLoader Javadoc](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html): the ClassLoader contract on modern JDKs.
- [Java Virtual Machine Specification 17, Chapter 5](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): loading/linking/initialization and runtime type identity.

**Conclusion:** Java 8 → modern Java **did not remove ClassLoader**; it transitioned the runtime into a system of **modules**, changed the default loader implementation, removed `rt.jar` and extension dirs, added the **platform loader** and module metadata/layers, and then tightened access to JDK internals. What remained unchanged is that **binary name + defining loader determine runtime type**, along with the principles of loading/linking/initialization and the need to manage the class loader lifecycle. When upgrading, **remove system loader casts**, stop hardcoding JDK JARs, define the classpath/module path clearly, and log **loader + module + CodeSource** together for accurate diagnostics.
