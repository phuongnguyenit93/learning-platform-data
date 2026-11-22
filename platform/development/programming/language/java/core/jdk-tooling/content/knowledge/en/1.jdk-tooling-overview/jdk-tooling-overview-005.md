# Build-Time Tools in the JDK

## 1. The Role of Build-Time Tools

Build-time tools are programs included in the JDK used to transform source code and resources into artifacts that can be inspected, packaged, and distributed. They participate in stages such as compiling `.java` files into `.class` files, creating JARs, generating API documentation, analyzing dependencies, building runtime images, and packaging applications.

A typical workflow may follow this order:

1. Compile source code with `javac`.
2. Inspect bytecode and dependencies with `javap`, `jdeps`, or `jdeprscan` when needed.
3. Generate API documentation with `javadoc`.
4. Package classes and resources with `jar`.
5. For modular applications, create a minimal runtime image with `jlink`.
6. Create a distribution package with `jpackage`; sign JARs if the release process requires it.

These tools are installed with the JDK and are typically located in the `bin` directory. Maven, Gradle, and Ant are separate build systems; they can invoke these JDK tools to automate workflows, but they are not JDK build-time commands themselves.

Not every project needs all tools. Small applications may only need `javac` and `jar`; public libraries often also need `javadoc`; modular applications can use `jdeps` and `jlink`; products distributed to end users may need `jpackage`.

## 2. `javac` — Compiling Java Source Code

`javac` reads `.java` files, checks syntax and types, and generates bytecode in `.class` files. Bytecode runs on a JVM compatible with the target Java version.

Example project structure:

~~~text
project/
├── src/
│   └── com/
│       └── example/
│           └── Hello.java
└── out/
~~~

Contents of `src/com/example/Hello.java`:

~~~java
package com.example;

public class Hello {
    public static void main(String[] args) {
        String name = args.length == 0 ? "JDK" : args[0];
        System.out.println("Hello, " + name + "!");
    }
}
~~~

Create the output directory and compile targeting Java 17 APIs:

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 -Xlint:all -d out src/com/example/Hello.java
java -cp out com.example.Hello Java
~~~

Output:

~~~text
Hello, Java!
~~~

On Windows PowerShell, you can create the output directory with:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -Xlint:all -d out src/com/example/Hello.java
java -cp out com.example.Hello Java
~~~

Common `javac` options:

| Option | Description |
|---|---|
| `--release 17` | Compiles for Java 17, including the language level, bytecode format, and public API surface of that version. This is usually the best choice when building with a newer JDK while targeting Java 17. |
| `-source 17` | Specifies the accepted source syntax/language level. |
| `-target 17` | Specifies the output bytecode version. Using `-source` and `-target` alone does not guarantee that code only calls APIs available in Java 17; `--release` enforces the API boundary as well. |
| `-encoding UTF-8` | Specifies the character encoding for reading source files. Declare this explicitly to avoid differences between developer machines and CI. |
| `-d out` | Places `.class` files in the `out` directory; the package structure is preserved underneath it. |
| `-classpath` or `-cp` | Specifies JARs/directories containing classes required during compilation. |
| `--module-path` | Specifies the path containing modules when compiling a project that uses the Java Platform Module System (JPMS). |
| `-Xlint:all` | Enables common compiler warnings. |
| `-Werror` | Treats warnings as errors; often used in CI once a project has resolved existing warnings. |
| `-parameters` | Stores method parameter names in bytecode so reflection-based libraries can read them. |
| `-g` | Generates debug information such as line numbers and local variables. |
| `@file` | Reads options and source files from an argument file, useful when commands become too long. |

Example compiling multiple files, where `lib/*` contains dependency JARs:

~~~bash
javac --release 17 -classpath "lib/*" -d out src/com/example/*.java
~~~

When using the classpath, classes are resolved by package and class name. When using JPMS, configure the module path and declare modules appropriately; avoid mixing the two mechanisms arbitrarily.

Common errors:

- `package ... does not exist`: missing library on the classpath/module path or incorrect source path.
- `cannot find symbol`: misspelled class, method, or variable name; or missing import/dependency.
- `invalid source release`: the JDK running `javac` is older than the version requested by `--release`.
- `UnsupportedClassVersionError` at runtime: the runtime is older than the compiled bytecode version. Align the runtime version or compile with a lower `--release`.

## 3. `jar` — Packaging Classes and Resources

A JAR (Java Archive) is a ZIP file with a structure and conventions tailored for Java applications. A JAR can contain bytecode, resources, metadata, and a manifest. It is convenient for distributing applications or libraries.

Create a JAR with a declared main class:

~~~bash
jar --create --file app.jar --main-class com.example.Hello -C out .
~~~

Where:

- `--create` creates a new JAR.
- `--file app.jar` sets the output filename.
- `--main-class` writes the class containing the `main` method into the manifest.
- `-C out .` changes into the `out` directory before adding contents, so the JAR contains `com/example/Hello.class` rather than a nested `out/` path.

List contents and run the application:

~~~bash
jar --list --file app.jar
java -jar app.jar Java
~~~

Output of the run command:

~~~text
Hello, Java!
~~~

Other common operations:

~~~bash
# Extract JAR into the current directory
jar --extract --file app.jar

# Update or add files to an existing JAR
jar --update --file app.jar -C resources .

# View the module descriptor of a modular JAR
jar --describe-module --file app.jar
~~~

A few points to remember:

- `java -jar app.jar` uses the main class declared in the manifest. Without `Main-Class`, the JVM does not know which class to run.
- `java -cp app.jar com.example.Hello` specifies the class to run directly; the classpath can contain multiple directories and JARs.
- Standard JARs can run on the classpath. Modular JARs also contain `module-info.class` and can be placed on the module path.
- Modifying a JAR's contents after signing invalidates the signature; always sign after packaging is complete.

## 4. `javadoc` — Generating API Documentation

`javadoc` reads source code and Javadoc comments to generate HTML documentation for packages, classes, constructors, methods, and public APIs.

Example comment on a method:

~~~java
/**
 * Returns a greeting for a person.
 *
 * @param name the name of the person to greet
 * @return the greeting string
 */
public static String greeting(String name) {
    return "Hello, " + name + "!";
}
~~~

Generate documentation for the `com.example` package:

~~~bash
javadoc -d docs -sourcepath src -subpackages com.example
~~~

The `docs` directory contains HTML pages that can be opened in a browser. For libraries, write Javadoc for public APIs, documenting parameters, return values, exceptions, and usage preconditions. Common tags include:

- `@param`: describes a parameter.
- `@return`: describes the return value.
- `@throws` or `@exception`: describes an exception that may be thrown.
- `@since`: the version in which the API was introduced.
- `@deprecated`: marks an API as no longer recommended and indicates the replacement.
- `{@link ...}`: creates a link to another class or API member.

Javadoc is documentation for API consumers; it does not replace a README with setup instructions, application run examples, or architecture documentation.

## 5. `javap` — Inspecting Bytecode Structure

`javap` is the JDK disassembler. It reads `.class` files or classes inside JARs and displays class signatures, methods, bytecode, and metadata. This tool is useful for verifying what the compiler generated, checking overloads, inspecting generic signatures, or investigating differences between builds.

~~~bash
# View class and method signatures
javap -classpath out com.example.Hello

# Display bytecode of methods
javap -classpath out -c com.example.Hello

# Also display private members
javap -classpath out -p com.example.Hello

# Display detailed class file information
javap -classpath out -verbose com.example.Hello
~~~

`javap` only lets you inspect bytecode; it does not replace a debugger and does not reconstruct the exact original source code.

## 6. `jdeps` and `jdeprscan` — Analyzing Dependencies and Deprecated APIs

`jdeps` analyzes dependencies at the package, class, or module level. It helps identify which JDK modules a library depends on, assists in preparing applications for JPMS, and detects usage of internal APIs.

~~~bash
# Summarize JAR dependencies
jdeps --summary app.jar

# Analyze dependencies recursively
jdeps --recursive app.jar

# Print the list of required JDK modules
jdeps --print-module-deps app.jar

# Find usage of JDK internal APIs
jdeps --jdk-internals app.jar
~~~

The resulting module dependencies can be fed into `jlink`. When analyzing a library with multiple class versions in a multi-release JAR, select the appropriate target version with the `--multi-release` option.

`jdeps` only analyzes dependencies that can be inferred from bytecode and the provided paths. It does not replace integration testing, does not detect all dynamically loaded dependencies via reflection, and cannot verify full runtime behavior on its own.

`jdeprscan` scans bytecode for usage of APIs marked as deprecated in a specific Java version:

~~~bash
jdeprscan --release 17 app.jar
~~~

Use the results to plan replacements for legacy APIs. Deprecated does not mean removed; read the API documentation and check your target version before making changes.

## 7. JPMS, `jmod`, and `jlink`

The Java Platform Module System (JPMS) allows applications to declare modules, module dependencies, and exported packages. A `module-info.java` file describes a module.

Example `src/module-info.java`:

~~~java
module com.example.hello {
    exports com.example;
}
~~~

Keep `Hello.java` in the `com.example` package, then compile and package the module:

~~~bash
javac --release 17 -d mods/com.example.hello src/module-info.java src/com/example/Hello.java
jar --create --file mlib/com.example.hello.jar --main-class com.example.Hello -C mods/com.example.hello .
java --module-path mlib -m com.example.hello/com.example.Hello Java
~~~

Here:

- `mods/com.example.hello` is the directory containing the compiled module.
- `mlib` is the directory containing the modular JAR.
- `--module-path` specifies where to locate modules.
- `-m` or `--module` specifies the module and main class to run.

### `jmod`

JMOD is a module archive format used primarily during runtime image creation. The `jmod` tool can create, list, describe, and inspect JMOD files.

~~~bash
# Create a JMOD from a compiled module
jmod create --class-path mods/com.example.hello --module-version 1.0 mlib/com.example.hello.jmod

# View the module description
jmod describe mlib/com.example.hello.jmod

# List contents
jmod list mlib/com.example.hello.jmod
~~~

JMOD is not a drop-in replacement for standard JARs on the classpath. It primarily serves JDK module tools, especially `jlink`.

### `jlink`

`jlink` assembles application modules and required platform modules to produce a custom runtime image. This runtime image can be smaller than a full JDK because it only includes the selected modules and their dependencies.

Example on Windows PowerShell:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mlib" --add-modules com.example.hello --launcher hello=com.example.hello/com.example.Hello --output runtime-image
~~~

On macOS/Linux, the module path separator is a colon:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mlib" --add-modules com.example.hello --launcher hello=com.example.hello/com.example.Hello --output runtime-image
~~~

Run the generated launcher:

~~~powershell
.\runtime-image\bin\hello.bat
~~~

~~~bash
./runtime-image/bin/hello
~~~

Important requirements and limitations:

- The application and its dependencies must be organized into appropriate modules; `jlink` cannot arbitrarily link unmodularized classpath libraries.
- The module path must contain both application modules and the corresponding platform modules, typically taken from the JDK's `jmods` directory.
- A runtime image is tied to the platform/architecture on which it was built. Separate images must be built for each target OS and architecture.
- `jlink` creates a runtime to run the application; it does not create a native user installer.

## 8. `jpackage` — Packaging Applications for Distribution

`jpackage` creates an application image or a native installer package from a Java application. The tool can bundle a runtime image with the application if a custom runtime image is not provided.

Assuming `dist` contains `hello.jar`, you can create an application image:

~~~bash
jpackage --type app-image --name HelloApp --input dist --main-jar hello.jar --main-class com.example.Hello --dest packages
~~~

Common package types by operating system:

- Windows: `msi` or `exe`.
- macOS: `dmg` or `pkg`.
- Linux: `deb` or `rpm`.

Example creating an MSI on Windows:

~~~powershell
jpackage --type msi --name HelloApp --input dist --main-jar hello.jar --main-class com.example.Hello --dest packages
~~~

Some installer types require corresponding native packaging tools to be installed on the build machine. Native packages are typically built on the target OS itself; check JDK and platform requirements before setting up cross-platform CI.

Key distinctions:

- A JAR is a Java packaging format that runs on a compatible JVM.
- An application image is a directory containing the application and the required runtime.
- A native installer is a platform-specific installation package integrated with the operating system's installer mechanism.

## 9. `keytool` and `jarsigner` — Managing Certificates and Signing JARs

`keytool` manages keystores, key pairs, and digital certificates. `jarsigner` signs JARs and verifies signatures. These two tools commonly appear in release pipelines that require verifying the origin and integrity of JARs.

Create a PKCS12 keystore and key pair:

~~~bash
keytool -genkeypair -alias release -keyalg RSA -keysize 3072 -validity 365 -storetype PKCS12 -keystore release.p12
~~~

The command prompts for certificate details and a keystore password. Sign the JAR:

~~~bash
jarsigner -keystore release.p12 -storetype PKCS12 app.jar release
~~~

Verify the signature:

~~~bash
jarsigner -verify -verbose -certs app.jar
~~~

Release notes:

- Protect private keys and keystore passwords; never commit them to source control or print them in CI logs.
- Only sign after the JAR is finalized. Any content modification after signing can cause signature verification to fail.
- A JAR signature verifies integrity and identity against a certificate; it does not prove that the application is secure or bug-free.
- Code signing and OS installer signing may be two separate steps.

## 10. Other JDK Tools You May Encounter

| Tool | Primary Purpose | When It Is Useful |
|---|---|---|
| `jdeprscan` | Finds deprecated APIs used in bytecode. | Upgrading Java versions or removing legacy APIs. |
| `serialver` | Prints the `serialVersionUID` of a Serializable class. | Checking serialization compatibility. |
| `jmod` | Creates and inspects module archives. | Preparing modules for runtime images. |
| `keytool` | Manages keys, keystores, and certificates. | Setting up truststores or signing workflows. |
| `jarsigner` | Signs and verifies JARs. | Releasing JARs that require digital signatures. |
| `jshell` | Interactive REPL for trying Java expressions and APIs. | Quick experimentation during development; not a standard build packaging step. |

Do not confuse build-time tools with runtime JVM monitoring tools such as `jcmd`, `jstack`, `jmap`, or `jstat`. Those tools are for diagnosing running Java processes.

## 11. Combining Tools in a Build Workflow

A minimal manual workflow for the example above might look like:

~~~bash
# 1. Compile targeting Java 17 with warnings enabled
mkdir -p out
javac --release 17 -encoding UTF-8 -Xlint:all -d out src/com/example/Hello.java

# 2. Generate API documentation
javadoc -d docs -sourcepath src -subpackages com.example

# 3. Package the application
jar --create --file app.jar --main-class com.example.Hello -C out .

# 4. Analyze dependencies
jdeps --summary app.jar

# 5. Run a manual check
java -jar app.jar Java
~~~

In real-world projects, Maven or Gradle typically manages dependencies, source sets, tests, plugins, and step ordering. These systems invoke `javac`, `jar`, `javadoc`, or related tools instead of running commands manually. Keep the JDK version consistent between developer machines and CI, declare the target version explicitly with `--release`, pin dependency versions, and separate output directories from source code.

A release pipeline may add the following steps after a successful build:

1. Run unit tests and integration tests.
2. Use `jdeps` to review dependencies and required modules.
3. Use `jlink` if distributing a minimal runtime for a modular application.
4. Use `jpackage` to create an application image or installer.
5. Sign the appropriate artifacts using a process that protects private keys.
6. Store artifacts, checksums, and build version metadata for traceability.

## 12. Common Errors and Troubleshooting

| Symptom | Common Cause | How to Check / Fix |
|---|---|---|
| `javac` is not recognized | `PATH` does not point to the JDK `bin` directory, or only a JRE is installed. | Run `java -version`, `javac -version`; check `JAVA_HOME` and `PATH`. |
| Compiles successfully, but running reports class not found | Wrong classpath, wrong fully qualified class name, or mismatched package structure. | Check the output directory and run with the fully qualified class name, e.g. `com.example.Hello`. |
| `no main manifest attribute` | The JAR has no `Main-Class`. | Recreate the JAR with `jar --main-class` or an appropriate manifest. |
| `UnsupportedClassVersionError` | The runtime is older than the bytecode version. | Align the runtime or build with an appropriate `javac --release`. |
| `jlink` reports module not found | Missing module on the module path or the application is not properly modularized. | Check `module-info.java`, `--module-path`, and `jdeps --print-module-deps` output. |
| `jpackage` fails to create an installer | Missing required native tools or building on an incompatible platform. | Check package type, target OS, and JDK requirements. |
| `jarsigner -verify` reports invalid signature | The JAR was modified after signing or there is a certificate/signature issue. | Rebuild a clean artifact, re-sign, and verify at the end. |

To diagnose which tool versions are being invoked, run:

~~~bash
java -version
javac -version
jar --version
javadoc --version
jdeps --version
jlink --version
jpackage --version
~~~

If `java` and `javac` point to different JDKs, build results may be inconsistent. Check the actual paths of the commands and configure `JAVA_HOME`/`PATH` so they use the same JDK.

## 13. Quick Reference

| Need | Tool |
|---|---|
| Compile `.java` to `.class` | `javac` |
| Package classes and resources into a JAR | `jar` |
| Generate HTML API documentation | `javadoc` |
| Inspect bytecode and class signatures | `javap` |
| Analyze package/module dependencies | `jdeps` |
| Find deprecated API usage | `jdeprscan` |
| Create/inspect module archives | `jmod` |
| Create a custom runtime image | `jlink` |
| Create an application image or installer | `jpackage` |
| Manage keystores and certificates | `keytool` |
| Sign and verify JARs | `jarsigner` |
| Check `serialVersionUID` | `serialver` |

When choosing a tool, start from the artifact you need to produce: `.class` files need `javac`, a JAR needs `jar`, API docs need `javadoc`, a minimal runtime needs `jlink`, and an installer needs `jpackage`. Use `jdeps`, `javap`, `jdeprscan`, `keytool`, and `jarsigner` when analysis, compatibility, or release requirements call for them.