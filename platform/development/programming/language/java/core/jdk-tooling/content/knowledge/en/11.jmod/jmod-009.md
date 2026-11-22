# JMOD and Module Images in Java

**JMOD** is an archive format for modules in the JDK ecosystem. A JMOD can contain bytecode along with supplementary components such as native libraries, headers, commands, configuration files, man pages, and legal notices. The `jmod` tool creates, lists, describes, and extracts these archives.

**A module image** is a runtime image created with `jlink`. The image contains the JVM along with the set of modules required by the application and can include its own launcher. In a typical workflow, JMOD is one of the inputs to `jlink`: `jmod` prepares the module archive, while `jlink` links the modules into a runtime image for deployment.

Both concepts belong to the Java Platform Module System (JPMS), introduced in Java 9. They support packaging modules and creating tailored runtimes for modular applications.

## 1. What Problem Does JMOD Solve?

A modular JAR typically packages an application's class files and resources. JMOD extends the packaging model to include additional components for the platform or deployment environment:

- Java class files and `module-info.class`.
- Native commands or executables bundled with the module.
- Native libraries.
- Header files used for JNI integration.
- Configuration files.
- Man pages and legal notices.
- Metadata for module linking.

JMOD is suited for platform-level module packaging or as an input for runtime image creation tools. A JMOD is not an ordinary JAR and is not designed to be run directly with `java -jar`.

### JMOD, Modular JAR, and Module Image

| Component | Main Contents | Usage |
|---|---|---|
| Modular JAR | Class files, resources, and module descriptor | Running a modular application or serving as input to module tools |
| JMOD | Class files along with supplementary sections such as native libraries, headers, config, and legal notices | Distributing modules for JDK tooling and serving as input to `jlink` |
| Module image | Runtime image containing the JVM and linked modules | Deploying and running the application on the target platform |

`jmod create` creates the archive; `jlink` is what creates the runtime image.

## 2. Structure and Sections of a JMOD

JMOD is an archive format with a section-based structure. When listing contents, `jmod list` typically displays paths starting with the section name.

| Section | Contents |
|---|---|
| `classes` | `module-info.class`, class files, and module resources |
| `bin` | Native commands or bundled executables |
| `conf` | Configuration files |
| `include` | Header files, typically used for native/JNI integration |
| `legal` | Legal notices and license information |
| `lib` | Native libraries and library components |
| `man` | Manual pages |
| `hashes` | Module hash data when generated/configured |

Not every JMOD contains all sections. A simple application JMOD may only contain `classes`; a JDK system module may also include native libraries, commands, configuration, or legal files.

JMOD has its own header and organization. You should not treat it as a JAR with a renamed extension or use arbitrary ZIP/JAR tools to modify its structure. Use `jmod` to work with the archive.

## 3. Location of JMODs in the JDK

A full JDK typically has a `jmods` directory containing the module archives of the Java platform. Common example paths include:

~~~text
Windows:
C:\Program Files\Java\jdk-17\jmods

Linux:
/usr/lib/jvm/jdk-17/jmods

macOS:
/Library/Java/JavaVirtualMachines/jdk-17.jdk/Contents/Home/jmods
~~~

The exact path depends on the vendor and installation method. If `JAVA_HOME` points to the JDK root directory, you can find the module archives in:

~~~text
%JAVA_HOME%\jmods
$JAVA_HOME/jmods
~~~

The JDK may contain files such as `java.base.jmod`, `java.logging.jmod`, `java.sql.jmod`, and many other modules. These are the module archives that JDK tools use to create runtime images or inspect platform components.

Do not confuse the `jmods` directory with the `lib` directory of a runtime image. JDK JMODs are packaging inputs for development/linking tools; they are not libraries to place on a regular classpath.

## 4. Basic `jmod` Commands

`jmod` is a command-line tool in the JDK's `bin` directory. View its help with:

~~~text
jmod --help
~~~

| Command | Purpose |
|---|---|
| `jmod create` | Creates a JMOD from a compiled module and supplementary sections |
| `jmod list` | Lists entries in a JMOD |
| `jmod describe` | Displays the module descriptor and module information |
| `jmod extract` | Extracts the sections and entries of a JMOD |
| `jmod hash` | Computes/records hashes for modules according to the specified configuration |

Exact syntax and options depend on the JDK version; check `jmod --help` for the exact JDK you are using before running deployment scripts.

### 4.1. Listing Contents with `jmod list`

Syntax:

~~~text
jmod list path/to/module.jmod
~~~

Example with a JDK module, in PowerShell:

~~~powershell
jmod list "$env:JAVA_HOME\jmods\java.base.jmod"
~~~

On macOS/Linux:

~~~sh
jmod list "$JAVA_HOME/jmods/java.base.jmod"
~~~

The command displays entries inside the archive, such as class files in `classes/`, native libraries in `lib/`, or configuration files in `conf/`. Output for system modules is quite long; when investigating, look for the specific section or package you need.

### 4.2. Describing a Module with `jmod describe`

Syntax:

~~~text
jmod describe path/to/module.jmod
~~~

Example:

~~~sh
jmod describe "$JAVA_HOME/jmods/java.logging.jmod"
~~~

The description typically includes the module name, module version if present, exported packages, module dependencies (`requires`), main class, or related metadata. The output reflects the archive's module descriptor and metadata; it is not a list of all class files.

### 4.3. Extracting with `jmod extract`

Syntax:

~~~text
jmod extract --dir extracted path/to/module.jmod
~~~

Example:

~~~sh
jmod extract --dir extracted "$JAVA_HOME/jmods/java.logging.jmod"
~~~

The `extracted` directory will contain the extracted sections, such as `classes`, `conf`, `legal`, or `lib` if the archive includes those sections. You should extract into a separate directory; do not extract directly into the JDK installation directory or a system directory currently in use.

## 5. Creating a JMOD from a Java Module

We will create a small module named `com.example.greeter`, compile it into an exploded module, package it into a JMOD, and then use `jlink` to create a runtime image.

Project structure:

~~~text
project/
  src/
    module-info.java
    com/
      example/
        greeter/
          Main.java
  out/
  mods/
  greeter-image/
~~~

### 5.1. Declaring the Module

Create `src/module-info.java`:

~~~java
module com.example.greeter {
    exports com.example.greeter;
}
~~~

`exports` allows other modules to access public types in the `com.example.greeter` package.

Create `src/com/example/greeter/Main.java`:

~~~java
package com.example.greeter;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from a custom module image!");
    }
}
~~~

The fully qualified name of the main class is `com.example.greeter.Main`.

### 5.2. Compiling into an Exploded Module

From the `project` root directory, create the output directories and compile.

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out, mods | Out-Null
javac --release 17 -d out src/module-info.java src/com/example/greeter/Main.java
~~~

macOS/Linux:

~~~sh
mkdir -p out mods
javac --release 17 -d out src/module-info.java src/com/example/greeter/Main.java
~~~

After compilation, the `out` directory looks like:

~~~text
out/
  module-info.class
  com/
    example/
      greeter/
        Main.class
~~~

The `out` directory is an exploded module: the module descriptor is at the root and class files are organized by package. You can test-run this module before creating a JMOD:

~~~text
java --module-path out -m com.example.greeter/com.example.greeter.Main
~~~

Stdout:

~~~text
Hello from a custom module image!
~~~

### 5.3. Creating a JMOD with `jmod create`

Create a JMOD from the compiled class files:

~~~text
jmod create --class-path out --module-version 1.0 --main-class com.example.greeter.Main mods/com.example.greeter.jmod
~~~

Meaning:

- `create`: creates a JMOD archive.
- `--class-path out`: takes the module descriptor, class files, and resources from the `out` directory.
- `--module-version 1.0`: records the module version.
- `--main-class`: declares the module's main class.
- `mods/com.example.greeter.jmod`: output JMOD path.

`out` must contain `module-info.class` at the root directory. If the module descriptor is missing or invalid, creating or describing the module will fail.

### 5.4. Inspecting the Newly Created JMOD

List the contents:

~~~text
jmod list mods/com.example.greeter.jmod
~~~

For this example, the key entries will look similar to:

~~~text
classes/module-info.class
classes/com/example/greeter/Main.class
~~~

Describe the module:

~~~text
jmod describe mods/com.example.greeter.jmod
~~~

The output reflects the module name `com.example.greeter`, exported packages, the platform dependency `java.base`, and the declared main class. Exact formatting depends on the JDK version.

Extract to inspect:

~~~text
jmod extract --dir extracted mods/com.example.greeter.jmod
~~~

After extraction, the class files are placed under `extracted/classes/`.

## 6. Creating a Module Image with `jlink`

`jlink` links a set of modules and their required dependencies into a runtime image. The image typically contains the Java runtime, resolved application and platform modules, runtime libraries, necessary configuration, and a launcher if declared.

Basic syntax:

~~~text
jlink --module-path module-path --add-modules module-name --output image-directory
~~~

- `--module-path`: where to find input modules. Typically includes the JDK's `jmods` directory and the directory containing application JMODs.
- `--add-modules`: specifies the root modules to include in the image. `jlink` resolves required dependencies.
- `--output`: output runtime image directory.

### 6.1. Linking an Image for the Greeter Example

On macOS/Linux, use a colon `:` to separate module path entries:

~~~sh
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.greeter --launcher greeter=com.example.greeter/com.example.greeter.Main --output greeter-image
~~~

On Windows PowerShell, use a semicolon `;`:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.greeter --launcher greeter=com.example.greeter/com.example.greeter.Main --output greeter-image
~~~

`--launcher` creates a `greeter` command pointing to the module and main class. If you do not need a custom launcher, you can omit this option and invoke the Java launcher inside the image with `-m`.

`jlink` must be able to find the JDK modules the application depends on—typically at least `java.base`—along with the `com.example.greeter` JMOD. If a required module is missing, linking will fail with a module resolution error.

### 6.2. Running the Application from the Module Image

On Linux/macOS:

~~~sh
./greeter-image/bin/greeter
~~~

On Windows PowerShell:

~~~powershell
.\greeter-image\bin\greeter.exe
~~~

Stdout:

~~~text
Hello from a custom module image!
~~~

This is the application running from the newly created runtime image. The target machine does not need a full JDK installed to run the image, though the image still depends on a compatible operating system and architecture.

### 6.3. Checking Modules Included in the Image

Use the Java launcher inside the image.

Linux/macOS:

~~~sh
./greeter-image/bin/java --list-modules
~~~

Windows:

~~~powershell
.\greeter-image\bin\java.exe --list-modules
~~~

The list displays the runtime modules included in the image, including the application module and linked dependency modules.

## 7. Commonly Used `jmod create` Options

`jmod create` can accept multiple input directories for different sections:

| Option | Contents |
|---|---|
| `--class-path path` | Class files and module resources |
| `--cmds path` | Native commands |
| `--config path` | Configuration files |
| `--header-files path` | Header files |
| `--libs path` | Native libraries |
| `--man-pages path` | Man pages |
| `--legal-notices path` | Legal notices |
| `--module-version version` | Module version |
| `--main-class class` | Module main class |
| `--target-platform platform` | Target platform for the module |
| `--hash-modules regex` | Computes hashes for modules matching the regular expression |

Example of packaging a module with native libraries and headers:

~~~text
jmod create --class-path out --libs native/lib --header-files native/include --module-version 1.0 mods/com.example.native.jmod
~~~

The paths are examples; each directory must contain the appropriate file types and a valid module descriptor. When native libraries are included, the module image becomes dependent on the platform and architecture of those native libraries.

Do not pass arbitrary directories to sections just to bundle files into the archive. Place files in the proper section according to their purpose and verify with `jmod list`.

## 8. Useful `jlink` Options

| Option | Purpose |
|---|---|
| `--module-path` | Specifies where to find modules |
| `--add-modules` | Selects root modules to link |
| `--bind-services` | Links service provider modules matching used services |
| `--launcher` | Creates a launcher for a module/main class |
| `--output` | Specifies the image directory |
| `--strip-debug` | Strips debug information from linked modules |
| `--no-header-files` | Excludes header files from the image |
| `--no-man-pages` | Excludes man pages from the image |
| `--compress` | Configures resource/module compression level in the image |
| `--list-plugins` | Lists available plugins |

Supported options and compression levels depend on the JDK. Check `jlink --help` and `jlink --list-plugins` before standardizing image configurations in CI.

For example, a smaller image can strip debug information, headers, and man pages if the application does not need them:

~~~text
jlink --strip-debug --no-header-files --no-man-pages --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.greeter --output greeter-image
~~~

Do not strip components if the application or operational workflow needs them. The goal is an image that is sufficient, diagnosable, and suited to deployment requirements.

## 9. JMOD and Module Images in the Deployment Process

A typical modular deployment pipeline includes these steps:

1. Write source code and the module descriptor.
2. Use `javac` to produce an exploded module.
3. Package into a modular JAR or JMOD depending on the target.
4. Inspect the descriptor and archive contents.
5. Use `jlink` to link modules with platform dependencies.
6. Verify the image and launcher.
7. Distribute the image matching the target machine's platform.

Important distinctions:

- `jmod` creates and manipulates module archives; `jlink` creates runtime images.
- A JMOD is not an executable JAR and cannot be run with `java -jar`.
- JMOD is designed for JDK tooling, especially the linking workflow; do not use JMODs as regular classpath libraries when running an application.
- A modular JAR can run on a compatible runtime and can also serve as an input module for `jlink`.
- A module image contains a linked runtime; it is not a Docker/container image and does not include an entire operating system.

## 10. Size and Portability of Module Images

One benefit of `jlink` is producing a runtime image containing only the modules the application needs and their resolved dependencies. Image size depends on:

- The set of linked modules.
- Bundled native libraries and resources.
- Debug metadata.
- Selected plugins and compression level.
- Whether legal notices, configuration, man pages, and headers are retained.

Module images are platform-specific. An image built for Windows cannot be copied to Linux and run directly; the CPU architecture and native libraries must also be compatible. You should build the image using a JDK matching the target platform or a toolchain that properly supports the target platform.

If an application uses JNI or native libraries, `jlink` does not automatically convert native libraries to another platform. You must provide the right binaries for each target operating system/architecture.

## 11. Common Errors When Working with JMOD and Module Images

### `jmod` or `jlink` is not recognized

**Cause:** `PATH` does not point to the JDK's `bin` directory, or only a minimal runtime is installed on the machine.

**Fix:** Check `JAVA_HOME`, use the full path to `jmod`/`jlink` in the JDK, or add `%JAVA_HOME%\bin` / `$JAVA_HOME/bin` to `PATH`. Verify with `jmod --help` and `jlink --help`.

### Module descriptor not found

**Cause:** The directory passed to `--class-path` does not have `module-info.class` at its root, or the source code was not compiled as a module.

**Fix:** Compile `module-info.java` together with the application classes and verify `out/module-info.class` exists before calling `jmod create`.

### `jmod create` reports a module or archive error

**Cause:** Invalid module descriptor, inconsistent module name, incorrect input path, or non-existent section directory.

**Fix:** Check `module-info.java`, build output, and the `--class-path` path; use `jmod describe` after creation to verify metadata.

### `jmod list` does not show expected files

**Cause:** Files were not placed in the right section, or the source directory was not specified in the `jmod create` command.

**Fix:** Check `--class-path`, `--libs`, `--cmds`, `--config`, `--header-files`, and corresponding section options. Recreate the archive from verified inputs.

### `jlink` reports module not found

**Cause:** The module path is missing the JDK `jmods`, missing the application JMOD, or the module name in `--add-modules` is incorrect.

**Fix:** Verify the module with `jmod describe`, ensure `--module-path` includes both `$JAVA_HOME/jmods` and the application JMOD directory, and use the exact module name in `--add-modules`.

### `jlink` reports missing dependency

**Cause:** The module descriptor does not declare `requires` properly, or the dependency is not on the module path.

**Fix:** Check `requires` in `module-info.java`, add the corresponding module, and re-run `jlink`. Required dependencies must be resolved in the module graph.

### Image runs on the build machine but fails on the target machine

**Cause:** Different OS/architecture, missing execute permissions, incompatible native libraries, or unsuitable image configuration.

**Fix:** Build the image for the exact target platform, check launcher execute permissions, native libraries, and required environment variables. Do not copy a Windows image to Linux or vice versa.

### Application cannot find resources at runtime

**Cause:** Resources were not packaged in the module, or the resource lookup path is incorrect.

**Fix:** Verify that resources exist in the module output/JMOD and use appropriate resource APIs such as `Class.getResource` or `Module.getResourceAsStream`. JMOD only packages files that are actually present in the input sections.

## 12. Verifying JMODs and Images in CI

A reproducible build pipeline should record:

- JDK version and build platform.
- Module name and module descriptor.
- `javac` command and target release.
- Input paths passed to `jmod create`.
- Output of `jmod describe` and key entries from `jmod list`.
- Module path and root modules passed to `jlink`.
- Launcher and plugin options used.
- List of modules in the image.
- Smoke test results on the image.
- Target operating system and architecture.

Sample verification steps:

~~~text
java --version
javac --version
jmod describe mods/com.example.greeter.jmod
jmod list mods/com.example.greeter.jmod
jlink --list-plugins
greeter-image/bin/java --list-modules
~~~

The last command uses the appropriate path on Windows or Unix-like systems. In CI, run the image's launcher to confirm the application actually starts and check stdout/exit code.

## 13. Quick Checklist

- [ ] A JMOD is a JDK module archive, not an ordinary JAR.
- [ ] A JMOD can contain class files, native libraries, commands, config, headers, legal notices, and man pages.
- [ ] `jmod list` lists entries in the archive.
- [ ] `jmod describe` displays the module descriptor and metadata.
- [ ] `jmod extract` extracts the archive by sections.
- [ ] `jmod create` packages a compiled module and supplementary sections.
- [ ] `module-info.class` must be at the root of the class output when creating a JMOD from an exploded module.
- [ ] A JMOD cannot be run directly with `java -jar`.
- [ ] `jlink` links modules and dependencies into a runtime image.
- [ ] The module path for `jlink` must include JDK `jmods` and application modules.
- [ ] `--launcher` creates a convenient launch command in the image.
- [ ] Verify the image with `java --list-modules` and run a smoke test.
- [ ] Images depend on the operating system, architecture, and native libraries.
- [ ] Use the proper JDK/toolchain for the deployment platform.

JMOD packages modules along with supplementary components in a structure understood by JDK tooling. Combining `jmod` with `jlink` lets you go from modular source code to a compact runtime image with a launcher containing only the modules your application needs.