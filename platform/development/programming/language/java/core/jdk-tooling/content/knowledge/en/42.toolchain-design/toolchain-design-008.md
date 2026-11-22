# Choosing Artifact Outputs in a Java Toolchain

**Artifact output** is the product that a build generates for another party to consume: a library JAR, a standalone executable application, a WAR deployed to an application server, a ZIP/TAR distribution package, an application image, a native installer, or a container image. Choosing the right output is an architectural decision of the toolchain because it affects execution, dependencies, runtime, security, updates, and deployment environments.

No single format fits every Java project. A library used as a dependency needs a different artifact than a CLI application, a web application, or a desktop application. A single project can also produce multiple outputs from the same source: a main JAR, a sources JAR, a Javadoc JAR, a distribution ZIP, and OS-specific installers.

This article provides a guide to choosing artifacts based on the deployment contract, distinguishing between output types, configuring Maven and Gradle, verifying actual artifacts, and organizing a reproducible release pipeline.

## 1. Start from Where the Artifact Will Be Used

Before choosing a plugin or packaging type, identify who receives the artifact and how they run it.

Five questions to answer:

1. **Who uses it?** Another Java application, an application server, a desktop user, a server operator, or a package manager?
2. **Where does it run?** An existing JVM, a container, a machine without Java installed, an application server, or a native environment?
3. **How are dependencies provided?** Via a Maven/Gradle repository, a lib directory, an application server, or bundled into the output?
4. **What is the deployment method?** Copying a JAR, running a script, deploying a WAR, running an installer, or pulling a container image?
5. **How are updates and rollbacks handled?** Replacing a file, deploying a new version, upgrading via a package manager, or replacing a container image?

The output must satisfy the exact contract between the build side and the deployment side. For example, a library used across multiple applications typically needs a thin JAR along with dependency metadata. A CLI released to end users might need a ZIP/TAR containing launcher scripts and dependencies. A desktop application might need an application image or a native installer.

### Deciding the output by consumer

| Consumer / environment | Typically suitable output | How it is used |
|---|---|---|
| Another Java application | Library JAR | Declare dependency in Maven/Gradle |
| CLI running on an existing JVM | Executable JAR or distribution ZIP | java -jar or launcher script |
| CLI needing bundled dependencies | Fat/shaded JAR or ZIP/TAR | Run via launcher with runtime classpath |
| Servlet container | WAR | Deploy to a compatible container |
| Jakarta EE application server | EAR or WAR per server contract | Deploy following enterprise structure |
| Java module consumer | Modular JAR | Use module path and JPMS |
| Desktop app | Application image or native installer | Dedicated launcher, runtime can be bundled |
| Server running in a container | Container image | Deploy via container platform |
| Environment without JVM dependency | Native executable | Separate native-image toolchain, e.g. GraalVM |
| Users needing source/API docs | Sources JAR and Javadoc JAR | Documentation and debugging, not a runtime output |

These are common choices, not mandatory rules. Always verify the target framework, runtime, and platform before finalizing.

## 2. Common Java Output Types

### Compiled classes directory

After the compile step, class files are typically located in:

~~~text
target/classes/                 # Maven
build/classes/java/main/        # Gradle
~~~

This is an intermediate output used for testing, packaging into a JAR/WAR, or running within the build. Normally, this directory is not released on its own because it lacks metadata, dependency declarations, and a complete distribution structure.

### Library JAR

A library JAR contains the class files, resources, and manifest of a library. Consumers declare the dependency by coordinates:

~~~text
com.acme.platform:customer-client:2.4.1
~~~

A library JAR usually does not need a Main-Class. The library's dependencies are described in a POM or Gradle Module Metadata; you should not embed all dependencies into a single JAR just to make it easier for users to copy.

It is good practice to also generate a sources JAR and a Javadoc JAR when publishing a library so IDEs and developers can view source code and API docs.

### Executable JAR

An executable JAR has a Main-Class in its manifest:

~~~text
Main-Class: com.acme.cli.Main
~~~

It can be run with:

~~~bash
java -jar app.jar
~~~

By default, an executable JAR can still be a **thin JAR**: containing only the application code. Other dependencies must be provided via the manifest Class-Path, a launcher script, or a framework's packaging mechanism.

Do not assume that having a Main-Class means the JAR already contains all dependencies. If a dependency is missing from the runtime classpath, the application may fail with NoClassDefFoundError.

### Fat JAR / shaded JAR

A fat JAR or shaded JAR packages the application code together with dependency classes/resources into a single archive. This is a convenient approach for a CLI or small service that needs one easy-to-run JAR file.

Advantages:

- Single-file distribution.
- Users do not need to set up a lib directory themselves.
- Easy to run with java -jar.
- Suitable for some simple deployment environments.

Disadvantages:

- Larger JAR size.
- Potential resource or class collisions.
- Requires proper merging of META-INF/services.
- Dependency licenses and notices must be handled.
- Signatures of dependency JARs usually become invalid after shading.
- Does not automatically guarantee JPMS or multi-release JAR compatibility.
- Bundled dependencies make it harder to replace an individual library.

Use a shaded/uber JAR when the deployment contract genuinely requires a self-contained archive. For large services or many dependencies, a distribution ZIP/TAR or a container image may be easier to manage.

### WAR

A WAR (Web Application Archive) packages a web application for deployment to a compatible servlet container. It typically contains:

~~~text
WEB-INF/
├── classes/
├── lib/
└── web.xml  # if the application uses a deployment descriptor
~~~

A WAR is suitable when the organization operates an application server/container and manages the web app lifecycle through that platform.

Things to check:

- Servlet / Jakarta Servlet API version.
- `javax.*` or `jakarta.*` namespace depending on the platform.
- Which dependencies are provided by the container.
- Context, security, and resource configurations.
- Whether the application server supports the exact framework/runtime.

Do not package the servlet API as a regular runtime dependency if the container must provide that API; Maven typically declares it with scope provided.

### EAR

An EAR (Enterprise Archive) can bundle multiple enterprise modules, such as a WAR, EJB JAR, and libraries. It is suitable for application servers that support Jakarta EE enterprise packaging. Do not use an EAR just because a project has multiple JARs; if you only need to distribute multiple independent files, a ZIP/TAR or a multi-module repository is usually simpler.

### Modular JAR

A modular JAR contains `module-info.class` and is used on the module path. This output is suitable when you want to expose APIs via `exports`, declare dependencies via `requires`, and enforce encapsulation.

A JAR with `module-info.class` can still be run as a regular JAR on the classpath, but when placed on the classpath, the module descriptor is not enforced as it is on the module path. Determine whether consumers will use the classpath or JPMS.

### Application image and native installer

An application image contains a launcher, application files, and a runtime image. Native installers such as MSI, EXE, DMG, PKG, DEB, or RPM provide an OS-native installation experience. `jpackage` can produce these output types.

An application image is not a native executable compiled from Java into machine code. It still executes bytecode on the bundled Java runtime.

### Runtime image

`jlink` creates a runtime image containing the required set of JDK modules. A runtime image can be used to run an application or serve as input to `jpackage` via `--runtime-image`. It does not include all application code and a launcher on its own unless packaged further.

### Distribution ZIP/TAR

A distribution archive contains multiple components:

~~~text
acme-cli/
├── bin/
│   ├── acme
│   └── acme.bat
├── lib/
│   ├── acme-cli.jar
│   └── dependency-*.jar
├── conf/
├── README.txt
└── LICENSE
~~~

This is a good choice when you need launcher scripts, sample configurations, multiple JARs, native libraries, and documentation. A ZIP/TAR can also contain an application image, provided the directory structure and executable permissions are preserved upon extraction.

### Sources, Javadoc, and test artifacts

Common supporting artifacts:

- sources JAR: source code corresponding to the binary.
- Javadoc JAR: API documentation.
- tests JAR: test classes/resources if the project intentionally publishes test fixtures.
- SBOM, checksum, signature, and provenance: release metadata.

These artifacts do not replace the runtime JAR. Only publish a test JAR when consumers genuinely need test fixtures or shared test utilities.

## 3. Distinguishing Fat JAR, Distribution, and Application Image

These three formats are often confused:

| Criterion | Fat JAR | Distribution ZIP/TAR | Application image |
|---|---|---|---|
| Application code | Yes | Yes | Yes |
| Dependencies | Merged into JAR | Separate JARs in lib | Files inside app image |
| Launcher | Main-Class or external script | Included scripts | Native launcher |
| Java runtime | Usually not bundled | May not be bundled | Usually bundled |
| Multiple config files | Harder to manage | Convenient | Can be included in image |
| OS-specific | Usually less OS-dependent if pure Java | May have OS-specific scripts | Yes |
| Used for | Single-file Java app | CLI/server distribution | Desktop or self-contained runtime app |

Choose a fat JAR if a single JAR file is the desired distribution contract. Choose a distribution when you need to manage multiple files and scripts. Choose an application image when you want a native launcher and a bundled runtime.

## 4. Technical Criteria for Choosing an Output

### Runtime availability

If the target environment already manages a JDK/JRE, a library JAR or a thin executable JAR may be sufficient. If users do not have Java installed, consider an application image/native installer or a native image.

### Dependency model

- Library: explicit dependency metadata.
- Thin executable JAR: dependencies provided via the runtime classpath.
- Fat JAR: dependencies are shaded/merged.
- WAR/EAR: the container may provide certain APIs/runtime.
- Container image: dependencies and runtime reside inside the image.

Do not bundle dependencies twice if the application server or container already provides them.

### Portability

Pure Java bytecode JARs can generally run across compatible OSes. Native libraries, launchers, installers, and native images depend on the OS/architecture. A distribution ZIP can be portable if it only contains Java code, though scripts and file permissions may need OS-specific variants.

### Module compatibility

If consumers use JPMS, check `module-info`, automatic module names, split packages, and service loading. Shading multiple modules into one JAR can erase module boundaries or cause the descriptor to no longer reflect the contents.

### Startup, memory, and size

A fat JAR does not inherently start faster than a library JAR. An application image is usually larger because it includes the runtime. A native image can reduce startup time for some workloads, but comes with trade-offs in build time, reflection/configuration, compatibility, and runtime behavior.

Measure on actual workloads before deciding, as startup, memory, and size depend on the application.

### Operations and update strategy

Choose an output that matches how operations are organized:

- Artifact repository: JAR/WAR/EAR with immutable versions.
- Server deploy: WAR or executable JAR.
- Desktop fleet: installer with identity and upgrade policy.
- Kubernetes: container image tag/digest.
- Linux workstation: DEB/RPM via a package repository.

### Security and compliance

Check dependency licenses, SBOM, signing, checksums, vulnerability scanning, and provenance. For fat JARs, merge license/notice files and handle dependency signatures. For installers, sign the artifact according to platform requirements.

## 5. Choosing Outputs by Project Type

### Library used by multiple applications

Recommendations:

- Main library JAR.
- POM/Gradle Module Metadata.
- Sources JAR.
- Javadoc JAR.
- SBOM/checksum/signature per release policy.

No Main-Class is needed. Do not shade dependencies by default because consumers need the ability to choose versions and resolve dependencies independently.

### Command-line tool

There are three common choices:

1. Executable JAR if users have Java and dependencies are simple.
2. Distribution ZIP/TAR if scripts, `lib/`, `conf/`, and docs are needed.
3. Native installer/application image if a native installation experience and dedicated runtime are desired.

Choose based on the target audience and deployment environment. An internal CLI might only need a distribution archive; a broadly distributed CLI might need an installer.

### Web service

Can be released as:

- Executable JAR for frameworks with an embedded server.
- WAR if the deployment target is a servlet container.
- Container image if the platform operates on containers.

Do not choose WAR or executable JAR out of habit. Follow the platform's deployment contract, configuration approach, and lifecycle management.

### Desktop application

Typically needs:

- Application image for smoke testing.
- Native installer for installation.
- Bundled runtime if you do not want to depend on pre-installed Java.
- Code signing/notarization per platform.

Build separately on Windows, macOS, and Linux; test on each target architecture.

### Enterprise application

If the application server requires an EAR, build an EAR following the server's module structure. Otherwise, multiple independent JARs/WARs deployed via separate pipelines can be simpler and easier to scale.

### Native executable

If the requirement is a native binary without needing a separate JVM runtime, consider GraalVM Native Image or an equivalent technology. This is a separate toolchain requiring verification of reflection, resource configuration, JNI, dynamic class loading, and compatibility. Do not call a `jpackage` application image a native image.

## 6. Maven: Choosing Packaging Types and Plugins

Maven `<packaging>` defines the basic lifecycle/package type. Common types include `jar`, `war`, `ear`, and `pom`. Additional plugins can generate extra outputs such as a shaded JAR, ZIP/TAR, or installer inputs.

### Library JAR

Minimal POM:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.acme</groupId>
    <artifactId>customer-client</artifactId>
    <version>2.4.1</version>
    <packaging>jar</packaging>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>
</project>
~~~

Build:

~~~bash
mvn clean package
~~~

Output:

~~~text
target/customer-client-2.4.1.jar
~~~

### Executable JAR

Add the Maven JAR Plugin to write Main-Class:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-jar-plugin</artifactId>
    <version>3.4.2</version>
    <configuration>
        <archive>
            <manifest>
                <mainClass>com.acme.cli.Main</mainClass>
                <addDefaultImplementationEntries>true</addDefaultImplementationEntries>
            </manifest>
        </archive>
    </configuration>
</plugin>
~~~

After building:

~~~bash
java -jar target/customer-client-2.4.1.jar
~~~

The command only succeeds if all runtime dependencies are present. Main-Class does not package dependencies automatically.

### Sources and Javadoc JAR

You can use the Maven Source Plugin and Javadoc Plugin to attach sources/Javadoc artifacts during the release lifecycle:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-source-plugin</artifactId>
    <version>3.3.1</version>
    <executions>
        <execution>
            <id>attach-sources</id>
            <goals><goal>jar-no-fork</goal></goals>
        </execution>
    </executions>
</plugin>
~~~

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-javadoc-plugin</artifactId>
    <version>3.11.2</version>
    <executions>
        <execution>
            <id>attach-javadocs</id>
            <goals><goal>jar</goal></goals>
        </execution>
    </executions>
</plugin>
~~~

Pin plugin versions and test Javadoc generation in CI. Javadoc failures can indicate incomplete API docs or toolchain incompatibility.

### WAR

Set:

~~~xml
<packaging>war</packaging>
~~~

and configure the Maven WAR Plugin. For the Servlet API provided by the container, declare the dependency with scope `provided`:

~~~xml
<dependency>
    <groupId>jakarta.servlet</groupId>
    <artifactId>jakarta.servlet-api</artifactId>
    <version>6.1.0</version>
    <scope>provided</scope>
</dependency>
~~~

Choose the exact version matching the target servlet container. Do not treat the example version here as a standard for every application server.

### Fat JAR with Maven Shade Plugin

The Shade Plugin creates a JAR with merged dependencies. Configure Main-Class and a service resource transformer if the application uses ServiceLoader:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-shade-plugin</artifactId>
    <version>3.6.0</version>
    <executions>
        <execution>
            <phase>package</phase>
            <goals><goal>shade</goal></goals>
            <configuration>
                <transformers>
                    <transformer implementation="org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
                    <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                        <mainClass>com.acme.cli.Main</mainClass>
                    </transformer>
                </transformers>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Also check for duplicate resources, license notices, signatures, multi-release entries, and module descriptors. Do not enable shading without a clear deployment reason.

### Distribution ZIP/TAR

The Maven Assembly Plugin or Maven Distribution Plugin can create a ZIP/TAR containing the JAR, lib, scripts, and docs. Define a descriptor to specify exactly which files go into the archive.

Example distribution contents:

~~~text
acme-cli/
├── bin/
├── lib/
├── conf/
└── README.md
~~~

Use `mvn package` or a goal bound to the lifecycle to create the archive. Inspect the archive listing and run the launcher after extracting into a clean directory.

## 7. Gradle: Choosing Plugins and Tasks

The Gradle Java Plugin creates class directories and JARs. The Application Plugin adds ways to run the application and build distributions. The War Plugin creates WARs. External plugins can create fat JARs or native packages.

### Library JAR

~~~groovy
plugins {
    id 'java-library'
}

group = 'com.acme'
version = '2.4.1'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Build:

~~~bash
./gradlew clean jar
~~~

The output is typically in:

~~~text
build/libs/<project-name>-2.4.1.jar
~~~

### Executable application and distribution

~~~groovy
plugins {
    id 'application'
}

group = 'com.acme'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'com.acme.cli.Main'
}
~~~

Useful tasks:

~~~bash
./gradlew run
./gradlew jar
./gradlew installDist
./gradlew distZip
./gradlew distTar
~~~

- `run`: runs the application in the Gradle environment.
- `jar`: creates the main JAR.
- `installDist`: creates a distribution directory with scripts and dependencies.
- `distZip`: creates a ZIP distribution.
- `distTar`: creates a TAR distribution.

The Application Plugin is suitable when you need to distribute multiple files instead of just a single JAR.

### WAR

~~~groovy
plugins {
    id 'war'
}

group = 'com.acme'
version = '2.4.1'
~~~

Build:

~~~bash
./gradlew war
~~~

The default output is in `build/libs`. Verify dependency scopes and target container compatibility.

### Changing the archive name

~~~groovy
tasks.named('jar', Jar) {
    archiveBaseName = 'customer-client'
    archiveVersion = project.version.toString()
    archiveClassifier = 'desktop'
}
~~~

Output name:

~~~text
build/libs/customer-client-2.4.1-desktop.jar
~~~

A classifier should represent a meaningful variant, such as `sources`, `javadoc`, `linux-x64`, or `tests`; do not use classifiers to hide multiple incompatible artifacts under the same name.

### Fat JAR on Gradle

The core Gradle Java Plugin does not provide a universal rule to merge all dependencies into a fat JAR. Use an appropriate plugin like the Shadow Plugin and pin its version; configure service file merging, manifest, licenses, and duplicate policies. For applications needing multiple files, an Application Plugin distribution is usually more transparent.

## 8. jlink, jpackage, and Container Images

### jlink runtime image

Use when you want to bundle the minimal set of required JDK modules:

~~~bash
jlink --add-modules java.base,java.logging,java.sql --strip-debug --no-header-files --no-man-pages --output build/runtime
~~~

The module list here is only an example; it must be determined from the application's actual dependencies. For a JPMS application, you can analyze with `jdeps` and inspect the module graph.

### jpackage application image

~~~bash
jpackage --type app-image --input input --name AcmeDesktop --main-jar app.jar --main-class com.acme.desktop.Main --dest dist
~~~

An application image typically contains a launcher, application files, and a runtime. Test running the image before creating a native installer.

### Native installer

On Windows, macOS, and Linux, `jpackage` can generate appropriate packages such as MSI/EXE, DMG/PKG, and DEB/RPM. Packages must be built on the target platform with the corresponding native toolchain.

### Container image

If the application runs in Kubernetes or a container platform, the final output may be an OCI container image. Building container images typically uses a Dockerfile/Buildpacks/Jib or an equivalent pipeline. Choose the base image, JRE/JDK, OS packages, user permissions, CA certificates, and architecture according to the runtime contract.

Do not confuse a container image with a JAR: the JAR is one part inside the container filesystem; the image also includes the runtime, OS layers, entrypoint, and metadata.

## 9. Output Structure and Naming Conventions

A project can produce multiple deliverables:

~~~text
release/
├── maven/
│   ├── customer-client-2.4.1.jar
│   ├── customer-client-2.4.1-sources.jar
│   └── customer-client-2.4.1-javadoc.jar
├── distribution/
│   └── acme-cli-2.4.1.zip
├── desktop/
│   ├── AcmeDesktop-2.4.1-windows-x64.msi
│   ├── AcmeDesktop-2.4.1-macos-aarch64.dmg
│   └── AcmeDesktop-2.4.1-linux-x64.deb
└── checksums/
~~~

Naming conventions should reflect:

- Product/artifact name.
- Version.
- Classifier or distribution type.
- OS and architecture when the output is platform-dependent.

For Maven repositories, use GAV and classifiers instead of arbitrary custom names. For release downloads, filenames should be easily recognizable while still mapping back to coordinates/versions.

### Do not publish intermediate outputs

Do not publish `target/classes`, `build/classes`, temporary staging directories, or intermediate files generated by plugins, unless there is a clear use case. Publish the final artifact that has been tested, signed, and checksummed.

## 10. Verifying Artifacts Before Release

A successful build does not prove the output satisfies the deployment contract.

### Inspecting a JAR

List contents:

~~~bash
jar --list --file target/app.jar
~~~

Inspect the manifest:

~~~bash
jar --extract --file target/app.jar META-INF/MANIFEST.MF
~~~

Verify `Main-Class` if `java -jar` is needed, `Implementation-Version`, service descriptors, and resources.

### Inspecting a modular JAR

~~~bash
jar --describe-module --file target/library.jar
~~~

Verify the module name, `requires`, `exports`, and packages.

### Testing an executable JAR

~~~bash
java -jar target/app.jar --help
~~~

Run it in the target runtime environment, not just via an IDE classpath. If the app needs dependencies outside the JAR, verify the launcher classpath or fat JAR.

### Testing a WAR

List the WAR contents and deploy to the exact target servlet container/version. Verify context startup, endpoints, security, static resources, database connections, and shutdown behavior.

### Testing a distribution

Extract into a clean directory:

~~~bash
unzip -l dist/acme-cli-1.0.0.zip
~~~

Then run the launcher script from the extracted directory. Do not run from the project root because the working directory and relative paths can mask packaging errors.

### Testing an application image/installer

Run the application image on a machine without a separate JDK. For native installers, test install, launch, upgrade, and uninstall on a clean VM for each OS/architecture.

### Verifying checksums and signatures

Windows PowerShell:

~~~powershell
Get-FileHash .\dist\app.jar -Algorithm SHA256
~~~

Linux/macOS:

~~~bash
sha256sum dist/app.jar
~~~

Verify signatures using the platform's tooling. Checksums must be compared against a trusted reference value; a hash by itself does not authenticate the publisher.

## 11. Reproducibility and Artifact Provenance

Two builds from the same source should produce comparable and traceable outputs. For archives, control:

- Entry order.
- Timestamps.
- Manifest metadata.
- File permissions.
- Line endings.
- Compiler/JDK version.
- Maven/Gradle and plugin versions.
- Dependency versions.
- Generated files.
- Absolute paths, hostname, and build time.

Maven can use `project.build.outputTimestamp` for reproducible archives. Gradle archive tasks provide `reproducibleFileOrder` and `preserveFileTimestamps`.

Record release metadata:

~~~text
Artifact: customer-client-2.4.1.jar
Version: 2.4.1
Git revision: abc1234
JDK: 24.0.2
Build tool: Maven 3.9.12
OS/architecture: windows-x64
SHA-256: <computed value>
~~~

The SHA-256 value must be computed from the final file; do not hard-code assumed checksums into source.

### Version and classifier

Version identifies the artifact release; classifier distinguishes variants. For example, `customer-client-2.4.1-sources.jar` and `customer-client-2.4.1.jar` belong to the same version but have different contents and purposes.

For native outputs, include OS/architecture in the filename and release metadata. Do not let a Windows artifact overwrite a Linux artifact just because they share the same version.

## 12. Anti-Patterns When Choosing Outputs

### Choosing fat JAR for every project type

Fat JARs are convenient for simple applications, but they are not the default choice for libraries, WARs, or every service. They make dependencies hard to replace and can cause resource/signature conflicts.

### Using a library JAR as an executable JAR

A library JAR does not necessarily have a Main-Class. Consumers should declare it as a dependency; do not expect every JAR to run with `java -jar`.

### Packaging container dependencies into a WAR

If the application server provides Servlet/Jakarta APIs, packaging another version can cause classloader conflicts. Use `provided` scope according to the container contract.

### Choosing an application image thinking it is a native machine-code binary

`jpackage` bundles a runtime and a launcher; bytecode still runs on the JVM. If a native executable is required, evaluate Native Image separately.

### Building an installer on a different OS

Native installers depend on the OS and toolchain. Build the output on the appropriate runner; do not copy a package from another platform and rename the extension.

### Using a single output for both library and application

One project can produce a library JAR and an executable distribution separately. Do not force a single archive to act as both a stable dependency and a deployment bundle containing all runtime dependencies.

### Publishing artifacts before testing

Artifacts must be smoke-tested and metadata-checked before publishing. A build exit code of 0 does not confirm that the application starts or deploys properly.

### Using the filename as the sole source of version

Filenames can be renamed. Keep the version in build metadata, manifest, repository coordinates, and release provenance.

## 13. Output Selection and CI Deployment Workflow

A clean pipeline can be organized as follows:

~~~text
Source + dependency lock
        |
        v
Compile / unit tests
        |
        v
Build primary artifact
        |
        +----> Library JAR + sources/Javadoc
        |
        +----> Executable JAR / WAR / EAR
        |
        +----> Distribution ZIP/TAR
        |
        +----> Application image / installer
        |
        +----> Container image
        |
        v
Smoke test each output
        |
        v
Verify metadata / dependency / licenses
        |
        v
Sign + checksum + provenance
        |
        v
Publish immutable release
~~~

Not every project needs every output. Only produce deliverables required by the deployment contract.

### Build matrix

For native outputs, use runners matching the OS/architecture:

| Runner | Output |
|---|---|
| Windows x64 | MSI/EXE, Windows app image |
| macOS arm64 | DMG/PKG, macOS app image |
| Linux x64 | DEB/RPM, Linux app image |
| Linux container runner | OCI image for target architecture |

Each runner needs the corresponding JDK, build tool, native packaging tools, and signing identity.

### Release gates

Before publishing:

1. Version and Git tag match.
2. Dependency tree is verified.
3. Artifact has the correct structure and metadata.
4. Smoke test passes using the packaged output itself.
5. OS/architecture is compatible.
6. License/SBOM and security scan pass policy.
7. Checksums and signatures are verified.
8. Artifact is stored immutably.

## 14. Java 17+ Lab: Creating an Executable JAR with Maven and a Distribution with Gradle

Sample program `Main.java`:

~~~java
package com.acme.output;

public final class Main {
    public static void main(String[] args) {
        System.out.println("Artifact output demo");
        System.out.println("Mode="
                + (args.length == 0 ? "default" : args[0]));
    }
}
~~~

### Maven executable JAR

POM:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.acme</groupId>
    <artifactId>output-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>com.acme.output.Main</mainClass>
                            <addDefaultImplementationEntries>true</addDefaultImplementationEntries>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Build:

~~~bash
mvn clean package
~~~

Output:

~~~text
target/output-demo-1.0.0.jar
~~~

Run:

~~~bash
java -jar target/output-demo-1.0.0.jar cli
~~~

Exact stdout:

~~~text
Artifact output demo
Mode=cli
~~~

This is an executable JAR without external dependencies. If you add dependencies, choose a thin JAR with a launcher classpath or configure the shade plugin in a controlled manner.

### Gradle distribution

`settings.gradle` file:

~~~groovy
rootProject.name = 'output-demo'
~~~

`build.gradle` file:

~~~groovy
plugins {
    id 'application'
}

group = 'com.acme'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'com.acme.output.Main'
}
~~~

Place `Main.java` in `src/main/java/com/acme/output/`.

Run:

~~~bash
./gradlew clean run distZip
~~~

Main outputs:

~~~text
build/libs/output-demo-1.0.0.jar
build/distributions/output-demo-1.0.0.zip
~~~

Output when run from Gradle:

~~~text
Artifact output demo
Mode=default
~~~

Extract the ZIP into a clean directory and run the script in `bin/` to verify the distribution does not depend on the project's working directory.

## 15. Artifact Output Selection Checklist

- Consumer and deployment environment have been identified.
- JAR, WAR, EAR, distribution, app image, installer, or container image has been chosen per the deployment contract.
- Library JAR has appropriate dependency metadata.
- Executable JAR has Main-Class if `java -jar` is used.
- Thin JAR has a clear runtime dependency classpath.
- Fat JAR handles service files, duplicate resources, licenses, and signatures.
- WAR/EAR is compatible with the container/application server.
- Modular JAR has the correct module name, `requires`, and `exports`.
- Distribution has the required launcher scripts, `lib`, `conf`, and docs.
- Application image contains a compatible runtime.
- Installer is built on the target OS/architecture.
- Native image is distinguished from a `jpackage` application image.
- Sources/Javadoc/test artifacts are only published when needed.
- Filename, version, and classifier are consistent.
- Artifact is verified by running/deploying the final output itself.
- Checksums, signatures, SBOM, and provenance are stored.
- Reproducibility and immutable release policies are enforced.

## 16. Key Terms to Remember

| Term | Meaning |
|---|---|
| Artifact output | Build product that is distributed or deployed |
| Library JAR | JAR serving as a dependency for another application |
| Executable JAR | JAR with Main-Class to run with java -jar |
| Thin JAR | JAR that does not bundle all dependencies |
| Fat/Shaded JAR | JAR bundling application code and dependencies |
| WAR | Web Application Archive |
| EAR | Enterprise Archive |
| Modular JAR | JAR with a module descriptor |
| Distribution archive | ZIP/TAR containing app, lib, scripts, and config |
| Application image | Launcher, application files, and runtime image |
| Runtime image | Custom Java runtime from jlink |
| Native installer | OS-specific installation package |
| Native image | Machine-code binary created by a native-image toolchain |
| Container image | Image containing filesystem, runtime, application, and entrypoint |
| Classifier | Label distinguishing artifact variants |
| Main-Class | Manifest attribute specifying the entry point |
| SBOM | Software Bill of Materials |
| Provenance | Information about source and process used to create an artifact |
| Immutable release | Released artifact that cannot be overwritten |

Choose artifact outputs by starting from how consumers will deploy and operate the application. Libraries typically need a JAR with dependency metadata; applications may need an executable JAR or distribution; web apps may need a WAR/EAR; desktop apps need an application image/installer; container platforms need an OCI image. After choosing, verify the final artifact itself in a production-like environment, keep versions/metadata synchronized, generate checksums, and keep releases immutable.

## References

- Apache Maven — POM Reference and Packaging: https://maven.apache.org/pom.html
- Apache Maven — Maven JAR Plugin: https://maven.apache.org/plugins/maven-jar-plugin/
- Apache Maven — Maven WAR Plugin: https://maven.apache.org/plugins/maven-war-plugin/
- Apache Maven — Maven Shade Plugin: https://maven.apache.org/plugins/maven-shade-plugin/
- Apache Maven — Maven Assembly Plugin: https://maven.apache.org/plugins/maven-assembly-plugin/
- Gradle — Java Plugin: https://docs.gradle.org/current/userguide/java_plugin.html
- Gradle — Application Plugin: https://docs.gradle.org/current/userguide/application_plugin.html
- Gradle — War Plugin: https://docs.gradle.org/current/userguide/war_plugin.html
- Oracle JDK 24 — jar Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jar.html
- Oracle JDK 24 — jlink Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jlink.html
- Oracle JDK 24 — jpackage Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jpackage.html
- Eclipse Adoptium — Java Packaging and Runtime Images: https://adoptium.net/
