# Role of group, artifact, version, and product identity

When releasing a Spring Boot application, different names may appear: the Gradle project name, group, artifactId, version, executable JAR filename, Spring application name, and container image name. **Those names are not synonymous by default**. For example, a build might set `project.name=metadata-demo`, `group=com.example.catalog`, `version=1.2.3`, yet produce `catalog-service-1.2.3.jar` and run a service with `spring.application.name=orders-api`.

To manage a release properly, you need to distinguish:

1. **Group:** the namespace/group behind the artifact.
2. **Artifact:** the distribution unit and logical name used when publishing/resolving.
3. **Version:** the release milestone of the artifact.
4. **Product/application identity:** the product name and logical service name in the system.
5. **Binary identity:** the checksum/digest of the exact built file or deployed image.

**Key takeaway:** `groupId:artifactId:version` (GAV) locates the module/version in a repository; the Gradle archive task determines the output filename; Spring Boot build-info indicates the metadata embedded in the binary; `spring.application.name` serves as the runtime identity. When investigating production incidents, cross-reference them instead of guessing.

The examples use Java 17, Spring Boot 3.3.5, and Gradle 8.7 for concrete configurations. These are illustrative versions, not a claim of the latest version.

## 1. What is GAV?

Example Maven coordinates:

~~~text
com.example.catalog:catalog-api:1.2.3
~~~

| Part | Meaning | Example |
| --- | --- | --- |
| `groupId` | Namespace/group of the artifact | `com.example.catalog` |
| `artifactId` | Logical name of the artifact | `catalog-api` |
| `version` | Version of the module | `1.2.3` |

In a Maven repository with standard layout, the JAR and POM for these coordinates can be stored under:

~~~text
com/example/catalog/catalog-api/1.2.3/catalog-api-1.2.3.jar
com/example/catalog/catalog-api/1.2.3/catalog-api-1.2.3.pom
~~~

Dots in `groupId` are converted into separators in the repository path. This is neither a Java source path nor the internal structure of a Spring Boot executable JAR.

**Note:** GAV is a **module/version** coordinate, but a module may also have sources files, Javadoc, a `tests` classifier artifact, a POM, or a WAR. The `classifier` and `extension/type` fields may be needed to point to the exact artifact file.

~~~text
GAV:        com.example.catalog:catalog-api:1.2.3
classifier: tests      (optional)
extension:  jar        (example)
~~~

One GAV coordinate can appear in multiple repositories; do not treat the same GAV in two places as absolute proof of identical bytes. Especially with snapshots or repositories that allow overwriting, use checksums and release provenance to verify the content.

### `groupId` does not have to match the Java package

A library may have groupId `com.example.catalog` yet contain classes in `com.example.catalog.domain`, `com.example.shared`, or other packages. Choose a group with a stable convention, typically a reverse domain controlled by the organization, to reduce name collisions. However, declaring a group does not automatically grant publish permission: the repository still checks authentication, authorization, and namespace policy.

### ArtifactId is not a marketing product name

A **Catalog Platform** product can contain three artifacts:

~~~text
com.example.catalog:catalog-core:1.2.3
com.example.catalog:catalog-api:1.2.3
com.example.catalog:catalog-batch:1.2.3
~~~

The three artifactIds should distinguish the units that are published/deployed. Sharing the same artifactId and version across different binaries can cause collisions in the repository.

## 2. Gradle `project.group`, `project.name`, and `project.version`

In `build.gradle` (Groovy DSL):

~~~groovy
group = 'com.example.catalog'
version = '1.2.3'
~~~

Gradle `project.name` is typically declared in `settings.gradle`:

~~~groovy
rootProject.name = 'metadata-demo'
~~~

When using the **Maven Publish plugin**, the default values of `MavenPublication` are:

| Publication field | Default value |
| --- | --- |
| `groupId` | `project.group` |
| `artifactId` | `project.name` |
| `version` | `project.version` |

With the values above, an un-overridden Maven publication defaults to the GAV:

~~~text
com.example.catalog:metadata-demo:1.2.3
~~~

**Do not confuse `project.name` with the output filename:** the JAR filename also depends on `archiveBaseName`, `archiveVersion`, `archiveClassifier`, and `archiveFileName`.

### Maven POM comparison

Maven declares these directly:

~~~xml
<groupId>com.example.catalog</groupId>
<artifactId>metadata-demo</artifactId>
<version>1.2.3</version>
~~~

Maven also has `<name>Catalog Service</name>` to display a human-friendly project name. `<name>` does not replace `<artifactId>`. In Maven, `groupId` and `version` can be inherited from a parent; inspect the effective POM if the child file does not declare them explicitly.

### Varying group by environment?

Normally, there is **no need** to create separate GAVs like `com.example.catalog.dev:catalog-api:1.2.3` and `com.example.catalog.prod:catalog-api:1.2.3` just for deploying across dev/staging/prod. The same release artifact should be promoted with the exact same bytes, while URLs, profiles, credentials, and server settings are supplied at runtime/deployment. If an organization has a policy for environment-specific artifacts, it must be managed consistently rather than applied ad hoc.

## 3. `version` is the artifact version, not the tool version

A project can simultaneously use:

~~~text
Application artifact version: 1.2.3
Spring Boot Gradle plugin:    3.3.5
Gradle Wrapper:              8.7
Java toolchain:              17
Git revision:                <commit-id>
~~~

`project.version=1.2.3` does not mean running Spring Boot 1.2.3 or Java 1.2.3. These versions follow independent axes.

### Semantic Versioning

Common convention:

~~~text
MAJOR.MINOR.PATCH
1.2.3
~~~

- **MAJOR:** incompatible changes according to the published contract.
- **MINOR:** backward-compatible feature additions.
- **PATCH:** backward-compatible bug fixes.

This is a policy enforced by the development team. Maven/Gradle **do not automatically guarantee** that a version is backward compatible just because it has three numbers.

### Snapshot and release

~~~text
1.3.0-SNAPSHOT
1.3.0-RC1
1.3.0
~~~

`SNAPSHOT` is typically used for development builds and can be published multiple times with corresponding metadata/timestamps; official releases should follow an immutability policy. Avoid overwriting a new file under the same release coordinate `1.2.3`, because consumers, caches, and rollbacks might pick up different bytes while seeing the same version.

Version **does not replace a Git commit or SHA-256**. Two rebuilds with the same version but different bytes due to dependencies/timestamps/build environment also require governance.

### One repo, multiple module versions

A multi-project build can use a **release train**:

~~~text
catalog-core:1.2.3
catalog-api:1.2.3
catalog-batch:1.2.3
~~~

or **independent versioning**:

~~~text
catalog-core:2.0.1
catalog-api:1.2.3
catalog-batch:0.8.4
~~~

Either policy requires release records, compatibility tests, and non-colliding coordinates. Modules sharing a repository do not have to share the same version.

## 4. JAR/WAR filename vs. Maven artifactId

Gradle archive tasks such as `jar`, `bootJar`, `war`, and `bootWar` have these properties:

| Property | Role | Example |
| --- | --- | --- |
| `archiveBaseName` | Base name of the archive | `catalog-service` |
| `archiveVersion` | Version appended to filename by convention | `1.2.3` |
| `archiveClassifier` | Distinguishes archive variant | `plain` |
| `archiveExtension` | Extension | `jar` |
| `archiveFileName` | Complete filename when overridden | `release.jar` |
| `destinationDirectory` | Output directory | `build/libs` |

With baseName `catalog-service`, archiveVersion `1.2.3`, empty classifier, and extension `jar`, the filename is typically:

~~~text
catalog-service-1.2.3.jar
~~~

If `archiveFileName.set('release.jar')`, the filename is fixed to `release.jar` and no longer changes automatically with `project.version`.

~~~groovy
tasks.named('bootJar') {
    archiveBaseName.set('catalog-service')
    archiveVersion.set(project.version.toString())
}
~~~

This snippet is placed in a project with the Spring Boot plugin and Java plugin. `bootJar` is an executable Boot archive; the Java plugin's `jar` task can produce a plain JAR with classifier `plain` depending on plugin configuration. Do not assume two `.jar` files serve the same purpose.

**Important example:**

~~~text
Gradle project.name           = metadata-demo
Gradle bootJar baseName      = catalog-service
Maven publication artifactId = metadata-demo (if default)
~~~

These three values can differ without conflict. The local filename and the artifact name published to a repository can also differ.

## 5. Spring Boot build metadata: `build-info.properties`

The Spring Boot Gradle plugin has a `bootBuildInfo` task that generates `META-INF/build-info.properties`. In an executable Boot JAR, this file typically resides at:

~~~text
BOOT-INF/classes/META-INF/build-info.properties
~~~

When configured with `springBoot { buildInfo() }` or a `springBoot { buildInfo { ... } }` block, Gradle integrates this task into resources/classes build. Spring Boot can auto-configure `BuildProperties` if the resource is present on the runtime classpath.

As of Spring Boot 3.3, the defaults are:

| Build info key | Default source |
| --- | --- |
| `build.artifact` | Base name of `bootJar` or `bootWar` |
| `build.group` | Gradle `project.group` |
| `build.name` | Gradle `project.name` |
| `build.version` | Gradle `project.version` |
| `build.time` | Build time, unless excluded |

The most common point of confusion: **`build.artifact` does not default to `MavenPublication.artifactId`**. One comes from the Boot archive base name, while the other comes from the Gradle project name or publication override.

### `spring.application.name` is the runtime identity

In Spring configuration:

~~~properties
spring.application.name=orders-api
~~~

This name may be used by logging, tracing, or service discovery depending on integration. It does not automatically change the group, artifactId, version, or archive file.

A service might have:

~~~text
Build group:             com.example.catalog
Build artifact:          catalog-service
Build name:              metadata-demo
Build version:           1.2.3
Spring application name: orders-api
~~~

If monitoring uses `orders-api` while the published artifact is named `catalog-service`, that is valid as long as there is a clear release mapping.

## 6. Complete hands-on lab: differing build info and application name

Example using Java 17, Spring Boot 3.3.5, and Gradle Groovy DSL. The goal is to produce an executable JAR with `project.name=metadata-demo`, `group=com.example.catalog`, `version=1.2.3`, `archiveBaseName=catalog-service`, and Spring app name `orders-api`.

### Directory structure

~~~text
metadata-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/catalog/MetadataDemoApplication.java
    └── resources/application.properties
~~~

### File `settings.gradle`

~~~groovy
rootProject.name = 'metadata-demo'
~~~

### File `build.gradle`

~~~groovy
import org.springframework.boot.gradle.tasks.bundling.BootJar

plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example.catalog'
version = '1.2.3'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}

springBoot {
    mainClass = 'com.example.catalog.MetadataDemoApplication'

    buildInfo {
        // Exclude build.time so metadata does not change on every build.
        excludes = ['time']
    }
}

tasks.named('bootJar', BootJar) {
    archiveBaseName.set('catalog-service')
    archiveVersion.set(project.version.toString())
}
~~~

**Explanation:**

1. Gradle `project.name` comes from settings; `group` and `version` are set in the build script.
2. `bootJar.archiveBaseName` renames the binary without changing `project.name`.
3. `springBoot.buildInfo` enables the `bootBuildInfo` task and generates the metadata resource. `excludes=['time']` prevents build-info from changing its timestamp every time, improving up-to-date checks and metadata reproducibility.
4. `spring-boot-starter` provides a minimal runtime for a Spring Boot command-line app without starting an HTTP server.
5. `maven-publish` is not enabled in this sample, so declaring `group`/`version` does not mean the application is published.

### File `src/main/resources/application.properties`

~~~properties
spring.application.name=orders-api
~~~

### File `src/main/java/com/example/catalog/MetadataDemoApplication.java`

~~~java
package com.example.catalog;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.info.BuildProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class MetadataDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MetadataDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner showIdentity(
            BuildProperties info, Environment environment) {
        return args -> {
            System.out.println("APP_NAME=" +
                    environment.getProperty(
                            "spring.application.name", "unnamed"));
            System.out.println("BUILD_GROUP=" + info.getGroup());
            System.out.println("BUILD_ARTIFACT=" + info.getArtifact());
            System.out.println("BUILD_NAME=" + info.getName());
            System.out.println("BUILD_VERSION=" + info.getVersion());
        };
    }
}
~~~

`BuildProperties` is auto-configured by Spring Boot from `META-INF/build-info.properties` if the resource is present. If you remove `buildInfo` while keeping the required injection, startup may fail due to a missing bean. The Java class has matching package and filename, valid on Java 17.

### Build and run

If a compatible Gradle Wrapper 8.7 is present, run from root:

~~~bash
./gradlew clean bootJar
~~~

Output:

~~~text
build/libs/catalog-service-1.2.3.jar
~~~

Run:

~~~bash
java -jar build/libs/catalog-service-1.2.3.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Five lines **printed by the application**:

~~~text
APP_NAME=orders-api
BUILD_GROUP=com.example.catalog
BUILD_ARTIFACT=catalog-service
BUILD_NAME=metadata-demo
BUILD_VERSION=1.2.3
~~~

Other Spring Boot/JVM logs may vary by environment. Because there is no web server, the command-line application exits once the runner completes if no background work remains.

### Inspect the archive

~~~bash
jar tf build/libs/catalog-service-1.2.3.jar
~~~

Look for:

~~~text
META-INF/MANIFEST.MF
BOOT-INF/classes/com/example/catalog/MetadataDemoApplication.class
BOOT-INF/classes/application.properties
BOOT-INF/classes/META-INF/build-info.properties
~~~

`jar tf` only lists entries. If `unzip` is available on Linux/macOS:

~~~bash
unzip -p build/libs/catalog-service-1.2.3.jar BOOT-INF/classes/META-INF/build-info.properties
~~~

Key properties:

~~~properties
build.artifact=catalog-service
build.group=com.example.catalog
build.name=metadata-demo
build.version=1.2.3
~~~

There is no requirement for fixed line order or for the file to contain only four keys. The example excluded the default `build.time`.

On Windows PowerShell use `.\gradlew.bat` instead of `./gradlew`; Java/JDK commands can be used similarly.

## 7. What does changing each value affect?

| Change | Primary effect | Not automatically changed |
| --- | --- | --- |
| `group='com.example.new'` | `build.group`, default Maven publication groupId if present | `spring.application.name` |
| `version='1.2.4'` | `build.version` and filename if archiveVersion uses project.version | Java package |
| `rootProject.name='catalog-project'` | project.name, default `build.name`, default publication artifactId | Explicitly set archiveBaseName |
| `archiveBaseName='catalog-v2'` | Filename and default `build.artifact` | Maven publication artifactId |
| `spring.application.name=inventory-api` | Spring Environment app name | GAV |
| `archiveFileName='fixed.jar'` | Fixed filename | Project version metadata |

**Do not force all fields to have identical names at all costs.** Sometimes you want the app name to describe the logical service, artifactId to describe the published library, and archive name to describe the deployed binary. The right approach is agreeing on a **mapping convention**, not forcing semantically wrong uniformity.

## 8. Publishing a Java library: Maven artifactId can differ from JAR filename

To learn Maven coordinates properly, use a **standalone Java library**, not a Spring Boot executable archive as a dependency library.

Structure:

~~~text
formatter-library/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/format/TextFormatter.java
~~~

### `settings.gradle`

~~~groovy
rootProject.name = 'formatter-library'
~~~

### `build.gradle`

~~~groovy
import org.gradle.api.publish.maven.MavenPublication

plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'com.example.catalog'
version = '1.2.3'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

publishing {
    publications {
        library(MavenPublication) {
            from components.java
            artifactId = 'format-kit'
        }
    }
}
~~~

### `src/main/java/com/example/format/TextFormatter.java`

~~~java
package com.example.format;

public final class TextFormatter {
    private TextFormatter() {
    }

    public static String normalize(String value) {
        return value.trim().toUpperCase(java.util.Locale.ROOT);
    }
}
~~~

Run from root with a compatible Gradle Wrapper:

~~~bash
./gradlew clean jar
./gradlew publishToMavenLocal
~~~

The local JAR produced by the `jar` task is typically:

~~~text
build/libs/formatter-library-1.2.3.jar
~~~

However, the Maven publication is:

~~~text
com.example.catalog:format-kit:1.2.3
~~~

In the standard Maven local repository:

~~~text
~/.m2/repository/com/example/catalog/format-kit/1.2.3/
    format-kit-1.2.3.jar
    format-kit-1.2.3.pom
~~~

The repository directory can vary by configuration/OS. ArtifactId is overridden to `format-kit` for the publication, **without requiring the local output filename to change**. A consumer can use:

~~~groovy
repositories {
    mavenLocal()
}

dependencies {
    implementation 'com.example.catalog:format-kit:1.2.3'
}
~~~

This is a snippet from **another project** with the Java plugin; in real CI, use a managed repository instead of relying on Maven local on a developer machine.

### Why not publish a Boot JAR arbitrarily as a Java library?

A Spring Boot executable JAR contains a launcher, `BOOT-INF/classes`, and nested runtime dependencies. An ordinary Java library JAR has classes at the root and metadata serving consumer compile/runtime variants. Copying a library's `from components.java` into an application publish pipeline without checking the artifact type can distribute a plain JAR instead of a Boot executable or create unsuitable dependencies. If you need to publish an executable service, configure a dedicated publication/distribution.

## 9. Maven POM: GAV and output filename

A Spring Boot Maven project can declare:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example.catalog</groupId>
    <artifactId>metadata-demo</artifactId>
    <version>1.2.3</version>
    <name>Catalog Service</name>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <finalName>catalog-service</finalName>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <configuration>
                    <mainClass>com.example.catalog.MetadataDemoApplication</mainClass>
                </configuration>
                <executions>
                    <execution>
                        <id>generate-build-info</id>
                        <goals>
                            <goal>build-info</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

This is an **alternative Maven option**; you do not need to maintain Gradle and Maven simultaneously. The Boot parent manages many dependency/plugin versions and supports `repackage` when `spring-boot-maven-plugin` is applied. The `build-info` goal here generates metadata for `BuildProperties`.

This POM has:

~~~text
GAV:      com.example.catalog:metadata-demo:1.2.3
<name>:   Catalog Service
<finalName>: catalog-service
~~~

After `mvn clean package`, the main JAR is expected to be `target/catalog-service.jar`. **`finalName` renames the file without changing Maven artifactId/version**. Without an override, Maven normally names the file using `artifactId-version`.

Also note that Spring Boot Maven build-info draws values from the **Maven project**, which can differ from how Gradle build-info takes `build.artifact` from the Boot archive base name. Do not copy the expected stdout from the Gradle example and treat it as mandatory for every Maven build.

## 10. Inspecting build-info with Java 17 without running Spring

If `unzip` is unavailable, create a standalone file `BuildInfoInspector.java`:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;

public final class BuildInfoInspector {
    private BuildInfoInspector() {
    }

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            System.err.println("Usage: java BuildInfoInspector <boot-jar>");
            System.exit(2);
        }

        try (JarFile jar = new JarFile(args[0])) {
            JarEntry entry = jar.getJarEntry(
                    "BOOT-INF/classes/META-INF/build-info.properties");
            if (entry == null) {
                System.err.println("BUILD_INFO_MISSING");
                System.exit(3);
            }

            Properties props = new Properties();
            try (InputStream input = jar.getInputStream(entry)) {
                props.load(input);
            }

            System.out.println("GROUP=" +
                    props.getProperty("build.group", "(absent)"));
            System.out.println("ARTIFACT=" +
                    props.getProperty("build.artifact", "(absent)"));
            System.out.println("NAME=" +
                    props.getProperty("build.name", "(absent)"));
            System.out.println("VERSION=" +
                    props.getProperty("build.version", "(absent)"));
        }
    }
}
~~~

Compile:

~~~bash
javac BuildInfoInspector.java
~~~

Run after building the Gradle demo:

~~~bash
java BuildInfoInspector build/libs/catalog-service-1.2.3.jar
~~~

Stdout:

~~~text
GROUP=com.example.catalog
ARTIFACT=catalog-service
NAME=metadata-demo
VERSION=1.2.3
~~~

`JarFile` opens the outer executable Boot JAR and reads the build-info entry without extracting nested dependencies or running the application. If given a plain JAR or a Boot JAR without build-info enabled, the program prints `BUILD_INFO_MISSING` and exits non-zero instead of guessing the version from the filename.

## 11. Runtime identity, image tag, and binary checksum

A product can be described as:

~~~text
Product:                Catalog Platform
Spring application name: orders-api
Gradle project name:    metadata-demo
Maven GAV:              com.example.catalog:metadata-demo:1.2.3
Executable file:        catalog-service-1.2.3.jar
Container image tag:    registry.example.test/catalog/orders-api:1.2.3
Git revision:           <commit-id-from-CI>
Image digest:           sha256:<digest-from-registry>
~~~

Values in angle brackets are **placeholders**, not verified data. `registry.example.test` is an illustrative hostname. Docker/OCI tags can be reassigned if registry policy allows; a concrete digest reflects image contents more reliably than a tag alone.

`spring.application.name` is the logical identity of the service, while environment (`dev`/`staging`/`prod`), region, Kubernetes Deployment/Pod, and container ID are deployment details. Do not embed the environment into GAV just to distinguish where it runs if the release process promotes **the same binary** across multiple environments.

### Artifact hash

Linux/macOS:

~~~bash
sha256sum build/libs/catalog-service-1.2.3.jar
~~~

Windows PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 build/libs/catalog-service-1.2.3.jar
~~~

A checksum is computed from the **actual bytes**, so there is no fixed output in this lesson. Use GAV, artifact hash, Git commit, and CI run/image digest when you need to verify the exact deployed version.

### Build time and reproducibility

Spring Boot `build-info.properties` by default can contain `build.time`, which changes with every build timestamp. According to Spring Boot 3.3 documentation, this causes the build-info task to always change its output and affects up-to-date checks. In the example:

~~~groovy
springBoot {
    buildInfo {
        excludes = ['time']
    }
}
~~~

removes one source of time variation. However, simply omitting the timestamp **does not guarantee the entire JAR will have the same SHA-256** on rebuild: dependency resolution, archive metadata, generated sources, toolchains, and other inputs still need to be managed.

### Metadata security

Build-info files, manifests, logs, and Actuator `info` may be visible to anyone authorized to read the artifact or endpoint. Do not put passwords, tokens, private keys, secret endpoint credentials, or sensitive data into metadata. If using the Actuator info endpoint, configure appropriate access permissions and exposure rather than leaving it public by default.

## 12. Commands to inspect GAV and artifacts

### Gradle

~~~bash
./gradlew properties
./gradlew tasks --all
./gradlew clean bootJar
jar tf build/libs/catalog-service-1.2.3.jar
~~~

In a multi-project build, if the app is in subproject `:app`:

~~~bash
./gradlew :app:properties
./gradlew :app:bootJar
~~~

Only use the exact project path defined in settings. `properties` displays many values, while `jar tf` shows the final artifact contents. Do not treat an output filename as sole proof of publication.

### Maven

~~~bash
mvn help:effective-pom
mvn help:evaluate -Dexpression=project.groupId -q -DforceStdout
mvn help:evaluate -Dexpression=project.artifactId -q -DforceStdout
mvn help:evaluate -Dexpression=project.version -q -DforceStdout
~~~

`effective-pom` shows fields after inheritance and plugin/dependency management. `help:evaluate` requires the Maven Help Plugin to be resolved. If a project only imports the Spring Boot BOM without configuring the packaging plugin, the BOM **does not automatically generate an executable JAR** or bind the `repackage` goal.

### Manifest is not Maven POM

A Spring Boot executable JAR typically contains:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.catalog.MetadataDemoApplication
~~~

These two values are used to launch Java/Spring Boot; **they are not GAV**. `Implementation-Version` in the manifest does not always appear automatically just because `project.version` has a value; use build-info or configure the manifest separately if needed.

## 13. Common error reference table

| Symptom | Cause | Fix |
| --- | --- | --- |
| Renamed `bootJar` but Maven artifactId stayed the same | Archive name and publication metadata are independent | Check `MavenPublication` and generated POM |
| `build.artifact` differs from Maven artifactId | Boot build-info uses the archive base name | Define a mapping policy and configure the right place |
| Changed version but filename stayed `app.jar` | Fixed `archiveFileName` | Use `archiveVersion` from `project.version` |
| `spring.application.name` differs from `project.name` | Two different roles | Keep runtime identity separate and document the mapping |
| Missing `BuildProperties` bean | `build-info.properties` not generated/packaged | Enable `buildInfo` and inspect the archive |
| Manifest lacks `Implementation-Version` | That field was not configured | Use build-info or a dedicated manifest attribute |
| CI publishes wrong artifactId | Maven Publish defaults to `project.name` | Override `artifactId` in the publication |
| Local Maven cache has stale build | Version reused or stale publish | Inspect POM/hash and bump release version per policy |
| App runs old artifact despite identical tag | Registry/deployment/cache used a different file | Compare checksums and image digests |
| Using Boot JAR as Java library causes load error | Executable layout differs from ordinary JAR | Publish the library component/variant |
| Multiple modules publish same GAV | Coordinate collision | Set distinct artifactId or version |
| `ClassNotFoundException` at runtime | Dependency/packaging/classpath issue, not just metadata | Check `BOOT-INF/lib` and launcher |
| Actuator info leaks secrets | Unsafe metadata/exposure | Never embed secrets; restrict access |
| Maven parent obscures version | Group/version may be inherited | Inspect `effective-pom` |

## 14. Release checklist

1. **Identify the product, owner, and namespace group**.
2. **Choose a clear artifactId per module**, avoiding duplicate GAVs for different bytes.
3. **Set versions according to policy**, distinguishing snapshots from releases.
4. **Distinguish project version** from Spring Boot, Gradle, Java, and dependency versions.
5. **Identify the output file** of `bootJar`/`bootWar` versus plain `jar`/`war`.
6. **Build the exact artifact** using controlled Wrapper/toolchain/versions.
7. **Read `build-info.properties` from the actual artifact**: group, artifact, name, version.
8. **Cross-check Maven publication/POM** instead of guessing artifactId from the filename.
9. **Verify runtime `spring.application.name`** matches logging/observability systems.
10. **Attach provenance**: Git SHA, CI run, checksum, and image digest when available.
11. **Do not overwrite a release artifact** under the same coordinates with modified contents.
12. **Do not put secrets into metadata**.
13. **Smoke test with the exact executable JAR/container image** that will be deployed.
14. **Record a release entry** so teams can roll back and verify.

Sample release record:

~~~text
Product: Catalog Platform
Application name: orders-api
Group: com.example.catalog
Publication artifactId: metadata-demo
Version: 1.2.3
Executable JAR: catalog-service-1.2.3.jar
Git commit: <actual-commit>
SHA-256: <actual-hash>
OCI digest (if used): <actual-digest>
~~~

This is only a **template to fill in**; replace the values in angle brackets with real results from CI/repository; do not put fabricated commits or hashes into release records.

## 15. Review questions

**Question 1.** Gradle project group `com.example.catalog`, name `metadata-demo`, version `1.2.3`. What is the default GAV of `MavenPublication`?

**Answer:** `com.example.catalog:metadata-demo:1.2.3`.

**Question 2.** If `bootJar.archiveBaseName='catalog-service'`, does the Maven artifactId automatically change to `catalog-service`?

**Answer:** No. Archive base name and Maven publication artifactId are two separate properties; Gradle Maven Publish defaults `artifactId` from `project.name`.

**Question 3.** Why is `build.artifact=catalog-service` while `build.name=metadata-demo`?

**Answer:** Spring Boot Gradle build-info defaults `artifact` from the Boot archive base name and `name` from Gradle `project.name`.

**Question 4.** Does `spring.application.name=orders-api` change GAV?

**Answer:** No. It is a runtime Spring property, not Maven/Gradle publication metadata.

**Question 5.** Is `project.version=1.2.3` the Spring Boot framework version?

**Answer:** No. It is the product/library version; the Boot plugin version is declared separately.

**Question 6.** Does Maven `<finalName>catalog-service</finalName>` make the artifactId `catalog-service`?

**Answer:** No. It changes the output filename without altering the `groupId:artifactId:version` coordinates.

**Question 7.** Why might the same GAV not prove two files have identical bytes?

**Answer:** Repositories/snapshots/overwrites or non-reproducible rebuilds can yield different bytes; hashes, immutability, and provenance are required.

**Question 8.** What should an application use to print its built version?

**Answer:** Enable Spring Boot build-info, ensure `META-INF/build-info.properties` is on the classpath, and read it with `BuildProperties`.

**Question 9.** Library `formatter-library` publishes artifactId `format-kit`; which coordinate must consumers use?

**Answer:** Use the published coordinate `com.example.catalog:format-kit:1.2.3`; the local JAR filename may still be `formatter-library-1.2.3.jar`.

**Question 10.** Why should production audits not rely solely on Docker tag `1.2.3`?

**Answer:** Tags can be retagged if policy permits; digests/checksums verify the exact deployed contents.

## 16. Official documentation

- Maven — [Maven Artifacts](https://maven.apache.org/repositories/artifacts.html): GAV, classifier, extension, and repository coordinates.
- Maven — [Naming Conventions](https://maven.apache.org/guides/mini/guide-naming-conventions.html): groupId, artifactId, version, and SNAPSHOT.
- Maven — [Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html): GAV in POM, packaging, and defaults.
- Gradle — [Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html): default `MavenPublication` fields and artifactId override.
- Gradle — [MavenPublication API](https://docs.gradle.org/current/javadoc/org/gradle/api/publish/maven/MavenPublication.html): mapping project group/name/version.
- Gradle — [The Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html): archive tasks and library outputs.
- Spring Boot 3.3 — [Integrating with Actuator](https://docs.spring.io/spring-boot/3.3/gradle-plugin/integrating-with-actuator.html): `bootBuildInfo`, `build.artifact/group/name/version/time`.
- Spring Boot 3.3 — [Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html): `bootJar` and output archives.
- Spring Boot — [Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): runtime info and endpoint security.

**Remember:** GAV identifies **the artifact in a repository**, archive properties determine **the built filename**, Spring Boot build-info defines **metadata inside the binary**, and `spring.application.name` defines **the logical name of the runtime application**. When releasing or rolling back, verify **GAV → publication → file/checksum → build-info → deployment identity** instead of assuming all names match automatically.
