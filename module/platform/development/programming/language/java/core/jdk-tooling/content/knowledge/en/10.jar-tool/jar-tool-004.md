# Extracting JARs with the jar Tool

JAR (Java Archive) is a ZIP-based archive format commonly used to package Java bytecode, resources, manifests, and metadata for an application or library. Extracting a JAR is the operation of unpacking entries inside the archive into files and directories on the file system.

The `jar` tool included with the JDK supports listing, creating, updating, and extracting archives. When you need to inspect library contents, retrieve configuration files, recover resources, or investigate the structure of an artifact, you can use `jar --extract` without writing a separate extraction program.

## 1. What Does a JAR Contain?

A JAR is an archive with an entry structure. Each entry has a relative path name inside the archive and can be a file or a directory. For example:

~~~text
customer-app.jar
├── META-INF/
│   └── MANIFEST.MF
├── com/
│   └── acme/
│       ├── app/
│       │   └── Main.class
│       └── model/
│           └── Customer.class
└── config/
    └── application.properties
~~~

Common types of content:

- **Class files:** Java bytecode with the `.class` extension.
- **Resources:** configuration files, templates, images, data, or other content that the application reads at runtime.
- **Manifest:** the `META-INF/MANIFEST.MF` file, which may contain version information, the main class, the class path, or archive attributes.
- **Service metadata:** files in `META-INF/services/` used with the service provider mechanism.
- **Module metadata:** such as `module-info.class` in a modular JAR.
- **Signature metadata:** signature files in `META-INF/` for signed artifacts.

Extraction only unpacks the entries into files. It does not decompile bytecode into Java source code, does not install the library into the JDK, and does not automatically extract nested JARs inside the archive.

## 2. Inspecting a JAR Before Extraction

Before extracting contents, you should verify that the archive file exists and inspect the list of entries:

~~~bash
jar --list --file customer-app.jar
~~~

Equivalent short-form options:

~~~bash
jar -tf customer-app.jar
~~~

Meaning:

- `--list` or `-t`: list entries in the archive.
- `--file` or `-f`: specify the JAR file.
- `-v`: display more details, including entry information such as size and timestamp when supported.

You can list in verbose mode:

~~~bash
jar --list --verbose --file customer-app.jar
~~~

or:

~~~bash
jar -tvf customer-app.jar
~~~

Entry names typically use forward slashes `/` as directory separators, even when running on Windows. For example, the entry `com/acme/app/Main.class` is the name to pass to `jar` when you only want to extract that class.

If the archive is large, listing first helps identify the exact entries to retrieve and avoids extracting unnecessary data.

## 3. Basic Extraction Syntax

Long-form syntax:

~~~bash
jar --extract --file archive.jar
~~~

Short-form syntax:

~~~bash
jar -xf archive.jar
~~~

Where:

- `--extract` or `-x`: extract entries from the archive.
- `--file` or `-f`: specify the archive to read.
- If no destination directory is specified, entries are extracted relative to the terminal's current working directory.

For example:

~~~bash
jar --extract --file customer-app.jar
~~~

After running this, the directory structure inside the JAR is created in the current directory. If the archive contains `com/acme/app/Main.class`, the corresponding path is created under the working directory.

The short form can be combined with verbose mode to display the entries being processed:

~~~bash
jar -xvf customer-app.jar
~~~

Avoid extracting an archive into a project directory that contains important files if you do not yet know its contents. List the entries and choose a dedicated destination directory to keep the output easy to control.

## 4. Extracting to a Destination Directory with --dir

To separate archive contents from the current working directory, use the `--dir` option:

~~~bash
jar --extract --file customer-app.jar --dir extracted
~~~

Entries are written into the `extracted` directory while preserving the relative directory structure inside the JAR.

For example, if the archive contains:

~~~text
com/acme/app/Main.class
com/acme/model/Customer.class
config/application.properties
~~~

the result will look like:

~~~text
extracted/
├── com/
│   └── acme/
│       ├── app/Main.class
│       └── model/Customer.class
└── config/
    └── application.properties
~~~

On Linux/macOS, you can create the destination directory first:

~~~bash
mkdir -p extracted
jar --extract --file customer-app.jar --dir extracted
~~~

On Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force extracted | Out-Null
jar --extract --file customer-app.jar --dir extracted
~~~

You can use an absolute path for `--dir` if a script runs from different working directories. For projects shared across a team, a relative path from the project root is usually easier to reproduce.

## 5. Extracting a Single Entry or a Group of Entries

You do not always need to extract the entire archive. You can pass the entry names to extract after the options:

~~~bash
jar --extract --file customer-app.jar --dir extracted com/acme/model/Customer.class
~~~

The command above extracts only the `com/acme/model/Customer.class` entry into the destination directory. If you need the manifest:

~~~bash
jar --extract --file customer-app.jar --dir extracted META-INF/MANIFEST.MF
~~~

You can specify multiple entries in a single invocation:

~~~bash
jar --extract --file customer-app.jar --dir extracted com/acme/app/Main.class com/acme/model/Customer.class config/application.properties
~~~

On PowerShell, you can also place the entries on the same line:

~~~powershell
jar --extract --file customer-app.jar --dir extracted com/acme/app/Main.class com/acme/model/Customer.class config/application.properties
~~~

Entry names must match the paths listed in the archive. Use `/` in entry names instead of changing them to `\` for Windows. If you pass a nonexistent name, `jar` cannot extract that entry and will report an error or that the requested item was not found depending on the version.

For a directory entry, check the archive listing to identify its child entries. Do not assume that passing only a directory name will always behave identically across all archives; the reliable approach is to specify the file entries you need to extract.

## 6. Complete Hands-On Example: Creating, Listing, and Extracting a JAR

This example creates a small Java application, packages it into an executable JAR, then extracts and runs the extracted classes.

Create the source structure:

~~~text
jar-extract-demo/
└── src/
    └── com/
        └── acme/
            ├── app/
            │   └── Main.java
            └── model/
                └── Customer.java
~~~

File `src/com/acme/model/Customer.java`:

~~~java
package com.acme.model;

public class Customer {
    private final String name;

    public Customer(String name) {
        this.name = name;
    }

    public String name() {
        return name;
    }
}
~~~

File `src/com/acme/app/Main.java`:

~~~java
package com.acme.app;

import com.acme.model.Customer;

public class Main {
    public static void main(String[] args) {
        Customer customer = new Customer("Linh");
        System.out.println("Customer: " + customer.name());
    }
}
~~~

### Step 1: Compile the Source Code

From the `jar-extract-demo` root directory, create the output directory and compile:

~~~bash
mkdir -p out
javac -d out src/com/acme/model/Customer.java src/com/acme/app/Main.java
~~~

On PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac -d out src/com/acme/model/Customer.java src/com/acme/app/Main.java
~~~

After compilation, the class files are located under `out/com/acme/`.

### Step 2: Create the JAR

Package the classes and declare the main class in the manifest:

~~~bash
jar --create --file customer-app.jar --main-class com.acme.app.Main -C out .
~~~

The `-C out .` option tells `jar` to change into the `out` directory when collecting contents to package; the dot represents all contents inside that directory. As a result, the JAR contains package paths such as `com/acme/app/Main.class`, without an extra root directory named `out`.

### Step 3: Check the Entry List

~~~bash
jar --list --file customer-app.jar
~~~

The archive will contain entries corresponding to `META-INF/MANIFEST.MF`, `com/acme/app/Main.class`, and `com/acme/model/Customer.class`. The archive may also contain directory entries such as `com/` or `META-INF/`.

### Step 4: Run the JAR Before Extracting

~~~bash
java -jar customer-app.jar
~~~

Output:

~~~text
Customer: Linh
~~~

### Step 5: Extract into a Separate Directory

~~~bash
mkdir -p extracted
jar --extract --file customer-app.jar --dir extracted
~~~

On PowerShell:

~~~powershell
New-Item -ItemType Directory -Force extracted | Out-Null
jar --extract --file customer-app.jar --dir extracted
~~~

After extraction, the main structure is:

~~~text
extracted/
├── META-INF/
│   └── MANIFEST.MF
└── com/
    └── acme/
        ├── app/Main.class
        └── model/Customer.class
~~~

### Step 6: Verify the Extracted Contents

On Windows PowerShell, you can view the manifest with:

~~~powershell
Get-Content extracted/META-INF/MANIFEST.MF
~~~

On Linux/macOS, use:

~~~bash
cat extracted/META-INF/MANIFEST.MF
~~~

The manifest has the `Main-Class: com.acme.app.Main` attribute because the JAR was created with the `--main-class` option.

You can run the classes directly from the extracted directory:

~~~bash
java -cp extracted com.acme.app.Main
~~~

Output:

~~~text
Customer: Linh
~~~

The output is the same as running the JAR. This confirms that the class entries were extracted with the correct package structure and can be loaded by the JVM from the `extracted` directory.

## 7. Extracting the Manifest and Inspecting Metadata

The manifest is a special text file located at:

~~~text
META-INF/MANIFEST.MF
~~~

It can be extracted individually:

~~~bash
jar --extract --file customer-app.jar --dir extracted META-INF/MANIFEST.MF
~~~

Common attributes:

| Attribute | Meaning |
|---|---|
| Manifest-Version | Manifest format version. |
| Main-Class | Main class when running with `java -jar`. |
| Class-Path | Dependency locations declared for the JAR application according to manifest rules. |
| Implementation-Title | Name of the implementation component. |
| Implementation-Version | Version of the implementation component. |
| Specification-Version | Specification version declared by the component. |

Attribute names in the manifest are case-insensitive according to manifest rules. Values can span multiple lines following manifest continuation rules, so you should not parse them manually by assuming each attribute always fits on a single line.

Extracting the manifest only lets you read its metadata. It does not automatically install dependencies or fix the classpath. If the JAR declares `Class-Path`, those paths must still exist and be resolved according to the application's rules at runtime.

## 8. Extracting Resources and the META-INF Directory

JARs often contain resources that the application reads through the class loader. For example:

~~~text
config/application.properties
templates/email.html
META-INF/services/com.acme.spi.PaymentProvider
~~~

You can extract a resource:

~~~bash
jar --extract --file customer-app.jar --dir extracted config/application.properties
~~~

Or extract service metadata:

~~~bash
jar --extract --file customer-app.jar --dir extracted META-INF/services/com.acme.spi.PaymentProvider
~~~

Resources retain their entry names and directory structure. When inspecting their contents, keep in mind that the resource file's encoding is determined by the application or file format itself; extraction does not convert encodings.

A JAR can contain another JAR file as an entry, such as `lib/dependency.jar`. When extracting the outer archive, that nested JAR remains a single file. To inspect its contents, you must run a separate `jar` command on the extracted JAR file.

## 9. Entry Paths and Working Directory

Entry names inside a JAR are relative paths according to archive conventions, not absolute paths on the machine. For example:

~~~text
com/acme/model/Customer.class
META-INF/MANIFEST.MF
config/app.properties
~~~

Key points to remember:

- Entry paths use `/` as the directory separator across all operating systems.
- Do not include Windows drive letters such as `C:\` in entry names.
- Do not add a leading `/` to entry names when passing relative paths.
- A relative path for `--dir` is resolved from the current working directory.
- If `--dir` is not specified, contents are extracted into the working directory.

To avoid targeting the wrong directory, check the working directory before running the command:

~~~bash
pwd
~~~

On PowerShell:

~~~powershell
Get-Location
~~~

If a script runs from multiple locations, you can use an absolute destination path or compute the path from the project root directory.

## 10. Multi-Release Archives and Modules

Some JARs have a multi-release structure, containing Java-version-specific alternative classes under `META-INF/versions/`. When listing or extracting, review all entries to understand which versions the archive actually contains. Do not confuse a class under `META-INF/versions/17/` with the class at the package root; they serve the multi-release JAR mechanism and are selected by the JVM based on the runtime version.

A modular JAR may contain `module-info.class`. When extracted, this file is unpacked like a normal class entry. You can inspect the module descriptor of a modular JAR with:

~~~bash
jar --describe-module --file modular-library.jar
~~~

If the archive has no explicit module descriptor, the JDK may describe it as an automatic module based on metadata and the archive name. Extraction does not change how a module is identified or automatically configure the module path for an application.

## 11. Signed JARs and Modifying Contents After Extraction

A JAR may contain signature metadata in `META-INF/`, such as `.SF`, `.RSA`, `.DSA`, or `.EC` files. These files relate to the archive's digital signature.

Extraction only reads the archive and creates copies of entries on the file system. If you modify the contents and repackage the archive, the old signature no longer validates the new archive contents. Do not treat keeping the signature files in the extracted directory as proof that the new archive is still valid.

You can verify the signature of the original archive with:

~~~bash
jarsigner -verify -verbose -certs customer-app.jar
~~~

If you need to redistribute the archive after modifying its contents, perform a re-signing process using an organization-authorized key and verify the new signature according to your release policy.

## 12. Safety When Extracting Archives

Before extracting a JAR received from an unfamiliar source:

1. List entries with `jar --list --file` to see what paths the archive intends to create.
2. Extract into a separate, newly created directory that contains no important data.
3. Check entry names, file counts, and archive size if the source is untrusted.
4. Do not immediately execute extracted files just because they came from a JAR.
5. Do not write custom archive extraction code without output path validation and resource limits.
6. If you need to modify or repackage a signed JAR, re-evaluate its signature status and release process.

An archive can contain a very large number of entries or large files. Bulk extraction can consume significant disk space. For untrusted archives, use a separate temporary directory and check available disk space before extracting.

## 13. Common Errors and Troubleshooting

| Symptom | Common Cause | Resolution |
|---|---|---|
| `NoSuchFileException` or unable to open archive | Wrong JAR path or terminal is in a different working directory. | Check the working directory and file path; try an absolute path. |
| `jar` is not recognized | JDK is not on `PATH` or using a runtime-only environment. | Check `javap --version`, `javac -version`, and `PATH`; install/select an appropriate JDK. |
| Requested entry not found | Entry name has the wrong package path or wrong letter casing. | List the archive and copy the exact entry name, using `/`. |
| Files appear in an unexpected directory | `--dir` was omitted or working directory was misunderstood. | Use `--dir extracted` and check `pwd`/`Get-Location`. |
| Missing classes when running extracted files | Only part of the JAR was extracted or external dependencies are missing. | Extract all required entries and configure the classpath/module path. |
| Nested JAR inside is still not extracted | `jar` only extracts direct entries of the archive being opened. | Run `jar` separately on the extracted nested JAR file. |
| Signature is no longer valid after modification | Contents changed while old signature metadata remained. | Re-sign the new archive using an appropriate release process. |
| Extraction creates more files than expected | Archive contains resources, metadata, multi-release entries, or other directories. | Inspect the listing first and extract only the needed entries. |

If you need to check the syntax supported by your current JDK version:

~~~bash
jar --help
~~~

Options can vary across JDK versions; consult the help output of the tool you are running rather than relying on examples for a different version.

## 14. Recommended JAR Extraction Workflow

When you receive a JAR to inspect or extract, follow these steps in order:

1. Identify the archive path and working directory.
2. View the entry list using `jar --list --file`.
3. Decide whether to extract everything or only specific entries.
4. Create a dedicated destination directory.
5. Use `jar --extract --file archive.jar --dir destination`.
6. Inspect the directory structure and key files such as the manifest, classes, and resources.
7. If you need to run the extracted classes, use the destination directory as the classpath and provide any missing dependencies.
8. If the archive is signed, verify the signature of the original file and do not reuse the old signature after modifying contents.
9. Record the command and artifact source if the extracted output is used in an investigation or build process.

Extracting a JAR is a straightforward operation, but it requires controlling paths and entry structure. Understanding `--list`, `--extract`, `--file`, `--dir`, and how to select specific entries helps you retrieve the exact contents from an archive, inspect Java artifacts, and investigate packaging issues systematically.
