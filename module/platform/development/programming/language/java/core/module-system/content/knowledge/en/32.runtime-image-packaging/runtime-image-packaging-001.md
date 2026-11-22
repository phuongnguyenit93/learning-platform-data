# jlink and Custom Runtime Images

> Scope: Java Platform Module System (JPMS). **jlink** is a JDK tool used to link a set of named modules along with their required dependencies into a custom runtime image. This image can be distributed with the application to run on a target machine without needing a full JDK installed.

## Objectives

After this lesson, you will be able to:

- Explain custom runtime images and the role of **jlink**.
- Prepare explicit modules as input for the linking process.
- Analyze dependencies to select root modules using **--add-modules**.
- Create an image from JDK modules and application modules.
- Integrate service providers using **--bind-services** when needed.
- Create a custom launcher for the application using **--launcher**.
- Reduce image size using appropriate packaging options.
- Run and verify the application using the created runtime image itself.

## 1. What Is a Custom Runtime Image?

A **runtime image** is a directory tree containing the Java runtime and the packaged modules needed to run a program. A full JDK typically includes development tools such as **javac**, **javadoc**, **jlink**, and build libraries. A custom runtime image created by **jlink** focuses on the set of modules needed for the application, so it is usually smaller than a full JDK.

The image structure may look similar to:

~~~text
runtime-image/
├── bin/
│   ├── java
│   └── app
├── conf/
├── legal/
├── lib/
│   ├── modules
│   ├── security/
│   └── ...
└── release
~~~

The exact filenames and number of files depend on the JDK, platform, and link options. On Windows, the Java launcher is typically **bin/java.exe**; application launchers may be generated as executable files or scripts in **bin**.

A few points to distinguish:

- A custom runtime image includes the Java runtime to run the application, but by default does not include the compiler or JDK development tools.
- The image contains only the selected modules along with resolved dependencies, not all JDK modules.
- The image contains native libraries and components dependent on the operating system/CPU architecture.
- The image is an artifact that can be distributed with the application; it does not automatically package all configuration files, data, external native libraries, or application-specific resources.

## 2. Input Requirements for jlink

**jlink** links modules that have an explicit module descriptor. Module sources can be:

- JDK modules in the **$JAVA_HOME/jmods** directory.
- Modular JARs containing **module-info.class**.
- Compiled exploded modules containing **module-info.class** in the module root directory.
- JMOD modules created for the application or libraries.

**Automatic modules cannot be linked directly with jlink.** If an application depends on a JAR library that only has **Automatic-Module-Name** or an automatic module name derived from the filename, you need to convert that library into an explicit module first. Adding Automatic-Module-Name only sets the automatic module name; it does not create an explicit descriptor.

You can check the JDK in use:

~~~bash
java --version
jlink --version
~~~

On Windows PowerShell:

~~~powershell
java.exe --version
jlink.exe --version
~~~

You should use **jlink** from a JDK compatible with the target Java version and verify that the input modules can be resolved on the module path. The JDK provides system modules in the **jmods** directory.

## 3. Two-Module Application Example

Suppose an application has a library module **com.acme.lib** and a main module **com.acme.app**.

Source structure:

~~~text
project/
└── src/
    ├── com.acme.lib/
    │   ├── module-info.java
    │   └── com/acme/lib/Message.java
    └── com.acme.app/
        ├── module-info.java
        └── com/acme/app/Main.java
~~~

Library module, file **src/com.acme.lib/module-info.java**:

~~~java
module com.acme.lib {
    exports com.acme.lib;
}
~~~

API class, file **src/com.acme.lib/com/acme/lib/Message.java**:

~~~java
package com.acme.lib;

public final class Message {
    private Message() {
    }

    public static String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Application module, file **src/com.acme.app/module-info.java**:

~~~java
module com.acme.app {
    requires com.acme.lib;
}
~~~

Main class, file **src/com.acme.app/com/acme/app/Main.java**:

~~~java
package com.acme.app;

import com.acme.lib.Message;

public final class Main {
    public static void main(String[] args) {
        String name = args.length == 0 ? "Java" : args[0];
        System.out.println(Message.greet(name));
    }
}
~~~

Module **com.acme.app** declares **requires com.acme.lib** because it uses the API exported from the library module. This is the dependency relationship that the module resolver will use when creating the runtime image.

## 4. Compiling Application Modules

From the **project** directory, compile both modules:

~~~bash
javac --module-source-path src -d mods -m com.acme.lib,com.acme.app
~~~

Explanation:

- **--module-source-path src** specifies the source directory tree organized by module.
- **-d mods** places the compiled output in the **mods** directory.
- **-m com.acme.lib,com.acme.app** instructs the compiler to compile the two modules.

After compiling, the structure looks like:

~~~text
mods/
├── com.acme.lib/
│   ├── module-info.class
│   └── com/acme/lib/Message.class
└── com.acme.app/
    ├── module-info.class
    └── com/acme/app/Main.class
~~~

The **mods/com.acme.lib** and **mods/com.acme.app** directories are exploded modules. They can be placed on the module path as input for jlink.

In real projects, modules can be packaged into modular JARs before linking. Whether using exploded modules or JARs, the essential condition is that the module descriptors and dependencies must be valid.

## 5. Analyzing Dependencies Before Linking

You should not guess modules. Analyze the static dependencies of the application and library modules.

Example:

~~~bash
jdeps --module-path mods --print-module-deps --module com.acme.app
~~~

The result lists the module dependencies identified by the tool from bytecode/module metadata. You can also use:

~~~bash
jdeps --module-path mods --list-deps --module com.acme.app
~~~

**jdeps** helps find static dependencies; classes loaded via reflection, dynamically generated class names, plugins, or external configurations might not be fully detected. Therefore, combine the results with module descriptors, runtime configuration, and actual testing.

When using **--add-modules com.acme.app**, jlink resolves this root module along with its required dependencies according to the module graph. Normally, you do not need to manually list each dependency already declared via **requires**. You can add multiple root modules if the application needs them:

~~~bash
--add-modules com.acme.app,com.acme.tools
~~~

If a module is only loaded dynamically or needs to be resolved even though it is not in the normal dependency graph, explicitly identify that module and add it as a root when appropriate.

## 6. Creating a Custom Runtime Image with jlink

JDK modules reside in **$JAVA_HOME/jmods**; compiled application modules reside in **mods**. Create the image:

Linux/macOS:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.app --output runtime-image
~~~

Windows PowerShell:

~~~powershell
jlink --module-path "$env:JAVA_HOME/jmods;mods" --add-modules com.acme.app --output runtime-image
~~~

Meaning of the options:

- **--module-path** specifies where jlink looks for modules. This example includes the JDK's JMOD directory and the application's exploded module directory.
- **--add-modules** specifies the root modules to include in the image.
- jlink resolves the dependencies of the root modules and links the required modules into the image.
- **--output** specifies the output image directory.

The output directory must not already exist or must be empty as required by the tool. Choose a dedicated build path for each image creation to avoid overwriting an artifact currently in use.

After the command completes, **runtime-image** is the custom runtime. This image can run the application module using the Java launcher located inside the image directory itself.

## 7. Linking Service Providers with --bind-services

An application may use ServiceLoader to find implementations of a service. For example, the application module declares:

~~~java
module com.acme.app {
    requires com.acme.spi;
    uses com.acme.spi.GreetingService;
}
~~~

The provider module declares:

~~~java
module com.acme.provider {
    requires com.acme.spi;
    provides com.acme.spi.GreetingService
        with com.acme.provider.EnglishGreetingService;
}
~~~

If you want jlink to find and link provider modules for services used by the modules being linked, add **--bind-services**:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.app --bind-services --output runtime-image
~~~

This option expands resolution to include matching provider modules along with their dependencies in the image. This is useful when providers are not directly declared by the app via **requires** but are discovered through service binding.

**--bind-services** does not replace service declarations:

- The consumer module still needs **uses**.
- The provider module still needs **provides ... with ...**.
- The provider must be present on the module path and satisfy service provider rules.
- The application must test the ServiceLoader flow on the image after linking.

If the application loads plugins on its own from an external directory or creates a custom module layer at runtime, design and test that mechanism separately. jlink does not automatically package arbitrary plugins located outside the module graph.

## 8. Creating a Custom Launcher with --launcher

You can instruct jlink to create a launcher named after the application instead of making users type the full **java --module ...** command.

Example:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.app --launcher app=com.acme.app/com.acme.app.Main --output runtime-image
~~~

Syntax:

~~~text
--launcher <launcher-name>=<module-name>/<main-class>
~~~

In the example:

- **app** is the name of the generated launcher.
- **com.acme.app** is the module containing the program.
- **com.acme.app.Main** is the main class.

After linking, run the launcher:

Linux/macOS:

~~~bash
./runtime-image/bin/app
~~~

Windows:

~~~powershell
.\runtime-image\bin\app.bat
~~~

The actual launcher name and format depend on the platform. Check the image's **bin** directory after linking.

You can create multiple launchers in the same image if the application has multiple entry points:

~~~bash
--launcher app=com.acme.app/com.acme.app.Main
--launcher admin=com.acme.app/com.acme.app.AdminMain
~~~

Each launcher points to its corresponding module and main class. The module containing the main class must be in the image.

## 9. Optimizing Runtime Image Size

jlink provides options to help reduce image size:

| Option | Effect |
|---|---|
| **--strip-debug** | Strips debug information from the linked modules |
| **--no-header-files** | Excludes native header files from the image |
| **--no-man-pages** | Excludes man pages from the image |
| **--compress=0** | No resource compression |
| **--compress=1** | Constant string sharing compression |
| **--compress=2** | ZIP compression for resources |

Combined example:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.app --strip-debug --no-header-files --no-man-pages --compress=2 --output runtime-image
~~~

Compressing and stripping debug info/headers/man pages can reduce distribution size. However, measure the image size and test startup time, performance, and application behavior in the target environment. Do not enable every option solely for the goal of creating the smallest possible image; keep components needed for operations, diagnostics, or distribution policies.

You can use **--limit-modules** to restrict the set of observable modules during resolution. This is an option to control the module universe, not a substitute for dependency analysis. If restricted too tightly, required modules may fail to resolve.

## 10. Running the Application from the Custom Runtime Image

If the image has a Java launcher, you can run the main module directly:

Linux/macOS:

~~~bash
./runtime-image/bin/java --module com.acme.app/com.acme.app.Main
~~~

Windows:

~~~powershell
.\runtime-image\bin\java.exe --module com.acme.app/com.acme.app.Main
~~~

Pass arguments to the program after the module/main class part:

~~~bash
./runtime-image/bin/java --module com.acme.app/com.acme.app.Main Lan
~~~

The application receives **Lan** in **String[] args**.

If you created a custom launcher:

~~~bash
./runtime-image/bin/app
~~~

Run using the executable inside the created image, not just the Java on the build machine's PATH. This confirms the application is using the exact set of packaged modules.

Custom runtime images typically do not include **javac**. Perform compilation and packaging with the JDK beforehand; the distributed image serves the runtime.

## 11. Verifying the Image After Creation

You can verify the image using the Java launcher inside the image itself:

~~~bash
./runtime-image/bin/java --version
./runtime-image/bin/java --list-modules
./runtime-image/bin/java --describe-module com.acme.app
~~~

These commands help confirm the Java version, the provided modules, and the descriptor of the application module.

Check the image structure:

~~~text
runtime-image/
├── bin/
├── conf/
├── legal/
├── lib/
└── release
~~~

If you need to verify JIMAGE contents, use the **jimage** tool from a compatible JDK to inspect the **runtime-image/lib/modules** file. jimage is not necessarily present in a minimal image.

Finally, run the application and its key workflows on the image. A module appearing in **--list-modules** is not enough to prove that all required classes/resources/native libraries are packaged or that the application does not need dynamically loaded modules.

## 12. Platform-Dependent Runtime Images

Runtime images contain native components and are therefore tied to the platform and architecture they were built for. An image built on Linux x64 is not an artifact that can run directly on Windows or macOS.

When releasing for multiple platforms:

- Build a separate image for each supported operating system and CPU architecture.
- Use a JDK/JMOD matching the target platform.
- Test on the target machine or an equivalent environment.
- Check native libraries, configuration files, execute permissions, and paths.
- Ensure the image is distributed with the required license/legal notices.

Do not simply rename an image directory and assume it is compatible with another platform. Treat each image as a separate platform artifact and manage versions/builds accordingly.

## 13. Common Errors and Troubleshooting

| Symptom | Common Cause | Solution |
|---|---|---|
| **jlink: Module ... not found** | Application module or dependency is not on the module path | Check **--module-path**, module name, and input JMODs/JARs |
| **Automatic module cannot be used with jlink** | Dependency is only an automatic module | Convert the library into an explicit module with **module-info.class** |
| **Module ... not found, required by ...** | Dependency in **requires** was not resolved | Add the required module to the module path and check descriptors |
| Invalid output directory | Output directory already exists and is not empty | Use a new or empty output directory as required by jlink |
| Provider missing from image | Provider module was not resolved or service binding was not used | Check **uses/provides**, module path, and consider **--bind-services** |
| Custom launcher fails to run | Wrong module/main class or module was not linked | Check **--launcher** and confirm the module is in the image |
| Works on JDK but fails on image | JDK has modules/tools that the custom image omitted | Test with Java inside the image and add truly needed dependencies |
| Image does not run on target machine | Image was built for a different OS/CPU or lacks native components | Build the image for the target platform and test on the corresponding environment |

Basic troubleshooting workflow:

1. Run **jdeps --print-module-deps** to inspect static dependencies.
2. Check descriptors and module names of dependencies.
3. Confirm every input module is an explicit module.
4. Select root modules with **--add-modules**.
5. Add **--bind-services** if service providers are needed.
6. Create the image into a clean output directory.
7. Run **--list-modules** and launch the application from the image.
8. Test features that use reflection, services, native libraries, or external configuration.

## 14. Key Takeaways

- **jlink** creates a custom runtime image from named modules with explicit descriptors.
- **--module-path** supplies JDK modules and application modules; **--add-modules** selects root modules.
- jlink automatically resolves dependencies in the module graph.
- Automatic modules cannot be linked directly.
- **--bind-services** helps include matching service providers in the image.
- **--launcher** creates a custom launcher for a module/main class.
- **--strip-debug**, **--no-header-files**, **--no-man-pages**, and **--compress** help optimize the image.
- An image is an OS/CPU-dependent artifact; it must be built and tested per target platform.
- Always test-run the application using the Java launcher inside the exact image to be distributed.

## References

- [The jlink Command — Java SE 21 Tool Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jlink.html)
- [The java Command — Java SE 21 Tool Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [The javac Command — Java SE 21 Tool Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
- [JEP 282 — jlink: The Java Linker](https://openjdk.org/jeps/282)
- [Java Platform Module System — OpenJDK Project Jigsaw](https://openjdk.org/projects/jigsaw/spec/)
