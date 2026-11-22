# getResourceAsStream and Handling Resource-Not-Found Cases in Java

**`getResourceAsStream`** is an API for reading a **resource** packaged with a Java application or visible through a class loader's lookup mechanism: configuration files, text templates, JSON data, certificates, icons, etc. It returns an **`InputStream` if found**, or **`null` if not found** — rather than automatically throwing `FileNotFoundException` for a missing resource.

This makes errors such as `NullPointerException` when creating an `InputStreamReader`, applications that run in the IDE but break after JAR packaging, or "the file is in the project yet the JVM still cannot find it" very common. The solution is to distinguish the **resource path**, the **loader used**, **where the resource actually resides on the runtime classpath/module path**, the **policy for handling missing resources**, and **closing streams properly**.

This article uses **JDK 17+**. Complete programs use `javac`/`java`; resource-packaging examples demonstrate both Windows PowerShell and Linux/macOS, since file-copy operations differ by operating system.

## 1. Before Handling `null`, Determine the Lookup Location

A resource name such as `config/app.properties` is a data name within the search scope of a class loader or module, not a file path relative to the current working directory. At runtime, that same name can point to a file in an output directory, an entry in a JAR, or a resource provided by a custom loader.

When `getResourceAsStream(name)` returns `null`, distinguish three questions:

1. **Is the name right?** With `ClassLoader`, the name is resolved from the resource root; with `Class`, it can be relative to the package.
2. **Does the source contain the resource?** You need to check the output/JAR of the artifact actually being run, not just the file in `src/main/resources`.
3. **Does the context allow finding it?** The chosen loader and module encapsulation can make an existing file invisible.

`ClassLoader.loadClass` loads class definitions, whereas `getResourceAsStream` only locates/opens data. Do not replace resource lookup with `Path.of(name)` or coerce a `jar:` URL into a `File`: both approaches bypass how JARs and modules organize data.

## 2. Two API Families with the Same Name but Different Path Rules

Distinguish:

```java
ClassLoader loader = Example.class.getClassLoader();
InputStream a = loader.getResourceAsStream("config/app.properties");
InputStream b = Example.class.getResourceAsStream("/config/app.properties");
InputStream c = Example.class.getResourceAsStream("local.txt");
```

This is an **illustrative snippet**; it requires importing `java.io.InputStream` and a real `Example` class. The two ways of obtaining resources have their own name-interpretation policies:

### `ClassLoader.getResourceAsStream(String name)`

- The name is a **resource name from the root of the loader's namespace**; for example, `"config/app.properties"`.
- Use `/` to separate parts of the resource name, even when running on Windows.
- **Do not add a leading `/`**. `loader.getResourceAsStream("/config/app.properties")` usually fails to find a resource at `config/app.properties`, because the loader does not perform the leading-slash stripping step that `Class.getResource...` does.
- The output directory or JARs visible to the loader determine whether that resource exists.
- `getResourceAsStream` typically relies on `getResource` and then opens the stream; if there is no URL or it cannot be opened, the result can be `null`. Do not assume `null` has only a single cause, such as a wrong name.

### `Class.getResourceAsStream(String name)`

- If `name` **starts with `/`**, it searches from the **namespace root**: `SomeClass.class.getResourceAsStream("/config/app.properties")`.
- If `name` **does not start with `/`**, the name is interpreted **relative to the class's package**: for `demo.Example`, `Example.class.getResourceAsStream("local.txt")` looks up the corresponding resource `demo/local.txt`.
- This approach is convenient for resources located right next to the class, but it is also easy to get wrong when the author assumes `"config/app.properties"` is always a path from the classpath root.

### Conversion Table

Suppose `demo.Example` is in package `demo` and the runtime has two resources `config/app.properties` and `demo/local.txt`:

| Call | Resource name looked up | Expected result |
| --- | --- | --- |
| `loader.getResourceAsStream("config/app.properties")` | `config/app.properties` | Found |
| `loader.getResourceAsStream("/config/app.properties")` | `/config/app.properties` | Usually not found |
| `Example.class.getResourceAsStream("/config/app.properties")` | `config/app.properties` | Found |
| `Example.class.getResourceAsStream("local.txt")` | `demo/local.txt` | Found |
| `Example.class.getResourceAsStream("/demo/local.txt")` | `demo/local.txt` | Found |
| `Example.class.getResourceAsStream("config/app.properties")` | `demo/config/app.properties` | Not found if the resource is only at the root |

On Java 9+, named modules have **encapsulation** rules for resources. Therefore, the table above represents the typical lookup model for classpath/unnamed-module resources; for named modules, access permissions and how the resource is packaged must also be considered.

## 3. Not Found Returns `null`: Must Check Before Reading

A very common mistake:

```java
InputStream input =
        Example.class.getClassLoader()
                .getResourceAsStream("config/missing.properties");
Properties props = new Properties();
props.load(input); // input == null: fails due to using null
```

The snippet above is **bug-demonstration code**, not a practice to follow. If the resource cannot be found, `getResourceAsStream` returns `null`. When passing `null` to `Properties.load` or `new InputStreamReader(input)`, the application can throw a `NullPointerException`, leaving anyone reading the logs unclear about which resource was missing.

Better yet is to **decide on a policy** before reading:

- **Required resource:** report an error with enough **resource name and loader/module context** for debugging. You can throw `FileNotFoundException` or `IllegalStateException` depending on the API boundary.
- **Optional resource:** use a documented default value; do not act as if the resource existed.
- **Plugin-provided resource:** if the loader cannot see it, check plugin dependency/packaging rather than silently reading the wrong copy from another loader.
- **Resource with sensitive content:** the error can log the controlled resource name, but avoid printing secrets or URLs containing credentials to the logs.

A required-resource pattern that does not hide the cause:

```java
static InputStream openRequired(ClassLoader loader, String name)
        throws java.io.FileNotFoundException {
    InputStream stream = loader.getResourceAsStream(name);
    if (stream == null) {
        throw new java.io.FileNotFoundException(
                "Classpath resource not found: " + name);
    }
    return stream;
}
```

This is an **illustrative method**; call it from a concrete class and place the result in `try-with-resources`. Do not pass `loader == null` to the pattern above; for bootstrap classes or other modules, choose the appropriate lookup API instead of assuming a loader object is always present.

### `FileNotFoundException` Is Thrown by Our Code, Not by `getResourceAsStream`

If the resource is missing, `getResourceAsStream` returns `null`. In the `openRequired` pattern, the application itself chooses to throw `FileNotFoundException` to express the "required resource" contract. That makes the stack trace clearer, though one must not claim that the JDK method throws this exception directly.

## 4. Practice A — Reading UTF-8 `.properties`, Checking for Null, and Closing the Stream

Create a small project:

```text
resource-lab/
├── src/
│   └── demo/
│       └── ConfigDemo.java
└── resources/
    └── config/
        └── app.properties
```

**`resources/config/app.properties`:**

```properties
app.name=Inventory
timeout.seconds=15
welcome=Chào Java
```

**`src/demo/ConfigDemo.java`:**

```java
package demo;

import java.io.FileNotFoundException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

public final class ConfigDemo {
    public static void main(String[] args) throws Exception {
        String resourceName = "config/app.properties";
        ClassLoader loader = ConfigDemo.class.getClassLoader();

        InputStream input = loader.getResourceAsStream(resourceName);
        if (input == null) {
            throw new FileNotFoundException(
                    "Missing required resource: " + resourceName);
        }

        Properties properties = new Properties();
        try (InputStream stream = input;
             InputStreamReader reader =
                     new InputStreamReader(stream, StandardCharsets.UTF_8)) {
            properties.load(reader);
        }

        System.out.println("name=" +
                properties.getProperty("app.name"));
        System.out.println("timeout=" +
                properties.getProperty("timeout.seconds"));
        System.out.println("welcome=" +
                properties.getProperty("welcome"));
    }
}
```

**Compile** from the `resource-lab` directory:

```sh
javac --release 17 -d out src/demo/ConfigDemo.java
```

The `javac -d out` command only generates `.class` files. We need to **copy the resource into the output directory** so that the runtime namespace has the `config/app.properties` entry.

On **Windows PowerShell**:

```powershell
New-Item -ItemType Directory -Force out\config | Out-Null
Copy-Item resources\config\app.properties out\config\app.properties
java -cp out demo.ConfigDemo
```

On **Linux/macOS**:

```sh
mkdir -p out/config
cp resources/config/app.properties out/config/app.properties
java -cp out demo.ConfigDemo
```

**Stdout of the `java` command, when the file is saved as UTF-8:**

```text
name=Inventory
timeout=15
welcome=Chào Java
```

**Why does the program work correctly?**

1. `ConfigDemo.class.getClassLoader()` returns the loader that sees `out` due to `-cp out`.
2. `"config/app.properties"` is the resource name from the classpath root, corresponding to `out/config/app.properties` after copying.
3. `getResourceAsStream` returns an `InputStream`; we check for `null` before passing it into the Reader.
4. `InputStreamReader(stream, StandardCharsets.UTF_8)` decodes the text bytes with an explicit charset, preserving Vietnamese diacritics.
5. `Properties.load(Reader)` reads each `key=value` pair; `getProperty` returns the value string.
6. `try-with-resources` closes the Reader and stream, even when `Properties.load` throws `IOException`.

**A charset detail worth remembering:** according to the Java API, `Properties.load(InputStream)` interprets bytes as ISO-8859-1 (characters outside that character set must be escaped). To read a **UTF-8 properties file directly**, use `Properties.load(Reader)` with `InputStreamReader(StandardCharsets.UTF_8)` as shown above. Do not arbitrarily replace it with `properties.load(input)` if the file contains Vietnamese diacritics.

**Do not confuse the runtime working directory and the classpath:** the path `resources/config/app.properties` existing in the source tree does not guarantee the loader can see it. The runner uses `-cp out`, so the resource must reside in `out` (or in another JAR/classpath visible to the loader). In Maven/Gradle, resource processing usually copies from `src/main/resources` to the output, whereas this manual example requires an explicit copy step.

## 5. Practice B — Demonstrating How Package-Relative and Classpath-Root Differ

The next exercise uses a class in package `demo` and two resources with the **same filename** located in two different places:

```text
path-lab/
├── src/demo/PathDemo.java
└── resources/
    ├── messages.txt
    └── demo/
        └── messages.txt
```

**`resources/messages.txt`:**

```text
hello-from-root
```

**`resources/demo/messages.txt`:**

```text
hello-from-package
```

**`src/demo/PathDemo.java`:**

```java
package demo;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class PathDemo {
    static String text(InputStream input) throws IOException {
        if (input == null) {
            return "<missing>";
        }
        try (InputStream stream = input) {
            return new String(stream.readAllBytes(),
                    StandardCharsets.UTF_8).trim();
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader loader = PathDemo.class.getClassLoader();

        System.out.println("relative=" +
                text(PathDemo.class.getResourceAsStream("messages.txt")));
        System.out.println("class absolute=" +
                text(PathDemo.class.getResourceAsStream("/messages.txt")));
        System.out.println("loader root=" +
                text(loader.getResourceAsStream("messages.txt")));
        System.out.println("loader leading slash missing=" +
                (loader.getResourceAsStream("/messages.txt") == null));
        System.out.println("missing=" +
                text(PathDemo.class.getResourceAsStream("absent.txt")));
    }
}
```

Compile:

```sh
javac --release 17 -d out src/demo/PathDemo.java
```

**Windows PowerShell** — copy the exact two resources and run:

```powershell
New-Item -ItemType Directory -Force out\demo | Out-Null
Copy-Item resources\messages.txt out\messages.txt
Copy-Item resources\demo\messages.txt out\demo\messages.txt
java -cp out demo.PathDemo
```

**Linux/macOS**:

```sh
mkdir -p out/demo
cp resources/messages.txt out/messages.txt
cp resources/demo/messages.txt out/demo/messages.txt
java -cp out demo.PathDemo
```

**Stdout of the `java` command:**

```text
relative=hello-from-package
class absolute=hello-from-root
loader root=hello-from-root
loader leading slash missing=true
missing=<missing>
```

Observations:

- `PathDemo.class.getResourceAsStream("messages.txt")` uses the package of `PathDemo` → `demo/messages.txt`.
- `PathDemo.class.getResourceAsStream("/messages.txt")` uses the **classpath root** → `messages.txt`.
- `loader.getResourceAsStream("messages.txt")` also uses the name from the **loader namespace root** → `messages.txt`.
- `loader.getResourceAsStream("/messages.txt")` does not apply `Class`'s slash-stripping rule; therefore, it does not find the packaged resource.
- `PathDemo.class.getResourceAsStream("absent.txt")` produces `null`, and the `text` helper turns it into the display string `<missing>`. In a real system, you should distinguish between required and optional resources rather than always swallowing the missing case.

In this learning example, `trim()` only removes trailing whitespace/newlines to make stdout easy to verify. Do not use `trim()` indiscriminately on formats where whitespace is meaningful, such as indented templates, signatures, or configuration files requiring byte-for-byte precision.

## 6. Practice C — Distinguishing Required and Optional Resources

Here is an easy-to-apply API wrapper: **required resources throw an informative error**, whereas **optional resources use an explicitly specified fallback**.

Structure:

```text
missing-lab/
├── src/demo/MissingDemo.java
└── resources/templates/report.txt
```

**`resources/templates/report.txt`:**

```text
Report template
```

**`src/demo/MissingDemo.java`:**

```java
package demo;

import java.io.FileNotFoundException;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class MissingDemo {
    static String required(ClassLoader loader, String name)
            throws IOException {
        InputStream opened = loader.getResourceAsStream(name);
        if (opened == null) {
            throw new FileNotFoundException(
                    "Resource not found: " + name);
        }
        try (InputStream stream = opened) {
            return new String(stream.readAllBytes(),
                    StandardCharsets.UTF_8).trim();
        }
    }

    static String optional(ClassLoader loader, String name,
                           String fallback) throws IOException {
        InputStream opened = loader.getResourceAsStream(name);
        if (opened == null) {
            return fallback;
        }
        try (InputStream stream = opened) {
            return new String(stream.readAllBytes(),
                    StandardCharsets.UTF_8).trim();
        }
    }

    public static void main(String[] args) throws IOException {
        ClassLoader loader = MissingDemo.class.getClassLoader();

        System.out.println("required=" +
                required(loader, "templates/report.txt"));
        try {
            required(loader, "templates/absent.txt");
        } catch (FileNotFoundException e) {
            System.out.println("missing=" + e.getMessage());
        }
        System.out.println("optional=" +
                optional(loader, "templates/absent.txt", "fallback"));
    }
}
```

Compile:

```sh
javac --release 17 -d out src/demo/MissingDemo.java
```

Copy the resource and run on **Windows PowerShell**:

```powershell
New-Item -ItemType Directory -Force out\templates | Out-Null
Copy-Item resources\templates\report.txt out\templates\report.txt
java -cp out demo.MissingDemo
```

On **Linux/macOS**:

```sh
mkdir -p out/templates
cp resources/templates/report.txt out/templates/report.txt
java -cp out demo.MissingDemo
```

**Stdout of the `java` command:**

```text
required=Report template
missing=Resource not found: templates/absent.txt
optional=fallback
```

Contract explanation:

- `required(...)` throws `FileNotFoundException` **only when the lookup returns `null`**. When the resource exists but reading fails, the `IOException` from the stream propagates with the corresponding cause.
- `optional(...)` returns the fallback **only when the resource cannot be found**; it **does not treat an I/O error while reading an existing resource as if the resource did not exist**. This avoids masking corrupted file/JAR errors.
- Both methods use `try-with-resources`, so they close the stream even if reading raises an error.
- The fallback `"fallback"` is an example of a valid option. Do not automatically provide fallbacks for critical configuration such as signing keys, payment endpoints, or required certificates.
- The resource name is part of the error message, helping debugging distinguish between `templates/report.txt` and `templates/absent.txt`.

A real-world application can return `Optional<String>` for an optional resource. However, if you use `Optional`, do not turn every exception into `Optional.empty()`: **missing** and **read failure** are two different states.

## 7. Resources Packaged in a JAR Are Still Read via the Same API

Once you have the `out` directory from example A (including `demo/ConfigDemo.class` and `config/app.properties`), package it:

```sh
jar --create --file resource-demo.jar -C out .
jar --list --file resource-demo.jar
java -cp resource-demo.jar demo.ConfigDemo
```

These commands are included in JDK 17+. In the `jar --list` output, look for **both**:

```text
demo/ConfigDemo.class
config/app.properties
```

The two lines above are **the entries to verify**, not a guarantee that the entire `jar --list` output has only two lines or appears in that exact order.

**Stdout of the `java` command in example A remains:**

```text
name=Inventory
timeout=15
welcome=Chào Java
```

This works because the JVM and `URLClassLoader`/built-in loaders know how to read resources as JAR entries. The application does not need to guess a temporary path to extract them.

Avoid the following approach:

```java
URL url = ConfigDemo.class.getResource("/config/app.properties");
File file = new File(url.getFile());
```

This is an **error-prone pattern** (missing `URL`/`File` imports if copied standalone): it may happen to work when `url` is `file:`, but it is unreliable when the URL is `jar:file:...!/...` or when the file name contains spaces/percent-encoding. For read-only data, **`getResourceAsStream`** eliminates the dependency on URL→filesystem path.

If a library genuinely requires a `Path`, you may have to copy the contents from the stream to a **temporary file** and manage deleting the file, or use the JAR filesystem provider API when appropriate. However, you should not do that just to read a few kilobytes of configuration.

## 8. Classpath, Working Directory, and Build Order

One reason resources work in the IDE but fail when using `java -cp` is **a difference in packaging**:

```text
source layout:                         runtime -cp out:
src/demo/ConfigDemo.java              out/demo/ConfigDemo.class
resources/config/app.properties       out/config/app.properties
```

The `resources/config/app.properties` entry is not automatically copied into `out` by `javac`. When running `java -cp out demo.ConfigDemo`, the loader searches the namespace under `out`. If you forget to copy it, `getResourceAsStream("config/app.properties") == null`.

In projects using Maven or Gradle, a convention directory like `src/main/resources` is typically copied by the build tool into the class output/JAR. This is **build tooling behavior**, not an automatic feature of `ClassLoader`. Always check the runtime artifact:

- Does the classes/output directory have the file at the right relative path?
- Does the JAR contain the resource entry? Check with `jar --list --file app.jar`.
- Does the IDE run configuration have a different classpath from the release build?
- Does the fat/uber JAR artifact merge resources from multiple dependencies according to the right policy?
- Do test resources appear only on the test classpath and not in the application artifact?
- Did the container deployment omit the directory/JAR or replace it with an older version?

The **working directory** affects calls such as `Files.readString(Path.of("config/app.properties"))`; it **does not by itself determine the root of classpath resource lookup**. In the examples, we specify running from the project root so the copy and `jar` commands resolve their paths properly, not because `getResourceAsStream` searches for resources from the working directory.

### Do Not Include `src/main/resources` in the Lookup Path

If the build has copied `src/main/resources/config/app.properties` to `config/app.properties` at the classpath root, the correct call is:

```java
loader.getResourceAsStream("config/app.properties");
```

Not `"src/main/resources/config/app.properties"`, because `src/main/resources` is the **repository location**, not necessarily part of the **resource name in the artifact**.

## 9. `getResourceAsStream`, `getResource`, and `getResources`

The three APIs serve different purposes:

- **`getResourceAsStream(name)`:** when you want to **read the contents** directly. Obtain an `InputStream` and close it after use.
- **`getResource(name)`:** when you want to **know the chosen URL** before opening a stream. Useful for debugging where a resource was found, though the URL may represent a JAR entry or a runtime-specific protocol.
- **`getResources(name)`:** when you want to **list matching resources with the same name** found by the loader through its mechanism. Returns an `Enumeration<URL>`, not an `InputStream`.

Example of a helper method for debugging when you suspect **duplicate resource names across multiple JARs**:

```java
static void printResources(ClassLoader loader, String name)
        throws java.io.IOException {
    java.util.Enumeration<java.net.URL> urls =
            loader.getResources(name);
    while (urls.hasMoreElements()) {
        System.out.println(urls.nextElement());
    }
}
```

This is an **illustrative method** that must be called with an actual loader and resource name; the resulting URLs depend on the environment, so there is no fixed stdout. `getResources` can help diagnose multiple JARs providing `META-INF/services/...`, `config/app.properties`, or metadata with the same name.

**Do not assume that `getResource` must choose "the first JAR listed in the source tree"**. Lookup order depends on the loader graph, classpath/module placement, and implementation. The default `ClassLoader.getResource` normally delegates to the parent before searching itself, but custom loaders can override the resource lookup mechanism. If an application requires explicit precedence, you need to design and test a dedicated policy rather than relying on implicit order.

For resources from multiple modules across different layers, discovery behavior also depends on module access and the specific class loader. Do not use `getResources` as a way to bypass encapsulation.

## 10. Relationship to Parent Delegation and Multiple Class Loaders

**Resource lookup is not the same as class loading**, even though both commonly rely on the loader graph:

```text
HostLoader
  ├── class: api.Plugin
  └── resource: config/defaults.properties
       ▲
       │ parent
  PluginLoader
  ├── class: impl.MyPlugin
  └── resource: plugin/settings.json
```

When the plugin calls:

```java
InputStream stream =
        pluginLoader.getResourceAsStream("config/defaults.properties");
```

the result depends on the **policy of `pluginLoader` and its ancestors**. With a default parent-first loader, the parent's resource may be returned. However, custom plugin loaders may override `getResource` or `getResources`; a loader that uses a child-first class policy does not necessarily use the same order for resources.

### Which Loader Should You Choose?

There are several options:

| Context | Option worth considering | Why |
| --- | --- | --- |
| Resource packaged alongside class `demo.MyComponent` | `MyComponent.class.getResourceAsStream("name.txt")` | Package-relative; ties the lookup to the specific runtime `Class<?>`. |
| Resource at the root of the classpath managed by a loader | `loader.getResourceAsStream("config/x.properties")` | Explicit root, explicit loader. |
| Plugin needs a resource inside the plugin JAR | The loader that defined the plugin class, or `PluginImplementation.class.getResourceAsStream(...)` | Avoids defaulting to the system loader, which cannot see the plugin JAR. |
| Framework locates a provider/resource by thread context | `Thread.currentThread().getContextClassLoader()` when specified by the framework contract | The TCCL may be configured by a container/plugin framework. |
| A class's class loader is `null` | `SomeClass.class.getResourceAsStream(...)` or an appropriate module API/system mechanism | Do not invoke methods on a `null` loader; usually the class is defined by the bootstrap loader. |

### The Resource's Class Loader and the Class-Defining Class Loader Differ

For example, a plugin JAR has a class `impl.Plugin` defined by the plugin loader. If host code tries to call:

```java
HostMain.class.getClassLoader()
        .getResourceAsStream("plugin/settings.json");
```

it may receive `null`, because the host loader cannot see the plugin JAR (typically the plugin loader is the **child** and the host is the **parent**). Conversely, code inside the plugin using `impl.Plugin.class.getResourceAsStream("/plugin/settings.json")` can see its own resource if the lookup is permitted by the plugin's loader/module.

**Do not switch everything to the system loader** when you encounter `null`. You must know which artifact/module owns the resource and **which loader is designed to see it**.

## 11. Thread Context Class Loader (TCCL) Is Not the Default Loader for Every API

Reading the TCCL:

```java
ClassLoader context =
        Thread.currentThread().getContextClassLoader();
```

This is a valid snippet inside a method. In common launchers, the main thread has the system loader as its TCCL; frameworks may change it when executing plugin code.

The following two calls are **not equivalent**:

```java
MyService.class.getResourceAsStream("service.json");
Thread.currentThread().getContextClassLoader()
        .getResourceAsStream("service.json");
```

- The call on the class uses **package-relative** lookup with `MyService` and resolves according to the class/module.
- The call through the TCCL uses a **resource name from the root namespace** of the TCCL and that loader object itself. It does not automatically associate with the `MyService` package.
- The TCCL can be `null` in certain contexts; if a framework allows that, you need an explicit fallback decision. Do not dereference null.
- `ClassLoader.getSystemResourceAsStream(name)` is a static API that uses the **system class loader**, not the TCCL by default.
- The TCCL does not change the parent of other loaders and cannot make a resource absent from the artifact appear on its own.

Framework APIs such as `ServiceLoader` may use the TCCL for discovery, but code calling `SomeClass.class.getResourceAsStream` **does not automatically switch to the TCCL** just because the thread is running in a plugin context.

## 12. Named Modules: Class Found, Yet Resources Can Still Be Hidden

Since Java 9, resource lookup across **named modules** follows **strong encapsulation** rules. The Javadoc for `ClassLoader.getResource`/`getResourceAsStream` states explicitly that resources in packages of a named module may not be visible if that package is **not opened unconditionally** for such lookups (except for specific rules such as resources ending in `.class`). Having `exports` on a package does not mean every resource inside it can be read via a loader from the outside.

Concepts that must be distinguished:

- **Module readability**: can code in module A read module B?
- **Exports**: does the package grant other modules access to public types?
- **Opens**: does the package allow reflection/resource access mechanisms under JPMS rules?
- **Loader visibility**: can the loader locate/look up the resource entry?
- **Resource access**: which API is called, from which module/caller, and is the package opened to that caller?

If code **inside a module** needs to read a resource packaged within that same module, `SomeClass.class.getResourceAsStream(...)` is the natural choice because this API is tied to the class's module. In complex cross-module cases, `Module.getResourceAsStream(name)` has specific access rules; read the Javadoc and test in your actual module configuration.

Example module descriptor:

```java
module com.example.reports {
    exports com.example.reports.api;
    opens com.example.reports.templates;
}
```

This is an **illustrative module-info.java**, not a standalone runnable example. Unconditionally applying `opens` to a package can make resources in that package visible through certain resource-lookup APIs. However, opening a package publicly also affects deep reflection; **do not open packages broadly just to work around a path error**. If a module reads its own resources, use the appropriate API and package/module design.

When you have verified that the resource is in the JAR/module yet `getResourceAsStream` still returns `null`, do not immediately conclude that the loader is wrong; **encapsulation** may be the cause.

## 13. Reading Text, Binary Data, and Managing Charsets

`getResourceAsStream` returns a byte stream. The API does not know whether the resource is UTF-8, ISO-8859-1, PNG, or Protobuf. The caller must decide **how to decode the contents**.

### Small Text

```java
static String readUtf8(java.io.InputStream stream)
        throws java.io.IOException {
    try (java.io.InputStream in = stream) {
        return new String(in.readAllBytes(),
                java.nio.charset.StandardCharsets.UTF_8);
    }
}
```

This method takes a **non-null stream**, reads everything into memory, and closes the stream. It is only suitable for moderately sized resources; do not use `readAllBytes()` for a very large resource or an untrusted source that could stream without bound.

### Large Text

For large documents, read with a buffer or `BufferedReader`:

```java
try (InputStream input = loader.getResourceAsStream(name)) {
    if (input == null) {
        throw new FileNotFoundException(name);
    }
    try (BufferedReader reader = new BufferedReader(
            new InputStreamReader(input, StandardCharsets.UTF_8))) {
        String line;
        while ((line = reader.readLine()) != null) {
            // Process line by line instead of holding everything in RAM.
        }
    }
}
```

This is a **snippet**, assuming `loader` and `name` are declared and `java.io.*`/`java.nio.charset.StandardCharsets` are imported. Note that `try-with-resources` **accepts a null reference** when initializing the resource, yet we still must check before using it; having `try (...)` does not cause a missing resource to create a stream on its own. Closing `BufferedReader` also closes the underlying input stream.

### Binary

For PNG/ZIP/keystore/certificate bytes, **do not** call `new String(bytes, UTF_8)` and write it back to a file if you want to preserve every byte. Copy the stream to the output instead:

```java
try (InputStream input = loader.getResourceAsStream(name)) {
    if (input == null) {
        throw new FileNotFoundException(name);
    }
    try (OutputStream output = Files.newOutputStream(destination)) {
        input.transferTo(output);
    }
}
```

The snippet requires the variables `loader`, `name`, and `destination`, as well as imports `java.io.*`/`java.nio.file.Files`. `InputStream.transferTo`, available since Java 9, transfers bytes without changing charsets. Before allowing a file write to `destination`, the application must still validate that the path is permitted. Do not use resource lookup as an arbitrary authorization mechanism to read/write files on the machine.

### Resources Can Be Empty

`getResourceAsStream` returns a **non-null stream** for an existing 0-byte resource; reading it returns EOF. **Do not equate an empty file with missing**. If a configuration must have content, perform separate validation after opening the stream (for example, a parser requiring mandatory keys).

## 14. Closing Streams, I/O Errors, and Resource Ownership

A resource may reside inside a JAR, and reading it can hold a handle to an archive or a connection to a data source. **Close the stream after use** to return resources to the system and avoid resource leaks.

Pattern to follow:

1. **Look up:** `InputStream opened = loader.getResourceAsStream(name)`.
2. **Check for missing:** if `opened == null`, throw an error or fall back according to the contract.
3. **Read inside `try-with-resources`.**
4. **Parse/validate the content.**
5. **Propagate the I/O error or wrap it with context while preserving the cause.**

Avoid:

```java
try {
    InputStream input = loader.getResourceAsStream(name);
    return new String(input.readAllBytes(), StandardCharsets.UTF_8);
} catch (Exception ignored) {
    return "";
}
```

This is a **bad pattern**: it causes a `NullPointerException` when missing, can swallow `IOException`, and fails to close the stream. Returning an empty string conflates a missing resource, a corrupted resource, and a resource with empty content.

A production wrapper may choose to throw `UncheckedIOException` from an API that does not declare checked exceptions. If so, **preserve the original cause** so callers can distinguish "not found" from "cannot read" and know the resource name and related loader/context.

### When a Resource in a JAR Opens a Stream, but Reading Fails

`getResourceAsStream` may return a stream before byte-reading errors are detected. Do not assume a non-null stream means the data is complete or valid. For JSON/CSV/properties, handle parse errors and validation separately; log the resource name and cause rather than automatically turning every error into `null`.

## 15. A Resource Existing Multiple Times: Precedence and Conflicts

Two dependency JARs both contain `config/app.properties`:

```text
a.jar!/config/app.properties
b.jar!/config/app.properties
```

If the application uses:

```java
ClassLoader loader = App.class.getClassLoader();
URL selected = loader.getResource("config/app.properties");
```

This is an illustrative snippet requiring `App`/`URL`. The loader may return **a selected URL** according to its policy. There is no standard rule that `a.jar` always takes precedence across every build and launcher. If multiple resources need to be merged, `getResources(name)` can provide an enumeration so the application can apply an explicit policy.

Typical cases:

- `META-INF/services/<service binary name>` often appears in multiple JARs and requires a discovery mechanism that reads multiple resources.
- `logging.properties` or `config/app.properties` appearing in multiple JARs can cause subtle configuration errors if lookup only returns the first copy.
- Duplicate resource names between host and plugin can unintentionally pick up the parent's copy instead of the plugin's.

How to prevent this:

- Use resource names with clear namespaces, for example `plugins/my-feature/settings.json`.
- Define where configuration overrides live with a **documented** precedence order.
- If a plugin must have its own data, use the plugin's loader/module or an explicit resource-provider API.
- Test the **actual artifact**, not just source files in the IDE.
- Print/log the URL via `getResource` when debugging, while avoiding exposing sensitive paths in end-user error messages.

## 16. Security Checks: Do Not Turn Resource Names into Arbitrary Paths

When a resource name is constructed from untrusted input:

```java
String name = "templates/" + userChoice + ".txt";
InputStream stream = loader.getResourceAsStream(name);
```

This is a snippet illustrating the risk. Do not assume string concatenation like this automatically prevents names containing `../`, unexpected package namespaces, or sensitive resources inside the artifact. **Prefer an allowlist** of permitted templates instead of accepting arbitrary paths:

```java
static String allowedTemplate(String choice) {
    return switch (choice) {
        case "welcome" -> "templates/welcome.txt";
        case "goodbye" -> "templates/goodbye.txt";
        default -> throw new IllegalArgumentException(
                "Unknown template: " + choice);
    };
}
```

This is a valid Java 17+ method to place in a class, though not a standalone program. It maps business values to fixed resource names, making auditing easier. If resource data needs protection, do not package production credentials/passwords directly into the JAR and treat obscuring file names as a security control.

**Note:** `getResourceAsStream` is a lookup-and-read API; it does not create a complete sandbox. A custom loader or URL handler can have side effects, and resource contents still require validation before use.

## 17. Common Errors and Fixes

| Symptom | Common cause | How to check and fix |
| --- | --- | --- |
| `getResourceAsStream(...) == null` even though the file is in the repository | Build did not copy the resource into the classpath/module artifact | Check `out/...`, `target/classes`, `build/resources/main`, and the JAR entry at the exact path. |
| `null` when using `"/config/x"` via `ClassLoader` | Leading slash prevents the name from matching | Use `loader.getResourceAsStream("config/x")`. |
| `null` when using `SomeClass.class.getResourceAsStream("x")` | The API searches relative to the class's package, not from the root | Change to `"/x"` if the resource is at the root, or place the file inside the package. |
| Runs in the IDE, fails in the JAR | Resource was not packaged or was shadowed | Inspect `jar --list`, the build artifact, classpath, and URL lookup. |
| `NullPointerException` in `InputStreamReader`/`Properties.load` | Returned `null` stream was not checked | Check first, report an error with the resource name, and do not swallow errors. |
| Broken Vietnamese diacritics in text | Text read with the wrong charset, or `Properties.load(InputStream)` used ISO-8859-1 | Read with `InputStreamReader(StandardCharsets.UTF_8)` and `Properties.load(Reader)`. |
| `IOException` when the resource actually exists | I/O error opening/reading the archive/network or loader source | Preserve the cause, distinguish from missing, and check the artifact and source. |
| Resource is in a plugin JAR, but the host cannot see it | Host loader cannot see JARs in the child plugin loader | Use a plugin-defined class/loader or design an appropriate bridge. |
| Reads the wrong config from another JAR | Multiple resources share the same name and lookup picks another copy | Use `getResources`/`getResource` to debug, clear namespaces, and explicit precedence order. |
| In a named module, the class is found but the resource cannot be read | Module resource encapsulation | Check package `opens` and choose the appropriate `Class`/`Module` resource API. |
| `FileNotFoundException` when using `Files.newInputStream`, whereas resource lookup gives a different result | File-system path ≠ classpath resource name | Choose the right API for where the resource is stored. |
| Resource exists, but content is empty | Entry has 0 bytes | Separate existence (non-null stream) from content validation. |
| Memory spikes when reading large files | `readAllBytes` loads the entire content into RAM | Stream by buffer/line, enforce capacity limits, and check size. |

### A Short yet Informative Debugging Workflow

1. Record the **actual resource name**, with or without a leading slash.
2. Record the **API used**: `Class.getResourceAsStream` or `ClassLoader.getResourceAsStream`; the two APIs do not share the same path rules.
3. Identify the **Class/ClassLoader/Module** used for the lookup. For plugins, do not default to the system loader.
4. Verify whether the file **made it into the runtime artifact** with the exact case and directory. On Linux, different casing creates different entry names; JAR entries are also case-sensitive.
5. Use `getResource(name)` to inspect the chosen URL, or `getResources(name)` when suspecting duplicate names.
6. If running in a named module, check **module encapsulation** and package opens.
7. If a stream is obtained yet an error still occurs, inspect **charset, parser, empty content, IOException, and size**.
8. For required resources, throw a clear error; for optional resources, apply the designed fallback.

## 18. Automated Testing Suggestions

For modules with critical resources, you should verify:

- **Unit test reading required resources**: content parses cleanly, mandatory keys exist, and values match the schema.
- **Missing resource test**: the wrapper method throws the expected exception and the message includes the resource name; it does not return an ambiguous empty string.
- **Optional resource test**: fallback is used only when missing; parse/I/O errors are not treated as missing.
- **UTF-8 test**: content with Vietnamese diacritics or non-ASCII characters still reads accurately.
- **Package-relative versus root test**: paths are normalized properly; leading slashes are handled appropriately for each API.
- **Integration test running from the final JAR**: verifies the file is actually packaged and the loader can see the resource.
- **Multiple loader/plugin test** if supported by the architecture: plugin resources are looked up by the appropriate loader rather than being unintentionally shadowed by a parent copy.
- **Named module test** if using JPMS: package opens/encapsulation and resource APIs behave the same in production as in tests.

### Build-Tool-Independent Assertion Pattern

Example verifying a required resource on the classpath:

```java
static void assertResourcePresent(Class<?> anchor, String absoluteName) {
    try (InputStream input = anchor.getResourceAsStream(absoluteName)) {
        if (input == null) {
            throw new AssertionError(
                    "Missing packaged resource: " + absoluteName);
        }
    } catch (java.io.IOException e) {
        throw new java.io.UncheckedIOException(e);
    }
}
```

This is an **illustrative method**; import `java.io.InputStream`, place it inside a class, and invoke it with `absoluteName` starting with `/` when targeting the root. Use `try-with-resources` even inside assertions to avoid resource leaks. If the resource content needs verification, read/parse it after confirming it is non-null.

Do not test solely against IDE source roots. Integration tests should use the **final distribution artifact**, because failures often occur during packaging.

## 19. Misconceptions to Avoid

- **"When a resource is not found, `getResourceAsStream` throws `FileNotFoundException`."** False: the API returns `null`; the caller decides how to handle it.
- **"Adding a leading `/` to the resource name is always right."** False: `Class` supports absolute resource names with a slash; `ClassLoader` usually requires a name **without a leading slash**.
- **"Every resource path is resolved from the working directory."** False: classpath/module lookup differs from filesystem-based `Path.of(...)`.
- **"If the file is visible in `src/main/resources`, the JVM can always read it."** False: the build/deploy process must package it into the runtime classpath/module image.
- **"`Class.forName` loads the class, so resources next to the class are definitely loaded as well."** False: class loading and resource lookup are two separate APIs and two separate behaviors.
- **"Resources inside a JAR must be extracted to physical files before they can be used."** False: `getResourceAsStream` reads the archive entry directly through a supporting loader.
- **"If the stream is non-null, the data is definitely valid."** False: the file could be empty, or suffer I/O or parse errors.
- **"You can skip `close()` because the resource ships with the application."** False: the stream still needs to be closed to release handles.
- **"`Properties.load(InputStream)` uses UTF-8 by default."** False: the traditional API uses ISO-8859-1; for UTF-8, use a Reader.
- **"A resource with the same name across multiple JARs is always merged."** False: `getResourceAsStream` typically returns one result; to enumerate all of them, use `getResources`.
- **"Changing the TCCL causes every `SomeClass.class.getResource...` call to use the new loader."** False: APIs on `Class` use the corresponding class/module context.
- **"If a resource exists, JPMS cannot block the lookup."** False: named module encapsulation can affect it.
- **"If not found, just return empty and continue."** False for required resources: doing so hides build, deployment, and configuration errors.

## 20. Self-Check Questions

**1. When `loader.getResourceAsStream("config/missing.properties")` does not find the resource, what is the normal result?** `null`, not a `FileNotFoundException` thrown directly by the method.

**2. Where does `Demo.class.getResourceAsStream("sample.txt")` look if `Demo` belongs to package `demo`?** At `demo/sample.txt` in the resource namespace visible to the class/module.

**3. What should you write to look up `sample.txt` at the root using the API on `Class`?** `Demo.class.getResourceAsStream("/sample.txt")`.

**4. What should you write to look up the same entry at the root using `ClassLoader`?** `loader.getResourceAsStream("sample.txt")`, without a leading slash.

**5. Why can a file exist in the repository yet the resource lookup still return null?** The file may not have been copied/packaged properly into the runtime classpath/module artifact, or it may not be visible to the loader/module.

**6. Why is it mandatory to check for null before creating an `InputStreamReader`?** Because a failed lookup returns `null`, and a Reader cannot read from a null stream.

**7. Why use `try-with-resources`?** It guarantees the stream is closed when reading finishes or when an exception occurs, reducing file/JAR handle leaks.

**8. How do you read a `.properties` file containing UTF-8 Vietnamese characters in Java?** Create an `InputStreamReader(stream, StandardCharsets.UTF_8)` and then call `Properties.load(Reader)`.

**9. Why is `new File(classUrl.getFile())` unreliable for resources inside a JAR?** Because the URL may be `jar:...!...` or percent-encoded, which does not correspond to a physical file path.

**10. A plugin has its own resource, but the system loader cannot see it; how do you fix this?** Look it up using the loader/class/module associated with the plugin or design an appropriate loader graph, rather than just renaming the file.

**11. When two JARs contain the same resource name, which API helps inspect all candidates?** `ClassLoader.getResources(name)` returns an enumeration of all visible URLs.

**12. A resource exists, yet the stream has 0 bytes: is that considered missing?** No. A non-null stream indicates the resource was opened; content validation must be done separately.

**13. In a named module, what besides the path can prevent reading a resource?** Encapsulation, package `opens`, and the rules of the `ClassLoader`/`Class`/`Module` API being used.

**14. How should an optional resource handle an I/O error while reading?** Do not equate IOException with a missing resource; report the error or apply a clear handling policy.

## 21. Official Documentation

- [Java SE 17 — `ClassLoader` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `getResource`, `getResourceAsStream`, `getResources`, parent delegation, and resource/module encapsulation.
- [Java SE 17 — `Class` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getResource` and `getResourceAsStream`, absolute names starting with `/`, and package-relative names.
- [Java SE 17 — `Module` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): `getResourceAsStream` in a module and access conditions under encapsulation.
- [Java SE 17 — `InputStream` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html): stream management, `readAllBytes`, `transferTo`, and `close`.
- [Java SE 17 — `Properties` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Properties.html): differences between `load(InputStream)` versus `load(Reader)` and character encoding.
- [JDK 17 — `jar` tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html): creating and listing JAR contents, verifying that resources are packaged.

**Remember:** **`getResourceAsStream` looks up a resource via a loader/module and returns a stream or `null`; it does not magically search source directories, nor does it automatically throw an exception when missing.** Choose the right path interpretation (`Class` is package-relative, `ClassLoader` starts from the resource root), verify the runtime artifact, check for null, read with the appropriate charset/format, close the stream, and distinguish **not found** from **read/parse failure**.
