# What Is Classpath and How to Determine the Root Directory in Java

A Java program that wants to load `com.example.app.Main` needs to know **where to find the bytecode**. The JVM does not scan the entire disk to look for a file named `Main.class`; in the traditional classpath model, the class loader uses the class's **binary name** and the configured **classpath entries** to determine the exact relative location.

The most important point: **the classpath root is the directory that precedes the entire package path**. If the file is located at `project/out/com/example/app/Main.class` and declares `package com.example.app;`, then the root is `project/out`, not `project/out/com/example/app`.

This article belongs to the **Search Paths** group of Java core – classloader. The goal is to understand the definition of classpath, determine the root directory for a package/default package, compile and run Java 17+ with the correct root, use JARs/resources/classpath wildcards, and diagnose errors.

## 1. What Is Classpath?

Classpath is a list of locations used to search for classes and resources in the class-path-based class loading model. Common entries include:

- **A directory** containing the compiled package tree, for example `out` or `build/classes/java/main`.
- **A JAR** containing `.class` entries and resources, for example `lib/helper.jar`.
- **A wildcard** `lib/*`, which the Java launcher expands into the JARs directly inside that directory.

The classpath of the `javac` command helps the compiler find dependent classes/types during compilation. The classpath of the `java` command helps the runtime find classes/resources during execution. These two sets can differ; dependencies needed at runtime must be present on the appropriate runtime search path.

**Different types of paths:**

| Concept | What is it used for? | Example |
| --- | --- | --- |
| Source root | Holds `.java` source files for the compiler/build tool | `src/main/java` |
| Classpath root | Holds the package tree of `.class` files or resources | `out`, `target/classes` |
| Working directory | Current directory of the process, serving as the anchor for relative paths | `project`, `user.dir` |
| `PATH` | Operating system variable for locating `java`/`javac` commands | `JDK/bin` |
| `CLASSPATH` | Environment variable that can provide the classpath when `-cp` is omitted | `out;lib/x.jar` on Windows |
| Module path | Where the Java module finder locates JPMS module artifacts | `--module-path mods` |

Do not confuse `PATH` with `CLASSPATH`. If the machine recognizes the `java` command but throws `ClassNotFoundException`, modifying `PATH` alone generally does not resolve the cause.

`import com.example.Foo;` in source code also **does not automatically add** the library to the classpath. `import` is merely Java syntax that allows referencing short names; the compiler and the JVM still require the appropriate class source.

## 2. How to Derive the Classpath Root from a Package

Example:

```java
package com.example.app;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello");
    }
}
```

Binary name: `com.example.app.Main`.

The bytecode path **relative to a directory classpath entry**: `com/example/app/Main.class`. The dots separating packages in the binary name are mapped to the corresponding directory separator characters in the class file path, and the `.class` suffix is appended.

If the output tree is:

```text
project/
├── src/
│   └── com/example/app/Main.java
└── out/
    └── com/
        └── example/
            └── app/
                └── Main.class
```

then the correct root is `out`:

```text
Classpath entry        Relative class path
      out         +    com/example/app/Main.class
                       |
                       v
             out/com/example/app/Main.class
```

From the `project` directory, run:

```bash
java -cp out com.example.app.Main
```

The command below uses the **wrong root**:

```bash
java -cp out/com/example/app com.example.app.Main
```

The JVM will try to look for `out/com/example/app/com/example/app/Main.class`, so it may report `Could not find or load main class com.example.app.Main`.

### Method for determining the root given the actual file

1. Find the **binary name** from the `package` and class name, for example `org.acme.Parser`.
2. Convert it into the relative path `org/acme/Parser.class`.
3. Strip that relative path from the end of the actual class file path; the remaining part is the **directory root**.

| Actual file | Binary name | Root |
| --- | --- | --- |
| `D:\work\build\classes\org\acme\Parser.class` | `org.acme.Parser` | `D:\work\build\classes` |
| `/srv/demo/out/a/b/Task.class` | `a.b.Task` | `/srv/demo/out` |
| `out/Hello.class`, no package declaration | `Hello` | `out` |
| `target/classes/com/demo/Main.class` | `com.demo.Main` | `target/classes` |

**Default package:** If a class has no `package` line, the binary name is `Hello`, the relative path is simply `Hello.class`, and the root is the directory directly containing the file. The default package is discouraged for multi-module/multi-package applications because namespaces are difficult to manage.

**Nested class:** `com.example.Outer.Inner` in source syntax typically has the binary name `com.example.Outer$Inner`; the file may be `Outer$Inner.class` under the `com/example` tree. The classpath root is still the directory before `com`.

**Source layout vs. runtime:** The location `src/com/example/Main.java` is a source path. `javac -d out` can automatically place output in the proper package tree inside `out`. The runtime needs the directory containing the **class output**, and does not automatically load source code under `src` just because `import` was used.

## 3. Configuring with `-cp` and Operating System Differences

The Java launcher has three equivalent options: `-cp`, `-classpath`, and `--class-path`.

```bash
java --class-path out com.example.app.Main
```

Multiple entries are joined using an OS-specific separator character:

| Operating system | Separator | Example |
| --- | --- | --- |
| Windows | Semicolon `;` | `java -cp "out;resources;lib/helper.jar" com.example.app.Main` |
| Linux/macOS | Colon `:` | `java -cp "out:resources:lib/helper.jar" com.example.app.Main` |

Wrapping the classpath value in quotes is good practice, especially if paths contain spaces or special shell characters. The `:` in `C:\work` on Windows is **not** a separator character between classpath entries.

If `out` is a relative path, it is resolved relative to the **working directory** where the process was started:

```bash
cd out
java -cp . com.example.app.Main
```

At this point, `.` is `out`. If run from `project`, `-cp .` points only to `project` and **does not automatically search down into `project/out`**. The classpath is not a mechanism that recursively scans all subdirectories.

### Default value and environment variable

When running a class on the classpath, if **neither `-cp` is provided nor the `CLASSPATH` variable is set**, the default classpath is the working directory `.`. However, **once `-cp` is provided**, Java does not automatically append `.` at the end. To use both the working directory and a JAR, specify it explicitly:

```bash
java -cp ".;lib/helper.jar" com.example.app.Main
```

The line above is for Windows; on Unix, replace `;` with `:`. If the class output is in `out`, you must specify `out` instead of `.`.

You should provide the classpath explicitly in scripts/IDEs/build tools rather than relying on a machine-wide `CLASSPATH`, because environment variables easily cause discrepancies across machines. `-cp` on the command line overrides `CLASSPATH` for that launcher process.

## 4. Standalone Java 17+ Example: Two Classes, Two Roots

Create the structure:

```text
classpath-demo/
├── src/
│   └── com/
│       └── example/
│           ├── app/Main.java
│           └── util/Greeter.java
├── resources/
│   └── com/example/app/config.properties
└── out/   (created before compiling)
```

File `src/com/example/util/Greeter.java`:

```java
package com.example.util;

public final class Greeter {
    private Greeter() {}

    public static String message() {
        return "Hello from Greeter";
    }
}
```

File `src/com/example/app/Main.java`:

```java
package com.example.app;

import com.example.util.Greeter;
import java.io.InputStream;
import java.util.Properties;

public class Main {
    public static void main(String[] args) throws Exception {
        System.out.println(Greeter.message());

        Properties properties = new Properties();
        try (InputStream stream =
                Main.class.getResourceAsStream("config.properties")) {
            if (stream == null) {
                throw new IllegalStateException("Resource not found");
            }
            properties.load(stream);
        }

        System.out.println("mode=" + properties.getProperty("mode"));
        System.out.println("main=" + Main.class.getName());
    }
}
```

File `resources/com/example/app/config.properties`:

```properties
mode=demo
```

From the `classpath-demo` directory, if `out` does not exist yet, create it:

```bash
mkdir out
```

Compile with JDK 17 or later:

```bash
javac --release 17 -d out src/com/example/util/Greeter.java src/com/example/app/Main.java
```

With `-d out`, the compiler generates:

```text
out/
└── com/example/
    ├── app/Main.class
    └── util/Greeter.class
```

The actual path of the resource remains `resources/com/example/app/config.properties`; `javac` does not automatically copy resource files into `out`.

Run on **Windows**:

```bash
java -cp "out;resources" com.example.app.Main
```

Run on **Linux/macOS**:

```bash
java -cp "out:resources" com.example.app.Main
```

Exact stdout of both:

```text
Hello from Greeter
mode=demo
main=com.example.app.Main
```

Explanation:

- The root `out` enables locating `com/example/app/Main.class` and `com/example/util/Greeter.class`.
- The root `resources` enables locating `com/example/app/config.properties`.
- `Main.class.getResourceAsStream("config.properties")` searches relative to `Main`'s package, which is `com/example/app`.
- `Main.class.getName()` returns the binary name `com.example.app.Main`.

Try **omitting `resources`**:

```bash
java -cp out com.example.app.Main
```

The program still finds `Main` and `Greeter`, prints the first line, and then throws `IllegalStateException: Resource not found`. This shows that the **class root** and the **resource root** can be two separate entries. If resources are copied into `out/com/example/app` during the build, `out` alone can also be sufficient.

Try **running with the wrong name `Main`**:

```bash
java -cp out Main
```

The command cannot find `Main` in the default package; the actual binary name is `com.example.app.Main`. This is a class name issue, not just a path issue.

## 5. `javac -cp` vs. `javac -d`

These two options often appear together, but they serve different purposes:

- `-d out`: **places `.class` output into the root `out`**, along with the package tree.
- `-cp something`: **specifies where the compiler searches for dependent classes and libraries**.

Suppose `Greeter.class` has already been compiled into `out`, and you only want to recompile `Main.java`:

```bash
javac --release 17 -cp out -d out src/com/example/app/Main.java
```

The compiler uses `out` to resolve `com.example.util.Greeter`, while the new output for `Main` is also written into `out`.

The runtime classpath is a separate setting:

```bash
java -cp "out;resources" com.example.app.Main
```

(Windows; on Linux/macOS, replace `;` with `:`.)

A dependency present on the compile classpath **does not automatically appear** on the runtime classpath. This explains the "`javac` works fine, but `java` is missing a class" error when launching manually and forgetting a required JAR.

In projects using Gradle/Maven, the build tool assembles the compile and runtime classpaths from dependency scopes/configurations. When running via an IDE or build tool, check the **actual run configuration** rather than assuming the compiler records every dependent library inside `Main.class`.

## 6. Classpath Root Inside a JAR

A JAR is a ZIP archive containing entries relative to the **root of the archive**. If you want the JAR to provide `com.example.app.Main`, the entry must be:

```text
com/example/app/Main.class
```

Do not accidentally store it as `out/com/example/app/Main.class` or `src/com/example/app/Main.java` and expect the loader to recognize it as the corresponding runtime class.

After compiling the example in Section 4, package it using the JDK `jar` tool on **a single cross-platform-compatible line**:

```bash
jar --create --file app.jar --main-class com.example.app.Main -C out . -C resources .
```

`-C out .` tells `jar` to take the contents under `out` and store them **relative to the root `out`**. `-C resources .` does the same for resources. `--main-class` writes `Main-Class` into the manifest.

Verify:

```bash
jar --list --file app.jar
java -jar app.jar
```

In the output of `jar --list`, besides the manifest and directory entries, the important files will be:

```text
com/example/app/Main.class
com/example/util/Greeter.class
com/example/app/config.properties
```

The stdout of `java -jar app.jar` remains:

```text
Hello from Greeter
mode=demo
main=com.example.app.Main
```

You can run the JAR as a classpath entry:

```bash
java -cp app.jar com.example.app.Main
```

### `-jar` does not behave like `-cp`

`java -cp app.jar com.example.app.Main` loads the main class by the name you pass from the classpath entry. `java -jar app.jar` reads the main class from the manifest and **does not use the classpath specified by `-cp` or the `CLASSPATH` variable as in standard class execution mode**. To reference dependencies outside an executable JAR, you can use the manifest `Class-Path` attribute or an appropriately designed launcher/packaging.

The manifest `Class-Path` references URLs/JARs according to rules relative to **the location of the JAR containing the manifest**, not simply any relative path anchored at `user.dir`.

In particular, a **Spring Boot executable JAR** typically has a `BOOT-INF/classes` and `BOOT-INF/lib` structure with its own launcher. Do not treat that structure as a flat JAR where `java -cp boot.jar com.example.Main` will always work; use the supported launcher or `java -jar`.

## 7. Does `lib/*` Add Everything?

No. The Java launcher's wildcard syntax such as `lib/*` expands to the JARs directly inside the `lib` directory. For example:

```bash
java -cp "out;lib/*" com.example.app.Main
```

on Windows; on Linux/macOS:

```bash
java -cp "out:lib/*" com.example.app.Main
```

Limitations:

- `lib/*` **does not recursively scan** `lib/plugins/**` or subdirectories.
- `lib/*` **does not automatically add** a directory root such as `lib/classes` or `.class` files located directly under `lib`.
- If you also need the class directory `lib/classes`, add the `lib/classes` entry explicitly.
- The expansion order of JARs by a wildcard is not necessarily stable; if multiple JARs contain the same class name, do not rely on "which JAR wins" as a long-term contract.
- Quoting the classpath generally prevents the shell from expanding the wildcard itself before the Java launcher processes it.

Classpath entries are searched according to the mechanism of the corresponding loader. On a standard classpath, multiple copies of a class across different entries can lead to loading the wrong dependency version and `NoSuchMethodError` or `NoSuchFieldError` errors at runtime.

## 8. Resource Paths: Different from Class Binary Names

The classpath can contain `config.properties`, JSON, XML, templates, images, or other resources. With `Main` in package `com.example.app`:

```java
java.net.URL relative =
        Main.class.getResource("config.properties");

java.net.URL absolute =
        Main.class.getResource(
                "/com/example/app/config.properties");

java.net.URL loaderResource =
        Main.class.getClassLoader()
                .getResource("com/example/app/config.properties");
```

This is **an illustrative snippet inserted into the `Main` class**. All three paths above point to the matching resource in the Section 4 example when using the standard application classloader.

| API | Lookup rule |
| --- | --- |
| `Class.getResource("x")` | Relative to that class's package |
| `Class.getResource("/a/b/x")` | Absolute from the resource root (the leading `/` is handled by this API) |
| `ClassLoader.getResource("a/b/x")` | Resource name relative to the loader root; normally **without** a leading `/` |

For bootstrap classes, `SomeCoreClass.class.getClassLoader()` can be `null`, so do not call `getResource` on a `null` value.

When a resource is inside a JAR, its URL may look like `jar:file:/.../app.jar!/com/example/app/config.properties`. Not every resource is a physical `java.io.File` on the filesystem. Reading via `getResourceAsStream` is usually safer across both directories and JARs.

Named modules also enforce module encapsulation, especially for resources in unopened packages. Therefore, how resources are visible through the API may change when migrating an application from the classpath to the module path.

## 9. Classpath vs. Module Path

Since Java 9, JPMS has introduced the **module path**. Example syntax for running a named module:

```bash
java --module-path mods --module m.example/com.example.Main
```

This is **illustrative syntax** and only works when `mods` contains an appropriate named module `m.example`. It does not apply directly to the program without `module-info.java` in Section 4.

| Classpath | Module path |
| --- | --- |
| Typically holds classes of each loader's unnamed module | Module finder discovers named modules |
| Configured with `-cp`/`--class-path` | Configured with `-p`/`--module-path` |
| Does not require `module-info.java` | Explicit modules use `module-info.class` |
| Maps directory/JAR entries by package | Adds module graph, readability, exports, and opens |
| Suitable for traditional Java applications | Suitable for code organized under JPMS |

Although modules also contain class files arranged by package structure, placing an artifact on the module path is **not completely synonymous** with placing that same artifact on the classpath. Module boundaries and `ModuleLayer` loader mappings can alter accessibility and resolution behavior.

## 10. How to Determine the Actual Classpath of a Running Application?

Some diagnostic APIs:

```java
System.out.println("classpath="
        + System.getProperty("java.class.path"));

System.out.println("working directory="
        + System.getProperty("user.dir"));

System.out.println("defining loader="
        + Main.class.getClassLoader());

System.out.println("code source="
        + Main.class.getProtectionDomain().getCodeSource());
```

This is **an illustrative snippet added to `Main.main`**, with no fixed stdout since it depends on the OS, launcher, and build tool.

- `java.class.path` is useful for classpath-based apps; it **does not list every source** that a custom loader might read.
- `user.dir` specifies the process working directory at startup; it is not necessarily the directory containing `Main.java` or the JAR.
- `Main.class.getClassLoader()` reveals the **defining loader** of `Main`.
- `getProtectionDomain().getCodeSource()` can hint at the artifact/root directory, but **may be `null`** or carry no useful filesystem location for bootstrap/custom loaders.

Inspection tools:

```bash
javap -classpath out com.example.app.Main
jar --list --file app.jar
```

The `javap` command verifies whether the class file can be found from the root `out` and prints class/bytecode information; `jar --list` shows the entry paths inside the JAR. If you need to investigate HotSpot class loading, you can enable:

```bash
java -Xlog:class+load=info -cp out com.example.app.Main
```

This log output is fairly verbose and its format depends on the JDK. It helps trace class sources, but does not prove that all class loaders in the application use the same classpath.

### Output conventions in build tools

| Build tool | Default source root | Common runtime classes root | Common resource output |
| --- | --- | --- | --- |
| Gradle Java plugin | `src/main/java` | `build/classes/java/main` | `build/resources/main` |
| Maven | `src/main/java` | `target/classes` | `target/classes` |

These paths are **customizable conventions**. An IDE or build tool may combine multiple roots and dependency JARs for a run configuration. Do not just look at `src/main/java` and assume that directory is the runtime classpath.

## 11. Is Classpath How Every ClassLoader Finds Classes?

No. Java has built-in loaders and custom loaders:

- **Bootstrap loader** defines the core classes of the JVM/Java SE; `String.class.getClassLoader()` is normally `null`.
- **Platform loader** handles the appropriate platform classes within the runtime image/module system.
- **Application loader** typically defines classes run from the application classpath and applicable modules.
- **Custom loader** can locate classes itself from a URL, memory, a database, a plugin archive, or another source; it may or may not use a classpath.

Example:

```java
ClassLoader system = ClassLoader.getSystemClassLoader();
Class<?> type = system.loadClass("com.example.app.Main");
System.out.println(type.getClassLoader());
```

This is **an illustrative snippet** that must be placed inside a method handling `ClassNotFoundException`, and the class must be visible from the system loader. `loadClass` may delegate to a parent; the loader receiving the request is not necessarily the loader that **defines** the class.

A runtime class is identified by **binary name + defining loader**. Two different loaders can define two classes with the same name that are two distinct runtime types, easily leading to a `ClassCastException`. When multiple plugins/containers are involved, you need to inspect loaders and module layers, not just the `-cp` string.

## 12. Common Errors and Troubleshooting Table

| Symptom | Cause to check | Action |
| --- | --- | --- |
| `Could not find or load main class` | Wrong binary name or wrong root | Combine the root with the relative path `a/b/C.class` and compare against the file |
| `NoClassDefFoundError: ... (wrong name: ...)` | The class file was found, but the internal name does not match | Check `package`, output location, and the class name passed at launch |
| `ClassNotFoundException` in `Class.forName` | The selected loader cannot see the class | Check the caller loader/explicit loader, dependencies, and binary name |
| `NoClassDefFoundError` at runtime | Missing dependency, linking error, or prior initialization failure | Read the initial cause and inspect runtime artifacts |
| `NoSuchMethodError` / `NoSuchFieldError` | Incompatible runtime JAR version | Check duplicate dependencies/versions and method/field descriptors |
| Resource is always `null` | Missing resource root or lookup path differs from package | Check the file inside the root/JAR and the `getResource` API call |
| Runs in the IDE, fails in the terminal | The IDE uses a different runtime classpath | Compare the Java command and the actual output roots |
| Missing libraries when running `-jar` | Mistakenly relying on `-cp` in `-jar` mode | Check manifest/launcher/dependency packaging |
| `lib/*` misses `.class` files in subdirectories | Wildcards only handle matching JARs | Add the actual directory entry explicitly |
| Spring Boot JAR fails to run with standard `java -cp` | The JAR has a special `BOOT-INF` layout | Run with a supported launcher, typically `java -jar` |

### Immediately actionable debugging workflow

1. **Determine the binary name.** Check `package`, class name, and `$` for nested classes.
2. **Locate the actual `.class` file.** In the output folder or JAR entry, is it `a/b/C.class`?
3. **Find the root.** Strip the exact `a/b/C.class` tree from the actual path; the portion before it is the root.
4. **Verify the command and OS.** What is `-cp` set to, is the separator right, and which working directory is it running from?
5. **Compare compile vs. runtime.** Does `javac -cp` include a dependency that `java -cp` is missing?
6. **Check resources separately.** `Class.getResource` and `ClassLoader.getResource` handle path names differently.
7. **If it still fails, check loader/module.** Which loader defines the class, and is there a custom policy or named module?
8. **Check the root cause.** The error may also stem from binary incompatibility or initialization failure, not simply a missing path.

## 13. Self-Check

**Question 1.** `Main.class` is at `C:\work\out\com\acme\Main.class` and its package is `com.acme`. Which `-cp` should you use?

**Answer:** `C:\work\out` because the JVM will look for `com/acme/Main.class` beneath the root.

**Question 2.** From the example project directory, why does `java -cp . com.example.app.Main` fail to run if you only compiled with `-d out`?

**Answer:** `.` points to the project directory, while the actual file resides under `out/com/example/app`. You need to use `-cp out`, or change the working directory to `out` and use `-cp .`.

**Question 3.** On Windows, if you want classes in `out` and resources in `resources`, which command is correct?

**Answer:** `java -cp "out;resources" com.example.app.Main`; on Linux/macOS, use `"out:resources"`.

**Question 4.** Does `-cp lib/*` automatically find `lib/classes/com/acme/Thing.class`?

**Answer:** No. The launcher wildcard handles JARs directly inside `lib` and does not recurse into the directory class root `lib/classes`.

**Question 5.** When `com.example.app.Main` is packaged inside `app.jar`, what is the entry name inside the JAR?

**Answer:** `com/example/app/Main.class`, without the `out/` or `src/` prefix.

**Question 6.** Why does `Main.class.getResource("config.properties")` look for the file under `resources/com/example/app`?

**Answer:** This API uses a resource name relative to the `com.example.app` package. The runtime must also have the `resources` entry on the classpath.

**Question 7.** Can you use `java -cp "extra.jar" -jar app.jar` to arbitrarily add dependencies to the classpath in `-jar` mode?

**Answer:** Not under the `-jar` launcher's standard classpath selection mechanism. You need to use the manifest `Class-Path` or a supporting launcher/packaging.

**Question 8.** Compilation succeeds with `javac -cp lib/helper.jar`, but at runtime `helper.SomeType` is missing. What should you check?

**Answer:** Whether the runtime classpath includes `helper.jar` or an equivalent way of supplying that dependency. `javac` does not remember or automatically add `-cp` for the `java` command.

**Question 9.** Why might a class present on the classpath still be unusable inside a plugin?

**Answer:** The plugin loader may use a different namespace/source/policy, the class may actually be defined by a different loader, or module access restrictions may apply. You need to check the defining loader and module layer.

**Question 10.** A default-package class `Hello.class` is located in `out`; how do you run it?

**Answer:** `java -cp out Hello` because the binary name is `Hello` and the relative class path is `Hello.class`.

## Key Takeaways

**The root is not the folder directly containing a packaged class: the root sits above the entire package directory tree.** Always calculate:

```text
Classpath root + binaryName.replace('.', '/') + ".class"
        = class path in a directory entry
```

For a JAR, the relative part must be the entry from the **root inside the archive**. Then separately verify the resource root, runtime dependencies, launcher mode (`-cp` or `-jar`), and the actual class loader as projects grow more complex.

Authoritative sources:

- [Java 17 `java` launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html) – classpath, wildcards, `-jar`, and module path.
- [Java 17 `javac`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html) – `-d`, compile classpath, and type search.
- [Java 17 `jar`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html) – archive entries and manifest.
- [Java SE 17 `ClassLoader` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html) – class/resource lookup and parent delegation.
