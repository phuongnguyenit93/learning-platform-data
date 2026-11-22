# Distinguishing Modular JARs from Runtime Images

Modular JARs and runtime images both belong to the Java Module System, but they solve two different problems. **A modular JAR is an application or library artifact with a module descriptor**. **A runtime image is a Java execution environment linked from the required modules**, typically created with jlink.

A modular JAR is distributed as an archive file on the module path and requires a compatible Java runtime. A runtime image contains the required runtime together with the linked application modules. Therefore, a runtime image enables deploying an application without requiring users to install a separate JDK or JRE.

## 1. Modular JAR

A modular JAR is a JAR file that has a module descriptor, typically module-info.class at the root directory. The descriptor declares the module name, dependencies, exported or opened packages, services used, and providers supplied.

Example:

~~~text
com.example.app.jar
|-- module-info.class
|-- com/
    |-- example/
        |-- app/
            |-- Main.class
~~~

Module descriptor:

~~~java
module com.example.app {
    requires java.logging;
    exports com.example.app.api;
}
~~~

Create a modular JAR from the out directory containing module-info.class and compiled classes:

~~~bash
jar --create --file mods/com.example.app.jar --main-class com.example.app.Main -C out .
~~~

Inspect the archive:

~~~bash
jar --describe-module --file mods/com.example.app.jar
jar --list --file mods/com.example.app.jar
~~~

Run the module from the module path:

~~~bash
java --module-path mods --module com.example.app
~~~

Or specify the main class:

~~~bash
java --module-path mods --module com.example.app/com.example.app.Main
~~~

A modular JAR only packages an application or library module. It does not carry the entire Java runtime with it. At runtime, the java command is still taken from a JDK/JRE installed on the machine or from a runtime image distributed with the application.

## 2. Runtime Image

A runtime image is a directory structure containing a Java runtime linked with a selected set of modules. The jlink tool creates the image from resolvable modules, including JDK platform modules and application modules on the module path.

Typical structure:

~~~text
app-image/
|-- bin/
|   |-- java
|   |-- keytool
|   |-- app
|-- conf/
|-- legal/
|-- lib/
|   |-- modules
|   |-- security/
|-- release
~~~

Exact filenames and directory details may vary by operating system and configuration. The key point is that the image has a Java launcher and a module image containing the linked modules. It is not a single JAR file.

A runtime image can include the platform Java modules the application needs, linked application modules, provider modules matched via service binding, the Java launcher, and necessary runtime components.

A runtime image is built for a target platform. An image built on Windows does not run directly on Linux or macOS. When releasing for multiple platforms, you must build a corresponding image for each operating system and architecture.

## 3. Comparison

| Criterion | Modular JAR | Runtime Image |
|---|---|---|
| Nature | Archive containing one module | Linked Java environment |
| Format | Single JAR file | Image directory with runtime layout |
| Contents | Classes, resources, and module descriptor | Java runtime, module image, and launcher |
| Purpose | Distribute an application or library module | Deploy a custom runtime |
| Required runtime | Needs a compatible JDK/JRE where it runs | Already contains the needed runtime |
| Creation tool | javac and jar | jlink |
| Number of modules | One modular JAR represents one module | One image can contain multiple modules |
| Platform | JARs generally work across platforms with a matching runtime | Image is tied to the target OS and architecture |
| How to launch | java --module-path ... --module ... | Java launcher located inside the image |

Do not think of a runtime image as a big kind of JAR. A modular JAR is a module distribution artifact; a runtime image is a deployment output containing a linked execution environment.

## 4. jlink and the Module Path

jlink reads module descriptors, resolves the dependency graph, and links selected modules into a runtime image. Application modules are provided via the module path alongside JDK system modules.

Example module directory:

~~~text
mods/
|-- com.example.app.jar
|-- com.example.data.jar
|-- com.example.logging.jar
~~~

Suppose com.example.app requires com.example.data, and com.example.data requires java.sql. When linking the root module com.example.app, jlink resolves required dependencies and includes the modules in the graph into the image.

Command on Linux or macOS:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app --output app-image
~~~

On Windows, use a semicolon to separate module path entries:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.app --output app-image
~~~

The module path includes the JDK's jmods directory and the directory containing modular JARs. add-modules specifies the root module. jlink resolves requires dependencies from the root module and creates the image in the output directory.

You do not need to manually list transitive dependencies if they are properly declared in requires. Every application module to be linked must be present on the module path and resolvable by jlink.

## 5. Creating a Custom Launcher

You can instruct jlink to create a custom-named launcher:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app --launcher app=com.example.app/com.example.app.Main --output app-image
~~~

The launcher app is created in the image's bin directory. Users run the application with this launcher without having to type the java --module command themselves.

If you do not create a custom launcher, call the Java launcher directly:

~~~bash
app-image/bin/java --module com.example.app
~~~

On Windows, the corresponding executable resides in the bin directory and is named java.exe.

A custom launcher simplifies deployment scripts and fixes the entry point. It does not automatically package external resources such as configuration files, data, or certificates that the application needs.

## 6. Selecting Modules for the Image

jlink starts from one or more root modules. requires dependencies are resolved according to the module graph.

| Option | Meaning |
|---|---|
| --module-path | Location to find input modules |
| --add-modules | Root modules to link |
| --bind-services | Also resolves provider modules for used services |
| --limit-modules | Restricts the observable module set during resolution |
| --launcher | Creates a custom launcher for a module and main class |
| --output | Output runtime image directory |
| --list-plugins | Lists available jlink plugins |

Example application using ServiceLoader and needing provider modules:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app --bind-services --output app-image
~~~

--bind-services instructs the linker to consider provider modules matching services used in the module graph. If the application loads plugins dynamically or has separate plugin configuration, design the linked module set accordingly; do not assume every plugin JAR will automatically appear in the image.

You can pass multiple root modules:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app,com.example.monitoring --output app-image
~~~

Each root can pull in its own dependencies. The image contains the set of modules needed according to resolution configuration and linker options.

## 7. Optimizing the Runtime Image

jlink has options to reduce image size or omit unnecessary components:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app --strip-debug --no-header-files --no-man-pages --compress=2 --output app-image
~~~

- --strip-debug removes debug information from linked modules.
- --no-header-files excludes native headers from the image.
- --no-man-pages excludes manual pages from the image.
- --compress=2 applies the compression level supported by the JDK.

These options can reduce size, but they also remove content useful for development or diagnostics. Do not apply them mechanically to images used for debugging. Measure size and test the application after linking.

Image size does not depend solely on the number of application JARs. JDK modules can pull in other modules, providers can be bound, and native runtime components also take up space. Inspect the module list after creation to see what the image actually contains.

## 8. Inspecting and Running the Image

Use the Java launcher inside the image to list modules:

~~~bash
app-image/bin/java --list-modules
~~~

Describe a module:

~~~bash
app-image/bin/java --describe-module com.example.app
~~~

Check the runtime version:

~~~bash
app-image/bin/java --version
~~~

Run the application:

~~~bash
app-image/bin/java --module com.example.app
~~~

Or run the custom launcher:

~~~bash
app-image/bin/app
~~~

If the application fails to start, check root modules, requires dependencies, needed providers, the launcher, configuration files, resources outside JARs, native libraries, and the target OS and architecture.

A successfully linked image does not guarantee every application feature works. Resources outside modules, configurations, native libraries, and external system connections still need testing.

## 9. Limitations of jlink and Automatic Modules

jlink requires modules with an appropriate structure to create an image. Automatic modules are not a direct substitute input for explicit modules in standard linking workflows. If a library only has a JAR without a module descriptor and is being used as an automatic module, it needs to be converted to an explicit module or repackaged appropriately before linking.

Remediation approaches:

- Upgrade the library to a version that provides module-info.class.
- Create a module descriptor if you control the source and dependencies.
- Repackage into a modular JAR and verify packages, service metadata, and dependencies.
- Replace the library with an implementation that already supports the module system.

Do not create a dummy descriptor just to make jlink accept an artifact without properly determining requires, exports, opens, uses, and provides. An incorrect descriptor can allow the application to resolve yet fail at runtime.

jlink creates a runtime image rather than a complete installer. If you need an installer, shortcuts, file associations, or OS integration, you can combine jpackage with a runtime image and deployment resources.

## 10. Modular JAR, Runtime Image, and jpackage

~~~text
Source code
    |
    | javac
    v
Compiled module
    |
    | jar
    v
Modular JAR(s)
    |
    | jlink
    v
Custom runtime image
    |
    | jpackage
    v
Application package / installer
~~~

| Tool | Output | Role |
|---|---|---|
| javac | Class files and module-info.class | Compiles modules |
| jar | Modular JAR | Packages application or library modules |
| jlink | Runtime image | Links a custom runtime |
| jpackage | Application package or installer | Packages applications for end users, optionally including a runtime image |

jpackage can use an already-created runtime image or create a suitable image during packaging depending on configuration. Modular JARs and runtime images can coexist in a release pipeline while serving different purposes.

## 11. Choosing a Distribution Artifact

| Need | Suitable Choice |
|---|---|
| Distribute a library for other applications to use | Modular JAR |
| Distribute application modules for an environment with a suitable Java | Modular JAR or multiple modular JARs |
| Do not want users to install a separate JDK/JRE | Runtime image |
| Want to include only the Java modules the application needs | Runtime image via jlink |
| Run the application on multiple operating systems | Build a separate image for each platform |
| Need an installer, shortcuts, or OS integration | jpackage, often combined with a runtime image |
| Need to update libraries independently | Modular JAR |
| Need a runtime with controlled modules and version | Runtime image |

If a server environment already manages the Java runtime, modular JARs can be easier to update and deploy. If releasing a desktop application or standalone tool to end users, a runtime image helps control the runtime and avoid depending on Java installed on the machine.

## 12. Key Takeaways

A modular JAR is an archive with a module descriptor, used to distribute a single module. A runtime image is a Java environment linked from selected modules, containing a Java launcher and necessary runtime components. jlink takes modules from the module path, resolves dependencies, and builds the image; it does not merely repackage JARs.

Use modular JARs when distributing standalone modules and use runtime images when distributing a complete custom execution environment. Inspect modules with jar --describe-module, inspect image contents with java --list-modules, and run the application using the launcher inside the image. For end-user distribution, consider jpackage to create platform-appropriate installation packages.

## References

- Oracle JDK — The jlink Command: https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html
- Oracle JDK — The jar Command: https://docs.oracle.com/en/java/javase/26/docs/specs/man/jar.html
- Oracle JDK — The jpackage Command: https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html
- Java Platform Module System — Module API: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/module/package-summary.html
