# JAR Artifacts in Java

**JAR (Java Archive)** is a ZIP-based archive format used to bundle Java classes, resources, and metadata into a single file for execution, distribution, or reuse. A JAR can be a library for other applications, an executable application with a `Main-Class` entry point, an explicit module with `module-info.class`, or a multi-release JAR containing implementations for multiple Java versions.

In a build pipeline, a JAR is a **binary artifact** produced from source code and declared dependencies. The artifact needs a stable name/version, correct contents, inspectability, and must be stored or published where build consumers can access it. The JDK's `jar` tool allows direct manipulation of archives; Gradle and Maven integrate packaging into the build lifecycle.

## 1. What Does a JAR Contain?

A JAR is a ZIP archive. Entries inside use hierarchical paths with `/` separators, independent of the operating system's path separator.

Example structure of a typical JAR:

```text
jar-demo-1.2.3.jar
├── META-INF/
│   └── MANIFEST.MF
├── com/
│   └── example/
│       └── HelloApp.class
└── app.properties
```

| Entry | Role |
| --- | --- |
| `META-INF/MANIFEST.MF` | Archive and application metadata |
| `com/example/*.class` | Bytecode organized by package |
| Resources | Properties, templates, images, schemas, configuration files, etc. |
| `META-INF/services/` | Service Provider Configuration for `ServiceLoader` |
| `module-info.class` | Module descriptor if this is an explicit modular JAR |
| `META-INF/versions/N/` | Classes/resources targeting Java release N in a multi-release JAR |
| `META-INF/*.SF`, `*.RSA`, `*.DSA`, `*.EC` | Files used for digital signatures |

A JAR does not automatically include external dependencies. A JAR created by the Java plugin or the `jar` command is typically a **thin JAR**: it contains the module's own classes and resources, while dependencies are provided via the classpath, module path, or a separate runtime distribution.

A **fat/uber JAR** bundles both the application's classes and its dependencies into the same archive. This approach requires a dedicated plugin or packaging step; the basic `jar` command does not automatically resolve and copy dependencies.

## 2. Manifest and Metadata

The manifest is a text file at `META-INF/MANIFEST.MF`. The main section at the top contains attributes that apply to the entire archive; subsequent sections can contain attributes specific to individual entries.

Example:

```text
Manifest-Version: 1.0
Main-Class: com.example.HelloApp
Implementation-Title: JAR Artifact Demo
Implementation-Version: 1.2.3
Automatic-Module-Name: com.example.jardemo

```

Common attributes:

| Attribute | Meaning |
| --- | --- |
| `Manifest-Version` | Manifest format version |
| `Main-Class` | Class with `public static void main(String[] args)` to run with `java -jar` |
| `Class-Path` | Space-separated list of relative URLs to external dependency JARs/directories |
| `Implementation-Title` | Product or module name |
| `Implementation-Version` | Implementation version |
| `Implementation-Vendor` | Vendor |
| `Specification-Title`, `Specification-Version` | Metadata about the API specification |
| `Automatic-Module-Name` | Stable name when a JAR without `module-info.class` is used as an automatic module |
| `Multi-Release: true` | Marks a multi-release JAR |

The manifest must end its main section with a blank line. Headers are written in the form `Name: value`; header names are case-insensitive. Long lines are wrapped in the manifest format using continuation lines starting with a single space. When there is long metadata or Unicode characters, it is better to let `jar`, Gradle, or Maven generate the manifest instead of assembling the text file manually.

### Main-Class and Executable JARs

`Main-Class` specifies the entry point, not the `.class` file name, and omits the `.class` extension.

When the manifest has `Main-Class`, you can run:

```bash
java -jar jar-demo-1.2.3.jar
```

If `Main-Class` is missing, the command above does not know which class to run and will fail with an error. A typical library JAR does not need `Main-Class`; command-line applications usually do.

### Class-Path in the Manifest

`Class-Path` uses relative URLs, separated by spaces, resolved relative to the location of the JAR containing the manifest.

Example:

```text
Manifest-Version: 1.0
Main-Class: com.example.HelloApp
Class-Path: lib/logging.jar lib/http-client.jar
```

When the application is launched with `java -jar`, the launcher can locate the libraries at those relative paths. The dependency files must actually be distributed in that exact directory layout. `Class-Path` does not copy dependencies into the JAR and does not replace dependency version management.

Do not confuse `Class-Path` in the manifest with `-cp`/`-classpath` on the command line. When using `java -jar`, the launcher reads the entry point and additional classpath from the manifest; running with `-cp` is a different mode.

## 3. Creating a JAR Directly with the JDK

The JDK provides `jar` to create, list, update, extract, describe modules, and validate archives.

A sample program:

File `src/main/java/com/example/HelloApp.java`:

```java
package com.example;

import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

public final class HelloApp {
    private HelloApp() {
    }

    public static void main(String[] args) throws IOException {
        Properties properties = new Properties();

        try (InputStream input =
                 HelloApp.class.getResourceAsStream("/app.properties")) {
            if (input == null) {
                throw new IllegalStateException(
                    "app.properties is missing from the JAR"
                );
            }

            properties.load(
                new InputStreamReader(input, StandardCharsets.UTF_8)
            );
        }

        System.out.println("Hello from executable JAR");
        System.out.println("app.name=" + properties.getProperty("app.name"));
        System.out.println(
            "app.version=" +
            HelloApp.class.getPackage().getImplementationVersion()
        );
    }
}
```

File `src/main/resources/app.properties`:

```properties
app.name=jar-demo
```

Place the manifest at the project root, file `MANIFEST.MF`:

```text
Manifest-Version: 1.0
Main-Class: com.example.HelloApp
Implementation-Title: JAR Artifact Demo
Implementation-Version: 1.2.3
Automatic-Module-Name: com.example.jardemo

```

Compile the source to Java 17 bytecode and create the JAR:

```bash
mkdir -p build/classes
javac --release 17 -encoding UTF-8 \
  -d build/classes \
  src/main/java/com/example/HelloApp.java

jar --create \
  --file build/jar-demo-1.2.3.jar \
  --manifest MANIFEST.MF \
  -C build/classes . \
  -C src/main/resources .
```

`-C directory .` changes the working directory for the packaging operation to that directory and includes its contents in the archive. As a result, the JAR contains `com/example/HelloApp.class` and `app.properties` without including absolute paths from the build machine.

You can set a fixed timestamp for the archive on JDK versions that support the `--date` option:

```bash
jar --create \
  --file build/jar-demo-1.2.3.jar \
  --manifest MANIFEST.MF \
  --date=2026-11-10T00:00:00Z \
  -C build/classes . \
  -C src/main/resources .
```

A fixed timestamp is one part of a reproducible archive; achieving byte-for-byte reproducibility also requires pinning sources, toolchain, file order, metadata, and dependencies.

### Common `jar` Operations

| Purpose | Command |
| --- | --- |
| Create an archive | `jar --create --file app.jar -C classes .` |
| Create an executable JAR | `jar --create --file app.jar --main-class com.example.Main -C classes .` |
| List contents | `jar --list --file app.jar` |
| View details | `jar --list --verbose --file app.jar` |
| Update/add entries | `jar --update --file app.jar -C resources .` |
| Extract all | `jar --extract --file app.jar --dir extracted` |
| Extract selected entries | `jar --extract --file app.jar com/example/Main.class` |
| Describe module | `jar --describe-module --file app.jar` |
| Validate structure | `jar --validate --file app.jar` |

`--create`, `--list`, `--update`, and `--extract` are operation modes. `-C` specifies the root directory for the subsequent files in the command. You can use `@argfile` to read options and file lists from a text file when the command line becomes too long.

After creating the archive, inspect its contents and test running it:

```bash
jar --list --file build/jar-demo-1.2.3.jar
jar --validate --file build/jar-demo-1.2.3.jar
java -jar build/jar-demo-1.2.3.jar
```

Output of the sample program:

```text
Hello from executable JAR
app.name=jar-demo
app.version=1.2.3
```

This output was verified on JDK 24.0.2 with classes compiled using `javac --release 17`.

### Extract and Update

Extract into a separate directory:

```bash
jar --extract --file build/jar-demo-1.2.3.jar --dir build/extracted
```

You can then inspect `build/extracted/META-INF/MANIFEST.MF` or check resources. Do not extract untrusted archives into directories containing source code or important files. `jar --validate` checks for certain issues such as duplicate entries and paths, but it does not replace artifact provenance and security verification.

`jar --update` adds or replaces entries in an archive. Any modification to a JAR after it has been signed invalidates the signature; you must re-sign after all modifications are complete.

## 4. Thin JAR, Executable JAR, and Fat JAR

Three common packaging styles:

| Type | Contents | How to Run |
| --- | --- | --- |
| Library/thin JAR | Module's classes and resources | Placed on the classpath or module path |
| Executable/thin JAR | Classes/resources + `Main-Class`; external dependencies | `java -jar` with manifest `Class-Path` or runtime classpath |
| Fat/uber JAR | Application and dependency classes/resources bundled together | Usually `java -jar` if the manifest has `Main-Class` |

### Thin JAR with External Dependencies

You can run the application using the classpath:

```bash
# Linux/macOS: path-list separator is :
java -cp "build/jar-demo.jar:lib/*" com.example.HelloApp
```

```powershell
# Windows: path-list separator is ;
java -cp "build\\jar-demo.jar;lib/*" com.example.HelloApp
```

In real-world projects, let Gradle/Maven manage dependencies and the runtime classpath instead of assembling command lines manually. Separators differ by OS; `:` cannot be used as a classpath separator on Windows.

### Fat/Uber JAR

The Gradle Java Plugin and Maven JAR Plugin create the project's own JAR by default. To bundle dependencies, the Gradle Shadow Plugin or Maven Shade Plugin is commonly used.

When creating a fat JAR, pay attention to:

- Avoiding multiple versions of the same class in the archive.
- Resolving resource conflicts at the same path.
- Properly merging `META-INF/services/*` files so `ServiceLoader` can still discover providers.
- Checking dependency licenses and notices.
- Not retaining old signature files from dependencies that were modified or merged; re-sign the final artifact if needed.
- Only relocating packages when you understand the impact on reflection, service loaders, and class names configured as strings.

A fat JAR is convenient for simple deployments, but it can be larger, harder to control for duplicate dependencies, and harder to update individual libraries. For server applications, you can distribute a thin JAR alongside a `lib/` directory or use an application distribution/container image.


## 5. Creating a JAR with Gradle

The Gradle Java Plugin creates a `jar` task from the output of the `main` source set, including compiled classes and resources. By default, the task writes the archive to `build/libs/`.

Example `build.gradle`:

```groovy
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

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}

tasks.named('jar', Jar) {
    archiveBaseName = 'jar-demo'

    manifest {
        attributes(
            'Main-Class': 'com.example.HelloApp',
            'Implementation-Title': 'JAR Artifact Demo',
            'Implementation-Version': project.version,
            'Automatic-Module-Name': 'com.example.jardemo'
        )
    }
}
```

Run:

```bash
./gradlew clean jar
java -jar build/libs/jar-demo-1.2.3.jar
```

On Windows PowerShell, use `.\\gradlew.bat clean jar`.

Gradle produces:

```text
build/libs/jar-demo-1.2.3.jar
```

You can customize the archive name using:

- `archiveBaseName`: artifact base name.
- `archiveVersion`: version.
- `archiveClassifier`: classifier such as `sources`, `tests`, or `all`.
- `archiveExtension`: file extension.
- `destinationDirectory`: target directory.

The Gradle `Jar` task supports `manifest { attributes(...) }` to add metadata. Starting with Gradle 9, archive tasks use deterministic file ordering and fixed timestamps by default, supporting reproducible archives.

## 6. Creating a JAR with Maven

A Maven project defaults to `jar` packaging if no other packaging is declared. The `package` lifecycle phase invokes the Maven JAR Plugin to package compiled classes and resources.

Example `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>com.example</groupId>
  <artifactId>jar-demo</artifactId>
  <version>1.2.3</version>
  <packaging>jar</packaging>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <project.build.outputTimestamp>2026-11-10T00:00:00Z</project.build.outputTimestamp>
  </properties>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
        <configuration>
          <release>17</release>
          <encoding>UTF-8</encoding>
        </configuration>
      </plugin>

      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-jar-plugin</artifactId>
        <version>3.4.2</version>
        <configuration>
          <archive>
            <manifest>
              <mainClass>com.example.HelloApp</mainClass>
              <addDefaultImplementationEntries>true</addDefaultImplementationEntries>
            </manifest>
            <manifestEntries>
              <Automatic-Module-Name>com.example.jardemo</Automatic-Module-Name>
            </manifestEntries>
          </archive>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
```

Run:

```bash
mvn --batch-mode clean package
java -jar target/jar-demo-1.2.3.jar
```

In Maven, the JAR is located at `target/jar-demo-1.2.3.jar`. `maven-jar-plugin` supports configuring the manifest, includes/excludes, and timestamps for reproducible archives.

Both Gradle and Maven build archives from `src/main/java` and `src/main/resources`, but their task/plugin configurations differ. Pin plugin and build tool versions so results remain consistent between local environments and CI.

## 7. Artifact Coordinates, Version, and Classifier

The file name is only part of an artifact's identity. In Maven repositories, the standard coordinates are:

```text
groupId:artifactId:version[:classifier]:extension
```

Examples:

```text
com.example:jar-demo:1.2.3
com.example:jar-demo:1.2.3:sources
com.example:jar-demo:1.2.3:javadoc
```

Components:

- `groupId`: organization namespace/group, typically based on a reverse domain name.
- `artifactId`: module or library name.
- `version`: release version.
- `classifier`: distinguishes variants such as `sources`, `javadoc`, `tests`, `linux-x86_64`.
- `extension`: file type, such as `jar`, `pom`, `zip`.

A repository can store the JAR, POM or Gradle module metadata, checksums, and signatures side by side. Metadata describes dependencies and variants to resolve; you should not just download a single JAR file and infer the dependency graph yourself.

### Versioning Rules

- A release version such as `1.2.3` should be treated as immutable once published.
- A snapshot/pre-release version such as `1.3.0-SNAPSHOT` is for development; repositories may update snapshot metadata/artifacts.
- A classifier does not replace a version. `jar-demo-1.2.3-tests.jar` is still the test variant of version `1.2.3`.
- Do not overwrite an already published release artifact; create a new version when the binary changes.
- Attach build metadata or a commit ID to the manifest when build traceability is needed, but never put secrets in metadata.

## 8. Local Install and Repository Publishing

With Maven:

```bash
# Package the artifact
mvn clean package

# Install the artifact into the local Maven repository so other projects on the machine can use it
mvn install

# Publish to the repository configured in distributionManagement
mvn deploy
```

`install` writes the artifact to the user's local repository. `deploy` uploads the artifact to a remote repository according to the configuration and credentials. Never put passwords/tokens in `pom.xml` or commit them to Git; use `settings.xml`, a secret manager, or CI environment variables.

With Gradle, use `maven-publish`:

```groovy
plugins {
    id 'java'
    id 'maven-publish'
}

group = 'com.example'
version = '1.2.3'

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
        }
    }

    repositories {
        maven {
            name = 'internal'
            url = uri(System.getenv('MAVEN_REPO_URL'))

            credentials {
                username = System.getenv('MAVEN_REPO_USER')
                password = System.getenv('MAVEN_REPO_PASSWORD')
            }
        }
    }
}
```

Run `publish` to publish to the configured repository; `publishToMavenLocal` uses the local Maven repository. This example uses environment variables for the URL and credentials; provide those values in CI secret settings rather than hardcoding secrets in the build file.

Before publishing, verify coordinates, version, manifest, dependency metadata, JAR contents, and checksums. Never publish artifacts from a failed build or an unknown source revision.

## 9. Modular JAR and Automatic-Module-Name

Since Java 9, a JAR can be an explicit modular JAR if `module-info.class` is at the archive root.

Example `src/main/java/module-info.java`:

```java
module com.example.jardemo {
    exports com.example;
}
```

Compile the module:

```bash
javac --release 17 \
  -d build/module-classes \
  src/main/java/module-info.java \
  src/main/java/com/example/HelloApp.java

jar --create \
  --file build/jar-demo-module.jar \
  --main-class com.example.HelloApp \
  --module-version 1.2.3 \
  -C build/module-classes .
```

View the descriptor:

```bash
jar --describe-module --file build/jar-demo-module.jar
```

Run the module:

```bash
java --module-path build/jar-demo-module.jar \
  --module com.example.jardemo
```

`module-info.class` defines the module name, required modules, exported/open packages, and `uses`/`provides` services. `--module-version` records the version in the modular JAR's module descriptor.

A JAR without `module-info.class` but with `Automatic-Module-Name` can be placed on the module path under that automatic module name. Without this attribute, the automatic module name is derived from the JAR file name; renaming the file can change the module name. Libraries intending to support the module path long-term should consider a stable module name.

## 10. Multi-Release JAR

A multi-release JAR allows a single artifact to support multiple major Java releases. Baseline-compatible classes sit at the root; implementations for newer releases sit under `META-INF/versions/N/`.

Example structure:

```text
multi-release.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── versions/
│       └── 21/
│           └── com/example/RuntimeFeature.class
└── com/example/RuntimeFeature.class
```

The manifest must include:

```text
Manifest-Version: 1.0
Multi-Release: true

```

Create the archive using `jar --release`:

```bash
jar --create \
  --file build/library.jar \
  --manifest MANIFEST.MF \
  -C build/classes-base . \
  --release 21 \
  -C build/classes-21 .
```

When running on Java 21 or newer, the class loader selects the implementation version best matching the runtime, falling back to lower versioned directories and finally to the root. Java 17 will use the root version if no matching version 17 directory exists.

Notes:

- `N` must be a Java release of 9 or higher.
- The manifest must contain `Multi-Release: true`; simply placing files under `META-INF/versions/` is not enough.
- The public/protected API across versions must remain compatible according to the JAR specification.
- Resources in `META-INF` are not versioned by the multi-release mechanism.
- Use `jar --validate --file library.jar` to check certain constraints and API consistency.
- Do not create a multi-release JAR just to hold OS-specific files; use classifiers or separate artifacts for native binaries.

Multi-release JARs are useful when a library needs to leverage new APIs on newer JDKs while maintaining an older runtime baseline.


## 11. Verifying JAR Contents and Quality

Before releasing, inspect the archive rather than relying solely on the `package` task succeeding.

### Inspecting Files and the Manifest

```bash
jar --list --verbose --file build/jar-demo-1.2.3.jar
jar --describe-module --file build/jar-demo-1.2.3.jar
```

You can extract the manifest to inspect `Main-Class`, version, module name, classpath, and other attributes. Confirm that resources are located at the exact paths accessed by `Class.getResourceAsStream()` or `ClassLoader.getResource()`.

### Running from the Actual Archive

Run the JAR from a working directory different from the build's classes directory. This helps catch code that accidentally reads resources from the source filesystem instead of packaged resources.

```bash
java -jar build/jar-demo-1.2.3.jar
```

For libraries, create a small consumer test that resolves the dependency from the repository, compiles against it, and exercises the API. A JAR may contain all of the project's classes yet still lack dependencies or metadata required by consumers.

### Verifying Checksums

Generate a SHA-256 checksum to confirm two copies are byte-for-byte identical:

```bash
sha256sum build/jar-demo-1.2.3.jar
```

PowerShell:

```powershell
Get-FileHash .\\build\\jar-demo-1.2.3.jar -Algorithm SHA256
```

Checksums detect file modification during transfer or storage if the expected value comes from a trusted channel. A checksum downloaded from the same untrusted source does not by itself prove artifact provenance.

## 12. Signing and Verifying JARs

`jarsigner` uses a private key and certificate to sign a JAR; `jarsigner -verify` checks the signature and the integrity of signed entries.

Create a keystore for a test environment:

```bash
keytool -genkeypair \
  -alias release-key \
  -keyalg RSA \
  -keysize 3072 \
  -validity 365 \
  -keystore release.p12 \
  -storetype PKCS12
```

Sign the archive after all packaging steps are complete:

```bash
jarsigner \
  -keystore release.p12 \
  build/jar-demo-1.2.3.jar \
  release-key
```

Verify:

```bash
jarsigner -verify -verbose -certs build/jar-demo-1.2.3.jar
```

For real releases:

- Protect the private key using a secret store or HSM per organizational policy.
- Use a certificate chain trusted by recipients.
- Consider a timestamp authority so signatures can still be verified after the certificate expires.
- Verify both the signature and the trust chain; a `jar verified` message with a self-signed certificate does not mean the signer is trusted.
- Do not modify a JAR after signing; changing the manifest, classes, or resources causes signature verification to fail.
- Sign the exact final artifact that gets published—do not sign one copy and upload another.

Digital signatures verify integrity and signer identity under the certificate trust model. SHA-256 checksums and digital signatures serve different purposes; release pipelines may use both.

## 13. Reproducible JARs

A reproducible build means that the same source, toolchain, dependencies, and build instructions produce byte-for-byte identical artifacts. This helps verify that a binary was actually built from the reviewed source.

Factors that commonly cause JARs to differ:

- Timestamps of individual ZIP entries.
- File ordering inside the archive.
- Compiler/build plugin versions.
- Unpinned dependencies or dependencies that change over time.
- Manifests containing build timestamps or variable metadata.
- Generated resources containing absolute paths or build-machine details.

With JDK `jar`, you can use `--date` to set a fixed entry timestamp.

Gradle 9 creates reproducible archives by default with deterministic file ordering and fixed timestamps. For older Gradle versions or explicit declaration:

```groovy
tasks.withType(AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
```

With Maven, set `project.build.outputTimestamp` and use plugins that support reproducible output:

```xml
<properties>
  <project.build.outputTimestamp>2026-11-10T00:00:00Z</project.build.outputTimestamp>
</properties>
```

To verify, build twice in equivalent environments and compare SHA-256 hashes. If the hashes differ, check archive entry timestamps/ordering, the manifest, generated files, tool versions, and dependency resolution.

## 14. Troubleshooting JAR Artifacts

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `no main manifest attribute` | Manifest is missing `Main-Class` | Add `Main-Class` and rebuild |
| `Could not find or load main class` | Incorrect class name or class missing from JAR | Check `jar --list`, package, and manifest |
| `NoClassDefFoundError` | Missing runtime dependency | Provide classpath, manifest `Class-Path`, or a fat JAR |
| Resource returns `null` | Resource not packaged or wrong path | Check entries and use classpath resource APIs |
| `ClassNotFoundException` only on Linux | Case mismatch in entry or classpath | Check exact package and file names |
| `Invalid signature file digest` | JAR modified after signing or old signature files repackaged | Remove old signature files appropriately, produce final archive, and re-sign |
| Module not found | Wrong module path or unexpected module name | Use `jar --describe-module` and check the module descriptor |
| Runtime does not pick up versioned class | Missing `Multi-Release: true` or wrong version path | Check manifest and `META-INF/versions/N` |
| Different archive hash across two builds | Changing timestamps/order/metadata/toolchain | Configure reproducible builds and pin toolchain versions |
| JAR is too large | Unnecessary dependencies/resources bundled | Inspect contents, exclude files, and review fat JAR setup |
| Duplicate classes/resources | Multiple dependencies contain the same entry | Inspect dependency graph, exclusions, and shading |
| Consumer cannot resolve dependencies | Only JAR published, missing POM/module metadata or wrong coordinates | Publish with Maven/Gradle and verify repository metadata |
| JAR has resource but app cannot read it | Using filesystem path instead of classpath resource | Use `getResourceAsStream()` or `ClassLoader` |

## 15. Pre-Release JAR Artifact Management Checklist

1. Determine `groupId`, `artifactId`, version, and classifier.
2. Select JDK/compiler release and pin Gradle/Maven/plugin versions.
3. Compile, test, and build the JAR using the build task.
4. Inspect the manifest, classes, resources, module descriptor, and dependency metadata.
5. Test running the executable JAR or run a consumer test for a library.
6. Run `jar --validate` when appropriate.
7. Check licenses, secrets, dependency vulnerabilities, and disallowed contents.
8. Generate checksums and SBOM according to release policy.
9. Sign the exact final archive if required by the process.
10. Publish the JAR along with its metadata to the repository.
11. Confirm the artifact resolves and downloads back from the repository.
12. Archive checksums, signatures, build logs, commit ID, and release provenance.

Never publish artifacts from a workspace in an unknown state or from a build where tests/verification failed. Release artifacts should be tied to a specific source revision and never overwritten after publication.

## 16. Key Takeaways

- A JAR is a ZIP archive containing classes, resources, and metadata; internal entries use `/` separators.
- `META-INF/MANIFEST.MF` holds `Main-Class`, `Class-Path`, version, and module metadata.
- `java -jar` requires `Main-Class`; library JARs typically do not need an entry point.
- Standard JARs do not bundle dependencies automatically; distinguish between thin JARs and fat/uber JARs.
- `jar --create`, `--list`, `--update`, `--extract`, `--describe-module`, and `--validate` are the core operations.
- The Gradle Java Plugin provides the `jar` task; the Maven JAR Plugin packages during the `package` phase.
- Artifact coordinates and classifiers help repositories distinguish versions and variants.
- `module-info.class` creates an explicit modular JAR; `Automatic-Module-Name` gives an automatic module a stable name.
- Multi-release JARs require `Multi-Release: true` and the `META-INF/versions/N/` structure.
- SHA-256 verifies bytes; `jarsigner` signs and verifies integrity and the signer certificate.
- Reproducible builds allow recreating an archive byte-for-byte from the same inputs.
- Inspect contents and test the actual JAR before publishing.

The JAR artifact is the deployable and shareable output of a Java build. When archive structure, manifest, dependencies, versions, signatures, and provenance are managed clearly, artifacts are easier to run, verify, and trust throughout the development lifecycle.

## References

- [The jar Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jar.html)
- [JAR File Specification — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/jar/jar.html)
- [The jarsigner Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jarsigner.html)
- [Gradle: Building Java & JVM Projects — JAR manifest](https://docs.gradle.org/current/userguide/building_java_projects.html)
- [Gradle Jar Task DSL](https://docs.gradle.org/current/dsl/org.gradle.jvm.tasks.Jar.html)
- [Gradle: Reproducible archives](https://docs.gradle.org/current/userguide/working_with_files.html)
- [Apache Maven JAR Plugin 3.4.2](https://maven.apache.org/plugins-archives/maven-jar-plugin-3.4.2/plugin-info.html)
- [Maven: Configuring for Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html)
