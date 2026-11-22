# Classpath and Traditional Class Lookup

In traditional Java, the **classpath** is the set of directories and archive files that the compiler or runtime uses to locate application classes and resources. Before the Java Platform Module System (JPMS), most Java applications only needed to organize **.class** and **.jar** files on the classpath and then run a class containing a **main** method. Even from Java 9 onward, running with the classpath remains supported and is especially common in projects that use non-modularized libraries.

This lesson explains what the classpath actually is, how package names are mapped to bytecode paths, how class loaders locate and define classes, why the compile-time classpath can differ from the runtime classpath, and how to handle errors when library versions are missing or duplicated.

## 1. What Does the Classpath Contain?

A classpath entry can be the root directory of a package tree or a JAR containing bytecode and resources:

~~~text
demo/
  out/
    com/example/app/Main.class
    com/example/util/Printer.class
  lib/
    json.jar
    logging.jar
~~~

If the classpath contains the **out** directory, the runtime can locate the **com.example.app.Main** class from the file:

~~~text
out/com/example/app/Main.class
~~~

For the class name **com.example.util.Printer**, the corresponding path is:

~~~text
out/com/example/util/Printer.class
~~~

Classpath entries are not module descriptors. They do not state which library depends on which library and do not restrict public packages according to the JPMS **exports** directive. Therefore, the classpath is easy to use, but expresses very little dependency structure at the architectural level.

Common entry forms:

| Classpath entry | Usage |
|---|---|
| **out** | Root directory containing compiled classes. |
| **lib/util.jar** | JAR containing a library's classes and resources. |
| **lib/*** | Wildcard supported by the Java launcher to include JARs directly inside the lib directory on the classpath. |
| **.** | Current working directory. |
| **config** | Directory that can contain resources and class files if organized with the proper paths. |

## 2. Class Names and Bytecode Paths

Consider the source:

~~~java
package com.example.util;

public final class Printer {
    private Printer() {
    }

    public static void print(String text) {
        System.out.println(text);
    }
}
~~~

The fully qualified name of the class is **com.example.util.Printer**. That is the **binary name** used by class-loading APIs. In a standard package layout, the class loader searches for a resource named:

~~~text
com/example/util/Printer.class
~~~

This is the path relative to the classpath root. Therefore, if the class file resides under the **out** directory, the classpath entry must be **out**, not **out/com/example/util**.

Distinguish four concepts:

- **Package:** com.example.util.
- **Simple name:** Printer.
- **Binary name:** com.example.util.Printer.
- **Relative .class path:** com/example/util/Printer.class.

Confusing the classpath root with the package directory is a common cause of the **Could not find or load main class** error.

## 3. Example of Compiling and Running a Program

Create two files:

~~~text
src/
  com/example/util/Printer.java
  com/example/app/Main.java
~~~

File **Main.java**:

~~~java
package com.example.app;

import com.example.util.Printer;

public final class Main {
    public static void main(String[] args) {
        Printer.print("Hello classpath");
    }
}
~~~

The **Printer.java** file is the class from the previous example. Compile both:

~~~bash
javac -d out \
      src/com/example/util/Printer.java \
      src/com/example/app/Main.java
~~~

Run:

~~~bash
java -cp out com.example.app.Main
~~~

Expected output:

~~~text
Hello classpath
~~~

Here:

1. **javac** compiles the source into bytecode and places the output in a directory tree matching the packages.
2. **-cp out** instructs the runtime to use **out** as a class search source.
3. **com.example.app.Main** is the binary name of the main class.
4. The JVM loads the required classes and invokes the main method.
5. When Main uses Printer, the runtime must be able to locate Printer within the class loader's scope.

It is not necessary to compile all classes into the same directory, but the required directories and JARs must be included on the effective classpath at runtime.

## 4. Compile-Time Classpath vs. Runtime Classpath

Both **javac** and **java** have the **-cp** or **-classpath** option, but each tool uses this list for a different purpose:

| Tool | Role |
|---|---|
| **javac** | Locates classes and libraries to perform type analysis, check references, and compile source code. |
| **java** | Locates bytecode and resources when the program is executed. |

Suppose **Printer** has been packaged in **lib/util.jar**. When compiling Main:

~~~bash
javac -cp lib/util.jar \
      -d app-out \
      src/com/example/app/Main.java
~~~

At runtime, both the app output and the library are needed:

~~~bash
java -cp "app-out:lib/util.jar" com.example.app.Main
~~~

If the runtime only receives:

~~~bash
java -cp app-out com.example.app.Main
~~~

then Main can be found, but the JVM still cannot find Printer when needed. This situation can lead to **NoClassDefFoundError**.

**A successful compilation does not mean the runtime classpath is complete.** Nor do build tools automatically guarantee that every JAR present at compile time is included in the actual Java process.

## 5. Path Separators on Windows and Unix

Classpath entries are separated by an operating-system-dependent character.

Linux or macOS:

~~~bash
java -cp "out:lib/a.jar:lib/b.jar" com.example.app.Main
~~~

Windows PowerShell:

~~~powershell
java -cp "out;lib/a.jar;lib/b.jar" com.example.app.Main
~~~

| Operating System | Separator between entries |
|---|---|
| Linux | Colon |
| macOS | Colon |
| Windows | Semicolon |

Paths in a classpath string can be relative or absolute. For relative paths, pay attention to the **working directory** of the running Java process.

Double quotes help the shell pass the entire classpath string as a single argument. This is especially useful when paths contain spaces or special characters.

Do not confuse the dots in a Java package name with the separator character between classpath entries.

## 6. Default Classpath and the CLASSPATH Environment Variable

When running in classpath mode without specifying **-cp**, the Java launcher may use the **CLASSPATH** environment variable if it is set. If no explicit classpath configuration or effective environment variable is present, the usual default is the current working directory (**.**).

For example:

~~~bash
java com.example.app.Main
~~~

The command above only succeeds if the effective classpath contains the exact class file of **com.example.app.Main**.

To avoid depending on the machine running the command, write it explicitly:

~~~bash
java -cp out com.example.app.Main
~~~

If the current directory also needs to be included, add it to the list explicitly:

~~~bash
java -cp ".:lib/util.jar" com.example.app.Main
~~~

Windows:

~~~powershell
java -cp ".;lib/util.jar" com.example.app.Main
~~~

When passing **-cp**, do not assume the **CLASSPATH** variable or the dot is automatically appended. In CI, IDEs, and deployment environments, explicit configuration makes execution commands much more reproducible.

## 7. Wildcards and Directories Containing JARs

The Java launcher supports classpath wildcards:

~~~bash
java -cp "out:lib/*" com.example.app.Main
~~~

Windows:

~~~powershell
java -cp "out;lib/*" com.example.app.Main
~~~

The wildcard adds supported JARs located **directly** inside the **lib** directory to the classpath list.

Things to remember:

- **-cp lib** only adds the `lib` directory to the classpath; it does not mean scanning all JARs inside it.
- **-cp lib/*** is the wildcard syntax for JARs directly inside `lib`.
- The wildcard does not recursively search subdirectories.
- The expansion order of JARs via a wildcard should not be treated as a stable contract for deciding library version selection.

If two JARs contain the same class, relying on wildcard order to pick which JAR wins makes the application hard to reproduce and hard to control.

## 8. How Do JARs Store Classes?

A JAR is an archive containing entries organized by path. After compiling **Printer.class** into **out**, package it:

~~~bash
jar --create \
    --file lib/util.jar \
    -C out com/example/util
~~~

Inside the archive, contents may include:

~~~text
META-INF/
META-INF/MANIFEST.MF
com/example/util/Printer.class
~~~

Java does not need to extract the JAR before searching for classes: an appropriate class loader can read classes and resources directly from the archive.

Inspect JAR contents:

~~~bash
jar --list --file lib/util.jar
~~~

If the file was packaged incorrectly as:

~~~text
out/com/example/util/Printer.class
~~~

while the runtime expects:

~~~text
com/example/util/Printer.class
~~~

then a normal class loader may not find Printer, even though the JAR can still be opened.

When encountering a missing class error, always check the **class name**, **classpath root location**, and **entry paths inside the JAR**.

## 9. java -cp vs. java -jar

There are two common ways to launch an application.

Specifying the classpath and main class:

~~~bash
java -cp "app.jar:lib/*" com.example.app.Main
~~~

Or using an executable JAR with a manifest:

~~~bash
java -jar app.jar
~~~

In the second approach, the manifest usually contains the line:

~~~text
Main-Class: com.example.app.Main
~~~

With **java -jar**, the launcher uses the JAR as the application source and does not process **-cp** or **CLASSPATH** as the supplementary classpath mechanism normally used when running by main class name.

If dependencies outside the executable JAR are needed, the manifest can declare **Class-Path**:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.app.Main
Class-Path: lib/util.jar lib/logging.jar
~~~

Manifest Class-Path entries follow manifest URL rules, typically resolved relative to the JAR containing the manifest. They do not use the same entry-splitting conventions as the string passed to **-cp**.

When investigating errors that only appear with **java -jar**, check the manifest and how dependencies are packaged, rather than just adding **-cp** and assuming the launcher will use it.

## 10. The Class Loader Actually Locates Bytecode

The classpath describes the **search sources**; the **class loader** performs the lookup and loading of classes from the sources it manages.

Some typical loaders in modern Java:

| Loader | Primary role |
|---|---|
| Bootstrap loader | Loads the core foundational classes of the Java runtime. |
| Platform loader | Serves parts of the Java platform according to the runtime design. |
| Application/system loader | Typically responsible for loading application classes from the application classpath. |
| Custom loader | Implemented by frameworks or applications to load plugins, dynamic bytecode, or custom sources. |

Example to inspect loaders:

~~~java
public final class LoaderInfo {
    public static void main(String[] args) {
        System.out.println(LoaderInfo.class.getClassLoader());
        System.out.println(ClassLoader.getSystemClassLoader());
        System.out.println(ClassLoader.getPlatformClassLoader());
        System.out.println(String.class.getClassLoader());
    }
}
~~~

For classes loaded by the bootstrap loader, **getClassLoader()** may return **null**. This is an API representation, not proof that the JVM lacks a bootstrap loader.

From Java 9 onward, the runtime structure and loader implementations are not identical to Java 8. Do not assume the app class loader is always a **URLClassLoader** or that all JDK classes come from an **rt.jar** file.

## 11. Parent Delegation: The Traditional Delegation Mechanism

Many class loaders use the **parent-first** model via **ClassLoader.loadClass(...)**. The default process can be summarized simply:

1. Check whether the class has already been loaded by the current loader.
2. If not, try delegating to the parent loader.
3. If the parent cannot find it, the loader searches its own sources, usually via **findClass(...)**.
4. If suitable bytecode is found, the loader defines the class.
5. If not found, the process may end with a **ClassNotFoundException**.

Diagram:

~~~text
loadClass("com.example.util.Printer")
                 |
                 v
           Already loaded?
            /          \
          Yes           No
          |             |
       Return      Ask parent loader
                        |
                 Parent did not find it
                        |
                   findClass(...)
                     /     \
                 Success   Not found
                    |         |
                 Class<?>   ClassNotFoundException
~~~

Parent delegation supports reusing Java platform classes and prevents classes on the application classpath from accidentally replacing core classes.

However, custom class loaders are not required to always follow strict parent-first ordering. Plugin frameworks, application servers, or containers may use their own strategies. When duplicate classes occur, identify the specific loader performing the class lookup.

## 12. loadClass, Class.forName, and defineClass

These three APIs/mechanisms are related but serve different purposes.

**ClassLoader.loadClass(String)**:

~~~java
ClassLoader loader = ClassLoader.getSystemClassLoader();

Class<?> type = loader.loadClass("com.example.util.Printer");
System.out.println(type.getName());
~~~

It asks the loader to return or load a class by binary name; this operation normally does not initialize the class solely by being called.

**Class.forName(String)**:

~~~java
Class<?> type = Class.forName("com.example.util.Printer");
~~~

The single-parameter overload searches for the class and typically triggers class initialization according to the API rules.

If you want to defer initialization:

~~~java
Class<?> type = Class.forName(
    "com.example.util.Printer",
    false,
    ClassLoader.getSystemClassLoader()
);
~~~

**defineClass(...)** is the appropriate internal class loader operation to turn bytecode into a class definition managed by the JVM. Ordinary application code does not need to call it directly.

Finding a class, defining it, **linking** it, and **initializing** it are stages that can occur at different times. A class is not necessarily initialized immediately when the class loader returns the **Class<?>** object.

## 13. Class Loading Usually Happens On Demand

The JVM does not necessarily load every class from all JARs on the classpath at startup.

For example:

~~~java
public final class Main {
    public static void main(String[] args) {
        System.out.println("Start");

        if (args.length > 0) {
            OptionalFeature.execute();
        }
    }
}
~~~

If the branch using OptionalFeature is not executed, the runtime may not yet need to load or resolve all classes and dependencies of that feature.

Therefore, an application can start and reach `main` successfully even if a library used only in a rarely invoked feature is missing from the runtime classpath. Only when that feature is called does the application fail.

To thoroughly verify dependencies, do not just launch `main`: exercise the business paths that use important libraries.

## 14. Duplicate Classes and Lookup Order

Suppose:

~~~text
lib/
  old-client.jar
  new-client.jar
~~~

Both contain:

~~~text
com/example/client/Client.class
~~~

In a class loader that searches an ordered classpath list, a source searched earlier can **shadow** a class with the same name in a source searched later.

For example:

~~~bash
java -cp "lib/old-client.jar:lib/new-client.jar:app.jar" \
     com.example.app.Main
~~~

When changing the order, the class may be loaded from a different version within that loader model. When wildcards, manifest dependencies, or custom loaders are involved, do not infer a single rule that applies to every environment.

Consequences can include:

- **NoSuchMethodError** because code was compiled against a new API, but runtime picks up an old class.
- **NoSuchFieldError** because an expected field no longer exists in the runtime binary.
- **AbstractMethodError** due to an incompatible class/interface.
- Behavior changing unintentionally depending on which JAR gets selected.

Reordering JARs should not be treated as a long-term fix. Identify duplicate dependencies and eliminate conflicts in the build or distribution configuration.

## 15. Class Identity Also Depends on the Class Loader

In the JVM, the same binary class name can still represent two different types if they are **defined by two different class loaders**.

For example, both the host and a plugin contain the file:

~~~text
com/acme/plugin/Widget.class
~~~

If two independent loaders each define this class separately, the **Class<?>** objects are not the same runtime type, even though **getName()** returns the same string.

This phenomenon can lead to confusing cast or linkage errors. To observe it:

~~~java
System.out.println(obj.getClass().getName());
System.out.println(obj.getClass().getClassLoader());
System.out.println(ExpectedType.class.getClassLoader());
~~~

When designing plugins, place shared interfaces in a loader shared by both host and plugin, rather than packaging a separate copy of the API in each plugin loader.

## 16. Resources Are Also Searched on the Classpath

The classpath is not only for bytecode. It can hold configuration files, templates, and data read by the application as resources.

For example:

~~~text
out/
  com/example/app/Main.class
  config/default.properties
~~~

Reading a resource:

~~~java
import java.io.InputStream;
import java.util.Properties;

public final class ConfigReader {
    public static Properties load() throws Exception {
        ClassLoader loader = ConfigReader.class.getClassLoader();

        try (InputStream input =
                 loader.getResourceAsStream("config/default.properties")) {
            if (input == null) {
                throw new IllegalStateException("Missing default.properties");
            }

            Properties result = new Properties();
            result.load(input);
            return result;
        }
    }
}
~~~

**getResourceAsStream(...)** searches for resources according to the loader's rules, not arbitrarily across the entire disk.

Distinguish between the **ClassLoader.getResourceAsStream(...)** and **Class.getResourceAsStream(...)** APIs: how relative paths and paths starting with a leading slash are interpreted can differ.

When building a JAR, confirm that resources are actually copied into the output; having the file in the source tree is not enough for the runtime to find it.

## 17. ServiceLoader in the Classpath World

The classpath also supports metadata discovery conventions. One example is **ServiceLoader**.

If the service interface is:

~~~text
com.example.spi.Plugin
~~~

A provider JAR on the classpath can contain:

~~~text
META-INF/services/com.example.spi.Plugin
~~~

with the content:

~~~text
com.example.impl.DefaultPlugin
~~~

When code calls:

~~~java
ServiceLoader<Plugin> loader = ServiceLoader.load(Plugin.class);

for (Plugin plugin : loader) {
    plugin.execute();
}
~~~

ServiceLoader can read matching service configurations from the class loader's search scope to discover providers.

In applications with custom loaders, a provider JAR outside the classpath of the active loader may not be found, even if the JAR file exists on disk. This is an issue of **the loader's search sources**, not the service interface name.

JPMS adds the **uses** and **provides ... with ...** declarations in module descriptors, enabling service management at the named module level.

## 18. Diagnosing ClassNotFoundException and NoClassDefFoundError

The two most common errors when the classpath is incomplete or differs from expectations are:

**ClassNotFoundException:** An API loading a class by name, such as **Class.forName(...)**, cannot find a matching class definition.

~~~java
Class.forName("com.example.driver.MissingDriver");
~~~

**NoClassDefFoundError:** The JVM needs a class at runtime but cannot obtain the required class definition, or the class previously encountered a problem during initialization; the error can appear when linking an already-compiled class.

For example, Main code was compiled with:

~~~java
Printer.print("Test");
~~~

but the runtime classpath lacks Printer.

| Error | Things to check |
|---|---|
| **ClassNotFoundException** | Is the binary name correct? Which loader is searching? Is the JAR within the sources managed by that loader? |
| **NoClassDefFoundError** | Is a runtime dependency missing? Is there a cause related to initialization? |
| **UnsupportedClassVersionError** | Was the class compiled for a newer Java version than the runtime? |
| **NoSuchMethodError** | Is the runtime using a different version of the class than compile time? |
| **Weird ClassCastException** | Do two classes with the same name share the same defining loader? |
| **Could not find or load main class** | Are the classpath root, package, main class, and output directory accurate? |

Read the full stack trace and the **Caused by** sections to avoid misdiagnosis.

## 19. Tools for Inspecting the Classpath

**Check whether a JAR contains a class:**

~~~bash
jar --list --file lib/util.jar
~~~

Look for the class file at the proper path:

~~~text
com/example/util/Printer.class
~~~

**Use javap to inspect a compiled class:**

~~~bash
javap -classpath out com.example.app.Main
~~~

**Enable class loading logs on a modern JDK:**

~~~bash
java -Xlog:class+load=info \
     -cp "out:lib/*" \
     com.example.app.Main
~~~

The **-verbose:class** option can also help observe class loading activity on supported Java versions.

**Print the loader and code source once a class is available:**

~~~java
Class<?> type = Class.forName("com.example.util.Printer");

System.out.println(type.getClassLoader());

var domain = type.getProtectionDomain();
if (domain != null) {
    System.out.println(domain.getCodeSource());
}
~~~

**CodeSource** information can help locate where a class came from if the loader provides the corresponding metadata; this value is not always present.

**Cross-check build configuration:** Inspect the runtime dependency graph of Maven/Gradle and the actual JVM command executed by the IDE, script, or container.

## 20. How Does Classpath Differ from Module Path?

Java 9 introduced **JPMS** to the platform and added the **module path**. The classpath still exists, but the two mechanisms have different goals.

| Aspect | Traditional Classpath | Module Path / JPMS |
|---|---|---|
| Primary unit | Classes and resources located via class loaders. | Named modules with descriptors and a module graph. |
| Dependencies | Determined by build tools and the actual classpath. | **requires**, **requires transitive**, **requires static**. |
| Package exposure | No dedicated module directive to restrict public packages between JARs on the classpath. | **exports** exposes API packages to other modules. |
| Deep reflection | Subject to Java access rules and runtime restrictions. | **opens** controls deep reflection between named modules. |
| Traditional JARs | Belong to the unnamed module when run on the classpath in a JPMS environment. | Can be treated as an automatic module on the module path if lacking module-info.class. |
| Resolution | Primarily based on the loader's class search sources. | Resolves the module graph before the program runs. |

Running via classpath:

~~~bash
java -cp "out:lib/*" com.example.app.Main
~~~

Running as a named module:

~~~bash
java --module-path mods \
     --module com.example.app/com.example.app.Main
~~~

Switching **-cp** to **--module-path** should not be viewed as a mere syntax change. Named modules have resolution mechanisms and module-level exports/opens controls that JARs on the traditional classpath do not have.

## 21. Common Misconceptions

**"The classpath must point directly to the directory containing Main.class."** Incorrect if Main has a package: it must point to the root of the package tree so the binary name maps properly.

**"Putting lib on the classpath will automatically pick up all JARs under lib."** Incorrect; you must list the JARs or use the wildcard supported by the launcher.

**"If a class is present in a JAR, every class loader can find it."** Incorrect; the JAR must be within the search scope of the appropriate loader.

**"If javac succeeds, the runtime has all dependencies."** Incorrect; the classpaths for the two phases can differ.

**"The JVM loads every class from all JARs at startup."** Incorrect; many classes are only loaded when needed.

**"Two classes with the same binary name are always equivalent."** Incorrect if their defining class loaders are different.

**"java -jar always uses -cp to add external libraries."** Incorrect; you need to understand JAR manifest rules or how packaging works.

**"Classpath and module path are the same."** Incorrect; the module path is a source participating in JPMS resolution, whereas the traditional classpath does not automatically create a separate named module for each JAR.

## 22. Practical Checklist

- Identify the correct binary name and package of the main class.
- Point the classpath at the root directory tree containing the class packages.
- Check both the compile classpath and the runtime classpath.
- Use the correct classpath separator for the operating system.
- Distinguish the **lib** directory from the wildcard for the JARs inside it.
- Package JARs so class entries have the exact paths corresponding to their binary names.
- Distinguish running via **java -cp ... Main** from **java -jar app.jar**.
- Do not rely on JAR ordering to resolve conflicting dependencies.
- Inspect the class loader when duplicate classes or unusual cast errors occur.
- Read the stack trace to distinguish class-not-found errors from linkage errors.
- Check the actual JVM classpath launched by the IDE or build tool.
- When migrating to JPMS, learn more about module resolution, **module-info.java**, and API boundaries.

**Classpath** solves bytecode and resource lookup in the traditional Java model. From a class binary name, a class loader searches for data in the sources it manages, typically following parent delegation, and then defines the class for the JVM to link and use. Mastering the classpath root, **javac/java** commands, JAR packaging, and class loaders helps diagnose dependency errors more accurately, while building a solid foundation for understanding the differences when using JPMS's **module path**.