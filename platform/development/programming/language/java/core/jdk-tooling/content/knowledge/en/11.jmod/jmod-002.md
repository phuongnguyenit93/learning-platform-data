# What is JMOD?

JMOD is a specialized JDK archive format for packaging a Java module along with components that may be needed when creating a runtime image, such as class files, native libraries, native commands, configuration files, headers, licenses, and man pages. The **jmod** tool creates, lists, extracts, describes, and manages hashes of JMOD files.

JMODs commonly appear in the `jmods` directory of a JDK and in the workflow for creating custom runtime images with `jlink`. JMOD is related to modular JARs, but serves a different packaging purpose: JARs are suitable for distributing Java libraries or applications; JMODs are designed for JDK tools, especially the runtime image linking process.

## 1. What is JMOD and when is it used?

**JMOD** is an archive format for Java platform modules. A JMOD can contain:

- Java class files and module resources.
- Native libraries required by the module.
- Accompanying native commands or executables.
- Configuration files.
- Headers for native development.
- Legal notices, licenses, and man pages.
- Module metadata such as version and main class.

Standard JDK modules are distributed as JMODs in the `JDK_HOME/jmods` directory. For example, a JDK typically includes files such as `java.base.jmod` and `java.logging.jmod`. These files are used by tools like `jlink` as inputs to create a runtime image.

### Common JMOD use cases

1. **Packaging modules for jlink:** placing application or custom modules on the module path so `jlink` can link a runtime image.
2. **Packaging native components:** combining class files with related native libraries, commands, or headers.
3. **Distributing modules in a JDK build workflow:** JMODs can hold components that are not suitable for a standard JAR.
4. **Inspecting modules:** reading the module descriptor, listing, or extracting archive contents for diagnostics.

For ordinary Java applications or libraries distributed to users, JAR remains the standard choice. Only create a JMOD when your packaging or runtime image creation workflow actually requires this format.

## 2. How is JMOD different from JAR?

JMOD and JAR are both Java-related archives, but they are not interchangeable in every situation.

| Criterion | JAR | JMOD |
|---|---|---|
| Primary purpose | Distributing Java applications, libraries, and resources | Packaging modules for JDK tools and creating runtime images |
| Contents | Class files, resources, manifest, module descriptor if modular JAR | Class files, resources, and additional sections such as native libraries, commands, config, headers, legal notices, man pages |
| Structure | ZIP archive following JAR conventions | Custom JMOD archive format with a header and categorized sections |
| Direct use with java | Can be run with -jar or placed on the classpath/module path depending on JAR type | Cannot be used directly like a JAR on the classpath or module path at runtime |
| Primary tools | jar, java, javac | jmod and jlink |
| Common use cases | Libraries, executable JARs, modular JARs | JDK modules and inputs for custom runtime images |

JMOD has its own format, so a `.jmod` file should not be treated as a regular JAR or ZIP. Do not use `java -jar filename.jmod` to run a module, and do not place a JMOD on the classpath like a library JAR.

Key point: **jmod packages modules; jlink links modules to create a runtime image; java runs the application from that runtime image.**

## 3. JMOD structure and sections

JMOD organizes its contents into sections. Depending on the module, an archive may contain only a subset of these sections.

| Section | Typical contents | Corresponding creation option |
|---|---|---|
| classes | Java class files and resources | --class-path |
| bin | Native commands or executables | --cmds |
| conf | Editable configuration files | --config |
| include | Header files for native development | --header-files |
| legal | Licenses and legal notices | --legal-notices |
| lib | Native libraries | --libs |
| man | Man pages | --man-pages |

For example, a pure Java module typically consists mainly of the `classes` section. A JDK module may also need native libraries, configuration files, or accompanying documentation.

The module descriptor `module-info.class` is stored alongside the module's class contents. Directives in the descriptor such as `requires`, `exports`, `opens`, `uses`, and `provides` remain meaningful during module resolution. JMOD does not change JPMS rules; it is a way of packaging a module that supports additional types of data beyond class files.

## 4. The jmod tool and its main modes

The `jmod` tool is located in the JDK's `bin` directory. You can check its version and syntax with:

~~~bash
jmod --version
jmod --help
~~~

Main modes:

| Mode | Purpose |
|---|---|
| create | Create a new JMOD archive |
| list | Print the names of entries in a JMOD |
| extract | Extract JMOD contents to a directory |
| describe | Display module information |
| hash | Record hashes to bind modules with matching dependencies |

General syntax:

~~~bash
jmod create [OPTIONS] module.jmod
jmod list module.jmod
jmod describe module.jmod
jmod extract --dir extracted module.jmod
jmod hash [OPTIONS] module.jmod
~~~

Exact option names and details may vary by JDK version. Use `jmod --help` on your target JDK to verify the exact syntax.

## 5. Creating a JMOD from a compiled module

`jmod` does not compile Java source code. First, use `javac` to produce class files and the module descriptor; then use `jmod create` to package the output.

Example creating a simple module named `com.example.hello`.

Directory structure:

~~~text
jmod-demo/
└── src/
    └── com.example.hello/
        ├── module-info.java
        └── com/
            └── example/
                └── hello/
                    └── Main.java
~~~

File `src/com.example.hello/module-info.java`:

~~~java
module com.example.hello {
}
~~~

File `src/com.example.hello/com/example/hello/Main.java`:

~~~java
package com.example.hello;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from a linked runtime!");
    }
}
~~~

### Step 1: Compile the module

From the `jmod-demo` root directory:

~~~bash
javac --release 17 -d mods/com.example.hello \
  src/com.example.hello/module-info.java \
  src/com.example.hello/com/example/hello/Main.java
~~~

The result is an exploded module in `mods/com.example.hello`:

~~~text
mods/
└── com.example.hello/
    ├── module-info.class
    └── com/
        └── example/
            └── hello/
                └── Main.class
~~~

### Step 2: Create the JMOD

Package the compiled module directory:

~~~bash
jmod create \
  --class-path mods/com.example.hello \
  --module-version 1.0 \
  --main-class com.example.hello.Main \
  com.example.hello.jmod
~~~

Explanation:

- `create` creates a new JMOD.
- `--class-path` specifies the JAR or directory containing the module's class files.
- `--module-version` records the module version.
- `--main-class` records the module's main class.
- `com.example.hello.jmod` is the output JMOD file.

The input must be compiled module contents with a valid module descriptor. The `--main-class` option is metadata for other tools; it does not turn a JMOD into a JAR that can be run with `java -jar`.

### Step 3: Describe and list the JMOD

View module information:

~~~bash
jmod describe com.example.hello.jmod
~~~

List entries:

~~~bash
jmod list com.example.hello.jmod
~~~

The listing may display paths with section prefixes, such as `classes/module-info.class` and `classes/com/example/hello/Main.class`. The exact output format depends on the JDK version.

### Step 4: Extract the JMOD

Extract into a separate directory:

~~~bash
jmod extract --dir extracted com.example.hello.jmod
~~~

After extraction, the sections are placed under the `extracted` directory. This is useful when you need to inspect the packaged class files, native libraries, or configuration files.

## 6. Using JMOD with jlink to create a runtime image

One of the primary uses of JMOD is as input to `jlink`. `jlink` resolves the module graph, selects the required modules, and builds a runtime image containing only the requested components.

For the example module above, you need:

- The application JMOD `com.example.hello.jmod`.
- The `jmods` directory of the target JDK, which contains `java.base.jmod` and other standard modules.

On Linux/macOS, assuming `JAVA_HOME` points to the current JDK and you are in the directory containing `com.example.hello.jmod`:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:." \
  --add-modules com.example.hello \
  --launcher hello=com.example.hello/com.example.hello.Main \
  --output runtime
~~~

On Windows Command Prompt, the separator between module path entries is a semicolon:

~~~bat
jlink --module-path "%JAVA_HOME%\jmods;." --add-modules com.example.hello --launcher hello=com.example.hello/com.example.hello.Main --output runtime
~~~

Explanation:

- `--module-path` provides the locations of the modules. This example includes the JDK's JMODs and the current directory containing the application JMOD.
- `--add-modules` selects the root modules to include in the runtime image; `jlink` resolves dependent modules automatically.
- `--launcher` creates a launcher command named `hello` pointing to the module and main class.
- `--output runtime` specifies the output runtime image directory.

If the module path does not contain `java.base`, some versions of `jlink` may automatically add the current JDK's `jmods` directory. Even so, explicitly specifying the JDK `jmods` directory makes the command clearer and easier to control. Do not mix JMODs from different JDK releases or platforms.

### Running the application from the runtime image

On Linux/macOS:

~~~bash
runtime/bin/hello
~~~

Output:

~~~text
Hello from a linked runtime!
~~~

You can also run it directly using the `java` launcher inside the runtime image:

~~~bash
runtime/bin/java -m com.example.hello/com.example.hello.Main
~~~

On Windows, the executable is created in `runtime/bin`; use `runtime\bin\hello.bat` if the launcher script is generated as a `.bat` file, or invoke `runtime\bin\java.exe` with the corresponding `-m` option.

A runtime image is a deployable runtime directory. It is neither a JMOD nor a full JDK; it contains only the modules and components linked by `jlink`.

## 7. Common jmod options

JMOD creation options can be used to include different kinds of content:

| Option | Meaning |
|---|---|
| --class-path | JAR or directory containing class files and resources |
| --cmds | Directory containing native commands |
| --config | Directory containing configuration files |
| --header-files | Directory containing header files |
| --legal-notices | Directory containing licenses and legal notices |
| --libs | Directory containing native libraries |
| --man-pages | Directory containing man pages |
| --module-version | Module version |
| --main-class | Module main class |
| --target-platform | Target platform for the module |
| --compress | Archive compression level, typically zip-0 through zip-9 |
| --date | Timestamp used for archive entries |
| --exclude | Pattern for excluding files from the archive |
| --hash-modules | Pattern of modules for which binding hashes should be recorded |

Not every module needs all sections. For a module containing only Java code, `--class-path` is usually sufficient. Only add native libraries, commands, or configs when the module actually has those components and they are compatible with the target platform.

### Archive compression

The `--compress` option controls the compression level:

- `zip-0`: no compression.
- `zip-1` through `zip-9`: increasing compression levels.
- The default in modern JDKs is typically `zip-6`.

Higher compression can reduce archive size at the cost of slower packaging or extraction. Measure on your actual content instead of choosing the highest compression level by default.

### Target platform

A JMOD can contain native code that depends on the operating system and architecture. The `--target-platform` option records the target platform for the archive. When packaging a module with native libraries, make sure the libraries are built for the right OS, CPU architecture, and ABI.

You cannot take a JMOD containing native libraries for one platform and assume it will run on another. Java class files are portable, but native libraries remain platform-bound.

### Hashes of dependent modules

The `hash` mode supports recording hashes to bind modules that have specific dependency relationships. It is used in advanced module packaging workflows, particularly when ensuring that related modules are built against a matching set of modules.

This is not a general-purpose checksum verification for arbitrary JMOD files. When using it, consult the `jmod hash` documentation for your specific JDK and clearly specify the module path and matching module regex.

## 8. JMODs in the JDK directory

A full JDK typically has a layout similar to:

~~~text
jdk/
├── bin/
│   ├── java
│   ├── javac
│   ├── jmod
│   └── jlink
├── jmods/
│   ├── java.base.jmod
│   ├── java.logging.jmod
│   ├── java.sql.jmod
│   └── ...
└── lib/
~~~

The `jmods` directory holds the JDK's modules in JMOD format. These serve as key inputs when `jlink` builds a runtime image. Do not arbitrarily delete or replace the JMODs shipped with a JDK, as they must match the tools and runtime of the same distribution.

You can check the active JDK version with:

~~~bash
java --version
javac --version
~~~

On Linux/macOS, you can check `JAVA_HOME` and list `$JAVA_HOME/jmods`. On Windows, the corresponding directory is typically `%JAVA_HOME%\jmods`.

JMODs from different vendors or releases should not be mixed in the same link operation unless explicitly documented as compatible.

## 9. Troubleshooting common errors

### jmod: command not found or unrecognized command

The machine may only have a minimal runtime installed, or `PATH` does not point to the JDK's `bin` directory. Verify you have a full JDK installed and check the actual path to `jmod`.

### Invalid JMOD file or unable to read archive

The file may be corrupted, not a valid JMOD format, or created by an incompatible tool version. Check the archive source, file size, and JDK version, and try `jmod describe` or `jmod list`.

### Invalid module descriptor

A JMOD must describe a valid module. Check `module-info.java`, the module name, `requires`/`exports` syntax, and the compiled `module-info.class`. `jmod` only packages the compiled output; it does not fix an invalid module descriptor.

### jlink cannot find the module

Check whether the module path includes both the application JMOD and the corresponding JDK JMODs. Confirm the module name with `jmod describe`. Ensure the name passed to `--add-modules` matches the actual module name rather than confusing the filename with the module name.

### Unresolved module dependency

A module declared with `requires` that is missing from the module path will cause `jlink` to fail. Add the appropriate JMOD or modular JAR dependency; do not try to work around the error by placing arbitrary archives on the classpath.

### Runtime image missing classes or resources

Check the module graph, the module descriptor, whether resources were packaged in the `classes` section, and whether the module was included in the image. `jlink` only links the selected modules and their required dependencies.

### Native library fails to load

Check the `libs` section, target platform, CPU architecture, ABI, and system library dependencies. The class files may be valid while the native library is still incompatible with the runtime environment.

### Mistakenly using JMOD as a JAR

A JMOD is not a JAR to be run with `java -jar` or added to the classpath. Use `jmod` to inspect or package, and `jlink` to create a runtime image; run the application from the runtime image using `java` or the generated launcher.

## 10. JMOD and related tools

| Tool | Role |
|---|---|
| javac | Compiles source code into class files and module descriptors |
| jar | Creates and manipulates JARs for applications and libraries |
| jmod | Creates, lists, extracts, and describes JMODs |
| jlink | Links modules into a custom runtime image |
| java | Runs modules or applications in the runtime |
| jdeps | Analyzes dependencies at the class, package, and module levels |

Typical workflow:

~~~text
.java sources
     |
     v
javac
     |
     v
exploded module (class files + module-info.class)
     |
     v
jmod create
     |
     v
application.jmod
     |
     +------ JDK jmods
     |
     v
jlink
     |
     v
custom runtime image
     |
     v
java / generated launcher
~~~

Each tool has a distinct responsibility: `javac` produces compiled output, `jmod` packages the module, `jlink` creates the runtime image, and `java` executes the application.

## 11. Checklist for creating and using JMODs

- Determine clearly whether a JMOD is needed or if a JAR suffices for distribution.
- Compile the module first with `javac` and verify `module-info.class`.
- Use `--class-path` pointing to the directory or JAR containing the compiled output.
- Set `--module-version` and `--main-class` appropriately if your workflow requires that metadata.
- Only add native/config/header/legal/man sections when the module actually needs them.
- Specify the right target platform if the archive contains native components.
- Use `jmod describe` to confirm the module name and descriptor.
- Use `jmod list` to verify the packaged entries.
- Use `jmod extract` when you need to inspect section contents.
- Place the application JMOD along with the matching JDK `jmods` on `jlink`'s module path.
- Select the root module with `--add-modules` and verify the dependency closure.
- Test the generated runtime image on the actual target platform.
- Do not use a JMOD directly like a JAR on the classpath or with `java -jar`.
- Keep the JDK tools and JMODs from a compatible release/vendor throughout the build workflow.

## 12. Key terms to remember

| Term | Meaning |
|---|---|
| JMOD | Specialized archive format for packaging modules for JDK tools |
| JMOD file | A file with the `.jmod` extension |
| Section | A content group such as `classes`, `bin`, `conf`, `include`, `legal`, `lib`, and `man` |
| Exploded module | A compiled module residing in a directory |
| module-info.class | The compiled module descriptor |
| jmod create | Creates a JMOD from compiled inputs |
| jmod describe | Displays module information |
| jmod list | Lists archive entries |
| jmod extract | Extracts sections to a directory |
| jmod hash | Records module-binding hashes according to tool rules |
| jlink | Builds a runtime image from modules |
| Runtime image | A Java runtime environment linked for a selected set of modules |

JMOD is a packaging format designed for JDK tools and the runtime image creation process. Keep the role of each step clear: **javac compiles the module, jmod packages the module, jlink creates the runtime image, and java runs the application from that runtime image**.