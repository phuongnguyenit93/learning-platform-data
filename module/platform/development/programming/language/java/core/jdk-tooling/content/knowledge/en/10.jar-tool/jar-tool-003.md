# Listing a JAR with the jar Tool

## 1. What Is JAR Listing?

JAR (Java ARchive) is a ZIP-based packaging format commonly used to distribute class files, resources, and metadata for a Java application or library. A JAR can contain:

- `.class` bytecode files.
- Resources such as `.properties`, images, XML, JSON, or text files.
- Package directories corresponding to the class structure.
- A manifest at `META-INF/MANIFEST.MF`.
- Signatures and metadata for package signing.
- Nested JARs inside another JAR, depending on how the application is packaged.

**Listing a JAR** is the operation of displaying the list of entries (files and directories) stored inside an archive. This operation helps verify whether the package contains the expected classes, resources, manifest, or libraries.

The `jar` tool included with the JDK supports this operation directly from the Terminal or Command Prompt. The list command only reads entry names and metadata; it does not extract the entire archive and does not run the application.

## 2. Basic Syntax of jar --list

Using the modern syntax:

```bash
jar --list --file app.jar
```

Where:

- `jar` invokes the JDK's Java Archive management tool.
- `--list` requests displaying the list of entries in the archive.
- `--file app.jar` specifies the JAR file to read.

These two options have corresponding short forms:

```bash
jar -tf app.jar
```

Here, `-t` stands for list and `-f` stands for file. This is the short syntax commonly seen in older documentation and scripts.

You can view the help for your installed JDK version:

```bash
jar --help
```

Options may be added across JDK versions. When working across multiple machines or multiple JDK versions, check the help for the actual environment.

## 3. What Entries Does a JAR Contain?

For example, an application JAR might have the following structure:

```text
app.jar
├── META-INF/
│   └── MANIFEST.MF
├── com/
│   └── example/
│       ├── Main.class
│       └── service/
│           └── UserService.class
└── config/
    └── app.properties
```

Meaning of the entries:

- `META-INF/MANIFEST.MF`: archive metadata, which may declare `Main-Class`, manifest version, package information, or other metadata.
- `com/example/Main.class`: bytecode of the `com.example.Main` class.
- `com/example/service/UserService.class`: bytecode of a class in a subpackage.
- `config/app.properties`: a resource read by the application at runtime.

Entry names inside a JAR typically use forward slashes `/` as directory separators, even when the JAR is created or used on Windows.

An archive can also contain separate directory entries such as `com/` and `com/example/`. Therefore, the listing may display both directories and files. Not all packaging tools store directory entries in the same way.

## 4. Hands-On Example: Creating and Listing a JAR

This example uses Java 17 or later. Create the file `src/com/example/Hello.java`:

```java
package com.example;

public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello, JAR!");
    }
}
```

Create the output directory. On Linux/macOS:

```bash
mkdir -p out
```

On Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force out
```

Compile from the project root directory:

```bash
javac --release 17 -d out src/com/example/Hello.java
```

This command creates the class file at `out/com/example/Hello.class`.

Create a JAR with the main class declared in the manifest:

```bash
jar --create --file app.jar --main-class com.example.Hello -C out .
```

Meaning:

- `--create`: creates a new archive.
- `--file app.jar`: sets the output archive name.
- `--main-class com.example.Hello`: declares the main class in the manifest.
- `-C out .`: changes to the `out` directory before adding all contents of that directory to the JAR.

Now list the contents:

```bash
jar --list --file app.jar
```

Representative output might include:

```text
META-INF/
META-INF/MANIFEST.MF
com/
com/example/
com/example/Hello.class
```

The order of entries and whether directory entries are displayed may vary depending on how the archive was created. The key thing to verify is that the JAR contains `META-INF/MANIFEST.MF` and the `com/example/Hello.class` class.

You can run the JAR to verify the main class:

```bash
java -jar app.jar
```

Stdout:

```text
Hello, JAR!
```

The list command verifies the archive contents; the run command verifies that the JVM can launch the application according to the manifest and current runtime.

## 5. Listing with Detailed Information Using --verbose

If you only use `--list`, the output is mainly entry names. Add `--verbose` to view additional details:

```bash
jar --list --verbose --file app.jar
```

Short form:

```bash
jar -tvf app.jar
```

Verbose mode typically displays:

- Entry size.
- Date and time recorded in the archive.
- Entry name.

Illustrative output example:

```text
     0 Thu Jan 01 00:00:00 UTC 1970 META-INF/
    55 Thu Jan 01 00:00:00 UTC 1970 META-INF/MANIFEST.MF
     0 Thu Jan 01 00:00:00 UTC 1970 com/
     0 Thu Jan 01 00:00:00 UTC 1970 com/example/
   425 Thu Jan 01 00:00:00 UTC 1970 com/example/Hello.class
```

The sizes and timestamps above are formatting examples only, not fixed values. They depend on the contents and when the archive was created.

Verbose listing is useful when you:

- Want to check whether a resource was actually packaged.
- Compare the size of a class or resource between two artifacts.
- Find empty entries or files with unusual sizes.
- Inspect entry timestamps when investigating the packaging process.

An entry's size does not necessarily equal the JAR file size on disk because ZIP can compress data and the archive also contains metadata.

## 6. Listing a JAR in Another Directory or a Dependency Library

If the JAR is not in the current directory, pass the path to the archive:

```bash
jar --list --file build/libs/application.jar
```

On Windows PowerShell:

```powershell
jar --list --file .\build\libs\application.jar
```

To inspect a dependency library:

```bash
jar --list --file lib/commons-library.jar
```

`jar --list` reads the archive directly, so there is no need to add the JAR to the classpath. The classpath is only needed when running an application or when a tool needs to resolve classes from different locations.

When there are multiple JARs, check the exact path and artifact name. Two JARs may contain the same class but belong to different library versions.

## 7. Quickly Finding an Entry in the Listing

`jar --list` does not provide built-in pattern-filtering syntax like a standalone query. You can pipe the output through shell filtering tools.

Linux/macOS, find entries in the `com/example` package:

```bash
jar --list --file app.jar | grep 'com/example'
```

Windows PowerShell:

```powershell
jar --list --file app.jar | Select-String 'com/example'
```

Windows Command Prompt:

```bat
jar --list --file app.jar | findstr "com/example"
```

Find configuration files ending in `.properties` on Linux/macOS:

```bash
jar --list --file app.jar | grep '\.properties$'
```

These filter commands only process the text printed by `jar`. They do not modify the JAR and do not remove entries from the archive.

If entry names contain special characters or require more precise analysis, you can save the listing to a file and use an appropriate text-processing tool.

## 8. Checking the Manifest in a JAR

When listing a JAR that has a manifest, you will usually see the entry:

```text
META-INF/MANIFEST.MF
```

However, `jar --list` only shows the entry name; it does not display the manifest contents.

A manifest may contain attributes such as:

```text
Manifest-Version: 1.0
Main-Class: com.example.Hello
```

`Main-Class` specifies the main class that `java -jar app.jar` will launch. If the JAR has no manifest or lacks a valid `Main-Class`, `java -jar` cannot run in this manner.

If the `unzip` utility is available, you can read the manifest without extracting the entire JAR:

```bash
unzip -p app.jar META-INF/MANIFEST.MF
```

If `unzip` is not available, you can use `jar --extract --file app.jar META-INF/MANIFEST.MF` in a separate working directory and then open the extracted file. The extract command writes files to disk, unlike the list operation which only reads the archive.

## 9. JARs with Resources and Package Directories

Not every entry in a JAR is a class file. JARs often contain resources for the application to read at runtime.

Example:

```text
app.jar
├── META-INF/MANIFEST.MF
├── com/example/Main.class
├── config/app.properties
├── messages/messages_vi.properties
└── images/logo.png
```

When listing, also check for the resources your application needs:

```bash
jar --list --file app.jar
```

If `config/app.properties` does not appear, the resource may not have been placed in the input directory during packaging, or the build configuration may have excluded it.

Resource paths inside a JAR are typically accessed from the classpath using their corresponding path, such as `config/app.properties`. The presence of an entry in the archive does not guarantee that the code reading the resource uses the right API or the right class loader.

## 10. Multi-Release JARs and Java-Version-Specific Entries

A multi-release JAR allows a single archive to contain alternative class versions for different Java runtimes. Additional entries are typically placed under:

```text
META-INF/versions/9/
META-INF/versions/11/
META-INF/versions/17/
```

Example:

```text
META-INF/MANIFEST.MF
com/example/Feature.class
META-INF/versions/11/com/example/Feature.class
META-INF/versions/17/com/example/Feature.class
```

When listing a JAR, paths under `META-INF/versions/` help identify that the archive contains Java-version-specific content.

For a JAR to be treated as a multi-release JAR, the manifest must declare the attribute:

```text
Multi-Release: true
```

Merely seeing the `META-INF/versions/` directory is not enough to conclude that the runtime will select the alternative entries. Both the manifest and the archive structure need to be checked.

`jar --list` displays the entries stored in the archive; it does not explain which class the runtime will select for a specific Java version.

## 11. Nested JARs Inside a JAR

Some applications package dependencies as JARs inside the main archive. For example, the structure of a Spring Boot application might contain:

```text
BOOT-INF/
├── classes/
│   └── com/example/Main.class
└── lib/
    ├── library-a.jar
    └── library-b.jar
```

When running:

```bash
jar --list --file application.jar
```

you will see entries such as `BOOT-INF/lib/library-a.jar`. The `jar` tool only lists the inner JAR as an entry of the outer archive; it does not automatically open and recursively list the entries of nested JARs.

To inspect a nested dependency JAR, you need to extract that entry into a separate directory and then run `jar --list` on the extracted file. For applications with custom packaging structures, consult the documentation of the framework or plugin that created the archive to know where classes and dependencies are located.

## 12. How Does Listing a JAR Differ from Extracting and Analyzing Classes?

Different tools serve different purposes:

| Tool or Operation | Purpose |
|---|---|
| `jar --list --file app.jar` | View entry names in the archive |
| `jar --list --verbose --file app.jar` | View entries along with size and timestamp |
| `jar --extract --file app.jar` | Extract archive contents to a directory |
| `javap -classpath app.jar com.example.Main` | View the structure and signatures of a class |
| `javap -classpath app.jar -c com.example.Main` | View method bytecode |
| `jdeps app.jar` | Analyze class and module dependencies |
| `jarsigner -verify app.jar` | Verify JAR signatures |

Listing a JAR is appropriate when the question is "What files does the archive contain?". If the question is "How was a method compiled?", use `javap`. If you need to determine dependencies, use `jdeps`.

## 13. Checking Signatures and Integrity

An entry listing does not prove that a JAR is trustworthy or that its signature is valid. An archive may list normally while still containing unwanted content.

If the JAR is signed, use `jarsigner` to verify the signature:

```bash
jarsigner -verify -verbose -certs app.jar
```

Review the verification output and certificate warnings according to your project's security policy. Verifying signatures is different from simply viewing entry names.

When receiving a JAR from an external source, verify the release source, checksum, or signature through official channels. Do not run a JAR merely because `jar --list` can read its contents.

## 14. Common Errors When Listing a JAR

| Symptom | Common Cause | Resolution |
|---|---|---|
| `jar` is not recognized | JDK is not installed or PATH does not include the JDK `bin` directory | Check `JAVA_HOME`, PATH, and `jar --help` |
| `java.nio.file.NoSuchFileException` | Incorrect path or JAR filename | Check the current directory and archive path |
| Expected class is missing | Packaged from the wrong root directory or class was not compiled | Check compiler output and the JAR creation command |
| Manifest is missing | Archive was created without a manifest | Check packaging configuration or generate an appropriate manifest |
| `java -jar` fails to run even though the JAR has classes | Manifest is missing or declares an invalid `Main-Class` | Read the manifest contents and verify the main class name |
| Listing shows nested JARs but not the classes inside them | `jar --list` does not recursively open nested archives | Extract the nested JAR and list it separately |
| Java-version-specific entries are missing | Archive contains no versioned entries or you are inspecting the wrong artifact | Check `META-INF/versions/` and verify the right JAR file |
| Verbose output is too long | Archive contains many dependencies and resources | Filter output with `grep`, `Select-String`, or `findstr` |
| JAR is readable but the application still fails | Listing does not check logic, runtime dependencies, or signatures | Run tests, use `jdeps`, `jarsigner`, and check runtime logs |

If `jar` reports an invalid archive or corrupted ZIP data, re-obtain the artifact from a trusted source and verify its checksum. You should not directly edit a corrupted archive and treat it as a reliable build.

## 15. Practical Workflow for Inspecting a JAR

When receiving or building a JAR, you can follow this sequence:

1. Identify the exact path and version of the artifact to inspect.
2. Run `jar --list --file <file.jar>` to view all entries.
3. Check whether the manifest, class files, and key resources are present.
4. Use `jar --list --verbose --file <file.jar>` if you need entry sizes and timestamps.
5. Search for specific packages or resources using shell filtering tools.
6. If you see nested JARs, extract them separately and list them again.
7. If you see `META-INF/versions/`, inspect the manifest to confirm a multi-release JAR.
8. Use `javap` to inspect specific classes and `jdeps` to analyze dependencies when needed.
9. Use `jarsigner -verify` if signature verification is required.
10. Run tests or smoke tests to confirm the application works on the target runtime.

This workflow helps distinguish packaging issues from compilation, dependency, or runtime errors.

## 16. Summary

`jar --list` is the fundamental command for viewing entries inside a Java Archive without extracting the entire archive.

Commands to remember:

- `jar --list --file app.jar`: list entry names.
- `jar -tf app.jar`: short form of the list operation.
- `jar --list --verbose --file app.jar`: also display sizes and timestamps.
- `jar --list --file path/to/app.jar`: list an archive at another path.
- `jar --list --file app.jar | grep ...`: filter the listing on Linux/macOS.
- `jar --list --file app.jar | Select-String ...`: filter the listing in PowerShell.
- `jar --list --file app.jar | findstr ...`: filter the listing in Windows Command Prompt.

Listing a JAR helps verify archive structure, manifests, classes, and resources. When you need to inspect bytecode, analyze dependencies, verify signatures, or run the application, combine the corresponding JDK tools to verify the exact aspect you need to check.
