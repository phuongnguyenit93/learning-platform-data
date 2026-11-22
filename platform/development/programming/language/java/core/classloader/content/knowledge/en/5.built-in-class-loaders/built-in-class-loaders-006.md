# ClassLoader.getPlatformClassLoader and getSystemClassLoader

## 1. What Are These Two APIs Used For?

When learning how the JVM loads classes, we often encounter two `static` methods of `java.lang.ClassLoader`:

~~~java
ClassLoader platform = ClassLoader.getPlatformClassLoader();
ClassLoader system = ClassLoader.getSystemClassLoader();
~~~

Both **return a ClassLoader object**, yet they serve different roles:

- `getPlatformClassLoader()` returns the **platform class loader**, the built-in loader used for classes of the Java platform and the JDK. This method was introduced in Java 9.
- `getSystemClassLoader()` returns the **system class loader** (commonly called the **application class loader**), the default loader typically used to launch the application and load classes located on the application classpath or application module path.

No parameters: these methods do not accept a class name, do not directly load a specific class, and do not create a new loader each time they are called. They provide a **reference to a loader already set up by the JVM**. Once you have the loader, you can call `loadClass(...)`, `getResource(...)`, or use the loader as the parent for a custom loader.

In a typical JVM from Java 9 onward, the delegation diagram is:

~~~text
                      ┌─────────────────────────────┐
                      │ Bootstrap loader            │
                      │ JVM core / java.base        │
                      │ Represented as null in Java │
                      └──────────────▲──────────────┘
                                     │ parent
                      ┌──────────────┴──────────────┐
                      │ Platform class loader       │
                      │ Java SE APIs / JDK modules  │
                      └──────────────▲──────────────┘
                                     │ parent
                      ┌──────────────┴──────────────┐
                      │ System / Application        │
                      │ class loader                │
                      │ Application code            │
                      └──────────────▲──────────────┘
                                     │ parent
                      ┌──────────────┴──────────────┐
                      │ ClassLoader created by      │
                      │ the application (if any)    │
                      └─────────────────────────────┘
~~~

The arrows indicate the **parent/delegation relationship**; they do not mean that every class is loaded into memory in top-down order. Typically, a child loader checks whether a class has already been loaded, tries delegating to its parent, and only searches its own bytecode if the parent cannot find it.

The diagram above describes the **default built-in loaders**. The JVM and application runner tools may use their own loaders; the `java.system.class.loader` option can also replace the system loader object. For named modules, class visibility involves additional module rules and certain special delegation paths; a simple parent diagram is not enough to describe every case.

## 2. Distinguishing Bootstrap, Platform, and System

| Criterion | Bootstrap loader | Platform loader | System loader |
|---|---|---|---|
| How to obtain | No API returns a regular `ClassLoader` object; typically represented by `null` | `ClassLoader.getPlatformClassLoader()` | `ClassLoader.getSystemClassLoader()` |
| Primary role | Loads core platform classes, such as `java.lang.String` in JDK 17 | Loads platform classes and JDK modules assigned to the platform loader | Typically loads application classes from the classpath/application module path |
| Default parent relationship | No parent | Bootstrap | Platform |
| Result of `Class.getClassLoader()` | `null` for classes defined by bootstrap | Platform loader object for classes defined by it | System loader object for classes defined by it |
| Is it a new loader on each call? | Not applicable | No | No |
| Can serve as parent for a custom loader? | Can pass `null` to specify bootstrap (with class visibility limitations) | Yes, suitable if only platform APIs are needed | Yes, suitable if a plugin needs to see application APIs |

**Very important point:** The `ClassLoader` on which we call `loadClass` is **not necessarily** the ClassLoader that *defined* the returned class.

For example, the system loader can execute:

~~~java
Class<?> type = ClassLoader.getSystemClassLoader()
        .loadClass("java.lang.String");
~~~

Even though the request originated from the system loader, `String.class.getClassLoader() == null` is still `true` on a standard Java 17 JVM: the bootstrap loader defined `String`, and the system loader merely forwarded the request up to its parent via the delegation mechanism.

Similarly, a class defined by the platform loader can be found by the system through the system loader. Therefore, do not use the phrase “a class requested via loader X” in place of “a class defined by loader X”.

## 3. `getPlatformClassLoader()`

### 3.1. Functionality and Return Value

~~~java
ClassLoader platform = ClassLoader.getPlatformClassLoader();
~~~

This `public static` method has existed since **Java 9** and returns the platform class loader. According to the Java 17 API, **platform classes** are visible through this loader. These include the Java SE APIs, their implementation classes, and JDK-specific runtime classes managed by the platform loader or its ancestors.

Typically on JDK 17:

- `platform != null`.
- `platform.getParent() == null`, because its parent is the bootstrap loader, which is represented by `null`.
- `platform != ClassLoader.getSystemClassLoader()`.

Note that **not** every class in `java.*` packages is defined by the same specific loader; which loader manages which module is part of the runtime mechanism and module configuration. You should not assume that “if a package name starts with `java.`, then `getClassLoader() == null`”.

### 3.2. Why Use the Platform Loader as a Parent?

Suppose you want to load an extension JAR without **automatically granting visibility to the host's entire classpath**. You can create a child loader whose parent is the platform loader:

~~~java
ClassLoader parent = ClassLoader.getPlatformClassLoader();

// Illustrative code, not a complete program:
// URL[] urls = ... URLs to custom JARs ...
// try (URLClassLoader pluginLoader = new URLClassLoader(urls, parent)) {
//     ...
// }
~~~

In that case, the plugin loader can delegate finding platform classes to the platform loader. It does **not automatically see** application classes defined by the system loader, because the system loader is not an ancestor of the platform loader.

If the plugin needs to implement a custom application interface such as `com.example.api.Plugin`, the parent should be the **loader that defined that interface** or a loader capable of delegating to that class, for example:

~~~java
ClassLoader sharedApiParent = Plugin.class.getClassLoader();
~~~

The snippet above only makes sense in a project that has already defined `Plugin`; it is **illustrative code**, not a standalone runnable Java file. Using the API contract's loader as the parent ensures the host and plugin share the exact **same runtime type**, preventing two loaders from each defining identically named API classes and causing `ClassCastException` or `ServiceConfigurationError`.

**Do not confuse visibility with security:** Setting the platform loader as the parent can restrict which application classes a plugin sees through the delegation mechanism; this **does not create a reliable sandbox** for plugin code. A plugin running in the same JVM can still execute code with the process's privileges.

### 3.3. Notes on JPMS

Some upgraded modules have readability relationships with other modules; therefore, the platform loader implementation may delegate to a **non-ancestor** loader in certain module scenarios. This point is noted in the Javadoc itself. You should not write an absolute rule stating that the platform loader “never delegates to the system loader,” nor rely solely on the `getParent()` relationship to determine complete module visibility.

## 4. `getSystemClassLoader()`

### 4.1. Functionality and Return Value

~~~java
ClassLoader system = ClassLoader.getSystemClassLoader();
~~~

This method returns the system class loader, typically used to load the application's startup class. It is also the **default parent** of a `ClassLoader` instance created using the no-parent constructor:

~~~java
class MyLoader extends ClassLoader {
    // Implicit super(): the default parent is the system class loader.
}
~~~

For Java 17 running a standard classpath application:

- The loader that defines the class containing the `main` method is typically the system/application loader.
- `system.getParent() == ClassLoader.getPlatformClassLoader()` is typically true for the default built-in loaders.
- `Thread.currentThread().getContextClassLoader() == system` is typically true on the `main` thread created by the Java launcher.

The three observations above describe the **defaults**, not a guarantee for every application server, IDE, agent, plugin host, custom Java container, or thread where the application explicitly sets its own context loader.

### 4.2. Where Does the System Loader Find Classes?

In an application launched with a classpath:

~~~bash
java -cp "build/classes:lib/example.jar" com.example.Main
~~~

The system loader typically looks for application classes in the directories/JARs on the application classpath. On Windows, the classpath separator is `;`; on Linux/macOS, it is usually `:`.

When running a JPMS application with `--module-path` and `--module`, classes of application modules are typically managed by the corresponding loader system. However, you cannot simply assume that all modules on the module path are defined by the **same** ClassLoader: module layer configurations and loader rules still matter.

Unlike Java 8, Java 9+ does not guarantee that the system loader is a `java.net.URLClassLoader`. Code like:

~~~java
// Unsafe on modern JDKs:
// URLClassLoader urls = (URLClassLoader) ClassLoader.getSystemClassLoader();
~~~

can cause a `ClassCastException`. To inspect the classpath, check `System.getProperty("java.class.path")` (if appropriate) or the build/runtime API in use; to add URLs for a plugin, create a separate `URLClassLoader`. Do not rely on internal implementation classes such as `jdk.internal.loader.ClassLoaders$AppClassLoader`.

### 4.3. Custom System Loader

The JVM allows setting a system property **right at startup**:

~~~bash
java -Djava.system.class.loader=com.example.CustomLoader -cp ... com.example.Main
~~~

The class name here is only a configuration example; the command **cannot run unless you have written and provided** `com.example.CustomLoader` on the appropriate classpath. A custom system loader must have a **public constructor taking exactly one parameter of type `ClassLoader`**. The JVM loads the configured class using the default system loader and then passes the default system loader as the parent when instantiating the custom instance.

Consequences:

1. `getSystemClassLoader()` may return the **custom loader**, rather than the original built-in loader.
2. `getSystemClassLoader().getParent()` may be the default system loader instead of the platform loader directly.
3. Inside the custom loader's constructor, **do not call back into `getSystemClassLoader()`**: an initialization cycle can cause an `IllegalStateException`.
4. If the configured class cannot be loaded, has an unsuitable constructor, or its constructor fails, the JVM may report an `Error` while setting up the system loader.
5. The runtime only evaluates this property when initializing the system loader. Changing it later via `System.setProperty(...)` is not a way to replace the loader of a running JVM.

This is a specialized configuration. Normal applications **do not need** to replace the system loader just to load a plugin or a dynamic JAR.

## 5. Java 17+ Program Comparing the Two Loaders Directly

Create **a single file** `LoaderComparison.java` in any directory:

~~~java
public final class LoaderComparison {
    private LoaderComparison() {
    }

    static final class AppType {
    }

    private static String definedBy(
            Class<?> type, ClassLoader platform, ClassLoader system) {
        ClassLoader loader = type.getClassLoader();
        if (loader == null) {
            return "bootstrap";
        }
        if (loader == platform) {
            return "platform";
        }
        if (loader == system) {
            return "system";
        }
        return "other";
    }

    public static void main(String[] args) throws ClassNotFoundException {
        ClassLoader platform = ClassLoader.getPlatformClassLoader();
        ClassLoader system = ClassLoader.getSystemClassLoader();

        System.out.println("Platform exists: " + (platform != null));
        System.out.println("System differs from platform: " + (system != platform));

        System.out.println("Platform parent is bootstrap: "
                + (platform.getParent() == null));
        System.out.println("System parent is platform: "
                + (system.getParent() == platform));

        System.out.println("String defined by: "
                + definedBy(String.class, platform, system));
        System.out.println("AppType defined by: "
                + definedBy(AppType.class, platform, system));

        Class<?> delegated = system.loadClass("java.lang.String");
        System.out.println("Delegated String identical: "
                + (delegated == String.class));

        boolean platformCanFindApp;
        try {
            platform.loadClass("LoaderComparison$AppType");
            platformCanFindApp = true;
        } catch (ClassNotFoundException ex) {
            platformCanFindApp = false;
        }
        System.out.println("Platform finds application class: "
                + platformCanFindApp);

        System.out.println("Main context loader is system: "
                + (Thread.currentThread().getContextClassLoader() == system));
    }
}
~~~

**Compile and run** with JDK 17+ from the directory containing the file, in a normal Java session, **without** `-Djava.system.class.loader`, `--patch-module`, or tools that modify loaders:

~~~bash
javac -encoding UTF-8 LoaderComparison.java
java -cp . LoaderComparison
~~~

**Expected stdout on standard OpenJDK/Oracle JDK 17 under the assumptions above:**

~~~text
Platform exists: true
System differs from platform: true
Platform parent is bootstrap: true
System parent is platform: true
String defined by: bootstrap
AppType defined by: system
Delegated String identical: true
Platform finds application class: false
Main context loader is system: true
~~~

The `-cp .` option places the application code on the application classpath. If the runtime environment has configured a custom loader, module patching, or a different context ClassLoader, some comparisons regarding the parent, defining loader, or context loader may differ. In that case, the output serves as useful diagnostic information rather than indicating the JVM is “wrong”.

### Explanation of Each Check

**`platform != null` and `system != platform`.** The platform loader is a distinct loader object, separate from the system loader in the built-in loader hierarchy. It is the bootstrap loader that is typically represented by `null`.

**`getParent()`.** The platform loader's parent is bootstrap in the default configuration, so `platform.getParent() == null`. The parent of the built-in system loader is the platform loader. If the system loader is customized, direct parent comparisons need to be reconsidered.

**`String.class.getClassLoader()`.** `java.lang.String` is defined by bootstrap, so `definedBy` returns `bootstrap`. Calling `system.loadClass("java.lang.String")` still returns the exact same `Class<?>` object thanks to delegation; the system loader **does not redefine** `String`.

**`AppType.class.getClassLoader()`.** `AppType` is a nested class in the application source, loaded by the system loader during a standard classpath run; the result is `system`. This nested class is not automatically treated as a platform class by the JVM just because it resides in the same file.

**`platform.loadClass("LoaderComparison$AppType")`.** The binary name of a nested class uses `$`. The regular platform loader does not have the program's application classpath and does not find this application class; therefore `ClassNotFoundException` is caught and `false` is printed.

**`Thread.currentThread().getContextClassLoader()`.** The Java launcher typically assigns the system loader as the context loader of the `main` thread. This is **per-thread state** that can be modified by frameworks and application code, not a method for retrieving the defining loader of `LoaderComparison`.

## 6. Three Different Ways to Obtain a ClassLoader and When to Use Them

The following APIs are easily confused, yet the questions they answer are different:

~~~java
ClassLoader platform = ClassLoader.getPlatformClassLoader();

ClassLoader system = ClassLoader.getSystemClassLoader();

ClassLoader defining = LoaderComparison.class.getClassLoader();

ClassLoader context = Thread.currentThread().getContextClassLoader();
~~~

| How to obtain | Primary meaning | When appropriate |
|---|---|---|
| `getPlatformClassLoader()` | Built-in platform loader | As a parent when a child loader only needs to share platform APIs |
| `getSystemClassLoader()` | System/application loader selected by the JVM | Finding application classes/resources in a standard runtime configuration; default parent |
| `SomeApi.class.getClassLoader()` | The loader that **defined** the exact runtime type `SomeApi` | Host/plugin designs that need to share interfaces and DTOs |
| `Thread.currentThread().getContextClassLoader()` | The loader held by the thread for contextual lookup by frameworks | `ServiceLoader` and class/resource discovery mechanisms of certain libraries |

**Example with `ServiceLoader`:** `ServiceLoader.load(MyService.class)` typically looks up providers via the thread context loader. In contrast, `ServiceLoader.load(MyService.class, explicitLoader)` accepts the loader passed in by the application. Consequently, a provider in a plugin loader may not be found if the thread context loader remains the system loader, which cannot see the plugin JAR.

If you temporarily change the context loader, always restore it using `finally`:

~~~java
// Illustrative code: pluginLoader must be declared in an actual program.
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();
try {
    thread.setContextClassLoader(pluginLoader);
    // Call library APIs that need to discover classes using the context loader.
} finally {
    thread.setContextClassLoader(previous);
}
~~~

Do not permanently change the context loader for the entire application without understanding its impact on thread pools or other frameworks.

## 7. Why “Class Loading” Is Not the Same as “Class Initialization”

The two methods `getPlatformClassLoader()` and `getSystemClassLoader()` only retrieve loader references. When calling `loadClass("com.example.Widget")`, the loader typically requests loading the class (and may resolve it via another API path), yet **does not automatically execute that class's static initializer**.

Distinguish between them:

~~~java
Class<?> a = ClassLoader.getSystemClassLoader()
        .loadClass("com.example.Widget");

// Illustrative code: if Widget exists and initialization needs to be triggered:
Class<?> b = Class.forName(
        "com.example.Widget",
        true,
        ClassLoader.getSystemClassLoader()
);
~~~

In the three-parameter overload of `Class.forName`, `initialize = true` requests initialization if the class has not yet been initialized. You can use `false` when you want to locate a class without actively triggering initialization.

Each runtime type is identified by **binary name + defining loader**, so two loaders each defining classes with the same FQCN can create two incompatible types. `loadClass` may return a class from a parent; you **cannot** determine where a class was defined solely by the ClassLoader name that the caller used.

## 8. Practical Usage: Choosing a Parent for a Plugin Loader

Suppose the host application declares the interface `com.acme.api.Plugin` and a plugin needs to implement that interface.

~~~text
Application classpath
  └── com.acme.api.Plugin       ← defined by the host's loader
Plugin JAR
  └── com.vendor.HelloPlugin    ← defined by the child loader
~~~

Two parent choices carry different implications:

**A. Sharing the host's API:**

~~~java
// This is a design pattern, not a standalone runnable program.
// Plugin is an interface already defined in the application.
ClassLoader parent = Plugin.class.getClassLoader();
// URLClassLoader loader = new URLClassLoader(jarUrls, parent);
~~~

The child loader delegates to the loader of `Plugin`, thereby resolving the shared interface with the exact same class identity. This is usually appropriate for plugins within the same JVM.

**B. Delegating directly only to the platform loader:**

~~~java
ClassLoader parent = ClassLoader.getPlatformClassLoader();
// URLClassLoader loader = new URLClassLoader(jarUrls, parent);
~~~

If the `Plugin` interface exists only on the classpath defined by the system loader and is not inside the plugin JAR, the child loader **typically cannot find** that interface. The consequence can be a `NoClassDefFoundError` or a provider error when loading the implementation class; having the platform loader as the parent does not make the system classpath visible to the child.

This is why you **choose the parent based on type-sharing needs** rather than mechanically picking platform or system. For untrusted plugins, privileges must be restricted at the process/container level with isolated protocols; ClassLoader does not provide a reliable security boundary.

## 9. Common Issues and How to Inspect Them

| Symptom | Cause or Misconception | How to Handle |
|---|---|---|
| `ClassCastException` when casting the system loader to `URLClassLoader` | Java 9+ does not guarantee that the system loader is of type `URLClassLoader` | Use the `ClassLoader` API, or create your own `URLClassLoader` for the JARs to load |
| Observing `platform.getParent() == null` and concluding platform is also bootstrap | `null` here **represents the bootstrap parent**, not that platform is bootstrap | Compare `platform == null` directly (false), and understand the meaning of `getParent()` |
| System loader returns `String.class` and concluding it defined `String` | Delegation returns the class defined by bootstrap | Check `String.class.getClassLoader()` |
| `ClassNotFoundException` when the platform loader searches for a host class | The application classpath is not a normal class lookup source for the platform loader | Use the host API's loader or the system loader when appropriate |
| `NoClassDefFoundError` inside a plugin | The plugin loader cannot see a required dependency or interface to resolve | Check the parent, the URLs containing dependency JARs, and the loader identity of the interface |
| `getSystemClassLoader().getParent()` differs from platform | Custom system loader or a different runtime configuration | Check `java.system.class.loader` and the actual loader hierarchy |
| `ServiceLoader` fails to find a provider | The thread context loader cannot see the plugin JAR or `META-INF/services` is missing | Explicitly specify the loader when loading the service; check the descriptor and resources |
| Initializing a custom system loader causes a circular error | The constructor calls back into `getSystemClassLoader()` | Use the parent passed into the constructor by the JVM; avoid accessing the system loader during initialization |
| `getResource(...)` does not find a resource in a named module | The module encapsulates the resource or differs in loader/visibility | Check the resource name, loader, module, and the module's `opens` rules |
| Code works from the IDE but not from the CLI | The IDE uses a different classpath/module path or context loader | Compare the launch command, classpath/module path, and `getClassLoader()` results |

For debugging, prioritize checking the **object identity** of the loader and class, for example:

~~~java
System.out.println(Example.class.getClassLoader());
System.out.println(Example.class.getClassLoader()
        == ClassLoader.getSystemClassLoader());
~~~

This is only illustrative code assuming class `Example` already exists. Do not use a loader's `toString()` string as a stable identifier: the display name and implementation class structure depend on the runtime. In a real application environment, you should also check the module name, `Class.getModule()`, and the bytecode source if relevant.

## 10. Self-Check Questions

**1. Why does `ClassLoader.getSystemClassLoader().loadClass("java.lang.String")` still return a class with `getClassLoader() == null`?**

Because the load request is **delegated** by the system loader to its ancestor. Bootstrap defines `String`, while the system loader merely returns the class already loaded/defined in the proper place.

**2. Why does `ClassLoader.getPlatformClassLoader().getParent() == null` not prove that the platform loader does not exist?**

`getParent()` returns the parent loader; `null` represents bootstrap in the standard configuration. The platform loader itself is still an instance returned by `getPlatformClassLoader()`.

**3. Which loader should be used as the parent when a plugin needs to implement a custom host interface?**

Typically `HostApi.class.getClassLoader()`, or another loader proven to locate the exact **same interface runtime type**. Do not default to the platform loader, as it generally cannot see the host classpath.

**4. Why should you not cast the system loader to `URLClassLoader` on Java 17?**

The API only promises to return a `ClassLoader`. Java 9+ uses built-in loader implementations different from Java 8, so the cast can fail.

**5. If `getSystemClassLoader()` returns a custom loader, is the default parent relationship still directly “system → platform”?**

Not necessarily. The custom loader receives the default system loader as its parent; the hierarchy can be **custom system → default system → platform → bootstrap**.

**6. Is the thread context loader always equal to the system loader?**

No. The `main` thread usually starts with the system loader, but frameworks, application servers, and application code can set a different context loader. To find out which loader defined a class, use `SomeClass.class.getClassLoader()`.

## 11. References

- [Java SE 17: ClassLoader — Built-in Class Loaders, getPlatformClassLoader and getSystemClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [Java SE 17: Class — getClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getClassLoader())
- [Java SE 17: ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html)
- [Java SE 17: Class.forName](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#forName(java.lang.String,boolean,java.lang.ClassLoader))

**Remember:** `getPlatformClassLoader()` retrieves the loader for platform APIs/runtime; `getSystemClassLoader()` retrieves the system loader typically used for the application. Parent relationships enable delegation, yet the **loader invoked** is not necessarily the **loader that defines the class**. When designing plugins, choose the parent based on the classes/interfaces the plugin actually needs to share.
