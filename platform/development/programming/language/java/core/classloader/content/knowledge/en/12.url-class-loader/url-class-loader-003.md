# URL Order and Handling Duplicate JARs or Classes in URLClassLoader

## 1. The Problem: Multiple Sources with the Same Binary Name

In a Java system that uses multiple libraries, two JAR files can both contain `com.example.lib.Parser.class` but in **two different versions**. A `URLClassLoader` can be created with a list of URLs pointing to multiple JARs or directories:

```java
try (URLClassLoader loader = new URLClassLoader(
        new URL[] {firstJarUrl, secondJarUrl},
        parentLoader)) {
    Class<?> parser = loader.loadClass("com.example.lib.Parser");
}
```

This is an **illustrative snippet**; the URL and parent variables must be provided by the application. The key question is: if both URLs contain `Parser.class`, does the JVM load both versions and then pick the newest one, or is there a different precedence rule?

In the standard model:

1. `URLClassLoader` inherits the `ClassLoader.loadClass` algorithm with **parent-first delegation**. If the parent can provide the class, the child loader immediately receives the parent's class and does not need to search the local URLs.
2. If the parent cannot find the class, `URLClassLoader` searches for the bytecode in **the URLs belonging to that loader's own search path**, following the configured search order and the corresponding classpath/JAR expansion mechanism.
3. For a given binary name, once the loader has successfully defined the class, subsequent `loadClass` calls on the same loader typically **reuse the already-loaded definition**, rather than automatically switching to a version at a later URL.
4. If two versions of a class with the same name need to coexist under two independent runtime identities, they must be defined by **two different defining loaders**. Within the same defining loader, a binary name cannot be arbitrarily defined repeatedly as two versions.

In short: **URL order only matters for classes/resources that the parent has not already satisfied and that the loader actually has to look up from local sources**. You must not look solely at JAR order and ignore parent delegation.

## 2. Which URLs Does URLClassLoader Accept?

`URLClassLoader` is a `ClassLoader` that can search for classes and resources from URLs pointing to directories or supported JARs, commonly used to build plugin environments, tools, or dynamic library loaders. A common way to instantiate it is:

```java
URL[] paths = {
    Path.of("plugins/api.jar").toUri().toURL(),
    Path.of("plugins/implementation.jar").toUri().toURL()
};

try (URLClassLoader loader = new URLClassLoader(paths, parentLoader)) {
    Class<?> implementation = loader.loadClass(
            "com.example.plugin.Implementation");
}
```

This is a **snippet**, assuming both JARs are valid, the class and `parentLoader` exist, and the necessary APIs are imported. A URL pointing to a **directory** must be set up as a valid directory URL (typically with a trailing `/`), for example from `Path.toUri().toURL()` of an existing directory.

Points to distinguish:

- URL pointing to a **JAR**: the JAR contains entries such as `com/example/plugin/Implementation.class`.
- URL pointing to the **root directory of the package tree**: the directory containing the path `com/example/plugin/Implementation.class`, not the directory `.../com/example/plugin/`.
- **URL order**: when the loader must search locally, entries searched earlier get the chance to provide the class/resource first.
- **Parent loader**: the parent can supply the class ahead of the entire local search path; this is independent of the URL order in the child.
- `loader.getURLs()` returns the URLs registered in the loader's search list in order; this is **not necessarily** an exhaustive listing of all indirect sources introduced into the search process by manifests/JARs or launcher configuration.

A URL merely being listed **does not prove** that the file exists, is readable, has a valid manifest, has a compatible class file version, or is actually selected to define a class.

## 3. Parent-First Comes First, URL Order Second

Suppose we have:

```text
Application Loader (parent)
  └── lib.Json  [version 1.0]

Plugin URLClassLoader (child)
  ├── URL[0] = plugin/lib-json-2.0.jar
  └── URL[1] = plugin/plugin.jar
```

If the code calls:

```java
Class<?> json = pluginLoader.loadClass("lib.Json");
```

and the parent already has a definition of `lib.Json`, the result is normally **the class defined by the parent**, even though the child's first URL contains version 2.0.

This happens because of the default algorithm:

```text
child.loadClass("lib.Json")
    |
    +-- findLoadedClass("lib.Json") -> already recorded? return Class
    |
    +-- parent.loadClass("lib.Json") -> found? return parent Class
    |
    +-- child.findClass("lib.Json")  -> only when parent does not find it
              |
              +-- search across the child's URL sources
```

The diagram shows the overall logic; the actual method also involves class-loading locks, validation checks, linking/resolution, and loader state.

**Therefore:** moving the version 2.0 JAR from URL[1] to URL[0] **does not help** if parent-first already picked the parent's version 1.0. Before changing the URL order, you need to determine the **defining loader** of the class being loaded.

Some plugin frameworks design **selective child-first** delegation for specific packages, but that is a custom policy. You should not assume by default that `URLClassLoader` uses child-first.

## 4. If Two URLs of the Same Loader Contain the Same Class

Consider a child loader whose parent does not have the class `sample.Duplicate`:

```text
URL[0] -> A.jar
           └── sample/Duplicate.class  (origin() returns "A")
URL[1] -> B.jar
           └── sample/Duplicate.class  (origin() returns "B")
```

When `URLClassLoader` searches locally, it encounters the copy in A first and defines `sample.Duplicate` from A (assuming there are no special redirects or indirect sources altering the search path). The already-defined class is not automatically replaced with the copy in B just because a later call "wants version B".

If you create **another URLClassLoader** with the URLs reversed:

```text
URL[0] -> B.jar
URL[1] -> A.jar
```

the new loader can define `sample.Duplicate` from B. The two returned classes:

- Have the same `Class.getName()`: `"sample.Duplicate"`.
- May have different bytecode/logic.
- Are **not equal** under `Class<?> == Class<?>` comparison because their defining loaders differ.
- Cannot have their instances treated as the same type solely based on having the same binary name.

Even if the exact same `.class` file is used in both sources, type identity still depends on **(binary name, defining loader)**.

### No "Newer JAR Wins" Rule

`URLClassLoader` does not automatically compare Maven versions, timestamps, JAR file names, or version numbers in `pom.properties` to pick the "best" version. If multiple classes with the same name are on the loader's search path, **order and delegation** are what you need to inspect, not "the last one will override".

If two JARs coexist but contain different packages/classes, the loader can load classes from both. What causes issues are **duplicate binary names**, **incompatible dependencies**, or package/module constraints, not every case of having multiple JARs.

## 5. Java 17+ Experiment: Reversing URLs Changes the Selected Class

The example below creates two separate directories instead of two JARs. For `URLClassLoader`, both JARs and class directories are valid URL search roots; using directories keeps the exercise completely self-contained without needing to prepare JARs manually.

The program:

1. Creates two `sample.Duplicate` source files with the **same binary name** that return different values.
2. Compiles each source into directory A or B using `JavaCompiler`.
3. Creates two independent `URLClassLoader` instances, one with URL[A,B] and one with URL[B,A].
4. Checks the returned class, defining loader, and resource with the same name.
5. Closes the loaders and cleans up temporary files upon completion.

Save the **entire** following code as `UrlOrderDemo.java`:

```java
import java.io.IOException;
import java.io.InputStream;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Enumeration;
import java.util.List;
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public class UrlOrderDemo {
    private static final String CLASS_NAME = "sample.Duplicate";
    private static final String MARKER =
            "lesson-url-order-2026.marker";

    private static String read(URL url) throws IOException {
        try (InputStream input = url.openStream()) {
            return new String(input.readAllBytes(),
                    StandardCharsets.UTF_8);
        }
    }

    private static void compile(JavaCompiler compiler,
                                Path source, Path output) {
        int exit = compiler.run(null, null, null,
                "--release", "17",
                "-d", output.toString(), source.toString());
        if (exit != 0) {
            throw new IllegalStateException("Compilation failed");
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Use a full JDK");
        }

        Path root = Files.createTempDirectory("url-order-demo-");
        Path a = root.resolve("a");
        Path b = root.resolve("b");
        Path sourceA = a.resolve("sample/Duplicate.java");
        Path sourceB = b.resolve("sample/Duplicate.java");
        Path classA = a.resolve("sample/Duplicate.class");
        Path classB = b.resolve("sample/Duplicate.class");
        Path markerA = a.resolve(MARKER);
        Path markerB = b.resolve(MARKER);

        try {
            Files.createDirectories(sourceA.getParent());
            Files.createDirectories(sourceB.getParent());

            Files.writeString(sourceA,
                    "package sample; public class Duplicate { "
                    + "public static String origin() { return \"A\"; } }");
            Files.writeString(sourceB,
                    "package sample; public class Duplicate { "
                    + "public static String origin() { return \"B\"; } }");
            Files.writeString(markerA, "A");
            Files.writeString(markerB, "B");

            compile(compiler, sourceA, a);
            compile(compiler, sourceB, b);

            URL urlA = a.toUri().toURL();
            URL urlB = b.toUri().toURL();
            ClassLoader parent = ClassLoader.getPlatformClassLoader();

            try (URLClassLoader first = new URLClassLoader(
                        new URL[] {urlA, urlB}, parent);
                 URLClassLoader reverse = new URLClassLoader(
                        new URL[] {urlB, urlA}, parent)) {

                Class<?> ca = first.loadClass(CLASS_NAME);
                Class<?> cb = reverse.loadClass(CLASS_NAME);

                System.out.println("firstClass="
                        + ca.getMethod("origin").invoke(null));
                System.out.println("reverseClass="
                        + cb.getMethod("origin").invoke(null));
                System.out.println("sameBinaryName="
                        + ca.getName().equals(cb.getName()));
                System.out.println("sameClassObject=" + (ca == cb));
                System.out.println("firstDefiningIsFirst="
                        + (ca.getClassLoader() == first));
                System.out.println("reverseDefiningIsReverse="
                        + (cb.getClassLoader() == reverse));

                System.out.println("firstResource="
                        + read(first.getResource(MARKER)));
                Enumeration<URL> urls = first.getResources(MARKER);
                List<String> values = new ArrayList<>();
                while (urls.hasMoreElements()) {
                    values.add(read(urls.nextElement()));
                }
                System.out.println("firstResources=" + values);
                System.out.println("reverseResource="
                        + read(reverse.getResource(MARKER)));
                System.out.println("stringDefinedByBootstrap="
                        + (first.loadClass("java.lang.String")
                                .getClassLoader() == null));
            }
        } finally {
            Files.deleteIfExists(sourceA);
            Files.deleteIfExists(sourceB);
            Files.deleteIfExists(classA);
            Files.deleteIfExists(classB);
            Files.deleteIfExists(markerA);
            Files.deleteIfExists(markerB);
            Files.deleteIfExists(a.resolve("sample"));
            Files.deleteIfExists(b.resolve("sample"));
            Files.deleteIfExists(a);
            Files.deleteIfExists(b);
            Files.deleteIfExists(root);
        }
    }
}
```

Compile and run (JDK 17 or later):

```bash
javac UrlOrderDemo.java
java UrlOrderDemo
```

**Stdout in a standard JDK environment** when there are no external sources with the duplicate name `sample.Duplicate` or the experiment's marker:

```text
firstClass=A
reverseClass=B
sameBinaryName=true
sameClassObject=false
firstDefiningIsFirst=true
reverseDefiningIsReverse=true
firstResource=A
firstResources=[A, B]
reverseResource=B
stringDefinedByBootstrap=true
```

### Result Analysis

- **`firstClass=A`**: the first loader has URL order URL[A,B], so the `sample.Duplicate` class from A wins in the local search path.
- **`reverseClass=B`**: the second loader has URL order URL[B,A], so the class from B wins.
- **`sameBinaryName=true`**, **`sameClassObject=false`**: the two classes have the same name but are defined by two different defining loaders, so they are **two runtime types**.
- **Both defining=true lines**: in the example, both loaders define the class themselves; the platform parent does not have `sample.Duplicate`.
- **`firstResource=A`**: `getResource` finds the first resource according to delegation + local URL order.
- **`firstResources=[A, B]`**: `getResources` can return **both URLs** of the duplicate-named resource in search order. Selecting a single defining class **does not mean** discarding all duplicate-named resources.
- **`reverseResource=B`**: reversing the URL order also changes the first resource when the parent does not have a copy of that resource.
- **`stringDefinedByBootstrap=true`**: even though `first.loadClass("java.lang.String")` is called, the core platform class is defined by the bootstrap loader, illustrating that parent/bootstrap delegation prioritizes JDK classes.

**Experiment prerequisites:** the program requires a JDK with the `jdk.compiler` compiler module (not just a minimal runtime image). Two temporary roots are created and the URLClassLoaders are closed before cleanup. If the environment restricts file creation or already injects a duplicate-named class/resource via a parent loader, the results need to be re-analyzed according to the actual search path.

### Why Does the Example Use Two ClassLoaders?

If you create **one** `URLClassLoader` and call `loadClass("sample.Duplicate")` twice, the same loader typically returns the **same Class object** due to the already-loaded class mechanism. Changing the order of the external URL array after creating the loader, or adding another JAR containing the same name via `addURL`, does not replace the already-defined class.

To observe both independent definitions, two separate loaders with their respective URL orders are needed. However, those two classes cannot by default be cast to one another in the application: they have different type identities.

## 6. APIs and URL Order: Classes Differ from Resources

A class can be defined **only once** per binary name within the same loader, whereas duplicate-named **resources** can be listed multiple times.

| API | Key Behavior |
| --- | --- |
| `loadClass(name)` | By default checks already-loaded classes, asks the parent, and only then searches the local URLs; returns a single `Class<?>` |
| `findClass(name)` of `URLClassLoader` | Finds/defines the class from the URLs backed by the loader if delegation reaches the local step |
| `findLoadedClass(name)` | Checks whether the JVM has recorded the class as loaded for that loader; avoids needing to redefine it |
| `getResource(name)` | Returns **a single URL**; parent-first by default, then local sources |
| `getResources(name)` | Returns URLs from both parent and local sources, which may contain multiple resources with the same name |
| `findResource(name)` / `findResources(name)` | Local search hooks; `URLClassLoader` provides URL-based implementations |
| `getURLs()` | Inspects the URLs registered for the loader, helping investigate the order of search roots |
| `close()` | Closes the URLClassLoader and releases JAR/URL resources managed by the loader; does not immediately "unload" already-defined classes from the JVM |

**Do not use `getResources` to conclude that the JVM has loaded multiple versions of a class with the same name.** Looking up a resource named `sample/Duplicate.class` across two JARs may return two URLs, while the JVM has chosen one specific class definition for the loader.

Conversely, a successful `loadClass` call does not guarantee that every resource in the same JAR can be found using the API you are calling: resource name, module encapsulation, the selected source, and the loader's policy still matter.

## 7. Duplicate JARs, "JAR Hell", and Binary Compatibility

The issue is not limited to which class wins. Suppose an application is compiled against library version A, which has the method:

```java
package lib;
public class Converter {
    public static String convert(String s) {
        return "A:" + s;
    }
}
```

Yet at runtime, due to URL order or parent-first delegation, the JVM instead defines `lib.Converter` from version B, which **no longer has** the `convert(String)` method:

```java
package lib;
public class Converter {
    public static String render(String s) {
        return "B:" + s;
    }
}
```

The two snippets represent **two mutually replacing versions**; they are not compiled simultaneously under the same name into a single output.

The compiled application bytecode may still contain the call `invokestatic lib/Converter.convert:(Ljava/lang/String;)Ljava/lang/String;`. When the runtime resolves that call against the version B class, the application may encounter a `NoSuchMethodError`.

Typical mismatch symptoms:

| Symptom | Possible Cause |
| --- | --- |
| `NoSuchMethodError` | The runtime selected a class missing the method signature that the code was compiled against |
| `NoSuchFieldError` | The runtime selected a class missing the field referenced by the bytecode |
| `IncompatibleClassChangeError` | Runtime/compile-time incompatibility in class/interface kind or static/instance declaration |
| `ClassCastException` between two classes with the same name | Two defining loaders create two independent runtime types |
| `LinkageError` such as a loader constraint violation | Inconsistent loader visibility for types across method signatures |
| `NoClassDefFoundError` | Possibly a missing indirect dependency, loading error, or a previously failed initialization state |
| Package sealing or signer error | Classes in the same package are defined from sources incompatible with sealing/certificate requirements |

You must read the full stack trace and `Caused by`. You cannot treat every `LinkageError` as "just swap the two JARs".

### Package Sealing and Certificates

A JAR can declare **sealing** in its manifest. When a package is sealed to a specific code source, attempting to define a class in the same package from a different URL/JAR can violate the sealing condition; similarly, classes in the same package within a loader may have to satisfy certificate/signing consistency.

This is why "class A from JAR1 and class B in the same package from JAR2" is not always valid. If a `SecurityException: sealing violation` or certificate mismatch message occurs, investigate the manifest, JAR sources, and package layout—**do not** disable checks or swap JARs indiscriminately.

### JPMS (Java 9+) Differs from the Traditional Classpath

The parent-first + URL order examples primarily examine classes on the **classpath/unnamed module** via `URLClassLoader`. For named modules, module resolution and package scope/readability add extra rules; placing multiple JARs on the module path does not mean URLClassLoader will resolve every conflict by URL array order.

In particular, split packages, `requires`, `exports`, and duplicate module detection follow different rules. You must distinguish **module path resolution** from **classpath search order** before diagnosing.

## 8. Manifest Class-Path, Dependent Libraries, and Indirect Search Paths

A JAR can declare a **`Class-Path`** attribute in `META-INF/MANIFEST.MF` to reference dependent JARs/directories:

```text
Manifest-Version: 1.0
Class-Path: lib/helper.jar lib/support.jar
```

Entries here are resolved according to manifest Class-Path rules, typically relative to the location of the JAR containing the manifest. When the loader mechanism supports processing this attribute, **indirect** dependency sources can enter the search path.

Therefore:

- The URL list passed directly to the constructor does not necessarily describe **every location** where the loader can search for classes.
- Participation of manifest Class-Path affects how the search order is computed when the loader actually reaches the JAR declaring the attribute.
- You should not assume that "URL[1] is definitely always checked before any dependency listed in URL[0]'s manifest". Search path expansion rules and manifest validity conditions must be evaluated according to the loader and the JAR specification.
- Do not assume `getURLs()` always lists all indirect URLs searched via the manifest in the same way as the constructor URLs.

For predictable deployment results, package and declare dependencies consistently using a build tool rather than relying on the accidental ordering of multiple JAR versions.

## 9. Why Are JAR Order on -cp and URL Order in URLClassLoader Not Always Equivalent?

An application can be launched with:

```bash
java -cp "lib/*:app/classes" com.example.Main
```

This is an example of **Linux/macOS** syntax; Windows uses `;`. The `lib/*` wildcard is expanded by the **Java launcher** into the set of JARs in the directory, and the order in which the wildcard lists JARs **is not guaranteed to follow file names/versions deterministically** for an application to rely on.

An explicit URL list created with `new URL[] {urlA, urlB}` in `URLClassLoader` provides the order specified by code; however, parent delegation and additional sources such as manifests can still affect resolution.

Scenarios to distinguish:

| Environment | What to Check |
| --- | --- |
| `java -cp "a.jar:b.jar"` | Launcher classpath and the order of entries passed to the application loader |
| `java -cp "lib/*"` | The JARs actually expanded from the wildcard; do not rely on alphabetical order |
| `new URLClassLoader({a,b}, parent)` | Direct URL order and the parent-first policy |
| `java -jar app.jar` | Entry point/manifest rules; do not treat `-cp` alongside `-jar` as a normal user classpath |
| Maven/Gradle | Dependency graph, conflict resolution, runtimeClasspath, packaged artifacts |
| Plugin/container | Loader tree, framework delegation rules, and private classes/shared packages |
| JPMS module path | Module resolution/readability/exports, not just the URL array |

A build that works on one machine but fails on another because there are multiple JAR versions with duplicate classes and it depends on wildcard ordering is a sign of **non-deterministic packaging**, not the JVM randomly picking classes.

## 10. When You Must Prioritize the Plugin's Library Version

A plugin strategy typically aims for:

- **Host-provided API/SPI** (`com.company.api.*`) to be **shared**: let the parent define them.
- **Implementations and private libraries** (`plugin.internal.*` or packages allowed to be isolated) to be defined by the plugin loader itself.
- Core JDK packages not to be spoofed by a custom loader.
- Types crossing method parameters/return types to be consistent in their defining loader to avoid `ClassCastException`/loader constraint violations.

With the default `URLClassLoader`, if the parent already has a library, parent-first usually wins. If two versions of a library strictly need to coexist, you can consider:

1. **Proper class loader separation:** each plugin uses its own defining loader for its implementation/dependencies, while sharing a host loader for the API.
2. **Namespace-based delegation:** the plugin framework explicitly defines which packages are parent-first and which are local-first, along with resource policies.
3. **Shading/relocation in the build:** rename the package of one library version (if licensing and library mechanics allow) to avoid sharing the same binary name within the same loader boundary.
4. **Cleaning up the dependency tree:** prefer a single unified version when isolation is not truly necessary.

You should not simply override all of `loadClass` to child-first for **every package** to fix a single bug. Doing so can create a separate copy of a host interface, break type identity, or run into security/class-definition constraints.

## 11. Diagnostics: Which Class Was Actually Loaded by the JVM?

If you can obtain the `Class<?>` object, three key pieces of information are the **binary name, defining loader, and code source**.

Place the following helper method in an application class:

```java
static void describe(Class<?> type) {
    System.out.println("name=" + type.getName());
    System.out.println("definingLoader=" + type.getClassLoader());

    java.security.ProtectionDomain pd = type.getProtectionDomain();
    java.security.CodeSource cs =
            pd == null ? null : pd.getCodeSource();
    System.out.println("codeSource=" +
            (cs == null ? "<unknown>" : cs.getLocation()));
}
```

This is a **helper snippet** without its own `main`. You need to import the APIs or use fully qualified names as shown above. `getClassLoader() == null` indicates the bootstrap loader; `CodeSource` can be `null` and should not be taken as proof of the wrong loader.

### Investigation Checklist for Duplicate Classes/JARs

1. **Identify the affected class name** from the exception/stack trace, for example `lib.Json`.
2. **Record the loader receiving the request and the defining loader** of the class actually returned. Parent-first delegation can cause the two loader objects to differ.
3. **Print `getURLs()` of the relevant URLClassLoader**, if you have access to the loader object. Compare the order of constructor URLs, URLs added later, and the actual source path.
4. **Check the duplicates**: `jar tf plugin-a.jar` and `jar tf plugin-b.jar` to see if both contain `lib/Json.class`; compare method signatures with `javap`.
5. **Verify the runtime artifact** rather than only the compile dependency. The built binary may target a different API version than the class loaded at runtime.
6. **Read the manifest and JAR metadata**: `Class-Path`, sealing, multi-release JAR, signer, package version; do not look only at the JAR file name.
7. **Cross-check resource lookup**: use `getResources` if you need to find all copies of `lib/config.properties`; distinguish multiple resource URLs from a single runtime Class.
8. **Check old class loaders** after a hot reload/deploy: already-defined classes/instances are not automatically replaced by modifying URLs or JARs on disk.
9. **Read the exact error type**: `NoSuchMethodError` is usually an ABI mismatch; `ClassCastException` can result from two defining loaders; a sealing violation is a package/JAR policy issue.
10. **If running on the module path**, determine the module graph and readability before relying on assumptions about classpath URL order.

### Using JDK Support Tools

```bash
jar tf plugins/a.jar
jar tf plugins/b.jar
javap -classpath plugins/a.jar -public lib.Json
javap -classpath plugins/b.jar -public lib.Json
```

These are example commands; the file names `plugins/a.jar`, `plugins/b.jar`, and `lib.Json` should be replaced with the actual artifacts/classes. On a JVM with unified logging:

```bash
java -Xlog:class+load=info -cp "app/classes:lib/*" com.example.Main
```

The command uses the Linux/macOS separator; on Windows replace `:` with `;`. The log can indicate the bytecode source, yet you still need to analyze the **defining loader** and how the classpath is expanded. A "logged" file/JAR does not by itself explain why one version took precedence over another.

## 12. Duplicate-Named Resources and ServiceLoader

It is not only `.class` files that can be duplicated: multiple JARs often all contain `META-INF/services/com.example.spi.Plugin`. The characteristics here differ from class duplication:

- `getResource(name)` typically retrieves the first URL according to delegation and local source order.
- `getResources(name)` can enumerate **multiple URLs** with the same name from both parent and local sources, helping libraries discover multiple descriptors.
- `ServiceLoader` consumes provider information following its own protocol, which may depend on the specified loader/context loader; you should not assume it only reads JAR URL[0].
- The provider must be compatible with **the exact runtime SPI interface** used by the host/consumer. If the host and plugin independently define two versions of `spi.Plugin` with different defining loaders, the provider may be invalid even if the descriptor file has the right name.

If two JARs contain a configuration resource `app.properties`, changing the URL order can change which version code using `getResource` receives first. However, if code uses `getResources` and merges all contents, the "winning file" is determined by **the application's merge logic**, not just URLClassLoader.

Since Java 9, named modules add resource visibility rules. Do not use `getResources` behavior on the classpath to directly infer how all resources in named modules are opened.

## 13. Misconceptions to Avoid

| Misconception | Reality |
| --- | --- |
| "URL[0] always wins over every other source." | Not if parent-first already found the class/resource earlier or indirect source rules apply. |
| "The JAR with the highest version will be selected." | URLClassLoader does not automatically select the newest Maven semantic version. |
| "Changing the URL order after a class is loaded replaces its definition." | An already-defined runtime class is not automatically replaced by another source within the same loader. |
| "Having two Duplicate.class files means the same loader holds two runtime classes." | The same binary name can only be defined once within a defining loader; which version wins depends on the search path. |
| "Two different loaders defining the same binary name can still be cast to each other." | Not necessarily; they are two independent runtime types. |
| "getResources returning two .class URLs means the JVM has defined two classes." | Resource enumeration and runtime Class definition are two distinct mechanisms. |
| "Any JARs containing classes in the same package can be loaded together." | Sealing/certificates or module boundaries may forbid mixing sources. |
| "lib/* always sorts JARs by name." | Wildcard expansion order should not be treated as a stable version order. |
| "Inspecting getURLs alone reveals all opened dependencies." | Manifest Class-Path and the parent/framework can add sources that cannot be inferred solely from the URL array. |
| "Closing URLClassLoader immediately unloads classes." | Close releases resources managed by the loader; unloading depends on reachability. |
| "Simply using child-first for all packages solves everything." | It can cause duplicated API/SPI types and type identity errors. |

## 14. Self-Check Questions

**Question 1.** A child URLClassLoader has URL[A.jar,B.jar], both containing `lib.X`; the parent also has `lib.X`. Which class is selected under default parent-first delegation?

**Answer:** The class provided by the parent (or an appropriate ancestor) if the parent can find it. The child's A/B order does not get a chance to be evaluated.

**Question 2.** The parent does not have `lib.X`. Both A.jar and B.jar contain this class. If the URL order is A then B, what typically happens?

**Answer:** The loader searches locally from URL A first and defines the class from A, under standard search path conditions. It does not automatically compare JAR versions.

**Question 3.** Reverse the URLs to B then A in a **new loader**; the class name remains the same. Are the two `Class<?>` objects from the two loaders equal?

**Answer:** No, if each loader defines its own corresponding copy. Different defining loaders result in different runtime type identities.

**Question 4.** `lib.X` has already been loaded from A in loader L; later B is added via `addURL` (if a subclass permits it). Will the next call `L.loadClass("lib.X")` switch to B?

**Answer:** No. The loader reuses the already-recorded/defined class; it does not replace the definition for the same binary name.

**Question 5.** `getResources("config.properties")` returns two URLs. Does that mean there are two runtime `Config` classes?

**Answer:** No. It only shows two resource sources with the same name; class identity must be checked via `Class<?>` and the defining loader.

**Question 6.** A running library throws `NoSuchMethodError` even though the class is present on the classpath. Why might URL order be involved?

**Answer:** The runtime may have selected a different version of the class than the compile-time version, missing the method descriptor called by the bytecode.

**Question 7.** Using `java -cp "lib/*"` and expecting `a.jar` to always beat `z.jar`. Is that reliable?

**Answer:** You should not rely on wildcard expansion order. Eliminate the conflict or configure the classpath/dependencies explicitly.

**Question 8.** Two different JARs contain different classes but belong to the same sealed package. What is the risk?

**Answer:** A sealing violation when the loader attempts to define a class of an already-sealed package from an invalid source. You need to design packages/JARs according to manifest constraints.

## 15. Conclusion and Official Documentation

When using `URLClassLoader`, you need to distinguish two levels of precedence: **parent delegation** first, and only then the **order of local URLs** when the loader must search for classes/resources itself. A duplicate binary name across JARs does not cause a loader to define two classes with the same name; the selected definition will be reused. Resources can be enumerated as multiple URLs, whereas having two runtime classes with the same name coexist requires using **different defining loaders** and controlling type boundaries.

To avoid "JAR hell", standardize the dependency graph, verify the actual defining loader/code source, avoid relying on wildcard ordering, and understand manifest, sealing, and module path constraints before concluding that you need to change the URL order.

References:

- Java SE 17 `URLClassLoader` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- Java SE 17 `ClassLoader` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 `java` launcher (classpath, wildcard): https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Java SE 17 `JarFile` API and multi-release JAR: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarFile.html
- JAR File Specification (manifest Class-Path, sealing): https://docs.oracle.com/javase/8/docs/technotes/guides/jar/jar.html
- JVMS 17 §5.3, Creation of Classes and Interfaces: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
