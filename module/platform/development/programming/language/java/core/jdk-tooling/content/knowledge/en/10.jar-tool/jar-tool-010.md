# Inspecting JARs with the JDK jar Tool

JAR (Java ARchive) is a ZIP-based archive format used to package class files, resources, metadata, and components of a Java application or library into a single file. The **jar** tool included with the JDK helps create, list, extract, update, and inspect JAR structure.

Inspecting JARs is an important step when packaging applications, investigating classpath/module path errors, verifying manifests, checking class file versions, or determining whether a dependency contains the expected classes and resources. A file with a .jar extension is not necessarily a standalone runnable application; the ability to run with java -jar depends on the manifest and how dependencies are packaged.

## 1. What Does a JAR Contain?

A JAR is an archive made up of entries. An entry can be:

- Class files, for example com/example/Main.class.
- Resources, for example application.properties, images, templates, or configuration files.
- The manifest at META-INF/MANIFEST.MF.
- Metadata about modules, services, and signatures.
- Special entries for multi-release JARs under META-INF/versions/.

Entry names typically use forward slashes and reflect the relative path inside the archive. A class with package com.example.Main must reside at entry com/example/Main.class for the class loader to find it by class name.

A JAR can be used as:

- **Library JAR**: provides classes and resources for other applications.
- **Executable JAR**: has a manifest specifying Main-Class to run with java -jar.
- **Modular JAR**: contains the module descriptor module-info.class.
- **Multi-release JAR**: contains different implementations per Java release.
- **Signed JAR**: has signature metadata to verify integrity and the signing source.

These types are not mutually exclusive. For example, a JAR can be both modular and signed; an executable JAR can also be a multi-release JAR.

## 2. Preparation and jar Syntax

The jar tool is located in the JDK's bin directory. Check the version and help:

~~~bash
jar --version
jar --help
~~~

Modern syntax uses long-form modes:

~~~bash
jar --create --file archive.jar [options] [files]
jar --list --file archive.jar [options]
jar --extract --file archive.jar [files]
jar --update --file archive.jar [options] [files]
jar --describe-module --file archive.jar
~~~

Traditional short forms such as c, t, x, u, f, and v still appear in older documentation and scripts. In new scripts, prefer long forms for readability:

| Mode | Purpose |
|---|---|
| --create | Create a new archive |
| --list | List entries in an archive |
| --extract | Extract entries |
| --update | Add or update entries |
| --describe-module | Display the JAR's module descriptor |
| --validate | Validate multi-release JAR structure |

A jar command typically operates on the archive file without needing to run the application. Listing entries also does not mean the classes in the JAR have been loaded or verified by the JVM at runtime.

## 3. Listing JAR Contents

Use --list to view the list of entries:

~~~bash
jar --list --file app.jar
~~~

Sample output:

~~~text
META-INF/
META-INF/MANIFEST.MF
com/
com/example/
com/example/Main.class
com/example/Service.class
config/
config/application.properties
~~~

Use verbose to see additional details such as size and timestamp:

~~~bash
jar --list --verbose --file app.jar
~~~

Listing entries is the first step to check:

- Whether classes are in the correct package path.
- Whether resources are packaged or missing.
- Whether the manifest exists.
- Whether the JAR has module-info.class or multi-release entries.
- Whether unwanted files or packages were included in the artifact.

If you need to search for an entry in the list, you can pipe the output through an OS filtering tool.

Linux/macOS:

~~~bash
jar --list --file app.jar | grep 'Main.class'
~~~

Windows PowerShell:

~~~powershell
jar --list --file app.jar | Select-String 'Main.class'
~~~

When inspecting dependencies, make sure you are reading the right JAR file and the right artifact version. Multiple versions of the same library can exist in caches or build directories.

## 4. Creating a JAR from Class Files and Resources

Suppose a project has been compiled into a classes directory:

~~~text
project/
  classes/
    com/example/Main.class
    com/example/Service.class
    config/app.properties
~~~

Create the JAR:

~~~bash
jar --create --file app.jar -C classes .
~~~

Explanation:

- --create instructs jar to create an archive.
- --file app.jar specifies the output file name.
- -C classes changes the working directory to classes for the following entries.
- The dot selects all contents in that directory.

After creating it, inspect:

~~~bash
jar --list --file app.jar
~~~

You can add specific groups of files or resources:

~~~bash
jar --create --file library.jar -C classes com/example -C resources .
~~~

Each -C DIR pair applies to the files or directories that follow it in the argument list until another -C is encountered. Check the entry list after packaging to confirm the archive structure matches what you expect.

Avoid including the entire project directory or .git directory in a JAR. Package only the classes and resources that the runtime or library consumers actually need.

## 5. Creating an Executable JAR with Main-Class

To run a JAR using java -jar, the manifest needs a Main-Class attribute containing the fully qualified name of a class with an appropriate main method.

Example source:

~~~java
package com.example;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from executable JAR");
    }
}
~~~

Compile:

~~~bash
javac --release 17 -d classes src/com/example/Main.java
~~~

Create the JAR and set Main-Class:

~~~bash
jar --create --file app.jar --main-class com.example.Main -C classes .
~~~

Run:

~~~bash
java -jar app.jar
~~~

Stdout:

~~~text
Hello from executable JAR
~~~

You can view the manifest by extracting the META-INF/MANIFEST.MF entry or opening the JAR with a ZIP reader. Sample manifest content:

~~~text
Manifest-Version: 1.0
Created-By: 17
Main-Class: com.example.Main
~~~

The class name in Main-Class must be a fully qualified name, using dots and without the .class extension.

An executable JAR does not automatically contain all dependencies. If Main depends on external libraries, the runtime needs to find those JARs via the manifest Class-Path, a classpath managed by another launcher, or a packaging mechanism such as a fat/uber JAR created by a build tool. The java -jar command uses JAR-mode classpath configuration and does not use the -cp option to override that classpath.

## 6. The Manifest and Key Attributes

The manifest is the metadata file at META-INF/MANIFEST.MF. It consists of name: value attributes, divided into a main section and optional per-entry sections.

A custom manifest can be written in a MANIFEST.MF file:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.Main
Implementation-Title: Demo Application
Implementation-Version: 1.2.0
Automatic-Module-Name: com.example.demo
~~~

Create a JAR from the manifest:

~~~bash
jar --create --file app.jar --manifest MANIFEST.MF -C classes .
~~~

Common attributes:

| Attribute | Purpose |
|---|---|
| Manifest-Version | Manifest format version |
| Main-Class | Startup class when using java -jar |
| Class-Path | Relative URLs for the launcher to locate dependencies of an executable JAR |
| Implementation-Title | Product or implementation name |
| Implementation-Version | Implementation version |
| Specification-Title | Name of the specification that the library implements |
| Specification-Version | Specification version |
| Automatic-Module-Name | Stable module name when the JAR has no module-info.class |

The manifest has its own formatting rules: each attribute is on its own line, lines end with CRLF per the manifest specification, sections are separated by blank lines, and long lines can be wrapped according to the format's continuation rules. When writing a manifest manually, use a supporting editor or tool to avoid syntax errors.

The Class-Path attribute uses paths relative to the JAR's location, with entries separated by spaces. It is not a good replacement for dependency management in large applications. With Maven/Gradle, it is usually better to let the build or launcher manage the classpath explicitly.

## 7. Extracting JAR Contents

To extract the entire archive into the current directory:

~~~bash
jar --extract --file app.jar
~~~

To extract only specific entries:

~~~bash
jar --extract --file app.jar com/example/Main.class META-INF/MANIFEST.MF
~~~

It is good practice to move into an empty directory before extracting so output files are easy to manage:

Linux/macOS:

~~~bash
mkdir extracted
cd extracted
jar --extract --file ../app.jar
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force extracted | Out-Null
Set-Location extracted
jar --extract --file ../app.jar
~~~

After extracting, you can use javap to read the bytecode:

~~~bash
javap -c -p com.example.Main
~~~

The command above assumes you are in the root directory containing the package path com/example/Main.class. If the class is in another directory, use -classpath to specify its location.

A JAR is an archive that can contain executables, scripts, service providers, or untrusted resources. Before extracting or placing a JAR on the classpath, verify its origin and contents. Do not run an application or plugin just because the archive extracts successfully.

## 8. Updating a JAR

Use --update to add new entries or replace entries with the same path in the archive:

~~~bash
jar --update --file app.jar -C updated-classes .
~~~

Example updating a resource:

~~~bash
jar --update --file app.jar -C resources config/app.properties
~~~

After updating, list the contents again:

~~~bash
jar --list --file app.jar
~~~

Notes:

- --update can add new entries or replace entries with the same name.
- Updating the contents of a signed JAR can invalidate its signatures.
- Updating the manifest or classes can make the artifact differ from the tested and released version.
- jar does not provide a general entry-deletion workflow equivalent to update. If you need to remove entries, create a new archive from the desired set of files or use an appropriate ZIP management tool.

In a release workflow, create a new artifact from a clean build rather than manually updating a released JAR. This keeps builds reproducible and traceable.

## 9. Inspecting Modular JARs

Since Java 9, the module system allows packaging a module in a JAR with a module descriptor module-info.class at the root directory.

Example structure:

~~~text
library.jar
  module-info.class
  com/example/api/Service.class
  com/example/internal/ServiceImpl.class
~~~

View the module description:

~~~bash
jar --describe-module --file library.jar
~~~

Sample output:

~~~text
com.example.library
exports com.example.api
requires java.base mandated
~~~

The module descriptor specifies:

- The module name.
- Exported packages (exports).
- Required modules (requires).
- Services used or provided (uses or provides).
- Packages opened for reflection as declared (opens).

If a JAR does not have module-info.class, it can be used as an automatic module when placed on the module path. The automatic module name can be derived from the JAR file name or taken from the Automatic-Module-Name attribute in the manifest.

Distinguishing classpath and module path:

- On the classpath, classes belong to the unnamed module and module-system package access rules are not enforced as they are for named modules.
- On the module path, the JVM/module system reads the module descriptor or creates an automatic module.
- A JAR that runs on the classpath is not guaranteed to run as a named module because it may encounter issues with exports, requires, split packages, or reflection access.

To inspect a JDK module description, use the appropriate java or jmod command:

~~~bash
java --describe-module java.base
jmod describe "$JAVA_HOME/jmods/java.base.jmod"
~~~

JMOD is the JDK's own packaging format; it is not a regular application JAR for distribution on the classpath.

## 10. Multi-Release JARs

A multi-release JAR allows a single archive to provide different classes for different Java runtimes. The manifest must contain the attribute:

~~~text
Multi-Release: true
~~~

Release-specific classes are placed under META-INF/versions/N/, where N is the Java release number.

Example:

~~~text
library.jar
  META-INF/
    MANIFEST.MF
    versions/
      11/
        com/example/Feature.class
      17/
        com/example/Feature.class
  com/
    example/
      Feature.class
~~~

Classes at the root directory are the base implementation. A Java 11 runtime can select the version in versions/11; a Java 17 runtime can select the version in versions/17 if present; if no matching version exists, the base entry is used.

Create a multi-release JAR with jar:

~~~bash
jar --create --file library.jar -C base-classes . --release 11 -C java11-classes . --release 17 -C java17-classes .
~~~

The --release VERSION option places the subsequent files into META-INF/versions/VERSION and marks the manifest as multi-release. Classes in each version directory must be compiled for the corresponding release and must preserve the public API contract exposed by the library.

Validate the structure:

~~~bash
jar --list --file library.jar
jar --validate --file library.jar
~~~

--validate checks multi-release JAR constraints. It does not replace running tests on each supported runtime.

## 11. Verifying Signatures and Integrity

A JAR can be signed with the **jarsigner** tool. Signatures help verify that signed entries have not been altered since signing and identify which certificate was used to sign.

Verify the signature:

~~~bash
jarsigner -verify -verbose -certs app.jar
~~~

Notes:

- jar is used for packaging and listing; jarsigner is used for signing and signature verification.
- Verification results must be reviewed alongside certificate details, trust chains, expiration dates, and security policies.
- A cryptographically valid signature does not automatically prove the signer is trustworthy.
- Modifying entries after signing can cause verification to fail or leave entries unprotected as expected.
- Sign only after the build, manifest updates, and all packaging steps are complete.

To inspect certificate and signature details, read the full output of jarsigner and use keytool when you need to view the truststore or certificate chain. Do not ignore warnings about untrusted certificates, expired certificates, or weak algorithms.

## 12. Inspecting Dependencies and Classes Inside a JAR

When encountering ClassNotFoundException or NoClassDefFoundError, first confirm whether the class is actually inside the artifact:

~~~bash
jar --list --file dependency.jar
~~~

You can filter by class name:

~~~bash
jar --list --file dependency.jar | grep 'com/example/Service.class'
~~~

Then use javap to inspect the class:

~~~bash
javap -classpath dependency.jar -p com.example.Service
~~~

Use jdeps to analyze dependencies between classes or modules:

~~~bash
jdeps --summary dependency.jar
jdeps --jdk-internals dependency.jar
~~~

jdeps is a separate JDK tool, not a mode of jar. It helps inspect package/module dependencies and detect certain references to JDK internal APIs.

Investigation steps:

1. Identify the missing or unlinkable class.
2. List the contents of the suspected JAR with jar --list.
3. Verify the package name and entry path.
4. Determine the actual classpath/module path at runtime.
5. Check the JAR version and transitive dependencies.
6. Check the class file version with javap if the error relates to runtime version compatibility.
7. Re-run in an environment with the same configuration as production.

A class being present in a JAR does not guarantee the class loader will find it. The JAR must also be on the right classpath/module path and not conflict with another class of the same name from another source.

## 13. JARs in Maven and Gradle

In real-world projects, build tools typically create JARs from the output directory and processed resources. Let Maven or Gradle manage artifacts instead of packaging manually in each environment.

### Maven

With jar packaging, Maven typically creates the artifact when running:

~~~bash
mvn clean package
~~~

The artifact is placed in the target directory by default. Inspect it:

~~~bash
jar --list --file target/app-1.0.0.jar
~~~

If you need to configure Main-Class and manifest metadata, use maven-jar-plugin:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-jar-plugin</artifactId>
    <version>3.4.2</version>
    <configuration>
        <archive>
            <manifest>
                <mainClass>com.example.Main</mainClass>
            </manifest>
            <manifestEntries>
                <Implementation-Version>1.0.0</Implementation-Version>
            </manifestEntries>
        </archive>
    </configuration>
</plugin>
~~~

The Maven JAR Plugin generates the manifest and packages the artifact; it is separate from the JDK's jar tool even though both produce the JAR format.

### Gradle

With the Java plugin, the jar task typically creates the archive in build/libs:

~~~bash
gradle clean jar
~~~

You can configure the manifest in build.gradle:

~~~groovy
tasks.jar {
    manifest {
        attributes(
            'Main-Class': 'com.example.Main',
            'Implementation-Version': project.version
        )
    }
}
~~~

Inspect the artifact:

~~~bash
jar --list --file build/libs/app.jar
jar --describe-module --file build/libs/app.jar
~~~

The actual file name depends on the project name, version, and archiveBaseName. If you use the Shadow plugin or a fat JAR tool, check its specific configuration and avoid confusing the plugin-generated archive with the standard JAR from the jar task.

## 14. Common Issues When Inspecting JARs

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Main class not found when running java -jar | Missing/incorrect Main-Class in manifest or class not at the right package path | Check META-INF/MANIFEST.MF and the class entry |
| ClassNotFoundException | JAR missing from classpath or entry missing | Check jar --list and the launch command |
| NoClassDefFoundError | Dependency may be missing at runtime or class initialization failed | Check dependencies and the root cause in the stack trace |
| JAR runs on dev machine but not on server | Different JDK, dependencies, or working directory | Check runtime, manifest Class-Path, and deployment environment |
| Module descriptor not found | JAR has no module-info.class or inspecting the wrong artifact | List entries and run jar --describe-module |
| Signature verification failed | Entry modified after signing or signature/certificate issue | Rebuild, sign last, and verify the certificate |
| Resource not found | Resource not packaged or wrong lookup path | Check the entry path and how ClassLoader is used |
| Multi-release entry not selected | Missing Multi-Release: true or wrong version directory | Check manifest and META-INF/versions |
| Archive updated but signature fails | Contents changed after signing | Finish all updates before re-signing |

## 15. Pre-Release JAR Inspection Checklist

1. **Identify the artifact**: name, version, module, and JAR type (library, executable, modular, or multi-release).
2. **List entries**: use jar --list to check classes, resources, manifest, and directory structure.
3. **Check the manifest**: confirm Main-Class, version metadata, Class-Path, or Automatic-Module-Name as needed.
4. **Inspect class files**: use javap to check class version, descriptors, and bytecode of key classes.
5. **Inspect the module**: use jar --describe-module if the artifact has a module descriptor or is used on the module path.
6. **Check dependencies**: use jdeps and build reports to understand dependencies and confirm they are present at runtime.
7. **Check multi-release**: review the manifest, META-INF/versions, and run jar --validate.
8. **Verify signatures**: use jarsigner -verify if the artifact is signed.
9. **Run smoke tests**: run the executable JAR or integrated application on the exact target runtime.
10. **Store artifact and checksums**: manage versions, build provenance, and checksums according to the project's release process.

## 16. Key Takeaways

- A JAR is a ZIP-based archive that can contain classes, resources, a manifest, module metadata, and signatures.
- Use jar --list to view entries, --create to build, --extract to unpack, and --update to add or replace entries.
- An executable JAR requires a valid Main-Class in its manifest; dependencies must be provided separately or packaged using an appropriate strategy.
- jar --describe-module shows the module descriptor; the classpath and module path have different loading rules.
- Multi-release JARs use Multi-Release: true and entries under META-INF/versions/N.
- jarsigner is the signing/verification tool; modifying a JAR after signing can invalidate the signature.
- jar --validate checks multi-release JAR constraints and does not replace runtime testing.
- jar --list confirms an entry exists but does not prove the application can load or run it.
- Always verify the final artifact, dependencies, manifest, class version, and runtime before releasing.

## Official References

- [jar Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jar.html)
- [JAR File Specification — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/jar/jar.html)
- [jarsigner Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jarsigner.html)
- [jdeps Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html)
- [Java Platform Module System — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)