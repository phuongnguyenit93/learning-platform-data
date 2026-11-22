# Determining Which Directory, JAR, or Runtime Image a Java Class Comes From

> **Java Core → ClassLoader → Diagnostics.** When encountering `ClassNotFoundException`, `NoSuchMethodError`, duplicate library version errors, or wanting to know where the JVM actually loaded a class from, the question “which file does this class come from?” cannot always be answered using `java.class.path` alone. The source may be a compiled directory, a JAR in a URL search path, a module in the runtime image (`jrt:`), or bytecode generated/read by a custom loader from a source with no corresponding `.class` file. This article shows how to combine the **actual `Class<?>`**, **defining loader**, **`Module`**, **`ProtectionDomain.CodeSource`**, **class-resource URL**, and **JVM class-loading logs** to find the true cause; it includes a Java 17+ program that creates and verifies all three directory/JAR/runtime image cases.

## 1. “Where Does a Class Come From?” Has Multiple Meanings

Distinguish five questions before using the APIs:

1. **Class identity:** Which `Class<?>` object is actually being used by the JVM, with which binary name and defining loader?
2. **Source artifact:** Does the bytecode typically come from a classes directory, a JAR file, a runtime image module, or a custom loader?
3. **Resource URL:** Can a resource `.../Foo.class` with the same name be found, and what is its URL protocol?
4. **Module ownership:** Does the class belong to the named module `java.base`, an application named module, or an unnamed module?
5. **Declared source:** What source does `CodeSource.location` of `ProtectionDomain` report as **labeled** by the loader/runtime?

These five questions do not always have the same answer.

For example, a class `com.example.Widget` is defined by the JVM from bytes fetched over HTTP by a custom loader that does not provide a `CodeSource`, while the loader's resource lookup may fail to find `com/example/Widget.class`. In that case, **there is no reliable file/JAR URL to infer** using reflection alone.

Conversely, with a standard `URLClassLoader` reading a directory or JAR file, `CodeSource` and the resource URL usually provide very useful diagnostic evidence.

## 2. Overview of Diagnostic Signals

| Signal | API/Tool | Indicates | Limitations |
| --- | --- | --- | --- |
| Defining class loader | `clazz.getClassLoader()` | The loader associated with the runtime `Class<?>`. | `null` for bootstrap-defined classes; does not reveal the path. |
| Named/unnamed module | `clazz.getModule()` | The module containing the class, `Module.getName()`. | An unnamed module typically has a `null` name; does not by itself point to a JAR. |
| CodeSource | `clazz.getProtectionDomain().getCodeSource().getLocation()` | The source URL attached to the protection domain, if present. | May be `null` or self-assigned by a custom loader; not guaranteed to be the verified true source. |
| Class resource | `clazz.getResource("/p/Foo.class")` | The resource URL looked up by name in the class's context. | May be `null`, have duplicate names, differ from the actual defined bytes, or not be exposed by a custom loader. |
| Loader search path | `((URLClassLoader) loader).getURLs()` | The URLs configured directly on the URLClassLoader instance. | Not the exact source path of the class; does not include parent/JVM-wide modules. |
| JVM loading event | `-Xlog:class+load=info` (HotSpot) | The source recorded by the JVM when loading the class. | Log depends on runtime/format; requires observing the actual class, does not replace the API contract. |
| Runtime image modules | `jrt:` / `FileSystems.getFileSystem(URI.create("jrt:/"))` | Module resources belonging to the currently running runtime image. | Not an `rt.jar` JAR file, and the URL should not be converted to a regular `File`. |

Choose the **right `Class<?>` object** as the starting point. Looking only at the class name string or application classpath can be wrong when two different loaders define the same binary name.

## 3. Identify the Defining Loader Before Identifying the Path

A runtime class is distinguished by **(binary name, defining class loader)** according to the JVM Specification.

```java
Class<?> type = Class.forName("com.example.Widget", false, loader);
System.out.println(type.getName());
System.out.println(type.getClassLoader());
System.out.println(type.getModule());
```

This is a **snippet** that requires `loader` to be a known `ClassLoader` and the class to exist; it is not a standalone program.

### Why Choosing the Right Class<?> Matters

Suppose:

```text
Host loader H:
  com.example.PluginApi.class

Plugin loader P1:
  com.example.Impl.class from plugin-v1.jar

Plugin loader P2:
  com.example.Impl.class from plugin-v2.jar
```

`P1.loadClass("com.example.Impl")` and `P2.loadClass("com.example.Impl")` can return **two different `Class<?>` objects**. If you call `Class.forName("com.example.Impl")` without passing the right loader, the result may be queried from the caller's loader, not the loader managing the plugin you want to diagnose.

`clazz.getClassLoader() == null` holds for foundational JDK classes defined by the **bootstrap loader**, such as `java.lang.String`. `null` does **not** mean the class was not loaded by the JVM or has a source file at path `null`. Classes defined by the platform loader or application loader usually return the corresponding loader object, which is not necessarily a `URLClassLoader`.

**Do not cast blindly:**

```java
// NOT portable on Java 9+:
java.net.URLClassLoader app =
        (java.net.URLClassLoader) ClassLoader.getSystemClassLoader();
```

The built-in system/application loader in OpenJDK Java 9+ is not a `URLClassLoader` in common configurations; this statement can throw a `ClassCastException`. Only use `getURLs` if the **actual instance** is a `URLClassLoader`.

## 4. Looking at the Module: named, unnamed, and java.base

`Class.getModule()` reveals the module that **actually contains the class**. With:

```java
Module module = String.class.getModule();
System.out.println(module.isNamed());
System.out.println(module.getName());
```

Output on Java 17+:

```text
true
java.base
```

The class `java.lang.String` belongs to the named module `java.base` located in the Java runtime image. Do not look for it via the `lib/rt.jar` path as in Java 8.

An application class placed on the regular classpath typically belongs to the **unnamed module** of its defining loader:

```java
Module m = someApplicationClass.getModule();
System.out.println(m.isNamed()); // usually false for a classpath class
System.out.println(m.getName());  // null if unnamed
```

This is a snippet that requires `someApplicationClass` to be provided. **Do not infer** that just because the module is unnamed, the class comes from a directory rather than a JAR: both directories and JARs on the classpath/`URLClassLoader` can belong to an unnamed module.

A named module `m.library` may be loaded from a JAR on the module path, a compiled modules directory, or a module in the runtime image; `getModule().getName()` is the **module name**, not the full path to the JAR.

## 5. ProtectionDomain.CodeSource.location: Useful, but Null Must Be Handled

For a loaded class:

```java
import java.net.URL;
import java.security.CodeSource;
import java.security.ProtectionDomain;

// Snippet: clazz is the Class<?> to inspect.
ProtectionDomain pd = clazz.getProtectionDomain();
CodeSource cs = pd == null ? null : pd.getCodeSource();
URL location = cs == null ? null : cs.getLocation();
System.out.println(location);
```

`CodeSource.location` is a `URL` describing the source associated with the class. For a `URLClassLoader` loading from a directory/JAR, the location is typically the **URL of the directory or archive path**:

```text
file:/.../classes/                 (directory class source)
file:/.../lib/example.jar          (JAR code source)
```

Note: **The CodeSource of a class inside a JAR is usually `file:...jar`**, not `jar:...!/p/Foo.class`. This is an important distinction between the **archive source** and the **URL to a specific entry/resource**.

CodeSource can be `null` for Java runtime classes, certain generated classes, hidden classes, custom loaders, or special security domains. Therefore, do not call:

```java
// Prone to NullPointerException:
clazz.getProtectionDomain().getCodeSource().getLocation();
```

without checking the values that may be null.

### Is CodeSource Security Evidence?

No. A custom `SecureClassLoader` can construct:

```java
new java.security.CodeSource(
        claimedUrl, (java.security.cert.Certificate[]) null);
```

and attach that URL to class bytes read from elsewhere. This is a snippet that requires `claimedUrl` in context and **does not verify that the bytecode was actually obtained from the stated URL**. For security audits, verify artifacts/hashes/signatures/sources through a trusted pipeline rather than merely logging `CodeSource`.

### Do Not Automatically Convert Every URL to a Path

`Path.of(location.toURI())` only makes sense when the URI scheme and corresponding file-system provider support it. A `file:` code source can be converted to a `Path` with `Path.of(URI)` on the default file system; `jar:` and `jrt:` have different semantics and usually cannot be converted directly to `new File(...)`.

Check `URL.getProtocol()` first; keep it as a `URL` if the purpose is purely diagnostic.

## 6. Class Resource URL: file:, jar:, jrt: Signals

`Class.getResource(String)` locates a resource as a URL:

```java
Class<?> clazz = /* class already found */;
String classResourceName = "/" +
        clazz.getName().replace('.', '/') + ".class";
java.net.URL classResource = clazz.getResource(classResourceName);
System.out.println(classResource);
```

This is a snippet; `clazz` must be defined beforehand. The leading `/` means the resource path is **absolute from the root**. This name construction works for **ordinary classes with a binary name**; for arrays, primitives, hidden/generated classes, or custom representations, one cannot assume a `.class` resource always exists.

Common URLs:

| Source | Illustrative Resource URL | `getProtocol()` |
| --- | --- | --- |
| Directory on classpath/custom URLClassLoader | `file:/work/out/demo/Widget.class` | `file` |
| Entry in a JAR | `jar:file:/work/plugins/widget.jar!/demo/Widget.class` | `jar` |
| JDK 9+ runtime image | `jrt:/java.base/java/lang/String.class` | `jrt` |

The part after the `!` character in `jar:...!/entry` is the **entry name inside the archive**, not a standalone file path that can be passed to `Files.readAllBytes(Path.of(...))` on the default filesystem.

These URLs are **examples**; actual paths vary by machine and JDK. On Windows, URLs may contain a drive letter and escaping; do not concatenate `"file:" + path` manually.

### Is the Resource URL Guaranteed to Be the Bytes Used to Define Class<?>?

**Not always.** `clazz.getResource(...)` performs a **resource lookup**, whereas class loading uses the `loadClass`/`findClass`/`defineClass` mechanism. A custom loader can:

- Define a class from bytes generated directly in memory without exposing any resource.
- Modify/transform bytes before `defineClass`, while the resource URL still points to the original.
- Load a class through one source while `findResource` uses a different mapping.
- Return a resource from a parent/delegated source that does not match the class object being inspected.

If **two JARs contain a resource/class with the same name**, `getResource` may return a URL based on the loader's delegation/ordering policy. An existing URL does not prove that the running class's bytecode was loaded from that URL when the class was defined earlier or the loader uses a different strategy.

A sound reasoning approach: compare **defining loader + module + CodeSource + class resource + class-load logs**; when they do not agree, inspect the loader implementation and transformation path instead of treating a single URL as ground truth.

## 7. Java 17+ Experiment: Three Sources—Directory, JAR, and Runtime Image

We will create two classes:

- `demo.dir.FromDirectory` compiled into `out/dir`.
- `demo.jar.FromJar` packaged in `plugin.jar`.
- `java.lang.String`, which is already present in the JDK 17+ `java.base` runtime image.

The `OriginDemo` application runs from `out/app` and creates a `URLClassLoader` with a search path containing a **directory URL** and a **JAR URL**. Its parent is the platform loader, so the two demo classes are defined by the custom loader itself.

### Project Structure

```text
src/
  dir/
    demo/dir/FromDirectory.java
  jar/
    demo/jar/FromJar.java
  app/
    OriginDemo.java
out/
  dir/         (created by javac)
  jar/         (created by javac)
  app/         (created by javac)
plugin.jar     (created by jar)
```

**File `src/dir/demo/dir/FromDirectory.java`:**

```java
package demo.dir;

public final class FromDirectory {
    public String value() {
        return "directory";
    }
}
```

**File `src/jar/demo/jar/FromJar.java`:**

```java
package demo.jar;

public final class FromJar {
    public String value() {
        return "jar";
    }
}
```

**File `src/app/OriginDemo.java`:**

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.security.CodeSource;
import java.security.ProtectionDomain;

public class OriginDemo {
    private static URL resourceFor(Class<?> type) {
        String path = "/" + type.getName().replace('.', '/') + ".class";
        return type.getResource(path);
    }

    private static URL sourceFor(Class<?> type) {
        ProtectionDomain pd = type.getProtectionDomain();
        CodeSource cs = pd == null ? null : pd.getCodeSource();
        return cs == null ? null : cs.getLocation();
    }

    public static void main(String[] args) throws Exception {
        URL dir = Path.of("out/dir")
                .toAbsolutePath().toUri().toURL();
        URL jar = Path.of("plugin.jar")
                .toAbsolutePath().toUri().toURL();

        try (URLClassLoader loader = new URLClassLoader(
                new URL[]{dir, jar},
                ClassLoader.getPlatformClassLoader())) {

            Class<?> directory = Class.forName(
                    "demo.dir.FromDirectory", false, loader);
            Class<?> archive = Class.forName(
                    "demo.jar.FromJar", false, loader);

            System.out.println("directory loader owned: "
                    + (directory.getClassLoader() == loader));
            System.out.println("directory resource protocol: "
                    + resourceFor(directory).getProtocol());
            System.out.println("directory CodeSource matches: "
                    + dir.equals(sourceFor(directory)));

            System.out.println("jar loader owned: "
                    + (archive.getClassLoader() == loader));
            System.out.println("jar resource protocol: "
                    + resourceFor(archive).getProtocol());
            System.out.println("jar resource inside archive: "
                    + resourceFor(archive).toExternalForm()
                       .contains("!/demo/jar/FromJar.class"));
            System.out.println("jar CodeSource matches: "
                    + jar.equals(sourceFor(archive)));

            System.out.println("loader search URLs: "
                    + loader.getURLs().length);

            Class<?> jdk = String.class;
            System.out.println("runtime module: "
                    + jdk.getModule().getName());
            System.out.println("runtime loader null: "
                    + (jdk.getClassLoader() == null));

            URL jrt = resourceFor(jdk);
            System.out.println("runtime resource protocol: "
                    + (jrt == null ? "null" : jrt.getProtocol()));
            System.out.println("runtime resource module path: "
                    + (jrt != null
                       && jrt.toExternalForm().contains(
                            "java.base/java/lang/String.class")));
            System.out.println("runtime CodeSource absent: "
                    + (sourceFor(jdk) == null));
        }
    }
}
```

### Compiling and Packaging

From the root directory containing `src` (running on Java 17+):

```bash
javac --release 17 -d out/dir src/dir/demo/dir/FromDirectory.java
javac --release 17 -d out/jar src/jar/demo/jar/FromJar.java
jar --create --file plugin.jar -C out/jar .
javac --release 17 -d out/app src/app/OriginDemo.java
java -cp out/app OriginDemo
```

The application program does **not** add `out/dir` or `plugin.jar` to `-cp`. Thus, it does not accidentally let the application loader load these two classes before the custom loader does. The `out/dir` path is converted via `Path.toUri().toURL()` to produce a proper directory URL; `plugin.jar` is a URL pointing to the JAR file.

**Exact stdout compiled and verified with `javac --release 17`, running on OpenJDK 24:**

```text
directory loader owned: true
directory resource protocol: file
directory CodeSource matches: true
jar loader owned: true
jar resource protocol: jar
jar resource inside archive: true
jar CodeSource matches: true
loader search URLs: 2
runtime module: java.base
runtime loader null: true
runtime resource protocol: jrt
runtime resource module path: true
runtime CodeSource absent: true
```

### Why Are the Three Source Types Recognized?

1. **Directory class:** `URLClassLoader` reads `out/dir/demo/dir/FromDirectory.class`; the class resource URL has the `file:` protocol, while `CodeSource.location` equals the `out/dir/` root. The class is indeed defined by the custom loader.
2. **JAR class:** `plugin.jar` contains the entry `demo/jar/FromJar.class`. The resource URL is `jar:...!/demo/jar/FromJar.class`; `CodeSource.location` is the URL to the **entire plugin.jar**. The class is defined by the same custom loader.
3. **Runtime class:** `String.class` belongs to `java.base`, managed by the bootstrap loader (`getClassLoader() == null`). Resource lookup returns `jrt:`; this class's `CodeSource` is not exposed in a file/JAR form in the demo.
4. `getURLs().length == 2` only states that the loader is configured with two search URLs. It does not mean the entire JVM only has two class sources; `String` is still loaded from the runtime image via the bootstrap loader.
5. `Class.forName(name, false, loader)` instructs the JVM to load/locate the class without forcing its static initializer to run. The test focuses on **provenance**, without relying on initialization side effects.

Actual paths depend on where the code is run, so the article prints **the protocol and Boolean checks** instead of hard-coding absolute paths.

### What the Example Does NOT Prove

- Does not prove that `CodeSource` is a trusted signature/source verification.
- Does not prove that every custom loader provides a `.class` resource.
- Does not prove that `getURLs()` lists loaded classes; it is the search path configuration.
- Does not test the case of two JARs containing the same class/resource name or a class being transformed before being defined.
- Does not accurately measure the timing/class unloading when the loader closes.

To know which entry a real loader read in production, combine logging and inspect the framework's loader implementation.

## 8. What Is the jrt: Runtime Image?

Starting in Java 9, the JDK/JRE image uses a **modular runtime image**. Foundational Java classes are no longer typically distributed in a standard `rt.jar` as in Java 8. With Java 9+ APIs, module resources are represented using the **`jrt:`** URI/URL scheme.

Examples:

```text
jrt:/java.base/java/lang/String.class
jrt:/java.logging/java/util/logging/Logger.class
```

Logical structure:

```text
jrt:/
  java.base/
    java/lang/String.class
  java.logging/
    java/util/logging/Logger.class
```

This is the **logical path space of the runtime image**, not an indication that an actual `java.base` directory with regular `.class` files exists on disk. For HotSpot/OpenJDK runtime images, module data is typically stored in the `lib/modules` image file; this format differs from traditional JAR/ZIP archives.

**Do not convert `jrt:/java.base/...` to `new File(...)` and try to read it.** If you need to traverse accessible runtime module data, use the jrt filesystem provider:

```java
import java.net.URI;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Path;

// Snippet: Java 9+ on a JDK supporting the jrt file system:
URI uri = URI.create("jrt:/");
FileSystem fs = FileSystems.getFileSystem(uri);
Path stringClass = fs.getPath(
        "/modules/java.base/java/lang/String.class");
System.out.println(java.nio.file.Files.exists(stringClass));
```

This is an illustrative snippet inside a method with `throws IOException` or appropriate exception handling; `getFileSystem` depends on the provider/file system already created/available in the environment. Do not hard-code the physical layout or expect `jrt` to work on Java 8.

### Runtime Image Differs from a Module JAR

A **named module** can come from:

- Runtime image (`jrt:`, for example `java.base`).
- Modular JAR on the module path (`file:`/`jar:` for the artifact).
- Exploded module directory on the module path.
- Custom ModuleLayer with its own class sources.

Therefore, `clazz.getModule().isNamed() == true` is **not sufficient** to conclude that a class belongs to the JDK runtime image. You must examine **the module name and resource/source** along with runtime provenance. Conversely, a Java class in a plugin JAR can belong to an unnamed module when loaded by a URLClassLoader from a classpath-style search path.

## 9. Class Resource, ClassLoader.getResource, and Duplicate Resources

The methods:

```java
// Snippet with Class<?> clazz:
java.net.URL viaClass =
        clazz.getResource("/demo/Widget.class");

ClassLoader loader = clazz.getClassLoader();
java.net.URL viaLoader = loader == null ? null
        : loader.getResource("demo/Widget.class");
```

The two resource names differ in syntax:

- `Class.getResource("/p/Foo.class")`: the leading `/` indicates an **absolute** resource name.
- `ClassLoader.getResource("p/Foo.class")`: the resource name uses a `/`-separated path **without a leading `/`**.
- `Class.getResource("Foo.class")`: **relative** to the package of the target class on which the method is called.
- `ClassLoader.getSystemResource(...)` uses the system class loader and is not a universal solution for other custom loaders.

For named modules, resource lookup is subject to **module encapsulation**, with an API exception for resources whose names end in `.class`; regular resources inside an encapsulated package may be blocked. Do not use a `null` `config.yml` resource to conclude that the module/class was not loaded.

When duplicate resource names exist across multiple URLs/JARs, `ClassLoader.getResources(String)` can list multiple found URLs (according to the delegation/visibility policy) for debugging:

```java
// Snippet: loader is the ClassLoader being inspected:
java.util.Enumeration<java.net.URL> urls =
        loader.getResources("demo/Widget.class");
while (urls.hasMoreElements()) {
    System.out.println(urls.nextElement());
}
```

**This is not a list of all classes defined by the JVM.** `getResources` returns the resources that can be found by name, not a list of class objects. If a loader already defined `Widget` from JAR A, and later the resource order changes or the class file in JAR A is replaced, the current result is not necessarily the exact bytes the JVM used earlier.

To detect **multiple versions of a class with the same name**, log each resource URL, check artifact checksums, and inspect `clazz.getClassLoader()`/`CodeSource` of the class actually being used.

## 10. URLClassLoader.getURLs: Search Path Is Not Final Provenance

`URLClassLoader` allows reading the configured URL search path:

```java
if (loader instanceof java.net.URLClassLoader urlLoader) {
    for (java.net.URL url : urlLoader.getURLs()) {
        System.out.println(url);
    }
}
```

This snippet uses pattern-matching `instanceof` (stable in Java 17+), with the variable `loader` of type `ClassLoader`. The `getURLs()` array contains the initial URLs and any URLs added via `addURL` for that loader itself.

However:

- Parent delegation may return a `Class<?>` from the parent, which is not in the child's search URLs.
- A single source URL may contain hundreds of classes; some URLs may never have been used.
- Manifest Class-Path and multi-release JAR lookup have their own semantics.
- An already defined class remains that same class; adding a new URL does **not** change that class's bytecode.
- The loader might not be a URLClassLoader, especially the built-in app loader in Java 9+.

**If the question is “Where does Class X actually come from?”, then `clazz`, not `loader.getURLs()`, is the starting point.**

## 11. When Do Class-Loading Logs Help Confirm the Source?

In HotSpot JDK 17+, you can enable `-Xlog:class+load=info` **before reproducing the issue** to record the load event and source of the relevant class:

```bash
java -Xlog:class+load=info -cp out/app OriginDemo
```

A log line typically contains the binary class name and `source:`; for JDK classes, you may also see `shared objects file` from CDS instead of a `jrt:` URL. Do not force the URL in the log to match `Class.getResource` or `CodeSource.location`: those are different signals. If an event is missing, the class may have already loaded before logging began. When the source from a custom loader, module layer, or instrumentation is unclear, combine the actual `Class<?>`, loader identity, and source metadata. Details on how to enable/filter logs and distinguish load/init/unload are covered in the two dedicated articles on Unified Logging.
## 12. Data May Not Reside on Disk: Generated/Hidden/Custom Classes

Some frameworks generate bytecode directly in memory (proxies, lambda implementations, hidden classes, code generation). They may:

- Have no corresponding `.class` file in a regular directory/JAR.
- Not expose a class resource via `Class.getResource(...)`.
- Have `CodeSource.location == null` or metadata that does not point to an actual file.
- Have a class name with a special structure unsuitable for blindly constructing a resource path.
- Be defined by a custom loader from bytes read through a database/network/transformation pipeline.

A class named `com.example.GeneratedProxy` does not necessarily correspond to a file `com/example/GeneratedProxy.class`. `getResource` returning `null` does not prove the class is broken or unloadable: the existing `Class<?>` itself is proof that the JVM knows about it.

For **arrays/primitives**:

```java
System.out.println(int.class.getClassLoader());
System.out.println(String[].class.getClassLoader());
```

Both can be `null` on a typical runtime, because primitive classes are not created by a user-defined loader; array classes follow loader semantics based on their component type. Do not try to look for `[Ljava/lang/String;.class` as a real JAR entry.

If the program uses generated classes, the best approach is to enable the **bytecode generator's diagnostic mode** to dump/record provenance (only when authorized and containing no secrets), trace loader.defineClass calls, and store separate build/version metadata.

## 13. When Can You Trust the Source and When Do You Need Further Verification?

A checklist before concluding “the class comes from JAR A”:

1. **Do you have the Class<?> actually being used?** If you only have the class name, you do not yet know the loader instance.
2. **Is the defining loader the expected loader?** Check `clazz.getClassLoader()` along with an identity check.
3. **What is the module name?** A named module can come from the runtime image, a module JAR, an exploded directory, or a custom layer.
4. **What is the resource URL protocol?** `file:`, `jar:`, `jrt:`, or `null`.
5. **What is the CodeSource location?** Is it null? `file:...jar` or `file:...classes/`?
6. **Do the class-loading logs record a corresponding event?** Logs may start before you configured them if the class was already loaded beforehand.
7. **Are there duplicate classes/resources across multiple JARs?** Use `getResources` or dependency diagnostics.
8. **Is there transformation/instrumentation?** The bytes in the archive may differ from the bytes defined by the JVM.
9. **Could the artifact have been replaced after the JVM loaded it?** The source currently on disk is not guaranteed to still be the bytes that were loaded.
10. **Are you investigating a runtime error or a security issue?** CodeSource is metadata/diagnostics, not provenance attestation.

In a plugin architecture, storing an activation record containing `pluginId`, artifact checksum, loader identity, module identity, version, and class entry name can be more helpful for debugging than simply printing `getURLs()` at the time an error occurs.

## 14. Common Mistakes and How to Handle Them

| Mistake / Wrong Assumption | Consequence | Fix |
| --- | --- | --- |
| Using `System.getProperty("java.class.path")` to locate all JVM classes | Does not include all modules/custom loaders. | Start from `Class<?>`, loader, module, and source. |
| Using `new File(resource.toURI())` with `jar:`/`jrt:` | `IllegalArgumentException` or no regular filesystem path exists. | Keep the URL/stream; use JarFile or jrt FileSystem when needed. |
| Seeing `CodeSource == null` and concluding the class is broken | Runtime/hidden/custom classes may have no location. | Analyze the module, resource URL, and logs. |
| Seeing `getResource == null` and thinking the class does not exist | Resource lookup has different semantics from class definition. | Use `Class<?>`, loader/module; inspect the custom loader's source. |
| Seeing `file:...jar` in CodeSource and expecting the `jar` protocol | CodeSource usually points to the archive, while resource points to the entry. | Distinguish archive location vs. entry URL. |
| Expecting Java 17 `String.class` to be in `rt.jar` | Java 9+ runtime images do not use legacy rt.jar like Java 8. | Look at `jrt:/java.base/...`. |
| Switching loaders when you only want to check a class's source | Creates a different class namespace, not representing the running class. | Inspect the exact Class object. |
| Casting the system loader to URLClassLoader | Java 9+ does not guarantee that subtype. | Only cast if `instanceof`; use class/module/provenance APIs. |
| Calling `getURLs` and assuming the first URL contains the class | Parent delegation/ordering/JAR metadata can change the outcome. | Identify the class's actual loader and source. |
| Parsing URLs with unchecked `split("!")` string splitting | Different URI schemes and encodings behave differently. | Use appropriate `JarURLConnection`/`URI` APIs and handle `null`. |
| Printing full paths into public production logs | May expose host/deployment layout. | Sanitize paths and restrict log access permissions. |
| Assuming bytes have a valid signature because `CodeSource` has a URL | A custom loader can assign any URL itself. | Verify the source/signature/hash independently. |
| Source filename on disk changed, assuming the running class is the “new version” | An already defined class does not automatically update. | Reload with a new loader per the plugin architecture and manage identity. |
| Ignoring multi-release JARs | The JVM may select a versioned entry based on the runtime. | Check the manifest/`META-INF/versions` and loader semantics. |

## 15. Workflow for Investigating a Real Dependency/Plugin Error

**Scenario:** The app encounters `NoSuchMethodError: com.vendor.lib.Util.newMethod()` even though you added a “right version” JAR to the startup script.

### Step A — Find the Caller/Callee Class Actually Running

From a debugger or an authorized log snippet:

```java
// Snippet: class VendorUtil resolved in the app:
Class<?> util = com.vendor.lib.Util.class;
System.out.println("class: " + util.getName());
System.out.println("loader: " + util.getClassLoader());
System.out.println("module: " + util.getModule());
```

This is a snippet that depends on the vendor class existing in the project; it is not part of the main demo code.

### Step B — Read CodeSource Safely with Null Handling

```java
java.security.ProtectionDomain pd = util.getProtectionDomain();
java.security.CodeSource cs =
        pd == null ? null : pd.getCodeSource();
System.out.println("source: " +
        (cs == null ? "<not reported>" : cs.getLocation()));
```

If it displays `file:/opt/app/lib/util-1.2.jar` while you expected `util-2.0.jar`, there is already evidence that **the runtime selected the old JAR**. If `CodeSource` is absent, switch to event logs/module data instead of guessing.

### Step C — Check for Resource Duplicates

```java
ClassLoader loader = util.getClassLoader();
if (loader != null) {
    var entries = loader.getResources(
            "com/vendor/lib/Util.class");
    while (entries.hasMoreElements()) {
        System.out.println("candidate: " + entries.nextElement());
    }
}
```

The output may show multiple candidate resources; the resource lookup order is not necessarily proof of which bytecode was defined by a custom loader.

### Step D — Identify the Exact Running Runtime

Check `java -version` of the **actual process** (server, container, IDE run configuration), dependency tree, loader hierarchy, and `-Xlog:class+load=info` if supported by the HotSpot JVM. `getURLs` or `java.class.path` alone does not describe the entire resolution/module graph.

### Step E — Fix the Right Source / Class Loading Policy

- Remove the old-version JAR **from the right loader path**.
- Align dependencies across build and deployment artifacts.
- If the class has already been defined in the JVM, a restart or a new loader generation by design is required; merely copying a JAR into a folder does not update the running class.
- For plugin child loaders, check whether parent-first delegation returns an API/dependency version from the host first.
- If the class comes from a runtime module, do not try adding a duplicate `java.*` JAR to override it.
- Run tests to verify the API/method version and load-source logs after the fix.

Do not jump to `ClassLoader#addURL` or casting the system loader: it may not affect the loader used to resolve the failing class.

## 16. Self-Check

1. **To know which class is actually running, should you start from the string name or from `Class<?>`?**  
   From the `Class<?>` used by the actual code, because it is bound to the defining loader and module.

2. **What does `clazz.getClassLoader() == null` typically mean for `String.class`?**  
   `String` is defined by the bootstrap loader, not that the JVM “forgot” the class.

3. **Do `CodeSource.location` for a JAR class and the resource URL have the same protocol?**  
   Not necessarily. With `URLClassLoader` in the demo: the code source is `file:...plugin.jar`, while the class resource is `jar:file:...plugin.jar!/entry`.

4. **What source does the class resource URL `file:/tmp/classes/p/X.class` suggest?**  
   A class-file resource inside a directory tree on the filesystem; it must be cross-checked against the defining loader and CodeSource.

5. **Is `jrt:/java.base/java/lang/String.class` a JAR file on disk?**  
   No. It is a logical path into the Java runtime image module `java.base`.

6. **Is a named module guaranteed to reside in the runtime image?**  
   No. A named module can be a modular JAR/exploded module on the module path or in a custom layer.

7. **If `CodeSource` is null while `Class<?>` exists, does that mean class loading failed?**  
   No. The source may simply not be exposed via CodeSource.

8. **If `URLClassLoader.getURLs()` returns two URLs, does that mean the loader has loaded two classes?**  
   No. It lists the configured search path.

9. **Does `Class.getResource` always return the exact bytes the JVM defined?**  
   No. The loader may transform bytes, the resource lookup may use a different path, or the class may be generated.

10. **Why should you use `clazz.getModule()` when diagnosing on JDK 17+?**  
    It identifies the module containing the class, helping distinguish runtime modules, application named modules, and unnamed modules.

11. **Can any `jar:` or `jrt:` URL be converted into `new File(...)`?**  
    No. You need a scheme-specific API or the corresponding stream/filesystem provider.

12. **Is `-Xlog:class+load=info` a mandatory Java standard across all JVM vendors?**  
    No. It is a diagnostic feature of JVMs with Unified Logging (specifically OpenJDK/HotSpot); it depends on the implementation.

13. **If `Class.forName` succeeds in finding a class, is the `Foo.class` resource guaranteed to be found?**  
    No. Class lookup and resource lookup are two separate APIs with their own contracts/semantics.

14. **If a loader has already loaded an older version of a class, does copying a new JAR automatically replace the runtime type?**  
    No. A defining loader does not automatically redefine a class when the file on disk is replaced.

## 17. Official References

- [Java SE 21 — Class](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): `getClassLoader`, `getModule`, `getResource`, and the runtime Class object.
- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): delegation, `getResource`, `getResources`, and module encapsulation for resources.
- [Java SE 21 — URLClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html): directory/JAR URL search path, `getURLs`, `findClass`.
- [Java SE 21 — CodeSource](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/CodeSource.html): URL location and certificates/signers metadata.
- [Java SE 21 — ProtectionDomain](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/ProtectionDomain.html): code source and security domain properties.
- [Java SE 21 — Module](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html): `getName`, `isNamed`.
- [Java SE 21 — FileSystems](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileSystems.html): `getFileSystem(URI)` for applicable file systems, including the jrt provider in supported environments.
- [Java SE 21 — java launcher](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): `-Xlog:class+load`, Unified Logging, and diagnostics.
- [JDK 9 — JEP 220 Modular Run-Time Images](https://openjdk.org/jeps/220): runtime image model replacing traditional `rt.jar` archives.
- [JVMS Java SE 21 `5.3](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3): class identity by binary name and defining loader.
