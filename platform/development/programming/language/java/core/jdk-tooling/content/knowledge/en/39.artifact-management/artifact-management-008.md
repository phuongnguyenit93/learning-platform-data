# Java Artifact Version Management

An **artifact version** is the version assigned to a built and released software component, such as a JAR, WAR, library, desktop application, or installer. Versions help users identify what has changed, help build tools locate the right dependency, help distribution systems select the version to install, and help release teams trace an artifact back to its source commit.

A Java project often has multiple types of versions at the same time: the public API version, Maven/Gradle version, version recorded in the JAR manifest, application version, native package version, Java runtime version, and CI build identifier. These values are related to one another but serve different purposes. A single canonical version source and clear mapping rules between them should be defined.

This article covers Semantic Versioning, Maven coordinates and SNAPSHOTs, Gradle project/archive versions, JAR manifest metadata, jpackage package versions, Git tags, dependency resolution, the CI release process, and how to inspect the version of a built artifact.

## 1. What does an artifact version mean?

A version answers several questions:

- Which release is this?
- Does the public API contain backward-incompatible changes?
- Which dependency can use this artifact?
- Which source revision was this artifact built from?
- Can the installer upgrade a previously installed version?
- Are operators running the exact released version?

A filename like version-demo.jar is not enough to uniquely identify the contents. You also need to inspect groupId, artifactId, version, classifier, repository, checksum, and provenance.

Example of a library:

~~~text
groupId:    com.acme.platform
artifactId: customer-client
version:    2.4.1
packaging:  jar
~~~

The full Maven coordinate is:

~~~text
com.acme.platform:customer-client:2.4.1
~~~

A desktop application may have version 2.4.1 while being built with JDK 24, Maven 3.9.12, and installer revision 3. These are distinct pieces of information:

| Value | Example | Meaning |
|---|---|---|
| Application version | 2.4.1 | Functional version of the application |
| Library/API version | 2.4.1 | Public API version of the library |
| Maven/Gradle project version | 2.4.1 | Version in the build/publish system |
| JAR Implementation-Version | 2.4.1 | Version metadata in the manifest |
| Installer/package revision | 3 | Packaging iteration or revision per package format |
| Java runtime version | 24.0.2 | JVM version used or bundled |
| Build identifier | 184 | A specific CI run |
| Git revision | abc1234 | Source commit that produced the artifact |

Do not use the Java runtime version in place of the application version. An application at version 2.4.1 can run on Java 17, 21, or 24 depending on compatibility requirements.

## 2. Semantic Versioning (SemVer)

Semantic Versioning 2.0.0 is a set of rules for assigning versions based on changes to the public API. Stable version format:

~~~text
MAJOR.MINOR.PATCH
~~~

- **MAJOR:** incremented when making incompatible changes to the public API.
- **MINOR:** incremented when adding functionality in a backward-compatible manner.
- **PATCH:** incremented when making backward-compatible bug fixes.

Examples:

| Change | Old version | New version |
|---|---|---|
| Bug fix that does not change the API | 2.4.1 | 2.4.2 |
| Adding a backward-compatible public method | 2.4.1 | 2.5.0 |
| Removing or changing a public API signature | 2.4.1 | 3.0.0 |

When MINOR is incremented, PATCH is reset to 0. When MAJOR is incremented, MINOR and PATCH are reset to 0.

### Define the public API first

SemVer is only meaningful when the project clearly defines its public API. The API may include:

- Public classes, interfaces, constructors, and methods.
- Public method signatures, checked exceptions, and return types.
- Public configuration keys or file formats.
- REST/IPC contracts if the artifact provides a service.
- Documented behaviors that users rely on.

A change can break compatibility even if the method signature does not change. For example, a method that previously accepted null now throws an exception, or changing default behavior causes downstream applications to stop working.

Do not bump PATCH solely because the code diff is small. Evaluate the impact on the contract that users depend on.

### 0.x versions

According to SemVer, a MAJOR version of 0 is for initial development. The public API is not yet considered stable and may change at any time.

Examples:

~~~text
0.3.0
0.4.0
0.4.1
1.0.0
~~~

When releasing 1.0.0, the project declares that the public API has reached stability according to its compatibility policy.

### Pre-release versions

A pre-release label can be appended after PATCH with a hyphen:

~~~text
2.5.0-alpha.1
2.5.0-beta.2
2.5.0-rc.1
2.5.0
~~~

For the same MAJOR.MINOR.PATCH, a pre-release version has lower precedence than a normal release. For example:

~~~text
2.5.0-alpha.1 < 2.5.0-beta.1
2.5.0-beta.1 < 2.5.0-rc.1
2.5.0-rc.1 < 2.5.0
~~~

Pre-release identifiers consist only of ASCII alphanumerics and hyphens; numeric identifiers must not include leading zeroes, except for the value 0 itself.

Use alpha for early experimentation, beta for broader testing, and rc when the contents are expected to be ready for release if no blocking bugs remain.

### Build metadata

SemVer allows metadata after a plus sign:

~~~text
2.5.0+build.184
2.5.0-rc.1+sha.abc1234
~~~

Build metadata helps trace builds but **does not affect version precedence**. Two versions that differ only in the metadata after the plus sign have the same precedence under SemVer.

If a repository or package manager does not handle full SemVer 2, keep the build number and Git SHA in separate manifest/provenance metadata instead of putting a plus sign in the version coordinate.

### Released versions must be immutable

Once a release version is published, the artifact contents for that version must not be replaced with a different binary. If a fix is needed, release a new version.

For example, if 2.4.1 has been released and a bug is discovered, create 2.4.2. Do not re-upload a different JAR under the same 2.4.1 coordinate. This protects caches, checksums, signatures, and the reproducibility of the dependency graph.

Refer to the full specification at [Semantic Versioning 2.0.0](https://semver.org/).

## 3. Versions in Maven

Maven identifies an artifact by three main components:

~~~text
groupId:artifactId:version
~~~

Example:

~~~xml
<groupId>com.acme.platform</groupId>
<artifactId>customer-client</artifactId>
<version>2.4.1</version>
<packaging>jar</packaging>
~~~

- groupId identifies the organization or project namespace.
- artifactId identifies the component.
- version identifies a specific version of the component.

These values determine the artifact path in a Maven repository and are used when declaring dependencies.

### Declaring a version in pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.acme.platform</groupId>
    <artifactId>customer-client</artifactId>
    <version>2.4.1</version>
    <packaging>jar</packaging>
</project>
~~~

Build:

~~~bash
mvn clean package
~~~

Default JAR filename:

~~~text
target/customer-client-2.4.1.jar
~~~

The Maven POM Reference describes GAV as the coordinates that identify an artifact in a repository. See [Maven POM Reference — Maven Coordinates](https://maven.apache.org/pom.html).

### What is SNAPSHOT?

A version ending in -SNAPSHOT indicates a development version that is not yet an immutable release:

~~~xml
<version>2.5.0-SNAPSHOT</version>
~~~

When deploying a snapshot to a repository that supports Maven snapshot metadata, the repository can store the artifact with a unique timestamp and build number. A consumer declaring version 2.5.0-SNAPSHOT will use that metadata to resolve the current snapshot according to its update policy.

For example, an internal stored artifact might have a name like:

~~~text
customer-client-2.5.0-20261110.103015-4.jar
~~~

The specific timestamped filename is generated by the repository and should not be constructed manually.

Use SNAPSHOTs during integration development. For an official release, switch to a release version:

~~~text
2.5.0-SNAPSHOT  ->  2.5.0
~~~

Do not use SNAPSHOTs for production dependencies that require reproducibility, because the same coordinate can resolve to different contents over time.

### Dependency declaration

An application using the library:

~~~xml
<dependency>
    <groupId>com.acme.platform</groupId>
    <artifactId>customer-client</artifactId>
    <version>2.4.1</version>
</dependency>
~~~

Declare versions explicitly or manage them centrally using dependencyManagement/BOM. Avoid wide version ranges without a control policy, because dependency resolution may pick a newer version than intended.

Inspect the dependency graph:

~~~bash
mvn dependency:tree
~~~

If multiple versions of the same artifact appear via transitive dependencies, Maven mediation selects a version according to dependency graph and dependency management rules. Inspect the dependency tree before overriding.

### Maven version ordering is not fully identical to SemVer 2

Maven has its own version comparison algorithm. Although common versions usually sort similarly to SemVer, the Maven POM Reference explicitly notes that its version ordering algorithm is not fully compatible with SemVer 2.0.0; the plus sign and build metadata are not handled according to SemVer 2 precedence rules, and qualifier comparisons are case-insensitive.

Therefore:

- Do not assume every valid SemVer version string orders the same way in Maven.
- Avoid relying on build metadata with a plus sign in Maven coordinates.
- Do not compare versions using String.compareTo().
- Use Maven version-aware APIs or a dependency resolver when comparing Maven versions.

Refer to [Maven Version Order Specification](https://maven.apache.org/pom.html#version-order-specification).

## 4. Versions in Gradle

Gradle uses the project version property to identify the project when publishing and typically uses it as the version part of archive filenames.

In build.gradle:

~~~groovy
plugins {
    id 'java'
}

group = 'com.acme.platform'
version = '2.4.1'
~~~

After running:

~~~bash
./gradlew clean jar
~~~

The default JAR filename is typically:

~~~text
build/libs/<project-name>-2.4.1.jar
~~~

### Customizing the archive name

Gradle archive tasks have the following properties:

- archiveBaseName: the base name part.
- archiveVersion: the version part.
- archiveClassifier: suffix distinguishing the artifact type.
- archiveExtension: the file extension.

Example:

~~~groovy
tasks.named('jar', Jar) {
    archiveBaseName = 'customer-client'
    archiveVersion = project.version.toString()
    archiveClassifier = 'desktop'
}
~~~

Result:

~~~text
build/libs/customer-client-2.4.1-desktop.jar
~~~

A classifier can distinguish sources, javadoc, platform-specific bundles, or content variants. A classifier does not replace the version and should not be used to represent an API change.

Gradle documents that archiveVersion defaults to project.version; see [Gradle Working With Files — Archive Tasks](https://docs.gradle.org/current/userguide/working_with_files.html).

### Including the version in a publication

When using the Maven Publish Plugin, the publication version should be consistent with the project version:

~~~groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'com.acme.platform'
version = '2.4.1'

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
            groupId = project.group.toString()
            artifactId = 'customer-client'
            version = project.version.toString()
        }
    }
}
~~~

Gradle can publish POM and Gradle Module Metadata. Consumers use this metadata to resolve dependencies, variants, and artifacts.

### Avoid dynamic dependency versions in release builds

Declarations such as:

~~~groovy
implementation 'com.acme:library:2.+'
~~~

can resolve to different versions at different times. Release builds should use fixed versions or controlled dependency constraints/locking.

Inspect dependencies:

~~~bash
./gradlew dependencies
~~~

View dependencies for a specific configuration:

~~~bash
./gradlew dependencyInsight --dependency customer-client --configuration runtimeClasspath
~~~

Use dependency locking if you need to preserve the exact resolved versions across builds and CI runs.

## 5. Recording the version in the JAR manifest

A JAR filename can be changed when copied or renamed. Therefore, version metadata should be recorded in the JAR's manifest.

Commonly used attributes:

| Manifest attribute | Meaning |
|---|---|
| Manifest-Version | Manifest format version, usually 1.0 |
| Implementation-Title | Implementation title |
| Implementation-Version | Version of the implementation/artifact |
| Implementation-Vendor | Implementation vendor |
| Specification-Title | Specification title |
| Specification-Version | Version of the specification/API contract |
| Specification-Vendor | Specification vendor |
| Build-Revision | Custom attribute that can hold the Git SHA |

**Manifest-Version is not the application version.** For example, a JAR having Manifest-Version 1.0 while having Implementation-Version 2.4.1 is completely normal.

The JAR File Specification defines Implementation-Version and Specification-Version as metadata for package versioning. See [JAR File Specification — Main Attributes](https://docs.oracle.com/en/java/javase/24/docs/specs/jar/jar.html).

### Configuring the Maven JAR Plugin

In pom.xml:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-jar-plugin</artifactId>
            <version>3.4.2</version>
            <configuration>
                <archive>
                    <manifest>
                        <addDefaultImplementationEntries>true</addDefaultImplementationEntries>
                        <addDefaultSpecificationEntries>true</addDefaultSpecificationEntries>
                    </manifest>
                    <manifestEntries>
                        <Build-Revision>abc1234</Build-Revision>
                    </manifestEntries>
                </archive>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

With a POM having version 2.4.1, the Maven JAR Plugin writes Implementation-Version and the corresponding metadata into the manifest. The build revision can be passed in from CI instead of being hard-coded.

### Configuring the Gradle JAR manifest

In build.gradle:

~~~groovy
version = '2.4.1'

tasks.named('jar', Jar) {
    manifest {
        attributes(
            'Implementation-Title': project.name,
            'Implementation-Version': project.version.toString(),
            'Implementation-Vendor': 'Acme Corporation',
            'Specification-Version': '2.4',
            'Build-Revision': 'abc1234'
        )
    }
}
~~~

Use a single canonical version source to set project.version, archiveVersion, and Implementation-Version. Do not maintain independent values that can easily drift out of sync.

### Reading the version at Java runtime

The Java Package API can read package metadata recorded in the manifest.

File **VersionInfo.java**:

~~~java
package com.acme.version;

public final class VersionInfo {
    public static void main(String[] args) {
        Package p = VersionInfo.class.getPackage();

        System.out.println(
            "Implementation-Title=" + p.getImplementationTitle()
        );
        System.out.println(
            "Implementation-Version=" + p.getImplementationVersion()
        );
    }
}
~~~

If the JAR manifest contains:

~~~text
Implementation-Title: version-demo
Implementation-Version: 2.4.1
~~~

Run:

~~~bash
java -cp target/version-demo-2.4.1.jar com.acme.version.VersionInfo
~~~

Stdout:

~~~text
Implementation-Title=version-demo
Implementation-Version=2.4.1
~~~

If running the class directly from a classes directory or an environment without manifest metadata, getImplementationVersion() may return null. The application should handle that case, such as displaying unknown or using an explicitly generated build-time resource.

### Main-Class is a different attribute

Implementation-Version only provides metadata. It does not declare an entry point.

If you want to run with:

~~~bash
java -jar app.jar
~~~

the JAR needs Main-Class in its manifest. It can be declared via the Maven JAR Plugin, Gradle manifest, or the jar --main-class option. Do not confuse Main-Class with Implementation-Version.

## 6. Distinguishing application version, artifact version, and Java version

A project may release multiple components:

~~~text
customer-client       2.4.1
customer-server       5.7.0
desktop-application   3.2.4
installer-package     3.2.4
Java runtime          24.0.2
build number          184
~~~

Not all modules necessarily share the same version. A library can be released independently of the application that uses it.

You should distinguish:

- API/library version: changes according to the library's public contract.
- Application version: changes according to product features and behavior.
- Installer version: follows the product version that the installer installs.
- Package revision: follows native package manager conventions if applicable.
- Java runtime version: the JDK/JRE used to compile or bundle.
- Build identifier: identifies a specific pipeline run.

### Java target version is not the artifact version

Maven compiler example:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

This value specifies the Java API and class-file target. It does not mean the artifact version is 17.

An artifact can have:

~~~text
Implementation-Version: 2.4.1
Build-Jdk-Spec: 24
Java release target: 17
~~~

This means artifact version 2.4.1 was built on JDK 24 and compiled for Java 17 compatibility according to the release configuration.

### Multi-release JAR

A multi-release JAR can contain different classes for different Java releases in directories:

~~~text
META-INF/versions/9/
META-INF/versions/17/
META-INF/versions/21/
~~~

The manifest declares:

~~~text
Multi-Release: true
~~~

This is how one artifact supports multiple Java runtime versions in the same JAR. The numbers 9, 17, and 21 are Java platform releases for the classes/resources, not the release version of the artifact.

## 7. Version in installers with jpackage

jpackage has the option:

~~~text
--app-version
~~~

This option specifies the version of the application and/or native package. Example:

~~~bash
jpackage --type app-image --input input --name AcmeDesktop --main-jar acme-desktop.jar --main-class com.acme.desktop.Main --app-version 2.4.1 --dest dist
~~~

The version is included in metadata and platform-specific package naming. The JDK documentation describes --app-version as the version of the application/package; see [Oracle JDK 24 jpackage Guide](https://docs.oracle.com/en/java/javase/24/jpackage/index.html).

### Keep the full version in the manifest

Some native package managers have their own version limits or rules. Therefore:

1. Keep the SemVer product version in release metadata.
2. Record the full version in the JAR manifest.
3. Pass a version compatible with the package format to --app-version.
4. If needed, store pre-release labels or build metadata in release notes/provenance.
5. Verify the actual metadata of the package after creation.

Do not assume every native package format handles every SemVer string the same way.

### Keep package identity stable

The version changes across releases, but the product identity usually needs to stay stable.

- Windows: keep --win-upgrade-uuid consistent for the same product and upgrade line.
- macOS: keep --mac-package-identifier stable.
- Linux: keep the package name stable; increment the package version and revision according to distro rules.

Do not generate a new upgrade UUID for each version if you want the installer to recognize and upgrade older installations.

### Package revision differs from application version

On Linux, jpackage provides --linux-app-release to set the release/revision in the RPM spec or Debian control file. This can represent the packaging revision while the application version stays the same.

For example, a package rebuild due to a metadata fix can keep application version 2.4.1 while incrementing the package revision according to your organization's release policy.

## 8. Managing versions with Git tags and CI

Git tags link a source revision to a released version.

Example:

~~~bash
git tag -a v2.4.1 -m "Release 2.4.1"
git push origin v2.4.1
~~~

CI can inspect the tag to determine the release version:

~~~bash
git describe --tags --always
~~~

Recommended release workflow:

1. Merge reviewed code into the release/main branch.
2. Run tests, API compatibility checks, and dependency verification.
3. Determine the version based on public API changes.
4. Create an annotated Git tag.
5. Build the artifact from the exact tagged commit.
6. Record the version and Git SHA in the manifest/provenance.
7. Generate checksums and signatures.
8. Publish the artifact to the release repository.
9. Save release notes and dependency metadata.
10. Do not modify released artifacts; any change creates a new version.

### Avoid deriving versions from build time

Do not use the current timestamp as the primary release version. Two builds from the same source could produce different artifact filenames even though the contents have not changed.

You can record the build timestamp in provenance or CI logs. If a build number is needed, use a separate field.

### Version and source revision must match

Before releasing, verify:

- The Git tag has the correct version.
- The working tree has no uncommitted changes.
- The POM/Gradle version matches the tag.
- The JAR manifest matches the version.
- The installer metadata matches the product version.
- The build revision matches the commit.
- Checksums are computed from the final artifact.

If any value does not match, stop the release and fix the pipeline or version source before publishing.

## 9. Dependency versions and compatibility

Dependency versions affect the API, runtime behavior, and reproducibility.

### Pin dependency versions

Maven example:

~~~xml
<dependency>
    <groupId>com.acme.platform</groupId>
    <artifactId>customer-client</artifactId>
    <version>2.4.1</version>
</dependency>
~~~

Gradle example:

~~~groovy
dependencies {
    implementation 'com.acme.platform:customer-client:2.4.1'
}
~~~

Avoid dynamic versions in release builds unless you have a dependency locking mechanism.

### Check transitive dependencies

One dependency may pull in a different version of the same library. Use:

~~~bash
mvn dependency:tree
~~~

or:

~~~bash
./gradlew dependencyInsight --dependency customer-client --configuration runtimeClasspath
~~~

If the resolved version differs from what you expected, check dependency paths, constraints, dependencyManagement, and exclusions.

### BOM and dependency alignment

A BOM helps manage a compatible set of versions:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.acme.platform</groupId>
            <artifactId>platform-bom</artifactId>
            <version>2.4.1</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Modules using the BOM can declare dependencies without repeating the version in every place.

In Gradle, you can use a platform or version catalog to manage versions centrally. For release builds, dependency locking helps pin the resolved versions.

### Do not assume MINOR is always safe in every ecosystem

SemVer defines compatibility based on the public API published by the vendor. However, a library might not strictly follow SemVer or might have its own behavioral compatibility nuances. Check release notes, API diffs, and run integration tests before upgrading a dependency.

## 10. Comparing versions properly

Do not compare versions as plain strings:

~~~java
"2.10.0".compareTo("2.9.0")
~~~

Lexicographical comparison can give the wrong result because the character '1' comes before '9', even though the numeric component 10 is greater than 9.

Use a parser/comparator for the chosen scheme:

- SemVer 2: use a SemVer 2-compliant library.
- Maven version: use Maven ComparableVersion or the corresponding resolver.
- OSGi version: use OSGi rules.
- Native package version: use the package manager's comparator.

Do not use a single comparator for all version types. For example, Maven version ordering is not fully compatible with SemVer 2.

### SemVer ordering examples

~~~text
1.9.0 < 1.10.0
2.0.0-alpha < 2.0.0-beta
2.0.0-beta < 2.0.0-rc.1
2.0.0-rc.1 < 2.0.0
~~~

Build metadata does not affect precedence:

~~~text
2.0.0+build.10
2.0.0+build.11
~~~

These two versions have the same precedence according to SemVer. If you need to distinguish specific builds, use a Git SHA or build identifier alongside the version.

## 11. Practice: inspecting version in a Maven JAR

Create the project:

~~~text
version-demo/
├── pom.xml
└── src/main/java/com/acme/version/VersionInfo.java
~~~

File **VersionInfo.java**:

~~~java
package com.acme.version;

public final class VersionInfo {
    public static void main(String[] args) {
        Package p = VersionInfo.class.getPackage();

        System.out.println(
            "Implementation-Title=" + p.getImplementationTitle()
        );
        System.out.println(
            "Implementation-Version=" + p.getImplementationVersion()
        );
    }
}
~~~

File **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.acme</groupId>
    <artifactId>version-demo</artifactId>
    <version>2.4.1</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
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
                            <addDefaultImplementationEntries>true</addDefaultImplementationEntries>
                            <addDefaultSpecificationEntries>true</addDefaultSpecificationEntries>
                        </manifest>
                        <manifestEntries>
                            <Build-Revision>example-git-sha</Build-Revision>
                        </manifestEntries>
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

Generated artifact:

~~~text
target/version-demo-2.4.1.jar
~~~

Inspect the manifest:

~~~bash
jar --extract --file target/version-demo-2.4.1.jar META-INF/MANIFEST.MF
~~~

The manifest contains fields similar to:

~~~text
Manifest-Version: 1.0
Implementation-Title: version-demo
Implementation-Version: 2.4.1
Specification-Version: 2.4
Build-Revision: example-git-sha
~~~

Run the class:

~~~bash
java -cp target/version-demo-2.4.1.jar com.acme.version.VersionInfo
~~~

Stdout:

~~~text
Implementation-Title=version-demo
Implementation-Version=2.4.1
~~~

If run directly from a classes directory, package metadata may be null because there is no manifest yet. Verify using the actual JAR artifact.

## 12. Practice: inspecting version in a Gradle JAR

Similar source structure:

~~~text
version-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/acme/version/VersionInfo.java
~~~

File **settings.gradle**:

~~~groovy
rootProject.name = 'version-demo'
~~~

File **build.gradle**:

~~~groovy
plugins {
    id 'java'
}

group = 'com.acme'
version = '2.4.1'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.named('jar', Jar) {
    archiveBaseName = 'version-demo'
    archiveVersion = project.version.toString()
    archiveClassifier = 'desktop'

    manifest {
        attributes(
            'Implementation-Title': project.name,
            'Implementation-Version': project.version.toString(),
            'Specification-Version': '2.4',
            'Build-Revision': 'example-git-sha'
        )
    }
}
~~~

Build:

~~~bash
./gradlew clean jar
~~~

Artifact:

~~~text
build/libs/version-demo-2.4.1-desktop.jar
~~~

Run:

~~~bash
java -cp build/libs/version-demo-2.4.1-desktop.jar com.acme.version.VersionInfo
~~~

Stdout:

~~~text
Implementation-Title=version-demo
Implementation-Version=2.4.1
~~~

Gradle project.version and the manifest version are configured from the same value to avoid drift.

## 13. Release versions and reproducible artifacts

A good release must be traceable to its source and have immutable contents.

Example release metadata:

~~~text
Application-Version: 2.4.1
Artifact: customer-client-2.4.1.jar
Git-Revision: abc1234
Build-Number: 184
JDK: 24.0.2
Maven: 3.9.12
SHA-256: <computed-checksum>
~~~

In practice, the checksum must be computed from the real artifact. Do not hard-code a sample checksum into a POM or source file.

To make artifacts reproducible:

- Pin the JDK and build tool.
- Pin plugin versions.
- Lock dependencies.
- Normalize timestamps if the archive requires it.
- Do not write username, hostname, or current time into the artifact if unnecessary.
- Preserve source revision and build metadata.
- Build twice from the same source in a controlled environment and compare checksums.

A version does not replace a checksum. Two artifacts with the same version but different checksums are a sign that needs investigation.

## 14. Troubleshooting artifact version issues

### JAR filename does not match the version in the POM

Check project.version, artifactId, classifier, and archive naming configuration. In Gradle, inspect archiveVersion and archiveClassifier. In Maven, inspect finalName and plugin configuration.

### Runtime returns null when reading Implementation-Version

The class may be running from a classes directory, the JAR may lack Implementation-Version, or the manifest attribute may be in the wrong section. Check:

~~~bash
jar --list --file app.jar
jar --extract --file app.jar META-INF/MANIFEST.MF
~~~

Ensure the attribute is in the main section of the manifest if you want it to apply to the package.

### java -jar reports no main manifest attribute

Implementation-Version does not declare the main class. Add Main-Class via the Maven/Gradle manifest or jar --main-class, then inspect the manifest.

### Maven SNAPSHOT does not update as expected

Check snapshotRepository, repository updatePolicy, metadata, and local cache. SNAPSHOT resolution depends on repository metadata; do not manually rename a local JAR into a timestamped snapshot.

### Dependency resolves to a different version

Run mvn dependency:tree or Gradle dependencyInsight. Check transitive dependencies, version constraints, dependencyManagement, BOMs, and locking.

### Version 2.10 is treated as smaller than 2.9

Do not use string comparison. Use a comparator designed for the corresponding version scheme.

### SemVer pre-release versions are ordered incorrectly

Check whether the parser supports SemVer 2 and numeric identifier rules. Do not use a Maven version comparator as a general-purpose SemVer 2 comparator.

### Installer version does not match JAR version

Check --app-version, JAR Implementation-Version, and release metadata. Separate the application version from the package revision and Java runtime version.

### A published release artifact needs a fix

Do not replace the file under the same release version. Create a new version, update dependencies and release notes, and publish the new artifact.

## 15. Recommended version release workflow

1. Define the scope of changes and the public API.
2. Choose MAJOR, MINOR, or PATCH according to the compatibility policy.
3. Finalize the version in the Maven POM or Gradle project.
4. Verify dependency versions and Java runtime target.
5. Run unit, integration, and compatibility tests.
6. Create a Git tag for the version.
7. Build the artifact from the exact tag/commit.
8. Record Implementation-Version and Git revision in the manifest.
9. Set the proper version for the application and native installer.
10. Generate checksums, signatures, and provenance.
11. Verify the filename, manifest, GAV, and package metadata.
12. Publish to the release repository.
13. Save release notes and verification results.
14. Keep the released artifact immutable.

## 16. Artifact version management checklist

- Public API or compatibility contract is defined.
- Clear MAJOR/MINOR/PATCH rules are in place.
- Pre-release labels are used for their intended purpose.
- Build metadata is not mistaken for version precedence.
- Maven GAV or Gradle group/name/version are consistent.
- SNAPSHOTs are used only during development.
- Release versions are never overwritten.
- Dependency versions are pinned or locked.
- Versions are not compared using String.compareTo().
- Maven version ordering is not confused with SemVer 2.
- JAR manifest contains Implementation-Version.
- Manifest-Version is not confused with the application version.
- Main-Class is declared separately if java -jar is needed.
- Package.getImplementationVersion() has been verified.
- jpackage --app-version matches the product version.
- Package identity remains stable across upgrades.
- Java runtime version is recorded separately.
- Git tag and build revision are traceable.
- Checksums are computed from the final artifact.
- Release artifacts are immutable and have provenance.

## 17. Key terms to remember

| Term | Meaning |
|---|---|
| Artifact version | Version of a built file/component |
| SemVer | MAJOR.MINOR.PATCH rules based on the public API |
| Major | Backward-incompatible change |
| Minor | New backward-compatible functionality |
| Patch | Backward-compatible bug fix |
| Pre-release | Alpha, beta, or release candidate version |
| Build metadata | Metadata after a plus sign, does not affect SemVer precedence |
| GAV | Maven groupId, artifactId, version |
| SNAPSHOT | Development version that changes according to repository metadata |
| Classifier | Suffix distinguishing the artifact type |
| Implementation-Version | Implementation version in the JAR manifest |
| Specification-Version | Version of the specification/API contract |
| Main-Class | Entry point to run a JAR with java -jar |
| jpackage --app-version | Version of the application/native package |
| Package revision | Packaging revision per package manager rules |
| Git tag | Source revision label for a version |
| Build number | Identifier for a single CI run |
| Provenance | Source and process information for how an artifact was produced |
| Immutable release | A published artifact that is never replaced |

Good artifact version management starts with a clear compatibility policy and a single canonical version source. Synchronize Maven/Gradle coordinates, JAR manifest, installer metadata, and Git tags; distinguish the product version from the Java runtime and build number; verify dependency resolution and keep release artifacts immutable. That way, users can select the right dependencies, run the exact application version, and accurately trace released binaries.

## References

- Semantic Versioning — [Semantic Versioning 2.0.0](https://semver.org/)
- Apache Maven — [POM Reference and Maven Coordinates](https://maven.apache.org/pom.html)
- Apache Maven — [Version Order Specification](https://maven.apache.org/pom.html#version-order-specification)
- Sonatype — [Publishing Requirements and Correct Coordinates](https://central.sonatype.org/publish/requirements/)
- Gradle — [Working With Files and Archive Tasks](https://docs.gradle.org/current/userguide/working_with_files.html)
- Gradle — [Building Java & JVM Projects](https://docs.gradle.org/current/userguide/building_java_projects.html)
- Oracle JDK 24 — [JAR File Specification](https://docs.oracle.com/en/java/javase/24/docs/specs/jar/jar.html)
- Oracle JDK 24 — [Packaging Tool User's Guide](https://docs.oracle.com/en/java/javase/24/jpackage/index.html)
