# On-Demand Class Loading via `Class.forName` and `ClassLoader.loadClass`

Java allows a program to know a **class name as a string** and then ask the JVM to find and load that class when needed. Two very common APIs are `Class.forName(...)` and `ClassLoader.loadClass(...)`. They can return the same `Class<?>` object, but they are **not synonymous regarding class initialization timing**, default class loader source, error handling, and level of lifecycle control.

This is foundational knowledge for reflection, JDBC drivers, plugin mechanisms, Dependency Injection containers, dynamic discovery, and investigating errors such as `ClassNotFoundException`, `NoClassDefFoundError`, or `ExceptionInInitializerError`. This article uses **Java SE 17** as its baseline, distinguishing behavior specified by the API/JLS/JVMS from decisions specific to the compiler/JVM/class loader.

## 1. Three distinct milestones before using a class

Read `Class<?>` as the **runtime representation of a type**, not a sign that `static {}` has already run. The JVM distinguishes **loading** (creating the class representation), **linking** (verification, preparation, resolution, where part of resolution may be deferred), and **initialization** (executing static field initializers/`<clinit>` according to rules).

For this article, the question is not to re-describe the entire JVM lifecycle, but **whether the two APIs that obtain `Class<?>` automatically request initialization**. `Class.forName(name)` usually requests initialization; `Class.forName(name, false, loader)` and `loader.loadClass(name)` do not actively do so. Even with `initialize=false`, loading/linking errors can still occur; merely having a `Class<?>` does not mean an instance has been created or the plugin lifecycle has run.

## 2. Two APIs: similar class-name input, different default semantics

### `Class.forName(String className)`

```java
Class<?> type = Class.forName("com.example.Plugin");
```

This is an **illustrative snippet**; the class `com.example.Plugin` is assumed to be on the appropriate classpath/module path. The single-parameter overload:

- Finds the class/interface by the provided **binary name**.
- Uses the **defining class loader of the class calling `Class.forName`** according to caller-sensitive rules, not `Thread.currentThread().getContextClassLoader()` by default.
- **Requests initialization** if the type has not been initialized and is an eligible class/interface.
- Can throw **`ClassNotFoundException`** (checked) when the class is not found, as well as appropriate linking or initialization errors.

If you only want to obtain metadata **without actively initializing**, the single-parameter overload is not a good choice. Use the overload with the `initialize=false` flag when appropriate.

### `Class.forName(String name, boolean initialize, ClassLoader loader)`

```java
ClassLoader loader = SomeCaller.class.getClassLoader();
Class<?> metadataOnly = Class.forName("com.example.Plugin", false, loader);
Class<?> ready = Class.forName("com.example.Plugin", true, loader);
```

This is also an **illustrative snippet**, not a standalone program; `SomeCaller` and `Plugin` are hypothetical names.

- `name`: binary name of the class/interface to find, or an array name form allowed by the API.
- `initialize=false`: requests loading and linking, but **does not actively initialize** the class.
- `initialize=true`: ensures initialization is performed if needed according to VM rules.
- `loader`: selects a specific loader; `null` represents the **bootstrap class loader** for this overload.
- A class that was already initialized earlier will **not re-run static initializers** just because `forName` is called again.

Note: a call to `forName(name, false, loader)` does not "lock" the class in an uninitialized state. **Another active use** in the application can cause the class to initialize before your next check. The `false` flag only states that the current call **does not request** initialization.

### `ClassLoader.loadClass(String name)`

```java
ClassLoader loader = Thread.currentThread().getContextClassLoader();
Class<?> type = loader.loadClass("com.example.Plugin");
```

**Illustrative snippet:** assumes the context class loader is not `null` and knows how to find the needed class.

- This API requests to **load** a class with the given binary name through the selected loader itself.
- The default `ClassLoader.loadClass(name)` implementation corresponds to the class loader's `loadClass(name, false)` mechanism: **does not require full resolve/link immediately**, and **does not request initialization**.
- A customized loader can decide the bytecode source and delegation policy; loading logic may differ between loaders.
- Returning `Class<?>` does not automatically run the target class's static block just because subsequent code intends to create an instance or use reflection.

There is a protected overload `loadClass(String name, boolean resolve)` used in class loader implementations. **`resolve=true` does not mean `initialize=true`**. Resolution/linking is different from initialization; moreover, that overload is **protected**, not a flag that an ordinary caller passes to public `loadClass(String)`.

### Quick comparison table

| API | Default loader used | Requests initialization? | Explicit loader selection? | Result |
| --- | --- | --- | --- | --- |
| `Class.forName(name)` | Caller's defining loader | **Yes** | Not in this overload | `Class<?>` |
| `Class.forName(name, true, loader)` | Passed-in loader | **Yes** | Yes | `Class<?>` |
| `Class.forName(name, false, loader)` | Passed-in loader | **No** | Yes | `Class<?>` |
| `loader.loadClass(name)` | The `loader` itself being called | **No** via default path | Yes, via loader instance | `Class<?>` |

**Practical rule:** If you must **ensure the class is initialized**, use `Class.forName(name, true, loader)` or a specified active use; if you only need `Class` to read metadata, choose `Class.forName(name, false, loader)` or `loader.loadClass(name)` depending on linking/loader needs and side-effect handling.

## 3. Java 17 program: observing the exact initialization order

Create file **`LazyLoadLab.java`**:

```java
public class LazyLoadLab {

    public static class Passive {
        static {
            System.out.println("Passive.<clinit>");
        }

        public static void ping() {
            System.out.println("Passive.ping");
        }
    }

    public static class Active {
        static {
            System.out.println("Active.<clinit>");
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader loader = LazyLoadLab.class.getClassLoader();
        String passiveName = LazyLoadLab.class.getName() + "$Passive";
        String activeName = LazyLoadLab.class.getName() + "$Active";

        System.out.println("1: loadClass");
        Class<?> passive = loader.loadClass(passiveName);

        System.out.println("2: forName(false)");
        Class<?> same = Class.forName(passiveName, false, loader);
        System.out.println("same=" + (passive == same));

        System.out.println("3: invoke static method");
        passive.getDeclaredMethod("ping").invoke(null);

        System.out.println("4: forName(true) again");
        Class.forName(passiveName, true, loader);

        System.out.println("5: forName(true) on another class");
        Class.forName(activeName, true, loader);

        System.out.println("6: done");
    }
}
```

Compile/run with JDK 17+:

```bash
javac --release 17 LazyLoadLab.java
java LazyLoadLab
```

**Exact stdout in this program**:

```text
1: loadClass
2: forName(false)
same=true
3: invoke static method
Passive.<clinit>
Passive.ping
4: forName(true) again
5: forName(true) on another class
Active.<clinit>
6: done
```

**Explanation:**

- `loader.loadClass(passiveName)` finds the class and returns the `Class` object **without printing `Passive.<clinit>`**.
- `Class.forName(passiveName, false, loader)` does not request initialization; in the same loader, both calls identify the same class, so `passive == same` is `true`.
- Getting the method with `getDeclaredMethod` to prepare reflection **is not yet a method invocation**; however, `Method.invoke(null)` on a static method is an active use and triggers initialization of `Passive` before running `ping`.
- The subsequent `Class.forName(passiveName, true, loader)` does not run the initializer a second time because the class has already been initialized.
- `Class.forName(activeName, true, loader)` causes `Active` to initialize and prints exactly one line from the static block.

The `<clinit>` marker in the output is a string explicitly printed by the example, not the name of a Java method that can be written in source and called directly. The compiler may generate a JVM `<clinit>` method containing static initializer code.

### Why not use `new Passive()` to test loading?

`new Passive()` is an **active use** that forces `Passive` to be initialized if it has not been initialized yet. It does not clearly show the difference between `loadClass` and `forName(false)`. For loading tests, avoid accidentally creating an instance, accessing a non-compile-time-constant static field, or calling a static method before the observation point.

## 4. When does the JVM initialize a class?

JLS §12.4.1 describes the times when a class/interface must be initialized immediately before the corresponding active use. Common cases:

- Creating an instance of the class with `new`.
- Invoking a **static method** declared by the relevant class/interface.
- Reading or writing a static field that is **not a constant variable** of the class/interface according to Java rules.
- Certain reflection operations that require initialization.
- Calling `Class.forName(name, true, loader)`.

Examples that **do not necessarily** trigger initialization of the component class:

- Obtaining a class literal via `SomeType.class`.
- Calling `ClassLoader.loadClass(name)`.
- Calling `Class.forName(name, false, loader)`.
- Creating an array `new SomeType[10]` (does not initialize the component class just because the array is created).
- Reading an eligible `static final` **constant variable** that the compiler has inlined at the usage site.

### Example verifying constant and class literal

File **`InitializationTriggers.java`**:

```java
public class InitializationTriggers {

    static class Values {
        static final int MAGIC = 42;
        static final int COMPUTED = compute();

        static int compute() {
            System.out.println("Values.<clinit>");
            return 99;
        }
    }

    public static void main(String[] args) {
        System.out.println("constant=" + Values.MAGIC);

        Class<?> type = Values.class;
        System.out.println("literal=" + type.getSimpleName());

        System.out.println("computed=" + Values.COMPUTED);
    }
}
```

```bash
javac --release 17 InitializationTriggers.java
java InitializationTriggers
```

**Stdout**:

```text
constant=42
literal=Values
Values.<clinit>
computed=99
```

`MAGIC` is a `static final int` initialized with a constant expression; reading it from the caller is usually inlined by the compiler and **does not cause `Values` to initialize**. The expression `Values.class` returns `Class<?>` and also does not initialize the class. `COMPUTED` is not a constant variable because it calls a method, so accessing `Values.COMPUTED` triggers initialization; `compute()` prints the middle line and returns `99`.

Do not generalize this to "no `static final` ever initializes a class": for example, `static final Object O = new Object();` or `static final int N = compute();` are not compile-time constant variables.

### Initialization can involve superclasses and interfaces

- When initializing a class, the JVM ensures the necessary **superclasses** are initialized first; there are also special rules for superinterfaces that declare default methods.
- Loading a subclass does not automatically mean the entire hierarchy has run its static initializers.
- Initializing an interface does not mean all of its superinterfaces are recursively initialized like classes.
- Initialization has a per-class/interface synchronization mechanism to prevent two threads from executing `<clinit>` concurrently; other threads may have to wait while one thread is initializing.

An important point in debugging: the order of static initializer logs can come from type dependency rules, **not only** from where the `forName` line is located.

## 5. Binary name, canonical name, and array name forms

APIs that accept a class name as a string usually require a **binary name** according to JLS rules, **not simply the display name in source**:

| Type | Name suitable for loading by string | Notes |
| --- | --- | --- |
| Top-level class `java.lang.String` | `java.lang.String` | Package/class name with dots |
| Nested class `Outer.Inner` | `Outer$Inner` | Binary name has `$` character for nested classes |
| A class in package `demo.` | `demo.Helper` | Package must match binary name in the class file |
| String array | `[Ljava.lang.String;` | Name following `Class.getName()`/descriptor-like array syntax |
| int array | `[I` | Array name form for primitive component |
| Primitive `int` | Do not use `Class.forName("int")` as a way to get the primitive class | Use `int.class` or `Integer.TYPE` |

With `Class.forName`, the source-style name `java.lang.String[]` is not the valid array name; `[Ljava.lang.String;` is the supported form. An array itself is an array class; **creating or loading an array class does not by default initialize the component class**.

Do not construct nested class names arbitrarily by replacing every dot with `$`. Use `SomeNested.class.getName()` if you already have the class literal, or the documentation for that type's binary name.

### Program to observe names and array forms

Create file **`NameForms.java`**:

```java
public class NameForms {
    public static class Nested {
    }

    public static void main(String[] args) throws Exception {
        ClassLoader loader = NameForms.class.getClassLoader();
        Class<?> nested = loader.loadClass(NameForms.class.getName() + "$Nested");

        System.out.println("nested=" + nested.getName());
        System.out.println("simple=" + nested.getSimpleName());
        System.out.println("array=" + Class.forName("[Ljava.lang.String;").isArray());
        System.out.println("intArray=" + Class.forName("[I").isArray());
        System.out.println("primitive=" + int.class.getName());
    }
}
```

```bash
javac --release 17 NameForms.java
java NameForms
```

**Stdout**:

```text
nested=NameForms$Nested
simple=Nested
array=true
intArray=true
primitive=int
```

The example places the class in the **default package**, so the nested class's binary name has the form `NameForms$Nested`. If placed in package `demo`, the prefix would be `demo.NameForms$Nested`.

## 6. Class identity: same binary name does not guarantee the same JVM class

A runtime class/interface is identified by its **binary name combined with its defining class loader**. Consequences:

- Two `Class<?>` objects for a class defined by the **same defining loader** represent the same runtime class; calling `loadClass`/`forName` again does not automatically spawn a "new version".
- Two **different** defining class loaders can define two classes with the **same binary name**, yet the JVM treats them as **two different types**.
- Therefore, two objects that look like "both are `plugin.Api`" may still not be castable to each other; method lookup, interface compatibility, and class identity do not rely on the string name alone.
- A loader **initiating** a load may receive a class actually **defined** by a parent loader; you must not equate "the loader I called `loadClass` on" with "the loader that actually defined the class" in all cases.

You can observe the returned class with:

```java
Class<?> type = Class.forName(name, false, loader);
System.out.println(type.getName());
System.out.println(type.getClassLoader());
```

This is an **illustrative snippet** with `name` and `loader` assumed to be already determined. `type.getClassLoader()` returns the defining loader; **`null`** usually represents the bootstrap loader. Avoid assuming that a class belonging to a JDK module must have a `null` loader, because Java 9+ also has the platform class loader and app class loader.

### Parent delegation is a common model, not a "only one loader exists" principle

`ClassLoader.loadClass` in its default implementation typically:

1. Checks whether the class has already been loaded by the loader (`findLoadedClass`).
2. If not, asks the parent loader first (or the bootstrap loader if there is no parent).
3. If the parent does not find it, uses `findClass` of the current loader.
4. If the caller requested resolution in the corresponding overload, may call `resolveClass`.

This is the common **parent-first delegation**. However, custom class loaders can change the search path, apply child-first for certain packages, or restrict namespaces. Being able to write a custom loader does not mean you can arbitrarily redefine system-protected packages.

For example, a separate loader can be used to isolate two versions of a library/plugin. You must clearly decide which shared API classes must be parent-loaded so plugin objects can be cast to the common interface; if both the plugin and the host load their own copy of the interface from two different loaders, casting can fail even though the binary names match.

## 7. Example of a common loader identity error in plugins

Suppose the host has an interface:

```java
package api;

public interface Plugin {
    String name();
}
```

And a plugin class:

```java
package impl;

public class PluginImpl implements api.Plugin {
    @Override
    public String name() {
        return "demo";
    }
}
```

**The two snippets are separate Java files by package**, not a single self-running file. For the host to cast `PluginImpl` to `api.Plugin`, the `api.Plugin` interface implemented by the plugin must correspond to the **same runtime class** as `api.Plugin` on the host side. The common implementation is to place the shared API in a parent loader and have the plugin loader delegate loading of that API.

If the plugin loader defines another copy of `api.Plugin` itself, both interfaces have the binary name `api.Plugin` but belong to two defining loaders: at runtime they are **not the same type**. In that case, `ClassCastException` or linkage/loader constraint errors can appear; this cannot be fixed by changing the cast in Java source.

### Do not confuse `Class<?>` with a plugin object

`Class.forName("impl.PluginImpl", true, loader)` returns a **`Class` object**, not an already-created `PluginImpl` object. To create an instance, you can use reflection with the appropriate constructor and check the type:

```java
Class<?> candidate = Class.forName("impl.PluginImpl", true, loader);
Object instance = candidate.getDeclaredConstructor().newInstance();
api.Plugin plugin = api.Plugin.class.cast(instance);
```

This is an **illustrative snippet**; it assumes a public no-arg constructor exists, the class is validly accessible under module/access rules, the loader is consistent for the shared API, and exceptions are handled. Do not assume `newInstance()` can create an object if the class is abstract, has no suitable constructor, or the module forbids reflection.

**`Class.forName` is not a dependency injection API**: it only finds/loads/initializes the class; choosing constructors, managing lifecycle, injecting dependencies, and startup/shutdown are upper-layer responsibilities.

## 8. Context ClassLoader in plugin and framework applications

`Thread.currentThread().getContextClassLoader()` (TCCL) provides a **context loader** that libraries/frameworks can actively use to locate plugins/providers in the context of the current thread.

Example snippet:

```java
ClassLoader context = Thread.currentThread().getContextClassLoader();
if (context == null) {
    throw new IllegalStateException("No context class loader");
}
Class<?> pluginClass = Class.forName("com.example.Plugin", true, context);
```

This is an **illustrative snippet**, not a standalone program; the plugin name is hypothetical.

Distinguish clearly:

- `Class.forName(name)` **does not automatically consult the TCCL**; the single-parameter overload uses the loader related to the **caller**.
- `Class.forName(name, initialize, context)` **is actively selecting** the TCCL.
- `context.loadClass(name)` uses the context loader obtained from the thread, but **does not request initialization**.
- Frameworks such as `ServiceLoader` have their own loader-selection rules per overload/API; for example, `ServiceLoader.load(Service.class)` by API typically uses the TCCL. You must read each framework's contract rather than inferring from `Class.forName`.

The TCCL is a **mutable per-thread context**. In a thread pool, a task may run with a context loader set earlier by the environment; a task that needs to change it should save the old loader and restore it in `finally` to avoid leaking effects to other tasks. Whether you have permission to set the TCCL or load classes also depends on the application's security environment and policies.

### Example TCCL restoration pattern

```java
Thread current = Thread.currentThread();
ClassLoader original = current.getContextClassLoader();
try {
    current.setContextClassLoader(pluginLoader);
    // Call framework that uses TCCL to look up provider.
    runDiscovery();
} finally {
    current.setContextClassLoader(original);
}
```

This is a **fragment** inside a method where `pluginLoader` and `runDiscovery()` already exist, not a standalone runnable program. This snippet does not change the defining loader of already-loaded classes; it only changes the context that some frameworks use to look up subsequent classes.

## 9. Errors and exceptions: do not equate `ClassNotFoundException` with `NoClassDefFoundError`

| Situation | Common symptom | Investigation direction |
| --- | --- | --- |
| `forName`/`loadClass` receives a class name not found via the selected loader | **`ClassNotFoundException`** (checked) | Binary name, package, classpath/module path, jar, loader |
| A class already references a dependency, but the JVM cannot define/load the dependency when needed | **`NoClassDefFoundError`** | Check cause, jar/runtime dependency, name, and loader |
| Class initialization runs static initializer and fails due to an eligible exception | Can be **`ExceptionInInitializerError`** | Find the root exception in static init, not just change the loader |
| Class was marked erroneous after an initialization failure; subsequent use | Can be **`NoClassDefFoundError`** “Could not initialize class ...” | Find the **first initialization failure**, do not confuse with a missing `.class` file |
| Invalid class file or malformed bytecode | **`ClassFormatError`**, **`VerifyError`** | Check format, class major version, and instrumentation |
| Runtime JVM is too old for the class-file major version | **`UnsupportedClassVersionError`** | Check the compiled class version and runtime |
| Method/field access is no longer valid due to binary mismatch | `NoSuchMethodError`, `IllegalAccessError`, `IncompatibleClassChangeError`... | Check binary compatibility, loader, package/module |

`ClassNotFoundException` is a checked exception usually reported by class-loading APIs when **the requested name is not found**. `NoClassDefFoundError` is a `LinkageError`; besides a missing dependency during linking, it can also occur after an **initialization failure**. You should not automatically treat both as the same error and catch/swallow both.

### Example illustrating failed class initialization

```java
public class InitFailure {
    static class Broken {
        static final int VALUE = compute();

        static int compute() {
            throw new IllegalStateException("startup failed");
        }
    }

    public static void main(String[] args) {
        try {
            Class.forName(InitFailure.class.getName() + "$Broken");
        } catch (ExceptionInInitializerError err) {
            System.out.println("initialization failed");
        }

        try {
            Class.forName(InitFailure.class.getName() + "$Broken");
        } catch (NoClassDefFoundError err) {
            System.out.println("class is erroneous");
        } catch (ClassNotFoundException err) {
            System.out.println("class not found");
        }
    }
}
```

**This is a standalone runnable Java 17 file** to illustrate the error path. Compile/run:

```bash
javac --release 17 InitFailure.java
java InitFailure
```

**Stdout in a JVM running the standalone program:**

```text
initialization failed
class is erroneous
```

The first `Class.forName` requests initialization of `Broken`; the static initializer fails, and the VM reports `ExceptionInInitializerError` because the source error is a `RuntimeException`. Afterward, the same class/loader is in the erroneous state, so the next initialization attempt can report `NoClassDefFoundError` because it can no longer be successfully initialized.

For real applications, **you should not "retry" by calling `forName` again in the same loader** and expect the initializer to run again. If recovery is needed, design the lifecycle and error handling proactively; reloading with a completely different loader also has consequences for type identity and resources, and is not a default patch for initialization bugs.

## 10. Reflection: reading metadata, initializing a class, and creating an object are three different things

Distinguish the operations:

| Operation | Requires creating an instance? | Requires initialization? |
| --- | --- | --- |
| `Class.forName(name, false, loader)` | No | No |
| `loader.loadClass(name)` | No | Not via the normal mechanism |
| `type.getName()`, `type.getDeclaredMethods()` | No | Not merely for inspecting metadata; dependency type resolution may occur |
| `Class.forName(name, true, loader)` | No | **Yes**, if needed |
| `type.getDeclaredConstructor().newInstance()` | **Yes** | **Yes**, before the instance is created/constructor runs |
| `type.getDeclaredMethod("run").invoke(null)` on a static method | No | **Yes**, before invoking the method if needed |
| `field.get(null)` on a normal static field | No | Usually an active use and requires initialization |
| `SomeClass.class` | No | Does not initialize by itself |

Reflection does not guarantee bypassing access checks. Java 9+ module boundaries can reject access to private internals via `setAccessible(true)` with `InaccessibleObjectException`, even when the class has been found. And `Constructor.newInstance` can wrap an error thrown by the constructor into `InvocationTargetException`; you must inspect the **cause** to know the real reason.

### Loading a class does not mean the object is "ready"

Class initialization running once does not mean all application services/resources are ready. A plugin may need constructor injection, runtime configuration, DB connections, or other lifecycle callbacks. Conversely, using `Class.forName(name, true, loader)` just to check **whether a class exists** can accidentally trigger expensive or dangerous static initialization.

## 11. Class loaders in Java 9+ modules and other overloads

Java 9 introduced the module system and added `Class.forName(Module module, String name)`. This overload differs from `forName(String, boolean, ClassLoader)`:

- Searches for the class by **name** in a **specific module** and may return `null` if the class is not found in that module.
- **Does not initialize** the class just because of the `Module` overload call; its contract also differs regarding linking and visibility checks.
- `module` does not automatically replace the class loader policy applied by the module system; classes also have a defining loader.
- Modules can enforce **readability/exports/opens** so that a class can be found while specific access operations remain restricted.

Example using the module API (Java 17):

```java
public class ModuleLookup {
    public static void main(String[] args) {
        Module module = String.class.getModule();
        Class<?> found = Class.forName(module, "java.lang.String");
        Class<?> missing = Class.forName(module, "java.lang.DoesNotExist");

        System.out.println("found=" + (found != null));
        System.out.println("missing=" + (missing == null));
    }
}
```

```bash
javac --release 17 ModuleLookup.java
java ModuleLookup
```

**Stdout**:

```text
found=true
missing=true
```

Use this overload when your goal is truly to **find a class within a module**, not simply to request initialization by class name. Do not mechanically replace `Class.forName(name, true, loader)` with `Class.forName(module, name)` and expect the static initializer to still run.

## 12. When should you use which API?

| Goal | Common choice | Reason |
| --- | --- | --- |
| Check/look up a class by name with caller loader semantics and want initialization | `Class.forName(name)` | Concise, requests initialization |
| Scan plugin classes using a known loader **without wanting side effects yet** | `Class.forName(name, false, pluginLoader)` | Allows inspecting metadata before initializing |
| Need a class via a custom class loader already held | `pluginLoader.loadClass(name)` | Uses that loader's mechanism; does not initialize by default |
| Want to explicitly initialize a class via a custom loader | `Class.forName(name, true, pluginLoader)` | Explicitly selects the loader and enables initialization |
| Create a plugin instance after validating the class type | `type.getDeclaredConstructor().newInstance()` | Creates the object and triggers initialization if needed |
| Framework lookup via TCCL | `Class.forName(name, ..., tccl)` or appropriate framework API | Avoids depending on the framework's own defining loader |
| Find a class in a specific Java module | `Class.forName(module, name)` | Targets the exact module; does not auto-initialize |
| Only need a class literal at compile time | `SomeType.class` | No string lookup needed; compiler checks the type name |

**Prefer type-safe code** when the class is known at compile time. Loading by string name is suitable for configuration and plugins, but loses compile-time name/class checking and can easily introduce loader, version, and runtime errors.

## 13. Practical plugin design points

### Separate discovery and startup

A reasonable workflow:

1. Read configuration or a list of plugin class names.
2. Choose the **right loader** according to the host's architecture, not an arbitrary system/app loader.
3. Load **without initializing** if metadata scanning is needed: `Class.forName(name, false, pluginLoader)`.
4. Check that the class implements/extends the API used by the host: `Plugin.class.isAssignableFrom(type)`.
5. Check instantiation prerequisites such as modifiers, constructors, and access permissions.
6. Actively initialize/create the object when the application is ready; handle errors within the lifecycle scope.
7. Start the plugin and release resources with explicit lifecycle hooks/framework mechanisms.
8. When unloading/reloading, manage class loaders, threads, static references, TCCL, and caches to avoid class loader leaks.

A minimal design pattern:

```java
Class<?> type = Class.forName(className, false, pluginLoader);
if (!Plugin.class.isAssignableFrom(type)) {
    throw new IllegalArgumentException("Not a Plugin: " + className);
}
Class<? extends Plugin> pluginType = type.asSubclass(Plugin.class);
Plugin plugin = pluginType.getDeclaredConstructor().newInstance();
plugin.start();
```

**This is an illustrative fragment**, assuming `Plugin` is the host's API, `className`/`pluginLoader` are valid, the plugin has a public no-arg constructor, and `start()` is defined. In real code, you need to handle checked exceptions, failed initialization states, shutdown, and module/access policies. `asSubclass` checks the runtime type relationship; it cannot rescue a situation where the `Plugin` API was defined by different loaders as two distinct types.

### Do not overuse static initializers to register every plugin

Legacy code sometimes calls `Class.forName("...Driver")` just so the static initializer self-registers the provider. This explains some older JDBC patterns, but is not a universal plugin mechanism. Modern Java has `ServiceLoader` and framework-specific mechanisms; choose them when you need standard discovery, dependency management, and lifecycle. Do not use `Class.forName` as a "plugin install command" regardless of the library.

## 14. Common misconceptions

| Misconception | Accurate understanding |
| --- | --- |
| "`loadClass` means the static block runs" | `loadClass(name)` does not request initialization |
| "`Class.forName(name)` only loads, does nothing else" | The single-parameter overload **requests initialization** |
| "The `resolve=true` flag is the `initialize=true` flag" | Linking/resolution is different from initialization |
| "`Class.forName(name)` always uses TCCL" | It uses the caller's loader under caller-sensitive semantics; TCCL must be selected explicitly if needed |
| "Two classes with the same name mean the same type" | The JVM also considers the **defining class loader** |
| "`Class.forName` returns a plugin instance" | It returns `Class<?>`; creating the object is a separate step |
| "`SomeClass.class` always initializes the class" | A class literal does not automatically request initialization |
| "Reading any `static final` never initializes the class" | Only eligible constant variables are handled under compile-time constant rules |
| "The first load will run `<clinit>`" | Loading and initialization are two separate phases |
| "If class init fails, the next `forName` will retry cleanly" | The class can become erroneous in the same loader; the next attempt reports `NoClassDefFoundError` |
| "`ClassNotFoundException` and `NoClassDefFoundError` have the same cause" | One is a checked exception for lookup, one is a linkage error with multiple causes, including prior init failure |
| "`Class.forName("int")` gets the primitive class" | Use `int.class`/`Integer.TYPE`; primitive names are not treated like normal binary class names |
| "`Outer.Inner` is always the string used for nested classes" | Binary names usually have `Outer$Inner` |
| "`Class.forName(module, name)` always initializes the class" | The `Module` overload **does not** request initialization |
| "If you chose a class loader, it is guaranteed to define the class" | Parent delegation can return a class defined by another loader |

## 15. Debugging workflow for failed class loading

When an error occurs, check in order:

1. **Name**: is the passed string value the exact binary name? Do nested classes use `$`? Do arrays use the right name? Was source-style `String[]` accidentally passed?
2. **API and flags**: does the code use `forName(name)`, `forName(name, false, loader)`, or `loader.loadClass(name)`? Is it triggering unintended initialization?
3. **Actual loader**: print `type.getClassLoader()` if loaded; distinguish app/platform/bootstrap/plugin loader and TCCL.
4. **Classpath/module path**: where is the jar actually located? Are there duplicate copies? Do the manifest, class path, module exports/opens, and launch mode match?
5. **Failure stage**: did the error happen during loading, verification/linking, initialization, or reflection/constructor?
6. **Nested cause**: for `ExceptionInInitializerError` check the cause; for `NoClassDefFoundError` check for a prior initialization failure and missing dependencies.
7. **Class identity**: are the host and plugin using the same API interface definition? Check the defining loader of both.
8. **Concurrency/lifecycle**: is another thread currently initializing the class? Does the static initializer block, hold a lock, perform I/O, or create a circular wait?
9. **JDK version**: is the class-file major version compatible with the runtime? For example, Java 17 is typically **major 61**, Java 8 is **major 52**.
10. **Necessity of reflection**: if `ServiceLoader` or a type-safe API can be used, consider replacing manual lookup mechanisms.

## 16. Self-check questions

**Question 1:** `ClassLoader.loadClass("demo.Plugin")` returns `Class<?>`. Is it guaranteed that `Plugin` has already run its static block?

**No.** Public `loadClass(name)` does not request initialization; initialization is a separate phase.

**Question 2:** Does `Class.forName("demo.Plugin")` automatically use the current thread's TCCL?

**Not by default.** It uses the loader associated with the caller. To use TCCL, obtain it and pass it into the three-parameter overload.

**Question 3:** Two loaders define two classes both named `demo.Plugin`; can an object from one loader be cast to the type from the other loader based solely on the matching name?

**No.** Runtime identity also depends on the defining loader, so these can be two different types.

**Question 4:** `Class.forName(name, false, loader)` returns; then `getDeclaredMethod("run").invoke(null)` calls a static method. When does initialization happen?

**When the invocation requires it**, if the class has not been initialized earlier; `forName(false)` does not trigger it on its own.

**Question 5:** Does reading `SomeClass.CONSTANT` always cause `SomeClass` to initialize?

**No.** If the field is a constant variable accessed under compile-time constant rules, the compiler may inline it and the class does not yet need to initialize.

**Question 6:** Why can calling `forName` a second time after a `<clinit>` error produce `NoClassDefFoundError`?

**Because the class is already in the erroneous state** for that loader; the JVM does not restart initialization afresh.

**Question 7:** Do `Class.forName(module, "java.lang.String")` and `Class.forName("java.lang.String")` have the same initialization contract?

**No.** The module overload searches within the module and does not request initialization; the single-string overload requests initialization.

## Authoritative reference materials

- [JLS Java SE 17 §12.2 — Loading of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.2): loading semantics and class loaders.
- [JLS Java SE 17 §12.3 — Linking of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.3): verification, preparation, resolution.
- [JLS Java SE 17 §12.4 — Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4): triggers and initialization order.
- [JVMS Java SE 17 §5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3): loading, defining/initiating loader.
- [JVMS Java SE 17 §5.4 — Linking](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4): linking rules.
- [JVMS Java SE 17 §5.5 — Initialization](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5): initialization procedure and errors.
- [`Class` API — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `forName` overloads, `getName`, `getClassLoader`.
- [`ClassLoader` API — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `findClass`, `resolveClass`, and delegation model.
- [`ServiceLoader` API — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): provider discovery and class loader.
- [`ClassNotFoundException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassNotFoundException.html), [`NoClassDefFoundError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoClassDefFoundError.html), [`ExceptionInInitializerError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ExceptionInInitializerError.html): identifying the error paths.

**Key takeaway:** `Class.forName(name)` is usually "**find + request initialization**"; `Class.forName(name, false, loader)` is "**find without initializing yet**"; `loader.loadClass(name)` is "**ask the loader to load without actively initializing**". When designing plugins, **class identity also includes the defining class loader**, and having `Class<?>` does not mean an instance has been created or the application lifecycle has run.
