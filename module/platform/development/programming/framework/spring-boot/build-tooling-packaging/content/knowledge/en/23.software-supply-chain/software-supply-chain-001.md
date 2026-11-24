# Controlling Download Sources for Plugins, Dependencies, and Wrapper Distributions

A Spring Boot application may build successfully and still be untrustworthy if **Maven/Gradle, plugins, dependencies, or the Wrapper program itself** are downloaded from uncontrolled sources. Maven plugins and Gradle plugins are executable code within the build process; dependencies enter the application classpath; the Wrapper is the bootstrap program that downloads and runs the build tool before project-level checks even begin.

This lesson belongs to the **Supply Chain** section and focuses on five questions:

- From **which repositories** is the build allowed to download artifacts?
- Are plugin repositories and project dependency repositories **controlled separately**?
- Does the Maven/Gradle Wrapper download the exact **pinned distribution and verify its checksum**?
- Does the dependency graph have **stable versions**, with verified checksums/signatures?
- Does CI run the same reviewed configuration, without using caches/credentials outside the trust boundary?

The examples use **Java 17, Spring Boot 3.3.13, Maven 3.9.9, and Gradle 8.10.2** for illustration. This is a fixed version set used in this lesson, not a recommendation for the latest versions. Hostnames such as `repo.corp.example` are illustrative examples only, not live registries or repositories.

## 1. Map of Code Sources Entering a Build

Dependencies declared in `pom.xml`/`build.gradle` are not the only inputs that can affect the final product. A typical build uses:

```text
Git checkout
    |
    v
Wrapper scripts + Wrapper JAR
    |
    v
Maven / Gradle distribution
    |
    v
Settings / extensions / init scripts
    |
    +------------------------+
    |                        |
    v                        v
Build plugins           Project dependencies
    |                        |
    v                        v
Plugin transitive        Direct + transitive
dependencies             libraries / metadata
    |                        |
    +-----------+------------+
                |
                v
        Compile / test / package
                |
                v
       Spring Boot executable JAR
                |
                v
          Release artifact
```

| Component | Example | Reason for control |
| --- | --- | --- |
| Wrapper script | `mvnw`, `gradlew` | Runs before the build and can download/execute other tools |
| Wrapper binary | `maven-wrapper.jar`, `gradle-wrapper.jar` | Executable code committed directly to the repository |
| Build distribution | Maven ZIP, Gradle ZIP | Provides the build tool program itself |
| Repository settings | `settings.xml`, `settings.gradle` | Selects download sources, credentials, and content routing |
| Build extensions | `.mvn/extensions.xml`, settings plugins | Can alter the build before regular tasks run |
| Build plugins | Spring Boot plugin, compiler/test plugins | Executes code during the build process |
| Plugin dependencies | Libraries required by plugins | Can execute with the same privileges as the build |
| Project dependencies | Spring Web, JUnit | Enters the compile/test/runtime classpath |
| Transitive dependencies | Libraries pulled in by dependencies | Still become part of the product even without direct declaration |
| Metadata | POM, Gradle Module Metadata, Ivy descriptor | Determines the dependency graph and transitive versions |

**The Wrapper is also a supply chain link.** If the Wrapper JAR or script is altered, dependency checks inside Maven/Gradle can be bypassed before they even have a chance to run.

## 2. Three Defense Layers That Must Work Together

| Layer | Question | Mechanism |
| --- | --- | --- |
| Source control | Where are artifacts allowed to be downloaded from? | Repository manager, mirror, allowlist, content filters |
| Version control | Which versions does the build select? | Pin plugin/dependency versions, BOM, dependency lock |
| Artifact verification | Do the downloaded bytes match a trusted artifact? | SHA-256, signatures, provenance, Wrapper checksum |

A repository manager helps route and control artifacts, but it does not automatically prove every proxied file is genuine. Pinning versions fixes coordinates, but it does not stop a repository from replacing the content of the same version. Checksums verify integrity, but an expected checksum fetched from an already-compromised repository may be untrustworthy. Signatures help verify the publisher, but you must still verify that the public key belongs to a trusted maintainer.

Therefore, **repository allowlists + pinned versions + checksum/signature verification + CI trust boundaries** together form a reasonably complete policy.

## 3. Designing an Enterprise Repository Manager

A repository manager such as Nexus/Artifactory or an equivalent service can provide a centralized endpoint:

```text
                 Maven / Gradle builds
                          |
                          v
                Corporate repository manager
                          |
              +-----------+------------+
              |                        |
              v                        v
       Hosted internal             Proxy external
       com.acme:*                  Maven Central
       com.company:*               Gradle Plugin Portal
              |                    approved vendor repos
              +-----------+------------+
                          |
                          v
                 Virtual / group endpoint
                          |
                          v
                Developer and CI runners
```

You should clearly separate:

- **Hosted repository:** only authorized pipelines are allowed to publish internal artifacts.
- **Proxy repository:** caches approved external sources.
- **Virtual/group repository:** aggregates hosted and proxy repositories into an endpoint for developers/CI.
- **Content policy:** restricts allowed groups/modules/plugins; blocks versions, licenses, or artifacts that fail policy.
- **Quarantine/scanning:** scans for malware, CVEs, licenses, and metadata before promoting new artifacts.
- **Immutability:** release coordinates cannot be overwritten; snapshot/dev repositories have separate policies.
- **Audit:** records which identity downloaded/published an artifact, from which source, and at what time.

Illustrative endpoint examples:

- `https://repo.corp.example/repository/maven-all/` for Maven dependencies/plugins.
- `https://repo.corp.example/repository/gradle-plugins/` for Gradle plugin markers and plugin artifacts.
- `https://repo.corp.example/repository/maven-internal/` for internal groups.

These URLs only illustrate how partitioning works; the repository manager must actually proxy/host the required metadata, POMs, Gradle module metadata, and plugin markers.

### 3.1. Preventing Dependency Confusion

Suppose an application uses `com.acme:billing-client:1.0.0`. If the internal artifact does not exist in the internal repository and the build falls back to querying a public repository, someone else could publish the same coordinates to the public repo and trick the build into pulling the wrong package.

Countermeasures:

- Internal namespaces must have clear ownership.
- The `com.acme` group must only resolve from the internal hosted repository.
- Never let a public repository act as a fallback for internal groups.
- Apply routing/allowlists in the repository manager; Gradle can use `exclusiveContent`.
- Fail the release pipeline if an internal artifact is missing instead of searching for the same GAV on the Internet.

**Do not rely on repository ordering as your only defense.** Configure routing/content policies that can be reviewed and audited.

## 4. Maven: Separating Project Repositories and Plugin Repositories

Maven has two repository types in the POM:

- `<repositories>`: where project dependencies are resolved from.
- `<pluginRepositories>`: where Maven plugins are resolved from.

Plugins also have their own dependencies on the plugin classpath. Parent POMs, build extensions, and build-supporting artifacts must also resolve from controlled sources.

Example POM fragment:

```xml
<repositories>
    <repository>
        <id>corp-public</id>
        <url>https://repo.corp.example/repository/maven-public/</url>
        <releases>
            <enabled>true</enabled>
            <checksumPolicy>fail</checksumPolicy>
        </releases>
        <snapshots>
            <enabled>false</enabled>
        </snapshots>
    </repository>
</repositories>

<pluginRepositories>
    <pluginRepository>
        <id>corp-plugins</id>
        <url>https://repo.corp.example/repository/maven-plugins/</url>
        <releases>
            <enabled>true</enabled>
            <checksumPolicy>fail</checksumPolicy>
        </releases>
        <snapshots>
            <enabled>false</enabled>
        </snapshots>
    </pluginRepository>
</pluginRepositories>
```

This is a fragment illustrating structure. `checksumPolicy=fail` causes Maven to fail when repository checksum verification fails. It is **not a publisher signature**; if both the artifact and its checksum are replaced in a compromised repository, that checksum alone is not enough to prove authenticity. For enterprise environments, a repository manager and verification/signature policies are needed as complements.

## 5. Maven Mirror in `settings.xml`

Maven can use global settings or user settings. User settings are typically located at `~/.m2/settings.xml`; this is the right place for mirrors, server credentials, proxies, and environment-specific configuration. Do not commit personal passwords into a POM.

Example `settings.xml`:

```xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0 https://maven.apache.org/xsd/settings-1.2.0.xsd">

    <servers>
        <server>
            <id>corp-maven</id>
            <username>${env.REPO_USER}</username>
            <password>${env.REPO_PASSWORD}</password>
        </server>
    </servers>

    <mirrors>
        <mirror>
            <id>corp-maven</id>
            <name>Corporate Maven virtual repository</name>
            <url>https://repo.corp.example/repository/maven-all/</url>
            <mirrorOf>*</mirrorOf>
        </mirror>
    </mirrors>
</settings>
```

Explanation:

1. `mirrorOf=*` tells Maven to route remote repository requests through the internal endpoint, including both dependency and plugin repositories.
2. The mirror's `id` is `corp-maven`; Maven retrieves credentials from the `<server>` with the **same id**.
3. `REPO_USER` and `REPO_PASSWORD` are injected by the CI secret store. Do not print their values to logs.
4. `maven-all` must be a virtual/group endpoint capable of serving approved artifacts, including both plugins and dependencies.
5. If policy requires separating plugin and dependency endpoints, configure mirrors accordingly; do not assume a repository that only proxies Maven Central will contain all Gradle/Maven plugins.
6. Use HTTPS and a trusted CA chain. Do not embed credentials in URLs.

**A Maven mirror is not automatic repository aggregation.** Maven picks a single matching mirror per request; to combine multiple sources, use a repository manager group/virtual repository. `mirrorOf=*` simply routes through one endpoint; it does not merge multiple mirrors automatically.

### 5.1. Server ID Must Match Mirror ID

If the POM declares repository ID `corp-public` but settings selects mirror ID `corp-maven`, credentials for requests routed through the mirror must match the **ID of the actual mirror**. If the ID is wrong, Maven may reach the URL without sending the right credentials and receive a 401.

CI should create a temporary settings file with restricted read permissions, inject secrets, and pass it via `-s`. Do not commit settings files containing credentials. Password encryption/secret injection does not replace restricting token scopes and hardening runners.

## 6. Maven: Pinning Plugin and Dependency Versions

### 6.1. A BOM Does Not Manage Everything in a Build

The Spring Boot parent/BOM manages dependency versions as a set tested together. It does not automatically pin every Maven plugin version. Plugin versions need to be managed via parent plugin management or explicitly declared in the project.

Example `pluginManagement`:

```xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
```

`pluginManagement` supplies versions/configuration for plugins when the project actually uses them; it does not run the plugins by itself. The Spring Boot parent may manage the version of `spring-boot-maven-plugin`; if you do not use the parent, pin the version explicitly.

Distinguish:

- `dependencyManagement` manages versions/scopes of project dependencies.
- `pluginManagement` manages versions/configuration of build plugins.

Putting a version into a BOM does not automatically pin Maven plugin versions.

### 6.2. Avoiding Versions That Change Over Time

Release builds should avoid:

- Maven version ranges such as `[1.0,2.0)`.
- SNAPSHOT dependencies or parent POMs whose contents change.
- Plugins without explicitly declared versions.
- Build extensions with dynamic versions.
- Repositories that allow overwriting release coordinates.

Prefer exact release versions, pinned parent/plugin versions, snapshots kept in a separate repository, and preventing release jobs from resolving snapshots outside policy.

### 6.3. Inspecting the Resolved Graph

From the project root:

```bash
./mvnw -B -ntp dependency:tree
./mvnw -B -ntp dependency:resolve-plugins
./mvnw -B -ntp help:effective-pom
```

- `dependency:tree` shows the actual transitive dependencies.
- `dependency:resolve-plugins` helps inspect resolved Maven plugins.
- `help:effective-pom` shows the configuration after inheritance, profiles, and plugin management.

Do not run verbose/debug configs on public logs if credentials are present. The dependency tree helps you understand the graph, but it does not verify artifact bytes on its own.

## 7. Maven Wrapper: Controlling the Distribution and Bootstrap Binary

### 7.1. What Does the Wrapper Download?

The Maven Wrapper typically consists of:

- `mvnw`/`mvnw.cmd`: entrypoint scripts for Linux/macOS/Windows.
- `.mvn/wrapper/maven-wrapper.properties`: configures the distribution URL and version.
- `maven-wrapper.jar` if using the binary Wrapper type; or the source/script-only variant.
- Maven distribution ZIP/TAR: the Maven program that is downloaded and executed.

When a developer runs `./mvnw verify`, the Wrapper can download the Maven version specified in the properties file before running the build. Therefore, **a Maven dependency mirror does not automatically control every detail of the Maven distribution download step**.

### 7.2. Using an Internal Distribution Mirror

The `.mvn/wrapper/maven-wrapper.properties` file should point `distributionUrl` to an organization-approved Maven distribution stored in the internal repository manager. For example, the URL can follow a structure like:

```text
https://repo.corp.example/repository/maven-distributions/apache-maven-3.9.9-bin.zip
```

This path is illustrative only; the repository manager must host the exact corresponding distribution file.

Maven Wrapper also supports the `MVNW_REPOURL` variable to route distribution downloads through a repository manager. If the repository requires Basic Authentication, `MVNW_USERNAME` and `MVNW_PASSWORD` can be supplied from the secret store. Do not embed credentials in `distributionUrl` because the properties file is committed to Git.

### 7.3. Verifying Checksums Separately for the Distribution and Wrapper JAR

Maven Wrapper has two properties:

- `distributionSha256Sum`: SHA-256 of the Maven distribution ZIP/TAR.
- `wrapperSha256Sum`: SHA-256 of `maven-wrapper.jar` if the project uses the binary Wrapper.

Obtain the expected SHA-256 from an independently verified Apache release source; if the organization mirrors the file, the mirror's checksum must match the official release bytes. Do not compute a checksum from a file just downloaded through the very source under suspicion and accept it as a trust anchor.

`wrapperSha256Sum` is only relevant when the wrapper type includes `maven-wrapper.jar`. For source/script-only variants, review the actual scripts and source downloader committed to the repository.

### 7.4. Generating/Updating the Maven Wrapper

When an already installed and verified Maven is available:

```bash
mvn wrapper:wrapper -Dmaven=3.9.9 -Dtype=bin
```

After running:

1. Review the diff of `mvnw`, `mvnw.cmd`, `.mvn/wrapper/maven-wrapper.properties`, and `maven-wrapper.jar`.
2. Confirm the distribution URL points to the right internal mirror/Apache distribution.
3. Record the corresponding distribution and wrapper binary checksums.
4. Verify the version using `./mvnw -version`.
5. Commit Wrapper changes with the same review rigor as executable code, not just as a version string change.

## 8. Maven Lab with Spring Boot and Java 17

Let's create a small application to demonstrate a build running through controlled repository settings.

Structure:

```text
supply-chain-demo/
├── pom.xml
└── src/
    ├── main/java/dev/example/supplychain/
    │   ├── SupplyChainApplication.java
    │   └── OriginController.java
    └── test/java/dev/example/supplychain/
        └── OriginControllerTest.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>dev.example</groupId>
    <artifactId>supply-chain-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <version>3.3.13</version>
            </plugin>
        </plugins>
    </build>
</project>
```

The POM does not declare a separate public repository; CI uses a corporate settings file to route requests. Both the parent version and the Boot plugin version are pinned at 3.3.13; starter versions are managed by the parent.

`src/main/java/dev/example/supplychain/SupplyChainApplication.java`:

```java
package dev.example.supplychain;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SupplyChainApplication {

    public static void main(String[] args) {
        SpringApplication.run(SupplyChainApplication.class, args);
    }
}
```

`src/main/java/dev/example/supplychain/OriginController.java`:

```java
package dev.example.supplychain;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OriginController {

    @GetMapping("/origin")
    public String origin() {
        return "dependency-policy-ok";
    }
}
```

`src/test/java/dev/example/supplychain/OriginControllerTest.java`:

```java
package dev.example.supplychain;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OriginControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void endpointReturnsExpectedBody() throws Exception {
        mvc.perform(get("/origin"))
                .andExpect(status().isOk())
                .andExpect(content().string("dependency-policy-ok"));
    }
}
```

Build using the Wrapper and corporate settings:

```bash
./mvnw -B -ntp -s "$CI_MAVEN_SETTINGS" clean verify
```

`CI_MAVEN_SETTINGS` is the path to a settings file generated securely by CI, containing the matching mirror/server IDs. Do not commit files with credentials. A successful build confirms that source compiles/tests/packages per the POM; to verify repository policy enforcement, CI needs to run on a runner without an unverified local cache and retain logs/graph evidence per policy.

## 9. Gradle: Plugin Repositories and Dependency Repositories

Gradle separates two paths:

- `pluginManagement.repositories` in `settings.gradle`: where plugins declared via `plugins { ... }` are resolved from.
- `dependencyResolutionManagement.repositories`: where libraries for the project/subprojects are resolved from.

Putting `mavenCentral()` in `repositories` inside `build.gradle` does **not** automatically add a lookup location for the plugins DSL. Adding Gradle Plugin Portal to `pluginManagement` likewise does not make it a project dependency repository.

### 9.1. Centralizing Repository Declarations

Example `settings.gradle`:

```groovy
pluginManagement {
    repositories {
        maven {
            name = 'corpPlugins'
            url = uri('https://repo.corp.example/repository/gradle-plugins/')
            credentials(PasswordCredentials)
        }
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)

    repositories {
        exclusiveContent {
            forRepository {
                maven {
                    name = 'corpInternal'
                    url = uri('https://repo.corp.example/repository/maven-internal/')
                    credentials(PasswordCredentials)
                }
            }
            filter {
                includeGroupAndSubgroups('com.acme')
            }
        }

        maven {
            name = 'corpPublic'
            url = uri('https://repo.corp.example/repository/maven-public/')
            credentials(PasswordCredentials)
        }
    }
}

rootProject.name = 'supply-chain-demo'
```

Explanation:

1. `corpPlugins` serves plugin markers and plugin artifacts. The repository manager must proxy the approved plugin sources.
2. `corpInternal` only accepts group `com.acme` and its subgroups. `exclusiveContent` guarantees that this group is only queried from the internal repository.
3. `corpPublic` is a proxy/virtual repository for approved external dependencies.
4. `FAIL_ON_PROJECT_REPOS` fails the build if a subproject declares its own repository outside settings.
5. If policy only permits corporate repositories, do not add direct public fallbacks such as `gradlePluginPortal()`/`mavenCentral()`; the repository manager must proxy approved sources.

### 9.2. Providing Gradle Credentials via Properties

`credentials(PasswordCredentials)` reads properties based on the repository name:

| Repository | Username property | Password property |
| --- | --- | --- |
| `corpPlugins` | `corpPluginsUsername` | `corpPluginsPassword` |
| `corpInternal` | `corpInternalUsername` | `corpInternalPassword` |
| `corpPublic` | `corpPublicUsername` | `corpPublicPassword` |

In CI, inject them via environment properties with the `ORG_GRADLE_PROJECT_` prefix. Example variable names:

```text
ORG_GRADLE_PROJECT_corpPluginsUsername
ORG_GRADLE_PROJECT_corpPluginsPassword
ORG_GRADLE_PROJECT_corpInternalUsername
ORG_GRADLE_PROJECT_corpInternalPassword
ORG_GRADLE_PROJECT_corpPublicUsername
ORG_GRADLE_PROJECT_corpPublicPassword
```

These are **variable names** for the CI secret store to populate. On local machines, properties can be placed in `~/.gradle/gradle.properties` with restricted read permissions; do not commit credentials.

### 9.3. Disallowing Fallback for Internal Groups

If `com.acme:billing-client:1.0.0` is missing from the internal repository, Gradle must fail rather than look up the same coordinates in a public repo. This is the goal of `exclusiveContent`. When publishing internal Gradle plugins, also check the plugin marker coordinates; the plugin marker group does not necessarily match the implementation module group.

## 10. Gradle: Pinning Plugins, BOM, and Project Dependencies

`build.gradle` (Groovy DSL):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

group = 'dev.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}

dependencyLocking {
    lockAllConfigurations()
}
```

- The Spring Boot plugin version is pinned in the `plugins` block and resolved via `pluginManagement`.
- The Boot BOM manages starter/transitive dependency versions.
- `dependencyLocking` records resolved versions for locked configurations.
- Repository declarations live in `settings.gradle` so policies can be reviewed centrally.
- The Gradle Wrapper version is pinned separately in `gradle-wrapper.properties`.

### 10.1. Generating Dependency Lock State

With the sample project:

```bash
./gradlew build --write-locks
```

Gradle creates/updates `gradle.lockfile` recording the resolved module versions. Commit the lock file and review every change when upgrading dependencies.

**Locking does not check bytes.** It fixes coordinates/versions; if a repository changes the content of the same version, dependency verification is needed to detect it. Locking also does not solve changing dependencies such as `-SNAPSHOT`; releases should use stable versions.

## 11. Gradle Dependency Verification

Gradle can verify dependency/plugin artifacts and metadata using the file:

`gradle/verification-metadata.xml`

When this file exists, Gradle applies dependency verification to artifacts resolved by the dependency management engine, including JARs/ZIPs, POM/module metadata, and plugin artifacts.

Bootstrap the metadata in a trusted environment:

```bash
./gradlew --write-verification-metadata sha256,pgp build
```

After generating the file:

1. Review the diff of `gradle/verification-metadata.xml`.
2. Verify checksums against official release sources whenever possible.
3. Verify PGP key fingerprints belong to trusted maintainers; do not automatically trust every downloaded key.
4. Inspect entries auto-generated by Gradle and document their origin/trust rationale.
5. Commit the metadata and run CI in strict verification mode.

### 11.1. Checksums Differ from Signatures

| Mechanism | Proves | Limitation |
| --- | --- | --- |
| SHA-256 | Downloaded bytes match a trusted fingerprint | Does not prove who published it |
| PGP signature | Artifact was signed by the corresponding key | Must verify the key belongs to the maintainer |
| Lockfile | Which version was resolved | Does not verify bytes |
| Vulnerability scan | Whether known CVEs exist | Does not prove source/authenticity |

If both the checksum and the artifact come from a compromised repository, they can be replaced together. Obtain checksums from independent sources or verify signatures when available.

### 11.2. Bootstrapping Has Risks

`--write-verification-metadata` creates metadata from the current artifacts downloaded by the build. If a repository already returns a malicious artifact, bootstrapping can record that artifact's checksum. Therefore bootstrapping is only an initialization step; independent review and verification are required before committing.

Gradle can verify PGP signatures when artifacts publish `.asc` files. Not every artifact has a signature; a trusted checksum serves as a fallback. If a signature exists but the key is not yet trusted, the build should fail so a reviewer can verify the fingerprint rather than accepting it automatically.

**Do not add `trusted-artifacts` for an entire group just to turn CI green.** Such configuration can skip verification for matching artifacts.

## 12. Gradle Wrapper: Pinning the Distribution and Checking the Wrapper JAR

### 12.1. Pinning the Distribution URL and SHA-256

File `gradle/wrapper/gradle-wrapper.properties`:

```properties
distributionUrl=https://repo.corp.example/gradle-distributions/gradle-8.10.2-bin.zip
distributionSha256Sum=31c55713e40233a8303827ceb42ca48a47267a0ad4bab9177123121e71524c26
```

The checksum above is the official SHA-256 of `gradle-8.10.2-bin.zip`. If you choose `-all.zip`, a different version, or another file, the checksum must be updated to match that exact artifact. When an internal mirror stores the exact bytes, the checksum must still match the official source.

Gradle Wrapper compares the distribution bytes against `distributionSha256Sum` and fails on mismatch. Gradle documentation notes that the distribution checksum is only verified when the distribution has not already been downloaded/cached; CI needs to manage caches/Gradle User Home within the trust boundary.

### 12.2. Checking the Wrapper JAR Separately

`gradle-wrapper.jar` resides at `gradle/wrapper/gradle-wrapper.jar` and is committed to source control. It runs before build scripts and before dependency verification. `distributionSha256Sum` does **not** verify the Wrapper JAR.

For Gradle 8.10.2, the Wrapper JAR checksum published by Gradle is:

```text
2db75c40782f5e8ba1fc278a5574bab070adccb2d21ca5a6e5ed840888448046
```

On Linux/macOS:

```bash
printf '%s  %s\n' '2db75c40782f5e8ba1fc278a5574bab070adccb2d21ca5a6e5ed840888448046' 'gradle/wrapper/gradle-wrapper.jar' | sha256sum --check -
```

Output when matching:

```text
gradle/wrapper/gradle-wrapper.jar: OK
```

You can use an organization-approved Gradle Wrapper Validation action/Gradle Setup Action in GitHub Actions to verify the Wrapper JAR. Review every JAR change as an executable code change, not merely a version bump.

### 12.3. Authentication for Private Gradle Distributions

If an internal distribution server requires Basic Auth/Bearer tokens, place credentials in Gradle User Home or CI secret properties rather than embedding them in the committed `distributionUrl`. Gradle supports hostname-scoped system properties, for example:

```properties
systemProp.gradle.repo_corp_example_wrapperUser=build-reader
systemProp.gradle.repo_corp_example_wrapperPassword=secret-from-ci
```

This is an example of **external property structure outside the repository**; CI must inject actual values through a secret store. Gradle also supports `wrapperToken` if the server uses Bearer authentication. Scope credentials by hostname to avoid sending them to another server if the URL changes.

## 13. Maven Wrapper vs. Gradle Wrapper Comparison

| Aspect | Maven Wrapper | Gradle Wrapper |
| --- | --- | --- |
| Distribution URL | `distributionUrl` in `.mvn/wrapper/maven-wrapper.properties` | `distributionUrl` in `gradle-wrapper.properties` |
| Distribution checksum | `distributionSha256Sum` | `distributionSha256Sum` |
| Wrapper binary checksum | `wrapperSha256Sum` when `maven-wrapper.jar` is present | Verify `gradle-wrapper.jar` separately |
| Internal mirror | `MVNW_REPOURL` or URL in properties | `distributionUrl` pointing to internal mirror |
| Auth | `MVNW_USERNAME`/`MVNW_PASSWORD` | Host-scoped Wrapper system properties |
| Bootstrap code | Wrapper scripts and optional wrapper JAR/source | `gradlew`/`gradlew.bat` and `gradle-wrapper.jar` |

Both Wrappers must be committed, version-pinned, and verified. They do not replace repository policies for plugins/dependencies once the build tool has started.

## 14. CI: Using the Reviewed Wrapper and Repository Policy

### 14.1. Maven CI

```bash
./mvnw -version
./mvnw -B -ntp -s "$CI_MAVEN_SETTINGS" clean verify
```

`CI_MAVEN_SETTINGS` is a settings file securely created by CI with matching mirror/server IDs. Credentials come from the secret store and the file is never committed. CI must fail on Wrapper checksum mismatch, repository auth failure, or artifacts not resolving from approved endpoints.

### 14.2. Gradle CI

```bash
./gradlew --version
./gradlew --no-daemon --dependency-verification strict clean build
```

`--dependency-verification strict` causes verification failures to fail the build. Do not use `lenient`/`off` in release gates to hide checksum/signature mismatches. When upgrading dependencies, update the lockfile/verification metadata in a separate reviewed PR.

### 14.3. Caches and Runners

- Caches must only be shared within appropriate trust boundaries; untrusted PRs must not write to caches used by release jobs.
- Do not treat `mvn -o` or Gradle `--offline` as proof of a trusted download source; offline mode only blocks network access.
- Do not run releases using unmanaged global settings/init scripts.
- Do not expose production secrets to build scripts running from untrusted forks.
- Separate build/test jobs from privileged publish/deploy jobs.
- Retain logs of Wrapper versions, repository sources, dependency graphs, lock/verification changes, and artifact provenance per policy.

## 15. Build Extensions and External Configuration

Several components can alter a build before regular tasks/tests run.

**Maven:**

- `.mvn/extensions.xml` declares core extensions that can execute inside Maven core.
- `.mvn/maven.config` and `.mvn/jvm.config` modify command/JVM options.
- Global/user `settings.xml` can add profiles, mirrors, servers, and proxies.
- Wrapper scripts/JAR execute before Maven starts.

**Gradle:**

- `settings.gradle` can apply settings plugins and alter plugin resolution.
- `buildSrc`, included builds, and convention plugins are executable build logic.
- `~/.gradle/init.d` can contain init scripts affecting every build on the machine/runner.
- `GRADLE_USER_HOME/gradle.properties` and global init scripts can impact credentials/repositories.

Release CI should use managed runner images, inspect global settings/init scripts, and restrict the file/secret read permissions of the build process. Reviewing `pom.xml` or `build.gradle` alone is not enough to understand all code sources executed by a build.

## 16. Common Issues and How to Handle Them

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Maven downloads dependencies from Central despite an internal repo | Mirror does not match or `mirrorOf=*` is missing | Check effective settings and mirror selection |
| Maven plugins download fine, but dependencies fail | `pluginRepositories` and `repositories` are two separate paths | Check both or configure a centralized mirror |
| Maven returns 401 after configuring a mirror | `<server><id>` does not match the mirror ID | Use the exact ID of the selected mirror |
| Maven checksum policy only warns | Repository policy is not set to fail or the checksum source is untrusted | Set the appropriate policy and verify checksums/signatures independently |
| Maven Wrapper downloads from the Internet | `distributionUrl`/`MVNW_REPOURL` does not point to the mirror | Configure a separate Wrapper distribution source |
| Maven Wrapper checksum mismatch | URL points to a different file or the artifact was altered | Fail the build and verify against the official release source; do not blindly update the checksum |
| Gradle plugin fails to resolve | Missing plugin marker/plugin repository | Configure `pluginManagement` and proxy the plugin portal |
| Gradle subproject adds Maven Central on its own | Repository mode is not locked down | Use `FAIL_ON_PROJECT_REPOS` |
| Internal group resolves from public repo | Missing exclusive routing | Use `exclusiveContent` and repository manager routing |
| Gradle reports missing checksum | Verification metadata is missing the artifact/POM/transitive plugin | Review and update the metadata |
| Gradle checksum mismatch | Bytes differ from expected | Stop the build; inspect cache/repository and official source |
| Untrusted PGP key | Fingerprint has not been verified | Verify the key with the maintainer and update trust metadata with review |
| Gradle distribution checksum passes but Wrapper JAR changed | The two files are verified separately | Verify `gradle-wrapper.jar` via checksum/validation action |
| Gradle Wrapper checksum check does not run on a warm cache | Distribution is already cached | Use a trusted cache/isolated GRADLE_USER_HOME and verify the Wrapper JAR |
| Lockfile unchanged but bytes changed | Lockfile pins version, not content | Enable dependency verification |
| BOM pinned but plugin version drifts | BOM does not manage all plugin versions | Pin in `pluginManagement`/plugin declaration |
| Laptop build passes but clean CI fails | Local cache/global settings masked missing configuration | Use the Wrapper, uniform settings, and clean runners |
| `--offline` passes | Artifacts already exist in local cache | Verify provenance/cache; offline is not proof of trust |
| New plugin requests unusual permissions/secrets | Plugins execute inside the build process | Review source, runner permissions, and secret scopes |

### Investigation Procedure When Artifact Tampering Is Suspected

1. Record the group/module/version, plugin ID, repository URL/ID, and resolution timestamp.
2. Preserve logs and checksum mismatch output; do not wipe the cache before collecting evidence.
3. Compute the SHA-256 of the cached file and compare it against the repository and official release source.
4. Check whether POM/module metadata and the dependency graph changed.
5. Check the Wrapper distribution/JAR if the change occurred before the build started.
6. Verify the PGP key fingerprint from an independent source.
7. Notify the repository manager/security owner and quarantine the artifact if tampering is indicated.
8. Only update lock/verification metadata after confirming the expected artifact.

## 17. Self-Check Questions

**Scenario A.** A Maven POM has `<repositories>`, yet plugins fail to download from the internal repository. Why?

*Answer:* Plugin resolution uses `<pluginRepositories>`; configure both or use a mirror in `settings.xml` covering all repository requests.

**Scenario B.** A Maven mirror has the right URL but returns 401. What is the first thing to check?

*Answer:* Whether `<server><id>` matches the selected `<mirror><id>`, and whether CI injected the credentials.

**Scenario C.** The Spring Boot BOM manages starter versions. Can you skip pinning all Maven plugin versions?

*Answer:* No. The BOM manages dependencies; plugin versions require `pluginManagement`/parent plugin management or explicit versions.

**Scenario D.** Gradle has `mavenCentral()` in `pluginManagement`, yet `implementation` fails to resolve Spring Web. Why?

*Answer:* Plugin repositories and project dependency repositories are independent. You must declare dependency repositories in `dependencyResolutionManagement`.

**Scenario E.** The Gradle lockfile has not changed, but checksum verification fails. Can you disable verification because versions are already locked?

*Answer:* No. Lockfiles pin versions; verification metadata checks bytes. Both are needed.

**Scenario F.** The Gradle distribution checksum passes, but the Wrapper JAR was modified. Is it safe?

*Answer:* No. `distributionSha256Sum` checks the distribution ZIP; `gradle-wrapper.jar` must be verified separately.

**Scenario G.** Gradle bootstraps verification metadata from a public repo and the build passes. Can all checksums be trusted?

*Answer:* No. Bootstrapping records the current bytes; review and verify them independently before committing.

**Scenario H.** Maven `checksumPolicy` is set to `fail`. Does that prove artifact authenticity?

*Answer:* Not completely. It checks checksums provided by the repository; if both the artifact and checksum were replaced, you need signatures/provenance or independent checksums.

**Scenario I.** `MVNW_REPOURL` points to an internal repo, yet dependencies still download from public sources. Why?

*Answer:* `MVNW_REPOURL` controls the Maven Wrapper distribution, not all dependency/plugin repositories once Maven starts. You need Maven settings mirrors.

**Scenario J.** Gradle enables `FAIL_ON_PROJECT_REPOS`, yet a plugin still resolves from another source. Why?

*Answer:* The repository mode applies to project dependency repositories; plugin repositories are still configured separately in `pluginManagement`. Also check settings/init scripts.

## 18. Acceptance Checklist

**Wrapper and build tool:**

- Wrapper scripts/binaries have been reviewed and checksum/signature-verified.
- Maven/Gradle distribution version is pinned in Wrapper properties.
- `distributionSha256Sum` matches the exact approved distribution file.
- Maven Wrapper JAR has `wrapperSha256Sum` when using the binary type.
- Gradle Wrapper JAR is verified separately, not confused with the distribution checksum.
- Wrapper distribution downloads over an internal mirror/HTTPS per policy.
- Wrapper credentials reside outside source control and have read-only permissions.

**Repositories and plugins:**

- Maven `repositories`/`pluginRepositories` are routed through approved mirrors.
- Maven settings server/mirror IDs match; secrets are injected securely.
- Gradle `pluginManagement` and `dependencyResolutionManagement` are configured separately.
- Gradle `FAIL_ON_PROJECT_REPOS` and content filters block repositories outside the allowlist.
- Internal groups resolve only from the hosted repository, with no public fallback.
- Plugin versions and transitive plugin dependencies are pinned and reviewed.
- Build extensions, settings plugins, init scripts, and global configs are controlled.

**Dependencies and verification:**

- Spring Boot BOM/parent and dependency versions are pinned.
- Releases do not use dynamic/latest/range/SNAPSHOT versions.
- Gradle lockfile is committed and updated under review.
- Gradle verification metadata contains verified checksums/signatures.
- Maven checksum policy is configured properly, with signatures/provenance added where required.
- CVE/license/malware scans are separate gates, not confused with checksums.
- CI builds run on runners/caches with clear trust boundaries.

**CI and release:**

- CI executes the Wrapper rather than an arbitrary Maven/Gradle installation on PATH.
- CI uses securely injected settings/Gradle properties.
- Untrusted PRs have neither publisher secrets nor write access to release caches.
- Verification failures fail the job; `lenient`/`off` is never used to mask mismatches.
- Repository sources, dependency graphs, Wrapper/tool versions, lock/verification metadata diffs, and artifact provenance are retained per policy.
- Release artifacts come from the exact verified build, not rebuilt with different sources/toolchains at deploy time.

**Conclusion:** The Spring Boot build supply chain must be protected from the **Wrapper distribution and Wrapper binary** through **plugin repositories**, **project dependency repositories**, **version/lock state**, and **downloaded bytes**. Maven uses `settings.xml` mirrors, `repositories`/`pluginRepositories`, BOM/`pluginManagement`, and Wrapper checksum properties; Gradle uses `pluginManagement`, `dependencyResolutionManagement`, content filters, dependency locking, and `verification-metadata.xml`. Combining a repository manager, version pinning, checksum/signature verification, and trusted CI runners enables teams to confirm that builds used **the right tools, the right sources, and the right approved artifacts**.

### Official Documentation

- Apache Maven — Using Mirrors for Repositories: https://maven.apache.org/guides/mini/guide-mirror-settings.html
- Apache Maven — Settings Reference: https://maven.apache.org/settings.html
- Apache Maven — POM Reference: https://maven.apache.org/pom.html
- Apache Maven — Maven Wrapper: https://maven.apache.org/tools/wrapper/
- Apache Software Foundation — Verifying Releases: https://apache.org/info/verification.html
- Gradle — Securing Repositories: https://docs.gradle.org/current/userguide/securing_repositories.html
- Gradle — Declaring Repositories: https://docs.gradle.org/current/userguide/declaring_repositories.html
- Gradle — Dependency Locking: https://docs.gradle.org/current/userguide/dependency_locking.html
- Gradle — Dependency Verification: https://docs.gradle.org/current/userguide/dependency_verification.html
- Gradle — Gradle Wrapper: https://docs.gradle.org/current/userguide/gradle_wrapper.html
- Gradle — Securing the Build Tool: https://docs.gradle.org/current/userguide/securing_build_tool.html
- Gradle — Official Distribution and Wrapper Checksums: https://gradle.org/release-checksums/
- Spring Boot 3.3 — Gradle Plugin: https://docs.spring.io/spring-boot/3.3/gradle-plugin/