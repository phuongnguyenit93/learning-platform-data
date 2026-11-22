# Java Application Packaging Tools

Packaging is the step that turns an application's compiled classes, resources, and configuration into a runnable or distributable form. Depending on the goal, the output can be a JAR file, a modular application, a trimmed Java runtime, or an operating-system installer.

This lesson focuses on the tools included with JDK 17 and later: `jar`, `jmod`, `jdeps`, `jlink`, `jpackage`, `keytool`, and `jarsigner`. These commands are located in the JDK's `bin` directory. Use a JDK to perform packaging steps; a standard Java runtime does not provide this full set of tools.

## 1. Choosing a Tool Based on the Desired Output

| Tool | Role | Common Output |
|---|---|---|
| `jar` | Bundles classes, resources, and a manifest into an archive | Standard JAR or executable JAR |
| `jmod` | Creates and inspects module archives for runtime linking | JMOD file |
| `jdeps` | Analyzes dependencies across packages, JARs, and modules | List of required dependencies |
| `jlink` | Assembles required modules into a custom Java runtime | Runnable runtime directory |
| `jpackage` | Packages an application with a runtime into an application image or installer | App image, MSI, EXE, DMG, PKG, DEB, or RPM depending on platform |
| `keytool` | Creates and manages keys, certificates, and keystores | Keystore and certificates |
| `jarsigner` | Signs and verifies JAR signatures | Signed JAR |

Not every application needs all of these tools. For a small application, a JAR with a manifest is often enough. When you want users to run the app without installing Java separately, you can create a runtime with `jlink` or let `jpackage` generate one during packaging.

## 2. Packaging JARs with `jar`

A JAR (Java Archive) is an archive file based on the ZIP format. It typically contains:

- Compiled `.class` bytecode files.
- Resources such as configuration files, images, templates, and data files.
- A `META-INF` directory, including the `MANIFEST.MF` manifest.
- Digital signatures if the JAR has been signed.

`jar` does not compile source code on its own. First use `javac` to produce bytecode, then use `jar` to bundle the files for distribution.

### 2.1. Creating an Executable JAR

Suppose you have the following project structure:

~~~text
project/
├── src/
│   └── com/
│       └── example/
│           └── HelloApp.java
├── out/
└── dist/
~~~

Contents of `src/com/example/HelloApp.java`:

~~~java
package com.example;

public class HelloApp {
    public static void main(String[] args) {
        System.out.println("Hello from a packaged JAR.");
    }
}
~~~

From the `project` directory, run the following commands in PowerShell:

~~~powershell
New-Item -ItemType Directory -Force -Path out, dist | Out-Null
javac -d out src/com/example/HelloApp.java
jar --create --file dist/hello.jar --main-class com.example.HelloApp -C out .
java -jar dist/hello.jar
~~~

On Bash or Zsh, the corresponding directory creation command is `mkdir -p out dist`; the remaining three `javac`, `jar`, and `java` commands stay the same.

Output:

~~~text
Hello from a packaged JAR.
~~~

Explanation:

- `javac -d out ...` compiles the source code and places `.class` files into `out` following the package structure.
- `jar --create` instructs the tool to create a new archive.
- `--file dist/hello.jar` specifies the JAR file path.
- `--main-class com.example.HelloApp` writes the class containing the `main` method into the manifest under the `Main-Class` attribute.
- `-C out .` changes the `jar` command's working directory to `out` and adds the entire contents of that directory to the archive.
- `java -jar` runs the JAR using the entry point information in the manifest.

You can inspect the archive contents without extracting them:

~~~powershell
jar --list --file dist/hello.jar
~~~

To extract into a separate directory:

~~~powershell
jar --extract --file dist/hello.jar --dir extracted
~~~

### 2.2. Manifest and Application Entry Point

The manifest is a text file at `META-INF/MANIFEST.MF`. For a simple executable JAR, the most important attribute is `Main-Class`:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.HelloApp

~~~

The trailing blank line after the attributes is part of the manifest format. When you use `jar --main-class`, the tool generates this attribute for you.

If running `java -jar app.jar` produces the message `no main manifest attribute`, the JAR does not have a valid `Main-Class`. Recreate the JAR with `--main-class` or provide a valid manifest.

### 2.3. JARs with External Dependencies

A JAR contains only the files you include when packaging it. If an application uses external libraries, those libraries must also be distributed and placed on the classpath or module path at runtime.

For classpath applications, you can run the main class directly:

~~~powershell
java -cp "dist/hello.jar;lib/*" com.example.HelloApp
~~~

The classpath separator is a semicolon on Windows and a colon on Linux/macOS. When using `java -jar`, external classpath options are not used to override the application's classpath; dependencies must be declared appropriately, such as via the `Class-Path` attribute in the manifest, or by running the main class with `-cp` as shown above.

## 3. Packaging Applications with the Java Platform Module System

Since Java 9, applications can be organized into modules. A module declares its name, exported packages, and the modules it depends on in a `module-info.java` file.

For example, add `src/module-info.java`:

~~~java
module com.example.hello {
    exports com.example;
}
~~~

Compile and package the module:

~~~powershell
New-Item -ItemType Directory -Force -Path mods/com.example.hello, dist | Out-Null
javac -d mods/com.example.hello src/module-info.java src/com/example/HelloApp.java
jar --create --file dist/com.example.hello.jar --main-class com.example.HelloApp -C mods/com.example.hello .
jar --describe-module --file dist/com.example.hello.jar
~~~

The JAR file now also contains `module-info.class`. The `jar --describe-module` command displays the module name, exported packages, module dependencies, and the main class if declared.

Run the module on the module path:

~~~powershell
java --module-path dist --module com.example.hello
~~~

The `--module` option can be shortened to `-m`. The module path is where the JVM searches for modules; it differs from the classpath, which is used to locate classes for non-modular applications.

A JAR without `module-info.class` can sometimes be used as an automatic module on the module path. The automatic module name can be derived from the filename or declared in the manifest. However, automatic modules do not replace explicitly designed modules and have limitations when used with `jlink`.

## 4. JMOD: Module Archives for the Linking Step

JMOD is a JDK archive format for module contents during development and runtime linking. In addition to classes and resources, a JMOD can contain native libraries, commands, configuration files, header files, documentation, and legal notices.

For example, create a JMOD from a compiled module directory:

~~~powershell
jmod create --class-path mods/com.example.hello --main-class com.example.HelloApp --module-version 1.0.0 dist/com.example.hello.jmod
jmod describe dist/com.example.hello.jmod
jmod list dist/com.example.hello.jmod
~~~

Useful subcommands:

- `jmod create` creates a JMOD file.
- `jmod describe` displays the module description.
- `jmod list` lists the archive contents.

JMOD is primarily intended for creating runtimes with `jlink`. For standard application distribution workflows, JAR is usually more convenient. Do not place JMOD files on the classpath to run them like JARs; use them at the module-linking step when appropriate.

## 5. Analyzing Dependencies with `jdeps`

`jdeps` analyzes the dependencies referenced by bytecode. This tool helps determine which JDK modules an application needs, especially before building a minimal runtime.

~~~powershell
jdeps --summary dist/com.example.hello.jar
jdeps --print-module-deps dist/com.example.hello.jar
~~~

- `--summary` summarizes dependencies by module.
- `--print-module-deps` prints the list of required modules in a format suitable for `jlink --add-modules`.

For applications with external libraries, include those libraries in the analysis scope using the appropriate classpath or module path. For example, you can use `--class-path "lib/*"` when analyzing a classpath application.

`jdeps` performs static bytecode analysis. Dependencies loaded dynamically via reflection, class names constructed from strings, external configuration, or plugin mechanisms may not be fully detected. Therefore, analysis results are a baseline for verification, not a substitute for testing actual application features at runtime.

## 6. Creating a Custom Runtime with `jlink`

A full JDK contains many modules that a specific application does not need. `jlink` assembles the selected modules along with their required dependencies into a runtime image. Users can run the application with this runtime without installing a compatible JRE separately.

### 6.1. Linking a Runtime from Modules

With the `com.example.hello` module from the previous section, run the following command in PowerShell on Windows:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;dist" --add-modules com.example.hello --launcher hello=com.example.hello/com.example.HelloApp --output runtime --strip-debug --no-header-files --no-man-pages
~~~

On Linux/macOS, the separator for module paths is a colon:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:dist" --add-modules com.example.hello --launcher hello=com.example.hello/com.example.HelloApp --output runtime --strip-debug --no-header-files --no-man-pages
~~~

The command above performs the following:

- `--module-path` specifies where to find JDK modules and application modules.
- `--add-modules` selects the root module; `jlink` automatically pulls in the required dependent modules into the runtime.
- `--launcher hello=...` generates a launcher command named `hello`.
- `--output runtime` specifies the output directory for the runtime image. The target directory must not exist yet or must be empty.
- `--strip-debug` removes debug information not needed in a distribution runtime.
- `--no-header-files` and `--no-man-pages` omit header files and man pages to reduce size.

Once created, you can run the launcher from the runtime image:

~~~powershell
.\runtime\bin\hello.bat
~~~

On Linux/macOS, the launcher is at `runtime/bin/hello`. If you did not create a custom launcher, you can invoke the Java executable inside the runtime directly, for example `runtime/bin/java -m com.example.hello`.

### 6.2. Important Limitations

`jlink` works with explicit modules that have a module descriptor. A JAR that is only an automatic module cannot be linked directly into a runtime image. If an application does not yet have a module descriptor, consider keeping the classpath model and using `jpackage`, or modularizing it before using `jlink`.

A runtime image is tied to the operating system and architecture it was built for. Build and test the runtime on the appropriate target environment. A custom runtime also does not create an installer by itself; it only provides the Java environment needed to run the application.

## 7. Packaging Applications with `jpackage`

`jpackage` creates an application image or installer for a Java application. It can bundle the JAR together with a runtime so end users do not need to install Java separately.

### 7.1. Packaging a Classpath Application

Using `dist/hello.jar` from section 2, run:

~~~powershell
jpackage --type app-image --name HelloApp --app-version 1.0.0 --input dist --main-jar hello.jar --main-class com.example.HelloApp --dest packages
~~~

Option meanings:

- `--type app-image` creates a runnable application directory for the current platform.
- `--name` sets the application name.
- `--app-version` sets the displayed application version.
- `--input` specifies the directory containing the JAR and files to distribute.
- `--main-jar` selects the main JAR inside the input directory.
- `--main-class` specifies the main class if the JAR does not provide that information itself.
- `--dest` specifies where to place the output.

`jpackage` generates a runtime image if you do not supply an existing one. You can pass `--runtime-image runtime` to use a runtime image created with `jlink`, provided that runtime contains all required modules and application components.

### 7.2. Packaging a Modular Application

With the `com.example.hello` module packaged in section 3 and the runtime created in section 6, you can use the module syntax:

~~~powershell
jpackage --type app-image --name HelloApp --module-path dist --module com.example.hello/com.example.HelloApp --runtime-image runtime --dest packages
~~~

In module mode, `--module-path` and `--module` identify the module and main class. This differs from classpath mode, which uses `--input` and `--main-jar`; do not mix the two option sets as if they were for a single application mode.

### 7.3. Creating OS-Specific Installers

Replace `--type app-image` with an installer type supported on the build machine, for example:

| Platform | Common Package Types |
|---|---|
| Windows | `msi` or `exe` |
| macOS | `dmg` or `pkg` |
| Linux | `deb` or `rpm` |

Example of creating an MSI package on Windows:

~~~powershell
jpackage --type msi --name HelloApp --app-version 1.0.0 --input dist --main-jar hello.jar --main-class com.example.HelloApp --dest packages
~~~

Available package types depend on the operating system, architecture, and supporting tools on the build machine. Native installers must be built and tested on the target platform; a command that builds an MSI cannot be substituted with a command that builds a DEB on Linux. Use `--type app-image` to test the application before building an installer.

`jpackage` also supports additional options such as icon, vendor name, installation directory, shortcuts, and application menus. Only add options required by your product's distribution needs; options specific to Windows, macOS, or Linux do not necessarily apply on other platforms.

## 8. Signing JARs with `keytool` and `jarsigner`

Digital signing allows recipients to verify whether a JAR has been modified after signing and to identify the certificate used to sign it. Signing does not automatically prove a publisher is trustworthy; trust also depends on the certificate source and the verification policy of the receiving environment.

### 8.1. Creating a Keystore

Example of generating a key pair and certificate in a PKCS12 keystore:

~~~powershell
keytool -genkeypair -alias release -keyalg RSA -keysize 3072 -validity 3650 -storetype PKCS12 -keystore release.p12
~~~

`keytool` will prompt for the keystore password and certificate details. Do not put real passwords in source code, commands saved in shell history, or repositories. For release environments, manage keystores and private keys according to your organization's security policy.

### 8.2. Signing and Verifying a JAR

Sign a JAR using the `release` alias:

~~~powershell
jarsigner -keystore release.p12 -storetype PKCS12 -signedjar dist/hello-signed.jar dist/hello.jar release
~~~

Verify the signature:

~~~powershell
jarsigner -verify -verbose -certs dist/hello-signed.jar
~~~

Sign only after all modifications to the JAR are complete. If you alter the archive contents after signing, the corresponding signature becomes invalid. Signed JARs should also be verified in the actual release pipeline.

`jarsigner` signs JARs; it does not replace the signing mechanisms for native installers produced by `jpackage`. Signing MSI, EXE, PKG, or macOS applications requires workflows and certificates appropriate for those platforms.

## 9. Common Packaging Workflows

### Scenario A: Sharing a Small Java Application

1. Compile with `javac`.
2. Package classes and resources with `jar`.
3. Set `Main-Class` in the manifest.
4. Test with `java -jar` in a clean environment.
5. Distribute the JAR along with instructions for installing Java and any dependent libraries.

This is a lightweight option when users already have a compatible Java runtime.

### Scenario B: Distributing an Application with a Bundled Runtime

1. Organize the application into explicit modules if you need a custom runtime with `jlink`.
2. Use `jdeps` to inspect referenced JDK modules.
3. Check for dynamically loaded dependencies and services that static analysis might miss.
4. Use `jlink` to create a runtime containing the required modules.
5. Use `jpackage` to create an app image or installer.
6. Test on a clean machine matching the target operating system and architecture.

### Scenario C: Preparing a Signed Release

1. Finalize source code, resources, and configuration.
2. Build the final JAR or app image.
3. Sign the JAR with `jarsigner` if distributing a JAR.
4. Sign the installer using the operating system's mechanism if distributing an installer.
5. Verify the signature and test the exact artifact to be released.
6. Archive the artifact, version, checksums, and certificate information according to your release process.

## 10. Common Errors and Troubleshooting

| Symptom | Common Cause | How to Check or Fix |
|---|---|---|
| `no main manifest attribute` when running `java -jar` | Manifest is missing `Main-Class` | Recreate the JAR with `jar --main-class` or a valid manifest |
| `Could not find or load main class` | Incorrect package/class name, missing class, or wrong root directory in the JAR | Use `jar --list` to inspect class paths; verify the fully qualified class name |
| `ClassNotFoundException` or `NoClassDefFoundError` | Missing dependency library at runtime | Add the library to the classpath/module path or update packaging configuration |
| `FindException` or `Module not found` | Module path is missing a JAR/module or the module name is wrong | Use `jar --describe-module` and check `--module-path` |
| `jlink` fails to link a module | Application module is not explicit or module path is missing a module | Ensure `module-info.class` is present and the module path is specified correctly |
| `jpackage` reports the main JAR was not found | `--main-jar` is not in the `--input` directory or the filename is wrong | Verify the exact filename and input directory structure |
| App image runs on the build machine but fails elsewhere | Missing resources, native libraries, modules, or environment configuration | Test on a clean machine; check native dependencies and resource paths |
| Invalid JAR signature | JAR was modified after signing or signature data mismatches | Build the final artifact first, then re-sign; verify the exact file to be released |

When troubleshooting, identify which stage the error occurs in: compilation, archive creation, class loading, module resolution, runtime creation, installer creation, or signature verification. Each stage has its own inputs and diagnostic tools; classifying the stage accurately helps avoid editing the manifest when the real issue is a missing dependency or module path.

## 11. Pre-Distribution Checklist

- [ ] Choose the right output format: JAR, runtime image, or installer.
- [ ] Verify the target JDK and Java version.
- [ ] Confirm the JAR contains all required classes, resources, and manifest entries.
- [ ] Ensure dependent libraries are distributed and loaded properly.
- [ ] If using modules, ensure module names, module paths, and module descriptors are consistent.
- [ ] If using `jlink`, ensure the runtime contains all required modules and dynamic dependencies have been tested.
- [ ] If using `jpackage`, ensure the package type matches the platform and has been tested in a clean environment.
- [ ] If signing, finalize the artifact before signing and verify the signature.
- [ ] Test the release artifact on the target version, target platform, and exact launch method users will use.

Good packaging makes an application easy to install, consistent to run, and straightforward to maintain. Choose tools based on how users will receive and run the application: `jar` for Java archives, `jlink` for custom runtimes, `jpackage` for app images or installers, and `keytool` and `jarsigner` for certificate management and JAR integrity verification.