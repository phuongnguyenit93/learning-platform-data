# Module Version and Main Class Metadata

> Scope: modular JARs in the Java Platform Module System (JPMS). When packaging a modular JAR, the **jar** tool can record a module version and main class into the module descriptor inside the JAR. This is module metadata, distinct from implementation attributes in the manifest and distinct from metadata of a JAR run via the class path mechanism.

## Objectives

After this lesson, you can:

- Record a module version using the **--module-version** option.
- Record a modular JAR's main class using **--main-class**.
- Distinguish metadata in the module descriptor from metadata in **META-INF/MANIFEST.MF**.
- Inspect the module version and main class with **jar --describe-module**.
- Read metadata at runtime using **ModuleDescriptor**.
- Run a module without specifying the main class in the command.
- Understand the limitations of module versions in module resolution.

## 1. What Are Module Version and Main Class Metadata?

A modular JAR has a **module-info.class** file at its root directory. This file contains the module descriptor: the module name, directives such as **requires**, **exports**, **opens**, **uses**, **provides**, along with certain other metadata.

Two commonly used metadata items when releasing a modular JAR are:

- **Module version**: the version attached to the module descriptor.
- **Main class**: the default launch class of the module.

When creating a JAR with the **jar** tool, you can set these two values using:

- **--module-version**: records the module version.
- **--main-class**: records the main class for the module.

For example, a modular JAR has module name **com.acme.app**, version **2.4.1**, and main class **com.acme.app.Main**. This metadata lets inspection tools and the launcher know the version information and default entry-point class.

Note: a JAR file name like **acme-app-2.4.1.jar** does not automatically give the module version 2.4.1. Module version is separate metadata recorded inside the module descriptor.

## 2. Creating a Modular JAR with Module Version and Main Class

Suppose the sources have been compiled into an exploded module:

~~~text
project/
├── src/
│   └── com.acme.app/
│       ├── module-info.java
│       └── com/acme/app/Main.java
└── mods/
    └── com.acme.app/
        ├── module-info.class
        └── com/acme/app/Main.class
~~~

Module descriptor:

~~~java
module com.acme.app {
    exports com.acme.app;
}
~~~

Main class:

~~~java
package com.acme.app;

public final class Main {
    public static void main(String[] args) {
        System.out.println("Acme application");
    }
}
~~~

Create the modular JAR:

~~~bash
jar --create \
    --file mlib/com.acme.app.jar \
    --module-version 2.4.1 \
    --main-class com.acme.app.Main \
    -C mods/com.acme.app .
~~~

Meaning:

- **--create** creates a new JAR.
- **--file** specifies the output JAR file.
- **--module-version 2.4.1** records the version into the module descriptor.
- **--main-class com.acme.app.Main** records the module's default main class.
- **-C mods/com.acme.app .** switches into the compiled module directory and includes its contents in the JAR.

The result is **mlib/com.acme.app.jar** with a module descriptor containing the module name, version, and main class. These two options do not replace the module descriptor; the JAR must still be a valid modular JAR.

You can use version strings following project conventions, such as **1.0**, **2.4.1**, or **3.0.0-RC1**, as long as the value is accepted by the tool as a valid module version. Keep the versioning convention consistent across the build and release process.

## 3. Where Is the Module Version Stored?

The module version is stored in the module descriptor metadata inside **module-info.class**, rather than merely relying on the JAR file name.

You can inspect it with:

~~~bash
jar --describe-module --file mlib/com.acme.app.jar
~~~

Illustrative output:

~~~text
com.acme.app@2.4.1 jar:file:///.../com.acme.app.jar!/module-info.class
exports com.acme.app
requires java.base mandated
main-class com.acme.app.Main
~~~

The first line shows the module name and version. The **main-class** line shows the default launch class recorded in the descriptor.

The file name could be **com.acme.app.jar**, **acme-app-2.4.1.jar**, or something else; the module name and module version come from the descriptor. Do not infer the module version solely from the filename.

If a JAR lacks an explicit module descriptor and is used as an automatic module, it does not have the same module version/main class metadata recorded via these options. **Automatic-Module-Name** in the manifest only supplies an automatic module name; it does not turn the JAR into an explicit modular JAR.

## 4. Main Class Metadata and ModuleMainClass

For a modular JAR, the `jar` tool's **--main-class** writes the main class into the **ModuleMainClass** attribute in the module descriptor.

For example:

~~~bash
jar --create \
    --file mlib/com.acme.app.jar \
    --module-version 2.4.1 \
    --main-class com.acme.app.Main \
    -C mods/com.acme.app .
~~~

When the module descriptor has a main class, you can run the module without specifying the class name:

~~~bash
java --module-path mlib --module com.acme.app
~~~

The launcher looks up the main class recorded in the module descriptor and invokes **public static void main(String[] args)**.

You can also specify the main class explicitly in the command:

~~~bash
java --module-path mlib \
     --module com.acme.app/com.acme.app.Main
~~~

The **-m module/main-class** syntax explicitly specifies which class to run. This is useful when a module has multiple entry points or when you want to select a class other than the default main class recorded in the descriptor.

If you omit the **/main-class** part when the descriptor has no main class, the launcher does not know which class to run and reports an error. Therefore, if you want to use **java -m com.acme.app**, make sure the modular JAR was packaged with **--main-class**.

## 5. Distinguishing ModuleMainClass from Main-Class in the Manifest

Do not confuse these two pieces of metadata:

| Metadata | Where Stored | Purpose |
|---|---|---|
| **ModuleMainClass** | Module descriptor in **module-info.class** | Default main class when launching a named module via **java -m module** |
| **Main-Class** | Main section of **META-INF/MANIFEST.MF** | Main class of an executable JAR launched via **java -jar** |

For a modular JAR, use **--main-class** when creating the JAR to record the main class in the module descriptor. When running as a named module, use **--module-path** and **--module**.

For a traditional executable JAR without a module descriptor, the manifest typically contains:

~~~text
Manifest-Version: 1.0
Main-Class: com.acme.app.Main
~~~

and is launched with:

~~~bash
java -jar app.jar
~~~

**java -jar** and **java --module-path ... --module ...** are two different launch mechanisms. If the goal is to launch the application as a named module, use the module path and module name.

## 6. Manifest Implementation Metadata Differs from Module Version

The manifest can still contain metadata describing the artifact or package, for example:

~~~text
Manifest-Version: 1.0
Implementation-Title: Acme Application
Implementation-Version: 2.4.1
Implementation-Vendor: Acme Corporation
Specification-Title: Acme Application API
Specification-Version: 2.0
Specification-Vendor: Acme Corporation
~~~

These attributes describe the implementation or specification of the JAR/package. They do not automatically become the module version in the module descriptor.

You can add a custom manifest when creating a modular JAR:

~~~bash
jar --create \
    --file mlib/com.acme.app.jar \
    --manifest manifest.mf \
    --module-version 2.4.1 \
    --main-class com.acme.app.Main \
    -C mods/com.acme.app .
~~~

Here:

- **--module-version** writes the version into the module descriptor.
- **--main-class** writes the main class into the module descriptor.
- **--manifest** includes the main attributes from the manifest file into the JAR.

Do not simply put **Implementation-Version** in the manifest and expect **jar --describe-module** to display it as the module version. If you need a module version, use **--module-version**.

For packages loaded from a JAR, the **Package** API can provide implementation/specification metadata through methods such as **getImplementationVersion()** and **getSpecificationVersion()**, if the manifest provides the corresponding attributes. That is package metadata and does not replace **ModuleDescriptor.version()**.

## 7. Reading Module Version and Main Class at Runtime

From a class inside a named module, you can obtain the current module:

~~~java
Module module = Main.class.getModule();
ModuleDescriptor descriptor = module.getDescriptor();
~~~

Read the module name:

~~~java
String moduleName = descriptor.name();
System.out.println("Module: " + moduleName);
~~~

Read the version:

~~~java
descriptor.version().ifPresent(version ->
        System.out.println("Version: " + version)
);
~~~

Read the main class:

~~~java
descriptor.mainClass().ifPresent(mainClass ->
        System.out.println("Main class: " + mainClass)
);
~~~

Complete example:

~~~java
package com.acme.app;

import java.lang.module.ModuleDescriptor;

public final class Main {
    public static void main(String[] args) {
        Module module = Main.class.getModule();
        ModuleDescriptor descriptor = module.getDescriptor();

        System.out.println("Module: " + descriptor.name());

        descriptor.version().ifPresent(version ->
                System.out.println("Version: " + version)
        );

        descriptor.mainClass().ifPresent(mainClass ->
                System.out.println("Main class: " + mainClass)
        );
    }
}
~~~

With the modular JAR packaged in the previous example, the output might be:

~~~text
Module: com.acme.app
Version: 2.4.1
Main class: com.acme.app.Main
~~~

**ModuleDescriptor.version()** and **ModuleDescriptor.mainClass()** return **Optional**, because the module version and main class are not required to be declared.

One note: **Module.getDescriptor()** can return **null** for an unnamed module. The example above assumes the class is running inside a named module that has a descriptor.

## 8. Inspecting Metadata with jar and javap

You can inspect module information without running the application:

~~~bash
jar --describe-module --file mlib/com.acme.app.jar
~~~

To view JAR contents:

~~~bash
jar --list --file mlib/com.acme.app.jar
~~~

Inspect **module-info.class** with javap:

~~~bash
javap -v --module-path mlib --module com.acme.app module-info
~~~

The verbose output shows the attributes in the class file, including the module descriptor and metadata such as **Module**, **ModuleMainClass**, or **ModuleTarget** if present.

You can use three inspection levels:

1. **jar --list** confirms the JAR contains **module-info.class** and the main class.
2. **jar --describe-module** displays the module name, version, directives, and main class.
3. **javap -v** helps deeply investigate the attribute contents of the module descriptor.

When checking a release artifact, run commands on the exact JAR being published, not merely on the compiler's class output directory.

## 9. Does Module Version Affect Module Resolution?

Module version is useful metadata for release management and artifact inspection, but JPMS does not use it as a dependency constraint like a package manager does.

Example directive:

~~~java
module com.acme.app {
    requires com.acme.lib;
}
~~~

The **requires** directive references a module by its name **com.acme.lib**. This syntax does not specify a version range such as **requires com.acme.lib [2.0, 3.0)**.

The module resolver primarily resolves modules by name and the module graph. It does not automatically pick the highest version or satisfy a version range based on **ModuleDescriptor.version()**.

Therefore:

- Module version helps identify and inspect the version of a module.
- Build tools or dependency managers are responsible for selecting artifact versions before runtime.
- Deployment must ensure the module path contains the exact intended set of JARs.
- Do not place multiple artifacts with the same module name on the module path expecting JPMS to select a version by semver rules.

Manage dependency versions with Maven, Gradle, or your project's release system; use the module descriptor version as supplementary metadata for observability and verification.

## 10. Common Errors and How to Fix Them

| Symptom | Common Cause | How to Fix |
|---|---|---|
| **jar --describe-module** does not show version | Modular JAR was not created with **--module-version** or inspecting a different JAR | Check the exact artifact and recreate it with **--module-version** |
| Running **java -m module** reports no main class | Module descriptor has no **ModuleMainClass** | Package with **--main-class** or specify **module/main-class** in the command |
| **Main-Class** is in manifest but **java -m module** still reports missing main class | Manifest `Main-Class` does not replace `ModuleMainClass` of a modular JAR | Use **jar --main-class** to record the main class into the module descriptor |
| Filename has a version but descriptor has no version | Version only exists in the artifact name | Use **--module-version** when packaging |
| Manifest has **Implementation-Version** but module version is still empty | Implementation metadata is separate from module descriptor version | Add **--module-version** |
| Runtime reads module name but version is empty | Version is optional metadata | Check **descriptor.version()** and the published artifact |
| Cannot run when omitting main class from the command | Descriptor does not declare a main class | Use **--main-class** when packaging or specify the main class when running |
| JAR is not recognized as an explicit module | Missing **module-info.class** or using an automatic/class-path JAR | Inspect the JAR with **jar --describe-module** and check its content structure |

Verification workflow:

1. Use **jar --describe-module --file** to confirm which module the JAR represents.
2. Check whether the version appears after the module name.
3. Check whether the **main-class** line has the right class name.
4. Use **jar --list** to confirm the main class and **module-info.class** are inside the JAR.
5. Run with **java --module-path ... --module module-name**.
6. Try both the syntax without specifying the main class and the syntax specifying **module/main-class**.
7. If runtime metadata is not as expected, print **Module.getDescriptor()** of the running class to identify the exact module.

## 11. Key Takeaways

- **--module-version** records the version into the module descriptor of a modular JAR.
- **--main-class** records the default main class into the module descriptor as **ModuleMainClass**.
- **jar --describe-module** is a quick way to inspect module name, version, and main class.
- **ModuleDescriptor.version()** and **mainClass()** allow reading metadata at runtime.
- **Implementation-Version** and **Specification-Version** in the manifest are package/implementation metadata; they do not replace the module version.
- **Main-Class** in the manifest serves traditional executable JARs; **ModuleMainClass** serves named modules.
- **java -m module** uses the main class in the module descriptor; **java -m module/main-class** explicitly specifies the class to run.
- JPMS does not use module version to automatically resolve version ranges; build/deployment tooling still manages dependency versions.

## References

- [The jar Command — Java SE 21 Tool Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jar.html)
- [The java Command — Java SE 21 Tool Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [ModuleDescriptor — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/ModuleDescriptor.html)
- [ModuleDescriptor.Version — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/ModuleDescriptor.Version.html)
- [Package — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Package.html)
- [JEP 261 — Module System](https://openjdk.org/jeps/261)