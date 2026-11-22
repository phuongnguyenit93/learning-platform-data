# ClassNotFoundException: Explicit Class Lookup Request Failed

`java.lang.ClassNotFoundException` (often abbreviated as **CNFE**) is a **checked exception** indicating that an operation **actively requesting to find/load a class by name** could not find a matching definition through the class loader being used. Typical entry points are `Class.forName(...)`, `ClassLoader.loadClass(...)`, and libraries/frameworks that call those APIs to load a driver, plugin, implementation, or configuration class by name.

For example, an application receives `"com.example.plugins.Reporter"` from a configuration file and then calls:

~~~java
Class<?> type = Class.forName("com.example.plugins.Reporter");
~~~

If the selected loader cannot find this class, the method throws `ClassNotFoundException`. That **does not prove that the `Reporter.class` file does not exist on the machine**: the class may reside in another JAR, an unresolved module, a directory not placed on the proper classpath, or a child loader that the caller does not use.

**Key Points:**
- CNFE reflects **a failed explicit class lookup request with the loader and requested name**.
- `Class.forName(String)`, `Class.forName(String, boolean, ClassLoader)`, and `loader.loadClass(String)` have different loader selection/initialization rules.
- The binary name, classpath/module path, and loader visibility scope must all be correct at the same time.
- `NoClassDefFoundError` is a different JVM/linkage error, typically occurring when a class required by bytecode cannot be defined/initialized; the two situations should not be treated as the same kind of error.
- The proper debugging approach is to identify **which class name was requested, which loader performed the lookup, which artifact contains the bytecode, and which step actually failed**.

## 1. Definition in the Java Exception Hierarchy

Inheritance diagram:

~~~text
java.lang.Object
  └── java.lang.Throwable
       └── java.lang.Exception
            └── java.lang.ReflectiveOperationException
                 └── java.lang.ClassNotFoundException
~~~

Because CNFE is a checked exception, a call declared with `throws ClassNotFoundException` must be **caught** or declared further in the method signature.

~~~java
public static Class<?> locate(String binaryName)
        throws ClassNotFoundException {
    return Class.forName(binaryName);
}
~~~

This is an illustrative method. The caller must handle the exception or continue declaring `throws`.

Contextual handling example:

~~~java
try {
    Class<?> type = Class.forName(configuredClassName);
    // Continue checking the contract and initializing.
} catch (ClassNotFoundException ex) {
    throw new IllegalStateException(
            "Configured provider was not found: " + configuredClassName,
            ex);
}
~~~

This is an illustrative snippet with `configuredClassName` already provided, not a standalone program. Wrapping in `IllegalStateException` may be appropriate when **a missing plugin is a critical configuration error**; if the plugin is optional, an intentional fallback policy should be chosen instead of always failing the entire host.

### Class Name in the Exception

The message or stack trace usually contains the requested binary name, for example:

~~~text
java.lang.ClassNotFoundException: com.example.plugins.Reporter
~~~

The actual message may vary depending on the loader/JVM; do not rely on the error string necessarily matching a specific character pattern. What is more reliable is the **exception type**, the name passed to the API, the cause chain, and the loader being used.

## 2. Why Do You Still Get CNFE When the "Class Exists"?

An accurate answer always requires three parts:

~~~text
Call being executed:
  which binary name?
              |
              v
  Which ClassLoader receives the request?
              |
              v
  Which sources does that loader search?
              |
              v
  Is the class available/found according to those rules?
       /                             \
     Yes                              No
     |                                 |
 Class<?> or                    ClassNotFoundException
 error at another step          (depending on API)
~~~

If `out/plugins/com/acme/Feature.class` exists but the application only runs with the classpath `out/app`, the application loader **does not automatically scan** `out/plugins` as well. Similarly, a plugin JAR may be visible to a child `URLClassLoader`, but `Class.forName(String)` called from the host still selects the **caller's** loader and does not guess the child loader.

### Four Common Conditions

1. **Correct name:** `com.acme.Feature`, not `com/acme/Feature.class`.
2. **Correct location:** the classpath root or URL must be a directory/JAR containing the proper package path.
3. **Correct loader:** the loader executing the lookup must actually see that source, directly or through effective delegation.
4. **Correct launch mechanism:** application classpath, executable JAR, and JPMS module path are not equivalent configurations.

Many CNFE errors are **configuration/loader visibility** errors, not missing files at the OS level.

## 3. Which APIs Can Throw ClassNotFoundException?

### 3.1. `Class.forName(String)`

~~~java
Class<?> c = Class.forName("com.acme.Feature");
~~~

The single-parameter overload uses the **defining class loader of the class calling the API** to look up the class and requests initialization by default. It **does not simply take the TCCL** carried by the thread.

A class in the host may successfully call `Class.forName("com.acme.HostHelper")` yet fail with `"com.acme.plugin.Feature"` if Feature only exists in the child plugin loader.

### 3.2. `Class.forName(String, boolean, ClassLoader)`

~~~java
Class<?> c = Class.forName(
        "com.acme.plugin.Feature",
        false,
        pluginLoader);
~~~

This is an illustrative snippet with `pluginLoader` already configured.

- `name`: binary name of the class/interface, or array name form according to the API rules.
- `initialize=false`: does not request running the class initializer.
- `initialize=true`: requests initializing the class if not already initialized; may produce an exception/error during the initialization phase **different from CNFE**.
- `loader`: **explicitly specified** class loader; this is the reliable approach when the plugin class is not in the host's loader.
- According to the API, passing `null` for loader means using the bootstrap loader, not "searching across all classpaths".

If the class is found but its initializer throws an exception, the result may be `ExceptionInInitializerError` or a related `Error`, **not CNFE** simply because the class failed to run.

### 3.3. `ClassLoader.loadClass(String)`

~~~java
Class<?> c = pluginLoader.loadClass("com.acme.plugin.Feature");
~~~

`loadClass` by default **does not request initialization**; it finds/loads the type according to the loader's delegation policy. If not found, it typically throws CNFE. When the class is found but the bytes are invalid or linking/access is invalid, other `LinkageError`/`SecurityException` failures may occur.

With the default parent-first loader:

~~~text
child.loadClass(name)
      |
      v
findLoadedClass(name)
      |
      +-- not yet loaded -> parent.loadClass(name)
                                 |
                                 +-- parent finds it -> return parent's Class
                                 |
                                 +-- no -> child.findClass(name)
                                                |
                                                +-- yes -> define Class
                                                |
                                                +-- no -> CNFE
~~~

**Calling through the child does not mean the child will be the defining loader.** If the parent can return the class, `c.getClassLoader()` is still the parent. When debugging, distinguish between the initiating loader and the defining loader.

### 3.4. Reflection and Libraries/Frameworks

`ClassNotFoundException` can occur when:

- A plugin system reads an implementation name from configuration and calls `Class.forName`.
- Code creates a `URLClassLoader` and calls `loadClass` with the configured class name.
- A framework reads metadata containing binary names and calls reflection to look up the class.
- Legacy JDBC systems call `Class.forName("...Driver")` to initialize the driver class; JDBC 4+ also has a service-provider discovery mechanism, so **not every driver requires calling `Class.forName` manually**.
- A framework or library hides CNFE beneath a higher-level exception, such as a provider discovery failure or a wrapper exception.

**Do not conflate:** `new SomeClass()` in compiled code is not a string-name request like `Class.forName`. When a dependency referenced by bytecode is missing, the JVM typically reports `NoClassDefFoundError`/linkage failure instead of a checked CNFE directly in Java source.

## 4. Binary Name, Package Path, and Classpath Root

Suppose the source is:

~~~java
package com.acme.plugin;

public final class Reporter {
}
~~~

After compiling, the file is typically located at:

~~~text
out/plugin/
  com/
    acme/
      plugin/
        Reporter.class
~~~

The name for the `loadClass`/`forName` API is:

~~~java
"com.acme.plugin.Reporter"
~~~

Not:

~~~text
com/acme/plugin/Reporter.class
com.acme.plugin.Reporter.class
/out/plugin/com/acme/plugin/Reporter.class
~~~

The latter strings are **paths** or file names, not the binary class name that the standard overloads expect.

### Inner/Nested Classes

A static nested class:

~~~java
package com.acme;

public final class Outer {
    public static final class Inner {
    }
}
~~~

The binary name of the nested class is:

~~~text
com.acme.Outer$Inner
~~~

Use `Class.forName("com.acme.Outer$Inner")`, **not** `"com.acme.Outer.Inner"`. In normal Java code you can reference `Outer.Inner.class`, but the binary name string and source type name syntax are different.

### Arrays and Primitive Types

`Class.forName` has its own rules for array class names, for example:

~~~java
Class<?> a = Class.forName("[Ljava.lang.String;");
System.out.println(a == String[].class);
~~~

With a standard JDK, the output is `true`. On the other hand:

~~~java
Class.forName("int");
~~~

is not the way to get `int.class`; that call throws `ClassNotFoundException`. Use `int.class` directly for primitive types.

**When debugging CNFE, always log the exact input string**. A single `/`, `.class`, wrong case in a package name, or confusing `$` with `.` can be the entire cause.

## 5. Complete Java 17+ Example: Host Cannot Find the Class, Plugin Loader Finds It

We create:

- A `com.acme.plugin.Greeting` class in a **separate plugin directory**.
- A host class `ClassNotFoundLab` compiled/run **without placing the plugin on the application classpath**.
- A `URLClassLoader` created by the host, pointing directly to the plugin directory.
- The same binary name fails when the host uses the default loader, but succeeds when explicitly choosing the plugin loader.
- A static initializer to illustrate the difference between **load** and **initialize**.

### 5.1. Project Structure

~~~text
project/
  src/
    plugin/
      com/
        acme/
          plugin/
            Greeting.java
    app/
      ClassNotFoundLab.java
  out/
    plugin/              (generated by javac)
    app/                 (generated by javac)
~~~

**Do not** place `out/plugin` on the application classpath when running the host; that is the key point of the experiment.

### 5.2. File `src/plugin/com/acme/plugin/Greeting.java`

~~~java
package com.acme.plugin;

public final class Greeting {
    static {
        System.out.println("plugin initialized");
    }

    public static String message() {
        return "hello from plugin";
    }
}
~~~

The initializer only prints when the class is actually initialized. `loadClass` does not require the initializer to run; `Class.forName(name, true, loader)` requires it.

### 5.3. File `src/app/ClassNotFoundLab.java`

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class ClassNotFoundLab {
    private static final String NAME =
            "com.acme.plugin.Greeting";

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: ClassNotFoundLab <plugin-directory-or-jar>");
        }

        // A. Host does not see out/plugin on the application classpath.
        try {
            Class.forName(NAME);
            System.out.println("default Class.forName: found");
        } catch (ClassNotFoundException ex) {
            System.out.println(
                    "default Class.forName: ClassNotFoundException");
        }

        try {
            ClassLoader.getSystemClassLoader().loadClass(NAME);
            System.out.println("system loadClass: found");
        } catch (ClassNotFoundException ex) {
            System.out.println(
                    "system loadClass: ClassNotFoundException");
        }

        // B. Plugin loader has a URL root pointing to out/plugin.
        URL root = Path.of(args[0]).toAbsolutePath()
                .toUri().toURL();

        ClassLoader parent = ClassNotFoundLab.class.getClassLoader();

        try (URLClassLoader pluginLoader =
                new URLClassLoader("plugin", new URL[] {root}, parent)) {

            Class<?> type = pluginLoader.loadClass(NAME);

            System.out.println(
                    "explicit loadClass: " + type.getName());
            System.out.println("defined by plugin loader: "
                    + (type.getClassLoader() == pluginLoader));

            Class<?> same = Class.forName(
                    NAME, false, pluginLoader);
            System.out.println(
                    "same Class object: " + (same == type));

            System.out.println("before initialization");
            Class.forName(NAME, true, pluginLoader);

            Object answer = type.getMethod("message").invoke(null);
            System.out.println("invoke: " + answer);

            try {
                pluginLoader.loadClass("com.acme.plugin.Missing");
                System.out.println("missing name: found");
            } catch (ClassNotFoundException ex) {
                System.out.println(
                        "missing name: ClassNotFoundException");
            }

            try {
                pluginLoader.loadClass(
                        "com/acme/plugin/Greeting");
                System.out.println("slash name: found");
            } catch (ClassNotFoundException ex) {
                System.out.println(
                        "slash name: ClassNotFoundException");
            }
        }

        try {
            Class.forName("int");
            System.out.println("primitive name: found");
        } catch (ClassNotFoundException ex) {
            System.out.println(
                    "primitive name: ClassNotFoundException");
        }
    }
}
~~~

Why not import `Greeting` into the host? If the host compiles against that class and then puts the plugin output on the application classpath, the experiment may no longer demonstrate an **explicit lookup from a host that cannot see the plugin**. The plugin is invoked via reflection only after the host creates the proper loader.

### 5.4. Compile and Run

**Bash commands on Linux/macOS** (or a compatible Bash environment) from the `project` directory:

~~~bash
mkdir -p out/plugin out/app

javac -d out/plugin \
    src/plugin/com/acme/plugin/Greeting.java

javac -d out/app src/app/ClassNotFoundLab.java

java -cp out/app ClassNotFoundLab out/plugin
~~~

For Windows PowerShell, create the directories using `New-Item -ItemType Directory -Force` and run the equivalent `javac`/`java` commands. Here the classpath has only **one** entry `out/app`, so no platform-specific separator between multiple entries is needed.

### 5.5. Exact Stdout of the Example

~~~text
default Class.forName: ClassNotFoundException
system loadClass: ClassNotFoundException
explicit loadClass: com.acme.plugin.Greeting
defined by plugin loader: true
same Class object: true
before initialization
plugin initialized
invoke: hello from plugin
missing name: ClassNotFoundException
slash name: ClassNotFoundException
primitive name: ClassNotFoundException
~~~

**Explanation:**

1. The first two calls use the host/system application loader, which does not see `out/plugin`, resulting in CNFE.
2. `URLClassLoader` is given a URL pointing to the proper `out/plugin/` root. When the parent does not find the class, the child looks up `com/acme/plugin/Greeting.class` from the directory.
3. `getClassLoader() == pluginLoader` is `true`, proving that the child is indeed the defining loader of the plugin class.
4. `loadClass` returned `Class<?>` but **did not initialize** the class, so the `plugin initialized` line did not appear before `before initialization`.
5. `Class.forName(NAME, false, pluginLoader)` returns the same runtime class; `true` does not prove the class has been initialized.
6. `Class.forName(NAME, true, pluginLoader)` triggers initialization and prints exactly one `plugin initialized` line.
7. The static method `message` runs and returns `hello from plugin`.
8. `com.acme.plugin.Missing` does not exist, and the string using `/` has an invalid binary name, so both result in CNFE.
9. `Class.forName("int")` does not retrieve the primitive `int.class`, so it also results in CNFE.

**Clear limitation:** this stdout assumes there is no copy of `com.acme.plugin.Greeting` on the application classpath, no other class with the same name defined by the parent, a compatible Java runtime, and the two source files are created exactly as in the example.

### 5.6. If the Plugin Is Packaged as a JAR

It can be packaged from the class output:

~~~bash
mkdir -p dist
jar --create --file dist/plugin.jar -C out/plugin .

jar --list --file dist/plugin.jar
~~~

The JAR must contain `com/acme/plugin/Greeting.class`. Try:

~~~bash
java -cp out/app ClassNotFoundLab dist/plugin.jar
~~~

Because the host converts the argument into a `file:` URL via `Path.toUri().toURL()`, URLClassLoader supports **both directory URLs and JAR file URLs**. The Usage message allows a directory or a JAR; the experiment uses the same code with the plugin JAR; when the class exists in the JAR and is not shadowed by the parent, stdout remains the same.

**Note:** a plugin JAR does not need `Main-Class` if classes are only loaded with URLClassLoader; `Main-Class` is for an executable JAR run via `java -jar`.

## 6. Distinguishing Between ClassNotFoundException and NoClassDefFoundError

Both can appear when a class is missing, but they report **two different error layers**:

| | `ClassNotFoundException` | `NoClassDefFoundError` |
| --- | --- | --- |
| Throwable branch | Checked `ReflectiveOperationException` | `LinkageError` → `Error` |
| Common triggers | `Class.forName(name)`, `loader.loadClass(name)` requesting lookup by name | JVM resolving a class referenced by bytecode or a class whose initialization failed |
| Information to gather | Binary name string, API overload, and selected loader | Cause chain, missing class, first failure, linker, and loader |

For example, `Class.forName("plugin.Missing")` from the host can throw **CNFE**, whereas bytecode compiled to call `MissingDependency.run()` with the dependency deleted at runtime can throw **NCDFE**, sometimes with CNFE appearing in the cause chain. These two examples only illustrate the context; bytecode calling `MissingDependency` only compiles if the class actually exists at compile time.

**For an initialization failure**, the first active use may throw `ExceptionInInitializerError`; subsequent uses within the same defining loader may throw `NoClassDefFoundError: Could not initialize class ...`. When encountering that symptom, you must look for `<clinit>` and the original cause, not just add a JAR.

The article **NoClassDefFoundError Due to Missing Dependency or Wrong Name** has two standalone labs reproducing a missing dependency error and a class bytecode carrying the wrong binary name. The article **NoClassDefFoundError After Class Initialization Fails** specifically covers the erroneous state and how to recover using a new loader. In this CNFE article, the primary question remains **who calls the lookup, with what name, and which loader actually performs the search**.

## 7. Why Is a Loader Physically Right Yet Wrong in Scope?

### 7.1. Parent Cannot See Child

~~~text
ApplicationLoader
      |
      +-- PluginLoader A -> plugin-a.jar
      |
      +-- PluginLoader B -> plugin-b.jar
~~~

A parent has no obligation to search for classes **in child loaders**. Plugin loader A also cannot automatically see classes private to plugin loader B when they only share a parent. Therefore:

~~~java
Class.forName("plugin.b.Feature");
~~~

when called from the host may throw CNFE even though the class resides in `plugin-b.jar`, which PluginLoader B can see. You need to intentionally call `Class.forName(name, initialize, loaderB)` or `loaderB.loadClass(name)`.

**Do not force every plugin JAR onto the global application classpath just to fix CNFE**, because doing so can break version isolation and the loader lifecycle of the plugin system.

### 7.2. Thread Context Class Loader (TCCL)

Some frameworks and `ServiceLoader.load(Service.class)` select the **thread context class loader** to locate providers. However:

~~~java
Class.forName("plugin.Feature");
~~~

does not switch to the TCCL by default just because the thread has been assigned a different TCCL.

If needed, make it explicit:

~~~java
ClassLoader tccl =
        Thread.currentThread().getContextClassLoader();

Class<?> type = Class.forName("plugin.Feature", false, tccl);
~~~

This is an illustrative snippet; if `tccl == null`, this overload uses the bootstrap loader. In a plugin runtime, consider determining the loader from the framework contract instead of implicitly depending on thread state.

When a library requires TCCL, set it temporarily and **restore it in `finally`**:

~~~java
Thread thread = Thread.currentThread();
ClassLoader old = thread.getContextClassLoader();
try {
    thread.setContextClassLoader(pluginLoader);
    // Call the library that requires TCCL.
} finally {
    thread.setContextClassLoader(old);
}
~~~

Do not leave a thread pool's TCCL pointing to a stopped plugin loader: it both causes incorrect discovery for subsequent requests and can keep the old loader from being unloaded.

### 7.3. Parent-First Can Load a Different Version Than Expected

Suppose the parent has `lib.Parser` version v1, while the plugin JAR contains v2. Calling `pluginLoader.loadClass("lib.Parser")` with the default URLClassLoader may return the v1 `Class<?>` defined by the parent, **without throwing CNFE**. However, when the plugin calls a method that only exists in v2, the JVM may throw `NoSuchMethodError`.

This is a case where **the lookup succeeds, yet runtime behavior/linkage is wrong**. Do not conclude that the classpath and dependency versions are correct just because no CNFE occurs.

## 8. Classpath, Executable JAR, and Module Path

### 8.1. Classpath Mode

On Linux/macOS:

~~~bash
java -cp "out/app:libs/plugin.jar" com.example.Main
~~~

On Windows:

~~~powershell
java -cp "out/app;libs/plugin.jar" com.example.Main
~~~

The illustrative syntax examples assume `com.example.Main` exists. The classpath separator is `:` on Unix-like systems and `;` on Windows.

A classpath root can be a directory or a JAR. If the binary name is `com.acme.Feature`, the path beneath the root must be `com/acme/Feature.class`.

Classpath CLI wildcard:

~~~bash
java -cp "out/app:libs/*" com.example.Main
~~~

It can add JAR files in the `libs` directory according to launcher rules; the wildcard **does not search the entire directory tree recursively**, and does not guarantee version order on its own. Do not use a wildcard if you are investigating two JARs that have the same class and need to know exactly which version is selected.

### 8.2. `java -jar` Mode

~~~bash
java -cp "libs/*" -jar app.jar
~~~

This **does not** mean `libs/*` is added to the application's user classpath as in classpath mode: with `-jar`, standard classpath settings such as `-cp` and `CLASSPATH` are ignored when choosing the application's class search path. Dependencies can be declared via the manifest's `Class-Path` or packaged using an appropriate mechanism.

Example manifest:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.Main
Class-Path: libs/plugin.jar

~~~

Manifest `Class-Path` entries are separated by **whitespace** and resolved **relative to the location of the JAR containing the manifest**, not according to the OS classpath separator. Do not write `Class-Path: libs/*` and expect wildcard behavior like `-cp "libs/*"`.

### 8.3. JPMS Named Modules

Java 9+ has named modules resolved via the **module path**, along with `requires`, `exports`, `opens` relationships and module layers.

**Distinctions:**
- A missing module or an unresolved module can cause a named-module class to fall outside the loader/module lookup scope requested by the caller.
- A package that is not `exports`-ed is an **access issue from another module**, not automatically synonymous with the class file not existing, and not every case reports CNFE. Depending on the situation, `IllegalAccessError`/`IllegalAccessException` may occur at the access step.
- `opens` mainly relates to deep reflection/resource access; **it is not a default cure-all for every CNFE**.
- `Class.forName(Module module, String name)` is a special overload: it searches for the class in the specified module and **returns `null` when not found in that module** per the API contract; it does not throw CNFE simply because the lookup failed to find it. It does not request initializing the class.
- `ClassLoader.loadClass(Module module, String name)` also has a different contract from `loadClass(String)` and may **return `null` if the class cannot be found in the specified module**.

Therefore, **identify which API overload is actually being called** before asserting that an unsuccessful lookup always throws `ClassNotFoundException`.

## 9. CNFE Diagnosis Process by Evidence Layer

### Step 1 — Record the Exact Request

Capture the **binary name value** actually passed to the API (after trimming/config parsing when needed), which API overload was called, the thread, the caller's module, and the stack trace/cause chain.

A config may accidentally contain leading/trailing whitespace:

~~~text
plugin.class = com.acme.plugin.Greeting
~~~

If the parser does not normalize it or reads the wrong key, the string passed to `Class.forName` may differ from the string you visually see.

### Step 2 — Print the Loader Used

~~~java
ClassLoader callerLoader =
        ClassNotFoundLab.class.getClassLoader();

ClassLoader tccl =
        Thread.currentThread().getContextClassLoader();

ClassLoader system =
        ClassLoader.getSystemClassLoader();

System.out.println(callerLoader);
System.out.println(tccl);
System.out.println(system);
~~~

This is an illustrative snippet when `ClassNotFoundLab` is in scope; there is no guarantee that the three loaders are equal. On many simple applications, they may match, but plugin/container frameworks often configure them differently.

**If the class has not been found yet, you do not have its `Class<?>` to call `getClassLoader()` on.** Start from the loader performing the lookup and that loader's search roots.

### Step 3 — Check Whether the Artifact Actually Contains the Class

For a JAR:

~~~bash
jar --list --file libs/plugin.jar
~~~

Look for the exact entry:

~~~text
com/acme/plugin/Greeting.class
~~~

If you only see `com/acme/plugin/Greeting.java`, then the JAR contains source, **not necessarily the class file** for the JVM to load as expected.

For a directory, check the root and package subdirectories. For the path `out/plugin/com/acme/plugin/Greeting.class`, the URL/classpath root is `out/plugin`, not `out/plugin/com/acme/plugin`.

### Step 4 — Check Whether Compile-Time and Runtime Configurations Differ

A project compiles because the dependency is on the IDE/Maven/Gradle classpath, while at runtime it uses a JAR/launch script that does not carry that dependency.

Determine:

- The actual `java` command being run (classpath mode or `-jar`).
- The environment/module path of the runtime process, not just the IDE.
- The artifact version/path and deployment directory.
- The dependency scope (compile-only/test-only vs runtime).
- If using a plugin framework, whether the plugin's URL classloader was properly initialized and is still alive.

**Successful compilation does not prove that the runtime loader will find every class.**

### Step 5 — Check the Binary Name Instead of a Path

~~~text
Java name to pass: com.acme.plugin.Greeting
JAR entry file:    com/acme/plugin/Greeting.class
~~~

For a nested class, use `Outer$Inner`. For a primitive, use `int.class`, not `Class.forName("int")`.

### Step 6 — Try a Controlled Explicit Loader

If you are diagnosing a trusted plugin and know the artifact location:

~~~java
URL url = Path.of("plugins", "plugin.jar")
        .toAbsolutePath().toUri().toURL();

try (URLClassLoader loader = new URLClassLoader(
        new URL[] {url},
        ClassLoader.getSystemClassLoader())) {
    Class<?> type = loader.loadClass("com.acme.plugin.Greeting");
    System.out.println(type.getName());
}
~~~

This is an **illustrative snippet**, requiring imports for `URL`, `URLClassLoader`, `Path` and exception handling; the plugin JAR must actually exist. If it can be found with the explicit URL loader but not with the host loader, the issue lies in **visibility/loader choice** rather than a nonexistent binary name.

**Do not rush to modify the global classpath of the entire application** when the plugin framework already has its own loader; doing so can create class version conflicts or duplicate runtime interfaces.

### Step 7 — Identify Issues After the Class Is Found

If the class has been loaded:

~~~java
Class<?> type = loader.loadClass("com.acme.plugin.Greeting");

System.out.println(type.getName());
System.out.println(type.getClassLoader());
System.out.println(type.getModule());
~~~

If CodeSource is available:

~~~java
var pd = type.getProtectionDomain();
var cs = pd == null ? null : pd.getCodeSource();

System.out.println(cs == null ? "source unavailable"
        : cs.getLocation());
~~~

The snippets above are only **diagnostic snippets** with an appropriate loader variable. CodeSource may be `null`; it is not an absolute guarantee of origin.

### Step 8 — JVM Class Loading Logs

On HotSpot/JDK 17+, logging can be enabled:

~~~bash
java -Xlog:class+load=info \
     -cp out/app ClassNotFoundLab out/plugin
~~~

This is a **diagnostic command** that produces additional runtime-dependent log lines; it is not part of the standard stdout in the example section. It is useful for seeing the source of classes that **have been loaded**, though not every missing class has a detailed entry at the `info` level. Do not mistakenly assume "class X is not in the log" is the sole conclusion about the cause of failure.

## 10. Common Errors and How to Fix Them

| Symptom | Common Likely Cause | Proper Fix |
|---|---|---|
| `Class.forName("pkg.X")` CNFE, JAR contains `pkg/X.class` | JAR is not in loader search roots | Configure classpath/URL/module for the **right loader** |
| `Class.forName` from host does not see plugin class | Host loader cannot see down into child | Use explicit plugin loader or plugin framework API |
| `.class` exists but path beneath root is wrong | Root points to the wrong directory | Move root up to the proper package level |
| `Class.forName("a/b/C.class")` | File path used instead of binary name | Change to `a.b.C` |
| `Class.forName("a.Outer.Inner")` | Wrong nested class binary name | Use `a.Outer$Inner` |
| `Class.forName("int")` | Invalid primitive name for the API | Use `int.class` |
| Runs from IDE successfully, `java -jar` CNFE | Runtime missing dependency/manifest reference | Check final artifact, manifest, and deployment |
| Plugin A sees class, plugin B does not | Different loader graph/ownership | Choose the right loader and design a shared SPI/API |
| CNFE inside `ServiceLoader`/framework wrapper | Incorrect provider config or TCCL | Check descriptor, provider type, TCCL, and cause chain |
| Top-level `NoClassDefFoundError` | JVM needs dependency during link/init | Read cause, check missing binary/module/init |
| `NoSuchMethodError` after class is loaded | Dependency version in parent differs from compile time | Compare runtime defining loader and bytecode signatures |
| `IllegalAccessError` / reflection error | Class exists but access/module differs | Check package ownership and appropriate `exports`/`opens` |
| `ClassFormatError` / `UnsupportedClassVersionError` | Invalid bytes or JDK runtime too old | Compile with appropriate `--release`, verify bytes/Java version |

### Why Does "Adding a Dependency" Sometimes Make the Error Worse?

For example, suppose the host needs the `api.Plugin` API defined by the parent, and the child plugin needs `plugin.Impl`. If to fix CNFE you also copy `api.Plugin` into a child-first JAR, the plugin may define **a second copy of the API**. When returning the object to the host, the cast will fail even though the interface name is identical.

A better approach is to keep the **shared API in the parent** and the implementation in the plugin child. There are cases where a lookup failure signals that you are using the wrong class loader boundary; the good solution is not "put every JAR everywhere".

## 11. Proper Error Design and Exception Handling

### Missing an Optional Plugin

If the extension is optional, you can log/warn and continue with a default provider:

~~~java
try {
    Class<?> provider = pluginLoader.loadClass(configuredProvider);
    // Check the interface and create an instance according to the contract.
} catch (ClassNotFoundException ex) {
    System.err.println("Optional provider unavailable: "
            + configuredProvider);
    // Choose a fallback according to the designed policy.
}
~~~

This is an illustrative snippet; `pluginLoader`/`configuredProvider` must exist. In production implementations, log the exception/cause and plugin ID sufficiently for lookup, without logging sensitive configuration data.

### Missing a Required Dependency

For an application that cannot operate if the configured class is missing, you should **fail fast** and report a contextual error (binary name, artifact/version, loader identity, runtime command). Do not catch and ignore it only to produce confusing linkage errors in a later step.

### Do Not Catch Every `Throwable`

A snippet like:

~~~java
try {
    Class.forName(name);
} catch (Throwable ignored) {
    // dangerous: hides linkage errors, OutOfMemoryError, initializer...
}
~~~

is an **illustrative anti-pattern**, not a fix. `ClassNotFoundException` is a specific type of error; `NoClassDefFoundError`, `ExceptionInInitializerError`, `VerifyError`, and `OutOfMemoryError` should not be treated as the same "no plugin".

A plugin system with its own fault-isolation policy may intentionally catch certain `LinkageError`s at a boundary, but it must preserve the cause, classify fatal/nonfatal errors, and make the proper lifecycle decision; do not merge everything into CNFE.

### `ClassNotFoundException` and the Cause Chain

A custom `findClass` may throw:

~~~java
throw new ClassNotFoundException(binaryName, ioException);
~~~

This is an illustrative snippet with `binaryName` and `ioException` variables available. Because a loader fetching bytes from disk/JAR/remote sources may fail due to I/O, the cause chain carries more useful information than a single class name.

If the cause is permission denied, timeout, or resource corruption, fixing the binary name or adding to the classpath is not enough. **Read `getCause()`**, identify the source URL/path and loader; do not throw an empty CNFE and lose the original information.

## 12. Quick Decision Table

| Observed Evidence | First Suspect | Next Step |
|---|---|---|
| `Class.forName(name)` fails, `pluginLoader.loadClass(name)` succeeds | Wrong loader at caller | Choose appropriate explicit plugin loader/TCCL |
| JAR does not contain `p/C.class` entry | Artifact has not packaged the class | Fix build/packaging |
| JAR contains class but URL loader cannot find it | Incorrect URL root/JAR, wrong name, or different delegation | Log `loader.getURLs()`, binary name, path |
| `Class.forName(name,true,loader)` reports initializer error | Class was found but init failed | Investigate `static` code/cause |
| CNFE is in the cause of NCDFE | JVM needs a class at link/runtime | Fix runtime dependency, do not misclassify error type |
| Class loads successfully but `ClassCastException` | Different loader for API class identity | Check defining loader of both types |
| Class loads successfully but `NoSuchMethodError` | Wrong ABI/version | Compare compiler classpath against runtime defining loader |
| `java -jar` fails while `-cp` mode runs | Runtime JAR manifest/dependencies differ | Check `Main-Class`/`Class-Path` and layout |
| Named-module lookup returns `null` | Using `Class.forName(Module, String)` overload | Check module object, resolution/layer, name |
| Fails only on one thread | Different TCCL or framework loader | Print thread name/TCCL, restore context after use |

## 13. Checklist Before Closing a CNFE Ticket

- [ ] Have the **exact binary name** requested, not just a file path or short name.
- [ ] Know which **API overload** was called and how it selects the loader.
- [ ] Distinguish among the caller loader, system loader, TCCL, and plugin loader.
- [ ] Know which JAR/directory the class resides in and that the runtime artifact **actually** contains the `.class` file.
- [ ] Package path structure matches the binary name, including nested class `$`.
- [ ] Classpath or URL root path points to the proper directory/JAR level.
- [ ] Launch mode is `-cp`, `-jar`, or JPMS; rules are not applied mistakenly.
- [ ] If using `java -jar`, manifest `Class-Path`/deployment dependencies are correct.
- [ ] If using JPMS, the module is actually resolved and package accessibility is reviewed separately.
- [ ] Do not confuse checked CNFE with `NoClassDefFoundError`/linkage/initializer errors.
- [ ] Check runtime **dependency version** and parent delegation if the class loaded but behaves incorrectly.
- [ ] Ensure adding JARs as a workaround does not create duplicate shared APIs in child loaders.
- [ ] If the class is loaded, check the defining loader and CodeSource when available.
- [ ] Have tests running against the **actual artifact** rather than only the IDE.
- [ ] Error logs include context, do not expose secrets, and do not catch every Throwable.
- [ ] Choose fail-fast or fallback for plugins based on application requirements.

## 14. Self-Check

**Question 1.** `out/plugin/com/acme/Foo.class` exists. The application only runs `java -cp out/app Main` and calls `Class.forName("com.acme.Foo")`. Why does CNFE occur?

**Answer:** The application loader only has `out/app`; its search path does not include `out/plugin`. Even though the file is on disk, the caller's loader cannot see it. You need to configure the classpath properly or specify a loader with a URL pointing to `out/plugin`.

**Question 2.** Is `Class.forName("com/acme/Foo.class")` correct?

**Answer:** No. The API needs the binary name `com.acme.Foo`; a string with `/` and `.class` is a path/filename.

**Question 3.** Why does `Class.forName(name)` from the host fail while `Class.forName(name, false, pluginLoader)` succeeds?

**Answer:** The first overload uses the caller's loader; the second overload uses the explicitly passed plugin loader. A parent normally does not search inside a child loader.

**Question 4.** A class has a failing initializer. Will `Class.forName(name, true, loader)` definitely throw CNFE?

**Answer:** No. The lookup may succeed while class initialization fails with `ExceptionInInitializerError` or a related error, not CNFE.

**Question 5.** How does `ClassNotFoundException` differ from `NoClassDefFoundError`?

**Answer:** CNFE is a checked exception for a failed explicit lookup; NCDFE is a `LinkageError` when the JVM needs a class definition/initialization that does not succeed, which may contain CNFE in its cause chain.

**Question 6.** Does `Class.forName("int")` retrieve the primitive class object?

**Answer:** No; use `int.class`. `Class.forName("int")` throws CNFE.

**Question 7.** What is the binary name of a nested class declared as `Outer.Inner` in source?

**Answer:** `Outer$Inner` (with a package prefix if applicable), not `Outer.Inner`.

**Question 8.** `Class.forName(module, "p.C")` does not find the class. It should throw CNFE, right?

**Answer:** No. The overload taking `Module` returns `null` if not found per the API contract; verify the overload before classifying the error.

**Question 9.** The class is found with URLClassLoader, but casting it to the host's SPI fails. Is this still CNFE?

**Answer:** No. The issue may be **two runtime SPI types** due to different defining loaders, leading to a `ClassCastException` or another error. The SPI needs to be shared in the parent.

**Question 10.** Why should you not fix the error by doing `catch (Throwable ignored)`?

**Answer:** It hides linkage errors, initializer errors, and critical errors; it is very difficult to diagnose and can continue in an invalid state.

## 15. Workflow to Remember

~~~text
        ClassNotFoundException occurs
                      |
                      v
       Which explicit API? Which name?
                      |
                      v
  Class.forName(String) / loadClass(String)
    or an overload with Module/loader?
                      |
                      v
Select the actual loader (caller/TCCL/explicit)
                      |
                      v
 Is the class in sources visible to the loader?
       /                                \
      No                                Yes
      |                                  |
Fix runtime classpath/URL       Check binary name,
module resolution               parent delegation,
or loader selection             JAR contents, root
      |                                  |
      +----------------+-----------------+
                       |
                       v
                   If found:
  distinguish init/linkage/access/type identity
                       |
                       v
      Test actual artifact + verify cause
~~~

**Conclusion:** `ClassNotFoundException` is a sign that an **explicit class lookup request did not complete with the chosen name and loader**. A lasting fix is not simply copying more `.class` files or catching every exception, but identifying the **lookup API**, **binary name**, **loader graph**, **runtime artifact/search roots**, and **failure phase**. Once the class has been found, continue checking initialization, binary compatibility, and runtime type identity before considering the fix complete.

### Official Documentation

- [Java SE 17 — ClassNotFoundException API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassNotFoundException.html)
- [Java SE 17 — Class.forName and Class.getClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html)
- [Java SE 17 — ClassLoader.loadClass, delegation and resource lookup](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [Java SE 17 — NoClassDefFoundError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoClassDefFoundError.html)
- [Java SE 17 — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html)
- [Java SE 17 — java launcher/classpath/`-jar`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
- [JVMS 17 `5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3)
