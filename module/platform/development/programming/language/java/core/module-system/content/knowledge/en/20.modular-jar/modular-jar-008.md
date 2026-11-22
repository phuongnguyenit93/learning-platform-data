# Inspecting a JAR with jar --describe-module

## 1. Purpose of jar --describe-module

Since Java 9, the Java Platform Module System (JPMS) has allowed applications and libraries to be packaged as named modules. A JAR can contain a `module-info.class` module descriptor, or lack a descriptor and be treated as an automatic module when placed on the module path.

The **jar** tool included with the JDK supports reading a JAR's module information:

    jar --describe-module --file path/to/library.jar

This command helps answer questions such as:

- Does the JAR have an explicit module descriptor?
- What is the module name?
- Which packages does the module export?
- Which modules does the module require?
- Which services does the module declare with `uses` and which providers does it supply with `provides`?
- If the JAR lacks a descriptor, what automatic module name is derived?

**jar --describe-module** is a metadata-reading operation. It does not run the application, initialize classes, automatically resolve all dependencies, or prove that all runtime execution paths will work.

## 2. Basic Syntax

Common syntax:

    jar --describe-module --file <jar-file>

Example on Windows:

    jar --describe-module --file .\lib\codec-api.jar

Example on Linux or macOS:

    jar --describe-module --file ./lib/codec-api.jar

You can write the options in another order:

    jar --file ./lib/codec-api.jar --describe-module

It is important to run **jar** from an appropriate JDK version. Check the tool version:

    jar --version
    java --version

If the machine only has a JRE or `PATH` points to a different JDK than expected, inspection results may differ from the build or deployment environment. Check the actual executable path of the tool when multiple JDKs are installed.

## 3. Reading the Output of a Modular JAR

Suppose a JAR was created from the following module descriptor:

    module com.example.codec {
        requires java.logging;

        exports com.example.codec;
        exports com.example.codec.spi to com.example.application;

        uses com.example.codec.spi.CodecProvider;

        provides com.example.codec.spi.CodecProvider
            with com.example.codec.internal.JsonCodecProvider;
    }

Run:

    jar --describe-module --file codec.jar

Illustrative output may look like:

    com.example.codec jar:file:///.../codec.jar!/module-info.class
    exports com.example.codec
    qualified exports com.example.codec.spi to com.example.application
    requires java.base mandated
    requires java.logging
    uses com.example.codec.spi.CodecProvider
    provides com.example.codec.spi.CodecProvider
        with com.example.codec.internal.JsonCodecProvider
    contains com.example.codec.internal

How to read the main lines:

- **Module name and descriptor source:** the first line shows the module name and the location of the module descriptor read by the tool.
- **exports:** packages exposed to other modules according to JPMS rules. If there is a `to` list, it is a qualified export, meaning only the named modules receive access to the package under that directive.
- **requires:** declared module dependencies. `java.base mandated` is the foundational dependency implicitly added by the compiler for regular modules.
- **uses:** this module looks up providers of the named service.
- **provides ... with ...:** this module registers one or more provider classes for a service.
- **contains:** packages present in the module that are not exported. This line helps identify internal packages; it is not a directive in `module-info.java`.

Actual output depends on the descriptor contents and the JDK in use. Not every JAR will have all of the lines above.

## 4. Distinguishing an Explicit Module and an Automatic Module

### JAR with module-info.class

If a JAR has a valid `module-info.class` at the root location, it is an explicit modular JAR. The module name and directives are taken from the compiled descriptor.

You can inspect the archive structure with:

    jar --list --file codec.jar

In the listing, look for `module-info.class` at the JAR root. For example:

    META-INF/
    META-INF/MANIFEST.MF
    module-info.class
    com/example/codec/Codec.class

In that case, the **jar --describe-module** output will describe the explicitly declared module.

### JAR without module-info.class

If a JAR does not contain a module descriptor, the tool can derive an automatic module when inspecting it:

    jar --describe-module --file legacy-codec.jar

The message usually looks like:

    No module descriptor found. Derived automatic module.

The tool then prints the automatic module name and the packages inferred from the JAR contents. A JAR like this can still be placed on the module path for other modules to depend on, though its metadata is not the same as an explicit module.

Automatic modules typically have these characteristics:

- Reads all other named modules and the unnamed module per automatic module rules.
- Exports the packages it contains per automatic module rules.
- The module name can come from the `Automatic-Module-Name` manifest attribute or be derived from the JAR file name.
- Lacks explicit `requires`, `exports`, `opens`, `uses`, and `provides` directives like those in an explicit module descriptor.

For libraries wishing to preserve a stable module name across file renames or release versions, declare **Automatic-Module-Name** in the manifest when not yet ready to migrate to an explicit module. For example:

    Manifest-Version: 1.0
    Automatic-Module-Name: com.example.legacycodec

Without this attribute, the automatic module name is derived from the file name according to JPMS naming rules. Renaming the JAR can change the derived module name; therefore, do not rely on a derived name as a long-term stable contract.

**Note:** an ordinary JAR on the classpath is loaded into the unnamed module. The fact that the tool can describe it as an automatic module does not mean it automatically becomes an automatic module in every run mode. The automatic module role arises when the JAR is placed on the module path.

## 5. Inspecting a Multi-Release JAR

A Multi-Release JAR (MR JAR) can contain alternative classes or module descriptors per Java version inside the `META-INF/versions/` directory.

An illustrative structure:

    META-INF/
    META-INF/MANIFEST.MF
    com/example/api/Codec.class
    META-INF/versions/9/module-info.class
    META-INF/versions/11/com/example/api/Codec.class

The manifest of an MR JAR must have the attribute:

    Multi-Release: true

To inspect the module descriptor for a specific version, use the **--release** option:

    jar --describe-module --file codec-mr.jar --release 9

This option asks the `jar` tool to describe contents appropriate for the specified version. When inspecting an MR JAR, compare descriptors across the target versions supported by the application; descriptors can differ between releases.

You can list the archive contents to confirm files reside in versioned directories:

    jar --list --file codec-mr.jar

Do not assume that a descriptor in `META-INF/versions/9/` will always be used in every environment. Which contents are selected depends on the runtime version and multi-release JAR rules.

## 6. Cross-Checking the Descriptor with JAR Structure

When module output is not as expected, inspect the archive contents:

    jar --list --file codec.jar

Common paths to check:

| Path in JAR | Meaning |
|---|---|
| `module-info.class` | Explicit module descriptor at archive root |
| `META-INF/versions/<N>/module-info.class` | Descriptor for Java version N in an MR JAR |
| `META-INF/MANIFEST.MF` | Manifest, which may contain `Automatic-Module-Name` and `Multi-Release` |
| `META-INF/services/<service-name>` | Classpath-style provider metadata |
| `com/example/.../*.class` | Classes and packages of the module |

For a JAR with a module descriptor, the module name in the output must match the name declared in the compiled `module-info.java` source. If the name or directives are wrong, check the exact built artifact, not only the source in the repository.

Do not directly edit a released JAR file to patch its descriptor. Edit the source/`module-info.java` or build configuration, rebuild the artifact, and run **jar --describe-module** on the newly produced output file.

## 7. Distinguishing Description Output from Runtime Verification

**jar --describe-module** reports a JAR's metadata. This output alone does not answer every question when integrating the module into an application.

For example, the line:

    requires com.example.logging

only indicates that the descriptor declares that dependency. It does not prove that the `com.example.logging` module is available on the module path when the application runs.

To check the consistency of a set of modules on the module path, you can use the launcher:

    java --module-path mods --validate-modules

This command asks the JVM to validate the module configuration on the module path and exit. This is an additional check, not a replacement for running the application with its actual configuration.

You can also use **jdeps** to analyze dependencies at the class/package level:

    jdeps --module-path mods --check com.example.codec

`jdeps` answers questions about bytecode and module dependencies within its analysis scope; it does not replace testing service providers, reflection, or runtime-specific configuration.

A common verification workflow:

1. Run `jar --describe-module --file ...` to determine the module name and directives.
2. Run `jar --list --file ...` to inspect the descriptor, manifest, and package layout.
3. If it is an MR JAR, repeat describing with `--release` for target versions.
4. Place the artifact along with its dependencies on the module path and run `java --validate-modules`.
5. Run the application or integration tests to confirm service discovery, reflection, and actual startup flow.

## 8. Common Errors

### JAR file not found

If the `jar` tool reports that the archive cannot be found, check the path and working directory:

    jar --describe-module --file ./build/libs/codec.jar

You can use an absolute path to eliminate confusion about the current directory. Paths containing spaces should be enclosed in quotes:

    jar --describe-module --file "C:/work/my project/codec.jar"

### Unexpected automatic module result

If you expected an explicit module but the tool reports no module descriptor found:

- Check whether the output JAR has `module-info.class` at the root.
- Check whether the build tool actually compiled and packaged `module-info.java`.
- For an MR JAR, check the descriptor in `META-INF/versions/<N>/` and use the corresponding `--release`.
- Confirm you are inspecting the newly built JAR, not an older copy in another directory.

### Automatic module name changes

If the module name is derived from the file name, renaming the file or adding a version suffix can affect the module name. To keep the name stable, declare **Automatic-Module-Name** in the manifest or migrate to an explicit module descriptor.

### Missing dependency at runtime

`jar --describe-module` may display `requires`, yet the dependency module cannot be found at runtime. Check the module path, artifact versions, and `java --validate-modules` output. Do not assume that a dependency appearing in the descriptor is already bundled or installed alongside the JAR.

### Using the wrong JDK

If multiple JDKs coexist, the `jar` and `java` commands may come from two different versions. Check `jar --version`, `java --version`, and executable paths to ensure you are analyzing the artifact with the expected toolset.

## 9. Step-by-Step Inspection Example

Suppose you have an artifact:

    build/libs/codec.jar

Step 1 — read the descriptor or automatic module:

    jar --describe-module --file build/libs/codec.jar

Step 2 — inspect the files inside:

    jar --list --file build/libs/codec.jar

Step 3 — if this is an MR JAR, view the descriptor for Java 9:

    jar --describe-module --file build/libs/codec.jar --release 9

Step 4 — validate the module set after placing the JARs into the `mods` directory:

    java --module-path mods --validate-modules

Step 5 — run the application using the actual module path:

    java --module-path mods --module com.example.application/com.example.application.Main

The example above uses illustrative module and main class names; substitute the names declared in your project's module descriptor. On Windows PowerShell, you can write the launcher command on a single line to avoid line-continuation syntax differences.

## 10. Key Takeaways

- **jar --describe-module --file <jar-file>** reads and displays a JAR's module metadata.
- An explicit modular JAR has a `module-info.class` module descriptor; an automatic module lacks an explicit descriptor and is derived when used on the module path.
- **Automatic-Module-Name** in the manifest helps keep an automatic module's name stable.
- A JAR on the classpath belongs to the unnamed module; being describable as an automatic module does not turn a JAR into an automatic module on the classpath.
- **--release** is useful when inspecting descriptors in a Multi-Release JAR.
- **exports**, **requires**, **uses**, and **provides** in the output help read module configuration; `contains` indicates internal packages.
- **jar --describe-module** does not prove dependencies are present or that the application will run successfully.
- Use **jar --list**, **java --validate-modules**, **jdeps**, and integration tests to cover different verification angles.
- Always inspect the exact output JAR and the right JDK version.

**jar --describe-module is the first step to understanding which module a JAR is recognized as and what relationships it declares.** Combining it with archive structure and module path checks helps catch discrepancies early between the artifact, descriptor, and runtime configuration.

## References

- Java SE 21 Tool Specifications — jar: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jar.html
- Java SE 21 Tool Specifications — java launcher: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- Java SE 21 Tool Specifications — jdeps: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeps.html