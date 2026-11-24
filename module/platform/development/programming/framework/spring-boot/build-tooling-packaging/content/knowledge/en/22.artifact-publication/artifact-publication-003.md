# Publishing Artifacts with Maven install, deploy, and distributionManagement

## 1. Objective

Successfully building a JAR file is only part of the release process. Other modules, other developers, and CI need to download the right artifact by Maven coordinates. Maven has two key steps:

- **`install`**: installs the artifact into the current machine's **local repository**, defaulting to `~/.m2/repository`, for use by other projects on the same machine.
- **`deploy`**: publishes the artifact to a **remote Maven repository** such as Nexus Repository or Artifactory so other machines/pipelines can download it.

`<distributionManagement>` in the POM specifies the publish destination. Credentials are stored separately in `settings.xml`, under a `<server>` whose `<id>` matches the repository ID in the POM.

After this lesson, you should be able to distinguish the `package`/`verify`/`install`/`deploy` lifecycle phases, understand GAV/classifiers, configure release and snapshot repositories, set up credentials securely, build/install/deploy, and verify that consumers can download the artifact. The lesson also explains Maven multi-module builds, attached artifacts, Spring Boot `repackage`, and common publish errors.

**Example versions:** Apache Maven 3.9.x, Spring Boot 3.5.16, and Java 17. The URL `repo.example.com` is an illustrative domain only; replace it with the repository manager provided by your organization. Do not use real credentials in POMs or public examples.

## 2. Maven Lifecycle: Where Do install and deploy Fit?

The default lifecycle manages compile, test, package, install, and deploy. Each invoked phase executes all phases preceding it.

```text
validate
   |
compile
   |
test
   |
package       -> creates JAR/WAR
   |
integration-test (if configured)
   |
verify        -> checks package/test results
   |
install       -> installs into local repository
   |
deploy        -> uploads to remote repository
```

| Phase | Outcome |
|---|---|
| `package` | Packages code according to `<packaging>` |
| `verify` | Runs checks bound to the lifecycle, potentially including integration-test checks |
| `install` | Writes the artifact and POM to the local Maven repository |
| `deploy` | Publishes the artifact, POM, and attached artifacts to the remote repository |

Because the lifecycle runs sequentially, **`mvn deploy` already includes install and all preceding phases**. Normally, there is no need to run `mvn install` separately before `mvn deploy` for the same build.

```bash
./mvnw clean verify
./mvnw clean install
./mvnw clean deploy
```

- `clean verify`: clean build and quality checks, without publishing.
- `clean install`: clean build and local install.
- `clean deploy`: clean build and remote upload.

`install` and `deploy` are lifecycle phases; the default goals `install:install` and `deploy:deploy` perform the actual work. Usually, invoke the phase rather than calling the plugin goal directly.

## 3. Artifact Coordinates: Which File Does Maven Identify?

Artifact coordinates:

```text
groupId : artifactId : version : classifier : extension
```

Example:

```text
com.example.platform : order-service : 1.4.0 : (none) : jar
```

- `groupId`: group/organization, usually a reversed domain name.
- `artifactId`: module/artifact name.
- `version`: release version; may be a release or `SNAPSHOT`.
- `classifier`: additional label such as `sources`, `javadoc`, or `exec`.
- `extension`: format such as `jar`, `war`, or `pom`.

Standard dependency:

```xml
<dependency>
    <groupId>com.example.platform</groupId>
    <artifactId>order-service</artifactId>
    <version>1.4.0</version>
</dependency>
```

Maven does not identify dependencies by filename alone; GAV/classifier/extension define the coordinates.

### 3.1. Local Repository Layout

For `com.example.platform:order-service:1.4.0`, the default local repository has the structure:

```text
~/.m2/repository/
└── com/example/platform/order-service/1.4.0/
    ├── order-service-1.4.0.jar
    └── order-service-1.4.0.pom
```

On Windows, the default is typically `%USERPROFILE%\.m2\repository`. It can be changed via `<localRepository>` in user settings or `-Dmaven.repo.local=...`.

Locally installed artifacts **do not automatically appear** on colleagues' machines. The local repository belongs to the current user/build machine environment.

### 3.2. Maven Also Publishes the POM

During install/deploy, Maven typically publishes the main JAR/WAR/POM, attached artifacts (sources, javadoc, other classifiers), and metadata/checksums/signatures per configuration. The POM describes dependencies/transitive dependencies. Uploading only a JAR without a POM can prevent consumers from resolving the expected dependency graph.

## 4. repositories, distributionManagement, and settings.xml

| Element | Purpose |
|---|---|
| `<repositories>` | Where Maven looks for dependencies to download |
| `<pluginRepositories>` | Where Maven looks for plugin artifacts |
| `<distributionManagement>` | Where the project's artifacts are uploaded when running deploy |
| `<servers>` in settings | Credentials keyed by repository/server ID |
| `<mirrors>` in settings | Redirects repository requests through a mirror/repository manager |

**`distributionManagement` is not a dependency download source.** A project can publish to a dedicated release repository while consumers download from a repository group URL via `<repositories>` or a mirror.

The POM is published and readable by any consumer; therefore, **never put usernames/passwords/tokens inside `pom.xml`**.

## 5. Configuring distributionManagement for Release and Snapshot

Add to the POM:

```xml
<distributionManagement>
    <repository>
        <id>company-releases</id>
        <name>Company Maven Releases</name>
        <url>https://repo.example.com/repository/maven-releases/</url>
    </repository>
    <snapshotRepository>
        <id>company-snapshots</id>
        <name>Company Maven Snapshots</name>
        <url>https://repo.example.com/repository/maven-snapshots/</url>
    </snapshotRepository>
</distributionManagement>
```

- `<repository>`: publish destination for release versions like `1.4.0`.
- `<snapshotRepository>`: publish destination for versions ending in `-SNAPSHOT` like `1.5.0-SNAPSHOT`.
- `<id>`: repository identifier so Maven can look up server credentials in settings.
- `<url>`: upload endpoint provided by the repository manager.

Maven chooses the destination based on the current version. If `snapshotRepository` is omitted, POM rules fall back to `repository`; environments with separate policies should declare both. Example URLs are not real repositories.

### 5.1. Release and Snapshot

| POM version | Type | Destination |
|---|---|---|
| `1.0.0-SNAPSHOT` | Snapshot | `snapshotRepository` |
| `1.0.1-SNAPSHOT` | Snapshot | `snapshotRepository` |
| `1.0.0` | Release | `repository` |
| `1.0.0-rc1` | Per organizational release convention; Maven does not treat it as a snapshot | Usually `repository` |

Maven recognizes snapshots by the `-SNAPSHOT` suffix. A snapshot repository can update the same coordinates and manage timestamps/build numbers via metadata. A release repository typically blocks overwriting the same version to guarantee immutability. Do not treat a release version as a mutable tag; if a fix is needed, release a new version.

## 6. Credentials in settings.xml: Server ID Must Match

Default user settings location:

```text
${user.home}/.m2/settings.xml
```

Example:

```xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0
              https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <servers>
        <server>
            <id>company-releases</id>
            <username>${env.MAVEN_REPO_USER}</username>
            <password>${env.MAVEN_REPO_TOKEN}</password>
        </server>
        <server>
            <id>company-snapshots</id>
            <username>${env.MAVEN_REPO_USER}</username>
            <password>${env.MAVEN_REPO_TOKEN}</password>
        </server>
    </servers>
</settings>
```

Maven settings support environment variable interpolation; the example uses `MAVEN_REPO_USER` and `MAVEN_REPO_TOKEN` in the CI environment. If releases and snapshots use different credentials, use separate variables.

**IDs must match exactly:**

```text
POM repository.id       = company-releases
settings server.id      = company-releases
```

The same applies to `company-snapshots`. Maven looks up credentials by **ID** rather than inferring them from the URL. An ID mismatch typically results in `401 Unauthorized` or a similar authentication error.

### 6.1. Security Rules

- Do not put real tokens in the POM, source control, Dockerfile, or command line.
- Provide user settings to CI via secret injection; do not print settings contents to logs.
- Use a least-privilege account allowed to publish only to the required repositories.
- Use HTTPS and a trusted certificate chain.
- Rotate/revoke tokens immediately if accidentally committed or logged.
- Maven settings password encryption depends on a master password; in CI, still use a secret manager and runner controls.

The POM describes where the artifact is published; settings describe the credentials of the publisher. Developers may have read access without deploy permissions, which is normal access separation.

## 7. Spring Boot 3.5 + Maven + Java 17 Example

Create project `order-service` using Spring Initializr or create the following files. Use `spring-boot-starter-parent` to manage plugin/dependency versions and repackage configuration.

### 7.1. Structure

```text
order-service/
├── pom.xml
├── mvnw
├── mvnw.cmd
├── .mvn/wrapper/
│   ├── maven-wrapper.jar
│   └── maven-wrapper.properties
└── src/
    ├── main/java/com/example/platform/order/
    │   ├── OrderApplication.java
    │   └── OrderController.java
    └── test/java/com/example/platform/order/
        └── OrderControllerTest.java
```

Wrapper scripts/JAR must be generated by Maven Wrapper/Initializr and committed properly; the diagram shows structure only and does not replace wrapper binaries.

### 7.2. pom.xml

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example.platform</groupId>
    <artifactId>order-service</artifactId>
    <version>1.4.0-SNAPSHOT</version>
    <name>Order Service</name>
    <description>Example Spring Boot artifact publication</description>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

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
            </plugin>
        </plugins>
    </build>
</project>
```

Spring Boot 3.5 Maven Plugin requires Maven 3.6.3 or later. `groupId`/`artifactId`/`version` define GAV; `distributionManagement` selects the remote repository; `spring-boot-maven-plugin` creates the executable JAR. When inheriting the starter parent, the `repackage` execution is already configured, so no duplicate execution is needed.

### 7.3. Main Class

`src/main/java/com/example/platform/order/OrderApplication.java`:

```java
package com.example.platform.order;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
```

### 7.4. Controller

`src/main/java/com/example/platform/order/OrderController.java`:

```java
package com.example.platform.order;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {
    @GetMapping("/orders/status")
    public Map<String, String> status() {
        return Map.of("service", "order-service", "status", "ready");
    }
}
```

### 7.5. JUnit Test

`src/test/java/com/example/platform/order/OrderControllerTest.java`:

```java
package com.example.platform.order;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderControllerTest {
    @Autowired
    private MockMvc mockMvc;

    @Test
    void reportsReady() throws Exception {
        mockMvc.perform(get("/orders/status"))
                .andExpect(status().isOk())
                .andExpect(content().json(
                        "{\"service\":\"order-service\",\"status\":\"ready\"}"));
    }
}
```

The test verifies the HTTP response in a Spring MVC test context without binding port 8080. JSON response:

```json
{
  "service": "order-service",
  "status": "ready"
}
```

`content().json` compares JSON structure regardless of key order. This is Java/Spring source requiring Maven dependencies; the project cannot be compiled with bare `javac` without the Spring/JUnit classpath.

## 8. Installing the Artifact to Local Repository with mvn install

From the root directory:

```bash
./mvnw --version
./mvnw clean verify
./mvnw clean install
```

On Windows:

```powershell
.\mvnw.cmd --version
.\mvnw.cmd clean verify
.\mvnw.cmd clean install
```

`clean install` runs the phases preceding install: validate, compile, test, package, verify, and any bound goals, then writes the artifact/POM to the local repository.

For GAV `com.example.platform:order-service:1.4.0-SNAPSHOT`, the path typically contains:

```text
~/.m2/repository/com/example/platform/order-service/1.4.0-SNAPSHOT/
```

Because Spring Boot Maven Plugin repackages the main JAR, the default installed artifact is an **executable JAR**. It runs with `java -jar` but should not be used as a standard dependency because application classes live under `BOOT-INF/classes`. Section 12 explains how to preserve a plain JAR.

### 8.1. Inspecting the Local Artifact

Unix/macOS:

```bash
ls -la ~/.m2/repository/com/example/platform/order-service/1.4.0-SNAPSHOT/
```

PowerShell:

```powershell
Get-ChildItem "$env:USERPROFILE\.m2\repository\com\example\platform\order-service\1.4.0-SNAPSHOT"
```

Typical files present:

```text
order-service-1.4.0-SNAPSHOT.jar
order-service-1.4.0-SNAPSHOT.pom
```

A local snapshot does not necessarily have a timestamped filename like a remote snapshot. Maven manages local metadata suitable for that machine's resolver.

### 8.2. Using the Artifact from Another Project

Consumer declares:

```xml
<dependency>
    <groupId>com.example.platform</groupId>
    <artifactId>order-service</artifactId>
    <version>1.4.0-SNAPSHOT</version>
</dependency>
```

On the same machine, Maven can resolve it after install. However, if the consumer imports classes from `OrderApplication`/`OrderController` of an executable Boot JAR, they may not be found because the executable layout is unsuitable as a dependency. For shared code, publish a plain library module or attach a separate plain JAR.

## 9. Remote Publishing with mvn deploy

### 9.1. Configuring User Settings

Ensure `~/.m2/settings.xml` has a `server.id` matching the POM:

```xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0
              https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <servers>
        <server>
            <id>company-releases</id>
            <username>${env.MAVEN_REPO_USER}</username>
            <password>${env.MAVEN_REPO_TOKEN}</password>
        </server>
        <server>
            <id>company-snapshots</id>
            <username>${env.MAVEN_REPO_USER}</username>
            <password>${env.MAVEN_REPO_TOKEN}</password>
        </server>
    </servers>
</settings>
```

Supply environment variables from the secret store/CI. If releases and snapshots use different tokens, use separate variables.

### 9.2. Running deploy

The POM currently has version `1.4.0-SNAPSHOT`, so Maven selects `snapshotRepository`:

```bash
./mvnw -B -ntp clean deploy
```

- `-B` enables batch mode for CI.
- `-ntp` disables transfer progress for cleaner logs.
- `clean` deletes previous build outputs.
- `deploy` runs the lifecycle through deploy, including compile/test/package/verify/install before upload.

When the version is `1.4.0` (without `-SNAPSHOT`), Maven selects `<repository>`. Change the version according to the approved release process; never switch to a release version just to test deploy.

### 9.3. Verifying Publication

After `BUILD SUCCESS`, check:

- Repository manager has the exact GAV.
- JAR/POM/attached artifacts are present.
- Version resides in the right release/snapshot repository.
- A consumer project can resolve the artifact from remote.
- The published artifact is the exact file that was tested.

Errors during `deploy:deploy` can happen after compile/test/package succeed; distinguish build errors from upload/auth/repository policy errors.

## 10. Verifying Remote Access from a Consumer Project

In the consumer POM, `<repositories>` is used to download dependencies:

```xml
<repositories>
    <repository>
        <id>company-public</id>
        <url>https://repo.example.com/repository/maven-public/</url>
        <releases>
            <enabled>true</enabled>
        </releases>
        <snapshots>
            <enabled>true</enabled>
        </snapshots>
    </repository>
</repositories>
```

`company-public` is an illustrative endpoint; many organizations configure a mirror in settings to route requests through the repository manager.

Add the dependency:

```xml
<dependency>
    <groupId>com.example.platform</groupId>
    <artifactId>order-service</artifactId>
    <version>1.4.0-SNAPSHOT</version>
</dependency>
```

A private consumer repository may require read credentials in settings; the server ID must match the repository/mirror ID that Maven uses.

### 10.1. Checking for New Snapshots

If the local cache holds an older snapshot, `-U` instructs Maven to check for updates:

```bash
./mvnw -U dependency:tree
./mvnw -U test
```

`-U` does not alter immutable release artifacts and does not resolve access permission issues. For a mistakenly published release version, release a new version per policy rather than overwriting.

**Do not use local install to prove remote deploy.** A consumer on the same machine can pull the artifact from `~/.m2/repository`. To prove real remote resolution, use a clean/separate local repository or another runner, and ensure the consumer routes to the right remote endpoint.

You can use a temporary local repository in the consumer:

```bash
./mvnw -Dmaven.repo.local=target/consumer-m2 -U test
```

Run the command inside the consumer project with appropriate `<repositories>` and read credentials in settings if the repository is private. There is no need to delete the developer's entire `~/.m2/repository`.

## 11. Snapshot and Release in the Release Workflow

### 11.1. Snapshot

`1.4.1-SNAPSHOT` is a development version that can be republished. The repository manager typically generates a timestamp/build number and updates `maven-metadata.xml`; the resolver uses metadata to pick the matching snapshot.

Snapshots are useful when multiple modules are integrating, CI builds from development branches, or consumers need to test APIs before a release. Avoid long-term snapshots in production if immutability is required; the same snapshot coordinate can point to different contents at different times.

### 11.2. Release

`1.4.0` is a release version per Maven convention. Repository managers usually block overwriting the same release coordinate. Releases should be built from a locked source revision, pass test/verification, and have a release record. If a bug is found after publishing, release a new version like `1.4.1`.

The `-SNAPSHOT` suffix is a Maven version convention, not synonymous with the Git `develop` branch. Record source commit/build metadata separately when traceability is required.

## 12. Spring Boot Executable JAR During install/deploy

The Spring Boot Maven Plugin `repackage` goal transforms a normal JAR/WAR into an executable archive. With `spring-boot-starter-parent`, the repackage execution is already configured; declaring the plugin is enough.

An executable JAR puts application classes under `BOOT-INF/classes` and dependencies under `BOOT-INF/lib`. It is meant for `java -jar`, but **unsuitable as a standard dependency JAR** because consumer classloaders do not look inside that nested layout.

### 12.1. Preserving Plain JAR and Attaching Executable JAR via Classifier

If you need to publish both a library JAR and an executable JAR, configure a classifier for repackage:

```xml
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
```

Place this fragment inside `<build><plugins>`. When using the starter parent, modify the existing `repackage` execution id; avoid adding a duplicate execution.

Typical result:

```text
order-service-1.4.0-SNAPSHOT.jar       -> plain JAR
order-service-1.4.0-SNAPSHOT-exec.jar  -> executable Spring Boot JAR
```

Maven install/deploy can publish both the main artifact and the classifier-attached executable artifact. Consumer dependencies default to the plain JAR; the executable artifact carries classifier `exec`.

### 12.2. Separating Library and Application Modules

A multi-module design is usually cleaner:

```text
platform-parent (packaging=pom)
      |
      +-- domain-library (plain JAR)
      |
      +-- order-service (executable Spring Boot JAR)
              |
              +-- dependency -> domain-library
```

The library publishes a plain JAR for other modules to use; the application module repackages into an executable JAR to run. Do not use an executable Boot JAR as a shared library simply because both have the `.jar` extension.

## 13. Maven Multi-Module Deploy from Aggregator

Root POM:

```xml
<packaging>pom</packaging>
<modules>
    <module>domain-library</module>
    <module>order-service</module>
</modules>
```

The parent can hold `distributionManagement` for child modules to inherit if the POM relationship is configured properly. Run from root:

```bash
./mvnw -B -ntp clean deploy
```

The Maven reactor collects modules, orders them by build/dependency relationships, and runs the lifecycle for each project.

Deploy only the application module along with its required dependencies:

```bash
./mvnw -pl :order-service -am deploy
```

- `-pl :order-service` selects the module by artifactId.
- `-am` adds projects in the reactor that the module depends on.
- `deploy` publishes the selected projects.

This command can also publish dependency modules pulled in by `-am`; verify the scope before using in CI. If you only want to build/test, choose `verify` instead of deploy.

**Reactor deploy is not an atomic transaction.** The first module may already be uploaded when the last module fails. For multi-module releases, use your repository manager's staging/close/promote feature if available or a partial-publication handling process; do not assume the server rolls everything back automatically.

## 14. Artifacts Not Built by a Maven Project: install-file and deploy-file

Use these goals for external JARs without a standard Maven build, not as the normal publishing method for source projects with a POM.

### 14.1. Installing an External JAR into Local Repository

```bash
./mvnw install:install-file \
  -Dfile=vendor-sdk.jar \
  -DgroupId=com.vendor \
  -DartifactId=vendor-sdk \
  -Dversion=2.3.0 \
  -Dpackaging=jar \
  -DgeneratePom=true
```

`install:install-file` installs locally only. `-DgeneratePom=true` generates a minimal POM and cannot automatically infer full transitive dependencies. If the vendor provides a POM, use `-DpomFile` to preserve accurate metadata.

### 14.2. Deploying a Single File Remotely

```bash
./mvnw deploy:deploy-file \
  -Dfile=vendor-sdk.jar \
  -DgroupId=com.vendor \
  -DartifactId=vendor-sdk \
  -Dversion=2.3.0 \
  -Dpackaging=jar \
  -DrepositoryId=company-releases \
  -Durl=https://repo.example.com/repository/maven-releases/
```

`deploy:deploy-file` uploads a single artifact; `repositoryId` must match the server ID in settings. This goal does not run the source project's build/test workflow. Exact syntax/parameters depend on the Maven Deploy Plugin version; consult plugin docs and pin the appropriate version before automating.

## 15. CI/CD: Safe and Repeatable Publishing

A release job should:

1. Check out the source revision and determine the release/snapshot version.
2. Set up the pinned JDK/Maven Wrapper versions.
3. Supply user settings/credentials from a secret manager.
4. Run verify/tests and quality gates.
5. Build/package the artifact.
6. Deploy to the right snapshot/release repository.
7. Verify GAV, POM, and attached artifacts in the repository manager.
8. Run a consumer smoke test or dependency resolution from remote.
9. Record build number, source commit, checksum, and release record.
10. Rotate/revoke tokens when no longer needed.

Sample CI command:

```bash
./mvnw -B -ntp clean deploy
```

**Do not use `-DskipTests` by default for releases.** It skips running tests (though it may still compile test sources depending on plugins); `-Dmaven.test.skip=true` skips compiling tests as well. Only skip if an earlier quality gate already verified the code and the published artifact is the exact one that passed that gate.

Permission separation:

- Developers normally have read access to the dependency repository.
- CI release jobs have permission to deploy releases.
- CI integration jobs have permission to deploy snapshots.
- The repository manager enforces immutable release policies, snapshot retention, and cleanup.

A release version should be built once, verified, and that exact verified artifact published. Rebuilding in another stage can yield different bytes due to timestamps/dependencies/environment; pass the artifact through the pipeline or verify checksums/digests.

## 16. Security, TLS, and Repository Manager

- Use HTTPS and a trusted certificate chain.
- Never disable TLS validation to work around certificate errors; install the proper CA for Maven/JDK/runner.
- Credentials live in user settings/secret injection, not in the POM.
- Do not pass passwords on the command line where shell history/process lists/logs can capture them.
- Use tokens scoped to publish only to the required repository/path.
- Separate release and snapshot permissions.
- Do not share debug logs containing internal URLs, usernames, local paths, or credentials.
- Track checksums/signatures/audit logs per policy.
- For critical artifacts, add SBOMs, signatures, and provenance/attestation; `mvn deploy` alone does not prove an artifact is safe or built from approved source.

## 17. Common Errors

| Symptom | Cause | Resolution |
|---|---|---|
| `401 Unauthorized` | Wrong token or server ID mismatch | Match repository ID with settings server ID |
| `403 Forbidden` | Account lacks deploy permission | Grant proper permission on the repository |
| `Repository does not allow updating assets` | Release version already exists | Bump version, do not overwrite release |
| Snapshot went to release repo | Wrong `snapshotRepository` or version | Check `-SNAPSHOT` suffix and effective POM |
| Release went to snapshot repo | Wrong version/POM config | Check `distributionManagement` |
| `mvn install` succeeded but another machine cannot resolve | Artifact exists only locally | Run `mvn deploy` |
| Consumer gets stale snapshot | Stale local metadata/cache | Use `-U`, check remote metadata |
| Cannot resolve after deploy | Wrong GAV/classifier or consumer uses another repo | Check repository browse UI, POM, and mirrors |
| JAR deployed but consumer cannot find classes | It is an executable Boot JAR | Publish a plain JAR or library module |
| Missing transitive dependencies | Deploy-file used without proper POM | Use `-DpomFile` or Maven lifecycle |
| `Failed to transfer file` | Network/proxy/TLS/DNS/server issue | Check endpoint, CA, proxy, server status |
| Checksum mismatch | Upload/storage/proxy corruption | Check artifact and repository metadata |
| Multi-module deploy stopped mid-way | One module failed after earlier modules uploaded | Use staging/release orchestration |
| CI lacks credentials | Secret/settings not supplied or wrong user home | Check settings path and env injection |
| Deployed to wrong URL | Parent/profile/override differed from expectation | Inspect `help:effective-pom` |
| Remote bytes differ from local | Rebuilt from another workspace or snapshot updated | Compare checksum, revision, and deployment metadata |

### 17.1. Diagnostic Commands

```bash
./mvnw --version
./mvnw help:effective-pom
./mvnw dependency:tree
./mvnw -B -ntp clean deploy
./mvnw -U verify
```

`help:effective-pom` reveals the active `distributionManagement` after inheritance/profiles. `dependency:tree` inspects the dependency graph, not remote deploy proof. When using `-s /path/to/settings.xml`, check the path and file permissions; do not share debug/settings output if it contains sensitive information.

## 18. End-to-End Practice

**A — Build/test:** in the section 7 project, run `./mvnw clean verify`. Expect `BUILD SUCCESS` and `OrderControllerTest` passing.

**B — Local install:** run `./mvnw clean install`; inspect `~/.m2/repository/com/example/platform/order-service/1.4.0-SNAPSHOT/`.

**C — Deploy snapshot:** replace the example URL with a real snapshot repository, provide credentials via settings/secret manager, keep version `1.4.0-SNAPSHOT`, and run `./mvnw -B -ntp clean deploy`. Verify the repository manager received the artifact and metadata.

**D — Consumer test:** create another project, declare `<repositories>` for the read endpoint and the dependency GAV; use a clean local repository or another runner to prove the artifact downloads from remote.

**E — Release:** when approved, change the version to `1.4.0` per the release process, build/test/verify from the locked source revision, and deploy to the release repository. Never redeploy the same release version if a bug is found; release a new version.

**F — Multi-module:** run from the aggregator, inspect the reactor summary, and verify which module publishes a plain JAR and which publishes an executable JAR/classifier.

### Checklist Before Enabling Deploy in CI

- [ ] Maven Wrapper and Java version are pinned.
- [ ] POM GAV complies with release policy.
- [ ] `distributionManagement` has the right release/snapshot URLs and IDs.
- [ ] `settings.xml` has `server.id` matching the IDs in POM.
- [ ] Credentials come from a secret store, never committed/logged.
- [ ] Repository uses HTTPS and a valid certificate.
- [ ] Release repository is immutable; snapshot repository has retention/cleanup.
- [ ] `mvn verify` and quality gates pass before deploy.
- [ ] Understood that `mvn install` is local-only.
- [ ] `mvn deploy` runs in an environment with publish permissions.
- [ ] POM/JAR/classifiers/attached artifacts have been verified.
- [ ] Consumer project resolves the exact GAV from remote.
- [ ] Executable Spring Boot JAR is not mistakenly used as a library dependency.
- [ ] Multi-module deploy order and partial failure handling are addressed.
- [ ] Release record stores checksum/source revision.
- [ ] Tests are not skipped by default on release.

### Official Documentation

- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — POM Reference: Distribution Management](https://maven.apache.org/pom.html#Distribution_Management)
- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html)
- [Apache Maven — Deploying over HTTP(S), Credentials and Repository IDs](https://maven.apache.org/guides/mini/guide-deployment-transports.html)
- [Apache Maven — Maven Deploy Plugin](https://maven.apache.org/plugins/maven-deploy-plugin/)
- [Apache Maven — Maven Install Plugin](https://maven.apache.org/plugins/maven-install-plugin/)
- [Apache Maven — Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html)
- [Spring Boot 3.5 — Maven Plugin: Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html)
- [Spring Boot 3.5 — Build and Use an Executable JAR](https://docs.spring.io/spring-boot/3.5/how-to/build.html)

**Key takeaway:** `install` only puts the artifact into the **local Maven repository**; `deploy` uploads the artifact to a **remote repository**. `distributionManagement` specifies the publish destination, while `settings.xml` holds credentials looked up by exact `server.id`. With Spring Boot, verify the JAR type being published: executable archives are for running, plain JARs are for dependencies; confirm GAV, POM, classifiers, and remote resolution before considering a release complete.