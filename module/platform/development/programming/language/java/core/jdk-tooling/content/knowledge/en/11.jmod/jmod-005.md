# Extracting JMOD in Java

## 1. What is JMOD and when do you need to extract it?

JMOD is an archive format for Java platform modules and developer-packaged modules. A JMOD file contains compiled classes along with additional components a module may need, such as native libraries, native commands, configuration files, headers, or legal notices.

JMOD files typically appear in the `jmods` directory of a JDK installation, such as `java.base.jmod` or `java.sql.jmod`. Developers can also create custom JMOD files using the `jmod` tool.

**Extracting a JMOD** is the operation of unpacking all entries of a `.jmod` file into a directory on the filesystem. The `jmod` tool reads the archive and preserves the internal section structure so you can inspect or use it during development.

Common scenarios where extraction is needed:

- Inspecting class files and `module-info.class` of a module.
- Viewing configuration files, native libraries, headers, or legal notices packaged with a module.
- Investigating the contents of a JMOD before creating a runtime image with `jlink`.
- Inspecting a JMOD created by a development team or vendor.
- Retrieving a specific component for analysis with another tool after extraction.

JMOD is not a format for running applications directly. According to the JDK documentation, JMOD is used at compile time or link time; for standard module deployment, a modular JAR is usually the appropriate choice. JMOD is especially useful when a module includes native libraries or additional configuration, or when linking modules into a runtime image with `jlink`. [Oracle Documentation on the jmod Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jmod.html)

## 2. Differences between JMOD, JAR, and runtime images

These three formats serve different purposes:

| Component | Main Contents | Purpose |
|---|---|---|
| JAR | Class files, resources, and manifest | Distributing Java libraries or applications; modular JARs can be placed on the module path |
| JMOD | Class files, module descriptor, and additional sections such as native libraries, configuration, headers, legal notices | Packaging modules for compile-time or link-time use, especially with `jlink` |
| Runtime image | Linked modules together with the required runtime | Running applications on a custom-built runtime |

JMOD has its own archive structure and can contain sections that a standard JAR does not represent in the same way. Therefore, use `jmod extract` to unpack a JMOD rather than assuming it can be handled like a regular JAR.

Related commands have different responsibilities:

- `jmod list`: prints the names of the entries inside a JMOD.
- `jmod describe`: displays module information such as name, requirements, and exports.
- `jmod extract`: extracts all entries into a directory.
- `jmod create`: creates a new JMOD.
- `jlink`: links modules into a runtime image.

## 3. Finding the JMOD file to extract

JDK JMOD files are typically located in the `jmods` directory under the JDK root directory:

```text
<JDK_HOME>/
├── bin/
│   └── jmod
├── jmods/
│   ├── java.base.jmod
│   ├── java.sql.jmod
│   ├── java.xml.jmod
│   └── ...
└── lib/
```

Some examples:

- `java.base.jmod`: the core foundational module, typically containing many classes and native components.
- `java.sql.jmod`: the module related to JDBC and SQL APIs.
- `java.xml.jmod`: the module providing XML APIs.

Not every runtime installation includes a `jmods` directory. This directory usually comes with a full JDK distribution. If you cannot find it, check `JAVA_HOME` and the location of the active JDK installation.

On Windows PowerShell:

```powershell
$env:JAVA_HOME
Get-Command jmod -All
Test-Path (Join-Path $env:JAVA_HOME 'jmods\java.sql.jmod')
```

On Linux or macOS:

```bash
echo "$JAVA_HOME"
command -v jmod
ls "$JAVA_HOME/jmods/java.sql.jmod"
```

`JAVA_HOME` should point to the JDK root directory, not the `bin` directory.

## 4. jmod extract syntax

General syntax:

```bash
jmod extract [options] <jmod-file>
```

The most important option when extracting is `--dir`:

```bash
jmod extract --dir <output-directory> <module-file.jmod>
```

Meaning:

- `jmod`: invokes the JMOD tool bundled with the JDK.
- `extract`: selects archive extraction mode.
- `--dir`: specifies the target directory where extracted entries are written.
- `<module-file.jmod>`: path to the source JMOD file.

Example:

```bash
jmod extract --dir extracted/java.sql "$JAVA_HOME/jmods/java.sql.jmod"
```

The command above extracts the entries of `java.sql.jmod` into the `extracted/java.sql` directory.

`jmod extract` unpacks the entire archive contents. The command has no parameter to select a single class or entry. If you only need one file, extract into a dedicated working directory and then take the needed file from the output.

## 5. Inspecting a JMOD before extracting

Before extracting, you should verify the right file and preview the entry list.

### 5.1. Listing contents with jmod list

```bash
jmod list "$JAVA_HOME/jmods/java.sql.jmod"
```

`jmod list` prints the names of the entries inside the archive. The output may include paths such as:

```text
classes/module-info.class
classes/java/sql/...
legal/...
```

This is an illustrative example; the exact list depends on the module, JDK version, and vendor.

The `list` command only reads the entry list and does not write any contents to a directory.

### 5.2. Viewing module information with jmod describe

```bash
jmod describe "$JAVA_HOME/jmods/java.sql.jmod"
```

`jmod describe` displays module metadata, such as:

- Module name.
- Modules that it `requires`.
- Packages that are `exports`.
- Services that the module `uses` or `provides`, if any.
- Module version or hash information where applicable.

`describe` helps you understand a module at the module descriptor level; it does not replace listing or extracting the files inside.

### 5.3. When should you use list and describe?

| Question to answer | Command |
|---|---|
| Which entries does the JMOD contain? | `jmod list` |
| What is the module's name and which modules does it depend on? | `jmod describe` |
| Do you need to read or analyze the actual files? | `jmod extract` |

## 6. Practical example on Linux and macOS

This example uses the current JDK to extract the `java.sql` module.

First, verify `JAVA_HOME` and create a new, separate target directory. Choose a directory that does not exist yet to avoid mixing results with old files.

```bash
set -e

if [ -z "$JAVA_HOME" ]; then
    echo "Set JAVA_HOME to the JDK directory." >&2
    exit 1
fi

jmodFile="$JAVA_HOME/jmods/java.sql.jmod"
outDir="extracted/java.sql"

mkdir -p extracted
mkdir "$outDir"

jmod list "$jmodFile"
jmod describe "$jmodFile"
jmod extract --dir "$outDir" "$jmodFile"

find "$outDir" -type f
```

Explanation:

1. `set -e` tells the shell to stop if a command fails.
2. The `JAVA_HOME` check reports an error if the variable is not set.
3. `jmodFile` points to the source JMOD in the `jmods` directory.
4. `outDir` is the directory that will hold the extracted output.
5. `mkdir` creates the new target directory.
6. `jmod list` and `jmod describe` let you inspect the archive before extracting.
7. `jmod extract --dir` performs the extraction.
8. `find` lists the actual files after extraction.

If the JDK is installed in a different location or you need to extract a different module, update `jmodFile` accordingly. Do not change the path to a regular JAR file.

## 7. Practical example on Windows PowerShell

The following example also extracts `java.sql.jmod` from the JDK specified by `JAVA_HOME`.

```powershell
$ErrorActionPreference = 'Stop'

if (-not $env:JAVA_HOME) {
    throw 'Set JAVA_HOME to the JDK directory.'
}

$jmodFile = Join-Path $env:JAVA_HOME 'jmods\java.sql.jmod'
$outDir = '.\extracted\java.sql'

if (-not (Test-Path $jmodFile)) {
    throw "JMOD file not found: $jmodFile"
}

New-Item -ItemType Directory -Path '.\extracted' -Force | Out-Null
New-Item -ItemType Directory -Path $outDir | Out-Null

jmod list $jmodFile
jmod describe $jmodFile
jmod extract --dir $outDir $jmodFile

Get-ChildItem -Path $outDir -Recurse -File
```

Meaning:

- `$env:JAVA_HOME` reads the JDK environment variable in PowerShell.
- `Join-Path` builds the path to the source JMOD.
- `Test-Path` confirms that the source file exists.
- `New-Item` creates the target directory.
- `jmod extract` unpacks the archive into the chosen directory.
- `Get-ChildItem -Recurse -File` lists the files after extraction.

This example creates a new target directory. If `.\extracted\java.sql` already exists, choose a new directory name or check the existing contents before running to avoid mixing with previous output.

## 8. Directory structure after extraction

JMOD organizes contents into sections. Depending on the module, only some sections appear; not every JMOD contains all directories.

Common sections:

| Directory after extraction | Contents |
|---|---|
| `classes/` | Java class files, including `module-info.class` if the module has a descriptor |
| `conf/` | Editable configuration files |
| `include/` | Header files, typically related to native interfaces |
| `legal/` | Module licenses and legal notices |
| `lib/` | Native libraries |
| `bin/` | Native commands or executables bundled with the module |
| `man/` | Manual pages |

Example of a structure you may see:

```text
extracted/
└── java.base/
    ├── classes/
    │   ├── module-info.class
    │   └── java/
    │       └── lang/
    │           └── Object.class
    ├── conf/
    ├── include/
    ├── legal/
    ├── lib/
    ├── bin/
    └── man/
```

This is an illustrative structure for a module with many types of components. A smaller module such as `java.sql` may only have `classes/` and `legal/`, or a different set of sections depending on the distribution.

Each section serves a distinct role:

- `classes/` contains bytecode and the module descriptor. This is usually the part to inspect when studying APIs or modules.
- `conf/` may contain configuration files used by the runtime or module components.
- `include/` contains headers for native/JNI work.
- `legal/` stores license information and legal notices.
- `lib/` and `bin/` may contain platform-dependent native code.
- `man/` contains manual documentation.

## 9. Verifying results after extraction

Once the command completes, verify that the expected files are present and that paths preserve the proper section layout.

### 9.1. Checking on Linux/macOS

```bash
find extracted/java.sql -type f
test -f extracted/java.sql/classes/module-info.class
```

If the module has `module-info.class`, the `test` command exits successfully when the file exists.

### 9.2. Checking on Windows PowerShell

```powershell
Get-ChildItem -Path '.\extracted\java.sql' -Recurse -File
Test-Path '.\extracted\java.sql\classes\module-info.class'
```

`Test-Path` returns `True` if the checked path exists.

### 9.3. Cross-checking against the original list

You can run again:

```bash
jmod list "$JAVA_HOME/jmods/java.sql.jmod"
```

Match the entries in the list against the extracted paths. For example, the entry `classes/module-info.class` should correspond to the file `classes/module-info.class` inside the target directory.

This cross-check confirms the structure and presence of files. If you need byte-for-byte content verification, use per-file checksums or an appropriate comparison tool; checking file names alone does not prove the contents are unaltered.

## 10. Working with other JMOD modules

You can extract any JMOD that the current JDK tool can read, not just `java.sql.jmod`.

Example with `java.xml.jmod`:

```bash
jmod list "$JAVA_HOME/jmods/java.xml.jmod"
jmod describe "$JAVA_HOME/jmods/java.xml.jmod"
jmod extract --dir extracted/java.xml "$JAVA_HOME/jmods/java.xml.jmod"
```

Example with `java.base.jmod`:

```bash
jmod list "$JAVA_HOME/jmods/java.base.jmod"
jmod extract --dir extracted/java.base "$JAVA_HOME/jmods/java.base.jmod"
```

`java.base.jmod` is typically large and contains many classes and platform components. If you are only learning how extraction works, start with a smaller module so the output is easier to inspect.

For a project-built JMOD, use its specific file path:

```bash
jmod list build/jmods/com.example.module.jmod
jmod describe build/jmods/com.example.module.jmod
jmod extract --dir extracted/com.example.module build/jmods/com.example.module.jmod
```

Replace the module name and output path in the example with your actual artifact.

## 11. Can you extract a single entry?

`jmod extract` unpacks all entries in the JMOD. The `--dir` option only selects the target directory; it is not an entry filter.

If you only need a single class or resource:

1. Use `jmod list` to find the exact entry path.
2. Extract the JMOD into a separate working directory.
3. Copy the needed file from the corresponding section, typically `classes/` or `conf/`.
4. Preserve the package structure or path if downstream tools require it.

Do not extract into your project directory or the active JDK directory just to grab one file. A module can contain thousands of classes and native components.

## 12. Analyzing extracted contents

After extraction, you can use other JDK tools to inspect each type of file.

### 12.1. Inspecting the module descriptor

`module-info.class` describes the module name, dependencies, exports, opens, uses, and provides. You can view module information before extracting with:

```bash
jmod describe "$JAVA_HOME/jmods/java.sql.jmod"
```

This is a convenient way to read module metadata without manually parsing class files.

### 12.2. Analyzing class files

Class files under `classes/` can be inspected with `javap`. For example, after extracting the `java.sql` module, JDBC API class files may reside under `classes/java/sql/`.

```bash
javap -classpath extracted/java.sql/classes java.sql.Connection
```

This command tells `javap` to look up the class from the directory containing the package root. It displays class and method signatures; add `-c` if you need to inspect method bytecode where appropriate.

### 12.3. Inspecting native libraries

Files in `lib/` or `bin/` may be native components tied to a specific operating system and architecture. Extracting only writes them to disk; it does not convert binaries for another platform and does not automatically install or register them on the system.

Verify the target platform and module origin before using extracted native binaries.

## 13. How are jmod extract and jlink related?

`jlink` creates a runtime image from a set of modules and their required dependencies. JMOD is one of the input formats used in this linking process.

Conceptual workflow:

```text
JMOD archive
    |
    | jmod list / describe
    v
Inspect contents and module metadata
    |
    | jmod extract
    v
Extracted sections for inspection
    |
    | jlink uses modules from module path
    v
Runtime image
```

Extraction is an operation for inspecting and retrieving files into a directory. It is not a required step before running `jlink`; `jlink` can work directly with a module path containing JMOD files.

Example of linking a runtime image from modules included in the JDK:

```bash
jlink --module-path "$JAVA_HOME/jmods" --add-modules java.sql --output sql-runtime
```

On Windows PowerShell:

```powershell
jlink --module-path "$env:JAVA_HOME\jmods" --add-modules java.sql --output sql-runtime
```

This command creates a runtime image containing the `java.sql` module and its required dependencies. It illustrates the link-time purpose of JMOD; you do not need to extract modules before invoking `jlink`.

## 14. Safety and compatibility notes

When extracting a JMOD, keep the following in mind:

- **Archive source:** prefer JMOD files from the JDK or trusted repositories.
- **Target directory:** choose a new, separate directory to avoid mixing with or overwriting existing files.
- **Size:** large modules such as `java.base` can extract many classes and native binaries.
- **Platform:** native libraries and native commands may only target a single operating system or architecture.
- **JDK version:** use `jmod` from a JDK compatible with the format and module being processed; if errors occur, check the tool version and archive source.
- **Do not run binaries just because they were extracted:** extracting does not prove that a binary is safe or compatible with the current machine.

Extracting does not execute Java classes or native commands inside the archive. However, it writes data to the filesystem, so you should still choose a safe working directory and verify the source file.

## 15. Common errors when extracting JMODs

| Symptom | Common Cause | Resolution |
|---|---|---|
| `jmod` is not recognized | `PATH` does not include the JDK `bin` directory, or only a runtime is installed | Check `JAVA_HOME`, `PATH`, and the JDK installation |
| `.jmod` file not found | Incorrect path or the JDK lacks a `jmods` directory | Verify the path and ensure the proper JDK distribution is used |
| Invalid archive | File is not a valid JMOD, is corrupted, or is an incomplete download | Re-acquire the artifact from a trusted source and verify its checksum |
| Cannot write to output directory | Missing write permissions or unsuitable target directory | Choose a user-managed directory with write permissions |
| Output mixed with old files | Reused an extract directory that already had contents | Choose a new, empty target directory |
| Classes not found in output | Looking in the wrong section or module does not contain the expected classes | Cross-check `jmod list` and look under `classes/` |
| `conf/`, `lib/`, or `include/` missing | Module does not have those sections | Check the entry list; not every module contains every section |
| Native binary does not run | Binary is incompatible with the OS or architecture | Verify the target platform and use the matching distribution |
| Wanted to extract one file but got many | `jmod extract` unpacks the entire archive | Extract to a separate directory and take the needed entry |

When an error occurs, keep the source JMOD file intact and inspect it with `jmod list`, `jmod describe`, and `jmod --version`. Avoid modifying the original archive to work around an unclear extraction error.

## 16. Standard workflow

When you need to extract a JMOD in practice:

1. Identify the JDK and the path to the `.jmod` file.
2. Check `jmod --version` to confirm which tool version you are using.
3. Use `jmod list` to confirm the archive contains the expected entries.
4. Use `jmod describe` to view module metadata when needed.
5. Choose a new, empty, writable output directory.
6. Run `jmod extract --dir <output-dir> <module.jmod>`.
7. List the extracted files and cross-check them against `jmod list`.
8. Analyze `module-info.class`, class files, configuration, or native files with the appropriate tools.
9. If the final goal is to build a runtime image, consider passing the module path directly to `jlink` instead of extracting first.
10. Record the JDK, module, source path, and output directory so others can reproduce the operation.

## 17. Summary

`jmod extract` is the command used to unpack the entire contents of a JMOD archive into a specified directory.

Key commands to remember:

- `jmod list <file.jmod>`: view the entry list.
- `jmod describe <file.jmod>`: view module metadata.
- `jmod extract --dir <output-dir> <file.jmod>`: extract all entries.
- `jmod --version`: check the tool version.
- `jmod --help`: view syntax and options for the current JDK.

A JMOD can contain classes, configuration files, legal notices, headers, and native binaries. After extraction, check the relevant sections, verify the output, and use the right tools to inspect each file type. Keep in mind that JMOD is designed for compile-time or link-time use; modular JARs are generally better suited for standard module distribution, while `jlink` is used to build custom runtime images.

**Official reference:** [The jmod Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jmod.html).