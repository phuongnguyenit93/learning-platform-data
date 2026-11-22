# Source-to-Artifact Flow in Java

A Java program goes from source code to an artifact through multiple steps: preparing sources and resources, compiling into bytecode, running tests, packaging, verifying artifact contents, and distributing it to the runtime environment. Each step produces a specific kind of output and can fail for different reasons.

Understanding this flow helps answer practical questions: where `.java` files become `.class` files, when resources are placed into a JAR, whether dependencies are included inside the JAR, why a build succeeds yet running with `java -jar` fails, and how to verify that the released file matches the tested file.

## 1. Pipeline Overview

The typical flow of a Java application:

~~~text
Source + Resources + Generated Sources + Dependencies
                       |
                       v
             Compile production code
                       |
                       v
          Class files (.class / bytecode)
                       |
          Process and copy resources
                       |
                       v
                Production classes
                       |
             Compile test sources
                       |
                       v
              Run unit/integration tests
                       |
                       v
            Package JAR / WAR / other
                       |
                       v
           Verify contents and metadata
                       |
                       v
         Sign / checksum / publish artifact
                       |
                       v
           Deploy and run on a JVM
~~~

Each stage has its own purpose:

- **Source:** Java code, configuration files, resources, generated sources, and build configuration.
- **Compile:** converts source code into class files, checking types, modules, and dependencies.
- **Test:** verifies the behavior of the compiled code.
- **Package:** bundles classes, resources, and metadata into a JAR or WAR.
- **Verify:** confirms that the artifact contains the right files, the right version, and is runtime-compatible.
- **Publish:** stores the artifact in a repository or artifact store.
- **Deploy:** delivers the tested artifact to the runtime environment.

Not every project needs every stage. Small applications can use `javac` and `jar` directly; larger projects typically use Gradle or Maven to manage tasks, dependencies, and lifecycle.

## 2. Inputs That Shape an Artifact

An artifact is not determined solely by `.java` files. Important inputs include:

| Input | Example | Role |
|---|---|---|
| Java source | src/main/java | Code compiled by the compiler |
| Resources | src/main/resources | Properties, XML, JSON, templates, images |
| Generated source | Annotation processor, code generator | Source code generated during the build |
| Dependencies | JAR, modular JAR | APIs and implementations from external libraries |
| Build configuration | build.gradle, pom.xml | Defines compiler, resources, tests, and packaging |
| JDK/toolchain | javac, jar, javadoc | Determines the compiler and tools used |
| Build properties | Version, release, flags | Changes metadata and bytecode output |
| Environment | OS, locale, timezone, variables | Can affect resource filtering and reproducibility |

An artifact can differ even if the source code is unchanged when dependency versions, JDK, compiler flags, generated sources, or build configuration change. When investigating differences, record these inputs alongside the source revision.

### 2.1. Common Source Layout

A Java project following Gradle/Maven conventions typically looks like this:

~~~text
project/
├── src/
│   ├── main/
│   │   ├── java/
│   │   │   └── com/example/app/Main.java
│   │   └── resources/
│   │       └── app.properties
│   └── test/
│       ├── java/
│       │   └── com/example/app/MainTest.java
│       └── resources/
│           └── test-data.json
├── build.gradle   # or pom.xml
└── README.md
~~~

- src/main/java contains production sources.
- src/main/resources contains resources included in the production artifact.
- src/test/java contains test sources.
- src/test/resources contains resources used only for tests.

These directory names are not a requirement of javac. They are conventions automatically understood by build tools. If you invoke javac directly, you must specify the source files, output directory, and dependency paths explicitly.

## 3. From Java Source to Bytecode

The javac compiler reads source files, performs syntax and type analysis, checks access and dependencies, and then generates class files. A class file contains bytecode for the JVM, the constant pool, method/field information, attributes, and required metadata.

Example:

~~~java
package com.example.app;

public final class Main {
    public static void main(String[] args) {
        System.out.println("Hello, Java!");
    }
}
~~~

Compile with JDK 17:

~~~bash
mkdir -p build/classes
javac --release 17 -encoding UTF-8 -d build/classes src/main/java/com/example/app/Main.java
~~~

Result:

~~~text
build/
└── classes/
    └── com/
        └── example/
            └── app/
                └── Main.class
~~~

Meaning of the options:

- **--release 17:** compiles against the language, class-file target, and Java SE APIs of release 17.
- **-encoding UTF-8:** specifies the character encoding of the source files.
- **-d build/classes:** destination directory for class files following the package hierarchy.
- **-classpath / --class-path:** where to find dependency classes/JARs on the classpath.
- **--module-path:** where to find named modules or automatic modules.
- **-processorpath:** where to find annotation processors when separate configuration is needed.

Do not confuse --release with the JDK running javac. The compiler can run on a newer JDK while producing output compatible with an older release if that release is supported.

### 3.1. Class-file version

Every class file has a major version. The JVM uses this information to determine whether the bytecode belongs to a version it supports.

| Java release | Class-file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 24 | 68 |

For example, Java 17 produces major version 61. Running a newer class file on an older JVM can result in UnsupportedClassVersionError.

Inspect a class file:

~~~bash
javap -verbose -classpath build/classes com.example.app.Main
~~~

Look for the major version line in the output. If the build uses --release 17 but runtime reports a newer class version, check the actual compiler used, leftover stale output, or packaged dependency class files.

### 3.2. Generated Sources and Annotation Processors

Some projects generate Java source files during the build:

- Annotation processors generating mappers, metamodels, or implementations.
- OpenAPI/Protocol Buffers compilers generating client/server sources.
- Plugins generating sources from schemas or DSLs.
- Code generators creating classes from configuration.

Generated sources are usually written to the build directory rather than src/main/java. The build tool must run the generation task before compilation and add the output directory to the source set. If compilation runs before the generator, the typical error is missing classes or packages.

Do not manually edit generated files if they will be regenerated on the next build. Edit the schema, annotations, or generator configuration that produces them instead.

## 4. How Are Resources Included in an Artifact?

Resources are not compiled into classes by javac. The build tool or a copy command places resources into the output directory, preserving relative paths so the application can read them via the classpath or module path.

Example src/main/resources/app.properties:

~~~properties
message=Hello
~~~

The resource is copied to:

~~~text
build/classes/app.properties
~~~

The application can read it using Class.getResourceAsStream:

~~~java
try (InputStream input = Main.class.getResourceAsStream("/app.properties")) {
    if (input == null) {
        throw new IllegalStateException("Missing app.properties");
    }
    Properties properties = new Properties();
    properties.load(input);
}
~~~

A path starting with / is resolved from the root of the classpath resources. Omitting the leading / resolves the lookup relative to the class's package.

Resource filtering is a separate feature provided by build tools. Some projects replace placeholders in resources with version or environment values during the build. This can make artifacts differ between staging and production even from identical source code. Do not put secrets into packaged resources; secrets should be supplied via a secret manager, environment variables, or external configuration outside the artifact.

## 5. Where Do Tests Fit in the Pipeline?

Test sources are typically compiled separately and executed in a test JVM:

~~~text
Production:
src/main/java       -> build/classes/.../main
src/main/resources  -> build/resources/.../main

Test:
src/test/java       -> build/classes/.../test
src/test/resources  -> build/resources/.../test
~~~

Tests can access production classes and test dependencies. Test classes and test reports are generally not included in the production JAR.

Common test categories:

- Unit tests: verify individual classes or methods.
- Integration tests: verify interactions across modules, databases, filesystems, or services.
- Contract tests: verify compatibility with APIs or protocols.
- Smoke tests: verify that the artifact starts up and handles basic functionality.

A successful build does not automatically mean tests actually ran. If logs show NO-SOURCE, NO-SOURCE test, or tests skipped, check the corresponding task or phase before concluding the pipeline tested the code.

## 6. Packaging Classes and Resources into a JAR

A JAR is a ZIP-based archive that typically contains:

- Compiled class files.
- Runtime resources.
- META-INF/MANIFEST.MF.
- A module descriptor if it is a modular JAR.
- Signature metadata if the JAR is signed.

By default, a JAR does not embed every dependency used by the project. A standard JAR is usually a **thin JAR**: it contains only the application's own code, while dependencies are supplied separately on the classpath or module path.

### 6.1. Manifest and Main-Class

The manifest is metadata stored in META-INF/MANIFEST.MF. The Main-Class attribute specifies the class with the main method so the launcher can run the JAR via java -jar.

Example MANIFEST.MF:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.app.Main
Implementation-Version: 1.2.3

~~~

Package from the output directory:

~~~bash
jar --create --file build/hello-app.jar --manifest build/MANIFEST.MF -C build/classes .
~~~

In the command above:

- --create creates a new archive.
- --file specifies the target JAR file.
- --manifest specifies the manifest file.
- -C changes directory to build/classes before adding contents.
- The dot adds all contents of the output directory.

Run the executable JAR:

~~~bash
java -jar build/hello-app.jar
~~~

When using java -jar, the launcher obtains the entry point from Main-Class. You cannot pass a regular classpath alongside this command in the usual way; external dependencies must be configured according to the appropriate packaging or launcher mechanism.

### 6.2. Thin JAR vs. Fat/Uber JAR

| Type | Contents | How to run |
|---|---|---|
| Thin JAR | Application classes and resources | Supply dependencies via classpath or module path |
| Fat/uber JAR | Application and dependencies bundled into one archive | Usually run with java -jar |
| Modular JAR | Includes module-info.class and module descriptor | Run via module path/module launcher |
| WAR | Web application and web metadata/resources | Deploy to a servlet container or compatible runtime |

Fat JARs are typically built using dedicated plugins or tasks rather than default jar command behavior. When merging dependencies, you must handle duplicate filenames, service descriptors, licenses, signatures, and resource merging. Never copy signature metadata verbatim from signed dependencies into a new JAR because the archive contents have changed.

### 6.3. Modular JAR

If a module has module-info.java, the compiler generates module-info.class. When packaged, that file sits at the root of the JAR, making it an explicit modular JAR.

~~~java
module com.example.app {
    requires java.logging;
    exports com.example.app.api;
}
~~~

Inspect the module descriptor:

~~~bash
jar --describe-module --file build/hello-app.jar
~~~

A JAR without module-info.class placed on the module path can be treated as an automatic module. Its module name is taken from Automatic-Module-Name in the manifest if present, or derived from the JAR filename. Do not confuse an automatic module with an explicit modular JAR.

## 7. WAR, Runtime Images, and Installers

JAR is not the only format:

- **WAR:** packages a web application, classes, resources, and WEB-INF metadata; deployed to a servlet container or compatible application server.
- **jlink image:** creates a custom runtime image containing only the JDK modules needed by a modular application.
- **jpackage installer:** creates a platform-native installer package such as MSI, EXE, PKG, or DEB depending on the environment and options.
- **Container image:** contains the runtime, artifact, and deployment configuration to run the application in a container.

These formats operate at different layers. A JAR is an application artifact; a jlink image is a runtime image; jpackage produces an installer; a container image is a deployment unit. Do not call all of them JARs or assume that creating a JAR means you have created a complete installer.

## 8. How Are Dependencies Distributed with the Artifact?

With a thin JAR, dependencies must be available at runtime. Common approaches include:

1. Placing dependency JARs in a lib directory and configuring the classpath.
2. Using the module path if the application is modular.
3. Using the manifest Class-Path attribute for simple, fixed layouts.
4. Building a fat JAR with a plugin/task that supports merging.
5. Using a build-generated launcher or script to assemble the classpath.

Example running a thin JAR with a lib directory on Linux/macOS:

~~~bash
java -cp "build/hello-app.jar:lib/*" com.example.app.Main
~~~

On Windows, the path element separator is a semicolon:

~~~powershell
java -cp "build\hello-app.jar;lib\*" com.example.app.Main
~~~

Manifest Class-Path follows URI rules relative to the JAR's location, not an environment variable. When dependency paths change, an old manifest may point to the wrong location.

Do not use -cp as a substitute for the module path when the application declares requires for named modules. If using JPMS, provide the proper module path and module graph.

## 9. Gradle: From Source Set to JAR

With the Java plugin, Gradle provides standard tasks:

| Task | Purpose |
|---|---|
| compileJava | Compiles production sources |
| processResources | Copies/filters production resources |
| classes | Aggregates production classes and resources |
| compileTestJava | Compiles test sources |
| processTestResources | Copies test resources |
| test | Runs tests |
| jar | Builds the JAR |
| check | Runs verification tasks |
| build | Aggregates assemble and check |

Typical output layout:

~~~text
build/
├── classes/java/main/
├── resources/main/
├── classes/java/test/
├── resources/test/
├── reports/tests/
├── test-results/
└── libs/
    └── project-version.jar
~~~

Useful commands:

~~~bash
./gradlew clean
./gradlew compileJava
./gradlew test
./gradlew jar
./gradlew build
./gradlew tasks --all
./gradlew jar --info
~~~

A minimal build.gradle:

~~~groovy
plugins {
    id 'java'
}

group = 'com.example'
version = '1.2.3'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.named('jar') {
    manifest {
        attributes(
            'Main-Class': 'com.example.app.Main',
            'Implementation-Version': project.version
        )
    }
}
~~~

Toolchains select the JDK for Java tasks; the Gradle daemon JVM may differ from the compiler JDK. To view detected JDKs:

~~~bash
./gradlew -q javaToolchains
~~~

The Gradle Wrapper should be committed to the repository so the team and CI use the same Gradle version. Use the project's Wrapper instead of a global Gradle installation when verifying pipelines.

## 10. Maven: From Lifecycle to JAR

Maven uses a lifecycle with standard phases:

| Phase | Main work |
|---|---|
| validate | Validates project and configuration |
| compile | Compiles production sources |
| test | Runs unit tests |
| package | Creates the JAR/WAR |
| verify | Runs additional checks |
| install | Installs the artifact into the local repository |
| deploy | Uploads the artifact to a remote repository |

Some phases invoke earlier phases automatically. For example, mvn package runs all required phases before package, including compile and test in the default lifecycle.

Useful commands:

~~~bash
mvn clean
mvn compile
mvn test
mvn package
mvn verify
mvn install
mvn deploy
~~~

Typical output layout:

~~~text
target/
├── classes/
├── test-classes/
├── surefire-reports/
└── artifactId-version.jar
~~~

A minimal pom.xml for Java 17 and an executable JAR:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>hello-app</artifactId>
  <version>1.2.3</version>
  <properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <maven.compiler.release>17</maven.compiler.release>
  </properties>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-jar-plugin</artifactId>
        <version>3.4.2</version>
        <configuration>
          <archive>
            <manifest>
              <mainClass>com.example.app.Main</mainClass>
            </manifest>
          </archive>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
~~~

The Maven Wrapper should also be committed so CI and developers use the same Maven distribution. The Maven compiler plugin, jar plugin, surefire plugin, and other plugins should have their versions explicitly managed in the build.

## 11. Verifying the Artifact After Packaging

Do not stop at the BUILD SUCCESSFUL message. Inspect the actual generated file.

### 11.1. List JAR Contents

~~~bash
jar --list --file build/hello-app.jar
~~~

Check for:

- META-INF/MANIFEST.MF.
- Main classes and package hierarchy.
- Required resources.
- module-info.class if it is an explicit modular JAR.
- No unexpected sources, test classes, temporary files, or secrets.

### 11.2. Read the Manifest

~~~bash
jar --extract --file build/hello-app.jar META-INF/MANIFEST.MF
~~~

Open META-INF/MANIFEST.MF and verify Main-Class, Implementation-Version, Class-Path, or other required metadata. Note that the extract command writes files into the working directory; run it in a separate inspection directory if you do not want to write into the project.

### 11.3. Inspect Bytecode and Dependencies

~~~bash
javap -classpath build/hello-app.jar -verbose com.example.app.Main
jdeps --print-module-deps build/hello-app.jar
~~~

javap confirms whether the class file exists and shows its bytecode version. jdeps analyzes dependencies at the class/module level; it does not replace runtime tests and does not verify dynamic or reflection-based dependencies.

### 11.4. Compute Checksums

Windows PowerShell:

~~~powershell
Get-FileHash build/hello-app.jar -Algorithm SHA256
~~~

Linux/macOS:

~~~bash
sha256sum build/hello-app.jar
~~~

Checksums help detect file tampering or transfer corruption. Two builds producing different checksums do not necessarily mean the source changed; archive timestamps, entry ordering, manifest metadata, or time-dependent generated content can make files differ byte-for-byte.

### 11.5. JAR Signing

If a release requires signing, use jarsigner with securely managed keys and certificates:

~~~bash
jarsigner -keystore release-keystore.p12 -storetype PKCS12 build/hello-app.jar release-key
jarsigner -verify -verbose -certs build/hello-app.jar
~~~

Signing protects the integrity of signed entries and binds them to the signer certificate. Verification results should be evaluated alongside the trust chain, expiration, certificate policy, and warnings. Signatures do not replace checksums in transfer workflows; checksums also do not prove the publisher's identity.

Never commit private keys, keystore passwords, or signing credentials to source control or package them into artifacts.

## 12. Reproducible Builds

A build is reproducible when, given the same source revision and controlled inputs, it produces identical artifacts according to defined criteria—typically byte-for-byte.

Factors that can cause artifacts to differ:

- Per-entry timestamps in ZIP/JAR archives.
- File ordering inside the archive.
- JDK/compiler version and compiler flags.
- Unpinned dependency versions.
- Generated sources containing timestamps or absolute paths.
- Locale, timezone, and environment variables.
- Environment-specific resource filtering.
- Changing build plugin versions.
- Different file permissions or line endings.

Gradle can configure archive tasks:

~~~groovy
import org.gradle.api.tasks.bundling.AbstractArchiveTask

tasks.withType(AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

Maven Archiver supports an output timestamp via project.build.outputTimestamp. For example, configure a fixed property and let the JAR plugin use that value:

~~~xml
<properties>
  <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

Check the plugin version and its documentation to confirm the option is supported. Reproducibility also requires controlling dependencies, toolchains, generated content, and the environment; setting a timestamp alone does not guarantee the entire build is reproducible.

Dependency locking, checksum verification, and Wrappers help reduce input variability. Avoid dynamic versions such as latest or 1.+ in release builds when stable, repeatable artifacts are required.

## 13. CI, Artifact Repositories, and Deployment

A CI pipeline should clearly separate build, test, package, verify, and publish:

1. Check out the exact commit.
2. Install/select the JDK and build tool per project configuration.
3. Resolve dependencies according to lock/version policy.
4. Compile and run tests.
5. Package the artifact.
6. Verify contents, version, and checksum.
7. Sign the artifact if required by the release process.
8. Upload that exact artifact to the artifact repository/store.
9. Deploy that same artifact to the next environment.

Once an artifact is tested, promote that exact artifact through staging and production. Avoid rebuilding independently for each environment because a second build can produce different contents. Environment-specific configuration should be supplied outside the artifact whenever possible.

Metadata to record alongside a release:

- Artifact coordinates: group, artifact, version, classifier.
- Source revision/commit.
- JDK vendor/version and compiler release.
- Gradle/Maven Wrapper version.
- Dependency lock/manifest.
- Build timestamp or provenance record.
- SHA-256 checksum.
- Signature and signer identity, if applicable.
- Relevant test and verification results.

Artifact repositories typically keep versions immutable. If code fixes are needed, create a new version instead of overwriting an already published release.

## 14. Running the Artifact in the Target Environment

The artifact is created by the build tool, but the runtime determines whether it can execute.

For an executable JAR:

~~~bash
java -jar build/hello-app.jar
~~~

For a thin JAR:

~~~bash
java -cp "build/hello-app.jar:lib/*" com.example.app.Main
~~~

For a modular JAR:

~~~bash
java --module-path lib --module com.example.app
~~~

On Windows, the classpath separator is a semicolon; on Linux/macOS, it is a colon. Module path and classpath must be configured appropriately for the application type.

When deploying, verify:

- Does the JDK/runtime version support the class-file version?
- Are all dependencies present at the right versions?
- Are resources included in the artifact or available on the runtime path?
- Is the Main-Class or module name correct?
- Is external configuration available?
- Are ports, filesystem permissions, certificates, and network access properly configured?
- Are JVM options, memory limits, and container limits reasonable?

Never embed passwords, private keys, or secrets in a JAR. A JAR file can be extracted and read; secrets inside an archive cannot be protected simply by renaming the file.

## 15. Complete Java 17 Example: Source to Executable JAR

This example includes one Java class, one properties resource, and a manifest. It demonstrates compiling, copying resources, packaging, running, and inspecting.

Project structure:

~~~text
hello-app/
├── src/
│   ├── main/
│   │   ├── java/com/example/app/Main.java
│   │   └── resources/app.properties
└── build/
    └── MANIFEST.MF
~~~

Contents of src/main/java/com/example/app/Main.java:

~~~java
package com.example.app;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public final class Main {
    private Main() { }

    public static void main(String[] args) throws IOException {
        Properties config = new Properties();
        try (InputStream input =
                 Main.class.getResourceAsStream("/app.properties")) {
            if (input == null) {
                throw new IllegalStateException("Missing app.properties");
            }
            config.load(input);
        }

        String name = args.length == 0 ? "Java" : args[0];
        String version = Main.class.getPackage().getImplementationVersion();
        System.out.println(config.getProperty("message") + ", " + name + "!");
        System.out.println("ARTIFACT_VERSION=" + version);
        System.out.println("RESOURCE_STATUS=LOADED");
    }
}
~~~

Contents of src/main/resources/app.properties:

~~~properties
message=Hello
~~~

Contents of build/MANIFEST.MF:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.app.Main
Implementation-Version: 1.2.3

~~~

### 15.1. Compile

From the hello-app directory:

~~~bash
mkdir -p build/classes
javac --release 17 -encoding UTF-8 -d build/classes src/main/java/com/example/app/Main.java
~~~

### 15.2. Copy Resource

Linux/macOS:

~~~bash
cp src/main/resources/app.properties build/classes/
~~~

Windows PowerShell:

~~~powershell
Copy-Item src/main/resources/app.properties build/classes/
~~~

### 15.3. Package

~~~bash
jar --create --file build/hello-app.jar --manifest build/MANIFEST.MF -C build/classes .
~~~

### 15.4. Run the Artifact

~~~bash
java -jar build/hello-app.jar Toolchain
~~~

Output verified with Amazon Corretto 17.0.15+6-LTS on Windows:

~~~text
Hello, Toolchain!
ARTIFACT_VERSION=1.2.3
RESOURCE_STATUS=LOADED
~~~

### 15.5. Inspect the Artifact

~~~bash
jar --list --file build/hello-app.jar
javap -classpath build/hello-app.jar -verbose com.example.app.Main
jdeps --print-module-deps build/hello-app.jar
~~~

Verified results:

- The JAR contains META-INF/MANIFEST.MF.
- The JAR contains app.properties and com/example/app/Main.class.
- The class file has major version 61, corresponding to Java 17.
- The minimum module dependency is java.base.
- The program reads the resource from the JAR itself and retrieves Implementation-Version from the manifest.

You can compute the checksum after packaging:

~~~powershell
Get-FileHash build/hello-app.jar -Algorithm SHA256
~~~

The checksum will change if any bytes of the archive change, even when the program output remains identical.

## 16. Common Errors in the Source-to-Artifact Flow

| Symptom | Common cause | Resolution |
|---|---|---|
| Class does not appear in the JAR | Source was not compiled or package task did not pick up output | Check the compile task and source set |
| Resource cannot be read | Resource was not copied or wrong path | Check processResources, target/classes, and JAR contents |
| Build succeeds but java -jar reports no main manifest attribute | Missing Main-Class in manifest | Configure the manifest or jar plugin |
| java -jar cannot find dependencies | JAR is a thin JAR and dependencies were not provided | Configure classpath/module path, launcher, or fat JAR |
| UnsupportedClassVersionError | Bytecode is newer than the runtime JVM | Check class major version and --release |
| Artifact is missing generated classes | Generator did not run or output is not in the source set | Configure task dependencies and generated source directory |
| Tests do not run | Test sources not discovered or task skipped | Check test source set, test filters, and reports |
| JAR contains extra/secret files | Resource folder contains non-release data | Audit archive contents before publishing |
| JAR checksum differs across two builds | Different timestamps, ordering, generated content, or toolchain | Control reproducibility and build inputs |
| Artifact runs locally but fails on server | Different runtime/JDK, dependencies, config, or OS | Run the exact artifact on the target environment and compare baselines |
| Modular JAR fails to resolve | Missing module-info or wrong module path/requires | Use jar --describe-module and java --show-module-resolution |
| Signature invalid after modifying JAR | Archive changed after signing | Re-sign after the final packaging step |

## 17. Pre-Release Artifact Checklist

- [ ] Sources, resources, generated sources, and dependencies are identified.
- [ ] JDK/toolchain and compiler release are appropriately pinned.
- [ ] Production sources compiled successfully.
- [ ] Required resources are copied to the correct paths.
- [ ] Unit/integration tests ran and results are recorded.
- [ ] Artifact has the intended type (JAR/WAR/module/runtime image) for release.
- [ ] Manifest includes Main-Class and version metadata where needed.
- [ ] Runtime dependencies are provided properly.
- [ ] Archive contents inspected via jar --list.
- [ ] Bytecode inspected via javap when needed.
- [ ] Dependencies inspected via jdeps when needed.
- [ ] Checksum computed and stored alongside the artifact.
- [ ] Signature verified if required by the release process.
- [ ] Reproducibility and dependency locking are configured appropriately.
- [ ] CI stores the exact artifact that was tested.
- [ ] That exact artifact is promoted to the next environment.
- [ ] Runtime, configuration, permissions, and secrets are ready for deployment.

## 18. Key Takeaways

Sources, resources, generated sources, and dependencies are the inputs. The compiler translates Java source into bytecode in class files; the build tool handles resources and tests; the packaging task builds the JAR/WAR; the verification step checks contents, metadata, and dependencies; publishing distributes the artifact; and deployment runs it in an appropriate runtime.

A standard JAR does not bundle all dependencies automatically. The manifest defines the entry point and metadata; the module descriptor governs JPMS; checksums verify integrity; and signatures bind contents to a signer. A reliable build records its toolchain and dependencies, inspects the actual artifact, and delivers the exact tested file to the deployment environment.

References:

- [Oracle Java SE 17 — The javac Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)
- [Oracle Java SE 17 — The jar Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html)
- [Oracle Java SE 17 — The java Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
- [Oracle Java SE 17 — The javap Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html)
- [Oracle Java SE 17 — The jdeps Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html)
- [Oracle Java SE 17 — JAR File Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html)
- [Oracle Java SE 17 — JAR Manifest](https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html#jar-manifest)
- [Oracle Java SE 17 — jarsigner](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jarsigner.html)
- [Gradle — The Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html)
- [Gradle — Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html)
- [Gradle — Reproducible Archives](https://docs.gradle.org/current/userguide/working_with_files.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Maven JAR Plugin](https://maven.apache.org/plugins/maven-jar-plugin/)
- [Apache Maven — Maven Archiver](https://maven.apache.org/shared/maven-archiver/)
