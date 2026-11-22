# Extension Class Loader in Java 8 and Changes from Java 9

> **Context:** Java Core → ClassLoader → Built-in Loaders. This article explains the **Java 8 extension class loader**, the mechanism for locating JARs in extension directories, and why that mechanism was removed in **Java 9** while the **platform class loader** remained. The focus is on reading the loader hierarchy, diagnosing errors, and migrating an application from JDK 8 to JDK 9+ without relying on HotSpot internal details.

## 1. The Key Answer to Remember First

**JDK 8:** Java provides the *installed/optional extensions* mechanism. Placing a JAR in an **extension directory** of the Java runtime allows the JDK to locate external libraries without the application needing to list that JAR on the application class path. A built-in loader commonly called the **extension class loader** is responsible for loading them.

**JDK 9 onward:** The **extension directories** mechanism has been **removed**. Old approaches such as placing JARs into `lib/ext` or passing `-Djava.ext.dirs=...` are no longer supported. Application libraries must be declared explicitly using the **class path**, **module path**, or an application-managed loading mechanism.

**However:** The loader position itself between bootstrap and application **did not disappear**. Starting in Java 9, this built-in loader role is called the **platform class loader**, exposed publicly via `ClassLoader.getPlatformClassLoader()`. It serves platform/JDK classes according to the modular runtime design and **no longer acts as a scanner for JARs in `lib/ext`**.

These are three distinct things that must be kept separate:

1. **Loader name/role:** Extension loader (JDK 8) → platform loader (JDK 9+).
2. **Arbitrary library deployment mechanism:** `java.ext.dirs` / `lib/ext` (JDK 8) → **removed** in JDK 9.
3. **JDK class organization:** `rt.jar` along with internal JARs (JDK 8) → **modular runtime image** and JPMS (JDK 9+).

Renaming the loader does **not** mean `lib/ext` was moved to a new “platform/ext” directory.

## 2. Java 8: Where Is the Extension Class Loader in the Delegation Chain?

With the default launcher and built-in loaders of **Oracle/OpenJDK 8**, the simplified model is:

~~~text
                       Bootstrap Class Loader
                   (typically represented by null)
                                |
                                v
              Extension Class Loader (ExtClassLoader)
                JRE_HOME/lib/ext and extension dirs
                                |
                                v
            Application / System Class Loader (AppClassLoader)
                  -cp / -classpath / CLASSPATH
                                |
                                v
             Custom loaders created by the application
~~~

The arrows in the diagram go from **parent** down to **child**; when locating a class, the default `loadClass` method typically *delegates up to the parent first* and only then calls `findClass` on the child. Therefore, the typical search precedence of the JDK 8 launcher is:

1. Bootstrap: many platform classes from the JDK/JRE, such as most core classes in `rt.jar`.
2. Extension loader: libraries installed in extension directories.
3. Application loader: application classes and dependencies on `-cp`.

**Consequence:** If a class with the same binary name resides in both an extension JAR and the application class path, the version found by the parent extension loader can **shadow** the version the application expects. This is one source of “works on machine A, fails on machine B” issues because different libraries are pre-installed in different JREs.

### 2.1. What Are Extension Directories?

In traditional JDK/JRE 8 packaging, JARs are placed in locations such as:

- `<JRE_HOME>/lib/ext` (in many JDK 8 installations, the Java runtime resides under `<JDK_HOME>/jre`).
- A shared extension directory on some operating systems/distributions.
- Locations specified by the `java.ext.dirs` system property under the Java 8 mechanism.

The term “installed extension” denotes a **runtime-level** deployment approach, not an extension concept like a browser plugin or a Java module. Applications do not need to pass `-cp` separately for JARs that the extension loader discovers in that runtime configuration.

Two configurations to distinguish:

| Java 8 Configuration | Who Typically Finds It? | Scope of Impact |
| --- | --- | --- |
| `<JRE_HOME>/lib/ext/vendor.jar` | Extension loader | Applications using the same JRE can see the library; causes runtime-wide conflicts |
| `-Djava.ext.dirs=some/extdir` | JDK 8 extension loader mechanism | Relies on the JDK 8-specific mechanism; meaningless on JDK 9+ |
| `java -cp app.jar:vendor.jar Main` | Application class loader under the default launcher | Only the process configured with that class path |
| Custom `URLClassLoader` loading JAR URLs | Application-created loader | Scope, permissions, and lifecycle are managed by the application |

Note the path separator for `-cp`: on Unix/Linux/macOS it is **`:`**, and on Windows it is **`;`**. Do not copy commands verbatim across operating systems while overlooking this separator.

**You should not modify a shared JRE installation directory for experiments.** The hands-on steps in the later section use a dedicated library directory inside the workspace and only run with a controlled JDK 8.

### 2.2. Is the Extension Loader a Class in the Java SE API?

Implementation classes such as `sun.misc.Launcher$ExtClassLoader` (JDK 8 HotSpot) are **internal details**. The API specification does not require every JVM to preserve that exact class name, package, or structure. Use `getParent()`, `getClassLoader()`, and standard APIs to observe behavior; do not import `sun.misc.Launcher` and do not compare `getClass().getName()` strings to drive logic.

In JDK 8, the public `ClassLoader` API **does not yet have** `getPlatformClassLoader()`. Attempting to call that method in code compiled for `--release 8` is invalid because this API was introduced in Java 9.

## 3. Why Was the Extension Mechanism Removed Starting in Java 9?

Java 9 introduced the **Java Platform Module System (JPMS)** with named modules, `requires` / `exports` relationships, and a modular runtime image. This change had several motivations: explicit dependency declarations, encapsulation and control over internal APIs, configurable runtime images with selectable modules, and support for tools such as `jlink`.

The old extension mechanism created an “implicit installation channel”:

- JARs were discovered automatically via the JRE without appearing in the dependency or application launch configuration.
- JAR versions could differ from machine to machine, making class loading results hard to reproduce.
- Extension JARs could take precedence over application JARs.
- Copying JARs into the JDK/JRE image broke runtime immutability and complicated update/release management.

Starting in **JDK 9**, extension directories are no longer locations that the runtime scans automatically to load libraries. Configuration via `java.ext.dirs` is rejected rather than silently preserving the old behavior. This is a change **documented in the migration guide**, not merely an arbitrary HotSpot optimization.

### 3.1. Before-and-After Comparison

| Topic | Java 8 | Java 9+ |
| --- | --- | --- |
| Intermediate built-in loader | Commonly called `ExtClassLoader` | **Platform class loader** |
| Public API to obtain intermediate loader | Mainly observed via `getParent()` in default configuration; no `getPlatformClassLoader()` | `ClassLoader.getPlatformClassLoader()`, starting in Java 9 |
| Automatic JAR discovery in `lib/ext` | Yes | **Removed** |
| `-Djava.ext.dirs` | Legacy JDK 8 mechanism | Unsupported; launcher reports an error |
| Platform class layout | Many classes in `rt.jar` and JRE JARs | **Modules** in a modular runtime image |
| Typical URL source of `java/lang/Class.class` | `jar:file:.../rt.jar!...` | `jrt:/java.base/java/lang/Class.class` |
| Application loader | On HotSpot 8, typically a `URLClassLoader` | On OpenJDK 9+, a different internal type, **not a `URLClassLoader` by default** |
| External application libraries | Class path or installed extension JARs | Class path, module path, or custom loader |
| Code accessibility across modules | No JPMS yet | Subject to additional readability, exports, and opens checks |
| Overriding standard JDK components | Legacy endorsed standards mechanism, separate from extensions | Endorsed directories were also removed; certain modules are upgraded via the **upgrade module path** |

**Note:** Do not infer that “Java 9 turned the entire Java runtime into modules, so every JAR is a named module.” A JAR run on the **class path** still belongs to the **unnamed module**; a JAR placed on the **module path** can be an **automatic module** or an explicit named module depending on its contents and how it is resolved.

### 3.2. What Does “The Extension Loader Is Retained Under the Name Platform Loader” Mean Exactly?

The Oracle migration guide explains that the extension class loader was **renamed to the platform class loader** in the built-in loader hierarchy. This statement refers to the **loader layer role**, not reviving the mechanism where “JARs installed into `lib/ext` are discovered automatically.”

Typical Java 9+ model:

~~~text
Bootstrap loader (VM built-in, API may return null)
       |
       v
Platform loader   <-- ClassLoader.getPlatformClassLoader()
       |
       v
Application/System loader <-- ClassLoader.getSystemClassLoader()
       |
       v
Custom loader if created by the application
~~~

Key points:

- All **platform classes** must be **visible** through the platform loader, though they are not necessarily **defined** by the platform loader. Some classes belong to the bootstrap loader; the `getClassLoader()` API for those classes returns `null`.
- Bootstrap in JDK 9+ defines fewer classes/modules than in the JDK 8 model. If a custom loader previously chose `null` as its parent and implicitly assumed it could see **all** platform classes, that assumption may fail after migration.
- The platform loader may need to perform **special delegation** for certain upgraded modules. Therefore, the parent-child diagram is only a baseline model; you should not assume every class is visible only through a single parent-first path.
- Runtime module readability/access and classloader delegation are two **different** mechanisms. A class may be locatable, yet the caller may still not be permitted to access that module's package.

## 4. Two Programs to Observe Loaders — Without Depending on Internal Class Names

### 4.1. A Single Source File That Runs on JDK 8 and JDK 9+

File **`LoaderCompatibility.java`**, without directly using the new API at compile time:

~~~java
public final class LoaderCompatibility {
    public static void main(String[] args) {
        ClassLoader system = ClassLoader.getSystemClassLoader();
        ClassLoader caller = LoaderCompatibility.class.getClassLoader();

        boolean hasPlatformApi;
        try {
            ClassLoader.class.getMethod("getPlatformClassLoader");
            hasPlatformApi = true;
        } catch (NoSuchMethodException ex) {
            hasPlatformApi = false;
        }

        System.out.println("platform API available: " + hasPlatformApi);
        System.out.println("caller uses system: " + (caller == system));
        System.out.println("system has parent: " + (system.getParent() != null));
        System.out.println("String bootstrap: "
                + (String.class.getClassLoader() == null));
    }
}
~~~

Compile on **JDK 8**:

~~~bash
javac LoaderCompatibility.java
java -cp . LoaderCompatibility
~~~

Or compile on **JDK 9+** while targeting Java 8 API/bytecode:

~~~bash
javac --release 8 LoaderCompatibility.java
java -cp . LoaderCompatibility
~~~

Expected output with the **default Oracle/OpenJDK 8 and class path**:

~~~text
platform API available: false
caller uses system: true
system has parent: true
String bootstrap: true
~~~

Expected output when running **the same compiled class** on **default OpenJDK 17/21/25 and class path**:

~~~text
platform API available: true
caller uses system: true
system has parent: true
String bootstrap: true
~~~

The first line differs because `ClassLoader.getPlatformClassLoader()` was only introduced in Java 9. The remaining three lines check properties of the **default runtime environment**; if launched with a custom system loader, a module layer, or a specialized container environment, do not treat them as invariant output across all JVMs.

**Why use reflection?** Writing `ClassLoader.getPlatformClassLoader()` directly in this source would fail to compile under `javac --release 8`. Reflection here is used solely to **detect the existence of the method**, with no need to open internal module access.

### 4.2. Using the API Supported Starting in JDK 9

File **`PlatformLoaderProbe.java`** (compiles only on Java 9 and later):

~~~java
public final class PlatformLoaderProbe {
    public static void main(String[] args)
            throws ClassNotFoundException {
        ClassLoader platform = ClassLoader.getPlatformClassLoader();
        ClassLoader application = ClassLoader.getSystemClassLoader();

        System.out.println("platform exists: " + (platform != null));
        System.out.println("app sees platform as parent: "
                + (application.getParent() == platform));
        System.out.println("platform sees String: "
                + (platform.loadClass("java.lang.String") == String.class));
        System.out.println("String defined by bootstrap: "
                + (String.class.getClassLoader() == null));
    }
}
~~~

~~~bash
javac PlatformLoaderProbe.java
java -cp . PlatformLoaderProbe
~~~

Typical output with **OpenJDK 17/21/25, default system loader**:

~~~text
platform exists: true
app sees platform as parent: true
platform sees String: true
String defined by bootstrap: true
~~~

The third and fourth lines illustrate the difference between **visible to** and **defined by**. The platform loader **sees `java.lang.String` through bootstrap**, rather than defining a separate `String` of its own. There is no basis to claim that “all Java SE classes are defined by the platform loader.”

Do not cast `platform` or `application` to `URLClassLoader` to obtain the list of URLs. On many JDK 9+ HotSpot runtimes, that cast will fail:

~~~java
// Counterexample: DO NOT use in JDK 9+ migration code.
java.net.URLClassLoader urls =
        (java.net.URLClassLoader) ClassLoader.getSystemClassLoader();
~~~

If you need the class path that was passed to the launcher, store the application's launch/build configuration. If you genuinely need to load JARs from dynamic URLs, the application can **create its own** `URLClassLoader` with an appropriate parent; this is an **application-owned** loader, not the built-in system loader.

## 5. Hands-On Migration: Moving an Extension JAR to the Class Path

For example, suppose there is a small library in package `legacy.greeting` and a client program. Illustrative directory structure:

~~~text
demo/
├─ src/
│  ├─ legacy/
│  │  └─ greeting/
│  │     └─ Greeting.java
│  └─ LegacyClient.java
└─ build/             (created by the compile commands)
~~~

File **`src/legacy/greeting/Greeting.java`**:

~~~java
package legacy.greeting;

public final class Greeting {
    private Greeting() { }

    public static String message() {
        return "hello from library";
    }
}
~~~

File **`src/LegacyClient.java`**:

~~~java
import legacy.greeting.Greeting;

public final class LegacyClient {
    public static void main(String[] args) {
        System.out.println(Greeting.message());

        ClassLoader library = Greeting.class.getClassLoader();
        ClassLoader application = LegacyClient.class.getClassLoader();
        System.out.println("same defining loader: "
                + (library == application));
    }
}
~~~

### 5.1. Preparing the JAR and Client Classes

The following commands run from the `demo` directory in a **POSIX shell**. To test on both Java 8 and Java 9+, build the JAR and client with JDK 8 to avoid bytecode version errors when running on the older version:

~~~bash
mkdir -p build/libclasses build/clientclasses build/extensions
javac -d build/libclasses src/legacy/greeting/Greeting.java
jar cf build/greeting.jar -C build/libclasses .
javac -cp build/greeting.jar -d build/clientclasses src/LegacyClient.java
~~~

The relative paths can be replaced with the corresponding paths in PowerShell or Gradle/Maven. The step above only creates artifacts for the **experiment**, without touching `JAVA_HOME`.

### 5.2. Java 8: Using a Separate, Controlled Extension Directory

In the Java 8 practice environment, copy `greeting.jar` into `build/extensions`. Then run:

~~~bash
cp build/greeting.jar build/extensions/
java -Djava.ext.dirs=build/extensions -cp build/clientclasses LegacyClient
~~~

Expected output with the **default Oracle/OpenJDK 8 launcher**:

~~~text
hello from library
same defining loader: false
~~~

**Explanation:** The client is defined by the application loader; `Greeting` is found by the extension loader (the parent of the application loader in JDK 8). The two classes do not have the same **defining loader**. This intentionally simulates the legacy extension mechanism without copying the library into a shared JRE.

If you run the command above on JDK 9+, the launcher will **reject** `-Djava.ext.dirs=...`. Do not misdiagnose this as a `ClassNotFoundException` in the application: the failure can occur **before `main` even runs**.

### 5.3. Java 9+: Moving the JAR to the Application Class Path

After **removing** the legacy property, run with both entries on the class path.

Linux/macOS:

~~~bash
java -cp "build/clientclasses:build/greeting.jar" LegacyClient
~~~

Windows PowerShell / Command Prompt:

~~~powershell
java -cp "build/clientclasses;build/greeting.jar" LegacyClient
~~~

Expected output on the default JDK 9+ launcher:

~~~text
hello from library
same defining loader: true
~~~

Without the extension mechanism, both the client and the library are on the **application class path**, so they share the same system/application loader in a typical configuration. **The API and business behavior remain correct** even though the returned class loader has changed.

**Do not force the two loaders to be different after migration.** A change in loader role/identity when switching deployment modes is expected. Business logic should not depend on a JAR being loaded by `ExtClassLoader` in order to work.

### 5.4. Practical Lessons from the Example

- Shared libraries should not be “installed system-wide” implicitly; projects should declare versioned dependencies.
- Parent-first delegation meant an old extension JAR could win over the version on the application class path in JDK 8; moving to the class path can change which class version is selected when duplicate JARs exist.
- When class identity changes, `instanceof`, casts, serialized metadata, reflective lookups, and caches may yield different results; inspect data exchanged across loader boundaries.
- If building with a newer JDK and running on JDK 8, you must set a compatible target (`javac --release 8` on supporting compilers) **and** ensure dependency/API compatibility. JDK 8 understands class file major version **52**, whereas JDK 17 defaults to producing major version **61**.

## 6. Three Proper Ways to Deploy Libraries on Java 9+

### Approach A — Class Path: Suitable for Legacy JAR Applications

Command explicitly listing the dependency JARs:

~~~bash
# Linux/macOS
java -cp "app.jar:libs/*" com.example.Main
~~~

~~~powershell
# Windows
java -cp "app.jar;libs/*" com.example.Main
~~~

When writing an actual program, replace `com.example.Main` with the main class in your application. The command uses a **wildcard class path** to include JARs located directly inside `libs`; it **does not recursively scan** subdirectories. Build tools such as Gradle and Maven typically manage dependencies and construct the class path instead of writing it manually.

Advantages: relatively straightforward migration from JDK 8; JARs are not required to have `module-info.class`. Limitations: classes on the class path all reside in the unnamed module corresponding to the loader; they do not immediately gain the strong encapsulation of named modules.

### Approach B — Module Path: For Applications Using JPMS

A JAR with an explicit `module-info.class` runs as a named module—for example, after you have built `app.jar` and the appropriate dependencies:

~~~bash
java --module-path "mods:libs" \
     --module com.example.app/com.example.Main
~~~

On Windows, replace the separator in the module path with `;` (or let your build tool generate the corresponding command). The module name and main class in the command above illustrate the **syntax form**; a real project must use its own actual module descriptor and package names.

For legacy JARs without a module descriptor, Java provides the **automatic modules** mechanism when placing the JAR on the module path. However, for a module to be **resolved**, the application must form an appropriate graph (for instance, via `requires` or `--add-modules` configuration); placing an arbitrary JAR on the module path does **not** mean all its classes are automatically visible.

The class path and module path are not mechanically interchangeable: package conflicts, split packages, exports/opens, service providers, and module readability all need to be verified during migration.

### Approach C — Custom Loader When Plugin Isolation Is Needed

If an application dynamically loads plugins by version or at runtime, a custom loader or an application-created `URLClassLoader` can still be valid:

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class PluginLoaderExample {
    public static void main(String[] args) throws Exception {
        URL jar = Path.of("plugins", "plugin.jar")
                      .toUri().toURL();

        try (URLClassLoader pluginLoader = new URLClassLoader(
                new URL[] { jar },
                ClassLoader.getPlatformClassLoader())) {
            // Only illustrates creating the loader and releasing resources.
            System.out.println(pluginLoader.getParent()
                    == ClassLoader.getPlatformClassLoader());
        }
    }
}
~~~

File **`PluginLoaderExample.java`**, compiled/run with Java 17+:

~~~bash
javac PluginLoaderExample.java
java PluginLoaderExample
~~~

Output:

~~~text
true
~~~

This example illustrates **selecting the parent via the public API**; it **does not require** `plugins/plugin.jar` to exist on disk in order to construct a URL. If you need to load classes from a JAR, the application must provide an actual file, call `loadClass` or use a module layer, and manage the lifecycle and dependencies.

**Important note:** Choosing `ClassLoader.getPlatformClassLoader()` as the parent for a plugin does **not automatically grant visibility to interfaces defined by the application loader**. If the plugin needs to share host SPIs/interfaces, design an appropriate parent boundary (typically using a loader that sees the shared contract) to avoid duplicate class identities. Choose the platform parent when the goal is to inherit only platform classes and you understand the specific dependencies.

`URLClassLoader.close()` releases closeable resources; it **does not guarantee immediate class unloading**. Thread context class loaders, caches, threads, listeners, and static registries may continue to retain the loader.

## 7. Do Not Confuse Extension, Endorsed, and Upgrade Module Path

In JDK 8, at least **two distinct legacy mechanisms** existed:

1. **Extension mechanism**: library or optional-package JARs in `lib/ext`, configured via `java.ext.dirs`. Removed in JDK 9; replaced by explicit class path/module path or custom loading as needed.
2. **Endorsed standards override mechanism**: `lib/endorsed`, `java.endorsed.dirs`, used to replace versions of certain permitted standard APIs. Also removed in JDK 9; when you need to **upgrade an actual module that Java permits upgrading**, consult `--upgrade-module-path` under JPMS.

`--upgrade-module-path` is **not** a “new name for `java.ext.dirs`.” It applies only within the module model, following rules for which modules are upgradeable, and is not meant to scan arbitrary utility JARs. Similarly:

- `--patch-module` is a mechanism for patching the contents of **a specific named module**; do not use it as a substitute for normal dependencies.
- `--add-exports` grants access to unexported public packages during migration; it **does not add** missing classes or JARs.
- `--add-opens` relates to deep reflection across modules; it **does not** re-enable the extension class loader.
- `-Xbootclasspath/a`, even where supported by a JVM in certain scenarios, is not a general replacement for the extension mechanism.

Identify the actual problem before choosing an option: “JAR not found” is a **deployment/class path/module path** problem; “class found but access denied” is a **module/access** problem.

## 8. Key Details When Upgrading from Java 8 to 9, 11, 17, 21+

| JDK Version | Key Points Directly Related to Extensions/Class Loading |
| --- | --- |
| **8** | Has extension directories and the `java.ext.dirs` mechanism. The intermediate loader is commonly called `ExtClassLoader`. The traditional runtime contains `rt.jar`. |
| **9** | **Removed extension & endorsed mechanisms**; introduced the platform class loader, `getPlatformClassLoader()`, JPMS, modular image, and `jrt:/`; OpenJDK's system/application loader is no longer a `URLClassLoader`. |
| **10** | Continues the JDK 9 model. Audit legacy launch scripts because extension flags/directories are invalid. |
| **11** | Removed Java EE/CORBA modules under JEP 320, so some classes/APIs present in JDK 8 are no longer in the JDK; you cannot “fix the loader” to make JDK 11 provide removed classes automatically. |
| **17** | JEP 403 enforces strong encapsulation on many internal JDK APIs; legacy reflection code may encounter `InaccessibleObjectException`—this is a module access issue, separate from the extension mechanism removed in 9. |
| **21, 25, and newer** | Continues using built-in bootstrap/platform/application loaders with JPMS; do not build logic on internal class names or `lib/ext` layout. Tool options, module graphs, and class file versions must be verified against the specific runtime release. |

**Separate compile-time and runtime versions:** `ClassLoader.getPlatformClassLoader()` belongs to the **Java 9+ API**, so a class compiled against the Java 8 API cannot call it directly. Conversely, Java 8-compatible class files do not guarantee that every JAR or Java SE API still exists on newer JDKs. Migration must verify APIs, module graphs, libraries, and startup configurations alike.

## 9. Diagnosing Failures When Upgrading an Application's JDK

### Symptom A: JVM Refuses to Start Due to `java.ext.dirs`

Example message documented by Oracle:

~~~text
<java-home>/lib/ext exists, extensions mechanism no longer supported; Use -classpath instead.
Error: Could not create the Java Virtual Machine.
~~~

Or a similar message with `-Djava.ext.dirs=...`. How to resolve:

1. Search for the configuration in start scripts, IDE VM options, Dockerfiles, Gradle/Maven launch tasks, application servers, and relevant environment variables.
2. **Remove** `-Djava.ext.dirs` and do not recreate a `lib/ext` directory in the new JDK image.
3. Place the required JARs into dependencies/class path/module path with explicit versions.
4. Re-run with the target runtime and verify the actual defining loader of the classes.

### Symptom B: `ClassNotFoundException` / `NoClassDefFoundError` After Migration

The cause may be a JAR that previously resided in an extension directory and is no longer on the class path/module path. `ClassNotFoundException` typically occurs when an explicit class lookup fails; `NoClassDefFoundError` can occur when a class required by bytecode cannot be resolved at runtime or due to another initialization/linkage cause. Do not conclude a JAR is missing from the exception name alone; read the full cause.

Inspect the artifacts:

~~~bash
jar tf build/greeting.jar
java -version
java -verbose:class -cp "build/clientclasses:build/greeting.jar" LegacyClient
~~~

The `jar tf` command lists the entries inside the JAR; `-verbose:class` shows class loading events across many JDKs, though the log format depends on the VM/version. In the command above, `:` is for Linux/macOS; on Windows, change it to `;`.

JDK 9+ HotSpot supports unified logging:

~~~bash
java -Xlog:class+load=info -cp "build/clientclasses:build/greeting.jar" LegacyClient
~~~

Use `java -Xlog:help` to see available tags and VM options. This is a **HotSpot diagnostic tool**, not part of a stable interface across every JVM implementation.

### Symptom C: Casting the System Loader to `URLClassLoader` Fails

A `ClassCastException` after upgrading is often caused by code assuming `ClassLoader.getSystemClassLoader()` is a `URLClassLoader` based on HotSpot 8. How to fix: replace it with `ClassLoader`/`Class` APIs when you only need to load classes or resources, or create your own `URLClassLoader` if dynamic URLs are needed. Do not attempt to cast to internal JDK class names.

### Symptom D: Custom Loader with Parent `null` Cannot See Platform Classes

In JDK 8, some code used `new URLClassLoader(urls, null)` because it assumed bootstrap could see all platform classes. In JDK 9+, some platform classes are defined by the platform loader rather than bootstrap; choosing `ClassLoader.getPlatformClassLoader()` as the parent can be appropriate if visibility to platform classes is needed. If the plugin also needs **host APIs**, you must select a more suitable parent or contract.

### Symptom E: `IllegalAccessError` or `InaccessibleObjectException`

This may involve named modules, package exports/opens, and strong encapsulation. Check the module path, `module-info.java`, and reflective calls. Moving from `lib/ext` to the class path **does not automatically resolve** all module access errors.

## 10. Step-by-Step Migration Checklist

1. **Baseline the environment before changing anything:** record `java -version`, launcher command, `java.class.path`, build dependencies, JDK vendor, source code, and the runtime image currently in use.
2. **Search for extension assumptions:** `lib/ext`, `java.ext.dirs`, `-extdirs`, `ExtClassLoader`, `sun.misc.Launcher`, casts of the system loader to `URLClassLoader`, and hard-coded `rt.jar` references.
3. **Inventory extension JARs:** name, version, source, license, public APIs, transitive dependencies, and class/package overlaps. Do not copy the JDK 8 directory wholesale into the new JDK.
4. **Choose the new deployment approach:** class path for typical legacy applications; module path when adopting a JPMS design; custom loader if genuinely managing dynamic plugins.
5. **Update launcher/build:** remove `java.ext.dirs` and other removed options; declare dependencies in the build; verify path separators and ensure JARs are packaged with the deployment artifact.
6. **Verify class identity:** if plugins or frameworks are present, check the defining loader of shared interfaces, modules, and binary names; avoid duplicating libraries between host and plugin when types must be shared.
7. **Check bytecode compatibility:** run on the target JDK and inspect the major version with `javap -verbose` if `UnsupportedClassVersionError` appears.
8. **Check module access:** distinguish missing dependencies from access errors; use proper module configuration.
9. **Re-run integration tests:** especially service providers, JDBC drivers, app servers, reflection, serialization, resource lookup, and plugin loading.
10. **Deploy reproducibly:** fixed runtime image, pinned dependency versions, explicit start command; never require operators to manually copy JARs into the JDK.

## 11. Self-Check Questions

1. **Did Java 9 remove the platform loader?** No. It received a new name and public API; what was removed is the extension directories mechanism.
2. **Can `-Djava.ext.dirs=libs` be changed to `-Djava.platform.dirs=libs`?** There is no such option or API.
3. **Must a platform class be defined by the platform loader?** No. It can be defined by bootstrap while still being visible through the platform loader.
4. **Is placing `foo.jar` on the module path enough to guarantee the application sees the module?** No. The module must be in the resolved graph, and its packages must allow access.
5. **Why does a Java 8 application load the right class while JDK 9+ loads a different version of the class?** An extension JAR may previously have preceded the application class path; after migration, deployment/loader precedence changed.
6. **Can JDK 9+ use `URLClassLoader` for plugins?** Yes, by having **the application create its own loader**, not by casting the built-in application loader.
7. **Does using parent `null` in a custom loader guarantee visibility of all Java SE classes?** No; on a modular JDK, choose the platform parent if you need platform classes that bootstrap does not define.
8. **Is `java.endorsed.dirs` another name for `java.ext.dirs`?** No. They are two separate legacy mechanisms, both removed starting in JDK 9.
9. **When `NoClassDefFoundError` appears, does it always mean a missing JAR?** No; you must inspect the cause, class file compatibility, and initialization/linking.
10. **Should you write unit tests asserting the internal name `jdk.internal.loader.ClassLoaders$PlatformClassLoader`?** No; test behavior and supported APIs instead.

## 12. Primary References to Consult

1. [Oracle JDK Migration Guide — New Class Loader Implementations, Removed Extension Mechanism](https://docs.oracle.com/en/java/javase/26/migrate/migrating-from-jdk-8-later-jdk-releases.html): confirms the new system loader, platform loader, and how to handle `lib/ext` / `java.ext.dirs`.
2. [Oracle Java SE 8 Extension Mechanism](https://docs.oracle.com/javase/8/docs/technotes/guides/extensions/spec.html): describes optional packages/installed extensions and legacy precedence.
3. [Oracle Java Tutorial JDK 8 — Understanding Extension Class Loading](https://docs.oracle.com/javase/tutorial/ext/basics/load.html): the bootstrap → extension → class path model in Java 8; **historical documentation; do not apply `lib/ext` directory deployment on newer JDKs**.
4. [`ClassLoader` Java SE 9 API](https://docs.oracle.com/javase/9/docs/api/java/lang/ClassLoader.html): the first standard API documentation featuring `getPlatformClassLoader()` and built-in loaders.
5. [JEP 261 — Module System](https://openjdk.org/jeps/261): module path, readability/access, and class loading changes to support JPMS.
6. [JEP 220 — Modular Run-Time Images](https://openjdk.org/jeps/220): modular images, the removal of `rt.jar` as before, and implications for tools reading classes/resources.
7. [JDK 9 Release Notes](https://www.oracle.com/java/technologies/javase/9-relnotes.html): confirms removal flags and migration recommendations.
8. [JEP 320 — Remove Java EE and CORBA Modules](https://openjdk.org/jeps/320), [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): other JDK upgrade errors easily mistaken for classloader errors.

**Practical conclusion:** When upgrading from Java 8, remove all paths installing JARs into `lib/ext` and all assumptions about internal class loaders. On Java 9+, use the **platform class loader** via its supported API when delegation to platform classes is needed, while application dependencies must be explicitly declared on the **class path/module path** or in an application-managed custom loader.
