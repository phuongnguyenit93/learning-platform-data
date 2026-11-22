# When to Use JMOD in Java

JMOD is a JDK archive format designed for modules at development and runtime-linking stages. The key factor in deciding whether to use JMOD is your packaging goal: JMOD is appropriate when you need to supply input to `jlink` or package additional components such as native libraries, commands, configuration files, headers, and legal notices. For typical Java applications consisting only of classes and resources, a modular JAR is usually more suitable for running and distributing.

This article explains when to use JMOD, when it is unnecessary, how to create a JMOD for a Java 17+ module, how to pass a JMOD into `jlink`, and how to choose the right format for each release stage.

## 1. What Need Does JMOD Address?

A JAR typically contains class files, resources, and metadata such as a manifest or module descriptor. It is the standard format for running classpath applications or named modules.

JMOD extends module packaging. Beyond classes and resources, a JMOD can contain additional content groups:

| Group | Packageable Content | When It Is Useful |
|---|---|---|
| `classes` | Module class files and resources | Any module that needs linking |
| `bin` | Commands or executables bundled with the module | Modules that provide executable tools |
| `conf` | Configuration files | Runtimes requiring configuration distributed with the module |
| `include` | Headers for native integration | Modules with native APIs or C/C++ integration |
| `legal` | Licenses and copyright notices | Distributing components with legal obligations |
| `lib` | Native libraries and supporting libraries | Modules that depend on native code |
| `man` | Command manual pages | Distributing documentation for bundled commands |

Not every JMOD contains all of these groups. A JMOD that only holds Java classes may only have a `classes` directory; the other groups appear when the packaging process provides them.

JMOD is useful when you need to feed module components into the runtime image creation process with `jlink`. It allows the toolchain to process module contents during the linking phase, including components beyond Java classes.

## 2. When to Use JMOD

### 2.1. Creating a Custom Runtime with jlink

This is the most common reason to use JMOD in modular application development. `jlink` takes modules from the module path and links them along with their required dependencies into a runtime image.

JMOD is one of the input formats that `jlink` can consume. If you build your own module and want it included in a runtime image, you can package the module as a JMOD and pass that archive to `jlink`.

General workflow:

1. Write the module and declare `module-info.java`.
2. Compile the module into class files.
3. Create a JMOD from the compiled class directory.
4. Run `jlink` with your JMOD and the JDK's JMODs.
5. Test the generated runtime image on the target platform.

This approach works well when you want to distribute an application alongside a minimal Java runtime, reducing the requirement for users to install a separate JDK/JRE.

### 2.2. When a Module Needs to Bundle Native Libraries or Non-Java Components

If a module has native libraries, executables, headers, configuration files, or legal notices that must be integrated into the runtime image, JMOD provides dedicated packaging sections for them.

For example, a module may require:

- Native libraries loaded via JNI or an appropriate native access mechanism.
- Executables that support the module.
- Configuration files that must be present in the runtime image.
- Headers used during native builds or integration.
- Legal notices that must be distributed with the module.

Native components are tied to a specific operating system and CPU architecture. When packaging native content, you must build and test artifacts for the target platform. You cannot take a Windows native library and expect a Linux runtime image to use it.

`jmod create` provides options such as `--libs`, `--cmds`, `--config`, `--header-files`, `--legal-notices`, and `--man-pages` to add each content group. Only include the components that the module actually needs.

### 2.3. Developing Modules or Toolchains for the JDK

JMOD is part of the JDK tooling ecosystem. System modules in the JDK's `jmods` directory are stored in JMOD format so linking tools can consume them.

When building custom modules for runtime images, developing platform components, or working with JDK-level module integration workflows, JMOD is the appropriate format for the packaging and linking stage.

For ordinary application projects, there is no need to convert every module to JMOD simply because the project uses JPMS. Choose the format based on the next step in your workflow.

### 2.4. Packaging a Module with Linking Metadata

JMOD can record module version, main class, and target platform metadata. This information is useful in build and runtime-linking pipelines.

Example:

~~~powershell
jmod create --class-path mods/com.example.app --main-class com.example.app.Main --module-version 1.0.0 build/com.example.app.jmod
~~~

In this command:

- `--class-path` points to the directory containing the module's class files and resources.
- `--main-class` records the module's main class.
- `--module-version` records the module version.
- The final argument is the path to the JMOD to be created.

This metadata supports tooling and packaging workflows. It does not turn a JMOD into a file that can be run directly with `java -jar`.

## 3. When JMOD Is Not Needed

### 3.1. When You Only Need to Run or Distribute a Java Application

If an application consists solely of class files and resources, a modular JAR is usually the simpler choice. The Java launcher can run a modular JAR on the module path:

~~~powershell
java --module-path app-modules --module com.example.app/com.example.app.Main
~~~

If the JAR includes main class metadata, you can omit the `/main-class` part:

~~~powershell
java --module-path app-modules --module com.example.app
~~~

For traditional classpath applications, an executable JAR with a `Main-Class` manifest attribute remains the familiar format:

~~~powershell
java -jar app.jar
~~~

JMOD is not designed to replace modular JARs in normal application execution workflows.

### 3.2. When Not Creating a Custom Runtime

If users already have a suitable Java runtime and you only need to distribute a Java module, a modular JAR is generally sufficient. There is no need to add `jmod create` and `jlink` steps if there is no requirement to package a runtime or special components.

### 3.3. When Trying to Run a JMOD Directly with the Java Launcher

JMOD is not a runtime archive format. Do not use the following commands to run an application:

~~~powershell
java -jar app.jmod
java --module-path build/app.jmod --module com.example.app
~~~

To run a named module, use a modular JAR or an exploded module on the module path. To use a JMOD, pass it into a runtime-linking workflow, typically `jlink`.

### 3.4. When jpackage Already Receives Suitable Input

`jpackage` can package applications from JARs/modules and produce an application image or installer. If a custom runtime is needed, you can first create a runtime image with `jlink`, then pass that runtime image to `jpackage` via `--runtime-image`.

JMOD can participate at the `jlink` step; `jpackage` consumes the generated runtime image rather than using a JMOD as a runnable application file.

## 4. Comparing JMOD, Modular JAR, and Runtime Image

| Format | Primary Role | Directly Runnable with Java Launcher? | Used with jlink? |
|---|---|---|---|
| Regular JAR | Packages classes/resources for the classpath | Yes, with appropriate launch configuration | Not the standard choice for explicit module linking |
| Modular JAR | Distributes a named module for runtime | Yes, on the module path | Can be used as module path input when appropriate |
| JMOD | Packages a module for development/linking, can contain native and system content | No | Yes |
| Runtime image | Linked Java runtime for an application or set of modules | Yes, via bin/java or a launcher | It is the output of jlink, not a JMOD input |

Deciding by goal:

- Need to ship a module for users to run on an existing Java installation: choose a modular JAR.
- Need to ship a simple classpath application: choose an executable JAR.
- Need to create a dedicated Java runtime with selected modules: use `jlink`; JMOD is a suitable input format.
- Need to package native libraries, commands, configuration, or headers into a module for linking: consider JMOD.
- Need to create an installer: use `jpackage`, optionally passing a runtime image created by `jlink`.

## 5. Practical Example: From a Java Module to a JMOD

The following example uses JDK 17 or later and creates a JMOD that can be passed to `jlink`.

Project structure:

~~~text
project/
├── src/
│   ├── module-info.java
│   └── com/
│       └── example/
│           └── app/
│               └── Main.java
├── mods/
└── build/
~~~

Contents of `src/module-info.java`:

~~~java
module com.example.app {
    exports com.example.app;
}
~~~

Contents of `src/com/example/app/Main.java`:

~~~java
package com.example.app;

public class Main {
    public static void main(String[] args) {
        String target = args.length == 0 ? "JMOD" : String.join(" ", args);
        System.out.println("Hello, " + target + "!");
    }
}
~~~

From the `project` directory, create the output directories and compile the module:

~~~powershell
New-Item -ItemType Directory -Force -Path mods/com.example.app, build | Out-Null
javac -d mods/com.example.app src/module-info.java src/com/example/app/Main.java
~~~

Before creating the JMOD, you can run the compiled module directly from the module directory:

~~~powershell
java --module-path mods --module com.example.app/com.example.app.Main "modular app"
~~~

Output:

~~~text
Hello, modular app!
~~~

Create the JMOD:

~~~powershell
jmod create --class-path mods/com.example.app --main-class com.example.app.Main --module-version 1.0.0 build/com.example.app.jmod
~~~

Inspect the archive and metadata:

~~~powershell
jmod list build/com.example.app.jmod
jmod describe build/com.example.app.jmod
~~~

The entry listing for this example will include core entries similar to:

~~~text
classes/module-info.class
classes/com/example/app/Main.class
~~~

The module description can show the module name, version, exported packages, required modules, and main class. Exact output depends on the JDK and module metadata.

## 6. Using JMOD to Create a Runtime Image with jlink

After creating `build/com.example.app.jmod`, you can use `jlink` to link the application module with the required JDK platform modules.

On Windows PowerShell:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;build" --add-modules com.example.app --output runtime
~~~

On Linux/macOS:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:build" --add-modules com.example.app --output runtime
~~~

Explanation:

- `--module-path` specifies the JDK system JMOD directory and the directory containing your application JMOD.
- `--add-modules` selects the root module to link.
- `jlink` automatically resolves the required module dependencies.
- `--output` specifies the runtime image directory to create.

Run the application using the newly created runtime.

PowerShell on Windows:

~~~powershell
.\runtime\bin\java.exe -m com.example.app/com.example.app.Main "custom runtime"
~~~

Linux/macOS:

~~~bash
./runtime/bin/java -m com.example.app/com.example.app.Main "custom runtime"
~~~

Output:

~~~text
Hello, custom runtime!
~~~

The runtime image contains the Java launcher and the linked modules. Users can run the application with this runtime without installing a separate full JDK, provided the runtime image was built for the corresponding platform and includes all required modules, resources, and native components.

## 7. Packaging Non-Class Components with JMOD

When a module needs more than classes and resources, `jmod create` lets you add the corresponding directories.

General example:

~~~powershell
jmod create --class-path mods/com.example.app --libs native-libs --config config --legal-notices legal --main-class com.example.app.Main --module-version 1.0.0 build/com.example.app.jmod
~~~

Additional options:

- `--libs`: adds native libraries to the `lib` group.
- `--cmds`: adds executables or commands to the `bin` group.
- `--config`: adds configuration files to the `conf` group.
- `--header-files`: adds headers to the `include` group.
- `--legal-notices`: adds legal notices to the `legal` group.
- `--man-pages`: adds manual pages to the `man` group.
- `--target-platform`: records the target platform for the JMOD when contents are platform-dependent.

Input paths must exist and contain the expected content. Do not add empty directories or unrelated files just to populate the archive.

If a module contains native libraries, you must ensure the binaries match the platform and architecture on which the runtime image will run. `--target-platform` records platform metadata, but it does not convert a native binary from one platform to another.

## 8. JMOD in a jpackage Workflow

When the final goal is to produce an installer, the workflow may include these steps:

1. Create a JMOD from the application module.
2. Use `jlink` to create a runtime image containing the application module and its dependencies.
3. Use `jpackage` to package the application with the runtime image into an OS-appropriate application image or installer.

Example `jpackage` command once the runtime image and application are properly prepared:

~~~powershell
jpackage --type app-image --name ExampleApp --module-path app-modules --module com.example.app/com.example.app.Main --runtime-image runtime --dest packages
~~~

In this example, `--runtime-image` takes the previously created runtime image. JMOD was already used at the `jlink` step; do not pass a JMOD to `jpackage` as if it were the main JAR.

For simple classpath applications or modular JARs, you can let `jpackage` generate the runtime if that fits your input configuration. Only add the JMOD/`jlink` step when there is a clear reason, such as a custom runtime or special module components.

## 9. Limitations to Keep in Mind

### 9.1. JMOD Is Not a Directly Runnable Format

JMOD is intended for the development and linking stages. The Java launcher runs classes, JARs, or modules on the module path; it does not treat a JMOD like a standard modular JAR.

### 9.2. JMOD Can Be Platform-Specific

If an archive contains native libraries, executables, or OS-dependent components, the artifact must be built and tested for the target platform. Do not share a JMOD containing native content as a platform-independent artifact if its contents are not truly portable.

### 9.3. Requires an Appropriate JDK

The `jmod` and `jlink` tools ship with the JDK. A stripped-down runtime image distributed to end users may not include these tools. Use an appropriate JDK build to create JMODs and link runtimes.

### 9.4. Dependencies Must Be Declared and Available

JMOD does not automatically resolve missing dependencies. The module descriptor must declare the modules the application requires, and those modules must be present on the module path when `jlink` performs linking.

### 9.5. Test the Runtime Image After Linking

A successful `jlink` build does not guarantee that every application feature will work at runtime. You should test resources, service providers, reflection, native libraries, configuration, and dynamically loaded modules. Dependencies not fully represented in the module graph may need to be added explicitly.

## 10. Common Errors When Choosing or Using JMOD

| Symptom | Common Cause | Resolution |
|---|---|---|
| Trying to run a JMOD with `java -jar` | Confusing JMOD with an executable JAR | Use a modular JAR or run the runtime image generated from the JMOD |
| `jlink` cannot find the module | Module path does not include the JMOD or module name is wrong | Check `--module-path`, `jmod describe`, and the name in the module descriptor |
| `jlink` reports missing dependencies | Required module is not on the module path | Add the dependent JMOD/JAR and verify `requires` |
| JMOD is missing expected classes | `--class-path` points to the wrong directory or module is not fully compiled | Check `javac` output and inspect with `jmod list` |
| Runtime image is missing native libraries | Native libraries were not added to the JMOD or wrong packaging group | Check `--libs`, `lib/` entries, and native platform |
| Runtime image builds but application fails at runtime | Missing dynamically loaded modules, resources, or service providers | Test actual features; review module graph and `jlink` configuration |
| `jmod` command is not recognized | Using a runtime instead of a JDK, or incorrect PATH | Use `jmod` from the JDK's `bin` directory |
| Native JMOD fails on another machine | Binaries were built for a different OS/CPU | Build and test native components for the target platform |

## 11. Quick Decision Flow

Answer these questions in order:

1. Does the application only need to run on an already-installed Java runtime and contain only classes/resources? Use a JAR—typically a modular JAR if the application uses JPMS.
2. Do you need to ship a dedicated Java runtime containing only the required modules? Use `jlink`; you can supply modules via JMOD or an appropriate modular JAR.
3. Does the module need to package native libraries, commands, configs, headers, or legal notices for linking? Use JMOD.
4. Do you need an OS installer or application image? Use `jpackage`, passing your runtime image if you created a custom runtime.
5. Is there native content? Verify the target OS/architecture and test on the target environment.

You do not need JMOD just because a project has `module-info.java`. Modular JARs already support running named modules. JMOD becomes valuable when your workflow needs an archive for runtime linking or needs to package module components beyond classes and resources.

## 12. Checklist Before Choosing JMOD

- [ ] Identified whether the goal is running a JAR, creating a runtime image, or building an installer.
- [ ] Determined whether `jlink` is needed to create a custom runtime.
- [ ] Determined whether the module requires native libraries, commands, configs, headers, or legal notices.
- [ ] If only distributing a Java module for an existing runtime, considered using a modular JAR.
- [ ] If using JMOD, prepared the module descriptor and dependencies.
- [ ] Created and inspected the JMOD with `jmod list`/`jmod describe`.
- [ ] If using `jlink`, ensured the module path contains the application JMOD and required JDK modules.
- [ ] If native content is included, verified the target OS/architecture.
- [ ] Tested the runtime image on the corresponding target environment.
- [ ] If an installer is needed, selected the appropriate package type via `jpackage`.

Choose JMOD when you need to package a module for the runtime-linking step, especially with `jlink`, or when a module must carry native libraries, commands, configuration files, headers, and legal notices. For ordinary Java applications, a modular JAR remains the convenient format for running and distributing. Start from how the application will be executed and what components must ship with it, then select JAR, JMOD, runtime image, or installer for the right stage.
