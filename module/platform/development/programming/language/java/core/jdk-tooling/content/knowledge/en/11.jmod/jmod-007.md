# Native Commands in JMOD

In the Java Development Kit, a **native command** is an operating-system-level executable program, such as a command-line utility written in C/C++, Rust, or another natively compiled language. It runs directly on the target operating system and CPU architecture, rather than being a Java class launched by the JVM.

The `jmod` tool supports packaging native commands into a JMOD using the `--cmds` option:

```text
jmod create --cmds <path> <module>.jmod
```

This option only places pre-built command files into the archive. It does not compile C/C++ code, does not convert binaries across Windows/Linux/macOS, and does not make a JMOD a directly executable program. JMOD is a compile-time/link-time format; to include a module and its native components in a runtime image, the standard workflow uses `jlink`.

## 1. How Does a Native Command Differ from a Java Main Class and a Native Library?

These three concepts are related but serve different roles:

| Component | Example | Role | How to Package in JMOD |
|---|---|---|---|
| Java class | `com.example.Main.class` | Bytecode loaded and executed by the JVM | `--class-path` |
| Native command | `bin/report-helper`, `report-helper.exe` | Program executed directly on the operating system | `--cmds` |
| Native library | `libreport.so`, `report.dll`, `libreport.dylib` | Library loaded by a native program or Java/JNI | `--libs` |

A Java module can declare a `main` class in its module descriptor using `--main-class`. This is metadata for the module's Java entry point. It does not replace `--cmds`.

Similarly, a native library used with JNI or linked by a native executable is not a command. If a command requires shared libraries, package those libraries into the native libraries section using `--libs` when appropriate, while ensuring that the library's system dependencies are present on the target machine.

For example:

- `jmod --cmds native-commands`: adds an executable such as `report-helper`.
- `jmod --libs native-libs`: adds a native library such as `libreport.so`.
- `jmod --class-path mods/com.example.tools`: adds the module descriptor and Java class files.

## 2. Location of Native Commands in a JMOD

JMOD divides its contents into sections by data type. Native commands are stored in the `bin/` section. A JMOD can contain sections such as:

| Section in JMOD | Contents |
|---|---|
| `classes/` | Module descriptor and Java class files |
| `bin/` | Native commands |
| `lib/` | Native libraries |
| `conf/` | Configuration files |
| `include/` | Header files |
| `legal/` | Legal notices |
| `man/` | Man pages |

Example structure after packaging:

```text
com.example.tools.jmod
├── classes/
│   ├── module-info.class
│   └── com/example/tools/Main.class
└── bin/
    └── report-helper
```

The path `bin/report-helper` is an entry inside the JMOD. When using `jmod list`, the section name appears in the entry list. When extracting with `jmod extract`, the contents are recreated under the target directory according to their corresponding sections.

A JMOD can also store native libraries, configurations, headers, and documentation. These parts help the module carry the components needed for linking a runtime image or deploying according to the product's workflow.

## 3. Preparing Native Commands Before Packaging

`jmod` is not a native compiler. Before invoking `--cmds`, the command must be built using a toolchain suitable for the target platform.

For example, a project might prepare:

```text
native-commands/
└── report-helper
```

In this Linux example, `report-helper` is a binary built for Linux and the target CPU architecture. On Windows, executable files typically have the `.exe` extension; macOS and Linux have their own native packaging and linking conventions.

Checks before packaging:

1. The command has been successfully compiled with a toolchain for the target operating system.
2. The CPU architecture matches the runtime image to be created.
3. The native libraries that the command depends on have been identified.
4. The command has appropriate execute permissions on the target platform.
5. Command names do not conflict with other tools or commands included in the runtime image.
6. The command can be tested standalone in a compatible environment before packaging.

On Linux, you can check the binary format with a system tool such as `file`:

```sh
file native-commands/report-helper
```

You can inspect the dynamic libraries required by an executable using an appropriate operating system tool, such as `ldd` on some Linux systems. Only run this inspection tool on trusted binaries and in an appropriate environment.

A Linux x86-64 binary cannot automatically run on Windows or macOS just because it is inside a JMOD. JMOD stores the built binary; it does not convert executable formats or instruction sets.

## 4. Creating a JMOD with a Native Command

Suppose the Java module has been compiled into:

```text
mods/
└── com.example.tools/
    ├── module-info.class
    └── com/
        └── example/
            └── tools/
                └── Main.class
```

Directory containing the native command:

```text
native-commands/
└── report-helper
```

Create the directory to hold the JMOD:

```sh
mkdir -p jmods
```

Create the JMOD for Linux AMD64:

```sh
jmod create \
  --class-path mods/com.example.tools \
  --cmds native-commands \
  --target-platform linux-amd64 \
  jmods/com.example.tools.jmod
```

Explanation:

- `create`: creates a new JMOD archive.
- `--class-path mods/com.example.tools`: reads the module descriptor and compiled class files.
- `--cmds native-commands`: copies the contents of the native command directory into the command section of the JMOD.
- `--target-platform linux-amd64`: declares the platform for which the JMOD is created.
- `jmods/com.example.tools.jmod`: output archive path.

`--cmds` copies the contents of the specified path, including subdirectories and their contents. If you specify a directory containing multiple commands, all matching contents are added to the archive. You can use `--exclude` when you need to exclude files using supported patterns.

On Windows, for example, with a binary built specifically for Windows AMD64:

```powershell
New-Item -ItemType Directory -Force jmods
jmod create --class-path mods\com.example.tools --cmds native-commands --target-platform windows-amd64 jmods\com.example.tools.jmod
```

Do not use a Linux AMD64 JMOD for a Windows AMD64 or macOS ARM64 runtime image. If distributing for multiple platforms, build the native command and create the corresponding JMOD for each platform.

## 5. Verifying That the Command Was Added to the JMOD

After creating the archive, use `jmod list`:

```sh
jmod list jmods/com.example.tools.jmod
```

Illustrative output:

```text
classes/module-info.class
classes/com/example/tools/Main.class
bin/report-helper
```

The actual entry names depend on the module contents and the command directory provided. What you need to confirm is that the command is located under the `bin/` section.

You can extract it to inspect:

```sh
jmod extract \
  --dir extracted \
  jmods/com.example.tools.jmod
```

After extraction, the structure looks like:

```text
extracted/
├── classes/
│   ├── module-info.class
│   └── com/example/tools/Main.class
└── bin/
    └── report-helper
```

On Windows, use the corresponding paths:

```powershell
jmod extract --dir extracted jmods\com.example.tools.jmod
```

`jmod describe` displays module descriptor information such as the module name and `requires` relationships; it does not replace using `jmod list` to inspect individual command entries.

## 6. Using a JMOD with jlink

A JMOD is not an archive that can be run directly with `java -jar`. It is used at compile-time or link-time. The `jlink` tool reads modules on the module path and creates a custom runtime image containing the selected modules along with their transitive dependencies.

Example on Linux/macOS:

```sh
jlink \
  --module-path "$JAVA_HOME/jmods:jmods" \
  --add-modules com.example.tools \
  --output runtime-image
```

On Windows PowerShell:

```powershell
jlink --module-path "$env:JAVA_HOME\jmods;jmods" --add-modules com.example.tools --output runtime-image
```

Here:

- `$JAVA_HOME/jmods` contains the JMODs of the current JDK.
- `jmods` is the directory containing `com.example.tools.jmod`.
- `--add-modules` selects the root module to include in the image.
- `--output` specifies the runtime image directory.

If the module is selected and the JMOD contains native commands, the command section is processed during linking. Native commands appear in the command directory of the runtime image, typically under `runtime-image/bin/`.

Example on Linux:

```sh
runtime-image/bin/report-helper --help
```

Check the Java runtime in the image:

```sh
runtime-image/bin/java --list-modules
```

The command name and how it is invoked depend on the operating system and the packaged binary. On Windows, the command is typically invoked by its executable filename, such as `runtime-image\bin\report-helper.exe`.

If you only want to check whether the module was linked into the image, use the runtime image's `java --list-modules` command. This command lists modules, not all native commands in the `bin` directory; check the image's file system to confirm specific commands.

## 7. Distinguishing Native Commands from jlink-Generated Launchers

There are two different ways to provide a command in a runtime image:

**Native command packaged with `jmod --cmds`:** this is a pre-built native executable. The JMOD contains that binary, and `jlink` can include it in the runtime image when linking the module.

**Launcher created with `jlink --launcher`:** this is a launcher for a Java module and main class. For example:

```sh
jlink \
  --module-path "$JAVA_HOME/jmods:jmods" \
  --add-modules com.example.tools \
  --launcher tools=com.example.tools/com.example.tools.Main \
  --output runtime-image
```

The `tools` launcher starts the declared Java module/main class. It is not a native command provided by the project via `--cmds`, even though the generated launcher may be a platform-appropriate executable or script.

| Requirement | Configuration |
|---|---|
| Include a pre-built native executable in a module | `jmod create --cmds` |
| Include a native shared library in a module | `jmod create --libs` |
| Specify the Java main class of a module | `jmod create --main-class` |
| Create a command launcher for a Java module in a runtime image | `jlink --launcher` |

Distinguishing these approaches helps avoid confusing a standalone native program with a launcher whose sole purpose is to invoke the JVM to run Java code.

## 8. Native Commands and Native Library Dependencies

A native command can depend on shared libraries. Example on Linux:

```text
native-commands/
└── report-helper

native-libs/
└── libreport.so
```

Package both the command and the library belonging to the module:

```sh
jmod create \
  --class-path mods/com.example.tools \
  --cmds native-commands \
  --libs native-libs \
  --target-platform linux-amd64 \
  jmods/com.example.tools.jmod
```

The libraries are placed in the native libraries section of the JMOD. When creating a runtime image, native components are processed according to JMOD/`jlink` and platform rules. However, adding a library to a JMOD does not guarantee that all of its system dependencies are also packaged.

For example, a native library might depend on the C runtime or an operating system shared library. Those dependencies must exist and be compatible on the target system. Inspect the binary's dependencies using the appropriate tool on the build or target platform itself.

On Linux, `ldd` can show the shared libraries that a dynamically linked executable requires. On macOS, you can use `otool -L`; on Windows, you can use an appropriate PE/dependency analysis tool. Inspection results on one platform do not replace testing on another platform.

## 9. Target Platform and Cross-Platform Distribution

Native commands are tied to the operating system and CPU architecture. The `--target-platform` option declares the target platform of the JMOD. Some example values:

| Target Platform | Operating System | Architecture |
|---|---|---|
| `linux-amd64` | Linux | AMD64/x86-64 |
| `windows-amd64` | Windows | AMD64/x86-64 |
| `macos-aarch64` | macOS | ARM64/Apple Silicon |

The target platform value is metadata describing the target. It does not recompile the command, does not change PE/ELF/Mach-O formats, and does not translate instruction sets.

If a product supports multiple platforms, the typical workflow is:

1. Build the native command using the appropriate toolchain for each target.
2. Test the executable on the corresponding target.
3. Create the JMOD with the native command and matching target-platform.
4. Link the appropriate runtime image using the target's JDK/toolchain.
5. Test the command inside the complete runtime image.
6. Distribute the platform-specific artifact.

Do not bundle Windows, Linux, and macOS binaries into a single JMOD and expect the JVM to automatically pick the right executable. Manage separate artifacts and name them clearly by platform and architecture.

## 10. Execute Permissions and Security

A native command runs with the privileges of the user who launches it. Placing an executable inside a JMOD or runtime image does not create a sandbox and does not restrict the command's operating system permissions.

Packaging considerations:

- Only include binaries in a JMOD whose origin and integrity have been verified.
- Do not package executables obtained from untrusted sources.
- Do not use command names that easily conflict with system commands or other commands in the image.
- Check execute permissions and file access permissions for the target platform.
- Do not assume a binary is runnable just because it appears in `jmod list` output.
- Verify native libraries and system dependencies when running on the target machine.
- Update and re-release the runtime image when a native command has vulnerabilities or requires patches.

The fact that a JMOD can be linked into a runtime image does not mean every command inside it is automatically safe. Update policies, artifact signing, checksum verification, and security testing remain part of the product's release process.

## 11. jlink and the Option to Strip Native Commands

`jlink` has a `strip-native-commands` plugin to remove native commands from the runtime image. This option is useful when you want to reduce command components in the image, but if your application needs commands packaged via `--cmds`, check the plugin configuration to avoid stripping them.

List the plugins supported by the current JDK:

```sh
jlink --list-plugins
```

If an image is created with the option to strip native commands, the executables may no longer be in the image even though they were in the JMOD. Therefore, after linking, always inspect the runtime image's `bin` directory directly and test the required commands.

Do not confuse `--strip-native-commands` with `--no-header-files` or `--no-man-pages`; they remove different types of components.

## 12. Common Errors

| Symptom | Common Cause | Resolution |
|---|---|---|
| `jmod` reports `--cmds` path not found | Incorrect path or directory has not been created | Check the native command directory and run the command from the correct working directory |
| `jmod list` has no `bin/` | JMOD created without `--cmds`, or input directory is empty/incorrect | Check the command input and recreate the JMOD from the correct directory |
| JMOD has `bin/...` but command does not run | Binary is incompatible with OS/CPU, lacks permissions, or is missing a shared library | Check the binary format, execute permissions, and dependencies on the target |
| `jlink` cannot find the module | JMOD is not on the module path, module name is wrong, or module descriptor is invalid | Check `--module-path`, `jmod describe`, and `module-info.class` |
| `jlink` rejects the target platform | JMOD does not match the runtime image platform | Create the JMOD for the correct OS/architecture and use the matching JDK |
| Native command is missing from the runtime image | Module was not linked, JMOD lacks the command entry, or a plugin stripped native commands | Check `--add-modules`, `jmod list`, `jlink --list-plugins`, and the image `bin` directory |
| Command reports missing DLL/shared library | Native library was not packaged or a system dependency is missing | Inspect dependencies and add the appropriate library with `--libs` if needed |
| Command runs on the build machine but fails on the target machine | Build environment has libraries or runtime dependencies absent on the target | Test on a clean image matching the deployment platform |
| Command name collides or wrong command is invoked | Multiple commands share the same name or conflict with tools in the image | Use a distinct name and verify the final contents of the `bin` directory |
| Command does not run after linking the image | Runtime image was created with strip native commands enabled or the artifact was removed | Check plugins and recreate the image with the appropriate configuration |

When diagnosing issues, follow the sequence: check the input directory → inspect the JMOD with `jmod list` → inspect the module with `jmod describe` → inspect the runtime image after `jlink` → run the command on the target platform. This helps isolate whether the error is in native building, packaging, module resolution, or runtime.

## 13. Checklist

- [ ] Native command has been pre-built using the appropriate toolchain.
- [ ] Binary matches the target operating system and CPU architecture.
- [ ] Command is distinguished from Java classes and native shared libraries.
- [ ] Used `--cmds` to add the command to the JMOD.
- [ ] Used `--libs` for shared libraries that need to be packaged.
- [ ] Set `--target-platform` accurately when creating a JMOD for a specific target.
- [ ] Verified the `bin/` section with `jmod list`.
- [ ] Verified extracted contents if needed with `jmod extract`.
- [ ] Linked the module with `jlink` using the correct module path and root module.
- [ ] Confirmed the command appears in the runtime image.
- [ ] Did not accidentally enable the plugin that strips native commands.
- [ ] Tested the command along with its dependencies in the target environment.

## 14. References

- Oracle JDK Tool Reference — The `jmod` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jmod.html
- Oracle JDK Tool Reference — The `jlink` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jlink.html

Native commands in JMOD provide a way to package platform-dependent executables alongside a Java module for linking into a runtime image. Understanding `--cmds`, the `bin/` section, `--target-platform`, `--libs`, and the role of `jlink` helps you build consistent native artifacts that can be verified and deployed on the right operating system and architecture.