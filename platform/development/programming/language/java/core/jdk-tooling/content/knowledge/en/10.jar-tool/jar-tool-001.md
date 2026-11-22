# The jar Command in the JDK

JAR (Java ARchive) is a ZIP-based archive format used to bundle class files, resources, metadata, and sometimes a module descriptor into a single file. The **jar** tool included with the JDK helps create, list, update, extract, and validate JARs. It is a packaging tool; it does not compile Java source code, nor does it guarantee on its own that a JAR can run standalone.

This article covers common jar operations in Java projects, from packaging class files to creating executable JARs, modular JARs, and multi-release JARs. The command examples use modern JDK syntax; check `jar --help` on your installed JDK because some options are only available in specific versions.

## 1. What Is a JAR?

A JAR file is a ZIP archive with structural and metadata conventions tailored for the Java ecosystem. It can contain:

- Compiled .class files.
- Resources such as properties, XML, JSON, images, or configuration files.
- A META-INF directory containing the manifest and other metadata.
- A module descriptor module-info.class at the archive root if it is a modular JAR.
- Digital signatures and related files if the archive is signed.

Example JAR structure:

~~~text
app.jar
├── META-INF/
│   └── MANIFEST.MF
└── com/
    └── example/
        └── Main.class
~~~

JARs are commonly used to:

- Distribute Java libraries.
- Package applications to run with the Java launcher.
- Package modules for the Java Platform Module System (JPMS).
- Store resources that applications read via a class loader.
- Distribute different class versions in a multi-release JAR.

### A JAR Does Not Mean an Executable JAR

A JAR is just an archive. To run with the `java -jar` command, the archive must have an entry point declared in the manifest, usually the `Main-Class` attribute. The application also needs all required dependency libraries packaged appropriately or configured on the classpath.

A library JAR can omit `Main-Class` and still be completely valid for use by other applications.

## 2. General Syntax of jar

Common syntax:

~~~bash
jar [OPTIONS] [FILES]
~~~

The jar tool has the following main operation modes:

| Mode | Long Option | Short Option | Purpose |
|---|---|---|---|
| Create | --create | -c | Create a new archive |
| List | --list | -t | List archive contents |
| Update | --update | -u | Add or replace entries in an archive |
| Extract | --extract | -x | Extract all or specific entries |
| Describe module | --describe-module | -d | Display the module descriptor or automatic module name |
| Validate | --validate | No corresponding short form | Validate certain archive constraints, especially for multi-release JARs |

Common options:

- --file or -f: archive file name.
- --verbose or -v: print details of processed entries.
- --manifest or -m: use the provided manifest file.
- --main-class or -e: declare the main class for a launchable JAR.
- --module-version: record the module version when creating a modular JAR or updating a suitable JAR.
- -C: change the working directory for subsequent files in the jar command.
- --no-compress or -0: store entries without compression.
- --date: set the timestamp for entries on JDKs that support it.
- --release: place subsequent files into the versioned directory of a multi-release JAR.

Do not combine options arbitrarily. Some options are only valid in create/update or extract mode. You can view the exact syntax for your current JDK with:

~~~bash
jar --help
jar --version
~~~

## 3. Preparing a Java Example

Create a small program:

~~~text
jar-demo/
└── src/
    └── com/
        └── example/
            └── Main.java
~~~

Contents of `src/com/example/Main.java`:

~~~java
package com.example;

public class Main {
    public static void main(String[] args) {
        String name = args.length == 0 ? "Java" : args[0];
        System.out.println("Hello, " + name + "!");
    }
}
~~~

Compile the source code with JDK 17 or later:

~~~bash
javac --release 17 -d out src/com/example/Main.java
~~~

After compilation, the class file is located at:

~~~text
out/
└── com/
    └── example/
        └── Main.class
~~~

Notes:

- `javac` produces class files; `jar` only packages existing files.
- The `-d out` option sets the output directory for the compiler.
- The package structure is created under `out`.
- When using `-C out` in the `jar` command, paths inside the archive start from the `out` directory, so the entry will be `com/example/Main.class`.

## 4. Creating a JAR with --create

Create an archive containing the entire contents of the `out` directory:

~~~bash
jar --create --file app.jar -C out .
~~~

Short form:

~~~bash
jar -c -f app.jar -C out .
~~~

Explanation:

- `--create` requests creating an archive.
- `--file app.jar` sets the output file name.
- `-C out` changes into the `out` directory before picking up subsequent files.
- The dot `.` refers to all contents in the current directory after changing into it with `-C`.

To print entries during creation:

~~~bash
jar --create --verbose --file app.jar -C out .
~~~

The `-C` option is very useful for controlling paths inside the archive. If you run `jar` from the project directory and pass `out/com/example/Main.class` directly without `-C`, the entry may include the `out/` prefix. In that case, the class loader may fail to find the class under its expected package name.

### Creating an Archive from Specific Files

You can specify individual files to include in the archive:

~~~bash
jar --create --file selected.jar -C out com/example/Main.class
~~~

The command above packages only the `Main.class` file. If the application needs additional resources or dependent classes, they must be included in the archive or provided via another dependency mechanism.

### Creating an Uncompressed JAR

By default, `jar` compresses entries using ZIP compression. You can store entries without compression using:

~~~bash
jar --create --no-compress --file app-stored.jar -C out .
~~~

Skipping compression can be helpful in certain workflows that need to reduce decompression or repackaging overhead, though the archive is usually larger. Measure on your actual workload before choosing this option.

## 5. Listing and Inspecting JAR Contents

Use `--list` to view the list of entries:

~~~bash
jar --list --file app.jar
~~~

Short form:

~~~bash
jar -tf app.jar
~~~

Use `--verbose` to view additional metadata such as size and timestamp:

~~~bash
jar --list --verbose --file app.jar
~~~

For example, the newly created archive should contain entries similar to:

~~~text
META-INF/
META-INF/MANIFEST.MF
com/
com/example/
com/example/Main.class
~~~

The order or some intermediate directories listed may vary depending on the tool version and how the archive was created. What matters is that entry paths match the package and class name.

You can use `jar --list` before releasing to check:

- Whether class files are in the correct package paths.
- Whether required resources are packaged.
- Whether build files, logs, or local configuration files were accidentally included in the archive.
- Whether the manifest appears as expected.
- Whether the archive contains duplicate file names or unwanted entries.

## 6. Extracting a JAR with --extract

Extract the entire archive into the current directory:

~~~bash
jar --extract --file app.jar
~~~

Short form:

~~~bash
jar -xf app.jar
~~~

Specify an extraction directory on JDKs that support the `--dir` option:

~~~bash
jar --extract --file app.jar --dir extracted
~~~

Or use `-C` to specify the target directory:

~~~bash
jar --extract --file app.jar -C extracted
~~~

You can extract specific entries by naming them after the options:

~~~bash
jar --extract --file app.jar com/example/Main.class
~~~

If the target directory already has files with the same name, the default extract mode may overwrite them. The `--keep-old-files` or `-k` option on supporting JDKs can preserve existing files.

Only extract trusted archives, or inspect the contents and entry paths before extracting into sensitive directories. Avoid extracting archives from unknown sources directly into project or system directories.

## 7. Updating a JAR with --update

`--update` adds new entries or replaces entries with the same name in an existing archive. For example, after creating `app.jar`, you can add a `resources` directory:

~~~text
resources/
└── app.properties
~~~

Update:

~~~bash
jar --update --file app.jar -C resources .
~~~

If the archive already has an entry at the same path, that entry is updated with the new content. Other entries are preserved.

You can use verbose mode to observe the changes:

~~~bash
jar --update --verbose --file app.jar -C resources .
~~~

Keep in mind:

- `--update` requires an existing archive.
- Entry names and paths are resolved relative to `jar`'s current working directory after the `-C` option.
- The update command is not an entry deletion tool. To remove contents, you typically recreate the archive from the desired set of files.
- When updating an executable JAR, do not lose or accidentally alter the required manifest.
- If replacing class files, ensure related classes and resources remain compatible.

## 8. Manifest and Executable JARs

A **Manifest** is a metadata file typically located at `META-INF/MANIFEST.MF`. A manifest consists of `name: value` attributes split across lines; each section is separated by a blank line.

A minimal manifest might look like:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.Main

~~~

The trailing blank line terminates the main section. The manifest uses UTF-8 with specific formatting and line-length rules; if you have long values or special characters, let the `jar` tool generate the attributes rather than concatenating strings in an invalid format.

### Creating an Executable JAR with --main-class

With the `out` directory containing `Main.class`:

~~~bash
jar --create --file app.jar --main-class com.example.Main -C out .
~~~

Then run:

~~~bash
java -jar app.jar
~~~

Output:

~~~text
Hello, Java!
~~~

Pass application arguments after the JAR name:

~~~bash
java -jar app.jar "JDK tooling"
~~~

Output:

~~~text
Hello, JDK tooling!
~~~

### Using a Custom Manifest

You can provide a custom manifest:

~~~bash
jar --create --file app-manifest.jar --manifest manifest.mf -C out .
~~~

If `manifest.mf` has `Main-Class`, the JAR can be run with `java -jar`. You can inspect the manifest after creation by listing or extracting the archive and reading `META-INF/MANIFEST.MF`.

Avoid both providing a manifest with `Main-Class` and setting a different `--main-class` value unless intentional. Keep a single, clear source of truth for the entry point configuration.

### Dependencies of an Executable JAR

Declaring `Main-Class` only specifies the main class; it does not automatically bundle all libraries that the application needs.

An application can handle dependencies by:

- Packaging libraries in a structure supported by the application or launcher.
- Using the manifest `Class-Path` attribute to reference other JARs using relative URL rules.
- Using a build tool to create an executable/fat JAR via a plugin mechanism.
- Using the module path if the application is organized as named modules.

When running with `java -jar`, the launcher uses the classpath determined for JAR mode and the manifest; do not rely on `-cp` as a normal way to add to the classpath in the same command.

## 9. Modular JARs and the --describe-module Command

A **modular JAR** contains `module-info.class` at the root of the archive. The module descriptor declares the module name, `requires`, `exports`, `opens`, and other module information.

Example `module-info.java`:

~~~java
module com.example.app {
    exports com.example.app;
}
~~~

After compiling the module, suppose the output is in `mods/com.example.app` and contains `module-info.class` at the root of that directory. You can package it with:

~~~bash
jar --create --file app-module.jar --main-class com.example.app.Main -C mods/com.example.app .
~~~

The `--main-class` option records the main class for a suitable modular JAR. The `--module-version` option can record the module version:

~~~bash
jar --create --file app-module.jar \
  --main-class com.example.app.Main \
  --module-version 1.0 \
  -C mods/com.example.app .
~~~

Inspect the module descriptor:

~~~bash
jar --describe-module --file app-module.jar
~~~

This command displays module information read from the archive. If the JAR has no module descriptor, the tool may report that no descriptor was found or display automatic module information depending on the case and JDK version.

Run the modular JAR via the module path:

~~~bash
java --module-path app-module.jar -m com.example.app
~~~

For a modular JAR with `Main-Class`, running the module still relies on the module path and module name. For regular JARs without a module descriptor, `java -jar` and the classpath are more common.

## 10. Multi-release JARs

A **Multi-release JAR** allows a single archive to contain versions of classes or resources tailored for different Java versions. The runtime selects the entry matching the running Java version, provided the manifest marks the archive as multi-release.

Example structure:

~~~text
multi-release.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── versions/
│       └── 21/
│           └── com/example/Feature.class
└── com/
    └── example/
        └── Feature.class
~~~

Classes at the root of the archive are the base version. Entries under `META-INF/versions/N` are used for runtime version N and above according to multi-release JAR rules.

You can create a multi-release JAR with the `--release` option. For example, if the `base` directory contains the base classes and the `java21` directory contains the replacement classes for Java 21:

~~~bash
jar --create --file library.jar -C base . --release 21 -C java21 .
~~~

The `--release` option places subsequent files into the corresponding versioned directory in the archive. The `jar` tool sets the necessary multi-release metadata when creating the archive this way.

Inspect the structure:

~~~bash
jar --list --file library.jar
~~~

On supporting JDKs, you can validate the consistency of a multi-release JAR:

~~~bash
jar --validate --file library.jar
~~~

Validation focuses on API consistency rules across versions in a multi-release JAR; it does not replace running tests on each target Java version.

## 11. Creating Reproducible Archives

In a build pipeline, two builds from the same source can produce different JARs if metadata such as timestamps, entry order, or manifest contents change.

Principles to improve reproducibility:

- Use the same JDK version and build tools.
- Control the list of input files and exclude temporary files.
- Generate a deterministic manifest.
- Do not package logs, caches, or environment-dependent data.
- If the JDK supports `--date`, set the archive timestamp to a standardized, agreed-upon value.
- Verify artifact checksums after building.

Example using a fixed timestamp on a JDK that supports the `--date` option:

~~~bash
jar --create --file app.jar --date 2024-01-01T00:00:00Z -C out .
~~~

Verify the `--date` syntax in `jar --help` for your JDK. Full reproducibility also depends on input ordering, the compiler, the manifest, resource filtering, and other build steps.

## 12. JAR, Digital Signing, and Integrity Verification

The `jar` tool packages archives; it does not perform digital signing itself. The JDK provides related tools:

- **keytool** manages keystores, key pairs, and certificates.
- **jarsigner** signs JARs and verifies signatures.
- **jar** creates or manipulates archive contents.

Example of verifying a JAR's signature:

~~~bash
jarsigner --verify --verbose --certs app.jar
~~~

Verification results should be evaluated alongside the certificate source, trust policy, and distribution process. A JAR with a valid signature does not automatically mean the code inside is safe; signatures primarily help authenticate the source and detect modifications compared to the signed contents.

When updating the contents of a signed JAR, existing signatures may become invalid. After making changes, re-sign according to your release process and re-verify the artifact.

## 13. Common Errors

### Could not find or load main class

Possible causes include an incorrect `Main-Class`, class files not in the expected package path, or an executable JAR missing its main class. Check the manifest and entry list with `jar --list`.

### Invalid or corrupt jarfile

The archive may be corrupted, incompletely downloaded, or not a valid JAR/ZIP file. Check the size and checksum, and rebuild the artifact from a trusted build source.

### No main manifest attribute

The JAR has no `Main-Class` attribute. Recreate it with `--main-class` or provide a manifest containing `Main-Class` if the goal is to run it with `java -jar`.

### NoClassDefFoundError or ClassNotFoundException

A required dependency or class is missing from the classpath/module path at runtime. `Main-Class` does not automatically package dependencies. Check the manifest `Class-Path`, launcher configuration, or how the executable JAR was built.

### Resource Not Found

The resource may have been packaged at the wrong path or omitted from the archive. Check entries with `jar --list` and load the resource via the class loader using the corresponding path.

### Old Contents Remain After Updating

The `--update` command adds or replaces entries; it does not delete entries that are no longer in the source directory. If you want the archive to contain only the new set of files, recreate the archive from scratch with the exact input list.

### Modular JAR Cannot Be Resolved

Check whether `module-info.class` is at the root of the JAR, as well as the module name, `requires`, `exports`, and module path. Use `jar --describe-module` and `java --show-module-resolution` to help diagnose.

### Invalid Signature After Updating

Modifying archive contents can invalidate old signatures. Re-sign with `jarsigner` according to your release process and verify after signing.

## 14. jar Usage Checklist

- Compile source code before packaging; `jar` does not replace `javac`.
- Choose the right input files and directories to avoid packaging unnecessary data.
- Use `-C` to control entry paths inside the archive.
- Inspect contents with `jar --list` before distributing.
- Declare `Main-Class` when the JAR needs to run with `java -jar`.
- Clearly identify application dependencies; `Main-Class` does not automatically include dependent libraries in the JAR.
- Keep `module-info.class` at the archive root when creating a modular JAR.
- Use `--release` properly when creating a multi-release JAR.
- Validate the archive with `jar --describe-module` or `--validate` when appropriate.
- Do not treat `--update` as a delete operation; recreate the archive if you need to remove entries.
- Re-sign and verify the JAR after modifying the contents of a signed archive.
- Keep the JDK version and build process consistent so artifacts are reproducible.

## 15. Key Terms to Remember

| Term | Meaning |
|---|---|
| JAR | A ZIP-based archive following Java conventions |
| Entry | A file or directory stored in an archive |
| Manifest | Metadata in META-INF/MANIFEST.MF |
| Main-Class | Attribute specifying the main class for an executable JAR |
| Executable JAR | A JAR that can be launched with java -jar |
| Modular JAR | A JAR with module-info.class at the archive root |
| Multi-release JAR | A JAR containing class/resource versions per Java release |
| --create | Create a new archive |
| --list | List entries in an archive |
| --update | Add or replace entries |
| --extract | Extract entries |
| -C | Select the working directory for subsequent files |
| jarsigner | Tool for signing and verifying JAR signatures |
| keytool | Tool for managing keystores and certificates |

Remember the three core roles: **`javac` compiles class files, `jar` packages class files and resources, and `java` launches the application from the JAR if the archive has a suitable entry point configuration**. Checking entries, the manifest, dependencies, and the module descriptor before releasing helps prevent most Java packaging and execution errors.