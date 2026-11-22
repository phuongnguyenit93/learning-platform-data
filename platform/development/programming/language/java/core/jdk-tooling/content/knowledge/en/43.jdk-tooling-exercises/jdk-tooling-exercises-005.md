# Creating a Runtime with jlink

jlink is a JDK tool used to assemble Java modules and their dependencies into a **custom runtime image**. This image contains the JVM along with the modules required by the application, allowing you to deploy Java programs without requiring users to install a full JDK on their machines.

The typical workflow includes: preparing the application according to the Java Platform Module System (JPMS), packaging it into a modular JAR, analyzing dependencies with jdeps, creating a runtime image with jlink, testing the standalone image, and using jpackage if an app bundle or installer is needed.

This exercise uses Java 17+ and a small modular application that uses the java.logging module. The commands have been tested on JDK 24.0.2; the core syntax also applies to JDK 17 and 21.

## 1. What Does jlink Produce?

A full JDK includes a compiler, debugger, documentation, profiling tools, and many modules that are unnecessary when only running an application. A runtime image created by jlink retains only the selected modules along with their transitive dependencies.

| Component | Full JDK | Custom Runtime Image |
|---|---|---|
| JVM and java command | Yes | Yes |
| JDK modules | Many modules | Only the linked modules |
| javac compiler | Yes | Usually not included |
| javadoc, jdeps, jlink tools | Yes | Not the purpose of a runtime image |
| Application modules | Depends on packaging | Can be linked directly |
| Application-specific launcher | Not generated automatically | Can be created with --launcher |

A runtime image is not a minimal JDK for continuing to compile source code. It is an execution environment tailored to a specific application.

### 1.1. Why Use a Custom Runtime?

- Reduce deployment size compared to shipping an entire JDK.
- Control which modules are present in the runtime.
- Package the application together with a tested Java runtime.
- Create a dedicated launcher so users do not have to type `java -m` manually.
- Reduce discrepancies caused by different Java versions or vendors installed on user machines.

Actual image size depends on modules, locale data, native libraries, and optimization options. There is no fixed size-reduction ratio for every application.

## 2. Prerequisites Before Using jlink

jlink operates on the module graph. The module path can contain modular JARs, JMODs, or exploded module directories. The application must have a valid module descriptor, and its dependencies must be resolvable into modules supported by the linker.

Preparation checklist:

1. A JDK with javac, jar, jdeps, jlink, and optionally jpackage.
2. A compiled application containing module-info.class.
3. Required dependency modules on the module path.
4. Exact module name and main class.
5. A build environment whose OS and CPU architecture match the target runtime to be distributed.

Verify that all tools belong to the intended JDK:

~~~sh
java -version
javac -version
jar --version
jdeps --version
jlink --version
jpackage --version
~~~

On Windows PowerShell, you can check the resolved paths:

~~~powershell
Get-Command java, javac, jar, jdeps, jlink, jpackage
$env:JAVA_HOME
~~~

On Linux/macOS:

~~~sh
command -v java javac jar jdeps jlink jpackage
echo "$JAVA_HOME"
~~~

If java and jlink come from two different JDKs, the linker may use a set of JDK modules that does not match the runtime you are testing. Set JAVA_HOME and PATH to point to the same JDK.

## 3. Creating a Modular Application for Practice

Create the project structure:

~~~text
jlink-demo/
├── src/
│   ├── module-info.java
│   └── com/
│       └── example/
│           └── app/
│               └── Main.java
└── build/
~~~

The application uses Java Logging to demonstrate a dependency outside java.base.

### 3.1. Declaring module-info.java

Create the file src/module-info.java:

~~~java
module com.example.app {
    requires java.logging;
}
~~~

Explanation:

- com.example.app is the module name.
- requires java.logging; declares that the application reads the java.logging module.
- java.base is implicitly read by every normal Java module; there is no need to write requires java.base;.

The module name does not have to match the JAR file name. However, it is best practice to follow the reverse-domain naming convention to avoid conflicts.

### 3.2. Writing the Main Class

Create the file src/com/example/app/Main.java:

~~~java
package com.example.app;

import java.util.logging.Logger;

public class Main {
    private static final Logger LOG =
        Logger.getLogger(Main.class.getName());

    public static void main(String[] args) {
        String target = args.length == 0
            ? "Java"
            : String.join(" ", args);

        LOG.info("Hello, " + target + "!");
    }
}
~~~

The program accepts command-line arguments. If run with the argument jlink, the log message will contain Hello, jlink!.

### 3.3. Compiling the Module

On Linux/macOS or Git Bash:

~~~sh
mkdir -p build/mods build/mlib

javac --release 17 \
  -d build/mods/com.example.app \
  src/module-info.java \
  src/com/example/app/Main.java
~~~

On Windows PowerShell, create the directories and compile with:

~~~powershell
New-Item -ItemType Directory -Force build/mods, build/mlib | Out-Null
javac --release 17 -d build/mods/com.example.app src/module-info.java src/com/example/app/Main.java
~~~

After compilation, the build/mods/com.example.app directory contains module-info.class and com/example/app/Main.class.

You can run the exploded module directly to verify before packaging the JAR:

~~~sh
java --module-path build/mods \
  --module com.example.app/com.example.app.Main
~~~

The output contains a log line with:

~~~text
INFO: Hello, Java!
~~~

The beginning of the log includes a timestamp and class name; the INFO line is the consistent message.

## 4. Packaging as a Modular JAR

Create the JAR in the module library directory:

~~~sh
jar --create \
  --file build/mlib/com.example.app.jar \
  --main-class com.example.app.Main \
  -C build/mods/com.example.app .
~~~

This command:

- Creates the file build/mlib/com.example.app.jar.
- Includes module-info.class and the application classes in the JAR.
- Declares the main class in the modular JAR metadata.

Inspect the descriptor:

~~~sh
jar --describe-module --file build/mlib/com.example.app.jar
~~~

The output will look similar to:

~~~text
com.example.app
requires java.base mandated
requires java.logging
contains com.example.app
main-class com.example.app.Main
~~~

This check confirms that the JAR has a valid module descriptor and the expected module name. If the command only displays an automatic module name, recheck the packaging step and the location of module-info.class.

You can run the JAR as a module:

~~~sh
java --module-path build/mlib \
  --module com.example.app/com.example.app.Main
~~~

## 5. Analyzing Module Dependencies with jdeps

jdeps analyzes dependencies at the package/class level and can print the list of JDK modules required by the linker. This is an important step to understand which modules the application uses.

Run:

~~~sh
jdeps --print-module-deps \
  --module-path build/mlib \
  --module com.example.app
~~~

For the sample application, the exact output is:

~~~text
java.base,java.logging
~~~

--print-module-deps prints a comma-separated list of modules; this output can be passed as input to jlink's --add-modules option.

You can view more detailed dependencies:

~~~sh
jdeps --list-deps \
  --module-path build/mlib \
  --module com.example.app
~~~

Check for missing dependencies:

~~~sh
jdeps --missing-deps \
  --module-path build/mlib \
  --module com.example.app
~~~

If the application uses multi-release JARs, specify the target release to analyze using --multi-release where appropriate.

### 5.1. jdeps Cannot See Every Dynamic Dependency

jdeps primarily analyzes bytecode and module descriptors. It may not fully detect classes loaded via reflection, class names read from configuration files, dynamically loaded plugins, undeclared service providers, or native libraries loaded via JNI.

Therefore:

- Review jdeps output alongside the module descriptor and application configuration.
- Add required modules explicitly with --add-modules when dependencies cannot be inferred from bytecode.
- Verify service providers with --bind-services when the application uses ServiceLoader.
- Run tests on the actual runtime image after linking.

Do not use --ignore-missing-deps to mask errors in release builds. If there are missing dependencies, identify the root cause and fix the module path or configuration before creating the image.

## 6. Creating a Runtime Image with jlink

Basic command:

~~~sh
jlink \
  --module-path build/mlib \
  --add-modules com.example.app \
  --launcher demo=com.example.app/com.example.app.Main \
  --strip-debug \
  --no-header-files \
  --no-man-pages \
  --output build/runtime
~~~

Option breakdown:

| Option | Effect |
|---|---|
| --module-path build/mlib | Where the linker locates application modules |
| --add-modules com.example.app | Selects the root module to link |
| --launcher demo=... | Creates a launcher named demo |
| --strip-debug | Strips debug information from the runtime image |
| --no-header-files | Excludes header files from the image |
| --no-man-pages | Excludes man pages from the image |
| --output build/runtime | Output directory for the runtime image |

When the module path only contains application modules and does not include java.base, jlink automatically adds the jmods directory of the running JDK. If you want to specify both paths explicitly, you must use the correct path separator for your OS: `:` on Linux/macOS and `;` on Windows.

--add-modules com.example.app instructs the linker to include the application module along with the dependencies declared in the module graph into the image. You do not need to list every transitive dependency manually in normal cases.

### 6.1. Adding Modules Outside the Module Graph

If the application loads modules via reflection or dynamic configuration, you may need to add modules explicitly:

~~~sh
jlink \
  --module-path build/mlib \
  --add-modules com.example.app,java.sql,jdk.crypto.ec \
  --output build/runtime
~~~

This is only a syntax example. Only add modules that are actually needed; adding unused modules increases the image size and expands the surface area that requires updates.

### 6.2. Binding Service Providers

For applications using ServiceLoader, the application's module descriptor can declare services. The example below assumes the CodecProvider interface belongs to the com.example.spi package and that this package is exported by the application module:

~~~java
module com.example.app {
    exports com.example.spi;
    uses com.example.spi.CodecProvider;
}
~~~

The provider implementation module must read the module containing the interface and declare the provider:

~~~java
module com.example.codec.json {
    requires com.example.app;
    provides com.example.spi.CodecProvider
        with com.example.codec.json.JsonCodecProvider;
}
~~~

When you need to include provider modules and their dependencies in the runtime image, use:

~~~sh
jlink \
  --module-path build/mlib \
  --add-modules com.example.app \
  --bind-services \
  --output build/runtime
~~~

--bind-services instructs the linker to link matching service provider modules and their dependencies. You still need to verify that modules declare `uses` and `provides` properly.

### 6.3. Keeping Required Locale Data

If the application requires locales beyond the default set, you can add jdk.localedata and restrict the included locales:

~~~sh
jlink \
  --module-path build/mlib \
  --add-modules com.example.app,jdk.localedata \
  --include-locales=vi,en \
  --output build/runtime
~~~

--include-locales requires the jdk.localedata module. Verify locale formatting and the application's actual requirements before stripping out locale data.

### 6.4. Size Optimization Options

The options --strip-debug, --no-header-files, and --no-man-pages are generally suitable for production runtimes. Compressing resources with the compress plugin can reduce size but adds decompression overhead, and plugin syntax changes across JDK releases.

List available plugins on the current JDK:

~~~sh
jlink --list-plugins
~~~

Only add compression options after checking the documentation for your exact JDK version and measuring image size and startup time on the real application.

## 7. Verifying the Created Runtime Image

List the modules inside the image:

~~~sh
build/runtime/bin/java --list-modules
~~~

For the sample application linked with JDK 24.0.2, the list contains these modules:

~~~text
com.example.app
java.base@24.0.2
java.logging@24.0.2
~~~

On another machine, the JDK module version suffix reflects the JDK used for linking.

Check the runtime version:

~~~sh
build/runtime/bin/java --version
~~~

Run the module using the Java executable inside the image:

~~~sh
build/runtime/bin/java \
  --module com.example.app/com.example.app.Main \
  from-runtime
~~~

Test the launcher created by jlink:

~~~sh
./build/runtime/bin/demo launcher-test
~~~

On Windows PowerShell:

~~~powershell
.\build\runtime\bin\demo.bat launcher-test
~~~

The log output must contain:

~~~text
INFO: Hello, launcher-test!
~~~

Always run the java binary inside the image. If you accidentally invoke Java from the developer machine's PATH, the test might pass even when the runtime image is missing modules.

## 8. Packaging the Application with jpackage

jlink creates a runtime image. jpackage uses the application and the runtime image to build a platform-specific application image or installer.

Create an application image from the newly built runtime:

~~~sh
jpackage \
  --type app-image \
  --name JlinkDemo \
  --module-path build/mlib \
  --module com.example.app/com.example.app.Main \
  --runtime-image build/runtime \
  --dest build/package
~~~

--runtime-image tells jpackage to use a pre-built image. If this option is omitted, jpackage invokes jlink internally to create a runtime based on the provided modules and options.

The application image contains a launcher and a runtime directory inside. The exact layout depends on the operating system:

- Windows: contains a .exe launcher file and directories for the application/runtime.
- Linux: contains a launcher in the bin directory and the runtime in the application directory.
- macOS: contains a .app bundle, with the launcher in Contents/MacOS and the runtime inside the bundle.

Test the launcher inside the application image before building an installer. Windows example:

~~~powershell
.\build\package\JlinkDemo\JlinkDemo.exe packaged
~~~

On Linux, the launcher is typically located under build/package/JlinkDemo/bin/; on macOS, the launcher is inside build/package/JlinkDemo.app/Contents/MacOS/.

### 8.1. Creating Platform-Specific Installers

Commonly used package types:

| Operating System | Package Type |
|---|---|
| Windows | exe, msi |
| macOS | dmg, pkg |
| Linux | deb, rpm |

Example of creating a Windows installer:

~~~powershell
jpackage --type exe --name JlinkDemo --module-path build/mlib --module com.example.app/com.example.app.Main --runtime-image build/runtime --dest build/installer
~~~

To create macOS or Linux installers, run jpackage on a machine/runner of the target operating system and select the corresponding package type. jpackage does not support cross-platform packaging; distributing for multiple OSes requires building on each platform.

On Windows, creating exe or msi packages may require the WiX Toolset. On macOS, signing the app or customizing certain resources requires Xcode Command Line Tools and an appropriate signing/notarization workflow.

### 8.2. Packaging Non-Modular Applications with jpackage

Legacy applications using classpath JARs can be packaged with jpackage using --input, --main-jar, and --main-class:

~~~sh
jpackage \
  --type app-image \
  --name LegacyApp \
  --input build/dist \
  --main-jar legacy-app.jar \
  --main-class com.example.Main \
  --dest build/package
~~~

The build/dist directory must contain the JAR and any files required by the application. For non-modular classpath applications, jpackage builds a runtime based on the default set of modules that the Java launcher normally provides to unnamed-module applications; you can add modules or the --bind-services option when needed.

If you want to manage the runtime directly with jlink, convert the application and its required dependencies into explicit modules. A standard classpath JAR does not automatically become a modular JAR just by being placed on the module path.

## 9. Limitations to Understand Before Releasing

### 9.1. Dependencies Without a Module Descriptor

A modular JAR has a module-info.class at its root or a valid descriptor in a multi-release JAR. Legacy classpath JARs without a descriptor do not provide an explicit module graph to jlink.

If a dependency is only available as a legacy JAR:

- Prefer a library version that includes an explicit module descriptor.
- You can use jdeps --generate-module-info to generate a suggested descriptor, then review and test it thoroughly.
- If keeping a classpath application, consider packaging with jpackage in non-modular mode.
- Do not rely on automatic module names assuming the linker can link them as explicit modules.

### 9.2. Reflection and Dynamic Class Loading

Frameworks may load classes by string name, scan packages, read configuration files, or load plugins at runtime. Static dependency analysis cannot always infer these classes.

Test all real execution paths: application startup, configuration loading, establishing connections, running plugins, serialization/deserialization, opening files, and invoking optional features. If a module is missing, add it with --add-modules or adjust the module descriptor.

### 9.3. JNI and Native Libraries

JNI/JNA libraries require binaries matching the target OS and architecture. A Windows x64 runtime image cannot run as-is on Linux ARM64. Verify native libraries, DLLs/shared libraries, search paths, and dynamic dependencies on the target machine.

### 9.4. Runtime Images Must Be Kept Updated

jlink does not automatically update an image when the JDK receives security patches. When upgrading the JDK, rebuild the runtime image, run regression tests, and re-release the application. Record the JDK vendor/version, OS/architecture, module list, and artifact checksums for release traceability.

## 10. Repeatable Build Workflow

A deployment pipeline should execute the following steps in order:

1. Pin the JDK vendor and version for the build job.
2. Compile the application with the selected target release.
3. Create the modular JAR and inspect the module descriptor.
4. Run jdeps --print-module-deps and jdeps --missing-deps.
5. Create the runtime image with jlink and the reviewed modules.
6. Verify java --list-modules inside the image.
7. Run the launcher and test features that rely on reflection, service loading, locales, or JNI.
8. Create the application image with jpackage --type app-image.
9. Test the app image on a clean machine of the target OS.
10. Create the installer, sign, and notarize if required by your distribution process.
11. Store the JDK version, module list, checksums, and build provenance alongside the artifact.

Do not use ALL-MODULE-PATH or include all JDK modules just to make errors disappear. Identify the modules that are genuinely required and add them intentionally.

## 11. Troubleshooting

| Symptom | Common Cause | Resolution |
|---|---|---|
| Error: module not found | Missing JAR/module on module path or wrong module name | Use jar --describe-module and check --module-path |
| jlink cannot find java.base | JDK modules not found by the linker | Check JAVA_HOME, the active JDK, and the jmods directory |
| Missing module after linking | Dependency loaded dynamically or undeclared | Check jdeps, module descriptor, and add required modules |
| JAR runs with java -jar but linker fails | JAR/dependency not built as explicit modules | Modularize dependencies or use jpackage in classpath mode |
| Service provider does not appear | Service not declared or provider not bound | Check uses/provides and --bind-services |
| Desired locale unavailable | Missing jdk.localedata or locale data | Add the module and use --include-locales |
| JNI reports library cannot be loaded | Wrong OS/architecture or missing native dependency | Build for the target platform and check native library path |
| Launcher works on system Java but image fails | Test accidentally invoked java from PATH | Run the executable/launcher located inside the runtime image |
| Installer does not run on another OS | Package is in a platform-native format | Build the package on each target OS |
| Runtime image is still too large | Too many modules or excessive locale data included | Inspect --list-modules, remove unneeded modules, and re-measure |

## 12. Pre-Distribution Checklist

- [ ] Used a JDK that includes jlink and jpackage.
- [ ] java, javac, jdeps, and jlink come from the same JDK.
- [ ] The application has an appropriate module descriptor.
- [ ] Verified the module name with jar --describe-module.
- [ ] Inspected dependencies with jdeps --print-module-deps.
- [ ] Resolved missing dependencies with jdeps --missing-deps.
- [ ] Created the runtime image with the correct root modules.
- [ ] Verified the module list inside the image.
- [ ] Tested the launcher generated by jlink.
- [ ] Tested reflection, ServiceLoader, locales, and native libraries if used by the application.
- [ ] Built and tested the application image with jpackage.
- [ ] Built separate packages for each target OS/architecture.
- [ ] Established a process to rebuild the runtime when upgrading the JDK or applying security updates.

## References

- [Oracle JDK 21 — The jlink Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jlink.html)
- [Oracle JDK 26 — The jdeps Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html)
- [Oracle JDK 21 — The jar Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jar.html)
- [Oracle JDK 21 — The jpackage Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jpackage.html)
- [Oracle JDK 21 — Packaging Overview and Runtime Requirements](https://docs.oracle.com/en/java/javase/21/jpackage/packaging-overview.html)
- [Oracle Java SE 21 — ModuleFinder API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/ModuleFinder.html)