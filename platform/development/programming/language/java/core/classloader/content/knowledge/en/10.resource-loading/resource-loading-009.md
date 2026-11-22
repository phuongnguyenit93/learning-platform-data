# Reading Resources in a JAR and Closing InputStream Properly

> **Scope:** Java Core → ClassLoader → Resources. The goal is to read text, configuration, and binary data packaged inside a JAR using the resource API, distinguish between relative and absolute resource names, handle `null` and I/O errors, use `try-with-resources` to close `InputStream`, and avoid relying on physical file paths. Code examples use Java 17+.

## 1. Why is reading a resource in a JAR different from reading a file on disk?

During development, you can place `config.properties` or `message.txt` in a project directory and read it with `Files.readString(Path.of(...))`. However, once built into a JAR:

```text
demo.jar
├── META-INF/
│   └── MANIFEST.MF
└── demo/
    ├── JarResourceDemo.class
    └── message.txt
```

`demo/message.txt` is an **entry inside an archive**, not a standalone file with an OS path like `/home/app/demo/message.txt` or `C:\app\demo\message.txt`. When running `java -cp demo.jar demo.JarResourceDemo`, the JVM/ClassLoader can locate this entry by its resource name and return an `InputStream` to read bytes.

Distinguish between two questions:

1. **Where to find the resource?** This is the responsibility of `Class.getResource...`, `ClassLoader.getResource...`, the module resource API, or a specialized loader mechanism.
2. **How to read the resource and manage its lifecycle?** This is the responsibility of the code using `InputStream`, the charset/decoder, error checking, and **closing the stream**.

The portable approach is **resource name → InputStream → read data → close**. Do not convert a JAR resource into a `File` just to use filesystem APIs if the task is only to read its content.

## 2. Choosing the right API to read an entry in a JAR

When the goal is to **read bytes and close the stream**, start with an API that directly yields an `InputStream`:

| Case | Appropriate API | What to check |
| --- | --- | --- |
| Resource is next to class `MyClass` | `MyClass.class.getResourceAsStream("data.txt")` | Name is resolved relative to the class's package |
| Resource is referenced from the root | `MyClass.class.getResourceAsStream("/demo/data.txt")` | Leading `/` follows `Class` rules |
| A specific loader is chosen | `loader.getResourceAsStream("demo/data.txt")` | No leading `/`; the loader may not see the resource |
| Need to open data from a located URL | `url.openStream()` | Check that the URL is not `null`, handle `IOException` |

Both `Class.getResourceAsStream` and `ClassLoader.getResourceAsStream` can return `null`: a missing resource, a wrong name, a different loader, or module boundaries must all be considered. If you need to **enumerate** multiple copies with the same name, use `loader.getResources(name)` and then open and close the stream from each URL. With a named module, `Module.getResourceAsStream(name)` has its own `opens` policy; do not infer its accessibility from `ClassLoader` results.

Looking up a resource does not mean loading a class or running a static initializer. Inside a JAR, an entry is not a standalone `File` on disk; for tasks that only read content, prefer using streams.

## 3. Paths: relative, absolute, and slashes

Suppose the calling class is `demo.JarResourceDemo` and the resource is at entry `demo/message.txt`.

**With the `Class` API:**

```java
// Look up demo/message.txt: relative name from package "demo"
JarResourceDemo.class.getResourceAsStream("message.txt");

// Look up demo/message.txt: leading "/" is absolute from root
JarResourceDemo.class.getResourceAsStream("/demo/message.txt");

// Look up message.txt directly at the archive/classpath root, NOT demo/message.txt
JarResourceDemo.class.getResourceAsStream("/message.txt");
```

**With the `ClassLoader` API:**

```java
ClassLoader loader = JarResourceDemo.class.getClassLoader();

// Correct: name from resource root
loader.getResourceAsStream("demo/message.txt");

// Do not use a leading "/" with the ClassLoader API
loader.getResourceAsStream("/demo/message.txt");
```

The snippets above must be placed inside code that has the class `demo.JarResourceDemo`, such as a method of that class; they illustrate **lookup rules**, not a standalone Java program.

Reason: when a name does not start with `/`, `Class.getResource...` prepends the package prefix (replacing `.` with `/`). If the name starts with `/`, it strips the `/` before looking it up. By contrast, `ClassLoader.getResource...` takes a name already resolved from the root; **there is no rule to automatically strip a leading `/`** like in the `Class` API.

Summary table:

| Call from `demo.JarResourceDemo` | Actual name looked up |
| --- | --- |
| `getResourceAsStream("message.txt")` | `demo/message.txt` |
| `getResourceAsStream("/demo/message.txt")` | `demo/message.txt` |
| `getResourceAsStream("/message.txt")` | `message.txt` |
| `getClassLoader().getResourceAsStream("demo/message.txt")` | `demo/message.txt` |

In a JAR, entry names use `/` and are usually **case-sensitive**. Do not use `\` as a package separator or manually turn a resource name into a Windows path. Do not include `src/main/resources` in the runtime name if the build tool already copies that directory's contents as the classpath root.

## 4. Standalone lab: packaging, reading, and closing streams

This example is designed to **actually run from a JAR**, not just from an IDE. All you need is JDK 17+ and the `javac`, `jar`, and `java` commands.

### Source structure

```text
src/
  demo/
    JarResourceDemo.java
resources/
  demo/
    message.txt
classes/           (created by javac)
demo.jar           (created by jar)
```

**File `src/demo/JarResourceDemo.java`:**

```java
package demo;

import java.io.FileNotFoundException;
import java.io.IOException;
import java.io.InputStream;
import java.net.URL;
import java.nio.charset.StandardCharsets;

public class JarResourceDemo {
    private static String readText(InputStream input) throws IOException {
        if (input == null) {
            throw new FileNotFoundException("demo/message.txt");
        }

        try (input) {
            return new String(input.readAllBytes(), StandardCharsets.UTF_8)
                    .stripTrailing();
        }
    }

    public static void main(String[] args) throws IOException {
        System.out.println("relative: " + readText(
                JarResourceDemo.class.getResourceAsStream("message.txt")));

        System.out.println("absolute: " + readText(
                JarResourceDemo.class.getResourceAsStream("/demo/message.txt")));

        System.out.println("loader: " + readText(
                JarResourceDemo.class.getClassLoader()
                        .getResourceAsStream("demo/message.txt")));

        URL url = JarResourceDemo.class.getResource("message.txt");
        System.out.println("protocol: " + url.getProtocol());
        System.out.println("missing: "
                + (JarResourceDemo.class.getResourceAsStream("missing.txt")
                        == null));
    }
}
```

**File `resources/demo/message.txt` (UTF-8):**

```text
Hello from inside JAR
```

### Compiling and packaging

From the root directory containing `src` and `resources`:

```bash
javac -d classes src/demo/JarResourceDemo.java
jar --create --file demo.jar -C classes . -C resources .
jar --list --file demo.jar
java -cp demo.jar demo.JarResourceDemo
```

For Windows PowerShell/CMD, this example also works with `/` in JDK tool arguments. If you want to inspect the contents, `jar --list --file demo.jar` will include the entries `demo/JarResourceDemo.class` and `demo/message.txt`; the full listing also includes manifest/directory entries, so do not hardcode the entire `jar` output.

**Stdout of `java -cp demo.jar demo.JarResourceDemo` verified on OpenJDK 21:**

```text
relative: Hello from inside JAR
absolute: Hello from inside JAR
loader: Hello from inside JAR
protocol: jar
missing: true
```

Key takeaways:

- `java -cp demo.jar`: the application loads both classes and resources from the same archive.
- The first three lookup APIs all find the same `demo/message.txt` entry in three different ways.
- `try (input)`, supported in Java 9+ for **effectively final** parameter variables, closes the stream when exiting the block, even if reading throws an `IOException`.
- `input.readAllBytes()` reads the bytes; `new String(..., UTF_8)` decodes the text using an **explicit charset**. It does not depend on the system-default encoding.
- `stripTrailing()` is only used in this example to strip the trailing newline for consistent output; real applications should not automatically strip/trim when trailing whitespace is meaningful data.
- `protocol: jar` shows that the URL returned has the form `jar:...!/demo/message.txt` when running from a JAR. The actual path portion varies across machines.
- `missing: true` demonstrates that when a resource is missing, the API returns `null` instead of throwing `FileNotFoundException` at the lookup step. The `readText` method intentionally throws a clear checked exception when a required resource is missing.

**Why is there no `try-with-resources` in `main`?** Because the `readText` helper **takes ownership** of the stream created by the caller, closes the stream internally, and returns a `String` (it does not return an open stream). This is an intentional design contract; public methods must clearly document who is responsible for closing, avoiding double-closing or leaking streams. Section 5 shows the common pattern where the caller itself opens and closes the resource.

## 5. Preferred pattern: try-with-resources at the point of use

If you do not need a helper to take ownership, write it directly:

```java
import java.io.FileNotFoundException;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

// Inside a Java method that declares throws IOException:
String name = "/demo/message.txt";

try (InputStream in = MyClass.class.getResourceAsStream(name)) {
    if (in == null) {
        throw new FileNotFoundException("Classpath resource: " + name);
    }

    String text = new String(in.readAllBytes(), StandardCharsets.UTF_8);
    System.out.println(text);
}
```

`MyClass` is an illustrative class to be replaced with your actual class; the code above **is not a standalone program**. `try-with-resources` accepts a `null` resource value: if it is `null`, there is no object to close. You still need to check for `null` **before calling `readAllBytes()`**, because otherwise the observed error will be a `NullPointerException` lacking context.

With the class loader access API:

```java
// Inside a method with a reference to Class<?> owner
ClassLoader loader = owner.getClassLoader();
if (loader == null) {
    // owner may be defined by the bootstrap loader;
    // consider ClassLoader.getSystemResourceAsStream(...) or the Class API.
}

try (InputStream in =
             owner.getResourceAsStream("/demo/message.txt")) {
    if (in == null) {
        throw new FileNotFoundException("demo/message.txt");
    }
    // Read data and automatically close the InputStream.
}
```

Here `owner` is assumed to be a `Class<?>` variable passed by the caller; the snippet is not standalone. Do not call `loader.getResourceAsStream(...)` if `loader == null`. **Using `owner.getResourceAsStream`** is usually simpler, especially when you want to tie the lookup to a specific class and avoid guessing a global loader.

### What happens when an exception occurs?

`try-with-resources`:

1. Acquires the stream to be used.
2. Executes the `try` body.
3. Calls `close()` **upon exiting the block**, whether the code succeeds or throws an exception.
4. If both the body and `close()` throw exceptions, the error from close is normally recorded as a **suppressed exception** on the primary error.

There is no need to call `close()` manually before every `return` or in both `catch` and `finally`. If you design an API that returns an `InputStream` to the caller, the **caller** must take responsibility for closing it; if you already close it inside the method, you cannot return a closed stream and expect the caller to keep reading.

`IOException` can occur while reading **or** closing. Do not write `catch (IOException ignored) {}` to hide errors when an important configuration file has been truncated or partially read.

## 6. Choosing how to read by data type: text, binary, large or small

### Small text, explicit UTF-8

`InputStream.readAllBytes()` (Java 9+) is suitable for **small resources with known/controlled sizes**.

```java
try (InputStream in =
        MyClass.class.getResourceAsStream("/demo/settings.json")) {
    if (in == null) {
        throw new FileNotFoundException("demo/settings.json");
    }
    String json = new String(in.readAllBytes(), StandardCharsets.UTF_8);
}
```

This is a snippet inside a method with `throws IOException` and an appropriate `MyClass`. It only reads the JSON string and **does not parse/validate JSON**.

### Reading text with a Reader specifying a charset

When you need to read line by line or reduce temporary memory compared to `readAllBytes()`:

```java
try (InputStream in =
             MyClass.class.getResourceAsStream("/demo/words.txt")) {
    if (in == null) {
        throw new FileNotFoundException("demo/words.txt");
    }

    try (var reader = new java.io.BufferedReader(
            new java.io.InputStreamReader(in, StandardCharsets.UTF_8))) {
        for (String line; (line = reader.readLine()) != null; ) {
            System.out.println(line);
        }
    }
}
```

This is not a standalone snippet. `BufferedReader` lets you read line by line; closing the reader also closes the underlying stream. Having two `try-with-resources` layers managing the same stream can cause `close()` to be called twice; standard `InputStream` implementations handle this, but a **cleaner design** is to declare a single reader in `try-with-resources` after verifying the stream is open, or ensure only one owner is responsible for closing. The example below is clearer when a reader is needed:

```java
InputStream raw = MyClass.class.getResourceAsStream("/demo/words.txt");
if (raw == null) {
    throw new FileNotFoundException("demo/words.txt");
}

try (var reader = new java.io.BufferedReader(
        new java.io.InputStreamReader(raw, StandardCharsets.UTF_8))) {
    String line;
    while ((line = reader.readLine()) != null) {
        System.out.println(line);
    }
}
```

`reader.close()` automatically closes `InputStreamReader` and then `raw`. All snippets here require import context or fully qualified names and `IOException` handling.

### Binary data: do not coerce into a String

For images or binary data, keep the bytes intact:

```java
try (InputStream in =
             MyClass.class.getResourceAsStream("/demo/logo.png")) {
    if (in == null) {
        throw new FileNotFoundException("demo/logo.png");
    }
    byte[] image = in.readAllBytes();
    // Pass bytes to an appropriate binary decoder/consumer.
}
```

Do not use `new String(bytes, UTF_8)` as an intermediate step for images: decoding/encoding can corrupt non-text data.

### Large resources: read in chunks

`readAllBytes()` can consume a large amount of memory, especially when the input size is untrusted. For large data, you can use a buffer array, enforce a total byte limit, or use `transferTo(OutputStream)` if it fits the processing pipeline:

```java
try (InputStream in =
             MyClass.class.getResourceAsStream("/demo/large.bin")) {
    if (in == null) {
        throw new FileNotFoundException("demo/large.bin");
    }

    byte[] buffer = new byte[8192];
    long total = 0;
    int count;
    while ((count = in.read(buffer)) != -1) {
        total += count;
        if (total > 50_000_000L) {
            throw new IOException("Resource exceeds permitted limit");
        }
        // Process only buffer[0..count), not the entire 8192 bytes.
    }
}
```

This snippet only illustrates a limit check and stream consumption; for untrusted sources, the workflow also needs to bound the actual total size **before performing expensive work**, rather than only counting after reading. Note that `InputStream.available()` is **not** the file size: the API only returns an estimate of bytes that can be read without blocking and must not be used to allocate an exact array.

## 7. Why should you not force a JAR URL into a java.io.File?

An operation that looks reasonable:

```java
URL url = MyClass.class.getResource("/demo/message.txt");
java.io.File file = new java.io.File(url.toURI());
```

The above is an illustrative snippet, requiring `URISyntaxException` handling and a `url != null` check. It may work when the resource is a direct file in an output directory (`file:` URL scheme) but **typically fails when packaged inside a JAR** (`jar:` URL scheme). `File`/`Path.of(URI)` by default requires a URI with an appropriate filesystem provider; `jar:file:/...!/demo/message.txt` does not automatically become a real file in the default filesystem.

Avoid doing the following:

- Concatenating `System.getProperty("user.dir") + "/src/main/resources/..."` to read a resource in a deployed JAR.
- Forcing every resource `URL` into `new File(...)` and then calling `Files.readString`.
- Catching `FileSystemNotFoundException` and manually converting to a path by splitting on `!`: this is error-prone with encoding, nested JARs, and custom loaders.

Correct approach for **tasks that only read content**:

```java
try (InputStream in = MyClass.class.getResourceAsStream("/demo/message.txt")) {
    if (in == null) {
        throw new FileNotFoundException("demo/message.txt");
    }
    // Process bytes or wrap in a Reader.
}
```

If you need to **iterate over all entries**, verify signatures, or access JAR-specific metadata, then consider `java.util.jar.JarFile`, `java.util.zip.ZipFile`, or the ZIP/JAR FileSystem Provider. Those APIs have different requirements and lifecycles and usually require a **path to an actual archive**, not a mechanical replacement for resource streams.

## 8. When you need to use JarFile directly: close both JarFile and InputStream

If the application receives a path to an actual archive (not just a classpath resource) and needs to read a specific entry, `JarFile` is an appropriate choice.

```java
import java.io.FileNotFoundException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;

// Inside a Java method that declares throws IOException:
try (JarFile jar = new JarFile("demo.jar")) {
    JarEntry entry = jar.getJarEntry("demo/message.txt");
    if (entry == null) {
        throw new FileNotFoundException("demo/message.txt");
    }

    try (InputStream in = jar.getInputStream(entry)) {
        String text = new String(in.readAllBytes(), StandardCharsets.UTF_8);
        System.out.println(text);
    }
}
```

This is a snippet inside a method that handles `IOException`. Meaning:

- `JarFile` **opens the archive and manages archive resources**; closed by the outer `try-with-resources`.
- `jar.getInputStream(entry)` provides a stream to read the entry's bytes; closed by the inner `try-with-resources`.
- `JarEntry.getName()` is the name inside the JAR using `/`, not an absolute OS path.
- `"demo.jar"` here is a **JAR file on disk** relative to the working directory; if you only have a classpath resource from a custom loader without a physical file, you cannot automatically use `JarFile`.

Do not use `JarFile` just to read a configuration file if `Class.getResourceAsStream` already suffices. And never forget to close `JarFile` when iterating over multiple entries, as it can hold onto file descriptors, archive handles, and decompression buffers.

## 9. Multiple resources with the same name and different ClassLoaders

The classpath may contain two JARs that both have the `demo/config.properties` entry. In that case:

- `getResource("demo/config.properties")` normally returns a single URL found according to the loader's search policy.
- `getResourceAsStream(...)` reads from the single resource selected by the lookup mechanism.
- `getResources("demo/config.properties")` can provide multiple URLs; use it when you **intentionally want to aggregate** multiple resources (such as plugin metadata), rather than as a way to "get the latest version."

Example:

```java
import java.io.InputStream;
import java.net.URL;
import java.util.Enumeration;

// Placed inside a method that declares throws IOException:
ClassLoader loader = Thread.currentThread().getContextClassLoader();
if (loader == null) {
    loader = ClassLoader.getSystemClassLoader();
}

Enumeration<URL> all = loader.getResources("demo/config.properties");

while (all.hasMoreElements()) {
    URL url = all.nextElement();
    try (InputStream in = url.openStream()) {
        // Read each configuration copy and merge according to application rules.
    }
}
```

Do not attempt to cast the loader to `URLClassLoader` to query JAR paths; on JDK 9+, the default application loader is not guaranteed to be a `URLClassLoader`. The order among resources depends on the loader, classpath/module search order, and duplicate packages; **do not rely on arbitrary ordering in place of a merge policy**.

**ClassLoader identity matters:** `SomeClass.class.getClassLoader()` refers to the loader that **defined** the class. In containers/plugins, the same resource name can yield different results when querying the system loader, thread context loader, or plugin loader. If a resource "belongs with" a class, you should usually call `ThatClass.class.getResourceAsStream` to avoid guessing which loader sees it.

### Resources in named modules

Since Java 9, resource lookup may be subject to **module encapsulation**. Per the Java SE API, non-`.class` resources located in a package of a named module may **not be visible** through `ClassLoader.getResource...` if the package is not appropriately opened; specifically, the `ClassLoader` API requires an **unconditionally opened package** for many resources in named modules.

`Class.getResourceAsStream` uses the semantics of the module containing the class, and access also depends on the caller/module and `Module.getResourceAsStream` rules. This means `null` **is not enough to conclude that a file is missing**: the file may exist but not be accessible via that API/caller. When packaging named modules, check `module-info.java`, `opens`, and the resource lookup method; do not try to work around it by concatenating OS paths.

## 10. Resource not found: designing clear failure handling

`getResourceAsStream` can return `null` due to:

1. The entry does not exist in the JAR or classpath directory.
2. Wrong package name, missing/extra `/`, or wrong letter casing.
3. The resource was not copied into the output JAR.
4. A different class loader or thread context loader.
5. Named module encapsulation or access restrictions.
6. An error or restriction opening the stream from the URL, depending on the implementation and environment.

**Required resource:** fail fast with a clear resource name, for example:

```java
InputStream raw = MyClass.class.getResourceAsStream("/demo/settings.json");
if (raw == null) {
    throw new IllegalStateException(
            "Required resource missing: /demo/settings.json");
}
try (raw) {
    // parse required data
}
```

This snippet is not standalone. `IllegalStateException` is a design choice for required configuration; you can also choose `FileNotFoundException` in APIs handling `IOException`. Avoid letting a `NullPointerException` occur at the stream-reading line because its diagnostic information is poor.

**Optional resource:** you can return a default configuration or `Optional` after checking for `null`, but you must distinguish **truly missing** from an **I/O error while reading**. You should not automatically turn every `IOException` into "use default value" if corrupted/invalid data needs to be detected.

### Inspecting the packaged JAR

From the directory containing the archive:

```bash
jar --list --file demo.jar
```

Verify the exact entry `demo/message.txt` (or the actual configuration name). If using Maven, the convention is that `src/main/resources/demo/message.txt` is copied to the corresponding classpath/JAR output; with the Gradle Java plugin, `src/main/resources` is also the default resource source. However, check the build configuration because filters or resource exclusions can alter contents or paths.

There is no need to modify `-cp` just to access an entry whose archive is already on the correct classpath: focus on verifying the resource name and loader. Only adjust runtime configuration if the JAR containing the resource is not in the search path of the loader performing the lookup.

## 11. Common stream management mistakes

| Mistake | Risk | Fix |
| --- | --- | --- |
| Calling `getResourceAsStream(...).readAllBytes()` directly | `NullPointerException` if not found. | Store the stream, check for `null`, and include the specific resource name in error handling. |
| Not closing streams from `getResourceAsStream` or `URL.openStream` | Resource, file handle, or network handle leaks depending on the source. | Wrap the stream in `try-with-resources`. |
| Returning an `InputStream` already closed inside a helper | Caller cannot read the stream properly. | Establish ownership: caller closes if the API returns a stream; helper closes if it returns bytes/text. |
| Using `File` for a `jar:` URL | Fails during URI conversion or makes wrong filesystem assumptions. | Read via `InputStream`; use `JarFile` when genuinely managing a physical archive. |
| Decoding text with the default charset | Vietnamese/UTF-8 content gets corrupted depending on the environment. | Use `StandardCharsets.UTF_8` or the charset specified by the format. |
| Using `new String(imageBytes, UTF_8)` for images | Corrupts binary data. | Keep raw bytes and use an appropriate binary decoder. |
| Using `available()` as the full file size | May read incomplete data or misallocate buffers. | Read until EOF or use a bounded format length. |
| Reading huge resources with `readAllBytes()` | OOM or GC pressure. | Stream in chunks with a byte limit. |
| Using `reader.lines()` and forgetting to close the reader | The underlying stream may keep the resource open. | Place the reader in `try-with-resources`, especially when returning a lazy stream. |
| Forgetting to close `JarFile` or `ZipFile` | Archive handles may lock files from deletion or overwriting. | Wrap the archive object in `try-with-resources`. |
| A utility silently closing a caller-provided stream | Caller is surprised when trying to use it further. | Document ownership clearly or accept `Supplier<InputStream>` with an explicit contract. |
| Swallowing `IOException` during read/close | Data loss or hidden runtime errors. | Log or propagate the error to the caller, handling suppressed exceptions. |

Regarding file handles: even after **closing an `InputStream`**, the URL/ClassLoader implementation may cache and manage the JAR at another level. Closing the stream is the **stream user's responsibility**, though it does not guarantee that all archive caches held by the JVM or custom loader are immediately released. If you create your own `URLClassLoader` for plugins, also manage the lifecycle/`close()` of the loader itself when appropriate.

## 12. Practical safe config-reading API design

A helper used in production code should:

- Accept **`Class<?> owner`** or a specific class loader/Module to explicitly define the search scope.
- Use **clear, standardized** resource names (such as `"/demo/config.properties"` for the `Class` API).
- Check for `null` and throw an exception describing the resource.
- Read using an explicit charset or appropriate data decoder.
- Close the stream in exactly one place according to the ownership contract.
- Avoid leaking absolute URLs/paths in sensitive logs if deployment details should not be exposed.
- Enforce a maximum size limit for resources coming from untrusted sources.

Reusable standalone helper example (place in `ResourceText.java` in the default package if copied as-is):

```java
import java.io.FileNotFoundException;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class ResourceText {
    private ResourceText() {}

    public static String requiredUtf8(Class<?> owner, String absoluteName)
            throws IOException {
        if (!absoluteName.startsWith("/")) {
            throw new IllegalArgumentException(
                    "Expected absolute resource name: " + absoluteName);
        }

        try (InputStream in = owner.getResourceAsStream(absoluteName)) {
            if (in == null) {
                throw new FileNotFoundException(absoluteName);
            }
            return new String(in.readAllBytes(), StandardCharsets.UTF_8);
        }
    }
}
```

This is a **compilable class**; it has no `main` method to run on its own and requires the caller to pass `owner` + `absoluteName`. The helper preserves the resource's whitespace/newlines; it does not `trim` or `strip` configuration content. `owner` must not be `null` per your contract; you can add `Objects.requireNonNull` if inputs come from external callers. For large resources, use a streaming version or byte limit instead of `readAllBytes()`.

Example call inside an application class:

```java
String text = ResourceText.requiredUtf8(
        MyApplication.class, "/demo/config.properties");
```

`MyApplication` is an illustrative class not included in `ResourceText.java`; replace it with your application's class and handle `IOException`. When running in a named module, appropriate resource access permissions as described in Section 9 are still required.

## 13. Self-check questions

1. **Does a resource `demo/message.txt` in a JAR have to exist as a `demo/message.txt` file on disk?** No. It is an archive entry; read it using a resource stream.
2. **From class `demo.Example`, how does `getResourceAsStream("message.txt")` differ from `getResourceAsStream("/message.txt")`?** The first looks up `demo/message.txt`, while the second looks up `message.txt` at the root.
3. **Is `ClassLoader.getResourceAsStream("/demo/message.txt")` a standard name?** No; the `ClassLoader` API takes a resource name from the root **without a leading `/`**. Pass `"demo/message.txt"`.
4. **What can a `null` return value from the API mean?** A missing resource, wrong name/loader, encapsulation/access restriction, or inability to obtain a stream per implementation behavior; do not automatically assume the file does not exist.
5. **For reading inside a JAR, should you choose `File` or `getResourceAsStream`?** Read content with a resource stream; `File` is only appropriate when you genuinely have a filesystem path and an API requires it.
6. **Why is `try-with-resources` necessary?** It closes the stream automatically on both success and exception paths, preventing handle leaks.
7. **Who closes the stream returned by a helper?** It depends on the API contract. If it returns an open `InputStream`, the caller must close it; if the helper reads and returns `String`/`byte[]`, the helper should close the stream before returning.
8. **Is `readAllBytes` always suitable for every resource?** No, only for data of reasonable/controlled size; large resources require streaming and limits.
9. **If a resource with the same name exists in two JARs, does `getResourceAsStream` read both?** No; it opens one located resource. Use `getResources` when you genuinely want to enumerate multiple copies.
10. **Why does `JarFile` have two levels of resources to close?** Because there is the archive handle and the stream for each entry; `try-with-resources` manages both.
11. **Does closing the stream mean the JAR file is unloaded from the JVM?** No. Class loaders and URL caching have their own lifecycles; closing the stream only fulfills the caller's obligation to close the stream it owns.
12. **In a named module, does not finding a resource always mean the build omitted the file?** No. There are also encapsulation/`opens` constraints and lookup API rules.

## 14. Official references

- [Java SE 21 — `Class.getResourceAsStream`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#getResourceAsStream(java.lang.String)): relative/absolute names by package, resources in named modules.
- [Java SE 21 — `ClassLoader` resource APIs](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): `getResource`, `getResourceAsStream`, `getResources`, and search order.
- [Java SE 21 — `Module.getResourceAsStream`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html#getResourceAsStream(java.lang.String)): encapsulation and module resource lookup.
- [Java SE 21 — `InputStream`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/InputStream.html): `readAllBytes`, `transferTo`, `available`, and `close`.
- [Java SE 21 — `AutoCloseable`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/AutoCloseable.html): lifecycle of `try-with-resources`.
- [Java SE 21 — `JarFile`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/jar/JarFile.html): reading entries and closing archives.
- [Java SE 21 — `jar` tool](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jar.html): packaging classes and resources from directories.
- [The Java Language Specification, `14.20.3 — try-with-resources`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20.3): close semantics and suppressed exceptions.
