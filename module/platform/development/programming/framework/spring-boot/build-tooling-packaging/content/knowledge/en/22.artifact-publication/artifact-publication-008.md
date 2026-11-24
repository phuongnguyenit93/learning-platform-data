# Downloading Artifacts from a Repository and Verifying Execution or Usage from Another Project

## 1. Objective and Scope

Once a Java/Spring Boot product is published to an artifact repository, you must verify that users can **download the right version from the repository and use it in an independent environment**. Two product types must be distinguished:

1. **Executable application**: a Spring Boot JAR/WAR runnable with `java -jar` or deployable into a Servlet container. Download the artifact, inspect its manifest/runtime, and run smoke tests.
2. **Java library**: a JAR exposing a public API for another project to declare as a dependency, compile, test, and call classes/methods. Resolve POM/metadata along with transitive dependencies, then verify inside a consumer project.

**Both types cannot be verified the same way.** A Spring Boot executable JAR typically puts application classes under `BOOT-INF/classes` and nested dependencies under `BOOT-INF/lib`; that is not the layout of a normal library JAR on a Java compile classpath.

Examples use **Spring Boot 3.3.5**, Java 17, Maven Wrapper, Gradle Wrapper, and Maven Dependency Plugin 3.7.1. These are illustrative versions, not recommendations of the latest releases. Always use versions approved by your project.

After this lesson, you will be able to:

- Read Maven coordinates `groupId:artifactId:version[:type[:classifier]]` and understand artifact paths in a Maven-compatible repository.
- Distinguish releases, SNAPSHOTs, POM metadata, classifiers, executable JARs, and plain library JARs.
- Securely configure private repository credentials via Maven `settings.xml` or Gradle user properties.
- Download a specific artifact using the Maven Dependency Plugin and run the downloaded Spring Boot executable JAR.
- Create a Maven/Gradle consumer project to resolve the library, inspect the dependency graph, compile, test, and invoke the public API.
- Verify archive contents, manifest, Java compatibility, checksums, and signatures/provenance when available.
- Diagnose repository errors, wrong coordinates, missing POM/transitive dependencies, mistaking a Boot JAR for a library, version conflicts, and stale caches.

## 2. Artifact Repositories and Maven Coordinates

An artifact repository stores built binaries alongside metadata. A Maven module is typically identified by GAV:

- `groupId`: namespace, e.g. `com.example.catalog`.
- `artifactId`: module name, e.g. `catalog-client`.
- `version`: version, e.g. `1.4.2`.

Artifacts can have packaging/type such as `jar`, `war`, `pom` and classifiers such as `sources`, `javadoc`, `exec`, `tests`.

Examples:

~~~text
com.example.catalog:catalog-client:1.4.2
com.example.catalog:catalog-service:1.0.0:jar:exec
~~~

A standard Maven repository stores files along the path:

~~~text
<repository-root>/
└── com/
    └── example/
        └── catalog/
            └── catalog-client/
                └── 1.4.2/
                    ├── catalog-client-1.4.2.pom
                    ├── catalog-client-1.4.2.jar
                    └── ...
~~~

With classifier `exec`, the file is named `catalog-service-1.0.0-exec.jar`.

**The POM is not an optional decorative file.** It describes coordinates, packaging, and dependencies/scopes so consumers resolve the right graph. A JAR might download cleanly, yet if the POM is missing or wrong, consumers will still fail compilation or lack classes at runtime.

| File | Meaning |
| --- | --- |
| `artifact-version.jar` | Main binary JAR |
| `artifact-version.pom` | Maven metadata and transitive dependencies |
| `artifact-version-sources.jar` | Attached source code |
| `artifact-version-javadoc.jar` | API documentation |
| `artifact-version-exec.jar` | Executable variant with classifier `exec` |
| `.module` | Gradle Module Metadata if produced by a Gradle publisher |
| `.sha256`, `.sha512`, `.asc` | Checksum/signature sidecars if provided by the repository |
| `maven-metadata.xml` | Metadata for version/SNAPSHOT resolution |

Gradle reads both Maven POM and Gradle Module Metadata; Maven primarily uses the POM. Never delete metadata if consumers need it to determine dependency graphs or variants.

## 3. Distinguishing Executable JARs and Library JARs

Example Spring Boot executable JAR:

~~~text
catalog-service.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/com/example/catalog/...
    └── lib/spring-*.jar
~~~

Application classes reside under `BOOT-INF/classes`, while dependency JARs are nested inside `BOOT-INF/lib`. A consumer project's Java compiler **does not automatically treat these nested paths as a regular classpath**. Therefore, never use a fat JAR as a normal Java dependency.

A plain library JAR normally puts classes at the root:

~~~text
com/example/catalog/CatalogClient.class
META-INF/MANIFEST.MF
~~~

| Type | Inspection | Usage |
| --- | --- | --- |
| Spring Boot executable JAR | `BOOT-INF/classes`, `BOOT-INF/lib`, manifest/launcher | `java -jar app.jar` |
| Plain Java library | Packages/classes at root, POM metadata | Maven/Gradle dependency |
| Executable WAR | `WEB-INF/classes`, `WEB-INF/lib`, `WEB-INF/lib-provided` | `java -jar app.war` or external Servlet container |
| POM-only artifact | Metadata, parent/BOM/dependency management | Import as parent/BOM, not run as a JAR |
| Sources/Javadoc | Source/docs contents, classifier | IDE/documentation tooling |

**Rule:** use executable archives to run applications; use plain library JARs as dependencies. If the same module needs to publish both forms, publish two artifacts distinguished by classifier or split modules.

## 4. Repository URLs, Credentials, and Version Policy

Illustrative URLs:

~~~text
Release:
https://repo.example.com/repository/maven-releases/

Snapshot:
https://repo.example.com/repository/maven-snapshots/
~~~

Replace with URLs provided by your organization. Do not guess repository manager URLs from a server hostname.

### 4.1. Maven settings.xml

Maven looks up credentials in user settings:

- Linux/macOS: `~/.m2/settings.xml`.
- Windows: `%USERPROFILE%\.m2\settings.xml`.

Example:

~~~xml
<settings>
    <servers>
        <server>
            <id>company-releases</id>
            <username>${env.REPO_USER}</username>
            <password>${env.REPO_TOKEN}</password>
        </server>
        <server>
            <id>company-snapshots</id>
            <username>${env.REPO_USER}</username>
            <password>${env.REPO_TOKEN}</password>
        </server>
    </servers>
</settings>
~~~

`REPO_USER` and `REPO_TOKEN` are supplied from the developer environment/CI secret store. Maven settings support environment variable interpolation. **Never commit settings.xml containing tokens, never hardcode passwords in the POM, and never print credentials to logs.**

`id` in `<server>` must match the repository ID Maven uses to download/deploy. A mismatched ID can cause 401/403 errors even when the token is valid.

### 4.2. Gradle Credentials

Keep credentials outside the repository. For a repository named `companyReleases`, Gradle looks up `companyReleasesUsername` and `companyReleasesPassword` when using `credentials(PasswordCredentials)`. On developer machines, store real values in `GRADLE_USER_HOME/gradle.properties` with restricted read permissions; in CI, supply them from the secret store via `ORG_GRADLE_PROJECT_companyReleasesUsername` and `ORG_GRADLE_PROJECT_companyReleasesPassword`. Never commit credential files and never print values to logs.

### 4.3. Release and SNAPSHOT

| Version | Meaning | Recommendation |
| --- | --- | --- |
| `1.4.2` | Specific release, immutable after publish | Use for production |
| `1.5.0-RC1` | Pre-release | Use only when testing is acceptable |
| `1.5.0-SNAPSHOT` | Development build that may be republished | Use for dev/integration |

**Never overwrite an already published release version.** When fixes are needed, publish a new version. SNAPSHOTs use metadata and timestamped artifacts; caching can cause two machines to resolve at different points in time. Maven supports `-U` and Gradle supports `--refresh-dependencies` for deliberate refreshes.

## 5. Sample Producer: Publishing a Java Library with Maven

Create library `catalog-client` providing only a public API, with no Spring Boot launcher.

Structure:

~~~text
catalog-client/
├── pom.xml
└── src/main/java/com/example/catalog/
    └── CatalogClient.java
~~~

File `src/main/java/com/example/catalog/CatalogClient.java`:

~~~java
package com.example.catalog;

public final class CatalogClient {

    private CatalogClient() {
    }

    public static String greeting(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        return "Hello, " + name + " from catalog-client";
    }
}
~~~

### 5.1. Producer POM

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>catalog-client</artifactId>
    <version>1.4.2</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
        </plugins>
    </build>

    <distributionManagement>
        <repository>
            <id>company-releases</id>
            <url>https://repo.example.com/repository/maven-releases/</url>
        </repository>
        <snapshotRepository>
            <id>company-snapshots</id>
            <url>https://repo.example.com/repository/maven-snapshots/</url>
        </snapshotRepository>
    </distributionManagement>
</project>
~~~

- GAV identifies the artifact.
- Compiler release 17 produces Java 17-compatible bytecode.
- `distributionManagement` specifies where to **deploy**; this is not a consumer repository configuration.
- Repository IDs must match `settings.xml`.
- Maven deploy lifecycle uploads the JAR, POM, and required metadata.

Publish:

~~~bash
./mvnw --version
./mvnw clean deploy
~~~

PowerShell:

~~~powershell
.\mvnw.cmd --version
.\mvnw.cmd clean deploy
~~~

The repository may contain:

~~~text
com/example/catalog/catalog-client/1.4.2/
├── catalog-client-1.4.2.pom
└── catalog-client-1.4.2.jar
~~~

**Do not conclude publishing succeeded just because the JAR exists in `target`.** Confirm the artifact uploaded to the remote repository and an independent consumer resolves it remotely.

## 6. Maven Consumer: Downloading the Library and Calling the API

Create an independent project `catalog-consumer`. Do not reference producer sources, `systemPath`, or manually copied JARs; the consumer must resolve the GAV from the remote repository.

### 6.1. Consumer POM

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.consumer</groupId>
    <artifactId>catalog-consumer</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <junit.version>5.10.2</junit.version>
    </properties>

    <repositories>
        <repository>
            <id>company-releases</id>
            <url>https://repo.example.com/repository/maven-releases/</url>
            <releases>
                <enabled>true</enabled>
                <checksumPolicy>fail</checksumPolicy>
            </releases>
            <snapshots>
                <enabled>false</enabled>
            </snapshots>
        </repository>
    </repositories>

    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>catalog-client</artifactId>
            <version>1.4.2</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.version}</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Repository ID `company-releases` matches the server ID in Maven settings. `checksumPolicy=fail` stops Maven if a repository-provided checksum mismatches; it **does not replace** independent digital signatures/provenance.

### 6.2. Consumer Calling the Public API

File `src/main/java/com/example/consumer/ConsumerApplication.java`:

~~~java
package com.example.consumer;

import com.example.catalog.CatalogClient;

public class ConsumerApplication {

    public static void main(String[] args) {
        String name = args.length > 0 ? args[0] : "Ada";
        System.out.println(CatalogClient.greeting(name));
    }
}
~~~

File `src/test/java/com/example/consumer/CatalogClientIntegrationTest.java`:

~~~java
package com.example.consumer;

import com.example.catalog.CatalogClient;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class CatalogClientIntegrationTest {

    @Test
    void callsPublishedLibrary() {
        assertEquals(
                "Hello, Ada from catalog-client",
                CatalogClient.greeting("Ada")
        );
    }

    @Test
    void rejectsBlankName() {
        assertThrows(
                IllegalArgumentException.class,
                () -> CatalogClient.greeting(" ")
        );
    }
}
~~~

This is a **consumer-side test**: the public class must resolve from the repository and the method must work as expected. Passing producer tests alone is insufficient because the producer might run against local compiled output/classpath rather than the published artifact.

### 6.3. Running the Consumer

Linux/macOS:

~~~bash
./mvnw clean test
./mvnw dependency:tree -Dincludes=com.example:catalog-client
./mvnw -q compile exec:java \
    -Dexec.mainClass=com.example.consumer.ConsumerApplication \
    -Dexec.args=Ada
~~~

PowerShell:

~~~powershell
.\mvnw.cmd clean test
.\mvnw.cmd dependency:tree "-Dincludes=com.example:catalog-client"
.\mvnw.cmd -q compile exec:java "-Dexec.mainClass=com.example.consumer.ConsumerApplication" "-Dexec.args=Ada"
~~~

Output printed by consumer main:

~~~text
Hello, Ada from catalog-client
~~~

`dependency:tree` shows the version and transitive graph. `exec:java` runs the consumer with the Maven-resolved dependency classpath.

## 7. Gradle Consumer: Using the Same Maven Repository

Gradle also reads Maven-compatible repositories.

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
}

group = 'com.example.consumer'
version = '1.0.0'

repositories {
    maven {
        name = 'companyReleases'
        url = uri('https://repo.example.com/repository/maven-releases/')
        credentials(PasswordCredentials)
    }
    mavenCentral()
}

dependencies {
    implementation 'com.example:catalog-client:1.4.2'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.2'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.test {
    useJUnitPlatform()
}
~~~

`credentials(PasswordCredentials)` reads properties based on repository name `companyReleases`, typically `companyReleasesUsername` and `companyReleasesPassword` in Gradle user properties. Never put tokens in the build script.

File `settings.gradle`:

~~~groovy
rootProject.name = 'catalog-consumer-gradle'
~~~

Reuse the consumer main/test sources from section 6 in Gradle's source layout.

Run:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency catalog-client --configuration runtimeClasspath
./gradlew clean test
~~~

- `dependencies` lists the dependency graph.
- `dependencyInsight` explains the selected version and selection reasons.
- `clean test` compiles/tests the consumer with the artifact from the Maven repository.

If the project has `gradle/verification-metadata.xml`, Gradle verifies artifacts against checksum/signature metadata before use.

## 8. Downloading a Spring Boot Executable JAR from a Repository

A runnable application requires checking the exact **executable artifact**, manifest/Boot layout, and startup behavior.

### 8.1. Publishing an Executable JAR with Classifier exec

Example coordinates:

~~~text
groupId:    com.example.catalog
artifactId: catalog-service
version:    1.0.0
classifier: exec
type:       jar
~~~

Spring Boot Maven Plugin `repackage` builds the executable JAR. To publish both a plain artifact and an executable artifact, configure classifier `exec` so the executable JAR is attached alongside the main artifact.

**Fragment when inheriting `spring-boot-starter-parent`:**

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <id>repackage</id>
            <configuration>
                <classifier>exec</classifier>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Starter Parent already provides execution ID `repackage`; in that case only the classifier needs configuring. If not using the parent and no execution exists yet, declare the `repackage` goal in an appropriate execution.

With classifier `exec`, Spring Boot Maven Plugin keeps the plain JAR as the main artifact and attaches the executable archive as a supplementary artifact:

~~~text
catalog-service-1.0.0.jar
catalog-service-1.0.0-exec.jar
catalog-service-1.0.0.pom
~~~

Consumers use the plain JAR if it truly serves as an API library; operators download classifier `exec` to run the application. If the module is purely an application with no reusable API, do not automatically assume the plain JAR makes a good library.

### 8.2. Downloading a Classifier with Maven Dependency Plugin

`dependency:get` accepts coordinates:

~~~text
groupId:artifactId:version[:packaging[:classifier]]
~~~

Linux/macOS:

~~~bash
./mvnw org.apache.maven.plugins:maven-dependency-plugin:3.7.1:get \
    -Dartifact=com.example.catalog:catalog-service:1.0.0:jar:exec \
    -Dtransitive=false \
    -DremoteRepositories=company-releases::default::https://repo.example.com/repository/maven-releases/
~~~

PowerShell:

~~~powershell
.\mvnw.cmd org.apache.maven.plugins:maven-dependency-plugin:3.7.1:get "-Dartifact=com.example.catalog:catalog-service:1.0.0:jar:exec" "-Dtransitive=false" "-DremoteRepositories=company-releases::default::https://repo.example.com/repository/maven-releases/"
~~~

`company-releases` is the repository ID; credentials come from `settings.xml` with the matching ID. `-Dtransitive=false` fits an executable JAR because the Boot JAR already bundles runtime dependencies. For plain library JARs, consumers must resolve the POM and transitive dependencies.

Maven Dependency Plugin `dependency:get` always considers Maven Central per goal rules; mirrors in settings can redirect repositories. For internal repositories, configure URLs/IDs and mirrors per company standards.

### 8.3. Local Repository Path

The downloaded artifact typically lands at:

~~~text
Linux/macOS:
~/.m2/repository/com/example/catalog/catalog-service/1.0.0/catalog-service-1.0.0-exec.jar

Windows:
%USERPROFILE%\.m2\repository\com\example\catalog\catalog-service\1.0.0\catalog-service-1.0.0-exec.jar
~~~

If Maven uses a custom `localRepository` in settings, check that path. This is a local cache/download, not the original file on the remote repository.

### 8.4. Inspecting the Archive and Running

~~~bash
jar tf ~/.m2/repository/com/example/catalog/catalog-service/1.0.0/catalog-service-1.0.0-exec.jar
~~~

For a Spring Boot executable JAR, expect the corresponding sections:

~~~text
META-INF/MANIFEST.MF
org/springframework/boot/loader/...
BOOT-INF/classes/...
BOOT-INF/lib/...
~~~

Inspect the manifest:

~~~bash
unzip -p ~/.m2/repository/com/example/catalog/catalog-service/1.0.0/catalog-service-1.0.0-exec.jar META-INF/MANIFEST.MF
~~~

Executable manifests typically set `Main-Class` to the Spring Boot launcher and `Start-Class` to the application main class. Do not hardcode the launcher name across all Boot versions; read the actual manifest.

Run:

~~~bash
java -jar ~/.m2/repository/com/example/catalog/catalog-service/1.0.0/catalog-service-1.0.0-exec.jar --server.port=8081
~~~

Another terminal:

~~~bash
curl -fsS http://localhost:8081/health
~~~

If the demo health endpoint returns `catalog-service-ok`, the expected response body is:

~~~text
catalog-service-ok
~~~

This verifies **the artifact downloaded from the repository can actually boot**. If the app requires a database, credentials, or external services, supply valid runtime configuration; never embed secrets into the JAR just to smoke test.

## 9. Gradle Producer: Publishing a Java Library

If the producer uses Gradle, the `maven-publish` plugin creates a Maven-compatible publication. For a pure Java library, use `java-library`:

~~~groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'com.example'
version = '1.4.2'

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
        }
    }
    repositories {
        maven {
            name = 'companyReleases'
            url = uri('https://repo.example.com/repository/maven-releases/')
            credentials(PasswordCredentials)
        }
    }
}
~~~

Gradle user properties reside in `GRADLE_USER_HOME/gradle.properties`, outside the repository. Keys `companyReleasesUsername` and `companyReleasesPassword` receive real values from a secret store; with `credentials(PasswordCredentials)`, Gradle looks them up automatically by repository name. CI can supply the same properties via `ORG_GRADLE_PROJECT_companyReleasesUsername` and `ORG_GRADLE_PROJECT_companyReleasesPassword`. Never commit credential files.

Publish:

~~~bash
./gradlew clean test publish
~~~

`from components.java` publishes the Java component with Maven metadata; `withSourcesJar()`/`withJavadocJar()` produce source/Javadoc artifacts if needed.

**If the producer is a Spring Boot application:** never publish `bootJar` as a library dependency by default. Spring Boot Gradle Plugin can generate an executable archive (`bootJar`) and a plain archive (`jar`, typically classifier `plain`). Explicitly decide which artifact is the library and which is the executable distribution; ideally split the library into a `java-library` module or attach the executable archive with a dedicated classifier. Check publication tasks and repository contents before handing off to consumers.

## 10. Verifying Checksums, Signatures, and Provenance

Downloading a file with the expected name does not prove its bytes match the approved artifact.

### 10.1. SHA-256

Linux/macOS:

~~~bash
sha256sum catalog-client-1.4.2.jar
~~~

PowerShell:

~~~powershell
Get-FileHash .\catalog-client-1.4.2.jar -Algorithm SHA256
~~~

Compare against a **trusted checksum** from CI, a release manifest, or verified provenance. If the repository provides `.sha256`, checksums catch transfer corruption/byte changes; if both the checksum and JAR came from a compromised source, a checksum alone does not prove who published them.

### 10.2. Signatures and Gradle Dependency Verification

If your organization signs artifacts, verify signatures against approved public keys/fingerprints and check attestations/provenance per release policy.

Gradle provides dependency verification via `gradle/verification-metadata.xml`, supporting SHA-256/SHA-512 and PGP signatures:

~~~bash
./gradlew --write-verification-metadata sha256
~~~

This command bootstraps checksum metadata for dependencies Gradle resolves. **Never commit the output blindly**: verify trusted sources, review diffs, and confirm new checksums. Gradle does not verify changing/SNAPSHOT dependencies in the same way as release artifacts in metadata verification.

### 10.3. Maven Checksum Policy

Maven repository declarations can configure `checksumPolicy` for release/snapshot metadata when repositories supply checksums. `fail` stops the build if received checksums mismatch. This checks integrity against repository checksums; verifying the publisher requires signatures/provenance and an appropriate trust policy.

### 10.4. Recording Results

A verification report should record:

- Exact GAV and classifier/type.
- Repository URL/ID and version.
- SHA-256 of the downloaded file.
- Maven/Gradle and Java versions.
- Output of `jar tf`, manifest, or dependency graph.
- Test/consumer build results.
- For executable apps: runtime settings, startup logs, and HTTP smoke results.
- Release commit, CI run, and signature/attestation references if available.

## 11. POM and Transitive Dependencies

When a consumer declares:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>catalog-client</artifactId>
    <version>1.4.2</version>
</dependency>
~~~

Maven reads the POM to determine the dependency graph. Illustrative example:

~~~text
catalog-consumer
└── com.example:catalog-client:1.4.2
    ├── org.slf4j:slf4j-api:...
    └── com.example:catalog-model:...
~~~

If the producer forgot to declare a required dependency in its POM, consumers may fail compilation or fail at runtime with `NoClassDefFoundError`.

Maven:

~~~bash
./mvnw dependency:tree
./mvnw dependency:tree -Dincludes=com.example
./mvnw dependency:resolve
./mvnw help:effective-pom
~~~

Gradle:

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency catalog-client --configuration runtimeClasspath
~~~

`dependency:tree` inspects direct/transitive dependencies; `dependencyInsight` explains the selected version and selection reasons.

**Never manually drop all transitive JARs into `libs/`.** Use POM/Gradle Module Metadata so the build tool manages the dependency graph, versions, and scopes.

## 12. Java and API Compatibility

An artifact can exist with a valid checksum yet remain incompatible with the consumer runtime.

1. **Java bytecode target:** a library compiled for Java 21 will not run on Java 17; the typical error is `UnsupportedClassVersionError`.
2. **Public API:** does the consumer invoke methods/classes that actually exist in the resolved version?
3. **Transitive dependencies:** does the POM describe accurate dependencies/scopes?
4. **Binary compatibility:** changing method signatures or removing classes can trigger `NoSuchMethodError`/`NoClassDefFoundError`.
5. **Runtime assumptions:** does the library expect a Spring context, Servlet container, native libraries, config files, or environment variables?
6. **Dependency conflicts:** consumers may pull different versions of Spring/Jackson/logging; inspect the dependency graph.
7. **Artifact classifier/type:** downloading `sources`, `tests`, `plain`, or `exec` by mistake produces an unexpected layout.

Inspect the public API of a plain library JAR:

~~~bash
javap -classpath catalog-client-1.4.2.jar com.example.catalog.CatalogClient
~~~

`javap` prints the API visible to the compiler; it helps confirm classes/methods exist in the artifact, though it does not replace consumer compilation/testing.

## 13. Release and SNAPSHOT

Release `1.4.2` should represent **an immutable set of bytes**. When fixes are needed, publish `1.4.3`. Never alter `1.4.2` contents in the repository while keeping the same coordinates; some consumers may cache the old build while other CI jobs fetch the new one, breaking reproducibility.

`1.5.0-SNAPSHOT` is a mutable development version. Repositories manage snapshot metadata/timestamped builds; Maven/Gradle cache policies can cause two machines to resolve at different times.

Maven refresh:

~~~bash
./mvnw -U clean test
~~~

Gradle refresh:

~~~bash
./gradlew --refresh-dependencies clean test
~~~

Never use SNAPSHOTs as production release dependencies unless explicitly allowed by policy. For reproducibility, prefer immutable releases or dependency locking/verification/provenance.

## 14. Remote Verification Without Local Cache Contamination

A common testing mistake is running `install`/`publishToMavenLocal` on the producer and having the consumer use `mavenLocal()`. This proves the artifact works from the local Maven cache, **not that the remote repository published properly**.

### Maven: Isolated Local Repository

~~~bash
./mvnw -Dmaven.repo.local=target/remote-verification-repo \
    org.apache.maven.plugins:maven-dependency-plugin:3.7.1:get \
    -Dartifact=com.example:catalog-client:1.4.2 \
    -Dtransitive=false \
    -DremoteRepositories=company-releases::default::https://repo.example.com/repository/maven-releases/
~~~

Then run the consumer project using that same isolated local repository:

~~~bash
./mvnw -Dmaven.repo.local=target/remote-verification-repo clean test
~~~

Maven must download plugins/dependencies into the temporary cache, so the first run may be slower. This proves the consumer resolves from the remote repository without pre-existing local artifacts masking issues.

### Gradle: Do Not Use mavenLocal to Mask Errors

The Gradle consumer declares the repository with its exact URL. When a refresh is needed:

~~~bash
./gradlew --refresh-dependencies clean test
~~~

`--refresh-dependencies` tells Gradle to re-check metadata/artifacts per cache rules without wiping all of `GRADLE_USER_HOME`.

**Never blindly delete all of `~/.m2` or `~/.gradle`** just to verify one dependency. Use a temporary local repository/cache or controlled refresh.

## 15. Repository Security and Dependency Confusion

Repository ordering and repository IDs affect which artifacts get resolved:

- Gradle resolves modules from declared repositories; order, metadata, and content rules matter.
- Maven can use repositories in POMs, settings profiles, and mirrors; mirrors can route requests through internal proxies.
- Internal coordinates such as `com.company:common-utils:1.0.0` must never accidentally resolve from uncontrolled public repositories.
- An internal repository manager should typically proxy/cache public dependencies and host private releases/snapshots under a unified policy.
- Use HTTPS and least-privilege credential permissions.
- Never use `flatDir` or loose JAR files for artifacts requiring transitive dependency metadata.
- Never allow untrusted builds to publish/overwrite release coordinates trusted by production consumers.
- Verify checksums, signatures, and provenance before releasing critical dependencies.

**Prevent repository shadowing/dependency confusion:** the same GAV can exist across multiple sources. If an untrusted source precedes or takes priority unexpectedly, consumers may download different bytes despite identical coordinates. Use repository allowlists/content filters, centralized repository policies, and verification metadata.

## 16. Common Errors and Fixes

| Symptom | Possible cause | Check/fix |
| --- | --- | --- |
| HTTP 401 | Missing/wrong credentials or server ID does not match repository ID | Check Maven settings, Gradle user properties, and IDs |
| HTTP 403 | Account authenticates but lacks read/deploy permission | Request the proper repository permission |
| HTTP 404 | Wrong GAV/version/classifier/repository URL or unpublished | Compare coordinates, paths, and repository contents |
| Could not find artifact | Repository not declared, wrong mirror, version does not exist | Inspect POM repositories, settings mirrors, and logs |
| POM exists without JAR | Publisher deployed without binary or wrong packaging | Check publish task, POM packaging, and remote contents |
| Consumer compile fails due to missing class | Wrong plain library version or artifact lacks public classes | `jar tf`, `javap`, dependency tree, and GAV |
| NoClassDefFoundError | POM missing dependency or wrong scope/optional flag | Inspect POM/dependency tree; publish a new version |
| NoSuchMethodError | Runtime binary/API version conflict | Inspect dependency graph and API compatibility |
| UnsupportedClassVersionError | Artifact targets higher Java version than runtime | Check JDK compiler release and consumer/runtime |
| no main manifest attribute | Downloaded plain JAR/library and ran with java -jar | Use executable classifier or exact application artifact |
| ClassNotFoundException with Boot JAR dependency | Application classes live in BOOT-INF/classes | Use a plain library JAR |
| App runs locally yet fails in CI | Different env/profile/secret/port/database/runtime | Run with identical runtime config and CI smoke tests |
| Stale snapshot | Unrefreshed metadata/artifact cache | Maven -U, Gradle --refresh-dependencies |
| SHA-256 mismatch | File altered, mirror bytes differ, or tampered artifact | Stop build, verify trusted checksum/signature |
| Gradle fails to resolve private repo | Credential property name mismatches repository name | Check companyReleasesUsername/Password |
| Maven deploy 401 | distributionManagement ID differs from server ID | Sync IDs and deploy permissions |
| Consumer picks stale local artifact | mavenLocal or local cache from prior publish | Use temporary local repo and explicit remote repository |
| POM missing transitive dependency | Producer published JAR only or wrong scope | Publish proper POM, inspect dependency tree |
| Classifier fails to download | Publisher did not attach classifier | Check repackage classifier and remote files |
| Correct JAR downloaded yet runtime lacks config | App depends on external env/secrets/services | Supply valid runtime config, never embed secrets |
| Same GAV with different bytes | Repository shadowing or overwritten release | Check repository ordering, immutable releases, and checksums |

### Diagnostic Order

1. Confirm `groupId`, `artifactId`, `version`, `type`, and `classifier`.
2. Verify repository URL/ID, credentials, and release/snapshot policy.
3. Confirm both POM and binary exist on remote.
4. Use Maven `dependency:get` or Gradle resolution to fetch the artifact.
5. Inspect the archive with `jar tf`, manifest, and checksum.
6. If a library, compile/test in an independent consumer.
7. If an executable app, run `java -jar` and HTTP/CLI smoke tests.
8. Check Java version, transitive dependencies, runtime config, and version conflicts.
9. If checksum/signature mismatches, halt usage and investigate the publish source; never bypass verification.

## 17. CI Workflow: Publishing Must Be Followed by Consumer Verification

~~~text
Producer source
      |
      v
Build + producer tests
      |
      v
Publish release artifact + POM + metadata
      |
      v
Resolve from remote repository
      |
      +--> Executable JAR: inspect + java -jar + smoke test
      |
      +--> Library JAR: consumer compile + tests + runtime test
      |
      v
Checksum / signature / provenance checks
      |
      v
Mark release ready for downstream consumers
~~~

Pipeline checklist:

1. Build exact commit, pinned JDK, and pinned toolchain.
2. Run producer tests and quality checks.
3. Publish immutable release version, never overwriting.
4. Create an isolated consumer workspace without sharing `target/classes` or producer sources.
5. Resolve via the exact remote repository, read-only credentials, and published coordinates.
6. Use a fresh local repository/cache or controlled refresh to avoid stale local artifacts.
7. Inspect POM/module metadata and transitive dependency graph.
8. For libraries, compile/test the consumer and invoke the real API.
9. For executable apps, download the exact classifier/artifact, check manifest, start the app, and smoke-test endpoints.
10. Verify SHA-256/signature/provenance per release policy.
11. Archive build logs, test reports, GAV/classifier, repository, checksum, and CI run ID.
12. Mark release-ready only when both publisher and consumer verifications pass.

**A green producer build is not enough.** Consumer verification catches bugs that appear only once the artifact leaves the source workspace: missing POM, wrong classifier, wrong dependency scope, different classpath, version conflicts, or undocumented runtime assumptions.

## 18. Practice Lab and Completion Criteria

1. Create library `catalog-client:1.4.2` with `CatalogClient.greeting()` and a Java 17 POM.
2. Configure `distributionManagement` and credentials in Maven user `settings.xml`.
3. Run `./mvnw clean deploy`; confirm JAR/POM appear in the release repository.
4. Create a new Maven consumer project, declaring `company-releases` and dependency `com.example:catalog-client:1.4.2`.
5. Run `./mvnw clean test`; confirm the consumer compiles/tests without including producer sources.
6. Run `dependency:tree` and `exec:java`; verify output `Hello, Ada from catalog-client`.
7. Create a Gradle consumer project using the same Maven repository and dependency GAV; run `dependencyInsight` and `clean test`.
8. Enable Gradle dependency verification if required by your organization, reviewing checksum/signature metadata before committing.
9. Build a Spring Boot executable app artifact with classifier `exec`, keeping the plain JAR separate.
10. Use Maven `dependency:get` to download classifier `exec` from the remote repository; never grab the file from the producer's `target/`.
11. Use `jar tf` and manifest inspection to confirm the Boot launcher/nested libraries; run `java -jar` and an HTTP smoke test.
12. Test mistaking the plain JAR for the executable JAR, explaining why `java -jar` or consumer classpath fails the intended purpose.
13. Test a non-existent version or wrong classifier; read resolver errors and identify the right coordinates.
14. Verify checksums against a trusted release manifest; never compare solely against an unauthenticated sidecar checksum.
15. Record GAV, classifier, repo URL/ID, Java/Maven/Gradle versions, SHA-256, dependency graph, consumer tests, and smoke results.
16. Restore test sources or maintain a new version per release policy; never overwrite an already published release.

**Completion criteria:** you download the artifact from the remote repository, verify the exact version/bytes, successfully boot the executable Spring Boot archive, and prove the plain Java library compiles/tests/runs from an independent Maven or Gradle project.

## Official References

- [Spring Boot 3.3 – Maven Plugin: Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html)
- [Spring Boot 3.3 – Gradle Plugin: Packaging Executable and Plain Archives](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html)
- [Apache Maven Dependency Plugin 3.7.1 – Usage and dependency:get](https://maven.apache.org/components/plugins-archives/maven-dependency-plugin-3.7.1/usage.html)
- [Apache Maven – Settings Reference](https://maven.apache.org/settings.html)
- [Apache Maven – Security and Deployment Settings](https://maven.apache.org/guides/mini/guide-deployment-security-settings.html)
- [Apache Maven – Deploying over HTTP(S)](https://maven.apache.org/guides/mini/guide-deployment-transports.html)
- [Gradle – Declaring Repositories](https://docs.gradle.org/current/userguide/declaring_repositories.html)
- [Gradle – Managing Dependencies of JVM Projects](https://docs.gradle.org/current/userguide/dependency_management_for_java_projects.html)
- [Gradle – Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html)
- [Gradle – Securing Dependencies with Checksums and Signatures](https://docs.gradle.org/current/userguide/dependency_verification.html)
- [Gradle – Securing Repositories and Credentials](https://docs.gradle.org/current/userguide/securing_repositories.html)