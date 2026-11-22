# Tracing the Parent Chain and the Actual Defining ClassLoader in Java

## 1. The Diagnostic Problem: Calling Loader A, Yet the Class Is Defined by Loader B

In a Java system with plugins, multiple JARs, containers, or frameworks, logs often only record:

```java
Class<?> type = pluginLoader.loadClass("com.example.Service");
```

Readers easily infer: "Because `pluginLoader.loadClass` was called, the plugin loader itself defined `Service`." **This conclusion is unfounded.** With the standard parent-first mechanism, the loader receiving the request may delegate to its parent, the parent continues asking its own parent, and the returned class may be a definition from a **completely different** loader.

In class loading diagnostics, three questions must be separated:

1. **Who receives the request?** The loader invoked by code, for example `pluginLoader`.
2. **Which loaders does the delegation path pass through?** The parent chain or forwarding edges created by a custom framework.
3. **Who actually defines the runtime class?** The defining ClassLoader, looked up via `returnedClass.getClassLoader()`.

This article presents how to trace the parent chain, verify the defining loader using the class object, distinguish it from the initiating loader and TCCL, retrieve the bytecode source, read JVM logs, and handle duplicate class name cases. A complete Java 17 program will create multiple loaders to **prove this with runnable results**, rather than relying solely on diagrams.

## 2. Three Concepts That Must Not Be Equated

### 2.1. Requesting Loader — The Object Receiving the Call

Suppose:

```java
ClassLoader requested = pluginLoader;
Class<?> type = requested.loadClass("com.example.Report");
```

This is a snippet; `pluginLoader` and the corresponding class are required.

The **requesting loader** here is simply `requested` — the object that the program calls. It may define the class itself, or it may rely on another loader.

### 2.2. Initiating Loader — JVM-Level Terminology

The JVMS distinguishes between the loader that **initiates loading** (*initiating loader*) and the loader that **defines the class** (*defining loader*). When a child loader delegates and receives a class defined by its parent, the JVM may record the child loader as an initiating loader of that class. This is important for loading/linking constraints and class reuse.

**Do not treat "initiating" and "defining" as the same concept.** A class has one defining loader under the runtime identity model; it can be requested/loaded by multiple different loaders via delegation. The protected method `findLoadedClass(name)` checks whether the class has already been recorded by the JVM for the associated loader, which does not mean the result was necessarily defined by that loader itself.

### 2.3. Defining Loader — Who Owns the Runtime Definition?

From a returned `Class<?>`:

```java
Class<?> type = requested.loadClass("com.example.Report");
ClassLoader defining = type.getClassLoader();
```

The value `defining` is the **defining ClassLoader** of that runtime class. It may:

- Equal `requested` if this loader defined it itself.
- Equal a parent/ancestor if parent-first delegation found the class.
- Equal another loader if the framework applies custom routing.
- Equal `null` for classes defined by the bootstrap loader, for example `java.lang.String` in standard Java.

**Verification rule:** to know which loader a class actually belongs to, inspect the **actual Class object that was returned or is being used**, rather than inferring from the loader that the code initially called.

## 3. How Is the Parent Chain Represented?

In standard Java 17:

```text
       Bootstrap (Class.getClassLoader() represented as null)
           ^
           |
       Platform ClassLoader
           ^
           |
       Application/System ClassLoader
           ^
           |
       Plugin ClassLoader (if parent is application)
```

The arrows point **from child to parent**, not in the direction of "class ownership". A plugin loader can be created with a different parent, for example:

```java
ClassLoader parent = ClassLoader.getPlatformClassLoader();

try (java.net.URLClassLoader plugin =
        new java.net.URLClassLoader(pluginUrls, parent)) {
    // Only code/plugins that need platform classes, by design.
}
```

This is an illustrative snippet; `pluginUrls` is required. In this case, the direct parent is **platform**, not the application loader. Therefore, **you cannot assume a loader's parent tree just by looking at the name "plugin loader"**.

Related APIs:

```java
ClassLoader system = ClassLoader.getSystemClassLoader();
ClassLoader platform = ClassLoader.getPlatformClassLoader();
ClassLoader parent = system.getParent();
```

This is a snippet. In a standard environment, the system/application loader typically has platform as its parent; however, the class loader hierarchy can be customized by a launcher, runtime, or framework.

**Bootstrap is not always a publicly exposed Java ClassLoader object.** When calling `ClassLoader.getParent()` returns `null`, the next parent is no longer an observable Java object. When calling `String.class.getClassLoader()` returns `null`, that is the API representation for the bootstrap loader.

### The Parent Chain Is a Parent–Child Relationship, Not the Entire Class Lookup Graph

A custom loader may override `loadClass` to route certain namespaces to a **peer loader**, the thread context loader, or a service registry. For example:

```text
Plugin A  --parent--> Application
    |
    +-- custom route for api.impl.* --> Plugin B
```

Here, `A.getParent()` only describes the direct parent. It **does not automatically reveal** the custom route A→B. Therefore, full tracing sometimes requires combining `getParent()` with logs from `loadClass` overrides and the framework's routers.

In JPMS (Java 9+), module resolution, module layers, and class loader mapping also affect where classes are searched; one should not infer the entire behavior from a simple parent tree.

## 4. Parent-First Delegation: Reading the Steps Accurately

The default `ClassLoader.loadClass(String, boolean)` algorithm overall:

```text
child.loadClass("pkg.Type")
    |
    +-- findLoadedClass("pkg.Type")
    |       \-- Already loaded? return recorded Class
    |
    +-- parent.loadClass("pkg.Type")
    |       \-- Found by parent? return parent/ancestor's Class
    |
    +-- child.findClass("pkg.Type")
            \-- Child finds bytecode then defineClass -> return Class
```

Beyond the diagram, there are also class loading locks, resolution/linking, and API-specified exceptions. The diagram only illustrates the **default** precedence.

Consequences:

- If the parent **has** `pkg.Type`, the child typically does not look for the bytecode with the same name in its own JAR.
- If the parent **does not have** it, the child may call `findClass` to define it itself.
- A child may have **recorded the loading** of a class defined by its parent; repeated requests for the same name return that same class object.
- Changing the URL order in the child **does not resolve** a conflict when parent-first has already returned the class from the parent.
- If `loadClass` is overridden to be child-first, the precedence rules differ; you must observe the actual implementation rather than assuming all loaders are parent-first.

A code fragment that easily causes confusion:

```java
ClassLoader child = ...;
Class<?> result = child.loadClass("pkg.Type");
System.out.println(result.getClassLoader() == child);
```

This is a snippet; the result may be `true` **or** `false`, depending on where the class is actually defined. If `false`, that is not necessarily a bug — it may be delegation working as designed.

## 5. Runtime Identity: The Same Binary Name Can Be Two Different Types

According to the JVMS, a runtime class/interface has an identity based on **(binary name, defining loader)**.

```text
("pkg.Type", ParentLoader) != ("pkg.Type", SiblingLoader)
```

Even if two loaders use the **exact same bytecode**, having both define `pkg.Type` creates two separate runtime types.

| Observation | Class P defined by parent | Class S defined by sibling |
| --- | --- | --- |
| `getName()` | `pkg.Type` | `pkg.Type` |
| `getClassLoader()` | parent | sibling |
| `P == S` | `false` if two independent definitions | `false` |
| `P.isInstance(instanceOfS)` | Not true merely because the names match | Not automatically compatible |
| Static fields | Bound to class P | Bound to class S |
| Package-private | Checked against P's runtime package | Against S's runtime package |

The **runtime package** also depends on the package name and the **defining loader**. Two classes declaring the same `package pkg;` but defined by two different loaders do not automatically share each other's package-private access.

When seeing a `ClassCastException` such as "X cannot be cast to X", you must print the defining loader of **both actual Class objects**, rather than only comparing string names.

## 6. Diagnostic APIs and Their Limitations

| API | What does it tell you? | What should you not infer? |
| --- | --- | --- |
| `type.getClassLoader()` | The defining loader of the actual class | Does not return a list of every loader that ever requested it |
| `loader.getParent()` | The direct parent of the loader (or null) | Does not list custom peer routing |
| `ClassLoader.getSystemClassLoader()` | The system class loader | Does not guarantee it is the loader defining every application class |
| `ClassLoader.getPlatformClassLoader()` | The JDK's platform loader | Does not prove a custom loader's parent is platform |
| `Thread.currentThread().getContextClassLoader()` | The TCCL currently bound to the thread | Not by default the defining loader of the calling class |
| `Class.forName(name, false, loader)` | Requests lookup/loading via the **specified** loader without eagerly initializing | The returned class may have been defined by a parent/ancestor |
| `type.getProtectionDomain().getCodeSource()` | Code source metadata when available | Does not always have a URL, nor does it confirm every class came from a file/JAR |
| `type.getModule()` | The runtime module of the class | Does not replace the defining loader or reveal the full resolution graph |
| `URLClassLoader.getURLs()` | The URLs registered as search sources for the URLClassLoader | Does not prove which URL actually defined the class; the parent may have won |
| `loader.getResource(name)` | The first resource URL according to the lookup policy | Not decisive proof that the actual class used that URL |
| `loader.getResources(name)` | May see multiple resource copies with the same name | Does not prove the JVM defined multiple classes with the same name in one loader |
| `findLoadedClass(name)` (protected) | The class the JVM recorded as loaded for the corresponding initiating loader | Has no public API callable from application code outside a subclass |

For bootstrap classes, `getClassLoader() == null` is normal; for primitives such as `int.class`, the API also returns `null`, but a primitive should not be treated as a class file read by the bootstrap loader like `java.lang.String`.

A `Class<?>` can represent an array class. The loader associated with array types follows the JVM rules for the component type; do not conclude that every array class comes from a `[].class` class file in a JAR.

## 7. Java 17 Practice: Creating Parent, Child, and Sibling Loaders to Verify the Actual Definition

This program uses the JDK's `JavaCompiler` to **generate two versions of the same binary name** `diag.Sample` and then loads them using three `URLClassLoader` instances:

```text
Platform loader
    |
    +--> Parent URLClassLoader
    |        root: parent-classes/
    |        diag.Sample.origin() -> "PARENT"
    |          |
    |          +--> Child URLClassLoader
    |                root: child-classes/
    |                diag.Sample.origin() -> "CHILD"
    |                diag.ChildOnly.origin() -> "CHILD_ONLY"
    |
    +--> Sibling URLClassLoader
             root: child-classes/
             diag.Sample.origin() -> "CHILD"
```

Even though `Child URLClassLoader` has its own `diag.Sample`, the call `child.loadClass("diag.Sample")` is satisfied by **Parent** through parent-first delegation. Meanwhile, `diag.ChildOnly` does not exist in the parent, so **Child defines it itself**. Sibling has platform as its parent, so it defines the Sample version in child-classes itself.

### 7.1. Complete Program

Save the entire code into the file `LoaderTraceDemo.java`:

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.CodeSource;
import java.util.Comparator;
import java.util.Enumeration;
import java.util.StringJoiner;
import java.util.stream.Stream;
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public final class LoaderTraceDemo {
    private static void compile(JavaCompiler compiler, Path output,
                                Path... sources) throws Exception {
        String[] args = new String[4 + sources.length];
        args[0] = "--release";
        args[1] = "17";
        args[2] = "-d";
        args[3] = output.toString();
        for (int i = 0; i < sources.length; i++) {
            args[4 + i] = sources[i].toString();
        }
        if (compiler.run(null, null, null, args) != 0) {
            throw new IllegalStateException("Compilation failed");
        }
    }

    private static boolean definedFrom(Class<?> type, Path expected)
            throws Exception {
        CodeSource source = type.getProtectionDomain().getCodeSource();
        return source != null && source.getLocation() != null
                && Path.of(source.getLocation().toURI()).toRealPath()
                       .equals(expected.toRealPath());
    }

    private static String origin(Class<?> type) throws Exception {
        return (String) type.getMethod("origin").invoke(null);
    }

    private static String chain(ClassLoader start, ClassLoader parent,
                                ClassLoader platform) {
        StringJoiner path = new StringJoiner(" -> ");
        for (ClassLoader at = start; at != null; at = at.getParent()) {
            path.add(at == start ? "child"
                    : at == parent ? "parent"
                    : at == platform ? "platform" : "other");
        }
        path.add("bootstrap");
        return path.toString();
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Use a full JDK 17+");
        }
        Path root = Files.createTempDirectory("loader-trace-");
        try {
            Path parentSrc = root.resolve("psrc/diag/Sample.java");
            Path childSrc = root.resolve("csrc/diag/Sample.java");
            Path onlySrc = root.resolve("csrc/diag/ChildOnly.java");
            Path parentOut = root.resolve("parent-classes");
            Path childOut = root.resolve("child-classes");
            Files.createDirectories(parentSrc.getParent());
            Files.createDirectories(childSrc.getParent());
            Files.createDirectories(parentOut);
            Files.createDirectories(childOut);
            Files.writeString(parentSrc,
                    "package diag; public class Sample {"
                    + " public static String origin() { return \"PARENT\"; } }");
            Files.writeString(childSrc,
                    "package diag; public class Sample {"
                    + " public static String origin() { return \"CHILD\"; } }");
            Files.writeString(onlySrc,
                    "package diag; public class ChildOnly {"
                    + " public static String origin() { return \"CHILD_ONLY\"; } }");
            compile(compiler, parentOut, parentSrc);
            compile(compiler, childOut, childSrc, onlySrc);

            ClassLoader platform = ClassLoader.getPlatformClassLoader();
            try (URLClassLoader parent = new URLClassLoader(
                         new URL[]{parentOut.toUri().toURL()}, platform);
                 URLClassLoader child = new URLClassLoader(
                         new URL[]{childOut.toUri().toURL()}, parent);
                 URLClassLoader sibling = new URLClassLoader(
                         new URL[]{childOut.toUri().toURL()}, platform)) {

                Class<?> fromChildRequest = child.loadClass("diag.Sample");
                Class<?> childOnly = child.loadClass("diag.ChildOnly");
                Class<?> childVersion = sibling.loadClass("diag.Sample");
                Class<?> fromForName = Class.forName("diag.Sample", false, child);

                System.out.println("chain=" + chain(child, parent, platform));
                System.out.println("requestIsDefining="
                        + (fromChildRequest.getClassLoader() == child));
                System.out.println("parentFirstOrigin=" + origin(fromChildRequest));
                System.out.println("parentFirstLoaderIsParent="
                        + (fromChildRequest.getClassLoader() == parent));
                System.out.println("parentCodeSource="
                        + definedFrom(fromChildRequest, parentOut));
                System.out.println("childOnlyOrigin=" + origin(childOnly));
                System.out.println("childOnlyLoaderIsChild="
                        + (childOnly.getClassLoader() == child));
                System.out.println("childCodeSource="
                        + definedFrom(childOnly, childOut));
                System.out.println("repeatedSameClass="
                        + (child.loadClass("diag.Sample") == fromChildRequest));
                System.out.println("forNameSameClass="
                        + (fromForName == fromChildRequest));
                System.out.println("siblingOrigin=" + origin(childVersion));
                System.out.println("sameBinaryName="
                        + childVersion.getName().equals(fromChildRequest.getName()));
                System.out.println("sameRuntimeClass="
                        + (childVersion == fromChildRequest));
                System.out.println("siblingLoaderIsSibling="
                        + (childVersion.getClassLoader() == sibling));
                Enumeration<URL> resources = child.getResources("diag/Sample.class");
                int matches = 0;
                while (resources.hasMoreElements()) {
                    resources.nextElement();
                    matches++;
                }
                System.out.println("classFileResources=" + matches);
                System.out.println("stringBootstrap="
                        + (child.loadClass("java.lang.String")
                                .getClassLoader() == null));
            }
        } finally {
            try (Stream<Path> paths = Files.walk(root)) {
                for (Path p : paths.sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(p);
                }
            }
        }
    }
}
```

### 7.2. Compiling and Running

From the directory containing the source file, using JDK 17 or later:

```bash
javac --release 17 LoaderTraceDemo.java
java LoaderTraceDemo
```

The program creates two temporary source directories and two temporary class directories, compiles the classes at runtime using `javax.tools.JavaCompiler`, and then cleans them up after all three URLClassLoader instances have been closed. **Do not add** the temporary directories to the application classpath; doing so could prevent the configured loaders from accurately demonstrating the assumption "the platform parent does not contain diag.Sample".

### 7.3. Verified Stdout

Compiled the program with JDK 21 and `--release 17`, and ran it successfully in a standard JDK environment. Output:

```text
chain=child -> parent -> platform -> bootstrap
requestIsDefining=false
parentFirstOrigin=PARENT
parentFirstLoaderIsParent=true
parentCodeSource=true
childOnlyOrigin=CHILD_ONLY
childOnlyLoaderIsChild=true
childCodeSource=true
repeatedSameClass=true
forNameSameClass=true
siblingOrigin=CHILD
sameBinaryName=true
sameRuntimeClass=false
siblingLoaderIsSibling=true
classFileResources=2
stringBootstrap=true
```

### 7.4. Why Does Each Result Matter?

**`chain=child -> parent -> platform -> bootstrap`**: following `getParent()` shows the parent chain of the tested loader. The final label "bootstrap" represents the `null` parent at the end of the chain; it is not a Java ClassLoader object whose name is being printed.

**`requestIsDefining=false`**: the request was sent to child, yet `fromChildRequest.getClassLoader()` **is not child**. This is direct evidence that "the loader receiving the request" differs from "the defining loader".

**`parentFirstOrigin=PARENT`** and **`parentFirstLoaderIsParent=true`**: parent-first used the parent's class even though child has a `diag.Sample.class` containing different logic.

**`parentCodeSource=true`**: the `ProtectionDomain.getCodeSource().getLocation()` of this class points to the `parent-classes` directory created by the program. This is a valuable supplementary signal, though on other JVMs/runtimes it may have `CodeSource == null` or a URL that is not a regular file.

**`childOnlyOrigin=CHILD_ONLY`**, **`childOnlyLoaderIsChild=true`**, **`childCodeSource=true`**: the parent does not have `diag.ChildOnly`, so child locates the bytecode at its local URL and defines the class itself. This case is completely different from `diag.Sample`.

**`repeatedSameClass=true`**: calling `child.loadClass("diag.Sample")` again retrieves the already recorded class instead of defining a new runtime type for the same name.

**`forNameSameClass=true`**: `Class.forName("diag.Sample", false, child)` uses the **specified loader** to find the class, yet the returned class is still the same definition from the parent. The `false` argument requests not eagerly initializing the class during this call.

**`siblingOrigin=CHILD`**, **`sameBinaryName=true`**, **`sameRuntimeClass=false`**, **`siblingLoaderIsSibling=true`**: sibling has platform as its parent, so it does not see the Sample version in the parent URLClassLoader and defines the version in `child-classes` itself. The two classes have the same name but **different defining loaders**, and are therefore two runtime types.

**`classFileResources=2`**: querying child for the `diag/Sample.class` resource can list both the parent's copy and the copy at the local URL. **Two resource URLs do not prove that the JVM defined two runtime classes with the same name in child**; the JVM actually selects one definition for `diag.Sample` along the child request path.

**`stringBootstrap=true`**: the JDK class `java.lang.String` is defined by bootstrap; when requested through child, the core class is also returned, demonstrating delegation.

## 8. Adding Helpers to Inspect the Parent Chain in a Real Project

Depending on the framework, a ClassLoader may have a very long `toString()`, or multiple loaders may share the same display name. It is good practice to assign a short ID based on **object identity**, record the requested loader clearly, and then print the defining loader after loading.

Minimal helper:

```java
static void printParentChain(ClassLoader starting) {
    int depth = 0;
    for (ClassLoader loader = starting;
         loader != null;
         loader = loader.getParent()) {
        System.out.println("depth=" + depth++
                + ", type=" + loader.getClass().getName()
                + ", identity=" + System.identityHashCode(loader));
    }
    System.out.println("depth=" + depth + ", loader=<bootstrap/null>");
}
```

This is an **illustrative helper**, not a standalone program. If a custom loader violates expectations and creates an unusual parent chain, you should include a depth limit and a visited set when writing diagnostic tools for a framework. Parent relationships established via standard constructors do not easily form cycles, but custom delegation routes outside the parent chain **can** have cycles of their own.

**Do not treat `System.identityHashCode(loader)` as an absolute global ID**: it can collide across different objects and is not stable across JVM runs. For a production logger, assign an ID from a registry using an object-identity map per session/plugin and avoid holding a strong reference to the loader after unloading.

### Printing Class/Module and CodeSource Information

A helper for diagnosing a loaded class:

```java
static void describe(Class<?> type) {
    ClassLoader loader = type.getClassLoader();
    java.security.ProtectionDomain pd = type.getProtectionDomain();
    java.security.CodeSource codeSource =
            pd == null ? null : pd.getCodeSource();

    System.out.println("name=" + type.getName());
    System.out.println("definingLoader=" + loader);
    System.out.println("module=" + type.getModule());
    System.out.println("package=" + type.getPackageName());
    System.out.println("source=" + (codeSource == null
            || codeSource.getLocation() == null
            ? "<unknown>" : codeSource.getLocation()));
}
```

This is a standalone method-level helper (place it inside a class and invoke it with an actual `Class<?>`). If the environment restricts access to certain metadata, handle exceptions appropriately; do not assume a missing CodeSource means a class "has no defining loader".

**Security logging warning:** `CodeSource` paths, repository URLs, or a loader's `toString()` string may contain internal paths or sensitive information. Only print them in authorized diagnostic environments and avoid exposing secrets/tokens in production logs.

## 9. How Does the Thread Context ClassLoader (TCCL) Differ from the Defining Loader?

Some frameworks load providers from a plugin JAR via:

```java
ClassLoader context =
        Thread.currentThread().getContextClassLoader();
```

TCCL is a **class-loading context attached to a thread**, used by certain APIs/frameworks to choose where to discover classes/services. It **does not change** the ClassLoader that defined an existing class.

Example of an application running host code defined by the application loader while temporarily using a plugin's TCCL:

```java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();
try {
    thread.setContextClassLoader(pluginLoader);
    // Invoke the framework/API that selects the context class loader.
} finally {
    thread.setContextClassLoader(previous);
}
```

This is a snippet; the `pluginLoader` variable is required. After changing the TCCL:

- `Host.class.getClassLoader()` **does not change**.
- The single-parameter `Class.forName("some.Type")` overload still follows the caller's loader rule, rather than automatically using the TCCL.
- `Class.forName("some.Type", false, pluginLoader)` uses the specified loader, though the class may still be defined by a parent.
- `ServiceLoader.load(Service.class)` has rules for using the context loader depending on the overload/API and caller module access; to diagnose it, you must record which overload was used.
- Thread pools may retain a plugin's TCCL after the plugin stops; remember to restore it in `finally` to prevent a classloader leak.

**Principle:** logging should separate `requestedLoader`, `TCCL`, and `actualClass.getClassLoader()` into **three distinct fields**, rather than labeling them all under a single "loader" label.

## 10. CodeSource: Which File/JAR Provided the Class?

When suspecting "two JAR versions both contain this class", after obtaining the actual `Class<?>`:

```java
java.security.CodeSource source =
        clazz.getProtectionDomain().getCodeSource();
System.out.println(source == null ? "<unknown>"
        : source.getLocation());
```

This is a snippet; the `clazz` variable is required. For classes loaded by `URLClassLoader` from a regular JAR/directory, `CodeSource.getLocation()` typically provides the source URL that defined the class. This is more useful than merely printing every JAR present in `loader.getURLs()`.

However:

- A custom loader calling `defineClass` from memory/a database may not provide a specific CodeSource URL.
- Classes from the `jrt:` runtime image/bootstrap may have metadata different from a regular file/JAR, or even `null`.
- `CodeSource` may indicate the declared origin, without guaranteeing that a file still exists on disk at debug time.
- JARs with a `Class-Path` manifest attribute and build tools can introduce indirect dependency sources; the constructor URL list is not always the entirety of the actual search scope.
- A classpath URL may use `jar:` or another protocol; do not assume `new File(url.toURI())` is always valid.
- For named modules, `type.getModule()` provides additional context; `CodeSource` does not replace module information.

**The strongest approach is to combine:** class name → defining loader → module → CodeSource (if present) → launcher/module/classpath configuration → actual source artifact.

## 11. Finding Multiple .class Resources Does Not Mean Multiple Classes Were Defined

When running:

```java
Enumeration<java.net.URL> urls =
        loader.getResources("diag/Sample.class");
while (urls.hasMoreElements()) {
    System.out.println(urls.nextElement());
}
```

this is a snippet; importing `Enumeration` and the `loader` variable are required. It can print URLs from both parent and child, even when `loader.loadClass("diag.Sample")` only receives the parent's definition.

The difference:

- **Resource search**: retrieves URLs of files with a matching name; `getResources` can return multiple locations.
- **Class loading**: the JVM defines/reuses a single runtime class for a binary name within the appropriate defining loader.
- **Parent-first**: the first source found may come from the parent, ignoring bytecode for the same class name in the child.
- **Custom resource lookup**: may use a different order from custom class delegation; do not use `getResource` as a substitute for evidence from class `getClassLoader()`.

When you need to determine which loader defined a class, **`Class.getClassLoader()` is the core fact**. Resource enumeration is useful for inspecting **conflicting candidate files**, not for determining the running class.

## 12. Cases Where a Simple Parent Chain Is Not Enough

### 12.1. Child-First or Hybrid Delegation

A plugin loader may prioritize local classes for `plugin.internal.*` while keeping parent-first for `java.*` and `host.api.*`. In that case, you must record the policy per namespace, because the `getParent()` relationship remains the same while the lookup order may differ.

Ask:

1. Does the loader override `loadClass(String)` or `loadClass(String, boolean)`?
2. For this binary name, is the policy parent-first or child-first?
3. Is there a forwarding branch to a peer loader?
4. Was the class already recorded via `findLoadedClass` from a previous call?
5. Did another loader define a duplicate of the same binary name?

### 12.2. JPMS Module Layers

On the module path, module resolution determines which modules participate in the graph, while loader mapping determines which loader defines each class. Two classes in the same module layer do not necessarily use the same loader, and the module name is not a substitute for the defining loader.

You should log both:

```java
Class<?> type = ...;
System.out.println(type.getModule());
System.out.println(type.getClassLoader());
```

This is a snippet. When custom module layers are present, you must cross-check the layer, module graph, service bindings, and actual package ownership.

### 12.3. Frameworks with Their Own Loader Trees

Application servers, OSGi-like frameworks, test runners, IDEs, plugin hosts, and build tools may:

- Create multiple peer classloaders;
- Delegate according to package/import rules;
- Use a shared loader for the API and separate loaders for implementations;
- Apply URL/classpath transformations or instrumentation;
- Pass bytes from the network, a database, a cache, or memory into `defineClass`.

Therefore, the parent chain is a **starting point**. When a class is defined by an unexpected loader, you must examine the framework's routing and creation logic rather than assuming a plain JDK URLClassLoader.

### 12.4. Class Loader Lifetime and Hot Reload

A plugin may be reloaded with a new loader while the host still retains a `Class<?>` or instance from the old loader in a cache. Code with the same name continues running with the old definition. `URLClassLoader.close()` does **not** automatically remove old classes or force unloading; the old classloader only becomes eligible for GC when the corresponding strong-reference paths disappear.

When diagnosing "deployed a new JAR, yet the JVM is still running the old class", you need to identify the actual class object, defining loader ID, CodeSource, and the reference holding onto the old version; do not only inspect the current JAR file contents on disk.

## 13. Supplementing with JVM Logs and Tools When the Parent Chain Is Insufficient

If you need to prove which class the JVM loaded and from which source, use `-Xlog:class+load=info` on HotSpot and correlate it with the **same runtime `Class<?>`**: `getName()`, `getClassLoader()`, `getModule()`, and `CodeSource` when available. Load logs at info level do not record every `loadClass`/delegation branch; to observe custom routing, you must insert logging directly into the loaders you own.

Use `jcmd PID VM.classloaders` to observe the parent tree of the **target JVM** (check supported commands with `jcmd PID help`). When suspecting JARs contain duplicate binary names or conflicting ABIs, run `jar --list` and `javap -s -p` on each artifact; these provide static data and do not confirm which copy was selected at runtime. This chapter has a separate article explaining `-Xlog`, three `jcmd` commands, and `jar/javap/jdeps`; keep the parent-chain trace in Section 7 as the primary empirical evidence for this article.
## 14. Practical Diagnostic Workflow in Priority Order

When observing a class loaded from the "wrong JAR/wrong loader":

1. **Obtain the exact `Class<?>`** that the application code is using. If you have an object, prefer `object.getClass()`; if you have an API method, check the class that actually declares it. Avoid arbitrarily calling `Class.forName` with a different loader and mistaking it for the offending class.
2. **Print the binary name and defining loader** using `type.getName()` and `type.getClassLoader()`. For bootstrap, explicitly record `<bootstrap/null>`.
3. **Record the requesting loader** and **TCCL** separately; use an object ID/registry ID to distinguish multiple instances with the same class name.
4. **Trace the parent chain** of the requesting loader; do not forget that the chain can end at bootstrap when parent returns null.
5. **Check the override policy** for the affected namespace: parent-first, child-first, peer delegation, or module provider resolution.
6. **Print the module and CodeSource** of the actual Class when metadata is available.
7. **List URL/resource candidates** using `getURLs`, `getResources("pkg/Type.class")`, or by inspecting the classpath/module path, but do not use them in place of the defining loader.
8. **Inspect JVM logs** with `-Xlog:class+load` to supplement timing and class origin; if needed, add logging inside custom `findClass`/`loadClass`.
9. **Compare duplicate binary names and ABIs** across JARs using `jar tf`/`javap`, especially when encountering `NoSuchMethodError` or `ClassCastException`.
10. **Inspect the loader lifecycle** if a plugin was just redeployed: a host cache may be holding onto a class or instance defined by the old loader.
11. **Inspect the module graph** if using JPMS, rather than looking only at the URL array of `URLClassLoader`.
12. **Re-evaluate the dependency policy:** remove duplicate JAR copies when possible; place the shared SPI in the parent and keep plugin implementations in their own loaders.

A well-structured event log:

```text
request=42 class=com.example.Service requestLoader=plugin-A
route=parent-first parent=host
result=success definingLoader=host module=<unnamed>
source=file:/deployment/host-api.jar
```

This is an **illustrative log**, not the stdout of the program in Section 7. Recording **requesting** and **defining** separately is the most important improvement.

## 15. Common Pitfalls

| Misconception | Correct Understanding |
| --- | --- |
| "I called `child.loadClass`, so the class was defined by child." | Parent-first may return a class from the parent. Check `result.getClassLoader()`. |
| "`child.getParent() == parent` means every class returned by child was defined by parent." | Child can define the class itself if parent does not have it. |
| "`Class.getClassLoader() == null` is an error." | For `String` in standard Java, that indicates bootstrap. |
| "The thread's TCCL is the defining loader for every class on that thread." | TCCL is only a context that certain APIs may choose to use. |
| "Two classes with equal `getName()` values are the same type." | They also require the same defining loader; they may be two runtime types. |
| "`getResources` finding two .class files means two runtime classes were defined by child." | Resource enumeration and class definition are different. |
| "`URLClassLoader.getURLs()` contains plugin.jar, so every plugin class must come from it." | The parent may provide the class first, and indirect sources can also be involved. |
| "A null CodeSource means the class has no source or no loader." | CodeSource may lack metadata; the defining loader is still determinable from the Class object. |
| "Changing the URL order in child will override the parent's version." | Not when parent-first still selects the parent. |
| "Closing URLClassLoader replaces the old class with the new version." | Closing does not redefine or unload; a new version typically requires a new loader. |
| "Two loaders pointing to the same directory create the same runtime class." | If each loader defines it independently, the class identities still differ. |
| "The parent chain describes every loading edge." | Custom peer delegation/module resolution can create other paths. |
| "No class-load log means loadClass was never called." | The call may have simply reused an already loaded class or failed before a definition event occurred. |
| "Just enable child-first for all packages to fix conflicts." | That can duplicate shared APIs/SPIs and break type identity. |

## 16. Self-Check Questions

**Question 1.** `child.loadClass("pkg.Type")` returns a Class object where `getClassLoader() == parent`. Who defined the class?

**Answer:** Parent. Child received the request and may be an initiating loader; the defining loader is parent.

**Question 2.** If the parent does not have `pkg.Helper` but the child has the bytecode in its own JAR, who can define it?

**Answer:** Child, if the parent-first policy reaches the child's `findClass` and the class file is valid.

**Question 3.** Why is `Thread.currentThread().getContextClassLoader()` not enough to tell who defined the class `pkg.Type`?

**Answer:** TCCL is a thread context for APIs that select a loader; a runtime class has already been defined by its own specific loader and does not change with TCCL.

**Question 4.** Two independent `URLClassLoader` instances have the same URL pointing to the `pkg.Type.class` file. Are the returned `Class<?>` objects guaranteed to be equal?

**Answer:** No, if each loader defines the class itself. Runtime class identity depends on (binary name, defining loader).

**Question 5.** `getResources("pkg/Type.class")` lists two URLs, yet `child.loadClass("pkg.Type")` returns the parent's class. Is this a contradiction?

**Answer:** No. Resource lookup can list multiple candidates; class loading selects/reuses one definition according to delegation.

**Question 6.** What is the most important tool for verifying the defining loader of an actual obtained class?

**Answer:** `type.getClassLoader()` on that `Class<?>` object itself. Supplement with CodeSource/module/logs when you want to know the source and context.

**Question 7.** Why can `Class.forName(name, false, child)` still return the parent's class?

**Answer:** The loader argument specifies where **the request starts**. The child's delegation algorithm can ask the parent, and the parent defines and returns the class.

**Question 8.** If the parent classloader is not the application loader but the platform loader, what should you do before diagnosing?

**Answer:** Print the actual `getParent()` chain; do not apply a rigid default hierarchy based on the plugin name.

**Question 9.** During a plugin hot reload, `CodeSource` still points to the old JAR and the old defining loader ID. What is one possibility?

**Answer:** The host may still be holding a Class<?>/instance of the old plugin version. Check caches, listeners, threads, and lifecycle.

**Question 10.** When `NoSuchMethodError` occurs with two library versions containing duplicate classes, is it enough to just print the list of present JARs?

**Answer:** No. You need to identify the exact runtime class that was selected, its defining loader, CodeSource, and method descriptor compared with the compile-time API.

## 17. Operational Checklist

- [ ] Obtain the exact `Class<?>`/instance causing the issue.
- [ ] Record the binary name, defining loader object identity, module, and CodeSource when available.
- [ ] Log the requesting loader in a separate field from the defining loader and TCCL.
- [ ] Print the parent chain starting from the loader receiving the request.
- [ ] Distinguish bootstrap (null) from an actual loader object.
- [ ] Inspect custom `loadClass`/`findClass`, child-first, and peer routes.
- [ ] Do not use `getResource`/`getResources` as a substitute for class identity evidence.
- [ ] List JAR candidates and check for duplicate binary names/method signatures.
- [ ] For URLClassLoader, check the URL order, while keeping in mind that parent-first can win.
- [ ] For JPMS, record the module/layer and resolution graph.
- [ ] For hot reload, inspect Class<?>/instances/caches belonging to the old loader.
- [ ] Use unified class-load log/jcmd according to JDK capabilities, protecting sensitive information.
- [ ] Ensure the host SPI/API has only a single shared runtime definition when plugins share types.
- [ ] Test both the branch where the parent owns the class and the branch where the child defines the class itself.

## 18. Conclusion and Official Sources

**The parent chain answers "whom can the loader ask?"; `Class.getClassLoader()` answers "who actually defined this class?".** These are two distinct questions, and both are important. When a class is requested through a child loader, parent-first delegation may cause it to be defined by the parent; only when the parent cannot find it does the child get the opportunity to define it locally. Two runtime classes with the same name but different defining loaders are two separate types, even if they share the same code source or bytecode.

For reliable diagnostics, start from the **actual Class object**, clearly record the requesting/defining loader, trace the parent chain, supplement with module/CodeSource, and inspect the actual routing code. System logs and resource enumeration are supporting evidence, not replacements for runtime class identity rules.

Official references:

- Java SE 17 `ClassLoader` API (`loadClass`, `findLoadedClass`, `getParent`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 `Class` API (`getClassLoader`, `forName`, `getModule`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- Java SE 17 `URLClassLoader` API (URL search paths, `getURLs`, `close`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- Java SE 17 `ProtectionDomain` / `CodeSource`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/ProtectionDomain.html
- JVMS 17 §5.3 — *Creation of Classes and Interfaces* (defining and initiating loaders): https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- JLS 17 §12.2 — *Loading of Classes and Interfaces*: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.2
- Java SE 17 launcher `java` (unified logging, classpath): https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Java SE 17 `jcmd` utility: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
