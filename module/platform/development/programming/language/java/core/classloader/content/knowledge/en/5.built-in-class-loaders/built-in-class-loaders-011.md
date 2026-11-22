# Customizing the System Class Loader with `java.system.class.loader`

In Java, the **system class loader** is the default class loader returned by `ClassLoader.getSystemClassLoader()`. In a standard JDK launch, it is the application class loader; it typically participates in loading application classes and serves as the default parent of `new ClassLoader()`.

When you need to change the object used as the **JVM's system class loader**, you can set the `java.system.class.loader` system property **at JVM startup**:

```bash
java -Djava.system.class.loader=CustomSystemLoader -cp . SystemLoaderDemo
```

In this command, `CustomSystemLoader` is the **fully qualified binary name of a Java class** provided by the application (including its package name, if any). The JVM locates and instantiates that class through the mechanism specified by `ClassLoader.getSystemClassLoader()`; the new instance becomes the system class loader.

This is a JVM-level feature that can affect libraries calling `ClassLoader.getSystemClassLoader()`, not just a single `loadClass` call. Therefore, it is important to understand the **initialization mechanism, parent delegation relationships, applicability limits, and diagnostic techniques** before using it.

## 1. Three Entities to Distinguish

```text
                JVM startup
                    |
                    v
      Built-in default system class loader
        (usually the application loader)
                    |
     loads CustomSystemLoader class from here
                    |
     new CustomSystemLoader(defaultLoader)
                    |
                    v
          CustomSystemLoader instance
          published as the system loader
                    |
       ClassLoader.getSystemClassLoader()
                    |
                    v
       returns this custom instance
```

Note the following relationship when the constructor calls `super(parent)`:

```text
CustomSystemLoader        <-- ClassLoader.getSystemClassLoader()
        |
        | getParent()
        v
Default built-in app loader
        |
        v
Platform loader (standard JDK environment)
        |
        v
Bootstrap loader (no Java ClassLoader object like other loaders)
```

| Concept | Role |
|---|---|
| **Default system class loader** | The built-in class loader that the JVM uses to locate/load the `CustomSystemLoader` provider class and passes to its constructor |
| **Custom system loader** | The instance constructed from the class name in `java.system.class.loader`, replacing the default system loader object published via `getSystemClassLoader()` |
| **Defining loader of a specific class** | The loader that actually invokes the runtime class definition mechanism; this may be a built-in parent, even if `loadClass` starts at the custom loader |
| **Thread context class loader (TCCL)** | A per-thread loader queried via `Thread.currentThread().getContextClassLoader()`; threads can change their context loader independently |
| **Bootstrap/platform loaders** | Other loaders in the class-loading architecture; they are not replaced wholesale just by changing the system loader |

**Avoid this misconception:** changing the system loader **does not automatically transfer defining ownership of every class** to the custom loader, nor does it alter all existing `ClassLoader` references in the JVM.

## 2. How Does the JVM Set Up a Custom System Loader?

According to the `java.lang.ClassLoader.getSystemClassLoader()` specification (Java 17+), when the `java.system.class.loader` property is set at the time the JVM first initializes the system loader, the process is essentially:

1. The JVM knows the **default system class loader** provided by the environment.
2. It reads the value of the `java.system.class.loader` property as the provider class name, for example `com.example.loader.CustomSystemLoader`.
3. It **loads the provider class using the default system class loader**, not a custom instance that does not exist yet.
4. It requires the provider class to have a **public constructor taking a single `ClassLoader` parameter**.
5. It invokes that constructor, passing in the **default system class loader**.
6. The resulting instance becomes the **system class loader**; subsequent calls to `ClassLoader.getSystemClassLoader()` after successful initialization return that instance.

The Java API specifies that the constructor parameter is the default loader, intended to be used as the **delegation parent**. To follow this convention, the constructor typically calls `super(parent)` or passes `parent` to the corresponding superclass constructor.

### Important Constructor Contract

```java
public final class CustomSystemLoader extends ClassLoader {
    public CustomSystemLoader(ClassLoader parent) {
        super(parent);
    }
}
```

This is the **minimal provider class**, which does not alter how classes are found yet: because it does not override the lookup mechanism, it inherits `ClassLoader`'s default delegation model.

Required conditions:

- The name in the property must be a class name that the **default system loader can load** at JVM startup.
- The constructor must have the exact signature **`public CustomSystemLoader(ClassLoader parent)`**.
- The constructor must complete successfully and should set the parent using the argument provided by the JVM.
- The provider must be a valid `ClassLoader`; you cannot supply a class that does not extend `ClassLoader`.
- If the provider is in a package, the property must include the fully qualified package name; for example, `-Djava.system.class.loader=com.example.loader.CustomSystemLoader`.

**Insufficient:** a no-arg `public CustomSystemLoader()` constructor, a `protected` constructor, a constructor taking `URL[]`, or a constructor taking `Object`. Those signatures do not satisfy the property contract.

## 3. Runnable Java 17+ Example: Replacing the System Loader and Observing Delegation

This example consists of **two Java files** and requires no Maven, Gradle, or external libraries. The custom loader logs when the JVM creates it and when a request is made to load a class named `DemoTarget`. It **delegates to its parent**, so the example also distinguishes between the *loader receiving the request* and the *loader actually defining the class*.

### File 1 — `CustomSystemLoader.java`

```java
public final class CustomSystemLoader extends ClassLoader {

    // Must be public and accept exactly one ClassLoader.
    public CustomSystemLoader(ClassLoader parent) {
        super(parent);
        System.out.println("CustomSystemLoader constructed");
    }

    @Override
    protected Class<?> loadClass(String name, boolean resolve)
            throws ClassNotFoundException {
        if ("DemoTarget".equals(name)) {
            System.out.println("CustomSystemLoader requested DemoTarget");
        }

        // Preserve the parent-first delegation provided by ClassLoader.
        return super.loadClass(name, resolve);
    }
}
```

**Explanation:**

- The JVM loads the `CustomSystemLoader` class itself using the default system loader before creating the custom instance.
- `super(parent)` preserves the parent supplied by the JVM, avoiding any custom redesign of the loader chain.
- Overriding `loadClass(String, boolean)` here is only to observe the request for `DemoTarget`. Ultimately, `super.loadClass` still checks already-loaded classes and delegates to the parent before calling `findClass`.
- Because `DemoTarget` is on the built-in loader's classpath, it is defined by the parent. Receiving the request through the custom loader does not prove that the class was *defined by the custom loader*.

### File 2 — `SystemLoaderDemo.java`

```java
public class SystemLoaderDemo {
    public static void main(String[] args)
            throws ClassNotFoundException {
        ClassLoader system = ClassLoader.getSystemClassLoader();

        System.out.println("custom system loader: "
                + (system instanceof CustomSystemLoader));

        // Explicitly request loading through the system loader.
        Class<?> type = system.loadClass("DemoTarget");

        System.out.println("target class: " + type.getSimpleName());
        System.out.println("defined by custom: "
                + (type.getClassLoader() == system));
        System.out.println("system has parent: "
                + (system.getParent() != null));
    }
}

// javac generates DemoTarget.class from this package-private top-level class.
class DemoTarget {
}
```

Compile in the directory containing both files:

```bash
javac CustomSystemLoader.java SystemLoaderDemo.java
```

### Running Normally, Without the Property

```bash
java -cp . SystemLoaderDemo
```

**Stdout on a standard JDK:**

```text
custom system loader: false
target class: DemoTarget
defined by custom: true
system has parent: true
```

Here, `getSystemClassLoader()` is the built-in application loader. The expression `type.getClassLoader() == system` evaluates to `true` because the built-in loader itself loaded and defined `DemoTarget`.

### Running with the Custom System Loader

```bash
java -Djava.system.class.loader=CustomSystemLoader -cp . SystemLoaderDemo
```

**Expected stdout:**

```text
CustomSystemLoader constructed
custom system loader: true
CustomSystemLoader requested DemoTarget
target class: DemoTarget
defined by custom: false
system has parent: true
```

Some HotSpot/JDK builds may emit an additional **CDS/Class Data Sharing warning to stderr** when using `java.system.class.loader`. That warning depends on the runtime and is **not part of the stdout shown above**.

**Why does it print `defined by custom: false`?**

`system.loadClass("DemoTarget")` invokes the overridden method on the custom loader, but `super.loadClass` delegates to the **default built-in app loader**, which already sees `DemoTarget.class` on `-cp .`. Because the parent defines the type, `type.getClassLoader()` returns the parent, not the custom instance.

Therefore:

```text
Who receives the request?        CustomSystemLoader
Who returns the Class object?    CustomSystemLoader.loadClass(...)
Who defines DemoTarget?          Default application loader (parent)
Who is the system loader?        CustomSystemLoader
```

This is a normal outcome of **parent delegation**, not a sign that replacing the system loader failed.

### Reading the Output Correctly

- `CustomSystemLoader constructed`: the custom instance was created during startup.
- `custom system loader: true`: `getSystemClassLoader()` returns an instance of the provider class.
- `CustomSystemLoader requested DemoTarget`: a `loadClass` call actually passed through the custom instance.
- `defined by custom: false`: the parent is the **defining loader** of `DemoTarget`.
- `system has parent: true`: the custom loader retained the parent supplied by the JVM.

Key takeaway: **replacing the system loader determines which default object is published, while which loader actually defines each type depends on the actual loading and delegation policy**.

## 4. What Is Needed for a Custom Loader to Define Its Own Classes?

If the goal is to load plugins or bytecode from a custom source, merely overriding `loadClass` to log as in the example above is not enough. You can add class-lookup capability by extending `URLClassLoader` or implementing `findClass` yourself to read bytecode and call `defineClass`.

Below is a **configuration sketch**, usable only when a `plugins` directory already contains bytecode matching the expected package structure:

```java
import java.net.MalformedURLException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class DirectorySystemLoader extends URLClassLoader {
    public DirectorySystemLoader(ClassLoader parent)
            throws MalformedURLException {
        super(
            "directory-system-loader",
            new URL[] { Path.of("plugins").toUri().toURL() },
            parent
        );
    }
}
```

This is **a separate provider** that must be saved in `DirectorySystemLoader.java` and compiled separately; it is **not part of the first example**, and requires corresponding `plugins` data to have any effect. Configuration:

```bash
java -Djava.system.class.loader=DirectorySystemLoader -cp . SystemLoaderDemo
```

Meaning: `URLClassLoader` tries its parent first according to the delegation policy. **Only when the parent cannot find the class name and the URL loader has matching bytecode** can it define the class from the configured URL. Classes already present in the parent are not automatically reassigned to be defined by the custom loader. This ordering helps prevent accidentally splitting a shared API into two distinct type definitions.

For plugins with their own lifecycle, creating a **dedicated `URLClassLoader` for the plugin** is usually easier to manage than replacing the system loader for the entire application. `java.system.class.loader` is appropriate when you genuinely need to change how application/framework components obtain the default system loader.

**Security considerations when implementing a custom bytecode loader:** validate trusted paths/JARs, handle package/sealing rules where applicable, avoid arbitrarily defining classes in restricted package namespaces, and do not treat the class loader mechanism as a security sandbox.

## 5. How Does This Differ from Creating a Regular Custom `ClassLoader`?

Consider these approaches:

| Approach | Scope | Example | Prefer when |
|---|---|---|---|
| Create an explicit loader | Only where code holds/references the loader | `new URLClassLoader(urls, parent)` | Plugins, isolated modules, or dynamic loading with an independent lifecycle |
| Set `java.system.class.loader` at startup | Replaces the instance returned by `ClassLoader.getSystemClassLoader()` | `-Djava.system.class.loader=...` | You want to change system loader behavior for programs/libraries that rely on the system loader |
| Set the thread context loader | Per-thread, inherited or changed via the `Thread` API | `Thread.currentThread().setContextClassLoader(loader)` | Context-based service/provider lookup or integrating libraries that require TCCL |

`new MyLoader(parent)` does **not** make it the system loader. Likewise, `Thread.currentThread().setContextClassLoader(myLoader)` does **not** change `ClassLoader.getSystemClassLoader()` to `myLoader`.

Similarly, calling `System.setProperty("java.system.class.loader", "...")` inside `main` is **not a reliable way to replace the loader**: the JVM has normally already initialized the system loader during startup. Set the property on the `java -D...` command line when launching the JVM.

### Relationship to the Thread Context Class Loader

The `ClassLoader.getSystemClassLoader()` documentation notes that the system loader is the context class loader for the main application thread when the runtime creates it. However, the context loader can be changed independently:

```java
ClassLoader system = ClassLoader.getSystemClassLoader();
ClassLoader context = Thread.currentThread().getContextClassLoader();
System.out.println(system == context);
```

This snippet is only for illustration; **do not assume it prints `true` in every environment**: a framework or application may have already changed the TCCL. Thread pools may also retain the context loader captured when a thread was created.

If a library uses `Thread.currentThread().getContextClassLoader()`, customizing the system loader **does not guarantee** that the library will always use the custom loader on every thread.

## 6. Limitations: Changing the System Loader Does Not Change Every JVM ClassLoader

### 6.1. Does Not Replace the Bootstrap or Platform Loader

`java.system.class.loader` affects the **system loader**; it does not turn the bootstrap loader into a custom Java loader. For `String.class`:

```java
ClassLoader loader = String.class.getClassLoader();
System.out.println(loader == null);
```

In a standard Java JVM, this prints `true` because `java.lang.String` is defined by the bootstrap loader. This is a standalone illustrative snippet, separate from the main demo.

Likewise, platform/module classes may be served by the platform or bootstrap loader according to runtime rules; do not expect a custom system loader to redefine `java.lang.String`, `java.util.List`, or classes in `java.base`.

### 6.2. "The System Loader Is Used to Run the Application" Does Not Mean Every Class Belongs to It

You can inspect which loader actually defined a class:

```java
System.out.println(SystemLoaderDemo.class.getClassLoader());
System.out.println(DemoTarget.class.getClassLoader());
System.out.println(ClassLoader.getSystemClassLoader());
```

These three values **can differ** depending on launch mode, classpath/module path, parent delegation, and implementation. Not every JVM displays the same `toString()` output or the same loader class name.

A more reliable check for a specific class:

```java
ClassLoader system = ClassLoader.getSystemClassLoader();
ClassLoader defining = DemoTarget.class.getClassLoader();
boolean definedBySystem = defining == system;
```

With the parent-first custom loader example above, `definedBySystem` is `false`, and that is intentional.

### 6.3. Runtime Modules, Classpath, and Type Visibility

The provider must be in a location where the **default system loader** can find it at startup. If you run with a classpath that does not contain `CustomSystemLoader.class`, the JVM cannot "rescue" itself using the custom loader, because that loader does not exist yet.

For modular projects (JPMS), you must also account for module path lookup, module readability, and accessibility. The simple `-cp .` example above uses the unnamed module and avoids complex module constraints. Do not apply every classpath example verbatim to applications packaged as named modules or custom runtime images.

### 6.4. Frameworks and JAR Launchers May Manage Their Own Loaders

An application launched via a custom launcher, nested JARs, or a framework may configure its own class loaders and TCCL. Simply setting `java.system.class.loader` **does not guarantee** changing the loading mechanism for every library or framework. Determine whether a library is calling:

- `ClassLoader.getSystemClassLoader()`;
- `Thread.currentThread().getContextClassLoader()`;
- `SomeClass.class.getClassLoader()`;
- or a loader held internally by the framework.

Each of these can return a different object within the same process.

### 6.5. Parent-First Is Not Mandatory for All Custom Loaders

`ClassLoader.loadClass` uses delegation by default, but subclasses can change that policy. Child-first loading helps load private library versions, but it can easily cause type identity issues, `ClassCastException`, or `LinkageError` if the same API is defined twice.

For a system loader, changing the policy too broadly can break libraries that expect common types to be shared through the parent. Restrict overrides to specific packages and rely on shared type contracts from the parent loader when needed.

## 7. Common Startup Errors

### 7.1. Provider Class Not Found

Example command:

```bash
java -Djava.system.class.loader=com.example.Missing -cp . SystemLoaderDemo
```

When the property is declared but the class cannot be loaded, per `getSystemClassLoader()` the JVM may throw an **`Error`**, often with the root cause in `getCause()`. Check the binary name spelling, package, classpath/module path, bytecode version, and availability of the provider class.

**Do not expect to catch this inside `main`:** because setup happens during startup, the program can terminate **before `main` runs**.

### 7.2. Wrong Constructor Signature

```java
// Violates the java.system.class.loader contract:
public CustomSystemLoader() {
    super();
}
```

This snippet illustrates an **invalid provider signature**. The JVM requires `public CustomSystemLoader(ClassLoader parent)`. If a matching public constructor does not exist, creating the system loader fails and the error may occur before `main`.

### 7.3. Constructor Throws an Exception

```java
public CustomSystemLoader(ClassLoader parent) {
    super(parent);
    throw new IllegalStateException("bad configuration");
}
```

This snippet illustrates a failure case, **not code to use in practice**. According to the JDK API, a constructor failure results in an `Error` during system loader creation, with the root cause accessible via `getCause()`. Avoid heavy logic, unready configuration dependencies, or complex plugin loading inside the constructor.

### 7.4. Calling `getSystemClassLoader()` in the Constructor: Initialization Cycle

```java
public CustomSystemLoader(ClassLoader parent) {
    super(parent);

    // WRONG: the system loader is currently being created, risking an initialization cycle.
    ClassLoader wrong = ClassLoader.getSystemClassLoader();
}
```

This snippet is an **anti-pattern example** and does not compile standalone. The JDK specifies that if a recursive call is detected while creating the system loader from the property, the JVM throws `IllegalStateException`. Instead of calling `getSystemClassLoader()`, the constructor already receives the **parent** supplied by the JVM.

A similar mistake is calling the no-arg `super()` constructor. That constructor defaults to looking up `getSystemClassLoader()` as its parent, which can trigger the exact cycle you want to avoid. **Always use `super(parent)` for a simple provider.**

### 7.5. Changing the Property After Startup

```java
System.setProperty(
    "java.system.class.loader", "OtherSystemLoader");
```

Do not treat this as replacing the already-initialized system loader instance. The `getSystemClassLoader()` contract checks the property when initializing the system loader; calling `setProperty` later only changes the property value, not a "hot swap" API for the loader.

### 7.6. Cast Errors When Reusing a Class with the Same Name

Suppose `com.example.Api` has already been defined by the parent, but the custom loader also defines another type with the exact same name. Java treats them as **two distinct types** if their defining loaders differ. Casts, method linkage, or interface assignments can fail even when logs print the same class name.

When diagnosing, log both the class name and its loader:

```java
Class<?> type = obj.getClass();  // obj must be non-null
System.out.println(type.getName());
System.out.println(type.getClassLoader());
```

Never assume `ClassLoader.getSystemClassLoader() == type.getClassLoader()` holds by default.

## 8. When Should You Choose `java.system.class.loader`?

**Consider it** when you need a system loader instance with behavior different from the default class loader and the relevant components **actually access it via the system loader**: specialized instrumentation or development tooling, a complex integrated runtime, or an application intentionally building a controlled default loading layer.

**Prefer an explicit loader first** if you only need to read plugin JARs from a directory, isolate an extension, or load classes on demand in one part of the application. This limits blast radius and simplifies unloading: use `URLClassLoader`, close resources properly when no longer needed, and release all references to classes, loaders, threads, and contexts if unloading is desired.

A decision checklist:

1. Does the target library **call `getSystemClassLoader()`**, or does it use TCCL or a custom loader?
2. Does the loader need to be replaced **right at startup**?
3. Can the provider be loaded by the default system loader and does it have the right **public constructor(ClassLoader)**?
4. Will the delegation policy keep **shared APIs** on the parent?
5. Do you have a plan to verify the loading path in the actual packaging environment (classpath, modules, Spring Boot launcher, test runner)?
6. Could a failure in the custom loader prevent the entire JVM from starting, and is that risk acceptable for the application?

If the answer is mainly "I just want to load plugins from a separate path," changing the global system loader is usually unnecessary.

## 9. Verifying with Built-in JVM Tools

### Identify the Active System Loader

```java
ClassLoader loader = ClassLoader.getSystemClassLoader();
System.out.println(loader.getClass().getName());
System.out.println(loader.getParent());
```

Output is VM-dependent; the class name and parent provide better evidence than inspecting the property value alone. In this article's example, the custom loader also logs when constructed by the JVM.

### Identify Which Loader Defined a Class

```java
Class<?> type = Class.forName(
        "DemoTarget",
        false,
        ClassLoader.getSystemClassLoader());

System.out.println(type.getClassLoader());
```

This illustrative snippet uses the class from the two-file demo. `Class.forName(name, false, loader)` looks up/loads and links the class without requiring initialization; `getClassLoader()` returns the **defining loader**, which is not necessarily the loader passed in.

### Log Class Loading Activity on HotSpot

```bash
java -Xlog:class+load=info -Djava.system.class.loader=CustomSystemLoader -cp . SystemLoaderDemo
```

HotSpot can log loaded types and their sources. Exact contents and ordering vary across Java versions and launchers; these logs are a diagnostic tool, not fixed stdout for the learning example.

### Test a Controlled Failure Case

You can temporarily set the property to a non-existent provider name to observe the startup error, then switch back to the valid example. No changes to `SystemLoaderDemo` source code are needed; the issue lies in the property or provider availability.

## 10. Common Misconceptions

1. **"`java.system.class.loader` is the name of an already-existing Java class loader."** False. The value is the **provider class name**; the JVM loads it with the default loader and calls the matching constructor to create the instance.
2. **"Simply subclassing `ClassLoader` is enough."** Not enough. The provider must have a **public constructor(ClassLoader)**.
3. **"The custom provider loads itself."** False. The JVM loads the provider using the **default system loader** before creating the custom instance.
4. **"The new system loader must define all application classes itself."** False. Parent-first delegation allows the parent to define classes.
5. **"`loadClass` was called on the custom loader, so `clazz.getClassLoader()` must equal the custom loader."** False. `getClassLoader()` returns the defining loader; the caller or initiating loader may be different.
6. **"Calling `System.setProperty` in `main` changes the system loader."** False. The system loader is normally created before `main`; the property must be set at JVM startup.
7. **"Using `super()` in the provider constructor works just like `super(parent)`."** It risks an initialization cycle because `super()` looks up the system loader as its parent. Use the `parent` argument passed in.
8. **"This property replaces the bootstrap/platform loader."** False. It selects the system loader; the other loader tiers keep their own roles.
9. **"Every thread's TCCL always equals the system loader."** False. TCCL is per-thread state and can be changed by applications or frameworks.
10. **"This feature enables JVM-wide class hot reload."** False. Replacing the system loader at startup does not reload existing class definitions; hot reload/redefinition is a separate mechanism with its own conditions.
11. **"There is no risk if the constructor does complex work."** False. Provider loading errors, wrong constructor signatures, or initialization cycles can block startup before `main`.
12. **"A custom system loader can open any package or module by default."** False. Module/bytecode access and type resolution remain governed by JVM, module, and visibility rules.

## 11. Self-Check

**Q1.** Which constructor does `CustomSystemLoader` need so the JVM can select it via `-Djava.system.class.loader=CustomSystemLoader`?

**Answer:** `public CustomSystemLoader(ClassLoader parent)`. The provider class must be findable by the default system loader; the constructor uses that `parent` as its delegation parent.

**Q2.** Why does `system.loadClass("DemoTarget")` in the example run through the custom loader while `type.getClassLoader() == system` is `false`?

**Answer:** Because `super.loadClass` delegates the lookup for `DemoTarget` to the built-in parent; the parent defines the class and becomes the defining loader. The custom loader only initiates and returns the result of the call.

**Q3.** Can you call `System.setProperty("java.system.class.loader", "...")` after `main` starts to switch the system loader immediately?

**Answer:** No. Java does not provide a mechanism to replace the system loader instance by modifying the property after it has already been initialized.

**Q4.** In the provider constructor, why should you use `super(parent)` and avoid calling `ClassLoader.getSystemClassLoader()`?

**Answer:** Because the new system loader instance is currently being created; calling `getSystemClassLoader()` recursively can trigger an `IllegalStateException`. The constructor already receives the default loader to use as its parent.

**Q5.** A library calls `Thread.currentThread().getContextClassLoader()` and still gets the old loader. Does that prove the property is not working?

**Answer:** No. TCCL is per-thread state and can be changed by a framework or application; you must inspect TCCL, the system loader, and the defining loader separately.

**Q6.** You want to load a plugin JAR from a separate path without changing the application's default class loading. Which option should you prefer?

**Answer:** A dedicated custom/`URLClassLoader` explicitly passed to the plugin component, rather than replacing the global system loader for a localized need.

## 12. Decision Flowchart

```text
Need to load classes from a custom source / path?
                         |
                         v
     Does any component require getSystemClassLoader()
          and need application-wide impact?
              /                         \
             No                         Yes
              |                          |
   Create a dedicated loader       Set property at startup:
   and use it directly             java.system.class.loader
              |                          |
   Manage plugin/lifecycle         Provider findable by default loader?
                                      |
                                      v
                              public constructor(ClassLoader)?
                                      |
                                      v
                              super(parent), design delegation
                                      |
                                      v
                                Run demo / observe loader
                                and actual defining loader
```

**Remember these three key points:** `java.system.class.loader` selects **which system loader instance is published**, the JVM creates that instance via **`public constructor(ClassLoader parent)`** passing the **default system loader** as the parent, and **which loader actually defines each class** depends on delegation and bytecode lookup. Keeping these three points clear avoids most mistakes when changing application-level loaders.

### References

- [Java SE 17 — ClassLoader.getSystemClassLoader()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html#getSystemClassLoader())
- [Java SE 21 — ClassLoader API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html)
- [Java SE 17 — URLClassLoader API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html)
- [JVMS §5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3)
