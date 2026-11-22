# Why Doesn't a Parent Loader Automatically Find a Child Loader's Dependencies?

## 1. The Core Problem: Parent–Child Relationship Does Not Create Bidirectional Visibility

In the standard Java class-loading mechanism, when a **child class loader** needs a class, it usually asks its **parent class loader** first. Only if the parent cannot find it does the child try searching in its own bytecode sources. This is **parent-first delegation**.

The reverse direction **does not happen automatically**: when a class defined by the parent needs a dependent type, the JVM uses the class-loading context of that parent class itself to resolve the type. The JVM does not search across all child loaders that might exist. Therefore:

> **A child can usually see the parent's classes through delegation; a parent cannot by default see classes provided only by a child.**

A common example is a framework residing on the application classpath while a plugin is loaded from a separate directory/JAR using a child `URLClassLoader`. The framework may know about a shared interface `PluginApi`, but if the framework directly calls a concrete class located only in the plugin JAR, the parent loader usually cannot find it. This remains true even when the plugin has already been successfully loaded by the child loader.

**Do not confuse two issues:**

1. **Visibility / lookup:** can the queried loader find and define/obtain the class by its binary name?
2. **Type identity / linkage:** if the class can be loaded, which class is actually defined by which loader, and is that type compatible across call boundaries?

To explain why a parent does not automatically find a child's dependencies, we must first understand the **lookup direction** and the **loader used by the JVM when resolving references from bytecode**.

## 2. Delegation Direction and the Parent's Limits
By default, `ClassLoader.loadClass` follows the sequence `findLoadedClass` → parent/bootstrap → child's `findClass`. The child relies on the parent to find shared APIs; the parent does not automatically maintain a list of all children, so `parent.loadClass("plugin.Helper")` cannot look into the child's private sources unless the parent has been configured with another lookup path.
```text
Child → Parent: can return the parent's Class
Parent → Child: no default reverse-delegation edge
```
Note that parent-first is the default policy; not every custom loader or JPMS-associated loader is required to use the exact same algorithm. More importantly, as §3 explains, **the bytecode of a parent class still uses the parent class's defining loader when resolving dependencies**, even when the child is the caller.

## 3. The Crucial Point: A Class's Dependencies Are Resolved by Its Defining Loader

Suppose the bytecode of class `Host` contains the statement:

~~~java
return plugin.Helper.message();
~~~

The symbolic reference in `Host`'s constant pool contains the type name `plugin.Helper` and the member information for `message`. When the JVM needs to resolve that reference, it uses the **defining loader of the class containing the reference**—that is, the loader that defined `Host`—to initiate loading the referenced type. It does not automatically use:

- The loader of whatever object happens to call the `Host` method.
- The thread context class loader, unless Java code/framework explicitly uses the API to read that value.
- A child loader that has loaded a class with the same name elsewhere.
- The “newest loader” or “nearest loader” appearing in the stack trace.

This is a key rule in **JVMS §5.3 and §5.4.3**: resolution is tied to the class containing the symbolic reference. If `Host` belongs to the parent, then resolving `plugin.Helper` is initiated by the parent; when the parent lacks this source and has no suitable delegation path, it fails. A child may already have loaded `plugin.Helper`, but that **does not automatically add the class to the parent's search space**.

Changing the call to `child.loadClass("Host")` does not help either: if delegation returns the `Host` defined by the parent, dependencies in `Host`'s bytecode still use `Host`'s loader.

### Defining Loader Differs from Initiating Loader

- **Defining loader:** the loader that actually defines a class or interface from its representation. The runtime type identity of a class or interface depends on **binary name + defining loader**.
- **Initiating loader:** a loader recorded by the JVM as participating in initiating the loading of a type. A child can be an initiating loader for a class defined by the parent when delegation succeeds.
- `SomeType.class.getClassLoader()` reports the **defining loader** of an ordinary class or interface, not necessarily the loader directly used by the caller.
- The failure of `parent.loadClass("plugin.Helper")` does not prove that `plugin.Helper` does not exist anywhere in the JVM; it only proves that this loader and its lookup policy could not find the requested type.

This also explains why a Java class may already have been loaded by a child yet a call on the parent side still encounters `ClassNotFoundException` or `NoClassDefFoundError`.

## 4. Runnable Experiment: Parent Cannot Find a Child-Only Dependency

The experiment uses two output directories to create **two separate classpath sources**. `Host` and `Demo` run from the application classpath. `Plugin` and `Helper` reside only in the directory read by the child `URLClassLoader`. During **compilation**, `Host` is given `Helper` on the compile classpath; at **runtime**, the plugin directory is not on the application classpath. This is intentional to simulate the scenario where the dependency is visible at compile time but invisible to the parent at runtime.

Source file structure:

~~~text
example/
├── app/
│   ├── Host.java
│   └── Demo.java
└── plugin/
    └── child/
        ├── Helper.java
        └── Plugin.java
~~~

### File `plugin/child/Helper.java`

~~~java
package child;

public class Helper {
    public static String message() {
        return "helper ready";
    }
}
~~~

### File `plugin/child/Plugin.java`

~~~java
package child;

public class Plugin {
    public static String run() {
        return Helper.message();
    }
}
~~~

`Plugin` and `Helper` both belong to the child's private bytecode source.

### File `app/Host.java`

~~~java
public class Host {
    public static String callChildDependency() {
        return child.Helper.message();
    }
}
~~~

`Host` is defined by the application/system loader at runtime. Although it compiles successfully, it still needs to resolve `child.Helper` when `callChildDependency()` is invoked.

### File `app/Demo.java`

~~~java
import java.lang.reflect.Method;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class Demo {
    public static void main(String[] args) throws Exception {
        ClassLoader parent = Demo.class.getClassLoader();

        try {
            parent.loadClass("child.Helper");
            System.out.println("parent unexpectedly found Helper");
        } catch (ClassNotFoundException expected) {
            System.out.println("parent: ClassNotFoundException");
        }

        try {
            System.out.println("Host: " + Host.callChildDependency());
        } catch (NoClassDefFoundError expected) {
            System.out.println("Host: NoClassDefFoundError");
        }

        URL pluginUrl = Path.of(args[0]).toUri().toURL();
        try (URLClassLoader child =
                     new URLClassLoader(new URL[]{pluginUrl}, parent)) {
            Class<?> plugin = child.loadClass("child.Plugin");
            System.out.println("Plugin defined by child: "
                    + (plugin.getClassLoader() == child));

            Method run = plugin.getMethod("run");
            System.out.println("Plugin: " + run.invoke(null));

            System.out.println("Host via child is parent class: "
                    + (child.loadClass("Host") == Host.class));

            try {
                Host.callChildDependency();
                System.out.println("Host unexpectedly resolved Helper");
            } catch (NoClassDefFoundError expected) {
                System.out.println("Host still: NoClassDefFoundError");
            }
        }
    }
}
~~~

### Compiling and Running on Linux/macOS (Bash)

From inside the `example/` directory, using JDK 17 or later:

~~~bash
mkdir -p out/plugin out/app
javac -d out/plugin plugin/child/Helper.java plugin/child/Plugin.java
javac -cp out/plugin -d out/app app/Host.java app/Demo.java
java -cp out/app Demo out/plugin
~~~

These commands **intentionally omit** `out/plugin` from the runtime `-cp`. It is used only as the compile classpath for `Host` or as the dedicated URL for the child loader. On Windows, you can create the two directories with `mkdir out\plugin` and `mkdir out\app` in PowerShell, then run the same `javac`/`java` commands with the appropriate path separators.

### Verified Stdout

~~~text
parent: ClassNotFoundException
Host: NoClassDefFoundError
Plugin defined by child: true
Plugin: helper ready
Host via child is parent class: true
Host still: NoClassDefFoundError
~~~

### Line-by-Line Analysis

1. `parent.loadClass("child.Helper")` checks the sources visible to the parent; `out/plugin` is not on the parent's runtime classpath, so it throws `ClassNotFoundException`.
2. `Host.callChildDependency()` executes bytecode referencing `child.Helper`. The JVM resolves the dependency in the context of `Host`'s defining loader, which is the parent; when that fails, the linking step requiring this class throws `NoClassDefFoundError` (with a cause related to not finding the class).
3. The child `URLClassLoader` finds `child.Plugin` from `out/plugin` because the parent does not have it, so `plugin.getClassLoader() == child` is `true`.
4. `Plugin.run()` calls `Helper.message()`. `Plugin` is defined by the child; when resolving `Helper`, the child finds the class file in the same source, so it prints `helper ready`.
5. When `child.loadClass("Host")` is called, the child asks the parent and receives `Host.class`; it does not create a duplicate `Host`. Therefore, the comparison result is `true`.
6. Calling `Host.callChildDependency()` once more still does not cause the parent to redirect to the child. The error persists; the fact that the plugin has been loaded by the child does not transfer the defining/resolution scope for `Host`'s dependencies.

**What the experiment proves:** the parent does not automatically find the child's private classes, and dependency lookup in parent code does not change based on the caller's loader. If you run the wrong command and add `out/plugin` to `java -cp`, the parent will find `Helper` from the start, invalidating the experiment's condition.

## 5. Why Doesn't the JVM Automatically Scan All Child Loaders?

### 5.1. There Is No Standard Children Graph to Traverse

A `ClassLoader` is constructed with a reference to its parent. The reverse direction is not a required standard registry. An application can create, discard, and replace many child loaders for plugin isolation, testing, hot reload, or multiple library versions.

The parent would not know which child to pick if there are:

~~~text
           Parent
        /    |     \
   Child A Child B Child C
   Helper v1 Helper v2 (no Helper)
~~~

If the parent scanned automatically, the question “which version of `Helper`?” would become ambiguous. The parent-first policy and defining-loader context make behavior explainable through a deterministic lookup path rather than depending on execution order or whichever loaders happen to remain alive.

### 5.2. Preserving Isolation and Type Identity

Two different children can both define `plugin.Helper` from different bytecode. The JVM treats them as **two distinct runtime types** because their defining loaders differ. The parent cannot arbitrarily pick one of the two and still guarantee that every call is linked in a type-safe manner.

Even when the name and source look identical, casting between two classes with the same binary name defined by different loaders can fail. For APIs that communicate between parent and child, the classes/interfaces belonging to the shared contract should be defined in a common loader (typically the parent) so that both sides share the same type identity.

### 5.3. Preventing Parent Library Classes from Arbitrarily Depending on Child Plugins

If the parent automatically loaded everything from children, frameworks and shared libraries could hardly guarantee independence: one plugin could alter class lookup results for another plugin, or cause the framework to accidentally receive a class outside its intended design scope. Default parent-first delegation supports sharing stable APIs and encapsulating private dependencies inside each child.

This is a **mechanism for organizing namespaces and resolving types**, not an absolute security sandbox boundary. Using a custom class loader does not by itself make untrusted bytecode safe.

## 6. Distinguishing Commonly Confused Scenarios

| Scenario | Does the parent see the child's class? | Reason |
| --- | --- | --- |
| `child.loadClass("api.Contract")`, `Contract` is in the parent | No need for parent to see child | The child delegates up to the parent and receives the shared class. |
| `parent.loadClass("plugin.Helper")`, `Helper` is only in the child | Usually no | The parent does not automatically query children. |
| Parent-defined class `Host` directly references `plugin.Helper` | Usually no | Resolution from `Host` starts with `Host`'s defining loader. |
| Child calls the parent's `Host.doWork()` method, and `Host` references the plugin | Not automatically | The caller's loader does not replace the loader associated with `Host`. |
| `child.loadClass("Host")` returns the parent's class | Still the parent's class | Delegation does not create a new copy of the class. |
| The app places the plugin JAR onto the parent's own runtime classpath | Possible | At that point the dependency is already in the parent's source; the child isolation example no longer holds. |
| The parent explicitly calls `Class.forName("plugin.Helper", false, child)` | Can find it | This **explicitly specifies the child** in the API, unlike automatic lookup through parent-first delegation. |
| Framework uses the thread context class loader to look up the plugin | Possible | Only when the code/framework **actually uses** the context loader; the JVM does not automatically use TCCL for every resolution. |
| A custom parent specifically programmed to query the child | Possible, by design | This is custom lookup/reverse delegation, not the default behavior of `ClassLoader`. |

**Do not equate `ClassNotFoundException` and `NoClassDefFoundError`:** calling `ClassLoader.loadClass` directly typically throws `ClassNotFoundException` when a class cannot be found. When the JVM resolves a symbolic reference requiring a class that cannot be loaded, code using that class may encounter `NoClassDefFoundError`. The message and cause help pinpoint where the failure occurred. In addition, `NoClassDefFoundError` can have other causes (for example, class initialization previously failed).

## 7. Proper Design When the Framework Is in the Parent and Plugins Are in the Child

### 7.1. Place the Communication Contract in the Parent

Suppose the framework defines:

~~~java
package api;

public interface Plugin {
    String execute();
}
~~~

A plugin defined by the child can be written as:

~~~java
package plugin;

import api.Plugin;

public class GreetingPlugin implements Plugin {
    @Override
    public String execute() {
        return "Hello from plugin";
    }
}
~~~

The two code snippets are **two separate files**, named `api/Plugin.java` and `plugin/GreetingPlugin.java` respectively. They merely illustrate the interface placed in the parent and its implementation in the child; they are not a standalone program like the example in Section 4.

The child loader delegates loading `api.Plugin` to the parent. The framework can load the implementation class using the child loader and cast it to the shared `api.Plugin`:

~~~java
Class<?> implementation = Class.forName("plugin.GreetingPlugin", true, childLoader);
api.Plugin plugin =
        (api.Plugin) implementation.getDeclaredConstructor().newInstance();
String result = plugin.execute();
~~~

This snippet lives inside the framework where the `childLoader` variable and the shared API already exist. At runtime, the implementation class exists in the child's private source, its constructor is accessible, and `api.Plugin` has only one shared defining loader. This is how to integrate via an interface instead of having the parent hard-code a class that exists only in the child.

**Common pitfall:** bundling a duplicate copy of `api.Plugin` inside the plugin JAR and using child-first delegation to define a second copy. Even though the name `api.Plugin` is the same, two distinct `Class` objects can cause a `ClassCastException` or a loading constraint error. For shared APIs, strive to design the system so that the plugin **delegates to a single copy of the API**.

### 7.2. Use an Explicitly Passed Loader to Load Plugins

When a specific class in the child is needed, the parent can receive a `ClassLoader` from the plugin manager component and call:

~~~java
Class<?> pluginType = Class.forName(
        "plugin.GreetingPlugin", true, pluginLoader);
~~~

Here, **application code explicitly** chooses the loader; it does not alter the bytecode rule in a parent class that statically references `plugin.Helper`. Merely calling `Class.forName` in one place does not cause all other references in the parent to automatically switch to the child.

When implementing a plugin manager, manage the lifecycle of `URLClassLoader`, close the loader when it is no longer in use, and avoid retaining references to plugin `Class`/object/loader instances if you want memory to be reclaimable. Closing URLClassLoader only releases its own resources; it does not directly “unload” all classes if live references remain.

### 7.3. Service Provider Interface and Thread Context ClassLoader

A library in the parent sometimes needs to locate an implementation residing in a child application or plugin. The library may **deliberately use** the *thread context class loader* (TCCL):

~~~java
ClassLoader contextLoader =
        Thread.currentThread().getContextClassLoader();
~~~

APIs such as `ServiceLoader.load(service)` use the running thread's context class loader by default. With a service API in the parent and a provider in the child, the caller or framework can configure the TCCL or call `ServiceLoader.load(service, childLoader)` to select the provider discovery scope. This also depends on service metadata configuration, module/provider accessibility, and matching interface identity between both sides.

**TCCL is not a global override of the parent-first rule:** the JVM does not automatically fetch the TCCL when resolving every symbolic reference. Only APIs or libraries that explicitly retrieve and use it can change where classes are searched. TCCL is also per-thread state, so if temporarily changed it must be restored in a `finally` block:

~~~java
Thread current = Thread.currentThread();
ClassLoader previous = current.getContextClassLoader();
try {
    current.setContextClassLoader(pluginLoader);
    // Call the framework/API whose contract uses the context loader.
} finally {
    current.setContextClassLoader(previous);
}
~~~

This snippet assumes `pluginLoader` was created elsewhere; it illustrates how to preserve the thread's state after the call.

### 7.4. When Is Child-First or Reverse Delegation Needed?

Some container/module/plugin systems define their own class-loading policies, such as prioritizing a plugin's libraries over the host's versions. In such cases `loadClass` can be overridden, provided you preserve synchronization via `getClassLoadingLock(name)`, check `findLoadedClass`, invoke `resolveClass` at the appropriate time, and protect core platform APIs and shared types from duplicate definitions.

Child-first allows **the child to search its own sources first** before checking the parent; it **does not make the parent automatically aware of its children**. If the parent needs to locate a child's implementation, you must design a registry, SPI, loader-parameterized loading API, or explicit communication mechanism. Do not modify a JDK parent class loader to scan across all child class loaders.

## 8. Common Pitfalls When Debugging

1. **Compilation succeeds but runtime fails:** the compiler may see the dependency via the compile classpath, while the loader of the class containing the reference cannot see it at runtime. Inspect the *compile classpath*, *runtime classpath*, and the child's private URLs; they do not necessarily match.
2. **Confusing the parent's classpath with the child's sources:** placing a JAR in a plugin directory does not automatically add it to the system loader. If only the child holds the URL to that JAR, only the child has the mechanism to search within that URL.
3. **Guessing the loader from a stack trace:** a parent method called from a plugin does not change that method's defining loader. Check `Host.class.getClassLoader()` and `PluginImpl.class.getClassLoader()`.
4. **Confusing “loaded somewhere” with “visible to every loader”:** there is no JVM-wide table guaranteeing that every loader returns the same `Class<?>` just because the name matches.
5. **Assuming `Thread.currentThread().setContextClassLoader(child)` fixes everything:** bytecode resolution in `Host` still uses the loader associated with `Host`. TCCL only helps in APIs/frameworks that explicitly use it.
6. **Loading a duplicate copy of a shared API in the child:** two copies of `api.Plugin` with the same name but different defining loaders are not guaranteed to be castable to one another. Share APIs through the parent.
7. **Catching the wrong exception:** `ClassNotFoundException` is a checked exception from explicit lookup; failures during JVM resolution may produce `NoClassDefFoundError`. Inspect `getCause()` and the cause chain.
8. **Assuming every JDK loader forms a strict parent-first tree:** since Java 9, the module system introduces exceptions and more complex delegation mechanisms. Analyze each loader and its policy rather than overgeneralizing.

### Quick Diagnostic Checklist

When a class resides only in a child plugin and the parent cannot find it, answer these questions in order:

- Which class contains the symbolic reference to the dependency, and what is `ThatClass.class.getClassLoader()`?
- Is the dependency present in a source/JAR that **that loader** can search?
- Which child loader holds the dependency? Is there any name/version overlap with the parent or a sibling?
- Does the framework provide an SPI/loader argument/TCCL contract to locate the implementation without a direct static reference?
- Is the shared API uniquely defined by the parent?
- Did the exception occur during a direct `loadClass` call or during JVM linking/resolution/initialization?

## 9. Self-Check Questions

**Scenario A:** A child-defined `Plugin` calls a child-defined `PluginHelper`. The child asks the parent, the parent does not have it, and the child's `findClass` succeeds. Why does this work?

**Answer:** Because resolution in `Plugin` is initiated by `Plugin`'s own defining loader; the child is the loader that has the source for `PluginHelper`, so it finds it after the parent fails to.

**Scenario B:** `Host` is defined by the parent, and a child calls `Host.invoke()`. Inside `Host.invoke()`, there is a direct reference to `PluginHelper`, which exists only in the child. Does the JVM use the child to resolve `Host`'s dependency?

**Answer:** Not under default class loading. Dependencies in `Host`'s bytecode are resolved using `Host`'s defining loader, which is the parent. The call direction of a method does not change the defining loader of `Host`.

**Scenario C:** Is it possible for the framework to find a plugin's provider without adding the entire plugin JAR to the parent?

**Answer:** Yes. Place the shared interface in the parent, have the child load the implementation, and use an explicit loader/SPI/TCCL in APIs designed to support them. The child only needs visibility to the parent API and its own implementation source.

## Authoritative References

- [Java SE 21 – ClassLoader: parent delegation, loadClass, and findClass](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html).
- [JVM Specification Java SE 21, §5.3 – Loading, Defining, and Initiating Loader](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3).
- [JVM Specification Java SE 21, §5.4.3 – Resolution](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.4.3).
- [Java SE 21 – ServiceLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html): choosing a class loader for provider lookup.
- [Java SE 21 – Thread.getContextClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html#getContextClassLoader()): thread context loader for frameworks and tooling.
