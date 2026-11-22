# Reading Configuration from Directories and JARs Using Resource APIs in Java

## 1. Practice Objectives

The same Java application needs to read a configuration file when running in an IDE, via the `java -cp` command with a directory containing class files, and after being packaged into a `.jar` file. If the code writes:

~~~java
Path path = Path.of("resources/config/app.properties");
~~~

this is a **file system path relative to the working directory**, not a classpath path. Upon deployment, `resources` may not exist as a directory and the file may reside **inside a JAR**. Therefore, the appropriate solution for configuration **packaged with the application** is to use the **resource APIs**:

- `ClassLoader.getResource(name)` to find a `URL` to the resource.
- `ClassLoader.getResourceAsStream(name)` to open a stream to read bytes, regardless of whether the resource is in a classpath directory or a JAR entry.
- `Class.getResource(name)` and `Class.getResourceAsStream(name)` when you want to locate a resource relative to a class's package.
- `Properties.load(Reader)` or another format parser to read data once you have the stream.

**End-of-exercise goal:** Build a Java 17+ application yourself, read the same configuration file using a single program, run it in both ways (directory/JAR), observe `file:` versus `jar:` URLs, handle a non-existent file, understand the `/` rule, avoid converting a JAR URL into a `File`, and verify resources when packaging with Maven/Gradle.

## 2. How Does a Resource Differ from a File on the File System?

A **resource** here is data identified by a **logical name within the classpath/module scope**, for example `config/app.properties`, `demo/local-note.txt`, images/logos, or JSON files. A resource entry can be obtained from:

~~~text
Classpath root is a directory:
out/classes/
├── demo/
│   └── ResourceConfigDemo.class
├── config/
│   └── app.properties
└── demo/
    └── local-note.txt

Or classpath root is a JAR:
resource-demo.jar
├── META-INF/MANIFEST.MF
├── demo/ResourceConfigDemo.class
├── config/app.properties
└── demo/local-note.txt
~~~

In the first diagram, the `demo/` directory should be understood simply as **one common directory**: both entries `ResourceConfigDemo.class` and `local-note.txt` reside in it; there is no need to create two `demo` directories.

The **classpath root** is the location where the class loader searches for hierarchical names:

- The class name `demo.ResourceConfigDemo` corresponds to the entry `demo/ResourceConfigDemo.class`.
- The resource name `config/app.properties` corresponds to the entry `config/app.properties`.
- Do not include prefixes like `src/`, `resources/`, or `out/classes/` in the resource name if they are merely source/build directories.

If the program only uses:

~~~java
Files.newInputStream(Path.of("config/app.properties"));
~~~

it will read the file from the working directory and **only run when the exact physical file exists at that location**. Conversely:

~~~java
InputStream stream =
        ResourceConfigDemo.class.getClassLoader()
                .getResourceAsStream("config/app.properties");
~~~

will search for the resource across the sources visible to the class loader. This is an **illustrative snippet** placed inside the `ResourceConfigDemo` class; Section 5 provides the complete code with null handling and stream closing.

## 3. Four Key APIs and Resource Naming Rules

| API | Name Argument | Return Value |
| --- | --- | --- |
| `loader.getResource("config/app.properties")` | Name relative to the **classpath root**, without a leading `/` | `URL` or `null` |
| `loader.getResourceAsStream("config/app.properties")` | Same as above | `InputStream` or `null` |
| `SomeClass.class.getResource("/config/app.properties")` | Starts with `/` ⇒ from the classpath/module root depending on the API context | `URL` or `null` |
| `SomeClass.class.getResource("local-note.txt")` | No `/` ⇒ relative to the package of `SomeClass` | `URL` or `null` |

Suppose `SomeClass` is in package `demo`:

~~~text
SomeClass.class.getResource("local-note.txt")
    -> demo/local-note.txt

SomeClass.class.getResource("/demo/local-note.txt")
    -> demo/local-note.txt

SomeClass.class.getResource("/config/app.properties")
    -> config/app.properties

SomeClass.class.getClassLoader()
    .getResource("config/app.properties")
    -> config/app.properties
~~~

**A very common mistake:**

~~~java
loader.getResourceAsStream("/config/app.properties");
~~~

With `ClassLoader`, the standard name must be `config/app.properties` **without a leading slash**. `Class#getResource` is a **different** API; it handles a leading slash to denote an absolute name. There is no single universal rule that applies verbatim to every method named `getResource`.

### 3.1. Resource Names Use Slashes

Even when running on Windows, a resource name is a **hierarchical path with `/`**, not `\` or a drive path like `C:\`. Valid examples:

~~~text
config/app.properties
templates/email/welcome.html
demo/local-note.txt
~~~

The name `"config\\app.properties"` in Java source code is not a portable resource path.

### 3.2. When Should You Use Class Instead of ClassLoader?

- Use `MyClass.class.getResource("file.txt")` when the file is associated with the package containing the class.
- Use `MyClass.class.getResource("/config/app.properties")` for a resource under the root.
- Use `MyClass.class.getClassLoader().getResourceAsStream("...")` when the goal is to search within the lookup scope of the defining class loader.
- For named-module applications, the semantics differ from the traditional classpath: `Class#getResource` can search within the class's module and follows encapsulation rules; do not equate all overloads with a global classpath search.

You should choose the API with an explicit path name and avoid relying on the **current working directory** if the data is packaged alongside the bytecode.

## 4. Hands-on Exercise: File Set and Expected Result

We will create a small project, **without needing Maven, Gradle, or external libraries**:

~~~text
resource-practice/
├── src/
│   └── demo/
│       └── ResourceConfigDemo.java
└── resources/
    ├── config/
    │   └── app.properties
    └── demo/
        └── local-note.txt
~~~

Purpose:

- `src/demo/ResourceConfigDemo.java`: the program containing main.
- `resources/config/app.properties`: configuration file packaged into the `config/` root.
- `resources/demo/local-note.txt`: sample file to distinguish lookups relative to the `demo` package.

After compiling and copying resources, the classpath directory must contain:

~~~text
out/classes/
├── demo/
│   ├── ResourceConfigDemo.class
│   └── local-note.txt
└── config/
    └── app.properties
~~~

After creating the JAR, the structure of **entry names** inside the JAR remains `demo/...` and `config/...`. This consistency makes it possible **not to modify the Java source when changing the deployment format**.

## 5. Complete Java 17+ Code

### 5.1. resources/config/app.properties

Create a UTF-8 text file with the **exact content**:

~~~properties
app.name=Resource Demo
app.port=8080
feature.enabled=true
~~~

The keys are intentionally ASCII so the stdout transcript is independent of locale/terminal encoding. In real systems, Unicode can be used; Section 8 explains why choosing the right `Reader` matters when loading Properties.

### 5.2. resources/demo/local-note.txt

Create a single-line UTF-8 text file:

~~~text
package-local-resource
~~~

### 5.3. src/demo/ResourceConfigDemo.java

~~~java
package demo;

import java.io.FileNotFoundException;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.Enumeration;
import java.util.Properties;

public final class ResourceConfigDemo {
    private static final String CONFIG = "config/app.properties";

    private ResourceConfigDemo() {
    }

    private static Properties loadConfig(ClassLoader loader)
            throws IOException {
        Properties values = new Properties();

        try (InputStream input = loader.getResourceAsStream(CONFIG)) {
            if (input == null) {
                throw new FileNotFoundException(
                        "Missing classpath resource: " + CONFIG);
            }

            try (InputStreamReader reader = new InputStreamReader(
                    input, StandardCharsets.UTF_8)) {
                values.load(reader);
            }
        }

        return values;
    }

    private static String readLocalNote() throws IOException {
        try (InputStream input = ResourceConfigDemo.class
                .getResourceAsStream("local-note.txt")) {
            if (input == null) {
                throw new FileNotFoundException(
                        "Missing package resource: demo/local-note.txt");
            }
            return new String(
                    input.readAllBytes(), StandardCharsets.UTF_8).strip();
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader loader = ResourceConfigDemo.class.getClassLoader();

        URL byLoader = loader.getResource(CONFIG);
        if (byLoader == null) {
            throw new FileNotFoundException(
                    "Missing classpath resource: " + CONFIG);
        }

        URL byClass = ResourceConfigDemo.class
                .getResource("/" + CONFIG);

        Properties config = loadConfig(loader);

        String name = config.getProperty("app.name");
        int port = Integer.parseInt(
                config.getProperty("app.port"));
        boolean enabled = Boolean.parseBoolean(
                config.getProperty("feature.enabled"));

        System.out.println("resource found: " + (byLoader != null));
        System.out.println("absolute Class lookup matches: "
                + byLoader.equals(byClass));
        System.out.println("protocol: " + byLoader.getProtocol());
        System.out.println("name: " + name);
        System.out.println("port: " + port);
        System.out.println("feature enabled: " + enabled);
        System.out.println("local note: " + readLocalNote());

        Enumeration<URL> matches = loader.getResources(CONFIG);
        int count = 0;
        while (matches.hasMoreElements()) {
            matches.nextElement();
            count++;
        }
        System.out.println("matching resources: " + count);
    }
}
~~~

### 5.4. Key Points to Understand in the Code

**Choosing a loader from a known class:** `ResourceConfigDemo.class.getClassLoader()` is the defining loader of the application class. In this demo, it is the application loader and is non-null. For classes defined by the bootstrap loader, `getClassLoader()` may return null; you should not assume every class has a non-null loader object.

**Finding a resource via URL:** `getResource(CONFIG)` returns a `URL` if found. When loaded from a regular directory, the protocol is usually `file`. When reading an entry from a JAR, the protocol of the supported URL is usually `jar`. The program **only prints the protocol**, rather than printing the full URL with machine-specific paths.

**Reading content via stream:** `getResourceAsStream` returns `null` if the resource is not found or is inaccessible according to the loader's mechanism. You must check for null **before** creating the `InputStreamReader`, otherwise you will get an unclear `NullPointerException`.

**Closing resources:** `try-with-resources` closes the reader/stream even if `Properties.load` throws an `IOException`. Here both reader and input are declared in a nested try; closing input again is safe for standard `InputStream` implementations, though it can be simplified into a single try with both resources once null has been checked.

**Reading UTF-8 explicitly:** `Properties.load(Reader)` decodes according to the charset chosen by the reader. The code uses `StandardCharsets.UTF_8` instead of relying on the OS default charset or mistakenly using the `load(InputStream)` overload.

**Class-relative lookup:** `ResourceConfigDemo.class.getResourceAsStream("local-note.txt")` looks up `demo/local-note.txt` because the class is in the `demo` package. If you write `"/local-note.txt"`, the lookup starts from the root and will **not** point to the created file.

**getResources:** `loader.getResources(CONFIG)` returns an `Enumeration<URL>` of the matches found. In the two basic run commands below, each process has one source containing `config/app.properties`, so the expected count is 1. In an application with multiple classpath roots/JARs containing the same resource name, the count can be greater.

**Validating configuration:** `Integer.parseInt` will throw `NumberFormatException` if `app.port` is not a number. `Boolean.parseBoolean` returns false for any string not equal to "true" (case-insensitive), including typos such as `tru`; for production configurations, you should explicitly validate values rather than silently accepting them.

## 6. Running Directly from a Classpath Directory

### 6.1. Linux/macOS (bash, zsh)

From the `resource-practice` directory:

~~~bash
mkdir -p out/classes
javac --release 17 -d out/classes src/demo/ResourceConfigDemo.java
cp -R resources/config resources/demo out/classes/
java -cp out/classes demo.ResourceConfigDemo
~~~

The copy command creates `out/classes/config/app.properties` and `out/classes/demo/local-note.txt` in the exact right locations. If copied wrongly into `out/classes/resources/config`, the lookup name `config/app.properties` will not match.

### 6.2. Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force out/classes | Out-Null
javac --release 17 -d out/classes src/demo/ResourceConfigDemo.java
Copy-Item -Recurse -Force resources/config out/classes
Copy-Item -Recurse -Force resources/demo out/classes
java -cp out/classes demo.ResourceConfigDemo
~~~

**There is no need to change Java resource names to Windows backslashes.** Resource names still use `/` as written in the source code.

### 6.3. Expected Stdout: Directory

~~~text
resource found: true
absolute Class lookup matches: true
protocol: file
name: Resource Demo
port: 8080
feature enabled: true
local note: package-local-resource
matching resources: 1
~~~

Conditions for an exact transcript: the classpath consists solely of `out/classes` as shown in the command; no other classpath root contains `config/app.properties`; the files have the exact right contents; and it runs on a standard JDK supporting `file:` URLs. The working directory location must be right for the compile/copy commands to find the sources, **but the resource reading itself does not depend on the working directory** once the classes and resources are placed under the proper root.

## 7. Packaging as an Executable JAR and Reading the Same Configuration

After completing Section 6 (so `out/classes` already contains both `.class` and resource files), create the JAR:

~~~bash
jar --create --file out/resource-demo.jar \
    --main-class demo.ResourceConfigDemo \
    -C out/classes .
~~~

The command above uses `\` line continuations for bash/zsh. In Windows PowerShell or CMD, use a **single line**:

~~~powershell
jar --create --file out/resource-demo.jar --main-class demo.ResourceConfigDemo -C out/classes .
~~~

Inspect the contents:

~~~bash
jar --list --file out/resource-demo.jar
~~~

Entries that must exist (the JAR may also contain `META-INF/` or entries in a different order):

~~~text
META-INF/MANIFEST.MF
demo/ResourceConfigDemo.class
demo/local-note.txt
config/app.properties
~~~

Run the JAR:

~~~bash
java -jar out/resource-demo.jar
~~~

**Expected stdout when running from the JAR:**

~~~text
resource found: true
absolute Class lookup matches: true
protocol: jar
name: Resource Demo
port: 8080
feature enabled: true
local note: package-local-resource
matching resources: 1
~~~

When packaged properly, all **business configuration values** and the package resource are identical to running from a directory. The main thing that changes is `protocol: jar`, indicating the resource is served via a JAR URL rather than a file URL.

**Note:** `java -jar` normally uses `Main-Class` from the manifest and does not take the app classpath from `-cp` like a regular main-class invocation. If other dependency JARs are needed, you must configure the manifest class-path, module path, or use an appropriate launcher/packaging approach. This demo has no dependencies outside the JDK.

## 8. Reading Properties with the Right Encoding

Java has two important overloads:

~~~java
Properties p = new Properties();
p.load(inputStream);
~~~

and:

~~~java
Properties p = new Properties();
p.load(reader);
~~~

These are **illustrative snippets** assuming an already-opened `inputStream` or `reader` variable. The difference:

- `load(InputStream)` specifies interpreting the bytes of `.properties` as **ISO-8859-1** and handling `\uXXXX` escapes according to the format, rather than automatically treating them as UTF-8.
- `load(Reader)` reads the characters provided by the `Reader`. When the reader is `new InputStreamReader(stream, UTF_8)`, the file can contain UTF-8 Vietnamese text such as `app.title=Quản lý kho`.
- If using Java's `Properties.store(OutputStream,...)`, you need to understand its corresponding escape/encoding format; do not assume a file produced by a UTF-8 tool will always be read correctly by the InputStream overload.

In the program from Section 5, `new InputStreamReader(input, StandardCharsets.UTF_8)` guarantees the encoding **is explicitly specified**, without depending on the operating system default. You must ensure that the file `resources/config/app.properties` is actually saved as UTF-8.

### 8.1. Properties Are Not Just Simple key=value Lines

`Properties` supports comments using `#`/`!`, escape characters, continuation lines, and various separators. For example:

~~~properties
# A comment
app.name=Resource Demo
app.port: 8080
feature.enabled=true
~~~

Both `=` and `:` are accepted according to `Properties` syntax. If the configuration is YAML, JSON, XML, or a custom format, you should not use `Properties.load` to read it and expect proper semantics; you can still use the **resource stream**, but the parser on top must match the format.

### 8.2. Missing and Invalid Values

You can handle them by failing fast:

~~~java
String rawPort = config.getProperty("app.port");
if (rawPort == null || rawPort.isBlank()) {
    throw new IllegalArgumentException("Missing app.port");
}
int port = Integer.parseInt(rawPort);
if (port < 1 || port > 65535) {
    throw new IllegalArgumentException("Invalid app.port");
}
~~~

This is an **illustrative snippet** with `config` already loaded. It demonstrates a validation policy instead of accepting any present value. For secrets, avoid printing passwords/tokens directly and do not hardcode real credentials into the JAR.

## 9. Why Should You Not Convert a Resource URL to File or Path?

A familiar mistake:

~~~java
URL url = loader.getResource("config/app.properties");
File file = new File(url.getFile());
~~~

This is **incorrect/non-portable code**, not to mention the URL must be null-checked. When the URL is:

~~~text
file:/.../out/classes/config/app.properties
~~~

a physical file may exist, yet converting `URL.getFile()` directly to a `File` can still mishandle escaping, spaces, Unicode, or URI encoding.

When the URL is a JAR entry, its typical form is:

~~~text
jar:file:/.../out/resource-demo.jar!/config/app.properties
~~~

`config/app.properties` is **not a separate file on disk**, so `new File(url.getFile())` or `Paths.get(url.toURI())` cannot work by default the way they do for a file URL. Some cases can handle a JAR filesystem specially, but there is no need to do so just to read configuration.

**The default solution for reading packaged bytes/text:** use `getResourceAsStream` or `URL.openStream()` inside a `try-with-resources` block.

Only convert a URL to a `Path` when the application genuinely requires a path and you **are certain of the matching protocol/file system provider**, for example a `file:` URL converted via `Path.of(url.toURI())` with exception handling. Do not force every resource to be a physical file.

### 9.1. What If Configuration Needs to Be Edited After Deployment?

Configuration packaged inside a JAR is an **application artifact**; you should not try to open a resource entry to write back to it. If the configuration needs to be changed without rebuilding the JAR:

- Place the default configuration inside the JAR.
- Place the override configuration at an **external filesystem path** (via an environment variable, CLI argument, system property, or deployment config).
- Read the default via `getResourceAsStream`.
- Read the override using `Files.newBufferedReader(path, UTF_8)` if a file is specified and permitted.
- Apply clear precedence order, validation, error handling, and lifecycle management.

Strictly distinguish between a **classpath resource** and an **external user-managed config**; each uses the appropriate API and access permissions.

## 10. Duplicate Resource Names Across Multiple JARs or Directories

Suppose:

~~~text
lib-a.jar!/config/app.properties
lib-b.jar!/config/app.properties
out/classes/config/app.properties
~~~

and all three are on the lookup path. `ClassLoader.getResource("config/app.properties")` searches for **one** resource according to the lookup order of the specific loader, usually with delegation to the parent. `ClassLoader.getResources(...)` can list multiple matches.

You should not assume a **consistent order across all JVMs, all class loaders, and all module layers**:

- Parent-first and child-first class loaders can behave differently.
- The Java module path differs from the unnamed classpath; rules for named modules affect visibility.
- When multiple named modules with the same loader contain duplicate resources, the API Javadoc states that the search order may be **unspecified**.
- An application that relies on “whichever JAR happens to be read first” can easily change its configuration when the build/deploy setup changes.

To inspect all occurrences:

~~~java
Enumeration<URL> resources =
        loader.getResources("config/app.properties");
while (resources.hasMoreElements()) {
    URL current = resources.nextElement();
    System.out.println(current);
}
~~~

This **illustrative snippet** requires `loader` to exist and the method to permit `IOException`. For debugging, you can print the source URL; however, in production logs you should avoid exposing internal paths or tokens embedded in the URL.

For critical configuration:

1. Prefer **one clear owner** for the configuration.
2. Check for duplicate resources in the build pipeline.
3. If designing an overlay/merge mechanism, define the precedence order and merge contract yourself instead of leaving it to lookup order.
4. In a multi-tenant/plugin architecture where each plugin has its own loader, deciding **which loader** to call `getResource` on is a critical decision.

## 11. Parent Delegation and Context Class Loader

In the demo, the chosen loader is the defining loader of `ResourceConfigDemo`. In real-world applications, other possibilities exist:

- **Application class loader**: sees classes/resources on the app classpath.
- **Plugin class loader**: can see the plugin's resources and the parent's depending on policy; suitable when the file belongs to the plugin.
- **Thread Context ClassLoader (TCCL)**: used by some frameworks/framework SPIs to discover providers/resources of the current context; it does not automatically replace the class's defining loader.
- **Custom loader**: may override `findResource`, `findResources`, or use URLClassLoader; delegation and resource lookup behavior must be verified.

Illustrative example:

~~~java
ClassLoader context =
        Thread.currentThread().getContextClassLoader();

if (context != null) {
    URL pluginConfig = context.getResource("config/plugin.properties");
}
~~~

**Illustrative code snippet**: TCCL can be appropriate if the caller/framework actively manages it. However, you should not use TCCL arbitrarily when a file must be tied permanently to a specific class/module; the TCCL of a thread pool or container might point to a different loader, causing missing or duplicate configuration.

When calling `loader.getResourceAsStream`, the API takes **a resource name**, not a `Class<?>` to “merge” namespaces. The chosen loader still determines the lookup scope.

## 12. Named Modules (JPMS) Differ from the Classpath

In Java 9+ with named modules, resource APIs are subject to **encapsulation rules** beyond simple paths. According to the Java 17 Javadoc:

- `ClassLoader.getResource`, `getResourceAsStream`, and `getResources` for non-`.class` resources belonging to **packages of named modules** can usually only find them if the package is **opened unconditionally**; `opens p to q` alone may not be sufficient for generic ClassLoader-style lookups.
- `Class.getResource` and `Class.getResourceAsStream` on a class belonging to a named module search within the module owning the class and apply module encapsulation rules; a resource in a package not opened to the caller module may not be accessible.
- `Module.getResourceAsStream` has semantics tied to the module and caller, making it suitable when you need a resource from a specific module.
- Resources at paths **not belonging to a package** may be subject to different conditions than resources inside a module package; do not treat classpath examples as a guarantee for every module.
- `exports` for a public Java API is not synonymous with `opens` for deep reflection/resource encapsulation.

An illustrative descriptor example if a module intentionally allows access to resources in package `demo.config` via a generic ClassLoader:

~~~java
module demo.app {
    opens demo.config;
}
~~~

**This is a snippet illustrating JPMS configuration, not something to add to the classpath demo in Section 5.** The package must exist and the module descriptor must be compiled validly for the specific project; do not unconditionally open packages containing sensitive data just to make API lookups convenient.

**Choose how to organize resources proactively:** Placing configuration at a root path that does not represent a Java package, or accessing resources through a code API owned by the module, can be simpler and clearer in permissions than opening numerous packages.

## 13. Maven and Gradle: Resource Packaging Conventions

### 13.1. Maven

Familiar structure:

~~~text
project/
├── pom.xml
└── src/
    └── main/
        ├── java/demo/ResourceConfigDemo.java
        └── resources/
            ├── config/app.properties
            └── demo/local-note.txt
~~~

By default, the Maven Resources Plugin copies `src/main/resources` into the output classes directory (usually `target/classes`), and the JAR packaging tool takes those entries. **The file `src/main/resources/config/app.properties` becomes `config/app.properties` in the JAR**, not `resources/config/app.properties`.

This exercise does not require running Maven; this is a layout reference in case you port the working example to a Maven project.

### 13.2. Gradle

With the standard Java plugin:

~~~text
src/main/java/demo/ResourceConfigDemo.java
src/main/resources/config/app.properties
src/main/resources/demo/local-note.txt
~~~

Gradle processes resources into the build output (for example `build/resources/main`), and the required outputs are included on the classpath/JAR according to the configuration. If source sets or custom packaging are configured, you must inspect the **actual artifact**, rather than relying solely on the source tree layout.

### 13.3. Command to Verify the Artifact

~~~bash
jar --list --file out/resource-demo.jar
~~~

This is for the JAR in Section 7's exercise. When using a build tool, replace the file path with the artifact generated by the build. A configuration file that exists on disk but is **not inside the JAR** will not automatically appear via resource lookup when running only the packaged JAR.

With framework-specific executable/fat JARs (for example class files/resources in `BOOT-INF/classes`), specialized loaders may provide different URL schemes and packaging structures. **Do not assume the URL is always `jar:file:...!/config/...` across all launchers.** The `getResourceAsStream` API remains the preferred abstraction if supported by the framework loader.

## 14. Common Errors and How to Diagnose Them

| Symptom | Possible Cause | Check/Fix |
| --- | --- | --- |
| `getResourceAsStream` returns null | Wrong name or resources are not yet on the classpath/JAR | Print the lookup name, check build output and `jar --list` |
| Works in IDE, fails with `java -jar` | IDE adds `src/main/resources` to the classpath, but the JAR is missing entries | Check copy/build configuration |
| Fails on Windows | Used `\` in the resource name | Always use `/` |
| `Class.getResource("config/x")` cannot find it | This API searches relative to the class's package | Use `"/config/x"` or a ClassLoader root name |
| `ClassLoader.getResource("/config/x")` is null | Invalid leading slash in ClassLoader lookup | Remove the leading slash |
| `FileNotFoundException` only when running JAR | Code assumes the resource is a physical File | Use InputStream |
| Java reads Vietnamese text as garbled characters | Used `Properties.load(InputStream)` on UTF-8 bytes | `load(Reader)` with UTF-8 |
| Config from another JAR gets picked | Duplicate resource names and lookup order | `getResources`, avoid duplicates, define precedence |
| Package-local note not found | Incorrectly copied `demo/local-note.txt` into the build root | Place at the exact package-relative path |
| `Integer.parseInt` fails | Missing or non-numeric value | Validate key/format with a clear message |
| Resource name is correct, but module hides it | Named module encapsulation, package not opened | Check module/Javadoc API, controlled `opens` |
| Plugin cannot read config | Chose the wrong ClassLoader/TCCL | Use the defining/plugin loader of the right owner |
| `Resource URL` has an unfamiliar protocol | Custom/fat JAR loader provides a custom URL scheme | Read the stream instead of relying on a File path |
| File exists on disk but is not found | It lies outside the classpath roots | Copy it when packaging or use an explicit filesystem API |

### 14.1. Recommended Diagnostic Order

1. **Read the exact message** and resource name. Distinguish `null` from an `IOException`/parser exception.
2. Check whether the lookup uses **Class or ClassLoader**, and which package the class is in.
3. Inspect the **actual runtime classpath or module path**, instead of inferring from an IDE window.
4. Check the output folder `out/classes` or build/classes/resources.
5. Check the JAR entries, paying attention to resources at the **classpath root**.
6. If there are multiple JARs, call `getResources` to inspect duplicate matches.
7. If using a named module, check module ownership and encapsulation.
8. If the URL does not use `file`, avoid `File`/`Path` assumptions.
9. Verify the charset and whether the data adheres to the `Properties` format.
10. Run from a different working directory to confirm that the program truly does not depend on the CWD after packaging.

## 15. Extended Self-Practice: External Configuration with Precedence

A practical exercise is to use defaults from `config/app.properties` **inside the JAR**, and then allow the operator to provide an external file:

~~~text
Built-in default (JAR)        app.name=Resource Demo
                              app.port=8080

Optional external override    app.port=9090

Effective config              app.name=Resource Demo
                              app.port=9090
~~~

Illustrative API example:

~~~java
Properties values = new Properties();
try (InputStream in = loader.getResourceAsStream(
        "config/app.properties")) {
    if (in == null) {
        throw new FileNotFoundException("Missing packaged defaults");
    }
    values.load(new InputStreamReader(
            in, StandardCharsets.UTF_8));
}

if (externalPath != null) {
    try (var reader = Files.newBufferedReader(
            externalPath, StandardCharsets.UTF_8)) {
        values.load(reader);
    }
}
~~~

**This is a snippet, not a standalone runnable file**; `loader`/`externalPath` are defined beforehand, and appropriate imports, exception handling, and validation are required. The second `Properties.load` call can overwrite keys of the same name, if that is the precedence you choose.

Recommended design:

- The external file is **explicitly specified** via CLI/ENV, rather than arbitrarily searched near the working directory.
- Clearly report whether the default file is missing or the external override file does not exist.
- Restrict allowed paths if untrusted users can control the path.
- Do not permit dangerous config keys merely because the file exists; validate after merging.
- Do not print secrets/token values to logs.
- Distinguish editing an external file at runtime from **replacing a JAR artifact**, and do not attempt to write back to a classpath URL.

## 16. Practical Testing Checklist

- [ ] `src/demo/ResourceConfigDemo.java` compiles with `javac --release 17`.
- [ ] `config/app.properties` is copied under the **classpath root**, without an extra `resources/` level.
- [ ] `demo/local-note.txt` resides at the same package-relative path as the class.
- [ ] `java -cp out/classes demo.ResourceConfigDemo` prints `protocol: file` and the expected keys/values.
- [ ] The JAR contains `config/app.properties` and `demo/local-note.txt`.
- [ ] `java -jar out/resource-demo.jar` prints `protocol: jar` and the expected keys/values.
- [ ] Streams are closed with `try-with-resources`.
- [ ] Missing resources are reported clearly instead of throwing `NullPointerException`.
- [ ] UTF-8 Properties are read using `InputStreamReader` + `Properties.load(Reader)`.
- [ ] `new File(url.getFile())` is not used on an entry inside a JAR.
- [ ] There is no reliance on duplicate resource ordering outside a defined contract.
- [ ] If plugins are present, the right ClassLoader and right resource owner are used.
- [ ] If using JPMS, check named-module encapsulation separately.
- [ ] If external config is used, validate precedence order and prevent secret leaks.

## 17. Self-Check Questions

**1. What is a resource?** Data looked up by logical name within the lookup scope of a class loader/module, which may reside in a directory, a JAR, or a source supported by the loader.

**2. Does `ClassLoader.getResourceAsStream("config/app.properties")` require a physical file outside the JAR?** No; it can read an entry inside the JAR.

**3. What is the difference between `MyClass.class.getResource("x.txt")` and `getResource("/x.txt")`?** A name without a leading slash is relative to the class's package; a leading slash resolves from the root.

**4. Should you write `loader.getResource("/config/app.properties")`?** No, under standard ClassLoader rules; use `config/app.properties`.

**5. Why does a resource work when run in the IDE but is missing in the JAR?** The IDE may add the resource source directory to the classpath, whereas the packaged JAR is missing the file or has the wrong root.

**6. What protocol does a resource URL inside a JAR usually have?** Usually `jar` in standard Java JAR environments; do not depend on this for all custom launchers.

**7. Why shouldn't you use `new File(url.getFile())` to read every resource?** An entry inside a JAR is not a separate file on the OS filesystem; there are also URI encoding issues.

**8. What does `getResourceAsStream` return if the file is missing?** `null` per the API; you should check it and report a clear error.

**9. Does `Properties.load(InputStream)` read UTF-8 the same way as `load(Reader UTF_8)`?** No. The InputStream overload follows ISO-8859-1 rules; the Reader overload uses decoded characters.

**10. Why is `getResources` useful?** It lets you detect multiple resources with the same name within the classpath/module lookup scope.

**11. Why is try-with-resources needed?** To close the stream/reader promptly, avoiding leaks of file/JAR handles and resources.

**12. What is the difference between classpath config and external config?** Classpath config is data packaged with the artifact; external config is managed by the deployment environment via an explicit Path.

**13. Does `Class.getResource` always behave like `ClassLoader.getResource` in a named module?** No; named modules have their own ownership and encapsulation rules.

**14. Under what JAR entry does `src/main/resources/config/app.properties` in Maven usually appear?** `config/app.properties`.

**15. When obtaining a ClassLoader from `String.class.getClassLoader()`, can it be null?** Yes. Null typically represents the bootstrap loader.

## 18. Official References

- Java SE 17 — `ClassLoader.getResource`, `getResources`, `getResourceAsStream`, module encapsulation: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 — `Class.getResource` and `getResourceAsStream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- Java SE 17 — `Module.getResourceAsStream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html
- Java SE 17 — `Properties.load(InputStream)` and `load(Reader)`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Properties.html
- Java SE 17 — `URL.openStream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URL.html
- Java SE 17 — `JarFile` (when actually needing to manipulate archive entries): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarFile.html
- Java SE 17 — `jar` command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html
