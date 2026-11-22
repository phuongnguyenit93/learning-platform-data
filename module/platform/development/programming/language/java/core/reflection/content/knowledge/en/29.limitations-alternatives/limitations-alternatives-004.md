# Java Reflection Has No API to Automatically List Every Class on the Classpath

An important limitation of **Java Core Reflection** is that **there is no standard method like `Class.getAllClassesInClasspath()` to obtain a list of every class an application can use**.

Reflection excels at answering questions about **a known type**: what its name is, what constructors, fields, methods, and annotations it has, and which instances can be created or methods invoked. However, the question "what are all the classes on the current classpath?" belongs to **discovering class sources, class-loading mechanisms, module structure, and the runtime environment**; Reflection does not perform that work on its own.

This lesson focuses on **the boundaries of Core Reflection**, easily confused concepts, how to discover classes within a defined scope, and choosing the right design when building a plugin scanner, test runner, annotation scanner, or framework.

## 1. "Listing All Classes" Can Actually Mean Several Different Things

Before choosing an API, define the goal:

| Practical question | Dataset you want to find | What can solve it? |
| --- | --- | --- |
| "What attributes does class `com.example.User` have?" | Metadata of **a known class** | `User.class`, `Class.forName`, `Class.getDeclaredFields` |
| "Which nested classes does class `Service` declare?" | Member classes/interfaces **declared inside a class** | `Service.class.getDeclaredClasses()` |
| "Which `.class` files exist in directory `build/classes`?" | **Physical entries** in a defined directory tree | `Files.walk` with `java.nio.file` |
| "Which `.class` entries does JAR `plugins.jar` contain?" | Entries belonging to **a specific JAR** | `JarFile`, `JarEntry` |
| "Which implementations are registered for an SPI?" | Providers under the service provider mechanism | `ServiceLoader` |
| "Which resources exist in module `m`?" | Resources of a **specified module** | `ModuleReader.list()` with appropriate permissions/environment |
| "Which classes has the JVM loaded?" | Classes **already loaded** at the time of observation | `Instrumentation.getAllLoadedClasses()` via a Java agent, outside Core Reflection |
| "Every class that could be loaded by all class loaders, including in the future?" | Potential set of classes that can change dynamically | **No general, complete way across all Java environments** |

The following two sets of data are distinct:

- **Classes *present* in a source**: for example, the file `com/acme/Plugin.class` inside a JAR. It is not guaranteed to be found by the current loader, nor guaranteed to link successfully or be accessible.
- **Classes *already loaded***: the JVM has created the corresponding runtime `Class<?>` through a class loader. A class packaged in a JAR that has never been used may **not yet** be loaded.

You must not infer that every loaded class has a `.class` file on `java.class.path`, or that every `.class` file on disk is a valid, invokable runtime class.

## 2. Core Reflection Knows the Structure of an Already Named Class

Familiar APIs:

```java
Class<?> type = String.class;

System.out.println(type.getName());
System.out.println(type.getDeclaredMethods().length > 0);
```

Once you have a `Class<?>`, you can inspect:

- `getDeclaredFields()`: directly declared fields, including non-public ones (finding them does not imply permission to access).
- `getDeclaredMethods()`: directly declared methods, without automatically adding all inherited methods.
- `getDeclaredConstructors()`: directly declared constructors.
- `getDeclaredAnnotations()`: directly present annotations observable by Reflection at runtime.
- `getDeclaredClasses()`: **member classes/interfaces declared directly inside this class**.

`getDeclaredClasses()` is frequently misunderstood. It **does not** traverse all classes in the same package, JAR, or classpath; it only describes member classes declared within the current class. Local classes or anonymous classes are not "all scanned" by this call either.

For example:

```java
class Container {
    static class Nested {}
}

class Independent {}
```

`Container.class.getDeclaredClasses()` can return `Container.Nested`; it does not automatically return `Independent` merely because the two classes are in the same source file, package, or compiled directory.

### Knowing a Name Differs from Discovering All Names

`Class.forName("com.acme.SomeType")` attempts to locate a class by **an already known name**. This API does not provide a class-name enumerator. The single-parameter variant can trigger class initialization.

```java
// Illustrates the case where the class name is known and a suitable class loader is available.
ClassLoader loader = Thread.currentThread().getContextClassLoader();
Class<?> type = Class.forName("com.acme.SomeType", false, loader);
```

`false` means do not request class initialization in this call. It **does not mean** no loading/linking occurs, no class-loading errors can be thrown, or that the found class is definitely accessible from the caller. If the class does not exist within the loader's scope: `ClassNotFoundException`. When there are linkage issues, `LinkageError` may occur.

**Exact class names** use binary name syntax; for example, a nested class can be named `com.acme.Outer$Inner`; a `$` in a binary name does not necessarily mean a simply declared member class.

## 3. Why Is the Classpath Not a Single Class Catalog?

### 3.1. The Classpath Has Multiple Sources and Does Not Carry a Built-in "Class List"

A Java application can obtain bytecode from:

- Directory trees containing compiled `.class` files.
- JARs passed via `-cp` / `--class-path`; classpath wildcards or manifest `Class-Path` entries can expand the sources used at runtime.
- Class loaders of application servers, frameworks, test runners, or plugin systems.
- Custom data sources: memory, network, encrypted files, dynamically generated classes, etc.
- **Module path** in JPMS applications, which has its own rules; it cannot simply be equated with the classpath.

`System.getProperty("java.class.path")` reflects a launcher/runtime classpath setting, but **does not fully represent every source of every class loader**. You should not simply split this string and conclude you have found every class in a JVM.

### 3.2. Different Class Loaders Have Different "Views"

Two class loaders can define classes with the **same binary name** and still produce **two distinct runtime types**. A class's identity is tied to both its binary name and its defining class loader.

For example, plugin loader A may find `com.plugins.PluginA` while the system loader cannot. The same name can also exist in plugin loader B yet be treated as a different class.

Many class loaders do not publish all source URLs/paths from which they load classes, and some sources are not even regular files or JARs. There is no contract in `java.lang.ClassLoader` requiring every subclass to provide a "list all loadable classes" method.

### 3.3. A Class May Not Be Loaded Yet or May Have No Direct File

JVM class loading typically happens on demand. A program may contain thousands of `.class` files while actually loading only a subset during a run. Conversely, the runtime may generate classes in memory or use **hidden classes** for implementation purposes; such classes do not necessarily have names findable via `Class.forName`.

There are also differences across classpaths, module paths, `jrt:/` runtime images, and framework packaging. An algorithm that "walks all files in a directory" therefore cannot be assumed correct for all environments.

## 4. APIs Often Mistaken for Classpath Scanners

| API | What it actually returns | What it does not guarantee |
| --- | --- | --- |
| `Class.forName(name)` | The class matching **one provided name**, if found/loadable | Discovering all class names automatically |
| `Class.getDeclaredClasses()` | Member classes/interfaces directly declared inside one class | All classes in the same package/JAR/classpath |
| `Package.getPackages()` | Information about packages already defined per runtime package mechanisms | Names of every class in each package |
| `ClassLoader.getDefinedPackages()` | Packages already defined by that loader | Every class in sources the loader can use |
| `ClassLoader.getResources(name)` | URLs of **resources with the exact requested name** | `**/*.class` globs or universal directory listings |
| `ClassLoader.resources(name)` | Stream of resources with a given name | The set of all resources/classes |
| `ModuleLayer.boot().modules()` | Modules present in the boot layer | Classes of all modules or all layers |
| `Instrumentation.getAllLoadedClasses()` | Classes **already loaded** at the time of the call, via an instrumentation agent | All classes that may be loaded in the future |

In particular, the following call is **not** a package-scanning API:

```java
var urls = Thread.currentThread()
        .getContextClassLoader()
        .getResources("com/acme/plugins");
```

It looks up resources bearing the **exact name** `com/acme/plugins` (if any); it does not mean it returns a list of every file underneath. In a JAR, "directory entries" might not exist; URLs can use many different protocols; modules have separate encapsulation rules for resources. If a scanner relies on `file:` and `jar:` URLs, it only handles **two supported source types**, not the entire classpath.

## 5. The Right Approach When You Need a Class Inventory Within a Defined Scope

First choose a **finite, controllable scope**: for example an `out/` directory or a specified set of application JARs. Next:

1. **Enumerate sources**: pinpoint the exact directories/JARs/modules/plugin locations to scan.
2. **Enumerate entries**: traverse `.class` files using `Files.walk` or `JarFile` (or an API appropriate for each source).
3. **Convert resource paths to candidate binary names**: `com/acme/Widget.class` → `com.acme.Widget`.
4. **Filter and deduplicate**: exclude `module-info`, `package-info` if needed, and handle nested classes, multi-release JARs, and duplicate names across sources.
5. **Verify loadability** with the context-appropriate class loader when truly needed; usually use `Class.forName(name, false, loader)` to avoid forcing immediate initialization.
6. **Check the contract**: interface, runtime annotations, methods/constructors, module accessibility, and application permissions before instantiating/invoking.
7. **Bound resources**: limit paths, file counts, scan time, JAR sizes, and candidate class counts; record per-source errors rather than swallowing exceptions.

**Reading file names** does not execute classes, whereas **loading classes** can trigger bytecode reading, dependency resolution, linkage errors, and custom class-loader behavior. You should not indiscriminately load and initialize every name found just to filter annotations.

### Example A — Walking a Class Directory

If you have output from `javac -d out ...`:

```text
out/
└── com/
    └── demo/
        ├── Alpha.class
        ├── Beta.class
        └── Outer$Nested.class
```

`Files.walk(Path.of("out"))` can traverse physical files in this tree. Converting relative paths to dots yields `com.demo.Alpha`, `com.demo.Beta`, and `com.demo.Outer$Nested` — these are **file-based candidates**, not guaranteed to be loadable one by one by every class loader.

If the root directory is misconfigured, or classes do not reside directly on a source the loader uses, the name set can differ from runtime reality.

### Example B — Walking a JAR

`JarFile` can list `JarEntry` items containing `.class` inside a **specific JAR**. That is an archive-reading tool in `java.util.jar`, not a Core Reflection class-listing API.

Several caveats when scanning real JARs:

- `module-info.class` is a module descriptor; `package-info.class` is normally not an implementation to register.
- Multi-release JARs may contain entries under `META-INF/versions/<version>/`. You must not turn the entire versioned path into a binary name like a normal class. Select the runtime-appropriate version or use a multi-release-aware tool.
- JAR-inside-JAR (*nested/fat JAR*) setups can require framework-specific readers and class loaders; not every nested entry can be treated as a directly loadable class.
- The same binary name may appear in multiple JARs, while the actual loader picks only one version according to its own ordering/algorithm.
- A class present in a JAR does not guarantee complete dependencies, JPMS permissions, or safe initialization.

## 6. Java 17+ Program: Contrasting Reflection with Listing a Single Source

The example below does **two separate things**:

- Uses `Class.forName` to access a class whose name is already known, rather than discovering names.
- Scans **a single root passed in by the runner**: an output directory or a `.jar` file. The program collects only **candidate names**, and never automatically loads every class it finds.

To keep the code standalone and results deterministic, we define a nested class `ExamplePlugin` in the same file. The program intentionally supports only directories and ordinary JARs; it does not claim to be a universal scanner for every class loader, module, or nested/multi-release JAR.

Create **`ClasspathInventoryDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.stream.Stream;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;

public class ClasspathInventoryDemo {
    public static class ExamplePlugin {}

    private static String className(String relative) {
        if (!relative.endsWith(".class")) {
            throw new IllegalArgumentException("Not a .class file: " + relative);
        }
        return relative.substring(0, relative.length() - 6)
                .replace('/', '.').replace('\\', '.');
    }

    public static List<String> findClassNames(Path root) throws IOException {
        List<String> names = new ArrayList<>();
        if (Files.isDirectory(root)) {
            try (Stream<Path> files = Files.walk(root)) {
                files.filter(Files::isRegularFile)
                        .map(root::relativize)
                        .map(Path::toString)
                        .filter(name -> name.endsWith(".class"))
                        .map(ClasspathInventoryDemo::className)
                        .forEach(names::add);
            }
        } else if (Files.isRegularFile(root)
                && root.getFileName().toString().endsWith(".jar")) {
            try (JarFile jar = new JarFile(root.toFile())) {
                var entries = jar.entries();
                while (entries.hasMoreElements()) {
                    JarEntry entry = entries.nextElement();
                    String name = entry.getName();
                    if (!entry.isDirectory()
                            && name.endsWith(".class")
                            && !name.startsWith("META-INF/versions/")) {
                        names.add(className(name));
                    }
                }
            }
        } else {
            throw new IllegalArgumentException("Directory or JAR required: " + root);
        }
        Collections.sort(names);
        return List.copyOf(names);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: java ClasspathInventoryDemo <root>");
        }
        Class<?> known =
                Class.forName("ClasspathInventoryDemo$ExamplePlugin");
        System.out.println("Known: " + known.getName());

        List<String> names = findClassNames(Path.of(args[0]));
        System.out.println("Candidates: " + names.size());
        System.out.println("Contains plugin: "
                + names.contains("ClasspathInventoryDemo$ExamplePlugin"));
    }
}
```

**Compile and run on a directory** with JDK 17 or higher:

```bash
javac -encoding UTF-8 -d out ClasspathInventoryDemo.java
java -cp out ClasspathInventoryDemo out
```

**Output:**

```text
Known: ClasspathInventoryDemo$ExamplePlugin
Candidates: 2
Contains plugin: true
```

There are two `.class` files because `javac` emits one for the outer class `ClasspathInventoryDemo` and one for the nested class `ExamplePlugin`.

**Create a JAR and test the same program:**

```bash
jar --create --file demo.jar -C out .
java -cp out ClasspathInventoryDemo demo.jar
```

**Output remains:**

```text
Known: ClasspathInventoryDemo$ExamplePlugin
Candidates: 2
Contains plugin: true
```

In the second command, the classes used to run the program are still loaded from `out`, while `demo.jar` is simply an **archive read by the program**. They are two independent activities. Running `java -cp demo.jar ClasspathInventoryDemo demo.jar` can also execute this example because the JAR contains the compiled classes, yet the code still scans only the single specified JAR.

**Read the code carefully:**

- `Class.forName("ClasspathInventoryDemo$ExamplePlugin")` succeeds because the binary name is known and the class can be loaded; this call **does not** discover `ExamplePlugin` by enumeration.
- `Files.walk(root)` traverses only the specified directory tree; always close `Stream<Path>` with try-with-resources.
- `JarFile.entries()` lists entries only in one specified JAR; always close `JarFile`.
- `className` merely converts path names ending with `.class` into strings. This does not validate class names, check metadata, or grant loading permissions.
- `Collections.sort` makes result ordering deterministic. Duplicate classes across multiple roots would require a dedicated merge strategy.
- The JAR scanner in the example **intentionally skips** `META-INF/versions/`, so do not use it to accurately report all versioned classes in a multi-release JAR.
- The example does not handle `module-info.class`, `package-info.class`, or nested JARs if encountered; real tools must filter those entries according to their purpose.

If `Candidates` changes when run in a directory containing additional files, that is normal because the scanner counts **entries inside the specified root**, not the number of classes loaded in the JVM.

## 7. "Finding Annotated Classes" Requires an Extra Discovery Layer

Suppose you want classes annotated with `@MyPlugin`.

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface MyPlugin {}
```

**The annotation declaration above is illustrative only**; to compile standalone, add imports from `java.lang.annotation` and place it in a valid file.

What does not exist:

```java
// PSEUDOCODE: This API DOES NOT exist in Java Core Reflection.
List<Class<?>> types = Reflection.findAllAnnotatedClasses(MyPlugin.class);
```

In practice, a scanner must:

1. Determine which roots/modules/sources to scan.
2. Find candidate entries or metadata using an appropriate filesystem/JAR/API mechanism.
3. Optionally parse metadata from bytecode **without loading classes**, or choose to load classes via a class loader with controlled error handling.
4. For loaded classes and runtime-retained annotations, call `clazz.isAnnotationPresent(MyPlugin.class)` / `getAnnotation`.
5. Verify contract/constructors/access rights before instantiating and executing.

`isAnnotationPresent` operates on **one** `Class<?>`; it does not supply the initial set of `Class<?>` objects itself.

### When Should You Use a Scanner Library?

- If you need to scan a **complex classpath**, package filtering, nested JARs, or multiple loader types, consider a library supporting that environment, such as **ClassGraph**, or the scanner of the framework your project already uses.
- If you already use Spring, the framework's component scanning / classpath metadata scanning may fit; Spring finding beans on its own **does not make that capability an API of `java.lang.reflect`**.
- For plugin environments with a clear contract, it is usually better to avoid scanning the entire classpath: use an explicit registry, plugin names in configuration, or **`ServiceLoader`**.

When using a library, verify version/compatibility with the JDK, JPMS, packaging format, and custom class loaders. Do not expect a third-party library to automatically detect every class that could appear dynamically in the future.

## 8. If You Only Want Plugins: `ServiceLoader` Usually Fits the Problem Better

Many programs scan the entire classpath with Reflection just to find all implementations of an interface. If you control the plugin registration contract, the **Service Provider Interface (SPI)** is a clearer choice:

```java
// Sketch: PaymentPlugin is an interface defined by the application.
ServiceLoader<PaymentPlugin> plugins =
        ServiceLoader.load(PaymentPlugin.class);

for (PaymentPlugin plugin : plugins) {
    plugin.execute();
}
```

This snippet is not standalone because the application must define `PaymentPlugin` and declare providers in `META-INF/services/<interface.name>` for the classpath, or `provides ... with ...` in the module descriptor when using named modules.

Key differences:

- `ServiceLoader` lists **declared providers** for a specific service, not every class.
- Providers can be discovered and instantiated/retrieved on demand (depending on how the API is used).
- This model expresses the plugin contract explicitly and avoids scanning every class to guess which ones are plugins.
- You still must handle misconfigured providers, missing dependencies, initialization failures, and appropriate loader/module boundaries.

If the real goal is merely "finding registered plugins", adding an explicit provider list is a better design than unbounded classpath scanning.

## 9. If You Want "Currently Loaded Classes": Java Agents Differ from Core Reflection

`java.lang.instrument.Instrumentation` has the method `getAllLoadedClasses()` returning classes **already loaded into the JVM** when called. This requires a valid instrumentation agent granted an `Instrumentation` instance (typically via `premain` or `agentmain` and an appropriate manifest/setup).

This method:

- Is not an API on `java.lang.Class` or `java.lang.reflect`.
- Cannot be conjured arbitrarily by `new Instrumentation()` (it is an interface passed to the agent by the JVM).
- Does not list every class that could be loaded later or every entry of an unused JAR.
- Can return classes from multiple class loaders, including classes not on the application classpath.
- Returns only a point-in-time snapshot, not an immutable map for the entire application lifetime.

For runtime observability, profiling, and instrumentation tools, this approach fits better than trying to infer loaded classes by scanning files. But for a scanner looking for plugins that might **not yet be loaded**, this API does not replace the source-discovery step.

## 10. Named Modules and Java 9+ Runtime Images

With the Java Platform Module System (JPMS), paths are no longer simply `-cp`. `ModuleLayer.boot().modules()` can report modules in the boot layer, yet that is the set of **modules**, not all classes of each module. Custom layers created later do not necessarily belong to the boot layer either.

To inspect resources inside an **already resolved** module, the `java.lang.module` ecosystem provides `ModuleReference.open()` and `ModuleReader.list()`; this still starts from a module resolved in the runtime configuration and respects API boundaries. **It is not a Core Reflection method that automatically lists every classpath entry**.

JDK classes can also reside in a runtime image via `jrt:/` instead of `rt.jar`-style archives as in very old JDKs. Therefore, do not write scanners that merely search for `rt.jar` and conclude they have listed the entire JDK.

**Distinction:** reading `.class` names inside a module does not guarantee a consumer is allowed to access those classes. Java modules use `exports` for normal API access and `opens` for certain deep reflection cases; both class loaders and module access matter.

## 11. Common Design Pitfalls

### Pitfall A — Calling `ClassLoader.getResources("com/foo")` and Treating Returned URLs as a Package Listing

That API only looks up **resources by name**, and a package does not necessarily have a directory entry in a JAR. Nor does it guarantee returning all class sources. Explicitly constrain sources, handle each URL scheme you support, or use a purpose-built scanner.

### Pitfall B — Scanning `java.class.path` and Claiming "All Classes Found"

That system property does not fully describe custom loaders, named modules, generated classes, agent activity, or specialized environments. Duplicate names across sources also require accounting for loaders and precedence order.

### Pitfall C — Loading Every Class Just to Inspect Annotations

Doing so can increase I/O and memory footprint, cause class-loading/linkage errors, and trigger unintended behavior when using initializing APIs. Prefer filtering via metadata/bytecode first; when loading is needed, use the right loader and `Class.forName(name, false, loader)` with proper error handling.

### Pitfall D — Treating Any `.class` File as a Safe Plugin

A bytecode file can have missing dependencies, be abstract, have incompatible visibility, lack a constructor, or contain dangerous logic. You must validate contracts, allowlists, and instantiation policies; scanning names is only the first step.

### Pitfall E — Scanning the Entire Classpath Too Broadly on Every Request

The classpath can be huge. Scanning it completely on a request path is both costly and error-prone. Restrict packages/roots, cache per application lifecycle, and actively invalidate on class-loader/redeploy changes; in controlled builds, you can generate an index at build time.

### Pitfall F — Forgetting the Difference Between Binary Name and File Path

`com/acme/Outer$Inner.class` is a resource path; the binary name is typically `com.acme.Outer$Inner`. Do not arbitrarily replace `$` with `.` when loading classes. Certain internal names, local/anonymous classes, `module-info`, or `package-info` require dedicated policies.

### Pitfall G — Relying on File/JAR Traversal Order

The order of `Files.walk` or `JarFile.entries` is not a business priority order. Sort results if deterministic output is required and define explicit duplicate resolution. Do not pick "the first class found" as the chosen plugin without an ordering contract.

## 12. Choosing a Solution Based on Your Goal

| Goal | Recommended starting point |
| --- | --- |
| Know class name from configuration | `Class.forName(name, false, loader)` and contract check |
| Read fields/methods/annotations of a known class | `Class<?>` and Reflection |
| List `.class` files in a **specified** directory/JAR | `Files.walk` / `JarFile` |
| Find registered implementations for an interface | `ServiceLoader` / registry |
| Find beans/components in a Spring application | Spring's component scanning / metadata scanning |
| Scan complex packages/classpath of a specific application | Specialized scanner suited to the environment |
| Inventory **already loaded** classes in a JVM | `Instrumentation` via a Java agent |
| Inspect resources of an **identified module** | `ModuleReader` and module resolution API |
| Want every class that could ever appear across all JVM loaders | Must narrow definition and scope; no universal API satisfies this unconditionally |

## 13. Key Takeaways

1. **Reflection starts from a `Class<?>` or an already known type name.** It lets you inspect structure and dynamically interact with members of that type; it has **no** core API that automatically lists every class on the classpath.
2. **Classpath entry, candidate class name, loadable class, loaded class, and accessible class are five distinct concepts.** Do not automatically conflate these sets.
3. **Class discovery** is the responsibility of a filesystem/JAR/module/source index/class-loader framework suited to the runtime environment; each approach covers only the scope it understands.
4. If you need contract-based plugins, consider **`ServiceLoader` or an explicit registry** before resorting to broad scanning.
5. If you need already loaded classes, look toward **Instrumentation** rather than inferring from `.class` file counts.
6. A proper scanning tool needs **a clear scope, filters, class-loader/module handling, error handling, and resource limits**, and must never advertise scanning a directory/JAR as "every class in the JVM".

### Self-Check

- Can `getDeclaredClasses()` find top-level classes in the same package? Why?
- Does `Class.forName("com.example.Widget")` automatically discover any other class names?
- Why can `ClassLoader.getResources("com/example")` return empty even when `com.example.Widget` can still be loaded?
- If a `.class` file resides inside a JAR, has the JVM necessarily loaded that class?
- If two custom class loaders load the same binary name, are you guaranteed to receive a single unique runtime type?
- When building a plugin registry, why does `ServiceLoader` usually make more sense than scanning all JARs?
- Which question does `Instrumentation.getAllLoadedClasses()` answer, and which question does it **not** answer?
- Why does the example code say only "Candidates: 2" instead of "All classes in classpath: 2"?

### Official References

- [`Class` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getDeclaredClasses`, `forName`, and single-type Reflection.
- [`ClassLoader` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `getResources`, scope, and delegation mechanism.
- [`JarFile` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarFile.html): reading entries from a specified JAR.
- [`ServiceLoader` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): SPI-based provider registration and discovery.
- [`Instrumentation` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `getAllLoadedClasses` via an agent.
- [`ModuleReader` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleReader.html): reading and listing resources of an identified module.