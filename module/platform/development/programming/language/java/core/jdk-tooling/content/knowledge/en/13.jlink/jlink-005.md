# Launchers in a jlink Runtime Image

An **in-image launcher** is an application launch command generated alongside a runtime image by the **jlink** tool. The launcher is preconfigured to use the Java runtime inside the image and run a specific module and main class. Users can start the application with a dedicated command such as greeter instead of typing the full path to java and the module/main class.

The option to create a launcher is:

~~~bash
--launcher <command>=<module>/<main-class>
~~~

Example:

~~~bash
jlink \
    --module-path mods \
    --add-modules com.example.cli \
    --launcher greeter=com.example.cli/com.example.cli.Main \
    --output image
~~~

The command above creates a runtime image in the image directory, adds the com.example.cli module, and generates a launcher named greeter in the image's bin directory. On Unix-like systems, you can run image/bin/greeter; on Windows, the launcher is typically image\bin\greeter.bat.

The launcher uses the runtime bundled with the image. The target machine does not need a separate compatible JDK or JRE installed, provided the image was built for the appropriate operating system and architecture.

## 1. What Roles Do the Runtime Image and Launcher Play?

jlink links a set of Java modules along with their transitive dependencies to produce a custom runtime image. The image is typically smaller than a full JDK because it contains only the modules and resources required by the application.

A runtime image may contain:

- The Java runtime and platform modules required by the application.
- The application modules included in the image.
- Platform-specific native libraries and runtime resources.
- The bin directory containing the java command and other linked commands.
- Application launchers generated with the --launcher option.

Example general structure:

~~~text
image/
├── bin/
│   ├── java
│   ├── keytool
│   └── greeter
├── conf/
├── legal/
├── lib/
└── release
~~~

The actual filenames and directory layout depend on the JDK, operating system, linked modules, and optimization options. On Windows, a custom launcher is generated as a batch script, typically with a .bat extension; on Unix-like systems, it is a shell script.

Two ways to run the application from the image:

~~~bash
image/bin/java \
    --module com.example.cli/com.example.cli.Main
~~~

or using the generated launcher:

~~~bash
image/bin/greeter
~~~

Both use the runtime inside the image. The launcher simply fixes the module and main class to make the launch command shorter.

## 2. --launcher Syntax

Full syntax:

~~~bash
jlink --launcher <command>=<module>
jlink --launcher <command>=<module>/<main-class>
~~~

Components:

- **command:** name of the launcher command created in the bin directory.
- **module:** name of the application module linked into the image.
- **main-class:** fully qualified name of the class containing the main method to run.

Example:

~~~bash
--launcher inventory=com.example.inventory/com.example.inventory.Main
~~~

The image will have a launcher named inventory. The launcher is configured to run the main class com.example.inventory.Main in the com.example.inventory module.

### Can the Main Class Be Omitted?

You can use the form:

~~~bash
--launcher inventory=com.example.inventory
~~~

When the main class is not specified in the launcher option, the module must have a main class recorded in the ModuleMainClass attribute. This attribute is typically set when packaging a modular JAR with the --main-class option of the jar tool.

When you are unsure whether the module has main class metadata, specify the full module/main-class in --launcher. This makes the entry point explicit and avoids relying on artifact metadata.

### The Launcher Must Point to a Module in the Image

The module specified in --launcher must be part of the module set that jlink links. Typically, the application module is included with --add-modules; jlink then adds the required transitive dependencies.

You cannot use a jlink launcher to arbitrarily run a class that is only on the classpath or a JAR that has not been included in the image. jlink operates on the module graph.

## 3. Distinguishing a jlink Launcher from the java Command

A standard java command needs to know the module and main class:

~~~bash
java --module-path mods \
    --module com.example.cli/com.example.cli.Main
~~~

If the application runs from a runtime image, you can invoke the java executable inside the image:

~~~bash
image/bin/java \
    --module com.example.cli/com.example.cli.Main
~~~

The --launcher option creates a command preconfigured for the module and main class:

~~~bash
image/bin/greeter
~~~

In terms of usage, a launcher acts like an executable shortcut. It does not compile source code, does not replace javac, does not package dependencies on its own, and is not an installer. Linking the runtime and modules was already performed when jlink ran.

A launcher typically performs the following tasks:

1. Determines the runtime image directory containing itself.
2. Invokes the Java runtime inside the image.
3. Specifies the configured module and main class.
4. Forwards application arguments to the main method.

Because the launcher is tied to the image, you can rename the image directory or move the entire image to another location on the same platform without installing a separate JDK. When moving it, keep the internal directory structure of the image intact.

## 4. Application Arguments and JVM Options

Arguments placed after the launcher are passed to the main method as String[] args.

Example:

~~~bash
image/bin/greeter production --port 8080
~~~

In Java:

~~~java
public static void main(String[] args) {
    // args[0] = "production"
    // args[1] = "--port"
    // args[2] = "8080"
}
~~~

Important note: arguments after the launcher name are application arguments. They do not automatically become JVM options such as -Xmx, -D, or -agentlib.

If you need to configure heap size or system properties, you can invoke the Java runtime in the image directly:

~~~bash
image/bin/java \
    -Xms128m \
    -Xmx512m \
    -Dapp.profile=production \
    --module com.example.cli/com.example.cli.Main \
    production --port 8080
~~~

This approach lets you pass JVM options before the module and application arguments after the main class.

Some launcher scripts generated by jlink use the JLINK_VM_OPTIONS environment variable to accept JVM options. Because script contents can vary by JDK and platform, inspect the generated script in your build environment before relying on this variable in your deployment process. The clearest way to control the JVM directly is to invoke image/bin/java with the desired options.

Do not confuse jlink's --launcher option with jpackage's --arguments and --java-options options. jpackage provides mechanisms to configure default arguments and JVM options for an application launcher; jlink focuses on linking modules and creating a command to run a module/main class.

## 5. Prerequisites for Creating a Launcher

To create a launcher in an image, prepare the following:

1. A JDK that includes the jlink tool.
2. Compiled application modules.
3. Valid module descriptors.
4. Required dependency modules on the module path or in the JDK image.
5. A main class with an appropriate entry point.
6. Exact module and main class names.
7. An output image directory that does not yet exist or has been cleaned by the build process.

A simple module descriptor:

~~~java
module com.example.cli {
}
~~~

Main class:

~~~java
package com.example.cli;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("Image launcher ready.");
    }
}
~~~

If the module uses other modules, declare dependencies in module-info.java:

~~~java
module com.example.cli {
    requires java.logging;
}
~~~

jlink reads the module graph to include the root module and its transitive dependencies in the image.

### Dependencies Must Be Modules That jlink Can Link

jlink's module path can contain modular JARs, JMOD files, or exploded module directories. A JAR that is only on the classpath is not sufficient for jlink to link it into a runtime image.

Automatic modules are also not an option for direct inclusion into an image by jlink. For legacy libraries, you need to convert them to modules with explicit descriptors or redesign how dependencies are packaged before creating the image.

If the application still requires a library outside the image, handle that dependency using an appropriate deployment mechanism, such as an external module path/classpath and a project-managed wrapper launcher. jlink's default launcher is designed to launch modules linked into the image.

## 6. Workflow for Creating an Image with a Launcher

General workflow:

~~~text
module-info.java + source files
             |
             v
          javac
             |
             v
       exploded module
             |
             v
           jlink
       /     |      \
      /      |       \
runtime   module    launcher
image     graph     command
      \      |       /
       \     |      /
             v
       image/bin/app
             |
             v
       application main
~~~

Steps:

1. Write the module descriptor and source code.
2. Compile the module with javac.
3. Verify modules and dependencies.
4. Select the root module for the image with --add-modules.
5. Specify the module path so jlink can locate the modules.
6. Create the launcher with --launcher.
7. Specify the image directory with --output.
8. Test running the launcher from the newly created image.
9. Verify the modules and resources included in the image.
10. Package the entire image for deployment on the target platform.

You do not need to bundle a full JDK with the application. The runtime image created by jlink already contains the runtime required for the linked module graph.

## 7. Complete Hands-On Example with Java 17+

This example creates the com.example.cli module and a launcher named greeter. The program prints a fixed line and displays arguments passed through the launcher.

Project structure:

~~~text
jlink-launcher-demo/
└── src/
    └── com.example.cli/
        ├── module-info.java
        └── com/
            └── example/
                └── cli/
                    └── Main.java
~~~

### Step 1: Create the Module Descriptor

Create src/com.example.cli/module-info.java:

~~~java
module com.example.cli {
}
~~~

The module does not need any dependencies outside java.base in this example.

### Step 2: Create the Main Class

Create src/com.example.cli/com/example/cli/Main.java:

~~~java
package com.example.cli;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("Image launcher ready.");

        if (args.length > 0) {
            System.out.println("args=" + String.join("|", args));
        }
    }
}
~~~

The main class has the public static void main(String[] args) method, which is the entry point the launcher will invoke.

### Step 3: Compile the Module

From the jlink-launcher-demo root directory, create the output directory:

~~~bash
mkdir -p mods
~~~

Compile with Java 17:

~~~bash
javac --release 17 \
    --module-source-path src \
    -d mods \
    -m com.example.cli
~~~

On PowerShell:

~~~powershell
New-Item -ItemType Directory -Force -Path "mods" | Out-Null
javac --release 17 --module-source-path "src" -d "mods" -m com.example.cli
~~~

Result:

~~~text
mods/
└── com.example.cli/
    ├── module-info.class
    └── com/
        └── example/
            └── cli/
                └── Main.class
~~~

This is an exploded module. The com.example.cli directory contains module-info.class and the module's classes.

### Step 4: Create the Runtime Image and Launcher on Linux/macOS

Run from the project root directory:

~~~bash
jlink \
    --module-path "mods:$JAVA_HOME/jmods" \
    --add-modules com.example.cli \
    --launcher greeter=com.example.cli/com.example.cli.Main \
    --output image
~~~

In this command:

- **--module-path** tells jlink where to find the exploded module and JDK modules.
- **--add-modules com.example.cli** selects the application module as the root module.
- **--launcher greeter=...** creates the greeter command for the main class.
- **--output image** creates the runtime image in the image directory.

### Step 5: Create the Runtime Image on Windows PowerShell

The module path element separator on Windows is a semicolon:

~~~powershell
jlink --module-path "mods;$env:JAVA_HOME\jmods" --add-modules com.example.cli --launcher greeter=com.example.cli/com.example.cli.Main --output image
~~~

If JAVA_HOME is not set, you can pass the absolute path to the jmods directory of the JDK in use.

Do not use a colon as the module path separator on Windows; the separator depends on the operating system.

### Step 6: Inspect the Launcher and Image

After jlink finishes, the structure looks like:

~~~text
image/
├── bin/
│   ├── java
│   ├── keytool
│   └── greeter
├── conf/
├── legal/
├── lib/
└── release
~~~

On Windows, the custom launcher is typically named greeter.bat in image\bin.

You can list the modules in the image:

~~~bash
image/bin/java --list-modules
~~~

On Windows:

~~~powershell
.\image\bin\java.exe --list-modules
~~~

The list shows the linked modules along with the runtime version. The actual set of modules depends on the JDK and the application's dependencies.

### Step 7: Run the Launcher

On Linux/macOS:

~~~bash
./image/bin/greeter
~~~

On Windows PowerShell:

~~~powershell
.\image\bin\greeter.bat
~~~

Output:

~~~text
Image launcher ready.
~~~

Passing arguments:

~~~bash
./image/bin/greeter production 8080
~~~

Output:

~~~text
Image launcher ready.
args=production|8080
~~~

This is the output of the sample application. You do not need to invoke java from PATH; the launcher uses the runtime inside the image.

### Step 8: Run Directly Using java in the Image

You can bypass the launcher and invoke the module/main class:

~~~bash
image/bin/java \
    --module com.example.cli/com.example.cli.Main \
    production 8080
~~~

Output:

~~~text
Image launcher ready.
args=production|8080
~~~

Both approaches use the same module and runtime. The java command is useful when you need to pass JVM options; the launcher is convenient when you want to provide a fixed command for users.

## 8. Multiple Launchers in the Same Image

A single runtime image can contain multiple launchers for multiple entry points across the linked modules.

Example:

~~~bash
jlink \
    --module-path mods \
    --add-modules com.example.cli,com.example.admin \
    --launcher greeter=com.example.cli/com.example.cli.Main \
    --launcher admin=com.example.admin/com.example.admin.Main \
    --output image
~~~

The image will have two application commands:

~~~text
image/
└── bin/
    ├── java
    ├── greeter
    └── admin
~~~

On Windows, the corresponding commands are generated as platform-specific batch launchers.

Each launcher is bound to a specific module and main class. All launchers share the same runtime image, so you do not need to build two separate runtimes if two applications can share a module graph.

Before creating multiple launchers, ensure every module referenced by the launchers is included in the image. The --add-modules option can accept multiple comma-separated module names.

## 9. ServiceLoader and --bind-services

If the application uses ServiceLoader, the application module can declare uses and the provider module can declare provides.

Consumer example:

~~~java
module com.example.app {
    requires com.example.spi;
    uses com.example.spi.GreetingService;
}
~~~

Provider example:

~~~java
module com.example.provider {
    requires com.example.spi;

    provides com.example.spi.GreetingService
        with com.example.provider.DefaultGreetingService;
}
~~~

When creating the image, you can add the provider module explicitly with --add-modules or use the option:

~~~bash
--bind-services
~~~

--bind-services instructs jlink to link service provider modules and their corresponding dependencies during service binding.

Example:

~~~bash
jlink \
    --module-path mods \
    --add-modules com.example.app \
    --bind-services \
    --launcher app=com.example.app/com.example.app.Main \
    --output image
~~~

A service provider is only included in the image when module resolution and service binding identify a matching provider. If the application requires a specific provider, adding the provider module explicitly makes the build more predictable.

Using --bind-services can increase the image size because more provider modules are linked. Check the module list after the build to confirm the actual set of modules.

You can find suitable providers for a service using:

~~~bash
jlink --suggest-providers com.example.spi.GreetingService
~~~

This command suggests provider modules on the module path for the specified service type.

## 10. Runtime Image Optimization Options

In addition to launchers, jlink provides options to tailor the image contents:

| Option | Effect |
|---|---|
| --strip-debug | Strips debug information from the image |
| --no-header-files | Excludes header files from the image |
| --no-man-pages | Excludes man pages from the image |
| --bind-services | Links service providers and dependencies |
| --limit-modules | Limits the universe of observable modules during resolution |
| --save-opts | Saves build options to a file |
| --list-plugins | Lists plugins supported by jlink |

Example of a leaner image:

~~~bash
jlink \
    --module-path mods \
    --add-modules com.example.cli \
    --launcher greeter=com.example.cli/com.example.cli.Main \
    --strip-debug \
    --no-header-files \
    --no-man-pages \
    --output image
~~~

Do not enable or disable plugins solely to reduce size without testing. Certain resources or metadata may be needed for debugging, diagnostics, locales, or deployment.

Compression options vary by JDK version. Run jlink --list-plugins and read the help output for the exact JDK you are using before setting --compress. Do not copy compression values verbatim from another JDK version without verifying them.

## 11. jlink Launchers vs. jpackage Launchers

The two tools serve different goals:

| Tool | Primary Output | Launcher |
|---|---|---|
| jlink | Custom runtime image from a module graph | Creates a module/main command via --launcher |
| jpackage | Application image or platform installer package | Creates an application launcher with additional configuration and OS integration |

jlink focuses on the runtime image. Its launcher is a way to run a linked module and main class.

jpackage packages an application for distribution. It can produce an application image, EXE/MSI installers on Windows, DEB/RPM on Linux, or PKG/DMG on macOS depending on the platform. If no pre-built runtime image is supplied, jpackage can invoke jlink to create the runtime.

Example of packaging a modular application with jpackage:

~~~bash
jpackage \
    --type app-image \
    --name Greeter \
    --module-path mlib \
    --module com.example.cli/com.example.cli.Main
~~~

jpackage has its own options such as --arguments, --java-options, and --add-launcher to configure an application image's launchers. These options are not jlink syntax.

If you only need a runtime image with a command to launch a module, jlink is sufficient. If you need an installer, icon, shortcut, application bundle, or end-user launcher configuration, consider jpackage.

## 12. Limitations and Deployment Considerations

### Platform-Specific Images

A runtime image contains native libraries and a runtime built for a specific operating system, architecture, and JDK. Do not build an image on Linux and assume it can run directly on Windows or macOS.

Build and test the image separately for each target platform. Account for CPU architecture, operating system version, native libraries, and runtime environment distribution requirements.

### No Automatic Updates

A custom runtime image does not have an automatic JDK update mechanism like some standard Java installations. The development team must rebuild and redistribute the image when JDK updates, security patches, or runtime dependencies are needed.

Establish a process for rebuilding, testing, and releasing the image for each platform. Do not treat a once-built image as an automatically maintained runtime.

### Cannot Link Arbitrary Classpath JARs

jlink requires modules that it can resolve. Dependencies that only exist on the classpath or as automatic modules cannot be handled as explicit named modules in the runtime image.

For legacy libraries, check module descriptors, Automatic-Module-Name, and dependencies. You may need to upgrade the library, create an appropriate module descriptor, or use a different packaging approach.

### Non-Existent or Misspelled Main Class

If the module name or main class in --launcher is incorrect, the launcher will fail to start the application properly. Verify the module name, package, class name, and compiled class files.

### Missing Dependencies

If an application module uses another module without declaring it properly in the descriptor, javac or jlink may report a resolution error. Check requires directives, the module path, and the module graph.

### Recreating an Image in an Existing Directory

jlink requires an appropriate output path for a new image. In build pipelines, manage the output cleanup step explicitly. Do not overwrite an image currently in use by another process.

### Launcher Not Accepting JVM Options as Expected

Arguments after the launcher are passed to the application. If you need to change heap settings, system properties, or agents, invoke image/bin/java with JVM options or use an explicitly managed wrapper script.

### Image Missing Debugging Tools

A minimal image may lack jcmd, jfr, or other diagnostic tools if the corresponding modules are not linked. If production troubleshooting is needed, decide in advance whether to include diagnostic modules in the image or use an external toolset.

## 13. Verifying the Image After Creation

After jlink completes, verify the following:

1. The image directory was created and has a valid structure.
2. The launcher command appears in image/bin.
3. The runtime in the image is the expected version.
4. The module list includes the application module and required dependencies.
5. The launcher executes the intended main class.
6. Arguments are passed accurately into String[] args.
7. Required resources, locales, and service providers are present.
8. The image runs on the target operating system and architecture.
9. The image size meets distribution requirements.
10. The image update process is defined.

Verification commands:

~~~bash
image/bin/java --version
image/bin/java --list-modules
image/bin/java --describe-module com.example.cli
~~~

On Windows:

~~~powershell
.\image\bin\java.exe --version
.\image\bin\java.exe --list-modules
.\image\bin\java.exe --describe-module com.example.cli
~~~

You can verify the image by running Java inside the image directly, then running the launcher. If the two produce different results, inspect the launcher script, module/main class, and passed arguments.

## 14. Recommended Build and Release Workflow

A reproducible workflow:

1. Build the application modules using the exact target JDK.
2. Run unit tests and validate module descriptors.
3. Identify root modules and required dependencies.
4. Check service providers if the application uses ServiceLoader.
5. Run jlink with explicit module path, add-modules, and launcher options.
6. Add optimization plugins after operational requirements are confirmed.
7. Inspect the module list and launcher files.
8. Run integration tests through the launcher.
9. Run tests on the target operating system and architecture.
10. Package the entire runtime image as a distribution artifact.
11. Record the JDK version, module graph, and jlink options used.
12. Schedule image rebuilds and releases when the JDK or dependencies require updates.

For cross-platform applications, build one image per platform. For applications with multiple entry points, consider multiple launchers in the same image if they share the module graph and runtime.

## 15. Summary of Essential Commands

~~~bash
# Compile module
javac --release 17 --module-source-path src -d mods -m com.example.cli

# Create image and launcher
jlink \
    --module-path mods \
    --add-modules com.example.cli \
    --launcher greeter=com.example.cli/com.example.cli.Main \
    --output image

# Inspect modules
image/bin/java --list-modules

# Run generated launcher
image/bin/greeter

# Run with explicit JVM options
image/bin/java -Xmx512m \
    --module com.example.cli/com.example.cli.Main
~~~

An in-image launcher is a convenient command for running a module linked with a custom runtime. When the module graph, main class, dependencies, and target platform are properly specified, jlink produces a deployable image that does not require users to install a separate JDK.

## References

- [The jlink Command — Java Platform, Standard Edition](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html)
- [The java Command — Java Platform, Standard Edition](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [The jpackage Command — Java Platform, Standard Edition](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html)
- [Creating Runtime and Application Images with jlink — dev.java](https://dev.java/learn/jlink/)
