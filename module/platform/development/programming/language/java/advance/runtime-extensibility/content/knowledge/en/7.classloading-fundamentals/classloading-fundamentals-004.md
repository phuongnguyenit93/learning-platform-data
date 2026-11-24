# Parent Delegation and Visibility Across ClassLoaders in Java

## 1. Why Understand Loader Boundaries?

In Java, a single JVM can use multiple **ClassLoaders** to load classes from the classpath, module path, plugin JARs, or directories added at runtime. When building a runtime-extensibility system, the host usually needs to share an API/SPI with plugins while keeping each plugin's implementations and dependencies separate.

Two questions are easily confused:

- **Who was asked to find a class?** For example: `childLoader.loadClass("demo.api.Task")`.
- **Which loader actually defined that class?** For example: `Task` was defined by the application loader, even though `childLoader` received the call.

The **parent delegation** mechanism determines how classes are searched by default. **Visibility** describes which classes can be found through which loaders, alongside Java access rules. They are closely related yet not synonymous: finding bytecode does not guarantee access to use the class, and a class loaded through a child was not necessarily defined by the child.

With Java 17, understanding both mechanisms helps prevent `ClassNotFoundException`, `ClassCastException`, `NoClassDefFoundError`, library version conflicts, and SPI recognition errors between host and plugins.

## 2. Loader Tree and Parent/Child Relationships

A common structure in Java 17 applications:

~~~text
Bootstrap loader (typically represented as null)
          |
          v
Platform class loader
          |
          v
Application/System class loader
  - Host
  - Shared API/SPI
          |
          +------------------------+
          |                        |
          v                        v
   Plugin loader A          Plugin loader B
   - Provider A              - Provider B
   - Private library A       - Private library B
~~~

In this structure, loaders A and B both have the application loader as their parent. This is a common illustrative model, not a fixed tree that every Java application must use.

- **Bootstrap loader** loads critical core classes. In many Java APIs, `Class.getClassLoader()` returns `null` for classes defined by bootstrap; `null` is a representation, not proof that no loading mechanism exists.
- **Platform class loader** is accessible via `ClassLoader.getPlatformClassLoader()`; manages many platform/JDK classes.
- **System/application class loader** is obtained via `ClassLoader.getSystemClassLoader()`; normally handles application classes placed on the classpath.
- **Custom loaders** such as `URLClassLoader` can be created with a specific parent and a set of URLs containing classes/plugins. A child loader can itself be the parent of other loaders.

**Parent here is a delegation relationship**, not an `extends` relationship between Java classes implementing loaders. That `ClassLoader` A was instantiated by an object of loader B does not automatically make B the parent of A; the parent is determined by the constructor/configuration.

Built-in loaders are additionally subject to Java Platform Module System (JPMS) rules. For upgraded/special named modules, the platform loader may have to forward requests to another loader; do not assume every case is a rigid three-node lookup tree.

## 3. The Parent-First Algorithm of ClassLoader.loadClass

The `java.lang.ClassLoader` class defines a default convention for `loadClass(String, boolean)`. The core idea when loader `L` receives a request to load a binary name is:

1. Check whether the class has already been loaded by `L` or recorded as loaded via `L`, using **findLoadedClass**.
2. If not present, try **delegating to parent**. If parent is `null`, try the bootstrap loading path.
3. Only if parent/bootstrap does not find it does `L` invoke **findClass** to locate/define the class from its own source.
4. If resolve is requested, perform **resolveClass**; then return the corresponding `Class`.

Conceptual diagram:

~~~text
L.loadClass("pkg.Example")
          |
          v
   findLoadedClass?
      | yes -> return Class
      | no
      v
   parent.loadClass?
      | found -> return Class from parent
      | ClassNotFoundException
      v
   L.findClass?
      | found -> define/return Class belonging to L
      | not found -> ClassNotFoundException
~~~

This is **conceptual pseudocode**, not the full JDK source code. In reality there is also per-class-name locking, resolution/linking work, and error handling. A custom loader can override `loadClass` to change the strategy; therefore **parent-first is the default convention of ClassLoader, not a JVM law imposed on every custom loader**.

Frequently confused methods:

| API | Role |
| --- | --- |
| `loadClass(name)` | Request loading a class per the loader's algorithm; defaults to trying parent first |
| `findClass(name)` | Hook for a custom loader to locate/define a class itself when the parent path fails; not a whole-tree search API |
| `defineClass(...)` | Turns bytecode into a `Class` defined by the current loader, subject to JVM constraints |
| `findLoadedClass(name)` | Looks up a `Class` already recorded as loaded through this loader |
| `resolveClass(clazz)` | Performs the appropriate linking/resolution step; distinct from running static initializers |
| `Class.forName(name, initialize, loader)` | Locates a class using the specified loader and can request class initialization |

**Loading, linking, and initialization** are not the same thing. `ClassLoader.loadClass` by itself does not guarantee static initializers have run. `Class.forName(name, true, loader)` requests initialization; constructors or accessing static members can trigger initialization per language rules. Do not infer from "class is loaded" that "an object of the class has been created."

## 4. What Does Parent See, Child See, Sibling See?

Assume **P** is the application loader, and **A** and **B** both have parent **P**:

| Where is the class defined? | P requests load | A requests load | B requests load |
| --- | --- | --- | --- |
| `SharedApi` only in P | Succeeds, P's `Class` | Succeeds via delegation, P's `Class` | Succeeds via delegation, P's `Class` |
| `PluginAOnly` only in A | Not found along P's tree | Succeeds, A's `Class` | Not found along B's tree |
| `PluginBOnly` only in B | Not found along P's tree | Not found along A's tree | Succeeds, B's `Class` |
| `com.demo.Impl` has separate copies in both A and B, none in P | Not found | A's `Class` | B's `Class` |
| `com.demo.Version` has a copy in P and another in A | P's `Class` | **P's `Class`** due to parent-first | P's `Class` if B also delegates to P |

These outcomes assume standard parent-first loaders, no directories/JARs added to the parent classpath, and no custom delegation rules.

### 4.1. Children Normally See Ancestor Classes

A requests loading `SharedApi`; A tries parent P first. Because P has the class, A receives **the exact `Class` defined by P**, without creating a copy of its own. B receives the same `Class`. Thus, providers in A or B can implement the exact same SPI interface used by the host.

### 4.2. Parent Does Not Automatically See Child-Private Classes

P does not walk down into its children to search for `PluginAOnly`. The default delegation graph runs **from child up to parent**, and does not automatically scan child loaders. Consequently, a library loaded by P will not automatically discover a class living inside A if it only calls `P.loadClass(name)`.

However, the host can **explicitly hold a reference to A and call `A.loadClass(name)`**; frameworks can also receive loader A via a parameter or the thread context class loader. That is explicit use of A, not the parent having default downward visibility into children.

### 4.3. Sibling Loaders Do Not Automatically See Each Other

A and B share parent P; A does not become B's parent or vice versa. When B searches for a class located only in A, B tries P and then B's own sources, without querying A. To communicate between two plugins, you need a **shared API in the parent**, or an intentional bridge/registry mechanism; never treat A's private class as a direct contract that B must cast to.

## 5. Class Identity: Same Name Does Not Mean Same Class

In the JVM, the identity of a reference type is bound to **its binary name and defining class loader**. Hence two copies of `demo.provider.TaskImpl` defined by A and B can have the same `Class.getName()` yet be two different `Class` objects:

~~~java
// Illustration inside a host that already has two loaders A, B:
Class<?> a = loaderA.loadClass("demo.provider.TaskImpl");
Class<?> b = loaderB.loadClass("demo.provider.TaskImpl");
boolean same = (a == b); // false if A and B define two independent copies
~~~

An object of `TaskImpl-A` cannot arbitrarily be cast to `TaskImpl-B`. When two classes share a name yet differ in identity, `ClassCastException` can still occur; reading class names in a stack trace is not enough to understand the cause. Assignability also depends on the exact `Class` object, not just the name string.

On the other hand, if both `TaskImpl` classes implement **demo.api.Task defined by parent P**, the host can cast each instance to P's `Task`:

~~~text
Task interface: defined by P
         ^                 ^
         |                 |
TaskImpl-A (A)        TaskImpl-B (B)
         |                 |
   cast to Task      cast to Task
         \                 /
          \               /
            Used by Host
~~~

This is the foundation of plugin architecture: **share stable APIs/SPIs via a common loader; isolate implementations and dependencies underneath**. Be careful if each plugin accidentally bundles an extra copy of the API while a custom loader uses child-first: the interface can then be defined multiple times and lose assignability to the host.

## 6. Runnable Java 17+ Example: Two Child Loaders and One Shared API

The following hands-on example simultaneously demonstrates:

- Two child loaders sharing one parent and receiving the same `Class` for the SPI.
- Each child loader defining a provider **with the same binary name**, where each copy has different behavior.
- B cannot see a class present only in A; the parent cannot automatically see the children's providers.
- If both the parent and A contain a binary name, **parent-first picks the parent's copy**.

No frameworks or libraries outside the JDK are needed. Source files are placed in directory `demo` according to this tree:

~~~text
demo/
├── api/
│   └── demo/
│       ├── api/Task.java
│       └── common/Origin.java
├── a/
│   └── demo/
│       ├── provider/TaskImpl.java
│       ├── common/Origin.java
│       └── only/OnlyA.java
├── b/
│   └── demo/
│       └── provider/TaskImpl.java
├── host/
│   └── demo/
│       └── host/Main.java
└── out/
    ├── api/
    ├── a/
    ├── b/
    └── host/
~~~

Note that **out/** is the compiled classes directory created by the commands below. At runtime, `out/api` and `out/host` are on the application classpath; `out/a` and `out/b` are **not** on the application classpath and are passed only as URLs to the child loaders.

### 6.1. API Belonging to the Parent

**api/demo/api/Task.java**

~~~java
package demo.api;

public interface Task {
    String id();
}
~~~

**api/demo/common/Origin.java**

~~~java
package demo.common;

public final class Origin {
    public static String where() {
        return "parent";
    }
}
~~~

`Origin` is an illustrative class used to verify lookup order; it is not an SPI. A copy with the same name will also be compiled into plugin A to observe which copy is chosen.

### 6.2. Two Providers in Two Child Loaders

**a/demo/provider/TaskImpl.java**

~~~java
package demo.provider;

import demo.api.Task;

public final class TaskImpl implements Task {
    @Override
    public String id() {
        return "alpha";
    }
}
~~~

**a/demo/common/Origin.java**

~~~java
package demo.common;

public final class Origin {
    public static String where() {
        return "child A";
    }
}
~~~

**a/demo/only/OnlyA.java**

~~~java
package demo.only;

public final class OnlyA {
}
~~~

**b/demo/provider/TaskImpl.java**

~~~java
package demo.provider;

import demo.api.Task;

public final class TaskImpl implements Task {
    @Override
    public String id() {
        return "beta";
    }
}
~~~

Both `TaskImpl` files have **the same package, the same class name, and the same interface**. They are compiled into two independent directories. At runtime, `URLClassLoader` A searches `out/a` only after asking the parent; `URLClassLoader` B searches `out/b` only after asking the parent.

### 6.3. Host Creating URLClassLoaders with the Same Parent

**host/demo/host/Main.java**

~~~java
package demo.host;

import demo.api.Task;
import demo.common.Origin;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class Main {
    private static boolean canLoad(ClassLoader loader, String binaryName) {
        try {
            loader.loadClass(binaryName);
            return true;
        } catch (ClassNotFoundException expected) {
            return false;
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException("Expected directories A and B");
        }

        ClassLoader parent = Task.class.getClassLoader();
        URL aUrl = Path.of(args[0]).toUri().toURL();
        URL bUrl = Path.of(args[1]).toUri().toURL();

        try (URLClassLoader childA = new URLClassLoader(new URL[]{aUrl}, parent);
             URLClassLoader childB = new URLClassLoader(new URL[]{bUrl}, parent)) {

            Class<?> aClass = childA.loadClass("demo.provider.TaskImpl");
            Class<?> bClass = childB.loadClass("demo.provider.TaskImpl");

            Task a = (Task) aClass.getDeclaredConstructor().newInstance();
            Task b = (Task) bClass.getDeclaredConstructor().newInstance();

            System.out.println("A: " + a.id());
            System.out.println("B: " + b.id());
            System.out.println("Same provider class: " + (aClass == bClass));
            System.out.println("Shared SPI class: " +
                    (childA.loadClass("demo.api.Task") ==
                     childB.loadClass("demo.api.Task")));
            System.out.println("Parent defines SPI: " +
                    (childA.loadClass("demo.api.Task").getClassLoader() == parent));
            System.out.println("Parent-first duplicate: " +
                    (childA.loadClass("demo.common.Origin") == Origin.class));
            System.out.println("B sees OnlyA: " +
                    canLoad(childB, "demo.only.OnlyA"));
            System.out.println("Parent sees provider: " +
                    canLoad(parent, "demo.provider.TaskImpl"));
        }
    }
}
~~~

**Analysis of key calls:** `parent` is obtained from `Task.class.getClassLoader()`, i.e., the loader owning the host's SPI. Each `URLClassLoader` receives that exact parent. Because the parent does not have `demo.provider.TaskImpl`, A and B define two separate copies. Conversely, the parent has `demo.api.Task`, so both A and B return the same `Class` for the interface.

### 6.4. Compiling and Running

Stand in the **demo/** directory. On Linux/macOS, create the output directories:

~~~bash
mkdir -p out/api out/a out/b out/host
~~~

On Windows PowerShell, you can use:

~~~powershell
New-Item -ItemType Directory -Force out/api,out/a,out/b,out/host | Out-Null
~~~

The following `javac` commands work on both operating systems because each command has only **one classpath entry**:

~~~bash
javac --release 17 -d out/api api/demo/api/Task.java api/demo/common/Origin.java
javac --release 17 -cp out/api -d out/a a/demo/provider/TaskImpl.java a/demo/only/OnlyA.java a/demo/common/Origin.java
javac --release 17 -cp out/api -d out/b b/demo/provider/TaskImpl.java
javac --release 17 -cp out/api -d out/host host/demo/host/Main.java
~~~

Run on Linux/macOS (**`:`** separates classpath entries):

~~~bash
java -cp "out/api:out/host" demo.host.Main out/a out/b
~~~

Or on Windows PowerShell/cmd (**`;`**):

~~~powershell
java -cp "out/api;out/host" demo.host.Main out/a out/b
~~~

**Exact standard output:**

~~~text
A: alpha
B: beta
Same provider class: false
Shared SPI class: true
Parent defines SPI: true
Parent-first duplicate: true
B sees OnlyA: false
Parent sees provider: false
~~~

Meaning of the lines:

1. A and B create their own providers, running the same `id()` method yet returning different values.
2. Both providers have the same binary name yet **do not share the same `Class` identity**, because A and B define them independently.
3. Both calls loading `demo.api.Task` return the single `Class` from the parent, enabling both instances to cast cleanly to `Task`.
4. Plugin A also contains `demo.common.Origin` returning `"child A"`, yet `childA.loadClass` returns the parent's `Origin` due to parent-first. Two copies are not chosen by "newer" or "closer."
5. Loader B cannot find `demo.only.OnlyA` because that class exists only in A. The parent cannot find `demo.provider.TaskImpl` because the providers are only placed in the children's URLs.

**Conditions for correct results:** run in a standard JVM whose classpath contains only `out/api` and `out/host`; do not accidentally add `out/a`, `out/b`, or a JAR containing providers to the parent classpath. Changing the launch setup can change class visibility and the results.

## 7. Where Does Parent-First Differ from Child-First?

Default `ClassLoader` and `URLClassLoader` normally check the parent first and then their own sources. This offers a clear benefit: core Java classes and the host's shared APIs are seen consistently from plugins.

However, some plugin systems need **dependency version isolation**. For example, the host has `library-x` version 1, while plugin A requires `library-x` version 2. Under parent-first, if the parent loader already sees `library-x` with the same binary name, A may accidentally receive version 1, leading to mismatched method/field errors.

Two strategies are commonly weighed:

| Strategy | Principle | Advantages and risks |
| --- | --- | --- |
| Parent-first | Parent takes precedence before child searches its own classes | Keeps shared APIs consistent, but risks dependency collisions if parent contains plugin libraries |
| Controlled child-first | For designated namespaces, try own sources first before asking parent | Can isolate versions, but easily duplicates API/SPI classes and breaks casting |

**Overriding `findClass` alone does not turn a loader into child-first.** Changing precedence requires intentionally adjusting `loadClass`, preserving locks, handling `findLoadedClass`, delegation, resolution, and class-identity safeguards. You must never try to redefine core classes in the `java.*` namespace; the JVM enforces its own protection constraints. An uncontrolled child-first strategy can trigger `ClassCastException`, `LinkageError`, dependency cycles, and class-loading deadlocks.

In practice, it is usually best to keep **parent-first for Java/platform and host APIs/SPIs; explicitly decide which plugin namespaces may stay private**. For conflicting libraries that do not need to appear in the API, you can isolate them via loaders or relocate/shade packages where appropriate.

## 8. Thread Context Class Loader: Why Can Parent Code Sometimes Find Plugins?

A library residing in a parent loader normally does not know the class names or JAR paths of plugins ahead of time. It can use the **thread context class loader (TCCL)** to obtain a loader supplied by the execution environment.

Example where a framework wants to discover SPI implementations:

~~~java
// Illustrative snippet inside a host that already has pluginLoader and MyService.class.
ClassLoader old = Thread.currentThread().getContextClassLoader();

try {
    Thread.currentThread().setContextClassLoader(pluginLoader);
    java.util.ServiceLoader<MyService> providers =
            java.util.ServiceLoader.load(MyService.class);
    for (MyService provider : providers) {
        provider.execute();
    }
} finally {
    Thread.currentThread().setContextClassLoader(old);
}
~~~

This is an **illustrative fragment**, not a standalone program; it requires `MyService`, `pluginLoader`, and valid provider configuration. `ServiceLoader.load(service)` uses the thread's context loader; there is also the **ServiceLoader.load(service, loader)** overload to select a loader explicitly, which is often easier to control in plugin hosts.

TCCL **does not invert the parent relationship**, does not cause `P.loadClass` to automatically see every child, and does not alter class identity. It only changes which loader APIs that consciously consult TCCL pick for discovery/loading.

When changing TCCL, always restore it in `finally`, especially on thread pools where threads are reused. Do not let plugin code hold onto the context loader indefinitely. Child threads may inherit the context loader of the thread that spawned them; a retained reference to an old loader can also prevent plugin unloading.

## 9. Resource Visibility Is Not Identical to Class Visibility

`ClassLoader` also looks up **resources** such as configuration files and `META-INF/services`. With the default `ClassLoader` implementation:

- **getResource(name)** tries the parent first and then the loader's own `findResource`.
- **getResources(name)** can collect multiple URLs; the default order puts parent results first followed by results found by the current loader.
- **findResource/findResources** are hooks for a custom loader to search its own sources.
- **getResourceAsStream(name)** opens the resource as an `InputStream` if found; close the stream when done.

Illustrative example in a host:

~~~java
// Illustrative snippet; pluginLoader is an already configured ClassLoader.
java.net.URL config = pluginLoader.getResource("config/plugin.properties");
if (config == null) {
    throw new IllegalStateException("Missing plugin resource");
}
~~~

With `ClassLoader.getResource`, ordinary resource names **do not begin with a leading `/`**. By contrast, `Class.getResource` uses package-relative paths and absolute paths starting with `/`. These two APIs are easily confused.

If both parent and plugin contain the same resource name, parent-first can cause the host's configuration to be picked ahead of the plugin's; therefore avoid overly generic resource names. Service descriptors can also appear in multiple JARs; in that case an API like `ServiceLoader` iterates through the corresponding resources according to its own rules.

**Named modules introduce additional resource encapsulation rules**: a resource present in a module is not necessarily visible via `getResource` like an arbitrary classpath file. Module readability/exports/opens and resource-opening rules can apply; do not assume all module resources can be accessed like unnamed-module resources.

## 10. Finding a Class Does Not Guarantee Access or Casting

Separate three layers:

1. **Reachability/loading**: can the loader locate a class definition by name?
2. **Type identity/compatibility**: does that `Class` have the same identity or assignability relationship with the type expected by the host?
3. **Access control**: does the caller have permission to access the class, package, constructor, and invoked members?

For example, two classes defined by different loaders may share a name yet not be assignable to each other. Even when the exact class is found, a non-public constructor can still cause `IllegalAccessException` when reflection instantiates it. For **named modules**, whether a package is exported or opened to the caller is an additional condition; having a class loader that sees the bytecode is not enough to bypass module access control. In systems using APIs/SPIs, the host should place public interfaces/DTOs in a properly exported shared module or library.

**Runtime packages** also depend on the class loader (and corresponding module metadata), so package-private access is not guaranteed merely because two classes share the same package name string if they come from different loaders.

## 11. Common Errors and How to Diagnose Them

| Symptom | Primary likelihood | How to investigate |
| --- | --- | --- |
| `ClassNotFoundException` when calling `loadClass` | No loader along the delegation path found the binary name | Check classpath, URLs, package/class name, and the loader being called |
| `NoClassDefFoundError` when using a class | A dependency needed at linking/initialization is missing, or the class failed to initialize earlier | Inspect cause, classpath, dependencies, and initializer errors |
| `ClassCastException` even though class names look identical | Two different defining loaders or genuinely incompatible type relationship | Compare `Class` objects and `getClassLoader` on each type |
| `NoSuchMethodError`/`NoSuchFieldError` | Selected class version differs from the version used at compile time | Check which library copy parent-first picked and verify binary compatibility |
| Other `LinkageError` | Linkage constraint violation or incompatible definitions | Inspect cause, class loader identity, and dependency graph |
| `ServiceLoader` does not find providers | Wrong TCCL, loader cannot see `META-INF/services`, invalid descriptor | Try `ServiceLoader.load(service, loader)` with an explicit loader; check resources |
| Plugin A runs, plugin B cannot find A's classes | Sibling loaders do not delegate to each other automatically | Move shared contract to parent API or design a bridge |
| Same-named resource gets picked from host | Parent-first in `getResource` | Print returned URL and give resources clear namespaces |

You can print the loader identity alongside the class name to observe:

~~~java
// Illustrative fragment taking Class<?> from an actual load operation.
static void describe(Class<?> type) {
    System.out.println(type.getName());
    System.out.println(type.getClassLoader());
    System.out.println(type.getModule());
}
~~~

This snippet only illustrates a debugging idea, not a standalone Java program. Print both the name and the loader, because identical `Class.getName` is not enough to determine `Class` identity. For bootstrap classes, `Class.getClassLoader()` can return `null`; do not invoke methods on that result without checking first.

If you need more detail, you can pass **-Xlog:class+load=info** when launching a JVM supporting unified logging (Java 17) to watch classes being loaded and their bytecode sources. Class loading happens lazily, so logs can vary depending on execution paths; do not infer the entire system from a list of classes that have never been touched.

## 12. Lifecycle and Limits of the Delegation Mechanism

Creating a new `URLClassLoader` does not automatically "reload" a `Class` already defined in an old loader. To pick up a new version of a class with the same name, systems typically create a new loader and hand over responsibility to new instances while ensuring no old references remain. An already-defined `Class` cannot normally have its definition replaced simply by reloading a file from the same path in the same loader.

`URLClassLoader` is `AutoCloseable`/`Closeable`; close it when no longer in use to release resources and file handles. **`close()` does not immediately unload classes** and does not guarantee that objects/Threads/TCCLs/callbacks holding references disappear. Class unloading also depends on garbage collection and having no reachable loaders/classes/objects left. If the host retains a static registry or thread context loader pointing to the old plugin, removing the plugin may fail to reclaim memory.

Parent delegation is also **not a security sandbox**. Plugins running inside the same JVM can still affect resources or state they are able to reach; isolating untrusted code requires appropriate permission controls and process boundaries.

## 13. Test Matrix and Checklist

| Test scenario | Expected result to confirm |
| --- | --- |
| Child loads class present only in parent | Receives the exact `Class` defined by parent |
| Both child and parent have the same binary name | With parent-first, the parent's copy is chosen |
| Class exists only in child A | Parent and sibling B cannot automatically load it |
| A and B each define the same binary name | Two distinct `Class` objects |
| Providers in A/B implement API defined by parent | Both can cast to the host's SPI |
| Plugin carries its own API copy and uses child-first | Detects risk to class identity/assignability |
| `Class.load` vs `Class.forName` with `initialize` | Distinguishes loaded from having executed static initializers |
| Parent/resource and child/resource have the same name | Confirms ordering of `getResource`/`getResources` |
| `ServiceLoader` using TCCL or explicit loader | Discovery uses the intended class loader |
| Closing and replacing plugin loader | No stale references left in TCCL/threads/registries |

Before deploying an extension point, check the following:

1. There is one shared API/SPI copy in a loader actually visible to both host and plugins.
2. The parent is chosen explicitly when creating loaders; do not assume "same JVM" means "same classpath."
3. Namespaces of implementations, dependencies, and resources have explicit parent-first/child-first policies.
4. Classes communicating across boundaries use only types with shared identity; never expose plugin-private classes in the API for other plugins to cast directly.
5. The host understands the paths of `ClassNotFoundException`, `NoClassDefFoundError`, `ClassCastException`, and linkage errors; log loader identity when needed.
6. Discovery operations use an explicit loader or controlled TCCL; always restore TCCL after changing it.
7. Module accessibility, resource lookup, and class loader lifecycle have been verified by tests in a realistic deployment environment.

**Key takeaway:** default `ClassLoader` looks up classes in the direction **child → parent → child's own sources**; a child can use ancestor `Class` objects, while parents and siblings do not automatically see a child's private classes. Sharing **contract types** in a common loader and isolating **implementations** in separate loaders is the foundational design for reliable runtime extensibility.

Official Java 17 documentation:

- https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html
