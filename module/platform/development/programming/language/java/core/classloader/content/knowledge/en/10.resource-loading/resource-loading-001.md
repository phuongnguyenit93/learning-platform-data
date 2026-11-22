# What Is a Resource and How Does It Relate to the Classpath in Java

## 1. What Is a Resource?

In Java, a **resource** is data that a program wants to read by a **resource name**, without depending directly on whether the data resides in a directory on disk or inside a JAR file. Resources are typically data bundled alongside an application or library:

- Default configuration files: `config/app.properties`, `logback.xml`, `META-INF/services/...`.
- Text templates, HTML pages, SQL statements, translations: `templates/email.html`, `sql/schema.sql`, `messages_vi.properties`.
- Images, icons, public certificates, test data, JSON files, or binary data.
- Even `.class` files can be looked up as resources, although **finding resource bytes** and **defining a Java type** are two different operations.

For example, an application wants to read `demo/config/message.txt`. When running in a development environment, the bytes might reside at `resources/demo/config/message.txt`. When packaged, they might reside **inside a JAR** with the entry name `demo/config/message.txt`. Java code using the appropriate resource name can read both cases without making assumptions about physical file paths.

**Key point:** The *classpath* provides the **search roots** for both classes and resources in traditional classpath-based execution. A *resource name* is a path **relative to that root**, typically separated by `/`. A resource **does not need to be a Java class**, has no constructor, and does not automatically become a `Class<?>` object just because it appears on the classpath.

This article accurately explains resource names, classpath structure, Java resource-lookup APIs, differences between `Class` and `ClassLoader`, running in an IDE/JAR, handling missing resources, multiple resources with the same name, and notes on JPMS since Java 9.

## 2. What Is the Classpath?

The **classpath** is the set of locations that Java tools can use to find classes and resources in classpath-based execution. When passing `-cp` or `--class-path` to the `java` command, you specify components such as:

- **Root directories** containing package directories and compiled files.
- **JAR files** containing class files and resource entries.
- Multiple directories/JARs listed using the separator syntax appropriate for the operating system.

Example on Windows:

~~~powershell
java -cp "out;resources;lib/util.jar" demo.Main
~~~

Conceptual equivalent on Linux/macOS:

~~~bash
java -cp "out:resources:lib/util.jar" demo.Main
~~~

The classpath separator is `;` on Windows and `:` on Linux/macOS. The `/` **inside a resource name** follows a different rule: `demo/config/message.txt` has the same logical name across operating systems.

When `resources` is a **classpath root**, the resource `demo/config/message.txt` corresponds to:

~~~text
resources/
└── demo/
    └── config/
        └── message.txt
~~~

When `out` is a classpath root, a class with binary name `demo.Main` corresponds to:

~~~text
out/
└── demo/
    └── Main.class
~~~

**Do not pass an entire resource file path as if it were a classpath root.** If you pass `resources/demo/config/message.txt` to `-cp` instead of the `resources` directory, the standard lookup mechanism will not treat it as an entry providing the exact resource name `demo/config/message.txt`.

The classpath used at **compile time** and at **runtime** can be different. `javac -cp` helps the compiler resolve required types; `java -cp` determines the search path when launching at runtime. A program that compiles successfully can still fail to read resources if the runtime packaging omits the resource directory or JAR.

## 3. Relationship Between Classes and Resources on the Classpath

A class and any resource can both be provided from the same directory/JAR:

~~~text
project/
├── src/
│   └── demo/
│       └── Main.java
├── resources/
│   ├── app.properties
│   └── demo/
│       └── config/
│           └── message.txt
└── out/
    └── demo/
        └── Main.class
~~~

If run with both `out` and `resources` on the classpath:

- `demo.Main` is the **binary name of the class**; the JVM/class loader searches for the appropriate class representation, for example the `demo/Main.class` entry.
- `demo/config/message.txt` is a **resource name**, pointing to arbitrary bytes that do not require Java syntax.
- `app.properties` is a resource placed **at the classpath root**, not belonging to package `demo`.
- `Main.class` can be viewed as resource bytes under the name `demo/Main.class`, but reading the stream is not equivalent to `ClassLoader.defineClass` and does not cause the code inside the class to run.

From Java's side, the programmer usually does not need to know whether a resource resides in a `file:` URL or a `jar:` URL. A resource may live inside a JAR, in a runtime module, or be supplied by a custom loader via another mechanism.

**Do not think of the classpath as a single filesystem path string.** It is a multi-location lookup mechanism, and separate class loaders can also have different search scopes. In Java 9+, named modules also have their own resource rules, which are covered in a later section.

## 4. How Resource Names Differ from Filesystem Paths

A resource name has the following characteristics:

- Uses **the `/` character** to separate components, such as `demo/config/message.txt`.
- Is typically interpreted **relative to the classpath root or the class loader's search scope**.
- Can be case-sensitive depending on the packaging source and environment; you should write the exact name and not rely on filesystem leniency.
- Must not be assumed to be an absolute path to a file on disk.
- Does not automatically use `user.dir` as its base when the API called is `ClassLoader.getResource`.

Comparing three different access approaches:

| Expression | Meaning |
| --- | --- |
| `Path.of("config/app.properties")` | File path relative to the process's working directory |
| `ClassLoader.getSystemResource("config/app.properties")` | Resource name relative to the system class loader |
| `MyClass.class.getResource("config/app.properties")` | Resource **relative to the package of MyClass** according to `Class` rules |

All three can read the same bytes if you intentionally arrange the directories appropriately, but **there is no contract that they point to the same location**.

For example, suppose the working directory is `C:\work\project`, while the resource resides inside `app.jar`. `Path.of("config/app.properties")` will look up a file on disk relative to the working directory; it **does not automatically look inside the JAR** to read the `config/app.properties` entry. Conversely, `ClassLoader.getResourceAsStream` can read the entry inside the JAR if the JAR is within the resource search scope.

## 5. Three Important APIs: URL, InputStream, and Listing

Commonly used methods:

| API | Returns | When to Use |
| --- | --- | --- |
| `ClassLoader.getResource(String)` | `URL` or `null` | When you need the logical address of a resource, or to open a stream from the URL |
| `ClassLoader.getResourceAsStream(String)` | `InputStream` or `null` | When you want to read bytes directly, including when the resource is in a JAR |
| `ClassLoader.getResources(String)` | `Enumeration<URL>` | When you want to find **all** visible resources with matching names |
| `ClassLoader.resources(String)` | `Stream<URL>` | Java 9+ API to stream multiple resources |
| `ClassLoader.getSystemResource(String)` | `URL` or `null` | Lookup via the **system class loader** |
| `Class.getResource(String)` | `URL` or `null` | Lookup relative to a reference class; supports package-relative names |
| `Class.getResourceAsStream(String)` | `InputStream` or `null` | Read bytes relative to a reference class, supporting package rules |

A `URL` indicates the location or reachability of a resource; it is not guaranteed to be a local file. An `InputStream` provides bytes and should be closed using `try-with-resources`. When `getResourceAsStream` returns `null`, the cause may be that the resource was not found, access permissions/resource encapsulation, or incorrect packaging.

**Prefer opening a stream to read content**, rather than trying to convert every URL into a `File`. For `jar:file:...!/entry`, converting via `Path.of(url.toURI())` on the default filesystem generally does not work the same way as with `file:` URLs.

## 6. Naming Rules: Class.getResource and ClassLoader.getResource

This is the most error-prone part.

Suppose the executing class has package `demo`:

~~~java
package demo;

public class Reader {
}
~~~

And the resource file is placed at the logical location:

~~~text
classpath root/
└── demo/
    └── config/
        └── message.txt
~~~

The corresponding calls:

| Call | Logical Resource Name After Applying Rules | Expected Result |
| --- | --- | --- |
| `Reader.class.getResource("config/message.txt")` | `demo/config/message.txt` | Found |
| `Reader.class.getResource("/demo/config/message.txt")` | `demo/config/message.txt` | Found |
| `Reader.class.getResource("message.txt")` | `demo/message.txt` | Not found if the resource is only under `demo/config/` |
| `Reader.class.getClassLoader().getResource("demo/config/message.txt")` | `demo/config/message.txt` | Found |
| `Reader.class.getClassLoader().getResource("config/message.txt")` | `config/message.txt` | Not found in this layout |
| `ClassLoader.getSystemResource("demo/config/message.txt")` | `demo/config/message.txt` | Found in standard execution if properly on the system classpath |

**Key differences:**

- `Class.getResource("relative/name")`: if the name **does not start with `/`**, Java automatically prepends the package of that class (`demo/` in the example).
- `Class.getResource("/absolute/name")`: if the name **starts with `/`**, the `Class` API strips the leading `/` and uses the name **relative to the root**.
- `ClassLoader.getResource("name")`: the name is already treated as relative to **the loader's search root**, so normally **no leading `/` is placed**. Passing `"/demo/config/message.txt"` to `ClassLoader.getResource` is not the standard equivalent of calling `Class.getResource("/demo/config/message.txt")`.
- For a `Class` belonging to a **named module**, `Class.getResource` searches within the class's module in addition to the package rules; it cannot be completely reduced to calling the system class loader.

You should choose a consistent lookup style: for resources bundled with a class/library, `MyClass.class.getResourceAsStream(...)` is usually appropriate; for a specific loader, `loader.getResourceAsStream("absolute/from/loader/root")` is appropriate.

## 7. Runnable Java 17+ Example: Using Resources in a Classpath Directory

The goal is to run **the same code** whether resources reside in the `resources` directory or both code and resources are packaged in a JAR. No frameworks or external libraries outside the JDK are used.

### 7.1. Hands-on Project Structure

Create the exact following files:

~~~text
resource-lab/
├── src/
│   └── demo/
│       └── ResourceExample.java
└── resources/
    ├── app.properties
    └── demo/
        └── config/
            └── message.txt
~~~

Contents of **resources/demo/config/message.txt** (single line; a trailing newline at the end of the file is optional):

~~~text
Hello from classpath!
~~~

Contents of **resources/app.properties**:

~~~properties
mode=demo
~~~

### 7.2. Complete Java File

File **src/demo/ResourceExample.java**:

~~~java
package demo;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.net.URL;

public class ResourceExample {
    private static String read(String resourceName) throws IOException {
        try (InputStream input =
                     ResourceExample.class.getResourceAsStream(resourceName)) {
            if (input == null) {
                throw new IOException("Missing resource: " + resourceName);
            }
            return new String(input.readAllBytes(), StandardCharsets.UTF_8).trim();
        }
    }

    public static void main(String[] args) throws IOException {
        ClassLoader loader = ResourceExample.class.getClassLoader();

        URL relative = ResourceExample.class.getResource(
                "config/message.txt");
        URL absolute = ResourceExample.class.getResource(
                "/demo/config/message.txt");
        URL byLoader = loader.getResource(
                "demo/config/message.txt");

        System.out.println("relative: " + (relative != null));
        System.out.println("absolute: " + (absolute != null));
        System.out.println("by loader: " + (byLoader != null));

        System.out.println("message: " +
                read("/demo/config/message.txt"));
        System.out.println("properties: " +
                read("/app.properties"));
    }
}
~~~

The program has `package demo;` and requires the exact file name `ResourceExample.java`. It retrieves three URLs but **does not print the URLs themselves**, because physical addresses vary across machines and between directories and JARs. The `read` method uses `try-with-resources` so the stream is always closed, checks for `null` to clearly report a missing resource, explicitly decodes as UTF-8, and removes leading/trailing whitespace via `trim()` so stdout stays consistent whether or not the file has a trailing newline.

### 7.3. Compiling and Running on Windows (PowerShell)

From the `resource-lab` directory:

~~~powershell
javac --release 17 -d out src/demo/ResourceExample.java
java -cp "out;resources" demo.ResourceExample
~~~

### 7.4. Compiling and Running on Linux/macOS

~~~bash
javac --release 17 -d out src/demo/ResourceExample.java
java -cp "out:resources" demo.ResourceExample
~~~

### 7.5. Exact Stdout

Both commands above, provided the directory tree and resource contents are correct, print:

~~~text
relative: true
absolute: true
by loader: true
message: Hello from classpath!
properties: mode=demo
~~~

**Line-by-line explanation:**

1. `relative: true`: `ResourceExample.class.getResource("config/message.txt")` prepends the `demo/` package prefix, so it searches for `demo/config/message.txt`.
2. `absolute: true`: `Class.getResource("/demo/config/message.txt")` strips the leading slash and searches from the root.
3. `by loader: true`: the loader receives the root-relative name `demo/config/message.txt`.
4. `message: ...`: `getResourceAsStream` reads the bytes of the message file via Class, without requiring a `File` on disk.
5. `properties: ...`: the name `/app.properties` refers to the resource at the root, not `demo/app.properties`.

Thus, a resource is not a Java class; it is text-based data that is likewise located through the classpath mechanism.

## 8. Rerunning the Example from a JAR

In the `resource-lab` directory, after compiling to produce `out/demo/ResourceExample.class`, package both the class and the resources into a JAR using the JDK tool:

~~~bash
jar --create --file resource-example.jar -C out . -C resources .
~~~

The `jar` command takes the contents of the `out` and `resources` directories as entries **relative to the JAR root**. You can verify this with:

~~~bash
jar --list --file resource-example.jar
~~~

The key entries that must be present:

~~~text
demo/ResourceExample.class
demo/config/message.txt
app.properties
~~~

The JAR may also contain a manifest and directory entries; you do not need to match every listing line identically. Run with only the JAR on the classpath:

~~~bash
java -cp resource-example.jar demo.ResourceExample
~~~

**Stdout remains the same as in section 7.5**, because the same resource names still exist at the JAR root:

~~~text
relative: true
absolute: true
by loader: true
message: Hello from classpath!
properties: mode=demo
~~~

The difference lies in the resource address pointed to by the URL: during development it may look like `file:...`, whereas inside a JAR it is typically `jar:file:...!/demo/config/message.txt`. Code that opens an `InputStream` can continue working under both packaging approaches.

**Do not mechanically replace a stream with `new File(...)` or `Path.of(url.toURI())`** just because the example worked on a file URL. For a JAR, a resource entry is not a regular file path on the default filesystem.

## 9. When to Use Properties, Reader, and InputStream?

If the resource is binary data such as PNG or bytecode, read the bytes through an `InputStream`. If it is text, you need to choose the charset explicitly; in Java 17 you can use:

~~~java
try (InputStream input =
             MyClass.class.getResourceAsStream("/data/note.txt")) {
    if (input == null) {
        throw new java.io.FileNotFoundException("data/note.txt");
    }
    String content = new String(
            input.readAllBytes(),
            java.nio.charset.StandardCharsets.UTF_8
    );
}
~~~

**This is an illustrative snippet placed inside a method**, assuming `MyClass` and the resource exist.

For `.properties` resources, you can use `java.util.Properties`:

~~~java
java.util.Properties props = new java.util.Properties();
try (InputStream input =
             MyClass.class.getResourceAsStream("/app.properties")) {
    if (input == null) {
        throw new java.io.FileNotFoundException("app.properties");
    }
    props.load(input);
}
String mode = props.getProperty("mode");
~~~

This is also an illustrative snippet inside a method. Note that `Properties.load(InputStream)` uses the encoding rules of the traditional properties format (ISO-8859-1, Unicode escapes); **it does not automatically decode every UTF-8 file the same way `new String(bytes, UTF_8)` does**. If you intentionally want to use UTF-8 for a properties file, supply a `Reader` with the corresponding charset via `Properties.load(Reader)`.

**Do not write runtime content into resources inside a JAR.** Packaged resources are primarily readable deployment data; configuration that needs to change typically belongs in external files, volumes, environment variables, or a configuration service outside the artifact.

## 10. Parent Delegation and Resource Search Scope

For `ClassLoader.getResource(name)`, the default implementation searches the **parent class loader first**, and then searches the resources provided by the current loader via `findResource`. This mirrors the parent-first idea of class loading, although not every custom loader necessarily uses that exact strategy.

Example:

~~~text
           ParentLoader
            ├── config/app.properties   [parent copy]
            |
            v
           ChildLoader
            └── config/app.properties   [child copy]
~~~

If the child loader uses `getResource("config/app.properties")` under default parent-first delegation, the **parent's** resource may be returned first. When multiple resources share the same name, the result also depends on search path configuration, custom loaders, and named modules.

A plugin application sometimes needs to find the plugin's own resources instead of the host's resources. In that case, you must choose the proper loader/lookup scope: the plugin class's loader, the loader defined by the framework's contract, or the **Thread Context ClassLoader** when a specific API requires it.

Do not assume `ClassLoader.getSystemResource(...)` can find every resource accessible to a plugin or application server. The system class loader and a custom plugin loader can have different search scopes.

## 11. Multiple Resources with the Same Name: getResource vs. getResources

When the classpath contains two JARs with the same `META-INF/services/com.example.Service` entry, calling:

~~~java
ClassLoader loader = Thread.currentThread().getContextClassLoader();

java.net.URL first = loader.getResource(
        "META-INF/services/com.example.Service");
java.util.Enumeration<java.net.URL> all = loader.getResources(
        "META-INF/services/com.example.Service");
~~~

**Illustrative snippet**: an appropriate loader, resource, and environment are required; `getResources` declares `throws IOException`, so the code must be placed in a method that handles this exception.

Meaning:

- `getResource` looks up **one URL**, typically the first resource according to the loader's search policy.
- `getResources` returns multiple URLs visible to the loader. In Java 9+, `loader.resources(name)` provides a `Stream<URL>` with the same idea.
- Multiple JARs providing the same resource name is a valid scenario; it is commonly seen in the Java Service Provider Interface (SPI).
- Do not rely on the **order of URLs** as a business API contract when Java/the JDK does not guarantee a stable order; with named modules, the module lookup order can be especially unpredictable.
- Do not take only the first resource when your task actually requires merging multiple providers or multiple configuration files.

To observe the URLs instead of guessing paths:

~~~java
while (all.hasMoreElements()) {
    System.out.println(all.nextElement());
}
~~~

This is a continuation of the snippet above; URLs may have different schemes and locations across environments, so no fixed stdout is stated.

## 12. Resources and ClassLoader Are Not Synonymous with Loading a Class

Consider two APIs:

~~~java
Class<?> type = loader.loadClass("demo.ResourceExample");
java.net.URL url = loader.getResource("demo/ResourceExample.class");
~~~

**Illustrative snippet**, assuming the `loader` variable is valid and the class/resource names exist.

- `loadClass` is designed to obtain a **runtime Class** from a binary name. The JVM performs the associated loading/linking rules.
- `getResource` is designed to locate **data** by path name; it returns a URL or null.
- Reading bytes from `getResourceAsStream("demo/ResourceExample.class")` does not automatically perform `defineClass`.
- Class loading may use bytes from the classpath/JAR, but how a Class is located/defined is not required to be a simple `getResource` call from Java source.
- A class loaded through a custom loader might not expose its original bytes as a resource URL; conversely, a `.class` resource that is found cannot necessarily be defined into a valid class under an arbitrary name you choose.

In particular, a **class binary name** uses dots between packages, for example `demo.ResourceExample`; the **resource path** of a class file uses slashes and the `.class` extension, for example `demo/ResourceExample.class`. For a member class `Outer.Inner`, the binary name typically contains `$`, and the resource path has the form `pkg/Outer$Inner.class`.

## 13. How Do Resources Differ from External Filesystem Resources?

Choose packaged resources when the data **ships with the application version**: default email templates, icons, SQL migration scripts (depending on the framework), sample data, or sample configuration. Choose the filesystem/database/config service when the data needs to **change without rebuilding the artifact** or requires write access.

| Case | Appropriate Mechanism |
| --- | --- |
| Reading a template packaged in the JAR | `getResourceAsStream` |
| Reading an image bundled with a library | `Class.getResource` or a stream |
| Reading a configuration file placed outside the JAR by an operator | `Path` / `Files` or the framework's configuration API |
| Writing logs, uploads, cache | Filesystem/volume/object storage; do not write to JAR resources |
| Looking up a class by binary name | `ClassLoader.loadClass`; do not treat resource bytes as a Class |
| Reading resources from a separate plugin | The plugin's loader or the mechanism specified by the framework |
| Merging multiple SPI descriptors with the same name | `getResources` or the appropriate `ServiceLoader` API |

A program can use **both**: a default resource inside the JAR as a fallback, then reading an external configuration on disk to override it. You need to define a clear precedence order and not rely on arbitrary ordering of identically named resources.

## 14. Important Differences with JPMS (Java 9+)

Since Java 9, the Java Platform Module System (JPMS) introduced the **named module**. At this point, not all resources are found by simply "scanning the classpath" in the traditional way.

- The traditional classpath places classes into the **unnamed module** corresponding to the loader.
- The module path contains named modules with their own resolution, class loading, and encapsulation mechanisms.
- With `Class.getResource` / `Class.getResourceAsStream`, if the class belongs to a named module, resource lookup is tied to **that class's module**, and access is controlled according to `Module.getResourceAsStream` rules.
- With `ClassLoader.getResource` or `getResourceAsStream`, **a non-.class resource in a package of a named module can typically only be found when that package is opened unconditionally** (an unrestricted `opens p;` declaration without a target), according to the Java 17 Javadoc. This is a stricter constraint than some cases of calling `Class.getResource` from within the module itself or a module granted open access.
- For resources located outside a module package, package encapsulation rules do not apply in the same way. Even so, the packaging/provisioning of the resource must still be correct.
- A resource inside a named module might not be found via APIs using the system class loader even if the entry is visible inside the modular JAR; consider using `MyClass.class.getResourceAsStream(...)` in the appropriate module context.

Example declaration:

~~~java
module com.example.reader {
    // When package demo.assets needs to be opened unconditionally:
    opens demo.assets;
}
~~~

This is a **module descriptor illustration**, not a standalone working file; the actual package and resource must exist. Only add `opens` when the design contract requires it, because opening a package affects reflective/runtime access scope.

**Do not confuse `exports` and `opens`:** `exports` enables access to public types from other modules; `opens` relates to deep reflection and resource encapsulation rules. Merely using `exports` on a package does not necessarily make non-.class resources in it visible via `ClassLoader.getResource`.

## 15. Resources in Gradle, Maven, and IDEs

In a standard Java project, the structure is typically:

~~~text
src/
├── main/
│   ├── java/
│   │   └── demo/
│   │       └── App.java
│   └── resources/
│       ├── app.properties
│       └── demo/
│           └── config/
│               └── message.txt
└── test/
    ├── java/
    └── resources/
        └── test-data.json
~~~

**With the standard Gradle Java plugin** and **Maven convention**, `src/main/resources` is the input directory; the build tool copies resources to the appropriate output so they are present on the runtime classpath or inside the JAR.

- The Gradle Java plugin typically copies resources to `build/resources/main`; compiled classes output usually resides in `build/classes/java/main`. When packaging the JAR, resources are placed into their corresponding entries.
- Maven typically copies resources to `target/classes`, alongside compiled classes from `src/main/java`.
- `src/test/resources` serves the test classpath; it must not be assumed to automatically go into the production JAR.
- IDEs may add resource directories to the classpath automatically; running the `java` command manually requires you to provide the proper path or use the JAR build output. This is why "it works in the IDE but cannot find the resource when running the JAR" happens frequently.

With a Spring Boot executable JAR that has its own packaging structure, resources can still be found by the runtime's class loader under the exact name, even though the internal entry may sit under a layer such as `BOOT-INF/classes/...`. Do not manually convert a resource path into a filesystem path based on a framework's internal JAR layout.

You should inspect the actual artifact with:

~~~bash
jar --list --file application.jar
~~~

This command applies when `application.jar` is the JAR file you are inspecting. Verify the resource name **relative to the runtime environment's search root**, rather than only checking whether the file exists somewhere in the source tree.

## 16. Handling When getResourceAsStream Returns null

A common mistake is:

~~~java
try (InputStream input =
             MyClass.class.getResourceAsStream("settings.json")) {
    String text = new String(input.readAllBytes());
}
~~~

This is **buggy illustrative code**, assuming `MyClass` exists. If the resource is not found, `input == null` and `readAllBytes()` throws a `NullPointerException`; the message does not clearly identify the resource name.

A better handling pattern:

~~~java
String name = "/config/settings.json";
try (InputStream input = MyClass.class.getResourceAsStream(name)) {
    if (input == null) {
        throw new java.io.FileNotFoundException(
                "Classpath resource missing: " + name);
    }
    byte[] bytes = input.readAllBytes();
}
~~~

This is an **illustrative snippet inside a method**. In a real production system, you may need to include the module name, loader, or list of classpath roots for debugging.

If a resource is not found, check in order:

1. **Correct name, casing, and slashes?** For example, `app.properties` differs from `config/app.properties`.
2. **Using Class or ClassLoader?** `Class.getResource("x")` searches relative to the package; `ClassLoader.getResource("x")` searches from the loader root.
3. **Is the classpath root correct?** Are `resources` or `out` actually on the classpath of the running process?
4. **Is the file inside the JAR/output?** Use `jar --list` and check the build output directory.
5. **Running inside a module or separate plugin?** The resource might reside in an unopened module, or another loader might have its own lookup scope.
6. **Are there multiple resources with the same name?** Check `getResources` to see if multiple sources provide the data.
7. **Are you trying to turn a JAR URL into a File?** Read via a stream or an appropriate JAR/ZIP filesystem API.
8. **Do the IDE and runtime use the same configuration?** Compare arguments, working directory, classpath/module path, and output artifact.

If the API requires an `InputStream`, close the stream with `try-with-resources` and handle `IOException`. If you only need to check existence, `getResource` returns a URL or null, though the result may depend on access permissions and module encapsulation.

## 17. Common Misconceptions

| Misconception | Fact |
| --- | --- |
| "A resource is a Java class" | A resource is named data; `.class` is just one kind of file that can be looked up |
| "The classpath is the directory containing source code" | The runtime classpath contains the required **output/JAR roots**; it does not automatically recognize `src/main/java` or `src/main/resources` |
| "A resource name is a full OS path" | The name is typically a path relative to the search root using `/` |
| "`Class.getResource("x")` and `ClassLoader.getResource("x")` are always the same" | The former applies package-relative resolution when there is no leading `/` |
| "You must add `/` to every resource name" | `ClassLoader.getResource` typically uses a root-relative name **without a leading slash** |
| "A found resource is a local file" | It can live in a JAR, runtime module, or another provider |
| "`getResourceAsStream` always returns a stream" | It can return `null` if not found or access is not permitted |
| "One resource name always corresponds to a single URL" | Multiple classpath entries can contain the same name; `getResources` finds multiple |
| "`new File(url.getPath())` is always valid" | False for JAR URLs and resources not residing on a regular filesystem |
| "The system loader can always find plugin resources" | A plugin loader/TCCL has its own scope |
| "`exports` is enough for all non-.class resources in JPMS" | Some resource lookups are subject to `opens` rules, especially via `ClassLoader` |
| "If a file is present in the IDE, it is guaranteed to be in the packaged JAR" | You must inspect the actual build output/artifact |

## 18. Self-Check Exercises

**1. The resource `icons/logo.png` is located at `src/main/resources/icons/logo.png`. When the build tool places its contents at the classpath root, what name should be passed to `loader.getResource`?**  
`icons/logo.png`, without including `src/main/resources`.

**2. A class belongs to package `demo`. What name does `Demo.class.getResource("data.txt")` look up?**  
`demo/data.txt`. To look up from the root, use `Demo.class.getResource("/data.txt")`.

**3. Why can `loader.getResource("/demo/data.txt")` return null?**  
Because the ClassLoader API expects a root-relative name **without a leading slash**. Use `demo/data.txt`.

**4. Why can code running in an IDE read a resource while `java -cp out ...` cannot find it?**  
`resources` may not be on the runtime classpath; the IDE adds the resource directory automatically, whereas the manual command only includes `out`.

**5. Why should you not use `Path.of(url.toURI())` for every resource?**  
A resource URL may use the `jar:`, `jrt:`, or another provider scheme, which is not equivalent to a file on the default filesystem.

**6. Two JARs contain `META-INF/services/...` with the same name. Which API should be used to view all of them?**  
`ClassLoader.getResources(name)` or `ClassLoader.resources(name)` (Java 9+).

**7. Do `ClassLoader.loadClass("demo.Main")` and `getResource("demo/Main.class")` return the same data type?**  
No. One API returns `Class<?>`, while the other returns a `URL` to the resource bytes.

**8. Can a file in a named module be hidden even if it physically exists?**  
Yes. Resource encapsulation and `opens`/module rules affect lookup visibility, especially through the ClassLoader API.

**9. An `app.properties` file must be modified after deployment; should it be written back inside the JAR?**  
No, it should not. Choose configuration outside the artifact or a storage source meant for writable data.

**10. When a resource stream is null, should you automatically fall back to an identically named resource in an arbitrary JAR?**  
No. You need to clarify the loader, module, classpath, and precedence policy, avoiding reliance on an accidentally present resource.

## 19. Official References

- **Java SE 17, `ClassLoader` API** — getResource, getResources, getResourceAsStream, resource names, delegation, and module visibility: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- **Java SE 17, `Class` API** — getResource/getResourceAsStream, package-relative and absolute naming rules: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- **Java SE 17, `Module` API** — module resource encapsulation and getResourceAsStream: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html
- **Java 17, `java` command** — runtime classpath and the -cp option: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- **Java 17, `jar` command** — creating and listing JAR contents: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html
