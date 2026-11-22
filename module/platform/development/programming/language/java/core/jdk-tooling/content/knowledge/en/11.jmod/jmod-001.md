# The jmod Command in the JDK

`jmod` is a command-line tool included with the JDK for creating, inspecting, extracting, and managing JMOD files. JMOD is an archive format for Java modules that can contain class files, a module descriptor, and additional components such as native libraries, native commands, configuration files, headers, man pages, and legal notices.

JMOD typically appears in workflows for creating a runtime image with `jlink` or when a module needs to package native components. For most standard Java applications, a modular JAR remains the more suitable format for running, distributing, and publishing through repositories. JMOD is intended for compile time or linking a runtime image; it is not a format that can be executed directly on the JVM.

This lesson uses JDK 21 as its baseline. Specific options may vary across JDK versions, so check the help output of the JDK installed on your machine.

## 1. What is JMOD?

A JMOD is an archive that holds the contents of a Java module. In addition to class files and `module-info.class`, it can contain additional sections:

- **Classes:** the module's class files and accompanying resources.
- **Native libraries:** native libraries used by the module.
- **Native commands:** related native executables or commands.
- **Configuration:** editable configuration files.
- **Header files:** headers, typically for native/JNI integration.
- **Man pages:** command reference documentation.
- **Legal notices:** legal and licensing information.

JMOD allows bundling these components into a single archive for use by build tools or the linker.

### 1.1. JMOD vs. Modular JAR

Both formats can package a module, but they serve different purposes:

| Feature | Modular JAR | JMOD |
|---|---|---|
| Contains class files and module descriptor | Yes | Yes |
| Contains Java resources | Yes | Yes |
| Packages native libraries/configuration using JMOD sections | Not in JMOD structure | Yes |
| Runs directly with the Java launcher on the module path | Yes | No |
| Used at compile/link time | Yes | Yes |
| Suitable for standard application distribution | Usually suitable | Usually not the first choice |
| Used as input for jlink | Possible | Primary use case |

Do not run a JMOD file with `java -jar`. JMOD is not an executable JAR. If you need to run an application, use a modular JAR or create a runtime image with `jlink` and run the launcher generated inside that image.

## 2. Syntax and Modes of jmod

General syntax:

~~~text
jmod (create|extract|list|describe|hash) [options] jmod-file
~~~

Five primary modes:

| Mode | Purpose |
|---|---|
| `create` | Creates a new JMOD archive from class files and additional contents |
| `extract` | Extracts the contents of a JMOD |
| `list` | Lists the entries inside a JMOD |
| `describe` | Displays module information stored in a JMOD |
| `hash` | Computes and records hashes of related modules according to the module graph |

Check version and help:

~~~bash
jmod --version
jmod --help
jmod --help-extra
~~~

`--help-extra` displays additional options such as `--do-not-resolve-by-default` and `--warn-if-resolved`. Do not guess options based on a different JDK version; check the help output from the actual `jmod` executable used by your build.

## 3. Preparing a Sample Module

Create a small module to practice the commands. Source structure:

~~~text
project/
└── src/
    └── com.example.greetings/
        ├── module-info.java
        └── com/
            └── greetings/
                └── Main.java
~~~

File `src/com.example.greetings/module-info.java`:

~~~java
module com.example.greetings {
    exports com.greetings;
}
~~~

File `src/com.example.greetings/com/greetings/Main.java`:

~~~java
package com.greetings;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from JMOD");
    }
}
~~~

The module is named `com.example.greetings` and exports the `com.greetings` package. The `main` method is the program's entry point.

Compile the module using the JDK:

~~~bash
javac --module-source-path src -d mods -m com.example.greetings
~~~

After compilation, the `mods` directory has a structure similar to:

~~~text
mods/
└── com.example.greetings/
    ├── module-info.class
    └── com/
        └── greetings/
            └── Main.class
~~~

Try running the module from the compiled class files:

~~~bash
java --module-path mods -m com.example.greetings/com.greetings.Main
~~~

Output:

~~~text
Hello from JMOD
~~~

This is the compiled module. We will package that module directory into a JMOD in the next step.

## 4. Creating a JMOD with create

The `create` mode builds an archive from compiled contents. Create the target directory and run:

~~~bash
mkdir -p jmods
jmod create --class-path mods/com.example.greetings \
  --main-class com.greetings.Main \
  --module-version 1.0 \
  jmods/com.example.greetings.jmod
~~~

On Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force jmods | Out-Null
jmod create --class-path mods/com.example.greetings --main-class com.greetings.Main --module-version 1.0 jmods/com.example.greetings.jmod
~~~

Meaning of each part:

- `create` requests creating a new archive.
- `--class-path` specifies the JAR or directory containing class files to copy into the JMOD.
- `--main-class` records the main class name in the module descriptor.
- `--module-version` records the module version in the descriptor.
- The final argument is the path of the JMOD file to create.

The class path directory must contain the module descriptor `module-info.class` and the corresponding class files. For the sample module, that directory is `mods/com.example.greetings`.

If the module has native libraries, you can include additional directories:

~~~bash
jmod create --class-path mods/com.example.greetings \
  --libs native-libs \
  --cmds native-commands \
  --config config \
  --header-files include \
  --legal-notices legal \
  --man-pages man \
  jmods/com.example.greetings.jmod
~~~

The additional paths are optional. Only include directories that actually exist in the project. JMOD copies the contents of the specified paths, including subdirectories, except files matching exclusion patterns.

## 5. Listing Contents with list

Use `list` to view the entries inside a JMOD:

~~~bash
jmod list jmods/com.example.greetings.jmod
~~~

The output lists the entry names in the archive. For the sample module, you will see entries related to the module descriptor and class files, such as:

~~~text
classes/module-info.class
classes/com/greetings/Main.class
~~~

The exact entry names depend on the packaged contents. If the archive includes native libraries, configuration files, or headers, the listing will also show the corresponding entries.

`list` only shows what contents are packaged. It does not verify that the application runs properly or that native libraries are compatible with the current operating system.

## 6. Viewing Module Information with describe

Use `describe` to read module metadata from a JMOD:

~~~bash
jmod describe jmods/com.example.greetings.jmod
~~~

The module description output typically shows:

- Module name and version, if present.
- Exported packages.
- Required modules via `requires`.
- Main class, if declared in the metadata.
- Other module details such as hashes, if recorded.

For the sample module, key details include the name `com.example.greetings`, the exported package `com.greetings`, and the `java.base` module implicitly required according to the Java module system rules.

Use `describe` when you want to inspect an archive's metadata without extracting it or inspecting individual class files.

## 7. Extracting with extract

The `extract` mode unpacks all entries of a JMOD. Use `--dir` to specify the destination directory:

~~~bash
jmod extract --dir extracted jmods/com.example.greetings.jmod
~~~

On Windows PowerShell:

~~~powershell
jmod extract --dir extracted jmods/com.example.greetings.jmod
~~~

After running, the `extracted` directory contains the unpacked components following the JMOD structure. For example, you may see the `classes` directory along with additional directories if the archive contains native libraries, config files, or headers.

Extracting is useful when:

- Inspecting the actual class files and module descriptor.
- Viewing packaged native libraries or configuration files.
- Comparing contents between two JMOD builds.
- Investigating errors caused by missing or mispackaged resources.

Only extract into an appropriate target directory. Avoid extracting over your source tree or directories containing other project data.

## 8. Using JMOD with jlink

One of the primary purposes of JMOD is to serve as input for creating a custom runtime image with `jlink`.

For the active JDK, platform modules reside in the `jmods` directory under `JAVA_HOME`. You can combine application JMODs with the JDK modules:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:jmods" \
  --add-modules com.example.greetings \
  --launcher greetings=com.example.greetings/com.greetings.Main \
  --output greetings-image
~~~

On Windows PowerShell, the module path separator is a semicolon:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;jmods" --add-modules com.example.greetings --launcher greetings=com.example.greetings/com.greetings.Main --output greetings-image
~~~

This command:

- Locates platform modules in `JAVA_HOME/jmods`.
- Locates application modules in the `jmods` directory.
- Adds `com.example.greetings` and its required dependencies to the runtime image.
- Creates a launcher named `greetings` to invoke the main class.
- Writes the runtime image to `greetings-image`.

Run the launcher on macOS/Linux:

~~~bash
./greetings-image/bin/greetings
~~~

On Windows, run the launcher file inside `greetings-image/bin`, typically `greetings.bat`.

Output:

~~~text
Hello from JMOD
~~~

The runtime image contains the required modules and the configured launcher. JMOD remains an input to the link step; the program runs from the generated runtime image, not directly from the JMOD file.

## 9. The hash Mode and Module Hashing

The Java module system supports qualified exports: a module can export a package only to one or more named modules. Module hashing helps bind modules in this relationship by recording the hash of the dependent module in the descriptor of the required module.

The `hash` mode analyzes the module graph, identifies the leaf modules at the ends of dependency branches, and records their hashes in the modules that need binding. When the runtime or linker resolves modules, the hashes are verified; if a module's contents no longer match the recorded value, resolution may fail with an error.

### 9.1. Previewing with --dry-run

Example run from a project directory containing `jmods`:

~~~bash
jmod hash --dry-run --module-path jmods --hash-modules '.*'
~~~

`--module-path` specifies where to find the JMODs or modular JARs participating in the module graph. `--hash-modules` takes a regular expression used to select modules. `--dry-run` previews the hashes that would be recorded without modifying the archives.

### 9.2. Recording Hashes

After reviewing the dry-run output, you can omit `--dry-run`:

~~~bash
jmod hash --module-path jmods --hash-modules '.*'
~~~

This command writes hashes into the matching module archives on the module path. Since this operation modifies archive contents, run it in a controlled build process and only after the module graph has been finalized.

### 9.3. When is Hashing Needed?

Module hashing is not a mandatory step for every project. It is useful when using qualified exports and you need to bind the modules allowed to depend on the exported package. If a dependent module is replaced with different contents, a hash mismatch helps detect the change relative to the bound module.

Do not use hashing as a substitute for digital signatures, release provenance control, or full dependency security verification. It is meant for consistency across modules in the module graph.

## 10. Common jmod Options

Options are used alongside their corresponding mode:

| Option | Purpose |
|---|---|
| `--class-path path` | Takes a JAR or directory of classes to include in the JMOD |
| `--libs path` | Adds native libraries |
| `--cmds path` | Adds native commands |
| `--config path` | Adds editable configuration files |
| `--header-files path` | Adds header files |
| `--legal-notices path` | Adds legal notices |
| `--man-pages path` | Adds man pages |
| `--main-class class` | Records the main class in the module descriptor |
| `--module-version version` | Records the module version |
| `--target-platform platform` | Records the target platform of the JMOD |
| `--compress zip-N` | Sets the compression level when creating the archive |
| `--date timestamp` | Sets the entry timestamp in the archive |
| `--exclude patterns` | Excludes files matching glob/regex patterns |
| `--module-path path` | Specifies the module path; required when using `--hash-modules` |
| `--hash-modules regex` | Selects modules for computing and recording hashes |
| `--dry-run` | Previews the hash operation without modifying files |
| `--dir path` | Specifies the extraction directory |
| `@filename` | Reads options from an options file |

### 10.1. Compression Level

`--compress` accepts `zip-0` through `zip-9`:

- `zip-0` applies no compression.
- `zip-9` applies maximum compression.
- The default in JDK 21 is `zip-6`.

Higher compression can reduce archive size but increases creation and read time. Choose a compression level based on build time, distribution size, and deployment requirements.

### 10.2. Timestamps and Reproducible Builds

`--date` allows specifying entry timestamps in ISO-8601 extended offset date-time format. Fixing the timestamp helps eliminate unnecessary differences between builds when input contents have not changed.

Example:

~~~bash
jmod create --class-path mods/com.example.greetings \
  --date 2025-01-01T00:00:00Z \
  jmods/com.example.greetings.jmod
~~~

For reproducible builds, in addition to the timestamp, you also need to control input contents, JDK version, build ordering and configuration, and other metadata.

### 10.3. Excluding Files

`--exclude` accepts a comma-separated list of patterns. Each pattern can be a glob, `glob:`, or `regex:`. Use it to omit files that should not be included in the archive, such as temporary files or unnecessary build metadata.

Check the listing with `jmod list` after creation to confirm that all required contents are still packaged.

## 11. Options File

You can place `jmod` options in a text file and pass it with the `@` prefix:

File `jmod-create.args`:

~~~text
create
--class-path
mods/com.example.greetings
--main-class
com.greetings.Main
--module-version
1.0
jmods/com.example.greetings.jmod
~~~

Run:

~~~bash
jmod @jmod-create.args
~~~

An options file is useful when commands are long or when you want to keep reviewable build configuration in a repository. The file contains options and values just as you would enter them at the command prompt. Do not assume environment variables in paths will be expanded inside an options file; the JDK documentation specifies not to use environment variables for path names in this file.

## 12. Complete Practical Workflow

Using the sample module above, the workflow to create and inspect a JMOD is:

1. **Compile the module:** use `javac --module-source-path src -d mods -m com.example.greetings`.
2. **Create the JMOD directory:** create `jmods` to store the archive.
3. **Package:** use `jmod create --class-path mods/com.example.greetings` with main class/version as needed.
4. **Inspect metadata:** run `jmod describe` to verify the module name, exported packages, `requires`, and main class.
5. **Check entries:** run `jmod list` to verify class files and resources are in the archive.
6. **Extract if needed:** use `jmod extract --dir extracted` to inspect contents.
7. **Link the runtime:** use `jlink` with a module path containing the JDK JMODs and the application JMOD.
8. **Run the image:** invoke the launcher in the `bin` directory of the runtime image.
9. **Hash if needed:** only use `jmod hash` when the module design requires binding qualified exports.

## 13. Common Errors

| Symptom | Common Cause | Resolution |
|---|---|---|
| `jmod` is not recognized | JDK is not installed or `PATH` does not point to the JDK `bin` directory | Check `JAVA_HOME`, `PATH`, and `jmod --version` |
| Unable to create JMOD | Class path directory does not exist or is missing the required module descriptor/class files | Check `javac` output and the `--class-path` path |
| `jmod describe` reports an archive error | Incorrect path or the file is not a valid JMOD | Verify the file name and recreate the archive from valid module output |
| `jmod list` is missing classes/resources | Contents have not been compiled or are not inside the paths passed to the archive | Check source/build output and the path options |
| `jlink` cannot find the module | Module path does not contain the JMOD or required dependencies | Check `--module-path` and the module's `requires` directives |
| `jlink` reports the module is incompatible with the platform | JMOD contains native code or `target-platform` differs from the target machine | Build the JMOD for the target OS/architecture |
| Application does not run directly from JMOD | JMOD is not a runtime executable format | Use a modular JAR or create a runtime image with `jlink` |
| Hash mismatch during linking | Dependent module has changed compared to the hash recorded in the required module | Inspect the module graph and rebuild hashes from a consistent set of modules |

## 14. Notes on Working with JMOD

- JMOD is a compile/link-time format; do not use it in place of a modular JAR for direct execution.
- For standard Java applications, prefer modular JARs if you do not need JMOD's native/configuration sections.
- When native libraries or native commands are present, the JMOD and target platform must match the operating system, architecture, and deployment environment.
- Verify archive contents with `jmod list` and metadata with `jmod describe` after creation.
- Use `jlink` to create an executable runtime image; do not confuse the JMOD packaging step with the runtime creation step.
- `jmod hash` should only be used when the module design needs to bind modules through qualified exports.
- Do not rely on the output of a different JDK version while ignoring `jmod --help` from the toolchain actually running the build.

## 15. Summary

`jmod` provides five primary operations: `create`, `extract`, `list`, `describe`, and `hash`. `create` packages compiled modules along with native components or additional metadata; `list` and `describe` help inspect archives; `extract` unpacks them for investigation; `hash` records module-binding hashes when a qualified exports design requires them.

JMOD shines in modular build pipelines and creating runtime images with `jlink`. For most applications that need standard execution or distribution, modular JARs remain the right choice. Clarify whether your target is compile, link, or runtime before choosing a packaging format.

References: [The jmod Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jmod.html); [The jlink Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jlink.html).