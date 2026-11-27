# Packaging JARs and Declaring the Main Class in Java 17

A Java application is usually compiled into multiple `.class` files, possibly accompanied by resources such as configuration files, email templates, or images. During deployment, sending individual files while preserving the exact directory structure is error-prone. A **JAR (Java Archive)** bundles classes and resources into a single archive file for distribution, execution, or use as a library.

To run a JAR directly with the `java -jar` command, the archive needs to declare the entry-point class in its manifest via the `Main-Class` attribute. That class must provide a valid entry point that the Java launcher can invoke. If the application has dependencies, you must ensure those libraries are also on the classpath or packaged in a way supported by the launcher or build tool.

This lesson explains how to create a JAR using the JDK 17 `jar` tool, declare `Main-Class`, run with `java -jar`, handle dependencies, distinguish regular JARs from modular JARs, and inspect artifacts before deployment.

## 1. What Is a JAR?

A JAR is a ZIP-based archive format used to bundle the components of a Java application into a single file. A JAR can contain:

- Compiled `.class` bytecode.
- Resources such as `.properties`, JSON, XML, templates, or images.
- Metadata inside the `META-INF` directory.
- A manifest describing archive information, which can declare the main class.
- Digital signatures and related metadata if the archive is signed.

Example structure of a simple JAR:

```text
app.jar
├── META-INF/
│   └── MANIFEST.MF
└── com/
    └── example/
        └── app/
            ├── Main.class
            └── GreetingService.class
```

JAR is not a separate bytecode format. The `.class` files inside are still JVM bytecode; the JAR simply packages them together with resources and metadata.

### 1.1. Library JARs and Executable JARs

There are two common ways to use a JAR:

| Type | Purpose | Common Usage |
| --- | --- | --- |
| Library JAR | Provides classes/resources for other applications to use | Placed on the classpath or module path |
| Executable JAR | Has an entry point to launch the application | java -jar app.jar |

A library JAR does not necessarily have a `Main-Class`. A regular executable JAR needs a manifest with `Main-Class` so the `java -jar` command knows which class to invoke.

Having a `Main-Class` does not automatically make all dependencies part of the JAR. The archive only contains the files packaged into it; external libraries still need to be provided to the runtime.

## 2. Preparing Source Code and Output Directory

Suppose the application has a main class in the `com.example.app` package:

```text
jar-demo/
├── src/
│   └── com/
│       └── example/
│           └── app/
│               └── Main.java
└── out/
```

Contents of `Main.java`:

```java
package com.example.app;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from a JAR");

        if (args.length > 0) {
            System.out.println("First argument: " + args[0]);
        }
    }
}
```

The application entry point is the method:

```java
public static void main(String[] args)
```

The Java launcher looks for the `main` method following this convention. The class name in the manifest is the fully qualified name including the package, for example `com.example.app.Main`, not the file name `Main.java` or `Main.class`.

### 2.1. Compiling with javac

From the `jar-demo` directory, compile the source code into the `out` directory:

```bash
javac -d out src/com/example/app/Main.java
```

After compiling:

```text
out/
└── com/
    └── example/
        └── app/
            └── Main.class
```

The `-d out` option tells the compiler to write `.class` files into the output directory and create the corresponding package directories. JARs are normally built from compiled bytecode, not from `.java` files.

If the application has multiple source files, you can list them or use a build tool to manage source sets. For example:

```bash
javac -d out src/com/example/app/Main.java src/com/example/app/GreetingService.java
```

## 3. Creating a JAR with the jar Tool

JDK 17 includes the `jar` command-line tool. Create a JAR from the output directory:

```bash
jar --create --file app.jar -C out .
```

Meaning:

- `--create` creates a new archive.
- `--file app.jar` specifies the output JAR file name.
- `-C out .` changes the working directory of the packaging command to `out` and adds all contents of that directory to the archive.

The resulting JAR will have entries organized by package, such as `com/example/app/Main.class`. There is no `out/` prefix at the start of entry paths because `-C out .` packages the contents inside `out`.

### 3.1. Creating an Executable JAR with --main-class

To declare the main class when creating the archive:

```bash
jar --create --file app.jar --main-class com.example.app.Main -C out .
```

The `--main-class` option (short form `-e`) sets the entry point for the archive. For a regular JAR, the tool writes the `Main-Class` attribute into the manifest.

You can inspect the archive contents:

```bash
jar --list --file app.jar
```

Example output:

```text
META-INF/
META-INF/MANIFEST.MF
com/
com/example/
com/example/app/
com/example/app/Main.class
```

### 3.2. Inspecting the Manifest

The manifest is located at:

```text
META-INF/MANIFEST.MF
```

Its main contents look like:

```text
Manifest-Version: 1.0
Created-By: 17
Main-Class: com.example.app.Main

```

Metadata lines may vary depending on how the JAR was created and the JDK version. The important attribute for `java -jar` is `Main-Class`.

### 3.3. Creating a Manifest Manually

You can create a `MANIFEST.MF` file:

```text
Manifest-Version: 1.0
Main-Class: com.example.app.Main

```

The manifest must end with a blank line after the main attributes section. Then create the JAR:

```bash
jar --create --file app.jar --manifest MANIFEST.MF -C out .
```

Attribute names are case-insensitive according to manifest rules, but you should write the standard form `Main-Class`. The value must be the fully qualified class name without the `.class` extension.

If you already use `--main-class`, you usually do not need to create a manual manifest just to set `Main-Class`. A custom manifest is useful when you need to declare additional metadata such as `Class-Path` or version information.

## 4. Running an Executable JAR with java -jar

When the manifest has a valid `Main-Class`:

```bash
java -jar app.jar
```

Output:

```text
Hello from a JAR
```

The Java launcher reads the manifest, loads the specified class, and invokes the `main` method.

### 4.1. Passing Arguments to the Application

Arguments placed after the JAR name are passed to `main(String[] args)`:

```bash
java -jar app.jar production --port 8080
```

Inside the program:

```java
public static void main(String[] args) {
    for (String arg : args) {
        System.out.println(arg);
    }
}
```

The `args` array does not contain the JAR name or the JVM options used to launch it. It only contains the application arguments placed after the JAR.

### 4.2. Passing JVM Options

Options intended for the JVM must be placed before `-jar`:

```bash
java -Xms256m -Xmx1g -Dapp.environment=production -jar app.jar
```

Where:

- `-Xms256m` sets the initial heap size.
- `-Xmx1g` sets the maximum heap limit.
- `-Dapp.environment=production` creates a system property for the application.

Arguments after `app.jar` are passed to the application:

```bash
java -Dapp.environment=production -jar app.jar --port 8080
```

### 4.3. The no main manifest attribute Error

If you run:

```bash
java -jar library.jar
```

and receive a `no main manifest attribute` error, the JAR's manifest does not have the `Main-Class` required by the launcher.

You can resolve this by:

- If the JAR is an application, recreating it with `--main-class` or a manifest containing `Main-Class`.
- If the JAR is only a library, running a separate `main` class on the classpath rather than assuming the library is executable.

You should not add an arbitrary `Main-Class` to a library JAR if the archive is not designed to be launched as an application.

## 5. Declaring the Main Class Correctly

`Main-Class` is the fully qualified class name of the entry point:

```text
Main-Class: com.example.app.Main
```

Common mistakes:

| Incorrect Declaration | Why It Is Wrong |
| --- | --- |
| Main-Class: Main | Missing package if the class belongs to com.example.app. |
| Main-Class: com/example/app/Main | Uses a file path instead of a Java class name. |
| Main-Class: com.example.app.Main.class | Do not append the .class extension. |
| Main-Class: com.example.app | This is a package, not a class. |
| Main-Class: com.example.app.Main.java | The manifest references a compiled class, not a source file. |

The entry-point class must have a valid `main` method, typically:

```java
public static void main(String[] args)
```

The method may declare `throws` if needed. If the class does not exist in the JAR or lacks a valid entry point, the launcher will report an error at runtime.

### 5.1. Applications with Multiple Classes Containing main

A project may have multiple classes with a `main` method, such as:

- `com.example.app.ServerMain`
- `com.example.app.MigrationMain`
- `com.example.app.AdminMain`

A single manifest only declares one default `Main-Class` for `java -jar`. If you need multiple run modes, you can:

1. Build separate JARs with different entry points.
2. Use a single launcher class that reads arguments and dispatches to the appropriate functionality.
3. Run the desired class directly with `java -cp ... fully.qualified.ClassName`.

You should not rely on class order inside the archive to select the entry-point class.

## 6. JARs with Resources

Applications often need to package configuration files or resources alongside bytecode:

```text
jar-demo/
├── src/
│   └── com/example/app/Main.java
├── resources/
│   └── app.properties
└── out/
```

You can copy resources into the output directory before packaging, or add the resources directory using `-C`:

```bash
jar --create --file app.jar --main-class com.example.app.Main -C out . -C resources .
```

Then `app.properties` sits at the root of the JAR. You can read the resource via the class loader:

```java
try (var input = Main.class.getResourceAsStream("/app.properties")) {
    if (input == null) {
        throw new IllegalStateException("Missing app.properties");
    }
    // Read content from input.
}
```

You should not use filesystem paths such as `new File("app.properties")` to read resources packaged inside a JAR. Resources inside an archive are not necessarily standalone files on the filesystem; use the classpath/module resource API instead.

## 7. Dependencies: JARs Do Not Automatically Bundle Other Libraries

An application may depend on external libraries:

```text
app.jar
lib/
├── logging.jar
└── database-driver.jar
```

The basic `jar` command only packages the specified files. It does not automatically locate and embed dependencies from Maven or Gradle.

There are two common ways to provide dependencies for a non-modular application.

### 7.1. Running with the Classpath

Instead of `java -jar`, you can specify the classpath and class name:

On Linux/macOS, the classpath separator is a colon:

```bash
java -cp "app.jar:lib/*" com.example.app.Main
```

On Windows, the classpath separator is a semicolon:

```powershell
java -cp "app.jar;lib/*" com.example.app.Main
```

The wildcard `lib/*` allows the launcher to add all JARs in the `lib` directory to the classpath. The main class name is specified directly after `-cp`.

When using `-jar`, the launcher takes the specified JAR as the source of application classes and ignores external classpath settings such as `-cp`/`CLASSPATH`. Therefore, do not use `java -cp ... -jar app.jar` expecting `-cp` to supply additional libraries to the application.

### 7.2. Using the Class-Path Attribute in the Manifest

If you want to keep using `java -jar`, the manifest can declare `Class-Path`:

```text
Manifest-Version: 1.0
Main-Class: com.example.app.Main
Class-Path: lib/logging.jar lib/database-driver.jar

```

When running:

```bash
java -jar app.jar
```

The launcher adds the URLs in `Class-Path` to the application's classpath. Relative paths are resolved relative to the location of the JAR containing the manifest, not arbitrarily relative to the current working directory.

For example:

```text
deploy/
├── app.jar
└── lib/
    ├── logging.jar
    └── database-driver.jar
```

With the structure above, `lib/logging.jar` is resolved relative to the directory containing `app.jar`.

Entries in the manifest `Class-Path` are archive URLs/paths following manifest rules, separated by spaces. If names contain spaces, they must be properly URL-encoded/escaped; avoid concatenating arbitrary file names manually without validation.

`Class-Path` is useful for a simple deployment layout, but you must ensure all dependent JARs are copied to the expected locations. It is not a dependency or version management system.

### 7.3. Fat JAR or Uber JAR

Another approach is creating a **fat JAR** (also called an uber JAR) containing both the application and the contents of its required dependencies in a single archive.

Build tools such as Maven and Gradle provide dedicated plugins to produce this type of artifact. They handle merging resources, metadata, and service provider configurations according to plugin rules.

You should not manually unpack every dependency and merge all files into one JAR without handling:

- Duplicate resource names.
- Duplicate `META-INF/services` files.
- Digital signatures from dependencies.
- Manifest files and module metadata.
- Library licenses and notices.

Some frameworks use a custom executable JAR format with their own launcher and nested JAR layout. Such archives should be built and run according to the framework's documentation; do not assume a basic `jar` command creates an equivalent structure.

## 8. Running a JAR Without Main-Class

A library JAR or a JAR packaged without an entry point can still be executed by specifying the classpath and main class:

```bash
java -cp library.jar com.example.tools.DiagnosticMain
```

In this case:

- `library.jar` is placed on the classpath.
- `com.example.tools.DiagnosticMain` is the launcher class.
- No `Main-Class` is needed in the manifest because the class name is supplied on the command line.

This is also how you run one of multiple `main` classes contained in the same artifact.

## 9. Modular JARs and the Main Class

Since Java 9, a JAR can be a **modular JAR** if it contains `module-info.class` at its root. Java 17 continues to support this model.

Example module source:

```text
src/
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
```

`module-info.java`:

```java
module com.example.app {
    exports com.example.app;
}
```

Main class:

```java
package com.example.app;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from a named module");
    }
}
```

### 9.1. Compiling the Module

From the project directory:

```bash
javac -d mods --module-source-path src -m com.example.app
```

Output:

```text
mods/
└── com.example.app/
    ├── module-info.class
    └── com/example/app/Main.class
```

### 9.2. Packaging a Modular JAR

Package the module contents:

```bash
jar --create --file app.jar --main-class com.example.app.Main -C mods/com.example.app .
```

For a modular JAR, `--main-class` records the main class information in the module metadata (`ModuleMainClass`) so the launcher can use it when running the module without specifying the class on the command line.

Inspect the descriptor:

```bash
jar --describe-module --file app.jar
```

### 9.3. Running a Modular JAR via the Module Path

Run a module with a declared main class:

```bash
java --module-path app.jar --module com.example.app
```

You can use the short form `-m` instead of `--module`:

```bash
java --module-path app.jar -m com.example.app
```

If no main class is declared in the module metadata, you can specify the class explicitly:

```bash
java --module-path app.jar -m com.example.app/com.example.app.Main
```

This is how you run an application on the module path. When working with modular JARs, distinguish the module name from the JAR file name: the module name comes from the module descriptor and does not have to match the file name.

### 9.4. Manifest Main-Class and ModuleMainClass

For a regular JAR, `Main-Class` in the manifest provides the entry point for `java -jar`.

For a modular JAR, `jar --main-class` also records the main class in the module metadata. When running with `java -m module`, the launcher uses `ModuleMainClass` if present; otherwise, specify `module/class` on the command line.

Both cases identify a Java class with `main`, but how the launcher locates the module and entry-point class differs.

## 10. Inspecting and Verifying JAR Contents

After building the artifact, verify that the archive contains the expected classes, resources, and manifest.

### 10.1. Listing Entries

```bash
jar --list --file app.jar
```

You can filter results by file name or package using the corresponding shell utilities.

### 10.2. Extracting the Archive

```bash
mkdir extracted
jar --extract --file app.jar --directory extracted
```

After extracting, verify:

- `META-INF/MANIFEST.MF`.
- That the class declared in `Main-Class` exists in the expected package.
- That required resources are included in the archive.
- That `module-info.class` is present if it is a modular JAR.

### 10.3. Inspecting the Module Descriptor

For a modular JAR:

```bash
jar --describe-module --file app.jar
```

This command shows the module name, exported packages, dependencies, and module metadata that the tool can display.

### 10.4. Verifying with an Actual Run

Finally, run the artifact the same way it will be deployed:

```bash
java -jar app.jar
```

Or for a modular JAR:

```bash
java --module-path app.jar -m com.example.app
```

Running directly from the `out` directory does not prove the JAR was packaged properly. Run the actual JAR file in a separate deployment directory with the expected dependency layout.

## 11. Manifest and Common Attributes

The manifest is a text file in Java manifest format located at `META-INF/MANIFEST.MF`.

Some common attributes:

| Attribute | Purpose |
| --- | --- |
| Manifest-Version | Manifest format version; typically 1.0. |
| Main-Class | Entry-point class for a regular executable JAR. |
| Class-Path | Additional dependency URLs/JARs for the application class loader. |
| Implementation-Title | Product or component name. |
| Implementation-Version | Implementation version. |
| Specification-Title | Name of the specification provided by the JAR. |
| Multi-Release | Marks a multi-release JAR if the archive is actually packaged with that structure. |

Not every JAR needs all of these attributes. Only add metadata that the application or deployment tooling actually uses.

### 11.1. Long Lines in the Manifest

The manifest specification enforces line-length limits and continuation-line rules. If you author a manifest manually, do not concatenate an excessively long `Class-Path` line by hand while ignoring these rules. Use the `jar` tool or a build tool to generate the manifest when the dependency list is large.

### 11.2. Do Not Arbitrarily Modify Signed JARs

If an archive is digitally signed, modifying its contents or changing entries can invalidate the signature. When you need to update the application, rebuild and re-sign the artifact through your release process rather than editing a signed JAR in place.

## 12. Packaging with Build Tools in Real Projects

For small projects, `javac` and `jar` are enough to illustrate the workflow. Real-world projects typically have many dependencies, resources, tests, versions, and environment configurations. Maven or Gradle makes the build reproducible and manages dependencies.

A typical build workflow:

1. Declare source sets and dependencies.
2. Compile sources into classes.
3. Copy resources into output.
4. Create the JAR with the appropriate manifest.
5. If needed, create an artifact containing dependencies via a dedicated plugin.
6. Test running the generated artifact itself.

For example, with Maven, the JAR plugin can configure `Main-Class` in the manifest; if a fat JAR is needed, use a plugin dedicated to packaging dependencies. With Gradle, configure the `jar` task or an appropriate plugin to set the manifest and build the artifact.

Plugin names and syntax may vary across build tool versions; consult the documentation for the version used in your project. What matters is that the final artifact contains the manifest/metadata and dependencies in the layout expected by the launcher.

## 13. Common Errors and How to Fix Them

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| no main manifest attribute | The JAR has no Main-Class. | Create an executable JAR with --main-class or add a proper manifest. |
| Could not find or load main class | Wrong class name, class not packaged, or wrong package path. | Check Main-Class and the list of entries inside the JAR. |
| Main method not found | The declared class does not have a valid main method. | Use a class with public static void main(String[] args). |
| Runs in IDE but JAR throws ClassNotFoundException. | Dependency is on the IDE classpath but not provided when running the JAR. | Configure the classpath, manifest Class-Path, or build an artifact containing dependencies. |
| java -cp ... -jar app.jar still misses libraries. | When using -jar, external classpath settings are ignored. | Use -cp with the main class name, or use manifest Class-Path/fat JAR. |
| Resource not found after packaging. | Resource was not added to the JAR or code uses filesystem paths. | Include the resource in the archive and read it via class loader/module resource API. |
| Modular JAR fails to run with expected module name. | Module name in descriptor differs from file name or descriptor is not at the root. | Use jar --describe-module to inspect module metadata. |
| Manifest is not read as expected. | Invalid formatting, missing trailing blank line, or invalid continuation lines. | Use standard manifest formatting and inspect META-INF/MANIFEST.MF after packaging. |
| JAR runs on dev machine but fails on another machine. | Missing dependencies, different runtime, or environment-dependent resources/paths. | Test the artifact in a clean environment with the target JDK/runtime. |

## 14. Complete Workflow: From Source to Executable JAR

For a simple non-modular application:

**Step 1 — Compile**

```bash
javac -d out src/com/example/app/Main.java
```

**Step 2 — Create the JAR and set the main class**

```bash
jar --create --file app.jar --main-class com.example.app.Main -C out .
```

**Step 3 — Inspect contents**

```bash
jar --list --file app.jar
```

**Step 4 — Run**

```bash
java -jar app.jar
```

**Step 5 — Run with arguments and JVM options**

```bash
java -Xmx512m -Dapp.environment=production -jar app.jar --port 8080
```

If the application has dependencies, supply them via classpath/manifest or use a build tool to produce the corresponding deployment artifact. If it is a modular JAR, use the module path and the `-m` launcher option.

## 15. Practice Exercises

### Exercise 1 — Create an Executable JAR

Create a `com.example.app.Main` class with a `main` method, compile it into an `out` directory, package it with `jar --main-class`, and run it with `java -jar`.

### Exercise 2 — Write a Manifest Manually

Create a `MANIFEST.MF` file containing `Manifest-Version` and `Main-Class`. Repackage the JAR using `--manifest`, then inspect the manifest inside the archive.

### Exercise 3 — Pass Arguments

Run the JAR with the arguments `dev`, `--port`, `8080`. Print the values inside `main(String[] args)` and distinguish them from `-Xmx` or `-D`, which are JVM options.

### Exercise 4 — External Dependencies

Create two JARs: an application and a library. Run the application with `-cp` on Linux/macOS and Windows; then try manifest `Class-Path`. Explain why `-cp` does not add to the classpath when using `-jar`.

### Exercise 5 — Resources in a JAR

Package `app.properties` alongside the application. Read the resource using `getResourceAsStream` and test running the JAR from a different working directory to prove the resource does not depend on the current working directory.

### Exercise 6 — Modular JAR

Create `module-info.java`, compile with `--module-source-path`, package a modular JAR with a main class, and run it using `java --module-path ... -m ....`. Use `jar --describe-module` to inspect the descriptor.

## 16. Official Java 17 Documentation

- [Java SE 17 jar tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html): create, update, list, and describe JARs; options `--main-class`, `--manifest`, `--describe-module`.
- [Java SE 17 Launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): how to run classes, JARs, and modules; options `-jar`, `-cp`, `--module-path`, `-m`.
- [Java SE 17 javac tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): compile sources and modules.
- [JAR File Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html): archive structure, manifest, and attributes.
- [Java Platform Module System — JLS §7](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html): module declarations and module organization.

A JAR packages bytecode, resources, and metadata into one archive for distribution. For regular executable JARs, `Main-Class` in the manifest specifies the class with the `main` method; `java -jar` uses that information to launch. Dependencies must still be provided via classpath, manifest `Class-Path`, or packaging mechanisms supported by build tools. For modular JARs, verify `module-info.class` and run via the module path. Always inspect and test running the final artifact before deployment.
