# Comparing parent-first and child-first in Java ClassLoader

**Parent-first** and **child-first** are two **class lookup priority policies** when a class loader needs to handle an unloaded class name. They determine **whether to ask the parent first or try the loader's own class source first**, thereby affecting the library version used, runtime type identity, plugin integration capabilities, and how dependency conflicts are handled.

In Java, `ClassLoader.loadClass` implements **parent-first delegation** by default. **Child-first** is a custom strategy, commonly found in plugin systems, application servers, or library version isolation environments. It is **not a built-in flag** in the `URLClassLoader` constructor. Using child-first requires a loader that implements its own policy, while preserving necessary exceptions for platform classes and shared APIs.

This lesson belongs to the **Loading policies** group of **Java core – classloader**. The content focuses on lookup order, runnable Java 17+ examples, impacts on the **defining loader**, shared SPIs/DTOs, resources, common errors, and how to make a well-grounded policy choice.

## 1. “First” is lookup priority, not Java inheritance order

Suppose both the host and the plugin have a class named `lib.Version`:

```text
HOST / parent loader                 PLUGIN / child loader
lib.Version  ->  "host"              lib.Version  ->  "plugin"
                  ▲                                  │
                  └───── parent of plugin loader ────┘
```

When code requests `pluginLoader.loadClass("lib.Version")`:

- **Parent-first:** tries the parent first. If the parent finds `lib.Version`, the child returns that exact class; the plugin's version may **never be defined**.
- **Child-first:** tries the plugin's local source first. If the child can find/define `lib.Version` itself, the plugin's version is selected; if there is no local class, depending on the policy, it falls back to the parent.

These are **two class selection policies**. They do **not** change:

- the Java superclass of `PluginLoader` (the `extends` keyword);
- the parent object returned by `pluginLoader.getParent()`;
- classes that have already been defined;
- the classpath used at **compile time**;
- the semantics of object creation or calling constructors of the loaded class.

**Key takeaway:** the same binary name can lead to **two different runtime types** if two separate class loaders define it themselves. The JVM identifies a type by **(binary name, defining loader)**, not merely by the class name string.

## 2. Default flow: parent-first

Java 17 `ClassLoader.loadClass(String, boolean)` has the conceptual algorithm:

```text
loadClass(name)
      │
      ▼
findLoadedClass(name)
      ├── already loaded → return recorded Class<?>
      │
      └── not yet
            │
            ▼
      ask parent.loadClass(name)
            │
            ├── success → return class found by parent/ancestor
            │
            └── ClassNotFoundException
                       │
                       ▼
                 findClass(name)
                       │
                       ├── success → class defined by child
                       └── failure → ClassNotFoundException
```

Three things to remember:

1. **Check already-loaded first:** the JVM does not create another class definition with the same binary name in the same defining loader just because `loadClass` is called again.
2. **Parent gets the first chance:** if `parent.loadClass` succeeds, the child does not need to use `findClass` for that name.
3. **Child is the fallback:** only when the parent cannot find it under the default logic does the child try its own class source.

`ClassLoader.loadClass(String)` normally calls the overload with `resolve=false` and does not automatically trigger static initialization. Loading, linking, and initialization are distinct concepts from parent/child priority policies.

Note that the diagram illustrates the **default `ClassLoader` contract**. Built-in loaders in JDK 9+ have module-aware logic, and custom loaders can override `loadClass`. Do not describe this linear diagram as an absolute rule for every modern loader.

## 3. Child-first flow: prioritizing own source, but with boundaries

A typical child-first loader implements the idea:

```text
loadClass(name)
      │
      ▼
findLoadedClass(name)
      ├── already present → return Class<?>
      └── not yet
           │
           ▼
     Is this a platform class / mandatory shared API?
           ├── yes → use parent-first for protected namespace
           │
           └── no
                │
                ▼
          try child.findClass(name)
                ├── found → return class defined by child
                └── ClassNotFoundException
                          │
                          ▼
                    try parent.loadClass(name)
```

**Important:** the “child first” idea alone is not enough for a correct implementation. A practical custom loader must also:

- Use `findLoadedClass` to avoid duplicate class definitions.
- Synchronize lookup properly, for example `synchronized (getClassLoadingLock(name))`.
- Do not swallow every `LinkageError` or `SecurityException` to fall back arbitrarily.
- Keep a **shared API namespace** always resolving to the host's exact runtime type.
- Do not attempt to define classes belonging to protected namespaces such as `java.*` on its own.
- Consider `registerAsParallelCapable()` if planning to implement complex concurrent loading; not every loader is parallel-capable by default.
- Maintain consistency of package sealing, module access, and resource/service discovery.

**Not every package should be child-first.** Typical plugin systems need **parent-first for contracts** and **selective child-first for private libraries**.

## 4. Decision comparison table

| Criterion | Parent-first | Child-first |
| --- | --- | --- |
| Source tried first | Parent/ancestor | Child's own source (except protected namespaces) |
| Implemented in default `ClassLoader` | Yes | No, usually requires overriding |
| For classes with the same name in host and plugin | Host version usually wins | Plugin version can win |
| Sharing host-defined SPI/DTO | Convenient if the API is in parent | Must protect API packages via delegation |
| Isolating private dependency versions | Difficult if parent already has a version with the same name | More favorable when the child contains a suitable version |
| Risks | Host library shadows plugin library; version skew | Creating duplicate API copies causing `ClassCastException`, `LinkageError` |
| JDK classes | Usually delegated from child to parent | Still need to ensure platform classes have a valid loading path |
| Complexity | Lower, familiar contract | Higher: synchronization, fallback, constraints, module/resource |
| Does it replace the parent object? | Not required | Not required |
| Does it guarantee a safe sandbox? | No | No |

There is no “absolute best” choice. **Parent-first** is suitable if the system has a unified dependency graph and wants to share many APIs; **selective child-first** is useful if plugins must use different library versions while still needing a common contract.

## 5. Practice A setup — same class name in host and plugin

This practice uses `URLClassLoader` to create a **parent-first loader** and a **custom child-first loader**. Both look at **the same plugin directory**, but with different priority orders.

Directory tree:

```text
policy-lab/
├── src/
│   ├── hostlib/
│   │   └── lib/Version.java
│   ├── pluginlib/
│   │   └── lib/Version.java
│   └── app/
│       └── demo/PolicyDemo.java
├── hostlib-out/      (generated by javac)
├── pluginlib-out/    (generated by javac)
└── app-out/          (generated by javac)
```

**`src/hostlib/lib/Version.java`:**

```java
package lib;

public final class Version {
    public static String origin() {
        return "host";
    }
}
```

**`src/pluginlib/lib/Version.java`:**

```java
package lib;

public final class Version {
    public static String origin() {
        return "plugin";
    }
}
```

The two source files declare **the same binary name `lib.Version`**, but produce **two different binary directories**. Do not compile both into the same output folder; the goal is to observe **runtime class selection**, not to declare two duplicate classes in a Java package of the same build.

### Controlled child-first implementation

File **`src/app/demo/PolicyDemo.java`**:

```java
package demo;

import lib.Version;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class PolicyDemo {
    static final class ChildFirstLoader extends URLClassLoader {
        ChildFirstLoader(URL[] urls, ClassLoader parent) {
            super(urls, parent);
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            synchronized (getClassLoadingLock(name)) {
                Class<?> found = findLoadedClass(name);

                if (found == null) {
                    if (name.startsWith("java.")) {
                        // Platform namespace: let parent/ancestor handle it.
                        found = super.loadClass(name, false);
                    } else {
                        try {
                            // Prioritize the child's own URLs.
                            found = findClass(name);
                        } catch (ClassNotFoundException notLocal) {
                            // Only fall back when there is truly no local class.
                            found = super.loadClass(name, false);
                        }
                    }
                }

                if (resolve) {
                    resolveClass(found);
                }
                return found;
            }
        }
    }

    private static String origin(ClassLoader loader) throws Exception {
        Class<?> type = loader.loadClass("lib.Version");
        return (String) type.getMethod("origin").invoke(null);
    }

    public static void main(String[] args) throws Exception {
        URL pluginClasses = Path.of("pluginlib-out")
                .toAbsolutePath().toUri().toURL();
        URL[] urls = { pluginClasses };
        ClassLoader host = PolicyDemo.class.getClassLoader();

        System.out.println("host=" + Version.origin());

        try (URLClassLoader parentFirst =
                     new URLClassLoader(urls, host);
             ChildFirstLoader childFirst =
                     new ChildFirstLoader(urls, host)) {

            System.out.println("parent-first=" + origin(parentFirst));
            System.out.println("child-first=" + origin(childFirst));

            Class<?> fromParent = parentFirst.loadClass("lib.Version");
            Class<?> fromChild = childFirst.loadClass("lib.Version");

            System.out.println("parent shares host=" +
                    (fromParent == Version.class));
            System.out.println("child differs from host=" +
                    (fromChild != Version.class));
            System.out.println("child defined locally=" +
                    (fromChild.getClassLoader() == childFirst));
        }
    }
}
```

**Compile** inside `policy-lab` using JDK 17+:

```sh
javac --release 17 -d hostlib-out src/hostlib/lib/Version.java
javac --release 17 -d pluginlib-out src/pluginlib/lib/Version.java
javac --release 17 -cp hostlib-out -d app-out src/app/demo/PolicyDemo.java
```

Run on **Windows PowerShell/CMD**, with the classpath separated by `;`:

```powershell
java -cp "app-out;hostlib-out" demo.PolicyDemo
```

Run on **Linux/macOS**, separated by `:`:

```sh
java -cp "app-out:hostlib-out" demo.PolicyDemo
```

**Stdout of the `java` command with this layout:**

```text
host=host
parent-first=host
child-first=plugin
parent shares host=true
child differs from host=true
child defined locally=true
```

### Line-by-line explanation

- **`host=host`:** `demo.PolicyDemo` uses `lib.Version` from `hostlib-out` on the application classpath.
- **`parent-first=host`:** the default `URLClassLoader` asks the host loader first. Since the parent already has `lib.Version`, it returns the `host` version and does not search for the plugin version.
- **`child-first=plugin`:** the `ChildFirstLoader` subclass tries `findClass("lib.Version")` first. It reads `pluginlib-out/lib/Version.class` and defines its own runtime type.
- **`parent shares host=true`:** the same `Class<?>` as the host's `Version.class`; therefore, both calls share the same class identity.
- **`child differs from host=true`:** the name `lib.Version` is the same, but the defining loaders are different.
- **`child defined locally=true`:** calling `getClassLoader()` on the `Class<?>` returns `childFirst` itself, demonstrating that the lookup result is the local version.

**Example limitations:** this is a simplified loader for explaining the policy. It uses parent fallback for `java.*`, has not built out a full package/module policy for a production framework, and does not yet handle all resource types or plugin versions. Do not copy it verbatim as a class loader for untrusted third-party code.

## 6. Why does example A not need to change the parent?

In the example, **both parent-first and child-first have the same parent object**:

```java
ClassLoader host = PolicyDemo.class.getClassLoader();
URLClassLoader parentFirst = new URLClassLoader(urls, host);
ChildFirstLoader childFirst = new ChildFirstLoader(urls, host);
```

This is an **illustrative recap snippet** that can be placed inside a method if the variables and imports are available; in real usage, both loaders must be closed at the right time.

The difference lies in `loadClass`:

- With parent-first, the default plan is to ask `host.loadClass`, and only then call the child's `findClass`.
- With child-first, the child's `findClass` is called early for names outside protected namespaces. Only when no local class is found does it ask the parent.

**Parent is a relationship between loader objects**, not the `extends` syntax. Using the same parent object **does not cause the two policies to yield the same result**, because each loader can choose a different order for calling the parent.

Conversely, merely changing the parent in a regular `URLClassLoader` constructor can also change which class is found, but **it does not mean child-first has been implemented**. Distinguish **choosing which sources are visible** from **the priority order among those sources**.

## 7. Same name is not the same type: runtime identity and casting

A type in the JVM is identified by the pair:

```text
(binary name, defining loader)
```

In example A:

```text
"lib.Version" + host loader       → host Class
"lib.Version" + childFirst loader → plugin Class
```

Therefore:

```java
fromParent.getName().equals(fromChild.getName()); // true
fromParent == fromChild;                          // false
```

This is an illustrative snippet assuming the two variables have already been declared from example A. If `lib.Version` is a domain class used to pass objects between the host and the plugin, the child-first version **may not be castable** to the host version, even though the method signatures look identical.

If the internal library `lib.Version` is only used for computation and returns a `String`, two separate definitions may not cause problems. However, if this library version is exposed in a public API (parameter/return type/exception/annotation), the identity issue becomes a boundary error.

**Do not use class names as the criterion for runtime equivalence.** To verify that a plugin implements the host's exact interface, use `HostApi.class.isAssignableFrom(pluginClass)` and compare `Class<?>` from both sides when needed.

## 8. Design boundaries: shared APIs must be shared, private dependencies can be isolated

Suppose the host has an interface:

```java
package api;

public interface Greeter {
    String greet(String name);
}
```

If the plugin implements the host's **exact runtime `api.Greeter`**, the host can cast the instance to `Greeter`. If the child-first loader **defines its own duplicate of `api.Greeter`**, the result can be:

```text
HostLoader defines api.Greeter    → interface A
PluginLoader defines api.Greeter  → interface B

PluginImpl implements B
Host needs interface A

A.getName() == B.getName()       → same binary name
A == B                           → false
A.isAssignableFrom(PluginImpl)   → false
```

Even **character-for-character identical** interface source code does not merge two types into one. This is why **pure child-first** is usually unsuitable for all packages.

A common practical model is **selective delegation**:

| Namespace | Policy to consider | Reason |
| --- | --- | --- |
| `java.*` and appropriate platform APIs | Parent/platform delegation | Avoid attempting to self-define platform classes |
| `api.*` (host SPI/DTO/callback) | Mandatory parent-first for shared APIs | Protect type identity between host and plugin |
| `impl.*` | Child-first | Plugin implementation may reside in a separate JAR |
| Private `vendor.*` | Child-first if the host also has a different version | Allow the plugin to manage its own dependency version |
| Unknown name | Fall back according to the defined policy | Must not swallow linkage errors or create loops |

The `api.*` namespace is an **example name**, not a standard JDK package. In production, explicitly list the contract packages and types exposed through method descriptors rather than relying solely on a simple prefix if the API spans multiple packages.

## 9. Practice B — child-first with exceptions to share the host's API

The following example intentionally packages **two copies of the bytes for the same `api.Greeter`** in two sources: the host's `api-out` and the plugin's `plugin-out`. This demonstrates why there must be a dedicated **parent-first rule for `api.*`**, even when the implementation uses child-first.

File tree:

```text
shared-api-lab/
└── src/
    ├── api/api/Greeter.java
    ├── plugin/impl/PluginGreeter.java
    └── host/demo/SelectiveDemo.java
```

**`src/api/api/Greeter.java`:**

```java
package api;

public interface Greeter {
    String greet(String name);
}
```

**`src/plugin/impl/PluginGreeter.java`:**

```java
package impl;

import api.Greeter;

public final class PluginGreeter implements Greeter {
    public PluginGreeter() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

**`src/host/demo/SelectiveDemo.java`:**

```java
package demo;

import api.Greeter;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class SelectiveDemo {
    static final class SelectiveLoader extends URLClassLoader {
        private final boolean protectSharedApi;

        SelectiveLoader(URL[] urls, ClassLoader parent,
                        boolean protectSharedApi) {
            super(urls, parent);
            this.protectSharedApi = protectSharedApi;
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            synchronized (getClassLoadingLock(name)) {
                Class<?> clazz = findLoadedClass(name);

                if (clazz == null) {
                    boolean delegate = name.startsWith("java.")
                            || (protectSharedApi && name.startsWith("api."));

                    if (delegate) {
                        clazz = super.loadClass(name, false);
                    } else {
                        try {
                            clazz = findClass(name);
                        } catch (ClassNotFoundException missingLocal) {
                            clazz = super.loadClass(name, false);
                        }
                    }
                }

                if (resolve) {
                    resolveClass(clazz);
                }
                return clazz;
            }
        }
    }

    public static void main(String[] args) throws Exception {
        URL pluginUrl = Path.of("plugin-out")
                .toAbsolutePath().toUri().toURL();
        URL[] urls = { pluginUrl };
        ClassLoader sharedParent = Greeter.class.getClassLoader();

        try (SelectiveLoader protectedLoader =
                    new SelectiveLoader(urls, sharedParent, true);
             SelectiveLoader naiveLoader =
                    new SelectiveLoader(urls, sharedParent, false)) {

            Class<?> good =
                    protectedLoader.loadClass("impl.PluginGreeter");
            Class<?> goodApi = good.getInterfaces()[0];

            System.out.println("protected API shared=" +
                    (goodApi == Greeter.class));
            System.out.println("protected implementation local=" +
                    (good.getClassLoader() == protectedLoader));
            System.out.println("protected assignable=" +
                    Greeter.class.isAssignableFrom(good));

            Greeter service = (Greeter)
                    good.getDeclaredConstructor().newInstance();
            System.out.println("protected result=" +
                    service.greet("Java"));

            Class<?> bad = naiveLoader.loadClass("impl.PluginGreeter");
            Class<?> badApi = bad.getInterfaces()[0];

            System.out.println("naive same name=" +
                    badApi.getName().equals(Greeter.class.getName()));
            System.out.println("naive same Class=" +
                    (badApi == Greeter.class));
            System.out.println("naive assignable=" +
                    Greeter.class.isAssignableFrom(bad));
        }
    }
}
```

**Compile** from the `shared-api-lab` directory:

```sh
javac --release 17 -d api-out src/api/api/Greeter.java
javac --release 17 -cp api-out -d plugin-out src/plugin/impl/PluginGreeter.java
javac --release 17 -d plugin-out src/api/api/Greeter.java
javac --release 17 -cp api-out -d host-out src/host/demo/SelectiveDemo.java
```

The third command intentionally copies the **API binary** into the plugin's output by compiling the same source file into `plugin-out`. In a production environment, **you should not package a duplicate shared API** if avoidable; this step is only meant to simulate the error in a controlled way.

Run on **Windows**:

```powershell
java -cp "host-out;api-out" demo.SelectiveDemo
```

Run on **Linux/macOS**:

```sh
java -cp "host-out:api-out" demo.SelectiveDemo
```

**Stdout of the `java` command:**

```text
protected API shared=true
protected implementation local=true
protected assignable=true
protected result=Hello, Java
naive same name=true
naive same Class=false
naive assignable=false
```

### Explaining the execution path of the two loaders

**Loader with API protection:**

1. `impl.PluginGreeter` does not belong to a protected namespace; the child prioritizes `findClass` and defines the implementation itself.
2. When the JVM needs `api.Greeter` for the `implements` clause, `SelectiveLoader` detects the `api.` prefix and calls `super.loadClass` in parent-first order.
3. The host parent sees `api.Greeter` from `api-out`, so it returns the host's **exact runtime interface**, even though `plugin-out` contains a duplicate.
4. `Greeter.class.isAssignableFrom(good)` is true; casting and calling the method succeed.

**Naive loader without API protection:**

1. Both `impl.PluginGreeter` and `api.Greeter` are found by the child in `plugin-out`.
2. The child's `api.Greeter` has the same binary name as the host's version, but a **different defining loader**.
3. The plugin class implements the **child's interface version**, not the host's interface.
4. `Greeter.class.isAssignableFrom(bad)` returns `false`. If the cast `(Greeter) bad.getDeclaredConstructor().newInstance()` is executed, the program can throw `ClassCastException`.

**Design limitations in this exercise:** checking the `api.` prefix is only an exercise. A production system must **precisely** determine which packages need to be shared and which loader owns them, considering additional platform namespaces, JPMS, package sealing, class-loading concurrency, and resource lookup. Calling `super.loadClass` for `api.*` will still fall back to local if the parent **does not have the API**; therefore, the prerequisite is that the **shared parent actually defines/sees the exact contract**.

## 10. Why does `java.*` need a special exception?

The Java runtime has platform namespaces and modules that a custom loader must not arbitrarily define on its own. In a child-first loader:

```java
if (name.startsWith("java.")) {
    return super.loadClass(name, false);
}
```

This is a **logic illustration snippet**, not a complete override (it lacks synchronization, loaded-cache checking, or resolve handling). It expresses the intent not to search locally for `java.*` first.

Note:

- Checking `java.` **does not replace** all module/JDK rules. Platform APIs can reside in other namespaces; a production implementation should have a **complete policy** and understand JPMS.
- `ClassLoader.defineClass` has its own checks that forbid defining class names starting with `java.` in an ordinary application loader.
- Choosing `ClassLoader.getPlatformClassLoader()` as the parent allows the child to see all **platform classes**, whereas a `null` parent relies only on the bootstrap mechanism, which does not guarantee that every Java SE/JDK class is on the bootstrap loader in Java 9+.
- Do not confuse “avoid defining `java.*`” with “all `java.*` classes are defined directly by the platform loader”: many core classes are defined by the bootstrap loader, while the platform loader still sees them through delegation.

A child-first loader that is safe with respect to **class-loading correctness** still does **not** turn plugin code into a security sandbox. Class loaders address namespace/visibility; untrusted code requires an independent security boundary.

## 11. Why must you not catch every error to fall back to the parent?

An incorrect pattern:

```java
try {
    return findClass(name);
} catch (Throwable ignored) {
    return getParent().loadClass(name);
}
```

This is an **incorrect pattern** and lacks enough context to run standalone. `Throwable` includes many errors that do not mean “the class was not found in the child”:

- `LinkageError` can indicate incompatible bytecode/APIs, a loader constraint violation, or a class definition error.
- `ExceptionInInitializerError`/`NoClassDefFoundError` can indicate that an earlier initialization failed or a dependency is missing.
- `SecurityException` can reflect a namespace/permission rule violation.
- `OutOfMemoryError` is not a lookup signal to silently switch sources.
- `ClassFormatError` and `UnsupportedClassVersionError` indicate unsuitable class bytes and should not be masked by an arbitrary version from the parent.

Fallback in the example only occurs when `findClass` throws **`ClassNotFoundException`**. This is the signal for “no local class definition exists with this name” in the loader API; in that case, trying the parent is reasonable logic. All other errors should be handled according to the contract, logged with context, and **never swapped to another version without permission**.

Even `ClassNotFoundException` can arise from internal custom loader logic; production systems need to distinguish a missing local class, a missing dependency, access/JPMS failures, and other causes when debugging.

## 12. Synchronization, `findLoadedClass`, and the define-once rule

When multiple threads concurrently request the class `lib.Version`, a custom child-first loader must not allow both to call `defineClass` for the same binary name in one loader instance. The JVM can report `LinkageError: attempted duplicate class definition` or related errors.

The key part of the override in the two examples:

```java
synchronized (getClassLoadingLock(name)) {
    Class<?> existing = findLoadedClass(name);
    if (existing != null) {
        return existing;
    }

    // Try local or parent according to the policy.
}
```

This is an **illustrative snippet** without complete lookup/result-handling logic. Key points:

- `getClassLoadingLock(name)` provides the lock that `ClassLoader` uses for requests to load a class name. For a loader not registered as parallel-capable, the lock may be the loader object itself; parallel-capable loaders can have a per-class-name lock.
- `findLoadedClass(name)` looks up a class already recorded as having had its loading initiated by that loader. It does not only report classes defined by the child itself; classes from the parent can also be recorded as having been loaded through the loader.
- Loaded classes must be checked **before** every local definition path.
- `resolveClass(clazz)` is only executed when `resolve` is requested, after the appropriate `Class<?>` has been selected.
- Do not use an arbitrary global lock if performance is needed, but also do not omit synchronization just because single-threaded tests pass.

### Parallel-capable loader

`ClassLoader.registerAsParallelCapable()` is a `protected static` API. When creating a subclass with concurrency requirements that wants to use per-binary-name locks, it must be registered at the proper time in the subclass's static initializer, understanding the rules regarding superclasses and registration. It is not automatically added to every snippet because doing so would make the policy comparison examples harder to read.

An incorrect override in a complex loader also carries a **deadlock** risk if loaders have circular delegation relationships or inconsistent synchronization. The standard `ClassLoader` parent chain avoids certain forms of cycles due to how it is constructed, but custom graphs/delegation beyond the parent can introduce additional dependencies between loaders. Production designs must verify concurrency and cycle detection.

## 13. Method linking and binary compatibility after class selection

Lookup priority only determines **which runtime class is used**. Afterward, the JVM must still link the method/field references in the bytecode:

```text
Plugin compile-time:
    lib.Parser.parse(String):Result  (v2)

Runtime parent-first:
    lib.Parser v1 only has parse(byte[]):Result

Result:
    the runtime class is found, but the method descriptor does not exist
    → may throw NoSuchMethodError at the point of use
```

This issue does not necessarily appear immediately when `pluginLoader.loadClass("impl.Plugin")` returns `Class<?>`; the JVM can defer resolution until an instruction needs the method. Therefore, “loaded successfully” **does not guarantee** dependency version compatibility.

Common errors:

| Error | What may have happened |
| --- | --- |
| `ClassNotFoundException` | The queried loader could not find the class by name |
| `NoClassDefFoundError` | A dependency could not be defined/used when the JVM needed it, or the class previously failed initialization |
| `NoSuchMethodError` | The runtime method reference has no method matching the descriptor |
| `NoSuchFieldError` | The runtime field reference has no field matching the name/descriptor |
| `IncompatibleClassChangeError` | A mismatch between class/interface, static/instance, or another linkage contract |
| `IllegalAccessError` | Runtime access/module constraints do not allow linking |
| `ClassCastException` | The runtime type is not assignable to the type expected by the host |
| `LinkageError` loading constraint | Two loader definitions do not satisfy type-safety constraints |
| `ExceptionInInitializerError` | Static initializer failed, not merely selecting the wrong loader |

To fix this, identify the **defining loader and artifact of the exact runtime class**, and compare the bytecode descriptor and dependency graph. Do not switch to child-first to mask every `LinkageError` without first understanding the root cause.

## 14. Are resources necessarily child-first along with classes?

**No.** A custom loader that only overrides `loadClass` to be child-first can still **keep the default parent-first `getResource`/`getResources` behavior**.

Example:

```text
Host classpath:
    config/theme.txt = host-theme

Plugin URL:
    config/theme.txt = plugin-theme
```

Even though `ChildFirstLoader` in example A defines `lib.Version` from the child URL, `child.getResource("config/theme.txt")` can return the **host version** because resource lookup asks the parent first. If the plugin needs its own resources, this must be designed and tested.

The APIs:

- `ClassLoader.getResource(name)`: the resource URL found according to the loader's policy.
- `ClassLoader.getResourceAsStream(name)`: an InputStream or `null` if not found or cannot be opened; the caller must check and close it.
- `ClassLoader.getResources(name)`: an Enumeration of visible URLs, suitable for investigating duplicate resource names.
- `URLClassLoader.findResource(name)`: searches only the child's own URLs; **this is not changing the class loading policy**.
- `getURLs()`: the URLClassLoader's own URL roots, **not** including the parent's URLs.

For plugin systems requiring strong isolation, separate policies must be defined for **classes**, **resources**, and **ServiceLoader discovery**. Do not infer “child-first resources” from “child-first classes”.

## 15. Self-checking resource priority when classes use child-first

Before changing the resource policy, use the exact loader from practice A and place `config/theme.txt` in both the host and the plugin. Give the two files different contents, then check three operations:

```java
String path = "config/theme.txt";
System.out.println(childFirst.getResource(path));  // default parent-first
System.out.println(childFirst.findResource(path)); // child's URL source only
var urls = childFirst.getResources(path);
while (urls.hasMoreElements()) {
    System.out.println(urls.nextElement());       // order of all URLs
}
```

This snippet sits inside the `try` block where `ChildFirstLoader childFirst` was declared; `IOException` from `getResources` must be handled. The APIs above return a URL or an enumeration, **not** the content directly. Read each URL to confirm the source order, and note that default `ClassLoader.getResource` can still select the parent's resource even though `loadClass` prioritized the child. If the resource is a schema/config that must match the implementation, explicitly document the override rule or fail fast. For `META-INF/services`, all descriptors must be considered rather than only the first URL.

## 16. Child-first in a plugin model: designing clear boundaries

A plugin system typically has three groups:

```text
                        SHARED HOST API
                         api.Plugin
                         api.Request
                         api.Response
                              ▲
                     parent-first for api.*
                              │
                 ┌────────────┴────────────┐
                 │                         │
             PLUGIN A                   PLUGIN B
             impl.a.*                   impl.b.*
             vendor.json v1             vendor.json v2
                 │                         │
              child-first              child-first
              private libs              private libs
```

This is a **conceptual model** and does not create a module/loader graph automatically without implementation. Contract classes need to share identity; private dependencies may differ in version.

### Distinguishing shared types and private types

Example API:

```java
package api;

public interface Processor {
    Result process(Request input) throws PluginException;
}
```

This is an **illustrative declaration** and requires adding `Request`, `Result`, and `PluginException` to compile. All types appearing at the boundary may need the same runtime identity:

- `api.Processor` is the SPI for the host to cast the plugin implementation.
- `api.Request` and `api.Result` appear in the JVM method descriptor.
- `api.PluginException` can be caught by the host by its runtime type.
- Callback interfaces, enums, annotations, and types nested inside payloads can also leak across the boundary.
- A `vendor.JsonNode` appearing in a public method signature can turn a seemingly private library into a **shared contract dependency**.

If the plugin defines a duplicate `api.Request`, reflective lookups such as `getMethod("process", HostRequest.class)` may fail to find the right method, or the JVM may report loading-constraint errors depending on the context.

**Design principle:** parent-first for packages/types that must be shared; child-first for code/dependencies that can remain independent, with control over fallback policy and module access.

## 17. JPMS and Java 9+: module readability does not equal loader priority

In the Java Platform Module System (JPMS), a named module has:

- **module resolution**: which modules are selected into the layer;
- **readability** via `requires` and module rules;
- **exports/opens**: which packages are accessible or open for reflection;
- **defining loader**: which loader defines the class;
- **delegation policy**: the order in which a loader searches for classes.

These five axes **are not the same thing**. A module `app.module` reading `api.module` does not mean the application loader must be a child of the API loader, nor does choosing child-first for a package automatically bypass `exports`.

`URLClassLoader` normally loads JARs in a **classpath-style** manner from URLs. Passing a modular JAR into the URL array **does not automatically create a new `ModuleLayer`** with valid `requires`/`exports`. To achieve module isolation, appropriate layers and loaders must be designed rather than merely changing `loadClass`.

On Java 9+, the built-in loaders (bootstrap/platform/application) have module-aware mechanisms, so the actual relationship between loaders and modules can be more complex than a simple parent chain. The examples above run on the **unnamed application classpath** so that policy control is easy to observe.

## 18. When to choose which policy?

**Choose default parent-first if:**

- The plugin is a trusted extension within an application whose dependency versions are already aligned;
- all plugins share the host SDK/SPI/DTO and rarely need separate library versions;
- the goal is ease of maintenance, reducing type identity confusion, and avoiding custom `loadClass` overrides;
- the runtime does not require per-package isolation.

**Consider child-first with exceptions if:**

- Multiple plugins must use **different versions** of the same library;
- the host has libraries with colliding binary names, where parent-first would pick the wrong version that the plugin was compiled against;
- the shared API has already been designed and loaded by a common loader;
- the system is prepared to test synchronization, package sealing, JPMS, and resource loading against the actual loader graph.

**Do not choose child-first if the sole goal is “better security”.** A class loader policy does not replace a sandbox; untrusted plugin code can perform any actions that the process is permitted to perform. Use process/container boundaries and separate access controls when the threat model demands them.

### Decision-making workflow

1. Identify the **shared API type identity** that both the host and the plugin must share.
2. Collect **dependency collisions**: which class names exist in both the parent and the child, and which version is being compiled against?
3. Verify whether parent-first actually causes a version conflict using a small example and binary signatures.
4. If child-first is needed, write a **per-package** policy rather than unconditionally altering all class names.
5. Define corresponding resource lookup and service discovery policies.
6. Test the plugin using the **real runtime loader graph**, rather than only compiling the host and plugin together on a single classpath.
7. Verify unloading/lifecycle when replacing a plugin, and do not reuse a loaded class as though it will relink against a new JAR.

## 19. Diagnostic tools in Java 17+

### Identifying the defining loader

```java
static void describe(Class<?> type) {
    System.out.println("name=" + type.getName());
    System.out.println("defined by=" + type.getClassLoader());
    System.out.println("module=" + type.getModule().getName());
}
```

This is an **illustrative method**, placed inside a class and called with the type to inspect. `getModule().getName()` returns `null` when the class is in an unnamed module — that is normal behavior.

For class loaders that can be retrieved:

```java
System.out.println(pluginLoader.getParent());
System.out.println(java.util.Arrays.toString(pluginLoader.getURLs()));
```

These snippets require `pluginLoader` to be of type `URLClassLoader`. Remember that `getURLs()` only reports **the child's own URLs**, not the effective set after delegation.

### Reading bytecode and descriptors

For example A:

```sh
javap -classpath hostlib-out -s lib.Version
javap -classpath pluginlib-out -s lib.Version
javap -classpath app-out -c -v demo.PolicyDemo
```

These commands read static class files. `javap` can confirm the method descriptors generated by the compiler, but **does not prove whether the runtime chose the parent or the child**. Combine it with `Class.getClassLoader()` or source logging.

### Class-load log

On HotSpot:

```sh
java -Xlog:class+load=info -cp "app-out:hostlib-out" demo.PolicyDemo
```

The command uses the **Linux/macOS** classpath separator; on Windows, replace `:` with `;`. Unified Logging produces many lines whose order and locations depend on the JVM/build, so there is no fixed exact stdout. Look for the `lib.Version` events and class file sources, then cross-check them against the defining loader information inside the program.

## 20. Practical error debugging checklist

| Symptom | Questions to ask | Troubleshooting approach |
| --- | --- | --- |
| Plugin sees an old library version | Does the parent have a class with the same binary name? | Check parent-first, choose an explicit dependency strategy |
| `ClassCastException` with classes of the same name | Do the host and plugin have two `Class<?>` from two defining loaders? | Protect the shared API, inspect loaders |
| `NoSuchMethodError` | Which descriptor did the caller compile against, and does the runtime class have that method? | Compare bytecode/JAR versions and priority policy |
| `NoClassDefFoundError` | Which URL holds the dependency, or did a class initializer fail? | Read the cause and runtime lookup graph |
| `IllegalAccessError` | Do the package/module/caller have access permissions? | Check JPMS exports and visibility |
| `LinkageError` loader constraint violation | Are types in public signatures doubly defined? | Unify contract identity |
| `ClassNotFoundException` | Could neither local nor parent find it? | Check URL roots, JAR entries, and parent |
| `ServiceConfigurationError` | Do the service interface/provider share identity, and is the discovery loader right? | TCCL, ServiceLoader, shared SPI |
| Wrong resource configuration | Is `getResource` still parent-first? | Debug `getResources`/`findResource` |
| Fails only under multiple threads | Does the `loadClass` override guard `findLoadedClass` and locking? | Test concurrency, locks, and parallel capability |

**Do not swallow `Throwable` and fall back.** Linkage, security, or VM errors are not normal class-source selection signals. Preserve the stack trace and root cause when debugging.

## 21. Loader lifecycle and version replacement

`URLClassLoader` implements `Closeable`. If your code owns the loader, you can:

```java
try (URLClassLoader plugin = new URLClassLoader(urls, parent)) {
    Class<?> implementation =
            plugin.loadClass("impl.PluginGreeter");
}
```

This is a **snippet** requiring the `urls` and `parent` variables and the `URLClassLoader` import. Upon exit, `close()` closes the JAR/file handles managed by the loader. However:

- `close()` **does not immediately unload** all plugin classes/objects;
- still-referenced objects/Class/Method/ThreadLocal/threads or TCCL can keep the loader alive;
- an already-defined class does not automatically change its bytecode when a JAR on disk is replaced;
- after closing, code may attempt to lazy-load a dependency/resource and fail;
- a new plugin version usually requires a **new loader instance**, detaching callbacks/threads and releasing old references;
- the shared API must still maintain stable runtime identity across plugin version lifecycles.

Child-first does not solve hot reload by itself; it is only one component of the class-loading architecture.

## 22. Misconceptions to avoid

- **“Java is child-first by default.”** No. Standard `ClassLoader.loadClass` prioritizes the parent.
- **“Putting the plugin URL before the host URL in a child overrides parent-first.”** No: the parent is still asked before local URLs.
- **“Simply choosing the platform loader as parent makes it child-first.”** No: that changes the **set visible via the parent**, not the lookup order.
- **“Child-first is always better because plugins use newer libraries.”** No: it can define duplicate copies of shared APIs.
- **“If the interface name is the same, casting works.”** No: JVM type identity also includes the defining loader.
- **“Overriding `loadClass` only requires calling `findClass` first.”** Not enough: you also need the loaded-cache, synchronization, fallback, and module/API constraints.
- **“Catching every `Throwable` and trying the parent is safe.”** False: doing so hides JVM/linkage/permission errors.
- **“Child-first means resources are also child-first.”** No: `getResource` has its own policy.
- **“If the plugin has a duplicate API in its JAR, the JVM automatically picks the right copy.”** No: it depends on delegation and the defining loader.
- **“Parent-first copies all parent JARs into the child.”** No: it is strictly runtime lookup/delegation.
- **“Two URLClassLoaders of the same Java class share the same class namespace.”** No: **two instances** can define distinct runtime classes.
- **“Working in the IDE means the plugin JAR will definitely work in the runtime loader.”** No: the IDE/test classpath can mask boundary errors.
- **“Parent-first/child-first is a sufficient security choice for untrusted plugins.”** No.
- **“Closing a URLClassLoader immediately unloads all classes.”** No; it still depends on GC and references.

## 23. Self-check questions

**1. Who does parent-first ask first?** After checking already-loaded classes, the loader asks the parent; only when the parent cannot find the class does it try the child's `findClass`.

**2. Is child-first built into the `URLClassLoader` constructor?** No. `URLClassLoader` uses parent-first `loadClass` by default; child-first must be deliberately implemented.

**3. With the same binary name in both parent and child, which version does parent-first usually use?** The parent's version if the parent finds it first.

**4. In the same situation, which version can child-first use?** The child's version if local lookup succeeds and the namespace is not protected.

**5. Are two definitions with the same name the same runtime Java type?** No, if their defining loaders are different.

**6. Why should the host's API be parent-first?** So that the host and plugin share the same runtime interface/DTO/callback identities, avoiding cast/linkage errors.

**7. Why is `findLoadedClass` important?** It prevents duplicate definitions and ensures loaded classes are used consistently.

**8. Why fall back only on `ClassNotFoundException`?** Because other errors may reflect invalid bytecode, missing permissions, or linking failures, rather than “no local class exists”.

**9. If you only override `loadClass`, does `getResource` automatically become child-first?** No. Resource lookup needs its own policy if you want to change it.

**10. Does `URLClassLoader.getURLs()` include the parent's URLs?** No; only that loader's own URLs.

**11. Why can `NoSuchMethodError` occur even though the class loaded successfully?** Method resolution in bytecode requires an exact descriptor, but the selected runtime version lacks that method.

**12. Can parent-first be a reasonable choice when plugins need shared SDKs/DTOs?** Yes, especially when all plugins use a single binary API with uniformly managed versions.

**13. Does child-first always load every Java SE class separately?** No; protected platforms/namespaces require delegation according to runtime rules.

**14. What criteria should guide strategy selection?** Which types **must share identity**, which dependencies **must have separate versions**, module/resource policies, and operational cost.

## 24. Authoritative references

- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `findLoadedClass`, `findClass`, `getClassLoadingLock` algorithms, and parallel capability.
- [Java SE 17 — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): constructors, URLs, lookup, and lifecycle.
- [Java SE 17 — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): defining loader and `isAssignableFrom` when checking API identity.
- [JVMS Java SE 17, Chapter 5](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): runtime class identity, loading, linking, and loading constraints.
- [Java SE 17 — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): provider discovery and the impact of loader/context.

**Key summary:** **Parent-first** prioritizes reusing classes from the parent, which is good for shared APIs and simple runtime structures, though host dependencies can shadow the plugin's versions. **Child-first** prioritizes definitions from the child, which is useful when plugins need separate dependency versions, but it must **intentionally apply parent-first to shared boundary types**, synchronize properly, handle errors accurately, and verify resources/JPMS. The question is not “which policy is better?” but rather **“which classes must share runtime identity, and which classes must be allowed to stay separate?”**
