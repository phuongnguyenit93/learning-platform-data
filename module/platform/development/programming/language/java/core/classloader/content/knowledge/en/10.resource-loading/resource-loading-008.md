# file:, jar:, jrt: and the Limitations of Converting Resource URLs to File in Java

A resource in a Java application does not necessarily reside in a regular operating system file. When using `Class.getResource(...)` or `ClassLoader.getResource(...)`, you receive a `java.net.URL` describing **how to access the resource**, rather than a guarantee that you can call `new File(...)` to operate on it.

Three common URL forms encountered when learning about class loaders and resources on Java 17+ are:

| Scheme | Illustrative Example | Where Is the Resource? |
|---|---|---|
| **`file:`** | `file:/opt/app/classes/demo/config.txt` | File/directory on a filesystem, commonly seen when running from a `classes` directory |
| **`jar:`** | `jar:file:/opt/app/lib/app.jar!/demo/config.txt` | An entry inside a JAR archive |
| **`jrt:`** | `jrt:/java.base/java/lang/String.class` | Runtime image content under the JDK 9+ module system |

**Key principle:** When the goal is only to **read resource data**, prefer `getResourceAsStream(...)` or `URL.openStream()`. Only convert to `Path`/`File` when a file API is genuinely required and you have verified that the URL has an appropriate scheme and filesystem.

## 1. Resource Name Differs from URL, Path, and File

Given the class:

```java
package demo;

public final class App {
}
```

and the deployment structure:

```text
classes/
└── demo/
    ├── App.class
    └── config.txt
```

You can look up the resource in two ways:

```java
URL a = App.class.getResource("config.txt");
URL b = App.class.getClassLoader()
        .getResource("demo/config.txt");
```

Both find the same resource in the example, but the naming rules differ:

- **`Class.getResource("config.txt")`:** a name not starting with `/` is resolved **relative to the class's package** (`demo/config.txt`).
- **`Class.getResource("/demo/config.txt")`:** the leading `/` indicates an absolute resource path from the root of the class's lookup scope, and is stripped before looking up by resource name.
- **`ClassLoader.getResource("demo/config.txt")`:** the resource name always uses an absolute path form within the loader's namespace **without a leading `/`**. Passing `"/demo/config.txt"` to this API typically fails to find the resource in a standard classpath model.

The argument `"demo/config.txt"` is a **resource name**, not a URL or an absolute filesystem path. It uses `/` by Java convention even on Windows.

Different objects serve different needs:

| Object | Representation | Use When |
|---|---|---|
| `String` resource name | `demo/config.txt` | Asking a class loader to locate a resource |
| `URL` | `jar:file:/.../app.jar!/demo/config.txt` | Identifying the location / how to open the resource |
| `URI` | `jar:file:/.../app.jar!/demo/config.txt` | Representing an identifier in URI syntax, without guaranteeing a filesystem |
| `Path` | Path within **a specific `FileSystem`** | Using APIs such as `Files.readString`, `Files.list`, etc. |
| `File` | Object representing a default filesystem pathname | Using legacy APIs that require `java.io.File` |
| `InputStream` | Byte stream from an opened source | Reading content **without needing** a physical file |

A valid `URL` may point to a JAR entry, a JDK module image, or another source. A successful call to `getResource(...)` only indicates that the resource can be located; it **does not prove** that the resource exists as a standalone file on disk.

## 2. The file: Form — When It Can Be Converted to Path

If the program runs with `java -cp classes ...`, a resource in the output directory typically has a URL of the form:

```text
file:/home/user/project/classes/demo/config.txt
```

When the scheme is `file` and the URI matches the current filesystem provider, the recommended conversion approach is:

```java
URL url = App.class.getResource("config.txt");
if (url == null) {
    throw new IllegalStateException("Missing config.txt");
}
if (!"file".equalsIgnoreCase(url.getProtocol())) {
    throw new IllegalStateException("Not a filesystem URL");
}

Path path = Path.of(url.toURI());
String content = Files.readString(path, StandardCharsets.UTF_8);
```

This is an **illustrative snippet** placed inside a method with `App`, `URL`, `Path`, `Files`, and `StandardCharsets` declared/imported and checked exceptions handled. In Java 17, `Path.of(URI)` is the appropriate API when converting a URI to a `Path` via a supporting filesystem provider.

**Why not use `new File(url.getFile())`?**

A file URL can contain percent-encoding:

```text
file:/home/user/My%20Project/classes/demo/config.txt
```

- `url.getPath()` and `url.getFile()` provide URL components; the string may still contain `%20` representing a space.
- `new File(url.getFile())` may interpret `%20` as three literal characters `%`, `2`, `0` in the actual filename, leading to "file not found".
- `url.toURI()` and `Path.of(uri)` use URI/filesystem provider rules to handle the path representation.
- Do not manually replace `"%20"` with spaces or call `URLDecoder.decode(...)` on **the entire URL path**: `URLDecoder` is intended for form/query data following its own rules (such as the `+` sign), not as a function to convert arbitrary URLs into filesystem paths.

On Windows, a file URL may take a form representing a drive letter or a UNC path; do not manually strip `file:`, concatenate `\`, or infer the drive letter from the string. Let the filesystem provider handle it via `URI` and catch the exception if the URL is not supported.

### Limitations Even with file:

- `Path.of(url.toURI())` may fail if the `file:` URI contains an authority/host not supported by the provider in the running environment.
- The file may be deleted or have its permissions changed **after** obtaining the URL; a valid URL does not guarantee that `Files.readString` will always succeed.
- A file URL may point to a **directory**; `Files.readString` applies to content files, which does not mean every path can be read as text.
- For writable resources, do not assume the `classes`/classpath directory is writable or suitable for storing application data. Another deployment may package the resource into a JAR.

## 3. The jar: Form — An Entry in an Archive, Not a Standalone File

When packaging the resource inside `app.jar`, the same resource may be found under the URL:

```text
jar:file:/opt/app/app.jar!/demo/config.txt
```

General syntax of a JAR URL according to `JarURLConnection`:

```text
jar:<url-of-JAR>!/<entry-name>
```

Breaking down the parts:

- `jar:`: the URL protocol indicating a JAR resource.
- `file:/opt/app/app.jar`: the URL of the **containing JAR**; in some cases the inner JAR URL may be a non-local file source.
- `!/`: the separator between the JAR container and the entry.
- `demo/config.txt`: the entry name inside the archive.

**There is no regular filesystem file named `demo/config.txt` next to the JAR**. The entry's bytes reside inside the archive.

Example of proper access:

```java
URL url = App.class.getResource("config.txt");
try (InputStream input = url.openStream()) {
    String text = new String(input.readAllBytes(),
            StandardCharsets.UTF_8);
    System.out.println(text);
}
```

This is an illustrative snippet that requires handling `url == null` and `IOException` in the calling method; for small content with a known encoding, it works for both `file:` and `jar:`. `readAllBytes()` loads the entire content into RAM; for large resources, read sequentially as a stream and enforce an appropriate size limit.

### Why Does new File(jarURL.toURI()) Fail?

`java.io.File` only represents pathnames on the default filesystem; it does not interpret `!/entry` as a file path inside a ZIP. For example:

```java
URL url = App.class.getResource("config.txt");
File file = new File(url.toURI()); // Incorrect for jar: URL
```

When `url` has the `jar` scheme, `new File(URI)` throws `IllegalArgumentException` because this constructor requires a valid URI with the `file` scheme. Converting the `url.getFile()` string to a `File` does not solve this either: it contains archive and entry information, not a normal file path.

**Further caution:** `Path.of(url.toURI())` is not magic that automatically turns every `jar:` URL into a `Path`. With the `jar` scheme, you need the ZIP/JAR filesystem provider and the corresponding filesystem must already be open. If no filesystem exists for the JAR yet or the provider is absent, you may get `FileSystemNotFoundException` or `ProviderNotFoundException`. Therefore, the advice "use `Path.of(url.toURI())` for all resource URLs" is incorrect.

### If You Truly Need JAR Metadata

You can use `JarURLConnection` when you know the URL is `jar:`:

```java
URL url = App.class.getResource("config.txt");
if (url != null && "jar".equals(url.getProtocol())) {
    URLConnection raw = url.openConnection();
    if (raw instanceof JarURLConnection jar) {
        System.out.println(jar.getEntryName());
        System.out.println(jar.getJarFileURL());
    }
}
```

This is an illustrative snippet requiring the imports `java.net.URL`, `java.net.URLConnection`, and `java.net.JarURLConnection`, and may throw `IOException`. `getEntryName()` returns the entry name; `getJarFileURL()` returns the URL of the archive, **not** the entry. `getJarFileURL()` may not use the file scheme in all environments.

`JarURLConnection` provides access to metadata/manifest/`JarEntry`, though you should pay attention to managing connections, caching, resources, and I/O errors. If you only need the content, `openStream()` or `getResourceAsStream` is simpler.

## 4. The jrt: Form — Resources in the Java Runtime Image

Since Java 9, the JDK uses a runtime image based on the module system (JEP 220) instead of a JDK 8-style `rt.jar` file for platform classes. On typical JDK 17+ installations, the resource for `java.lang.String` may have a URL like:

```text
jrt:/java.base/java/lang/String.class
```

This means:

- `jrt:`: the resource protocol/namespace of the Java runtime image.
- `java.base`: the module containing the class.
- `java/lang/String.class`: the resource path within the module.

Example:

```java
URL url = String.class.getResource("String.class");
System.out.println(url.getProtocol()); // jrt on typical JDK 17
```

This snippet is placed in a method that imports `java.net.URL` and handles `url == null` as needed. **Do not write code that requires every Java runtime and custom image to always return the exact same URL string**: how a resource is located depends on the loader, module, and runtime implementation. In hands-on exercises with a standard JDK, `jrt:` is the expected form.

### jrt: Does Not Mean a Physical File

Even though the URL contains `java/lang/String.class`, it is not a regular file located under a `java.base` directory on disk. Therefore:

```java
new File(jrtUrl.toURI()); // Invalid: scheme is not file:
```

is conceptually wrong. Like `jar:`, a `jrt:` URL denotes a special resource source; `java.io.File` cannot arbitrarily represent an entry in the runtime image.

When you only need to read, still use a stream:

```java
URL url = String.class.getResource("String.class");
if (url == null) {
    throw new IllegalStateException("Runtime resource unavailable");
}
try (InputStream input = url.openStream()) {
    byte[] firstBytes = input.readNBytes(4);
    // Read class bytecode from the runtime resource when provided.
}
```

This is an illustrative snippet and will not compile on its own if imports/exception-handling methods are missing. For standard bytecode, the first 4 bytes are typically the magic number `CA FE BA BE`, though reading the resource stream should only be used for illustration, not as a replacement for the reflection API when class metadata is needed.

### JRT FileSystem Differs from File

The JDK may provide the NIO **JRT FileSystem** provider. When this provider is available, you can work with a `Path` belonging to the `jrt:` filesystem:

```java
URI uri = URI.create(
        "jrt:/java.base/java/lang/String.class");

Path path = Path.of(uri);
byte[] bytes = Files.readAllBytes(path);
```

This is an illustrative snippet for a JDK that supports the `jrt:` provider. `path` is a path **on the virtual filesystem of the runtime image**, not a `File` path on the default filesystem. Do not convert it with `path.toFile()` and expect it to succeed; NIO `Path.toFile()` may throw `UnsupportedOperationException` for a filesystem that does not use the default provider.

With a minimal custom runtime or an environment lacking the appropriate provider, `Path.of(jrtUri)` may fail. When only reading a resource of an existing class, the less-coupled approach remains `getResourceAsStream` or `URL.openStream`.

## 5. Java 17+ Experiment: The Same Resource Produces file: or jar:

The example below creates **a single Java program** and one resource file. Run it the first time using the `classes` directory; run it the second time using `app.jar`. The resource content does not change, yet the URL protocol differs because the deployment structure differs.

Create the directory tree:

```text
resource-demo/
├── src/
│   └── demo/
│       └── ResourceSchemesDemo.java
└── classes/
    └── demo/
        └── data/
            └── message.txt
```

Contents of **`src/demo/ResourceSchemesDemo.java`**:

```java
package demo;

import java.io.InputStream;
import java.net.JarURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ResourceSchemesDemo {
    public static void main(String[] args) throws Exception {
        URL resource = ResourceSchemesDemo.class
                .getResource("data/message.txt");
        if (resource == null) {
            throw new IllegalStateException("Missing demo resource");
        }

        URL runtime = String.class.getResource("String.class");
        if (runtime == null) {
            throw new IllegalStateException("Missing runtime class resource");
        }

        System.out.println("Application protocol: "
                + resource.getProtocol());
        System.out.println("Runtime protocol: "
                + runtime.getProtocol());

        try (InputStream stream = resource.openStream()) {
            String message = new String(
                    stream.readAllBytes(), StandardCharsets.UTF_8);
            System.out.println("Message: " + message.trim());
        }

        if ("file".equals(resource.getProtocol())) {
            Path file = Path.of(resource.toURI());
            System.out.println("File exists: "
                    + Files.exists(file));
        } else if ("jar".equals(resource.getProtocol())) {
            JarURLConnection connection =
                    (JarURLConnection) resource.openConnection();
            System.out.println("JAR entry: "
                    + connection.getEntryName());
        }
    }
}
```

On **Bash** (Linux/macOS/Git Bash), inside the `resource-demo` directory, create the file, compile, and run:

```bash
mkdir -p classes/demo/data
printf 'Hello resource!\n' > classes/demo/data/message.txt

javac --release 17 -d classes src/demo/ResourceSchemesDemo.java
java -cp classes demo.ResourceSchemesDemo
```

Output on a standard JDK 17+ when running from the directory:

```text
Application protocol: file
Runtime protocol: jrt
Message: Hello resource!
File exists: true
```

Package and run the program from the JAR:

```bash
jar --create --file app.jar -C classes .
java -cp app.jar demo.ResourceSchemesDemo
```

Output:

```text
Application protocol: jar
Runtime protocol: jrt
Message: Hello resource!
JAR entry: demo/data/message.txt
```

This is an **example verified by compiling with `javac --release 17` and running in both modes** on a JDK with JRT. The `jar --create` command puts both `demo/ResourceSchemesDemo.class` and `demo/data/message.txt` into the archive.

Because `Main-Class` is not declared in the manifest, the test **uses `java -cp app.jar demo.ResourceSchemesDemo`**, not `java -jar app.jar`. `java -jar` is a different mode and requires an entry point in the manifest.

If run in an environment that already has a resource with the same name at a higher-priority location on the classpath, a custom class loader, or special packaging, the URL may differ. Inspect `getProtocol()` rather than hardcoding logic based on the filename.

### Running on PowerShell

For Windows PowerShell, replace the two directory- and file-creation lines with:

```powershell
New-Item -ItemType Directory -Force -Path classes/demo/data | Out-Null
[System.IO.File]::WriteAllText(
    "classes/demo/data/message.txt",
    "Hello resource!" + [Environment]::NewLine,
    [System.Text.UTF8Encoding]::new($false)
)
```

Then run the same `javac`, `java`, and `jar` commands as in the Bash section. The path `classes/demo/data` is understood by Java and the JDK tools on Windows; the Java code always uses `/` in resource names.

## 6. Safety Rule: Read Resources from a Stream, Do Not Assume File

A reusable method for small classpath resources:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class ResourceText {
    private ResourceText() {
    }

    public static String read(String name) throws IOException {
        try (InputStream input =
                ResourceText.class.getResourceAsStream(name)) {
            if (input == null) {
                throw new IOException("Resource not found: " + name);
            }
            return new String(input.readAllBytes(),
                    StandardCharsets.UTF_8);
        }
    }
}
```

This **`ResourceText.java`** file can be compiled with:

```bash
javac --release 17 ResourceText.java
```

It is a utility class **without `main`**, so it is not a standalone program with stdout. A caller can use `ResourceText.read("/demo/data/message.txt")` if that resource is on the classpath/module and accessible under the corresponding rules.

Advantages:

- No need to ask whether the source is `file:` or `jar:`.
- No need to extract the resource to a temporary directory.
- When changing packaging from `classes` to a JAR, the resource-reading code stays unchanged.
- `try-with-resources` ensures the stream is closed once reading finishes.

Limitations:

- `readAllBytes()` is unsuitable for very large or untrusted resources; use buffered/streamed reading and enforce a size limit.
- `getResourceAsStream` returns `null` if not found or access is denied; you must check for it.
- If data needs to be modified, a resource embedded in a JAR should not be used as storage. Choose an external `Path` (config file, data directory, database, etc.) and read/write via `Files`.
- With remote resources or custom loaders, opening the stream may fail with I/O/network errors; appropriate timeout, logging, and input-source protection policies are needed.

A practical rule: **classpath resources are primarily read-only assets of the application** (templates, schemas, images, default configuration). User data or application state should be managed separately from the JAR.

## 7. When a Path Inside a JAR Is Required: ZIP FileSystem

Java NIO supports a filesystem provider for ZIP/JAR through the `jdk.zipfs` module in JDKs that include it. When you need to use `Files` APIs with entries inside a JAR, you can explicitly **open a ZIP filesystem** instead of forcing a resource URL into a `File`.

Illustrative example (archive is a local file):

```java
import java.net.URI;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

public class ZipFsExample {
    public static void main(String[] args) throws Exception {
        Path archive = Path.of("app.jar").toAbsolutePath();
        URI zipUri = URI.create("jar:" + archive.toUri());

        try (FileSystem fs =
                     FileSystems.newFileSystem(zipUri, Map.of())) {
            Path entry = fs.getPath("/demo/data/message.txt");
            System.out.println(Files.readString(entry).trim());
        }
    }
}
```

This is a supplementary example **with `main`**, requiring `app.jar` from the previous experiment, `jdk.zipfs` to be available, and the corresponding entry to exist. Compiling with `javac --release 17 ZipFsExample.java` and running `java ZipFsExample` from the directory containing `app.jar` prints:

```text
Hello resource!
```

Characteristics:

- `FileSystems.newFileSystem` creates/opens a **virtual filesystem** attached to the archive. `entry` is a `Path` **inside the ZIP filesystem**, not an operating system `File`.
- Close the `FileSystem` when done, and pay attention to lifecycle/caching when multiple components use the same archive. Closing the filesystem while other code still uses a `Path` from it can lead to errors.
- It does not automatically support every `jar:` scheme (for example, remote JAR URLs or framework-specific nested JARs). In those cases, dedicated protocols/loaders need to handle them separately.
- Extracting the entry to a temporary file is also an option if a library strictly requires a `File`, but you must manage the lifecycle and permissions of the temporary file and not mistake that location for the original resource source.

When you only need to read a few bytes or parse text/JSON, **a stream is still simpler than ZipFileSystem**.

## 8. What to Do When a Library Requires a File?

Some legacy APIs require a `java.io.File` parameter instead of an `InputStream`. There are three options:

| Need | Implementation Approach |
|---|---|
| Can change the API or pick another overload | Prefer an API accepting `InputStream`, `Reader`, `URL`, or `ByteBuffer` |
| The URL is genuinely a local `file:` | Check the scheme, convert `url.toURI()` → `Path.of(uri)` → `path.toFile()` on the default filesystem |
| The resource is in a JAR/JRT, yet the API only accepts `File` | Create a managed temporary file copy, or switch to a stream-accepting library; do not force special URLs into `File` |

Example of copying to a temporary file:

```java
URL resource = MyApp.class.getResource("/assets/report-template.bin");
if (resource == null) {
    throw new IllegalStateException("Missing template");
}

Path temp = Files.createTempFile("report-template-", ".bin");
try {
    try (InputStream in = resource.openStream()) {
        Files.copy(in, temp,
                java.nio.file.StandardCopyOption.REPLACE_EXISTING);
    }

    legacyApiThatRequiresFile(temp.toFile());
} finally {
    Files.deleteIfExists(temp);
}
```

This is an **illustrative snippet**, not standalone because it requires `MyApp`, `legacyApiThatRequiresFile(...)`, and the appropriate imports. In production:

- If the legacy API retains the file after the method returns, **do not delete it too early**.
- Pay attention to temporary file read permissions, sensitive data, and cleanup even when exceptions occur.
- Do not allow temporary filenames to be predictable or overwritten by untrusted sources.
- For very large resources, consider streaming and enforcing a size limit.
- Using `deleteOnExit()` is not a substitute for long-term temporary file management in server processes.

## 9. Common Exceptions and Errors

| Symptom | Typical Cause | Resolution |
|---|---|---|
| `getResource(...) == null` | Incorrect resource name, wrong `/` prefix, resource not packaged, module access restrictions | Check the name, loader, and actual entry |
| `new File(url.toURI())` throws `IllegalArgumentException` | URL is `jar:` or `jrt:`, not `file:` | Use a stream or an appropriate provider |
| `Path.of(jarUri)` throws `FileSystemNotFoundException` | The JAR filesystem has not been opened for the URI | Open a managed ZIP filesystem or read via a stream |
| File exists, yet `Files.readString` reports not found | Using `new File(url.getFile())` with `%20`/URL encoding, resulting in a wrong path | Use `Path.of(url.toURI())` for `file:` URIs |
| `FileSystemProviderNotFoundException` / `ProviderNotFoundException` | The provider for the required scheme is not present | Check the runtime image/modules/providers; fall back to a stream |
| `UnsupportedOperationException` from `Path.toFile()` | The Path belongs to a virtual filesystem rather than the default filesystem | Use `Files` on Path instead of forcing conversion to File |
| `IOException` during `openStream()` | Resource is unreadable, corrupt archive, remote I/O failure, or permission issue | Handle I/O errors and close the stream; do not assume a missing class |
| Works in IDE, fails when packaged as a JAR | Resource was not copied into the JAR, or code assumes a file on disk | Inspect the archive and replace File reading with a stream |
| `jrt:` inaccessible in a minimal environment | Differences in provider, resources, or runtime image | Use appropriate module/resource APIs and avoid hardcoding filesystem assumptions |

*Note on exception names:* In Java 17, the filesystem provider exception class is named `java.nio.file.ProviderNotFoundException`. Use this exact name in code; the phrase `FileSystemProviderNotFoundException` is sometimes only an informal description, **not the name of a standard exception class**.

## 10. Special Cases in the Java Ecosystem

### Named Modules and Resource Encapsulation

On Java 9+, class loader resource lookup is also governed by **module encapsulation**. With `ClassLoader.getResource`, resources **not ending in `.class`** inside a package of a named module can typically only be returned when the package is unconditionally `opens`, according to the API rules. Therefore, `null` does not always mean the file does not exist.

`Class.getResource` and `Module.getResourceAsStream` also have their own corresponding rules for module resources. When module-internal resources are needed, consider the appropriate API and specified access permissions; do not attempt to work around them by treating a `jrt:` URL as a physical file path.

### Nested JARs and Framework Packaging

An application packaged by a framework may contain nested JARs, such as `BOOT-INF/lib/dependency.jar`. URLs returned by custom class loaders may have a special format or a more complex structure than a standard `jar:file:...!/entry`.

Do not write a manual URL parser like:

```java
String path = url.toString().split("!/")[0];
```

This approach ignores URL encoding, multiple layers, remote sources, and differences between loader implementations. If you only need to read the resource, use `openStream()`. If you need to identify the actual archive, use the official framework/loader API or `JarURLConnection` when the URL uses the standard JAR protocol.

### HTTP, Dynamically Generated Data, and Non-File Resources

Not every loader reads solely from a filesystem. Custom loaders may return `http:`, `https:`, or another protocol. In that case, creating a `File` is meaningless. Nor is there a uniform guarantee on URL protocols across class loader plugins; a resource may be generated in memory or provided via a custom API.

### Distinguishing Class Resources from the Path to the Running JAR

`MyApp.class.getResource("MyApp.class")` typically returns a URL pointing to a **.class entry** or specific .class file, not the filesystem path containing the application. If you want a place to store data next to the running program, do not start by slicing the resource URL string: packaging and class loaders can change. Use external configuration, a controlled working directory, or an official deployment API.

`ProtectionDomain.getCodeSource().getLocation()` sometimes provides the URL of the JAR or source directory from which the code was loaded, though it can be `null` or fail to reflect the deployment semantics you need, especially with the module system or custom loaders. It is not a substitute for explicit configuration of data paths.

## 11. Checklist for Choosing the Right API

When working with a resource, ask yourself:

1. **Do I want to read content or do I need a filesystem path?** If reading, use `getResourceAsStream`/`openStream`.
2. **Is the resource name in the right format?** `Class.getResource` supports package-relative names; `ClassLoader.getResource` requires a name without a leading `/`.
3. **Could the resource be null?** Always check and report a clear error.
4. **What is the actual scheme?** Check `url.getProtocol()` rather than guessing from the IDE or filename.
5. **If it is `file:`**, have you converted `url.toURI()` to `Path` via the corresponding provider instead of manually decoding strings?
6. **If it is `jar:`**, do you truly need a `Path`? A stream may be enough; a ZIP filesystem is only needed when an API must work with entries.
7. **If it is `jrt:`**, do you understand it is a virtual runtime image, not `rt.jar` or a physical file?
8. **If using JPMS**, is the package/resource permitted to be accessed via the API you are calling?
9. **If a File is needed for a legacy library**, have you properly managed the temporary file, security, and cleanup?
10. **Have you tested running both from a directory and from a JAR?** These two configurations commonly expose faulty path assumptions.

## 12. Knowledge Self-Check

**1. Does `getResource("config.txt")` returning a `URL` mean the resource is an actual file on disk?** No. The URL may be `file:`, `jar:`, `jrt:`, or another scheme.

**2. Why should `new File(url.getFile())` not be used directly on a file URL containing spaces?** Because the URL component may contain `%20`, which is not equivalent to a properly decoded filesystem name.

**3. What does the URL `jar:file:/app/app.jar!/demo/config.txt` point to?** The `demo/config.txt` entry **inside** the `app.jar` archive. There is no standalone regular file at that path.

**4. Is `new File(jarUrl.toURI())` valid?** Not for a JAR URI: the `File(URI)` constructor requires an appropriate file URI.

**5. Can `Path.of(jrtUri)` be used on a JDK that supports the `jrt:` provider?** Yes, but it is a `Path` belonging to the virtual JRT filesystem; it cannot by default be converted to `java.io.File`.

**6. Why is reading a resource via a stream better than forcing it into a File?** Streams work across multiple protocols and with both JAR and directory packaging, reducing coupling to the filesystem layout.

**7. Is `ClassLoader.getResource("/demo/config.txt")` the same as `Class.getResource("/demo/config.txt")`?** No. `ClassLoader.getResource` uses resource names without a leading `/`; `Class.getResource` has its own rules for handling a leading `/`.

**8. When a resource is in a named module, does `getResource` returning null definitely mean the resource is missing?** No. It may be due to module encapsulation rules or resource access permissions.

**9. Why does it work in the IDE while the executable JAR fails with FileNotFoundException?** The code may be using `new File(...)`, assuming the resource is deployed as a filesystem file, whereas after packaging it becomes a JAR entry.

**10. If a library strictly requires a File for a JAR-embedded resource, what is the sensible approach?** Prefer an overload accepting a stream if available; otherwise, copy the resource to a temporary file with proper lifecycle and security management.

## 13. Official References

- Java SE 17 API, `ClassLoader.getResource/getResourceAsStream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 API, `Class.getResource/getResourceAsStream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- Java SE 17 API, `JarURLConnection` (`jar:` URL syntax and metadata): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/JarURLConnection.html
- Java SE 17 API, `File(URI)`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/File.html
- Java SE 17 API, `Path.of(URI)`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html
- Java SE 17 API, `FileSystems` and ZIP filesystem provider: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystems.html
- JEP 220, *Modular Run-Time Images* (change from `rt.jar` to runtime image): https://openjdk.org/jeps/220

**Remember:** `file:` can usually be converted to a `Path` on the corresponding filesystem; `jar:` denotes an entry inside an archive; `jrt:` denotes modular runtime image content. **A resource URL is not synonymous with `File`.** When you only need to read content, use a stream so your code continues working when the application switches from a classes directory to a JAR or a Java runtime module.
