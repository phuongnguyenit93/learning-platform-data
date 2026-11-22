# Class.forName(String) and Default Loader Selection

`Class.forName(String)` is a familiar API when a Java program needs to obtain a `Class<?>` from a **class name at runtime**: looking up implementations from configuration, registering drivers, initializing plugins, or using reflection. The easiest point to misunderstand is the word “default”: the single-argument overload **does not automatically select the thread context class loader, does not always use the system loader, and does not define the class with the bootstrap loader just because the method is in `java.lang.Class`**.

According to Java SE 17, the call:

```java
Class<?> type = Class.forName("com.example.Service");
```

is equivalent in meaning to:

```java
Class<?> type = Class.forName(
        "com.example.Service",
        true,
        currentLoader
);
```

where **`currentLoader` is the defining class loader of the class calling `Class.forName(String)`**. `true` requests **class/interface initialization** if it has not been initialized beforehand. `currentLoader` is an explanatory notation from the specification, not a built-in variable in Java.

This lesson belongs to the **Class Loading API** group of Java core – classloader. We will distinguish the default loader from the system loader and the thread context loader; understand input names, loading–linking–initialization behavior, and compare the overloads; run an experimental program and handle common errors in plugin/module applications.

## 1. What Does `Class.forName(String)` Do?

Signature in Java 17:

```java
public static Class<?> forName(String className)
        throws ClassNotFoundException
```

`className` is the binary name of the class or interface to find; for array types, the API accepts array names following the `Class.getName()` convention. When invoked:

1. **Select loader by caller:** The JVM identifies *the class directly calling this method* and obtains the **defining loader** of that class.
2. **Find/load the class:** Requests that loader to find an already-loaded class or load the corresponding class, using the loader's delegation/module mapping mechanism.
3. **Link when needed:** The JVM ensures the linking conditions required by the operation, including appropriate resolution.
4. **Initialize:** For a regular class/interface, the effective initialization parameter is `true`; if the class has not yet been initialized, the JVM performs initialization before returning successfully.
5. **Return `Class<?>`:** That is the metadata/runtime identity object of the found class; the method **does not create an instance** of the target class.

If the class has already been initialized successfully, subsequent calls do not re-run the static initializer. If finding, linking, or initialization fails, the method reports the corresponding error.

### Three Loaders to Name Accurately

| Concept | How to Obtain | Meaning in `Class.forName(String)` |
| --- | --- | --- |
| **Loader of the calling class** | `Caller.class.getClassLoader()` | **Is the default choice** of the single-argument overload |
| **System/application loader** | `ClassLoader.getSystemClassLoader()` | Matches the default loader only when the calling class is actually defined by the system loader |
| **Thread context class loader (TCCL)** | `Thread.currentThread().getContextClassLoader()` | **Not automatically chosen by the single-argument overload**; to use it, pass it explicitly via the three-argument overload |
| **Bootstrap loader** | Typically represented as `null` in `Class.getClassLoader()` | Can be the default loader when the caller is defined by bootstrap; `null` also means selecting bootstrap when passed to the three-argument overload |
| **Loader of the returned class** | `type.getClassLoader()` | Defining loader of the **resulting class**; may differ from the loader used to start the lookup |

**Important:** “The loader used to start the lookup” and “the loader that defines the found class” are different. For example, the system loader is asked to find `java.lang.String`, yet parent delegation may return `Class<String>` defined by the bootstrap loader; `String.class.getClassLoader()` is typically `null`.

## 2. Why Can It Not Be Assumed to Be the System Loader by Default?

For a simple program run with `java -cp . Main`, `Main` is typically defined by the system/application loader. In that context, `Class.forName("pkg.Tool")` looks similar to `ClassLoader.getSystemClassLoader().loadClass("pkg.Tool")` because both calls typically start from the same loader.

That similarity **is not a general rule**:

- **Plugin loader:** The class `PluginEntry` is defined by its own loader; when code in `PluginEntry` calls `Class.forName("plugin.Helper")`, the default loader is the loader that defined `PluginEntry`. The system loader may have no visibility of `plugin.Helper` at all.
- **Shared library:** The class `LibraryHelper` is defined by a parent/system loader; if `LibraryHelper` itself calls `Class.forName(name)`, the call defaults to **the loader of `LibraryHelper`**, even when a plugin in a child loader invokes the helper's method.
- **Container/application server:** Each application may have its own loader. Two applications calling the same name `com.acme.Model` via caller classes in two different loaders may receive two different classes.
- **Custom module layer:** A module can be assigned to its own loader via `ModuleLayer`; a class in that module calling the single-argument overload uses the loader that defined the caller class, rather than automatically falling back to the system loader.
- **Bootstrap-defined caller:** If the caller code actually resides in a class defined by bootstrap, the defining loader is represented as `null`.

Therefore, one should ask **“which class contains the `Class.forName(...)` statement and who defined that class?”**, rather than only asking “where was the program launched from?”.

### Caller-Sensitive: The Caller of `forName` Itself Decides

The JDK marks certain APIs as *caller-sensitive* because their behavior must reflect the class at the call site. A wrapper method typically behaves differently from a plugin calling directly:

```java
public final class LibraryHelper {
    private LibraryHelper() { }

    public static Class<?> load(String name)
            throws ClassNotFoundException {
        return Class.forName(name);
    }
}
```

This is a **complete, compilable class**, without `main`. When a plugin calls `LibraryHelper.load("plugin.Widget")`, the class executing the `Class.forName` call is **`LibraryHelper`**. If `LibraryHelper` is defined by a parent loader that cannot see `plugin.Widget`, the call may throw `ClassNotFoundException` even though the plugin loader can find the class.

There is no rule to “automatically walk back up the call stack to the originating application/plugin to borrow its loader”. If a helper needs to load classes within the plugin's domain, the API design should accept a `ClassLoader` or `ModuleLayer`/`Module` explicitly.

## 3. Java 17+ Example: Changing the TCCL While the Single-Argument Overload Still Uses the Caller Loader

Create a file **`ForNameDemo.java`**:

```java
public class ForNameDemo {
    static class Target {
        static {
            System.out.println("Target initialized");
        }
    }

    static class Deferred {
        static {
            System.out.println("Deferred initialized");
        }
    }

    static class ArrayElement {
        static {
            System.out.println("ArrayElement initialized");
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader callerLoader = ForNameDemo.class.getClassLoader();
        ClassLoader isolated = new ClassLoader(null) { };

        Thread thread = Thread.currentThread();
        ClassLoader previous = thread.getContextClassLoader();

        thread.setContextClassLoader(isolated);
        try {
            System.out.println("caller loader is context: "
                    + (callerLoader == thread.getContextClassLoader()));

            System.out.println("one arg");
            Class<?> target = Class.forName("ForNameDemo$Target");
            System.out.println("found target: " + (target == Target.class));

            try {
                Class.forName("ForNameDemo$Target", false, isolated);
                System.out.println("unexpected");
            } catch (ClassNotFoundException expected) {
                System.out.println("explicit context: not found");
            }

            Class<?> deferred = Class.forName(
                    "ForNameDemo$Deferred", false, callerLoader);
            System.out.println("deferred loaded: "
                    + (deferred == Deferred.class));

            System.out.println("initialize deferred");
            Class.forName("ForNameDemo$Deferred", true, callerLoader);

            Class<?> array = Class.forName(
                    "[LForNameDemo$ArrayElement;");
            System.out.println("array found: " + array.isArray());

            System.out.println("initialize component");
            Class.forName("ForNameDemo$ArrayElement");
        } finally {
            thread.setContextClassLoader(previous);
        }
    }
}
```

Compile and run with JDK 17+:

```bash
javac --release 17 ForNameDemo.java
java -cp . ForNameDemo
```

Expected stdout on standard Java SE when run on the application class path:

```text
caller loader is context: false
one arg
Target initialized
found target: true
explicit context: not found
deferred loaded: true
initialize deferred
Deferred initialized
array found: true
initialize component
ArrayElement initialized
```

### Why Do the Lines Appear in This Exact Order?

1. `ForNameDemo` is defined by the application loader when running `java -cp .`. `isolated` is a custom loader with parent `null` (delegating to bootstrap) and does not have the `ForNameDemo$Target` bytecode.
2. After setting `isolated` as the TCCL, `callerLoader == thread.getContextClassLoader()` returns `false`.
3. `Class.forName("ForNameDemo$Target")` executes **directly inside `ForNameDemo.main`**, so it uses the loader of `ForNameDemo`, not the TCCL. The class is found and the initializer prints `Target initialized` before the API returns.
4. `Class.forName(name, false, isolated)` uses the exact custom loader passed in. That loader does not have the target class and neither does its bootstrap parent, so it throws `ClassNotFoundException`.
5. `Class.forName("ForNameDemo$Deferred", false, callerLoader)` obtains `Class<?>` but **does not run** the static block yet. Only the subsequent call with `true` prints `Deferred initialized`.
6. `Class.forName("[LForNameDemo$ArrayElement;")` looks up the **array** class; the component type may be loaded, yet the static initializer of `ArrayElement` **is not forced to run simply because the array class is looked up**. Only the subsequent single-argument call using the component name prints `ArrayElement initialized`.
7. The previous TCCL is restored in `finally` to avoid affecting other operations on the same thread.

The example above intentionally uses **two different loaders** and **three kinds of initialization** to demonstrate the API's behavior. The result depends on the explicitly stated execution context: default JDK 17+, on the application class path, without an unusual custom loader system.

## 4. Comparing the Overloads and `ClassLoader.loadClass`

| API | Loader Selection | Initializes Regular Class? | If Not Found |
| --- | --- | --- | --- |
| `Class.forName(String name)` | **Defining loader of the caller** | **Yes**, if not yet initialized | `ClassNotFoundException` |
| `Class.forName(String name, boolean initialize, ClassLoader loader)` | **Passed-in loader**; `null` is bootstrap | According to `initialize` | `ClassNotFoundException` |
| `Class.forName(Module module, String name)` | **Passed-in module** and the loader associated with that module | **Does not require linking/initialization** per this overload's contract | Returns `null` if the class is not found in the module |
| `ClassLoader.loadClass(String name)` | Target loader on which it is called; uses `loadClass` policy | **Does not automatically request initialization** | `ClassNotFoundException` |
| `T.class` | Result is resolved by the compiler/JVM in the caller class's context | **Not triggered by the class literal alone** | Not a dynamic-name API; linkage error if the class dependency is invalid |

For `Class.forName(String, boolean, ClassLoader)`, the parameter `initialize = true` means **initializing the class/interface** when needed. If the class has already been initialized successfully, the JVM does not re-initialize it.

`ClassLoader.loadClass(name)` **is not an equivalent replacement** for `Class.forName(name)`: it returns `Class<?>` without automatically triggering initialization. A subsequent usage step such as calling a static method, accessing a non-compile-time-constant static field, or creating a new instance may force initialization.

The `Class.forName(Module, String)` overload was introduced to identify the target module more explicitly. It accepts a **binary name**, does not accept array names the way the string/loader overloads do; it returns `null` if the target module does not contain the requested class. This method does not guarantee that the class has been linked or initialized; using its members still requires following JVM/module access rules.

## 5. One or Three Arguments: Choosing the API by Intent

### Case A – Knowing the Target Class Is in the Same Loader Domain as the Caller

Use:

```java
Class<?> type = Class.forName("com.example.local.Handler");
```

This is an **illustrative snippet** that only works if the corresponding class exists and is accessible through the caller class's loader. It suits programs with a single application loader or code that intentionally wants to use its own namespace.

### Case B – Needing to Select the Plugin's Loader

Use the three-argument overload:

```java
public static Class<?> loadPluginType(
        String binaryName, ClassLoader pluginLoader)
        throws ClassNotFoundException {
    return Class.forName(binaryName, true, pluginLoader);
}
```

This is a **complete illustrative method** that needs to be placed inside a class. To only look up the type and avoid static side effects before execution is needed, consider `false`:

```java
Class<?> pluginType =
        Class.forName(binaryName, false, pluginLoader);
```

`false` does not guarantee that “no work at all occurs”: the JVM may still load/link the class and required dependencies. It only states that **initialization of the target class is not requested** during this call.

### Case C – Library/Framework Receiving Plugins via TCCL

Some frameworks (for example, provider discovery mechanisms) deliberately use the **thread context class loader** to locate implementations defined by child loaders. If that is the desired contract:

```java
ClassLoader contextLoader = Thread.currentThread()
        .getContextClassLoader();

Class<?> implementation =
        Class.forName(binaryName, true, contextLoader);
```

The snippet above assumes `binaryName` is defined, the context loader is appropriate, and the code resides in a method that handles `ClassNotFoundException`. If the TCCL is `null`, the three-argument overload uses the **bootstrap loader**, without automatically switching to the system loader. If a framework needs a `system` fallback when the TCCL is null, it must **write an explicit fallback policy** per the framework's contract.

The TCCL is mutable state belonging to a thread. When temporarily assigning it for a plugin request or service discovery, always restore the previous loader in `finally`, especially when threads are reused by a thread pool.

### Case D – Class Belonging to a Specific Named Module

If the module is already known:

```java
Module module = /* target module in the appropriate layer */;
Class<?> type = Class.forName(module, "com.example.api.Service");
if (type == null) {
    throw new IllegalArgumentException("Class not in target module");
}
```

This is **illustrative code**; `module` must be obtained from an actual module. For an application-created module layer, you can obtain the loader via `layer.findLoader("m.plugin")` and use the three-argument overload if you also need to **initialize** that class. Do not assume that a class in a custom `ModuleLayer` is always present via the system loader.

## 6. Input Names: Binary Names and Array Type Names

`Class.forName(String)` accepts the **binary name** of a class/interface; for member classes, it uses `$` instead of the `Outer.Inner` syntax of Java source. For example:

| Type to Find | Valid Name |
| --- | --- |
| Regular class | `java.lang.String` |
| Member class | `java.util.Map$Entry` |
| `String[]` | `[Ljava.lang.String;` |
| `String[][]` | `[[Ljava.lang.String;` |
| `int[]` | `[I` |

Use `SomeType.class.getName()` to observe the actual name, especially with nested classes. The strings `java/util/Map$Entry`, `java.util.Map.Entry`, and `java.lang.String[]` are not the corresponding lookup names for the types in the table. `"int"` and `"void"` do not return the primitive/void class; use `int.class` or `void.class`.

Array classes have their own rule: `Class.forName("[Lpkg.Component;")` may load the component type but does not initialize the component simply because of the array lookup. Details on each parameter, error symptoms, and additional loader-based lookup examples are covered in greater depth in the lesson on the three-argument overload.

## 7. Why Can `forName` Trigger `<clinit>`?

Class initialization occurs during the phase when the JVM must complete initializing the class before the requesting operation proceeds. The single-argument overload of `Class.forName` has `initialize = true`, so when the class has not yet been initialized, static field initializers and static blocks (represented by the compiler as `<clinit>` when needed) will run.

Example:

```java
public class InitOnlyDemo {
    static class Configuration {
        static final int VALUE = initialize();

        static int initialize() {
            System.out.println("Configuration initialized");
            return 10;
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("before");
        Class<?> type = Class.forName(
                "InitOnlyDemo$Configuration");
        System.out.println("after");
        System.out.println("class: " + type.getSimpleName());
    }
}
```

```bash
javac --release 17 InitOnlyDemo.java
java -cp . InitOnlyDemo
```

Exact stdout:

```text
before
Configuration initialized
after
class: Configuration
```

There is no `new Configuration()` or manual method call; `Class.forName` alone requested initialization. With `Configuration.class`, the class literal itself does not force the initializer to run.

**Note on constants:** If code only reads a `static final int X = 10` that is a *constant variable* in source, the compiler may inline the value and therefore not need to initialize the declaring class. However, `Class.forName("SomeClass")` **still requires initialization** of `SomeClass`, regardless of whether the class has constant fields or not; the two kinds of operations must not be conflated.

### `forName` with an Array Differs from the Component Class

If `name` is an array class name, the API returns the `Class<?>` of the **array**; the component type is loaded but **not initialized** simply by calling `forName` with the array name. The example in the `ForNameDemo` section showed that `"[LForNameDemo$ArrayElement;"` does not execute the `ArrayElement` static block. Do not assume that `true` will initialize the component class in all cases.

## 8. Handling Errors Accurately

The API may throw **`ClassNotFoundException`**, **`LinkageError`**, and **`ExceptionInInitializerError`** in different situations:

| Situation | Typical Result | Meaning |
| --- | --- | --- |
| Selected loader cannot find the binary name | `ClassNotFoundException` | The class is not available through that loader/delegation scope |
| Class file exists, but a linkage dependency fails or the class has incompatible bytecode | `LinkageError` (or a subclass) | The JVM could not complete linking as required |
| Static initializer throws an exception that is not an `Error` | `ExceptionInInitializerError` | `<clinit>` failed during the first initialization |
| Class previously failed initialization and is used again | Usually `NoClassDefFoundError` | The class is in an erroneous state and will not automatically retry running its initializer |
| Attempting to load the primitive name `"int"` | Usually `ClassNotFoundException` | The API is not used to obtain primitive classes |
| Class is found, but subsequent code is not allowed to access a member | `IllegalAccessException`, `IllegalAccessError`, or the corresponding reflection exception | Finding a class does not mean having permission to use all of its members |

`ExceptionInInitializerError` is a subclass of `LinkageError`. If code needs to log errors separately, place the more specific catch before catching `LinkageError`; one should not necessarily catch these errors to continue execution, because the class may already have transitioned into an erroneous state.

### Initialization Failures on the First and Subsequent Attempts

When `<clinit>` throws an exception that is not an `Error`, the JVM typically wraps it in `ExceptionInInitializerError` on the first trigger. The class becomes **erroneous**, so the next active use of the **same runtime class** typically receives `NoClassDefFoundError`, without re-running the initializer. Therefore, the stack trace and cause of the first error should be preserved. The lesson on the `Class.forName(name, initialize, loader)` overload specifically practices this scenario with two `initialize=true` calls.

## 9. Why Does Loading a Class Not Guarantee It Can Be Used?

`Class.forName` is an API for **finding class metadata**. Being able to obtain a `Class<?>` does not prove:

- A no-argument constructor exists to create an instance.
- The class is not abstract or an interface.
- The caller has permission to invoke the constructor or private methods.
- The named module has `exports` or `opens` on the package for the required access.
- The client and the plugin class use **the same interface definition**; in Java, type identity is binary name + defining loader.
- The class's dependencies will link successfully along all code paths invoked later.

Code example:

```java
Class<?> type = Class.forName(binaryName, false, pluginLoader);
Object instance = type.getDeclaredConstructor().newInstance();
```

This is an **illustrative snippet**, assuming `binaryName` and `pluginLoader` are available, the class has an accessible constructor, and exceptions are handled. The first line with `initialize=false` only looks up the class. The second line may trigger initialization when creating the instance, while also having to pass access/module checks and potentially throwing exceptions from the constructor.

If the plugin implements a host interface, you should check:

```java
Class<?> type =
        Class.forName(binaryName, true, pluginLoader);
if (!PluginApi.class.isAssignableFrom(type)) {
    throw new IllegalArgumentException(
            "Not an implementation of PluginApi");
}
```

This is **illustrative code**, assuming `PluginApi` belongs to a shared API that both the host and the plugin resolve to **the same `Class<?>`**. When each loader defines its own copy of `PluginApi` with the same name, the assignability check can fail even though the interface name is identical; fix the class loader/delegation layout, not just the `forName` string.

## 10. Should `Class.forName` Be Used to Trigger Driver Registration?

In older JDBC versions, many examples called:

```java
Class.forName("com.example.jdbc.Driver");
```

to force the driver's static initializer to register with `DriverManager`. This is a **historical pattern** illustrating a side effect of `forName`; the string `com.example.jdbc.Driver` above is only an illustrative name and does not represent an actual existing driver.

In modern JDBC 4+, compatible drivers are typically discovered through the **service-provider mechanism** when the JAR/module is packaged properly. Therefore, you should not add `Class.forName` by default to every JDBC application or assume it is the only way to register a driver.

If a driver is not detected, investigate dependencies, `META-INF/services/java.sql.Driver` or the module `provides` declaration, the TCCL, the module system, and the driver manager. `Class.forName` can force initialization of a specific class given the right loader, but it cannot fix all service discovery or binary compatibility errors.

## 11. Loader Issues in Multi-Module or Plugin Applications

Suppose the host uses the system loader and each plugin has its own loader:

```text
               [system loader]
                  /         \
          [plugin A]       [plugin B]
           demo.Impl        demo.Impl
```

If code in **plugin A** calls `Class.forName("demo.Impl")`, the API defaults to using the defining loader of the caller class belonging to plugin A (assuming the caller is defined by plugin A); the result can be A's `demo.Impl`.

If the **host/helper** in the system loader itself calls `Class.forName("demo.Impl")`, the class may not be found because the system loader does not look down into child plugin loaders. If **plugin B** calls it, it may receive `demo.Impl` defined by plugin B — **two non-identical `Class<?>` objects**.

This does not mean `forName` accidentally “switches loaders by thread name”. It selects based on **the definition of the caller class at the call site**, while each loader executes its own lookup policy. The same `"demo.Impl"` string can yield different results while still adhering to the API contract.

### Designing Explicit Helpers

In a library developed for multiple loaders, provide an overload that accepts a loader parameter:

```java
public final class PluginClasses {
    private PluginClasses() { }

    public static Class<?> find(
            String binaryName,
            boolean initialize,
            ClassLoader loader) throws ClassNotFoundException {
        return Class.forName(binaryName, initialize, loader);
    }
}
```

This class **compiles with Java 17+** and requires no specific framework. Instead of depending on the loader of `PluginClasses` itself, the caller chooses the loader appropriate for the requested plugin/layer. However, do **not** arbitrarily pass the TCCL or system loader: decisions should come from the plugin architecture regarding namespaces, shared APIs, lifecycle, and access permissions.

If a plugin loader needs to be unloaded, avoid keeping `Class<?>` references or plugin class instances in static caches that outlive the plugin, because those references can retain the loader and prevent garbage collection.

## 12. How to Diagnose Which Loader a `forName` Call Is Using

Add logging close to **the exact call site of `Class.forName(String)`**:

```java
ClassLoader callerLoader = MyCaller.class.getClassLoader();
ClassLoader systemLoader = ClassLoader.getSystemClassLoader();
ClassLoader tccl = Thread.currentThread().getContextClassLoader();

System.out.println("caller=" + callerLoader);
System.out.println("system=" + systemLoader);
System.out.println("tccl=" + tccl);

Class<?> result = Class.forName(binaryName);
System.out.println("defined by=" + result.getClassLoader());
System.out.println("module=" + result.getModule());
```

This is an **illustrative snippet**, assuming `MyCaller` is the actual class containing the code at the call site, `binaryName` is valid, and `ClassNotFoundException` is handled. Do not use `MyCaller.class.getClassLoader()` in a non-caller class and mistake it for the effective loader.

Troubleshooting sequence:

1. **Identify the direct call site:** Which class contains the statement? Does it go through a wrapper/helper defined by another loader?
2. **Compare loaders:** Print the defining loader of the caller, system, and TCCL; remember that `null` typically represents bootstrap.
3. **Verify the exact name:** Binary name of member/nested classes, array names, or package names. Do not pass an invalid source canonical name for a nested class.
4. **Check the class path/module layer:** Which loader is the class actually defined for? Is it located in a child loader while the call originates from a parent?
5. **Distinguish the failure stage:** `ClassNotFoundException` means class lookup failed; `ExceptionInInitializerError` means initialization failed; `NoClassDefFoundError` may indicate a missing dependency or an erroneous class.
6. **Check module access:** Can the class be found, yet reflection/invocation is blocked by `exports`/`opens` or Java access rules?
7. **Fix loader selection at the API boundary:** Pass a `ClassLoader`/`Module`/`ModuleLayer` when the context needs to be explicit; avoid changing the application-wide TCCL as a temporary patch for a single call.

On HotSpot, you can enable logging for class loading:

```bash
java -Xlog:class+load=info -cp . ForNameDemo
```

This log reports **loading**, not sole proof of caller-sensitive selection or the timing of class initialization. Observe output from the static block and the `getClassLoader()` value at the exact call site for more accurate analysis.

## 13. Frequently Asked Questions

**Q1.** Why does `Class.forName("java.lang.String")` work even though the caller is in the application loader?

**Answer:** The application loader can delegate through the platform/bootstrap loader to obtain `String`. The default loader starting the request is the caller's, but the returned class is defined by bootstrap.

**Q2.** If the TCCL points to the plugin loader, does `Class.forName("plugin.Driver")` automatically use the plugin loader?

**Answer:** No. The single-argument overload uses the defining loader of the caller class. To use the TCCL, retrieve `Thread.currentThread().getContextClassLoader()` and pass it through the three-argument overload according to your API policy.

**Q3.** If two methods both call `Class.forName("pkg.Type")` and get different results, is that an error?

**Answer:** Not necessarily. If the two methods reside in classes loaded by different defining loaders, the API can find two different definitions of `pkg.Type`. A class's JVM identity depends on **binary name + defining loader**.

**Q4.** Does `Class.forName(name, false, loader)` guarantee that the class has never been initialized?

**Answer:** No. It only **does not request** initialization during this call. The class may have already been initialized by another operation, and the call may still load/link whatever the JVM needs.

**Q5.** Has `Class.forName("pkg.Example")` called the constructor yet?

**Answer:** No. The class initializer `<clinit>` may run, whereas the instance constructor `<init>` only runs when an instance is actually created with `new` or reflection/an equivalent mechanism.

**Q6.** Why does `Class.forName("int")` not return `int.class`?

**Answer:** `int` is not the binary name of a class that a loader can look up like a regular class. Obtain the primitive class via `int.class` or `Integer.TYPE`. For primitive arrays, you can use array names such as `"[I"`.

**Q7.** Why does `Class.forName("[Lpkg.Component;")` not run the static initializer of `Component` even though the single-argument overload has `initialize=true`?

**Answer:** With an array name, the component type is loaded but **not automatically initialized** just from looking up the array class. Only a subsequent operation on the component that requires initialization will trigger it.

**Q8.** Does `Class.forName(Module, String)` initialize automatically?

**Answer:** No. This overload does not link or run the class initializer under the API contract, and if the class is not in the target module it can return `null`. It differs from the three-argument overload with `initialize=true`.

**Q9.** Why can a host in a parent loader not find a class in a child plugin loader even though the plugin calls the host API successfully?

**Answer:** Parent delegation mainly allows a child to query its parent, rather than automatically making the parent see all classes defined by the child. When the host needs plugin classes, intentionally pass the loader/plugin layer or use an appropriate discovery mechanism.

**Q10.** Can all errors from `forName` be caught with `catch (ClassNotFoundException e)`?

**Answer:** No. Linking and initialization failures can be `LinkageError`, including `ExceptionInInitializerError` or `NoClassDefFoundError` in specific situations.

## 14. Short Exercises with Answers

**Exercise 1.** In `ForNameDemo`, explain why `Class.forName("ForNameDemo$Target")` succeeds when the TCCL has been assigned a loader that cannot find `Target`.

*Answer:* The caller is `ForNameDemo`, so the single-argument overload uses the defining loader of `ForNameDemo`. It does not read the TCCL. The custom loader `isolated` is only used in the explicit three-argument call.

**Exercise 2.** A library `FrameworkHelper` defined by the system loader receives a plugin class name `com.acme.PluginImpl` and calls `Class.forName(name)`, but throws `ClassNotFoundException`. Where does the API boundary need to change?

*Answer:* Have the plugin/module layer pass the appropriate loader or module context into the helper, then use `Class.forName(name, initialize, loader)` or the corresponding module API. Changing the thread's TCCL is not enough if the helper still uses the single-argument overload.

**Exercise 3.** What can the following code print?

```java
Class<?> c = Class.forName("java.lang.String");
System.out.println(c.getClassLoader() == null);
```

*Answer:* On standard Java SE, it prints `true` because `String` is defined by bootstrap. The caller class may reside in the application loader, but the loader of the resulting class is determined through delegation.

**Exercise 4.** Does `Class<?> c = Class.forName("pkg.Type", false, loader);` prevent `pkg.Type` from being initialized later?

*Answer:* No. It avoids requesting initialization **during the current call**. The first call to a static method, instance creation, or another requiring operation will force initialization if the class has not yet been initialized.

**Exercise 5.** Why are the loader used to return `Class<?>` and the ability to use a constructor via reflection two different questions?

*Answer:* Loading/class lookup provides a `Class<?>` object. Constructor invocation also requires the class to be ready for initialization, a matching constructor, and Java/module access conditions. The later steps can fail even when class lookup has already succeeded.

## Key Takeaways

Whenever you see `Class.forName(name)`, read it as **“find and request initialization of the class using the defining loader of the class containing this call”**. If the system involves plugins, an application server, a custom `ModuleLayer`, or a TCCL, clearly identify the **caller class**, **defining loader**, **binary name**, **desired loader**, and **whether immediate initialization is needed**. Choose the three-argument overload or the `Module` overload when you need to express that choice explicitly.

Standard references:

- [Class – Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): Contracts for `Class.forName(String)`, `Class.forName(String, boolean, ClassLoader)`, and `Class.forName(Module, String)`.
- [ClassLoader – Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): Parent delegation, `loadClass`, and built-in loaders.
- [JLS 17, 12.4 – Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4): Initialization timing and error behavior.
- [JVMS 17, 5 – Loading, Linking and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): Defining/initiating loaders, type identity, and linking mechanisms.
