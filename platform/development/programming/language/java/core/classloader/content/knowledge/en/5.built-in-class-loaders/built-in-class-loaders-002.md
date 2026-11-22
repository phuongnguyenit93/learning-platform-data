# Platform class loader in modern JDKs

The **platform class loader** is one of the built-in class loaders of the Java runtime from **Java 9 onward**. It allows Java code and custom class loaders to access classes belonging to the **Java platform** without assuming that all Java SE/JDK classes are defined by the **bootstrap class loader**. On Java 17+, the API to obtain this loader is `ClassLoader.getPlatformClassLoader()`.

This is an important distinction after Java transitioned to the **Java Platform Module System (JPMS)**: part of the platform classes are defined by the bootstrap loader, and part by the platform loader. Therefore, **a class visible from the platform loader is not necessarily defined by the platform loader itself**. This lesson explains the place of this built-in loader, its delegation mechanism, its relationship with modules, how to observe it on JDK 17+, and common design mistakes.

## 1. Why does Java need the platform class loader?

Before Java 9, learners commonly saw this model:

```text
Bootstrap ClassLoader
       ↑
Extension ClassLoader
       ↑
Application/System ClassLoader
       ↑
Custom ClassLoader
```

In modern JDKs, the basic presentation becomes:

```text
Bootstrap loader (provided by the JVM; Java typically represents it as null)
             ↑
Platform loader (ClassLoader.getPlatformClassLoader())
             ↑
Application/System loader (ClassLoader.getSystemClassLoader())
             ↑
Custom loader with the system loader as its parent, if chosen that way
```

The arrow `↑` represents a **typical parent/delegation relationship**; it is not a Java class `extends` relationship, nor does it prove that every actual lookup follows a strict straight line. Custom loaders can choose a different parent; built-in loaders have special handling to support modules.

Key changes since Java 9:

1. **The old extension mechanism was removed.** `jre/lib/ext` or `java.ext.dirs` are no longer used as an automatic extension installation mechanism as in JDK 8.
2. **The extension class loader was replaced in role/name by the platform class loader.** Do not treat the new name as merely a relabeling while the extension directory mechanism still operates.
3. **Many Java SE/JDK classes reside in modules**, not in a single `rt.jar`. Platform modules can be defined for the bootstrap or platform loader.
4. **The application loader in common JDKs from Java 9 onward is no longer guaranteed to be a `URLClassLoader`.** Do not cast `(URLClassLoader) ClassLoader.getSystemClassLoader()` to add JARs.
5. **The public API `ClassLoader.getPlatformClassLoader()` was added in Java 9** so applications can choose an appropriate parent when they want visibility to platform classes without implicitly taking the application classpath as the parent namespace.

The platform loader is an internal component of the **runtime class-loading system**. It is not a JAR, not a new JVM, not a class loader created by the application per package, and not another name for the thread context class loader.

## 2. The three built-in loaders and their different roles

| Component | Identifying API | Primary role | Notes |
| --- | --- | --- | --- |
| **Bootstrap loader** | `SomeClass.class.getClassLoader() == null` typically represents bootstrap | Loads/defines many core platform classes, including `java.lang.String` | Bootstrap has no normal `ClassLoader` object exposed to Java; `null` has a special meaning here. |
| **Platform loader** | `ClassLoader.getPlatformClassLoader()` | Provides access to all platform classes; defines some classes in platform modules, while also seeing classes defined by bootstrap | Since Java 9; has the built-in implementation name `platform` in common JDKs. |
| **Application/System loader** | `ClassLoader.getSystemClassLoader()` | Typically defines classes on the application classpath/module path, along with some JDK tools | The system loader can be customized via `java.system.class.loader`; do not always equate it with a specific implementation class name. |

**Visibility** and **defining loader** are two different concepts. When calling `platform.loadClass("java.lang.String")`, the platform loader can delegate to bootstrap. The resulting `Class<?>` is the `String` class already defined by bootstrap; it is not that platform just defined a new copy of `String`.

Similarly, when the application loader receives `loadClass("java.lang.String")`, it can delegate through platform to bootstrap. Which loader `ClassLoader.loadClass` was called on is not sufficient to conclude that the **defining loader** of the result is that loader.

### Initiating loader and defining loader

Suppose the application loader requests loading `java.lang.String`:

```text
Request to application loader
            │
            ▼
Application loader  ──delegates──> Platform loader
                                     │
                                     └──delegates──> Bootstrap loader
                                                         │
                                                         ▼
                                                   java.lang.String
                                                   is defined
```

- **Initiating loader:** the loader used by the JVM or application code to request loading a class; it may be recorded as having initiated loading that class.
- **Defining loader:** the loader that actually defines the class from binary data or a built-in mechanism. Runtime type identity depends on **binary name + defining loader**.
- **`loadClass` result:** the `Class<?>` object of the actual definition found; calling the method on a loader does not create a copy of the class in that loader.

The diagram depicts typical parent-first delegation. `ClassLoader` allows custom models; built-in loaders are module-aware and can therefore also delegate according to module relationships, not only along a linear parent path.

## 3. What exactly does the platform class loader guarantee?

The Java 17 Javadoc for `ClassLoader.getPlatformClassLoader()` specifies: **all platform classes are visible to the platform loader**. This group consists of Java SE platform APIs, their implementation classes, and appropriate JDK runtime classes, defined by the platform loader **or one of its ancestors**.

From this statement, we can deduce:

- `platform.loadClass("java.lang.String")` finds `String` on a normal JDK, but `String.class.getClassLoader()` is typically `null` (bootstrap).
- Other platform classes may be defined by the platform loader. The **per-module/per-class** assignment is a detail that can change between JDK releases or implementations; you should not hardcode a fixed table of class names in business logic.
- `ClassLoader.getPlatformClassLoader()` returns the **loader**, not the set of modules or all class names defined by the loader.
- There is no guarantee that every class on the **application classpath** is visible from the platform loader.
- A loader's ability to find a `Class<?>` does not replace JPMS **module readability**, `exports`, and runtime access-control rules.

A common misconception: "**the platform class loader is the loader that directly defines all classes in `java.*` packages**". This is false. For example, `java.lang.String` belongs to `java.base` and is usually defined by bootstrap. Conversely, a package name starting with `java.` also does not provide an official API to determine every defining loader; inspect the specific `Class` object.

### Is the parent relationship an absolute rule?

In common JDK 17 configurations, the platform loader is the parent of the application loader; the parent of the platform loader is represented as bootstrap (`null`). However:

- `ClassLoader.getSystemClassLoader()` can be replaced with a loader provided by system configuration via `-Djava.system.class.loader=...`; do not assume `getSystemClassLoader().getParent() == getPlatformClassLoader()` in all cases.
- **The platform loader may have to delegate to other loaders, including the application loader**, when handling upgraded/overridden modules and module dependencies. This is an exception documented in the `ClassLoader` Javadoc.
- In the module system, the **loader parent** relationship and the **module reads** relationship are two different graphs. `Module X reads Module Y` does not mean `X's class loader is a child of Y's class loader`.
- Even if a loader can see a class, permissions for **direct linking or reflection** remain constrained by the language and JPMS.

## 4. Practice A — observing platform, system, and bootstrap with Java 17+

Create a single standalone runnable program in the tree:

```text
platform-loader-lab/
└── src/
    └── demo/
        └── PlatformOverview.java
```

Contents of **`src/demo/PlatformOverview.java`**:

```java
package demo;

public class PlatformOverview {
    public static void main(String[] args) throws ClassNotFoundException {
        ClassLoader platform = ClassLoader.getPlatformClassLoader();
        ClassLoader system = ClassLoader.getSystemClassLoader();

        Class<?> stringFromPlatform =
                platform.loadClass("java.lang.String");

        System.out.println("platform exists: " + (platform != null));
        System.out.println("platform != system: " + (platform != system));
        System.out.println("String reachable: " +
                (stringFromPlatform == String.class));
        System.out.println("String bootstrap: " +
                (String.class.getClassLoader() == null));
        System.out.println("app loaded by system: " +
                (PlatformOverview.class.getClassLoader() == system));
    }
}
```

In the `platform-loader-lab` directory, with a **common JDK 17+ and the default launcher**:

```sh
javac --release 17 -d out src/demo/PlatformOverview.java
java -cp out demo.PlatformOverview
```

**Stdout in the default OpenJDK/HotSpot 17+ configuration**:

```text
platform exists: true
platform != system: true
String reachable: true
String bootstrap: true
app loaded by system: true
```

Line-by-line explanation:

1. `ClassLoader.getPlatformClassLoader()` always returns a valid platform loader for JDKs that support the API.
2. Platform and system are **two distinct loaders**. Do not use internal implementation class names to check this.
3. `platform.loadClass("java.lang.String")` can see the class defined by bootstrap; the result has the same identity as `String.class`.
4. `String.class.getClassLoader() == null` is how Java typically represents that `String` is defined by bootstrap on the corresponding JDK.
5. `PlatformOverview` resides in `out`, placed on the application classpath by `-cp out`; with the launcher/default built-in system loader, the program's defining loader equals the system loader.

If the application uses a custom system loader, an agent, another module layer, or a specialized JVM implementation, some observed details about the defining loader may differ; read the code and stdout scope as **default OpenJDK/HotSpot 17+**, not an independent guarantee across every JVM.

### Do not confuse the display name with the API contract

On many modern OpenJDK builds:

```java
System.out.println(ClassLoader.getPlatformClassLoader().getName());
System.out.println(ClassLoader.getSystemClassLoader().getName());
```

typically prints:

```text
platform
app
```

This is an **illustrative snippet to insert into `main` if you want to observe it**, not a standalone program. The names `platform` and `app` are implementation notes in the built-in loaders Javadoc; application analysis should rely on the API and object identity, not on `loader.getClass().getName()` or the display name string.

## 5. Why did Java 9 change how platform classes are loaded?

Before Java 9, the extension mechanism allowed placing JARs in a JRE directory so that the extension class loader could see them without the application declaring them in `-cp`. This led to the habit of treating bootstrap + extension as a region of classes outside the application classpath.

From Java 9 onward:

- The JDK uses a runtime **module image** instead of the traditional distribution model based on `rt.jar`. In common JDK installations, many platform classes are provided via the module system and can be observed via `jrt:/...` URLs; you should not try to find every class by opening `rt.jar`.
- The **platform class loader** is provided via a stable API, serving access to platform classes in a way compatible with the module model.
- The `lib/ext`/`java.ext.dirs` mechanism for deploying extensions was removed. Third-party libraries must be configured via the **classpath**, **module path**, or an explicitly designed loading mechanism/module layer.
- Legacy code assuming `getSystemClassLoader() instanceof URLClassLoader` or that `new URLClassLoader(urls, null)` sees all Java SE classes needs to be revisited.

You should not describe the platform loader as a "new extension JAR directory". The word "platform" here refers to **the loader's role in the Java platform**, not a file search path.

## 6. Platform loader and JPMS: three layers to separate

There are three distinct questions when an application runs with modules:

1. **Is the module resolved into the boot layer or an appropriate layer?** A module being present in the image/path does not mean every module is selected into the graph.
2. **Which class loader is the module defined to?** Bootstrap/platform/application can participate; the mapping depends on the runtime.
3. **Is another class/module allowed to use the API?** This involves `requires`/readability, `exports`, and `opens`, not just whether the loader can find the bytes.

For example, a module `app.module` declares:

```java
module app.module {
    requires java.sql;
}
```

This is an **illustrative `module-info.java` file**, not runnable on its own. `requires java.sql` establishes a readability relationship so that code in module `app.module` can use the exported API of `java.sql`. It does not mean classes in `java.sql` must be defined by the application loader, nor does it mean the platform loader will load all third-party database drivers.

Expanding the perspective:

| Term | Question answered | Inference to avoid |
| --- | --- | --- |
| Module resolution | Which modules participate in the runtime configuration? | "Present on the module path" = "already resolved". |
| Readability | Does the caller module read the target module? | Loader can load it = compiler/runtime definitely allows reading. |
| Exports | Does the package allow external modules to access public types? | Public class = always usable from every module. |
| Opens | Is the package open for appropriate deep reflection? | Class loading succeeded = `setAccessible` always succeeds. |
| Defining loader | Which loader creates runtime class identity? | Module name or package name automatically determines the loader. |
| Parent delegation | When a loader does not handle it, does it delegate to another loader? | This graph is identical to `requires`. |

### Does the platform loader only see modules defined by itself?

No. The Javadoc specifies that the platform loader **sees platform classes**, including classes defined by an ancestor (bootstrap). Furthermore, in certain situations where **upgraded modules** need to reference modules defined by another loader, the platform loader can delegate outside the parent chain (even to the application loader). Therefore, the bootstrap ← platform ← app diagram remains very useful for learning, but it is not an absolute module lookup model.

## 7. Practice B — using the platform loader as the parent of a custom loader

A concrete reason to obtain the platform loader is **to use it as the parent of an application-created class loader**. When a plugin only needs platform classes and wants to avoid accidentally seeing every class on the application classpath via its parent, the platform loader can be chosen.

Create files:

```text
platform-parent-lab/
└── src/
    └── demo/
        ├── AppOnly.java
        └── ParentVisibility.java
```

**`src/demo/AppOnly.java`**:

```java
package demo;

public class AppOnly {
    public static String value() {
        return "in app classpath";
    }
}
```

**`src/demo/ParentVisibility.java`**:

```java
package demo;

public class ParentVisibility {
    public static void main(String[] args) throws Exception {
        ClassLoader platform = ClassLoader.getPlatformClassLoader();

        ClassLoader plugin = new ClassLoader(platform) { };

        Class<?> core = plugin.loadClass("java.lang.String");
        System.out.println("platform API visible: " +
                (core == String.class));

        try {
            plugin.loadClass("demo.AppOnly");
            System.out.println("app class visible: true");
        } catch (ClassNotFoundException e) {
            System.out.println("app class visible: false");
        }

        Class<?> app = ClassLoader.getSystemClassLoader()
                .loadClass("demo.AppOnly");
        System.out.println("system sees app: " +
                (app == AppOnly.class));
    }
}
```

Compile and run with JDK 17+ from the `platform-parent-lab` directory:

```sh
javac --release 17 -d out src/demo/AppOnly.java src/demo/ParentVisibility.java
java -cp out demo.ParentVisibility
```

**Stdout on a default OpenJDK/HotSpot JDK with the classpath above:**

```text
platform API visible: true
app class visible: false
system sees app: true
```

**Why?**

- `new ClassLoader(platform) { }` creates an anonymous subclass using `ClassLoader`'s **default parent-first** behavior, without overriding `findClass` and without custom file/JAR reading logic.
- For `java.lang.String`, the new loader delegates up to platform/bootstrap and finds the class.
- For `demo.AppOnly` on the **unnamed application classpath**, the platform loader does not use the application classpath as a lookup source by default; the new loader does not read files on its own either. The result is `ClassNotFoundException`.
- The system loader can find `demo.AppOnly` from `-cp out`, thus returning the same `Class` as `AppOnly.class`.

**Scope of the example:** This is a loader with no way to load plugins itself, used to illustrate the **parent visibility boundary**. It is **not yet a complete plugin loader**. A real-world plugin loader must have a bytecode source, valid package/module definitions, dependency management, and an appropriate API-sharing mechanism.

### Why not always choose `null` as the parent?

The `ClassLoader(null)` constructor uses bootstrap as the parent according to the standard `ClassLoader` mechanism. However, since Java 9, **it is not guaranteed that all platform classes are visible through bootstrap**. A plugin needing a Java SE API from a module defined by the platform loader can fail when the parent is only bootstrap.

Choosing `ClassLoader.getPlatformClassLoader()` as the parent gives the child loader **full visibility of platform classes** per the Javadoc. If the plugin also needs to use application classes such as `com.myapp.spi.Plugin` defined by the application loader, using platform as the parent may not be suitable: you need to explicitly design a shared class loader for the SPI or an appropriate module layer/delegation mechanism. Do not arbitrarily change the parent expecting only a performance change.

### When would you choose the system loader as the parent instead?

If the plugin needs to access many APIs of the running application itself, the system loader (or a loader containing shared APIs) may be more suitable. On the other hand, if the plugin has dependencies with the same names as the application's, parent-first can cause the application's classes to take precedence, thereby causing version conflicts.

There is no single parent suitable for every framework. The selection criteria are **which classes need shared identity** between core and plugin, which classes need isolation, and which modules need to be visible.

## 8. Practice C — observing module and defining loader without relying on internal names

Create a standalone file `src/demo/ModuleView.java`:

```java
package demo;

public class ModuleView {
    public static void main(String[] args) {
        Class<?> platformClass = java.sql.Driver.class;

        System.out.println("module: " +
                platformClass.getModule().getName());

        ClassLoader loader = platformClass.getClassLoader();
        ClassLoader platform = ClassLoader.getPlatformClassLoader();
        ClassLoader system = ClassLoader.getSystemClassLoader();

        String owner = loader == null ? "bootstrap"
                : loader == platform ? "platform"
                : loader == system ? "system" : "other";

        System.out.println("owner: " + owner);
        System.out.println("visible from platform: " +
                canLoad(platform, platformClass.getName(), platformClass));
    }

    private static boolean canLoad(ClassLoader loader,
                                   String name,
                                   Class<?> expected) {
        try {
            return loader.loadClass(name) == expected;
        } catch (ClassNotFoundException e) {
            return false;
        }
    }
}
```

Compile and run from the practice directory using a full JDK 17+ supporting the `java.sql` module:

```sh
javac --release 17 -d out src/demo/ModuleView.java
java -cp out demo.ModuleView
```

The output is designed to **distinguish stable information from JVM-dependent information**:

```text
module: java.sql
owner: <bootstrap or platform, depending on JDK assignment>
visible from platform: true
```

The `owner` line above is an **illustrative result template**; the notation inside `<...>` is not literal stdout. Run the program to see the actual loader; on common OpenJDK builds, `java.sql` is usually defined by the platform loader, but this lesson does not bind a specific module to a defining loader as a stable contract. The `java.sql` module line and visibility through platform are observed/guaranteed properties when running on a full JDK as described. With a runtime image created via `jlink` or a module-restricted configuration, missing the `java.sql` module may cause the program not to compile/run properly; ensure that module is present.

The value of the program: it queries **the `Class<?>` object itself** for its module and loader, then uses `platform.loadClass` to test visibility. Do not compare JVM internal loader class names, because there is no binary compatibility guarantee when a JDK vendor changes implementations.

## 9. Distinguishing the platform loader from the Thread Context Class Loader (TCCL)

The platform loader is **a built-in loader** identified via the static API `ClassLoader.getPlatformClassLoader()`. Meanwhile, the **Thread Context Class Loader** is a mutable per-thread attribute:

```java
ClassLoader context = Thread.currentThread().getContextClassLoader();
```

This is an **illustrative** snippet that can be placed in `main`. On a common JVM launcher, the main thread's initial context loader is typically the system loader. However, a framework may change it to perform discovery/plugin loading.

You should not infer that:

```text
Thread.currentThread().getContextClassLoader()
    == ClassLoader.getPlatformClassLoader()
```

is the default, or that every `Class.forName` call automatically uses the context loader. There are important differences:

- `Class.forName(String)` uses the calling class's loading context per the Java API, and **requests initialization**.
- `Class.forName(String, boolean, ClassLoader)` uses the directly passed loader, and allows opting out of initialization.
- `ServiceLoader.load(Class<S>)` typically uses the **current thread's context class loader** to locate providers; `ServiceLoader.load(Class<S>, ClassLoader)` allows passing a loader.
- `ClassLoader.getPlatformClassLoader()` only provides the **platform loader object**; it does not modify the thread's TCCL.

JDBC example: `java.sql.Driver` is a **platform API**; the driver placed on the classpath/module path by the application provider is **third-party code**. Finding `java.sql.Driver` through the platform loader does not guarantee that the platform loader sees all driver implementation classes. If a framework searches for drivers/providers via TCCL or ServiceLoader, the loader used for discovery may be the system/plugin loader. Simply changing the TCCL can change the set of providers found, even though the platform loader does not change.

## 10. Key differences when choosing a custom loader's parent

The decision can be illustrated through the following table:

| Goal | Parent worth considering | Risks to control |
| --- | --- | --- |
| Plugin needs Java platform APIs and should be separated from the application | `ClassLoader.getPlatformClassLoader()` | Does not see application SPI/SDK unless an explicit sharing channel is created. |
| Plugin needs application interfaces/core libraries | System loader or a loader containing shared APIs | Parent-first may cause the plugin to use the dependency version from core. |
| Isolate a custom set of classes at a low level | Dedicated loader with a specific delegation plan | Type identity, package sealing, module access, resource lookup, TCCL. |
| Legacy loader that used parent `null` for all Java classes | Switch to platform parent if the full Java SE/JDK API is truly needed | Keeping `null` may miss platform-defined classes after Java 9. |

**You cannot simply swap the platform/system parent to create a security sandbox.** Class loaders primarily handle class definition and namespaces. Security boundaries, file/network access permissions, and execution of untrusted code require independent mechanisms; name isolation via class loaders does not by itself make code safe.

**Do not use the platform loader as an application library repository.** `ClassLoader.getPlatformClassLoader()` provides no API to arbitrarily add JARs to the platform path. If an application wants to hot-load JARs, design a dedicated loader or module layer with an appropriate lifecycle.

### Class identity must be checked

The JVM identifies a runtime class/interface by **(binary name, defining loader)**. If `com.example.spi.Plugin` appears in two JARs and is defined separately by two loaders, the two classes can have the same `getName()` yet **not be assignable to each other**. This causes `ClassCastException` or `LinkageError` depending on context.

A plugin using the platform parent that loads its own copy of the application's SPI interface may fail to cast to the SPI interface defined by the app loader. Place the **shared SPI** under a common loader in a structure that both sides actually use, or introduce a data-transfer layer across the boundary. Do not take identical `getName()` values as proof of identical identity.

## 11. Observing real applications with JDK tools

### 11.1. Seeing which module/JAR a class comes from

With example A:

```sh
java -Xlog:class+load=info -cp out demo.PlatformOverview
```

This is **Unified Logging** on supporting JVMs, notably HotSpot. The log has many lines and its order depends on runtime behavior, so there is no fixed stdout for this command. Load lines typically include the class name and source such as `jrt:/java.base` or a classpath entry. **The source of class bytes does not by itself reveal the entire parent relationship**; combine it with `getClassLoader()` to identify the defining loader.

### 11.2. Checking modules present in the JDK

```sh
java --list-modules
java --describe-module java.sql
```

Use `java --list-modules` to see which modules exist in the current runtime image; `java --describe-module` gives module information. The output list is configuration data and **does not directly state which loader defines each class**. If you are using `jlink` to build a custom image, check that the module is present before running example C.

### 11.3. Printing the parent relationship in the running environment

You can add to `main` of example A:

```java
System.out.println(
        ClassLoader.getSystemClassLoader().getParent()
                == ClassLoader.getPlatformClassLoader());
System.out.println(
        ClassLoader.getPlatformClassLoader().getParent() == null);
```

In default OpenJDK/HotSpot, this typically prints two `true` lines. This is an **additional insertion snippet**, not a standalone Java file. With a custom system loader or special configuration, do not rely on assuming the parent relationship always matches the example.

## 12. Common failure scenarios and how to diagnose them

| Symptom | Possible cause | Inspection/fix |
| --- | --- | --- |
| `ClassNotFoundException` when using a loader with parent `null` | The desired Java SE class is defined by platform rather than bootstrap; or another dependency is not visible | Check `getPlatformClassLoader()`; verify the module is present in the runtime; consider the platform parent. |
| `ClassNotFoundException` for an app class when using the platform parent | The platform loader does not search arbitrary classes on the unnamed application classpath | Design an appropriate parent or add a dedicated class source for the child loader; do not force app JARs into platform. |
| `ClassCastException` despite identical binary name | Two independent defining loaders defined the same API | Inspect `getClassLoader()` of both `Class` objects; reorganize the shared SPI and delegation. |
| `LinkageError` with loading constraint | Descriptors across loaders require the same identity but receive incompatible classes | Inspect the full stacktrace, defining loaders, API versions, and module graph. |
| `IllegalAccessError` / `InaccessibleObjectException` | Runtime access/module exports/opens constraints | Check `requires`, `exports`, `opens`, and how reflection is used. |
| Legacy `java.ext.dirs` no longer works | JDK 8's extension mechanism was removed | Move dependencies to `-cp`, `--module-path`, or a dedicated loader. |
| `ClassCastException` when casting the system loader to `URLClassLoader` | Application depends on the JDK 8 implementation | Remove the cast; use an appropriate loader API or design custom loading. |
| ServiceLoader does not find driver/provider | TCCL, module `provides/uses`, classpath, or layer differs from expectation | Check the discovery loader, module graph, and provider configuration. |
| Module is on the path but class is still inaccessible | Module is not resolved or lacks readability/exports permissions | Check `--add-modules`/root modules and descriptors; do not inspect only the class loader. |

**Step-by-step debugging approach:**

1. Identify the **requested class name**, which loader initiated the load request, and which API raised the error.
2. Print the **defining loader** of the `Class` (if already obtained) using `getClassLoader()`; `null` represents bootstrap in this context.
3. Check the **actual classpath/module path at runtime**, including custom runtime images and the module graph.
4. Verify the **custom loader's parent**: `null`, platform, system, or a loader providing shared APIs?
5. If the class is found yet still fails, check **resolution**, binary API, access rules, module exports/opens, and TCCL.
6. Reproduce from a minimal run workflow with a known JDK, avoiding guesses based solely on JAR filenames.

### Distinguishing commonly confused calls

```java
ClassLoader platform = ClassLoader.getPlatformClassLoader();
Class<?> clazz = platform.loadClass("java.lang.String");
Class<?> loaded = Class.forName("java.lang.String", false, platform);
```

This is an illustrative snippet that can be placed inside a method declaring `throws ClassNotFoundException`. Both APIs allow obtaining a class by binary name and loader; `Class.forName` has the `initialize=false` parameter so as not to require initialization. `loadClass(String)` usually does not require initialization either. Retrieving a `Class<?>` object **does not mean an instance has been created**.

## 13. Misconceptions to avoid

- **"The platform class loader is the bootstrap loader."** No: platform is a distinct loader object, whereas bootstrap is typically represented by `null`.
- **"All `java.*` classes are defined by platform."** No: some classes are defined by bootstrap and remain visible from platform.
- **"The platform loader loads all application libraries."** No: the normal application classpath is handled by the application/system loader.
- **"The platform loader is the exact same Extension loader with the `lib/ext` directory."** No: the old extension directory mechanism was removed in Java 9.
- **"The loader parent hierarchy always matches the module dependency graph."** No: JPMS readability, module definitions, and class loaders are different relationships.
- **"Platform can only query bootstrap and never delegates in reverse."** No: the Javadoc notes cases where upgraded modules need to see classes in the application loader.
- **"`getPlatformClassLoader()` replaces TCCL."** No: TCCL is a mutable thread attribute used by certain discovery APIs.
- **"You can use the platform parent for complete security isolation of a plugin."** No: class loaders primarily separate namespaces/visibility; security requires other mechanisms.
- **"Classes with the same name are the same type."** No: identity also depends on the defining loader.
- **"Every platform loader is a `URLClassLoader` so URLs can be added to it."** No: do not rely on internal implementations.

## 14. Self-check questions

**1. In which Java version was the platform loader introduced?** Since Java 9, via `ClassLoader.getPlatformClassLoader()`.

**2. Why does the platform loader see `java.lang.String` even though `String`'s defining loader is bootstrap?** Because platform can delegate up to bootstrap; visibility differs from defining identity.

**3. Why can a `null` parent cause errors after upgrading from Java 8 to Java 17?** Because Java 9+ does not guarantee that all platform classes are defined by bootstrap; some reside in the platform loader.

**4. Does choosing platform as the parent of a custom plugin loader automatically load classes on the application classpath?** No. The child loader must have its own source to find classes, or a delegation relationship must be designed to see application classes.

**5. Are two classes with the same name loaded from two different custom loaders always equivalent?** No. The defining loader is part of runtime type identity.

**6. If code running in module `app.module` sees the `java.sql` API, does that mean the app loader defines all `java.sql` classes?** No. Module readability and loader mapping are two separate concerns.

**7. Why should you not cast the system loader to `URLClassLoader`?** Because the system loader's implementation is not specified to be a `URLClassLoader`, and JDKs from Java 9 onward changed it.

**8. When should TCCL be used instead of the platform loader?** When an API/framework needs to discover providers or resources in the context of a thread/plugin; this serves a different purpose from using the platform loader as a parent.

## 15. Official references and further reading

- [Java SE 17 `ClassLoader` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): the **Run-time Built-in Class Loaders** section, `getPlatformClassLoader()`, `getSystemClassLoader()`, `getParent()`, and delegation.
- [Java SE 17 `Class` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getClassLoader()`, `getModule()`, and runtime class metadata.
- [Java SE 17 `Module` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): module identity, readability, and module relationships.
- [JDK Migration Guide — New Class Loader Implementations](https://docs.oracle.com/en/java/javase/15/migrate/): migration from the extension mechanism to the platform class loader and warnings about the `null` parent.
- [JEP 261 — Module System](https://openjdk.org/jeps/261): context on the module path, runtime image, and built-in loaders since Java 9.

**Key takeaway:** the platform class loader is **a stable access point to platform classes** and a useful parent choice for custom loaders on modern JDKs. When analyzing a class, keep separate **which module it belongs to**, **which loader defines it**, **which loaders can see it**, and **whether the caller has permission to access it**. These four questions help avoid most confusion when migrating Java 8 applications to 17+ or designing a plugin system.
