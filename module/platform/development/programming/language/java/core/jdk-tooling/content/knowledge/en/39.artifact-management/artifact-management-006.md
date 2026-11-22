# Artifact Metadata in the Java Ecosystem

In the Artifact Management group, metadata is the information that helps build tools, repositories, and users identify, resolve, verify, and consume a built binary. For Java libraries, metadata appears in many places: Maven POMs, `maven-metadata.xml` in repositories, Gradle Module Metadata (`.module`), manifests inside JARs, the `module-info.class` module descriptor, checksums, and signatures.

These metadata types serve different purposes. POMs and `.module` files describe the component, its dependencies, and how consumers use the artifact. `maven-metadata.xml` helps repositories locate versions or map SNAPSHOTs. Manifests describe JAR and application attributes. `module-info.class` describes a Java module. Checksums and signatures support integrity and provenance verification.

This lesson uses Maven 3.9.12, Gradle 9.2.1, and Zulu/OpenJDK 24.0.2. The Java example is compatible with Java 17+. A sample library was published to a local file repository using both Maven and Gradle, and its POM, repository metadata, Gradle `.module`, JAR manifest, module descriptor, and checksums were inspected.

## 1. Where Does Metadata Sit in the Artifact Lifecycle?

An artifact is not just a JAR file. Consumers need to know which component the file belongs to, which version it is, which dependencies it requires, and which compile/runtime contexts it can be used in.

~~~text
Source + build configuration
          |
          v
    Compile / Package
          |
          v
      Library JAR
       |       |
       |       +--> META-INF/MANIFEST.MF
       |       +--> module-info.class (if modular)
       |       +--> embedded build metadata (tool-specific)
       |
       v
   Publish to repository
       |
       +--> artifact JAR
       +--> POM / Gradle .module
       +--> sources / Javadoc JAR
       +--> maven-metadata.xml
       +--> checksums / signatures
                    |
                    v
            Dependency resolution
                    |
                    v
              Consumer build
~~~

Metadata can be divided into four groups:

| Group | Examples | Role |
|---|---|---|
| Component metadata | `pom.xml`, `.module` | Coordinates, dependencies, variants, capabilities |
| Repository metadata | `maven-metadata.xml` | Version list, snapshot timestamps, plugin prefixes |
| Archive metadata | `MANIFEST.MF`, `module-info.class` | JAR attributes, entry point, module graph |
| Integrity/provenance | `.sha256`, `.asc`, JAR signature, SBOM | File verification, signer, and software bill of components |

A metadata file may sit next to the JAR in a repository or inside the JAR itself. Do not confuse the sidecar POM with `META-INF/maven/.../pom.xml`, which some build plugins embed inside the JAR.

## 2. Maven Coordinates: Identifying Artifacts with GAV

Maven identifies a primary component using three coordinates:

- `groupId`: the organization or namespace that owns the component.
- `artifactId`: the component name.
- `version`: the released version.

Example:

~~~xml
<groupId>com.example</groupId>
<artifactId>metadata-demo</artifactId>
<version>1.2.0</version>
<packaging>jar</packaging>
~~~

The GAV of this component is `com.example:metadata-demo:1.2.0`.

In the Maven repository layout, dots in `groupId` are converted into directories:

~~~text
Repository root/
  com/
    example/
      metadata-demo/
        1.2.0/
          metadata-demo-1.2.0.pom
          metadata-demo-1.2.0.jar
          metadata-demo-1.2.0-sources.jar
          metadata-demo-1.2.0-javadoc.jar
~~~

`packaging` determines the primary artifact type and how Maven binds lifecycles/plugins. For Java libraries, `jar` is the standard packaging. `war`, `pom`, `maven-plugin`, and other packaging types follow their respective rules.

Beyond GAV, a file is further identified by its extension and classifier:

- Extension is the file type, such as `jar`, `pom`, `zip`.
- Classifier distinguishes variants attached to the same GAV, such as `sources`, `javadoc`, `tests`, `linux-x86_64`.

Example of a dependency with a classifier:

~~~xml
<dependency>
  <groupId>com.example</groupId>
  <artifactId>metadata-demo</artifactId>
  <version>1.2.0</version>
  <classifier>tests</classifier>
  <type>test-jar</type>
</dependency>
~~~

Do not invent or add a classifier just because a file has a different name. A classifier must be declared and published properly in the component metadata.

## 3. POM: Component Metadata for Maven

A POM is an XML project model. The POM is published alongside the artifact and read by Maven to obtain coordinates, the dependency graph, licenses, SCM, developers, and other project information.

A POM with basic metadata:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>com.example</groupId>
  <artifactId>metadata-demo</artifactId>
  <version>1.2.0</version>
  <packaging>jar</packaging>

  <name>Metadata Demo</name>
  <description>Example library that demonstrates artifact metadata.</description>
  <url>https://example.com/metadata-demo</url>

  <licenses>
    <license>
      <name>Apache License, Version 2.0</name>
      <url>https://www.apache.org/licenses/LICENSE-2.0</url>
    </license>
  </licenses>

  <developers>
    <developer>
      <id>example-team</id>
      <name>Example Team</name>
    </developer>
  </developers>

  <scm>
    <connection>scm:git:https://example.com/metadata-demo.git</connection>
    <url>https://example.com/metadata-demo</url>
  </scm>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.example</groupId>
      <artifactId>api-support</artifactId>
      <version>2.4.0</version>
      <scope>compile</scope>
    </dependency>
  </dependencies>
</project>
~~~

Key sections:

- `name`, `description`, `url`: help users understand the component.
- `licenses`: declares the license applicable to the artifact.
- `developers`: development team information.
- `scm`: source control location and connection.
- `properties`: build properties that plugins can use.
- `dependencies`: dependencies that consumers need to resolve.
- `dependencyManagement`: manages default versions within a dependency family; by itself it does not add dependencies to the classpath.
- `distributionManagement`: target repositories for deploying releases/SNAPSHOTs.

Dependency scope affects where a dependency is used and how it propagates to consumers. Common scopes are `compile`, `provided`, `runtime`, `test`, `system`, and `import` (in dependency management with a POM BOM). Choose the scope according to the library's true contract; declaring the wrong scope can cause a dependency to be missing at runtime or leak unnecessary dependencies to consumers.

The POM is metadata for build tools, not a manifest file inside the JAR. If a user downloads a standalone JAR without a repository/POM, Maven cannot automatically know that library's transitive dependencies.

## 4. Repository Metadata `maven-metadata.xml`

`maven-metadata.xml` is metadata managed by a Maven repository. It is neither a POM nor a binary artifact. Maven reads it automatically during version lookup, SNAPSHOT resolution, and Maven plugin discovery.

There are three main metadata locations:

1. **Group level:** located in the `groupId` directory, primarily mapping plugin prefixes to `artifactId`.
2. **Artifact level:** located in the `groupId/artifactId` directory, describing the version list, `latest`, `release`, and `lastUpdated`.
3. **Version level:** located in the base SNAPSHOT version directory, describing the timestamp/build number and mapping to individual snapshot files.

Example of artifact-level metadata:

~~~xml
<metadata>
  <groupId>com.example</groupId>
  <artifactId>metadata-demo</artifactId>
  <versioning>
    <latest>1.2.0</latest>
    <release>1.2.0</release>
    <versions>
      <version>1.0.0</version>
      <version>1.1.0</version>
      <version>1.2.0</version>
    </versions>
    <lastUpdated>20261110120000</lastUpdated>
  </versioning>
</metadata>
~~~

Repository managers can update this metadata when artifacts are deployed. Do not manually edit `maven-metadata.xml` to force Maven to use a specific JAR file; if repository metadata is inconsistent, fix the publishing process or rebuild metadata through the repository's official administrative features.

Maven metadata usually has checksum sidecars depending on repository configuration. When downloading artifacts, Maven can use the metadata and checksums to resolve and verify files.

## 5. SNAPSHOT Metadata and Timestamped Versions

`1.2.0-SNAPSHOT` is a mutable base version that changes when a team deploys a new build. In a remote Maven repository, each SNAPSHOT deployment is typically stored under a name containing a timestamp and build number.

For example, the version directory remains:

~~~text
com/example/metadata-demo/1.2.0-SNAPSHOT/
~~~

But the artifact files may be:

~~~text
metadata-demo-1.2.0-20261110.120000-3.jar
metadata-demo-1.2.0-20261110.120000-3.pom
maven-metadata.xml
~~~

Version-level metadata maps the base version `1.2.0-SNAPSHOT` to a specific snapshot:

~~~xml
<metadata modelVersion="1.1.0">
  <groupId>com.example</groupId>
  <artifactId>metadata-demo</artifactId>
  <version>1.2.0-SNAPSHOT</version>
  <versioning>
    <snapshot>
      <timestamp>20261110.120000</timestamp>
      <buildNumber>3</buildNumber>
    </snapshot>
    <snapshotVersions>
      <snapshotVersion>
        <extension>jar</extension>
        <value>1.2.0-20261110.120000-3</value>
        <updated>20261110120000</updated>
      </snapshotVersion>
      <snapshotVersion>
        <extension>pom</extension>
        <value>1.2.0-20261110.120000-3</value>
        <updated>20261110120000</updated>
      </snapshotVersion>
    </snapshotVersions>
  </versioning>
</metadata>
~~~

Consumers declare `1.2.0-SNAPSHOT`; Maven reads the metadata to locate the corresponding timestamped file. Because SNAPSHOTs can change, do not use SNAPSHOTs as production release versions that require long-term reproducibility.

Release versions such as `1.2.0` should be immutable once released. Do not deploy a different binary to the same release coordinates; increment the version instead. If a repository allows overwriting releases, old builds may resolve to a new binary without any change to the POM or source code.

## 6. Gradle Module Metadata: The `.module` File

Gradle Module Metadata (GMM) is Gradle's native metadata format, typically named `<artifact>-<version>.module`. When using Maven Publish or Ivy Publish, Gradle automatically publishes `.module` alongside the POM/Ivy descriptor to preserve concepts that cannot be fully expressed in a POM.

GMM can describe:

- Variants such as `apiElements`, `runtimeElements`, `sourcesElements`, `javadocElements`.
- Attributes such as Java target version, usage, category, and library elements.
- Dependency constraints and rich version constraints.
- Capabilities and feature variants.
- Artifact files attached to each variant.

Abbreviated example of `.module`:

~~~json
{
  "formatVersion": "1.1",
  "component": {
    "group": "com.example",
    "module": "metadata-demo",
    "version": "1.2.0"
  },
  "variants": [
    {
      "name": "apiElements",
      "attributes": {
        "org.gradle.category": "library",
        "org.gradle.usage": "java-api",
        "org.gradle.jvm.version": 17
      },
      "files": [
        {
          "name": "metadata-demo-1.2.0.jar",
          "url": "metadata-demo-1.2.0.jar"
        }
      ]
    }
  ]
}
~~~

The POM and `.module` are published side by side. Maven consumers read the POM; Gradle consumers can prefer GMM to select the appropriate variant. Do not delete the `.module` file or the `published-with-gradle-metadata` marker in the POM if the publication needs to support Gradle variant-aware resolution.

A POM cannot represent every Gradle concept, so Gradle has to map part of its model to Maven. During publishing, Gradle may warn if a dependency constraint, capability, or variant cannot be equivalently represented in the POM. Read these warnings and test both Gradle and Maven consumers if the library supports both.

## 7. Manifest Inside the JAR

A JAR is a ZIP archive that can contain a manifest at:

~~~text
META-INF/MANIFEST.MF
~~~

A manifest has main attributes that apply to the entire archive and named sections that apply to specific entries. A simple manifest:

~~~text
Manifest-Version: 1.0
Implementation-Title: Metadata Demo
Implementation-Version: 1.2.0
Specification-Title: Metadata Demo API
Specification-Version: 1.2
Main-Class: com.example.app.Main
Automatic-Module-Name: com.example.metadata
Multi-Release: true
~~~

Commonly used attributes:

| Attribute | Meaning |
|---|---|
| `Manifest-Version` | Manifest syntax version |
| `Main-Class` | Entry point when running `java -jar` |
| `Class-Path` | Relative URLs to required dependency JARs |
| `Implementation-Title` | Implementation name |
| `Implementation-Version` | Implementation version |
| `Implementation-Vendor` | Implementation vendor |
| `Specification-Title` | Specification/API name |
| `Specification-Version` | Specification version |
| `Automatic-Module-Name` | Stable module name for a JAR without a module descriptor |
| `Multi-Release` | Marks a multi-release JAR when set to `true` |

`Class-Path` in a manifest uses space-separated relative URLs; it does not use `File.pathSeparator`. This is a JAR manifest-specific rule, different from the classpath argument of the `java -cp` command.

`Main-Class` is needed for executable JARs, though not every library JAR needs it. `Implementation-Version` is useful for diagnostics, but consumers should not use the manifest as a substitute for dependency management or version pinning.

Manifest lines have a length limit per the JAR specification; the `jar` tool and build plugins handle line wrapping and continuation automatically. Avoid writing manifests manually as raw strings unless necessary.

## 8. `module-info.class` and JPMS Metadata

A named Java module has a module descriptor compiled from `module-info.java`:

~~~java
module com.example.metadata {
    requires java.logging;
    exports com.example.metadata.api;
}
~~~

When compiled, `module-info.class` is placed at the root of the JAR. The descriptor can specify:

- `requires`: dependent modules.
- `exports`: public packages that the module allows other modules to access.
- `opens`: packages opened for reflection.
- `uses`: services that the module consumes.
- `provides`: implementations provided for a service.
- `requires transitive` and `requires static`: control module dependency relationships.

Inspecting a JAR:

~~~text
jar --describe-module --file target/metadata-demo-1.2.0.jar
~~~

When a JAR has no `module-info.class`, it can become an automatic module when placed on the module path. The automatic module name is normally derived from the filename; the `Automatic-Module-Name` manifest attribute provides a stable name so it does not change if the file is renamed.

`Automatic-Module-Name` does not replace a module descriptor. Once a project has `module-info.java`, the descriptor is the primary source of module metadata.

A multi-release JAR can contain Java-version-specific classes under `META-INF/versions/<N>/`. If a JAR contains these, the manifest must include `Multi-Release: true` for the JVM to handle them properly. Do not add this attribute if the archive is not packaged with a multi-release structure.

## 9. Embedded Metadata Inside the JAR

Some build tools embed additional project metadata inside the archive. For example, the Maven JAR Plugin typically places:

~~~text
META-INF/maven/com.example/metadata-demo/pom.xml
META-INF/maven/com.example/metadata-demo/pom.properties
~~~

`pom.properties` typically contains:

~~~properties
groupId=com.example
artifactId=metadata-demo
version=1.2.0
~~~

Embedded metadata helps with diagnostics or lets a library read its own build information. It does not replace the sidecar POM that Maven uses to resolve dependencies from a repository.

Not every Gradle JAR embeds `pom.properties`; the format depends on build plugins and configuration. If an application needs to read its version at runtime, it can use the package implementation version or a project-generated build-info resource, but it must define fallback behavior when that metadata is absent.

## 10. Sources, Javadoc, and Classifier Artifacts

A publication often includes multiple files sharing the same GAV:

~~~text
metadata-demo-1.2.0.jar
metadata-demo-1.2.0-sources.jar
metadata-demo-1.2.0-javadoc.jar
~~~

- Binary JAR contains classes/resources for execution.
- Sources JAR contains source code for IDEs to display during debugging or navigation.
- Javadoc JAR contains HTML API documentation for IDE hover/help display.

Maven Source Plugin and Javadoc Plugin can attach these artifacts to a publication. The Gradle Java Plugin supports:

~~~groovy
java {
    withSourcesJar()
    withJavadocJar()
}
~~~

Gradle creates the `sourcesJar` and `javadocJar` tasks and attaches the corresponding variants to the Java component. When publishing `from components.java`, the secondary artifacts are published as part of the publication.

Do not arbitrarily rename the classifier of a file that consumers already depend on. When publishing `tests`, `sources`, `javadoc`, or native artifacts, declare the exact extension/classifier so dependency resolvers can find the file.

## 11. Checksums: Verifying Integrity

Repositories can publish checksum sidecars:

~~~text
metadata-demo-1.2.0.jar.sha256
metadata-demo-1.2.0.jar.sha512
metadata-demo-1.2.0.jar.sha1
~~~

Checksums help detect files that were altered or corrupted during storage or transfer. SHA-256 and SHA-512 are suitable for modern integrity verification; MD5/SHA-1 should only be treated as legacy metadata if a repository still provides them.

Computing the checksum of a local file:

Windows PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 .\target\metadata-demo-1.2.0.jar
~~~

Linux:

~~~sh
sha256sum target/metadata-demo-1.2.0.jar
~~~

macOS:

~~~sh
shasum -a 256 target/metadata-demo-1.2.0.jar
~~~

Compare the computed value against a checksum obtained from a trusted source. If both the JAR and its checksum are downloaded from a compromised repository, an attacker could replace both; a checksum alone does not authenticate the publisher's identity.

Gradle Maven Publish generates checksum metadata for published files. Repository managers can also generate checksum sidecars according to policy. Never fabricate a checksum file named like an official checksum whose contents do not match the artifact.

## 12. PGP Signatures and JAR Signatures

There are two common signature types:

**Detached PGP signature** typically has the `.asc` extension and sits next to the artifact:

~~~text
metadata-demo-1.2.0.jar
metadata-demo-1.2.0.jar.asc
~~~

Consumers use GPG and a trusted public key fingerprint to verify it. A detached signature signs the artifact file externally to the archive.

**JAR signing** uses `jarsigner`. The tool updates manifest digests and adds signature files/blocks to `META-INF`, for example:

~~~text
META-INF/MANIFEST.MF
META-INF/DEMO.SF
META-INF/DEMO.RSA
~~~

Creating a keystore, signing, and verifying are separate steps. Example commands:

~~~text
jarsigner -keystore release.p12 -storetype PKCS12 -signedjar metadata-demo-signed.jar metadata-demo.jar release-key
jarsigner -verify -verbose -certs metadata-demo-signed.jar
~~~

In a release pipeline, private keys must be kept in a secure signing system or CI secret store. Never commit keystores, private keys, tokens, or passwords to a repository or POM.

A JAR signature whose digests are valid does not automatically mean the certificate is trusted. Consumers must also verify the certificate chain, fingerprint, validity period, and timestamp. JAR signing is also different from a detached PGP signature: both the format and how consumers verify them differ.

Sign only after the archive is finalized. Modifying signed entries afterward will cause signature verification to fail; if content changes are needed, rebuild and re-sign.

## 13. SBOM and Provenance Accompanying Artifacts

An SBOM (Software Bill of Materials) describes the components and dependencies used to produce a software artifact. Common formats include CycloneDX and SPDX. An SBOM can be published as a separate artifact or attached to a release:

~~~text
metadata-demo-1.2.0.jar
metadata-demo-1.2.0.pom
metadata-demo-1.2.0.module
metadata-demo-1.2.0-sbom.cdx.json
metadata-demo-1.2.0.jar.asc
~~~

An SBOM supplements component, license, version, and dependency information; it does not replace the POM or Gradle Module Metadata used for dependency resolution.

Provenance/attestation can record the source revision, build workflow, builder identity, and build inputs. Store and verify provenance according to your organization's supply-chain process; do not treat a JSON file named `provenance` as a trustworthy attestation without signature/identity verification.

## 14. Publishing Metadata with Maven

To publish artifacts, Maven uses `distributionManagement` in the POM or an appropriate deploy configuration:

~~~xml
<distributionManagement>
  <repository>
    <id>releases</id>
    <url>https://repo.example.com/maven-releases/</url>
  </repository>
  <snapshotRepository>
    <id>snapshots</id>
    <url>https://repo.example.com/maven-snapshots/</url>
  </snapshotRepository>
</distributionManagement>
~~~

The `id` must match `<server><id>` in Maven's `settings.xml`, where credentials are configured. Store credentials in `settings.xml` or a CI secret store—never put passwords in the POM.

Example publish command:

~~~text
mvn -B -ntp clean deploy
~~~

- `install` places the artifact into the local Maven repository so other builds on the same machine can use it.
- `deploy` publishes the artifact and POM to the configured repository.
- `package` only builds the package in the local workspace; it does not publish to a remote repository.

A project POM should pin build plugin versions and declare source encoding and release target. For example, the Maven JAR Plugin can add manifest attributes:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-jar-plugin</artifactId>
  <version>3.4.2</version>
  <configuration>
    <archive>
      <manifestEntries>
        <Implementation-Title>Metadata Demo</Implementation-Title>
        <Implementation-Version>1.2.0</Implementation-Version>
        <Specification-Title>Metadata Demo API</Specification-Title>
      </manifestEntries>
    </archive>
  </configuration>
</plugin>
~~~

Attach Sources/Javadoc JARs using the Maven Source Plugin and Maven Javadoc Plugin when required by the publication. Set the correct classifiers and inspect the actual artifacts in the repository after deployment.

## 15. Publishing Metadata with Gradle

Use `maven-publish` to publish a Java component:

~~~groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'com.example'
version = '1.2.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
    withSourcesJar()
    withJavadocJar()
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
            pom {
                name = 'Metadata Demo'
                description = 'Example Java library.'
                url = 'https://example.com/metadata-demo'
                licenses {
                    license {
                        name = 'Apache License, Version 2.0'
                        url = 'https://www.apache.org/licenses/LICENSE-2.0'
                    }
                }
                scm {
                    connection = 'scm:git:https://example.com/metadata-demo.git'
                    url = 'https://example.com/metadata-demo'
                }
            }
        }
    }
    repositories {
        maven {
            name = 'releases'
            url = uri('https://repo.example.com/maven-releases')
            credentials {
                username = providers.environmentVariable('REPO_USER').get()
                password = providers.environmentVariable('REPO_TOKEN').get()
            }
        }
    }
}
~~~

Run:

~~~text
./gradlew publish
~~~

Gradle creates publication tasks based on the publication and repository names, such as `publishMavenJavaPublicationToReleasesRepository`. `publish` runs all configured publish tasks.

To add manifest attributes:

~~~groovy
tasks.named('jar', Jar) {
    manifest {
        attributes(
            'Implementation-Title': project.name,
            'Implementation-Version': project.version
        )
    }
}
~~~

Gradle automatically generates `.module` and the POM when using Maven Publish. If you configure custom variants or dependency constraints, check mapping warnings to ensure Maven consumers still receive a valid POM. Never put repository credentials in a committed `gradle.properties` or a potentially public build script.

## 16. Versioning and Metadata Consistency

The version is part of an artifact's identity. Keep versions synchronized across:

- GAV in the POM/Gradle publication.
- Artifact filenames.
- `Implementation-Version` in the manifest, if used.
- Version in embedded `pom.properties`.
- Version in the SBOM/provenance.
- Release tags and changelogs.

Do not hardcode multiple independent versions across the POM, Gradle script, and manifest when they can all be derived from the same project version. Version mismatches make it difficult for users to determine which binary is actually running.

Use semantic versioning when appropriate for the library's contract: major for incompatible changes, minor for backward-compatible features, and patch for backward-compatible bug fixes. Maven does not enforce semantic versioning; it is a project policy.

Release artifacts should be immutable. Snapshots can change across deployments; release versions should not be overwritten. Do not use `LATEST` or `RELEASE` dynamic versions in production dependencies when reproducible builds are required; pin specific versions or use controlled dependency constraints/platforms.

## 17. Reproducible Artifacts and Build Metadata

The same source, dependencies, and build configuration should produce artifacts with stable contents. Metadata can cause a JAR to differ between two builds if timestamps, build paths, machine names, or generated build IDs are embedded in the archive.

With Maven, you can set:

~~~xml
<properties>
  <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

Set the timestamp according to your project's reproducible build process, typically derived from a standardized source revision or release timestamp.

With Gradle, archive tasks are designed to produce stable output when inputs do not change; avoid injecting the current time or local machine paths into manifests or resources.

Principles:

- Pin JDK/toolchain and plugin versions.
- Pin dependency versions and avoid uncontrolled dynamic versions.
- Set encoding explicitly.
- Standardize archive timestamps and file ordering.
- Do not embed usernames, build hostnames, local paths, or secrets.
- Do not generate random build identifiers if downstream caching or reproducibility requires stability.
- Compute and store checksums after the final artifact has been built and signed.

Metadata for traceability should record controlled source revision/build provenance without causing meaningless differences in the artifact across builds from identical inputs.

## 18. Inspecting Artifacts and Metadata After Publishing

Do not rely solely on a `BUILD SUCCESS` message. Inspect the repository output:

~~~text
# List JAR entries
jar --list --file target/metadata-demo-1.2.0.jar

# Inspect module descriptor
jar --describe-module --file target/metadata-demo-1.2.0.jar

# Extract manifest for inspection
jar --extract --file target/metadata-demo-1.2.0.jar META-INF/MANIFEST.MF
~~~

In a Maven project:

~~~text
mvn help:effective-pom
mvn dependency:tree
mvn -B -ntp deploy
~~~

In a Gradle project:

~~~text
./gradlew outgoingVariants
./gradlew dependencies
./gradlew publishToMavenLocal
~~~

Verify that the repository version directory contains the expected files:

- Main JAR and POM.
- `.module` if published with Gradle.
- Sources/Javadoc JARs if required.
- Snapshot `maven-metadata.xml` when publishing a SNAPSHOT.
- Checksums/signatures per repository policy.

To verify that a published artifact can be resolved by consumers, create a clean consumer project and declare the dependency using the exact GAV. Do not test only the producer build; a broken POM or missing classifier can still yield a green producer build while failing consumer resolution.

## 19. Java 17+ Example: Reading Metadata from a JAR

Create `ArtifactMetadataInspector.java`:

~~~java
import java.io.IOException;
import java.nio.file.Path;
import java.util.jar.Attributes;
import java.util.jar.JarFile;
import java.util.jar.Manifest;

public final class ArtifactMetadataInspector {
    private ArtifactMetadataInspector() {
    }

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: ArtifactMetadataInspector <jar-file>");
        }

        Path jarPath = Path.of(args[0]);

        try (JarFile jar = new JarFile(jarPath.toFile())) {
            Manifest manifest = jar.getManifest();
            Attributes attributes = manifest == null
                    ? new Attributes()
                    : manifest.getMainAttributes();

            System.out.println("JAR_NAME=" + jarPath.getFileName());
            System.out.println("MANIFEST_PRESENT=" + (manifest != null));
            System.out.println("IMPLEMENTATION_TITLE="
                    + attributes.getValue("Implementation-Title"));
            System.out.println("IMPLEMENTATION_VERSION="
                    + attributes.getValue("Implementation-Version"));
            System.out.println("AUTOMATIC_MODULE_NAME="
                    + attributes.getValue("Automatic-Module-Name"));
            System.out.println("MODULE_INFO_PRESENT="
                    + (jar.getEntry("module-info.class") != null));
        }
    }
}
~~~

Compile:

~~~text
javac --release 17 -encoding UTF-8 -Xlint:all -Werror -d out ArtifactMetadataInspector.java
~~~

Run with the built/published artifact:

~~~text
java -cp out ArtifactMetadataInspector target/metadata-demo-1.2.0.jar
~~~

If the JAR has manifest attributes like the Maven/Gradle examples above, the output will look like:

~~~text
JAR_NAME=metadata-demo-1.2.0.jar
MANIFEST_PRESENT=true
IMPLEMENTATION_TITLE=Metadata Demo
IMPLEMENTATION_VERSION=1.2.0
AUTOMATIC_MODULE_NAME=null
MODULE_INFO_PRESENT=true
~~~

`AUTOMATIC_MODULE_NAME=null` is normal when the JAR contains `module-info.class` and the manifest does not declare `Automatic-Module-Name`. The program reads the manifest and checks for the module descriptor entry; to view specific exports and requires, use `jar --describe-module`.

## 20. Verifying Signatures and Checksums in the Release Pipeline

After publishing the final artifact, compute SHA-256 and store the checksum according to repository policy. If signing the JAR with `jarsigner`, verify the signature before uploading:

~~~text
jarsigner -verify -verbose -certs target/metadata-demo-1.2.0.jar
~~~

If strict verification is needed:

~~~text
jarsigner -verify -strict -verbose -certs target/metadata-demo-1.2.0.jar
~~~

`-strict` can cause the command to return an error when the certificate chain or trust policy does not meet requirements. This is a different check from merely confirming that entry digests still match.

For PGP detached signatures:

~~~text
gpg --verify metadata-demo-1.2.0.jar.asc metadata-demo-1.2.0.jar
~~~

Verify the public key fingerprint through an independent trusted channel. Do not trust a public key solely because it was downloaded alongside the artifact from the same repository being verified.

A well-structured release pipeline typically runs in this order:

1. Build from a reviewed/tagged source revision.
2. Run compile, tests, static checks, and packaging.
3. Generate POM/Gradle metadata, Sources/Javadoc JARs, and SBOM.
4. Inspect the manifest, module descriptor, and repository coordinates.
5. Compute checksums and sign artifacts/metadata according to policy.
6. Publish to a staging/release repository.
7. Resolve the artifact using a consumer test project.
8. Promote the release after verification succeeds.

## 21. Troubleshooting Artifact Metadata

### Consumer resolves the JAR but is missing transitive dependencies

**Cause:** The POM is missing dependencies, has the wrong scope, or the publication only contains the binary without component metadata.

**Resolution:** Inspect the published POM, `dependency:tree`, Gradle `.module`, and consumer configuration. Check dependency scopes and API exposure.

### Maven reports `Could not find artifact`

**Cause:** Wrong GAV, version not yet published, repository URL/profile not enabled, or snapshot/release repository misconfigured.

**Resolution:** Check the repository path by `groupId`/`artifactId`/`version`, POM, and metadata. Confirm `distributionManagement`, settings profile, and server id.

### SNAPSHOT consumer still resolves an old binary

**Cause:** Snapshot metadata cache, repository proxy cache, or timestamp mapping not updated.

**Resolution:** Check version-level `maven-metadata.xml`, `timestamp`/`buildNumber`, repository cache policy, and `-U` when you need to force Maven to check for updates. Do not manually delete metadata on shared repositories.

### Gradle consumer does not see the expected variant

**Cause:** `.module` was not published/read, variant attributes do not match consumer attributes, or mapping the publication to a POM lost features.

**Resolution:** Inspect `outgoingVariants`, `.module`, dependency attributes, and repository metadata sources. Check warnings emitted during publishing.

### Sources/Javadoc JAR does not appear

**Cause:** Plugin/task did not attach the artifact, wrong classifier, or publication was not created from a component with those variants.

**Resolution:** Check `sourcesJar`, `javadocJar`, Maven source/javadoc plugin executions, and actual files in the repository.

### `Implementation-Version` is missing

**Cause:** Manifest is not configured, or the artifact was created by a different task than the one being inspected.

**Resolution:** Configure Maven JAR Plugin or Gradle `Jar.manifest`, rebuild, and inspect `META-INF/MANIFEST.MF`.

### `jar --describe-module` cannot find a module descriptor

**Cause:** The JAR does not contain `module-info.class`; it may be a classpath JAR or an automatic module.

**Resolution:** Check `module-info.java`, compiler release, source sets, and JAR contents. If a stable automatic module name is needed, configure `Automatic-Module-Name`.

### Checksum mismatch

**Cause:** Corrupted file, stale proxy cache, artifact modified after checksum generation, or comparing the wrong classifier/version.

**Resolution:** Re-download from a trusted repository, verify the exact file/version/classifier, and check publish logs. Never edit a checksum to match a binary of unknown origin.

### JAR signature invalid

**Cause:** Archive was modified after signing, corrupted entry, missing signature block, or invalid certificate/trust chain.

**Resolution:** Rebuild and then sign as the final step; check certificate chain, timestamp, and public key fingerprint. Distinguish between a digest mismatch and an untrusted certificate.

### Release was overwritten

**Cause:** Repository allows redeploying the same release version, or CI does not check whether the version already exists.

**Resolution:** Enable release immutability/redeploy policy, increment the version, and use a staging repository. Do not rely on `maven-metadata.xml` to detect every case of binary overwriting.

## 22. Pre-Release Artifact Checklist

- [ ] `groupId`, `artifactId`, `version`, and packaging are correct.
- [ ] POM includes required name, description, URL, license, SCM, and developer metadata.
- [ ] Dependencies and scopes accurately reflect the API/runtime contract.
- [ ] Gradle `.module` and POM are consistent with the publication.
- [ ] Snapshot/release repository is selected appropriately for the version.
- [ ] `maven-metadata.xml` is updated properly by the repository.
- [ ] Main JAR includes required manifest attributes.
- [ ] `module-info.class` or `Automatic-Module-Name` matches module policy.
- [ ] Sources/Javadoc JARs are attached when required by the release.
- [ ] SBOM/provenance is generated if required by supply-chain policy.
- [ ] Checksums are computed from the final files.
- [ ] Signatures are verified with trusted keys/certificates.
- [ ] Release artifact version is not redeployed/overwritten.
- [ ] A consumer project can resolve and use the artifact from the target repository.
- [ ] Build reproducibility and tool/plugin versions are controlled.
- [ ] Credentials are not present in the POM, JAR, manifest, or source repository.

## 23. References

- Apache Maven — Maven POM Reference: https://maven.apache.org/pom.html
- Apache Maven — Repository Metadata: https://maven.apache.org/repositories/metadata.html
- Apache Maven — Repository Layout and SNAPSHOT: https://maven.apache.org/repository/layout.html
- Apache Maven — Maven Deploy Plugin: https://maven.apache.org/plugins/maven-deploy-plugin/
- Gradle — Gradle Module Metadata: https://docs.gradle.org/current/userguide/publishing_gradle_module_metadata.html
- Gradle — Publishing a project as a module: https://docs.gradle.org/current/userguide/publishing_setup.html
- Gradle — Maven Publish Plugin: https://docs.gradle.org/current/userguide/publishing_maven.html
- Java SE 24 — JAR File Specification: https://docs.oracle.com/en/java/javase/24/docs/specs/jar/jar.html
- Oracle JDK 24 — `jar` command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jar.html
- Oracle JDK 24 — `jarsigner` command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jarsigner.html
- Java SE 24 — `java.util.jar.Manifest`: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/jar/Manifest.html
- Java SE 24 — `java.util.jar.JarFile`: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/jar/JarFile.html

Artifact metadata bridges the gap between binaries and the build/repository ecosystem. POMs and `.module` files help consumers understand components, dependencies, and variants; `maven-metadata.xml` supports version and SNAPSHOT resolution; manifests and `module-info.class` describe the JAR at runtime; checksums and signatures support integrity and authenticity. A reliable release requires verifying these metadata layers alongside the final binary and testing resolution from an independent consumer project.
