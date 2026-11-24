# Troubleshooting Plugin Not Found, Unresolved Dependencies, and Authenticated Repositories

## 1. Classify the Error Before Fixing

A Maven/Spring Boot build can fail with messages such as **No plugin found for prefix**, **PluginResolutionException**, **Could not resolve dependencies**, **Could not transfer artifact**, HTTP **401/403/407**, **PKIX path building failed**, **UnknownHostException**, timeouts, or **maven-default-http-blocker**.

These errors do not share the same root cause. Plugin resolution differs from dependency resolution; repository authentication differs from proxy authentication; TLS trust differs from username/password. Identify **the first unresolved artifact**, the URL Maven is calling, and the response type before changing versions or editing the POM.

| Group | Message | Where to Check First |
| --- | --- | --- |
| Plugin | No plugin found for prefix, PluginResolutionException | Plugin coordinates/version, pluginRepositories |
| Dependency | Could not resolve dependencies, Failed to read artifact descriptor | GAV, repositories, parent/BOM, transitive path |
| Repository auth | 401, 403 | settings.xml, server ID, token, and read permission |
| Proxy | 407 | settings.xml proxies, proxy account |
| TLS | PKIX path building failed | CA chain, JDK truststore, TLS inspection |
| Network | DNS, timeout, connection refused | DNS, VPN, firewall, proxy, service health |
| Policy/path | 404, blocked HTTP | URL, repository layout, release/snapshot policy |
| Local state | Cached failure, offline failure | .m2 cache, update policy, offline mode |

## 2. Maven Has Two Repository Groups

Maven uses a local repository (default **USER_HOME/.m2/repository**) to cache artifacts, and remote repositories to download external artifacts.

| Configuration | Purpose |
| --- | --- |
| **repositories** | Download project dependencies, parent POMs, and BOMs |
| **pluginRepositories** | Download Maven plugins and plugin artifacts |
| **distributionManagement** | Where project artifacts are deployed/published |
| **mirrors** | Override repository URLs during resolution |
| **servers** | Credentials for a repository, mirror, or deployment server |

**`repositories` does not replace `pluginRepositories`.** Dependencies may download fine while a plugin is still not found because plugins reside in a separate repository or the `pluginRepository` profile is not active.

## 3. Resolving Plugin Not Found

### 3.1. Verify Coordinates and Prefix

A Maven plugin has three primary coordinates: `groupId`, `artifactId`, `version`. For example, the Spring Boot Maven Plugin:

~~~text
org.springframework.boot:spring-boot-maven-plugin:3.5.16
~~~

A prefix command:

~~~bash
./mvnw spring-boot:run
~~~

tells Maven to look up the plugin with prefix **spring-boot**. When prefix metadata fails to resolve, try the full coordinates:

~~~bash
./mvnw org.springframework.boot:spring-boot-maven-plugin:3.5.16:run
~~~

Full coordinates bypass the prefix lookup step, though Maven still needs to download the plugin if it is not yet in the local repository. If this command also fails, check the version, repository, mirror, authentication, and network.

### 3.2. Common Causes

1. Typo in groupId/artifactId/prefix.
2. Non-existent version or release/SNAPSHOT disabled.
3. Plugin resides in a dedicated repository but `pluginRepository` is missing.
4. Profile containing `pluginRepository` is not active.
5. Mirror does not proxy plugin artifacts or its URL is wrong.
6. Server ID does not match repository/mirror ID so credentials are not used.
7. Proxy, TLS, DNS, or firewall blocks the request.
8. Local repository is not writable due to permissions/disk space.
9. Repository does not contain the requested plugin version.

### 3.3. Spring Boot Plugin Version Management

When inheriting **spring-boot-starter-parent**, Maven receives dependency management and plugin management. You can declare the plugin without a version:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

If you only import the **spring-boot-dependencies** BOM, the BOM manages dependency versions but does not provide plugin management like the starter parent does. In that case, declare the plugin version and the `repackage` goal explicitly:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <version>3.5.16</version>
    <executions>
        <execution>
            <goals>
                <goal>repackage</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Spring Boot 3.5.16 requires Java 17+ and Maven 3.6.3+. Verify which Maven is actually running:

~~~bash
./mvnw --version
java -version
~~~

Prefer the Maven Wrapper committed in the project so local environments and CI use the same Maven distribution.

## 4. Plugin Repositories Differ from Dependency Repositories

If a company maintains separate dependency and plugin repositories, the POM may declare:

~~~xml
<repositories>
    <repository>
        <id>company-dependencies</id>
        <url>https://repo.example.com/repository/maven-dependencies/</url>
        <releases><enabled>true</enabled></releases>
        <snapshots><enabled>false</enabled></snapshots>
    </repository>
</repositories>

<pluginRepositories>
    <pluginRepository>
        <id>company-plugins</id>
        <url>https://repo.example.com/repository/maven-plugins/</url>
        <releases><enabled>true</enabled></releases>
        <snapshots><enabled>false</enabled></snapshots>
    </pluginRepository>
</pluginRepositories>
~~~

The two IDs are distinct, so `settings.xml` needs two corresponding server entries. If a plugin only exists in **company-plugins**, declaring **company-dependencies** alone will not help Maven find the plugin.

### 4.1. Releases and Snapshots

A **1.2.0-SNAPSHOT** version requires a repository with snapshots enabled. A release version **1.2.0** requires releases enabled. Plugin repositories also have these two flags.

~~~xml
<releases><enabled>false</enabled></releases>
<snapshots>
    <enabled>true</enabled>
    <updatePolicy>always</updatePolicy>
</snapshots>
~~~

The snippet above only illustrates a snapshot repository. Do not change a release to SNAPSHOT just to dodge an error if the artifact is not published to a snapshot repository.

## 5. Unresolved Dependencies

### 5.1. Check GAV and Artifact Metadata

Maven coordinates consist of:
- **groupId**: namespace.
- **artifactId**: artifact name.
- **version**: version.
- **type**: artifact type, usually `jar`.
- **classifier**: artifact variant, if any.

Example:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
    <version>3.5.16</version>
</dependency>
~~~

When using the corresponding Spring Boot parent/BOM, the version is already managed and can be omitted. If resolution fails, check GAV spelling, whether the version is published, whether the artifact exists in the repository, release/SNAPSHOT policies, and classifier/type.

### 5.2. DependencyManagement Does Not Add Dependencies Automatically

A BOM/parent manages versions, but does not automatically add a dependency to the classpath. The project must still declare the dependency in **dependencies**.

Similarly, **pluginManagement** manages configuration/versions when a plugin is declared; it does not automatically activate all plugins.

### 5.3. Transitive Dependencies

A direct dependency may exist, yet its POM points to a transitive dependency that cannot be downloaded. Logs usually indicate the path:

~~~text
application
  -> library-a
      -> library-b
          -> library-c
~~~

Focus on the first unresolved artifact. Once the required plugin can download, run:

~~~bash
./mvnw dependency:tree -Dverbose
~~~

This command displays the dependency graph, selected versions, scopes, and exclusions. If the Maven Dependency Plugin itself fails to resolve, fix plugin resolution first or inspect the effective POM.

## 6. Checking Active Profiles and Effective Configuration

Repositories may live inside a profile in the POM or `settings.xml`. If a profile is not active, repositories inside it do not participate in resolution.

~~~bash
./mvnw help:active-profiles
./mvnw help:effective-pom -Dverbose
./mvnw help:effective-settings
~~~

- **help:active-profiles**: which profiles are currently active.
- **help:effective-pom**: POM after inheritance and applied profiles.
- **help:effective-settings**: merged settings from global and user settings.

Help Plugin goals must also be resolved. If the Help Plugin cannot be downloaded yet, use `-X` logs and inspect the POM/settings directly.

Settings profile example:

~~~xml
<profiles>
    <profile>
        <id>company-repositories</id>
        <repositories>
            <repository>
                <id>company-dependencies</id>
                <url>https://repo.example.com/repository/maven-public/</url>
            </repository>
        </repositories>
        <pluginRepositories>
            <pluginRepository>
                <id>company-plugins</id>
                <url>https://repo.example.com/repository/maven-public/</url>
            </pluginRepository>
        </pluginRepositories>
    </profile>
</profiles>
<activeProfiles>
    <activeProfile>company-repositories</activeProfile>
</activeProfiles>
~~~

You can explicitly activate a profile:

~~~bash
./mvnw -Pcompany-repositories clean verify
~~~

## 7. Authentication in settings.xml

Maven separates credentials from the POM. Repository URLs/IDs can be shared in the project; username/password/tokens live in **settings.xml**.

Common locations:
- Global: **MAVEN_HOME/conf/settings.xml**.
- User: **USER_HOME/.m2/settings.xml**.

If both exist, Maven merges them; user settings take higher precedence when configurations conflict. You can select user settings with **-s** and global settings with **-gs**.

### 7.1. Server ID Must Match Repository ID

POM:

~~~xml
<repository>
    <id>company-dependencies</id>
    <url>https://repo.example.com/repository/maven-dependencies/</url>
</repository>
~~~

settings.xml:

~~~xml
<servers>
    <server>
        <id>company-dependencies</id>
        <username>build-user</username>
        <password>token-from-secret-store</password>
    </server>
</servers>
~~~

**ID is the key mapping credentials, not username.** If the POM uses `company-dependencies` while settings uses `company-releases`, Maven may fail to send the right credentials and the server returns 401.

### 7.2. Using Environment Variables

~~~xml
<servers>
    <server>
        <id>company-dependencies</id>
        <username>${env.MVN_REPO_USER}</username>
        <password>${env.MVN_REPO_TOKEN}</password>
    </server>
    <server>
        <id>company-plugins</id>
        <username>${env.MVN_REPO_USER}</username>
        <password>${env.MVN_REPO_TOKEN}</password>
    </server>
</servers>
~~~

Linux/macOS:

~~~bash
export MVN_REPO_USER="build-user"
export MVN_REPO_TOKEN="token-from-secret-store"
./mvnw -s /secure/path/settings.xml clean verify
~~~

PowerShell:

~~~powershell
$env:MVN_REPO_USER = "build-user"
$env:MVN_REPO_TOKEN = "token-from-secret-store"
.\\mvnw.cmd -s C:\\secure\\settings.xml clean verify
~~~

Environment variables must be set in the exact process running Maven. Do not put real tokens into POMs, source control, shell history, command-line logs, or screenshots.

## 8. Mirrors and Mirror Credentials

A Maven mirror replaces repository URLs without modifying the POM.

~~~xml
<mirrors>
    <mirror>
        <id>company-mirror</id>
        <url>https://repo.example.com/repository/maven-public/</url>
        <mirrorOf>central</mirrorOf>
    </mirror>
</mirrors>
~~~

Maven has an original repository ID **central**, yet the actual request goes to mirror ID **company-mirror**. Therefore, server credentials must use the mirror ID:

~~~xml
<servers>
    <server>
        <id>company-mirror</id>
        <username>${env.MVN_REPO_USER}</username>
        <password>${env.MVN_REPO_TOKEN}</password>
    </server>
</servers>
~~~

If the mirror has ID `company-mirror` while the server only declares ID `central`, credentials may not be used.

### 8.1. Mirroring All Repositories

~~~xml
<mirrors>
    <mirror>
        <id>company-mirror</id>
        <url>https://repo.example.com/repository/maven-public/</url>
        <mirrorOf>*</mirrorOf>
    </mirror>
</mirrors>
~~~

The internal endpoint must proxy/host all required artifacts, including plugins, parent POMs, and dependencies. **`mirrorOf=*` does not automatically aggregate multiple repositories**; the repository manager must be configured as an appropriate group/proxy.

Some patterns:

| Pattern | Meaning |
| --- | --- |
| central | Repository with ID `central` |
| * | Every repository |
| external:* | External repositories, excluding localhost/file |
| repo1,repo2 | Two specific IDs |
| *,!inhouse | Every repository except `inhouse` |

Do not add arbitrary whitespace in comma-separated lists. Maven picks one matching mirror per repository; multiple matching mirrors are not combined into a fallback list.

## 9. Proxy Authentication Differs from Repository Authentication

Requests may pass through a proxy before reaching the repository. The proxy and the repository are two separate places that may require credentials.

~~~xml
<proxies>
    <proxy>
        <id>company-proxy</id>
        <active>true</active>
        <protocol>http</protocol>
        <host>proxy.example.com</host>
        <port>8080</port>
        <username>${env.MVN_PROXY_USER}</username>
        <password>${env.MVN_PROXY_PASSWORD}</password>
        <nonProxyHosts>localhost|127.0.0.1|*.internal.example.com</nonProxyHosts>
    </proxy>
</proxies>
~~~

Use the exact proxy protocol/host/port provided by your network team. **nonProxyHosts** is a pipe-delimited (`|`) list of hosts that bypass the proxy.

- **407** is usually proxy authentication.
- **401** is usually repository authentication.

Do not edit the POM before identifying which server returned the status.

## 10. TLS and PKIX

The message:

~~~text
PKIX path building failed
unable to find valid certification path to requested target
~~~

usually indicates that the Java truststore does not trust the certificate chain of the HTTPS server or TLS inspection proxy.

Check:
- Whether the HTTPS URL and hostname are correct.
- Whether the certificate is expired or missing an intermediate CA.
- Which JDK/truststore Maven is using.
- Whether a corporate proxy uses a private CA that is not trusted yet.
- Whether the CI image has the required CA certificates.

If there is a private CA, obtain the verified certificate chain from an administrator and configure the truststore per policy. Example:

~~~bash
export MAVEN_OPTS="-Djavax.net.ssl.trustStore=/secure/company-truststore.p12 -Djavax.net.ssl.trustStoreType=PKCS12"
./mvnw clean verify
~~~

The path and keystore type must match the actual file. Do not put the truststore password into logs/command lines if secret injection can be used.

**Do not disable SSL verification, switch HTTPS to HTTP, or ignore certificate errors.** Doing so removes protection against repository spoofing and man-in-the-middle attacks.

## 11. Maven 3.8.1+ Blocks External HTTP Repositories

Starting from Maven 3.8.1, external repositories using HTTP are blocked by default via **maven-default-http-blocker** to reduce the risk of downloading dependencies over unencrypted connections.

Common message:

~~~text
Blocked mirror for repositories:
[maven-default-http-blocker (http://0.0.0.0/)]
~~~

How to resolve:
1. Locate the direct POM or transitive dependency POM declaring the HTTP URL.
2. Upgrade the dependency to a version using HTTPS if available.
3. If the organization controls the repository, use a trusted HTTPS mirror.
4. Check that the repository manager proxies upstream over HTTPS.
5. Do not remove the blocker or allow HTTP globally just to make the build pass.

The HTTP URL sometimes resides in a transitive dependency's POM, not the application POM. The log will point to the dependency path leading to the legacy POM. Updating the dependency is usually the sustainable fix.

## 12. Understanding HTTP Status Codes from Repositories

The codes below are common diagnostic signals, not absolute rules for every repository manager.

| Status/Error | Common Meaning | What to Check |
| --- | --- | --- |
| 401 Unauthorized | Missing/wrong credentials | Server ID, token/password, expiration, auth scheme |
| 403 Forbidden | No permission or blocked by policy | Read permission, token scope, IP allowlist |
| 404 Not Found | Artifact/version/path does not exist or repo does not proxy it | GAV, URL, layout, classifier |
| 407 Proxy Authentication Required | Proxy requires credentials | settings.xml proxies, proxy account |
| 429 Too Many Requests | Rate limit | Retry/backoff, CI concurrency, quota |
| 5xx | Temporary repository/proxy/server error | Service health, upstream, status page |
| PKIX/TLS handshake | Certificate/truststore issue | CA chain, JDK truststore, proxy |
| UnknownHostException | DNS cannot resolve host | DNS, VPN, hostname, proxy |
| Timeout/refused | Network path/port/service unreachable | Firewall, route, proxy, service |

Some repositories intentionally return 404 instead of 401 to avoid disclosing whether a private artifact exists. Combine HTTP responses with server logs and account permissions.

### 12.1. 401

Compare the repository ID in the POM/settings profile, the mirror ID in `settings.xml`, the server ID in `servers`, and the actual URL in `-X` logs. If a mirror exists, compare against the **mirror ID**, not just the original repository ID.

### 12.2. 403

A token may authenticate successfully yet lack read package/repository permissions. Check token scope, repository path, project ACL, account, IP allowlist, and release/snapshot policy. Grant the minimum permissions required for reading dependencies/plugins; publish/deploy uses separate permissions.

### 12.3. 404

A Maven repository uses a layout based on `groupId/artifactId/version`. Example:

~~~text
org/example/library/1.2.3/library-1.2.3.pom
org/example/library/1.2.3/library-1.2.3.jar
~~~

A version may only have a POM or a specific classifier. Check whether the artifact was published completely and whether the repository manager proxies the right upstream.

## 13. Local Repository, Cache, and Offline Mode

Maven stores artifacts in **USER_HOME/.m2/repository**. If a previous download failed, metadata/cache may cause subsequent builds to keep reporting a cached failure. Do not delete the entire local repository immediately when encountering an error.

### 13.1. Use `-U` at the Right Time

~~~bash
./mvnw -U clean verify
~~~

**-U** forces Maven to check for missing releases and updated SNAPSHOTs on remote repositories. Use it after fixing repository URLs/credentials or when suspecting a cached failure.

**-U does not fix** typos, non-existent artifacts, expired tokens, 401/403, DNS/TLS/firewalls, or blocked HTTP.

### 13.2. Offline Mode

~~~bash
./mvnw -o clean verify
~~~

**-o** tells Maven to operate offline. Only use it when required parent POMs, plugins, plugin dependencies, and project dependencies are already in the local repository. When investigating artifact download failures, do not enable offline mode.

### 13.3. Scoped Cache Cleanup

1. Confirm the URL/coordinates/repository are correct.
2. Use `-U` so Maven retries.
3. If it still fails, locate the exact artifact/version directory in `.m2`.
4. Delete only the cache of the failing artifact/version once the exact scope is known.
5. Rebuild and read the transfer logs.

Do not delete the entire `.m2/repository` on a shared developer/CI machine; doing so forces re-downloading many artifacts, increases network load, and breaks caches for other projects.

## 14. Ordered Diagnostic Command Sequence

### Step 1: Confirm Maven/JDK

~~~bash
./mvnw --version
java -version
~~~

### Step 2: Capture the Full Error

~~~bash
./mvnw -U -e -X validate
~~~

- **-U**: checks missing releases and updated snapshots.
- **-e**: prints exception details.
- **-X**: enables debug logs, revealing repository URLs/mirrors and resolution steps.

Do not post unredacted `-X` logs to public issues. Logs may contain private repository URLs, usernames, environment values, or sensitive metadata.

### Step 3: Check Profiles and POM

~~~bash
./mvnw help:active-profiles
./mvnw help:effective-pom -Dverbose
~~~

Look for `spring-boot-maven-plugin` version, `pluginRepositories`, `repositories`, `dependencyManagement`, `pluginManagement`, and applied profiles.

### Step 4: Check Settings

~~~bash
./mvnw help:effective-settings
~~~

Confirm mirrors, server IDs, active settings profiles, proxy, local repository, and offline setting. Maven Help Plugin hides passwords by default. **Do not enable `showPasswords=true`** when sharing logs.

### Step 5: Inspect the Dependency Graph

~~~bash
./mvnw dependency:tree -Dverbose
~~~

Look for transitive dependencies, version conflicts, exclusions, and scopes. If the dependency plugin cannot be downloaded yet, fix plugin resolution first.

### Step 6: Clean Build

~~~bash
./mvnw -U -B -ntp clean verify
~~~

`clean` deletes `target` of the current project; it does not delete the entire local Maven repository.

## 15. Minimal Spring Boot Project for Reproduction

The example uses Java 17 and Spring Boot 3.5.16. Spring Boot 3.5.16 requires Maven 3.6.3 or later.

### 15.1. Structure

~~~text
repository-diagnostic/
├── pom.xml
├── mvnw
├── mvnw.cmd
├── .mvn/wrapper/...
└── src/
    └── main/
        ├── java/com/example/repository/
        │   ├── RepositoryDiagnosticApplication.java
        │   └── HealthController.java
        └── resources/application.properties
~~~

The Maven Wrapper should be generated via Spring Initializr or the Maven Wrapper plugin and committed to the repository.

### 15.2. Main Class

File **src/main/java/com/example/repository/RepositoryDiagnosticApplication.java**:

~~~java
package com.example.repository;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RepositoryDiagnosticApplication {
    public static void main(String[] args) {
        SpringApplication.run(RepositoryDiagnosticApplication.class, args);
    }
}
~~~

### 15.3. Controller

File **src/main/java/com/example/repository/HealthController.java**:

~~~java
package com.example.repository;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HealthController {
    @GetMapping("/repository-check")
    public String check() {
        return "repository-resolution-ok";
    }
}
~~~

### 15.4. application.properties

~~~properties
spring.application.name=repository-diagnostic
server.port=8080
~~~

### 15.5. Basic POM

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>repository-diagnostic</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
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
~~~

With this POM, Maven uses the Spring Boot parent to manage dependency/plugin versions. There is no need to add versions for the starter or plugin.

### 15.6. Build and Run

~~~bash
./mvnw -B -ntp clean verify
./mvnw spring-boot:run
~~~

From another terminal:

~~~bash
curl --fail --silent --show-error http://localhost:8080/repository-check
~~~

Exact response body:

~~~text
repository-resolution-ok
~~~

If the build passes and the endpoint returns the expected body, dependencies/plugins resolve in the current environment, the app compiles/starts, and the endpoint works. That does not prove all private repositories or all production profiles have been verified.

## 16. CI/CD: Providing Credentials Securely

A pipeline typically needs to check out source, set up JDK/Wrapper, provide `settings.xml` from a secret store, run Maven build/test, and archive reports/artifacts. Never store credentials inside artifacts.

Illustrative GitHub Actions example:

~~~yaml
name: Maven build

on:
  push:
    branches:
      - main
  pull_request:

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v6

      - name: Set up Java
        uses: actions/setup-java@v5
        with:
          distribution: temurin
          java-version: "17"
          cache: maven

      - name: Create Maven settings
        env:
          MVN_REPO_USER: ${{ secrets.MVN_REPO_USER }}
          MVN_REPO_TOKEN: ${{ secrets.MVN_REPO_TOKEN }}
        run: |
          mkdir -p "$HOME/.m2"
          cat > "$HOME/.m2/settings.xml" <<'EOF'
          <settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
            <servers>
              <server>
                <id>company-mirror</id>
                <username>${env.MVN_REPO_USER}</username>
                <password>${env.MVN_REPO_TOKEN}</password>
              </server>
            </servers>
            <mirrors>
              <mirror>
                <id>company-mirror</id>
                <url>https://repo.example.com/repository/maven-public/</url>
                <mirrorOf>*</mirrorOf>
              </mirror>
            </mirrors>
          </settings>
          EOF
          chmod 600 "$HOME/.m2/settings.xml"

      - name: Verify
        run: ./mvnw -B -ntp -U clean verify
~~~

This is a template. Replace registry endpoints/secret names according to your organization; pin GitHub Actions by commit SHA in production pipelines per supply-chain policy.

### 16.1. Pull Requests from Forks

Do not grant private repository tokens or publish credentials to workflows running untrusted code from forks. Separate PR verification jobs from release/sign/publish jobs. If private dependencies are needed to test PRs, design a restricted access policy and prevent untrusted scripts from reading secrets.

### 16.2. Caching Maven Dependencies

CI can cache the local Maven repository to reduce download time. However, caching cannot fix expired credentials, wrong mirror URLs, missing artifacts, repositories not proxying plugins, or TLS/CA issues.

To isolate the cache:

~~~bash
./mvnw -Dmaven.repo.local=target/m2-diagnostic -U -B clean verify
~~~

This command creates a fresh cache in `target`; the first run will download more. Do not use a temporary cache path as a permanent configuration without considering disk space and CI cache policy.

## 17. Decision Table: Where to Fix?

| Message | Where to Check | First Action |
| --- | --- | --- |
| No plugin found for prefix | Prefix, plugin group, pluginRepositories | Try full coordinates, verify plugin version/repository |
| PluginResolutionException | Plugin coordinates, pluginRepositories, settings | Read transfer URL error and server ID |
| Could not resolve dependencies | GAV, repositories, parent/BOM, profiles | Verify artifact/version and dependency path |
| Could not find artifact | Repository URL/path, release/snapshot | Check whether artifact is published and repository policy |
| 401 | settings.xml servers | Match server ID with repository/mirror ID, token |
| 403 | Repository permissions/policy | Check read scope, project ACL, IP policy |
| 407 | settings.xml proxies | Check proxy credentials |
| PKIX path building failed | JDK truststore/corporate CA | Import verified CA, configure truststore |
| UnknownHostException | DNS/network | Check host, VPN, DNS/proxy |
| Blocked mirror | POM/transitive POM HTTP URL | Switch to HTTPS or trusted HTTPS mirror |
| Cached failure | Local .m2 cache/update policy | After fixing remote, run `-U` |
| Offline resolution failure | Offline mode | Remove `-o` when remote download is needed |
| Permission denied in .m2 | Local repository path | Fix owner/permissions/disk |

## 18. Common Configuration Mistakes

- **Putting credentials in the POM:** POMs are committed and shared; use `settings.xml`/secret stores.
- **Server ID not matching mirror ID:** Maven connects to the mirror, so credentials must match the mirror ID.
- **Declaring only `repositories`:** plugins in a separate repo require `pluginRepositories`.
- **Confusing `dependencyManagement` with `dependencies`:** a BOM manages versions; it does not add dependencies to the classpath automatically.
- **Changing versions to dodge authentication:** fix credentials/permissions at the root cause.
- **Disabling TLS or re-enabling HTTP:** leaves dependency downloads vulnerable to spoofing; use HTTPS and trusted CAs.
- **Using `-U` as a cure-all:** `-U` does not fix typos, permissions, URLs, proxies, TLS, or non-existent artifacts.
- **Deleting all of `.m2`:** increases build time/network load and masks root causes; handle caches with scoped cleanup.

## 19. Practice Exercises

**Question 1.** The POM declares repository ID `company-dependencies`, but settings has server ID `company-releases`. Why might you receive 401?

**Answer:** Maven maps credentials by repository/server ID. Since the two IDs differ, credentials do not match the request.

**Question 2.** Dependencies download fine, yet plugins fail to download. Why?

**Answer:** Dependencies use `repositories`; plugins use `pluginRepositories`. The two lists can differ.

**Question 3.** Why do full coordinates help diagnose "No plugin found for prefix"?

**Answer:** They bypass prefix lookup. If full coordinates resolve, the issue may lie in prefix metadata/group mapping.

**Question 4.** A mirror has ID `company-mirror` and `mirrorOf=central`. Which ID must server credentials use?

**Answer:** `company-mirror`, because Maven connects through that mirror.

**Question 5.** A dependency version is `1.2.0-SNAPSHOT`, but the repository only enables releases. What happens?

**Answer:** Maven does not look for snapshots in that repository. A repository enabling snapshots and appropriate metadata is required.

**Question 6.** Maven returns 407. Should you change the repository password?

**Answer:** Not as a first step. 407 is proxy authentication; inspect `settings.xml` proxies.

**Question 7.** Maven 3.8.1+ reports `maven-default-http-blocker`. What is the safe fix?

**Answer:** Update the URL to HTTPS or use a managed HTTPS mirror. Do not remove the HTTP blocker just to make the build pass.

**Question 8.** Does `help:effective-settings` display passwords?

**Answer:** Not by default. Do not enable `showPasswords` when sharing logs.

**Question 9.** After fixing the token, Maven still reports a cached transfer failure. What should you do?

**Answer:** Run `-U` so Maven rechecks missing releases/updated snapshots; if necessary, delete only the specific artifact/version cache after verifying remote config.

**Question 10.** You imported the `spring-boot-dependencies` BOM, yet the plugin has no version. Why?

**Answer:** The BOM manages dependency versions, not plugin management like the starter parent does. Declare the plugin version explicitly or inherit the parent.

## 20. Troubleshooting Checklist

- [ ] Identify whether the error is in plugin, dependency, authentication, proxy, TLS, or local cache.
- [ ] Confirm Maven/JDK versions via the Maven Wrapper.
- [ ] Check plugin `groupId`, `artifactId`, `version`, and `goal`.
- [ ] Distinguish `pluginRepositories` from `repositories`.
- [ ] Check release/snapshot policy.
- [ ] Check active profiles and effective POM.
- [ ] Check effective settings, mirror URL, and `mirrorOf`.
- [ ] Match server ID against the actual repository ID or mirror ID.
- [ ] Verify token, read permission, expiration, and proxy credentials.
- [ ] Check HTTPS certificate chain and truststore.
- [ ] Check for external HTTP repositories blocked by Maven.
- [ ] Use `-U` after fixing remote configuration if needed.
- [ ] Clean only the specific artifact cache when cache corruption is evidenced.
- [ ] Never commit credentials or share unredacted debug logs.
- [ ] Run `clean verify` and inspect outputs/artifacts after fixing.
- [ ] Verify CI uses the same Maven settings/profiles as the verified environment.

## 21. Consolidated Diagnostic Workflow

~~~text
Maven build fails
       |
       v
Read first unresolved coordinate and remote URL
       |
       +---- Plugin?
       |       +--> Check prefix / full coordinates
       |       +--> Check pluginRepositories
       |       +--> Check plugin version + release/snapshot
       |
       +---- Dependency?
       |       +--> Check GAV + parent/BOM
       |       +--> Check repositories + active profiles
       |       +--> Check transitive dependency path
       |
       +---- HTTP/auth/network?
               +--> 401/403: server ID, token, read permission
               +--> 407: proxy credentials
               +--> 404: coordinates, path, repository content
               +--> PKIX: CA/truststore
               +--> timeout/DNS: network/proxy
               +--> HTTP blocker: replace with HTTPS/mirror
       |
       v
Inspect effective POM/settings and -X logs
       |
       v
Correct one root cause
       |
       v
Retry with -U when remote cache may be stale
       |
       v
mvn clean verify
       |
       v
Record verified configuration and keep secrets out of logs
~~~

Reading **the first unresolved artifact and URL** is usually far more effective than changing multiple versions at once, adding more repositories, or deleting the local cache.

## 22. Conclusion

Three groups of errors are commonly lumped together as “Maven cannot download dependencies”, yet their fixes differ:

- **Plugin not found**: check plugin coordinates, prefix, `pluginRepositories`, and plugin version.
- **Dependency not found**: check GAV, `repositories`, `dependencyManagement`, transitive paths, active profiles, and releases/snapshots.
- **Repository authentication**: check `settings.xml`, server ID, mirror ID, token scope, and read permissions.
- **Proxy/TLS/network**: handle proxy credentials, DNS, firewalls, and certificate trust.
- **Local cache**: use `-U` or clean only the exact artifact after the remote configuration is already correct.

A stable Maven configuration requires a POM that clearly describes dependencies/plugins, `settings.xml` holding credentials, managed mirrors/repository managers, and CI using the same Maven Wrapper/profiles. When a build fails, rely on artifact coordinates, the actual URL, and the HTTP/TLS response to fix the right layer.

## 23. Official References

- Apache Maven — PluginResolutionException: https://cwiki.apache.org/confluence/spaces/MAVEN/pages/4589202/PluginResolutionException
- Apache Maven — Settings Reference: https://maven.apache.org/settings.html
- Apache Maven — Introduction to Repositories: https://maven.apache.org/guides/introduction/introduction-to-repositories
- Apache Maven — Using Mirrors for Repositories: https://maven.apache.org/guides/mini/guide-mirror-settings
- Apache Maven — Configuring Maven: https://maven.apache.org/guides/mini/guide-configuring-maven.html
- Apache Maven — Configuring a Proxy: https://maven.apache.org/guides/mini/guide-proxies.html
- Apache Maven — Password Encryption: https://maven.apache.org/guides/mini/guide-encryption.html
- Apache Maven — Maven 3.8.1 Release Notes: https://maven.apache.org/docs/3.8.1/release-notes.html
- Apache Maven Help Plugin — effective-settings: https://maven.apache.org/plugins/maven-help-plugin/effective-settings-mojo.html
- Apache Maven Help Plugin — effective-pom: https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html
- Apache Maven — POM Reference: https://maven.apache.org/pom.html
- Spring Boot 3.5.16 — Maven Plugin: https://docs.spring.io/spring-boot/3.5/maven-plugin/
- Spring Boot 3.5.16 — System Requirements: https://docs.spring.io/spring-boot/3.5/system-requirements.html
- Spring Boot 3.5 — Build Systems: https://docs.spring.io/spring-boot/3.5/reference/using/build-systems.html
