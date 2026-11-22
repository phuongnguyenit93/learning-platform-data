# Creating a JMOD with the jmod Tool

JMOD (Java Module) is an archive format used to package a Java module along with components that may be needed during linking and runtime image creation. The JDK **`jmod`** command-line tool lets you create, list, describe, and extract JMOD files.

JMOD is typically used together with **`jlink`** to create custom runtime images. JMOD is not a drop-in replacement for JAR: JAR is normally used when compiling, running, or distributing applications, whereas JMOD is designed primarily for link time.

## 1. What Is JMOD?

A JMOD file has the `.jmod` extension and can contain multiple content sections:

- **classes:** class files, the module descriptor, and module resources.
- **libs:** native libraries.
- **bin/cmds:** native programs or commands included with the module.
- **conf:** configuration files.
- **include/header files:** headers used for native integration.
- **legal:** license information and legal notices.

JMOD is useful when a module needs to be packaged with components beyond Java bytecode, such as native libraries or configuration files.

A typical JMOD can contain Java classes and `module-info.class`. For a custom Java module, you must compile the module before packaging it.

## 2. Differences Between JMOD and JAR

| Criterion | JAR | JMOD |
| --- | --- | --- |
| File extension | `.jar` | `.jmod` |
| Contents | Class files, resources, manifest, and metadata | Class files/module descriptor along with sections such as native libraries, config, headers, and legal notices |
| Compiling and running | Can be used on the classpath or module path according to JAR structure | Not used directly as a standard compile-time or runtime dependency |
| Linking with jlink | Modular JARs can be used as input modules | The native input format suited for the linking process |
| Common purpose | Distributing Java libraries and applications | Packaging modules for the JDK/runtime image |

One point to keep in mind: JMOD is designed for use at link time. Do not pass a `.jmod` file to `java -cp` or `javac -cp` as if it were a regular JAR. When you need to create a runtime image from modules, use `jlink`.

## 3. Checking the jmod Tool

`jmod` is included with the JDK. Open a terminal and run:

```bash
jmod --version
jmod --help
```

If the system does not recognize the command:

- Check that a full JDK is installed on the machine.
- Check that the JDK's `bin` directory is in `PATH`.
- Check that `JAVA_HOME` points to the JDK root directory.
- Open a new terminal after updating environment variables.

You can invoke the tool directly via its path in `JAVA_HOME/bin` if you do not want to modify `PATH` yet.

## 4. Basic jmod Syntax

Main operations:

```text
jmod create [options] jmod-file
jmod list jmod-file
jmod describe [options] jmod-file
jmod extract [--dir dir] jmod-file
```

| Command | Purpose |
| --- | --- |
| `jmod create` | Create a JMOD file from class files and input sections |
| `jmod list` | List entries inside a JMOD |
| `jmod describe` | Display module description and module descriptor |
| `jmod extract` | Extract JMOD contents to a directory |
| `jmod hash` | Compute and record hashes for dependent modules as configured |

Specific options may vary depending on the JDK version. Use `jmod --help` from the exact JDK you are using to check supported syntax.

## 5. Preparing a Java Module

The following example creates the `com.example.hello` module, compiles the module into class files, and packages it into a JMOD.

Source code structure:

```text
project/
  src/
    com.example.hello/
      module-info.java
      com/
        example/
          hello/
            Main.java
```

Create **`src/com.example.hello/module-info.java`**:

```java
module com.example.hello {
    exports com.example.hello;
}
```

The module descriptor declares the module name and the package exported to other modules.

Create **`src/com.example.hello/com/example/hello/Main.java`**:

```java
package com.example.hello;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from JMOD module");
    }
}
```

The `Main` class is the entry point for the example. The `com.example.hello` package is exported in `module-info.java`.

## 6. Compiling the Module Before Creating a JMOD

At the `project` root directory, create the output directory and compile the module.

**Windows PowerShell:**

```powershell
New-Item -ItemType Directory -Force mods | Out-Null
javac -d mods --module-source-path src -m com.example.hello
```

**macOS/Linux:**

```bash
mkdir -p mods
javac -d mods --module-source-path src -m com.example.hello
```

After compiling, the output structure looks like:

```text
mods/
  com.example.hello/
    module-info.class
    com/
      example/
        hello/
          Main.class
```

The `mods/com.example.hello` directory is the root of the compiled module. It contains `module-info.class` and the class files organized by package structure.

You can inspect the compiled module with:

```bash
java --module-path mods --list-modules
```

Or run the module directly before packaging:

```bash
java --module-path mods -m com.example.hello/com.example.hello.Main
```

Output:

```text
Hello from JMOD module
```

This test run confirms that the module descriptor, module name, and main class work on the module path.

## 7. Creating a JMOD with jmod create

Once you have the class files, create the JMOD:

```bash
jmod create --class-path mods/com.example.hello --module-version 1.0.0 --main-class com.example.hello.Main com.example.hello.jmod
```

Option meanings:

- `create`: creates a new JMOD archive.
- `--class-path mods/com.example.hello`: takes class files and resources from the compiled module directory.
- `--module-version 1.0.0`: attaches a version to the module.
- `--main-class com.example.hello.Main`: declares the module's main class.
- `com.example.hello.jmod`: name of the output JMOD file.

This command packages an already compiled module; it does not compile Java source code. If you modify the source code, recompile before creating a new JMOD.

Other `jmod create` options:

| Option | Content added to JMOD |
| --- | --- |
| `--class-path` | Module class files and resources |
| `--cmds` | Native commands/programs |
| `--config` | Configuration files |
| `--header-files` | Native header files |
| `--libs` | Native libraries |
| `--legal-notices` | Legal notice files |
| `--module-version` | Module version |
| `--main-class` | Module main class |
| `--target-platform` | Target platform for module contents when needed |

Sections such as native libraries, commands, and headers are only needed when the module actually includes those components. For pure Java modules, `--class-path` is usually sufficient.

## 8. Listing JMOD Contents with jmod list

After creating the archive, run:

```bash
jmod list com.example.hello.jmod
```

The output will contain entries similar to:

```text
classes/module-info.class
classes/com/example/hello/Main.class
```

Depending on the JDK version, formatting and additional entries may differ. Verify that the JMOD contains the module descriptor and the expected class files.

If `module-info.class` is missing, recheck the directory passed to `--class-path` and the module compilation step. A JMOD for a named module requires a valid module descriptor.

## 9. Describing a Module with jmod describe

Run:

```bash
jmod describe com.example.hello.jmod
```

For the example module, the output looks like:

```text
com.example.hello@1.0.0
exports com.example.hello
requires java.base mandated
main-class com.example.hello.Main
```

The output may include:

- Module name.
- Module version, if declared.
- Exported packages.
- Required modules.
- Main class, if declared.
- Other module attributes.

`jmod describe` is useful for verifying metadata without manually extracting or directly reading binary class files.

## 10. Extracting a JMOD with jmod extract

To inspect the contents in detail, extract the archive:

```bash
jmod extract --dir extracted com.example.hello.jmod
```

After extraction, sections are placed into their corresponding directories. For a pure Java example, the structure may be:

```text
extracted/
  classes/
    module-info.class
    com/
      example/
        hello/
          Main.class
```

You can use `javap` to inspect the extracted module descriptor or class files:

```bash
javap -p -v extracted/classes/com/example/hello/Main.class
```

When you need to inspect the module descriptor:

```bash
javap -v extracted/classes/module-info.class
```

Extraction is only for inspecting or processing archive contents. To create a runtime image, use the original JMOD as input to `jlink`.

## 11. Using JMOD with jlink to Create a Runtime Image

JMOD shines when linking modules into a runtime image. `jlink` reads modules from the module path, selects the required modules, and builds a custom runtime image.

To link the example module, the module path needs:

- The standard JMOD directory of the current JDK, usually `$JAVA_HOME/jmods`.
- The directory containing the custom JMOD, which in this example is the current directory `.`.

**macOS/Linux:**

```bash
jlink --module-path "$JAVA_HOME/jmods:." --add-modules com.example.hello --output image
```

**Windows PowerShell:**

```powershell
jlink --module-path "$env:JAVA_HOME\jmods;." --add-modules com.example.hello --output image
```

Explanation:

- `--module-path`: where `jlink` looks for JDK modules and custom modules.
- `--add-modules com.example.hello`: root module to include in the runtime image; required dependencies are resolved from the module graph.
- `--output image`: output runtime image directory.

The `image` directory must not already exist or must satisfy `jlink`'s output directory requirements. It is good practice to create the new runtime image at a separate path for each build.

Run the application from the runtime image:

**macOS/Linux:**

```bash
./image/bin/java -m com.example.hello/com.example.hello.Main
```

**Windows PowerShell:**

```powershell
.\image\bin\java.exe -m com.example.hello/com.example.hello.Main
```

Output:

```text
Hello from JMOD module
```

The runtime image contains only the selected modules and their required dependencies. This reduces the runtime environment size compared to distributing an entire JDK, depending on the actual modules and components of the application.

## 12. JMOD Can Contain Native Libraries and Configuration

One advantage of JMOD is the ability to package content beyond class files. For example, a module that needs native libraries can add a library directory using `--libs`:

```bash
jmod create --class-path mods/com.example.hello --libs native-libs --module-version 1.0.0 com.example.hello.jmod
```

Additional options can include commands, configuration, headers, and legal notices in the archive:

```bash
jmod create --class-path mods/com.example.hello --cmds commands --config config --header-files include --libs native-libs --legal-notices legal com.example.hello.jmod
```

The paths in the example must exist and contain the corresponding type of content. You do not need to create these directories if the module has no native components or additional metadata.

When packaging native libraries:

- Choose the correct target architecture and operating system.
- Ensure library names and locations match how the module uses them.
- Check native dependencies of the libraries.
- Use a toolchain and JDK compatible with the target platform.
- Test the runtime image on the corresponding deployment environment.

A JMOD can carry platform-specific content, so you should not assume a JMOD containing native libraries can be used as-is across all operating systems.

## 13. Important Notes When Creating JMODs

- **Compile before packaging:** `jmod create` takes class files/resources, not source code to compile itself.
- **Module descriptor:** a custom module must have a valid `module-info.class`.
- **Module name:** must be consistent across `module-info.java`, the `javac` command, `--main-class`, and `jlink --add-modules`.
- **JDK version:** use a matching JDK version for `javac`, `jmod`, and `jlink`; avoid mixing module formats from incompatible toolchains.
- **JMOD is not a standard runtime dependency:** do not put JMODs on the `java` or `javac` classpath like JARs.
- **JMOD and JAR serve different purposes:** if you only need to distribute a regular Java library or application, JAR is usually more appropriate.
- **JMOD can contain native components:** identify the target platform and test on the corresponding OS/architecture.
- **Runtime image:** after running `jlink`, test the output image rather than only checking that JMOD creation succeeded.

## 14. Common Errors

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `jmod` is not recognized | JDK not installed or `PATH` lacks the `bin` directory | Check `JAVA_HOME` and `PATH` |
| `jmod create` cannot find class files | `--class-path` points to the wrong directory or module is not compiled | Check the output directory and recompile with `javac` |
| Invalid module descriptor | Missing or incorrect `module-info.class` | Check `module-info.java`, module name, and output structure |
| `jmod describe` reports an error | File is not a valid JMOD or is corrupted | Recreate the archive and inspect with `jmod list` |
| `jlink` cannot find module | Module path is missing JMODs or module name is wrong | Include the JDK `jmods` directory and the directory with the custom JMOD |
| Runtime image fails to launch | Module was not added or main class is incorrect | Check `--add-modules`, `--main-class`, and the `java -m` command |
| JMOD works on this machine but fails on another | Contains native libraries or platform-specific content | Build and test artifacts for the exact target OS/architecture |
| Using JMOD in `java -cp` fails to find classes | JMOD is not a standard runtime JAR | Use JMOD with `jlink` or distribute a modular JAR as appropriate |

## 15. Recommended Workflow for Creating a JMOD

A repeatable workflow:

1. Create the module with `module-info.java` and the required packages.
2. Compile the module with `javac` into a dedicated output directory.
3. Test-run the module on the module path to confirm the module descriptor and main class.
4. Use `jmod create` to package class files and any needed sections.
5. Use `jmod list` to verify the archive contents.
6. Use `jmod describe` to check the module name, version, exports, requires, and main class.
7. Use `jmod extract` when you need to inspect sections in detail.
8. Use `jlink` to create a runtime image from the JMOD and required JDK modules.
9. Test-run the application using Java inside the runtime image.
10. Record the JDK version, build commands, and target platform so the artifact can be reproduced.

## 16. Summary

- JMOD is an archive format for Java modules and runtime linking.
- `jmod create` builds a JMOD from class files and input sections.
- `jmod list`, `describe`, and `extract` are used to list, describe, and extract archives respectively.
- Custom modules must be compiled first and have a valid module descriptor.
- JMODs can contain class files, native libraries, commands, config, headers, and legal notices.
- JMODs are not used directly like JARs on a standard compile/runtime classpath.
- `jlink` uses JMODs and required modules to create custom runtime images.

Once you master the `javac` → `jmod create` → archive inspection → `jlink` workflow, you can package Java modules and build smaller, controlled runtime environments for deploying applications.
