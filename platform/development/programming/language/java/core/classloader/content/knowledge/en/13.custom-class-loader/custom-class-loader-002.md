# Choosing the constructor, parent, and loader name when building a custom ClassLoader

## 1. Three decisions when creating a custom class loader

A *custom class loader* can read class bytes from a JAR, a dedicated directory, plugin resources, the network, or a program-managed source. Before writing how to find classes, determine **three distinct things**:

1. **Which constructor should be used to instantiate the class loader object?** In Java 17, `ClassLoader` has a default constructor, a constructor taking a parent, and a constructor taking a name plus a parent.
2. **Which loader is the parent during delegation?** This affects the classes and resources visible to the custom loader, shared API boundaries, plugin isolation capabilities, and the risk of duplicate runtime types.
3. **Which loader name will appear during diagnostics?** A name helps humans distinguish loaders, but it does not replace object identity and does not by itself change the parent or bytecode lookup.

It is important to distinguish: **creating a ClassLoader object does not mean creating a new Java class**. If the subclass does not implement logic to find/define new classes, it may simply delegate to the parent without defining any application classes itself.

A common sensible choice:

```java
public final class PluginClassLoader extends ClassLoader {
    public PluginClassLoader(String pluginId, ClassLoader apiParent) {
        super("plugin:" + pluginId, apiParent);
    }
}
```

This is a minimal subclass illustrating how to choose the **name** and **parent**. It does not read a plugin JAR yet; to load its own bytecode, an appropriate mechanism is still needed, such as overriding `findClass` or using a loader capable of reading the specified class source.

## 2. ClassLoader constructors in Java 17

`java.lang.ClassLoader` provides the following three `protected` constructors:

| Constructor | Parent | Loader name | Scenario |
|---|---|---|---|
| `ClassLoader()` | `ClassLoader.getSystemClassLoader()` | Unnamed (`getName() == null`) | Simple loader that wants to delegate through the system loader by default |
| `ClassLoader(ClassLoader parent)` | The passed `parent` itself | Unnamed (`getName() == null`) | Need to choose an explicit parent without needing a label |
| `ClassLoader(String name, ClassLoader parent)` | The passed `parent` itself | `name`, or `null` if unnamed | Plugin/module loader that wants both a parent and an easily traceable name |

Points to remember:

- `protected` means the constructors are invoked from a subclass via `super(...)`, rather than calling `new ClassLoader()` directly in application code outside an appropriate scope.
- The no-argument constructor actually uses the **system class loader** as its parent according to the JDK 17 contract; it does not choose “the caller class's loader” or the current thread's TCCL.
- `parent == null` in the two/three-parameter constructor indicates that the parent is the **bootstrap class loader** in the default delegation mechanism. It does **not** create a new bootstrap loader object.
- For the constructor with `name`, `null` is accepted to create an unnamed loader; **the empty string `""` is not allowed** and causes an `IllegalArgumentException`.
- The named constructor was introduced in **Java 9**, so it works on Java 17 but does not exist on Java 8.

### Valid subclass template

```java
public final class DemoLoader extends ClassLoader {
    public DemoLoader() {
        super();
    }

    public DemoLoader(ClassLoader parent) {
        super(parent);
    }

    public DemoLoader(String name, ClassLoader parent) {
        super(name, parent);
    }
}
```

This is a valid standalone class if saved in the file `DemoLoader.java`. In Java 17, the superclass constructor call using `super(...)` must appear first in the corresponding constructor. If `super()` is omitted in the no-argument constructor, the Java compiler inserts an implicit `super()` call.

**Constructors only configure the loader object.** The `DemoLoader` class above does not override `findClass`, so it does not yet have its own mechanism to read a new JAR.

## 3. What is a parent in class loading?

`ClassLoader` typically uses **parent delegation** when asked to load a class. With the default `ClassLoader.loadClass(String, boolean)`:

1. Call `findLoadedClass(name)` to check whether the class has already been recorded by the JVM for this loader.
2. If not, try asking `parent.loadClass(name)`. If the parent is `null`, try using the **bootstrap loader**.
3. If the parent/bootstrap does not provide the class, call `findClass(name)` on the current loader.
4. If resolution is requested, call `resolveClass` according to the contract and then return `Class<?>`.

Conceptual model:

```text
custom.loadClass("com.example.Service")
              |
              v
 Already loaded via this loader?
        | yes                 | no
        v                     v
Use existing Class<?>    Parent delegation
                               |
                  +------------+-----------+
                  | found                  | not found
                  v                        v
            Use parent's             custom.findClass
              Class<?>                     |
                                  Find/define itself
                                       or fail
```

**Parent is not synonymous with a Java superclass.** A class loader can have a `parent` that is a loader object of another class regardless of the Java inheritance relationship between the two class loader implementations.

**Parent is not synonymous with the defining loader of the custom loader class itself.** For example, `PluginClassLoader.class` may be defined by the application loader, whereas the object `new PluginClassLoader(..., platformLoader)` created by the app has `getParent() == platformLoader`. These two properties refer to two different things.

### When the parent finds the class

If the parent returns a `Class<?>`, the custom loader uses that class; **it does not create another class with the same name itself**.

```java
ClassLoader app = MainApp.class.getClassLoader();
ClassLoader child = new ClassLoader(app) { };

Class<?> c = child.loadClass("MainApp");
```

This snippet illustrates a case requiring an existing `MainApp` class. If `MainApp` is defined by the app loader, `c == MainApp.class` is true, while `c.getClassLoader() == child` is false. **The initiating loader and the defining loader can be different**.

### When the parent does not find the class

The current loader is allowed to use `findClass` to locate the class from its own source. However, if the subclass does not override `findClass`, the default implementation throws `ClassNotFoundException`.

Therefore:

```java
ClassLoader isolated = new ClassLoader(null) { };
isolated.loadClass("java.lang.String"); // usually succeeds via bootstrap
isolated.loadClass("MyApplication");    // usually fails if it cannot find it itself
```

The snippet above illustrates behavior on JDK 17 running on a standard class path, with `MyApplication` simply being an application class. The second call can throw a checked exception, so it needs to be handled in a real program.

## 4. Which parent should be chosen for each need?

On JDK 17, the commonly encountered loader layers are bootstrap, platform, and application/system. However, custom loaders can be organized according to many different models.

| Selected parent | Typical capabilities | Points of caution |
|---|---|---|
| `null` | Delegation to bootstrap in the default algorithm | Does not guarantee visibility of all platform classes and app classes; must provide `findClass` logic for its own classes |
| `ClassLoader.getPlatformClassLoader()` | Can access visible platform classes | Does not automatically see all classes located on the application class path |
| `ClassLoader.getSystemClassLoader()` | In a typical app class path, sees the application's APIs/classes | Does not automatically see classes/plugins loaded by another custom loader |
| `SharedApi.class.getClassLoader()` | Uses the same loader that can see the shared API types | Must verify that implementation/plugin classes are provided by a separate finder; avoid duplicating the shared API |
| Another plugin loader | Can delegate to a specialized loader if required by the design | Consider lifecycle, dependency graph, visibility, and the risk of deadlock |

Choosing the right `parent` means choosing **lookup constraints and type sharing**. There is no fixed choice that always fits every application.

### A null parent does not mean “cannot see Java core”

When `parent == null`, the default `ClassLoader.loadClass` uses the bootstrap loader in the delegation step. Therefore, `java.lang.Object` and `java.lang.String` can normally still be loaded.

However, on JDK 17, **not every Java platform class is defined by bootstrap**. Modules and built-in loaders are partitioned appropriately for the runtime. The Java SE 17 constructor documentation warns clearly: when the parent is `null`, **there is no guarantee that all platform classes are visible**.

You should not choose a null parent merely because you want “complete isolation” or “complete safety”: that loader still uses the core runtime, and class loading is not a complete security sandbox.

### Is the system loader suitable as a parent for plugins?

Sometimes it is suitable, if the plugin needs to share interfaces/DTOs defined by the app loader. However, with an application server, module layer, OSGi-like container, or plugin framework, the system loader is not necessarily the loader that holds the required shared API.

A more reliable approach: find the loader that **defines the shared contract**, such as `PluginApi.class.getClassLoader()`, and use it as the parent if the architecture expects it. In case the API class is defined by bootstrap, `getClassLoader()` may return `null`, so you need to understand the semantics of the target constructor.

## 5. What is the loader name used for?

Since Java 9, the constructor:

```java
super("plugin:billing", parent);
```

allows attaching a name to a loader. It can be read via:

```java
String name = loader.getName();
```

The name is used to **identify** the loader in tools, logs, diagnostics, or when printing configuration information.

Things a name **cannot do**:

- It does not determine the binary name or runtime identity of a class.
- It does not change parent delegation or the class lookup order.
- It does not specify the JAR path, directory, or module.
- It does not guarantee uniqueness; two loader objects can have the same name.
- It does not turn a loader into the bootstrap, platform, or system loader.
- It does not automatically name classes or threads.

Example:

```java
ClassLoader app = MyApp.class.getClassLoader();
DemoLoader a = new DemoLoader("plugins", app);
DemoLoader b = new DemoLoader("plugins", app);

boolean sameName = a.getName().equals(b.getName());
boolean sameObject = a == b;
```

This snippet illustrates a case requiring the two classes `MyApp`/`DemoLoader`. `sameName` is true, while `sameObject` is false. **Having the same name does not mean two loaders are the same**.

### Practical naming rules

A useful name usually includes the function and a **non-sensitive** identifier:

- `plugin:invoice`
- `tenant-loader:west`
- `module:reporting`
- `reload:inventory:v2`

Do not include passwords, tokens, private paths, or secrets in the loader name because diagnostic tools may display that name. A name is human-readable, but **it is not a security boundary**.

When you need to distinguish between hot reload cycles, you can use a version label or a non-sensitive internal run ID, but do not rely on the label to determine runtime class identity; compare loader objects or `Class<?>` instead.

### Null names, empty names, and getName

- `new DemoLoader(null, app)` with the named constructor produces an **unnamed** loader.
- `new DemoLoader("", app)` throws **`IllegalArgumentException`** per Java SE 17.
- `loader.getName()` returns `null` if the loader is unnamed.
- `getName()` is public and not `final` for API compatibility; if a subclass overrides it, the contract requires returning the exact name set at creation time.

The loader name must not be used instead of checking `Class.getClassLoader()` when you want to know the **defining loader**.

## 6. Java 17 example: comparing the three constructors, parent, and name

Create the file **`LoaderConstructorDemo.java`**:

```java
public class LoaderConstructorDemo {
    static class DemoLoader extends ClassLoader {
        DemoLoader() {
            super();
        }

        DemoLoader(ClassLoader parent) {
            super(parent);
        }

        DemoLoader(String name, ClassLoader parent) {
            super(name, parent);
        }
    }

    public static void main(String[] args)
            throws ClassNotFoundException {
        ClassLoader app = LoaderConstructorDemo.class.getClassLoader();
        ClassLoader system = ClassLoader.getSystemClassLoader();

        DemoLoader defaultLoader = new DemoLoader();
        DemoLoader parentLoader = new DemoLoader(app);
        DemoLoader namedA = new DemoLoader("plugin:orders", app);
        DemoLoader namedB = new DemoLoader("plugin:orders", app);
        DemoLoader bootstrapChild = new DemoLoader("isolated", null);

        System.out.println("Default parent is system: "
                + (defaultLoader.getParent() == system));

        System.out.println("Explicit parent is app: "
                + (parentLoader.getParent() == app));

        System.out.println("No-arg name is null: "
                + (defaultLoader.getName() == null));

        System.out.println("Parent-only name is null: "
                + (parentLoader.getName() == null));

        System.out.println("Named loader: " + namedA.getName());

        System.out.println("Same name: "
                + namedA.getName().equals(namedB.getName()));

        System.out.println("Different loader objects: "
                + (namedA != namedB));

        System.out.println("Null parent: "
                + (bootstrapChild.getParent() == null));

        System.out.println("Bootstrap supplies String: "
                + (bootstrapChild.loadClass("java.lang.String")
                        == String.class));

        System.out.println("App parent supplies main: "
                + (parentLoader.loadClass("LoaderConstructorDemo")
                        == LoaderConstructorDemo.class));

        try {
            bootstrapChild.loadClass("LoaderConstructorDemo");
            System.out.println("Unexpected app lookup success");
        } catch (ClassNotFoundException expected) {
            System.out.println("Bootstrap-only cannot find main");
        }

        boolean rejectedEmptyName = false;
        try {
            new DemoLoader("", app);
        } catch (IllegalArgumentException expected) {
            rejectedEmptyName = true;
        }
        System.out.println("Empty name rejected: "
                + rejectedEmptyName);
    }
}
```

Run on JDK 17 in the directory containing the file:

```bash
javac LoaderConstructorDemo.java
java LoaderConstructorDemo
```

Stdout in a typical JDK 17 class path configuration:

```text
Default parent is system: true
Explicit parent is app: true
No-arg name is null: true
Parent-only name is null: true
Named loader: plugin:orders
Same name: true
Different loader objects: true
Null parent: true
Bootstrap supplies String: true
App parent supplies main: true
Bootstrap-only cannot find main
Empty name rejected: true
```

Reading the output:

1. The no-argument constructor of `ClassLoader` selects the system class loader as its parent; the constructor accepting `app` sets the app loader itself.
2. Not passing a name causes `getName()` to return `null`; the `(name,parent)` constructor assigns the name `plugin:orders`.
3. Two loader objects can share the same name yet remain two distinct objects.
4. `bootstrapChild` has a `null` parent and still finds `String` from bootstrap through the default `loadClass`; it does not read `LoaderConstructorDemo.class` from the application class path on its own.
5. `parentLoader.loadClass("LoaderConstructorDemo")` delegates to return the class **defined by the app loader**, without creating a copy itself.
6. `""` is an invalid loader name, so `IllegalArgumentException` is caught and the final result is `true`.

**Conditions of the example:** run the program on a standard class path and do not modify the loader classes/bytecode during execution. If a custom system loader is configured, the rule for the no-argument constructor is still to use the loader returned by `getSystemClassLoader()`, though the details of app visibility may differ.

## 7. When does the chosen parent affect findClass?

Many people write a subclass:

```java
public class FileBackedLoader extends ClassLoader {
    FileBackedLoader(ClassLoader parent) {
        super(parent);
    }

    @Override
    protected Class<?> findClass(String name)
            throws ClassNotFoundException {
        // Read the bytes of name from a custom class source.
        // After validation, defineClass(name, bytes, 0, bytes.length).
        throw new ClassNotFoundException(name);
    }
}
```

This is a **structural skeleton for explanation**; it is not yet a real file-reading loader and always throws `ClassNotFoundException`. The important point is that `findClass` is normally called **after the parent fails**, in the default `loadClass` algorithm.

Therefore, if the parent **already sees a class with the same name**, your `findClass` code may never run for that name. If you want an implementation to have the right to define its own namespace, you need to design the **lookup path** carefully, rather than merely renaming the loader.

### Java 17 example: parent-first prevents findClass from running when the parent finds the class

Create the file **`ParentFirstDemo.java`**:

```java
public class ParentFirstDemo {
    static class ProbeLoader extends ClassLoader {
        private int findCalls;

        ProbeLoader(String name, ClassLoader parent) {
            super(name, parent);
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            findCalls++;
            throw new ClassNotFoundException(name);
        }

        int findCalls() {
            return findCalls;
        }
    }

    public static void main(String[] args)
            throws ClassNotFoundException {
        ClassLoader app = ParentFirstDemo.class.getClassLoader();
        ProbeLoader child = new ProbeLoader("probe", app);

        Class<?> loaded = child.loadClass("ParentFirstDemo");
        System.out.println("Parent supplied main: "
                + (loaded == ParentFirstDemo.class));
        System.out.println("findClass calls after hit: "
                + child.findCalls());

        boolean missing = false;
        try {
            child.loadClass("example.never.Exists123456");
        } catch (ClassNotFoundException expected) {
            missing = true;
        }

        System.out.println("Missing class reported: " + missing);
        System.out.println("findClass calls after miss: "
                + child.findCalls());
    }
}
```

Run on a clean class path that does not contain the class `example.never.Exists123456`:

```bash
javac ParentFirstDemo.java
java ParentFirstDemo
```

Stdout:

```text
Parent supplied main: true
findClass calls after hit: 0
Missing class reported: true
findClass calls after miss: 1
```

`ParentFirstDemo` is already defined by the app loader, so the child loader receives that class back and **does not need to call `findClass`**. The class `example.never.Exists123456` does not exist in the parent; the child loader's `findClass` is tried and throws `ClassNotFoundException`. Attaching the name `probe` helps identify the loader, **without altering the parent-first algorithm**.

In a real system, prefer overriding `findClass` when you only want to provide a custom way to locate bytes. Override `loadClass` to switch from parent-first to child-first only when you have a clear architecture, control over the shared namespace, and proper synchronization handling.

## 8. Choosing a parent and shared API in a plugin application

Suppose the host application has:

```text
Host / shared API loader
    api.Plugin
    api.Request
    |
    +-- Plugin loader A
    |      plugin.AImplementation
    |
    +-- Plugin loader B
           plugin.BImplementation
```

If both plugins need to implement `api.Plugin` and receive `api.Request`, a common design is to have the plugin loaders delegate the shared `api.*` types to **the same loader that owns the API**.

If a plugin loader defines its own copy of `api.Plugin`, even though the binary name matches, it can be a **different runtime class**, leading to type casting errors or loading constraints when the host and plugin exchange types.

Choosing the right parent helps:

- Shared APIs/interfaces/DTOs have the same runtime identity.
- Plugin code can still define its own implementation and dependencies if the lookup policy allows it.
- Reduce the risk of `ClassCastException`, `LinkageError`, or an unassignable provider.
- Make lifecycle management easier: the dedicated loader can be dereferenced when the plugin stops, while the shared API loader lives alongside the host.

**However, the chosen parent does not automatically enforce the entire isolation policy.** If child-first is needed for certain packages and parent-first for `java.*`/`api.*`, you must design an appropriate lookup policy yourself and satisfy the Java/JVM constraints.

### Is a null parent better for plugins?

Not necessarily. A null-parent plugin can see bootstrap classes, **but does not automatically see the host API**. If the plugin bytecode implements `api.Plugin` owned by the host, the JVM must resolve that type. Without a shared lookup path, loading/linking can fail.

If the plugin needs to be isolated from the app while still sharing a contract, you can use a dedicated common loader as the parent or a controlled delegation mechanism, instead of setting a null parent without an API lookup strategy.

## 9. How to verify the chosen loader

When debugging, use these distinct properties:

```java
ClassLoader parent = myLoader.getParent();
String label = myLoader.getName();

Class<?> found = myLoader.loadClass("com.example.SomeClass");
ClassLoader actualOwner = found.getClassLoader();
```

This is an **illustrative** snippet requiring actual variables/classes and `ClassNotFoundException` handling. Meaning:

- `myLoader.getParent()`: the parent used for delegation.
- `myLoader.getName()`: the name for diagnostics, which may be null.
- `found.getClassLoader()`: **the defining loader of the returned runtime class**; it may differ from `myLoader` if the parent supplied the class.

A quick diagnostic table:

| Observation | Do not conclude | Correct interpretation |
|---|---|---|
| `myLoader.getName().equals(other.getName())` | The two loaders are the same | Names can collide; compare object identity |
| `myLoader.getParent() == null` | No delegation | With the default `loadClass`, delegates to bootstrap |
| `loaded.getClassLoader() != myLoader` | Lookup failed | The class may have been defined by the parent and returned by the child |
| `ClassNotFoundException` from a null-parent loader | The JVM is missing core classes | The loader may not know about app classes and does not override `findClass` |
| Loaders have different names | Their classes are definitely different | If both delegate to the parent, they can receive **the same Class<?>** |
| `findClass` is not called | The override is broken | The parent may have already returned a result first |

### Does the class loader name appear in errors and logs?

JVM tools such as class loading logs, stack traces, or diagnostics can display loader information and names. On HotSpot JDK 17, you can enable:

```bash
java -Xlog:class+load=info LoaderConstructorDemo
```

The output may contain many loaded library classes; the log format depends on the JVM/version. The name is useful for readability, but do not use the name alone as proof of which loader object defined a class. When needed, also inspect `Class.getClassLoader()` and the corresponding loader statistics tools.

## 10. Constructors and the lifecycle of a loader object

Creating `new DemoLoader(...)` only creates a **loader object**, without necessarily defining its own classes yet. In a long-running JVM:

- A loader can stay alive for a very long time if held in a static registry, thread context class loader, thread-local, listener, cache, or executor.
- Classes defined by a loader have runtime identities tied to that loader.
- To hot reload a new version of the same binary name, a **new loader** is typically created instead of trying to redefine an existing class in the old loader.
- A new loader can have the **same name** as the old loader while being a different object and potentially defining a different runtime class.
- Dropping references to a loader/plugin does not guarantee that class unloading occurs immediately; garbage collection and class unloading depend on reachability and the JVM implementation.

Therefore, the loader name should indicate the logical owner and an optional version for debugging, while **the lifecycle must be managed via object references and resource release responsibilities**, not via the name.

### Constructors alone are not enough to read a JAR

`new DemoLoader("plugin:A", appLoader)` does not make the loader understand a plugin JAR path. If using `URLClassLoader`, you must supply the URLs/parent matching a constructor supported by that loader type. With a `ClassLoader` subclass, you typically implement `findClass` to read bytes and call `defineClass` per the API; you need to handle package identity, access controls, resources, and errors.

If the loader owns closeable resources (for example `URLClassLoader`), design the lifecycle to call `close()` when appropriate and after no active tasks are still using it. `close()` does not mean the JVM immediately unloads all classes defined by the loader.

## 11. Common mistaken choices

### “Let super() choose the parent automatically because the current loader is a plugin loader”

Incorrect. `ClassLoader()` takes the **system class loader**; it does not automatically use the TCCL or the plugin class's loader. In complex environments, the default parent may not see the required shared API.

**Fix:** if you know the loader that owns the API, pass it explicitly to `super(apiLoader)` or `super(name, apiLoader)`.

### “Pass a null parent to get a loader completely independent of Java core”

Incorrect. A null parent is interpreted by the default `loadClass` as bootstrap delegation. At the same time, it does not guarantee that all platform classes are visible.

**Fix:** design isolation intentionally, ensuring shared runtime/API types are resolved properly.

### “The loader name is a unique key to identify classes”

Incorrect. Two loader objects can have the same name. JVM class identity is based on the binary name plus the **defining loader**, not `getName()`.

**Fix:** store the loader object/reference, and when comparing runtime class identity, compare `Class<?>` using `==`.

### “Setting the name to plugin-v2 makes the JVM automatically load the v2 JAR”

Incorrect. `name` is a label; it does not determine the classpath, URL, or finder.

**Fix:** manage the source of class bytes/resource URLs in a dedicated finder, rather than stuffing paths into the name as a configuration mechanism.

### “Using super(null) is equivalent to super()”

Incorrect. `super()` uses the system loader as the parent; `super((ClassLoader) null)` selects bootstrap lookup in default delegation.

**Fix:** choose the desired behavior explicitly; in source code, `super(null)` invokes the one-parameter constructor when there is no other one-parameter constructor causing ambiguity, while `super(name,null)` makes the parent clearer.

### “As long as you override findClass, classes in the plugin will always be defined by the custom loader”

Incorrect. Parent-first prioritizes classes found in the parent; `findClass` is only called when needed.

**Fix:** design the namespace: shared APIs parent-first, while implementations may need their own lookup path. Only override `loadClass` when truly necessary, synchronizing via `getClassLoadingLock(name)` and `findLoadedClass(name)`.

### “An empty loader name saves log space”

Incorrect. The named constructor since Java 9 rejects `""`.

**Fix:** pass `null` to leave it unnamed or pass a **non-empty** name.

### “The loader name will automatically ensure class unloading”

Incorrect. The name is metadata for diagnostics; garbage collection/unloading depends on reachability and the JVM.

**Fix:** clean up long-lived references such as thread pools, listeners, callbacks, registries, context class loaders, and caches when the plugin closes.

## 12. A quick selection checklist

Before implementing, answer these in order:

1. **Does this loader need to see the host's shared API?** If yes, choose a parent that sees the exact API classes; verify runtime identity.
2. **Where does it need to load its own classes from?** A JAR, directory, generated bytecode, or another source — there must be an appropriate finder; the constructor does not handle this on its own.
3. **Does the application want parent-first or a selective strategy?** Do not use child-first for every package if there are shared contracts.
4. **Is a loader name needed for debugging?** If yes, use `ClassLoader(String, ClassLoader)` and a non-sensitive, non-empty label.
5. **Is a null parent truly necessary?** Remember bootstrap delegation and platform visibility limits.
6. **Is there a hot reload scenario?** Each loader object owns class identities; manage the lifecycle, close resources, and clear references appropriately.
7. **Is there concurrency?** If overriding `loadClass`, keep the check/delegate/find/resolve operations synchronized according to `getClassLoadingLock` and the parallel-capable contract.
8. **Are named modules used?** The parent and `ClassLoader` do not bypass JPMS readability, exports/opens, or module-layer relationships.

## 13. Self-check exercises

**Question 1.** In Java 17, do `new DemoLoader()` and `new DemoLoader(null)` have the same parent if the two constructors respectively call `super()` and `super(parent)`?

**Answer:** No. `super()` selects the system loader; `super(null)` selects a null parent, meaning bootstrap delegation in the default `loadClass`.

**Question 2.** How do `new DemoLoader("", app)` and `new DemoLoader(null, app)` differ?

**Answer:** An empty string causes `IllegalArgumentException`, whereas a `null` name is valid and creates an unnamed loader.

**Question 3.** Two loaders are both named `plugin:orders`. Are they the same loader object?

**Answer:** That cannot be inferred from the name. Names are not necessarily unique, and class identity is not based on the name either.

**Question 4.** A child loader has parent `app`. Why can `child.loadClass("MyApp")` return the class defined by the app loader?

**Answer:** Because the default algorithm prioritizes parent lookup. The returned `Class<?>` retains app as its defining loader and does not become a class defined by child.

**Question 5.** Why doesn't passing `null` as the parent always allow finding every Java SE/JDK platform class?

**Answer:** Bootstrap does not define every platform class on JDK 17. The constructor's API documentation also warns that there is no guarantee all platform classes are visible when the parent is `null`.

**Question 6.** If `findClass` has been overridden, why does the `findClass` call counter remain 0 when loading a class visible to the parent?

**Answer:** The default `loadClass` checks already-loaded classes and then delegates to the parent; only when the parent does not provide the class is `findClass` tried.

**Question 7.** A plugin needs to use the host's `api.Plugin` interface. What should guide the choice of parent?

**Answer:** The loader must resolve the interface to the **exact shared API runtime class**; typically you choose a parent that can see/define `api.Plugin` rather than simply choosing null or the system loader out of habit.

**Question 8.** Does a new loader bearing the same name as the loader of an older plugin version automatically replace the old runtime classes?

**Answer:** No. Different loader objects can define different runtime classes, even with the same name or the same class binary name; class unloading depends on reachability, not on the name.

## 14. Key takeaways and references

- **`ClassLoader()`** selects the **system class loader** as its parent.
- **`ClassLoader(parent)`** selects an explicit parent; **`parent == null`** indicates bootstrap in the default algorithm.
- **`ClassLoader(name,parent)`** (Java 9+) sets the loader name; `name == null` is valid, and `name == ""` is rejected.
- **The loader name does not create runtime class identity**; the binary name plus the defining loader determine the class.
- **The parent determines the delegation path**, whereas `findClass`/the byte source determines which classes the loader can define itself.
- **When designing plugins**, prefer a common loader for shared API types, and define the lookup policy and lifecycle before choosing the constructor.

Official sources:

1. [Java SE 17 — ClassLoader API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): constructors, `getName`, `getParent`, `loadClass`, `findClass`, `getClassLoadingLock`, and runtime built-in loaders.
2. [Java SE 17 — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): an example of a loader with URLs, parent, name, and `close` lifecycle.
3. [JVMS 17 — Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): defining/initiating loaders, type identity, and constraints.
4. [JEP 261 — Module System](https://openjdk.org/jeps/261): how built-in loaders and Java modules work since Java 9.
