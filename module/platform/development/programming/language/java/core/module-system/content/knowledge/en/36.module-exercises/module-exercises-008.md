# Creating a Runtime Image with jlink

jlink is a JDK tool used to create a custom runtime image from resolved modules. Instead of requiring the target machine to install a full JDK or JRE, an application can be distributed with an image containing the Java runtime and the modules needed to run the application.

Modular JARs and runtime images solve two different problems. A modular JAR packages an application or library module. A runtime image is a Java execution environment linked from a set of modules, typically created with jlink. If an installer, shortcut, or operating system integration is needed, jpackage can be used after the image creation step.

## 1. What does jlink produce?

A runtime image is a structured directory containing the linked Java runtime. Typical structure:

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

File and directory details depend on the operating system, architecture, and jlink configuration. The bin directory contains the Java launcher and retained runtime tools. lib contains the module image and runtime libraries; conf contains configuration; legal contains license information.

An image is not a JAR or an installer. It is a Java environment that can be run directly on the corresponding platform. An image built for Windows cannot be treated as a shared image for Linux or macOS. Separate images must be built and tested for each target operating system and architecture.

## 2. Input prerequisites

jlink requires resolvable modules. Typically needed:

- A JDK matching the Java version the application requires.
- Application modules with valid module descriptors.
- Required modular dependencies.
- The JDK's jmods directory to locate platform modules.
- An output directory for the new image.

jlink works with explicit modules such as system modules, modular JARs, JMODs, or exploded modules. JARs on the classpath and automatic modules are not direct substitutes for explicit modules in the linking process. If a library is only a regular JAR, upgrade or modularize it before linking.

Check the tools:

~~~bash
java --version
javac --version
jlink --version
~~~

Ensure java, javac, and jlink come from the same JDK. JAVA_HOME should point to that JDK; the jmods directory is typically located at JAVA_HOME/jmods.

## 3. Preparing a modular application

Example module named com.example.app with main class com.example.app.Main.

Source structure:

~~~text
src/
|-- com.example.app/
    |-- module-info.java
    |-- com/
        |-- example/
            |-- app/
                |-- Main.java
~~~

Module descriptor:

~~~java
module com.example.app {
    requires java.logging;
}
~~~

Main class:

~~~java
package com.example.app;

import java.util.logging.Logger;

public class Main {
    private static final Logger LOG =
            Logger.getLogger(Main.class.getName());

    public static void main(String[] args) {
        LOG.info("Application started");
        System.out.println("Hello from a custom runtime image");
    }
}
~~~

java.base is implicitly depended on by every module, so there is no need to declare requires java.base.

Compile the module into the mods directory:

~~~bash
javac -d mods/com.example.app src/com.example.app/module-info.java src/com.example.app/com/example/app/Main.java
~~~

After compilation, the exploded module directory has module-info.class and the classes in their packages. It can be packaged into a modular JAR if the build pipeline requires an archive:

~~~bash
jar --create --file mods/com.example.app.jar --main-class com.example.app.Main -C mods/com.example.app .
~~~

jlink can use either exploded modules or modular JARs as input. There is no need to create a JAR only to extract it again if the build already produced a valid exploded module.

## 4. Creating a basic runtime image

The jlink command needs to know where to find system modules and application modules:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app --output app-image
~~~

Meaning:

1. --module-path specifies where to search for modules. The example includes the JDK's jmods directory and the mods directory containing exploded modules or modular JARs.
2. --add-modules specifies the root module to include in the configuration.
3. jlink resolves the root module's requires and necessary dependencies.
4. --output specifies the output runtime image directory.

On Windows, the module path separator is a semicolon:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.app --output app-image
~~~

On Linux and macOS, the separator is typically a colon. Use the right separator for the operating system in build scripts.

If the module path is missing a dependency, jlink reports a resolution error. Identify the missing module and supply the right artifact; do not randomly dump every JAR in to mask the error.

## 5. Root modules and dependency resolution

--add-modules specifies the root modules to include in the image. jlink uses module descriptors to resolve requires dependencies, including transitive dependencies needed for the module graph.

Example:

~~~text
com.example.app
    |
    +-- requires com.example.orders
    |       |
    |       +-- requires com.example.persistence
    |
    +-- requires java.logging
~~~

If com.example.app is the root, the required dependencies are resolved according to the descriptors. There is no need to list every requires dependency individually if the module graph is completely declared.

Multiple root modules can be specified:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app,com.example.monitoring --output app-image
~~~

Use multiple roots when a module needs to be present even though it is not pulled in through normal dependencies. The --limit-modules option restricts the set of observable modules during resolution. If restricted too tightly, valid dependencies may not be found.

## 6. Using jlink with ServiceLoader

If the application uses ServiceLoader, the consumer module must declare uses and the provider module must declare provides ... with ....

Consumer example:

~~~java
module com.example.app {
    uses com.example.spi.GreetingService;
}
~~~

Provider module:

~~~java
module com.example.greeting.provider {
    requires com.example.spi;

    provides com.example.spi.GreetingService
        with com.example.greeting.provider.DefaultGreetingService;
}
~~~

If you want the linker to find and link matching providers for the used services, use --bind-services:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app --bind-services --output app-image
~~~

--bind-services instructs resolution to consider service binding and matching provider modules on the module path. Providers must have valid module descriptors and reside in the module sources observable by the linker.

Do not assume every plugin will automatically appear in the image. Plugins loaded dynamically from a directory outside the image or from a separate ModuleLayer need their own distribution and loading strategy. If a plugin must be inside the image, specify roots/service binding clearly and verify the module is actually linked.

## 7. Creating a custom launcher

You can ask jlink to generate a named launcher:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app --launcher app=com.example.app/com.example.app.Main --output app-image
~~~

The app launcher is created in the image's bin directory. The launcher syntax is the launcher name, an equals sign, then the module name and main class separated by a slash.

If no separate launcher is created, invoke the Java launcher inside the image:

~~~bash
app-image/bin/java --module com.example.app
~~~

On Windows, the corresponding executable resides in app-image/bin and is named java.exe. Launcher names and extensions depend on the platform.

A custom launcher fixes the entry point, but does not automatically package configuration files, data, certificates, native libraries, or external non-module files the application needs. Those resources must be included in the deployment package separately.

## 8. Optimizing image size

jlink has options to reduce size or omit unnecessary components:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app --strip-debug --no-header-files --no-man-pages --compress=2 --output app-image
~~~

| Option | Effect |
|---|---|
| --strip-debug | Strips debug information from linked modules |
| --no-header-files | Excludes native header files from the image |
| --no-man-pages | Excludes man pages from the image |
| --compress=2 | Enables the corresponding compression level supported by the JDK |
| --include-locales | Limits locale data included in the image |

Optimization options can remove data useful for debugging or diagnostics. Build a baseline image first, measure its size, apply options one by one, and re-run tests.

If the application needs locales beyond the default set, check the jdk.localedata module and appropriate include-locales settings. Do not strip locale data just to save space if the application needs to format dates, numbers, or messages in those locales.

## 9. Analyzing required modules

jdeps can analyze bytecode dependencies and suggest required system modules:

~~~bash
jdeps --module-path "$JAVA_HOME/jmods:mods" --print-module-deps mods/com.example.app.jar
~~~

The output helps identify dependencies detected from bytecode. jdeps does not fully detect all dependencies created dynamically via reflection, ServiceLoader, class names from config, JNI, or native code. Do not treat this output as an absolute complete list; combine it with module descriptors, application config, and runtime tests.

Inspect the archive's descriptor:

~~~bash
jar --describe-module --file mods/com.example.app.jar
~~~

## 10. Inspecting the image after creation

Run inspection commands from the Java launcher inside the image.

List modules:

~~~bash
app-image/bin/java --list-modules
~~~

Describe the application module:

~~~bash
app-image/bin/java --describe-module com.example.app
~~~

Check the runtime version:

~~~bash
app-image/bin/java --version
~~~

Run the application using the image:

~~~bash
app-image/bin/java --module com.example.app
~~~

Or run the custom launcher:

~~~bash
app-image/bin/app
~~~

On Windows, use the executable in the app-image/bin directory. Using the image's Java launcher confirms the application is running on the linked runtime instead of accidentally using a globally installed JDK on the build machine.

## 11. Testing in a clean environment

A runtime image should be tested in an environment that does not rely on the build machine's JDK. Copy the image to a platform-matching VM or container where no other JDK is installed, then run the application.

Minimum checks:

- Launcher starts the right module and main class.
- Dependency modules are present in the image.
- Service providers are found if the application uses ServiceLoader.
- External configuration files and resources outside modules are found.
- Native libraries and JNI work if used by the application.
- Locale, timezone, charset, and security configuration meet requirements.
- Database, network, and external system connections work.
- Logging, file output, and relative paths are correct in the deployment directory.
- Application starts after changing the working directory.
- Image runs on the exact target operating system and architecture.

A successfully linked image only proves that the module linking process completed. It does not prove every business path or external non-JDK dependency works.

## 12. Limitations of jlink

jlink is not a tool that packages arbitrary JARs into a runtime. Input modules must be resolvable by the module system. Non-modular JARs, automatic modules, and classpath dependencies must be addressed before linking.

Ways to handle legacy libraries:

- Upgrade to a version that provides module-info.class.
- Create an appropriate module descriptor if source and dependencies can be controlled.
- Repackage into an explicit modular JAR and check packages, service metadata, reflection, and dependencies.
- Replace the library with an implementation supporting the module system.

Do not create a fake module descriptor just to make jlink accept an archive. The descriptor must accurately reflect requires, exports, opens, uses, and provides. A module that resolves successfully yet declares things inaccurately can still cause runtime failures.

jlink also does not create OS installers, shortcuts, file associations, or OS service registrations. If those capabilities are needed, use jpackage or an appropriate platform packaging tool.

## 13. Combining with jpackage

A release pipeline often looks like:

~~~text
Source code
    |
    | javac
    v
Compiled named modules
    |
    | jar (if needed)
    v
Modular JARs
    |
    | jlink
    v
Custom runtime image
    |
    | jpackage
    v
Application package / installer
~~~

jpackage can use a pre-built runtime image or build an appropriate image during packaging depending on configuration. jlink focuses on creating a runtime image; jpackage focuses on creating an end-user application package.

When releasing, build separate packages for each target platform, verify license requirements, and test installers in a clean environment. A runtime image does not automatically update when a new JDK releases; when security patches or JDK updates are needed, rebuild and release a new image.

## 14. Common Errors

- **Missing module on module path:** jlink cannot resolve dependencies. Supply the right modular artifact or JMOD.
- **Passing an automatic module to link:** convert the dependency into an explicit module before linking.
- **Insufficient root module selection:** a needed module without a normal dependency relationship or service binding may be omitted from the image.
- **Forgetting uses/provides:** ServiceLoader does not discover providers as expected.
- **Wrong module path separator:** Windows uses a semicolon; Linux and macOS typically use a colon.
- **Creating launcher with wrong module/main class:** check module name and fully qualified main class.
- **Assuming all resources are linked:** config files, data, and native libraries outside modules must be packaged separately.
- **Testing only on the build machine:** may accidentally use a pre-installed JDK or libraries. Test using the image in a clean environment.
- **Using one image for all operating systems:** build images per target platform and architecture.
- **Not rebuilding when updating JDK:** a runtime image is a snapshot of the linked runtime; rebuild the image when updating the JDK.

## 15. Practical Workflow

1. Confirm application modules have module-info.class and dependencies are properly declared.
2. Compile modules with javac.
3. Package modular JARs if required by the pipeline.
4. Run jar --describe-module to inspect descriptors.
5. Use jdeps to review bytecode dependencies and cross-check module descriptors.
6. Run jlink with a module path containing JDK jmods and application modules.
7. Select root modules with --add-modules; add --bind-services when service binding is needed.
8. Create a launcher with --launcher if a dedicated entry point is desired.
9. Apply size optimizations after establishing a baseline.
10. Inspect the image with java --list-modules, --describe-module, and --version.
11. Run the application using the launcher inside the image.
12. Test in a clean environment and on each release platform.
13. Use jpackage if OS-integrated installers or distribution packages are needed.

## 16. Remember

jlink creates a custom runtime image from resolvable modules. Specify the module path, select root modules, let the linker resolve dependencies, and write the image to the output directory. You can use --bind-services for service providers, --launcher for a dedicated entry point, and strip/compress options to reduce size.

A modular JAR is a module distribution input; a runtime image is a linked execution environment. The image must be inspected using its own Java launcher and tested on the target platform. For end-user applications, jpackage can package a runtime image into an installer. Rebuild the image when updating the JDK to receive patches and runtime changes.

## References

- Oracle JDK — The jlink Command: https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html
- Oracle JDK — The jar Command: https://docs.oracle.com/en/java/javase/26/docs/specs/man/jar.html
- Oracle JDK — The jdeps Command: https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html
- Oracle JDK — The jpackage Command: https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html