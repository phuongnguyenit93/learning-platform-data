# Creating a URLClassLoader from Directories and JARs

## 1. The Problem: Adding Class Sources at Runtime

Once a Java program has started, it sometimes needs to load a plugin, extension, driver, or external library without placing all of those classes/JARs on the initial application classpath. **`java.net.URLClassLoader`** is a built-in class loader that locates classes and resources via a **list of URLs** pointing to a directory containing `.class` files or to a JAR.

A common example: the host application has `PluginHost.class`, while the plugin `sample.Greeting` is compiled to `out/plugin/sample/Greeting.class` or packaged into `dist/plugin.jar`. The host creates a `URLClassLoader` with a URL pointing to the exact **package root** or **JAR file**, and then calls `loadClass("sample.Greeting")`.

Concepts:

- **URL search path**: the URLs that a `URLClassLoader` searches **after trying its parent** under the default parent-first policy.
- **Directory URL**: a URL using the `file:` scheme, ending with a `/`, pointing to the **package root directory**. For example, `file:/home/user/app/out/plugin/`.
- **JAR URL**: typically a `file:` URL pointing to **the JAR file itself**, such as `file:/home/user/app/dist/plugin.jar`; `URLClassLoader` opens the archive and looks up entries by package path. The API also supports suitable URLs using the `jar:` protocol; in the ordinary JAR file scenario, there is no need to manually construct the `jar:file:...!/` syntax.
- **Parent loader**: the loader queried first. It is usually advisable to use `PluginHost.class.getClassLoader()` so that the plugin can see the application's shared interfaces/APIs.
- **Defining loader**: the loader that actually defines a class. Obtained via `SomeClass.class.getClassLoader()`; it may differ from the loader object on which you called `loadClass`.

`URLClassLoader` supports classes/resources on a traditional classpath. It does **not** automatically set up a Java Platform Module System layer, does not automatically find any JARs nested inside another JAR, and does not automatically provide a security sandbox environment for untrusted bytecode.

## 2. URL Structure and Package Paths Must Be Correct

Suppose the binary name of the plugin is `sample.Greeting`. The corresponding class file has the path `sample/Greeting.class` beneath the search **root**.

### Directory Case

~~~text
out/
└── plugin/                  <-- The URL must point here
    └── sample/
        ├── Greeting.class
        └── message.txt
~~~

Semantically valid URL:

~~~text
file:/project/out/plugin/
~~~

`URLClassLoader` converts the binary name `sample.Greeting` into the corresponding path `sample/Greeting.class` and searches under the root directory. Do **not** use `out/plugin/sample/` as the root URL if `sample` itself is the package: in that case, the loader will search the wrong path `.../sample/sample/Greeting.class`.

According to the `URLClassLoader` Javadoc, **a `file:` URL ending with `/` is treated as a directory**; other `file:` URLs are treated as JAR files to be opened as needed. Therefore, the trailing slash on a directory URL is very important.

To construct a URL in a portable way, prefer:

~~~java
Path directory = Path.of("out", "plugin")
        .toAbsolutePath().normalize();
URL directoryUrl = directory.toUri().toURL();
~~~

The snippet above assumes the directory **already exists**, because how `Path.toUri()` forms a directory URL relies on filesystem information; in the full example in Section 5, the directory is created beforehand. Avoid manually concatenating strings like `"file://" + path` or manually replacing `\` with `/`; on Windows, spaces, drive letters, and special characters need to be properly URI/URL encoded.

### JAR Case

~~~text
dist/
└── plugin.jar
    ├── META-INF/MANIFEST.MF
    └── sample/
        ├── Greeting.class
        └── message.txt
~~~

URL pointing to the **archive file**:

~~~java
Path jarFile = Path.of("dist", "plugin.jar")
        .toAbsolutePath().normalize();
URL jarUrl = jarFile.toUri().toURL();
~~~

An example of how the URL may appear is `file:/project/dist/plugin.jar`; it does **not** end with `/`. `URLClassLoader` automatically reads the appropriate entries from the JAR.

Do not pass `file:/project/dist/` and assume the loader will **automatically scan all JARs** in the `dist` directory. If you provide a directory URL, it uses that directory as a source of loose class files; any JARs to be included must be listed as separate URLs or through supporting metadata/design. Wildcard syntax such as `lib/*` from the Java launcher is **not an automatic wildcard feature of `new URLClassLoader(new URL[]{...})`**.

## 3. Instantiating URLClassLoader: Constructors and Parent

Commonly used constructors:

~~~java
URLClassLoader loader = new URLClassLoader(
        new URL[]{directoryUrl}, parentLoader);
~~~

~~~java
URLClassLoader loader = new URLClassLoader(
        new URL[]{jarUrl}, parentLoader);
~~~

For multiple sources, pass an array of URLs:

~~~java
URLClassLoader loader = new URLClassLoader(
        new URL[]{directoryUrl, firstJarUrl, secondJarUrl},
        PluginHost.class.getClassLoader());
~~~

These are **illustrative snippets**, assuming all URL variables and `PluginHost` already exist; runnable standalone code is in Section 5. The list of URLs is searched **in the order provided**, but only after the parent has been tried according to the default lookup behavior.

| Constructor | Meaning |
| --- | --- |
| `new URLClassLoader(urls)` | Uses the default parent according to the `ClassLoader` mechanism. |
| `new URLClassLoader(urls, parent)` | Explicitly specifies the loader to delegate to first. |
| `new URLClassLoader("plugin-loader", urls, parent)` | Names the loader to aid diagnostics (Java 9+). |
| `new URLClassLoader(urls, null)` | Parent delegation corresponds to the bootstrap class loader; it does **not** mean this loader is the bootstrap loader and may cause APIs not defined by the bootstrap loader to be missing. |

**Recommendation:** if the host shares an interface, for example `api.Plugin`, keep that interface in the parent and let the child load the implementation class. The plugin uses the same `api.Plugin` seen by the host, avoiding two definitions of the interface with the same name but different defining loaders.

### Parent-First Does Not Mean Every Class Is Defined by the Parent

Default `ClassLoader.loadClass`:

~~~text
Host requests loader.loadClass("sample.Greeting")
                      |
                      v
           Child already has class?
                      |
                   Not yet
                      |
                      v
        Parent.loadClass("sample.Greeting")
                 /           \
              Found        Not found
                |               |
                v               v
     Return parent Class   Child.findClass(...)
                                |
                         Search in URLs
                                |
                          Define class
~~~

If the parent already has `sample.Greeting` on the application classpath, the child URLClassLoader can return **the parent's version**, rather than defining the one inside the plugin JAR. To verify which loader defined the class, use:

~~~java
Class<?> type = loader.loadClass("sample.Greeting");
boolean loadedByChild = type.getClassLoader() == loader;
~~~

In the standalone example below, the plugin is intentionally **not** placed on the host's classpath so that this check is always `true`.

## 4. Two Key APIs: loadClass and Resource Lookup

### Loading a Class by Binary Name

~~~java
Class<?> type = loader.loadClass("sample.Greeting");
~~~

The name must be in **binary name** form (using `.` as the package separator). Do not pass `"sample/Greeting.class"` or a JAR path to `loadClass`. `loadClass` returns a `Class<?>` object; this call itself does not actively initialize the static initializer of `Greeting`.

To initialize or use the type dynamically, you can use reflection:

~~~java
String result = (String) type.getMethod("hello").invoke(null);
~~~

This is an example of calling a **public static `hello()`** method, so `Method.invoke(null)` is valid. Calling a static method is an active use; if the class has not yet been initialized, the JVM runs its static initializer block before the method body executes. For an instance method, you must create a valid object and pass the instance instead of `null`.

If you only need to obtain the `Class<?>` object without triggering initialization, `loader.loadClass(name)` usually serves that purpose. By contrast, `Class.forName(name, true, loader)` **explicitly requests initialization**, unlike `Class.forName(name, false, loader)`.

### Loading Resources via URLClassLoader

URLClassLoader can also locate resources on the same search path:

~~~java
URL configUrl = loader.getResource("sample/message.txt");
InputStream in = loader.getResourceAsStream("sample/message.txt");
~~~

Resource names in `ClassLoader` start **from the resource root** and use `/`; do not add a leading `/` like the absolute path style of `Class.getResource`. If not found, the API may return `null`.

Reading data via a stream works similarly whether the resource resides as a file in a directory or as an entry inside a JAR. In particular, do not force a `jar:file:...!/sample/message.txt` URL into a `java.io.File` on disk.

## 5. Hands-On Java 17+: The Same Plugin in a Directory and a JAR

The hands-on exercise has **two Java source files** in two separate parts: the plugin is compiled into `out/plugin`, and the host is compiled into `out/host`. The plugin is then packaged into `dist/plugin.jar`. The host runs with only `out/host` on the application classpath, so the plugin can only be found by the URLClassLoader created by the host.

Working structure:

~~~text
example/
├── src/
│   ├── plugin/
│   │   └── sample/Greeting.java
│   └── host/
│       └── PluginHost.java
├── out/
│   ├── plugin/          <-- created after compilation
│   └── host/            <-- created after compilation
└── dist/
    └── plugin.jar       <-- created after packaging
~~~

### File `src/plugin/sample/Greeting.java`

~~~java
package sample;

public class Greeting {
    static {
        System.out.println("Greeting initialized");
    }

    public static String hello() {
        return "hello from plugin";
    }
}
~~~

The message in the static block lets you observe that each class is **initialized once per specific class definition**. When two loaders define the same name, each version of `sample.Greeting` has its own initialization process.

### File `src/host/PluginHost.java`

~~~java
import java.io.InputStream;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;

public class PluginHost {
    private static void inspect(String label, URL url) throws Exception {
        try (URLClassLoader loader = new URLClassLoader(
                new URL[]{url}, PluginHost.class.getClassLoader())) {
            Class<?> type = loader.loadClass("sample.Greeting");

            System.out.println(label + " owns class: "
                    + (type.getClassLoader() == loader));
            System.out.println(label + " message: "
                    + type.getMethod("hello").invoke(null));

            try (InputStream in =
                         loader.getResourceAsStream("sample/message.txt")) {
                if (in == null) {
                    throw new IllegalStateException("missing resource");
                }
                System.out.println(label + " resource: "
                        + new String(in.readAllBytes(),
                                StandardCharsets.UTF_8).trim());
            }
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException("dir jar");
        }

        URL dir = Path.of(args[0]).toAbsolutePath()
                .normalize().toUri().toURL();
        URL jar = Path.of(args[1]).toAbsolutePath()
                .normalize().toUri().toURL();

        System.out.println("directory URL ends in /: "
                + dir.toExternalForm().endsWith("/"));
        System.out.println("JAR URL ends in .jar: "
                + jar.toExternalForm().endsWith(".jar"));

        inspect("directory", dir);
        inspect("JAR", jar);
    }
}
~~~

Learning points in the code:

1. `Path.of(args[0]).toAbsolutePath().normalize().toUri().toURL()` creates a URL from the passed directory path.
2. `Path.of(args[1])...toURL()` creates a URL from the passed JAR path.
3. Each call to `inspect` creates **a new URLClassLoader**, with `PluginHost`'s loader as its parent and only a single URL source.
4. `loader.loadClass("sample.Greeting")` searches for the class in the parent first; in this example, the parent does not have the plugin, so the child defines it.
5. `type.getClassLoader() == loader` verifies the actual defining loader.
6. Reflection `type.getMethod("hello").invoke(null)` triggers static initialization if needed, then invokes the method and returns the string.
7. `getResourceAsStream("sample/message.txt")` locates the text file from both sources. The code handles `null` and closes the stream.
8. `try (URLClassLoader loader = ...)` guarantees that `close()` is called upon exiting the block, even if an exception occurs.

### Compiling and Running on Linux/macOS

From inside the `example` directory (with the two Java sources above already created):

~~~bash
mkdir -p out/plugin/sample out/host dist

javac -d out/plugin src/plugin/sample/Greeting.java
printf 'resource from plugin\n' > out/plugin/sample/message.txt

javac -d out/host src/host/PluginHost.java
jar --create --file dist/plugin.jar -C out/plugin .

java -cp out/host PluginHost out/plugin dist/plugin.jar
~~~

**Important:** pass only `out/host` via `-cp` at runtime. Do not add `out/plugin` or `dist/plugin.jar` to the application classpath; if added, the parent could see the plugin first and the example would no longer demonstrate that the child defines the class.

### Compiling and Running on Windows PowerShell

From inside the `example` directory:

~~~powershell
New-Item -ItemType Directory -Force out\plugin\sample, out\host, dist | Out-Null

javac -d out\plugin src\plugin\sample\Greeting.java
Set-Content -Path out\plugin\sample\message.txt -Value "resource from plugin" -Encoding Ascii

javac -d out\host src\host\PluginHost.java
jar --create --file dist\plugin.jar -C out\plugin .

java -cp out\host PluginHost out\plugin dist\plugin.jar
~~~

On Windows, `Path.toUri().toURL()` handles drive paths, spaces, and URI characters appropriately; you do not need to manually build a URL string by concatenating `file:///C:/...`. In this example, the resource contains only ASCII characters so that the output is identical across shells.

### Verified Stdout

~~~text
directory URL ends in /: true
JAR URL ends in .jar: true
directory owns class: true
Greeting initialized
directory message: hello from plugin
directory resource: resource from plugin
JAR owns class: true
Greeting initialized
JAR message: hello from plugin
JAR resource: resource from plugin
~~~

The program above was compiled and run successfully with the JDK on Windows using the exact directory/JAR structure described.

### Explanation of the Results

- `directory URL ends in /: true`: `Path.toUri()` on an existing directory produces a directory URL ending in `/`.
- `JAR URL ends in .jar: true`: the second argument points to the `plugin.jar` file itself.
- `directory owns class: true` and `JAR owns class: true`: each URLClassLoader **defines** its own `sample.Greeting` from the corresponding source.
- `Greeting initialized` appears **twice** because there are **two class definitions in two different loaders**, not because the JVM “re-initialized the same class”.
- `directory/JAR message` has the same content because both sources contain the same plugin bytecode.
- `directory/JAR resource` are identical because the `sample/message.txt` resource was copied into the root of the plugin directory and then packaged into the JAR.

The condition for the output to be correct is that **the files and URLs are properly prepared**. If the JAR only contains `Greeting.class` and is missing `message.txt`, the program will throw `IllegalStateException("missing resource")` during the JAR reading step.

## 6. When You Need to Load Multiple JARs or Combine Directories and JARs

Passing multiple URLs at once is the straightforward approach:

~~~java
URL[] sources = {
    Path.of("out/plugin").toAbsolutePath().toUri().toURL(),
    Path.of("lib/dependency-a.jar").toAbsolutePath().toUri().toURL(),
    Path.of("lib/dependency-b.jar").toAbsolutePath().toUri().toURL()
};

try (URLClassLoader loader =
             new URLClassLoader(sources, PluginHost.class.getClassLoader())) {
    Class<?> plugin = loader.loadClass("sample.Greeting");
    // Use the plugin here.
}
~~~

This snippet is **illustrative code for a context where all required files exist**; it will not run standalone without creating the two dependency JARs. According to the API, the loader searches the URLs **in the order provided after the parent has been consulted**. If two URLs both contain the same binary name, the first class found according to the lookup policy determines which definition is used. Avoid having two versions of the same class name to prevent unpredictable runtime errors.

A common mistake is passing only `plugin.jar` in the URLs while forgetting the JARs that contain the plugin's dependencies. `URLClassLoader` does not automatically scan the directory containing a JAR to hunt for dependencies; you need to list the dependency URLs, use an appropriate manifest mechanism, or configure the loader accordingly.

### JAR Manifest Class-Path

A JAR can declare a `Class-Path` attribute in its manifest to reference other JARs using relative URLs, according to the JAR specification. This can affect dependency lookup, but do not treat it as an absolute substitute for an explicitly managed dependency list: you must verify the actual JAR files, path relationships, packaging, and how the class loader uses the manifest.

### JARs Nested Inside a JAR

A path such as `plugin.jar!/BOOT-INF/lib/dependency.jar` is **not automatically** handled like an ordinary JAR file when only `file:/.../plugin.jar` is passed to a standard URLClassLoader. Some frameworks have their own launcher/class loader that supports nested JARs; that is an additional mechanism, not a guaranteed default of `URLClassLoader`.

## 7. Closing URLClassLoader Properly and the Limits of close()

`URLClassLoader` implements `Closeable`, so you should use *try-with-resources* to release I/O resources associated with JARs and URLs:

~~~java
try (URLClassLoader loader = new URLClassLoader(
        new URL[]{jarUrl}, parentLoader)) {
    Class<?> clazz = loader.loadClass("sample.Greeting");
    // Work with clazz and resources while the loader is still open.
}
~~~

Important points:

- `close()` closes the JAR files opened by the loader and stops the loader from being used to load **new classes or resources defined by the loader itself**.
- `close()` does **not destroy** already-created `Class<?>` objects or instances, nor does it automatically evict all live plugin objects from memory.
- **Class unloading** can only occur when the JVM decides to perform it and when no references remain that prevent the loader and its associated classes from being garbage-collected. References from static fields, running threads, thread context loaders, thread-locals, callbacks/registries, or plugin objects can all keep the loader alive.
- If you have obtained an `InputStream` from a resource, **close the stream separately**. If you close the loader while still reading a resource, subsequent read behavior may no longer be reliable; the API documentation also warns that streams must be closed appropriately.
- Closing a loader after finishing with a plugin is not equivalent to “immediately reloading a new version”. To get a new namespace, you typically need to create a **new loader**, avoid retaining references to old classes/objects, and coordinate the lifecycle properly.
- `close()` can throw `IOException`; try-with-resources handles calling close even when the block throws an error, and the exception must still be propagated/handled appropriately.

Do **not** hold a `URLClassLoader` in a global static variable indefinitely if the intended design is session-based plugin loading/unloading. Conversely, do not close the loader too early if lazy loading or resource lookup will still be needed later.

## 8. Class Identity, Shared APIs, and Parent-First

The runtime identity of a regular Java class/interface is tied to its **binary name + defining class loader**. Therefore:

~~~text
Parent loader: app.PluginApi
     |
     +---- child A: sample.Greeting (version A)
     |
     +---- child B: sample.Greeting (version B)
~~~

If both child A and child B define `sample.Greeting` themselves, they create two distinct types even though their binary names are identical. Casting an object from one version to the other loader's class version can cause a `ClassCastException` or linkage errors. Do not rely on class name strings to conclude that two `Class<?>` objects are equal.

For the host to work with plugins more safely, place the shared contract interface in the **parent**:

~~~java
package api;

public interface Plugin {
    String execute();
}
~~~

In the plugin JAR:

~~~java
package plugin;

import api.Plugin;

public class Impl implements Plugin {
    @Override
    public String execute() {
        return "plugin result";
    }
}
~~~

These are **two separate illustrative Java files**, not part of the runnable program in Section 5. Once `api.Plugin` is defined by the parent, the child can ask the parent for the same interface; the host loads `plugin.Impl` with a URLClassLoader and casts it to `api.Plugin`. Do not bundle a separate copy of `api.Plugin` under a child-first policy, so as to avoid type identity conflicts.

A reflection pattern while the loader is open:

~~~java
Class<?> implType = loader.loadClass("plugin.Impl");
api.Plugin plugin = (api.Plugin)
        implType.getDeclaredConstructor().newInstance();
String result = plugin.execute();
~~~

Conditions: `api.Plugin` resides in the parent, the plugin is compiled against the same API, the corresponding constructor is accessible, and there are no module/security/accessibility conflicts. This is a standalone example of an API contract, not a required part of the previous `PluginHost` program.

## 9. Common Errors and How to Diagnose Them

| Error / Symptom | Common Cause | How to Check |
| --- | --- | --- |
| `ClassNotFoundException: sample.Greeting` when passing a directory | The URL mistakenly points to `out/plugin/sample/` instead of the root `out/plugin/`; or the package/class name does not match. | Check whether `sample/Greeting.class` is directly beneath the directory root. |
| `ClassNotFoundException` when using a directory file URL | Missing trailing `/`, causing the `file:` URL to be interpreted as not a directory. | Build the URL using `Path.of(existingDirectory).toUri().toURL()`. |
| `ClassNotFoundException` when loading a JAR | The URL points to the wrong file; the JAR does not contain the right entry; the class has a different binary name. | Run `jar tf dist/plugin.jar` and verify `sample/Greeting.class`. |
| `NoClassDefFoundError` when the plugin uses a dependency | The dependency is absent from both the parent and the child's URL list; or a related class failed in another step. | Inspect the cause and the JAR containing the needed class; add the correct dependency URL. |
| `ClassCastException` even though both classes have the same name | There are two different defining loaders or a duplicated shared API. | Log `clazz.getClassLoader()` and verify that the interface is in the parent. |
| `Plugin defined by child == false` | The parent saw the class name first because the host classpath contains the plugin. | Do not include the plugin JAR on the application `-cp` if you want the child to define it. |
| Resource via `getResourceAsStream` is `null` | The file was not copied into the root URL/JAR, or the resource name has an inappropriate leading `/`. | Check the entry and use a root-relative name like `sample/message.txt`. |
| `ClassFormatError` / `UnsupportedClassVersionError` | Malformed bytecode or built with too new a Java target. | Check `javac --release` and the runtime JDK version. |
| `NoSuchMethodError` after the class loads | The runtime dependency version differs from compile time; duplicate JARs/loaders. | Compare dependencies and loader sources, not just class names. |
| Cannot replace/delete JAR after use on Windows | The loader still holds a file handle to the JAR, or a stream has not been closed. | Close streams and call `URLClassLoader.close()`; check for live references. |
| Classes/objects still work after closing the loader | `close` does not immediately unload already-defined classes. | Understand the GC/loader lifecycle; do not use `close` as a class deletion command. |

### Practical Debugging

1. Print the URLs the loader is using via `loader.getURLs()` to confirm that directories have a trailing slash and JARs point to the right file.
2. Print `type.getName()` and `type.getClassLoader()` to learn the binary name and defining loader, rather than inferring from the loader that was called.
3. Use `jar tf plugin.jar` to inspect entries; do not pass `sample/Greeting.class` to `loadClass`.
4. Check whether the runtime application `-cp` accidentally includes the plugin/dependencies. If so, parent-first may pick up the parent's class.
5. Distinguish `ClassNotFoundException` during lookup by name from `NoClassDefFoundError` when the JVM resolves a missing dependency and `ExceptionInInitializerError` when an initializer fails.
6. If the host loads the plugin successfully but a class used inside the plugin fails, look for the dependency in sources visible to the **plugin's defining loader**, not only in the directory containing the original JAR.
7. Check reflection access permissions, method names, constructors, and module/package openness; loading a class successfully does not guarantee that reflection calls will succeed.

## 10. Things URLClassLoader Does Not Do Automatically

- **Does not create a JPMS ModuleLayer:** passing a JAR to URLClassLoader is not equivalent to resolving named modules via `--module-path` or building a module graph.
- **Does not resolve Maven/Gradle-style dependencies:** it searches for bytecode/resources within the provided URLs (and appropriate extension mechanisms) rather than automatically downloading transitive dependencies from a repository.
- **Does not support launcher-style wildcards in the URL array:** you must create a URL for each JAR or have the application enumerate the files before instantiating the loader.
- **Does not guarantee security isolation:** a custom class loader or parent-child class loading **is not a sandbox** for untrusted plugins. Only use trusted plugins; verify sources, checksums/signatures, and process permissions as appropriate.
- **Does not guarantee reloading by modifying the JAR file in place:** for a live loader, already-defined classes do not have their bytecode replaced within the same definition. You typically need to build a new loader and terminate the old loader's lifecycle.
- **Does not guarantee every URL can be loaded safely:** network URLs can be slow/unavailable and open up the risk of fetching untrusted code. This learning example intentionally uses local files and predetermined paths.

## 11. Checklist to Remember

When creating a URLClassLoader from a directory/JAR, check these items in order:

1. What is the **binary name** of the class to load? Is it at the exact `package/Class.class` path or corresponding JAR entry?
2. Does the directory URL point to the **package root**, use the `file:` scheme, and end with `/`?
3. Does the JAR URL point to **the JAR file itself**? Does the file contain the entry to load?
4. Do you need to add URLs of dependency JARs? Are you confusing the launcher's `lib/*` syntax with the `URL[]` array?
5. What is the parent loader? Does it contain the shared API, or a duplicate plugin with the same name that would change the defining loader?
6. Did you call `loadClass("sample.Greeting")` with a dot-separated package name rather than a file path?
7. Do you need to **initialize** the class or only load its metadata? `loadClass` does not replace `Class.forName(..., true, loader)`.
8. Do you need to read a resource? Use `loader.getResourceAsStream("sample/message.txt")` and check for `null`.
9. Have streams and the loader been closed at the proper point in the lifecycle? Are any references being held that prevent class unloading?
10. Are you assuming URLClassLoader is a module loader, dependency manager, or security sandbox? If so, a different appropriate design is needed.

### Self-Check Questions

**Question 1.** To load `com.example.Plugin` from `plugins/classes/com/example/Plugin.class`, where must the directory URL point?

**Answer:** `plugins/classes/`, not `plugins/classes/com/example/`; use `Path.of("plugins/classes").toUri().toURL()` once the directory exists.

**Question 2.** For `plugins/plugin.jar` containing `com/example/Plugin.class`, what URL should be passed?

**Answer:** The URL of **the JAR file**, such as `Path.of("plugins/plugin.jar").toUri().toURL()`; there is no need to manually write `jar:file:...!/com/example/Plugin.class` as the URL search root.

**Question 3.** `loader.loadClass(name)` returns a class with `getClassLoader() != loader`. Does that mean the URL is definitely wrong?

**Answer:** No. Parent-first may return a class defined by the parent. Check the parent classpath and the defining loader.

**Question 4.** Two separate loaders both load `sample.Greeting` from the same bytecode and call its static method. Why does the static block run twice?

**Answer:** They define two separate runtime classes according to the binary name + defining loader pair; each class has its own initialization state.

**Question 5.** Once `URLClassLoader` is closed, can you assume the plugin classes and objects have definitely been unloaded?

**Answer:** No. `close()` releases I/O resources and prevents new loading from the loader; unloading depends on reference lifetimes and GC/JVM decisions.

## Official References

- [Java SE 21 – URLClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html): constructors, directory/JAR URLs, delegation, `getURLs`, `close()`.
- [Java SE 21 – ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, parent-first, resource lookup, and defining loader.
- [Java SE 21 – Path.toUri()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Path.html#toUri()): URI from a filesystem path.
- [JVMS Java SE 21 §5.3 – Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3): class identity and class loaders in the JVM.
