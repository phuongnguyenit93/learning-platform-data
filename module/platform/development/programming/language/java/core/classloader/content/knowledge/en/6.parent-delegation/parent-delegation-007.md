# Visibility from Child Loader to Parent Loader

## 1. The Meaning of “Visibility” in the Delegation Mechanism

In Java, a ClassLoader is not only responsible for reading `.class` files. It determines **which loader is allowed to participate in finding a class or resource** and **which loader actually defines the runtime class**. With the typical **parent-first delegation** model, a child loader tries asking its parent loader to find the class first. Only if the parent cannot find it does the child loader search its own sources.

The most important point of this lesson is **asymmetry**:

- **Child → parent:** a child loader typically sees the classes that its parent loader or the parent's ancestors can find through the delegation mechanism.
- **Parent → child:** a parent loader **does not automatically search** JARs, directories, or classes managed solely by a child loader.
- “Seeing” does not necessarily mean “defining itself”: a child loader can **return the exact class defined by the parent**, without creating a duplicate.
- The delegation mechanism for class lookup **does not bypass** Java access control, runtime type integrity, or module rules.

This is the model of the default `ClassLoader.loadClass` and subclasses that follow delegation. A custom ClassLoader can override `loadClass` to change the lookup rules; JPMS also has special module linkages. Therefore, do not treat the parent–child relationship as an immutable visibility rule across every ClassLoader in every framework.

## 2. Visual Model

For example, a JVM has an application loader (parent) and a `URLClassLoader` loading a plugin JAR (child):

~~~text
                     Bootstrap ClassLoader
                               ▲
                               │
                     Platform ClassLoader
                               ▲
                               │
                     Application Loader
                     (parent)
                       ├── demo.api.Greeter
                       └── demo.host.Host
                               ▲
                  loadClass()   │ delegates up to parent
                               │
                     URLClassLoader
                     (child)
                       └── hello-plugin.jar
                             ├── demo.plugin.HelloGreeter
                             └── plugin-message.txt
~~~

Suppose only the parent has `demo.api.Greeter` and only the child has `demo.plugin.HelloGreeter`:

| Request | Result under typical parent-first | Who defines the class? |
|---|---|---|
| `child.loadClass("demo.api.Greeter")` | Child asks parent; parent finds it | **Parent** |
| `child.loadClass("demo.plugin.HelloGreeter")` | Parent does not find it; child searches in the JAR | **Child** |
| `parent.loadClass("demo.api.Greeter")` | Parent finds the class on its own classpath | **Parent** |
| `parent.loadClass("demo.plugin.HelloGreeter")` | Not found if the plugin JAR belongs only to the child | No result, throws `ClassNotFoundException` |
| `child.getResource("plugin-message.txt")` | Child finds its own resource after the parent does not find it | Resource URL inside the plugin JAR |
| `parent.getResource("plugin-message.txt")` | Does not find the resource that exists only in the child | Returns `null` |

**The direction of the arrow is the direction of lookup delegation from child up to parent.** Java has no default mechanism requiring a parent to iterate over all existing child loaders. A parent may not even keep any list of its children.

“Parent does not see child” does **not** mean that code defined by the parent can never use a class from the child. The host can certainly hold a reference to the child loader, call `child.loadClass(...)`, or receive a plugin instance via a shared interface. In that case, the host **explicitly calls into the child loader**, rather than the parent searching backward on its own via `parent.loadClass(...)`.

## 3. How Does Parent-First Find a Class?

Conceptually, the default implementation of `ClassLoader.loadClass(String, boolean)` performs:

1. Checks whether the class is already known to the loader via `findLoadedClass(name)`.
2. If not, **delegates to the parent** via `parent.loadClass(name, false)`; if there is no parent, tries the bootstrap mechanism.
3. Only when the parent/bootstrap loader reports that it was not found does it call the loader's own `findClass(name)`.
4. If the caller requests `resolve == true`, performs the necessary resolution on the result.

A pseudocode representation:

~~~java
// PSEUDOCODE: not a standalone runnable method.
Class<?> loadClassConceptually(String name) throws ClassNotFoundException {
    Class<?> already = findLoadedClass(name);
    if (already != null) {
        return already;
    }

    try {
        return delegateToParentOrBootstrap(name);
    } catch (ClassNotFoundException notFoundByParent) {
        return findClass(name);
    }
}
~~~

This is a **logical model**, not a verbatim copy of the real implementation. The actual implementation handles synchronization, exceptions, resolution, and many other details.

Common points of confusion:

- `loadClass(...)` may return a class **defined by the parent**, even though the child is the object receiving the call.
- Each call to `loadClass` **does not necessarily** re-read the bytecode; the loader and the JVM remember classes that have been loaded.
- The parent-first check applies to the class **requested for lookup**; it does not force the JVM to initialize all of the parent's classes beforehand.
- `loadClass(String)` normally **does not trigger class initialization**. If you want to initialize actively, you can use `Class.forName(name, true, loader)` after understanding the need.
- `ClassLoader` defaults to parent-first; a framework may use child-first or package/module-specific rules.

## 4. Runnable Java 17+ Example: Host, API, and Plugin

We will build an experimental program demonstrating four results: **the child sees the API from the parent**, **the parent does not see the child-only implementation**, **the child loads the implementation and resource from the plugin JAR**, and **two separate children define two classes with the same name but different runtime types**.

### 4.1. Project Structure

Create the directories and files at the exact paths:

~~~text
visibility-demo/
├── host-src/
│   └── demo/
│       ├── api/
│       │   └── Greeter.java
│       └── host/
│           └── Host.java
├── plugin-src/
│   └── demo/
│       └── plugin/
│           └── HelloGreeter.java
└── plugin-resources/
    └── plugin-message.txt
~~~

The `build/host` and `build/plugin` directories and the `build/hello-plugin.jar` file will be created during the compilation step. **Do not put the plugin JAR on the classpath of the host execution command**, because the goal is for the host and the plugin to reside in two different loaders.

### 4.2. Shared Contract in the Parent

File **`host-src/demo/api/Greeter.java`**:

~~~java
package demo.api;

public interface Greeter {
    String greet(String name);
}
~~~

This interface is compiled onto the host classpath. The plugin is allowed to depend on `Greeter` at **compile time**, but at **runtime** it will resolve the interface through the parent loader.

### 4.3. Child-Only Implementation Class

File **`plugin-src/demo/plugin/HelloGreeter.java`**:

~~~java
package demo.plugin;

import demo.api.Greeter;

public final class HelloGreeter implements Greeter {
    public HelloGreeter() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

This is a `public` class with a `public` no-arg constructor, so the host can instantiate it using reflection. The plugin can call interface methods defined by the parent because the plugin loader can ask the parent to load `demo.api.Greeter`.

Text file **`plugin-resources/plugin-message.txt`**:

~~~text
Only the plugin loader sees this resource by default.
~~~

This file exists only in the plugin JAR and is used to verify that **resource** lookup also follows the delegation direction and does not automatically reverse from parent down to child.

### 4.4. Host Explicitly Creating Child Loaders

File **`host-src/demo/host/Host.java`**:

~~~java
package demo.host;

import demo.api.Greeter;

import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;

public final class Host {
    private Host() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: Host <path-to-plugin-jar>");
        }

        Path jar = Path.of(args[0]).toAbsolutePath().normalize();
        if (!Files.isRegularFile(jar)) {
            throw new IllegalArgumentException("Missing JAR: " + jar);
        }

        ClassLoader parent = Greeter.class.getClassLoader();
        URL[] urls = {jar.toUri().toURL()};

        try (URLClassLoader child = new URLClassLoader(urls, parent);
             URLClassLoader anotherChild = new URLClassLoader(urls, parent)) {

            Class<?> apiViaChild =
                    child.loadClass("demo.api.Greeter");
            System.out.println("Child sees parent API: "
                    + (apiViaChild == Greeter.class));

            boolean parentSeesPlugin;
            try {
                parent.loadClass("demo.plugin.HelloGreeter");
                parentSeesPlugin = true;
            } catch (ClassNotFoundException ignored) {
                parentSeesPlugin = false;
            }
            System.out.println("Parent finds child-only class: "
                    + parentSeesPlugin);

            Class<?> implementation =
                    child.loadClass("demo.plugin.HelloGreeter");
            System.out.println("Plugin defined by child: "
                    + (implementation.getClassLoader() == child));

            Greeter instance = (Greeter) implementation
                    .getConstructor()
                    .newInstance();
            System.out.println("Call through shared API: "
                    + instance.greet("Java"));

            System.out.println("Child finds plugin resource: "
                    + (child.getResource("plugin-message.txt") != null));
            System.out.println("Parent finds plugin resource: "
                    + (parent.getResource("plugin-message.txt") != null));

            Class<?> implementationTwo =
                    anotherChild.loadClass("demo.plugin.HelloGreeter");
            System.out.println("Two child classes identical: "
                    + (implementation == implementationTwo));

            System.out.println("Both implement shared API: "
                    + (Greeter.class.isAssignableFrom(implementation)
                    && Greeter.class.isAssignableFrom(implementationTwo)));
        }
    }
}
~~~

**Why choose `Greeter.class.getClassLoader()` as the parent?** Because this is the loader that **defines the interface that the host and plugin need to share**. In this sample classpath program, it is the application/system loader; in complex frameworks, the interface's loader may differ from the system loader. Obtaining the parent from the interface aligns the design with the goal of sharing the runtime type.

We create **two** `URLClassLoader` instances with the same JAR path to prove that two independent child loaders can still define two implementation classes bearing the **same binary name** yet not being the same runtime class.

## 5. Compiling and Running the Experiment

Requires JDK **17 or later** with `javac`, `jar`, and `java`. Open a terminal in the `visibility-demo/` directory containing all four source/resource files.

**Bash on Linux/macOS or Git Bash:**

~~~bash
mkdir -p build/host build/plugin

javac -encoding UTF-8 \
  -d build/host \
  host-src/demo/api/Greeter.java \
  host-src/demo/host/Host.java

javac -encoding UTF-8 \
  -cp build/host \
  -d build/plugin \
  plugin-src/demo/plugin/HelloGreeter.java

jar --create --file build/hello-plugin.jar \
  -C build/plugin . \
  -C plugin-resources .

java -cp build/host demo.host.Host build/hello-plugin.jar
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force build/host,build/plugin | Out-Null

javac -encoding UTF-8 -d build/host host-src/demo/api/Greeter.java host-src/demo/host/Host.java

javac -encoding UTF-8 -cp build/host -d build/plugin plugin-src/demo/plugin/HelloGreeter.java

jar --create --file build/hello-plugin.jar -C build/plugin . -C plugin-resources .

java -cp build/host demo.host.Host build/hello-plugin.jar
~~~

The packaging command keeps `demo/plugin/HelloGreeter.class` and `plugin-message.txt` in the plugin JAR, while `Greeter.class` remains in `build/host`. Inspect if needed:

~~~bash
jar --list --file build/hello-plugin.jar
~~~

In the listing command output, make sure there are at least the two entries `demo/plugin/HelloGreeter.class` and `plugin-message.txt`; the JAR may also contain `META-INF/MANIFEST.MF` and directory entries.

**Program stdout on the specified standard classpath:**

~~~text
Child sees parent API: true
Parent finds child-only class: false
Plugin defined by child: true
Call through shared API: Hello, Java!
Child finds plugin resource: true
Parent finds plugin resource: false
Two child classes identical: false
Both implement shared API: true
~~~

Internal class loader names such as `jdk.internal.loader.ClassLoaders$AppClassLoader@...` are not printed because this string is unstable across JVMs or runs. The `==` comparisons produce concrete, verifiable results.

## 6. Path Analysis for Each Call

### 6.1. Child Requests a Parent Class

~~~java
Class<?> apiViaChild = child.loadClass("demo.api.Greeter");
~~~

The child checks `demo.api.Greeter` and then asks the parent. The parent already sees `Greeter` from `build/host`, so it returns the class it defined itself. The child receives and returns the **same `Class<?>` object**:

~~~java
apiViaChild == Greeter.class  // true
~~~

No duplicate copy of `Greeter` is defined by the child. Claiming that “calling `child.loadClass` means the class belongs to the child” would misexplain both the host/plugin code and the ability to cast via the API.

### 6.2. Parent Requests a Class Located Only in the Child

~~~java
parent.loadClass("demo.plugin.HelloGreeter");
~~~

The plugin JAR is **not on the parent's classpath**, so the parent and its ancestors cannot find `HelloGreeter`. The parent has no standard “try all my children” step and throws `ClassNotFoundException`.

This conclusion applies only to the example configuration. If the same plugin JAR is also placed on the application classpath, or if the parent is configured with additional class lookup sources, the parent **can find** the plugin. That is, visibility direction depends on **both the loader relationship and the bytecode location**.

### 6.3. Child Requests the Implementation Class from Its Own JAR

~~~java
Class<?> implementation =
        child.loadClass("demo.plugin.HelloGreeter");
~~~

The child asks the parent; the parent does not find it, so the child proceeds to use `URLClassLoader`'s `findClass` capability to read the class from the JAR. Therefore:

~~~java
implementation.getClassLoader() == child  // true
~~~

During the JVM's linking of this class, the `demo.api.Greeter` interface is looked up via the parent; therefore, the plugin object can be cast to `Greeter` and the host can call `greet("Java")`. The two sides do not need the same loader **for every class**, but rather need to share the exact **same runtime interface** at the communication boundary.

### 6.4. Resources Have the Same Default Lookup Direction

~~~java
child.getResource("plugin-message.txt")   // non-null URL
parent.getResource("plugin-message.txt")  // null in the example
~~~

`URLClassLoader` implements `getResource` in a parent-first manner: it asks the parent first, then searches its own URLs. However, when the parent queries on its own, it **does not know the child's URLs** and therefore cannot find the plugin's resource. Similarly, `getResources` can aggregate resources from the parent and the child according to its implementation rules, and `ServiceLoader` uses `META-INF/services/...` resources to locate providers when running under the classpath mechanism.

For resources in **named modules**, there are also package encapsulation/opening rules and module mechanisms; do not assume every resource can be read from every loader.

### 6.5. Two Children, Two Independent Implementation Classes

~~~java
Class<?> implementationTwo =
        anotherChild.loadClass("demo.plugin.HelloGreeter");
~~~

`child` and `anotherChild` have the same JAR URL and parent, yet each loader **defines its own** `demo.plugin.HelloGreeter`. To the JVM, runtime class identity depends on the **binary name plus the defining loader**:

~~~text
(demo.plugin.HelloGreeter, child)
    !=
(demo.plugin.HelloGreeter, anotherChild)
~~~

Thus `implementation == implementationTwo` returns `false`. Even so, both implementations use `demo.api.Greeter` defined by the **same parent**, so `Greeter.class.isAssignableFrom(...)` returns `true` for both.

This is a useful form of isolation for plugins: implementations across two versions can be different runtime types, while the host still communicates through the same API.

## 7. Class Visibility Differs from Member Access Permission

Even when a child finds a parent's class, Java still checks access permissions to the class, constructor, method, and field:

- A `public` member of a public API can be used if the corresponding module rules allow it.
- A `private` member does not become accessible merely through a parent–child loader relationship.
- A **runtime package** is determined not only by the package name but also by the **defining loader** (and, in the module system, also the module). Two classes with the same package name string but defined by two different loaders **do not automatically have package-private access** to each other.
- Reflection is also subject to access control and JPMS `exports`/`opens`. A parent relationship does not automatically bypass `InaccessibleObjectException` or `IllegalAccessException`.

For example, placing a `demo.api.Helper` class in the parent with a package-private method, and then adding a class in the same package `demo.api.PluginCode` to the child, **does not make** the two classes belong to the same runtime package. Attempting unauthorized access can cause an `IllegalAccessError` during linking/execution, depending on the case.

When building plugins, place the shared contract in a **public exported API** according to proper design; do not rely on “both being in the `demo.api` package” to share default-access members.

## 8. Why Can the Parent Sometimes Still Call Code in the Child?

A host program loaded by the parent can still work with plugin objects through two mechanisms:

**Approach 1 — Explicitly using the child loader.** For example, `Host` calls `child.loadClass(...)`, instantiates it via reflection, and casts the object to `Greeter`. This is precisely what our runnable example demonstrated. The class that the host directly references in source code does not need to import the plugin implementation.

**Approach 2 — Passing objects through a shared interface.** The child loader creates an instance implementing `Greeter`, and the host receives the instance via the interface. Afterward, the host does not need to know the implementation class name. A framework may also combine this with `ServiceLoader.load(Greeter.class, child)` to discover providers in a plugin JAR that contains an appropriate service descriptor.

**Thread Context ClassLoader (TCCL)** is also a mechanism for *selecting a lookup loader* by context. A library defined by a parent loader can query:

~~~java
ClassLoader lookup = Thread.currentThread().getContextClassLoader();
~~~

If a framework sets the TCCL to the child loader, the library can use that loader to find classes/resources belonging to the plugin. However, **TCCL does not modify the parent relationship** and does not turn `parent.loadClass(...)` into a search of the child. It only allows code to explicitly choose a different loader. When setting the TCCL temporarily, it must be restored in a `finally` block to avoid affecting other tasks on the same thread.

## 9. Exceptions and Limitations of the Model

### 9.1. Child-First Loader

Some plugin frameworks or application servers implement a **child-first** strategy: checking the child's own sources first before asking the parent (typically still making exceptions for core JDK classes). This changes the **priority** when both parent and child contain the same class name; it does not eliminate the runtime type identity requirement.

Child-first can allow a plugin to use its own version of a library dependency, but it can also easily lead to `ClassCastException`, `LinkageError`, or `ServiceConfigurationError` if the plugin also defines the API that the host is using.

### 9.2. JPMS and Module Layers

Modules have **readability**, `exports`, and `opens` rules in addition to loader relationships. A ClassLoader can be associated with named modules; resolving classes across modules does not always follow a simple “strictly parent-first then child” diagram.

In particular, within a `ModuleLayer`, the same class name in different modules or loaders may be subject to distinct constraints. To determine whether code can access a class, examine both the loader **and** module readability/exports.

### 9.3. Bootstrap and the `null` Loader

`Class.getClassLoader() == null` usually means the class was defined by the **bootstrap loader**, not that the class “was not loaded”. The bootstrap loader is typically the final ancestor when a child loader uses parent-first delegation. A loader whose parent is `null` does not automatically see the entire application classpath.

### 9.4. Class Visibility Is Not a Security Boundary

A ClassLoader separates namespaces and class lookup sources; it is **not a sandbox** for untrusted plugins. A plugin running in the same JVM can execute code with the privileges of the host process. If system access isolation is needed, use process/container boundaries and appropriate control mechanisms.

## 10. Common Pitfalls When Reasoning About Visibility

| Observation | Common Misconception | Correct Analysis |
|---|---|---|
| `child.loadClass("demo.api.Greeter")` succeeds | “This class was defined by the child” | The parent itself may have defined the class, and the child only delegated |
| `parent.loadClass("demo.plugin.HelloGreeter")` fails | “The host cannot use the plugin” | The host can hold a reference to the child and call `child.loadClass`, or receive the plugin via an API |
| Child has its own `Greeter.class` file, yet the host cast fails | “Same FQCN means the same class” | If two loaders actually each define their own copy, the runtime types differ |
| `child.getResource(...)` returns a parent resource | “The resource was copied into the child” | Parent-first resource lookup can return a URL belonging to the parent |
| Two children point to the same JAR, yet the classes differ | “The JVM loaded the same file incorrectly” | Identity consists of the class name **and the defining loader** |
| Class is found, yet member access fails | “Finding the class means having full access” | Java access control, runtime packages, and JPMS still apply |
| `ServiceLoader` cannot find the plugin | “The parent should automatically find providers in the child” | Pass the plugin loader explicitly or configure the TCCL properly |
| `ClassNotFoundException` and `NoClassDefFoundError` are conflated | “Both just mean the class file does not exist” | `ClassNotFoundException` usually comes from a lookup-by-name request; `NoClassDefFoundError` can occur during runtime linking/dependency resolution |
| Plugin dependency shares a library name with the host | “The child always picks up its own library” | Parent-first usually prefers the parent's version; child-first can reverse the priority and cause conflicts |

## 11. Plugin Design Guidelines Based on Visibility

1. **Place the API contract:** Interfaces/DTOs used for exchanging data between host and plugin should be defined by a shared loader, typically the host's loader.
2. **Choose the parent intentionally:** If the plugin needs to call the host API, use `SomeHostApi.class.getClassLoader()` as the parent (or a loader proven to see that API). Choosing the platform loader will typically **not** see the host application's classpath.
3. **Keep implementations in separate sources:** Plugin implementations and their private dependencies should reside in the child JAR URLs; avoid accidentally placing them on the host classpath when you want the child to define them.
4. **Verify by true identity:** Compare `SomeClass.class.getClassLoader()`, `loaderA == loaderB`, and `Class<?> == Class<?>` instead of only looking at package names or printing hash codes.
5. **Manage lifecycle:** `URLClassLoader.close()` closes resource sources, though it does not force the JVM to immediately unload classes. Releasing an old loader requires clearing references to its classes/objects/loader, threads, callbacks, caches, and related plugin resources.
6. **Diagnose resources as well:** When using `ServiceLoader`, check `META-INF/services/...` and the lookup loader. When using JPMS, also check the module configuration.

## 12. Practice Questions

**Question 1.** The parent defines `com.app.Api`, and the child defines `com.plugin.Impl implements Api`. Calling `child.loadClass("com.app.Api")` returns a class defined by which loader?

**Answer:** Typically the class defined by the **parent**, provided the child follows parent-first delegation and the parent sees the API. Using `child.loadClass` does not change the defining loader.

**Question 2.** Why does `parent.loadClass("com.plugin.Impl")` throw `ClassNotFoundException`, yet the host can still create an `Impl` instance?

**Answer:** The parent does not search downward into the child's own classes. The host can call **`child.loadClass("com.plugin.Impl")`**, then instantiate it via reflection and cast it to the shared interface defined by the parent.

**Question 3.** Two different `URLClassLoader` instances read the same JAR and both load a class with FQCN `com.plugin.Impl`. Are the two `Class<?>` results equal under `==`?

**Answer:** **No**, if each loader actually defines the class itself. They are two different runtime types. If the class is defined by the parent and both children merely delegate, they can be **equal**.

**Question 4.** Does setting the TCCL to the child change `parent.loadClass(...)` so that it automatically searches from the child?

**Answer:** **No.** The TCCL is simply a loader reference held by the thread for calling code to use explicitly. It does not reverse the delegation direction of `parent.loadClass`.

**Question 5.** Can a plugin with the same package name as a host class automatically read package-private members of the host class?

**Answer:** Not automatically. Two classes defined by different loaders belong to **different runtime packages**; module constraints and access permissions must also be considered.

## 13. Official Documentation

- [Java SE 17 — ClassLoader: delegation, loadClass, getResource](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [Java SE 17 — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html)
- [Java SE 17 — Class.getClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getClassLoader())
- [Java SE 17 — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html)
- [Java Virtual Machine Specification 17 — Loading, Linking, and Initializing](https://docs.oracle.com/en/java/javase/specs/jvms/se17/html/jvms-5.html)

**Remember:** With parent-first delegation, **a child loader can ask its parent to find a class, but the parent does not automatically search down into the child**. The child shares the API defined by the parent while still defining its own implementation from its own JAR; runtime class identity depends on **class name + defining loader**.
