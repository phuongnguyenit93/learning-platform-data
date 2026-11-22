# Listing JMOD Contents with jmod list

JMOD (Java Module) is an archive format provided by the JDK to package module contents during development and runtime linking. A JMOD file can contain class files, commands, native libraries, configuration files, headers, documentation, and legal notices. The `jmod list` tool lists the entries in a JMOD file, helping you verify whether the archive contains all the required components.

This guide covers how to use `jmod list` in JDK 17 and later, how to locate the JDK's JMOD files, how to create a sample JMOD for inspection, how to read the output, and how to distinguish listing from describing or extracting an archive.

## 1. What Is JMOD and When Should You Use It?

JMOD is an archive format for modules in the JDK development and modular application workflow. Compared to a standard JAR, JMOD can store more types of content, not just Java classes and resources.

A JMOD can contain content groups such as:

| Content Group | Role |
|---|---|
| `classes` | Module class files and resources |
| `bin` | Commands or executables bundled with the module |
| `conf` | Configuration files |
| `include` | Headers for native integration |
| `legal` | Copyright and license notices |
| `lib` | Native libraries or supporting libraries |
| `man` | Command manual pages |

Not every JMOD contains all of the groups above. The actual contents depend on the module and how the archive was created. Entries are typically displayed with a group prefix, such as `classes/module-info.class` or `classes/java/lang/String.class`.

JMOD is primarily used as input to `jlink` to create runtime images. It is not a general-purpose distribution format for direct execution with `java -jar`, and the Java launcher does not use JMOD files as modular JARs on the module path.

## 2. The jmod Tool and list Syntax

`jmod` is a command-line tool included with the JDK. The basic syntax for listing an archive is:

~~~text
jmod list <jmod-file>
~~~

Example:

~~~powershell
jmod list "$env:JAVA_HOME/jmods/java.base.jmod"
~~~

The command reads the specified JMOD and prints the list of entries inside it. It does not extract or modify the archive.

If the `JAVA_HOME` environment variable is not set, use the full path to the JDK installation directory, for example:

~~~powershell
jmod list "C:/Program Files/Java/jdk-17/jmods/java.base.jmod"
~~~

On Linux or macOS:

~~~bash
jmod list "$JAVA_HOME/jmods/java.base.jmod"
~~~

Make sure `JAVA_HOME` points to a JDK that has a `jmods` directory. Some stripped-down runtime installations do not include this directory because they do not contain the full set of JDK tools and module archives.

## 3. Listing Built-in JDK JMODs

The JDK typically stores standard module archives in the `jmods` directory directly under `JAVA_HOME`.

In PowerShell, list the JMOD file names:

~~~powershell
Get-ChildItem "$env:JAVA_HOME/jmods" -Filter *.jmod |
    Select-Object -ExpandProperty Name
~~~

Then list the contents of a specific module, such as `java.base`:

~~~powershell
jmod list "$env:JAVA_HOME/jmods/java.base.jmod"
~~~

`java.base` is the foundational module of the Java Platform, containing core classes such as `java.lang`, `java.util`, and other base packages. This JMOD can be very large, so the listing output may include thousands of entries.

To filter for specific entries in PowerShell:

~~~powershell
jmod list "$env:JAVA_HOME/jmods/java.base.jmod" |
    Select-String "module-info.class|java/lang/String.class"
~~~

On Linux/macOS, use `grep`:

~~~bash
jmod list "$JAVA_HOME/jmods/java.base.jmod" |
    grep -E 'module-info.class|java/lang/String.class'
~~~

Filtering the output only helps you quickly inspect a subset of the list. If you need to verify the entire archive, save and review the full output or inspect the relevant entry groups directly.

## 4. Creating a Sample JMOD for Practice

You can create a small module, compile it into class files, and package it into a JMOD. This example uses Java 17 or later.

Project structure:

~~~text
project/
├── src/
│   ├── module-info.java
│   └── com/
│       └── example/
│           └── hello/
│               └── Main.java
├── mods/
└── build/
~~~

Contents of `src/module-info.java`:

~~~java
module com.example.hello {
    exports com.example.hello;
}
~~~

Contents of `src/com/example/hello/Main.java`:

~~~java
package com.example.hello;

public class Main {
    public static void main(String[] args) {
        String name = args.length == 0 ? "JMOD" : String.join(" ", args);
        System.out.println("Hello, " + name + "!");
    }
}
~~~

From the `project` root directory, create the output directories and compile the module:

~~~powershell
New-Item -ItemType Directory -Force -Path mods/com.example.hello, build | Out-Null
javac -d mods/com.example.hello src/module-info.java src/com/example/hello/Main.java
~~~

Create the JMOD:

~~~powershell
jmod create --class-path mods/com.example.hello --main-class com.example.hello.Main --module-version 1.0.0 build/com.example.hello.jmod
~~~

In the command above:

- `create` instructs `jmod` to create a new JMOD.
- `--class-path` specifies the directory containing the compiled module class files and resources.
- `--main-class` records the main class in the module metadata.
- `--module-version` records the module version.
- The final argument is the path to the JMOD file to be created.

List the contents of the newly created JMOD:

~~~powershell
jmod list build/com.example.hello.jmod
~~~

The abbreviated output looks like:

~~~text
classes/module-info.class
classes/com/example/hello/Main.class
~~~

The exact entries depend on the module's contents. Because this example only contains a module descriptor and one Java class, the list mainly consists of these two class files.

## 5. Reading and Understanding jmod list Output

Each line of output represents one entry in the JMOD. Paths are typically grouped by content section.

Example:

~~~text
classes/module-info.class
classes/com/example/hello/Main.class
~~~

This can be interpreted as:

- `classes/` is the module's classes and resources group.
- `module-info.class` is the compiled module descriptor.
- `com/example/hello/Main.class` is the bytecode for the `com.example.hello.Main` class.

If the JMOD was created with native libraries or configuration files, the list may include entries under corresponding groups such as `lib/` or `conf/`. If the module includes commands, headers, or legal notices, those entries also appear under the groups used by the packaging tool.

`jmod list` only lists entry names and their locations within the archive. It does not display full file contents, explain dependencies, or verify that the application will run successfully. Use the appropriate tool for deeper questions.

## 6. Distinguishing list, describe, and extract

The `jmod` tool provides subcommands for different purposes:

| Command | Purpose | When to Use |
|---|---|---|
| `jmod list file.jmod` | List entries | Confirm which files are in the archive |
| `jmod describe file.jmod` | Display module description | View module name, requires, exports, main class, and metadata |
| `jmod extract --dir out file.jmod` | Extract contents | Inspect or process actual files |
| `jmod create ... file.jmod` | Create archive | Package a module from classes and resources |
| `jmod hash ...` | Record dependency hashes by configuration | Support specialized module linking workflows |

Example of describing the newly created module:

~~~powershell
jmod describe build/com.example.hello.jmod
~~~

Example of extracting into a separate directory:

~~~powershell
jmod extract --dir extracted build/com.example.hello.jmod
~~~

After extracting, you can inspect the files in the `extracted` directory using OS tools. `extract` writes files to disk; `list` only reads the entry list, making it more suitable for quick checks.

Do not use `jar --list` as a substitute for `jmod list` when working with JMOD files. JAR and JMOD serve different packaging workflows; use the JDK-provided tool intended for each format.

## 7. Inspecting the Module Descriptor and Class Files

An important entry in a JMOD is `classes/module-info.class`. It contains the module information generated by the compiler from `module-info.java`.

You can view the module description with:

~~~powershell
jmod describe build/com.example.hello.jmod
~~~

You can use `javap` to inspect the compiled descriptor after extracting:

~~~powershell
javap -v extracted/classes/module-info.class
~~~

The verbose output of `javap` shows the module name, required modules, exported or opened packages, and declared providers.

For the sample module, you can run the program from the compiled module directory using:

~~~powershell
java --module-path mods --module com.example.hello/com.example.hello.Main
~~~

Output:

~~~text
Hello, JMOD!
~~~

This command runs the module from the exploded module directory in `mods`, not directly from the JMOD. If you want to use the JMOD to build a custom runtime, include the archive on `jlink`'s module path as part of the runtime linking workflow.

## 8. JMOD and jlink

A key reason to create and inspect JMODs is to use them in the `jlink` workflow. `jlink` builds a runtime image from input modules and their required dependencies.

For example, if the JMOD is located in the `build` directory and the JDK has a `jmods` directory, on Windows you can create a runtime image as follows:

~~~powershell
jlink --module-path "$env:JAVA_HOME/jmods;build" --add-modules com.example.hello --output runtime
~~~

On Linux/macOS, the module path separator is a colon:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:build" --add-modules com.example.hello --output runtime
~~~

`jlink` reads the module archives and links the selected modules into a runtime image. Before running it, ensure the JMOD has a valid module descriptor, the correct module name, and all dependent modules present.

JMODs can contain native code or platform-specific data. When packaging a module with native components, build and test on the appropriate target operating system and architecture.

## 9. Filtering and Saving Entry Lists

For large JMODs, the output can be long. You can save the list to a file for later review or comparison.

PowerShell:

~~~powershell
jmod list "$env:JAVA_HOME/jmods/java.base.jmod" |
    Out-File -Encoding utf8 build/java-base-entries.txt
~~~

Linux/macOS:

~~~bash
jmod list "$JAVA_HOME/jmods/java.base.jmod" > build/java-base-entries.txt
~~~

You can filter entries by group:

~~~powershell
Select-String "^classes/" build/java-base-entries.txt
Select-String "^lib/" build/java-base-entries.txt
Select-String "^conf/" build/java-base-entries.txt
~~~

To compare contents between two JMOD versions, generate entry lists from each archive and use an appropriate diff tool. Note that JDK version changes can significantly alter the list of classes, resources, or native libraries; comparing entries alone does not explain the reason for the changes.

Do not modify a JMOD file directly by replacing entries inside the archive. If you need to change its contents, recreate the JMOD from updated input components.

## 10. Common Errors When Using jmod list

| Symptom | Common Cause | Resolution |
|---|---|---|
| `Error: file not found` | Incorrect JMOD path or the JMOD does not exist | Check `JAVA_HOME`, the `jmods` directory, and the file name |
| `jmod is not recognized` or command not found | JDK `bin` is not on PATH | Invoke using the full path or configure PATH to include the JDK |
| `Error: invalid JMOD file` | Corrupted file, wrong format, or not a valid JMOD | Obtain the archive from a trusted source or recreate it with `jmod create` |
| Expected class is missing from the list | Class was not compiled or not included on class-path when creating the JMOD | Check `javac` output and the `--class-path` argument |
| Module descriptor not found | Module was not compiled as an explicit module or JMOD was created without `module-info` | Check `module-info.java` and `module-info.class` in the input directory |
| Path with spaces causes command failure | Path is not enclosed in quotes | Enclose the entire path in quotes |
| Confusing JMOD with JAR when running an application | Using a JMOD in place of a modular JAR | Use a modular JAR with the Java launcher, or use a JMOD as input to `jlink` |
| Output is too large or hard to read | Listing a module with many entries | Filter with `Select-String`/`grep` or redirect output to a file |

When an error occurs, identify which step failed: locating the JMOD, reading the archive, creating the JMOD, describing the module, extracting, or runtime linking. Use `jmod list` to check entries; use `jmod describe` to view metadata; use `jmod extract` only when you need to inspect actual files.

## 11. Checklist for Listing JMODs

- [ ] Using the `jmod` command from the correct JDK.
- [ ] The path to the JMOD exists and points to the intended archive.
- [ ] Using the correct syntax `jmod list <jmod-file>`.
- [ ] Verified key entries such as `classes/module-info.class` and required classes/resources.
- [ ] Distinguished the entry list from module metadata contents.
- [ ] Using `jmod describe` when needing to view dependencies, exports, or main class.
- [ ] Using `jmod extract` only when extracting files is actually needed.
- [ ] Not confusing JMOD with JAR when running via the Java launcher.
- [ ] If the JMOD contains native content, accounted for the target OS and architecture.
- [ ] If used for `jlink`, verified the module descriptor and required dependencies.

`jmod list` is the direct way to inspect the entries packaged inside a JMOD. Start with the right archive path, read the entry groups to confirm classes and resources, and use `jmod describe` or `jmod extract` when more detail is needed. Clearly distinguish JMOD from modular JAR so you choose the right tool for packaging, running applications, and building runtime images.
