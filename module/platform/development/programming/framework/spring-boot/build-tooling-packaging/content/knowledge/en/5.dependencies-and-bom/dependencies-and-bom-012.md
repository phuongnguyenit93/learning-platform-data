# Configuring Maven Repositories, Mirrors, Proxies, and Credentials in Spring Boot

## 1. Big Picture: Where Are Libraries Found and How Do Connections Route?

A Spring Boot project using Maven must download several kinds of artifacts: parent POMs, the Spring Boot BOM, starters, *transitive dependencies*, and Maven plugins such as compiler, surefire, resources, or `spring-boot-maven-plugin`. If any of those cannot be reached, `mvn package` can fail even when Java code is completely valid.

Four components to distinguish:

- **Remote Maven repository:** stores POMs, JARs, metadata, and plugins by `groupId:artifactId:version` coordinates. Maven Central and internal Nexus/Artifactory servers are examples.
- **Local repository:** artifact cache on the build machine, defaulting to `~/.m2/repository`. It avoids re-downloading, yet is not a mirror server.
- **Mirror:** replaces the address of a remote repository Maven connects to. For instance, every fetch for ID `central` gets redirected to an internal repository manager endpoint.
- **Network proxy:** intermediary server for network connections. It determines the network route to a repository, whereas a mirror determines the target repository. You may use both, one, or neither.

Credentials also have two scopes: **repository credentials** for artifact repositories and **proxy credentials** for the network proxy. When encountering HTTP 401, 403, or 407, identify which party is rejecting the request.

```text
pom.xml: dependency / parent / plugin / BOM
           |
           v
      Maven Resolver
           |
           +--> local cache (~/.m2/repository)
           |
           +--> logical repository (central, private, vendor)
                      |
                      +--> settings.xml: select mirror by mirrorOf
                      |
                      +--> settings.xml: fetch server credentials by ID
                      |
                      +--> settings.xml: proxy / nonProxyHosts
                                        |
                                        v
                              Repository manager / Internet
```

**A BOM does not specify where to download artifacts.** Maven BOMs and `spring-boot-starter-parent` mainly manage versions; repositories/mirrors/networking/credentials decide whether the corresponding POMs and JARs can actually be fetched.

## 2. Put Configuration in the Right Place

| Location | Appropriate Content | Commit to Git? |
| --- | --- | --- |
| `pom.xml` | Dependencies, plugins, versions, project-needed repositories, `distributionManagement` | Yes, yet never place tokens/passwords here |
| `~/.m2/settings.xml` | Mirrors, proxies, server credentials, dev/CI machine profiles | No; machine-specific config that may contain secrets |
| `${maven.home}/conf/settings.xml` | Global settings for the installed Maven distribution | Typically system-managed |
| `~/.m2/repository` | Cache of downloaded artifacts/POMs/metadata | No; never edit directly to configure mirrors |
| `.mvn/maven.config` | Shared project-wide Maven command-line flags | Yes, if containing no secrets |
| CI-provided settings via `mvn -s <path>` | Build agent accounts and routing | Keep outside source control, least privilege |

Maven merges global and user settings, with user settings taking precedence for matching entries. `-s` specifies a user settings file, while `-gs` selects global settings. Maven Wrapper `./mvnw` helps pin a consistent Maven version for the repository.

**Principle:** POMs describe shared build requirements; settings describe network environment and access rights; secrets are supplied separately by users or CI. Never "fix" dependency download errors by putting usernames/passwords directly in `pom.xml` or repository URLs in Git.

## 3. Remote Repositories and How Maven Resolves Artifacts

For `org.springframework.boot:spring-boot-starter-web:3.5.0`, a standard Maven repository layout looks like:

```text
org/springframework/boot/spring-boot-starter-web/3.5.0/
  spring-boot-starter-web-3.5.0.pom
  spring-boot-starter-web-3.5.0.jar
```

Maven needs the POM to discover further dependencies and may need `maven-metadata.xml` for certain version/snapshot types. **A BOM has `pom` packaging**; having no JAR file for a BOM is normal. Maven downloads plugins from plugin repositories, which may differ from dependency repositories.

Maven Central is typically available via the Super POM. Add custom repositories only when an artifact or plugin truly does not exist in approved sources.

### 3.1. Dependency Repositories in `pom.xml`

Example adding a vendor repository, with an **illustrative, non-existent URL**:

```xml
<repositories>
    <repository>
        <id>vendor-releases</id>
        <url>https://repo.vendor.example/releases</url>
        <releases><enabled>true</enabled></releases>
        <snapshots><enabled>false</enabled></snapshots>
    </repository>
</repositories>
```

`<id>vendor-releases</id>` is the logical ID used inside Maven. If the repository requires authentication and **no mirror** applies, `<server><id>vendor-releases</id>` in settings must match this ID. If a mirror applies, the credentials ID is normally the **selected mirror's** ID.

Snapshots and releases are two critical policies: a release-only repo will not serve `1.0.0-SNAPSHOT`. When projects use non-fixed or snapshot dependencies, metadata/cache policies affect resolution.

### 3.2. Plugin Repositories Are Configured Separately

```xml
<pluginRepositories>
    <pluginRepository>
        <id>vendor-plugins</id>
        <url>https://repo.vendor.example/plugins</url>
    </pluginRepository>
</pluginRepositories>
```

`<repositories>` is where dependencies are searched. `<pluginRepositories>` is where build plugins and plugin dependencies are searched. If Maven downloads Spring Boot starters fine yet fails to download `spring-boot-maven-plugin` or `maven-surefire-plugin`, check plugin repositories/mirrors. Mirror rules can apply to both dependency and plugin repositories.

### 3.3. Repositories via Settings Profiles

You can use a settings profile on dev/CI machines when repositories should not live in the project POM:

```xml
<profiles>
    <profile>
        <id>internal-releases</id>
        <repositories>
            <repository>
                <id>team-releases</id>
                <url>https://repo.example.org/repository/team-releases/</url>
                <releases><enabled>true</enabled></releases>
                <snapshots><enabled>false</enabled></snapshots>
            </repository>
        </repositories>
    </profile>
</profiles>
<activeProfiles>
    <activeProfile>internal-releases</activeProfile>
</activeProfiles>
```

This snippet belongs **inside `<settings>`**, not as a standalone XML file. Existing profiles can also be activated with `mvn -Pinternal-releases package`. However, if an `external:*` or `*` mirror is active, `team-releases` may still be redirected to that mirror. To access it directly, configure mirror exclusions or have the repository manager aggregate internal sources too.

## 4. Mirrors in Maven: Meaning and Selection Order

Mirrors are declared in `settings.xml`:

```xml
<mirrors>
    <mirror>
        <id>corp-central</id>
        <name>Central via company cache</name>
        <url>https://repo.example.org/repository/maven-central/</url>
        <mirrorOf>central</mirrorOf>
    </mirror>
</mirrors>
```

`mirrorOf=central` replaces only the repository with ID `central`, not `vendor-releases` or `team-releases`. It maps an **original repository ID** to a **mirror with a new ID/URL**.

| `mirrorOf` Value | Behavior |
| --- | --- |
| `central` | Only the repository with ID `central` |
| `*` | Every repository; requires the mirror to serve/proxy all needed artifacts |
| `external:*` | Remote repositories, excluding localhost and `file:` repos |
| `external:http:*` | External HTTP repositories, excluding localhost (Maven 3.8+) |
| `central,vendor-releases` | Both listed IDs |
| `*,!team-releases` | All except ID `team-releases` |
| `external:*,!team-releases` | External repos, except `team-releases` |

When multiple mirrors exist, Maven prioritizes a mirror whose `mirrorOf` matches the original ID exactly, before evaluating advanced expressions in declaration order. Avoid unintended whitespace in pattern lists because Maven's parser has strict syntax rules.

**Maven does not simultaneously query multiple mirrors for one repository to find an artifact.** If you need to combine Maven Central, internal release/snapshot repos, and vendor repos, use a repository manager (group/virtual repo) that proxies or hosts all required sources. Defining multiple mirrors all with `mirrorOf=*` does not provide reliable fallback.

Choose `external:*` when keeping local/file repos for development; choose `*` when every source, including private repos, must pass through a governed endpoint. The backing repository manager must include **both plugins and POMs/BOMs**, or resolution errors will happen early.

## 5. Complete `~/.m2/settings.xml` Example: Mirror, Credentials, and Proxy

The example below assumes an HTTPS repository manager, separate account token, and an optional network proxy. **All `example.org` domains are illustrative URLs**; replace with real endpoints. If no proxy is needed, omit the entire `<proxies>` block.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0
                              https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <mirrors>
        <mirror>
            <id>corp-maven</id>
            <name>Corporate Maven repository manager</name>
            <url>https://repo.example.org/repository/maven-public/</url>
            <mirrorOf>external:*</mirrorOf>
        </mirror>
    </mirrors>

    <servers>
        <server>
            <id>corp-maven</id>
            <username>${env.MAVEN_REPO_USER}</username>
            <password>${env.MAVEN_REPO_TOKEN}</password>
        </server>
    </servers>

    <proxies>
        <proxy>
            <id>corp-egress</id>
            <active>true</active>
            <protocol>http</protocol>
            <host>proxy.example.org</host>
            <port>8080</port>
            <nonProxyHosts>*.example.org|localhost|127.0.0.1</nonProxyHosts>
        </proxy>
    </proxies>
</settings>
```

How this example works: Maven needs an artifact from `central`; `external:*` matches and redirects the request to `corp-maven`; Maven looks up `<server id="corp-maven">` for username/token; because hostname `repo.example.org` matches `*.example.org` in `nonProxyHosts`, the proxy is bypassed for this URL.

### 5.1. Passing Secrets via Environment Variables

Maven settings supports interpolating `${env.MAVEN_REPO_USER}` and `${env.MAVEN_REPO_TOKEN}`. Variables must be set before Maven launches, e.g., on Linux/macOS:

```bash
export MAVEN_REPO_USER="build-user"
# MAVEN_REPO_TOKEN should be injected securely by a secret manager/CI.
mvn -B -ntp verify
```

PowerShell example setting **username**, while the token comes from your organization's secret management:

```powershell
$env:MAVEN_REPO_USER = "build-user"
mvn -B -ntp verify
```

Never copy real tokens into committed scripts, command lines, or shell history. When CI injects tokens from a secret store, ensure secrets are scoped only to jobs needing them and never echoed/logged. Maven has version-specific password encryption mechanisms (Maven 3 and Maven 4 differ); check your version's docs before using them. Even when encrypted, protect settings files and master secrets.

### 5.2. Why Must IDs Match?

`<server><id>corp-maven</id>` **matches the mirror ID**, not the original `central` repository ID. If you rename the mirror to `company-group` while leaving server ID as `corp-maven`, Maven may fail to send credentials and get 401. For unmirrored private repos, the server ID must match the connected repository ID.

Avoid placing broad credentials on an overly wide mirror unless aligned with access policy. Use read-only accounts for fetching artifacts; keep publish permissions separate.

## 6. Proxies in Maven and Proxy Authentication Errors

A proxy does not cache artifacts like a repository manager; it forwards network traffic. If your organization requires Internet egress through a proxy, configure `<proxies>` in Maven `settings.xml`:

```xml
<proxies>
    <proxy>
        <id>corp-egress</id>
        <active>true</active>
        <protocol>http</protocol>
        <host>proxy.example.org</host>
        <port>8080</port>
        <username>${env.MAVEN_PROXY_USER}</username>
        <password>${env.MAVEN_PROXY_TOKEN}</password>
        <nonProxyHosts>*.example.org|localhost|127.0.0.1</nonProxyHosts>
    </proxy>
</proxies>
```

This **replaces the `<proxies>` block** in the sample settings; do not paste it as a second block. When the proxy needs no authentication, omit `username`/`password`. The proxy protocol can be `http` while the repository URL uses `https`: an HTTP proxy can open a TLS tunnel via CONNECT; verify against your actual infrastructure.

**`nonProxyHosts` is crucial:** if an internal repo is directly reachable, avoid routing connections to it through an Internet proxy. `*.example.org|localhost|127.0.0.1` is an example pattern—adjust it to your internal DNS. Some environments configure browser proxies/PAC files, yet JVM/Maven runs separately and does not automatically inherit every browser setting.

| Code / Symptom | Likely Meaning | Remediation Direction |
| --- | --- | --- |
| HTTP 401 | Repository rejected credentials or token expired | Check server ID after mirror mapping, token, and read permissions |
| HTTP 403 | Authenticated, yet lacks permission or blocked by policy | Check permissions/repository path and release/snapshot policy |
| HTTP 407 | **Proxy** requires authentication | Check proxy user/token and `nonProxyHosts` |
| `Connect timed out` | Network, firewall, proxy, VPN, or wrong host/port | Verify DNS and network route from the build machine |
| `UnknownHostException` | Host failed DNS resolution | Check repository URL and DNS/proxy |
| `PKIX path building failed` | JVM does not trust the TLS certificate chain | Install CA/trust store per policy; use an appropriate JDK |
| HTTP 404 | Artifact/version missing, wrong repo/group, or mirror missing upstream | Check coordinates, URL, snapshot/release policy, and repository manager |
| `Non-resolvable parent POM` | Maven could not download the parent | Check parent, mirror, credentials, and cache |
| `Non-resolvable import POM` | Maven could not download the BOM | Check BOM, repository, release policy, and proxy |
| `PluginResolutionException` | Could not download plugin | Check plugin repository, mirror, and permissions |

**Never disable TLS verification** to bypass `PKIX` errors. With corporate proxies performing HTTPS inspection, properly configure the corporate CA and Java trust store in use. HTTP 407 and 401 differ fundamentally: proxy authentication cannot be fixed by editing repository `<servers>`.

## 7. Reading Dependencies and Publishing Artifacts Are Separate Flows

Downloading dependencies occurs during resolution and can use mirrors; publishing Maven artifacts (`mvn deploy`) normally uses `distributionManagement`:

```xml
<distributionManagement>
    <repository>
        <id>team-releases</id>
        <url>https://repo.example.org/repository/team-releases/</url>
    </repository>
    <snapshotRepository>
        <id>team-snapshots</id>
        <url>https://repo.example.org/repository/team-snapshots/</url>
    </snapshotRepository>
</distributionManagement>
```

This is a **`pom.xml` snippet**. To deploy, `settings.xml` must have credentials matching IDs `team-releases` and `team-snapshots`, unless using an equivalent mechanism supported by your Maven version. **A `corp-maven` server ID used to read from a mirror does not guarantee deployment works**, because uploads target different IDs.

Maven `mvn package` builds archives; `mvn deploy` uploads Maven artifacts to the configured repository. OCI images and container registries use different publishing mechanisms (e.g., `docker push` or dedicated plugins); a Maven repository mirror does not act as a container registry.

## 8. Spring Boot Parent, BOM, and Repository Interaction

A minimal Maven project illustrating Spring Boot 3.5.0, Java 17:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>repository-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <properties><java.version>17</java.version></properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

This POM illustrates **dependency resolution**; lacking a `main`/`@SpringBootApplication` class, it is not a runnable HTTP server app. Version 3.5.0 is fixed for the example and does not imply it is the latest Spring Boot release.

In this build, Maven must fetch the parent POM, starter transitives, default plugins, and Boot Maven plugin. If your mirror only hosts internal JARs without proxying Central/Plugins, resolution will fail. If the parent POM cannot be resolved, Maven can fail **before** ever invoking the compiler or tests.

### When Importing the BOM Without Spring Boot Parent

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.5.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

This is a POM fragment, not a complete file. The BOM controls versions of managed dependencies, yet **does not supply all default plugin configurations like `spring-boot-starter-parent`**. Even after importing the BOM, `spring-boot-dependencies:3.5.0:pom` must still be downloadable from the selected repository.

## 9. Maven Inspection Tools and Troubleshooting Workflow

### 9.1. Essential Commands

```bash
mvn -version
mvn help:effective-settings
mvn help:active-profiles
mvn help:effective-pom
mvn -U -B -ntp dependency:tree
```

Meaning:

- `mvn -version` shows Maven version, Java version, and JVM path.
- `help:effective-settings` shows settings merged from user/global settings (mirrors/proxies/profiles), though output can be sensitive: **view only in authorized environments, never paste publicly**.
- `help:active-profiles` lists active profiles.
- `help:effective-pom` inspects inherited parent, dependency management, repositories, and plugins.
- `-U` forces re-checking artifact/metadata resolution (especially snapshots or cached missing-artifact markers); `-B` runs non-interactively in batch mode; `-ntp` hides download progress logs; `dependency:tree` prints the dependency tree.

Note: goals `help:*` and `dependency:tree` are Maven plugins themselves, so **they also must resolve from repositories** if not cached yet. In a completely offline environment, Help Plugin errors do not prove settings files are missing.

You can point to a specific CI settings file:

```bash
mvn -s /path/to/ci-settings.xml -B -ntp verify
```

That path is an example; on Windows use an appropriate Windows path. Confirm the file actually exists and was loaded, especially when dev machines pass while build agents lack `~/.m2/settings.xml`.

### 9.2. Investigating a Resolution Failure

1. Identify the **exact artifact** failing: parent POM, BOM, dependency, or Maven plugin; read `groupId/artifactId/version` and the failing URL.
2. Inspect **effective settings** and `mirrorOf` to see which endpoint Maven actually chose. Reading the POM alone is insufficient.
3. Verify **credential IDs**: server ID must match the selected mirror ID; deploying uses `distributionManagement.repository.id`.
4. Verify **networking** from the exact machine/agent running Maven: DNS, VPN, proxy, `nonProxyHosts`, JVM trust store. A browser on another machine succeeding does not prove CI has connectivity.
5. Verify the **repository manager** proxies the group containing the needed artifact, read permissions, release/snapshot policies, and token validity.
6. If upstream was fixed yet Maven keeps reporting "was cached ... resolution will not be reattempted," try `mvn -U ...`. Avoid immediately deleting all of `~/.m2/repository`, which causes heavy re-downloads without fixing root causes.
7. When `-X` debug output is needed, **redact credentials, headers, and sensitive URLs** before sharing logs.

`mvn -o package` runs offline only when every required artifact/POM/plugin is already in local cache; an offline PASS does not prove current repository connectivity works.

## 10. Using Gradle to Fetch Maven Artifacts: What Differs?

Gradle supports Maven repositories with its own configuration model. In a Gradle project, dependency repositories and plugin repositories are separate:

- `repositories` or `dependencyResolutionManagement.repositories`: where Java libraries, Spring Boot starters, BOMs, etc. are fetched.
- `pluginManagement.repositories`: where Gradle plugins (including plugin markers) are resolved; configured in `settings.gradle(.kts)`.
- `gradle.properties` / JVM system properties: proxy, secret, and Gradle option configuration.

**Version note:** starting in **Gradle 9.8.0**, an incubating feature can reuse Maven mirror settings when explicitly enabled via `org.gradle.mirror.maven.settings=true`. By default, Gradle **does not** read Maven `settings.xml`; even when enabled, Maven proxies/profiles are not imported. See section 10.4.

### 10.1. Gradle Kotlin DSL Example with Two Internal Maven Repositories

**`settings.gradle.kts`:**

```kotlin
pluginManagement {
    repositories {
        maven {
            name = "corpPlugins"
            url = uri("https://repo.example.org/repository/gradle-plugins/")
            credentials(PasswordCredentials::class)
        }
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        maven {
            name = "corpMaven"
            url = uri("https://repo.example.org/repository/maven-public/")
            credentials(PasswordCredentials::class)
        }
    }
}

rootProject.name = "spring-build-demo"
```

**`build.gradle.kts` to test dependency resolution:**

```kotlin
plugins {
    java
}

dependencies {
    implementation("org.apache.commons:commons-lang3:3.14.0")
}
```

These two files do not compile a full Spring Boot app; they illustrate repository setup and resolving a Java dependency. After substituting real URLs and supplying real credentials, run:

```bash
./gradlew dependencies --configuration compileClasspath
```

On Windows use `gradlew.bat`. `corpPlugins` must proxy **Gradle plugin markers** (e.g., Spring Boot Gradle plugin); otherwise add an approved plugin repository. `corpMaven` must supply regular dependencies. If a repository requires no auth, omit `credentials(...)`.

`RepositoriesMode.FAIL_ON_PROJECT_REPOS` enforces declaring repositories in settings, fitting centralized governance; under this mode, do not declare `repositories` in `build.gradle.kts` or the build will fail. If subprojects need per-project repositories, choose the matching mode intentionally.

### 10.2. Gradle Credentials: Externalized Properties

With repository names `corpMaven` and `corpPlugins`, `credentials(PasswordCredentials::class)` looks up conventional properties:

```properties
# ~/.gradle/gradle.properties - user-specific, DO NOT commit
corpMavenUsername=your-service-account
corpMavenPassword=token-from-secret-store
corpPluginsUsername=your-service-account
corpPluginsPassword=token-from-secret-store
```

Those values are **placeholders** and must never be used literally in production. In CI, pass equivalents via environment variables `ORG_GRADLE_PROJECT_corpMavenUsername` and `ORG_GRADLE_PROJECT_corpMavenPassword` from a secret manager. Never print tokens to console. When a repository expects an HTTP header token instead of basic authentication, use `HttpHeaderCredentials`/authentication per Gradle docs, still keeping secrets externalized.

### 10.3. Gradle Proxies Use JVM System Properties

**`~/.gradle/gradle.properties`**, example:

```properties
systemProp.http.proxyHost=proxy.example.org
systemProp.http.proxyPort=8080
systemProp.https.proxyHost=proxy.example.org
systemProp.https.proxyPort=8080
systemProp.http.nonProxyHosts=*.example.org|localhost|127.0.0.1
```

Note that `http.nonProxyHosts` is also the JVM property name typically honored for excluded hosts when handling HTTPS. For authenticated proxies, provide `systemProp.http.proxyUser` / `systemProp.http.proxyPassword` or HTTPS counterparts via protected user/CI configuration; avoid committing them into project `gradle.properties`. Gradle **does not read Maven settings' `<proxies>`** in place of this configuration.

### 10.4. Newer Gradle Feature: Reusing Maven Mirror Settings

Gradle **9.8.0 and later** offers experimental support, **disabled by default**. When an organization already maintains Maven mirrors and wants to share them, add to user-level `~/.gradle/gradle.properties`:

```properties
org.gradle.mirror.maven.settings=true
```

When enabled, Gradle reads corresponding `<mirrors>` and `<servers>` rules from Maven settings, applying `mirrorOf` to HTTP/HTTPS Maven repositories; it does **not** alter file repositories, Ivy, or S3/GCS. Gradle uses the repository **name** to match Maven repository IDs (with special handling for Central). The Gradle Plugin Portal may also be redirected if a rule matches, so internal repos must host or proxy plugin marker artifacts.

This feature **does not import Maven proxies, profiles, or pluginGroups**, nor does it alter publishing destinations. Certain newer Maven 4 password encryption formats are not yet supported per feature docs, so check exact Gradle/Maven versions. On older Gradle Wrappers or when the flag is off, declare `pluginManagement`/`dependencyResolutionManagement` explicitly as in section 10.1.

Because this is a newer feature, check your Gradle Wrapper version and its docs when troubleshooting instead of assuming every Gradle project reads Maven `settings.xml`.

## 11. Four Common Configuration Scenarios

### Dev Machine Reaching Maven Central Directly

If outbound HTTPS to the Internet is allowed without a proxy, a standard Spring Boot project builds without custom mirrors or `servers`. Maven Central is already a default source. When errors occur, check DNS/JDK/TLS/versions before adding extra repositories.

### Enterprise Mandating Nexus/Artifactory

Create a group/virtual repository managing approved upstreams, and point Maven `mirrorOf=external:*` or `*` to it; server ID must match mirror ID. In CI, inject secrets separately. In Gradle, configure mirrors in settings or (on newer versions, where suitable) opt into Maven mirror reuse. Test both plugin repositories and BOMs.

### Internal Repo Plus Separate Vendor Repo

If a group repository can aggregate both, use one simple endpoint. If `team-releases` must be accessed directly, `mirrorOf=external:*,!team-releases` can exclude that ID alongside a dedicated `<server id="team-releases">`. Never configure multiple `*` mirrors expecting Maven to fall back automatically across them.

### Works in Dev, Yet CI Fails with 401/PKIX

Compare Maven/Gradle Wrappers, JDK/`JAVA_HOME`, actual user settings on the agent, secret injection, server IDs, and corporate CAs. Never "fix" CI by committing tokens or disabling TLS in repositories.

## 12. Common Troubleshooting Table

| Symptom | Quick Check | Fix Direction |
| --- | --- | --- |
| Maven tries `repo.maven.apache.org` instead of intranet | `mvn help:effective-settings`, `mirrorOf`, `-s` file | Fix mirror pattern/ID and verify the actual settings file loaded |
| Mirror returns 404 for Spring Boot parent/BOM | Does repo proxy Central? Is group URL right? | Add approved upstream/hosted repo and check policy |
| Maven downloads dependencies fine, fails on plugins | Do `pluginRepositories`/mirrors serve plugin artifacts? | Configure an appropriate plugin repository |
| HTTP 401 from repository manager | Does server ID match mirror ID; is token valid? | Supply right server credentials and read permissions |
| HTTP 407 through corporate proxy | Is Maven `<proxy>` or Gradle JVM proxy accurate? | Supply proxy credentials and `nonProxyHosts` |
| `PKIX path building failed` | Trust store of the Java running Maven/Gradle | Install trusted CA properly; never disable SSL |
| Network timeout / DNS error | Does machine/CI have route and DNS to host? | Fix proxy/VPN/firewall/endpoint |
| `Non-resolvable import POM` | BOM coordinates/version, mirror, repo policy | Ensure BOM POM exists in approved sources |
| Gradle `Plugin ... was not found` | Does `pluginManagement.repositories` have plugin markers? | Add right plugin repo, separate from dependency repo if needed |
| Enabled Gradle mirror reuse, yet still bypasses proxy | Feature imports mirrors/servers only, not Maven proxies | Configure JVM system properties for Gradle |
| Cleared cache, yet still 404 | Remote truly lacks artifact or permissions are wrong | Fix upstream repo/credentials/version instead of repeatedly deleting cache |
| Maven `-o` succeeds, yet fresh machine fails | First machine relied on local cache | Test on a clean agent with proper connectivity |

## 13. Pre-CI/CD Checklist

1. **Valid sources:** ordinary dependencies, Spring Boot parent/BOM, transitive dependencies, Maven plugins, and Gradle plugin markers all resolve from approved sources.
2. **Accurate routing:** `mirrorOf` matches right repository IDs; proxy `nonProxyHosts` matches DNS; no accidental reliance on a dev machine/VPN.
3. **Least privilege:** dependency read accounts separated from publish permissions; no secrets in Git, URLs, logs, or build artifacts.
4. **TLS/integrity:** HTTPS, valid CA/trust store, checksums/signatures per policy, and upstream artifact traceability.
5. **Version/build:** stable Maven/Gradle Wrappers, defined Java runtime, consistent dependency/plugin version management; snapshots separated from releases.
6. **Environment-specific config:** user/CI `settings.xml` or `gradle.properties`, verifying agents receive secrets and exact config files.
7. **Real testing:** build on clean CI fetching dependencies/plugins, run tests, verify subsequent builds; never treat offline results as network proof.
8. **Safe debugging:** use `mvn help:effective-settings`, `mvn -U`, `gradlew dependencies`, and redact sensitive info; avoid sharing `-X` publicly.
9. **Repository governance:** lock write access on mirrors/groups, control external sources and cache update workflows. A mirror is a distribution mechanism, not an automatic guarantee of artifact trustworthiness.

## 14. Key Distinctions to Remember

- **Mirror ≠ proxy:** mirrors rewrite repository URLs; proxies route network connections. **Local repo ≠ mirror:** local repo is just a machine cache.
- **`mirrorOf=*` ≠ multiple fallback mirrors:** Maven picks one matching mirror; use a repository manager group for aggregated sources.
- **Server ID ≠ username:** server ID must match the repository/mirror ID Maven **actually connects to**, whereas username is the login account.
- **Dependency repository ≠ plugin repository:** inspect both, especially for Spring Boot builds using Maven/Gradle plugins.
- **BOM version management ≠ access rights:** valid version config cannot substitute for repositories/credentials.
- **`mvn deploy` ≠ fetching dependencies:** publishing uses separate IDs/URLs in `distributionManagement`, usually needing separate write permissions.
- **Maven settings ≠ Gradle settings:** Gradle 9.8+ supports conditional mirror reuse, yet Maven proxies are never auto-imported into Gradle.
- **HTTP 407 ≠ HTTP 401:** 407 is typically from a network proxy; 401 is typically from a repository.
- **Skipping TLS / committing tokens is never a valid fix:** fix CAs, IDs, proxies, permissions, and upstream repositories.

## 15. Versioned Official Documentation

- Maven – [Settings Reference](https://maven.apache.org/settings.html) (user/global settings, servers, mirrors, proxies, profiles).
- Maven – [Using Mirrors for Repositories](https://maven.apache.org/guides/mini/guide-mirror-settings.html) (`mirrorOf`, `external:*`, matching priority).
- Maven – [Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html) (versions, transitives, and BOMs).
- Maven – [Deployment Security Settings](https://maven.apache.org/guides/mini/guide-deployment-security-settings.html) (deploy credentials).
- Gradle – [Declaring Repositories](https://docs.gradle.org/current/userguide/declaring_repositories_basics.html).
- Gradle – [Centralizing Repository Declarations](https://docs.gradle.org/current/userguide/centralizing_repositories.html).
- Gradle – [Networking](https://docs.gradle.org/current/userguide/networking.html).
- Gradle – [Securing Repositories](https://docs.gradle.org/current/userguide/securing_repositories.html).
- Gradle – [Release Notes 9.8.0](https://docs.gradle.org/9.8.0/release-notes.html) (opt-in Maven mirror reuse).

**How to isolate the root cause when a dependency fails to download:** check **which artifact** Maven/Gradle is looking for -> original repository ID and URL -> mirror mapping -> proxy route -> credentials ID and permissions -> upstream/cache status. Inspecting layer by layer restores Spring Boot builds safely and consistently across dev machines and CI.