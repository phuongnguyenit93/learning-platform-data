# Artifact Packaging in Java

An artifact is a distributable binary product generated from source code after the build process. In Java, an artifact is typically a JAR, WAR, EAR, ZIP/TAR distribution, or a runtime image that can be installed and run independently.

In CI/CD, artifact packaging transforms source code into a versioned binary with clear metadata and structure for testing, storage, release, and deployment. The artifact must contain the exact classes, resources, and dependencies required; run on the target runtime; and allow provenance identification and integrity verification.

A key principle is **build once, test once, and deploy that exact same artifact across environments**. Staging and production should receive the same tested binary, identified by its version and checksum. Do not rebuild the binary when promoting to production.

## 1. Artifacts in the CI/CD Lifecycle

~~~text
Source code
    |
    v
Compile + test
    |
    v
Package artifact
    |
    v
Verify + scan + sign
    |
    v
Publish immutable version
    |
    v
Deploy staging
    |
    v
Promote same artifact digest
    |
    v
Production
~~~

| Step | Output |
|---|---|
| Compile | Class files and processed resources |
| Test | Evidence that the code passes tests |
| Package | JAR, WAR, EAR, or distribution |
| Verify | Archive, manifest, dependency, and execution checks |
| Scan | Vulnerability and license scan results |
| Sign | Signature authenticating provenance and integrity |
| Publish | Artifact stored in a versioned repository |
| Promote | The same artifact moved to the next environment |

Do not treat the entire `target` or `build` directory as a release artifact. These directories can contain temporary classes, test reports, and intermediate files. CI should select only the final output file along with the metadata that needs to be stored.

## 2. Common Java Artifact Types

### JAR

A JAR is a ZIP-based archive that typically contains class files, resources, a `META-INF` directory, a manifest, and optionally a module descriptor or signature information. A JAR can be used as a dependency on the classpath or module path. A standard JAR is not necessarily executable directly via `java -jar`.

### Thin JAR

A thin JAR contains only the project's own code and resources. External dependencies are provided via the classpath or runtime distribution. Its advantages are small file size, separately managed dependencies, and suitability for libraries published to a Maven repository. Its disadvantage is that the required dependencies must be supplied when running the application; `Main-Class` in the manifest is not sufficient if the application needs external libraries.

### Executable JAR

An executable JAR has a manifest containing `Main-Class`. It can be run with:

~~~bash
java -jar application.jar
~~~

Example manifest:

~~~text
Manifest-Version: 1.0
Main-Class: com.acme.Application
Implementation-Title: artifact-demo
Implementation-Version: 1.0.0
~~~

An executable JAR can still be a thin JAR. `Main-Class` only specifies the entry point; it does not automatically bundle dependencies.

### Fat JAR or Shaded JAR

A fat JAR, also called an uber JAR, contains the application classes together with the required dependencies in a single archive. It is easy to distribute because there is only one file, but it is larger and can suffer from resource/class conflicts. `META-INF/services`, licenses, and signatures must be handled properly. The Maven Shade Plugin can bundle dependencies and relocate packages when needed.

### WAR, EAR, and Distributions

| Format | Purpose |
|---|---|
| WAR | Web application running in a servlet container or application server |
| EAR | Multiple enterprise components such as WARs and module JARs |
| ZIP/TAR distribution | Application, dependencies, launch scripts, and documentation |

A WAR typically contains `WEB-INF/classes`, `WEB-INF/lib`, and web resources. A ZIP/TAR distribution typically includes the main JAR, dependency JARs in `lib`, scripts in `bin`, sample configuration files, and licenses.

### Runtime Images and Installers

`jlink` creates a custom Java runtime image from the required modules. `jpackage` creates an application image or installer such as MSI, EXE, DEB, RPM, PKG, or DMG. These packages are intended for desktop applications or software that requires an installer, unlike JARs used as dependencies.

## 3. Choosing the Right Artifact Type

| Need | Artifact to Consider |
|---|---|
| Library used as a dependency | Thin JAR + POM/Gradle metadata |
| Library requiring IDE source lookup | JAR + sources JAR + Javadoc JAR |
| Command-line tool with few dependencies | Executable JAR |
| Application with many dependencies | Fat JAR or ZIP/TAR distribution |
| Web application | WAR |
| Enterprise application | EAR if required by the application server |
| Desktop app requiring an installer | `jpackage` installer |
| Modular app requiring its own runtime | `jlink` runtime image, optionally combined with `jpackage` |

A JAR with `Main-Class` that requires external libraries can still fail with `ClassNotFoundException` or `NoClassDefFoundError`. The manifest `Class-Path` can declare relative URLs to dependency JARs, but those paths and file distributions must be managed carefully. For applications with many dependencies, a distribution with a `lib` directory or a fat JAR is usually easier to operate.

## 4. Project Structure and the Maven Lifecycle

Example Maven structure:

~~~text
artifact-demo/
  pom.xml
  src/
    main/java/com/acme/ArtifactDemo.java
    main/resources/application.properties
    test/java/com/acme/ArtifactDemoTest.java
  target/
    classes/
    test-classes/
    surefire-reports/
    artifact-demo-1.0.0.jar
~~~

Convention: Java sources are placed in `src/main/java`; runtime resources in `src/main/resources`; and test sources in `src/test/java`. Do not include test classes, `.env` files, private keys, credentials, or IDE metadata in the archive.

Maven uses the following lifecycle phases:

| Phase | Role |
|---|---|
| validate | Validates the project and build information |
| compile | Compiles source code |
| test | Runs unit tests |
| package | Packages the JAR, WAR, or declared format |
| integration-test | Runs integration tests if configured |
| verify | Checks quality criteria and test results |
| install | Installs the artifact into the local Maven repository |
| deploy | Publishes the artifact to a remote repository |

Phases run sequentially. Create an artifact with:

~~~bash
mvn clean package
~~~

In CI, prefer:

~~~bash
mvn -B clean verify
~~~

`verify` runs the preceding phases and executes any configured integration tests or quality checks. Only use `mvn deploy` when the project has a configured remote repository and the pipeline is permitted to publish.

## 5. Creating an Executable JAR with Maven

The example below creates a JAR runnable with `java -jar`. The project has no external dependencies so that we can focus on the artifact structure.

File `src/main/java/com/acme/ArtifactDemo.java`:

~~~java
package com.acme;

public final class ArtifactDemo {

    private ArtifactDemo() {
    }

    public static void main(String[] args) {
        System.out.println("ARTIFACT_OK version=1.0.0");
    }
}
~~~

File `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.acme</groupId>
    <artifactId>artifact-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
    </properties>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
                <configuration><release>17</release></configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>com.acme.ArtifactDemo</mainClass>
                        </manifest>
                        <manifestEntries>
                            <Implementation-Title>artifact-demo</Implementation-Title>
                            <Implementation-Version>1.0.0</Implementation-Version>
                        </manifestEntries>
                    </archive>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Compile, test, and package:

~~~bash
mvn -B clean verify
~~~

The artifact is created at `target/artifact-demo-1.0.0.jar`.

Run the artifact:

~~~bash
java -jar target/artifact-demo-1.0.0.jar
~~~

Exact stdout:

~~~text
ARTIFACT_OK version=1.0.0
~~~

This example has no external dependencies. If dependencies are added, you must decide whether to distribute them separately or build a fat JAR.

## 6. Packaging Dependencies with the Maven Shade Plugin

When an application needs dependencies but you want to distribute a single file, you can use the Maven Shade Plugin.

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-shade-plugin</artifactId>
    <version>3.6.2</version>
    <executions>
        <execution>
            <phase>package</phase>
            <goals><goal>shade</goal></goals>
            <configuration>
                <filters>
                    <filter>
                        <artifact>*:*</artifact>
                        <excludes>
                            <exclude>META-INF/*.SF</exclude>
                            <exclude>META-INF/*.DSA</exclude>
                            <exclude>META-INF/*.RSA</exclude>
                            <exclude>META-INF/*.EC</exclude>
                        </excludes>
                    </filter>
                </filters>
                <transformers>
                    <transformer implementation=
                      "org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                        <mainClass>com.acme.ArtifactDemo</mainClass>
                    </transformer>
                    <transformer implementation=
                      "org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
                </transformers>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Run `mvn clean package`. The Shade Plugin is bound to the `package` phase and produces the shaded JAR.

Multiple dependencies can contain resources with the same name. An important example is `META-INF/services`. Java `ServiceLoader` reads these files to discover implementations; `ServicesResourceTransformer` merges service descriptors from all dependencies.

Resources such as `LICENSE` and `NOTICE` also need to be handled in accordance with dependency distribution terms. Signed dependency JARs may contain `META-INF/*.SF`, `*.RSA`, `*.DSA`, or `*.EC`. When Shade merges and modifies the archive contents, the original signatures can no longer validate the new contents. Exclude old signature files from the merged archive and re-sign the final artifact if needed.

If two dependencies have classes in overlapping packages or conflicting versions, the Shade Plugin can relocate packages. Relocation can affect reflection, serialization, resource names, and service descriptors; only use it after verifying those impacts.

## 7. Creating an Application Distribution with Gradle

The Gradle Java Plugin creates a JAR in `build/libs`. If an application needs dependencies and launch scripts, use the Application Plugin.

Example `build.gradle.kts`:

~~~kotlin
plugins {
    application
}
group = "com.acme"
version = "1.0.0"
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
application {
    mainClass.set("com.acme.ArtifactDemo")
}
tasks.jar {
    manifest {
        attributes(
            "Main-Class" to "com.acme.ArtifactDemo",
            "Implementation-Title" to project.name,
            "Implementation-Version" to project.version
        )
    }
}
~~~

Build and run checks:

~~~bash
./gradlew clean check
~~~

Create a ZIP distribution:

~~~bash
./gradlew distZip
~~~

Create a TAR distribution:

~~~bash
./gradlew distTar
~~~

Install the distribution into the build directory:

~~~bash
./gradlew installDist
~~~

Common outputs:

~~~text
build/
  libs/artifact-demo-1.0.0.jar
  distributions/artifact-demo-1.0.0.zip
  distributions/artifact-demo-1.0.0.tar
  install/artifact-demo/bin/
  install/artifact-demo/lib/
~~~

The Application Plugin generates start scripts and packages dependencies into `lib`. A ZIP/TAR distribution is an application package runnable via scripts, rather than a single fat JAR.

With Gradle 9, archive tasks use reproducible file ordering and fixed timestamps by default to support reproducible archives. For older Gradle versions, check or configure the corresponding archive properties.

## 8. Artifact Coordinates and Versioning

Maven identifies an artifact by the following components:

| Component | Meaning | Example |
|---|---|---|
| groupId | Organization/project namespace | com.acme |
| artifactId | Module name | artifact-demo |
| version | Release version | 1.0.0 |
| classifier | Variant differentiator | sources, javadoc, tests |
| type/packaging | Artifact format | jar, war, pom |

For example, the coordinates are `com.acme:artifact-demo:1.0.0`. The default filename is `artifact-demo-1.0.0.jar`. With a classifier, the file might be `artifact-demo-1.0.0-sources.jar` or `artifact-demo-1.0.0-javadoc.jar`.

Semantic Versioning typically uses `MAJOR.MINOR.PATCH`: `MAJOR` for incompatible API changes, `MINOR` for backward-compatible features, and `PATCH` for backward-compatible bug fixes.

`SNAPSHOT` is typically used for development builds that are not yet final releases. Release versions such as `1.0.0` should be treated as immutable. If a bug fix is needed after publishing, release `1.0.1` instead of overwriting the `1.0.0` file.

Build metadata can record the Git commit SHA, build number, JDK vendor/version, CI pipeline ID, dependency lock, or SBOM reference. Do not include dynamic timestamps in the archive if the goal is a reproducible build.

## 9. Inspecting JAR Contents with JDK Tools

List contents:

~~~bash
jar --list --file target/artifact-demo-1.0.0.jar
~~~

Validate archive integrity with JDK 26:

~~~bash
jar --validate --file target/artifact-demo-1.0.0.jar
~~~

This command checks for structural issues such as duplicate entries, unsafe paths, and API consistency of multi-release JARs. It does not replace functional testing or security scanning.

The manifest is located at `META-INF/MANIFEST.MF`. Check `Main-Class`, `Implementation-Version`, `Class-Path`, and `Multi-Release` if present.

For modular JARs:

~~~bash
jar --describe-module --file application.jar
~~~

Verify the module name, `requires`, `exports`, `uses`, and `provides` against the project's module design.

Run a smoke test:

~~~bash
java -jar target/artifact-demo-1.0.0.jar
~~~

A JAR can be a valid ZIP archive yet still be missing required classes, resources, or dependencies. A smoke test confirms that the launcher can run the artifact as expected.

## 10. Dependencies, Security, and CI Checks

An artifact that runs on the build machine is not guaranteed to run in production. Before publishing, verify runtime dependencies, `compile`/`runtime`/`provided` scopes, version conflicts, duplicate classes/packages, OS/architecture-dependent native libraries, service providers, and licenses.

With Maven:

~~~bash
mvn dependency:tree
~~~

With Gradle:

~~~bash
./gradlew dependencies
~~~

A pipeline should verify: build succeeds; unit/integration tests pass; correct file and version; valid manifest; archive contains no test classes, local configs, or secrets; runtime dependencies are complete; JAR validation and smoke test pass; license/vulnerability scans pass; and checksum, SBOM, and provenance are recorded.

Linux:

~~~bash
ls -lh target/artifact-demo-1.0.0.jar
jar --list --file target/artifact-demo-1.0.0.jar
jar --validate --file target/artifact-demo-1.0.0.jar
~~~

Windows PowerShell:

~~~powershell
Get-Item target/artifact-demo-1.0.0.jar
jar --list --file target/artifact-demo-1.0.0.jar
jar --validate --file target/artifact-demo-1.0.0.jar
~~~

Do not package passwords, API tokens, private keys, `.env` files, logs containing sensitive data, test fixtures with real data that must not be distributed, or IDE metadata.

You should have dependency vulnerability scanning, license compliance scanning, an SBOM in SPDX or CycloneDX format, SHA-256 checksums, release signatures, provenance recording the source commit/builder/build process, repository permissions, an immutable release policy, and appropriate retention.

## 11. Checksums and Artifact Signing

A checksum is a hash value of a file. SHA-256 is commonly used to determine whether two files have the same content.

Linux:

~~~bash
sha256sum target/artifact-demo-1.0.0.jar
~~~

Windows PowerShell:

~~~powershell
Get-FileHash target/artifact-demo-1.0.0.jar -Algorithm SHA256
~~~

Checksums help detect files that were altered or corrupted during upload/download. However, a checksum downloaded from the same source does not authenticate the publisher's identity. To verify origin, you need a digital signature or trusted provenance.

`jarsigner` signs JAR contents using a certificate/key. Java tooling can verify the signature and detect modified entries.

~~~bash
jarsigner -keystore release.p12 -storetype PKCS12 application.jar release-key
jarsigner -verify -verbose -certs application.jar
~~~

Private keys and passwords must be managed through a secret store or signing service. Do not commit keystores or credentials to the source repository. Perform shading, manifest updates, and resource merging before signing the final artifact.

Some repositories such as Maven Central require PGP signatures alongside the artifact and metadata. JAR signing and PGP signing are two different signature layers; follow the requirements of your repository and release policy.

## 12. Reproducible Builds

A reproducible build is the ability to produce an artifact with identical byte content when rebuilt from the same source, build instructions, and controlled environment.

### Maven

You can set a fixed timestamp for the archive:

~~~xml
<properties>
    <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

Use plugin versions that support reproducible builds and pin plugin versions. You can verify with:

~~~bash
mvn clean install
mvn clean verify artifact:compare
~~~

Local comparison is a basic check. For stronger independent verification, rebuild in a different environment while keeping the same source and build instructions.

### Gradle

Gradle 9 creates archives with reproducible file ordering and fixed timestamps by default. For older versions, check the configuration of `Jar`/`Zip` tasks:

~~~kotlin
tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
~~~

Other factors affecting reproducibility include JDK vendor/version, Wrapper version, plugin/dependency versions, generated sources, locale, timezone, environment variables, and timestamps or absolute paths embedded in the output.

Pin dependencies, use a wrapper, toolchain, and a deterministic build container. Do not add dynamic timestamps or build numbers into archive contents if byte-for-byte reproducibility is required.

## 13. Publishing Artifacts to a Repository

An artifact repository stores binaries and metadata for use by other projects or deployment pipelines. Examples include Maven Central, Nexus Repository, Artifactory, GitHub Packages, and internal repositories.

Maven uses `distributionManagement` in the POM to declare target repositories:

~~~xml
<distributionManagement>
    <repository>
        <id>internal-releases</id>
        <url>https://repo.example.com/releases</url>
    </repository>
    <snapshotRepository>
        <id>internal-snapshots</id>
        <url>https://repo.example.com/snapshots</url>
    </snapshotRepository>
</distributionManagement>
~~~

Credentials are configured separately in Maven `settings.xml`, with the server `id` matching the `id` in the POM. CI should retrieve credentials from a secret manager or secret variables.

Once the release is verified:

~~~bash
mvn deploy
~~~

The Deploy Plugin publishes the artifact, POM, and attached artifacts to the remote repository. Do not put usernames/passwords directly in `pom.xml`.

Maven Central now uses the Central Portal publishing flow. Do not assume the legacy OSSRH deployment process still applies; use Sonatype's current publishing guide and supported plugins.

The Gradle Maven Publish Plugin creates a Maven publication from a Java component and publishes it to a Maven-compatible repository:

~~~groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}
group = 'com.acme'
version = '1.0.0'
java {
    withSourcesJar()
    withJavadocJar()
}
publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
        }
    }
}
~~~

Repository URLs and authentication are configured in `publishing.repositories`. Do not hardcode credentials in `build.gradle`; use Gradle properties or CI secrets.

Release repositories should keep versions immutable. Snapshot repositories for development builds can be updated according to policy. Never upload two different binaries under the same release coordinates. If a release has a bug, increment the version and publish a new release.

## 14. jlink and jpackage for Self-Contained Runtime Applications

JARs typically require the user to have a compatible Java runtime installed. If you need to bundle the runtime with the application, you can use JDK packaging tools.

`jlink` creates a custom runtime image from the application module and its required modules:

~~~bash
jlink --module-path mods --add-modules com.acme.app --output build/runtime
~~~

`jlink` requires a module path containing the application module and all required modules. Developers are responsible for updating the runtime image when JDK updates or security patches are needed.

`jpackage` takes a built application and creates an application image or native installer:

~~~bash
jpackage --type app-image --name ArtifactDemo --input target/package-input --main-jar artifact-demo.jar --main-class com.acme.ArtifactDemo
~~~

The input directory must contain the main JAR and required dependencies. If the application uses external dependencies, they must be placed in the input directory with the classpath/runtime configured properly.

| Platform | Formats |
|---|---|
| Windows | exe, msi |
| Linux | deb, rpm |
| macOS | pkg, dmg |

`jpackage` generates a runtime using `jlink` if an existing runtime image is not provided. Installer creation must be performed on the target platform and may require additional tools such as WiX on Windows or Xcode tools on macOS.

If packaging an application that uses `ServiceLoader`, check the service provider modules in the runtime image. With JDK 25+, `jpackage` does not automatically include service bindings by default; you may need to pass the `jlink` option `--bind-services` when the application relies on service binding.

## 15. Artifacts in a CI/CD Pipeline

~~~text
Checkout source
      |
      v
Resolve pinned toolchain and dependencies
      |
      v
Compile + unit tests
      |
      v
Package JAR/WAR/distribution
      |
      v
Verify archive + smoke test
      |
      v
Security scan + SBOM
      |
      v
Checksum + signature + provenance
      |
      v
Publish immutable version
      |
      v
Deploy to staging
      |
      v
Promote same artifact digest
      |
      v
Production
~~~

Pipeline rules:

1. Build from a specific commit.
2. Use the Maven Wrapper or Gradle Wrapper.
3. Pin the JDK toolchain and plugin/dependency versions.
4. Run tests before publishing.
5. Verify the artifact after packaging.
6. Generate checksums and an SBOM.
7. Sign the artifact according to policy.
8. Upload to the repository with a unique version.
9. Store the artifact reference and digest in release metadata.
10. Deploy to staging using the published artifact.
11. After staging passes, promote the same artifact to production.
12. Do not rebuild the binary during promotion.

CI systems typically have an artifact upload feature to share files between jobs or store short-term build outputs. A dedicated artifact repository provides versioning, dependency metadata, retention, and access controls suitable for long-term distribution. Do not confuse CI job artifacts with a release repository, as each has different retention and access policies.

## 16. Troubleshooting Artifact Packaging

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Failed to create JAR | Compile/test/package failed | Read Maven/Gradle errors and fix the first failing phase |
| JAR missing resources | Resources in the wrong directory or excluded | Place them in `src/main/resources` and inspect the archive |
| `java -jar` reports no main manifest attribute | Manifest missing `Main-Class` | Configure `Main-Class` in the manifest |
| `ClassNotFoundException` at runtime | Thin JAR missing runtime dependencies | Create a distribution or shaded JAR |
| `NoClassDefFoundError` | Missing dependency or version conflict | Inspect the runtime dependency tree |
| `ServiceLoader` cannot find provider | `META-INF/services` lost during shading | Use `ServicesResourceTransformer` |
| `SecurityException` when using shaded JAR | Old dependency signature files remain in archive | Exclude old signature files and sign the final artifact if needed |
| Unusually large JAR | Wrong dependencies, test data, or resources bundled | Check `jar --list` and the dependency graph |
| Wrong version in filename | Build version and release version out of sync | Verify coordinates and pipeline variables |
| Publish fails | Incorrect repository URL, permissions, or credentials | Check `settings.xml`, server `id`, and CI secrets |
| Publishing same version rejected | Release repository enforces immutability | Increment version and publish a new release |
| Checksum mismatch | Corrupted file or modified artifact | Re-download from a trusted source and verify digest |
| Invalid signature | Archive modified after signing or wrong key | Sign only after the final package step and verify certificate |
| Rebuild produces different hash | Unstable timestamps, file order, or environment | Check reproducible build settings, toolchain, and plugins |
| Installer missing modules | Runtime image missing dependencies/modules/service bindings | Check module graph and `jlink` options |
| Artifact works on build machine but fails in production | Differences in runtime/JDK/OS/dependencies | Smoke test in a production-like environment |

## 17. Reproducible Artifact Packaging Checklist

1. Choose the artifact type based on how the application is used.
2. Finalize `groupId`, `artifactId`, `version`, and `classifier`.
3. Pin the JDK, Maven/Gradle Wrapper, plugins, and dependencies.
4. Specify the target Java release using compiler release/toolchain.
5. Run `validate`, `compile`, and `test`.
6. Package the appropriate JAR, WAR, EAR, or distribution.
7. Inspect the manifest, module descriptor, and resources.
8. Confirm runtime dependencies can be resolved.
9. Run `jar --validate` and smoke test the artifact.
10. Scan dependencies, licenses, and sensitive content.
11. Generate an SBOM, checksums, and signatures per policy.
12. Publish the release version to the repository.
13. Record the binary's digest and provenance.
14. Deploy to staging from the exact published artifact.
15. Promote the same digest to production after testing passes.
16. Retain artifacts and metadata according to the retention policy.

## 18. Key Takeaways

- An artifact is the distributable binary output of the build process.
- A JAR contains classes/resources; `Main-Class` gives a JAR an entry point but does not automatically bundle dependencies.
- Thin JARs suit libraries; fat/shaded JARs bundle dependencies; ZIP/TAR distributions include scripts and `lib`.
- WAR and EAR are intended for web and enterprise deployment models respectively.
- `jlink` creates a custom runtime image; `jpackage` creates an application image or installer.
- Maven `package` builds the artifact; `verify` runs checks; `install` puts it in the local repository; `deploy` publishes it to a remote repository.
- The Gradle Java Plugin creates a JAR; the Application Plugin creates a distribution with dependencies and start scripts.
- Artifact coordinates consist of `groupId`, `artifactId`, `version`, `classifier`, and `type`.
- Release versions should be immutable; to fix bugs, publish a new version.
- Inspect JAR contents, manifest, dependencies, and run a smoke test after packaging.
- Shading must handle duplicate resources, service descriptors, and signature files.
- Checksums verify content; signatures authenticate origin; provenance records the build process.
- Reproducible builds allow comparing binaries rebuilt from the same source and build environment.
- Do not include secrets or local files in an artifact.
- Build once, test, and deploy the same binary across environments.

## Official References

- [JAR File Specification — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/jar/jar.html)
- [The jar Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jar.html)
- [Introduction to the Maven Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle)
- [Maven JAR Plugin — Usage and Manifest Customization](https://maven.apache.org/plugins/maven-jar-plugin/usage.html)
- [Apache Maven Shade Plugin — Usage](https://maven.apache.org/components/plugins/maven-shade-plugin/usage.html)
- [Maven Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html)
- [Maven Deploy Plugin](https://maven.apache.org/plugins/maven-deploy-plugin/)
- [Gradle Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html)
- [Gradle Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html)
- [Gradle Reproducible Archives](https://docs.gradle.org/current/userguide/working_with_files.html)
- [The jlink Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html)
- [The jpackage Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html)
- [Packaging Overview — JDK 26](https://docs.oracle.com/en/java/javase/26/jpackage/packaging-overview.html)
- [Sonatype Central — Immutability of Published Components](https://central.sonatype.org/publish/requirements/immutability/)
