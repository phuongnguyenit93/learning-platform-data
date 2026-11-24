# Publishing Artifacts with Gradle maven-publish and MavenPublication

## Objective

A Java library might build successfully on a developer's machine, yet other modules still cannot use it until the artifact is **identified, packaged, and pushed to a repository**. Gradle provides the `maven-publish` plugin alongside the `MavenPublication` type to describe artifacts, Maven coordinates, POM metadata, and target repositories.

The publishing workflow answers three questions:

1. **What to publish?** A Java component, an executable Spring Boot JAR, a sources JAR, or a custom artifact.
2. **Where to publish?** Maven Local, a file-based repository for testing, or a remote repository such as Nexus/Artifactory/GitHub Packages.
3. **Which task to run?** Gradle generates tasks from the publication and repository names.

After this lesson, you will be able to:

- Distinguish `maven-publish`, `publishing`, `MavenPublication`, and a Maven repository.
- Create a publication from `components.java` to publish a Java library with dependency metadata.
- Customize `groupId`, `artifactId`, `version`, and POM metadata.
- Attach a task-produced artifact using `artifact(tasks.named(...))`.
- Publish a Spring Boot executable JAR via `bootJar`.
- Understand `generatePomFileFor...`, `publish...To...Repository`, and `publishToMavenLocal` tasks.
- Inspect repository layout, POM, Gradle Module Metadata, and test resolving the artifact from a consumer project.
- Configure remote credentials, snapshots/releases, and CI without hardcoding secrets.
- Diagnose wrong GAVs, missing dependencies, wrong classifiers, publishing the wrong JAR, or repository upload rejections.

**Practice context:** Java 17+, compatible Gradle 8.x, Groovy DSL and Kotlin DSL. Library examples use `java-library`; application examples use Spring Boot plugin **3.3.13**. Remote URLs below are sample addresses only, not live upload endpoints.

---

## 1. Maven Repositories and GAV Coordinates

### 1.1 GAV Identifies a Module

A Maven artifact is typically identified by:

- `groupId`: group/organization, e.g. `com.example.libs`.
- `artifactId`: module name, e.g. `greeting-library`.
- `version`: version, e.g. `1.2.0` or `1.3.0-SNAPSHOT`.

These three components are called **GAV**:

```text
com.example.libs:greeting-library:1.2.0
```

A Maven repository uses GAV to organize directories and filenames:

```text
repository-root/
└── com/
    └── example/
        └── libs/
            └── greeting-library/
                └── 1.2.0/
                    ├── greeting-library-1.2.0.jar
                    ├── greeting-library-1.2.0.pom
                    ├── greeting-library-1.2.0.module
                    └── greeting-library-1.2.0-sources.jar
```

This is an illustrative structure. Gradle may also publish `.module`, checksums, and signatures depending on configuration. Maven primarily uses the POM; Gradle can use Gradle Module Metadata to understand richer variants.

### 1.2 Download Repositories vs Upload Repositories

In Gradle:

```groovy
repositories {
    mavenCentral()
}
```

declares where the project **downloads dependencies to build**.

Whereas:

```groovy
publishing {
    repositories {
        maven {
            name = 'internal'
            url = uri('https://repo.example.com/repository/releases/')
        }
    }
}
```

declares where Gradle **uploads publications**. The two blocks serve different roles. Declaring Maven Central in `repositories` does not publish artifacts; declaring a repository in `publishing.repositories` does not make it a dependency source for the project either.

### 1.3 Repository Types

| Type | Location | Purpose |
| --- | --- | --- |
| Maven Local | `~/.m2/repository` or `%USERPROFILE%\.m2\repository` | Testing on the current machine |
| File repository | E.g. `build/repo` | Testing publish/resolve without a server |
| Remote repository | Nexus, Artifactory, GitHub Packages, internal repository | Sharing with the team and CI |

`mavenLocal()` inside the `repositories` block lets a consumer resolve from Maven Local. It is not an upload configuration. Gradle provides a dedicated `publishToMavenLocal` task and does not need Maven Local added to `publishing.repositories`.

Maven Central has its own public release process covering namespaces, authentication, signing, and portal submission. Do not treat an arbitrary Maven URL as a valid Central endpoint.

---

## 2. Maven Publish Plugin and MavenPublication

### 2.1 Applying the Plugin

`build.gradle`:

```groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}
```

`maven-publish` is a core Gradle plugin and needs no separate version. The plugin registers the `publishing` extension with two configuration groups:

- `publications`: named publications describing artifacts and metadata.
- `repositories`: target repositories with a name and URL.

`MavenPublication` is the object describing how a module is published in Maven format. It is neither the POM file itself nor a repository.

### 2.2 Publications Sourcing Artifacts from a Component or Task

Java libraries typically use:

```groovy
publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
        }
    }
}
```

A Spring Boot executable archive can use:

```groovy
publishing {
    publications {
        bootApp(MavenPublication) {
            artifact tasks.named('bootJar')
        }
    }
}
```

`from components.java` publishes the Java software component along with dependency/variant metadata. `artifact(tasks.named('bootJar'))` adds the exact archive produced by the `bootJar` task. Choose based on how consumers use the artifact.

### 2.3 Publication Name Differs from artifactId

In:

```groovy
publications {
    mavenJava(MavenPublication) {
        from components.java
    }
}
```

`mavenJava` is the Gradle publication name, used in task names and POM output paths. It does not have to match the Maven `artifactId`.

By default, Gradle maps:

| Maven field | Gradle project property |
| --- | --- |
| `groupId` | `project.group` |
| `artifactId` | `project.name` |
| `version` | `project.version` |

You can override them:

```groovy
publishing {
    publications {
        mavenJava(MavenPublication) {
            groupId = 'com.example.platform'
            artifactId = 'shared-utils'
            version = '2.4.0'
            from components.java
        }
    }
}
```

If `rootProject.name` is `greeting-library`, `group` is `com.example.libs`, and `version` is `1.2.0`, the default GAV is `com.example.libs:greeting-library:1.2.0`. Always inspect the generated POM before uploading.

---

## 3. Complete Hands-On Java Library

### 3.1 Structure

```text
greeting-library/
├── settings.gradle
├── build.gradle
├── gradlew / gradlew.bat
├── gradle/wrapper/...
└── src/
    ├── main/java/com/example/greeting/GreetingService.java
    └── test/java/com/example/greeting/GreetingServiceTest.java
```

The project requires a valid Gradle Wrapper and JDK 17 or corresponding toolchain provisioning.

### 3.2 `settings.gradle`

```groovy
rootProject.name = 'greeting-library'
```

The project name is the default source for Maven `artifactId`.

### 3.3 Java Library Class

File `src/main/java/com/example/greeting/GreetingService.java`:

```java
package com.example.greeting;

import org.apache.commons.lang3.StringUtils;

public final class GreetingService {

    public String greet(String name) {
        String normalized = StringUtils.trimToNull(name);

        if (normalized == null) {
            throw new IllegalArgumentException("name must not be blank");
        }

        return "Hello, " + normalized + "!";
    }
}
```

`StringUtils` is used internally only; the public API accepts and returns `String`. Because consumers do not need Commons Lang types to compile calls, `implementation` is the right dependency configuration.

### 3.4 Unit Test

File `src/test/java/com/example/greeting/GreetingServiceTest.java`:

```java
package com.example.greeting;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GreetingServiceTest {

    private final GreetingService service = new GreetingService();

    @Test
    void greetsTrimmedName() {
        assertEquals("Hello, Linh!", service.greet("  Linh  "));
    }

    @Test
    void rejectsBlankName() {
        assertThrows(
                IllegalArgumentException.class,
                () -> service.greet("   ")
        );
    }
}
```

Tests verify normal behavior and invalid input. JUnit is a test dependency, not a production dependency of the library.

### 3.5 Complete `build.gradle`

```groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'com.example.libs'
version = '1.2.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
    withSourcesJar()
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.14.0'

    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.10.2'
}

tasks.named('test') {
    useJUnitPlatform()
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java

            pom {
                name = 'Greeting Library'
                description = 'A small reusable Java greeting library.'
                url = 'https://example.com/projects/greeting-library'

                licenses {
                    license {
                        name = 'The Apache License, Version 2.0'
                        url = 'https://www.apache.org/licenses/LICENSE-2.0.txt'
                        distribution = 'repo'
                    }
                }

                developers {
                    developer {
                        id = 'platform-team'
                        name = 'Platform Team'
                    }
                }

                scm {
                    connection = 'scm:git:https://example.com/team/greeting-library.git'
                    developerConnection = 'scm:git:ssh://git@example.com/team/greeting-library.git'
                    url = 'https://example.com/team/greeting-library'
                }
            }
        }
    }

    repositories {
        maven {
            name = 'localTestRepo'
            url = layout.buildDirectory.dir('repo')
        }
    }
}
```

This is a complete build script for the lab project. POM URLs are sample metadata only; replace them with real project details when releasing. Repository `build/repo` is a file-based local repository, not a production remote repository.

### 3.6 Why Use `java-library`?

`java-library` provides a Java component with API boundaries:

- `api`: dependencies exposed in the public API and required on the consumer's compile classpath.
- `implementation`: internal implementation dependencies; consumers do not need them to compile against the public API.
- `compileOnly`: needed when compiling the producer but not published as a normal runtime dependency.
- `testImplementation`: for tests only, never added as a production dependency.

In this example, `commons-lang3` is `implementation`, so the POM typically maps it to Maven runtime scope. If a public method exposes a Commons Lang type that consumers need at compile time, consider `api`.

`from components.java` allows Gradle to pull artifacts and dependency/variant metadata from the Java component. Uploading a standalone JAR file will not automatically generate an equivalent dependency contract.

### 3.7 Sources JAR

`withSourcesJar()` registers a task to build a sources JAR and adds a source variant to the Java component. When the publication uses `from components.java`, the source artifact is published according to the component's metadata.

The filename typically has classifier `sources`:

```text
greeting-library-1.2.0-sources.jar
```

IDEs can use this file to display source code while debugging. It does not replace the binary JAR and is not a runtime dependency.

---

## 4. Building, Generating the POM, and Publishing to a File Repository

### 4.1 Run Verification First

```bash
./gradlew clean check
```

Windows PowerShell:

```powershell
.\gradlew.bat clean check
```

`check` runs the verification lifecycle, which includes tests. Publishing tasks do not substitute for verification by default; run tests/checks before releasing.

### 4.2 Generate the POM for Inspection

```bash
./gradlew generatePomFileForMavenJavaPublication
```

The default POM is generated at:

```text
build/publications/mavenJava/pom-default.xml
```

Verify GAV, name/description/license/SCM, dependency scopes, and ensure JUnit does not appear as a production dependency. Having a generated POM does not mean the artifact has been uploaded.

### 4.3 Publish to the File Repository

```bash
./gradlew publishMavenJavaPublicationToLocalTestRepoRepository
```

The task name is derived from publication `mavenJava` and repository `localTestRepo`. After publishing succeeds, the repository is expected to contain:

```text
build/repo/
└── com/example/libs/greeting-library/1.2.0/
    ├── greeting-library-1.2.0.jar
    ├── greeting-library-1.2.0.pom
    ├── greeting-library-1.2.0.module
    └── greeting-library-1.2.0-sources.jar
```

Additional checksums or metadata may appear depending on Gradle/repository settings. Inspect actual files rather than treating the illustrative list as fixed.

### 4.4 Aggregate Tasks

`./gradlew publish` is an aggregate task for all publications to the remote/file Maven repositories declared in `publishing.repositories`. If multiple publications and repositories exist, the task may upload multiple combinations.

`publish` **does not include `publishToMavenLocal`**. To publish to Maven Local, use the dedicated task.

### 4.5 Inspecting Tasks

```bash
./gradlew tasks --all
./gradlew tasks --group publishing
```

Common tasks:

| Task | Purpose |
| --- | --- |
| `generatePomFileForMavenJavaPublication` | Generates the POM for publication `mavenJava` |
| `publishMavenJavaPublicationToLocalTestRepoRepository` | Uploads to `localTestRepo` |
| `publishMavenJavaPublicationToMavenLocal` | Publishes one publication to Maven Local |
| `publish` | Publishes to all declared target repositories |
| `publishToMavenLocal` | Publishes all publications to Maven Local |

Task names depend on publication/repository names. Renaming `mavenJava` to `releaseLibrary` changes the task names accordingly.

---

## 5. Maven Local and Consumer Project

### 5.1 Publish to Maven Local

```bash
./gradlew publishToMavenLocal
```

Maven Local usually resides at `~/.m2/repository` on Linux/macOS or `%USERPROFILE%\.m2\repository` on Windows.

This is a personal repository/cache convenient for testing on a single machine. It is not a shared server for teams or CI. Stale artifacts left in Maven Local can cause consumers to mistakenly resolve a previously published version.

### 5.2 Gradle Consumer

Create project `greeting-consumer` with `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenLocal()
    mavenCentral()
}

dependencies {
    implementation 'com.example.libs:greeting-library:1.2.0'
}

application {
    mainClass = 'com.example.consumer.ConsumerApplication'
}
```

File `src/main/java/com/example/consumer/ConsumerApplication.java`:

```java
package com.example.consumer;

import com.example.greeting.GreetingService;

public class ConsumerApplication {

    public static void main(String[] args) {
        GreetingService service = new GreetingService();
        System.out.println(service.greet("Linh"));
    }
}
```

Run `./gradlew run`. Exact stdout from the sample code:

```text
Hello, Linh!
```

The consumer compiles and calls the library by GAV. The runtime dependency `commons-lang3` must also be resolved from publication metadata.

### 5.3 Consumer Using the File Repository

Replace Maven Local with:

```groovy
repositories {
    maven {
        url = uri('../greeting-library/build/repo')
    }
    mavenCentral()
}
```

The URL must point to the **repository root**, not directly into the version directory. Gradle locates the artifact using Maven layout automatically.

### 5.4 Maven Consumer

If published to Maven Local, a Maven consumer declares:

```xml
<dependency>
    <groupId>com.example.libs</groupId>
    <artifactId>greeting-library</artifactId>
    <version>1.2.0</version>
</dependency>
```

Maven resolves from the local repository before checking remote repositories per configuration. If the artifact lives in a separate file/remote repository, the consumer must declare the appropriate repository in its POM or Maven settings.

### 5.5 Why Is a Consumer Test Needed?

Merely seeing a JAR file in a repository does not prove the module works. Consumer tests catch wrong GAVs/repositories, missing runtime dependencies, missing classes, wrong POM scopes, having a sources JAR with a broken binary, or resolving an old version by mistake.

For important releases, use a clean consumer project rather than relying solely on the producer's IDE cache.

---

## 6. POM and Dependency Metadata

### 6.1 The POM Is the Maven Contract

A publication POM typically contains GAV, packaging, dependencies/scopes, name, description, URL, license, developers, and SCM.

Excerpt:

```xml
<groupId>com.example.libs</groupId>
<artifactId>greeting-library</artifactId>
<version>1.2.0</version>
<packaging>jar</packaging>
<name>Greeting Library</name>
<description>A small reusable Java greeting library.</description>
```

The actual POM also contains `modelVersion`, XML namespace, and Gradle-generated dependency metadata.

### 6.2 `api` and `implementation`

Example:

```groovy
dependencies {
    api 'org.example:public-contract:1.0.0'
    implementation 'org.example:internal-helper:2.0.0'
    compileOnly 'org.example:provided-at-compile:1.0.0'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.2'
}
```

`api` is a dependency in the public contract, needed on the consumer compile classpath. `implementation` is an internal dependency, typically mapped to Maven runtime scope. `compileOnly` is needed only during producer compilation; `testImplementation` is for tests only.

Gradle can also publish `.module` so Gradle consumers understand API/runtime variants. Avoid arbitrarily patching scopes with `pom.withXml` when the Java component already describes dependencies accurately.

### 6.3 `versionMapping`

When resolved dependency versions need to be written into the POM:

```groovy
publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java

            versionMapping {
                usage('java-api') {
                    fromResolutionOf('runtimeClasspath')
                }
                usage('java-runtime') {
                    fromResolutionResult()
                }
            }
        }
    }
}
```

This is an advanced configuration. Select the resolution configuration according to the dependency model. Dynamic/changing dependencies can cause metadata to vary with resolution outcomes; enable only when your versioning policy requires it.

### 6.4 Avoid Direct XML Patching

Gradle provides `pom.withXml` to manipulate XML directly, but prefer the typed DSL such as `pom.name`, `pom.description`, `pom.licenses`, `pom.developers`, and `pom.scm`. Use XML patching only for specialized metadata lacking a corresponding DSL API.

---

## 7. Custom Artifacts and Sources JAR

### 7.1 Creating a Sources JAR Manually

If not using `withSourcesJar()`:

```groovy
tasks.register('customSourcesJar', Jar) {
    archiveClassifier = 'sources'
    from sourceSets.main.allJava
}
```

Add to the publication:

```groovy
publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
            artifact tasks.named('customSourcesJar')
        }
    }
}
```

Do not declare both `withSourcesJar()` and a custom sources JAR with the same classifier unintentionally; the publication may suffer duplicate extension/classifier conflicts.

### 7.2 Using TaskProvider

`artifact(tasks.named('customSourcesJar'))` links the publication to the task producing the artifact, allowing Gradle to infer necessary task dependencies. Passing a bare file path tells Gradle which file to publish, but the generating task may not be wired automatically without `builtBy` or a task dependency.

Maven artifacts are distinguished by extension and classifier. Avoid publishing two main JARs with an empty classifier in the same publication.

---

## 8. Publishing a Spring Boot Executable JAR with bootJar

The Spring Boot Gradle plugin builds an executable JAR via the `bootJar` task. Spring Boot documentation notes that this task's output can be added to a `MavenPublication` using `artifact`.

### 8.1 Complete Configuration

`settings.gradle`:

```groovy
rootProject.name = 'orders-service'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
    id 'maven-publish'
}

group = 'com.example.apps'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}

publishing {
    publications {
        bootApp(MavenPublication) {
            groupId = project.group.toString()
            artifactId = 'orders-service'
            version = project.version.toString()

            artifact tasks.named('bootJar')

            pom {
                name = 'Orders Service'
                description = 'Executable Spring Boot application for order processing.'
                url = 'https://example.com/apps/orders-service'
            }
        }
    }

    repositories {
        maven {
            name = 'localBootRepo'
            url = layout.buildDirectory.dir('boot-repo')
        }
    }
}
```

### 8.2 Build and Publish

```bash
./gradlew clean check
./gradlew publishBootAppPublicationToLocalBootRepoRepository
```

Expected artifacts:

```text
build/boot-repo/com/example/apps/orders-service/1.0.0/
├── orders-service-1.0.0.jar
└── orders-service-1.0.0.pom
```

The POM is generated at `build/publications/bootApp/pom-default.xml`. Inspect the actual GAV and archive.

### 8.3 Why Not Use `from components.java` Like a Library?

`bootJar` is an executable archive containing the Boot loader and nested runtime dependencies, typically under `BOOT-INF/lib`. The sample publication puts only the **executable artifact** into the Maven repository for recipients to download and run.

When a publication has only `artifact tasks.named('bootJar')` without `from components.java`, the POM does not automatically inherit the dependency graph from the Java component. This can be appropriate since the executable JAR already embeds its runtime dependencies inside. Recipients download the artifact to run it rather than treating it as a Java library.

If the goal is for other projects to compile against a public Java API, publish a separate Java library component using `from components.java`. Never treat an executable application JAR as a library contract merely because both end in `.jar`.

### 8.4 Publishing Both a Library and an Executable JAR

If both are needed, define separate publications or use distinct classifiers/artifactIds:

| Publication | Contents | Consumer |
| --- | --- | --- |
| `library` | Java component and dependency metadata | Other projects compiling/linking against the code |
| `bootApp` | Executable `bootJar` output | Release pipeline or operator downloading and running |

Both artifacts need clear identities and POMs matching their consumers. If attaching the Boot JAR as a secondary artifact of a library publication, use a dedicated classifier; a Maven POM cannot express every Gradle variant completely.

---

## 9. Kotlin DSL Equivalent

If the project uses `build.gradle.kts`:

```kotlin
plugins {
    `java-library`
    `maven-publish`
}

group = "com.example.libs"
version = "1.2.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
    withSourcesJar()
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.apache.commons:commons-lang3:3.14.0")
    testImplementation("org.junit.jupiter:junit-jupiter:5.10.2")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher:1.10.2")
}

tasks.test {
    useJUnitPlatform()
}

publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            from(components["java"])

            pom {
                name.set("Greeting Library")
                description.set("A small reusable Java greeting library.")
                url.set("https://example.com/projects/greeting-library")
            }
        }
    }

    repositories {
        maven {
            name = "localTestRepo"
            url = uri(layout.buildDirectory.dir("repo"))
        }
    }
}
```

Syntax comparison:

| Groovy DSL | Kotlin DSL |
| --- | --- |
| `id 'maven-publish'` | `maven-publish` |
| `mavenJava(MavenPublication)` | `create<MavenPublication>("mavenJava")` |
| `from components.java` | `from(components["java"])` |
| `artifact tasks.named('bootJar')` | `artifact(tasks.named("bootJar"))` |
| `url = layout.buildDirectory.dir('repo')` | `url = uri(layout.buildDirectory.dir("repo"))` |
| `name = 'Greeting Library'` | `name.set("Greeting Library")` |

Do not mix Groovy closures into `.gradle.kts`. Check that `maven-publish` is applied if the IDE fails to resolve `MavenPublication`.

---

## 10. Remote Repositories and Credentials

### 10.1 Declaring the Target Repository

```groovy
publishing {
    repositories {
        maven {
            name = 'internal'
            url = uri('https://repo.example.com/repository/releases/')
        }
    }
}
```

The name `internal` is the Gradle repository name, not a GAV field. It affects task names, e.g. `publishMavenJavaPublicationToInternalRepository`.

The URL must be the **upload endpoint** provided by the repository manager. Download URLs and upload URLs may differ.

### 10.2 Credentials from Environment

Never hardcode usernames/passwords in `build.gradle` or commit `gradle.properties` containing secrets. They can be sourced from the CI secret store:

```groovy
publishing {
    repositories {
        maven {
            name = 'internal'
            url = uri(providers.environmentVariable('MAVEN_REPO_URL').get())

            credentials {
                username = providers.environmentVariable('MAVEN_REPO_USER').orNull
                password = providers.environmentVariable('MAVEN_REPO_PASSWORD').orNull
            }
        }
    }
}
```

CI needs all three corresponding variables configured. Do not echo values, do not enable debug logs that expose credentials, and grant upload permissions only to release jobs that need them. If `MAVEN_REPO_URL` is missing, Gradle fails while evaluating the URL rather than uploading to an unintended destination.

### 10.3 Basic Authentication

If the repository explicitly requires Basic Authentication:

```groovy
import org.gradle.authentication.http.BasicAuthentication

publishing {
    repositories {
        maven {
            name = 'internal'
            url = uri('https://repo.example.com/repository/releases/')
            credentials {
                username = providers.environmentVariable('MAVEN_REPO_USER').orNull
                password = providers.environmentVariable('MAVEN_REPO_PASSWORD').orNull
            }
            authentication {
                basic(BasicAuthentication)
            }
        }
    }
}
```

Enable only authentication schemes that the server actually supports. Use HTTPS to protect credentials in transit.

### 10.4 Snapshot and Release

- `1.2.0-SNAPSHOT` is for integration development and can be updated.
- `1.2.0` is a release version and should typically be immutable once published.

The URL can be selected by version:

```groovy
def isSnapshot = version.toString().endsWith('-SNAPSHOT')

publishing {
    repositories {
        maven {
            name = 'internal'
            url = uri(
                isSnapshot
                    ? 'https://repo.example.com/repository/snapshots/'
                    : 'https://repo.example.com/repository/releases/'
            )
        }
    }
}
```

This example selects **one single destination** per build. If both snapshot and release repositories are configured simultaneously and `publish` is invoked, Gradle may publish to both. Understand the task graph and select the exact destination.

The repository server may forbid redeploying the same release GAV. When publishing new code, increment the version instead of overwriting an already published `1.2.0`. Snapshot metadata timestamps/build numbers are managed by the repository manager.

### 10.5 Remote Publish Is a Real Upload

`./gradlew publish` can upload artifacts to every declared target repository. In this lab, use a file repository or Maven Local. Run remote publishing only when authorized, using the right endpoint, version, and an approved release pipeline.

---

## 11. Task Graph and Task Names

With publication `mavenJava` and repository `internal`, Gradle typically generates:

- `generatePomFileForMavenJavaPublication`
- `publishMavenJavaPublicationToInternalRepository`
- `publishMavenJavaPublicationToMavenLocal`
- `publish`
- `publishToMavenLocal`

Exact task names depend on the publication/repository names.

`generatePomFileFor...` creates the POM for inspection before uploading. The default path is typically:

```text
build/publications/<publicationName>/pom-default.xml
```

`publish...To...Repository` uploads a single publication to a specific repository. Example:

```bash
./gradlew publishMavenJavaPublicationToInternalRepository
```

`publish` is the aggregate task for remote/file repositories in `publishing.repositories`; `publishToMavenLocal` is the aggregate for Maven Local. `mavenLocal()` in dependency resolution does not trigger publishing.

You can use `--dry-run` to preview the task graph:

```bash
./gradlew publish --dry-run
```

`--dry-run` does not prove credentials, permissions, endpoints, or upload success.

---

## 12. Gradle Module Metadata and Maven POM

Gradle supports Gradle Module Metadata to describe variants and dependency graphs richer than a Maven POM. When publishing a Java component, Gradle typically publishes Gradle metadata alongside the Maven POM.

- Maven consumers primarily use `.pom`.
- Gradle consumers can use `.module` to consume variant-aware metadata.
- The JAR is the primary binary artifact.
- Sources/Javadoc JARs are secondary artifacts with classifiers/variants.
- Checksums/signatures are added per configuration.

A POM cannot represent every Gradle variant. When publishing to Maven format, some information must be mapped or compatibility warnings may arise. Do not habitually suppress warnings; understand which dependency/variant cannot be represented accurately.

An artifact added directly via `artifact(...)` can be published with a classifier/extension, but does not automatically create a variant with its own dependency contract. For feature variants, see Gradle's custom component/variant publishing documentation.

---

## 13. Multi-Project Builds

Example:

```text
platform/
├── settings.gradle
├── build.gradle
├── greeting-library/
│   └── build.gradle
└── orders-service/
    └── build.gradle
```

`settings.gradle`:

```groovy
rootProject.name = 'platform'
include 'greeting-library', 'orders-service'
```

If `greeting-library` is a Java library, that module applies `java-library` and `maven-publish` and publishes `components.java`. Module `orders-service` can depend on the library project:

```groovy
dependencies {
    implementation project(':greeting-library')
}
```

Publish the library module using its task path:

```bash
./gradlew :greeting-library:publishMavenJavaPublicationToInternalRepository
```

Do not run `publish` at root without knowing which publications/repositories each subproject includes. Each module may have its own GAV and repository policy. Two subprojects must never publish different binaries to the same GAV.

Gradle project dependencies build the internal graph, whereas publishing to a remote repository is a separate distribution step. CI must decide whether to publish dependency modules first or publish a controlled release set.

---

## 14. Common Errors and Diagnostics

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| `No publications configured` | `publishing.publications` not declared | Apply `maven-publish` and create a `MavenPublication` |
| `MavenPublication` not recognized | Plugin not applied or wrong DSL | Check `plugins`, Groovy/Kotlin syntax |
| Publish task does not exist | Wrong publication/repository name | Run `tasks --all` and check actual task names |
| POM has no dependencies | Only added `artifact(file/task)`, no `from components.java` | For libraries, publish the component; for executable apps, an artifact-only POM may be intentional |
| Consumer fails to resolve | Wrong GAV/repository URL/version | Inspect POM, repository layout, and consumer repositories |
| JAR published but missing classes | Wrong task/output selected | Inspect JAR with `jar tf` |
| Spring Boot JAR missing main manifest | Published plain `jar` instead of `bootJar` | Use `artifact tasks.named('bootJar')` |
| Sources JAR missing | `withSourcesJar()` not enabled | Configure the Java component |
| POM contains test dependencies | Test configuration included in publication | Keep test dependencies in `testImplementation` |
| HTTP 401 | Wrong credentials or authentication scheme | Check credential source/auth, never log secrets |
| HTTP 403 | Account lacks permission or policy rejected upload | Check permissions and snapshot/release endpoint |
| HTTP 404 | Wrong upload URL | Use the endpoint provided by the repository manager |
| TLS/proxy errors | Wrong CA, proxy, or network config | Check HTTPS/CA/proxy settings |
| Release version already exists | Repository forbids redeploying releases | Bump version, do not overwrite |
| Snapshot does not update | Stale snapshot metadata/cache or wrong repo resolved | Check metadata and repository order |
| Consumer sees old artifact | Maven Local or Gradle cache holds old version | Check repo identity/version, perform controlled refresh |
| `publish` uploads to multiple places | Multiple remote repositories in publishing | Use a specific task or select URL by version |
| `publish` does not run tests | Publish tasks do not replace verification lifecycle | Run `check`/`build` before publish |
| Duplicate classifier | Two artifacts share the same extension/classifier | Set distinct classifiers or remove duplicate artifact |
| Maven Central publish fails | Missing Portal/signing workflow | Follow current Central publishing process |
| Using old `uploadArchives` | Legacy Gradle examples | Use `maven-publish` |
| Maven Local works while remote fails | Local requires no network/credentials | Test staging repository and upload permissions |
| Boot JAR used as a library | Executable archive is not a public API component | Separate library and application modules |

Investigation workflow:

1. Identify the goal: library binary, executable app, sources, or distribution.
2. Check plugins and publication names.
3. Verify GAV in the generated POM.
4. Check artifacts, extensions, and classifiers.
5. Check dependency scopes and metadata.
6. Verify the repository URL and exact publish task.
7. Check credentials/permissions without printing secrets.
8. After upload, inspect the repository and test with a clean consumer project.
9. Record version/hash to identify the published artifact.

---

## 15. CI/CD and Release Policy

### 15.1 Recommended Pipeline

```text
Checkout source
      |
      v
Resolve Gradle Wrapper / JDK
      |
      v
./gradlew clean check
      |
      v
Generate POM + validate GAV/artifacts
      |
      v
Publish to staging repository
      |
      v
Consumer integration test
      |
      v
Approve release
      |
      v
Publish immutable release version
      |
      v
Record repository URL, GAV and checksums
```

Separate **verification** from **publishing**. Never allow a job to upload a release simply because the Gradle build script evaluated without errors.

### 15.2 Protecting Credentials

Never hardcode credentials in build scripts. Use CI secret variables or a credential store. Avoid logging command lines containing tokens, never upload debug logs containing credentials, and rotate tokens if there is any sign of exposure.

### 15.3 Snapshot and Release Policy

- Snapshots are for integration development and may be updated.
- Release versions should be immutable; every released change requires a new version.
- Do not use snapshots as production dependencies if the system requires immutable artifacts.
- Check the snapshot repository's retention/cleanup policy.
- Ensure release pipelines do not accidentally publish to snapshot endpoints and vice versa.

### 15.4 Post-Upload Verification

After publishing, verify GAV, JAR/Sources JAR, POM dependency scopes, Gradle Module Metadata, consumer resolution, and that versions were not unintentionally replaced.

For critical releases, record checksums/signatures per policy. **An HTTP 200 from an upload does not automatically prove consumers get the right artifact**; verify download/resolution from the consumer side.

### 15.5 Maven Publishing Is Not Application Deployment

`maven-publish` pushes binaries/metadata to a Maven repository for other tools to resolve. It does not deploy a Spring Boot service to a server, Kubernetes, or a Docker registry. Application deployment is a separate workflow.

---

## 16. Comprehensive Practice

### A. Publish a Java Library

1. Create project `greeting-library` per section 3.
2. Run `./gradlew clean check`.
3. Run `generatePomFileForMavenJavaPublication` and read the POM.
4. Run `publishMavenJavaPublicationToLocalTestRepoRepository`.
5. Inspect the GAV path and JAR/Sources JAR.
6. Create `greeting-consumer`, resolve from the file repo, and run `GreetingService`.
7. Record stdout and explain why the consumer receives `commons-lang3` even though it is `implementation`.

### B. Publish to Maven Local

1. Run `./gradlew publishToMavenLocal`.
2. Verify the artifact under `~/.m2/repository`.
3. Create a consumer declaring `mavenLocal()` and GAV.
4. Change the version on a lab branch to distinguish stale cached artifacts from new ones.
5. Explain why Maven Local is not a shared team repository.

### C. Publish a Spring Boot Executable JAR

1. Create project `orders-service` with the Spring Boot Gradle plugin.
2. Configure the publication using `artifact tasks.named('bootJar')`.
3. Run `clean check` and publish to the file repository.
4. Verify the archive has `BOOT-INF/classes` and `BOOT-INF/lib`.
5. Download the exact artifact and run `java -jar` in the lab environment.
6. Explain why an app-only publication differs from a Java library publication using `components.java`.

### D. Verify Dependency Metadata

1. Add a public dependency to `api` and an internal dependency to `implementation`.
2. Generate the POM and inspect Maven scopes.
3. Compile a consumer using a type from the public dependency.
4. Switch the dependency from `api` to `implementation` on a lab branch, observe compilation behavior, and fix it back.
5. Explain why POM/Gradle Module Metadata are part of the contract.

### E. Safely Simulate a Remote Repository

1. Use an assigned staging URL or a file repository.
2. Supply credentials via CI secret variables.
3. Run the specific task `publishMavenJavaPublicationTo...Repository`.
4. Verify the repository received the right GAV.
5. Run the consumer test against the staging repository.
6. Never use an already existing release version to test overwriting.

### F. Diagnose Wrong Artifact Selection

A colleague wrote:

```groovy
publishing {
    publications {
        bootApp(MavenPublication) {
            from components.java
        }
    }
}
```

yet the goal is to publish a **Spring Boot executable JAR**. Inspect the artifact represented by `components.java` and compare it with the `bootJar` task. Fix the publication:

```groovy
publishing {
    publications {
        bootApp(MavenPublication) {
            artifact tasks.named('bootJar')
        }
    }
}
```

Explain the impact of removing `from components.java` on POM dependencies, and why that can be appropriate for an executable JAR that already bundles runtime dependencies.

### G. Real Results Report

```text
Project:
Gradle Wrapper version:
Java toolchain:
Applied plugins:
Publication name:
Publication type:
GAV:
Primary artifact task/file:
Additional artifacts/classifiers:
Generated POM path:
POM dependency scopes:
Repository name/type:
Publish task:
Publish result:
Published repository path:
Consumer tool:
Consumer dependency coordinates:
Consumer compile/run result:
Observed stdout or error:
Checksum/hash (if required):
Release/Snapshot policy:
Remaining issue:
```

This is a template for real evidence. Do not write "publish succeeded" if you only generated a POM or ran `--dry-run`. If you only published locally, state Maven Local/file repository explicitly and do not claim remote upload.

---

## 17. Official References

- Gradle — Maven Publish Plugin: https://docs.gradle.org/current/userguide/publishing_maven.html
- Gradle — Publishing Setup: https://docs.gradle.org/current/userguide/publishing_setup.html
- Gradle API — MavenPublication, GAV mapping, `from`, `artifact`, and POM: https://docs.gradle.org/current/javadoc/org/gradle/api/publish/maven/MavenPublication.html
- Gradle — Publishing Customization: https://docs.gradle.org/current/userguide/publishing_customization.html
- Gradle — Gradle Module Metadata: https://docs.gradle.org/current/userguide/publishing_gradle_module_metadata.html
- Spring Boot 3.3 — Publishing your Application with Maven-publish Plugin and `bootJar`: https://docs.spring.io/spring-boot/3.3/gradle-plugin/publishing.html
- Spring Boot 3.3 — Packaging Executable Archives: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Apache Maven — POM Reference and `distributionManagement`: https://maven.apache.org/pom.html
- Apache Maven Deploy Plugin: https://maven.apache.org/plugins/maven-deploy-plugin/usage.html
- Apache Maven — Deployment over HTTP(S), repository IDs, and `settings.xml`: https://maven.apache.org/guides/mini/guide-deployment-transports.html

**Key takeaway:** `maven-publish` provides the publication infrastructure; `MavenPublication` describes artifacts, GAV, and POM metadata; `from components.java` publishes a Java component with dependency metadata; `artifact(tasks.named('bootJar'))` publishes the designated executable Spring Boot archive. `publishToMavenLocal` writes to Maven Local, whereas `publish` uploads to declared target repositories. Always inspect **POM, artifacts/classifiers, repository layout, and a real consumer** before releasing a version.