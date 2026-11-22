# Distinguishing Classpath, Module Path, and Native Library Path

> Java Core → ClassLoader → Search paths. These three path types serve three different mechanisms: finding Java classes/resources, finding Java named modules, and finding native binaries. You cannot fix errors across all three simply by adding files to a single directory.

## 1. Comparing the Three Paths

| Type | Searched Artifacts | Common Configuration | Mechanism |
| --- | --- | --- | --- |
| **Classpath** | Directory containing a `.class` tree, Java JARs, and resources | `-cp`, `-classpath`, `--class-path` | ClassLoader and unnamed module |
| **Module path** | Exploded module, modular JAR, automatic-module JAR | `--module-path` or `-p` | JPMS discovery, resolution, and access graph |
| **Native library path** | `.dll`, `.so`, `.dylib` containing machine code | `-Djava.library.path=...`, `System.load`, `System.loadLibrary` | JNI/VM and OS dynamic loader |

~~~text
                         Java process
            +-----------------+------------------+
            |                 |                  |
       Classpath         Module path       Native search
     .class / JAR       Named modules       DLL/SO/dylib
            |                 |                  |
       ClassLoader        Module graph       OS/VM linker
~~~

A classloader that loads Java classes does not automatically open a DLL just because the DLL is on the classpath. Conversely, `java.library.path` is not used to find `.class` files. The module path is also not merely a renamed classpath.

## 2. Classpath: Java Classes and Resources

If class `demo.app.Main` is compiled into `out/classes/demo/app/Main.class`, the **classpath root** is `out/classes`, not `out/classes/demo/app`.

Linux/macOS:

~~~bash
java -cp "out/classes:libs/helper.jar" demo.app.Main
~~~

Windows PowerShell/CMD:

~~~powershell
java -cp "out/classes;libs/helper.jar" demo.app.Main
~~~

Separate classpath entries with **`:`** on Unix and **`;`** on Windows. `libs/*` expands to **JARs directly inside the `libs` directory** when processed by the Java launcher; it does not scan recursively. Always use the binary class name (`demo.app.Main`), not the file path of Main.class.

Compile-time and runtime classpaths are **two configurations that can differ**: `javac -cp` is used for type lookup at compile time, while `java -cp` is used for class loading at runtime. If a JAR is present at the compile step but missing at runtime, you may encounter `NoClassDefFoundError` or `ClassNotFoundException` depending on the situation.

- `CLASSPATH` is an environment variable that provides the default value when `-cp` is omitted; prefer explicit configuration for reproducibility.
- When running a main class via the classpath without configuring `-cp`/`CLASSPATH`, the current directory is usually the default classpath.
- `java -jar app.jar` uses `Main-Class` from the manifest. In this launcher mode, `-cp`/`CLASSPATH` is not the normal way to append an additional user classpath. You need the manifest `Class-Path`, a valid distribution, or to run with the main class via `-cp`.
- `System.getProperty("java.class.path")` does not list all classes loaded by custom loaders from plugins/network. Modifying the property after startup does not force the loader to re-read the classpath.

### 2.1. Unnamed Module on JDK 9+

Classes from the classpath belong to the **unnamed module** of the defining classloader; the Java runtime still contains named modules such as `java.base`.

File **ClasspathInfo.java**:

~~~java
public class ClasspathInfo {
    public static void main(String[] args) {
        Module current = ClasspathInfo.class.getModule();
        System.out.println("named=" + current.isNamed());
        System.out.println("name=" + current.getName());
        System.out.println("core=" + Object.class.getModule().getName());
    }
}
~~~

~~~bash
javac --release 17 ClasspathInfo.java
java -cp . ClasspathInfo
~~~

Stdout:

~~~text
named=false
name=null
core=java.base
~~~

`null` is simply the name of an unnamed module, not a class loading failure.

### 2.2. Compiling a Library JAR and Using It from the Classpath

Source tree:

~~~text
classpath-demo/
├─ src-lib/demo/lib/Greeter.java
└─ src-app/demo/app/Main.java
~~~

File **src-lib/demo/lib/Greeter.java**:

~~~java
package demo.lib;

public final class Greeter {
    private Greeter() {}

    public static String message() {
        return "hello from classpath";
    }
}
~~~

File **src-app/demo/app/Main.java**:

~~~java
package demo.app;

import demo.lib.Greeter;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeter.message());
        System.out.println(Greeter.class.getModule().isNamed());
    }
}
~~~

From the classpath-demo directory (POSIX shell):

~~~bash
mkdir -p out/lib out/app dist
javac --release 17 -d out/lib src-lib/demo/lib/Greeter.java
jar --create --file dist/greeter.jar -C out/lib .
javac --release 17 -cp dist/greeter.jar -d out/app src-app/demo/app/Main.java
java -cp "out/app:dist/greeter.jar" demo.app.Main
~~~

Stdout:

~~~text
hello from classpath
false
~~~

The final step is where the **runtime classpath** is determined. Omitting `dist/greeter.jar` from the Java command can cause Greeter not to be found at runtime even though `javac` succeeded.

## 3. Module Path: JPMS Discovery and Resolution

Java 9 introduced the Java Platform Module System. `--module-path` tells the module system where to find module artifacts. It still needs to select **root modules** and follow `requires` directives to build the dependency graph. A JAR placed on the module path is **not automatically resolved**.

Three common types:

- **Explicit named module**: has `module-info.class`; the descriptor declares `requires`, `exports`, `opens`, and services.
- **Automatic named module**: a JAR without a descriptor that is on the module path; when resolved, the module name can come from the manifest `Automatic-Module-Name` or the file name.
- **Unnamed module**: code on the classpath, not an automatic named module, even if the JAR contains a manifest Automatic-Module-Name.

Conditions for using a named-module API:

1. **Resolution**: the module must be in the graph.
2. **Readability**: the caller module must read the providing module.
3. **Exports**: the public API package must be exported to the caller.
4. **Opens** when deep reflection conforming to the module API is needed; `opens` does not mean `exports`.

A single classloader can define multiple modules; **loader parent delegation** and **module readability** are two independent relationships.

### 3.1. Example of Two Named Modules, Java 17+

Structure:

~~~text
src/
├─ demo.greeting/
│  ├─ module-info.java
│  └─ demo/greeting/Greeter.java
└─ demo.consumer/
   ├─ module-info.java
   └─ demo/consumer/Main.java
~~~

**src/demo.greeting/module-info.java**

~~~java
module demo.greeting {
    exports demo.greeting;
}
~~~

**src/demo.greeting/demo/greeting/Greeter.java**

~~~java
package demo.greeting;

public final class Greeter {
    private Greeter() {}

    public static String message() {
        return "hello from module";
    }
}
~~~

**src/demo.consumer/module-info.java**

~~~java
module demo.consumer {
    requires demo.greeting;
}
~~~

**src/demo.consumer/demo/consumer/Main.java**

~~~java
package demo.consumer;

import demo.greeting.Greeter;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeter.message());
        System.out.println(Greeter.class.getModule().getName());
        System.out.println(Main.class.getModule()
                .canRead(Greeter.class.getModule()));
    }
}
~~~

Compile and run from the parent directory of src (POSIX shell):

~~~bash
mkdir -p mods/demo.greeting mods/demo.consumer
javac --release 17 -d mods/demo.greeting \
    src/demo.greeting/module-info.java \
    src/demo.greeting/demo/greeting/Greeter.java
javac --release 17 --module-path mods -d mods/demo.consumer \
    src/demo.consumer/module-info.java \
    src/demo.consumer/demo/consumer/Main.java
java --module-path mods --module demo.consumer/demo.consumer.Main
~~~

Stdout:

~~~text
hello from module
demo.greeting
true
~~~

`mods` contains **two exploded modules**, each subfolder having module-info.class and a package tree. If you remove requires, consumer cannot read the dependency; if you remove exports, the public Greeter cannot be accessed as an API by consumer.

### 3.2. Combining Classpath and Module Path

~~~bash
java --module-path mods --class-path "legacy/*" \
    --module demo.consumer/demo.consumer.Main
~~~

Configuring both paths simultaneously does **not** make a named module read the entire unnamed module. You cannot write `requires unnamed;` in a module descriptor. When migration is needed, consider converting the legacy JAR into an automatic/explicit named module or using `--add-reads module=ALL-UNNAMED` with a clear understanding of its limitations.

Inspecting modules:

~~~bash
java --list-modules
jar --describe-module --file libs/library.jar
java --show-module-resolution --module-path mods \
    --module demo.consumer/demo.consumer.Main
~~~

These commands only run when the JAR/modules in the example actually exist. `java --list-modules` lists system modules; `jar --describe-module` shows a JAR's metadata/automatic module name; `--show-module-resolution` lets you trace the graph at runtime.

## 4. Native Library Path: Finding Operating System Binaries

JNI/native code uses a shared library compiled for the **OS, CPU architecture, and ABI**. The logical name `codec` typically maps to `codec.dll` on Windows, `libcodec.so` on Linux, and `libcodec.dylib` on macOS. The actual name is determined by the platform/JVM: query `System.mapLibraryName("codec")`.

Two APIs:

~~~java
System.loadLibrary("codec");                 // logical name
System.load("/opt/app/native/libcodec.so");  // absolute path Linux
~~~

This is an explanatory snippet and will not run without a real native binary.

- `System.loadLibrary` takes a **logical name**, without directory or extension.
- `System.load` takes an **absolute path** to the native binary.
- The JVM may call `ClassLoader.findLibrary(String)` on the associated loader to obtain an absolute path; otherwise, it searches the effective native library paths, such as `java.library.path`.
- Packaging a DLL/SO **inside a JAR resource** is not enough: the native loader does not automatically load files from a jar: URL. A JNI wrapper may extract the matching binary to a verified file and call `System.load(absolutePath)`.
- Native libraries are subject to their own loader/lifecycle constraints; attempting to load the same binary in two different defining loaders can throw `UnsatisfiedLinkError`. `URLClassLoader.close()` does not guarantee that a native library is unloaded immediately.

Linux/macOS example:

~~~bash
java -Djava.library.path=/opt/app/native -cp "app.jar:libs/*" com.acme.Main
~~~

Windows:

~~~powershell
java -Djava.library.path="C:\app\native" -cp "app.jar;libs/*" com.acme.Main
~~~

`-Djava.library.path` must appear **before the main class name**. Placing it afterward turns it into an application argument. Changing `System.setProperty("java.library.path", "...")` after JVM startup **does not guarantee** that the runtime updates its native search table.

### 4.1. JVM Native Lookup and the OS Dynamic Linker Are Two Layers

Layer 1: The JVM locates `codec` via `loadLibrary`/`load`. Layer 2: The OS loader locates **dependent binaries** of `codec`, such as `libcrypto.so` or other runtime DLLs. Linux uses `LD_LIBRARY_PATH`/RPATH/RUNPATH; Windows uses DLL search rules and PATH in certain cases; macOS uses `@rpath`/loader paths/signing. You cannot assume that having a correct `java.library.path` alone guarantees all native dependencies will be found.

### 4.2. Java Example for Observing Configuration Only

**NativePathView.java**

~~~java
public class NativePathView {
    public static void main(String[] args) {
        System.out.println("classpath=" +
                System.getProperty("java.class.path"));
        System.out.println("nativePath=" +
                System.getProperty("java.library.path"));
        System.out.println("mapped=" +
                System.mapLibraryName("codec"));
    }
}
~~~

~~~bash
javac --release 17 NativePathView.java
java -cp . NativePathView
~~~

There is no fixed universal stdout: classpath, nativePath, and mapped filename depend on the OS/JDK/launcher. This sample does not actually load any library.

### 4.3. The JNI Class Is Loaded from the Java Path, While the JNI Binary Is a Separate File

~~~java
public final class NativeBridge {
    static {
        System.loadLibrary("codec");
    }

    public static native int sum(int a, int b);
}
~~~

**NativeBridge.java** can be compiled with:

~~~bash
javac --release 17 NativeBridge.java
~~~

However, initializing or calling `sum` requires a real JNI binary with a matching name/ABI/symbol. The Java class can exist on the classpath/module path while the binary is missing from native search; the failure in that case is a native loading/linking error, not a ClassNotFoundException for the Java bridge class.

## 5. Native Access Restrictions Starting in JDK 24/25

Under JEP 472, JDK 24+ restricts native operations such as `System.load`/`System.loadLibrary`. JDK 25 warns by default for ungranted native access; `deny` mode can throw `IllegalCallerException`.

Caller on the classpath/unnamed module:

~~~bash
java --enable-native-access=ALL-UNNAMED \
    -Djava.library.path=/opt/app/native \
    -cp "app.jar:libs/*" com.acme.Main
~~~

Caller in a named module:

~~~bash
java --enable-native-access=demo.nativeapp \
    --module-path mods \
    --module demo.nativeapp/demo.nativeapp.Main
~~~

**Separation:** `--enable-native-access` grants permission; `java.library.path` locates binaries; `--module-path` locates modules; `-cp` locates Java classes/resources. Enabling permission does not make a missing file appear, and having the file on the right path does not automatically grant permission. JDK 17/21 do not have the same policy/flags as JDK 25.

## 6. Resource Lookup Is Not Native Lookup

A `config/app.properties` file packaged as a resource is typically read via a ClassLoader:

~~~java
try (var stream = Thread.currentThread()
        .getContextClassLoader()
        .getResourceAsStream("config/app.properties")) {
    if (stream == null) {
        throw new IllegalStateException("Missing resource");
    }
    // Process the stream here.
}
~~~

This snippet must reside inside a method that handles IOException. It looks up classloader resources, not `java.library.path`. Named modules add resource encapsulation rules and `Module.getResourceAsStream`; failing to find a resource does not mean a Java class cannot be loaded.

## 7. Diagnosing by Specific Error

| Error | Layer to Inspect |
| --- | --- |
| `ClassNotFoundException` | Binary name, classpath, loader delegation |
| `NoClassDefFoundError` | Runtime dependency, linkage, or prior init failure |
| `FindException` “Module not found” | Module path, root modules, requires |
| `ResolutionException` | Module conflicts, split packages, readability graph |
| `IllegalAccessError`/`InaccessibleObjectException` | Exports, opens, module access |
| `UnsupportedClassVersionError` | Java runtime version and bytecode major version |
| `UnsatisfiedLinkError` | Native filename/location, native ABI, missing dependency, or symbol |
| `IllegalCallerException` on newer JDKs | Native access policy of the caller module |
| Works in IDE but `java -jar` fails | Manifest/dependency distribution/classpath |

**Practical workflow:** read the first error and its cause → identify the missing artifact (`.class`, named module, or DLL/SO) → record `java -version` and the launch command → inspect the appropriate path/loader/module graph/native linker → fix the dependency packaging/version and re-run. Do not change all three paths at once by guessing.

Helpful commands:

~~~bash
java -version
java --help
java --list-modules
jar --list --file libs/library.jar
jar --describe-module --file libs/library.jar
java --show-module-resolution --module-path mods \
    --module demo.consumer/demo.consumer.Main
~~~

The example modules/JARs in these commands must be created or replaced with real files. On HotSpot with unified logging, `java -Xlog:class+load=info ...` can provide a class-loading trace, though the log format is not a JLS contract.

## 8. Checklist and Review Questions

- Classpath finds Java classes/resources in the unnamed module, module path performs module discovery/resolution, and native path finds OS binaries.
- A JAR present on the module path is not necessarily **resolved**.
- An automatic module has a name; an unnamed module from the classpath has no name.
- A loader seeing a class does not mean the caller module is permitted to access the package.
- The classpath separator on Unix is `:`, and on Windows it is `;`.
- `System.loadLibrary("codec")` does not take the full filename `libcodec.so` as its argument.
- Placing a DLL inside a JAR does not automatically cause the OS linker to open the DLL.
- `java.library.path` does not govern the entire lookup of dependent native libraries.
- Running `java -jar` does not append `-cp` the way launching a main class does.
- `--enable-native-access` on newer JDKs does not replace `java.library.path`.
- Changing system properties after startup does not guarantee that built-in loaders reload their search paths.

## 9. Official Documentation

1. [Java launcher JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html) — `--class-path`, `--module-path`, `--module`, `--enable-native-access`.
2. [javac JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html) — compiler paths.
3. [ClassLoader Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html) — class loading, resource lookup, `findLibrary`.
4. [System Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.html) — `load`, `loadLibrary`, `mapLibraryName`.
5. [ModuleFinder Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/module/ModuleFinder.html) — explicit and automatic modules.
6. [JEP 261](https://openjdk.org/jeps/261) — Java Platform Module System.
7. [JEP 472](https://openjdk.org/jeps/472) — restricted JNI native access and warnings starting in JDK 24.

**Remember:** Before fixing a search path, properly classify whether the issue involves a Java class, a Java module, or a native binary. These are three separate mechanisms, each requiring its own tools and remediation.
