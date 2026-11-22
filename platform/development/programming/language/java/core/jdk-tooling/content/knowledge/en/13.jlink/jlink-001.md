# The jlink Command

`jlink` is a tool in the JDK used to **link Java modules and create a custom runtime image**. A runtime image contains the JVM along with the set of modules needed to run an application. As a result, the application can be distributed with a runtime smaller than the full JDK, containing components selected based on the application's dependencies.

General syntax:

```text
jlink --module-path <module-path>
      --add-modules <module>[,<module>...]
      --output <directory>
      [other-options]
```

The three most important parts:

- `--module-path`: where to find the input modules.
- `--add-modules`: the root modules to include in the runtime image.
- `--output`: the directory that receives the generated runtime image.

`jlink` works with linkable Java modules, such as modules in JMODs, modular JARs, or exploded modules. It does not package an arbitrary classpath application into a runtime image simply by passing the name of a regular JAR file.

## 1. What is a runtime image?

An installed JDK on a machine typically contains many development tools such as `javac`, `javadoc`, `jdb`, `jar`, `jlink`, and modules used for building. When deployed, an application may only need the JVM and a subset of Java SE modules.

`jlink` reads the module dependency graph and creates an image containing the required components. Example structure of an image:

```text
app-image/
├── bin/
│   ├── java
│   └── app
├── conf/
├── include/
├── legal/
├── lib/
│   └── modules
└── release
```

The actual directories and files depend on the operating system, the JDK, and the linked modules. If a launcher is declared using `--launcher`, the image will also include the launcher command in the `bin` directory.

A runtime image is usually smaller than the full JDK because it does not include all development tools and unrequested modules. It still contains the runtime needed to run the application; it is not a single native executable file.

## 2. Module resolution mechanism during linking

`jlink` does not simply copy every JAR in a directory. It resolves the module graph based on module declarations and input options.

General process:

1. Read the module path and find observable modules.
2. Identify the root modules selected via `--add-modules`.
3. Resolve `requires` relationships and transitive dependencies.
4. Identify service providers if service binding is enabled.
5. Verify whether the resolved modules can be linked.
6. Write the runtime image and apply the selected plugins.

Example module descriptor:

```java
module com.example.app {
    requires java.logging;
}
```

If `com.example.app` is selected, the `java.logging` module is also included because it is a required dependency. Other needed modules are resolved according to their dependency relationships.

Dependencies loaded via reflection, class names configured in files, or plugin mechanisms may not be fully represented in `requires`. When an application uses such modules, add the appropriate root modules with `--add-modules` and test the actual image.

## 3. Preparing a modular application

Example of creating a modular application named `com.example.app`:

```text
project/
└── src/
    └── com.example.app/
        ├── module-info.java
        └── com/
            └── example/
                └── app/
                    └── Main.java
```

Contents of `module-info.java`:

```java
module com.example.app {
}
```

Contents of `Main.java`:

```java
package com.example.app;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from custom runtime");
    }
}
```

Compile the module into the `mods` directory:

```sh
mkdir -p mods/com.example.app
javac -d mods/com.example.app \
  src/com.example.app/module-info.java \
  src/com.example.app/com/example/app/Main.java
```

After compiling:

```text
mods/
└── com.example.app/
    ├── module-info.class
    └── com/
        └── example/
            └── app/
                └── Main.class
```

The `mods/com.example.app` directory is an exploded module: a module laid out as a directory structure rather than packaged in a JAR/JMOD.

Inspect the module descriptor:

```sh
jar --describe-module --file mods/com.example.app
```

For an exploded module, you can use an appropriate tool to inspect the descriptor or run `jlink` directly on the module path. The module name must match the declaration in `module-info.java`.

## 4. Creating a basic runtime image

Assume the `JAVA_HOME` environment variable points to the JDK being used. The `$JAVA_HOME/jmods` directory contains the JMODs of that JDK; the `mods` directory contains the newly compiled exploded module.

On Linux/macOS:

```sh
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --output app-image
```

On Windows PowerShell:

```powershell
jlink --module-path "$env:JAVA_HOME/jmods;mods" --add-modules com.example.app --output app-image
```

The module path separator character differs by operating system:

| Operating System | Separator |
|---|---|
| Windows | Semicolon `;` |
| Linux/macOS | Colon `:` |

The output directory must not already exist or must be empty. If `app-image` already has contents, choose a new path or clean the build directory properly before running again.

After successful creation, the image contains the required runtime modules. Run the program using Java inside the image:

```sh
./app-image/bin/java -m com.example.app/com.example.app.Main
```

Output:

```text
Hello from custom runtime
```

On Windows, run:

```powershell
.\app-image\bin\java.exe -m com.example.app/com.example.app.Main
```

This image can run the application without using the `java` command from the JDK installed on the machine, provided the image was built for the right platform and the required dependencies were included.

## 5. Creating a custom launcher with --launcher

If you want users to run the application using a short command, you can create a launcher with `--launcher`:

```sh
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --launcher app=com.example.app/com.example.app.Main \
  --output app-image
```

Syntax:

```text
--launcher <command>=<module>[/<main-class>]
```

- `command`: name of the launcher created in the `bin` directory.
- `module`: name of the module containing the entry point.
- `main-class`: fully qualified class name containing `public static void main(String[] args)`.

If the module already declares a main class in its module descriptor via the `main-class` attribute, the `/<main-class>` part can be omitted according to the supported syntax.

After creating the image, run the launcher:

```sh
./app-image/bin/app
```

Output:

```text
Hello from custom runtime
```

A launcher is a command that starts a Java module using the runtime bundled with the image. It differs from a native command provided by the application itself and packaged in a JMOD using `jmod --cmds`.

## 6. Important jlink options

| Option | Purpose |
|---|---|
| `--module-path` | Specifies where to find input modules |
| `--add-modules` | Selects root modules to link; accepts a comma-separated list |
| `--bind-services` | Finds and links service providers along with their dependencies |
| `--limit-modules` | Limits the set of observable modules during resolution |
| `--output` | Specifies the output runtime image directory |
| `--launcher` | Creates a launcher command for a module/main class |
| `--compress=0` | No resource compression |
| `--compress=1` | Constant string sharing in resources |
| `--compress=2` | ZIP compression for resources |
| `--strip-debug` | Strips debug information from linked modules |
| `--no-header-files` | Excludes native header files from the image |
| `--no-man-pages` | Excludes man pages from the image |
| `--strip-native-commands` | Strips native commands from the image |
| `--include-locales` | Limits the locale data included in the image |
| `--save-opts` | Saves link options for reuse |

The list of options and plugins may vary by JDK version. View the help of the tool you are using:

```sh
jlink --help
jlink --list-plugins
```

Do not enable every plugin just to reduce size. Identify the application's requirements, apply options one by one, and test the runtime image.

## 7. Selecting root modules with --add-modules

`--add-modules` specifies the root modules to include in the image. For example:

```sh
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app,java.sql \
  --output app-image
```

The command above selects both `com.example.app` and `java.sql` as root modules. Required modules referenced via `requires` will be resolved further.

You can use:

```text
--add-modules ALL-MODULE-PATH
```

to add all observable modules on the module path. This is convenient for experimentation, but it can produce a significantly larger image and negate the benefit of minimal module selection.

If the application loads modules by name at runtime or uses a plugin framework, identify the required modules and add them explicitly. Only add modules justified by the application configuration and testing.

## 8. Service binding with --bind-services

Java `ServiceLoader` allows a module to use a service interface and locate implementations provided by other modules.

Example module using a service:

```java
module com.example.app {
    uses com.example.spi.ReportService;
}
```

Module providing an implementation:

```java
module com.example.report.csv {
    requires com.example.app;
    provides com.example.spi.ReportService
        with com.example.report.csv.CsvReportService;
}
```

When creating a runtime image, `--bind-services` instructs the linker to find providers of services used by the selected modules, then link those providers along with their required dependencies.

```sh
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --bind-services \
  --output app-image
```

Service binding can cause the image to include additional provider modules. This is necessary if the application relies on `ServiceLoader` to discover implementations, but should not be enabled mechanically if service providers are not needed.

## 9. Reducing runtime image size

Plugins can be combined to reduce size:

```sh
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --strip-debug \
  --no-header-files \
  --no-man-pages \
  --compress=2 \
  --output app-image
```

The options above:

- `--strip-debug`: strips debug information from linked modules.
- `--no-header-files`: excludes native header files unnecessary for normal runtime execution.
- `--no-man-pages`: excludes manual pages.
- `--compress=2`: compresses resources using ZIP.

Compression can reduce image size, but it may affect resource read time at runtime. Measure both size and performance on the actual application.

Do not strip native commands if the application or deployment process needs them. Similarly, do not strip debug metadata if it is needed for production troubleshooting or tools that depend on that information.

## 10. Limiting locale data

The JDK has the `jdk.localedata` module containing additional locale data. If the image needs to support a specific set of locales, you can select them using the `--include-locales` plugin.

Example:

```sh
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app,jdk.localedata \
  --include-locales=en,vi \
  --output app-image
```

In this example, the `jdk.localedata` module is added explicitly and locale data is limited to English and Vietnamese. The locale list should match product requirements and the locale tags supported by the JDK.

If the application uses date, number, currency formatting, or collation for other locales, test directly on the image. Missing locale data can cause display or text-processing behavior to differ from the full JDK.

## 11. Limiting the module universe with --limit-modules

`--limit-modules` limits the set of modules observable to the linker when resolving the module graph.

Example:

```sh
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --limit-modules java.base,java.logging,com.example.app \
  --output app-image
```

This option helps control module scope and avoid accidentally observing unexpected modules. However, if a required module or service provider is not in the allowed set, linking will fail or the image will lack functionality.

Only use `--limit-modules` after understanding the dependency graph. To diagnose, you can inspect module descriptors using:

```sh
jar --describe-module --file path/to/library.jar
jmod describe path/to/module.jmod
```

## 12. Module path and input module formats

The module path can contain:

- JMOD files, typically provided in the JDK's `jmods` directory.
- Modular JARs containing `module-info.class`.
- Exploded modules, which are directories containing a module descriptor and class files.

A JAR with only a manifest or only traditional classpath class files does not automatically become a proper explicit module suitable for linking. An automatic module is also not a substitute input for an explicit module in a normal `jlink` workflow.

You can view the module name of a JAR:

```sh
jar --describe-module --file library.jar
```

You can view the description of a JMOD:

```sh
jmod describe library.jmod
```

Input modules must have their dependencies fully resolved. If a module requires another module that is not on the module path, `jlink` will report a resolution error.

Use JMODs from the same JDK that you are using to link. Mixing JMODs from different JDK versions can cause errors due to differences in module versions, class files, or internal structure.

## 13. Verifying the runtime image after creation

After `jlink` succeeds, verify the image using the executable inside the image itself.

List modules:

```sh
./app-image/bin/java --list-modules
```

Check runtime version:

```sh
./app-image/bin/java -version
```

Run a module:

```sh
./app-image/bin/java -m com.example.app/com.example.app.Main
```

Run the launcher if configured:

```sh
./app-image/bin/app
```

On Windows, the corresponding executables are in `app-image\bin`, such as `java.exe` and the launcher with the appropriate extension.

Check the `release` file in the image root directory to view version and module information. Inspect the `bin` directory directly if you need to confirm specific native commands or launchers.

A successfully created image still needs functional testing. Run integration tests and check configuration files, locales, TLS/security providers, logging, native libraries, and resource paths required by the application.

## 14. Platform compatibility

A runtime image is built for the operating system and architecture of the corresponding JDK/linker environment. `jlink` is not a cross-compiler that lets you create a Windows image on Linux simply by changing a parameter.

Native components in the image, such as the JVM library and native commands, depend on the platform's binary format and ABI. Therefore:

- Build Windows images using the appropriate JDK/toolchain on Windows.
- Build Linux images using the appropriate JDK/toolchain on Linux.
- Build macOS images using the appropriate JDK/toolchain on macOS.
- Test the image on the target CPU architecture.
- Check native libraries that depend on the operating system.

If a product supports multiple platforms, build and test a separate image for each platform/architecture. Do not distribute the same runtime image for all operating systems.

## 15. jlink and related JDK tools

| Tool | Role |
|---|---|
| `javac` | Compiles Java source code into class files |
| `jar` | Creates and manipulates JARs; describes modules of modular JARs |
| `jmod` | Creates, lists, describes, and extracts JMODs |
| `jdeps` | Analyzes dependencies of classes/JARs/modules |
| `jlink` | Links modules and creates custom runtime images |
| `java` | Runs applications on the JVM |
| `jimage` | Inspects or manipulates the JDK runtime image format |

A common workflow:

```text
.java source
    |
    v
javac
    |
    v
Exploded module / modular JAR
    |
    v
jmod (if packaging the module as JMOD is needed)
    |
    v
jlink
    |
    v
Custom runtime image
    |
    v
java or launcher in the image
```

Not every project needs to create an intermediate JMOD. If modules are already in exploded module or modular JAR form, they can be placed directly on `jlink`'s module path.

## 16. Common errors

| Symptom | Common Cause | Resolution |
|---|---|---|
| `Error: Module ... not found` | Module is not on the module path or module name is wrong | Check `--module-path`, the name in the module descriptor, and JMOD/JAR paths |
| `Module ... not found, required by ...` | Missing required dependency | Add the module to the module path and check `requires` declarations |
| `automatic module ... cannot be used with jlink` | Input is an automatic module instead of a proper explicit module | Use a modular JAR/JMOD with a descriptor or modularize the dependency explicitly |
| `directory exists and is not empty` | Output directory already exists and has contents | Choose a new output directory or clean the build directory properly and re-run |
| Image builds, but app fails with `ClassNotFoundException` | Missing dynamically loaded module or undeclared dependency | Add the needed module via `--add-modules` and re-test |
| ServiceLoader cannot find provider | Provider module was not linked or service binding is missing | Check `uses`/`provides`, module path, and consider `--bind-services` |
| Image is missing locales | Missing `jdk.localedata` or locale not included | Add the module and configure `--include-locales` |
| Runtime image does not run on another OS | Image contains native binaries for the build platform | Build a separate image using a JDK matching the target |
| Image is too large | Too many modules selected or appropriate plugins not used | Inspect the module graph, select minimal root modules, and measure plugin impact |
| Launcher does not appear | Wrong `--launcher` syntax or invalid module/main class | Check module name, class name, and file list in `bin` |
| Runtime is missing a native command | Command is not in the module or was stripped | Check JMOD `bin/`, `--cmds` configuration, and `--strip-native-commands` plugin |
| App runs on full JDK but fails in image | Image is missing resources, providers, locales, modules, or native dependencies | Test on the image, add the missing components, and re-link |

When encountering errors, first check the module path and module descriptors, then check root modules and dependencies. If linking succeeds but the application fails at runtime, check dynamically loaded components, service providers, resources, and native libraries.

## 17. Checklist for creating a custom runtime image

- [ ] Application is organized into modules with appropriate descriptors.
- [ ] Module path contains the required application and JDK modules.
- [ ] Root modules have been selected with `--add-modules`.
- [ ] Required dependencies and dynamically loaded modules have been accounted for.
- [ ] Service providers have been handled if the application uses `ServiceLoader`.
- [ ] Output directory does not exist or is empty.
- [ ] A launcher is declared if a custom startup command is desired.
- [ ] Compression/strip/locale plugins match product requirements.
- [ ] Image is built for the correct operating system and architecture.
- [ ] `java --list-modules` has been run from the image to confirm modules.
- [ ] Application has been run using the runtime image, not just the development JDK.
- [ ] Dependencies, resources, locales, TLS, and native libraries have been tested on the target environment.

## 18. References

- Oracle JDK Tool Reference — The `jlink` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jlink.html
- Oracle JDK Tool Reference — The `jmod` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jmod.html
- Java Platform Module System — Java Language and JVM specifications: https://docs.oracle.com/javase/specs/

`jlink` turns a resolved set of modules into a runtime image that can be distributed with an application. By choosing the right root modules, dependencies, launcher, and plugins, you can produce a smaller runtime that is easier to test and tailored to the deployment platform.