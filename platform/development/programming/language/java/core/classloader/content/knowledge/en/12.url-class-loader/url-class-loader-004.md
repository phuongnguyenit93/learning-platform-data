# Loading Classes and Resources via URLClassLoader in Java

`java.net.URLClassLoader` is a built-in class loader in Java used to locate **classes** and **resources** from URLs pointing to directories or JAR files. It commonly appears in plugin systems, extensions, dynamic library loaders, or programs that need to read resource files from a JAR that is not on the application classpath.

To use `URLClassLoader` properly, you must understand five things:

1. The URL must point to the **root directory containing the package** or the **JAR file**, not to a class name.
2. The name passed to `loadClass` is a **binary class name** using dots, whereas a resource name is a path using `/`.
3. Default parent delegation can cause the **parent** to define a class instead of the `URLClassLoader` being called.
4. `loadClass` does not mean running the static initializer or creating a Java instance; `getResource` only finds the URL, while `getResourceAsStream` opens the stream.
5. `URLClassLoader.close()` closes the opened file/JAR handles; it **does not force** the JVM to unload already-defined classes.

This article focuses on the API, mechanisms, lifecycle, and common pitfalls, then builds a Java 17+ example that loads the same plugin from both a directory and a JAR.

## 1. Where Does URLClassLoader Sit in the Loader Hierarchy?

~~~text
java.lang.Object
  -> java.lang.ClassLoader
      -> java.security.SecureClassLoader
          -> java.net.URLClassLoader
~~~

`URLClassLoader` inherits the class loading model of `ClassLoader`, while providing a way to search for bytecode/resources using a URL search path and implementing `Closeable`.

~~~text
Host application
      |
      v
new URLClassLoader(urls, parent)
      |
      +--> Parent loader (prioritized in default loadClass)
      |       |
      |       +--> Java classes, shared APIs
      |
      +--> URL search path (if parent cannot find it)
              |
              +--> file:/.../classes/
              |       example/plugin/HelloPlugin.class
              |       example/plugin/greeting.txt
              |
              +--> file:/.../plugin.jar
                      example/plugin/HelloPlugin.class
                      example/plugin/greeting.txt
~~~

Some important methods:

| API | Returns | Purpose |
|---|---|---|
| `loadClass(String)` | `Class<?>` or throws `ClassNotFoundException` | Load a type by binary name |
| `getResource(String)` | `URL` or `null` | Find a single resource |
| `getResources(String)` | `Enumeration<URL>` | List multiple resources with the same name |
| `getResourceAsStream(String)` | `InputStream` or `null` | Open a resource for reading |
| `getURLs()` | `URL[]` | Inspect the loader's list of URLs |
| `getParent()` | `ClassLoader` or `null` | View the parent loader |
| `getName()` | `String` or `null` | Diagnostic name of the loader |
| `close()` | `void`, may throw `IOException` | Close the loader's file/JAR handles |

**Note:** `URLClassLoader` is not a Maven/Gradle dependency resolver, does not automatically download dependencies from the Internet, and is not a security sandbox for untrusted plugins.

## 2. Constructors and Parent Delegation

Common constructors in Java 17:

~~~java
URLClassLoader a = new URLClassLoader(urls);
URLClassLoader b = new URLClassLoader(urls, parent);
URLClassLoader c = new URLClassLoader("plugin-a", urls, parent);
~~~

These are **illustrative snippets**; `urls` must be a `URL[]` and `parent` an appropriate `ClassLoader`.

- `URLClassLoader(URL[])` uses the system class loader as its parent.
- `URLClassLoader(URL[], ClassLoader)` allows specifying the parent explicitly.
- `URLClassLoader(String, URL[], ClassLoader)` creates a named loader (Java 9+); the name makes logs easier to read, though it is **not a unique identifier**.
- If the parent is `null`, delegation to the bootstrap class loader does not guarantee that all platform classes are available.
- For plugins that need to implement a shared host interface, the parent should see **a single copy** of that API. Do not redefine the same interface inside each child loader.

For the default implementation of `ClassLoader.loadClass`:

~~~text
loadClass("example.plugin.HelloPlugin")
                 |
       findLoadedClass(name)?
          /              \
        yes               no
         |                 |
    return Class      ask parent first
                           |
                   parent found it?
                    /          \
                  yes           no
                   |             |
             return Class   findClass in URL[]
                                 |
                             defineClass
~~~

If the parent already sees the same binary name, the child may receive the `Class` defined by the parent. Therefore, this snippet:

~~~java
Class<?> type = loader.loadClass("example.plugin.HelloPlugin");
System.out.println(type.getClassLoader() == loader);
~~~

may print `false` even though the `loadClass` call succeeded. `Class.getClassLoader()` indicates the **defining loader**; it is not always the initiating loader.

**JVM type identity = (binary class name, defining class loader).** Two different loaders that each define the same `example.plugin.HelloPlugin` produce two separate runtime types that cannot be cast to each other.

## 3. Directory URLs and JAR File URLs

### Directories

If you have `plugins/classes/example/plugin/HelloPlugin.class`, the root URL needs to point to **`plugins/classes/`**:

~~~java
import java.net.URL;
import java.nio.file.Path;

Path directory = Path.of("plugins", "classes").toAbsolutePath();
URL directoryUrl = directory.toUri().toURL();
~~~

`URLClassLoader` treats a `file:` URL ending with `/` as a directory. Create URLs using `Path.toUri().toURL()` rather than manually concatenating `"file:" + path` so that Windows paths, spaces, and special characters are handled properly. When the directory actually exists, its URL is produced in the appropriate form.

Do not point the URL to `HelloPlugin.class` itself; the loader appends `example/plugin/HelloPlugin.class` from the binary name when searching inside the root.

### JAR Files

~~~java
Path jarPath = Path.of("plugins", "hello-plugin.jar").toAbsolutePath();
URL jarUrl = jarPath.toUri().toURL();
~~~

A `file:/.../hello-plugin.jar` URL is a valid input. For a resource inside a JAR, `getResource` may return a URL of the form:

~~~text
jar:file:/.../hello-plugin.jar!/example/plugin/greeting.txt
~~~

You do not need to write `jar:file:...!/` yourself as the input URL to load **an entire JAR**. Files inside the JAR must follow the proper package path:

~~~text
hello-plugin.jar
  META-INF/MANIFEST.MF
  example/plugin/HelloPlugin.class
  example/plugin/greeting.txt
~~~

**A plugin JAR does not need `Main-Class`.** `Main-Class` is for executable JARs run with `java -jar`; `URLClassLoader` loads classes by name via `loadClass` rather than executing the JAR's entry point.

### Multiple URLs

~~~java
URL[] sources = {
    Path.of("plugins/classes").toUri().toURL(),
    Path.of("plugins/one.jar").toUri().toURL(),
    Path.of("plugins/two.jar").toUri().toURL()
};

try (URLClassLoader loader = new URLClassLoader(
        "extensions", sources, ClassLoader.getSystemClassLoader())) {
    Class<?> type = loader.loadClass("example.plugin.HelloPlugin");
}
~~~

This is an **illustrative snippet** that requires the corresponding URLs to exist. The parent is queried first under default delegation, after which the child searches the URLs in their configured order. If two JARs contain duplicate class or resource names, the position in the search path can determine which one is found. A JAR's `Class-Path` manifest attribute can also affect the effective search path; do not assume only the original URLs are present.

## 4. Loading Classes, Initializing Classes, and Creating Instances

Three calls:

~~~java
Class<?> a = loader.loadClass("example.plugin.HelloPlugin");

Class<?> b = Class.forName(
        "example.plugin.HelloPlugin", false, loader);

Class<?> c = Class.forName(
        "example.plugin.HelloPlugin", true, loader);
~~~

These are API snippets; they require an already-configured loader and `ClassNotFoundException` handling.

| Operation | Meaning |
|---|---|
| `loader.loadClass(name)` | Requests loading the class, but **does not request static initialization** |
| `Class.forName(name, false, loader)` | Finds/loads/links the type without requesting initialization |
| `Class.forName(name, true, loader)` | Finds and requests initialization of the type |
| `type.getConstructor().newInstance()` | Creates an object via reflection if the constructor permits |
| `type.getMethod("sayHello").invoke(instance)` | Invokes a method via reflection; may throw an exception or invocation target error |

Having a `Class<?>` object does not mean a plugin instance exists yet. Calling `loadClass` multiple times on the same loader typically returns the already-loaded runtime definition rather than redefining the same name on every call.

When using a shared plugin API:

~~~java
PluginApi plugin = (PluginApi) type.getConstructor().newInstance();
~~~

This is an illustrative snippet and is **only valid when `PluginApi` is defined by a shared loader and the plugin class implements that exact runtime interface**. If the host and plugin loaders each define their own copy of `PluginApi` with the same name, the cast can throw a `ClassCastException`.

## 5. Finding Resources: Paths and APIs

### `getResource`, `getResources`, and `getResourceAsStream`

~~~java
URL first = loader.getResource("example/plugin/greeting.txt");

Enumeration<URL> matches =
        loader.getResources("example/plugin/greeting.txt");

try (InputStream input =
        loader.getResourceAsStream("example/plugin/greeting.txt")) {
    if (input == null) {
        throw new IllegalStateException("Resource not found");
    }
    String text = new String(
            input.readAllBytes(), StandardCharsets.UTF_8);
    System.out.println(text);
}
~~~

These are **API snippets** requiring imports for `URL`, `Enumeration`, `InputStream`, and `StandardCharsets`, as well as appropriate exception handling.

- `getResource` returns the first matching `URL` or `null`.
- `getResources` returns an enumeration of matching URLs; useful when multiple JARs contain a resource with the same name.
- `getResourceAsStream` opens a stream or returns `null`. Close the stream with try-with-resources, even if the loader is closed later.
- A resource may be found first by the parent according to delegation rules; the `URLClassLoader` is not guaranteed to be the physical source of the returned resource.

### `Class` and `ClassLoader` Resolve Paths Differently

Suppose `example.plugin.HelloPlugin` sits next to `example/plugin/greeting.txt`:

~~~java
Class<?> type = loader.loadClass("example.plugin.HelloPlugin");

// Class API: relative to package example.plugin
InputStream a = type.getResourceAsStream("greeting.txt");

// Class API: absolute from root
InputStream b = type.getResourceAsStream(
        "/example/plugin/greeting.txt");

// ClassLoader API: always pass path from root
InputStream c = loader.getResourceAsStream(
        "example/plugin/greeting.txt");
~~~

All three streams can point to the same resource. They are for illustration only and should be closed after use.

| Call | Name searched |
|---|---|
| `type.getResource("greeting.txt")` | `example/plugin/greeting.txt` |
| `type.getResource("/example/plugin/greeting.txt")` | `example/plugin/greeting.txt` |
| `loader.getResource("example/plugin/greeting.txt")` | `example/plugin/greeting.txt` |
| `loader.getResource("greeting.txt")` | `greeting.txt` at root |

Do not put a leading `/` in resource names passed to `ClassLoader` out of habit from `Class.getResource`. Resource paths use `/`, whereas class binary names use `.`.

If a resource resides in a **named module** loaded via JPMS, `opens`/module encapsulation rules also apply; the example below uses a plugin class in an unnamed module to focus on URL and path rules.

## 6. Runnable Java 17+ Example: Loading the Same Class and Resource from Directory and JAR

The example has two Java files and one text file; the host is compiled **without the plugin on the classpath**. Two independent `URLClassLoader` instances will define two separate copies of `example.plugin.HelloPlugin` and read the resource with the same name.

### Directory Structure

~~~text
project/
  src/
    plugin/example/plugin/HelloPlugin.java
    host/LoaderLab.java
  resources/
    example/plugin/greeting.txt
  out/
    plugin/
    host/
  dist/
    hello-plugin.jar
~~~

### File `src/plugin/example/plugin/HelloPlugin.java`

~~~java
package example.plugin;

public class HelloPlugin {
    public HelloPlugin() {
    }

    public String sayHello() {
        return "Hello from URLClassLoader";
    }
}
~~~

### File `resources/example/plugin/greeting.txt`

~~~text
resource-ok
~~~

### File `src/host/LoaderLab.java`

~~~java
import java.io.InputStream;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;

public class LoaderLab {
    private static final String CLASS_NAME =
            "example.plugin.HelloPlugin";
    private static final String RESOURCE_NAME =
            "example/plugin/greeting.txt";

    private static Class<?> loadSource(String label, URL source)
            throws Exception {
        ClassLoader parent = ClassLoader.getPlatformClassLoader();

        try (URLClassLoader loader = new URLClassLoader(
                label, new URL[] {source}, parent)) {

            Class<?> type = loader.loadClass(CLASS_NAME);
            Object instance = type.getConstructor().newInstance();
            String hello = (String) type.getMethod("sayHello")
                    .invoke(instance);

            System.out.println(label + " class: " + hello);
            System.out.println(label + " defined here: "
                    + (type.getClassLoader() == loader));

            try (InputStream in =
                    loader.getResourceAsStream(RESOURCE_NAME)) {
                if (in == null) {
                    throw new IllegalStateException(
                            "Missing: " + RESOURCE_NAME);
                }
                String data = new String(
                        in.readAllBytes(), StandardCharsets.UTF_8).strip();
                System.out.println(label + " resource: " + data);
            }

            try (InputStream in =
                    type.getResourceAsStream("greeting.txt")) {
                System.out.println(label + " class-relative: "
                        + (in != null));
            }

            return type;
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: LoaderLab <directory> <jar>");
        }

        URL dir = Path.of(args[0])
                .toAbsolutePath().toUri().toURL();
        URL jar = Path.of(args[1])
                .toAbsolutePath().toUri().toURL();

        Class<?> fromDir = loadSource("directory", dir);
        Class<?> fromJar = loadSource("jar", jar);

        System.out.println("same class name: "
                + fromDir.getName().equals(fromJar.getName()));
        System.out.println("same runtime class: "
                + (fromDir == fromJar));
    }
}
~~~

**Key points in the code:**

- `URLClassLoader(String, URL[], ClassLoader)` creates a named loader; one loader per source.
- `getPlatformClassLoader()` is used as the parent **only for this demo**, so it does not see the plugin class on the application classpath and the child becomes the defining loader.
- `loadClass` returns `Class<?>`; reflection is what creates the object.
- The loader's `getResourceAsStream` takes a path from the root; `Class.getResourceAsStream` takes a path relative to the package.
- Returning `Class<?>` from the method and then closing the loader demonstrates that closing the loader **does not automatically remove the existing runtime type**.

### Compile and Package (Bash/Linux/macOS)

~~~bash
mkdir -p out/plugin/example/plugin out/host dist

javac -d out/plugin src/plugin/example/plugin/HelloPlugin.java

cp resources/example/plugin/greeting.txt out/plugin/example/plugin/greeting.txt

jar --create --file dist/hello-plugin.jar -C out/plugin .

javac -d out/host src/host/LoaderLab.java
~~~

`javac` does not copy `.txt` files automatically, so the `cp` command is essential. After building:

~~~text
out/plugin/example/plugin/HelloPlugin.class
out/plugin/example/plugin/greeting.txt
out/host/LoaderLab.class
dist/hello-plugin.jar
~~~

Inspect the JAR contents with `jar --list --file dist/hello-plugin.jar`; both `example/plugin/HelloPlugin.class` and `example/plugin/greeting.txt` should be present.

### Run the Host

~~~bash
java -cp out/host LoaderLab out/plugin dist/hello-plugin.jar
~~~

**Expected stdout on JDK 17+:**

~~~text
directory class: Hello from URLClassLoader
directory defined here: true
directory resource: resource-ok
directory class-relative: true
jar class: Hello from URLClassLoader
jar defined here: true
jar resource: resource-ok
jar class-relative: true
same class name: true
same runtime class: false
~~~

The copy from the directory and the copy from the JAR have the same binary name but are **not the same runtime `Class` object**. Each `URLClassLoader` defines its own separate copy. This is why loader identity affects type compatibility, even when the bytecode is completely identical.

**On Windows PowerShell**, use `New-Item -ItemType Directory -Force` to create directories and `Copy-Item` instead of `cp`; the `javac`, `jar`, and `java` commands remain the same. This example runs without multiple classpath entries, so the `;` separator is not needed.

## 7. Loader Lifecycle and Closing Resources

`URLClassLoader` implements `Closeable`, so use try-with-resources:

~~~java
try (URLClassLoader loader = new URLClassLoader(urls, parent)) {
    // load classes and read resources
}
~~~

Behavior of `close()`:

- Attempts to close JAR/file handles opened by the loader.
- Does not turn an already-loaded class back into an unloaded class; classes and instances already created can still be used.
- Does not guarantee **immediate class unloading**. Unloading still depends on whether references remain to the loader, objects, `Class<?>`, threads, context loaders, caches, and GC decisions.
- Should not be called concurrently while another thread is still loading classes; the API contract does not guarantee deterministic behavior under such races.
- New classes/resources from the loader's own URLs may no longer be found after the loader is closed; the parent can still provide its own classes or resources.
- Even though the loader will be closed, an `InputStream` should still be closed immediately after reading.

In long-running plugin systems, manage each plugin and its `URLClassLoader` with a clear lifecycle; do not open and close a new loader on every method call.

## 8. URLClassLoader vs. Classpath and JPMS

**Host classpath:** Creating a separate `URLClassLoader` does not modify `java.class.path`, `CLASSPATH`, or the search path of other loaders. Calling `Class.forName(String)` in the host uses the caller's loader; use `loader.loadClass(name)` or the `Class.forName(name, initialize, loader)` overload to search within the plugin loader.

**JPMS:** Adding a modular JAR to the URL array does not automatically resolve named modules, create a `ModuleLayer`, or enforce `requires` rules like the module path does. The example in this article uses an unnamed module.

**Packaging and security:** A plain loader does not resolve Maven/Gradle dependency graphs, unpack nested JARs, or sandbox untrusted code. Those concerns must be handled through appropriate build/launcher tooling and process boundaries.

## 9. Common Errors and How to Troubleshoot Them

| Symptom | Possible Cause | What to Check |
|---|---|---|
| `ClassNotFoundException` | Wrong root URL, wrong binary name, or missing `.class` | Check `example/plugin/HelloPlugin.class` |
| `NoClassDefFoundError` | Missing dependency, linkage error, or prior initialization failure | Read the cause chain / stack trace |
| `UnsupportedClassVersionError` | Java runtime is older than the class version | Check `javac --release` and runtime version |
| `IllegalAccessException` | Constructor or method is not accessible | Check public API and JPMS |
| `ClassCastException` | Same API name but different defining loaders | Compare `getClassLoader()` of both `Class` objects |
| Resource returns `null` | Missing file, wrong path, resource not copied, wrong loader, encapsulation | Check JAR entries and path |
| Unexpected resource | Parent or an earlier URL has a resource with the same name | Use `getResources` and inspect delegation |
| JAR is locked | Stream or loader not closed | Use try-with-resources |
| Class still exists after `close()` | References remain to loader/class/object | Check caches, threads, callbacks |

### Quick Diagnostics

**Inspect the URLs in use:**

~~~java
for (URL u : loader.getURLs()) {
    System.out.println(u);
}
~~~

**Check a class's defining loader:**

~~~java
Class<?> type = loader.loadClass("example.plugin.HelloPlugin");
System.out.println(type.getClassLoader() == loader);
~~~

**Check a resource from the root:**

~~~java
URL resource = loader.getResource("example/plugin/greeting.txt");
System.out.println(resource == null ? "missing" : resource);
~~~

These are illustrative snippets requiring `loader` to be a `URLClassLoader` along with the necessary imports and exception handling. For JAR files, `jar --list --file your-plugin.jar` helps distinguish a genuinely missing file from an incorrect resource lookup.

## 10. Common Misconceptions

1. **"A JAR URL immediately loads every class."** No; classes are located and loaded on demand.
2. **"`loadClass` means initialize."** No; if you need eager initialization, use `Class.forName(name, true, loader)`.
3. **"ClassLoader automatically prepends the package or accepts a leading `/` in resource paths."** Use a path from the classpath root; `Class.getResource` has its own rules.
4. **"`getResources` only returns one URL."** It can list multiple resources with the same name.
5. **"`getResourceAsStream` is never `null` and closes itself."** Check for `null` and close the stream.
6. **"The host can always cast a plugin's interface of the same name."** The defining loader of the API must be a single shared runtime type.
7. **"Closing the loader immediately stops every plugin method."** Already-loaded classes remain alive, though lazy dependencies or resources after closing may fail.
8. **"URLClassLoader is a dependency resolver, module launcher, or sandbox."** No; those are separate mechanisms.

## 11. Self-Check Questions

**Question 1.** Class `com.acme.Tool` is located at `plugins/classes/com/acme/Tool.class`. Where should the root URL point?

**Answer:** `plugins/classes/`, as a directory URL ending with `/`; load it with `loadClass("com.acme.Tool")`.

**Question 2.** If the parent defines `com.acme.Tool`, is `toolClass.getClassLoader() == child` true?

**Answer:** No, because the defining loader is the parent; the child only initiated the request.

**Question 3.** Resource `com/acme/config.txt` is in the same package as `Tool`. Which call on the loader corresponds to `Tool.class.getResourceAsStream("config.txt")`?

**Answer:** `loader.getResourceAsStream("com/acme/config.txt")`, not `loader.getResourceAsStream("config.txt")`.

**Question 4.** Two `URLClassLoader` instances each define `com.acme.Tool` from the exact same bytecode. Do they share a single runtime type?

**Answer:** No. The same binary name with different defining loaders produces two distinct runtime types.

**Question 5.** Why should you close a `URLClassLoader`?

**Answer:** To release file/JAR handles and related resources, not to force the JVM to unload classes immediately.

**Question 6.** The host needs to cast the plugin to the `PluginApi` interface. Where should the API be placed?

**Answer:** In a shared library defined by the parent so that the host and plugin use the exact same runtime interface.

**Question 7.** A resource exists in the JAR, yet `getResourceAsStream` returns `null`. What should you check before changing the loader code?

**Answer:** Check the entry name, the resource path from the root, which JAR the loader actually opened, whether the resource was copied during build, and the parent's sources.

## 12. Decision Map

~~~text
Are plugin classes/resources in a directory or a JAR?
               |
               v
Create the proper root URL using Path.toUri().toURL()
               |
               v
Choose an appropriate parent for shared APIs
               |
               v
new URLClassLoader(urls, parent)
               |
       +-------+--------+
       |                |
       v                v
  loadClass(name)   getResource(name)
       |                |
       v                v
  Class<?>          URL/InputStream
       |                |
  check defining    read resource,
  loader identity   close stream
       |
  create object if needed
       |
       +--------+-------+
                v
   close loader at end of lifecycle
                |
       close != immediate class unload
~~~

**Summary:** `URLClassLoader` combines a sequence of **source URLs** with **parent delegation**. Loading classes properly requires binary names and the right root URLs; finding resources properly requires paths matching the API; running plugins reliably requires managing type identity, dependencies, and stream/loader lifecycles.

### Official Documentation

- [Java SE 17 — URLClassLoader API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html)
- [Java SE 17 — ClassLoader API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [Java SE 17 — Class.getResourceAsStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getResourceAsStream(java.lang.String))
- [JVMS `5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3)
