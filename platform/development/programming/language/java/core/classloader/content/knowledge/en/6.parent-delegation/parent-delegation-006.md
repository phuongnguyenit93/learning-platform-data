# Distinguishing the Requested Loader from the Actual Defining Loader

## 1. A Confusing Scenario

Suppose an application has a child `ClassLoader` named `PluginLoader`:

```java
Class<?> type = pluginLoader.loadClass("com.example.api.Service");
```

A common misconception is: “Because `pluginLoader.loadClass(...)` was called, `Service` was defined by `pluginLoader`.” In reality, `PluginLoader` may **delegate** the request to its parent loader; the parent loader finds or has already loaded `Service` and returns **the parent's own class definition**. The child loader merely receives the returned result.

Therefore, three concepts must be separated:

1. **Requested loader** (*requested loader*): the `ClassLoader` object called to handle the request, such as `pluginLoader` in the example above.
2. **Initiating loader** (*initiating loader*, JVMS terminology): the loader recorded by the JVM as initiating the loading of a specific class/interface, which may be satisfied by delegating to another loader. This term relates to loading state and linkage constraints in the JVM.
3. **Defining loader** (*defining loader*): the loader that actually establishes the runtime definition of the class from binary data (typically via `defineClass`), or the bootstrap loader handled by the JVM for platform classes. **This is the loader that participates in runtime type identity.**

In the common flow, the loader initially called is the requested loader, and delegation can result in the defining loader being at the parent. You should not equate the specification's *initiating loader* concept with “any object whose `loadClass` method is called in the stack trace”: proper terminology must be used when analyzing JVM mechanisms.

### A Memorable Observation Rule

```java
Class<?> c = requestedLoader.loadClass("some.package.Type");
ClassLoader defining = c.getClassLoader();
```

- `requestedLoader` is where the developer sends the request.
- `c.getClassLoader()` returns the **defining loader** according to the Java API; `null` means the class was defined by the bootstrap loader.
- The two values **can differ** while the program remains completely correct.
- For a bootstrap-defined class, there is no ordinary Java `ClassLoader` object to compare against `null`.

The snippets above are illustrative, assuming the corresponding variables already exist.

## 2. Why Can the Requested Loader Differ from the Defining Loader?
When inheriting the default `ClassLoader.loadClass`, the child checks `findLoadedClass(name)`, queries the parent (or bootstrap if the parent is `null`), and only calls `findClass(name)` if the parent does not find it. Therefore, a call to `child.loadClass("api.Service")` can return **the exact `Class<?>` defined by the parent**, without creating a new class in the child.
```text
requested child → parent finds api.Service → returns parent's Class
requested child → parent does not find it → child.findClass → may define in child
```
This path is the default; custom loaders or JPMS can change the policy. When debugging, distinguish the `loadClass` call path from `result.getClassLoader()` (the defining loader). `loadClass` does not itself require initialization.

## 3. Comparison Table: Where Requests Arrive, Where Classes Are Found, and Where They Are Defined

| Scenario | Loader Receiving the Initial Request | Actual Defining Loader | Result |
| --- | --- | --- | --- |
| Child requests an API class already present in the application loader | Child | Application loader | Receives the same `Class` defined by the parent |
| Child requests `java.lang.String` | Child | Bootstrap loader | `String.class.getClassLoader() == null` |
| Parent does not have the plugin class; child has the JAR containing that class | Child | Child, if `findClass` defines it successfully | Child actually owns the plugin class definition |
| Two children both ask the parent about the same class | Child A and Child B | Parent | The two results can be the same `Class<?>` object |
| Two independent children each define the same binary name themselves | Child A and Child B | A and B respectively | Two different runtime types |
| Child-first loader prioritizes its own library version | Child | Usually the child for prioritized packages | Can coexist alongside the parent's version; API boundaries must be controlled |

**You cannot infer the defining loader from:** the JAR placement location, the variable name `pluginLoader`, the value of `Thread.currentThread().getContextClassLoader()`, or a call to `ClassLoader.getSystemClassLoader()`. You must inspect the actual returned class and how it was defined.

## 4. Java 17+: Experimenting with Requesting at the Child While Defining at the Parent

This complete example uses a `SharedApi` class loaded in the application and a `ProbeLoader` as the child loader. `ProbeLoader` has no class lookup path of its own; it attempts `findClass` only when the parent cannot satisfy the request. This clarifies parent-first delegation through the number of `findClass` calls.

Save `RequestedVsDefiningLoaderDemo.java`:

```java
public class RequestedVsDefiningLoaderDemo {

    public static final class SharedApi {
        public String message() {
            return "shared";
        }
    }

    static final class ProbeLoader extends ClassLoader {
        int localFindCalls;

        ProbeLoader(ClassLoader parent) {
            super(parent);
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            localFindCalls++;
            throw new ClassNotFoundException(name);
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader appLoader = SharedApi.class.getClassLoader();
        ProbeLoader child = new ProbeLoader(appLoader);

        Class<?> result = child.loadClass(SharedApi.class.getName());

        System.out.println("requestedIsDefining="
                + (child == result.getClassLoader()));
        System.out.println("sameRuntimeClass="
                + (result == SharedApi.class));
        System.out.println("findClassCalls=" + child.localFindCalls);
        System.out.println("stringFromBootstrap="
                + (child.loadClass("java.lang.String")
                        .getClassLoader() == null));

        Thread thread = Thread.currentThread();
        ClassLoader previous = thread.getContextClassLoader();
        try {
            thread.setContextClassLoader(child);
            System.out.println("tcclIsChild="
                    + (thread.getContextClassLoader() == child));
            System.out.println("tcclDefinesSharedApi="
                    + (result.getClassLoader() == child));
        } finally {
            thread.setContextClassLoader(previous);
        }
    }
}
```

Run with **JDK 17 or higher**:

```bash
javac RequestedVsDefiningLoaderDemo.java
java RequestedVsDefiningLoaderDemo
```

Stdout of the program on a normal run:

```text
requestedIsDefining=false
sameRuntimeClass=true
findClassCalls=0
stringFromBootstrap=true
tcclIsChild=true
tcclDefinesSharedApi=false
```

Explanation of each result:

1. `requestedIsDefining=false`: even though `child.loadClass(...)` was called, `SharedApi` is still defined by the application loader (the parent in this example).
2. `sameRuntimeClass=true`: the returned value is the exact `RequestedVsDefiningLoaderDemo.SharedApi.class`, not a “copy” of the class.
3. `findClassCalls=0`: the parent handled the request successfully, so the child loader did not need to attempt defining it in `findClass`.
4. `stringFromBootstrap=true`: even when the child receives the request, `java.lang.String` is defined by the bootstrap loader.
5. `tcclIsChild=true` indicates that the **thread context class loader** has been set to the child, but `tcclDefinesSharedApi=false` because changing the TCCL does not change the defining loader of an already loaded class.

The `finally` block restores the TCCL to prevent context leakage to other operations on the same thread, especially when using a thread pool.

### What Happens If You Call with a Name Not Present in the Parent?

Because `ProbeLoader.findClass` only increments the counter and throws `ClassNotFoundException`, a request such as `child.loadClass("example.Missing")` will traverse up through the parent, try `findClass` in the child, and then fail. In that case, `localFindCalls` increases. With the name `SharedApi`, the parent finds it first, so the `findClass` branch does **not** run.

Therefore, **calling `loadClass` does not mean calling `defineClass`**; local activity only occurs when the loading algorithm reaches the place where the class is defined.

## 5. When Is the Requested Loader Also the Defining Loader?

To see the opposite case, you can create a class that exists only in the plugin's own JAR/classes directory, and then ask `URLClassLoader` to load it. When the parent cannot find it, `URLClassLoader` looks up the bytecode via its URL and defines the class itself.

The following program uses the JDK's `JavaCompiler` to create a temporary test class in a separate directory, and then uses a `URLClassLoader` whose parent is the platform loader. No external libraries need to be downloaded.

Save `LocalDefinitionDemo.java`:

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public class LocalDefinitionDemo {
    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("loader-definition-");
        Path source = directory.resolve("sample/PluginType.java");
        Path compiled = directory.resolve("sample/PluginType.class");

        try {
            Files.createDirectories(source.getParent());
            Files.writeString(source,
                    "package sample; public class PluginType {}");

            JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
            if (compiler == null) {
                throw new IllegalStateException("A JDK is required");
            }
            int exit = compiler.run(
                    null, null, null,
                    "-d", directory.toString(), source.toString());
            if (exit != 0) {
                throw new IllegalStateException("Compilation failed");
            }

            URL url = directory.toUri().toURL();
            try (URLClassLoader pluginLoader = new URLClassLoader(
                    new URL[]{url},
                    ClassLoader.getPlatformClassLoader())) {

                Class<?> pluginType = pluginLoader.loadClass(
                        "sample.PluginType");
                Class<?> again = pluginLoader.loadClass(
                        "sample.PluginType");

                System.out.println("requestedIsDefining="
                        + (pluginType.getClassLoader() == pluginLoader));
                System.out.println("sameClassOnSecondRequest="
                        + (pluginType == again));
                System.out.println("parentDefinesPlugin="
                        + (pluginType.getClassLoader()
                                == ClassLoader.getPlatformClassLoader()));
            }
        } finally {
            Files.deleteIfExists(source);
            Files.deleteIfExists(compiled);
            Files.deleteIfExists(directory.resolve("sample"));
            Files.deleteIfExists(directory);
        }
    }
}
```

Run:

```bash
javac LocalDefinitionDemo.java
java LocalDefinitionDemo
```

Stdout when test compilation succeeds:

```text
requestedIsDefining=true
sameClassOnSecondRequest=true
parentDefinesPlugin=false
```

Explanation:

- The platform loader does not have the `sample.PluginType` class generated in the temporary directory.
- `URLClassLoader` proceeds to search within its URL, reads the class file, and defines the class: this time **requested loader = defining loader**.
- Calling `loadClass` again with the same loader and the same binary name returns the same `Class` definition; it does not create a second class in the same loader.
- Calling `close()` on `URLClassLoader` only releases resources such as JAR/file handles; it does not make already-defined classes immediately disappear. The JVM can only unload them when reachability and lifecycle conditions are met.

**Prerequisites to run:** you must use a JDK with a system compiler, not just a runtime without `ToolProvider.getSystemJavaCompiler()`. The program uses Java 17+ APIs and cleans up the test files after closing the loader.

## 6. Do Not Infer the Initiating Loader Solely from Java Calls
In the JVMS, the *initiating loader* is a role recorded by the JVM during loading; it can differ from the defining loader when delegation succeeds. However, you cannot count every `ClassLoader` object appearing on the call stack and declare all of them to be initiating loaders. `Class.getClassLoader()` only reports the **defining loader**; there is no API on `Class` that lists all initiating loaders.
`findLoadedClass(name)` in a subclass checks the classes that the JVM has recorded for this loader, including those it initiated through delegation. Do not treat that result as a list of classes whose bytecode the child read and defined itself. For the examples in §4–5, the definitive observable evidence is **the returned `Class<?>` object and its defining loader**.

## 7. Consequences at Plugin API Boundaries
Runtime class identity depends on **(binary name, defining loader)**. If two children each define `api.Event` themselves from the same bytecode, they create two runtime types; casting or `instanceof` across the boundary can fail. If both rely on the parent to load the same `api.Event`, they receive a shared type.
When designing plugins, place shared API/SPI classes in a loader accessible to both the host and child loaders; load implementations/plugin dependencies separately when needed. In particular, inspect the types in parameters and return values: the JVM may enforce *loading constraints* during linking. Two classes with the same `package` string but different defining loaders also do not automatically belong to the same runtime package, so package-private access is not automatically shared.
When debugging, compare `Class<?> == Class<?>` and `getClassLoader()` on both sides; having the same class name or JAR path is not enough to prove type identity.

## 8. APIs Commonly Mistaken for the Defining Loader

| API / Property | What It Actually Indicates |
| --- | --- |
| `requestedLoader.loadClass(name)` | Sends a request to this loader, which may delegate; the result is a `Class<?>` |
| `Class.forName(name, false, requestedLoader)` | Requests finding the class using the specified loader without actively initializing it; the defining loader may differ |
| `clazz.getClassLoader()` | **Defining loader** of the runtime `clazz`; `null` for bootstrap |
| `clazz.getModule()` | Runtime module of the class; the module does not replace the defining loader question |
| `ClassLoader.getSystemClassLoader()` | System/application loader according to the environment; not “the loader of every class” |
| `Thread.currentThread().getContextClassLoader()` | Context loader carried by the thread; useful for SPI/resource discovery, but does not itself tell who defined the current class |
| `ClassLoader.getParent()` | Parent configured for delegation according to the API; not proof that the parent defined a specific class |
| `clazz.getProtectionDomain().getCodeSource()` | Code source information when available, which may be `null`; not the loader identity |

In particular, changing the **thread context class loader (TCCL)** does not change the defining loader of any previously defined class. The TCCL only affects APIs or libraries that **actively choose** the context loader when looking up classes, resources, or service providers.

Brief illustrative example:

```java
ClassLoader previous = Thread.currentThread().getContextClassLoader();
try {
    Thread.currentThread().setContextClassLoader(pluginLoader);
    // Discovery APIs can choose the TCCL to look up providers in the plugin.
} finally {
    Thread.currentThread().setContextClassLoader(previous);
}
```

The `pluginLoader` variable and the discovery APIs must be prepared by the application; this snippet only illustrates the TCCL restoration pattern, not a standalone program.

## 9. When the Lookup Policy Is Changed
A custom **child-first** loader can prioritize its own bytes for a plugin namespace, yet the result must still be checked via `result.getClassLoader()`: some names may delegate back to the parent, while others are defined by the child. Choose child-first only for namespaces that require isolation, preserving core JDK types and shared APIs. Overriding `loadClass` also requires managing caching, locking via `getClassLoadingLock`, resolution, and JVM constraints.

## 10. Practical Diagnostics When the Requested Loader Differs from the Defining Loader

When encountering `ClassCastException`, `NoSuchMethodError`, `ServiceConfigurationError`, or unexpected behavior in a plugin/container, you can follow this sequence:

1. **Record the exact binary name** being requested, the loader object invoked by the code, and the code path causing the error.
2. **Obtain the returned Class object** if loading succeeds. Print `clazz.getName()` and `clazz.getClassLoader()`; when comparing against an expected type, print the loaders of **both sides**.
3. **Inspect the parent relationship and delegation policy.** A `ChildLoader` may be receiving the parent's API/library version; the parent loader cannot automatically read all of the child's private classes.
4. **Check the JAR/module actually containing the bytecode** at runtime. When non-`null`, `CodeSource` can help verify this; a class may also come from a runtime module that is not represented as a JAR URL.
5. **Log class selection in the custom loader**, paying attention to when `loadClass` receives a request, when it delegates to the parent, when `findClass` is called, and when `defineClass` succeeds.
6. **Read the full cause of the error.** `ClassNotFoundException` is typically tied to APIs that look up classes by name; `NoClassDefFoundError` can result from missing dependencies during linking/initialization or a class that failed initialization; `LinkageError` may indicate a conflict in loader relationships.
7. **If the issue occurs during plugin reload**, compare the old and new defining loaders along with references still retaining classes/instances from the old loader.
8. **If ServiceLoader cannot find a provider**, distinguish between the loader searching for the provider, the loader defining the SPI, and the loader defining the provider. The provider must implement **the exact** SPI interface the host uses, not a same-named version defined by the plugin itself.

A helper method template that can be placed in an application class:

```java
static void describe(Class<?> type) {
    ClassLoader defining = type.getClassLoader();
    System.out.println("name=" + type.getName());
    System.out.println("definingLoader=" + defining);
    System.out.println("module=" + type.getModule().getName());

    java.security.ProtectionDomain pd = type.getProtectionDomain();
    java.security.CodeSource src = pd == null ? null : pd.getCodeSource();
    System.out.println("codeSource="
            + (src == null ? "<unknown>" : src.getLocation()));
}
```

This is a **helper method**, not a program with `main`. `getModule().getName()` can return `null` for an unnamed module; `CodeSource` may also be absent. The string representation of a class loader in logs is useful, but it is not guaranteed to be a unique, stable identifier across runs.

It can be combined with JVM tools when the environment permits:

```bash
java -Xlog:class+load=info RequestedVsDefiningLoaderDemo
```

Depending on the JVM and log level, the bytecode source may appear in the log; **do not equate “source: file X” with the defining loader**. For processes that support attach, `jcmd <pid> VM.classloaders` helps inspect the class loader structure; parameters and support depend on the JVM version.

## 11. Common Misconceptions

**“Calling `child.loadClass` means `child` defines the class.”** False when the class is found and returned by the parent.

**“`getClassLoader()` returns the nearest loader in the call stack.”** False: it returns the defining loader of the runtime class.

**“Every class has a ClassLoader object.”** False: `String.class.getClassLoader() == null` because the bootstrap loader is not represented as a Java object like regular loaders.

**“Two loaders requesting the same name will receive two copies.”** False if both delegate to the same definition in the parent.

**“Two loaders reading the same `.class` from disk must be the same type.”** False if each loader defines the bytecode itself; runtime type identity also considers the defining loader.

**“TCCL equaling the plugin loader means the SPI is defined by the plugin loader.”** False: the TCCL may be used to find the provider; the SPI usually needs to be defined by a shared loader.

**“Looking at `getParent()` is enough to deduce where every class is defined.”** False: delegation can be customized; you must verify the actual result.

**“Changing the loader later can change the defining loader of an existing Class.”** False: an existing `Class<?>` already has a defining loader bound to its runtime definition. To obtain a new definition, a new definition must be created through an appropriate loader.

## 12. Self-Check Exercises

**Question 1.** `PluginLoader` calls `loadClass("api.Plugin")`; the parent has already defined `api.Plugin` and returns it. Which is the requested loader, and which is the defining loader?

**Answer:** The requested loader is `PluginLoader`; the defining loader is the parent. `clazz.getClassLoader()` reports the parent.

**Question 2.** Two plugin loaders both delegate `api.Plugin` to the parent. Do the two results have the same type identity?

**Answer:** Yes, if the parent returns the same runtime `Class` definition. In that case, the two plugins can share the SPI.

**Question 3.** Two loaders each define `internal.Node` themselves from the same `.class` file. Can an instance of version A be cast to version B?

**Answer:** No. The runtime type identity differs because the defining loaders are different, even though the binary name and bytecode are the same.

**Question 4.** Does `Thread.currentThread().setContextClassLoader(pluginLoader)` cause a class already defined by the app loader to switch to the plugin loader?

**Answer:** No. The TCCL affects loader selection in certain APIs from that point forward; it does not change the defining loader of an already-defined class.

**Question 5.** When calling `child.loadClass("java.lang.String")`, `getClassLoader()` returns `null`. Does that mean loadClass failed?

**Answer:** No. `null` indicates that the bootstrap loader defined `String`.

**Question 6.** The app reports using a different library version than expected even though the plugin created its own `URLClassLoader`. What should you check first?

**Answer:** Print the defining loader and the bytecode location of the library class that was actually loaded; check whether parent-first selected the parent loader's version first.

## 13. Conclusion

To properly understand a class-loading call, always separate two questions: **“Which loader was requested to handle the class name?”** and **“Which loader actually defined the returned class?”**. Parent delegation allows these two answers to differ normally. Runtime type identity, type casting across plugins, and dependency isolation are determined by the **defining loader**, not simply by the object on which the application called `loadClass`.

### Authoritative References

- Java SE 17 `ClassLoader` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 `Class` API (`getClassLoader`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getClassLoader()
- Java Virtual Machine Specification 17, §5.3 *Creation of Classes and Interfaces*: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- Java Virtual Machine Specification 17, §5.3.4 *Loading Constraints*: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3.4
