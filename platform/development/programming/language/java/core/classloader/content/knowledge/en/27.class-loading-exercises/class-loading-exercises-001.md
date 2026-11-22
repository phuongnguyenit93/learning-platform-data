# Printing the Loader Tree and Class Origins in a Small Application

## 1. What Questions Does This Exercise Address?

Once the JVM is running a Java application, looking only at package names or the classpath is not enough to know **which ClassLoader actually defines each class**. Especially when an application has plugin JARs, multiple class loaders, or a repeatedly packaged library, common questions are:

- Which loader defines **java.lang.String**?
- Does the **Main** program class come from the application/system loader or the plugin loader?
- Which defining loader does a class present only in **plugin.jar** have?
- What does the **parent** relationship tree of a custom loader look like?
- If both the parent and the plugin contain **sample.host.HostApi**, which version does the JVM select?
- Can the **CodeSource** and resource URL of a class be determined from a JAR or from a directory?
- Why can two loaders using the same binary name create two **different Class objects**?
- Does printing the loader tree mean seeing the entire delegation/module graph?

This exercise builds a **Java 17+** application with the host in the **host-out** directory, the plugin in **plugin.jar**, and two **URLClassLoaders**, and then prints the evidence at runtime. The code has been compiled and run on **OpenJDK 21** with the commands listed below; the application uses only the Java standard library.

**Most important goal:** separate three kinds of information: **(1) class identity/defining loader; (2) loader parent relationships; (3) artifact/code source origin or resource URL**. They are related, but cannot be used interchangeably.

## 2. Different Observations When Printing the Loader Tree

This exercise must distinguish **class identity**, the **parent tree**, and the **source of bytes**. An ordinary class is identified by **(binary name, defining loader)**, so two `URLClassLoader` instances that actually define `sample.plugin.Greeter` will have two distinct `Class<?>` objects; whereas two loaders delegating to the same parent can return exactly **one** `Class<?>`.

| Observation | API | What should not be inferred |
| --- | --- | --- |
| Who defines the class? | `clazz.getClassLoader()` | The loader on which `loadClass()` was called is necessarily the defining loader |
| Who is the loader's parent? | `loader.getParent()` | This is a list of all live loaders or the entire JPMS graph |
| What origin is recorded? | `clazz.getProtectionDomain().getCodeSource()` | The URL is cryptographic proof or every class has a CodeSource |
| Where is the resource located? | `clazz.getResource(...)` / `loader.getResources(...)` | The resource existing means the class has already been loaded by the JVM |
| Which module does the class belong to? | `clazz.getModule()` | Module identity and defining loader are the same concept |

In common HotSpot/OpenJDK builds, the parent tree starts at the application loader, goes to the platform loader, and then to the bootstrap loader (typically represented as `null`). `String.class.getClassLoader() == null` because String is defined by the bootstrap loader, **not a class loading error**. Some platform classes have a defining loader other than bootstrap; specific results depend on the runtime/JDK.

We must distinguish the **initiating loader** (the loader that initiates the request, which may delegate) from the **defining loader** (the loader that actually owns the class). `Class.getClassLoader()` only tells you the defining loader, not the list of all initiating loaders. The program will compare object identity, artifact origin, parent chain, and module instead of relying on class names or the loader's `toString()` string.

## 3. Expected Outcome of the Exercise

We will build:

~~~text
Host application:
  host-out/
    sample/app/InspectLoaders.class
    sample/app/IsolatedLoaderDemo.class
    sample/host/HostApi.class
          |
          +-- HostApi.origin() -> "host"

Plugin artifact:
  plugin.jar
    sample/plugin/Greeter.class
    sample/host/HostApi.class
          |
          +-- the HostApi version packaged inside the plugin
          +-- HostApi.origin() -> "plugin-shadow"
~~~

**There are intentionally two versions of HostApi** to observe parent delegation; this is an exercise fixture, not a plugin architecture that should be applied by default. When the plugin loader has the **application loader as its parent**, the HostApi call will pick the host version first. When an isolated loader has the **platform loader as its parent**, it cannot see host-out via its parent chain and will pick the version packaged in plugin.jar.

The two cases with the same class name but different defining loaders will produce different results.

## 4. Creating the Project

Complete source structure:

~~~text
loader-tree-lab/
├── src/
│   └── sample/
│       ├── app/
│       │   ├── InspectLoaders.java
│       │   └── IsolatedLoaderDemo.java
│       └── host/
│           └── HostApi.java
├── plugin-src/
│   └── sample/
│       ├── host/
│       │   └── HostApi.java
│       └── plugin/
│           └── Greeter.java
├── host-out/       (generated after javac)
├── plugin-out/     (generated after javac)
└── plugin.jar      (generated after jar)
~~~

**Run all commands from the loader-tree-lab directory**. Do not mix host-out or plugin.jar into a source folder and expect parent delegation to automatically pick the right one; the output paths here are deliberately separated for verification.

### 4.1 Host Version of the API

**src/sample/host/HostApi.java**:

~~~java
package sample.host;

public final class HostApi {
    private HostApi() {
    }

    public static String origin() {
        return "host";
    }
}
~~~

At runtime, this class will come from the **host-out** directory on the application's classpath.

### 4.2 Plugin Version of the API Used as a Shadow Test

**plugin-src/sample/host/HostApi.java**:

~~~java
package sample.host;

public final class HostApi {
    private HostApi() {
    }

    public static String origin() {
        return "plugin-shadow";
    }
}
~~~

This is **a class with the same binary name sample.host.HostApi** but a different body. We compile it into **plugin-out** and package it into plugin.jar. It lets us directly observe which version the loader selected via the result of **origin()**.

**Warning:** Packaging two copies of a shared API in both the host and a plugin in production easily causes a type identity mismatch. The duplicate copy here is solely for diagnostic purposes.

### 4.3 Plugin Class

**plugin-src/sample/plugin/Greeter.java**:

~~~java
package sample.plugin;

import sample.host.HostApi;

public final class Greeter {
    static {
        System.out.println("plugin initialized");
    }

    public String greet() {
        return "hello from " + HostApi.origin();
    }
}
~~~

Greeter depends on HostApi. It also has a static initializer to demonstrate that **loadClass does not automatically trigger class initialization**, whereas reflective instance creation does.

**Important compilation note:** Greeter is compiled against the host's HostApi, but when the JVM loads the **binary name sample.host.HostApi** at runtime, loader resolution and parent delegation determine which Class is used in a given case. Because both versions of HostApi have the same public method signature, the demo can invoke the method without encountering NoSuchMethodError. If the API schemas differed, that would be a separate kind of error requiring its own investigation.

## 5. Main Program: Printing the Loader Tree and Each Class's Origin

Create **src/sample/app/InspectLoaders.java** with the full contents:

~~~java
package sample.app;

import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.security.CodeSource;
import java.security.ProtectionDomain;
import java.sql.DriverManager;
import java.util.Enumeration;

public final class InspectLoaders {
    private static String role(
            ClassLoader loader, ClassLoader plugin) {
        if (loader == null) {
            return "bootstrap";
        }
        if (loader == plugin) {
            return "plugin-loader";
        }
        if (loader == ClassLoader.getSystemClassLoader()) {
            return "application";
        }
        if (loader == ClassLoader.getPlatformClassLoader()) {
            return "platform";
        }
        return "other";
    }

    private static void tree(
            ClassLoader loader, ClassLoader plugin) {
        System.out.println("Loader ancestry:");

        int depth = 0;
        while (true) {
            System.out.println("  ".repeat(depth)
                    + role(loader, plugin));

            if (loader == null) {
                break;
            }

            loader = loader.getParent();
            depth++;
        }
    }

    private static String source(
            Class<?> c, Path host, Path jar) throws Exception {
        ProtectionDomain pd = c.getProtectionDomain();
        CodeSource cs =
                pd == null ? null : pd.getCodeSource();

        URL url = cs == null ? null : cs.getLocation();

        if (url == null) {
            return "unavailable";
        }

        // The fixture uses file: URLs from a directory or a JAR.
        Path actual = Path.of(url.toURI()).toRealPath();

        if (actual.equals(host.toRealPath())) {
            return "host-out";
        }
        if (actual.equals(jar.toRealPath())) {
            return "plugin.jar";
        }
        return "other";
    }

    public static void main(String[] args)
            throws Exception {

        Path host = Path.of("host-out");
        Path jar = Path.of("plugin.jar");
        URL jarUrl = jar.toUri().toURL();

        ClassLoader app =
                ClassLoader.getSystemClassLoader();

        try (URLClassLoader plugin =
                    new URLClassLoader(
                            "plugin-loader",
                            new URL[]{jarUrl},
                            app);
             URLClassLoader plugin2 =
                    new URLClassLoader(
                            "plugin-loader-2",
                            new URL[]{jarUrl},
                            app)) {

            tree(plugin, plugin);

            System.out.println("String loader = "
                    + role(String.class.getClassLoader(),
                           plugin));

            System.out.println("DriverManager loader = "
                    + role(DriverManager.class.getClassLoader(),
                           plugin));

            System.out.println("HostApi loader = "
                    + role(sample.host.HostApi.class
                            .getClassLoader(), plugin));

            Class<?> type =
                    plugin.loadClass("sample.plugin.Greeter");

            System.out.println("Greeter loader = "
                    + role(type.getClassLoader(), plugin));

            System.out.println("Greeter source = "
                    + source(type, host, jar));

            System.out.println("HostApi source = "
                    + source(sample.host.HostApi.class,
                             host, jar));

            Class<?> shared =
                    plugin.loadClass("sample.host.HostApi");

            System.out.println("shadow selected = "
                    + (shared == sample.host.HostApi.class));

            System.out.println("Greeter named module = "
                    + type.getModule().isNamed());

            System.out.println("String module = "
                    + String.class.getModule().getName());

            System.out.println("plugin class resource scheme = "
                    + type.getResource("Greeter.class")
                            .getProtocol());

            Enumeration<URL> paths = plugin.getResources(
                    "sample/host/HostApi.class");

            int n = 0;
            while (paths.hasMoreElements()) {
                paths.nextElement();
                n++;
            }

            System.out.println("shadow resource count = " + n);

            Class<?> again =
                    plugin.loadClass("sample.plugin.Greeter");

            System.out.println("same loader cache = "
                    + (type == again));

            Class<?> parallel =
                    plugin2.loadClass("sample.plugin.Greeter");

            System.out.println("second loader same Class = "
                    + (type == parallel));

            System.out.println("before instance");

            Object obj =
                    type.getConstructor().newInstance();

            System.out.println("greeting = "
                    + type.getMethod("greet").invoke(obj));
        }
    }
}
~~~

This is a **complete standalone program** in the sample.app package. The methods are separated for clarity during debugging.

### 5.1 Why Does role() Compare Object Identity?

The code uses:

~~~java
if (loader == ClassLoader.getSystemClassLoader()) {
    return "application";
}
~~~

instead of comparing **loader.toString()** or **loader.getClass().getName()**. The implementation names and identity hashes of built-in loaders often vary across JVMs and versions; **object identity comparison** is more reliable for determining whether a loader is the exact system/platform object within the current process.

**role() only generates labels for the demo.** If the runtime uses another custom loader, it may print **other**, which does not mean the class is broken. For a production diagnostic tool, you should also print **ClassLoader.getName()**, the implementation type, and a stable instance identifier within the same process.

### 5.2 Why Use the tree() Loop?

~~~java
ClassLoader current = plugin;

while (true) {
    // Print current.
    if (current == null) {
        break;
    }
    current = current.getParent();
}
~~~

This is an illustrative snippet, not a complete method. It traverses the **parent chain** up to null. For a valid loader hierarchy, the parent chain is finite.

**Do not invent a fake Java BootstrapClassLoader object.** Null is a useful representation in the API results of platform JVMs such as HotSpot.

If you need a general-purpose tool for many custom loaders, you can cap the depth and add cycle detection in case a custom representation does not match assumptions. However, a ClassLoader's parent relationship is established when the constructor runs; it is normally not a graph that users mutate to create cycles.

### 5.3 getParent() Differs from loadClass()

**getParent()** only returns information about the loader relationship; it **does not call loadClass()** or load a class. Reading the loader tree does not automatically initialize Greeter.

By default, **ClassLoader.loadClass(name)** checks whether the class is already loaded, asks the parent first, and then calls findClass if the parent does not find it. Custom loaders can override this policy, so having the same parent tree **is not enough to guarantee the same lookup behavior**.

### 5.4 Where Does CodeSource Come From?

The **source(c, host, jar)** method uses:

~~~java
ProtectionDomain pd = c.getProtectionDomain();
CodeSource cs = pd == null ? null : pd.getCodeSource();
URL url = cs == null ? null : cs.getLocation();
~~~

These statements are a snippet from the method.

**CodeSource.getLocation()** can point to a classes directory or a JAR file. In the demo:

- HostApi from **host-out/** → CodeSource location corresponds to the host-out directory.
- Greeter read by URLClassLoader from **plugin.jar** → location is a file URL pointing to plugin.jar.

**CodeSource or location can be null**, especially for bootstrap/JDK classes, self-defined bytes/custom code domains, or security/runtime contexts. Therefore, you must not call **.getLocation().toString()** without a null-check.

The demo method uses **Path.of(url.toURI()).toRealPath()** because it knows in advance that the two valid sources are **file:** paths. This is **not a general-purpose URL converter**: URLs with the **jrt:, jar:, http:** protocol or a custom handler may not convert directly to a Path.

### 5.5 Why Is a Resource URL Different from CodeSource?

There are two different questions:

~~~java
type.getProtectionDomain()
        .getCodeSource().getLocation();
~~~

and:

~~~java
type.getResource("Greeter.class");
~~~

The first asks for **the class's code source location** recorded by the protection domain. For a URLClassLoader reading from a JAR, this is typically **file:/.../plugin.jar**.

The second looks up **the resource corresponding to the class file**; for a class inside a JAR, the URL typically has the form:

~~~text
jar:file:/.../plugin.jar!/sample/plugin/Greeter.class
~~~

It contains the entry path inside the JAR and has **protocol = jar**. The actual address depends on the filesystem path, so the program only prints the protocol to keep the output reproducible.

**Note:** Class.getResource and ClassLoader.getResource do not follow identical path resolution rules: **Class.getResource("Greeter.class")** resolves relative to the class's package; **ClassLoader.getResource("sample/plugin/Greeter.class")** uses an absolute resource name with slashes between segments, **without starting with /**.

### 5.6 Why Call getResources Instead of Only getResource?

The program calls:

~~~java
plugin.getResources("sample/host/HostApi.class")
~~~

and counts **2** resource URLs: one from **host-out**, and one from **plugin.jar**. This indicates *that there are two resources at the same path*, not that the JVM has defined two HostApi Classes in the same loader.

**getResource** usually follows a parent-first policy: the parent resource can win. **getResources** can enumerate multiple URLs; in real-world applications you also need to consider duplicate entries, module encapsulation, custom resource delegation, and the launcher environment.

**Do not conclude that “resource count = 2” means “Class count = 2”.** Class identity is only established when the JVM defines a Class per loader, not simply because a JAR contains a matching entry.

## 6. Compiling and Packaging

From the **loader-tree-lab** directory, after creating all the source files above, run:

~~~bash
javac --release 17 -d host-out   src/sample/host/HostApi.java   src/sample/app/InspectLoaders.java

javac --release 17 -cp host-out -d plugin-out   plugin-src/sample/plugin/Greeter.java

javac --release 17 -d plugin-out   plugin-src/sample/host/HostApi.java

jar --create --file plugin.jar -C plugin-out .

java -cp host-out sample.app.InspectLoaders
~~~

These are multi-line commands using **backslash** line continuation suitable for bash on Linux/macOS. For Windows PowerShell, use one line per command:

~~~powershell
javac --release 17 -d host-out src/sample/host/HostApi.java src/sample/app/InspectLoaders.java
javac --release 17 -cp host-out -d plugin-out plugin-src/sample/plugin/Greeter.java
javac --release 17 -d plugin-out plugin-src/sample/host/HostApi.java
jar --create --file plugin.jar -C plugin-out .
java -cp host-out sample.app.InspectLoaders
~~~

**Why compile Greeter before the plugin's HostApi version?** So that it is compiled against the host's API via **-cp host-out**. Then we add the other HostApi version into plugin-out and package it. The compiler records a symbolic reference to **sample.host.HostApi**, while the defining loader of HostApi is selected by the JVM at runtime.

**Important classpath note:** Only include **host-out** on the application classpath when running the program. Do not add **plugin.jar** to the application classpath in the main demo command; if you add it, the application parent can load Greeter itself first and the ownership test changes.

**Why use --release 17?** This is a Java 17+ program; using --release 17 keeps the bytecode/class-file target compatible with Java 17 even when compiled with JDK 21. The **URLClassLoader(String name, URL[] urls, ClassLoader parent)** constructor has existed since Java 9, so it is valid.

## 7. Actual Output and Line-by-Line Explanation

Here is the **stdout verified on OpenJDK 21** with the source tree and commands above:

~~~text
Loader ancestry:
plugin-loader
  application
    platform
      bootstrap
String loader = bootstrap
DriverManager loader = platform
HostApi loader = application
Greeter loader = plugin-loader
Greeter source = plugin.jar
HostApi source = host-out
shadow selected = true
Greeter named module = false
String module = java.base
plugin class resource scheme = jar
shadow resource count = 2
same loader cache = true
second loader same Class = false
before instance
plugin initialized
greeting = hello from host
~~~

### 7.1 First Lines: the Loader Tree

~~~text
plugin-loader
  application
    platform
      bootstrap
~~~

Meaning:

- The plugin URLClassLoader has the **application/system loader as its parent**.
- The system loader has the **platform loader as its parent** in the test environment.
- The platform loader has a parent represented by **null/bootstrap**.
- The indentation is just the code **"  ".repeat(depth)**, not a built-in tree-drawing feature of the JVM.

**These are not all the loaders currently existing in the JVM.** The program only prints the parent chain starting from **plugin**, without scanning other loaders created by the JVM/framework.

### 7.2 String and DriverManager

~~~text
String loader = bootstrap
DriverManager loader = platform
~~~

**java.lang.String** is among the core platform classes defined by the bootstrap loader on OpenJDK. **java.sql.DriverManager** is defined by the platform loader in the test JVM, giving an example of a non-bootstrap platform class.

Another JVM may not have the exact same detailed mapping; do not write a portable assertion like “every JDK must have DriverManager's loader be platform” unless the runtime environment is controlled and verified.

### 7.3 HostApi Belongs to application

~~~text
HostApi loader = application
HostApi source = host-out
~~~

**HostApi.class** is compiled and loaded from **host-out** by the application loader. This is the **Class object used by the host to reference the shared API**.

In the demo, the application loader instance is the parent of plugin, so when plugin requests this name, the parent already sees the class.

### 7.4 Greeter Belongs to plugin.jar

~~~text
Greeter loader = plugin-loader
Greeter source = plugin.jar
~~~

The application parent does not have **sample.plugin.Greeter**, because plugin.jar is not on the application classpath. The plugin URLClassLoader searches for the class in its single URL, plugin.jar, and defines Greeter itself.

**getClassLoader() and CodeSource complement each other:**

- getClassLoader tells you **who defines it**.
- CodeSource tells you **the recorded artifact source**.
- The roles of the two APIs cannot be swapped; two different loaders can read the same JAR and create two different Class objects.

### 7.5 The Plugin Has a Duplicate HostApi, but It Is Not Selected

~~~text
shadow selected = true
greeting = hello from host
~~~

Here **shadow selected** is the printed name checking whether **plugin.loadClass("sample.host.HostApi")** returns the host's exact HostApi Class. A value of **true** means **the parent/host wins**, not plugin-shadow.

The line **greeting = hello from host** proves that Greeter's code called the host's HostApi implementation. The **plugin-shadow** version resides in plugin.jar, but is not the class selected for this lookup.

This is **parent-first delegation**, consistent with the default ClassLoader.loadClass behavior. Do not change the message to “plugin-shadow selected = true”, as that would cause learners to interpret the result backward.

### 7.6 Module Information

~~~text
Greeter named module = false
String module = java.base
~~~

Greeter is defined from the JAR via URLClassLoader in the **unnamed module** of the plugin loader, because the demo does not use module-info.java or JPMS ModuleLayer.

String belongs to the **named module java.base**. ClassLoader identity and module membership are two different layers of information: a single loader can define multiple named modules according to the module layer, though in this fixture Greeter is in an unnamed module.

**Class.getModule() does not tell you the JAR filename**. Use CodeSource or a resource URL to investigate the artifact.

### 7.7 A Loader Reuses an Already Loaded Class

~~~text
same loader cache = true
~~~

The two calls to **plugin.loadClass("sample.plugin.Greeter")** return the same Class object. The default ClassLoader.loadClass algorithm checks whether the class is already loaded/initiated and does not call defineClass a second time for the same name.

If a custom loader attempts to define a duplicate class in the same loader, it can throw a **LinkageError**, rather than creating an updated version of the method body.

### 7.8 Two Loaders Reading the Same JAR Create Two Different Classes

~~~text
second loader same Class = false
~~~

**plugin** and **plugin2** both have URLs pointing to the same **plugin.jar**, yet they are **two different URLClassLoader objects**. When each loader defines sample.plugin.Greeter on its own, we get two Class objects with different runtime identities.

When a plugin application needs to cast an object to a shared interface, the interface/DTO should normally come from **a common defining loader**. If plugin2 defines its own copy of an API interface with the same name as the host's, the cast can fail even if the source is identical.

### 7.9 loadClass Does Not Run the Static Initializer Yet

~~~text
before instance
plugin initialized
greeting = hello from host
~~~

The program calls loadClass, inspects Class/CodeSource/Resource, and then prints **before instance**. Only when:

~~~java
type.getConstructor().newInstance();
~~~

is executed does Greeter get initialized, the static block run, and **plugin initialized** get printed.

**Loading does not mean initialization**. The resolve flag in ClassLoader is also not a request to automatically run the class initializer; only active use according to the JLS triggers initialization as appropriate.

## 8. Second Exercise: Same JAR, Different Parent

Goal: change exactly one factor—the **parent loader**—and observe the result. This time the custom URLClassLoader has the **platform loader** as its parent, not the application loader.

Because the platform loader does not see **host-out** in the fixture, the child can define the **sample.host.HostApi** version packaged inside plugin.jar itself.

Create **src/sample/app/IsolatedLoaderDemo.java**:

~~~java
package sample.app;

import java.net.URLClassLoader;
import java.net.URL;
import java.nio.file.Path;
import sample.host.HostApi;

public class IsolatedLoaderDemo {
    public static void main(String[] args) throws Exception {
        URL jar = Path.of("plugin.jar").toUri().toURL();

        try (URLClassLoader isolated =
                new URLClassLoader(
                        "isolated",
                        new URL[]{jar},
                        ClassLoader.getPlatformClassLoader())) {

            Class<?> shadow =
                    isolated.loadClass("sample.host.HostApi");

            Class<?> greeter =
                    isolated.loadClass("sample.plugin.Greeter");

            System.out.println(
                    "host and isolated HostApi same = "
                    + (shadow == HostApi.class));

            System.out.println(
                    "shadow owner is isolated = "
                    + (shadow.getClassLoader() == isolated));

            System.out.println(
                    "greeter owner is isolated = "
                    + (greeter.getClassLoader() == isolated));

            Object g =
                    greeter.getConstructor().newInstance();

            System.out.println(
                    "greeting = "
                    + greeter.getMethod("greet").invoke(g));
        }
    }
}
~~~

Compile/run from the project directory:

~~~bash
javac --release 17 -cp host-out -d host-out   src/sample/app/IsolatedLoaderDemo.java

java -cp host-out sample.app.IsolatedLoaderDemo
~~~

For Windows PowerShell, use a single-line javac command:

~~~powershell
javac --release 17 -cp host-out -d host-out src/sample/app/IsolatedLoaderDemo.java
java -cp host-out sample.app.IsolatedLoaderDemo
~~~

**Stdout when run on OpenJDK 21:**

~~~text
host and isolated HostApi same = false
shadow owner is isolated = true
greeter owner is isolated = true
plugin initialized
greeting = hello from plugin-shadow
~~~

### 8.1 Why Does It Differ from the First Program?

In the first program:

~~~text
PluginLoader -> ApplicationLoader -> Platform -> Bootstrap
                   |
                   +-- knows HostApi from host-out
~~~

In the second program:

~~~text
IsolatedLoader -> Platform -> Bootstrap
      |
      +-- looks up HostApi itself in plugin.jar
~~~

Because the application loader **is not on isolated's parent chain**, the fact that the launcher code uses **HostApi.class** from host-out does not force isolated to pick that Class.

**Class equality = false** reflects two different defining loaders: the application loader and the isolated loader.

**The "plugin-shadow" result** shows that Greeter in isolated uses the HostApi version packaged in plugin.jar.

### 8.2 Do Not Confuse a Platform Parent with a “Full Sandbox”

Choosing platform as the parent helps illustrate class lookup isolation, **not a security sandbox**. The plugin can access whatever Java APIs the runtime/module constraints permit. When running untrusted code, a different isolation model (such as a process/container sandbox) with appropriate permissions is needed.

If a plugin needs to call a host API, switching the parent to platform can make the shared API no longer visible. The second example works because plugin.jar has its own copy of HostApi; in practice this can lead to **ClassCastException/LinkageError** when the host-plugin boundary requires the same Class identity.

## 9. Reading CodeSource Safely in a Real Program

CodeSource is a useful signal, but **it does not always have a URL**.

### 9.1 Helper for Production Code

~~~java
static String codeSourceLocation(Class<?> type) {
    try {
        java.security.ProtectionDomain pd =
                type.getProtectionDomain();

        if (pd == null) {
            return "(no protection domain)";
        }

        java.security.CodeSource cs = pd.getCodeSource();

        if (cs == null || cs.getLocation() == null) {
            return "(no code source URL)";
        }

        return cs.getLocation().toExternalForm();

    } catch (SecurityException denied) {
        return "(access denied)";
    }
}
~~~

This is a **complete method** that can be placed in a helper class, though it does not have its own main method. It does not automatically read or validate the URL contents.

### 9.2 When Might CodeSource Differ from Expectations?

- **Bootstrap/JDK classes:** CodeSource is usually not a normal JAR file URL.
- **Custom ClassLoader using defineClass with a custom ProtectionDomain:** It may have no location, or a location set by the loader.
- **In-memory generated classes, proxies, hidden classes:** A physical source may not exist as a .class file in a directory/JAR that you can point to.
- **Named modules/runtime image:** The location may use **jrt:** or have no source URL in the way you expect.
- **Container/nested JAR/custom URL protocols:** The URL may represent a logical location rather than a simple file Path.
- **Security policy:** Access to ProtectionDomain/CodeSource may be restricted depending on the runtime.

**Do not use CodeSource as a replacement for file verification.** It is metadata associated with the protection domain, not cryptographic proof that the bytes originated from a signed and trusted artifact.

### 9.3 Do Not Print Sensitive Paths to Production Logs

A CodeSource location can contain home directory paths, build workspaces, container mounts, network paths, or internal URLs. In this exercise we normalize it to **host-out/plugin.jar** so stdout stays stable. For production logs, consider access permissions and the level of information permitted to be output.

## 10. Resource Lookup: Seeing a Class File Does Not Mean the Class Is Loaded

Two APIs:

~~~java
ClassLoader loader = Greeter.class.getClassLoader();
java.net.URL url =
        loader.getResource("sample/plugin/Greeter.class");
~~~

This is a non-standalone snippet and requires the Greeter class to be visible at compile time. It looks up a **resource URL**, rather than returning a Class<?>.

**The differences:**

| API | Returns | Meaning |
| --- | --- | --- |
| **clazz.getClassLoader()** | ClassLoader or null | Defining loader of the runtime Class. |
| **clazz.getModule()** | Module | Named/unnamed module of the Class. |
| **clazz.getProtectionDomain().getCodeSource()** | CodeSource or null | Source/protection domain metadata. |
| **clazz.getResource("X.class")** | URL or null | Finds a resource relative to clazz's package. |
| **loader.getResource("p/X.class")** | URL or null | Finds a resource by /-separated name through the loader. |
| **loader.getResources("p/X.class")** | Enumeration URL | Matching resources that may include both parent and child. |
| **loader.loadClass("p.X")** | Class<?> | Looks up a runtime class by binary name. |

**JPMS note:** For resources in named modules, **ClassLoader.getResource** is also subject to package openness/encapsulation rules. Do not assume every resource inside a named module will be returned simply because the JAR has that entry. Class.getResource has its own module-aware semantics.

**Being able to locate a path does not mean loadClass will automatically use that exact resource URL:** a parent-first URLClassLoader may choose the parent's Class even though the plugin JAR also contains a resource with the same name.

## 11. Printing a Multi-Loader Tree in a Complex Application

If a system has multiple plugin loaders, you can record each loader using a structured format:

~~~text
Name: plugin-A
  implementation: java.net.URLClassLoader
  parent: application
  known artifact URL: file:/.../pluginA.jar
  class sample.plugin.PluginA:
      defining loader = plugin-A
      module = unnamed
      code source = pluginA.jar

Name: plugin-B
  implementation: java.net.URLClassLoader
  parent: application
  known artifact URL: file:/.../pluginB.jar
  class sample.plugin.PluginB:
      defining loader = plugin-B
      module = unnamed
      code source = pluginB.jar
~~~

This is a **report template**, not the fixture's stdout.

With multiple loaders, you need to:

1. Assign a **name or deployment ID** when creating a loader.
2. Record the loader's **owner** (host/plugin manager).
3. Record the parent chain for new loaders.
4. Print **Class.getClassLoader()** for each important class.
5. Compare the identity of shared APIs using **==**.
6. Correlate CodeSource/resource URLs with expected artifacts.
7. Record the module name and layer if using JPMS.
8. Manage the lifecycle/closing of URLClassLoader when a deployment stops.

**Do not traverse the JVM to list all loaders by assuming every loader sits under the system loader.** Loaders whose parent is bootstrap/platform or that use peer delegation might not be found by walking from the system parent chain.

### 11.1 Displaying the Parent Chain Without Relying on toString()

If you use output like:

~~~text
jdk.internal.loader.ClassLoaders$AppClassLoader@30946e09
~~~

this is a class name and identity hash tied to the JVM implementation. It is useful for distinguishing instances within a single process, but it is not stable across runs. You should not write integration tests comparing the literal hash or implementation class name.

You can add your own stable label such as **plugin-loader, plugin-loader-2, deployment-v1** and compare identities within the program.

### 11.2 Thread Context ClassLoader Is Another Axis

~~~java
ClassLoader tccl =
        Thread.currentThread().getContextClassLoader();
~~~

The TCCL does not necessarily equal the loader that defined the currently executing class. Frameworks such as ServiceLoader can use the TCCL to locate providers and resources.

If you are debugging an SPI where a provider cannot be found, **both the service type's Class.getClassLoader and the TCCL** are useful, though they do not replace class identity checks. Temporarily setting the TCCL must **restore the previous one** in a finally block if the thread belongs to a host pool.

## 12. Diagnosing Unexpected Output

### 12.1 Greeter Loader Is application Instead of plugin

The usual cause is accidentally placing **plugin.jar** or plugin-out on the application classpath:

~~~bash
# Do not use for expected demo output:
java -cp "host-out:plugin.jar" sample.app.InspectLoaders
~~~

Because URLClassLoader is parent-first, the application loader sees Greeter first, so plugin.loadClass returns the parent's class. In this case, Greeter's **CodeSource** may still be plugin.jar, yet its **defining loader** is no longer plugin.

**Lesson:** the same artifact source does not guarantee the same loader owner.

### 12.2 Greeter source = unavailable

Do not jump to the conclusion that the class “has no file”. The runtime may be using a custom defineClass, in-memory bytes, no CodeSource, or a security/module context hiding the information.

Check the defining loader, resource lookup, class loading logs, and that loader's ProtectionDomain design.

### 12.3 FileNotFoundException or NoSuchFileException When Running

The example uses **plugin.jar** and **host-out** paths relative to the **current working directory**. If you run it in an IDE with a different working directory, the files will not be found.

Fix: run from the project root or change the working directory configuration or use absolute input paths. Do not rely on the classpath to automatically locate **plugin.jar** when Path.of("plugin.jar") looks it up directly on the filesystem.

### 12.4 ClassNotFoundException: sample.plugin.Greeter

Check:

~~~bash
jar --list --file plugin.jar
~~~

The entry must be present:

~~~text
sample/plugin/Greeter.class
~~~

If it is missing, check javac -d plugin-out and jar -C plugin-out. If it is present, verify that the plugin URL uses **Path.of("plugin.jar").toUri().toURL()** properly, that the class name uses dots, and check parent delegation.

### 12.5 ClassCastException Despite Identical Class Names

If two URLClassLoaders define the same binary name on their own, **the Class objects are different**. An instance created by the first plugin loader cannot automatically be cast to the type defined by plugin2.

For shared host-plugin contracts, place interfaces/DTOs in the parent loader and avoid packaging duplicate copies in child-first packages.

### 12.6 NoClassDefFoundError: sample/host/HostApi

If you use the platform parent and plugin.jar **no longer contains its own HostApi**, yet Greeter still depends on it, the isolated loader cannot see host-out's HostApi. The loader may need a different parent or the API package must be allowed to delegate to the shared loader.

**Fix the API boundary architecture** instead of just swallowing the exception and returning an incompatible Class.

### 12.7 DriverManager Loader Output Is Not platform

This observation depends on the runtime JDK. Check the vendor/version and built-in ClassLoader mapping. The demo is still valid if the Class is loaded by a different loader; just adjust the expected output to match the supported environment and do not equate all platform classes with one fixed loader.

### 12.8 Resource Source Is jar: While CodeSource Is file:

This is common and normal:

~~~text
CodeSource: file:/.../plugin.jar
Resource:   jar:file:/.../plugin.jar!/sample/plugin/Greeter.class
~~~

CodeSource points to the artifact location; the resource URL points to the specific entry inside the JAR. Two URLs with different protocols do not mean two class versions.

### 12.9 Static Initializer Does Not Run During loadClass

According to the JLS, class initialization is a separate step from loading. The example runs the initializer only during reflective construction. Do not use **getClassLoader()**, **getModule()**, or **getResource()** to assert that the static initializer has executed.

## 13. Tests Based on the Example

Assertions should focus on **properties**, not the string hashes of loaders:

~~~java
// Snippet in a scope that has plugin, type, and plugin2:
assert type.getClassLoader() == plugin;
assert plugin.loadClass("sample.host.HostApi")
        == sample.host.HostApi.class;
assert type != plugin2.loadClass(
        "sample.plugin.Greeter");
~~~

To enable assert in Java:

~~~bash
java -ea -cp host-out sample.app.InspectLoaders
~~~

In the main exercise, assertions are not added to the launcher, but if you put the snippet into the appropriate scope, the three properties above hold true under the guided setup. Note that **assert is disabled by default** unless **-ea** is passed, so important integration tests usually use testing framework assertions (JUnit) or explicit checks that do not depend on JVM assertion flags.

### 13.1 Do Not Test Using a Hardcoded System.identityHashCode

**System.identityHashCode(loader)** can be useful for labeling identity within a single run, but the exact value is not stable across processes. Compare with **==** within the same JVM, and log a business-meaningful deployment ID as well.

### 13.2 Testing the Source Location

For this fixture, the code uses **toRealPath** to compare CodeSource with host-out and plugin.jar, avoiding relative/absolute path differences for the same file.

On Windows, if directory case, symlinks, permissions, or file layout differ, Path equality may require appropriate handling. This is **fixture code** for two file URLs, not a class-origin verification method usable for every protocol.

## 14. Extending the Practice

### Exercise A — Add a Class Present Only in the Plugin JAR

Create a new class **sample.plugin.Helper**, compile it into plugin-out, and repackage plugin.jar. Print:

~~~java
Class<?> helper =
        plugin.loadClass("sample.plugin.Helper");

System.out.println(helper.getClassLoader() == plugin);
~~~

Expected **true** if the parent does not see that class and the plugin loader is still open. Place the code in the scope that holds InspectLoaders's URLClassLoader plugin.

### Exercise B — Observe a CodeSource Without a URL

In main, print:

~~~java
System.out.println(
        String.class.getProtectionDomain()
                .getCodeSource());
~~~

The result may be null or in a runtime-specific form. Do not write a portable exact-output assertion. In a real application, null-check ProtectionDomain first if needed.

### Exercise C — Add plugin.jar to the Application Classpath

Try running the launcher with plugin.jar added to the classpath. Observe **Greeter loader**, **Class identity**, the static initializer, and **resource counts**; compare with running when plugin.jar is only on the URLClassLoader.

**Explanation:** Parent-first allows the application loader to define Greeter, even though the program still calls plugin.loadClass. However, the **source = plugin.jar** output may still remain the same. This clearly illustrates that **artifact source and defining loader** are two separate axes.

### Exercise D — Create Two Versions of plugin.jar

Package a Greeter method returning two different results under two JAR URLs, create a separate loader for each JAR, and compare **Class identity** and the method results. Do not attempt to redefine Greeter in the same loader by calling defineClass a second time. When hot reload is needed, create a new loader and manage its lifecycle.

### Exercise E — Print Module Name / Unnamed Module

Check:

~~~java
System.out.println(type.getModule().isNamed());
System.out.println(type.getModule().getName());
~~~

With an ordinary URLClassLoader on the fixture's classpath-style JAR, the output is **false** followed by **null** because Greeter is in an unnamed module. For **String.class**, **getModule().getName()** is **java.base**.

### Exercise F — Compare ClassLoader.getResource and Class.getResource

Use the resource path **sample/plugin/Greeter.class** for ClassLoader and **Greeter.class** for package-relative Class.getResource. Print the protocols and check whether they logically point to the same entry.

Do not arbitrarily add a leading slash to **ClassLoader.getResource**, because by contract a ClassLoader resource name uses a /-separated path without a leading slash.

## 15. Self-Check Questions

**1.** In HotSpot, why does **String.class.getClassLoader()** return null?

**Answer:** The bootstrap loader is a built-in JVM loader and is commonly represented as null, not because String has not been loaded.

**2.** Does **getParent()** list all loaders currently existing in the JVM?

**Answer:** No. It follows the parent chain starting from the loader being inspected, not a list of all loader objects.

**3.** Is a ClassLoader on which **loadClass** is called guaranteed to be the defining loader of the returned Class?

**Answer:** No. It may delegate to its parent and act only as the initiating loader in that context.

**4.** Which API returns the defining loader?

**Answer:** **Class.getClassLoader()** (which may be null for bootstrap classes).

**5.** Which API provides a Class's code source location?

**Answer:** **Class.getProtectionDomain().getCodeSource().getLocation()**, with a null-check at each step.

**6.** Both the parent and the plugin JAR contain HostApi. Why does the host version win in the first demo?

**Answer:** URLClassLoader is parent-first by default and has the application loader as its parent, where HostApi is already on the classpath.

**7.** Why does getResources find two **HostApi.class** URLs while plugin.loadClass returns only one Class object?

**Answer:** Resource lookup can enumerate both files; class lookup follows delegation and returns one defined/selected Class rather than defining each resource into a separate Class.

**8.** Do **CodeSource** and **Class.getResource** always have the same URL?

**Answer:** No. One may be file:/.../plugin.jar, while the other is jar:file:/.../plugin.jar!/path/Class.class.

**9.** Two new URLClassLoader instances both read the same plugin.jar. Why is Greeter Class equality false?

**Answer:** Their defining loaders differ, so the two runtime Class identities are different.

**10.** Does **loadClass** run the static initializer?

**Answer:** Not by itself. Initialization occurs according to other active use rules, such as creating an instance via reflection in the demo.

**11.** Which version of HostApi does the isolated loader with the platform parent load?

**Answer:** It loads the version in plugin.jar, because the platform parent cannot see the host-out version in the fixture.

**12.** A JAR contains the class, yet the program still throws ClassNotFoundException — what should you check?

**Answer:** The exact binary name, the exact path inside the JAR, the URL used to create the loader, parent delegation, whether the loader has already been closed, module encapsulation, and the runtime classpath/module path.

**13.** Can you confirm that a Class has been unloaded merely by closing the URLClassLoader and having called getClassLoader beforehand?

**Answer:** No. URLClassLoader.close only closes the loader's own ability to look up new classes/resources and the resources it owns; existing Class objects and instances can remain alive until no strong references remain and the JVM unloads them later.

**14.** What are the risks of logging the full CodeSource URL?

**Answer:** It can expose filesystem paths or internal infrastructure; at the same time, the URL is not a cryptographic guarantee that the class source is genuinely trusted.

## 16. Exercise Summary

~~~text
Create host-out containing HostApi
               |
               v
Create plugin.jar containing Greeter + duplicate-named HostApi
               |
               v
AppLoader (parent) ------> host version of HostApi
               ^
               |
Plugin URLClassLoader ---> Greeter from plugin.jar
               |
               +-- asks for HostApi -> parent wins
               |
               +-- class resource URLs may have 2 versions
               |
               v
Class.getClassLoader() => WHO defined?
Class.getModule()      => IN WHICH module?
CodeSource location    => SOURCE artifact metadata?
Class.getResource()    => RESOURCE entry URL?
ClassLoader.getParent()=> PARENT chain?
               |
               v
Create another URLClassLoader for plugin.jar
               |
               v
Different Greeter Class identity
~~~

**Key takeaways:**

- **The loader tree** explains parent relationships, not the complete runtime graph.
- **Class.getClassLoader()** is the direct way to query the defining loader of a Class object.
- **CodeSource and resource URLs** help locate the artifact, but do not replace loader identity information.
- **Parent-first** can cause the class to actually come from the host even when the plugin JAR contains a file with the same name.
- **Two loaders reading the same JAR can still create two different Class objects**.
- **loadClass does not automatically initialize a class**; active use such as newInstance is what causes the static initializer in the fixture to run.
- When diagnosing real applications, print **loader identity, module, CodeSource, resource URL, and class-loading logs** together instead of looking only at the class name.

### Official References

- Java SE 21 **ClassLoader API** (getParent, loadClass, getResource, getSystemClassLoader): https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 21 **URLClassLoader API** (constructors, class/resource loading, close): https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html
- Java SE 21 **Class API** (getClassLoader/getModule/getProtectionDomain/getResource): https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html
- Java SE 21 **ProtectionDomain API**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/ProtectionDomain.html
- Java SE 21 **CodeSource API**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/CodeSource.html
- Java SE 21 **JLS §12.2: Loading Classes and Interfaces**: https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.2
- Java SE 21 **JVMS §5.3: Creation and Loading**: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3
