# Runtime image, jrt:, and the removal of rt.jar

Starting with **Java 9**, the JDK transitioned to a **modular runtime image** model: the classes and resources of the Java platform itself are organized into runtime **modules**, replacing the approach of shipping most of the core library via the **`rt.jar`** file as in Java 8 and earlier. When referencing a resource of the modern JDK, you will commonly encounter URLs with the **`jrt:`** scheme, such as `jrt:/java.base/java/lang/Object.class`.

This is a change in **how runtime classes are packaged and accessed**, directly related to how **built-in class loaders** locate platform classes. It **does not mean class loaders were removed**, that the JVM stopped using `.class` bytecode, or that all application JARs disappeared.

This article explains why `rt.jar` no longer exists, what `jrt:` actually represents, the differences between modules, runtime images, JARs, and JMODs, and how to inspect them using Java 17+ APIs and tools.

## 1. What is a runtime image?

A **runtime image** is the set of components required to run a Java program, including the Java launcher, the JVM, modules containing runtime libraries and resources, along with the appropriate native and configuration components.

Since Java 9, the runtime image is organized by **modules**. For example:

- `java.base`: foundational APIs such as `java.lang`, `java.util`, `java.io`, and `java.nio`; every Java module reads `java.base` according to the module system rules.
- `java.logging`: Java's standard logging API.
- `java.sql`: the JDBC APIs.
- `java.xml`: standard XML APIs.
- Several `jdk.*` modules: tools or APIs belonging to the JDK, not necessarily present in every runtime image.

Not every runtime image contains the same set of modules. A full JDK typically includes many modules and tools; a **custom runtime image** created by `jlink` can include only the modules needed by an application and their dependencies.

### Comparing the pre- and post-Java 9 models

~~~text
JDK 8 and earlier (simplified)
└─ JRE / runtime directory
   └─ lib/
      └─ rt.jar             ← many platform classes, e.g., java.lang.String
   └─ other libraries, files, and native components

Java 9+ (simplified)
└─ runtime image
   ├─ bin/java
   ├─ lib/modules           ← runtime image container of common JDK implementations
   ├─ conf/                 ← runtime configuration
   └─ other libraries, files, and native components
           ↓
     modules java.base, java.logging, java.sql, ...
~~~

This diagram is a **conceptual illustration**, not a guarantee that every Java distribution or OS has the exact directory tree above. The module specification and standard APIs matter more than application code assuming internal JVM file names. In HotSpot/OpenJDK, `lib/modules` typically uses a proprietary runtime image format, not a ZIP/JAR file that can be opened with `JarFile`.

**Distinguishing "runtime image" and "module"**: a runtime image is the entire execution environment; each module is a named unit and dependency/encapsulation boundary within that environment. A `module-info.class` describes which packages a module contains, which modules it requires, which packages it exports/opens, and so on. A runtime image contains many modules, not just a single renamed "giant JAR".

## 2. Why was `rt.jar` removed?

In Java 8, classes for most of the core runtime library were stored in `rt.jar`. Legacy tools often went directly to:

~~~text
<JAVA_HOME>/jre/lib/rt.jar
~~~

to locate `java/lang/Object.class`, `java/lang/String.class`, or use `JarFile` to iterate over all standard classes.

Starting with Java 9, **JEP 220 — Modular Run-Time Images** restructured the runtime image to support the module model, flexible packaging, and better internal management. Files such as **`rt.jar`**, **`tools.jar`**, and **`dt.jar`** no longer exist in their old roles in the modular JDK. The nested `jre/` directory structure inside the JDK installation directory also no longer exists in the old way.

This change solves several problems:

1. **Modular organization**: the standard library has clearer identities, dependencies, and access rules compared to a flat collection of classes.
2. **Right-sized runtimes**: `jlink` can assemble only the required modules to distribute a dedicated runtime image for an application.
3. **Flexibility for the JVM and tools in internal representation**: implementations are no longer forced to use the ZIP structure of `rt.jar`.
4. **Reducing code that depends on implementation paths**: applications and tools have interfaces such as `jrt:` and Java APIs to access modules and resources in a proper way.

**What did not change:** bytecode is still based on the **ClassFile** format; Java still loads classes, verifies bytecode, links, and initializes classes. JARs remain very common for packaging libraries and applications, on both the classpath and the module path. Removing `rt.jar` only applies to **how JDK runtime classes are packaged**—it does not eliminate the `.jar` format.

## 3. What is `jrt:`?

In practical terms, `jrt:` stands for the **Java runtime image protocol/scheme**. It provides a **logical address space** for modules, classes, and resources stored in the runtime image, allowing tools to use URIs/URLs to access them without knowing how the internal container file is organized.

For example:

~~~text
jrt:/java.base/java/lang/Object.class
│    │         └─ resource/class path inside the module
│    └─ module name java.base
└─ jrt scheme
~~~

With a standard JDK 17, `ClassLoader.getSystemResource("java/lang/Object.class")` can return a URL:

~~~text
jrt:/java.base/java/lang/Object.class
~~~

whereas before Java 9, the same resource lookup could produce a URL of the form:

~~~text
jar:file:/.../jre/lib/rt.jar!/java/lang/Object.class
~~~

The key point is that **`jrt:` is not an ordinary file path on disk**. `jrt:/java.base/java/lang/Object.class` does not mean a physical directory named `jrt:` exists on disk, nor is it an HTTP request downloading a class over the network.

### How the `jrt:` scheme differs from `jar:` and `file:`

| Scheme | Common meaning | Example |
| --- | --- | --- |
| `file:` | A file or directory provided by the operating system. | `file:/opt/app/classes/Demo.class` |
| `jar:` | An entry located inside a JAR/ZIP referenced via a URL. | `jar:file:/opt/app/lib/api.jar!/com/example/Api.class` |
| `jrt:` | A module and resource inside a **runtime image**. | `jrt:/java.base/java/lang/Object.class` |

`jrt:` solves the problem of **resource identification and access**, whereas whether a class is actually defined by the bootstrap, platform, or application loader is an aspect of **class loading**. You should not see the `jrt:` scheme and infer that "all classes accessed via `jrt:` belong to the bootstrap loader".

## 4. The runtime image provides a virtual `jrt` file system

Alongside `jrt:` URLs, modern JDKs include an **NIO FileSystem Provider** for the runtime image. The root of the file system has the URI `jrt:/`.

A typical structure when browsing through the provider:

~~~text
jrt:/
├── modules/
│   ├── java.base/
│   │   ├── module-info.class
│   │   ├── java/lang/Object.class
│   │   └── ...
│   ├── java.logging/
│   └── ...
└── packages/
    ├── java.lang/
    ├── java.util/
    └── ...
~~~

**It is very easy to confuse these two kinds of paths**:

- **URL to a resource**: `jrt:/java.base/java/lang/Object.class`.
- **Path in the `jrt` FileSystem**: `/modules/java.base/java/lang/Object.class`.

These are **two representations of the same logical data source** following the conventions of two different APIs. When using `Files.exists` or `Files.readAllBytes` with the JRT NIO FileSystem, obtain a `Path` from the provider and use the `/modules/...` structure; do not call `Path.of("jrt:/...")` expecting the default file system to understand that scheme.

The `/packages/...` paths can assist with package-to-module lookup in the virtual structure; they do not mean packages must exist as real directories on disk. The contents of each image depend on the set of modules linked into that image.

## 5. Java 17 example: reading a class in `java.base` via URL and the JRT FileSystem

Create a file named **`RuntimeImageExplorer.java`**:

~~~java
import java.net.URI;
import java.net.URL;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

public class RuntimeImageExplorer {
    public static void main(String[] args) throws Exception {
        Module module = Object.class.getModule();
        URL resource = Object.class.getResource("Object.class");

        System.out.println("Module: " + module.getName());
        System.out.println("Resource scheme: " + resource.getProtocol());

        URI imageUri = URI.create("jrt:/");
        try (FileSystem image = FileSystems.newFileSystem(imageUri, Map.of())) {
            Path classFile = image.getPath(
                    "/modules/java.base/java/lang/Object.class");

            System.out.println("Class exists: " + Files.isRegularFile(classFile));

            byte[] bytes = Files.readAllBytes(classFile);
            System.out.printf(
                    "ClassFile magic: %02X%02X%02X%02X%n",
                    bytes[0] & 0xFF,
                    bytes[1] & 0xFF,
                    bytes[2] & 0xFF,
                    bytes[3] & 0xFF);
        }
    }
}
~~~

Compile and run with **JDK 17 or newer**, from the directory containing the file:

~~~bash
javac --release 17 RuntimeImageExplorer.java
java RuntimeImageExplorer
~~~

On a **standard JDK 17 with the `jrt` provider**, stdout is:

~~~text
Module: java.base
Resource scheme: jrt
Class exists: true
ClassFile magic: CAFEBABE
~~~

Explanation:

1. `Object.class.getModule()` returns the module that defines `java.lang.Object`, which is `java.base`.
2. `Object.class.getResource("Object.class")` locates the resource in the same package; the URL uses the `jrt` scheme on a standard modular runtime.
3. `FileSystems.newFileSystem(URI.create("jrt:/"), Map.of())` opens a `FileSystem` supplied by the JRT provider. `try` ensures the file system is closed after use.
4. `image.getPath("/modules/java.base/java/lang/Object.class")` points to the ClassFile inside the virtual structure of the runtime image.
5. The first four bytes of a ClassFile are `CA FE BA BE` (the magic number of the ClassFile format); `%02X` and `& 0xFF` display each byte in hexadecimal.

**Limitations of the example:** It requires an actual modular JDK environment and the `jrt` provider; if a custom image or another JVM lacks the expected resource or provider, the program may not behave as shown above. In real applications, check `resource != null` before using it and handle `IOException` or provider errors appropriately. Do not hard-code that every application class belongs to `java.base`; that is only the case for `Object.class`.

### If you only need to determine a class's module

You do not need to read bytecode:

~~~java
System.out.println(String.class.getModule().getName());
System.out.println(String.class.getClassLoader());
~~~

The snippet above is a **fragment** that can be placed inside a method. On a typical JDK, `String.class` belongs to `java.base`, and `String.class.getClassLoader()` returns `null` to represent the **bootstrap loader** in the API. `null` does not mean the JVM does not use class loading. An application class on the regular classpath belongs to the **unnamed module** of its defining class loader and does not necessarily have a `jrt:` URL.

## 6. How does the runtime image relate to the three built-in class loaders?

In modern Java, three loaders are commonly discussed:

| Loader | General role |
| --- | --- |
| **Bootstrap class loader** | Built into the JVM; defines core platform classes, including most of `java.base`; the Java API typically returns `null` for this loader. |
| **Platform class loader** | Defines many classes in other platform modules of the JDK; accessed via `ClassLoader.getPlatformClassLoader()`. |
| **Application/system class loader** | Responsible for application classes and many libraries visible on the classpath/module path; accessed via `ClassLoader.getSystemClassLoader()`. |

Before Java 9, many resources explained that the bootstrap loader read classes from `rt.jar`, the extension loader read from `lib/ext`, and the application loader read from the classpath. **Do not apply that storage-location model verbatim to Java 9+**. The extension loader mechanism and the `lib/ext` directory belong to the old model; the platform loader replaces that role in the new design, with a different modular organization.

An accurate high-level diagram:

~~~text
             Runtime image (multiple modules)
                  │
                  ├── java.base
                  ├── java.logging
                  ├── java.sql
                  └── other JDK modules
                        │
                        ▼
             Appropriate built-in loader
                        │
                   defines Class
                        ▼
               JVM links/initializes

     Application classpath and module path
                        │
                        ▼
         Application or custom loader
                        │
                   defines Class
~~~

The diagram **does not mean all modules are loaded all at once at startup**. Module resolution establishes the module graph for a run; loading individual classes and when classes are initialized are separate activities.

**Parent delegation still plays a role**, but you cannot infer from the `lib/modules` path that the bootstrap loader loads every module. Some modules are assigned to the platform or application loader, and custom loaders can coexist. Furthermore, whether a module can read another module (`requires`) or export/open packages are module-level access rules, not another name for parent delegation.

## 7. How does `rt.jar` differ from `lib/modules`, `jmods`, and library JARs?

These locations and formats are often mistakenly treated as equivalent:

| Item | Purpose | Can it be used directly as a classpath JAR? |
| --- | --- | --- |
| **`rt.jar`** (Java 8 and earlier) | Contained many core Java platform classes in the legacy runtime JAR. | It is a JAR, but part of the JVM-managed runtime, not an ordinary application library. |
| **`lib/modules`** (common modular JDKs) | Internal implementation container for modules in the running **runtime image**. | **No.** Do not treat it as a ZIP/JAR or an application dependency to pass to `-cp`. |
| **`jmods/*.jmod`** (full JDK, when present) | Input module artifacts typically used by tools such as `jlink`. | **No.** JMOD differs from JAR and is not a format placed directly on the runtime module path. |
| **Regular JARs**, including **modular JARs** | Distributing libraries or applications. | Can be used on the classpath or module path, depending on configuration and JAR characteristics. |

In particular, a **JMOD** can package both classes and resources/native files to support assembling a runtime image. Meanwhile, `jrt:` represents data **already inside the runtime image**, not a scheme pointing to any `.jmod` file on disk.

Java 9+ does not force every application to write its own `module-info.java` or convert every dependency into a JMOD. **The classpath and unnamed modules are still supported**. Having third-party libraries in `.jar` files does not conflict with the removal of the JDK's `rt.jar`.

## 8. Tools for inspecting a runtime image

The commands below apply to **JDK 17+** when the corresponding tool is installed with the JDK. They are CLI tool examples and do not modify the existing runtime.

### 8.1. List available modules

~~~bash
java --list-modules
~~~

The output may include:

~~~text
java.base@17...
java.logging@17...
java.sql@17...
~~~

The `...` is **ellipsis notation omitting the version details and additional lines in the example**, not a fixed part of the output. The actual list depends on the JDK/runtime image. `--list-modules` answers "which modules does the current runtime have?", but does not tell you which classes have been loaded into the JVM.

### 8.2. Inspect module details

~~~bash
java --describe-module java.base
~~~

This command shows `java.base` metadata: exported packages, module requirements, and other module information in the Java launcher's format. This is **module system** information, not the full bytecode contents of each `.class`.

### 8.3. Inspect a standard ClassFile with javap

~~~bash
javap -c java.lang.String
~~~

`javap` disassembles the class definition/bytecode to display its methods. If you want constant pool/attribute details, use `javap -v java.lang.String` (the output is very long). There is no need to hunt for `rt.jar` and manually extract `String.class`.

### 8.4. Inspect the runtime container with jimage

~~~text
jimage list <path-to-JDK>/lib/modules
~~~

Replace `<path-to-JDK>` with the actual JDK installation path. `jimage` is a JDK tool that supports the implementation container format provided by the JDK; the example path may vary by runtime. This is an option for **inspection tools**, not an interface applications should rely on to locate classes.

### 8.5. Create a minimal image with jlink

Example on a JDK that includes `jlink` and the default input modules:

~~~bash
jlink --add-modules java.base --output minimal-runtime
~~~

Then, on Linux/macOS:

~~~bash
./minimal-runtime/bin/java --list-modules
~~~

Or on Windows PowerShell:

~~~powershell
.\minimal-runtime\bin\java.exe --list-modules
~~~

The new image contains only `java.base` and its required dependencies (if any), so many other modules from the full JDK are absent. `jlink` **creates a new output directory**; if that directory name already exists, choose another output name. This example only illustrates trimming a runtime; it is not a complete packaging guide for a complex application. Real applications must include all required modules and dependencies, including dynamically loaded services where appropriate.

## 9. Migrating legacy code that depended on `rt.jar`

A Java 8 pattern might look like this:

~~~java
// Anti-pattern example: legacy code manually looking up rt.jar from the Java installation directory.
String path = System.getProperty("java.home") + "/lib/rt.jar";
~~~

This is a **fragment illustrating a design flaw**, not a standalone program and not a universal rule for every JDK 8 layout. If that path is later opened with `new JarFile(path)`, it will fail on JDK 9+ because `rt.jar` does not exist.

Choose a solution based on your actual goal:

| Need | Appropriate approach on modern JDKs |
| --- | --- |
| **Load or use a standard class** | Use normal Java APIs or `Class.forName(...)` as appropriate; the JVM and loaders determine the class source. |
| **Find a resource for a class** | `SomeClass.class.getResource(...)` or `getResourceAsStream(...)`. |
| **Find a resource via the system class loader** | `ClassLoader.getSystemResource(...)`, while handling `null` results and `jrt:` URLs. |
| **Browse module classes/resources in the runtime image** | JRT FileSystem Provider (`FileSystems.newFileSystem(URI.create("jrt:/"), ...)`) or the `jimage` tool. |
| **Find which module contains/defines a class** | `SomeClass.class.getModule()`, `ModuleLayer`, or modular tools where appropriate. |
| **Build a runtime distributed with an application** | `jlink`, after analyzing module dependencies and required service providers. |
| **Analyze bytecode** | `javap` for basic needs; an appropriate ClassFile reading library for specialized tooling. |

Do not blindly replace every `rt.jar` reference with a hard-coded `$JAVA_HOME/lib/modules` path. The goal is to **eliminate reliance on internal container paths and formats**. Also do not treat `jrt:/` as a classpath entry to be added manually: runtime classes are already managed by the module system and built-in loaders.

### Safely reading a resource with InputStream

If you only need to read the bytes of a resource, the API on the class itself is usually easier to use than manipulating paths:

~~~java
try (var stream = Object.class.getResourceAsStream("Object.class")) {
    if (stream == null) {
        throw new IllegalStateException("Cannot locate Object.class");
    }
    byte[] bytes = stream.readAllBytes();
    System.out.println(bytes.length > 4);
}
~~~

This is a **fragment** meant to be placed in a method that throws or handles `IOException`. On a standard JDK, it prints `true`; using `getResourceAsStream` avoids assuming the URL must have a `file:` or `jar:` scheme. Reading an entire ClassFile is only appropriate when you genuinely need the raw bytes; using a class's API does not require reading `.class` files yourself.

## 10. Limitations and common pitfalls

### 10.1. The default `FileSystems` does not understand `jrt:` automatically

`Path.of("jrt:/java.base/java/lang/Object.class")` creates a path on the **default filesystem** (which may become an ordinary file name string), not a JRT resource. You must obtain a `Path` from the JRT provider as shown in Section 5.

### 10.2. Do not cast the system/platform loader to URLClassLoader

On Java 9+, the built-in application and platform loaders have different internal implementations from JDK 8; code like:

~~~java
// Wrong assumption on modern JDKs:
java.net.URLClassLoader loader =
        (java.net.URLClassLoader) ClassLoader.getSystemClassLoader();
~~~

can throw `ClassCastException`. This is an illustrative anti-pattern that **can compile**, but should not be executed to manage the classpath. Use standard `ClassLoader`/module APIs or a clearly designed custom loader instead of casting.

### 10.3. Resource paths may change or be inaccessible

Not every resource is open for lookup from every module or loader. Module encapsulation can affect `getResource` or `getResourceAsStream` in cases outside public API classes/packages. Custom runtime images may also omit the module you are looking for. Always check for `null`, access permissions, and module availability rather than assuming every JDK has every module.

### 10.4. `jrt:` does not prove a module or class is initialized

Having a path `jrt:/java.base/...class` only confirms the corresponding resource or definition can be provided; it does not mean the class is initialized, has instantiated objects, or has been JIT-compiled. **Resource resolution**, **class loading**, **class linking**, and **class initialization** are distinct activities.

### 10.5. Do not "patch" `lib/modules` by manually editing bytes

The runtime image container is an implementation detail, not a compatible JAR for users to swap entries in directly. Manual edits can corrupt the runtime or break JVM/tool assumptions. When you need to add libraries, use the classpath/module path and your build process; when you need a new image, use `jlink` with the appropriate set of modules.

### 10.6. Do not confuse JMOD, JAR, and runtime image

- **Modular JAR**: contains `module-info.class` and can be placed on the module path.
- **JMOD**: typically used to supply contents for linking and JDK tools; not used as a dependency JAR on the runtime module path.
- **Runtime image**: an assembled execution environment with a module list and layout matching the implementation.

## 11. Self-check

**Q1.** Does Java 17 need `rt.jar` to use `java.lang.String`?

**Answer:** No. Platform classes reside in modules of the runtime image, and the JVM together with built-in loaders provide class definition through the modern mechanism.

**Q2.** Is the URL `jrt:/java.base/java/lang/Object.class` a physical path to a JAR file?

**Answer:** No. It is a logical URL with the `jrt:` scheme, pointing to a resource in the `java.base` module inside the runtime image. The API/provider hides the underlying container layout.

**Q3.** Why do we use `/modules/java.base/java/lang/Object.class` when using the JRT FileSystem?

**Answer:** The JRT NIO FileSystem exposes a virtual tree under `/modules/...`. This `Path` convention differs from the `jrt:/java.base/...` resource URL syntax.

**Q4.** Can you add `$JAVA_HOME/lib/modules` to the classpath to replace `rt.jar`?

**Answer:** You should not, and it does not make sense: `lib/modules` is a runtime image file/container, not a JAR dependency on the classpath. The JVM's loaders already manage system modules.

**Q5.** What does `jlink` create, and what should applications watch out for?

**Answer:** It creates a custom runtime image containing the selected root modules and their resolved dependencies. Applications must accurately identify all modules needed at runtime, including providers that only appear via dynamic loading.

**Q6.** Does `Object.class.getClassLoader() == null` on a common JDK mean there is no class loading?

**Answer:** No. `null` is how the API represents the bootstrap loader; the class is still loaded and defined by the JVM through the appropriate mechanism.

## 12. Key takeaways and official references

**Three key points to remember:**

1. Starting with Java 9, **`rt.jar` was removed** and standard classes belong to modules in a **modular runtime image**; this is a change in JDK distribution structure, not the removal of application library JARs.
2. **`jrt:`** is a logical access scheme for runtime image resources. To browse it as a file system, use the **JRT NIO provider** and `/modules/<module>/...`; do not depend on the container's physical path.
3. **Built-in class loaders still define classes**; the module graph, loaders, and class initialization are distinct concepts. To update legacy code, replace direct operations on `rt.jar` with **appropriate resource/module APIs**, `javap`, `jimage`, or `jlink` depending on your goal.

**Official references:**

- OpenJDK, **JEP 220: Modular Run-Time Images** — https://openjdk.org/jeps/220
- Oracle, **Migrating From JDK 8 to Later JDK Releases**, section *Removed rt.jar and tools.jar* — https://docs.oracle.com/en/java/javase/17/migrate/migrating-jdk-8-later-jdk-releases.html
- Oracle Java SE 17 API, **module `java.base`**, JRT file system provider section — https://docs.oracle.com/en/java/javase/17/docs/api/java.base/module-summary.html
- Oracle Java SE 17, **jlink** — https://docs.oracle.com/en/java/javase/17/docs/specs/man/jlink.html
