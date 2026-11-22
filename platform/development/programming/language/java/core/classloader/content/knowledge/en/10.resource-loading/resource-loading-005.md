# getResources, resources, and Listing Multiple Resources with the Same Name

## 1. When do you need to list instead of finding a single resource?

A Java application can use multiple JARs. Two or more JARs can certainly contain **resources with the same name**, for example:

~~~text
parent.jar
└── demo/resource/lesson-source.txt     → PARENT

a.jar
└── demo/resource/lesson-source.txt     → A

b.jar
└── demo/resource/lesson-source.txt     → B
~~~

If you only call `ClassLoader.getResource(name)`, you typically get **a single first URL** along the ClassLoader's search path. However, a plugin manager, metadata reader, service discovery system, or configuration inspection tool may need **every** URL matching the same name. In that case, two notable APIs are:

~~~java
Enumeration<URL> all = loader.getResources(name);
Stream<URL> stream = loader.resources(name);
~~~

This lesson focuses on the difference between **finding one resource** and **listing every visible resource**, parent/child ordering, iterating over `Enumeration` versus `Stream`, and cases that are easy to confuse when resources have duplicate names.

**Distinguish this right from the start:** Resources are typically data such as text files, configuration files, images, `META-INF/services/...`; a resource name is not a binary class name. `getResources` is not a command to read all classes of a JAR and does not list all files in the JAR when you only provide one resource name.

## 2. Four Commonly Used APIs

Given a `ClassLoader loader` object and the resource name `"demo/resource/lesson-source.txt"`:

| API | Result | Meaning |
|---|---|---|
| `loader.getResource(name)` | `URL` or `null` | Gets **one** first resource according to the lookup rules |
| `loader.getResourceAsStream(name)` | `InputStream` or `null` | Opens a stream for the first resource; the caller must close it |
| `loader.getResources(name)` | `Enumeration<URL>` | Lists **the matching URLs** visible to the loader |
| `loader.resources(name)` | `Stream<URL>` | Accesses the matching URLs via the Java Stream API (since Java 9) |

Both `getResources` and `resources` work with **URLs**, not returning content bytes directly. To read the content, open `URL.openStream()` or another suitable API, then close the stream after processing.

An example of the API form; this code is for illustration only, not yet a standalone runnable program:

~~~java
String name = "demo/resource/lesson-source.txt";
ClassLoader loader = Thread.currentThread().getContextClassLoader();

URL first = loader.getResource(name);
Enumeration<URL> urls = loader.getResources(name);
Stream<URL> stream = loader.resources(name);
~~~

`getResources` can throw `IOException`; I/O errors arising when consuming `resources` may be wrapped in `UncheckedIOException`. In real-world applications, you also need to handle the `loader == null` case if obtaining the loader from context or `SomeClass.class.getClassLoader()`.

## 3. ClassLoader Lookup Mechanism

For a `ClassLoader` that follows **parent-first delegation**, the lookup order is usually:

~~~text
child.getResources("demo/resource/lesson-source.txt")
                   │
                   ▼
            Ask parent first
                   │
           PARENT (if any)
                   │
                   ▼
      Traverse child's own sources
                   │
               A then B
                   │
                   ▼
       Enumeration/Stream of URLs
           [PARENT, A, B]
~~~

For example, we create a parent `URLClassLoader` containing `parent.jar`. The child is also a `URLClassLoader` but contains two URLs in the order `[a.jar, b.jar]`.

- `child.getResource(name)` finds **PARENT** first and returns the URL in `parent.jar`.
- `child.getResources(name)` lists **PARENT, A, B** in the order of the experimental configuration.
- `child.resources(name)` represents those URLs as a `Stream<URL>`.
- `parent.getResources(name)` does not itself traverse the child's own resources, so in this example it only has **PARENT**.
- Another loader that does not have `parent.jar` in its search chain, but has `[a.jar,b.jar]`, will list **A, B**.

These rules explain **the example using the default URLClassLoader**. A custom ClassLoader can override `getResource` or `getResources`, or provide resources from non-JAR sources. Resource rules for named modules and the effect of `opens` must also be examined separately.

## 4. Complete Java 17+ Example with Three Resource JARs

The example creates three JARs containing only text resources; the host explicitly creates the parent and child loaders. We choose a resource path specific to this lesson to avoid unintentional collisions with JDK or host resources.

### 4.1. Directory Structure

~~~text
resources-demo/
├── src/
│   └── demo/host/
│       └── ResourceDemo.java
└── resource-src/
    ├── parent/
    │   └── demo/resource/lesson-source.txt
    ├── a/
    │   └── demo/resource/lesson-source.txt
    └── b/
        └── demo/resource/lesson-source.txt
~~~

The `lesson-source.txt` files contain the exact corresponding label, one line per file:

| Path | Content |
|---|---|
| `resource-src/parent/demo/resource/lesson-source.txt` | `PARENT` |
| `resource-src/a/demo/resource/lesson-source.txt` | `A` |
| `resource-src/b/demo/resource/lesson-source.txt` | `B` |

Use UTF-8 text without BOM; a trailing newline at the end of the file may or may not be present because the program uses `strip()`.

### 4.2. Runnable Java File

Create the file **`src/demo/host/ResourceDemo.java`**:

~~~java
package demo.host;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Enumeration;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public final class ResourceDemo {
    private static final String NAME = "demo/resource/lesson-source.txt";

    private ResourceDemo() {
    }

    private static String content(URL url) throws IOException {
        if (url == null) {
            return "(missing)";
        }
        try (InputStream stream = url.openStream()) {
            return new String(
                    stream.readAllBytes(),
                    StandardCharsets.UTF_8).strip();
        }
    }

    private static String content(InputStream input) throws IOException {
        if (input == null) {
            return "(missing)";
        }
        try (InputStream stream = input) {
            return new String(
                    stream.readAllBytes(),
                    StandardCharsets.UTF_8).strip();
        }
    }

    private static String all(Enumeration<URL> urls) throws IOException {
        List<String> names = new ArrayList<>();
        while (urls.hasMoreElements()) {
            names.add(content(urls.nextElement()));
        }
        return String.join(" > ", names);
    }

    private static String all(Stream<URL> urls) {
        try (urls) {
            return urls.map(url -> {
                try {
                    return content(url);
                } catch (IOException ex) {
                    throw new UncheckedIOException(ex);
                }
            }).collect(Collectors.joining(" > "));
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                    "Usage: ResourceDemo <parent.jar> <a.jar> <b.jar>");
        }

        Path parentJar = Path.of(args[0]).toAbsolutePath().normalize();
        Path aJar = Path.of(args[1]).toAbsolutePath().normalize();
        Path bJar = Path.of(args[2]).toAbsolutePath().normalize();

        if (!Files.isRegularFile(parentJar)
                || !Files.isRegularFile(aJar)
                || !Files.isRegularFile(bJar)) {
            throw new IllegalArgumentException("All three JARs must exist");
        }

        URL parentUrl = parentJar.toUri().toURL();
        URL aUrl = aJar.toUri().toURL();
        URL bUrl = bJar.toUri().toURL();

        // Parent contains parent.jar; child contains a.jar, b.jar.
        // The platform loader does not have the file demo/resource/lesson-source.txt.
        try (URLClassLoader parent = new URLClassLoader(
                     new URL[] {parentUrl},
                     ClassLoader.getPlatformClassLoader());
             URLClassLoader child = new URLClassLoader(
                     new URL[] {aUrl, bUrl}, parent);
             URLClassLoader noParentJar = new URLClassLoader(
                     new URL[] {aUrl, bUrl},
                     ClassLoader.getPlatformClassLoader())) {

            System.out.println("getResource: "
                    + content(child.getResource(NAME)));
            System.out.println("getResourceAsStream: "
                    + content(child.getResourceAsStream(NAME)));

            System.out.println("getResources: "
                    + all(child.getResources(NAME)));
            System.out.println("resources: "
                    + all(child.resources(NAME)));

            System.out.println("parent getResources: "
                    + all(parent.getResources(NAME)));
            System.out.println("without parent.jar: "
                    + all(noParentJar.getResources(NAME)));

            System.out.println("missing single resource: "
                    + (child.getResource("demo/resource/not-found.txt")
                    == null));
        }
    }
}
~~~

**Intentional details:**

- We choose `ClassLoader.getPlatformClassLoader()` as the ancestor for the parent loader and the `noParentJar` loader. This avoids accidentally finding resources on the host application classpath in this test. The resource name is also specifically chosen to ensure it is not present in ordinary JDK modules.
- The `child` loader's parent is the URLClassLoader holding `parent.jar`; the child's own search path is `a.jar` followed by `b.jar`.
- Both `content(URL)` and `content(InputStream)` overloads close the stream. The case where a resource does not exist is explicitly represented as `"(missing)"`.
- `all(Enumeration<URL>)` uses `hasMoreElements()`/`nextElement()` in enumeration order.
- `all(Stream<URL>)` uses the Java Stream API; errors reading a URL inside the lambda are converted from a checked `IOException` to an `UncheckedIOException` so as not to swallow errors.
- The program prints **the content of each resource**, avoiding printing `jar:file:/...` with machine-dependent absolute paths.

### 4.3. Compiling and Packaging JARs

Run the commands from the `resources-demo/` directory, after creating the files above.

**Bash (Linux, macOS, Git Bash):**

~~~bash
mkdir -p build/classes dist

javac -encoding UTF-8 \
  -d build/classes src/demo/host/ResourceDemo.java

jar --create --file dist/parent.jar -C resource-src/parent .
jar --create --file dist/a.jar -C resource-src/a .
jar --create --file dist/b.jar -C resource-src/b .

java -cp build/classes \
  demo.host.ResourceDemo dist/parent.jar dist/a.jar dist/b.jar
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force build/classes,dist | Out-Null

javac -encoding UTF-8 -d build/classes src/demo/host/ResourceDemo.java

jar --create --file dist/parent.jar -C resource-src/parent .
jar --create --file dist/a.jar -C resource-src/a .
jar --create --file dist/b.jar -C resource-src/b .

java -cp build/classes demo.host.ResourceDemo dist/parent.jar dist/a.jar dist/b.jar
~~~

Note: Do **not** put the three resource JARs on `-cp` of the host run command; the program will load them through the `URLClassLoader` instances it creates itself. If you accidentally place `parent.jar` or `a.jar` on the application classpath, the resource lookup model in the example may differ from expected.

Inspect the JARs if needed:

~~~bash
jar --list --file dist/parent.jar
jar --list --file dist/a.jar
jar --list --file dist/b.jar
~~~

All three JARs must have the exact entry `demo/resource/lesson-source.txt`. The output of `jar --list` may additionally contain `META-INF/MANIFEST.MF` and directory entries.

### 4.4. Exact Stdout

With the exact contents of the 3 text files and the given run command, the result is:

~~~text
getResource: PARENT
getResourceAsStream: PARENT
getResources: PARENT > A > B
resources: PARENT > A > B
parent getResources: PARENT
without parent.jar: A > B
missing single resource: true
~~~

**Line-by-line explanation:**

1. `getResource` retrieves the first resource in parent-first order, so it is `PARENT`.
2. `getResourceAsStream` opens that same first resource, so it also reads `PARENT`.
3. `getResources` combines resources from the parent and the child's URL sources in the expected order: `PARENT > A > B`.
4. `resources` returns a Stream of URLs matching the same name; when consumed with `collect`, the example produces the same order `PARENT > A > B`.
5. `parent.getResources` only sees `parent.jar` and its ancestors; it does not search downward into the child's JARs, so it only has `PARENT`.
6. `noParentJar` points to A then B, and its parent is the platform loader, so it does not see `parent.jar` and produces `A > B`.
7. `getResource` returns `null` for a nonexistent name.

This is **a controlled configuration with the standard URLClassLoader**, not a guarantee that every ClassLoader orders resources in a similar way.

## 5. How do `getResources` and `resources` differ?

### 5.1. `Enumeration<URL>` from `getResources`

~~~java
Enumeration<URL> urls = loader.getResources("example/config.properties");
while (urls.hasMoreElements()) {
    URL url = urls.nextElement();
    // Process each URL
}
~~~

This is a long-standing API, well suited for older Java libraries and places where you want to iterate sequentially with `while`. `getResources` declares `throws IOException`. `Enumeration` provides the element order from the loader, though the Enumeration interface itself does not impose a specific order for every kind of source.

**Do not assume “Enumeration means no duplicates”.** If multiple different JARs contain the requested resource name, the result can contain multiple URLs. If the same resource appears through multiple search paths, whether results are distinguished or duplicated depends on the implementation; the caller must handle duplicates according to business requirements.

### 5.2. `Stream<URL>` from `resources`

Since Java 9, `ClassLoader.resources(String)` returns a `Stream<URL>` for using transformation/filtering/collection operations:

~~~java
try (Stream<URL> urls = loader.resources("example/config.properties")) {
    List<URL> matches = urls.toList(); // Java 16+
    System.out.println("Count: " + matches.size());
}
~~~

This snippet is **for illustration only**, assuming `loader` and the appropriate imports are already in place. On Java 17+, `Stream.toList()` is available. When using a Stream:

- A Stream is typically processed **lazily**: URLs are traversed when a terminal operation such as `toList()` or `collect(...)` is invoked.
- A Stream is **single-use**; once consumed, you cannot invoke a second terminal operation on that same Stream.
- Do not run `parallel()` if ordering is part of your priority logic and you have not verified the contract of the collector/source.
- If traversing resources leads to an I/O error, according to the `resources` documentation, the error may surface as an `UncheckedIOException` while consuming the Stream.
- `try-with-resources` for the Stream is a clean practice when writing general-purpose libraries, especially if the pipeline has `onClose` handlers. **Do not infer** that closing the Stream can close every `InputStream` that you explicitly opened inside `map`; those input streams must be closed individually.

`resources` **does not convert the resource content into a Stream of text lines**. It is a Stream of **URLs**; each URL still needs to be read individually when you want to process its data.

### 5.3. Which API to Choose?

| Need | Recommended API |
|---|---|
| The first single configuration file according to the loader | `getResource` |
| A stream to read the first file | `getResourceAsStream` |
| Listing all URLs with the same name and processing sequentially | `getResources` |
| Filtering/sorting/transforming URLs using the Stream API | `resources` |
| Loading service providers from multiple JARs | `ServiceLoader`, because descriptor formatting and the service contract must also be handled |
| Listing all entries in a JAR | `JarFile`/ZIP API or a JAR-reading mechanism, **not** `getResources(name)` |

## 6. How Important Is Enumeration Order?

When a default child loader delegates to its parent, resources visible to the parent typically appear first. For a standard `URLClassLoader`, its own URLs are searched in search-path order, for example `[a.jar, b.jar]`. However:

- A custom child ClassLoader can change both `getResource` and `getResources`; if it overrides one method while ignoring the other, the behavior of the single-resource API and the multi-resource API may be incompatible.
- If a resource belongs to a **named module**, module encapsulation rules and package openness may prevent the resource from being visible as in the classpath example.
- If JARs are added using the classpath wildcard `lib/*`, the order in which JARs are expanded is not necessarily stable. Do not design configuration priority based on alphabetical file names.
- A JAR manifest `Class-Path`, a framework loader, or a tool-constructed classpath may add resource sources to the search path.
- If a stable business order is needed, it is better to define **explicit priority rules** in the application (for example, config version, priority field, or plugin order) and apply them after collecting the URLs, rather than relying on the arbitrary order of the environment.

**Do not equate resource order with class identity.** For classes with the same name, a loader typically selects one corresponding defined class. For resources with duplicate names, `getResources` can return **multiple URLs** so the caller can decide whether to merge, prioritize, or process all of them.

## 7. Same Resource Name, Multiple URLs: Deciding How to Handle Them

If the result of `getResources(name)` is `[PARENT, A, B]`, an application can choose among three different strategies:

**Pick the first one:** Use `getResource` when the application has the rule “the parent or an earlier source takes precedence”. There is no need to enumerate multiple files if you only want one resource.

**Merge configurations:** Iterate through `getResources` or `resources`, parse each file, and merge them according to a deterministic rule, such as “later entries override earlier keys” or “duplicate keys are an error”. You must specify the merge order clearly and ensure stability according to business requirements.

**Process all of them:** For service metadata, index files, or rule fragments, every resource may be needed. Duplicate files do not mean they should be skipped: each JAR may provide an independent declaration.

Example pattern for merging in the order URLs are encountered (illustrative code, not a standalone runnable program):

~~~java
Enumeration<URL> urls = loader.getResources("features.properties");
while (urls.hasMoreElements()) {
    URL url = urls.nextElement();
    try (InputStream in = url.openStream()) {
        // Parse this file and merge according to the application's rules.
    }
}
~~~

If a file can come from untrusted code or libraries, do not automatically execute its contents or open URLs outside the necessary scope. A URL is a location for accessing a resource, not a certification that the content is valid or safe.

## 8. Resource Names, Absolute Paths, and Relative Paths

### 8.1. `ClassLoader.getResource` does not automatically prepend a package

With `ClassLoader`, you typically specify the resource name as a **path from the root** and **without a leading `/`**:

~~~java
loader.getResource("demo/resource/lesson-source.txt");
~~~

If you pass `"/demo/resource/lesson-source.txt"` to `ClassLoader.getResource`, the lookup may fail because the leading slash is treated as part of the resource name. Use a path from the root as in the JAR.

### 8.2. `Class.getResource` has different rules

With `Class.getResource`:

~~~java
// Illustrative example with ResourceDemo already defined.
ResourceDemo.class.getResource("local.txt");
ResourceDemo.class.getResource("/demo/resource/lesson-source.txt");
~~~

A name **not starting with `/`** is interpreted relative to the class's package; a name **starting with `/`** is interpreted from the root. However, `ResourceDemo.class` belongs to the **system loader** and does not automatically see the JARs created by the child loader in the example. Therefore, simply changing the name to an absolute form **does not automatically make the child's own resources visible**.

If the target is plugin JARs, perform the lookup using the plugin's own loader, such as `child.getResources(name)`, rather than defaulting to the host's class loader.

### 8.3. Resource names are not class names

The file `demo/resource/lesson-source.txt` differs from the name `demo.resource.lesson-source`. Resources use slash-separated paths; a class named `demo.plugin.Greeter` typically has a corresponding bytecode resource at `demo/plugin/Greeter.class`, but retrieving bytecode via the resource API can be subject to module/loader constraints and is not a general-purpose way to “list classes”.

## 9. ServiceLoader: A Real-World Case Requiring Multiple Resources with the Same Name

In the classpath model, Java SPI uses provider configuration files located at:

~~~text
META-INF/services/<fully qualified name of the service interface>
~~~

For example, with `example.api.PaymentProvider`, two plugin JARs may both contain:

~~~text
META-INF/services/example.api.PaymentProvider
~~~

JAR A declares `example.plugins.CardProvider`, and JAR B declares `example.plugins.WalletProvider`. When `ServiceLoader` is given the proper loader that sees both JARs, it can read multiple descriptor files with the same name and discover multiple providers.

Important points:

- `ServiceLoader` is a provider discovery API that understands the descriptor format, checks whether the class/provider conforms to the service interface, and instantiates objects when needed.
- `ClassLoader.getResources("META-INF/services/...")` only returns **URLs**. If you parse descriptors yourself, you must handle comments, encoding, syntax, ordering, and class loaders yourself.
- The service interface must be understood by both the host and plugins as **the same runtime type**; two interfaces with the same name defined by separate loaders can lead to `ServiceConfigurationError`.
- In **JPMS named modules**, service binding relies on `uses` and `provides ... with ...` and may not require traditional classpath descriptors. Do not describe all of JPMS solely with `META-INF/services`.

Illustrative code assuming `PaymentProvider` and `pluginLoader` already exist:

~~~java
ServiceLoader<PaymentProvider> providers =
        ServiceLoader.load(PaymentProvider.class, pluginLoader);

for (PaymentProvider provider : providers) {
    // Use the provider through the shared interface.
}
~~~

This snippet is not a standalone program: it assumes the interface, providers, and loader have already been configured. For the runnable example in Section 4, we use only text resources to focus on the behavior of the listing APIs.

## 10. Notes on JPMS and Resource Encapsulation

On Java 9+, classes and resources can reside in **named modules**. Resource lookup rules differ significantly from JARs on the classpath (unnamed modules).

Some non-class resources in a named module are not returned when the package containing the resource **is not opened unconditionally**, depending on the ClassLoader API being used. In other words, just because a file is inside a module JAR does not mean `loader.getResources(name)` sees that file from every context.

When in doubt:

1. Verify that the resource is in the actual JAR/module used at runtime.
2. Verify the module and package containing the resource, and any `opens` or `open module` declarations if needed.
3. Check which loader was queried and how the framework constructs `ModuleLayer`.
4. Check whether the wrong `ClassLoader` path was used compared to `Class.getResource`.
5. Do not indiscriminately add `--add-opens` just to mask configuration errors; understand why the module is restricting access.

The example in Section 4 **does not use named modules**, so the resource lookup results do not depend on module declarations.

## 11. Safe Practices When Listing Multiple Resources

### 11.1. Properly Closing Content Streams

The `InputStream` returned by `URL.openStream()` or `getResourceAsStream` must be closed; use `try-with-resources`. With multiple URLs, opening and closing them **sequentially** is generally preferable to opening all streams at once.

Avoid keeping streams/JAR handles open for long when a plugin needs to be replaced. `URLClassLoader.close()` closes the loader's JAR handles, but does not turn every `InputStream` still in use into an object with an automatically managed lifecycle.

### 11.2. An I/O Error Is Not “Not Found”

Distinguish between:

- `getResource(name) == null`: the loader could not find a URL according to its lookup mechanism.
- `getResources(name)` returns an empty Enumeration: there are no matching resources that the loader can list.
- `IOException` during enumeration or reading a URL: the access operation failed, not necessarily that the resource does not exist.
- `UncheckedIOException` during Stream processing: a wrapped I/O error when working through the Java Stream API.

Do not write `catch (IOException e) { return Collections.emptyList(); }` if I/O errors need to be reported; doing so silently turns “read failed” into “no resource”.

### 11.3. Deduplication Must Fit the Requirements

If the list contains repeated identical URLs, `distinct()` on the URL Stream or a `Set<URL>` can be useful in specific cases, but URL equality/normalization has subtle complexities; in some environments, comparing URLs can cause unintended behavior. When safe deduplication is required, choose an explicit key such as plugin name + relative resource path or a URI normalized according to a controlled policy.

If two **different** JARs both provide a resource name with different contents, dropping entries merely because the name matches usually loses data that needs to be processed.

## 12. Common Pitfalls

| Symptom | Why It Happens | How to Handle It |
|---|---|---|
| `getResource` only returns PARENT even though A/B have the same resource | Parent-first and only returns the first URL | Use `getResources`/`resources` if you need all of them |
| `getResources` does not see the plugin's file | Using a system/host loader that does not see the plugin's URLs | Pass the appropriate plugin loader |
| `ClassLoader.getResource("/a/b.txt")` returns null | The name has a leading slash added | Use `"a/b.txt"` |
| `Class.getResource("x.txt")` does not search from the root properly | The name is relative to the class's package | Use `"/x.txt"` if you truly want lookup from the root and the right loader |
| Only one `META-INF/services` file is processed | `getResource` only returns one result | Use `ServiceLoader` or enumerate descriptors properly |
| `Stream has already been operated upon or closed` | The `resources` Stream has already been consumed once | Create a new Stream when you need to iterate again |
| Results from multiple JARs appear mixed in an unexpected order | Parent, URL order, wildcard, framework loader | Print the URL list and inspect the loader configuration and search path |
| `IOException` when opening a resource | The JAR/URL is unreadable or the stream failed | Report the real error and close resources properly |
| File is inside a named module but is not visible | Module encapsulation; the package is not opened appropriately | Check module ownership and `opens` |
| Closing the loader causes subsequent resource read failures | Resource lookup or stream is used after the loader closes | Complete processing within the loader's active lifecycle |

## 13. Self-Check

**Question 1.** If the parent has a `settings.txt` and two child JARs also have files with the same name, what do `getResource` and `getResources` typically return?

**Answer:** `getResource` returns the parent's first URL, while `getResources` can enumerate both the parent and the two child resources, following the parent-first order of a standard loader.

**Question 2.** Does `resources(name)` return a Stream of text lines in the file?

**Answer:** No. It is a `Stream<URL>`. To read text, you must open the corresponding URL and process the input stream.

**Question 3.** Can `getResources(name)` be used as an API to list all entries in a JAR?

**Answer:** No. It finds resources with a **specific name** that the ClassLoader sees. If you need to list all entries, use `JarFile` or the ZIP API.

**Question 4.** Why can a framework using `ServiceLoader` find multiple providers even though the JARs all contain `META-INF/services/<service>`?

**Answer:** Multiple descriptors with the same name can be found through the loader; `ServiceLoader` has rules for reading and processing providers from those descriptors.

**Question 5.** Why can't `ResourceDemo.class.getResource("/demo/resource/lesson-source.txt")` in the host replace `child.getResources("demo/resource/lesson-source.txt")`?

**Answer:** `Class.getResource` uses the loader/module attached to the host class and does not automatically see resources managed separately by the child loader.

**Question 6.** Does closing the Java Stream returned by `resources` automatically close the `InputStream` instances that code opens afterward during processing?

**Answer:** You should not assume so. Each input stream opened by the application must have its own closing mechanism, typically `try-with-resources` in the reading function.

## 14. Official Documentation

- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `getResource`, `getResourceAsStream`, `getResources`, and `resources`.
- [Java SE 17 — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): URL search path and loader lifecycle.
- [Java SE 17 — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): provider configuration, discovering multiple providers.
- [Java SE 17 — Class.getResource](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getResource(java.lang.String)): relative/absolute paths based on the class.
- [Java SE 17 — Java Platform Module System](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): module scope and resource access permissions.

**Remember:** `getResource` finds the first single URL; `getResources` provides an `Enumeration<URL>` of multiple resources with the same name; `resources` provides a `Stream<URL>` (Java 9+). Results depend on the specific loader, parent delegation, the URL path, and in named modules there are also module rules. Listing URLs does not automatically read or merge contents — the application itself must decide how to process them and close streams properly.
