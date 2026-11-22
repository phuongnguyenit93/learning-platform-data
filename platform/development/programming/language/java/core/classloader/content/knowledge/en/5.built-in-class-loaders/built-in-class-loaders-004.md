# Parent Relationships and the Scope of Classes Each Loader Is Responsible For

In Java, a **class loader** receives a request to find a type by its binary name, and can forward the request up to a **parent loader** or locate the bytecode itself to define the type. On Java 17+, the system typically has three built-in loader tiers: **bootstrap**, **platform**, and **application/system**. Understanding parent relationships and the scope of responsibility of each tier helps explain why `java.lang.String` and a user-written class have different loaders, why a child loader can usually use classes defined by a parent loader, and why two classes with the same name sometimes cannot be cast to each other.

This lesson belongs to the **Built-in Loaders** group of Java core – classloader. The focus is on: identifying **who the parent is**, **who actually defines the class**, **where each loader looks for classes**, exceptions to the delegation model, and how to inspect this using Java 17+.

## 1. The Three Built-in Loaders and the Parent Relationship Diagram

In a typical Java SE launch configuration, the parent delegation diagram can be visualized as follows:

```text
Bootstrap class loader  [built into the JVM; usually represented as null]
          ↑ parent of
Platform class loader   [ClassLoader.getPlatformClassLoader()]
          ↑ parent of
Application/system      [ClassLoader.getSystemClassLoader()]
          ↑ parent of
Custom class loader     [if you create it with parent = system loader]
```

The arrows here represent **parent relationships for querying class lookups**, not `extends` inheritance relationships, nor do they indicate which loader instantiated another loader, nor do they guarantee that every request always follows this exact path.

| Loader | How to obtain/identify | Typical responsibilities | Parent |
| --- | --- | --- | --- |
| **Bootstrap** | Typically observed as `null` via `SomeCoreClass.class.getClassLoader()`; there is no regular Java `ClassLoader` instance to hold | Defines classes in several core platform modules, for example the core part of `java.base` | None |
| **Platform** | `ClassLoader.getPlatformClassLoader()` | Java SE platform and JDK classes assigned to the platform loader or an ancestor loader | In standard configurations, forwards requests to bootstrap |
| **Application / system** | `ClassLoader.getSystemClassLoader()` | Application classes on the application class path, application module path, and appropriate JDK classes/tools | Platform (or an equivalent ancestor loader in built-in configurations) |
| **Custom loader** | An instance created by the program/framework, for example `new URLClassLoader(urls, parent)` | Plugins, dynamically loaded code, isolated namespaces, or other bytecode sources | Chosen by the application; by default the `ClassLoader()` constructor uses the system loader as its parent |

**Bootstrap is not synonymous with platform.** Since Java 9, the module system changed how JDK classes are distributed: bootstrap defines several foundational modules, while platform and system define/initiate many classes from other modules. Avoid memorizing the old rule “bootstrap loads all `java.*`, extension loads `javax.*`, app loads the rest”: package names are not an accurate assignment table.

In Java 8 and earlier, you often encounter the term **extension class loader** and `jre/lib/ext`. From Java 9 onward, the extension mechanism was removed and replaced by the **platform class loader** in the built-in loader structure. Do not use `ExtClassLoader` or `rt.jar` as architectural assumptions for Java 17+.

## 2. What Is a Parent Loader, and Is It Where Classes Reside?

Each `ClassLoader` can hold a reference to a **parent loader** to delegate class-loading requests to. The `getParent()` API returns the configured delegation relationship, not “the loader that created this object”. A child loader can ask its parent first to avoid redefining classes already provided by the parent.

Three concepts need to be clearly distinguished:

1. **Requesting loader:** the loader that the application or JVM calls to request a class, for example `child.loadClass("java.lang.String")`.
2. **Defining loader:** the loader that actually creates the class definition from the corresponding class data (usually via `defineClass`), or bootstrap handled by the JVM. Inspected using `SomeType.class.getClassLoader()`.
3. **Initiating loader:** the loader that the JVM records as having initiated the loading process for that class name; a child loader can be an initiating loader even when the class is defined by its parent.

If you call `child.loadClass("java.lang.String")` in the parent-first model, the parent can return the same `Class<String>` defined by bootstrap. **The returned result does not mean child defined `String`.** Calling `getClassLoader()` on the returned class is what reveals the defining loader in Java's representation.

A Java class is identified at runtime by its **binary name + defining class loader**, rather than by name alone. Two different loaders can define two classes with the same name `com.example.Plugin`, but they are **two independent types**; casting between them can fail. Conversely, if two child loaders both delegate to a definition provided by a parent, both can receive **the same `Class<?>` object**.

### A Loader's Parent Can Be `null`

`ClassLoader.getParent() == null` typically represents the bootstrap parent because bootstrap is not a regular `ClassLoader` instance. This **does not mean** the loader in question is itself bootstrap. For example, the platform loader in a standard configuration can have `getParent() == null`, yet the platform loader itself is still a distinct `ClassLoader` object.

When you create `new URLClassLoader(urls, null)`, `null` means delegating to bootstrap, **not disabling delegation altogether**. Note that from JDK 9 onward, bootstrap does not provide all platform classes, so a custom loader with a `null` parent might not see APIs that are defined by the platform loader; if a plugin needs those APIs, consider setting the parent to `ClassLoader.getPlatformClassLoader()` or the system loader depending on the desired architecture.

## 3. Practical Scope of Each Loader

### 3.1 Bootstrap: The Minimal Foundation for JVM Operation

Bootstrap is provided by the JVM. It defines core classes such as `java.lang.Object`, `java.lang.String`, and `java.lang.Class` in the relevant foundational modules. For these common types:

```java
System.out.println(String.class.getClassLoader() == null);
System.out.println(Object.class.getClassLoader() == null);
```

This is a **two-statement illustrative snippet** that needs to be placed inside an executable method. In standard Java SE 17, both lines print `true`. Do not write `ClassLoader bootstrap = String.class.getClassLoader(); bootstrap.loadClass(...)`: the `bootstrap` variable has the value `null`, so calling a method on it will throw a `NullPointerException`.

Limitations to understand:

- Bootstrap does not by default load individual user files or every class in the JDK.
- A custom loader with bootstrap as its parent is not guaranteed to have access to all platform APIs.
- Classes defined by bootstrap typically have `Class.getClassLoader() == null`; this representation is an API convention and does not allow direct manipulation of a bootstrap object.

### 3.2 Platform: The Broader Platform Layer Beyond Bootstrap

The platform loader is responsible for **platform classes** that the runtime assigns to it or to ancestor loaders. Platform classes can be Java SE APIs, implementation classes, or JDK-specific classes. The API that returns this loader is:

```java
ClassLoader platform = ClassLoader.getPlatformClassLoader();
```

Platform does not simply “load all peripheral libraries”. Many user libraries reside on the application class path and are defined by the application loader. Nor should you infer the defining loader solely from the `java.`, `javax.`, or `jdk.` prefixes: the module system and runtime configuration determine how they are distributed.

**Important delegation exception:** the `ClassLoader` documentation allows the platform loader, in certain **upgraded modules** scenarios, to delegate to another loader, including the application loader, even though application is not an ancestor of platform. Therefore, the parent diagram at the beginning of this lesson is the **default model for parent relationships**, not a rigid law stating that every lookup only goes from child to parent without ever taking another edge.

### 3.3 Application/system: The Default Anchor of the Application

`ClassLoader.getSystemClassLoader()` typically returns the loader used to start the application. With the default launcher configuration, it defines classes from the **application class path** (`-cp`/`--class-path`) and eligible classes/modules from the **application module path**. On built-in JDKs, the system loader is usually named `"app"`.

Example command to run with a class path:

```bash
javac --release 17 Hello.java
java -cp . Hello
```

If `Hello` is a simple class in the current directory and no custom system loader is configured, `Hello.class.getClassLoader()` is typically `ClassLoader.getSystemClassLoader()` itself.

This scope has limitations:

- A class that does not appear on the appropriate class path/module path is usually not found by the app loader.
- **A parent does not automatically know about classes defined by a child.** If a plugin class is defined only by a plugin loader, the system loader cannot find it on its own.
- The system loader can be customized via the `java.system.class.loader` property. Therefore, do not assume that its implementation class name, `toString()` string, or even its direct relationship with platform is always fixed across every application.
- The class path and module path are not an equivalent unit: named modules are also governed by module readability, exports, and opens.

## 4. Java 17+ Hands-on Test: Parent Relationships and Defining Loaders

Create the file `LoaderRolesDemo.java`:

```java
public class LoaderRolesDemo {
    static class Sample {
    }

    public static void main(String[] args) throws ClassNotFoundException {
        ClassLoader platform = ClassLoader.getPlatformClassLoader();
        ClassLoader system = ClassLoader.getSystemClassLoader();
        ClassLoader sampleLoader = Sample.class.getClassLoader();

        System.out.println("String by bootstrap: "
                + (String.class.getClassLoader() == null));
        System.out.println("Platform parent bootstrap: "
                + (platform.getParent() == null));
        System.out.println("System parent platform: "
                + (system.getParent() == platform));
        System.out.println("Sample defined by system: "
                + (sampleLoader == system));

        Class<?> viaSystem = system.loadClass("java.lang.String");
        System.out.println("Same String class: "
                + (viaSystem == String.class));

        Class<?> viaPlatform = platform.loadClass("java.lang.String");
        System.out.println("Platform delegates String: "
                + (viaPlatform == String.class));
    }
}
```

Compile/run using JDK 17+ on the class path, without setting `java.system.class.loader`:

```bash
javac --release 17 LoaderRolesDemo.java
java -cp . LoaderRolesDemo
```

On a standard JDK with the three built-in loaders and the default launcher, the expected stdout is:

```text
String by bootstrap: true
Platform parent bootstrap: true
System parent platform: true
Sample defined by system: true
Same String class: true
Platform delegates String: true
```

Explanation:

- `String` is defined by bootstrap, so `getClassLoader()` returns `null`.
- `platform.getParent() == null` does **not** mean platform is bootstrap; it represents parent delegation to bootstrap.
- `system.getParent() == platform` describes the standard parent edge between app and platform.
- `Sample` is a class compiled alongside the program and loaded from the current class path, so app/system is the defining loader in the configuration above.
- Both `loadClass("java.lang.String")` calls on system and platform return the same `String.class` object, because these loaders delegate to use the existing definition from bootstrap.

If you run with a custom system loader, modify the class path/module path, or change the launcher/runtime, some comparison lines may change. The main point is to verify **relationships and identity** via the API, rather than memorizing internal JDK implementation class names.

### Printing the Parent Chain for Diagnostics

A utility snippet (placed inside a Java method) can traverse from system up through its parents:

```java
ClassLoader loader = ClassLoader.getSystemClassLoader();
while (loader != null) {
    System.out.println(loader.getName());
    loader = loader.getParent();
}
System.out.println("<bootstrap represented as null>");
```

This is an **illustrative code snippet to insert into a method**, not a standalone runnable file. On common built-in JDKs, the names `app` and `platform` may appear, whereas a custom loader's name may be `null`; do not infer permissions/class storage locations based solely on the name. The loop follows the configured **parent chain**; it does not list every module relationship or non-tree delegation.

## 5. How Does Parent-First Delegation Work?

`ClassLoader.loadClass(String)` invokes the class lookup process following the default algorithm of `loadClass(String, boolean)`:

1. **Already loaded?** Uses `findLoadedClass(name)` within the loader's context to avoid redundant processing.
2. **Ask the parent first.** Calls `parent.loadClass(name, false)`; if the parent is `null`, uses the bootstrap mechanism to search.
3. **Parent cannot find it:** the current loader calls `findClass(name)` to define/retrieve the class itself from the source it manages.
4. **If resolution is requested:** the JVM links it via `resolveClass`; `loadClass` itself does not run static initializers by default.

Diagram:

```text
child.loadClass("demo.Feature")
       |
       v
Already loaded before? --- yes ---> return Class
       |
       no
       v
Ask parent.loadClass(...) --- found --> return parent's Class
       |
   not found
       v
child.findClass(...) ------- found ---> child defines Class
       |
   not found
       v
ClassNotFoundException
```

This is **default parent-first**, not an absolute requirement for every custom loader. Subclasses can override `loadClass` to implement a different policy, but they must obey JVM constraints and handle critical classes safely. Per the API recommendations, most custom loaders should override `findClass` and retain the default `loadClass` algorithm unless there is a compelling reason to change it.

Parent-first helps reuse foundational classes, prevents accidentally defining incompatible duplicates, and allows multiple child loaders to share types provided by a parent. However, it does not automatically resolve version conflicts: if the parent already sees an older version of a dependency, the child will be returned the parent's class under the default algorithm.

### Runnable Example: Requested Through Child, Defined by Parent

Create the file `DelegationDemo.java`:

```java
public class DelegationDemo {
    static class ChildLoader extends ClassLoader {
        ChildLoader(ClassLoader parent) {
            super(parent);
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            System.out.println("findClass: " + name);
            throw new ClassNotFoundException(name);
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader child = new ChildLoader(
                ClassLoader.getSystemClassLoader());

        Class<?> core = child.loadClass("java.lang.String");
        System.out.println("String shared: "
                + (core == String.class));

        Class<?> local = child.loadClass("DelegationDemo");
        System.out.println("App class shared: "
                + (local == DelegationDemo.class));

        try {
            child.loadClass("demo.Missing");
        } catch (ClassNotFoundException expected) {
            System.out.println("Missing class");
        }
    }
}
```

```bash
javac --release 17 DelegationDemo.java
java -cp . DelegationDemo
```

Stdout:

```text
String shared: true
App class shared: true
findClass: demo.Missing
Missing class
```

Key takeaways:

- Child requests `String`, but bootstrap provides the definition: child's `findClass` **is not called**.
- Child requests `DelegationDemo`, which the app/system loader has already defined: child receives **the same `Class<?>`**.
- For `demo.Missing`, the parent does not find it, so child then tries `findClass` and throws `ClassNotFoundException`.
- The example intentionally does not generate bytecode for the missing class; the goal is to observe the **delegation order**, not to simulate a full-featured plugin loader.

If you want child to define a class itself, you must supply valid bytecode and call `defineClass(...)` inside `findClass`; you must ensure appropriate loader relationships, packages, modules, visibility, and lifecycle. You must not arbitrarily define classes in prohibited namespaces such as `java.*`, and you should not break parent-first just to sidestep a dependency clash without first analyzing type identity.

## 6. Loader Relationships Are Not Java Class Inheritance Relationships

Common misconceptions:

- `class P extends ClassLoader` only states that **P is a type of loader** in Java's class system.
- `new P(parent)` only specifies **which parent this instance of P will ask** when delegating, provided the constructor code and overrides honor that parameter.
- `MyService extends BaseService` is an inheritance relationship between **two application classes**. `MyService` and `BaseService` can be defined by different loaders, as long as the JVM can resolve them and properly enforce the constraints.
- The loader of a class is not necessarily the loader of every class it references. The JVM can use the referencing class's loader to request a dependent type and then receive a definition back from a parent.

A parent loader does not automatically have the ability to find classes defined by a child. The usual delegation relationship is **child asks parent first**, not that every loader shares a single unlimited class repository. If a framework needs to load a plugin defined by a child, the framework must know how to obtain the plugin loader or hand it off to an appropriate discovery mechanism.

## 7. Class Scope, Modules, and the Class Path Are Three Different Concepts

On Java 17, built-in loaders work alongside the **Java Platform Module System (JPMS)**:

- **Class path:** code running under the class path mechanism typically belongs to the **unnamed module** of the corresponding loader. The application loader is the common loader that defines application classes from `-cp`.
- **Module path:** named modules are identified, resolved, and assigned to loaders by the runtime according to the module system mechanism; do not assume that “every named module uses the platform loader” or “every user module gets its own separate loader”.
- **Module readability:** which modules a module can read, relating to the module's static/dynamic dependencies.
- **Exports/opens:** govern API access and reflection to packages according to module rules. A class may **be loaded** while other code is still blocked from accessing its members due to module encapsulation.
- **Resource lookup:** `getResource` or `getResources` is also affected by paths, search order, and packaging/module mechanisms. Knowing that a class can be loaded does not guarantee that every resource in the same package can be found in the old way.

**Loader scope answers the question “which class definitions can be seen/initiated on request?”**; **module boundaries additionally answer “which code has permission to read, access, and reflect?”**. These two checks may be related, but they do not replace each other.

A class can belong to a named module while being defined by either the platform or app loader depending on the module and runtime. When you need to know what happens in practice, inspect it directly:

```java
Class<?> type = java.util.ArrayList.class;
System.out.println(type.getModule().getName());
System.out.println(type.getClassLoader());
```

This is **illustrative code to insert inside a method**. `getModule().getName()` tells you the class's module; `getClassLoader()` tells you its defining loader. Do not guess the loader by looking at the module name.

### When Should You Choose Bootstrap, Platform, or App as the Parent for a Custom Loader?

| Goal | Commonly considered parent | Trade-offs |
| --- | --- | --- |
| Plugin needs extended Java SE APIs and should not automatically see the entire app | **Platform loader** | Still requires organizing shared APIs, module visibility, and additional dependencies |
| Plugin needs interfaces/APIs declared by the application itself | **System loader** or the loader that defined the shared API | Ensures the plugin receives the same interface definition; can be affected by dependency versions in the parent |
| Maximum isolation loader, relying only on a subset of foundational bootstrap classes | `null` parent | Not guaranteed to see all platform classes; high dependency management overhead |
| Framework with its own loader ecosystem | Parent established by the framework's contract | Must check the framework's contract because parent-first/child-first behavior may vary |

Choose the parent based on **which types must be shared**, the sources of classes that need to be accessed, and your version conflict policy. Do not use `null` merely because you want “better security” or want to make the loader lighter; class loader isolation by itself is not a complete security boundary.

## 8. The Thread Context Class Loader Differs from the Current Class's Defining Loader

There is another concept easily confused with the parent: the **thread context class loader (TCCL)**.

```java
ClassLoader context = Thread.currentThread()
        .getContextClassLoader();
ClassLoader defining = MyType.class.getClassLoader();
```

This is an **illustrative snippet**, assuming `MyType` exists. `context` is held by the thread so that frameworks/service discovery can select a source of classes or resources. `defining` is the loader that defined `MyType`. They can be different, and the TCCL **does not automatically change** the defining loader of an existing class.

In `main` of a normally launched application, the context loader is usually the system loader, though an executor, app server, or framework may assign a different one. A safe pattern when temporarily replacing the TCCL is:

```java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();
try {
    thread.setContextClassLoader(pluginLoader);
    // Perform the discovery operation that requires pluginLoader.
} finally {
    thread.setContextClassLoader(previous);
}
```

This is an **illustrative snippet**, assuming `pluginLoader` already exists. Restore the context in `finally` so subsequent work on the same thread does not accidentally see the plugin namespace. In a thread-pool environment, leaving the old TCCL set after a request easily leaks references to the plugin loader or loads the wrong class.

The TCCL can allow a framework coded in a “higher” loader to locate providers managed by a “lower” loader, but only when the framework **explicitly uses the TCCL**. It does not reverse the entire parent delegation mechanism for all classes.

## 9. Same Name, Different Loader: Why Do Casting Errors Occur?

Suppose two independent plugin loaders both define the binary name `demo.api.Task`:

```text
system loader -> defines demo.api.Task (if there is a shared API)
     |
     +--> PluginLoader A -> defines demo.impl.Service
     |
     +--> PluginLoader B -> defines demo.impl.Service
```

The two `demo.impl.Service` classes may have identical bytecode yet be two distinct classes because their **defining loaders differ**. An object from A must not be treated as an instance of class B just because the name matches. To share objects across plugin boundaries, you need a **shared API/interface** defined by a common loader (usually a parent), so code on both sides resolves to **the same Class object** of the API contract.

If each plugin also defines its own copy of the `demo.api.Task` interface, the identical interface names are still two incompatible types. In logs, the `ClassCastException` message may display two identical class names accompanied by different loader/module identifiers. When investigating, print:

```java
System.out.println(instance.getClass().getName());
System.out.println(instance.getClass().getClassLoader());
System.out.println(instance.getClass().getModule());
```

This is an **illustrative snippet**, where `instance` is the object under investigation. You need to check by the identity of `Class<?>`/`ClassLoader`, rather than only comparing `getName()` or relying entirely on `toString()`.

## 10. Debugging Which Loader Is Loading and Defining a Class

There are three complementary inspection approaches:

**A. Reading metadata at runtime**

```java
static void inspect(Class<?> type) {
    System.out.println("class=" + type.getName());
    System.out.println("loader=" + type.getClassLoader());
    System.out.println("module=" + type.getModule().getName());
}
```

This is an **illustrative method** that needs to be placed inside the class being compiled. If `getClassLoader()` returns `null`, that is the JVM's representation of bootstrap. If `getModule().getName()` is `null`, the module is unnamed (an unnamed module).

**B. Viewing class loading traces on HotSpot**

```bash
java -Xlog:class+load=info LoaderRolesDemo
```

Unified logging in many HotSpot builds prints information about loaded classes and their associated sources. The format, reported source, and level of detail depend on the runtime; **logging the source does not necessarily show the full defining loader**. Use it to supplement inspection via `Class.getClassLoader()` and your class path/module path configuration. On runtimes that do not support this option, consult the vendor's equivalent logging flag.

**C. Inspecting the class lookup path**

```bash
java -cp ".;libs/*" LoaderRolesDemo
```

The semicolon `;` in the example above is the **class path separator on Windows**. On Linux/macOS, use a colon `:`: `java -cp ".:libs/*" LoaderRolesDemo`. Checking for errors caused by missing JARs, duplicate classes, or mismatched versions on the class path is a separate task from reading the parent chain. For named modules, also check `--module-path`, `--add-reads`, and `--add-exports` when appropriate to diagnose module access permissions; do not tweak flags arbitrarily just to make errors disappear.

### Distinguishing Common Errors

| Symptom | What to check first |
| --- | --- |
| `ClassNotFoundException` from `loadClass` or `Class.forName` | Binary name, actual class path/module path, parent, custom `findClass`, source JAR |
| `NoClassDefFoundError` when code references a class | Missing runtime class/dependency, linking error, or a previous class initialization failure; inspect `cause`/stack trace |
| `ClassCastException` between two identical names | Were the two classes created by two different defining loaders? |
| `NoSuchMethodError` / `NoSuchFieldError` | Binary compatibility of the dependency actually returned by the loader; method/field name and descriptor |
| `IllegalAccessError` / `InaccessibleObjectException` | Access level, package/module readability, exports/opens, reflective access |
| `ServiceLoader` cannot find a provider | The context loader being used, module service declarations, `META-INF/services` files/module configuration, provider visibility |
| Plugin was unloaded but the loader is still alive | Objects/threads/TCCL/static caches/stacks still holding references to the plugin's classes, instances, or loader |

A few diagnostic notes:

- `ClassNotFoundException` is a checked exception commonly seen with explicit class-loading APIs; `NoClassDefFoundError` is a linkage error and does not always mean the physical file is missing.
- `ClassLoader.loadClass(String)` does not **initialize** the class by default; the single-parameter overload of `Class.forName(String)` requests initialization. This is a lifecycle difference, not a parent tree difference.
- If a dependency resides in the parent with an incompatible version, a parent-first child will typically receive the parent's copy. You must address the dependency/version architecture rather than expecting Java to intuitively pick the “closer JAR”.
- Do not treat the output of `getResources()` as an exact list of all classes a loader can define, because resource lookup follows different rules from class loading and is subject to module encapsulation.

## 11. Design Scenarios and Appropriate Decisions

**Scenario A – simple Java application:** your code and dependencies are on `-cp`. The system loader defines most application classes, while JDK core classes typically come from bootstrap/platform. There is usually no need to create a custom loader.

**Scenario B – plugins sharing `PluginApi`:** place `PluginApi` on the classpath/module of a **common parent**, while letting each plugin's loader define its own plugin implementation. When the host invokes methods through `PluginApi`, all parties use the same interface definition. Be careful if the host also packages a copy of the API inside the plugin JAR, especially when using child-first.

**Scenario C – plugin needs broader JDK APIs than bootstrap without seeing the entire application:** the platform loader can be suitable as a parent; verify in practice against the modules/services the plugin requires. If the plugin must cast to a host interface, you must resolve how the interface's defining loader is shared.

**Scenario D – application server/container:** the container may provide custom loaders with a child-first policy for certain libraries and parent-first for the platform. Do not mechanically apply the `java -cp . Main` loader tree to the whole system; check the framework documentation and runtime objects.

**Scenario E – plugin framework using TCCL:** the provider is defined by a plugin loader while the discovery code sits in a parent layer. The framework can choose the context loader to locate the provider. You must set and restore the context within the task scope, especially in thread pools.

## 12. Self-Check Knowledge Questions

**Question 1.** `ClassLoader.getSystemClassLoader().loadClass("java.lang.String")` returns `String.class`. Can we conclude that the system loader defines `String`?

**Answer:** No. In a standard JDK configuration, the system loader delegates through platform to bootstrap; `String`'s defining loader is represented as `null`. The requesting loader differs from the defining loader of the class.

**Question 2.** Does `ClassLoader.getPlatformClassLoader().getParent() == null` mean the platform loader is the bootstrap loader?

**Answer:** No. Platform is still a `ClassLoader` instance; `null` here represents bootstrap in the parent relationship.

**Question 3.** Why is a custom loader with a `null` parent not guaranteed to find every Java SE API class?

**Answer:** It only delegates to bootstrap under the standard mechanism. Since Java 9, many platform classes are defined outside bootstrap, so a `null` parent does not guarantee the entire platform is visible.

**Question 4.** PluginLoader A and B both look up `java.lang.String`. Why can the `Class<?>` be the same? Yet two `demo.impl.Service` cannot be cast to each other?

**Answer:** Both delegate to a single bootstrap definition of `String`, so they receive the same `Class<?>`. Meanwhile, each plugin can define `Service` on its own, creating two separate types because their defining loaders differ.

**Question 5.** When is `findClass` called in a custom loader by default?

**Answer:** After `findLoadedClass` does not return an already loaded class and the parent cannot find the requested class. If the parent finds the class, the child's `findClass` is not called by default.

**Question 6.** What three questions do `getParent()`, `getContextClassLoader()`, and `SomeClass.class.getClassLoader()` answer?

**Answer:** `getParent()`: which loader is queried as the parent. `getContextClassLoader()`: the context loader currently held by the thread for APIs that use it. `Class.getClassLoader()`: the defining loader of the class (bootstrap may be `null`).

**Question 7.** As long as a class can be loaded, can any other module reflectively access its private members?

**Answer:** No. Loader visibility is different from Java/module access permissions; JPMS readability, exports, and opens along with reflection rules still apply.

**Question 8.** To use the same API interface between a host and two independent plugins, where should the interface definition be placed?

**Answer:** In a source visible to the **common loader** shared by the host and plugins, usually a parent/API loader; avoid letting each plugin define its own copy of the same interface name.

## Practical Takeaways

To accurately explain a class-loading event, ask in order:

1. What is the **binary name** of the class being requested?
2. **Who receives the request**, and who is that loader's **parent**?
3. Does the loader **delegate parent-first** or use a different policy? Which class/module sources does each loader manage?
4. **Who actually defines** the returned class (`Class.getClassLoader()`)?
5. Do the classes that need to interact use **the same API definition**, or are they separated across defining loaders?
6. Do module readability/exports/opens, resource lookup, and the TCCL affect what you are doing?

Do not infer class access permissions solely from the `.` dots in a package name or from the JAR name. **Parent relationships explain the direction of delegation; the defining loader determines the runtime identity of a type; modules and the thread context add the necessary visibility/lookup rules.**

Authoritative references for further verification:

- [Java SE 17 API – `java.lang.ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): the three built-in loaders, parent, `loadClass`, `findClass`, and delegation exceptions.
- [Java SE 17 API – `java.lang.Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getClassLoader()` and `getModule()`.
- [JVM Specification 17 – §5 Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): type identity, defining/initiating loaders, and linking.
